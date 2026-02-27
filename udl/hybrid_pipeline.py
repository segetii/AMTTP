"""
Hybrid Pipeline — Adaptive Fisher/RankFusion Selection
=======================================================
Auto-detects anomaly heterogeneity from training data and selects
the optimal fusion strategy:

  - HOMOGENEOUS anomalies (e.g. shuttle): Use Fisher projection
    → single discriminant direction captures everything
  - HETEROGENEOUS anomalies (e.g. mammography): Use RankFusion
    → preserves each operator's unique detections

Detection mechanism:
  On a validation fold, fit each operator independently and measure
  the pairwise Spearman rank correlation of their anomaly scores.
  Low mean correlation → heterogeneous → RankFusion.
  High mean correlation → homogeneous → Fisher.

Can also blend both strategies with learned mixing weight α:
  score = α · fisher_score + (1-α) · rankfuse_score

Usage:
    from udl.hybrid_pipeline import HybridPipeline

    pipe = HybridPipeline(operators=[...])
    pipe.fit(X_train, y_train)
    scores = pipe.score(X_test)  # auto-selects best strategy
"""

import copy
import warnings
import numpy as np
from scipy.stats import spearmanr
from sklearn.model_selection import StratifiedKFold

from .pipeline import UDLPipeline
from .rank_fusion import RankFusionPipeline


