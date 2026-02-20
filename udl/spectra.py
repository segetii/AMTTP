"""
Spectrum Projection Operators — Law-Domain Feature Extraction
==============================================================
Each operator transforms raw observation rows into a specific
law-domain representation. These are composable building blocks
of the Representation Stack.

Design:
  - Each operator is a callable class with fit() / transform() semantics
  - All share the same interface: (X_raw) → (X_projected)
  - Operators are domain-agnostic by design
"""

import numpy as np
from scipy.fft import rfft, rfftfreq
from scipy.stats import entropy as sp_entropy


# ═══════════════════════════════════════════════════════════════════
# 1. STATISTICAL / PROBABILISTIC SPECTRUM
# ═══════════════════════════════════════════════════════════════════

class StatisticalSpectrum:
    """
    Projects observation into statistical deviation space.

    Computes per-row:
      - Row entropy (Shannon)
      - KL divergence from reference distribution
      - Hellinger distance from reference
      - Skewness and kurtosis of row values
    """

    def __init__(self, eps=1e-10):
        self.eps = eps
        self.ref_dist = None

    def fit(self, X_ref):
        """Compute reference distribution from normal data."""
        # Normalise each row to probability vector
        row_sums = np.abs(X_ref).sum(axis=1, keepdims=True) + self.eps
        P_ref = np.abs(X_ref) / row_sums
        # Average distribution across all reference rows
        self.ref_dist = P_ref.mean(axis=0)
        self.ref_dist = self.ref_dist / (self.ref_dist.sum() + self.eps)
        return self

    def transform(self, X):
        """Project each row into statistical deviation coordinates (vectorised)."""
        N, m = X.shape
        out = np.zeros((N, 5), dtype=np.float64)

        row_sums = np.abs(X).sum(axis=1, keepdims=True) + self.eps
        P = np.abs(X) / row_sums

        q = self.ref_dist if self.ref_dist is not None else np.full(m, 1.0 / m)
        q_safe = np.clip(q, self.eps, 1.0)
        P_safe = np.clip(P, self.eps, 1.0)

        # 1. Shannon entropy per row: -Σ p_i log p_i
        out[:, 0] = -np.sum(P_safe * np.log(P_safe), axis=1)

        # 2. KL divergence: Σ p_i log(p_i / q_i)
        out[:, 1] = np.sum(P_safe * np.log(P_safe / q_safe[None, :]), axis=1)

        # 3. Hellinger distance
        out[:, 2] = np.sqrt(0.5 * np.sum((np.sqrt(P_safe) - np.sqrt(q_safe)[None, :]) ** 2, axis=1))

        # 4. Skewness per row
        mu = P.mean(axis=1, keepdims=True)
        sigma = P.std(axis=1, keepdims=True) + self.eps
        z = (P - mu) / sigma
        out[:, 3] = np.mean(z ** 3, axis=1)

        # 5. Kurtosis per row
        out[:, 4] = np.mean(z ** 4, axis=1) - 3.0

        return out


# ═══════════════════════════════════════════════════════════════════
# 2. CHAOS / DYNAMICAL SPECTRUM
# ═══════════════════════════════════════════════════════════════════

class ChaosSpectrum:
    """
    Projects observation into dynamical deviation space.

    Treats each row as discrete signal f(t) and computes:
      - Lyapunov-like divergence exponent from reference
      - Recurrence rate (fraction of repeated patterns)
      - Approximate entropy (complexity measure)
    """

    def __init__(self, eps=1e-10):
        self.eps = eps
        self.ref_signal = None

    def fit(self, X_ref):
        """Compute reference signal (mean waveform of normal data)."""
        self.ref_signal = X_ref.mean(axis=0)
        return self

    def transform(self, X):
        """Project each row into chaos deviation coordinates."""
        N, m = X.shape
        out = np.zeros((N, 3), dtype=np.float64)

        ref = self.ref_signal if self.ref_signal is not None else np.zeros(m)

        for i in range(N):
            # Lyapunov-like divergence
            diff = np.abs(X[i] - ref) + self.eps
            if m > 1:
                ratios = diff[1:] / (diff[:-1] + self.eps)
                ratios = np.clip(ratios, self.eps, 1e6)
                out[i, 0] = np.mean(np.log(ratios))
            else:
                out[i, 0] = 0.0

            # Recurrence rate (simplified: fraction of values within threshold)
            threshold = np.std(X[i]) * 0.1 + self.eps
            dist_matrix = np.abs(X[i, :, None] - X[i, None, :])
            recurrence = (dist_matrix < threshold).sum() / max(m * m, 1)
            out[i, 1] = recurrence

            # Approximate entropy (simplified)
            out[i, 2] = self._approx_entropy(X[i], m_order=2, r=0.2)

        return out

    def _approx_entropy(self, signal, m_order=2, r=0.2):
        """Simplified approximate entropy."""
        N = len(signal)
        if N < m_order + 1:
            return 0.0
        r_val = r * (np.std(signal) + self.eps)

        def phi(m):
            templates = np.array([signal[j:j + m] for j in range(N - m + 1)])
            count = 0
            total = len(templates)
            for k in range(total):
                dists = np.max(np.abs(templates - templates[k]), axis=1)
                count += np.sum(dists <= r_val)
            return np.log(count / (total * total) + self.eps)

        return abs(phi(m_order) - phi(m_order + 1))


