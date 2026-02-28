"""
Hyperplane Projection — Geometric Class Separation
=====================================================
Projects the multi-spectrum representation onto a discriminative
hyperplane that maximally separates normal from anomalous behaviour.

Implements:
  - Fisher Linear Discriminant (supervised, with partial labels)
  - PCA-based unsupervised projection
  - Anomaly vector decomposition (perpendicular + parallel to hyperplane)
  - Angular analysis for direction-based classification
"""

import numpy as np


class HyperplaneProjector:
    """
    Projects multi-spectrum anomaly representations onto a separating
    hyperplane and classifies based on geometric position.
    """

    def __init__(self, method="fisher", n_components=1):
        """
        Parameters
        ----------
        method : str
            'fisher' (supervised) or 'pca' (unsupervised)
        n_components : int
            Number of projection dimensions
        """
        self.method = method
        self.n_components = n_components
        self.W_ = None           # Projection matrix (D, n_components)
        self.threshold_ = None   # Decision threshold
        self.centroid_ = None    # Normal-class centroid in projected space
        self._fitted = False

    def fit(self, R, y=None, centroid=None):
        """
        Fit the projection hyperplane.

        Parameters
        ----------
        R : ndarray (N, D)
            Stacked representation vectors.
        y : ndarray (N,) or None
            Labels: 0=normal, 1=anomaly. Required for 'fisher'.
            If None with fisher, falls back to PCA.
        centroid : ndarray (D,) or None
            Pre-computed centroid. If None, uses R.mean(axis=0).
        """
        N, D = R.shape
        self.centroid_ = centroid if centroid is not None else R.mean(axis=0)

        if self.method == "fisher" and y is not None:
            self._fit_fisher(R, y)
        else:
            self._fit_pca(R)

        # Project reference data to set threshold
        R_proj = self.project(R).ravel()
        if y is not None:
            # Determine correct sign: anomalies should project higher
            normal_mean = R_proj[y == 0].mean() if (y == 0).any() else R_proj.mean()
            anomaly_mean = R_proj[y == 1].mean() if (y == 1).any() else R_proj.max()
            # If anomalies project lower, flip the projection axis
            if anomaly_mean < normal_mean:
                self.W_ = -self.W_
                R_proj = -R_proj
                normal_mean, anomaly_mean = -anomaly_mean, -normal_mean
            self.threshold_ = (normal_mean + anomaly_mean) / 2
        else:
            # Unsupervised: set threshold at mean + 2*std
            self.threshold_ = R_proj.mean() + 2 * R_proj.std()

        self._fitted = True
        return self

    def _fit_fisher(self, R, y):
        """Fisher Linear Discriminant — maximises between/within scatter ratio."""
        classes = np.unique(y)
        if len(classes) < 2:
            self._fit_pca(R)
            return

        mu_overall = R.mean(axis=0)
        D = R.shape[1]

        S_W = np.zeros((D, D))  # Within-class scatter
        S_B = np.zeros((D, D))  # Between-class scatter

        for c in classes:
            R_c = R[y == c]
            mu_c = R_c.mean(axis=0)
            diff = R_c - mu_c
            S_W += diff.T @ diff

            n_c = len(R_c)
            mu_diff = (mu_c - mu_overall).reshape(-1, 1)
            S_B += n_c * (mu_diff @ mu_diff.T)

        # Regularise S_W
        S_W += 1e-6 * np.eye(D)

        try:
            M = np.linalg.inv(S_W) @ S_B
            eigenvalues, eigenvectors = np.linalg.eigh(M)
            idx = np.argsort(eigenvalues)[::-1]
            self.W_ = eigenvectors[:, idx[:self.n_components]]
        except np.linalg.LinAlgError:
            self._fit_pca(R)

    def _fit_pca(self, R):
        """PCA-based projection — unsupervised fallback."""
        mu = R.mean(axis=0)
        R_c = R - mu
        U, S, Vt = np.linalg.svd(R_c, full_matrices=False)
        self.W_ = Vt[:self.n_components].T

    def project(self, R):
        """Project representations onto the hyperplane normal direction."""
        if self.W_ is None:
            raise RuntimeError("Call fit() first")
        return (R - self.centroid_) @ self.W_

    def classify(self, R, return_scores=False):
        """
        Classify observations as normal (0) or anomaly (1).

        Parameters
        ----------
        R : ndarray (N, D)
        return_scores : bool
            If True, also return projection scores.

        Returns
        -------
        predictions : ndarray (N,) of {0, 1}
        scores : ndarray (N,) — only if return_scores=True
        """
        scores = self.project(R).ravel()
        predictions = (scores > self.threshold_).astype(int)
        if return_scores:
            return predictions, scores
        return predictions

    def decompose_vector(self, R):
        """
        Decompose anomaly vector into parallel and perpendicular components
        relative to the decision hyperplane.

        Returns
        -------
        dict with:
          - 'parallel':     component along hyperplane normal (classifier-relevant)
          - 'perpendicular': component within hyperplane (cluster-relevant)
          - 'angle':        angle between vector and hyperplane normal (radians)
          - 'magnitude':    total deviation magnitude
        """
        dev = R - self.centroid_
        w = self.W_.ravel()
        w_norm = w / (np.linalg.norm(w) + 1e-10)

        # Scalar projection onto normal
        parallel_scalar = dev @ w_norm  # (N,)

        # Parallel vector component
        parallel_vec = np.outer(parallel_scalar, w_norm)  # (N, D)

        # Perpendicular component
        perp_vec = dev - parallel_vec  # (N, D)

        # Magnitudes
        parallel_mag = np.abs(parallel_scalar)
        perp_mag = np.linalg.norm(perp_vec, axis=1)
        total_mag = np.linalg.norm(dev, axis=1)

        # Angle from hyperplane normal
        cos_angle = parallel_scalar / (total_mag + 1e-10)
        cos_angle = np.clip(cos_angle, -1, 1)
        angle = np.arccos(np.abs(cos_angle))

        return {
            "parallel": parallel_mag,
            "perpendicular": perp_mag,
            "angle": angle,
            "magnitude": total_mag,
            "parallel_sign": np.sign(parallel_scalar),
        }

    def predict_proba(self, R):
        """
        Convert projection scores to pseudo-probabilities via sigmoid mapping.

        Maps Fisher projection scores using a sigmoid centred at the
        decision threshold.  For truly calibrated probabilities, use
        ScoreCalibrator from udl.calibration on top of pipeline.score().

        Returns
        -------
        probs : ndarray (N,) in [0, 1]
        """
        scores = self.project(R).ravel()
        # Sigmoid centred at threshold, scale set from reference spread
        z = scores - self.threshold_
        # Clip to avoid overflow in exp
        z = np.clip(z, -500, 500)
        return 1.0 / (1.0 + np.exp(-z))

    def classify_tiered(self, R):
        """
        Three-tier classification: CLEAR / REVIEW / ALERT.

        Returns
        -------
        tiers : ndarray (N,) of {0, 1, 2}
        probs : ndarray (N,)
        """
        probs = self.predict_proba(R)
        tiers = np.ones(len(probs), dtype=int)  # default REVIEW
        tiers[probs < 0.3] = 0   # CLEAR
        tiers[probs >= 0.7] = 2  # ALERT
        return tiers, probs

    def angular_analysis(self, R, tensor_result=None):
        """
        Angle-based anomaly analysis.

        Observations deviating at unusual angles (relative to normal
        reference cluster) are more likely to be novel anomalies vs.
        well-known patterns.

        Returns angular deviation in [0, π/2] for each observation.
        """
        decomp = self.decompose_vector(R)
        return decomp["angle"]

    def __repr__(self):
        status = "fitted" if self._fitted else "unfitted"
        return f"HyperplaneProjector(method='{self.method}', {status})"


