"""Tests for BSDT scoring variants:
  - QuadSurf  (post-hoc degree-2 polynomial surface)
  - SignedLR  (supervised logistic regression, discovers herding)
  - ExpoGate  (post-hoc QuadSurf + tanh + sigmoid gating)
  - score_variants() comparison helper on ReducedTensorDescriptor
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'udl'))

import numpy as np
import pytest
from system_mode import BSDTChannels, ReducedTensorDescriptor


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def labelled_data():
    """Generate normal + anomalous data with labels."""
    rng = np.random.RandomState(42)
    n_ref, n_anom = 80, 20
    d = 5
    X_normal = rng.randn(n_ref, d) * 0.5
    X_anom = rng.randn(n_anom, d) * 0.5 + 3.0
    X = np.vstack([X_normal, X_anom])
    y = np.array([0] * n_ref + [1] * n_anom)
    return X, y, X_normal


@pytest.fixture
def fitted_bsdt(labelled_data):
    """BSDTChannels fitted on normal data."""
    X, y, X_ref = labelled_data
    bsdt = BSDTChannels(k=5)
    bsdt.fit(X_ref)
    return bsdt


# ── QuadSurf tests ───────────────────────────────────────────────

class TestQuadSurf:
    def test_fit_returns_self(self, fitted_bsdt, labelled_data):
        _, _, X_ref = labelled_data
        result = fitted_bsdt.fit_quadsurf(X_ref)
        assert result is fitted_bsdt

    def test_score_shape(self, fitted_bsdt, labelled_data):
        X, _, X_ref = labelled_data
        fitted_bsdt.fit_quadsurf(X_ref)
        scores = fitted_bsdt.score_quadsurf(X)
        assert scores.shape == (len(X),)

    def test_scores_nonnegative(self, fitted_bsdt, labelled_data):
        X, _, X_ref = labelled_data
        fitted_bsdt.fit_quadsurf(X_ref)
        scores = fitted_bsdt.score_quadsurf(X)
        assert np.all(scores >= 0), f"Min score: {scores.min()}"

    def test_anomalies_score_higher(self, fitted_bsdt, labelled_data):
        X, y, X_ref = labelled_data
        fitted_bsdt.fit_quadsurf(X_ref)
        scores = fitted_bsdt.score_quadsurf(X)
        mean_normal = scores[y == 0].mean()
        mean_anom = scores[y == 1].mean()
        assert mean_anom > mean_normal, (
            f"Anomaly mean {mean_anom:.4f} <= normal mean {mean_normal:.4f}")

    def test_poly_features_shape(self):
        rng = np.random.RandomState(0)
        C = rng.randn(10, 4)
        Phi = BSDTChannels._poly_features(C)
        # 1 bias + 4 linear + 10 quadratic = 15
        assert Phi.shape == (10, 15)

    def test_no_labels_needed(self, fitted_bsdt, labelled_data):
        """QuadSurf is post-hoc: only needs reference data, not labels."""
        X, _, X_ref = labelled_data
        fitted_bsdt.fit_quadsurf(X_ref)  # no y argument
        scores = fitted_bsdt.score_quadsurf(X)
        assert scores.shape == (len(X),)
        assert np.all(np.isfinite(scores))


# ── SignedLR tests ────────────────────────────────────────────────

class TestSignedLR:
    def test_fit_returns_self(self, fitted_bsdt, labelled_data):
        X, y, _ = labelled_data
        result = fitted_bsdt.fit_signed_lr(X, y)
        assert result is fitted_bsdt

    def test_score_shape(self, fitted_bsdt, labelled_data):
        X, y, _ = labelled_data
        fitted_bsdt.fit_signed_lr(X, y)
        scores = fitted_bsdt.score_signed_lr(X)
        assert scores.shape == (len(X),)

    def test_scores_in_01(self, fitted_bsdt, labelled_data):
        """Logistic output must be in [0, 1]."""
        X, y, _ = labelled_data
        fitted_bsdt.fit_signed_lr(X, y)
        scores = fitted_bsdt.score_signed_lr(X)
        assert np.all(scores >= 0) and np.all(scores <= 1), (
            f"Range: [{scores.min():.4f}, {scores.max():.4f}]")

    def test_anomalies_score_higher(self, fitted_bsdt, labelled_data):
        X, y, _ = labelled_data
        fitted_bsdt.fit_signed_lr(X, y)
        scores = fitted_bsdt.score_signed_lr(X)
        mean_normal = scores[y == 0].mean()
        mean_anom = scores[y == 1].mean()
        assert mean_anom > mean_normal

    def test_weights_exist(self, fitted_bsdt, labelled_data):
        X, y, _ = labelled_data
        fitted_bsdt.fit_signed_lr(X, y)
        assert hasattr(fitted_bsdt, '_lr_beta')
        # 1 bias + 4 channels = 5 weights
        assert fitted_bsdt._lr_beta.shape == (5,)

    def test_class_imbalance_handled(self, fitted_bsdt, labelled_data):
        """Should work even with imbalanced data."""
        X, y, _ = labelled_data
        # Make very imbalanced: only 2 anomalies
        y_imb = np.zeros(len(y))
        y_imb[-2:] = 1
        fitted_bsdt.fit_signed_lr(X, y_imb)
        scores = fitted_bsdt.score_signed_lr(X)
        assert scores.shape == (len(X),)


# ── ExpoGate tests ───────────────────────────────────────────────

class TestExpoGate:
    def test_fit_returns_self(self, fitted_bsdt, labelled_data):
        _, _, X_ref = labelled_data
        result = fitted_bsdt.fit_expogate(X_ref)
        assert result is fitted_bsdt

    def test_score_shape(self, fitted_bsdt, labelled_data):
        X, _, X_ref = labelled_data
        fitted_bsdt.fit_expogate(X_ref)
        scores = fitted_bsdt.score_expogate(X)
        assert scores.shape == (len(X),)

    def test_scores_in_01(self, fitted_bsdt, labelled_data):
        """Sigmoid output must be in (0, 1)."""
        X, _, X_ref = labelled_data
        fitted_bsdt.fit_expogate(X_ref)
        scores = fitted_bsdt.score_expogate(X)
        assert np.all(scores > 0) and np.all(scores < 1), (
            f"Range: [{scores.min():.4f}, {scores.max():.4f}]")

    def test_anomalies_score_higher(self, fitted_bsdt, labelled_data):
        X, y, X_ref = labelled_data
        fitted_bsdt.fit_expogate(X_ref)
        scores = fitted_bsdt.score_expogate(X)
        mean_normal = scores[y == 0].mean()
        mean_anom = scores[y == 1].mean()
        assert mean_anom > mean_normal

    def test_gate_scale_effect(self, fitted_bsdt, labelled_data):
        """Higher gate_scale -> sharper sigmoid -> more extreme scores."""
        _, _, X_ref = labelled_data
        fitted_bsdt.fit_expogate(X_ref, gate_scale=1.0)
        s_gentle = fitted_bsdt.score_expogate(X_ref).copy()
        fitted_bsdt.fit_expogate(X_ref, gate_scale=10.0)
        s_sharp = fitted_bsdt.score_expogate(X_ref)
        # Sharper gate should have more extreme values (further from 0.5)
        dev_gentle = np.abs(s_gentle - 0.5).mean()
        dev_sharp = np.abs(s_sharp - 0.5).mean()
        assert dev_sharp >= dev_gentle - 0.01

    def test_no_labels_needed(self, fitted_bsdt, labelled_data):
        """ExpoGate is post-hoc: only needs reference data, not labels."""
        X, _, X_ref = labelled_data
        fitted_bsdt.fit_expogate(X_ref)  # no y argument
        scores = fitted_bsdt.score_expogate(X)
        assert scores.shape == (len(X),)
        assert np.all(np.isfinite(scores))


# ── score_variants on ReducedTensorDescriptor ─────────────────────

class TestScoreVariants:
    def test_returns_all_variants(self, labelled_data):
        X, y, X_ref = labelled_data
        desc = ReducedTensorDescriptor(k_neighbors=5)
        desc.fit(X_ref)
        results = desc.score_variants(X, y, X_ref=X_ref)
        expected = {'baseline', 'full_bsdt', 'quadsurf',
                    'signed_lr', 'expo_gate'}
        assert set(results.keys()) == expected

    def test_each_has_auroc(self, labelled_data):
        X, y, X_ref = labelled_data
        desc = ReducedTensorDescriptor(k_neighbors=5)
        desc.fit(X_ref)
        results = desc.score_variants(X, y, X_ref=X_ref)
        for name, r in results.items():
            assert 'auroc' in r, f"Missing auroc in {name}"
            assert 0.0 <= r['auroc'] <= 1.0, (
                f"{name} auroc out of range: {r['auroc']}")

    def test_variants_beat_baseline(self, labelled_data):
        """Post-hoc and supervised variants should match or beat baseline."""
        X, y, X_ref = labelled_data
        desc = ReducedTensorDescriptor(k_neighbors=5)
        desc.fit(X_ref)
        results = desc.score_variants(X, y, X_ref=X_ref)
        base = results['baseline']['auroc']
        for name in ['quadsurf', 'signed_lr', 'expo_gate']:
            var = results[name]['auroc']
            # Allow small margin for edge cases
            assert var >= base - 0.05, (
                f"{name} ({var:.4f}) too far below baseline ({base:.4f})")

    def test_signed_lr_has_weights(self, labelled_data):
        X, y, X_ref = labelled_data
        desc = ReducedTensorDescriptor(k_neighbors=5)
        desc.fit(X_ref)
        results = desc.score_variants(X, y, X_ref=X_ref)
        assert 'weights' in results['signed_lr']
        assert len(results['signed_lr']['weights']) == 5  # bias + 4 channels


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
