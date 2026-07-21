"""
Binance Microstructure Data Fetcher
====================================
Two data tiers:

  TIER 1 — FROM KLINES (free, full history from 2020+)
    • taker_buy_ratio = r[9] / r[5]  — fraction of volume from aggressive buyers

  TIER 2 — FUNDING RATE REST API (full history from 2019+)
    • funding_rate    = 8h rate forward-filled to 1h bars

  TIER 3 — BINANCE DATA VISION (daily ZIPs, full history from 2020+)
    • oi_usd      = sum_open_interest_value   (closing OI per 1h)
    • lsr         = count_long_short_ratio    (global L/S account ratio, mean per 1h)
    • top_lsr     = sum_toptrader_long_short_ratio  (smart money, mean per 1h)
    • taker_ls    = sum_taker_long_short_vol_ratio  (taker volume skew, mean per 1h)

  NOTE: The Binance REST openInterestHist/globalLongShortAccountRatio endpoints
  only support very recent startTime, so Data Vision is the only viable source
  for multi-year backtests.

All results cached as .pkl in C:\\amttp\\data\\.

Usage:
    from run_crypto_microstructure_data import load_microstructure, prefetch_all
    prefetch_all(["BTCUSDT", "SOLUSDT"])       # downloads & caches everything
    ms = load_microstructure("BTCUSDT", "2023-01-01", "2026-06-01")
"""
from __future__ import annotations

import io
import time
import zipfile
import pickle
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

CACHE_DIR = Path(r"C:\amttp\data")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DV_BASE = "https://data.binance.vision/data/futures/um/daily/metrics"

# ─── helpers ──────────────────────────────────────────────────────────────────

def _ms(ts: str | pd.Timestamp) -> int:
    return int(pd.Timestamp(ts).timestamp() * 1000)


def _utc(ts: str | pd.Timestamp) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def _paginate_klines(symbol: str, start_ms: int, end_ms: int,
                     max_retries: int = 3) -> list[list]:
    """Paginate klines endpoint (returns list-of-lists, max 1500/call)."""
    url = "https://fapi.binance.com/fapi/v1/klines"
    records = []
    p = {"symbol": symbol, "interval": "1h", "limit": 1500,
         "startTime": start_ms, "endTime": end_ms}
    while True:
        for attempt in range(max_retries):
            try:
                r = requests.get(url, params=p, timeout=20)
                data = r.json()
                break
            except Exception:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2)
        if not isinstance(data, list) or len(data) == 0:
            break
        records.extend(data)
        last_ts = int(data[-1][0])
        if last_ts >= end_ms or len(data) < 1500:
            break
        p["startTime"] = last_ts + 1
        time.sleep(0.04)
    return records


def _paginate_funding(symbol: str, start_ms: int, end_ms: int,
                      max_retries: int = 3) -> list[dict]:
    """Paginate fundingRate endpoint (list-of-dicts, max 1000/call)."""
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    records = []
    p = {"symbol": symbol, "limit": 1000,
         "startTime": start_ms, "endTime": end_ms}
    while True:
        for attempt in range(max_retries):
            try:
                r = requests.get(url, params=p, timeout=20)
                data = r.json()
                break
            except Exception:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2)
        if not isinstance(data, list) or len(data) == 0:
            break
        records.extend(data)
        last_ts = int(data[-1]["fundingTime"])
        if last_ts >= end_ms or len(data) < 1000:
            break
        p["startTime"] = last_ts + 1
        time.sleep(0.04)
    return records


# ─── TIER 1: taker buy ratio from klines ─────────────────────────────────────

