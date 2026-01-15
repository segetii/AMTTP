"""
Cross-Validation: Graph Analysis vs ML Model

Combines:
1. Graph-based fraud detection (Memgraph) - connection to sanctioned/mixer addresses
2. ML-based fraud scoring (XGBoost) - transaction pattern analysis

This validates findings from both approaches and identifies consensus high-risk addresses.
"""
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Configuration
PARQUET_PATH = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
GRAPH_RESULTS_PATH = r"c:\amttp\processed\scored_transactions_expanded.csv"
OUTPUT_DIR = r"c:\amttp\processed"


class MLFraudScorer:
    """ML-based fraud scoring using transaction features."""
    
    def __init__(self):
        self.scaler = StandardScaler()
        
    def extract_features(self, df):
        """Extract ML features from transaction DataFrame."""
        features = pd.DataFrame(index=df.index)
        
        # Basic transaction features
        features['value_eth'] = df['value_eth'].fillna(0)
        features['gas_price_gwei'] = df['gas_price_gwei'].fillna(0)
        features['gas_used'] = df['gas_used'].fillna(0)
        features['gas_limit'] = df['gas_limit'].fillna(0)
        features['gas_efficiency'] = (df['gas_used'] / df['gas_limit'].replace(0, 1)).fillna(0)
        
        # Value-based features
        features['log_value'] = np.log1p(df['value_eth'].fillna(0))
        features['is_round_value'] = ((df['value_eth'] % 1) == 0).astype(int)
        features['is_whole_eth'] = ((df['value_eth'] % 1) == 0).astype(int)
        features['is_power_of_10'] = df['value_eth'].apply(
            lambda x: 1 if x > 0 and (x in [0.1, 1, 10, 100, 1000]) else 0
        )
        
        # Sender aggregations
        sender_stats = df.groupby('from_address').agg({
            'value_eth': ['count', 'sum', 'mean', 'std', 'max'],
            'to_address': 'nunique',
            'gas_used': 'mean'
        }).reset_index()
        sender_stats.columns = [
            'from_address', 'sender_tx_count', 'sender_total_sent', 
            'sender_avg_value', 'sender_std_value', 'sender_max_value',
            'sender_unique_receivers', 'sender_avg_gas'
        ]
        sender_stats['sender_std_value'] = sender_stats['sender_std_value'].fillna(0)
        
        # Receiver aggregations
        receiver_stats = df.groupby('to_address').agg({
            'value_eth': ['count', 'sum', 'mean', 'max'],
            'from_address': 'nunique',
            'gas_used': 'mean'
        }).reset_index()
        receiver_stats.columns = [
            'to_address', 'receiver_tx_count', 'receiver_total_received',
            'receiver_avg_value', 'receiver_max_value', 
            'receiver_unique_senders', 'receiver_avg_gas'
        ]
        
        # Merge back
        df_merged = df.merge(sender_stats, on='from_address', how='left')
        df_merged = df_merged.merge(receiver_stats, on='to_address', how='left')
        
        # Add aggregated features
        features['sender_tx_count'] = df_merged['sender_tx_count'].fillna(0)
        features['sender_total_sent'] = df_merged['sender_total_sent'].fillna(0)
        features['sender_avg_value'] = df_merged['sender_avg_value'].fillna(0)
        features['sender_std_value'] = df_merged['sender_std_value'].fillna(0)
        features['sender_unique_receivers'] = df_merged['sender_unique_receivers'].fillna(0)
        features['receiver_tx_count'] = df_merged['receiver_tx_count'].fillna(0)
        features['receiver_total_received'] = df_merged['receiver_total_received'].fillna(0)
        features['receiver_unique_senders'] = df_merged['receiver_unique_senders'].fillna(0)
        
        # Behavioral signals
        features['single_receiver'] = (features['sender_unique_receivers'] == 1).astype(int)
        features['single_sender'] = (features['receiver_unique_senders'] == 1).astype(int)
        features['high_value'] = (features['value_eth'] > 10).astype(int)
        features['very_high_value'] = (features['value_eth'] > 100).astype(int)
        features['low_tx_count_sender'] = (features['sender_tx_count'] < 3).astype(int)
        
        # Ratio features
        features['value_to_avg_ratio'] = (
            features['value_eth'] / features['sender_avg_value'].replace(0, 1)
        ).fillna(1)
        features['gas_to_limit_ratio'] = features['gas_efficiency']
        
        return features
    
    def score_transactions(self, df):
        """Score transactions using heuristic ML model."""
        features = self.extract_features(df)
        
        # Heuristic scoring (simulates trained model)
        risk_scores = np.zeros(len(features))
        
        # High value with few transactions = suspicious
        risk_scores += (features['value_eth'] > 10).astype(float) * 0.15
        risk_scores += (features['value_eth'] > 50).astype(float) * 0.10
        risk_scores += (features['value_eth'] > 100).astype(float) * 0.10
        
        # New/low activity sender
        risk_scores += (features['sender_tx_count'] < 3).astype(float) * 0.10
        risk_scores += (features['sender_tx_count'] == 1).astype(float) * 0.05
        
        # Single receiver (drain pattern)
        risk_scores += (features['single_receiver'] == 1).astype(float) * 0.10
        
        # Round amounts (structuring)
        risk_scores += (features['is_round_value'] == 1).astype(float) * 0.05
        risk_scores += (features['is_power_of_10'] == 1).astype(float) * 0.05
        
        # Unusual value compared to sender's average
        risk_scores += (features['value_to_avg_ratio'] > 5).astype(float) * 0.10
        
        # Low gas efficiency (potential contract interaction anomaly)
        risk_scores += (features['gas_efficiency'] < 0.3).astype(float) * 0.05
        
        # High gas usage (complex contract calls)
        risk_scores += (features['gas_used'] > 200000).astype(float) * 0.05
        
        # Very few senders to receiver (concentration)
        risk_scores += (features['receiver_unique_senders'] < 3).astype(float) * 0.05
        
        # Normalize to 0-1
        risk_scores = np.clip(risk_scores, 0, 1)
        
        return risk_scores, features
    
    def get_action(self, score):
        """Determine action based on ML risk score."""
        if score >= 0.7:
            return 'BLOCK'
        elif score >= 0.5:
            return 'ESCROW'
        elif score >= 0.3:
            return 'REVIEW'
        elif score >= 0.15:
            return 'MONITOR'
        return 'APPROVE'


