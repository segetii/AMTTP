"""
AMTTP Memgraph Ingestion Service (Production)
==============================================
Reads transactions from MongoDB (production data store) → Polars for
parallel aggregation → Memgraph via neo4j bolt driver.

Polars patterns adapted from sophisticated_fraud_detection_ultra.py:
  - Lazy group_by aggregation across all cores (Rust-based, zero-copy)
  - Vectorised column transforms (no Python loops in hot path)

All config via environment variables for Docker / CI compatibility.

Graph Schema:
  (:Address {id, first_seen, last_seen, tx_count, total_sent, total_received,
             in_degree, out_degree, fraud_flag})
  (:Address)-[:TRANSFER {tx_hash, value, ts, block, gas_price, gas_used}]->(:Address)
  Labels: :Sanctioned, :Mixer, :Exchange, :DeFi

Usage:
  # Local
  py -3 scripts/ingest_memgraph_fast.py

  # Docker / CI (env-var overrides)
  MONGO_URI=mongodb://mongo:27017 MEMGRAPH_URI=bolt://memgraph:7687 python ingest_memgraph_fast.py
"""
import os, sys, time, io, logging
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("memgraph-ingest")

print("=" * 70)
print("AMTTP MEMGRAPH INGESTION (Polars + MongoDB → neo4j bolt)")
print("=" * 70)
print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
overall_t0 = time.perf_counter()

# ── Dependencies ────────────────────────────────────────────────────────────
import polars as pl
from pymongo import MongoClient
from neo4j import GraphDatabase

print(f"Polars {pl.__version__} | Engine: POLARS (Rust, parallel)")

# ── Configuration (env-var overrides for Docker) ────────────────────────────
MONGO_URI        = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB         = os.getenv("MONGO_DB", "amttp")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "transactions")
MEMGRAPH_URI     = os.getenv("MEMGRAPH_URI", "bolt://localhost:7687")
NODE_BATCH       = int(os.getenv("NODE_BATCH", "5000"))
EDGE_BATCH       = int(os.getenv("EDGE_BATCH", "2000"))

print(f"MongoDB: {MONGO_URI}/{MONGO_DB}.{MONGO_COLLECTION}")
print(f"Memgraph: {MEMGRAPH_URI}")

# Known address labels (exchanges, mixers, sanctioned, DeFi)
KNOWN_LABELS = {
    # Exchanges
    "0x28c6c06298d514db089934071355e5743bf21d60": ("Exchange", "Binance Hot"),
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": ("Exchange", "Binance"),
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": ("Exchange", "Binance"),
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": ("Exchange", "Coinbase"),
    "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43": ("Exchange", "Coinbase"),
    "0x503828976d22510aad0201ac7ec88293211d23da": ("Exchange", "Coinbase"),
    "0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503": ("Exchange", "Binance US"),
    # Mixers (Tornado Cash)
    "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf": ("Mixer", "Tornado Cash 0.1"),
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b": ("Mixer", "Tornado Cash 1"),
    "0x4736dcf1b7a3d580672cce6e7c65cd5cc9cfba9d": ("Mixer", "Tornado Cash 10"),
    "0xa160cdab225685da1d56aa342ad8841c3b53f291": ("Mixer", "Tornado Cash 100"),
    "0x722122df12d4e14e13ac3b6895a86e84145b6967": ("Mixer", "Tornado Cash Router"),
    # OFAC Sanctioned
    "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c": ("Sanctioned", "OFAC"),
    "0xd882cfc20f52f2599d84b8e8d58c7fb62cfe344b": ("Sanctioned", "OFAC"),
    "0x7f367cc41522ce07553e823bf3be79a889debe1b": ("Sanctioned", "OFAC"),
    "0x72a5843cc08275c8171e582972aa4fda8c397b2a": ("Sanctioned", "Lazarus"),
    "0xa7e5d5a720f06526557c513402f2e6b5fa20b008": ("Sanctioned", "Lazarus"),
    "0x098b716b8aaf21512996dc57eb0615e2383e2f96": ("Sanctioned", "OFAC"),
    "0x8589427373d6d84e98730d7795d8f6f8731fda16": ("Sanctioned", "OFAC"),
    "0xdd4c48c0b24039969fc16d1cdf626eab821d3384": ("Sanctioned", "OFAC"),
    "0xa0e1c89ef1a489c9c7de96311ed5ce5d32c20e4b": ("Sanctioned", "OFAC"),
    "0x35fb6f6db4fb05e6a4ce86f2c93691425626d4b1": ("Sanctioned", "OFAC"),
    # DeFi
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": ("DeFi", "Uniswap V2"),
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": ("DeFi", "Uniswap V3"),
    "0xdef1c0ded9bec7f1a1670819833240f027b25eff": ("DeFi", "0x Exchange"),
    "0x1111111254fb6c44bac0bed2854e76f90643097d": ("DeFi", "1inch"),
    "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f": ("DeFi", "SushiSwap"),
}


