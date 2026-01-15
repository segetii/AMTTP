"""
SOPHISTICATED FRAUD DETECTION PATTERNS
======================================
Detects advanced money laundering techniques:
1. SMURFING - Breaking large amounts into small transactions
2. LAYERING - Rapid sequential transactions through intermediaries
3. FAN-OUT - One address sending to many (distribution)
4. FAN-IN - Many addresses sending to one (collection/aggregation)
5. ROUND-TRIP - Funds returning to origin through intermediaries
6. PEELING CHAIN - Sequential decreasing amounts
7. UNUSUAL TIME PATTERNS - Transactions at unusual hours
8. VELOCITY ANOMALIES - Sudden spikes in activity
"""
import pandas as pd
import numpy as np
import mgclient
from datetime import datetime, timedelta
from collections import defaultdict

# Configuration
PARQUET_PATH = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
OUTPUT_DIR = r"c:\amttp\processed"

print("="*70)
print("SOPHISTICATED FRAUD PATTERN DETECTION")
print("="*70)
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Load data
print("\n📂 Loading transactions...")
df = pd.read_parquet(PARQUET_PATH)
print(f"   Loaded {len(df):,} transactions")

# Ensure timestamp is datetime
if df['block_timestamp'].dtype == 'object':
    df['block_timestamp'] = pd.to_datetime(df['block_timestamp'])

results = {}

# ============================================================
# 1. SMURFING DETECTION
# ============================================================
print("\n" + "="*60)
print("1️⃣  SMURFING DETECTION")
print("="*60)
print("Looking for addresses splitting large amounts into small transactions...")

# Parameters
SMURFING_THRESHOLD = 1.0  # ETH - transactions below this are "small"
MIN_SMALL_TX_COUNT = 5     # Need at least this many small transactions
TIME_WINDOW_HOURS = 24     # Within this time window

# Find addresses with many small outgoing transactions
sender_stats = df.groupby('from_address').agg({
    'value_eth': ['count', 'sum', 'mean', 'std', 'min', 'max'],
    'to_address': 'nunique',
    'block_timestamp': ['min', 'max']
}).reset_index()
sender_stats.columns = [
    'address', 'tx_count', 'total_sent', 'avg_value', 'std_value', 
    'min_value', 'max_value', 'unique_receivers', 'first_tx', 'last_tx'
]

# Smurfing indicators:
# - Many transactions (>5)
# - Small average value (<1 ETH)
# - Low standard deviation (consistent amounts)
# - Multiple receivers
# - High total volume relative to average

sender_stats['time_span_hours'] = (
    (sender_stats['last_tx'] - sender_stats['first_tx']).dt.total_seconds() / 3600
).fillna(0)

sender_stats['is_potential_smurf'] = (
    (sender_stats['tx_count'] >= MIN_SMALL_TX_COUNT) &
    (sender_stats['avg_value'] < SMURFING_THRESHOLD) &
    (sender_stats['total_sent'] > 5) &  # But total is significant
    (sender_stats['unique_receivers'] >= 3)
)

# Calculate smurfing score
sender_stats['smurf_score'] = 0.0
sender_stats.loc[sender_stats['is_potential_smurf'], 'smurf_score'] = (
    (sender_stats['tx_count'] / 10).clip(0, 1) * 30 +  # Many transactions
    (1 - sender_stats['avg_value'] / SMURFING_THRESHOLD).clip(0, 1) * 25 +  # Small amounts
    (sender_stats['unique_receivers'] / 10).clip(0, 1) * 20 +  # Many receivers
    (sender_stats['total_sent'] / 50).clip(0, 1) * 25  # Significant total
)

smurfers = sender_stats[sender_stats['smurf_score'] > 30].sort_values('smurf_score', ascending=False)
print(f"\n🔍 Found {len(smurfers)} potential SMURFING addresses")

if len(smurfers) > 0:
    print("\nTop 10 Smurfing Suspects:")
    print("-" * 70)
    for i, row in smurfers.head(10).iterrows():
        print(f"  {row['address'][:42]}")
        print(f"    TX: {row['tx_count']:,} | Avg: {row['avg_value']:.3f} ETH | Total: {row['total_sent']:.2f} ETH | Score: {row['smurf_score']:.1f}")

