"""
AMTTP ML Pipeline - Memgraph Data Loader

Utility to load transaction data and sanctions into Memgraph.

Usage:
    python -m graph.loader --transactions data/transactions.csv
    python -m graph.loader --sanctions data/ofac_addresses.json
    python -m graph.loader --both --transactions data/transactions.csv --sanctions data/ofac.json
"""
import argparse
import json
import logging
from pathlib import Path
from typing import List

import pandas as pd

from .service import get_memgraph_service, MemgraphConfig
from .updater import GraphUpdater, Transaction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_transactions_from_csv(path: str, updater: GraphUpdater, batch_size: int = 1000):
    """
    Load transactions from CSV file into Memgraph.
    
    Expected columns: from, to, value, timestamp, hash, blockNumber
    """
    logger.info(f"Loading transactions from {path}")
    
    df = pd.read_csv(path)
    logger.info(f"Found {len(df)} transactions")
    
    # Build transaction objects
    transactions = []
    for _, row in df.iterrows():
        txn = Transaction(
            hash=str(row.get("hash", "")),
            from_address=str(row.get("from", row.get("from_address", ""))),
            to_address=str(row.get("to", row.get("to_address", ""))),
            value=float(row.get("value", 0)),
            timestamp=int(row.get("timestamp", row.get("ts", 0))),
            block_number=int(row.get("blockNumber", row.get("block", 0))),
        )
        transactions.append(txn)
    
    # Batch insert
    count = updater.add_transactions_batch(transactions, batch_size=batch_size)
    logger.info(f"Loaded {count} transactions into Memgraph")
    
    return count


def load_transactions_from_parquet(path: str, updater: GraphUpdater, batch_size: int = 1000):
    """Load transactions from Parquet file."""
    logger.info(f"Loading transactions from {path}")
    
    df = pd.read_parquet(path)
    logger.info(f"Found {len(df)} transactions")
    
    transactions = []
    for _, row in df.iterrows():
        txn = Transaction(
            hash=str(row.get("hash", "")),
            from_address=str(row.get("from", row.get("from_address", ""))),
            to_address=str(row.get("to", row.get("to_address", ""))),
            value=float(row.get("value", 0)),
            timestamp=int(row.get("timestamp", row.get("ts", 0))),
            block_number=int(row.get("blockNumber", row.get("block", 0))),
        )
        transactions.append(txn)
    
    count = updater.add_transactions_batch(transactions, batch_size=batch_size)
    logger.info(f"Loaded {count} transactions into Memgraph")
    
    return count


def load_sanctions_from_json(path: str, updater: GraphUpdater):
    """
    Load sanctioned addresses from JSON file.
    
    Expected format: {"addresses": ["0x...", "0x..."]}
    """
    logger.info(f"Loading sanctions from {path}")
    
    with open(path, "r") as f:
        data = json.load(f)
    
    addresses = data.get("addresses", [])
    if not addresses:
        # Try flat list
        addresses = data if isinstance(data, list) else []
    
    logger.info(f"Found {len(addresses)} sanctioned addresses")
    
    count = updater.tag_addresses_batch(addresses, "sanctioned")
    logger.info(f"Tagged {count} addresses as sanctioned")
    
    return count


def main():
    parser = argparse.ArgumentParser(description="Load data into Memgraph")
    parser.add_argument("--transactions", type=str, help="Path to transactions CSV or Parquet")
    parser.add_argument("--sanctions", type=str, help="Path to sanctions JSON")
    parser.add_argument("--host", type=str, default="localhost", help="Memgraph host")
    parser.add_argument("--port", type=int, default=7687, help="Memgraph port")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for inserts")
    parser.add_argument("--create-indexes", action="store_true", help="Create indexes")
    
    args = parser.parse_args()
    
    # Setup service
    config = MemgraphConfig(host=args.host, port=args.port)
    service = get_memgraph_service(config)
    updater = GraphUpdater(service)
    
    # Create indexes if requested
    if args.create_indexes:
        logger.info("Creating indexes...")
        updater.create_indexes()
    
    # Load transactions
    if args.transactions:
        path = Path(args.transactions)
        if path.suffix.lower() in (".parquet", ".pq"):
            load_transactions_from_parquet(str(path), updater, args.batch_size)
        else:
            load_transactions_from_csv(str(path), updater, args.batch_size)
    
    # Load sanctions
    if args.sanctions:
        load_sanctions_from_json(args.sanctions, updater)
    
    # Print stats
    stats = service.get_graph_stats()
    logger.info(f"Graph stats: {stats}")


if __name__ == "__main__":
    main()
