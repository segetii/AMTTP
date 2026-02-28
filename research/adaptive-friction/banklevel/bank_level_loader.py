"""
bank_level_loader.py
====================
Loads FDIC call-report data at the INDIVIDUAL BANK level (not SPECGRP aggregates).

Uses the FDIC SDI REST API:
  GET /institutions  – filter to top-N banks by total assets, get CERT IDs
  GET /financials    – per-quarter financial ratios for each CERT

Produces:
  X(t): (T, N, d)  quarterly state matrix for top-N banks
  meta: list of dicts with bank name, cert, state, charter type

This replaces the 7-bucket SPECGRP approach with institution-level panels,
giving a credible network story.
"""
from __future__ import annotations
import json
import time
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional

import requests

# ── Configuration ─────────────────────────────────────────────────────────────
FDIC_BASE        = "https://banks.data.fdic.gov/api"
CACHE_DIR        = Path(__file__).parent / "fdic_bank_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Fields requested per quarter per institution
BANK_FIELDS = [
    "CERT", "REPDTE", "ASSET", "LNLSNET", "EQ", "NCLNLS", "NETINC", "EINTEXP",
]
# Derived feature names (same 5 ratios as SPECGRP pipeline)
FEATURE_NAMES = [
    "loan_to_asset",   # LNLSNET / ASSET
    "equity_ratio",    # EQ / ASSET
    "npl_ratio",       # NCLNLS / LNLSNET
    "roa",             # NETINC / ASSET
    "funding_cost",    # EINTEXP / LNLSNET
]


# ── Institution catalogue ─────────────────────────────────────────────────────

