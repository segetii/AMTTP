"""
AMTTP Memgraph Data Loader
Loads training transaction data into Memgraph for graph analytics
"""
import pandas as pd
import mgclient
from datetime import datetime
import sys

print("=" * 60)
print("AMTTP MEMGRAPH DATA LOADER")
print("=" * 60)

# Configuration
PARQUET_PATH = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
SAMPLE_SIZE = 100000  # Load 100k transactions for dashboard

# Known sanctioned addresses
SANCTIONED = {
    "0x8589427373d6d84e98730d7795d8f6f8731fda16",
    "0x722122df12d4e14e13ac3b6895a86e84145b6967",
    "0xdd4c48c0b24039969fc16d1cdf626eab821d3384",
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",
    "0x4736dcf1b7a3d580672cce6e7c65cd5cc9cfba9d",
    "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",
    "0x098b716b8aaf21512996dc57eb0615e2383e2f96",
    "0xa0e1c89ef1a489c9c7de96311ed5ce5d32c20e4b",
    "0x35fb6f6db4fb05e6a4ce86f2c93691425626d4b1",
}

print("\n[1/5] Connecting to Memgraph...")
try:
    conn = mgclient.connect(host='localhost', port=7687)
    cursor = conn.cursor()
    print("✅ Connected to Memgraph")
except Exception as e:
    print(f"❌ Failed to connect: {e}")
    sys.exit(1)

print("\n[2/5] Loading parquet file...")
t0 = datetime.now()
df = pd.read_parquet(PARQUET_PATH)
print(f"   Loaded {len(df):,} rows in {(datetime.now()-t0).total_seconds():.1f}s")
print(f"   Columns: {df.columns.tolist()}")

# Sample data
if len(df) > SAMPLE_SIZE:
    print(f"\n[3/5] Sampling {SAMPLE_SIZE:,} transactions...")
    df = df.sample(n=SAMPLE_SIZE, random_state=42)
else:
    print(f"\n[3/5] Using all {len(df):,} transactions...")

# Prepare data
df['from_addr'] = df['from_address'].astype(str).str.lower()
df['to_addr'] = df['to_address'].astype(str).str.lower()
df['value'] = pd.to_numeric(df['value_eth'], errors='coerce').fillna(0.0)
df['gas'] = pd.to_numeric(df['gas_used'], errors='coerce').fillna(0)
df['block'] = pd.to_numeric(df['block_number'], errors='coerce').fillna(0).astype(int)

print(f"   Sample value range: {df['value'].min():.4f} - {df['value'].max():.2f} ETH")

print("\n[4/5] Clearing Memgraph and loading data...")
t0 = datetime.now()

# Clear existing data
cursor.execute("MATCH (n) DETACH DELETE n")
conn.commit()
print("   Cleared existing data")

# Drop and recreate indexes
try:
    cursor.execute("DROP INDEX ON :Address(address)")
    conn.commit()
except:
    pass

# Get unique addresses
all_addresses = list(set(df['from_addr'].unique()) | set(df['to_addr'].unique()))
print(f"   Creating {len(all_addresses):,} address nodes...")

# Batch create address nodes
BATCH_SIZE = 5000
for i in range(0, len(all_addresses), BATCH_SIZE):
    batch = all_addresses[i:i+BATCH_SIZE]
    cursor.execute("""
        UNWIND $addrs AS addr
        CREATE (n:Address {address: addr})
    """, {"addrs": batch})
    conn.commit()
    print(f"      Addresses: {min(i+BATCH_SIZE, len(all_addresses)):,}/{len(all_addresses):,}", end='\r')

print(f"\n   Created {len(all_addresses):,} address nodes")

# Create index using a fresh connection
try:
    idx_conn = mgclient.connect(host='localhost', port=7687)
    idx_conn.autocommit = True
    idx_cursor = idx_conn.cursor()
    idx_cursor.execute("CREATE INDEX ON :Address(address)")
    idx_conn.close()
    print("   Created address index")
except Exception as e:
    print(f"   Index creation skipped: {e}")

