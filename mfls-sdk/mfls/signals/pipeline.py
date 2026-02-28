"""
High-level MFLS signal pipeline.

Orchestrates: data loading → standardisation → network estimation →
BSDT fitting → signal computation → evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class PanelData:
    """Standardised panel data ready for MFLS processing."""
    X_raw: np.ndarray               # (T, N, d) original
    X_std: np.ndarray               # (T, N, d) z-scored on normal period
    dates: pd.DatetimeIndex
    names: list[str]                 # institution names
    feature_names: list[str]
    mu: np.ndarray                   # (d,) normal-period mean
    sigma: np.ndarray                # (d,) normal-period std
    normal_mask: np.ndarray          # (T,) bool


@dataclass
class MFLSResult:
    """Complete MFLS pipeline output."""
    signal: np.ndarray               # (T,) MFLS detection signal
    dates: pd.DatetimeIndex
    auroc: Optional[float] = None
    auroc_ci: Optional[Tuple[float, float]] = None
    gfc_lead_quarters: Optional[int] = None
    hit_rate: Optional[float] = None
    false_alarm_rate: Optional[float] = None
    threshold: Optional[float] = None
    ccyb_bps: Optional[np.ndarray] = None
    peak_ccyb: Optional[float] = None
    spectral_radius: Optional[float] = None
    pct_supercritical: Optional[float] = None
    causality_results: Optional[Dict] = None
    bsdt_channels: Optional[object] = None  # BSDTChannels


@dataclass
class HerdingResult:
    """Herding / convergent behaviour detection."""
    temporal_novelty: np.ndarray     # (T,) delta_T signal
    herding_score: np.ndarray        # (T,) inverted: low novelty = high herding
    dates: pd.DatetimeIndex
    signed_lr_weights: Optional[Dict[str, float]] = None
    beta_delta_T: Optional[float] = None


def standardise_panel(
    X: np.ndarray,
    dates: pd.DatetimeIndex,
    normal_start: str,
    normal_end: str,
    names: list[str],
    feature_names: list[str],
) -> PanelData:
    """
    Z-score standardise on a normal (calibration) period.

    Parameters
    ----------
    X : ndarray (T, N, d)
    dates : DatetimeIndex
    normal_start, normal_end : str — e.g. "1994-01-01", "2003-12-31"
    names : list of institution names
    feature_names : list of feature names

    Returns
    -------
    PanelData
    """
    mask = (dates >= pd.Timestamp(normal_start)) & (dates <= pd.Timestamp(normal_end))
    X_ref = X[mask].reshape(-1, X.shape[-1])
    mu = X_ref.mean(axis=0)
    sigma = X_ref.std(axis=0) + 1e-10

    X_std = (X - mu) / sigma

    return PanelData(
        X_raw=X,
        X_std=X_std,
        dates=dates,
        names=names,
        feature_names=feature_names,
        mu=mu,
        sigma=sigma,
        normal_mask=mask,
    )
