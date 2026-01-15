"""
Batch Processing Pipeline for Large-Scale Ethereum Fraud Detection

Processes millions of transactions in chunks:
1. ML scoring in batches
2. Graph analysis with streaming ingestion
3. Pattern detection across batches
4. Results aggregation

Usage:
    python batch_fraud_pipeline.py --input ./data/eth_full --output ./processed
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Generator, Dict, Any, List, Optional
from collections import defaultdict
import gc

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    import pandas as pd
    import numpy as np
    from tqdm import tqdm
except ImportError as e:
    logger.error(f"Missing: {e}. Run: pip install pandas numpy tqdm")
    sys.exit(1)

# Optional imports
try:
    import xgboost as xgb
    HAVE_XGB = True
except ImportError:
    HAVE_XGB = False
    logger.warning("XGBoost not installed - ML scoring disabled")

try:
    from neo4j import GraphDatabase
    HAVE_NEO4J = True
except ImportError:
    HAVE_NEO4J = False

try:
    from mgclient import connect as mg_connect
    HAVE_MEMGRAPH = True
except ImportError:
    HAVE_MEMGRAPH = False


class BatchFraudPipeline:
    """
    Process large-scale Ethereum data for fraud detection.
    
    Features:
    - Chunk-based processing (configurable batch size)
    - Memory-efficient streaming
    - Incremental pattern detection
    - Graph database batch ingestion
    """
    
    # Default thresholds
    ML_THRESHOLD = 0.55
    MULTI_SIGNAL_MIN = 2
    
    # Pattern detection thresholds
    FAN_OUT_THRESHOLD = 10      # Sends to 10+ addresses
    FAN_IN_THRESHOLD = 10       # Receives from 10+ addresses  
    RAPID_TX_THRESHOLD = 5      # 5+ tx in 1 hour
    ROUND_AMOUNT_TOLERANCE = 0.001
    
    def __init__(
        self,
        input_dir: str,
        output_dir: str,
        batch_size: int = 100_000,
        memgraph_host: str = "localhost",
        memgraph_port: int = 7687
    ):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.batch_size = batch_size
        
        # Stats tracking
        self.stats = {
            "total_transactions": 0,
            "flagged_transactions": 0,
            "critical_addresses": set(),
            "high_risk_addresses": set(),
            "patterns_detected": defaultdict(int),
            "processing_time_seconds": 0
        }
        
        # Pattern accumulators (for cross-batch detection)
        self.address_tx_counts = defaultdict(int)
        self.address_out_counts = defaultdict(int)
        self.address_in_counts = defaultdict(int)
        self.address_values = defaultdict(list)
        self.hourly_tx = defaultdict(lambda: defaultdict(int))
        
        # Memgraph connection
        self.memgraph = None
        if HAVE_MEMGRAPH:
            try:
                self.memgraph = mg_connect(host=memgraph_host, port=memgraph_port)
                logger.info(f"Connected to Memgraph at {memgraph_host}:{memgraph_port}")
            except Exception as e:
                logger.warning(f"Memgraph not available: {e}")
        
        # Load ML model if available
        self.ml_model = None
        model_path = Path(__file__).parent.parent / "ml" / "Automation" / "ml_pipeline" / "models" / "fraud_model.json"
        if HAVE_XGB and model_path.exists():
            self.ml_model = xgb.Booster()
            self.ml_model.load_model(str(model_path))
            logger.info(f"Loaded ML model from {model_path}")
    
    def iter_parquet_files(self) -> Generator[Path, None, None]:
        """Iterate through parquet files in chronological order."""
        files = sorted(self.input_dir.glob("eth_transactions_*.parquet"))
        if not files:
            raise FileNotFoundError(f"No parquet files found in {self.input_dir}")
        
        logger.info(f"Found {len(files)} parquet files")
        for f in files:
            yield f
    
    def iter_batches(self) -> Generator[pd.DataFrame, None, None]:
        """Stream data in batches across all files."""
        for parquet_file in self.iter_parquet_files():
            # Read in chunks
            df = pd.read_parquet(parquet_file)
            
            for start_idx in range(0, len(df), self.batch_size):
                end_idx = min(start_idx + self.batch_size, len(df))
                batch = df.iloc[start_idx:end_idx].copy()
                yield batch
            
            # Free memory
            del df
            gc.collect()
    
    def extract_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract ML features from transaction data."""
        features = pd.DataFrame()
        
        # Basic features
        features['value_eth'] = df['value_eth'].fillna(0)
        features['gas_price_gwei'] = df['gas_price_gwei'].fillna(0)
        features['gas_used'] = df['gas_used'].fillna(21000)
        features['gas_limit'] = df['gas_limit'].fillna(21000)
        
        # Derived features
        features['gas_efficiency'] = features['gas_used'] / features['gas_limit'].replace(0, 1)
        features['value_log'] = np.log1p(features['value_eth'])
        features['is_round_amount'] = ((features['value_eth'] * 100) % 1 < self.ROUND_AMOUNT_TOLERANCE).astype(int)
        
        # Time features if timestamp available
        if 'block_timestamp' in df.columns:
            try:
                ts = pd.to_datetime(df['block_timestamp'])
                features['hour'] = ts.dt.hour
                features['day_of_week'] = ts.dt.dayofweek
                features['is_weekend'] = (features['day_of_week'] >= 5).astype(int)
            except:
                features['hour'] = 12
                features['day_of_week'] = 0
                features['is_weekend'] = 0
        else:
            features['hour'] = 12
            features['day_of_week'] = 0
            features['is_weekend'] = 0
        
        return features
    
    def score_batch_ml(self, df: pd.DataFrame) -> np.ndarray:
        """Score a batch using ML model."""
        if self.ml_model is None:
            return np.zeros(len(df))
        
        features = self.extract_features(df)
        
        # Ensure column order matches training
        expected_cols = ['value_eth', 'gas_price_gwei', 'gas_used', 'gas_limit', 
                        'gas_efficiency', 'value_log', 'is_round_amount',
                        'hour', 'day_of_week', 'is_weekend']
        
        for col in expected_cols:
            if col not in features.columns:
                features[col] = 0
        
        features = features[expected_cols]
        dmatrix = xgb.DMatrix(features)
        scores = self.ml_model.predict(dmatrix)
        
        return scores
    
    def update_pattern_accumulators(self, df: pd.DataFrame):
        """Update pattern detection accumulators with new batch."""
        for _, row in df.iterrows():
            from_addr = row['from_address']
            to_addr = row['to_address']
            value = row.get('value_eth', 0)
            
            if from_addr:
                self.address_tx_counts[from_addr] += 1
                self.address_out_counts[from_addr] += 1
                self.address_values[from_addr].append(value)
            
            if to_addr:
                self.address_in_counts[to_addr] += 1
            
            # Track hourly activity
            if 'block_timestamp' in row and pd.notna(row['block_timestamp']):
                try:
                    ts = pd.to_datetime(row['block_timestamp'])
                    hour_key = ts.strftime('%Y-%m-%d-%H')
                    if from_addr:
                        self.hourly_tx[from_addr][hour_key] += 1
                except:
                    pass
    
    def detect_patterns(self, address: str) -> List[str]:
        """Detect fraud patterns for an address based on accumulated data."""
        patterns = []
        
        # Fan-out: sends to many addresses
        if self.address_out_counts[address] >= self.FAN_OUT_THRESHOLD:
            patterns.append("FAN_OUT")
        
        # Fan-in: receives from many addresses  
        if self.address_in_counts[address] >= self.FAN_IN_THRESHOLD:
            patterns.append("FAN_IN")
        
        # Rapid transactions
        hourly = self.hourly_tx.get(address, {})
        if any(count >= self.RAPID_TX_THRESHOLD for count in hourly.values()):
            patterns.append("RAPID_TX")
        
        # Round amounts (possible structuring)
        values = self.address_values.get(address, [])
        if values:
            round_count = sum(1 for v in values if abs(v - round(v)) < self.ROUND_AMOUNT_TOLERANCE)
            if len(values) >= 5 and round_count / len(values) > 0.8:
                patterns.append("ROUND_AMOUNTS")
        
        # Smurfing (many small transactions)
        if len(values) >= 10:
            small_tx = sum(1 for v in values if 0.1 <= v <= 1.0)
            if small_tx / len(values) > 0.7:
                patterns.append("SMURFING")
        
        return patterns
    
    def ingest_to_memgraph(self, df: pd.DataFrame):
        """Batch ingest transactions to Memgraph."""
        if self.memgraph is None:
            return
        
        cursor = self.memgraph.cursor()
        
        # Batch create nodes and edges
        batch_size = 1000
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i+batch_size]
            
            for _, row in batch.iterrows():
                try:
                    query = """
                    MERGE (from:Address {address: $from_addr})
                    MERGE (to:Address {address: $to_addr})
                    CREATE (from)-[:TX {
                        hash: $tx_hash,
                        value: $value,
                        timestamp: $timestamp
                    }]->(to)
                    """
                    cursor.execute(query, {
                        'from_addr': row['from_address'],
                        'to_addr': row['to_address'],
                        'tx_hash': row.get('tx_hash', ''),
                        'value': float(row.get('value_eth', 0)),
                        'timestamp': str(row.get('block_timestamp', ''))
                    })
                except Exception as e:
                    pass  # Continue on individual failures
        
        self.memgraph.commit()
    
    def process_batch(self, df: pd.DataFrame, batch_num: int) -> pd.DataFrame:
        """Process a single batch of transactions."""
        # ML scoring
        ml_scores = self.score_batch_ml(df)
        df['ml_score'] = ml_scores
        
        # Update pattern accumulators
        self.update_pattern_accumulators(df)
        
        # Ingest to graph database
        self.ingest_to_memgraph(df)
        
        # Update stats
        self.stats['total_transactions'] += len(df)
        high_risk = (ml_scores >= self.ML_THRESHOLD).sum()
        self.stats['flagged_transactions'] += high_risk
        
        return df
    
    def finalize_patterns(self) -> pd.DataFrame:
        """After all batches, compute final pattern detection results."""
        logger.info("Finalizing pattern detection across all addresses...")
        
        results = []
        all_addresses = set(self.address_tx_counts.keys()) | set(self.address_in_counts.keys())
        
        for addr in tqdm(all_addresses, desc="Detecting patterns"):
            patterns = self.detect_patterns(addr)
            
            if patterns:
                self.stats['patterns_detected'][','.join(sorted(patterns))] += 1
                
                result = {
                    'address': addr,
                    'patterns': patterns,
                    'pattern_count': len(patterns),
                    'total_tx': self.address_tx_counts[addr],
                    'out_count': self.address_out_counts[addr],
                    'in_count': self.address_in_counts[addr]
                }
                
                if len(patterns) >= 3:
                    self.stats['critical_addresses'].add(addr)
                    result['risk_level'] = 'CRITICAL'
                elif len(patterns) >= 2:
                    self.stats['high_risk_addresses'].add(addr)
                    result['risk_level'] = 'HIGH'
                else:
                    result['risk_level'] = 'MEDIUM'
                
                results.append(result)
        
        return pd.DataFrame(results)
    
    def run(self) -> Dict[str, Any]:
        """Run the full batch processing pipeline."""
        start_time = datetime.now()
        
        logger.info("=" * 60)
        logger.info("BATCH FRAUD DETECTION PIPELINE")
        logger.info("=" * 60)
        logger.info(f"Input: {self.input_dir}")
        logger.info(f"Output: {self.output_dir}")
        logger.info(f"Batch size: {self.batch_size:,}")
        logger.info("")
        
        # Process all batches
        batch_num = 0
        scored_batches = []
        
        for batch in tqdm(self.iter_batches(), desc="Processing batches"):
            batch_num += 1
            scored_batch = self.process_batch(batch, batch_num)
            
            # Save high-risk transactions from this batch
            high_risk = scored_batch[scored_batch['ml_score'] >= self.ML_THRESHOLD]
            if len(high_risk) > 0:
                scored_batches.append(high_risk)
            
            # Periodic save and cleanup
            if batch_num % 10 == 0:
                gc.collect()
        
        # Save all flagged transactions
        if scored_batches:
            flagged_df = pd.concat(scored_batches, ignore_index=True)
            flagged_df.to_parquet(self.output_dir / "flagged_transactions.parquet", index=False)
            logger.info(f"Saved {len(flagged_df):,} flagged transactions")
        
        # Finalize pattern detection
        patterns_df = self.finalize_patterns()
        if len(patterns_df) > 0:
            patterns_df.to_parquet(self.output_dir / "pattern_addresses.parquet", index=False)
            patterns_df.to_csv(self.output_dir / "pattern_addresses.csv", index=False)
            logger.info(f"Saved {len(patterns_df):,} addresses with patterns")
        
        # Calculate processing time
        end_time = datetime.now()
        self.stats['processing_time_seconds'] = (end_time - start_time).total_seconds()
        
        # Convert sets to counts for JSON serialization
        final_stats = {
            'total_transactions': self.stats['total_transactions'],
            'flagged_transactions': self.stats['flagged_transactions'],
            'critical_address_count': len(self.stats['critical_addresses']),
            'high_risk_address_count': len(self.stats['high_risk_addresses']),
            'patterns_detected': dict(self.stats['patterns_detected']),
            'processing_time_seconds': self.stats['processing_time_seconds'],
            'transactions_per_second': self.stats['total_transactions'] / max(1, self.stats['processing_time_seconds'])
        }
        
        # Save stats
        with open(self.output_dir / "pipeline_stats.json", "w") as f:
            json.dump(final_stats, f, indent=2)
        
        # Save critical addresses list
        with open(self.output_dir / "critical_addresses.txt", "w") as f:
            for addr in sorted(self.stats['critical_addresses']):
                f.write(f"{addr}\n")
        
        # Print summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("PIPELINE COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total transactions processed: {final_stats['total_transactions']:,}")
        logger.info(f"Flagged by ML: {final_stats['flagged_transactions']:,}")
        logger.info(f"Critical addresses: {final_stats['critical_address_count']:,}")
        logger.info(f"High risk addresses: {final_stats['high_risk_address_count']:,}")
        logger.info(f"Processing time: {final_stats['processing_time_seconds']:.1f} seconds")
        logger.info(f"Throughput: {final_stats['transactions_per_second']:,.0f} tx/sec")
        
        return final_stats


def main():
    parser = argparse.ArgumentParser(description="Batch fraud detection pipeline")
    parser.add_argument("--input", type=str, required=True, help="Input directory with parquet files")
    parser.add_argument("--output", type=str, default="./processed", help="Output directory")
    parser.add_argument("--batch-size", type=int, default=100000, help="Batch size (default: 100000)")
    parser.add_argument("--memgraph-host", type=str, default="localhost", help="Memgraph host")
    parser.add_argument("--memgraph-port", type=int, default=7687, help="Memgraph port")
    
    args = parser.parse_args()
    
    pipeline = BatchFraudPipeline(
        input_dir=args.input,
        output_dir=args.output,
        batch_size=args.batch_size,
        memgraph_host=args.memgraph_host,
        memgraph_port=args.memgraph_port
    )
    
    pipeline.run()


if __name__ == "__main__":
    main()
