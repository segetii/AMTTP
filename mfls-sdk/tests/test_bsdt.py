"""Unit tests for BSDT operators."""
import numpy as np
import pytest

from mfls.core.bsdt import BSDTOperator, BSDTOperators


# ---- helpers ---------------------------------------------------------------

def _make_panel(T=40, N=5, d=3, rng=42):
    """Return a (T, N, d) synthetic panel."""
    rs = np.random.RandomState(rng)
    X = rs.randn(T, N, d)
    # inject a shock in the last 5 quarters
    X[-5:] += 3.0
    return X


# ---- BSDTOperator ----------------------------------------------------------

class TestBSDTOperator:
    def test_fit_and_score(self):
        """BSDTOperator.fit expects (T, N, d); score_series expects (T, N, d)."""
        rs = np.random.RandomState(0)
        # 3D panel: 30 quarters, 4 institutions, 3 features
        X_normal = rs.randn(30, 4, 3)
        op = BSDTOperator()
        op.fit(X_normal)

        X_test = rs.randn(10, 4, 3)
        scores = op.score_series(X_test)
        assert scores.shape == (10,)
        assert np.all(np.isfinite(scores))

    def test_deviation_increases_for_outliers(self):
        rs = np.random.RandomState(1)
        # fit on (T, N, d) = (50, 3, 2)
        X_normal = rs.randn(50, 3, 2)
        op = BSDTOperator()
        op.fit(X_normal)

        # deviation expects (N, d) = (3, 2)
        x_inlier = rs.randn(3, 2) * 0.5
        x_outlier = np.full((3, 2), 10.0)
        assert op.deviation(x_outlier).sum() > op.deviation(x_inlier).sum()

    def test_energy_non_negative(self):
        rs = np.random.RandomState(2)
        X = rs.randn(40, 3, 4)  # (T, N, d)
        op = BSDTOperator()
        op.fit(X[:30])
        for t in range(30, 40):
            assert op.energy_score(X[t]) >= 0.0

    def test_gradient_shape(self):
        rs = np.random.RandomState(3)
        N, d = 5, 3
        X = rs.randn(50, N, d)
        op = BSDTOperator()
        op.fit(X[:30])
        # gradient expects (N, d) → (N, d)
        g = op.gradient(X[35])
        assert g.shape == (N, d)


# ---- BSDTOperators (4-channel) ---------------------------------------------

class TestBSDTOperators:
    def test_fit_and_channels(self):
        X = _make_panel()
        ops = BSDTOperators()
        ops.fit(X[:20])

        ch = ops.compute_channels(X)
        assert ch.delta_C.shape == (40,)
        assert ch.delta_G.shape == (40,)
        assert ch.delta_A.shape == (40,)
        assert ch.delta_T.shape == (40,)
        assert ch.channels.shape == (40, 4)
        assert ch.per_agent.shape == (40, 5, 4)

    def test_audit(self):
        X = _make_panel()
        names = [f"bank_{i}" for i in range(5)]
        ops = BSDTOperators()
        ops.fit(X[:20])

        # audit needs: X_curr, X_prev, history, institution_names
        t = -1
        X_curr = X[t]           # (N, d)
        X_prev = X[t - 1]       # (N, d)
        history = [X[s] for s in range(max(0, len(X) + t - 20), len(X) + t)]
        audit = ops.audit(X_curr, X_prev, history, institution_names=names)
        assert len(audit.institution_names) == 5
        assert audit.total_score.shape == (5,)
        assert len(audit.dominant_channel) == 5
        assert all(ch in ("delta_C", "delta_G", "delta_A", "delta_T")
                   for ch in audit.dominant_channel)

    def test_shocked_quarters_higher(self):
        """Channels should be higher in the shocked tail."""
        X = _make_panel()
        ops = BSDTOperators()
        ops.fit(X[:20])
        ch = ops.compute_channels(X)
        # mean signal in last 5 vs first 20
        mean_tail = ch.channels[-5:].mean()
        mean_head = ch.channels[:20].mean()
        assert mean_tail > mean_head, "Shocked quarters should have higher channel values"


# ---- run -------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
