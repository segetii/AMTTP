"""
Law Selection Matrix — Auto-Detect Data Type & Select Optimal Laws
===================================================================
Analyses input data to determine its type (tabular, time-series,
high-dimensional, compositional, etc.) and selects only the
spectrum operators that are mathematically valid for that type.

Usage:
    from udl.law_matrix import DataProfile, select_laws

    profile = DataProfile.detect(X)     # auto-analyse data
    operators = select_laws(profile)     # get valid operator list

Or let the pipeline do it automatically:
    pipe = UDLPipeline(operators='auto')

Law Validity Matrix
-------------------
Each law has boundary conditions — minimum feature count, ordering
requirements, distributional assumptions.  If the data violates a
law's boundary, that law produces noise features that degrade the
classifier.

                         STAT  CHAOS  SPEC  GEOM  RECON  RANK
    Tabular (m<20)        ○      ✗      ✗     ✓      ○     ✓
    Tabular (m≥20)        ○      ✗      ✗     ✓      ✓     ✓
    Time-series (m<20)    ○      ✗      ✗     ✓      ○     ✓
    Time-series (m≥30)    ✓      ✓      ✓     ✓      ✓     ✓
    High-dim (m≥100)      ○      ✗      ✗     ✓      ✓     ✓
    Compositional         ✓      ✗      ✗     ✓      ○     ✓
    Image patches         ○      ✗      ✓     ✓      ✓     ✓
    Signal (waveform)     ✓      ✓      ✓     ✓      ✓     ✓

    ✓ = valid    ○ = marginal (included at reduced trust)    ✗ = noise
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Optional


# ═══════════════════════════════════════════════════════════════════
# LAW BOUNDARY CONDITIONS
# ═══════════════════════════════════════════════════════════════════

# Each law's minimum requirements
LAW_REQUIREMENTS = {
    "stat": {
        "min_features": 5,        # need ≥5 for meaningful entropy/skew/kurtosis
        "min_samples": 30,
        "needs_ordering": False,   # doesn't require temporal ordering
        "needs_composition": True, # best when features are proportional
        "description": "Statistical divergence (entropy, KL, Hellinger, skewness, kurtosis)",
    },
    "chaos": {
        "min_features": 30,       # Lyapunov needs ≥30 time steps
        "min_samples": 50,
        "needs_ordering": True,   # REQUIRES temporal/sequential ordering
        "needs_composition": False,
        "description": "Dynamical invariants (Lyapunov, recurrence, approx. entropy)",
    },
    "phase": {
        "min_features": 3,        # needs ≥3 for consecutive-pair phase space
        "min_samples": 20,
        "needs_ordering": False,  # works on tabular data (all feature pairs)
        "needs_composition": False,
        "description": "Phase-curve interaction (pairwise feature displacement structure)",
    },
    "freq": {
        "min_features": 16,       # FFT needs ≥16 samples for useful resolution
        "min_samples": 30,
        "needs_ordering": True,   # REQUIRES uniformly-sampled signal
        "needs_composition": False,
        "description": "Frequency domain (PSD deviation, spectral entropy, centroid)",
    },
    "geom": {
        "min_features": 2,        # works with any m≥2
        "min_samples": 10,        # needs N_ref ≥ 3m ideally
        "needs_ordering": False,  # universal
        "needs_composition": False,
        "description": "Geometric distance (Mahalanobis, cosine, norm ratio)",
    },
    "recon": {
        "min_features": 8,        # needs m≥8 so rank can capture structure
        "min_samples": 30,
        "needs_ordering": False,
        "needs_composition": False,
        "description": "Off-manifold detection (SVD reconstruction error)",
    },
    "rank": {
        "min_features": 3,        # works with any m≥3
        "min_samples": 100,       # needs stable percentile estimates
        "needs_ordering": False,  # distribution-free, universal
        "needs_composition": False,
        "description": "Rank-order extremity (percentile, tail fraction, IQR)",
    },
}


# ═══════════════════════════════════════════════════════════════════
# DATA TYPE DETECTION
# ═══════════════════════════════════════════════════════════════════

@dataclass
class DataProfile:
    """
    Characterises a dataset to determine which laws apply.

    Attributes
    ----------
    n_samples : int
        Number of observations.
    n_features : int
        Number of features per observation.
    data_type : str
        Detected type: 'tabular', 'short_series', 'time_series',
        'high_dim', 'compositional', 'signal'.
    is_ordered : bool
        Whether features have meaningful sequential ordering.
    is_compositional : bool
        Whether rows sum to a constant (proportions/fractions).
    has_low_rank : bool
        Whether normal data has significant low-rank structure.
    effective_rank : float
        Estimated intrinsic dimensionality (via explained variance).
    feature_ratio : float
        n_features / n_samples — high ratio = curse of dimensionality.
    valid_laws : list of str
        Law names that pass boundary conditions.
    marginal_laws : list of str
        Laws that are technically valid but near their boundary.
    invalid_laws : list of str
        Laws that would produce noise for this data.
    diagnostics : dict
        Raw analysis metrics for debugging.
    """
    n_samples: int = 0
    n_features: int = 0
    data_type: str = "unknown"
    is_ordered: bool = False
    is_compositional: bool = False
    has_low_rank: bool = False
    effective_rank: float = 0.0
    feature_ratio: float = 0.0
    valid_laws: List[str] = field(default_factory=list)
    marginal_laws: List[str] = field(default_factory=list)
    invalid_laws: List[str] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)

    @staticmethod
    def detect(X, ordered=None):
        """
        Auto-detect data profile from a feature matrix.

        Parameters
        ----------
        X : ndarray (N, m)
            Raw feature matrix (typically normal/reference data).
        ordered : bool or None
            Override: True = features are time-ordered,
            False = features are independent columns,
            None = auto-detect.

        Returns
        -------
        DataProfile
        """
        N, m = X.shape
        profile = DataProfile()
        profile.n_samples = N
        profile.n_features = m
        profile.feature_ratio = m / max(N, 1)

        # ── Check if compositional ──
        # Rows that sum to a near-constant are proportional data
        row_sums = np.abs(X).sum(axis=1)
        sum_cv = row_sums.std() / (row_sums.mean() + 1e-10)
        profile.is_compositional = (sum_cv < 0.05) and (m >= 3)

        # ── Check if features are ordered (auto-correlation test) ──
        if ordered is not None:
            profile.is_ordered = ordered
        else:
            profile.is_ordered = _detect_ordering(X) if m >= 10 else False

        # ── Estimate effective rank via SVD ──
        if N >= 5 and m >= 3:
            try:
                X_c = X - X.mean(axis=0)
                _, S, _ = np.linalg.svd(X_c, full_matrices=False)
                var_explained = (S ** 2) / ((S ** 2).sum() + 1e-10)
                cum_var = np.cumsum(var_explained)
                # Effective rank = number of components for 95% variance
                profile.effective_rank = float(np.searchsorted(cum_var, 0.95) + 1)
                profile.has_low_rank = (profile.effective_rank < m * 0.6)
            except Exception:
                profile.effective_rank = float(m)
                profile.has_low_rank = False
        else:
            profile.effective_rank = float(m)
            profile.has_low_rank = False

        # ── Classify data type ──
        if profile.is_compositional:
            profile.data_type = "compositional"
        elif profile.is_ordered and m >= 30:
            profile.data_type = "signal"         # full time-series/waveform
        elif profile.is_ordered and m >= 10:
            profile.data_type = "short_series"   # too short for chaos/freq
        elif m >= 100:
            profile.data_type = "high_dim"
        else:
            profile.data_type = "tabular"

        # ── Store diagnostics ──
        profile.diagnostics = {
            "sum_cv": float(sum_cv),
            "effective_rank": profile.effective_rank,
            "rank_ratio": profile.effective_rank / m,
            "feature_ratio": profile.feature_ratio,
        }

        # ── Apply law boundary checks ──
        profile.valid_laws, profile.marginal_laws, profile.invalid_laws = \
            _check_law_boundaries(profile)

        return profile

    def summary(self):
        """Human-readable summary."""
        lines = [
            f"DataProfile: {self.data_type}",
            f"  Samples: {self.n_samples}, Features: {self.n_features}",
            f"  Ordered: {self.is_ordered}, Compositional: {self.is_compositional}",
            f"  Effective rank: {self.effective_rank:.1f}/{self.n_features} "
            f"(low-rank: {self.has_low_rank})",
            f"  Valid laws:    {self.valid_laws}",
            f"  Marginal laws: {self.marginal_laws}",
            f"  Invalid laws:  {self.invalid_laws}",
        ]
        return "\n".join(lines)


def _detect_ordering(X, n_probe=200):
    """
    Heuristic: if adjacent features are more correlated than random
    pairs, the features likely have sequential ordering.

    Returns True if mean adjacent correlation > 2× mean random correlation.
    """
    N, m = X.shape
    if m < 5:
        return False

    # Sample rows for speed
    rows = X[:min(n_probe, N)]

    # Adjacent feature correlations
    adj_corrs = []
    for j in range(m - 1):
        c = np.corrcoef(rows[:, j], rows[:, j + 1])[0, 1]
        if not np.isnan(c):
            adj_corrs.append(abs(c))

    # Random pair correlations
    rng = np.random.RandomState(42)
    rand_corrs = []
    for _ in range(min(m, 30)):
        i, j = rng.choice(m, 2, replace=False)
        c = np.corrcoef(rows[:, i], rows[:, j])[0, 1]
        if not np.isnan(c):
            rand_corrs.append(abs(c))

    if not adj_corrs or not rand_corrs:
        return False

    mean_adj = np.mean(adj_corrs)
    mean_rand = np.mean(rand_corrs)

    return mean_adj > 2.0 * mean_rand + 0.1


def _check_law_boundaries(profile):
    """
    Apply boundary conditions to each law and classify as
    valid / marginal / invalid.
    """
    valid = []
    marginal = []
    invalid = []

    m = profile.n_features
    N = profile.n_samples

    for law_name, req in LAW_REQUIREMENTS.items():

        # ── Hard boundary: minimum feature count ──
        if m < req["min_features"]:
            invalid.append(law_name)
            continue

        # ── Hard boundary: needs ordering but data is unordered ──
        if req["needs_ordering"] and not profile.is_ordered:
            invalid.append(law_name)
            continue

        # ── Hard boundary: not enough samples ──
        if N < req["min_samples"]:
            invalid.append(law_name)
            continue

        # ── Marginal conditions ──
        is_marginal = False

        # Statistical: marginal on non-compositional data with few features
        if law_name == "stat":
            if not profile.is_compositional and m < 10:
                is_marginal = True

        # Reconstruction: marginal if data is nearly full-rank
        if law_name == "recon":
            if not profile.has_low_rank:
                is_marginal = True

        # Chaos: marginal if features are 30-50 (short for stable Lyapunov)
        if law_name == "chaos":
            if m < 50:
                is_marginal = True

        # Phase: marginal if very low-dim (3-5 features → few pairs)
        if law_name == "phase":
            if m < 5:
                is_marginal = True

        # Spectral: marginal if features are 16-32 (low FFT resolution)
        if law_name == "freq":
            if m < 32:
                is_marginal = True

        if is_marginal:
            marginal.append(law_name)
        else:
            valid.append(law_name)

    return valid, marginal, invalid


# ═══════════════════════════════════════════════════════════════════
# LAW SELECTION
# ═══════════════════════════════════════════════════════════════════

# Pre-defined law combinations per data type
# These are the RECOMMENDED stacks (proven by boundary analysis)
LAW_MATRIX = {
    #                         stat  chaos  phase  freq   geom   recon  rank
    "tabular":               [False, False, True,  False, True,  False, True ],
    "tabular_wide":          [False, False, True,  False, True,  True,  True ],  # m≥20
    "short_series":          [True,  False, True,  False, True,  True,  True ],
    "signal":                [True,  True,  True,  True,  True,  True,  True ],  # full stack: chaos valid here
    "high_dim":              [False, False, True,  False, True,  True,  True ],
    "compositional":         [True,  False, True,  False, True,  False, True ],
}

LAW_NAMES = ["stat", "chaos", "phase", "freq", "geom", "recon", "rank"]


def select_laws(profile, include_marginal=False):
    """
    Select the optimal set of spectrum operators for a data profile.

    Parameters
    ----------
    profile : DataProfile
        Result of DataProfile.detect(X).
    include_marginal : bool
        If True, also include marginal laws (near boundary).
        Default False — only use clearly valid laws.

    Returns
    -------
    operators : list of (name, operator_instance) tuples
        Ready to pass to RepresentationStack(operators=...).
    """
    from .spectra import (
        StatisticalSpectrum, ChaosSpectrum, SpectralSpectrum,
        GeometricSpectrum, ReconstructionSpectrum, RankOrderSpectrum,
    )
    from .experimental_spectra import PhaseCurveSpectrum

    OPERATOR_MAP = {
        "stat":  lambda: StatisticalSpectrum(),
        "chaos": lambda: ChaosSpectrum(),
        "phase": lambda: PhaseCurveSpectrum(),
        "freq":  lambda: SpectralSpectrum(),
        "geom":  lambda: GeometricSpectrum(),
        "recon": lambda: ReconstructionSpectrum(),
        "rank":  lambda: RankOrderSpectrum(),
    }

    # Determine which laws to include
    active = set(profile.valid_laws)
    if include_marginal:
        active |= set(profile.marginal_laws)

    # Build operator list in canonical order
    operators = []
    for name in LAW_NAMES:
        if name in active:
            operators.append((name, OPERATOR_MAP[name]()))

    # Safety: always include at least geometric + rank
    active_names = {n for n, _ in operators}
    if "geom" not in active_names:
        operators.append(("geom", OPERATOR_MAP["geom"]()))
    if "rank" not in active_names and profile.n_samples >= 100:
        operators.append(("rank", OPERATOR_MAP["rank"]()))

    return operators


def get_law_matrix_table():
    """
    Return the full law matrix as a formatted string for display.
    """
    header = f"{'Data Type':<20} {'STAT':>5} {'CHAOS':>6} {'PHASE':>6} {'FREQ':>5} {'GEOM':>5} {'RECON':>6} {'RANK':>5} │ {'Min m':>5} {'Ordering':>9}"
    lines = [header, "─" * len(header)]

    type_info = {
        "tabular":        {"min_m": "<20",  "ordering": "No"},
        "tabular_wide":   {"min_m": "≥20",  "ordering": "No"},
        "short_series":   {"min_m": "10-29","ordering": "Yes"},
        "signal":         {"min_m": "≥30",  "ordering": "Yes"},
        "high_dim":       {"min_m": "≥100", "ordering": "No"},
        "compositional":  {"min_m": "≥5",   "ordering": "No"},
    }

    for dtype, flags in LAW_MATRIX.items():
        info = type_info[dtype]
        row = f"{dtype:<20}"
        for f in flags:
            row += f"{'  ✓  ' if f else '  ✗  ':>6}"
        row += f" │ {info['min_m']:>5} {info['ordering']:>9}"
        lines.append(row)

    # Per-law boundary line
    lines.append("")
    lines.append("Law Boundaries:")
    for name, req in LAW_REQUIREMENTS.items():
        lines.append(f"  {name:<6}: min_features={req['min_features']}, "
                     f"min_samples={req['min_samples']}, "
                     f"ordered={req['needs_ordering']}")

    return "\n".join(lines)
