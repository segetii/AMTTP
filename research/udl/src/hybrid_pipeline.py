"""
Hybrid Pipeline — Adaptive Best-of-All Selection
==================================================
Cross-validates ALL available pipeline configurations and picks the
one that maximises anomaly COVERAGE (not AUC).

Candidate strategies evaluated on each CV fold:
  1. Fisher LDA projection    (linear discriminant — best for homogeneous anomalies)
  2. QDA projection           (quadratic, per-class covariance — captures non-linear boundaries)
  3. QDA-magnified            (QDA + DimensionMagnifier pre-processing)
  4. RankFusion (mean)        (rank-average of per-operator scores — best for heterogeneous)

Then optionally blends the CV-best projection with RankFusion via learned alpha.

Modes:
  'auto'  — pick the single best candidate by CV coverage (default)
  'blend' — pick best candidate + learn optimal alpha blend with RankFusion
  'fisher'/'qda'/'qda-magnified'/'fusion' — force a specific strategy

Usage:
    from udl.hybrid_pipeline import HybridPipeline

    pipe = HybridPipeline(operators=[...])
    pipe.fit(X_train, y_train)
    scores = pipe.score(X_test)
"""

import gc
import copy
import warnings
import numpy as np
from sklearn.model_selection import StratifiedKFold

from .pipeline import UDLPipeline
from .rank_fusion import RankFusionPipeline

# All projection-based strategies to compete
CANDIDATE_PROJECTIONS = ['fisher', 'qda', 'qda-magnified']