# ═══════════════════════════════════════════════════════════════════
# 3. SPECTRAL / FREQUENCY SPECTRUM
# ═══════════════════════════════════════════════════════════════════

class SpectralSpectrum:
    """
    Projects observation into frequency deviation space.

    Computes:
      - Power spectral density deviation from reference
      - Dominant frequency ratio
      - Spectral entropy
      - Spectral centroid shift
    """

    def __init__(self, eps=1e-10):
        self.eps = eps
        self.ref_psd = None
        self.ref_centroid = None

    def fit(self, X_ref):
        """Compute reference spectral profile."""
        N, m = X_ref.shape
        n_freq = m // 2 + 1
        psds = np.zeros((N, n_freq))
        for i in range(N):
            fft_vals = rfft(X_ref[i])
            psds[i] = np.abs(fft_vals) ** 2
        self.ref_psd = psds.mean(axis=0)
        self.ref_psd = self.ref_psd / (self.ref_psd.sum() + self.eps)

        # Reference spectral centroid
        freqs = np.arange(n_freq)
        self.ref_centroid = np.sum(freqs * self.ref_psd)
        return self

    def transform(self, X):
        """Project each row into spectral deviation coordinates (vectorised)."""
        N, m = X.shape
        n_freq = m // 2 + 1
        out = np.zeros((N, 4), dtype=np.float64)
        freqs = np.arange(n_freq)
        ref_psd = self.ref_psd if self.ref_psd is not None else np.ones(n_freq) / n_freq

        # Batch FFT — rfft supports axis param
        fft_all = rfft(X, axis=1)                       # (N, n_freq) complex
        psd_all = np.abs(fft_all) ** 2                   # (N, n_freq)
        psd_sums = psd_all.sum(axis=1, keepdims=True) + self.eps
        psd_norm = psd_all / psd_sums                    # (N, n_freq)

        # 1. PSD L2 divergence from reference
        out[:, 0] = np.sqrt(np.sum((psd_norm - ref_psd[None, :]) ** 2, axis=1))

        # 2. Dominant frequency ratio
        dom_obs = np.argmax(psd_norm, axis=1)            # (N,)
        dom_ref = np.argmax(ref_psd)
        out[:, 1] = np.abs(dom_obs - dom_ref) / max(n_freq, 1)

        # 3. Spectral entropy  -Σ p log p
        psd_safe = psd_norm + self.eps
        out[:, 2] = -np.sum(psd_safe * np.log(psd_safe), axis=1)

        # 4. Spectral centroid shift
        centroids = np.sum(freqs[None, :] * psd_norm, axis=1)
        ref_c = self.ref_centroid if self.ref_centroid is not None else centroids
        out[:, 3] = np.abs(centroids - ref_c)

        return out


# ═══════════════════════════════════════════════════════════════════
# 4. GEOMETRIC / MANIFOLD SPECTRUM
# ═══════════════════════════════════════════════════════════════════

class GeometricSpectrum:
    """
    Projects observation into geometric deviation space.

    Computes:
      - Mahalanobis distance from reference centroid
      - Cosine dissimilarity from reference direction
      - L2 norm ratio (magnitude relative to reference)
    """

    def __init__(self, eps=1e-10):
        self.eps = eps
        self.mu = None
        self.cov_inv = None
        self.ref_norm = None

    def fit(self, X_ref):
        """Compute reference geometry (centroid + covariance)."""
        self.mu = X_ref.mean(axis=0)
        cov = np.cov(X_ref.T) + self.eps * np.eye(X_ref.shape[1])
        try:
            self.cov_inv = np.linalg.inv(cov)
        except np.linalg.LinAlgError:
            self.cov_inv = np.linalg.pinv(cov)
        self.ref_norm = np.linalg.norm(self.mu) + self.eps
        return self

    def transform(self, X):
        """Project each row into geometric deviation coordinates (vectorised)."""
        N, m = X.shape
        out = np.zeros((N, 3), dtype=np.float64)
        mu = self.mu if self.mu is not None else np.zeros(m)

        diff = X - mu[None, :]  # (N, m)

        # 1. Mahalanobis distance
        if self.cov_inv is not None:
            # mahal_sq_i = diff_i @ cov_inv @ diff_i^T  (vectorised)
            mahal_sq = np.sum(diff @ self.cov_inv * diff, axis=1)
            out[:, 0] = np.sqrt(np.maximum(mahal_sq, 0))
        else:
            out[:, 0] = np.linalg.norm(diff, axis=1)

        # 2. Cosine dissimilarity from reference direction
        norms_x = np.linalg.norm(X, axis=1) + self.eps
        norm_mu = np.linalg.norm(mu) + self.eps
        cos_sim = (X @ mu) / (norms_x * norm_mu)
        out[:, 1] = 1.0 - np.clip(cos_sim, -1, 1)

        # 3. Norm ratio
        ref_n = self.ref_norm if self.ref_norm else 1.0
        out[:, 2] = norms_x / ref_n

        return out


