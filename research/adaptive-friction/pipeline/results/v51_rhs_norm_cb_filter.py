# -*- coding: utf-8 -*-
"""
v51_rhs_norm_cb_filter.py
=========================

IMPLEMENTS THE FIX identified by v50 clustering:

  C2 cluster (high-rhs_norm, negative-skew losers) is distinguishable at
  CB-release time by:  rhs_norm_0 > THRESHOLD

  For A_v34_base and E_d0.50, rhs_norm_0 > 0.60 at CB release:
    ✓ BLOCKS  2024-01-30  (loser, −8.4%)      rhs_norm=0.733
    ✓ PASSES  2025-04-02  (winner, +8.1%)     rhs_norm=0.575
    ✗ MISSES  2023-06-16  (loser, −12.5%)     rhs_norm=0.584  ← below threshold

  The filter: when CB would release (cb_dd ≤ cb_resume):
      compute rhs_norm from ODE log at that bar
      if rhs_norm > RHS_THRESH → extend halt by EXTEND_BARS (re-lock CB)
      allow release only once rhs_norm has dropped below threshold

Sweep: RHS_THRESH ∈ {0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75}
       applied to  A_v34_base (d=0.25, q=0.50, w=90d)
                   E_d0.50    (d=0.50, q=0.50, w=90d)

Outputs
-------
  v51_rhs_filter/
    sweep_results.csv
    plots/
      pareto_final_vs_maxdd.png
      equity_comparison_A.png
      equity_comparison_E.png
      rhs_norm_at_releases.png
"""
from __future__ import annotations

import json
import sys
import time
from collections import deque
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

import run_crypto_godmode_v27_all_microstructure as v27
import run_crypto_godmode_v28_canonical_stability as v28
from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import W_TARGET_A1, build_b_aligned, build_w_star
from run_crypto_canonical_v4 import build_factor_returns
from run_crypto_godmode_v8_multiasset_shell import (
    ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol,
)
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, INIT, HOURS_PER_DAY, equity_metrics
from run_crypto_godmode_v35_top5_cb_transition import REG_VARIANT, K_NORMAL, RT_BPS, build_sigma, theta_from

from v49_mode1_feature_search import run_ode

BAR = "=" * 110
OUT = Path(OUT_DIR) / "v51_rhs_filter"
PLOT = OUT / "plots"

VARIANTS = [
    ("A_v34_base", 0.25, 0.50, "tab:red"),
    ("E_d0.50",    0.50, 0.50, "tab:orange"),
]

CB_HALT    = 0.08
CB_RESUME  = 0.04
CB_WINDOW_D = 90

RHS_THRESHOLDS   = [0.0, 0.50, 0.55, 0.60, 0.65, 0.70]
EXTEND_BARS_LIST = [240, 480, 720, 1440]   # 10d, 20d, 30d, 60d extra halt


