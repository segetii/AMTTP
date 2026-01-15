"""
Quick Fraud Detection on Full ETH Dataset
Runs graph-based pattern detection WITHOUT needing Memgraph ingestion.
Uses pandas for in-memory graph analysis.
"""
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict
import sys
import io

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

print("="*60)
print("QUICK FRAUD DETECTION (In-Memory Graph Analysis)")
print("="*60)
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Configuration
PARQUET_PATH = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
OUTPUT_DIR = r"c:\amttp\processed"

# ============================================================
# SANCTIONED ADDRESS DATABASE
# ============================================================

TORNADO_CASH = {
    "0x8589427373d6d84e98730d7795d8f6f8731fda16", "0x722122df12d4e14e13ac3b6895a86e84145b6967",
    "0xdd4c48c0b24039969fc16d1cdf626eab821d3384", "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",
    "0x4736dcf1b7a3d580672cce6e7c65cd5cc9cfba9d", "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",
    "0xa160cdab225685da1d56aa342ad8841c3b53f291", "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc",
    "0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936", "0x58e8dcc13be9780fc42e8723d8ead4cf46943df2",
    "0x178169b423a011fff22b9e3f3abea13414ddd0f1", "0x610b717796ad172b316836ac95a2ffad065ceab4",
    "0xba214c1c1928a32bffe790263e38b4af9bfcd659", "0x0836222f2b2b24a3f36f98668ed8f0b38d1a872f",
    "0xd882cfc20f52f2599d84b8e8d58c7fb62cfe344b", "0x7f367cc41522ce07553e823bf3be79a889debe1b",
    "0x23773e65ed146a459791799d01336db287f25334", "0xd691f27f38b395864ea86cfc7253969b409c362d",
    "0x22aaa7720ddd5388a3c0a3333430953c68f1849b", "0x03893a7c7463ae47d46bc7f091665f1893656003",
}

LAZARUS_GROUP = {
    "0x098b716b8aaf21512996dc57eb0615e2383e2f96", "0xa0e1c89ef1a489c9c7de96311ed5ce5d32c20e4b",
    "0x3cffd56b47b7b41c56258d9c7731abadc360e073", "0x53b6936513e738f44fb50d2b9476730c0ab3bfc1",
    "0x35fb6f6db4fb05e6a4ce86f2c93691425626d4b1", "0x4f3a120e72c76c22ae802d129f599bfdbc31cb81",
}

EXPLOIT_ADDRESSES = {
    "0x59abf3837fa962d6853b4cc0a19513aa031fd32b",  # PolyNetwork
    "0x0d0707963952f2fba59dd06f2b425ace40b492fe",  # Cream Finance
    "0x905315602ed9a854e325f692ff82f58799beab57",  # Uranium Finance
}

ALL_SANCTIONED = TORNADO_CASH | LAZARUS_GROUP | EXPLOIT_ADDRESSES
ALL_SANCTIONED_LOWER = {a.lower() for a in ALL_SANCTIONED}

# Risk weights
RISK_WEIGHTS = {
    'sent_to_sanctioned': 100,
    'received_from_sanctioned': 80,
    'sent_to_2hop': 40,
    'received_from_2hop': 30,
    'high_value_tx': 15,
    'round_amount': 10,
    'many_small_tx': 20,
    'fan_out': 25,
    'fan_in': 25,
}

# Load data
print("\n[1/5] Loading transactions...")
df = pd.read_parquet(PARQUET_PATH)
df['from_address'] = df['from_address'].str.lower()
df['to_address'] = df['to_address'].str.lower()
print(f"      Loaded {len(df):,} transactions")

# Step 1: Find direct connections to sanctioned addresses
print("\n[2/5] Finding direct sanctioned connections...")
address_risk = defaultdict(lambda: {'score': 0, 'reasons': []})

# Sent TO sanctioned
sent_to_sanctioned = df[df['to_address'].isin(ALL_SANCTIONED_LOWER)]
for addr in sent_to_sanctioned['from_address'].unique():
    txs = sent_to_sanctioned[sent_to_sanctioned['from_address'] == addr]
    total_value = txs['value_eth'].sum()
    address_risk[addr]['score'] += RISK_WEIGHTS['sent_to_sanctioned']
    address_risk[addr]['reasons'].append(f'sent_to_sanctioned({len(txs)} txs, {total_value:.2f} ETH)')

print(f"      Found {len(sent_to_sanctioned['from_address'].unique())} addresses sent to sanctioned")

# Received FROM sanctioned
received_from_sanctioned = df[df['from_address'].isin(ALL_SANCTIONED_LOWER)]
for addr in received_from_sanctioned['to_address'].unique():
    txs = received_from_sanctioned[received_from_sanctioned['to_address'] == addr]
    total_value = txs['value_eth'].sum()
    address_risk[addr]['score'] += RISK_WEIGHTS['received_from_sanctioned']
    address_risk[addr]['reasons'].append(f'received_from_sanctioned({len(txs)} txs, {total_value:.2f} ETH)')

print(f"      Found {len(received_from_sanctioned['to_address'].unique())} addresses received from sanctioned")

# Step 2: Find 2-hop connections
print("\n[3/5] Finding 2-hop connections...")

# Addresses that received from sanctioned (1st hop)
first_hop_receivers = set(received_from_sanctioned['to_address'].unique())

# Who did first-hop receivers send to? (2nd hop)
if first_hop_receivers:
    second_hop = df[df['from_address'].isin(first_hop_receivers)]
    for addr in second_hop['to_address'].unique():
        if addr not in first_hop_receivers and addr not in ALL_SANCTIONED_LOWER:
            address_risk[addr]['score'] += RISK_WEIGHTS['received_from_2hop']
            address_risk[addr]['reasons'].append('2hop_from_sanctioned')

