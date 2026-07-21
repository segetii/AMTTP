"""
_diag_v32_2026.py
-----------------
Diagnostic: why does the v32 best config (d=0.3, s=0, cb_original) stop
trading in 2026?

Investigates:
  1. CB state timeline — when does it trigger / recover around Dec 2025?
  2. Energy signal E_t = b^T G b vs theta threshold — is the engine producing
     signals above theta in 2026?
  3. rho_eff (geometry friction) — is it clamping positions to zero?
  4. unit_normal raw output — are there any non-zero bars in 2026?
  5. psi_y / soft friction — microstructure gate open/closed?
  6. log_ann (annealability / position) timeline 2025-2026
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULT_DIR = Path(r"C:\amttp\research\adaptive-friction\pipeline\results")
OUT_DIR    = Path(r"C:\amttp\research\adaptive-friction\pipeline\results\v33_cb_fix\diag_2026")
OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(RESULT_DIR))

import run_crypto_godmode_v27_all_microstructure as v27
import run_crypto_godmode_v28_canonical_stability as v28
import run_crypto_godmode_v30_fractional_ricci as v30
from run_crypto_pairs_v34_full_combined import OUT_DIR as BASE_OUT, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import KAPPA_A, W_TARGET_A1, build_b_aligned, build_w_star, run_godmode_sweep
from run_crypto_canonical_v4 import A_FACTORS, build_factor_returns, rescale_to_correlation
from run_crypto_godmode_v8_multiasset_shell import ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import (
    DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, INIT, equity_metrics, simulate_combined,
)

# Best v32 config
D_BEST  = 0.30
Q_BEST  = 0.50
FFD_THRESHOLD = 1e-5
KAPPA_CAP = 20.0
CB_HALT       = v28.CB_HALT        # 0.08
CB_RESUME     = v28.CB_RESUME      # 0.01
CB_WINDOW     = v28.CB_WINDOW_DAYS # 180
K_NORMAL      = 6.5
RT_BPS        = 6.0

REG_VARIANT = dict(name="soft_all_micro", tbr_long_min=0.47, tbr_short_max=0.53,
                   soft=True, rho=False, w_funding=0.25, w_oi=0.18,
                   w_lsr=0.16, w_taker=0.16)

FOCUS_START = "2025-06-01"
FOCUS_END   = "2026-05-14"


# ── FFD helpers (same as v32) ─────────────────────────────────────────────

def ffd_weights(d: float, threshold=FFD_THRESHOLD, max_lag=4096):
    w = [1.0]
    for k in range(1, max_lag):
        wk = -w[-1] * (d - k + 1) / k
        if abs(wk) < threshold:
            break
        w.append(wk)
    return np.array(w)


def frac_diff_series(x, w):
    n, L = len(x), len(w)
    out = np.full(n, np.nan)
    if n < L:
        return out
    for t in range(L - 1, n):
        out[t] = float(np.dot(w, x[t - L + 1: t + 1][::-1]))
    return out


def ffd_covariance(factor_R, train_mask, d, df):
    R = np.nan_to_num(factor_R, nan=0.0)
    P = np.cumsum(R, axis=0)
    w = ffd_weights(d)
    L = len(w)
    F = np.full_like(P, np.nan, dtype=float)
    for j in range(P.shape[1]):
        F[:, j] = frac_diff_series(P[:, j], w)
    valid = train_mask & np.all(np.isfinite(F), axis=1)
    X = F[valid]
    mu = X.mean(axis=0)
    Xc = X - mu
    cov = (Xc.T @ Xc) / max(len(Xc) - 1, 1)
    return rescale_to_correlation(cov), dict(warm_lags=int(L - 1), n_train=int(len(Xc)))


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print("=" * 80)
    print("  DIAGNOSTICS: v32 best config (d=0.30, q=0.50, cb_original) 2025-2026")
    print("=" * 80)

    # ── 1. Build data ────────────────────────────────────────────────────
    print("\n[1] Building inputs ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        v27._get_ms(sym)

    df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask  = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask   = np.asarray(df.index >= TEST_START)
    test_ts     = pd.Timestamp(TEST_START)
    factor_R    = build_factor_returns(df)
    w_star      = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned   = build_b_aligned(w_star)
    ohlc_map    = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch          = get_channel_series()
    v27.RT_COST = RT_BPS / 10_000.0

    # ── 2. Build Sigma ───────────────────────────────────────────────────
    print("\n[2] Building Sigma (d=0.30) ...")
    Sigma_ffd, ffd_diag = ffd_covariance(factor_R, train_mask, D_BEST, df)
    Sigma_cap, cond_diag = v30.cap_condition(Sigma_ffd, KAPPA_CAP)
    G = np.linalg.inv(Sigma_cap)
    print(f"  cond_before={cond_diag['cond_before']:.3e}  cond_after={cond_diag['cond_after']:.3f}")

    # ── 3. Compute energy over full timeline ─────────────────────────────
    print("\n[3] Computing Fisher energy E_t = b_t^T G b_t over full timeline ...")
    rho_cap = float(np.linalg.norm(Sigma_ffd - Sigma_cap)) / max(float(np.linalg.norm(Sigma_cap)), 1e-12)
    budget  = float(np.sqrt(1.0 + rho_cap ** 2))

    E_all = np.einsum("ti,ij,tj->t", b_aligned, G, b_aligned)
    E_train = E_all[train_mask]
    theta_q  = max(float(np.quantile(E_train, Q_BEST)), 1e-6)
    theta    = theta_q * budget
    print(f"  theta = {theta:.6f}  (quantile({Q_BEST}) of train energy * budget {budget:.4f})")
    print(f"  Train energy: min={E_train.min():.4f}  median={np.median(E_train):.4f}  "
          f"max={E_train.max():.4f}  q50={theta_q:.4f}")

    # Energy time series as DataFrame
    E_df = pd.Series(E_all, index=df.index, name="energy")
    active = (E_df > theta).astype(int)
    print(f"\n  Energy > theta globally: {active.mean():.2%} of all hours")

    focus_sl = slice(FOCUS_START, FOCUS_END)
    E_focus = E_df[focus_sl]
    act_focus = active[focus_sl]
    print(f"  Energy > theta in {FOCUS_START}-{FOCUS_END}: {act_focus.mean():.2%} of hours  "
          f"({act_focus.sum()} bars of {len(act_focus)})")

    # Monthly breakdown
    print("\n  Monthly energy-above-theta fraction (Jun 2025 – May 2026):")
    for mo in pd.date_range("2025-06", "2026-06", freq="MS"):
        sl = (df.index >= mo) & (df.index < mo + pd.DateOffset(months=1))
        n = sl.sum()
        if n == 0:
            continue
        frac = active[sl].mean()
        emean = E_df[sl].mean()
        print(f"    {mo.strftime('%Y-%m')}: {frac:.2%} above-theta  mean_E={emean:.4f}  n={n}")

    # ── 4. Run godmode → log_ann ─────────────────────────────────────────
    print("\n[4] Running godmode sweep to get log_ann (rho_eff, w_btc, etc.) ...")
    log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned,
                                Sigma_cap, theta, kappa=KAPPA_A, anneal=True,
                                label="diag_d0p30_q0p50")
    print(f"  log_ann columns: {list(log_ann.columns)}")

    log_focus = log_ann[focus_sl]
    print(f"\n  log_ann focus ({FOCUS_START}–{FOCUS_END}): {len(log_focus)} rows")
    for col in ["rho_eff", "in_signal", "w_btc", "w_eth", "w_sol", "energy_norm"]:
        if col in log_focus.columns:
            s = log_focus[col].dropna()
            print(f"    {col:<16}: mean={s.mean():.4f}  min={s.min():.4f}  max={s.max():.4f}  "
                  f"nonzero={( s != 0).sum()}")

    # Monthly rho_eff and in_signal breakdown
    print("\n  Monthly rho_eff / in_signal (Jun 2025 – May 2026):")
    for mo in pd.date_range("2025-06", "2026-06", freq="MS"):
        sl2 = (log_ann.index >= mo) & (log_ann.index < mo + pd.DateOffset(months=1))
        n = sl2.sum()
        if n == 0:
            continue
        rho_m  = log_ann["rho_eff"][sl2].mean() if "rho_eff" in log_ann.columns else float("nan")
        sig_m  = log_ann["in_signal"][sl2].mean() if "in_signal" in log_ann.columns else float("nan")
        print(f"    {mo.strftime('%Y-%m')}: rho_eff={rho_m:.4f}  in_signal={sig_m:.4f}  n={n}")

    # ── 5. Build unit signal ─────────────────────────────────────────────
    print("\n[5] Building unit signal (v28 variant) ...")
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                    signal_kind="wstar", use_quadrant=False)
    inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                    signal_kind="wstar", use_quadrant=True)
    inputs     = attach_q_hot(inputs_noq, inputs_q)
    sig_map    = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                  for asset, _, _, idx in ASSETS}
    result     = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)
    unit       = result["unit"]

    unit_focus = unit[focus_sl]
    print(f"  unit focus bars: {len(unit_focus)}")
    print(f"  unit nonzero bars in focus: {(unit_focus != 0).sum()}")
    print(f"  unit mean (nonzero): {unit_focus[unit_focus != 0].mean():.6f}"
          if (unit_focus != 0).any() else "  unit mean (nonzero): N/A (all zero)")

    # Monthly unit activity breakdown
    print("\n  Monthly unit activity (Jun 2025 – May 2026):")
    for mo in pd.date_range("2025-06", "2026-06", freq="MS"):
        sl3 = (unit.index >= mo) & (unit.index < mo + pd.DateOffset(months=1))
        n  = sl3.sum()
        if n == 0:
            continue
        u   = unit[sl3]
        nz  = (u != 0).sum()
        cum = float(u.sum())
        print(f"    {mo.strftime('%Y-%m')}: n={n}  nonzero={nz}  cum_return={cum:+.6f}")

    # Per-asset unit decomposition
    print("\n  Per-asset unit nonzero bars in focus:")
    for asset, info in result["per_asset"].items():
        # recompute from raw
        pass
    print("  (see log_ann for full per-asset breakdown)")

    # ── 6. Run simulation with CB state tracking ─────────────────────────
    print("\n[6] Running simulation — tracking CB state ...")
    sim = simulate_combined(
        unit_normal=unit, unit_crash=pd.Series(0.0, index=unit.index),
        K_normal=K_NORMAL, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window_days=CB_WINDOW,
        use_cb=True,
    )
    eq = sim["eq"]

    # Manually re-run to capture CB state per bar
    from collections import deque
    HOURS_PER_DAY = 24
    window_bars = CB_WINDOW * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq_v = INIT; peak_alltime = INIT; halted = False
    eq_vals, cb_flags, roll_dd_vals, roll_peak_vals, y_vals = [], [], [], [], []
    for bar_i in range(len(unit)):
        ur_n = float(unit.iloc[bar_i])
        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq_v:
            mono_dq.pop()
        mono_dq.append((bar_i, eq_v))
        roll_peak = mono_dq[0][1]
        dd_aty = max(0.0, 1.0 - eq_v / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq_v / max(roll_peak, 1e-12))
        if not halted and cb_dd >= CB_HALT:
            halted = True
        elif halted and cb_dd <= CB_RESUME:
            halted = False
        if halted:
            y = 0.0
        elif dd_aty <= DYN_DD_SOFT:
            y = 1.0
        elif dd_aty >= DYN_DD_STOP:
            y = DYN_Y_FLOOR
        else:
            y = DYN_Y_FLOOR + (1.0 - DYN_Y_FLOOR) * (DYN_DD_STOP - dd_aty) / (DYN_DD_STOP - DYN_DD_SOFT)
        r = K_NORMAL * y * ur_n
        r = max(r, -0.95)
        eq_v *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq_v)
        eq_vals.append(eq_v)
        cb_flags.append(int(halted))
        roll_dd_vals.append(cb_dd)
        roll_peak_vals.append(roll_peak)
        y_vals.append(y)

    cb_s      = pd.Series(cb_flags,      index=unit.index, name="cb_halted")
    roll_dd_s = pd.Series(roll_dd_vals,  index=unit.index, name="roll_dd")
    roll_pk_s = pd.Series(roll_peak_vals,index=unit.index, name="roll_peak")
    eq_s      = pd.Series(eq_vals,       index=unit.index, name="equity")
    y_s       = pd.Series(y_vals,        index=unit.index, name="y_scale")

    print(f"\n  CB triggered at (first 5 state=1 starts):")
    transitions = cb_s.diff().fillna(cb_s)
    trigger_times = transitions[transitions == 1].index
    resume_times  = transitions[transitions == -1].index
    for ts in trigger_times[:10]:
        eq_at = eq_s[ts]
        rp    = roll_pk_s[ts]
        dd    = roll_dd_s[ts]
        print(f"    {ts}  eq=${eq_at:,.0f}  roll_peak=${rp:,.0f}  roll_dd={dd:.4f}")

    print(f"\n  CB resumed at:")
    for ts in resume_times[:10]:
        eq_at = eq_s[ts]
        rp    = roll_pk_s[ts]
        dd    = roll_dd_s[ts]
        print(f"    {ts}  eq=${eq_at:,.0f}  roll_peak=${rp:,.0f}  roll_dd={dd:.4f}")

    print(f"\n  CB state at end of 2025: {cb_s['2025-12-31'] if '2025-12-31' in cb_s.index else 'N/A'}")
    # last day of 2025
    dec25 = cb_s["2025-12-01":"2025-12-31"]
    if len(dec25):
        print(f"  Dec 2025 halted fraction: {dec25.mean():.2%}")
        print(f"  End of Dec 2025 CB state: {int(dec25.iloc[-1])}")
    jan26 = cb_s["2026-01-01":"2026-01-31"]
    if len(jan26):
        print(f"  Jan 2026 halted fraction: {jan26.mean():.2%}")
    # Find when the CB last triggered before 2026 and what the rolling peak then was
    print("\n  Monthly CB and roll-DD (Jun 2025 – May 2026):")
    for mo in pd.date_range("2025-06", "2026-06", freq="MS"):
        sl4 = (unit.index >= mo) & (unit.index < mo + pd.DateOffset(months=1))
        n = sl4.sum()
        if n == 0:
            continue
        cb_m  = cb_s[sl4].mean()
        rdd_m = roll_dd_s[sl4].mean()
        rdd_max = roll_dd_s[sl4].max()
        eq_m  = eq_s[sl4].iloc[-1]
        rp_m  = roll_pk_s[sl4].mean()
        print(f"    {mo.strftime('%Y-%m')}: cb={cb_m:.2%}  "
              f"roll_dd_mean={rdd_m:.4f}  roll_dd_max={rdd_max:.4f}  "
              f"eq_end=${eq_m:,.0f}  roll_peak=${rp_m:,.0f}")

    # What roll_dd would need to be for CB to release?
    last_peak = roll_pk_s.iloc[-1]
    last_eq   = eq_s.iloc[-1]
    last_dd   = roll_dd_s.iloc[-1]
    print(f"\n  As of data end:")
    print(f"    equity         = ${last_eq:,.0f}")
    print(f"    rolling peak   = ${last_peak:,.0f}")
    print(f"    rolling DD     = {last_dd:.4f}")
    print(f"    CB halted?     = {bool(cb_s.iloc[-1])}")
    print(f"    To release CB  : equity must reach ${last_peak * (1 - CB_RESUME):,.0f} "
          f"(= roll_peak × {1 - CB_RESUME:.2f})")
    print(f"    Equity gap     : need +{(last_peak * (1 - CB_RESUME)) / last_eq - 1:.2%} gain")

    # ── 7. Check if 2026 has ANY energy signals above theta ──────────────
    print("\n[7] Checking energy signal in 2026 ...")
    sl26 = (df.index >= "2026-01-01")
    n26  = sl26.sum()
    if n26 > 0:
        E26   = E_df[sl26]
        act26 = active[sl26]
        print(f"  2026 bars:            {n26}")
        print(f"  Above-theta bars:     {act26.sum()} ({act26.mean():.2%})")
        print(f"  Energy range:         min={E26.min():.4f}  mean={E26.mean():.4f}  max={E26.max():.4f}")
        print(f"  Theta:                {theta:.6f}")
        print(f"  Max energy vs theta:  {E26.max() / theta:.2f}×")

    # How much energy above theta is being blocked by CB?
    unit26 = unit[sl26]
    cb26   = cb_s[sl26]
    print(f"\n  Unit in 2026:")
    print(f"    nonzero bars (raw):    {(unit26 != 0).sum()} / {len(unit26)}")
    print(f"    CB halted bars:        {cb26.sum()} / {len(cb26)}")
    print(f"    Unit nonzero × halted: {((unit26 != 0) & (cb26 == 1)).sum()}  (blocked by CB)")
    print(f"    Unit nonzero × active: {((unit26 != 0) & (cb26 == 0)).sum()}  (executed)")

    # ── 8. What-if: if CB were released on Jan 1 2026 ────────────────────
    print("\n[8] What-if: force CB off from Jan 1 2026 ...")
    unit_mod = unit.copy()
    # Same simulation but CB disabled from 2026-01-01
    eq_v2 = INIT; peak2 = INIT; halted2 = False
    eq2, cb2 = [], []
    cutover = pd.Timestamp("2026-01-01")
    for bar_i in range(len(unit)):
        ts   = unit.index[bar_i]
        ur_n = float(unit.iloc[bar_i])
        if ts >= cutover:
            halted2 = False   # force CB off
        # simplified: no rolling window tracking after cutover
        dd2 = max(0.0, 1.0 - eq_v2 / max(peak2, 1e-12))
        if dd2 <= DYN_DD_SOFT:
            y2 = 1.0
        elif dd2 >= DYN_DD_STOP:
            y2 = DYN_Y_FLOOR
        else:
            y2 = DYN_Y_FLOOR + (1.0 - DYN_Y_FLOOR) * (DYN_DD_STOP - dd2) / (DYN_DD_STOP - DYN_DD_SOFT)
        if halted2:
            y2 = 0.0
        r2 = K_NORMAL * y2 * ur_n
        r2 = max(r2, -0.95)
        eq_v2 *= (1.0 + r2)
        peak2 = max(peak2, eq_v2)
        eq2.append(eq_v2)
        cb2.append(int(halted2))

    eq_whf = pd.Series(eq2, index=unit.index)
    eq_2026_start = eq_s["2026-01-01":].iloc[0] if len(eq_s["2026-01-01":]) else eq_s.iloc[-1]
    eq_whf_2026 = eq_whf["2026-01-01":]
    print(f"  Original equity (2026 start):    ${eq_s['2026-01-01':].iloc[0]:,.0f}" if len(eq_s["2026-01-01":]) else "  (no 2026 bars)")
    print(f"  What-if equity (2026 end):        ${eq_whf_2026.iloc[-1]:,.0f}" if len(eq_whf_2026) else "  (no 2026 bars)")
    print(f"  What-if max equity in 2026:       ${eq_whf_2026.max():,.0f}" if len(eq_whf_2026) else "")
    gain_whf = (eq_whf_2026.iloc[-1] / eq_whf_2026.iloc[0] - 1) if len(eq_whf_2026) > 1 else 0
    print(f"  What-if 2026 gain (Jan–May):      {gain_whf:+.2%}")

    # ── 9. Recalibrated theta: use post-2025 window ───────────────────────
    print("\n[9] Rolling theta recalibration — what if theta used trailing 2y window?")
    window_train_bars = 2 * 365 * 24  # 2 years in hours
    # For each bar in 2026, compute theta from trailing 2y of energy
    theta_rolling = []
    idx_arr = np.array(range(len(E_df)))
    dates_2026 = [i for i, d in enumerate(df.index) if d >= pd.Timestamp("2026-01-01")]
    if dates_2026:
        for i in dates_2026[:24]:   # first 24 hrs sample
            start_ = max(0, i - window_train_bars)
            e_win  = E_all[start_:i]
            if len(e_win) >= 100:
                th_ = float(np.quantile(e_win, Q_BEST)) * budget
                theta_rolling.append((df.index[i], th_))
        if theta_rolling:
            print(f"  Theta from trailing 2y window in Jan 2026 (sample):")
            for ts, th in theta_rolling[:6]:
                print(f"    {ts}  theta={th:.6f}  vs fixed theta={theta:.6f}  ratio={th/theta:.3f}")
            print(f"  -> If theta has grown (ratio>1), the engine is undertriggered post-2025 bull run")
        else:
            print("  (not enough bars)")

    # ── 10. Plots ─────────────────────────────────────────────────────────
    print("\n[10] Saving plots ...")

    # Plot 1: equity + CB state 2024-2026
    fig, axes = plt.subplots(4, 1, figsize=(16, 14), sharex=True)
    sl_plot = slice("2024-01-01", FOCUS_END)
    ax0 = axes[0]
    ax0.semilogy(eq_s[sl_plot].index, eq_s[sl_plot].values, color="steelblue", lw=1.5, label="equity")
    ax0.set_ylabel("Equity ($)"); ax0.set_title("v32 best (d=0.30): Equity + CB state 2024–2026")
    ax0.legend(loc="upper left"); ax0.grid(True, alpha=0.25)

    ax1 = axes[1]
    ax1.fill_between(cb_s[sl_plot].index, cb_s[sl_plot].values,
                     step="post", alpha=0.6, color="tomato", label="CB halted")
    ax1.fill_between(roll_dd_s[sl_plot].index, roll_dd_s[sl_plot].values,
                     step="post", alpha=0.4, color="orange", label="rolling DD")
    ax1.axhline(CB_HALT,   color="red",   ls="--", lw=1.2, label=f"CB_HALT={CB_HALT}")
    ax1.axhline(CB_RESUME, color="green", ls="--", lw=1.2, label=f"CB_RESUME={CB_RESUME}")
    ax1.set_ylabel("CB / roll_DD"); ax1.legend(fontsize=8); ax1.grid(True, alpha=0.25)

    ax2 = axes[2]
    E_plot = E_df[sl_plot]
    ax2.plot(E_plot.index, E_plot.values, color="purple", lw=0.8, alpha=0.7, label="energy E_t")
    ax2.axhline(theta, color="red", ls="--", lw=1.3, label=f"theta={theta:.4f}")
    ax2.set_ylabel("Energy E_t"); ax2.legend(fontsize=8); ax2.grid(True, alpha=0.25)
    ax2.set_ylim(0, min(E_plot.max() * 1.2, theta * 5))

    ax3 = axes[3]
    u_plot = unit[sl_plot]
    ax3.bar(u_plot.index, u_plot.values, color="teal", alpha=0.6, label="unit_normal", width=0.04)
    ax3.axhline(0, color="black", lw=0.6)
    ax3.set_ylabel("unit return"); ax3.legend(fontsize=8); ax3.grid(True, alpha=0.25)

    out1 = OUT_DIR / "diag_equity_cb_energy_2024-2026.png"
    fig.tight_layout(); fig.savefig(out1, dpi=170); plt.close(fig)
    print(f"  saved: {out1}")

    # Plot 2: monthly energy distribution heat + theta line
    fig2, ax = plt.subplots(figsize=(14, 5))
    focus_E = E_df["2023-01-01":FOCUS_END]
    ax.plot(focus_E.index, focus_E.values, color="purple", lw=0.6, alpha=0.5, label="energy")
    ax.axhline(theta, color="red", ls="--", lw=1.5, label=f"theta={theta:.4f}")
    cb_foc = cb_s["2023-01-01":FOCUS_END]
    ax.fill_between(cb_foc.index, 0, theta * 3, where=cb_foc == 1,
                    alpha=0.15, color="red", step="post", label="CB halted")
    ax.set_title("Energy E_t vs theta (2023–2026) with CB halt shading")
    ax.set_ylabel("Energy"); ax.set_ylim(0, theta * 4); ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)
    out2 = OUT_DIR / "diag_energy_theta_2023-2026.png"
    fig2.tight_layout(); fig2.savefig(out2, dpi=170); plt.close(fig2)
    print(f"  saved: {out2}")

    # Plot 3: rolling peak vs equity vs CB_RESUME threshold
    fig3, ax = plt.subplots(figsize=(14, 5))
    sl_rp = slice("2025-01-01", FOCUS_END)
    ax.semilogy(roll_pk_s[sl_rp].index, roll_pk_s[sl_rp].values, "k--", lw=1.2, label="rolling peak")
    ax.semilogy(eq_s[sl_rp].index, eq_s[sl_rp].values, color="steelblue", lw=1.8, label="equity")
    # CB_RESUME threshold = roll_peak * (1 - CB_RESUME)
    release_level = roll_pk_s[sl_rp] * (1 - CB_RESUME)
    ax.semilogy(release_level.index, release_level.values, color="green", ls="-.", lw=1.2,
                label=f"release threshold (roll_peak×{1-CB_RESUME:.2f})")
    ax.set_title(f"v32: Equity vs rolling peak & CB release level (2025–2026)")
    ax.set_ylabel("Equity ($)"); ax.legend(fontsize=9); ax.grid(True, alpha=0.25)
    out3 = OUT_DIR / "diag_cb_release_level_2025-2026.png"
    fig3.tight_layout(); fig3.savefig(out3, dpi=170); plt.close(fig3)
    print(f"  saved: {out3}")

    print(f"\n  Elapsed: {time.time()-t0:.1f}s")
    print("=" * 80)


if __name__ == "__main__":
    main()
