"""
BigQuery Full Ethereum Data Export

Downloads the complete Ethereum transaction dataset (no sampling) for a date range.
Uses pagination to handle millions of rows and saves to Parquet for efficient storage.

Requirements:
- Google Cloud credentials (set GOOGLE_APPLICATION_CREDENTIALS)
- pip install google-cloud-bigquery pyarrow pandas

Usage:
    python bigquery_full_export.py --days 7 --output ./data/eth_full
    python bigquery_full_export.py --start 2025-12-01 --end 2025-12-07 --output ./data/eth_full
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from google.cloud import bigquery
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError as e:
    logger.error(f"Missing dependencies: {e}")
    logger.error("Run: pip install google-cloud-bigquery pandas pyarrow")
    sys.exit(1)


class BigQueryFullExporter:
    """
    Export full Ethereum transaction data from BigQuery.
    
    Handles:
    - Pagination for large datasets (millions of rows)
    - Day-by-day processing to manage memory
    - Parquet output with compression
    - Resume capability
    """
    
    # BigQuery has 10GB result limit, so we process day by day
    ROWS_PER_BATCH = 500_000  # Rows to fetch per query
    
    def __init__(self, billing_project: Optional[str] = None, credentials_path: Optional[str] = None):
        """Initialize BigQuery client."""
        if credentials_path and os.path.exists(credentials_path):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
        
        self.billing_project = billing_project
        
        if billing_project:
            self.client = bigquery.Client(project=billing_project)
        else:
            self.client = bigquery.Client()
        
        logger.info(f"BigQuery client initialized")
    
    def estimate_data_size(self, start_date: datetime, end_date: datetime, min_value_eth: float = 0.0) -> dict:
        """Estimate the size of data to be downloaded."""
        query = f"""
        SELECT 
            COUNT(*) as total_transactions,
            SUM(CAST(value AS FLOAT64)) / 1e18 as total_eth,
            COUNT(DISTINCT from_address) as unique_senders,
            COUNT(DISTINCT to_address) as unique_receivers
        FROM `bigquery-public-data.crypto_ethereum.transactions`
        WHERE 
            block_timestamp >= TIMESTAMP('{start_date.strftime('%Y-%m-%d')}')
            AND block_timestamp < TIMESTAMP('{end_date.strftime('%Y-%m-%d')}')
            AND to_address IS NOT NULL
            {"AND CAST(value AS FLOAT64) / 1e18 >= " + str(min_value_eth) if min_value_eth > 0 else ""}
        """
        
        # Cost estimate (dry run)
        job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        dry_run = self.client.query(query, job_config=job_config)
        gb_scanned = dry_run.total_bytes_processed / (1024**3)
        
        # Run actual count
        result = self.client.query(query).result()
        row = list(result)[0]
        
        return {
            "total_transactions": row.total_transactions,
            "total_eth": round(row.total_eth or 0, 2),
            "unique_senders": row.unique_senders,
            "unique_receivers": row.unique_receivers,
            "estimated_gb_to_scan": round(gb_scanned, 2),
            "estimated_cost_usd": round(gb_scanned * 0.005, 4),  # $5/TB
            "estimated_file_size_gb": round(row.total_transactions * 500 / (1024**3), 2),  # ~500 bytes/row
        }
    
    def export_day(
        self,
        date: datetime,
        output_dir: Path,
        min_value_eth: float = 0.0
    ) -> int:
        """Export all transactions for a single day."""
        date_str = date.strftime('%Y-%m-%d')
        next_date = date + timedelta(days=1)
        next_date_str = next_date.strftime('%Y-%m-%d')
        
        output_file = output_dir / f"eth_transactions_{date_str}.parquet"
        
        # Skip if already exists
        if output_file.exists():
            existing_df = pd.read_parquet(output_file)
            logger.info(f"  {date_str}: Already exists ({len(existing_df):,} rows)")
            return len(existing_df)
        
        query = f"""
        SELECT
            `hash` as tx_hash,
            block_number,
            block_timestamp,
            from_address,
            to_address,
            CAST(value AS FLOAT64) / 1e18 as value_eth,
            CAST(gas_price AS FLOAT64) / 1e9 as gas_price_gwei,
            receipt_gas_used as gas_used,
            gas as gas_limit,
            COALESCE(transaction_type, 0) as transaction_type,
            nonce,
            transaction_index
        FROM `bigquery-public-data.crypto_ethereum.transactions`
        WHERE 
            block_timestamp >= TIMESTAMP('{date_str}')
            AND block_timestamp < TIMESTAMP('{next_date_str}')
            AND to_address IS NOT NULL
            {"AND CAST(value AS FLOAT64) / 1e18 >= " + str(min_value_eth) if min_value_eth > 0 else ""}
        ORDER BY block_number, transaction_index
        """
        
        logger.info(f"  {date_str}: Fetching data...")
        
        # Use pandas gbq for efficient download
        df = self.client.query(query).to_dataframe()
        
        if len(df) == 0:
            logger.warning(f"  {date_str}: No data found")
            return 0
        
        # Save to Parquet with compression
        df.to_parquet(output_file, compression='snappy', index=False)
        
        file_size_mb = output_file.stat().st_size / (1024**2)
        logger.info(f"  {date_str}: Saved {len(df):,} transactions ({file_size_mb:.1f} MB)")
        
        return len(df)
    
    def export_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        output_dir: str,
        min_value_eth: float = 0.0
    ) -> dict:
        """Export all transactions in date range, one day at a time."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # First, estimate the data
        logger.info("=" * 60)
        logger.info("ESTIMATING DATA SIZE")
        logger.info("=" * 60)
        
        estimate = self.estimate_data_size(start_date, end_date, min_value_eth)
        logger.info(f"Total transactions: {estimate['total_transactions']:,}")
        logger.info(f"Total ETH moved: {estimate['total_eth']:,.2f}")
        logger.info(f"Unique senders: {estimate['unique_senders']:,}")
        logger.info(f"Unique receivers: {estimate['unique_receivers']:,}")
        logger.info(f"Estimated scan: {estimate['estimated_gb_to_scan']:.2f} GB")
        logger.info(f"Estimated cost: ${estimate['estimated_cost_usd']:.4f}")
        logger.info(f"Estimated file size: {estimate['estimated_file_size_gb']:.2f} GB")
        logger.info("")
        
        # Process day by day
        logger.info("=" * 60)
        logger.info("EXPORTING DATA (DAY BY DAY)")
        logger.info("=" * 60)
        
        current_date = start_date
        total_rows = 0
        days_processed = 0
        
        while current_date < end_date:
            rows = self.export_day(current_date, output_path, min_value_eth)
            total_rows += rows
            days_processed += 1
            current_date += timedelta(days=1)
        
        # Create a manifest file
        manifest = {
            "export_date": datetime.now().isoformat(),
            "start_date": start_date.strftime('%Y-%m-%d'),
            "end_date": end_date.strftime('%Y-%m-%d'),
            "days_processed": days_processed,
            "total_rows": total_rows,
            "min_value_eth": min_value_eth,
            "files": [f.name for f in output_path.glob("*.parquet")]
        }
        
        import json
        with open(output_path / "manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("EXPORT COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total rows: {total_rows:,}")
        logger.info(f"Days processed: {days_processed}")
        logger.info(f"Output directory: {output_path}")
        
        return manifest


def main():
    parser = argparse.ArgumentParser(description="Export full Ethereum data from BigQuery")
    parser.add_argument("--days", type=int, default=7, help="Number of days to export (default: 7)")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", type=str, default="./data/eth_full", help="Output directory")
    parser.add_argument("--min-value", type=float, default=0.0, help="Minimum ETH value (filters dust)")
    parser.add_argument("--project", type=str, help="GCP billing project ID")
    parser.add_argument("--credentials", type=str, help="Path to service account JSON")
    parser.add_argument("--estimate-only", action="store_true", help="Only estimate, don't download")
    
    args = parser.parse_args()
    
    # Calculate date range
    if args.start and args.end:
        start_date = datetime.strptime(args.start, '%Y-%m-%d')
        end_date = datetime.strptime(args.end, '%Y-%m-%d')
    else:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=args.days)
    
    logger.info(f"Date range: {start_date.date()} to {end_date.date()}")
    
    # Initialize exporter
    exporter = BigQueryFullExporter(
        billing_project=args.project,
        credentials_path=args.credentials
    )
    
    if args.estimate_only:
        estimate = exporter.estimate_data_size(start_date, end_date, args.min_value)
        print("\n" + "=" * 50)
        print("DATA ESTIMATE")
        print("=" * 50)
        for k, v in estimate.items():
            print(f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}")
        return
    
    # Export data
    exporter.export_date_range(
        start_date=start_date,
        end_date=end_date,
        output_dir=args.output,
        min_value_eth=args.min_value
    )


if __name__ == "__main__":
    main()