class HybridPipeline:
    """
    Adaptive anomaly detection that CV-competes Fisher, QDA,
    QDA-magnified, and RankFusion on coverage, then picks the best.
    """

    def __init__(
        self,
        operators,
        centroid_method="auto",
        score_method="v1",
        heterogeneity_threshold=0.5,  # kept for backwards compat
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
        self._best_pipe = None       # winning pipeline object
        self._fusion_pipe = None     # RankFusion (for blend mode)
        self._strategy = None        # winning strategy name
        self._blend_alpha = None     # blending weight (blend mode only)
        self._best_proj = None       # best projection method (blend mode)
        self._cv_results = {}        # {strategy: mean_coverage}
        self._fitted = False

    # ------------------------------------------------------------------
    #  Coverage helper
    # ------------------------------------------------------------------
    @staticmethod
    def _coverage(scores, y, top_k):
        """Fraction of true anomalies in the top-k% of scores."""
        anom_idx = np.where(y == 1)[0]
        if len(anom_idx) == 0:
            return 0.0
        threshold = np.percentile(scores, 100 * (1 - top_k))
        return float(np.sum(scores[anom_idx] >= threshold)) / len(anom_idx)

    # ------------------------------------------------------------------
    #  Build a pipeline for a given strategy
    # ------------------------------------------------------------------
    def _build(self, strategy, ops):
        """Return a pipeline (not yet fitted) for the given strategy."""
        if strategy == 'fusion':
            return RankFusionPipeline(
                operators=ops,
                centroid_method=self.centroid_method,
                score_method=self.score_method,
                fusion='mean',
            )
        else:
            # Fisher, QDA, or QDA-magnified
            magnify = strategy == 'qda-magnified'
            return UDLPipeline(
                operators=ops,
                centroid_method=self.centroid_method,
                projection_method=strategy,
                score_method=self.score_method,
                magnify=magnify,
            )

    # ------------------------------------------------------------------
    #  CV-compete all strategies
    # ------------------------------------------------------------------
    def _cv_select(self, X, y):
        """
        Cross-validate all candidate strategies and return
        {strategy: mean_coverage}.
        """
        n_anom = int(y.sum())
        if n_anom < 4 or len(X) < 20:
            return {'fusion': 1.0}

        try:
            skf = StratifiedKFold(
                n_splits=self.n_val_folds, shuffle=True, random_state=42
            )
            folds = list(skf.split(X, y))
        except ValueError:
            return {'fusion': 1.0}

        candidates = list(CANDIDATE_PROJECTIONS) + ['fusion']
        fold_scores = {c: [] for c in candidates}

        for train_idx, val_idx in folds:
            X_tr, X_val = X[train_idx], X[val_idx]
            y_tr, y_val = y[train_idx], y[val_idx]

            anom_rate = y_val.mean()
            top_k = min(max(anom_rate * 2, 0.05), 0.30)

            for strat in candidates:
                try:
                    pipe = self._build(
                        strat, copy.deepcopy(self.operator_specs)
                    )
                    pipe.fit(X_tr, y_tr)
                    s = pipe.score(X_val)
                    cov = self._coverage(s, y_val, top_k)
                    fold_scores[strat].append(cov)
                except Exception:
                    fold_scores[strat].append(0.0)
                finally:
                    gc.collect()

        results = {}
        for strat in candidates:
            if fold_scores[strat]:
                results[strat] = float(np.mean(fold_scores[strat]))
            else:
                results[strat] = 0.0

        return results

    # ------------------------------------------------------------------
    #  Blend: CV-learn optimal alpha (best proj + fusion)
    # ------------------------------------------------------------------
    def _cv_blend(self, X, y, best_proj):
        """
        Learn optimal alpha between a projection method and RankFusion.

        alpha=1 -> pure projection, alpha=0 -> pure RankFusion
        """
        n_anom = int(y.sum())
        if n_anom < 4:
            return 0.5

        try:
            skf = StratifiedKFold(
                n_splits=self.n_val_folds, shuffle=True, random_state=42
            )
            folds = list(skf.split(X, y))
        except ValueError:
            return 0.5

        alphas = [0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0]
        alpha_covs = {a: [] for a in alphas}

        for train_idx, val_idx in folds:
            X_tr, X_val = X[train_idx], X[val_idx]
            y_tr, y_val = y[train_idx], y[val_idx]

            anom_rate = y_val.mean()
            top_k = min(max(anom_rate * 2, 0.05), 0.30)

            # Fit projection pipeline
            proj_ranks = None
            try:
                pp = self._build(
                    best_proj, copy.deepcopy(self.operator_specs)
                )
                pp.fit(X_tr, y_tr)
                ps = pp.score(X_val)
                proj_ranks = ps.argsort().argsort() / max(len(ps) - 1, 1)
            except Exception:
                pass
            finally:
                gc.collect()

            # Fit RankFusion
            fuse_ranks = None
            try:
                fp = self._build(
                    'fusion', copy.deepcopy(self.operator_specs)
                )
                fp.fit(X_tr, y_tr)
                fs = fp.score(X_val)
                fuse_ranks = fs.argsort().argsort() / max(len(fs) - 1, 1)
            except Exception:
                pass
            finally:
                gc.collect()

            if proj_ranks is None and fuse_ranks is None:
                continue

            anom_idx = np.where(y_val == 1)[0]
            for a in alphas:
                if proj_ranks is not None and fuse_ranks is not None:
                    blended = a * proj_ranks + (1 - a) * fuse_ranks
                elif proj_ranks is not None:
                    blended = proj_ranks
                else:
                    blended = fuse_ranks
                cov = self._coverage(blended, y_val, top_k)
                alpha_covs[a].append(cov)

        best_alpha = 0.5
        best_cov = -1
        for a in alphas:
            if alpha_covs[a]:
                mc = np.mean(alpha_covs[a])
                if mc > best_cov:
                    best_cov = mc
                    best_alpha = a

        return best_alpha

    # ------------------------------------------------------------------
    #  Fit
    # ------------------------------------------------------------------
    def fit(self, X, y=None):
        """
        Fit the hybrid pipeline.

        1. CV-compete Fisher / QDA / QDA-magnified / RankFusion on coverage
        2. Select best (or learn blend weights)
        3. Fit the chosen pipeline(s) on full training data
        """
        # -- Forced modes --
        if y is None:
            self._strategy = 'fusion'
            if self.verbose:
                print("[Hybrid] No labels -> defaulting to RankFusion")

        elif self.mode in CANDIDATE_PROJECTIONS or self.mode == 'fusion':
            self._strategy = self.mode

        elif self.mode in ('auto', 'blend'):
            # -- CV-compete all strategies --
            self._cv_results = self._cv_select(X, y)

            if self.verbose:
                print("[Hybrid] CV coverage results:")
                for strat, cov in sorted(
                    self._cv_results.items(), key=lambda x: -x[1]
                ):
                    print(f"  {strat:20s} {cov*100:.1f}%")

            if self.mode == 'auto':
                self._strategy = max(
                    self._cv_results, key=self._cv_results.get
                )
                if self.verbose:
                    print(f"[Hybrid] Auto-selected: {self._strategy.upper()}")

            else:  # blend
                # Best projection method (not fusion)
                proj_results = {
                    k: v
                    for k, v in self._cv_results.items()
                    if k != 'fusion'
                }
                self._best_proj = (
                    max(proj_results, key=proj_results.get)
                    if proj_results
                    else 'fisher'
                )
                self._blend_alpha = self._cv_blend(X, y, self._best_proj)
                self._strategy = 'blend'

                if self.verbose:
                    print(
                        f"[Hybrid] Blend: {self._best_proj} x "
                        f"alpha={self._blend_alpha:.2f} + "
                        f"fusion x {1-self._blend_alpha:.2f}"
                    )
        else:
            raise ValueError(f"Unknown mode: {self.mode}")

        # -- Fit final pipeline(s) on full training data --
        if self._strategy == 'blend':
            try:
                self._best_pipe = self._build(
                    self._best_proj, copy.deepcopy(self.operator_specs)
                )
                self._best_pipe.fit(X, y)
            except Exception as e:
                if self.verbose:
                    print(f"[Hybrid] {self._best_proj} fit failed: {e}")
                self._best_pipe = None

            try:
                self._fusion_pipe = self._build(
                    'fusion', copy.deepcopy(self.operator_specs)
                )
                self._fusion_pipe.fit(X, y)
            except Exception as e:
                if self.verbose:
                    print(f"[Hybrid] Fusion fit failed: {e}")
                self._fusion_pipe = None

            # Fallback
            if self._best_pipe is None and self._fusion_pipe is not None:
                self._strategy = 'fusion'
                self._best_pipe = self._fusion_pipe
            elif self._best_pipe is not None and self._fusion_pipe is None:
                self._strategy = self._best_proj
        else:
            try:
                self._best_pipe = self._build(
                    self._strategy, copy.deepcopy(self.operator_specs)
                )
                self._best_pipe.fit(X, y)
            except Exception as e:
                if self.verbose:
                    print(
                        f"[Hybrid] {self._strategy} failed: {e}, "
                        f"trying fusion fallback"
                    )
                self._strategy = 'fusion'
                self._best_pipe = self._build(
                    'fusion', copy.deepcopy(self.operator_specs)
                )
                self._best_pipe.fit(X, y)

        self._fitted = True
        return self

    # ------------------------------------------------------------------
    #  Score
    # ------------------------------------------------------------------
    def score(self, X):
        """Score using the auto-selected strategy."""
        assert self._fitted, "Must call fit() first"

        if self._strategy == 'blend':
            n = len(X)
            proj_ranks = fuse_ranks = None

            if self._best_pipe is not None:
                ps = self._best_pipe.score(X)
                proj_ranks = ps.argsort().argsort() / max(n - 1, 1)
            if self._fusion_pipe is not None:
                fs = self._fusion_pipe.score(X)
                fuse_ranks = fs.argsort().argsort() / max(n - 1, 1)

            a = self._blend_alpha
            if proj_ranks is not None and fuse_ranks is not None:
                return a * proj_ranks + (1 - a) * fuse_ranks
            elif proj_ranks is not None:
                return proj_ranks
            elif fuse_ranks is not None:
                return fuse_ranks
            else:
                return np.zeros(n)
        else:
            return self._best_pipe.score(X)

    def score_samples(self, X):
        """Alias for score()."""
        return self.score(X)

    def predict(self, X, threshold=0.5):
        scores = self.score(X)
        t = np.percentile(scores, 100 * (1 - threshold))
        return (scores >= t).astype(int)

    @property
    def strategy(self):
        return self._strategy

    @property
    def cv_results(self):
        return self._cv_results

    def __repr__(self):
        if not self._fitted:
            return "HybridPipeline(not fitted)"
        return (
            f"HybridPipeline(strategy='{self._strategy}', "
            f"cv={self._cv_results}, "
            f"n_ops={len(self.operator_specs)})"
        )
