from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from run_crypto_pairs_v34_full_combined import build_1h_df
from run_crypto_godmode_v8_multiasset_shell import fetch_futures_ohlcv_symbol
from run_crypto_microstructure_data import load_microstructure


ASSETS = [
    ("eth", "ETHUSDT"),
    ("btc", "BTCUSDT"),
    ("sol", "SOLUSDT"),
]

MS_COLS = [
    "taker_buy_ratio",
    "funding_rate",
    "oi_usd",
    "lsr",
    "top_lsr",
    "taker_ls",
    "tbr_z",
    "funding_z",
    "oi_pct_1h",
    "oi_pct_24h",
    "oi_z",
    "lsr_z",
    "top_lsr_z",
    "taker_ls_z",
]

FUT_COLS = ["open", "high", "low", "close", "volume"]


def to_naive_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    idx = out.index
    if getattr(idx, "tz", None) is not None:
        out.index = idx.tz_convert("UTC").tz_localize(None)
    return out.sort_index()


def ensure_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = pd.NA
    return out[cols]


def add_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    roll60 = 60
    vol_win = 24

    ret_eth = out["ret_eth"].fillna(0)
    vol_eth = ret_eth.rolling(vol_win, min_periods=vol_win).std()
    cross_disp = out["spread_ret_eb"].abs()

    out["ret_eth_z"] = (ret_eth - ret_eth.rolling(roll60, min_periods=roll60).mean()) / (
        ret_eth.rolling(roll60, min_periods=roll60).std() + 1e-8
    )
    out["vol_eth_z"] = (vol_eth - vol_eth.rolling(roll60, min_periods=roll60).mean()) / (
        vol_eth.rolling(roll60, min_periods=roll60).std() + 1e-8
    )
    out["btc_dom_z"] = (out["btc_dom"] - out["btc_dom"].rolling(roll60, min_periods=roll60).mean()) / (
        out["btc_dom"].rolling(roll60, min_periods=roll60).std() + 1e-8
    )
    out["cross_disp_z"] = (
        cross_disp - cross_disp.rolling(roll60, min_periods=roll60).mean()
    ) / (cross_disp.rolling(roll60, min_periods=roll60).std() + 1e-8)

    return out


def build_unified_dataset(start: str, end: str, shift_microstructure_1h: bool = True) -> pd.DataFrame:
    base_df, _ = build_1h_df(start=start, end=end)
    base_df = to_naive_utc_index(base_df)
    base_df = add_engineered_features(base_df)

    unified = base_df.copy()

    for asset, symbol in ASSETS:
        # Futures OHLCV per asset
        fut = fetch_futures_ohlcv_symbol(symbol, start=start, end=end, interval="1h")
        fut = to_naive_utc_index(fut)
        fut = ensure_cols(fut, FUT_COLS).add_prefix(f"fut_{asset}_")

        # Microstructure per asset
        ms = load_microstructure(symbol, start=start, end=end)
        ms = to_naive_utc_index(ms)
        ms = ensure_cols(ms, MS_COLS)
        if shift_microstructure_1h:
            # Avoid lookahead by applying one-bar lag consistently
            ms = ms.shift(1)
        ms = ms.add_prefix(f"ms_{asset}_")

        unified = unified.join(fut, how="left")
        unified = unified.join(ms, how="left")

    unified = unified.sort_index()
    return unified


def main() -> None:
    parser = argparse.ArgumentParser(description="Build one unified 1h crypto dataset (spot + futures + microstructure).")
    parser.add_argument("--start", default="2021-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="2026-06-01", help="End date YYYY-MM-DD")
    parser.add_argument(
        "--out-dir",
        default=r"c:\amttp\data\processed",
        help="Output directory for parquet/csv",
    )
    parser.add_argument(
        "--no-ms-shift",
        action="store_true",
        help="Do not shift microstructure by 1h (not recommended for modeling).",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Building unified dataset...")
    df = build_unified_dataset(
        start=args.start,
        end=args.end,
        shift_microstructure_1h=not args.no_ms_shift,
    )

    stamp = f"{args.start}_to_{args.end}".replace("-", "")
    parquet_path = out_dir / f"unified_crypto_1h_{stamp}.parquet"
    csv_path = out_dir / f"unified_crypto_1h_{stamp}.csv"

    df.to_parquet(parquet_path)
    df.to_csv(csv_path)

    print(f"Saved: {parquet_path}")
    print(f"Saved: {csv_path}")
    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns):,}")
    print("First columns:", list(df.columns[:12]))


if __name__ == "__main__":
    main()