def fetch_taker_buy_ratio(symbol: str, start: str, end: str) -> pd.Series:
    """
    Returns taker_buy_volume / total_volume per 1h bar  (0-1 scale).
    > 0.5 = net buy pressure, < 0.5 = net sell pressure.
    Uses r[9] from the existing klines API call -- no extra cost.
    """
    cache_path = CACHE_DIR / f"binance_futures_{symbol}_1h_tbr.pkl"
    start_ms   = _ms(start)
    end_ms     = _ms(end)

    cached: pd.Series | None = None
    if cache_path.exists():
        try:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
        except Exception:
            cached = None

    # Determine which ranges need fetching
    expected = pd.Timestamp.utcnow().floor("h") - pd.Timedelta(hours=1)
    fetch_ranges: list[tuple[int, int]] = []
    if cached is None:
        fetch_ranges.append((start_ms, end_ms))
    else:
        cache_start = cached.index[0]
        cache_end   = cached.index[-1]
        # Extend backward if needed
        if cache_start > _utc(start) + pd.Timedelta(hours=2):
            fetch_ranges.append((start_ms, int(cache_start.timestamp() * 1000) - 1))
        # Extend forward if needed
        if cache_end < expected:
            fetch_ranges.append((int(cache_end.timestamp() * 1000) + 1, end_ms))
        if not fetch_ranges:
            print(f"  {symbol} TBR [CACHE ok]  {cache_start.date()} -> {cache_end.date()}")
            mask = (cached.index >= _utc(start)) & (cached.index <= _utc(end))
            return cached[mask]
        d0 = pd.Timestamp(fetch_ranges[0][0], unit='ms', tz='UTC').date()
        d1 = pd.Timestamp(fetch_ranges[-1][1], unit='ms', tz='UTC').date()
        print(f"  {symbol} TBR [extending: {d0} -> {d1}]")

    all_new_rows: list[list] = []
    for (fstart, fend) in fetch_ranges:
        all_new_rows.extend(_paginate_klines(symbol, fstart, fend))
    rows = all_new_rows
    if not rows:
        if cached is not None:
            mask = (cached.index >= _utc(start)) & (cached.index <= _utc(end))
            return cached[mask]
        return pd.Series(dtype=float, name="taker_buy_ratio")

    ts_arr  = pd.to_datetime([int(r[0]) for r in rows], unit="ms", utc=True)
    vol_arr = np.array([float(r[5]) for r in rows])
    tbv_arr = np.array([float(r[9]) for r in rows])
    tbr_arr = np.where(vol_arr > 0, tbv_arr / vol_arr, 0.5)
    new_s   = pd.Series(tbr_arr, index=ts_arr, name="taker_buy_ratio")

    if cached is not None:
        combined = pd.concat([cached, new_s])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        combined = new_s.sort_index()

    with open(cache_path, "wb") as f:
        pickle.dump(combined, f)
    print(f"  {symbol} TBR [saved]  {combined.index[0].date()} -> {combined.index[-1].date()}  n={len(combined):,}")
    mask = (combined.index >= _utc(start)) & (combined.index <= _utc(end))
    return combined[mask]


# ─── TIER 2: funding rate (REST, full history) ────────────────────────────────

def fetch_funding_rate_1h(symbol: str, start: str, end: str) -> pd.Series:
    """
    Returns 8h funding rate forward-filled to 1h bars.
    Positive = longs pay shorts (bullish crowding).
    Negative = shorts pay longs (bearish crowding / depressed market).
    """
    cache_path = CACHE_DIR / f"binance_futures_{symbol}_1h_fr.pkl"
    start_ms   = _ms(start)
    end_ms     = _ms(end)

    cached: pd.Series | None = None
    if cache_path.exists():
        try:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
        except Exception:
            cached = None

    expected = pd.Timestamp.utcnow().floor("h") - pd.Timedelta(hours=8)
    fetch_ranges: list[tuple[int, int]] = []
    if cached is None:
        fetch_ranges.append((start_ms, end_ms))
    else:
        cache_start = cached.index[0]
        cache_end   = cached.index[-1]
        if cache_start > _utc(start) + pd.Timedelta(hours=24):
            fetch_ranges.append((start_ms, int(cache_start.timestamp() * 1000) - 1))
        if cache_end < expected:
            fetch_ranges.append((int(cache_end.timestamp() * 1000) + 1, end_ms))
        if not fetch_ranges:
            print(f"  {symbol} FR  [CACHE ok]  {cache_start.date()} -> {cache_end.date()}")
            idx = pd.date_range(start=_utc(start), end=_utc(end), freq="1h")
            return cached.reindex(idx, method="ffill").dropna()
        print(f"  {symbol} FR  [extending {len(fetch_ranges)} range(s)]")

    all_new_rows: list[dict] = []
    for (fstart, fend) in fetch_ranges:
        all_new_rows.extend(_paginate_funding(symbol, fstart, fend))
    rows = all_new_rows
    if not rows:
        if cached is not None:
            idx = pd.date_range(start=_utc(start), end=_utc(end), freq="1h")
            return cached.reindex(idx, method="ffill").dropna()
        return pd.Series(dtype=float, name="funding_rate")

    ts_arr = pd.to_datetime([int(r["fundingTime"]) for r in rows], unit="ms", utc=True)
    fr_arr = np.array([float(r["fundingRate"]) for r in rows])
    new_s  = pd.Series(fr_arr, index=ts_arr, name="funding_rate")

    if cached is not None:
        combined = pd.concat([cached, new_s])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        combined = new_s.sort_index()

    with open(cache_path, "wb") as f:
        pickle.dump(combined, f)
    print(f"  {symbol} FR  [saved]  8h bars: {len(combined):,}")

    idx = pd.date_range(start=_utc(start), end=_utc(end), freq="1h")
    return combined.reindex(idx, method="ffill").dropna()


