"""
Meta-Fusion Pipeline — per-sample rank fusion across diverse strategies.
=========================================================================
Instead of picking ONE winner per dataset, runs multiple complementary
strategies in parallel and rank-averages their per-sample scores.

Lean Design Principle:
  - Only operators that GENERALIZE (minCov > 30% solo)
  - Only operators with low mutual correlation (rho < 0.80)
  - Only strategies that see DIFFERENT anomalies

Based on correlation audit:
  Redundant: Wavelet <-> Phase (rho=0.92) → keep Phase (higher mCov)
  Garbage:   Statistical (0% minCov), Compress (4% minCov)
  Weak:      Exponential, Fourier, BSpline, Rank, Kernel, Dependency
             (all < 30% minCov solo, and high corr with better ops)

Selected operators by coverage + diversity:
  Phase      (mCov=86%, minCov=51%) — best overall solo performer
  Topo       (mCov=78%, minCov=41%) — low corr with everything (~0.10-0.39)
  Legendre   (mCov=75%, minCov=40%) — shuttle specialist
  Geometric  (mCov=75%, minCov=49%) — mammography specialist
  Recon      (mCov=73%, minCov=26%) — moderate but low corr with Phase (0.46)

Meta-fusion strategies (all run, scores rank-averaged):
  S1: Fisher(selected_ops)        — linear projection
  S2: RankFusion(selected_ops)    — per-operator rank average
  S3: QuadSurf(selected_ops)      — polynomial surface (mammography champion)

Usage:
    from udl.meta_fusion import MetaFusionPipeline
    pipe = MetaFusionPipeline()
    pipe.fit(X_train, y_train)
    scores = pipe.score(X_test)
"""

import gc
import copy
import numpy as np
from scipy.stats import rankdata

from .pipeline import UDLPipeline
from .rank_fusion import RankFusionPipeline
from .experimental_spectra import PhaseCurveSpectrum, LegendreBasisSpectrum
from .spectra import GeometricSpectrum, ReconstructionSpectrum
from .new_spectra import TopologicalSpectrum


# ── The lean, non-redundant operator set ──
def default_operators():
    """5 operators selected by correlation audit: high coverage, low mutual correlation."""
    return [
        ("phase",    PhaseCurveSpectrum()),
        ("topo",     TopologicalSpectrum(k=15)),
        ("legendre", LegendreBasisSpectrum(n_degree=6)),
        ("geometric", GeometricSpectrum()),
        ("recon",    ReconstructionSpectrum()),
    ]


class MetaFusionPipeline:
    """
    Per-sample meta-fusion across complementary scoring strategies.

    Fits multiple independent pipelines on the same data, converts each
    to ranks, and averages ranks. No ML at the fusion level — pure
    rank aggregation. Each strategy sees different anomalies; the union
    of their detections maximises coverage.

    Parameters
    ----------
    operators : list or None
        Operator specs. If None, uses the default 5-op lean set.
    strategies : list of str
        Which strategies to fuse. Default: ['fisher', 'fusion', 'quadsurf'].
        Options: 'fisher', 'fusion', 'quadsurf', 'qs_expo', 'signed_lr', 'magnifier'.
    fusion_mode : str
        How to combine strategy ranks: 'mean' (default), 'max', 'softmax'.
    verbose : bool
        Print strategy-level diagnostics.
    """

    STRATEGY_REGISTRY = {
        'fisher':    {'projection_method': 'fisher'},
        'fusion':    {'_is_fusion': True},
        'quadsurf':  {'projection_method': 'fisher', 'mfls_method': 'quadratic'},
        'qs_expo':   {'projection_method': 'fisher', 'mfls_method': 'quadratic_smooth'},
        'signed_lr': {'projection_method': 'fisher', 'mfls_method': 'logistic'},
        'magnifier': {'projection_method': 'fisher', 'magnify': True},
    }

    def __init__(
        self,
        operators=None,
        strategies=None,
        fusion_mode='mean',
        verbose=True,
    ):
        self.operator_specs = operators or default_operators()
        self.strategies = strategies or ['fisher', 'fusion', 'quadsurf']
        self.fusion_mode = fusion_mode
        self.verbose = verbose

        # Fitted state
        self._pipes = {}       # {strategy_name: fitted pipeline}
        self._fitted = False

    def _build(self, strategy_name):
        """Build an unfitted pipeline for a given strategy."""
        cfg = self.STRATEGY_REGISTRY[strategy_name]
        ops = copy.deepcopy(self.operator_specs)

        if cfg.get('_is_fusion'):
            return RankFusionPipeline(
                operators=ops,
                centroid_method='auto',
                score_method='v1',
                fusion='mean',
            )
        else:
            return UDLPipeline(
                operators=ops,
                centroid_method='auto',
                score_method='v1',
                projection_method=cfg.get('projection_method', 'fisher'),
                mfls_method=cfg.get('mfls_method'),
                magnify=cfg.get('magnify', False),
            )

    def fit(self, X, y):
        """Fit all strategy pipelines."""
        self._pipes = {}
        for name in self.strategies:
            if name not in self.STRATEGY_REGISTRY:
                if self.verbose:
                    print(f"  [MetaFusion] Unknown strategy '{name}', skipping")
                continue
            try:
                pipe = self._build(name)
                pipe.fit(X, y)
                self._pipes[name] = pipe
                if self.verbose:
                    print(f"  [MetaFusion] Fitted: {name}")
            except Exception as e:
                if self.verbose:
                    print(f"  [MetaFusion] FAILED: {name} — {e}")
            gc.collect()

        if not self._pipes:
            raise RuntimeError("All strategies failed to fit")

        self._fitted = True
        return self

    def score(self, X):
        """
        Score samples by rank-averaging across all fitted strategies.

        Each strategy produces a score vector → convert to ranks →
        average ranks → final score (higher = more anomalous).
        """
        if not self._fitted:
            raise RuntimeError("MetaFusionPipeline not fitted. Call fit() first.")

        rank_matrix = []
        for name, pipe in self._pipes.items():
            try:
                raw_scores = pipe.score(X)
                ranks = rankdata(raw_scores, method='average')
                rank_matrix.append(ranks)
            except Exception as e:
                if self.verbose:
                    print(f"  [MetaFusion] Score FAILED: {name} — {e}")

        if not rank_matrix:
            raise RuntimeError("All strategies failed to score")

        R = np.column_stack(rank_matrix)

        if self.fusion_mode == 'mean':
            return R.mean(axis=1)
        elif self.fusion_mode == 'max':
            return R.max(axis=1)
        elif self.fusion_mode == 'softmax':
            # Softmax-weighted average (emphasise highest-rank strategies)
            exp_R = np.exp(R / R.shape[0])
            weights = exp_R / exp_R.sum(axis=1, keepdims=True)
            return (R * weights).sum(axis=1)
        else:
            return R.mean(axis=1)

    def score_samples(self, X):
        """Alias for score() — sklearn API compatibility."""
        return self.score(X)

    @property
    def strategy_names(self):
        """Names of successfully fitted strategies."""
        return list(self._pipes.keys())

    @property
    def n_strategies(self):
        return len(self._pipes)

    def __repr__(self):
        status = f"{len(self._pipes)} fitted" if self._fitted else "unfitted"
        return (f"MetaFusionPipeline(strategies={self.strategies}, "
                f"fusion='{self.fusion_mode}', {status})")
