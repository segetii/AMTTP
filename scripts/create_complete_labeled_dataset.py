"""
Create Complete Labeled Dataset for GNN Training
=================================================
1. Load eth_merged_dataset.parquet (1.67M transactions)
2. Aggregate features per address (625K+ addresses)
3. Run hybrid model scoring on ALL addresses
4. Create labeled dataset with fraud column (1=fraud, 0=normal)
5. Export for GNN training
"""
import pandas as pd
import numpy as np
import polars as pl
from pathlib import Path
import pickle
import time
import warnings
warnings.filterwarnings('ignore')

print("=" * 70)
print("CREATE COMPLETE LABELED DATASET FOR GNN TRAINING")
print("=" * 70)

start_time = time.time()

# Paths
ETH_DATA = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
OUTPUT_DIR = r"c:\amttp\processed"

# ============================================================================
# STEP 1: Load all transactions
# ============================================================================
print("\n[1/6] Loading transactions...")
df = pl.read_parquet(ETH_DATA)
print(f"   Loaded {len(df):,} transactions")

# Get unique addresses
all_senders = set(df['from_address'].unique().to_list())
all_receivers = set(df['to_address'].unique().to_list())
all_addresses = list(all_senders.union(all_receivers))
print(f"   Unique addresses: {len(all_addresses):,}")

# ============================================================================
# STEP 2: Compute features for ALL addresses
# ============================================================================
print("\n[2/6] Computing features for ALL addresses...")

# Sender features
print("   Computing sender features...")
sender_stats = df.group_by('from_address').agg([
    pl.len().alias('sent_count'),
    pl.col('value_eth').sum().alias('total_sent'),
    pl.col('value_eth').mean().alias('avg_sent'),
    pl.col('value_eth').max().alias('max_sent'),
    pl.col('value_eth').min().alias('min_sent'),
    pl.col('value_eth').std().alias('std_sent'),
    pl.col('gas_used').sum().alias('total_gas_sent'),
    pl.col('gas_used').mean().alias('avg_gas_used'),
    pl.col('gas_price_gwei').mean().alias('avg_gas_price'),
    pl.col('to_address').n_unique().alias('unique_receivers'),
    pl.col('block_timestamp').min().alias('first_sent_time'),
    pl.col('block_timestamp').max().alias('last_sent_time'),
]).rename({'from_address': 'address'})

# Receiver features
print("   Computing receiver features...")
receiver_stats = df.group_by('to_address').agg([
    pl.len().alias('received_count'),
    pl.col('value_eth').sum().alias('total_received'),
    pl.col('value_eth').mean().alias('avg_received'),
    pl.col('value_eth').max().alias('max_received'),
    pl.col('value_eth').min().alias('min_received'),
    pl.col('value_eth').std().alias('std_received'),
    pl.col('from_address').n_unique().alias('unique_senders'),
    pl.col('block_timestamp').min().alias('first_received_time'),
    pl.col('block_timestamp').max().alias('last_received_time'),
]).rename({'to_address': 'address'})

# Create address DataFrame and join features
print("   Merging features...")
addr_df = pl.DataFrame({'address': all_addresses})
addr_df = addr_df.join(sender_stats, on='address', how='left')
addr_df = addr_df.join(receiver_stats, on='address', how='left')

# Fill nulls with 0
addr_df = addr_df.fill_null(0)

# Convert to pandas for derived features
addr_pd = addr_df.to_pandas()

# Compute derived features
print("   Computing derived features...")
addr_pd['total_transactions'] = addr_pd['sent_count'] + addr_pd['received_count']
addr_pd['balance'] = addr_pd['total_received'] - addr_pd['total_sent']
addr_pd['in_out_ratio'] = addr_pd['received_count'] / (addr_pd['sent_count'] + 1)
addr_pd['unique_counterparties'] = addr_pd['unique_receivers'] + addr_pd['unique_senders']
addr_pd['avg_value'] = (addr_pd['avg_sent'] + addr_pd['avg_received']) / 2

# Time features (handle datetime)
for col in ['first_sent_time', 'last_sent_time', 'first_received_time', 'last_received_time']:
    if addr_pd[col].dtype == 'object' or addr_pd[col].dtype == 'datetime64[ns]':
        addr_pd[col] = pd.to_datetime(addr_pd[col], errors='coerce')

