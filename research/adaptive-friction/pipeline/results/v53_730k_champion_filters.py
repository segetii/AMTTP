# -*- coding: utf-8 -*-
"""
v53_730k_champion_filters.py
============================

Focus ONLY on the true $730K champion algorithm:
  d=0.50, q=0.65, cb_halt=8%, cb_resume=4%, cb_window=90d
  stored in v35 as d0p5_q0p65_w090_r04:
    Final=$730,056, MaxDD=-34.84%, Calmar=17.49

Purpose:
  Stop optimizing proxy variants. Re-test the useful controls directly on
  the champion:
    1) rhs_norm release extension filter (v51 idea)
    2) CB window variants around champion (90/105/120/150/180)

Outputs:
  v53_730k_champion/sweep_results.csv
  v53_730k_champion/v53_results.json
"""
from __future__ import annotations

import json
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

import run_crypto_godmode_v27_all_microstructure as v27
import run_crypto_godmode_v28_canonical_stability as v28
from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import W_TARGET_A1, build_b_aligned, build_w_star
from run_crypto_canonical_v4 import build_factor_returns
from run_crypto_godmode_v8_multiasset_shell import ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, INIT, HOURS_PER_DAY, equity_metrics
from run_crypto_godmode_v35_top5_cb_transition import REG_VARIANT, K_NORMAL, RT_BPS, build_sigma, theta_from
from v49_mode1_feature_search import run_ode

BAR = "=" * 110
OUT = Path(OUT_DIR) / "v53_730k_champion"

# TRUE champion from v35_top5_cb_transition
D = 0.50
Q = 0.65
CB_HALT = 0.08
CB_RESUME = 0.04

CB_WINDOWS = [90, 105, 120, 150, 180]
RHS_THRESHOLDS = [0.0, 0.50, 0.55, 0.60, 0.65, 0.70]
EXTEND_BARS_LIST = [240, 480, 720, 1440]  # 10d,20d,30d,60d


def simulate_with_rhs_filter(unit_series, ode_log, K_normal,
                             cb_halt, cb_resume, cb_window_d,
                             rhs_thresh=0.0, extend_bars=0):
    window_bars = cb_window_d * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq, peak_alltime = INIT, INIT
    halted = False
    extend_counter = 0
    release_events = []

    unit = unit_series.values
    rhs = ode_log["rhs_norm"].reindex(unit_series.index, method="ffill").fillna(0.0).values

    eq_vals, y_vals, halted_vals = [], [], []
    for i in range(len(unit)):
        ur_n = float(unit[i])
        while mono_dq and mono_dq[0][0] <= i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((i, eq))
        roll_peak = mono_dq[0][1]
        cb_dd = max(0.0, 1.0 - eq / max(roll_peak, 1e-12))
        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))

        if extend_counter > 0:
            extend_counter -= 1
            if extend_counter == 0:
                halted = False
        elif not halted:
            if cb_dd >= cb_halt:
                halted = True
        else:
            if cb_dd <= cb_resume:
                rhs_now = float(rhs[i])
                if rhs_thresh > 0 and rhs_now > rhs_thresh:
                    extend_counter = extend_bars
                    release_events.append(dict(bar=i, ts=unit_series.index[i], rhs_norm=rhs_now, blocked=True))
                else:
                    halted = False
                    if rhs_thresh > 0:
                        release_events.append(dict(bar=i, ts=unit_series.index[i], rhs_norm=rhs_now, blocked=False))

        is_halted = halted or (extend_counter > 0)
        if is_halted:
            y = 0.0
        elif dd_aty <= DYN_DD_SOFT:
            y = 1.0
        elif dd_aty >= DYN_DD_STOP:
            y = DYN_Y_FLOOR
        else:
            y = DYN_Y_FLOOR + (1.0 - DYN_Y_FLOOR) * (DYN_DD_STOP - dd_aty) / (DYN_DD_STOP - DYN_DD_SOFT)

        r = max(K_normal * y * ur_n, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq)
        y_vals.append(y)
        halted_vals.append(int(is_halted))

    return dict(
        eq=pd.Series(eq_vals, index=unit_series.index),
        y=pd.Series(y_vals, index=unit_series.index),
        cb=pd.Series(halted_vals, index=unit_series.index),
        release_events=release_events,
        n_blocked=sum(1 for e in release_events if e["blocked"]),
    )


