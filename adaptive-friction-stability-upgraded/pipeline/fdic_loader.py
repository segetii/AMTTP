"""
fdic_loader.py
==============
Fetches actual FDIC call report data from the FDIC Statistics on Depository
Institutions (SDI) public REST API.

Endpoint: https://banks.data.fdic.gov/api/financials
No API key required.  Data is public regulatory-filing data.

Returns quarterly aggregate financial ratios for 7 FDIC institution-type
categories (SPECGRP 1-7), giving a real T × N × d panel with:
    N = 7 real institution types
    d = 6 features: all derived from official call report filings

Feature definitions (all defensible CAMELS-adjacent metrics):
    f0  loan_to_asset    = LNLSNET / ASSET          (leverage proxy)
    f1  equity_ratio     = EQ      / ASSET          (capital adequacy)
    f2  npl_ratio        = NCLNLS  / LNLSNET        (credit stress)
    f3  roa              = NETINC  / ASSET           (profitability)
    f4  funding_cost     = INTEXP  / LNLSNET        (interest cost per loan $)
    f5  yield_slope      = T10Y2Y  (FRED)            (common market factor)

SPECGRP sector mapping (FDIC/OCC institutional classification):
    1 – Mutual savings banks (depositor-owned S&Ls)
    2 – Stock savings banks  (shareholder-owned savings)
    3 – State commercial banks, non-Fed-member
    4 – National commercial banks (OCC-chartered)
    5 – Federal savings associations (OTS/OCC)
    6 – State savings associations
    7 – Foreign-chartered institutions (US branches/agencies)

No researcher-chosen weights or heuristic adjustments anywhere in this file.
"""

from __future__ import annotations
import json
import pickle
import time
import warnings
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlencode
from urllib.error import URLError

import numpy as np
import pandas as pd

FDIC_BASE   = "https://banks.data.fdic.gov/api/financials"
CACHE_DIR   = Path(__file__).parent / "fred_cache"
CACHE_FILE  = CACHE_DIR / "fdic_specgrp_quarterly.pkl"

# FDIC SPECGRP codes and human labels
SPECGRP_MAP: dict[int, str] = {
    1: "Mutual Savings Banks",
    2: "Stock Savings Banks",
    3: "State Commercial Banks",
    4: "National Commercial Banks",
    5: "Federal Savings Associations",
    6: "State Savings Associations",
    7: "Foreign Institution Branches",
}

FDIC_FIELDS = ["REPDTE", "SPECGRP", "ASSET", "LNLSNET",
               "EQ", "NETINC", "INTINC", "INTEXP", "NCLNLS"]

FEATURE_NAMES = [
    "loan_to_asset",    # f0
    "equity_ratio",     # f1
    "npl_ratio",        # f2
    "roa",              # f3
    "funding_cost",     # f4
    "yield_slope",      # f5  (filled from FRED later)
]


