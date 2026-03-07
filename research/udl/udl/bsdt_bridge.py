"""
BSDT Integration Bridge — Connect Blind Spot Decomposition Theory
to the Universal Deviation Law framework.

Maps BSDT's 4 components (C, G, A, T) into UDL law-domain operators
so existing BSDT research results can be directly consumed by
the UDL tensor pipeline.

Usage:
    from udl.bsdt_bridge import BSDTSpectrum
    stack = RepresentationStack(operators=[
        ("bsdt", BSDTSpectrum()),
        ("stat", StatisticalSpectrum()),
        ...
    ])
"""

import numpy as np


class BSDTSpectrum:
    """
    Projects raw features through BSDT's 4-component decomposition:
      C = Camouflage score     (how well anomaly hides in normal space)
      G = Feature gap score    (zero/missing feature patterns)
      A = Activity anomaly     (transaction volume deviation)
      T = Temporal novelty     (distribution shift over time)

    This operator ports the exact logic from adaptive_mfls.py
    into the UDL framework's fit/transform interface.

    FP-Reduction Enhancements (v2)
    ------------------------------
    1. **Percentile-rank normalization**: Converts each component to its
       percentile rank against the normal reference distribution. This
       produces uniform [0,1] scores for normals and pushes only true
       outliers to extreme values, reducing FP from boundary noise.
    2. **Adaptive zero-threshold for G**: Instead of a fixed eps, uses
       the 5th percentile of absolute feature values as the "near-zero"
       threshold, preventing legitimate small values from being flagged.
    3. **Tunable sigmoid inflection for A and T**: The inflection point
       and steepness are fit from the reference data's distribution,
       rather than using hardcoded constants.
    """

    def __init__(self, activity_indices=None, eps=1e-8,
                 percentile_norm=False, adaptive_zero=True,
                 sigmoid_steepness=1.0):
        """
        Parameters
        ----------
        activity_indices : tuple of (idx_sent, idx_recv) or None
            Column indices for activity features.
            If None, uses column magnitudes as proxy.
        eps : float
            Numerical stability.
        percentile_norm : bool
            If True, convert each component to percentile rank against
            the normal reference. Produces well-calibrated [0,1] scores
            and reduces FP from boundary noise (default False).
        adaptive_zero : bool
            If True, use data-driven threshold for the G (feature-gap)
            component instead of fixed eps (default True).
        sigmoid_steepness : float
            Controls how sharply A and T sigmoids transition (default 1.0).
            Higher = sharper (more FP-aggressive).
            Lower = gentler (more FP-conservative).
        """
        self.activity_indices = activity_indices
        self.eps = eps
        self.percentile_norm = percentile_norm
        self.adaptive_zero = adaptive_zero
        self.sigmoid_steepness = sigmoid_steepness

        # Reference statistics (fitted)
        self.mu_normal_ = None
        self.d_max_ = None
        self.ref_mean_ = None
        self.ref_var_ = None
        self.mu_activity_ = None
        self.sigma_activity_ = None
        # Percentile normalization reference
        self._ref_components = None  # (N_ref, 4) sorted for percentile lookup
        # Adaptive zero threshold
        self._zero_threshold = None
        # Fitted sigmoid parameters
        self._activity_inflection = 0.0  # z-score inflection for A
        self._temporal_inflection = 2.0  # Mahalanobis inflection for T
        self._temporal_scale = 0.5       # sigmoid scale for T

    def fit(self, X_ref):
        """
        Compute reference statistics from normal data.

        Parameters
        ----------
        X_ref : ndarray (N, m)
            Reference (normal-class) observations.
        """
        # Camouflage reference
        self.mu_normal_ = X_ref.mean(axis=0)
        dists = np.linalg.norm(X_ref - self.mu_normal_, axis=1)
        self.d_max_ = np.percentile(dists, 99) + self.eps

        # Adaptive zero threshold for G component
        if self.adaptive_zero:
            abs_vals = np.abs(X_ref).ravel()
            abs_vals = abs_vals[abs_vals > 0]  # exclude true zeros
            if len(abs_vals) > 0:
                self._zero_threshold = np.percentile(abs_vals, 5)
            else:
                self._zero_threshold = self.eps
        else:
            self._zero_threshold = self.eps

        # Temporal novelty reference
        self.ref_mean_ = X_ref.mean(axis=0)
        self.ref_var_ = X_ref.var(axis=0) + self.eps

        # Fit sigmoid inflection for T from reference distribution
        diff = X_ref - self.ref_mean_
        mahal_sq = np.sum(diff * diff / self.ref_var_, axis=1)
        mahal_norm = mahal_sq / X_ref.shape[1]
        # Set inflection at 95th percentile of reference Mahalanobis
        # This means <5% of normals will have T > 0.5, reducing FP
        self._temporal_inflection = float(np.percentile(mahal_norm, 95))
        # Scale inversely with spread so transition is proportional
        iqr = float(np.percentile(mahal_norm, 75) - np.percentile(mahal_norm, 25))
        self._temporal_scale = self.sigmoid_steepness / max(iqr, self.eps)

        # Activity anomaly reference
        activity = self._get_activity(X_ref)
        log_activity = np.log1p(activity)
        self.mu_activity_ = log_activity.mean()
        self.sigma_activity_ = max(log_activity.std(), self.eps)
        # Set inflection at 95th percentile of reference activity z-scores
        z_ref = (log_activity - self.mu_activity_) / self.sigma_activity_
        self._activity_inflection = float(np.percentile(z_ref, 95))

        # Compute reference components for percentile normalization
        if self.percentile_norm:
            self._ref_components = np.sort(
                self._compute_raw(X_ref), axis=0
            )  # (N_ref, 4), sorted per column

        return self

    def _compute_raw(self, X):
        """Compute raw (unnormalized) BSDT 4-component vector."""
        N = X.shape[0]
        out = np.zeros((N, 4), dtype=np.float64)

        # C — Camouflage score
        dists = np.linalg.norm(X - self.mu_normal_, axis=1)
        out[:, 0] = 1.0 - np.clip(dists / self.d_max_, 0, 1)

        # G — Feature gap score (with adaptive zero threshold)
        zero_thr = self._zero_threshold if self._zero_threshold is not None else self.eps
        out[:, 1] = (np.abs(X) < zero_thr).sum(axis=1).astype(np.float64) / X.shape[1]

        # A — Activity anomaly score (with fitted inflection)
        activity = self._get_activity(X)
        z = (np.log1p(activity) - self.mu_activity_) / self.sigma_activity_
        out[:, 2] = 1.0 / (1.0 + np.exp(
            -self.sigmoid_steepness * (z - self._activity_inflection)
        ))

        # T — Temporal novelty score (with fitted inflection)
        diff = X - self.ref_mean_
        mahal_sq = np.sum(diff * diff / self.ref_var_, axis=1)
        mahal_norm = mahal_sq / X.shape[1]
        out[:, 3] = 1.0 / (1.0 + np.exp(
            -self._temporal_scale * (mahal_norm - self._temporal_inflection)
        ))

        return out

    def transform(self, X):
        """
        Compute BSDT 4-component vector for each observation.

        Returns
        -------
        components : ndarray (N, 4)
            Columns: [C, G, A, T]
        """
        raw = self._compute_raw(X)

        if self.percentile_norm and self._ref_components is not None:
            # Convert each component to percentile rank against normal ref
            N_ref = self._ref_components.shape[0]
            for c in range(4):
                ranks = np.searchsorted(self._ref_components[:, c], raw[:, c])
                raw[:, c] = ranks.astype(np.float64) / N_ref
            return raw

        return raw

    def _get_activity(self, X):
        """Extract activity proxy from features."""
        if self.activity_indices is not None:
            idx_s, idx_r = self.activity_indices
            return np.abs(X[:, idx_s]) + np.abs(X[:, idx_r]) + self.eps
        else:
            # Proxy: total absolute feature magnitude
            return np.abs(X).sum(axis=1) + self.eps


class BSDTAugmentedStack:
    """
    Convenience: builds a RepresentationStack that includes BSDT
    components as the first law-domain, followed by the standard
    UDL spectra.

    This gives 6 law domains:
      [BSDT(4d) | Stat(5d) | Chaos(3d) | Freq(4d) | Geom(3d) | Exp(10d)]
    """

    @staticmethod
    def build(activity_indices=None, exp_alpha=1.0):
        from .spectra import (
            StatisticalSpectrum,
            ChaosSpectrum,
            SpectralSpectrum,
            GeometricSpectrum,
            ExponentialSpectrum,
        )
        from .stack import RepresentationStack

        operators = [
            ("bsdt", BSDTSpectrum(activity_indices=activity_indices)),
            ("stat", StatisticalSpectrum()),
            ("chaos", ChaosSpectrum()),
            ("freq", SpectralSpectrum()),
            ("geom", GeometricSpectrum()),
            ("exp", ExponentialSpectrum(alpha=exp_alpha)),
        ]
        return RepresentationStack(operators=operators, exp_alpha=exp_alpha)
