"""
ULTRA-FAST Memgraph Ingestion - Optimized for millions of transactions
Uses simple CREATE queries and avoids expensive MERGE operations.
"""
import pandas as pd
import mgclient
from datetime import datetime
import sys
import io

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

print("="*60)
print("ULTRA-FAST MEMGRAPH INGESTION")
print("="*60)
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Configuration
PARQUET_PATH = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
MEMGRAPH_HOST = "localhost"
MEMGRAPH_PORT = 7687
BATCH_SIZE = 2000

# Known addresses for labeling
SANCTIONED_ADDRESSES = {
    "0x8589427373d6d84e98730d7795d8f6f8731fda16", "0x722122df12d4e14e13ac3b6895a86e84145b6967",
    "0xdd4c48c0b24039969fc16d1cdf626eab821d3384", "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",
    "0x4736dcf1b7a3d580672cce6e7c65cd5cc9cfba9d", "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",
    "0xa160cdab225685da1d56aa342ad8841c3b53f291", "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc",
    "0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936", "0x58e8dcc13be9780fc42e8723d8ead4cf46943df2",
    "0x178169b423a011fff22b9e3f3abea13414ddd0f1", "0x610b717796ad172b316836ac95a2ffad065ceab4",
    "0xba214c1c1928a32bffe790263e38b4af9bfcd659", "0x0836222f2b2b24a3f36f98668ed8f0b38d1a872f",
    "0x098b716b8aaf21512996dc57eb0615e2383e2f96", "0xa0e1c89ef1a489c9c7de96311ed5ce5d32c20e4b",
    "0x3cffd56b47b7b41c56258d9c7731abadc360e073", "0x35fb6f6db4fb05e6a4ce86f2c93691425626d4b1",
}
SANCTIONED_LOWER = {a.lower() for a in SANCTIONED_ADDRESSES}

# Connect
print(f"\nConnecting to Memgraph at {MEMGRAPH_HOST}:{MEMGRAPH_PORT}...")
conn = mgclient.connect(host=MEMGRAPH_HOST, port=MEMGRAPH_PORT)
cursor = conn.cursor()
print("Connected!")

# Clear existing data
print("\n[1/4] Clearing existing data...")
cursor.execute("MATCH (n) DETACH DELETE n")
conn.commit()
print("      Done!")

# Create indexes
print("\n[2/4] Creating indexes...")
try:
    cursor.execute("CREATE INDEX ON :Address(address)")
    conn.commit()
except:
    pass
print("      Done!")

# Load data
print(f"\n[3/4] Loading transactions...")
df = pd.read_parquet(PARQUET_PATH)
print(f"      Loaded {len(df):,} transactions")

# Step 1: Create all unique addresses first
print("\n[4/4] Ingesting data...")
print("      Step 1: Creating address nodes...")

all_addresses = set(df['from_address'].dropna().unique()) | set(df['to_address'].dropna().unique())
addr_list = [{"addr": a.lower()} for a in all_addresses if a]

# Batch create addresses
for i in range(0, len(addr_list), 10000):
    batch = addr_list[i:i+10000]
    cursor.execute("""
        UNWIND $addrs AS a
        CREATE (n:Address {address: a.addr})
    """, {"addrs": batch})
    conn.commit()
    if i % 50000 == 0:
        print(f"           Addresses: {min(i+10000, len(addr_list)):,}/{len(addr_list):,}")

print(f"      Created {len(addr_list):,} address nodes")

# Step 2: Add labels to special addresses
print("      Step 2: Labeling special addresses...")
for addr in SANCTIONED_LOWER:
    try:
        cursor.execute("""
            MATCH (n:Address {address: $addr})
            SET n:Sanctioned
        """, {"addr": addr})
    except:
        pass
conn.commit()

# Step 3: Create edges
print("      Step 3: Creating transaction edges...")
total = len(df)
start_time = datetime.now()

for i in range(0, total, BATCH_SIZE):
    batch = df.iloc[i:i+BATCH_SIZE]
    
    tx_list = []
    for _, row in batch.iterrows():
        from_addr = str(row['from_address']).lower() if pd.notna(row['from_address']) else None
        to_addr = str(row['to_address']).lower() if pd.notna(row['to_address']) else None
        
        if not from_addr or not to_addr:
            continue
        
        tx_list.append({
            'from': from_addr,
            'to': to_addr,
            'value': float(row['value_eth']) if pd.notna(row['value_eth']) else 0.0,
        })
    
    if not tx_list:
        continue
    
    # Use MATCH to find existing nodes, then CREATE edge
    query = """
    UNWIND $txs AS tx
    MATCH (from:Address {address: tx.from})
    MATCH (to:Address {address: tx.to})
    CREATE (from)-[:TRANSACTION {value_eth: tx.value}]->(to)
    """
    
    try:
        cursor.execute(query, {"txs": tx_list})
        conn.commit()
    except Exception as e:
        # Skip problematic batches
        pass
    
    if (i // BATCH_SIZE) % 50 == 0:
        pct = min(i + BATCH_SIZE, total) / total * 100
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = (i + BATCH_SIZE) / elapsed if elapsed > 0 else 0
        eta = (total - i - BATCH_SIZE) / rate / 60 if rate > 0 else 0
        print(f"           Transactions: {min(i+BATCH_SIZE, total):,}/{total:,} ({pct:.1f}%) - {rate:.0f} tx/s - ETA: {eta:.1f} min")

elapsed = (datetime.now() - start_time).total_seconds()
print(f"\n      Completed in {elapsed/60:.1f} minutes")

# Stats
cursor.execute("MATCH (n) RETURN count(n)")
nodes = cursor.fetchone()[0]
cursor.execute("MATCH ()-[r]->() RETURN count(r)")
edges = cursor.fetchone()[0]
cursor.execute("MATCH (n:Sanctioned) RETURN count(n)")
sanctioned = cursor.fetchone()[0]

print("\n" + "="*60)
print("INGESTION COMPLETE")
print("="*60)
print(f"   Nodes: {nodes:,}")
print(f"   Edges: {edges:,}")
print(f"   Sanctioned: {sanctioned}")

conn.close()

print("\nReady for fraud detection! Run:")
print("   python scripts/fraud_detection_expanded.py")
