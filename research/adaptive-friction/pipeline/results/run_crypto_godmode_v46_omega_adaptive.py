# -*- coding: utf-8 -*-
"""
run_crypto_godmode_v46_omega_adaptive.py
=========================================

v46 = v41 + Omega-at-halt Adaptive Window (Correct Application of Mode 1 Filter)

──────────────────────────────────────────────────────────────────────────────
Why the Omega gate fires only OmBlk=4 in v39–v45
──────────────────────────────────────────────────────────────────────────────

  Formula (v38_reversal_geometry.py, derived from segment cluster analysis):
      Ω = γ × ‖f(z)‖  ≥  0.02  →  BLOCK re-entry  (Mode 1 reversal predicted)

  Empirical gap:
      Max WINNER Ω = 0.0063   Min LOSER Ω = 0.0403   Separation = 6.4×
      Threshold θ = 0.020 sits in the middle of the 0.0063–0.0403 gap.
      Zero winning segments blocked. Zero false positives.

  Implementation in v39–v45 (simulate_combined_lockmin_v41):
      At each halted bar where candidate=True (CB would release):
          if gamma[bar_i] * rhs_norm[bar_i] >= 0.02 → block re-entry

  WHY it fires only 4 times in v39–v45:
      In v38, Mode 1 trips were caused by PREMATURE G2.4 releases (linear budget
      overcounted noise → released after only lock_min=500 bars ≈ 21 days, before
      the ODE had converged). At that early release point, Ω was still 0.040+.

      In v39+, Fix 2 (saturating budget) eliminated premature G2.4 releases.
      All 19 staircase re-entries are now STANDARD releases (equity naturally
      recovered to within 4% of the 90d rolling peak). Over 90 days of halt,
      the ODE fully converges → γ≈0, ‖f(z)‖≈0, Ω≈0 at release.

      The Omega gate NEVER SEES high Ω at release because the signal decays to 0
      during the long lockout period. Fix 2 solved the ODE-convergence problem,
      but this removed the early-warning signal that the Omega gate relied on.

──────────────────────────────────────────────────────────────────────────────
v46 Fix: Check Omega at HALT TIME, not release time
──────────────────────────────────────────────────────────────────────────────

  The Mode 1 signal is present at HALT TIME (when the CB fires), not at release.
  At halt time: the ODE was actively fighting a position change → γ and ‖f(z)‖
  may still be elevated, indicating the system entered a reversal while overexcited.

  Adaptive window rule:
      omega_at_halt  =  gamma[halt_bar] × rhs_norm[halt_bar]

      If omega_at_halt ≥ omega_adaptive_thresh (default 0.02):
          → Mode 1 reversal trip detected
          → apply cb_window_mode1 (e.g. 180d) for this trip
          → keeps pre-reversal peak in lookback longer → fewer re-entries into decline

      If omega_at_halt < omega_adaptive_thresh:
          → Normal market correction
          → apply cb_window_normal (e.g. 90d) → fast recovery preserved

  Why this works:
    - v45 showed: 180d window cuts MaxDD from −34.6% → −14% (halves staircase trips)
    - 90d window needed for normal dips (fast recovery preserves final equity)
    - Omega_at_halt distinguishes MODE 1 (ODE overexcited → Mode 1 reversal likely)
      from NORMAL CORRECTION (ODE calm → genuine price recovery expected)
    - Applies the 6.4× Omega gap discriminant at the moment when the signal exists

──────────────────────────────────────────────────────────────────────────────
Grid
────
  omega_adaptive_thresh  : [None, 0.01, 0.02, 0.04]
    → None  = no adaptive window (all trips use cb_window_normal = 90d) [baseline]
    → 0.01  = aggressive: catches more trips as Mode 1
    → 0.02  = exact threshold from v38 derivation (max winner=0.0063, min loser=0.0403)
    → 0.04  = conservative: only catches definitely-Mode-1 (above min loser Omega)

  cb_window_mode1        : [180, 270]  (d)  # extended window for Mode 1 trips
    → 180d  = best result from v45
    → 270d  = extra protection for deep staircases

  cb_window_normal       : 90  (d)  # fixed: standard window for normal trips

  (d,q): TOP3, fixed engine: η=2e-4, lm=500, km=None, existing Ω and ρ gates

  Variants:
    Baseline:   3 (omega_thresh=None, all use 90d window)
    Adaptive:   3 (d,q) × 3 (thresholds) × 2 (mode1 windows) = 18
    Total:      21

Theory references
───────────────────
  Omega formula:      v38_reversal_geometry.py  (6.4× gap, θ=0.02)
  Cluster source:     v38_trade_clustering.py   (38a/38b C0 LOSER)
  Window insight:     v45 results (180d = best MaxDD without destroying returns)
  Mode 1 definition:  C0 LOSER = peaked +4.7%/+5.9% then reversed (skew=-4.4/-5.9)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from collections import deque

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
    ANNEAL_AMP, ANNEAL_PEAK,
    TradingDomain, EPSILON,
)
from run_crypto_canonical_v4 import (
    A_FACTORS, N_STATE, K_FACTOR, DT,
    build_factor_returns, rescale_to_correlation,
)
from run_crypto_godmode_v8_multiasset_shell import (
    ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol,
)
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import (
    DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, INIT, HOURS_PER_DAY,
    equity_metrics, period_table,
)
from run_crypto_godmode_v35_top5_cb_transition import (
    ffd_weights, frac_diff_series, ffd_covariance,
    build_sigma, theta_from,
    TOP5, CB_HALT as CB_HALT_DEFAULT, REG_VARIANT,
    FFD_THRESHOLD, FFD_MAX_LAG, K_NORMAL, RT_BPS, KAPPA_CAP,
)

BAR      = "=" * 120
OUT_DIR_ = Path(OUT_DIR) / "v46_omega_adaptive"
PLOT_DIR = OUT_DIR_ / "plots"

# TOP3 (d,q) — same as v38–v45
TOP3 = [
    (0.30, 0.50),   # rank-1
    (0.30, 0.65),   # rank-2
    (0.25, 0.50),   # rank-3: r2026>0
]

# ── Fixed CB + engine settings ────────────────────────────────────────────────
CB_HALT          = 0.08
CB_RESUME        = 0.04
CB_WINDOW_NORMAL = 90     # days — standard window for non-Mode-1 trips

ETA          = 2e-4
LOCK_MIN     = 500
KAPPA_MAX    = None
OMEGA_THRESH = 0.02   # existing Omega gate at release time (unchanged)
RHO_ALPHA    = 0.5

# ── v46 adaptive window grids ─────────────────────────────────────────────────
# omega_at_halt_threshold: Omega measured at HALT TIME to detect Mode 1 reversal
OMEGA_ADAPTIVE_THRESH_GRID = [None, 0.01, 0.02, 0.04]
#  None = disabled (all trips use CB_WINDOW_NORMAL)
#  0.01 = aggressive (catches more trips)
#  0.02 = derived from v38 cluster gap (max winner=0.0063, min loser=0.0403)
#  0.04 = conservative (barely above min loser 0.0403)

CB_WINDOW_MODE1_GRID = [180, 270]  # days — window for Mode 1 trips


# ── G7 + Fisher helpers ───────────────────────────────────────────────────────

def regularise_sigma_g7(
    Sigma: np.ndarray, kappa_max: float
) -> tuple[np.ndarray, float]:
    eigvals = np.linalg.eigvalsh(Sigma)
    lam_max = float(eigvals[-1])
    lam_min = float(max(eigvals[0], 1e-12))
    if lam_max / lam_min <= kappa_max:
        return Sigma, 0.0
    lam_reg = max((lam_max - kappa_max * lam_min) / (kappa_max - 1.0), 0.0)
    return Sigma + lam_reg * np.eye(Sigma.shape[0]), float(lam_reg)


def fisher_weight_noise_sqrt(
    Sigma_cap: np.ndarray, eps: float = 1e-10
) -> tuple[np.ndarray, int]:
    G        = np.linalg.inv(Sigma_cap)
    I_X      = A_FACTORS.T @ G @ A_FACTORS
    vals, vecs = np.linalg.eigh(I_X)
    rank_Ix  = int(np.sum(vals > eps * vals[-1]))
    inv_sqrt = np.zeros_like(vals)
    for i in range(rank_Ix):
        inv_sqrt[i] = 1.0 / np.sqrt(max(vals[i], eps))
    return vecs @ np.diag(inv_sqrt) @ vecs.T, rank_Ix


def c_sigma_saturating(
    eta: float, rank_Ix: int, rho_typ: float, lock_bars: int
) -> float:
    if eta == 0.0 or rho_typ <= 0.0:
        return 0.0
    E_inf = eta * rank_Ix / rho_typ
    return E_inf * (1.0 - np.exp(-rho_typ * lock_bars * DT))


# ── Deterministic ODE ─────────────────────────────────────────────────────────

def run_godmode_det_v39(
    df, train_mask, test_mask, w_star_arr, b_arr,
    Sigma_cap, theta_base, kappa=KAPPA_A, label="",
) -> tuple[pd.DataFrame, float]:
    T = len(df)
    R = np.column_stack([
        df["ret_btc"].fillna(0.0).values,
        df["ret_eth"].fillna(0.0).values,
        (df["ret_sol"].fillna(0.0).values if "ret_sol" in df.columns
         else df["ret_eth"].fillna(0.0).values),
    ])

    rho_train: list[float] = []
    for t in np.where(train_mask)[0][::50]:
        sys_t = TradingDomain(
            A=A_FACTORS, b=b_arr[t], Sigma=Sigma_cap,
            kappa=kappa, w_star=w_star_arr[t],
            theta=theta_base, epsilon=EPSILON,
        ).build()
        sc = _predictive_scalars(sys_t, np.zeros(N_STATE))
        if sc["rho_eff"] > 0:
            rho_train.append(sc["rho_eff"])
    rho_typ = float(np.median(rho_train)) if rho_train else 1.0

    hours = df.index.hour
    keys = [
        "E", "gamma", "dE_dt", "cos_theta", "mfls", "v_E", "rho_eff",
        "rhs_norm", "w_btc", "w_eth", "w_sol", "pnl", "pnl_long_only",
        "stop_flag", "stale_flag", "drift_flag", "conviction", "theta_t",
    ]
    log = {k: np.zeros(T) for k in keys}
    w           = np.zeros(N_STATE, dtype=float)
    cos_th_prev = 0.0
    t0          = time.time()

    for t in range(T):
        hr      = int(hours[t])
        theta_t = theta_base * (1.0 + ANNEAL_AMP * np.cos(
            2.0 * np.pi * (hr - ANNEAL_PEAK) / 24.0))
        sys_t = TradingDomain(
            A=A_FACTORS, b=b_arr[t], Sigma=Sigma_cap,
            kappa=kappa, w_star=w_star_arr[t],
            theta=theta_t, epsilon=EPSILON,
        ).build()
        sc         = _predictive_scalars(sys_t, w)
        conviction = float(np.clip(-cos_th_prev, CONV_MIN, CONV_MAX))
        w          = np.clip(w + DT * sc["rhs"] * conviction, -W_BOX, W_BOX)

        log["E"][t]             = sc["E"]
        log["gamma"][t]         = sc["gamma"]
        log["dE_dt"][t]         = sc["dE_dt"]
        log["cos_theta"][t]     = sc["cos_theta"]
        log["mfls"][t]          = sc["mfls"]
        log["v_E"][t]           = sc["v_E"]
        log["rho_eff"][t]       = sc["rho_eff"]
        log["rhs_norm"][t]      = sc["rhs_norm"]
        log["w_btc"][t]         = w[0]
        log["w_eth"][t]         = w[1]
        log["w_sol"][t]         = w[2]
        log["pnl"][t]           = float(w @ R[t])
        log["pnl_long_only"][t] = float(R[t].mean())
        log["stop_flag"][t]     = 1.0 if sc["gamma"] > 0.90 else 0.0
        log["stale_flag"][t]    = 1.0 if (sc["rho_eff"] > 0 and sc["rho_eff"] < 0.1 * rho_typ) else 0.0
        log["drift_flag"][t]    = 1.0 if sc["cos_theta"] > 0.0 else 0.0
        log["conviction"][t]    = conviction
        log["theta_t"][t]       = theta_t

        cos_th_prev = sc["cos_theta"]
        if t > 0 and (t % 5000) == 0:
            print(f"    [{label}] {t:>6}/{T}  ({time.time()-t0:.1f}s)")

    return pd.DataFrame(log, index=df.index), rho_typ


# ── v46: Omega-at-halt Adaptive Window CB simulation ─────────────────────────

def simulate_omega_adaptive_v46(
    unit_normal:             pd.Series,
    unit_crash:              pd.Series,
    K_normal:                float,
    K_crash:                 float,
    dd_soft:                 float,
    dd_stop:                 float,
    y_floor:                 float,
    cb_halt:                 float,
    cb_resume:               float,
    cb_window_normal:        int,            # days — standard window
    cb_window_mode1:         int,            # days — Mode 1 extended window
    omega_adaptive_thresh:   float | None,   # None = disabled (always use normal)
    eta:                     float,
    rank_Ix:                 int,
    rho_typ:                 float,
    lock_min:                int,
    gamma_arr:               np.ndarray,
    rhs_norm_arr:            np.ndarray,
    rho_eff_arr:             np.ndarray,
    omega_thresh:            float | None = 0.02,  # existing gate at release time
    rho_alpha:               float = 0.5,
) -> dict:
    """v46: Adaptive CB window based on Omega measured at halt time.

    At each halt event:
      omega_at_halt = gamma[halt_bar] × rhs_norm[halt_bar]

      If omega_adaptive_thresh is not None AND omega_at_halt >= omega_adaptive_thresh:
          → Mode 1 reversal trip — use cb_window_mode1 (e.g. 180d)
      Else:
          → Normal market correction — use cb_window_normal (e.g. 90d)

    The Mode 1 extended window keeps the pre-reversal equity peak visible for
    longer in the rolling-window max deque, preventing premature re-entry into
    a still-declining market.

    All other mechanics identical to v41 (Fix 1 Omega gate at release,
    Fix 2 saturating budget, Fix 3 rho_eff gate).

    Additional diagnostics:
      mode1_trips:       number of trips classified as Mode 1 (high Omega at halt)
      mode1_omega_log:   list of omega_at_halt values for Mode 1 trips
      normal_trips:      trips classified as normal (low Omega at halt)
    """
    window_bars_normal = cb_window_normal * HOURS_PER_DAY
    window_bars_mode1  = cb_window_mode1  * HOURS_PER_DAY

    mono_dq: deque = deque()
    eq             = INIT
    peak_alltime   = INIT
    halted         = False
    halt_start_bar = 0
    rho_eff_at_halt  = rho_typ
    current_window   = window_bars_normal   # active window for this trip

    eq_vals:        list[float] = []
    y_vals:         list[float] = []
    cb_flags:       list[int]   = []
    lock_bars_arr:  list[int]   = []

    ito_resets          = 0
    gate_blocks_omega   = 0
    gate_blocks_rho     = 0
    mode1_trips         = 0
    normal_trips        = 0
    mode1_omega_log:    list[float] = []
    normal_omega_log:   list[float] = []
    rho_halt_log:       list[float] = []
    reset_bar_log:      list[int]   = []

    N = len(unit_normal)

    for bar_i in range(N):
        ur_n = float(unit_normal.iloc[bar_i])
        ur_c = float(unit_crash.iloc[bar_i])

        # ── Sliding-window peak (uses current_window for active trip) ─────────
        while mono_dq and mono_dq[0][0] <= bar_i - current_window:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

        # ── Halt trigger ──────────────────────────────────────────────────────
        if not halted and cb_dd >= cb_halt:
            halted          = True
            halt_start_bar  = bar_i
            rho_eff_at_halt = rho_eff_arr[bar_i]

            # Classify trip as Mode 1 or normal using Omega at halt time
            omega_at_halt = gamma_arr[bar_i] * rhs_norm_arr[bar_i]
            if (omega_adaptive_thresh is not None
                    and omega_at_halt >= omega_adaptive_thresh):
                current_window = window_bars_mode1
                mode1_trips   += 1
                mode1_omega_log.append(omega_at_halt)
            else:
                current_window = window_bars_normal
                normal_trips  += 1
                normal_omega_log.append(omega_at_halt)

        # ── Resume evaluation ─────────────────────────────────────────────────
        elif halted:
            lock_bars   = bar_i - halt_start_bar
            is_standard = cb_dd <= cb_resume
            is_g24      = (
                not is_standard
                and eta > 0.0
                and lock_bars >= lock_min
                and cb_dd <= cb_resume + c_sigma_saturating(eta, rank_Ix, rho_typ, lock_bars)
            )
            candidate = is_standard or is_g24

            if candidate and omega_thresh is not None:
                omega_val = gamma_arr[bar_i] * rhs_norm_arr[bar_i]
                if omega_val >= omega_thresh:
                    gate_blocks_omega += 1
                    candidate = False

            if candidate and rho_alpha > 0.0:
                ode_shock = rho_eff_at_halt < rho_alpha * rho_typ
                if ode_shock and rho_eff_arr[bar_i] < rho_alpha * rho_typ:
                    gate_blocks_rho += 1
                    candidate = False

            if candidate:
                halted         = False
                halt_start_bar = bar_i
                current_window = window_bars_normal   # reset to normal for next trip
                if is_g24:
                    ito_resets += 1
                    reset_bar_log.append(bar_i)

        # ── Position sizing ───────────────────────────────────────────────────
        if halted:
            y = 0.0
        elif dd_aty <= dd_soft:
            y = 1.0
        elif dd_aty >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        r = K_normal * y * ur_n + K_crash * ur_c
        r = max(r, -0.95)
        eq          *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)

        eq_vals.append(eq)
        y_vals.append(y)
        cb_flags.append(int(halted))
        lock_bars_arr.append(bar_i - halt_start_bar if halted else 0)

    eqs  = pd.Series(eq_vals, index=unit_normal.index)
    rets = eqs.pct_change().fillna(eqs.iloc[0] / INIT - 1.0)
    dd_s = (eqs - eqs.cummax()) / eqs.cummax()
    years = max((eqs.index[-1] - eqs.index[0]).days / 365.25, 1e-9)

    in_halt = False
    for bi in range(N):
        if cb_flags[bi] and not in_halt:
            in_halt = True
            rho_halt_log.append(float(rho_eff_arr[bi]))
        elif not cb_flags[bi] and in_halt:
            in_halt = False

    n_trips    = len(rho_halt_log)
    pct_halted = float(np.mean(cb_flags))

    return dict(
        eq                  = eqs,
        final               = float(eqs.iloc[-1]),
        cagr                = float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe              = (float(np.sqrt(24 * 365.25) * rets.mean() / rets.std())
                               if rets.std() > 0 else 0.0),
        maxdd               = float(dd_s.min()),
        pct_halted          = pct_halted,
        n_trips             = n_trips,
        mode1_trips         = mode1_trips,
        normal_trips        = normal_trips,
        avg_y               = float(np.mean(y_vals)),
        ito_resets          = ito_resets,
        gate_blocks_omega   = gate_blocks_omega,
        gate_blocks_rho     = gate_blocks_rho,
        omega_at_halt_mode1 = mode1_omega_log,
        omega_at_halt_normal= normal_omega_log,
        rho_eff_at_halt_log = rho_halt_log,
        max_lock_bars       = int(max(lock_bars_arr)) if lock_bars_arr else 0,
        reset_ts            = [],
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def yow(eq: pd.Series) -> dict[str, float]:
    return {r["period"][:4]: r["return_pct"] for r in period_table(eq, "Y")}


def result_row_v46(
    label: str, sim: dict, test_ts: pd.Timestamp,
    d: float, q: float,
    omega_adaptive_thresh: float | None,
    cb_window_mode1: int,
    rank_Ix: int, lambda_g7: float, rho_typ: float,
    sdiag: dict, bdiag: dict,
) -> dict:
    eq = sim["eq"][sim["eq"].index >= test_ts]
    m  = equity_metrics(eq, label)
    yy = yow(eq)
    return dict(
        name=label, d=d, q=q,
        eta=ETA, lock_min=LOCK_MIN, kappa_max=KAPPA_MAX,
        omega_adaptive_thresh=omega_adaptive_thresh,
        cb_window_normal=CB_WINDOW_NORMAL,
        cb_window_mode1=cb_window_mode1,
        rank_Ix=rank_Ix, lambda_g7=lambda_g7, rho_typ=rho_typ,
        final=m["final"], profit=m["final"] - INIT,
        cagr=m["cagr"], sharpe=m["sharpe"], maxdd=m["maxdd"], calmar=m["calmar"],
        pct_halted=sim.get("pct_halted", float("nan")),
        n_trips=sim.get("n_trips", 0),
        mode1_trips=sim.get("mode1_trips", 0),
        normal_trips=sim.get("normal_trips", 0),
        ito_resets=sim.get("ito_resets", 0),
        gate_blocks_omega=sim.get("gate_blocks_omega", 0),
        gate_blocks_rho=sim.get("gate_blocks_rho", 0),
        max_lock_bars=sim.get("max_lock_bars", 0),
        omega_halt_mode1_mean=(
            float(np.mean(sim["omega_at_halt_mode1"]))
            if sim.get("omega_at_halt_mode1") else float("nan")
        ),
        omega_halt_normal_mean=(
            float(np.mean(sim.get("omega_at_halt_normal", [0.0])))
            if sim.get("omega_at_halt_normal") else float("nan")
        ),
        r2022=yy.get("2022", float("nan")),
        r2023=yy.get("2023", float("nan")),
        r2024=yy.get("2024", float("nan")),
        r2025=yy.get("2025", float("nan")),
        r2026=yy.get("2026", float("nan")),
        sigma=sdiag, budget=bdiag,
    )


# ── Plots ─────────────────────────────────────────────────────────────────────

def plot_equity_v46(
    sim_store: dict[str, dict],
    results:   list[dict],
    test_ts:   pd.Timestamp,
) -> str:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    n_rows = len(TOP3)
    fig, axes = plt.subplots(n_rows, 1, figsize=(17, 4 * n_rows), sharex=True)
    if n_rows == 1:
        axes = [axes]

    thresh_colors = {
        None:  "#aaaaaa",
        0.01:  "#4393c3",
        0.02:  "#d6604d",
        0.04:  "#8B0000",
    }
    mode1_ls = {180: "-", 270: "--"}

    for ax_i, (d, q) in enumerate(TOP3):
        ax = axes[ax_i]

        for r in results:
            if r["d"] != d or r["q"] != q:
                continue
            bk = r["name"]
            if bk not in sim_store:
                continue
            eq2 = sim_store[bk]["eq"][sim_store[bk]["eq"].index >= test_ts]
            oa  = r["omega_adaptive_thresh"]
            w1  = r["cb_window_mode1"]
            clr = thresh_colors.get(oa, "#888888")
            ls  = mode1_ls.get(w1, "-")
            lbl_thresh = f"ω_thr={oa:.2f}" if oa is not None else "None (baseline)"
            mode1_pct = (100 * r["mode1_trips"] / r["n_trips"]
                         if r["n_trips"] > 0 else 0.0)
            ax.semilogy(
                eq2.index, eq2.values, lw=1.8, color=clr, ls=ls,
                label=(f"{lbl_thresh} w1={w1}d  "
                       f"${eq2.iloc[-1]:,.0f}  "
                       f"MaxDD={r['maxdd']:.1%}  "
                       f"Cal={r['calmar']:.1f}  "
                       f"M1={r['mode1_trips']}/{r['n_trips']} ({mode1_pct:.0f}%)"),
            )

        ax.axhline(730_056, ls=":", lw=1.0, color="purple", alpha=0.4, label="v34 $730k")
        ax.axhline(617_095, ls=":", lw=1.0, color="green",  alpha=0.4, label="v40 $617k")
        ax.axhline(130_672, ls=":", lw=1.0, color="blue",   alpha=0.4, label="v45 $131k (180d)")
        ax.set_title(f"v46 Ω-adaptive — d={d}, q={q}", fontweight="bold")
        ax.set_ylabel("Equity ($)")
        ax.legend(fontsize=7, loc="upper left")
        ax.grid(True, alpha=0.25)

    axes[-1].set_xlabel("Date")
    fig.suptitle(
        "v46: Omega-at-halt adaptive window  (Mode 1 → 180d/270d,  normal → 90d)",
        fontweight="bold", y=1.01,
    )
    out = PLOT_DIR / "v46_equity_omega_adaptive.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def plot_omega_diagnostic(results: list[dict]) -> str:
    """Bar chart: mean Omega at halt for Mode 1 vs normal trips per variant."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: mode1_trips and normal_trips count by omega_adaptive_thresh for d=0.25, q=0.50
    sub = [r for r in results if r["d"] == 0.25 and r["q"] == 0.50]
    labels = []
    m1_counts = []
    nm_counts = []
    for r in sub:
        oa = r["omega_adaptive_thresh"]
        w1 = r["cb_window_mode1"]
        labels.append(f"ω≥{oa:.2f}\nw1={w1}d" if oa is not None else f"baseline\n(90d all)")
        m1_counts.append(r["mode1_trips"])
        nm_counts.append(r["normal_trips"])

    x = range(len(labels))
    ax = axes[0]
    ax.bar(x, m1_counts, label="Mode 1 trips (extended window)", color="#d6604d", alpha=0.8)
    ax.bar(x, nm_counts, bottom=m1_counts, label="Normal trips (90d window)", color="#4393c3", alpha=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Number of CB trips")
    ax.set_title("Mode 1 vs Normal trip classification (d=0.25, q=0.50)")
    ax.legend(fontsize=9)

    # Right: scatter MaxDD vs Final for all variants
    ax = axes[1]
    thresh_colors = {None: "#aaaaaa", 0.01: "#4393c3", 0.02: "#d6604d", 0.04: "#8B0000"}
    for r in results:
        clr = thresh_colors.get(r["omega_adaptive_thresh"], "#888888")
        ax.scatter(r["maxdd"] * 100, r["final"] / 1000, c=clr, alpha=0.6, s=60)

    ax.axvline(-34.6, ls="--", lw=1, color="orange", alpha=0.8, label="v40 MaxDD=-34.6%")
    ax.axhline(617.095, ls="--", lw=1, color="green", alpha=0.8, label="v40 Final=$617k")
    ax.axhline(130.672, ls="--", lw=1, color="blue",  alpha=0.8, label="v45 Final=$131k")
    ax.set_xlabel("MaxDD (%)")
    ax.set_ylabel("Final equity ($k)")
    ax.set_title("v46: MaxDD vs Final   (colour = ω_adaptive_thresh)")
    ax.legend(fontsize=8)

    from matplotlib.patches import Patch
    patches = [Patch(color=c, label=f"ω≥{k:.2f}" if k else "baseline")
               for k, c in thresh_colors.items()]
    axes[0].figure.legend(handles=patches, loc="upper center",
                          ncol=4, fontsize=8, bbox_to_anchor=(0.5, 1.01))

    out = PLOT_DIR / "v46_omega_diagnostic.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return str(out)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    t0_total = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    # Variants = 3 (d,q) × 4 (thresholds) × 2 (mode1 windows) - 3×1×2 (None only needs one window)
    # Effectively: baseline (None, any window) = 3; adaptive = 3 × 3 × 2 = 18; total = 21
    # But we run all combos: 3 × 4 × 2 = 24 minus 3×1 duplicates (None ignores mode1_window)
    # Simpler: run all 3 × 4 × 2 = 24, baseline results will be identical for both mode1 windows
    n_total = len(TOP3) * len(OMEGA_ADAPTIVE_THRESH_GRID) * len(CB_WINDOW_MODE1_GRID)

    print(BAR)
    print("  CRYPTO GODMODE v46 — Omega-at-halt Adaptive Window")
    print()
    print("  Mode 1 filter formula (v38_reversal_geometry.py):")
    print("    Ω = γ × ‖f(z)‖  ≥  0.02  →  BLOCK (Mode 1 reversal detected)")
    print("    Max winner Ω = 0.0063   Min loser Ω = 0.0403   Gap = 6.4×")
    print()
    print("  v46 applies Omega at HALT TIME (not release time):")
    print("    If omega_at_halt ≥ omega_adaptive_thresh → Mode 1 trip → cb_window_mode1")
    print("    Else                                      → Normal trip → cb_window_normal=90d")
    print()
    print(f"  OMEGA_ADAPTIVE_THRESH grid:  {OMEGA_ADAPTIVE_THRESH_GRID}")
    print(f"  CB_WINDOW_MODE1 grid:        {CB_WINDOW_MODE1_GRID}d")
    print(f"  CB_WINDOW_NORMAL (fixed):    {CB_WINDOW_NORMAL}d")
    print(f"  Fixed engine:  eta={ETA:.0e}  lm={LOCK_MIN}  km=None  om={OMEGA_THRESH}  ra={RHO_ALPHA}")
    print(f"  (d,q) TOP3:    {TOP3}")
    print(f"  Total:         {n_total}")
    print(BAR)

    # ── [0] Microstructure cache ──────────────────────────────────────────────
    print("\n[0] Preloading microstructure cache ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = v27._get_ms(sym)
        print(f"  {sym}: {ms.shape}")

    # ── [1] Shared market inputs ──────────────────────────────────────────────
    print("\n[1] Building shared market inputs ...")
    df, _      = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    test_ts    = pd.Timestamp(TEST_START)
    w_star     = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned  = build_b_aligned(w_star)
    factor_R   = build_factor_returns(df)
    v27.RT_COST = RT_BPS / 10_000.0

    # ── [2] FFD Sigma ─────────────────────────────────────────────────────────
    print("\n[2] Building FFD Sigma ...")
    sigma_store: dict[float, tuple] = {}
    for d in sorted(set(d_ for d_, _ in TOP3)):
        Sigma_base, Sigma_ffd, sdiag, bdiag = build_sigma(factor_R, train_mask, df, d)
        Sigma_cap, lam_g7 = Sigma_base, 0.0
        Sigma_w_sqrt, rank_Ix = fisher_weight_noise_sqrt(Sigma_cap)
        kp_raw = float(np.linalg.cond(Sigma_base))
        print(f"  d={d:.2f}: κ(Σ)={kp_raw:.2f}  rank(I_X)={rank_Ix}")
        sigma_store[d] = (Sigma_cap, Sigma_ffd, sdiag, bdiag, Sigma_w_sqrt, rank_Ix, lam_g7)

    # ── [3] Deterministic ODE ─────────────────────────────────────────────────
    print("\n[3] Running deterministic ODE sweeps ...")
    unit_store: dict[tuple, tuple] = {}
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol)
                for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()

    for d, q in TOP3:
        Sigma_cap, _, sdiag, bdiag, _, rank_Ix, lam_g7 = sigma_store[d]
        theta     = theta_from(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)
        label_ode = f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}_det_v46"
        print(f"  ODE: {label_ode}  θ={theta:.5f}", end="  ", flush=True)
        t_ode = time.time()
        log_ann, rho_typ = run_godmode_det_v39(
            df, train_mask, test_mask, w_star, b_aligned,
            Sigma_cap, theta, kappa=KAPPA_A, label=label_ode,
        )
        print(f"ρ_typ={rho_typ:.4f}", end="  ", flush=True)
        inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                        signal_kind="wstar", use_quadrant=False)
        inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                        signal_kind="wstar", use_quadrant=True)
        inputs     = attach_q_hot(inputs_noq, inputs_q)
        sig_map    = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                      for asset, _, _, idx in ASSETS}
        unit = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]
        unit_store[(d, q)] = (unit, log_ann, rho_typ)
        print(f"{time.time()-t_ode:.1f}s  unit={len(unit)}")

    # ── [4] Adaptive window sweep ─────────────────────────────────────────────
    print(f"\n[4] Running v46 Omega-adaptive sweep ...")
    results:      list[dict]      = []
    sim_store_eq: dict[str, dict] = {}

    hdr = (f"  {'label':<72}  {'Calmar':>7}  {'Final':>12}  {'MaxDD':>7}  "
           f"{'r2026':>7}  {'M1/tot':>7}  {'maxlk':>6}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for d, q in TOP3:
        Sigma_cap, _, sdiag, bdiag, _, rank_Ix, lam_g7 = sigma_store[d]
        unit, log_ann_dq, rho_typ_dq = unit_store[(d, q)]

        idx          = unit.index
        gamma_arr    = log_ann_dq["gamma"].reindex(idx).fillna(0.0).values
        rhs_norm_arr = log_ann_dq["rhs_norm"].reindex(idx).fillna(0.0).values
        rho_eff_arr  = log_ann_dq["rho_eff"].reindex(idx).fillna(rho_typ_dq).values

        for omega_thresh_adapt in OMEGA_ADAPTIVE_THRESH_GRID:
            for w1 in CB_WINDOW_MODE1_GRID:
                oa_str = f"oa{str(omega_thresh_adapt).replace('.','p')}" if omega_thresh_adapt is not None else "oa_None"
                label = (f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}"
                         f"_{oa_str}_w1_{w1:03d}d")

                sim = simulate_omega_adaptive_v46(
                    unit_normal=unit,
                    unit_crash=pd.Series(0.0, index=unit.index),
                    K_normal=K_NORMAL, K_crash=0.0,
                    dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                    cb_halt=CB_HALT, cb_resume=CB_RESUME,
                    cb_window_normal=CB_WINDOW_NORMAL,
                    cb_window_mode1=w1,
                    omega_adaptive_thresh=omega_thresh_adapt,
                    eta=ETA, rank_Ix=rank_Ix, rho_typ=rho_typ_dq, lock_min=LOCK_MIN,
                    gamma_arr=gamma_arr, rhs_norm_arr=rhs_norm_arr, rho_eff_arr=rho_eff_arr,
                    omega_thresh=OMEGA_THRESH, rho_alpha=RHO_ALPHA,
                )
                sim_store_eq[label] = sim

                row = result_row_v46(
                    label=label, sim=sim, test_ts=test_ts,
                    d=d, q=q,
                    omega_adaptive_thresh=omega_thresh_adapt,
                    cb_window_mode1=w1,
                    rank_Ix=rank_Ix, lambda_g7=lam_g7, rho_typ=rho_typ_dq,
                    sdiag=sdiag, bdiag=bdiag,
                )
                results.append(row)

                m1 = sim.get("mode1_trips", 0)
                nt = sim.get("n_trips", 1)
                m1_str = f"{m1}/{nt}"
                base_flag = " [BASELINE]" if omega_thresh_adapt is None else ""
                print(f"  {label:<72}  {row['calmar']:>7.2f}  "
                      f"${row['final']:>11,.0f}  {row['maxdd']:>7.1%}  "
                      f"{row['r2026']:>+7.3f}  {m1_str:>7}  "
                      f"{sim.get('max_lock_bars',0):>6}{base_flag}")

    # ── [5] Summary ────────────────────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  v46 RESULTS SUMMARY")
    print(f"  Total variants: {len(results)}")
    print()

    # ── Omega distribution at halt time (critical diagnostic) ──
    print("  Omega at halt time — are the 19 staircase trips classifiable?")
    print("  (from baseline variants: omega_adaptive_thresh=None, d=0.25, q=0.50)")
    base_sims = [k for k in sim_store_eq if "oa_None" in k and "d0p25_q0p5" in k]
    if base_sims:
        bsim = sim_store_eq[base_sims[0]]
        all_omega = bsim.get("omega_at_halt_normal", [])
        if all_omega:
            print(f"  All {len(all_omega)} trip Omega values (at halt):")
            for i, ov in enumerate(sorted(all_omega, reverse=True)):
                bar = "█" * int(ov * 500)
                above = "  ← Mode 1 (≥ 0.02)" if ov >= 0.02 else ""
                print(f"    Trip rank {i+1:2d}: Ω={ov:.5f}  {bar}{above}")
        else:
            print("  No halt omega data (all classified as normal with None threshold)")

    # ── Best results by region ──
    print("\n  All variants sorted by Calmar:")
    by_cal = sorted(results, key=lambda r: -r.get("calmar", 0))
    print(f"  {'name':<60}  {'Calmar':>7}  {'Final':>12}  {'MaxDD':>7}  "
          f"{'r2026':>7}  {'M1/tot':>7}")
    for r in by_cal[:15]:
        m1_str = f"{r['mode1_trips']}/{r['n_trips']}"
        print(f"  {r['name']:<60}  {r['calmar']:>7.2f}  "
              f"${r['final']:>11,.0f}  {r['maxdd']:>7.1%}  "
              f"{r['r2026']:>+7.3f}  {m1_str:>7}")

    # ── Best MaxDD ──
    best_dd = max(results, key=lambda r: r.get("maxdd", -99))
    print(f"\n  Best MaxDD: {best_dd['name']}")
    print(f"    Calmar={best_dd['calmar']:.2f}  Final=${best_dd['final']:,.0f}  "
          f"MaxDD={best_dd['maxdd']:.1%}  r2026={best_dd.get('r2026',0):+.4f}  "
          f"Mode1={best_dd['mode1_trips']}/{best_dd['n_trips']}")

    print(f"\n  Reference lines:")
    print(f"    v34/v35:   $730,056  Calmar=17.49  MaxDD=−35%    r2026=+7%")
    print(f"    v40/v41:   $617K     Calmar=16.60  MaxDD=−34.6%  OmBlk=4  n_trips=19")
    print(f"    v45 w=180d: $131K    Calmar=23.25  MaxDD=−14.0%  n_trips=10")

    # ── [6] Save JSON ──────────────────────────────────────────────────────────
    print(f"\n[6] Saving results ...")

    def serialise(obj):
        if isinstance(obj, float) and (obj != obj or abs(obj) == float("inf")):
            return None
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        raise TypeError(type(obj))

    out_json = OUT_DIR_ / "crypto_godmode_v46_omega_adaptive.json"
    rows_clean = [
        {k: v for k, v in r.items()
         if k not in ("sigma", "budget", "rho_eff_at_halt_log",
                      "omega_at_halt_mode1", "omega_at_halt_normal")
         and not isinstance(v, pd.Series)}
        for r in results
    ]
    with open(out_json, "w") as f:
        json.dump(
            {
                "version":    "v46",
                "formula":    "Omega_at_halt = gamma[halt_bar] * rhs_norm[halt_bar]",
                "threshold":  "0.02 (derived: max_winner=0.0063, min_loser=0.0403, gap=6.4x)",
                "rule":       "If Omega_at_halt >= thresh -> Mode 1 trip -> cb_window_mode1 (180d/270d); else -> 90d",
                "rationale":  "ODE overexcited at halt predicts Mode 1 reversal; longer window prevents premature re-entry",
                "grids": {
                    "omega_adaptive_thresh": OMEGA_ADAPTIVE_THRESH_GRID,
                    "cb_window_mode1":       CB_WINDOW_MODE1_GRID,
                    "cb_window_normal":      CB_WINDOW_NORMAL,
                },
                "results": rows_clean,
            },
            f, indent=2, default=serialise,
        )
    print(f"  → {out_json}")

    # ── [7] Plots ──────────────────────────────────────────────────────────────
    print(f"\n[7] Generating plots ...")
    eq_path   = plot_equity_v46(sim_store_eq, results, test_ts)
    print(f"  Equity curves: {eq_path}")
    diag_path = plot_omega_diagnostic(results)
    print(f"  Diagnostics:   {diag_path}")

    elapsed = time.time() - t0_total
    print(f"\n{BAR}")
    print(f"  v46 COMPLETE  |  elapsed={elapsed:.1f}s  ({elapsed/60:.1f} min)")
    print(f"  Formula: Ω_at_halt = γ × ‖f(z)‖  ≥  thresh → Mode 1 → 180d/270d window")
    print(f"  Key diagnostic: see 'Omega at halt time' section above")
    print(f"  — How many of the 19 staircase trips had Ω ≥ 0.02 at halt?")
    print(BAR)


if __name__ == "__main__":
    main()