# Active duration in minutes
addr_pd['first_activity'] = addr_pd[['first_sent_time', 'first_received_time']].min(axis=1)
addr_pd['last_activity'] = addr_pd[['last_sent_time', 'last_received_time']].max(axis=1)
addr_pd['active_duration_mins'] = (addr_pd['last_activity'] - addr_pd['first_activity']).dt.total_seconds() / 60
addr_pd['active_duration_mins'] = addr_pd['active_duration_mins'].fillna(0)

print(f"   Computed {len(addr_pd.columns)} features for {len(addr_pd):,} addresses")

# ============================================================================
# STEP 3: Load existing hybrid model results (for flagged addresses)
# ============================================================================
print("\n[3/6] Loading hybrid model results for flagged addresses...")
hybrid_results = pd.read_csv(r"c:\amttp\processed\sophisticated_xgb_combined.csv")
print(f"   Loaded {len(hybrid_results):,} flagged addresses with scores")

# Create mapping from address to hybrid results
hybrid_map = hybrid_results.set_index('address').to_dict('index')

# ============================================================================
# STEP 4: Score ALL addresses
# ============================================================================
print("\n[4/6] Scoring ALL addresses...")

# Initialize scores - include ALL hybrid model features
addr_pd['sophisticated_score'] = 0.0
addr_pd['patterns'] = ''
addr_pd['pattern_count'] = 0
addr_pd['xgb_raw_score'] = 0.0
addr_pd['xgb_normalized'] = 0.0
addr_pd['pattern_boost'] = 0.0
addr_pd['soph_normalized'] = 0.0
addr_pd['hybrid_score'] = 0.0
addr_pd['risk_level'] = 'MINIMAL'

# Apply hybrid results to flagged addresses
flagged_count = 0
for idx, row in addr_pd.iterrows():
    addr = row['address']
    if addr in hybrid_map:
        h = hybrid_map[addr]
        addr_pd.at[idx, 'sophisticated_score'] = h.get('sophisticated_score', 0)
        addr_pd.at[idx, 'patterns'] = h.get('patterns', '')
        addr_pd.at[idx, 'pattern_count'] = h.get('pattern_count', 0)
        addr_pd.at[idx, 'xgb_raw_score'] = h.get('xgb_raw_score', 0)
        addr_pd.at[idx, 'xgb_normalized'] = h.get('xgb_normalized', 0)
        addr_pd.at[idx, 'pattern_boost'] = h.get('pattern_boost', 0)
        addr_pd.at[idx, 'soph_normalized'] = h.get('soph_normalized', 0)
        addr_pd.at[idx, 'hybrid_score'] = h.get('hybrid_score', 0)
        addr_pd.at[idx, 'risk_level'] = h.get('risk_level', 'MINIMAL')
        flagged_count += 1

print(f"   Applied hybrid scores to {flagged_count:,} flagged addresses")

# For unflagged addresses, compute a simple risk score based on features
print("   Computing risk scores for unflagged addresses...")

# Simple heuristic for unflagged: based on transaction patterns
unflagged_mask = addr_pd['hybrid_score'] == 0

# Normalize features for scoring
from sklearn.preprocessing import MinMaxScaler
score_features = ['total_transactions', 'in_out_ratio', 'unique_counterparties', 'total_sent', 'total_received']
scaler = MinMaxScaler()

# Score based on unusual patterns (high activity, high in/out ratio, etc.)
if unflagged_mask.sum() > 0:
    unflagged_data = addr_pd.loc[unflagged_mask, score_features].fillna(0)
    if len(unflagged_data) > 0:
        # Simple scoring: addresses with more activity get higher scores
        # But cap at low values since they weren't flagged by pattern detection
        activity_score = (
            unflagged_data['total_transactions'].clip(upper=100) / 100 * 10 +
            unflagged_data['in_out_ratio'].clip(upper=10) / 10 * 5 +
            unflagged_data['unique_counterparties'].clip(upper=50) / 50 * 5
        )
        addr_pd.loc[unflagged_mask, 'hybrid_score'] = activity_score.clip(upper=30)  # Cap at 30 for unflagged

# ============================================================================
# STEP 5: Create fraud labels
# ============================================================================
print("\n[5/6] Creating fraud labels...")

# Binary label: 1 = fraud (CRITICAL or HIGH), 0 = normal
addr_pd['fraud'] = addr_pd['risk_level'].isin(['CRITICAL', 'HIGH']).astype(int)

# Also create a multi-class label for more granular training
risk_to_class = {'CRITICAL': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1, 'MINIMAL': 0}
addr_pd['risk_class'] = addr_pd['risk_level'].map(risk_to_class).fillna(0).astype(int)

