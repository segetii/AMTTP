"""Domain instantiations — §8 of canonical_system_v4.

Each domain provides only (S, J, G, F_base) — the canonical ODE structure,
the gradient formula g_X = 2JᵀGS, the projection, and the gain are unchanged.

* §8.1 :class:`TradingDomain`       — statistical-arbitrage spread control
* §8.2 :class:`GalerkinDomain`      — spectral / Galerkin PDE control
* §8.3 :class:`OptimisationDomain`  — first-order optimisation
* §8.4 :class:`RoboticsDomain`      — task-space robotics control
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional
import numpy as np

from .core import CanonicalSystem


# =======================================================================
#  §8.1 — Trading / statistical-arbitrage spread control
# =======================================================================
@dataclass
class TradingDomain:
    """§8.1  X = w (portfolio weights), S(w) = Aw − b, G = Σ⁻¹.

        F_base(w) = −κ (w − w⋆)            (alpha-tracking + mean reversion)
        E(w) = (Aw−b)ᵀ Σ⁻¹ (Aw−b)          (squared Mahalanobis spread)
        g_w = 2 Aᵀ Σ⁻¹ (Aw − b)             (closed form; J = A constant)

    Parameters
    ----------
    A : (k, n) factor-loading matrix.
    b : (k,) target spread vector.
    Sigma : (k, k) factor covariance (PD).
    kappa : float > 0, alpha-tracking strength.
    w_star : (n,) alpha-target weight.
    theta : adaptive-gain regularisation (default 1.0).
    epsilon : ODE regularisation (default 0.0).
    """
    A: np.ndarray
    b: np.ndarray
    Sigma: np.ndarray
    kappa: float
    w_star: np.ndarray
    theta: float = 1.0
    epsilon: float = 0.0

    def build(self) -> CanonicalSystem:
        A = np.asarray(self.A, dtype=float)
        b = np.asarray(self.b, dtype=float)
        Sigma = np.asarray(self.Sigma, dtype=float)
        w_star = np.asarray(self.w_star, dtype=float)
        kappa = float(self.kappa)
        # G = Σ⁻¹  via Cholesky inversion (Sigma must be PD)
        L = np.linalg.cholesky(Sigma)
        G = np.linalg.solve(L.T, np.linalg.solve(L, np.eye(Sigma.shape[0])))
        S      = lambda w: A @ w - b
        J      = lambda w: A
        F_base = lambda w: -kappa * (w - w_star)
        # K ≡ 0 because S is affine — Hessian reduces to 2·G_pull
        K_zero = lambda w: np.zeros((b.size,) + (w.size,) * 2)
        return CanonicalSystem(S=S, J=J, G=G, F_base=F_base,
                               theta=self.theta, epsilon=self.epsilon,
                               K=K_zero)


# =======================================================================
#  §8.2 — Spectral / Galerkin PDE control
# =======================================================================
@dataclass
class GalerkinDomain:
    """§8.2  X = (a_1,…,a_N), S(X) = X − a⋆, G = diag(g_k), F_base = L_N X.

        E(X) = Σ_k g_k (a_k − a⋆_k)²        (weighted ℓ² norm)
        g_X = 2 G (X − a⋆)                  (J = I_N)

    Parameters
    ----------
    g_weights : (N,) mode weights g_k > 0  (e.g. g_k = k² for H¹-type energy).
    a_star    : (N,) desired spectrum.
    L_N       : (N, N) discretised PDE operator.
    """
    g_weights: np.ndarray
    a_star: np.ndarray
    L_N: np.ndarray
    theta: float = 1.0
    epsilon: float = 0.0

    def build(self) -> CanonicalSystem:
        gw = np.asarray(self.g_weights, dtype=float)
        a_star = np.asarray(self.a_star, dtype=float)
        L_N = np.asarray(self.L_N, dtype=float)
        if (gw <= 0).any():
            raise ValueError("mode weights g_k must be positive")
        N = gw.size
        G = np.diag(gw)
        I = np.eye(N)
        S      = lambda X: X - a_star
        J      = lambda X: I
        F_base = lambda X: L_N @ X
        K_zero = lambda X: np.zeros((N, N, N))
        return CanonicalSystem(S=S, J=J, G=G, F_base=F_base,
                               theta=self.theta, epsilon=self.epsilon,
                               K=K_zero)


# =======================================================================
#  §8.3 — First-order optimisation
# =======================================================================
@dataclass
class OptimisationDomain:
    """§8.3  Minimise f ∈ C².  S(X) = ∇f(X), G = I, F_base = −∇f.

        E(X) = ‖∇f(X)‖²
        J(X) = ∇²f(X)         (Hessian of f, supplied or finite-diff)
        g_X = 2 (∇²f) ∇f      (canonical gradient of E)

    Yields a damped, projection-corrected gradient flow that vanishes at
    stationary points.  See Cor. 8.3 for exponential rate when ∇²f ≻ 0.

    Parameters
    ----------
    grad_f : callable X ↦ ∇f(X) ∈ Rⁿ.
    hess_f : optional callable X ↦ ∇²f(X) ∈ Rⁿˣⁿ.  If None, central FD.
    """
    grad_f: Callable[[np.ndarray], np.ndarray]
    hess_f: Optional[Callable[[np.ndarray], np.ndarray]] = None
    n: int = 0
    theta: float = 1.0
    epsilon: float = 0.0

    def build(self) -> CanonicalSystem:
        if self.n <= 0:
            raise ValueError("OptimisationDomain.n must be set to the state dim")
        gf = self.grad_f
        I = np.eye(self.n)
        S      = lambda X: np.asarray(gf(X), dtype=float)
        J      = (lambda X: np.asarray(self.hess_f(X), dtype=float)) \
                  if self.hess_f is not None else None
        F_base = lambda X: -np.asarray(gf(X), dtype=float)
        return CanonicalSystem(S=S, J=J, G=I, F_base=F_base,
                               theta=self.theta, epsilon=self.epsilon)


# =======================================================================
#  §8.4 — Task-space robotics control
# =======================================================================
@dataclass
class RoboticsDomain:
    """§8.4  X = q (joint angles), FK : Rⁿ → Rᵏ.

        S(q) = FK(q) − p⋆,  G = W ≻ 0  (task-space weight)
        F_base(q) = −K_p · J(q)ᵀ W (FK(q) − p⋆)  (PD-controller form)
        g_q = 2 J(q)ᵀ W (FK(q) − p⋆) = (2/K_p) · |F_base(q)|·sign-aligned

    With this F_base, F_base = −(K_p/2) g_q exactly, so F = F_base − g_q is
    fully aligned with −g_q and the canonical ODE collapses to
    Ẋ = −(1 + K_p/2)(1 − γ) g_q   (degenerate alignment regime, §8.4).

    Parameters
    ----------
    fk      : callable q ↦ FK(q) ∈ Rᵏ.
    fk_jac  : optional callable q ↦ ∂FK/∂q ∈ Rᵏˣⁿ.  If None, central FD.
    p_star  : (k,) desired end-effector pose.
    W       : (k, k) task-space weight, SPD.
    Kp      : float > 0, proportional gain.
    """
    fk: Callable[[np.ndarray], np.ndarray]
    p_star: np.ndarray
    W: np.ndarray
    Kp: float
    fk_jac: Optional[Callable[[np.ndarray], np.ndarray]] = None
    theta: float = 1.0
    epsilon: float = 1e-12   # default ε > 0 to handle kinematic singularities

    def build(self) -> CanonicalSystem:
        p_star = np.asarray(self.p_star, dtype=float)
        W = np.asarray(self.W, dtype=float)
        Kp = float(self.Kp)
        S = lambda q: np.asarray(self.fk(q), dtype=float) - p_star
        J = (lambda q: np.asarray(self.fk_jac(q), dtype=float)) \
              if self.fk_jac is not None else None

        def F_base(q: np.ndarray) -> np.ndarray:
            qq = np.asarray(q, dtype=float)
            err = np.asarray(self.fk(qq), dtype=float) - p_star
            # need J(q) here — use closure over CanonicalSystem path.
            # Compute via supplied jac or finite diff (matches CanonicalSystem.jacobian).
            if self.fk_jac is not None:
                Jq = np.asarray(self.fk_jac(qq), dtype=float)
            else:
                h = 1e-6
                n = qq.size
                S0 = np.asarray(self.fk(qq), dtype=float) - p_star
                Jq = np.empty((S0.size, n))
                for i in range(n):
                    ei = np.zeros(n); ei[i] = 1.0
                    Sp = np.asarray(self.fk(qq + h * ei), dtype=float) - p_star
                    Sm = np.asarray(self.fk(qq - h * ei), dtype=float) - p_star
                    Jq[:, i] = (Sp - Sm) / (2.0 * h)
            return -Kp * Jq.T @ W @ err

        return CanonicalSystem(S=S, J=J, G=W, F_base=F_base,
                               theta=self.theta, epsilon=self.epsilon)