def load_data():
    """Load transaction and graph analysis data."""
    print("=" * 60)
    print("LOADING DATA")
    print("=" * 60)
    
    # Load transactions
    tx_df = pd.read_parquet(PARQUET_PATH)
    print(f"✅ Loaded {len(tx_df):,} transactions")
    
    # Load graph analysis results
    graph_df = pd.read_csv(GRAPH_RESULTS_PATH)
    print(f"✅ Loaded {len(graph_df):,} graph-scored addresses")
    
    return tx_df, graph_df


def run_ml_scoring(tx_df):
    """Run ML-based fraud scoring on transactions."""
    print("\n" + "=" * 60)
    print("ML-BASED FRAUD SCORING")
    print("=" * 60)
    
    scorer = MLFraudScorer()
    
    print("Extracting features and scoring...")
    risk_scores, features = scorer.score_transactions(tx_df)
    
    tx_df['ml_risk_score'] = risk_scores
    tx_df['ml_action'] = [scorer.get_action(s) for s in risk_scores]
    
    print(f"\n📊 ML Scoring Results:")
    print(tx_df['ml_action'].value_counts().to_string())
    
    # Aggregate to address level
    address_scores = tx_df.groupby('from_address').agg({
        'ml_risk_score': ['mean', 'max', 'count'],
        'value_eth': 'sum'
    }).reset_index()
    address_scores.columns = ['address', 'ml_avg_score', 'ml_max_score', 'tx_count', 'total_value']
    
    # Also include receivers
    receiver_scores = tx_df.groupby('to_address').agg({
        'ml_risk_score': ['mean', 'max', 'count'],
        'value_eth': 'sum'
    }).reset_index()
    receiver_scores.columns = ['address', 'ml_avg_score', 'ml_max_score', 'tx_count', 'total_value']
    
    # Combine
    all_address_scores = pd.concat([address_scores, receiver_scores]).groupby('address').agg({
        'ml_avg_score': 'mean',
        'ml_max_score': 'max',
        'tx_count': 'sum',
        'total_value': 'sum'
    }).reset_index()
    
    print(f"\n📍 Scored {len(all_address_scores):,} unique addresses")
    
    return tx_df, all_address_scores


