"""Canonical core — §3–§5, §7, §C.5, §D.3, §H.1 of canonical_system_v4.

THE CANONICAL ODE (§3, LOCKED, FROZEN):

    Ẋ = F_base(X) − g_X(X) − γ(X) · ⟨F(X), g_X(X)⟩ / (‖g_X(X)‖² + ε) · g_X(X)

with
    S(X) ∈ Rᵏ                  — representation map           (§4.1)
    G ∈ Rᵏˣᵏ, G ≻ 0             — feature-space metric         (§4.2)
    E(X) = S(X)ᵀ G S(X)         — energy                       (§4.2)
    g_X(X) = 2 J(X)ᵀ G S(X)     — single, unique gradient      (§4.3)
    F(X) = F_base(X) − g_X(X)   — modified force               (§4.4 / §B.2a)
    γ(X) = E(X) / (E(X) + θ)    — adaptive gain ∈ [0,1)        (§4.5)

ε ≥ 0 is the regularisation of §2.2 (ε = 0 is exact canonical; ε > 0
removes the singularity at g_X = 0).

Four inviolable rules (§5):
    1. Geometry enters only through g_X.
    2. All projections use the Euclidean inner product.
    3. G_pull = JᵀGJ is for curvature analysis ONLY — never in dynamics.
    4. Each object has exactly one definition; no duplication.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional
import numpy as np


# -----------------------------------------------------------------------
# Type aliases (state X ∈ Rⁿ, feature S ∈ Rᵏ)
# -----------------------------------------------------------------------
ScalarFn = Callable[[np.ndarray], float]
VectorFn = Callable[[np.ndarray], np.ndarray]   # Rⁿ → Rⁿ  or  Rⁿ → Rᵏ
MatrixFn = Callable[[np.ndarray], np.ndarray]   # Rⁿ → Rᵏˣⁿ


# =======================================================================
#  CanonicalSystem — the locked kernel
# =======================================================================
@dataclass
class CanonicalSystem:
    """The canonical dynamical geometry system v4 (§3–§5).

    Parameters
    ----------
    S : callable X ↦ S(X) ∈ Rᵏ
        Representation / feature map (§4.1).
    J : callable X ↦ J(X) ∈ Rᵏˣⁿ
        Jacobian ∂S/∂X.  If None, computed by central finite differences.
    G : (k, k) ndarray, SPD
        Constant feature-space metric (§4.2).  May be replaced by a callable
        G(X) for the geometric-flow / Fisher extensions; in the locked
        kernel G is constant in X and t.
    F_base : callable X ↦ F_base(X) ∈ Rⁿ
        Domain-specific nominal field (§A.3).
    theta : float, default 1.0
        Regularisation constant of the adaptive gain (§4.5); θ > 0.
    epsilon : float, default 0.0
        Singular-set regularisation of the ODE (§2.2); ε ≥ 0.  Set to a
        small positive value (e.g. 1e-12) to integrate through g_X ≈ 0.
    K : optional callable X ↦ K(X) ∈ Rᵏˣⁿˣⁿ
        Representation curvature tensor K_ab^i = ∂_a∂_b S^i (§C.5).  If
        provided, the analytic Hessian (§Prop. 6.1) is used; otherwise the
        Hessian is approximated by finite differences of g_X.
    """

    S: VectorFn
    J: Optional[MatrixFn]
    G: np.ndarray
    F_base: VectorFn
    theta: float = 1.0
    epsilon: float = 0.0
    K: Optional[Callable[[np.ndarray], np.ndarray]] = None
    # finite-difference step for J / K when not supplied
    fd_step: float = 1e-6
    _G_eigs: tuple[float, float] = field(init=False, default=(0.0, 0.0))

    def __post_init__(self):
        G = np.asarray(self.G, dtype=float)
        if G.ndim != 2 or G.shape[0] != G.shape[1]:
            raise ValueError("G must be square (k×k)")
        # symmetrise to kill numerical asymmetry, then check PD
        G = 0.5 * (G + G.T)
        eigs = np.linalg.eigvalsh(G)
        if eigs[0] <= 0.0:
            raise ValueError(f"G must be positive definite; min eig = {eigs[0]:.3e}")
        self.G = G
        self._G_eigs = (float(eigs[0]), float(eigs[-1]))   # (μ_G, M_G)
        if self.theta <= 0.0:
            raise ValueError("theta must be > 0 (§A.4)")
        if self.epsilon < 0.0:
            raise ValueError("epsilon must be ≥ 0 (§2.2)")

    # ------------------------------------------------------------------
    # Core scalar / vector quantities (single definition each, §4)
    # ------------------------------------------------------------------
    def jacobian(self, X: np.ndarray) -> np.ndarray:
        """J(X) ∈ Rᵏˣⁿ.  Analytic if supplied; otherwise central finite diff."""
        if self.J is not None:
            return np.asarray(self.J(X), dtype=float)
        # central finite differences  (k×n)
        h = self.fd_step
        n = X.size
        S0 = np.asarray(self.S(X), dtype=float)
        k = S0.size
        Jfd = np.empty((k, n))
        for i in range(n):
            ei = np.zeros(n)
            ei[i] = 1.0
            Sp = np.asarray(self.S(X + h * ei), dtype=float)
            Sm = np.asarray(self.S(X - h * ei), dtype=float)
            Jfd[:, i] = (Sp - Sm) / (2.0 * h)
        return Jfd

    def energy(self, X: np.ndarray) -> float:
        """E(X) = S(X)ᵀ G S(X)  — §4.2 (single definition)."""
        s = np.asarray(self.S(X), dtype=float)
        return float(s @ self.G @ s)

    def gradient(self, X: np.ndarray) -> np.ndarray:
        """g_X(X) = 2 J(X)ᵀ G S(X)  — §4.3 (single, unique gradient)."""
        s = np.asarray(self.S(X), dtype=float)
        Jx = self.jacobian(X)
        return 2.0 * Jx.T @ (self.G @ s)

    def gain(self, X: np.ndarray) -> float:
        """γ(X) = E / (E + θ) ∈ [0, 1)  — §4.5."""
        e = self.energy(X)
        return e / (e + self.theta)

    def modified_force(self, X: np.ndarray) -> np.ndarray:
        """F(X) = F_base(X) − g_X(X)  — §4.4 / §B.2a (single force)."""
        return np.asarray(self.F_base(X), dtype=float) - self.gradient(X)

    # ------------------------------------------------------------------
    # The canonical ODE (§3, LOCKED) — vector field Ẋ
    # ------------------------------------------------------------------
    def rhs(self, X: np.ndarray) -> np.ndarray:
        """Right-hand side of the canonical ODE (§3, regularised §2.2):

            Ẋ = F − γ · ⟨F, g_X⟩ / (‖g_X‖² + ε) · g_X

        where F = F_base − g_X is the modified force.
        """
        gX = self.gradient(X)
        F  = np.asarray(self.F_base(X), dtype=float) - gX
        gn2 = float(gX @ gX) + self.epsilon
        if gn2 <= 0.0:
            return F  # g_X = 0 and ε = 0  ⇒  Ẋ = F (target manifold)
        gamma = self.gain(X)
        alpha = float(F @ gX) / gn2          # §H.1 step 8
        return F - gamma * alpha * gX        # §H.1 step 9

    def dE_dt(self, X: np.ndarray) -> float:
        """Canonical energy derivative (Lemma 6.7):

            Ė = (1 − γ) · ( ⟨g_X, F_base⟩ − ‖g_X‖² )
        """
        gX = self.gradient(X)
        Fb = np.asarray(self.F_base(X), dtype=float)
        return (1.0 - self.gain(X)) * (float(gX @ Fb) - float(gX @ gX))

    # ------------------------------------------------------------------
    # Hessian (§C.5 Prop. 6.1) and curvature manifold (§D.3)
    # ------------------------------------------------------------------
    def hessian(self, X: np.ndarray) -> np.ndarray:
        """∇²_X E = 2 JᵀGJ + ⟨η, K⟩₁,  η = 2GS  (§Prop. 6.1).

        If the analytic curvature tensor K is supplied, uses the closed
        form.  Otherwise approximates ∇²E by central finite differences of
        g_X (which equals ∇_X E by §4.3).
        """
        Jx = self.jacobian(X)
        H_pull = 2.0 * Jx.T @ self.G @ Jx          # 2·G_pull
        if self.K is not None:
            s = np.asarray(self.S(X), dtype=float)
            eta = 2.0 * self.G @ s                 # η = 2GS
            Kx = np.asarray(self.K(X), dtype=float)  # (k, n, n)
            # ⟨η, K⟩₁ = Σ_i η_i K^i  ∈ Rⁿˣⁿ
            curv = np.einsum("i,iab->ab", eta, Kx)
            return H_pull + curv
        # finite-difference Jacobian of g_X  (∇²E = ∂g_X/∂X)
        h = self.fd_step
        n = X.size
        Hfd = np.empty((n, n))
        for i in range(n):
            ei = np.zeros(n); ei[i] = 1.0
            gp = self.gradient(X + h * ei)
            gm = self.gradient(X - h * ei)
            Hfd[:, i] = (gp - gm) / (2.0 * h)
        return 0.5 * (Hfd + Hfd.T)                 # symmetrise

    def curvature_manifold_indicator(self, X: np.ndarray) -> float:
        """λ_max(∇²E(X)) − 1  — zero on the curvature manifold C_man (§D.3).

        > 0 → curvature-dominated regime;
        < 0 → convex-dominated regime;
        = 0 → on C_man.
        """
        H = self.hessian(X)
        H = 0.5 * (H + H.T)
        return float(np.linalg.eigvalsh(H)[-1] - 1.0)

    def lambda_max_bound(self, X: np.ndarray, K_op_norm: float = 0.0) -> float:
        """Upper bound on λ_max(∇²E) — §Prop. 6.6:

            λ_max ≤ 2·M_G·‖J‖² + ‖K‖_op · ‖2GS‖

        ``K_op_norm`` is the operator norm ‖K‖_op of the curvature tensor;
        pass 0 if S is affine (K ≡ 0) — the bound then reduces to 2·M_G·‖J‖².
        """
        Jx = self.jacobian(X)
        s  = np.asarray(self.S(X), dtype=float)
        J_op = float(np.linalg.norm(Jx, ord=2))
        eta_norm = float(np.linalg.norm(2.0 * self.G @ s))
        return 2.0 * self._G_eigs[1] * J_op**2 + K_op_norm * eta_norm

    # ------------------------------------------------------------------
    # Stability metrics (§7.3 exponential rate, §7.4 ultimate bound)
    # ------------------------------------------------------------------
    def exponential_rate(self, X0: np.ndarray, sigma_min: float) -> float:
        """ρ = 4 σ² (μ_G²/M_G) (1 − γ_max)  — exponential decay (§Thm. 7.3).

        Valid when F_base ≡ 0 and the rank condition σ_min(J) ≥ σ holds on
        the operating sublevel set {E ≤ E(X0)}.

        Returns
        -------
        rho : float
            Lower bound on the energy decay rate so that E(t) ≤ E(0) e^{−ρt}.
        """
        mu_G, M_G = self._G_eigs
        gamma_max = self.gain(X0)
        return 4.0 * sigma_min**2 * (mu_G**2 / M_G) * (1.0 - gamma_max)

    def ultimate_bound_threshold(self, sigma_min: float) -> float:
        """Critical disturbance Ψ⋆ = σ θ μ_G / √M_G  — §Thm. 7.4 / Rmk 7.5.

        For ‖F_base‖ ≤ M with M < Ψ⋆ there exists a finite ultimate bound
        on E; the maximum of Ψ(R) is attained at R⋆ = θ.
        """
        mu_G, M_G = self._G_eigs
        return sigma_min * self.theta * mu_G / np.sqrt(M_G)

    def ultimate_bound(self, sigma_min: float, M: float) -> Optional[tuple[float, float]]:
        """Roots (R₋, R₊) of Ψ(R) = M from §Thm. 7.4.

        Returns ``None`` when M ≥ Ψ⋆ (no admissible window).
        """
        Psi_star = self.ultimate_bound_threshold(sigma_min)
        if M >= Psi_star:
            return None
        # Ψ(R) = (θ/(R+θ)) · 2σ μ_G √R / √M_G  =  M
        # Solve: 2σ μ_G √R · θ = M · (R+θ) · √M_G  →  quadratic in u = √R
        mu_G, M_G = self._G_eigs
        A = M * np.sqrt(M_G)
        B = -2.0 * sigma_min * mu_G * self.theta
        C = M * np.sqrt(M_G) * self.theta
        disc = B*B - 4.0 * A * C
        if disc < 0.0:
            return None
        sq = np.sqrt(disc)
        u_minus = (-B - sq) / (2.0 * A)
        u_plus  = (-B + sq) / (2.0 * A)
        return (float(u_minus**2), float(u_plus**2))


# =======================================================================
#  Integrator (§H.1.1 + §H.1.4 stopping & adaptive step)
# =======================================================================
@dataclass
class IntegrationResult:
    """Output of :meth:`CanonicalSystem.integrate`."""
    X_final: np.ndarray
    trajectory: np.ndarray         # shape (T+1, n)
    energy: np.ndarray             # shape (T+1,)
    grad_norm: np.ndarray          # shape (T+1,)
    converged: bool
    n_steps: int


def _integrate(sys: CanonicalSystem,
               X0: np.ndarray,
               h: float,
               max_steps: int,
               *,
               adaptive: bool,
               eps_E: float,
               eps_g: float,
               dwell: int,
               K_op_norm: float,
               record: bool) -> IntegrationResult:
    """Forward-Euler integrator implementing §H.1.1 + §H.1.4."""
    X = np.array(X0, dtype=float, copy=True)
    traj = [X.copy()] if record else []
    Ehist, gnorm = [sys.energy(X)], [float(np.linalg.norm(sys.gradient(X)))]
    dwell_count = 0
    converged = False
    h0 = h
    for t in range(max_steps):
        # §H.1.4 adaptive step: h_t = h_0 / (1 + λ_max(∇²E))
        if adaptive:
            lam = sys.lambda_max_bound(X, K_op_norm=K_op_norm)
            h_t = h0 / (1.0 + max(lam, 0.0))
        else:
            h_t = h0
        Xdot = sys.rhs(X)
        X = X + h_t * Xdot
        E   = sys.energy(X)
        gn  = float(np.linalg.norm(sys.gradient(X)))
        if record:
            traj.append(X.copy())
        Ehist.append(E)
        gnorm.append(gn)
        # §H.1.1 step 11 — stopping criterion (E < ε_E AND ‖g_X‖ < ε_g for τ steps)
        if E < eps_E and gn < eps_g:
            dwell_count += 1
            if dwell_count >= dwell:
                converged = True
                break
        else:
            dwell_count = 0
    return IntegrationResult(
        X_final=X,
        trajectory=np.array(traj) if record else np.empty((0, X.size)),
        energy=np.array(Ehist),
        grad_norm=np.array(gnorm),
        converged=converged,
        n_steps=t + 1,
    )


# Bind as a method on CanonicalSystem
def integrate(self: CanonicalSystem,
              X0: np.ndarray,
              h: float = 1e-2,
              max_steps: int = 10_000,
              *,
              adaptive: bool = False,
              eps_E: float = 1e-8,
              eps_g: float = 1e-6,
              dwell: int = 5,
              K_op_norm: float = 0.0,
              record: bool = True) -> IntegrationResult:
    """Forward-Euler integrate the canonical ODE (§H.1.1 + §H.1.4).

    Default tolerances ``ε_E=1e-8``, ``ε_g=1e-6``, ``τ=5`` follow §H.1.4.

    Parameters
    ----------
    X0 : (n,) ndarray            initial state.
    h : float, default 1e-2      base step size h₀.
    max_steps : int              hard cap on iterations.
    adaptive : bool              if True, scale step by 1/(1+λ_max(∇²E)) (§H.1.4).
    eps_E, eps_g, dwell          stopping criterion (§H.1.1 step 11).
    K_op_norm : float            ‖K‖_op for the adaptive bound; 0 if S affine.
    record : bool                if False, do not store trajectory (saves memory).
    """
    return _integrate(self, X0, h, max_steps,
                      adaptive=adaptive, eps_E=eps_E, eps_g=eps_g,
                      dwell=dwell, K_op_norm=K_op_norm, record=record)


CanonicalSystem.integrate = integrate  # type: ignore[attr-defined]
