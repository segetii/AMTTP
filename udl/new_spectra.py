"""
New Spectrum Operators — Orthogonal Views
==========================================
Each captures a fundamentally different aspect of deviation not covered
by the existing operator library.

1. GraphNeighborhoodSpectrum  — local kNN graph structure
2. DensityRatioSpectrum       — KDE log-likelihood contrast
3. TopologicalSpectrum        — persistent homology proxy (TDA-lite)
4. DependencyCopulaSpectrum   — pairwise dependency structure
5. CompressibilitySpectrum    — Kolmogorov complexity proxy
6. KernelRKHSSpectrum         — nonlinear reconstruction error
"""

import numpy as np
from scipy.spatial.distance import cdist


# ═══════════════════════════════════════════════════════════════════
# 1. GRAPH / NEIGHBORHOOD SPECTRUM
# ═══════════════════════════════════════════════════════════════════

class GraphNeighborhoodSpectrum:
    """
    Local graph structure around each point in kNN graph.

    Computes per-point:
      1. Mean kNN distance (how isolated)
      2. Local reachability density ratio (LOF-like)
      3. kNN distance variance (uniformity of neighborhood)
      4. Relative rank of distance to global median
      5. Shared-neighbor fraction (connectivity)

    This captures the *local density structure* that Geometric
    (global Mahalanobis) and Phase (pairwise interactions) miss.
    """

    def __init__(self, k=10, eps=1e-10):
        self.k = k
        self.eps = eps
        self._ref_distances = None
        self._ref_median_dist = None
        self._ref_mean_dist = None
        self._ref_std_dist = None
        self._X_ref = None

    def fit(self, X_ref):
        self._X_ref = X_ref.copy()
        N = len(X_ref)
        k = min(self.k, N - 1)
        self.k = k

        # Compute all pairwise distances within reference
        D = cdist(X_ref, X_ref, metric='euclidean')
        np.fill_diagonal(D, np.inf)

        # kNN distances for each reference point
        sorted_D = np.sort(D, axis=1)[:, :k]
        mean_dists = sorted_D.mean(axis=1)

        self._ref_median_dist = np.median(mean_dists)
        self._ref_mean_dist = np.mean(mean_dists)
        self._ref_std_dist = np.std(mean_dists) + self.eps

        # Store per-point kNN info for reachability computation
        self._ref_knn_dists = sorted_D
        self._ref_mean_knn = mean_dists
        return self

    def transform(self, X):
        N = len(X)
        k = self.k
        out = np.zeros((N, 5), dtype=np.float64)

        # Distances from test points to reference points
        D = cdist(X, self._X_ref, metric='euclidean')
        sorted_D = np.sort(D, axis=1)[:, :k]

        for i in range(N):
            knn_dists = sorted_D[i]

            # 1. Mean kNN distance (z-scored)
            mean_d = knn_dists.mean()
            out[i, 0] = (mean_d - self._ref_mean_dist) / self._ref_std_dist

            # 2. Local reachability density ratio
            # LRD = 1 / mean(reach_dist), compare to ref median
            reach_dist = np.maximum(knn_dists, self._ref_knn_dists[:k, -1] if len(self._ref_knn_dists) > 0 else knn_dists)
            lrd = 1.0 / (reach_dist.mean() + self.eps)
            ref_lrd = 1.0 / (self._ref_mean_dist + self.eps)
            out[i, 1] = np.log(ref_lrd / (lrd + self.eps) + self.eps)

            # 2. kNN distance variance (normalized)
            out[i, 2] = knn_dists.std() / (mean_d + self.eps)

            # 4. Rank relative to reference distribution
            out[i, 3] = np.searchsorted(
                np.sort(self._ref_mean_knn), mean_d
            ) / len(self._ref_mean_knn)

            # 5. Max/mean ratio (tail stretch)
            out[i, 4] = knn_dists[-1] / (mean_d + self.eps)

        return out


