"""
World Bank GFDD and ECB MIR data loaders for non-U.S. institutions.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
from scipy.interpolate import CubicSpline


CACHE_DIR = Path(__file__).parent / "_cache" / "intl"
WB_BASE = "https://api.worldbank.org/v2"
ECB_BASE = "https://data-api.ecb.europa.eu/service/data"

# World Bank GFDD indicator codes → MFLS feature names
WB_INDICATORS = {
    "loan_to_asset": "FB.BNK.CAPA.ZS",   # bank credit / GDP (proxy)
    "npl_ratio": "FB.AST.NPER.ZS",        # NPL / total loans
    "equity_ratio": "GFDD.SI.01",          # bank Z-score (capitalisation proxy)
    "roa": "GFDD.DI.01",                  # credit / GDP (deposit proxy)
}
WB_FUNDING_ALTERNATIVES = ["FR.INR.LEND", "FR.INR.DPST", "GFDD.SI.05"]


def wb_fetch_indicator(
    iso3: str,
    indicator: str,
    start: int = 2000,
    end: int = 2024,
    timeout: int = 45,
) -> pd.Series:
    """
    Fetch a single World Bank indicator for one country.

    Returns
    -------
    pd.Series indexed by year → float
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"wb_{iso3}_{indicator}.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text())
        return pd.Series(data, dtype=float).sort_index()

    url = f"{WB_BASE}/country/{iso3}/indicator/{indicator}"
    params = {"format": "json", "per_page": 500, "date": f"{start}:{end}"}
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code != 200:
            return pd.Series(dtype=float)

        pages = resp.json()
        if not isinstance(pages, list) or len(pages) < 2:
            return pd.Series(dtype=float)

        records = {}
        for entry in pages[1]:
            if entry.get("value") is not None:
                records[int(entry["date"])] = float(entry["value"])

        if records:
            cache_file.write_text(json.dumps(records))

        return pd.Series(records, dtype=float).sort_index()
    except (requests.RequestException, ValueError, KeyError):
        return pd.Series(dtype=float)