# Statistics
print(f"\n   Label Distribution:")
print(f"      fraud=1 (CRITICAL/HIGH): {addr_pd['fraud'].sum():,} ({addr_pd['fraud'].mean()*100:.3f}%)")
print(f"      fraud=0 (others):        {(addr_pd['fraud'] == 0).sum():,} ({(1-addr_pd['fraud'].mean())*100:.3f}%)")

print(f"\n   Risk Level Distribution:")
for level in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'MINIMAL']:
    count = (addr_pd['risk_level'] == level).sum()
    pct = count / len(addr_pd) * 100
    print(f"      {level:10}: {count:>8,} ({pct:>6.3f}%)")

# ============================================================================
# STEP 6: Save labeled dataset
# ============================================================================
print("\n[6/6] Saving labeled dataset...")

# Select columns to keep
feature_cols = [
    'address',
    # Transaction counts
    'sent_count', 'received_count', 'total_transactions',
    # Value features
    'total_sent', 'total_received', 'balance',
    'avg_sent', 'avg_received', 'avg_value',
    'max_sent', 'max_received',
    'min_sent', 'min_received',
    'std_sent', 'std_received',
    # Gas features
    'total_gas_sent', 'avg_gas_used', 'avg_gas_price',
    # Network features
    'unique_receivers', 'unique_senders', 'unique_counterparties',
    # Ratios
    'in_out_ratio',
    # Time features
    'active_duration_mins',
    # Hybrid Model Scoring Features (ALL from sophisticated_xgb_combined.csv)
    'sophisticated_score', 'patterns', 'pattern_count',
    'xgb_raw_score', 'xgb_normalized',
    'pattern_boost', 'soph_normalized', 'hybrid_score',
    'risk_level',
    # Labels
    'fraud', 'risk_class'
]

# Keep only existing columns
feature_cols = [c for c in feature_cols if c in addr_pd.columns]
labeled_df = addr_pd[feature_cols]

# Save as parquet (efficient for large data)
parquet_path = f"{OUTPUT_DIR}/eth_addresses_labeled.parquet"
labeled_df.to_parquet(parquet_path, index=False)
print(f"   Saved: {parquet_path}")
print(f"   Size: {len(labeled_df):,} addresses × {len(feature_cols)} features")

# Save as CSV for inspection
csv_path = f"{OUTPUT_DIR}/eth_addresses_labeled.csv"
labeled_df.to_csv(csv_path, index=False)
print(f"   Saved: {csv_path}")

# Save feature names
with open(f"{OUTPUT_DIR}/feature_names.pkl", 'wb') as f:
    numeric_features = [c for c in feature_cols if c not in ['address', 'patterns', 'risk_level', 'fraud', 'risk_class']]
    pickle.dump(numeric_features, f)
print(f"   Saved: feature_names.pkl ({len(numeric_features)} numeric features)")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print("LABELED DATASET SUMMARY")
print("=" * 70)

print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     COMPLETE LABELED DATASET CREATED                         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ Total Addresses:    {len(labeled_df):>10,}                                                ║
║ Total Features:     {len(feature_cols):>10}                                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ FRAUD LABELS (Binary):                                                       ║
║   fraud=1 (CRITICAL/HIGH):  {addr_pd['fraud'].sum():>8,} ({addr_pd['fraud'].mean()*100:.3f}%)                        ║
║   fraud=0 (Normal):         {(addr_pd['fraud'] == 0).sum():>8,} ({(1-addr_pd['fraud'].mean())*100:.3f}%)                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ RISK CLASSES (Multi-class):                                                  ║
║   4 = CRITICAL:     {(addr_pd['risk_class'] == 4).sum():>8,}                                                ║
║   3 = HIGH:         {(addr_pd['risk_class'] == 3).sum():>8,}                                                ║
║   2 = MEDIUM:       {(addr_pd['risk_class'] == 2).sum():>8,}                                                ║
║   1 = LOW:          {(addr_pd['risk_class'] == 1).sum():>8,}                                                ║
║   0 = MINIMAL:      {(addr_pd['risk_class'] == 0).sum():>8,}                                                ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ OUTPUT FILES:                                                                ║
║   {parquet_path:<60} ║
║   {csv_path:<60} ║
╚══════════════════════════════════════════════════════════════════════════════╝

READY FOR GNN TRAINING:
- Load: pd.read_parquet('{parquet_path}')
- Features: {len(numeric_features)} numeric columns
- Target: 'fraud' (binary) or 'risk_class' (multi-class)
""")

elapsed = time.time() - start_time
print(f"\nCompleted in {elapsed:.2f} seconds")
print("=" * 70)
