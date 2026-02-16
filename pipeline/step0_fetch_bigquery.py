"""
AMTTP - BigQuery Ethereum Data Fetcher

Fetches real Ethereum transaction data from Google BigQuery public dataset.

Dataset: bigquery-public-data.crypto_ethereum
- transactions: All Ethereum transactions
- traces: Internal transactions
- token_transfers: ERC20/721 transfers
- blocks: Block metadata

Free tier: 1TB/month query processing
"""
import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import BigQuery
try:
    from google.cloud import bigquery
    from google.oauth2 import service_account
    HAVE_BIGQUERY = True
except ImportError:
    HAVE_BIGQUERY = False
    logger.warning("google-cloud-bigquery not installed. Run: pip install google-cloud-bigquery")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)


@dataclass
class EthTransaction:
    """Ethereum transaction from BigQuery."""
    tx_hash: str
    block_number: int
    block_timestamp: str
    from_address: str
    to_address: str
    value_eth: float
    gas_price_gwei: float
    gas_used: int
    gas_limit: int
    transaction_type: int
    max_fee_per_gas_gwei: float
    max_priority_fee_gwei: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BigQueryEthereumFetcher:
    """
    Fetch Ethereum data from BigQuery public dataset.
    
    Requires:
    1. Google Cloud project with BigQuery API enabled
    2. Service account JSON key OR default credentials (gcloud auth)
    
    For Colab: Uses default credentials automatically
    For local: Set GOOGLE_APPLICATION_CREDENTIALS env var
    """
    
    PROJECT_ID = "bigquery-public-data"
    DATASET = "crypto_ethereum"
    
    def __init__(
        self, 
        credentials_path: Optional[str] = None,
        project_id: Optional[str] = None,
    ):
        """
        Initialize BigQuery client.
        
        Args:
            credentials_path: Path to service account JSON (optional for Colab)
            project_id: Your GCP project ID for billing (required for queries)
        """
        if not HAVE_BIGQUERY:
            raise ImportError("google-cloud-bigquery not installed")
        
        self.billing_project = project_id or os.getenv("GCP_PROJECT_ID")
        
        if credentials_path:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=["https://www.googleapis.com/auth/bigquery.readonly"]
            )
            self.client = bigquery.Client(
                credentials=credentials,
                project=self.billing_project,
            )
        else:
            # Use default credentials (works in Colab automatically)
            self.client = bigquery.Client(project=self.billing_project)
        
        logger.info(f"BigQuery client initialized (billing project: {self.billing_project})")
    
    def estimate_query_cost(self, query: str) -> Dict[str, Any]:
        """Estimate query cost before running."""
        job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        query_job = self.client.query(query, job_config=job_config)
        
        bytes_processed = query_job.total_bytes_processed
        gb_processed = bytes_processed / (1024 ** 3)
        estimated_cost = gb_processed * 5.0  # $5 per TB = $0.005 per GB
        
        return {
            "bytes_processed": bytes_processed,
            "gb_processed": round(gb_processed, 3),
            "estimated_cost_usd": round(estimated_cost, 4),
        }
    
    def fetch_transactions(
        self,
        days: int = 7,
        limit: int = 100000,
        min_value_eth: float = 0.01,
        sample_rate: float = 0.01,  # 1% sample for large date ranges
    ) -> List[EthTransaction]:
        """
        Fetch Ethereum transactions from the last N days.
        
        Args:
            days: Number of days to look back
            limit: Maximum transactions to fetch
            min_value_eth: Minimum transaction value (filters dust)
            sample_rate: Random sample rate (0.01 = 1%)
            
        Returns:
            List of EthTransaction objects
        """
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        query = f"""
        SELECT
            `hash` as tx_hash,
            block_number,
            FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', block_timestamp) as block_timestamp,
            from_address,
            to_address,
            CAST(value AS FLOAT64) / 1e18 as value_eth,
            CAST(gas_price AS FLOAT64) / 1e9 as gas_price_gwei,
            receipt_gas_used as gas_used,
            gas as gas_limit,
            COALESCE(transaction_type, 0) as transaction_type,
            COALESCE(CAST(max_fee_per_gas AS FLOAT64) / 1e9, 0) as max_fee_per_gas_gwei,
            COALESCE(CAST(max_priority_fee_per_gas AS FLOAT64) / 1e9, 0) as max_priority_fee_gwei
        FROM `bigquery-public-data.crypto_ethereum.transactions`
        WHERE 
            block_timestamp >= TIMESTAMP('{start_date.strftime('%Y-%m-%d')}')
            AND block_timestamp < TIMESTAMP('{end_date.strftime('%Y-%m-%d')}')
            AND to_address IS NOT NULL
            AND CAST(value AS FLOAT64) / 1e18 >= {min_value_eth}
            AND RAND() < {sample_rate}
        ORDER BY block_timestamp DESC
        LIMIT {limit}
        """
        
        # Estimate cost first
        cost_estimate = self.estimate_query_cost(query)
        logger.info(f"Query estimate: {cost_estimate['gb_processed']} GB, ~${cost_estimate['estimated_cost_usd']}")
        
        # Run query
        logger.info(f"Fetching transactions from {start_date.date()} to {end_date.date()}...")
        query_job = self.client.query(query)
        results = query_job.result()
        
        transactions = []
        for row in results:
            tx = EthTransaction(
                tx_hash=row.tx_hash,
                block_number=row.block_number,
                block_timestamp=row.block_timestamp,
                from_address=row.from_address.lower() if row.from_address else "",
                to_address=row.to_address.lower() if row.to_address else "",
                value_eth=float(row.value_eth or 0),
                gas_price_gwei=float(row.gas_price_gwei or 0),
                gas_used=int(row.gas_used or 0),
                gas_limit=int(row.gas_limit or 0),
                transaction_type=int(row.transaction_type or 0),
                max_fee_per_gas_gwei=float(row.max_fee_per_gas_gwei or 0),
                max_priority_fee_gwei=float(row.max_priority_fee_gwei or 0),
            )
            transactions.append(tx)
        
        logger.info(f"Fetched {len(transactions)} transactions")
        return transactions
    
    def fetch_high_value_transactions(
        self,
        days: int = 7,
        min_value_eth: float = 10.0,
        limit: int = 50000,
    ) -> List[EthTransaction]:
        """Fetch high-value transactions (more likely to be interesting for fraud)."""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        query = f"""
        SELECT
            `hash` as tx_hash,
            block_number,
            FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', block_timestamp) as block_timestamp,
            from_address,
            to_address,
            CAST(value AS FLOAT64) / 1e18 as value_eth,
            CAST(gas_price AS FLOAT64) / 1e9 as gas_price_gwei,
            receipt_gas_used as gas_used,
            gas as gas_limit,
            COALESCE(transaction_type, 0) as transaction_type,
            COALESCE(CAST(max_fee_per_gas AS FLOAT64) / 1e9, 0) as max_fee_per_gas_gwei,
            COALESCE(CAST(max_priority_fee_per_gas AS FLOAT64) / 1e9, 0) as max_priority_fee_gwei
        FROM `bigquery-public-data.crypto_ethereum.transactions`
        WHERE 
            block_timestamp >= TIMESTAMP('{start_date.strftime('%Y-%m-%d')}')
            AND block_timestamp < TIMESTAMP('{end_date.strftime('%Y-%m-%d')}')
            AND to_address IS NOT NULL
            AND CAST(value AS FLOAT64) / 1e18 >= {min_value_eth}
        ORDER BY value DESC
        LIMIT {limit}
        """
        
        cost_estimate = self.estimate_query_cost(query)
        logger.info(f"High-value query estimate: {cost_estimate['gb_processed']} GB")
        
        query_job = self.client.query(query)
        results = query_job.result()
        
        transactions = []
        for row in results:
            tx = EthTransaction(
                tx_hash=row.tx_hash,
                block_number=row.block_number,
                block_timestamp=row.block_timestamp,
                from_address=row.from_address.lower() if row.from_address else "",
                to_address=row.to_address.lower() if row.to_address else "",
                value_eth=float(row.value_eth or 0),
                gas_price_gwei=float(row.gas_price_gwei or 0),
                gas_used=int(row.gas_used or 0),
                gas_limit=int(row.gas_limit or 0),
                transaction_type=int(row.transaction_type or 0),
                max_fee_per_gas_gwei=float(row.max_fee_per_gas_gwei or 0),
                max_priority_fee_gwei=float(row.max_priority_fee_gwei or 0),
            )
            transactions.append(tx)
        
        logger.info(f"Fetched {len(transactions)} high-value transactions")
        return transactions
    
    def fetch_address_transactions(
        self,
        addresses: List[str],
        days: int = 30,
        limit: int = 10000,
    ) -> List[EthTransaction]:
        """Fetch transactions involving specific addresses."""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Format addresses for SQL
        addr_list = ", ".join([f"'{a.lower()}'" for a in addresses])
        
        query = f"""
        SELECT
            `hash` as tx_hash,
            block_number,
            FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', block_timestamp) as block_timestamp,
            from_address,
            to_address,
            CAST(value AS FLOAT64) / 1e18 as value_eth,
            CAST(gas_price AS FLOAT64) / 1e9 as gas_price_gwei,
            receipt_gas_used as gas_used,
            gas as gas_limit,
            COALESCE(transaction_type, 0) as transaction_type,
            COALESCE(CAST(max_fee_per_gas AS FLOAT64) / 1e9, 0) as max_fee_per_gas_gwei,
            COALESCE(CAST(max_priority_fee_per_gas AS FLOAT64) / 1e9, 0) as max_priority_fee_gwei
        FROM `bigquery-public-data.crypto_ethereum.transactions`
        WHERE 
            block_timestamp >= TIMESTAMP('{start_date.strftime('%Y-%m-%d')}')
            AND (LOWER(from_address) IN ({addr_list}) OR LOWER(to_address) IN ({addr_list}))
        ORDER BY block_timestamp DESC
        LIMIT {limit}
        """
        
        query_job = self.client.query(query)
        results = query_job.result()
        
        return [
            EthTransaction(
                tx_hash=row.tx_hash,
                block_number=row.block_number,
                block_timestamp=row.block_timestamp,
                from_address=row.from_address.lower() if row.from_address else "",
                to_address=row.to_address.lower() if row.to_address else "",
                value_eth=float(row.value_eth or 0),
                gas_price_gwei=float(row.gas_price_gwei or 0),
                gas_used=int(row.gas_used or 0),
                gas_limit=int(row.gas_limit or 0),
                transaction_type=int(row.transaction_type or 0),
                max_fee_per_gas_gwei=float(row.max_fee_per_gas_gwei or 0),
                max_priority_fee_gwei=float(row.max_priority_fee_gwei or 0),
            )
            for row in results
        ]
    
    def get_known_addresses_activity(self, days: int = 7) -> Dict[str, Any]:
        """
        Get transaction activity for known addresses (exchanges, mixers, etc).
        
        Uses a more efficient approach by filtering on known addresses first.
        """
        # Known addresses to track
        known_addresses = [
            # Exchanges
            "0x28c6c06298d514db089934071355e5743bf21d60",  # Binance
            "0xdfd5293d8e347dfe59e90efd55b2956a1343963d",  # Binance
            "0x56eddb7aa87536c09ccc2793473599fd21a8b17f",  # Coinbase
            # Mixers (sanctioned)
            "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",  # Tornado Cash
            "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",  # Tornado Cash
        ]
        
        transactions = self.fetch_address_transactions(known_addresses, days)
        
        return {
            "addresses_tracked": len(known_addresses),
            "transactions_found": len(transactions),
            "transactions": [tx.to_dict() for tx in transactions[:100]],  # Sample
        }


