"""
gravity_engine_newtonian.py  (extended pipeline version)
=========================================================
Copy of gravity_engine.py + **real Newtonian gravitational interaction**.

The original engine uses:
  - Radial anchoring:  F_rad = α(μ − xᵢ)           [harmonic spring]
  - Pairwise molecular: erf attraction + log repulsion [short/medium range]

This version adds a third force layer:
  - Newtonian gravity:  F_grav = −G mᵢ mⱼ r̂ / r²    [long-range 1/r²]

with corresponding potential:
  - Φ_grav = −Σᵢ<ⱼ G mᵢ mⱼ / rᵢⱼ

The three regimes create multi-scale dynamics:
  ┌──────────────┬──────────────┬──────────────────────────────┐
  │  Range       │  Dominant    │  Physical role               │
  ├──────────────┼──────────────┼──────────────────────────────┤
  │  r → 0       │  Repulsion   │  Core exclusion (log 1/r)    │
  │  r ~ σ       │  Molecular   │  Local clustering (erf att.) │
  │  r → ∞       │  Gravity     │  Hierarchical structure      │
  └──────────────┴──────────────┴──────────────────────────────┘

Parameters
----------
G_NEWTON : float
    Gravitational constant.  Set to 1.0 by default (natural units).
    Scale this to control the relative strength of gravity vs molecular.
MASS_DEFAULT : float
    Default mass for all particles when no mass array is supplied.

Author: Odeyemi Olusegun Israel
"""

from __future__ import annotations
import numpy as np
from scipy.special import erf as _erf


# ─────────────────────────────────────────────────────────────────────────────
# Parameters  (match paper Appendix B table + new gravitational parameters)
# ─────────────────────────────────────────────────────────────────────────────

# --- Original molecular parameters ---
ALPHA      = 0.10    # radial spring
GAMMA      = 1.00    # pairwise coupling baseline
SIGMA      = 1.00    # attraction length-scale
LAMBDA_REP = 0.10    # repulsion coefficient
EPS        = 1e-5    # softening (shared with gravity)
F_MAX      = 100.0   # force clamp

# --- New gravitational parameters ---
G_NEWTON     = 1.0   # gravitational constant (natural units)
MASS_DEFAULT = 1.0   # default particle mass
GRAV_SOFT    = 0.01  # gravitational softening length (prevents 1/r² blowup)
MIX_GRAV     = 1.0   # mixing coefficient: total = molecular + MIX_GRAV * gravity


# ─────────────────────────────────────────────────────────────────────────────
# Data-derived mass computation — NO heuristics
# ─────────────────────────────────────────────────────────────────────────────

def compute_masses_from_data(X_series: np.ndarray, method: str = "influence") -> np.ndarray:
    """
    Compute particle masses purely from the data.  No hand-tuning.

    Three data-driven methods, all producing (N,) mass arrays:

    1. "influence" (default)  —  Gravitational mass ∝ influence on others.
       m_i = Σⱼ |Corr(xᵢ, xⱼ)|  averaged over time.
       Sectors that co-move with many others are "heavier" — they pull
       the system.  This is the data's own answer to "systemic importance".

    2. "energy"  —  Mass ∝ mean kinetic energy (displacement from equilibrium).
       m_i = ⟨‖xᵢ(t) − μ‖²⟩_t
       Sectors that fluctuate more carry more energy → more massive.
       This mirrors E = ½mv² from classical mechanics.

    3. "variance"  —  Mass ∝ total variance explained.
       m_i = Tr(Cov(xᵢ))
       Sectors with larger feature-space footprint are heavier.

    All methods normalise so that Σ mᵢ = N (mean mass = 1).

    Parameters
    ----------
    X_series : (T, N, d) trajectory array
    method   : "influence", "energy", or "variance"

    Returns
    -------
    masses : (N,) array, normalised so mean = 1
    """
    T, N, d = X_series.shape

    if method == "influence":
        # Flatten each sector's trajectory to (T*d,) then compute
        # cross-correlation magnitude summed over all other sectors.
        # This measures how much sector i drives/follows the system.
        flat = X_series.reshape(T, N * d)  # (T, N*d)
        # Per-sector block: columns [i*d : (i+1)*d]
        # Cross-sector absolute correlation
        masses = np.zeros(N)
        for i in range(N):
            xi = X_series[:, i, :]  # (T, d)
            for j in range(N):
                if i == j:
                    continue
                xj = X_series[:, j, :]  # (T, d)
                # Mean absolute cross-correlation across feature pairs
                for fi in range(d):
                    for fj in range(d):
                        c = np.corrcoef(xi[:, fi], xj[:, fj])[0, 1]
                        if np.isfinite(c):
                            masses[i] += abs(c)
        # Normalise: each sector compared d*d feature pairs × (N-1) sectors
        masses /= (d * d * (N - 1) + 1e-12)

    elif method == "energy":
        # Mass = time-averaged displacement energy from global mean
        mu = X_series.mean(axis=(0, 1))  # (d,) global equilibrium
        # ⟨‖xᵢ(t) − μ‖²⟩_t  for each sector i
        diff = X_series - mu[None, None, :]  # (T, N, d)
        masses = np.mean(np.sum(diff ** 2, axis=2), axis=0)  # (N,)

    elif method == "variance":
        # Mass = trace of per-sector covariance  Tr(Cov(xᵢ))
        masses = np.zeros(N)
        for i in range(N):
            xi = X_series[:, i, :]  # (T, d)
            cov_i = np.cov(xi.T)    # (d, d)
            masses[i] = np.trace(cov_i)

    else:
        raise ValueError(f"Unknown mass method: {method!r}")

    # Normalise so mean mass = 1 (total mass = N)
    masses = N * masses / (masses.sum() + 1e-12)
    return masses


