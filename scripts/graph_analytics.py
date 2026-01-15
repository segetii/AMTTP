"""
AMTTP Memgraph Ingestion and Graph Analytics

Ingests Ethereum transaction data into Memgraph and runs graph-based
fraud detection algorithms.

Usage:
    python graph_analytics.py --input "C:/path/to/eth_data.parquet"
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any, Optional

import pandas as pd
import numpy as np
from tqdm import tqdm
import mgclient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "processed" / "graph_analytics"


class MemgraphAnalytics:
    """
    Graph analytics for Ethereum transaction network.
    
    Features:
    - Batch ingestion of transactions
    - PageRank for importance scoring
    - Community detection
    - Pattern matching for fraud detection
    - Hub/authority analysis
    """
    
    def __init__(self, host: str = "localhost", port: int = 7687):
        self.conn = mgclient.connect(host=host, port=port)
        self.cursor = self.conn.cursor()
        logger.info(f"Connected to Memgraph at {host}:{port}")
    
    def clear_database(self):
        """Clear all data from database."""
        logger.info("Clearing existing data...")
        self.cursor.execute("MATCH (n) DETACH DELETE n")
        self.conn.commit()
        logger.info("Database cleared")
    
    def create_indexes(self):
        """Create indexes for faster queries."""
        logger.info("Creating indexes...")
        indexes = [
            "CREATE INDEX ON :Address(address)",
            "CREATE INDEX ON :Address(is_suspicious)",
        ]
        for idx in indexes:
            try:
                self.cursor.execute(idx)
                self.conn.commit()
            except Exception as e:
                pass  # Index may already exist
    
    def ingest_transactions(self, df: pd.DataFrame, batch_size: int = 5000):
        """Batch ingest transactions into Memgraph."""
        logger.info(f"Ingesting {len(df):,} transactions...")
        
        # Create addresses and transactions
        total_batches = (len(df) + batch_size - 1) // batch_size
        
        for batch_start in tqdm(range(0, len(df), batch_size), total=total_batches, desc="Ingesting"):
            batch = df.iloc[batch_start:batch_start + batch_size]
            
            # Build batch query
            for _, row in batch.iterrows():
                try:
                    from_addr = str(row['from_address']).lower()
                    to_addr = str(row['to_address']).lower()
                    value = float(row.get('value_eth', 0))
                    tx_hash = str(row.get('tx_hash', ''))[:20]  # Truncate for storage
                    
                    query = """
                    MERGE (from:Address {address: $from_addr})
                    MERGE (to:Address {address: $to_addr})
                    CREATE (from)-[:SENT {
                        value: $value,
                        tx_hash: $tx_hash
                    }]->(to)
                    """
                    
                    self.cursor.execute(query, {
                        'from_addr': from_addr,
                        'to_addr': to_addr,
                        'value': value,
                        'tx_hash': tx_hash
                    })
                except Exception as e:
                    pass  # Continue on individual failures
            
            self.conn.commit()
        
        # Get counts
        self.cursor.execute("MATCH (n:Address) RETURN count(n) as cnt")
        address_count = self.cursor.fetchone()[0]
        
        self.cursor.execute("MATCH ()-[r:SENT]->() RETURN count(r) as cnt")
        tx_count = self.cursor.fetchone()[0]
        
        logger.info(f"Ingested {address_count:,} addresses, {tx_count:,} transactions")
        return address_count, tx_count
    
    def run_pagerank(self, iterations: int = 20, damping: float = 0.85):
        """Run PageRank algorithm to find important addresses."""
        logger.info("Running PageRank...")
        
        # Memgraph MAGE PageRank
        try:
            query = """
            CALL pagerank.get()
            YIELD node, rank
            WITH node, rank
            WHERE rank > 0.001
            SET node.pagerank = rank
            RETURN node.address as address, rank
            ORDER BY rank DESC
            LIMIT 100
            """
            self.cursor.execute(query)
            results = self.cursor.fetchall()
            self.conn.commit()
            
            logger.info(f"PageRank completed, top 100 addresses flagged")
            return results
        except Exception as e:
            logger.warning(f"PageRank failed (MAGE may not be installed): {e}")
            return []
    
    def detect_fan_patterns(self, threshold: int = 10):
        """Detect fan-out and fan-in patterns."""
        logger.info("Detecting fan patterns...")
        
        # Fan-out: addresses sending to many recipients
        query = f"""
        MATCH (from:Address)-[r:SENT]->(to:Address)
        WITH from, count(DISTINCT to) as recipients, sum(r.value) as total_sent
        WHERE recipients >= {threshold}
        SET from.is_suspicious = true, from.pattern = 'FAN_OUT'
        RETURN from.address as address, recipients, total_sent
        ORDER BY recipients DESC
        LIMIT 1000
        """
        self.cursor.execute(query)
        fan_out = self.cursor.fetchall()
        self.conn.commit()
        
        # Fan-in: addresses receiving from many senders
        query = f"""
        MATCH (from:Address)-[r:SENT]->(to:Address)
        WITH to, count(DISTINCT from) as senders, sum(r.value) as total_received
        WHERE senders >= {threshold}
        SET to.is_suspicious = true, to.pattern = 'FAN_IN'
        RETURN to.address as address, senders, total_received
        ORDER BY senders DESC
        LIMIT 1000
        """
        self.cursor.execute(query)
        fan_in = self.cursor.fetchall()
        self.conn.commit()
        
        logger.info(f"Found {len(fan_out)} fan-out, {len(fan_in)} fan-in addresses")
        return fan_out, fan_in
    
    def detect_cycles(self, max_depth: int = 4):
        """Detect cyclic transactions (potential layering)."""
        logger.info("Detecting cycles...")
        
        query = f"""
        MATCH path = (a:Address)-[:SENT*2..{max_depth}]->(a)
        WITH a, length(path) as cycle_length
        SET a.is_suspicious = true, a.pattern = 'CYCLE'
        RETURN a.address as address, cycle_length
        LIMIT 500
        """
        try:
            self.cursor.execute(query)
            cycles = self.cursor.fetchall()
            self.conn.commit()
            logger.info(f"Found {len(cycles)} addresses in cycles")
            return cycles
        except Exception as e:
            logger.warning(f"Cycle detection limited: {e}")
            return []
    
    def detect_mixers(self, in_threshold: int = 20, out_threshold: int = 20):
        """Detect potential mixer addresses (high in/out degree)."""
        logger.info("Detecting potential mixers...")
        
        query = f"""
        MATCH (addr:Address)
        OPTIONAL MATCH (addr)-[:SENT]->(out)
        WITH addr, count(DISTINCT out) as out_degree
        OPTIONAL MATCH (in)-[:SENT]->(addr)
        WITH addr, out_degree, count(DISTINCT in) as in_degree
        WHERE out_degree >= {out_threshold} AND in_degree >= {in_threshold}
        SET addr.is_suspicious = true, addr.pattern = 'MIXER'
        RETURN addr.address as address, in_degree, out_degree
        ORDER BY in_degree + out_degree DESC
        LIMIT 500
        """
        self.cursor.execute(query)
        mixers = self.cursor.fetchall()
        self.conn.commit()
        
        logger.info(f"Found {len(mixers)} potential mixer addresses")
        return mixers
    
    def get_suspicious_addresses(self):
        """Get all flagged suspicious addresses."""
        query = """
        MATCH (a:Address)
        WHERE a.is_suspicious = true
        OPTIONAL MATCH (a)-[r_out:SENT]->()
        OPTIONAL MATCH ()-[r_in:SENT]->(a)
        WITH a, 
             count(DISTINCT r_out) as sent_count,
             count(DISTINCT r_in) as received_count,
             COALESCE(sum(r_out.value), 0) as total_sent,
             COALESCE(sum(r_in.value), 0) as total_received
        RETURN 
            a.address as address,
            a.pattern as pattern,
            COALESCE(a.pagerank, 0) as pagerank,
            sent_count,
            received_count,
            total_sent,
            total_received
        ORDER BY pagerank DESC
        """
        self.cursor.execute(query)
        results = self.cursor.fetchall()
        
        return pd.DataFrame(results, columns=[
            'address', 'pattern', 'pagerank', 'sent_count', 
            'received_count', 'total_sent', 'total_received'
        ])
    
    def get_network_stats(self):
        """Get overall network statistics."""
        stats = {}
        
        # Node count
        self.cursor.execute("MATCH (n) RETURN count(n) as cnt")
        stats['total_addresses'] = self.cursor.fetchone()[0]
        
        # Edge count
        self.cursor.execute("MATCH ()-[r]->() RETURN count(r) as cnt")
        stats['total_transactions'] = self.cursor.fetchone()[0]
        
        # Suspicious count
        self.cursor.execute("MATCH (n:Address {is_suspicious: true}) RETURN count(n) as cnt")
        stats['suspicious_addresses'] = self.cursor.fetchone()[0]
        
        # Total value
        self.cursor.execute("MATCH ()-[r:SENT]->() RETURN sum(r.value) as total")
        result = self.cursor.fetchone()[0]
        stats['total_eth_moved'] = float(result) if result else 0
        
        return stats


def run_graph_analytics(input_file: str, output_dir: Path = OUTPUT_DIR, sample_size: Optional[int] = None):
    """
    Main graph analytics pipeline.
    """
    start_time = time.time()
    
    print("=" * 70)
    print("AMTTP GRAPH ANALYTICS PIPELINE")
    print("=" * 70)
    print(f"Input: {input_file}")
    print(f"Output: {output_dir}")
    print()
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    logger.info(f"Loading data from {input_file}...")
    df = pd.read_parquet(input_file)
    
    if sample_size and len(df) > sample_size:
        logger.info(f"Sampling {sample_size:,} transactions from {len(df):,}")
        df = df.sample(n=sample_size, random_state=42)
    
    logger.info(f"Processing {len(df):,} transactions")
    
    # Connect to Memgraph
    analytics = MemgraphAnalytics()
    
    # Clear and prepare database
    analytics.clear_database()
    analytics.create_indexes()
    
    # Ingest data
    address_count, tx_count = analytics.ingest_transactions(df)
    
    # Run analytics
    print("\n" + "=" * 70)
    print("RUNNING GRAPH ANALYTICS")
    print("=" * 70 + "\n")
    
    # Detect patterns
    fan_out, fan_in = analytics.detect_fan_patterns(threshold=10)
    mixers = analytics.detect_mixers(in_threshold=20, out_threshold=20)
    cycles = analytics.detect_cycles(max_depth=4)
    
    # Run PageRank
    pagerank_results = analytics.run_pagerank()
    
    # Get results
    suspicious_df = analytics.get_suspicious_addresses()
    network_stats = analytics.get_network_stats()
    
    # Save results
    suspicious_df.to_csv(output_dir / "suspicious_addresses_graph.csv", index=False)
    suspicious_df.to_parquet(output_dir / "suspicious_addresses_graph.parquet", index=False)
    
    # Save fan-out/fan-in details
    if fan_out:
        fan_out_df = pd.DataFrame(fan_out, columns=['address', 'recipients', 'total_sent'])
        fan_out_df.to_csv(output_dir / "fan_out_addresses.csv", index=False)
    
    if fan_in:
        fan_in_df = pd.DataFrame(fan_in, columns=['address', 'senders', 'total_received'])
        fan_in_df.to_csv(output_dir / "fan_in_addresses.csv", index=False)
    
    if mixers:
        mixers_df = pd.DataFrame(mixers, columns=['address', 'in_degree', 'out_degree'])
        mixers_df.to_csv(output_dir / "potential_mixers.csv", index=False)
    
    # Calculate statistics
    elapsed = time.time() - start_time
    
    stats = {
        'input_file': input_file,
        'transactions_processed': int(len(df)),
        'addresses_in_graph': network_stats['total_addresses'],
        'transactions_in_graph': network_stats['total_transactions'],
        'total_eth_moved': round(network_stats['total_eth_moved'], 2),
        'suspicious_addresses': network_stats['suspicious_addresses'],
        'fan_out_count': len(fan_out),
        'fan_in_count': len(fan_in),
        'mixer_candidates': len(mixers),
        'cycle_addresses': len(cycles),
        'processing_time_seconds': round(elapsed, 2)
    }
    
    with open(output_dir / "graph_analytics_stats.json", "w") as f:
        json.dump(stats, f, indent=2)
    
    # Print summary
    print("\n" + "=" * 70)
    print("GRAPH ANALYTICS COMPLETE")
    print("=" * 70)
    print(f"\n📊 NETWORK STATISTICS:")
    print(f"   Addresses in graph:      {stats['addresses_in_graph']:,}")
    print(f"   Transactions in graph:   {stats['transactions_in_graph']:,}")
    print(f"   Total ETH moved:         {stats['total_eth_moved']:,.2f}")
    print(f"\n🚨 SUSPICIOUS PATTERNS DETECTED:")
    print(f"   Fan-out addresses:       {stats['fan_out_count']:,}")
    print(f"   Fan-in addresses:        {stats['fan_in_count']:,}")
    print(f"   Potential mixers:        {stats['mixer_candidates']:,}")
    print(f"   Cycle participants:      {stats['cycle_addresses']:,}")
    print(f"   Total suspicious:        {stats['suspicious_addresses']:,}")
    print(f"\n⏱️ Processing time:          {stats['processing_time_seconds']:.1f}s")
    print(f"\n📁 OUTPUT FILES:")
    print(f"   • {output_dir / 'suspicious_addresses_graph.csv'}")
    print(f"   • {output_dir / 'fan_out_addresses.csv'}")
    print(f"   • {output_dir / 'fan_in_addresses.csv'}")
    print(f"   • {output_dir / 'potential_mixers.csv'}")
    print("\n" + "=" * 70)
    
    return suspicious_df, stats


def main():
    parser = argparse.ArgumentParser(description="Run graph analytics on ETH transaction data")
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet",
        help="Input parquet file path"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=str(OUTPUT_DIR),
        help="Output directory"
    )
    parser.add_argument(
        "--sample", "-s",
        type=int,
        default=None,
        help="Sample size (for testing with large datasets)"
    )
    
    args = parser.parse_args()
    
    run_graph_analytics(args.input, Path(args.output), args.sample)


if __name__ == "__main__":
    main()
