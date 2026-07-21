# -*- coding: utf-8 -*-
"""
v55_730k_robust_full.py
=======================

Robustness sweep on the TRUE $730K champion algorithm.

Locked baseline:
  d=0.50, q=0.65, CB halt=8%, resume=4%, window=90d
  v35 cell: d0p5_q0p65_w090_r04
  v54 best: $953,748 / -28.97% / Cal 23.02 (omega a=0.5, rhs filter 0.55/30d)

v55 stacks the remaining canonical mechanisms onto that cell:

  M1. G7 covariance regularisation
        Sigma <- Sigma + lambda*·I  with kappa_max in {None, 20, 10, 5}
  M2. G2.4 stochastic CB override (release smoothing)
        c_sigma = eta · DT · rank(I_X);  release if cb_dd <= cb_resume + c_sigma·lock_bars
        Composes with the rhs release filter (BOTH must allow).
  M3. Admissibility brake (pre-trade leverage cap)
        Psi* ~= sigma * theta * mu_G / sqrt(M_G)
        K_t <- K_t · min(1, c_admiss · Psi* / (rhs_norm + eps))
  M4. Curvature / Hessian sizing (proxy)
        K_t <- K_t / (1 + b_curv · rhs_norm)
  M5. Soft omega sizing (already proven)
        K_t <- K_t / (1 + a_omega · gamma · rhs_norm)
  M6. rhs release filter (already proven from v53/v54)
        on release, if rhs_now > release_thr  =>  extend halt by release_ext bars

Mechanisms M3..M6 layer multiplicatively at simulation time.
M1 changes the geometry, so each kappa_max is a fresh ODE run.

Phased sweep:
  Phase A (4 cells)  : per-kappa_max baselines reproducing v54-style sizing
  Phase B (full)     : G7 x admiss x curvature x omega x rhs-filter x G2.4 (pruned grids)

Verification gate: the (kappa_max=None, omega=0.5, rhs filter on, others off)
cell must reproduce v54 best within $5K and 0.5% MaxDD.

Goal:
  Push MaxDD above (i.e. closer to zero) -25% while keeping Final > $700K,
  ideally > $900K.  No expansion of the champion CB envelope.
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
from simulate_master_strategy import (
    DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, INIT, HOURS_PER_DAY, equity_metrics,
)
from run_crypto_godmode_v35_top5_cb_transition import REG_VARIANT, K_NORMAL, RT_BPS, build_sigma, theta_from
from run_crypto_godmode_v38_ito_tightcb import (
    regularise_sigma_g7, fisher_weight_noise_sqrt, c_sigma_per_bar,
)
from v49_mode1_feature_search import run_ode

BAR = "=" * 112
OUT = Path(OUT_DIR) / "v55_730k_robust_full"

# ── Locked champion baseline ────────────────────────────────────────────────
D_CHAMP    = 0.50
Q_CHAMP    = 0.65
CB_HALT    = 0.08
CB_RESUME  = 0.04
CB_WINDOW_D = 90

# ── M1. G7 grid (None = no regularisation) ──────────────────────────────────
KAPPA_MAX_GRID = [None, 20, 10, 5]

# ── M2. G2.4 (eta, lock_min) ────────────────────────────────────────────────
G24_GRID = [
    (0.0,    0),    # off
    (1e-4,   0),    # mild
    (1e-4,   500),  # mild + lock_min
    (3e-4,   0),    # stronger
    (3e-4,   500),
]

# ── M3. Admissibility brake constant ────────────────────────────────────────
ADMISS_GRID = [0.0, 1.0, 2.0]

# ── M4. Curvature proxy (rhs_norm) ──────────────────────────────────────────
CURV_GRID = [0.0, 0.25, 0.50]

# ── M5. Soft omega (already proven) ─────────────────────────────────────────
OMEGA_GRID = [0.0, 0.50]

# ── M6. rhs release filter ──────────────────────────────────────────────────
RELEASE_FILTERS = [
    (0.0,  0),         # off
    (0.55, 30 * HOURS_PER_DAY),   # v53/v54 best
]

EPS_RHS = 1e-6


# ── Admissibility helpers ───────────────────────────────────────────────────

def compute_psi_star(Sigma: np.ndarray, theta: float, b_arr: np.ndarray, train_mask: np.ndarray) -> float:
    """Psi* ≈ sigma · theta · mu_G / sqrt(M_G).

    sigma : rolling std of S(0)=−b_t over training mask (proxy for residual std)
    G     : Sigma^{-1}; mu_G = mean eig(G); M_G = max eig(G)
    """
    G = np.linalg.inv(Sigma)
    eig_G = np.linalg.eigvalsh(G)
    mu_G  = float(np.mean(eig_G))
    M_G   = float(np.max(eig_G))
    # Residual S(0) = A·0 - b = -b; use its norm std on training rows
    if b_arr.ndim == 2:
        s_norm = np.linalg.norm(b_arr[train_mask], axis=1)
    else:
        s_norm = np.abs(b_arr[train_mask])
    sigma_res = float(np.std(s_norm)) + 1e-9
    return sigma_res * theta * mu_G / np.sqrt(max(M_G, 1e-12))


# ── Simulation with stacked mechanisms ──────────────────────────────────────

def simulate_robust(
    unit_series: pd.Series,
    ode_log: pd.DataFrame,
    K_normal: float,
    cb_halt: float,
    cb_resume: float,
    cb_window_d: int,
    *,
    omega_a: float = 0.0,
    curv_b: float = 0.0,
    admiss_c: float = 0.0,
    psi_star: float = 0.0,
    g24_eta: float = 0.0,
    g24_lock_min: int = 0,
    g24_rank_Ix: int = 0,
    release_thr: float = 0.0,
    release_ext: int = 0,
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
    k_mult_vals = []
    halted_vals = []

    for i in range(len(unit)):
        ur = float(unit[i])
        # rolling peak
        while mono_dq and mono_dq[0][0] <= i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((i, eq))
        roll_peak = mono_dq[0][1]
        cb_dd = max(0.0, 1.0 - eq / max(roll_peak, 1e-12))
        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))

        # Halt / release logic
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

        # Stack sizing: omega · curvature · admissibility
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
        k_mult_vals.append(k_mult)
        halted_vals.append(int(is_halted))

    return dict(
        eq=pd.Series(eq_vals, index=unit_series.index),
        k_mult=pd.Series(k_mult_vals, index=unit_series.index),
        cb=pd.Series(halted_vals, index=unit_series.index),
        n_blocked=n_blocked,
        n_g24_releases=n_g24_releases,
    )


def build_unit_for_sigma(df, train_mask, w_star, b_aligned, Sigma, theta, ch, ohlc_map):
    log_ann, _ = run_ode(df, train_mask, w_star, b_aligned, Sigma, theta)
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                     signal_kind="wstar", use_quadrant=False)
    inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
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
    print("  v55 — TRUE $730K CHAMPION + ROBUST FULL-STACK MECHANISMS")
    print(f"  Locked: d={D_CHAMP}, q={Q_CHAMP}, CB={CB_WINDOW_D}d/{int(CB_HALT*100)}-{int(CB_RESUME*100)}%")
    print(f"  M1 G7 kappa_max grid : {KAPPA_MAX_GRID}")
    print(f"  M2 G2.4 (eta,lock)   : {G24_GRID}")
    print(f"  M3 admiss c grid     : {ADMISS_GRID}")
    print(f"  M4 curvature b grid  : {CURV_GRID}")
    print(f"  M5 omega a grid      : {OMEGA_GRID}")
    print(f"  M6 release filters   : {RELEASE_FILTERS}")
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

    # Champion Sigma (no G7); kappa_max=None means "use champion as-is"
    Sigma_base, _, sdiag, bdiag = build_sigma(factor_R, train_mask, df, D_CHAMP)

    # Build per-kappa_max geometries
    geom_specs = []
    for kappa_max in KAPPA_MAX_GRID:
        if kappa_max is None:
            Sigma_g7 = Sigma_base
            lam_g7 = 0.0
        else:
            Sigma_g7, lam_g7 = regularise_sigma_g7(Sigma_base, float(kappa_max))
        theta_g7 = theta_from(b_aligned, train_mask, Sigma_g7, bdiag["budget"], Q_CHAMP)
        psi_star = compute_psi_star(Sigma_g7, theta_g7, b_aligned, train_mask)
        # rank(I_X) for G2.4
        _, rank_Ix = fisher_weight_noise_sqrt(Sigma_g7)
        geom_specs.append(dict(
            kappa_max=kappa_max, Sigma=Sigma_g7, theta=theta_g7,
            lam_g7=lam_g7, psi_star=psi_star, rank_Ix=rank_Ix,
        ))
        kp_lbl = "None" if kappa_max is None else str(kappa_max)
        print(f"  G7 kappa_max={kp_lbl:<5}  lam_g7={lam_g7:.4e}  theta={theta_g7:.4f}  "
              f"Psi*={psi_star:.4e}  rank(I_X)={rank_Ix}")

    rows = []

    # ── Phase A: per-G7 baseline reproductions (mirrors v54-best cell) ───
    print("\n[Phase A] Baseline reproduction per G7 level (omega=0.5, rhs filter on, others off)")
    print(f"\n  {'kappa':<6} {'theta':>7} {'blk':>4} {'final':>11} {'maxdd':>8} {'calmar':>7} {'sharpe':>7}")
    print("  " + "-" * 70)

    geom_unit_cache = {}
    for spec in geom_specs:
        kp_lbl = "None" if spec["kappa_max"] is None else str(spec["kappa_max"])
        print(f"\n  [Phase A] kappa_max={kp_lbl}: running ODE ...")
        log_ann, unit = build_unit_for_sigma(df, train_mask, w_star, b_aligned,
                                             spec["Sigma"], spec["theta"], ch, ohlc_map)
        geom_unit_cache[kp_lbl] = (log_ann, unit)

        sim = simulate_robust(
            unit, log_ann, K_NORMAL, CB_HALT, CB_RESUME, CB_WINDOW_D,
            omega_a=0.5, curv_b=0.0, admiss_c=0.0, psi_star=spec["psi_star"],
            g24_eta=0.0, g24_lock_min=0, g24_rank_Ix=spec["rank_Ix"],
            release_thr=0.55, release_ext=30 * HOURS_PER_DAY,
        )
        eq_test = sim["eq"][sim["eq"].index >= test_ts]
        m = equity_metrics(eq_test, f"phaseA_kappa{kp_lbl}")
        row = dict(
            phase="A", kappa_max=kp_lbl, theta=spec["theta"], lam_g7=spec["lam_g7"],
            psi_star=spec["psi_star"], rank_Ix=spec["rank_Ix"],
            omega_a=0.5, curv_b=0.0, admiss_c=0.0,
            g24_eta=0.0, g24_lock_min=0, release_thr=0.55, release_ext_days=30,
            n_blocked=sim["n_blocked"], n_g24=sim["n_g24_releases"],
            final=m["final"], profit=m["final"] - INIT,
            maxdd=m["maxdd"], calmar=m["calmar"], sharpe=m["sharpe"],
            mean_k_mult=float(sim["k_mult"].mean()),
        )
        rows.append(row)
        print(f"  {kp_lbl:<6} {spec['theta']:>7.4f} {sim['n_blocked']:>4} "
              f"${m['final']:>10,.0f} {m['maxdd']:>8.2%} {m['calmar']:>7.2f} {m['sharpe']:>7.2f}")

    # Verification gate
    base_row = next(r for r in rows if r["kappa_max"] == "None")
    if abs(base_row["final"] - 953_748.0) > 5_000.0 or abs(base_row["maxdd"] - (-0.2897)) > 0.005:
        print("\n  WARN: Phase A baseline does NOT reproduce v54 best within tolerance.")
        print(f"        got Final=${base_row['final']:,.0f}  MaxDD={base_row['maxdd']:.2%}")
        print(f"        expected ~$953,748 / -28.97%")
    else:
        print(f"\n  Phase A baseline reproduces v54 best (Final=${base_row['final']:,.0f}, MaxDD={base_row['maxdd']:.2%}). Gate PASS.")

    # ── Phase B: full stack sweep ───────────────────────────────────────
    print("\n[Phase B] Full stack sweep (G7 x admiss x curvature x omega x rhs x G2.4)")
    print(f"\n  {'kp':<5} {'om':>5} {'cv':>5} {'ad':>5} {'rel':>9} {'g24':>14} {'blk':>4} {'g24r':>5} "
          f"{'final':>11} {'maxdd':>8} {'calmar':>7} {'sharpe':>7}")
    print("  " + "-" * 110)

    for spec in geom_specs:
        kp_lbl = "None" if spec["kappa_max"] is None else str(spec["kappa_max"])
        log_ann, unit = geom_unit_cache[kp_lbl]
        for omega_a in OMEGA_GRID:
            for curv_b in CURV_GRID:
                for admiss_c in ADMISS_GRID:
                    for rel_thr, rel_ext in RELEASE_FILTERS:
                        for g24_eta, g24_lm in G24_GRID:
                            sim = simulate_robust(
                                unit, log_ann, K_NORMAL, CB_HALT, CB_RESUME, CB_WINDOW_D,
                                omega_a=omega_a, curv_b=curv_b, admiss_c=admiss_c,
                                psi_star=spec["psi_star"],
                                g24_eta=g24_eta, g24_lock_min=g24_lm,
                                g24_rank_Ix=spec["rank_Ix"],
                                release_thr=rel_thr, release_ext=rel_ext,
                            )
                            eq_test = sim["eq"][sim["eq"].index >= test_ts]
                            m = equity_metrics(eq_test, "phaseB")
                            row = dict(
                                phase="B", kappa_max=kp_lbl, theta=spec["theta"],
                                lam_g7=spec["lam_g7"], psi_star=spec["psi_star"], rank_Ix=spec["rank_Ix"],
                                omega_a=omega_a, curv_b=curv_b, admiss_c=admiss_c,
                                g24_eta=g24_eta, g24_lock_min=g24_lm,
                                release_thr=rel_thr, release_ext_days=rel_ext // HOURS_PER_DAY,
                                n_blocked=sim["n_blocked"], n_g24=sim["n_g24_releases"],
                                final=m["final"], profit=m["final"] - INIT,
                                maxdd=m["maxdd"], calmar=m["calmar"], sharpe=m["sharpe"],
                                mean_k_mult=float(sim["k_mult"].mean()),
                            )
                            rows.append(row)
                            mark = ""
                            if m["final"] > 900_000 and m["maxdd"] > -0.25:
                                mark = "  ★★ BIG WIN"
                            elif m["final"] > 700_000 and m["maxdd"] > -0.25:
                                mark = "  ★ TARGET"
                            elif m["final"] > 700_000 and m["maxdd"] > -0.2897:
                                mark = "  ◉ beats v54 DD"
                            rel_lbl = "off" if rel_thr <= 0 else f"r{rel_thr:.2f}/{rel_ext//HOURS_PER_DAY}d"
                            g24_lbl = "off" if g24_eta <= 0 else f"e{g24_eta:.0e}_l{g24_lm}"
                            print(f"  {kp_lbl:<5} {omega_a:>5.2f} {curv_b:>5.2f} {admiss_c:>5.2f} "
                                  f"{rel_lbl:>9} {g24_lbl:>14} {sim['n_blocked']:>4} "
                                  f"{sim['n_g24_releases']:>5} ${m['final']:>10,.0f} "
                                  f"{m['maxdd']:>8.2%} {m['calmar']:>7.2f} {m['sharpe']:>7.2f}{mark}")

    res = pd.DataFrame(rows)
    res.to_csv(OUT / "sweep_results.csv", index=False)

    # ── Summaries ───────────────────────────────────────────────────────
    print("\n" + BAR)
    print("[Summary]")

    def show_top(label, df_sub, sort_by, ascending):
        if df_sub.empty:
            print(f"\n  {label}: (none)")
            return
        top = df_sub.sort_values(sort_by, ascending=ascending).head(8)
        print(f"\n  {label}:")
        for _, r in top.iterrows():
            print(f"    kp={r['kappa_max']:<5} om={r['omega_a']:.2f} cv={r['curv_b']:.2f} "
                  f"ad={r['admiss_c']:.2f} g24=e{r['g24_eta']:.0e}/l{int(r['g24_lock_min'])} "
                  f"rel={r['release_thr']:.2f}/{int(r['release_ext_days'])}d  "
                  f"Final=${r['final']:>10,.0f}  MaxDD={r['maxdd']:.2%}  Cal={r['calmar']:.2f}  Sh={r['sharpe']:.3f}")

    show_top("Top 8 by Calmar", res, "calmar", ascending=False)
    show_top("Top 8 by Final",  res, "final",  ascending=False)
    feasible = res[(res["final"] > 700_000)]
    show_top("Top 8 by MaxDD (Final>$700K)", feasible, "maxdd", ascending=False)
    big_win = res[(res["final"] > 900_000) & (res["maxdd"] > -0.25)]
    show_top("BIG WIN cells (Final>$900K AND MaxDD>-25%)", big_win, "calmar", ascending=False)

    json.dump({
        "version": "v55",
        "focus": "true_730k_champion_robust_full_stack",
        "baseline": {"d": D_CHAMP, "q": Q_CHAMP, "cb_halt": CB_HALT,
                     "cb_resume": CB_RESUME, "cb_window_d": CB_WINDOW_D},
        "kappa_max_grid": [str(k) for k in KAPPA_MAX_GRID],
        "g24_grid": G24_GRID,
        "admiss_grid": ADMISS_GRID,
        "curv_grid": CURV_GRID,
        "omega_grid": OMEGA_GRID,
        "release_filters": RELEASE_FILTERS,
        "results": res.to_dict(orient="records"),
    }, open(OUT / "v55_results.json", "w"), indent=2, default=str)

    print(f"\n  → saved: {OUT / 'sweep_results.csv'}")
    print(f"  → saved: {OUT / 'v55_results.json'}")
    print(f"  total rows: {len(res)}")
    print(f"  elapsed = {time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
