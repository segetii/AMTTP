"""
Generate Labeled Training Dataset for Fraud Detection Model
============================================================
Creates a labeled dataset with fraud=1 (positive) and fraud=0 (normal)
using a multi-signal approach for high-quality pseudo-labels.

Labeling Strategy (Best Approach):
- fraud=1: Addresses with HIGH confidence fraud signals
  - CRITICAL/HIGH risk level AND
  - Multi-pattern (>=2 patterns) OR
  - Both XGB and Pattern agree (multi-signal validation)
  
- fraud=0: Addresses with no fraud signals
  - Not in any flagged list
  - Random sample from normal transactions
"""
import pandas as pd
import numpy as np
import polars as pl
from pathlib import Path
import time

print("=" * 70)
print("GENERATING LABELED TRAINING DATASET")
print("=" * 70)

start_time = time.time()

# Paths
PARQUET_PATH = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
FRAUD_RESULTS = r"c:\amttp\processed\sophisticated_xgb_combined.csv"
OUTPUT_DIR = r"c:\amttp\processed"

# ============================================================================
# STEP 1: Load fraud detection results
# ============================================================================
print("\n[1/5] Loading fraud detection results...")
fraud_df = pd.read_csv(FRAUD_RESULTS)
print(f"   Loaded {len(fraud_df):,} flagged addresses")

# ============================================================================
# STEP 2: Define fraud labels using multi-signal approach
# ============================================================================
print("\n[2/5] Applying fraud labeling strategy...")

# POSITIVE LABELS (fraud=1): High confidence fraud signals
# Criteria: (CRITICAL or HIGH) AND (multi-pattern OR multi-signal validated)
fraud_positive = fraud_df[
    (fraud_df['risk_level'].isin(['CRITICAL', 'HIGH'])) &
    (
        (fraud_df['pattern_count'] >= 2) |  # Multi-pattern
        ((fraud_df['xgb_normalized'] > 51) & (fraud_df['pattern_count'] >= 2))  # Multi-signal
    )
]

print(f"   FRAUD POSITIVE (fraud=1): {len(fraud_positive):,} addresses")
print(f"      - CRITICAL: {len(fraud_positive[fraud_positive['risk_level']=='CRITICAL']):,}")
print(f"      - HIGH: {len(fraud_positive[fraud_positive['risk_level']=='HIGH']):,}")

# Create set of fraud addresses for quick lookup
fraud_addresses = set(fraud_positive['address'].values)

# ============================================================================
# STEP 3: Load full transaction dataset
# ============================================================================
print("\n[3/5] Loading full transaction dataset...")
df = pl.read_parquet(PARQUET_PATH)
print(f"   Loaded {len(df):,} transactions")

# Get unique addresses (both senders and receivers)
all_senders = set(df['from_address'].unique().to_list())
all_receivers = set(df['to_address'].unique().to_list())
all_addresses = all_senders.union(all_receivers)
print(f"   Unique addresses: {len(all_addresses):,}")

# ============================================================================
# STEP 4: Create labeled dataset at TRANSACTION level
# ============================================================================
print("\n[4/5] Creating labeled transaction dataset...")

# Convert to pandas for labeling
df_pd = df.to_pandas()

# Label transactions: fraud=1 if either sender OR receiver is in fraud list
df_pd['sender_fraud'] = df_pd['from_address'].isin(fraud_addresses).astype(int)
df_pd['receiver_fraud'] = df_pd['to_address'].isin(fraud_addresses).astype(int)
df_pd['fraud'] = ((df_pd['sender_fraud'] == 1) | (df_pd['receiver_fraud'] == 1)).astype(int)

# Statistics
fraud_tx = df_pd['fraud'].sum()
normal_tx = len(df_pd) - fraud_tx
print(f"   Fraud transactions (fraud=1): {fraud_tx:,} ({fraud_tx/len(df_pd)*100:.2f}%)")
print(f"   Normal transactions (fraud=0): {normal_tx:,} ({normal_tx/len(df_pd)*100:.2f}%)")

# ============================================================================
# STEP 5: Create balanced training dataset
# ============================================================================
print("\n[5/5] Creating balanced training dataset...")

# Get all fraud transactions
fraud_transactions = df_pd[df_pd['fraud'] == 1]

# Sample normal transactions (same size as fraud for balance, or max 500k)
n_normal_sample = min(len(fraud_transactions) * 2, 500000, normal_tx)
normal_transactions = df_pd[df_pd['fraud'] == 0].sample(n=n_normal_sample, random_state=42)