# ─── TIER 3: Binance Data Vision metrics (OI + LSR) ──────────────────────────

def _dv_url(symbol: str, d: date) -> str:
    return f"{DV_BASE}/{symbol}/{symbol}-metrics-{d}.zip"


def _fetch_dv_day(symbol: str, d: date, session: requests.Session,
                  max_retries: int = 3) -> pd.DataFrame | None:
    """Download one day of metrics CSV from Binance Data Vision. Returns 5-min df."""
    url = _dv_url(symbol, d)
    for attempt in range(max_retries):
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 404:
                return None
            if r.status_code != 200:
                time.sleep(1)
                continue
            z = zipfile.ZipFile(io.BytesIO(r.content))
            with z.open(z.namelist()[0]) as f:
                df = pd.read_csv(f, parse_dates=["create_time"])
                df["create_time"] = pd.to_datetime(df["create_time"], utc=True)
                df = df.set_index("create_time").sort_index()
                cols = ["sum_open_interest_value",
                        "count_long_short_ratio",
                        "sum_toptrader_long_short_ratio",
                        "sum_taker_long_short_vol_ratio"]
                df = df[[c for c in cols if c in df.columns]]
                df = df.rename(columns={
                    "sum_open_interest_value":        "oi_usd",
                    "count_long_short_ratio":          "lsr",
                    "sum_toptrader_long_short_ratio":  "top_lsr",
                    "sum_taker_long_short_vol_ratio":  "taker_ls",
                })
                df = df.apply(pd.to_numeric, errors="coerce")
                return df
        except Exception:
            if attempt == max_retries - 1:
                return None
            time.sleep(1)
    return None


def fetch_dv_metrics(symbol: str, start: str, end: str,
                     batch_size: int = 30) -> pd.DataFrame:
    """
    Downloads daily metrics ZIPs from Binance Data Vision,
    aggregates to 1h, caches result.

    Columns: oi_usd, lsr, top_lsr, taker_ls
    All at 1h resolution (5-min source aggregated per hour).
    """
    cache_path = CACHE_DIR / f"binance_futures_{symbol}_1h_dv_metrics.pkl"

    cached: pd.DataFrame | None = None
    if cache_path.exists():
        try:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            print(f"  {symbol} DV  [CACHE {len(cached):,} rows]  "
                  f"{cached.index[0].date()} -> {cached.index[-1].date()}")
        except Exception:
            cached = None

    start_d = pd.Timestamp(start).date()
    end_d   = min(pd.Timestamp(end).date(),
                  (pd.Timestamp.utcnow() - pd.Timedelta(days=1)).date())
    if cached is not None:
        cache_end_d = cached.index[-1].date()
        need_start  = cache_end_d + timedelta(days=1)
    else:
        need_start = start_d

    if need_start > end_d:
        print(f"  {symbol} DV  [up-to-date]")
        if cached is None:
            return pd.DataFrame()
        mask = (cached.index >= _utc(start)) & (cached.index <= _utc(end))
        return cached[mask]

    all_dates = []
    d = need_start
    while d <= end_d:
        all_dates.append(d)
        d += timedelta(days=1)

    print(f"  {symbol} DV  [fetching {len(all_dates)} days: {need_start} -> {end_d}]", flush=True)

    new_frames: list[pd.DataFrame] = []
    session = requests.Session()
    total = len(all_dates)
    for i in range(0, total, batch_size):
        batch = all_dates[i:i + batch_size]
        for day_d in batch:
            df_day = _fetch_dv_day(symbol, day_d, session)
            if df_day is not None and not df_day.empty:
                new_frames.append(df_day)
        done = min(i + batch_size, total)
        print(f"    {symbol} DV  {done}/{total} ({done/total*100:.0f}%)", flush=True)
        time.sleep(0.05)
    session.close()

    if not new_frames:
        print(f"  {symbol} DV  [no new data]")
        if cached is None:
            return pd.DataFrame()
        mask = (cached.index >= _utc(start)) & (cached.index <= _utc(end))
        return cached[mask]

    raw_5m = pd.concat(new_frames).sort_index()
    raw_5m = raw_5m[~raw_5m.index.duplicated(keep="last")]
    hourly = raw_5m.resample("1h").agg({
        "oi_usd":   "last",
        "lsr":      "mean",
        "top_lsr":  "mean",
        "taker_ls": "mean",
    }).dropna(how="all")

    if cached is not None:
        combined = pd.concat([cached, hourly])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        combined = hourly

    with open(cache_path, "wb") as f:
        pickle.dump(combined, f)
    print(f"  {symbol} DV  [saved] {combined.index[0].date()} -> {combined.index[-1].date()}  "
          f"n_1h={len(combined):,}")

    mask = (combined.index >= _utc(start)) & (combined.index <= _utc(end))
    return combined[mask]


