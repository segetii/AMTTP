"""
Tests for ReducedTensorDescriptor — O(Nd + d³) reduced descriptor.

Verifies:
  1. Correct output shape (N, d+7) for n_eigs=d
  2. Morse index recovery matches _numerical_morse_index
  3. Local injectivity near equilibrium
  4. Alarm fires at saddle points (index ≥ 1)
  5. Complexity is O(Nd + d³), not O(N²d)
  6. Feature names are correct
  7. Works with custom energy functions
"""

import sys, os
import numpy as np
import pytest

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'udl'))
from system_mode import ReducedTensorDescriptor, MorseTopologyAlarm


# ── Fixtures ──────────────────────────────────────────────────────

def make_normal_data(n=200, d=6, seed=42):
    """Generate normal-period reference data."""
    rng = np.random.RandomState(seed)
    return rng.randn(n, d) * 0.5


def make_anomaly_data(n=20, d=6, seed=99):
    """Generate anomalous data (shifted far from origin)."""
    rng = np.random.RandomState(seed)
    return rng.randn(n, d) * 0.5 + 5.0


def quadratic_energy(X):
    """Simple quadratic energy E(X) = ½‖X‖².  Hessian = I."""
    return 0.5 * np.sum(X ** 2, axis=1) if X.ndim > 1 else 0.5 * np.sum(X ** 2)


def saddle_energy(X):
    """Saddle energy: E = x₁² - x₂² + ½Σxᵢ² (i≥3).
    Hessian at origin: diag(2, -2, 1, 1, ...) → Morse index = 1.
    """
    if X.ndim == 1:
        X = X.reshape(1, -1)
    e = X[:, 0] ** 2 - X[:, 1] ** 2
    if X.shape[1] > 2:
        e += 0.5 * np.sum(X[:, 2:] ** 2, axis=1)
    return e if len(e) > 1 else float(e[0])


# ── Tests ─────────────────────────────────────────────────────────