# ═══════════════════════════════════════════════════════════════════
# 5. EXPONENTIAL / ENERGY AMPLIFICATION LAYER  (legacy, kept for compat)
# ═══════════════════════════════════════════════════════════════════

class ExponentialSpectrum:
    """
    Applies exponential amplification to observation features.

    This is NOT a standalone metric — it amplifies small deviations
    into energy-scale differences, making subtle anomalies separable.

    Maps: x → exp(α * (x - μ_ref) / σ_ref)

    Output is compressed to max_dim via PCA if input dimension is large.
    """

    def __init__(self, alpha=1.0, max_dim=10, eps=1e-10):
        self.alpha = alpha
        self.max_dim = max_dim
        self.eps = eps
        self.mu = None
        self.sigma = None
        self._pca_components = None
        self._pca_mean = None

    def fit(self, X_ref):
        """Compute reference mean and scale."""
        self.mu = X_ref.mean(axis=0)
        self.sigma = X_ref.std(axis=0) + self.eps
        # Pre-compute PCA reduction if needed
        if X_ref.shape[1] > self.max_dim:
            exp_ref = self._raw_transform(X_ref)
            self._pca_mean = exp_ref.mean(axis=0)
            centered = exp_ref - self._pca_mean
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            self._pca_components = Vt[:self.max_dim]
        return self

    def _raw_transform(self, X):
        mu = self.mu if self.mu is not None else np.zeros(X.shape[1])
        sigma = self.sigma if self.sigma is not None else np.ones(X.shape[1])
        z = (X - mu) / sigma
        z = np.clip(z, -10, 10)
        return np.exp(self.alpha * z)

    def transform(self, X):
        """Apply controlled exponential amplification (with PCA compression)."""
        exp_out = self._raw_transform(X)
        if self._pca_components is not None:
            return (exp_out - self._pca_mean) @ self._pca_components.T
        return exp_out


# ═══════════════════════════════════════════════════════════════════
# 6. RECONSTRUCTION / OFF-MANIFOLD SPECTRUM  (replaces Exponential)
# ═══════════════════════════════════════════════════════════════════

class ReconstructionSpectrum:
    """
    Detects off-manifold anomalies via SVD reconstruction error.

    Idea:  Fit a low-rank linear subspace on normal data.
           Anomalies that deviate from this subspace have large
           reconstruction residuals in directions not captured
           by the dominant singular vectors.

    Features (5-dimensional output):
      1. Total reconstruction error  ‖x - x̂‖₂
      2. Relative reconstruction error  ‖x - x̂‖ / ‖x‖
      3. Max absolute residual (spike detector)
      4. Residual entropy  H(|r|/Σ|r|)  — uniformly-spread vs concentrated
      5. Subspace projection magnitude  ‖x̂‖  (how much is *on* manifold)

    Properties:
      - Zero learnable parameters — pure linear algebra (SVD)
      - Closed-form, deterministic
      - Catches anomalies invisible to distance metrics
        (off-manifold but equidistant from centroid)
    """

    def __init__(self, rank_ratio=0.8, min_rank=2, max_rank=20, eps=1e-10):
        self.rank_ratio = rank_ratio   # fraction of variance to retain
        self.min_rank = min_rank
        self.max_rank = max_rank
        self.eps = eps
        self._mu = None
        self._Vr = None       # right singular vectors (top-r)
        self._rank = None

    def fit(self, X_ref):
        """Compute the normal-data subspace via truncated SVD."""
        N, m = X_ref.shape
        self._mu = X_ref.mean(axis=0)
        X_centered = X_ref - self._mu

        U, S, Vt = np.linalg.svd(X_centered, full_matrices=False)

        # Choose rank to retain `rank_ratio` of total variance
        total_var = (S ** 2).sum()
        cum_var = np.cumsum(S ** 2) / (total_var + self.eps)
        r = int(np.searchsorted(cum_var, self.rank_ratio) + 1)
        r = max(self.min_rank, min(r, self.max_rank, len(S)))

        self._Vr = Vt[:r]        # shape (r, m)
        self._rank = r
        return self

    def transform(self, X):
        """Project each row, reconstruct, and extract residual features (vectorised)."""
        N, m = X.shape
        out = np.zeros((N, 5), dtype=np.float64)

        mu = self._mu if self._mu is not None else np.zeros(m)
        X_centered = X - mu

        # Projection onto subspace:  x̂ = Vr^T Vr x_c
        proj_coeffs = X_centered @ self._Vr.T          # (N, r)
        X_reconstructed = proj_coeffs @ self._Vr        # (N, m)
        residuals = X_centered - X_reconstructed        # (N, m)

        # 1. Total reconstruction error  ‖r‖
        recon_err = np.linalg.norm(residuals, axis=1)
        out[:, 0] = recon_err

        # 2. Relative reconstruction error
        x_norms = np.linalg.norm(X_centered, axis=1) + self.eps
        out[:, 1] = recon_err / x_norms

        # 3. Max absolute residual (spike)
        out[:, 2] = np.max(np.abs(residuals), axis=1)

        # 4. Residual entropy  H(|r|/Σ|r|)  — vectorised
        abs_r = np.abs(residuals) + self.eps               # (N, m)
        p_r = abs_r / abs_r.sum(axis=1, keepdims=True)     # row-normalised
        out[:, 3] = -np.sum(p_r * np.log(p_r + 1e-30), axis=1)

        # 5. Subspace projection magnitude
        out[:, 4] = np.linalg.norm(X_reconstructed, axis=1)

        return out


