#!/usr/bin/env python3
"""
Cluster Analysis on Node2Vec Embeddings
Identify fraud patterns using DBSCAN/HDBSCAN clustering
"""

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
from collections import Counter

def main():
    print("=" * 60)
    print("NODE2VEC CLUSTER ANALYSIS - FRAUD PATTERN DETECTION")
    print("=" * 60)
    
    # Load embeddings
    data = np.load('c:/amttp/processed/node2vec_embeddings.npz', allow_pickle=True)
    embeddings = data['vectors']
    addresses = data['nodes']
    print(f'\nLoaded {len(embeddings)} embeddings (dim={embeddings.shape[1]})')
    
    # Standardize
    X = StandardScaler().fit_transform(embeddings)
    
    # DBSCAN clustering with cosine distance
    print('\nRunning DBSCAN clustering (eps=0.5, min_samples=5)...')
    db = DBSCAN(eps=0.5, min_samples=5, metric='cosine', n_jobs=-1)
    labels = db.fit_predict(X)
    
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = list(labels).count(-1)
    print(f'Clusters found: {n_clusters}')
    print(f'Noise points: {n_noise} ({100*n_noise/len(labels):.1f}%)')
    
    # Load fraud labels
    addr_df = pd.read_parquet('c:/amttp/processed/eth_addresses_labeled.parquet')
    fraud_set = set(addr_df[addr_df['fraud'] == 1]['address'].str.lower())
    print(f'\nKnown fraud addresses in dataset: {len(fraud_set)}')
    
    # Count fraud in embeddings
    fraud_in_embeddings = [a for a in addresses if a.lower() in fraud_set]
    print(f'Fraud addresses with embeddings: {len(fraud_in_embeddings)}')
    
    # Analyze cluster composition
    print('\n' + '=' * 60)
    print('CLUSTER FRAUD CONCENTRATION')
    print('=' * 60)
    
    cluster_fraud = {}
    for addr, lbl in zip(addresses, labels):
        if lbl not in cluster_fraud:
            cluster_fraud[lbl] = {'total': 0, 'fraud': 0, 'addrs': []}
        cluster_fraud[lbl]['total'] += 1
        if addr.lower() in fraud_set:
            cluster_fraud[lbl]['fraud'] += 1
            cluster_fraud[lbl]['addrs'].append(addr)
    
    # Sort by fraud count
    sorted_clusters = sorted(cluster_fraud.items(), key=lambda x: x[1]['fraud'], reverse=True)
    
    print(f'\n{"Cluster":<12} {"Size":>10} {"Fraud":>8} {"Fraud%":>10}')
    print('-' * 45)
    
    for cid, stats in sorted_clusters[:20]:
        if stats['total'] > 0:
            pct = 100 * stats['fraud'] / stats['total']
            name = 'NOISE' if cid == -1 else f'Cluster-{cid}'
            marker = ' ***' if pct > 5 and stats['fraud'] >= 2 else ''
            print(f'{name:<12} {stats["total"]:>10} {stats["fraud"]:>8} {pct:>9.2f}%{marker}')
    
    # Find high-fraud clusters
    print('\n' + '=' * 60)
    print('HIGH-FRAUD CLUSTERS (>2% fraud rate OR 3+ fraud addresses)')
    print('=' * 60)
    
    high_fraud = []
    for cid, stats in sorted_clusters:
        if cid == -1:
            continue  # Skip noise
        pct = 100 * stats['fraud'] / stats['total'] if stats['total'] > 0 else 0
        if stats['fraud'] >= 3 or (pct > 2 and stats['fraud'] >= 2):
            high_fraud.append((cid, stats, pct))
    
    if high_fraud:
        for cid, stats, pct in high_fraud:
            print(f'\n🔴 Cluster {cid}: {stats["fraud"]}/{stats["total"]} fraud ({pct:.1f}%)')
            print(f'   Fraud addresses:')
            for addr in stats['addrs'][:5]:
                print(f'     - {addr}')
            if len(stats['addrs']) > 5:
                print(f'     ... and {len(stats["addrs"]) - 5} more')
    else:
        print('\nNo high-concentration fraud clusters found.')
        print('Fraud addresses may be distributed across clusters.')
    
    # Cluster size distribution
    print('\n' + '=' * 60)
    print('CLUSTER SIZE DISTRIBUTION')
    print('=' * 60)
    
    sizes = [s['total'] for c, s in cluster_fraud.items() if c != -1]
    if sizes:
        print(f'Total clusters: {len(sizes)}')
        print(f'Largest cluster: {max(sizes)} addresses')
        print(f'Smallest cluster: {min(sizes)} addresses')
        print(f'Median cluster size: {np.median(sizes):.0f}')
        print(f'Mean cluster size: {np.mean(sizes):.1f}')
    
    # Fraud distribution analysis
    print('\n' + '=' * 60)
    print('FRAUD DISTRIBUTION ANALYSIS')
    print('=' * 60)
    
    fraud_in_clusters = sum(s['fraud'] for c, s in cluster_fraud.items() if c != -1)
    fraud_in_noise = cluster_fraud.get(-1, {}).get('fraud', 0)
    
    print(f'Fraud in clusters: {fraud_in_clusters}')
    print(f'Fraud in noise: {fraud_in_noise}')
    print(f'Total fraud with embeddings: {fraud_in_clusters + fraud_in_noise}')
    
    # Save results
    np.savez('c:/amttp/processed/node2vec_clusters.npz', 
             addresses=addresses, 
             clusters=labels,
             n_clusters=n_clusters)
    
    # Create cluster summary DataFrame
    cluster_df = pd.DataFrame({
        'address': addresses,
        'cluster': labels
    })
    cluster_df.to_parquet('c:/amttp/processed/address_clusters.parquet')
    
    print(f'\n✅ Saved cluster assignments to:')
    print(f'   - node2vec_clusters.npz')
    print(f'   - address_clusters.parquet')

if __name__ == '__main__':
    main()