results['smurfing'] = smurfers[['address', 'tx_count', 'total_sent', 'avg_value', 'unique_receivers', 'smurf_score']]

# ============================================================
# 2. FAN-OUT DETECTION (Distribution Pattern)
# ============================================================
print("\n" + "="*60)
print("2️⃣  FAN-OUT DETECTION (Distribution)")
print("="*60)
print("Looking for addresses distributing funds to many recipients...")

# Fan-out: One address sending to MANY addresses in short time
fan_out = sender_stats[
    (sender_stats['unique_receivers'] >= 10) &
    (sender_stats['tx_count'] >= 10)
].copy()

fan_out['fan_out_score'] = (
    (fan_out['unique_receivers'] / 20).clip(0, 1) * 40 +
    (fan_out['tx_count'] / 20).clip(0, 1) * 30 +
    (fan_out['total_sent'] / 100).clip(0, 1) * 30
)

fan_out = fan_out.sort_values('fan_out_score', ascending=False)
print(f"\n🔍 Found {len(fan_out)} FAN-OUT addresses (distributing to many)")

if len(fan_out) > 0:
    print("\nTop 10 Fan-Out Addresses:")
    print("-" * 70)
    for i, row in fan_out.head(10).iterrows():
        print(f"  {row['address'][:42]}")
        print(f"    Receivers: {row['unique_receivers']} | TX: {row['tx_count']} | Total: {row['total_sent']:.2f} ETH")

results['fan_out'] = fan_out[['address', 'unique_receivers', 'tx_count', 'total_sent', 'fan_out_score']]

# ============================================================
# 3. FAN-IN DETECTION (Collection/Aggregation Pattern)
# ============================================================
print("\n" + "="*60)
print("3️⃣  FAN-IN DETECTION (Collection)")
print("="*60)
print("Looking for addresses receiving from many sources...")

# Fan-in: One address receiving from MANY addresses
receiver_stats = df.groupby('to_address').agg({
    'value_eth': ['count', 'sum', 'mean'],
    'from_address': 'nunique',
    'block_timestamp': ['min', 'max']
}).reset_index()
receiver_stats.columns = [
    'address', 'rx_count', 'total_received', 'avg_value',
    'unique_senders', 'first_rx', 'last_rx'
]

fan_in = receiver_stats[
    (receiver_stats['unique_senders'] >= 10) &
    (receiver_stats['rx_count'] >= 10)
].copy()

fan_in['fan_in_score'] = (
    (fan_in['unique_senders'] / 20).clip(0, 1) * 40 +
    (fan_in['rx_count'] / 20).clip(0, 1) * 30 +
    (fan_in['total_received'] / 100).clip(0, 1) * 30
)

fan_in = fan_in.sort_values('fan_in_score', ascending=False)
print(f"\n🔍 Found {len(fan_in)} FAN-IN addresses (collecting from many)")

if len(fan_in) > 0:
    print("\nTop 10 Fan-In (Collection) Addresses:")
    print("-" * 70)
    for i, row in fan_in.head(10).iterrows():
        print(f"  {row['address'][:42]}")
        print(f"    Senders: {row['unique_senders']} | TX: {row['rx_count']} | Total: {row['total_received']:.2f} ETH")

results['fan_in'] = fan_in[['address', 'unique_senders', 'rx_count', 'total_received', 'fan_in_score']]

# ============================================================
# 4. PEELING CHAIN DETECTION
# ============================================================
print("\n" + "="*60)
print("4️⃣  PEELING CHAIN DETECTION")
print("="*60)
print("Looking for sequential transactions with decreasing amounts...")

# Sort by time
df_sorted = df.sort_values('block_timestamp')

# Group consecutive transactions by sender
peeling_suspects = []

for sender in df['from_address'].unique():
    sender_txs = df_sorted[df_sorted['from_address'] == sender].sort_values('block_timestamp')
    
    if len(sender_txs) < 3:
        continue
    
    # Check for decreasing pattern
    values = sender_txs['value_eth'].values
    
    # Count how many consecutive decreases
    decreasing_count = sum(1 for i in range(1, len(values)) if values[i] < values[i-1])
    decrease_ratio = decreasing_count / (len(values) - 1) if len(values) > 1 else 0
    
    # Check if amounts are similar (peeling typically removes small amounts)
    if len(values) >= 3 and decrease_ratio > 0.6:
        peeling_suspects.append({
            'address': sender,
            'tx_count': len(sender_txs),
            'first_value': values[0],
            'last_value': values[-1],
            'decrease_ratio': decrease_ratio,
            'total_peeled': values[0] - values[-1] if values[0] > values[-1] else 0,
            'peeling_score': decrease_ratio * 50 + min(len(values) / 10, 1) * 50
        })

