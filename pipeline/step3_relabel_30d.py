"""Fetch last-30-day ETH transactions from Etherscan, aggregate to address features, and relabel with TeacherAM."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.eth_data_fetcher import EtherscanFetcher, SyntheticDataGenerator


RAW_OUT = Path("C:/amttp/processed/eth_30d_raw.parquet")
LABELED_OUT = Path("C:/amttp/processed/eth_30d_teacher_labeled.parquet")
SCHEMA_PATH = Path("C:/amttp/ml/Automation/TeacherAM/metadata/feature_schema.json")
MODEL_PATH = Path("C:/amttp/ml/Automation/TeacherAM/models/xgb.json")


def _load_feature_schema(schema_path: Path) -> list[str]:
    with schema_path.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    features = schema.get("feature_names", [])
    if not features:
        raise ValueError(f"No feature_names found in {schema_path}")
    return features


def _fetch_transactions(days: int = 30) -> pd.DataFrame:
    api_key = os.getenv("ETHERSCAN_API_KEY", "")
    if not api_key:
        raise RuntimeError("ETHERSCAN_API_KEY is not set")

    addresses = list(
        dict.fromkeys(
            SyntheticDataGenerator.EXCHANGES
            + SyntheticDataGenerator.MIXERS
            + SyntheticDataGenerator.SANCTIONED
        )
    )

    fetcher = EtherscanFetcher(api_key=api_key)
    all_txs = []
    for addr in addresses:
        txs = asyncio_run(fetcher.get_transactions(address=addr, offset=1000))
        all_txs.extend(txs)
        internal = asyncio_run(fetcher.get_internal_transactions(address=addr))
        all_txs.extend(internal)

    if not all_txs:
        raise RuntimeError("No transactions fetched from Etherscan")

    df = pd.DataFrame([t.to_dict() for t in all_txs])
    cutoff = int(datetime.now(timezone.utc).timestamp()) - (days * 24 * 3600)
    df = df[df["timestamp"] >= cutoff]
    df = df.drop_duplicates(subset=["tx_hash"]).reset_index(drop=True)
    return df


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


def _aggregate_address_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", errors="coerce")

    sender_stats = df.groupby("from_address").agg(
        sent_count=("tx_hash", "count"),
        total_sent=("value_eth", "sum"),
        avg_sent=("value_eth", "mean"),
        max_sent=("value_eth", "max"),
        min_sent=("value_eth", "min"),
        std_sent=("value_eth", "std"),
        total_gas_sent=("gas_used", "sum"),
        avg_gas_used=("gas_used", "mean"),
        avg_gas_price=("gas_price_gwei", "mean"),
        unique_receivers=("to_address", "nunique"),
        first_sent_time=("timestamp", "min"),
        last_sent_time=("timestamp", "max"),
    )
    sender_stats.index.name = "address"

    receiver_stats = df.groupby("to_address").agg(
        received_count=("tx_hash", "count"),
        total_received=("value_eth", "sum"),
        avg_received=("value_eth", "mean"),
        max_received=("value_eth", "max"),
        min_received=("value_eth", "min"),
        std_received=("value_eth", "std"),
        unique_senders=("from_address", "nunique"),
        first_received_time=("timestamp", "min"),
        last_received_time=("timestamp", "max"),
    )
    receiver_stats.index.name = "address"

    addr_df = pd.DataFrame({"address": pd.Index(df["from_address"]).append(pd.Index(df["to_address"]))}).drop_duplicates()
    addr_df = addr_df.merge(sender_stats, on="address", how="left")
    addr_df = addr_df.merge(receiver_stats, on="address", how="left")

    time_cols = [
        "first_sent_time",
        "last_sent_time",
        "first_received_time",
        "last_received_time",
    ]
    for col in time_cols:
        if col in addr_df.columns:
            addr_df[col] = pd.to_datetime(addr_df[col], errors="coerce")

    numeric_cols = addr_df.columns.difference(["address"] + time_cols)
    addr_df[numeric_cols] = addr_df[numeric_cols].fillna(0)

    addr_df["total_transactions"] = addr_df["sent_count"] + addr_df["received_count"]
    addr_df["balance"] = addr_df["total_received"] - addr_df["total_sent"]
    addr_df["in_out_ratio"] = addr_df["received_count"] / (addr_df["sent_count"] + 1)
    addr_df["unique_counterparties"] = addr_df["unique_receivers"] + addr_df["unique_senders"]
    addr_df["avg_value"] = (addr_df["avg_sent"] + addr_df["avg_received"]) / 2

    addr_df["first_activity"] = addr_df[["first_sent_time", "first_received_time"]].min(axis=1)
    addr_df["last_activity"] = addr_df[["last_sent_time", "last_received_time"]].max(axis=1)
    active_minutes = (addr_df["last_activity"] - addr_df["first_activity"]).dt.total_seconds() / 60
    addr_df["active_duration_mins"] = active_minutes.fillna(0)

    return addr_df


def _backfill_h_features(df: pd.DataFrame) -> pd.DataFrame:
    def _col_or_zero(name: str) -> pd.Series:
        if name in df.columns:
            return df[name]
        return pd.Series(0, index=df.index, dtype=float)

    total_in = _col_or_zero("total_received")
    total_out = _col_or_zero("total_sent")
    total_to_contracts = _col_or_zero("total_sent_contracts")
    tx_in = _col_or_zero("received_count")
    tx_out = _col_or_zero("sent_count")
    tx_total = _col_or_zero("total_transactions")
    counter_in = _col_or_zero("unique_senders")
    counter_out = _col_or_zero("unique_receivers")
    temporal_span = _col_or_zero("active_duration_mins")
    created = _col_or_zero("number_of_created_contracts")
    erc20_tx = _col_or_zero("total_erc20_tnxs")
    looped = _col_or_zero("looped")

    df["h_value_in"] = total_in
    df["h_value_out"] = total_out
    df["h_net_flow"] = total_in - total_out
    df["h_value_to_contracts"] = total_to_contracts

    df["h_tx_in_count"] = tx_in
    df["h_tx_out_count"] = tx_out
    df["h_tx_count"] = tx_total

    df["h_counterparties"] = counter_in + counter_out
    df["h_cp_per_tx"] = df["h_counterparties"] / np.maximum(tx_total, 1)
    df["h_self_dealing"] = (looped > 0).astype(float)

    df["h_value_per_cp"] = (total_in + total_out) / np.maximum(df["h_counterparties"], 1)
    df["h_value_per_tx"] = (total_in + total_out) / np.maximum(tx_total, 1)
    df["h_complexity"] = np.log1p(created + erc20_tx + tx_total)
    df["h_temporal_span"] = temporal_span
    df["h_tx_frequency"] = tx_total / np.maximum(temporal_span, 1)

    return df


def _label_with_teacher(addr_df: pd.DataFrame, fraud_pct: float = 0.05) -> pd.DataFrame:
    features = _load_feature_schema(SCHEMA_PATH)
    addr_df = _backfill_h_features(addr_df)

    aligned = pd.DataFrame(0.0, index=addr_df.index, columns=features)
    for col in features:
        if col in addr_df.columns:
            aligned[col] = pd.to_numeric(addr_df[col], errors="coerce")
    aligned = aligned.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    import xgboost as xgb

    booster = xgb.Booster()
    booster.load_model(str(MODEL_PATH))
    raw_scores = booster.predict(xgb.DMatrix(aligned.values, feature_names=features))

    # Reuse prior calibration approach: sigmoid with k=30 centered at p75.
    p75 = np.nanpercentile(raw_scores, 75)
    calibrated_scores = 1.0 / (1.0 + np.exp(-30 * (raw_scores - p75)))

    cutoff = np.quantile(calibrated_scores, 1.0 - fraud_pct)
    labels = (calibrated_scores >= cutoff).astype(np.int32)
    risk_levels = np.where(labels == 1, "HIGH", "LOW")

    out = addr_df.copy()
    out["teacher_model"] = "xgb"
    out["teacher_score_raw"] = raw_scores
    out["teacher_score"] = calibrated_scores
    out["teacher_calibration"] = "sigmoid_p75_k30"
    out["teacher_threshold"] = float(cutoff)
    out["teacher_fraud"] = labels
    out["teacher_risk_level"] = risk_levels
    return out


def main() -> None:
    tx_df = _fetch_transactions(days=30)
    RAW_OUT.parent.mkdir(parents=True, exist_ok=True)
    tx_df.to_parquet(RAW_OUT, index=False)

    addr_df = _aggregate_address_features(tx_df)
    labeled = _label_with_teacher(addr_df, fraud_pct=0.05)
    labeled.to_parquet(LABELED_OUT, index=False)

    print(f"Saved raw txs: {RAW_OUT}")
    print(f"Saved labeled addresses: {LABELED_OUT}")
    print(f"Rows: {len(labeled):,}")
    print(f"Teacher fraud rate: {labeled['teacher_fraud'].mean():.4%}")


if __name__ == "__main__":
    main()
