"""Part IV — Stochastic canonical SDE  (canonical_system_v4 §16, v4.1 surgical extension).

The locked canonical ODE of Part I is the σ_W = 0 limit of the SDE

    dX = H(X) dt + σ_W Σ(X) dW             (§S.1)

with H(X) the canonical-ODE drift (or H = −g̃_X for the natural-gradient
variant).  The canonical default for Σ is the Fisher noise

    Σ_F(X) = I_X(X)^{†/2}                  (§S.2)

— the symmetric PSD square root of the Moore–Penrose pseudo-inverse of the
pullback Fisher metric I_X = JᵀI_S J.

This module implements:

* :func:`fisher_noise`              — Σ_F(X) = I_X^{†/2}
* :class:`CanonicalSDE`             — Euler–Maruyama integrator (§S.1)
* :func:`expected_dE_dt`            — Itô formula for E along the SDE (§Thm 16.3)
* :func:`trace_correction`          — ½ σ_W² tr(ΣᵀHΣ) (§S.3)
* :func:`mean_square_ultimate_bound` — σ_W² τ_Σ / (2ρ)  (§Thm 16.5)
* :func:`natural_gradient_langevin` — H = −g̃_X, Σ = √(2T) I_X^{†/2}  (§S.6)

The diffusion enters ONLY through the noise term — the locked drift, the
gradient g_X = 2JᵀGS, and the Euclidean projection are unchanged.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple
import numpy as np

from .core import CanonicalSystem
from .extensions import FisherInformationMetric, natural_gradient


# =======================================================================
#  §S.2 — Fisher noise field   Σ_F(X) = I_X(X)^{†/2}
# =======================================================================
def fisher_noise(fim: FisherInformationMetric,
                 X: np.ndarray,
                 *,
                 reg: float = 0.0,
                 tol: float = 1e-12) -> np.ndarray:
    r"""Symmetric PSD square root of I_X(X)^† = (Jᵀ I_S J)^†.

    Parameters
    ----------
    fim  : FisherInformationMetric  — supplies S, J, I_S(z).
    X    : (n,) state.
    reg  : Tikhonov ε added to I_X before inversion (ε = 0 → exact pseudo-inverse).
    tol  : eigenvalue threshold below which the inverse-sqrt is set to 0.

    Returns
    -------
    Σ_F(X) ∈ R^{n×n}, symmetric PSD, with rank = rank(I_X(X)).

    Notes
    -----
    Computed via eigen-decomposition: I_X = U diag(λ) Uᵀ ⇒
    Σ_F = U diag(λ_i^{−1/2} · 1[λ_i > tol]) Uᵀ.  The result satisfies
    Σ_F · I_X · Σ_F = projector onto range(I_X).  See §Prop 16.4.
    """
    Ix = fim.pullback(np.asarray(X, dtype=float))
    n = Ix.shape[0]
    if reg > 0.0:
        Ix = Ix + reg * np.eye(n)
    Ix = 0.5 * (Ix + Ix.T)
    eigs, U = np.linalg.eigh(Ix)
    inv_sqrt = np.where(eigs > tol, 1.0 / np.sqrt(np.maximum(eigs, tol)), 0.0)
    return U @ np.diag(inv_sqrt) @ U.T


# =======================================================================
#  §S.1 — Canonical SDE & Euler–Maruyama integrator
# =======================================================================
@dataclass
class SDETrajectory:
    X_final: np.ndarray
    trajectory: np.ndarray   # shape (T+1, n) when record=True, else (0, n)
    energy: np.ndarray       # shape (T+1,)
    n_steps: int


@dataclass
class CanonicalSDE:
    r"""Canonical SDE  dX = H(X) dt + σ_W Σ(X) dW  (§S.1).

    Parameters
    ----------
    drift : callable  X ↦ H(X) ∈ Rⁿ
        Drift field — either the canonical-ODE rhs ``sys.rhs`` (locked
        variant) or ``−natural_gradient(fim, X)`` (chart-covariant variant).
    diffusion : callable  X ↦ Σ(X) ∈ Rⁿˣʳ
        Diffusion field; default Fisher-noise via :func:`fisher_noise`.
    sigma_W : float ≥ 0
        Noise gain (set to 0 to recover the deterministic ODE exactly).
    energy : callable  X ↦ E(X) ∈ R≥0
        Used for trajectory diagnostics (typically ``sys.energy``).
    """
    drift: Callable[[np.ndarray], np.ndarray]
    diffusion: Callable[[np.ndarray], np.ndarray]
    sigma_W: float = 1.0
    energy: Optional[Callable[[np.ndarray], float]] = None

    def step(self,
             X: np.ndarray,
             h: float,
             rng: np.random.Generator) -> np.ndarray:
        """Single Euler–Maruyama step."""
        Sig = np.asarray(self.diffusion(X), dtype=float)
        if Sig.ndim != 2:
            raise ValueError("diffusion(X) must be a 2-D matrix")
        r = Sig.shape[1]
        dW = rng.standard_normal(r) * np.sqrt(h)
        return X + h * np.asarray(self.drift(X), dtype=float) \
                 + self.sigma_W * (Sig @ dW)

    def integrate(self,
                  X0: np.ndarray,
                  *,
                  h: float,
                  n_steps: int,
                  rng: Optional[np.random.Generator] = None,
                  record: bool = False) -> SDETrajectory:
        """Euler–Maruyama integration of the canonical SDE.

        Parameters
        ----------
        X0     : (n,) initial state.
        h      : time-step (must be small enough for stability).
        n_steps: number of EM steps.
        rng    : numpy Generator; if None a fresh default_rng() is used.
        record : whether to record the full trajectory and energy history.

        Returns
        -------
        SDETrajectory
        """
        if rng is None:
            rng = np.random.default_rng()
        X = np.asarray(X0, dtype=float).copy()
        E_fn = self.energy
        traj = [X.copy()] if record else []
        E_hist = [float(E_fn(X)) if E_fn is not None else 0.0]
        for _ in range(n_steps):
            X = self.step(X, h, rng)
            if record:
                traj.append(X.copy())
            if E_fn is not None:
                E_hist.append(float(E_fn(X)))
        return SDETrajectory(
            X_final=X,
            trajectory=np.array(traj) if record else np.empty((0, X.size)),
            energy=np.array(E_hist),
            n_steps=n_steps,
        )

    def monte_carlo(self,
                    X0: np.ndarray,
                    *,
                    h: float,
                    n_steps: int,
                    n_paths: int,
                    rng: Optional[np.random.Generator] = None) -> np.ndarray:
        """Run ``n_paths`` independent EM trajectories starting at X0.

        Returns an array of shape ``(n_paths, n_steps+1)`` of energies E(X_t)
        along each path (requires ``self.energy`` set).
        """
        if self.energy is None:
            raise ValueError("monte_carlo requires self.energy to be set")
        if rng is None:
            rng = np.random.default_rng()
        E_paths = np.empty((n_paths, n_steps + 1))
        for p in range(n_paths):
            res = self.integrate(X0, h=h, n_steps=n_steps, rng=rng, record=False)
            E_paths[p] = res.energy
        return E_paths


# =======================================================================
#  §16 Theorem 16.3 — Itô formula for the energy
# =======================================================================
def expected_dE_dt(sys: CanonicalSystem,
                   drift: Callable[[np.ndarray], np.ndarray],
                   diffusion: Callable[[np.ndarray], np.ndarray],
                   X: np.ndarray,
                   *,
                   sigma_W: float = 1.0) -> Tuple[float, float, float]:
    r"""Analytic E[dE/dt] from the Itô formula (§Thm 16.3):

        d/dt E[E(X_t)] = ⟨g_X, H⟩ + ½ σ_W² tr(Σᵀ ∇²E Σ)

    Returns ``(total, drift_term, diffusion_term)``.
    """
    X = np.asarray(X, dtype=float)
    g  = sys.gradient(X)
    HE = sys.hessian(X)
    Sig = np.asarray(diffusion(X), dtype=float)
    drift_term = float(g @ np.asarray(drift(X), dtype=float))
    diffusion_term = 0.5 * (sigma_W ** 2) * float(np.trace(Sig.T @ HE @ Sig))
    return drift_term + diffusion_term, drift_term, diffusion_term


# =======================================================================
#  §S.3 — Trace correction & noise floor
# =======================================================================
def trace_correction(sys: CanonicalSystem,
                     diffusion: Callable[[np.ndarray], np.ndarray],
                     X: np.ndarray,
                     *,
                     sigma_W: float = 1.0) -> float:
    """½ σ_W² tr(Σ(X)ᵀ ∇²E(X) Σ(X))  — the It\u00f4 correction term."""
    HE = sys.hessian(np.asarray(X, dtype=float))
    Sig = np.asarray(diffusion(X), dtype=float)
    return 0.5 * (sigma_W ** 2) * float(np.trace(Sig.T @ HE @ Sig))


# =======================================================================
#  §Thm 16.5 — Mean-square ultimate bound
# =======================================================================
def mean_square_ultimate_bound(rho: float,
                               tau_Sigma: float,
                               *,
                               sigma_W: float = 1.0) -> float:
    r"""σ_W² τ_Σ / (2 ρ)  —  the mean-square noise floor (§Thm 16.5).

    Parameters
    ----------
    rho       : exponential decay rate from Theorem 7.3.
    tau_Sigma : uniform upper bound for tr(Σᵀ ∇²E Σ) on the operating set.
    sigma_W   : noise gain.

    Returns
    -------
    The asymptotic upper bound for limsup_{t→∞} E[E(X_t)].
    """
    if rho <= 0:
        raise ValueError("rho must be > 0")
    return (sigma_W ** 2) * tau_Sigma / (2.0 * rho)


# =======================================================================
#  §S.6 — Natural-gradient Langevin (chart-covariant variant)
# =======================================================================
def natural_gradient_langevin(fim: FisherInformationMetric,
                              *,
                              T: float = 1.0,
                              reg: float = 1e-10) -> CanonicalSDE:
    r"""Build the natural-gradient Langevin SDE (§S.6):

        dX = −g̃_X(X) dt + √(2T) · I_X(X)^{†/2} dW

    with σ_W = 1 absorbed into Σ.  Stationary density (on the
    identifiable submanifold) is the Gibbs measure π_T ∝ exp(−E/T)
    with respect to the Fisher volume form (Prop. 16.7).
    """
    if T <= 0:
        raise ValueError("temperature T must be > 0")
    coef = float(np.sqrt(2.0 * T))

    def drift(X: np.ndarray) -> np.ndarray:
        return -natural_gradient(fim, X, reg=reg)

    def diffusion(X: np.ndarray) -> np.ndarray:
        return coef * fisher_noise(fim, X, reg=reg)

    def E_fn(X: np.ndarray) -> float:
        return float(fim.build(X).energy(X))

    return CanonicalSDE(drift=drift, diffusion=diffusion,
                        sigma_W=1.0, energy=E_fn)
