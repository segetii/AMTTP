"""
AMTTP ML Inference Pipeline

Runs fraud detection inference on the full Ethereum dataset.
Uses the trained XGBoost model with address-level aggregation.

Usage:
    python run_inference.py
    python run_inference.py --input "C:/path/to/eth_data.parquet"
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
from typing import Dict, List, Any

import pandas as pd
import numpy as np
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
ML_DIR = PROJECT_ROOT / "ml" / "Automation" / "ml_pipeline"
MODEL_PATH = ML_DIR / "models" / "trained" / "xgb.json"
FEATURE_SCHEMA_PATH = ML_DIR / "models" / "feature_schema.json"
OUTPUT_DIR = PROJECT_ROOT / "processed" / "inference_results"


class EthereumFeatureExtractor:
    """
    Extract ML features from raw Ethereum transactions.
    
    Aggregates transactions by address to compute:
    - Transaction frequency and timing patterns
    - Value statistics (sent, received)
    - Gas usage patterns
    - Network metrics (unique counterparties)
    """
    
    def __init__(self):
        self.feature_schema = None
        if FEATURE_SCHEMA_PATH.exists():
            with open(FEATURE_SCHEMA_PATH) as f:
                self.feature_schema = json.load(f)
                logger.info(f"Loaded feature schema: {len(self.feature_schema.get('feature_names', []))} features")
    
    def aggregate_by_address(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate raw transactions to address-level features.
        Each address gets one row with computed metrics.
        """
        logger.info("Aggregating transactions by address...")
        
        # Ensure proper types
        df['value_eth'] = pd.to_numeric(df['value_eth'], errors='coerce').fillna(0)
        df['gas_price_gwei'] = pd.to_numeric(df['gas_price_gwei'], errors='coerce').fillna(0)
        df['gas_used'] = pd.to_numeric(df['gas_used'], errors='coerce').fillna(21000)
        df['gas_limit'] = pd.to_numeric(df['gas_limit'], errors='coerce').fillna(21000)
        
        # Convert timestamp
        if 'block_timestamp' in df.columns:
            df['block_timestamp'] = pd.to_datetime(df['block_timestamp'], utc=True, errors='coerce')
        
        # Sent transactions aggregation
        sent_agg = df.groupby('from_address').agg({
            'value_eth': ['sum', 'mean', 'max', 'min', 'std', 'count'],
            'gas_price_gwei': ['mean', 'max'],
            'gas_used': ['sum', 'mean'],
            'gas_limit': ['sum', 'mean'],
            'to_address': 'nunique',
            'block_timestamp': ['min', 'max'],
            'nonce': 'max'
        }).reset_index()
        
        # Flatten column names
        sent_agg.columns = ['address', 
                           'total_ether_sent', 'avg_val_sent', 'max_val_sent', 'min_val_sent', 'std_val_sent', 'sent_tnx',
                           'avg_gas_price', 'max_gas_price',
                           'total_gas_used', 'avg_gas_used',
                           'total_gas_limit', 'avg_gas_limit',
                           'unique_sent_to', 
                           'first_sent_time', 'last_sent_time',
                           'max_nonce']
        
        # Received transactions aggregation
        received_agg = df.groupby('to_address').agg({
            'value_eth': ['sum', 'mean', 'max', 'min', 'std', 'count'],
            'from_address': 'nunique',
            'block_timestamp': ['min', 'max']
        }).reset_index()
        
        received_agg.columns = ['address',
                               'total_ether_received', 'avg_val_received', 'max_value_received', 'min_value_received', 'std_val_received', 'received_tnx',
                               'unique_received_from',
                               'first_received_time', 'last_received_time']
        
        # Merge sent and received
        features = pd.merge(sent_agg, received_agg, on='address', how='outer')
        
        # Fill NaN with 0 for counts
        fill_zeros = ['total_ether_sent', 'sent_tnx', 'total_ether_received', 'received_tnx',
                     'unique_sent_to', 'unique_received_from', 'max_nonce']
        for col in fill_zeros:
            if col in features.columns:
                features[col] = features[col].fillna(0)
        
        # Compute derived features
        features['total_ether_balance'] = features['total_ether_received'] - features['total_ether_sent']
        features['neighbors'] = features['unique_sent_to'].fillna(0) + features['unique_received_from'].fillna(0)
        
        # Time features
        features['time_diff_between_first_and_last_(mins)'] = 0.0
        for idx, row in features.iterrows():
            try:
                first_time = min(
                    pd.Timestamp(row['first_sent_time']) if pd.notna(row.get('first_sent_time')) else pd.Timestamp.max,
                    pd.Timestamp(row['first_received_time']) if pd.notna(row.get('first_received_time')) else pd.Timestamp.max
                )
                last_time = max(
                    pd.Timestamp(row['last_sent_time']) if pd.notna(row.get('last_sent_time')) else pd.Timestamp.min,
                    pd.Timestamp(row['last_received_time']) if pd.notna(row.get('last_received_time')) else pd.Timestamp.min
                )
                if first_time != pd.Timestamp.max and last_time != pd.Timestamp.min:
                    features.at[idx, 'time_diff_between_first_and_last_(mins)'] = (last_time - first_time).total_seconds() / 60
            except:
                pass
        
        # Compute avg time between transactions
        features['avg_min_between_sent_tnx'] = features['time_diff_between_first_and_last_(mins)'] / features['sent_tnx'].replace(0, 1)
        features['avg_min_between_received_tnx'] = features['time_diff_between_first_and_last_(mins)'] / features['received_tnx'].replace(0, 1)
        
        # Additional computed features to match schema
        features['count'] = features['sent_tnx'] + features['received_tnx']
        features['income'] = features['total_ether_received'] - features['total_ether_sent']
        features['looped'] = 0  # Would require graph analysis
        features['number_of_created_contracts'] = 0  # Would require contract creation detection
        features['flag'] = 0  # Target variable placeholder
        
        # ERC20 placeholders (zeros since we only have ETH data)
        erc20_cols = [
            'erc20_avg_time_between_contract_tnx', 'erc20_avg_time_between_rec_2_tnx',
            'erc20_avg_time_between_rec_tnx', 'erc20_avg_time_between_sent_tnx',
            'erc20_avg_val_rec', 'erc20_avg_val_sent', 'erc20_avg_val_sent_contract',
            'erc20_max_val_rec', 'erc20_max_val_sent', 'erc20_max_val_sent_contract',
            'erc20_min_val_rec', 'erc20_min_val_sent', 'erc20_min_val_sent_contract',
            'erc20_total_ether_received', 'erc20_total_ether_sent', 'erc20_total_ether_sent_contract',
            'erc20_uniq_rec_addr', 'erc20_uniq_rec_contract_addr', 'erc20_uniq_rec_token_name',
            'erc20_uniq_sent_addr', 'erc20_uniq_sent_addr.1', 'erc20_uniq_sent_token_name',
            'total_erc20_tnxs'
        ]
        for col in erc20_cols:
            features[col] = 0.0
        
        # Contract interaction placeholders
        features['avg_value_sent_to_contract'] = 0.0
        features['max_val_sent_to_contract'] = 0.0
        features['min_value_sent_to_contract'] = 0.0
        
        logger.info(f"Aggregated to {len(features):,} unique addresses")
        return features
    
    def align_to_schema(self, features: pd.DataFrame) -> pd.DataFrame:
        """Align features to match the trained model's expected schema."""
        if self.feature_schema is None:
            return features
        
        expected_features = self.feature_schema.get('feature_names', [])
        
        # Create aligned DataFrame
        aligned = pd.DataFrame(index=features.index)
        
        for col in expected_features:
            if col in features.columns:
                aligned[col] = features[col]
            else:
                # Fill missing with zeros
                aligned[col] = 0.0
        
        # Fill any NaN values
        aligned = aligned.fillna(0.0)
        
        return aligned