def simulate_with_rhs_filter(unit_series, ode_log, K_normal,
                               cb_halt, cb_resume, cb_window_d,
                               rhs_thresh, extend_bars=720):
    """
    v34-style CB sim with timer-based rhs_norm extension at release.

    At every CB release attempt (cb_dd drops to cb_resume while halted):
      • if rhs_norm > rhs_thresh → extend halt by `extend_bars` more bars
        (keep y=0 for that many additional bars, then release unconditionally)
      • else → normal release

    The timer approach avoids the rolling-peak stale problem:
      the strategy stays halted (y=0, eq flat), and after the timer expires
      it releases regardless of cb_dd.  One block per CB cycle.
    """
    window_bars = cb_window_d * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq, peak_alltime = INIT, INIT

    halted          = False
    extend_counter  = 0      # bars remaining in extended halt
    release_events  = []

    unit = unit_series.values
    rhs  = ode_log["rhs_norm"].reindex(unit_series.index, method="ffill").fillna(0.0).values
    N    = len(unit)
    eq_vals, y_vals, state_vals = [], [], []

    for i in range(N):
        ur_n = float(unit[i])
        while mono_dq and mono_dq[0][0] <= i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((i, eq))
        roll_peak = mono_dq[0][1]
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak, 1e-12))
        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))

        # ── Halt / release logic ──
        if extend_counter > 0:
            # In forced extension: count down, then release unconditionally
            extend_counter -= 1
            if extend_counter == 0:
                halted = False   # release regardless of cb_dd / rhs_norm

        elif not halted:
            if cb_dd >= cb_halt:
                halted = True

        else:  # halted, no extension active
            if cb_dd <= cb_resume:
                rhs_now = float(rhs[i])
                if rhs_thresh > 0.0 and rhs_now > rhs_thresh:
                    extend_counter = extend_bars  # stay halted for N more bars
                    release_events.append(dict(bar=i, ts=unit_series.index[i],
                                                rhs_norm=rhs_now, blocked=True,
                                                extend_bars=extend_bars))
                else:
                    halted = False
                    if rhs_thresh > 0.0:
                        release_events.append(dict(bar=i, ts=unit_series.index[i],
                                                    rhs_norm=rhs_now, blocked=False,
                                                    extend_bars=0))

        # ── Position scaler ──
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
        state_vals.append(int(is_halted))

    return dict(
        eq=pd.Series(eq_vals, index=unit_series.index),
        cb=pd.Series(state_vals, index=unit_series.index),
        y=pd.Series(y_vals, index=unit_series.index),
        release_events=release_events,
    )


