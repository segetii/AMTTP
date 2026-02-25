"""
N-Body Gravity Pull Clustering Engine
======================================
Physics-inspired gravitational clustering for anomaly detection.

Each data point is treated as a particle in an N-body system subject to:
  1. Radial pull toward the global centre (spring-like restoring force)
  2. Pairwise interaction: short-range attraction + close-range repulsion
  3. (Optional) Operator deviation pull from UDL spectrum operators

The system evolves via discrete Euler integration:
    X^{t+1} = X^t + η · F(X^t)

After sufficient iterations, normal points cluster together while
outliers are displaced to isolated positions. Convergence is
monitored empirically via displacement tolerance; the dynamics
are a computational heuristic, not a formal energy minimisation.

Formula
-------
F_i = −α(x_i − μ)                       [radial anchoring]
    − γ Σ_{j≠i} ∇K(x_i − x_j)          [pairwise interaction]
    − Σ_k β_k DΦ_k(x_i)^T D_k(x_i)     [operator deviation, optional]

Interaction kernel:
    K(r) = −exp(−r²/σ²) + λ/(r + ε)     [attraction + repulsion]

Author: Odeyemi Olusegun Israel
"""

from __future__ import annotations

import numpy as np
from sklearn.preprocessing import StandardScaler
from scipy.spatial import cKDTree
from typing import Optional, List, Tuple, Dict

# Import spectrum operators for built-in integration
try:
    from udl.spectra import ExponentialSpectrum
except ImportError:
    try:
        from spectra import ExponentialSpectrum
    except ImportError:
        ExponentialSpectrum = None

# ── Backend dispatch ──
# Centralised in udl.backend: JAX (XLA JIT + GPU) → CuPy → NumPy.
# No numba dependency — JAX replaces it with better perf + portability.
try:
    from udl.backend import xp, jit, vmap, to_numpy, BACKEND as _BACKEND
except ImportError:
    try:
        from backend import xp, jit, vmap, to_numpy, BACKEND as _BACKEND
    except ImportError:
        # Absolute fallback: no backend module at all
        xp = np
        _BACKEND = "numpy"
        def jit(fn=None, **kw):
            return fn if fn is not None else (lambda f: f)
        def vmap(fn=None, **kw):
            return fn if fn is not None else (lambda f: f)
        def to_numpy(arr):
            return np.asarray(arr)

def get_backend() -> str:
    """Return the active compute backend: 'numpy', 'jax', or 'cupy'."""
    return _BACKEND


# ---------------------------------------------------------------------------
# Interaction kernels
# ---------------------------------------------------------------------------

# ── JAX-accelerated pairwise force (replaces numba) ──
#
# When JAX is available, XLA compiles this into a fused GPU/CPU kernel
# with automatic cache-blocking, loop tiling, and SIMD vectorisation.
# When JAX is absent, @jit is a no-op and this runs as plain NumPy.

@jit
def _pairwise_forces_jax(X, gamma, sigma, lambda_rep, eps):
    """Fully-vectorised pairwise forces — JIT-compiled via XLA.

    XLA fuses the matmul, exp, and reduction into a single kernel.
    On CPU: automatic AVX-512 / NEON vectorisation + cache blocking.
    On GPU: compiled to CUDA/ROCm without user code changes.

    O(n²) but ~50-100× faster than a Python loop, and GPU-portable.
    """
    diff = X[:, None, :] - X[None, :, :]                     # (n, n, d)
    dist_sq = xp.sum(diff ** 2, axis=2, keepdims=True)       # (n, n, 1)
    dist = xp.sqrt(dist_sq) + eps                            # (n, n, 1)

    attraction = xp.exp(-dist_sq / (sigma * sigma))           # (n, n, 1)
    repulsion = lambda_rep / dist                             # (n, n, 1)
    magnitude = -gamma * (attraction - repulsion)             # (n, n, 1)

    unit = diff / dist                                        # (n, n, d)
    forces = xp.sum(magnitude * unit, axis=1)                 # (n, d)
    return forces


def _pairwise_forces_loop(X: np.ndarray,
                          gamma: float = 1.0,
                          sigma: float = 1.0,
                          lambda_rep: float = 0.1,
                          eps: float = 1e-5) -> np.ndarray:
    """O(n²) pairwise interaction forces — loop version (reference).

    Parameters
    ----------
    X : (n, d) array
    gamma : interaction strength
    sigma : attraction length-scale
    lambda_rep : repulsion coefficient
    eps : softening to avoid division by zero

    Returns
    -------
    forces : (n, d) array — net pairwise force on each particle
    """
    n = X.shape[0]
    forces = np.zeros_like(X)

    for i in range(n):
        diff = X[i] - X                         # (n, d)
        dist = np.linalg.norm(diff, axis=1, keepdims=True) + eps  # (n, 1)

        # Attraction: pulls neighbours within σ closer
        attraction = np.exp(-(dist ** 2) / (sigma ** 2))     # (n, 1)

        # Repulsion: prevents collapse at short range
        repulsion = lambda_rep / dist                         # (n, 1)

        # Net force magnitude (negative = attractive direction)
        magnitude = -gamma * (attraction - repulsion)         # (n, 1)

        # Direction-weighted sum (skip self via zero diff[i])
        forces[i] = np.sum(magnitude * (diff / dist), axis=0)

    return forces


