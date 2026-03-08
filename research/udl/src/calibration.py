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


class FARTargetCalibrator:
    """
    False-Alarm-Rate targeted score calibration.

    Given a target FAR (fraction of normal points scoring above the
    decision threshold at a given recall level), learns an optimal
    score transformation that minimises FAR while preserving recall.

    Two-stage approach
    ------------------
    1. **Isotonic calibration** — monotone non-parametric mapping from
       raw scores to P(anomaly | score).  Preserves ranking, fixes
       score distribution skew.

    2. **Quantile thresholding** — finds the decision threshold τ such
       that FAR = target at the specified recall level, then rescales
       scores so that τ maps to 0.5 (natural decision boundary).

    For unsupervised deployment (no labels), falls back to percentile-
    based normalisation using reference statistics from normal data.

    Parameters
    ----------
    target_far : float
        Desired false alarm rate (e.g. 0.05 for FCA compliance).
    target_recall : float
        Recall level at which to optimise FAR (default 0.95 = 95%).
    method : str
        Calibration method: 'isotonic' (supervised), 'quantile'
        (semi-supervised), or 'combined' (both stages).
    """

    def __init__(self, target_far: float = 0.05,
                 target_recall: float = 0.95,
                 method: str = 'combined'):
        self.target_far = target_far
        self.target_recall = target_recall
        self.method = method
        self._isotonic = None
        self._threshold = None
        self._ref_quantiles = None
        self._fitted = False

    def fit(self, scores: np.ndarray, y: np.ndarray) -> 'FARTargetCalibrator':
        """
        Fit the calibrator on raw scores and binary labels.

        Parameters
        ----------
        scores : 1-D array of raw anomaly scores
        y      : binary labels (1 = anomaly, 0 = normal)
        """
        scores = np.asarray(scores, dtype=np.float64).ravel()
        y = np.asarray(y, dtype=np.int32).ravel()
        n = len(scores)

        if n < 10 or y.sum() < 2:
            # Not enough data — fall back to minmax
            self._ref_quantiles = (float(scores.min()), float(scores.max()))
            self._fitted = True
            return self

        normal_scores = scores[y == 0]
        anomaly_scores = scores[y == 1]

        # Stage 1: Isotonic calibration (score → P(anomaly))
        if self.method in ('isotonic', 'combined'):
            from sklearn.isotonic import IsotonicRegression
            self._isotonic = IsotonicRegression(
                out_of_bounds='clip', increasing=True
            )
            self._isotonic.fit(scores, y.astype(float))

        # Stage 2: Find optimal threshold for target FAR at target recall
        # Sort anomaly scores to find the recall threshold
        anom_sorted = np.sort(anomaly_scores)
        # Threshold for target recall: we need catch recall fraction of anomalies
        # So the threshold is the (1-recall)-th quantile of anomaly scores
        recall_idx = max(0, int((1 - self.target_recall) * len(anom_sorted)))
        recall_threshold = anom_sorted[recall_idx]

        # At this threshold, what is the FAR?
        current_far = float(np.mean(normal_scores >= recall_threshold))

        # Find the threshold that gives exactly target_far on normals
        # while trying to preserve recall
        normal_sorted = np.sort(normal_scores)
        target_idx = max(0, int((1 - self.target_far) * len(normal_sorted)) - 1)
        target_idx = min(target_idx, len(normal_sorted) - 1)
        far_threshold = float(normal_sorted[target_idx])

        # Use the more conservative (higher) threshold if FAR-optimal
        # threshold still catches enough anomalies
        recall_at_far = float(np.mean(anomaly_scores >= far_threshold))
        if recall_at_far >= self.target_recall * 0.8:
            # FAR threshold achieves acceptable recall — use it
            self._threshold = far_threshold
        else:
            # FAR threshold too aggressive — compromise
            # Interpolate between recall threshold and FAR threshold
            self._threshold = 0.5 * (recall_threshold + far_threshold)

        # Store reference quantiles for rescaling
        self._ref_quantiles = (
            float(np.percentile(normal_scores, 25)),
            float(np.percentile(normal_scores, 75)),
            float(np.percentile(normal_scores, 95)),
            float(np.median(anomaly_scores)),
        )

        self._fitted = True
        return self

    def transform(self, scores: np.ndarray) -> np.ndarray:
        """
        Transform raw scores to FAR-calibrated scores.

        Calibrated scores have the property that the decision boundary
        at 0.5 approximately achieves the target FAR at the target
        recall level.
        """
        scores = np.asarray(scores, dtype=np.float64).ravel()

        if not self._fitted:
            return scores

        # Stage 1: apply isotonic calibration if available
        if self._isotonic is not None:
            cal_scores = np.clip(self._isotonic.predict(scores), 0.0, 1.0)
        else:
            # Minmax fallback
            s_min, s_max = self._ref_quantiles[0], self._ref_quantiles[1]
            rng = s_max - s_min
            if rng < 1e-15:
                return np.full_like(scores, 0.5)
            cal_scores = np.clip((scores - s_min) / rng, 0.0, 1.0)

        # Stage 2: rescale so the FAR-optimal threshold maps to 0.5
        if self._threshold is not None and self._isotonic is not None:
            # Calibrate the threshold too
            cal_thresh = float(np.clip(
                self._isotonic.predict(np.array([self._threshold]))[0],
                0.0, 1.0
            ))
            if cal_thresh > 1e-6 and cal_thresh < 1 - 1e-6:
                # Piecewise linear rescale: [0, cal_thresh] → [0, 0.5]
                #                           [cal_thresh, 1] → [0.5, 1]
                below = cal_scores <= cal_thresh
                result = np.empty_like(cal_scores)
                result[below] = 0.5 * cal_scores[below] / cal_thresh
                result[~below] = 0.5 + 0.5 * (
                    (cal_scores[~below] - cal_thresh) / (1 - cal_thresh)
                )
                return np.clip(result, 0.0, 1.0)

        return cal_scores

    def fit_transform(self, scores: np.ndarray,
                      y: np.ndarray) -> np.ndarray:
        """Fit and transform in one step."""
        return self.fit(scores, y).transform(scores)

    @property
    def threshold(self) -> float:
        """The raw-score threshold for the target FAR."""
        return self._threshold if self._threshold is not None else 0.5
