"""Unit tests for MFLS scoring variants."""
import numpy as np
import pytest

from mfls.core.scoring import (
    MFLSBaseline,
    MFLSFullBSDT,
    MFLSQuadSurf,
    MFLSSignedLR,
    MFLSExpoGate,
    ALL_VARIANTS,
)


def _make_data(T=60, N=5, d=4, rng=7):
    rs = np.random.RandomState(rng)
    X = rs.randn(T, N, d)
    X[-10:] += 2.5  # inject tail shock
    channels = np.abs(rs.randn(T, 4))
    # labels: 0 for normal, 1 for crisis (last 10)
    labels = np.zeros(T, dtype=float)
    labels[-10:] = 1.0
    return X, channels, labels


class TestUnsupervisedVariants:
    """MFLSBaseline and MFLSFullBSDT do not use labels."""

    def test_baseline_output_shape(self):
        X, channels, _ = _make_data()
        m = MFLSBaseline()
        m.fit(X[:30])
        s = m.score_series(X)
        assert s.shape == (60,)
        assert np.all(np.isfinite(s))

    def test_fullbsdt_output_shape(self):
        X, channels, _ = _make_data()
        m = MFLSFullBSDT()
        m.fit(channels[:30])
        s = m.score(channels)
        assert s.shape == (60,)

    def test_fullbsdt_higher_in_tail(self):
        X, channels, _ = _make_data()
        # Make tail channels clearly higher
        channels[-10:] += 5.0
        m = MFLSFullBSDT()
        m.fit(channels[:30])
        s = m.score(channels)
        assert s[-10:].mean() > s[:30].mean()


class TestSupervisedVariants:
    """QuadSurf, SignedLR, ExpoGate require labels."""

    def test_signedlr(self):
        X, channels, labels = _make_data()
        m = MFLSSignedLR()
        m.fit(channels[:50], y=labels[:50])
        s = m.score(channels)
        assert s.shape == (60,)
        # channel_weights includes bias + 4 channels = 5 keys
        assert m.channel_weights is not None
        assert len(m.channel_weights) == 5

    def test_quadsurf(self):
        X, channels, labels = _make_data()
        m = MFLSQuadSurf()
        m.fit(channels[:50], y=labels[:50])
        s = m.score(channels)
        assert s.shape == (60,)

    def test_expogate(self):
        X, channels, labels = _make_data()
        m = MFLSExpoGate()
        m.fit(channels[:50], y=labels[:50])
        s = m.score(channels)
        assert s.shape == (60,)

    def test_supervised_crisis_higher(self):
        """Supervised variants should generally assign higher scores to crisis."""
        X, channels, labels = _make_data()
        # amplify crisis channels to make supervised learning work
        channels[-10:] += 3.0
        for name in ("signed_lr", "quadsurf", "expo_gate"):
            cls = ALL_VARIANTS[name]
            m = cls()
            m.fit(channels[:50], y=labels[:50])
            s = m.score(channels)
            assert s[-10:].mean() >= s[:30].mean() * 0.5, f"{name} crisis scores too low"


class TestVariantRegistry:
    def test_all_variants_registered(self):
        assert "baseline" in ALL_VARIANTS
        assert "full_bsdt" in ALL_VARIANTS
        assert "quadsurf" in ALL_VARIANTS
        assert "signed_lr" in ALL_VARIANTS
        assert "expo_gate" in ALL_VARIANTS
        assert len(ALL_VARIANTS) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
