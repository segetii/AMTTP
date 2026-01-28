#!/usr/bin/env python3
"""
Generate Visualization Data from ML Training Dataset
Creates realistic mock data for Next.js and Flutter visualizations
Based on 920K+ real Ethereum transactions used for ML model training
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import random

def main():
    print("=" * 70)
    print("GENERATING VISUALIZATION DATA FROM ML TRAINING SET")
    print("=" * 70)
    
    # Load transaction data
    print("\n[1/5] Loading transaction data...")
    tx_df = pd.read_parquet('c:/amttp/processed/eth_transactions_labeled_balanced.parquet')
    print(f"   Loaded {len(tx_df):,} transactions")
    
    # Load address features with risk scores
    print("\n[2/5] Loading address features...")
    addr_df = pd.read_parquet('c:/amttp/processed/eth_addresses_labeled.parquet')
    print(f"   Loaded {len(addr_df):,} addresses")
    print(f"   Fraud addresses: {addr_df['fraud'].sum():,}")
    
    # Sample 20,000 transactions with balanced fraud representation
    print("\n[3/5] Sampling 20,000 transactions...")
    
    # Get fraud transactions (minority class)
    fraud_tx = tx_df[tx_df['fraud'] == 1]
    clean_tx = tx_df[tx_df['fraud'] == 0]
    
    # Sample with ~5% fraud rate (realistic for visualization)
    n_fraud = min(1000, len(fraud_tx))
    n_clean = 19000
    
    sampled_fraud = fraud_tx.sample(n=n_fraud, random_state=42)
    sampled_clean = clean_tx.sample(n=n_clean, random_state=42)
    sampled_tx = pd.concat([sampled_fraud, sampled_clean]).sample(frac=1, random_state=42)
    
    print(f"   Sampled: {len(sampled_tx):,} transactions")
    print(f"   Fraud rate: {sampled_tx['fraud'].mean() * 100:.2f}%")
    
    # Generate visualization-ready transaction data
    print("\n[4/5] Generating visualization data...")
    
    # Create address lookup for risk scores
    addr_risk = addr_df.set_index('address')[['hybrid_score', 'risk_level', 'fraud', 'total_transactions']].to_dict('index')
    
    transactions = []
    for idx, row in sampled_tx.iterrows():
        # Get sender risk info
        sender_info = addr_risk.get(row['from_address'], {
            'hybrid_score': random.uniform(0, 30),
            'risk_level': 'LOW',
            'fraud': 0,
            'total_transactions': random.randint(1, 100)
        })
        
        # Get receiver risk info
        receiver_info = addr_risk.get(row['to_address'], {
            'hybrid_score': random.uniform(0, 30),
            'risk_level': 'LOW',
            'fraud': 0,
            'total_transactions': random.randint(1, 100)
        })
        
        # Calculate combined risk score
        sender_risk = sender_info.get('hybrid_score', 0) or 0
        receiver_risk = receiver_info.get('hybrid_score', 0) or 0
        combined_risk = max(sender_risk, receiver_risk)
        
        # Determine risk level
        if combined_risk >= 80 or row['fraud'] == 1:
            risk_level = 'CRITICAL'
            status = 'flagged'
        elif combined_risk >= 60:
            risk_level = 'HIGH'
            status = 'flagged' if random.random() > 0.5 else 'pending'
        elif combined_risk >= 40:
            risk_level = 'MEDIUM'
            status = 'pending' if random.random() > 0.7 else 'approved'
        else:
            risk_level = 'LOW'
            status = 'approved'
        
        # Generate transaction patterns
        patterns = []
        if row['value_eth'] > 10:
            patterns.append('large_transfer')
        if sender_info.get('total_transactions', 0) < 5:
            patterns.append('new_address')
        if row['nonce'] == 0:
            patterns.append('first_transaction')
        if row['gas_price_gwei'] > 50:
            patterns.append('high_gas')
        if row['fraud'] == 1:
            patterns.append('known_fraud')
        
        tx_data = {
            'id': row['tx_hash'],
            'hash': row['tx_hash'],
            'blockNumber': int(row['block_number']),
            'timestamp': row['block_timestamp'].isoformat() if pd.notna(row['block_timestamp']) else datetime.now().isoformat(),
            'from': row['from_address'],
            'to': row['to_address'],
            'value': float(row['value_eth']),
            'valueUsd': float(row['value_eth']) * 2500,  # Approximate ETH price
            'gasPrice': float(row['gas_price_gwei']),
            'gasUsed': int(row['gas_used']),
            'gasLimit': int(row['gas_limit']),
            'nonce': int(row['nonce']),
            'transactionIndex': int(row['transaction_index']),
            'riskScore': min(100, max(0, combined_risk)),
            'riskLevel': risk_level,
            'status': status,
            'patterns': patterns,
            'senderRisk': min(100, max(0, sender_risk)),
            'receiverRisk': min(100, max(0, receiver_risk)),
            'isFraud': bool(row['fraud'] == 1),
            'senderFraud': bool(row['sender_fraud'] == 1),
            'receiverFraud': bool(row['receiver_fraud'] == 1)
        }
        transactions.append(tx_data)
    
    # Generate graph nodes from unique addresses
    print("\n[5/5] Generating graph data...")
    
    unique_addresses = set()
    for tx in transactions:
        unique_addresses.add(tx['from'])
        unique_addresses.add(tx['to'])
    
    nodes = []
    edges = []
    edge_counts = {}
    
    for addr in unique_addresses:
        info = addr_risk.get(addr, {
            'hybrid_score': random.uniform(0, 30),
            'risk_level': 'LOW',
            'fraud': 0,
            'total_transactions': random.randint(1, 50)
        })
        
        risk = info.get('hybrid_score', 0) or 0
        is_fraud = info.get('fraud', 0) == 1
        
        # Determine node type
        if is_fraud:
            node_type = 'fraud'
        elif risk >= 80:
            node_type = 'critical'
        elif risk >= 60:
            node_type = 'high_risk'
        elif risk >= 40:
            node_type = 'medium_risk'
        else:
            node_type = 'normal'
        
        nodes.append({
            'id': addr,
            'address': addr,
            'label': addr[:10] + '...',
            'riskScore': min(100, max(0, risk)),
            'riskLevel': info.get('risk_level', 'LOW'),
            'type': node_type,
            'isFraud': is_fraud,
            'transactionCount': info.get('total_transactions', 1)
        })
    
    # Generate edges from transactions
    for tx in transactions:
        edge_key = f"{tx['from']}_{tx['to']}"
        if edge_key not in edge_counts:
            edge_counts[edge_key] = {
                'source': tx['from'],
                'target': tx['to'],
                'count': 0,
                'totalValue': 0,
                'maxRisk': 0,
                'isFraud': False
            }
        edge_counts[edge_key]['count'] += 1
        edge_counts[edge_key]['totalValue'] += tx['value']
        edge_counts[edge_key]['maxRisk'] = max(edge_counts[edge_key]['maxRisk'], tx['riskScore'])
        edge_counts[edge_key]['isFraud'] = edge_counts[edge_key]['isFraud'] or tx['isFraud']
    
    edges = list(edge_counts.values())
    
    # Generate time series data for velocity heatmap
    velocity_data = []
    for day in range(7):  # Mon-Sun
        for hour in range(24):
            day_txs = [tx for tx in transactions 
                       if datetime.fromisoformat(tx['timestamp'].replace('Z', '+00:00')).weekday() == day 
                       and datetime.fromisoformat(tx['timestamp'].replace('Z', '+00:00')).hour == hour]
            velocity_data.append({
                'day': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][day],
                'hour': hour,
                'count': len(day_txs),
                'avgRisk': np.mean([tx['riskScore'] for tx in day_txs]) if day_txs else 0,
                'totalValue': sum([tx['value'] for tx in day_txs])
            })
    
    # Generate risk distribution data
    risk_distribution = []
    for bucket in range(0, 100, 10):
        bucket_txs = [tx for tx in transactions if bucket <= tx['riskScore'] < bucket + 10]
        risk_distribution.append({
            'range': f'{bucket}-{bucket + 10}',
            'rangeStart': bucket,
            'rangeEnd': bucket + 10,
            'count': len(bucket_txs),
            'fraudCount': len([tx for tx in bucket_txs if tx['isFraud']])
        })
    
    # Summary statistics
    summary = {
        'totalTransactions': len(transactions),
        'totalAddresses': len(nodes),
        'totalEdges': len(edges),
        'fraudTransactions': len([tx for tx in transactions if tx['isFraud']]),
        'flaggedTransactions': len([tx for tx in transactions if tx['status'] == 'flagged']),
        'criticalRisk': len([tx for tx in transactions if tx['riskLevel'] == 'CRITICAL']),
        'highRisk': len([tx for tx in transactions if tx['riskLevel'] == 'HIGH']),
        'mediumRisk': len([tx for tx in transactions if tx['riskLevel'] == 'MEDIUM']),
        'lowRisk': len([tx for tx in transactions if tx['riskLevel'] == 'LOW']),
        'avgRiskScore': np.mean([tx['riskScore'] for tx in transactions]),
        'totalValue': sum([tx['value'] for tx in transactions]),
        'avgValue': np.mean([tx['value'] for tx in transactions])
    }
    
    # Create output data
    output_data = {
        'metadata': {
            'generatedAt': datetime.now().isoformat(),
            'sourceDataset': 'eth_transactions_labeled_balanced.parquet',
            'totalSourceTransactions': len(tx_df),
            'sampledTransactions': len(transactions),
            'version': '1.0.0'
        },
        'summary': summary,
        'transactions': transactions,
        'graph': {
            'nodes': nodes,
            'edges': edges
        },
        'velocityHeatmap': velocity_data,
        'riskDistribution': risk_distribution
    }
    
    # Save to JSON
    output_path = 'c:/amttp/frontend/frontend/public/data/ml-visualization-data.json'
    print(f"\nSaving to {output_path}...")
    
    # Ensure directory exists
    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(output_data, f)
    
    print(f"\n✅ Generated visualization data:")
    print(f"   Transactions: {len(transactions):,}")
    print(f"   Addresses: {len(nodes):,}")
    print(f"   Edges: {len(edges):,}")
    print(f"   Fraud rate: {summary['fraudTransactions'] / summary['totalTransactions'] * 100:.2f}%")
    print(f"   File size: {os.path.getsize(output_path) / 1024 / 1024:.2f} MB")
    
    # Also create a smaller subset for quick loading
    quick_data = {
        'metadata': output_data['metadata'],
        'summary': summary,
        'transactions': transactions[:1000],  # First 1000 for quick load
        'graph': {
            'nodes': nodes[:500],
            'edges': edges[:1000]
        },
        'velocityHeatmap': velocity_data,
        'riskDistribution': risk_distribution
    }
    
    quick_path = 'c:/amttp/frontend/frontend/public/data/ml-visualization-quick.json'
    with open(quick_path, 'w') as f:
        json.dump(quick_data, f)
    
    print(f"   Quick load file: {os.path.getsize(quick_path) / 1024:.2f} KB")
    
    print("\n" + "=" * 70)
    print("VISUALIZATION DATA GENERATION COMPLETE")
    print("=" * 70)

if __name__ == '__main__':
    main()
