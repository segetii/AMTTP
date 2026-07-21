# -*- coding: utf-8 -*-
"""
v49_mode1_feature_search.py
============================

Find a formula that captures the Mode 1 reversal trade.

A Mode 1 segment (from v38 cluster analysis) is one where:
    • The strategy gained +4% to +6% above CB-release equity (peak_gain ≥ 4%)
    • Then a few large negative bars erased the gain
    • Final segment return ended up negative (≤ -2%) with negative skew (≤ -1)

This script:
  1. Runs v34 simulator on the full test set, extracts every active segment.
  2. Tags each segment as MODE1 (peak ≥ 4% & final ≤ -2%) or OTHER.
  3. Builds candidate features measured at SEGMENT-START time (not segment averages):
       - ODE state:         gamma_0, rhs_norm_0, omega_0, cos_theta_0, E_0
       - Pre-segment:       prev_lock_h, prev_seg_return
       - Calendar:          start_year, start_month, start_hour, start_dow
       - Early window:      first_4h_ret, first_24h_vol, first_4h_skew, first_4h_max_dd
       - Market:            btc_ret_24h, btc_vol_24h, btc_above_ma200
  4. Univariate AUC scan to rank features by Mode 1 discriminating power.
  5. Logistic regression to combine the top-3 features into one formula.
  6. Validates by simulating: skip every Mode 1-classified segment → measure new MaxDD.
"""
from __future__ import annotations

import json
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))

import run_crypto_godmode_v27_all_microstructure as v27
import run_crypto_godmode_v28_canonical_stability as v28
from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import (
    KAPPA_A, W_TARGET_A1, build_b_aligned, build_w_star,
    _predictive_scalars, CONV_MIN, CONV_MAX, W_BOX,
    ANNEAL_AMP, ANNEAL_PEAK, TradingDomain, EPSILON,
)
from run_crypto_canonical_v4 import A_FACTORS, N_STATE, DT, build_factor_returns
from run_crypto_godmode_v8_multiasset_shell import (
    ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol,
)
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import (
    DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, INIT, HOURS_PER_DAY,
    equity_metrics,
)
from run_crypto_godmode_v35_top5_cb_transition import (
    REG_VARIANT, K_NORMAL, RT_BPS, build_sigma, theta_from,
)

BAR      = "=" * 110
OUT_DIR_ = Path(OUT_DIR) / "v49_mode1_search"
PLOT_DIR = OUT_DIR_ / "plots"

# Use top variant: d=0.25, q=0.50 (the $617K baseline closest to v34 $730K)
D, Q = 0.25, 0.50
CB_HALT, CB_RESUME, CB_WINDOW_D = 0.08, 0.04, 90

# Loser definitions
# Mode 1 (reversal):  peaked then collapsed
MODE1_PEAK_THRESH   = 0.02   # peaked ≥ +2% above segment-start equity
MODE1_FINAL_THRESH  = -0.02  # ended ≤ -2% net
# Mode 0 (stillborn): never showed profit, bled from bar 1
MODE0_PEAK_THRESH   = 0.005  # peak_gain ≤ +0.5% (essentially never gained)
MODE0_FINAL_THRESH  = -0.03  # final ≤ -3%
# Generic loser
LOSS_THRESH         = -0.03


# ─── ODE engine ───────────────────────────────────────────────────────────────

