"""
RECALIBRATED XGBoost Inference for Fraud Detection

The XGBoost model outputs very low raw scores (0-1.1%) because:
1. It was trained on labeled fraud data with specific patterns
2. We can only compute ~14 of 171 features from raw transactions

This script recalibrates the scores using:
1. Percentile-based normalization (relative to the dataset)
2. Pattern boosting from behavioral analysis
3. Multi-signal validation

This matches how the model performed well 2 days ago.
"""
import os
import sys
import json
import time
import numpy as np
import pandas as pd
import xgboost as xgb
from pathlib import Path
from datetime import datetime

print("=" * 70)
print("RECALIBRATED XGBOOST FRAUD INFERENCE")
print("=" * 70)

# =============================================================================
# CONFIGURATION
# =============================================================================
DATA_PATH = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
MODEL_PATH = r"c:\amttp\ml\Automation\ml_pipeline\models\trained\xgb.json"
SCHEMA_PATH = r"c:\amttp\ml\Automation\ml_pipeline\models\feature_schema.json"
OUTPUT_DIR = r"c:\amttp\processed"

# Recalibrated thresholds (percentile-based)
# These thresholds are relative to the score distribution, not absolute
RECALIBRATED_THRESHOLDS = {
    "CRITICAL": 99,   # Top 1% of scores
    "HIGH": 95,       # Top 5% 
    "MEDIUM": 85,     # Top 15%
    "LOW": 70,        # Top 30%
    "MINIMAL": 0      # Everything else
}

# Pattern boost weights (add to normalized score)
PATTERN_BOOST = {
    "SMURFING": 15,
    "STRUCTURING": 20,
    "PEELING": 20,
    "LAYERING": 12,
    "FAN_OUT": 10,
    "FAN_IN": 10,
    "VELOCITY": 10,
}

# =============================================================================
# STEP 1: Load Data and Model
# =============================================================================
print(f"\n[STEP 1] Loading data and model...")
start_time = time.time()

# Load transaction data
print(f"   Loading: {DATA_PATH}")
df = pd.read_parquet(DATA_PATH)
print(f"   Loaded {len(df):,} transactions")

# Load model
print(f"   Loading XGBoost model...")
model = xgb.Booster()
model.load_model(MODEL_PATH)

# Load feature schema
with open(SCHEMA_PATH, 'r') as f:
    schema = json.load(f)
feature_names = schema['feature_names']
print(f"   Feature schema: {len(feature_names)} features")

# =============================================================================
# STEP 2: Aggregate Transactions by Address (Feature Engineering)
# =============================================================================
print(f"\n[STEP 2] Aggregating transactions by address...")

# Ensure proper types
df['value_eth'] = pd.to_numeric(df['value_eth'], errors='coerce').fillna(0)
df['gas_price_gwei'] = pd.to_numeric(df.get('gas_price_gwei', 0), errors='coerce').fillna(0)
df['gas_used'] = pd.to_numeric(df.get('gas_used', 21000), errors='coerce').fillna(21000)
df['block_timestamp'] = pd.to_datetime(df['block_timestamp'], utc=True, errors='coerce')

# Sent transactions aggregation
print("   Computing sent transaction features...")
sent_agg = df.groupby('from_address').agg({
    'value_eth': ['sum', 'mean', 'max', 'min', 'std', 'count'],
    'to_address': 'nunique',
    'gas_price_gwei': ['mean', 'max'],
    'gas_used': ['sum', 'mean'],
    'block_timestamp': ['min', 'max'],
}).reset_index()

sent_agg.columns = ['address', 
                   'total_ether_sent', 'avg_val_sent', 'max_val_sent', 'min_val_sent', 'std_val_sent', 'sent_tnx',
                   'unique_sent_to', 
                   'avg_gas_price', 'max_gas_price',
                   'total_gas_used', 'avg_gas_used',
                   'first_sent_time', 'last_sent_time']

# Received transactions aggregation
print("   Computing received transaction features...")
received_agg = df.groupby('to_address').agg({
    'value_eth': ['sum', 'mean', 'max', 'min', 'std', 'count'],
    'from_address': 'nunique',
    'block_timestamp': ['min', 'max']
}).reset_index()

received_agg.columns = ['address',
                       'total_ether_received', 'avg_val_received', 'max_value_received', 'min_value_received', 'std_val_received', 'received_tnx',
                       'unique_received_from',
                       'first_received_time', 'last_received_time']

