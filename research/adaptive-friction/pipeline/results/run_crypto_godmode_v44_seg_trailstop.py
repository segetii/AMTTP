# -*- coding: utf-8 -*-
"""
run_crypto_godmode_v44_seg_trailstop.py
=======================================

v44 = v41 + Intra-segment Trailing Stop (Mode 1 Reversal Filter)

──────────────────────────────────────────────────────────────────────────────
Context from v38_reversal_geometry.py (Mode 1 C0 cluster)
──────────────────────────────────────────────────────────────────────────────

  38a C0 LOSER: peaked at +4.7% above CB-release level, reversed to net -5.3%  (skew=-4.4)
  38b C0 LOSER: peaked at +5.9% above CB-release level, reversed to net -5.1%  (skew=-5.9)

  These "Mode 1 reversal" segments:
    - Start with ODE in overexcited state (gamma>0.10, rhs_norm>0.30, Omega>0.04)
    - Move in the CORRECT direction initially (+4.7% to +5.9% from CB release point)
    - Then suffer a large reversal bar that erases gains + more (negative skew -4.4 / -5.9)
    - End with negative seg_return despite being initially "correct"

──────────────────────────────────────────────────────────────────────────────
Why the existing Omega gate (v39–v43) fails
──────────────────────────────────────────────────────────────────────────────

  In v39–v43, the Omega gate (gamma × rhs_norm >= 0.02 → block CB re-entry)
  fires only OmBlk=4 times across the entire test period — nearly useless.

  Root cause: The deterministic ODE continues running during CB lockout.
  By the time the CB releases (after 90d rolling peak DD recovers from 8%→4%),
  the ODE has fully converged → gamma≈0, rhs_norm≈0, Omega≈0.
  The gate never fires because the signal it looks for is gone by the time
  it checks.

──────────────────────────────────────────────────────────────────────────────
v44 Fix: Intra-segment trailing stop (equity-based Mode 1 filter)
──────────────────────────────────────────────────────────────────────────────

  After each CB release, reset a per-segment local equity peak (seg_peak_eq).
  If equity drops >= seg_trail_stop (%) from seg_peak_eq → halt early.

  This catches the Mode 1 pattern:
    - CB releases → strategy active → equity gains +4.7% to +5.9% (seg_peak_eq rises)
    - Equity reverses → drops seg_trail_stop from seg_peak_eq → early halt fires
    - Instead of waiting for the full 8% CB to fire after a deep round-trip loss

  Use a shorter lockout (trail_lockout_days = 14-30d) for trail halts because
  the loss from a trail halt (4-6%) is smaller than a full CB halt (8%).
  Main CB (8% / 90d window) remains unchanged.

  KEY PROPERTY: The trailing stop only benefits when:
    equity RISES (new local high) after CB release, THEN falls.
  For pure staircase steps (immediate decline after release), the main CB
  fires before the trailing stop can add any value.

──────────────────────────────────────────────────────────────────────────────
Grid
────
  SEG_TRAIL_STOP_GRID     : [0.040, 0.047, 0.059]
    → 4.0%  = aggressive filter (tighter than Mode 1 peak)
    → 4.7%  = exact 38a C0 trailing stop (v38_reversal_geometry.py)
    → 5.9%  = exact 38b C0 trailing stop (v38_reversal_geometry.py)
  TRAIL_LOCKOUT_DAYS_GRID : [14, 30]
    → 2-week and 1-month lockout after trail halt

  Fixed engine settings (proven best from v40/v41):
    η=2e-4, lock_min=500, kappa_max=None, omega_thresh=0.02, rho_alpha=0.5

  (d,q) TOP3 = same as v38–v43

  Baselines: trail_stop=None per (d,q) — uses simulate_combined_lockmin_v41
  Trail variants: 3 (d,q) × 3 (trail_stop) × 2 (lockout) = 18
  Total: 3 + 18 = 21 variants

Theory references
───────────────────
  Mode 1 peak geometry:   v38_reversal_geometry.py  (38a/38b C0 LOSER cluster)
  Mode 1 cluster source:  v38_trade_clustering.py   (segment Ω analysis, C0)
  Mode 2 filter (ρ_eff):  v38_mode2_investigation.py
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
OUT_DIR_ = Path(OUT_DIR) / "v44_seg_trailstop"
PLOT_DIR = OUT_DIR_ / "plots"

# TOP3 (d,q) — same as v38–v43
TOP3 = [
    (0.30, 0.50),   # rank-1: baseline Calmar=23.00
    (0.30, 0.65),   # rank-2: best Calmar=23.98
    (0.25, 0.50),   # rank-3: r2026>0 at high η
]

# ── CB config (identical to v34: cb_v34_tight) ────────────────────────────────
CB_HALT   = 0.08
CB_RESUME = 0.04
CB_WINDOW = 90   # days

# ── Fixed engine settings (proven best from v40/v41) ────────────────────────
ETA         = 2e-4
LOCK_MIN    = 500
KAPPA_MAX   = None
OMEGA_THRESH = 0.02
RHO_ALPHA   = 0.5

# ── v44 intra-segment trailing stop grids ────────────────────────────────────
# Values from v38_reversal_geometry.py:
#   38a C0 LOSER: peaked at +4.7%   38b C0 LOSER: peaked at +5.9%
SEG_TRAIL_STOP_GRID     = [0.040, 0.047, 0.059]   # 4.0% (tight), 4.7% (38a), 5.9% (38b)
TRAIL_LOCKOUT_DAYS_GRID = [14, 30]                 # 2-week and 1-month lockout


# ── G7 covariance regularisation (Proposition G7.1) ──────────────────────────

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


# ── Fisher noise helpers ──────────────────────────────────────────────────────

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


# ── Budget formulae ───────────────────────────────────────────────────────────

def c_sigma_per_bar(eta: float, rank_Ix: int) -> float:
    return eta * DT * rank_Ix


def c_sigma_saturating(
    eta: float, rank_Ix: int, rho_typ: float, lock_bars: int
) -> float:
    if eta == 0.0 or rho_typ <= 0.0:
        return 0.0
    E_inf = eta * rank_Ix / rho_typ
    return E_inf * (1.0 - np.exp(-rho_typ * lock_bars * DT))


# ── Deterministic canonical ODE ──────────────────────────────────────────────

def run_godmode_det_v39(
    df:          pd.DataFrame,
    train_mask:  np.ndarray,
    test_mask:   np.ndarray,
    w_star_arr:  np.ndarray,
    b_arr:       np.ndarray,
    Sigma_cap:   np.ndarray,
    theta_base:  float,
    kappa:       float = KAPPA_A,
    label:       str   = "",
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

        stop_flag  = 1.0 if sc["gamma"] > 0.90 else 0.0
        stale_flag = 1.0 if (sc["rho_eff"] > 0 and sc["rho_eff"] < 0.1 * rho_typ) else 0.0
        drift_flag = 1.0 if sc["cos_theta"] > 0.0 else 0.0

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
        log["stop_flag"][t]     = stop_flag
        log["stale_flag"][t]    = stale_flag
        log["drift_flag"][t]    = drift_flag
        log["conviction"][t]    = conviction
        log["theta_t"][t]       = theta_t

        cos_th_prev = sc["cos_theta"]
        if t > 0 and (t % 5000) == 0:
            print(f"    [{label}] {t:>6}/{T}  ({time.time()-t0:.1f}s)")

    return pd.DataFrame(log, index=df.index), rho_typ


# ── v41 CB simulation (baseline — unchanged) ─────────────────────────────────

def simulate_combined_lockmin_v41(
    unit_normal:   pd.Series,
    unit_crash:    pd.Series,
    K_normal:      float,
    K_crash:       float,
    dd_soft:       float,
    dd_stop:       float,
    y_floor:       float,
    cb_halt:       float,
    cb_resume:     float,
    cb_window_days: int,
    eta:           float,
    rank_Ix:       int,
    rho_typ:       float,
    lock_min:      int,
    gamma_arr:     np.ndarray,
    rhs_norm_arr:  np.ndarray,
    rho_eff_arr:   np.ndarray,
    omega_thresh:  float | None = 0.02,
    rho_alpha:     float = 0.5,
    ramp_init:     float = 1.0,
    ramp_bars:     int   = 168,
) -> dict:
    """v41 CB simulation — used for baseline variants (trail_stop=None)."""
    window_bars    = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq             = INIT
    peak_alltime   = INIT
    halted         = False
    halt_start_bar = 0
    rho_eff_at_halt = rho_typ
    resume_bar      = -1

    eq_vals:       list[float] = []
    y_vals:        list[float] = []
    cb_flags:      list[int]   = []
    lock_bars_arr: list[int]   = []

    ito_resets        = 0
    gate_blocks_omega = 0
    gate_blocks_rho   = 0
    reset_bar_log:    list[int] = []

    N = len(unit_normal)

    for bar_i in range(N):
        ur_n = float(unit_normal.iloc[bar_i])
        ur_c = float(unit_crash.iloc[bar_i])

        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

        if not halted and cb_dd >= cb_halt:
            halted          = True
            halt_start_bar  = bar_i
            rho_eff_at_halt = rho_eff_arr[bar_i]

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

            if candidate:
                if omega_thresh is not None:
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
                resume_bar     = bar_i
                if is_g24:
                    ito_resets += 1
                    reset_bar_log.append(bar_i)

        if halted:
            y = 0.0
        elif dd_aty <= dd_soft:
            y = 1.0
        elif dd_aty >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        if (not halted) and ramp_init < 1.0 and resume_bar >= 0:
            t_since = bar_i - resume_bar
            scale   = (ramp_init + t_since * (1.0 - ramp_init) / ramp_bars
                       if t_since < ramp_bars else 1.0)
        else:
            scale = 1.0

        r = (K_normal * scale) * y * ur_n + K_crash * ur_c
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
    reset_ts = [unit_normal.index[b] for b in reset_bar_log if b < N]

    rho_halt_log: list[float] = []
    in_halt = False
    for bi in range(N):
        if cb_flags[bi] and not in_halt:
            in_halt = True
            rho_halt_log.append(float(rho_eff_arr[bi]))
        elif not cb_flags[bi] and in_halt:
            in_halt = False

    return dict(
        eq                  = eqs,
        final               = float(eqs.iloc[-1]),
        cagr                = float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe              = (float(np.sqrt(24 * 365.25) * rets.mean() / rets.std())
                               if rets.std() > 0 else 0.0),
        maxdd               = float(dd_s.min()),
        pct_halted          = float(np.mean(cb_flags)),
        n_trips             = int(sum(cb_flags[i] > cb_flags[i - 1]
                                      for i in range(1, len(cb_flags)))),
        avg_y               = float(np.mean(y_vals)),
        ito_resets          = ito_resets,
        gate_blocks_omega   = gate_blocks_omega,
        gate_blocks_rho     = gate_blocks_rho,
        trail_halt_count    = 0,
        rho_eff_at_halt_log = rho_halt_log,
        max_lock_bars       = int(max(lock_bars_arr)) if lock_bars_arr else 0,
        reset_ts            = [str(ts) for ts in reset_ts],
    )


# ── v44: Intra-segment trailing stop simulation ───────────────────────────────

def simulate_seg_trailstop_v44(
    unit_normal:        pd.Series,
    unit_crash:         pd.Series,
    K_normal:           float,
    K_crash:            float,
    dd_soft:            float,
    dd_stop:            float,
    y_floor:            float,
    cb_halt:            float,
    cb_resume:          float,
    cb_window_days:     int,
    eta:                float,
    rank_Ix:            int,
    rho_typ:            float,
    lock_min:           int,
    gamma_arr:          np.ndarray,
    rhs_norm_arr:       np.ndarray,
    rho_eff_arr:        np.ndarray,
    omega_thresh:       float | None = 0.02,
    rho_alpha:          float = 0.5,
    seg_trail_stop:     float = 0.047,
    trail_lockout_days: int   = 14,
) -> dict:
    """v44: CB simulation + intra-segment trailing stop (Mode 1 reversal filter).

    After each CB release, track a per-segment local equity peak (seg_peak_eq).
    If equity drops seg_trail_stop (%) from seg_peak_eq → halt early ("trail halt").
    Trail halt resumes after trail_lockout_days (fixed time, shorter than CB window).
    Main CB continues to fire unchanged at cb_halt (8%) of 90d rolling peak.

    Two halt states:
      "cb"    — triggered by main CB (8% of 90d peak).  Resumes by standard CB logic.
      "trail" — triggered by intra-seg trailing stop.    Resumes after trail_lockout_bars.

    On any resume (either type): seg_peak_eq resets to current equity.

    This captures Mode 1 reversals directly:
      Release at equityₐ → equity rises to equityₐ × (1 + trail_stop) (seg peak)
      → equity falls trail_stop% from peak → trail halt fires early
      rather than waiting for the full 8% CB drawdown.
    """
    window_bars        = cb_window_days * HOURS_PER_DAY
    trail_lockout_bars = trail_lockout_days * HOURS_PER_DAY
    mono_dq: deque    = deque()
    eq                = INIT
    peak_alltime      = INIT
    halted            = False
    halt_reason       = ""        # "cb" or "trail"
    halt_start_bar    = 0
    rho_eff_at_halt   = rho_typ
    seg_peak_eq       = INIT      # local equity peak since last CB/trail release

    eq_vals:        list[float] = []
    y_vals:         list[float] = []
    cb_flags:       list[int]   = []
    lock_bars_arr:  list[int]   = []

    ito_resets          = 0
    gate_blocks_omega   = 0
    gate_blocks_rho     = 0
    trail_halt_count    = 0
    reset_bar_log:      list[int]   = []
    rho_halt_log:       list[float] = []

    N = len(unit_normal)

    for bar_i in range(N):
        ur_n = float(unit_normal.iloc[bar_i])
        ur_c = float(unit_crash.iloc[bar_i])

        # ── Sliding-window peak (CB) ──────────────────────────────────────────
        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

        if not halted:
            # ── Update segment-level peak ────────────────────────────────────
            seg_peak_eq = max(seg_peak_eq, eq)
            seg_trail_dd = max(0.0, 1.0 - eq / max(seg_peak_eq, 1e-12))

            # ── Priority 1: Main CB trigger (8% of 90d rolling peak) ─────────
            if cb_dd >= cb_halt:
                halted          = True
                halt_reason     = "cb"
                halt_start_bar  = bar_i
                rho_eff_at_halt = rho_eff_arr[bar_i]

            # ── Priority 2: Intra-segment trailing stop (Mode 1 filter) ──────
            elif seg_trail_dd >= seg_trail_stop:
                halted           = True
                halt_reason      = "trail"
                halt_start_bar   = bar_i
                trail_halt_count += 1

        else:  # halted
            lock_bars = bar_i - halt_start_bar

            if halt_reason == "trail":
                # ── Trail halt: fixed-time lockout ────────────────────────────
                # Also check if main CB fires while in trail halt
                if cb_dd >= cb_halt:
                    # Escalate to full CB halt
                    halt_reason     = "cb"
                    halt_start_bar  = bar_i
                    rho_eff_at_halt = rho_eff_arr[bar_i]
                elif lock_bars >= trail_lockout_bars:
                    halted      = False
                    halt_reason = ""
                    seg_peak_eq = eq   # reset segment peak on trail resume

            else:  # halt_reason == "cb"
                # ── CB halt: standard resume logic (v41) ─────────────────────
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
                    halt_reason    = ""
                    halt_start_bar = bar_i
                    seg_peak_eq    = eq    # reset segment peak on CB resume
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
    reset_ts = [unit_normal.index[b] for b in reset_bar_log if b < N]

    # Collect rho_eff_at_halt for each CB trip
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
        avg_y               = float(np.mean(y_vals)),
        ito_resets          = ito_resets,
        gate_blocks_omega   = gate_blocks_omega,
        gate_blocks_rho     = gate_blocks_rho,
        trail_halt_count    = trail_halt_count,
        rho_eff_at_halt_log = rho_halt_log,
        max_lock_bars       = int(max(lock_bars_arr)) if lock_bars_arr else 0,
        reset_ts            = [str(ts) for ts in reset_ts],
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def yow(eq: pd.Series) -> dict[str, float]:
    return {r["period"][:4]: r["return_pct"] for r in period_table(eq, "Y")}


def result_row_v44(
    label: str,
    sim:   dict,
    test_ts: pd.Timestamp,
    d: float, q: float,
    seg_trail_stop: float | None,
    trail_lockout_days: int,
    rank_Ix: int, lambda_g7: float, rho_typ: float,
    sdiag: dict, bdiag: dict,
) -> dict:
    eq = sim["eq"][sim["eq"].index >= test_ts]
    m  = equity_metrics(eq, label)
    yy = yow(eq)
    return dict(
        name=label,
        d=d, q=q,
        eta=ETA, lock_min=LOCK_MIN, kappa_max=KAPPA_MAX,
        omega_thresh=OMEGA_THRESH, rho_alpha=RHO_ALPHA,
        seg_trail_stop=seg_trail_stop,
        trail_lockout_days=trail_lockout_days,
        rank_Ix=rank_Ix, lambda_g7=lambda_g7, rho_typ=rho_typ,
        final=m["final"], profit=m["final"] - INIT,
        cagr=m["cagr"], sharpe=m["sharpe"], maxdd=m["maxdd"], calmar=m["calmar"],
        pct_halted=sim.get("pct_halted", float("nan")),
        n_trips=sim.get("n_trips", 0),
        ito_resets=sim.get("ito_resets", 0),
        gate_blocks_omega=sim.get("gate_blocks_omega", 0),
        gate_blocks_rho=sim.get("gate_blocks_rho", 0),
        trail_halt_count=sim.get("trail_halt_count", 0),
        max_lock_bars=sim.get("max_lock_bars", 0),
        reset_ts=sim.get("reset_ts", []),
        r2022=yy.get("2022", float("nan")),
        r2023=yy.get("2023", float("nan")),
        r2024=yy.get("2024", float("nan")),
        r2025=yy.get("2025", float("nan")),
        r2026=yy.get("2026", float("nan")),
        sigma=sdiag, budget=bdiag,
    )


# ── Equity curve plot ─────────────────────────────────────────────────────────

def plot_equity_v44(
    sim_store: dict[str, dict],
    results:   list[dict],
    test_ts:   pd.Timestamp,
) -> str:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    n_rows = len(TOP3)
    fig, axes = plt.subplots(n_rows, 1, figsize=(16, 4 * n_rows), sharex=True)
    if n_rows == 1:
        axes = [axes]

    trail_colors = {
        None:  ("#aaaaaa", "--",  "Baseline (no trail stop)"),
        0.040: ("#ff7f0e", "-",   "trail=4.0%"),
        0.047: ("#d62728", "-",   "trail=4.7% (38a C0)"),
        0.059: ("#8B0000", "-",   "trail=5.9% (38b C0)"),
    }
    lockout_ls   = {14: "-", 30: ":"}

    for ax_i, (d, q) in enumerate(TOP3):
        ax = axes[ax_i]

        # Baseline
        base_rows = [r for r in results
                     if r["d"] == d and r["q"] == q and r["seg_trail_stop"] is None]
        if base_rows:
            bk = base_rows[0]["name"]
            if bk in sim_store:
                eq0 = sim_store[bk]["eq"][sim_store[bk]["eq"].index >= test_ts]
                ax.semilogy(eq0.index, eq0.values, lw=1.5, color="#aaaaaa", ls="--",
                            label=(f"Baseline  ${eq0.iloc[-1]:,.0f}  "
                                   f"MaxDD={base_rows[0]['maxdd']:.1%}  "
                                   f"Cal={base_rows[0]['calmar']:.2f}"))

        # Trail stop variants
        for trail_stop in SEG_TRAIL_STOP_GRID:
            clr, _, clabel = trail_colors.get(trail_stop, ("#888888", "-", str(trail_stop)))
            for lockout in TRAIL_LOCKOUT_DAYS_GRID:
                sub = [r for r in results
                       if r["d"] == d and r["q"] == q
                       and r["seg_trail_stop"] == trail_stop
                       and r["trail_lockout_days"] == lockout]
                if not sub:
                    continue
                r = sub[0]
                bk = r["name"]
                if bk not in sim_store:
                    continue
                eq2 = sim_store[bk]["eq"][sim_store[bk]["eq"].index >= test_ts]
                ls  = lockout_ls.get(lockout, "-")
                ax.semilogy(
                    eq2.index, eq2.values, lw=1.5, color=clr, ls=ls,
                    label=(f"{clabel} lock={lockout}d  "
                           f"${eq2.iloc[-1]:,.0f}  "
                           f"MaxDD={r['maxdd']:.1%}  "
                           f"Cal={r['calmar']:.2f}  "
                           f"TrHlt={r['trail_halt_count']}"),
                )

        ax.axhline(730_056, ls=":", lw=1.0, color="purple", alpha=0.5, label="v34 $730k")
        ax.set_title(f"v44 Rank-{ax_i+1}: d={d}, q={q}", fontweight="bold")
        ax.set_ylabel("Equity ($)")
        ax.legend(fontsize=7, loc="upper left")
        ax.grid(True, alpha=0.25)

    axes[-1].set_xlabel("Date")
    fig.suptitle(
        "v44: cb_v34_tight + Intra-segment Trailing Stop (Mode 1 Reversal Filter)",
        fontweight="bold", y=1.01,
    )
    out = PLOT_DIR / "v44_equity_trail_stop.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def plot_scatter_dd_v_calmar_v44(results: list[dict]) -> str:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    trail_colors = {
        None:  "#aaaaaa",
        0.040: "#ff7f0e",
        0.047: "#d62728",
        0.059: "#8B0000",
    }
    fig, ax = plt.subplots(figsize=(12, 7))
    for r in results:
        ts = r["seg_trail_stop"]
        clr = trail_colors.get(ts, "#888888")
        lbl = f"trail={ts:.3f}" if ts is not None else "Baseline"
        ax.scatter(r["maxdd"] * 100, r["calmar"], c=clr, alpha=0.6, s=60,
                   label=lbl)

    # De-duplicate legend
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), fontsize=9)

    ax.axhline(16.60, ls="--", lw=1, color="gray",  label="v40 Calmar=16.60")
    ax.axvline(-34.6, ls="--", lw=1, color="red",   label="v40 MaxDD=−34.6%")
    ax.set_xlabel("MaxDD (%)")
    ax.set_ylabel("Calmar")
    ax.set_title("v44: MaxDD vs Calmar  (colour = seg_trail_stop value)")
    ax.grid(True, alpha=0.25)
    out = PLOT_DIR / "v44_scatter_dd_calmar.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return str(out)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    t0_total = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    n_trail    = len(TOP3) * len(SEG_TRAIL_STOP_GRID) * len(TRAIL_LOCKOUT_DAYS_GRID)
    n_baseline = len(TOP3)
    n_total    = n_baseline + n_trail

    print(BAR)
    print("  CRYPTO GODMODE v44 — Intra-segment Trailing Stop (Mode 1 Reversal Filter)")
    print()
    print("  Mode 1 reversal geometry (v38_reversal_geometry.py):")
    print("    38a C0 LOSER: peaked +4.7% above CB-release → reversed to net -5.3% (skew=-4.4)")
    print("    38b C0 LOSER: peaked +5.9% above CB-release → reversed to net -5.1% (skew=-5.9)")
    print()
    print(f"  SEG_TRAIL_STOP grid:     {SEG_TRAIL_STOP_GRID}")
    print(f"  TRAIL_LOCKOUT_DAYS grid: {TRAIL_LOCKOUT_DAYS_GRID}")
    print(f"  Fixed CB:                halt={CB_HALT:.0%}  resume={CB_RESUME:.0%}  window={CB_WINDOW}d")
    print(f"  Fixed engine:            eta={ETA:.0e}  lm={LOCK_MIN}  km=None  om={OMEGA_THRESH}  ra={RHO_ALPHA}")
    print(f"  (d,q) TOP3:              {TOP3}")
    print(f"  Baselines:               {n_baseline}  (trail_stop=None)")
    print(f"  Trail variants:          {n_trail}")
    print(f"  Total:                   {n_total}")
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
        Sigma_cap, lam_g7 = Sigma_base, 0.0   # no G7 regularisation
        Sigma_w_sqrt, rank_Ix = fisher_weight_noise_sqrt(Sigma_cap)
        kp_raw = float(np.linalg.cond(Sigma_base))
        print(f"  d={d:.2f}: κ(Σ)={kp_raw:.2f}  rank(I_X)={rank_Ix}")
        sigma_store[d] = (Sigma_cap, Sigma_ffd, sdiag, bdiag, Sigma_w_sqrt, rank_Ix, lam_g7)

    # ── [3] Deterministic ODE sweeps ──────────────────────────────────────────
    print("\n[3] Running deterministic ODE sweeps ...")
    unit_store: dict[tuple, tuple] = {}

    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol)
                for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()

    for d, q in TOP3:
        Sigma_cap, _, sdiag, bdiag, _, rank_Ix, lam_g7 = sigma_store[d]
        theta     = theta_from(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)
        label_ode = (f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}_det_v44")
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

    # ── [4] CB simulation sweep ────────────────────────────────────────────────
    print(f"\n[4] Running v44 intra-segment trailing stop sweep ...")
    results:      list[dict]      = []
    sim_store_eq: dict[str, dict] = {}

    hdr = (f"  {'label':<75}  {'Calmar':>7}  {'Final':>12}  {'MaxDD':>7}  "
           f"{'r2026':>7}  {'pct_h':>6}  {'n_trp':>5}  {'TrHlt':>6}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for d, q in TOP3:
        Sigma_cap, _, sdiag, bdiag, _, rank_Ix, lam_g7 = sigma_store[d]
        unit, log_ann_dq, rho_typ_dq = unit_store[(d, q)]

        idx          = unit.index
        gamma_arr    = log_ann_dq["gamma"].reindex(idx).fillna(0.0).values
        rhs_norm_arr = log_ann_dq["rhs_norm"].reindex(idx).fillna(0.0).values
        rho_eff_arr  = log_ann_dq["rho_eff"].reindex(idx).fillna(rho_typ_dq).values

        # ── Baseline: no trail stop ────────────────────────────────────────
        label_base = (f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}"
                      f"_BASELINE_halt8r4w90")
        sim_base = simulate_combined_lockmin_v41(
            unit_normal=unit,
            unit_crash=pd.Series(0.0, index=unit.index),
            K_normal=K_NORMAL, K_crash=0.0,
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
            cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window_days=CB_WINDOW,
            eta=ETA, rank_Ix=rank_Ix, rho_typ=rho_typ_dq, lock_min=LOCK_MIN,
            gamma_arr=gamma_arr, rhs_norm_arr=rhs_norm_arr, rho_eff_arr=rho_eff_arr,
            omega_thresh=OMEGA_THRESH, rho_alpha=RHO_ALPHA,
            ramp_init=1.0, ramp_bars=168,
        )
        row_base = result_row_v44(
            label=label_base, sim=sim_base, test_ts=test_ts,
            d=d, q=q,
            seg_trail_stop=None, trail_lockout_days=0,
            rank_Ix=rank_Ix, lambda_g7=lam_g7, rho_typ=rho_typ_dq,
            sdiag=sdiag, bdiag=bdiag,
        )
        results.append(row_base)
        sim_store_eq[label_base] = sim_base
        print(f"  {label_base:<75}  {row_base['calmar']:>7.2f}  "
              f"${row_base['final']:>11,.0f}  {row_base['maxdd']:>7.1%}  "
              f"{row_base['r2026']:>+7.3f}  {sim_base.get('pct_halted',0):>6.1%}  "
              f"{sim_base.get('n_trips',0):>5}  "
              f"{sim_base.get('trail_halt_count',0):>6}  [BASELINE]")

        # ── Trail stop variants ────────────────────────────────────────────
        for trail_stop in SEG_TRAIL_STOP_GRID:
            for lockout_days in TRAIL_LOCKOUT_DAYS_GRID:
                label = (f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}"
                         f"_TR{int(trail_stop*1000):03d}_L{lockout_days:02d}d")

                sim = simulate_seg_trailstop_v44(
                    unit_normal=unit,
                    unit_crash=pd.Series(0.0, index=unit.index),
                    K_normal=K_NORMAL, K_crash=0.0,
                    dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                    cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window_days=CB_WINDOW,
                    eta=ETA, rank_Ix=rank_Ix, rho_typ=rho_typ_dq, lock_min=LOCK_MIN,
                    gamma_arr=gamma_arr, rhs_norm_arr=rhs_norm_arr, rho_eff_arr=rho_eff_arr,
                    omega_thresh=OMEGA_THRESH, rho_alpha=RHO_ALPHA,
                    seg_trail_stop=trail_stop,
                    trail_lockout_days=lockout_days,
                )
                sim_store_eq[label] = sim

                row = result_row_v44(
                    label=label, sim=sim, test_ts=test_ts,
                    d=d, q=q,
                    seg_trail_stop=trail_stop, trail_lockout_days=lockout_days,
                    rank_Ix=rank_Ix, lambda_g7=lam_g7, rho_typ=rho_typ_dq,
                    sdiag=sdiag, bdiag=bdiag,
                )
                results.append(row)

                print(f"  {label:<75}  {row['calmar']:>7.2f}  "
                      f"${row['final']:>11,.0f}  {row['maxdd']:>7.1%}  "
                      f"{row['r2026']:>+7.3f}  {sim.get('pct_halted',0):>6.1%}  "
                      f"{sim.get('n_trips',0):>5}  "
                      f"{sim.get('trail_halt_count',0):>6}")

    # ── [5] Summary ────────────────────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  v44 RESULTS SUMMARY")
    print(f"  Total variants: {len(results)}")
    print()

    # ── Baseline summary ──
    print("  Baselines (trail_stop=None):")
    print(f"  {'d':>5}  {'q':>5}  {'Calmar':>7}  {'Final':>12}  {'MaxDD':>7}  {'r2026':>7}")
    for r in results:
        if r["seg_trail_stop"] is None:
            print(f"  {r['d']:>5.2f}  {r['q']:>5.2f}  {r['calmar']:>7.2f}  "
                  f"${r['final']:>11,.0f}  {r['maxdd']:>7.1%}  {r['r2026']:>+7.3f}")

    # ── Best by MaxDD < -30% threshold ──
    print("\n  Trail-stop variants with MaxDD > -30% (better than v40 −34.6%):")
    dd30 = [r for r in results if r.get("maxdd", -99) > -0.30 and r["seg_trail_stop"] is not None]
    if dd30:
        dd30.sort(key=lambda r: -r["final"])
        print(f"  {'label':<60}  {'Calmar':>7}  {'Final':>12}  {'MaxDD':>7}  "
              f"{'r2026':>7}  {'TrHlt':>6}")
        for r in dd30[:10]:
            print(f"  {r['name']:<60}  {r['calmar']:>7.2f}  "
                  f"${r['final']:>11,.0f}  {r['maxdd']:>7.1%}  "
                  f"{r['r2026']:>+7.3f}  {r['trail_halt_count']:>6}")
    else:
        print("    (none)")

    # ── Best by MaxDD < -25% ──
    print("\n  Trail-stop variants with MaxDD > -25%:")
    dd25 = [r for r in results if r.get("maxdd", -99) > -0.25 and r["seg_trail_stop"] is not None]
    if dd25:
        dd25.sort(key=lambda r: -r["final"])
        print(f"  {'label':<60}  {'Calmar':>7}  {'Final':>12}  {'MaxDD':>7}  "
              f"{'r2026':>7}  {'TrHlt':>6}")
        for r in dd25[:10]:
            print(f"  {r['name']:<60}  {r['calmar']:>7.2f}  "
                  f"${r['final']:>11,.0f}  {r['maxdd']:>7.1%}  "
                  f"{r['r2026']:>+7.3f}  {r['trail_halt_count']:>6}")
    else:
        print("    (none)")

    # ── Best Calmar overall ──
    all_trail = [r for r in results if r["seg_trail_stop"] is not None]
    if all_trail:
        best_cal = max(all_trail, key=lambda r: r.get("calmar", 0))
        print(f"\n  Best Calmar (trail variants): {best_cal['name']}")
        print(f"    Calmar={best_cal['calmar']:.2f}  Final=${best_cal['final']:,.0f}  "
              f"MaxDD={best_cal['maxdd']:.1%}  r2026={best_cal.get('r2026',0):+.4f}  "
              f"TrHlt={best_cal['trail_halt_count']}  "
              f"OmBlk={best_cal['gate_blocks_omega']}  RhBlk={best_cal['gate_blocks_rho']}")

        best_fin = max(all_trail, key=lambda r: r.get("final", 0))
        print(f"\n  Best Final equity (trail variants): {best_fin['name']}")
        print(f"    Calmar={best_fin['calmar']:.2f}  Final=${best_fin['final']:,.0f}  "
              f"MaxDD={best_fin['maxdd']:.1%}  r2026={best_fin.get('r2026',0):+.4f}  "
              f"TrHlt={best_fin['trail_halt_count']}")

    # ── Per trail_stop sweep row ──
    print("\n  Per trail_stop × lockout_days sweep (d=0.25, q=0.50):")
    print(f"  {'trail_stop':>10}  {'lockout':>7}  {'Calmar':>7}  {'Final':>12}  "
          f"{'MaxDD':>7}  {'r2026':>7}  {'TrHlt':>6}  {'n_trips':>7}")
    base_dq = [r for r in results if r["d"] == 0.25 and r["q"] == 0.50]
    for r in base_dq:
        ts_fmt = f"{r['seg_trail_stop']:.3f}" if r['seg_trail_stop'] is not None else "   None"
        print(f"  {ts_fmt:>10}  {r['trail_lockout_days']:>7}  {r['calmar']:>7.2f}  "
              f"${r['final']:>11,.0f}  {r['maxdd']:>7.1%}  "
              f"{r['r2026']:>+7.3f}  {r['trail_halt_count']:>6}  {r['n_trips']:>7}")

    print(f"\n  Reference lines:")
    print(f"    v34/v35:  $730,056  Calmar=17.49  MaxDD=−35%    r2026=+7%")
    print(f"    v40/v41:  $617K     Calmar=16.60  MaxDD=−34.6%  OmBlk=4  RhBlk=0")
    print(f"    v43 best: $19,645   Calmar=N/A    MaxDD=−29.8%  [regime-switching killed returns]")

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

    out_json = OUT_DIR_ / "crypto_godmode_v44_seg_trailstop.json"
    rows_clean = [
        {k: v for k, v in r.items()
         if k not in ("sigma", "budget", "rho_eff_at_halt_log")
         and not isinstance(v, pd.Series)}
        for r in results
    ]
    with open(out_json, "w") as f:
        json.dump(
            {
                "version":    "v44",
                "cb":         "cb_v34_tight",
                "cb_halt":    CB_HALT,
                "cb_resume":  CB_RESUME,
                "cb_window":  CB_WINDOW,
                "trail_stop_grid":     SEG_TRAIL_STOP_GRID,
                "trail_lockout_grid":  TRAIL_LOCKOUT_DAYS_GRID,
                "rationale": {
                    "mode1_38a_c0_peak": "+4.7%  (seg peaked +4.7% then reversed to -5.3%)",
                    "mode1_38b_c0_peak": "+5.9%  (seg peaked +5.9% then reversed to -5.1%)",
                    "filter":            "equity-based trailing stop from local seg_peak_eq",
                    "lockout":           "shorter than main CB to limit false-positive cost",
                },
                "fixes": {
                    "Fix1_omega_gate":       "gamma * rhs_norm >= omega_thresh (still applied at CB release)",
                    "Fix2_saturating_budget": "E_inf*(1-exp(-rho_typ*lock_bars*DT))",
                    "Fix3_rho_eff_gate":      "rho_eff_at_halt < alpha*rho_typ → rho gate active",
                    "New_v44_trail_stop":     "if eq < seg_peak*(1-trail_stop) → trail halt for lockout_days",
                },
                "results": rows_clean,
            },
            f, indent=2, default=serialise,
        )
    print(f"  → {out_json}")

    # ── [7] Plots ──────────────────────────────────────────────────────────────
    print(f"\n[7] Generating plots ...")
    eq_path = plot_equity_v44(sim_store_eq, results, test_ts)
    print(f"  Equity curves: {eq_path}")
    sc_path = plot_scatter_dd_v_calmar_v44(results)
    print(f"  Scatter plot:  {sc_path}")

    elapsed = time.time() - t0_total
    print(f"\n{BAR}")
    print(f"  v44 COMPLETE  |  elapsed={elapsed:.1f}s  ({elapsed/60:.1f} min)")
    print(f"  Mode 1 filter: intra-segment trailing stop from seg_peak_eq")
    print(f"  Trail stop values: {SEG_TRAIL_STOP_GRID}  (4.0%, 4.7%=38a, 5.9%=38b)")
    print(f"  Trail lockout:     {TRAIL_LOCKOUT_DAYS_GRID}d")
    print(f"  Main CB unchanged: halt={CB_HALT:.0%}  resume={CB_RESUME:.0%}  window={CB_WINDOW}d")
    print(BAR)


if __name__ == "__main__":
    main()
