"""
AMTTP - Memgraph Data Ingestion

Loads Ethereum transaction data into Memgraph graph database.

Graph Schema:
- (Address) nodes with properties: id, first_seen, last_seen, tx_count, total_sent, total_received
- (Address)-[:TRANSFER]->(Address) edges with: tx_hash, value, timestamp, block, gas_price, gas_used
- Labels: :Exchange, :Mixer, :Sanctioned, :DeFi for special addresses
"""
import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Add parent to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "ml" / "Automation"))

from ml_pipeline.graph.service import MemgraphService, get_memgraph_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Known address labels
KNOWN_ADDRESSES = {
    # Exchanges
    "0x28c6c06298d514db089934071355e5743bf21d60": ("Exchange", "Binance Hot Wallet"),
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": ("Exchange", "Binance"),
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": ("Exchange", "Binance"),
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": ("Exchange", "Coinbase"),
    "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43": ("Exchange", "Coinbase"),
    "0x503828976d22510aad0201ac7ec88293211d23da": ("Exchange", "Coinbase"),
    "0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503": ("Exchange", "Binance US"),
    
    # Mixers (Tornado Cash related - sanctioned)
    "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf": ("Mixer", "Tornado Cash 0.1 ETH"),
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b": ("Mixer", "Tornado Cash 1 ETH"),
    "0x4736dcf1b7a3d580672cce6e7c65cd5cc9cfba9d": ("Mixer", "Tornado Cash 10 ETH"),
    "0xa160cdab225685da1d56aa342ad8841c3b53f291": ("Mixer", "Tornado Cash 100 ETH"),
    
    # Sanctioned addresses (OFAC)
    "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c": ("Sanctioned", "OFAC Sanctioned"),
    "0xd882cfc20f52f2599d84b8e8d58c7fb62cfe344b": ("Sanctioned", "OFAC Sanctioned"),
    "0x7f367cc41522ce07553e823bf3be79a889debe1b": ("Sanctioned", "OFAC Sanctioned"),
    "0x72a5843cc08275c8171e582972aa4fda8c397b2a": ("Sanctioned", "Lazarus Group"),
    "0xa7e5d5a720f06526557c513402f2e6b5fa20b008": ("Sanctioned", "Lazarus Group"),
    
    # DeFi Protocols
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": ("DeFi", "Uniswap V2 Router"),
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": ("DeFi", "Uniswap V3 Router"),
    "0xdef1c0ded9bec7f1a1670819833240f027b25eff": ("DeFi", "0x Exchange"),
    "0x1111111254fb6c44bac0bed2854e76f90643097d": ("DeFi", "1inch Router"),
    "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f": ("DeFi", "SushiSwap Router"),
}