def _fdic_api_call(params: dict, verbose: bool = False) -> list[dict]:
    """
    Single page call to the FDIC financials endpoint.
    Returns the 'data' list from the JSON response.
    """
    url = FDIC_BASE + "?" + urlencode(params)
    if verbose:
        print(f"  [fdic] GET {url[:100]}...")
    try:
        with urlopen(url, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload.get("data", [])
    except URLError as e:
        warnings.warn(f"[fdic] API call failed: {e}")
        return []


def fetch_fdic_specgrp(
    start: str = "1990-01-01",
    end: str   = "2024-12-31",
    use_cache:  bool = True,
    verbose:    bool = True,
) -> pd.DataFrame:
    """
    Download quarterly FDIC aggregate call-report data by SPECGRP.

    Returns
    -------
    DataFrame with MultiIndex (REPDTE, SPECGRP) and columns:
        ASSET, LNLSNET, EQ, NETINC, INTINC, INTEXP, NCLNLS
    All values are *sums* across all institutions in that SPECGRP for the quarter.
    Dates are quarter-end timestamps.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if use_cache and CACHE_FILE.exists():
        with open(CACHE_FILE, "rb") as f:
            data = pickle.load(f)
        if verbose:
            print(f"[fdic] Loaded from cache. "
                  f"Shape: {data.shape}, dates: {data.index.get_level_values(0)[[0,-1]]}")
        return data

    # FDIC date format: YYYYMMDD (no separators)
    start_fdic = start.replace("-", "")
    end_fdic   = end.replace("-", "")

    params = {
        # FDIC API aggregation: use 'limit' (not agg_limit) for result count.
        # Do not include 'fields' when using agg_by — API derives output columns.
        "filters":        f"REPDTE:[{start_fdic} TO {end_fdic}]",
        "agg_by":         "REPDTE,SPECGRP",
        "agg_sum_fields": "ASSET,LNLSNET,EQ,NETINC,INTINC,INTEXP,NCLNLS",
        "limit":          10000,
        "output":         "json",
    }

    if verbose:
        print("[fdic] Fetching SPECGRP aggregates from FDIC SDI API …")
    raw = _fdic_api_call(params, verbose=verbose)

    if not raw:
        raise RuntimeError(
            "[fdic] API returned empty data.  "
            "Check https://banks.data.fdic.gov/api/financials is reachable."
        )

    # Each record is {"data": {...}} — extract inner dict
    rows = [r["data"] if "data" in r else r for r in raw]
    df   = pd.DataFrame(rows)

    # Parse date: FDIC returns REPDTE as string 'YYYYMMDD'
    df["REPDTE"]  = pd.to_datetime(df["REPDTE"].astype(str), format="%Y%m%d")
    df["SPECGRP"] = pd.to_numeric(df["SPECGRP"], errors="coerce").astype("Int64")

    # Numeric conversion for financial fields
    for col in FDIC_FIELDS[2:]:   # skip REPDTE and SPECGRP
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Keep only known SPECGRP codes
    df = df[df["SPECGRP"].isin(SPECGRP_MAP.keys())].copy()
    df = df.dropna(subset=["ASSET"])

    # Snap to quarter-end for alignment with FRED
    df["REPDTE"] = df["REPDTE"] + pd.offsets.QuarterEnd(0)
    df = df.set_index(["REPDTE", "SPECGRP"]).sort_index()

    if verbose:
        dates = df.index.get_level_values(0)
        print(f"[fdic] Fetched {len(df)} observations, "
              f"{df.index.get_level_values(1).nunique()} sectors, "
              f"dates {dates.min().date()} – {dates.max().date()}")

    with open(CACHE_FILE, "wb") as f:
        pickle.dump(df, f)
    return df


def compute_sector_features(
    fdic_df: pd.DataFrame,
    fred_slope: pd.Series,
) -> dict[int, pd.DataFrame]:
    """
    Compute the d=6 feature time series for each SPECGRP sector.

    Parameters
    ----------
    fdic_df    : result of fetch_fdic_specgrp() — MultiIndex (date, SPECGRP)
    fred_slope : pd.Series, T10Y2Y from FRED, quarterly, aligned by quarter-end date

    Returns
    -------
    Dict {specgrp: DataFrame(T, 6)} — index = quarter-end dates
    """
    eps = 1e-10   # guard against division by zero

    sector_features: dict[int, pd.DataFrame] = {}

    for grp in SPECGRP_MAP:
        try:
            sub = fdic_df.xs(grp, level="SPECGRP")
        except KeyError:
            continue

        feat = pd.DataFrame(index=sub.index)
        asset = sub["ASSET"].clip(lower=eps)

        feat["loan_to_asset"] = sub["LNLSNET"] / asset
        feat["equity_ratio"]  = sub["EQ"]      / asset
        feat["npl_ratio"]     = sub["NCLNLS"]  / (sub["LNLSNET"].clip(lower=eps))
        feat["roa"]           = sub["NETINC"]   / asset
        feat["funding_cost"]  = sub["INTEXP"]   / (sub["LNLSNET"].clip(lower=eps))

        # Align yield slope from FRED (same value for all sectors)
        feat = feat.join(fred_slope.rename("yield_slope"), how="left")
        feat["yield_slope"] = feat["yield_slope"].ffill(limit=2)

        sector_features[grp] = feat[FEATURE_NAMES]

    return sector_features


def build_panel(
    sector_features: dict[int, pd.DataFrame],
) -> tuple[np.ndarray, pd.DatetimeIndex, list[str]]:
    """
    Stack sector features into array X of shape (T, N, d).

    Only uses time steps present in ALL sectors (inner join on dates).

    Returns
    -------
    X       : np.ndarray (T, N, d)
    dates   : pd.DatetimeIndex length T
    sectors : list of sector names, length N
    """
    # Inner join on dates
    all_dates = None
    for feat in sector_features.values():
        d = feat.dropna().index
        all_dates = d if all_dates is None else all_dates.intersection(d)

    grps    = sorted(sector_features.keys())
    sectors = [SPECGRP_MAP[g] for g in grps]
    T       = len(all_dates)
    N       = len(grps)
    d_feat  = len(FEATURE_NAMES)

    X = np.full((T, N, d_feat), np.nan)
    for j, grp in enumerate(grps):
        X[:, j, :] = sector_features[grp].loc[all_dates].values

    return X, pd.DatetimeIndex(all_dates), sectors