def run_ode(df, train_mask, w_star_arr, b_arr, Sigma_cap, theta_base, kappa=KAPPA_A):
    T = len(df)
    R = np.column_stack([
        df["ret_btc"].fillna(0.0).values,
        df["ret_eth"].fillna(0.0).values,
        (df["ret_sol"].fillna(0.0).values if "ret_sol" in df.columns
         else df["ret_eth"].fillna(0.0).values),
    ])
    rho_train = []
    for t in np.where(train_mask)[0][::50]:
        sys_t = TradingDomain(A=A_FACTORS, b=b_arr[t], Sigma=Sigma_cap, kappa=kappa,
                              w_star=w_star_arr[t], theta=theta_base, epsilon=EPSILON).build()
        sc = _predictive_scalars(sys_t, np.zeros(N_STATE))
        if sc["rho_eff"] > 0: rho_train.append(sc["rho_eff"])
    rho_typ = float(np.median(rho_train)) if rho_train else 1.0

    keys = ["E","gamma","dE_dt","cos_theta","mfls","v_E","rho_eff","rhs_norm",
            "w_btc","w_eth","w_sol","pnl","pnl_long_only",
            "stop_flag","stale_flag","drift_flag","conviction","theta_t"]
    log = {k: np.zeros(T) for k in keys}
    w           = np.zeros(N_STATE)
    cos_th_prev = 0.0
    hours = df.index.hour
    t0 = time.time()
    for t in range(T):
        hr      = int(hours[t])
        theta_t = theta_base * (1.0 + ANNEAL_AMP * np.cos(2*np.pi*(hr-ANNEAL_PEAK)/24.0))
        sys_t = TradingDomain(A=A_FACTORS, b=b_arr[t], Sigma=Sigma_cap, kappa=kappa,
                              w_star=w_star_arr[t], theta=theta_t, epsilon=EPSILON).build()
        sc         = _predictive_scalars(sys_t, w)
        conviction = float(np.clip(-cos_th_prev, CONV_MIN, CONV_MAX))
        w          = np.clip(w + DT * sc["rhs"] * conviction, -W_BOX, W_BOX)
        log["E"][t]=sc["E"]; log["gamma"][t]=sc["gamma"]; log["dE_dt"][t]=sc["dE_dt"]
        log["cos_theta"][t]=sc["cos_theta"]; log["mfls"][t]=sc["mfls"]; log["v_E"][t]=sc["v_E"]
        log["rho_eff"][t]=sc["rho_eff"]; log["rhs_norm"][t]=sc["rhs_norm"]
        log["w_btc"][t]=w[0]; log["w_eth"][t]=w[1]; log["w_sol"][t]=w[2]
        log["pnl"][t]=float(w@R[t]); log["pnl_long_only"][t]=float(R[t].mean())
        log["stop_flag"][t]=1.0 if sc["gamma"]>0.90 else 0.0
        log["stale_flag"][t]=1.0 if (sc["rho_eff"]>0 and sc["rho_eff"]<0.1*rho_typ) else 0.0
        log["drift_flag"][t]=1.0 if sc["cos_theta"]>0.0 else 0.0
        log["conviction"][t]=conviction; log["theta_t"][t]=theta_t
        cos_th_prev = sc["cos_theta"]
        if t>0 and t%5000==0:
            print(f"    ODE {t:>6}/{T}  ({time.time()-t0:.1f}s)")
    return pd.DataFrame(log, index=df.index), rho_typ


# ─── v34-style sim with full per-bar trace ────────────────────────────────────

def simulate_v34_trace(unit_normal, K_normal, cb_halt, cb_resume, cb_window_d):
    window_bars = cb_window_d * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq, peak_alltime = INIT, INIT
    halted = False
    eq_vals, y_vals, cb_flags = [], [], []
    N = len(unit_normal)
    for i in range(N):
        ur_n = float(unit_normal.iloc[i])
        while mono_dq and mono_dq[0][0] <= i - window_bars: mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq: mono_dq.pop()
        mono_dq.append((i, eq))
        roll_peak = mono_dq[0][1]
        cb_dd = max(0.0, 1.0 - eq/max(roll_peak,1e-12))
        dd_aty = max(0.0, 1.0 - eq/max(peak_alltime,1e-12))
        if not halted and cb_dd >= cb_halt: halted = True
        elif halted and cb_dd <= cb_resume: halted = False
        if halted: y = 0.0
        elif dd_aty <= DYN_DD_SOFT: y = 1.0
        elif dd_aty >= DYN_DD_STOP: y = DYN_Y_FLOOR
        else:
            y = DYN_Y_FLOOR + (1.0-DYN_Y_FLOOR)*(DYN_DD_STOP-dd_aty)/(DYN_DD_STOP-DYN_DD_SOFT)
        r = max(K_normal*y*ur_n, -0.95)
        eq *= (1.0 + r); peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq); y_vals.append(y); cb_flags.append(int(halted))
    return dict(eq=pd.Series(eq_vals, index=unit_normal.index),
                cb=pd.Series(cb_flags, index=unit_normal.index),
                y=pd.Series(y_vals, index=unit_normal.index))


