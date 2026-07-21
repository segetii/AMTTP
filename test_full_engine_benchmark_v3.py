# -*- coding: utf-8 -*-
"""
test_full_engine_benchmark_v3.py
=================================
Third-generation benchmark: fixes C5 (persistence threshold) and C6 (sigma_n).

Changes vs v2:
  C5  PERSISTENCE FILTER — sublevel filtration now tracks per-component birth
                           Forman value.  Only marks a β₀ death when
                           persistence = F(merge_vertex) − F(component_birth)
                           exceeds tau_persist = std(Forman) (data-adaptive).
                           Eliminates the trivial saturation (76/76, 100%) that
                           occurred because k=10 makes the kNN graph near-complete.

  C6  SIGMA_N FIX        — std(diff(E_norm)) evaluates to ~1e-4 on smooth EEG
                           signals, causing the Kramers exp(barrier/σ²) to blow
                           up (h → 0 everywhere, drift ≈ 0).  Replace with
                           sigma_n = std(E_norm) ≈ 1 (spread of energy in the
                           normalized frame), so the barrier and noise are in
                           the same units and h varies meaningfully.

All other v2 features preserved (C2 accel, C3 retired, C7 κ_norm, C8-C10 Ricci).

Output: benchmark_v3_results.json

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
K_RICCI          = 10
BONFERRONI_MAIN  = 4   # C2(new) / C4: Edot_accel, cos_theta, gamma, rho_eff
BONFERRONI_RICCI = 3   # C8-C10: Ollivier, Forman, BG
TIERS            = ["v4", "cgs1", "cgs1_stoch", "cgs1_curv"]
G7_KAPPA_MAX     = 10.0

# C2 (new) + C4: predicted sign of pre-onset drift
PREDICTED_SIGN = {
    "Edot_accel": -1.0,   # C2: d(Edot)/dt < 0 → dissipation accelerates
    "cos_theta":  +1.0,   # C4
    "gamma":      +1.0,   # C4
    "rho_eff":    -1.0,   # C4
}

# C8-C10: Ricci curvature collapse corridor signals
PREDICTED_SIGN_RICCI = {
    "ricci_ollivier": -1.0,   # C8: diverging neighbourhoods → drift < 0
    "ricci_forman":   -1.0,   # C9: bottleneck region        → drift < 0
    "ricci_bg":       +1.0,   # C10: faster ball growth      → drift > 0
}


# ════════════════════════════════════════════════════════════════════════════
#  CGS helpers
# ════════════════════════════════════════════════════════════════════════════

def _alpha_of(engine: FrozenCanonicalV4) -> float:
    return float(getattr(engine, "alpha_base_", getattr(engine, "alpha_base", 0.05)))


def build_cgs_fns(engine: FrozenCanonicalV4):
    mu, sigma, G = engine.mu_, engine.sigma_, engine.G_
    alpha, theta = _alpha_of(engine), float(engine.theta_)
    J_const = np.eye(len(sigma))

    def S_fn(X):     return (np.asarray(X, dtype=float) - mu) / sigma
    def J_fn(X):     return J_const
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
    """κ = 2·λ_max(G), β* = clip(SNR(κ_norm_ref), 0, 1)  [§67.5, §67.7]"""
    G      = engine.G_
    kappa  = 2.0 * float(np.linalg.eigvalsh(G)[-1])
    Z_ref  = (np.asarray(X_ref, dtype=float) - engine.mu_[None, :]) / engine.sigma_[None, :]
    GS     = Z_ref @ G
    E_ref  = np.einsum("ij,ij->i", Z_ref, GS)
    gsq    = 4.0 * np.einsum("ij,ij->i", GS, GS)
    kn     = kappa * E_ref / (gsq + EPS)
    snr    = float(np.std(kn)) / (float(np.mean(kn)) + EPS)
    beta   = float(np.clip(snr, 0.0, 1.0))
    return kappa, beta


# ════════════════════════════════════════════════════════════════════════════
#  State-series extraction (4 tiers)
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

    else:  # cgs1 / cgs1_stoch
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
    d = G.shape[0]
    try:
        return np.linalg.cholesky(G + 1e-10 * np.eye(d))
    except np.linalg.LinAlgError:
        lam, V = np.linalg.eigh(G)
        return V @ np.diag(np.sqrt(np.maximum(lam, 1e-10)))


def build_g_metric_knn(X: np.ndarray, G: np.ndarray, k: int):
    L     = _g_cholesky(G)
    XL    = X @ L
    k_eff = min(k + 1, len(X))
    tree  = cKDTree(XL)
    dists_raw, idx_raw = tree.query(XL, k=k_eff)
    return XL, dists_raw[:, 1:], idx_raw[:, 1:]


def compute_ollivier_ricci(XL: np.ndarray, dists: np.ndarray,
                            idx: np.ndarray) -> np.ndarray:
    """κ_OR(t,s) = 1 − W₁(μ_t, μ_s) / d_G(t,s); W₁ via 1D sliced projection."""
    T, k = dists.shape
    kappa = np.zeros(T)
    for t in range(T):
        nbrs_t = idx[t]
        pts_t  = XL[nbrs_t]
        kt     = []
        for i, s in enumerate(nbrs_t):
            d_ts = float(dists[t, i])
            if d_ts < EPS:
                continue
            v_unit = (XL[s] - XL[t]) / d_ts
            pts_s  = XL[idx[s]]
            proj_t = pts_t @ v_unit
            proj_s = pts_s @ v_unit
            w1     = float(np.mean(np.abs(np.sort(proj_t) - np.sort(proj_s))))
            kt.append(1.0 - w1 / d_ts)
        kappa[t] = float(np.mean(kt)) if kt else 0.0
    return kappa


def compute_forman_ricci(XL: np.ndarray, dists: np.ndarray,
                          idx: np.ndarray) -> np.ndarray:
    """Per-vertex Forman-Ricci on the G-metric k-NN graph."""
    T, k    = dists.shape
    sigma2  = float(np.median(dists) ** 2) + EPS
    W       = np.exp(-dists ** 2 / sigma2)
    vstr    = W.sum(axis=1)
    sqrtW   = np.sqrt(W)
    sum_sqW = sqrtW.sum(axis=1)
    forman  = np.zeros(T)
    for t in range(T):
        nbrs  = idx[t]
        sq_t  = sqrtW[t]
        ss_t  = float(sum_sqW[t])
        wv_t  = float(vstr[t])
        wv_s  = vstr[nbrs]
        tri_t = sq_t * (ss_t - sq_t)
        tri_s = np.zeros(k)
        for i, s in enumerate(nbrs):
            pos      = np.where(idx[s] == t)[0]
            sq_back  = float(sqrtW[s, pos[0]]) if pos.size > 0 else 0.0
            tri_s[i] = sq_t[i] * (float(sum_sqW[s]) - sq_back)
        forman[t] = float(np.mean(wv_t + wv_s - tri_t - tri_s))
    return forman


def compute_bishop_gromov(dists: np.ndarray, d_eff: int) -> np.ndarray:
    """BG(t) = (r_k / r_1) / k^{1/d}; > 1 ↔ Ric < 0 (faster ball growth)."""
    k    = dists.shape[1]
    r1   = dists[:, 0]  + EPS
    rk   = dists[:, -1] + EPS
    flat = float(k ** (1.0 / max(d_eff, 1)))
    return rk / (r1 * flat)


def compute_forman_betti_transitions(forman: np.ndarray,
                                      nn_idx: np.ndarray,
                                      tau_persist: float | None = None) -> np.ndarray:
    """0-dim persistent homology via sublevel filtration on vertex Forman curvature.

    Vertices are added in ascending Forman order (most-negative first = bottleneck
    regime first).  When a newly added vertex merges two components, a β₀ death
    occurs with persistence:

        persist = Forman(merge_vertex) − Forman(birth_of_dying_component)

    Only deaths with persistence ≥ tau_persist are marked as events.  This
    eliminates the trivial saturation from a dense k-NN graph (k=10 in d=5).

    tau_persist defaults to std(Forman) — the 1-sigma scale of curvature
    variation, providing a data-adaptive threshold.

    Returns: boolean array (T,) — True at merge vertices with high persistence.
    """
    T      = len(forman)
    parent = np.arange(T, dtype=int)
    # birth_forman[r] = Forman value when component rooted at r was created.
    # Initialized to forman[v] for each vertex (each starts its own component).
    birth_f = forman.copy()

    if tau_persist is None:
        tau_persist = max(float(np.std(forman)), EPS)

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union_with_persist(a: int, b: int, f_v: float) -> tuple[bool, float]:
        """Merge components of a and b.  Returns (merged, persistence).
        Elder component (lower birth Forman) absorbs younger component.
        Persistence = f_v - birth of dying (younger) component.
        """
        ra, rb = find(a), find(b)
        if ra == rb:
            return False, 0.0
        ba, bb = birth_f[ra], birth_f[rb]
        # Younger component (higher birth Forman) dies;
        # persistence is measured from its birth to the current merge.
        if ba <= bb:
            # ra is older; rb dies
            persist = f_v - bb
            parent[rb] = ra
        else:
            # rb is older; ra dies
            persist = f_v - ba
            parent[ra] = rb
        # Elder root's birth_f unchanged (it was born earlier)
        return True, max(persist, 0.0)

    order  = np.argsort(forman)    # ascending: most-negative first
    added  = np.zeros(T, dtype=bool)
    events = np.zeros(T, dtype=bool)

    for v in order:
        added[v] = True
        f_v = float(forman[v])
        for s in nn_idx[v]:
            if added[s]:
                merged, persist = union_with_persist(v, s, f_v)
                if merged and persist >= tau_persist:
                    events[v] = True   # mark the merge vertex (pinch point)

    return events


def compute_all_ricci(X: np.ndarray, G: np.ndarray, k: int = K_RICCI) -> dict:
    """Compute Ollivier-Ricci, Forman-Ricci, BG, and Forman-Betti for trajectory X."""
    T, d  = X.shape
    k_use = min(k, T - 1)
    t0    = time.time()
    print(f"    [ricci] k-NN (T={T}, d={d}, k={k_use}) ", end="", flush=True)

    XL, dists, nn_idx = build_g_metric_knn(X, G, k_use)
    print(f"kNN:{time.time()-t0:.1f}s ", end="", flush=True)

    ro = compute_ollivier_ricci(XL, dists, nn_idx)
    print(f"Olliv:{time.time()-t0:.1f}s ", end="", flush=True)

    rf = compute_forman_ricci(XL, dists, nn_idx)
    print(f"Forman:{time.time()-t0:.1f}s ", end="", flush=True)

    bg    = compute_bishop_gromov(dists, d_eff=d)
    betti = compute_forman_betti_transitions(rf, nn_idx)
    print(f"Betti+BG:{time.time()-t0:.1f}s")

    n_betti = int(betti.sum())
    print(f"    [ricci] Olliv={ro.mean():+.4f}±{ro.std():.4f}  "
          f"Forman={rf.mean():+.4f}±{rf.std():.4f}  "
          f"BG={bg.mean():.4f}±{bg.std():.4f}  "
          f"Betti_events={n_betti}/{T} ({100*n_betti/T:.1f}%)")

    return dict(ricci_ollivier=ro, ricci_forman=rf, ricci_bg=bg,
                betti_forman=betti, nn_idx=nn_idx)


# ════════════════════════════════════════════════════════════════════════════
#  C6 FIX: normalized Kramers hazard with direction-aware barrier
# ════════════════════════════════════════════════════════════════════════════

def kramers_hazard(E: np.ndarray, Edot: np.ndarray,
                   crisis_mask: np.ndarray, W: float) -> np.ndarray:
    """Kramers barrier-crossing probability with z-scored E.

    Fixes the EEG degeneration (e_star = 16M):
    - E is z-scored by quiescent statistics so sigma_n ≈ O(1)
    - e_star = ±2 standard deviations, placed on the CRISIS SIDE of the
      quiescent mean (direction-aware: above if crisis E > quiescent, below
      if crisis E < quiescent).

    This ensures h(t) rises pre-onset regardless of the direction of E change.
    """
    q = ~np.asarray(crisis_mask, dtype=bool)
    c = np.asarray(crisis_mask, dtype=bool)
    T = len(E)

    # Quiescent statistics for normalization
    if q.sum() > 1:
        E_q_mean = float(np.mean(E[q]))
        E_q_std  = max(float(np.std(E[q])), EPS)
    else:
        E_q_mean = float(np.mean(E))
        E_q_std  = max(float(np.std(E)), EPS)

    # Z-score E and Edot
    E_norm    = (E - E_q_mean) / E_q_std
    Edot_norm = Edot / E_q_std

    # Direction-aware barrier: crisis side of quiescent mean
    E_c_mean = float(np.mean(E[c])) if c.sum() > 0 else E_q_mean + E_q_std
    direction = float(np.sign(E_c_mean - E_q_mean))
    if direction == 0.0:
        direction = 1.0
    e_star = direction * 2.0    # ±2 std; quiescent mean = 0 after z-score

    # Use spread of E_norm (≈1 after z-scoring) rather than step-to-step noise
    # std(diff(E_norm)) ≈ 1e-4 on smooth signals (e.g. EEG) → barrier/σ² → ∞ → h≡0
    sigma_n = max(float(np.std(E_norm)), EPS)
    tau_h   = float(max(1.0, W))

    h     = np.zeros(T)
    order = np.argsort(E_norm)
    Es    = E_norm[order]
    Eds   = Edot_norm[order]
    if np.ptp(Es) < EPS:
        return h

    slope_sorted  = np.gradient(Eds, Es + np.linspace(0, EPS, T))
    dmu           = np.empty(T)
    dmu[order]    = slope_sorted
    mu_star_slope = float(np.interp(e_star, Es, slope_sorted))
    s2 = max(sigma_n ** 2, 1e-12)

    for t in range(T):
        e_t = float(E_norm[t])
        # If already past the barrier on the crisis side → crossing probability = 1
        if direction > 0 and e_star <= e_t:
            h[t] = 1.0
            continue
        if direction < 0 and e_star >= e_t:
            h[t] = 1.0
            continue
        barrier     = abs(e_star - e_t)
        denom       = np.sqrt(abs(dmu[t]) * abs(mu_star_slope)) + 1e-12
        log_barrier = min(2.0 * barrier / s2, 700.0)
        tau_K       = (2.0 * np.pi / denom) * np.exp(log_barrier)
        h[t]        = 1.0 - np.exp(-tau_h / max(tau_K, 1e-12))

    return h


# ════════════════════════════════════════════════════════════════════════════
#  Standard dynamical instruments
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
    T    = len(boolean)
    pre  = _pre_onset_mask(onsets, W, T)
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


# ════════════════════════════════════════════════════════════════════════════
#  Per-engine evaluation
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

    # ── C2 (redefined): Edot acceleration drift ──────────────────────────────
    # d(Edot)/dt < 0 pre-onset = energy dissipation accelerates toward collapse
    Edot_accel = np.concatenate([[0.0], np.diff(s["Edot"])])  # (T,)

    # C2 + C4 — Edot_accel / cos_theta / gamma / rho_eff, Bonferroni×4
    geom_keys = ["Edot_accel", "cos_theta", "gamma", "rho_eff"]
    signals   = dict(Edot_accel=Edot_accel,
                     cos_theta=s["cos_theta"],
                     gamma=s["gamma"],
                     rho_eff=s["rho_eff"])
    for key in geom_keys:
        sig    = signals[key]
        d      = _drift_stat(sig, onsets, W)
        p      = event_shuffle_p(sig, onsets, W, _drift_stat, d)
        p_bonf = min(1.0, p * BONFERRONI_MAIN) if np.isfinite(p) else float("nan")
        row[f"drift_{key}"]  = d
        row[f"p_{key}"]      = p
        row[f"pbonf_{key}"]  = p_bonf
        pod = per_onset_drift(sig, onsets, W)
        row[f"poFrac_{key}"] = pod["frac_pos"]
        pred = PREDICTED_SIGN[key]
        row[f"match_{key}"]  = bool(np.isfinite(d) and np.sign(d) == pred
                                    and np.isfinite(p_bonf) and p_bonf < 0.05)

    # ── C3b — disjunction OR-precursor (updated: Edot_accel < 0 | cos rising) ──
    # C3 AND is retired; C3b uses the improved C2 signal
    accel_event = (Edot_accel < 0)
    cos_rise    = np.concatenate([[False], np.diff(s["cos_theta"]) > 0]) if T > 1 else np.zeros(T, bool)
    p_disj = (accel_event | cos_rise).astype(float)
    rd = _rate_ratio(p_disj, onsets, W)
    row["disj_conc_ratio"]  = rd
    row["p_disj"]           = event_shuffle_p(p_disj, onsets, W, _rate_ratio, rd)
    row["disj_global_rate"] = float(p_disj.mean())
    row["disj_lead"]        = precursor_lead((accel_event | cos_rise), onsets, W)

    # ── C5 (rebuilt): Forman sublevel Betti β₀ deaths ──────────────────────
    # 0-dim persistent homology on the Ricci k-NN graph; domain-level, same
    # for all tiers.  Replaces TSB Morse proxy.
    if ricci is not None and "betti_forman" in ricci:
        bt = ricci["betti_forman"].astype(float)
        rb = _rate_ratio(bt, onsets, W)
        row["betti_conc_ratio"]  = rb
        row["p_betti"]           = event_shuffle_p(bt, onsets, W, _rate_ratio, rb)
        row["betti_global_rate"] = float(bt.mean())
        row["betti_peak"]        = int(bt.sum())
        row["betti_lead"]        = precursor_lead(ricci["betti_forman"], onsets, W)

    # ── C6 (fixed): normalized Kramers — cgs1_stoch and cgs1_curv ──────────
    if tier in ("cgs1_stoch", "cgs1_curv"):
        h_t = kramers_hazard(s["E"], s["Edot"], crisis_mask, float(W))
        dh  = _drift_stat(h_t, onsets, W)
        row["kramers_drift"]       = dh
        row["p_kramers"]           = event_shuffle_p(h_t, onsets, W, _drift_stat, dh)
        row["kramers_global_mean"] = float(np.mean(h_t))
        # Diagnostic: record normalized e_star
        q = ~crisis_mask
        c = crisis_mask
        E_q_mean = float(np.mean(s["E"][q])) if q.sum() > 0 else float(np.mean(s["E"]))
        E_q_std  = max(float(np.std(s["E"][q])), EPS)
        E_c_mean = float(np.mean(s["E"][c])) if c.sum() > 0 else E_q_mean + E_q_std
        direction = float(np.sign(E_c_mean - E_q_mean)) or 1.0
        row["e_star_norm"]  = float(direction * 2.0)
        row["E_q_mean"]     = E_q_mean
        row["E_q_std"]      = E_q_std

    # ── C7: κ_norm drift (cgs1_curv only) ──────────────────────────────────
    if tier == "cgs1_curv" and "kappa_norm" in s:
        kn  = s["kappa_norm"]
        dkn = _drift_stat(kn, onsets, W)
        pkn = event_shuffle_p(kn, onsets, W, _drift_stat, dkn)
        row["kappa_norm_drift"] = dkn
        row["p_kappa_norm"]     = pkn
        row["match_kappa_norm"] = bool(np.isfinite(dkn) and np.sign(dkn) == +1.0
                                       and np.isfinite(pkn) and pkn < 0.05)

    # ── C8-C10: Ricci curvature — domain-level, same for all tiers ─────────
    if ricci is not None:
        for rkey, pred_sign in PREDICTED_SIGN_RICCI.items():
            rval = ricci.get(rkey)
            if rval is None:
                continue
            dr      = _drift_stat(rval, onsets, W)
            pr      = event_shuffle_p(rval, onsets, W, _drift_stat, dr)
            pr_bonf = min(1.0, pr * BONFERRONI_RICCI) if np.isfinite(pr) else float("nan")
            row[f"drift_{rkey}"]  = dr
            row[f"p_{rkey}"]      = pr
            row[f"pbonf_{rkey}"]  = pr_bonf
            row[f"match_{rkey}"]  = bool(
                np.isfinite(dr) and np.sign(dr) == pred_sign
                and np.isfinite(pr_bonf) and pr_bonf < 0.05)
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


def run_all_tiers_v2(X_ref, X, crisis_mask, label, W) -> list[dict]:
    """Fit engine, compute Ricci+Betti once, then evaluate all 4 tiers."""
    ref_engine = FrozenCanonicalV4(alpha_base=0.05)
    ref_engine.fit(X_ref)
    TSB.apply_g7_to_engine(ref_engine, G7_KAPPA_MAX)
    ricci = compute_all_ricci(X, ref_engine.G_, k=K_RICCI)

    rows = []
    for tier in TIERS:
        engine = FrozenCanonicalV4(alpha_base=0.05)
        engine.fit(X_ref)
        lam_g7 = TSB.apply_g7_to_engine(engine, G7_KAPPA_MAX)
        kappa, beta_c = compute_curv_params(engine, X_ref) if tier == "cgs1_curv" else (0.0, 0.0)
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
    return run_all_tiers_v2(X_ref, Xagg, crisis, "banks", W=4)


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
        rows += run_all_tiers_v2(X_ref, X, crisis, f"protein:{pdb_id}", W=5)
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
    return run_all_tiers_v2(X_ref, X_eeg, crisis, "eeg", W=64)


# ════════════════════════════════════════════════════════════════════════════
#  Reporting
# ════════════════════════════════════════════════════════════════════════════

def _sig(val, p, fmt="{:+.3f}"):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "   -   "
    star = "*" if (isinstance(p, float) and np.isfinite(p) and p < 0.05) else " "
    return fmt.format(val) + star


def print_report(rows: list[dict]) -> None:
    W_TOT = 162
    print("\n" + "=" * W_TOT)
    print("DYNAMICAL + RICCI VALIDATION v2  "
          "( * p<0.05 ; C2/C4: Bonferroni×4 ; C8-C10: Bonferroni×3 )")
    print("CHANGES: C2=Edot_accel(redef) | C3AND=retired | C5=Forman_Betti(rebuilt) | C6=normalized")
    print("=" * W_TOT)
    hdr = (f"{'domain':<14}{'engine':<12}{'n_on':>4}{'descF':>7}"
           f"{'dAccel':>9}{'dCos':>9}{'dgam':>9}{'drho':>9}"
           f"{'C4ok':>5}{'Disj':>7}{'Betti':>8}{'Kram':>10}"
           f"{'dKn':>8}{'dOlliv':>9}{'dForman':>9}{'dBG':>8}")
    print(hdr)
    print("-" * W_TOT)
    last = None
    for r in rows:
        if last is not None and r["domain"] != last:
            print("-" * W_TOT)
        last = r["domain"]
        c4ok = sum(int(bool(r.get(f"match_{k}")))
                   for k in ("Edot_accel", "cos_theta", "gamma", "rho_eff"))
        print(
            f"{r['domain']:<14}{r['engine']:<12}{r['n_onsets']:>4}"
            f"{_sig(r.get('desc_frac'), None, '{:.3f}'):>7}"
            f"{_sig(r.get('drift_Edot_accel'),    r.get('pbonf_Edot_accel')):>9}"
            f"{_sig(r.get('drift_cos_theta'),      r.get('pbonf_cos_theta')):>9}"
            f"{_sig(r.get('drift_gamma'),          r.get('pbonf_gamma')):>9}"
            f"{_sig(r.get('drift_rho_eff'),        r.get('pbonf_rho_eff')):>9}"
            f"{c4ok:>5}"
            f"{_sig(r.get('disj_conc_ratio'),      r.get('p_disj'),   '{:.2f}'):>7}"
            f"{_sig(r.get('betti_conc_ratio'),     r.get('p_betti'),  '{:.2f}'):>8}"
            f"{_sig(r.get('kramers_drift'),        r.get('p_kramers'),'{:+.2e}'):>10}"
            f"{_sig(r.get('kappa_norm_drift'),     r.get('p_kappa_norm'),'{:+.3f}'):>8}"
            f"{_sig(r.get('drift_ricci_ollivier'), r.get('pbonf_ricci_ollivier'),'{:+.4f}'):>9}"
            f"{_sig(r.get('drift_ricci_forman'),   r.get('pbonf_ricci_forman'),  '{:+.4f}'):>9}"
            f"{_sig(r.get('drift_ricci_bg'),       r.get('pbonf_ricci_bg'),      '{:+.4f}'):>8}"
        )
    print("=" * W_TOT)
    print("dAccel: d(Edot)/dt drift pre-onset          (C2 NEW, predict <0)")
    print("dCos/dgam/drho: geometry drift               (C4, predict +/+/-)")
    print("C4ok  : # signals correctly signed AND Bonf-significant (now includes dAccel)")
    print("Disj  : [Edot_accel<0 | cos rise] rate-ratio (C3b updated)")
    print("Betti : Forman sublevel β₀ death rate-ratio  (C5 REBUILT from Ricci graph)")
    print("Kram  : normalized Kramers hazard drift       (C6 FIXED: e_star=±2σ direction-aware)")
    print("dKn   : κ_norm drift (cgs1_curv only)         (C7)")
    print("dOlliv/dForman/dBG: Ricci manifold curvature  (C8-C10, Bonferroni×3)")
    print("=" * W_TOT)

    # ── Confirmed precursors ──────────────────────────────────────────────
    print("\nCONFIRMED C1-C7 PRECURSORS (Bonferroni-significant, theory-signed):")
    any_conf = False
    for r in rows:
        hits = [k for k in ("Edot_accel", "cos_theta", "gamma", "rho_eff")
                if r.get(f"match_{k}")]
        if r.get("match_kappa_norm"):
            hits.append("kappa_norm")
        if hits:
            any_conf = True
            parts = []
            for k in hits:
                if k == "kappa_norm":
                    parts.append(f"kappa_norm={r.get('kappa_norm_drift', float('nan')):+.3f}")
                else:
                    parts.append(f"{k}={r['drift_'+k]:+.4f}(f+={r.get('poFrac_'+k, float('nan')):.2f})")
            print(f"  {r['domain']:<14} {r['engine']:<12} n={r['n_onsets']:<3} → {', '.join(parts)}")
    if not any_conf:
        print("  (none)")

    # ── C5 Betti summary ─────────────────────────────────────────────────
    print("\nC5 FORMAN BETTI TRANSITIONS (domain-level, same all tiers):")
    seen = set()
    for r in rows:
        dom = r["domain"]
        if dom in seen:
            continue
        seen.add(dom)
        br   = r.get("betti_conc_ratio", float("nan"))
        pb   = r.get("p_betti", float("nan"))
        rate = r.get("betti_global_rate", float("nan"))
        sig  = "*" if (np.isfinite(pb) and pb < 0.05) else " "
        print(f"  {dom:<14} ratio={br:+.3f}{sig}  p={pb:.4f}  global_rate={rate:.3f}"
              f"  n_events={r.get('betti_peak','?')}")

    # ── C6 Kramers fix diagnostics ────────────────────────────────────────
    print("\nC6 KRAMERS NORMALIZATION CHECK (e_star should be ±2, not ±16M):")
    for r in rows:
        if r.get("e_star_norm") is None:
            continue
        kd  = r.get("kramers_drift", float("nan"))
        pk  = r.get("p_kramers",     float("nan"))
        sig = "*" if (np.isfinite(pk) and pk < 0.05) else " "
        print(f"  {r['domain']:<14} {r['engine']:<12} "
              f"e_star_norm={r['e_star_norm']:+.1f}  "
              f"E_q_mean={r.get('E_q_mean', float('nan')):.2e}  "
              f"E_q_std={r.get('E_q_std', float('nan')):.2e}  "
              f"drift={kd:+.4f}{sig}  p={pk:.4f}")

    # ── Ricci collapse corridors ──────────────────────────────────────────
    print("\nCONFIRMED RICCI COLLAPSE CORRIDORS (C8-C10, Bonferroni×3):")
    any_ricci = False
    seen = set()
    for r in rows:
        dom = r["domain"]
        if dom in seen:
            continue
        hits = [k for k in PREDICTED_SIGN_RICCI if r.get(f"match_{k}")]
        if hits:
            any_ricci = True
            seen.add(dom)
            parts = [f"{k}={r.get('drift_'+k, float('nan')):+.4f}"
                     f"(mean={r.get(k+'_global_mean', float('nan')):.4f})"
                     for k in hits]
            print(f"  {dom:<14} n_on={r['n_onsets']:<3} → {', '.join(parts)}")
    if not any_ricci:
        print("  (none)")

    print("=" * W_TOT + "\n")


def main() -> None:
    t0 = time.time()
    print("=" * 100)
    print("DYNAMICAL + RICCI VALIDATION v3")
    print("Fixes: C5=persistence_filter | C6=sigma_n=std(E_norm)")
    print("Tiers: v4 / cgs1 / cgs1_stoch / cgs1_curv  ×  banks / eeg / protein")
    print("=" * 100)
    rows: list[dict] = []
    rows += domain_banks()
    rows += domain_eeg()
    rows += domain_protein()
    if not rows:
        print("No domains produced results.")
        return
    print_report(rows)
    out_path = os.path.join(ROOT, "benchmark_v3_results.json")
    payload  = {
        "generated":    time.strftime("%Y-%m-%d %H:%M:%S"),
        "version":      "v3",
        "engine_tiers": TIERS,
        "n_shuffle":    N_SHUFFLE,
        "k_ricci":      K_RICCI,
        "g7_kappa_max": G7_KAPPA_MAX,
        "changes_from_v2": {
            "C5":  "persistence filter: tau=std(Forman); eliminates trivial saturation",
            "C6":  "sigma_n=std(E_norm) instead of std(diff(E_norm)); fixes EEG h≡0",
        },
        "changes_from_v1": {
            "C2":        "Edot_accel = d(Edot)/dt; predict<0; replaces raw Edot drift",
            "C3":        "THREE-PHASE AND RETIRED",
            "C5":        "Forman sublevel β₀ persistent homology; replaces TSB Morse proxy",
            "C6":        "E z-scored by quiescent stats; e_star=±2σ direction-aware",
            "cgs1_morse": "RETIRED (C5 now runs on Ricci graph for all tiers)",
        },
        "predicted_signs": {**PREDICTED_SIGN, **PREDICTED_SIGN_RICCI,
                            "kappa_norm": +1.0},
        "claims": {
            "C1":  "Lyapunov descent: Edot<0 during quiescence",
            "C2":  "Edot_accel = d(Edot)/dt drifts < 0 pre-onset (dissipation accelerates)",
            "C3b": "[Edot_accel<0 | cos_theta rising] rate-ratio > 1 pre-onset",
            "C4":  "Geometry drift cos+/gamma+/rho- pre-onset",
            "C5":  "Forman sublevel β₀ deaths concentrate pre-onset",
            "C6":  "Normalized Kramers crossing-hazard rises pre-onset",
            "C7":  "κ_norm drift pre-onset (cgs1_curv only)",
            "C8":  "Ollivier-Ricci drift < 0 pre-onset",
            "C9":  "Forman-Ricci drift < 0 pre-onset",
            "C10": "Bishop-Gromov ratio drift > 0 pre-onset",
        },
        "results": rows,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Saved {len(rows)} rows → {out_path}")
    print(f"Elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