# =============================================================================
# [1/6] LOAD FROM MONGODB → POLARS
# =============================================================================
print("\n[1/6] Reading from MongoDB...")
t0 = time.perf_counter()

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
# Verify connection
client.admin.command("ping")
db = client[MONGO_DB]
coll = db[MONGO_COLLECTION]

total_docs = coll.estimated_document_count()
print(f"   Collection has ~{total_docs:,} documents")

# Project only needed fields (reduces wire transfer ~60%)
projection = {
    "_id": 0, "hash": 1, "from": 1, "to": 1, "valueEth": 1,
    "timestamp": 1, "blockNumber": 1, "gasPriceGwei": 1, "gasUsed": 1,
    "fraud": 1, "senderFraud": 1, "receiverFraud": 1,
}

# Stream with batch_size hint for server-side cursor efficiency
docs = list(coll.find({}, projection).batch_size(50000))
mongo_time = time.perf_counter() - t0
print(f"   Fetched {len(docs):,} documents in {mongo_time:.2f}s ({len(docs)/mongo_time:,.0f} docs/s)")

# Convert to Polars DataFrame (fast dict-of-lists path)
t1 = time.perf_counter()
df = pl.DataFrame(docs)
print(f"   Polars DataFrame: {df.shape[0]:,} x {df.shape[1]} in {time.perf_counter()-t1:.3f}s")
client.close()

# =============================================================================
# [2/6] CLEAN & TRANSFORM (Polars vectorised — zero Python loops)
# =============================================================================
print("\n[2/6] Cleaning data (Polars parallel)...")
t0 = time.perf_counter()
orig_count = df.shape[0]

df = df.with_columns([
    pl.col("from").str.to_lowercase().alias("from_addr"),
    pl.col("to").str.to_lowercase().alias("to_addr"),
    pl.col("valueEth").cast(pl.Float64).fill_null(0.0).alias("value"),
    pl.col("timestamp").str.to_datetime("%Y-%m-%d %H:%M:%S%z", time_zone="UTC")
      .dt.epoch("s").cast(pl.Int64).fill_null(0).alias("ts"),
    pl.col("blockNumber").cast(pl.Int64).fill_null(0).alias("block"),
    pl.col("gasPriceGwei").cast(pl.Float64).fill_null(0.0).alias("gas_price"),
    pl.col("gasUsed").cast(pl.Int64).fill_null(0).alias("gas_used"),
    pl.col("fraud").cast(pl.Int32).fill_null(0).alias("fraud_flag"),
    pl.col("senderFraud").cast(pl.Int32).fill_null(0).alias("sender_fraud"),
    pl.col("receiverFraud").cast(pl.Int32).fill_null(0).alias("receiver_fraud"),
]).filter(
    pl.col("to_addr").is_not_null() & (pl.col("to_addr") != "")
)

clean_count = df.shape[0]
print(f"   {orig_count:,} -> {clean_count:,} (dropped {orig_count - clean_count:,} null to-address)")
print(f"   Cleaned in {time.perf_counter()-t0:.3f}s")

# =============================================================================
# [3/6] PRE-COMPUTE ADDRESS AGGREGATES (Single Polars pass, parallel)
# =============================================================================
print("\n[3/6] Computing address aggregates (parallel)...")
t0 = time.perf_counter()

# Sender aggregates
sender_agg = df.lazy().group_by("from_addr").agg([
    pl.len().alias("out_tx_count"),
    pl.col("value").sum().alias("total_sent"),
    pl.col("ts").min().alias("first_seen_as_sender"),
    pl.col("ts").max().alias("last_seen_as_sender"),
    pl.col("sender_fraud").max().alias("sender_fraud_flag"),
]).collect()

