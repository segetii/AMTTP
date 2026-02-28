"""
Coefficient Coordinate System for Anomaly Detection
=====================================================
Maps each data row x ∈ ℝⁿ to a point θ ∈ ℝᵏ in coefficient space,
where each axis has structural meaning:

    θ = (β₀, β₁, β₂, ε, â₁, â₂, ...)

    β₀  = intercept   — the level (WHERE the function sits)
    β₁  = gradient     — the slope (HOW FAST it changes)
    β₂  = curvature    — acceleration (HOW the change bends)
    ε   = residual     — unexplained energy (goodness-of-fit)
    â_k = spectral     — DCT frequency modes

This is NOT dimensionality reduction — it is a change of basis.
The new axes are structural invariants rather than raw measurements.

Key principle: anomalies deviate in STRUCTURE, not just magnitude.
A normal row and an anomalous row may have similar means but wildly
different gradients or curvatures.

For unordered tabular features, we construct MULTIPLE VIEWS:
    View 1: sort features ascending  → monotone profile shape
    View 2: order by variance rank   → stability profile
    View 3: order by magnitude rank  → scale profile

Each view extracts its own coefficient set. The multi-view coordinate
vector captures structural information that no single ordering reveals.

    Θ_multi = (θ_sorted ‖ θ_variance ‖ θ_magnitude)

Mathematical formulation:
    Given row x = (x₁, ..., xₙ), define ordering π: {1..n} → {1..n}
    Construct profile: f_π(t_i) = x_{π(i)}, t_i = i/(n-1)
    Fit polynomial: f_π(t) ≈ Σ βⱼ tʲ
    Compute DCT: â_k = DCT_k(f_π)
    Residual: ε = ‖f_π - Σ βⱼ tʲ‖² / n

This mapping is Lipschitz continuous — small perturbations in x produce
bounded changes in θ — preserving local geometry for the GravityEngine.
"""

import numpy as np
from scipy.fft import dct


