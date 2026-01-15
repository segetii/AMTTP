"""
Create flagged dataset with flag column (1=positive/fraud, 0=normal)
Based on multi-signal detection results
"""
import pandas as pd

print("=" * 70)
print("CREATING FLAGGED DATASET")
print("=" * 70)

# Load original dataset
original = pd.read_parquet('C:/Users/Administrator/Downloads/eth_last_7_days.parquet')
print(f"\nOriginal dataset: {len(original)} transactions")
print(f"Columns: {original.columns.tolist()}")

# Load our scored results
cv = pd.read_csv('c:/amttp/processed/cross_validated_results.csv')
soph = pd.read_csv('c:/amttp/processed/sophisticated_fraud_patterns.csv')
hybrid = pd.read_csv('c:/amttp/processed/hybrid_risk_scores.csv')

# Get pattern addresses
pattern_addrs = set(soph['address'].str.lower())

# Identify flagged addresses using multi-signal detection
# (ML >= 0.55 AND at least 2 signals)
flagged_addrs = set()
escrow_addrs = set()

for _, row in cv.iterrows():
    addr = row['address'].lower()
    ml_score = row['ml_max_score']
    graph_score = row['risk_score']
    
    ml_signal = ml_score >= 0.55
    graph_signal = graph_score > 0
    pattern_signal = addr in pattern_addrs
    
    signal_count = sum([ml_signal, graph_signal, pattern_signal])
    
    if ml_score >= 0.55 and signal_count >= 2:
        flagged_addrs.add(addr)
        if ml_score >= 0.75:
            escrow_addrs.add(addr)

print(f"\nFlagged addresses (multi-signal): {len(flagged_addrs)}")
print(f"Escrow addresses (highest risk): {len(escrow_addrs)}")

# Add flag column to transactions
# Flag = 1 if either from_address OR to_address is flagged
original['from_lower'] = original['from_address'].str.lower()
original['to_lower'] = original['to_address'].str.lower()

original['flag'] = original.apply(
    lambda x: 1 if x['from_lower'] in flagged_addrs or x['to_lower'] in flagged_addrs else 0,
    axis=1
)

# Also add detailed columns for analysis
original['from_flagged'] = original['from_lower'].isin(flagged_addrs).astype(int)
original['to_flagged'] = original['to_lower'].isin(flagged_addrs).astype(int)
original['escrow_involved'] = original.apply(
    lambda x: 1 if x['from_lower'] in escrow_addrs or x['to_lower'] in escrow_addrs else 0,
    axis=1
)

# Drop temp columns
original = original.drop(columns=['from_lower', 'to_lower'])

# Summary
flagged_count = original['flag'].sum()
normal_count = len(original) - flagged_count

print(f"\n" + "=" * 70)
print("DATASET SUMMARY")
print("=" * 70)
print(f"  Total transactions:     {len(original):,}")
print(f"  Flagged (flag=1):       {flagged_count:,} ({flagged_count/len(original)*100:.2f}%)")
print(f"  Normal (flag=0):        {normal_count:,} ({normal_count/len(original)*100:.2f}%)")
print(f"  Escrow involved:        {original['escrow_involved'].sum():,}")

# Save as CSV
output_csv = 'C:/Users/Administrator/Downloads/eth_last_7_days_flagged.csv'
original.to_csv(output_csv, index=False)
print(f"\n✅ Saved CSV to: {output_csv}")

# Also save as Parquet (more efficient)
output_parquet = 'C:/Users/Administrator/Downloads/eth_last_7_days_flagged.parquet'
original.to_parquet(output_parquet, index=False)
print(f"✅ Saved Parquet to: {output_parquet}")

# Show sample of flagged transactions
print(f"\n" + "=" * 70)
print("SAMPLE FLAGGED TRANSACTIONS")
print("=" * 70)
flagged_sample = original[original['flag'] == 1].head(10)
for _, row in flagged_sample.iterrows():
    print(f"  {row['from_address'][:20]}... -> {row['to_address'][:20]}...")
    print(f"    Value: {row['value']:.4f} ETH | Block: {row['block_number']}")

# Column info
print(f"\n" + "=" * 70)
print("NEW COLUMNS ADDED")
print("=" * 70)
print("""
  flag:           1 = fraud/suspicious, 0 = normal
  from_flagged:   1 = sender is flagged address
  to_flagged:     1 = receiver is flagged address  
  escrow_involved: 1 = highest risk (escrow recommended)
""")
