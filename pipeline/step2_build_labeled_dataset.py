"""
Build final eth_addresses_labeled_v2 from ultra-script outputs + graph properties.

Inputs:
  - eth_merged_dataset.parquet              (1.67M txs)
  - processed/sophisticated_xgb_combined.csv (ultra script: patterns + XGB hybrid)

Pipeline:
  1. Aggregate all 625K addresses from transactions
  2. Merge ultra-script pattern+XGB scores (5,316 flagged)
  3. Compute graph properties for ALL 625K addresses
  4. Recalculate hybrid score = 40% XGB + 30% pattern_boost + 30% soph_norm
  5. Cross-check: XGB vs Rules vs Graph agreement
  6. PR-curve threshold optimization → risk_level → fraud
  7. Save final parquet
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

print("=" * 80)
print("FINAL LABELED DATASET BUILD  (ultra outputs + graph + cross-check)")
print("=" * 80)
t_total = time.perf_counter()

# ── Paths ────────────────────────────────────────────────────────────────────
PARQUET_PATH = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
ULTRA_COMBINED = r"C:\amttp\processed\sophisticated_xgb_combined.csv"
PATTERN_CSV = r"C:\amttp\processed\sophisticated_fraud_patterns.csv"
ML_MODEL_PATH = r"C:\amttp\ml\Automation\ml_pipeline\models\trained\xgb.json"
ML_SCHEMA_PATH = r"C:\amttp\ml\Automation\ml_pipeline\models\feature_schema.json"
TEACHER_MODEL_PATH = r"C:\amttp\ml\Automation\TeacherAM\models\xgb.json"
TEACHER_SCHEMA_PATH = r"C:\amttp\ml\Automation\TeacherAM\metadata\feature_schema.json"
OUTPUT_PARQUET = r"C:\amttp\processed\eth_addresses_labeled_v2.parquet"

KNOWN_MIXERS = {a.lower() for a in [
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
]}
KNOWN_SANCTIONED = {a.lower() for a in [
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
]}
KNOWN_EXCHANGES = {a.lower() for a in [
    "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d",
    "0x28c6c06298d514db089934071355e5743bf21d60",
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549",
    "0x2b5634c42055806a59e9107ed44d43c426e58258",
    "0xeb2629a2734e272bcc07bda959863f316f4bd4cf",
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b",
    "0xfe9e8709d3215310075d67e3ed32a380ccf451c8",
]}

PATTERN_BOOST_WEIGHTS = {
    "SMURFING": 25, "LAYERING": 15, "FAN_OUT": 15, "FAN_IN": 15,
    "STRUCTURING": 20, "VELOCITY": 15, "PEELING": 20,
}

# ═══════════════════════════════════════════════════════════════════════════
# 1. LOAD TRANSACTIONS → AGGREGATE ALL 625K ADDRESSES
# ═══════════════════════════════════════════════════════════════════════════
print("\n[1/7] Loading transactions & aggregating ALL addresses …")
t0 = time.perf_counter()

df = pd.read_parquet(PARQUET_PATH)
df["from_address"] = df["from_address"].str.lower()
df["to_address"] = df["to_address"].str.lower()
df["value_eth"] = pd.to_numeric(df["value_eth"], errors="coerce").fillna(0)
df["gas_price_gwei"] = pd.to_numeric(df.get("gas_price_gwei", 0), errors="coerce").fillna(0)
df["gas_used"] = pd.to_numeric(df.get("gas_used", 21000), errors="coerce").fillna(21000)
df["block_timestamp"] = pd.to_datetime(df["block_timestamp"], utc=True, errors="coerce")

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

addr = sent.join(recv, how="outer").reset_index()
num_cols = addr.select_dtypes(include="number").columns
addr[num_cols] = addr[num_cols].fillna(0)
addr["total_transactions"] = addr["sent_count"] + addr["received_count"]
addr["balance"] = addr["total_received"] - addr["total_sent"]
addr["in_out_ratio"] = addr["received_count"] / (addr["sent_count"] + 1)
addr["unique_counterparties"] = addr["unique_receivers"] + addr["unique_senders"]
addr["avg_value"] = (addr["avg_sent"] + addr["avg_received"]) / 2
addr["neighbors"] = addr["unique_counterparties"]
addr["count"] = addr["total_transactions"]
addr["income"] = addr["balance"]

for c in ["first_sent_time", "last_sent_time", "first_received_time", "last_received_time"]:
    if c in addr.columns:
        addr[c] = pd.to_datetime(addr[c], errors="coerce")
first_act = addr[["first_sent_time", "first_received_time"]].min(axis=1)
last_act = addr[["last_sent_time", "last_received_time"]].max(axis=1)
addr["active_duration_mins"] = (last_act - first_act).dt.total_seconds().fillna(0) / 60

print(f"   {len(addr):,} addresses from {len(df):,} txs in {time.perf_counter()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════
# 2. MERGE ULTRA-SCRIPT PATTERN + XGB RESULTS
# ═══════════════════════════════════════════════════════════════════════════
print("\n[2/7] Merging ultra-script outputs …")
t0 = time.perf_counter()

ultra = pd.read_csv(ULTRA_COMBINED, low_memory=False)
ultra["address"] = ultra["address"].str.lower()
print(f"   Ultra combined: {len(ultra):,} flagged addresses")

# Columns from ultra we want
ultra_cols = [
    "address", "sophisticated_score", "patterns", "pattern_count",
    "xgb_raw_score", "xgb_normalized", "pattern_boost", "soph_normalized",
    "hybrid_score", "risk_level",
]
ultra_keep = [c for c in ultra_cols if c in ultra.columns]
ultra_sub = ultra[ultra_keep].copy()

# Rename ultra hybrid to avoid conflict during merge (we'll recompute)
ultra_sub = ultra_sub.rename(columns={
    "hybrid_score": "ultra_hybrid_score",
    "risk_level": "ultra_risk_level",
})

addr = addr.merge(ultra_sub, on="address", how="left")

# Fill NaN for non-flagged addresses
for c in ["sophisticated_score", "pattern_count", "xgb_raw_score",
          "xgb_normalized", "pattern_boost", "soph_normalized",
          "ultra_hybrid_score"]:
    if c in addr.columns:
        addr[c] = addr[c].fillna(0)

addr["patterns"] = addr["patterns"].fillna("")
addr["ultra_risk_level"] = addr["ultra_risk_level"].fillna("MINIMAL")

print(f"   Merged in {time.perf_counter()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════
# 3. RUN XGB ON ALL 625K ADDRESSES (not just the 5,316 flagged)
# ═══════════════════════════════════════════════════════════════════════════
print("\n[3/7] Running XGB on ALL 625K addresses …")
t0 = time.perf_counter()
import xgboost as xgb

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

# Backfill h_* features (for TeacherAM)
addr["h_value_in"] = addr["total_received"]
addr["h_value_out"] = addr["total_sent"]
addr["h_net_flow"] = addr["total_received"] - addr["total_sent"]
addr["h_value_to_contracts"] = 0.0
addr["h_tx_count"] = addr["total_transactions"]
addr["h_tx_in_count"] = addr["received_count"]
addr["h_tx_out_count"] = addr["sent_count"]
addr["h_counterparties"] = addr["unique_counterparties"]
addr["h_cp_per_tx"] = addr["h_counterparties"] / addr["h_tx_count"].clip(lower=1)
addr["h_self_dealing"] = 0.0
addr["h_value_per_cp"] = (addr["h_value_in"]+addr["h_value_out"]) / addr["h_counterparties"].clip(lower=1)
addr["h_value_per_tx"] = (addr["h_value_in"]+addr["h_value_out"]) / addr["h_tx_count"].clip(lower=1)
addr["h_complexity"] = np.log1p(addr["h_tx_count"])
addr["h_temporal_span"] = addr["active_duration_mins"]
addr["h_tx_frequency"] = addr["h_tx_count"] / addr["h_temporal_span"].clip(lower=1)


def _run_xgb(schema_path, model_path, label):
    with open(schema_path) as f:
        fnames = json.load(f)["feature_names"]
    aligned = pd.DataFrame(0.0, index=addr.index, columns=fnames)
    for feat in fnames:
        if feat in addr.columns:
            aligned[feat] = pd.to_numeric(addr[feat], errors="coerce")
        elif feat in FEATURE_MAP and FEATURE_MAP[feat] in addr.columns:
            aligned[feat] = pd.to_numeric(addr[FEATURE_MAP[feat]], errors="coerce")
    aligned = aligned.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    booster = xgb.Booster()
    booster.load_model(model_path)
    raw = booster.predict(xgb.DMatrix(aligned.values, feature_names=fnames))
    matched = (aligned.sum(axis=0) != 0).sum()
    # Sigmoid calibration k=30 @ p75
    cal = 1.0 / (1.0 + np.exp(-30 * (raw - np.percentile(raw, 75)))) * 100
    print(f"   [{label}] Features w/ data: {matched}/{len(fnames)}")
    print(f"   [{label}] Raw: [{raw.min():.6f}, {raw.max():.6f}]  Cal(0-100): [{cal.min():.1f}, {cal.max():.1f}]  median={np.median(cal):.1f}")
    return raw, cal

ml_raw, ml_cal = _run_xgb(ML_SCHEMA_PATH, ML_MODEL_PATH, "ml_pipeline")
addr["xgb_raw_score"] = ml_raw
addr["xgb_normalized"] = ml_cal

tam_raw, tam_cal = _run_xgb(TEACHER_SCHEMA_PATH, TEACHER_MODEL_PATH, "TeacherAM")
addr["teacher_raw_score"] = tam_raw
addr["teacher_normalized"] = tam_cal

print(f"   XGB done in {time.perf_counter()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════
# 4. GRAPH PROPERTIES FOR ALL 625K ADDRESSES
# ═══════════════════════════════════════════════════════════════════════════
print("\n[4/7] Computing graph properties …")
t0 = time.perf_counter()

addr["in_degree"] = addr["unique_senders"]
addr["out_degree"] = addr["unique_receivers"]
addr["degree"] = addr["in_degree"] + addr["out_degree"]
addr["degree_centrality"] = addr["degree"] / max(addr["degree"].max(), 1)
addr["betweenness_proxy"] = (
    (addr["in_degree"] / max(addr["in_degree"].max(), 1)) *
    (addr["out_degree"] / max(addr["out_degree"].max(), 1))
)

# Known-entity interaction counts
for target_set, prefix in [(KNOWN_MIXERS, "mixer"), (KNOWN_SANCTIONED, "sanctioned"), (KNOWN_EXCHANGES, "exchange")]:
    s2t = df[df["to_address"].isin(target_set)].groupby("from_address").size().rename(f"sent_to_{prefix}")
    s2t.index.name = "address"
    t2s = df[df["from_address"].isin(target_set)].groupby("to_address").size().rename(f"recv_from_{prefix}")
    t2s.index.name = "address"
    addr = addr.merge(s2t, on="address", how="left")
    addr = addr.merge(t2s, on="address", how="left")
    addr[f"sent_to_{prefix}"] = addr[f"sent_to_{prefix}"].fillna(0)
    addr[f"recv_from_{prefix}"] = addr[f"recv_from_{prefix}"].fillna(0)
    addr[f"{prefix}_interaction"] = addr[f"sent_to_{prefix}"] + addr[f"recv_from_{prefix}"]

addr["graph_risk_score"] = (
    addr["degree_centrality"] * 10 +
    addr["betweenness_proxy"] * 15 +
    (addr["mixer_interaction"] > 0).astype(float) * 30 +
    (addr["sanctioned_interaction"] > 0).astype(float) * 40 +
    (addr["exchange_interaction"] > 0).astype(float) * 5
).clip(0, 100)

addr["is_mixer"] = addr["address"].isin(KNOWN_MIXERS).astype(int)
addr["is_sanctioned"] = addr["address"].isin(KNOWN_SANCTIONED).astype(int)
addr["is_exchange"] = addr["address"].isin(KNOWN_EXCHANGES).astype(int)

print(f"   Graph done in {time.perf_counter()-t0:.1f}s")
print(f"   Mixer interactions > 0:      {(addr['mixer_interaction']>0).sum():,}")
print(f"   Sanctioned interactions > 0: {(addr['sanctioned_interaction']>0).sum():,}")
print(f"   Exchange interactions > 0:   {(addr['exchange_interaction']>0).sum():,}")

# ═══════════════════════════════════════════════════════════════════════════
# 5. RECOMPUTE HYBRID SCORE (40% XGB + 30% pattern_boost + 30% soph_norm)
# ═══════════════════════════════════════════════════════════════════════════
print("\n[5/7] Computing hybrid scores …")
t0 = time.perf_counter()

max_soph = addr["sophisticated_score"].max()
if max_soph > 0:
    addr["soph_normalized"] = (addr["sophisticated_score"] / max_soph) * 100
else:
    addr["soph_normalized"] = 0

# pattern_boost: recompute for completeness
def calc_boost(p):
    if not p:
        return 0
    return min(sum(PATTERN_BOOST_WEIGHTS.get(x.strip(), 0) for x in str(p).split(",")), 100)

addr["pattern_boost"] = addr["patterns"].apply(calc_boost)

addr["hybrid_score"] = (
    addr["xgb_normalized"] * 0.40 +
    addr["pattern_boost"] * 0.30 +
    addr["soph_normalized"] * 0.30
)

# Multi-signal bonus
def count_signals(row):
    n = 0
    if row["xgb_normalized"] >= 50:
        n += 1
    if row["graph_risk_score"] >= 10:
        n += 1
    if row["pattern_count"] >= 3:
        n += 1
    return n

addr["signal_count"] = addr.apply(count_signals, axis=1)
addr.loc[addr["signal_count"] == 2, "hybrid_score"] *= 1.2
addr.loc[addr["signal_count"] >= 3, "hybrid_score"] *= 1.5
addr["hybrid_score"] = addr["hybrid_score"].clip(0, 100)

print(f"   Hybrid score: [{addr['hybrid_score'].min():.1f}, {addr['hybrid_score'].max():.1f}]  median={addr['hybrid_score'].median():.1f}")
print(f"   Multi-signal ≥2: {(addr['signal_count'] >= 2).sum():,}")
print(f"   Done in {time.perf_counter()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════
# 6. CROSS-CHECK: XGB vs RULES vs GRAPH
# ═══════════════════════════════════════════════════════════════════════════
print("\n[6/7] CROSS-CHECK: Model vs Rules vs Graph …")
t0 = time.perf_counter()

# Define per-signal flags
xgb_flag = addr["xgb_normalized"] >= np.percentile(addr["xgb_normalized"], 95)    # top 5%
rule_flag = addr["pattern_count"] >= 1
graph_flag = addr["graph_risk_score"] >= 5                                         # any notable graph signal

n_xgb = xgb_flag.sum()
n_rule = rule_flag.sum()
n_graph = graph_flag.sum()

# Agreement matrix
xgb_only  = xgb_flag & ~rule_flag & ~graph_flag
rule_only = rule_flag & ~xgb_flag & ~graph_flag
graph_only = graph_flag & ~xgb_flag & ~rule_flag
xgb_rule  = xgb_flag & rule_flag & ~graph_flag
xgb_graph = xgb_flag & graph_flag & ~rule_flag
rule_graph = rule_flag & graph_flag & ~xgb_flag
all_three = xgb_flag & rule_flag & graph_flag

print(f"   Signal activation (out of {len(addr):,} addresses):")
print(f"     XGB (top 5%):     {n_xgb:>8,}")
print(f"     Rules (≥1 patt):  {n_rule:>8,}")
print(f"     Graph (score≥5):  {n_graph:>8,}")
print()
print(f"   AGREEMENT MATRIX:")
print(f"     XGB only:                {xgb_only.sum():>6,}")
print(f"     Rule only:               {rule_only.sum():>6,}")
print(f"     Graph only:              {graph_only.sum():>6,}")
print(f"     XGB ∩ Rule:              {xgb_rule.sum():>6,}")
print(f"     XGB ∩ Graph:             {xgb_graph.sum():>6,}")
print(f"     Rule ∩ Graph:            {rule_graph.sum():>6,}")
print(f"     ALL THREE (XGB∩Rule∩G):  {all_three.sum():>6,}")
print()

# Overlap percentages
xgb_rule_overlap = (xgb_flag & rule_flag).sum()
xgb_graph_overlap = (xgb_flag & graph_flag).sum()
rule_graph_overlap = (rule_flag & graph_flag).sum()

print(f"   OVERLAP RATES:")
print(f"     XGB ∩ Rules / XGB:   {xgb_rule_overlap}/{n_xgb}  = {xgb_rule_overlap/max(n_xgb,1)*100:.1f}%")
print(f"     XGB ∩ Graph / XGB:   {xgb_graph_overlap}/{n_xgb}  = {xgb_graph_overlap/max(n_xgb,1)*100:.1f}%")
print(f"     Rules ∩ Graph / Rules: {rule_graph_overlap}/{n_rule}  = {rule_graph_overlap/max(n_rule,1)*100:.1f}%")
print()

# For flagged addresses, break down which signals agree
flagged_ultra = addr["sophisticated_score"] > 0
flagged_set = addr[flagged_ultra].copy()

flagged_set["has_xgb"] = flagged_set["xgb_normalized"] >= np.percentile(addr["xgb_normalized"], 95)
flagged_set["has_rule"] = flagged_set["pattern_count"] >= 1
flagged_set["has_graph"] = flagged_set["graph_risk_score"] >= 5

n_flagged = len(flagged_set)
n_both_xgb_rule = (flagged_set["has_xgb"] & flagged_set["has_rule"]).sum()
n_both_rule_graph = (flagged_set["has_rule"] & flagged_set["has_graph"]).sum()
n_all3 = (flagged_set["has_xgb"] & flagged_set["has_rule"] & flagged_set["has_graph"]).sum()

print(f"   AMONG {n_flagged:,} ULTRA-FLAGGED ADDRESSES:")
print(f"     Also flagged by XGB:   {flagged_set['has_xgb'].sum():,} ({flagged_set['has_xgb'].mean()*100:.1f}%)")
print(f"     Also flagged by Graph: {flagged_set['has_graph'].sum():,} ({flagged_set['has_graph'].mean()*100:.1f}%)")
print(f"     XGB ∩ Rule ∩ Graph:    {n_all3:,}")
print()

# Show top 10 multi-signal addresses
ms = addr[addr["signal_count"] >= 2].nlargest(10, "hybrid_score")
print(f"   TOP 10 MULTI-SIGNAL ADDRESSES:")
for _, r in ms.iterrows():
    flags = []
    if r["xgb_normalized"] >= np.percentile(addr["xgb_normalized"], 95):
        flags.append("XGB")
    if r["pattern_count"] >= 1:
        flags.append(f"RULES({int(r['pattern_count'])}p)")
    if r["graph_risk_score"] >= 5:
        flags.append(f"GRAPH({r['graph_risk_score']:.1f})")
    print(f"     {r['address']}  hybrid={r['hybrid_score']:.1f}  signals={','.join(flags)}")

# Correlation between signals
print(f"\n   SIGNAL CORRELATIONS (Spearman):")
from scipy.stats import spearmanr
for a, b in [("xgb_normalized", "sophisticated_score"),
             ("xgb_normalized", "graph_risk_score"),
             ("sophisticated_score", "graph_risk_score")]:
    rho, pval = spearmanr(addr[a], addr[b])
    print(f"     {a:30s} vs {b:25s}  ρ={rho:+.4f}  p={pval:.2e}")

print(f"   Cross-check done in {time.perf_counter()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════
# 7. PR-CURVE THRESHOLD → RISK LEVEL → FRAUD LABEL
# ═══════════════════════════════════════════════════════════════════════════
print("\n[7/7] PR-curve threshold optimization …")
t0 = time.perf_counter()

pseudo = (addr["pattern_count"] >= 3).astype(int)
pos = pseudo.sum()
print(f"   Pseudo positives (pattern≥3): {pos:,}")

best_f1, best_t = 0, 60
for t in np.linspace(10, 95, 50):
    p = (addr["hybrid_score"] >= t).astype(int)
    tp = ((p == 1) & (pseudo == 1)).sum()
    fp = ((p == 1) & (pseudo == 0)).sum()
    fn = ((p == 0) & (pseudo == 1)).sum()
    pr = tp / (tp + fp) if (tp + fp) else 0
    rc = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * pr * rc / (pr + rc) if (pr + rc) else 0
    if f1 > best_f1:
        best_f1, best_t = f1, t

ct = min(best_t + 15, 95)
ht = best_t
mt = max(best_t - 15, 20)

print(f"   Best F1={best_f1:.3f} @ threshold={best_t:.1f}")
print(f"   CRITICAL≥{ct:.1f} | HIGH≥{ht:.1f} | MEDIUM≥{mt:.1f} | LOW≥20")

addr["risk_level"] = addr["hybrid_score"].apply(
    lambda s: "CRITICAL" if s >= ct else "HIGH" if s >= ht else "MEDIUM" if s >= mt else "LOW" if s >= 20 else "MINIMAL"
)
addr["fraud"] = addr["risk_level"].isin(["CRITICAL", "HIGH"]).astype(int)
addr["risk_class"] = addr["risk_level"].map({"MINIMAL": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4})

print(f"   Done in {time.perf_counter()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════
# SAVE
# ═══════════════════════════════════════════════════════════════════════════
print("\n[SAVE] Writing final parquet …")
t0 = time.perf_counter()

addr = addr.sort_values("hybrid_score", ascending=False)
Path(OUTPUT_PARQUET).parent.mkdir(parents=True, exist_ok=True)
addr.to_parquet(OUTPUT_PARQUET, index=False)

print(f"   Saved {len(addr):,} rows × {len(addr.columns)} cols to {OUTPUT_PARQUET}")
print(f"   in {time.perf_counter()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ═══════════════════════════════════════════════════════════════════════════
elapsed = time.perf_counter() - t_total
print(f"\n{'='*80}")
print("FINAL SUMMARY")
print(f"{'='*80}")
print(f"  Addresses:       {len(addr):,}")
print(f"  Transactions:    {len(df):,}")
print(f"  Columns:         {len(addr.columns)}")
print()
for lev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "MINIMAL"]:
    n = (addr["risk_level"] == lev).sum()
    print(f"   {lev:10}: {n:>8,}  ({n/len(addr)*100:>5.2f}%)")

fraud_n = addr["fraud"].sum()
print(f"\n  fraud=1: {fraud_n:,} ({fraud_n/len(addr)*100:.2f}%)")

# Prior schema check
prior = ["address","sent_count","received_count","total_transactions","total_sent",
         "total_received","balance","avg_sent","avg_received","avg_value","max_sent",
         "max_received","min_sent","min_received","std_sent","std_received",
         "total_gas_sent","avg_gas_used","avg_gas_price","unique_receivers",
         "unique_senders","unique_counterparties","in_out_ratio","active_duration_mins",
         "sophisticated_score","patterns","pattern_count","xgb_raw_score",
         "xgb_normalized","pattern_boost","soph_normalized","hybrid_score",
         "risk_level","fraud","risk_class"]
present = sum(1 for c in prior if c in addr.columns)
print(f"\n  Prior-schema cols: {present}/{len(prior)}")
print(f"  Total time: {elapsed:.1f}s")
print(f"{'='*80}")
