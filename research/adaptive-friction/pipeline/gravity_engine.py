"""
gravity_engine.py  (pipeline version)
======================================
Self-contained GravityEngine implementation for the empirical pipeline.
Matches the mathematical specification in main.tex ?4-?5 exactly.

Key quantities computed per time step t:
    Phi(X)          - total potential energy
    grad_Phi(X)     - restoring force field  (N ? d)
    lambda_max(t)   - leading eigenvalue of D??_pair (power iteration)
    gamma_star(t)   - adaptive coupling  alpha / lambda_max
    mfls(t)         - MFLS detection score (blind-spot energy gradient norm)
    cos_theta(t)    - alignment: ?E_BS vs ???  (re-verification on real data)
"""

from __future__ import annotations
import numpy as np
from scipy.special import erf as _erf


# ?????????????????????????????????????????????????????????????????????????????
# Parameters  (match paper Appendix B table)
# ?????????????????????????????????????????????????????????????????????????????
ALPHA      = 0.10   # radial spring
GAMMA      = 1.00   # pairwise coupling baseline
SIGMA      = 1.00   # attraction length-scale
LAMBDA_REP = 0.10   # repulsion coefficient
EPS        = 1e-5   # softening
F_MAX      = 100.0  # force clamp


# ?????????????????????????????????????????????????????????????????????????????
# Potential energy
# ?????????????????????????????????????????????????????????????????????????????

def radial_energy(X: np.ndarray, mu: np.ndarray, alpha: float = ALPHA) -> float:
    """?_rad = (alpha/2) ?? ?x? ? ???"""
    diff = X - mu[None, :]                  # (N, d)
    return 0.5 * alpha * float(np.sum(diff ** 2))


def pairwise_energy(X: np.ndarray, gamma: float = GAMMA,
                    sigma: float = SIGMA, lam: float = LAMBDA_REP,
                    eps: float = EPS) -> float:
    """?_pair = ??<? [gamma?erf_potential ? gammalambda?log(r?? + ?)]"""
    N = X.shape[0]
    diff = X[:, None, :] - X[None, :, :]   # (N, N, d)
    dist = np.linalg.norm(diff, axis=2)    # (N, N)
    np.fill_diagonal(dist, eps)
    # Attraction (erf integral)
    E_att = 0.5 * gamma * (sigma * np.sqrt(np.pi) * 0.5) * np.sum(_erf(dist / sigma))
    # Repulsion
    E_rep = -0.5 * gamma * lam * np.sum(np.log(dist + eps))
    # Remove diagonal self-terms
    E_att -= N * gamma * (sigma * np.sqrt(np.pi) * 0.5) * _erf(0.0)
    E_rep += N * gamma * lam * np.log(eps)
    return float(E_att + E_rep)


def total_energy(X: np.ndarray, mu: np.ndarray, **kw) -> float:
    return radial_energy(X, mu, kw.get("alpha", ALPHA)) + \
           pairwise_energy(X, kw.get("gamma", GAMMA),
                           kw.get("sigma", SIGMA),
                           kw.get("lam", LAMBDA_REP),
                           kw.get("eps", EPS))


# ?????????????????????????????????????????????????????????????????????????????
# Gradient (force) - analytic
# ?????????????????????????????????????????????????????????????????????????????

def radial_force(X: np.ndarray, mu: np.ndarray, alpha: float = ALPHA) -> np.ndarray:
    """-??_rad = alpha(? ? X)"""
    return alpha * (mu[None, :] - X)        # (N, d)


def pairwise_force(X: np.ndarray, gamma: float = GAMMA, sigma: float = SIGMA,
                   lam: float = LAMBDA_REP, eps: float = EPS) -> np.ndarray:
    """-??_pair  shape (N, d)

    Matches udl/gravity.py formula exactly:
        magnitude = -gamma ? (exp(?r?/??) ? lambda/r)
        force on i = magnitude_ij ? unit_ij   summed over j

    This is -d/dr[?_pair] = -d/dr[gamma?(???/2)?erf(r/?) ? gammalambda?ln(r)]
                          = -gamma?exp(-r?/??) + gammalambda/r
    """
    N, d = X.shape
    diff = X[:, None, :] - X[None, :, :]   # (N, N, d)  diff[i,j] = x? - x?
    dist = np.linalg.norm(diff, axis=2)    # (N, N)
    np.fill_diagonal(dist, eps)
    unit = diff / (dist[:, :, None] + eps)  # (N, N, d)  unit direction i?j

    # -gamma?(exp(-r?/??) - lambda/r) = gamma?(lambda/r - exp(-r?/??))
    attraction = np.exp(-(dist ** 2) / (sigma ** 2))  # (N, N), dimensionless
    repulsion  = lam / (dist + eps)                    # (N, N)
    magnitude  = -gamma * (attraction - repulsion)     # (N, N)
    np.fill_diagonal(magnitude, 0.0)

    F = np.sum(magnitude[:, :, None] * unit, axis=1)  # (N, d)

    # Force clamp
    norms = np.linalg.norm(F, axis=1, keepdims=True)
    scale = np.where(norms > F_MAX, F_MAX / (norms + 1e-12), 1.0)
    return F * scale