def save_transactions(transactions: List[EthTransaction], filename: str) -> Path:
    """Save transactions to JSON file."""
    filepath = DATA_DIR / filename
    with open(filepath, 'w') as f:
        json.dump([tx.to_dict() for tx in transactions], f)
    logger.info(f"Saved {len(transactions)} transactions to {filepath}")
    return filepath


def load_transactions(filename: str) -> List[Dict]:
    """Load transactions from JSON file."""
    filepath = DATA_DIR / filename
    with open(filepath, 'r') as f:
        return json.load(f)


# For Colab integration
def colab_authenticate():
    """Authenticate in Google Colab environment."""
    try:
        from google.colab import auth
        auth.authenticate_user()
        logger.info("Colab authentication successful")
        return True
    except ImportError:
        logger.info("Not running in Colab")
        return False


# CLI
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch Ethereum data from BigQuery")
    parser.add_argument("--days", type=int, default=7, help="Days of data to fetch")
    parser.add_argument("--limit", type=int, default=50000, help="Max transactions")
    parser.add_argument("--min-value", type=float, default=0.1, help="Min ETH value")
    parser.add_argument("--sample-rate", type=float, default=0.01, help="Sample rate (0.01 = 1%)")
    parser.add_argument("--output", type=str, default="eth_bigquery_transactions.json")
    parser.add_argument("--project", type=str, help="GCP project ID for billing")
    parser.add_argument("--high-value", action="store_true", help="Fetch only high-value txs")
    parser.add_argument("--estimate-only", action="store_true", help="Only estimate cost")
    
    args = parser.parse_args()
    
    # Initialize
    fetcher = BigQueryEthereumFetcher(project_id=args.project)
    
    if args.high_value:
        transactions = fetcher.fetch_high_value_transactions(
            days=args.days,
            min_value_eth=args.min_value,
            limit=args.limit,
        )
    else:
        transactions = fetcher.fetch_transactions(
            days=args.days,
            limit=args.limit,
            min_value_eth=args.min_value,
            sample_rate=args.sample_rate,
        )
    
    if not args.estimate_only:
        filepath = save_transactions(transactions, args.output)
        print(f"\nSaved {len(transactions)} transactions to {filepath}")
        
        # Sample output
        print("\nSample transactions:")
        for tx in transactions[:5]:
            print(f"  {tx.tx_hash[:16]}... | {tx.value_eth:.2f} ETH | {tx.block_timestamp}")
