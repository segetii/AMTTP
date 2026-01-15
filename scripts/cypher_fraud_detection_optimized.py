"""
OPTIMIZED Memgraph Ingestion + Cypher Fraud Detection
Uses batch UNWIND queries and vectorized pandas operations for 10-50x speedup.
"""
import pandas as pd
import numpy as np
import mgclient
from datetime import datetime
from collections import defaultdict
import sys
import io

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

print("="*60)
print("OPTIMIZED MEMGRAPH + CYPHER FRAUD DETECTION")
print("="*60)
start_total = datetime.now()

PARQUET_PATH = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
OUTPUT_DIR = r"c:\amttp\processed"

# Sanctioned addresses (lowercase for fast lookup)
SANCTIONED = {
    "0x8589427373d6d84e98730d7795d8f6f8731fda16", "0x722122df12d4e14e13ac3b6895a86e84145b6967",
    "0xdd4c48c0b24039969fc16d1cdf626eab821d3384", "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",
    "0x4736dcf1b7a3d580672cce6e7c65cd5cc9cfba9d", "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",
    "0x098b716b8aaf21512996dc57eb0615e2383e2f96", "0xa0e1c89ef1a489c9c7de96311ed5ce5d32c20e4b",
    "0x35fb6f6db4fb05e6a4ce86f2c93691425626d4b1", "0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936",
    "0xa160cdab225685da1d56aa342ad8841c3b53f291", "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc",
    "0x58e8dcc13be9780fc42e8723d8ead4cf46943df2", "0x178169b423a011fff22b9e3f3abea13414ddd0f1",
    "0x610b717796ad172b316836ac95a2ffad065ceab4", "0xba214c1c1928a32bffe790263e38b4af9bfcd659",
    "0x0836222f2b2b24a3f36f98668ed8f0b38d1a872f", "0x3cffd56b47b7b41c56258d9c7731abadc360e073",
}
SANCTIONED_LOWER = {s.lower() for s in SANCTIONED}

# Connect
print("\nConnecting to Memgraph...")
conn = mgclient.connect(host='localhost', port=7687)
cursor = conn.cursor()
print("Connected!")

# ============================================================
# PHASE 1: OPTIMIZED DATA LOADING
# ============================================================
print("\n" + "="*60)
print("PHASE 1: DATA LOADING")
print("="*60)

t0 = datetime.now()
print("Loading parquet file...")
df = pd.read_parquet(PARQUET_PATH)

# Vectorized lowercase conversion (much faster than str.lower())
df['from_lower'] = df['from_address'].str.lower()
df['to_lower'] = df['to_address'].str.lower()
df['value'] = pd.to_numeric(df['value_eth'], errors='coerce').fillna(0.0)

# Drop rows with missing addresses
df = df.dropna(subset=['from_lower', 'to_lower'])

print(f"Loaded {len(df):,} transactions in {(datetime.now()-t0).total_seconds():.1f}s")

