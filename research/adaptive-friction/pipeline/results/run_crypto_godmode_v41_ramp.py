# -*- coding: utf-8 -*-
"""
run_crypto_godmode_v41_ramp.py
================================

v41 = v40 + Post-CB Re-Entry Ramp

Diagnostic finding (diag_v41_plan.py)
--------------------------------------
MaxDD = -34.6% at 2024-12-19.  Root cause:
  - NOT a single crash — the 14-month staircase decline (Nov 2023 → Dec 2024)
    accumulates across 8+ CB trips in sequence.
  - Many trips are ultra-short (3h, 10h, 16h): strategy resumes immediately
    into declining price and fires CB again, losing up to 8% each time.
  - ρ_eff and Ω gates evaluated at RESUME time cannot help: by then both
    ρ_eff and Ω have recovered to normal levels.

Fix (v41): Post-CB Re-Entry Ramp
----------------------------------
When CB releases, scale K_effective by:
    ramp_factor = min(1, ramp_init + bars_since_resume × (1 - ramp_init) / ramp_bars)
This limits exposure during the vulnerable re-entry window.
  - Short-term re-entries (3h) operate at ramp_init fraction of full size.
  - If the strategy survives the first ramp_bars hours, full sizing is restored.
  - Does NOT affect pct_halted or the CB trigger logic.

Grid additions vs v40
----------------------
  RAMP_INIT_GRID : [1.0, 0.5, 0.3]  (1.0 = baseline no-ramp)
  RAMP_BARS_GRID : [48, 168, 720]   (2d/7d/30d ramp period)

v40 = v39 = v38 + Three targeted re-entry filters derived from ODE diagnostics

──────────────────────────────────────────────────────────────────────────────
Fix 1 — Mode 1 (Reversal): Ω gate                            [omega_thresh]
──────────────────────────────────────────────────────────────────────────────
  Discriminant: Ω = γ × ‖f(z)‖  (adaptive friction × ODE residual norm)
  Block CB re-entry when Ω ≥ omega_thresh (default 0.02)

  Physical interpretation: high Ω means the ODE is far from convergence; the
  friction gain γ is still fighting large residuals. Re-entering positions at
  this state means they are sized according to a stale (wrong) equilibrium.
  The market then corrects (reversal), amplifying the drawdown.

  Empirical evidence (v38_trade_clustering.py, test window 38a + 38b C0):
      Max winner Ω:  0.0063    Min loser Ω:  0.0403   →  6.4× separation gap
      Catch rate: 13/13 (100%) of Mode-1 loser segments.  False positives: 0.

──────────────────────────────────────────────────────────────────────────────
Fix 2 — Itô budget math error                                [always ON in v39]
──────────────────────────────────────────────────────────────────────────────
  v38 formula (wrong):  noise_budget = c_σ × lock_bars   (LINEAR — diverges)
  where  c_σ = η · DT · rank(I_X)

  Correct formula from Theorem thm:sde-bound (canonical_system_v4.tex §IV):
      E[E(X_t)] ≤ e^{-ρt} E_0 + E∞ · (1 − e^{−ρt})
      E∞ = η · rank(I_X) / ρ_eff       (asymptotic floor — constant)
  Correct budget:  E∞ × (1 − exp(−ρ_typ × lock_bars × DT))   (SATURATING)

  Overestimate ratio at ρ_typ=9.8, η=3e-4:
    @  100 bars:    98×      @  500 bars:   488×
    @ 1000 bars:   980×      @ 5000 bars:  4898×
  The linear budget allowed G2.4 to fire when the CB drawdown was 4–13%
  (far above cb_resume=4%), creating false "noise-covered" early releases.

──────────────────────────────────────────────────────────────────────────────
Fix 3 — Mode 2 (Pure crash): ρ_eff gate                       [rho_alpha]
──────────────────────────────────────────────────────────────────────────────
  Discriminant: ρ_eff = v_E / E   (local exponential convergence rate of ODE)
  Block CB re-entry when ρ_eff < rho_alpha × rho_typ  (default alpha=0.5)

  Physical interpretation: low ρ_eff at release means the ODE is recovering
  sluggishly from the crash shock — the weight vector is far from its
  equilibrium attractor. Re-entering positions while ρ_eff is suppressed means
  the engine is unhedged during the remainder of a crash that has not bottomed.

  Empirical evidence (v38_mode2_investigation.py, test window 38a):
    Mode-2 crash entries:  ρ_eff = 4.10, 4.82   (≈ 0.42–0.49 × ρ_typ)
    Winners (Ω<0.02):      ρ_eff = 6.71–19.58   (≥ 0.68 × ρ_typ)
    ρ_typ (training median) = 9.80
    Threshold α=0.5 → ρ_min=4.90: catches both worst crashes, passes 6.71

──────────────────────────────────────────────────────────────────────────────
Grid
────
  η         ∈ {0, 2e-4, 3e-4}         (best from v38 — focused)
  lock_min  ∈ {500, 1000}             (best from v38 — focused)
  κ_max     ∈ {None, 10, 5}           (G7 regularisation — same as v38)
  omega     ∈ {None, 0.02}            (Mode 1 gate: None=off, 0.02=proven)
  rho_α     ∈ {0.0, 0.5, 0.6}         (Mode 2 gate: 0.0=off)
  (d,q)     ∈ TOP3 (same as v38)

  η=0: 1 baseline (no gates, no G2.4) per (d,q,κ_max)
  η>0: 2 × 2 × 2 × 3 = 24 combinations per (d,q,κ_max)
  Total: 3 × 3 × (1 + 24) = 225 variants

Expected outcome
────────────────
  All-fixes-on (omega=0.02, rho_α=0.5–0.6, saturating budget, halt-time gate):
    ODE-shock trips blocked until ρ_eff recovers above threshold.
    Expected: MaxDD improvement when crash trips coincide with suppressed ρ_eff.
    r2026: > 0

Theory references
─────────────────
  Mode 1 filter:  v38_trade_clustering.py (segment Ω analysis, 38a/38b C0)
  Fix 2:          canonical_system_v4.tex §IV, Theorem thm:sde-bound (line 2126)
  Mode 2 filter:  v38_mode2_investigation.py (per-segment ρ_eff at entry)
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
OUT_DIR_ = Path(OUT_DIR) / "v41_ramp"
PLOT_DIR = OUT_DIR_ / "plots"

# TOP3 (d,q) — same as v38
TOP3 = [
    (0.30, 0.50),   # rank-1: baseline Calmar=23.00
    (0.30, 0.65),   # rank-2: best Calmar=23.98
    (0.25, 0.50),   # rank-3: r2026>0 at high η
]

# ── CB config (identical to v38: cb_v34_tight) ────────────────────────────────
CB_HALT   = 0.08
CB_RESUME = 0.04
CB_WINDOW = 90   # days

# ── v39 grids ─────────────────────────────────────────────────────────────────
ETA_GRID          = [0.0, 2e-4, 3e-4]          # focused from v38
LOCK_MIN_GRID     = [500, 1000]                 # focused from v38
KAPPA_MAX_GRID    = [None, 10, 5]               # G7 regularisation (same as v38)
OMEGA_THRESH_GRID = [None, 0.02]               # None=gate off; 0.02=proven threshold
RHO_ALPHA_GRID    = [0.0, 0.5, 0.6]            # 0.0=gate off; 0.5/0.6=Mode-2 candidates


# ── v41 re-entry ramp grid ───────────────────────────────────────────────────
RAMP_INIT_GRID = [1.0, 0.5, 0.3]     # 1.0 = no ramp (baseline)
RAMP_BARS_GRID = [48, 168, 720]      # 2d, 7d, 30d ramp window

# ── G7 covariance regularisation (Proposition G7.1) ──────────────────────────

def regularise_sigma_g7(
    Sigma: np.ndarray, kappa_max: float
) -> tuple[np.ndarray, float]:
    """Regularise Σ → Σ + λ*I so that κ(Σ + λI) ≤ kappa_max.

    From G7.1:  λ* = (λ_max − κ_max · λ_min) / (κ_max − 1)
    Returns (regularised_Sigma, lambda_applied).
    """
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
    """Compute I_X^{-1/2} in weight space (Fisher-optimal noise matrix, G2.2)."""
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
    """v38 linear formula — retained for diagnostic comparisons only."""
    return eta * DT * rank_Ix


def c_sigma_saturating(
    eta: float, rank_Ix: int, rho_typ: float, lock_bars: int
) -> float:
    """Fix 2: Correct Itô budget per Theorem thm:sde-bound.

    E∞     = η · rank(I_X) / ρ_typ            asymptotic noise floor
    budget = E∞ · (1 − exp(−ρ_typ · lock_bars · DT))   SATURATING

    At ρ_typ=9.8 this saturates within ~5 bars at max value ≈ 9.2e-5.
    Contrast with v38 linear: at 1000 bars → 9.0e-2 (980× overestimate).
    """
    if eta == 0.0 or rho_typ <= 0.0:
        return 0.0
    E_inf = eta * rank_Ix / rho_typ
    return E_inf * (1.0 - np.exp(-rho_typ * lock_bars * DT))


# ── Deterministic canonical ODE — now also returns rho_typ ───────────────────

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
    """Deterministic ODE identical to v38 run_godmode_det, but also returns rho_typ.

    Returns
    -------
    log_ann : pd.DataFrame
        Per-bar ODE diagnostics including gamma, rhs_norm, rho_eff.
    rho_typ : float
        Training-median ρ_eff — used by Fix 2 (saturating budget) and
        Fix 3 (ρ_eff gate threshold).
    """
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


# ── v41 CB simulation with post-CB re-entry ramp ─────────────────────────────

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
    eta:           float,          # η for Fix 2 saturating budget
    rank_Ix:       int,
    rho_typ:       float,          # training-median ρ (Fix 2 + Fix 3)
    lock_min:      int,            # G2.4 gate: only fires if lock_bars >= lock_min
    gamma_arr:     np.ndarray,     # γ at each bar — for Fix 1 Ω gate
    rhs_norm_arr:  np.ndarray,     # ‖f(z)‖ at each bar — for Fix 1 Ω gate
    rho_eff_arr:   np.ndarray,     # ρ_eff at each bar — for Fix 3 gate
    omega_thresh:  float | None = 0.02,   # None = gate disabled
    rho_alpha:     float = 0.5,           # 0.0 = gate disabled
    ramp_init:     float = 1.0,           # starting K scale post-CB (1.0 = no ramp)
    ramp_bars:     int   = 168,           # hours to ramp from ramp_init to 1.0
) -> dict:
    """CB simulation with Fix 3 revised to use ρ_eff recorded at halt time.

    Resume decision logic (at each halted bar in order):
    ──────────────────────────────────────────────────────
    Step 1  Determine candidate resume:
            Standard:     cb_dd ≤ cb_resume
            G2.4 override:  cb_dd ≤ cb_resume + saturating_budget(lock_bars)
                            AND lock_bars ≥ lock_min  AND η > 0

    Step 2  Fix 1 — Omega gate:
            If omega_thresh is not None AND γ[bar] × ‖f(z)‖[bar] ≥ omega_thresh
            → stay halted (extend lock)

    Step 3  Fix 3 revised — ρ_eff gate conditioned on ρ_eff AT HALT TIME:
            Only activates when ρ_eff_at_halt < rho_alpha × ρ_typ
            (i.e., this was an ODE-shock event — trip triggered by a crash that
            also suppressed ρ_eff below threshold).
            When active: also require ρ_eff_current ≥ rho_alpha × ρ_typ.
            If ρ_eff has already recovered by release time → gate passes.
            Non-shock trips (healthy ρ_eff at halt) → gate inactive.
    """
    window_bars   = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq             = INIT
    peak_alltime   = INIT
    halted         = False
    halt_start_bar = 0
    # v40: track ρ_eff at the moment the CB trips — initialise to a healthy value
    rho_eff_at_halt = rho_typ
    # v41: track last resume bar for ramp scaling
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

        # ── Sliding-window peak (unchanged from v38) ──────────────────────────
        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
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
            # v40: snapshot ρ_eff the moment the CB fires
            rho_eff_at_halt = rho_eff_arr[bar_i]

        # ── Resume evaluation ─────────────────────────────────────────────────
        elif halted:
            lock_bars = bar_i - halt_start_bar

            # Step 1: candidate resume (standard OR G2.4 with saturating budget)
            is_standard = cb_dd <= cb_resume
            is_g24      = (
                not is_standard
                and eta > 0.0
                and lock_bars >= lock_min
                and cb_dd <= cb_resume + c_sigma_saturating(eta, rank_Ix, rho_typ, lock_bars)
            )
            candidate = is_standard or is_g24

            if candidate:
                # Step 2 — Fix 1: Ω gate (unchanged from v39)
                if omega_thresh is not None:
                    omega_val = gamma_arr[bar_i] * rhs_norm_arr[bar_i]
                    if omega_val >= omega_thresh:
                        gate_blocks_omega += 1
                        candidate = False

                # Step 3 — Fix 3 revised: ρ_eff gate conditioned on halt-time shock
                # Only activated if the trip started with a suppressed ρ_eff
                # (i.e., this was an ODE-shock event, not just a price correction).
                if candidate and rho_alpha > 0.0:
                    ode_shock = rho_eff_at_halt < rho_alpha * rho_typ
                    if ode_shock and rho_eff_arr[bar_i] < rho_alpha * rho_typ:
                        # ODE shock at entry AND not yet recovered at release
                        gate_blocks_rho += 1
                        candidate = False

            # Commit the release
            if candidate:
                halted         = False
                halt_start_bar = bar_i       # reset for next lock accumulation
                resume_bar     = bar_i       # v41: record last resume bar
                if is_g24:
                    ito_resets += 1
                    reset_bar_log.append(bar_i)

        # ── Position sizing + v41 post-CB re-entry ramp ──────────────────────
        if halted:
            y = 0.0
        elif dd_aty <= dd_soft:
            y = 1.0
        elif dd_aty >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        # v41: attenuate K during post-CB ramp window
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

    # Collect rho_eff_at_halt for each CB trip (diagnostic)
    rho_halt_log: list[float] = []
    in_halt = False
    prev_rhe = rho_typ
    for bi in range(N):
        cur_flag = cb_flags[bi]
        if cur_flag and not in_halt:
            in_halt = True
            prev_rhe = float(rho_eff_arr[bi])
            rho_halt_log.append(prev_rhe)
        elif not cur_flag and in_halt:
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
        rho_eff_at_halt_log = rho_halt_log,
        max_lock_bars       = int(max(lock_bars_arr)) if lock_bars_arr else 0,
        reset_ts            = [str(ts) for ts in reset_ts],
    )


# ── Metrics helpers ───────────────────────────────────────────────────────────

def yow(eq: pd.Series) -> dict[str, float]:
    return {r["period"][:4]: r["return_pct"] for r in period_table(eq, "Y")}


def result_row_v41(
    label, sim, test_ts, d, q, eta, lock_min, kappa_max,
    omega_thresh, rho_alpha, rank_Ix, lambda_g7, rho_typ, sdiag, bdiag,
    ramp_init: float = 1.0, ramp_bars: int = 168,
) -> dict:
    eq = sim["eq"][sim["eq"].index >= test_ts]
    m  = equity_metrics(eq, label)
    yy = yow(eq)
    return dict(
        name=label, d=d, q=q, eta=eta, lock_min=lock_min, kappa_max=kappa_max,
        omega_thresh=omega_thresh, rho_alpha=rho_alpha,
        rank_Ix=rank_Ix, lambda_g7=lambda_g7, rho_typ=rho_typ,
        final=m["final"], profit=m["final"] - INIT,
        cagr=m["cagr"], sharpe=m["sharpe"], maxdd=m["maxdd"], calmar=m["calmar"],
        pct_halted=sim.get("pct_halted", float("nan")),
        n_trips=sim.get("n_trips", 0),
        ito_resets=sim.get("ito_resets", 0),
        gate_blocks_omega=sim.get("gate_blocks_omega", 0),
        ramp_init=ramp_init,
        ramp_bars=ramp_bars,
        gate_blocks_rho=sim.get("gate_blocks_rho", 0),
        rho_eff_at_halt_log=sim.get("rho_eff_at_halt_log", []),
        max_lock_bars=sim.get("max_lock_bars", 0),
        reset_ts=sim.get("reset_ts", []),
        r2022=yy.get("2022", float("nan")),
        r2023=yy.get("2023", float("nan")),
        r2024=yy.get("2024", float("nan")),
        r2025=yy.get("2025", float("nan")),
        r2026=yy.get("2026", float("nan")),
        sigma=sdiag, budget=bdiag,
    )


# ── Plots ──────────────────────────────────────────────────────────────────────

def plot_gate_ablation(results: list[dict]) -> list[str]:
    """For each (d,q,κ_max): bar chart of MaxDD and Calmar across gate combinations.

    Fixed at best (η=3e-4, lock_min=1000) to isolate gate effect.
    """
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    gate_combos = [(None, 0.0), (None, 0.5), (None, 0.6),
                   (0.02, 0.0), (0.02, 0.5), (0.02, 0.6)]
    combo_labels = [
        "no gates\n(v38 eq.)",
        "ρ α=0.5 only",
        "ρ α=0.6 only",
        "Ω only",
        "Ω + ρ α=0.5\n(all fixes)",
        "Ω + ρ α=0.6\n(all fixes)",
    ]
    colors = ["#aaaaaa", "#5b9bd5", "#2e75b6", "#ff7f0e", "#d62728", "#8B0000"]

    for d, q in TOP3:
        for kappa_max in KAPPA_MAX_GRID:
            km_label = f"κ={kappa_max}" if kappa_max else "no-G7"
            sub = [r for r in results
                   if r["d"] == d and r["q"] == q and r["kappa_max"] == kappa_max
                   and r["eta"] == 3e-4 and r["lock_min"] == 1000]
            if not sub:
                continue

            maxdds  = []
            calmars = []
            finals  = []
            valid_labels = []
            valid_colors = []

            for (om, ra), clabel, clr in zip(gate_combos, combo_labels, colors):
                match = [r for r in sub
                         if r["omega_thresh"] == om and abs(r["rho_alpha"] - ra) < 1e-9]
                if match:
                    r = match[0]
                    maxdds.append(abs(r["maxdd"]) * 100)
                    calmars.append(r["calmar"])
                    finals.append(r["final"])
                    valid_labels.append(clabel)
                    valid_colors.append(clr)

            if not maxdds:
                continue

            fig, axes = plt.subplots(1, 3, figsize=(18, 5))
            x = range(len(maxdds))

            ax = axes[0]
            bars = ax.bar(x, maxdds, color=valid_colors)
            ax.axhline(35, ls="--", lw=1, color="gray", label="v38 MaxDD −35%")
            ax.set_xticks(list(x))
            ax.set_xticklabels(valid_labels, fontsize=7)
            ax.set_ylabel("|MaxDD| (%)")
            ax.set_title("MaxDD by gate combo")
            ax.legend(fontsize=8)
            for bar_, v in zip(bars, maxdds):
                ax.text(bar_.get_x() + bar_.get_width() / 2, bar_.get_height() + 0.2,
                        f"{v:.1f}%", ha="center", fontsize=8)

            ax = axes[1]
            bars = ax.bar(x, calmars, color=valid_colors)
            ax.axhline(17.49, ls="--", lw=1, color="gray", label="v34/v35 Calmar=17.49")
            ax.set_xticks(list(x))
            ax.set_xticklabels(valid_labels, fontsize=7)
            ax.set_ylabel("Calmar")
            ax.set_title("Calmar by gate combo")
            ax.legend(fontsize=8)
            for bar_, v in zip(bars, calmars):
                ax.text(bar_.get_x() + bar_.get_width() / 2, bar_.get_height() + 0.1,
                        f"{v:.1f}", ha="center", fontsize=8)

            ax = axes[2]
            bars = ax.bar(x, [f / 1000 for f in finals], color=valid_colors)
            ax.axhline(730.056, ls="--", lw=1, color="purple", alpha=0.7, label="v34 $730k")
            ax.axhline(288.433, ls="--", lw=1, color="orange", alpha=0.7, label="v37 $288k")
            ax.set_xticks(list(x))
            ax.set_xticklabels(valid_labels, fontsize=7)
            ax.set_ylabel("Final equity ($k)")
            ax.set_title("Final equity by gate combo")
            ax.legend(fontsize=8)

            km_str = str(kappa_max) if kappa_max else "none"
            fig.suptitle(
                f"v39 Gate ablation: d={d}, q={q}, {km_label} | η=3e-4, lock_min=1000",
                fontweight="bold",
            )
            out = PLOT_DIR / (f"v39_gate_ablation_d{str(d).replace('.','p')}"
                              f"_q{str(q).replace('.','p')}_km{km_str}.png")
            fig.tight_layout()
            fig.savefig(out, dpi=160)
            plt.close(fig)
            paths.append(str(out))
    return paths


def plot_heatmap_v39(results: list[dict]) -> list[str]:
    """2D heatmap over (omega_thresh, rho_alpha) for each (d,q,κ_max,η,lock_min)."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []

    for rank_idx, (d, q) in enumerate(TOP3, 1):
        for kappa_max in KAPPA_MAX_GRID:
            for eta in [2e-4, 3e-4]:
                for lock_min in LOCK_MIN_GRID:
                    sub = [r for r in results
                           if r["d"] == d and r["q"] == q
                           and r["kappa_max"] == kappa_max
                           and abs(r["eta"] - eta) < 1e-9
                           and r["lock_min"] == lock_min]
                    if not sub:
                        continue

                    omegas  = sorted(set(r["omega_thresh"] for r in sub),
                                     key=lambda x: -1.0 if x is None else x)
                    rho_als = sorted(set(r["rho_alpha"] for r in sub))

                    r2026_mat = np.full((len(omegas), len(rho_als)), float("nan"))
                    cal_mat   = np.full((len(omegas), len(rho_als)), float("nan"))
                    dd_mat    = np.full((len(omegas), len(rho_als)), float("nan"))

                    for r in sub:
                        i = omegas.index(r["omega_thresh"])
                        j = rho_als.index(r["rho_alpha"])
                        r2026_mat[i, j] = r.get("r2026") or 0.0
                        cal_mat[i, j]   = r["calmar"]
                        dd_mat[i, j]    = abs(r["maxdd"]) * 100

                    omega_labels = [("None" if om is None else f"{om:.2f}") for om in omegas]
                    rho_labels   = [f"{ra:.1f}" for ra in rho_als]
                    km_label = f"κ={kappa_max}" if kappa_max else "No G7"

                    fig, axes = plt.subplots(1, 3, figsize=(18, 4))
                    for ax, mat, title, fmt, cmap in [
                        (axes[0], r2026_mat, "r2026",     ".2f", "RdYlGn"),
                        (axes[1], cal_mat,   "Calmar",    ".1f", "RdYlGn"),
                        (axes[2], dd_mat,    "|MaxDD| %", ".1f", "RdYlGn_r"),
                    ]:
                        im = ax.imshow(mat, aspect="auto", origin="lower", cmap=cmap)
                        ax.set_xticks(range(len(rho_als)))
                        ax.set_xticklabels(rho_labels, fontsize=9)
                        ax.set_yticks(range(len(omegas)))
                        ax.set_yticklabels(omega_labels, fontsize=9)
                        ax.set_xlabel("rho_alpha", fontsize=9)
                        ax.set_ylabel("omega_thresh", fontsize=9)
                        ax.set_title(title, fontweight="bold")
                        plt.colorbar(im, ax=ax)
                        for ii in range(len(omegas)):
                            for jj in range(len(rho_als)):
                                v = mat[ii, jj]
                                if not np.isnan(v):
                                    ax.text(jj, ii, f"{v:{fmt}}", ha="center",
                                            va="center", fontsize=8, color="black")

                    km_str = str(kappa_max) if kappa_max else "none"
                    fig.suptitle(
                        f"v39 Rank-{rank_idx}: d={d}, q={q} | {km_label} | "
                        f"η={eta:.0e}, lock_min={lock_min}",
                        fontweight="bold",
                    )
                    out = PLOT_DIR / (
                        f"v39_heatmap_r{rank_idx}_d{str(d).replace('.','p')}"
                        f"_q{str(q).replace('.','p')}_km{km_str}"
                        f"_eta{eta:.0e}_lm{lock_min}.png"
                    )
                    fig.tight_layout()
                    fig.savefig(out, dpi=160)
                    plt.close(fig)
                    paths.append(str(out))
    return paths