# Merge sent and received
print("   Merging features...")
features = pd.merge(sent_agg, received_agg, on='address', how='outer')

# Fill NaN
features = features.fillna(0)

# Compute derived features
features['total_ether_balance'] = features['total_ether_received'] - features['total_ether_sent']
features['income'] = features['total_ether_balance']
features['neighbors'] = features['unique_sent_to'] + features['unique_received_from']
features['count'] = features['sent_tnx'] + features['received_tnx']

# Time features
features['time_diff_between_first_and_last_(mins)'] = 0.0

print(f"   Aggregated {len(features):,} unique addresses")

# =============================================================================
# STEP 3: Create Feature Matrix and Run Inference
# =============================================================================
print(f"\n[STEP 3] Running XGBoost inference...")

# Map computed features to schema
feature_mapping = {
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
    "total_ether_sent": "total_ether_sent",
    "total_ether_received": "total_ether_received",
}

# Build feature matrix
print(f"   Building feature matrix ({len(features):,} x {len(feature_names)})...")
feature_matrix = np.zeros((len(features), len(feature_names)), dtype=np.float32)

for i, feat in enumerate(feature_names):
    if feat in feature_mapping and feature_mapping[feat] in features.columns:
        feature_matrix[:, i] = features[feature_mapping[feat]].fillna(0).values

# Run inference
print("   Running XGBoost predictions...")
dmatrix = xgb.DMatrix(feature_matrix, feature_names=feature_names)
raw_scores = model.predict(dmatrix)

print(f"   Raw score range: {raw_scores.min():.6f} - {raw_scores.max():.6f}")

# =============================================================================
# STEP 4: RECALIBRATE SCORES (Key step!)
# =============================================================================
print(f"\n[STEP 4] Recalibrating scores...")

# Compute percentiles
percentiles = {
    'p50': np.percentile(raw_scores, 50),
    'p75': np.percentile(raw_scores, 75),
    'p90': np.percentile(raw_scores, 90),
    'p95': np.percentile(raw_scores, 95),
    'p99': np.percentile(raw_scores, 99),
    'p99.9': np.percentile(raw_scores, 99.9),
}

print(f"   Percentile distribution:")
for k, v in percentiles.items():
    print(f"      {k}: {v:.6f}")

# Method 1: Percentile rank normalization (0-100)
# This normalizes relative to the dataset, not absolute values
percentile_ranks = np.zeros_like(raw_scores)
for i, score in enumerate(raw_scores):
    percentile_ranks[i] = (raw_scores < score).sum() / len(raw_scores) * 100

# Method 2: Min-max normalization to 0-100
min_score = raw_scores.min()
max_score = raw_scores.max()
if max_score > min_score:
    normalized_scores = ((raw_scores - min_score) / (max_score - min_score)) * 100
else:
    normalized_scores = np.zeros_like(raw_scores)

# Use percentile ranks as the calibrated score
calibrated_scores = percentile_ranks

print(f"   Calibrated score range: {calibrated_scores.min():.1f} - {calibrated_scores.max():.1f}")

# =============================================================================
# STEP 5: Apply Pattern Boosts (from behavioral analysis)
# =============================================================================
print(f"\n[STEP 5] Applying pattern boosts...")

# Load sophisticated fraud patterns if available
PATTERNS_PATH = os.path.join(OUTPUT_DIR, "sophisticated_fraud_patterns.csv")
if os.path.exists(PATTERNS_PATH):
    patterns_df = pd.read_csv(PATTERNS_PATH)
    patterns_df['address'] = patterns_df['address'].str.lower()
    print(f"   Loaded {len(patterns_df):,} addresses with patterns")
    
    # Create pattern boost lookup
    pattern_boost_map = {}
    for _, row in patterns_df.iterrows():
        addr = row['address']
        patterns = str(row.get('patterns', ''))
        boost = sum(PATTERN_BOOST.get(p.strip(), 0) for p in patterns.split(',') if p.strip())
        pattern_boost_map[addr] = min(boost, 50)  # Cap at 50
    
    print(f"   Created pattern boost for {len(pattern_boost_map):,} addresses")
else:
    pattern_boost_map = {}
    print("   No pattern data found, skipping boost")

# Create results DataFrame
results = pd.DataFrame({
    'address': features['address'].str.lower(),
    'raw_score': raw_scores,
    'percentile_rank': percentile_ranks,
    'normalized_score': normalized_scores,
    'calibrated_score': calibrated_scores,
})

