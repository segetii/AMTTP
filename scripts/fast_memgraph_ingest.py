"""
FAST Memgraph Ingestion - Optimized for large datasets (1M+ transactions)
Uses batch UNWIND queries for 100x faster ingestion.
"""
import pandas as pd
import mgclient
from datetime import datetime
import sys
import io

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

print("="*60)
print("FAST MEMGRAPH INGESTION (Optimized)")
print("="*60)
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Configuration
PARQUET_PATH = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
MEMGRAPH_HOST = "localhost"
MEMGRAPH_PORT = 7687
BATCH_SIZE = 1000  # Smaller batch to avoid timeout

# Known addresses
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
    "0x53b6936513e738f44fb50d2b9476730c0ab3bfc1", "0x6f1ca141a28907f78ebaa64fb83a9088b02a8352",
}

EXCHANGE_ADDRESSES = {
    "0x28c6c06298d514db089934071355e5743bf21d60", "0xdfd5293d8e347dfe59e90efd55b2956a1343963d",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549", "0x56eddb7aa87536c09ccc2793473599fd21a8b17f",
    "0xf977814e90da44bfa03b6295a0616a897441acec", "0x71660c4005ba85c37ccec55d0c4493e66fe775d3",
    "0x503828976d22510aad0201ac7ec88293211d23da", "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43",
    "0xb5d85cbf7cb3ee0d56b3bb207d5fc4b82f43f511", "0x2910543af39aba0cd09dbb2d50200b3e800a63d2",
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b",
}

# Pre-compute lowercase sets for fast lookup
SANCTIONED_LOWER = {a.lower() for a in SANCTIONED_ADDRESSES}
EXCHANGE_LOWER = {a.lower() for a in EXCHANGE_ADDRESSES}

# Load high-risk from previous analysis
HIGH_RISK_LOWER = set()
try:
    hr_df = pd.read_csv(r'c:\amttp\processed\consensus_high_risk.csv')
    HIGH_RISK_LOWER = set(hr_df['address'].str.lower())
    print(f"Loaded {len(HIGH_RISK_LOWER)} consensus high-risk addresses")
except:
    print("No consensus high-risk file found")


def get_node_type(address):
    """Fast label lookup."""
    addr = address.lower() if address else ""
    if addr in SANCTIONED_LOWER:
        return "Sanctioned"
    if addr in EXCHANGE_LOWER:
        return "Exchange"
    if addr in HIGH_RISK_LOWER:
        return "HighRisk"
    return "Address"


# Connect
print(f"\nConnecting to Memgraph at {MEMGRAPH_HOST}:{MEMGRAPH_PORT}...")
conn = mgclient.connect(host=MEMGRAPH_HOST, port=MEMGRAPH_PORT)
cursor = conn.cursor()
print("Connected!")

# Clear existing data
print("\n[1/5] Clearing existing data...")
cursor.execute("MATCH (n) DETACH DELETE n")
conn.commit()
print("      Database cleared!")

# Create indexes
print("\n[2/5] Creating indexes...")
for idx in ["Address", "Sanctioned", "Exchange", "HighRisk"]:
    try:
        cursor.execute(f"CREATE INDEX ON :{idx}(address)")
        conn.commit()
    except:
        pass
print("      Indexes created!")

# Load data
print(f"\n[3/5] Loading transactions from parquet...")
df = pd.read_parquet(PARQUET_PATH)
print(f"      Loaded {len(df):,} transactions")

# Pre-process: identify special addresses
print("\n[4/5] Analyzing address types...")
all_addresses = set(df['from_address'].dropna().unique()) | set(df['to_address'].dropna().unique())
print(f"      Found {len(all_addresses):,} unique addresses")

sanctioned_in_data = {a for a in all_addresses if a.lower() in SANCTIONED_LOWER}
exchange_in_data = {a for a in all_addresses if a.lower() in EXCHANGE_LOWER}
high_risk_in_data = {a for a in all_addresses if a.lower() in HIGH_RISK_LOWER}