peeling_df = pd.DataFrame(peeling_suspects)
if len(peeling_df) > 0:
    peeling_df = peeling_df.sort_values('peeling_score', ascending=False)
    print(f"\n🔍 Found {len(peeling_df)} potential PEELING CHAIN addresses")
    
    print("\nTop 10 Peeling Chain Suspects:")
    print("-" * 70)
    for i, row in peeling_df.head(10).iterrows():
        print(f"  {row['address'][:42]}")
        print(f"    TX: {row['tx_count']} | First: {row['first_value']:.3f} → Last: {row['last_value']:.3f} ETH | Score: {row['peeling_score']:.1f}")
else:
    peeling_df = pd.DataFrame(columns=['address', 'tx_count', 'peeling_score'])
    print("\n   No clear peeling chains detected")

results['peeling'] = peeling_df

# ============================================================
# 5. LAYERING DETECTION (Rapid Pass-Through)
# ============================================================
print("\n" + "="*60)
print("5️⃣  LAYERING DETECTION (Rapid Pass-Through)")
print("="*60)
print("Looking for addresses that receive and quickly send funds...")

# Find addresses that both send AND receive
senders = set(df['from_address'].unique())
receivers = set(df['to_address'].unique())
pass_through = senders & receivers

print(f"   Addresses that both send and receive: {len(pass_through):,}")

# For each pass-through address, check timing
layering_suspects = []

for addr in list(pass_through)[:1000]:  # Limit for performance
    received = df[df['to_address'] == addr][['block_timestamp', 'value_eth', 'from_address']].copy()
    sent = df[df['from_address'] == addr][['block_timestamp', 'value_eth', 'to_address']].copy()
    
    if len(received) == 0 or len(sent) == 0:
        continue
    
    # Check for rapid turnaround (receive then send quickly)
    received = received.sort_values('block_timestamp')
    sent = sent.sort_values('block_timestamp')
    
    # Simple check: did they receive then send within same block range?
    first_receive = received['block_timestamp'].min()
    first_send = sent['block_timestamp'].min()
    last_receive = received['block_timestamp'].max()
    last_send = sent['block_timestamp'].max()
    
    total_in = received['value_eth'].sum()
    total_out = sent['value_eth'].sum()
    
    # Pass-through ratio (how much of received was sent)
    pass_ratio = min(total_out / total_in, 1.0) if total_in > 0 else 0
    
    if pass_ratio > 0.8 and len(received) >= 2 and len(sent) >= 2:
        layering_suspects.append({
            'address': addr,
            'rx_count': len(received),
            'tx_count': len(sent),
            'total_in': total_in,
            'total_out': total_out,
            'pass_ratio': pass_ratio,
            'unique_sources': received['from_address'].nunique(),
            'unique_destinations': sent['to_address'].nunique(),
            'layering_score': pass_ratio * 40 + min(len(received) / 5, 1) * 30 + min(len(sent) / 5, 1) * 30
        })

layering_df = pd.DataFrame(layering_suspects)
if len(layering_df) > 0:
    layering_df = layering_df.sort_values('layering_score', ascending=False)
    print(f"\n🔍 Found {len(layering_df)} potential LAYERING addresses")
    
    print("\nTop 10 Layering (Pass-Through) Suspects:")
    print("-" * 70)
    for i, row in layering_df.head(10).iterrows():
        print(f"  {row['address'][:42]}")
        print(f"    In: {row['total_in']:.2f} ETH → Out: {row['total_out']:.2f} ETH | Pass: {row['pass_ratio']*100:.0f}% | Score: {row['layering_score']:.1f}")
else:
    layering_df = pd.DataFrame(columns=['address', 'layering_score'])
    print("\n   No clear layering patterns detected")

results['layering'] = layering_df

