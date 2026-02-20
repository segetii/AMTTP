"""
UDL Pipeline — End-to-End Anomaly Detection
=============================================
Orchestrates:  Raw → Stack → Centroid → Tensor → Projection → Scores

This is the main user-facing API:
    pipe = UDLPipeline()
    pipe.fit(X_train, y_train)
    scores = pipe.score(X_test)
    labels = pipe.predict(X_test)
"""

import numpy as np
from .stack import RepresentationStack
from .centroid import CentroidEstimator
from .tensor import AnomalyTensor
from .projection import HyperplaneProjector
from .mfls_weighting import MFLSWeighting
from .gravitational import GravitationalTransformVec, TwoPassGravity
from .calibration import ScoreCalibrator


class UDLPipeline:
    """
    Universal Deviation Law — full detection pipeline.

    Flow:
      1. RepresentationStack: raw → multi-spectrum features R ∈ ℝ^D
      2. CentroidEstimator:   R_ref → centroid c ∈ ℝ^D
      3. AnomalyTensor:       R → tensor T[i, k, d] + MDN decomposition
      4. HyperplaneProjector: T → projection → classification

    Parameters
    ----------
    centroid_method : str
        Centroid estimation strategy (default 'auto').
    projection_method : str
        'fisher' (supervised) or 'pca' (unsupervised).
    exp_alpha : float
        Exponential amplification factor.
    score_weights : tuple of (w_magnitude, w_novelty)
        Weights for composite anomaly score.
    operators : list or None
        Custom spectrum operators. None = default 5-operator stack.
    score_method : str
        'v1' = original magnitude/max + novelty (default).
        'v2' = per-law z-score sigmoid + novelty.
        'v3a' = one-sided exponential activation on z-scores.
        'v3b' = shifted sigmoid (corrects v2 baseline shift).
        'v3c' = distribution-free quantile scoring.
        'v3d' = hybrid 3-channel (magnitude quantile + z-spike + novelty).
        'v3e' = Fisher projection score (uses the hyperplane directly).
    calibrate : str or None
        Score calibration method to map raw scores to probabilities.
        None = disabled (default). 'isotonic' = non-parametric isotonic regression.
        'platt' = sigmoid (logistic) scaling. 'beta' = Beta calibration.
        When enabled, predict_proba() returns calibrated P(anomaly).
    mfls_method : str or None
        MFLS law-domain weight calibration strategy.
        None = disabled (use fixed score_weights as before).
        'mi' = Mutual Information weighting (supervised).
        'variance' = Variance-Ratio / Fisher weighting.
        'logistic' = Logistic regression on per-law magnitudes.
    magnify : bool
        Whether to apply DimensionMagnifier before projection.
        Automatically True when projection_method='qda-magnified'.
    cost_ratio : float
        FN/FP cost ratio passed to QDAProjector (default 1.0).
        cost_ratio=10 means missing an anomaly is 10x worse than a false alarm.
    ensemble : str or None
        Ensemble mode combining QDA + MFLS scores.
        None = disabled. 'stack' / 'product' / 'max_f1'.
    gravity : str or None
        Gravitational cluster transform applied after magnification.
        None = disabled (default).
        'attract_repel' = Approach C — fixed attract+repel field.
        'two_pass' = Approach A — soft-probability iterative warp.
    gravity_alpha : float
        Attraction strength for 'attract_repel' mode (default 0.3).
    gravity_gamma : float
        Repulsion strength for 'attract_repel' mode (default 0.1).
    gravity_strength : float
        Pull strength for 'two_pass' mode (default 0.3).
    gravity_passes : int
        Number of iterations for either mode (default 2).
    target_fpr : float or None
        Neyman-Pearson FPR constraint for QDAProjector. When set (e.g., 0.01),
        the QDA threshold is adjusted to guarantee FPR ≤ target_fpr on the
        training normal data. This is the most direct FP-reduction lever.
    """

    def __init__(
        self,
        centroid_method="auto",
        projection_method="fisher",
        exp_alpha=1.0,
        score_weights=(0.7, 0.3),
        operators=None,
        score_method='v1',
        mfls_method=None,
        mfls_ridge_alpha=0.1,
        mfls_smooth_sigma=1.0,
        mfls_max_fpr=None,
        magnify=False,
        cost_ratio=1.0,
        target_fpr=None,
        ensemble=None,
        gravity=None,
        gravity_alpha=0.3,
        gravity_gamma=0.1,
        gravity_strength=0.3,
        gravity_passes=2,
        calibrate=None,
        include_marginal=False,
    ):
        self.stack = RepresentationStack(
            operators=operators, exp_alpha=exp_alpha,
            include_marginal=include_marginal,
        )
        self.centroid_est = CentroidEstimator(method=centroid_method)
        self.tensor_builder = AnomalyTensor()
        self.score_weights = score_weights
        self.score_method = score_method
        self.mfls_method = mfls_method
        self.cost_ratio = cost_ratio
        self.target_fpr = target_fpr
        self.ensemble = ensemble

        # ── Magnifier setup ──
        use_magnify = magnify or projection_method == 'qda-magnified'
        if use_magnify:
            from .magnifier import DimensionMagnifier
            self.magnifier_ = DimensionMagnifier(verbose=True)
        else:
            self.magnifier_ = None

        # ── Projector setup ──
        if projection_method in ('qda', 'qda-magnified'):
            from .projection import QDAProjector
            self.projector = QDAProjector(
                cost_ratio=cost_ratio, target_fpr=target_fpr
            )
        else:
            self.projector = HyperplaneProjector(method=projection_method)

        # ── MFLS weighting ──
        self.mfls_ = (
            MFLSWeighting(
                method=mfls_method,
                ridge_alpha=mfls_ridge_alpha,
                smooth_sigma=mfls_smooth_sigma,
                max_fpr=mfls_max_fpr,
            )
            if mfls_method
            else None
        )

        # ── Gravitational transform ──
        self.gravity = gravity
        self._gravity_transform = None
        if gravity == 'attract_repel':
            self._gravity_transform = GravitationalTransformVec(
                alpha=gravity_alpha,
                gamma=gravity_gamma,
                beta=1.0,
                n_iterations=gravity_passes,
                normalize=True,
            )
        elif gravity == 'two_pass':
            self._gravity_transform = TwoPassGravity(
                strength=gravity_strength,
                n_passes=gravity_passes,
                normalize=True,
            )

        # ── Score calibration ──
        self.calibrate = calibrate  # None, 'isotonic', 'platt', or 'beta'
        self._calibrator = (
            ScoreCalibrator(method=calibrate) if calibrate else None
        )

        self._fitted = False
        self._tensor_result_ref = None

    def fit(self, X, y=None):
        """
        Fit pipeline on training data.

        Parameters
        ----------
        X : ndarray (N, m)
            Raw feature matrix.
        y : ndarray (N,) or None
            Labels (0=normal, 1=anomaly). Enables supervised projection
            and more accurate centroid estimation using normal class only.
        """
        # Determine reference subset (normal data)
        if y is not None:
            X_ref = X[y == 0]
            if len(X_ref) == 0:
                X_ref = X  # fallback
        else:
            X_ref = X

        # 1. Fit representation stack on reference data
        self.stack.fit(X_ref)
        R_ref = self.stack.transform(X_ref)

        # 2. Estimate centroid
        self.centroid_est.fit(R_ref)
        centroid = self.centroid_est.get_centroid()

        # 3. Fit tensor builder
        self.tensor_builder.fit(R_ref, centroid=centroid)

        # 4. Build reference tensor (for novelty calibration)
        self._tensor_result_ref = self.tensor_builder.build(
            R_ref, self.stack.law_dims_
        )

        # 4b. Store per-law reference stats for v2 z-score scoring
        self.tensor_builder.store_ref_law_stats(self._tensor_result_ref)

        # 5. Transform full training data
        R_all = self.stack.transform(X)

        # 5b. Fit and apply magnifier (if enabled)
        if self.magnifier_ is not None and y is not None:
            self.magnifier_.fit(R_all, y,
                               law_names=self.stack.law_names_,
                               law_dims=self.stack.law_dims_)
            R_all = self.magnifier_.magnify(R_all)

        # 5c. Gravitational transform (if enabled)
        if self._gravity_transform is not None and y is not None:
            R_all = self._gravity_transform.fit_transform(R_all, y)

        self.projector.fit(R_all, y=y, centroid=centroid)

        # 6. Fit MFLS law-domain weighting (if enabled)
        if self.mfls_ is not None:
            tr_all = self.tensor_builder.build(R_all, self.stack.law_dims_)
            self.mfls_.fit(tr_all.law_magnitudes, y=y)

        # 7. Fit score calibrator (if enabled)
        self._fitted = True  # must set before score() call
        if self._calibrator is not None and y is not None:
            train_scores = self.score(X)
            self._calibrator.fit(train_scores, y)

        return self

    def transform(self, X):
        """
        Transform raw data into multi-spectrum representation.

        Returns
        -------
        R : ndarray (N, D)
        """
        self._check_fitted()
        return self.stack.transform(X)

    def build_tensor(self, X):
        """
        Build anomaly tensor for given data.

        Returns
        -------
        TensorResult
        """
        self._check_fitted()
        R = self.stack.transform(X)
        return self.tensor_builder.build(R, self.stack.law_dims_)

    def score(self, X):
        """
        Compute composite anomaly scores.

        If MFLS weighting is enabled, uses calibrated per-law weights.
        Otherwise, uses fixed magnitude + novelty weights.

        Returns
        -------
        scores : ndarray (N,)   — higher = more anomalous
        """
        self._check_fitted()
        tr = self.build_tensor(X)

        if self.mfls_ is not None:
            return self.mfls_.score(tr.law_magnitudes)

        if self.score_method == 'v2':
            return tr.anomaly_score_v2(weights=self.score_weights)
        elif self.score_method == 'v3a':
            return tr.anomaly_score_v3a(weights=self.score_weights)
        elif self.score_method == 'v3b':
            return tr.anomaly_score_v3b(weights=self.score_weights)
        elif self.score_method == 'v3c':
            return tr.anomaly_score_v3c(weights=self.score_weights)
        elif self.score_method == 'v3d':
            return tr.anomaly_score_v3d(weights=self.score_weights)
        elif self.score_method == 'v3e':
            # Fisher projection score — use the hyperplane directly
            R = self.stack.transform(X)
            _, fisher_scores = self.projector.classify(R, return_scores=True)
            # Robust normalisation (IQR-based) — resistant to outliers
            # Min-max is sensitive to a single extreme normal point shifting
            # the scale and creating FP. IQR-based clips outliers first.
            q25 = np.percentile(fisher_scores, 25)
            q75 = np.percentile(fisher_scores, 75)
            iqr = q75 - q25
            if iqr < 1e-10:
                # Fallback to min-max if IQR is degenerate
                fmin, fmax = fisher_scores.min(), fisher_scores.max()
                if fmax - fmin < 1e-10:
                    return np.zeros(len(fisher_scores))
                return (fisher_scores - fmin) / (fmax - fmin)
            # Clip at [Q25 - 1.5*IQR, Q75 + 1.5*IQR] then scale to [0, 1]
            lo = q25 - 1.5 * iqr
            hi = q75 + 1.5 * iqr
            clipped = np.clip(fisher_scores, lo, hi)
            return (clipped - lo) / (hi - lo)

        return tr.anomaly_score(weights=self.score_weights)

    def _apply_transforms(self, R):
        """Apply magnifier + gravitational transform to representation."""
        if self.magnifier_ is not None:
            R = self.magnifier_.magnify(R)
        if self._gravity_transform is not None:
            R = self._gravity_transform.transform(R)
        return R

    def predict(self, X):
        """
        Binary anomaly predictions.

        Returns
        -------
        labels : ndarray (N,) of {0, 1}
        """
        self._check_fitted()
        R = self.stack.transform(X)
        R = self._apply_transforms(R)
        return self.projector.classify(R)

    def predict_proba(self, X):
        """
        Calibrated anomaly probabilities.

        If calibration is enabled (calibrate='isotonic'/'platt'/'beta'),
        maps raw scores through the fitted calibrator for true probabilities.
        Otherwise falls back to the projector's sigmoid approximation.

        Returns
        -------
        probs : ndarray (N,) in [0, 1]
        """
        self._check_fitted()
        if self._calibrator is not None and self._calibrator._fitted:
            raw_scores = self.score(X)
            return self._calibrator.transform(raw_scores)
        # Fallback: projector pseudo-probabilities
        R = self.stack.transform(X)
        R = self._apply_transforms(R)
        return self.projector.predict_proba(R)

    def score_calibrated(self, X):
        """
        Score with calibration — returns probabilities if calibrator is fitted,
        otherwise returns raw scores.

        Returns
        -------
        calibrated : ndarray (N,) — probabilities in [0,1] if calibrated
        """
        self._check_fitted()
        raw = self.score(X)
        if self._calibrator is not None and self._calibrator._fitted:
            return self._calibrator.transform(raw)
        return raw

    def calibration_summary(self, X, y):
        """
        Compute calibration quality metrics on test data.

        Parameters
        ----------
        X : ndarray — test features
        y : ndarray — test labels (0/1)

        Returns
        -------
        dict with ECE, Brier score, F1, threshold, TP/FN/FP/TN, etc.
        """
        self._check_fitted()
        if self._calibrator is None or not self._calibrator._fitted:
            raise RuntimeError("Calibration not enabled. Pass calibrate='isotonic' to __init__.")
        raw = self.score(X)
        return self._calibrator.summary(raw, y)

    def predict_tiered(self, X):
        """
        Three-tier prediction: CLEAR / REVIEW / ALERT.

        Returns
        -------
        tiers : ndarray (N,) of {0, 1, 2}
        probs : ndarray (N,)
        """
        self._check_fitted()
        R = self.stack.transform(X)
        R = self._apply_transforms(R)
        return self.projector.classify_tiered(R)

    def score_and_predict(self, X):
        """
        Return both scores and predictions.
        """
        self._check_fitted()
        R = self.stack.transform(X)
        tr = self.tensor_builder.build(R, self.stack.law_dims_)
        scores = tr.anomaly_score(weights=self.score_weights)
        labels = self.projector.classify(R)
        return scores, labels

    def decompose(self, X):
        """
        Full decomposition: tensor + hyperplane vector analysis.

        Returns
        -------
        dict with keys:
          'tensor_result': TensorResult
          'projection_decomp': dict from projector.decompose_vector()
          'scores': composite anomaly scores
          'labels': binary predictions
          'coupling_matrix': cross-law coupling correlations
        """
        self._check_fitted()
        R = self.stack.transform(X)
        tr = self.tensor_builder.build(R, self.stack.law_dims_)
        decomp = self.projector.decompose_vector(R)
        coupling = self.tensor_builder.cross_law_coupling(tr)

        return {
            "tensor_result": tr,
            "projection_decomp": decomp,
            "scores": tr.anomaly_score(weights=self.score_weights),
            "labels": self.projector.classify(R),
            "coupling_matrix": coupling,
        }

    def get_diagnostics(self):
        """
        Return diagnostic info about the fitted pipeline.
        """
        self._check_fitted()
        return {
            "stack": repr(self.stack),
            "centroid_method": repr(self.centroid_est),
            "projector": repr(self.projector),
            "law_dims": self.stack.law_dims_,
            "law_names": self.stack.law_names_,
            "total_representation_dim": self.stack.total_dim,
        }

    def _check_fitted(self):
        if not self._fitted:
            raise RuntimeError("Pipeline not fitted. Call fit() first.")

    def __repr__(self):
        status = "fitted" if self._fitted else "unfitted"
        return f"UDLPipeline({status}, D={self.stack.total_dim})"
