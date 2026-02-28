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
    f4  funding_cost     = EINTEXP / LNLSNET         (interest cost per loan $)
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
All data comes from FDIC regulatory filings, aggregated by institution type.

API note
--------
The FDIC REST API does not support combining ``agg_by`` with date-range
filters.  This module therefore iterates over each quarter-end date
individually, issuing one server-side ``agg_by=SPECGRP`` call per quarter.
For 140 quarters (1990-2024), this takes ~3-4 minutes.  Results are
cached to ``fred_cache/fdic_specgrp_quarterly.pkl``.
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

# Correct FDIC field names (verified against API schema):
#   EINTEXP  = interest expense  (not 'INTEXP' which doesn't exist)
#   NCLNLS   = non-current loans & leases ($)
#   INTINC   = interest income
#   ASSET    = total assets
#   LNLSNET  = net loans & leases
#   EQ       = total equity capital
#   NETINC   = net income
AGG_SUM_FIELDS = "ASSET,LNLSNET,EQ,NETINC,EINTEXP,INTINC,NCLNLS"

# Column mapping: agg_by returns fields with 'sum_' prefix
AGG_RENAME = {
    "sum_ASSET":   "ASSET",
    "sum_LNLSNET": "LNLSNET",
    "sum_EQ":      "EQ",
    "sum_NETINC":  "NETINC",
    "sum_EINTEXP": "EINTEXP",
    "sum_INTINC":  "INTINC",
    "sum_NCLNLS":  "NCLNLS",
}

NUMERIC_COLS = ["ASSET", "LNLSNET", "EQ", "NETINC", "EINTEXP", "INTINC", "NCLNLS"]

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
        print(f"  [fdic] GET {url[:120]}...")
    try:
        with urlopen(url, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload.get("data", [])
    except URLError as e:
        warnings.warn(f"[fdic] API call failed: {e}")
        return []


def _quarter_end_dates(start: str, end: str) -> list[str]:
    """
    Generate quarter-end date strings in FDIC format (YYYYMMDD).
    E.g. 19900331, 19900630, 19900930, 19901231, ...
    """
    start_dt = pd.Timestamp(start)
    end_dt   = pd.Timestamp(end)
    dates    = pd.date_range(start_dt, end_dt, freq="QE")
    return [d.strftime("%Y%m%d") for d in dates]


def fetch_fdic_specgrp(
    start: str = "1990-01-01",
    end: str   = "2024-12-31",
    use_cache:  bool = True,
    verbose:    bool = True,
) -> pd.DataFrame:
    """
    Download quarterly FDIC aggregate call-report data by SPECGRP.

    Strategy: iterate over each quarter-end date and issue a single
    ``agg_by=SPECGRP`` call per quarter.  The FDIC API does *not*
    support combining ``agg_by`` with date-range filters, so this
    per-quarter approach is the only reliable method.

    Returns
    -------
    DataFrame with MultiIndex (REPDTE, SPECGRP) and columns:
        ASSET, LNLSNET, EQ, NETINC, EINTEXP, INTINC, NCLNLS
    All values are *sums* across all institutions in that SPECGRP for
    the quarter.  Dates are quarter-end timestamps.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if use_cache and CACHE_FILE.exists():
        with open(CACHE_FILE, "rb") as f:
            data = pickle.load(f)
        if verbose:
            print(f"[fdic] Loaded from cache. "
                  f"Shape: {data.shape}, dates: {data.index.get_level_values(0)[[0,-1]]}")
        return data

    quarter_dates = _quarter_end_dates(start, end)
    if verbose:
        print(f"[fdic] Fetching SPECGRP aggregates for {len(quarter_dates)} quarters "
              f"from FDIC SDI API ...")
        print(f"[fdic] Date range: {quarter_dates[0]} – {quarter_dates[-1]}")

    all_rows: list[dict] = []
    n_ok    = 0
    n_empty = 0
    t0      = time.perf_counter()

    for i, qdate in enumerate(quarter_dates):
        params = {
            "filters":        f"REPDTE:{qdate}",
            "agg_by":         "SPECGRP",
            "agg_sum_fields": AGG_SUM_FIELDS,
            "limit":          20,
            "output":         "json",
        }
        records = _fdic_api_call(params, verbose=False)

        if records:
            for r in records:
                d = r["data"] if "data" in r else r
                d["REPDTE"] = qdate
                all_rows.append(d)
            n_ok += 1
        else:
            n_empty += 1

        # Progress every 20 quarters
        if verbose and (i + 1) % 20 == 0:
            elapsed = time.perf_counter() - t0
            pct     = (i + 1) / len(quarter_dates) * 100
            print(f"  [fdic] {i+1}/{len(quarter_dates)} quarters ({pct:.0f}%) "
                  f"in {elapsed:.1f}s  ({n_ok} ok, {n_empty} empty)")

        # Polite delay between API calls
        time.sleep(0.25)

    elapsed = time.perf_counter() - t0
    if verbose:
        print(f"[fdic] Completed: {n_ok}/{len(quarter_dates)} quarters "
              f"in {elapsed:.1f}s.  Total rows: {len(all_rows)}")

    if not all_rows:
        raise RuntimeError(
            "[fdic] API returned empty data for ALL quarters.  "
            "Check https://banks.data.fdic.gov/api/financials is reachable."
        )

    df = pd.DataFrame(all_rows)

    # Rename sum_ prefixed columns to clean names
    df = df.rename(columns=AGG_RENAME)

    # Parse date
    df["REPDTE"]  = pd.to_datetime(df["REPDTE"].astype(str), format="%Y%m%d")
    df["SPECGRP"] = pd.to_numeric(df["SPECGRP"], errors="coerce").astype("Int64")

    # Numeric conversion for financial fields
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Keep only known SPECGRP codes (1-7)
    df = df[df["SPECGRP"].isin(SPECGRP_MAP.keys())].copy()
    df = df.dropna(subset=["ASSET"])

    # Snap to quarter-end for alignment with FRED
    df["REPDTE"] = df["REPDTE"] + pd.offsets.QuarterEnd(0)
    df = df.set_index(["REPDTE", "SPECGRP"]).sort_index()

    # Keep only needed columns
    df = df[NUMERIC_COLS].copy()

    if verbose:
        dates = df.index.get_level_values(0)
        print(f"[fdic] Final panel: {len(df)} observations, "
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
        feat["funding_cost"]  = sub["EINTEXP"]  / (sub["LNLSNET"].clip(lower=eps))

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