def _pairwise_forces_vec(X: np.ndarray,
                         gamma: float = 1.0,
                         sigma: float = 1.0,
                         lambda_rep: float = 0.1,
                         eps: float = 1e-5) -> np.ndarray:
    """O(n²) pairwise interaction forces — fully vectorised.

    Broadcasts the full (n, n, d) difference tensor.
    Uses more memory but ~10-50× faster than the loop version.

    When running under JAX, this is equivalent to _pairwise_forces_jax
    but called without @jit (useful for debugging / tracing).
    """
    diff = xp.asarray(X)[:, None, :] - xp.asarray(X)[None, :, :]
    dist = xp.sqrt(xp.sum(diff ** 2, axis=2, keepdims=True)) + eps

    attraction = xp.exp(-(dist ** 2) / (sigma ** 2))
    repulsion = lambda_rep / dist
    magnitude = -gamma * (attraction - repulsion)

    unit = diff / dist
    forces = xp.sum(magnitude * unit, axis=1)
    return to_numpy(forces)


def _pairwise_forces_chunked(X: np.ndarray,
                             gamma: float = 1.0,
                             sigma: float = 1.0,
                             lambda_rep: float = 0.1,
                             eps: float = 1e-5,
                             chunk_size: int = 500) -> np.ndarray:
    """O(n²) pairwise forces via cache-blocked matrix ops.

    Processes blocks of `chunk_size` rows at a time to keep the
    working set in L2/L3 cache.  Still fully vectorised within each block.

    Memory: O(chunk_size × n × d) instead of O(n² × d).

    When JAX is active, XLA performs its own cache-blocking inside
    _pairwise_forces_jax, so this path is only taken as a NumPy fallback
    for large datasets that would OOM with the full (n,n,d) broadcast.
    """
    n, d = X.shape
    forces = np.zeros_like(X)
    X_xp = xp.asarray(X)

    for start in range(0, n, chunk_size):
        end = min(start + chunk_size, n)
        X_block = X_xp[start:end]                            # (b, d)

        diff = X_block[:, None, :] - X_xp[None, :, :]        # (b, n, d)
        dist = xp.sqrt(xp.sum(diff ** 2, axis=2, keepdims=True)) + eps

        attraction = xp.exp(-(dist ** 2) / (sigma ** 2))
        repulsion = lambda_rep / dist
        magnitude = -gamma * (attraction - repulsion)

        unit = diff / dist
        forces[start:end] = to_numpy(xp.sum(magnitude * unit, axis=1))

    return forces


def _pairwise_forces_knn(X: np.ndarray,
                        gamma: float = 1.0,
                        sigma: float = 1.0,
                        lambda_rep: float = 0.1,
                        k: int = 20,
                        eps: float = 1e-5,
                        tree: Optional[cKDTree] = None) -> np.ndarray:
    """kNN-limited pairwise forces — vectorised.

    Uses sklearn NearestNeighbors (auto-selects best algorithm for
    the data distribution).  Robust to clustered data.

    Parameters
    ----------
    X : (n, d) array
    gamma, sigma, lambda_rep : force parameters
    k : number of neighbours per point
    eps : softening constant
    tree : ignored (kept for API compatibility)

    Returns
    -------
    forces : (n, d) array
    """
    from sklearn.neighbors import NearestNeighbors

    n, d = X.shape
    k_eff = min(k, n - 1)

    # FP32 kNN search: BLAS distance calc uses half the memory bandwidth.
    # Neighbor indices are identical; physics stays in FP64.
    X_f32 = X.astype(np.float32)
    nn = NearestNeighbors(n_neighbors=k_eff + 1, algorithm='brute')
    nn.fit(X_f32)
    _, indices = nn.kneighbors(X_f32)

    # Skip self -> (n, k_eff)
    nbr_idx = indices[:, 1:]

    # Gather neighbour positions and compute differences vectorised
    X_nbrs = X[nbr_idx]                                # (n, k_eff, d)
    diff = X[:, None, :] - X_nbrs                       # (n, k_eff, d)
    dist = np.linalg.norm(diff, axis=2, keepdims=True) + eps  # (n, k_eff, 1)

    # Force computation — fully vectorised
    attraction = np.exp(-(dist ** 2) / (sigma ** 2))
    repulsion = lambda_rep / dist
    magnitude = -gamma * (attraction - repulsion)
    unit = diff / dist
    forces = np.sum(magnitude * unit, axis=1)           # (n, d)

    return forces


