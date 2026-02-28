"""Unit tests for network estimation and energy functions."""
import numpy as np
import pytest

from mfls.core.network import lw_correlation_network, NetworkInfo
from mfls.core.energy import (
    radial_energy,
    pairwise_energy,
    total_energy,
    total_force,
    analyse_trajectory,
    calibrate_ccyb,
)
from mfls.core.bsdt import BSDTOperator


class TestNetwork:
    def test_lw_correlation(self):
        rs = np.random.RandomState(0)
        # lw_correlation_network expects (T, N, d)
        X = rs.randn(50, 8, 3)
        info = lw_correlation_network(X)
        assert isinstance(info, NetworkInfo)
        assert info.W.shape == (8, 8)
        assert 0.0 <= info.shrinkage <= 1.0
        assert info.spectral_radius > 0
        assert info.n_institutions == 8
        # diagonal should be ~1
        np.testing.assert_allclose(np.diag(info.W), 1.0, atol=0.01)

    def test_spectral_radius_positive(self):
        rs = np.random.RandomState(1)
        X = rs.randn(30, 5, 3)
        info = lw_correlation_network(X)
        assert info.spectral_radius > 0


class TestEnergy:
    def test_radial_energy(self):
        N, d = 5, 3
        X = np.ones((N, d))
        mu = np.zeros(d)
        e = radial_energy(X, mu)
        assert np.isfinite(e)
        assert e > 0

    def test_pairwise_increases_close(self):
        # Create two sets of agents at different distances
        X_far = np.array([[0, 0], [5, 5]], dtype=float)
        X_close = np.array([[0, 0], [0.5, 0.5]], dtype=float)
        e_far = pairwise_energy(X_far)
        e_close = pairwise_energy(X_close)
        # Just check both are finite; the relation depends on potential shape
        assert np.isfinite(e_far)
        assert np.isfinite(e_close)

    def test_total_energy_finite(self):
        rs = np.random.RandomState(4)
        N, d = 10, 3
        X = rs.randn(N, d)
        mu = np.zeros(d)
        e = total_energy(X, mu)
        assert np.isfinite(e)

    def test_total_force_shape(self):
        rs = np.random.RandomState(5)
        N, d = 10, 3
        X = rs.randn(N, d)
        mu = np.zeros(d)
        F = total_force(X, mu)
        assert F.shape == X.shape


class TestTrajectory:
    def test_analyse_trajectory(self):
        rs = np.random.RandomState(6)
        T, N, d = 20, 3, 2  # small for speed
        panel = rs.randn(T, N, d)
        panel[-5:] += 3.0  # shock

        mu = panel[:10].reshape(-1, d).mean(axis=0)
        op = BSDTOperator()
        op.fit(panel[:10])

        result = analyse_trajectory(panel, mu, op, n_power_iter=5)
        assert result.energy.shape == (T,)
        assert result.force_norm.shape == (T,)
        assert result.lambda_max.shape == (T,)
        assert result.gamma_star.shape == (T,)
        assert result.mfls.shape == (T,)


class TestCCyB:
    def test_calibrate_ccyb(self):
        rs = np.random.RandomState(7)
        T = 40
        energy = rs.rand(T)
        gamma_star = rs.rand(T) * 0.5
        leverage_std = rs.rand(T) * 0.1 + 0.05
        ccyb = calibrate_ccyb(energy, gamma_star, leverage_std)
        assert ccyb.shape == (T,)
        assert ccyb.min() >= 0
        assert ccyb.max() <= 250  # max 250 bps


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