class FraudPredictor:
    """
    Predict fraud risk using trained XGBoost model.
    """
    
    THRESHOLDS = {
        "BLOCK": 0.95,
        "ESCROW": 0.85,
        "REVIEW": 0.55,
        "MONITOR": 0.35,
        "APPROVE": 0.0
    }
    
    def __init__(self, model_path: Path = MODEL_PATH):
        import xgboost as xgb
        
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found at {model_path}")
        
        self.model = xgb.Booster()
        self.model.load_model(str(model_path))
        logger.info(f"Loaded XGBoost model from {model_path}")
    
    def predict(self, features: pd.DataFrame) -> pd.DataFrame:
        """Run prediction on feature matrix."""
        import xgboost as xgb
        
        # Ensure all numeric
        X = features.astype(np.float32).values
        
        # Create DMatrix
        dmatrix = xgb.DMatrix(X, feature_names=list(features.columns))
        
        # Predict
        logger.info("Running model inference...")
        scores = self.model.predict(dmatrix)
        
        # Assign actions based on thresholds
        results = pd.DataFrame({
            'risk_score': scores,
            'prediction': (scores >= 0.55).astype(int)
        })
        
        results['action'] = results['risk_score'].apply(self._get_action)
        results['risk_level'] = results['risk_score'].apply(self._get_risk_level)
        
        return results
    
    def _get_action(self, score: float) -> str:
        if score >= self.THRESHOLDS['BLOCK']:
            return 'BLOCK'
        elif score >= self.THRESHOLDS['ESCROW']:
            return 'ESCROW'
        elif score >= self.THRESHOLDS['REVIEW']:
            return 'REVIEW'
        elif score >= self.THRESHOLDS['MONITOR']:
            return 'MONITOR'
        else:
            return 'APPROVE'
    
    def _get_risk_level(self, score: float) -> str:
        if score >= 0.90:
            return 'CRITICAL'
        elif score >= 0.75:
            return 'HIGH'
        elif score >= 0.50:
            return 'MEDIUM'
        elif score >= 0.25:
            return 'LOW'
        else:
            return 'MINIMAL'