# ═══════════════════════════════════════════════════════════════════
# 7. RANK-ORDER / PERCENTILE SPECTRUM  (new 6th law domain)
# ═══════════════════════════════════════════════════════════════════

class RankOrderSpectrum:
    """
    Distribution-free extremity detection via rank-order statistics.

    Idea:  For each feature, compute the percentile rank of the
           observation relative to the reference population.
           Anomalies have many features in extreme percentiles.

    Features (5-dimensional output):
      1. Max percentile rank across features  (catches single-feature spikes)
      2. Mean percentile rank  (diffuse extremity)
      3. Count of features in tail (>95th or <5th percentile)
      4. Rank entropy  H(ranks)  — uniform ranks = normal, skewed = anomaly
      5. Interquartile deviation  (fraction of features outside IQR of ranks)

    Properties:
      - Completely distribution-free — no Gaussian assumption
      - Naturally bounded [0, 1] ranks — no normalisation needed
      - Absorbs the advantage of KNN/LOF without learning density
      - O(m log N) per observation via searchsorted
    """

    def __init__(self, tail_threshold=0.05, eps=1e-10):
        self.tail_threshold = tail_threshold
        self.eps = eps
        self._sorted_ref = None  # (m,) arrays of sorted reference values per feature
        self._N_ref = None

    def fit(self, X_ref):
        """Sort each feature column of reference data for percentile lookup."""
        self._N_ref = X_ref.shape[0]
        # Sort each feature independently
        self._sorted_ref = np.sort(X_ref, axis=0)  # (N_ref, m)
        return self

    def transform(self, X):
        """Compute rank-order features for each observation (vectorised)."""
        N, m = X.shape
        out = np.zeros((N, 5), dtype=np.float64)

        N_ref = self._N_ref

        # Vectorised percentile rank:  for each feature j, searchsorted all N rows at once
        ranks = np.zeros((N, m), dtype=np.float64)
        for j in range(m):
            ranks[:, j] = np.searchsorted(self._sorted_ref[:, j], X[:, j],
                                           side='right') / N_ref

        # Extremity: distance from 0.5  → 0 = median, 1 = extreme
        extremity = np.abs(ranks - 0.5) * 2.0   # (N, m)

        # 1. Max percentile extremity
        out[:, 0] = np.max(extremity, axis=1)

        # 2. Mean percentile extremity
        out[:, 1] = np.mean(extremity, axis=1)

        # 3. Fraction of tail features (< threshold or > 1-threshold)
        tail = (ranks < self.tail_threshold) | (ranks > (1.0 - self.tail_threshold))
        out[:, 2] = tail.sum(axis=1) / max(m, 1)

        # 4. Rank entropy — vectorised
        p_ext = extremity + self.eps
        p_ext = p_ext / p_ext.sum(axis=1, keepdims=True)
        out[:, 3] = -np.sum(p_ext * np.log(p_ext + 1e-30), axis=1)

        # 5. IQR deviation: fraction of features with extremity > 0.5
        out[:, 4] = (extremity > 0.5).sum(axis=1) / max(m, 1)

        return out
