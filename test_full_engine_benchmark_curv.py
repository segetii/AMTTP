# -*- coding: utf-8 -*-
"""
test_full_engine_benchmark_curv.py
====================================
Curvature-augmented extension of test_full_engine_benchmark.py.

Adds a fifth engine tier, ``cgs1_curv``, which replaces the standard
Lyapunov energy E with the curvature-augmented energy

    E_unified(t) = E(t) · h(t),    h(t) = 1 + β* · κ_norm(t)

derived in §67 of the CanonicalBSDT derivations document.  For the
quadratic energy  E = S^T G S  the exact formulas simplify to:

    κ = 2 · λ_max(G)                   [§67.5: Hessian constant = 2G]
    κ_norm(t) = κ · E(t) / ‖g_X(t)‖²  [§66: normalised curvature]
    g̃_X(t)   = h(t) · g_X(t)          [§67.3: ∇κ_norm = 0 for quadratic E]
    γ_unified = E_unified / (E_unified + θ)
    β*        = clip(std(κ_norm_ref)/mean(κ_norm_ref), 0, 1)   [§67.7 SNR]

Proposition 67.7 guarantees γ_unified ≥ γ_E pointwise, so the collapse
threshold is crossed no later under cgs1_curv than under cgs1.

Structural claims tested (C1–C6 identical to base benchmark; C7 is new):
  C7  κ_norm drift — normalised curvature rises pre-onset as an independent
                     7th signal (§55.2 scalar collapse signature).

cgs1_curv also inherits C5 (Betti/Morse) and C6 (Kramers) from cgs1_stoch
so the full observable stack can be compared for all three rich tiers.

All other test logic (event-shuffle null, Bonferroni×4 for C2/C4, domain
functions, onset definitions) is identical to test_full_engine_benchmark.py.

Tiers: v4 / cgs1 / cgs1_morse / cgs1_stoch / cgs1_curv
Output: benchmark_curv_results.json (repo root) + printed report.

Author: Copilot — June 2026
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings

import numpy as np

warnings.filterwarnings("ignore")
np.random.seed(20260601)

ROOT = r"C:\amttp"
NS   = os.path.join(ROOT, "research", "neural-stability")
BANK = os.path.join(ROOT, "research", "adaptive-friction", "banklevel_enhanced")
sys.path.insert(0, NS)
sys.path.insert(0, BANK)

from canonical_v4_engine import FrozenCanonicalV4      # noqa: E402
from cgs_v1_engine import evaluate_cgs_v1_batch        # noqa: E402
import trading_stack_brakes as TSB                     # noqa: E402

EPS          = 1e-12
N_SHUFFLE    = 2000
TIERS_CURV   = ["v4", "cgs1", "cgs1_morse", "cgs1_stoch", "cgs1_curv"]
G7_KAPPA_MAX = 10.0   # G7 regularisation cap on cond(Sigma_0); None disables

# Theory-predicted sign of the pre-onset drift for each geometry diagnostic
PREDICTED_SIGN = {
    "cos_theta": +1.0,
    "gamma":     +1.0,
    "rho_eff":   -1.0,
    "Edot":      +1.0,
    "kappa_norm": +1.0,   # C7: curvature scalar rises approaching collapse
}


# ════════════════════════════════════════════════════════════════════════════
#  CGS-v1 function builders from a fitted FrozenCanonicalV4
# ════════════════════════════════════════════════════════════════════════════

def _alpha_of(engine: FrozenCanonicalV4) -> float:
    return float(getattr(engine, "alpha_base_", getattr(engine, "alpha_base", 0.05)))


def build_cgs_fns(engine: FrozenCanonicalV4):
    """Derive (S_fn, J_fn, G, Fbase_fn, theta) from a fitted V4 engine.

    Euclidean chart (J = I) avoids the dEdot blow-ups that the true diagonal
    Jacobian J = diag(1/sigma) caused on stiff domains (banks/protein).
    """
    mu, sigma, G = engine.mu_, engine.sigma_, engine.G_
    alpha, theta = _alpha_of(engine), float(engine.theta_)
    n_dim = len(sigma)
    J_const = np.eye(n_dim)

    def S_fn(X):
        return (np.asarray(X, dtype=float) - mu) / sigma

    def J_fn(X):
        return J_const

    def Fbase_fn(X):
        return -alpha * S_fn(X)

    return S_fn, J_fn, G, Fbase_fn, theta


def compute_cos_theta_series(X_series: np.ndarray,
                              engine: FrozenCanonicalV4) -> np.ndarray:
    """Per-step alignment cos(theta) = <gX, Fbase> / (||gX|| ||Fbase||)."""
    mu, sigma, G = engine.mu_, engine.sigma_, engine.G_
    alpha = _alpha_of(engine)
    Z = (np.asarray(X_series, dtype=float) - mu[None, :]) / sigma[None, :]
    gX   = 2.0 * (Z @ G)
    Fbase = -alpha * Z
    dot = np.einsum("ij,ij->i", gX, Fbase)
    gn  = np.linalg.norm(gX,   axis=1) + EPS
    fn  = np.linalg.norm(Fbase, axis=1) + EPS
    return np.clip(dot / (gn * fn), -1.0, 1.0)


# ════════════════════════════════════════════════════════════════════════════
#  Curvature calibration  (document §67.5 and §67.7)
# ════════════════════════════════════════════════════════════════════════════

def compute_curv_params(engine: FrozenCanonicalV4,
                        X_ref: np.ndarray) -> tuple[float, float]:
    """Calibrate κ and β* from reference data using document-exact formulas.

    For quadratic  E = S^T G S:
        ∇²E = 2G  (constant Hessian, §67.5)
        κ   = 2 · λ_max(G)                          — computed once
        κ_norm(t) = κ · E(t) / ‖g_X(t)‖²
        β*  = clip(std(κ_norm_ref) / mean(κ_norm_ref), 0, 1)  [§67.7 SNR]
    """
    G = engine.G_
    # Exact Hessian eigenvalue — single eigensolver call at calibration time
    kappa = 2.0 * float(np.linalg.eigvalsh(G)[-1])

    X_ref = np.asarray(X_ref, dtype=float)
    Z_ref  = (X_ref - engine.mu_[None, :]) / engine.sigma_[None, :]
    GS_ref = Z_ref @ G
    E_ref  = np.einsum("ij,ij->i", Z_ref, GS_ref)            # (T_ref,)
    g_norm_sq_ref = 4.0 * np.einsum("ij,ij->i", GS_ref, GS_ref)

    kappa_norm_ref = kappa * E_ref / (g_norm_sq_ref + EPS)

    mu_kn  = float(np.mean(kappa_norm_ref))
    std_kn = float(np.std(kappa_norm_ref))
    snr    = std_kn / (mu_kn + EPS)
    beta_curv = float(np.clip(snr, 0.0, 1.0))

    print(f"  [curv-cal] kappa={kappa:.4f}  beta_curv={beta_curv:.4f}"
          f"  kn_mean={mu_kn:.4f}  kn_std={std_kn:.4f}  SNR={snr:.4f}")
    return kappa, beta_curv


# ════════════════════════════════════════════════════════════════════════════
#  State-series extraction
# ════════════════════════════════════════════════════════════════════════════

def engine_series(tier: str, engine: FrozenCanonicalV4, X: np.ndarray,
                  kappa: float = 0.0, beta_curv: float = 0.0) -> dict:
    """Return dynamical state series the instruments operate on.

    All tiers expose: E, Edot, g_norm, cos_theta, gamma, rho_eff.
    cgs1_curv additionally exposes: kappa_norm.
    """
    if tier == "v4":
        r = engine.evaluate(X)
        E, Edot, g_norm = r.E, r.Edot, r.g_norm
        cos_theta, gamma = r.cos_theta, r.gamma
        rho_eff = -Edot / (np.abs(E) + EPS)
        return dict(E=E, Edot=Edot, g_norm=g_norm,
                    cos_theta=cos_theta, gamma=gamma, rho_eff=rho_eff)

    elif tier == "cgs1_curv":
        mu, sigma, G = engine.mu_, engine.sigma_, engine.G_
        theta = float(engine.theta_)
        alpha = _alpha_of(engine)

        Z   = (np.asarray(X, dtype=float) - mu[None, :]) / sigma[None, :]
        GS  = Z @ G                                          # (T, d)
        gX  = 2.0 * GS                                      # (T, d)
        E   = np.einsum("ij,ij->i", Z, GS)                  # (T,)
        g_norm_sq = np.einsum("ij,ij->i", gX, gX)           # (T,)

        # ── Normalised curvature  κ_norm(t) = κ · E(t) / ‖g_X(t)‖²  (§66) ──
        kappa_norm = kappa * E / (g_norm_sq + EPS)           # (T,)

        # ── Curvature amplification  h(t) = 1 + β* · κ_norm(t)  (§67.2) ──
        h = 1.0 + beta_curv * kappa_norm                     # (T,)

        # ── Curvature-augmented energy  E_unified = E · h  (Prop 67.2) ──
        E_unified = E * h                                    # (T,)

        # ── Amplified gradient  g̃_X = h · g_X  (∇κ_norm = 0 for quad. E, §67.5) ──
        g_tilde = h[:, None] * gX                           # (T, d)

        # ── Unified gain  γ_unified = E_unified / (E_unified + θ)  (§67.3) ──
        gamma_u = E_unified / (E_unified + theta)           # (T,)

        # ── Unified ODE step (§67.3 Eq(5)) ──
        Fbase   = -alpha * Z                                 # (T, d)
        F_total = Fbase - gX                                 # (T, d)  base force
        dot_Fg      = np.einsum("ij,ij->i", F_total, g_tilde)   # (T,)
        g_tilde_sq  = np.einsum("ij,ij->i", g_tilde, g_tilde)   # (T,)
        alpha_u = dot_Fg / (g_tilde_sq + EPS)               # (T,)
        Xdot_u  = F_total - (gamma_u * alpha_u)[:, None] * g_tilde  # (T, d)

        # ── Energy time-derivative via chain rule (Thm 67.4) ──
        Edot_u   = np.einsum("ij,ij->i", g_tilde, Xdot_u)  # (T,)
        rho_eff_u = -Edot_u / (np.abs(E_unified) + EPS)

        cos_theta = compute_cos_theta_series(X, engine)
        g_norm    = np.sqrt(g_tilde_sq)

        return dict(E=E_unified, Edot=Edot_u, g_norm=g_norm,
                    cos_theta=cos_theta, gamma=gamma_u, rho_eff=rho_eff_u,
                    kappa_norm=kappa_norm)

    else:  # cgs1 / cgs1_morse / cgs1_stoch
        S_fn, J_fn, G, Fbase_fn, theta = build_cgs_fns(engine)
        b = evaluate_cgs_v1_batch(X, S_fn, J_fn, G, Fbase_fn, theta)
        E, Edot, g_norm, gamma = b["E"], b["Edot"], b["g_norm"], b["gamma"]
        cos_theta = compute_cos_theta_series(X, engine)
        rho_eff   = -Edot / (np.abs(E) + EPS)
        return dict(E=E, Edot=Edot, g_norm=g_norm,
                    cos_theta=cos_theta, gamma=gamma, rho_eff=rho_eff)


# ════════════════════════════════════════════════════════════════════════════
#  Dynamical instruments  (identical to base benchmark)
# ════════════════════════════════════════════════════════════════════════════

def onset_events(crisis_mask: np.ndarray) -> np.ndarray:
    """Indices where the trajectory ENTERS a crisis/disordered segment."""
    c = np.asarray(crisis_mask, dtype=int)
    if c.size == 0:
        return np.array([], dtype=int)
    rising = np.where(np.diff(c) > 0)[0] + 1
    if c[0] == 1:
        rising = np.concatenate([[0], rising])
    return rising


def _pre_onset_mask(onsets: np.ndarray, W: int, T: int) -> np.ndarray:
    m = np.zeros(T, dtype=bool)
    for o in onsets:
        lo = max(0, o - W)
        if lo < o:
            m[lo:o] = True
    return m


def lyapunov_descent(Edot: np.ndarray, crisis_mask: np.ndarray) -> dict:
    """C1: does E dissipate during quiescence?"""
    q = ~np.asarray(crisis_mask, dtype=bool)
    if q.sum() == 0:
        return dict(desc_frac=float("nan"), Edot_quiescent=float("nan"))
    eq = Edot[q]
    return dict(desc_frac=float((eq < 0).mean()),
                Edot_quiescent=float(np.mean(eq)))


def _drift_stat(signal: np.ndarray, onsets: np.ndarray, W: int) -> float:
    """Pre-onset mean minus global mean (the event-locked drift)."""
    T = len(signal)
    pre = _pre_onset_mask(onsets, W, T)
    if pre.sum() == 0:
        return float("nan")
    return float(np.mean(signal[pre]) - np.mean(signal))


def _rate_ratio(boolean: np.ndarray, onsets: np.ndarray, W: int) -> float:
    """Pre-onset event rate / global event rate (>1 = concentrates pre-onset)."""
    T = len(boolean)
    pre = _pre_onset_mask(onsets, W, T)
    base = float(np.mean(boolean)) + EPS
    if pre.sum() == 0:
        return float("nan")
    return float(np.mean(boolean[pre]) / base)


def precursor_lead(boolean: np.ndarray, onsets: np.ndarray, W: int) -> float:
    """Mean lead (steps) of the FIRST precursor firing inside each pre-onset
    window, averaged over onsets that have at least one firing."""
    T = len(boolean)
    leads = []
    for o in onsets:
        lo = max(0, o - W)
        if lo >= o:
            continue
        seg = np.where(boolean[lo:o])[0]
        if seg.size:
            first = lo + int(seg[0])
            leads.append(o - first)
    return float(np.mean(leads)) if leads else float("nan")


def per_onset_drift(signal: np.ndarray, onsets: np.ndarray, W: int) -> dict:
    """Per-onset version of the drift statistic."""
    g = float(np.mean(signal))
    vals = []
    T = len(signal)
    for o in onsets:
        lo = max(0, o - W)
        if lo >= o:
            continue
        vals.append(float(np.mean(signal[lo:o]) - g))
    if not vals:
        return dict(n_events=0, frac_pos=float("nan"),
                    mean=float("nan"), std=float("nan"), values=[])
    arr = np.asarray(vals)
    return dict(n_events=len(vals), frac_pos=float((arr > 0).mean()),
                mean=float(arr.mean()), std=float(arr.std()), values=vals)


def event_shuffle_p(signal: np.ndarray, onsets: np.ndarray, W: int,
                    stat_fn, observed: float, n: int = N_SHUFFLE,
                    two_sided: bool = True) -> float:
    """Empirical p-value via event-shuffle null (n=2000)."""
    T = len(signal)
    k = len(onsets)
    if k == 0 or not np.isfinite(observed):
        return float("nan")
    null = np.empty(n)
    lo, hi = W, T
    for i in range(n):
        fake = np.random.randint(lo, hi, size=k) if hi > lo else onsets
        null[i] = stat_fn(signal, fake, W)
    null = null[np.isfinite(null)]
    if null.size == 0:
        return float("nan")
    if two_sided:
        centre = np.median(null)
        return float((np.abs(null - centre) >= abs(observed - centre)).mean())
    return float((null >= observed).mean())


def kramers_hazard(E: np.ndarray, Edot: np.ndarray, e_star: float,
                   sigma_n: float, tau: float) -> np.ndarray:
    """C6: per-step Kramers barrier-crossing probability over horizon tau."""
    T = len(E)
    h = np.zeros(T)
    order = np.argsort(E)
    Es, Eds = E[order], Edot[order]
    if np.ptp(Es) < EPS:
        return h
    slope_sorted = np.gradient(Eds, Es + np.linspace(0, EPS, T))
    dmu = np.empty(T)
    dmu[order] = slope_sorted
    mu_star_slope = float(np.interp(e_star, Es, slope_sorted))
    s2 = max(sigma_n ** 2, 1e-12)
    for t in range(T):
        e_t = E[t]
        if e_star <= e_t:
            h[t] = 1.0
            continue
        denom      = np.sqrt(abs(dmu[t]) * abs(mu_star_slope)) + 1e-12
        log_barrier = min(2.0 * (e_star - e_t) / s2, 700.0)
        tau_K      = (2.0 * np.pi / denom) * np.exp(log_barrier)
        h[t]       = 1.0 - np.exp(-tau / max(tau_K, 1e-12))
    return h


# ════════════════════════════════════════════════════════════════════════════
#  Per-engine evaluation
# ════════════════════════════════════════════════════════════════════════════

def run_one_engine(tier: str, engine: FrozenCanonicalV4, X: np.ndarray,
                   crisis_mask: np.ndarray, label: str, W: int,
                   kappa: float = 0.0, beta_curv: float = 0.0) -> dict:
    X            = np.asarray(X, dtype=float)
    crisis_mask  = np.asarray(crisis_mask, dtype=bool)
    T            = X.shape[0]
    s            = engine_series(tier, engine, X, kappa=kappa, beta_curv=beta_curv)
    onsets       = onset_events(crisis_mask)
    n_on         = len(onsets)

    row = {"domain": label, "engine": tier, "n_onsets": int(n_on),
           "T": int(T), "W": int(W)}
    if tier == "cgs1_curv":
        row["kappa_ref"]  = float(kappa)
        row["beta_curv"]  = float(beta_curv)

    # C1 — Lyapunov descent during quiescence
    row.update(lyapunov_descent(s["Edot"], crisis_mask))

    # C2 + C4 — energy + geometry drift across onset, with predicted signs
    geom_keys = ["Edot", "cos_theta", "gamma", "rho_eff"]
    n_tests   = len(geom_keys)   # Bonferroni family size
    for key in geom_keys:
        d      = _drift_stat(s[key], onsets, W)
        p      = event_shuffle_p(s[key], onsets, W, _drift_stat, d)
        p_bonf = min(1.0, p * n_tests) if np.isfinite(p) else float("nan")
        row[f"drift_{key}"]   = d
        row[f"p_{key}"]       = p
        row[f"pbonf_{key}"]   = p_bonf
        pod = per_onset_drift(s[key], onsets, W)
        row[f"poFrac_{key}"]  = pod["frac_pos"]
        pred = PREDICTED_SIGN[key]
        row[f"match_{key}"] = bool(np.isfinite(d) and np.sign(d) == pred
                                   and np.isfinite(p_bonf) and p_bonf < 0.05)

    # C3 — three-phase precursor concentration (all tiers share the geometry)
    topo = TSB.morse_curvature_signals(
        s["E"], s["g_norm"], s["cos_theta"], engine.G_, alpha_base=_alpha_of(engine))
    p3 = topo["three_phase_mask"].astype(float)
    r3 = _rate_ratio(p3, onsets, W)
    row["p3_conc_ratio"]  = r3
    row["p_p3"]           = event_shuffle_p(p3, onsets, W, _rate_ratio, r3)
    row["p3_global_rate"] = float(p3.mean())
    row["p3_lead"]        = precursor_lead(topo["three_phase_mask"], onsets, W)

    # C3b — DISJUNCTION precursor: [Edot rising] OR [cos_theta rising]
    Edot_rise = np.concatenate([[False], np.diff(s["Edot"])     > 0]) if T > 1 else np.zeros(T, bool)
    cos_rise  = np.concatenate([[False], np.diff(s["cos_theta"]) > 0]) if T > 1 else np.zeros(T, bool)
    p_disj    = (Edot_rise | cos_rise).astype(float)
    rd = _rate_ratio(p_disj, onsets, W)
    row["disj_conc_ratio"]  = rd
    row["p_disj"]           = event_shuffle_p(p_disj, onsets, W, _rate_ratio, rd)
    row["disj_global_rate"] = float(p_disj.mean())
    row["disj_lead"]        = precursor_lead((Edot_rise | cos_rise), onsets, W)

    # C5 — Betti / Morse-index flip time-locking
    #       cgs1_morse, cgs1_stoch, AND cgs1_curv
    if tier in ("cgs1_morse", "cgs1_stoch", "cgs1_curv"):
        bt = topo["betti_transitions"].astype(float)
        rb = _rate_ratio(bt, onsets, W)
        row["betti_conc_ratio"]  = rb
        row["p_betti"]           = event_shuffle_p(bt, onsets, W, _rate_ratio, rb)
        row["betti_global_rate"] = float(bt.mean())
        row["betti_peak"]        = int(topo["betti_cumulative"][-1]) if T else 0

    # C6 — Kramers barrier-crossing hazard
    #       cgs1_stoch AND cgs1_curv
    if tier in ("cgs1_stoch", "cgs1_curv"):
        E_arr  = s["E"]
        q      = ~crisis_mask
        e_star = float(np.mean(E_arr[q]) + 2.0 * np.std(E_arr[q])) \
                 if q.sum() else float(np.mean(E_arr))
        sigma_n = float(np.std(np.diff(E_arr))) + EPS
        tau_h   = float(max(1.0, W))
        h_t     = kramers_hazard(E_arr, s["Edot"], e_star, sigma_n, tau_h)
        dh = _drift_stat(h_t, onsets, W)
        row["kramers_drift"]       = dh
        row["p_kramers"]           = event_shuffle_p(h_t, onsets, W, _drift_stat, dh)
        row["kramers_global_mean"] = float(np.mean(h_t))
        row["e_star"]              = e_star
        row["sigma_n_eff"]         = sigma_n

    # C7 — κ_norm drift (cgs1_curv only)
    if tier == "cgs1_curv" and "kappa_norm" in s:
        kn    = s["kappa_norm"]
        dkn   = _drift_stat(kn, onsets, W)
        pkn   = event_shuffle_p(kn, onsets, W, _drift_stat, dkn)
        row["kappa_norm_drift"] = dkn
        row["p_kappa_norm"]     = pkn
        pred_kn = PREDICTED_SIGN["kappa_norm"]
        row["match_kappa_norm"] = bool(np.isfinite(dkn) and np.sign(dkn) == pred_kn
                                       and np.isfinite(pkn) and pkn < 0.05)

    return _clean(row)


def _clean(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, (np.floating, np.integer)):
            v = v.item()
        elif isinstance(v, np.bool_):
            v = bool(v)
        out[k] = v
    return out


def run_all_tiers_curv(X_ref, X, crisis_mask, label, W) -> list[dict]:
    """Fit one engine per tier; calibrate curvature params for cgs1_curv."""
    rows = []
    for tier in TIERS_CURV:
        engine = FrozenCanonicalV4(alpha_base=0.05)
        engine.fit(X_ref)
        # G7: cap cond(Sigma_0) so near-singular references don't blow up gradients
        lam_g7 = TSB.apply_g7_to_engine(engine, G7_KAPPA_MAX)
        if tier == "cgs1_curv":
            kappa, beta_c = compute_curv_params(engine, X_ref)
        else:
            kappa, beta_c = 0.0, 0.0
        r = run_one_engine(tier, engine, X, crisis_mask, label, W,
                           kappa=kappa, beta_curv=beta_c)
        r["g7_lambda"] = float(lam_g7)
        rows.append(r)
    return rows


# ════════════════════════════════════════════════════════════════════════════
#  Domains
# ════════════════════════════════════════════════════════════════════════════

def domain_banks() -> list[dict]:
    import pandas as pd
    cache = os.path.join(BANK, "gsib_cache_real", "gsib_real_panel.npz")
    if not os.path.exists(cache):
        print(f"[banks] cache not found: {cache} — skipping")
        return []
    npz  = np.load(cache)
    X_3d = npz["X"]
    T    = X_3d.shape[0]
    dates = pd.date_range("2005-01-01", "2023-12-31", freq="QE")[:T]
    Xagg  = np.nan_to_num(np.nanmean(X_3d, axis=1), nan=0.0, posinf=0.0, neginf=0.0)
    windows = [("2008-09-30", "2009-03-31"), ("2011-09-30", "2012-03-31"),
               ("2020-03-31", "2020-06-30"), ("2023-03-31", "2023-06-30")]
    crisis = np.zeros(T, dtype=bool)
    for lo, hi in windows:
        crisis |= np.asarray((dates >= pd.Timestamp(lo)) & (dates <= pd.Timestamp(hi)))
    X_ref = Xagg[np.asarray(dates < pd.Timestamp("2008-01-01"))]
    print(f"[banks] T={T} d={Xagg.shape[1]} ref={len(X_ref)} onsets={len(onset_events(crisis))}")
    return run_all_tiers_curv(X_ref, Xagg, crisis, "banks", W=4)


def domain_protein() -> list[dict]:
    try:
        from domain_v2_protein import (
            PDB_IDS, fetch_pdb_bfactors, bfactors_to_state_matrix,
            CRISIS_B_ZSCORE, REF_B_FRACTION)
    except Exception as exc:
        print(f"[protein] import failed: {exc} — skipping")
        return []
    rows = []
    for pdb_id in PDB_IDS:
        print(f"[protein] {pdb_id} fetching ...")
        try:
            data = fetch_pdb_bfactors(pdb_id)
        except Exception as exc:
            print(f"[protein] {pdb_id} fetch error: {exc} — skipping")
            continue
        if not data:
            continue
        bf     = np.asarray(data["bfactors"], dtype=float)
        X      = bfactors_to_state_matrix(bf)
        crisis = bf > (bf.mean() + CRISIS_B_ZSCORE * bf.std())
        X_ref  = X[bf <= np.percentile(bf, REF_B_FRACTION * 100)]
        print(f"[protein] {pdb_id} n={len(bf)} ref={len(X_ref)} onsets={len(onset_events(crisis))}")
        rows += run_all_tiers_curv(X_ref, X, crisis, f"protein:{pdb_id}", W=5)
    return rows


def domain_eeg() -> list[dict]:
    try:
        from domain_real_eeg import load_arff, DATA
    except Exception as exc:
        print(f"[eeg] import failed: {exc} — skipping")
        return []
    if not os.path.exists(DATA):
        print(f"[eeg] data not found: {DATA} — skipping")
        return []
    X_eeg, y = load_arff(DATA)
    open_idx  = np.where(y == 0)[0]
    if len(open_idx) < 100:
        return []
    X_ref  = X_eeg[open_idx[:1500]]
    crisis = (y == 1)
    print(f"[eeg] n={len(y)} ref={len(X_ref)} onsets={len(onset_events(crisis))}")
    return run_all_tiers_curv(X_ref, X_eeg, crisis, "eeg", W=64)


# ════════════════════════════════════════════════════════════════════════════
#  Reporting
# ════════════════════════════════════════════════════════════════════════════

def _sig(val, p, fmt="{:+.3f}"):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "   -   "
    star = "*" if (isinstance(p, float) and np.isfinite(p) and p < 0.05) else " "
    return fmt.format(val) + star


def print_report(rows: list[dict]) -> None:
    W_TOT = 144
    print("\n" + "=" * W_TOT)
    print("DYNAMICAL VALIDATION  "
          "( * = event-shuffle p < 0.05 AFTER Bonferroni×4 ;  drift = pre-onset mean − global mean )")
    print("=" * W_TOT)
    hdr = (f"{'domain':<14}{'engine':<12}{'n_on':>4}{'descF':>7}"
           f"{'dEdot':>9}{'dCos':>9}{'dgam':>9}{'drho':>9}"
           f"{'C4ok':>5}{'P3conc':>8}{'Disj':>8}{'Dlead':>7}"
           f"{'Betti':>8}{'Kram':>11}{'dKn':>9}{'bCurv':>7}")
    print(hdr)
    print("-" * W_TOT)
    last = None
    for r in rows:
        if last is not None and r["domain"] != last:
            print("-" * W_TOT)
        last = r["domain"]
        c4ok = sum(int(bool(r.get(f"match_{k}")))
                   for k in ("Edot", "cos_theta", "gamma", "rho_eff"))
        bc   = r.get("beta_curv", float("nan"))
        bc_s = f"{bc:.3f}" if isinstance(bc, float) and not np.isnan(bc) else "  -  "
        print(
            f"{r['domain']:<14}{r['engine']:<12}{r['n_onsets']:>4}"
            f"{_sig(r.get('desc_frac'), None, '{:.3f}'):>7}"
            f"{_sig(r.get('drift_Edot'),      r.get('pbonf_Edot')):>9}"
            f"{_sig(r.get('drift_cos_theta'), r.get('pbonf_cos_theta')):>9}"
            f"{_sig(r.get('drift_gamma'),     r.get('pbonf_gamma')):>9}"
            f"{_sig(r.get('drift_rho_eff'),   r.get('pbonf_rho_eff')):>9}"
            f"{c4ok:>5}"
            f"{_sig(r.get('p3_conc_ratio'),   r.get('p_p3'),     '{:.2f}'):>8}"
            f"{_sig(r.get('disj_conc_ratio'), r.get('p_disj'),   '{:.2f}'):>8}"
            f"{_sig(r.get('disj_lead'),       None,              '{:.1f}'):>7}"
            f"{_sig(r.get('betti_conc_ratio'),r.get('p_betti'),  '{:.2f}'):>8}"
            f"{_sig(r.get('kramers_drift'),   r.get('p_kramers'),'{:+.2e}'):>11}"
            f"{_sig(r.get('kappa_norm_drift'),r.get('p_kappa_norm'),'{:+.3f}'):>9}"
            f"{bc_s:>7}"
        )
    print("=" * W_TOT)
    print("descF  : fraction of quiescent steps with Edot<0   (C1, want > 0.5)")
    print("dEdot  : energy-rate drift pre-onset                (C2, predict +)")
    print("dCos/dgam/drho : geometry drift pre-onset           (C4, predict + / + / -)")
    print("C4ok   : # of {Edot,cos,gamma,rho} correctly signed AND Bonferroni-significant")
    print("P3conc : three-phase AND-precursor rate-ratio        (C3, want > 1)")
    print("Disj   : OR-precursor [Edot rise | cos rise] ratio  (C3b, want > 1)")
    print("Dlead  : mean lead (steps) of OR-precursor pre-onset (larger = earlier)")
    print("Betti  : Morse-index flip rate-ratio pre-onset       (C5, want > 1)")
    print("Kram   : Kramers crossing-hazard drift pre-onset     (C6, want > 0)")
    print("dKn    : κ_norm drift pre-onset (cgs1_curv only)     (C7, predict +)")
    print("bCurv  : β* calibrated curvature weight (cgs1_curv only)")
    print("=" * W_TOT)

    # Confirmation summary
    print("\nCONFIRMED PRECURSORS (Bonferroni-significant, theory-signed C4 diagnostics):")
    any_conf = False
    for r in rows:
        hits = [k for k in ("Edot", "cos_theta", "gamma", "rho_eff") if r.get(f"match_{k}")]
        if r.get("match_kappa_norm"):
            hits.append("kappa_norm")
        if hits:
            any_conf = True
            parts = []
            for k in hits:
                drift_k = r.get("drift_" + k, r.get("kappa_norm_drift", float("nan")))
                frac_k  = r.get("poFrac_" + k, float("nan"))
                if k == "kappa_norm":
                    parts.append(f"kappa_norm={r.get('kappa_norm_drift', float('nan')):+.3f}")
                else:
                    parts.append(f"{k}={drift_k:+.3f}(frac+={frac_k:.2f})")
            print(f"  {r['domain']:<14} {r['engine']:<12} n_on={r['n_onsets']:<3} -> {', '.join(parts)}")
    if not any_conf:
        print("  (none)")
    print("=" * W_TOT + "\n")

    # Curvature-specific summary: cgs1_curv vs cgs1 on shared diagnostics
    curv_rows  = [r for r in rows if r["engine"] == "cgs1_curv"]
    base_rows  = {(r["domain"], r["engine"]): r for r in rows}
    if curv_rows:
        print("CURVATURE TIER COMPARISON  (cgs1_curv vs cgs1 — Prop 67.7: γ_u ≥ γ_E):")
        for rc in curv_rows:
            rb = base_rows.get((rc["domain"], "cgs1"))
            if rb is None:
                continue
            d_rho_c = rc.get("drift_rho_eff", float("nan"))
            d_rho_b = rb.get("drift_rho_eff", float("nan"))
            d_kn    = rc.get("kappa_norm_drift", float("nan"))
            beta_c  = rc.get("beta_curv", float("nan"))
            kappa_r = rc.get("kappa_ref", float("nan"))
            sign_ok = "✓" if (np.isfinite(d_rho_c) and np.isfinite(d_rho_b)
                               and d_rho_c <= d_rho_b) else "?"
            print(f"  {rc['domain']:<14} drho_curv={d_rho_c:+.4f}  drho_cgs1={d_rho_b:+.4f}"
                  f"  Prop67.7={sign_ok}"
                  f"  dKn={d_kn:+.4f}  kappa={kappa_r:.3f}  beta*={beta_c:.4f}")
        print("=" * W_TOT + "\n")


def main() -> None:
    t0 = time.time()
    print("=" * 100)
    print("DYNAMICAL ENGINE VALIDATION — v4 / cgs1 / cgs1_morse / cgs1_stoch / cgs1_curv"
          "  ×  banks / protein / eeg")
    print("=" * 100)
    rows: list[dict] = []
    rows += domain_banks()
    rows += domain_eeg()
    rows += domain_protein()
    if not rows:
        print("No domains produced results.")
        return
    print_report(rows)
    out_path = os.path.join(ROOT, "benchmark_curv_results.json")
    payload  = {
        "generated":       time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine_tiers":    TIERS_CURV,
        "n_shuffle":       N_SHUFFLE,
        "g7_kappa_max":    G7_KAPPA_MAX,
        "predicted_signs": PREDICTED_SIGN,
        "claims": {
            "C1":  "Lyapunov descent: Edot<0 during quiescence",
            "C2":  "Energy precursor: Edot drifts + pre-onset",
            "C3":  "Three-phase AND-precursor concentrates pre-onset",
            "C3b": "Disjunction OR-precursor concentrates pre-onset",
            "C4":  "Geometry drift cos+/gamma+/rho- pre-onset",
            "C5":  "Betti/Morse flips time-lock pre-onset",
            "C6":  "Kramers crossing-hazard rises pre-onset",
            "C7":  "kappa_norm (normalised curvature) rises pre-onset (cgs1_curv only)",
        },
        "curvature_derivation": {
            "kappa_formula":    "2 * lambda_max(G)  [Hessian constant = 2G, §67.5]",
            "kappa_norm":       "kappa * E(t) / ||g_X(t)||^2  [§66]",
            "h_factor":         "1 + beta* * kappa_norm(t)  [§67.2]",
            "E_unified":        "E(t) * h(t)  [Prop 67.2, valid Lyapunov]",
            "g_tilde":          "h(t) * g_X(t)  [grad kappa_norm = 0 for quad E, §67.5]",
            "beta_star":        "clip(std(kn_ref)/mean(kn_ref), 0, 1)  [SNR, §67.7]",
            "prop_67_7":        "gamma_unified >= gamma_E pointwise",
        },
        "results": rows,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Saved {len(rows)} rows -> {out_path}")
    print(f"Elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
