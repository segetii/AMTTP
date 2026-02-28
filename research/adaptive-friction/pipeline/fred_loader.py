"""
fred_loader.py
==============
Fetches publicly available FRED series needed for §8 empirical validation.
All series are quarterly, 2000-Q1 through 2024-Q4 (cropped to data availability).

No API key required for pandas_datareader FRED access.
Results are cached to fred_cache/ to avoid re-fetching on repeated runs.
"""

from __future__ import annotations
import warnings
import pickle
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

# Attempt pandas_datareader; fall back to direct FRED URL download
try:
    import pandas_datareader.data as web
    _PDR_AVAILABLE = True
except ImportError:
    _PDR_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# Series catalogue
# Each entry: (fred_id, description, transform)
# transform: 'level' | 'log' | 'growth_yoy' | 'zscore'
# ─────────────────────────────────────────────────────────────────────────────
FRED_SERIES: dict[str, tuple[str, str, str]] = {
    # Leverage / credit
    "credit_gdp":     ("DPCREDIT",     "Bank credit to private sector (% GDP)",          "level"),
    "total_loans":    ("TOTLL",        "Total loans & leases at commercial banks ($B)",   "growth_yoy"),
    # Liquidity / funding
    "fed_funds":      ("FEDFUNDS",     "Effective Federal Funds Rate (%)",                "level"),
    "ted_spread":     ("TEDRATE",      "TED Spread (3M LIBOR - T-bill, bp)",              "level"),
    # Stress composites
    "stlfsi":         ("STLFSI2",      "St. Louis Fed Financial Stress Index",            "level"),
    "nfci":           ("NFCI",         "Chicago Fed National Financial Conditions",        "level"),
    # Market / volatility
    "vix":            ("VIXCLS",       "CBOE VIX",                                        "level"),
    "hy_spread":      ("BAMLH0A0HYM2", "ICE BofA HY Option-Adjusted Spread (bp)",        "level"),
    "baa_spread":     ("BAA10Y",       "Moody's BAA - 10yr Treasury spread (bp)",         "level"),
    # Yield curve
    "slope_10y2y":    ("T10Y2Y",       "10Y minus 2Y treasury spread (bp)",               "level"),
    # Banking profitability
    "roa":            ("USROA",        "Return on Assets, all insured commercial banks",  "level"),
}

START = "2000-01-01"
END   = "2024-12-31"
CACHE_DIR = Path(__file__).parent / "fred_cache"
CACHE_FILE = CACHE_DIR / "fred_quarterly.pkl"


def _fetch_one(series_id: str, start: str, end: str) -> pd.Series:
    """Fetch a single FRED series via pandas_datareader."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = web.DataReader(series_id, "fred", start, end)
    return df.iloc[:, 0]


def _fetch_via_url(series_id: str, start: str, end: str) -> pd.Series:
    """Direct FRED API download (no key, public endpoint)."""
    url = (
        f"https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id={series_id}&vintage_date={end[:10]}"
    )
    try:
        df = pd.read_csv(url, index_col=0, parse_dates=True)
        df = df.loc[start:end]
        return df.iloc[:, 0].rename(series_id)
    except Exception as e:
        raise RuntimeError(f"Failed to download {series_id}: {e}") from e


def fetch_all(use_cache: bool = True, verbose: bool = True) -> pd.DataFrame:
    """
    Return a DataFrame of quarterly FRED series (index = period end dates).
    Caches to disk on first run.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if use_cache and CACHE_FILE.exists():
        with open(CACHE_FILE, "rb") as f:
            data = pickle.load(f)
        if verbose:
            print(f"[fred] Loaded from cache: {CACHE_FILE}")
        return data

    frames = {}
    for key, (series_id, desc, _) in FRED_SERIES.items():
        if verbose:
            print(f"  Fetching {series_id:20s} ({desc[:50]})")
        try:
            if _PDR_AVAILABLE:
                s = _fetch_one(series_id, START, END)
            else:
                s = _fetch_via_url(series_id, START, END)
            frames[key] = s
        except Exception as e:
            if verbose:
                print(f"    [warn] {series_id} failed: {e}")
            frames[key] = pd.Series(dtype=float, name=key)

    # Combine, resample to quarterly (period end), forward-fill max 2 quarters
    df = pd.DataFrame(frames)
    df.index = pd.to_datetime(df.index)
    df = df.resample("QE").last()          # quarter-end
    df = df.ffill(limit=2)
    df = df.loc[START:END]
    df = df.dropna(how="all")

    with open(CACHE_FILE, "wb") as f:
        pickle.dump(df, f)
    if verbose:
        print(f"[fred] Saved to cache: {CACHE_FILE}")
    return df


def apply_transforms(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply the transforms defined in FRED_SERIES catalogue.
    Returns a DataFrame of the same shape with transformed values.
    """
    out = pd.DataFrame(index=df.index)
    for key, (_, __, transform) in FRED_SERIES.items():
        if key not in df.columns:
            continue
        s = df[key].copy()
        if transform == "log":
            s = np.log(s.clip(lower=1e-6))
        elif transform == "growth_yoy":
            s = s.pct_change(4) * 100           # 4 quarters = YoY
        elif transform == "zscore":
            s = (s - s.mean()) / (s.std() + 1e-12)
        # 'level' → no transform
        out[key] = s
    return out.dropna(how="all")


def standardise(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Z-score each column using full-sample mean and std. Returns (df_std, means, stds)."""
    means = df.mean()
    stds  = df.std().replace(0, 1)
    return (df - means) / stds, means, stds


if __name__ == "__main__":
    print("Fetching FRED data...")
    raw = fetch_all(use_cache=False)
    print(raw.tail())
    xf  = apply_transforms(raw)
    std, mu, sig = standardise(xf)
    print(f"\nFinal shape: {std.shape}")
    print(std.describe().round(2))