# Who sent to first-hop receivers?
first_hop_senders = set(sent_to_sanctioned['from_address'].unique())
if first_hop_senders:
    second_hop_senders = df[df['to_address'].isin(first_hop_senders)]
    for addr in second_hop_senders['from_address'].unique():
        if addr not in first_hop_senders and addr not in ALL_SANCTIONED_LOWER:
            address_risk[addr]['score'] += RISK_WEIGHTS['sent_to_2hop']
            address_risk[addr]['reasons'].append('2hop_to_sanctioned')

print(f"      Analyzed 2-hop network")

# Step 3: Behavioral patterns
print("\n[4/5] Detecting behavioral patterns...")

# Aggregate by sender
sender_stats = df.groupby('from_address').agg({
    'value_eth': ['sum', 'mean', 'count', 'std'],
    'to_address': 'nunique'
}).reset_index()
sender_stats.columns = ['address', 'total_sent', 'avg_sent', 'tx_count', 'std_sent', 'unique_receivers']

# Aggregate by receiver  
receiver_stats = df.groupby('to_address').agg({
    'value_eth': ['sum', 'mean', 'count'],
    'from_address': 'nunique'
}).reset_index()
receiver_stats.columns = ['address', 'total_received', 'avg_received', 'rx_count', 'unique_senders']

# High value transactions
high_value_senders = sender_stats[sender_stats['total_sent'] > 100]['address']
for addr in high_value_senders:
    val = sender_stats[sender_stats['address'] == addr]['total_sent'].values[0]
    address_risk[addr]['score'] += RISK_WEIGHTS['high_value_tx']
    address_risk[addr]['reasons'].append(f'high_value({val:.1f} ETH)')

# Fan-out pattern (single address sends to many)
fan_out = sender_stats[sender_stats['unique_receivers'] > 50]['address']
for addr in fan_out:
    n = sender_stats[sender_stats['address'] == addr]['unique_receivers'].values[0]
    address_risk[addr]['score'] += RISK_WEIGHTS['fan_out']
    address_risk[addr]['reasons'].append(f'fan_out({n} receivers)')

# Fan-in pattern (many addresses send to one)
fan_in = receiver_stats[receiver_stats['unique_senders'] > 50]['address']
for addr in fan_in:
    n = receiver_stats[receiver_stats['address'] == addr]['unique_senders'].values[0]
    address_risk[addr]['score'] += RISK_WEIGHTS['fan_in']
    address_risk[addr]['reasons'].append(f'fan_in({n} senders)')

# Round amounts (structuring)
df['is_round'] = (df['value_eth'] % 1 == 0) & (df['value_eth'] > 0)
round_tx_counts = df[df['is_round']].groupby('from_address').size()
frequent_round = round_tx_counts[round_tx_counts > 5]
for addr in frequent_round.index:
    address_risk[addr]['score'] += RISK_WEIGHTS['round_amount']
    address_risk[addr]['reasons'].append(f'round_amounts({frequent_round[addr]} txs)')

print(f"      Detected patterns for {len(address_risk)} addresses")

# Step 5: Generate results
print("\n[5/5] Generating results...")

results = []
for addr, data in address_risk.items():
    if data['score'] > 0:
        results.append({
            'address': addr,
            'risk_score': data['score'],
            'reasons': ', '.join(data['reasons']),
            'reason_count': len(data['reasons'])
        })

results_df = pd.DataFrame(results)
results_df = results_df.sort_values('risk_score', ascending=False)

# Save results
results_df.to_csv(f"{OUTPUT_DIR}/scored_transactions_expanded.csv", index=False)
print(f"      Saved {len(results_df)} scored addresses")

# Summary
print("\n" + "="*60)
print("FRAUD DETECTION RESULTS")
print("="*60)

print(f"\nTotal addresses analyzed: {len(set(df['from_address']) | set(df['to_address'])):,}")
print(f"Addresses with risk signals: {len(results_df):,}")

# Risk distribution
critical = results_df[results_df['risk_score'] >= 100]
high = results_df[(results_df['risk_score'] >= 50) & (results_df['risk_score'] < 100)]
medium = results_df[(results_df['risk_score'] >= 25) & (results_df['risk_score'] < 50)]
low = results_df[results_df['risk_score'] < 25]

print(f"\nRisk Distribution:")
print(f"   CRITICAL (>=100): {len(critical):,}")
print(f"   HIGH (50-99):     {len(high):,}")
print(f"   MEDIUM (25-49):   {len(medium):,}")
print(f"   LOW (<25):        {len(low):,}")

# Top risky addresses
print("\nTop 10 Risky Addresses:")
for i, row in results_df.head(10).iterrows():
    print(f"   {row['address'][:20]}... Score: {row['risk_score']} - {row['reasons'][:50]}")

# Save high-risk for cross-validation
high_risk = results_df[results_df['risk_score'] >= 50]
high_risk.to_csv(f"{OUTPUT_DIR}/high_risk_addresses.csv", index=False)
print(f"\nSaved {len(high_risk)} high-risk addresses to high_risk_addresses.csv")

critical_risk = results_df[results_df['risk_score'] >= 100]
critical_risk.to_csv(f"{OUTPUT_DIR}/critical_risk_addresses.csv", index=False)
print(f"Saved {len(critical_risk)} critical addresses to critical_risk_addresses.csv")

print("\n" + "="*60)
print("NEXT STEP: Run cross_validate_fraud.py")
print("="*60)