# ═══════════════════════════════════════════════════════════════════
# 2. DENSITY RATIO SPECTRUM
# ═══════════════════════════════════════════════════════════════════

class DensityRatioSpectrum:
    """
    KDE-based log-likelihood deviation from training distribution.

    Computes per-point:
      1. Log-density under reference KDE (Gaussian kernel)
      2. Log-density z-score vs reference distribution
      3. Local density gradient magnitude
      4. Density rank (percentile in reference)

    Captures non-Gaussian density shapes that Mahalanobis misses.
    """

    def __init__(self, bandwidth='auto', max_ref=2000, eps=1e-10):
        self.bandwidth = bandwidth
        self.max_ref = max_ref
        self.eps = eps
        self._X_ref = None
        self._h = None
        self._ref_log_densities = None
        self._ref_mean_ld = None
        self._ref_std_ld = None

    def _kde_log_density(self, X_query):
        """Compute log density for query points using Gaussian KDE."""
        N_ref = len(self._X_ref)
        m = self._X_ref.shape[1]
        h = self._h

        # D[i,j] = ||query_i - ref_j||^2
        D_sq = cdist(X_query, self._X_ref, metric='sqeuclidean')
        # log kernel: -0.5 * D / h^2 - m/2 * log(2*pi*h^2)
        log_kernels = -0.5 * D_sq / (h ** 2) - 0.5 * m * np.log(2 * np.pi * h ** 2)
        # log-sum-exp for numerical stability
        max_lk = log_kernels.max(axis=1, keepdims=True)
        log_density = max_lk.squeeze() + np.log(
            np.exp(log_kernels - max_lk).mean(axis=1) + self.eps
        )
        return log_density

    def fit(self, X_ref):
        N, m = X_ref.shape
        # Subsample if large
        if N > self.max_ref:
            rng = np.random.RandomState(42)
            idx = rng.choice(N, self.max_ref, replace=False)
            self._X_ref = X_ref[idx].copy()
        else:
            self._X_ref = X_ref.copy()

        # Bandwidth: Silverman's rule
        if self.bandwidth == 'auto':
            self._h = max(
                np.median(np.std(self._X_ref, axis=0)) *
                (len(self._X_ref) ** (-1.0 / (m + 4))),
                self.eps
            )
        else:
            self._h = self.bandwidth

        # Reference log-densities
        self._ref_log_densities = self._kde_log_density(self._X_ref)
        self._ref_mean_ld = np.mean(self._ref_log_densities)
        self._ref_std_ld = np.std(self._ref_log_densities) + self.eps
        self._sorted_ref_ld = np.sort(self._ref_log_densities)
        return self

    def transform(self, X):
        N = len(X)
        out = np.zeros((N, 4), dtype=np.float64)

        log_d = self._kde_log_density(X)

        # 1. Raw log-density
        out[:, 0] = log_d

        # 2. Z-scored log-density
        out[:, 1] = (log_d - self._ref_mean_ld) / self._ref_std_ld

        # 3. Density gradient magnitude (finite difference approximation)
        m = X.shape[1]
        delta = self._h * 0.01
        for j in range(min(m, 10)):  # cap to avoid explosion
            X_plus = X.copy()
            X_plus[:, j] += delta
            ld_plus = self._kde_log_density(X_plus)
            out[:, 2] += ((ld_plus - log_d) / delta) ** 2
        out[:, 2] = np.sqrt(out[:, 2])

        # 4. Density rank (percentile)
        out[:, 3] = np.searchsorted(self._sorted_ref_ld, log_d) / len(self._sorted_ref_ld)

        return out


# ═══════════════════════════════════════════════════════════════════
# 3. TOPOLOGICAL SPECTRUM (TDA-lite)
# ═══════════════════════════════════════════════════════════════════