print(f"      Sanctioned addresses found: {len(sanctioned_in_data)}")
print(f"      Exchange addresses found: {len(exchange_in_data)}")
print(f"      High-risk addresses found: {len(high_risk_in_data)}")

# Create special nodes first
print("\n      Creating labeled nodes...")
for addr in sanctioned_in_data:
    cursor.execute("MERGE (n:Sanctioned:Address {address: $addr})", {"addr": addr.lower()})
for addr in exchange_in_data:
    cursor.execute("MERGE (n:Exchange:Address {address: $addr})", {"addr": addr.lower()})
for addr in high_risk_in_data:
    cursor.execute("MERGE (n:HighRisk:Address {address: $addr})", {"addr": addr.lower()})
conn.commit()

# Batch ingest transactions
print(f"\n[5/5] Ingesting transactions (batch size: {BATCH_SIZE})...")
total = len(df)
start_time = datetime.now()

for i in range(0, total, BATCH_SIZE):
    batch = df.iloc[i:i+BATCH_SIZE]
    
    # Prepare batch data
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
            'block': int(row['block_number']) if pd.notna(row['block_number']) else 0
        })
    
    if not tx_list:
        continue
    
    # Batch UNWIND query - much faster than individual inserts
    query = """
    UNWIND $transactions AS tx
    MERGE (from:Address {address: tx.from})
    MERGE (to:Address {address: tx.to})
    CREATE (from)-[:TRANSACTION {value_eth: tx.value, block: tx.block}]->(to)
    """
    
    try:
        cursor.execute(query, {"transactions": tx_list})
        conn.commit()
    except Exception as e:
        # On timeout, try smaller sub-batches
        try:
            for j in range(0, len(tx_list), 200):
                sub_batch = tx_list[j:j+200]
                cursor.execute(query, {"transactions": sub_batch})
                conn.commit()
        except:
            pass  # Skip problematic batch
    
    # Progress update every 10 batches
    if (i // BATCH_SIZE) % 10 == 0:
        pct = min(i + BATCH_SIZE, total) / total * 100
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = (i + BATCH_SIZE) / elapsed if elapsed > 0 else 0
        eta = (total - i - BATCH_SIZE) / rate if rate > 0 else 0
        print(f"      Progress: {min(i+BATCH_SIZE, total):,}/{total:,} ({pct:.1f}%) - Rate: {rate:.0f} tx/s - ETA: {eta/60:.1f} min")

# Final stats
elapsed = (datetime.now() - start_time).total_seconds()
print(f"\n      Completed in {elapsed/60:.1f} minutes ({total/elapsed:.0f} tx/sec)")

# Get stats
print("\n" + "="*60)
print("INGESTION COMPLETE")
print("="*60)

cursor.execute("MATCH (n) RETURN count(n)")
nodes = cursor.fetchone()[0]
cursor.execute("MATCH ()-[r]->() RETURN count(r)")
edges = cursor.fetchone()[0]

print(f"\nGraph Statistics:")
print(f"   Total nodes: {nodes:,}")
print(f"   Total edges: {edges:,}")

# Count by label
cursor.execute("""
MATCH (n)
WITH labels(n) as lbls
UNWIND lbls as lbl
RETURN lbl, count(*) as cnt
ORDER BY cnt DESC
""")
print("\nNodes by label:")
for row in cursor.fetchall():
    print(f"   {row[0]}: {row[1]:,}")

conn.close()

print("\n" + "="*60)
print("READY FOR FRAUD DETECTION")
print("="*60)
print("""
Next steps:
1. Run fraud_detection_expanded.py for graph-based analysis
2. Run cross_validate_fraud.py for ML cross-validation

Or query in Memgraph Lab (http://localhost:3000):

MATCH (s:Sanctioned)-[t:TRANSACTION]-(connected)
RETURN s, t, connected LIMIT 100
""")