class PatternDetector:
    """
    Detect behavioral patterns indicating fraud.
    """
    
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.patterns = defaultdict(list)
    
    def detect_all(self) -> pd.DataFrame:
        """Run all pattern detections."""
        logger.info("Detecting behavioral patterns...")
        
        # Fan-out detection (sends to many addresses)
        fan_out = self.df.groupby('from_address')['to_address'].nunique()
        fan_out_addrs = fan_out[fan_out >= 10].index.tolist()
        for addr in fan_out_addrs:
            self.patterns[addr].append('FAN_OUT')
        
        # Fan-in detection (receives from many)
        fan_in = self.df.groupby('to_address')['from_address'].nunique()
        fan_in_addrs = fan_in[fan_in >= 10].index.tolist()
        for addr in fan_in_addrs:
            self.patterns[addr].append('FAN_IN')
        
        # Round amount detection (possible structuring)
        self.df['is_round'] = (self.df['value_eth'] % 1 == 0) & (self.df['value_eth'] > 0)
        round_agg = self.df.groupby('from_address').agg({
            'is_round': ['sum', 'count']
        })
        round_agg.columns = ['round_count', 'total_count']
        round_agg['round_ratio'] = round_agg['round_count'] / round_agg['total_count']
        structuring = round_agg[(round_agg['round_ratio'] > 0.8) & (round_agg['total_count'] >= 5)].index.tolist()
        for addr in structuring:
            self.patterns[addr].append('STRUCTURING')
        
        # High frequency detection
        if 'block_timestamp' in self.df.columns:
            self.df['hour'] = pd.to_datetime(self.df['block_timestamp']).dt.floor('H')
            hourly_counts = self.df.groupby(['from_address', 'hour']).size()
            rapid_tx = hourly_counts[hourly_counts >= 5].reset_index()['from_address'].unique().tolist()
            for addr in rapid_tx:
                self.patterns[addr].append('RAPID_TX')
        
        # Small value smurfing detection
        small_tx = self.df[(self.df['value_eth'] >= 0.1) & (self.df['value_eth'] <= 1.0)]
        smurf_agg = small_tx.groupby('from_address').size()
        smurfers = smurf_agg[smurf_agg >= 10].index.tolist()
        for addr in smurfers:
            self.patterns[addr].append('SMURFING')
        
        # Create patterns DataFrame
        pattern_results = []
        for addr, pats in self.patterns.items():
            pattern_results.append({
                'address': addr,
                'patterns': pats,
                'pattern_count': len(pats),
                'pattern_string': ','.join(sorted(pats))
            })
        
        logger.info(f"Detected {len(self.patterns):,} addresses with suspicious patterns")
        return pd.DataFrame(pattern_results)


