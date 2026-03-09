"""
Tests for BSDTChannels — Blind-Spot Detection Tensor implementation.

Verifies:
  1. fit/score API works correctly
  2. Four channels (δ_C, δ_G, δ_A, δ_T) have correct shapes and ranges
  3. E_BS ≥ 0 and MFLS ≥ 0
  4. Anomalies score higher than normals
  5. Integration in FusedSystemScorer with BSDT enabled
  6. Gradient (MFLS) is finite and non-negative
  7. Score monotonicity: farther points → higher score
"""

import sys, os
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'udl'))
from system_mode import (
    BSDTChannels, FusedSystemScorer, MolecularEngine,
    GravityModeEngine, HybridGravityEngine
)


# ── Fixtures ──────────────────────────────────────────────────────

def make_normal(n=200, d=6, seed=42):
    rng = np.random.RandomState(seed)
    return rng.randn(n, d) * 0.5


def make_anomaly(n=20, d=6, seed=99):
    rng = np.random.RandomState(seed)
    return rng.randn(n, d) * 0.5 + 5.0


# ── BSDTChannels unit tests ──────────────────────────────────────

class TestBSDTChannels:

    def test_fit_score_api(self):
        """BSDTChannels.fit() → score() returns correct shape."""
        X_ref = make_normal(200, 6)
        X_test = np.vstack([make_normal(50, 6, seed=7),
                            make_anomaly(10, 6)])
        bsdt = BSDTChannels(k=10)
        bsdt.fit(X_ref)
        scores = bsdt.score(X_test)

        assert scores.shape == (60,)
        assert np.all(np.isfinite(scores))

    def test_channel_shapes(self):
        """channels() returns dict with 4 arrays of correct length."""
        X_ref = make_normal(100, 4)
        X_test = make_normal(30, 4, seed=7)

        bsdt = BSDTChannels(k=8)
        bsdt.fit(X_ref)
        ch = bsdt.channels(X_test)

        assert set(ch.keys()) == {'delta_C', 'delta_G', 'delta_A', 'delta_T'}
        for key in ch:
            assert ch[key].shape == (30,), f"{key} shape mismatch"
            assert np.all(np.isfinite(ch[key])), f"{key} has non-finite values"

    def test_channel_ranges(self):
        """δ_C, δ_A, δ_T ∈ [0, 1]; δ_G ∈ [0, 1]."""
        X_ref = make_normal(200, 6)
        X_test = np.vstack([make_normal(100, 6, seed=3),
                            make_anomaly(20, 6)])

        bsdt = BSDTChannels(k=10)
        bsdt.fit(X_ref)
        ch = bsdt.channels(X_test)

        assert np.all(ch['delta_C'] >= 0) and np.all(ch['delta_C'] <= 1), \
            "δ_C should be in [0, 1]"
        assert np.all(ch['delta_G'] >= 0) and np.all(ch['delta_G'] <= 1), \
            "δ_G should be in [0, 1]"
        # δ_A is sigmoid → (0, 1)
        assert np.all(ch['delta_A'] >= 0) and np.all(ch['delta_A'] <= 1), \
            "δ_A should be in [0, 1]"
        # δ_T is sigmoid → (0, 1)
        assert np.all(ch['delta_T'] >= 0) and np.all(ch['delta_T'] <= 1), \
            "δ_T should be in [0, 1]"

    def test_energy_nonneg(self):
        """E_BS = Σ δ_i² ≥ 0."""
        X_ref = make_normal(100, 6)
        X_test = make_normal(50, 6, seed=3)

        bsdt = BSDTChannels(k=10)
        bsdt.fit(X_ref)
        e = bsdt.energy(X_test)

        assert np.all(e >= 0), "E_BS must be non-negative"
        assert np.all(np.isfinite(e)), "E_BS must be finite"

    def test_mfls_nonneg(self):
        """MFLS = ‖∇E_BS‖ ≥ 0 and finite."""
        X_ref = make_normal(100, 6)
        X_test = make_normal(50, 6, seed=3)

        bsdt = BSDTChannels(k=10)
        bsdt.fit(X_ref)
        m = bsdt.mfls(X_test)

        assert np.all(m >= 0), "MFLS must be non-negative"
        assert np.all(np.isfinite(m)), "MFLS must be finite"

    def test_anomalies_score_higher(self):
        """Anomalies (shifted +5σ) should score higher than normals."""
        X_ref = make_normal(200, 6)
        X_norm = make_normal(100, 6, seed=7)
        X_anom = make_anomaly(30, 6)

        bsdt = BSDTChannels(k=10)
        bsdt.fit(X_ref)

        s_norm = bsdt.score(X_norm)
        s_anom = bsdt.score(X_anom)

        assert np.mean(s_anom) > np.mean(s_norm), \
            f"Anomaly mean ({np.mean(s_anom):.4f}) should exceed " \
            f"normal mean ({np.mean(s_norm):.4f})"

    def test_score_monotonicity(self):
        """Points farther from centroid should score higher on average."""
        X_ref = make_normal(200, 6)
        rng = np.random.RandomState(11)

        # Create points at increasing distances
        near = rng.randn(50, 6) * 0.3
        mid = rng.randn(50, 6) * 0.3 + 2.0
        far = rng.randn(50, 6) * 0.3 + 6.0

        bsdt = BSDTChannels(k=10)
        bsdt.fit(X_ref)

        s_near = np.mean(bsdt.score(near))
        s_mid = np.mean(bsdt.score(mid))
        s_far = np.mean(bsdt.score(far))

        assert s_far > s_mid > s_near, \
            f"Monotonicity violated: near={s_near:.4f}, mid={s_mid:.4f}, far={s_far:.4f}"

    def test_small_dataset(self):
        """Works with very small reference set (n=10, d=3)."""
        rng = np.random.RandomState(42)
        X_ref = rng.randn(10, 3)
        X_test = rng.randn(5, 3)

        bsdt = BSDTChannels(k=5)
        bsdt.fit(X_ref)
        s = bsdt.score(X_test)

        assert s.shape == (5,)
        assert np.all(np.isfinite(s))

    def test_1d_input(self):
        """Works with 1D features."""
        rng = np.random.RandomState(42)
        X_ref = rng.randn(50, 1)
        X_test = rng.randn(20, 1)

        bsdt = BSDTChannels(k=5)
        bsdt.fit(X_ref)
        s = bsdt.score(X_test)

        assert s.shape == (20,)
        assert np.all(np.isfinite(s))


