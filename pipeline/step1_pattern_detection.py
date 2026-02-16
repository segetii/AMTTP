"""
ULTRA-FAST SOPHISTICATED FRAUD DETECTION
=========================================
Maximum speed using:
- Polars (5-10x faster than pandas)
- Lazy evaluation with query optimization
- Parallel execution across all cores
- Streaming for memory efficiency
- Pre-filtering to reduce data early

Detects: SMURFING, LAYERING, FAN-OUT, FAN-IN, PEELING, STRUCTURING, VELOCITY
"""
import sys
import io
import os
import time
import numpy as np
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

print("="*70)
print("ULTRA-FAST FRAUD DETECTION (Polars Engine)")
print("="*70)

# Check for Polars
try:
    import polars as pl
    print(f"Polars version: {pl.__version__}")
    print("Engine: POLARS (Rust-based, parallel)")
except ImportError:
    print("Polars not installed. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "polars", "-q"])
    import polars as pl
    print("Polars installed successfully!")

# Configuration
PARQUET_PATH = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
OUTPUT_DIR = r"c:\amttp\processed"

# Thresholds
MIN_TX_COUNT = 3  # Skip addresses with fewer transactions
SMURFING_THRESHOLD = 1.0
FAN_THRESHOLD = 10
MAX_PER_PATTERN = 5000      # Safety cap (was hard 1000)


def _adaptive_cap(df, score_col, max_cap=MAX_PER_PATTERN):
    """
    Replace arbitrary .head(1000) with distribution-aware filtering.

    Why this is better than a hard cap:
    ─────────────────────────────────────────────────────────────────────
    1. ADAPTS TO DATA SIZE:  .head(1000) keeps the same count whether
       the dataset has 2K or 200K qualifiers. This keeps the top 50%
       of qualifiers (above-median scorers), so the retention scales
       with the actual pattern prevalence.

    2. SCORE-AWARE:  Address #1001 might score 94.9 while #1000 scores
       95.0 — a hard cap silently drops it.  We cut at the statistical
       midpoint of the score distribution instead, so every address
       above the natural "average suspiciousness" for that pattern is
       retained.

    3. PRESERVES GRADIENT:  For training data, the student model needs
       to see the full spectrum of pattern intensity — not just the top
       1000 extremes. Keeping ~3-4K per pattern (vs 1000) exposes the
       model to moderate-risk addresses that are critical for learning
       decision boundaries.

    4. SAFETY CAP:  Still enforced at 5000 to prevent combinatorial
       explosion on degenerate distributions.

    Cutoff: median (p50) of qualifying scores.
    Typical retention: ~2000-4000 per pattern (from 4000-8000 qualifiers).
    """
    if len(df) == 0:
        return df
    total = len(df)
    p50 = float(df[score_col].median())
    df = df.filter(pl.col(score_col) >= p50)
    if len(df) > max_cap:
        df = df.head(max_cap)
    kept = len(df)
    print(f"           Adaptive: {total:,} qualifiers → {kept:,} kept "
          f"(≥ median={p50:.1f}, cap={max_cap})")
    return df


def optimize_thresholds_pr_curve(scores, pattern_counts, verbose=True):
    """
    Optimize risk thresholds using PR-curve analysis.
    Uses pattern_count >= 3 as pseudo ground truth (multi-signal = likely fraud)
    Returns optimal thresholds for each risk level.
    """
    import numpy as np
    
    # Use multi-pattern as pseudo ground truth
    pseudo_labels = (pattern_counts >= 3).astype(int)
    
    if pseudo_labels.sum() == 0:
        if verbose:
            print("[PR-CURVE] No multi-pattern addresses found for optimization")
        return {'CRITICAL': 80, 'HIGH': 60, 'MEDIUM': 40, 'LOW': 20}
    
    # Test different thresholds
    thresholds = np.linspace(10, 95, 50)
    best_f1 = 0
    best_threshold = 60
    
    results = []
    for thresh in thresholds:
        predictions = (scores >= thresh).astype(int)
        
        tp = ((predictions == 1) & (pseudo_labels == 1)).sum()
        fp = ((predictions == 1) & (pseudo_labels == 0)).sum()
        fn = ((predictions == 0) & (pseudo_labels == 1)).sum()
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        results.append({
            'threshold': thresh,
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'tp': tp,
            'fp': fp
        })
        
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = thresh
    
    if verbose:
        print(f"\n[PR-CURVE OPTIMIZATION]")
        print(f"   Pseudo labels (pattern_count >= 3): {pseudo_labels.sum():,}")
        print(f"   Best F1 threshold: {best_threshold:.1f} (F1={best_f1:.3f})")
        
        # Show a few key points
        for r in results:
            if r['threshold'] in [30, 50, 60, 70, 80]:
                print(f"   Threshold {r['threshold']:.0f}: P={r['precision']:.3f} R={r['recall']:.3f} F1={r['f1']:.3f}")
    
    # Dynamic thresholds based on PR-curve analysis
    # CRITICAL: Very high precision (few false positives)
    # HIGH: Best F1 balance
    # MEDIUM: Higher recall
    
    critical_thresh = best_threshold + 15 if best_threshold + 15 < 95 else 85
    high_thresh = best_threshold
    medium_thresh = best_threshold - 15 if best_threshold - 15 > 20 else 30
    
    return {
        'CRITICAL': critical_thresh,
        'HIGH': high_thresh,
        'MEDIUM': medium_thresh,
        'LOW': 20,
        'best_f1': best_f1,
        'best_threshold': best_threshold
    }

print(f"\nStarted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
overall_start = time.perf_counter()

# =============================================================================
# LOAD DATA (Lazy for memory efficiency)
# =============================================================================
print("\n[1/7] Loading data with lazy evaluation...")
t0 = time.perf_counter()

# Use scan for lazy loading - only reads what's needed
lf = pl.scan_parquet(PARQUET_PATH)

# Immediately lowercase addresses and select needed columns only
lf = lf.select([
    pl.col("from_address").str.to_lowercase().alias("from_address"),
    pl.col("to_address").str.to_lowercase().alias("to_address"),
    pl.col("value_eth").cast(pl.Float64).fill_null(0),
    pl.col("block_timestamp"),
    pl.col("block_number").cast(pl.Int64).fill_null(0),
])

# Collect to get row count
df = lf.collect()
print(f"       Loaded {len(df):,} transactions in {time.perf_counter()-t0:.2f}s")

# =============================================================================
# PRE-COMPUTE AGGREGATIONS (Single parallel pass)
# =============================================================================
print("\n[2/7] Computing aggregations (parallel)...")
t0 = time.perf_counter()

# Sender aggregations
sender_agg = df.lazy().group_by("from_address").agg([
    pl.count().alias("tx_count"),
    pl.col("value_eth").sum().alias("total_sent"),
    pl.col("value_eth").mean().alias("avg_value"),
    pl.col("value_eth").std().alias("std_value"),
    pl.col("value_eth").min().alias("min_value"),
    pl.col("value_eth").max().alias("max_value"),
    pl.col("to_address").n_unique().alias("unique_receivers"),
    pl.col("block_timestamp").min().alias("first_tx"),
    pl.col("block_timestamp").max().alias("last_tx"),
]).collect()

# Receiver aggregations  
receiver_agg = df.lazy().group_by("to_address").agg([
    pl.count().alias("rx_count"),
    pl.col("value_eth").sum().alias("total_received"),
    pl.col("value_eth").mean().alias("avg_received"),
    pl.col("from_address").n_unique().alias("unique_senders"),
    pl.col("block_timestamp").min().alias("first_rx"),
    pl.col("block_timestamp").max().alias("last_rx"),
]).collect()

print(f"       Computed in {time.perf_counter()-t0:.2f}s")
print(f"       Unique senders: {len(sender_agg):,} | Unique receivers: {len(receiver_agg):,}")

# =============================================================================
# 1. SMURFING DETECTION
# =============================================================================
print("\n[3/7] Detecting SMURFING...")
t0 = time.perf_counter()

smurfers = sender_agg.lazy().filter(
    (pl.col("tx_count") >= 5) &
    (pl.col("avg_value") < SMURFING_THRESHOLD) &
    (pl.col("total_sent") > 5) &
    (pl.col("unique_receivers") >= 3)
).with_columns([
    (
        (pl.col("tx_count") / 10).clip(0, 1) * 30 +
        (1 - pl.col("avg_value") / SMURFING_THRESHOLD).clip(0, 1) * 25 +
        (pl.col("unique_receivers") / 10).clip(0, 1) * 20 +
        (pl.col("total_sent") / 50).clip(0, 1) * 25
    ).alias("smurf_score")
]).filter(
    pl.col("smurf_score") > 30
).sort("smurf_score", descending=True).collect()
smurfers = _adaptive_cap(smurfers, "smurf_score")

print(f"       Found {len(smurfers)} SMURFING addresses in {time.perf_counter()-t0:.2f}s")

# =============================================================================
# 2. FAN-OUT DETECTION
# =============================================================================
print("\n[4/7] Detecting FAN-OUT...")
t0 = time.perf_counter()

fan_out = sender_agg.lazy().filter(
    (pl.col("unique_receivers") >= FAN_THRESHOLD) &
    (pl.col("tx_count") >= FAN_THRESHOLD)
).with_columns([
    (
        (pl.col("unique_receivers") / 20).clip(0, 1) * 40 +
        (pl.col("tx_count") / 20).clip(0, 1) * 30 +
        (pl.col("total_sent") / 100).clip(0, 1) * 30
    ).alias("fan_out_score")
]).sort("fan_out_score", descending=True).collect()
fan_out = _adaptive_cap(fan_out, "fan_out_score")

print(f"       Found {len(fan_out)} FAN-OUT addresses in {time.perf_counter()-t0:.2f}s")

# =============================================================================
# 3. FAN-IN DETECTION
# =============================================================================
print("\n[5/7] Detecting FAN-IN...")
t0 = time.perf_counter()

fan_in = receiver_agg.lazy().filter(
    (pl.col("unique_senders") >= FAN_THRESHOLD) &
    (pl.col("rx_count") >= FAN_THRESHOLD)
).with_columns([
    (
        (pl.col("unique_senders") / 20).clip(0, 1) * 40 +
        (pl.col("rx_count") / 20).clip(0, 1) * 30 +
        (pl.col("total_received") / 100).clip(0, 1) * 30
    ).alias("fan_in_score")
]).sort("fan_in_score", descending=True).collect()
fan_in = _adaptive_cap(fan_in, "fan_in_score")

print(f"       Found {len(fan_in)} FAN-IN addresses in {time.perf_counter()-t0:.2f}s")

# =============================================================================
# 4. LAYERING DETECTION (Pass-through addresses)
# =============================================================================
print("\n[6/7] Detecting LAYERING...")
t0 = time.perf_counter()

# Join sender and receiver stats
layering = sender_agg.lazy().join(
    receiver_agg.lazy().rename({"to_address": "from_address"}),
    on="from_address",
    how="inner"
).with_columns([
    (pl.col("total_sent") / pl.col("total_received").clip(lower_bound=0.001)).clip(0, 1).alias("pass_ratio")
]).filter(
    (pl.col("pass_ratio") > 0.8) &
    (pl.col("rx_count") >= 2) &
    (pl.col("tx_count") >= 2)
).with_columns([
    (
        pl.col("pass_ratio") * 40 +
        (pl.col("rx_count") / 5).clip(0, 1) * 30 +
        (pl.col("tx_count") / 5).clip(0, 1) * 30
    ).alias("layering_score")
]).sort("layering_score", descending=True).collect()
layering = _adaptive_cap(layering, "layering_score")

print(f"       Found {len(layering)} LAYERING addresses in {time.perf_counter()-t0:.2f}s")

# =============================================================================
# 5. ROUND AMOUNT STRUCTURING
# =============================================================================
print("\n[7/7] Detecting STRUCTURING...")
t0 = time.perf_counter()

# Define round amounts
round_amounts = [0.1, 0.5, 1.0, 5.0, 10.0, 50.0, 100.0, 500.0, 1000.0]

# Detect round transactions
df_with_round = df.lazy().with_columns([
    (
        ((pl.col("value_eth") >= 1) & (pl.col("value_eth") == pl.col("value_eth").floor())) |
        pl.col("value_eth").is_in(round_amounts)
    ).alias("is_round")
])

# Aggregate round transactions by sender
round_agg = df_with_round.filter(pl.col("is_round")).group_by("from_address").agg([
    pl.count().alias("round_tx_count"),
    pl.col("value_eth").sum().alias("round_total")
]).collect()

# Join with total tx count
structuring = round_agg.lazy().join(
    sender_agg.lazy().select(["from_address", "tx_count"]),
    on="from_address",
    how="left"
).with_columns([
    (pl.col("round_tx_count") / pl.col("tx_count")).alias("round_ratio")
]).filter(
    (pl.col("round_tx_count") >= 3) &
    (pl.col("round_ratio") > 0.5)
).with_columns([
    (
        pl.col("round_ratio") * 40 +
        (pl.col("round_tx_count") / 10).clip(0, 1) * 30 +
        (pl.col("round_total") / 50).clip(0, 1) * 30
    ).alias("structuring_score")
]).sort("structuring_score", descending=True).collect()
structuring = _adaptive_cap(structuring, "structuring_score")

print(f"       Found {len(structuring)} STRUCTURING addresses in {time.perf_counter()-t0:.2f}s")

# =============================================================================
# 6. VELOCITY ANOMALIES
# =============================================================================
print("\n       Detecting VELOCITY...")
t0 = time.perf_counter()

# Hourly aggregation
hourly = df.lazy().with_columns([
    pl.col("block_timestamp").dt.truncate("1h").alias("hour")
]).group_by(["from_address", "hour"]).agg([
    pl.count().alias("tx_count")
]).collect()

velocity_stats = hourly.lazy().group_by("from_address").agg([
    pl.col("tx_count").mean().alias("avg_tx_hour"),
    pl.col("tx_count").max().alias("max_tx_hour")
]).with_columns([
    (pl.col("max_tx_hour") / pl.col("avg_tx_hour").clip(lower_bound=0.001)).alias("velocity_ratio")
]).filter(
    (pl.col("max_tx_hour") >= 5) &
    (pl.col("velocity_ratio") > 3)
).with_columns([
    (
        (pl.col("velocity_ratio") / 10).clip(0, 1) * 50 +
        (pl.col("max_tx_hour") / 20).clip(0, 1) * 50
    ).alias("velocity_score")
]).sort("velocity_score", descending=True).collect()
velocity_stats = _adaptive_cap(velocity_stats, "velocity_score")

print(f"       Found {len(velocity_stats)} VELOCITY anomalies in {time.perf_counter()-t0:.2f}s")

# =============================================================================
# 7. PEELING CHAIN (Optimized)
# =============================================================================
print("\n       Detecting PEELING...")
t0 = time.perf_counter()

# Sort by sender and time, compute value differences
peeling = df.lazy().sort(["from_address", "block_timestamp"]).with_columns([
    pl.col("value_eth").shift(1).over("from_address").alias("prev_value")
]).filter(
    pl.col("prev_value").is_not_null()
).with_columns([
    (pl.col("value_eth") < pl.col("prev_value")).alias("is_decrease")
]).group_by("from_address").agg([
    pl.count().alias("pair_count"),
    pl.col("is_decrease").sum().alias("decrease_count"),
    pl.col("value_eth").first().alias("last_value"),
    pl.col("prev_value").last().alias("first_value"),
]).filter(
    pl.col("pair_count") >= 2
).with_columns([
    (pl.col("decrease_count") / pl.col("pair_count")).alias("decrease_ratio")
]).filter(
    pl.col("decrease_ratio") > 0.6
).with_columns([
    (
        pl.col("decrease_ratio") * 50 +
        (pl.col("pair_count") / 10).clip(0, 1) * 50
    ).alias("peeling_score")
]).sort("peeling_score", descending=True).collect()
peeling = _adaptive_cap(peeling, "peeling_score")

print(f"       Found {len(peeling)} PEELING addresses in {time.perf_counter()-t0:.2f}s")

# =============================================================================
# COMBINE ALL SCORES
# =============================================================================
print("\n" + "="*70)
print("COMBINING SCORES...")
t0 = time.perf_counter()

# Collect all scored addresses
all_scores = []

if len(smurfers) > 0:
    all_scores.append(smurfers.select([
        pl.col("from_address").alias("address"),
        pl.col("smurf_score").alias("score"),
        pl.lit("SMURFING").alias("pattern")
    ]))

if len(fan_out) > 0:
    all_scores.append(fan_out.select([
        pl.col("from_address").alias("address"),
        pl.col("fan_out_score").alias("score"),
        pl.lit("FAN_OUT").alias("pattern")
    ]))

if len(fan_in) > 0:
    all_scores.append(fan_in.select([
        pl.col("to_address").alias("address"),
        pl.col("fan_in_score").alias("score"),
        pl.lit("FAN_IN").alias("pattern")
    ]))

if len(layering) > 0:
    all_scores.append(layering.select([
        pl.col("from_address").alias("address"),
        pl.col("layering_score").alias("score"),
        pl.lit("LAYERING").alias("pattern")
    ]))

if len(structuring) > 0:
    all_scores.append(structuring.select([
        pl.col("from_address").alias("address"),
        pl.col("structuring_score").alias("score"),
        pl.lit("STRUCTURING").alias("pattern")
    ]))

if len(velocity_stats) > 0:
    all_scores.append(velocity_stats.select([
        pl.col("from_address").alias("address"),
        pl.col("velocity_score").alias("score"),
        pl.lit("VELOCITY").alias("pattern")
    ]))

if len(peeling) > 0:
    all_scores.append(peeling.select([
        pl.col("from_address").alias("address"),
        pl.col("peeling_score").alias("score"),
        pl.lit("PEELING").alias("pattern")
    ]))

# Combine all
if all_scores:
    combined = pl.concat(all_scores)
    
    # Aggregate by address
    final = combined.lazy().group_by("address").agg([
        pl.col("score").sum().alias("sophisticated_score"),
        pl.col("pattern").alias("patterns"),
        pl.count().alias("pattern_count")
    ]).with_columns([
        pl.col("patterns").list.join(", ")
    ]).sort("sophisticated_score", descending=True).collect()
    
    print(f"       Combined {len(final):,} addresses in {time.perf_counter()-t0:.2f}s")
else:
    final = pl.DataFrame({"address": [], "sophisticated_score": [], "patterns": [], "pattern_count": []})

# =============================================================================
# SAVE RESULTS
# =============================================================================
output_path = Path(OUTPUT_DIR) / "sophisticated_fraud_patterns.csv"
final.write_csv(str(output_path))

# =============================================================================
# SUMMARY
# =============================================================================

print("\n" + "="*70)
print("RESULTS SUMMARY")
print("="*70)

print(f"\nTotal addresses with patterns: {len(final):,}")
multi_pattern = final.filter(pl.col("pattern_count") > 1)
print(f"Multi-pattern addresses: {len(multi_pattern):,}")

print("\nPattern Distribution:")
pattern_counts = {
    "SMURFING": len(smurfers),
    "FAN_OUT": len(fan_out),
    "FAN_IN": len(fan_in),
    "LAYERING": len(layering),
    "STRUCTURING": len(structuring),
    "VELOCITY": len(velocity_stats),
    "PEELING": len(peeling),
}
for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
    print(f"   {pattern}: {count:,}")

print(f"\nTOP 20 SOPHISTICATED FRAUD SUSPECTS:")
print("-" * 70)
for row in final.head(20).iter_rows(named=True):
    print(f"  {row['address']}")
    print(f"    Score: {row['sophisticated_score']:.1f} | Patterns: {row['patterns']}")

print(f"\nResults saved to: {output_path}")

# =============================================================================
# XGBOOST CROSS-VALIDATION (with calibrated thresholds)
# =============================================================================
print(f"\n{'='*70}")
print("XGBOOST CROSS-VALIDATION")
print("="*70)

try:
    import xgboost as xgb
    import json
    
    # Load XGBoost model
    model_path = r"c:\amttp\ml\Automation\ml_pipeline\models\trained\xgb.json"
    schema_path = r"c:\amttp\ml\Automation\ml_pipeline\models\feature_schema.json"
    
    if os.path.exists(model_path) and os.path.exists(schema_path):
        print("\n[XGB] Loading model and feature schema...")
        model = xgb.Booster()
        model.load_model(model_path)
        
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        feature_names = schema['feature_names']
        
        # Engineer features from transaction data for each flagged address
        print("[XGB] Engineering features for flagged addresses...")
        flagged_addresses = final.select("address").to_series().to_list()
        
        # Filter transactions for flagged addresses only (df is already collected)
        flagged_txs = df.filter(
            pl.col("from_address").is_in(flagged_addresses) | 
            pl.col("to_address").is_in(flagged_addresses)
        )
        
        print(f"[XGB] Found {len(flagged_txs):,} transactions involving {len(flagged_addresses):,} flagged addresses")
        
        # Pre-compute address-level aggregations using Polars (fast)
        sent_agg = flagged_txs.group_by("from_address").agg([
            pl.len().alias("sent_tnx"),
            pl.col("value_eth").sum().alias("total_sent"),
            pl.col("value_eth").mean().alias("avg_val_sent"),
            pl.col("value_eth").min().alias("min_val_sent"),
            pl.col("value_eth").max().alias("max_val_sent"),
            pl.col("value_eth").std().alias("std_val_sent"),
            pl.col("to_address").n_unique().alias("unique_sent_to"),
            pl.col("block_timestamp").min().alias("first_sent"),
            pl.col("block_timestamp").max().alias("last_sent"),
        ]).rename({"from_address": "address"})
        
        recv_agg = flagged_txs.group_by("to_address").agg([
            pl.len().alias("received_tnx"),
            pl.col("value_eth").sum().alias("total_received"),
            pl.col("value_eth").mean().alias("avg_val_received"),
            pl.col("value_eth").min().alias("min_value_received"),
            pl.col("value_eth").max().alias("max_value_received"),
            pl.col("value_eth").std().alias("std_val_received"),
            pl.col("from_address").n_unique().alias("unique_recv_from"),
            pl.col("block_timestamp").min().alias("first_recv"),
            pl.col("block_timestamp").max().alias("last_recv"),
        ]).rename({"to_address": "address"})
        
        # Join sent and received aggregations
        addr_features = sent_agg.join(recv_agg, on="address", how="full", coalesce=True)
        addr_features = addr_features.fill_null(0)
        
        # Compute derived features matching the schema
        addr_features = addr_features.with_columns([
            (pl.col("total_received") - pl.col("total_sent")).alias("total_ether_balance"),
            (pl.col("total_received") - pl.col("total_sent")).alias("income"),
            (pl.col("sent_tnx") + pl.col("received_tnx")).alias("count"),
            (pl.col("unique_sent_to") + pl.col("unique_recv_from")).alias("neighbors"),
        ])
        
        # Create feature matrix matching schema
        print(f"[XGB] Creating feature matrix for {len(addr_features):,} addresses...")
        
        # Map computed features to schema names
        available_mapping = {
            "avg_val_sent": "avg_val_sent",
            "avg_val_received": "avg_val_received", 
            "min_val_sent": "min_val_sent",
            "max_val_sent": "max_val_sent",
            "min_value_received": "min_value_received",
            "max_value_received": "max_value_received",
            "sent_tnx": "sent_tnx",
            "received_tnx": "received_tnx",
            "count": "count",
            "neighbors": "neighbors",
            "total_ether_balance": "total_ether_balance",
            "income": "income",
            "total_ether_sent": "total_sent",
            "total_ether_received": "total_received",
        }
        
        # Build feature matrix
        feature_matrix = np.zeros((len(addr_features), len(feature_names)), dtype=np.float32)
        addr_df = addr_features.to_pandas()
        addr_df = addr_df.set_index("address")
        
        for i, feat in enumerate(feature_names):
            if feat in available_mapping and available_mapping[feat] in addr_df.columns:
                feature_matrix[:, i] = addr_df[available_mapping[feat]].fillna(0).values
        
        # Run XGBoost predictions
        print("[XGB] Running predictions...")
        dmatrix = xgb.DMatrix(feature_matrix, feature_names=feature_names)
        xgb_raw_scores = model.predict(dmatrix)
        
        # RECALIBRATION: The model outputs small scores (0-1%) because many features are 0
        # Apply sigmoid calibration to spread scores more meaningfully
        # Formula: calibrated = 1 / (1 + exp(-k * (raw - threshold)))
        # k=30 provides better spread than k=50/500 (less aggressive, more granular)
        
        median_score = np.median(xgb_raw_scores)
        k = 30  # Scaling factor - k=30 for better spread (was 500, too aggressive)
        
        # Sigmoid calibration with percentile-based threshold for better separation
        # Use 75th percentile instead of median for more nuanced scoring
        p75_score = np.percentile(xgb_raw_scores, 75)
        xgb_calibrated = 1 / (1 + np.exp(-k * (xgb_raw_scores - p75_score)))
        
        # Scale to 0-100
        xgb_normalized = xgb_calibrated * 100
        
        print(f"\n[XGB] Score Calibration:")
        print(f"   Raw scores:   Min={xgb_raw_scores.min():.4%} | Max={xgb_raw_scores.max():.4%} | Median={median_score:.4%}")
        print(f"   Calibrated:   Min={xgb_normalized.min():.1f} | Max={xgb_normalized.max():.1f} | Median={np.median(xgb_normalized):.1f}")
        
        # Percentile-based risk thresholds (top X% = high risk)
        p99 = np.percentile(xgb_normalized, 99)
        p95 = np.percentile(xgb_normalized, 95)
        p90 = np.percentile(xgb_normalized, 90)
        
        print(f"   Percentiles:  P90={p90:.1f} | P95={p95:.1f} | P99={p99:.1f}")
        
        # Pattern-based score boost (from recalibrate_ml.py)
        PATTERN_BOOST = {
            "SMURFING": 25,
            "LAYERING": 15,
            "FAN_OUT": 15,
            "FAN_IN": 15,
            "STRUCTURING": 20,
            "VELOCITY": 15,
            "PEELING": 20,
        }
        
        # Create results DataFrame
        xgb_df = pl.DataFrame({
            "address": addr_df.index.tolist(),
            "xgb_raw_score": xgb_raw_scores.tolist(),
            "xgb_normalized": xgb_normalized.tolist(),
        })
        
        # Join with sophisticated fraud results
        combined = final.join(xgb_df, on="address", how="left").fill_null(0)
        
        # Apply pattern boosts to XGB score
        def calculate_boost(patterns_str):
            if not patterns_str:
                return 0
            boost = 0
            for pattern, value in PATTERN_BOOST.items():
                if pattern in patterns_str:
                    boost += value
            return min(boost, 100)  # Cap at 100
        
        combined_pd = combined.to_pandas()
        combined_pd['pattern_boost'] = combined_pd['patterns'].apply(calculate_boost)
        
        # Final hybrid score: XGB normalized + Pattern boost + Sophisticated score (normalized)
        max_soph = combined_pd['sophisticated_score'].max()
        combined_pd['soph_normalized'] = (combined_pd['sophisticated_score'] / max_soph) * 100 if max_soph > 0 else 0
        
        # Hybrid score formula: 40% XGB + 30% Pattern boost + 30% Sophisticated
        combined_pd['hybrid_score'] = (
            combined_pd['xgb_normalized'] * 0.4 +
            combined_pd['pattern_boost'] * 0.3 +
            combined_pd['soph_normalized'] * 0.3
        )
        
        # PR-CURVE THRESHOLD OPTIMIZATION
        # Use pattern_count >= 3 as pseudo ground truth
        optimized_thresholds = optimize_thresholds_pr_curve(
            combined_pd['hybrid_score'].values,
            combined_pd['pattern_count'].values,
            verbose=True
        )
        
        # Risk classification based on PR-curve optimized thresholds
        def classify_risk(score, thresholds):
            if score >= thresholds['CRITICAL']:
                return 'CRITICAL'
            elif score >= thresholds['HIGH']:
                return 'HIGH'
            elif score >= thresholds['MEDIUM']:
                return 'MEDIUM'
            elif score >= thresholds['LOW']:
                return 'LOW'
            else:
                return 'MINIMAL'
        
        combined_pd['risk_level'] = combined_pd['hybrid_score'].apply(
            lambda x: classify_risk(x, optimized_thresholds)
        )
        combined_pd = combined_pd.sort_values('hybrid_score', ascending=False)
        
        # Statistics
        risk_dist = combined_pd['risk_level'].value_counts()
        
        print(f"\n[HYBRID SCORING] RESULTS (Optimized Thresholds):")
        print(f"   Thresholds: CRITICAL>={optimized_thresholds['CRITICAL']:.1f} | HIGH>={optimized_thresholds['HIGH']:.1f} | MEDIUM>={optimized_thresholds['MEDIUM']:.1f}")
        print(f"   Addresses analyzed: {len(combined_pd):,}")
        print(f"\n   Risk Distribution:")
        for level in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'MINIMAL']:
            count = risk_dist.get(level, 0)
            pct = count / len(combined_pd) * 100
            print(f"      {level:10}: {count:>6,} ({pct:>5.2f}%)")
        
        # Top threats
        critical = combined_pd[combined_pd['risk_level'] == 'CRITICAL']
        high = combined_pd[combined_pd['risk_level'] == 'HIGH']
        
        print(f"\n   TOP 15 HIGHEST-RISK ADDRESSES:")
        for i, row in combined_pd.head(15).iterrows():
            print(f"     {row['address']}")
            print(f"       Hybrid: {row['hybrid_score']:.1f} | XGB: {row['xgb_normalized']:.1f} | Patterns: {row['patterns']}")
        
        # Multi-signal validation
        multi_signal = combined_pd[
            (combined_pd['xgb_normalized'] > 50) &  # Top 50% of XGB
            (combined_pd['pattern_count'] >= 3)  # 3+ patterns
        ]
        print(f"\n[MULTI-SIGNAL VALIDATION]")
        print(f"   XGB (>50 normalized) AND Multi-pattern (>=3): {len(multi_signal):,}")
        
        # Save results
        combined_path = r"c:\amttp\processed\sophisticated_xgb_combined.csv"
        combined_pd.to_csv(combined_path, index=False)
        print(f"\n[XGB] Combined results saved to: {combined_path}")
        
        # Save high-risk subset
        high_risk = combined_pd[combined_pd['risk_level'].isin(['CRITICAL', 'HIGH'])]
        if len(high_risk) > 0:
            high_risk_path = r"c:\amttp\processed\xgb_high_risk_addresses.csv"
            high_risk.to_csv(high_risk_path, index=False)
            print(f"[XGB] High-risk addresses ({len(high_risk):,}) saved to: {high_risk_path}")
        
    else:
        print("[XGB] Model or schema not found, skipping XGBoost validation")
        
except ImportError:
    print("[XGB] XGBoost not installed, skipping cross-validation")
except Exception as e:
    import traceback
    print(f"[XGB] Error during cross-validation: {e}")
    traceback.print_exc()

print(f"\n{'='*70}")
print(f"TOTAL TIME: {time.perf_counter() - overall_start:.2f} seconds")
print(f"{'='*70}")