def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)

    print(BAR)
    print("  v53 — TRUE $730K CHAMPION ONLY")
    print(f"  Champion: d={D:.2f}, q={Q:.2f}, halt={CB_HALT:.0%}, resume={CB_RESUME:.0%}, window=90d")
    print("  Sweep: CB windows × rhs_norm release filters")
    print(BAR)

    print("\n[0] Microstructure + inputs ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        v27._get_ms(sym)

    df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_ts = pd.Timestamp(TEST_START)
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    factor_R = build_factor_returns(df)
    v27.RT_COST = RT_BPS / 10_000.0

    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()

    print("\n[1] Building exact champion ODE/unit returns ...")
    Sigma_base, _, _, bdiag = build_sigma(factor_R, train_mask, df, D)
    theta = theta_from(b_aligned, train_mask, Sigma_base, bdiag["budget"], Q)
    log_ann, _ = run_ode(df, train_mask, w_star, b_aligned, Sigma_base, theta)
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                     signal_kind="wstar", use_quadrant=False)
    inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                   signal_kind="wstar", use_quadrant=True)
    inputs = attach_q_hot(inputs_noq, inputs_q)
    sig_map = {a: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{a}")
               for a, _, _, idx in ASSETS}
    unit = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]

    print("\n[2] Sweep ...")
    print(f"\n  {'window':>6} {'thr':>5} {'ext_d':>6} {'n_blk':>6} {'final':>12} {'maxdd':>8} {'calmar':>7} {'sharpe':>7}")
    print("  " + "-" * 74)

    rows = []
    for w in CB_WINDOWS:
        # baseline per window
        sim = simulate_with_rhs_filter(unit, log_ann, K_NORMAL, CB_HALT, CB_RESUME, w, 0.0, 0)
        eq_test = sim["eq"][sim["eq"].index >= test_ts]
        m = equity_metrics(eq_test, f"champ_w{w}_base")
        row = dict(d=D, q=Q, window_d=w, rhs_thresh=0.0, extend_bars=0, extend_days=0,
                   n_blocked=0, final=m["final"], maxdd=m["maxdd"], calmar=m["calmar"], sharpe=m["sharpe"])
        rows.append(row)
        star = "  <-- TRUE 730K" if w == 90 else ""
        print(f"  {w:>5}d {'base':>5} {'---':>6} {'---':>6} ${m['final']:>10,.0f} {m['maxdd']:>8.2%} {m['calmar']:>7.2f} {m['sharpe']:>7.2f}{star}")

        for thr in RHS_THRESHOLDS[1:]:
            for ext in EXTEND_BARS_LIST:
                sim = simulate_with_rhs_filter(unit, log_ann, K_NORMAL, CB_HALT, CB_RESUME, w, thr, ext)
                eq_test = sim["eq"][sim["eq"].index >= test_ts]
                m = equity_metrics(eq_test, f"champ_w{w}_t{thr}_e{ext}")
                n_blk = sim["n_blocked"]
                row = dict(d=D, q=Q, window_d=w, rhs_thresh=thr, extend_bars=ext,
                           extend_days=ext // HOURS_PER_DAY, n_blocked=n_blk,
                           final=m["final"], maxdd=m["maxdd"], calmar=m["calmar"], sharpe=m["sharpe"])
                rows.append(row)
                mark = ""
                if m["final"] > 500_000 and m["maxdd"] > -0.30:
                    mark = "  ★ high-ret lower-DD"
                elif m["maxdd"] > -0.20 and m["final"] > 100_000:
                    mark = "  ★ low-DD"
                print(f"  {w:>5}d {thr:>5.2f} {ext//HOURS_PER_DAY:>5}d {n_blk:>6} ${m['final']:>10,.0f} {m['maxdd']:>8.2%} {m['calmar']:>7.2f} {m['sharpe']:>7.2f}{mark}")
        print()

    res = pd.DataFrame(rows)
    res.to_csv(OUT / "sweep_results.csv", index=False)
    best_cal = res.loc[res["calmar"].idxmax()]
    best_ret = res.loc[res["final"].idxmax()]
    best_mdd = res.loc[res["maxdd"].idxmax()]

    print("\n[3] Best configs:")
    for label, r in [("Best final", best_ret), ("Best Calmar", best_cal), ("Best MDD", best_mdd)]:
        print(f"  {label:<12}: w={int(r.window_d)}d thr={r.rhs_thresh:.2f} ext={int(r.extend_days)}d "
              f"blk={int(r.n_blocked)}  Final=${r.final:,.0f}  MDD={r.maxdd:.2%}  Cal={r.calmar:.2f}")

    json.dump({"version":"v53", "champion":{"d":D,"q":Q,"cb_halt":CB_HALT,"cb_resume":CB_RESUME},
               "results":res.to_dict(orient="records")},
              open(OUT / "v53_results.json", "w"), indent=2, default=str)

    print(f"\n  → saved: {OUT / 'sweep_results.csv'}")
    print(f"  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