def total_force(X: np.ndarray, mu: np.ndarray, **kw) -> np.ndarray:
    """-?? = F_rad + F_pair"""
    return radial_force(X, mu, kw.get("alpha", ALPHA)) + \
           pairwise_force(X, kw.get("gamma", GAMMA),
                          kw.get("sigma", SIGMA),
                          kw.get("lam", LAMBDA_REP),
                          kw.get("eps", EPS))


# ?????????????????????????????????????????????????????????????????????????????
# Spectral radius via power iteration (Rayleigh quotient)
# ?????????????????????????????????????????????????????????????????????????????

def _hvp(X: np.ndarray, v: np.ndarray, h: float = 1e-4, **kw) -> np.ndarray:
    """Finite-difference Hessian-vector product for ?_pair."""
    v_unit = v / (np.linalg.norm(v) + 1e-12)
    Fp = pairwise_force(X + h * v_unit, **kw)
    Fm = pairwise_force(X - h * v_unit, **kw)
    # D??_pair ? v ? (?F(X+hv) + F(X?hv)) / (2h)  [since F = ???_pair]
    return (Fm - Fp) / (2 * h)


def spectral_radius(X: np.ndarray, K: int = 20, rng: np.random.Generator | None = None,
                    **kw) -> tuple[float, np.ndarray]:
    """
    Estimate lambda_max(D??_pair(X)) via K steps of power iteration.
    Returns (lambda_max, leading_eigenvector).
    """
    if rng is None:
        rng = np.random.default_rng(0)
    v = rng.standard_normal(X.shape)
    v /= np.linalg.norm(v) + 1e-12
    lam = 0.0
    for _ in range(K):
        Hv = _hvp(X, v, **kw)
        lam = float(np.sum(Hv * v))        # Rayleigh quotient
        v = Hv / (np.linalg.norm(Hv) + 1e-12)
    return max(lam, 1e-6), v


# ?????????????????????????????????????????????????????????????????????????????
# BSDT blind-spot energy (for MFLS score and alignment verification)
# ?????????????????????????????????????????????????????????????????????????????

class BSDTOperator:
    """Fitted BSDT reference distribution; computes E_BS gradient."""

    def __init__(self):
        self.mu0_: np.ndarray | None = None
        self.Sigma0_inv_: np.ndarray | None = None

    def fit(self, X_normal: np.ndarray) -> "BSDTOperator":
        """Fit on normal-period data (T_normal, N, d) - reshape to (T*N, d)."""
        Xf = X_normal.reshape(-1, X_normal.shape[-1])
        self.mu0_ = Xf.mean(axis=0)
        cov = np.cov(Xf.T) + 1e-6 * np.eye(Xf.shape[1])
        self.Sigma0_inv_ = np.linalg.inv(cov)
        return self

    def deviation(self, X: np.ndarray) -> np.ndarray:
        """??(X) = (x? ? ??)? ???? (x? ? ??)   shape (N,)"""
        z = X - self.mu0_
        return np.sum(z @ self.Sigma0_inv_ * z, axis=1)

    def energy_score(self, X: np.ndarray) -> float:
        """MFLS = ?? ??(X)  (total blind-spot energy, deviation terms only)"""
        return float(np.sum(self.deviation(X)))

    def gradient(self, X: np.ndarray) -> np.ndarray:
        """?E_BS deviation term = 2 ???? (X ? ??)   shape (N, d)"""
        z = X - self.mu0_
        return 2.0 * (z @ self.Sigma0_inv_.T)

    def mfls_score(self, X: np.ndarray) -> float:
        """??E_BS(X)?_F - Frobenius norm of gradient as detection score."""
        return float(np.linalg.norm(self.gradient(X)))


# ?????????????????????????????????????????????????????????????????????????????
# Main trajectory analysis
# ?????????????????????????????????????????????????????????????????????????????