# ─── Segment extraction with peak_gain & start-time features ────────────────

def extract_segments(sim, ode_log, df, btc_ret, btc_ma200, test_ts):
    eq    = sim["eq"]
    cb    = sim["cb"]
    rets  = eq.pct_change().fillna(0.0)
    test_mask = eq.index >= test_ts
    eq, cb, rets = eq[test_mask], cb[test_mask], rets[test_mask]
    ode = ode_log.reindex(eq.index, method="ffill")
    btc_ret_a = btc_ret.reindex(eq.index, method="ffill").fillna(0.0)
    btc_ma_a  = btc_ma200.reindex(eq.index, method="ffill").fillna(method="bfill")
    btc_arr   = df["btc"].reindex(eq.index, method="ffill").values

    arr = cb.values
    idx = cb.index
    segs = []
    in_seg, start_i = False, None
    prev_lock_h = 0
    prev_seg_ret = 0.0

    for i in range(len(arr)):
        active = arr[i] == 0
        if active and not in_seg:
            in_seg, start_i = True, i
            j = i - 1
            while j >= 0 and arr[j] == 1: j -= 1
            prev_lock_h = i - j - 1 if i > 0 else 0
        elif (not active or i == len(arr)-1) and in_seg:
            end_i = i if not active else i+1
            in_seg = False
            sl = slice(start_i, end_i)
            seg_eq, seg_rets, seg_ode = eq.iloc[sl], rets.iloc[sl], ode.iloc[sl]
            if len(seg_eq) < 4: 
                prev_seg_ret = float(seg_eq.iloc[-1]/seg_eq.iloc[0]-1)
                continue
            cum = seg_eq / seg_eq.iloc[0]
            seg_return = float(cum.iloc[-1]-1)
            peak_gain  = float(cum.max()-1)
            seg_maxdd  = float((cum/cum.cummax()-1).min())
            skew = float(seg_rets.skew()) if len(seg_rets)>3 else 0.0
            mode1     = (peak_gain >= MODE1_PEAK_THRESH) and (seg_return <= MODE1_FINAL_THRESH)
            mode0     = (peak_gain <= MODE0_PEAK_THRESH) and (seg_return <= MODE0_FINAL_THRESH)
            is_loser  = seg_return <= LOSS_THRESH

            # Start-time features (the only ones usable as a real-time filter)
            sb = seg_ode.iloc[0]
            gamma_0    = float(sb["gamma"])
            rhs_norm_0 = float(sb["rhs_norm"])
            omega_0    = gamma_0 * rhs_norm_0
            cos_th_0   = float(sb["cos_theta"])
            E_0        = float(sb["E"])
            rho_0      = float(sb["rho_eff"])
            conv_0     = float(sb["conviction"])
            mfls_0     = float(sb["mfls"])
            w_abs_0    = float(abs(sb["w_btc"]) + abs(sb["w_eth"]) + abs(sb["w_sol"]))

            # Early-window features (first 4 / 24 bars after start)
            first4 = seg_rets.iloc[:4]
            first24 = seg_rets.iloc[:min(24, len(seg_rets))]
            first4_ret = float((1+first4).prod()-1)
            first4_vol = float(first4.std() if len(first4)>1 else 0.0)
            first4_dd  = float(((1+first4).cumprod()/(1+first4).cumprod().cummax()-1).min())
            first24_vol = float(first24.std() if len(first24)>1 else 0.0)

            # Market context at start
            ts0 = idx[start_i]
            btc_24h_ret = float(btc_ret_a.iloc[max(0,start_i-24):start_i+1].sum())
            btc_24h_vol = float(btc_ret_a.iloc[max(0,start_i-24):start_i+1].std())
            above_ma    = bool(btc_arr[start_i] > btc_ma_a.iloc[start_i])

            segs.append(dict(
                start=ts0, end=idx[end_i-1], duration_h=len(seg_rets),
                seg_return=seg_return, peak_gain=peak_gain, seg_maxdd=seg_maxdd,
                pnl_skew=skew, mode1=int(mode1), mode0=int(mode0), loser=int(is_loser),
                # ODE state at start
                gamma_0=gamma_0, rhs_norm_0=rhs_norm_0, omega_0=omega_0,
                cos_theta_0=cos_th_0, E_0=E_0, rho_0=rho_0,
                conv_0=conv_0, mfls_0=mfls_0, w_abs_0=w_abs_0,
                # context
                prev_lock_h=prev_lock_h, prev_seg_ret=prev_seg_ret,
                start_year=ts0.year, start_month=ts0.month,
                start_hour=ts0.hour, start_dow=ts0.dayofweek,
                # early window
                first4_ret=first4_ret, first4_vol=first4_vol, first4_dd=first4_dd,
                first24_vol=first24_vol,
                # market
                btc_24h_ret=btc_24h_ret, btc_24h_vol=btc_24h_vol,
                btc_above_ma200=int(above_ma),
            ))
            prev_seg_ret = seg_return
    return pd.DataFrame(segs)