# Label sanctioned addresses
sanctioned_count = 0
for addr in SANCTIONED:
    addr_lower = addr.lower()
    try:
        cursor.execute("MATCH (n:Address {address: $addr}) SET n:Sanctioned, n.sanctioned = true", {"addr": addr_lower})
        conn.commit()
        sanctioned_count += 1
    except:
        pass
print(f"   Labeled {sanctioned_count} sanctioned addresses")

# Create transaction edges with smaller batches
print(f"   Creating {len(df):,} transaction edges...")
TX_BATCH = 200  # Smaller batches to avoid timeout
tx_data = df[['from_addr', 'to_addr', 'value', 'gas', 'block']].to_dict('records')

for i in range(0, len(tx_data), TX_BATCH):
    batch = tx_data[i:i+TX_BATCH]
    try:
        cursor.execute("""
            UNWIND $txs AS tx
            MATCH (from:Address {address: tx.from_addr})
            MATCH (to:Address {address: tx.to_addr})
            CREATE (from)-[:SENT {value: tx.value, gas: tx.gas, block: tx.block}]->(to)
        """, {"txs": batch})
        conn.commit()
    except Exception as e:
        print(f"\n   Warning at batch {i}: {e}")
        continue
    if i % 5000 == 0:
        print(f"      Transactions: {min(i+TX_BATCH, len(tx_data)):,}/{len(tx_data):,}", end='\r')

print(f"\n   Created {len(df):,} transaction edges")
print(f"   Total time: {(datetime.now()-t0).total_seconds():.1f}s")

print("\n[5/5] Running analytics queries...")

# Get statistics
cursor.execute("MATCH (n:Address) RETURN count(n) as count")
addr_count = cursor.fetchone()[0]

cursor.execute("MATCH ()-[r:SENT]->() RETURN count(r) as count")
tx_count = cursor.fetchone()[0]

cursor.execute("MATCH (n:Sanctioned) RETURN count(n) as count")
sanc_count = cursor.fetchone()[0]

cursor.execute("MATCH ()-[r:SENT]->() RETURN sum(r.value) as total")
total_value = cursor.fetchone()[0] or 0

# Find high-risk addresses (many outgoing transactions)
cursor.execute("""
    MATCH (a:Address)-[r:SENT]->()
    WITH a, count(r) as out_count, sum(r.value) as total_sent
    WHERE out_count > 10
    RETURN a.address as address, out_count, total_sent
    ORDER BY out_count DESC
    LIMIT 10
""")
high_activity = cursor.fetchall()

# Find addresses connected to sanctioned
cursor.execute("""
    MATCH (a:Address)-[r:SENT]->(s:Sanctioned)
    RETURN a.address as from_addr, s.address as to_sanctioned, sum(r.value) as total_sent
    ORDER BY total_sent DESC
    LIMIT 10
""")
sanc_connections = cursor.fetchall()

print("\n" + "=" * 60)
print("MEMGRAPH DATA SUMMARY")
print("=" * 60)
print(f"✅ Total Addresses:     {addr_count:,}")
print(f"✅ Total Transactions:  {tx_count:,}")
print(f"✅ Sanctioned Addresses: {sanc_count}")
print(f"✅ Total Value:         {total_value:,.2f} ETH")

print("\n📊 High-Activity Addresses (potential mixers/exchanges):")
for row in high_activity[:5]:
    print(f"   {row[0][:12]}... - {row[1]} txs, {row[2]:.2f} ETH")

if sanc_connections:
    print("\n🚨 Addresses Sending to Sanctioned:")
    for row in sanc_connections[:5]:
        print(f"   {row[0][:12]}... → {row[1][:12]}... ({row[2]:.4f} ETH)")
else:
    print("\n✅ No direct sanctioned connections found in sample")

print("\n" + "=" * 60)
print("DATA LOADED SUCCESSFULLY!")
print("=" * 60)
print("Access Memgraph Lab at: http://localhost:3000")
print("Graph Server health:    http://localhost:8001/health")

conn.close()