# Receiver aggregates
receiver_agg = df.lazy().group_by("to_addr").agg([
    pl.len().alias("in_tx_count"),
    pl.col("value").sum().alias("total_received"),
    pl.col("ts").min().alias("first_seen_as_receiver"),
    pl.col("ts").max().alias("last_seen_as_receiver"),
    pl.col("receiver_fraud").max().alias("receiver_fraud_flag"),
]).collect()

# Merge into unified address table
# Rename to have a common join key
sender_agg = sender_agg.rename({"from_addr": "address"})
receiver_agg = receiver_agg.rename({"to_addr": "address"})

addr_df = sender_agg.join(receiver_agg, on="address", how="full", coalesce=True)

# Fill nulls and compute final properties
addr_df = addr_df.with_columns([
    pl.col("out_tx_count").fill_null(0).alias("out_degree"),
    pl.col("in_tx_count").fill_null(0).alias("in_degree"),
    pl.col("total_sent").fill_null(0.0),
    pl.col("total_received").fill_null(0.0),
    pl.when(pl.col("sender_fraud_flag").is_not_null())
      .then(pl.col("sender_fraud_flag"))
      .otherwise(pl.col("receiver_fraud_flag").fill_null(0))
      .alias("fraud_flag"),
]).with_columns([
    (pl.col("out_degree") + pl.col("in_degree")).alias("tx_count"),
    pl.min_horizontal("first_seen_as_sender", "first_seen_as_receiver").alias("first_seen"),
    pl.max_horizontal("last_seen_as_sender", "last_seen_as_receiver").alias("last_seen"),
])

print(f"   {addr_df.shape[0]:,} unique addresses computed in {time.perf_counter()-t0:.3f}s")
print(f"   Fraud-flagged addresses: {addr_df.filter(pl.col('fraud_flag') > 0).shape[0]:,}")

# =============================================================================
# [4/6] CLEAR MEMGRAPH & CREATE NODES
# =============================================================================
print("\n[4/6] Loading into Memgraph...")
t0 = time.perf_counter()

driver = GraphDatabase.driver(MEMGRAPH_URI)

# Clear existing data
with driver.session() as session:
    session.run("MATCH (n) DETACH DELETE n")
    print("   Cleared existing graph data")

# Create index first (on empty graph = instant)
with driver.session() as session:
    try:
        session.run("CREATE INDEX ON :Address(id)")
    except Exception:
        pass  # already exists
    print("   Index on :Address(id) ready")

# Batch-create address nodes with pre-computed properties
addr_records = addr_df.select([
    "address", "out_degree", "in_degree", "tx_count",
    "total_sent", "total_received", "first_seen", "last_seen", "fraud_flag",
]).to_dicts()

print(f"   Creating {len(addr_records):,} address nodes...")

for i in range(0, len(addr_records), NODE_BATCH):
    batch = addr_records[i:i + NODE_BATCH]
    with driver.session() as session:
        session.run("""
            UNWIND $nodes AS n
            CREATE (a:Address {
                id: n.address,
                out_degree: n.out_degree,
                in_degree: n.in_degree,
                tx_count: n.tx_count,
                total_sent: n.total_sent,
                total_received: n.total_received,
                first_seen: n.first_seen,
                last_seen: n.last_seen,
                fraud_flag: n.fraud_flag
            })
        """, nodes=batch)
    done = min(i + NODE_BATCH, len(addr_records))
    if i % 20000 == 0 or done == len(addr_records):
        print(f"      Nodes: {done:,}/{len(addr_records):,}")

node_time = time.perf_counter() - t0
print(f"   {len(addr_records):,} nodes created in {node_time:.1f}s")

# Label known addresses
print("   Labeling known addresses...")
with driver.session() as session:
    for addr, (label, name) in KNOWN_LABELS.items():
        session.run(
            f"MATCH (a:Address {{id: $addr}}) SET a:{label}, a.name = $name",
            addr=addr, name=name,
        )
print(f"   Labeled {len(KNOWN_LABELS)} known addresses")

