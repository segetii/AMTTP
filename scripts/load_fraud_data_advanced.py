"""
AMTTP Advanced Memgraph Loader
==============================
Loads fraud detection training data into Memgraph with proper timeout handling.
This is the production-ready version with all ML scores and fraud labels.
"""
import pandas as pd
import numpy as np
from datetime import datetime
import time
import sys

# Install mgclient if needed
try:
    import mgclient
except ImportError:
    print("Installing mgclient...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pymgclient", "-q"])
    import mgclient

print("=" * 70)
print("AMTTP ADVANCED MEMGRAPH DATA LOADER")
print("=" * 70)
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Configuration
MEMGRAPH_HOST = "127.0.0.1"
MEMGRAPH_PORT = 7687
ADDRESS_BATCH = 500    # Smaller batches for addresses
TX_BATCH = 50          # Very small batches for transactions to avoid timeout
MAX_ADDRESSES = 50000  # Limit for demo
MAX_TRANSACTIONS = 50000  # Limit for demo

# Data paths
ADDR_PATH = r"C:\amttp\processed\eth_addresses_labeled.parquet"
TX_PATH = r"C:\amttp\processed\eth_transactions_full_labeled.parquet"

def get_connection():
    """Get a fresh connection to Memgraph."""
    conn = mgclient.connect(host=MEMGRAPH_HOST, port=MEMGRAPH_PORT)
    conn.autocommit = True
    return conn

