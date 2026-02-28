"""
state_matrix.py  (v2 - real FDIC call report data)
===================================================
Builds the joint state matrix  X(t) ? ?^{N ? d}  directly from FDIC call
report filings - no synthetic loading matrix, no researcher-chosen weights.

Data source
-----------
FDIC Statistics on Depository Institutions (SDI) public API.
N = 7 FDIC-classified institution types (SPECGRP 1-7).
d = 6 features: 5 official call-report ratios + 1 FRED yield-curve factor.

Feature definitions (CAMELS-adjacent, standard supervisory metrics):
    f0  loan_to_asset  = LNLSNET / ASSET
    f1  equity_ratio   = EQ      / ASSET
    f2  npl_ratio      = NCLNLS  / LNLSNET
    f3  roa            = NETINC  / ASSET
    f4  funding_cost   = INTEXP  / LNLSNET
    f5  yield_slope    = T10Y2Y from FRED  (common factor)

Normal-period: 1994-Q1 through 2003-Q4 (post-S&L resolution, pre-boom).
"""

from __future__ import annotations
import numpy as np
import pandas as pd

try:
    from .fdic_loader import compute_sector_features, build_panel, FEATURE_NAMES
except ImportError:
    from fdic_loader import compute_sector_features, build_panel, FEATURE_NAMES

# ?????????????????????????????????????????????????????????????????????????????
# Normal-period: post-S&L-resolution quiet decade, pre-boom
# (FIRREA 1989 resolution substantially complete by 1993)
# ?????????????????????????????????????????????????????????????????????????????
NORMAL_START = "1994-01-01"
NORMAL_END   = "2003-12-31"


def build_state_matrix_fdic(
    fdic_df: pd.DataFrame,
    fred_slope: pd.Series,
) -> tuple[np.ndarray, pd.DatetimeIndex, list[str]]:
    """
    Build X(t) ? ?^{T ? N ? d} directly from FDIC call-report data.

    Parameters
    ----------
    fdic_df    : fetch_fdic_specgrp() result - MultiIndex (date, SPECGRP)
    fred_slope : FRED T10Y2Y quarterly series

    Returns
    -------
    X       : np.ndarray (T, N, d)  - raw, unstandardised
    dates   : pd.DatetimeIndex length T
    sectors : list[str] length N
    """
    sector_features = compute_sector_features(fdic_df, fred_slope)
    X, dates, sectors = build_panel(sector_features)
    return X, dates, sectors


def standardise_panel(
    X: np.ndarray,
    X_ref: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Standardise X feature-by-feature using reference-period statistics.

    If X_ref is None, uses the full panel (in-sample, for exploration only).
    For valid inference, always pass X_ref = normal-period slice, so
    deviations are measured against the documented pre-boom benchmark.

    Returns  (X_std, mu, sigma)  - sigma has shape (d,).
    """
    src = X_ref if X_ref is not None else X
    flat  = src.reshape(-1, src.shape[-1])
    mu    = np.nanmean(flat, axis=0)
    sigma = np.nanstd(flat,  axis=0) + 1e-10
    X_std = (X - mu[None, None, :]) / sigma[None, None, :]
    return X_std, mu, sigma


def get_normal_period(
    X: np.ndarray,
    dates: pd.DatetimeIndex,
    start: str = NORMAL_START,
    end:   str = NORMAL_END,
) -> tuple[np.ndarray, pd.DatetimeIndex]:
    """Extract the normal reference period from X."""
    mask = (dates >= start) & (dates <= end)
    return X[mask], dates[mask]
