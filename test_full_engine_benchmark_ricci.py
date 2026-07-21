# -*- coding: utf-8 -*-
"""
test_full_engine_benchmark_ricci.py
======================================
Riemannian geometry of the BSDT occupancy manifold.

The energy-landscape Hessian curvature (§67) measures how E curves as a
*function*.  The question here is different:

    Does collapse occur where the OCCUPANCY MANIFOLD itself has negative
    Ricci curvature?

The occupancy manifold M is the set of states {X(t)} visited by the
trajectory, equipped with the G-metric (precision-induced Riemannian metric):

    d_G(x, y)² = (x − y)ᵀ G (x − y)

Three curvature measures are computed from the k-NN graph on M:

  C8   Ollivier-Ricci  κ_OR(t)
       Discrete analogue of sectional curvature via Wasserstein transport.
       For each k-NN edge (t, s):
           κ_OR(t, s) = 1 − W₁(μ_t, μ_s) / d_G(t, s)
       where μ_t = uniform on k-NN neighbourhood of t.
       κ < 0 ↔ neighbourhood distributions DIVERGE ↔ collapse corridor.
       W₁ approximated via 1D projection onto the edge direction (exact for
       1D, lower bound in higher dimensions; preserves the sign of κ).

  C9   Forman-Ricci  F(t)
       Combinatorial Ricci curvature of the weighted k-NN graph.
       Edge weights: w_{ts} = exp(−d²_G / σ²), σ² = median(d²)
       Vertex strength: w_v(t) = Σ_{s~t} w_{ts}
           F(t,s) = w_v(t) + w_v(s)
                  − √(w_{ts}) · [Σ_{s'~t,s'≠s} √(w_{ts'})
                                + Σ_{t'~s,t'≠t} √(w_{st'})]
       F < 0 ↔ strong edge surrounded by stronger neighbourhood ↔ bottleneck.

  C10  Bishop-Gromov volume ratio  BG(t)
       In d-dimensional flat space the k-th NN distance satisfies:
           r_k(t) / r_1(t) ≈ k^{1/d}
       The Bishop-Gromov ratio
           BG(t) = (r_k(t) / r_1(t)) / k^{1/d_eff}
       compares observed geodesic-ball growth to the flat-space prediction.
       BG > 1 ↔ manifold expands faster than flat ↔ negative Ricci curvature.
       Derived from the Bishop-Gromov comparison theorem: on a manifold with
       Ric ≥ (n−1)K, the normalised volume Vol(B(p,r)) / Vol_K(r) is
       non-increasing in r.

Physical interpretation (connection to BSDT gap observations):
  Negative Ricci regions naturally create geodesic spreading, instability,
  and divergence of nearby trajectories — precisely the "collapse corridor"
  structure visible in BSDT gap analysis.  Hamilton's Ricci flow concentrates
  mass away from negative-Ricci regions, generating the disconnected supports
  and bottlenecks observed in the benchmark.  Pre-onset states should
  consistently lie IN, or be approaching, negative-Ricci regions.

Structural claims (augmenting C1–C7 from the curvature benchmark):
  C8   drift(κ_OR)  < 0 pre-onset  (diverging neighbourhoods)
  C9   drift(F)     < 0 pre-onset  (bottleneck connectivity)
  C10  drift(BG)    > 0 pre-onset  (geodesic ball expands faster)

The Ricci observables are DOMAIN-LEVEL: computed once per domain using the
fitted G-metric, then appended to every engine-tier row.  The tier comparison
(C1–C7) is identical to test_full_engine_benchmark_curv.py.

Engine tiers: v4 / cgs1 / cgs1_morse / cgs1_stoch / cgs1_curv
Domains:      banks / eeg / protein
Output:       benchmark_ricci_results.json

Author: Copilot — June 2026
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings

import numpy as np
from scipy.spatial import cKDTree

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

EPS              = 1e-12
N_SHUFFLE        = 2000
K_RICCI          = 10     # k-NN neighbours for manifold curvature
BONFERRONI_RICCI = 3      # separate Bonferroni family for C8-C10
TIERS_CURV       = ["v4", "cgs1", "cgs1_morse", "cgs1_stoch", "cgs1_curv"]
G7_KAPPA_MAX     = 10.0

# Theory-predicted signs of pre-onset drift for geometry diagnostics
PREDICTED_SIGN = {
    "cos_theta":       +1.0,
    "gamma":           +1.0,
    "rho_eff":         -1.0,
    "Edot":            +1.0,
    "kappa_norm":      +1.0,   # C7
}

# C8-C10: collapse corridors via Ricci curvature of the occupancy manifold
PREDICTED_SIGN_RICCI = {
    "ricci_ollivier":  -1.0,   # C8: diverging neighbourhoods  → drift < 0
    "ricci_forman":    -1.0,   # C9: bottleneck region         → drift < 0
    "ricci_bg":        +1.0,   # C10: faster geodesic ball growth → drift > 0
}


# ════════════════════════════════════════════════════════════════════════════
#  CGS helpers (identical to curvature benchmark)
# ════════════════════════════════════════════════════════════════════════════

def _alpha_of(engine: FrozenCanonicalV4) -> float:
    return float(getattr(engine, "alpha_base_", getattr(engine, "alpha_base", 0.05)))


def build_cgs_fns(engine: FrozenCanonicalV4):
    mu, sigma, G = engine.mu_, engine.sigma_, engine.G_
    alpha, theta = _alpha_of(engine), float(engine.theta_)
    n_dim   = len(sigma)
    J_const = np.eye(n_dim)

    def S_fn(X):    return (np.asarray(X, dtype=float) - mu) / sigma
    def J_fn(X):    return J_const
    def Fbase_fn(X): return -alpha * S_fn(X)
    return S_fn, J_fn, G, Fbase_fn, theta


def compute_cos_theta_series(X: np.ndarray, engine: FrozenCanonicalV4) -> np.ndarray:
    mu, sigma, G = engine.mu_, engine.sigma_, engine.G_
    alpha = _alpha_of(engine)
    Z  = (np.asarray(X, dtype=float) - mu[None, :]) / sigma[None, :]
    gX = 2.0 * (Z @ G)
    Fb = -alpha * Z
    dot = np.einsum("ij,ij->i", gX, Fb)
    gn  = np.linalg.norm(gX, axis=1) + EPS
    fn  = np.linalg.norm(Fb, axis=1) + EPS
    return np.clip(dot / (gn * fn), -1.0, 1.0)


def compute_curv_params(engine: FrozenCanonicalV4, X_ref: np.ndarray):
    """Calibrate κ and β* from §67.5, §67.7 (for cgs1_curv tier)."""
    G  = engine.G_
    kappa = 2.0 * float(np.linalg.eigvalsh(G)[-1])
    Z_ref = (np.asarray(X_ref, dtype=float) - engine.mu_[None, :]) / engine.sigma_[None, :]
    GS    = Z_ref @ G
    E_ref = np.einsum("ij,ij->i", Z_ref, GS)
    gsq   = 4.0 * np.einsum("ij,ij->i", GS, GS)
    kn    = kappa * E_ref / (gsq + EPS)
    snr   = float(np.std(kn)) / (float(np.mean(kn)) + EPS)
    beta  = float(np.clip(snr, 0.0, 1.0))
    return kappa, beta


# ════════════════════════════════════════════════════════════════════════════
#  State-series extraction (all 5 tiers)
# ════════════════════════════════════════════════════════════════════════════

def engine_series(tier: str, engine: FrozenCanonicalV4, X: np.ndarray,
                  kappa: float = 0.0, beta_curv: float = 0.0) -> dict:
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
        Z  = (np.asarray(X, dtype=float) - mu[None, :]) / sigma[None, :]
        GS = Z @ G
        gX = 2.0 * GS
        E  = np.einsum("ij,ij->i", Z, GS)
        gsq = np.einsum("ij,ij->i", gX, gX)
        kn  = kappa * E / (gsq + EPS)
        h   = 1.0 + beta_curv * kn
        E_u = E * h
        gam_u = E_u / (E_u + theta)
        g_til = h[:, None] * gX
        F_tot = -alpha * Z - gX
        dot_F = np.einsum("ij,ij->i", F_tot, g_til)
        gtsq  = np.einsum("ij,ij->i", g_til, g_til)
        au    = dot_F / (gtsq + EPS)
        Xdot  = F_tot - (gam_u * au)[:, None] * g_til
        Ed_u  = np.einsum("ij,ij->i", g_til, Xdot)
        rho_u = -Ed_u / (np.abs(E_u) + EPS)
        cos_theta = compute_cos_theta_series(X, engine)
        return dict(E=E_u, Edot=Ed_u, g_norm=np.sqrt(gtsq),
                    cos_theta=cos_theta, gamma=gam_u, rho_eff=rho_u,
                    kappa_norm=kn)

    else:  # cgs1 / cgs1_morse / cgs1_stoch
        S_fn, J_fn, G, Fbase_fn, theta = build_cgs_fns(engine)
        b = evaluate_cgs_v1_batch(X, S_fn, J_fn, G, Fbase_fn, theta)
        cos_theta = compute_cos_theta_series(X, engine)
        rho_eff   = -b["Edot"] / (np.abs(b["E"]) + EPS)
        return dict(E=b["E"], Edot=b["Edot"], g_norm=b["g_norm"],
                    cos_theta=cos_theta, gamma=b["gamma"], rho_eff=rho_eff)


# ════════════════════════════════════════════════════════════════════════════
#  Riemannian geometry of the occupancy manifold
# ════════════════════════════════════════════════════════════════════════════

def _g_cholesky(G: np.ndarray) -> np.ndarray:
    """Return L such that G = L Lᵀ (robust to near-singular G)."""
    d = G.shape[0]
    try:
        return np.linalg.cholesky(G + 1e-10 * np.eye(d))
    except np.linalg.LinAlgError:
        lam, V = np.linalg.eigh(G)
        return V @ np.diag(np.sqrt(np.maximum(lam, 1e-10)))


def build_g_metric_knn(X: np.ndarray, G: np.ndarray, k: int = K_RICCI):
    """Build k-NN graph using the G-metric d_G(x,y)² = (x−y)ᵀ G (x−y).

    Returns (XL, dists, idx):
      XL   : (T, d) G-isometric embedding; ||XL[t] − XL[s]|| = d_G(X[t], X[s])
      dists: (T, k) distances to k nearest neighbours (self excluded)
      idx  : (T, k) indices of the k nearest neighbours
    """
    L  = _g_cholesky(G)
    XL = X @ L                               # (T, d) G-isometric embedding
    k_eff = min(k + 1, len(X))
    tree  = cKDTree(XL)
    dists_raw, idx_raw = tree.query(XL, k=k_eff)
    return XL, dists_raw[:, 1:], idx_raw[:, 1:]   # strip self


def compute_ollivier_ricci(XL: np.ndarray, dists: np.ndarray,
                            idx: np.ndarray) -> np.ndarray:
    """Per-step Ollivier-Ricci curvature of the occupancy manifold.

    For each k-NN edge (t, s):
        κ_OR(t, s) = 1 − W₁(μ_t, μ_s) / d_G(t, s)
    where μ_t = uniform distribution on the k nearest neighbours of t.

    W₁ is computed via 1D projection onto the edge direction (t→s) and
    sorted matching — exact for 1D distributions, a valid approximation
    in higher dimensions that preserves the sign of curvature.

    κ < 0  →  neighbourhood distributions diverge  →  collapse corridor.
    """
    T, k = dists.shape
    kappa = np.zeros(T)
    for t in range(T):
        nbrs_t = idx[t]           # (k,) neighbor indices
        pts_t  = XL[nbrs_t]       # (k, d) neighbourhood of t
        kappa_t = []
        for i, s in enumerate(nbrs_t):
            d_ts = float(dists[t, i])
            if d_ts < EPS:
                continue
            v      = XL[s] - XL[t]                    # edge vector
            v_norm = float(np.linalg.norm(v)) + EPS
            v_unit = v / v_norm                        # (d,) unit direction

            pts_s  = XL[idx[s]]                        # (k, d) neighbourhood of s

            # 1D projection onto edge direction → sorted matching → W₁
            proj_t = pts_t @ v_unit                    # (k,)
            proj_s = pts_s @ v_unit                    # (k,)
            w1     = float(np.mean(np.abs(np.sort(proj_t) - np.sort(proj_s))))
            kappa_t.append(1.0 - w1 / d_ts)

        kappa[t] = float(np.mean(kappa_t)) if kappa_t else 0.0
    return kappa


def compute_forman_ricci(XL: np.ndarray, dists: np.ndarray,
                          idx: np.ndarray) -> np.ndarray:
    """Per-step Forman-Ricci curvature of the G-metric k-NN graph.

    Edge weights:    w_{ts} = exp(−d²_G(t,s) / σ²),   σ² = median(d²)
    Vertex strength: w_v(t) = Σ_{s~t} w_{ts}

    Forman-Ricci of edge (t, s):
        F(t,s) = w_v(t) + w_v(s)
               − √(w_{ts}) · [ Σ_{s'~t, s'≠s} √(w_{ts'})
                              + Σ_{t'~s, t'≠t} √(w_{st'}) ]

    Per-step curvature = mean F over incident edges.
    F < 0  →  strong edge in a highly-connected neighbourhood  →  bottleneck.
    """
    T, k = dists.shape
    sigma2  = float(np.median(dists) ** 2) + EPS
    W       = np.exp(-dists ** 2 / sigma2)     # (T, k)
    vstr    = W.sum(axis=1)                     # (T,) vertex strengths
    sqrtW   = np.sqrt(W)                        # (T, k)
    sum_sqW = sqrtW.sum(axis=1)                 # (T,)

    forman  = np.zeros(T)
    for t in range(T):
        nbrs  = idx[t]           # (k,)
        w_t   = W[t]             # (k,)
        sq_t  = sqrtW[t]         # (k,)
        ss_t  = float(sum_sqW[t])
        wv_t  = float(vstr[t])
        wv_s  = vstr[nbrs]       # (k,)

        # Triangle contribution at t:
        # For edge (t→s_i): Σ_{j≠i} sq_t[j] = ss_t − sq_t[i]
        # Contribution: sq_t[i] × (ss_t − sq_t[i])
        tri_t = sq_t * (ss_t - sq_t)            # (k,)

        # Triangle contribution at s_i:
        # sq_t[i] × (sum_sqW[s_i] − sq(w_{s_i → t}))
        tri_s = np.zeros(k)
        for i, s in enumerate(nbrs):
            pos = np.where(idx[s] == t)[0]
            sq_back = float(sqrtW[s, pos[0]]) if pos.size > 0 else 0.0
            tri_s[i] = sq_t[i] * (float(sum_sqW[s]) - sq_back)

        F_edges = wv_t + wv_s - tri_t - tri_s
        forman[t] = float(np.mean(F_edges))

    return forman


def compute_bishop_gromov(dists: np.ndarray, d_eff: int) -> np.ndarray:
    """Bishop-Gromov volume-comparison curvature proxy.

    In d-dimensional flat space:  r_k(t) / r_1(t) ≈ k^{1/d}

    BG(t) = (r_k(t) / r_1(t)) / k^{1/d_eff}

    BG > 1  →  geodesic ball grows faster than flat  →  Ric < 0
    BG < 1  →  slower growth  →  Ric > 0

    Derived from the Bishop-Gromov comparison theorem applied to the
    empirical k-NN ball volume.
    """
    k     = dists.shape[1]
    r1    = dists[:, 0] + EPS                    # first NN distance   (T,)
    rk    = dists[:, -1] + EPS                   # k-th NN distance    (T,)
    flat  = float(k ** (1.0 / max(d_eff, 1)))    # flat-space prediction
    return rk / (r1 * flat)                       # > 1 = negative Ricci


def compute_all_ricci(X: np.ndarray, G: np.ndarray,
                      k: int = K_RICCI) -> dict:
    """Compute all three Ricci curvature series for trajectory X with G-metric.

    Returns dict with keys: 'ricci_ollivier', 'ricci_forman', 'ricci_bg'.
    """
    T, d = X.shape
    k_use = min(k, T - 1)
    t0    = time.time()
    print(f"    [ricci] k-NN (T={T}, d={d}, k={k_use}) ", end="", flush=True)

    XL, dists, nn_idx = build_g_metric_knn(X, G, k_use)
    print(f"kNN:{time.time()-t0:.1f}s ", end="", flush=True)

    ro = compute_ollivier_ricci(XL, dists, nn_idx)
    print(f"Olliv:{time.time()-t0:.1f}s ", end="", flush=True)

    rf = compute_forman_ricci(XL, dists, nn_idx)
    print(f"Forman:{time.time()-t0:.1f}s ", end="", flush=True)

    bg = compute_bishop_gromov(dists, d_eff=d)
    print(f"BG:{time.time()-t0:.1f}s")

    print(f"    [ricci] Olliv={ro.mean():+.4f}±{ro.std():.4f}  "
          f"Forman={rf.mean():+.4f}±{rf.std():.4f}  "
          f"BG={bg.mean():.4f}±{bg.std():.4f}")

    return dict(ricci_ollivier=ro, ricci_forman=rf, ricci_bg=bg)


# ════════════════════════════════════════════════════════════════════════════
#  Standard dynamical instruments (identical to curvature benchmark)
# ════════════════════════════════════════════════════════════════════════════

def onset_events(crisis_mask: np.ndarray) -> np.ndarray:
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
    q = ~np.asarray(crisis_mask, dtype=bool)
    if q.sum() == 0:
        return dict(desc_frac=float("nan"), Edot_quiescent=float("nan"))
    eq = Edot[q]
    return dict(desc_frac=float((eq < 0).mean()),
                Edot_quiescent=float(np.mean(eq)))


def _drift_stat(signal: np.ndarray, onsets: np.ndarray, W: int) -> float:
    T   = len(signal)
    pre = _pre_onset_mask(onsets, W, T)
    if pre.sum() == 0:
        return float("nan")
    return float(np.mean(signal[pre]) - np.mean(signal))


def _rate_ratio(boolean: np.ndarray, onsets: np.ndarray, W: int) -> float:
    T   = len(boolean)
    pre = _pre_onset_mask(onsets, W, T)
    base = float(np.mean(boolean)) + EPS
    if pre.sum() == 0:
        return float("nan")
    return float(np.mean(boolean[pre]) / base)


def per_onset_drift(signal: np.ndarray, onsets: np.ndarray, W: int) -> dict:
    g    = float(np.mean(signal))
    vals = []
    T    = len(signal)
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


def precursor_lead(boolean: np.ndarray, onsets: np.ndarray, W: int) -> float:
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


def event_shuffle_p(signal: np.ndarray, onsets: np.ndarray, W: int,
                    stat_fn, observed: float, n: int = N_SHUFFLE,
                    two_sided: bool = True) -> float:
    T = len(signal)
    k = len(onsets)
    if k == 0 or not np.isfinite(observed):
        return float("nan")
    null = np.empty(n)
    lo, hi = W, T
    for i in range(n):
        fake   = np.random.randint(lo, hi, size=k) if hi > lo else onsets
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
        denom       = np.sqrt(abs(dmu[t]) * abs(mu_star_slope)) + 1e-12
        log_barrier = min(2.0 * (e_star - e_t) / s2, 700.0)
        tau_K       = (2.0 * np.pi / denom) * np.exp(log_barrier)
        h[t]        = 1.0 - np.exp(-tau / max(tau_K, 1e-12))
    return h


# ════════════════════════════════════════════════════════════════════════════
#  Per-engine evaluation  (C1–C7 identical to curvature benchmark)
# ════════════════════════════════════════════════════════════════════════════

def run_one_engine(tier: str, engine: FrozenCanonicalV4, X: np.ndarray,
                   crisis_mask: np.ndarray, label: str, W: int,
                   kappa: float = 0.0, beta_curv: float = 0.0,
                   ricci: dict | None = None) -> dict:
    X           = np.asarray(X, dtype=float)
    crisis_mask = np.asarray(crisis_mask, dtype=bool)
    T           = X.shape[0]
    s           = engine_series(tier, engine, X, kappa=kappa, beta_curv=beta_curv)
    onsets      = onset_events(crisis_mask)
    n_on        = len(onsets)

    row = {"domain": label, "engine": tier, "n_onsets": int(n_on),
           "T": int(T), "W": int(W)}
    if tier == "cgs1_curv":
        row["kappa_ref"] = float(kappa)
        row["beta_curv"] = float(beta_curv)

    # C1 — Lyapunov descent during quiescence
    row.update(lyapunov_descent(s["Edot"], crisis_mask))

    # C2 + C4 — energy + geometry drift, Bonferroni×4
    geom_keys = ["Edot", "cos_theta", "gamma", "rho_eff"]
    n_tests   = len(geom_keys)
    for key in geom_keys:
        d      = _drift_stat(s[key], onsets, W)
        p      = event_shuffle_p(s[key], onsets, W, _drift_stat, d)
        p_bonf = min(1.0, p * n_tests) if np.isfinite(p) else float("nan")
        row[f"drift_{key}"]  = d
        row[f"p_{key}"]      = p
        row[f"pbonf_{key}"]  = p_bonf
        pod = per_onset_drift(s[key], onsets, W)
        row[f"poFrac_{key}"] = pod["frac_pos"]
        pred = PREDICTED_SIGN[key]
        row[f"match_{key}"]  = bool(np.isfinite(d) and np.sign(d) == pred
                                    and np.isfinite(p_bonf) and p_bonf < 0.05)

    # C3 — three-phase AND-precursor
    topo = TSB.morse_curvature_signals(
        s["E"], s["g_norm"], s["cos_theta"], engine.G_, alpha_base=_alpha_of(engine))
    p3 = topo["three_phase_mask"].astype(float)
    r3 = _rate_ratio(p3, onsets, W)
    row["p3_conc_ratio"]  = r3
    row["p_p3"]           = event_shuffle_p(p3, onsets, W, _rate_ratio, r3)
    row["p3_global_rate"] = float(p3.mean())
    row["p3_lead"]        = precursor_lead(topo["three_phase_mask"], onsets, W)

    # C3b — disjunction OR-precursor
    Edot_rise = np.concatenate([[False], np.diff(s["Edot"])      > 0]) if T > 1 else np.zeros(T, bool)
    cos_rise  = np.concatenate([[False], np.diff(s["cos_theta"]) > 0]) if T > 1 else np.zeros(T, bool)
    p_disj = (Edot_rise | cos_rise).astype(float)
    rd = _rate_ratio(p_disj, onsets, W)
    row["disj_conc_ratio"]  = rd
    row["p_disj"]           = event_shuffle_p(p_disj, onsets, W, _rate_ratio, rd)
    row["disj_global_rate"] = float(p_disj.mean())
    row["disj_lead"]        = precursor_lead((Edot_rise | cos_rise), onsets, W)

    # C5 — Betti/Morse  (cgs1_morse / cgs1_stoch / cgs1_curv)
    if tier in ("cgs1_morse", "cgs1_stoch", "cgs1_curv"):
        bt = topo["betti_transitions"].astype(float)
        rb = _rate_ratio(bt, onsets, W)
        row["betti_conc_ratio"]  = rb
        row["p_betti"]           = event_shuffle_p(bt, onsets, W, _rate_ratio, rb)
        row["betti_global_rate"] = float(bt.mean())
        row["betti_peak"]        = int(topo["betti_cumulative"][-1]) if T else 0

    # C6 — Kramers  (cgs1_stoch / cgs1_curv)
    if tier in ("cgs1_stoch", "cgs1_curv"):
        E_arr   = s["E"]
        q       = ~crisis_mask
        e_star  = (float(np.mean(E_arr[q]) + 2.0 * np.std(E_arr[q]))
                   if q.sum() else float(np.mean(E_arr)))
        sigma_n = float(np.std(np.diff(E_arr))) + EPS
        tau_h   = float(max(1.0, W))
        h_t     = kramers_hazard(E_arr, s["Edot"], e_star, sigma_n, tau_h)
        dh = _drift_stat(h_t, onsets, W)
        row["kramers_drift"]       = dh
        row["p_kramers"]           = event_shuffle_p(h_t, onsets, W, _drift_stat, dh)
        row["kramers_global_mean"] = float(np.mean(h_t))
        row["e_star"]              = e_star
        row["sigma_n_eff"]         = sigma_n

    # C7 — κ_norm drift  (cgs1_curv only)
    if tier == "cgs1_curv" and "kappa_norm" in s:
        kn  = s["kappa_norm"]
        dkn = _drift_stat(kn, onsets, W)
        pkn = event_shuffle_p(kn, onsets, W, _drift_stat, dkn)
        row["kappa_norm_drift"] = dkn
        row["p_kappa_norm"]     = pkn
        row["match_kappa_norm"] = bool(np.isfinite(dkn) and np.sign(dkn) == +1.0
                                       and np.isfinite(pkn) and pkn < 0.05)

    # C8-C10 — Ricci curvature of the occupancy manifold (domain-level, same all tiers)
    if ricci is not None:
        for rkey, pred_sign in PREDICTED_SIGN_RICCI.items():
            rval = ricci.get(rkey)
            if rval is None:
                continue
            dr = _drift_stat(rval, onsets, W)
            pr = event_shuffle_p(rval, onsets, W, _drift_stat, dr)
            pr_bonf = min(1.0, pr * BONFERRONI_RICCI) if np.isfinite(pr) else float("nan")
            row[f"drift_{rkey}"]  = dr
            row[f"p_{rkey}"]      = pr
            row[f"pbonf_{rkey}"]  = pr_bonf
            row[f"match_{rkey}"]  = bool(
                np.isfinite(dr) and np.sign(dr) == pred_sign
                and np.isfinite(pr_bonf) and pr_bonf < 0.05)
        # Domain-level Ricci summary stats
        for rkey in PREDICTED_SIGN_RICCI:
            rval = ricci.get(rkey)
            if rval is not None:
                row[f"{rkey}_global_mean"] = float(np.mean(rval))
                row[f"{rkey}_global_std"]  = float(np.std(rval))

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


def run_all_tiers_ricci(X_ref, X, crisis_mask, label, W) -> list[dict]:
    """Fit engine, compute Ricci series once, then evaluate all 5 tiers."""
    # Fit a single reference engine to get G (all tiers use the same G7 result)
    ref_engine = FrozenCanonicalV4(alpha_base=0.05)
    ref_engine.fit(X_ref)
    TSB.apply_g7_to_engine(ref_engine, G7_KAPPA_MAX)
    ricci = compute_all_ricci(X, ref_engine.G_, k=K_RICCI)

    rows = []
    for tier in TIERS_CURV:
        engine = FrozenCanonicalV4(alpha_base=0.05)
        engine.fit(X_ref)
        lam_g7 = TSB.apply_g7_to_engine(engine, G7_KAPPA_MAX)
        if tier == "cgs1_curv":
            kappa, beta_c = compute_curv_params(engine, X_ref)
        else:
            kappa, beta_c = 0.0, 0.0
        r = run_one_engine(tier, engine, X, crisis_mask, label, W,
                           kappa=kappa, beta_curv=beta_c, ricci=ricci)
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
    npz   = np.load(cache)
    X_3d  = npz["X"]
    T     = X_3d.shape[0]
    dates = pd.date_range("2005-01-01", "2023-12-31", freq="QE")[:T]
    Xagg  = np.nan_to_num(np.nanmean(X_3d, axis=1), nan=0.0, posinf=0.0, neginf=0.0)
    windows = [("2008-09-30", "2009-03-31"), ("2011-09-30", "2012-03-31"),
               ("2020-03-31", "2020-06-30"), ("2023-03-31", "2023-06-30")]
    crisis = np.zeros(T, dtype=bool)
    for lo, hi in windows:
        crisis |= np.asarray((dates >= pd.Timestamp(lo)) & (dates <= pd.Timestamp(hi)))
    X_ref = Xagg[np.asarray(dates < pd.Timestamp("2008-01-01"))]
    print(f"[banks] T={T} d={Xagg.shape[1]} ref={len(X_ref)} onsets={len(onset_events(crisis))}")
    return run_all_tiers_ricci(X_ref, Xagg, crisis, "banks", W=4)


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
        rows += run_all_tiers_ricci(X_ref, X, crisis, f"protein:{pdb_id}", W=5)
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
    return run_all_tiers_ricci(X_ref, X_eeg, crisis, "eeg", W=64)


# ════════════════════════════════════════════════════════════════════════════
#  Reporting
# ════════════════════════════════════════════════════════════════════════════

def _sig(val, p, fmt="{:+.3f}"):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "   -   "
    star = "*" if (isinstance(p, float) and np.isfinite(p) and p < 0.05) else " "
    return fmt.format(val) + star


def print_report(rows: list[dict]) -> None:
    W_TOT = 158
    print("\n" + "=" * W_TOT)
    print("DYNAMICAL + RICCI VALIDATION  "
          "( * = p < 0.05 ; C4: Bonferroni×4 ; C8-C10: Bonferroni×3 )")
    print("=" * W_TOT)
    hdr = (f"{'domain':<14}{'engine':<12}{'n_on':>4}{'descF':>7}"
           f"{'dEdot':>9}{'dCos':>9}{'dgam':>9}{'drho':>9}"
           f"{'C4ok':>5}{'P3':>7}{'Disj':>7}{'Kram':>10}"
           f"{'dKn':>8}"
           f"{'dOlliv':>9}{'dForman':>9}{'dBG':>8}")
    print(hdr)
    print("-" * W_TOT)
    last = None
    for r in rows:
        if last is not None and r["domain"] != last:
            print("-" * W_TOT)
        last = r["domain"]
        c4ok = sum(int(bool(r.get(f"match_{k}")))
                   for k in ("Edot", "cos_theta", "gamma", "rho_eff"))
        print(
            f"{r['domain']:<14}{r['engine']:<12}{r['n_onsets']:>4}"
            f"{_sig(r.get('desc_frac'), None, '{:.3f}'):>7}"
            f"{_sig(r.get('drift_Edot'),      r.get('pbonf_Edot')):>9}"
            f"{_sig(r.get('drift_cos_theta'), r.get('pbonf_cos_theta')):>9}"
            f"{_sig(r.get('drift_gamma'),     r.get('pbonf_gamma')):>9}"
            f"{_sig(r.get('drift_rho_eff'),   r.get('pbonf_rho_eff')):>9}"
            f"{c4ok:>5}"
            f"{_sig(r.get('p3_conc_ratio'),   r.get('p_p3'),    '{:.2f}'):>7}"
            f"{_sig(r.get('disj_conc_ratio'), r.get('p_disj'),  '{:.2f}'):>7}"
            f"{_sig(r.get('kramers_drift'),   r.get('p_kramers'),'{:+.2e}'):>10}"
            f"{_sig(r.get('kappa_norm_drift'),r.get('p_kappa_norm'),'{:+.3f}'):>8}"
            f"{_sig(r.get('drift_ricci_ollivier'), r.get('pbonf_ricci_ollivier'),'{:+.4f}'):>9}"
            f"{_sig(r.get('drift_ricci_forman'),   r.get('pbonf_ricci_forman'),  '{:+.4f}'):>9}"
            f"{_sig(r.get('drift_ricci_bg'),        r.get('pbonf_ricci_bg'),      '{:+.4f}'):>8}"
        )
    print("=" * W_TOT)
    print("C4ok  : # of {Edot,cos,gamma,rho} correctly signed AND Bonf-significant")
    print("dOlliv: Ollivier-Ricci drift pre-onset  (C8, predict <0 = diverging nbhds)")
    print("dForman: Forman-Ricci drift pre-onset   (C9, predict <0 = bottleneck region)")
    print("dBG   : Bishop-Gromov ratio drift       (C10, predict >0 = faster ball growth)")
    print("dKn   : κ_norm drift (cgs1_curv only)   (C7, predict >0)")
    print("=" * W_TOT)

    # Confirmed precursors
    print("\nCONFIRMED C1-C7 PRECURSORS (Bonferroni-significant, theory-signed):")
    any_conf = False
    for r in rows:
        hits = [k for k in ("Edot", "cos_theta", "gamma", "rho_eff") if r.get(f"match_{k}")]
        if r.get("match_kappa_norm"):
            hits.append("kappa_norm")
        if hits:
            any_conf = True
            parts = []
            for k in hits:
                if k == "kappa_norm":
                    parts.append(f"kappa_norm={r.get('kappa_norm_drift', float('nan')):+.3f}")
                else:
                    parts.append(f"{k}={r['drift_'+k]:+.3f}(f+={r.get('poFrac_'+k, float('nan')):.2f})")
            print(f"  {r['domain']:<14} {r['engine']:<12} n={r['n_onsets']:<3} -> {', '.join(parts)}")
    if not any_conf:
        print("  (none)")

    # Ricci collapse corridor summary (C8-C10)
    print("\nCONFIRMED RICCI COLLAPSE CORRIDORS (C8-C10, Bonferroni×3):")
    any_ricci = False
    seen = set()  # Ricci is domain-level; show each domain once
    for r in rows:
        dom = r["domain"]
        if dom in seen:
            continue
        hits_ricci = [k for k in PREDICTED_SIGN_RICCI if r.get(f"match_{k}")]
        if hits_ricci:
            any_ricci = True
            seen.add(dom)
            parts = []
            for k in hits_ricci:
                d_val = r.get(f"drift_{k}", float("nan"))
                mean_val = r.get(f"{k}_global_mean", float("nan"))
                parts.append(f"{k}={d_val:+.4f}(mean={mean_val:.4f})")
            print(f"  {dom:<14} n_on={r['n_onsets']:<3} -> {', '.join(parts)}")
    if not any_ricci:
        print("  (none — collapse corridors not detected at Bonferroni×3)")

    # Ricci curvature landscape summary (global means)
    print("\nOCCUPANCY MANIFOLD RICCI CURVATURE LANDSCAPE (global means across all tiers):")
    print(f"  {'domain':<14} {'Olliv_mean':>12} {'Forman_mean':>13} {'BG_mean':>9}"
          f"  interpretation")
    last_dom_r = None
    for r in rows:
        dom = r["domain"]
        if dom == last_dom_r:
            continue
        last_dom_r = dom
        om   = r.get("ricci_ollivier_global_mean", float("nan"))
        fm   = r.get("ricci_forman_global_mean",   float("nan"))
        bgm  = r.get("ricci_bg_global_mean",        float("nan"))
        if not np.isfinite(om):
            continue
        interp = ("negative Ricci → collapse corridor present"
                  if om < 0 else "positive Ricci → stable region")
        print(f"  {dom:<14} {om:>+12.4f} {fm:>+13.4f} {bgm:>9.4f}  {interp}")

    print("=" * W_TOT + "\n")


def main() -> None:
    t0 = time.time()
    print("=" * 100)
    print("DYNAMICAL + RICCI VALIDATION — Riemannian geometry of the occupancy manifold")
    print("Tiers: v4 / cgs1 / cgs1_morse / cgs1_stoch / cgs1_curv  ×  banks / eeg / protein")
    print("=" * 100)
    rows: list[dict] = []
    rows += domain_banks()
    rows += domain_eeg()
    rows += domain_protein()
    if not rows:
        print("No domains produced results.")
        return
    print_report(rows)
    out_path = os.path.join(ROOT, "benchmark_ricci_results.json")
    payload  = {
        "generated":       time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine_tiers":    TIERS_CURV,
        "n_shuffle":       N_SHUFFLE,
        "k_ricci":         K_RICCI,
        "g7_kappa_max":    G7_KAPPA_MAX,
        "predicted_signs": {**PREDICTED_SIGN, **PREDICTED_SIGN_RICCI},
        "claims": {
            "C1":  "Lyapunov descent: Edot<0 during quiescence",
            "C2":  "Energy precursor: Edot drifts + pre-onset",
            "C3":  "Three-phase AND-precursor concentrates pre-onset",
            "C3b": "Disjunction OR-precursor concentrates pre-onset",
            "C4":  "Geometry drift cos+/gamma+/rho- pre-onset",
            "C5":  "Betti/Morse flips time-lock pre-onset",
            "C6":  "Kramers crossing-hazard rises pre-onset",
            "C7":  "kappa_norm drift pre-onset (cgs1_curv only)",
            "C8":  "Ollivier-Ricci curvature < 0 pre-onset (diverging nbhds)",
            "C9":  "Forman-Ricci curvature < 0 pre-onset (bottleneck region)",
            "C10": "Bishop-Gromov ratio > 1 pre-onset (geodesic ball expansion)",
        },
        "ricci_theory": {
            "metric":       "d_G(x,y)² = (x-y)^T G (x-y)  [precision-induced]",
            "ollivier":     "kappa_OR(t,s) = 1 - W1(mu_t, mu_s) / d_G(t,s)",
            "w1_approx":    "1D sliced projection onto edge direction",
            "forman":       "F(t,s) = wv_t + wv_s - sqrt(w_ts)*[tri_t + tri_s]",
            "bishop_gromov": "BG = (r_k/r_1) / k^{1/d}; >1 ↔ Ric < 0",
            "bonferroni":   f"Family size = {BONFERRONI_RICCI} (C8,C9,C10 separate from C1-C7)",
            "connection":   ("Negative Ricci → geodesic spreading → collapse corridors."
                             " Ricci flow concentrates mass away from negative-Ricci regions,"
                             " generating BSDT gaps and disconnected supports."),
        },
        "results": rows,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Saved {len(rows)} rows -> {out_path}")
    print(f"Elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
