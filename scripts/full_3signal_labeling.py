"""
Full 3-Signal Labeling Pipeline
================================
Replicates the original eth_addresses_labeled.parquet build process
but uses the NEW TeacherAM XGB model for the ML signal.

Signals:
  1. XGB Teacher Score  (sigmoid-calibrated, k=30 @ p75)
  2. Rule-Based Patterns (SMURFING, LAYERING, FAN_OUT, FAN_IN, PEELING, STRUCTURING, VELOCITY)
  3. Graph Properties    (in-degree, out-degree, centrality proxies, mixer/sanctioned proximity)

Hybrid score: 40% XGB + 30% pattern_boost + 30% soph_normalized
Then PR-curve-optimized thresholds → risk_level → fraud label.

Input:  eth_merged_dataset.parquet  (1.67M txs, 625K addresses)
Output: processed/eth_addresses_labeled_v2.parquet
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
PARQUET_PATH = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
OUTPUT_PATH = r"C:\amttp\processed\eth_addresses_labeled_v2.parquet"
OUTPUT_CSV = r"C:\amttp\processed\eth_addresses_labeled_v2.csv"

# ML Pipeline model (primary — used in original labeled dataset)
ML_MODEL_PATH = r"C:\amttp\ml\Automation\ml_pipeline\models\trained\xgb.json"
ML_SCHEMA_PATH = r"C:\amttp\ml\Automation\ml_pipeline\models\feature_schema.json"

# TeacherAM model (secondary — for comparison column)
TEACHER_MODEL_PATH = r"C:\amttp\ml\Automation\TeacherAM\models\xgb.json"
TEACHER_SCHEMA_PATH = r"C:\amttp\ml\Automation\TeacherAM\metadata\feature_schema.json"

# Known addresses for graph signal
KNOWN_MIXERS = [
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",
    "0x722122df12d4e14e13ac3b6895a86e84145b6967",
    "0xba214c1c1928a32bffe790263e38b4af9bfcd659",
    "0xd4b88df4d29f5cedd6857912842cff3b20c8cfa3",
    "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",
    "0xa160cdab225685da1d56aa342ad8841c3b53f291",
    "0xfd8610d20aa15b7b2e3be39b396a1bc3516c7144",
    "0xf60dd140cff0706bae9cd734ac3683f76585193a",
    "0x23773e65ed146a459791799d01336db287f25334",
    "0xb1c8094b234dce6e03f10a5b673c1d8c69739a00",
]

KNOWN_SANCTIONED = [
    "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c",
    "0x901bb9583b24d97e995513c6778dc6888ab6870e",
    "0xa7e5d5a720f06526557c513402f2e6b5fa20b008",
    "0x7f367cc41522ce07553e823bf3be79a889debe1b",
    "0x1da5821544e25c636c1417ba96ade4cf6d2f9b5a",
    "0x7db418b5d567a4e0e8c59ad71be1fce48f3e6107",
    "0x72a5843cc08275c8171e582972aa4fda8c397b2a",
    "0x7f19720a857f834696350e4284200515b2256c6e",
    "0x2f389ce8bd8ff92de3402ffce4691d17fc4f6535",
    "0x19aa5fe80d33a56d56c78e82ea5e50e5d80b4dff",
]

KNOWN_EXCHANGES = [
    "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be",  # Binance
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d",  # Binance
    "0x28c6c06298d514db089934071355e5743bf21d60",  # Binance
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f",  # Binance
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549",  # Binance
    "0x2b5634c42055806a59e9107ed44d43c426e58258",  # KuCoin
    "0xeb2629a2734e272bcc07bda959863f316f4bd4cf",  # OKX
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b",  # OKX
    "0xfe9e8709d3215310075d67e3ed32a380ccf451c8",  # ByBit
]

# Smurfing/pattern thresholds (matching ultra script)
SMURFING_THRESHOLD = 1.0
FAN_THRESHOLD = 10
MIN_TX_COUNT = 3

# Pattern boost weights (from calibrated_thresholds.json)
PATTERN_BOOST_WEIGHTS = {
    "SMURFING": 25,
    "LAYERING": 15,
    "FAN_OUT": 15,
    "FAN_IN": 15,
    "STRUCTURING": 20,
    "VELOCITY": 15,
    "PEELING": 20,
}

print("=" * 80)
print("FULL 3-SIGNAL LABELING PIPELINE (625K addresses)")
print("=" * 80)
overall_start = time.perf_counter()

# ============================================================================
# STEP 1: LOAD DATA
# ============================================================================
print(f"\n[STEP 1] Loading transaction data ...")
t0 = time.perf_counter()
df = pd.read_parquet(PARQUET_PATH)
df["from_address"] = df["from_address"].str.lower()
df["to_address"] = df["to_address"].str.lower()
df["value_eth"] = pd.to_numeric(df["value_eth"], errors="coerce").fillna(0)
df["gas_price_gwei"] = pd.to_numeric(df.get("gas_price_gwei", 0), errors="coerce").fillna(0)
df["gas_used"] = pd.to_numeric(df.get("gas_used", 21000), errors="coerce").fillna(21000)
df["block_timestamp"] = pd.to_datetime(df["block_timestamp"], utc=True, errors="coerce")
print(f"   Loaded {len(df):,} transactions in {time.perf_counter()-t0:.1f}s")

# ============================================================================
# STEP 2: ADDRESS-LEVEL FEATURE AGGREGATION
# ============================================================================
print(f"\n[STEP 2] Aggregating address-level features ...")
t0 = time.perf_counter()

# --- Sent ---
sent = df.groupby("from_address").agg(
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
    first_sent_time=("block_timestamp", "min"),
    last_sent_time=("block_timestamp", "max"),
)
sent.index.name = "address"

# --- Received ---
recv = df.groupby("to_address").agg(
    received_count=("tx_hash", "count"),
    total_received=("value_eth", "sum"),
    avg_received=("value_eth", "mean"),
    max_received=("value_eth", "max"),
    min_received=("value_eth", "min"),
    std_received=("value_eth", "std"),
    unique_senders=("from_address", "nunique"),
    first_received_time=("block_timestamp", "min"),
    last_received_time=("block_timestamp", "max"),
)
recv.index.name = "address"

# --- Merge ---
addr_df = sent.join(recv, how="outer")
addr_df = addr_df.reset_index()
numeric_cols = addr_df.select_dtypes(include="number").columns
addr_df[numeric_cols] = addr_df[numeric_cols].fillna(0)

# Derived features
addr_df["total_transactions"] = addr_df["sent_count"] + addr_df["received_count"]
addr_df["balance"] = addr_df["total_received"] - addr_df["total_sent"]
addr_df["in_out_ratio"] = addr_df["received_count"] / (addr_df["sent_count"] + 1)
addr_df["unique_counterparties"] = addr_df["unique_receivers"] + addr_df["unique_senders"]
addr_df["avg_value"] = (addr_df["avg_sent"] + addr_df["avg_received"]) / 2
addr_df["neighbors"] = addr_df["unique_counterparties"]
addr_df["count"] = addr_df["total_transactions"]
addr_df["income"] = addr_df["balance"]

# Time features
for c in ["first_sent_time", "last_sent_time", "first_received_time", "last_received_time"]:
    if c in addr_df.columns:
        addr_df[c] = pd.to_datetime(addr_df[c], errors="coerce")

first_activity = addr_df[["first_sent_time", "first_received_time"]].min(axis=1)
last_activity = addr_df[["last_sent_time", "last_received_time"]].max(axis=1)
addr_df["active_duration_mins"] = (last_activity - first_activity).dt.total_seconds().fillna(0) / 60

print(f"   {len(addr_df):,} unique addresses in {time.perf_counter()-t0:.1f}s")

# ============================================================================
# STEP 3: RULE-BASED PATTERN DETECTION (Signal 2)
# ============================================================================
print(f"\n[STEP 3] Detecting behavioral patterns (7 rules) ...")
t0 = time.perf_counter()

# Initialize per-address score columns
for col in ["smurf_score", "fan_out_score", "fan_in_score", "layering_score",
            "structuring_score", "velocity_score", "peeling_score"]:
    addr_df[col] = 0.0

# ---- 3a: SMURFING ----
smurf_mask = (
    (addr_df["sent_count"] >= 5) &
    (addr_df["avg_sent"] < SMURFING_THRESHOLD) &
    (addr_df["total_sent"] > 5) &
    (addr_df["unique_receivers"] >= 3)
)
addr_df.loc[smurf_mask, "smurf_score"] = (
    (addr_df.loc[smurf_mask, "sent_count"] / 10).clip(0, 1) * 30 +
    (1 - addr_df.loc[smurf_mask, "avg_sent"] / SMURFING_THRESHOLD).clip(0, 1) * 25 +
    (addr_df.loc[smurf_mask, "unique_receivers"] / 10).clip(0, 1) * 20 +
    (addr_df.loc[smurf_mask, "total_sent"] / 50).clip(0, 1) * 25
)
addr_df.loc[addr_df["smurf_score"] <= 30, "smurf_score"] = 0
n_smurf = (addr_df["smurf_score"] > 0).sum()
print(f"   SMURFING:     {n_smurf:,}")

# ---- 3b: FAN-OUT ----
fo_mask = (
    (addr_df["unique_receivers"] >= FAN_THRESHOLD) &
    (addr_df["sent_count"] >= FAN_THRESHOLD)
)
addr_df.loc[fo_mask, "fan_out_score"] = (
    (addr_df.loc[fo_mask, "unique_receivers"] / 20).clip(0, 1) * 40 +
    (addr_df.loc[fo_mask, "sent_count"] / 20).clip(0, 1) * 30 +
    (addr_df.loc[fo_mask, "total_sent"] / 100).clip(0, 1) * 30
)
n_fo = (addr_df["fan_out_score"] > 0).sum()
print(f"   FAN_OUT:      {n_fo:,}")

# ---- 3c: FAN-IN ----
fi_mask = (
    (addr_df["unique_senders"] >= FAN_THRESHOLD) &
    (addr_df["received_count"] >= FAN_THRESHOLD)
)
addr_df.loc[fi_mask, "fan_in_score"] = (
    (addr_df.loc[fi_mask, "unique_senders"] / 20).clip(0, 1) * 40 +
    (addr_df.loc[fi_mask, "received_count"] / 20).clip(0, 1) * 30 +
    (addr_df.loc[fi_mask, "total_received"] / 100).clip(0, 1) * 30
)
n_fi = (addr_df["fan_in_score"] > 0).sum()
print(f"   FAN_IN:       {n_fi:,}")

# ---- 3d: LAYERING (pass-through: sends ≈ receives) ----
lay_mask = (
    (addr_df["sent_count"] >= 2) &
    (addr_df["received_count"] >= 2) &
    (addr_df["total_received"] > 0)
)
pass_ratio = (addr_df["total_sent"] / addr_df["total_received"].clip(lower=0.001)).clip(0, 1)
lay_mask = lay_mask & (pass_ratio > 0.8)
addr_df.loc[lay_mask, "layering_score"] = (
    pass_ratio.loc[lay_mask] * 40 +
    (addr_df.loc[lay_mask, "received_count"] / 5).clip(0, 1) * 30 +
    (addr_df.loc[lay_mask, "sent_count"] / 5).clip(0, 1) * 30
)
n_lay = (addr_df["layering_score"] > 0).sum()
print(f"   LAYERING:     {n_lay:,}")

# ---- 3e: STRUCTURING (round amounts) ----
round_amounts = [0.1, 0.5, 1.0, 5.0, 10.0, 50.0, 100.0, 500.0, 1000.0]
df["is_round"] = ((df["value_eth"] >= 1) & (df["value_eth"] == df["value_eth"].apply(lambda x: float(int(x))))) | df["value_eth"].isin(round_amounts)
round_agg = df[df["is_round"]].groupby("from_address").agg(
    round_tx_count=("tx_hash", "count"),
    round_total=("value_eth", "sum"),
).rename_axis("address")
addr_df = addr_df.merge(round_agg, on="address", how="left")
addr_df["round_tx_count"] = addr_df["round_tx_count"].fillna(0)
addr_df["round_total"] = addr_df["round_total"].fillna(0)
round_ratio = addr_df["round_tx_count"] / addr_df["sent_count"].clip(lower=1)
struct_mask = (addr_df["round_tx_count"] >= 3) & (round_ratio > 0.5)
addr_df.loc[struct_mask, "structuring_score"] = (
    round_ratio.loc[struct_mask] * 40 +
    (addr_df.loc[struct_mask, "round_tx_count"] / 10).clip(0, 1) * 30 +
    (addr_df.loc[struct_mask, "round_total"] / 50).clip(0, 1) * 30
)
n_struct = (addr_df["structuring_score"] > 0).sum()
print(f"   STRUCTURING:  {n_struct:,}")

# ---- 3f: VELOCITY (hourly burst) ----
print("   Computing VELOCITY (hourly aggregation) ...")
df["hour"] = df["block_timestamp"].dt.floor("h")
hourly = df.groupby(["from_address", "hour"]).size().reset_index(name="tx_count_h")
hourly_stats = hourly.groupby("from_address").agg(
    avg_tx_hour=("tx_count_h", "mean"),
    max_tx_hour=("tx_count_h", "max"),
).rename_axis("address")
hourly_stats["velocity_ratio"] = hourly_stats["max_tx_hour"] / hourly_stats["avg_tx_hour"].clip(lower=0.001)
addr_df = addr_df.merge(hourly_stats[["velocity_ratio", "max_tx_hour"]], on="address", how="left")
addr_df["velocity_ratio"] = addr_df["velocity_ratio"].fillna(0)
addr_df["max_tx_hour"] = addr_df["max_tx_hour"].fillna(0)
vel_mask = (addr_df["max_tx_hour"] >= 5) & (addr_df["velocity_ratio"] > 3)
addr_df.loc[vel_mask, "velocity_score"] = (
    (addr_df.loc[vel_mask, "velocity_ratio"] / 10).clip(0, 1) * 50 +
    (addr_df.loc[vel_mask, "max_tx_hour"] / 20).clip(0, 1) * 50
)
n_vel = (addr_df["velocity_score"] > 0).sum()
print(f"   VELOCITY:     {n_vel:,}")

# ---- 3g: PEELING (sequential decreasing values) ----
print("   Computing PEELING chains ...")
sorted_txs = df.sort_values(["from_address", "block_timestamp"])
sorted_txs["prev_value"] = sorted_txs.groupby("from_address")["value_eth"].shift(1)
pairs = sorted_txs.dropna(subset=["prev_value"])
pairs["is_decrease"] = pairs["value_eth"] < pairs["prev_value"]
peel_agg = pairs.groupby("from_address").agg(
    pair_count=("is_decrease", "count"),
    decrease_count=("is_decrease", "sum"),
).rename_axis("address")
peel_agg["decrease_ratio"] = peel_agg["decrease_count"] / peel_agg["pair_count"]
peel_agg = peel_agg[(peel_agg["pair_count"] >= 2) & (peel_agg["decrease_ratio"] > 0.6)]
addr_df = addr_df.merge(peel_agg[["decrease_ratio", "pair_count"]], on="address", how="left", suffixes=("", "_peel"))
addr_df["decrease_ratio"] = addr_df["decrease_ratio"].fillna(0)
addr_df["pair_count"] = addr_df.get("pair_count", pd.Series(0, index=addr_df.index)).fillna(0)
peel_mask = addr_df["decrease_ratio"] > 0.6
addr_df.loc[peel_mask, "peeling_score"] = (
    addr_df.loc[peel_mask, "decrease_ratio"] * 50 +
    (addr_df.loc[peel_mask, "pair_count"] / 10).clip(0, 1) * 50
)
n_peel = (addr_df["peeling_score"] > 0).sum()
print(f"   PEELING:      {n_peel:,}")

# Combine pattern scores
score_cols = ["smurf_score", "fan_out_score", "fan_in_score",
              "layering_score", "structuring_score", "velocity_score", "peeling_score"]
PATTERN_NAMES = ["SMURFING", "FAN_OUT", "FAN_IN", "LAYERING", "STRUCTURING", "VELOCITY", "PEELING"]

addr_df["sophisticated_score"] = addr_df[score_cols].sum(axis=1)

def build_patterns(row):
    parts = []
    for col, name in zip(score_cols, PATTERN_NAMES):
        if row[col] > 0:
            parts.append(name)
    return ", ".join(parts)

addr_df["patterns"] = addr_df.apply(build_patterns, axis=1)
addr_df["pattern_count"] = (addr_df[score_cols] > 0).sum(axis=1)

def calc_boost(patterns_str):
    if not patterns_str:
        return 0
    return min(sum(PATTERN_BOOST_WEIGHTS.get(p.strip(), 0) for p in patterns_str.split(",")), 100)

addr_df["pattern_boost"] = addr_df["patterns"].apply(calc_boost)

print(f"   Pattern step done in {time.perf_counter()-t0:.1f}s")
print(f"   Addresses with ≥1 pattern: {(addr_df['pattern_count'] > 0).sum():,}")

# ============================================================================
# STEP 4: GRAPH PROPERTIES (Signal 3)
# ============================================================================
print(f"\n[STEP 4] Computing graph properties ...")
t0 = time.perf_counter()

# Degree centrality proxies (from tx data)
addr_df["in_degree"] = addr_df["unique_senders"]
addr_df["out_degree"] = addr_df["unique_receivers"]
addr_df["degree"] = addr_df["in_degree"] + addr_df["out_degree"]

# Normalize degree → centrality proxy  (degree / max_degree)
max_degree = addr_df["degree"].max()
addr_df["degree_centrality"] = addr_df["degree"] / max(max_degree, 1)

# Betweenness proxy: pass-through addresses (high in-degree AND high out-degree)
addr_df["betweenness_proxy"] = (
    (addr_df["in_degree"] / max(addr_df["in_degree"].max(), 1)) *
    (addr_df["out_degree"] / max(addr_df["out_degree"].max(), 1))
)

# Known-entity proximity
mixer_set = set(a.lower() for a in KNOWN_MIXERS)
sanctioned_set = set(a.lower() for a in KNOWN_SANCTIONED)
exchange_set = set(a.lower() for a in KNOWN_EXCHANGES)

# Direct interaction with known addresses
sent_to_mixer = df[df["to_address"].isin(mixer_set)].groupby("from_address").size().rename("sent_to_mixer")
recv_from_mixer = df[df["from_address"].isin(mixer_set)].groupby("to_address").size().rename("recv_from_mixer")
sent_to_sanctioned = df[df["to_address"].isin(sanctioned_set)].groupby("from_address").size().rename("sent_to_sanctioned")
recv_from_sanctioned = df[df["from_address"].isin(sanctioned_set)].groupby("to_address").size().rename("recv_from_sanctioned")
sent_to_exchange = df[df["to_address"].isin(exchange_set)].groupby("from_address").size().rename("sent_to_exchange")
recv_from_exchange = df[df["from_address"].isin(exchange_set)].groupby("to_address").size().rename("recv_from_exchange")

for s, col_name in [
    (sent_to_mixer, "sent_to_mixer"), (recv_from_mixer, "recv_from_mixer"),
    (sent_to_sanctioned, "sent_to_sanctioned"), (recv_from_sanctioned, "recv_from_sanctioned"),
    (sent_to_exchange, "sent_to_exchange"), (recv_from_exchange, "recv_from_exchange"),
]:
    s.index.name = "address"
    addr_df = addr_df.merge(s, on="address", how="left")
    addr_df[col_name] = addr_df[col_name].fillna(0)

addr_df["mixer_interaction"] = addr_df["sent_to_mixer"] + addr_df["recv_from_mixer"]
addr_df["sanctioned_interaction"] = addr_df["sent_to_sanctioned"] + addr_df["recv_from_sanctioned"]
addr_df["exchange_interaction"] = addr_df["sent_to_exchange"] + addr_df["recv_from_exchange"]

# Graph risk score (0-100): weighted combination
addr_df["graph_risk_score"] = (
    addr_df["degree_centrality"] * 10 +
    addr_df["betweenness_proxy"] * 15 +
    (addr_df["mixer_interaction"] > 0).astype(float) * 30 +
    (addr_df["sanctioned_interaction"] > 0).astype(float) * 40 +
    (addr_df["exchange_interaction"] > 0).astype(float) * 5
).clip(0, 100)

# Is known entity flag
addr_df["is_mixer"] = addr_df["address"].isin(mixer_set).astype(int)
addr_df["is_sanctioned"] = addr_df["address"].isin(sanctioned_set).astype(int)
addr_df["is_exchange"] = addr_df["address"].isin(exchange_set).astype(int)

print(f"   Graph features done in {time.perf_counter()-t0:.1f}s")
print(f"   Mixer interactions:      {(addr_df['mixer_interaction'] > 0).sum():,}")
print(f"   Sanctioned interactions: {(addr_df['sanctioned_interaction'] > 0).sum():,}")
print(f"   Exchange interactions:   {(addr_df['exchange_interaction'] > 0).sum():,}")

# ============================================================================
# STEP 5: XGB SCORING (Signal 1) — with sigmoid calibration
# ============================================================================
print(f"\n[STEP 5] Running XGB inference (ml_pipeline model + TeacherAM) ...")
t0 = time.perf_counter()
import xgboost as xgb

# Shared feature mapping (address cols → schema names)
FEATURE_MAP = {
    "avg_val_sent": "avg_sent",
    "avg_val_received": "avg_received",
    "min_val_sent": "min_sent",
    "max_val_sent": "max_sent",
    "min_value_received": "min_received",
    "max_value_received": "max_received",
    "sent_tnx": "sent_count",
    "received_tnx": "received_count",
    "count": "count",
    "neighbors": "neighbors",
    "total_ether_balance": "balance",
    "income": "income",
    "total_ether_sent": "total_sent",
    "total_ether_received": "total_received",
    "total_transactions_(including_tnx_to_create_contract": "total_transactions",
    "unique_sent_to_addresses": "unique_receivers",
    "unique_received_from_addresses": "unique_senders",
    "time_diff_between_first_and_last_(mins)": "active_duration_mins",
}

# ---- Backfill h_* features (needed by TeacherAM) ----
def _col(name):
    return addr_df[name] if name in addr_df.columns else pd.Series(0, index=addr_df.index, dtype=float)

addr_df["h_value_in"] = _col("total_received")
addr_df["h_value_out"] = _col("total_sent")
addr_df["h_net_flow"] = _col("total_received") - _col("total_sent")
addr_df["h_value_to_contracts"] = 0.0
addr_df["h_tx_count"] = _col("total_transactions")
addr_df["h_tx_in_count"] = _col("received_count")
addr_df["h_tx_out_count"] = _col("sent_count")
addr_df["h_counterparties"] = _col("unique_counterparties")
addr_df["h_cp_per_tx"] = addr_df["h_counterparties"] / addr_df["h_tx_count"].clip(lower=1)
addr_df["h_self_dealing"] = 0.0
addr_df["h_value_per_cp"] = (addr_df["h_value_in"] + addr_df["h_value_out"]) / addr_df["h_counterparties"].clip(lower=1)
addr_df["h_value_per_tx"] = (addr_df["h_value_in"] + addr_df["h_value_out"]) / addr_df["h_tx_count"].clip(lower=1)
addr_df["h_complexity"] = np.log1p(addr_df["h_tx_count"])
addr_df["h_temporal_span"] = _col("active_duration_mins")
addr_df["h_tx_frequency"] = addr_df["h_tx_count"] / addr_df["h_temporal_span"].clip(lower=1)

def _build_aligned(schema_path, model_path):
    with open(schema_path, "r") as f:
        schema = json.load(f)
    fnames = schema["feature_names"]
    aligned = pd.DataFrame(0.0, index=addr_df.index, columns=fnames)
    for feat in fnames:
        if feat in addr_df.columns:
            aligned[feat] = pd.to_numeric(addr_df[feat], errors="coerce")
        elif feat in FEATURE_MAP and FEATURE_MAP[feat] in addr_df.columns:
            aligned[feat] = pd.to_numeric(addr_df[FEATURE_MAP[feat]], errors="coerce")
    aligned = aligned.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    booster = xgb.Booster()
    booster.load_model(model_path)
    dmat = xgb.DMatrix(aligned.values, feature_names=fnames)
    scores = booster.predict(dmat)
    matched = (aligned.sum(axis=0) != 0).sum()
    return scores, matched, len(fnames)

# --- PRIMARY: ml_pipeline model (171 features — matches original dataset) ---
print("   [PRIMARY] ml_pipeline model ...")
raw_scores, matched, total_feat = _build_aligned(ML_SCHEMA_PATH, ML_MODEL_PATH)
print(f"   Features with data: {matched}/{total_feat}")
print(f"   Raw scores: min={raw_scores.min():.6f}  max={raw_scores.max():.6f}  median={np.median(raw_scores):.6f}")

# Sigmoid calibration (k=30 centered at p75 — identical to prior pipeline)
p75 = np.percentile(raw_scores, 75)
k = 30
calibrated = 1.0 / (1.0 + np.exp(-k * (raw_scores - p75)))
xgb_normalized = calibrated * 100  # scale to 0-100

print(f"   Calibrated (0-100): min={xgb_normalized.min():.1f}  max={xgb_normalized.max():.1f}  median={np.median(xgb_normalized):.1f}")
print(f"   p90={np.percentile(xgb_normalized, 90):.1f}  p95={np.percentile(xgb_normalized, 95):.1f}  p99={np.percentile(xgb_normalized, 99):.1f}")

addr_df["xgb_raw_score"] = raw_scores
addr_df["xgb_normalized"] = xgb_normalized

# --- SECONDARY: TeacherAM model (67 features — for comparison) ---
print("   [SECONDARY] TeacherAM model ...")
tam_scores, tam_matched, tam_total = _build_aligned(TEACHER_SCHEMA_PATH, TEACHER_MODEL_PATH)
tam_p75 = np.percentile(tam_scores, 75)
tam_cal = 1.0 / (1.0 + np.exp(-30 * (tam_scores - tam_p75))) * 100
addr_df["teacher_raw_score"] = tam_scores
addr_df["teacher_normalized"] = tam_cal
print(f"   Features with data: {tam_matched}/{tam_total}")
print(f"   TeacherAM calibrated: min={tam_cal.min():.1f}  max={tam_cal.max():.1f}  median={np.median(tam_cal):.1f}")

print(f"   XGB step done in {time.perf_counter()-t0:.1f}s")

# ============================================================================
# STEP 6: HYBRID SCORE = 40% XGB + 30% pattern_boost + 30% soph_normalized
# ============================================================================
print(f"\n[STEP 6] Computing hybrid scores ...")
t0 = time.perf_counter()

max_soph = addr_df["sophisticated_score"].max()
addr_df["soph_normalized"] = (addr_df["sophisticated_score"] / max(max_soph, 1)) * 100

addr_df["hybrid_score"] = (
    addr_df["xgb_normalized"] * 0.40 +
    addr_df["pattern_boost"] * 0.30 +
    addr_df["soph_normalized"] * 0.30
)

# Multi-signal bonus
def count_signals(row):
    signals = 0
    if row["xgb_normalized"] >= 50:
        signals += 1
    if row["graph_risk_score"] >= 10:
        signals += 1
    if row["pattern_count"] >= 3:
        signals += 1
    return signals

addr_df["signal_count"] = addr_df.apply(count_signals, axis=1)
addr_df.loc[addr_df["signal_count"] == 2, "hybrid_score"] *= 1.2
addr_df.loc[addr_df["signal_count"] >= 3, "hybrid_score"] *= 1.5
addr_df["hybrid_score"] = addr_df["hybrid_score"].clip(0, 100)

print(f"   Hybrid score range: {addr_df['hybrid_score'].min():.1f} - {addr_df['hybrid_score'].max():.1f}")
print(f"   Multi-signal (≥2): {(addr_df['signal_count'] >= 2).sum():,}")

# ============================================================================
# STEP 7: PR-CURVE THRESHOLD OPTIMIZATION → risk_level → fraud label
# ============================================================================
print(f"\n[STEP 7] Optimizing thresholds via PR-curve ...")

# Pseudo ground-truth: pattern_count >= 3  (multi-signal = likely fraud)
pseudo_labels = (addr_df["pattern_count"] >= 3).astype(int)
positives = pseudo_labels.sum()
print(f"   Pseudo positives (pattern_count>=3): {positives:,}")

best_f1 = 0
best_thresh = 60

for thresh in np.linspace(10, 95, 50):
    preds = (addr_df["hybrid_score"] >= thresh).astype(int)
    tp = ((preds == 1) & (pseudo_labels == 1)).sum()
    fp = ((preds == 1) & (pseudo_labels == 0)).sum()
    fn = ((preds == 0) & (pseudo_labels == 1)).sum()
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
    if f1 > best_f1:
        best_f1 = f1
        best_thresh = thresh

critical_thresh = min(best_thresh + 15, 95)
high_thresh = best_thresh
medium_thresh = max(best_thresh - 15, 20)

print(f"   Best F1: {best_f1:.3f} @ threshold={best_thresh:.1f}")
print(f"   CRITICAL >= {critical_thresh:.1f}  |  HIGH >= {high_thresh:.1f}  |  MEDIUM >= {medium_thresh:.1f}  |  LOW >= 20")

def classify_risk(score):
    if score >= critical_thresh:
        return "CRITICAL"
    elif score >= high_thresh:
        return "HIGH"
    elif score >= medium_thresh:
        return "MEDIUM"
    elif score >= 20:
        return "LOW"
    return "MINIMAL"

addr_df["risk_level"] = addr_df["hybrid_score"].apply(classify_risk)
addr_df["fraud"] = addr_df["risk_level"].isin(["CRITICAL", "HIGH"]).astype(int)

# risk_class (numeric 0-4)
risk_class_map = {"MINIMAL": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
addr_df["risk_class"] = addr_df["risk_level"].map(risk_class_map)

print(f"   Hybrid step done in {time.perf_counter()-t0:.1f}s")

# ============================================================================
# STEP 8: SAVE OUTPUT
# ============================================================================
print(f"\n[STEP 8] Saving results ...")
t0 = time.perf_counter()

# Sort by hybrid score descending
addr_df = addr_df.sort_values("hybrid_score", ascending=False)

# Save parquet
Path(OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
addr_df.to_parquet(OUTPUT_PATH, index=False)
print(f"   Parquet: {OUTPUT_PATH}")

# Save CSV (for quick inspection)
addr_df.to_csv(OUTPUT_CSV, index=False)
print(f"   CSV:     {OUTPUT_CSV}")

print(f"   Saved in {time.perf_counter()-t0:.1f}s")

# ============================================================================
# SUMMARY
# ============================================================================
elapsed = time.perf_counter() - overall_start
print(f"\n{'=' * 80}")
print("SUMMARY")
print(f"{'=' * 80}")
print(f"   Total addresses:    {len(addr_df):,}")
print(f"   Total transactions: {len(df):,}")
print()
risk_counts = addr_df["risk_level"].value_counts()
for level in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "MINIMAL"]:
    cnt = risk_counts.get(level, 0)
    pct = cnt / len(addr_df) * 100
    emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢", "MINIMAL": "⚪"}.get(level, "")
    print(f"   {emoji} {level:10}: {cnt:>8,}  ({pct:>5.2f}%)")

fraud_count = addr_df["fraud"].sum()
print(f"\n   fraud=1 (CRITICAL+HIGH): {fraud_count:,}  ({fraud_count/len(addr_df)*100:.2f}%)")
print(f"   fraud=0:                 {len(addr_df)-fraud_count:,}")

print(f"\n   Columns in output: {len(addr_df.columns)}")
print(f"   {addr_df.columns.tolist()}")
print(f"\n   Total time: {elapsed:.1f}s")

# Match prior schema columns check
prior_cols = [
    "address", "sent_count", "received_count", "total_transactions",
    "total_sent", "total_received", "balance", "avg_sent", "avg_received",
    "avg_value", "max_sent", "max_received", "min_sent", "min_received",
    "std_sent", "std_received", "total_gas_sent", "avg_gas_used", "avg_gas_price",
    "unique_receivers", "unique_senders", "unique_counterparties", "in_out_ratio",
    "active_duration_mins", "sophisticated_score", "patterns", "pattern_count",
    "xgb_raw_score", "xgb_normalized", "pattern_boost", "soph_normalized",
    "hybrid_score", "risk_level", "fraud", "risk_class"
]
present = [c for c in prior_cols if c in addr_df.columns]
missing = [c for c in prior_cols if c not in addr_df.columns]
print(f"\n   Prior-schema columns present: {len(present)}/{len(prior_cols)}")
if missing:
    print(f"   Missing: {missing}")

# New columns (graph properties + teacher details)
new_cols = [
    "in_degree", "out_degree", "degree", "degree_centrality", "betweenness_proxy",
    "mixer_interaction", "sanctioned_interaction", "exchange_interaction",
    "graph_risk_score", "is_mixer", "is_sanctioned", "is_exchange",
    "signal_count",
]
print(f"   New graph/signal columns: {[c for c in new_cols if c in addr_df.columns]}")

print(f"\n{'=' * 80}")
print("DONE — eth_addresses_labeled_v2.parquet ready")
print(f"{'=' * 80}")