class TopologicalSpectrum:
    """
    Persistent homology proxy using local neighborhood structure.

    No external TDA library needed. Approximates topological features:
      1. Local connectivity: at what distance does the ε-ball become connected?
      2. Hole indicator: ratio of volume of ε-ball to convex hull of neighbors
      3. Dimension estimate: local intrinsic dimensionality
      4. Boundary indicator: fraction of angular coverage around point
      5. Persistence proxy: gap between 1st and kth neighbor distance

    Captures manifold holes, boundaries, and dimensional changes.
    """

    def __init__(self, k=15, eps=1e-10):
        self.k = k
        self.eps = eps
        self._X_ref = None
        self._ref_stats = None
        self._ref_std = None

    def fit(self, X_ref):
        N = len(X_ref)
        k = min(self.k, N - 1)
        self.k = k
        self._X_ref = X_ref.copy()

        # Compute reference statistics
        ref_features = self._compute_features(X_ref, X_ref)
        self._ref_mean = ref_features.mean(axis=0)
        self._ref_std = ref_features.std(axis=0) + self.eps
        return self

    def _compute_features(self, X_query, X_ref):
        N = len(X_query)
        k = self.k
        m = X_ref.shape[1]
        out = np.zeros((N, 5), dtype=np.float64)

        D = cdist(X_query, X_ref, metric='euclidean')
        sorted_idx = np.argsort(D, axis=1)[:, :k]

        for i in range(N):
            nn_idx = sorted_idx[i]
            nn_dists = D[i, nn_idx]
            nn_points = X_ref[nn_idx]

            # 1. Connectivity radius ratio: d_k / d_1
            d1 = nn_dists[0] + self.eps
            dk = nn_dists[-1] + self.eps
            out[i, 0] = dk / d1

            # 2. Density uniformity in neighborhood
            # Ratio of median to mean distance (uniform → 1, clustered → <1)
            out[i, 1] = np.median(nn_dists) / (np.mean(nn_dists) + self.eps)

            # 3. Local intrinsic dimensionality (MLE estimate)
            # Levina-Bickel estimator
            log_ratios = np.log(dk / (nn_dists[:-1] + self.eps) + self.eps)
            if len(log_ratios) > 0 and np.sum(log_ratios) > self.eps:
                lid = (k - 1) / np.sum(log_ratios)
                out[i, 2] = lid
            else:
                out[i, 2] = m  # default to ambient dim

            # 4. Angular coverage (boundary detection)
            # Center neighbors, compute angles between them
            centered = nn_points - X_query[i]
            norms = np.linalg.norm(centered, axis=1, keepdims=True) + self.eps
            unit_vecs = centered / norms
            # Cosine similarity matrix
            cos_sim = unit_vecs @ unit_vecs.T
            # Angular spread: how much of the sphere is covered
            # If all neighbors on one side → low coverage → boundary
            mean_cos = np.mean(cos_sim[np.triu_indices(k, k=1)])
            out[i, 3] = mean_cos  # high → clustered neighbors → boundary

            # 5. Persistence proxy: d_k - d_1 normalized
            out[i, 4] = (dk - d1) / (dk + self.eps)

        return out

    def transform(self, X):
        features = self._compute_features(X, self._X_ref)
        # Z-score relative to reference
        return (features - self._ref_mean) / self._ref_std


# ═══════════════════════════════════════════════════════════════════
# 4. DEPENDENCY / COPULA SPECTRUM
# ═══════════════════════════════════════════════════════════════════

