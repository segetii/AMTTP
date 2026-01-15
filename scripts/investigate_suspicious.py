#!/usr/bin/env python3
"""
Investigate suspicious addresses near fraud cluster
"""

import pandas as pd
import numpy as np

def main():
    # Load suspicious addresses
    suspicious = pd.read_csv('c:/amttp/processed/suspicious_near_fraud.csv')
    print('='*70)
    print('SUSPICIOUS ADDRESSES NEAR FRAUD CLUSTER')
    print('='*70)
    print(f'Total suspicious addresses: {len(suspicious)}')

    # Load full address data for context
    addr_df = pd.read_parquet('c:/amttp/processed/eth_addresses_labeled.parquet')
    addr_df['address'] = addr_df['address'].str.lower()

    # Merge to get details
    merged = suspicious.merge(addr_df, on='address', how='left')

    print(f'\nRisk Level Distribution:')
    print(merged['risk_level'].value_counts().to_string())

    print(f'\n' + '='*70)
    print('TOP 20 BY HYBRID SCORE (Most Suspicious)')
    print('='*70)
    
    top20 = merged.nlargest(20, 'hybrid_score')[['address', 'hybrid_score', 'risk_level', 'pattern_count', 'total_transactions']]
    
    for idx, row in top20.iterrows():
        addr = row['address'][:42]
        score = row['hybrid_score']
        risk = row['risk_level']
        patterns = row['pattern_count']
        txns = row['total_transactions']
        print(f"  {addr} | Score: {score:.2f} | Risk: {risk} | Patterns: {patterns} | Txns: {txns}")

    print(f'\n' + '='*70)
    print('STATISTICS FOR SUSPICIOUS ADDRESSES')
    print('='*70)
    
    print(f"  Avg hybrid_score: {merged['hybrid_score'].mean():.2f}")
    print(f"  Avg pattern_count: {merged['pattern_count'].mean():.1f}")
    print(f"  Avg transactions: {merged['total_transactions'].mean():.0f}")
    print(f"  Max hybrid_score: {merged['hybrid_score'].max():.2f}")
    
    # High risk breakdown
    high_risk = merged[merged['risk_level'].isin(['HIGH', 'CRITICAL'])]
    print(f"\n  HIGH/CRITICAL risk addresses: {len(high_risk)}")
    
    # Save high-priority for review
    high_priority = merged[merged['hybrid_score'] > 50].sort_values('hybrid_score', ascending=False)
    high_priority.to_csv('c:/amttp/processed/high_priority_review.csv', index=False)
    print(f"  Saved {len(high_priority)} high-priority addresses (score>50) to high_priority_review.csv")

if __name__ == '__main__':
    main()
