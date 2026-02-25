"""
Functional Feature Extraction for Anomaly Detection
=====================================================
Transforms each data row x ∈ ℝⁿ into a functional representation f(t),
extracts structural coefficients θ = (β₀, β₁, β₂, ..., aₖ),
and produces a compact parametric embedding that preserves anomaly geometry.

Pipeline:
    Raw row x → Functional embedding f(t) → Coefficient extraction θ
    → Dimensional geometry modelling → Cluster / deviation detection

Three canonical orderings are supported (to avoid arbitrary feature index):
    1. 'sorted'   — Sort features ascending → monotone shape function
    2. 'variance'  — Order by global variance rank (most stable → most volatile)
    3. 'raw'       — Use original feature index (valid when features are sequential)

Extractors:
    - Polynomial coefficients (intercept, gradient, curvature, jerk)
    - DCT spectral coefficients (frequency decomposition)
    - Statistical shape descriptors (energy, entropy, skewness, kurtosis)
    - Wavelet energy bands (multi-resolution)

Reference:
    Functional Data Analysis (Ramsay & Silverman, 2005)
    This is *not* PCA — it is structure-preserving parametric compression.
"""

import numpy as np
from scipy.fft import dct
from scipy.stats import skew, kurtosis


class FunctionalExtractor:
    """
    Transforms raw feature matrix into structural coefficient space.

    Parameters
    ----------
    ordering : str
        How to define the independent variable t for each row.
        'sorted' = sort features ascending (canonical shape).
        'variance' = order by global feature variance rank.
        'raw' = use original column order.
    poly_degree : int
        Degree of polynomial fit (default 3 → intercept, slope, curvature, jerk).
    n_dct : int
        Number of DCT coefficients to keep (default 5).
    include_stats : bool
        Whether to include statistical shape descriptors.
    include_wavelets : bool
        Whether to include wavelet energy bands.
    standardize : bool
        Whether to z-standardize each feature before extraction.
    """

    def __init__(self, ordering='sorted', poly_degree=3, n_dct=5,
                 include_stats=True, include_wavelets=True,
                 standardize=True):
        self.ordering = ordering
        self.poly_degree = poly_degree
        self.n_dct = n_dct
        self.include_stats = include_stats
        self.include_wavelets = include_wavelets
        self.standardize = standardize

        # Fitted state
        self._mean = None
        self._std = None
        self._variance_order = None
        self._t = None  # independent variable grid
        self._n_features = None

    def fit(self, X):
        """Learn ordering and standardization from training data."""
        n, d = X.shape
        self._n_features = d

        # Standardization parameters
        if self.standardize:
            self._mean = X.mean(axis=0)
            self._std = X.std(axis=0) + 1e-10
        else:
            self._mean = np.zeros(d)
            self._std = np.ones(d)

        # Variance-based ordering
        variances = X.var(axis=0)
        self._variance_order = np.argsort(variances)  # low variance → high

        # Independent variable grid (normalised to [0, 1])
        self._t = np.linspace(0, 1, d)

        return self

    def transform(self, X):
        """
        Extract functional coefficients from each row.

        Returns
        -------
        Theta : ndarray (N, k)
            Structural coefficient matrix.
        feature_names : list of str
            Names of extracted features.
        """
        n, d = X.shape
        assert d == self._n_features, f"Expected {self._n_features} features, got {d}"

        # Standardize
        X_s = (X - self._mean) / self._std

        # Apply ordering
        X_ordered = self._apply_ordering(X_s)

        features = []
        names = []

        # ── 1. Polynomial coefficients ──
        poly_feats, poly_names = self._extract_polynomial(X_ordered)
        features.append(poly_feats)
        names.extend(poly_names)

        # ── 2. DCT spectral coefficients ──
        dct_feats, dct_names = self._extract_dct(X_ordered)
        features.append(dct_feats)
        names.extend(dct_names)

        # ── 3. Statistical shape descriptors ──
        if self.include_stats:
            stat_feats, stat_names = self._extract_stats(X_ordered)
            features.append(stat_feats)
            names.extend(stat_names)

        # ── 4. Wavelet energy bands ──
        if self.include_wavelets and d >= 4:
            wav_feats, wav_names = self._extract_wavelets(X_ordered)
            features.append(wav_feats)
            names.extend(wav_names)

        # ── 5. Gradient-based features ──
        grad_feats, grad_names = self._extract_gradients(X_ordered)
        features.append(grad_feats)
        names.extend(grad_names)

        Theta = np.hstack(features)
        return Theta, names

    def fit_transform(self, X):
        """Fit and transform in one call."""
        self.fit(X)
        return self.transform(X)

    def _apply_ordering(self, X_s):
        """Reorder columns according to chosen ordering."""
        if self.ordering == 'sorted':
            # Each row sorted independently → canonical monotone shape
            return np.sort(X_s, axis=1)
        elif self.ordering == 'variance':
            return X_s[:, self._variance_order]
        elif self.ordering == 'raw':
            return X_s
        else:
            raise ValueError(f"Unknown ordering: {self.ordering}")

    def _extract_polynomial(self, X_ord):
        """Fit polynomial to each row's profile, extract coefficients."""
        n, d = X_ord.shape
        t = self._t
        deg = min(self.poly_degree, d - 1)

        # Vectorised polynomial fitting using Vandermonde matrix
        V = np.vander(t, N=deg + 1, increasing=True)  # (d, deg+1)
        # Least squares: coeffs = (V^T V)^{-1} V^T y for each row
        # X_ord is (n, d), V is (d, deg+1)
        # coeffs = X_ord @ V @ inv(V^T V)... use lstsq
        VtV_inv_Vt = np.linalg.lstsq(V, np.eye(d), rcond=None)[0]  # (deg+1, d)
        coeffs = X_ord @ VtV_inv_Vt.T  # (n, deg+1)

        # Also compute residual energy (how much the polynomial doesn't explain)
        fitted = coeffs @ V.T  # (n, d)
        residuals = X_ord - fitted
        residual_energy = np.sum(residuals ** 2, axis=1, keepdims=True) / d

        names = [f'poly_beta{i}' for i in range(deg + 1)] + ['poly_residual_energy']
        return np.hstack([coeffs, residual_energy]), names

    def _extract_dct(self, X_ord):
        """Discrete Cosine Transform — spectral decomposition."""
        n, d = X_ord.shape
        k = min(self.n_dct, d)

        # DCT-II (the standard one used in JPEG etc.)
        dct_full = dct(X_ord, type=2, axis=1, norm='ortho')  # (n, d)
        dct_coeffs = dct_full[:, :k]  # first k coefficients

        # Spectral energy concentration: fraction of energy in first k coefficients
        total_energy = np.sum(dct_full ** 2, axis=1, keepdims=True) + 1e-10
        partial_energy = np.sum(dct_coeffs ** 2, axis=1, keepdims=True)
        energy_ratio = partial_energy / total_energy

        names = [f'dct_{i}' for i in range(k)] + ['dct_energy_ratio']
        return np.hstack([dct_coeffs, energy_ratio]), names

    def _extract_stats(self, X_ord):
        """Statistical shape descriptors of the profile."""
        n, d = X_ord.shape

        energy = np.sum(X_ord ** 2, axis=1, keepdims=True) / d   # L2 energy
        entropy = self._profile_entropy(X_ord)                    # Shannon entropy
        range_ = (X_ord[:, -1] - X_ord[:, 0]).reshape(-1, 1)     # range (max-min for sorted)
        iqr = (np.percentile(X_ord, 75, axis=1) -
               np.percentile(X_ord, 25, axis=1)).reshape(-1, 1)  # IQR
        sk = skew(X_ord, axis=1).reshape(-1, 1)                  # skewness
        ku = kurtosis(X_ord, axis=1).reshape(-1, 1)              # kurtosis

        # Profile roughness: mean absolute second difference
        if d >= 3:
            d2 = np.diff(X_ord, n=2, axis=1)
            roughness = np.mean(np.abs(d2), axis=1, keepdims=True)
        else:
            roughness = np.zeros((n, 1))

        names = ['stat_energy', 'stat_entropy', 'stat_range', 'stat_iqr',
                 'stat_skewness', 'stat_kurtosis', 'stat_roughness']
        return np.hstack([energy, entropy, range_, iqr, sk, ku, roughness]), names

    def _profile_entropy(self, X_ord):
        """Shannon entropy of the absolute value profile (treated as distribution)."""
        n, d = X_ord.shape
        abs_x = np.abs(X_ord) + 1e-10
        p = abs_x / abs_x.sum(axis=1, keepdims=True)
        entropy = -np.sum(p * np.log(p + 1e-10), axis=1, keepdims=True)
        return entropy

    def _extract_wavelets(self, X_ord):
        """Simple Haar wavelet energy at different scales."""
        n, d = X_ord.shape
        bands = []
        names = []
        signal = X_ord.copy()

        level = 0
        while signal.shape[1] >= 2:
            # Haar decomposition: split into approximation + detail
            half = signal.shape[1] // 2
            # Pair adjacent values
            even = signal[:, :2*half:2]    # (n, half)
            odd = signal[:, 1:2*half:2]    # (n, half)
            approx = (even + odd) / np.sqrt(2)
            detail = (even - odd) / np.sqrt(2)

            # Detail energy at this level
            detail_energy = np.sum(detail ** 2, axis=1, keepdims=True) / half
            bands.append(detail_energy)
            names.append(f'wavelet_energy_L{level}')
            level += 1

            signal = approx
            if level >= 4:  # cap at 4 levels
                break

        # Approximation energy at coarsest level
        approx_energy = np.sum(signal ** 2, axis=1, keepdims=True) / max(signal.shape[1], 1)
        bands.append(approx_energy)
        names.append('wavelet_approx_energy')

        return np.hstack(bands), names

    def _extract_gradients(self, X_ord):
        """First and second derivative statistics of the profile."""
        n, d = X_ord.shape

        if d < 2:
            return np.zeros((n, 4)), ['grad_mean', 'grad_std', 'grad_max', 'grad_min']

        # First derivative (finite differences)
        dx = np.diff(X_ord, axis=1)  # (n, d-1)
        grad_mean = dx.mean(axis=1, keepdims=True)
        grad_std = dx.std(axis=1, keepdims=True)
        grad_max = dx.max(axis=1, keepdims=True)
        grad_min = dx.min(axis=1, keepdims=True)

        feats = [grad_mean, grad_std, grad_max, grad_min]
        names = ['grad_mean', 'grad_std', 'grad_max', 'grad_min']

        # Second derivative
        if d >= 3:
            d2x = np.diff(dx, axis=1)  # (n, d-2)
            curv_mean = d2x.mean(axis=1, keepdims=True)
            curv_std = d2x.std(axis=1, keepdims=True)
            curv_max = np.abs(d2x).max(axis=1, keepdims=True)
            feats.extend([curv_mean, curv_std, curv_max])
            names.extend(['curv_mean', 'curv_std', 'curv_max_abs'])

        return np.hstack(feats), names

    def describe(self):
        """Return summary of extraction configuration."""
        return {
            'ordering': self.ordering,
            'poly_degree': self.poly_degree,
            'n_dct': self.n_dct,
            'include_stats': self.include_stats,
            'include_wavelets': self.include_wavelets,
            'standardize': self.standardize,
            'n_input_features': self._n_features,
        }