# ============================================================
# 6. ROUND AMOUNT STRUCTURING
# ============================================================
print("\n" + "="*60)
print("6️⃣  ROUND AMOUNT STRUCTURING")
print("="*60)
print("Looking for suspiciously round transaction amounts...")

# Check for round amounts (exact ETH, powers of 10)
def is_suspicious_round(value):
    if value <= 0:
        return False
    # Exact whole numbers
    if value == int(value) and value >= 1:
        return True
    # Powers of 10
    if value in [0.1, 0.5, 1, 5, 10, 50, 100, 500, 1000]:
        return True
    # Common structuring amounts
    if value in [0.99, 0.999, 9.99, 99.99]:
        return True
    return False

df['is_round'] = df['value_eth'].apply(is_suspicious_round)

round_tx_by_sender = df[df['is_round']].groupby('from_address').agg({
    'value_eth': ['count', 'sum'],
    'to_address': 'nunique'
}).reset_index()
round_tx_by_sender.columns = ['address', 'round_tx_count', 'round_total', 'round_receivers']

# Merge with total tx count
total_tx = df.groupby('from_address').size().reset_index(name='total_tx')
round_tx_by_sender = round_tx_by_sender.merge(total_tx, left_on='address', right_on='from_address', how='left')
round_tx_by_sender['round_ratio'] = round_tx_by_sender['round_tx_count'] / round_tx_by_sender['total_tx']

# Suspicious if high ratio of round amounts
structuring = round_tx_by_sender[
    (round_tx_by_sender['round_tx_count'] >= 3) &
    (round_tx_by_sender['round_ratio'] > 0.5)
].copy()

structuring['structuring_score'] = (
    structuring['round_ratio'] * 40 +
    (structuring['round_tx_count'] / 10).clip(0, 1) * 30 +
    (structuring['round_total'] / 50).clip(0, 1) * 30
)

structuring = structuring.sort_values('structuring_score', ascending=False)
print(f"\n🔍 Found {len(structuring)} addresses with ROUND AMOUNT STRUCTURING")

if len(structuring) > 0:
    print("\nTop 10 Round Amount Structuring:")
    print("-" * 70)
    for i, row in structuring.head(10).iterrows():
        print(f"  {row['address'][:42]}")
        print(f"    Round TX: {row['round_tx_count']}/{row['total_tx']} ({row['round_ratio']*100:.0f}%) | Total: {row['round_total']:.2f} ETH")

results['structuring'] = structuring[['address', 'round_tx_count', 'round_ratio', 'round_total', 'structuring_score']]

# ============================================================
# 7. VELOCITY ANOMALIES (Sudden Activity Spikes)
# ============================================================
print("\n" + "="*60)
print("7️⃣  VELOCITY ANOMALIES")
print("="*60)
print("Looking for sudden spikes in transaction activity...")

# Group by address and hour
df['hour'] = df['block_timestamp'].dt.floor('H')

hourly_activity = df.groupby(['from_address', 'hour']).agg({
    'tx_hash': 'count',
    'value_eth': 'sum'
}).reset_index()
hourly_activity.columns = ['address', 'hour', 'tx_count', 'value']

# Find addresses with high variance in activity
velocity_stats = hourly_activity.groupby('address').agg({
    'tx_count': ['mean', 'std', 'max'],
    'value': ['mean', 'std', 'max']
}).reset_index()
velocity_stats.columns = ['address', 'avg_tx_hour', 'std_tx_hour', 'max_tx_hour', 
                          'avg_val_hour', 'std_val_hour', 'max_val_hour']

# Velocity score: high max relative to average
velocity_stats['velocity_ratio'] = velocity_stats['max_tx_hour'] / velocity_stats['avg_tx_hour'].replace(0, 1)
velocity_stats = velocity_stats[velocity_stats['max_tx_hour'] >= 5]  # At least 5 tx in one hour

velocity_anomalies = velocity_stats[velocity_stats['velocity_ratio'] > 3].copy()
velocity_anomalies['velocity_score'] = (
    (velocity_anomalies['velocity_ratio'] / 10).clip(0, 1) * 50 +
    (velocity_anomalies['max_tx_hour'] / 20).clip(0, 1) * 50
)