# =============================================================================
# [5/6] CREATE EDGES (TRANSFER relationships)
# =============================================================================
print("\n[5/6] Creating transaction edges...")
t0 = time.perf_counter()

# Prepare edge data from Polars (fast column extraction)
edge_df = df.select([
    pl.col("hash").alias("tx_hash"),
    "from_addr", "to_addr", "value", "ts", "block", "gas_price", "gas_used",
])
edge_records = edge_df.to_dicts()

print(f"   Creating {len(edge_records):,} TRANSFER edges...")

for i in range(0, len(edge_records), EDGE_BATCH):
    batch = edge_records[i:i + EDGE_BATCH]
    with driver.session() as session:
        session.run("""
            UNWIND $txs AS tx
            MATCH (f:Address {id: tx.from_addr})
            MATCH (t:Address {id: tx.to_addr})
            CREATE (f)-[:TRANSFER {
                tx_hash: tx.tx_hash,
                value: tx.value,
                ts: tx.ts,
                block: tx.block,
                gas_price: tx.gas_price,
                gas_used: tx.gas_used
            }]->(t)
        """, txs=batch)
    done = min(i + EDGE_BATCH, len(edge_records))
    if i % 20000 == 0 or done == len(edge_records):
        elapsed = time.perf_counter() - t0
        rate = done / elapsed if elapsed > 0 else 0
        print(f"      Edges: {done:,}/{len(edge_records):,}  ({rate:,.0f} edges/s)")

edge_time = time.perf_counter() - t0
print(f"   {len(edge_records):,} edges created in {edge_time:.1f}s")

# =============================================================================
# [6/6] POST-INGESTION ANALYTICS
# =============================================================================
print("\n[6/6] Running graph analytics...")
t0 = time.perf_counter()

with driver.session() as session:
    # Mark mixer-exposed addresses (1-2 hop from mixer)
    try:
        r = session.run("""
            MATCH (m:Mixer)
            MATCH (a:Address)-[:TRANSFER*1..2]-(m)
            WHERE NOT a:Mixer
            SET a.mixer_exposure = true
            RETURN count(DISTINCT a) AS cnt
        """).single()
        print(f"   Mixer-exposed: {r['cnt']} addresses")
    except Exception as e:
        print(f"   Mixer exposure calc skipped: {e}")

    # Mark sanction-proximate (1-3 hops)
    try:
        r = session.run("""
            MATCH (s:Sanctioned)
            MATCH (a:Address)-[:TRANSFER*1..3]-(s)
            WHERE NOT a:Sanctioned
            SET a.sanction_proximity = true
            RETURN count(DISTINCT a) AS cnt
        """).single()
        print(f"   Sanction-proximate: {r['cnt']} addresses")
    except Exception as e:
        print(f"   Sanction proximity calc skipped: {e}")

    # Detect loops (A→B→A)
    try:
        r = session.run("""
            MATCH (a:Address)-[:TRANSFER]->(b:Address)-[:TRANSFER]->(a)
            WHERE a.id < b.id
            RETURN count(*) AS loops
        """).single()
        print(f"   Circular transfers (A<->B): {r['loops']}")
    except Exception as e:
        print(f"   Loop detection skipped: {e}")

    # Final stats
    stats = session.run("""
        MATCH (n:Address) WITH count(n) AS nodes
        MATCH ()-[r:TRANSFER]->() WITH nodes, count(r) AS edges
        RETURN nodes, edges
    """).single()
    n_nodes = stats["nodes"]
    n_edges = stats["edges"]

print(f"   Analytics in {time.perf_counter()-t0:.1f}s")

driver.close()

# =============================================================================
# SUMMARY
# =============================================================================
total_time = time.perf_counter() - overall_t0
print("\n" + "=" * 70)
print("MEMGRAPH INGESTION COMPLETE")
print("=" * 70)
print(f"  Addresses (nodes):  {n_nodes:,}")
print(f"  Transactions (edges): {n_edges:,}")
print(f"  Fraud-flagged:      {addr_df.filter(pl.col('fraud_flag') > 0).shape[0]:,}")
print(f"  Known labels:       {len(KNOWN_LABELS)}")
print(f"  Total time:         {total_time:.1f}s")
print(f"  Throughput:         {n_edges / total_time:,.0f} edges/s")
print("=" * 70)
