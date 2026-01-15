"""
FRESH Memgraph Ingestion - Clear all old data and ingest BigQuery transactions
with proper labeling for fraud visualization.
"""
import pandas as pd
import mgclient
from datetime import datetime

print("="*60)
print("FRESH MEMGRAPH INGESTION")
print("="*60)
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Configuration
PARQUET_PATH = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
MEMGRAPH_HOST = "localhost"
MEMGRAPH_PORT = 7687

# ============================================================
# KNOWN ADDRESSES DATABASE
# ============================================================

SANCTIONED_ADDRESSES = {
    # Tornado Cash (OFAC sanctioned)
    "0x8589427373d6d84e98730d7795d8f6f8731fda16",
    "0x722122df12d4e14e13ac3b6895a86e84145b6967",
    "0xdd4c48c0b24039969fc16d1cdf626eab821d3384",
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",
    "0x4736dcf1b7a3d580672cce6e7c65cd5cc9cfba9d",
    "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",
    "0xa160cdab225685da1d56aa342ad8841c3b53f291",
    "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc",
    "0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936",
    "0x58e8dcc13be9780fc42e8723d8ead4cf46943df2",
    "0x178169b423a011fff22b9e3f3abea13414ddd0f1",
    "0x610b717796ad172b316836ac95a2ffad065ceab4",
    "0xba214c1c1928a32bffe790263e38b4af9bfcd659",
    "0x0836222f2b2b24a3f36f98668ed8f0b38d1a872f",
    # Lazarus Group
    "0x098b716b8aaf21512996dc57eb0615e2383e2f96",
    "0xa0e1c89ef1a489c9c7de96311ed5ce5d32c20e4b",
    "0x3cffd56b47b7b41c56258d9c7731abadc360e073",
    "0x35fb6f6db4fb05e6a4ce86f2c93691425626d4b1",
}

MIXER_ADDRESSES = {
    "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",
    "0x4736dcf1b7a3d580672cce6e7c65cd5cc9cfba9d",
    "0xdd4c48c0b24039969fc16d1cdf626eab821d3384",
    "0x0d0707963952f2fba59dd06f2b425ace40b492fe",
    "0x4bb96091ee9d802ed039c4d1a5f6216f90f81b01",
}

EXCHANGE_ADDRESSES = {
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance",
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": "Binance",
    "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance",
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase",
    "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase",
    "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43": "Coinbase",
    "0xb5d85cbf7cb3ee0d56b3bb207d5fc4b82f43f511": "Coinbase",
    "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": "Kraken",
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX",
}

DEFI_ADDRESSES = {
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "Uniswap V2",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3",
    "0xef1c6e67703c7bd7107eed8303fbe6ec2554bf6b": "Uniswap Universal",
    "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f": "SushiSwap",
    "0x1111111254fb6c44bac0bed2854e76f90643097d": "1inch",
    "0xdef1c0ded9bec7f1a1670819833240f027b25eff": "0x Exchange",
}

# Load consensus high-risk from our analysis
HIGH_RISK_ADDRESSES = set()
try:
    hr_df = pd.read_csv(r'c:\amttp\processed\consensus_high_risk.csv')
    HIGH_RISK_ADDRESSES = set(hr_df['address'].str.lower())
    print(f"Loaded {len(HIGH_RISK_ADDRESSES)} consensus high-risk addresses")
except:
    print("No consensus high-risk file found")

def get_node_label(address):
    """Determine the label(s) for an address."""
    addr = address.lower() if address else ""
    
    if addr in {a.lower() for a in SANCTIONED_ADDRESSES}:
        return "Sanctioned"
    if addr in {a.lower() for a in MIXER_ADDRESSES}:
        return "Mixer"
    if addr in {a.lower() for a in EXCHANGE_ADDRESSES}:
        return "Exchange"
    if addr in {a.lower() for a in DEFI_ADDRESSES}:
        return "DeFi"
    if addr in HIGH_RISK_ADDRESSES:
        return "HighRisk"
    return "Address"

def get_name(address):
    """Get a human-readable name if known."""
    addr = address.lower() if address else ""
    
    if addr in {a.lower() for a in SANCTIONED_ADDRESSES}:
        return "Tornado Cash / Sanctioned"
    if addr in {a.lower() for a in MIXER_ADDRESSES}:
        return "Mixer"
    
    for ex_addr, name in EXCHANGE_ADDRESSES.items():
        if addr == ex_addr.lower():
            return name
    
    for defi_addr, name in DEFI_ADDRESSES.items():
        if addr == defi_addr.lower():
            return name
    
    return None