def run_inference(input_file: str, output_dir: Path = OUTPUT_DIR):
    """
    Main inference pipeline.
    """
    start_time = time.time()
    
    print("=" * 70)
    print("AMTTP ML INFERENCE PIPELINE")
    print("=" * 70)
    print(f"Input: {input_file}")
    print(f"Output: {output_dir}")
    print()
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    logger.info(f"Loading data from {input_file}...")
    df = pd.read_parquet(input_file)
    logger.info(f"Loaded {len(df):,} transactions")
    
    # Feature extraction
    extractor = EthereumFeatureExtractor()
    features = extractor.aggregate_by_address(df)
    
    # Save address list for reference
    address_df = features[['address']].copy()
    
    # Align to model schema
    aligned_features = extractor.align_to_schema(features)
    
    # Run prediction
    predictor = FraudPredictor()
    predictions = predictor.predict(aligned_features)
    
    # Combine results
    results = pd.concat([address_df.reset_index(drop=True), predictions], axis=1)
    
    # Pattern detection
    pattern_detector = PatternDetector(df)
    patterns = pattern_detector.detect_all()
    
    # Merge patterns with predictions
    if len(patterns) > 0:
        results = results.merge(patterns, on='address', how='left')
        results['pattern_count'] = results['pattern_count'].fillna(0).astype(int)
        results['pattern_string'] = results['pattern_string'].fillna('')
    
    # Compute combined score
    results['combined_score'] = results['risk_score']
    if 'pattern_count' in results.columns:
        # Boost score based on pattern count
        results.loc[results['pattern_count'] >= 3, 'combined_score'] *= 1.5
        results.loc[results['pattern_count'] == 2, 'combined_score'] *= 1.3
        results.loc[results['pattern_count'] == 1, 'combined_score'] *= 1.1
        results['combined_score'] = results['combined_score'].clip(0, 1)
    
    # Final risk level based on combined score
    results['final_risk_level'] = results['combined_score'].apply(
        lambda x: 'CRITICAL' if x >= 0.90 else 'HIGH' if x >= 0.75 else 'MEDIUM' if x >= 0.50 else 'LOW' if x >= 0.25 else 'MINIMAL'
    )
    
    # Sort by risk score
    results = results.sort_values('combined_score', ascending=False)
    
    # Save results
    results.to_parquet(output_dir / "all_predictions.parquet", index=False)
    results.to_csv(output_dir / "all_predictions.csv", index=False)
    
    # Save high-risk subset
    high_risk = results[results['combined_score'] >= 0.55]
    high_risk.to_csv(output_dir / "high_risk_addresses.csv", index=False)
    
    critical = results[results['final_risk_level'] == 'CRITICAL']
    critical.to_csv(output_dir / "critical_addresses.csv", index=False)
    
    # Statistics
    elapsed = time.time() - start_time
    stats = {
        'input_file': input_file,
        'total_transactions': int(len(df)),
        'unique_addresses': int(len(results)),
        'risk_distribution': results['final_risk_level'].value_counts().to_dict(),
        'action_distribution': results['action'].value_counts().to_dict(),
        'high_risk_count': int(len(high_risk)),
        'critical_count': int(len(critical)),
        'addresses_with_patterns': int((results.get('pattern_count', 0) > 0).sum()) if 'pattern_count' in results else 0,
        'processing_time_seconds': round(elapsed, 2)
    }
    
    with open(output_dir / "inference_stats.json", "w") as f:
        json.dump(stats, f, indent=2)
    
    # Print summary
    print("\n" + "=" * 70)
    print("INFERENCE COMPLETE")
    print("=" * 70)
    print(f"\n📊 RESULTS SUMMARY:")
    print(f"   Total transactions processed: {stats['total_transactions']:,}")
    print(f"   Unique addresses analyzed:    {stats['unique_addresses']:,}")
    print(f"   Processing time:              {stats['processing_time_seconds']:.1f}s")
    print(f"\n🚨 RISK DISTRIBUTION:")
    for level in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'MINIMAL']:
        count = stats['risk_distribution'].get(level, 0)
        pct = count / stats['unique_addresses'] * 100
        print(f"   {level:10}: {count:>8,} ({pct:>5.2f}%)")
    
    print(f"\n📋 ACTION DISTRIBUTION:")
    for action in ['BLOCK', 'ESCROW', 'REVIEW', 'MONITOR', 'APPROVE']:
        count = stats['action_distribution'].get(action, 0)
        print(f"   {action:10}: {count:>8,}")
    
    print(f"\n📁 OUTPUT FILES:")
    print(f"   • {output_dir / 'all_predictions.csv'}")
    print(f"   • {output_dir / 'high_risk_addresses.csv'}")
    print(f"   • {output_dir / 'critical_addresses.csv'}")
    print(f"   • {output_dir / 'inference_stats.json'}")
    
    print("\n" + "=" * 70)
    
    return results, stats


def main():
    parser = argparse.ArgumentParser(description="Run ML inference on ETH transaction data")
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
    
    args = parser.parse_args()
    
    run_inference(args.input, Path(args.output))


if __name__ == "__main__":
    main()
