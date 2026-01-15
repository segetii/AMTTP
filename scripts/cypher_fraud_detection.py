"""
Memgraph Ingestion + Cypher Fraud Detection
Ingests transaction data and runs graph-based fraud detection using Cypher queries.
"""
import pandas as pd
import mgclient
from datetime import datetime
import sys
import io

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

print("="*60)
print("MEMGRAPH INGESTION + CYPHER FRAUD DETECTION")
print("="*60)

PARQUET_PATH = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
OUTPUT_DIR = r"c:\amttp\processed"

# Sanctioned addresses
SANCTIONED = [
    "0x8589427373d6d84e98730d7795d8f6f8731fda16", "0x722122df12d4e14e13ac3b6895a86e84145b6967",
    "0xdd4c48c0b24039969fc16d1cdf626eab821d3384", "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",
    "0x4736dcf1b7a3d580672cce6e7c65cd5cc9cfba9d", "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",
    "0x098b716b8aaf21512996dc57eb0615e2383e2f96", "0xa0e1c89ef1a489c9c7de96311ed5ce5d32c20e4b",
    "0x35fb6f6db4fb05e6a4ce86f2c93691425626d4b1", "0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936",
]

# Connect
print("\nConnecting to Memgraph...")
conn = mgclient.connect(host='localhost', port=7687)
cursor = conn.cursor()
print("Connected!")

# Clear and setup
print("\n[1/4] Clearing database...")
cursor.execute("MATCH (n) DETACH DELETE n")
conn.commit()

print("[2/4] Creating indexes...")
try:
    cursor.execute("CREATE INDEX ON :Address(address)")
    conn.commit()
except:
    pass

# Load data - use a sample for faster ingestion
print("\n[3/4] Loading and ingesting transactions...")
df = pd.read_parquet(PARQUET_PATH)
print(f"      Total transactions: {len(df):,}")

# Sample for faster processing (adjust as needed)
SAMPLE_SIZE = 200000
if len(df) > SAMPLE_SIZE:
    # Prioritize transactions involving high-risk addresses
    df['from_lower'] = df['from_address'].str.lower()
    df['to_lower'] = df['to_address'].str.lower()
    sanctioned_lower = [s.lower() for s in SANCTIONED]
    
    # Get transactions involving sanctioned addresses
    risky_txs = df[(df['from_lower'].isin(sanctioned_lower)) | (df['to_lower'].isin(sanctioned_lower))]
    print(f"      Risky transactions: {len(risky_txs):,}")
    
    # Get remaining sample
    remaining = SAMPLE_SIZE - len(risky_txs)
    if remaining > 0:
        other_txs = df[~df.index.isin(risky_txs.index)].sample(n=min(remaining, len(df) - len(risky_txs)))
        df_sample = pd.concat([risky_txs, other_txs])
    else:
        df_sample = risky_txs
    
    print(f"      Using sample of {len(df_sample):,} transactions")
    df = df_sample

# Ingest in batches
BATCH_SIZE = 500
total = len(df)
start_time = datetime.now()

