"""
bsdt_operators.py - Four BSDT Deviation Operators for Macro Data
=================================================================

Implements the four blind-spot operators from Odeyemi (2025) BSDT,
adapted for quarterly macro panel data X(t) ? R^{N ? d}:

    ?_C  Camouflage       - Mahalanobis distance from normal distribution
    ?_G  Feature Gap      - PCA residual in low-variance directions
    ?_A  Activity Anomaly - velocity excess (quarter-over-quarter change)
    ?_T  Temporal Novelty - KDE self-history novelty

All operators are fitted on a normal-period reference sample, then
evaluated on the full panel.  No researcher-chosen weights; operator
definitions follow the paper definitions exactly.

Usage
-----
    ops = BSDTOperators(n_components=4).fit(X_normal)
    channels = ops.compute_all(X_series)
    # channels shape: (T, 4)  - one score per operator per quarter
"""

from __future__ import annotations
import numpy as np
from scipy.spatial.distance import mahalanobis


class BSDTOperators:
    """
    Full BSDT operator suite for macro state matrices.

    Parameters
    ----------
    n_components : int
        Number of PCA components for ?_G (top-k to project out).
        Default 4 (out of d=6, leaves 2 gap dimensions).
    velocity_pctl : float
        Percentile of normal-period velocity to use as v? threshold
        for ?_A.  Default 95.
    kde_bandwidth : float or None
        Bandwidth for ?_T kernel density.  If None, uses Scott's rule.
    """

    def __init__(self, n_components: int = 4, velocity_pctl: float = 95.0,
                 kde_bandwidth: float | None = None):
        self.n_components = n_components
        self.velocity_pctl = velocity_pctl
        self.kde_bandwidth = kde_bandwidth

        # Fitted quantities
        self.mu0_: np.ndarray | None = None          # (d,) normal mean
        self.Sigma0_: np.ndarray | None = None        # (d,d) normal cov
        self.Sigma0_inv_: np.ndarray | None = None    # (d,d) precision
        self.Vk_: np.ndarray | None = None            # (d, k) top-k eigenvectors
        self.V_gap_: np.ndarray | None = None         # (d, d-k) gap eigenvectors
        self.v0_: float = 0.0                         # velocity threshold
        self.normal_velocities_: np.ndarray | None = None

    def fit(self, X_normal: np.ndarray) -> "BSDTOperators":
        """
        Fit all operators on normal-period data.

        Parameters
        ----------
        X_normal : (T_norm, N, d) - normal period state matrices
        """
        T, N, d = X_normal.shape
        # Flatten to (T*N, d) for distribution estimation
        Xf = X_normal.reshape(-1, d)

        # ?? ?_C: Camouflage - Mahalanobis ??
        self.mu0_ = Xf.mean(axis=0)
        self.Sigma0_ = np.cov(Xf.T) + 1e-6 * np.eye(d)
        self.Sigma0_inv_ = np.linalg.inv(self.Sigma0_)

        # ?? ?_G: Feature Gap - PCA decomposition ??
        eigvals, eigvecs = np.linalg.eigh(self.Sigma0_)
        # eigh returns ascending order; top-k = last k
        k = min(self.n_components, d - 1)
        self.Vk_ = eigvecs[:, -k:]           # (d, k) - top-k directions
        self.V_gap_ = eigvecs[:, :-k]         # (d, d-k) - gap directions

        # ?? ?_A: Activity Anomaly - velocity threshold ??
        # Compute quarter-over-quarter velocities in normal period
        velocities = []
        for t in range(1, T):
            dX = X_normal[t] - X_normal[t - 1]  # (N, d)
            v = np.linalg.norm(dX, axis=1)       # (N,)
            velocities.extend(v.tolist())
        self.normal_velocities_ = np.array(velocities)
        self.v0_ = float(np.percentile(self.normal_velocities_, self.velocity_pctl))

        # ?? ?_T: Temporal Novelty - store bandwidth ??
        if self.kde_bandwidth is None:
            # Scott's rule: h = n^(-1/(d+4)) * ?
            n_eff = len(Xf)
            self.kde_bandwidth = float(n_eff ** (-1.0 / (d + 4)) * Xf.std())

        return self

    def delta_C(self, X: np.ndarray) -> np.ndarray:
        """
        Camouflage deviation: per-agent Mahalanobis distance.

        ?_C(x_i) = (x_i - ??)? ???? (x_i - ??)

        Parameters
        ----------
        X : (N, d) - single time-step state matrix

        Returns
        -------
        (N,) - per-agent camouflage score
        """
        z = X - self.mu0_
        return np.sum(z @ self.Sigma0_inv_ * z, axis=1)

    def delta_G(self, X: np.ndarray) -> np.ndarray:
        """
        Feature Gap deviation: variance in low-eigenvalue directions.

        ?_G(x_i) = ||x_i - ??||? - ||?_k(x_i - ??)||?

        This is the residual norm after projecting out the top-k
        principal components - measures displacement in directions
        the normal covariance doesn't explain.

        Returns
        -------
        (N,) - per-agent feature gap score
        """
        z = X - self.mu0_                    # (N, d)
        total_sq = np.sum(z ** 2, axis=1)    # (N,)
        proj = z @ self.Vk_                  # (N, k) - projection onto top-k
        proj_sq = np.sum(proj ** 2, axis=1)  # (N,)
        return np.maximum(total_sq - proj_sq, 0.0)

    def delta_A(self, X_curr: np.ndarray, X_prev: np.ndarray) -> np.ndarray:
        """
        Activity Anomaly: excess velocity above normal threshold.

        ?_A(x_i) = max(0, ||?_i|| - v?)

        where ?_i ? x_i(t) - x_i(t-1) for quarterly data.

        Parameters
        ----------
        X_curr : (N, d) - state at time t
        X_prev : (N, d) - state at time t-1

        Returns
        -------
        (N,) - per-agent activity anomaly score
        """
        dX = X_curr - X_prev
        velocity = np.linalg.norm(dX, axis=1)
        return np.maximum(velocity - self.v0_, 0.0)

    def delta_T(self, X: np.ndarray, history: list[np.ndarray]) -> np.ndarray:
        """
        Temporal Novelty: KDE-based self-history novelty.

        ?_T(x_i, t) = max(0, -log p_h(x_i(t)))

        where p_h is Gaussian KDE over the agent's own past states.

        Parameters
        ----------
        X       : (N, d) - current state
        history : list of (N, d) arrays - past states [X(0), ..., X(t-1)]

        Returns
        -------
        (N,) - per-agent temporal novelty score
        """
        N, d = X.shape
        novelty = np.zeros(N)

        if len(history) < 3:
            return novelty  # not enough history

        h = self.kde_bandwidth
        h2 = h ** 2

        for i in range(N):
            # Collect agent i's history
            past = np.array([H[i] for H in history])  # (T_hist, d)
            T_hist = len(past)

            # Gaussian KDE: p(x) = (1/T) ?_t K_h(x - past_t)
            diff = X[i] - past                          # (T_hist, d)
            sq_dist = np.sum(diff ** 2, axis=1)          # (T_hist,)
            log_kernels = -0.5 * sq_dist / h2 - 0.5 * d * np.log(2 * np.pi * h2)
            # Log-sum-exp for numerical stability
            max_lk = log_kernels.max()
            log_density = max_lk + np.log(np.sum(np.exp(log_kernels - max_lk))) - np.log(T_hist)
            novelty[i] = max(0.0, -log_density)

        return novelty

    def compute_channels(
        self,
        X_series: np.ndarray,
        verbose: bool = False,
    ) -> dict[str, np.ndarray]:
        """
        Compute all four BSDT channels over a time series.

        Parameters
        ----------
        X_series : (T, N, d) - full panel

        Returns
        -------
        dict with keys:
            'delta_C'   : (T,) - system-level camouflage score
            'delta_G'   : (T,) - system-level feature gap score
            'delta_A'   : (T,) - system-level activity anomaly score
            'delta_T'   : (T,) - system-level temporal novelty score
            'channels'  : (T, 4) - all channels stacked
            'per_agent' : (T, N, 4) - per-agent scores
        """
        T, N, d = X_series.shape

        # Per-agent scores: (T, N, 4)
        pa = np.zeros((T, N, 4))
        history: list[np.ndarray] = []

        for t in range(T):
            if verbose and t % 20 == 0:
                print(f"  [bsdt] t={t}/{T}")

            X = X_series[t]

            # ?_C: always available
            pa[t, :, 0] = self.delta_C(X)

            # ?_G: always available
            pa[t, :, 1] = self.delta_G(X)

            # ?_A: needs t >= 1
            if t >= 1:
                pa[t, :, 2] = self.delta_A(X, X_series[t - 1])

            # ?_T: needs history
            pa[t, :, 3] = self.delta_T(X, history)
            history.append(X.copy())

        # System-level: sum across agents (Frobenius-like aggregation)
        sys_scores = pa.sum(axis=1)  # (T, 4)

        return {
            "delta_C":   sys_scores[:, 0],
            "delta_G":   sys_scores[:, 1],
            "delta_A":   sys_scores[:, 2],
            "delta_T":   sys_scores[:, 3],
            "channels":  sys_scores,
            "per_agent": pa,
        }