# Connect
print(f"\nConnecting to Memgraph at {MEMGRAPH_HOST}:{MEMGRAPH_PORT}...")
conn = mgclient.connect(host=MEMGRAPH_HOST, port=MEMGRAPH_PORT)
cursor = conn.cursor()
print("Connected!")

# CLEAR ALL DATA
print("\n🗑️  Clearing ALL existing data...")
cursor.execute("MATCH (n) DETACH DELETE n")
conn.commit()
print("   Database cleared!")

# Create indexes
print("\n📑 Creating indexes...")
try:
    cursor.execute("CREATE INDEX ON :Address(address)")
    conn.commit()
except:
    pass
try:
    cursor.execute("CREATE INDEX ON :Sanctioned(address)")
    conn.commit()
except:
    pass

# Load data
print(f"\n📂 Loading transactions from {PARQUET_PATH}...")
df = pd.read_parquet(PARQUET_PATH)
print(f"   Loaded {len(df):,} transactions")

# Ingest
print("\n⏳ Ingesting transactions...")
batch_size = 500
total = len(df)
stats = {"Sanctioned": 0, "Mixer": 0, "Exchange": 0, "DeFi": 0, "HighRisk": 0, "Address": 0}

for i in range(0, total, batch_size):
    batch = df.iloc[i:i+batch_size]
    
    for _, row in batch.iterrows():
        from_addr = str(row['from_address']) if pd.notna(row['from_address']) else ""
        to_addr = str(row['to_address']) if pd.notna(row['to_address']) else ""
        
        if not from_addr or not to_addr:
            continue
        
        from_label = get_node_label(from_addr)
        to_label = get_node_label(to_addr)
        from_name = get_name(from_addr)
        to_name = get_name(to_addr)
        
        stats[from_label] = stats.get(from_label, 0) + 1
        stats[to_label] = stats.get(to_label, 0) + 1
        
        # Create/merge nodes with proper labels
        query = f"""
        MERGE (from:{from_label} {{address: $from_addr}})
        """
        if from_name:
            query += f" SET from.name = $from_name"
        
        query += f"""
        MERGE (to:{to_label} {{address: $to_addr}})
        """
        if to_name:
            query += f" SET to.name = $to_name"
        
        query += """
        CREATE (from)-[:TX {
            hash: $tx_hash,
            value: $value,
            block: $block
        }]->(to)
        """
        
        params = {
            'from_addr': from_addr,
            'to_addr': to_addr,
            'from_name': from_name,
            'to_name': to_name,
            'tx_hash': str(row['tx_hash'])[:16],  # Shortened for display
            'value': float(row['value_eth']) if pd.notna(row['value_eth']) else 0.0,
            'block': int(row['block_number']) if pd.notna(row['block_number']) else 0
        }
        
        try:
            cursor.execute(query, params)
        except Exception as e:
            pass
    
    conn.commit()
    
    if (i + batch_size) % 2000 == 0 or i + batch_size >= total:
        pct = (i + batch_size) / total * 100
        print(f"   Progress: {min(i+batch_size, total):,}/{total:,} ({pct:.0f}%)")

# Final stats
print("\n" + "="*60)
print("INGESTION COMPLETE")
print("="*60)

cursor.execute("MATCH (n) RETURN labels(n)[0] as label, count(n) as cnt ORDER BY cnt DESC")
print("\n📊 Node counts by type:")
for row in cursor.fetchall():
    emoji = {"Sanctioned": "🔴", "Mixer": "🟣", "HighRisk": "🟠", "Exchange": "🔵", "DeFi": "🟢", "Address": "⚪"}
    print(f"   {emoji.get(row[0], '⚪')} {row[0]}: {row[1]:,}")

cursor.execute("MATCH ()-[r]->() RETURN count(r)")
edges = cursor.fetchone()[0]
print(f"\n📈 Total transactions: {edges:,}")

conn.close()

print("\n" + "="*60)
print("✅ READY FOR VISUALIZATION")
print("="*60)
print("""
Open Memgraph Lab at http://localhost:3000 and run:

1️⃣ SEE THE FRAUD NETWORK:
   MATCH (s:Sanctioned)-[t:TX]-(connected)
   RETURN s, t, connected
   LIMIT 100

2️⃣ HIGH-RISK ADDRESS CONNECTIONS:
   MATCH (hr:HighRisk)-[t:TX]-(other)
   RETURN hr, t, other
   LIMIT 100

3️⃣ EXCHANGE ACTIVITY:
   MATCH (ex:Exchange)-[t:TX]-(other)
   RETURN ex, t, other
   LIMIT 50

4️⃣ FULL RISKY NETWORK:
   MATCH (n)-[t:TX]-(m)
   WHERE n:Sanctioned OR n:Mixer OR n:HighRisk
   RETURN n, t, m
   LIMIT 200
""")
