"""
Representation Stack — Multi-Spectrum Feature Builder
======================================================
Composes spectrum operators into a single transformation pipeline:
  raw features → [Φ_stat | Φ_chaos | Φ_freq | Φ_geom | Φ_exp] → R ∈ ℝ^D

The stack handles:
  - fit() on reference data to calibrate all operators
  - transform() to project any data into unified representation space
  - Tracking of per-law dimensionality for downstream tensor construction
"""

import numpy as np
from .spectra import (
    StatisticalSpectrum,
    ChaosSpectrum,
    SpectralSpectrum,
    GeometricSpectrum,
    ExponentialSpectrum,
    ReconstructionSpectrum,
    RankOrderSpectrum,
)


class RepresentationStack:
    """
    Ordered stack of spectrum projection operators.

    By default, includes all 5 law-domain operators.
    Custom stacks can be built by passing a subset or alternative operators.

    Applies Z-score standardisation to raw input before projection.
    """

    def __init__(self, operators=None, exp_alpha=1.0, standardize=True,
                 include_marginal=False):
        """
        Parameters
        ----------
        operators : list of (name, instance) tuples, 'auto', or None
            If None, builds the default 6-operator stack (all laws).
            If 'auto', auto-selects valid laws based on data shape
            during fit() using the law boundary matrix.
        exp_alpha : float
            Amplification factor for ExponentialSpectrum.
        standardize : bool
            Whether to Z-standardize raw input before projection.
        include_marginal : bool
            When operators='auto', whether to include marginal laws
            (near boundary). Default False = only clearly valid laws.
        """
        self._auto_select = (operators == "auto")
        self._include_marginal = include_marginal
        self._data_profile = None

        if operators is not None and operators != "auto":
            self.operators = operators
        elif operators == "auto":
            # Will be populated during fit()
            self.operators = None
        else:
            self.operators = [
                ("stat", StatisticalSpectrum()),
                ("chaos", ChaosSpectrum()),
                ("freq", SpectralSpectrum()),
                ("geom", GeometricSpectrum()),
                ("recon", ReconstructionSpectrum()),
                ("rank", RankOrderSpectrum()),
            ]
        self.standardize = standardize
        self._input_mu = None
        self._input_sigma = None
        self.law_dims_ = None
        self.law_names_ = None
        self._fitted = False

    def fit(self, X_ref):
        """
        Fit all operators on reference (normal) data.

        Parameters
        ----------
        X_ref : ndarray (N, m)
            Raw feature matrix of normal observations.
        """
        # ── Auto-select laws if requested ──
        if self._auto_select and self.operators is None:
            from .law_matrix import DataProfile, select_laws
            self._data_profile = DataProfile.detect(X_ref)
            self.operators = select_laws(
                self._data_profile,
                include_marginal=self._include_marginal,
            )

        if self.standardize:
            self._input_mu = X_ref.mean(axis=0)
            self._input_sigma = X_ref.std(axis=0) + 1e-10
            X_ref = (X_ref - self._input_mu) / self._input_sigma

        dims = []
        names = []
        for name, op in self.operators:
            op.fit(X_ref)
            out = op.transform(X_ref[:1])  # probe output dim
            dims.append(out.shape[1])
            names.append(name)

        self.law_dims_ = dims
        self.law_names_ = names
        self._fitted = True
        return self

    def transform(self, X):
        """
        Project raw features through all spectrum operators.

        Returns
        -------
        R : ndarray (N, D_total)
            Concatenated representation across all law domains.
        """
        if not self._fitted:
            raise RuntimeError("Call fit() first")

        if self.standardize and self._input_mu is not None:
            X = (X - self._input_mu) / self._input_sigma

        blocks = []
        for name, op in self.operators:
            blocks.append(op.transform(X))

        return np.hstack(blocks)

    def fit_transform(self, X_ref):
        """Convenience: fit on X_ref, then transform it."""
        self.fit(X_ref)
        return self.transform(X_ref)

    @property
    def total_dim(self):
        """Total output dimensionality."""
        return sum(self.law_dims_) if self.law_dims_ else 0

    def __repr__(self):
        ops = [n for n, _ in self.operators]
        return f"RepresentationStack(operators={ops}, D={self.total_dim})"