def execute_single(query, params=None):
    """Execute a single query with fresh connection."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        result = cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        conn.close()
        raise e

# Step 1: Connect
print("\n[1/7] Connecting to Memgraph...")
try:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("RETURN 1")
    conn.close()
    print(f"   ✓ Connected to Memgraph at {MEMGRAPH_HOST}:{MEMGRAPH_PORT}")
except Exception as e:
    print(f"   ✗ Failed to connect: {e}")
    print("   Make sure Memgraph is running: docker-compose up -d memgraph")
    sys.exit(1)

# Step 2: Load data files
print("\n[2/7] Loading data files...")
t0 = datetime.now()

addr_df = pd.read_parquet(ADDR_PATH)
print(f"   ✓ Loaded {len(addr_df):,} addresses from {ADDR_PATH.split('/')[-1]}")
print(f"     Columns: {list(addr_df.columns)[:8]}...")

tx_df = pd.read_parquet(TX_PATH)
print(f"   ✓ Loaded {len(tx_df):,} transactions from {TX_PATH.split('/')[-1]}")
print(f"     Columns: {list(tx_df.columns)[:8]}...")

# Sample data for faster loading
if len(addr_df) > MAX_ADDRESSES:
    # Prioritize fraud addresses
    fraud_addrs = addr_df[addr_df.get('fraud', addr_df.get('is_fraud', 0)) == 1]
    non_fraud = addr_df[addr_df.get('fraud', addr_df.get('is_fraud', 0)) != 1].sample(
        n=min(MAX_ADDRESSES - len(fraud_addrs), len(addr_df) - len(fraud_addrs)),
        random_state=42
    )
    addr_df = pd.concat([fraud_addrs, non_fraud])
    print(f"   → Sampled {len(addr_df):,} addresses (keeping all {len(fraud_addrs):,} fraud)")

if len(tx_df) > MAX_TRANSACTIONS:
    tx_df = tx_df.sample(n=MAX_TRANSACTIONS, random_state=42)
    print(f"   → Sampled {len(tx_df):,} transactions")

# Step 3: Clear existing data
print("\n[3/7] Clearing existing graph data...")
try:
    execute_single("MATCH (n) DETACH DELETE n")
    print("   ✓ Cleared existing data")
except Exception as e:
    print(f"   Warning: {e}")

# Step 4: Create indexes
print("\n[4/7] Creating indexes...")
indexes = [
    "CREATE INDEX ON :Address(id)",
    "CREATE INDEX ON :Address(fraud)",
    "CREATE INDEX ON :Address(risk_level)",
    "CREATE INDEX ON :Fraud(id)",
]
for idx in indexes:
    try:
        execute_single(idx)
    except:
        pass
print("   ✓ Indexes created")

# Step 5: Load addresses
print("\n[5/7] Loading address nodes...")
start_time = time.time()
loaded = 0
errors = 0

# Detect column names
fraud_col = 'fraud' if 'fraud' in addr_df.columns else 'is_fraud' if 'is_fraud' in addr_df.columns else None
addr_col = 'address' if 'address' in addr_df.columns else 'from_address' if 'from_address' in addr_df.columns else None

if not addr_col:
    print(f"   ERROR: Cannot find address column. Available: {list(addr_df.columns)}")
    sys.exit(1)

print(f"   Using columns: address={addr_col}, fraud={fraud_col}")

for i in range(0, len(addr_df), ADDRESS_BATCH):
    batch = addr_df.iloc[i:i+ADDRESS_BATCH]
    
    for _, row in batch.iterrows():
        addr_id = str(row.get(addr_col, '')).lower()
        if not addr_id or addr_id == 'nan' or len(addr_id) < 10:
            continue
        
        # Get fraud status
        is_fraud = int(row.get(fraud_col, 0)) if fraud_col and pd.notna(row.get(fraud_col)) else 0
        
        # Get scores with defaults
        hybrid_score = float(row.get('hybrid_score', 0)) if pd.notna(row.get('hybrid_score', 0)) else 0
        xgb_score = float(row.get('xgb_normalized', row.get('xgb_score', 0))) if pd.notna(row.get('xgb_normalized', row.get('xgb_score', 0))) else 0
        risk_level = str(row.get('risk_level', 'UNKNOWN'))
        risk_class = int(row.get('risk_class', 0)) if pd.notna(row.get('risk_class', 0)) else 0
        
        # Determine labels
        labels = ['Address']
        if is_fraud == 1:
            labels.append('Fraud')
        if risk_level == 'CRITICAL':
            labels.append('Critical')
        elif risk_level == 'HIGH':
            labels.append('HighRisk')
        
        label_str = ':'.join(labels)
        
        try:
            execute_single(f"""
                CREATE (a:{label_str} {{
                    id: $id,
                    fraud: $fraud,
                    risk_level: $risk_level,
                    risk_class: $risk_class,
                    hybrid_score: $hybrid_score,
                    xgb_score: $xgb_score
                }})
            """, {
                'id': addr_id,
                'fraud': is_fraud,
                'risk_level': risk_level,
                'risk_class': risk_class,
                'hybrid_score': hybrid_score,
                'xgb_score': xgb_score
            })
            loaded += 1
        except Exception as e:
            errors += 1
            if errors < 5:
                print(f"   Warning: {e}")
    
    # Progress
    elapsed = time.time() - start_time
    rate = loaded / elapsed if elapsed > 0 else 0
    pct = (i + ADDRESS_BATCH) / len(addr_df) * 100
    print(f"   Progress: {pct:.0f}% | {loaded:,} addresses | {rate:.0f}/sec", end='\r')

print(f"\n   ✓ Loaded {loaded:,} address nodes ({errors} errors)")

# Step 6: Load transactions
print("\n[6/7] Loading transaction edges...")
start_time = time.time()
loaded_tx = 0
errors = 0

# Normalize columns
tx_df['from_addr'] = tx_df['from_address'].astype(str).str.lower()
tx_df['to_addr'] = tx_df['to_address'].astype(str).str.lower()

for i in range(0, len(tx_df), TX_BATCH):
    batch = tx_df.iloc[i:i+TX_BATCH]
    
    for _, row in batch.iterrows():
        from_addr = row['from_addr']
        to_addr = row['to_addr']
        
        if not from_addr or not to_addr or from_addr == 'nan' or to_addr == 'nan':
            continue
        
        value = float(row.get('value_eth', 0)) if pd.notna(row.get('value_eth', 0)) else 0
        block = int(row.get('block_number', 0)) if pd.notna(row.get('block_number', 0)) else 0
        tx_fraud = int(row.get('fraud', 0)) if pd.notna(row.get('fraud', 0)) else 0
        
        try:
            execute_single("""
                MATCH (from:Address {id: $from_addr})
                MATCH (to:Address {id: $to_addr})
                CREATE (from)-[:TRANSFER {value_eth: $value, block: $block, fraud: $fraud}]->(to)
            """, {
                'from_addr': from_addr,
                'to_addr': to_addr,
                'value': value,
                'block': block,
                'fraud': tx_fraud
            })
            loaded_tx += 1
        except:
            errors += 1
    
    # Progress
    elapsed = time.time() - start_time
    rate = loaded_tx / elapsed if elapsed > 0 else 0
    pct = (i + TX_BATCH) / len(tx_df) * 100
    print(f"   Progress: {pct:.0f}% | {loaded_tx:,} edges | {rate:.0f}/sec", end='\r')

print(f"\n   ✓ Loaded {loaded_tx:,} transaction edges ({errors} skipped - missing addresses)")

# Step 7: Compute metrics
print("\n[7/7] Computing graph metrics...")

# Compute degrees
try:
    execute_single("""
        MATCH (a:Address)
        OPTIONAL MATCH (a)-[out:TRANSFER]->()
        OPTIONAL MATCH ()-[in:TRANSFER]->(a)
        WITH a, count(DISTINCT out) AS out_deg, count(DISTINCT in) AS in_deg
        SET a.out_degree = out_deg, a.in_degree = in_deg
    """)
    print("   ✓ Computed degree metrics")
except Exception as e:
    print(f"   Warning: Degree computation skipped - {e}")

# Get final statistics
print("\n" + "=" * 70)
print("MEMGRAPH LOAD COMPLETE")
print("=" * 70)

try:
    result = execute_single("MATCH (a:Address) RETURN count(a)")
    print(f"   Total Addresses:     {result[0][0]:,}")
    
    result = execute_single("MATCH (f:Fraud) RETURN count(f)")
    print(f"   Fraud Addresses:     {result[0][0]:,}")
    
    result = execute_single("MATCH (h:HighRisk) RETURN count(h)")
    print(f"   High-Risk Addresses: {result[0][0]:,}")
    
    result = execute_single("MATCH (c:Critical) RETURN count(c)")
    print(f"   Critical Addresses:  {result[0][0]:,}")
    
    result = execute_single("MATCH ()-[t:TRANSFER]->() RETURN count(t)")
    print(f"   Total Transactions:  {result[0][0]:,}")
    
    result = execute_single("MATCH ()-[t:TRANSFER]->() RETURN sum(t.value_eth)")
    total_val = result[0][0] if result[0][0] else 0
    print(f"   Total Value:         {total_val:,.2f} ETH")
except Exception as e:
    print(f"   Stats error: {e}")

print(f"""

USEFUL CYPHER QUERIES FOR MEMGRAPH LAB:
=======================================

1. View all fraud addresses:
   MATCH (f:Fraud) RETURN f LIMIT 100

2. Find high-risk network:
   MATCH (a:HighRisk)-[t:TRANSFER]-(b) 
   RETURN a, t, b LIMIT 200

3. Transactions to fraud addresses:
   MATCH (a:Address)-[t:TRANSFER]->(f:Fraud)
   RETURN a.id, t.value_eth, f.id LIMIT 50

4. Top risk scores:
   MATCH (a:Address) WHERE a.hybrid_score > 50
   RETURN a.id, a.hybrid_score, a.risk_level
   ORDER BY a.hybrid_score DESC LIMIT 20

5. Fraud clusters (2-hop):
   MATCH p=(a:Address)-[:TRANSFER*1..2]-(f:Fraud)
   RETURN p LIMIT 300

ACCESS POINTS:
==============
- Memgraph Lab:    http://localhost:3000
- Graph Server:    http://localhost:8001/health
- Dashboard:       http://localhost:3006

Done! Total time: {(datetime.now() - t0).total_seconds():.1f}s
""")