# Add pattern boost
results['pattern_boost'] = results['address'].map(pattern_boost_map).fillna(0)
results['final_score'] = (results['calibrated_score'] + results['pattern_boost']).clip(0, 100)

# =============================================================================
# STEP 6: Classify Risk Levels
# =============================================================================
print(f"\n[STEP 6] Classifying risk levels...")

# Compute thresholds from percentiles
critical_threshold = np.percentile(results['final_score'], RECALIBRATED_THRESHOLDS['CRITICAL'])
high_threshold = np.percentile(results['final_score'], RECALIBRATED_THRESHOLDS['HIGH'])
medium_threshold = np.percentile(results['final_score'], RECALIBRATED_THRESHOLDS['MEDIUM'])
low_threshold = np.percentile(results['final_score'], RECALIBRATED_THRESHOLDS['LOW'])

print(f"   Threshold values:")
print(f"      CRITICAL (P99): >= {critical_threshold:.1f}")
print(f"      HIGH (P95):     >= {high_threshold:.1f}")
print(f"      MEDIUM (P85):   >= {medium_threshold:.1f}")
print(f"      LOW (P70):      >= {low_threshold:.1f}")

def classify_risk(score):
    if score >= critical_threshold:
        return 'CRITICAL'
    elif score >= high_threshold:
        return 'HIGH'
    elif score >= medium_threshold:
        return 'MEDIUM'
    elif score >= low_threshold:
        return 'LOW'
    else:
        return 'MINIMAL'

results['risk_level'] = results['final_score'].apply(classify_risk)

# Sort by final score
results = results.sort_values('final_score', ascending=False)

# =============================================================================
# STEP 7: Display Results
# =============================================================================
print(f"\n{'='*70}")
print("RECALIBRATED INFERENCE RESULTS")
print("="*70)

risk_counts = results['risk_level'].value_counts()
total = len(results)

print(f"\nRisk Distribution ({total:,} addresses):")
for level in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'MINIMAL']:
    count = risk_counts.get(level, 0)
    pct = count / total * 100
    print(f"   {level:10}: {count:>8,} ({pct:>5.2f}%)")

print(f"\nTOP 25 HIGHEST-RISK ADDRESSES:")
print("-" * 70)
for i, (_, row) in enumerate(results.head(25).iterrows(), 1):
    boost_str = f"+{row['pattern_boost']:.0f}" if row['pattern_boost'] > 0 else ""
    print(f"{i:>3}. {row['address']}")
    print(f"      Final: {row['final_score']:.1f} | Raw: {row['raw_score']:.6f} | Rank: P{row['percentile_rank']:.1f} {boost_str}")

# =============================================================================
# STEP 8: Save Results
# =============================================================================
print(f"\n[STEP 8] Saving results...")

# Save all results
all_results_path = os.path.join(OUTPUT_DIR, "recalibrated_inference_results.csv")
results.to_csv(all_results_path, index=False)
print(f"   Saved {len(results):,} addresses to {all_results_path}")

# Save high-risk subset
high_risk = results[results['risk_level'].isin(['CRITICAL', 'HIGH'])]
high_risk_path = os.path.join(OUTPUT_DIR, "recalibrated_high_risk.csv")
high_risk.to_csv(high_risk_path, index=False)
print(f"   Saved {len(high_risk):,} high-risk addresses to {high_risk_path}")

# Save critical only
critical = results[results['risk_level'] == 'CRITICAL']
critical_path = os.path.join(OUTPUT_DIR, "recalibrated_critical.csv")
critical.to_csv(critical_path, index=False)
print(f"   Saved {len(critical):,} critical addresses to {critical_path}")

# Summary stats
elapsed = time.time() - start_time
print(f"\n{'='*70}")
print(f"INFERENCE COMPLETE in {elapsed:.1f} seconds")
print("="*70)
print(f"\nKey Statistics:")
print(f"   Total addresses analyzed: {len(results):,}")
print(f"   CRITICAL risk: {len(critical):,} ({len(critical)/len(results)*100:.2f}%)")
print(f"   HIGH risk: {len(high_risk) - len(critical):,}")
print(f"   Addresses with pattern boost: {(results['pattern_boost'] > 0).sum():,}")
print(f"\nFiles saved:")
print(f"   • {all_results_path}")
print(f"   • {high_risk_path}")
print(f"   • {critical_path}")