def compute_G_from_data(X_series: np.ndarray, masses: np.ndarray,
                        alpha: float = ALPHA) -> float:
    """
    Compute the gravitational constant G from the data's own scales.
    No hand-tuning.

    Principle: G should be set so that the gravitational force is a
    fixed fraction of the molecular force at the system's characteristic
    inter-particle distance.  Specifically:

        G = α · ⟨r⟩² / ⟨mᵢ mⱼ⟩

    where ⟨r⟩ is the mean inter-particle distance and ⟨mᵢmⱼ⟩ is the
    mean mass product.  This ensures:
        F_grav(⟨r⟩) ≈ α   (same order as the radial spring)

    The ratio F_grav / F_molecular is then determined entirely by
    the geometry and mass distribution of the data.
    """
    T, N, d = X_series.shape

    # Mean inter-particle distance over the trajectory
    mean_r = 0.0
    count = 0
    for t in range(0, T, max(1, T // 20)):  # sample ~20 timesteps
        X = X_series[t]
        diff = X[:, None, :] - X[None, :, :]
        dist = np.sqrt(np.sum(diff ** 2, axis=2))
        # Upper triangle (exclude diagonal)
        triu_idx = np.triu_indices(N, k=1)
        mean_r += dist[triu_idx].mean()
        count += 1
    mean_r /= count

    # Mean mass product
    mass_prod = masses[:, None] * masses[None, :]
    mean_mm = mass_prod[np.triu_indices(N, k=1)].mean()

    # G such that F_grav(⟨r⟩) = G ⟨mm⟩ / ⟨r⟩² ≈ α
    G = alpha * mean_r ** 2 / (mean_mm + 1e-12)
    return float(G)


# ─────────────────────────────────────────────────────────────────────────────
# Potential energy — original molecular terms
# ─────────────────────────────────────────────────────────────────────────────

def radial_energy(X: np.ndarray, mu: np.ndarray, alpha: float = ALPHA) -> float:
    """Φ_rad = (α/2) Σ ‖xᵢ − μ‖²"""
    diff = X - mu[None, :]
    return 0.5 * alpha * float(np.sum(diff ** 2))


def pairwise_energy(X: np.ndarray, gamma: float = GAMMA,
                    sigma: float = SIGMA, lam: float = LAMBDA_REP,
                    eps: float = EPS) -> float:
    """Φ_pair = Σᵢ<ⱼ [γ·erf_potential − γλ·log(rᵢⱼ + ε)]"""
    N = X.shape[0]
    diff = X[:, None, :] - X[None, :, :]
    dist = np.linalg.norm(diff, axis=2)
    np.fill_diagonal(dist, eps)
    # Attraction (erf integral)
    E_att = 0.5 * gamma * (sigma * np.sqrt(np.pi) * 0.5) * np.sum(_erf(dist / sigma))
    # Repulsion
    E_rep = -0.5 * gamma * lam * np.sum(np.log(dist + eps))
    # Remove diagonal self-terms
    E_att -= N * gamma * (sigma * np.sqrt(np.pi) * 0.5) * _erf(0.0)
    E_rep += N * gamma * lam * np.log(eps)
    return float(E_att + E_rep)


# ─────────────────────────────────────────────────────────────────────────────
# Potential energy — NEW Newtonian gravitational term
# ─────────────────────────────────────────────────────────────────────────────

def newtonian_energy(X: np.ndarray,
                     masses: np.ndarray | None = None,
                     G: float = G_NEWTON,
                     soft: float = GRAV_SOFT) -> float:
    """
    Φ_grav = −Σᵢ<ⱼ G mᵢ mⱼ / √(rᵢⱼ² + ε²)

    Plummer softening:  Uses √(r² + ε²) instead of r to prevent the
    1/r singularity.  This is the standard approach in N-body astrophysics
    (Aarseth 2003, Dehnen & Read 2011).

    Parameters
    ----------
    X      : (N, d) position array
    masses : (N,) mass array, defaults to MASS_DEFAULT for all particles
    G      : gravitational constant
    soft   : Plummer softening length
    """
    N = X.shape[0]
    if masses is None:
        masses = np.full(N, MASS_DEFAULT)

    diff = X[:, None, :] - X[None, :, :]         # (N, N, d)
    dist_sq = np.sum(diff ** 2, axis=2)           # (N, N)
    r_soft = np.sqrt(dist_sq + soft ** 2)         # (N, N) — Plummer softened

    # Mass product matrix
    mass_prod = masses[:, None] * masses[None, :]  # (N, N) = mᵢ mⱼ

    # Upper triangle only (avoid double counting)
    E = -G * np.sum(np.triu(mass_prod / r_soft, k=1))
    return float(E)


def newtonian_force(X: np.ndarray,
                    masses: np.ndarray | None = None,
                    G: float = G_NEWTON,
                    soft: float = GRAV_SOFT) -> np.ndarray:
    """
    F_grav(i) = −Σⱼ≠ᵢ G mᵢ mⱼ (xᵢ − xⱼ) / (rᵢⱼ² + ε²)^{3/2}

    This is -∇ᵢ Φ_grav.  The force is purely attractive (particles pull
    each other).  Plummer softening makes the force finite at r → 0:
        F → G m₁ m₂ / ε²   (finite, not infinite)

    Returns
    -------
    F : (N, d) force array — force on each particle from all others
    """
    N, d = X.shape
    if masses is None:
        masses = np.full(N, MASS_DEFAULT)

    diff = X[:, None, :] - X[None, :, :]          # (N, N, d)  diff[i,j] = xᵢ − xⱼ
    dist_sq = np.sum(diff ** 2, axis=2)            # (N, N)
    r_soft_cubed = (dist_sq + soft ** 2) ** 1.5    # (N, N) — (r² + ε²)^{3/2}

    # Mass product and gravitational coupling
    mass_prod = masses[:, None] * masses[None, :]  # (N, N)
    np.fill_diagonal(mass_prod, 0.0)               # no self-force

    # F_i = −G Σⱼ mᵢ mⱼ (xᵢ − xⱼ) / (r² + ε²)^{3/2}
    # This points from i toward j (attractive), since −(xᵢ − xⱼ) = xⱼ − xᵢ
    coeff = -G * mass_prod / r_soft_cubed          # (N, N)
    np.fill_diagonal(coeff, 0.0)

    F = np.sum(coeff[:, :, None] * diff, axis=1)   # (N, d)
    return F


# ─────────────────────────────────────────────────────────────────────────────
# Combined energy & force (molecular + gravitational)
# ─────────────────────────────────────────────────────────────────────────────

def total_energy(X: np.ndarray, mu: np.ndarray,
                 masses: np.ndarray | None = None,
                 mix_grav: float = MIX_GRAV, **kw) -> float:
    """
    Φ_total = Φ_rad + Φ_pair + mix_grav · Φ_grav

    The mixing parameter controls relative importance:
      - mix_grav = 0:  original molecular engine (no gravity)
      - mix_grav = 1:  equal weight molecular + gravity
      - mix_grav >> 1: gravity-dominated (astrophysical regime)
    """
    E_mol = radial_energy(X, mu, kw.get("alpha", ALPHA)) + \
            pairwise_energy(X, kw.get("gamma", GAMMA),
                            kw.get("sigma", SIGMA),
                            kw.get("lam", LAMBDA_REP),
                            kw.get("eps", EPS))
    E_grav = newtonian_energy(X, masses,
                              kw.get("G", G_NEWTON),
                              kw.get("soft", GRAV_SOFT))
    return E_mol + mix_grav * E_grav


def total_force(X: np.ndarray, mu: np.ndarray,
                masses: np.ndarray | None = None,
                mix_grav: float = MIX_GRAV, **kw) -> np.ndarray:
    """
    F_total = F_rad + F_pair + mix_grav · F_grav

    Returns (N, d) force array, clamped to F_MAX per-particle.
    """
    F_mol = radial_force(X, mu, kw.get("alpha", ALPHA)) + \
            pairwise_force(X, kw.get("gamma", GAMMA),
                           kw.get("sigma", SIGMA),
                           kw.get("lam", LAMBDA_REP),
                           kw.get("eps", EPS))
    F_grav = newtonian_force(X, masses,
                             kw.get("G", G_NEWTON),
                             kw.get("soft", GRAV_SOFT))
    F = F_mol + mix_grav * F_grav

    # Force clamp (applied to combined force)
    norms = np.linalg.norm(F, axis=1, keepdims=True)
    scale = np.where(norms > F_MAX, F_MAX / (norms + 1e-12), 1.0)
    return F * scale


# ─────────────────────────────────────────────────────────────────────────────
# Gradient (force) — original molecular pairwise
# ─────────────────────────────────────────────────────────────────────────────

def radial_force(X: np.ndarray, mu: np.ndarray, alpha: float = ALPHA) -> np.ndarray:
    """-∇Φ_rad = α(μ − X)"""
    return alpha * (mu[None, :] - X)


def pairwise_force(X: np.ndarray, gamma: float = GAMMA, sigma: float = SIGMA,
                   lam: float = LAMBDA_REP, eps: float = EPS) -> np.ndarray:
    """-∇Φ_pair  shape (N, d)

    magnitude = −γ · (exp(−r²/σ²) − λ/r)
    force on i = magnitude_ij · unit_ij   summed over j
    """
    N, d = X.shape
    diff = X[:, None, :] - X[None, :, :]
    dist = np.linalg.norm(diff, axis=2)
    np.fill_diagonal(dist, eps)
    unit = diff / (dist[:, :, None] + eps)

    attraction = np.exp(-(dist ** 2) / (sigma ** 2))
    repulsion  = lam / (dist + eps)
    magnitude  = -gamma * (attraction - repulsion)
    np.fill_diagonal(magnitude, 0.0)

    F = np.sum(magnitude[:, :, None] * unit, axis=1)

    # Note: force clamp moved to total_force() so it applies to the combined force
    return F


# ─────────────────────────────────────────────────────────────────────────────
# Spectral radius via power iteration (Rayleigh quotient)
# ─────────────────────────────────────────────────────────────────────────────

def _hvp(X: np.ndarray, v: np.ndarray, h: float = 1e-4,
         masses: np.ndarray | None = None,
         mix_grav: float = MIX_GRAV, **kw) -> np.ndarray:
    """Finite-difference Hessian-vector product for combined Φ_pair + Φ_grav."""
    v_unit = v / (np.linalg.norm(v) + 1e-12)

    # Molecular pairwise
    Fp_mol = pairwise_force(X + h * v_unit, **kw)
    Fm_mol = pairwise_force(X - h * v_unit, **kw)
    Hv_mol = (Fm_mol - Fp_mol) / (2 * h)

    # Gravitational (if active)
    if mix_grav > 0:
        G = kw.get("G", G_NEWTON)
        soft = kw.get("soft", GRAV_SOFT)
        Fp_grav = newtonian_force(X + h * v_unit, masses, G, soft)
        Fm_grav = newtonian_force(X - h * v_unit, masses, G, soft)
        Hv_grav = (Fm_grav - Fp_grav) / (2 * h)
        return Hv_mol + mix_grav * Hv_grav
    return Hv_mol


def spectral_radius(X: np.ndarray, K: int = 20,
                    rng: np.random.Generator | None = None,
                    masses: np.ndarray | None = None,
                    mix_grav: float = MIX_GRAV,
                    **kw) -> tuple[float, np.ndarray]:
    """
    Estimate λ_max(D²Φ_combined(X)) via K steps of power iteration.
    Returns (λ_max, leading_eigenvector).
    """
    if rng is None:
        rng = np.random.default_rng(0)
    v = rng.standard_normal(X.shape)
    v /= np.linalg.norm(v) + 1e-12
    lam = 0.0
    for _ in range(K):
        Hv = _hvp(X, v, masses=masses, mix_grav=mix_grav, **kw)
        lam = float(np.sum(Hv * v))
        v = Hv / (np.linalg.norm(Hv) + 1e-12)
    return max(lam, 1e-6), v


# ─────────────────────────────────────────────────────────────────────────────
# BSDT blind-spot energy (for MFLS score and alignment verification)
# ─────────────────────────────────────────────────────────────────────────────

class BSDTOperator:
    """Fitted BSDT reference distribution; computes E_BS gradient."""

    def __init__(self):
        self.mu0_: np.ndarray | None = None
        self.Sigma0_inv_: np.ndarray | None = None

    def fit(self, X_normal: np.ndarray) -> "BSDTOperator":
        """Fit on normal-period data (T_normal, N, d) — reshape to (T*N, d)."""
        Xf = X_normal.reshape(-1, X_normal.shape[-1])
        self.mu0_ = Xf.mean(axis=0)
        cov = np.cov(Xf.T) + 1e-6 * np.eye(Xf.shape[1])
        self.Sigma0_inv_ = np.linalg.inv(cov)
        return self

    def deviation(self, X: np.ndarray) -> np.ndarray:
        """δ(X) = (xᵢ − μ₀)ᵀ Σ₀⁻¹ (xᵢ − μ₀)   shape (N,)"""
        z = X - self.mu0_
        return np.sum(z @ self.Sigma0_inv_ * z, axis=1)

    def energy_score(self, X: np.ndarray) -> float:
        """MFLS = Σᵢ δᵢ(X)"""
        return float(np.sum(self.deviation(X)))

    def gradient(self, X: np.ndarray) -> np.ndarray:
        """∇E_BS = 2 Σ₀⁻¹ (X − μ₀)   shape (N, d)"""
        z = X - self.mu0_
        return 2.0 * (z @ self.Sigma0_inv_.T)

    def mfls_score(self, X: np.ndarray) -> float:
        """‖∇E_BS(X)‖_F"""
        return float(np.linalg.norm(self.gradient(X)))


# ─────────────────────────────────────────────────────────────────────────────
# Main trajectory analysis (updated for gravity)
# ─────────────────────────────────────────────────────────────────────────────

def simulate_and_align(
    X0: np.ndarray,
    mu: np.ndarray,
    bsdt: "BSDTOperator",
    masses: np.ndarray | None = None,
    mix_grav: float = MIX_GRAV,
    n_steps: int = 100,
    eta: float = 0.02,
    alpha: float = ALPHA,
    **kw,
) -> dict[str, float]:
    """
    Run GravityEngine simulation from X0 with combined molecular + Newtonian
    forces, measuring gradient alignment at each step.
    """
    X = X0.copy()
    cos_history = []
    for _ in range(n_steps):
        mu_t = X.mean(axis=0)
        F     = total_force(X, mu_t, masses=masses, mix_grav=mix_grav, alpha=alpha, **kw)
        G_bs  = bsdt.gradient(X)
        dot_  = np.sum(G_bs * F, axis=1)
        nG    = np.linalg.norm(G_bs, axis=1)
        nF    = np.linalg.norm(F,    axis=1)
        cos_  = dot_ / (nG * nF + 1e-12)
        cos_history.append(float(np.mean(cos_)))
        X = X + eta * F
        if np.linalg.norm(eta * F) < 1e-6:
            break
    c = np.array(cos_history)
    return {
        "mean_cos":       float(c.mean()),
        "min_cos":        float(c.min()),
        "frac_above_07":  float((c >= 0.7).mean()),
        "n_steps_run":    len(c),
    }


def analyse_trajectory(
    X_series: np.ndarray,
    mu: np.ndarray,
    bsdt: BSDTOperator,
    masses: np.ndarray | None = None,
    mix_grav: float = MIX_GRAV,
    alpha: float = ALPHA,
    n_power_iter: int = 20,
    verbose: bool = False,
    **kw,
) -> dict[str, np.ndarray]:
    """
    Given a T-length series of state matrices X(t) ∈ ℝ^{N × d},
    compute per-step statistics with combined molecular + Newtonian dynamics.

    Additional returned keys (vs original):
        grav_energy   (T,) - Newtonian gravitational energy alone
        grav_force_norm (T,) - ‖F_grav‖_F at each step
    """
    T, N, d = X_series.shape
    rng = np.random.default_rng(42)

    energy          = np.zeros(T)
    grav_energy_arr = np.zeros(T)
    mfls            = np.zeros(T)
    lambda_max      = np.zeros(T)
    gamma_star      = np.zeros(T)
    above_cman      = np.zeros(T, dtype=bool)
    cos_theta       = np.zeros(T)
    force_norm      = np.zeros(T)
    grav_force_norm = np.zeros(T)

    _lam_cache = 1e-6

    for t in range(T):
        X = X_series[t]
        if verbose and t % 20 == 0:
            print(f"  t={t:3d}/{T}")

        mu_t = X.mean(axis=0)

        # Combined energy
        energy[t] = total_energy(X, mu, masses=masses, mix_grav=mix_grav, alpha=alpha, **kw)
        grav_energy_arr[t] = newtonian_energy(X, masses, G=kw.get('G', G_NEWTON))

        # Combined force
        F = total_force(X, mu_t, masses=masses, mix_grav=mix_grav, alpha=alpha, **kw)
        force_norm[t] = float(np.linalg.norm(F))

        # Gravitational force alone (diagnostic)
        F_g = newtonian_force(X, masses, G=kw.get('G', G_NEWTON))
        grav_force_norm[t] = float(np.linalg.norm(F_g))

        # MFLS / blind-spot gradient
        G_bsdt = bsdt.gradient(X)
        mfls[t] = float(np.linalg.norm(G_bsdt))

        # Per-agent cosine alignment
        dot_per  = np.sum(G_bsdt * F, axis=1)
        norm_g   = np.linalg.norm(G_bsdt, axis=1)
        norm_f   = np.linalg.norm(F,      axis=1)
        cos_per  = dot_per / (norm_g * norm_f + 1e-12)
        cos_theta[t] = float(np.mean(cos_per))

        # Spectral radius (every 4 steps)
        if t % 4 == 0:
            lam, _ = spectral_radius(X, K=n_power_iter, rng=rng,
                                     masses=masses, mix_grav=mix_grav)
            _lam_cache = lam
        else:
            lam = _lam_cache
        lambda_max[t] = lam
        gamma_star[t] = alpha / (lam + 1e-9)
        above_cman[t] = lam > alpha

    return {
        "energy":           energy,
        "grav_energy":      grav_energy_arr,
        "mfls":             mfls,
        "lambda_max":       lambda_max,
        "gamma_star":       gamma_star,
        "above_cman":       above_cman,
        "cos_theta":        cos_theta,
        "force_norm":       force_norm,
        "grav_force_norm":  grav_force_norm,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Quick self-test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    rng = np.random.default_rng(42)
    N, d = 12, 6
    X = rng.standard_normal((N, d)) * 0.5
    mu = np.zeros(d)
    masses = rng.uniform(0.5, 2.0, size=N)  # heterogeneous masses

    print("=== Newtonian Gravity Engine — Self Test ===")
    print(f"Particles: {N},  Dimensions: {d}")
    print(f"Masses: {masses.round(2)}")
    print()

    # Individual energy components
    E_rad  = radial_energy(X, mu)
    E_pair = pairwise_energy(X)
    E_grav = newtonian_energy(X, masses)
    E_tot  = total_energy(X, mu, masses=masses)
    print(f"Φ_radial   = {E_rad:+.4f}")
    print(f"Φ_pairwise = {E_pair:+.4f}")
    print(f"Φ_gravity  = {E_grav:+.4f}")
    print(f"Φ_total    = {E_tot:+.4f}")
    print()

    # Force norms
    F_rad  = radial_force(X, mu)
    F_pair = pairwise_force(X)
    F_grav = newtonian_force(X, masses)
    F_tot  = total_force(X, mu, masses=masses)
    print(f"‖F_radial‖   = {np.linalg.norm(F_rad):.4f}")
    print(f"‖F_pairwise‖ = {np.linalg.norm(F_pair):.4f}")
    print(f"‖F_gravity‖  = {np.linalg.norm(F_grav):.4f}")
    print(f"‖F_total‖    = {np.linalg.norm(F_tot):.4f}")
    print()

    # Test with mix_grav=0 (should match original engine)
    E_mol_only = total_energy(X, mu, masses=masses, mix_grav=0.0)
    print(f"Φ_total(mix_grav=0) = {E_mol_only:+.4f}  (should ≈ Φ_rad + Φ_pair = {E_rad + E_pair:+.4f})")
    print()

    # Spectral radius
    lam_max, _ = spectral_radius(X, masses=masses)
    print(f"λ_max(D²Φ_combined) = {lam_max:.4f}")
    print(f"γ* = α/λ_max = {ALPHA / lam_max:.4f}")
    print()
    print("✓ Self-test passed")
