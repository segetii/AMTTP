"""
Rank-Fusion Pipeline — Coverage-Optimal Anomaly Detection
==========================================================
Runs each spectrum operator as an independent mini-pipeline
and fuses their scores via rank-averaging.

Why this beats Fisher pipeline for coverage:
  - Fisher projection compresses all operators into 1D, losing
    minority signals from operators with anti-correlated scores.
  - Rank fusion preserves each operator's unique detections because
    it never mixes the raw score dimensions.

Evidence (mammography dataset, 78 test anomalies):
  Fisher pipeline  → 52.6% coverage (41/78 caught)
  Mean-rank fusion → 65.4% coverage (51/78 caught)
  Theoretical max  → 69.2% coverage (54/78 detectable)

Usage:
    from udl.rank_fusion import RankFusionPipeline
    from udl.experimental_spectra import PhaseCurveSpectrum
    from udl.new_spectra import TopologicalSpectrum, KernelRKHSSpectrum
    from udl.spectra import RankOrderSpectrum

    pipe = RankFusionPipeline(operators=[
        ("phase", PhaseCurveSpectrum()),
        ("topo", TopologicalSpectrum(k=15)),
        ("kernel", KernelRKHSSpectrum()),
        ("rank", RankOrderSpectrum()),
    ])
    pipe.fit(X_train, y_train)
    scores = pipe.score(X_test)
"""

import copy
import numpy as np
from .pipeline import UDLPipeline


class RankFusionPipeline:
    """
    Multi-operator anomaly detection via rank fusion.

    Each operator runs through its own UDLPipeline with independent
    centroid estimation, tensor construction, and scoring. Final scores
    are rank-normalized per operator and averaged.

    Parameters
    ----------
    operators : list of (name, operator) tuples
        Spectrum operators to fuse. Each gets its own pipeline.
    centroid_method : str
        Centroid method for individual pipelines (default 'auto').
    score_method : str
        Score method for individual pipelines (default 'v1').
    fusion : str
        How to combine rank-normalized scores:
        'mean' — average ranks (best overall)
        'softmax' — log-sum-exp of ranks (smooth max)
        'top2' — average of top-2 ranks per sample
    """

    def __init__(
        self,
        operators,
        centroid_method="auto",
        score_method="v1",
        fusion="mean",
    ):
        self.operator_specs = operators  # [(name, op), ...]
        self.centroid_method = centroid_method
        self.score_method = score_method
        self.fusion = fusion
        self._pipelines = {}
        self._fitted = False

    def fit(self, X, y=None):
        """
        Fit independent pipeline per operator.
        """
        self._pipelines = {}
        for name, op in self.operator_specs:
            pipe = UDLPipeline(
                operators=[(name, copy.deepcopy(op))],
                centroid_method=self.centroid_method,
                projection_method='fisher',
                score_method=self.score_method,
            )
            try:
                pipe.fit(X, y)
                self._pipelines[name] = pipe
            except Exception as e:
                print(f"  [RankFusion] operator '{name}' failed to fit: {e}")
        self._fitted = True
        return self

    def score(self, X):
        """
        Compute rank-fused anomaly scores.

        Returns
        -------
        scores : ndarray (N,) — higher = more anomalous
        """
        assert self._fitted, "Must call fit() first"
        assert self._pipelines, "No operators successfully fitted"

        n = len(X)
        rank_matrix = []

        for name, pipe in self._pipelines.items():
            try:
                s = pipe.score(X)
                # Rank-normalize to [0, 1]
                ranks = s.argsort().argsort() / (n - 1) if n > 1 else s
                rank_matrix.append(ranks)
            except Exception as e:
                print(f"  [RankFusion] operator '{name}' score failed: {e}")

        if not rank_matrix:
            return np.zeros(n)

        R = np.array(rank_matrix)  # shape (n_ops, n_samples)

        if self.fusion == "mean":
            return R.mean(axis=0)
        elif self.fusion == "softmax":
            return np.log(np.sum(np.exp(R * 5), axis=0))
        elif self.fusion == "top2":
            k = min(2, len(R))
            return np.sort(R, axis=0)[-k:].mean(axis=0)
        else:
            return R.mean(axis=0)

    def predict(self, X, threshold=0.5):
        """
        Binary anomaly prediction based on rank-fused score.

        Parameters
        ----------
        threshold : float
            Score quantile threshold (default 0.5 = median split).
        """
        scores = self.score(X)
        t = np.percentile(scores, 100 * (1 - threshold))
        return (scores >= t).astype(int)

    def score_decomposition(self, X):
        """
        Return per-operator ranked scores for analysis.

        Returns
        -------
        dict[str, ndarray] — operator name → rank-normalized scores
        """
        assert self._fitted
        n = len(X)
        decomp = {}
        for name, pipe in self._pipelines.items():
            try:
                s = pipe.score(X)
                decomp[name] = s.argsort().argsort() / (n - 1) if n > 1 else s
            except:
                pass
        return decomp

    @property
    def n_operators(self):
        return len(self._pipelines)

    @property
    def operator_names(self):
        return list(self._pipelines.keys())

    def __repr__(self):
        ops = ", ".join(self.operator_names) if self._fitted else "not fitted"
        return f"RankFusionPipeline(fusion='{self.fusion}', ops=[{ops}])"
