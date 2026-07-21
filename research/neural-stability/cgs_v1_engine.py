"""
cgs_v1_engine.py
================
Canonical Geometric System v1 (CGS-v1)
Seven theorem-level extensions of the Canonical Euclidean Kernel v4 (CEK-v4),
plus all Gap-Closure addenda G1-G7 from the canonical gap document.

Mathematical source documents (in order of supersession):
  canonicaldocument_pdf.pdf          <- base CEK-v4
  canonicalgapdocument_pdf.pdf       <- gap closures G1-G7
  math_reference_corrected.pdf       <- corrected derivations
  Complete_Derivations_Full.pdf      <- full proofs
  CGS_v1_manuscript.pdf              <- LATEST: universal architecture (this file)

CGS-v1 universal flow (Section 2.3, CGS_v1_manuscript.pdf):
    g* = P_D(nabla E_lambda)          projection onto admissible subspace D_X
    Xdot = Fbase - g* - gamma * <Fbase-g*, g*> / ||g*||^2  * g*
    gamma = E_lambda / (E_lambda + theta)

Structural commitment (Section 10.2):
    1.  CEK-v4 frozen Euclidean kernel is locked and unchanged.
    2.  CGS-v1 is the universal architecture; each extension chooses (D_X, nabla E_lambda, Fbase).
    3.  Projection acts on the CORRECTION FIELD g*, not on the chain-rule gradient nabla E.
    4.  Every theorem has explicit hypotheses, coercivity constants, and scope.

Extensions implemented:
    Ext I    SymplecticCGS   -- symplectic / Poisson (Hamiltonian-tangent projection)
    Ext II   LieGroupCGS     -- matrix Lie groups SO(n), SE(3), retracted integrator
    Ext III  ParetoCGS       -- multi-objective Pareto / MGDA
    Ext IV   GraphWaveletCGS -- diffusion-wavelet graph flow
    Ext V    KurtosisCGS     -- kurtosis-corrected SPD preconditioner
    Ext VI   RobustCGS       -- robust / adversarial damping (minimax)
    Ext VII  DelayCGS        -- delay / LK functional + Smith predictors

Gap closures:
    G1   euler_step, rk4_step, adaptive_euler_h, integrate_trajectory
    G2   sde_euler_maruyama, fisher_noise_sigma, ito_correction, free_energy
    G3   metric_relaxation_step, rho_flow, optimal_sigma_rel
    G4   rho_eff_pointwise, singularity_avoidance_check
    G5   fp_per_1000, lead_precision_frontier
    G6   kappa_rep, chart_dependence_negligible
    G7   tikhonov_regularize, psi_star

Extra:
    PortHamiltonianCGS    -- multi-engine port-Hamiltonian composition
    collapse_horizon      -- closed-form linear collapse-time estimate
    spectral_proxy        -- local convergence rate proxy

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

try:
    from scipy.linalg import expm as _scipy_expm
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

EPS = 1e-12


# ============================================================
# LOW-LEVEL MATRIX EXPONENTIAL (falls back to first-order if scipy absent)
# ============================================================

def _matrix_exp(A: np.ndarray) -> np.ndarray:
    if _HAS_SCIPY:
        return _scipy_expm(A)
    # First-order Cayley approximation as fallback (accurate for small steps)
    n = A.shape[0]
    I = np.eye(n)
    return np.linalg.solve(I - 0.5 * A, I + 0.5 * A)


# ============================================================
# SECTION 0: UNIVERSAL FLOW PRIMITIVE
# ============================================================

def universal_rhs(Fbase: np.ndarray,
                  g_star: np.ndarray,
                  E_lambda: float,
                  theta: float) -> np.ndarray:
    """
    CGS-v1 universal ODE right-hand side (single state vector).

    Xdot = Fbase - g* - gamma * alpha * g*
    where  alpha = <Fbase - g*, g*> / ||g*||^2
           gamma = E_lambda / (E_lambda + theta)

    Theorem 2.1 (CGS.1): Elambda_dot = <nabla E, Fbase> - (1+gamma*alpha)<nabla E, g*>
    Corollary 2.2 (CGS.2): Edot <= 0 when <nabla E, Fbase> <= (1+gamma*alpha)<nabla E, g*>
    """
    g2 = float(np.dot(g_star, g_star)) + EPS
    alpha = float(np.dot(Fbase - g_star, g_star)) / g2
    gamma = float(E_lambda) / (float(E_lambda) + float(theta) + EPS)
    return Fbase - g_star - gamma * alpha * g_star


# ============================================================
# SECTION 1: G1 — INTEGRATORS
# (Proposition G1.1, Corollary G1.2, G1.3, §G1.2 canonicalgapdocument)
# ============================================================

def euler_step(X: np.ndarray, rhs: Callable[[np.ndarray], np.ndarray],
               h: float) -> np.ndarray:
    """Explicit Euler: X_{t+h} = X_t + h * RHS(X_t)."""
    return X + h * rhs(X)


def rk4_step(X: np.ndarray, rhs: Callable[[np.ndarray], np.ndarray],
             h: float) -> np.ndarray:
    """
    Classical RK4 integrator. Local truncation error O(h^5), global O(h^4).
    Preferred over Euler for stiffness; energy monotonicity condition weakens
    to coefficient 1/120 instead of 1/2 (§G1.2).
    """
    k1 = rhs(X)
    k2 = rhs(X + 0.5 * h * k1)
    k3 = rhs(X + 0.5 * h * k2)
    k4 = rhs(X + h * k3)
    return X + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def adaptive_euler_h(Edot: float, Lambda: float, Xdot_norm2: float,
                     h0: float = 0.01) -> float:
    """
    Corollary G1.2: safe step h <= -2 * Edot / (Lambda * |Xdot|^2).
    Lambda = lambda_max(nabla^2 E(X_t)).  Falls back to h0 when undetermined.
    """
    denom = Lambda * Xdot_norm2 + EPS
    if Edot >= 0.0 or denom <= 0.0:
        return h0
    h_safe = -2.0 * Edot / denom
    return float(np.clip(h_safe, 1e-6, h0))


def integrate_trajectory(X0: np.ndarray,
                         rhs: Callable[[np.ndarray], np.ndarray],
                         steps: int,
                         h: float = 0.01,
                         method: str = "rk4") -> np.ndarray:
    """
    Integrate ODE forward `steps` steps from X0.
    Returns array of shape (steps+1, n).
    method: "rk4" (default) or "euler".
    """
    traj = np.empty((steps + 1, X0.shape[0]))
    traj[0] = X0
    step_fn = rk4_step if method == "rk4" else euler_step
    X = X0.copy()
    for k in range(steps):
        X = step_fn(X, rhs, h)
        traj[k + 1] = X
    return traj


# ============================================================
# SECTION 2: G2 — STOCHASTIC SDE + FREE ENERGY
# (Theorem G2.1, Proposition G2.2, Corollary G2.3, Theorem G2.4)
# ============================================================

def sde_euler_maruyama(X: np.ndarray,
                       drift_fn: Callable[[np.ndarray], np.ndarray],
                       sigma_fn: Callable[[np.ndarray], np.ndarray],
                       dt: float,
                       rng: np.random.Generator) -> np.ndarray:
    """
    Euler-Maruyama step for canonical SDE:  dX = H(X)dt + Sigma(X)dW_t
    Theorem G2.1: dE = <g_X, H>dt + <g_X, Sigma dW> + 1/2 tr(Sigma^T nabla^2 E Sigma) dt
    """
    sigma = sigma_fn(X)
    m = sigma.shape[1] if sigma.ndim == 2 else X.shape[0]
    dW = rng.standard_normal(m) * np.sqrt(dt)
    noise = (sigma @ dW) if sigma.ndim == 2 else (sigma * dW)
    return X + dt * drift_fn(X) + noise


def fisher_noise_sigma(I_X: np.ndarray) -> np.ndarray:
    """
    Proposition G2.2: Sigma = I_X^{dagger 1/2}  (Moore-Penrose square root).
    Under this choice, the Ito correction on {S=0} equals rank(I_X)/2 (chart-independent).
    """
    vals, vecs = np.linalg.eigh(I_X)
    sqrt_pinv = np.where(vals > EPS, 1.0 / np.sqrt(np.maximum(vals, EPS)), 0.0)
    return vecs @ np.diag(sqrt_pinv) @ vecs.T


def ito_correction(sigma: np.ndarray, hess_E: np.ndarray) -> float:
    """Theorem G2.1: Ito correction = 1/2 tr(Sigma^T nabla^2 E Sigma)."""
    return 0.5 * float(np.trace(sigma.T @ hess_E @ sigma))


def free_energy(E_mean: float, rank_IX: int, t: float) -> float:
    """
    Corollary G2.3: F = E[E] - rank(I_X)/2 * t.
    F is non-increasing when the deterministic descent condition holds.
    The Ito correction is a constant-rate drift, not an instability source.
    """
    return E_mean - 0.5 * rank_IX * t


# ============================================================
# SECTION 3: G3 — TIME-VARYING G(t)
# (Theorem G3.1, Remark G3.2, Corollary G3.3)
# ============================================================

def metric_relaxation_step(G_t: np.ndarray, G_star: np.ndarray,
                            sigma_rel: float, dt: float) -> np.ndarray:
    """
    Theorem G3.1: Gdot = sigma_rel (G* - G).  Euler step.
    rho_flow -> rho_F as t -> inf (Remark G3.2).
    """
    return G_t + dt * sigma_rel * (G_star - G_t)


def rho_flow(rho_F: float, mu_t: float, delta_G_t: float) -> float:
    """
    Theorem G3.1: rho_flow = rho_F * mu*(t) / (mu*(t) + delta_G(t)).
    mu_t = lambda_min(G(t)), delta_G_t = ||G(t) - G*||_F / ||G*||_F.
    """
    return rho_F * mu_t / (mu_t + delta_G_t + EPS)


def optimal_sigma_rel(rho_F: float, mu0: float,
                      G0: np.ndarray, G_star: np.ndarray) -> float:
    """
    Corollary G3.3: sigma_rel* = rho_F * mu*(0) / ||G(0)-G*||_F.
    Minimises integral energy bound int_0^inf E(t)dt.
    """
    delta = float(np.linalg.norm(G0 - G_star, "fro"))
    return rho_F * mu0 / (delta + EPS)


# ============================================================
# SECTION 4: G4 — NEAR-SINGULAR CONVERGENCE
# (Theorem G4.1, Proposition G4.2)
# ============================================================

def rho_eff_pointwise(sigma_min_J: float, mu_G: float,
                      M_G: float, gamma: float) -> float:
    """
    Theorem G4.1: rho_eff(X) = 4 sigma^2 mu_G^2 / M_G * (1 - gamma).
    Pointwise rate when sigma_min(J(X)) may vary near singular set.
    """
    return 4.0 * sigma_min_J ** 2 * mu_G ** 2 / (M_G + EPS) * (1.0 - gamma)


def singularity_avoidance_check(sigma_min_J: float, M_G: float,
                                 mu_G: float, M_dist: float,
                                 gamma_max: float) -> bool:
    """
    Proposition G4.2: canonical ODE avoids singular set if
    sigma_min(J) >= sigma_crit = sqrt(M_G * M / (4 mu_G^2 (1-gamma_max))).
    Returns True if condition holds (safe), False if at risk.
    """
    sigma_crit = np.sqrt(M_G * M_dist / (4.0 * mu_G ** 2 * (1.0 - gamma_max) + EPS))
    return sigma_min_J >= sigma_crit


# ============================================================
# SECTION 5: G5 — FALSE-POSITIVE RATE PROTOCOL
# (Definition G5.1, Protocol G5.2)
# ============================================================

def fp_per_1000(alarms: np.ndarray, crisis_mask: np.ndarray) -> float:
    """
    Protocol G5.2: count FP alarms per 1000 non-crisis steps.
    lambda_FP < 5 /1000h = deployment-grade for grid operators.
    lambda_FP < 20/1000h = research-grade.
    """
    non_crisis = ~crisis_mask.astype(bool)
    n_nc = int(non_crisis.sum())
    if n_nc == 0:
        return 0.0
    fp = int(alarms[non_crisis].sum())
    return fp / n_nc * 1000.0


def lead_precision_frontier(alarms: np.ndarray,
                             crisis_onsets: Sequence[int],
                             crisis_mask: np.ndarray,
                             L_values: Sequence[int]) -> Dict[int, float]:
    """
    Protocol G5.2, step 5: precision at each lead L.
    Precision(L) = TP(L) / (TP(L) + FP).
    """
    n = len(alarms)
    fp = int(alarms[~crisis_mask.astype(bool)].sum())
    result: Dict[int, float] = {}
    for L in L_values:
        tp = 0
        for onset in crisis_onsets:
            window = range(max(0, onset - int(L)), min(n, onset + 1))
            if any(alarms[i] for i in window):
                tp += 1
        denom = tp + fp
        result[int(L)] = tp / denom if denom > 0 else 0.0
    return result


def theoretical_fpr(k_sigma: float = 2.0, lambda_bg: float = 1.0) -> float:
    """
    §G5.3: lambda_FP = lambda_bg * 2*(1 - Phi(k)).
    For k=2: ~0.046 * lambda_bg (roughly 1 false alarm per 22 steps under normality).
    """
    from math import erfc, sqrt
    return lambda_bg * erfc(k_sigma / sqrt(2.0))


# ============================================================
# SECTION 6: G6 — CHART-DEPENDENCE METRIC
# (Definition G6.1, Proposition G6.2)
# ============================================================

def kappa_rep(T: np.ndarray) -> float:
    """
    Definition G6.1: kappa_rep = ||I - T^{-1}||_op + O(||T-I||^2).
    T = Jacobian of reparametrisation diffeomorphism at X.
    kappa_rep < delta => chart dependence negligible (Prop G6.2).
    """
    try:
        T_inv = np.linalg.inv(T)
    except np.linalg.LinAlgError:
        return float("inf")
    return float(np.linalg.norm(np.eye(T.shape[0]) - T_inv, ord=2))


def chart_dependence_negligible(T: np.ndarray, delta: float = 0.05) -> bool:
    """
    Proposition G6.2: negligible iff ||T - I||_op < delta/2.
    For BSDT with affine S (J=const): kappa_rep = 0 identically.
    """
    return float(np.linalg.norm(T - np.eye(T.shape[0]), ord=2)) < delta * 0.5


# ============================================================
# SECTION 7: G7 — TIKHONOV CALIBRATION CONDITIONING
# (Proposition G7.1, Corollary G7.2)
# ============================================================

def tikhonov_regularize(Sigma0: np.ndarray,
                        kappa_max: float = 10.0,
                        theta: Optional[float] = None
                        ) -> Tuple[np.ndarray, float, Optional[float]]:
    """
    Regularise Sigma0 to target condition number kappa_max.
    lambda* = (lambda_max - kappa_max * lambda_min) / (kappa_max - 1).
    theta_new = theta * kappa / kappa_max  (to hold Psi* constant).

    Corollary G7.2: Psi* degrades as 1/sqrt(kappa(Sigma0)).
    Returns (Sigma_reg, lambda_star, theta_new).
    """
    eigvals = np.linalg.eigvalsh(Sigma0)
    lam_min = float(eigvals.min())
    lam_max = float(eigvals.max())
    kappa = lam_max / (lam_min + EPS)
    if kappa <= kappa_max:
        return Sigma0.copy(), 0.0, theta
    lam_star = (lam_max - kappa_max * lam_min) / (kappa_max - 1.0)
    Sigma_reg = Sigma0 + lam_star * np.eye(Sigma0.shape[0])
    theta_new = (theta * kappa / kappa_max) if theta is not None else None
    return Sigma_reg, float(lam_star), theta_new


def psi_star(sigma_min_J: float, theta: float,
             kappa_Sigma0: float, lam_max_Sigma0: float) -> float:
    """
    Proposition G7.1: Psi* = sigma*theta / sqrt(kappa(Sigma0) * lambda_max(Sigma0)).
    Admissibility threshold for disturbance budget M.
    """
    return sigma_min_J * theta / (np.sqrt(kappa_Sigma0 * lam_max_Sigma0) + EPS)


# ============================================================
# SECTION 8: EXTENSION I — SYMPLECTIC / POISSON  (§3 CGS-v1)
# ============================================================

def symplectic_projection(grad_E: np.ndarray, grad_H: np.ndarray) -> np.ndarray:
    """
    P_H = I - (nabla H)(nabla H)^T / ||nabla H||^2  applied to grad_E.
    Preserves Hamiltonian: Theorem 3.1 (H_dot = 0 under Fbase = X_H).
    Theorem 3.2: E_dot = <nabla E, X_H> - (1+gamma*alpha)*||g*||^2.
    """
    norm2 = float(np.dot(grad_H, grad_H)) + EPS
    return grad_E - (float(np.dot(grad_H, grad_E)) / norm2) * grad_H


def poisson_projection(grad_E: np.ndarray,
                       casimir_grads: List[np.ndarray]) -> np.ndarray:
    """
    Theorem 3.5: Casimir conservation — remove all Casimir directions from g.
    g_Pi = g_X - sum_i <g_X, nabla C_i>/||nabla C_i||^2 * nabla C_i.
    Cdot_i = 0 along the Poisson CGS-v1 flow.
    """
    g = grad_E.copy()
    for c in casimir_grads:
        norm2 = float(np.dot(c, c)) + EPS
        g = g - (float(np.dot(g, c)) / norm2) * c
    return g


@dataclass
class SymplecticCGS:
    """
    Extension I: Symplectic / Poisson CGS-v1 (§3).

    State X = (q, p) in R^{2n}.
    H: R^{2n} -> R  (Hamiltonian).
    S: R^{2n} -> R^k  (tracking residual, controls energy E = S^T G S).

    Application: power grid  X = (delta, omega),  H = 1/2 omega^T M omega + sum Bij(1-cos(...))
    Prop 3.5 preserves slack-bus Casimir (sum delta_i = const) exactly.
    """
    S_fn: Callable            # S(X) -> R^k
    J_fn: Callable            # dS/dX -> R^{k x 2n}
    G: np.ndarray             # k×k SPD metric
    H_fn: Callable            # Hamiltonian H(X)
    gradH_fn: Callable        # nabla H(X) -> R^{2n}
    Fbase_fn: Callable        # nominal vector field (e.g. X_H + load disturbance)
    theta: float = 1.0
    casimir_grads_fn: Optional[Callable] = None  # returns list of Casimir gradients at X

    def g_star(self, X: np.ndarray) -> np.ndarray:
        S = self.S_fn(X)
        Jac = self.J_fn(X)
        grad_E = 2.0 * Jac.T @ (self.G @ S)
        grad_H = self.gradH_fn(X)
        g = symplectic_projection(grad_E, grad_H)
        if self.casimir_grads_fn is not None:
            g = poisson_projection(g, self.casimir_grads_fn(X))
        return g

    def energy(self, X: np.ndarray) -> float:
        S = self.S_fn(X)
        return float(S @ self.G @ S)

    def rhs(self, X: np.ndarray) -> np.ndarray:
        return universal_rhs(self.Fbase_fn(X), self.g_star(X),
                             self.energy(X), self.theta)

    def step_rk4(self, X: np.ndarray, h: float = 0.01) -> np.ndarray:
        return rk4_step(X, self.rhs, h)

    def integrate(self, X0: np.ndarray, steps: int, h: float = 0.01,
                  method: str = "rk4") -> np.ndarray:
        return integrate_trajectory(X0, self.rhs, steps, h, method)

    def hamiltonian_drift(self, traj: np.ndarray) -> np.ndarray:
        """Verify Theorem 3.1: H_dot ≈ 0 along trajectory."""
        return np.array([self.H_fn(traj[k + 1]) - self.H_fn(traj[k])
                         for k in range(len(traj) - 1)])


# ============================================================
# SECTION 9: EXTENSION II — LIE GROUPS  (§4 CGS-v1)
# ============================================================

def _hat_so3(omega: np.ndarray) -> np.ndarray:
    """Hat map: R^3 -> so(3) skew-symmetric matrix."""
    return np.array([[ 0.0,       -omega[2],  omega[1]],
                     [ omega[2],   0.0,       -omega[0]],
                     [-omega[1],   omega[0],   0.0]])


def _rodrigues(omega: np.ndarray) -> np.ndarray:
    """Rodrigues formula: exp(hat(omega)) in SO(3)."""
    angle = float(np.linalg.norm(omega))
    if angle < EPS:
        return np.eye(3) + _hat_so3(omega)   # first-order
    K = _hat_so3(omega / angle)
    return np.eye(3) + np.sin(angle) * K + (1.0 - np.cos(angle)) * (K @ K)


def lie_group_retract(X: np.ndarray, xi: np.ndarray, h: float) -> np.ndarray:
    """
    Definition 4.5: X_{t+h} = X · exp(h * xi).
    X: n×n matrix Lie group element.
    xi: Lie algebra element — length-3 vector for SO(3) (uses Rodrigues),
        or (n*n,) flat vector for general GL(n) (uses matrix expm).
    Theorem 4.2: solutions remain in G for all t >= 0.
    """
    n = X.shape[0]
    if X.shape == (3, 3) and xi.shape == (3,):
        return X @ _rodrigues(h * xi)
    xi_mat = (h * xi).reshape(n, n)
    return X @ _matrix_exp(xi_mat)


@dataclass
class LieGroupCGS:
    """
    Extension II: Lie Group CGS-v1 (§4).
    X in G (n×n matrix Lie group, e.g. SO(3), SE(3), GL(n)).

    Definition 4.1:
        g_g = 2 Jhat* G S
        Xdot = X (xi_nom - g_g - gamma * <xi_nom - g_g, g_g>_g / ||g_g||_g^2 * g_g)

    Application: drone attitude  X=R in SO(3), S(R) = log(R^T R_target), G=I3.
    Theorem 4.3: Lyapunov descent on G.
    Theorem 4.4: local exponential convergence with O(K0*r^2) curvature correction.
    """
    S_fn: Callable        # S(X) -> R^k  (k-dim residual)
    J_hat_fn: Callable    # lifted Jacobian Jhat(X): g -> R^k  (k x dim_g matrix)
    G: np.ndarray         # k×k SPD metric
    xi_nom_fn: Callable   # xi_nom(X) -> element of g (flat vector, length dim_g)
    theta: float = 1.0
    metric_g: Optional[np.ndarray] = None  # inner product on g; None = Euclidean

    def _Mg(self, dim: int) -> np.ndarray:
        return self.metric_g if self.metric_g is not None else np.eye(dim)

    def g_g(self, X: np.ndarray) -> np.ndarray:
        """Definition 4.1: g_g = 2 Jhat*(X) G S(X)."""
        S = self.S_fn(X)
        Jhat = self.J_hat_fn(X)   # shape (k, dim_g)
        return 2.0 * Jhat.T @ (self.G @ S)

    def energy(self, X: np.ndarray) -> float:
        S = self.S_fn(X)
        return float(S @ self.G @ S)

    def xi_rhs(self, X: np.ndarray) -> np.ndarray:
        """Lie-algebra element driving the retracted integrator."""
        gg = self.g_g(X)
        xi_n = self.xi_nom_fn(X)
        Mg = self._Mg(len(gg))
        gg_norm2 = float(gg @ Mg @ gg) + EPS
        alpha = (float(xi_n @ Mg @ gg) - float(gg @ Mg @ gg)) / gg_norm2
        E = self.energy(X)
        gamma = E / (E + self.theta + EPS)
        return xi_n - gg - gamma * alpha * gg

    def step(self, X: np.ndarray, h: float = 0.01) -> np.ndarray:
        """Retracted integrator: X_{t+h} = X · exp(h * xi_t)."""
        xi = self.xi_rhs(X)
        return lie_group_retract(X, xi, h)

    def integrate(self, X0: np.ndarray, steps: int, h: float = 0.01) -> list:
        """Returns list of (steps+1) matrices."""
        traj = [X0.copy()]
        X = X0.copy()
        for _ in range(steps):
            X = self.step(X, h)
            traj.append(X.copy())
        return traj


# ============================================================
# SECTION 10: EXTENSION III — PARETO / MGDA  (§5 CGS-v1)
# ============================================================

def mgda_weights_m2(g1: np.ndarray, g2: np.ndarray) -> np.ndarray:
    """
    Closed-form MGDA solution for m=2 (§5.3 footnote).
    lambda1 = (||g2||^2 - <g1,g2>) / (||g1||^2 + ||g2||^2 - 2<g1,g2>).
    """
    n1sq = float(np.dot(g1, g1))
    n2sq = float(np.dot(g2, g2))
    dot12 = float(np.dot(g1, g2))
    denom = n1sq + n2sq - 2.0 * dot12 + EPS
    lam1 = float(np.clip((n2sq - dot12) / denom, 0.0, 1.0))
    return np.array([lam1, 1.0 - lam1])


def mgda_frank_wolfe(grads: List[np.ndarray],
                     max_iter: int = 100,
                     tol: float = 1e-9) -> np.ndarray:
    """
    Definition 5.1: Frank-Wolfe algorithm for MGDA minimum-norm point.
    Computes lambda* = argmin_{lambda in Delta} || sum_i lambda_i g_i ||^2.
    Theorem 5.2: if gbar != 0 then <nabla E_i, -gbar> < 0 for all i in supp(lambda*).
    """
    m = len(grads)
    Gmat = np.array([[float(np.dot(gi, gj)) for gj in grads] for gi in grads])
    lam = np.ones(m) / m
    for _ in range(max_iter):
        grad_lam = Gmat @ lam
        i_min = int(np.argmin(grad_lam))
        e_i = np.zeros(m)
        e_i[i_min] = 1.0
        fw_dir = e_i - lam
        step_num = float(np.dot(grad_lam, fw_dir))
        step_denom = float(fw_dir @ Gmat @ fw_dir) + EPS
        step = float(np.clip(-step_num / step_denom, 0.0, 1.0))
        lam = lam + step * fw_dir
        lam = np.maximum(lam, 0.0)
        lam /= lam.sum() + EPS
        if abs(step) * float(np.linalg.norm(fw_dir)) < tol:
            break
    return lam


@dataclass
class ParetoCGS:
    """
    Extension III: Multi-Objective Pareto CGS-v1 (§5).

    Each system dict: {"S_fn": callable, "J_fn": callable, "G": ndarray}
    Aggregate gradient gbar = sum lambda*_i g^(i)_X  (MGDA minimum-norm).

    Theorem 5.2 (corrected): strict descent on supp(lambda*) under angle condition.
    Theorem 5.3: convergence to Pareto stationary set {X: gbar(X) = 0}.
    Theorem 5.5 (Pareto sliding): once X in P, Xdot = Fbase (forward-invariant).

    Application: portfolio (profit vs variance), robotics (task vs obstacle avoidance).
    """
    systems: List[Dict]   # list of {"S_fn", "J_fn", "G"} dicts
    Fbase_fn: Callable
    theta: float = 1.0

    def compute_grads(self, X: np.ndarray) -> Tuple[List[np.ndarray], List[float]]:
        grads, energies = [], []
        for sys in self.systems:
            S = sys["S_fn"](X)
            Jac = sys["J_fn"](X)
            G = sys["G"]
            grads.append(2.0 * Jac.T @ (G @ S))
            energies.append(float(S @ G @ S))
        return grads, energies

    def aggregate(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
        """Returns (g_bar, lambda_star, E_bar)."""
        grads, energies = self.compute_grads(X)
        m = len(grads)
        lam = mgda_weights_m2(grads[0], grads[1]) if m == 2 \
              else mgda_frank_wolfe(grads)
        g_bar = sum(lam[i] * grads[i] for i in range(m))
        E_bar = float(sum(lam[i] * energies[i] for i in range(m)))
        return g_bar, lam, E_bar

    def rhs(self, X: np.ndarray) -> np.ndarray:
        g_bar, _, E_bar = self.aggregate(X)
        return universal_rhs(self.Fbase_fn(X), g_bar, E_bar, self.theta)

    def step_rk4(self, X: np.ndarray, h: float = 0.01) -> np.ndarray:
        return rk4_step(X, self.rhs, h)

    def integrate(self, X0: np.ndarray, steps: int, h: float = 0.01) -> np.ndarray:
        return integrate_trajectory(X0, self.rhs, steps, h, "rk4")


# ============================================================
# SECTION 11: EXTENSION IV — GRAPH / DIFFUSION WAVELET  (§6 CGS-v1)
# ============================================================

def diffusion_wavelet_filters(L: np.ndarray,
                               scales: np.ndarray) -> List[np.ndarray]:
    """
    Definition 6.2 (filter computation).
    Psi_l = exp(-t_l L) - exp(-t_{l+1} L).
    Returns L_bands N×N filter matrices.
    Lemma 6.3: lambda_min(L_ms restricted to 1-perp) >= c_spec > 0
    when t0 <= 1/lambda_N  and  tL >= 1/lambda_2.
    """
    H_prev = _matrix_exp(-float(scales[0]) * L)
    filters: List[np.ndarray] = []
    for t_next in scales[1:]:
        H_next = _matrix_exp(-float(t_next) * L)
        filters.append(H_prev - H_next)
        H_prev = H_next
    return filters


def graph_feature_map(X_dev: np.ndarray,
                       filters: List[np.ndarray],
                       scales: np.ndarray,
                       d_eff: float = 1.0) -> Tuple[np.ndarray, np.ndarray]:
    """
    Definition 6.2: S_graph = (Psi_0(X-X*), ..., Psi_L(X-X*)) stacked.
    G_graph = diag(t_l^{-d_eff} I_N, ...) — diagonal, returned as weight vector.
    """
    N = X_dev.shape[0]
    parts = [psi @ X_dev for psi in filters]
    S_graph = np.concatenate(parts)
    g_weights = np.concatenate([
        float(scales[l]) ** (-d_eff) * np.ones(N)
        for l in range(len(filters))
    ])
    return S_graph, g_weights


def spectral_coercivity_constant(L: np.ndarray, scales: np.ndarray,
                                  d_eff: float = 1.0) -> float:
    """
    Lemma 6.3: c_spec = t0^{-d_eff} * (1 - exp(-1))^2 / L_bands^2.
    Lower bound on lambda_min(L_ms | 1-perp) for well-separated scales.
    """
    L_bands = len(scales) - 1
    t0 = float(scales[0])
    return float(t0 ** (-d_eff)) * (1.0 - np.exp(-1.0)) ** 2 / (L_bands ** 2 + EPS)


@dataclass
class GraphWaveletCGS:
    """
    Extension IV: Graph / Fractal CGS-v1 (§6).

    L:  N×N graph Laplacian (symmetric, PSD).
    X in R^N: node states.
    scales: array [t_0, t_1, ..., t_L] for the diffusion heat kernel.
    d_eff: effective scaling dimension (design parameter, not topological invariant).

    Theorem 6.4: exponential convergence on 1-perp with rate rho_graph = 4*c_spec*(1-gamma_max).
    Theorem 6.5: total energy descent under angle condition; per-scale requires orthogonality.
    Application: water network (pressure regulation) + grid topology.
    """
    L: np.ndarray
    scales: np.ndarray      # shape (L_bands+1,)
    X_star: np.ndarray      # target node state
    d_eff: float = 1.0
    theta: float = 1.0
    Fbase: Optional[np.ndarray] = None   # constant (N,) or None -> zero

    def __post_init__(self) -> None:
        self._filters = diffusion_wavelet_filters(self.L, self.scales)
        self._c_spec = spectral_coercivity_constant(self.L, self.scales, self.d_eff)

    def compute(self, X: np.ndarray) -> Tuple[np.ndarray, float]:
        """Returns (g_X in R^N, E_graph)."""
        X_dev = X - self.X_star
        N = X_dev.shape[0]
        E = 0.0
        gX = np.zeros(N)
        for l, psi in enumerate(self._filters):
            w = float(self.scales[l]) ** (-self.d_eff)
            psi_dev = psi @ X_dev
            E += w * float(np.dot(psi_dev, psi_dev))
            gX += 2.0 * w * psi.T @ psi_dev
        return gX, E

    def rhs(self, X: np.ndarray) -> np.ndarray:
        gX, E = self.compute(X)
        Fb = self.Fbase if self.Fbase is not None else np.zeros_like(X)
        return universal_rhs(Fb, gX, E, self.theta)

    def step_rk4(self, X: np.ndarray, h: float = 0.01) -> np.ndarray:
        return rk4_step(X, self.rhs, h)

    def integrate(self, X0: np.ndarray, steps: int, h: float = 0.01) -> np.ndarray:
        return integrate_trajectory(X0, self.rhs, steps, h, "rk4")

    def convergence_rate_bound(self, gamma_max: float) -> float:
        """Theorem 6.4: rho_graph = 4*c_spec*(1-gamma_max)."""
        return 4.0 * self._c_spec * (1.0 - gamma_max)


# ============================================================
# SECTION 12: EXTENSION V — KURTOSIS-CORRECTED SPD PRECONDITIONER  (§7)
# ============================================================

@dataclass
class KurtosisCGS:
    """
    Extension V: Kurtosis-corrected CGS-v1 (§7).

    G^(beta) = I_S(X) + beta * K4(X)   (Definition 7.1).
    Admissible beta: B = (-mu_I/L_K, mu_I/L_K)   (Theorem 7.2, Weyl's inequality).
    Theorem 7.3: Edot <= 0 for beta in B, under angle condition.
    Theorem 7.6 (isotropic kurtosis): rate rho(beta) strictly increasing in beta when c > 0.
    Application: portfolio under fat-tailed (elliptical) distributions.
    """
    S_fn: Callable
    J_fn: Callable
    I_S_fn: Callable          # Fisher information I_S(X) -> k×k
    K4_fn: Callable           # fourth-cumulant K4(X) -> k×k
    Fbase_fn: Callable
    theta: float = 1.0
    beta: float = 0.0

    def G_beta(self, X: np.ndarray) -> np.ndarray:
        """Definition 7.1: G^(beta) = I_S + beta * K4."""
        return self.I_S_fn(X) + self.beta * self.K4_fn(X)

    def beta_range(self, X: np.ndarray) -> Tuple[float, float]:
        """Theorem 7.2: admissible beta in (-mu_I/L_K, mu_I/L_K)."""
        I_S = self.I_S_fn(X)
        K4 = self.K4_fn(X)
        mu_I = float(np.linalg.eigvalsh(I_S).min())
        L_K = float(np.linalg.norm(K4, ord=2))
        if L_K < EPS:
            return float("-inf"), float("inf")
        span = mu_I / L_K
        return -span, span

    def energy(self, X: np.ndarray) -> float:
        S = self.S_fn(X)
        return float(S @ self.G_beta(X) @ S)

    def rhs(self, X: np.ndarray) -> np.ndarray:
        S = self.S_fn(X)
        Jac = self.J_fn(X)
        G = self.G_beta(X)
        gX = 2.0 * Jac.T @ (G @ S)
        E = float(S @ G @ S)
        return universal_rhs(self.Fbase_fn(X), gX, E, self.theta)

    def step_rk4(self, X: np.ndarray, h: float = 0.01) -> np.ndarray:
        return rk4_step(X, self.rhs, h)

    def integrate(self, X0: np.ndarray, steps: int, h: float = 0.01) -> np.ndarray:
        return integrate_trajectory(X0, self.rhs, steps, h, "rk4")

    def rate_derivative_sign(self, X: np.ndarray) -> float:
        """
        Theorem 7.6: sign of d rho/d beta = sign of c (Assumption 7.4).
        Returns c(X) under isotropy assumption K4 = c * I_S.
        """
        I_S = self.I_S_fn(X)
        K4 = self.K4_fn(X)
        if float(np.linalg.norm(I_S)) < EPS:
            return 0.0
        # c ~ trace(K4) / trace(I_S) under isotropy
        return float(np.trace(K4)) / (float(np.trace(I_S)) + EPS)


# ============================================================
# SECTION 13: EXTENSION VI — ROBUST / ADVERSARIAL DAMPING  (§8)
# ============================================================

def robust_gamma(E: float, g_norm: float, M_adv: float, theta: float) -> float:
    """
    Theorem 8.3: gamma_rob = (E + M_adv*||g||) / (E + M_adv*||g|| + theta).
    Implementable non-degenerate robust gain (Remark 8.2 avoids gamma -> 1- degeneracy).
    """
    num = E + M_adv * g_norm
    return num / (num + theta + EPS)


def worst_case_adversary(gX: np.ndarray, M_adv: float) -> np.ndarray:
    """
    Theorem 8.1: u* = M_adv * g_X / ||g_X||.
    Unique adversary maximising J(gamma, u) = Edot via Cauchy-Schwarz.
    """
    norm = float(np.linalg.norm(gX)) + EPS
    return M_adv * gX / norm


def robust_descent_region(gX: np.ndarray, Fnom: np.ndarray,
                           M_adv: float) -> bool:
    """
    Theorem 8.3: S_rob = {X: ||g_X||^2 >= <g_X, Fnom> + M_adv*||g_X||}.
    Returns True if X is in the robust descent region.
    """
    g_norm = float(np.linalg.norm(gX))
    dot_gF = float(np.dot(gX, Fnom))
    return g_norm ** 2 >= dot_gF + M_adv * g_norm


@dataclass
class RobustCGS:
    """
    Extension VI: Robust / Adversarial CGS-v1 (§8).

    Theorem 8.5: robust ultimate boundedness - trajectories entering {E <= R+} are
    ultimately bounded in [R-, R+] under two-sided gradient coercivity.
    Theorem 8.6: Fisher amplification — net-descent condition explicit in ||S|| and ||X-X*||.
    Application: drone under adversarial wind gusts.
    """
    S_fn: Callable
    J_fn: Callable
    G: np.ndarray
    Fnom_fn: Callable
    theta: float = 1.0
    M_adv: float = 0.0

    def _compute(self, X: np.ndarray) -> Tuple[np.ndarray, float, float]:
        S = self.S_fn(X)
        Jac = self.J_fn(X)
        gX = 2.0 * Jac.T @ (self.G @ S)
        E = float(S @ self.G @ S)
        g_norm = float(np.linalg.norm(gX)) + EPS
        return gX, E, g_norm

    def rhs(self, X: np.ndarray, use_worst_case: bool = False) -> np.ndarray:
        gX, E, g_norm = self._compute(X)
        gamma = robust_gamma(E, g_norm, self.M_adv, self.theta)
        Fnom = self.Fnom_fn(X)
        u = worst_case_adversary(gX, self.M_adv) if use_worst_case else np.zeros_like(gX)
        Fbase = Fnom + u
        g2 = g_norm ** 2
        alpha = float(np.dot(Fbase - gX, gX)) / (g2 + EPS)
        return Fbase - gX - gamma * alpha * gX

    def step_rk4(self, X: np.ndarray, h: float = 0.01,
                  use_worst_case: bool = False) -> np.ndarray:
        return rk4_step(X, lambda x: self.rhs(x, use_worst_case), h)

    def integrate(self, X0: np.ndarray, steps: int, h: float = 0.01,
                  use_worst_case: bool = False) -> np.ndarray:
        return integrate_trajectory(X0, lambda x: self.rhs(x, use_worst_case),
                                    steps, h, "rk4")

    def energy(self, X: np.ndarray) -> float:
        S = self.S_fn(X)
        return float(S @ self.G @ S)

    def gamma_rob_value(self, X: np.ndarray) -> float:
        _, E, g_norm = self._compute(X)
        return robust_gamma(E, g_norm, self.M_adv, self.theta)

    def ultimate_bound_roots(self, C1: float, C2: float,
                              M_nom: float) -> Tuple[float, float]:
        """
        Theorem 8.5: Psi_rob(R) = theta*C1*sqrt(R)/(R + M_adv*C2*sqrt(R)+theta) - M_adv.
        Returns (R-, R+) — ultimate energy bounds.  Returns (nan, nan) if inadmissible.
        C1 = 2*sigma*mu_G/sqrt(M_G),  C2 = 2*J_max*sqrt(M_G/mu_G).
        """
        theta = self.theta
        M_adv = self.M_adv

        def psi_rob_of_sqrtR(u: float) -> float:
            return theta * C1 * u / (u * u + M_adv * C2 * u + theta + EPS) - M_adv

        # Maximum at u = sqrt(theta), i.e. R = theta
        psi_star = psi_rob_of_sqrtR(np.sqrt(theta))
        if M_nom >= psi_star:
            return float("nan"), float("nan")
        # Bisect for the two roots
        u_vals = np.linspace(0.0, np.sqrt(theta) * 10, 5000)
        psi_vals = np.array([psi_rob_of_sqrtR(u) - M_nom for u in u_vals])
        sign_changes = np.where(np.diff(np.sign(psi_vals)))[0]
        if len(sign_changes) < 2:
            return float("nan"), float("nan")
        R_minus = float(u_vals[sign_changes[0]] ** 2)
        R_plus = float(u_vals[sign_changes[1]] ** 2)
        return R_minus, R_plus


# ============================================================
# SECTION 14: EXTENSION VII — DELAY / LK PREDICTOR  (§9)
# ============================================================

def lk_functional(E_t: float, g_norm2_hist: np.ndarray,
                   mu: float = 0.5, dt: float = 1.0) -> float:
    """
    Definition 9.1: V(X_t) = E(X(t)) + mu * int_{t-tau}^t ||g_X(s)||^2 ds.
    g_norm2_hist: array of ||g_X(s)||^2 values at discrete steps over [t-tau, t].
    """
    return E_t + mu * float(np.trapz(g_norm2_hist)) * dt


def smith_predictor_cheap(X_delayed: np.ndarray,
                           Fnom_hist: np.ndarray,
                           dt: float) -> np.ndarray:
    """
    Theorem 9.4: X_hat(t) = X(t-tau) + int_{t-tau}^t Fnom(X(s)) ds.
    O(tau) rate degradation.  Easy to implement.
    Fnom_hist: (tau_steps, n) array of Fnom values over the delay window.
    """
    return X_delayed + dt * Fnom_hist.sum(axis=0)


def smith_predictor_full(X_delayed: np.ndarray,
                          drift_hist: np.ndarray,
                          dt: float) -> np.ndarray:
    """
    Theorem 9.5: X_hat_full(t) = X(t-tau) + int full drift.
    O(tau^2) recovery.  Idealised — requires auxiliary observer (Remark 9.6).
    drift_hist: (tau_steps, n) array of full canonical drift at each delayed step.
    """
    return X_delayed + dt * drift_hist.sum(axis=0)


def delay_margin(gamma_max: float, rho_free: float, L_g: float) -> float:
    """
    Theorem 9.3: tau* = (1-gamma_max)*rho / L_g^2.  Sufficient only.
    L_g: Lipschitz constant of X -> g_X on operating set.
    """
    return (1.0 - gamma_max) * rho_free / (L_g ** 2 + EPS)


@dataclass
class DelayCGS:
    """
    Extension VII: Delayed Canonical CGS-v1 (§9).

    Delayed ODE: Xdot(t) = Fnom(X(t)) - gX(X(t-tau)) - gamma(X(t-tau))*alpha(t-tau)*gX(X(t-tau))
    LK functional: V = E(X(t)) + mu * int_{t-tau}^t ||gX(s)||^2 ds.
    Theorem 9.2: LK descent inequality under angle condition on [t-tau, t].
    Application: drone GPS dropout (cheap predictor O(tau), full predictor O(tau^2)).
    """
    S_fn: Callable
    J_fn: Callable
    G: np.ndarray
    Fnom_fn: Callable
    theta: float = 1.0
    tau_steps: int = 5       # delay tau in discrete steps
    mu_lk: float = 0.5       # LK functional weighting coefficient

    def _gX(self, X: np.ndarray) -> np.ndarray:
        S = self.S_fn(X)
        Jac = self.J_fn(X)
        return 2.0 * Jac.T @ (self.G @ S)

    def _energy(self, X: np.ndarray) -> float:
        S = self.S_fn(X)
        return float(S @ self.G @ S)

    def _canonical_drift(self, X_now: np.ndarray,
                          X_delayed: np.ndarray) -> np.ndarray:
        """Delayed ODE drift."""
        gX_d = self._gX(X_delayed)
        E_d = self._energy(X_delayed)
        g2 = float(np.dot(gX_d, gX_d)) + EPS
        Fnom_d = self.Fnom_fn(X_delayed)
        F_d = Fnom_d - gX_d
        alpha = float(np.dot(F_d, gX_d)) / g2
        gamma = E_d / (E_d + self.theta + EPS)
        return self.Fnom_fn(X_now) - (1.0 + gamma * alpha) * gX_d

    def integrate(self, X0: np.ndarray, steps: int, h: float = 0.01) -> np.ndarray:
        """
        Euler integration with circular history buffer for delay.
        Returns (steps+1, n) trajectory array.
        """
        n = X0.shape[0]
        buf_size = self.tau_steps + 1
        history = np.tile(X0, (buf_size, 1))  # circular buffer
        traj = np.empty((steps + 1, n))
        traj[0] = X0
        for k in range(steps):
            idx_now = k % buf_size
            idx_del = (k - self.tau_steps) % buf_size
            X_now = history[idx_now]
            X_delayed = history[idx_del]
            drift = self._canonical_drift(X_now, X_delayed)
            X_next = X_now + h * drift
            history[(k + 1) % buf_size] = X_next
            traj[k + 1] = X_next
        return traj

    def lk_value(self, traj: np.ndarray, t_idx: int,
                  h: float = 0.01) -> float:
        """Compute V(X_t) at index t_idx along a precomputed trajectory."""
        E_t = self._energy(traj[t_idx])
        start = max(0, t_idx - self.tau_steps)
        g_norm2 = np.array([float(np.dot(self._gX(traj[i]), self._gX(traj[i])))
                             for i in range(start, t_idx + 1)])
        return lk_functional(E_t, g_norm2, self.mu_lk, h)


# ============================================================
# SECTION 15: PORT-HAMILTONIAN MULTI-ENGINE COMPOSITION
# ============================================================

@dataclass
class PortHamiltonianCGS:
    """
    Port-Hamiltonian composition of multiple CGS-v1 engines.

    Combined flow:
        Xdot_all = (J_ph - R_ph) nabla E_total  +  sum individual corrections

    Power balance: sum_i <effort_i, flow_i> = -d(E_total)/dt.
    J_ph: skew-symmetric interconnection matrix (n_total x n_total).
    R_ph: PSD dissipation matrix (n_total x n_total).

    Each engine must implement .rhs(X_i) -> ndarray and .energy(X_i) -> float.
    All engines operate on equal-sized state slices (stride = n_total / n_engines).
    """
    engines: List              # each with .rhs(X) and .energy(X)
    J_ph: np.ndarray           # skew-symmetric (n_total x n_total)
    R_ph: np.ndarray           # PSD dissipation (n_total x n_total)
    effort_fn: Callable        # effort_fn(X_all, energies) -> nabla E_total (n_total,)

    def rhs(self, X_all: np.ndarray) -> np.ndarray:
        n_total = X_all.shape[0]
        m = len(self.engines)
        stride = n_total // m
        individual = np.zeros(n_total)
        energies: List[float] = []
        for i, eng in enumerate(self.engines):
            sl = slice(i * stride, (i + 1) * stride)
            individual[sl] = eng.rhs(X_all[sl])
            energies.append(eng.energy(X_all[sl]))
        effort = self.effort_fn(X_all, energies)
        ph_term = (self.J_ph - self.R_ph) @ effort
        return individual + ph_term

    def step_rk4(self, X_all: np.ndarray, h: float = 0.01) -> np.ndarray:
        return rk4_step(X_all, self.rhs, h)

    def integrate(self, X0: np.ndarray, steps: int, h: float = 0.01) -> np.ndarray:
        return integrate_trajectory(X0, self.rhs, steps, h, "rk4")

    def total_energy(self, X_all: np.ndarray) -> float:
        m = len(self.engines)
        n_total = X_all.shape[0]
        stride = n_total // m
        return sum(eng.energy(X_all[i * stride:(i + 1) * stride])
                   for i, eng in enumerate(self.engines))


# ============================================================
# SECTION 16: COLLAPSE HORIZON + SPECTRAL PROXY
# ============================================================

def collapse_horizon(E: float, Edot: float, E_threshold: float) -> float:
    """
    Closed-form linear collapse-time estimate:
        t* = (E_threshold - E) / Edot

    Early-warning interpretation:
      - Edot > 0 (rising E): t* = time until alarm threshold is reached.
      - Edot <= 0 (falling E): returns inf (no alarm predicted).
      - E > E_threshold already: returns 0 (alarm active).
    """
    if E >= E_threshold:
        return 0.0
    if Edot <= 0.0:
        return float("inf")
    return (E_threshold - E) / Edot


def spectral_proxy(gX: np.ndarray, E: float, theta: float) -> float:
    """
    Local convergence rate proxy: rho_proxy = (1-gamma) * ||g_X||^2 / E.
    Approximates the exponential decay rate from Theorem 9.3 (CEK-v4).
    """
    g2 = float(np.dot(gX, gX))
    gamma = E / (E + theta + EPS)
    return (1.0 - gamma) * g2 / (E + EPS)


def spectral_alarm_horizon_series(E_series: np.ndarray,
                                   Edot_series: np.ndarray,
                                   threshold: float) -> np.ndarray:
    """
    Vectorised collapse_horizon over a time series.
    Returns array of predicted steps-to-threshold at each t.
    """
    horizons = np.full_like(E_series, float("inf"))
    above = E_series >= threshold
    rising = (~above) & (Edot_series > 0.0)
    horizons[above] = 0.0
    horizons[rising] = (threshold - E_series[rising]) / (Edot_series[rising] + EPS)
    return horizons


# ============================================================
# SECTION 17: CONVENIENCE: BATCH EVALUATOR (backward-compat with CEK-v4)
# ============================================================

def evaluate_cgs_v1_batch(X_series: np.ndarray,
                           S_fn: Callable,
                           J_fn: Callable,
                           G: np.ndarray,
                           Fbase_fn: Callable,
                           theta: float,
                           projection: str = "euclidean",
                           projection_kwargs: Optional[Dict] = None) -> Dict[str, np.ndarray]:
    """
    Batch evaluation of CGS-v1 flow over a time series X_series (T x n).

    projection: "euclidean" | "symplectic" | "pareto" | "identity"
    Returns dict with keys: E, g_norm, Edot, gamma, alpha, g_star_norm,
                            rho_proxy, collapse_steps, delta_C, delta_A.
    """
    T = X_series.shape[0]
    kwargs = projection_kwargs or {}

    E_arr = np.empty(T)
    g_norm_arr = np.empty(T)
    Edot_arr = np.empty(T)
    gamma_arr = np.empty(T)
    alpha_arr = np.empty(T)
    g_star_norm_arr = np.empty(T)
    rho_arr = np.empty(T)

    for t in range(T):
        X = X_series[t]
        S = S_fn(X)
        Jac = J_fn(X)
        grad_E = 2.0 * Jac.T @ (G @ S)
        E = float(S @ G @ S)

        if projection == "symplectic":
            grad_H = kwargs["gradH_fn"](X)
            g_star = symplectic_projection(grad_E, grad_H)
            if "casimir_grads_fn" in kwargs:
                g_star = poisson_projection(g_star, kwargs["casimir_grads_fn"](X))
        else:
            g_star = grad_E.copy()

        Fb = Fbase_fn(X)
        g2 = float(np.dot(g_star, g_star)) + EPS
        alpha = float(np.dot(Fb - g_star, g_star)) / g2
        gamma = E / (E + theta + EPS)
        Xdot = Fb - g_star - gamma * alpha * g_star
        Edot = float(np.dot(grad_E, Xdot))

        E_arr[t] = E
        g_norm_arr[t] = float(np.linalg.norm(grad_E))
        Edot_arr[t] = Edot
        gamma_arr[t] = gamma
        alpha_arr[t] = alpha
        g_star_norm_arr[t] = float(np.linalg.norm(g_star))
        rho_arr[t] = spectral_proxy(g_star, E, theta)

    # collapse horizon over series (threshold = 2*sigma alarm)
    mu_E = float(np.mean(E_arr))
    sig_E = float(np.std(E_arr)) + EPS
    threshold = mu_E + 2.0 * sig_E
    collapse_steps = spectral_alarm_horizon_series(E_arr, Edot_arr, threshold)

    return dict(
        E=E_arr,
        g_norm=g_norm_arr,
        Edot=Edot_arr,
        gamma=gamma_arr,
        alpha=alpha_arr,
        g_star_norm=g_star_norm_arr,
        rho_proxy=rho_arr,
        collapse_steps=collapse_steps,
        threshold=threshold,
        alarms=E_arr > threshold,
        delta_C=np.abs(gamma_arr * alpha_arr) * g_star_norm_arr,
        delta_A=g_norm_arr,
    )


# ============================================================
# SECTION 18: CORRECTED STABILITY THEORY
# (math_reference_corrected.pdf §XXX — Theorems 1, 2, 3 + Metastability Proposition)
# ============================================================

def attenuation_factor(E: float, theta: float) -> float:
    """
    math_reference §XXX Theorem 1 (Energy Attenuation Identity) — factor g(E).

    g(E) = theta / (E + theta)

    g(0) = 1  (no energy → full nominal drift).
    g(E) → 0 as E → ∞  (heavy energy level suppresses controlled drift).
    g is strictly decreasing and Lipschitz with constant 1/theta.
    """
    return float(theta) / (float(E) + float(theta) + EPS)


def energy_attenuation_identity(gX: np.ndarray,
                                 Fbase: np.ndarray,
                                 E: float,
                                 theta: float) -> Tuple[float, float, float]:
    """
    math_reference §XXX Theorem 1 — full Energy Attenuation Identity.

    Ė_uncontrolled = ⟨gX, Fbase⟩
    Ė_controlled   = g(E) · Ė_uncontrolled     where g(E) = θ/(E+θ)

    The CGS-v1 controller attenuates the nominal energy drift by factor g(E),
    which is always ≤ 1.  When Ė_uncontrolled ≤ 0 the controller preserves
    descent monotonically.

    Returns (Edot_uncontrolled, g_E, Edot_controlled).
    """
    Edot_unc = float(np.dot(gX, Fbase))
    g_E = attenuation_factor(E, theta)
    return Edot_unc, g_E, g_E * Edot_unc


def restoring_condition_check(gX: np.ndarray,
                               Fbase: np.ndarray,
                               eta: float = 0.0) -> bool:
    """
    math_reference §XXX Theorem 2 (Conditional Stability) — Restoring Condition (RC).

    RC: ⟨gX, Fbase⟩ ≤ η · ‖gX‖²   where η ∈ [0, 1).

    When RC holds on the sublevel set Ω_c = {X : E(X) ≤ c}, that set is
    forward-invariant under the controlled CGS-v1 flow.

    eta = 0  (default): strict RC (nominal drift is not aligned with gradient).
    eta > 0: relaxed RC permitting mild positive alignment.

    Returns True if RC is satisfied (system is stable in this sublevel set).
    """
    lhs = float(np.dot(gX, Fbase))
    rhs = eta * float(np.dot(gX, gX))
    return lhs <= rhs


def lasalle_omega(E_series: np.ndarray,
                  Edot_series: np.ndarray,
                  threshold: float) -> np.ndarray:
    """
    math_reference §XXX Theorem 3 (LaSalle Convergence).

    Theoretical statement: X(t) → M ⊆ S ∩ Ω_c  as t → ∞,
    where S = {X : Ė(X) = 0}  (set of zero energy-derivative states),
    and   Ω_c = {E ≤ threshold}  (sublevel set).

    Practical proxy: returns Boolean mask of timesteps estimated to lie in
    S ∩ Ω_c — i.e. |Ė| ≤ tol  AND  E ≤ threshold.

    The tolerance is set adaptively as 1% of the std-dev of Edot_series.
    """
    tol = float(np.std(Edot_series)) * 0.01 + EPS
    return (np.abs(Edot_series) <= tol) & (E_series <= threshold)


def metastability_bound(E: float, theta: float, eps0: float) -> float:
    """
    math_reference §XXX Metastability Proposition.

    If ‖⟨∇E, F⟩‖ ≤ ε₀  (slow manifold / near-critical regime)
    then  ‖Ė‖ ≤ g(E) · ε₀  where g(E) = θ/(E+θ).

    The attenuation factor g(E) strictly reduces the worst-case drift rate
    in proportion to the current energy level.  Even in the metastable regime,
    heavy energy suppresses further energy growth.

    Returns the upper bound on |Ė| in the metastable regime.
    """
    return attenuation_factor(E, theta) * float(eps0)


# ============================================================
# SECTION 19: COVARIANCE + NETWORK PRIMITIVES
# (math_reference_corrected.pdf §II–§V — Ledoit-Wolf, spectral radius,
#  erf-log potential, Gershgorin Hessian bound)
# ============================================================

def ledoit_wolf_shrinkage(S: np.ndarray,
                           T: np.ndarray) -> Tuple[float, np.ndarray]:
    """
    math_reference §II — Ledoit-Wolf analytical shrinkage covariance (2004).

    S: (p×p) sample covariance matrix.
    T: (p×p) shrinkage target (e.g. T = (tr(S)/p)·I for equal-eigenvalue target).

    Analytical oracle formula:
        μ    = tr(S)/p
        ρ*   = clip( ‖S − μI‖_F² / (p · ‖S − T‖_F²),  0, 1 )
        Σ̂   = (1 − ρ*)·S + ρ*·T

    Shrinks toward T to reduce estimation error when p/n is not negligible.
    Returns (rho_star, Sigma_hat).
    """
    p = S.shape[0]
    mu = np.trace(S) / p
    diff = S - T
    denom = float(np.sum(diff ** 2))
    if denom < EPS:
        return 0.0, S.copy()
    num = float(np.sum((S - mu * np.eye(p)) ** 2)) / p
    rho = float(np.clip(num / (denom + EPS), 0.0, 1.0))
    return rho, (1.0 - rho) * S + rho * T


def network_spectral_radius(W: np.ndarray) -> float:
    """
    math_reference §II — Systemic contagion spectral radius.

    ρ(W) = λmax(|W|) = max_i |λi(W)|

    W: (N×N) symmetric weight / correlation matrix (off-diagonal entries).
    ρ(W) > 1 → unstable contagion regime (shock amplification).
    ρ(W) < 1 → stable contagion regime (shock attenuation).
    """
    return float(np.max(np.abs(np.linalg.eigvalsh(W))))


def spectral_radius_proxy(W_bar_off: float, N: int) -> Tuple[float, bool]:
    """
    math_reference §II — Closed-form spectral-radius proxy.

    ρ̃ = 1 + (N − 1) · W̄_off
    where W̄_off = mean of all off-diagonal entries of W.

    Contagion threshold: ρ̃ > N/2  (majority contagion dominates).

    W_bar_off: scalar mean off-diagonal weight.
    N:         number of nodes.
    Returns (rho_tilde, contagion_alarm).
    """
    rho_tilde = 1.0 + (N - 1) * float(W_bar_off)
    return rho_tilde, rho_tilde > N / 2.0


def erf_log_force_matrix(X: np.ndarray,
                          mu: np.ndarray,
                          alpha: float,
                          gamma_erf: float,
                          sigma_erf: float,
                          lmbda: float) -> Tuple[np.ndarray, np.ndarray]:
    """
    math_reference §III–§IV — Erf-log pairwise potential (closed-form force).

    K_ij  = γ · (2/√π) · exp(−D²_ij / σ²)  −  λ / D_ij    (i ≠ j, D_ij > 0)
    L     = diag(K·1) − K                   (graph Laplacian of K)
    F_mat = −α(X − 1·μᵀ) − L·X             (total force matrix, shape N×n)

    X:         (N, n) node state matrix — N nodes, n-dimensional embedding.
    mu:        (n,) equilibrium / rest position.
    alpha:     harmonic attraction coefficient.
    gamma_erf: erf-kernel strength coefficient.
    sigma_erf: length scale of erf kernel.
    lmbda:     log-repulsion strength.

    Returns (F_mat, K) where F_mat is (N×n) force and K is (N×N) interaction.
    """
    N = X.shape[0]
    diff = X[:, np.newaxis, :] - X[np.newaxis, :, :]   # N×N×n
    D2 = np.sum(diff ** 2, axis=-1)                     # N×N
    D = np.sqrt(D2 + EPS)
    K = np.zeros((N, N))
    for i in range(N):
        for j in range(N):
            if i != j:
                K[i, j] = (gamma_erf * (2.0 / np.sqrt(np.pi))
                            * np.exp(-D2[i, j] / (sigma_erf ** 2 + EPS))
                            - lmbda / D[i, j])
    L = np.diag(K @ np.ones(N)) - K
    F_mat = -alpha * (X - np.ones((N, 1)) @ mu[np.newaxis, :]) - L @ X
    return F_mat, K


def gershgorin_hessian_bound(K: np.ndarray, alpha: float) -> float:
    """
    math_reference §V — Gershgorin upper bound on λmax(∇²Φ).

    ∇²Φ = α·I + (∂K/∂r-dependent terms)
    Gershgorin circle theorem gives:
        λmax(∇²Φ) ≤ α + max_i Σ_{j≠i} |K_ij|

    K:     (N×N) interaction matrix from erf_log_force_matrix.
    alpha: harmonic coefficient (diagonal contribution).
    Returns the scalar upper bound on the spectral radius of the Hessian.
    """
    N = K.shape[0]
    off_diag_sums = np.array([np.sum(np.abs(K[i])) - np.abs(K[i, i])
                               for i in range(N)])
    return float(alpha + np.max(off_diag_sums))


# ============================================================
# SECTION 20: CEK-V4 STRUCTURAL LEMMAS
# (canonicaldocument_pdf.pdf — Lemma 7.7, Thm 9.6, Props 7.1/7.5/7.6,
#  Corollaries 10.1–10.4)
# ============================================================

def energy_derivative_lemma77(gX: np.ndarray,
                               Fbase: np.ndarray,
                               E: float,
                               theta: float) -> float:
    """
    canonicaldocument Lemma 7.7 — Master energy-derivative identity.

    Ė = (1 − γ) · [⟨gX, Fbase⟩ − ‖gX‖²]

    This identity holds in the Euclidean (no extra projection) case,
    i.e. when g* = gX.  It is used in the proofs of Theorems 9.1–9.6.

    Note: for Ė ≤ 0 we need ⟨gX, Fbase⟩ ≤ ‖gX‖², i.e. RC with η < 1;
    γ ∈ (0,1) so the factor (1−γ) is always positive.
    """
    gamma = E / (E + theta + EPS)
    return (1.0 - gamma) * (float(np.dot(gX, Fbase)) - float(np.dot(gX, gX)))


def z2_symmetry_check(S_fn: Callable,
                       X: np.ndarray,
                       X_sharp: np.ndarray,
                       tol: float = 1e-8) -> bool:
    """
    canonicaldocument Theorem 9.6 — Z2 symmetry (involutive lift).

    S(X♯) = −S(X)  ⟹  E(X♯) = ‖S(X♯)‖² = ‖S(X)‖² = E(X).

    X♯ is the involutive lift (e.g. negation X♯ = −X for mean-reverting S,
    or transpose conjugate for matrix-valued states).

    Consequence: the energy landscape has Z2 symmetry about the critical
    manifold; both X and X♯ are at the same energy level.

    Returns True if ‖S(X♯) + S(X)‖ ≤ tol  (symmetry confirmed numerically).
    """
    return bool(np.allclose(S_fn(X_sharp), -S_fn(X), atol=tol))


def hessian_energy(J: np.ndarray,
                    G: np.ndarray,
                    K_S: np.ndarray) -> np.ndarray:
    """
    canonicaldocument Proposition 7.1 — State-space Hessian of E.

    ∇²_X E = 2 Jᵀ (G + K_S) J

    J:   (k × n) Jacobian dS/dX.
    G:   (k × k) SPD metric tensor.
    K_S: (k × k) curvature correction ∂²S/∂X² · S  (symmetric for smooth S).

    Returns the (n × n) Hessian matrix of E at the current X.
    """
    return 2.0 * J.T @ (G + K_S) @ J


def critical_manifold_condition(gX: np.ndarray,
                                 Fbase: np.ndarray) -> Tuple[float, bool]:
    """
    canonicaldocument Proposition 7.5 — Critical manifold characterisation.

    C_man = {X : ⟨gX, Fbase⟩ = ‖gX‖²}  is an (n−1)-dimensional
    submanifold of R^n (implicit function theorem, ∇φ = gX − Fbase ≠ 0).

    Returns (residual, is_critical) where:
        residual    = ⟨gX, Fbase⟩ − ‖gX‖²
        is_critical = True iff |residual| < 1e-6 · (‖gX‖² + 1)
    """
    inner = float(np.dot(gX, Fbase))
    gX2 = float(np.dot(gX, gX))
    residual = inner - gX2
    is_crit = abs(residual) < 1e-6 * (gX2 + 1.0)
    return residual, is_crit


def curvature_bound(J: np.ndarray,
                     G: np.ndarray,
                     kappa_S: float) -> float:
    """
    canonicaldocument Proposition 7.6 — Curvature bound on ‖∇²E‖_op.

    ‖∇²E‖_op ≤ 2 · ‖J‖_op² · (λmax(G) + κ_S)

    where:
        ‖J‖_op  = σmax(J)  (largest singular value of J)
        λmax(G) = largest eigenvalue of metric G
        κ_S     = ‖K_S‖_op  (Lipschitz constant of the curvature correction)

    Returns the operator-norm upper bound.
    """
    sig_max_J = float(np.linalg.norm(J, ord=2))
    lam_max_G = float(np.linalg.eigvalsh(G).max())
    return 2.0 * sig_max_J ** 2 * (lam_max_G + kappa_S)


# ---- Corollaries 10.1–10.4: domain instantiations ----

def corollary_10_1_futures_S(price: float,
                              fair_value: float,
                              spread_cost: float) -> Tuple[float, float]:
    """
    canonicaldocument Corollary 10.1 — Futures / spot-price tracking.

    S = (price − fair_value) / spread_cost   (dimensionless tracking residual)
    E = S²

    Equilibrium at S = 0: price = fair_value.
    CGS-v1 drives the spread toward zero at rate controlled by θ.
    Returns (S, E).
    """
    S = (price - fair_value) / (spread_cost + EPS)
    return S, S ** 2


def corollary_10_2_options_S(delta: float,
                              delta_target: float,
                              vega: float) -> Tuple[float, float]:
    """
    canonicaldocument Corollary 10.2 — Options delta hedging.

    S = (delta − delta_target) / vega   (vega-normalised hedge residual)
    E = S²

    Equilibrium at S = 0: delta-neutral portfolio.
    Returns (S, E).
    """
    S = (delta - delta_target) / (vega + EPS)
    return S, S ** 2


def corollary_10_3_robotics_S(q: np.ndarray,
                               q_target: np.ndarray,
                               J_rob: np.ndarray,
                               G_rob: np.ndarray) -> Tuple[np.ndarray, float]:
    """
    canonicaldocument Corollary 10.3 — Robotic task-space tracking.

    S = J_rob (q − q_target)  (task-space residual vector, shape k)
    E = Sᵀ G_rob S             (weighted task-space energy)

    J_rob: (k × n) task Jacobian.
    G_rob: (k × k) task-space metric (e.g. I_k).
    Returns (S, E).
    """
    S = J_rob @ (q - q_target)
    return S, float(S @ G_rob @ S)


def corollary_10_4_contact_S(f_contact: np.ndarray,
                               f_desired: np.ndarray,
                               K_contact: np.ndarray) -> Tuple[np.ndarray, float]:
    """
    canonicaldocument Corollary 10.4 — Contact mechanics force regulation.

    S = K_contact^{−1/2} (f_contact − f_desired)   (compliance-normalised)
    E = ‖S‖²

    K_contact: (k × k) SPD contact-stiffness matrix.
    Returns (S, E).
    """
    eigvals, eigvecs = np.linalg.eigh(K_contact)
    K_inv_sqrt = eigvecs @ np.diag(1.0 / np.sqrt(np.maximum(eigvals, EPS))) @ eigvecs.T
    S = K_inv_sqrt @ (f_contact - f_desired)
    return S, float(S @ S)


# ============================================================
# SECTION 21: BSDT DERIVED SIGNALS
# (Complete_Derivations_Full.pdf §12, §15; collapse_geometry/mfls.py §XXIV.4, §XXVI.1)
#
# BSDT has TWO distinct MFLS quantities operating in different spaces:
#
#   MFLS_ch  =  ‖g_t‖         g_t ∈ ℝ⁴  (channel gradient: ∇_S E_BS, abstract intensity)
#   MFLS_st  =  ‖G̃_t‖_F       G̃_t ∈ ℝ^{N×d}  (state pullback Σ_k g_k J_k, physical intensity)
#   ρ_MFLS   =  MFLS_st / MFLS_ch               (amplification factor)
#
# §XXVI.1 derivation (canonical):
#   R_t = g_t^T Gram g_t = ‖G̃_t‖_F²   →   cos ψ_t = ρ_MFLS   (NOT inner product)
#
# admissibility_ratio and safety_ratio (§12) use MFLS_st (physical intensity).
# ============================================================

def mfls(g_norm_history: np.ndarray) -> float:
    """
    Complete_Derivations §12 — Generic MFLS: max over lead window.

    For state-space MFLS (MFLS_paper = ‖∇E_BS‖_F per §VI.5):
        Pass a 1-D array of ‖∇E_BS(X_{t'})‖ scalars.

    For channel-space MFLS see mfls_channel().
    For state-pullback MFLS see mfls_state().

    MFLS(t) = max_{t' ∈ [t-L, t]} scalar_{t'}

    g_norm_history: 1-D array of scalar signal values over the lead window.
    Returns: scalar MFLS value.
    """
    return float(np.max(g_norm_history))


def mfls_channel(channel_vec_history: np.ndarray) -> float:
    """
    §XXIV.4 — MFLS in the 4-channel BSDT space (MFLS_ch).

    BSDT channel state: g_t = (δ_C, δ_G, δ_A, δ_T) ∈ ℝ⁴ (abstract intensity).
    MFLS_ch(t) = max_{t' ∈ window} ‖g_{t'}‖₂

    This is a dimensionally consistent norm in channel space,
    but does NOT reflect physical (state-space) amplitudes.
    Use MFLS_st / mfls_state() for physical intensities.

    channel_vec_history: (T_window, K) array of K-channel state vectors (K=4 for BSDT).
    Returns: scalar MFLS_ch.
    """
    norms = np.linalg.norm(channel_vec_history, axis=1)
    return float(np.max(norms))


def mfls_state(G_tilde_F_norm_history: np.ndarray) -> float:
    """
    §XXIV.4 — MFLS in the state-pullback space (MFLS_st).

    G̃_t = Σ_k g_k J_k ∈ ℝ^{N×d}  (state-space pullback, physical intensity).
    MFLS_st(t) = max_{t' ∈ window} ‖G̃_{t'}‖_F

    This is the correct input to admissibility_ratio() and safety_ratio()
    per Complete_Derivations §12: A = MFLS_st / √E.

    G_tilde_F_norm_history: 1-D array of ‖G̃_{t'}‖_F Frobenius norms over the window.
    Returns: scalar MFLS_st.
    """
    return float(np.max(G_tilde_F_norm_history))


def rho_mfls_amplification(mfls_st_val: float, mfls_ch_val: float) -> float:
    """
    §XXIV.4 — MFLS amplification factor ρ_MFLS.

    ρ_MFLS = MFLS_st / MFLS_ch  = ‖G̃‖_F / ‖g‖

    ρ < 1: state does not fully transmit channel risk (contained).
    ρ = 1: perfect transmission — channel and state MFLS agree.
    ρ > 1: state over-amplifies the channel signal → real collapse risk.

    Used to compute the misalignment angle: ψ_t = arccos(min(1, ρ_MFLS)).
    """
    return float(mfls_st_val) / (float(mfls_ch_val) + EPS)


def admissibility_ratio(mfls_val: float, E: float) -> float:
    """
    Complete_Derivations §12 — Admissibility ratio.

    A = MFLS_st / √E

    mfls_val: MFLS_st = max_{window} ‖G̃_{t'}‖_F  (state-pullback MFLS, physical units).
              Compute via mfls_state(G_tilde_F_norm_history).
              Do NOT pass MFLS_ch (channel-space) — it is dimensionally inconsistent
              with sqrt(E) which lives in the N×d physical state space.
    E:        current Lyapunov energy.

    A > 1: high-momentum state — directional flux dominates energy spread.
    A ≤ 1: sub-critical — energy is spatially diffuse.
    """
    return float(mfls_val) / (np.sqrt(float(E)) + EPS)


def safety_ratio(theta: float,
                 mfls_val: float,
                 E: float,
                 M_max: float) -> float:
    """
    Complete_Derivations §12 — Safety ratio.

    ρ_safety = θ · MFLS_st / (2 · M_max · √E)

    mfls_val: MFLS_st = max_{window} ‖G̃_{t'}‖_F  (state-pullback MFLS, physical units).
              Same space requirement as admissibility_ratio.
    theta:    CGS damping parameter.
    E:        current Lyapunov energy.
    M_max:    perturbation bound.

    ρ_safety ≥ 1: θ-damping dominates all M_max-bounded perturbations (provably safe).
    ρ_safety < 1: disturbance can exceed θ-damping; raise θ or reduce M_max.
    """
    return float(theta) * float(mfls_val) / (2.0 * float(M_max) * np.sqrt(float(E)) + EPS)


def psi_t_misalignment(G_tilde_F_norm: float,
                        g_norm: float) -> Tuple[float, float]:
    """
    §XXVI.1 — Sixth EWS signal ψ_t (misalignment angle between state and channel spaces).

    Derivation (collapse_geometry/mfls.py §XXVI.1):
        R_t  = g_t^T Gram g_t                       (scalar)
             = g_t^T (Σ_{ij} ⟨J_i, J_j⟩_F) g_t
             = ‖Σ_k g_k J_k‖_F²
             = ‖G̃_t‖_F²

        cos ψ_t  = R_t / (‖G̃_t‖_F · ‖g_t‖)
                 = ‖G̃_t‖_F² / (‖G̃_t‖_F · ‖g_t‖)
                 = ‖G̃_t‖_F / ‖g_t‖
                 = ρ_MFLS

        ψ_t = arccos(min(1, ρ_MFLS))   clamped — ρ > 1 maps to ψ = 0
        ξ_6 = cos² ψ_t = min(1, ρ_MFLS²)    ∈ [0, 1]  (sixth EWS)

    NOTE: This is NOT the inner product of vectors in the same space.
    G̃ ∈ ℝ^{N×d} and g ∈ ℝ⁴ live in different spaces; only their norms enter.

    ψ ≈ 0  (ρ ≥ 1): perfect or over-transmission — alarm is genuine (collapse).
    ψ > 0  (ρ < 1): under-transmission — channel risk is partially contained.
    ψ ∉ F_BSDT (sixth EWS carries strictly more information than raw BSDT filter,
                Theorem 40.1).

    G_tilde_F_norm: ‖G̃_t‖_F = MFLS_st scalar.
    g_norm:         ‖g_t‖    = MFLS_ch scalar.
    Returns (cos_psi, psi_t_radians).
    """
    rho = float(G_tilde_F_norm) / (float(g_norm) + EPS)
    cos_psi = float(min(1.0, rho))
    return cos_psi, float(np.arccos(cos_psi))


# ============================================================
# SECTION 22: CHANNEL RECOVERY + PER-CHANNEL LYAPUNOV
# (Complete_Derivations §16, Proposition 16.1, §28–29, Theorem 29.1)
# ============================================================

def channel_recovery_R(A: np.ndarray, J: np.ndarray) -> np.ndarray:
    """
    Complete_Derivations §16 — Channel recovery operator.

    R = ½ A⁻¹ (JJᵀ)⁻¹ J

    A: (k×k) invertible amplitude / channel-gain matrix (e.g. diag of gains).
    J: (k×n) Jacobian dS/dX.

    Property: S ≈ R · gX  (Shapley inversion, restores channel scores from gX).
    Used in GT.6 (Theorem 38.2) for Shapley-channel attribution.
    Returns (k×n) recovery operator R.
    """
    A_inv = np.linalg.inv(A)
    JJt = J @ J.T
    JJt_inv = np.linalg.inv(JJt + EPS * np.eye(JJt.shape[0]))
    return 0.5 * A_inv @ JJt_inv @ J


def channel_recovery_lipschitz(A: np.ndarray, J: np.ndarray) -> float:
    """
    Complete_Derivations Proposition 16.1 — Lipschitz stability of R.

    ‖R‖_op ≤ 1 / (2 · σmin(A) · σmin(J)²)

    σmin(A): smallest singular value of amplitude matrix A.
    σmin(J): smallest singular value of Jacobian J.

    Returns the operator-norm upper bound on ‖R‖.
    """
    sig_min_A = float(np.min(np.abs(np.linalg.eigvalsh(A @ A.T))))
    sig_min_A = np.sqrt(max(sig_min_A, EPS))
    sig_min_J = float(np.linalg.svd(J, compute_uv=False).min())
    return 1.0 / (2.0 * sig_min_A * sig_min_J ** 2 + EPS)


def per_channel_energy(A: np.ndarray,
                        S: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Complete_Derivations §28 — Per-channel Lyapunov decomposition.

    E^(k)      = A_kk · S_k²                  (within-channel energy, shape k)
    E^(k, k')  = 2 · A_{kk'} · S_k · S_{k'}  (cross-channel coupling, shape k×k)

    E_total = Σ_k E^(k) + Σ_{k≠k'} E^(k,k')  (full Lyapunov function)

    A: (k×k) symmetric coupling matrix (positive definite for stability).
    S: (k,)  channel residual vector.
    Returns (E_diag of shape (k,), E_cross of shape (k,k)).
    """
    k = len(S)
    E_diag = np.array([float(A[i, i]) * float(S[i]) ** 2 for i in range(k)])
    E_cross = np.zeros((k, k))
    for i in range(k):
        for j in range(k):
            if i != j:
                E_cross[i, j] = 2.0 * float(A[i, j]) * float(S[i]) * float(S[j])
    return E_diag, E_cross


def per_channel_lyapunov(A: np.ndarray,
                          S: np.ndarray,
                          gX_channels: np.ndarray,
                          Fbase: np.ndarray) -> Tuple[float, np.ndarray]:
    """
    Complete_Derivations §29, Theorem 29.1 — Per-channel Lyapunov test.

    E_total  = Σ_k E^(k) + Σ_{k<k'} E^(k,k')
    Ė_k     ≈ ⟨gX^(k), Fbase⟩ − ‖gX^(k)‖²  (linearised per-channel descent)

    Theorem 29.1: E_total is non-increasing iff all per-channel Ė_k ≤ 0
    under the linear-independence condition on {gX^(k)}.

    A:            (k×k) SPD coupling matrix.
    S:            (k,)  channel residual vector.
    gX_channels:  (k, n) per-channel gradient rows.
    Fbase:        (n,)  nominal drift.

    Returns (E_total, Edot_per_channel) where Edot_per_channel is shape (k,).
    """
    E_diag, E_cross = per_channel_energy(A, S)
    E_total = float(E_diag.sum()) + float(E_cross.sum())
    kc = gX_channels.shape[0]
    Edot_channels = np.array([
        float(np.dot(gX_channels[i], Fbase)) - float(np.dot(gX_channels[i], gX_channels[i]))
        for i in range(kc)
    ])
    return E_total, Edot_channels


# ============================================================
# SECTION 23: GAME-THEORETIC FOUNDATIONS
# (Complete_Derivations §34–38: Theorems 34.1, 35.1, 37.1, 38.1, 38.2)
# ============================================================

def projection_game_saddle(Fbase: np.ndarray,
                            gX: np.ndarray,
                            E: float,
                            theta: float) -> Tuple[np.ndarray, float, float]:
    """
    Complete_Derivations §34, Theorem 34.1 (GT.1) — Saddle-point characterisation.

    Two-player zero-sum game:
        Controller   minimises  E(X + Δu)   over Δu with ‖Δu‖ ≤ 1
        Nature       maximises  E(X + Δu)   over Δu (adversarial)

    Unique saddle point (Theorem 34.1):
        u*  = Fbase − γ · ⟨Fbase, gX⟩/‖gX‖² · gX
        λ*  = ⟨Fbase, gX⟩ · E / ((E + θ) · ‖gX‖²)
        γ   = E / (E + θ)

    u* is exactly the CGS-v1 canonical projection of Fbase onto D_X⊥,
    confirming that CGS-v1 solves the saddle-point optimality condition.

    Returns (u_star, lambda_star, gamma).
    """
    gX2 = float(np.dot(gX, gX)) + EPS
    gamma = float(E) / (float(E) + float(theta) + EPS)
    inner = float(np.dot(Fbase, gX))
    u_star = Fbase - gamma * inner / gX2 * gX
    lambda_star = inner * float(E) / ((float(E) + float(theta) + EPS) * gX2)
    return u_star, lambda_star, gamma


def adversarial_minimax_value(gX: np.ndarray,
                               Fnom: np.ndarray,
                               M_adv: float,
                               E: float,
                               theta: float) -> Tuple[np.ndarray, float, float]:
    """
    Complete_Derivations §35, Theorem 35.1 (GT.2) — Adversarial minimax game.

    Nature plays worst-case perturbation F_adv with ‖F_adv‖ ≤ M_adv.

    Theorem 35.1:
        F*_adv = M_adv · gX / ‖gX‖     (Nature aligns with gradient)
        B      = ⟨gX, Fnom⟩ + M_adv · ‖gX‖ − ‖gX‖²
        V*     = (1 − γ) · B            (minimax value of the game)

    There is NO interior saddle point in the unconstrained adversarial game:
    Nature always benefits from boundary play (extreme perturbation).

    Returns (F_star_adv, B, V_star).
    """
    gX_norm = float(np.linalg.norm(gX)) + EPS
    F_star = M_adv * gX / gX_norm
    gX2 = float(np.dot(gX, gX))
    B = float(np.dot(gX, Fnom)) + M_adv * gX_norm - gX2
    gamma = float(E) / (float(E) + float(theta) + EPS)
    V_star = (1.0 - gamma) * B
    return F_star, B, V_star


def coalition_superadditivity_check(grads: List[np.ndarray]) -> Tuple[bool, np.ndarray]:
    """
    Complete_Derivations §37, Theorem 37.1 (GT.4) — Coalition superadditivity.

    Assumption GT.4 (cross-engine disalignment):
        For all i ≠ j: ⟨g^(i), g^(j)⟩ ≤ 0

    Under GT.4 (gradients point in opposing directions), combining engines
    strictly improves performance:
        v(I, S^(i) ∪ S^(j)) ≥ v(I, S^(i)) + v(I, S^(j))
    (coalition value ≥ sum of individual values for any pair i, j).

    Returns (assumption_gt4_satisfied, inner_product_matrix  of shape m×m).
    """
    m = len(grads)
    inner_mat = np.array([[float(np.dot(grads[i], grads[j]))
                           for j in range(m)]
                          for i in range(m)])
    off_diag_mask = ~np.eye(m, dtype=bool)
    assumption_ok = bool(np.all(inner_mat[off_diag_mask] <= 0.0))
    return assumption_ok, inner_mat


def shapley_channel_attribution(grad_channels: List[np.ndarray],
                                 S_fn: Callable[[frozenset], float],
                                 m: Optional[int] = None) -> np.ndarray:
    """
    Complete_Derivations §38, Theorem 38.1 (GT.5) — Shapley channel attribution.

    ϕ_k = Σ_{T ⊆ [m]\\{k}} [ v(T∪{k}) − v(T) ] · |T|!(m−|T|−1)!/m!

    v(T): characteristic function — value of using channel subset T.
         Passed in as S_fn: frozenset → scalar.

    grad_channels: list of m gradient vectors (one per channel); used to infer m.
    m:             number of channels (default = len(grad_channels)).

    Returns (m,) Shapley value vector ϕ.
    Note: exact computation is O(2^m); practical for m ≤ 12.
    """
    from itertools import combinations
    from math import factorial
    if m is None:
        m = len(grad_channels)
    phi = np.zeros(m)
    all_others_by_k = [[i for i in range(m) if i != k] for k in range(m)]
    for k in range(m):
        others = all_others_by_k[k]
        for r in range(len(others) + 1):
            for subset in combinations(others, r):
                T_set = frozenset(subset)
                T_with_k = frozenset(list(T_set) + [k])
                marginal = S_fn(T_with_k) - S_fn(T_set)
                weight = factorial(r) * factorial(m - r - 1) / factorial(m)
                phi[k] += weight * marginal
    return phi


def shapley_recovery_R_gt6(A: np.ndarray,
                            J: np.ndarray,
                            gX: np.ndarray) -> np.ndarray:
    """
    Complete_Derivations §38, Theorem 38.2 (GT.6) — Shapley inversion via R.

    R = ½ A⁻¹ (JJᵀ)⁻¹ J   (same operator as channel_recovery_R)
    S_shapley = R · gX       (channel-level Shapley attribution by linear inversion)

    Theorem 38.2 establishes that the unique linear combination of channel
    recovery scores consistent with the kernel architecture EQUALS the
    exact Shapley values under the uniform coalition measure.

    Returns S_shapley: (k,) reconstructed channel Shapley attribution.
    """
    R = channel_recovery_R(A, J)
    return R @ gX


# ============================================================
# SECTION 24: θ MECHANISM DESIGN
# (Complete_Derivations §39, Theorem 39.1 — Admissibility-binding θ*)
# ============================================================

def theta_admissibility_binding(M: float,
                                 M_G: float,
                                 sigma: float,
                                 mu_G: float) -> float:
    """
    Complete_Derivations §39, Theorem 39.1 (GT.7) — Admissibility-binding θ*.

    θ* = M · √M_G / (σ · μ_G)

    M:    disturbance bound — ‖Fbase − F_nominal‖ ≤ M.
    M_G:  ‖G‖_op = λmax(G)  (largest eigenvalue of metric tensor).
    σ:    σmin(J)  (smallest singular value of Jacobian J).
    μ_G:  λmin(G)  (smallest eigenvalue of metric G).

    θ* is the unique threshold where the admissibility constraint binds:
    θ < θ* → constraint inactive (system may be unsafe under worst M).
    θ = θ* → tight margin (minimum θ that guarantees admissibility).
    θ > θ* → conservative (safe but may over-damp performance).

    Returns θ*.
    """
    return float(M) * np.sqrt(float(M_G)) / (float(sigma) * float(mu_G) + EPS)


def theta_empirical_median(E_calm: np.ndarray) -> float:
    """
    Complete_Derivations §39 — Data-adaptive θ from calm-period observations.

    θ̂ = median{ E(t) : t ∈ T_calm }

    T_calm: period with no detected alarms / low-volatility baseline.
    This data-driven estimator automatically scales θ to the operating energy
    level of the system, producing the tightest admissible θ without manual tuning.

    E_calm: (T_calm,) array of energy values during the calm reference period.
    Returns θ̂ (scalar).
    """
    return float(np.median(E_calm))


# ============================================================
# SECTION 25: INFORMATION DOMINANCE
# (Complete_Derivations §40, Theorem 40.1, Corollary 40.2)
# ============================================================

def information_dominance_check(psi_t_series: np.ndarray,
                                 threshold_deg: float = 30.0) -> Tuple[bool, float]:
    """
    Complete_Derivations §40, Theorem 40.1 (GT.8) — Information dominance.

    Theoretical statement: F_can+ ⊋ F_BSDT
    The canonical filter (CGS-v1) generates strictly MORE information than
    the raw BSDT filter because ψt (sixth signal, §15) is included in F_can+
    but ψt ∉ F_BSDT.

    Practical test: ψt is information-dominant if it systematically deviates
    from π/2 during crisis versus calm epochs.

    Δψ = mean(ψt during alarm half) − mean(ψt during calm half)
    Information dominance confirmed if |Δψ| > threshold_deg (in degrees).

    psi_t_series:  (T,) array of ψt values in radians.
    threshold_deg: detection threshold in degrees (default 30°).

    Returns (dominance_confirmed: bool, delta_psi_degrees: float).
    """
    if len(psi_t_series) < 4:
        return False, 0.0
    psi_deg = np.degrees(psi_t_series)
    split = len(psi_deg) // 2
    calm_mean = float(np.mean(psi_deg[:split]))
    alarm_mean = float(np.mean(psi_deg[split:]))
    delta_psi = alarm_mean - calm_mean
    return abs(delta_psi) > threshold_deg, delta_psi


def decision_dominance_cor402(psi_t_series: np.ndarray,
                               E_series: np.ndarray,
                               theta: float,
                               action_threshold: float = 0.5) -> np.ndarray:
    """
    Complete_Derivations §40, Corollary 40.2 — Decision dominance.

    The canonical controller dominates a pure-BSDT controller in decision
    quality when ψt is included in the action rule:

    Action rule:  a_t = 1  iff  A_t · cos(ψt) > action_threshold
    where A_t = ‖gX_t‖ / √E_t   (admissibility ratio)

    We proxy ‖gX_t‖ ≈ √(g(E_t) · E_t) = √(θ · E_t / (E_t + θ)).

    psi_t_series:   (T,) array of ψt radians.
    E_series:       (T,) energy series.
    theta:          current θ parameter.
    action_threshold: scalar scalar action gate.

    Returns integer action sequence of shape (T,): 1 = intervene, 0 = wait.
    """
    T = len(E_series)
    cos_psi = np.cos(psi_t_series)
    g_E = np.array([attenuation_factor(float(E_series[t]), theta) for t in range(T)])
    gX_proxy = np.sqrt(np.maximum(g_E * E_series, 0.0))
    sqrt_E = np.sqrt(np.maximum(E_series, 0.0)) + EPS
    A_t = gX_proxy / sqrt_E
    return (A_t * cos_psi > action_threshold).astype(int)


# ============================================================
# SECTION 26: PHASE EXTENSION (Part IV)
# (Trigonometry of Collapse, Parts I & III; Complete_Derivations Part IV)
#
# The three fundamental angles, angular kinematics, the phase-amplitude
# energy split, the Kuramoto phase-coherence channel, the three-phase
# precursor, and SO(3) rotation-angle trigonometry.  Everything below is a
# function of the two canonical objects (gX, E) plus the raw state.
# ============================================================

def alignment_angle(Fbase: np.ndarray, gX: np.ndarray) -> Tuple[float, float]:
    """
    Trigonometry of Collapse §1 — Alignment angle θ_t.

        cos θ_t = ⟨gX, Fbase⟩ / (‖gX‖ · ‖Fbase‖)   ∈ [-1, +1]
        θ_t     = arccos(cos θ_t)                   ∈ [0, π]

    θ_t = 0    : Fbase points exactly along gX — nominal force fully drives instability.
    θ_t = π/2  : Fbase ⊥ gX — tangential force, no first-order energy change.
    θ_t = π    : Fbase anti-parallel to gX — force actively opposes instability.

    Frobenius inner products are used so matrix-valued Fbase / gX are accepted.
    Returns (cos_theta, theta_radians).
    """
    fb = np.asarray(Fbase, dtype=float).ravel()
    g = np.asarray(gX, dtype=float).ravel()
    denom = (np.linalg.norm(fb) * np.linalg.norm(g)) + EPS
    cos_theta = float(np.clip(np.dot(fb, g) / denom, -1.0, 1.0))
    return cos_theta, float(np.arccos(cos_theta))


def collapse_angle(cos_theta: float) -> float:
    """
    Trigonometry of Collapse §3 — Collapse angle tan θ_t.

        tan θ_t = ‖F_⊥‖ / ‖F_∥‖ = sin θ_t / cos θ_t = √(1 − cos²θ_t) / cos θ_t

    tan θ_t → 0   : force fully collapse-directed (all energy drives instability).
    tan θ_t → ∞   : force fully perpendicular (no first-order energy change).
    tan θ_t = 1   : critical balance (θ_t = 45°).

    For cos θ_t → 0 the collapse angle diverges; a large finite value is returned.
    """
    c = float(np.clip(cos_theta, -1.0, 1.0))
    sin_theta = np.sqrt(max(0.0, 1.0 - c * c))
    return float(sin_theta / (c + np.sign(c) * EPS)) if c != 0.0 else float(np.inf)


def angular_velocity_theta_exact(gX: np.ndarray,
                                  Fbase: np.ndarray,
                                  gX_dot: np.ndarray,
                                  Fbase_dot: np.ndarray) -> float:
    """
    Trigonometry of Collapse Thm. (Angular velocity, exact) — θ̇_t = −ḣ / sin θ_t.

    With h = cos θ_t = p/(ab), p = ⟨gX, Fbase⟩, a = ‖gX‖, b = ‖Fbase‖:

        ḣ = (⟨ġX, Fbase⟩ + ⟨gX, Ḟbase⟩) / (ab)
            − cos θ_t · (⟨gX, ġX⟩/a² + ⟨Fbase, Ḟbase⟩/b²)

        θ̇_t = −ḣ / sin θ_t,   sin θ_t = √(1 − h²) > 0  for θ_t ∈ (0, π).

    θ̇_t > 0 : angle opening (force rotating away from gradient).
    θ̇_t < 0 : angle closing (force aligning with gradient).
    """
    g = np.asarray(gX, dtype=float).ravel()
    fb = np.asarray(Fbase, dtype=float).ravel()
    gd = np.asarray(gX_dot, dtype=float).ravel()
    fbd = np.asarray(Fbase_dot, dtype=float).ravel()
    a = np.linalg.norm(g)
    b = np.linalg.norm(fb)
    ab = a * b + EPS
    h = float(np.clip(np.dot(g, fb) / ab, -1.0, 1.0))
    p_dot = np.dot(gd, fb) + np.dot(g, fbd)
    h_dot = p_dot / ab - h * (np.dot(g, gd) / (a * a + EPS)
                              + np.dot(fb, fbd) / (b * b + EPS))
    sin_theta = np.sqrt(max(EPS, 1.0 - h * h))
    return float(-h_dot / sin_theta)


def angular_velocity_theta_discrete(theta_series: np.ndarray,
                                     dt: float = 1.0) -> np.ndarray:
    """
    Trigonometry of Collapse §43.3 — Discrete angular velocity.

        θ̇_t ≈ (θ_t − θ_{t-1}) / Δt      (backward difference)

    theta_series: (T,) array of alignment angles θ_t (radians).
    Returns (T,) array; first element is 0 (no prior sample).
    """
    theta = np.asarray(theta_series, dtype=float)
    out = np.zeros_like(theta)
    out[1:] = (theta[1:] - theta[:-1]) / dt
    return out


def angular_acceleration_theta(theta_series: np.ndarray,
                               dt: float = 1.0) -> np.ndarray:
    """
    Trigonometry of Collapse §43.3 — Discrete angular acceleration.

        θ̈_t ≈ (θ_{t+1} − 2θ_t + θ_{t-1}) / Δt²    (central difference)

    Only the SIGN of θ̈_t is needed for the precursor condition, so the
    central-difference approximation is exact for detection purposes.

    theta_series: (T,) array of alignment angles (radians).
    Returns (T,) array; boundary elements (first, last) are 0.
    """
    theta = np.asarray(theta_series, dtype=float)
    out = np.zeros_like(theta)
    out[1:-1] = (theta[2:] - 2.0 * theta[1:-1] + theta[:-2]) / (dt * dt)
    return out


def phase_amplitude_split(X: np.ndarray,
                          X_dot: np.ndarray,
                          gX: np.ndarray) -> Tuple[float, float]:
    """
    Trigonometry of Collapse Thm. 44.1 — Phase-amplitude energy split.

        A = ‖X‖_F,   X̂ = X/A,   Ȧ = ⟨X̂, Ẋ⟩_F,   Ẋ_⊥ = Ẋ − Ȧ X̂

        Ė = Ė^(A) + Ė^(φ),
        Ė^(A) = ⟨gX, X̂⟩_F · Ȧ          (amplitude energy rate)
        Ė^(φ) = ⟨gX, Ẋ_⊥⟩_F            (phase energy rate)

    The amplitude rate captures radial (magnitude) energy change; the phase
    rate captures tangential (directional) energy change.  Their sum recovers
    the full Ė = ⟨gX, Ẋ⟩_F exactly.

    Returns (Edot_amplitude, Edot_phase).
    """
    x = np.asarray(X, dtype=float).ravel()
    xd = np.asarray(X_dot, dtype=float).ravel()
    g = np.asarray(gX, dtype=float).ravel()
    A = np.linalg.norm(x)
    if A < EPS:
        return 0.0, float(np.dot(g, xd))
    x_hat = x / A
    A_dot = float(np.dot(x_hat, xd))
    xd_perp = xd - A_dot * x_hat
    edot_amp = float(np.dot(g, x_hat) * A_dot)
    edot_phase = float(np.dot(g, xd_perp))
    return edot_amp, edot_phase


def instantaneous_phase(X_tilde: np.ndarray,
                        V1: np.ndarray,
                        V2: np.ndarray) -> np.ndarray:
    """
    Trigonometry of Collapse §45.1 — Instantaneous phase from top-2 PCA plane.

        φ_i(t) = arg(V1ᵀ x̃_i + i · V2ᵀ x̃_i)   ∈ (−π, π]

    Each agent's centred state is projected onto the first two principal
    directions of Σ_0; the resulting (real, imag) pair defines an oscillation
    phase via arctan2.

    X_tilde: (N, d) centred state matrix (rows = agents).
    V1, V2:  (d,) leading PCA eigenvectors of Σ_0.
    Returns (N,) array of phases in radians.
    """
    Xt = np.atleast_2d(np.asarray(X_tilde, dtype=float))
    a = Xt @ np.asarray(V1, dtype=float)
    b = Xt @ np.asarray(V2, dtype=float)
    return np.arctan2(b, a)


def phase_coherence_channel(phases: np.ndarray) -> np.ndarray:
    """
    Trigonometry of Collapse §45.2 — Phase coherence channel δ_Φ^(i).

        δ_Φ^(i) = 1 − |  (1/(N−1)) Σ_{j≠i} exp(i(φ_j − φ_i))  |   ∈ [0, 1]

    δ_Φ^(i) = 0 : agent i fully synchronised with the population.
    δ_Φ^(i) = 1 : agent i completely incoherent with peers.

    phases: (N,) array of agent phases (radians).
    Returns (N,) array of per-agent phase incoherence.
    """
    phi = np.asarray(phases, dtype=float).ravel()
    N = phi.size
    if N < 2:
        return np.zeros(N)
    z = np.exp(1j * phi)                       # (N,)
    total = z.sum()
    # Σ_{j≠i} exp(iφ_j) = total − exp(iφ_i); coherence relative to agent i.
    others = (total - z) / (N - 1)
    rel = others * np.exp(-1j * phi)           # multiply by exp(−iφ_i)
    return 1.0 - np.abs(rel)


def kuramoto_order_parameter(phases: np.ndarray) -> float:
    """
    Trigonometry of Collapse §45.3 — Kuramoto order parameter R(t).

        R(t) = | (1/N) Σ_i exp(i φ_i) |   ∈ [0, 1]

    R = 1 : perfect synchronisation (all phases identical).
    R = 0 : phases uniformly dispersed (no collective alignment).

    phases: (N,) array of agent phases (radians).
    Returns scalar R(t).
    """
    phi = np.asarray(phases, dtype=float).ravel()
    if phi.size == 0:
        return 0.0
    return float(np.abs(np.mean(np.exp(1j * phi))))


def phase_energy(delta_Phi: np.ndarray) -> float:
    """
    Trigonometry of Collapse §45.4 — Phase energy E_φ.

        E_φ = (1/N) Σ_i (δ_Φ^(i))²

    The Lyapunov energy of the phase-coherence channel S_Φ = (δ_Φ^(1), …, δ_Φ^(N))
    under metric G = I_N / N.  High E_φ ⇒ population phases are dispersing.

    delta_Phi: (N,) per-agent phase incoherence (from phase_coherence_channel).
    Returns scalar E_φ.
    """
    d = np.asarray(delta_Phi, dtype=float).ravel()
    if d.size == 0:
        return 0.0
    return float(np.mean(d * d))


def phase_gain(E_phi: float, theta_phi: float) -> float:
    """
    Trigonometry of Collapse §45.5 — Phase gain γ_φ (Fermi-Dirac in phase energy).

        γ_φ = E_φ / (E_φ + θ_φ)   ∈ [0, 1)

    θ_φ = median calm-period phase energy (calibrated separately from θ).
    Mirrors the amplitude gain γ = E/(E+θ); controls phase-channel damping.

    Returns scalar γ_φ.
    """
    return float(E_phi) / (float(E_phi) + float(theta_phi) + EPS)


def three_phase_precursor(Edot, Rdot, theta_ddot):
    """
    Trigonometry of Collapse Thm. 46.1 — Three-phase precursor P(t).

        P(t)  ⇔  Ė(t) > 0  ∧  Ṙ(t) > 0  ∧  θ̈_t > 0

    Under P(t) the safety ratio is strictly decreasing (Theorem 46.1):
    energy rising (phase 1) + synchronisation building (phase 2) + angular
    decoherence accelerating (phase 3) jointly imply imminent collapse.

    The temporal ordering τ_E ≥ τ_R ≥ τ_P gives successively higher confidence
    at shorter horizon.  Accepts scalars or equal-length arrays.

    Returns bool (scalar inputs) or boolean ndarray (array inputs).
    """
    Ed = np.asarray(Edot, dtype=float)
    Rd = np.asarray(Rdot, dtype=float)
    td = np.asarray(theta_ddot, dtype=float)
    mask = (Ed > 0.0) & (Rd > 0.0) & (td > 0.0)
    if mask.ndim == 0:
        return bool(mask)
    return mask


def rotation_angle_from_trace(R: np.ndarray) -> float:
    """
    Trigonometry of Collapse (Rotational Geometry) — SO(3) angle from trace.

        tr(exp(ω̂)) = 1 + 2 cos θ   ⇒   θ_rot = arccos((tr(R) − 1)/2)  ∈ [0, π]

    Recovers the rotation magnitude of an SO(3) state directly from its trace.
    In the canonical engine, E(R) = ‖log(Rᵀ R_target)‖_F² = 2 θ_rot², so the
    rotation angle is an exact energy proxy on SO(3).

    R: (3, 3) rotation matrix.
    Returns θ_rot (radians).
    """
    Rm = np.asarray(R, dtype=float)
    cos_theta = (np.trace(Rm) - 1.0) / 2.0
    return float(np.arccos(np.clip(cos_theta, -1.0, 1.0)))


# ── Section 26 — Regime classification and phase-decoherence alarm ────────────

def classify_collapse_regime(cos_theta: float, epsilon: float = 0.05) -> str:
    """
    Section 26 — Regime classification from alignment angle cos θ_t.

    Partitions (F_base, g_X) alignment into three canonical regimes:

      'collapse'   — cos θ > +ε  : F_base pushes along ∇E → energy rising.
      'restoring'  — cos θ < −ε  : F_base opposes ∇E → energy falling (mean-reverting).
      'critical'   — |cos θ| ≤ ε : near-orthogonal, phase-transition boundary.

    epsilon: half-width of the critical band (default 0.05, i.e. within 3° of π/2).
    """
    c = float(cos_theta)
    if c > epsilon:
        return 'collapse'
    elif c < -epsilon:
        return 'restoring'
    return 'critical'


def phase_decoherence_alarm(R_dot: float, E_phi: float, theta_phi: float,
                             cos_theta: float, epsilon: float = 0.05) -> bool:
    """
    Section 26 — Phase-decoherence alarm for the restoring / mean-reverting regime.

    The canonical three-phase precursor P(t) = (Ė>0)∧(Ṙ>0)∧(θ̈>0) requires
    Ė > 0, which is impossible when cos θ ≈ −1 (restoring regime: F_base opposes
    ∇E everywhere).  This complementary precursor fires when ALL hold:

        regime = 'restoring'  (cos θ < −ε)      [mean-reverting dynamics]
        Ṙ < 0                                    [Kuramoto synchrony falling]
        E_φ > θ_φ                               [phase disorder elevated above calm baseline]

    Interpretation: in a mean-reverting system the precursor to phase-incoherence
    collapse is not rising energy (blocked by the restoring force) but falling
    Kuramoto order while phase energy is already elevated — synchrony is being
    lost despite the restoring drive, signalling an impending phase-coherence
    breakdown.

    Returns True if all three conditions hold simultaneously.

    Parameters
    ----------
    R_dot     : Kuramoto Ṙ(t) — backward difference of R(t).
    E_phi     : phase energy E_φ(t) at the current step.
    theta_phi : calm-period median of E_φ (threshold).
    cos_theta : cos θ_t — alignment angle between F_base and g_X.
    epsilon   : critical-band half-width for regime classification.
    """
    regime = classify_collapse_regime(cos_theta, epsilon)
    return regime == 'restoring' and bool(R_dot < 0.0) and bool(E_phi > theta_phi)


def windowed_precursor_array(Edot: np.ndarray, Rdot: np.ndarray,
                             theta_ddot: np.ndarray,
                             window: int = 8,
                             min_fraction: float = 0.5) -> np.ndarray:
    """
    Section 26 — Windowed three-phase precursor P_w(t).

    At each time t, fires when within the rolling window [t-window+1, t] at
    least `min_fraction` of samples satisfy EACH of the three conditions:

        Ė(τ) > 0  (energy rising — ΔE backward diff)
        Ṙ(τ) > 0  (Kuramoto coherence rising)
        θ̈(τ) > 0  (angular acceleration positive)

    More robust than the pointwise three_phase_precursor to instantaneous
    noise.  At window=1 reduces exactly to three_phase_precursor.

    Vectorized using cumulative sums — O(T) time.

    Parameters
    ----------
    Edot, Rdot, theta_ddot : (T,) arrays (same units as three_phase_precursor).
    window       : number of past samples to check (default 8).
    min_fraction : fraction of window that must satisfy each condition (default 0.5).

    Returns (T,) boolean array.
    """
    T         = len(Edot)
    c1        = (np.asarray(Edot,      dtype=float) > 0).astype(np.int32)
    c2        = (np.asarray(Rdot,      dtype=float) > 0).astype(np.int32)
    c3        = (np.asarray(theta_ddot, dtype=float) > 0).astype(np.int32)
    min_count = max(1, int(np.ceil(window * min_fraction)))

    def _rolling_sum(c: np.ndarray) -> np.ndarray:
        cs  = np.concatenate([[0], np.cumsum(c)])
        out = np.zeros(T, dtype=np.int32)
        out[window - 1:] = cs[window: T + 1] - cs[: T - window + 1]
        return out

    return (_rolling_sum(c1) >= min_count) & \
           (_rolling_sum(c2) >= min_count) & \
           (_rolling_sum(c3) >= min_count)


def eeg_amplitude_phase_precursor(Edot: np.ndarray, R: np.ndarray,
                                   R_calm_mean: float, R_calm_std: float,
                                   k_sigma: float = 2.0) -> np.ndarray:
    """
    Section 26 — EEG amplitude-phase combined precursor P^EEG(t).

        P^EEG(t) = (Ė(t) > 0) ∧ (R(t) > μ_R + k·σ_R)

    Combines the dominant amplitude signal (energy rising: ΔE > 0) with a
    phase-coherence confirmation (Kuramoto R above the interictal baseline).

    Designed for amplitude-dominated ictal events (|ĖA|/|Ėφ| >> 1) where
    R rises slightly during hypersynchronous seizure activity while ΔE spikes
    dramatically.  The two-condition conjunction substantially reduces the
    false-alarm rate compared to ΔE > 0 alone.

    Parameters
    ----------
    Edot       : (T,) energy increment ΔE = E[t] - E[t-1] (backward diff).
    R          : (T,) Kuramoto order parameter.
    R_calm_mean: mean R over the calm/interictal reference period.
    R_calm_std : std  R over the calm/interictal reference period.
    k_sigma    : threshold multiplier (default 2.0 → 2-sigma above baseline).

    Returns (T,) boolean array.
    """
    R_threshold = float(R_calm_mean) + float(k_sigma) * float(R_calm_std)
    return (np.asarray(Edot, dtype=float) > 0) & \
           (np.asarray(R,    dtype=float) > R_threshold)