def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    PLOT.mkdir(parents=True, exist_ok=True)

    print(BAR)
    print("  v51 — RHS_NORM CB GATE (CLUSTER C2 FIX)")
    print("  Filter: at CB release, if rhs_norm > threshold → keep halted")
    print(f"  Thresholds tested: {RHS_THRESHOLDS}")
    print(BAR)

    # ─── Setup ───
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

    # ─── ODE per variant ───
    print("\n[1] Building ODE + unit returns ...")
    ode_cache = {}
    for label, d, q, _ in VARIANTS:
        print(f"\n  [{label}]  d={d}, q={q}")
        Sigma_base, _, _, bdiag = build_sigma(factor_R, train_mask, df, d)
        theta = theta_from(b_aligned, train_mask, Sigma_base, bdiag["budget"], q)
        log_ann, _ = run_ode(df, train_mask, w_star, b_aligned, Sigma_base, theta)
        inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                         signal_kind="wstar", use_quadrant=False)
        inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                       signal_kind="wstar", use_quadrant=True)
        inputs = attach_q_hot(inputs_noq, inputs_q)
        sig_map = {a: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{a}")
                   for a, _, _, idx in ASSETS}
        unit = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]
        ode_cache[label] = (log_ann, unit)

    # ─── Sweep ───
    extend_options = [0] + EXTEND_BARS_LIST  # 0 = baseline (no filter)
    print(f"\n[2] Sweeping {len(RHS_THRESHOLDS)} thresholds × {len(EXTEND_BARS_LIST)} extend windows × {len(VARIANTS)} variants ...")
    print(f"\n  {'variant':<12} {'thr':>5} {'ext_d':>6} {'n_blk':>6} "
          f"{'final':>12} {'maxdd':>8} {'calmar':>7} {'sharpe':>7}")
    print("  " + "-" * 75)

    all_rows = []
    eq_curves = {v[0]: {} for v in VARIANTS}

    for label, d, q, color in VARIANTS:
        log_ann, unit = ode_cache[label]
        # Baseline first
        sim = simulate_with_rhs_filter(unit, log_ann, K_NORMAL,
                                        CB_HALT, CB_RESUME, CB_WINDOW_D,
                                        rhs_thresh=0.0, extend_bars=0)
        eq_test = sim["eq"][sim["eq"].index >= test_ts]
        m = equity_metrics(eq_test, f"{label}_base")
        row = dict(variant=label, d=d, q=q, rhs_thresh=0.0, extend_bars=0, extend_days=0,
                    n_blocked=0, final=m["final"], maxdd=m["maxdd"],
                    calmar=m["calmar"], sharpe=m["sharpe"])
        all_rows.append(row)
        eq_curves[label][(0.0, 0)] = eq_test
        print(f"  {label:<12} {'base':>5} {'---':>6} {'---':>6}   ${m['final']:>10,.0f} "
              f"{m['maxdd']:>8.2%} {m['calmar']:>7.2f} {m['sharpe']:>7.2f} ◉")

        for thr in RHS_THRESHOLDS[1:]:  # skip 0.0
            for ext in EXTEND_BARS_LIST:
                sim = simulate_with_rhs_filter(unit, log_ann, K_NORMAL,
                                                CB_HALT, CB_RESUME, CB_WINDOW_D,
                                                rhs_thresh=thr, extend_bars=ext)
                eq_test = sim["eq"][sim["eq"].index >= test_ts]
                m = equity_metrics(eq_test, f"{label}_t{thr:.2f}_e{ext}")
                n_blocked = sum(1 for e in sim["release_events"] if e["blocked"])
                ext_days = ext // HOURS_PER_DAY
                row = dict(variant=label, d=d, q=q, rhs_thresh=thr, extend_bars=ext,
                            extend_days=ext_days, n_blocked=n_blocked,
                            final=m["final"], maxdd=m["maxdd"],
                            calmar=m["calmar"], sharpe=m["sharpe"])
                all_rows.append(row)
                eq_curves[label][(thr, ext)] = eq_test
                star = ("  ★" if m["maxdd"] > -0.30 and m["final"] > 100_000
                        else ("  ◉" if m["maxdd"] > -0.32 and m["final"] > 200_000 else ""))
                print(f"  {label:<12} {thr:>5.2f} {ext_days:>6}d {n_blocked:>6}   ${m['final']:>10,.0f} "
                      f"{m['maxdd']:>8.2%} {m['calmar']:>7.2f} {m['sharpe']:>7.2f}{star}")
        print()

    results = pd.DataFrame(all_rows)
    results.to_csv(OUT / "sweep_results.csv", index=False)
    print(f"  → sweep_results.csv saved")

    # ─── rhs_norm at release attempts (diagnostic using lowest threshold) ───
    print("\n[3] rhs_norm at CB release attempts (all checkpoints):")
    for label, d, q, color in VARIANTS:
        log_ann, unit = ode_cache[label]
        sim_diag = simulate_with_rhs_filter(unit, log_ann, K_NORMAL,
                                             CB_HALT, CB_RESUME, CB_WINDOW_D,
                                             rhs_thresh=0.30, extend_bars=1)
        test_events = [e for e in sim_diag["release_events"]
                       if pd.Timestamp(e["ts"]) >= test_ts]
        print(f"\n  {label}  ({len(test_events)} release attempts in test set):")
        if test_events:
            print(f"    {'timestamp':<22} {'rhs_norm':>10}  status")
            for ev in test_events:
                print(f"    {str(ev['ts']):<22} {ev['rhs_norm']:>10.4f}  "
                      f"{'BLOCKED' if ev['blocked'] else 'released'}")

    # ─── Plots ───
    print("\n[4] Generating plots ...")

    # 1. Pareto: Final equity vs MaxDD across all threshold × extend combos
    fig, ax = plt.subplots(figsize=(13, 8))
    for label, d, q, color in VARIANTS:
        sub = results[results["variant"] == label]
        base = sub[sub["rhs_thresh"] == 0.0].iloc[0]
        ax.scatter([base["maxdd"] * 100], [base["final"] / 1000],
                    c=color, s=350, marker="*", zorder=8,
                    label=f"{label} baseline: ${base['final']:,.0f}, MDD={base['maxdd']:.1%}")
        for _, r in sub[sub["rhs_thresh"] > 0].iterrows():
            ax.scatter([r["maxdd"] * 100], [r["final"] / 1000],
                        c=color, s=80, alpha=0.7, edgecolor="black", linewidth=0.5, zorder=5)
            lbl = f"{r['rhs_thresh']:.2f}/{int(r['extend_days'])}d"
            ax.annotate(lbl, (r["maxdd"] * 100, r["final"] / 1000),
                         xytext=(4, 3), textcoords="offset points", fontsize=7, color=color)
    # v45 reference point
    ax.scatter([-14.0], [130.7], c="gold", s=250, marker="D", zorder=7,
               label="v45_w180: $131K, MDD=-14%", edgecolor="black")
    ax.axvline(-34.57, color="gray", lw=0.8, ls="--", alpha=0.4)
    ax.set_xlabel("Max Drawdown (%)")
    ax.set_ylabel("Final Equity ($K)")
    ax.set_title("v51 — Pareto: Final equity vs MaxDD\n"
                  "(labels: rhs_thresh / extend_days;  ★ = baseline;  ◆ = v45_w180 reference)",
                  fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(PLOT / "pareto_final_vs_maxdd.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # 2. Equity curves for best 4 non-baseline configs per variant
    for label, d, q, base_color in VARIANTS:
        sub = results[results["variant"] == label]
        # pick: baseline + top-4 by Calmar (unique final values only)
        non_base = sub[sub["rhs_thresh"] > 0].sort_values("calmar", ascending=False).head(4)
        configs_to_plot = [(0.0, 0)] + list(zip(non_base["rhs_thresh"], non_base["extend_bars"]))
        fig, ax = plt.subplots(figsize=(15, 6))
        cmap = plt.cm.plasma
        for k, (thr, ext) in enumerate(configs_to_plot):
            if (thr, ext) not in eq_curves[label]: continue
            eq = eq_curves[label][(thr, ext)]
            lw = 2.5 if thr == 0.0 else 1.4
            color = "black" if thr == 0.0 else cmap(k / max(len(configs_to_plot) - 1, 1))
            row = results[(results["variant"] == label) & (results["rhs_thresh"] == thr) &
                           (results["extend_bars"] == ext)].iloc[0]
            lbl = (f"baseline" if thr == 0.0
                   else f"thr={thr:.2f} ext={int(ext//HOURS_PER_DAY)}d  "
                        f"${row['final']:,.0f}  MDD={row['maxdd']:.1%}")
            ax.semilogy(eq.index, eq.values, lw=lw, alpha=0.85, color=color, label=lbl)
        ax.set_ylabel("Equity ($, log)")
        ax.set_title(f"v51 — {label}: baseline vs best filtered configs",
                      fontweight="bold")
        ax.legend(fontsize=8, loc="upper left")
        ax.grid(True, alpha=0.2)
        fig.tight_layout()
        fig.savefig(PLOT / f"equity_comparison_{label}.png", dpi=160, bbox_inches="tight")
        plt.close(fig)

    # 3. rhs_norm bar chart at all releases
    fig, ax = plt.subplots(figsize=(14, 5))
    xtick_labels, all_rhs_vals = [], []
    for label, d, q, color in VARIANTS:
        log_ann, unit = ode_cache[label]
        sim_d = simulate_with_rhs_filter(unit, log_ann, K_NORMAL,
                                          CB_HALT, CB_RESUME, CB_WINDOW_D,
                                          rhs_thresh=0.30, extend_bars=1)
        test_evs = [e for e in sim_d["release_events"] if pd.Timestamp(e["ts"]) >= test_ts]
        for ev in test_evs:
            ts_str = f"{label[:1]}\n{str(ev['ts'])[:10]}"
            xtick_labels.append(ts_str)
            all_rhs_vals.append(ev["rhs_norm"])
    x = range(len(xtick_labels))
    bars = ax.bar(x, all_rhs_vals, alpha=0.75, edgecolor="black", color="steelblue")
    for thr, col in [(0.50, "red"), (0.60, "orange"), (0.70, "gold")]:
        ax.axhline(thr, color=col, lw=1.2, ls="--", label=f"thr={thr:.2f}")
    ax.set_xticks(range(len(xtick_labels)))
    ax.set_xticklabels(xtick_labels, fontsize=7, rotation=45, ha="right")
    ax.set_ylabel("rhs_norm at CB release")
    ax.set_title("v51 — rhs_norm at every CB release attempt (test set)\n"
                  "Bars above threshold line = would be BLOCKED",
                  fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25, axis="y")
    fig.tight_layout()
    fig.savefig(PLOT / "rhs_norm_at_releases.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # 4. Calmar vs threshold, for best extend window per threshold
    fig, ax = plt.subplots(figsize=(10, 5))
    for label, d, q, color in VARIANTS:
        sub = results[results["variant"] == label]
        base_cal = float(sub[sub["rhs_thresh"] == 0.0]["calmar"].iloc[0])
        best_per_thr = sub[sub["rhs_thresh"] > 0].groupby("rhs_thresh")["calmar"].max().reset_index()
        ax.plot(best_per_thr["rhs_thresh"], best_per_thr["calmar"],
                 marker="o", color=color, lw=2, label=label)
        ax.axhline(base_cal, color=color, lw=1.0, ls="--", alpha=0.5)
    ax.set_xlabel("rhs_norm threshold")
    ax.set_ylabel("Calmar ratio (best extend window per threshold)")
    ax.set_title("v51 — Calmar vs rhs_norm threshold\n(dashed = baseline)",
                  fontweight="bold")
    ax.legend(); ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(PLOT / "calmar_vs_threshold.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # ─── Summary ───
    print(f"\n[5] Best configurations per variant:")
    for label, d, q, _ in VARIANTS:
        sub = results[results["variant"] == label]
        base = sub[sub["rhs_thresh"] == 0.0].iloc[0]
        non_base = sub[sub["rhs_thresh"] > 0].copy()
        if non_base.empty:
            continue
        best_cal = non_base.loc[non_base["calmar"].idxmax()]
        best_mdd_improv = non_base.loc[(non_base["maxdd"] - base["maxdd"]).idxmax()]
        print(f"\n  {label}:")
        print(f"    Baseline:         Final=${base['final']:>10,.0f}  MDD={base['maxdd']:>+.2%}  Cal={base['calmar']:.2f}")
        print(f"    Best Calmar:      Final=${best_cal['final']:>10,.0f}  MDD={best_cal['maxdd']:>+.2%}  "
              f"Cal={best_cal['calmar']:.2f}  "
              f"(thr={best_cal['rhs_thresh']:.2f}, ext={int(best_cal['extend_days'])}d, "
              f"blk={int(best_cal['n_blocked'])})")
        if best_mdd_improv["rhs_thresh"] != best_cal["rhs_thresh"]:
            print(f"    Best MDD reduce:  Final=${best_mdd_improv['final']:>10,.0f}  "
                  f"MDD={best_mdd_improv['maxdd']:>+.2%}  Cal={best_mdd_improv['calmar']:.2f}  "
                  f"(thr={best_mdd_improv['rhs_thresh']:.2f}, ext={int(best_mdd_improv['extend_days'])}d)")
        print(f"    v45_w180 ref:     Final=$   130,672  MDD=-13.98%  Cal=23.25")

    # ─── Save JSON ───
    json.dump({
        "version": "v51",
        "filter": "rhs_norm_0 at CB release",
        "thresholds_tested": RHS_THRESHOLDS,
        "results": results.to_dict(orient="records"),
    }, open(OUT / "v51_results.json", "w"), indent=2, default=str)

    print(f"\n  → Plots in: {PLOT}")
    print(f"\n{BAR}")
    print(f"  v51 COMPLETE  |  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
