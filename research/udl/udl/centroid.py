"""
Centroid Estimation — Equilibrium Reference Points
====================================================
Implements 7 strategies for determining the "normal centre" of
a data distribution. The centroid defines the origin from which
all anomaly vectors are measured, making its accuracy critical.

Strategy selection can be automatic (via CentroidEstimator.auto())
or explicit.
"""

import numpy as np
from scipy.spatial.distance import cdist


class CentroidEstimator:
    """
    Multi-strategy centroid estimator.

    Each method maps (X_ref) → centroid vector c ∈ ℝ^d.
    """

    def __init__(self, method="auto", **kwargs):
        """
        Parameters
        ----------
        method : str
            One of: 'mean', 'geometric_median', 'density_peak',
            'energy_minimum', 'trimmed_mean', 'medoid', 'manifold',
            or 'auto' (heuristic selection).
        kwargs : dict
            Method-specific parameters.
        """
        self.method = method
        self.kwargs = kwargs
        self.centroid_ = None
        self._method_used = None

    def fit(self, X_ref):
        """Compute centroid from reference (normal) data."""
        if self.method == "auto":
            self.centroid_, self._method_used = self._auto_select(X_ref)
        else:
            fn = self._get_method(self.method)
            self.centroid_ = fn(X_ref)
            self._method_used = self.method
        return self

    def get_centroid(self):
        """Return fitted centroid."""
        if self.centroid_ is None:
            raise RuntimeError("Call fit() first")
        return self.centroid_

    # ─── STRATEGY IMPLEMENTATIONS ───────────────────────────────

    @staticmethod
    def mean(X):
        """Simple arithmetic mean — optimal for unimodal Gaussian data."""
        return X.mean(axis=0)

    @staticmethod
    def geometric_median(X, max_iter=100, tol=1e-6):
        """
        Weiszfeld's algorithm for geometric median.
        Minimises sum of Euclidean distances — robust to outliers.
        """
        y = np.median(X, axis=0).copy()
        for _ in range(max_iter):
            dists = np.linalg.norm(X - y, axis=1, keepdims=True)
            dists = np.maximum(dists, 1e-10)
            weights = 1.0 / dists
            y_new = (X * weights).sum(axis=0) / weights.sum()
            if np.linalg.norm(y_new - y) < tol:
                break
            y = y_new
        return y

    @staticmethod
    def density_peak(X, bandwidth=None):
        """
        Kernel density peak — finds the highest-density point.
        Estimates mode rather than mean; suitable for skewed data.
        """
        N, d = X.shape
        if bandwidth is None:
            bandwidth = 1.06 * X.std() * N ** (-1.0 / 5)
            bandwidth = max(bandwidth, 1e-6)

        # Evaluate density at each data point (Gaussian KDE)
        dists_sq = cdist(X, X, metric="sqeuclidean")
        densities = np.exp(-dists_sq / (2 * bandwidth ** 2)).sum(axis=1)

        peak_idx = np.argmax(densities)
        return X[peak_idx].copy()

    @staticmethod
    def energy_minimum(X, n_candidates=50):
        """
        Energy-based centroid — minimises total potential energy.
        V(c) = Σ ||x_i - c||^2 + λ * Σ_i Σ_j ||x_i - x_j|| coupling
        Actually reduces to mean for pure quadratic, so we add a norm penalty.
        """
        N, d = X.shape
        # Sample candidates from data
        indices = np.random.choice(N, min(n_candidates, N), replace=False)
        candidates = X[indices]

        best_energy = np.inf
        best_c = X.mean(axis=0)

        for c in candidates:
            # Attractive potential
            dists = np.linalg.norm(X - c, axis=1)
            energy = np.sum(dists ** 2) + 0.1 * np.sum(dists)
            if energy < best_energy:
                best_energy = energy
                best_c = c.copy()
        return best_c

    @staticmethod
    def trimmed_mean(X, trim_fraction=0.1):
        """
        Trimmed mean — removes extreme points before averaging.
        Balances robustness and efficiency.
        """
        N, d = X.shape
        centroid = X.mean(axis=0)
        dists = np.linalg.norm(X - centroid, axis=1)
        threshold = np.percentile(dists, 100 * (1 - trim_fraction))
        mask = dists <= threshold
        return X[mask].mean(axis=0)

    @staticmethod
    def medoid(X):
        """
        Medoid — the actual data point closest to all others.
        Always returns a real observation; interpretable.
        """
        dists = cdist(X, X, metric="euclidean")
        total_dists = dists.sum(axis=1)
        return X[np.argmin(total_dists)].copy()

    @staticmethod
    def manifold(X, n_components=None):
        """
        Manifold centroid — projects to lower-dimensional manifold
        via PCA, computes centroid there, projects back.
        Better when data lives on a submanifold.
        """
        N, d = X.shape
        if n_components is None:
            n_components = min(d, max(2, d // 2))

        mu = X.mean(axis=0)
        X_c = X - mu
        U, S, Vt = np.linalg.svd(X_c, full_matrices=False)
        # Project to top-k subspace
        V_k = Vt[:n_components]
        X_proj = X_c @ V_k.T
        centroid_proj = X_proj.mean(axis=0)
        # Back-project
        centroid = centroid_proj @ V_k + mu
        return centroid

    # ─── AUTO SELECTION ─────────────────────────────────────────

    def _auto_select(self, X):
        """
        Heuristically choose best centroid method based on data shape.

        Decision logic:
          - If N < 30: use medoid (too few for statistics)
          - If skewness > 2: use geometric_median or density_peak
          - If d > 50: use manifold
          - Otherwise: use trimmed_mean (robust default)
        """
        N, d = X.shape

        if N < 30:
            return self.medoid(X), "medoid"

        # Check skewness of column means
        col_means = X.mean(axis=0)
        mu = col_means.mean()
        sigma = col_means.std() + 1e-10
        skew = np.mean(((col_means - mu) / sigma) ** 3)

        if abs(skew) > 2.0:
            return self.geometric_median(X), "geometric_median"

        if d > 50:
            return self.manifold(X), "manifold"

        return self.trimmed_mean(X), "trimmed_mean"

    def _get_method(self, name):
        """Resolve method name to callable."""
        methods = {
            "mean": self.mean,
            "geometric_median": self.geometric_median,
            "density_peak": self.density_peak,
            "energy_minimum": self.energy_minimum,
            "trimmed_mean": self.trimmed_mean,
            "medoid": self.medoid,
            "manifold": self.manifold,
        }
        if name not in methods:
            raise ValueError(f"Unknown method '{name}'. Choose from: {list(methods)}")
        return methods[name]

    def __repr__(self):
        m = self._method_used or self.method
        return f"CentroidEstimator(method='{m}')"