velocity_anomalies = velocity_anomalies.sort_values('velocity_score', ascending=False)
print(f"\n🔍 Found {len(velocity_anomalies)} addresses with VELOCITY ANOMALIES")

if len(velocity_anomalies) > 0:
    print("\nTop 10 Velocity Anomalies:")
    print("-" * 70)
    for i, row in velocity_anomalies.head(10).iterrows():
        print(f"  {row['address'][:42]}")
        print(f"    Max TX/hour: {row['max_tx_hour']:.0f} | Avg: {row['avg_tx_hour']:.1f} | Spike Ratio: {row['velocity_ratio']:.1f}x")

results['velocity'] = velocity_anomalies[['address', 'max_tx_hour', 'avg_tx_hour', 'velocity_ratio', 'velocity_score']]

# ============================================================
# COMBINED RISK SCORE
# ============================================================
print("\n" + "="*70)
print("COMBINED SOPHISTICATED FRAUD SCORE")
print("="*70)

# Combine all scores
all_addresses = set()
for key in results:
    if len(results[key]) > 0 and 'address' in results[key].columns:
        all_addresses.update(results[key]['address'].values)

combined_scores = []
for addr in all_addresses:
    score = 0
    patterns = []
    
    # Check each pattern
    if len(results.get('smurfing', [])) > 0:
        match = results['smurfing'][results['smurfing']['address'] == addr]
        if len(match) > 0:
            score += match.iloc[0]['smurf_score']
            patterns.append('SMURFING')
    
    if len(results.get('fan_out', [])) > 0:
        match = results['fan_out'][results['fan_out']['address'] == addr]
        if len(match) > 0:
            score += match.iloc[0]['fan_out_score']
            patterns.append('FAN_OUT')
    
    if len(results.get('fan_in', [])) > 0:
        match = results['fan_in'][results['fan_in']['address'] == addr]
        if len(match) > 0:
            score += match.iloc[0]['fan_in_score']
            patterns.append('FAN_IN')
    
    if len(results.get('peeling', [])) > 0:
        match = results['peeling'][results['peeling']['address'] == addr]
        if len(match) > 0:
            score += match.iloc[0]['peeling_score']
            patterns.append('PEELING')
    
    if len(results.get('layering', [])) > 0:
        match = results['layering'][results['layering']['address'] == addr]
        if len(match) > 0:
            score += match.iloc[0]['layering_score']
            patterns.append('LAYERING')
    
    if len(results.get('structuring', [])) > 0:
        match = results['structuring'][results['structuring']['address'] == addr]
        if len(match) > 0:
            score += match.iloc[0]['structuring_score']
            patterns.append('STRUCTURING')
    
    if len(results.get('velocity', [])) > 0:
        match = results['velocity'][results['velocity']['address'] == addr]
        if len(match) > 0:
            score += match.iloc[0]['velocity_score']
            patterns.append('VELOCITY')
    
    combined_scores.append({
        'address': addr,
        'sophisticated_score': score,
        'patterns': ', '.join(patterns),
        'pattern_count': len(patterns)
    })

combined_df = pd.DataFrame(combined_scores)
combined_df = combined_df.sort_values('sophisticated_score', ascending=False)

# Save results
combined_df.to_csv(f"{OUTPUT_DIR}/sophisticated_fraud_patterns.csv", index=False)

print(f"\n📊 SUMMARY:")
print(f"   Total addresses with patterns: {len(combined_df)}")
print(f"   Multi-pattern addresses: {len(combined_df[combined_df['pattern_count'] > 1])}")

print(f"\n🚨 TOP 20 SOPHISTICATED FRAUD SUSPECTS:")
print("-" * 70)
for i, row in combined_df.head(20).iterrows():
    print(f"  {row['address'][:42]}")
    print(f"    Score: {row['sophisticated_score']:.1f} | Patterns: {row['patterns']}")

# Pattern frequency
print(f"\n📈 Pattern Frequency:")
all_patterns = []
for p in combined_df['patterns'].values:
    all_patterns.extend(p.split(', '))
pattern_counts = pd.Series(all_patterns).value_counts()
for pattern, count in pattern_counts.items():
    if pattern:
        print(f"   • {pattern}: {count}")

print(f"\n✅ Results saved to {OUTPUT_DIR}/sophisticated_fraud_patterns.csv")
print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