def fetch_top_banks(
    n: int = 50,
    min_asset_millions: float = 10_000,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Return a DataFrame of the top-N banks by total assets (latest available quarter).
    Columns: CERT, INSTNAME, STNAME, SPECGRP.
    """
    cache_path = CACHE_DIR / f"top{n}_banks.json"
    if not force_refresh and cache_path.exists():
        with open(cache_path) as f:
            data = json.load(f)
        print(f"[bank_loader] Top-{n} banks loaded from cache ({len(data)} entries)")
        return pd.DataFrame(data)

    print(f"[bank_loader] Fetching top-{n} banks from FDIC /institutions …")
    params = {
        "filters":  f"ACTIVE:1 AND ASSET:[{min_asset_millions} TO 99999999]",
        "fields":   "CERT,INSTNAME,STNAME,SPECGRP,ASSET",
        "sort_by":  "ASSET",
        "sort_order": "DESC",
        "limit":    n,
        "offset":   0,
        "output":   "json",
    }
    resp = requests.get(f"{FDIC_BASE}/institutions", params=params, timeout=30)
    resp.raise_for_status()
    data_raw = resp.json().get("data", [])
    records  = [d["data"] for d in data_raw if "data" in d]
    with open(cache_path, "w") as f:
        json.dump(records, f)
    df = pd.DataFrame(records)
    print(f"[bank_loader] Fetched {len(df)} institutions")
    return df


# ── Per-institution time series ───────────────────────────────────────────────

def _quarter_dates(start: str = "1990-03-31", end: str = "2024-12-31") -> List[str]:
    """Generate quarter-end dates YYYYMMDD."""
    dates = pd.date_range(start=start, end=end, freq="QE")
    return [d.strftime("%Y%m%d") for d in dates]


def fetch_institution_timeseries(
    cert: int,
    fields: List[str] = BANK_FIELDS,
    start: str = "1990-03-31",
    end:   str = "2024-12-31",
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Fetch all quarterly call-report rows for a single bank (identified by CERT).
    Returns a DataFrame indexed by REPDTE (as Timestamp).
    """
    cache_path = CACHE_DIR / f"cert_{cert}.json"
    if not force_refresh and cache_path.exists():
        with open(cache_path) as f:
            raw = json.load(f)
        df = pd.DataFrame(raw)
        if not df.empty:
            df["REPDTE"] = pd.to_datetime(df["REPDTE"])
            return df.set_index("REPDTE").sort_index()
        return df

    fields_str = ",".join(fields)
    params = {
        "filters":    f"CERT:{cert}",
        "fields":     fields_str,
        "sort_by":    "REPDTE",
        "sort_order": "ASC",
        "limit":      500,
        "offset":     0,
        "output":     "json",
    }
    all_rows = []
    while True:
        try:
            resp = requests.get(f"{FDIC_BASE}/financials", params=params, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print(f"  [bank_loader] CERT {cert} error: {e}")
            break
        chunk   = resp.json()
        records = [d["data"] for d in chunk.get("data", []) if "data" in d]
        all_rows.extend(records)
        if len(records) < params["limit"]:
            break
        params["offset"] += params["limit"]
        time.sleep(0.15)

    with open(cache_path, "w") as f:
        json.dump(all_rows, f)

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["REPDTE"] = pd.to_datetime(df["REPDTE"].astype(str))
    return df.set_index("REPDTE").sort_index()


# ── Feature computation ───────────────────────────────────────────────────────

def compute_features(df: pd.DataFrame) -> pd.Series | None:
    """
    Compute the 5-element feature vector from raw call-report columns.
    Returns a DataFrame with columns = FEATURE_NAMES; same index as df.
    Returns None if required columns are missing.
    """
    required = ["ASSET", "LNLSNET", "EQ", "NCLNLS", "NETINC", "EINTEXP"]
    for col in required:
        if col not in df.columns:
            return None

    df = df[required].apply(pd.to_numeric, errors="coerce")

    out = pd.DataFrame(index=df.index)
    eps = 1e-6  # avoid division by zero
    out["loan_to_asset"] = df["LNLSNET"] / (df["ASSET"] + eps)
    out["equity_ratio"]  = df["EQ"]       / (df["ASSET"] + eps)
    out["npl_ratio"]     = df["NCLNLS"]   / (df["LNLSNET"] + eps)
    out["roa"]           = df["NETINC"]   / (df["ASSET"] + eps)
    out["funding_cost"]  = df["EINTEXP"]  / (df["LNLSNET"] + eps)
    return out


# ── Master panel builder ──────────────────────────────────────────────────────

def build_bank_panel(
    n_banks: int = 30,
    start: str = "1990-03-31",
    end:   str = "2024-12-31",
    min_coverage: float = 0.70,   # require ≥70% quarterly coverage
    force_refresh: bool = False,
) -> Dict:
    """
    Build the joint state matrix X(t) ∈ ℝ^{N × d} for institution-level data.

    Returns dict with keys:
      X:          np.ndarray (T, N, d)
      dates:      pd.DatetimeIndex
      bank_meta:  list of dicts (cert, name, state, specgrp)
      feature_names: list[str]
      n_banks_actual: int
    """
    # Step 1: get bank catalogue
    banks_df = fetch_top_banks(n=n_banks * 2, force_refresh=force_refresh)  # oversample
    if banks_df.empty:
        raise RuntimeError("[bank_loader] Could not fetch institution list from FDIC")

    target_dates = pd.to_datetime(
        pd.date_range(start=start, end=end, freq="QE")
    )
    T = len(target_dates)
    d = len(FEATURE_NAMES)

    # Step 2: for each institution, fetch and compute features
    bank_timeseries: Dict[int, pd.DataFrame] = {}
    bank_meta: List[Dict] = []
    certs_tried = 0

    for _, row in banks_df.iterrows():
        if len(bank_timeseries) >= n_banks:
            break
        cert = int(row.get("CERT", 0))
        if cert == 0:
            continue
        certs_tried += 1

        print(f"  [bank_loader] Fetching CERT {cert} — {row.get('INSTNAME', '?')} …")
        raw = fetch_institution_timeseries(cert, start=start, end=end,
                                           force_refresh=force_refresh)
        if raw.empty:
            continue

        feats = compute_features(raw)
        if feats is None or feats.empty:
            continue

        # require minimum quarterly coverage
        feats = feats.reindex(target_dates, method="nearest", tolerance="45D")
        coverage = feats.notna().all(axis=1).mean()
        if coverage < min_coverage:
            print(f"  [bank_loader]   → skipped (coverage {coverage:.1%} < {min_coverage:.0%})")
            continue

        # forward-fill small gaps
        feats = feats.ffill(limit=2).fillna(0.0)
        bank_timeseries[cert] = feats
        bank_meta.append({
            "cert":    cert,
            "name":    row.get("INSTNAME", str(cert)),
            "state":   row.get("STNAME", ""),
            "specgrp": row.get("SPECGRP", ""),
        })
        print(f"  [bank_loader]   → included (coverage {coverage:.1%})")

    N = len(bank_timeseries)
    if N == 0:
        raise RuntimeError("[bank_loader] No institutions passed coverage filter")

    print(f"\n[bank_loader] Final panel: T={T}, N={N}, d={d}")

    # Step 3: assemble (T, N, d) tensor
    X = np.zeros((T, N, d))
    for i, (cert, feats) in enumerate(bank_timeseries.items()):
        X[:, i, :] = feats[FEATURE_NAMES].values

    return {
        "X":               X,
        "dates":           target_dates,
        "bank_meta":       bank_meta,
        "feature_names":   FEATURE_NAMES,
        "n_banks_actual":  N,
    }


if __name__ == "__main__":
    panel = build_bank_panel(n_banks=20)
    print(f"\nPanel shape: {panel['X'].shape}")
    print(f"Banks: {[b['name'] for b in panel['bank_meta'][:5]]} …")
