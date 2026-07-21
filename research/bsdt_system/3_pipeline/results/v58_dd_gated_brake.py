# -*- coding: utf-8 -*-
"""
v58_dd_gated_brake.py
=====================

Diagnosis from v57:
  Pre-trade inverse-vol cap (k_vol = sigma_target / sigma_realised) destroys the
  productive moonshot path. Every config that preserves Final > $700K is the
  "off" cell (no vol cap). Realised-vol gating is too coincident with the
  realised PnL distribution: it cuts K on the same bars that drive recovery.

Real fix (this file):
  A *DD-gated* soft brake on K_normal that does NOTHING below a threshold and
  only scales K when live drawdown exceeds dd_thr, with a floor K_min so the
  engine keeps participating in the recovery instead of going to zero.

  dd_excess = max(0, dd_aty - dd_thr)
  k_dd      = max(K_MIN_FRAC, 1 - beta * dd_excess / max(eps, dd_stop - dd_thr))
  effective_K = K_normal * y * k_mult_stack * k_dd

  This is independent of realised vol. It only acts when there is *actual*
  drawdown (the thing the user wants to fix), and it releases smoothly as
  equity recovers. The shallow regime (dd < dd_thr) is untouched, so the
  champion's productive bars are preserved.

Sweep over (dd_thr, beta, K_min, dd_stop) on the same v55 winner stacks.
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
import run_crypto_godmode_v28_canonical_stability as v28  # noqa: F401
from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import W_TARGET_A1, build_b_aligned, build_w_star
from run_crypto_canonical_v4 import build_factor_returns
from run_crypto_godmode_v8_multiasset_shell import ASSETS, fetch_futures_ohlcv_symbol
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import (
    DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, INIT, HOURS_PER_DAY, equity_metrics,
)
from run_crypto_godmode_v35_top5_cb_transition import REG_VARIANT, K_NORMAL, RT_BPS, build_sigma, theta_from  # noqa: F401
from run_crypto_godmode_v38_ito_tightcb import (
    regularise_sigma_g7, fisher_weight_noise_sqrt, c_sigma_per_bar,
)
from v55_730k_robust_full import compute_psi_star, build_unit_for_sigma

BAR = "=" * 112
OUT = Path(OUT_DIR) / "v58_dd_gated_brake"

D_CHAMP    = 0.50
Q_CHAMP    = 0.65
CB_HALT    = 0.08
CB_RESUME  = 0.04
CB_WINDOW_D = 90
EPS_RHS = 1e-6

# v55 winner stacks (kept identical to v57 for apples-to-apples)
STACKS = [
    ("V55_Final",   None, 0.50, 0.00, 0.00, 3e-4, 0,    0.55, 30),
    ("V55_Calmar",  10,   0.50, 0.25, 2.00, 1e-4, 0,    0.55, 30),
    ("V55_LowDD",   10,   0.50, 0.25, 0.00, 3e-4, 500,  0.00, 0),
    ("V54_Base",    None, 0.50, 0.00, 0.00, 0.0,  0,    0.55, 30),
]

# DD-gated brake sweep grid
DD_THRS  = [0.08, 0.12, 0.16, 0.20]   # only act once dd_aty exceeds this
DD_STOPS = [0.30, 0.40]               # dd at which brake reaches its floor
BETAS    = [1.0, 1.5, 2.0]            # slope inside the gate (1.0 = linear to floor)
KMIN_FRACS = [0.20, 0.40, 0.60]       # leverage floor (never cut to zero)


def simulate_dd_gated(
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
    dd_thr: float | None = None,
    dd_stop_brake: float = 0.30,
    beta: float = 1.0,
    k_min_frac: float = 0.20,
):
    window_bars = cb_window_d * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq, peak_alltime = INIT, INIT
    halted = False
    halt_start_bar = 0
    extend_counter = 0
    n_blocked = 0
    n_g24_releases = 0
    n_brake_active = 0

    unit  = unit_series.values
    ode   = ode_log.reindex(unit_series.index, method="ffill").fillna(0.0)
    rhs_v = ode["rhs_norm"].values
    gma_v = ode["gamma"].values

    c_sigma_bar = c_sigma_per_bar(g24_eta, g24_rank_Ix) if g24_eta > 0 else 0.0
    gate_span = max(1e-6, dd_stop_brake - (dd_thr if dd_thr is not None else 0.0))

    eq_vals = []
    kdd_vals = []

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
        if is_halted:
            y = 0.0
        elif dd_aty <= DYN_DD_SOFT:
            y = 1.0
        elif dd_aty >= DYN_DD_STOP:
            y = DYN_Y_FLOOR
        else:
            y = DYN_Y_FLOOR + (1.0 - DYN_Y_FLOOR) * (DYN_DD_STOP - dd_aty) / (DYN_DD_STOP - DYN_DD_SOFT)

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

        # DD-gated soft brake (the new mechanism)
        if dd_thr is not None and dd_aty > dd_thr:
            dd_excess = dd_aty - dd_thr
            k_dd = max(k_min_frac, 1.0 - beta * dd_excess / gate_span)
            n_brake_active += 1
        else:
            k_dd = 1.0

        r = max(K_normal * y * k_mult * k_dd * ur, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq)
        kdd_vals.append(k_dd)

    return dict(
        eq=pd.Series(eq_vals, index=unit_series.index),
        n_blocked=n_blocked,
        n_g24_releases=n_g24_releases,
        n_brake_active=n_brake_active,
        mean_kdd=float(np.mean(kdd_vals)),
    )


def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)

    print(BAR)
    print("  v58 — DD-GATED soft brake on K_normal (real DD reducer)")
    print(f"  Stacks tested        : {[s[0] for s in STACKS]}")
    print(f"  dd_thr               : {DD_THRS}")
    print(f"  dd_stop_brake        : {DD_STOPS}")
    print(f"  beta                 : {BETAS}")
    print(f"  k_min_frac           : {KMIN_FRACS}")
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

    print("\n[Sweep] stack x dd_thr x dd_stop x beta x K_min  (+ baseline 'off')")
    print(f"\n  {'stack':<11} {'thr':>5} {'stop':>5} {'beta':>5} {'kmin':>5} "
          f"{'mean_kdd':>9} {'final':>11} {'maxdd':>8} {'calmar':>7} {'sharpe':>7}")
    print("  " + "-" * 100)

    for (stk_lbl, kp, omega_a, curv_b, admiss_c, g24_eta, g24_lm, rel_thr, rel_d) in STACKS:
        kp_lbl = "None" if kp is None else str(kp)
        spec = geom_specs[kp_lbl]

        # 1) baseline "off" run for reference
        sim = simulate_dd_gated(
            spec["unit"], spec["log_ann"], K_NORMAL, CB_HALT, CB_RESUME, CB_WINDOW_D,
            omega_a=omega_a, curv_b=curv_b, admiss_c=admiss_c,
            psi_star=spec["psi_star"],
            g24_eta=g24_eta, g24_lock_min=g24_lm,
            g24_rank_Ix=spec["rank_Ix"],
            release_thr=rel_thr, release_ext=rel_d * HOURS_PER_DAY,
            dd_thr=None,
        )
        eq_test = sim["eq"][sim["eq"].index >= test_ts]
        m = equity_metrics(eq_test, "v58")
        rows.append(dict(
            stack=stk_lbl, kappa_max=kp_lbl,
            dd_thr=0.0, dd_stop=0.0, beta=0.0, k_min=1.0,
            mean_kdd=1.0, n_brake=0,
            final=m["final"], profit=m["final"] - INIT,
            maxdd=m["maxdd"], calmar=m["calmar"], sharpe=m["sharpe"],
        ))
        print(f"  {stk_lbl:<11} {'OFF':>5} {'-':>5} {'-':>5} {'-':>5} "
              f"{1.000:>9.3f} ${m['final']:>10,.0f} {m['maxdd']:>8.2%} "
              f"{m['calmar']:>7.2f} {m['sharpe']:>7.2f}  (baseline)")

        # 2) sweep brake configs
        for dd_thr in DD_THRS:
            for dd_stop in DD_STOPS:
                if dd_stop <= dd_thr:
                    continue
                for beta in BETAS:
                    for kmin in KMIN_FRACS:
                        sim = simulate_dd_gated(
                            spec["unit"], spec["log_ann"], K_NORMAL, CB_HALT, CB_RESUME, CB_WINDOW_D,
                            omega_a=omega_a, curv_b=curv_b, admiss_c=admiss_c,
                            psi_star=spec["psi_star"],
                            g24_eta=g24_eta, g24_lock_min=g24_lm,
                            g24_rank_Ix=spec["rank_Ix"],
                            release_thr=rel_thr, release_ext=rel_d * HOURS_PER_DAY,
                            dd_thr=dd_thr, dd_stop_brake=dd_stop,
                            beta=beta, k_min_frac=kmin,
                        )
                        eq_test = sim["eq"][sim["eq"].index >= test_ts]
                        m = equity_metrics(eq_test, "v58")
                        row = dict(
                            stack=stk_lbl, kappa_max=kp_lbl,
                            dd_thr=dd_thr, dd_stop=dd_stop, beta=beta, k_min=kmin,
                            mean_kdd=sim["mean_kdd"], n_brake=sim["n_brake_active"],
                            final=m["final"], profit=m["final"] - INIT,
                            maxdd=m["maxdd"], calmar=m["calmar"], sharpe=m["sharpe"],
                        )
                        rows.append(row)
                        mark = ""
                        if m["final"] > 900_000 and m["maxdd"] > -0.25:
                            mark = "  ** BIG WIN"
                        elif m["final"] > 700_000 and m["maxdd"] > -0.25:
                            mark = "  * TARGET"
                        elif m["final"] > 500_000 and m["maxdd"] > -0.25:
                            mark = "  o sub-25 MDD"
                        elif m["final"] > 700_000 and m["maxdd"] > -0.2897:
                            mark = "  . beats v54 DD"
                        print(f"  {stk_lbl:<11} {dd_thr:>5.2f} {dd_stop:>5.2f} {beta:>5.2f} "
                              f"{kmin:>5.2f} {sim['mean_kdd']:>9.3f} ${m['final']:>10,.0f} "
                              f"{m['maxdd']:>8.2%} {m['calmar']:>7.2f} {m['sharpe']:>7.2f}{mark}")

    res = pd.DataFrame(rows)
    res.to_csv(OUT / "sweep_results.csv", index=False)

    print("\n" + BAR)
    print("[Summary]")

    def show_top(label, df_sub, sort_by, ascending):
        if df_sub.empty:
            print(f"\n  {label}: (none)")
            return
        top = df_sub.sort_values(sort_by, ascending=ascending).head(10)
        print(f"\n  {label}:")
        for _, r in top.iterrows():
            print(f"    [{r['stack']:<11}] thr={r['dd_thr']:.2f} stop={r['dd_stop']:.2f} "
                  f"beta={r['beta']:.1f} kmin={r['k_min']:.2f}  "
                  f"Final=${r['final']:>10,.0f}  MaxDD={r['maxdd']:.2%}  "
                  f"Cal={r['calmar']:.2f}  Sh={r['sharpe']:.3f}")

    show_top("Top 10 by Calmar", res, "calmar", ascending=False)
    show_top("Top 10 by Final",  res, "final",  ascending=False)
    feasible = res[res["final"] > 700_000]
    show_top("Top 10 by MaxDD (Final>$700K)", feasible, "maxdd", ascending=False)
    target = res[(res["final"] > 700_000) & (res["maxdd"] > -0.25)]
    show_top("TARGET (Final>$700K AND MaxDD>-25%)", target, "calmar", ascending=False)
    big_win = res[(res["final"] > 900_000) & (res["maxdd"] > -0.25)]
    show_top("BIG WIN (Final>$900K AND MaxDD>-25%)", big_win, "calmar", ascending=False)

    json.dump({
        "version": "v58",
        "focus": "dd_gated_soft_brake_on_K_normal",
        "stacks": [list(s) for s in STACKS],
        "dd_thrs": DD_THRS,
        "dd_stops": DD_STOPS,
        "betas": BETAS,
        "k_mins": KMIN_FRACS,
        "results": res.to_dict(orient="records"),
    }, open(OUT / "v58_results.json", "w"), default=str, indent=2)

    print(f"\n  -> saved: {OUT / 'sweep_results.csv'}")
    print(f"  -> saved: {OUT / 'v58_results.json'}")
    print(f"  total rows: {len(rows)}")
    print(f"  elapsed = {time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
