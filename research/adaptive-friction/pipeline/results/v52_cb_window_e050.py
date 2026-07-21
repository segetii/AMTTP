# -*- coding: utf-8 -*-
"""
v52_cb_window_e050.py
=====================

Diagnosis: v51 best result (E_d0.50, rhs_norm≥0.55, ext=30d) achieves
Final=$948K but MaxDD=-29.45%.  The all-time peak (~$1.34M) is set by the
Nov-2025 moonshot; post-peak normal performance creates the residual -29%.

The v45 w=180d breakthrough (-14% MDD) worked by keeping the strategy
HALTED LONGER after large equity peaks (longer rolling window → cb_dd
stays high after a moonshot → strategy stays inactive → protects gains).

v45 used d=0.25 → Final=$131K (cheap MDD at cost of return).
v52 tests whether d=0.50 (higher leverage on each active segment) can
give BOTH lower MDD (via wider CB window) AND higher returns.

Sweep
-----
  Variant:    E_d0.50  (d=0.50, q=0.50) ONLY
  CB windows: [90, 120, 150, 180, 240, 365]
  Filter:     baseline (no rhs) AND rhs_norm(thr=0.55, ext=30d) from v51
  Reference:  A_v34_base (d=0.25, q=0.50, w=90d) as fixed baseline marker
              B_v45_w180 (d=0.25, q=0.50, w=180d) as reference point

Total runs: 6 windows × 2 filter modes × 1 variant = 12 + 2 reference = 14

Outputs
-------
  v52_window_sweep/
    sweep_results.csv
    plots/
      pareto_final_vs_maxdd.png       main Pareto with all configs
      calmar_vs_window.png            Calmar vs CB window length
      equity_best_configs.png         equity curves: top picks
      mdd_vs_window.png               MaxDD vs window
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
OUT = Path(OUT_DIR) / "v52_window_sweep"
PLOT = OUT / "plots"

# ── Config ──────────────────────────────────────────────────────────────────
VARIANTS = [
    ("A_v34_base", 0.25, 0.50),  # reference only, w=90d
    ("E_d0.50",    0.50, 0.50),  # SWEEP TARGET
]

CB_HALT    = 0.08
CB_RESUME  = 0.04

CB_WINDOWS  = [90, 120, 150, 180, 240, 365]   # days

# Best rhs_norm config from v51
RHS_THRESH  = 0.55
EXTEND_BARS = 720    # 30 days


def simulate_with_rhs_filter(unit_series, ode_log, K_normal,
                               cb_halt, cb_resume, cb_window_d,
                               rhs_thresh=0.0, extend_bars=720):
    """
    CB simulation with optional rhs_norm gating at release.
    Identical logic to v51 (timer-based extension).
    """
    window_bars = cb_window_d * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq, peak_alltime = INIT, INIT

    halted          = False
    extend_counter  = 0
    release_events  = []

    unit = unit_series.values
    rhs  = ode_log["rhs_norm"].reindex(unit_series.index, method="ffill").fillna(0.0).values
    N    = len(unit)
    eq_vals, y_vals, halted_vals = [], [], []

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

        # Halt / release logic (timer-based)
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
                if rhs_thresh > 0.0 and rhs_now > rhs_thresh:
                    extend_counter = extend_bars
                    release_events.append(dict(bar=i, ts=unit_series.index[i],
                                                rhs_norm=rhs_now, blocked=True))
                else:
                    halted = False
                    if rhs_thresh > 0.0:
                        release_events.append(dict(bar=i, ts=unit_series.index[i],
                                                    rhs_norm=rhs_now, blocked=False))

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
        cb=pd.Series(halted_vals, index=unit_series.index),
        y=pd.Series(y_vals, index=unit_series.index),
        release_events=release_events,
        n_blocked=sum(1 for e in release_events if e["blocked"]),
    )


def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    PLOT.mkdir(parents=True, exist_ok=True)

    print(BAR)
    print("  v52 — CB WINDOW SWEEP for E_d0.50")
    print("  Hypothesis: wider CB window keeps strategy halted longer after")
    print("              moonshot peak → lower MaxDD with d=0.50 returns")
    print(f"  Windows: {CB_WINDOWS} days")
    print(f"  Filter:  rhs_norm≥{RHS_THRESH} + ext={EXTEND_BARS//HOURS_PER_DAY}d (from v51)")
    print(BAR)

    # ── Setup ─────────────────────────────────────────────────────────────
    print("\n[0] Microstructure + inputs ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        v27._get_ms(sym)

    df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_ts    = pd.Timestamp(TEST_START)
    w_star     = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned  = build_b_aligned(w_star)
    factor_R   = build_factor_returns(df)
    v27.RT_COST = RT_BPS / 10_000.0

    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()

    # ── ODE per variant ───────────────────────────────────────────────────
    print("\n[1] Building ODE + unit returns ...")
    ode_cache = {}
    for label, d, q in VARIANTS:
        print(f"\n  [{label}]  d={d}, q={q}")
        Sigma_base, _, _, bdiag = build_sigma(factor_R, train_mask, df, d)
        theta = theta_from(b_aligned, train_mask, Sigma_base, bdiag["budget"], q)
        log_ann, _ = run_ode(df, train_mask, w_star, b_aligned, Sigma_base, theta)
        inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                         signal_kind="wstar", use_quadrant=False)
        inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                         signal_kind="wstar", use_quadrant=True)
        inputs     = attach_q_hot(inputs_noq, inputs_q)
        sig_map    = {a: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{a}")
                      for a, _, _, idx in ASSETS}
        unit       = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]
        ode_cache[label] = (log_ann, unit)

    # ── Sweep ─────────────────────────────────────────────────────────────
    print(f"\n[2] Running sweep: {len(CB_WINDOWS)} windows × 2 filters × {len(VARIANTS)} variants ...")
    hdr = (f"\n  {'variant':<12} {'window':>7} {'filter':>9} {'n_blk':>6} "
           f"{'final':>12} {'maxdd':>8} {'calmar':>7} {'sharpe':>7}")
    print(hdr)
    print("  " + "-" * 79)

    all_rows = []
    eq_store = {}   # (label, window_d, use_rhs) -> eq_test Series

    for label, d, q in VARIANTS:
        log_ann, unit = ode_cache[label]

        if label == "A_v34_base":
            # Reference: only run the standard w=90 baseline
            sim = simulate_with_rhs_filter(unit, log_ann, K_NORMAL,
                                            CB_HALT, CB_RESUME, 90, 0.0, 0)
            eq_test = sim["eq"][sim["eq"].index >= test_ts]
            m = equity_metrics(eq_test, label)
            row = dict(variant=label, d=d, q=q, window_d=90, filter="none",
                        n_blocked=0, final=m["final"], maxdd=m["maxdd"],
                        calmar=m["calmar"], sharpe=m["sharpe"])
            all_rows.append(row)
            eq_store[(label, 90, False)] = eq_test
            print(f"  {label:<12} {90:>6}d {'none':>9} {'---':>6}   ${m['final']:>10,.0f} "
                  f"{m['maxdd']:>8.2%} {m['calmar']:>7.2f} {m['sharpe']:>7.2f}  [ref A]")
            continue

        # E_d0.50: full sweep
        for w in CB_WINDOWS:
            for use_rhs, filt_label in [(False, "none"), (True, f"rhs≥{RHS_THRESH}")]:
                thr   = RHS_THRESH if use_rhs else 0.0
                ext   = EXTEND_BARS if use_rhs else 0
                sim   = simulate_with_rhs_filter(unit, log_ann, K_NORMAL,
                                                  CB_HALT, CB_RESUME, w, thr, ext)
                eq_test = sim["eq"][sim["eq"].index >= test_ts]
                m = equity_metrics(eq_test, f"{label}_w{w}_{filt_label}")
                n_blk = sim["n_blocked"]
                row = dict(variant=label, d=d, q=q, window_d=w, filter=filt_label,
                            n_blocked=n_blk, final=m["final"], maxdd=m["maxdd"],
                            calmar=m["calmar"], sharpe=m["sharpe"])
                all_rows.append(row)
                eq_store[(label, w, use_rhs)] = eq_test

                # Markers
                star = ""
                if m["maxdd"] > -0.20 and m["final"] > 200_000:
                    star = "  ★★ (<20% MDD + >$200K)"
                elif m["maxdd"] > -0.25 and m["final"] > 300_000:
                    star = "  ★ (<25% MDD + >$300K)"
                elif m["maxdd"] > -0.30 and m["final"] > 500_000:
                    star = "  ◉ (<30% MDD + >$500K)"

                print(f"  {label:<12} {w:>6}d {filt_label:>9} {n_blk:>6}   ${m['final']:>10,.0f} "
                      f"{m['maxdd']:>8.2%} {m['calmar']:>7.2f} {m['sharpe']:>7.2f}{star}")

        print()

    results = pd.DataFrame(all_rows)
    results.to_csv(OUT / "sweep_results.csv", index=False)
    print(f"  → sweep_results.csv saved ({len(results)} rows)")

    # ── Plots ─────────────────────────────────────────────────────────────
    print("\n[3] Generating plots ...")

    # 1. Pareto: Final equity vs MaxDD
    fig, ax = plt.subplots(figsize=(14, 9))
    e_rows = results[results["variant"] == "E_d0.50"].copy()

    cmap_none = plt.cm.Blues
    cmap_rhs  = plt.cm.Oranges
    windows_sorted = sorted(CB_WINDOWS)

    for i, w in enumerate(windows_sorted):
        shade = 0.35 + 0.55 * i / (len(windows_sorted) - 1)
        # no filter
        r0 = e_rows[(e_rows["window_d"] == w) & (e_rows["filter"] == "none")]
        if not r0.empty:
            ax.scatter([r0.iloc[0]["maxdd"] * 100], [r0.iloc[0]["final"] / 1000],
                        c=[cmap_none(shade)], s=160, marker="o", zorder=5,
                        label=f"E w={w}d")
            ax.annotate(f"w={w}d", (r0.iloc[0]["maxdd"] * 100, r0.iloc[0]["final"] / 1000),
                         xytext=(4, 3), textcoords="offset points", fontsize=8)
        # rhs filter
        r1 = e_rows[(e_rows["window_d"] == w) & (e_rows["filter"] != "none")]
        if not r1.empty:
            ax.scatter([r1.iloc[0]["maxdd"] * 100], [r1.iloc[0]["final"] / 1000],
                        c=[cmap_rhs(shade)], s=160, marker="^", zorder=5,
                        label=f"E w={w}d+rhs")
            ax.annotate(f"w={w}d+rhs", (r1.iloc[0]["maxdd"] * 100, r1.iloc[0]["final"] / 1000),
                         xytext=(4, 3), textcoords="offset points", fontsize=8)

    # Reference points
    a_row = results[results["variant"] == "A_v34_base"].iloc[0]
    ax.scatter([a_row["maxdd"] * 100], [a_row["final"] / 1000],
                c="black", s=250, marker="*", zorder=8,
                label=f"A_v34_base (w=90d): ${a_row['final']/1000:.0f}K")
    ax.scatter([-34.85], [728.9], c="gray", s=200, marker="D", zorder=7,
               label="E_d0.50 v51-baseline: $729K, MDD=-34.85%", edgecolor="black")
    ax.scatter([-29.45], [948.1], c="gold", s=250, marker="*", zorder=8,
               label="E_d0.50 v51-best (w=90d+rhs): $948K, MDD=-29.45%", edgecolor="darkorange")
    ax.scatter([-13.98], [130.7], c="limegreen", s=200, marker="s", zorder=7,
               label="v45_w180 (d=0.25,w=180d): $131K, MDD=-14%", edgecolor="green")
    ax.axvline(-29.45, color="orange", lw=0.8, ls="--", alpha=0.4, label="v51 best MDD")
    ax.axvline(-20.0,  color="red",    lw=1.0, ls="--", alpha=0.5, label="-20% target")

    ax.set_xlabel("Max Drawdown (%)", fontsize=12)
    ax.set_ylabel("Final Equity ($K)", fontsize=12)
    ax.set_title("v52 — Pareto: E_d0.50 CB Window Sweep\n"
                  "(circles=no rhs filter, triangles=rhs≥0.55+30d; color=window length)",
                  fontweight="bold", fontsize=12)
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(PLOT / "pareto_final_vs_maxdd.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # 2. Calmar vs window
    fig, ax = plt.subplots(figsize=(11, 6))
    for use_rhs, filt_name, color, marker in [
        (False, "no filter", "steelblue", "o"),
        (True,  f"rhs≥{RHS_THRESH}+30d", "darkorange", "^"),
    ]:
        sub = e_rows[e_rows["filter"] == ("none" if not use_rhs else f"rhs\u2265{RHS_THRESH}")]
        sub_s = sub.sort_values("window_d")
        ax.plot(sub_s["window_d"], sub_s["calmar"], marker=marker,
                 color=color, lw=2.0, label=f"E_d0.50 {filt_name}")
    ax.axhline(17.45, color="gray",  lw=1.0, ls="--", alpha=0.6, label="E_d0.50 v51-baseline Cal=17.45")
    ax.axhline(22.60, color="orange",lw=1.0, ls="--", alpha=0.6, label="v51 best Cal=22.60")
    ax.axhline(23.25, color="green", lw=1.0, ls="--", alpha=0.6, label="v45_w180 Cal=23.25")
    ax.set_xlabel("CB Window (days)", fontsize=12)
    ax.set_ylabel("Calmar Ratio", fontsize=12)
    ax.set_title("v52 — Calmar vs CB Window", fontweight="bold", fontsize=12)
    ax.legend(fontsize=9); ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(PLOT / "calmar_vs_window.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # 3. MaxDD vs window
    fig, ax = plt.subplots(figsize=(11, 6))
    for use_rhs, filt_name, color, marker in [
        (False, "no filter", "steelblue", "o"),
        (True,  f"rhs≥{RHS_THRESH}+30d", "darkorange", "^"),
    ]:
        sub = e_rows[e_rows["filter"] == ("none" if not use_rhs else f"rhs\u2265{RHS_THRESH}")]
        sub_s = sub.sort_values("window_d")
        ax.plot(sub_s["window_d"], sub_s["maxdd"] * 100, marker=marker,
                 color=color, lw=2.0, label=f"E_d0.50 {filt_name}")
    ax.axhline(-34.85, color="gray",   lw=1.0, ls="--", alpha=0.6, label="E baseline -34.85%")
    ax.axhline(-29.45, color="orange", lw=1.0, ls="--", alpha=0.6, label="v51 best -29.45%")
    ax.axhline(-20.0,  color="red",    lw=1.2, ls="--", alpha=0.7, label="-20% target")
    ax.axhline(-13.98, color="green",  lw=1.0, ls="--", alpha=0.6, label="v45_w180 -13.98%")
    ax.set_xlabel("CB Window (days)", fontsize=12)
    ax.set_ylabel("Max Drawdown (%)", fontsize=12)
    ax.set_title("v52 — MaxDD vs CB Window", fontweight="bold", fontsize=12)
    ax.legend(fontsize=9); ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(PLOT / "mdd_vs_window.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # 4. Equity curves: best configs per filter type
    fig, ax = plt.subplots(figsize=(16, 7))
    # A baseline
    if ("A_v34_base", 90, False) in eq_store:
        ax.semilogy(eq_store[("A_v34_base", 90, False)].index,
                     eq_store[("A_v34_base", 90, False)].values,
                     lw=1.2, color="black", ls="--", alpha=0.6, label="A_v34_base w=90d (ref)")

    cmap2 = plt.cm.tab10
    k = 0
    for w in CB_WINDOWS:
        for use_rhs in [False, True]:
            key = ("E_d0.50", w, use_rhs)
            if key not in eq_store:
                continue
            r = results[(results["variant"] == "E_d0.50") &
                         (results["window_d"] == w) &
                         (results["filter"] == ("none" if not use_rhs else f"rhs\u2265{RHS_THRESH}"))
                       ].iloc[0]
            lbl = (f"E w={w}d{'+ rhs' if use_rhs else '':5s}  "
                   f"${r['final']/1000:.0f}K  MDD={r['maxdd']:.1%}  Cal={r['calmar']:.1f}")
            lw = 2.2 if abs(r["maxdd"]) < 0.25 else 1.2
            ax.semilogy(eq_store[key].index, eq_store[key].values,
                         lw=lw, alpha=0.8, color=cmap2(k % 10), label=lbl)
            k += 1

    ax.set_ylabel("Equity ($, log scale)")
    ax.set_title("v52 — E_d0.50: all CB window configs", fontweight="bold")
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(PLOT / "equity_all_configs.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n[4] Summary — E_d0.50 best per window:")
    print(f"\n  {'window':>6} {'filter':>12} {'n_blk':>6}  {'final':>12} {'maxdd':>8} {'calmar':>7}")
    print("  " + "-" * 64)
    for w in CB_WINDOWS:
        best_w = e_rows[e_rows["window_d"] == w].sort_values("calmar", ascending=False).iloc[0]
        star = ""
        if best_w["maxdd"] > -0.20:
            star = "  ★★"
        elif best_w["maxdd"] > -0.25:
            star = "  ★"
        elif best_w["maxdd"] > -0.29:
            star = "  ◉"
        print(f"  {w:>6}d {best_w['filter']:>12} {int(best_w['n_blocked']):>6}  "
              f"${best_w['final']:>10,.0f} {best_w['maxdd']:>8.2%} {best_w['calmar']:>7.2f}{star}")

    print(f"\n  References:")
    print(f"  A_v34_base w=90d  baseline: ${a_row['final']:>10,.0f}  MDD=-34.57%  Cal=16.60")
    print(f"  E_d0.50    w=90d  baseline: $   728,938  MDD=-34.85%  Cal=17.45")
    print(f"  E_d0.50    w=90d  rhs≥0.55: $   948,085  MDD=-29.45%  Cal=22.60")
    print(f"  v45_w180  (d=0.25,w=180d) : $   130,672  MDD=-13.98%  Cal=23.25")

    # Save JSON
    summary = {
        "version": "v52",
        "description": "CB window sweep for E_d0.50 (d=0.50, q=0.50)",
        "cb_windows_tested": CB_WINDOWS,
        "rhs_filter": {"thresh": RHS_THRESH, "extend_bars": EXTEND_BARS, "extend_days": EXTEND_BARS // HOURS_PER_DAY},
        "results": results.to_dict(orient="records"),
    }
    with open(OUT / "v52_results.json", "w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    print(f"\n  → v52_results.json saved")
    print(f"  → Plots in: {PLOT}")

    print(f"\n{BAR}")
    print(f"  v52 COMPLETE  |  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
