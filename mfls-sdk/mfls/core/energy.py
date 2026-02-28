"""
GravityEngine — potential energy, forces, phase-transition detection,
and adaptive damping (optimal policy).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.special import erf


# ---------------------------------------------------------------------------
# Default parameters
# ---------------------------------------------------------------------------

ALPHA = 0.10       # radial spring constant
GAMMA = 1.00       # pairwise coupling baseline
SIGMA = 1.00       # attraction length-scale
LAMBDA_REP = 0.10  # repulsion coefficient
EPS = 1e-5         # softening
F_MAX = 100.0      # force clamp


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class TrajectoryAnalysis:
    """Full trajectory analysis output."""
    energy: np.ndarray          # (T,)  total potential Phi(X_t)
    mfls: np.ndarray            # (T,)  MFLS detection signal
    lambda_max: np.ndarray      # (T,)  spectral radius of Hessian
    gamma_star: np.ndarray      # (T,)  optimal adaptive damping
    above_cman: np.ndarray      # (T,)  bool: above critical manifold
    cos_theta: np.ndarray       # (T,)  gradient alignment angle
    force_norm: np.ndarray      # (T,)  restoring force magnitude
    pct_supercritical: float    # fraction of time above Cman


@dataclass
class WelfareCalibration:
    """CCyB and welfare calibration output."""
    ccyb_bps: np.ndarray         # (T,)  CCyB in basis points
    welfare_loss_pp: float       # consumption-equivalent loss (pp)
    peak_ccyb_bps: float         # maximum CCyB value
    crisis_name: str


# ---------------------------------------------------------------------------
# Energy and force functions
# ---------------------------------------------------------------------------

def radial_energy(X: np.ndarray, mu: np.ndarray, alpha: float = ALPHA) -> float:
    """Radial spring energy.  X (N, d), mu (d,) → scalar."""
    return float(0.5 * alpha * np.sum((X - mu) ** 2))


def pairwise_energy(
    X: np.ndarray,
    gamma: float = GAMMA,
    sigma: float = SIGMA,
    lam: float = LAMBDA_REP,
    eps: float = EPS,
) -> float:
    """Pairwise interaction energy (erf-log potential).  X (N, d) → scalar."""
    N = X.shape[0]
    E = 0.0
    for i in range(N):
        for j in range(i + 1, N):
            r = np.linalg.norm(X[i] - X[j]) + eps
            attract = -gamma * sigma * erf(r / sigma)
            repulse = lam * np.log(r + eps)
            E += attract + repulse
    return float(E)


def total_energy(X: np.ndarray, mu: np.ndarray, **kw) -> float:
    """Total potential: radial + pairwise."""
    return radial_energy(X, mu, kw.get("alpha", ALPHA)) + pairwise_energy(X, **{k: v for k, v in kw.items() if k != "alpha"})


def _pairwise_force(X: np.ndarray, gamma=GAMMA, sigma=SIGMA, lam=LAMBDA_REP, eps=EPS) -> np.ndarray:
    N, d = X.shape
    F = np.zeros_like(X)
    for i in range(N):
        for j in range(N):
            if i == j:
                continue
            diff = X[i] - X[j]
            r = np.linalg.norm(diff) + eps
            rhat = diff / r
            attract = gamma * (2.0 / np.sqrt(np.pi)) * np.exp(-(r / sigma) ** 2)
            repulse = -lam / r
            F[i] += (attract + repulse) * rhat
    return F


def total_force(X: np.ndarray, mu: np.ndarray, alpha=ALPHA, **kw) -> np.ndarray:
    """Total restoring force = -grad Phi.  (N, d) → (N, d)."""
    radial = -alpha * (X - mu)
    pw = _pairwise_force(X, **kw)
    return radial + pw


# ---------------------------------------------------------------------------
# Spectral radius of the Hessian (power iteration)
# ---------------------------------------------------------------------------

def spectral_radius_hessian(
    X: np.ndarray,
    mu: np.ndarray,
    K: int = 20,
    rng: Optional[np.random.Generator] = None,
    **kw,
) -> float:
    """Approximate lambda_max of the Hessian via randomised power iteration."""
    if rng is None:
        rng = np.random.default_rng(42)
    h = 1e-4
    v = rng.standard_normal(X.shape)
    v /= np.linalg.norm(v)
    for _ in range(K):
        Xp = X + h * v
        Xm = X - h * v
        Ep = total_energy(Xp, mu, **kw)
        Em = total_energy(Xm, mu, **kw)
        E0 = total_energy(X, mu, **kw)
        Hv = (Ep + Em - 2 * E0) / (h ** 2) * v  # approximate H*v
        lam = np.linalg.norm(Hv)
        if lam > 1e-12:
            v = Hv / lam
    return float(lam)


# ---------------------------------------------------------------------------
# Trajectory analysis
# ---------------------------------------------------------------------------

def analyse_trajectory(
    X_series: np.ndarray,
    mu: np.ndarray,
    bsdt_operator,
    alpha: float = ALPHA,
    n_power_iter: int = 20,
    verbose: bool = False,
) -> TrajectoryAnalysis:
    """
    Full trajectory analysis: energy, MFLS, spectral radius, optimal damping.

    Parameters
    ----------
    X_series : ndarray (T, N, d)
    mu : ndarray (d,)
    bsdt_operator : BSDTOperator (must be fitted)
    alpha : float
    n_power_iter : int
    verbose : bool

    Returns
    -------
    TrajectoryAnalysis
    """
    T = X_series.shape[0]
    energy = np.zeros(T)
    mfls = np.zeros(T)
    lmax = np.zeros(T)
    gstar = np.zeros(T)
    cos_th = np.zeros(T)
    fnorm = np.zeros(T)

    for t in range(T):
        Xt = X_series[t]
        energy[t] = total_energy(Xt, mu, alpha=alpha)
        mfls[t] = bsdt_operator.mfls_score(Xt)

        # Spectral radius
        lmax[t] = spectral_radius_hessian(Xt, mu, K=n_power_iter, alpha=alpha)

        # Optimal damping: gamma* = E(X) / (E(X) + theta)
        E_blind = bsdt_operator.energy_score(Xt)
        theta = 1.0  # intervention cost parameter
        gstar[t] = E_blind / (E_blind + theta) if E_blind > 0 else 0.0

        # Gradient alignment
        grad_bs = bsdt_operator.gradient(Xt).ravel()
        force = total_force(Xt, mu, alpha=alpha).ravel()
        fnorm[t] = np.linalg.norm(force)
        g_norm = np.linalg.norm(grad_bs)
        if fnorm[t] > 1e-12 and g_norm > 1e-12:
            cos_th[t] = np.dot(grad_bs, force) / (g_norm * fnorm[t])

        if verbose and (t + 1) % 20 == 0:
            print(f"  Trajectory: {t + 1}/{T}")

    above_cman = lmax > 1.0
    return TrajectoryAnalysis(
        energy=energy,
        mfls=mfls,
        lambda_max=lmax,
        gamma_star=gstar,
        above_cman=above_cman,
        cos_theta=cos_th,
        force_norm=fnorm,
        pct_supercritical=float(above_cman.mean()),
    )


# ---------------------------------------------------------------------------
# Welfare / CCyB calibration
# ---------------------------------------------------------------------------

def calibrate_ccyb(
    energy: np.ndarray,
    gamma_star: np.ndarray,
    leverage_std: np.ndarray,
    kappa: float = 1.0,
) -> np.ndarray:
    """
    Map gamma*(X_t) to CCyB basis points.

    CCyB(t) = kappa^{-1} * gamma*(t) * sigma_ell(t)  (scaled to [0, 250] bps)

    Parameters
    ----------
    energy : (T,)
    gamma_star : (T,)
    leverage_std : (T,) — cross-sectional std of leverage at each t
    kappa : float — intervention cost

    Returns
    -------
    ccyb_bps : (T,)
    """
    raw = gamma_star * leverage_std / kappa
    # Scale to 0-250 bps (Basel III CCyB range)
    if raw.max() > 1e-12:
        ccyb = 250.0 * raw / raw.max()
    else:
        ccyb = np.zeros_like(raw)
    return ccyb


def welfare_loss(
    energy: np.ndarray,
    energy_counterfactual: np.ndarray,
    sigma: float = 1.0,
    theta: float = 1.0,
    T_window: int = 10,
) -> float:
    """
    Consumption-equivalent welfare loss (percentage points).

    Parameters
    ----------
    energy : (T_window,) — actual energy path during crisis
    energy_counterfactual : (T_window,) — energy under optimal gamma*
    sigma, theta : calibration parameters
    T_window : number of crisis quarters

    Returns
    -------
    float — welfare loss in percentage points
    """
    gap = np.sum(energy - energy_counterfactual)
    pct = 100.0 * (1.0 - np.exp(-gap / (sigma * theta * T_window)))
    return max(0.0, float(pct))