for i in range(0, total, BATCH_SIZE):
    batch = df.iloc[i:i+BATCH_SIZE]
    
    for _, row in batch.iterrows():
        from_addr = str(row['from_address']).lower() if pd.notna(row['from_address']) else None
        to_addr = str(row['to_address']).lower() if pd.notna(row['to_address']) else None
        
        if not from_addr or not to_addr:
            continue
        
        value = float(row['value_eth']) if pd.notna(row['value_eth']) else 0.0
        
        try:
            cursor.execute("""
                MERGE (from:Address {address: $from_addr})
                MERGE (to:Address {address: $to_addr})
                CREATE (from)-[:TX {value: $value}]->(to)
            """, {"from_addr": from_addr, "to_addr": to_addr, "value": value})
        except:
            pass
    
    conn.commit()
    
    if (i // BATCH_SIZE) % 20 == 0:
        pct = min(i + BATCH_SIZE, total) / total * 100
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = (i + BATCH_SIZE) / elapsed if elapsed > 0 else 0
        print(f"      Progress: {min(i+BATCH_SIZE, total):,}/{total:,} ({pct:.1f}%) - {rate:.0f} tx/s")

# Label sanctioned addresses
print("\n      Labeling sanctioned addresses...")
for addr in SANCTIONED:
    cursor.execute("""
        MATCH (n:Address {address: $addr})
        SET n:Sanctioned
    """, {"addr": addr.lower()})
conn.commit()

# Stats
cursor.execute("MATCH (n) RETURN count(n)")
nodes = cursor.fetchone()[0]
cursor.execute("MATCH ()-[r]->() RETURN count(r)")
edges = cursor.fetchone()[0]
print(f"\n      Nodes: {nodes:,}, Edges: {edges:,}")

# ============================================================
# CYPHER FRAUD DETECTION RULES
# ============================================================
print("\n" + "="*60)
print("[4/4] RUNNING CYPHER FRAUD DETECTION RULES")
print("="*60)

results = []

# Rule 1: Direct connections to sanctioned addresses
print("\n[Rule 1] Direct connections to sanctioned addresses...")
cursor.execute("""
    MATCH (a:Address)-[t:TX]->(s:Sanctioned)
    WITH a, count(t) as tx_count, sum(t.value) as total_value
    RETURN a.address as address, tx_count, total_value, 'sent_to_sanctioned' as rule
    ORDER BY total_value DESC
    LIMIT 500
""")
for row in cursor.fetchall():
    results.append({
        'address': row[0],
        'tx_count': row[1],
        'total_value': row[2],
        'rule': row[3],
        'risk_score': 100
    })
print(f"      Found {len(results)} addresses")

# Rule 2: Received from sanctioned
print("\n[Rule 2] Received from sanctioned addresses...")
cursor.execute("""
    MATCH (s:Sanctioned)-[t:TX]->(a:Address)
    WITH a, count(t) as tx_count, sum(t.value) as total_value
    RETURN a.address as address, tx_count, total_value, 'received_from_sanctioned' as rule
    ORDER BY total_value DESC
    LIMIT 500
""")
count_before = len(results)
for row in cursor.fetchall():
    results.append({
        'address': row[0],
        'tx_count': row[1],
        'total_value': row[2],
        'rule': row[3],
        'risk_score': 80
    })
print(f"      Found {len(results) - count_before} addresses")

# Rule 3: 2-hop from sanctioned (money laundering pattern)
print("\n[Rule 3] 2-hop connections (laundering pattern)...")
cursor.execute("""
    MATCH (s:Sanctioned)-[:TX]->(hop1:Address)-[:TX]->(hop2:Address)
    WHERE NOT hop2:Sanctioned AND hop1 <> hop2
    WITH hop2, count(DISTINCT hop1) as intermediaries
    WHERE intermediaries >= 1
    RETURN hop2.address as address, intermediaries, 'laundering_2hop' as rule
    ORDER BY intermediaries DESC
    LIMIT 300
""")
count_before = len(results)
for row in cursor.fetchall():
    results.append({
        'address': row[0],
        'tx_count': row[1],
        'total_value': 0,
        'rule': row[2],
        'risk_score': 50
    })
print(f"      Found {len(results) - count_before} addresses")

# Rule 4: Fan-out pattern (single address sends to many - distribution)
print("\n[Rule 4] Fan-out pattern (distribution)...")
cursor.execute("""
    MATCH (a:Address)-[t:TX]->(receivers:Address)
    WITH a, count(DISTINCT receivers) as num_receivers, sum(t.value) as total_sent
    WHERE num_receivers > 20
    RETURN a.address as address, num_receivers, total_sent, 'fan_out_distribution' as rule
    ORDER BY num_receivers DESC
    LIMIT 200
""")
count_before = len(results)
for row in cursor.fetchall():
    results.append({
        'address': row[0],
        'tx_count': row[1],
        'total_value': row[2],
        'rule': row[3],
        'risk_score': 40
    })
print(f"      Found {len(results) - count_before} addresses")

# Rule 5: Fan-in pattern (many addresses send to one - collection)
print("\n[Rule 5] Fan-in pattern (collection)...")
cursor.execute("""
    MATCH (senders:Address)-[t:TX]->(a:Address)
    WITH a, count(DISTINCT senders) as num_senders, sum(t.value) as total_received
    WHERE num_senders > 20
    RETURN a.address as address, num_senders, total_received, 'fan_in_collection' as rule
    ORDER BY num_senders DESC
    LIMIT 200
""")
count_before = len(results)
for row in cursor.fetchall():
    results.append({
        'address': row[0],
        'tx_count': row[1],
        'total_value': row[2],
        'rule': row[3],
        'risk_score': 40
    })
print(f"      Found {len(results) - count_before} addresses")

# Rule 6: Circular transactions (wash trading)
print("\n[Rule 6] Circular transactions (wash trading)...")
cursor.execute("""
    MATCH (a:Address)-[:TX]->(b:Address)-[:TX]->(a)
    WHERE a <> b
    WITH a, count(DISTINCT b) as circular_partners
    WHERE circular_partners >= 1
    RETURN a.address as address, circular_partners, 'circular_trading' as rule
    ORDER BY circular_partners DESC
    LIMIT 200
""")
count_before = len(results)
for row in cursor.fetchall():
    results.append({
        'address': row[0],
        'tx_count': row[1],
        'total_value': 0,
        'rule': row[2],
        'risk_score': 35
    })
print(f"      Found {len(results) - count_before} addresses")

# Rule 7: High-value transactions
print("\n[Rule 7] High-value transactions (>10 ETH)...")
cursor.execute("""
    MATCH (a:Address)-[t:TX]->()
    WHERE t.value > 10
    WITH a, count(t) as high_value_tx, sum(t.value) as total_high_value
    WHERE high_value_tx >= 1
    RETURN a.address as address, high_value_tx, total_high_value, 'high_value_sender' as rule
    ORDER BY total_high_value DESC
    LIMIT 200
""")
count_before = len(results)
for row in cursor.fetchall():
    results.append({
        'address': row[0],
        'tx_count': row[1],
        'total_value': row[2],
        'rule': row[3],
        'risk_score': 25
    })
print(f"      Found {len(results) - count_before} addresses")

# Aggregate results by address
print("\n" + "="*60)
print("AGGREGATING RESULTS")
print("="*60)

from collections import defaultdict
address_scores = defaultdict(lambda: {'score': 0, 'rules': [], 'total_value': 0})

for r in results:
    addr = r['address']
    address_scores[addr]['score'] += r['risk_score']
    address_scores[addr]['rules'].append(r['rule'])
    address_scores[addr]['total_value'] = max(address_scores[addr]['total_value'], r.get('total_value', 0) or 0)

# Create final DataFrame
final_results = []
for addr, data in address_scores.items():
    final_results.append({
        'address': addr,
        'risk_score': data['score'],
        'rules': ', '.join(set(data['rules'])),
        'rule_count': len(set(data['rules'])),
        'total_value': data['total_value']
    })

results_df = pd.DataFrame(final_results)
results_df = results_df.sort_values('risk_score', ascending=False)

# Save
results_df.to_csv(f"{OUTPUT_DIR}/cypher_fraud_results.csv", index=False)

# Summary
print(f"\nTotal unique addresses flagged: {len(results_df):,}")

critical = results_df[results_df['risk_score'] >= 100]
high = results_df[(results_df['risk_score'] >= 50) & (results_df['risk_score'] < 100)]
medium = results_df[(results_df['risk_score'] >= 25) & (results_df['risk_score'] < 50)]

print(f"\nRisk Distribution:")
print(f"   CRITICAL (>=100): {len(critical):,}")
print(f"   HIGH (50-99):     {len(high):,}")
print(f"   MEDIUM (25-49):   {len(medium):,}")

print("\nTop 15 Risky Addresses:")
for _, row in results_df.head(15).iterrows():
    print(f"   {row['address'][:42]} | Score: {row['risk_score']:3} | Rules: {row['rules'][:40]}")

# Save high-risk
high_risk = results_df[results_df['risk_score'] >= 50]
high_risk.to_csv(f"{OUTPUT_DIR}/cypher_high_risk.csv", index=False)
print(f"\nSaved {len(high_risk)} high-risk addresses to cypher_high_risk.csv")

conn.close()
print("\n" + "="*60)
print("CYPHER FRAUD DETECTION COMPLETE")
print("="*60)
