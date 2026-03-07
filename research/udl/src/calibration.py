"""
calibration.py — Score calibration utilities for UDL pipelines
===============================================================
Wraps sklearn calibration methods (isotonic, Platt/sigmoid, beta)
into a uniform fit/transform interface compatible with UDLPipeline.
"""
import numpy as np


class ScoreCalibrator:
    """
    Calibrate raw anomaly scores to the [0, 1] probability range.

    Parameters
    ----------
    method : str
        One of 'isotonic', 'platt', 'beta', or 'minmax'.
        'minmax' is a simple fallback requiring no labels.
    """

    def __init__(self, method="isotonic"):
        self.method = method
        self._calibrator = None
        self._min = None
        self._max = None
        self._fitted = False  # checked by UDLPipeline.predict_proba()

    def fit(self, scores: np.ndarray, y: np.ndarray = None):
        """
        Fit the calibrator.

        Parameters
        ----------
        scores : 1-D array of raw anomaly scores
        y      : binary labels (1 = anomaly). Required for supervised
                 methods ('isotonic', 'platt'). Ignored for 'minmax'.
        """
        scores = np.asarray(scores, dtype=np.float64).ravel()

        if self.method == "minmax":
            self._min = scores.min()
            self._max = scores.max()

        elif self.method == "isotonic":
            # Monotone non-parametric mapping: sort scores, fit isotonic
            # regression against empirical anomaly rate at each quantile.
            from sklearn.isotonic import IsotonicRegression
            if y is None:
                self._min = scores.min()
                self._max = scores.max()
                self.method = "minmax"
            else:
                ir = IsotonicRegression(out_of_bounds="clip", increasing=True)
                ir.fit(scores, y.astype(float))
                self._calibrator = ir

        elif self.method in ("platt", "sigmoid"):
            # Platt scaling: fit a logistic regression on raw scores → labels.
            from sklearn.linear_model import LogisticRegression
            if y is None:
                self._min = scores.min()
                self._max = scores.max()
                self.method = "minmax"
            else:
                lr = LogisticRegression(C=1e4, max_iter=1000, solver="lbfgs")
                lr.fit(scores.reshape(-1, 1), y)
                self._calibrator = lr

        elif self.method == "beta":
            # Beta calibration: Platt scaling on log-odds of the score.
            # Works well for right-skewed anomaly score distributions.
            from sklearn.linear_model import LogisticRegression
            if y is None:
                self._min = scores.min()
                self._max = scores.max()
                self.method = "minmax"
            else:
                lr = LogisticRegression(C=1e4, max_iter=1000, solver="lbfgs")
                lr.fit(np.log1p(np.abs(scores)).reshape(-1, 1), y)
                self._calibrator = lr

        else:
            # Unknown method — fall back to minmax
            self._min = scores.min()
            self._max = scores.max()

        self._fitted = True
        return self

    def transform(self, scores: np.ndarray) -> np.ndarray:
        """Map raw scores to calibrated probabilities in [0, 1]."""
        scores = np.asarray(scores, dtype=np.float64).ravel()

        if self.method == "minmax" or (self._calibrator is None and self._fitted):
            r = self._max - self._min
            if r < 1e-12:
                return np.full_like(scores, 0.5)
            return np.clip((scores - self._min) / r, 0.0, 1.0)

        if self.method == "isotonic":
            # IsotonicRegression.predict() outputs values in [0,1]
            return np.clip(self._calibrator.predict(scores), 0.0, 1.0)

        if self.method in ("platt", "sigmoid", "beta"):
            inp = np.log1p(np.abs(scores)).reshape(-1, 1) \
                  if self.method == "beta" else scores.reshape(-1, 1)
            return self._calibrator.predict_proba(inp)[:, 1]

        # Fallback
        r = float(scores.max() - scores.min())
        if r < 1e-12:
            return np.full_like(scores, 0.5)
        return np.clip((scores - scores.min()) / r, 0.0, 1.0)

    def fit_transform(self, scores: np.ndarray,
                      y: np.ndarray = None) -> np.ndarray:
        return self.fit(scores, y).transform(scores)
