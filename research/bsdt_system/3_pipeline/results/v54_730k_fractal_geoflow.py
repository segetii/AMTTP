# -*- coding: utf-8 -*-
"""
v54_730k_fractal_geoflow.py
===========================

Focus: improve the TRUE $730K champion algorithm, not proxies.

Locked target baseline:
  d=0.50, q=0.65, CB halt=8%, resume=4%, window=90d
  v35 name: d0p5_q0p65_w090_r04
  baseline: Final=$730,056, MaxDD=-34.84%, Calmar=17.46
  v53 best: Final=$949,196, MaxDD=-29.45%, Calmar=22.61

v54 adds two framework ideas:
  1) Fractal / fractional memory covariance
     - use power-law long-memory covariance alpha from v30
  2) Geometric flow / Ricci-style SPD shrink
     - log-Euclidean shrink covariance eigenvalues toward identity

Then adds soft position sizing instead of hard-only release blocking:
  K_eff = K / (1 + a * rhs_norm)
  K_eff = K / (1 + a * gamma * rhs_norm)

Goal:
  Preserve high-return 90d champion path while reducing MaxDD below v53's -29.45%,
  ideally toward -25% without dropping below $700K.
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
from run_crypto_godmode_v30_fractional_ricci import build_fractional_ricci_sigma
from v49_mode1_feature_search import run_ode

BAR = "=" * 112
OUT = Path(OUT_DIR) / "v54_730k_fractal_geoflow"

# True champion baseline
D_CHAMP = 0.50
Q_CHAMP = 0.65
CB_HALT = 0.08
CB_RESUME = 0.04
CB_WINDOW_D = 90

# Fractal / fractional memory + geometric-flow grid
ALPHA_GRID = [0.60, 0.80, 1.00, 1.20]
RICCI_ETA_GRID = [0.00, 0.05, 0.10, 0.20]

# Soft sizing grid.  "none" reproduces geometry baseline.
SIZE_CONFIGS = [
    ("none", 0.0),
    ("rhs",  0.25), ("rhs", 0.50), ("rhs", 1.00), ("rhs", 2.00), ("rhs", 4.00),
    ("omega",0.50), ("omega",1.00), ("omega",2.00), ("omega",4.00), ("omega",8.00),
]

# Also test v53's best hard release filter as an overlay.
RELEASE_FILTERS = [
    (0.0, 0),       # no hard release filter
    (0.55, 720),    # v53 best: rhs>=0.55, extend=30d
]


def simulate_soft(unit_series, ode_log, K_normal, cb_halt, cb_resume, cb_window_d,
                  size_mode="none", size_a=0.0,
                  release_thr=0.0, release_ext=0):
    window_bars = cb_window_d * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq, peak_alltime = INIT, INIT
    halted = False
    extend_counter = 0
    release_events = []

    unit = unit_series.values
    ode = ode_log.reindex(unit_series.index, method="ffill").fillna(0.0)
    rhs = ode["rhs_norm"].values
    gamma = ode["gamma"].values

    eq_vals, y_vals, k_mult_vals, halted_vals = [], [], [], []

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

        # v53 timer-based release filter, optional
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
                if release_thr > 0.0 and rhs_now > release_thr:
                    extend_counter = release_ext
                    release_events.append(dict(bar=i, ts=unit_series.index[i], rhs_norm=rhs_now, blocked=True))
                else:
                    halted = False
                    if release_thr > 0.0:
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

        # Soft fractal/geometric-flow risk sizing overlay
        if size_mode == "rhs":
            k_mult = 1.0 / (1.0 + size_a * max(float(rhs[i]), 0.0))
        elif size_mode == "omega":
            k_mult = 1.0 / (1.0 + size_a * max(float(gamma[i] * rhs[i]), 0.0))
        else:
            k_mult = 1.0

        r = max(K_normal * y * k_mult * ur_n, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq)
        y_vals.append(y)
        k_mult_vals.append(k_mult)
        halted_vals.append(int(is_halted))

    return dict(
        eq=pd.Series(eq_vals, index=unit_series.index),
        y=pd.Series(y_vals, index=unit_series.index),
        k_mult=pd.Series(k_mult_vals, index=unit_series.index),
        cb=pd.Series(halted_vals, index=unit_series.index),
        n_blocked=sum(1 for e in release_events if e["blocked"]),
        release_events=release_events,
    )


def build_unit_for_sigma(df, train_mask, w_star, b_aligned, Sigma, theta, ch, ohlc_map):
    log_ann, _ = run_ode(df, train_mask, w_star, b_aligned, Sigma, theta)
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                     signal_kind="wstar", use_quadrant=False)
    inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                   signal_kind="wstar", use_quadrant=True)
    inputs = attach_q_hot(inputs_noq, inputs_q)
    sig_map = {a: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{a}")
               for a, _, _, idx in ASSETS}
    unit = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]
    return log_ann, unit


def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)

    print(BAR)
    print("  v54 — TRUE $730K CHAMPION + FRACTAL/FRACTIONAL + GEOMETRIC FLOW")
    print(f"  Locked champion target: d={D_CHAMP}, q={Q_CHAMP}, CB={CB_WINDOW_D}d/{CB_RESUME:.0%}")
    print(f"  Alpha grid: {ALPHA_GRID}")
    print(f"  Ricci eta grid: {RICCI_ETA_GRID}")
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

    geometry_specs = []

    # Exact champion geometry, for anchor and direct comparison.
    Sigma_champ, _, sdiag_champ, bdiag_champ = build_sigma(factor_R, train_mask, df, D_CHAMP)
    theta_champ = theta_from(b_aligned, train_mask, Sigma_champ, bdiag_champ["budget"], Q_CHAMP)
    geometry_specs.append(dict(kind="champ_ffd", label="champ_d0.50", Sigma=Sigma_champ,
                               theta=theta_champ, alpha=np.nan, ricci_eta=0.0,
                               diag={**sdiag_champ, **bdiag_champ}))

    # Fractal/fractional + geometric-flow geometries.
    for alpha in ALPHA_GRID:
        for eta in RICCI_ETA_GRID:
            Sigma, diag = build_fractional_ricci_sigma(factor_R, train_mask, alpha, eta)
            theta = theta_from(b_aligned, train_mask, Sigma, 1.0, Q_CHAMP)
            geometry_specs.append(dict(kind="fractal_geoflow", label=f"alpha{alpha:.2f}_ricci{eta:.2f}",
                                       Sigma=Sigma, theta=theta, alpha=alpha, ricci_eta=eta, diag=diag))

    rows = []
    print("\n[1] Running geometries and soft sizing sweeps ...")
    print(f"\n  {'geometry':<20} {'mode':<6} {'a':>5} {'rel':>9} {'blk':>4} {'final':>11} {'maxdd':>8} {'calmar':>7} {'sharpe':>7}")
    print("  " + "-" * 93)

    for gidx, spec in enumerate(geometry_specs, start=1):
        print(f"\n  [geometry {gidx}/{len(geometry_specs)}] {spec['label']}  theta={spec['theta']:.4f}")
        log_ann, unit = build_unit_for_sigma(df, train_mask, w_star, b_aligned,
                                             spec["Sigma"], spec["theta"], ch, ohlc_map)
        for mode, a in SIZE_CONFIGS:
            for rel_thr, rel_ext in RELEASE_FILTERS:
                # Avoid duplicate hard-filter baseline for none? keep all for audit.
                sim = simulate_soft(unit, log_ann, K_NORMAL, CB_HALT, CB_RESUME, CB_WINDOW_D,
                                    size_mode=mode, size_a=a,
                                    release_thr=rel_thr, release_ext=rel_ext)
                eq_test = sim["eq"][sim["eq"].index >= test_ts]
                m = equity_metrics(eq_test, f"{spec['label']}_{mode}{a}_rel{rel_thr}")
                row = dict(
                    geometry=spec["label"], kind=spec["kind"], alpha=spec["alpha"], ricci_eta=spec["ricci_eta"],
                    theta=spec["theta"], size_mode=mode, size_a=a,
                    release_thr=rel_thr, release_ext_bars=rel_ext, release_ext_days=rel_ext // HOURS_PER_DAY,
                    n_blocked=sim["n_blocked"], final=m["final"], profit=m["final"] - INIT,
                    maxdd=m["maxdd"], calmar=m["calmar"], sharpe=m["sharpe"],
                    mean_k_mult=float(sim["k_mult"].mean()), p05_k_mult=float(sim["k_mult"].quantile(0.05)),
                )
                rows.append(row)
                mark = ""
                if m["final"] > 700_000 and m["maxdd"] > -0.25:
                    mark = "  ★ TARGET"
                elif m["final"] > 700_000 and m["maxdd"] > -0.2946:
                    mark = "  ◉ beats v53 DD"
                elif m["final"] > 900_000:
                    mark = "  high-final"
                rel = "none" if rel_thr <= 0 else f"r{rel_thr:.2f}/{rel_ext//HOURS_PER_DAY}d"
                print(f"  {spec['label']:<20} {mode:<6} {a:>5.2f} {rel:>9} {sim['n_blocked']:>4} "
                      f"${m['final']:>10,.0f} {m['maxdd']:>8.2%} {m['calmar']:>7.2f} {m['sharpe']:>7.2f}{mark}")

    res = pd.DataFrame(rows)
    res.to_csv(OUT / "sweep_results.csv", index=False)

    # Summaries
    candidates = res.copy()
    best_final = candidates.loc[candidates["final"].idxmax()]
    best_calmar = candidates.loc[candidates["calmar"].idxmax()]
    best_dd = candidates.loc[candidates["maxdd"].idxmax()]
    feasible = candidates[(candidates["final"] > 700_000) & (candidates["maxdd"] > -0.30)]

    print("\n[2] Summary")
    for title, r in [("Best final", best_final), ("Best Calmar", best_calmar), ("Best MaxDD", best_dd)]:
        print(f"  {title:<12}: {r.geometry} mode={r.size_mode} a={r.size_a:.2f} "
              f"rel={r.release_thr:.2f}/{int(r.release_ext_days)}d  "
              f"Final=${r.final:,.0f} Profit=${r.profit:,.0f} MaxDD={r.maxdd:.2%} Cal={r.calmar:.2f}")

    if len(feasible):
        print("\n  Feasible high-return / improved-DD candidates:")
        show = feasible.sort_values(["maxdd", "final"], ascending=[False, False]).head(15)
        for _, r in show.iterrows():
            print(f"    {r.geometry:<20} {r.size_mode:<6} a={r.size_a:<4.2f} "
                  f"rel={r.release_thr:.2f}/{int(r.release_ext_days)}d  "
                  f"Final=${r.final:,.0f} MaxDD={r.maxdd:.2%} Cal={r.calmar:.2f}")
    else:
        print("\n  No candidate passed Final>$700K and MaxDD>-30%.")

    json.dump({
        "version": "v54",
        "focus": "true_730k_champion_fractal_geoflow",
        "baseline": {"d": D_CHAMP, "q": Q_CHAMP, "cb_halt": CB_HALT, "cb_resume": CB_RESUME, "cb_window_d": CB_WINDOW_D},
        "alpha_grid": ALPHA_GRID,
        "ricci_eta_grid": RICCI_ETA_GRID,
        "size_configs": SIZE_CONFIGS,
        "release_filters": RELEASE_FILTERS,
        "results": res.to_dict(orient="records"),
    }, open(OUT / "v54_results.json", "w"), indent=2, default=str)

    print(f"\n  → saved: {OUT / 'sweep_results.csv'}")
    print(f"  → saved: {OUT / 'v54_results.json'}")
    print(f"  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