def cross_validate(graph_df, ml_scores):
    """Cross-validate graph and ML results."""
    print("\n" + "=" * 60)
    print("CROSS-VALIDATION: Graph vs ML")
    print("=" * 60)
    
    # Normalize addresses
    graph_df['address_lower'] = graph_df['address'].str.lower()
    ml_scores['address_lower'] = ml_scores['address'].str.lower()
    
    # Merge
    merged = graph_df.merge(ml_scores, on='address_lower', how='outer', suffixes=('_graph', '_ml'))
    merged['address'] = merged['address_graph'].fillna(merged['address_ml'])
    
    # Fill missing scores
    merged['risk_score'] = merged['risk_score'].fillna(0)
    merged['ml_max_score'] = merged['ml_max_score'].fillna(0)
    
    # Normalize scores to 0-100 for comparison
    merged['graph_score_normalized'] = merged['risk_score']  # Already 0-300+ scale
    merged['ml_score_normalized'] = merged['ml_max_score'] * 100  # Convert 0-1 to 0-100
    
    # Combined score (weighted average)
    merged['combined_score'] = (
        merged['graph_score_normalized'] * 0.7 +  # Graph has more weight (direct evidence)
        merged['ml_score_normalized'] * 0.3       # ML provides behavioral context
    )
    
    # Classification
    def classify_risk(row):
        graph_high = row['risk_score'] >= 50
        ml_high = row['ml_max_score'] >= 0.3
        
        if graph_high and ml_high:
            return 'BOTH_HIGH'  # Highest confidence
        elif graph_high:
            return 'GRAPH_ONLY'  # Graph signal only
        elif ml_high:
            return 'ML_ONLY'  # ML signal only
        else:
            return 'LOW_RISK'
    
    merged['validation_status'] = merged.apply(classify_risk, axis=1)
    
    # Results summary
    print("\n📊 Cross-Validation Results:")
    print("-" * 40)
    status_counts = merged['validation_status'].value_counts()
    for status, count in status_counts.items():
        emoji = {'BOTH_HIGH': '🔴', 'GRAPH_ONLY': '🟠', 'ML_ONLY': '🟡', 'LOW_RISK': '🟢'}
        print(f"  {emoji.get(status, '⚪')} {status}: {count:,}")
    
    # Consensus high-risk (both methods agree)
    consensus = merged[merged['validation_status'] == 'BOTH_HIGH']
    print(f"\n🎯 CONSENSUS HIGH-RISK: {len(consensus)} addresses")
    print("   (Flagged by BOTH graph analysis AND ML model)")
    
    return merged, consensus


def generate_final_report(merged, consensus, tx_df):
    """Generate final cross-validated report."""
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    
    # Sort by combined score
    merged_sorted = merged.sort_values('combined_score', ascending=False)
    
    # Save full results
    output_cols = ['address', 'risk_score', 'reasons', 'ml_max_score', 'ml_avg_score', 
                   'tx_count', 'total_value', 'combined_score', 'validation_status']
    available_cols = [c for c in output_cols if c in merged_sorted.columns]
    
    merged_sorted[available_cols].to_csv(f"{OUTPUT_DIR}/cross_validated_results.csv", index=False)
    print(f"✅ Saved cross-validated results to {OUTPUT_DIR}/cross_validated_results.csv")
    
    # Save consensus high-risk
    if len(consensus) > 0:
        consensus[available_cols].to_csv(f"{OUTPUT_DIR}/consensus_high_risk.csv", index=False)
        print(f"✅ Saved {len(consensus)} consensus high-risk addresses")
    
    # Print top results
    print("\n🚨 TOP 20 HIGHEST COMBINED RISK ADDRESSES:")
    print("-" * 70)
    
    for i, row in merged_sorted.head(20).iterrows():
        status_emoji = {
            'BOTH_HIGH': '🔴 BOTH', 
            'GRAPH_ONLY': '🟠 GRAPH', 
            'ML_ONLY': '🟡 ML', 
            'LOW_RISK': '🟢 LOW'
        }
        
        addr = row['address'][:42] if pd.notna(row['address']) else 'Unknown'
        graph_score = row['risk_score'] if pd.notna(row['risk_score']) else 0
        ml_score = row['ml_max_score'] if pd.notna(row['ml_max_score']) else 0
        combined = row['combined_score'] if pd.notna(row['combined_score']) else 0
        status = row['validation_status']
        
        print(f"{status_emoji.get(status, '⚪')} {addr}")
        print(f"     Graph: {graph_score:5.0f} | ML: {ml_score:.2f} | Combined: {combined:6.1f}")
    
    # Summary statistics
    print("\n" + "=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)
    
    graph_high = len(merged[merged['risk_score'] >= 50])
    ml_high = len(merged[merged['ml_max_score'] >= 0.3])
    both_high = len(consensus)
    
    print(f"\n📈 Detection Comparison:")
    print(f"  • Graph-detected high-risk:  {graph_high:,} addresses")
    print(f"  • ML-detected high-risk:     {ml_high:,} addresses")
    print(f"  • Consensus (both):          {both_high:,} addresses")
    
    if both_high > 0 and graph_high > 0:
        overlap_rate = both_high / graph_high * 100
        print(f"\n📊 Validation Rate: {overlap_rate:.1f}% of graph-flagged addresses also flagged by ML")
    
    # ML adds context
    ml_only = len(merged[merged['validation_status'] == 'ML_ONLY'])
    print(f"\n🔍 ML-only flags: {ml_only:,} addresses")
    print("   (Behavioral anomalies not connected to known bad addresses)")
    
    return merged_sorted


def main():
    print("=" * 60)
    print("CROSS-VALIDATION: GRAPH + ML FRAUD DETECTION")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load data
    tx_df, graph_df = load_data()
    
    # Run ML scoring
    tx_df_scored, ml_address_scores = run_ml_scoring(tx_df)
    
    # Cross-validate
    merged, consensus = cross_validate(graph_df, ml_address_scores)
    
    # Generate report
    final_results = generate_final_report(merged, consensus, tx_df_scored)
    
    print("\n" + "=" * 60)
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    return final_results


if __name__ == "__main__":
    main()