def simulate_and_align(
    X0: np.ndarray,
    mu: np.ndarray,
    bsdt: "BSDTOperator",
    n_steps: int = 100,
    eta: float = 0.02,
    alpha: float = ALPHA,
) -> dict[str, float]:
    """
    Starting from initial state X0 (e.g. the FRED state at a crisis onset),
    run the GravityEngine simulation for n_steps and measure gradient alignment
    at each step.  This replicates the verify_gradient_alignment.py methodology
    on real-data initial conditions.

    Returns mean/min/frac-above-0.7 cos ? over the trajectory.
    """
    X = X0.copy()
    cos_history = []
    for _ in range(n_steps):
        mu_t = X.mean(axis=0)   # current cluster centre (matches verify script)
        F     = total_force(X, mu_t, alpha=alpha)
        G_bs  = bsdt.gradient(X)
        dot_  = np.sum(G_bs * F, axis=1)
        nG    = np.linalg.norm(G_bs, axis=1)
        nF    = np.linalg.norm(F,    axis=1)
        cos_  = dot_ / (nG * nF + 1e-12)
        cos_history.append(float(np.mean(cos_)))
        X = X + eta * F         # gradient flow step
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
    alpha: float = ALPHA,
    n_power_iter: int = 20,
    verbose: bool = False,
) -> dict[str, np.ndarray]:
    """
    Given a T-length series of state matrices X(t) ? ?^{N ? d},
    compute per-step statistics.

    Parameters
    ----------
    X_series : (T, N, d)
    mu       : (d,) equilibrium (mean over normal period)
    bsdt     : fitted BSDTOperator

    Returns
    -------
    dict with keys:
        energy       (T,)  - ?(X_t)
        mfls         (T,)  - MFLS detection score
        lambda_max   (T,)  - spectral radius of D??_pair
        gamma_star   (T,)  - adaptive coupling alpha/lambda_max
        above_cman   (T,)  - bool: lambda_max(t) > alpha  (above critical manifold)
        cos_theta    (T,)  - gradient alignment angle
        force_norm   (T,)  - ?????_F
    """
    T, N, d = X_series.shape
    rng = np.random.default_rng(42)

    energy      = np.zeros(T)
    mfls        = np.zeros(T)
    lambda_max  = np.zeros(T)
    gamma_star  = np.zeros(T)
    above_cman  = np.zeros(T, dtype=bool)
    cos_theta   = np.zeros(T)
    force_norm  = np.zeros(T)

    for t in range(T):
        X = X_series[t]
        if verbose and t % 20 == 0:
            print(f"  t={t:3d}/{T}")

        # Use current cluster mean as radial anchor (matches verify_gradient_alignment.py)
        mu_t = X.mean(axis=0)

        # Energy (use fixed equilibrium mu for potential comparisons across time)
        energy[t] = total_energy(X, mu, alpha=alpha)

        # Force (= ???) anchored at current cluster mean
        F = total_force(X, mu_t, alpha=alpha)
        force_norm[t] = float(np.linalg.norm(F))

        # MFLS / blind-spot gradient (measures distance from historical normal)
        G_bsdt = bsdt.gradient(X)
        mfls[t] = float(np.linalg.norm(G_bsdt))

        # Per-agent cosine alignment (matching verify_gradient_alignment.py cosine_alignment())
        # For each agent i: cos_?? = ??E_BS(x?), F(x?)? / (??E_BS(x?)? ? ?F(x?)?)
        dot_per  = np.sum(G_bsdt * F, axis=1)           # (N,)
        norm_g   = np.linalg.norm(G_bsdt, axis=1)       # (N,)
        norm_f   = np.linalg.norm(F,      axis=1)       # (N,)
        cos_per  = dot_per / (norm_g * norm_f + 1e-12)  # (N,)
        cos_theta[t] = float(np.mean(cos_per))

        # Spectral radius (cheaper: every 4 steps, interpolate between)
        if t % 4 == 0:
            lam, _ = spectral_radius(X, K=n_power_iter, rng=rng)
            _lam_cache = lam
        else:
            lam = _lam_cache
        lambda_max[t] = lam
        gamma_star[t] = alpha / (lam + 1e-9)
        above_cman[t] = lam > alpha

    return {
        "energy":      energy,
        "mfls":        mfls,
        "lambda_max":  lambda_max,
        "gamma_star":  gamma_star,
        "above_cman":  above_cman,
        "cos_theta":   cos_theta,
        "force_norm":  force_norm,
    }
