"""
Load Fraud Detection Data into Memgraph
========================================
Loads the transaction data with fraud labels and model scores into Memgraph.

Creates:
- Address nodes with fraud scores and labels
- Transaction edges with risk levels
- Fraud cluster detection
"""
import pandas as pd
import numpy as np
from datetime import datetime
import time
import sys

# Try to import mgclient (Memgraph Python driver)
try:
    import mgclient
    HAVE_MGCLIENT = True
except ImportError:
    print("mgclient not installed. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pymgclient", "-q"])
    import mgclient
    HAVE_MGCLIENT = True

print("="*70)
print("LOADING FRAUD DETECTION DATA INTO MEMGRAPH")
print("="*70)
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Configuration
MEMGRAPH_HOST = "127.0.0.1"
MEMGRAPH_PORT = 7687
BATCH_SIZE = 1000

# Connect to Memgraph
print("\n[1/6] Connecting to Memgraph...")
try:
    conn = mgclient.connect(host=MEMGRAPH_HOST, port=MEMGRAPH_PORT)
    conn.autocommit = True
    cursor = conn.cursor()
    print(f"   ✓ Connected to Memgraph at {MEMGRAPH_HOST}:{MEMGRAPH_PORT}")
except Exception as e:
    print(f"   ✗ Failed to connect: {e}")
    print("   Make sure Memgraph is running: docker-compose up -d memgraph")
    sys.exit(1)

# Helper function
def execute(query, params=None):
    """Execute a Cypher query."""
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor.fetchall()
    except Exception as e:
        print(f"Query error: {e}")
        return []

# Load data
print("\n[2/6] Loading data files...")

# Load address features with fraud labels
addr_df = pd.read_parquet('c:/amttp/processed/eth_addresses_labeled.parquet')
print(f"   ✓ Loaded {len(addr_df):,} addresses with labels")

# Load transactions
tx_df = pd.read_parquet('c:/amttp/processed/eth_transactions_full_labeled.parquet')
print(f"   ✓ Loaded {len(tx_df):,} transactions")

# Check columns
print(f"\n   Address columns: {list(addr_df.columns)[:10]}...")
print(f"   Transaction columns: {list(tx_df.columns)[:10]}...")

# Setup schema
print("\n[3/6] Setting up graph schema...")

schema_queries = [
    "CREATE INDEX ON :Address(id);",
    "CREATE INDEX ON :Address(fraud);",
    "CREATE INDEX ON :Address(risk_level);",
    "CREATE INDEX ON :Address(hybrid_score);",
    "CREATE INDEX ON :Transaction(tx_hash);",
]

for q in schema_queries:
    try:
        execute(q)
    except:
        pass  # Index may already exist

print("   ✓ Indexes created")

# Clear existing data (optional - comment out to append)
print("\n[4/6] Loading address nodes...")

# Prepare address data
addr_data = addr_df.copy()

# Handle missing columns gracefully
def get_col(df, col, default=0):
    return df[col].fillna(default).values if col in df.columns else [default] * len(df)

# Load addresses in batches
total_addrs = len(addr_data)
loaded_addrs = 0
start_time = time.time()