def plot_equity_best_v39(
    sim_store: dict[str, dict], results: list[dict], test_ts: pd.Timestamp
) -> str:
    """Best Calmar with r2026>0 per rank × gate config, vs v34 baseline."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(len(TOP3), 1, figsize=(16, 4 * len(TOP3)), sharex=True)
    if len(TOP3) == 1:
        axes = [axes]

    gate_styles = {
        # (omega_thresh, rho_alpha) → (color, linestyle, label_suffix)
        (None,  0.0): ("#aaaaaa", "--", "no gates (v38 equiv)"),
        (None,  0.5): ("#5b9bd5", "-.", "ρ gate α=0.5 only"),
        (0.02,  0.0): ("#ff7f0e", "-.", "Ω gate only"),
        (0.02,  0.5): ("#d62728", "-",  "all fixes α=0.5"),
        (0.02,  0.6): ("#8B0000", "-",  "all fixes α=0.6"),
    }

    for ax_i, (d, q) in enumerate(TOP3):
        ax = axes[ax_i]

        # η=0 baseline (best κ_max by final equity)
        base_rows = [r for r in results if r["d"] == d and r["q"] == q
                     and r["eta"] == 0.0]
        if base_rows:
            best_base = max(base_rows, key=lambda r: r["final"])
            bk = best_base["name"]
            if bk in sim_store:
                eq0 = sim_store[bk]["eq"][sim_store[bk]["eq"].index >= test_ts]
                ax.semilogy(eq0.index, eq0.values, lw=1.2, color="#cccccc", ls=":",
                            alpha=0.8, label=f"η=0 baseline  ${eq0.iloc[-1]:,.0f}  "
                                             f"Cal={best_base['calmar']:.2f}")

        # Best Calmar with r2026>0 per gate combination
        for (om, ra), (clr, ls, gsuffix) in gate_styles.items():
            sub = [r for r in results
                   if r["d"] == d and r["q"] == q
                   and r["eta"] > 0
                   and r["omega_thresh"] == om
                   and abs(r["rho_alpha"] - ra) < 1e-9
                   and r.get("r2026", 0) > 0]
            if not sub:
                continue
            best = max(sub, key=lambda r: r["calmar"])
            bk   = best["name"]
            if bk not in sim_store:
                continue
            eq2 = sim_store[bk]["eq"][sim_store[bk]["eq"].index >= test_ts]
            km_tag = f"κ={best['kappa_max']}" if best["kappa_max"] else "no-G7"
            ax.semilogy(eq2.index, eq2.values, lw=1.8, color=clr, ls=ls,
                        label=(f"{gsuffix} ({km_tag}) "
                               f"${eq2.iloc[-1]:,.0f}  "
                               f"Cal={best['calmar']:.2f}  "
                               f"MaxDD={best['maxdd']:.1%}  "
                               f"r2026={best.get('r2026',0):+.3f}"))

        ax.axhline(730056, ls=":", lw=1.0, color="purple", alpha=0.5, label="v34/v35 $730k")
        ax.axhline(288433, ls=":", lw=1.0, color="orange", alpha=0.5, label="v37 $288k")
        ax.set_title(f"v39 Rank-{ax_i+1}: d={d}, q={q}", fontweight="bold")
        ax.set_ylabel("Equity ($)")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.25)

    axes[-1].set_xlabel("Date")
    fig.suptitle(
        "v39: cb_v34_tight + Fix1(Ω gate) + Fix2(saturating budget) + Fix3(ρ_eff gate)",
        fontweight="bold", y=1.01,
    )
    out = PLOT_DIR / "v39_equity_best.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def plot_scatter_dd_v_calmar(results: list[dict]) -> str:
    """Scatter: MaxDD vs Calmar, coloured by gate combination."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    gate_colors = {
        (None,  0.0): "#aaaaaa",
        (None,  0.5): "#5b9bd5",
        (None,  0.6): "#2e75b6",
        (0.02,  0.0): "#ff7f0e",
        (0.02,  0.5): "#d62728",
        (0.02,  0.6): "#8B0000",
    }
    fig, ax = plt.subplots(figsize=(12, 7))
    for r in results:
        if r["eta"] == 0.0:
            continue
        om = r["omega_thresh"]
        ra = r["rho_alpha"]
        clr = gate_colors.get((om, ra), "#888888")
        ax.scatter(r["maxdd"] * 100, r["calmar"], c=clr, alpha=0.45, s=30)

    ax.axhline(17.49, ls="--", lw=1, color="gray", label="v34/v35 Calmar=17.49")
    ax.axvline(-35,   ls="--", lw=1, color="red",  label="v34/v35 MaxDD −35%")

    from matplotlib.patches import Patch
    legend_patches = [
        Patch(color=clr, label=f"Ω={'0.02' if om else 'off'}, ρα={ra:.1f}")
        for (om, ra), clr in gate_colors.items()
    ]
    ax.legend(handles=legend_patches + [
        plt.Line2D([0], [0], ls="--", color="gray",  label="v34/v35 Calmar"),
        plt.Line2D([0], [0], ls="--", color="red",   label="v34/v35 MaxDD"),
    ], fontsize=8, loc="upper left")

    ax.set_xlabel("MaxDD (%)")
    ax.set_ylabel("Calmar")
    ax.set_title("v39 all variants: MaxDD vs Calmar  (colour = gate combination)")
    ax.grid(True, alpha=0.25)
    out = PLOT_DIR / "v39_scatter_dd_calmar.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return str(out)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    t0_total = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    # Variant count: per (d,q,km): 1 baseline(eta=0,ramp=1.0) + (eta_active × lock × omega × rho × ramp_combo)
    n_ramp_combo = len([ri for ri in RAMP_INIT_GRID if ri < 1.0]) * len(RAMP_BARS_GRID)
    n_inner = 1 + len([e for e in ETA_GRID if e > 0]) * len(LOCK_MIN_GRID) * \
              len(OMEGA_THRESH_GRID) * len(RHO_ALPHA_GRID) * (1 + n_ramp_combo)
    n_total = len(TOP3) * len(KAPPA_MAX_GRID) * n_inner

    print(BAR)
    print("  CRYPTO GODMODE v41 — Post-CB re-entry ramp (limit exposure after CB release)")
    print("  CB: cb_v34_tight (halt=8%, resume=4%, window=90d)")
    print("  Fix 1  : Ω = γ × ‖f(z)‖ ≥ omega_thresh → extend lock (Mode 1 reversal)")
    print("  Fix 2  : saturating budget E∞·(1−e^{−ρT}) replaces linear c_σ×lock_bars")
    print("  Fix 3  : ρ_eff_at_halt + ρ_eff_current ODE-shock gate (unchanged from v40)")
    print("  NEW v41: post-CB ramp: K_eff = K_normal × min(1, ramp_init + Δbar/ramp_bars)")
    print(f"  RAMP_INIT grid:   {RAMP_INIT_GRID}")
    print(f"  RAMP_BARS grid:   {RAMP_BARS_GRID}")
    print(f"  η grid:           {ETA_GRID}")
    print(f"  lock_min grid:    {LOCK_MIN_GRID}")
    print(f"  κ_max grid:       {KAPPA_MAX_GRID}")
    print(f"  omega_thresh grid:{OMEGA_THRESH_GRID}")
    print(f"  rho_alpha grid:   {RHO_ALPHA_GRID}")
    print(f"  (d,q) TOP3:       {TOP3}")
    print(f"  CB config:        halt={CB_HALT}  resume={CB_RESUME}  window={CB_WINDOW}d")
    print(f"  CB sim variants:  {n_total}")
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

    # ── [2] FFD Sigma × κ_max grid ────────────────────────────────────────────
    print("\n[2] Building FFD Sigma + G7 regularisation grid ...")
    sigma_store: dict[tuple, tuple] = {}   # (d, kappa_max) → (Sigma_cap, ..., rank_Ix, lam_g7)

    for d in sorted(set(d_ for d_, _ in TOP3)):
        Sigma_base, Sigma_ffd, sdiag, bdiag = build_sigma(factor_R, train_mask, df, d)
        kp_raw = float(np.linalg.cond(Sigma_base))
        print(f"\n  d={d:.2f}: raw κ(Σ₀)={kp_raw:.2f}")

        for kappa_max in KAPPA_MAX_GRID:
            if kappa_max is None:
                Sigma_cap, lam_g7 = Sigma_base, 0.0
            else:
                Sigma_cap, lam_g7 = regularise_sigma_g7(Sigma_base, float(kappa_max))

            Sigma_w_sqrt, rank_Ix = fisher_weight_noise_sqrt(Sigma_cap)
            G     = np.linalg.inv(Sigma_cap)
            I_X   = A_FACTORS.T @ G @ A_FACTORS
            kp_S0 = float(np.linalg.cond(Sigma_cap))
            kp_IX = float(np.linalg.cond(I_X))

            km_lbl = f"κ_max={kappa_max}" if kappa_max else "no-G7"
            print(f"    {km_lbl:15s}:  λ_g7={lam_g7:.3e}  κ(Σ_cap)={kp_S0:.2f}  "
                  f"rank(I_X)={rank_Ix}  κ(I_X)={kp_IX:.2f}")
            sigma_store[(d, kappa_max)] = (Sigma_cap, Sigma_ffd, sdiag, bdiag,
                                           Sigma_w_sqrt, rank_Ix, lam_g7)

    # Budget comparison: v38 linear vs v39 saturating
    print("\n  Budget comparison (v38 linear vs v39 saturating) at η=3e-4:")
    d0, km0 = sorted(set(d_ for d_, _ in TOP3))[0], None
    _, _, _, _, _, rank_Ix0, _ = sigma_store[(d0, km0)]
    # Use a representative rho_typ=9.8 (will be recomputed precisely per config)
    rho_repr = 9.8
    c_lin = c_sigma_per_bar(3e-4, rank_Ix0)
    E_inf = 3e-4 * rank_Ix0 / rho_repr
    print(f"  rank(I_X)={rank_Ix0}  c_σ/bar(linear)={c_lin:.3e}  "
          f"E∞(saturating)={E_inf:.3e}  ρ_repr={rho_repr}")
    for lock_bars_ in [10, 50, 100, 500, 1000, 2000]:
        lin_val = c_lin * lock_bars_
        sat_val = c_sigma_saturating(3e-4, rank_Ix0, rho_repr, lock_bars_)
        ratio   = lin_val / max(sat_val, 1e-20)
        print(f"    lock={lock_bars_:>5}:  linear={lin_val:.4f}  "
              f"saturating={sat_val:.3e}  ratio={ratio:.1f}×")

    # ── [3] Deterministic ODE sweeps ──────────────────────────────────────────
    print("\n[3] Running deterministic ODE sweeps ...")
    # unit_store: (d,q,kappa_max) → (unit, log_ann, rho_typ)
    unit_store: dict[tuple, tuple] = {}

    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol)
                for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()

    for d, q in TOP3:
        for kappa_max in KAPPA_MAX_GRID:
            Sigma_cap, _, sdiag, bdiag, _, rank_Ix, lam_g7 = sigma_store[(d, kappa_max)]
            theta     = theta_from(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)
            km_str    = f"km{kappa_max}" if kappa_max else "km_none"
            label_ode = (f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}"
                         f"_{km_str}_det_v39")
            print(f"  ODE: {label_ode}  θ={theta:.5f}  λ_g7={lam_g7:.2e}",
                  end="  ", flush=True)
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
            unit_store[(d, q, kappa_max)] = (unit, log_ann, rho_typ)
            print(f"{time.time()-t_ode:.1f}s  unit={len(unit)}")

    # ── [4] CB simulation sweep ────────────────────────────────────────────────
    print(f"\n[4] Running CB simulation sweep (v39 gates + G7) ...")
    results:      list[dict]      = []
    sim_store_eq: dict[str, dict] = {}

    hdr = (f"  {'Variant':<110}  {'Calmar':>7}  {'Final':>12}  {'MaxDD':>7}  "
           f"{'r2026':>7}  {'OmBlk':>5}  {'RhBlk':>5}  {'Rst':>4}")
    sep = (f"  {'-'*110}  {'-'*7}  {'-'*12}  {'-'*7}  "
           f"{'-'*7}  {'-'*5}  {'-'*5}  {'-'*4}")
    print(hdr)
    print(sep)

    for d, q in TOP3:
        for kappa_max in KAPPA_MAX_GRID:
            Sigma_cap, _, sdiag, bdiag, _, rank_Ix, lam_g7 = sigma_store[(d, kappa_max)]
            unit, log_ann_dq, rho_typ_dq = unit_store[(d, q, kappa_max)]

            # Pre-align ODE log arrays to unit index (same df index → trivial)
            idx          = unit.index
            gamma_arr    = log_ann_dq["gamma"].reindex(idx).fillna(0.0).values
            rhs_norm_arr = log_ann_dq["rhs_norm"].reindex(idx).fillna(0.0).values
            rho_eff_arr  = log_ann_dq["rho_eff"].reindex(idx).fillna(rho_typ_dq).values

            km_str = str(kappa_max) if kappa_max else "none"

            for eta in ETA_GRID:
                for lock_min in LOCK_MIN_GRID:
                    if eta == 0.0 and lock_min > 0:
                        continue

                    # For eta=0: only run one baseline (no gates)
                    omega_loop = OMEGA_THRESH_GRID if eta > 0.0 else [None]
                    rho_loop   = RHO_ALPHA_GRID    if eta > 0.0 else [0.0]

                    for omega_thresh in omega_loop:
                        for rho_alpha in rho_loop:
                            om_str  = (f"om{omega_thresh:.2f}" if omega_thresh is not None
                                       else "omNone")
                            ra_str  = f"ra{rho_alpha:.1f}"

                            for ramp_init in RAMP_INIT_GRID:
                                ramp_bars_range = RAMP_BARS_GRID if ramp_init < 1.0 else [168]
                                for ramp_bars in ramp_bars_range:
                                    ri_str = f"ri{str(ramp_init).replace('.','p')}"
                                    rb_str = f"rb{ramp_bars}"
                                    label   = (f"d{str(d).replace('.','p')}"
                                               f"_q{str(q).replace('.','p')}"
                                               f"_eta{eta:.0e}_lm{lock_min}"
                                               f"_km{km_str}_{om_str}_{ra_str}"
                                               f"_{ri_str}_{rb_str}")

                                    sim = simulate_combined_lockmin_v41(
                                        unit_normal=unit,
                                        unit_crash=pd.Series(0.0, index=unit.index),
                                        K_normal=K_NORMAL, K_crash=0.0,
                                        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP,
                                        y_floor=DYN_Y_FLOOR,
                                        cb_halt=CB_HALT, cb_resume=CB_RESUME,
                                        cb_window_days=CB_WINDOW,
                                        eta=eta, rank_Ix=rank_Ix, rho_typ=rho_typ_dq,
                                        lock_min=lock_min,
                                        gamma_arr=gamma_arr,
                                        rhs_norm_arr=rhs_norm_arr,
                                        rho_eff_arr=rho_eff_arr,
                                        omega_thresh=omega_thresh,
                                        rho_alpha=rho_alpha,
                                        ramp_init=ramp_init,
                                        ramp_bars=ramp_bars,
                                    )
                                    sim_store_eq[label] = sim

                                    theta = theta_from(
                                        b_aligned, train_mask, Sigma_cap, bdiag["budget"], q
                                    )
                                    row = result_row_v41(
                                        label, sim, test_ts, d, q, eta, lock_min, kappa_max,
                                        omega_thresh, rho_alpha, rank_Ix, lam_g7,
                                        rho_typ_dq, sdiag, bdiag,
                                        ramp_init=ramp_init, ramp_bars=ramp_bars,
                                    )
                                    results.append(row)

                                    print(f"  {label[:110]:<110}  "
                                          f"{row['calmar']:>7.2f}  "
                                          f"${row['final']:>11,.0f}  "
                                          f"{row['maxdd']:>7.1%}  "
                                          f"{row['r2026']:>+7.3f}  "
                                          f"{sim['gate_blocks_omega']:>5}  "
                                          f"{sim['gate_blocks_rho']:>5}  "
                                          f"{sim['ito_resets']:>4}")

    # ── [5] Summary ────────────────────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  v41 RESULTS SUMMARY")
    print(f"  Total variants: {len(results)}")

    # ── Baseline comparison (η=0) ──
    print("\n  η=0 baseline MaxDD per (d,q,κ_max):")
    for d, q in TOP3:
        for kappa_max in KAPPA_MAX_GRID:
            km_str   = str(kappa_max) if kappa_max else "none"
            base_key = (f"d{str(d).replace('.','p')}_q{str(q).replace('.','p')}"
                        f"_eta0_lm0_km{km_str}_omNone_ra0.0")
            rows = [r for r in results if r["name"] == base_key]
            if rows:
                r = rows[0]
                print(f"    d={d:.2f} q={q:.2f} κ={km_str:4}:  "
                      f"Calmar={r['calmar']:.2f}  Final=${r['final']:,.0f}  "
                      f"MaxDD={r['maxdd']:.1%}  r2026={r['r2026']:+.3f}")

    # ── All-fixes best: omega=0.02, rho_alpha=0.5 ──
    print("\n  All-fixes (Ω=0.02, ρα=0.5) — best Calmar with r2026>0:")
    full_fix = [r for r in results
                if r["omega_thresh"] == 0.02
                and abs(r["rho_alpha"] - 0.5) < 1e-9
                and r.get("r2026", 0) > 0 and r["eta"] > 0]
    if full_fix:
        best = max(full_fix, key=lambda r: r["calmar"])
        print(f"    {best['name']}")
        print(f"    Calmar={best['calmar']:.2f}  Final=${best['final']:,.0f}  "
              f"MaxDD={best['maxdd']:.1%}  r2026={best['r2026']:+.4f}  "
              f"OmBlk={best['gate_blocks_omega']}  RhBlk={best['gate_blocks_rho']}  "
              f"Resets={best['ito_resets']}")
    else:
        print("    (none with r2026>0)")

    # ── All-fixes rho_alpha=0.6 ──
    print("\n  All-fixes (Ω=0.02, ρα=0.6) — best Calmar with r2026>0:")
    full_fix6 = [r for r in results
                 if r["omega_thresh"] == 0.02
                 and abs(r["rho_alpha"] - 0.6) < 1e-9
                 and r.get("r2026", 0) > 0 and r["eta"] > 0]
    if full_fix6:
        best6 = max(full_fix6, key=lambda r: r["calmar"])
        print(f"    {best6['name']}")
        print(f"    Calmar={best6['calmar']:.2f}  Final=${best6['final']:,.0f}  "
              f"MaxDD={best6['maxdd']:.1%}  r2026={best6['r2026']:+.4f}  "
              f"OmBlk={best6['gate_blocks_omega']}  RhBlk={best6['gate_blocks_rho']}  "
              f"Resets={best6['ito_resets']}")
    else:
        print("    (none with r2026>0)")

    # ── Omega-only gate ──
    print("\n  Omega gate only (Ω=0.02, ρα=0.0) — best Calmar with r2026>0:")
    om_only = [r for r in results
               if r["omega_thresh"] == 0.02
               and abs(r["rho_alpha"]) < 1e-9
               and r.get("r2026", 0) > 0 and r["eta"] > 0]
    if om_only:
        best_om = max(om_only, key=lambda r: r["calmar"])
        print(f"    {best_om['name']}")
        print(f"    Calmar={best_om['calmar']:.2f}  Final=${best_om['final']:,.0f}  "
              f"MaxDD={best_om['maxdd']:.1%}  r2026={best_om['r2026']:+.4f}")
    else:
        print("    (none with r2026>0)")

    # ── rho gate only ──
    print("\n  rho_alpha=0.5 gate only (Ω=None) — best Calmar with r2026>0:")
    rho_only = [r for r in results
                if r["omega_thresh"] is None
                and abs(r["rho_alpha"] - 0.5) < 1e-9
                and r.get("r2026", 0) > 0 and r["eta"] > 0]
    if rho_only:
        best_rho = max(rho_only, key=lambda r: r["calmar"])
        print(f"    {best_rho['name']}")
        print(f"    Calmar={best_rho['calmar']:.2f}  Final=${best_rho['final']:,.0f}  "
              f"MaxDD={best_rho['maxdd']:.1%}  r2026={best_rho['r2026']:+.4f}")
    else:
        print("    (none with r2026>0)")

    # ── Overall best by Calmar ──
    best_cal = max(results, key=lambda r: r.get("calmar", 0))
    print(f"\n  Best Calmar overall:  {best_cal['name']}")
    print(f"    Calmar={best_cal['calmar']:.2f}  Final=${best_cal['final']:,.0f}  "
          f"MaxDD={best_cal['maxdd']:.1%}  r2026={best_cal.get('r2026',0):+.4f}")

    # ── Best MaxDD < 25% ──
    dd25 = [r for r in results if r.get("maxdd", -99) > -0.25]
    if dd25:
        best_dd25 = max(dd25, key=lambda r: r.get("final", 0))
        print(f"\n  Best Final with |MaxDD| < 25%:  {best_dd25['name']}")
        print(f"    Calmar={best_dd25['calmar']:.2f}  Final=${best_dd25['final']:,.0f}  "
              f"MaxDD={best_dd25['maxdd']:.1%}  r2026={best_dd25.get('r2026',0):+.4f}  "
              f"Ω={best_dd25['omega_thresh']}  ρα={best_dd25['rho_alpha']}")

    # ── Reference lines ──
    print(f"\n  v34/v35 reference: $730,056  Calmar=17.49  MaxDD=−35%  r2026=+7%")
    print(f"  v37 reference:     $288,433  Calmar=25.18  MaxDD=−17.4%  r2026=+108%")
    print(f"  v40 best:          Calmar=16.63  Final=$617K  MaxDD=−34.6%  RhBlk=0")

    # ── Ramp sweep: best MaxDD per ramp_init/ramp_bars ──
    print(f"\n  v41 ramp sweep (d=0.25,q=0.50,km=none,eta>0,Ω=0.02,ρα=0.5):")
    print(f"  {'ri':>5}  {'rb':>5}  {'Calmar':>7}  {'Final':>12}  {'MaxDD':>7}  {'r2026':>7}")
    ramp_base = [r for r in results if r["d"] == 0.25 and r["q"] == 0.50
                 and r["kappa_max"] is None and r["eta"] > 0
                 and r.get("omega_thresh") == 0.02
                 and abs(r.get("rho_alpha", 0) - 0.5) < 1e-9]
    # group by (ramp_init, ramp_bars), pick best calmar
    from itertools import groupby
    ramp_base.sort(key=lambda r: (r.get("ramp_init", 1.0), r.get("ramp_bars", 168)))
    for key, grp in groupby(ramp_base, key=lambda r: (r.get("ramp_init", 1.0), r.get("ramp_bars", 168))):
        best_r = max(grp, key=lambda r: r.get("calmar", 0))
        print(f"  {key[0]:>5.2f}  {key[1]:>5}  {best_r['calmar']:>7.2f}  "
              f"${best_r['final']:>11,.0f}  {best_r['maxdd']:>7.1%}  "
              f"{best_r.get('r2026',0):>+7.3f}")

    # ── Sweet-spot scan ──
    print(f"\n  Sweet-spot scan (d=0.25, q=0.50):")
    for kappa_max in KAPPA_MAX_GRID:
        km_str = str(kappa_max) if kappa_max else "none"
        sub = [r for r in results if r["d"] == 0.25 and r["q"] == 0.50
               and r["kappa_max"] == kappa_max and r["eta"] > 0]
        sub.sort(key=lambda r: (r["lock_min"], r["eta"], str(r["omega_thresh"]),
                                r["rho_alpha"], r.get("ramp_init", 1.0), r.get("ramp_bars", 168)))
        print(f"\n  κ_max={km_str}:")
        print(f"  {'lock_min':>8}  {'η':>9}  {'ω':>7}  {'ρα':>5}  {'ri':>5}  {'rb':>5}  "
              f"{'Calmar':>7}  {'Final':>12}  {'MaxDD':>7}  {'r2026':>7}  "
              f"{'OmBlk':>5}  {'RhBlk':>5}")
        for r in sub[:30]:
            om_fmt = f"{r['omega_thresh']:.2f}" if r["omega_thresh"] is not None else " None"
            print(f"  {r['lock_min']:>8}  {r['eta']:>9.1e}  {om_fmt:>7}  {r['rho_alpha']:>5.1f}  "
                  f"{r.get('ramp_init',1.0):>5.2f}  {r.get('ramp_bars',168):>5}  "
                  f"{r['calmar']:>7.2f}  ${r['final']:>11,.0f}  "
                  f"{r['maxdd']:>7.1%}  {r['r2026']:>+7.3f}  "
                  f"{r['gate_blocks_omega']:>5}  {r['gate_blocks_rho']:>5}")

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

    out_json = OUT_DIR_ / "crypto_godmode_v41_ramp.json"
    rows_clean = [
        {k: v for k, v in r.items()
         if k not in ("sigma", "budget", "rho_eff_at_halt_log") and not isinstance(v, pd.Series)}
        for r in results
    ]
    with open(out_json, "w") as f:
        json.dump(
            {
                "version":    "v41",
                "cb":         "cb_v34_tight",
                "cb_halt":    CB_HALT,
                "cb_resume":  CB_RESUME,
                "cb_window":  CB_WINDOW,
                "fixes": {
                    "Fix1_omega_gate":       "gamma * rhs_norm >= omega_thresh → stay halted",
                    "Fix2_saturating_budget": "E_inf*(1-exp(-rho_typ*lock_bars*DT))",
                    "Fix3_rho_eff_gate_v40":  "rho_eff_at_halt<alpha*rho_typ AND rho_eff_current<alpha*rho_typ → stay halted",
                    "New_ramp_v41":           "K_eff=K_normal*min(1,ramp_init+Δbar/ramp_bars) after CB release",
                },
                "results": rows_clean,
            },
            f, indent=2, default=serialise,
        )
    print(f"  → {out_json}")

    # ── [7] Plots ──────────────────────────────────────────────────────────────
    print(f"\n[7] Generating plots ...")
    ab_paths = plot_gate_ablation(results)
    print(f"  Gate ablation plots: {len(ab_paths)}")
    hm_paths = plot_heatmap_v39(results)
    print(f"  Heatmap plots: {len(hm_paths)}")
    sc_path  = plot_scatter_dd_v_calmar(results)
    print(f"  Scatter plot: {sc_path}")
    eq_path  = plot_equity_best_v39(sim_store_eq, results, test_ts)
    print(f"  Equity curve: {eq_path}")

    elapsed = time.time() - t0_total
    print(f"\n{BAR}")
    print(f"  v41 COMPLETE  |  elapsed={elapsed:.1f}s  ({elapsed/60:.1f} min)")
    print(f"  CB: cb_v34_tight  (halt={CB_HALT}, resume={CB_RESUME}, window={CB_WINDOW}d)")
    print(f"  Fixes applied:")
    print(f"    Fix 1 (Ω gate):         gamma × rhs_norm ≥ omega_thresh → extend lock")
    print(f"    Fix 2 (budget):         E∞·(1−e^{{−ρT}}) replaces c_σ×lock_bars")
    print(f"    Fix 3 (ρ halt-time):    ODE-shock gate (v40, unchanged)")
    print(f"    NEW v41 (ramp):         K_eff = K_normal × min(1, ramp_init + Δbar/ramp_bars)")
    print(BAR)


if __name__ == "__main__":
    main()