class QDAProjector:
    """
    Quadratic Discriminant Analysis — models per-class covariance.

    Unlike Fisher (linear), QDA fits a separate Gaussian per class,
    capturing non-linear decision boundaries.  Especially effective
    after the DimensionMagnifier normalises features to [-1, +1].

    Same interface as HyperplaneProjector so the pipeline can swap
    them transparently.

    Production Features
    -------------------
    - Auto-calibrated threshold (maximises F1 on training data)
    - Cost-sensitive threshold (penalise missed anomalies vs false alarms)
    - Isotonic probability calibration for reliable confidence scores
    - Three-tier predictions: CLEAR / REVIEW / ALERT
    """

    def __init__(self, reg_param=1e-4, cost_ratio=1.0, target_fpr=None):
        self.reg_param = reg_param
        self.cost_ratio = cost_ratio     # FN cost / FP cost  (10 = missing anomaly 10x worse)
        self.target_fpr = target_fpr     # Neyman-Pearson: guarantee FPR ≤ target_fpr
        self._qda = None
        self._calibrator = None          # isotonic probability calibrator
        self.centroid_ = None
        self.threshold_ = 0.5            # default; overridden by calibration
        self.threshold_f1_ = None        # best-F1 threshold (stored for diagnostics)
        self.threshold_cost_ = None      # cost-sensitive threshold
        self.threshold_fpr_ = None       # Neyman-Pearson threshold
        self._review_band = (0.3, 0.7)   # default review band; refined during calibration
        self._fitted = False
        self._calibrated = False

    def fit(self, R, y=None, centroid=None):
        """Fit QDA on the representation space."""
        from sklearn.discriminant_analysis import QuadraticDiscriminantAnalysis

        self.centroid_ = centroid if centroid is not None else R.mean(axis=0)

        if y is None or len(np.unique(y)) < 2:
            raise ValueError("QDAProjector requires labels with 2+ classes")

        self._qda = QuadraticDiscriminantAnalysis(reg_param=self.reg_param)
        self._qda.fit(R, y)
        self._fitted = True

        # Auto-calibrate threshold on training data
        self._calibrate_threshold(R, y)
        return self

    def _calibrate_threshold(self, R, y):
        """
        Find optimal decision threshold using training data.

        Four strategies computed simultaneously:
          1. Best-F1 threshold (maximises F1 score)
          2. Cost-sensitive threshold (minimises cost_ratio*FN + FP)
          3. Neyman-Pearson threshold (guarantees FPR ≤ target_fpr)
          4. Review band (region of uncertain predictions)

        The active threshold priority:
          target_fpr set  → Neyman-Pearson (FPR guarantee)
          cost_ratio != 1 → cost-sensitive
          otherwise       → best-F1
        """
        from sklearn.metrics import precision_recall_curve, f1_score as sk_f1

        probs = self._qda.predict_proba(R)[:, 1]

        # ── Strategy 1: Best-F1 threshold ──
        precisions, recalls, thresholds = precision_recall_curve(y, probs)
        f1s = 2 * precisions * recalls / (precisions + recalls + 1e-10)
        best_idx = np.argmax(f1s[:-1])  # last entry is sentinel
        self.threshold_f1_ = float(thresholds[best_idx])

        # ── Strategy 2: Cost-sensitive threshold ──
        sweep = np.linspace(0.01, 0.99, 500)
        best_cost = np.inf
        best_t = 0.5
        n_pos = (y == 1).sum()
        n_neg = (y == 0).sum()
        for t in sweep:
            preds = (probs >= t).astype(int)
            fn = ((preds == 0) & (y == 1)).sum()
            fp = ((preds == 1) & (y == 0)).sum()
            cost = self.cost_ratio * fn + fp
            if cost < best_cost:
                best_cost = cost
                best_t = t
        self.threshold_cost_ = float(best_t)

        # ── Strategy 3: Neyman-Pearson (FPR guarantee) ──
        if self.target_fpr is not None:
            normal_probs = probs[y == 0]
            # Threshold = (1 - target_fpr) percentile of normal probabilities
            # This guarantees at most target_fpr fraction of normals are flagged
            self.threshold_fpr_ = float(np.percentile(
                normal_probs, 100 * (1 - self.target_fpr)
            ))
        else:
            self.threshold_fpr_ = None

        # ── Set active threshold (priority: FPR > cost > F1) ──
        if self.target_fpr is not None and self.threshold_fpr_ is not None:
            self.threshold_ = self.threshold_fpr_
        elif self.cost_ratio != 1.0:
            self.threshold_ = self.threshold_cost_
        else:
            self.threshold_ = self.threshold_f1_

        # ── Strategy 4: Review band ──
        margin = 0.15
        n = len(y)
        margin = max(0.05, min(0.25, margin * np.sqrt(500 / n)))
        self._review_band = (
            max(0.01, self.threshold_ - margin),
            min(0.99, self.threshold_ + margin),
        )

        # ── Isotonic calibration ──
        try:
            from sklearn.isotonic import IsotonicRegression
            self._calibrator = IsotonicRegression(
                y_min=0, y_max=1, out_of_bounds='clip'
            )
            self._calibrator.fit(probs, y)
            self._calibrated = True
        except Exception:
            self._calibrator = None
            self._calibrated = False

    def project(self, R):
        """Return anomaly probability (analogous to projection score)."""
        if not self._fitted:
            raise RuntimeError("Call fit() first")
        return self._qda.predict_proba(R)[:, 1].reshape(-1, 1)

    def predict_proba(self, R):
        """
        Calibrated anomaly probability.

        If isotonic calibration succeeded, returns calibrated probs.
        Otherwise returns raw QDA posterior probabilities.

        Returns
        -------
        probs : ndarray (N,) in [0, 1]
        """
        raw = self.project(R).ravel()
        if self._calibrated and self._calibrator is not None:
            return self._calibrator.predict(raw)
        return raw

    def classify(self, R, return_scores=False):
        """Classify observations as normal (0) or anomaly (1)."""
        probs = self.project(R).ravel()
        predictions = (probs >= self.threshold_).astype(int)
        if return_scores:
            return predictions, probs
        return predictions

    def classify_tiered(self, R):
        """
        Three-tier production classification.

        Returns
        -------
        tiers : ndarray (N,) of {0, 1, 2}
            0 = CLEAR  — confidently normal, no action needed
            1 = REVIEW — uncertain, needs human review
            2 = ALERT  — confidently anomalous, escalate immediately
        probs : ndarray (N,) — calibrated probabilities
        """
        probs = self.predict_proba(R)
        lo, hi = self._review_band
        tiers = np.ones(len(probs), dtype=int)  # default REVIEW
        tiers[probs < lo] = 0   # CLEAR
        tiers[probs >= hi] = 2  # ALERT
        return tiers, probs

    def decompose_vector(self, R):
        """Compatibility stub — QDA has no hyperplane normal."""
        dev = R - self.centroid_
        magnitude = np.linalg.norm(dev, axis=1)
        probs = self.project(R).ravel()
        return {
            "parallel": probs,
            "perpendicular": np.zeros(len(R)),
            "angle": np.zeros(len(R)),
            "magnitude": magnitude,
            "parallel_sign": np.sign(probs - 0.5),
        }

    def angular_analysis(self, R, tensor_result=None):
        """Return anomaly probabilities (QDA analogue of angular analysis)."""
        return self.project(R).ravel()

    def get_threshold_info(self):
        """Return diagnostic info about calibrated thresholds."""
        return {
            "active_threshold": self.threshold_,
            "best_f1_threshold": self.threshold_f1_,
            "cost_sensitive_threshold": self.threshold_cost_,
            "neyman_pearson_threshold": self.threshold_fpr_,
            "target_fpr": self.target_fpr,
            "cost_ratio": self.cost_ratio,
            "review_band": self._review_band,
            "calibrated": self._calibrated,
        }

    def __repr__(self):
        status = "fitted" if self._fitted else "unfitted"
        cal = ", calibrated" if self._calibrated else ""
        thr = f", thr={self.threshold_:.3f}" if self._fitted else ""
        fpr = f", fpr≤{self.target_fpr}" if self.target_fpr else ""
        return f"QDAProjector(reg={self.reg_param}, cost={self.cost_ratio}{thr}{fpr}{cal}, {status})"