# ── Integration with FusedSystemScorer ────────────────────────────

class TestFusedScorerBSDT:

    def test_fused_includes_bsdt(self):
        """FusedSystemScorer with BSDT enabled produces valid scores."""
        X_ref = make_normal(100, 6)
        X_test = np.vstack([make_normal(50, 6, seed=7),
                            make_anomaly(10, 6)])

        scorer = FusedSystemScorer(k=10, use_bsdt=True)
        scorer.fit(X_ref, X_sim=X_test)
        scores = scorer.score(X_test)

        assert scores.shape == (60,)
        assert np.all(np.isfinite(scores))

    def test_fused_bsdt_vs_no_bsdt(self):
        """Scores differ when BSDT is enabled vs disabled."""
        X_ref = make_normal(100, 6)
        X_test = np.vstack([make_normal(50, 6, seed=7),
                            make_anomaly(10, 6)])

        scorer_with = FusedSystemScorer(k=10, use_bsdt=True)
        scorer_with.fit(X_ref, X_sim=X_test)
        s_with = scorer_with.score(X_test)

        scorer_without = FusedSystemScorer(k=10, use_bsdt=False)
        scorer_without.fit(X_ref, X_sim=X_test)
        s_without = scorer_without.score(X_test)

        assert not np.allclose(s_with, s_without), \
            "BSDT should change the fused scores"

    def test_fused_bsdt_attribute(self):
        """FusedSystemScorer has bsdt attribute when enabled."""
        scorer = FusedSystemScorer(k=10, use_bsdt=True)
        assert scorer.bsdt is not None
        assert isinstance(scorer.bsdt, BSDTChannels)

        scorer_off = FusedSystemScorer(k=10, use_bsdt=False)
        assert scorer_off.bsdt is None


# ── Engine integration tests ──────────────────────────────────────

class TestEngineBSDT:

    def test_molecular_uses_bsdt(self):
        """MolecularEngine.fit_score includes BSDT via fused scorer."""
        rng = np.random.RandomState(42)
        X = np.vstack([rng.randn(80, 4) * 0.5,
                       rng.randn(10, 4) * 0.5 + 4.0])
        y = np.array([0] * 80 + [1] * 10)

        engine = MolecularEngine(iterations=10, k_neighbors=8,
                                 max_samples=200, use_fused=True)
        scores = engine.fit_score(X, y)

        assert scores.shape == (90,)
        assert np.all(np.isfinite(scores))
        # BSDT should be fitted inside the fused scorer
        assert engine.fused_scorer.bsdt is not None
        assert engine.fused_scorer.bsdt._fitted

    def test_gravity_uses_bsdt(self):
        """GravityModeEngine.fit_score includes BSDT via fused scorer."""
        rng = np.random.RandomState(42)
        X = np.vstack([rng.randn(80, 4) * 0.5,
                       rng.randn(10, 4) * 0.5 + 4.0])
        y = np.array([0] * 80 + [1] * 10)

        engine = GravityModeEngine(iterations=10, k_neighbors=8,
                                   max_samples=200, use_fused=True)
        scores = engine.fit_score(X, y)

        assert scores.shape == (90,)
        assert np.all(np.isfinite(scores))
        assert engine.fused_scorer.bsdt is not None
        assert engine.fused_scorer.bsdt._fitted


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
