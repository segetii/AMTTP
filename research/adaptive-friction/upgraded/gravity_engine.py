"""
gravity_engine.py  (pipeline version)
======================================
Self-contained GravityEngine implementation for the empirical pipeline.
Matches the mathematical specification in main.tex ?4-?5 exactly.

Key quantities computed per time step t:
    Phi(X)          - total potential energy
    grad_Phi(X)     - restoring force field  (N ? d)
    lambda_max(t)   - leading eigenvalue of D??_pair (power iteration)
    gamma_star(t)   - canonical guardian  lambda_max / (lambda_max + alpha) ∈ [0,1)
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
    unit = diff / (dist[:, :, None] + eps)  # (N, N, d)  unit direction i<-j

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
        """||nabla E_BS(X)||_F - Frobenius norm of gradient as detection score."""
        return float(np.linalg.norm(self.gradient(X)))


class BSDTChannelOperator(BSDTOperator):
    """
    Full 4-channel BSDT decomposition (section XXIV.4).

    Four risk channels  g_t = (g_C, g_G, g_A, g_T) in R^4  with unit-normalised
    state-space Jacobians  J_k in R^{N x d}:

        C - Contagion : g_C = lambda_max(W_LW),  J_C = v_W[:,None] / sqrt(d)
        G - Geometry  : g_G = ||nabla E_BS||_F,  J_G = nabla E_BS / ||nabla E_BS||_F
        A - Activity  : g_A = ||F||_F,            J_A = F / ||F||_F
        T - Topology  : g_T = lambda_max(D^2 Phi),J_T = v_H / ||v_H||_F

    State-space pullback:  G_tilde_t = g_C*J_C + g_G*J_G + g_A*J_A + g_T*J_T

    MFLS_ch(t) = max_{L-window} ||g_t||_2        (channel space,  section XXIV.4)
    MFLS_st(t) = max_{L-window} ||G_tilde_t||_F  (physical space, section XXIV.4)
    """

    def __init__(self, v_W: np.ndarray | None = None) -> None:
        """
        v_W : (N,) leading eigenvector of LW correlation network W.
              Call network_builder.leading_eigenvec(W) to obtain it.
              If None, falls back to uniform 1/sqrt(N).
        """
        super().__init__()
        self._v_W: np.ndarray | None = None
        if v_W is not None:
            self.set_network_eigvec(v_W)

    def set_network_eigvec(self, v_W: np.ndarray) -> None:
        """Set (or update) the LW-network leading eigenvector."""
        self._v_W = v_W / (np.linalg.norm(v_W) + 1e-12)

    def _v_W_for(self, N: int) -> np.ndarray:
        """Return stored v_W if compatible, else uniform fallback."""
        if self._v_W is not None and len(self._v_W) == N:
            return self._v_W
        return np.ones(N) / np.sqrt(float(N))

    def channel_vec(
        self,
        X: np.ndarray,
        F: np.ndarray,
        lam_hess: float,
        lam_W: float,
    ) -> np.ndarray:
        """
        Channel intensity vector  g_t = (g_C, g_G, g_A, g_T) in R^4.

        X        : (N, d) current state
        F        : (N, d) restoring force -nabla Phi(X)  (pre-computed)
        lam_hess : scalar  lambda_max(D^2 Phi_pair)
        lam_W    : scalar  lambda_max(W_LW)  (fixed for the panel run)
        """
        g_G = float(np.linalg.norm(self.gradient(X)))  # ||nabla E_BS||_F
        g_A = float(np.linalg.norm(F))                 # ||F||_F
        return np.array([float(lam_W), g_G, g_A, float(lam_hess)])

    def G_tilde(
        self,
        X: np.ndarray,
        F: np.ndarray,
        v_hess: np.ndarray,
        lam_hess: float,
        lam_W: float,
    ) -> np.ndarray:
        """
        State-space pullback  G_tilde_t = sum_k g_k J_k  in R^{N x d}  (section XXIV.4).

        Jacobians (unit-normalised in ||.||_F):
            J_C = v_W[:,None] / sqrt(d)     (eigenvec x uniform feature direction)
            J_G = nabla E_BS / ||nabla E_BS||_F   (unit blind-spot gradient)
            J_A = F / ||F||_F               (unit restoring-force direction)
            J_T = v_H / ||v_H||_F           (unit Hessian leading eigenvector)

        F      : (N, d) restoring force  (pre-computed, avoids redundant call)
        v_hess : (N, d) leading Hessian eigenvector  (pre-computed)
        """
        N, d = X.shape
        EPS_ = 1e-12
        grad_bs = self.gradient(X)           # (N, d)  2 Sigma0_inv (X - mu0)
        g_C = float(lam_W)
        g_G = float(np.linalg.norm(grad_bs))
        g_A = float(np.linalg.norm(F))
        g_T = float(lam_hess)
        v_W = self._v_W_for(N)
        J_C = v_W[:, None] * (np.ones((1, d)) / np.sqrt(float(d)))
        J_G = grad_bs / (g_G + EPS_)
        J_A = F       / (g_A + EPS_)
        J_T = v_hess  / (np.linalg.norm(v_hess) + EPS_)
        return g_C * J_C + g_G * J_G + g_A * J_A + g_T * J_T   # (N, d)


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
        gamma_star   (T,)  - canonical guardian λ/(λ+α) ∈ [0,1)
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
        gamma_star[t] = lam / (lam + alpha)   # canonical guardian: λ/(λ+α) ∈ [0,1)
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


def analyse_trajectory_full(
    X_series: np.ndarray,
    mu: np.ndarray,
    bsdt: "BSDTChannelOperator",
    lam_W: float,
    alpha: float = ALPHA,
    lead_window: int = 4,
    theta: float = 0.10,
    M_max: float = 1.0,
    n_power_iter: int = 20,
    verbose: bool = False,
) -> dict[str, np.ndarray]:
    """
    Full 4-channel BSDT trajectory analysis with admissibility (section 12, XXIV.4, XXVI.1).

    Parameters
    ----------
    X_series    : (T, N, d)
    mu          : (d,) normal-period equilibrium mean
    bsdt        : BSDTChannelOperator (fitted, v_W set via set_network_eigvec)
    lam_W       : lambda_max(W_LW) -- LW network spectral radius (scalar, fixed)
    lead_window : L quarters for windowed max (default 4Q)
    theta       : CGS damping parameter theta (default = ALPHA = 0.10)
    M_max       : perturbation bound M_max normalised (default 1.0)

    Returns all keys from analyse_trajectory, plus:
        g_ch          (T, 4)  channel vector g_t = (g_C, g_G, g_A, g_T)
        G_tilde_F     (T,)    ||G_tilde_t||_F  instantaneous (before windowing)
        mfls_ch       (T,)    MFLS_ch = max_{L} ||g_t||_2        (channel space)
        mfls_st       (T,)    MFLS_st = max_{L} ||G_tilde_t||_F  (physical space)
        admissibility (T,)    A = MFLS_st / sqrt(E)               (section 12)
        safety        (T,)    rho_safety = theta*MFLS_st/(2*M_max*sqrt(E))
        rho_mfls      (T,)    rho_MFLS = MFLS_st / MFLS_ch       (section XXIV.4)
        psi_deg       (T,)    psi_t = arccos(min(1, rho_MFLS)) degrees (section XXVI.1)
        lmax_series   (T,)    alias of lambda_max (backward-compat)
    """
    T, N, d = X_series.shape
    rng  = np.random.default_rng(42)
    EPS_ = 1e-12

    energy     = np.zeros(T)
    mfls_raw   = np.zeros(T)
    lambda_max = np.zeros(T)
    gamma_star = np.zeros(T)
    above_cman = np.zeros(T, dtype=bool)
    cos_theta  = np.zeros(T)
    force_norm = np.zeros(T)
    g_ch       = np.zeros((T, 4))
    G_tilde_F  = np.zeros(T)

    _lam_cache: float      = 1e-6
    _vH_cache: np.ndarray  = np.zeros((N, d))

    for t in range(T):
        X    = X_series[t]
        if verbose and t % 20 == 0:
            print(f"  t={t:3d}/{T}")

        mu_t       = X.mean(axis=0)
        energy[t]  = total_energy(X, mu, alpha=alpha)
        F          = total_force(X, mu_t, alpha=alpha)
        force_norm[t] = float(np.linalg.norm(F))

        G_bsdt      = bsdt.gradient(X)                    # nabla E_BS  (N, d)
        mfls_raw[t] = float(np.linalg.norm(G_bsdt))
        norm_g  = np.linalg.norm(G_bsdt, axis=1)
        norm_f  = np.linalg.norm(F,      axis=1)
        cos_theta[t] = float(
            np.mean(np.sum(G_bsdt * F, axis=1) / (norm_g * norm_f + EPS_))
        )

        if t % 4 == 0:
            _lam_cache, _vH_cache = spectral_radius(X, K=n_power_iter, rng=rng)
        lambda_max[t] = _lam_cache
        gamma_star[t] = _lam_cache / (_lam_cache + alpha)   # canonical guardian
        above_cman[t] = _lam_cache > alpha

        # --- 4-channel decomposition ---
        g_ch[t]      = bsdt.channel_vec(X, F, _lam_cache, lam_W)
        G_tilde_F[t] = float(np.linalg.norm(
            bsdt.G_tilde(X, F, _vH_cache, _lam_cache, lam_W)
        ))

    # Windowed max  (section XXIV.4, section 12)
    L = max(1, lead_window)
    mfls_ch = np.empty(T)
    mfls_st = np.empty(T)
    for t in range(T):
        lo = max(0, t - L + 1)
        mfls_ch[t] = float(np.max(np.linalg.norm(g_ch[lo:t + 1], axis=1)))
        mfls_st[t] = float(np.max(G_tilde_F[lo:t + 1]))

    # Admissibility and safety  (section 12)
    sqrt_E        = np.sqrt(np.maximum(energy, 0.0)) + EPS_
    admissibility = mfls_st / sqrt_E
    safety        = theta * mfls_st / (2.0 * M_max * sqrt_E)

    # Amplification and misalignment angle  (section XXIV.4, section XXVI.1)
    rho_mfls = mfls_st / np.where(mfls_ch > EPS_, mfls_ch, EPS_)
    psi_deg  = np.degrees(np.arccos(np.minimum(1.0, rho_mfls)))

    return {
        "energy":        energy,
        "mfls":          mfls_raw,
        "lambda_max":    lambda_max,
        "lmax_series":   lambda_max,       # backward-compat alias
        "gamma_star":    gamma_star,
        "above_cman":    above_cman,
        "cos_theta":     cos_theta,
        "force_norm":    force_norm,
        "g_ch":          g_ch,
        "G_tilde_F":     G_tilde_F,
        "mfls_ch":       mfls_ch,
        "mfls_st":       mfls_st,
        "admissibility": admissibility,
        "safety":        safety,
        "rho_mfls":      rho_mfls,
        "psi_deg":       psi_deg,
    }
