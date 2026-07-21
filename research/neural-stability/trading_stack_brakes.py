# -*- coding: utf-8 -*-
"""
trading_stack_brakes.py
=======================
Port of the trading-champion brake stack (v55 / v58 / v38) to score/alarm
modulators on top of FrozenCanonicalV4.

Mode A — crisis-detection augmentation:
    Each brake reduces (or holds) a per-step multiplier `k_mod` in [0, 1].
    Final modulated score: score_mod = score * k_mod.
    Final alarms:  score_mod > engine.threshold_  AND  not CB-halted.

Brakes ported
-------------
1. G7 covariance regularisation       — `apply_g7_to_engine`
2. Admissibility brake                — `score_modulators(... admiss_c, psi_star)`
3. Soft omega sizing                  — `score_modulators(... omega_a)`
4. Curvature sizing                   — `score_modulators(... curv_b)`
5. DD-gated soft brake                — `dd_gated_brake`
6. G2.4 stochastic CB resume override — `g24_resume_budget`
7. RHS release filter                 — `rhs_release_filter` (used inline in CB loop)

All math is taken verbatim from the trading scripts so behaviour is identical
when the same inputs are wired in.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np

EPS = 1e-9

# ─── optional CGS-v1 topology / stochastic components ────────────────────────
# These live in cgs_v1_engine.py.  Imported lazily so the brake stack still
# works standalone (FrozenCanonicalV4-only) if cgs_v1_engine is unavailable.
try:
    from cgs_v1_engine import (
        three_phase_precursor as _cgs_three_phase,
        hessian_energy as _cgs_hessian_energy,
        curvature_bound as _cgs_curvature_bound,
        ito_correction as _cgs_ito_correction,
        free_energy as _cgs_free_energy,
    )
    _HAS_CGS = True
except Exception:  # pragma: no cover - fallback path
    _HAS_CGS = False

    def _cgs_three_phase(Edot, Rdot, theta_ddot):
        Ed = np.asarray(Edot, dtype=float)
        Rd = np.asarray(Rdot, dtype=float)
        td = np.asarray(theta_ddot, dtype=float)
        mask = (Ed > 0.0) & (Rd > 0.0) & (td > 0.0)
        return bool(mask) if mask.ndim == 0 else mask


# ─── helpers cloned from v55 / v38 ───────────────────────────────────────────

def regularise_sigma_g7(Sigma: np.ndarray, kappa_max: float) -> tuple[np.ndarray, float]:
    """G7.1: return Sigma + lam_reg*I such that kappa(Sigma) <= kappa_max."""
    eigvals = np.linalg.eigvalsh(Sigma)
    lam_max = float(eigvals[-1])
    lam_min = float(max(eigvals[0], 1e-12))
    if lam_max / lam_min <= kappa_max:
        return Sigma, 0.0
    lam_reg = max((lam_max - kappa_max * lam_min) / (kappa_max - 1.0), 0.0)
    return Sigma + lam_reg * np.eye(Sigma.shape[0]), float(lam_reg)


def apply_g7_to_engine(engine, kappa_max: Optional[float]) -> float:
    """Apply G7 regularisation to a fitted FrozenCanonicalV4 in-place.

    Re-derives G_ from the regularised Sigma. Returns lam_reg used (0 if no-op).
    """
    if kappa_max is None or not engine.fitted:
        return 0.0
    Sigma = np.linalg.pinv(engine.G_)  # invert back to Sigma
    Sigma_reg, lam_reg = regularise_sigma_g7(Sigma, float(kappa_max))
    engine.G_ = np.linalg.pinv(Sigma_reg)
    return lam_reg


def compute_psi_star_from_engine(engine, X_ref: np.ndarray) -> float:
    """Psi* ≈ sigma_res · theta · mu_G / sqrt(M_G).

    Uses the engine's frozen G_ and theta_ and the residual norms on X_ref
    after standardisation: S = (X_ref - mu_)/sigma_, residual is S itself
    (target is 0).
    """
    if not engine.fitted:
        return 0.0
    G = engine.G_
    eig_G = np.linalg.eigvalsh(G)
    mu_G = float(np.mean(eig_G))
    M_G = float(max(np.max(eig_G), 1e-12))
    Z = (X_ref - engine.mu_[None, :]) / engine.sigma_[None, :]
    s_norm = np.linalg.norm(Z, axis=1)
    sigma_res = float(np.std(s_norm)) + EPS
    return sigma_res * float(engine.theta_) * mu_G / np.sqrt(M_G)


def fisher_rank(G: np.ndarray, eps: float = 1e-10) -> int:
    """Effective rank of G (used by G2.4 c_sigma)."""
    vals = np.linalg.eigvalsh(G)
    return int(np.sum(vals > eps * vals[-1]))


def c_sigma_per_step(eta: float, rank_Ix: int, dt: float = 1.0) -> float:
    """G2.4 Itô budget per step: c_sigma = eta * dt * rank(G)."""
    return float(eta) * float(dt) * int(rank_Ix)


# ─── score modulators ────────────────────────────────────────────────────────

def score_modulators(
    score: np.ndarray,
    gamma: np.ndarray,
    rhs: np.ndarray,
    *,
    omega_a: float = 0.0,
    curv_b: float = 0.0,
    admiss_c: float = 0.0,
    psi_star: float = 0.0,
) -> np.ndarray:
    """Multiplicative dampers cloned from v55 simulate_robust.

        k *= 1 / (1 + omega_a * gamma * rhs+)
        k *= 1 / (1 + curv_b  * rhs+)
        k *= min(1, admiss_c * psi_star / (rhs + EPS))    (only if psi_star>0)

    Returns k_mod array, same length as score, in (0, 1].
    """
    n = len(score)
    k = np.ones(n, dtype=float)
    rhs_pos = np.maximum(rhs, 0.0)
    if omega_a > 0.0:
        k /= (1.0 + omega_a * np.maximum(gamma, 0.0) * rhs_pos)
    if curv_b > 0.0:
        k /= (1.0 + curv_b * rhs_pos)
    if admiss_c > 0.0 and psi_star > 0.0:
        brake = np.minimum(1.0, admiss_c * psi_star / (rhs_pos + EPS))
        k *= brake
    return np.clip(k, 0.0, 1.0)


# ─── DD-gated brake (v58 port, on score-drawdown) ────────────────────────────

def dd_gated_brake(
    score: np.ndarray,
    *,
    dd_thr: Optional[float] = None,
    dd_stop: float = 0.40,
    beta: float = 1.0,
    k_min: float = 0.20,
) -> tuple[np.ndarray, dict]:
    """DD-gated soft brake on anomaly score.

    "Drawdown" here is the *retracement from running max of score* — i.e.
    score has decayed dd fraction below its all-time peak. When the system
    is in such a retracement, the brake holds k=1 (we are NOT in crisis).
    When score *exceeds* its prior peak by more than dd_thr (i.e. crisis
    intensifying past prior worst), the brake activates and damps further
    score growth so we don't double-count.

    This is the anomaly-domain analogue of v58's equity-DD throttle: in
    trading, dd_thr triggers when equity falls; here it triggers when the
    anomaly indicator climbs past its prior local max by dd_thr.

    Returns (k_dd, info_dict). When dd_thr is None, returns ones.
    """
    n = len(score)
    if dd_thr is None:
        return np.ones(n, dtype=float), dict(n_brake=0, mean_kdd=1.0)

    gate_span = max(EPS, dd_stop - dd_thr)
    k_dd = np.ones(n, dtype=float)
    running_max = -np.inf
    n_brake = 0
    for t in range(n):
        s = float(score[t])
        running_max = max(running_max, s)
        if running_max <= 0.0:
            continue
        # how much score exceeds its prior running max as a fraction of that max
        excess = (s - running_max) / max(running_max, EPS)
        # crisis intensifying: excess >= dd_thr triggers
        if excess >= dd_thr:
            d = excess - dd_thr
            k_dd[t] = max(k_min, 1.0 - beta * d / gate_span)
            n_brake += 1
    return k_dd, dict(n_brake=int(n_brake), mean_kdd=float(np.mean(k_dd)))


# ─── G2.4 budget for CB resume + rhs release filter ──────────────────────────

@dataclass
class BrakeCBState:
    halted: bool = False
    halt_start: int = 0
    halt_peak: float = 0.0
    extend_counter: int = 0


def cb_step(
    t: int,
    score_t: float,
    rhs_t: float,
    state: BrakeCBState,
    rolling_peak: float,
    *,
    halt_frac: float,
    resume_frac: float,
    g24_eta: float = 0.0,
    g24_lock_min: int = 0,
    g24_rank_Ix: int = 0,
    release_thr: float = 0.0,
    release_ext: int = 0,
) -> tuple[bool, dict]:
    """Single-step CB transition matching v55/v58 logic, on anomaly score.

    Returns (is_halted_after_step, stats).
    Direction: surge ABOVE rolling peak triggers HALT (anomaly convention).
    """
    halt_now = state.halted
    n_g24 = 0
    n_blocked = 0

    if state.extend_counter > 0:
        state.extend_counter -= 1
        if state.extend_counter == 0:
            state.halted = False
        halt_now = state.halted or (state.extend_counter > 0)
        return halt_now, dict(g24=0, blocked=0)

    if not state.halted:
        surge = (score_t / max(rolling_peak, EPS)) - 1.0
        if surge >= halt_frac:
            state.halted = True
            state.halt_start = t
            state.halt_peak = score_t
        halt_now = state.halted
    else:
        recovery = (state.halt_peak - score_t) / max(state.halt_peak, EPS)
        # G2.4 stochastic override: extra budget c_sigma * lock_bars
        c_sig = c_sigma_per_step(g24_eta, g24_rank_Ix) if g24_eta > 0 else 0.0
        lock_bars = t - state.halt_start
        std_resume = recovery >= resume_frac
        g24_resume = (
            c_sig > 0.0
            and lock_bars >= g24_lock_min
            and recovery >= (resume_frac - c_sig * lock_bars)
        )
        if std_resume or g24_resume:
            # rhs release filter — block release while rhs spikes
            if release_thr > 0.0 and rhs_t > release_thr:
                state.extend_counter = release_ext
                n_blocked += 1
            else:
                state.halted = False
                state.halt_peak = 0.0
                if g24_resume and not std_resume:
                    n_g24 += 1
        halt_now = state.halted or (state.extend_counter > 0)

    return halt_now, dict(g24=n_g24, blocked=n_blocked)


# ─── full pipeline ───────────────────────────────────────────────────────────

def run_brake_pipeline(
    score: np.ndarray,
    gamma: np.ndarray,
    rhs: np.ndarray,
    threshold: float,
    *,
    # score modulators
    omega_a: float = 0.0,
    curv_b: float = 0.0,
    admiss_c: float = 0.0,
    psi_star: float = 0.0,
    # DD brake
    dd_thr: Optional[float] = None,
    dd_stop: float = 0.40,
    beta: float = 1.0,
    k_min: float = 0.20,
    # CB
    cb_halt: float = 0.08,
    cb_resume: float = 0.04,
    cb_window: int = 90,
    # G2.4
    g24_eta: float = 0.0,
    g24_lock_min: int = 0,
    g24_rank_Ix: int = 0,
    # rhs release filter
    release_thr: float = 0.0,
    release_ext: int = 0,
) -> dict:
    """Apply all brakes to a (score, gamma, rhs) triple.

    Returns dict with:
      score_mod, k_mod, k_dd, alarms, cb_flags, n_g24, n_blocked, n_brake
    """
    n = len(score)
    score = np.asarray(score, dtype=float)
    gamma = np.asarray(gamma, dtype=float)
    rhs = np.asarray(rhs, dtype=float)

    k_mod = score_modulators(
        score, gamma, rhs,
        omega_a=omega_a, curv_b=curv_b,
        admiss_c=admiss_c, psi_star=psi_star,
    )
    k_dd, dd_info = dd_gated_brake(
        score, dd_thr=dd_thr, dd_stop=dd_stop, beta=beta, k_min=k_min,
    )
    score_mod = score * k_mod * k_dd

    # CB on the modulated score with monotone-deque rolling max
    state = BrakeCBState()
    mono: deque = deque()
    cb_flags = np.zeros(n, dtype=bool)
    alarms = np.zeros(n, dtype=bool)
    n_g24_total = 0
    n_blocked_total = 0
    for t in range(n):
        s = float(score_mod[t])
        while mono and mono[0][0] <= t - cb_window:
            mono.popleft()
        while mono and mono[-1][1] <= s:
            mono.pop()
        mono.append((t, s))
        roll_peak = mono[0][1]
        is_halted, stats = cb_step(
            t, s, float(rhs[t]), state, roll_peak,
            halt_frac=cb_halt, resume_frac=cb_resume,
            g24_eta=g24_eta, g24_lock_min=g24_lock_min, g24_rank_Ix=g24_rank_Ix,
            release_thr=release_thr, release_ext=release_ext,
        )
        cb_flags[t] = is_halted
        n_g24_total += stats["g24"]
        n_blocked_total += stats["blocked"]
        if (not is_halted) and (s > threshold):
            alarms[t] = True

    return dict(
        score_mod=score_mod,
        k_mod=k_mod,
        k_dd=k_dd,
        alarms=alarms,
        cb_flags=cb_flags,
        n_g24=int(n_g24_total),
        n_blocked=int(n_blocked_total),
        n_brake=int(dd_info["n_brake"]),
        mean_kmod=float(np.mean(k_mod)),
        mean_kdd=float(dd_info["mean_kdd"]),
        pct_halted=float(cb_flags.mean()),
    )


# ─── crisis-detection metrics ────────────────────────────────────────────────

def auroc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Mann-Whitney U based AUROC. Handles ties as 0.5."""
    s = np.asarray(scores, dtype=float)
    y = np.asarray(labels, dtype=bool)
    n_pos = int(y.sum())
    n_neg = int((~y).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s), dtype=float)
    ranks[order] = np.arange(1, len(s) + 1, dtype=float)
    # average ranks for ties
    _, inv, counts = np.unique(s, return_inverse=True, return_counts=True)
    sum_by_val = np.zeros_like(counts, dtype=float)
    np.add.at(sum_by_val, inv, ranks)
    avg_rank = sum_by_val / counts
    ranks = avg_rank[inv]
    sum_pos = ranks[y].sum()
    return float((sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def first_alarm_lead(alarms: np.ndarray, crisis_index: int) -> int:
    """Steps the first alarm precedes crisis_index. Negative = late, large = early."""
    fa = int(np.argmax(alarms)) if np.any(alarms) else len(alarms)
    return int(crisis_index - fa)


def far(alarms: np.ndarray, crisis_mask: np.ndarray) -> float:
    """False alarm rate over non-crisis steps."""
    a = np.asarray(alarms, dtype=bool)
    c = np.asarray(crisis_mask, dtype=bool)
    n_neg = int((~c).sum())
    if n_neg == 0:
        return float("nan")
    return float((a & ~c).sum()) / n_neg


def hit_rate(alarms: np.ndarray, crisis_mask: np.ndarray) -> float:
    a = np.asarray(alarms, dtype=bool)
    c = np.asarray(crisis_mask, dtype=bool)
    n_pos = int(c.sum())
    if n_pos == 0:
        return float("nan")
    return float((a & c).sum()) / n_pos


def crisis_metrics(
    score_mod: np.ndarray,
    alarms: np.ndarray,
    crisis_mask: np.ndarray,
) -> dict:
    """All crisis-detection metrics in one call."""
    crisis_mask = np.asarray(crisis_mask, dtype=bool)
    first_crisis = int(np.argmax(crisis_mask)) if crisis_mask.any() else len(crisis_mask)
    return dict(
        auroc=auroc(score_mod, crisis_mask),
        hit_rate=hit_rate(alarms, crisis_mask),
        far=far(alarms, crisis_mask),
        n_alarms=int(np.asarray(alarms, dtype=bool).sum()),
        lead_time=first_alarm_lead(alarms, first_crisis),
        first_crisis=first_crisis,
    )


# ─── Morse / Betti / curvature topology layer (CGS-v1 port) ──────────────────

def morse_curvature_signals(
    E_series: np.ndarray,
    g_norm_series: np.ndarray,
    cos_theta_series: np.ndarray,
    G: np.ndarray,
    *,
    alpha_base: float = 0.05,
) -> dict:
    """Per-step Morse index, three-phase precursor, curvature bound and Betti-β₁
    change events — the topology components present in cgs_v1_engine but absent
    from the trading brake stack.

    Morse index note
    ----------------
    For the locked affine state map S = (X-μ)/σ with SPD metric G, the *algebraic*
    Morse index of E = SᵀGS is identically 0 everywhere (E is globally convex on
    the chart), so it carries no temporal information.  We therefore use the
    *empirical kinematic* Morse proxy: a step is saddle-like (index ≥ 1) when the
    energy acceleration Ë(t) > 0, i.e. the well is opening up underneath the
    trajectory.  Transitions 0→1 of this proxy are Betti-β₁ creation events
    (a new unstable direction appears — a topological precursor of collapse).

    Returns
    -------
    dict with keys:
      morse_idx           : int8 array, 1 where Ë>0 (saddle-like), else 0
      three_phase_mask    : bool array, three_phase_precursor(Ė,Ṙ,θ̈)
      curvature_upper_bound : float, 2·‖J‖²·λmax(G) with J=alpha_base·I, K_S=0
      betti_transitions   : bool array, 0→1 transitions of morse_idx
      betti_cumulative    : int array, running count of β₁ creation events
    """
    E = np.asarray(E_series, dtype=float)
    g = np.asarray(g_norm_series, dtype=float)
    c = np.asarray(cos_theta_series, dtype=float)
    T = len(E)

    # first / second differences (prepend zeros so outputs align to length T)
    Edot = np.concatenate([[0.0], np.diff(E)]) if T > 1 else np.zeros(T)
    Eddot = np.concatenate([[0.0], np.diff(Edot)]) if T > 1 else np.zeros(T)
    Rdot = np.concatenate([[0.0], np.diff(g)]) if T > 1 else np.zeros(T)
    theta_dot = np.concatenate([[0.0], np.diff(c)]) if T > 1 else np.zeros(T)
    theta_ddot = np.concatenate([[0.0], np.diff(theta_dot)]) if T > 1 else np.zeros(T)

    morse_idx = (Eddot > 0.0).astype(np.int8)

    tp = _cgs_three_phase(Edot, Rdot, theta_ddot)
    three_phase_mask = np.atleast_1d(np.asarray(tp, dtype=bool))
    if three_phase_mask.shape[0] != T:
        three_phase_mask = np.zeros(T, dtype=bool)

    # curvature bound (Prop 7.6): J = alpha_base·I ⇒ ‖J‖_op = alpha_base, K_S = 0
    Gm = np.atleast_2d(np.asarray(G, dtype=float))
    if _HAS_CGS:
        J = alpha_base * np.eye(Gm.shape[0])
        curv_bound = float(_cgs_curvature_bound(J, Gm, 0.0))
    else:
        lam_max_G = float(np.linalg.eigvalsh(Gm).max())
        curv_bound = 2.0 * (alpha_base ** 2) * lam_max_G

    if T > 1:
        trans = (np.diff(morse_idx.astype(int)) > 0)
        betti_transitions = np.concatenate([[False], trans])
    else:
        betti_transitions = np.zeros(T, dtype=bool)
    betti_cumulative = np.cumsum(betti_transitions.astype(int))

    return dict(
        morse_idx=morse_idx,
        three_phase_mask=three_phase_mask,
        curvature_upper_bound=curv_bound,
        betti_transitions=betti_transitions,
        betti_cumulative=betti_cumulative,
    )


def morse_confirmation_filter(
    alarms: np.ndarray,
    morse_idx: np.ndarray,
    three_phase_mask: np.ndarray,
    *,
    require_either: bool = True,
) -> np.ndarray:
    """Keep only alarms that are topologically confirmed.

    require_either=True  (permissive): keep alarm if Morse index ≥ 1 OR the
                         three-phase precursor is active at that step.
    require_either=False (strict)    : keep alarm only if Morse index ≥ 1 AND
                         three-phase precursor is active.

    Confirmation can only ever *remove* alarms, so hit-rate is non-increasing
    while false-alarm rate is the intended target for reduction.
    """
    a = np.asarray(alarms, dtype=bool)
    m = np.asarray(morse_idx, dtype=int) >= 1
    tp = np.asarray(three_phase_mask, dtype=bool)
    confirm = (m | tp) if require_either else (m & tp)
    return a & confirm


def stochastic_ito_score(
    E_series: np.ndarray,
    G: np.ndarray,
    *,
    sigma_n: float = 1e-2,
    alpha_base: float = 0.05,
    dt: float = 1.0,
) -> dict:
    """§XIX stochastic extension — Itô-corrected energy score (CGS-v1 port).

    Under dX = (controlled drift) dt + σ_n dW, the energy picks up an Itô drift
    term ½ σ_n² tr(Σᵀ ∇²E Σ)  (Theorem G2.1).  With the locked affine chart the
    state-space Hessian is ∇²E = 2 Jᵀ G J (J = alpha_base·I, K_S = 0), constant
    in time, so the per-step correction is a constant positive drift added to E.

    Returns
    -------
    dict with keys:
      score_stoch  : E(t) + Itô correction   (the stochastic anomaly score)
      ito_corr     : scalar Itô correction term
      free_energy  : F = E[E] − ½ rank(G) · t  (Corollary G2.3, t = T·dt)
      threshold    : μ + 2σ of score_stoch
      alarms       : score_stoch > threshold
    """
    E = np.asarray(E_series, dtype=float)
    Gm = np.atleast_2d(np.asarray(G, dtype=float))
    k = Gm.shape[0]
    J = alpha_base * np.eye(k)
    K_S = np.zeros((k, k))
    if _HAS_CGS:
        H = _cgs_hessian_energy(J, Gm, K_S)
        ito_corr = float(_cgs_ito_correction(sigma_n * np.eye(k), H))
    else:
        H = 2.0 * J.T @ (Gm + K_S) @ J
        Sigma = sigma_n * np.eye(k)
        ito_corr = 0.5 * float(np.trace(Sigma.T @ H @ Sigma))

    score_stoch = E + ito_corr
    rank_G = int(np.linalg.matrix_rank(Gm))
    t_total = float(len(E) * dt)
    if _HAS_CGS:
        F = float(_cgs_free_energy(float(np.mean(E)), rank_G, t_total))
    else:
        F = float(np.mean(E)) - 0.5 * rank_G * t_total

    mu_s = float(np.mean(score_stoch))
    sig_s = float(np.std(score_stoch)) + EPS
    threshold = mu_s + 2.0 * sig_s
    return dict(
        score_stoch=score_stoch,
        ito_corr=ito_corr,
        free_energy=F,
        threshold=threshold,
        alarms=score_stoch > threshold,
    )


def crisis_metrics_extended(
    score_mod: np.ndarray,
    alarms: np.ndarray,
    alarms_morse: np.ndarray,
    crisis_mask: np.ndarray,
    betti_cumulative: np.ndarray,
    three_phase_mask: np.ndarray,
) -> dict:
    """Base crisis metrics + topology-confirmed metrics in one call."""
    crisis_mask = np.asarray(crisis_mask, dtype=bool)
    base = crisis_metrics(score_mod, alarms, crisis_mask)
    am = np.asarray(alarms_morse, dtype=bool)
    betti_cumulative = np.asarray(betti_cumulative, dtype=int)
    tp = np.asarray(three_phase_mask, dtype=bool)
    base.update(
        hit_rate_morse=hit_rate(am, crisis_mask),
        far_morse=far(am, crisis_mask),
        n_morse_alarms=int(am.sum()),
        betti_peak=int(betti_cumulative[-1]) if betti_cumulative.size else 0,
        three_phase_ratio=float(tp.mean()) if tp.size else 0.0,
    )
    return base


def run_brake_pipeline_with_morse(
    score: np.ndarray,
    gamma: np.ndarray,
    rhs: np.ndarray,
    threshold: float,
    E_series: np.ndarray,
    g_norm_series: np.ndarray,
    cos_theta_series: np.ndarray,
    G: np.ndarray,
    *,
    alpha_base: float = 0.05,
    morse_require_either: bool = True,
    **brake_kwargs,
) -> dict:
    """run_brake_pipeline + Morse/Betti/three-phase topology confirmation layer.

    All keyword brake parameters (omega_a, admiss_c, dd_thr, cb_halt, …) are
    forwarded verbatim to run_brake_pipeline.  After the standard alarms are
    produced, they are filtered through morse_confirmation_filter using the
    energy-kinematic topology signals.

    Returns the run_brake_pipeline dict augmented with:
      morse_idx, three_phase_mask, curvature_upper_bound,
      betti_transitions, betti_cumulative,
      alarms_morse (permissive), alarms_morse_strict (strict),
      n_morse_confirmed
    """
    out = run_brake_pipeline(score, gamma, rhs, threshold, **brake_kwargs)
    topo = morse_curvature_signals(
        E_series, g_norm_series, cos_theta_series, G, alpha_base=alpha_base,
    )
    alarms_morse = morse_confirmation_filter(
        out["alarms"], topo["morse_idx"], topo["three_phase_mask"],
        require_either=True,
    )
    alarms_morse_strict = morse_confirmation_filter(
        out["alarms"], topo["morse_idx"], topo["three_phase_mask"],
        require_either=False,
    )
    primary = alarms_morse if morse_require_either else alarms_morse_strict
    out.update(
        morse_idx=topo["morse_idx"],
        three_phase_mask=topo["three_phase_mask"],
        curvature_upper_bound=topo["curvature_upper_bound"],
        betti_transitions=topo["betti_transitions"],
        betti_cumulative=topo["betti_cumulative"],
        alarms_morse=alarms_morse,
        alarms_morse_strict=alarms_morse_strict,
        alarms_confirmed=primary,
        n_morse_confirmed=int(np.asarray(primary, dtype=bool).sum()),
    )
    return out
