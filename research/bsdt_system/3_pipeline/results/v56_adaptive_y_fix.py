# -*- coding: utf-8 -*-
"""
v56_adaptive_y_fix.py
=====================

Fix the adaptive-Y drawdown throttle on top of the v55 robust stack.

Diagnosis of the v55 result:
- The Y schedule (dd_soft=0.05, dd_stop=0.20, y_floor=0.25) leaves 25% size on
  at -20%+ DD; with K_normal=6.5 the effective leverage is still ~1.6x.
- It uses dd_aty (all-time peak) which lags during fast crashes inside an
  established uptrend.
- Net effect: -29% to -32% MaxDD persists even with G7 + omega + curvature
  + admissibility + G2.4 + rhs filter all active.

This script holds the v55 best mechanism stacks fixed and sweeps:
  * (dd_soft, dd_stop, y_floor) schedules — including hard stops (y_floor=0)
  * DD source: 'aty' (all-time peak), 'cb' (rolling 90d peak), 'max' (worst of both)

Only the y-throttle changes; the upstream signal (G7 / omega / curvature /
admissibility / G2.4 / rhs filter) is held at the v55 winners.
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
from run_crypto_canonical_v4 import build_factor_returns, A_FACTORS, DT
from run_crypto_godmode_v8_multiasset_shell import ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import INIT, HOURS_PER_DAY, equity_metrics
from run_crypto_godmode_v35_top5_cb_transition import REG_VARIANT, K_NORMAL, RT_BPS, build_sigma, theta_from
from run_crypto_godmode_v38_ito_tightcb import (
    regularise_sigma_g7, fisher_weight_noise_sqrt, c_sigma_per_bar,
)
from v49_mode1_feature_search import run_ode
from v55_730k_robust_full import compute_psi_star, build_unit_for_sigma

BAR = "=" * 112
OUT = Path(OUT_DIR) / "v56_adaptive_y_fix"

# ── Locked champion baseline ─────────────────────────────────────────────────
D_CHAMP    = 0.50
Q_CHAMP    = 0.65
CB_HALT    = 0.08
CB_RESUME  = 0.04
CB_WINDOW_D = 90
EPS_RHS = 1e-6

# ── v55 winner stacks (locked) ───────────────────────────────────────────────
# Each stack: (label, kappa_max, omega_a, curv_b, admiss_c, g24_eta, g24_lock_min, rel_thr, rel_ext_days)
STACKS = [
    # Best Final ($1.41M / -31.56% / Cal 24.12)
    ("V55_Final",   None, 0.50, 0.00, 0.00, 3e-4, 0,    0.55, 30),
    # Best Calmar ($1.30M / -29.46% / Cal 25.13)
    ("V55_Calmar",  10,   0.50, 0.25, 2.00, 1e-4, 0,    0.55, 30),
    # Best sub-25% MaxDD ($540K / -23.41% / Cal 23.40)
    ("V55_LowDD",   10,   0.50, 0.25, 0.00, 3e-4, 500,  0.00, 0),
    # v54 baseline ($953K / -28.97% / Cal 23.02) — sanity
    ("V54_Base",    None, 0.50, 0.00, 0.00, 0.0,  0,    0.55, 30),
]

# ── Y-schedule grid ──────────────────────────────────────────────────────────
# (label, dd_soft, dd_stop, y_floor)
Y_SCHEDULES = [
    ("v55_default",   0.05, 0.20, 0.25),  # current — baseline
    ("floor_10",      0.05, 0.20, 0.10),  # floor down
    ("floor_00",      0.05, 0.20, 0.00),  # hard stop at -20%
    ("mid",           0.04, 0.15, 0.10),  # tighter mid
    ("hard_12",       0.03, 0.12, 0.00),  # hard stop at -12%
    ("hard_15",       0.03, 0.15, 0.00),  # hard stop at -15%
    ("hard_18",       0.04, 0.18, 0.00),  # hard stop at -18%
    ("aggressive_10", 0.02, 0.10, 0.00),  # very tight
    ("loose",         0.05, 0.25, 0.30),  # looser (control)
]

# ── DD source for Y throttle ─────────────────────────────────────────────────
DD_SOURCES = ["aty", "cb", "max"]


def simulate_y(
    unit_series: pd.Series,
    ode_log: pd.DataFrame,
    K_normal: float,
    cb_halt: float,
    cb_resume: float,
    cb_window_d: int,
    *,
    omega_a: float,
    curv_b: float,
    admiss_c: float,
    psi_star: float,
    g24_eta: float,
    g24_lock_min: int,
    g24_rank_Ix: int,
    release_thr: float,
    release_ext: int,
    # Y-throttle params
    dd_soft: float,
    dd_stop: float,
    y_floor: float,
    dd_source: str,
):
    window_bars = cb_window_d * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq, peak_alltime = INIT, INIT
    halted = False
    halt_start_bar = 0
    extend_counter = 0
    n_blocked = 0
    n_g24_releases = 0

    unit  = unit_series.values
    ode   = ode_log.reindex(unit_series.index, method="ffill").fillna(0.0)
    rhs_v = ode["rhs_norm"].values
    gma_v = ode["gamma"].values

    c_sigma_bar = c_sigma_per_bar(g24_eta, g24_rank_Ix) if g24_eta > 0 else 0.0

    eq_vals = []

    for i in range(len(unit)):
        ur = float(unit[i])
        while mono_dq and mono_dq[0][0] <= i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((i, eq))
        roll_peak = mono_dq[0][1]
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak, 1e-12))
        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))

        if extend_counter > 0:
            extend_counter -= 1
            if extend_counter == 0:
                halted = False
        elif not halted:
            if cb_dd >= cb_halt:
                halted = True
                halt_start_bar = i
        else:
            lock_bars = i - halt_start_bar
            standard_resume = (cb_dd <= cb_resume)
            g24_resume = (
                c_sigma_bar > 0.0
                and lock_bars >= g24_lock_min
                and cb_dd <= cb_resume + c_sigma_bar * lock_bars
            )
            if standard_resume or g24_resume:
                rhs_now = float(rhs_v[i])
                if release_thr > 0.0 and rhs_now > release_thr:
                    extend_counter = release_ext
                    n_blocked += 1
                else:
                    halted = False
                    if g24_resume and not standard_resume:
                        n_g24_releases += 1

        is_halted = halted or (extend_counter > 0)

        # Pick DD source for Y throttle
        if dd_source == "aty":
            dd_for_y = dd_aty
        elif dd_source == "cb":
            dd_for_y = cb_dd
        else:  # 'max'
            dd_for_y = max(dd_aty, cb_dd)

        if is_halted:
            y = 0.0
        elif dd_for_y <= dd_soft:
            y = 1.0
        elif dd_for_y >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_for_y) / (dd_stop - dd_soft)

        rhs_now = float(rhs_v[i])
        gma_now = float(gma_v[i])
        k_mult = 1.0
        if omega_a > 0.0:
            k_mult /= (1.0 + omega_a * max(gma_now * rhs_now, 0.0))
        if curv_b > 0.0:
            k_mult /= (1.0 + curv_b * max(rhs_now, 0.0))
        if admiss_c > 0.0 and psi_star > 0.0:
            brake = min(1.0, admiss_c * psi_star / (rhs_now + EPS_RHS))
            k_mult *= brake

        r = max(K_normal * y * k_mult * ur, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq)

    return dict(
        eq=pd.Series(eq_vals, index=unit_series.index),
        n_blocked=n_blocked,
        n_g24_releases=n_g24_releases,
    )


def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)

    print(BAR)
    print("  v56 — ADAPTIVE-Y FIX on v55 winner stacks")
    print(f"  Stacks tested        : {[s[0] for s in STACKS]}")
    print(f"  Y schedules          : {[s[0] for s in Y_SCHEDULES]}")
    print(f"  DD sources           : {DD_SOURCES}")
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

    Sigma_base, _, sdiag, bdiag = build_sigma(factor_R, train_mask, df, D_CHAMP)

    # Build per-kappa_max geometries (dedup)
    kappa_set = sorted({s[1] for s in STACKS}, key=lambda x: (x is None, x))
    geom_specs = {}
    for kappa_max in kappa_set:
        if kappa_max is None:
            Sigma_g7 = Sigma_base
            lam_g7 = 0.0
        else:
            Sigma_g7, lam_g7 = regularise_sigma_g7(Sigma_base, float(kappa_max))
        theta_g7 = theta_from(b_aligned, train_mask, Sigma_g7, bdiag["budget"], Q_CHAMP)
        psi_star = compute_psi_star(Sigma_g7, theta_g7, b_aligned, train_mask)
        _, rank_Ix = fisher_weight_noise_sqrt(Sigma_g7)
        kp_lbl = "None" if kappa_max is None else str(kappa_max)
        print(f"  G7 kappa_max={kp_lbl:<5}  lam_g7={lam_g7:.4e}  theta={theta_g7:.4f}  "
              f"Psi*={psi_star:.4e}  rank(I_X)={rank_Ix}")
        log_ann, unit = build_unit_for_sigma(df, train_mask, w_star, b_aligned,
                                             Sigma_g7, theta_g7, ch, ohlc_map)
        geom_specs[kp_lbl] = dict(
            Sigma=Sigma_g7, theta=theta_g7, lam_g7=lam_g7,
            psi_star=psi_star, rank_Ix=rank_Ix,
            log_ann=log_ann, unit=unit,
        )

    rows = []

    print("\n[Sweep] stack x y_schedule x dd_source")
    print(f"\n  {'stack':<11} {'sched':<14} {'src':<4} {'dd_s':>5} {'dd_p':>5} {'y_fl':>5} "
          f"{'final':>11} {'maxdd':>8} {'calmar':>7} {'sharpe':>7}")
    print("  " + "-" * 100)

    for (stk_lbl, kp, omega_a, curv_b, admiss_c, g24_eta, g24_lm, rel_thr, rel_d) in STACKS:
        kp_lbl = "None" if kp is None else str(kp)
        spec = geom_specs[kp_lbl]
        for (y_lbl, dd_s, dd_p, y_fl) in Y_SCHEDULES:
            for src in DD_SOURCES:
                sim = simulate_y(
                    spec["unit"], spec["log_ann"], K_NORMAL, CB_HALT, CB_RESUME, CB_WINDOW_D,
                    omega_a=omega_a, curv_b=curv_b, admiss_c=admiss_c,
                    psi_star=spec["psi_star"],
                    g24_eta=g24_eta, g24_lock_min=g24_lm,
                    g24_rank_Ix=spec["rank_Ix"],
                    release_thr=rel_thr, release_ext=rel_d * HOURS_PER_DAY,
                    dd_soft=dd_s, dd_stop=dd_p, y_floor=y_fl, dd_source=src,
                )
                eq_test = sim["eq"][sim["eq"].index >= test_ts]
                m = equity_metrics(eq_test, "v56")
                row = dict(
                    stack=stk_lbl, kappa_max=kp_lbl,
                    omega_a=omega_a, curv_b=curv_b, admiss_c=admiss_c,
                    g24_eta=g24_eta, g24_lock_min=g24_lm,
                    release_thr=rel_thr, release_ext_days=rel_d,
                    y_schedule=y_lbl, dd_soft=dd_s, dd_stop=dd_p, y_floor=y_fl,
                    dd_source=src,
                    n_blocked=sim["n_blocked"], n_g24=sim["n_g24_releases"],
                    final=m["final"], profit=m["final"] - INIT,
                    maxdd=m["maxdd"], calmar=m["calmar"], sharpe=m["sharpe"],
                )
                rows.append(row)
                mark = ""
                if m["final"] > 900_000 and m["maxdd"] > -0.25:
                    mark = "  ★★ BIG WIN"
                elif m["final"] > 700_000 and m["maxdd"] > -0.25:
                    mark = "  ★ TARGET"
                elif m["final"] > 500_000 and m["maxdd"] > -0.20:
                    mark = "  ◉ deep brake"
                print(f"  {stk_lbl:<11} {y_lbl:<14} {src:<4} {dd_s:>5.2f} {dd_p:>5.2f} {y_fl:>5.2f} "
                      f"${m['final']:>10,.0f} {m['maxdd']:>8.2%} {m['calmar']:>7.2f} {m['sharpe']:>7.2f}{mark}")

    res = pd.DataFrame(rows)
    res.to_csv(OUT / "sweep_results.csv", index=False)

    # ── Summaries ───────────────────────────────────────────────────────
    print("\n" + BAR)
    print("[Summary]")

    def show_top(label, df_sub, sort_by, ascending):
        if df_sub.empty:
            print(f"\n  {label}: (none)")
            return
        top = df_sub.sort_values(sort_by, ascending=ascending).head(10)
        print(f"\n  {label}:")
        for _, r in top.iterrows():
            print(f"    [{r['stack']:<11}] {r['y_schedule']:<14} src={r['dd_source']:<4} "
                  f"(soft={r['dd_soft']:.2f}, stop={r['dd_stop']:.2f}, floor={r['y_floor']:.2f})  "
                  f"Final=${r['final']:>10,.0f}  MaxDD={r['maxdd']:.2%}  Cal={r['calmar']:.2f}  Sh={r['sharpe']:.3f}")

    show_top("Top 10 by Calmar", res, "calmar", ascending=False)
    show_top("Top 10 by Final",  res, "final",  ascending=False)
    feasible = res[(res["final"] > 700_000)]
    show_top("Top 10 by MaxDD (Final>$700K)", feasible, "maxdd", ascending=False)
    big_win = res[(res["final"] > 900_000) & (res["maxdd"] > -0.25)]
    show_top("BIG WIN cells (Final>$900K AND MaxDD>-25%)", big_win, "calmar", ascending=False)
    target = res[(res["final"] > 700_000) & (res["maxdd"] > -0.25)]
    show_top("TARGET cells (Final>$700K AND MaxDD>-25%)", target, "final", ascending=False)

    json.dump({
        "version": "v56",
        "focus": "adaptive_y_fix_on_v55_winners",
        "stacks": [list(s) for s in STACKS],
        "y_schedules": [list(s) for s in Y_SCHEDULES],
        "dd_sources": DD_SOURCES,
        "results": res.to_dict(orient="records"),
    }, open(OUT / "v56_results.json", "w"), default=str, indent=2)

    print(f"\n  -> saved: {OUT / 'sweep_results.csv'}")
    print(f"  -> saved: {OUT / 'v56_results.json'}")
    print(f"  total rows: {len(rows)}")
    print(f"  elapsed = {time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