# Combine
balanced_df = pd.concat([fraud_transactions, normal_transactions], ignore_index=True)
balanced_df = balanced_df.sample(frac=1, random_state=42).reset_index(drop=True)  # Shuffle

print(f"   Balanced dataset: {len(balanced_df):,} transactions")
print(f"      - Fraud (1): {balanced_df['fraud'].sum():,} ({balanced_df['fraud'].mean()*100:.1f}%)")
print(f"      - Normal (0): {len(balanced_df) - balanced_df['fraud'].sum():,}")

# ============================================================================
# SAVE DATASETS
# ============================================================================
print("\n" + "=" * 70)
print("SAVING DATASETS")
print("=" * 70)

# 1. Full labeled dataset (all transactions)
full_path = Path(OUTPUT_DIR) / "eth_transactions_labeled_full.parquet"
df_pd.to_parquet(full_path, index=False)
print(f"\n1. Full labeled dataset: {full_path}")
print(f"   Size: {len(df_pd):,} transactions")

# 2. Balanced training dataset
balanced_path = Path(OUTPUT_DIR) / "eth_transactions_labeled_balanced.parquet"
balanced_df.to_parquet(balanced_path, index=False)
print(f"\n2. Balanced training dataset: {balanced_path}")
print(f"   Size: {len(balanced_df):,} transactions")

# 3. Also save as CSV for easy inspection
balanced_csv_path = Path(OUTPUT_DIR) / "eth_transactions_labeled_balanced.csv"
balanced_df.to_csv(balanced_csv_path, index=False)
print(f"\n3. CSV version: {balanced_csv_path}")

# 4. Fraud addresses list with labels
fraud_addresses_df = fraud_positive[['address', 'risk_level', 'pattern_count', 'patterns', 
                                      'xgb_normalized', 'hybrid_score', 'sophisticated_score']]
fraud_addresses_df['fraud'] = 1
fraud_addresses_path = Path(OUTPUT_DIR) / "fraud_addresses_labeled.csv"
fraud_addresses_df.to_csv(fraud_addresses_path, index=False)
print(f"\n4. Fraud addresses list: {fraud_addresses_path}")
print(f"   Size: {len(fraud_addresses_df):,} addresses")

# ============================================================================
# DATASET SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print("DATASET SUMMARY")
print("=" * 70)

print(f"""
╔═══════════════════════════════════════════════════════════════════╗
║                    LABELED DATASET CREATED                        ║
╠═══════════════════════════════════════════════════════════════════╣
║ LABELING STRATEGY:                                                ║
║   fraud=1: HIGH/CRITICAL risk + multi-pattern (>=2)              ║
║   fraud=0: Not in any fraud list                                 ║
╠═══════════════════════════════════════════════════════════════════╣
║ FULL DATASET:                                                     ║
║   Total transactions: {len(df_pd):>10,}                              ║
║   Fraud (1):          {fraud_tx:>10,} ({fraud_tx/len(df_pd)*100:>5.2f}%)                  ║
║   Normal (0):         {normal_tx:>10,} ({normal_tx/len(df_pd)*100:>5.2f}%)                  ║
╠═══════════════════════════════════════════════════════════════════╣
║ BALANCED DATASET (for training):                                  ║
║   Total transactions: {len(balanced_df):>10,}                              ║
║   Fraud (1):          {balanced_df['fraud'].sum():>10,} ({balanced_df['fraud'].mean()*100:>5.1f}%)                   ║
║   Normal (0):         {len(balanced_df) - balanced_df['fraud'].sum():>10,}                              ║
╠═══════════════════════════════════════════════════════════════════╣
║ FRAUD ADDRESSES:      {len(fraud_addresses_df):>10,}                              ║
╚═══════════════════════════════════════════════════════════════════╝

COLUMNS IN LABELED DATASET:
""")

print("  Transaction features:")
for col in balanced_df.columns[:15]:
    print(f"    - {col}")
if len(balanced_df.columns) > 15:
    print(f"    ... and {len(balanced_df.columns) - 15} more columns")

print(f"\n  Label columns:")
print(f"    - fraud (1=fraud, 0=normal)")
print(f"    - sender_fraud (1 if sender is fraud address)")
print(f"    - receiver_fraud (1 if receiver is fraud address)")

elapsed = time.time() - start_time
print(f"\n{'='*70}")
print(f"Completed in {elapsed:.2f} seconds")
print(f"{'='*70}")
