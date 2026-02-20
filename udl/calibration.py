"""
Score Calibration — Convert Raw Anomaly Scores to Probabilities
================================================================
Maps arbitrary anomaly scores to well-calibrated probabilities so
that `P(anomaly | score = s) ≈ calibrated_score(s)`.

Three calibration strategies:
  1. Isotonic Regression  — non-parametric, most reliable
  2. Platt Scaling        — sigmoid fit, lightweight & smooth
  3. Beta Calibration     — maps scores through a Beta CDF (bounded)

Usage:
    cal = ScoreCalibrator(method='isotonic')
    cal.fit(train_scores, y_train)       # y ∈ {0, 1}
    probs = cal.transform(test_scores)   # ∈ [0, 1]

The calibrator also provides:
  - optimal_threshold() — best-F1 threshold on calibrated probs
  - reliability_curve() — for plotting calibration quality
  - expected_calibration_error() — ECE metric
"""

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve, brier_score_loss


class ScoreCalibrator:
    """
    Converts raw anomaly scores to calibrated probabilities P(anomaly).

    Parameters
    ----------
    method : str
        'isotonic'  — non-parametric isotonic regression (default)
        'platt'     — Platt sigmoid scaling (logistic regression on scores)
        'beta'      — Beta calibration (parametric, bounded)
    n_bins : int
        Number of bins for reliability diagram and ECE (default 10).
    """

    def __init__(self, method='isotonic', n_bins=10):
        if method not in ('isotonic', 'platt', 'beta'):
            raise ValueError(f"Unknown calibration method: {method}")
        self.method = method
        self.n_bins = n_bins
        self._calibrator = None
        self._threshold = None         # optimal-F1 threshold on calibrated probs
        self._score_range = (0, 1)     # observed min/max of training scores
        self._fitted = False

    def fit(self, scores, y):
        """
        Fit calibration mapping from raw scores to probabilities.

        Parameters
        ----------
        scores : ndarray (N,)
            Raw anomaly scores (higher = more anomalous).
        y : ndarray (N,)
            Binary labels (0=normal, 1=anomaly).
        """
        scores = np.asarray(scores, dtype=np.float64).ravel()
        y = np.asarray(y, dtype=np.int32).ravel()
        assert len(scores) == len(y), "scores and y must have same length"
        assert set(np.unique(y)).issubset({0, 1}), "y must be binary {0, 1}"

        self._score_range = (float(scores.min()), float(scores.max()))

        if self.method == 'isotonic':
            self._fit_isotonic(scores, y)
        elif self.method == 'platt':
            self._fit_platt(scores, y)
        elif self.method == 'beta':
            self._fit_beta(scores, y)

        # Compute optimal threshold on calibrated probabilities
        cal_probs = self._raw_transform(scores)
        self._threshold = self._find_best_f1_threshold(cal_probs, y)
        self._fitted = True
        return self

    def transform(self, scores):
        """
        Convert raw scores to calibrated probabilities.

        Parameters
        ----------
        scores : ndarray (N,)
            Raw anomaly scores.

        Returns
        -------
        probs : ndarray (N,) in [0, 1]
        """
        self._check_fitted()
        return self._raw_transform(scores)

    def predict(self, scores, threshold=None):
        """
        Binary prediction at the given threshold (default: optimal-F1).

        Returns
        -------
        labels : ndarray (N,) of {0, 1}
        """
        self._check_fitted()
        probs = self.transform(scores)
        t = threshold if threshold is not None else self._threshold
        return (probs >= t).astype(int)

    def optimal_threshold(self):
        """Return the optimal F1 threshold on calibrated probabilities."""
        self._check_fitted()
        return self._threshold

    # ─────────────────────────────────────────────
    #  Calibration quality metrics
    # ─────────────────────────────────────────────

    def expected_calibration_error(self, scores, y):
        """
        Expected Calibration Error (ECE).

        Lower is better. 0 = perfectly calibrated.
        """
        probs = self.transform(scores)
        y = np.asarray(y).ravel()
        bin_edges = np.linspace(0, 1, self.n_bins + 1)
        ece = 0.0
        for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
            mask = (probs >= lo) & (probs < hi)
            if mask.sum() == 0:
                continue
            avg_pred = probs[mask].mean()
            avg_true = y[mask].mean()
            ece += mask.sum() * np.abs(avg_pred - avg_true)
        return ece / len(y)

    def brier_score(self, scores, y):
        """Brier score (mean squared error of probability estimates)."""
        probs = self.transform(scores)
        return brier_score_loss(y, probs)

    def reliability_curve(self, scores, y):
        """
        Compute reliability (calibration) curve data.

        Returns
        -------
        bin_centers : ndarray (n_bins,)
        fraction_positives : ndarray (n_bins,)
        mean_predicted : ndarray (n_bins,)
        bin_counts : ndarray (n_bins,)
        """
        probs = self.transform(scores)
        y = np.asarray(y).ravel()
        bin_edges = np.linspace(0, 1, self.n_bins + 1)
        centers, frac_pos, mean_pred, counts = [], [], [], []

        for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
            mask = (probs >= lo) & (probs < hi)
            n = mask.sum()
            centers.append((lo + hi) / 2)
            counts.append(n)
            if n > 0:
                frac_pos.append(y[mask].mean())
                mean_pred.append(probs[mask].mean())
            else:
                frac_pos.append(np.nan)
                mean_pred.append(np.nan)

        return (np.array(centers), np.array(frac_pos),
                np.array(mean_pred), np.array(counts))

    def summary(self, scores, y):
        """
        Return a dict summarising calibration quality.
        """
        self._check_fitted()
        probs = self.transform(scores)
        y = np.asarray(y).ravel()
        preds = self.predict(scores)

        tp = int(((preds == 1) & (y == 1)).sum())
        fn = int(((preds == 0) & (y == 1)).sum())
        fp = int(((preds == 1) & (y == 0)).sum())
        tn = int(((preds == 0) & (y == 0)).sum())

        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-10)

        return {
            "method": self.method,
            "threshold": self._threshold,
            "ece": self.expected_calibration_error(scores, y),
            "brier": self.brier_score(scores, y),
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "score_range": self._score_range,
        }

    # ─────────────────────────────────────────────
    #  Internal calibration methods
    # ─────────────────────────────────────────────

    def _fit_isotonic(self, scores, y):
        """Non-parametric monotonic mapping via isotonic regression."""
        self._calibrator = IsotonicRegression(
            y_min=0, y_max=1, out_of_bounds='clip', increasing=True
        )
        self._calibrator.fit(scores, y)

    def _fit_platt(self, scores, y):
        """Platt scaling — fit logistic regression on 1D scores."""
        lr = LogisticRegression(C=1e10, solver='lbfgs', max_iter=5000)
        lr.fit(scores.reshape(-1, 1), y)
        self._calibrator = lr

    def _fit_beta(self, scores, y):
        """
        Beta calibration — map scores to [0, 1] then fit
        logistic regression on log(s/(1-s)), log(s), log(1-s).

        Falls back to Platt if score range doesn't allow Beta transform.
        """
        # Normalise scores to (0, 1) using observed range + epsilon
        smin, smax = scores.min(), scores.max()
        eps = 1e-8
        rng = smax - smin
        if rng < eps:
            # All scores identical — fall back to isotonic
            self._fit_isotonic(scores, y)
            self.method = 'isotonic'  # mark fallback
            return

        s_norm = (scores - smin) / (rng + eps)
        s_norm = np.clip(s_norm, eps, 1 - eps)

        # Compute Beta features: [log(s), log(1-s)]
        X_beta = np.column_stack([np.log(s_norm), np.log(1.0 - s_norm)])
        lr = LogisticRegression(C=1e10, solver='lbfgs', max_iter=5000)
        lr.fit(X_beta, y)

        self._calibrator = lr
        self._beta_range = (smin, smax)  # store for transform

    def _raw_transform(self, scores):
        """Apply the fitted calibrator to raw scores."""
        scores = np.asarray(scores, dtype=np.float64).ravel()

        if self.method == 'isotonic':
            return self._calibrator.predict(scores)

        elif self.method == 'platt':
            return self._calibrator.predict_proba(scores.reshape(-1, 1))[:, 1]

        elif self.method == 'beta':
            smin, smax = self._beta_range
            eps = 1e-8
            rng = smax - smin
            s_norm = (scores - smin) / (rng + eps)
            s_norm = np.clip(s_norm, eps, 1 - eps)
            X_beta = np.column_stack([np.log(s_norm), np.log(1.0 - s_norm)])
            return self._calibrator.predict_proba(X_beta)[:, 1]

    @staticmethod
    def _find_best_f1_threshold(probs, y):
        """Find threshold on probabilities maximising F1."""
        prec, rec, thresholds = precision_recall_curve(y, probs)
        f1s = 2 * prec * rec / (prec + rec + 1e-10)
        best_idx = np.argmax(f1s)
        if best_idx < len(thresholds):
            return float(thresholds[best_idx])
        return 0.5

    def _check_fitted(self):
        if not self._fitted:
            raise RuntimeError("Calibrator not fitted. Call fit() first.")

    def __repr__(self):
        status = "fitted" if self._fitted else "unfitted"
        thr = f", thr={self._threshold:.4f}" if self._fitted else ""
        return f"ScoreCalibrator(method='{self.method}'{thr}, {status})"