def pairwise_forces(X: np.ndarray,
                    gamma: float = 1.0,
                    sigma: float = 1.0,
                    lambda_rep: float = 0.1,
                    eps: float = 1e-5,
                    k_neighbors: int = 0,
                    tree: Optional[cKDTree] = None) -> Tuple[np.ndarray, Optional[cKDTree]]:
    """Compute pairwise N-body interaction forces.

    Auto-selects the fastest available implementation:
      1. k_neighbors > 0 → chunked brute-force kNN (O(n²d/chunk), robust)
      2. n ≤ 800          → fully vectorised (fits in memory)
      3. Numba available  → JIT-parallelised loop (~50× vs numpy loop)
      4. n ≤ 5000         → chunked vectorised (blocks of 500)
      5. fallback         → numpy loop

    Returns
    -------
    (forces, tree) : ((n,d) array, None)
        tree is always None now (brute-force kNN needs no tree).
    """
    if k_neighbors > 0:
        f = _pairwise_forces_knn(X, gamma, sigma, lambda_rep, k_neighbors, eps)
        return f, None

    n = X.shape[0]

    # Dispatch strategy:
    #   JAX available + n ≤ 5000  →  @jit XLA kernel (fastest, auto cache-blocks)
    #   JAX available + n > 5000  →  chunked with xp (avoids OOM on GPU)
    #   NumPy only + n ≤ 800     →  full vectorised broadcast
    #   NumPy only + n ≤ 5000    →  chunked vectorised
    #   NumPy only + n > 5000    →  loop (low memory)
    if _BACKEND == "jax":
        if n <= 5000:
            f = _pairwise_forces_jax(xp.asarray(X), gamma, sigma, lambda_rep, eps)
            return to_numpy(f), None
        else:
            return _pairwise_forces_chunked(X, gamma, sigma, lambda_rep, eps), None

    if n <= 800:
        return _pairwise_forces_vec(X, gamma, sigma, lambda_rep, eps), None
    if n <= 5000:
        return _pairwise_forces_chunked(X, gamma, sigma, lambda_rep, eps), None
    return _pairwise_forces_loop(X, gamma, sigma, lambda_rep, eps), None


# ---------------------------------------------------------------------------
# Radial pull
# ---------------------------------------------------------------------------

def radial_pull(X: np.ndarray, mu: np.ndarray, alpha: float = 0.1) -> np.ndarray:
    """Spring-like restoring force toward the global centre.

    F_radial = −α (x_i − μ)

    Parameters
    ----------
    X : (n, d) array
    mu : (d,) array — global centroid
    alpha : spring constant

    Returns
    -------
    force : (n, d) array
    """
    return -alpha * (X - mu)


# ---------------------------------------------------------------------------
# Operator deviation pull (optional extension)
# ---------------------------------------------------------------------------

def operator_deviation_pull(X: np.ndarray,
                            mu: np.ndarray,
                            operators: Optional[list] = None,
                            betas: Optional[np.ndarray] = None) -> np.ndarray:
    """Deviation force from UDL spectrum operators.

    F_op = −Σ_k β_k · (Φ_k(x)² − Φ_k(μ)²)   [quadratic approximation]

    Parameters
    ----------
    X : (n, d) array
    mu : (d,) array
    operators : list of (name, operator) tuples with .transform()
    betas : per-operator weights (defaults to uniform 1/K)

    Returns
    -------
    force : (n, d) array — operator-induced restoring force
    """
    if operators is None:
        return np.zeros_like(X)

    K = len(operators)
    if betas is None:
        betas = np.ones(K) / K

    force = np.zeros_like(X)
    mu_row = mu.reshape(1, -1)

    for k, (name, op) in enumerate(operators):
        try:
            phi_x = op.transform(X)         # (n, d_k)
            phi_mu = op.transform(mu_row)    # (1, d_k)
            # Quadratic deviation: Φ(x)² − Φ(μ)²  projected back to input space
            # Simplified: use raw difference scaled to input dimension
            dev = phi_x - phi_mu             # (n, d_k)
            # Project back: pad/truncate to input dim
            d_in = X.shape[1]
            d_k = dev.shape[1]
            if d_k >= d_in:
                contrib = dev[:, :d_in]
            else:
                contrib = np.zeros_like(X)
                contrib[:, :d_k] = dev
            force -= betas[k] * contrib
        except Exception:
            continue

    return force


# ---------------------------------------------------------------------------
# Total force
# ---------------------------------------------------------------------------