def ecb_mir_lending_rate(
    country_code: str,
    timeout: int = 30,
) -> pd.Series:
    """
    Fetch ECB MFI Interest Rate (MIR) lending rate.

    Parameters
    ----------
    country_code : str — e.g. "DE", "FR", "IT"

    Returns
    -------
    pd.Series indexed by monthly Timestamp → float
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"ecb_mir_{country_code}.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text())
        s = pd.Series(data, dtype=float)
        s.index = pd.to_datetime(s.index)
        return s.sort_index()

    key = f"MIR.M.{country_code}.B.A2A.A.R.A.2240.EUR.N"
    url = f"{ECB_BASE}/{key}"
    headers = {"Accept": "application/vnd.sdmx.data+json;version=1.0.0"}
    resp = requests.get(url, headers=headers, timeout=timeout)

    if resp.status_code != 200:
        return pd.Series(dtype=float)

    try:
        body = resp.json()
        obs = body["dataSets"][0]["series"]["0:0:0:0:0:0:0:0:0:0"]["observations"]
        dims = body["structure"]["dimensions"]["observation"][0]["values"]
        records = {}
        for idx_str, val_list in obs.items():
            period = dims[int(idx_str)]["id"]
            records[period] = val_list[0]
        s = pd.Series(records, dtype=float)
        s.index = pd.to_datetime(s.index)
        s = s.sort_index()
        cache_file.write_text(s.to_json(date_format="iso"))
        return s
    except Exception:
        return pd.Series(dtype=float)


def annual_to_quarterly(
    annual_series: pd.Series,
    target_dates: pd.DatetimeIndex,
) -> np.ndarray:
    """Cubic spline interpolation from annual to quarterly."""
    if annual_series.empty or len(annual_series) < 2:
        return np.full(len(target_dates), np.nan)

    years = annual_series.index.values.astype(float)
    vals = annual_series.values.astype(float)
    cs = CubicSpline(years, vals, extrapolate=True)

    target_years = target_dates.year + (target_dates.month - 1) / 12.0
    return cs(target_years)


def monthly_to_quarterly(
    monthly_series: pd.Series,
    target_dates: pd.DatetimeIndex,
) -> np.ndarray:
    """Resample monthly to quarterly (end-of-quarter mean)."""
    if monthly_series.empty:
        return np.full(len(target_dates), np.nan)
    quarterly = monthly_series.resample("QE").mean()
    result = np.full(len(target_dates), np.nan)
    for i, dt in enumerate(target_dates):
        matches = quarterly.index[quarterly.index <= dt]
        if len(matches) > 0:
            result[i] = quarterly.loc[matches[-1]]
    return result


# ---------------------------------------------------------------------------
# G-SIB catalogue
# ---------------------------------------------------------------------------

GSIB_CATALOGUE = [
    # US banks (FDIC CERT)
    {"name": "JPMorgan Chase", "region": "US", "iso": "USA", "cert": 628, "tier": 1},
    {"name": "Bank of America", "region": "US", "iso": "USA", "cert": 3510, "tier": 1},
    {"name": "Citigroup", "region": "US", "iso": "USA", "cert": 7213, "tier": 1},
    {"name": "Wells Fargo", "region": "US", "iso": "USA", "cert": 3511, "tier": 1},
    {"name": "Goldman Sachs", "region": "US", "iso": "USA", "cert": 33124, "tier": 2},
    {"name": "BNY Mellon", "region": "US", "iso": "USA", "cert": 542, "tier": 2},
    # UK banks (World Bank — no ECB MIR, use WB funding rate)
    {"name": "HSBC", "region": "UK", "iso": "GBR", "tier": 1},
    {"name": "Barclays", "region": "UK", "iso": "GBR", "tier": 2},
    # EU banks (World Bank + ECB country-level)
    {"name": "BNP Paribas", "region": "EU", "iso": "FRA", "ecb_cc": "FR", "tier": 1},
    {"name": "Societe Generale", "region": "EU", "iso": "FRA", "ecb_cc": "FR", "tier": 2},
    {"name": "Deutsche Bank", "region": "EU", "iso": "DEU", "ecb_cc": "DE", "tier": 1},
    {"name": "ING", "region": "EU", "iso": "NLD", "ecb_cc": "NL", "tier": 2},
    {"name": "UniCredit", "region": "EU", "iso": "ITA", "ecb_cc": "IT", "tier": 2},
    # Asia banks (World Bank country-level)
    {"name": "MUFG", "region": "Asia", "iso": "JPN", "tier": 1},
    {"name": "Mizuho", "region": "Asia", "iso": "JPN", "tier": 2},
    {"name": "SMFG", "region": "Asia", "iso": "JPN", "tier": 2},
    {"name": "ICBC", "region": "Asia", "iso": "CHN", "tier": 1},
    {"name": "CCB", "region": "Asia", "iso": "CHN", "tier": 1},
    {"name": "Bank of China", "region": "Asia", "iso": "CHN", "tier": 1},
    {"name": "Ag Bank of China", "region": "Asia", "iso": "CHN", "tier": 2},
    # Africa — Nigeria (World Bank country-level)
    {"name": "Zenith Bank", "region": "Africa", "iso": "NGA", "tier": 2},
    {"name": "GTBank", "region": "Africa", "iso": "NGA", "tier": 2},
    {"name": "First Bank Nigeria", "region": "Africa", "iso": "NGA", "tier": 2},
    {"name": "Access Bank", "region": "Africa", "iso": "NGA", "tier": 2},
    {"name": "UBA", "region": "Africa", "iso": "NGA", "tier": 2},
]

FEATURE_NAMES = ["loan_to_asset", "equity_ratio", "npl_ratio", "roa", "funding_cost"]


def build_gsib_panel(
    start: str = "2005-01-01",
    end: str = "2023-12-31",
    force_refresh: bool = False,
    min_coverage: float = 0.50,
    verbose: bool = True,
) -> Dict:
    """
    Build a real-data G-SIB panel from FDIC + World Bank + ECB.

    Parameters
    ----------
    start, end : str — date range
    force_refresh : bool
    min_coverage : float — minimum data coverage to include a bank
    verbose : bool

    Returns
    -------
    dict with keys:
        X : ndarray (T, N, d)
        dates : pd.DatetimeIndex
        meta : list[dict] — per-bank metadata
        n_gsib, n_us, n_non_us : int
        feature_names : list[str]
    """
    from mfls.data.fdic import fetch_bank_financials

    dates = pd.date_range(start, end, freq="QE")
    T = len(dates)
    d = len(FEATURE_NAMES)

    panels = []
    meta = []

    for bank in GSIB_CATALOGUE:
        try:
            if bank.get("cert"):
                # US bank: use FDIC
                df = fetch_bank_financials(bank["cert"], force_refresh=force_refresh)
                if df.empty:
                    continue
                df = df.set_index("date").reindex(dates).ffill().bfill()
                arr = df[FEATURE_NAMES].values
                coverage = 1.0 - np.isnan(arr).mean()
            else:
                # Non-US: World Bank + ECB
                arr = np.full((T, d), np.nan)
                for k, feat in enumerate(FEATURE_NAMES):
                    if feat == "funding_cost" and bank.get("ecb_cc"):
                        s = ecb_mir_lending_rate(bank["ecb_cc"])
                        if not s.empty:
                            arr[:, k] = monthly_to_quarterly(s, dates)
                            continue
                    if feat == "funding_cost":
                        for alt in WB_FUNDING_ALTERNATIVES:
                            s = wb_fetch_indicator(bank["iso"], alt)
                            if not s.empty:
                                arr[:, k] = annual_to_quarterly(s, dates)
                                break
                    elif feat in WB_INDICATORS:
                        s = wb_fetch_indicator(bank["iso"], WB_INDICATORS[feat])
                        if not s.empty:
                            arr[:, k] = annual_to_quarterly(s, dates)

                coverage = 1.0 - np.isnan(arr).mean()

            if coverage < min_coverage:
                if verbose:
                    print(f"  Skipped {bank['name']}: coverage {coverage:.1%}")
                continue

            # Fill remaining NaNs
            for k in range(d):
                col = pd.Series(arr[:, k])
                arr[:, k] = col.ffill().bfill().fillna(0.0).values

            panels.append(arr)
            meta.append({
                "name": bank["name"],
                "region": bank["region"],
                "iso": bank["iso"],
                "tier": bank["tier"],
                "source": "FDIC" if bank.get("cert") else "WorldBank/ECB",
            })
            if verbose:
                print(f"  {bank['name']}: OK ({coverage:.0%} coverage)")

        except Exception as e:
            if verbose:
                print(f"  {bank['name']}: FAILED — {e}")

    N = len(panels)
    X = np.stack(panels, axis=1)  # (T, N, d)
    n_us = sum(1 for m in meta if m["source"] == "FDIC")

    return {
        "X": X,
        "dates": dates,
        "meta": meta,
        "n_gsib": N,
        "n_us": n_us,
        "n_non_us": N - n_us,
        "feature_names": FEATURE_NAMES,
    }