# Smart sampling: prioritize risky transactions
SAMPLE_SIZE = 300000
if len(df) > SAMPLE_SIZE:
    t0 = datetime.now()
    
    # Vectorized check for sanctioned addresses (fast)
    is_risky = df['from_lower'].isin(SANCTIONED_LOWER) | df['to_lower'].isin(SANCTIONED_LOWER)
    risky_df = df[is_risky]
    
    # High-value transactions
    high_value = df[~is_risky & (df['value'] > 1)]
    
    # Random sample of remainder
    remaining = SAMPLE_SIZE - len(risky_df) - len(high_value)
    if remaining > 0:
        other = df[~is_risky & (df['value'] <= 1)].sample(n=min(remaining, len(df) - len(risky_df) - len(high_value)), random_state=42)
        df = pd.concat([risky_df, high_value.head(remaining//2), other])
    else:
        df = pd.concat([risky_df, high_value.head(SAMPLE_SIZE - len(risky_df))])
    
    print(f"Sampled {len(df):,} transactions (prioritizing risky) in {(datetime.now()-t0).total_seconds():.1f}s")

# ============================================================
# PHASE 2: OPTIMIZED MEMGRAPH INGESTION
# ============================================================
print("\n" + "="*60)
print("PHASE 2: MEMGRAPH INGESTION (Batch Mode)")
print("="*60)

# Clear database
t0 = datetime.now()
print("Clearing database...")
try:
    cursor.execute("DROP INDEX ON :Address(address)")
    conn.commit()
except:
    pass
cursor.execute("MATCH (n) DETACH DELETE n")
conn.commit()
print(f"Cleared in {(datetime.now()-t0).total_seconds():.1f}s")

# Create unique addresses first (faster than MERGE in transaction loop)
t0 = datetime.now()
print("Creating address nodes...")
all_addresses = list(set(df['from_lower'].unique()) | set(df['to_lower'].unique()))
print(f"   {len(all_addresses):,} unique addresses")

# Batch create addresses using UNWIND
ADDR_BATCH = 10000
for i in range(0, len(all_addresses), ADDR_BATCH):
    batch = all_addresses[i:i+ADDR_BATCH]
    cursor.execute("""
        UNWIND $addrs AS addr
        CREATE (n:Address {address: addr})
    """, {"addrs": batch})
    conn.commit()

print(f"Created address nodes in {(datetime.now()-t0).total_seconds():.1f}s")

# Create index AFTER bulk insert (faster)
t0 = datetime.now()
print("Creating indexes...")
cursor.execute("CREATE INDEX ON :Address(address)")
conn.commit()
print(f"Index created in {(datetime.now()-t0).total_seconds():.1f}s")

# Label sanctioned addresses
print("Labeling sanctioned addresses...")
for addr in SANCTIONED_LOWER:
    try:
        cursor.execute("MATCH (n:Address {address: $addr}) SET n:Sanctioned", {"addr": addr})
    except:
        pass
conn.commit()

# Batch create edges using UNWIND with MATCH
t0 = datetime.now()
print("Creating transaction edges...")
TX_BATCH = 2000
total = len(df)

# Convert to list of dicts for UNWIND (vectorized)
tx_records = df[['from_lower', 'to_lower', 'value']].to_dict('records')

for i in range(0, total, TX_BATCH):
    batch = tx_records[i:i+TX_BATCH]
    
    # Prepare batch data
    tx_list = [{'f': r['from_lower'], 't': r['to_lower'], 'v': r['value']} for r in batch]
    
    try:
        cursor.execute("""
            UNWIND $txs AS tx
            MATCH (from:Address {address: tx.f})
            MATCH (to:Address {address: tx.t})
            CREATE (from)-[:TX {value: tx.v}]->(to)
        """, {"txs": tx_list})
        conn.commit()
    except Exception as e:
        # On error, try smaller batches
        for j in range(0, len(tx_list), 200):
            try:
                cursor.execute("""
                    UNWIND $txs AS tx
                    MATCH (from:Address {address: tx.f})
                    MATCH (to:Address {address: tx.t})
                    CREATE (from)-[:TX {value: tx.v}]->(to)
                """, {"txs": tx_list[j:j+200]})
                conn.commit()
            except:
                pass
    
    if (i // TX_BATCH) % 25 == 0:
        pct = min(i + TX_BATCH, total) / total * 100
        elapsed = (datetime.now() - t0).total_seconds()
        rate = (i + TX_BATCH) / elapsed if elapsed > 0 else 0
        eta = (total - i - TX_BATCH) / rate / 60 if rate > 0 else 0
        print(f"   Progress: {min(i+TX_BATCH, total):,}/{total:,} ({pct:.1f}%) - {rate:.0f} tx/s - ETA: {eta:.1f}m")

print(f"Edges created in {(datetime.now()-t0).total_seconds():.1f}s")

# Stats
cursor.execute("MATCH (n) RETURN count(n)")
nodes = cursor.fetchone()[0]
cursor.execute("MATCH ()-[r]->() RETURN count(r)")
edges = cursor.fetchone()[0]
cursor.execute("MATCH (n:Sanctioned) RETURN count(n)")
sanctioned_count = cursor.fetchone()[0]
print(f"\nGraph: {nodes:,} nodes, {edges:,} edges, {sanctioned_count} sanctioned")

# ============================================================
# PHASE 3: CYPHER FRAUD DETECTION (Optimized Queries)
# ============================================================
print("\n" + "="*60)
print("PHASE 3: CYPHER FRAUD DETECTION")
print("="*60)

results = []

def run_rule(name, query, risk_score, limit=500):
    """Run a fraud detection rule and collect results."""
    t0 = datetime.now()
    cursor.execute(query)
    rows = cursor.fetchall()
    elapsed = (datetime.now() - t0).total_seconds()
    
    for row in rows:
        results.append({
            'address': row[0],
            'metric': row[1] if len(row) > 1 else 0,
            'value': row[2] if len(row) > 2 else 0,
            'rule': name,
            'risk_score': risk_score
        })
    
    print(f"[{name}] Found {len(rows)} addresses ({elapsed:.2f}s)")
    return len(rows)

# Rule 1: Sent to sanctioned (CRITICAL)
run_rule('sent_to_sanctioned', """
    MATCH (a:Address)-[t:TX]->(s:Sanctioned)
    WITH a, count(t) as tx_count, sum(t.value) as total_value
    RETURN a.address, tx_count, total_value
    ORDER BY total_value DESC LIMIT 500
""", 100)

# Rule 2: Received from sanctioned (HIGH)
run_rule('received_from_sanctioned', """
    MATCH (s:Sanctioned)-[t:TX]->(a:Address)
    WHERE NOT a:Sanctioned
    WITH a, count(t) as tx_count, sum(t.value) as total_value
    RETURN a.address, tx_count, total_value
    ORDER BY total_value DESC LIMIT 500
""", 80)

# Rule 3: 2-hop laundering pattern (HIGH)
run_rule('laundering_2hop', """
    MATCH (s:Sanctioned)-[:TX]->(h1:Address)-[:TX]->(h2:Address)
    WHERE NOT h2:Sanctioned AND h1 <> h2
    WITH h2, count(DISTINCT h1) as hops
    RETURN h2.address, hops, 0
    ORDER BY hops DESC LIMIT 300
""", 50)

# Rule 4: Fan-out distribution (MEDIUM)
run_rule('fan_out', """
    MATCH (a:Address)-[t:TX]->(r:Address)
    WITH a, count(DISTINCT r) as receivers, sum(t.value) as total
    WHERE receivers > 15
    RETURN a.address, receivers, total
    ORDER BY receivers DESC LIMIT 200
""", 40)

# Rule 5: Fan-in collection (MEDIUM)
run_rule('fan_in', """
    MATCH (s:Address)-[t:TX]->(a:Address)
    WITH a, count(DISTINCT s) as senders, sum(t.value) as total
    WHERE senders > 15
    RETURN a.address, senders, total
    ORDER BY senders DESC LIMIT 200
""", 40)

# Rule 6: Circular/wash trading (MEDIUM)
run_rule('circular', """
    MATCH (a:Address)-[:TX]->(b:Address)-[:TX]->(a)
    WHERE a <> b
    WITH a, count(DISTINCT b) as partners
    RETURN a.address, partners, 0
    ORDER BY partners DESC LIMIT 200
""", 35)

# Rule 7: High-value sender (LOW-MEDIUM)
run_rule('high_value', """
    MATCH (a:Address)-[t:TX]->()
    WHERE t.value > 10
    WITH a, count(t) as hv_count, sum(t.value) as total
    RETURN a.address, hv_count, total
    ORDER BY total DESC LIMIT 200
""", 25)

# ============================================================
# PHASE 4: AGGREGATE AND SAVE
# ============================================================
print("\n" + "="*60)
print("PHASE 4: AGGREGATING RESULTS")
print("="*60)

# Fast aggregation using defaultdict
address_scores = defaultdict(lambda: {'score': 0, 'rules': set(), 'value': 0})

for r in results:
    addr = r['address']
    address_scores[addr]['score'] += r['risk_score']
    address_scores[addr]['rules'].add(r['rule'])
    address_scores[addr]['value'] = max(address_scores[addr]['value'], r.get('value', 0) or 0)

# Convert to DataFrame efficiently
final_data = [
    {
        'address': addr,
        'risk_score': data['score'],
        'rules': ', '.join(data['rules']),
        'rule_count': len(data['rules']),
        'total_value': data['value']
    }
    for addr, data in address_scores.items()
]

results_df = pd.DataFrame(final_data)
results_df = results_df.sort_values('risk_score', ascending=False)

# Save results
results_df.to_csv(f"{OUTPUT_DIR}/cypher_fraud_results.csv", index=False)

# Summary
print(f"\nTotal unique addresses flagged: {len(results_df):,}")

critical = len(results_df[results_df['risk_score'] >= 100])
high = len(results_df[(results_df['risk_score'] >= 50) & (results_df['risk_score'] < 100)])
medium = len(results_df[(results_df['risk_score'] >= 25) & (results_df['risk_score'] < 50)])

print(f"\nRisk Distribution:")
print(f"   CRITICAL (>=100): {critical:,}")
print(f"   HIGH (50-99):     {high:,}")
print(f"   MEDIUM (25-49):   {medium:,}")

print("\nTop 15 Risky Addresses:")
for _, row in results_df.head(15).iterrows():
    print(f"   {row['address'][:42]} | Score: {row['risk_score']:3} | {row['rules'][:35]}")

# Save high-risk
high_risk = results_df[results_df['risk_score'] >= 50]
high_risk.to_csv(f"{OUTPUT_DIR}/cypher_high_risk.csv", index=False)
print(f"\nSaved {len(high_risk)} high-risk addresses to cypher_high_risk.csv")

conn.close()

total_time = (datetime.now() - start_total).total_seconds()
print("\n" + "="*60)
print(f"COMPLETE - Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
print("="*60)
