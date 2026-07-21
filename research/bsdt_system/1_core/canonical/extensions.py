"""Extensions — Part II (App. D–F) and Part III (App. H–K) of canonical_system_v4.

Every extension changes ONLY the triple (S, G, F_base); the canonical ODE,
the gradient formula g_X = 2JᵀGS, and the Euclidean projection are
unchanged.  See §G (LOCKED): "In every v3 extension g_X = 2JᵀGS, the
projection is Euclidean, and Rules 1–4 are obeyed."

* App. D :class:`FractalRepresentation`     — multi-scale mollified distance
* App. E :class:`ContactRepresentation`     — Reeb-aware feature map
* App. F :class:`GeometricFlowMetric`       — time-varying G via Ricci flow
* App. H :class:`FisherInformationMetric`   — Fisher G(X) = I_S(S(X))
* NG.1   :func:`natural_gradient`           — auxiliary chart-covariant flow
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence
import numpy as np

from .core import CanonicalSystem


# =======================================================================
#  Appendix D — Fractal-Geometric Extension
# =======================================================================
@dataclass
class FractalRepresentation:
    """§D — Multi-scale mollified distance to a (possibly fractal) target A.

        S_frac(X) = ( d_{δ_1}(X), …, d_{δ_L}(X) ) ∈ Rᴸ   (§F.1)
        G_frac    = diag( δ_1^{−2 d_H}, …, δ_L^{−2 d_H} )

    where d_δ(X) = inf_{Y∈A_δ} ‖X − Y‖ is the molli(cid:28)ed distance to the δ-
    thickening A_δ of A, and d_H ∈ (0, n) is the Hausdorff dimension of A.

    Parameters
    ----------
    dist_fn : callable (X, δ) ↦ d_δ(X)  ∈ R≥0.
        Mollified distance to the target at scale δ.  Must be C² off the
        cut locus (Federer's tubular-neighbourhood theorem).
    grad_dist_fn : optional callable (X, δ) ↦ ∇_X d_δ(X) ∈ Rⁿ.
        If None, central finite differences are used.
    deltas : sequence of L positive scales δ_1 > δ_2 > … > δ_L > 0.
    d_H : float ∈ (0, n)
        Hausdorff dimension of the target A.
    """
    dist_fn: Callable[[np.ndarray, float], float]
    deltas: Sequence[float]
    d_H: float
    grad_dist_fn: Optional[Callable[[np.ndarray, float], np.ndarray]] = None
    F_base: Optional[Callable[[np.ndarray], np.ndarray]] = None
    theta: float = 1.0
    epsilon: float = 1e-12   # ε > 0 to handle the cut locus
    fd_step: float = 1e-6

    def build(self) -> CanonicalSystem:
        deltas = np.asarray(list(self.deltas), dtype=float)
        if (deltas <= 0).any():
            raise ValueError("all δ_ℓ must be > 0")
        if not np.all(deltas[:-1] > deltas[1:]):
            raise ValueError("δ_1 > δ_2 > … > δ_L required (Prop. D.1)")
        L = deltas.size
        # G_frac = diag(δ_ℓ^{−2 d_H})
        G = np.diag(deltas ** (-2.0 * self.d_H))
        df = self.dist_fn
        gdf = self.grad_dist_fn

        def S(X: np.ndarray) -> np.ndarray:
            return np.array([float(df(X, d)) for d in deltas])

        if gdf is not None:
            def J(X: np.ndarray) -> np.ndarray:
                return np.stack([np.asarray(gdf(X, d), dtype=float)
                                 for d in deltas], axis=0)
        else:
            J = None  # CanonicalSystem will use FD

        F_base = self.F_base if self.F_base is not None \
                 else (lambda X: np.zeros_like(X, dtype=float))
        return CanonicalSystem(S=S, J=J, G=G, F_base=F_base,
                               theta=self.theta, epsilon=self.epsilon,
                               fd_step=self.fd_step)


# =======================================================================
#  Appendix E — Contact-Geometric Extension
# =======================================================================
@dataclass
class ContactRepresentation:
    """§E — Reeb-aware feature map on a contact manifold (R^{2m+1}, α).

        S_ct(X) = ( Φ(X), α_X(F_base(X)) ) ∈ R^{k₀+1}    (§C.1)
        G_ct    = blockdiag(G_0, β),  β > 0

    Standard contact form  α = dz − Σ y_i dx_i  on R^{2m+1} with coordinates
    (x_1, …, x_m, y_1, …, y_m, z).  The horizontal-descent property of
    Prop. E.1 forces α(F_base) → 0 whenever Φ → 0 at the target.

    Parameters
    ----------
    Phi : callable X ↦ Φ(X) ∈ R^{k₀}   target encoded by Φ = 0.
    Phi_jac : optional callable X ↦ ∂Φ/∂X.  If None, FD.
    F_base : callable X ↦ F_base(X) ∈ R^{2m+1}.
    G0 : (k₀, k₀) SPD metric on the Φ-component.
    beta : float > 0, weight on the Reeb-component.
    m : int ≥ 1, the contact dimension (state space is R^{2m+1}).
    """
    Phi: Callable[[np.ndarray], np.ndarray]
    F_base: Callable[[np.ndarray], np.ndarray]
    G0: np.ndarray
    beta: float
    m: int
    Phi_jac: Optional[Callable[[np.ndarray], np.ndarray]] = None
    theta: float = 1.0
    epsilon: float = 0.0

    def build(self) -> CanonicalSystem:
        m = int(self.m)
        n = 2 * m + 1
        if self.beta <= 0.0:
            raise ValueError("beta must be > 0 (§C.1)")
        G0 = np.asarray(self.G0, dtype=float)
        k0 = G0.shape[0]
        # Standard contact 1-form  α_X(v) = v_z − Σ_i y_i v_{x_i}
        # Coordinate convention: X = (x_1..x_m, y_1..y_m, z).
        idx_x = np.arange(0, m)
        idx_y = np.arange(m, 2 * m)
        idx_z = 2 * m

        def alpha_X(X: np.ndarray, v: np.ndarray) -> float:
            return float(v[idx_z] - np.dot(X[idx_y], v[idx_x]))

        Phi = self.Phi
        Fb  = self.F_base

        def S(X: np.ndarray) -> np.ndarray:
            phi_val = np.asarray(Phi(X), dtype=float)
            reeb    = alpha_X(X, np.asarray(Fb(X), dtype=float))
            return np.concatenate([phi_val, [reeb]])

        # Jacobian: top block ∂Φ/∂X (k₀×n); bottom row ∂[α_X(F_base)]/∂X (1×n)
        # We compute the bottom row by FD always (depends on F_base + α_X
        # nonlinearly through y_i F_base_{x_i}).
        if self.Phi_jac is not None:
            J_phi = self.Phi_jac
        else:
            J_phi = None  # rely on FD path inside CanonicalSystem? No, J must
                          # be the joint (k₀+1, n) Jacobian — supply explicitly.
        def J(X: np.ndarray) -> np.ndarray:
            # Top block
            if J_phi is not None:
                Jp = np.asarray(J_phi(X), dtype=float)
            else:
                h = 1e-6
                Phi0 = np.asarray(Phi(X), dtype=float)
                Jp = np.empty((Phi0.size, n))
                for i in range(n):
                    ei = np.zeros(n); ei[i] = 1.0
                    pp = np.asarray(Phi(X + h * ei), dtype=float)
                    pm = np.asarray(Phi(X - h * ei), dtype=float)
                    Jp[:, i] = (pp - pm) / (2.0 * h)
            # Bottom row by FD on alpha_X(F_base(X))
            h = 1e-6
            Jb = np.empty(n)
            for i in range(n):
                ei = np.zeros(n); ei[i] = 1.0
                rp = alpha_X(X + h * ei, np.asarray(Fb(X + h * ei), dtype=float))
                rm = alpha_X(X - h * ei, np.asarray(Fb(X - h * ei), dtype=float))
                Jb[i] = (rp - rm) / (2.0 * h)
            return np.vstack([Jp, Jb])

        # G_ct = blockdiag(G_0, β)
        G_ct = np.zeros((k0 + 1, k0 + 1))
        G_ct[:k0, :k0] = G0
        G_ct[k0, k0]   = float(self.beta)

        return CanonicalSystem(S=S, J=J, G=G_ct, F_base=Fb,
                               theta=self.theta, epsilon=self.epsilon)


# =======================================================================
#  Appendix F — Geometric-Flow Extension (time-varying metric)
# =======================================================================
@dataclass
class GeometricFlowMetric:
    """§F — Time-varying metric evolved by a Ricci-type flow:

        Ġ = −2 Ric(G; X) + σ · ( G_⋆(X) − G )           (§GF.1)

    with σ ≥ 0 the relaxation rate and G_⋆ the target metric.  The state
    flow is the canonical ODE with the *current* G; the metric flow is
    integrated alongside via Lie–Trotter splitting (§F.4).

    Lemma F.1: Ė = (1−γ)(⟨g_X, F_base⟩ − ‖g_X‖²) + Sᵀ Ġ S.

    Parameters
    ----------
    G0 : (k, k) initial SPD metric.
    Ric : callable (G, X) ↦ Ric(G; X) ∈ Rᵏˣᵏ_sym.  Default ``lambda G,X: 0``.
    G_star : callable X ↦ G_⋆(X) ∈ Rᵏˣᵏ SPD.  Default ``lambda X: G0``.
    sigma_rel : float ≥ 0.
    S, J, F_base : as in CanonicalSystem.
    """
    G0: np.ndarray
    S: Callable[[np.ndarray], np.ndarray]
    F_base: Callable[[np.ndarray], np.ndarray]
    J: Optional[Callable[[np.ndarray], np.ndarray]] = None
    Ric: Optional[Callable[[np.ndarray, np.ndarray], np.ndarray]] = None
    G_star: Optional[Callable[[np.ndarray], np.ndarray]] = None
    sigma_rel: float = 1.0
    theta: float = 1.0
    epsilon: float = 0.0

    def __post_init__(self):
        self._G_t = np.array(self.G0, dtype=float, copy=True)
        if self.Ric is None:
            self.Ric = lambda G, X: np.zeros_like(G)
        if self.G_star is None:
            self.G_star = lambda X: self.G0
        if self.sigma_rel < 0.0:
            raise ValueError("sigma_rel must be ≥ 0 (§F.1)")

    @property
    def G_current(self) -> np.ndarray:
        return self._G_t

    def build(self) -> CanonicalSystem:
        """Snapshot — returns a CanonicalSystem with the *current* G_t.

        Call :meth:`metric_step` to advance the metric, then re-build the
        system whenever you need the updated G.  Equivalent: use the
        :meth:`coupled_step` helper which advances state+metric together.
        """
        return CanonicalSystem(S=self.S, J=self.J, G=self._G_t,
                               F_base=self.F_base,
                               theta=self.theta, epsilon=self.epsilon)

    def metric_step(self, X: np.ndarray, h: float) -> np.ndarray:
        """One explicit-Euler half-step of the metric flow (§F.4)."""
        R   = np.asarray(self.Ric(self._G_t, X), dtype=float)
        Gst = np.asarray(self.G_star(X), dtype=float)
        Gdot = -2.0 * R + self.sigma_rel * (Gst - self._G_t)
        Gnew = self._G_t + h * Gdot
        # symmetrise; project to PD by clipping eigenvalues to ≥ μ_min
        Gnew = 0.5 * (Gnew + Gnew.T)
        eigs, U = np.linalg.eigh(Gnew)
        eigs = np.clip(eigs, 1e-12, None)
        self._G_t = U @ np.diag(eigs) @ U.T
        return self._G_t

    def coupled_step(self, X: np.ndarray, h: float) -> np.ndarray:
        """Lie–Trotter step (§F.4): state half-step (frozen G), metric half-step."""
        sys = self.build()
        Xnew = X + h * sys.rhs(X)
        self.metric_step(Xnew, h)
        return Xnew


# =======================================================================
#  Appendix H — Fisher Information Metric (Part III)
# =======================================================================
@dataclass
class FisherInformationMetric:
    """§H — Specialise the v3 metric flow with the Fisher information metric.

        G(X) := I_S( S(X) ) ,    I_S(z) = E[u(y;z) u(y;z)ᵀ]   (§IG.1)

    The canonical ODE, the formula g_X = 2JᵀGS, and the Euclidean
    projection are unchanged.  See §H.2 (F1) tracking schedule.

    Parameters
    ----------
    S : callable X ↦ S(X) ∈ Rᵏ.
    J : optional callable X ↦ J(X) ∈ Rᵏˣⁿ.
    fisher_info : callable z ↦ I_S(z) ∈ Rᵏˣᵏ_PD.
        The feature-space Fisher information matrix.
    F_base : callable X ↦ F_base(X) ∈ Rⁿ.
    """
    S: Callable[[np.ndarray], np.ndarray]
    fisher_info: Callable[[np.ndarray], np.ndarray]
    F_base: Callable[[np.ndarray], np.ndarray]
    J: Optional[Callable[[np.ndarray], np.ndarray]] = None
    theta: float = 1.0
    epsilon: float = 1e-12

    def G_at(self, X: np.ndarray) -> np.ndarray:
        z = np.asarray(self.S(X), dtype=float)
        Iz = np.asarray(self.fisher_info(z), dtype=float)
        Iz = 0.5 * (Iz + Iz.T)
        return Iz

    def build(self, X_calib: np.ndarray) -> CanonicalSystem:
        """Build a CanonicalSystem with G frozen at X_calib (snapshot).

        For the (F1) tracking schedule of §H.2, rebuild on each major step.
        For (F2) relaxation use :class:`GeometricFlowMetric` with
        G_star(X) = I_S(S(X)) and σ_rel > 0.
        """
        G = self.G_at(np.asarray(X_calib, dtype=float))
        return CanonicalSystem(S=self.S, J=self.J, G=G, F_base=self.F_base,
                               theta=self.theta, epsilon=self.epsilon)

    def pullback(self, X: np.ndarray) -> np.ndarray:
        """Pullback Fisher metric on state space:  I_X = Jᵀ I_S J  ∈ Rⁿˣⁿ.

        Used in :func:`natural_gradient` (§NG.1).  By Rule 3 this object
        appears here ONLY as an auxiliary; it never enters the locked ODE.
        """
        sys = self.build(X)            # snapshot G at X
        Jx = sys.jacobian(X)
        Iz = self.G_at(X)
        return Jx.T @ Iz @ Jx


# =======================================================================
#  §NG.1 — Auxiliary natural-gradient flow (extension, breaks Rule 2)
# =======================================================================
def natural_gradient(fim: FisherInformationMetric,
                     X: np.ndarray,
                     *,
                     reg: float = 1e-10) -> np.ndarray:
    """Auxiliary natural gradient  g̃_X = I_X† g_X  (§NG.1).

    NOT used by the locked canonical ODE (Rule 2 — Euclidean projection).
    Provided for the chart-covariant variant of §K.1 / Theorem I.1:

        Ẋ = −g̃_X(X)            (chart-covariant; an extension)

    Uses Tikhonov regularisation when I_X is rank-deficient.

    Returns
    -------
    g_tilde : (n,) ndarray
        Natural-gradient direction in state space.
    """
    sys = fim.build(X)
    gX  = sys.gradient(X)
    Ix  = fim.pullback(X)
    n = X.size
    A = Ix + reg * np.eye(n)
    return np.linalg.solve(A, gX)


# =======================================================================
#  §9.3 — Information-geometric Hessian (state-dependent G via Fisher)
# =======================================================================
def info_geometric_hessian(fim: "FisherInformationMetric",
                           X: np.ndarray,
                           *,
                           h: float = 1e-5) -> np.ndarray:
    r"""§9.3 — Hessian of E(X) = S(X)ᵀ I_S(S(X)) S(X) when G depends on X.

    For G(X) = I_S(S(X)) the flat Euclidean Hessian acquires three extra
    terms beyond the constant-G formula 2JᵀGJ + ⟨η,K⟩₁:

        (∇²E)_{ab} = 2(JᵀI_S J)_{ab} + η_i K^i_{ab}
                   + 2 (∂_a I_{S,ij}) J^j_b S^i
                   + 2 (∂_b I_{S,ij}) J^j_a S^i
                   + S^i (∂_a∂_b I_{S,ij}) S^j

    where η = 2 I_S S, and ∂_a means ∂/∂X_a.  The last term vanishes for
    exponential families in canonical coordinates.  On the target set
    {S = 0} all three corrections vanish and ∇²E = 2 I_X.

    This is computed by finite-differencing E(X) directly, which is
    exact (up to FD truncation) and captures every term automatically.
    Provided alongside the closed-form for verification and for the
    Hessian-aware adaptive step of §H.1.4.
    """
    n = X.size
    def E_at(Xi: np.ndarray) -> float:
        z = np.asarray(fim.S(Xi), dtype=float)
        Iz = np.asarray(fim.fisher_info(z), dtype=float)
        return float(z @ (0.5 * (Iz + Iz.T)) @ z)
    H = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            ei = np.zeros(n); ei[i] = 1.0
            ej = np.zeros(n); ej[j] = 1.0
            Epp = E_at(X + h*ei + h*ej); Emm = E_at(X - h*ei - h*ej)
            Epm = E_at(X + h*ei - h*ej); Emp = E_at(X - h*ei + h*ej)
            H[i, j] = (Epp - Epm - Emp + Emm) / (4 * h * h)
    return 0.5 * (H + H.T)


# =======================================================================
#  §10.1 — Natural-gradient variant flow  Ẋ = −g̃_X
# =======================================================================
@dataclass
class NaturalGradientFlow:
    r"""§10.1 — Chart-covariant natural-gradient flow (extension, breaks Rule 2).

        Ẋ = −g̃_X(X) = −I_X(X)†  g_X(X)

    By Theorem I.1 / Theorem 7.1 of Part III the trajectory of this flow
    is chart-covariant: under X = Φ(X̃) with T = ∂Φ/∂X̃, X̃(t) = Φ⁻¹(X(t)).

    NOTE.  This is *not* the locked canonical ODE.  It is provided as an
    explicit auxiliary integrator alongside the locked CanonicalSystem.
    Use only when chart invariance is required (e.g. for MLE in
    log-parameter coordinates or VI in natural-parameter coordinates).
    """
    fim: FisherInformationMetric
    reg: float = 1e-10

    def rhs(self, X: np.ndarray) -> np.ndarray:
        return -natural_gradient(self.fim, X, reg=self.reg)

    def integrate(self,
                  X0: np.ndarray,
                  *,
                  h: float = 0.01,
                  max_steps: int = 5000,
                  eps_E: float = 1e-10,
                  eps_g: float = 1e-7,
                  dwell: int = 5,
                  record: bool = False):
        """Forward-Euler integration of Ẋ = −g̃_X.

        Stops when E < eps_E and ‖g_X‖ < eps_g for `dwell` consecutive steps.
        """
        from .core import IntegrationResult
        X = np.asarray(X0, dtype=float).copy()
        traj = [X.copy()] if record else []
        sys_snap = self.fim.build(X)
        E_t = sys_snap.energy(X)
        g_t = float(np.linalg.norm(sys_snap.gradient(X)))
        E_hist = [E_t]
        g_hist = [g_t]
        good = 0
        converged = False
        last_step = max_steps
        for step in range(1, max_steps + 1):
            X = X + h * self.rhs(X)
            sys_snap = self.fim.build(X)
            E_t = sys_snap.energy(X)
            g_t = float(np.linalg.norm(sys_snap.gradient(X)))
            E_hist.append(E_t)
            g_hist.append(g_t)
            if record:
                traj.append(X.copy())
            if E_t < eps_E and g_t < eps_g:
                good += 1
                if good >= dwell:
                    converged = True
                    last_step = step
                    break
            else:
                good = 0
        return IntegrationResult(
            X_final=X,
            trajectory=np.array(traj) if record else np.empty((0, X.size)),
            energy=np.array(E_hist),
            grad_norm=np.array(g_hist),
            converged=converged,
            n_steps=last_step,
        )


# =======================================================================
#  §10.2 — MLE & VI as canonical instances
# =======================================================================
@dataclass
class MLEInstance:
    r"""§10.2 — Maximum-likelihood estimation as a canonical instance.

    In local asymptotic-normal (LAN) coordinates around the MLE X⋆:

        S(X) = X − X⋆ ,   G = I_S(S(X)) ,   F_base ≡ 0

    yields E = SᵀI_S S, the quadratic log-likelihood error, and the
    natural-gradient variant flow recovers Fisher scoring locally.

    Parameters
    ----------
    X_mle : (n,) array — the MLE point X⋆.
    fisher_info : callable z ↦ I_S(z) ∈ Rⁿˣⁿ_PD  (n = k here since S = X − X⋆).
    """
    X_mle: np.ndarray
    fisher_info: Callable[[np.ndarray], np.ndarray]
    theta: float = 1.0

    def fim(self) -> FisherInformationMetric:
        x_star = np.asarray(self.X_mle, dtype=float)
        n = x_star.size
        return FisherInformationMetric(
            S=lambda X: X - x_star,
            J=lambda X: np.eye(n),
            fisher_info=self.fisher_info,
            F_base=lambda X: np.zeros_like(X, dtype=float),
            theta=self.theta,
        )

    def fisher_scoring(self) -> NaturalGradientFlow:
        """Local Fisher-scoring flow (the natural-gradient variant)."""
        return NaturalGradientFlow(fim=self.fim())


@dataclass
class VIInstance:
    r"""§10.2 — Variational inference as a canonical instance.

    In natural-parameter coordinates λ(X) of the variational family q_X
    (with target λ⋆ = argmin KL(q‖p)):

        S(X) = λ(X) − λ⋆ ,    G = I_S(S(X)) ,    F_base ≡ 0

    so E is the local Fisher quadratic approximation to the negative
    ELBO; the natural-gradient variant flow Ẋ = −g̃_X is natural-gradient VI.

    Parameters
    ----------
    lam : callable X ↦ λ(X) ∈ Rᵏ.
    lam_star : (k,) target natural parameter λ⋆.
    fisher_info : callable z ↦ I_S(z) ∈ Rᵏˣᵏ_PD.
    lam_jac : optional callable X ↦ ∂λ/∂X ∈ Rᵏˣⁿ.  If None, FD.
    """
    lam: Callable[[np.ndarray], np.ndarray]
    lam_star: np.ndarray
    fisher_info: Callable[[np.ndarray], np.ndarray]
    lam_jac: Optional[Callable[[np.ndarray], np.ndarray]] = None
    theta: float = 1.0

    def fim(self) -> FisherInformationMetric:
        l_star = np.asarray(self.lam_star, dtype=float)
        return FisherInformationMetric(
            S=lambda X: np.asarray(self.lam(X), dtype=float) - l_star,
            J=self.lam_jac,
            fisher_info=self.fisher_info,
            F_base=lambda X: np.zeros_like(X, dtype=float),
            theta=self.theta,
        )

    def natural_gradient_vi(self) -> NaturalGradientFlow:
        """Natural-gradient VI as the chart-covariant variant flow."""
        return NaturalGradientFlow(fim=self.fim())