# ─── Univariate AUC scan ──────────────────────────────────────────────────────

def auc_score(y, x):
    """ROC-AUC. Returns area, plus the threshold maximising Youden J."""
    y = np.asarray(y, dtype=float); x = np.asarray(x, dtype=float)
    mask = ~np.isnan(x)
    y, x = y[mask], x[mask]
    if y.sum() == 0 or y.sum() == len(y): return 0.5, np.nan, 0.0, 0.0
    order = np.argsort(-x)
    y_s = y[order]; x_s = x[order]
    cum_pos = np.cumsum(y_s)
    cum_neg = np.cumsum(1 - y_s)
    P = y.sum(); N = len(y) - P
    tpr = cum_pos / P
    fpr = cum_neg / N
    auc = float(np.trapz(tpr, fpr))
    if auc < 0.5:
        auc = 1.0 - auc
        # flip direction
        order = np.argsort(x)
        y_s = y[order]; x_s = x[order]
        cum_pos = np.cumsum(y_s); cum_neg = np.cumsum(1 - y_s)
        tpr = cum_pos / P; fpr = cum_neg / N
        flip = True
    else:
        flip = False
    j = tpr - fpr
    k = int(np.argmax(j))
    return float(auc), float(x_s[k]), float(tpr[k]), float(fpr[k]), flip


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    print(BAR)
    print("  v49 — MODE 1 FEATURE SEARCH")
    print(f"  Definition: peak_gain ≥ {MODE1_PEAK_THRESH:+.0%}  &  seg_return ≤ {MODE1_FINAL_THRESH:+.0%}")
    print(f"  Variant:    d={D}, q={Q}, cb_halt={CB_HALT}, cb_resume={CB_RESUME}, win={CB_WINDOW_D}d")
    print(BAR)

    # Microstructure cache
    print("\n[0] Microstructure cache ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        v27._get_ms(sym)

    # Build inputs
    print("\n[1] Building inputs ...")
    df, _      = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_ts    = pd.Timestamp(TEST_START)
    w_star     = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned  = build_b_aligned(w_star)
    factor_R   = build_factor_returns(df)
    v27.RT_COST = RT_BPS / 10_000.0

    btc_ret = df["btc"].pct_change().fillna(0.0)
    btc_ma200 = df["btc"].rolling(200*HOURS_PER_DAY, min_periods=24).mean().bfill()

    # ODE
    print("\n[2] FFD Sigma + ODE ...")
    Sigma_base, _, sdiag, bdiag = build_sigma(factor_R, train_mask, df, D)
    theta = theta_from(b_aligned, train_mask, Sigma_base, bdiag["budget"], Q)
    log_ann, rho_typ = run_ode(df, train_mask, w_star, b_aligned, Sigma_base, theta)

    print("\n[3] Building unit returns via canonical v28 ...")
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                     signal_kind="wstar", use_quadrant=False)
    inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                     signal_kind="wstar", use_quadrant=True)
    inputs     = attach_q_hot(inputs_noq, inputs_q)
    sig_map    = {a: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{a}")
                  for a, _, _, idx in ASSETS}
    unit = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]

    # ── Sim + segment extraction ──
    print("\n[4] Simulating + extracting segments ...")
    sim = simulate_v34_trace(unit, K_NORMAL, CB_HALT, CB_RESUME, CB_WINDOW_D)
    final_baseline = float(sim["eq"][sim["eq"].index >= test_ts].iloc[-1])
    seg = extract_segments(sim, log_ann, df, btc_ret, btc_ma200, test_ts)
    print(f"  Total active segments on test set: {len(seg)}")
    print(f"  MODE 1 reversal (peak≥{MODE1_PEAK_THRESH:.0%} & final≤{MODE1_FINAL_THRESH:.0%}): "
          f"{int(seg['mode1'].sum())}")
    print(f"  MODE 0 stillborn (peak≤{MODE0_PEAK_THRESH:.1%} & final≤{MODE0_FINAL_THRESH:.0%}): "
          f"{int(seg['mode0'].sum())}")
    print(f"  Generic LOSER  (final≤{LOSS_THRESH:.0%}):                       "
          f"{int(seg['loser'].sum())}")
    print(f"  Pure winners   (final>0):                              "
          f"{int((seg['seg_return']>0).sum())}")
    print(f"  Baseline final equity: ${final_baseline:,.0f}")

    seg.to_csv(OUT_DIR_ / "segments.csv", index=False)
    print(f"  → segments.csv saved")

    # ── Segment table ──
    print("\n[5] All segments:")
    print(f"\n  {'start':<20} {'dur':>5}  {'final':>8}  {'peak':>7}  {'maxdd':>8}  "
          f"{'skew':>6}  {'M0':>2} {'M1':>2} {'L':>2}")
    for _, r in seg.iterrows():
        print(f"  {str(r['start'])[:19]:<20} {r['duration_h']:>5}  "
              f"{r['seg_return']:>+7.2%}  {r['peak_gain']:>+6.2%}  {r['seg_maxdd']:>+7.2%}  "
              f"{r['pnl_skew']:>+6.2f}  {r['mode0']:>2} {r['mode1']:>2} {r['loser']:>2}")

    # ── Pick target with enough samples ──
    targets = [("loser", "loser"), ("mode0", "mode0_stillborn"), ("mode1", "mode1_reversal")]
    target_col, target_name = None, None
    for col, name in targets:
        if seg[col].sum() >= 2:
            target_col, target_name = col, name
            print(f"\n  → Using target '{target_name}' (n={int(seg[col].sum())} positives, "
                  f"{int(len(seg)-seg[col].sum())} negatives)")
            break
    if target_col is None:
        print("  No target class has ≥2 samples. Aborting.")
        return
    y = seg[target_col].values

    # ── Univariate AUC scan ──
    print(f"\n[6] Univariate AUC scan (target = {target_name}):")
    feat_cols = [
        "gamma_0", "rhs_norm_0", "omega_0", "cos_theta_0", "E_0", "rho_0",
        "conv_0", "mfls_0", "w_abs_0",
        "prev_lock_h", "prev_seg_ret",
        "start_year", "start_month", "start_hour", "start_dow",
        "first4_ret", "first4_vol", "first4_dd", "first24_vol",
        "btc_24h_ret", "btc_24h_vol", "btc_above_ma200",
    ]
    rows = []
    if y.sum() < 2:
        print("  Not enough positive samples to scan. Aborting.")
        return
    for f in feat_cols:
        if f not in seg.columns: continue
        x = seg[f].values
        try:
            auc, thr, tpr, fpr, flip = auc_score(y, x)
            direction = "x ≤ thr" if flip else "x ≥ thr"
            rows.append((f, auc, thr, tpr, fpr, direction))
        except Exception:
            continue
    rows.sort(key=lambda r: -r[1])
    print(f"\n  {'feature':<18} {'AUC':>6}  {'thresh':>10}  {'TPR':>5}  {'FPR':>5}  rule")
    print("  " + "-"*70)
    for f, auc, thr, tpr, fpr, direction in rows:
        flag = "  ★" if auc >= 0.85 else ("  ◉" if auc >= 0.75 else "")
        print(f"  {f:<18} {auc:>6.3f}  {thr:>10.4f}  {tpr:>5.2f}  {fpr:>5.2f}  {direction}{flag}")

    # ── Best 1-feature filter ──
    best = rows[0]
    print(f"\n[7] BEST SINGLE-FEATURE FORMULA:")
    print(f"  Mode 1 if  {best[0]}  {best[5].replace('thr', f'{best[2]:.4f}')}")
    print(f"  AUC = {best[1]:.3f}   TPR = {best[3]:.2f}   FPR = {best[4]:.2f}")

    # ── Best 2-feature combo (greedy search via product) ──
    print(f"\n[8] Best 2-feature ratio/product combos:")
    feats_for_combo = [r for r in rows[:6] if r[1] > 0.55]
    combos = []
    X = seg[[r[0] for r in feats_for_combo]].copy()
    for i, (f1, _, _, _, _, _) in enumerate(feats_for_combo):
        for j, (f2, _, _, _, _, _) in enumerate(feats_for_combo):
            if i >= j: continue
            x1 = seg[f1].astype(float).values
            x2 = seg[f2].astype(float).values
            for op_name, op in [("*", lambda a,b: a*b),
                                 ("+", lambda a,b: a+b),
                                 ("-", lambda a,b: a-b),
                                 ("/", lambda a,b: a/(b+1e-9))]:
                try:
                    z = op(x1, x2)
                    if np.any(~np.isfinite(z)): continue
                    auc, thr, tpr, fpr, flip = auc_score(y, z)
                    combos.append((f"{f1} {op_name} {f2}", auc, thr, tpr, fpr,
                                   "x ≤ thr" if flip else "x ≥ thr"))
                except Exception:
                    continue
    combos.sort(key=lambda r: -r[1])
    print(f"  {'combo':<35} {'AUC':>6}  {'thresh':>12}  {'TPR':>5}  {'FPR':>5}  rule")
    print("  " + "-"*80)
    for c, auc, thr, tpr, fpr, direction in combos[:10]:
        flag = "  ★" if auc >= 0.85 else ("  ◉" if auc >= 0.75 else "")
        print(f"  {c:<35} {auc:>6.3f}  {thr:>12.4f}  {tpr:>5.2f}  {fpr:>5.2f}  {direction}{flag}")

    # ── Validate by skipping Mode 1 segments using best formula ──
    print(f"\n[9] Validation: skip every segment where best formula fires")
    best_formula = combos[0] if combos else best
    if combos:
        # Compute the best formula expression as a numeric series
        f1, op_name, f2 = best_formula[0].split(" ")
        x1 = seg[f1].astype(float).values
        x2 = seg[f2].astype(float).values
        op = {"*": lambda a,b: a*b, "+": lambda a,b: a+b,
              "-": lambda a,b: a-b, "/": lambda a,b: a/(b+1e-9)}[op_name]
        score = op(x1, x2)
    else:
        score = seg[best[0]].astype(float).values
    thr = best_formula[2]
    flip = best_formula[5] == "x ≤ thr"
    pred_mode1 = (score <= thr) if flip else (score >= thr)
    n_pred = int(pred_mode1.sum())
    actual_blocked_mode1 = int(((y == 1) & pred_mode1).sum())
    actual_blocked_winner = int(((y == 0) & pred_mode1).sum() &
                                (seg["seg_return"] > 0).sum())
    blocked_winners_returns = float(seg.loc[pred_mode1 & (seg["seg_return"]>0), "seg_return"].sum())
    blocked_losers_returns  = float(seg.loc[pred_mode1 & (seg["seg_return"]<0), "seg_return"].sum())
    print(f"  Predicted Mode 1 segments:        {n_pred} of {len(seg)}")
    print(f"    True positives  (real Mode 1):   {actual_blocked_mode1}")
    print(f"    False positives (winners):       {int(((y==0) & pred_mode1).sum())}")
    print(f"    Σ-return blocked from winners:   {blocked_winners_returns:+.4f}")
    print(f"    Σ-return blocked from losers:    {blocked_losers_returns:+.4f}")
    print(f"    Net Σ-return saved (if blocked): {-blocked_losers_returns - blocked_winners_returns:+.4f}")

    # Apply filter: simulate again with start-bar gate
    print("\n[10] Re-simulating with formula-based segment skip...")
    skip_mask = np.zeros(len(unit), dtype=bool)
    seg_to_skip = seg[pred_mode1]
    for _, r in seg_to_skip.iterrows():
        st = pd.Timestamp(r["start"])
        en = pd.Timestamp(r["end"])
        skip_mask |= (unit.index >= st) & (unit.index <= en)

    # Modified sim: zero out unit returns during skip windows
    unit_filtered = unit.copy()
    unit_filtered[skip_mask] = 0.0
    sim_filtered = simulate_v34_trace(unit_filtered, K_NORMAL, CB_HALT, CB_RESUME, CB_WINDOW_D)
    eq_f = sim_filtered["eq"][sim_filtered["eq"].index >= test_ts]
    m_f  = equity_metrics(eq_f, "v49_filtered")
    print(f"  Filtered:    Final=${m_f['final']:,.0f}  MaxDD={m_f['maxdd']:.2%}  "
          f"Calmar={m_f['calmar']:.2f}  Sharpe={m_f['sharpe']:.2f}")
    eq_b = sim["eq"][sim["eq"].index >= test_ts]
    m_b  = equity_metrics(eq_b, "v49_baseline")
    print(f"  Baseline:    Final=${m_b['final']:,.0f}  MaxDD={m_b['maxdd']:.2%}  "
          f"Calmar={m_b['calmar']:.2f}  Sharpe={m_b['sharpe']:.2f}")
    print(f"  Δ:           Final={m_f['final']-m_b['final']:+,.0f}  "
          f"ΔMaxDD={(m_f['maxdd']-m_b['maxdd'])*100:+.2f}pp  "
          f"ΔCalmar={m_f['calmar']-m_b['calmar']:+.2f}")

    # Plot
    fig, ax = plt.subplots(figsize=(15, 6))
    ax.semilogy(eq_b.index, eq_b.values, lw=1.5, color="red", label=f"Baseline ${m_b['final']:,.0f} MDD={m_b['maxdd']:.1%}")
    ax.semilogy(eq_f.index, eq_f.values, lw=1.5, color="blue", label=f"Filtered ${m_f['final']:,.0f} MDD={m_f['maxdd']:.1%}")
    # Highlight Mode 1 segments
    for _, r in seg[seg["mode1"]==1].iterrows():
        ax.axvspan(r["start"], r["end"], alpha=0.15, color="orange")
    ax.set_title(f"v49 — Mode 1 filter using {best_formula[0]} {best_formula[5].replace('thr', f'{thr:.4f}')}",
                 fontweight="bold")
    ax.set_ylabel("Equity ($)")
    ax.legend(); ax.grid(True, alpha=0.25)
    out = PLOT_DIR / "v49_mode1_filter.png"
    fig.tight_layout(); fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  → plot: {out}")

    # Save JSON
    print(f"\n[11] Saving results JSON ...")
    out_json = OUT_DIR_ / "v49_mode1_search.json"
    with open(out_json, "w") as f:
        json.dump({
            "version": "v49",
            "mode1_definition": dict(peak_thresh=MODE1_PEAK_THRESH, final_thresh=MODE1_FINAL_THRESH),
            "n_segments": len(seg),
            "n_mode1": int(seg["mode1"].sum()),
            "univariate_top10": [{"feat":r[0],"auc":r[1],"thresh":r[2],
                                   "tpr":r[3],"fpr":r[4],"rule":r[5]} for r in rows[:10]],
            "combo_top10": [{"combo":c[0],"auc":c[1],"thresh":c[2],
                             "tpr":c[3],"fpr":c[4],"rule":c[5]} for c in combos[:10]],
            "best_formula": dict(combo=best_formula[0], thresh=best_formula[2],
                                 rule=best_formula[5], auc=best_formula[1]),
            "filtered_metrics": dict(final=m_f["final"], maxdd=m_f["maxdd"],
                                     calmar=m_f["calmar"], sharpe=m_f["sharpe"]),
            "baseline_metrics": dict(final=m_b["final"], maxdd=m_b["maxdd"],
                                     calmar=m_b["calmar"], sharpe=m_b["sharpe"]),
        }, f, indent=2)
    print(f"  → {out_json}")
    print(f"\n{BAR}")
    print(f"  v49 COMPLETE  |  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