def total_force(X: np.ndarray,
                mu: np.ndarray,
                alpha: float = 0.1,
                gamma: float = 1.0,
                sigma: float = 1.0,
                lambda_rep: float = 0.1,
                operators: Optional[list] = None,
                betas: Optional[np.ndarray] = None,
                eps: float = 1e-5,
                k_neighbors: int = 0,
                tree: Optional[cKDTree] = None,
                tree_refresh: int = 3) -> Tuple[np.ndarray, Optional[cKDTree]]:
    """Sum of all force components on each particle.

    F_i = F_radial + F_pairwise + F_operator

    Parameters
    ----------
    X, mu, alpha, gamma, sigma, lambda_rep : see component functions
    operators : optional UDL spectrum operators for deviation pull
    betas : per-operator weights
    eps : softening constant
    k_neighbors : if > 0, limit pairwise interaction to k nearest
    tree : optional pre-built cKDTree for kNN (avoids rebuild)
    tree_refresh : rebuild tree every N iterations (0 = every time)

    Returns
    -------
    (F, tree) : ((n, d) array, cKDTree or None)
    """
    F = radial_pull(X, mu, alpha)
    F_pair, tree_out = pairwise_forces(X, gamma, sigma, lambda_rep, eps,
                                        k_neighbors=k_neighbors, tree=tree)
    F += F_pair
    if operators is not None:
        F += operator_deviation_pull(X, mu, operators, betas)
    return F, tree_out


# ---------------------------------------------------------------------------
# Energy monitoring
# ---------------------------------------------------------------------------

def compute_system_energy(X: np.ndarray,
                          mu: np.ndarray,
                          alpha: float,
                          gamma: float,
                          sigma: float,
                          lambda_rep: float,
                          eps: float = 1e-5,
                          beta_dev: float = 0.0) -> Dict[str, float]:
    """Compute the total potential energy consistent with the force field.

    The forces are:
        F_radial  = -alpha (x_i - mu)          => E_radial = (alpha/2) ||x-mu||^2
        F_pair_ij = -gamma [exp(-r^2/s^2) - lambda/r] * unit(x_i-x_j)

    The potential V(r) whose negative gradient gives F_pair is:
        V_attract(r) = gamma * (sigma*sqrt(pi)/2) * erf(r/sigma)
        V_repel(r)   = -gamma * lambda * log(r)
        (since dV/dr = gamma*(exp(-r^2/s^2) - lambda/r), F = -dV/dr * unit)

    Operator deviation:
        F_dev = -beta (x^2 - mu^2)  => E_dev = (beta/2) sum_i ||x_i^2 - mu^2||^2
        (quadratic penalty for deviating from mu in squared space)

    Returns dict with per-component and total energy.
    """
    from scipy.special import erf as _erf

    n = X.shape[0]

    # For large n, subsample to keep energy monitoring tractable.
    # The energy is used only for line-search direction — an unbiased
    # estimate from a subsample is sufficient.
    max_energy_n = 1000
    if n > max_energy_n:
        rng = np.random.RandomState(0)
        idx = rng.choice(n, max_energy_n, replace=False)
        X = X[idx]
        mu = mu if mu.ndim == 1 else mu[idx]
        n = max_energy_n
        scale = 1.0  # per-particle energy is already size-invariant
    else:
        scale = 1.0

    # Radial energy:  E = (alpha/2) sum ||x_i - mu||^2
    disp = X - mu
    E_radial = 0.5 * alpha * np.sum(disp ** 2)

    # Pairwise energy consistent with force field
    s_sqrt_pi_half = sigma * np.sqrt(np.pi) * 0.5

    if n <= 5000:
        diff = X[:, None, :] - X[None, :, :]
        dist = np.linalg.norm(diff, axis=2) + eps
        np.fill_diagonal(dist, eps)

        # V_attract = gamma * (sigma*sqrt(pi)/2) * erf(r/sigma)
        # Sum over i<j pairs (factor of 2 for symmetry -> use 0.5 * full sum)
        E_attract = 0.5 * gamma * s_sqrt_pi_half * np.sum(_erf(dist / sigma))
        E_attract -= 0.5 * gamma * s_sqrt_pi_half * n * _erf(0.0)  # remove diagonal

        # V_repel = -gamma * lambda * log(r)
        E_repel = -0.5 * gamma * lambda_rep * np.sum(np.log(dist))
        E_repel += 0.5 * gamma * lambda_rep * n * np.log(eps)  # remove diagonal
    else:
        E_attract = 0.0
        E_repel = 0.0
        for i in range(n):
            diff_i = X[i] - X[i + 1:]
            dist_i = np.linalg.norm(diff_i, axis=1) + eps
            E_attract += gamma * s_sqrt_pi_half * np.sum(_erf(dist_i / sigma))
            E_repel -= gamma * lambda_rep * np.sum(np.log(dist_i))

    # Operator deviation energy: E_dev = (beta/2) sum ||x^2 - mu^2||^2
    E_dev = 0.0
    if beta_dev > 0:
        dev = X ** 2 - mu ** 2
        E_dev = 0.5 * beta_dev * np.sum(dev ** 2)

    E_total = E_radial + E_attract + E_repel + E_dev

    return {
        "total": float(E_total),
        "radial": float(E_radial),
        "attraction": float(E_attract),
        "repulsion": float(E_repel),
        "deviation": float(E_dev),
        "per_particle": float(E_total / max(n, 1)),
    }


