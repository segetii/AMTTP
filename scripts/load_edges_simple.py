"""Simple edge loader for Memgraph"""
import pandas as pd
import mgclient

print("Loading edges into Memgraph...")

# Connect
conn = mgclient.connect(host='127.0.0.1', port=7687)
conn.autocommit = True
cur = conn.cursor()

# Get addresses already in graph
cur.execute('MATCH (a:Address) RETURN a.id')
addr_in_graph = set(r[0] for r in cur.fetchall())
print(f"Found {len(addr_in_graph)} addresses in graph")

# Load transactions
tx = pd.read_parquet(r"C:\amttp\processed\eth_transactions_full_labeled.parquet")
print(f"Loaded {len(tx)} transactions")

# Filter to transactions between addresses we have
mask = tx['from_address'].isin(addr_in_graph) & tx['to_address'].isin(addr_in_graph)
valid_tx = tx[mask]
print(f"Found {len(valid_tx)} transactions between known addresses")

# Sample if too many
if len(valid_tx) > 10000:
    valid_tx = valid_tx.sample(10000, random_state=42)
    print(f"Sampled to {len(valid_tx)} transactions")

# Create edges
loaded = 0
errors = 0
for idx, row in valid_tx.iterrows():
    try:
        query = """
        MATCH (from:Address {id: $from_addr})
        MATCH (to:Address {id: $to_addr})
        CREATE (from)-[:TRANSFER {value_eth: $value}]->(to)
        """
        params = {
            'from_addr': str(row['from_address']),
            'to_addr': str(row['to_address']),
            'value': float(row.get('value_eth', 0)) if pd.notna(row.get('value_eth')) else 0.0
        }
        cur.execute(query, params)
        loaded += 1
        if loaded % 500 == 0:
            print(f"  Loaded {loaded} edges...")
    except Exception as e:
        errors += 1
        if errors < 3:
            print(f"  Error: {e}")

print(f"\nDone! Loaded {loaded} edges, {errors} errors")

# Verify
cur.execute('MATCH ()-[r:TRANSFER]->() RETURN count(r)')
print(f"Total TRANSFER edges in graph: {cur.fetchone()[0]}")
