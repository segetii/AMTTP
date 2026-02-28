"""
gsib_loader_real.py
===================
Replaces synthetic proxies with REAL data from:
  - FDIC SDI call-report (US G-SIBs, individual bank-level, quarterly)
  - World Bank GFDD (non-US, country banking-sector aggregate, annual -> interpolated quarterly)
  - ECB MIR (euro-area, country-level bank lending rates, monthly -> quarterly)

Each non-US G-SIB inherits its home country's banking-sector aggregates.
This is COUNTRY-LEVEL data, not individual-bank data, and is clearly labelled
as such in the output metadata.

Produces
--------
  X: (T, N, d=5)   where N = number of G-SIBs with sufficient data coverage
  dates: pd.DatetimeIndex (quarterly)
  meta: list of dicts {name, region, home_country, data_source, coverage_pct}

Feature mapping (World Bank indicator -> pipeline feature)
----------------------------------------------------------
  loan_to_asset  <- GFDD.DI.01 (private credit / GDP, rescaled to [0,1] range)
  equity_ratio   <- FB.BNK.CAPA.ZS (bank capital / assets %)
  npl_ratio      <- FB.AST.NPER.ZS (NPL / gross loans %)
  roa            <- GFDD.SI.01 (bank ROA or profitability %)
  funding_cost   <- ECB MIR lending rate (euro-area) or FR.INR.LEND / FR.INR.DPST (others)
"""
from __future__ import annotations
import json
import time
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from scipy import interpolate as sci_interp

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FDIC_BASE = "https://banks.data.fdic.gov/api"
WB_BASE   = "https://api.worldbank.org/v2"
ECB_BASE  = "https://data-api.ecb.europa.eu/service/data"

CACHE_DIR = Path(__file__).parent / "gsib_cache_real"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_NAMES = [
    "loan_to_asset",
    "equity_ratio",
    "npl_ratio",
    "roa",
    "funding_cost",
]

# ---------------------------------------------------------------------------
# G-SIB Catalogue with home-country ISO codes
# ---------------------------------------------------------------------------
GSIB_CATALOGUE = [
    # US G-SIBs (real FDIC data)
    {"name": "JPMorgan Chase",          "region": "US",   "iso": "USA", "cert": 628,    "tier": 1},
    {"name": "Bank of America",         "region": "US",   "iso": "USA", "cert": 3510,   "tier": 1},
    {"name": "Citibank NA",             "region": "US",   "iso": "USA", "cert": 7213,   "tier": 1},
    {"name": "Wells Fargo",             "region": "US",   "iso": "USA", "cert": 3511,   "tier": 1},
    {"name": "Goldman Sachs Bank USA",  "region": "US",   "iso": "USA", "cert": 34264,  "tier": 1},
    {"name": "Morgan Stanley Bank NA",  "region": "US",   "iso": "USA", "cert": 59529,  "tier": 1},
    {"name": "BNY Mellon",              "region": "US",   "iso": "USA", "cert": 639,    "tier": 1},
    {"name": "State Street Bank",       "region": "US",   "iso": "USA", "cert": 35301,  "tier": 1},
    # EU G-SIBs (World Bank + ECB MIR)
    {"name": "HSBC",                    "region": "EU",   "iso": "GBR", "cert": None,   "tier": 2, "ecb_cc": None},
    {"name": "BNP Paribas",             "region": "EU",   "iso": "FRA", "cert": None,   "tier": 2, "ecb_cc": "FR"},
    {"name": "Deutsche Bank",           "region": "EU",   "iso": "DEU", "cert": None,   "tier": 2, "ecb_cc": "DE"},
    {"name": "Barclays",                "region": "EU",   "iso": "GBR", "cert": None,   "tier": 2, "ecb_cc": None},
    {"name": "Societe Generale",        "region": "EU",   "iso": "FRA", "cert": None,   "tier": 2, "ecb_cc": "FR"},
    {"name": "UniCredit",               "region": "EU",   "iso": "ITA", "cert": None,   "tier": 2, "ecb_cc": "IT"},
    {"name": "ING",                     "region": "EU",   "iso": "NLD", "cert": None,   "tier": 2, "ecb_cc": "NL"},
    # Asia G-SIBs (World Bank)
    {"name": "Mitsubishi UFJ",          "region": "Asia", "iso": "JPN", "cert": None,   "tier": 2},
    {"name": "Mizuho",                  "region": "Asia", "iso": "JPN", "cert": None,   "tier": 2},
    {"name": "Sumitomo Mitsui",         "region": "Asia", "iso": "JPN", "cert": None,   "tier": 2},
    {"name": "Bank of China",           "region": "Asia", "iso": "CHN", "cert": None,   "tier": 2},
    {"name": "ICBC",                    "region": "Asia", "iso": "CHN", "cert": None,   "tier": 2},
    {"name": "China Construction Bank", "region": "Asia", "iso": "CHN", "cert": None,   "tier": 2},
    {"name": "Standard Chartered",      "region": "Asia", "iso": "GBR", "cert": None,   "tier": 2, "ecb_cc": None},
]