# ---------------------------------------------------------------------------
# Main gravity engine
# ---------------------------------------------------------------------------

class GravityEngine:
    """N-body gravitational clustering engine.

    Evolves a particle system under radial + pairwise forces via
    discrete Euler integration and produces anomaly scores.

    Parameters
    ----------
    alpha : float
        Radial pull toward global centre (spring constant).
    gamma : float
        Pairwise interaction strength.
    sigma : float
        Attraction Gaussian length-scale.
    lambda_rep : float
        Short-range repulsion coefficient.
    eta : float
        Step size (learning rate) for Euler integration.
    iterations : int
        Number of discrete time steps.
    normalize : bool
        Whether to StandardScaler the input before simulation.
    track_energy : bool
        Whether to record system energy at each step.
    convergence_tol : float
        Early stopping if max displacement < tol. Set 0 to disable.

    Attributes
    ----------
    scaler_ : StandardScaler (fitted if normalize=True)
    mu_ : (d,) centroid of the (normalised) training data
    X_initial_ : (n, d) input positions (after normalisation)
    X_final_ : (n, d) final positions after simulation
    energy_history_ : list of dicts — per-step energy (if track_energy)
    displacement_history_ : list of float — max displacement per step
    converged_at_ : int or None — iteration where convergence was reached
    """

    def __init__(self,
                 alpha: float = 0.1,
                 gamma: float = 1.0,
                 sigma: float = 1.0,
                 lambda_rep: float = 0.1,
                 eta: float = 0.01,
                 iterations: int = 100,
                 normalize: bool = True,
                 track_energy: bool = True,
                 convergence_tol: float = 1e-6,
                 k_neighbors: int = 0,
                 beta_dev: float = 0.0,
                 exp_alpha: float = 0.0):
        self.alpha = alpha
        self.gamma = gamma
        self.sigma = sigma
        self.lambda_rep = lambda_rep
        self.eta = eta
        self.iterations = iterations
        self.normalize = normalize
        self.track_energy = track_energy
        self.convergence_tol = convergence_tol
        self.k_neighbors = k_neighbors
        self.beta_dev = beta_dev
        self.exp_alpha = exp_alpha    # ExponentialSpectrum amplification strength

        # Will be set during fit / run
        self.scaler_: Optional[StandardScaler] = None
        self.mu_: Optional[np.ndarray] = None
        self.X_initial_: Optional[np.ndarray] = None
        self.X_final_: Optional[np.ndarray] = None
        self.energy_history_: List[Dict[str, float]] = []
        self.displacement_history_: List[float] = []
        self.converged_at_: Optional[int] = None
        self._exp_spectrum: Optional[object] = None   # fitted ExponentialSpectrum

    # ----- core simulation -----

    def fit_transform(self, X: np.ndarray,
                      operators: Optional[list] = None,
                      betas: Optional[np.ndarray] = None,
                      time_budget: float = 0.0) -> np.ndarray:
        """Run the gravity simulation and return final positions.

        Parameters
        ----------
        X : (n, d) array — input data
        operators : optional list of (name, spectrum_op) for deviation pull
        betas : per-operator weights
        time_budget : max seconds allowed (0 = unlimited)

        Returns
        -------
        X_final : (n, d) array — evolved positions
        """
        import time as _time
        _t_start = _time.monotonic()

        # Step 1 — Normalize
        if self.normalize:
            self.scaler_ = StandardScaler()
            X_work = self.scaler_.fit_transform(X).astype(np.float64)
        else:
            X_work = X.astype(np.float64).copy()

        self.X_initial_ = X_work.copy()

        # Step 2a — Exponential amplification (if exp_alpha > 0)
        if self.exp_alpha > 0 and ExponentialSpectrum is not None:
            self._exp_spectrum = ExponentialSpectrum(
                alpha=self.exp_alpha, max_dim=X_work.shape[1]
            )
            self._exp_spectrum.fit(X_work)
            X_work = self._exp_spectrum.transform(X_work).astype(np.float64)
            # Re-normalise after exponential transform
            _exp_scaler = StandardScaler()
            X_work = _exp_scaler.fit_transform(X_work).astype(np.float64)
            self.X_initial_ = X_work.copy()   # update initial positions

        # Step 2b — Global centre
        self.mu_ = np.mean(X_work, axis=0)

        # Step 6 — Iterative update with backtracking line-search
        self.energy_history_ = []
        self.displacement_history_ = []
        self.converged_at_ = None

        # Line-search parameters
        ls_beta = 0.5          # step shrink factor
        ls_max_tries = 8       # max halvings before accepting step
        damping = 0.9          # convex-combination damping ∈ (0, 1]

        # Pre-compute initial energy for line-search
        _E_cur = None
        if self.track_energy:
            _E_cur = compute_system_energy(
                X_work, self.mu_, self.alpha, self.gamma,
                self.sigma, self.lambda_rep,
                beta_dev=self.beta_dev if operators is None else 0.0,
            )

        for t in range(self.iterations):
            # Energy snapshot (before step)
            if self.track_energy:
                if _E_cur is None:
                    _E_cur = compute_system_energy(
                        X_work, self.mu_, self.alpha, self.gamma,
                        self.sigma, self.lambda_rep,
                        beta_dev=self.beta_dev if operators is None else 0.0,
                    )
                _E_cur["step"] = t
                self.energy_history_.append(_E_cur)

            # Build operator list: include built-in deviation if beta_dev > 0
            ops = operators
            bs = betas
            if self.beta_dev > 0 and ops is None:
                # Built-in quadratic deviation operator D(x) = x² − μ²
                ops = [("quad_dev", None)]   # sentinel
                bs = np.array([self.beta_dev])

            # Compute total force
            F, _ = total_force(
                X_work, self.mu_,
                alpha=self.alpha,
                gamma=self.gamma,
                sigma=self.sigma,
                lambda_rep=self.lambda_rep,
                operators=ops,
                betas=bs,
                k_neighbors=self.k_neighbors,
            )

            # Add built-in deviation force if beta_dev > 0 and no external ops
            if self.beta_dev > 0 and operators is None:
                # F_dev = −β (x² − μ²)  — nonlinear deviation amplification
                dev = X_work ** 2 - self.mu_ ** 2
                F -= self.beta_dev * dev

            # Clamp forces to prevent divergence
            force_norm = np.linalg.norm(F, axis=1, keepdims=True)
            max_force = 100.0
            mask = force_norm > max_force
            if np.any(mask):
                F = np.where(mask, F * (max_force / (force_norm + 1e-10)), F)

            # Backtracking line-search on corrected energy
            eta_t = self.eta
            accepted = False
            E_old_val = _E_cur["total"] if _E_cur is not None else None

            for _ls in range(ls_max_tries):
                dX = eta_t * damping * F
                X_trial = X_work + dX

                # Reject NaN / divergent steps immediately
                if np.any(np.isnan(X_trial)) or np.any(np.abs(X_trial) > 1e6):
                    eta_t *= ls_beta
                    continue

                if E_old_val is not None:
                    _E_trial = compute_system_energy(
                        X_trial, self.mu_, self.alpha, self.gamma,
                        self.sigma, self.lambda_rep,
                        beta_dev=self.beta_dev if operators is None else 0.0,
                    )
                    if _E_trial["total"] <= E_old_val:
                        # Energy decreased — accept
                        X_work = X_trial
                        _E_cur = _E_trial
                        accepted = True
                        break
                    else:
                        eta_t *= ls_beta
                else:
                    # No energy tracking — accept unconditionally
                    X_work = X_trial
                    accepted = True
                    break

            if not accepted:
                # All line-search attempts failed — take the smallest step anyway
                dX = eta_t * damping * F
                X_work += dX
                if self.track_energy:
                    _E_cur = compute_system_energy(
                        X_work, self.mu_, self.alpha, self.gamma,
                        self.sigma, self.lambda_rep,
                        beta_dev=self.beta_dev if operators is None else 0.0,
                    )

            # Divergence check
            if np.any(np.isnan(X_work)) or np.any(np.abs(X_work) > 1e6):
                X_work -= dX
                self.converged_at_ = t + 1
                break

            # Time budget check
            if time_budget > 0 and (_time.monotonic() - _t_start) > time_budget:
                self.converged_at_ = t + 1
                break

            # Convergence check
            max_disp = float(np.max(np.abs(dX)))
            self.displacement_history_.append(max_disp)

            if self.convergence_tol > 0 and max_disp < self.convergence_tol:
                self.converged_at_ = t + 1
                # Final energy snapshot
                if self.track_energy:
                    _E_cur["step"] = t + 1
                    self.energy_history_.append(_E_cur)
                break

        self.X_final_ = X_work
        return X_work

    # ----- scoring -----

    def anomaly_scores(self, X_final: Optional[np.ndarray] = None) -> np.ndarray:
        """Compute anomaly scores as distance from centre after dynamics.

        Parameters
        ----------
        X_final : (n, d) array. If None, uses self.X_final_.

        Returns
        -------
        scores : (n,) array — higher = more anomalous
        """
        if X_final is None:
            X_final = self.X_final_
        if X_final is None:
            raise RuntimeError("Call fit_transform() first.")
        return np.linalg.norm(X_final - self.mu_, axis=1)

    def energy_scores(self, X_final: Optional[np.ndarray] = None) -> np.ndarray:
        """Per-point energy as anomaly score.

        E(x_i) = (α/2)||x_i − μ||²  −  γ Σ_j exp(−||x_i−x_j||²/σ²)
                 + γ·λ Σ_j log(||x_i−x_j|| + ε)

        Uses kNN approximation when k_neighbors > 0 (same as force
        computation) so scoring is O(n·k·log n) instead of O(n²).

        Parameters
        ----------
        X_final : (n, d) array. If None, uses self.X_final_.

        Returns
        -------
        scores : (n,) — per-point energy (higher = more anomalous)
        """
        if X_final is None:
            X_final = self.X_final_
        if X_final is None:
            raise RuntimeError("Call fit_transform() first.")

        n = X_final.shape[0]
        eps = 1e-5

        # Radial term: (α/2)||x_i − μ||²  — always O(n)
        disp = X_final - self.mu_
        E_radial = 0.5 * self.alpha * np.sum(disp ** 2, axis=1)  # (n,)

        # Pairwise interaction — choose method based on k_neighbors
        if self.k_neighbors > 0:
            # kNN-approximated energy: O(n·k·log n)
            E_attract, E_repel = self._energy_knn(X_final, eps)
        elif n <= 3000:
            # Full vectorised: O(n²) but fits in memory
            E_attract, E_repel = self._energy_vec(X_final, eps)
        else:
            # Full loop: O(n²) low memory
            E_attract, E_repel = self._energy_loop(X_final, eps)

        return E_radial + E_attract + E_repel

    def _energy_knn(self, X: np.ndarray, eps: float) -> Tuple[np.ndarray, np.ndarray]:
        """kNN-approximated per-point energy. O(n·k·log n).

        FP32 kNN search + n_jobs=-1 (scoring is non-dynamic, so
        non-determinism doesn't affect convergence).
        """
        from sklearn.neighbors import NearestNeighbors
        n = X.shape[0]
        k_eff = min(self.k_neighbors, n - 1)

        # FP32 brute search for speed; does not affect dynamics
        X_f32 = X.astype(np.float32)
        nn = NearestNeighbors(n_neighbors=k_eff + 1, algorithm='brute')
        nn.fit(X_f32)
        distances_f32, _ = nn.kneighbors(X_f32)

        # Skip self → (n, k_eff);  upcast for energy arithmetic
        dist = distances_f32[:, 1:].astype(np.float64) + eps  # (n, k_eff)
        dist_sq = dist ** 2

        E_attract = -self.gamma * np.sum(
            np.exp(-dist_sq / (self.sigma * self.sigma)), axis=1
        )  # (n,)

        E_repel = self.gamma * self.lambda_rep * np.sum(
            np.log(dist), axis=1
        )  # (n,)

        return E_attract, E_repel

    def _energy_vec(self, X: np.ndarray, eps: float) -> Tuple[np.ndarray, np.ndarray]:
        """Full vectorised per-point energy. O(n²), fits n ≤ 3000.

        Uses the active backend (JAX/CuPy/NumPy) for automatic
        XLA fusion of exp + log + reduction when available.
        """
        X_b = xp.asarray(X)
        n = X_b.shape[0]
        diff = X_b[:, None, :] - X_b[None, :, :]              # (n, n, d)
        dist = xp.sqrt(xp.sum(diff ** 2, axis=2)) + eps       # (n, n)

        E_attract = -self.gamma * xp.sum(
            xp.exp(-(dist ** 2) / (self.sigma ** 2)), axis=1
        )
        E_attract = E_attract + self.gamma  # remove self-term

        E_repel = self.gamma * self.lambda_rep * xp.sum(
            xp.log(dist), axis=1
        )
        E_repel = E_repel - self.gamma * self.lambda_rep * float(xp.log(xp.asarray(eps)))

        return to_numpy(E_attract), to_numpy(E_repel)

    def _energy_loop(self, X: np.ndarray, eps: float) -> Tuple[np.ndarray, np.ndarray]:
        """Loop-based per-point energy. O(n²), low memory."""
        n = X.shape[0]
        E_attract = np.zeros(n)
        E_repel = np.zeros(n)
        for i in range(n):
            diff_i = X[i] - X
            dist_i = np.linalg.norm(diff_i, axis=1) + eps
            dist_i[i] = eps
            E_attract[i] = -self.gamma * np.sum(
                np.exp(-(dist_i ** 2) / (self.sigma ** 2))
            )
            E_attract[i] += self.gamma
            E_repel[i] = self.gamma * self.lambda_rep * np.sum(np.log(dist_i))
            E_repel[i] -= self.gamma * self.lambda_rep * np.log(eps)
        return E_attract, E_repel

    def displacement_scores(self) -> np.ndarray:
        """How far each point moved during the simulation.

        Normal points in dense regions move little; outliers drift far.

        Returns
        -------
        scores : (n,) array — total displacement per particle
        """
        if self.X_initial_ is None or self.X_final_ is None:
            raise RuntimeError("Call fit_transform() first.")
        return np.linalg.norm(self.X_final_ - self.X_initial_, axis=1)

    def cluster_labels(self, n_clusters: int = 2,
                       method: str = "kmeans") -> np.ndarray:
        """Cluster the final positions.

        Parameters
        ----------
        n_clusters : number of clusters
        method : 'kmeans' or 'dbscan'

        Returns
        -------
        labels : (n,) int array
        """
        if self.X_final_ is None:
            raise RuntimeError("Call fit_transform() first.")

        if method == "kmeans":
            from sklearn.cluster import KMeans
            return KMeans(n_clusters=n_clusters,
                          random_state=42, n_init=10).fit_predict(self.X_final_)
        elif method == "dbscan":
            from sklearn.cluster import DBSCAN
            return DBSCAN(eps=0.5, min_samples=5).fit_predict(self.X_final_)
        else:
            raise ValueError(f"Unknown clustering method: {method}")

    # ----- diagnostics -----

    def convergence_summary(self) -> Dict:
        """Return convergence diagnostics.

        Returns
        -------
        dict with keys:
            converged : bool
            converged_at : int or None
            iterations_run : int
            final_max_displacement : float
            energy_drop : float (E_final − E_initial)
            energy_initial / energy_final : float
        """
        n_steps = len(self.displacement_history_)
        summary = {
            "converged": self.converged_at_ is not None,
            "converged_at": self.converged_at_,
            "iterations_run": n_steps,
            "final_max_displacement": (
                self.displacement_history_[-1] if self.displacement_history_ else float("nan")
            ),
        }

        if self.energy_history_ and len(self.energy_history_) >= 2:
            summary["energy_initial"] = self.energy_history_[0]["total"]
            summary["energy_final"] = self.energy_history_[-1]["total"]
            summary["energy_drop"] = (
                self.energy_history_[-1]["total"] - self.energy_history_[0]["total"]
            )
        else:
            summary["energy_initial"] = float("nan")
            summary["energy_final"] = float("nan")
            summary["energy_drop"] = float("nan")

        return summary

    def print_summary(self) -> None:
        """Pretty-print convergence diagnostics."""
        s = self.convergence_summary()
        print("=" * 55)
        print("  Gravity Engine — Convergence Summary")
        print("=" * 55)
        print(f"  Iterations run   : {s['iterations_run']}")
        if s["converged"]:
            print(f"  Converged at     : step {s['converged_at']}")
        else:
            print(f"  Converged        : No (max iter reached)")
        print(f"  Final max |dX|   : {s['final_max_displacement']:.2e}")
        print(f"  Energy initial   : {s['energy_initial']:.4f}")
        print(f"  Energy final     : {s['energy_final']:.4f}")
        print(f"  Energy drop      : {s['energy_drop']:.4f}")
        print("=" * 55)

    def __repr__(self) -> str:
        return (
            f"GravityEngine(α={self.alpha}, γ={self.gamma}, σ={self.sigma}, "
            f"λ_rep={self.lambda_rep}, η={self.eta}, T={self.iterations})"
        )


# ---------------------------------------------------------------------------
# Convenience function (matches user's pseudocode exactly)
# ---------------------------------------------------------------------------

def run_gravity_clustering(X: np.ndarray,
                           alpha: float = 0.1,
                           gamma: float = 1.0,
                           sigma: float = 1.0,
                           lambda_rep: float = 0.1,
                           eta: float = 0.01,
                           iterations: int = 100,
                           normalize: bool = True) -> np.ndarray:
    """One-call gravity simulation — returns final positions.

    Equivalent to:
        engine = GravityEngine(...)
        return engine.fit_transform(X)

    Parameters
    ----------
    X : (n, d) array — input data
    alpha, gamma, sigma, lambda_rep, eta, iterations : hyperparameters
    normalize : whether to StandardScaler the input

    Returns
    -------
    X_final : (n, d) array — evolved positions
    """
    engine = GravityEngine(
        alpha=alpha, gamma=gamma, sigma=sigma,
        lambda_rep=lambda_rep, eta=eta, iterations=iterations,
        normalize=normalize, track_energy=False,
    )
    return engine.fit_transform(X)
