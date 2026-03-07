"""
Experimental Spectrum Operators — Candidate Law Domains
========================================================
Each operator represents a candidate "law" for the UDL framework.
All follow the same fit()/transform() interface as existing spectra.

APPROACH A — Functional Reduction:
  A1. FourierBasisSpectrum     — Fourier coefficient representation
  A2. BSplineBasisSpectrum     — B-spline coefficient representation
  A3. WaveletBasisSpectrum     — Wavelet coefficient representation
  A4. LegendreBasisSpectrum    — Legendre polynomial coefficient representation

APPROACH B — Coordinate System:
  B1. PolarSpectrum            — Hyperspherical coordinate decomposition
  B2. RadarPolygonSpectrum     — Radar chart polygon geometry
  B3. PhaseCurveSpectrum       — Feature-pair phase trajectory
  B4. GramEigenSpectrum        — Self-interaction Gram matrix eigenstructure

Results from benchmarking will determine which become official law domains.
"""

import numpy as np
from scipy.fft import rfft
from scipy.interpolate import BSpline
from scipy.stats import entropy as sp_entropy


# ═══════════════════════════════════════════════════════════════════
#  APPROACH A: FUNCTIONAL REDUCTION
# ═══════════════════════════════════════════════════════════════════


class FourierBasisSpectrum:
    """
    A1: Reduce each row to Fourier basis coefficients.

    Theory: Treating x_i as f(t_j), decompose into Fourier series.
    The coefficients c_k = |F[k]| capture the frequency content of
    the row's "shape". Anomalous rows have different frequency
    fingerprints than normal rows.

    Output: K Fourier magnitudes (normalised by reference).
    """

    def __init__(self, n_coeffs=8, eps=1e-10):
        self.n_coeffs = n_coeffs
        self.eps = eps
        self.ref_coeffs = None

    def fit(self, X_ref):
        N, m = X_ref.shape
        k = min(self.n_coeffs, m // 2 + 1)
        self.n_coeffs = k

        coeffs = np.zeros((N, k))
        for i in range(N):
            fft_vals = rfft(X_ref[i])
            coeffs[i] = np.abs(fft_vals[:k])

        self.ref_coeffs = coeffs.mean(axis=0) + self.eps
        self.ref_std = coeffs.std(axis=0) + self.eps
        return self

    def transform(self, X):
        N, m = X.shape
        k = self.n_coeffs
        out = np.zeros((N, k), dtype=np.float64)

        for i in range(N):
            fft_vals = rfft(X[i])
            magnitudes = np.abs(fft_vals[:k])
            # Z-score relative to reference distribution
            out[i] = (magnitudes - self.ref_coeffs) / self.ref_std

        return out


class BSplineBasisSpectrum:
    """
    A2: Reduce each row to B-spline basis coefficients.

    Theory: Fit a B-spline curve through the row values.
    The control point coefficients define the row's "shape" in a
    local basis. Anomalies have different local curvature patterns.

    Output: n_basis coefficients from least-squares B-spline fit.
    """

    def __init__(self, n_basis=6, degree=3, eps=1e-10):
        self.n_basis = n_basis
        self.degree = degree
        self.eps = eps
        self.ref_coeffs = None
        self.ref_std = None
        self._knots = None
        self._basis_matrix = None

    def _build_basis_matrix(self, m):
        """Build B-spline basis matrix for m evaluation points."""
        t = np.linspace(0, 1, m)
        n_internal = self.n_basis - self.degree - 1
        if n_internal < 0:
            n_internal = 0
            self.n_basis = self.degree + 1

        internal_knots = np.linspace(0, 1, n_internal + 2)[1:-1]
        self._knots = np.concatenate([
            np.zeros(self.degree + 1),
            internal_knots,
            np.ones(self.degree + 1)
        ])

        # Evaluate each basis function at all t values
        B = np.zeros((m, self.n_basis))
        for j in range(self.n_basis):
            c_j = np.zeros(self.n_basis)
            c_j[j] = 1.0
            spl = BSpline(self._knots, c_j, self.degree, extrapolate=False)
            vals = spl(t)
            vals = np.nan_to_num(vals, 0.0)
            B[:, j] = vals

        self._basis_matrix = B
        return B

    def fit(self, X_ref):
        N, m = X_ref.shape
        B = self._build_basis_matrix(m)

        # Least-squares coefficients for each row
        # c = (B^T B)^{-1} B^T y
        BtB_inv_Bt = np.linalg.pinv(B)  # (n_basis, m)

        coeffs = np.zeros((N, self.n_basis))
        for i in range(N):
            coeffs[i] = BtB_inv_Bt @ X_ref[i]

        self.ref_coeffs = coeffs.mean(axis=0)
        self.ref_std = coeffs.std(axis=0) + self.eps
        return self

    def transform(self, X):
        N, m = X.shape
        if self._basis_matrix is None or self._basis_matrix.shape[0] != m:
            self._build_basis_matrix(m)

        BtB_inv_Bt = np.linalg.pinv(self._basis_matrix)
        out = np.zeros((N, self.n_basis), dtype=np.float64)

        for i in range(N):
            coeffs = BtB_inv_Bt @ X[i]
            out[i] = (coeffs - self.ref_coeffs) / self.ref_std

        return out


class WaveletBasisSpectrum:
    """
    A3: Reduce each row to wavelet coefficients.

    Theory: Haar wavelet decomposition captures both WHERE and at
    what SCALE deviations occur. Unlike Fourier (global frequency),
    wavelets provide time-frequency localisation.

    Uses simplified Haar wavelet (no pywt dependency).
    Output: Multi-scale detail coefficients.
    """

    def __init__(self, max_levels=4, eps=1e-10):
        self.max_levels = max_levels
        self.eps = eps
        self.ref_coeffs = None
        self.ref_std = None
        self._out_dim = None

    def _haar_decompose(self, signal, levels):
        """Simplified Haar wavelet decomposition."""
        coeffs = []
        approx = signal.copy()

        for level in range(levels):
            n = len(approx)
            if n < 2:
                break
            n_even = n - (n % 2)
            # Detail coefficients: differences
            detail = (approx[:n_even:2] - approx[1:n_even:2]) / np.sqrt(2)
            # Approximation: averages
            approx = (approx[:n_even:2] + approx[1:n_even:2]) / np.sqrt(2)
            coeffs.extend(detail.tolist())

        # Add final approximation
        coeffs.extend(approx.tolist())
        return np.array(coeffs)

    def fit(self, X_ref):
        N, m = X_ref.shape
        levels = min(self.max_levels, int(np.log2(max(m, 2))))

        # Probe output dimension
        probe = self._haar_decompose(X_ref[0], levels)
        self._out_dim = len(probe)

        all_coeffs = np.zeros((N, self._out_dim))
        for i in range(N):
            c = self._haar_decompose(X_ref[i], levels)
            all_coeffs[i, :len(c)] = c[:self._out_dim]

        self.ref_coeffs = all_coeffs.mean(axis=0)
        self.ref_std = all_coeffs.std(axis=0) + self.eps
        return self

    def transform(self, X):
        N, m = X.shape
        levels = min(self.max_levels, int(np.log2(max(m, 2))))
        out = np.zeros((N, self._out_dim), dtype=np.float64)

        for i in range(N):
            c = self._haar_decompose(X[i], levels)
            length = min(len(c), self._out_dim)
            raw = np.zeros(self._out_dim)
            raw[:length] = c[:length]
            out[i] = (raw - self.ref_coeffs) / self.ref_std

        return out


class LegendreBasisSpectrum:
    """
    A4: Reduce each row to Legendre polynomial coefficients.

    Theory: Project f(t) onto orthogonal Legendre polynomial basis.
    Low-order coefficients capture trend/shape (mean, slope, curvature),
    higher-order capture fine structure. Anomalies deviate in their
    polynomial "moments".

    Output: n_degree+1 Legendre coefficients.
    """

    def __init__(self, n_degree=6, eps=1e-10):
        self.n_degree = n_degree
        self.eps = eps
        self.ref_coeffs = None
        self.ref_std = None
        self._basis_matrix = None

    def _build_legendre_matrix(self, m):
        """Build Legendre polynomial evaluation matrix."""
        t = np.linspace(-1, 1, m)  # Legendre polynomials on [-1, 1]
        n = self.n_degree + 1
        P = np.zeros((m, n))

        P[:, 0] = 1.0  # P_0 = 1
        if n > 1:
            P[:, 1] = t  # P_1 = t
        for k in range(2, n):
            # Bonnet's recursion: (k+1)P_{k+1} = (2k+1)tP_k - kP_{k-1}
            P[:, k] = ((2 * k - 1) * t * P[:, k - 1] - (k - 1) * P[:, k - 2]) / k

        self._basis_matrix = P
        return P

    def fit(self, X_ref):
        N, m = X_ref.shape
        P = self._build_legendre_matrix(m)
        n = self.n_degree + 1

        # Least-squares projection: c = (P^T P)^{-1} P^T y
        PtP_inv_Pt = np.linalg.pinv(P)  # (n, m)

        coeffs = np.zeros((N, n))
        for i in range(N):
            coeffs[i] = PtP_inv_Pt @ X_ref[i]

        self.ref_coeffs = coeffs.mean(axis=0)
        self.ref_std = coeffs.std(axis=0) + self.eps
        return self

    def transform(self, X):
        N, m = X.shape
        n = self.n_degree + 1

        if self._basis_matrix is None or self._basis_matrix.shape[0] != m:
            self._build_legendre_matrix(m)

        PtP_inv_Pt = np.linalg.pinv(self._basis_matrix)
        out = np.zeros((N, n), dtype=np.float64)

        for i in range(N):
            coeffs = PtP_inv_Pt @ X[i]
            out[i] = (coeffs - self.ref_coeffs) / self.ref_std

        return out


# ═══════════════════════════════════════════════════════════════════
#  APPROACH B: COORDINATE SYSTEM TRANSFORMATIONS (v2 — fixed)
#
#  KEY FIX: Preserve per-feature information instead of collapsing
#  m dimensions into ~5 aggregate statistics.
# ═══════════════════════════════════════════════════════════════════


class PolarSpectrum:
    """
    B1: Hyperspherical coordinate decomposition (FIXED).

    v1 problem: Collapsed all angles into 5 summary stats. In high
    dimensions, angular summaries become noise.

    v2 fix: Output the FULL per-angle z-score vector + radial z-score.
    Each angle deviation is preserved as a separate feature, so the
    downstream centroid/tensor sees WHERE the angular deviation occurs.
    PCA compression applied when m is large to keep dimensionality
    manageable (same approach as ExponentialSpectrum).

    Output: [radial_z, angle_z_1, angle_z_2, ..., angle_z_{m-1}]
            compressed via PCA to max_dim if m > max_dim.
    """

    def __init__(self, max_dim=12, eps=1e-10):
        self.max_dim = max_dim
        self.eps = eps
        self.ref_radius = None
        self.ref_radius_std = None
        self.ref_angles = None
        self.ref_angle_std = None
        self._pca_components = None
        self._pca_mean = None
        self._out_dim = None

    def _to_hyperspherical(self, x):
        """Convert Cartesian to hyperspherical coordinates."""
        m = len(x)
        r = np.linalg.norm(x) + self.eps
        angles = np.zeros(m - 1)
        for k in range(m - 1):
            denom = np.sqrt(np.sum(x[k:] ** 2)) + self.eps
            cos_val = np.clip(x[k] / denom, -1.0, 1.0)
            angles[k] = np.arccos(cos_val)
        if m >= 2:
            angles[-1] = np.arctan2(x[-1], x[-2] + self.eps)
        return r, angles

    def fit(self, X_ref):
        N, m = X_ref.shape
        radii = np.zeros(N)
        all_angles = np.zeros((N, m - 1))

        for i in range(N):
            r, angles = self._to_hyperspherical(X_ref[i])
            radii[i] = r
            all_angles[i] = angles

        self.ref_radius = radii.mean()
        self.ref_radius_std = radii.std() + self.eps
        self.ref_angles = all_angles.mean(axis=0)
        self.ref_angle_std = all_angles.std(axis=0) + self.eps

        # Build full representation for PCA calibration
        full = self._raw_transform(X_ref, radii, all_angles)

        # PCA compress if needed
        if full.shape[1] > self.max_dim:
            self._pca_mean = full.mean(axis=0)
            centered = full - self._pca_mean
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            self._pca_components = Vt[:self.max_dim]
            self._out_dim = self.max_dim
        else:
            self._out_dim = full.shape[1]
        return self

    def _raw_transform(self, X, radii=None, all_angles=None):
        N, m = X.shape
        if radii is None or all_angles is None:
            radii = np.zeros(N)
            all_angles = np.zeros((N, m - 1))
            for i in range(N):
                radii[i], all_angles[i] = self._to_hyperspherical(X[i])

        # Per-angle z-scores (full vector, not aggregated)
        angle_z = (all_angles - self.ref_angles) / self.ref_angle_std
        radial_z = ((radii - self.ref_radius) / self.ref_radius_std).reshape(-1, 1)
        return np.hstack([radial_z, angle_z])

    def transform(self, X):
        full = self._raw_transform(X)
        if self._pca_components is not None:
            return (full - self._pca_mean) @ self._pca_components.T
        return full


class RadarPolygonSpectrum:
    """
    B2: Radar polygon per-vertex deviation (FIXED).

    v1 problem: Collapsed polygon into 6 aggregate stats (area,
    perimeter, etc.), losing per-feature deviation information.

    v2 fix: Output the per-vertex displacement vector from the
    reference polygon. Each feature gets its own radar-coordinate
    deviation: Δr_j = x_j - x_ref_j in polar coordinates on the
    radar chart. This preserves WHICH spoke deviates and by how much.

    Output: m per-spoke deviations (z-scored), compressed via PCA
            if m > max_dim. Plus 2 global shape features (area_z,
            centroid_offset_z) that capture holistic distortion.
    """

    def __init__(self, max_dim=12, eps=1e-10, sort_features=True):
        self.max_dim = max_dim
        self.eps = eps
        self.sort_features = sort_features
        self._sort_idx = None
        self.ref_spokes = None
        self.ref_spoke_std = None
        self.ref_area = None
        self.ref_area_std = None
        self.ref_coffset = None
        self.ref_coffset_std = None
        self._pca_components = None
        self._pca_mean = None
        self._out_dim = None

    def _compute_area_and_offset(self, x, m):
        """Shoelace area and centroid offset for a radar polygon."""
        angles = 2 * np.pi * np.arange(m) / m
        px = x * np.cos(angles)
        py = x * np.sin(angles)
        area = 0.5 * np.abs(
            np.sum(px[:-1] * py[1:] - px[1:] * py[:-1])
            + px[-1] * py[0] - px[0] * py[-1]
        )
        cx, cy = np.mean(px), np.mean(py)
        coffset = np.sqrt(cx ** 2 + cy ** 2)
        return area, coffset

    def fit(self, X_ref):
        N, m = X_ref.shape
        if self.sort_features:
            ref_mags = np.abs(X_ref).mean(axis=0)
            self._sort_idx = np.argsort(ref_mags)

        X_sorted = X_ref[:, self._sort_idx] if self._sort_idx is not None else X_ref

        # Per-spoke reference stats
        self.ref_spokes = X_sorted.mean(axis=0)
        self.ref_spoke_std = X_sorted.std(axis=0) + self.eps

        # Global shape stats
        areas = np.zeros(N)
        coffsets = np.zeros(N)
        for i in range(N):
            areas[i], coffsets[i] = self._compute_area_and_offset(X_sorted[i], m)
        self.ref_area = areas.mean()
        self.ref_area_std = areas.std() + self.eps
        self.ref_coffset = coffsets.mean()
        self.ref_coffset_std = coffsets.std() + self.eps

        # Build full representation for PCA
        full = self._raw_transform(X_ref)
        total_dim = full.shape[1]

        if total_dim > self.max_dim:
            self._pca_mean = full.mean(axis=0)
            centered = full - self._pca_mean
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            self._pca_components = Vt[:self.max_dim]
            self._out_dim = self.max_dim
        else:
            self._out_dim = total_dim
        return self

    def _raw_transform(self, X):
        N, m = X.shape
        X_sorted = X[:, self._sort_idx] if self._sort_idx is not None else X

        # Per-spoke z-scored deviations
        spoke_z = (X_sorted - self.ref_spokes) / self.ref_spoke_std

        # Global shape features
        areas = np.zeros(N)
        coffsets = np.zeros(N)
        for i in range(N):
            areas[i], coffsets[i] = self._compute_area_and_offset(X_sorted[i], m)
        area_z = ((areas - self.ref_area) / self.ref_area_std).reshape(-1, 1)
        coffset_z = ((coffsets - self.ref_coffset) / self.ref_coffset_std).reshape(-1, 1)

        return np.hstack([spoke_z, area_z, coffset_z])

    def transform(self, X):
        full = self._raw_transform(X)
        if self._pca_components is not None:
            return (full - self._pca_mean) @ self._pca_components.T
        return full


class PhaseCurveSpectrum:
    """
    B3: Phase trajectory with absolute position (FIXED).

    v1 problem: Only extracted translation-invariant trajectory shape
    features (curvature, roughness). Anomalies that shift ALL features
    by a constant produce identical trajectories → AUC 0.29.

    v2 fix: Output per-segment deviation vectors in phase space,
    preserving BOTH absolute position AND shape. For each consecutive
    pair (x_j, x_{j+1}), compute the z-scored displacement from the
    reference pair. This makes the representation sensitive to shifts.

    Output: 2*(m-1) features (Δx, Δy per phase point), compressed
            via PCA if high-dimensional.
    """

    def __init__(self, max_dim=12, eps=1e-10):
        self.max_dim = max_dim
        self.eps = eps
        self.ref_phase_points = None
        self.ref_phase_std = None
        self._pca_components = None
        self._pca_mean = None
        self._out_dim = None

    def _to_phase_coords(self, X):
        """Convert rows to phase-space coordinates: (x_j, x_{j+1})."""
        N, m = X.shape
        # Each row gives m-1 2D points
        px = X[:, :-1]  # (N, m-1)
        py = X[:, 1:]   # (N, m-1)
        # Interleave: [px_0, py_0, px_1, py_1, ...]
        return np.column_stack([px, py])  # (N, 2*(m-1))

    def fit(self, X_ref):
        N, m = X_ref.shape
        phase = self._to_phase_coords(X_ref)

        self.ref_phase_points = phase.mean(axis=0)
        self.ref_phase_std = phase.std(axis=0) + self.eps

        # Build full z-scored representation
        full = (phase - self.ref_phase_points) / self.ref_phase_std

        if full.shape[1] > self.max_dim:
            self._pca_mean = full.mean(axis=0)
            centered = full - self._pca_mean
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            self._pca_components = Vt[:self.max_dim]
            self._out_dim = self.max_dim
        else:
            self._out_dim = full.shape[1]
        return self

    def transform(self, X):
        phase = self._to_phase_coords(X)
        full = (phase - self.ref_phase_points) / self.ref_phase_std
        if self._pca_components is not None:
            return (full - self._pca_mean) @ self._pca_components.T
        return full


class GramEigenSpectrum:
    """
    B4: Cross-feature interaction matrix (FIXED).

    v1 problem: Used outer product G = g*g^T which is always rank 1,
    giving constant eigenvalue ratios [1,0,0,...] for every row.

    v2 fix: Compute a CROSS-CORRELATION interaction matrix between
    feature groups. Partition features into g groups, compute the
    pairwise correlation/product BETWEEN groups (not self-outer-product).
    The upper triangle of this interaction matrix captures how feature
    groups co-vary, which differs between normal and anomalous rows.

    Also: use the raw interaction values (not just eigenvalues) as
    features to preserve more information.

    Output: g*(g+1)/2 interaction features (upper triangle including
            diagonal), z-scored and PCA-compressed if needed.
    """

    def __init__(self, n_groups=None, max_dim=12, eps=1e-10):
        self.n_groups = n_groups
        self.max_dim = max_dim
        self.eps = eps
        self._actual_groups = None
        self._group_slices = None
        self._out_dim = None
        self.ref_stats = None
        self.ref_stats_std = None
        self._pca_components = None
        self._pca_mean = None

    def _compute_interaction(self, x):
        """Compute cross-group interaction features for one row."""
        ng = self._actual_groups
        # Group statistics: mean and std per group
        group_means = np.zeros(ng)
        group_stds = np.zeros(ng)
        for g in range(ng):
            s = self._group_slices[g]
            group_vals = x[s]
            group_means[g] = np.mean(group_vals)
            group_stds[g] = np.std(group_vals) + self.eps

        # Cross-group interaction matrix (upper triangle)
        # I[j,k] = (mean_j * mean_k) / (std_j * std_k) — normalised product
        features = []
        for j in range(ng):
            for k in range(j, ng):
                if j == k:
                    # Diagonal: group energy (mean^2 / std)
                    features.append(group_means[j] ** 2 / group_stds[j])
                else:
                    # Off-diagonal: normalised cross-product
                    features.append(
                        group_means[j] * group_means[k] /
                        (group_stds[j] * group_stds[k])
                    )
        return np.array(features)

    def fit(self, X_ref):
        N, m = X_ref.shape
        if self.n_groups is None:
            self._actual_groups = min(m, 8)
        else:
            self._actual_groups = min(self.n_groups, m)

        ng = self._actual_groups
        gs = max(1, m // ng)

        # Build group slices
        self._group_slices = []
        for g in range(ng):
            start = g * gs
            end = min(start + gs, m) if g < ng - 1 else m
            self._group_slices.append(slice(start, end))

        # Compute interaction features for all reference rows
        probe = self._compute_interaction(X_ref[0])
        n_feats = len(probe)

        all_feats = np.zeros((N, n_feats))
        for i in range(N):
            all_feats[i] = self._compute_interaction(X_ref[i])

        self.ref_stats = all_feats.mean(axis=0)
        self.ref_stats_std = all_feats.std(axis=0) + self.eps

        # Z-score and PCA if needed
        full = (all_feats - self.ref_stats) / self.ref_stats_std

        if full.shape[1] > self.max_dim:
            self._pca_mean = full.mean(axis=0)
            centered = full - self._pca_mean
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            self._pca_components = Vt[:self.max_dim]
            self._out_dim = self.max_dim
        else:
            self._out_dim = full.shape[1]
        return self

    def transform(self, X):
        N, m = X.shape
        n_feats = len(self.ref_stats)
        all_feats = np.zeros((N, n_feats))
        for i in range(N):
            all_feats[i] = self._compute_interaction(X[i])

        full = (all_feats - self.ref_stats) / self.ref_stats_std
        if self._pca_components is not None:
            return (full - self._pca_mean) @ self._pca_components.T
        return full