# ─── Master loader ────────────────────────────────────────────────────────────

def load_microstructure(
    symbol: str,
    start:  str = "2021-01-01",
    end:    str = "2026-06-01",
) -> pd.DataFrame:
    """
    Returns a DataFrame with derived microstructure features aligned to UTC 1h bars.

    Base columns
    ------------
    taker_buy_ratio  -- fraction of volume from aggressive buyers (0-1)
    funding_rate     -- 8h rate, forward-filled to 1h
    oi_usd           -- open interest USD notional (closing per 1h)
    lsr              -- global long/short account ratio
    top_lsr          -- top-trader long/short ratio (smart money)
    taker_ls         -- taker buy/sell volume ratio

    Derived z-score features (WIN=480h rolling)
    -------------------------------------------
    tbr_z            -- z-score of (taker_buy_ratio - 0.5)
    funding_z        -- z-score of funding_rate (720h window)
    oi_pct_1h        -- OI pct_change per 1h
    oi_pct_24h       -- OI pct_change over 24h
    oi_z             -- z-score of oi_pct_1h
    lsr_z            -- z-score of log(lsr)
    top_lsr_z        -- z-score of log(top_lsr)
    taker_ls_z       -- z-score of log(taker_ls)
    """
    print(f"\n  === microstructure {symbol}  {start} -> {end} ===")

    tbr = fetch_taker_buy_ratio(symbol, start, end)
    fr  = fetch_funding_rate_1h(symbol, start, end)
    dv  = fetch_dv_metrics(symbol, start, end)

    idx = pd.date_range(start=_utc(start), end=_utc(end), freq="1h")

    def _align_s(s: pd.Series, name: str) -> pd.Series:
        if s.empty:
            return pd.Series(np.nan, index=idx, name=name)
        s2 = s.copy().rename(name)
        if s2.index.tz is None:
            s2.index = s2.index.tz_localize("UTC")
        return s2.reindex(idx, method="ffill")

    def _align_col(df: pd.DataFrame, col: str) -> pd.Series:
        if df.empty or col not in df.columns:
            return pd.Series(np.nan, index=idx, name=col)
        s = df[col].copy()
        if s.index.tz is None:
            s.index = s.index.tz_localize("UTC")
        return s.reindex(idx, method="ffill").rename(col)

    df = pd.DataFrame({
        "taker_buy_ratio": _align_s(tbr, "taker_buy_ratio"),
        "funding_rate":    _align_s(fr,  "funding_rate"),
        "oi_usd":          _align_col(dv, "oi_usd"),
        "lsr":             _align_col(dv, "lsr"),
        "top_lsr":         _align_col(dv, "top_lsr"),
        "taker_ls":        _align_col(dv, "taker_ls"),
    })

    WIN    = 480
    FR_WIN = 720

    # tbr z-score
    tbr_c  = df["taker_buy_ratio"] - 0.5
    tbr_mu = tbr_c.rolling(WIN, min_periods=72).mean()
    tbr_sd = tbr_c.rolling(WIN, min_periods=72).std()
    df["tbr_z"] = (tbr_c - tbr_mu) / (tbr_sd + 1e-9)

    # funding z-score
    fr_mu = df["funding_rate"].rolling(FR_WIN, min_periods=72).mean()
    fr_sd = df["funding_rate"].rolling(FR_WIN, min_periods=72).std()
    df["funding_z"] = (df["funding_rate"] - fr_mu) / (fr_sd + 1e-9)

    # OI and L/S features (only if DV data available)
    if df["oi_usd"].notna().sum() > 100:
        df["oi_pct_1h"]  = df["oi_usd"].pct_change(1, fill_method=None)
        df["oi_pct_24h"] = df["oi_usd"].pct_change(24, fill_method=None)
        oi_mu = df["oi_pct_1h"].rolling(WIN, min_periods=72).mean()
        oi_sd = df["oi_pct_1h"].rolling(WIN, min_periods=72).std()
        df["oi_z"] = (df["oi_pct_1h"] - oi_mu) / (oi_sd + 1e-9)

        lsr_log = np.log(df["lsr"].clip(lower=1e-3))
        lsr_mu  = lsr_log.rolling(WIN, min_periods=72).mean()
        lsr_sd  = lsr_log.rolling(WIN, min_periods=72).std()
        df["lsr_z"] = (lsr_log - lsr_mu) / (lsr_sd + 1e-9)

        top_log = np.log(df["top_lsr"].clip(lower=1e-3))
        top_mu  = top_log.rolling(WIN, min_periods=72).mean()
        top_sd  = top_log.rolling(WIN, min_periods=72).std()
        df["top_lsr_z"] = (top_log - top_mu) / (top_sd + 1e-9)

        tls_log = np.log(df["taker_ls"].clip(lower=1e-3))
        tls_mu  = tls_log.rolling(WIN, min_periods=72).mean()
        tls_sd  = tls_log.rolling(WIN, min_periods=72).std()
        df["taker_ls_z"] = (tls_log - tls_mu) / (tls_sd + 1e-9)

    for col in df.columns:
        nan_pct = df[col].isna().mean()
        if nan_pct > 0.01:
            valid = int((1 - nan_pct) * len(df))
            print(f"    {col}: {nan_pct:.0%} NaN  ({valid:,} valid bars)")

    print(f"  === {symbol} done  shape={df.shape} ===")
    return df