# ---------------------------------------------------------------------------
# World Bank fetcher (annual)
# ---------------------------------------------------------------------------
WB_INDICATORS = {
    "loan_to_asset":  "GFDD.DI.01",   # private credit / GDP (%)
    "equity_ratio":   "FB.BNK.CAPA.ZS",  # bank capital / assets (%)
    "npl_ratio":      "FB.AST.NPER.ZS",  # NPL / gross loans (%)
    "roa":            "GFDD.SI.01",   # bank ROA / profitability (%)
    "funding_cost":   "FR.INR.LEND",  # fallback lending rate (%)
}

# Alternative funding cost indicators (tried in order)
WB_FUNDING_ALTERNATIVES = ["FR.INR.LEND", "FR.INR.DPST", "GFDD.SI.05"]


def _wb_fetch_indicator(iso3: str, indicator: str, start: int = 2000,
                        end: int = 2024, timeout: int = 45) -> pd.Series:
    """Fetch a single World Bank indicator for one country."""
    cache = CACHE_DIR / f"wb_{iso3}_{indicator}.json"
    if cache.exists():
        with open(cache) as f:
            raw = json.load(f)
        s = pd.Series(raw, dtype=float)
        s.index = pd.to_datetime(s.index)
        return s.sort_index()

    url = f"{WB_BASE}/country/{iso3}/indicator/{indicator}"
    params = {"format": "json", "per_page": 100, "date": f"{start}:{end}"}
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        entries = data[1] if isinstance(data, list) and len(data) > 1 else []
    except Exception as e:
        warnings.warn(f"World Bank fetch failed for {iso3}/{indicator}: {e}")
        return pd.Series(dtype=float)

    vals = {}
    for e in entries:
        if e.get("value") is not None:
            try:
                vals[f"{e['date']}-06-30"] = float(e["value"])
            except (ValueError, TypeError):
                pass

    if vals:
        with open(cache, "w") as f:
            json.dump(vals, f)

    s = pd.Series(vals, dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _wb_fetch_all_features(iso3: str) -> Dict[str, pd.Series]:
    """Fetch all 5 features for a country from World Bank."""
    result = {}
    for feat_name, ind_code in WB_INDICATORS.items():
        if feat_name == "funding_cost":
            # Try alternatives in order
            for alt_code in WB_FUNDING_ALTERNATIVES:
                s = _wb_fetch_indicator(iso3, alt_code)
                if len(s) >= 5:
                    result[feat_name] = s
                    break
            else:
                result[feat_name] = pd.Series(dtype=float)
        else:
            result[feat_name] = _wb_fetch_indicator(iso3, ind_code)
    return result


# ---------------------------------------------------------------------------
# ECB MIR fetcher (monthly lending rates for euro-area)
# ---------------------------------------------------------------------------
def _ecb_mir_lending_rate(country_code: str) -> pd.Series:
    """Fetch monthly bank lending rate from ECB MIR for a euro-area country."""
    cache = CACHE_DIR / f"ecb_mir_{country_code}.json"
    if cache.exists():
        with open(cache) as f:
            raw = json.load(f)
        s = pd.Series(raw, dtype=float)
        s.index = pd.to_datetime(s.index)
        return s.sort_index()

    # MIR: Loans to non-financial corps, all maturities, new business, rate
    url = f"{ECB_BASE}/MIR/M.{country_code}.B.A2A.A.R.A.2240.EUR.N"
    params = {"format": "csvdata", "startPeriod": "2000-01", "endPeriod": "2024-12"}
    try:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code != 200:
            return pd.Series(dtype=float)
        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            return pd.Series(dtype=float)
    except Exception as e:
        warnings.warn(f"ECB MIR fetch failed for {country_code}: {e}")
        return pd.Series(dtype=float)

    # Parse CSV: header is first line, data starts from second
    header = lines[0].split(",")
    # Find TIME_PERIOD and OBS_VALUE columns
    try:
        time_idx = next(i for i, h in enumerate(header) if "TIME_PERIOD" in h)
        val_idx  = next(i for i, h in enumerate(header) if "OBS_VALUE" in h)
    except StopIteration:
        # Fallback: positional (column 11 = time, column 12 = value in ECB CSV)
        time_idx, val_idx = 11, 12

    vals = {}
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) > max(time_idx, val_idx):
            try:
                date_str = parts[time_idx].strip()
                val = float(parts[val_idx].strip())
                vals[f"{date_str}-01"] = val
            except (ValueError, IndexError):
                pass

    if vals:
        with open(cache, "w") as f:
            json.dump(vals, f)

    s = pd.Series(vals, dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


# ---------------------------------------------------------------------------
# Annual -> Quarterly interpolation
# ---------------------------------------------------------------------------
def _annual_to_quarterly(annual_series: pd.Series,
                         target_dates: pd.DatetimeIndex) -> np.ndarray:
    """
    Interpolate annual data to quarterly using cubic spline.
    Falls back to linear if fewer than 4 annual observations.
    """
    s = annual_series.dropna().sort_index()
    if len(s) < 2:
        return np.full(len(target_dates), np.nan)

    # Convert to fractional years for interpolation
    ref_year = target_dates[0].year
    x_annual = np.array([(d.year - ref_year) + (d.month - 1) / 12.0 for d in s.index])
    y_annual = s.values.astype(float)

    x_quarterly = np.array([(d.year - ref_year) + (d.month - 1) / 12.0 for d in target_dates])

    # Choose interpolation method based on data density
    if len(s) >= 4:
        try:
            f_interp = sci_interp.CubicSpline(x_annual, y_annual, extrapolate=True)
            result = f_interp(x_quarterly)
        except Exception:
            f_interp = sci_interp.interp1d(x_annual, y_annual, kind="linear",
                                           fill_value="extrapolate")
            result = f_interp(x_quarterly)
    else:
        f_interp = sci_interp.interp1d(x_annual, y_annual, kind="linear",
                                       fill_value="extrapolate")
        result = f_interp(x_quarterly)

    return result


def _monthly_to_quarterly(monthly_series: pd.Series,
                          target_dates: pd.DatetimeIndex) -> np.ndarray:
    """Resample monthly data to quarterly (mean of 3 months), then align."""
    s = monthly_series.dropna().sort_index()
    if len(s) < 3:
        return np.full(len(target_dates), np.nan)
    q = s.resample("QE").mean()
    aligned = q.reindex(target_dates, method="ffill")
    return aligned.values


# ---------------------------------------------------------------------------
# FDIC fetcher (same as gsib_loader.py)
# ---------------------------------------------------------------------------
BANK_FIELDS = [
    "CERT", "REPDTE", "ASSET", "LNLSNET", "EQ", "NCLNLS", "NETINC", "EINTEXP",
]


def _fdic_financials_cert(cert: int, start: str = "19940101",
                           end: str = "20241231",
                           force_refresh: bool = False) -> pd.DataFrame:
    """Fetch quarterly financials for a single FDIC CERT."""
    cache = CACHE_DIR / f"fdic_cert_{cert}.json"
    if not force_refresh and cache.exists():
        with open(cache) as f:
            raw = json.load(f)
        return pd.DataFrame(raw)

    url = f"{FDIC_BASE}/financials"
    params = {
        "filters": f"CERT:{cert} AND REPDTE:[{start} TO {end}]",
        "fields":  ",".join(BANK_FIELDS),
        "limit":   500, "offset": 0,
        "sort_by": "REPDTE", "sort_order": "ASC", "output": "json",
    }
    records = []
    while True:
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json().get("data", [])
        except Exception as e:
            warnings.warn(f"FDIC API error for CERT {cert}: {e}")
            break
        if not data:
            break
        records.extend(d["data"] for d in data if "data" in d)
        if len(data) < params["limit"]:
            break
        params["offset"] += params["limit"]
        time.sleep(0.1)

    df = pd.DataFrame(records)
    if not df.empty:
        with open(cache, "w") as f:
            json.dump(records, f)
    return df


def _build_us_gsib_series(cert: int, dates: pd.DatetimeIndex) -> np.ndarray:
    """Build (T, 5) feature array from FDIC call-report for a single US bank."""
    df = _fdic_financials_cert(cert)
    if df.empty:
        return np.full((len(dates), len(FEATURE_NAMES)), np.nan)

    def _safe_div(a, b):
        return np.where(
            (pd.to_numeric(b, errors="coerce").fillna(0).abs() > 1e-3),
            pd.to_numeric(a, errors="coerce").fillna(0) /
            pd.to_numeric(b, errors="coerce").fillna(1),
            np.nan,
        )

    df["REPDTE"] = pd.to_datetime(df["REPDTE"], format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["REPDTE"]).set_index("REPDTE").sort_index()
    for col in ["ASSET", "LNLSNET", "EQ", "NCLNLS", "NETINC", "EINTEXP"]:
        df[col] = pd.to_numeric(df.get(col, 0), errors="coerce").fillna(0)

    df["loan_to_asset"] = _safe_div(df["LNLSNET"], df["ASSET"])
    df["equity_ratio"]  = _safe_div(df["EQ"],      df["ASSET"])
    df["npl_ratio"]     = _safe_div(df["NCLNLS"],  df["LNLSNET"].replace(0, np.nan))
    df["roa"]           = _safe_div(df["NETINC"],  df["ASSET"])
    df["funding_cost"]  = _safe_div(df["EINTEXP"], df["LNLSNET"].replace(0, np.nan))

    feat = df[FEATURE_NAMES].copy()
    feat = feat.resample("QE").last()
    feat = feat.reindex(dates, method="ffill").fillna(method="bfill").fillna(0.0)
    return feat.values


# ---------------------------------------------------------------------------
# Non-US G-SIB series from World Bank + ECB
# ---------------------------------------------------------------------------
def _build_real_nonus_gsib_series(
    iso3: str,
    ecb_cc: Optional[str],
    dates: pd.DatetimeIndex,
) -> Tuple[np.ndarray, Dict[str, str]]:
    """
    Build (T, 5) feature array for a non-US G-SIB using real data.

    Returns (features_array, source_info_dict).
    """
    T = len(dates)
    features = np.full((T, 5), np.nan)
    sources = {}

    # Fetch World Bank data for this country
    wb_data = _wb_fetch_all_features(iso3)

    # Feature 0: loan_to_asset (from credit/GDP, rescaled)
    if len(wb_data.get("loan_to_asset", pd.Series(dtype=float))) >= 2:
        raw = _annual_to_quarterly(wb_data["loan_to_asset"], dates)
        # Credit/GDP is in %, typically 50-200%. Rescale to loan_to_asset fraction ~0.3-0.8
        features[:, 0] = np.clip(raw / 200.0, 0.1, 0.95)
        sources["loan_to_asset"] = f"World Bank GFDD.DI.01 ({iso3})"
    else:
        sources["loan_to_asset"] = "MISSING"

    # Feature 1: equity_ratio (from capital/assets, already in %)
    if len(wb_data.get("equity_ratio", pd.Series(dtype=float))) >= 2:
        raw = _annual_to_quarterly(wb_data["equity_ratio"], dates)
        features[:, 1] = np.clip(raw / 100.0, 0.02, 0.30)  # convert % to fraction
        sources["equity_ratio"] = f"World Bank FB.BNK.CAPA.ZS ({iso3})"
    else:
        sources["equity_ratio"] = "MISSING"

    # Feature 2: npl_ratio (already in %)
    if len(wb_data.get("npl_ratio", pd.Series(dtype=float))) >= 2:
        raw = _annual_to_quarterly(wb_data["npl_ratio"], dates)
        features[:, 2] = np.clip(raw / 100.0, 0.0, 0.30)  # convert % to fraction
        sources["npl_ratio"] = f"World Bank FB.AST.NPER.ZS ({iso3})"
    else:
        sources["npl_ratio"] = "MISSING"

    # Feature 3: roa (GFDD profitability, in %)
    if len(wb_data.get("roa", pd.Series(dtype=float))) >= 2:
        raw = _annual_to_quarterly(wb_data["roa"], dates)
        # GFDD.SI.01 is "interest margin" or return, typically 5-30%
        # Scale to ROA-like units (fraction ~0.001-0.02)
        features[:, 3] = np.clip(raw / 1000.0, -0.05, 0.05)
        sources["roa"] = f"World Bank GFDD.SI.01 ({iso3})"
    else:
        sources["roa"] = "MISSING"

    # Feature 4: funding_cost
    # Priority: ECB MIR (monthly) > World Bank lending rate (annual)
    ecb_used = False
    if ecb_cc is not None:
        ecb_data = _ecb_mir_lending_rate(ecb_cc)
        if len(ecb_data) >= 12:
            raw = _monthly_to_quarterly(ecb_data, dates)
            features[:, 4] = np.clip(raw / 100.0, 0.0, 0.20)  # % to fraction
            sources["funding_cost"] = f"ECB MIR lending rate ({ecb_cc})"
            ecb_used = True

    if not ecb_used:
        fc = wb_data.get("funding_cost", pd.Series(dtype=float))
        if len(fc) >= 2:
            raw = _annual_to_quarterly(fc, dates)
            features[:, 4] = np.clip(raw / 100.0, 0.0, 0.20)
            sources["funding_cost"] = f"World Bank lending/deposit rate ({iso3})"
        else:
            sources["funding_cost"] = "MISSING"

    return features, sources


# ---------------------------------------------------------------------------
# Main panel builder
# ---------------------------------------------------------------------------
def build_gsib_panel_real(
    quarters_start: str  = "2005-01-01",   # limited by World Bank coverage
    quarters_end:   str  = "2023-12-31",
    force_refresh:  bool = False,
    min_coverage:   float = 0.50,  # minimum non-NaN fraction required
    verbose:        bool = True,
) -> Dict:
    """
    Build a real-data G-SIB panel.

    Unlike gsib_loader.py, no synthetic data is generated.
    Non-US G-SIBs use country-level banking-sector aggregates
    from World Bank GFDD + ECB MIR.

    Parameters
    ----------
    quarters_start : start of panel (2005+ recommended for World Bank coverage)
    quarters_end   : end of panel
    force_refresh  : bypass caches
    min_coverage   : minimum fraction of non-NaN quarters to include a bank

    Returns
    -------
    dict with X (T,N,d), dates, meta, feature_names, etc.
    """
    dates = pd.date_range(quarters_start, quarters_end, freq="QE")
    T = len(dates)

    cache_path = CACHE_DIR / "gsib_real_panel.npz"
    meta_cache = CACHE_DIR / "gsib_real_meta.json"

    if not force_refresh and cache_path.exists() and meta_cache.exists():
        if verbose:
            print("[gsib_real] Loading real G-SIB panel from cache...")
        d = np.load(cache_path)
        with open(meta_cache) as f:
            meta = json.load(f)
        X = d["X"]
        n_us = sum(1 for m in meta if m["tier"] == 1)
        n_nonus = len(meta) - n_us
        if verbose:
            print(f"  Cached: T={X.shape[0]}, N={X.shape[1]}, d={X.shape[2]}")
            print(f"  US (FDIC): {n_us}, Non-US (World Bank): {n_nonus}")
        return {
            "X": X, "dates": dates, "meta": meta,
            "n_gsib": len(meta), "n_us": n_us, "n_non_us": n_nonus,
            "feature_names": FEATURE_NAMES,
        }

    if verbose:
        print(f"[gsib_real] Building REAL G-SIB panel: T={T} quarters ({quarters_start} to {quarters_end})")
        print(f"  US G-SIBs: FDIC call-report (individual bank-level)")
        print(f"  Non-US G-SIBs: World Bank GFDD + ECB MIR (country banking-sector aggregates)")

    X_list = []
    meta_out = []
    n_us = 0
    n_nonus = 0
    skipped = []

    for i, bank in enumerate(GSIB_CATALOGUE):
        name   = bank["name"]
        region = bank["region"]
        cert   = bank.get("cert")
        tier   = bank["tier"]
        iso3   = bank["iso"]
        ecb_cc = bank.get("ecb_cc")

        if tier == 1 and cert is not None:
            # Real FDIC data
            if verbose:
                print(f"  [{i+1:2d}] {name:30s} FDIC CERT={cert}")
            X_bank = _build_us_gsib_series(cert, dates)
            coverage = float((~np.isnan(X_bank)).all(axis=1).mean())
            data_source = "fdic_call_report"

            if coverage < min_coverage:
                if verbose:
                    print(f"       -> SKIPPED (coverage {coverage:.1%} < {min_coverage:.0%})")
                skipped.append(name)
                continue

            n_us += 1
            if verbose:
                print(f"       -> OK (coverage {coverage:.1%})")
        else:
            # Real World Bank + ECB data
            if verbose:
                ecb_str = f" + ECB MIR ({ecb_cc})" if ecb_cc else ""
                print(f"  [{i+1:2d}] {name:30s} World Bank ({iso3}){ecb_str}")
            X_bank, feat_sources = _build_real_nonus_gsib_series(iso3, ecb_cc, dates)
            coverage = float((~np.isnan(X_bank)).any(axis=1).mean())
            n_missing = sum(1 for v in feat_sources.values() if v == "MISSING")
            data_source = "world_bank_country_aggregate"

            if coverage < min_coverage or n_missing >= 3:
                if verbose:
                    print(f"       -> SKIPPED (coverage {coverage:.1%}, {n_missing}/5 features missing)")
                skipped.append(name)
                continue

            n_nonus += 1
            if verbose:
                avail = [k for k, v in feat_sources.items() if v != "MISSING"]
                miss  = [k for k, v in feat_sources.items() if v == "MISSING"]
                print(f"       -> OK (coverage {coverage:.1%}, available: {avail}, missing: {miss})")

        # Fill remaining NaNs: forward-fill then backward-fill per feature
        for d_feat in range(X_bank.shape[1]):
            col = pd.Series(X_bank[:, d_feat])
            col = col.ffill().bfill()
            # If still NaN (entire column missing), fill with cross-sectional median later
            X_bank[:, d_feat] = col.values

        X_list.append(X_bank)
        meta_entry = {
            "name": name, "region": region, "iso": iso3,
            "cert": cert, "tier": tier,
            "data_source": data_source,
            "coverage": round(coverage, 3),
        }
        if tier == 2:
            meta_entry["ecb_cc"] = ecb_cc
        meta_out.append(meta_entry)

    if not X_list:
        raise RuntimeError("No G-SIBs passed the coverage filter!")

    X_out = np.stack(X_list, axis=1)  # (T, N, d)

    # Cross-sectional NaN fill: replace any remaining NaN with cross-bank median
    for t in range(X_out.shape[0]):
        for d_feat in range(X_out.shape[2]):
            col = X_out[t, :, d_feat]
            nan_mask = np.isnan(col)
            if nan_mask.any() and (~nan_mask).any():
                X_out[t, nan_mask, d_feat] = np.nanmedian(col)
            elif nan_mask.all():
                X_out[t, :, d_feat] = 0.0  # last resort

    N_out = X_out.shape[1]

    if verbose:
        print(f"\n  ===== REAL G-SIB PANEL =====")
        print(f"  Shape: T={T}, N={N_out}, d={X_out.shape[2]}")
        print(f"  US (FDIC bank-level): {n_us}")
        print(f"  Non-US (WB country-aggregate): {n_nonus}")
        print(f"  Skipped: {len(skipped)} ({skipped})")
        print(f"  Date range: {dates[0].date()} -> {dates[-1].date()}")

    # Cache
    np.savez_compressed(cache_path, X=X_out)
    with open(meta_cache, "w") as f:
        json.dump(meta_out, f, indent=2)

    return {
        "X": X_out, "dates": dates, "meta": meta_out,
        "n_gsib": N_out, "n_us": n_us, "n_non_us": n_nonus,
        "feature_names": FEATURE_NAMES,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    panel = build_gsib_panel_real(verbose=True, force_refresh=True)
    X     = panel["X"]
    dates = panel["dates"]
    meta  = panel["meta"]

    print(f"\nPanel shape: {X.shape}")
    print(f"Date range: {dates[0].date()} -> {dates[-1].date()}")

    print(f"\nSample data (first bank, Q1-Q4 2008):")
    mask_2008 = (dates >= pd.Timestamp("2008-01-01")) & (dates <= pd.Timestamp("2008-12-31"))
    if mask_2008.any():
        print(pd.DataFrame(
            X[mask_2008, 0, :],
            columns=FEATURE_NAMES,
            index=dates[mask_2008],
        ))

    print(f"\nAll banks and sources:")
    for m in meta:
        print(f"  {m['name']:30s}  {m['region']:5s}  source={m['data_source']:35s}  coverage={m['coverage']:.0%}")
