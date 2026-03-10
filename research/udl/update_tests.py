"""Update test_bsdt_variants.py for transductive Fisher SignedLR."""

FILE = r'c:\amttp\research\udl\tests\test_bsdt_variants.py'

with open(FILE, 'r') as f:
    src = f.read()

# TestSignedFisher: fit_signed_lr takes full data X, not X_ref
src = src.replace(
    '''class TestSignedFisher:
    def test_fit_returns_self(self, fitted_bsdt, labelled_data):
        _, _, X_ref = labelled_data
        result = fitted_bsdt.fit_signed_lr(X_ref)
        assert result is fitted_bsdt

    def test_score_shape(self, fitted_bsdt, labelled_data):
        X, _, X_ref = labelled_data
        fitted_bsdt.fit_signed_lr(X_ref)
        scores = fitted_bsdt.score_signed_lr(X)
        assert scores.shape == (len(X),)

    def test_scores_in_01(self, fitted_bsdt, labelled_data):
        """Sigmoid output must be in [0, 1]."""
        X, _, X_ref = labelled_data
        fitted_bsdt.fit_signed_lr(X_ref)
        scores = fitted_bsdt.score_signed_lr(X)
        assert np.all(scores >= 0) and np.all(scores <= 1), (
            f"Range: [{scores.min():.4f}, {scores.max():.4f}]")

    def test_anomalies_score_higher(self, fitted_bsdt, labelled_data):
        X, y, X_ref = labelled_data
        fitted_bsdt.fit_signed_lr(X_ref)
        scores = fitted_bsdt.score_signed_lr(X)
        mean_normal = scores[y == 0].mean()
        mean_anom = scores[y == 1].mean()
        assert mean_anom > mean_normal

    def test_weights_exist(self, fitted_bsdt, labelled_data):
        _, _, X_ref = labelled_data
        fitted_bsdt.fit_signed_lr(X_ref)
        assert hasattr(fitted_bsdt, '_lr_beta')
        # 1 bias + 4 channels = 5 weights
        assert fitted_bsdt._lr_beta.shape == (5,)

    def test_no_labels_needed(self, fitted_bsdt, labelled_data):
        """SignedFisher is closed-form: no labels required."""
        X, _, X_ref = labelled_data
        fitted_bsdt.fit_signed_lr(X_ref)
        scores = fitted_bsdt.score_signed_lr(X)
        assert scores.shape == (len(X),)
        assert np.all(np.isfinite(scores))

    def test_signed_weights_reflect_direction(self, fitted_bsdt, labelled_data):
        """Weights encode direction: positive if channel increases with
        overall magnitude, negative if it decreases (herding)."""
        _, _, X_ref = labelled_data
        fitted_bsdt.fit_signed_lr(X_ref)
        beta = fitted_bsdt._lr_beta[1:]
        assert np.any(np.abs(beta) > 1e-12)''',

    '''class TestSignedFisher:
    def test_fit_returns_self(self, fitted_bsdt, labelled_data):
        X, _, _ = labelled_data
        result = fitted_bsdt.fit_signed_lr(X)
        assert result is fitted_bsdt

    def test_score_shape(self, fitted_bsdt, labelled_data):
        X, _, _ = labelled_data
        fitted_bsdt.fit_signed_lr(X)
        scores = fitted_bsdt.score_signed_lr(X)
        assert scores.shape == (len(X),)

    def test_scores_in_01(self, fitted_bsdt, labelled_data):
        """Sigmoid output must be in [0, 1]."""
        X, _, _ = labelled_data
        fitted_bsdt.fit_signed_lr(X)
        scores = fitted_bsdt.score_signed_lr(X)
        assert np.all(scores >= 0) and np.all(scores <= 1), (
            f"Range: [{scores.min():.4f}, {scores.max():.4f}]")

    def test_anomalies_score_higher(self, fitted_bsdt, labelled_data):
        X, y, _ = labelled_data
        fitted_bsdt.fit_signed_lr(X)
        scores = fitted_bsdt.score_signed_lr(X)
        mean_normal = scores[y == 0].mean()
        mean_anom = scores[y == 1].mean()
        assert mean_anom > mean_normal

    def test_weights_exist(self, fitted_bsdt, labelled_data):
        X, _, _ = labelled_data
        fitted_bsdt.fit_signed_lr(X)
        assert hasattr(fitted_bsdt, '_lr_beta')
        # 1 bias + 4 channels = 5 weights
        assert fitted_bsdt._lr_beta.shape == (5,)

    def test_no_labels_needed(self, fitted_bsdt, labelled_data):
        """SignedFisher is closed-form: no labels required.
        Uses full data X for Fisher VR weights (transductive, label-free)."""
        X, _, _ = labelled_data
        fitted_bsdt.fit_signed_lr(X)  # NO y argument!
        scores = fitted_bsdt.score_signed_lr(X)
        assert scores.shape == (len(X),)
        assert np.all(np.isfinite(scores))

    def test_signed_weights_reflect_direction(self, fitted_bsdt, labelled_data):
        """Weights encode direction: positive if channel increases with
        overall magnitude, negative if it decreases (herding)."""
        X, _, _ = labelled_data
        fitted_bsdt.fit_signed_lr(X)
        beta = fitted_bsdt._lr_beta[1:]
        assert np.any(np.abs(beta) > 1e-12)'''
)

# Also fix the zero_leakage test -- SignedFisher uses full data X,
# so changing labels should not change scores
assert 'test_zero_leakage' in src
assert 'LABEL LEAKAGE DETECTED' in src

with open(FILE, 'w') as f:
    f.write(src)

print("Tests updated: SignedFisher now uses full data X")