def prefetch_all(symbols: list[str] | None = None,
                 start: str = "2022-01-01",
                 end:   str = "2026-06-01") -> None:
    """Download and cache all microstructure data for all symbols."""
    if symbols is None:
        symbols = ["BTCUSDT", "SOLUSDT"]
    for sym in symbols:
        load_microstructure(sym, start=start, end=end)
        print()


# ─── CLI test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sym   = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    start = sys.argv[2] if len(sys.argv) > 2 else "2023-01-01"
    end   = sys.argv[3] if len(sys.argv) > 3 else "2026-06-01"
    ms_df = load_microstructure(sym, start=start, end=end)
    print(f"\nColumns : {list(ms_df.columns)}")
    print(f"Shape   : {ms_df.shape}")
    print(ms_df.dropna(subset=["taker_buy_ratio"]).tail(6).to_string())
    print()
    tbr_w = ms_df["taker_buy_ratio"].dropna().iloc[-168:]
    print(f"TBR  last-7d: min={tbr_w.min():.3f}  max={tbr_w.max():.3f}  mean={tbr_w.mean():.3f}")
    fr_w  = ms_df["funding_rate"].dropna().iloc[-24:]
    print(f"FR   last-24h mean: {fr_w.mean():.6f}")
    if "oi_pct_24h" in ms_df.columns:
        v = ms_df["oi_pct_24h"].dropna()
        if not v.empty:
            print(f"OI 24h (latest): {v.iloc[-1]:+.2%}")
    if "lsr" in ms_df.columns:
        v = ms_df["lsr"].dropna()
        if not v.empty:
            print(f"LSR latest: {v.iloc[-1]:.3f}  (>1=crowded long)")