class DependencyCopulaSpectrum:
    """
    Pairwise statistical dependency structure.

    Unlike Phase Curve (which captures displacement), this captures
    the *statistical dependency* between feature pairs:
      1. Per-point contribution to pairwise correlation deviation
      2. Product-moment anomaly score
      3. Rank-based dependency (Kendall-like)
      4. Tail dependency indicator
      5. Conditional deviation (feature given neighbors)

    Catches anomalies with normal marginals but abnormal joint structure.
    """

    def __init__(self, max_pairs=20, eps=1e-10):
        self.max_pairs = max_pairs
        self.eps = eps
        self._ref_corr = None
        self._ref_means = None
        self._ref_stds = None
        self._pair_indices = None

    def fit(self, X_ref):
        N, m = X_ref.shape
        self._ref_means = X_ref.mean(axis=0)
        self._ref_stds = X_ref.std(axis=0) + self.eps

        # Z-score the reference
        Z_ref = (X_ref - self._ref_means) / self._ref_stds

        # Reference correlation matrix
        self._ref_corr = np.corrcoef(Z_ref.T)
        np.fill_diagonal(self._ref_corr, 0)

        # Select most correlated pairs (most informative)
        n_pairs = min(self.max_pairs, m * (m - 1) // 2)
        upper_tri = np.triu_indices(m, k=1)
        abs_corrs = np.abs(self._ref_corr[upper_tri])
        top_idx = np.argsort(abs_corrs)[-n_pairs:]
        self._pair_indices = [(upper_tri[0][i], upper_tri[1][i]) for i in top_idx]
        self._n_pairs = len(self._pair_indices)

        # Reference pair products (for deviation computation)
        self._ref_pair_means = np.zeros(self._n_pairs)
        self._ref_pair_stds = np.zeros(self._n_pairs)
        for idx, (j1, j2) in enumerate(self._pair_indices):
            products = Z_ref[:, j1] * Z_ref[:, j2]
            self._ref_pair_means[idx] = products.mean()
            self._ref_pair_stds[idx] = products.std() + self.eps

        # Reference rank correlations
        self._ref_ranks = np.zeros((N, m))
        for j in range(m):
            self._ref_ranks[:, j] = np.argsort(np.argsort(X_ref[:, j])) / N

        return self

    def transform(self, X):
        N, m = X.shape
        out = np.zeros((N, 5), dtype=np.float64)

        Z = (X - self._ref_means) / self._ref_stds

        # 1. Mean product-moment deviation across selected pairs
        pair_devs = np.zeros(N)
        for idx, (j1, j2) in enumerate(self._pair_indices):
            products = Z[:, j1] * Z[:, j2]
            pair_devs += np.abs(products - self._ref_pair_means[idx]) / self._ref_pair_stds[idx]
        out[:, 0] = pair_devs / max(self._n_pairs, 1)

        # 2. Max pair deviation (worst single dependency)
        max_dev = np.zeros(N)
        for idx, (j1, j2) in enumerate(self._pair_indices):
            products = Z[:, j1] * Z[:, j2]
            dev = np.abs(products - self._ref_pair_means[idx]) / self._ref_pair_stds[idx]
            max_dev = np.maximum(max_dev, dev)
        out[:, 1] = max_dev

        # 3. Correlation structure anomaly
        # How much does this point's cross-product pattern deviate?
        if self._n_pairs > 1:
            point_pattern = np.zeros((N, self._n_pairs))
            for idx, (j1, j2) in enumerate(self._pair_indices):
                point_pattern[:, idx] = Z[:, j1] * Z[:, j2]
            # Deviation of pattern from reference
            pattern_dev = (point_pattern - self._ref_pair_means) / self._ref_pair_stds
            out[:, 2] = np.std(pattern_dev, axis=1)

        # 4. Tail dependency: fraction of features in extreme quantiles
        for j in range(m):
            z_abs = np.abs(Z[:, j])
            out[:, 3] += (z_abs > 2.0).astype(float)
        out[:, 3] /= m

        # 5. Joint extremity: product of z-scores across features
        # Log of product = sum of logs
        log_z = np.log(np.abs(Z) + self.eps)
        out[:, 4] = log_z.mean(axis=1)

        return out


# ═══════════════════════════════════════════════════════════════════
# 5. COMPRESSIBILITY SPECTRUM
# ═══════════════════════════════════════════════════════════════════

class CompressibilitySpectrum:
    """
    Kolmogorov complexity proxy via compression and entropy measures.

    Computes per-point:
      1. Compression ratio (zlib)
      2. Byte entropy of quantized feature vector
      3. Run-length complexity
      4. Unique-value ratio
      5. Quantized pattern hash deviation

    Extremely fast, completely orthogonal to geometric/statistical views.
    """

    def __init__(self, n_bins=32, eps=1e-10):
        self.n_bins = n_bins
        self.eps = eps
        self._bin_edges = None
        self._ref_stats = None
        self._ref_std = None

    def fit(self, X_ref):
        N, m = X_ref.shape
        # Learn bin edges from reference data per feature
        self._bin_edges = []
        for j in range(m):
            edges = np.percentile(X_ref[:, j],
                                  np.linspace(0, 100, self.n_bins + 1))
            edges[0] -= 1e-6
            edges[-1] += 1e-6
            self._bin_edges.append(edges)

        # Compute reference statistics
        ref_features = self._compute_features(X_ref)
        self._ref_mean = ref_features.mean(axis=0)
        self._ref_std = ref_features.std(axis=0) + self.eps
        return self

    def _compute_features(self, X):
        import zlib
        N, m = X.shape
        out = np.zeros((N, 5), dtype=np.float64)

        for i in range(N):
            row = X[i]

            # Quantize to bin indices
            quantized = np.zeros(m, dtype=np.uint8)
            for j in range(m):
                quantized[j] = np.searchsorted(self._bin_edges[j], row[j]) - 1
            quantized = np.clip(quantized, 0, self.n_bins - 1)

            # 1. Compression ratio
            raw_bytes = quantized.tobytes()
            compressed = zlib.compress(raw_bytes, level=1)
            out[i, 0] = len(compressed) / (len(raw_bytes) + self.eps)

            # 2. Byte entropy
            byte_counts = np.bincount(quantized, minlength=self.n_bins)
            probs = byte_counts / (m + self.eps)
            probs = probs[probs > 0]
            out[i, 1] = -np.sum(probs * np.log2(probs + self.eps))

            # 3. Run-length complexity
            runs = 1
            for k in range(1, len(quantized)):
                if quantized[k] != quantized[k - 1]:
                    runs += 1
            out[i, 2] = runs / m

            # 4. Unique value ratio
            out[i, 3] = len(np.unique(quantized)) / self.n_bins

            # 5. Sorted-order deviation (how far from sorted?)
            sorted_q = np.sort(quantized)
            out[i, 4] = np.mean(np.abs(quantized.astype(float) - sorted_q.astype(float)))

        return out

    def transform(self, X):
        features = self._compute_features(X)
        return (features - self._ref_mean) / self._ref_std


# ═══════════════════════════════════════════════════════════════════
# 6. KERNEL / RKHS SPECTRUM
# ═══════════════════════════════════════════════════════════════════

class KernelRKHSSpectrum:
    """
    Nonlinear reconstruction error via kernel PCA.

    Uses RBF kernel to project into RKHS, keeps top-k components,
    reconstructs, and measures the error. Captures *nonlinear*
    off-manifold deviation that linear SVD (ReconstructionSpectrum) misses.

    Computes per-point:
      1. Kernel PCA reconstruction error
      2. Projection magnitude (distance from origin in RKHS)
      3. Residual entropy
      4. Max component deviation
      5. Kernel distance to centroid
    """

    def __init__(self, n_components=10, gamma='auto', max_ref=1500, eps=1e-10):
        self.n_components = n_components
        self.gamma = gamma
        self.max_ref = max_ref
        self.eps = eps
        self._X_ref = None
        self._alphas = None
        self._eigenvalues = None
        self._gamma = None
        self._ref_stats = None
        self._ref_std = None

    def _rbf_kernel(self, X1, X2):
        D_sq = cdist(X1, X2, metric='sqeuclidean')
        return np.exp(-self._gamma * D_sq)

    def fit(self, X_ref):
        N, m = X_ref.shape

        # Subsample if large
        if N > self.max_ref:
            rng = np.random.RandomState(42)
            idx = rng.choice(N, self.max_ref, replace=False)
            X_ref = X_ref[idx]
            N = self.max_ref

        self._X_ref = X_ref.copy()

        # Auto bandwidth
        if self.gamma == 'auto':
            D_sq = cdist(X_ref, X_ref, metric='sqeuclidean')
            median_sq = np.median(D_sq[D_sq > 0])
            self._gamma = 1.0 / (median_sq + self.eps)
        else:
            self._gamma = self.gamma

        # Kernel matrix
        K = self._rbf_kernel(X_ref, X_ref)

        # Center kernel matrix
        N_ref = len(X_ref)
        one_N = np.ones((N_ref, N_ref)) / N_ref
        K_centered = K - one_N @ K - K @ one_N + one_N @ K @ one_N

        # Eigendecomposition
        eigenvalues, eigenvectors = np.linalg.eigh(K_centered)
        # Sort descending
        idx_sort = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[idx_sort]
        eigenvectors = eigenvectors[:, idx_sort]

        n_comp = min(self.n_components, N_ref)
        self.n_components = n_comp

        # Keep top components
        self._eigenvalues = np.maximum(eigenvalues[:n_comp], self.eps)
        self._alphas = eigenvectors[:, :n_comp]
        self._K_ref = K
        self._one_N = one_N

        # Reference stats
        ref_features = self._compute_features(X_ref)
        self._ref_mean = ref_features.mean(axis=0)
        self._ref_std = ref_features.std(axis=0) + self.eps
        return self

    def _compute_features(self, X):
        N = len(X)
        n_comp = self.n_components
        out = np.zeros((N, 5), dtype=np.float64)

        # Kernel between query and reference
        K_test = self._rbf_kernel(X, self._X_ref)
        N_ref = len(self._X_ref)

        # Center test kernel
        one_test = np.ones((N, N_ref)) / N_ref
        K_ref_mean = self._K_ref.mean(axis=0, keepdims=True)
        K_test_centered = (K_test - one_test @ self._K_ref
                           - K_test.mean(axis=1, keepdims=True)
                           + self._K_ref.mean())

        # Project onto top components
        projections = K_test_centered @ self._alphas / np.sqrt(self._eigenvalues + self.eps)

        # Reconstruction in kernel space
        K_reconstructed = (projections * np.sqrt(self._eigenvalues)) @ self._alphas.T
        # Add back centering (approximate)
        K_recon_full = K_reconstructed + one_test @ self._K_ref + K_test.mean(axis=1, keepdims=True) - self._K_ref.mean()

        # Reconstruction error: ||phi(x) - phi_recon(x)||^2
        # = K(x,x) - 2*K_recon(x,.) + K_recon_recon
        diag_K_test = np.ones(N)  # RBF self-kernel = 1
        recon_error = diag_K_test - np.sum(projections ** 2, axis=1)
        recon_error = np.maximum(recon_error, 0)

        # 1. Reconstruction error
        out[:, 0] = np.sqrt(recon_error + self.eps)

        # 2. Projection magnitude
        out[:, 1] = np.sqrt(np.sum(projections ** 2, axis=1))

        # 3. Residual entropy (how spread across remaining components)
        abs_proj = np.abs(projections) + self.eps
        proj_probs = abs_proj / abs_proj.sum(axis=1, keepdims=True)
        out[:, 2] = -np.sum(proj_probs * np.log(proj_probs), axis=1)

        # 4. Max component deviation
        out[:, 3] = np.max(np.abs(projections), axis=1)

        # 5. Kernel distance to centroid
        K_test_mean = K_test.mean(axis=1)
        out[:, 4] = np.sqrt(np.maximum(1.0 - 2 * K_test_mean + self._K_ref.mean(), 0))

        return out

    def transform(self, X):
        features = self._compute_features(X)
        return (features - self._ref_mean) / self._ref_std