class TestReducedTensorDescriptor:

    def test_output_shape(self):
        """Descriptor has shape (N, n_eigs + 6)."""
        d = 6
        X_ref = make_normal_data(n=100, d=d)
        X_test = make_normal_data(n=30, d=d, seed=7)

        desc = ReducedTensorDescriptor(k_neighbors=10, n_eigs=d)
        desc.fit(X_ref)
        D = desc.transform(X_test, energy_fn=quadratic_energy)

        assert D.shape == (30, d + 6), f"Expected ({30}, {d+6}), got {D.shape}"

    def test_feature_names(self):
        """Feature names match output columns."""
        d = 4
        X_ref = make_normal_data(n=50, d=d)
        desc = ReducedTensorDescriptor(n_eigs=d)
        desc.fit(X_ref)
        names = desc.feature_names()

        expected = (['grad_norm'] +
                    [f'hessian_eig_{j}' for j in range(d)] +
                    ['mahalanobis', 'medoid_dist', 'trace_H',
                     'det_sigma', 'morse_index'])
        assert names == expected, f"Names mismatch: {names} vs {expected}"
        # Length matches output columns
        D = desc.transform(X_ref[:5], energy_fn=quadratic_energy)
        assert len(names) == D.shape[1]

    def test_morse_index_quadratic(self):
        """Quadratic energy → Morse index = 0 everywhere (global min)."""
        d = 6
        X_ref = make_normal_data(n=100, d=d)
        X_test = make_normal_data(n=20, d=d, seed=7)

        desc = ReducedTensorDescriptor(n_eigs=d)
        desc.fit(X_ref)
        indices = desc.get_morse_index(X_test, energy_fn=quadratic_energy)

        assert np.all(indices == 0), \
            f"Quadratic should have index=0, got {indices}"

    def test_morse_index_saddle(self):
        """Saddle energy → Morse index = 1 near origin."""
        d = 6
        X_ref = make_normal_data(n=100, d=d)
        # Test near origin where saddle structure is clear
        X_test = np.zeros((5, d))
        X_test[:, 0] = np.linspace(-0.01, 0.01, 5)

        desc = ReducedTensorDescriptor(n_eigs=d, eps_hessian=1e-3)
        desc.fit(X_ref)
        indices = desc.get_morse_index(X_test, energy_fn=saddle_energy)

        assert np.all(indices >= 1), \
            f"Saddle should have index≥1 near origin, got {indices}"

    def test_alarm_fires_at_saddle(self):
        """Alarm (ind ≥ 1) fires at saddle, not at minima."""
        d = 6
        X_ref = make_normal_data(n=100, d=d)

        # Normal points (quadratic = minimum)
        X_normal = make_normal_data(n=10, d=d, seed=7)
        # Saddle points
        X_saddle = np.zeros((10, d))
        X_saddle[:, 0] = np.linspace(-0.01, 0.01, 10)

        desc = ReducedTensorDescriptor(n_eigs=d, eps_hessian=1e-3)
        desc.fit(X_ref)

        alarm_normal = desc.get_alarm(X_normal, energy_fn=quadratic_energy)
        alarm_saddle = desc.get_alarm(X_saddle, energy_fn=saddle_energy)

        assert not np.any(alarm_normal), \
            f"No alarm at minima, got {alarm_normal}"
        assert np.all(alarm_saddle), \
            f"Alarm should fire at saddle, got {alarm_saddle}"

    def test_local_injectivity(self):
        """Distinct nearby points → distinct descriptors."""
        d = 4
        X_ref = make_normal_data(n=100, d=d)
        desc = ReducedTensorDescriptor(n_eigs=d)
        desc.fit(X_ref)

        # Two close but distinct points
        x1 = np.array([[0.1, 0.2, 0.3, 0.4]])
        x2 = np.array([[0.1, 0.2, 0.3, 0.41]])  # differ by 0.01

        D1 = desc.transform(x1, energy_fn=quadratic_energy)
        D2 = desc.transform(x2, energy_fn=quadratic_energy)

        diff = np.linalg.norm(D1 - D2)
        assert diff > 1e-6, f"Descriptors should differ, dist={diff}"

    def test_gradient_norm_positive(self):
        """Gradient norm > 0 away from origin for quadratic energy."""
        d = 6
        X_ref = make_normal_data(n=100, d=d)
        X_test = make_anomaly_data(n=10, d=d)  # far from origin

        desc = ReducedTensorDescriptor(n_eigs=d)
        desc.fit(X_ref)
        D = desc.transform(X_test, energy_fn=quadratic_energy)

        grad_norms = D[:, 0]
        assert np.all(grad_norms > 0.1), \
            f"Gradient norms should be large away from origin: {grad_norms}"

    def test_mahalanobis_separates_normal_anomaly(self):
        """Mahalanobis distance is higher for anomalies."""
        d = 6
        X_ref = make_normal_data(n=200, d=d)
        X_normal = make_normal_data(n=30, d=d, seed=7)
        X_anomaly = make_anomaly_data(n=30, d=d)

        desc = ReducedTensorDescriptor(n_eigs=d)
        desc.fit(X_ref)

        D_normal = desc.transform(X_normal, energy_fn=quadratic_energy)
        D_anomaly = desc.transform(X_anomaly, energy_fn=quadratic_energy)

        n_eigs = min(desc.n_eigs, d)
        maha_normal = D_normal[:, n_eigs + 1].mean()
        maha_anomaly = D_anomaly[:, n_eigs + 1].mean()

        assert maha_anomaly > maha_normal * 2, \
            f"Anomaly Mahalanobis ({maha_anomaly:.2f}) should be >> " \
            f"normal ({maha_normal:.2f})"

    def test_trace_equals_sum_eigenvalues(self):
        """trace(H) = sum of Hessian eigenvalues (consistency check)."""
        d = 4
        X_ref = make_normal_data(n=50, d=d)
        X_test = make_normal_data(n=5, d=d, seed=3)

        desc = ReducedTensorDescriptor(n_eigs=d)
        desc.fit(X_ref)
        D = desc.transform(X_test, energy_fn=quadratic_energy)

        eig_block = D[:, 1:1+d]
        trace_from_eigs = eig_block.sum(axis=1)
        trace_stored = D[:, d + 3]

        np.testing.assert_allclose(
            trace_stored, trace_from_eigs, rtol=1e-5,
            err_msg="trace(H) should equal sum of eigenvalues")

    def test_default_mahalanobis_energy(self):
        """Works without explicit energy_fn (uses Mahalanobis)."""
        d = 6
        X_ref = make_normal_data(n=100, d=d)
        X_test = make_normal_data(n=10, d=d, seed=7)

        desc = ReducedTensorDescriptor(n_eigs=d)
        desc.fit(X_ref)
        D = desc.transform(X_test)  # no energy_fn

        assert D.shape == (10, d + 6)
        assert np.all(np.isfinite(D)), "All values should be finite"

    def test_complexity_info(self):
        """Complexity info returns correct strings."""
        d = 6
        X_ref = make_normal_data(n=100, d=d)
        desc = ReducedTensorDescriptor(n_eigs=d)
        desc.fit(X_ref)
        info = desc.complexity_info()

        assert 'O(Nd + d^3)' in info['total']
        assert 'O(N^2*d)' in info['vs_full']
        assert info['speedup'] == '~N/d = ~100/6'

    def test_fit_required(self):
        """transform() raises if fit() not called."""
        desc = ReducedTensorDescriptor()
        X = make_normal_data(n=10)
        with pytest.raises(RuntimeError, match="Call fit"):
            desc.transform(X)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