class CoefficientCoordinates:
    """
    Maps raw features to a structural coefficient coordinate system.

    Parameters
    ----------
    views : list of str
        Which orderings to use. Options: 'sorted', 'variance', 'magnitude', 'raw'.
        Default ['sorted', 'variance'] — two complementary views.
    poly_degree : int
        Polynomial degree for profile fitting (default 2 = intercept + slope + curvature).
    n_spectral : int
        Number of DCT spectral coefficients per view (default 2).
    include_residual : bool
        Include polynomial residual energy ε (default True).
    include_gradient_stats : bool
        Include max|gradient| and gradient range (default True).
        Captures local "spikes" that polynomials smooth over.
    """

    def __init__(self, views=None, poly_degree=2, n_spectral=2,
                 include_residual=True, include_gradient_stats=True):
        self.views = views or ['sorted', 'variance']
        self.poly_degree = poly_degree
        self.n_spectral = n_spectral
        self.include_residual = include_residual
        self.include_gradient_stats = include_gradient_stats

        # Fitted state
        self._mean = None
        self._std = None
        self._variance_order = None
        self._n_features = None
        self._V_lstsq = None   # precomputed Vandermonde pseudoinverse

    @property
    def n_coordinates(self):
        """Number of output coordinates per data point."""
        per_view = self.poly_degree + 1  # polynomial coefficients
        if self.include_residual:
            per_view += 1
        per_view += self.n_spectral  # DCT modes
        if self.include_gradient_stats:
            per_view += 2  # max|grad|, grad_range
        return per_view * len(self.views)

    def fit(self, X):
        """Learn standardization and ordering from training data."""
        n, d = X.shape
        self._n_features = d

        # Standardize to unit variance
        self._mean = X.mean(axis=0)
        self._std = X.std(axis=0) + 1e-10

        # Variance ordering (ascending: most stable → most volatile)
        self._variance_order = np.argsort(X.var(axis=0))

        # Precompute Vandermonde pseudoinverse for polynomial fitting
        t = np.linspace(0, 1, d)
        deg = min(self.poly_degree, d - 1)
        V = np.vander(t, N=deg + 1, increasing=True)  # (d, deg+1)
        # Pseudoinverse: V_pinv @ y = coefficients
        self._V_lstsq = np.linalg.pinv(V)  # (deg+1, d)
        self._t = t
        self._deg = deg

        return self

    def transform(self, X):
        """
        Extract coefficient coordinates for each row.

        Returns
        -------
        Theta : ndarray (N, k)
            Coordinate matrix in coefficient space.
        names : list of str
            Axis labels for each coordinate.
        """
        n, d = X.shape
        X_s = (X - self._mean) / self._std

        all_coords = []
        all_names = []

        for view in self.views:
            X_v = self._apply_view(X_s, view)
            coords, names = self._extract_coordinates(X_v, prefix=view)
            all_coords.append(coords)
            all_names.extend(names)

        Theta = np.hstack(all_coords)
        return Theta, all_names

    def fit_transform(self, X):
        self.fit(X)
        return self.transform(X)

    def _apply_view(self, X_s, view):
        """Reorder columns according to the view."""
        if view == 'sorted':
            return np.sort(X_s, axis=1)
        elif view == 'variance':
            return X_s[:, self._variance_order]
        elif view == 'magnitude':
            # Per-row ordering by absolute magnitude
            idx = np.argsort(np.abs(X_s), axis=1)
            return np.take_along_axis(X_s, idx, axis=1)
        elif view == 'raw':
            return X_s
        else:
            raise ValueError(f"Unknown view: {view}")

    def _extract_coordinates(self, X_v, prefix=''):
        """Extract structural coordinates from an ordered profile."""
        n, d = X_v.shape
        coords = []
        names = []

        # ── Polynomial coefficients: β₀, β₁, β₂, ... ──
        # coeffs[i] = V_pinv @ X_v[i]
        poly_coeffs = X_v @ self._V_lstsq.T  # (n, deg+1)
        coords.append(poly_coeffs)
        labels = ['level', 'gradient', 'curvature', 'jerk', 'snap', 'crackle']
        for j in range(self._deg + 1):
            name = labels[j] if j < len(labels) else f'beta{j}'
            names.append(f'{prefix}_{name}')

        # ── Residual energy ε ──
        if self.include_residual:
            V = np.vander(self._t, N=self._deg + 1, increasing=True)
            fitted = poly_coeffs @ V.T  # (n, d)
            residual = np.sum((X_v - fitted) ** 2, axis=1, keepdims=True) / d
            coords.append(residual)
            names.append(f'{prefix}_residual')

        # ── DCT spectral modes ──
        k = min(self.n_spectral, d)
        if k > 0:
            dct_coeffs = dct(X_v, type=2, axis=1, norm='ortho')[:, 1:k+1]  # skip DC (≈β₀)
            coords.append(dct_coeffs)
            for j in range(k):
                names.append(f'{prefix}_freq{j+1}')

        # ── Gradient statistics (captures local spikes) ──
        if self.include_gradient_stats and d >= 2:
            dx = np.diff(X_v, axis=1)
            max_abs_grad = np.max(np.abs(dx), axis=1, keepdims=True)
            grad_range = (np.max(dx, axis=1, keepdims=True) -
                         np.min(dx, axis=1, keepdims=True))
            coords.append(max_abs_grad)
            coords.append(grad_range)
            names.append(f'{prefix}_max_grad')
            names.append(f'{prefix}_grad_range')

        return np.hstack(coords), names

    def describe(self):
        """Summary of the coordinate system."""
        return {
            'views': self.views,
            'coordinates_per_view': self.n_coordinates // len(self.views),
            'total_coordinates': self.n_coordinates,
            'poly_degree': self.poly_degree,
            'n_spectral': self.n_spectral,
            'input_features': self._n_features,
            'compression_ratio': f'{self._n_features} -> {self.n_coordinates}',
        }


# ─── Convenience: all-in-one pipeline wrapper ───

def functional_gravity_pipeline(X, gravity_params, views=None,
                                 poly_degree=2, n_spectral=2):
    """
    Full pipeline: Raw → Coefficient Coordinates → GravityEngine.

    Returns GravityEngine instance fitted on the coefficient space.
    """
    from udl.gravity import GravityEngine

    cc = CoefficientCoordinates(
        views=views, poly_degree=poly_degree, n_spectral=n_spectral,
    )
    Theta, names = cc.fit_transform(X)

    eng = GravityEngine(
        alpha=gravity_params['alpha'],
        gamma=gravity_params['gamma'],
        sigma=gravity_params['sigma'],
        lambda_rep=gravity_params['lambda_rep'],
        eta=gravity_params['eta'],
        iterations=gravity_params['iterations'],
        normalize=True, track_energy=False, convergence_tol=1e-7,
        k_neighbors=gravity_params.get('k_neighbors', 0),
        beta_dev=gravity_params.get('beta_dev', 0.0),
    )
    eng.fit_transform(Theta, time_budget=300)

    return eng, cc, Theta, names