class HybridPipeline:
    """
    Adaptive anomaly detection that selects between Fisher projection
    and rank fusion based on measured operator agreement.

    Parameters
    ----------
    operators : list of (name, operator) tuples
        Spectrum operators.
    centroid_method : str
        Centroid estimation for sub-pipelines.
    score_method : str
        Scoring mode for sub-pipelines.
    heterogeneity_threshold : float
        Mean Spearman |ρ| below this → use RankFusion.
        Above → use Fisher. Default 0.5 (empirically calibrated).
    mode : str
        'auto'  — auto-detect and pick one (default)
        'blend' — fit both and blend with learned α
        'fisher' — force Fisher only
        'fusion' — force RankFusion only
    n_val_folds : int
        Number of cross-val folds for heterogeneity estimation (default 2).
    verbose : bool
        Print diagnostics during fit.
    """

    def __init__(
        self,
        operators,
        centroid_method="auto",
        score_method="v1",
        heterogeneity_threshold=0.5,
        mode="auto",
        n_val_folds=2,
        verbose=True,
    ):
        self.operator_specs = operators
        self.centroid_method = centroid_method
        self.score_method = score_method
        self.het_threshold = heterogeneity_threshold
        self.mode = mode
        self.n_val_folds = n_val_folds
        self.verbose = verbose

        # Fitted state
        self._fisher_pipe = None
        self._fusion_pipe = None
        self._strategy = None       # 'fisher' or 'fusion' or 'blend'
        self._blend_alpha = 0.5     # mixing weight for blend mode
        self._heterogeneity = None  # measured mean |ρ|
        self._pairwise_corr = None  # full correlation matrix
        self._fitted = False

    def _measure_heterogeneity(self, X, y):
        """
        Estimate anomaly heterogeneity by measuring inter-operator
        score correlation on a validation fold.

        Returns
        -------
        mean_abs_corr : float
            Mean absolute Spearman correlation between operator
            anomaly scores. Low = heterogeneous, high = homogeneous.
        corr_matrix : ndarray
            Pairwise correlation matrix.
        """
        # Use a single validation fold for speed
        n_anom = int(y.sum())
        if n_anom < 4 or len(X) < 20:
            # Too few samples — default to fusion (safer)
            return 0.0, np.zeros((len(self.operator_specs), len(self.operator_specs)))

        try:
            skf = StratifiedKFold(n_splits=self.n_val_folds, shuffle=True, random_state=42)
            train_idx, val_idx = next(skf.split(X, y))
        except ValueError:
            return 0.0, np.zeros((len(self.operator_specs), len(self.operator_specs)))

        X_tr, X_val = X[train_idx], X[val_idx]
        y_tr, y_val = y[train_idx], y[val_idx]

        # Fit each operator independently and collect scores on val set
        op_scores = {}
        for name, op in self.operator_specs:
            try:
                pipe = UDLPipeline(
                    operators=[(name, copy.deepcopy(op))],
                    centroid_method=self.centroid_method,
                    projection_method='fisher',
                    score_method=self.score_method,
                )
                pipe.fit(X_tr, y_tr)
                s = pipe.score(X_val)
                if np.std(s) > 1e-12:  # skip degenerate
                    op_scores[name] = s
            except Exception:
                pass

        if len(op_scores) < 2:
            return 0.0, np.zeros((len(self.operator_specs), len(self.operator_specs)))

        # Compute pairwise Spearman correlation
        names = list(op_scores.keys())
        n_ops = len(names)
        corr_matrix = np.eye(n_ops)

        correlations = []
        for i in range(n_ops):
            for j in range(i + 1, n_ops):
                rho, _ = spearmanr(op_scores[names[i]], op_scores[names[j]])
                if np.isnan(rho):
                    rho = 0.0
                corr_matrix[i, j] = rho
                corr_matrix[j, i] = rho
                correlations.append(abs(rho))

        mean_abs_corr = np.mean(correlations) if correlations else 0.0
        return mean_abs_corr, corr_matrix

    def _estimate_blend_alpha(self, X, y):
        """
        Estimate optimal blending weight α between Fisher and RankFusion
        using cross-validation on detection coverage.

        α = 1 → pure Fisher, α = 0 → pure RankFusion
        """
        n_anom = int(y.sum())
        if n_anom < 4:
            return 0.5

        try:
            skf = StratifiedKFold(n_splits=self.n_val_folds, shuffle=True, random_state=42)
        except ValueError:
            return 0.5

        alphas = [0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0]
        alpha_scores = {a: [] for a in alphas}

        for train_idx, val_idx in skf.split(X, y):
            X_tr, X_val = X[train_idx], X[val_idx]
            y_tr, y_val = y[train_idx], y[val_idx]

            # Fit both
            try:
                fp = UDLPipeline(
                    operators=copy.deepcopy(self.operator_specs),
                    centroid_method=self.centroid_method,
                    projection_method='fisher',
                    score_method=self.score_method,
                )
                fp.fit(X_tr, y_tr)
                f_scores = fp.score(X_val)
                f_ranks = f_scores.argsort().argsort() / max(len(f_scores) - 1, 1)
            except Exception:
                f_ranks = None

            try:
                rp = RankFusionPipeline(
                    operators=copy.deepcopy(self.operator_specs),
                    centroid_method=self.centroid_method,
                    score_method=self.score_method,
                    fusion='mean',
                )
                rp.fit(X_tr, y_tr)
                r_scores = rp.score(X_val)
                r_ranks = r_scores.argsort().argsort() / max(len(r_scores) - 1, 1)
            except Exception:
                r_ranks = None

            if f_ranks is None and r_ranks is None:
                continue

            anom_rate = y_val.mean()
            top_k = min(max(anom_rate * 2, 0.05), 0.30)
            anom_idx = np.where(y_val == 1)[0]

            for a in alphas:
                if f_ranks is not None and r_ranks is not None:
                    blended = a * f_ranks + (1 - a) * r_ranks
                elif f_ranks is not None:
                    blended = f_ranks
                else:
                    blended = r_ranks

                threshold = np.percentile(blended, 100 * (1 - top_k))
                caught = np.sum(blended[anom_idx] >= threshold)
                cov = caught / len(anom_idx) if len(anom_idx) > 0 else 0
                alpha_scores[a].append(cov)

        # Pick alpha with best mean coverage
        best_alpha = 0.5
        best_cov = -1
        for a in alphas:
            if alpha_scores[a]:
                mc = np.mean(alpha_scores[a])
                if mc > best_cov:
                    best_cov = mc
                    best_alpha = a

        return best_alpha

    def fit(self, X, y=None):
        """
        Fit the hybrid pipeline.

        1. Measure inter-operator heterogeneity
        2. Select strategy (or learn blend weights)
        3. Fit the chosen pipeline(s) on full training data
        """
        if y is None:
            # No labels → default to fusion (more robust unsupervised)
            self._strategy = 'fusion'
            self._heterogeneity = None
            if self.verbose:
                print("[Hybrid] No labels → defaulting to RankFusion")
        elif self.mode == 'fisher':
            self._strategy = 'fisher'
            self._heterogeneity = None
        elif self.mode == 'fusion':
            self._strategy = 'fusion'
            self._heterogeneity = None
        elif self.mode == 'blend':
            self._heterogeneity, self._pairwise_corr = self._measure_heterogeneity(X, y)
            self._blend_alpha = self._estimate_blend_alpha(X, y)
            self._strategy = 'blend'
            if self.verbose:
                print(f"[Hybrid] Blend mode: alpha={self._blend_alpha:.2f} "
                      f"(heterogeneity={self._heterogeneity:.3f})")
        else:  # auto
            self._heterogeneity, self._pairwise_corr = self._measure_heterogeneity(X, y)
            if self._heterogeneity >= self.het_threshold:
                self._strategy = 'fisher'
            else:
                self._strategy = 'fusion'
            if self.verbose:
                print(f"[Hybrid] Heterogeneity={self._heterogeneity:.3f} "
                      f"(threshold={self.het_threshold}) -> {self._strategy.upper()}")

        # Fit the selected pipeline(s) on full training data
        if self._strategy in ('fisher', 'blend'):
            try:
                self._fisher_pipe = UDLPipeline(
                    operators=copy.deepcopy(self.operator_specs),
                    centroid_method=self.centroid_method,
                    projection_method='fisher',
                    score_method=self.score_method,
                )
                self._fisher_pipe.fit(X, y)
            except Exception as e:
                if self.verbose:
                    print(f"[Hybrid] Fisher fit failed: {e}")
                self._fisher_pipe = None
                if self._strategy == 'fisher':
                    self._strategy = 'fusion'  # fallback

        if self._strategy in ('fusion', 'blend'):
            try:
                self._fusion_pipe = RankFusionPipeline(
                    operators=copy.deepcopy(self.operator_specs),
                    centroid_method=self.centroid_method,
                    score_method=self.score_method,
                    fusion='mean',
                )
                self._fusion_pipe.fit(X, y)
            except Exception as e:
                if self.verbose:
                    print(f"[Hybrid] RankFusion fit failed: {e}")
                self._fusion_pipe = None
                if self._strategy == 'fusion':
                    self._strategy = 'fisher'  # fallback

        self._fitted = True
        return self

    def score(self, X):
        """
        Score using the auto-selected strategy.
        """
        assert self._fitted, "Must call fit() first"

        if self._strategy == 'fisher':
            return self._fisher_pipe.score(X)
        elif self._strategy == 'fusion':
            return self._fusion_pipe.score(X)
        elif self._strategy == 'blend':
            n = len(X)
            f_ranks = r_ranks = None
            if self._fisher_pipe is not None:
                fs = self._fisher_pipe.score(X)
                f_ranks = fs.argsort().argsort() / max(n - 1, 1)
            if self._fusion_pipe is not None:
                rs = self._fusion_pipe.score(X)
                r_ranks = rs.argsort().argsort() / max(n - 1, 1)

            a = self._blend_alpha
            if f_ranks is not None and r_ranks is not None:
                return a * f_ranks + (1 - a) * r_ranks
            elif f_ranks is not None:
                return f_ranks
            elif r_ranks is not None:
                return r_ranks
            else:
                return np.zeros(n)
        else:
            raise ValueError(f"Unknown strategy: {self._strategy}")

    def predict(self, X, threshold=0.5):
        scores = self.score(X)
        t = np.percentile(scores, 100 * (1 - threshold))
        return (scores >= t).astype(int)

    @property
    def strategy(self):
        return self._strategy

    @property
    def heterogeneity(self):
        return self._heterogeneity

    def __repr__(self):
        if not self._fitted:
            return "HybridPipeline(not fitted)"
        return (f"HybridPipeline(strategy='{self._strategy}', "
                f"heterogeneity={self._heterogeneity}, "
                f"n_ops={len(self.operator_specs)})")