for i in range(0, total_addrs, BATCH_SIZE):
    batch = addr_data.iloc[i:i+BATCH_SIZE]
    
    for _, row in batch.iterrows():
        addr_id = str(row.get('address', '')).lower()
        if not addr_id or addr_id == 'nan':
            continue
            
        # Build properties
        props = {
            'id': addr_id,
            'fraud': int(row.get('fraud', 0)),
            'risk_level': str(row.get('risk_level', 'UNKNOWN')),
            'risk_class': int(row.get('risk_class', 0)) if pd.notna(row.get('risk_class')) else 0,
            'hybrid_score': float(row.get('hybrid_score', 0)) if pd.notna(row.get('hybrid_score')) else 0,
            'xgb_score': float(row.get('xgb_normalized', 0)) if pd.notna(row.get('xgb_normalized')) else 0,
            'sophisticated_score': float(row.get('sophisticated_score', 0)) if pd.notna(row.get('sophisticated_score')) else 0,
            'sent_count': int(row.get('sent_count', 0)) if pd.notna(row.get('sent_count')) else 0,
            'received_count': int(row.get('received_count', 0)) if pd.notna(row.get('received_count')) else 0,
            'total_sent': float(row.get('total_sent', 0)) if pd.notna(row.get('total_sent')) else 0,
            'total_received': float(row.get('total_received', 0)) if pd.notna(row.get('total_received')) else 0,
            'balance': float(row.get('balance', 0)) if pd.notna(row.get('balance')) else 0,
        }
        
        # Create node with appropriate labels
        labels = ['Address']
        if props['fraud'] == 1:
            labels.append('Fraud')
        if props['risk_level'] == 'CRITICAL':
            labels.append('Critical')
        elif props['risk_level'] == 'HIGH':
            labels.append('HighRisk')
            
        label_str = ':'.join(labels)
        
        query = f"""
        MERGE (a:{label_str} {{id: $id}})
        SET a.fraud = $fraud,
            a.risk_level = $risk_level,
            a.risk_class = $risk_class,
            a.hybrid_score = $hybrid_score,
            a.xgb_score = $xgb_score,
            a.sophisticated_score = $sophisticated_score,
            a.sent_count = $sent_count,
            a.received_count = $received_count,
            a.total_sent = $total_sent,
            a.total_received = $total_received,
            a.balance = $balance
        """
        
        try:
            execute(query, props)
            loaded_addrs += 1
        except Exception as e:
            pass  # Skip problematic addresses
    
    # Progress update
    if (i // BATCH_SIZE) % 50 == 0:
        progress = (i + BATCH_SIZE) / total_addrs * 100
        elapsed = time.time() - start_time
        rate = loaded_addrs / elapsed if elapsed > 0 else 0
        print(f"   Progress: {progress:.1f}% | {loaded_addrs:,} addresses | {rate:.0f} addr/sec")

print(f"   ✓ Loaded {loaded_addrs:,} address nodes")

# Load transactions (sample for speed - full load takes a while)
print("\n[5/6] Loading transaction edges...")

# Sample transactions for faster loading (or load all)
MAX_TX = 20000  # Load 20,000 transactions for realistic visualization
tx_sample = tx_df.head(MAX_TX) if len(tx_df) > MAX_TX else tx_df

total_tx = len(tx_sample)
loaded_tx = 0
start_time = time.time()

for i in range(0, total_tx, BATCH_SIZE):
    batch = tx_sample.iloc[i:i+BATCH_SIZE]
    
    for _, row in batch.iterrows():
        from_addr = str(row.get('from_address', '')).lower()
        to_addr = str(row.get('to_address', '')).lower()
        
        if not from_addr or not to_addr or from_addr == 'nan' or to_addr == 'nan':
            continue
        
        props = {
            'from_addr': from_addr,
            'to_addr': to_addr,
            'tx_hash': str(row.get('tx_hash', '')),
            'value_eth': float(row.get('value_eth', 0)) if pd.notna(row.get('value_eth')) else 0,
            'block_number': int(row.get('block_number', 0)) if pd.notna(row.get('block_number')) else 0,
            'gas_price': float(row.get('gas_price_gwei', 0)) if pd.notna(row.get('gas_price_gwei')) else 0,
            'fraud': int(row.get('fraud', 0)) if pd.notna(row.get('fraud')) else 0,
        }
        
        query = """
        MATCH (from:Address {id: $from_addr})
        MATCH (to:Address {id: $to_addr})
        CREATE (from)-[t:TRANSFER {
            tx_hash: $tx_hash,
            value_eth: $value_eth,
            block_number: $block_number,
            gas_price: $gas_price,
            fraud: $fraud
        }]->(to)
        """
        
        try:
            execute(query, props)
            loaded_tx += 1
        except:
            pass
    
    # Progress update
    if (i // BATCH_SIZE) % 20 == 0:
        progress = (i + BATCH_SIZE) / total_tx * 100
        elapsed = time.time() - start_time
        rate = loaded_tx / elapsed if elapsed > 0 else 0
        print(f"   Progress: {progress:.1f}% | {loaded_tx:,} transactions | {rate:.0f} tx/sec")

print(f"   ✓ Loaded {loaded_tx:,} transaction edges")

# Compute graph metrics
print("\n[6/6] Computing graph metrics and fraud patterns...")

# Compute degree for all nodes
degree_query = """
MATCH (a:Address)
OPTIONAL MATCH (a)-[out:TRANSFER]->()
OPTIONAL MATCH ()-[in:TRANSFER]->(a)
WITH a, count(DISTINCT out) AS out_deg, count(DISTINCT in) AS in_deg
SET a.out_degree = out_deg,
    a.in_degree = in_deg
RETURN count(a)
"""
result = execute(degree_query)
print(f"   ✓ Computed degree for {result[0][0] if result else 0} addresses")

# Find fraud clusters (addresses connected to fraud)
fraud_cluster_query = """
MATCH (f:Fraud)-[:TRANSFER*1..2]-(a:Address)
WHERE NOT a:Fraud
SET a.fraud_proximity = true
RETURN count(DISTINCT a)
"""
try:
    result = execute(fraud_cluster_query)
    print(f"   ✓ Marked {result[0][0] if result else 0} addresses with fraud proximity")
except:
    pass

# Get final stats
print("\n" + "="*70)
print("MEMGRAPH LOAD COMPLETE")
print("="*70)

stats_query = """
MATCH (a:Address)
RETURN 
    count(a) AS total_addresses,
    sum(CASE WHEN a.fraud = 1 THEN 1 ELSE 0 END) AS fraud_addresses,
    sum(CASE WHEN a.fraud_proximity = true THEN 1 ELSE 0 END) AS fraud_proximate
"""
result = execute(stats_query)
if result:
    print(f"\n   Total Addresses:     {result[0][0]:,}")
    print(f"   Fraud Addresses:     {result[0][1]:,}")
    print(f"   Fraud Proximate:     {result[0][2]:,}")

edge_query = "MATCH ()-[t:TRANSFER]->() RETURN count(t)"
result = execute(edge_query)
print(f"   Total Transactions:  {result[0][0]:,}" if result else "")

print(f"""
   
USEFUL CYPHER QUERIES FOR MEMGRAPH LAB:
=======================================

1. View fraud addresses:
   MATCH (f:Fraud) RETURN f LIMIT 50

2. Find transactions to fraud addresses:
   MATCH (a:Address)-[t:TRANSFER]->(f:Fraud)
   RETURN a, t, f LIMIT 100

3. Find high-risk addresses:
   MATCH (a:Address) WHERE a.hybrid_score > 70
   RETURN a.id, a.hybrid_score, a.risk_level
   ORDER BY a.hybrid_score DESC LIMIT 20

4. Visualize fraud network:
   MATCH p=(a:Address)-[:TRANSFER*1..3]-(f:Fraud)
   RETURN p LIMIT 200

5. Find addresses connected to multiple frauds:
   MATCH (a:Address)-[:TRANSFER]-(f:Fraud)
   WITH a, count(DISTINCT f) AS fraud_connections
   WHERE fraud_connections > 1
   RETURN a.id, fraud_connections
   ORDER BY fraud_connections DESC

Open Memgraph Lab at: http://localhost:3000
""")

conn.close()
print("Done!")
