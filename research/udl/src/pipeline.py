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
from .energy import DeviationEnergy, OperatorDiversity, EnergyFlow, StabilityAnalyser


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
    energy_score : bool
        If True, also fits the DeviationEnergy model during fit(),
        enabling energy_scores() and energy_decompose() methods.
        Energy scoring provides a geometric anomaly score based on the
        deviation-induced energy functional E(x).
    energy_alpha : float
        Radial anchoring weight for energy functional (default 1.0).
    energy_gamma : float
        Pairwise interaction weight (0 = disabled, default 0.0).
    energy_flow : bool
        If True, applies EnergyFlow transform (N-body gradient flow)
        before QDA projection. This moves normal points toward equilibrium
        and ejects anomalies to high-energy positions.
    energy_flow_steps : int
        Number of gradient flow iterations (default 10).
    energy_calibrate : str or None
        Calibration method for energy scores: 'isotonic', 'platt', 'beta',
        or None (raw scores). Produces calibrated P(anomaly) from energy.
    energy_cost_ratio : float
        Cost ratio for energy threshold: FN_cost / FP_cost.
        Higher values shift the threshold to catch more anomalies at
        the expense of more false positives (default 1.0 = balanced).
    energy_target_fpr : float or None
        Neyman-Pearson FPR constraint for energy threshold. When set
        (e.g., 0.01 for 1% FPR), the threshold is chosen to guarantee
        FPR <= target on training normals. Overrides energy_cost_ratio.
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
        energy_score=False,
        energy_alpha=1.0,
        energy_gamma=0.0,
        energy_flow=False,
        energy_flow_steps=10,
        energy_calibrate=None,
        energy_cost_ratio=1.0,
        energy_target_fpr=None,
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

        # ── Energy functional ──
        self.energy_score = energy_score
        self.energy_alpha = energy_alpha
        self.energy_gamma = energy_gamma
        self.energy_flow = energy_flow
        self.energy_flow_steps = energy_flow_steps
        self.energy_calibrate = energy_calibrate
        self.energy_cost_ratio = energy_cost_ratio
        self.energy_target_fpr = energy_target_fpr
        self._energy_model = None
        self._energy_calibrator = (
            ScoreCalibrator(method=energy_calibrate)
            if energy_calibrate else None
        )
        self._energy_threshold = None   # cost-sensitive threshold
        self._energy_flow_transform = None
        self._operator_diversity = None

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

        # 5d. Energy flow transform (if enabled)
        if self.energy_flow and y is not None:
            self._energy_flow_transform = EnergyFlow(
                n_steps=self.energy_flow_steps,
                learning_rate=0.05,
                alpha=self.energy_alpha,
                gamma=self.energy_gamma,
                interaction_kernel='attract_repel',
            )
            R_all = self._energy_flow_transform.fit_transform(R_all, y)

        self.projector.fit(R_all, y=y, centroid=centroid)

        # 6. Fit MFLS law-domain weighting (if enabled)
        if self.mfls_ is not None:
            tr_all = self.tensor_builder.build(R_all, self.stack.law_dims_)
            self.mfls_.fit(tr_all.law_magnitudes, y=y)

        # 7. Fit energy model (if enabled)
        if self.energy_score:
            fitted_ops = [
                (name, op) for name, op in self.stack.operators
            ]
            self._energy_model = DeviationEnergy(
                alpha=self.energy_alpha,
                beta_weights='adaptive' if y is not None else 'uniform',
                gamma=self.energy_gamma,
            )
            # Fit on full X with labels so adaptive weights can see both classes
            self._energy_model.fit(fitted_ops, X, y_ref=y)

            # 7b. Calibrate energy scores (if enabled)
            if self._energy_calibrator is not None and y is not None:
                train_energy = self._energy_model.score(X)
                self._energy_calibrator.fit(train_energy, y)
                # Cost-sensitive threshold on calibrated probabilities
                self._energy_threshold = self._compute_energy_threshold(
                    train_energy, y
                )

        # 8. Fit score calibrator (if enabled)
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
        """Apply magnifier + gravitational + energy flow transforms."""
        if self.magnifier_ is not None:
            R = self.magnifier_.magnify(R)
        if self._gravity_transform is not None:
            R = self._gravity_transform.transform(R)
        if self._energy_flow_transform is not None:
            R = self._energy_flow_transform.transform(R)
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

    # ─── ENERGY FUNCTIONAL METHODS ──────────────────────────────

    def energy_scores(self, X):
        """
        Compute deviation-induced energy E(x) for each observation.

        Higher energy = more anomalous (further from equilibrium).
        Requires energy_score=True at construction.

        Returns
        -------
        energies : ndarray (N,)
        """
        self._check_fitted()
        if self._energy_model is None:
            raise RuntimeError("Energy scoring not enabled. "
                               "Set energy_score=True in constructor.")
        return self._energy_model.score(X)

    def energy_decompose(self, X):
        """
        Decompose energy into per-law contributions.

        Returns
        -------
        dict mapping law_name → ndarray(N,) of per-law energies
        """
        self._check_fitted()
        if self._energy_model is None:
            raise RuntimeError("Energy scoring not enabled.")
        return self._energy_model.per_law_energy(X)

    def energy_gradient_scores(self, X):
        """
        Compute ||∇E(x)|| — gradient magnitude as anomaly score.

        Points at stable equilibrium (normal) have small gradients.
        Anomalies have large gradients (strong restoring force).

        Returns
        -------
        grad_mags : ndarray (N,)
        """
        self._check_fitted()
        if self._energy_model is None:
            raise RuntimeError("Energy scoring not enabled.")
        return self._energy_model.gradient_magnitude(X)

    def operator_diversity_report(self, X_ref=None):
        """
        Analyse operator diversity — the deviation-separating condition.

        Checks whether ∩_k ker(DΦ_k(μ)) = {0}, which guarantees that
        no perturbation is invisible to all operators simultaneously.

        Returns
        -------
        report : dict with diversity metrics
        """
        self._check_fitted()
        fitted_ops = [
            (name, op) for name, op in self.stack.operators
        ]
        diversity = OperatorDiversity()
        if X_ref is None:
            # Use the stored reference centroid
            mu = self.centroid_est.get_centroid()
            # We need raw-space centroid, so use the stack inverse
            # ... but we don't have X_ref stored. Use a dummy.
            report = diversity.compute(fitted_ops, X_ref=np.zeros((1, len(mu))))
        else:
            report = diversity.compute(fitted_ops, X_ref)
        return report

    def stability_analysis(self, X, y=None):
        """
        Analyse stability of the energy functional at the normal centroid.

        Provides:
        - Analytical radial Hessian (always PD)
        - Class separation metrics (Cohen's d, energy ratio)
        - Empirical Hessian (may be indefinite for nonlinear operators)

        Requires energy_score=True.

        Returns
        -------
        report : dict with stability metrics
        """
        self._check_fitted()
        if self._energy_model is None:
            raise RuntimeError("Energy scoring not enabled.")
        analyser = StabilityAnalyser(self._energy_model)
        mu = self._energy_model.mu_raw_
        return analyser.analyse(mu, X=X, y=y)

    # ─── ENERGY CALIBRATION METHODS ──────────────────────────────

    def energy_predict_proba(self, X):
        """
        Calibrated P(anomaly) from energy scores.

        Requires energy_score=True and energy_calibrate='isotonic'|'platt'|'beta'.

        Returns
        -------
        probs : ndarray (N,) in [0, 1]
        """
        self._check_fitted()
        if self._energy_model is None:
            raise RuntimeError("Energy scoring not enabled.")
        if self._energy_calibrator is None or not self._energy_calibrator._fitted:
            raise RuntimeError(
                "Energy calibration not enabled. "
                "Set energy_calibrate='platt' (or 'isotonic'/'beta') in constructor."
            )
        raw = self._energy_model.score(X)
        return self._energy_calibrator.transform(raw)

    def energy_predict(self, X, threshold=None):
        """
        Binary anomaly prediction from calibrated energy scores.

        Uses the cost-sensitive threshold by default, or a custom one.

        Parameters
        ----------
        X : ndarray (N, m)
        threshold : float or None
            Override threshold on calibrated probability.
            Default: cost-sensitive optimal threshold from training.

        Returns
        -------
        labels : ndarray (N,) of {0, 1}
        """
        probs = self.energy_predict_proba(X)
        t = threshold if threshold is not None else self._energy_threshold
        if t is None:
            t = self._energy_calibrator.optimal_threshold()
        return (probs >= t).astype(int)

    def energy_predict_tiered(self, X, review_low=0.15, review_high=0.70):
        """
        Three-tier energy-based classification.

        Returns
        -------
        tiers : ndarray (N,) of {0, 1, 2}
            0 = CLEAR, 1 = REVIEW, 2 = ALERT
        probs : ndarray (N,) in [0, 1]
        """
        probs = self.energy_predict_proba(X)
        tiers = np.zeros(len(probs), dtype=int)
        tiers[probs >= review_low] = 1
        tiers[probs >= review_high] = 2
        return tiers, probs

    def energy_calibration_summary(self, X, y):
        """
        Return calibration quality metrics for energy scores.

        Returns
        -------
        report : dict with ECE, Brier, precision, recall, F1, FP, FN, threshold
        """
        self._check_fitted()
        if self._energy_calibrator is None:
            raise RuntimeError("Energy calibration not enabled.")
        raw = self._energy_model.score(X)
        report = self._energy_calibrator.summary(raw, y)
        # Add cost-sensitive threshold info
        report['cost_threshold'] = self._energy_threshold
        report['cost_ratio'] = self.energy_cost_ratio
        # Also compute detection stats at cost-sensitive threshold
        preds = self.energy_predict(X)
        y = np.asarray(y).ravel()
        tp = int(((preds == 1) & (y == 1)).sum())
        fn = int(((preds == 0) & (y == 1)).sum())
        fp = int(((preds == 1) & (y == 0)).sum())
        tn = int(((preds == 0) & (y == 0)).sum())
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-10)
        report['cost_tp'] = tp
        report['cost_fn'] = fn
        report['cost_fp'] = fp
        report['cost_tn'] = tn
        report['cost_precision'] = prec
        report['cost_recall'] = rec
        report['cost_f1'] = f1
        return report

    def _compute_energy_threshold(self, train_energy, y):
        """
        Find threshold on calibrated energy probabilities.

        Priority:
        1. energy_target_fpr: Neyman-Pearson (FPR <= target on training normals)
        2. energy_cost_ratio != 1: cost-sensitive (minimise cost_ratio*FN + FP)
        3. Otherwise: F1-optimal threshold from calibrator
        """
        probs = self._energy_calibrator.transform(train_energy)
        y = np.asarray(y).ravel()

        # Mode 1: FPR-constrained (Neyman-Pearson)
        if self.energy_target_fpr is not None:
            normals = probs[y == 0]
            # Find the lowest threshold where FPR(normals) <= target
            # Sort normal probabilities descending
            sorted_probs = np.sort(normals)[::-1]
            max_fp = int(np.floor(self.energy_target_fpr * len(normals)))
            if max_fp <= 0:
                return float(sorted_probs[0] + 1e-6)  # extremely strict
            # Threshold = the (max_fp)th highest normal probability
            threshold = float(sorted_probs[min(max_fp, len(sorted_probs)-1)])
            return threshold + 1e-8  # just above to ensure <= FPR

        # Mode 2: Cost-sensitive
        if self.energy_cost_ratio != 1.0:
            thresholds = np.linspace(0.01, 0.99, 200)
            best_cost = np.inf
            best_t = 0.5
            for t in thresholds:
                preds = (probs >= t).astype(int)
                fn = ((preds == 0) & (y == 1)).sum()
                fp = ((preds == 1) & (y == 0)).sum()
                cost = self.energy_cost_ratio * fn + fp
                if cost < best_cost:
                    best_cost = cost
                    best_t = t
            return float(best_t)

        # Mode 3: Balanced (F1-optimal)
        return self._energy_calibrator.optimal_threshold()

    def _check_fitted(self):
        if not self._fitted:
            raise RuntimeError("Pipeline not fitted. Call fit() first.")

    def __repr__(self):
        status = "fitted" if self._fitted else "unfitted"
        return f"UDLPipeline({status}, D={self.stack.total_dim})"
