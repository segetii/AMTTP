"""
FDIC Statistics on Depository Institutions data loader.

Fetches quarterly call-report data for individual banks via the FDIC
SDI REST API (https://banks.data.fdic.gov).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import requests


FDIC_BASE = "https://banks.data.fdic.gov/api"
CACHE_DIR = Path(__file__).parent / "_cache" / "fdic"

# Standard features computed from call-report fields
FEATURE_NAMES = ["loan_to_asset", "equity_ratio", "npl_ratio", "roa", "funding_cost"]

# FDIC fields required
BANK_FIELDS = ["CERT", "REPDTE", "ASSET", "LNLSNET", "EQ", "NCLNLS", "NETINC", "EINTEXP"]


def fetch_bank_financials(
    cert: int,
    start: str = "19900101",
    end: str = "20241231",
    force_refresh: bool = False,
    timeout: int = 30,
) -> pd.DataFrame:
    """
    Fetch quarterly financials for a single bank by FDIC CERT number.

    Parameters
    ----------
    cert : int — FDIC certificate number
    start, end : str — date range (YYYYMMDD)
    force_refresh : bool — bypass cache
    timeout : int — request timeout

    Returns
    -------
    pd.DataFrame with columns: date, loan_to_asset, equity_ratio, npl_ratio, roa, funding_cost
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"cert_{cert}.json"

    if cache_file.exists() and not force_refresh:
        data = json.loads(cache_file.read_text())
        df = pd.DataFrame(data)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        return df

    url = f"{FDIC_BASE}/financials"
    params = {
        "filters": f"CERT:{cert} AND REPDTE:[{start} TO {end}]",
        "fields": ",".join(BANK_FIELDS),
        "sort_by": "REPDTE",
        "sort_order": "ASC",
        "limit": 10000,
    }

    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    rows = resp.json().get("data", [])

    records = []
    for row in rows:
        d = row.get("data", {})
        try:
            asset = float(d.get("ASSET", 0))
            if asset < 1:
                continue
            rec = {
                "date": pd.Timestamp(str(d["REPDTE"])),
                "loan_to_asset": float(d.get("LNLSNET", 0)) / asset,
                "equity_ratio": float(d.get("EQ", 0)) / asset,
                "npl_ratio": float(d.get("NCLNLS", 0)) / max(float(d.get("LNLSNET", 1)), 1),
                "roa": float(d.get("NETINC", 0)) / asset,
                "funding_cost": float(d.get("EINTEXP", 0)) / asset,
            }
            records.append(rec)
        except (ValueError, TypeError, ZeroDivisionError):
            continue

    df = pd.DataFrame(records)
    if not df.empty:
        cache_file.write_text(df.to_json(orient="records", date_format="iso"))

    return df


def build_bank_panel(
    certs: Dict[str, int],
    start: str = "19900101",
    end: str = "20241231",
    force_refresh: bool = False,
    min_coverage: float = 0.50,
    verbose: bool = True,
) -> Dict:
    """
    Build a (T, N, d) state matrix panel from individual FDIC banks.

    Parameters
    ----------
    certs : dict mapping bank_name → FDIC CERT number
    start, end : str — date range
    force_refresh : bool
    min_coverage : float — minimum fraction of dates a bank must cover
    verbose : bool

    Returns
    -------
    dict with keys:
        X : ndarray (T, N, d)
        dates : pd.DatetimeIndex
        names : list[str] — bank names (length N)
        feature_names : list[str]
    """
    all_dfs = {}
    for name, cert in certs.items():
        try:
            df = fetch_bank_financials(cert, start, end, force_refresh)
            if not df.empty:
                df = df.set_index("date").resample("QE").last().dropna()
                all_dfs[name] = df
                if verbose:
                    print(f"  {name} (CERT {cert}): {len(df)} quarters")
        except Exception as e:
            if verbose:
                print(f"  {name} (CERT {cert}): FAILED — {e}")

    if not all_dfs:
        raise ValueError("No bank data retrieved.")

    # Common date index
    all_dates = sorted(set().union(*(df.index for df in all_dfs.values())))
    date_idx = pd.DatetimeIndex(all_dates)
    T = len(date_idx)

    # Filter by coverage
    kept = {}
    for name, df in all_dfs.items():
        coverage = df.index.isin(date_idx).sum() / T
        if coverage >= min_coverage:
            kept[name] = df
        elif verbose:
            print(f"  Dropped {name}: coverage {coverage:.1%} < {min_coverage:.0%}")

    N = len(kept)
    d = len(FEATURE_NAMES)
    X = np.full((T, N, d), np.nan)

    names = list(kept.keys())
    for j, name in enumerate(names):
        df = kept[name].reindex(date_idx)
        for k, feat in enumerate(FEATURE_NAMES):
            if feat in df.columns:
                X[:, j, k] = df[feat].values

    # Forward-fill then back-fill NaNs
    for j in range(N):
        for k in range(d):
            col = pd.Series(X[:, j, k])
            col = col.ffill().bfill().fillna(0.0)
            X[:, j, k] = col.values

    return {
        "X": X,
        "dates": date_idx,
        "names": names,
        "feature_names": FEATURE_NAMES,
    }