class MemgraphIngester:
    """Ingest Ethereum transactions into Memgraph."""
    
    def __init__(self, service: Optional[MemgraphService] = None):
        self.service = service or get_memgraph_service()
        self._setup_schema()
    
    def _setup_schema(self):
        """Create indexes and constraints for performance."""
        schema_queries = [
            # Indexes
            "CREATE INDEX ON :Address(id);",
            "CREATE INDEX ON :Address(first_seen);",
            "CREATE INDEX ON :Address(tx_count);",
            # Note: Memgraph doesn't support all Neo4j constraint types
        ]
        
        for query in schema_queries:
            try:
                self.service.execute(query)
            except Exception as e:
                logger.debug(f"Schema setup (may already exist): {e}")
    
    def clear_graph(self):
        """Clear all data from the graph."""
        logger.warning("Clearing all graph data...")
        self.service.execute("MATCH (n) DETACH DELETE n;")
        logger.info("Graph cleared")
    
    def add_known_addresses(self):
        """Add known addresses with labels."""
        logger.info("Adding known address labels...")
        
        for address, (label, name) in KNOWN_ADDRESSES.items():
            query = f"""
            MERGE (a:Address {{id: $addr}})
            SET a:{label}, a.name = $name
            RETURN a.id
            """
            try:
                self.service.execute(query, {"addr": address, "name": name})
            except Exception as e:
                logger.debug(f"Failed to add {address}: {e}")
        
        logger.info(f"Added {len(KNOWN_ADDRESSES)} known addresses")
    
    def ingest_transactions(
        self,
        transactions: List[Dict[str, Any]],
        batch_size: int = 500,
    ) -> Dict[str, int]:
        """
        Ingest transactions into Memgraph.
        
        Args:
            transactions: List of transaction dicts
            batch_size: Number of transactions per batch
            
        Returns:
            Statistics dict
        """
        total = len(transactions)
        logger.info(f"Ingesting {total} transactions...")
        
        stats = {
            "total": total,
            "ingested": 0,
            "errors": 0,
            "addresses": set(),
            "time_ms": 0,
        }
        
        start_time = time.time()
        
        # Process in batches
        for i in range(0, total, batch_size):
            batch = transactions[i:i + batch_size]
            
            # Build batch query using UNWIND
            query = """
            UNWIND $txs AS tx
            
            MERGE (from:Address {id: tx.from_address})
            ON CREATE SET 
                from.first_seen = tx.timestamp,
                from.last_seen = tx.timestamp,
                from.tx_count = 1,
                from.total_sent = tx.value_eth,
                from.total_received = 0.0
            ON MATCH SET 
                from.first_seen = CASE WHEN from.first_seen > tx.timestamp THEN tx.timestamp ELSE from.first_seen END,
                from.last_seen = CASE WHEN from.last_seen < tx.timestamp THEN tx.timestamp ELSE from.last_seen END,
                from.tx_count = coalesce(from.tx_count, 0) + 1,
                from.total_sent = coalesce(from.total_sent, 0) + tx.value_eth
            
            MERGE (to:Address {id: tx.to_address})
            ON CREATE SET 
                to.first_seen = tx.timestamp,
                to.last_seen = tx.timestamp,
                to.tx_count = 1,
                to.total_sent = 0.0,
                to.total_received = tx.value_eth
            ON MATCH SET 
                to.first_seen = CASE WHEN to.first_seen > tx.timestamp THEN tx.timestamp ELSE to.first_seen END,
                to.last_seen = CASE WHEN to.last_seen < tx.timestamp THEN tx.timestamp ELSE to.last_seen END,
                to.tx_count = coalesce(to.tx_count, 0) + 1,
                to.total_received = coalesce(to.total_received, 0) + tx.value_eth
            
            CREATE (from)-[t:TRANSFER {
                tx_hash: tx.tx_hash,
                value: tx.value_eth,
                ts: tx.timestamp,
                block: tx.block_number,
                gas_price: tx.gas_price_gwei,
                gas_used: tx.gas_used
            }]->(to)
            
            RETURN count(t) AS created
            """
            
            # Format transactions for query
            tx_data = [
                {
                    "tx_hash": tx.get("tx_hash", ""),
                    "from_address": tx.get("from_address", "").lower(),
                    "to_address": tx.get("to_address", "").lower(),
                    "value_eth": float(tx.get("value_eth", 0)),
                    "timestamp": int(tx.get("timestamp", 0)),
                    "block_number": int(tx.get("block_number", 0)),
                    "gas_price_gwei": float(tx.get("gas_price_gwei", 0)),
                    "gas_used": int(tx.get("gas_used", 0)),
                }
                for tx in batch
                if tx.get("to_address")  # Skip contract creation txs
            ]
            
            try:
                result = self.service.execute(query, {"txs": tx_data})
                stats["ingested"] += len(tx_data)
                
                # Track unique addresses
                for tx in tx_data:
                    stats["addresses"].add(tx["from_address"])
                    stats["addresses"].add(tx["to_address"])
                    
            except Exception as e:
                logger.error(f"Batch ingestion error: {e}")
                stats["errors"] += len(batch)
            
            # Progress
            progress = (i + len(batch)) / total * 100
            if (i // batch_size) % 10 == 0:
                logger.info(f"Progress: {progress:.1f}% ({stats['ingested']}/{total})")
        
        stats["time_ms"] = (time.time() - start_time) * 1000
        stats["addresses"] = len(stats["addresses"])
        
        logger.info(f"Ingestion complete: {stats['ingested']} transactions, {stats['addresses']} addresses, {stats['time_ms']:.0f}ms")
        
        return stats
    
    def compute_graph_metrics(self):
        """Compute and store graph metrics for addresses."""
        logger.info("Computing graph metrics...")
        
        # Compute degree centrality
        degree_query = """
        MATCH (a:Address)
        OPTIONAL MATCH (a)-[out:TRANSFER]->()
        OPTIONAL MATCH ()-[in:TRANSFER]->(a)
        WITH a, count(DISTINCT out) AS out_deg, count(DISTINCT in) AS in_deg
        SET a.out_degree = out_deg,
            a.in_degree = in_deg,
            a.total_degree = out_deg + in_deg
        RETURN count(a) AS updated
        """
        
        result = self.service.execute(degree_query)
        logger.info(f"Updated degree metrics for {result[0][0]} addresses")
        
        # Mark addresses connected to mixers
        mixer_query = """
        MATCH (m:Mixer)
        MATCH (a:Address)-[:TRANSFER*1..2]-(m)
        WHERE NOT a:Mixer
        SET a.mixer_exposure = true
        RETURN count(DISTINCT a) AS marked
        """
        
        try:
            result = self.service.execute(mixer_query)
            logger.info(f"Marked {result[0][0]} addresses with mixer exposure")
        except Exception as e:
            logger.debug(f"Mixer marking failed (may be no mixers): {e}")
        
        # Mark addresses connected to sanctioned
        sanction_query = """
        MATCH (s:Sanctioned)
        MATCH (a:Address)-[:TRANSFER*1..3]-(s)
        WHERE NOT a:Sanctioned
        SET a.sanction_proximity = true
        RETURN count(DISTINCT a) AS marked
        """
        
        try:
            result = self.service.execute(sanction_query)
            logger.info(f"Marked {result[0][0]} addresses with sanction proximity")
        except Exception as e:
            logger.debug(f"Sanction marking failed: {e}")
    
    def detect_patterns(self) -> Dict[str, Any]:
        """Detect suspicious patterns in the graph."""
        patterns = {}
        
        # 1. Circular transfers (wash trading)
        loop_query = """
        MATCH (a:Address)-[:TRANSFER]->(b:Address)-[:TRANSFER]->(a)
        WHERE a.id < b.id
        RETURN count(*) AS loops, collect(DISTINCT a.id)[..10] AS sample_addresses
        """
        
        try:
            result = self.service.execute(loop_query)
            patterns["circular_transfers"] = {
                "count": result[0][0],
                "sample": result[0][1] if len(result[0]) > 1 else [],
            }
        except Exception as e:
            logger.debug(f"Loop detection failed: {e}")
        
        # 2. High-frequency traders (many transactions)
        hft_query = """
        MATCH (a:Address)
        WHERE a.tx_count > 100
        RETURN count(a) AS count, collect(a.id)[..10] AS sample
        """
        
        try:
            result = self.service.execute(hft_query)
            patterns["high_frequency_traders"] = {
                "count": result[0][0],
                "sample": result[0][1] if len(result[0]) > 1 else [],
            }
        except Exception as e:
            logger.debug(f"HFT detection failed: {e}")
        
        # 3. Fund concentration (large receivers)
        concentration_query = """
        MATCH (a:Address)
        WHERE a.total_received > 100
        RETURN count(a) AS count, sum(a.total_received) AS total_eth
        """
        
        try:
            result = self.service.execute(concentration_query)
            patterns["fund_concentration"] = {
                "addresses": result[0][0],
                "total_eth": result[0][1],
            }
        except Exception as e:
            logger.debug(f"Concentration detection failed: {e}")
        
        return patterns
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current graph statistics."""
        stats = self.service.get_graph_stats()
        
        # Add more detailed stats
        label_query = """
        MATCH (a:Address)
        RETURN 
            count(a) AS total,
            sum(CASE WHEN a:Exchange THEN 1 ELSE 0 END) AS exchanges,
            sum(CASE WHEN a:Mixer THEN 1 ELSE 0 END) AS mixers,
            sum(CASE WHEN a:Sanctioned THEN 1 ELSE 0 END) AS sanctioned,
            sum(CASE WHEN a:DeFi THEN 1 ELSE 0 END) AS defi,
            sum(CASE WHEN a.mixer_exposure = true THEN 1 ELSE 0 END) AS mixer_exposed,
            sum(CASE WHEN a.sanction_proximity = true THEN 1 ELSE 0 END) AS sanction_proximate
        """
        
        try:
            result = self.service.execute(label_query)
            if result:
                row = result[0]
                stats["address_breakdown"] = {
                    "total": row[0],
                    "exchanges": row[1],
                    "mixers": row[2],
                    "sanctioned": row[3],
                    "defi": row[4],
                    "mixer_exposed": row[5],
                    "sanction_proximate": row[6],
                }
        except Exception as e:
            logger.debug(f"Stats query failed: {e}")
        
        return stats


def load_and_ingest(
    data_file: str,
    clear_existing: bool = False,
) -> Dict[str, Any]:
    """Load transaction data and ingest into Memgraph."""
    data_path = Path(data_file)
    
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")
    
    # Load transactions
    logger.info(f"Loading transactions from {data_path}")
    with open(data_path, 'r') as f:
        transactions = json.load(f)
    
    logger.info(f"Loaded {len(transactions)} transactions")
    
    # Ingest
    ingester = MemgraphIngester()
    
    if clear_existing:
        ingester.clear_graph()
    
    # Add known addresses first
    ingester.add_known_addresses()
    
    # Ingest transactions
    stats = ingester.ingest_transactions(transactions)
    
    # Compute metrics
    ingester.compute_graph_metrics()
    
    # Detect patterns
    patterns = ingester.detect_patterns()
    
    # Final stats
    final_stats = ingester.get_stats()
    
    return {
        "ingestion": stats,
        "patterns": patterns,
        "graph_stats": final_stats,
    }


# CLI
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Ingest Ethereum data into Memgraph")
    parser.add_argument("--file", type=str, default="data/eth_transactions.json")
    parser.add_argument("--clear", action="store_true", help="Clear existing graph data")
    parser.add_argument("--stats-only", action="store_true", help="Only show stats")
    
    args = parser.parse_args()
    
    if args.stats_only:
        ingester = MemgraphIngester()
        stats = ingester.get_stats()
        print(json.dumps(stats, indent=2))
    else:
        result = load_and_ingest(args.file, args.clear)
        print("\n" + "=" * 50)
        print("INGESTION COMPLETE")
        print("=" * 50)
        print(json.dumps(result, indent=2, default=str))
