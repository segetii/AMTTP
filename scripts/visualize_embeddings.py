#!/usr/bin/env python3
"""
Node2Vec Embedding Visualization with t-SNE and UMAP
Visualize fraud patterns in embedding space
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.manifold import TSNE
from sklearn.preprocessing import StandardScaler

def main():
    print("=" * 70)
    print("NODE2VEC EMBEDDING VISUALIZATION")
    print("=" * 70)
    
    # Load embeddings
    print("\n[1/4] Loading Node2Vec embeddings...")
    emb_data = np.load('c:/amttp/processed/node2vec_embeddings.npz', allow_pickle=True)
    nodes = emb_data['nodes']
    vectors = emb_data['vectors']
    print(f"   Loaded {len(nodes)} embeddings (dim={vectors.shape[1]})")
    
    # Load fraud labels
    print("\n[2/4] Loading fraud labels...")
    addr_df = pd.read_parquet('c:/amttp/processed/eth_addresses_labeled.parquet')
    addr_df['address'] = addr_df['address'].str.lower()
    fraud_set = set(addr_df[addr_df['fraud'] == 1]['address'])
    
    # Create labels array
    labels = np.array([1 if n.lower() in fraud_set else 0 for n in nodes])
    print(f"   Fraud nodes: {labels.sum()}")
    print(f"   Non-fraud nodes: {(labels == 0).sum()}")
    
    # Sample for visualization (too many points = slow)
    print("\n[3/4] Sampling for visualization...")
    n_fraud = labels.sum()
    n_sample_legit = min(5000, (labels == 0).sum())  # Sample legitimate
    
    fraud_idx = np.where(labels == 1)[0]
    legit_idx = np.where(labels == 0)[0]
    sampled_legit_idx = np.random.choice(legit_idx, n_sample_legit, replace=False)
    
    sample_idx = np.concatenate([fraud_idx, sampled_legit_idx])
    np.random.shuffle(sample_idx)
    
    X_sample = vectors[sample_idx]
    y_sample = labels[sample_idx]
    nodes_sample = nodes[sample_idx]
    
    print(f"   Sampled: {len(X_sample)} nodes ({y_sample.sum()} fraud)")
    
    # Standardize
    X_scaled = StandardScaler().fit_transform(X_sample)
    
    # t-SNE
    print("\n[4/4] Running t-SNE (this may take a minute)...")
    tsne = TSNE(
        n_components=2,
        perplexity=50,
        learning_rate=200,
        max_iter=1000,
        random_state=42,
        n_jobs=-1
    )
    X_tsne = tsne.fit_transform(X_scaled)
    print("   t-SNE complete!")
    
    # Create visualization
    print("\n[5/5] Creating visualizations...")
    
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    
    # Plot 1: All points
    ax1 = axes[0]
    
    # Plot non-fraud first (background)
    mask_legit = y_sample == 0
    ax1.scatter(
        X_tsne[mask_legit, 0], 
        X_tsne[mask_legit, 1],
        c='lightblue',
        s=10,
        alpha=0.3,
        label=f'Legitimate ({mask_legit.sum():,})'
    )
    
    # Plot fraud on top
    mask_fraud = y_sample == 1
    ax1.scatter(
        X_tsne[mask_fraud, 0], 
        X_tsne[mask_fraud, 1],
        c='red',
        s=50,
        alpha=0.8,
        marker='x',
        linewidths=2,
        label=f'Fraud ({mask_fraud.sum()})'
    )
    
    ax1.set_title('t-SNE of Node2Vec Embeddings\n(Fraud Detection)', fontsize=14, fontweight='bold')
    ax1.set_xlabel('t-SNE 1')
    ax1.set_ylabel('t-SNE 2')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Fraud focus with density
    ax2 = axes[1]
    
    # Plot fraud points with their immediate neighbors
    fraud_coords = X_tsne[mask_fraud]
    
    # Contour density for all points
    from scipy.stats import gaussian_kde
    
    try:
        # Density estimation
        xy = X_tsne.T
        kde = gaussian_kde(xy)
        
        # Create grid
        x_min, x_max = X_tsne[:, 0].min() - 5, X_tsne[:, 0].max() + 5
        y_min, y_max = X_tsne[:, 1].min() - 5, X_tsne[:, 1].max() + 5
        xx, yy = np.mgrid[x_min:x_max:100j, y_min:y_max:100j]
        positions = np.vstack([xx.ravel(), yy.ravel()])
        
        z = kde(positions).reshape(xx.shape)
        
        ax2.contourf(xx, yy, z, levels=20, cmap='Blues', alpha=0.6)
        ax2.contour(xx, yy, z, levels=10, colors='blue', alpha=0.3, linewidths=0.5)
    except Exception as e:
        print(f"   KDE failed: {e}, using scatter only")
        ax2.scatter(X_tsne[:, 0], X_tsne[:, 1], c='lightblue', s=5, alpha=0.2)
    
    # Fraud overlay
    ax2.scatter(
        fraud_coords[:, 0], 
        fraud_coords[:, 1],
        c='red',
        s=80,
        alpha=0.9,
        marker='*',
        edgecolors='darkred',
        linewidths=1,
        label=f'Fraud Addresses ({len(fraud_coords)})',
        zorder=10
    )
    
    ax2.set_title('Fraud Distribution in Embedding Space\n(Density + Fraud Overlay)', fontsize=14, fontweight='bold')
    ax2.set_xlabel('t-SNE 1')
    ax2.set_ylabel('t-SNE 2')
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save figure
    output_path = 'c:/amttp/reports/node2vec_visualization.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"   Saved: {output_path}")
    
    # Additional analysis plot
    fig2, axes2 = plt.subplots(1, 2, figsize=(14, 6))
    
    # Plot 3: Fraud cluster analysis
    ax3 = axes2[0]
    
    # Calculate distances from fraud centroid
    fraud_centroid = fraud_coords.mean(axis=0)
    distances_to_fraud = np.sqrt(((X_tsne - fraud_centroid) ** 2).sum(axis=1))
    
    # Color by distance to fraud centroid
    scatter = ax3.scatter(
        X_tsne[:, 0], 
        X_tsne[:, 1],
        c=distances_to_fraud,
        cmap='RdYlGn',
        s=15,
        alpha=0.6
    )
    
    # Mark centroid
    ax3.scatter(
        fraud_centroid[0], 
        fraud_centroid[1],
        c='black',
        s=200,
        marker='X',
        edgecolors='white',
        linewidths=2,
        label='Fraud Centroid',
        zorder=10
    )
    
    ax3.set_title('Distance to Fraud Centroid\n(Red = Close, Green = Far)', fontsize=14, fontweight='bold')
    ax3.set_xlabel('t-SNE 1')
    ax3.set_ylabel('t-SNE 2')
    ax3.legend(loc='upper right')
    plt.colorbar(scatter, ax=ax3, label='Distance')
    
    # Plot 4: Histogram of distances
    ax4 = axes2[1]
    
    fraud_distances = distances_to_fraud[mask_fraud]
    legit_distances = distances_to_fraud[mask_legit]
    
    ax4.hist(legit_distances, bins=50, alpha=0.6, label='Legitimate', color='blue', density=True)
    ax4.hist(fraud_distances, bins=20, alpha=0.8, label='Fraud', color='red', density=True)
    
    ax4.axvline(fraud_distances.mean(), color='red', linestyle='--', linewidth=2, label=f'Fraud Mean: {fraud_distances.mean():.1f}')
    ax4.axvline(legit_distances.mean(), color='blue', linestyle='--', linewidth=2, label=f'Legit Mean: {legit_distances.mean():.1f}')
    
    ax4.set_title('Distribution of Distances to Fraud Centroid', fontsize=14, fontweight='bold')
    ax4.set_xlabel('Distance to Fraud Centroid')
    ax4.set_ylabel('Density')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    output_path2 = 'c:/amttp/reports/node2vec_fraud_analysis.png'
    plt.savefig(output_path2, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"   Saved: {output_path2}")
    
    # Print statistics
    print("\n" + "=" * 70)
    print("FRAUD PROXIMITY ANALYSIS")
    print("=" * 70)
    
    print(f"\n   Fraud distance to centroid: {fraud_distances.mean():.2f} ± {fraud_distances.std():.2f}")
    print(f"   Legit distance to centroid: {legit_distances.mean():.2f} ± {legit_distances.std():.2f}")
    
    # Find non-fraud nodes close to fraud centroid
    threshold = np.percentile(fraud_distances, 75)  # 75th percentile of fraud distances
    close_legit = (distances_to_fraud < threshold) & (y_sample == 0)
    
    print(f"\n   Non-fraud nodes within fraud cluster radius: {close_legit.sum()}")
    print(f"   (These may warrant manual review)")
    
    # Save suspicious addresses
    suspicious_addrs = nodes_sample[close_legit]
    suspicious_df = pd.DataFrame({'address': suspicious_addrs})
    suspicious_df.to_csv('c:/amttp/processed/suspicious_near_fraud.csv', index=False)
    print(f"   Saved suspicious addresses to: suspicious_near_fraud.csv")
    
    print("\n" + "=" * 70)
    print("✅ VISUALIZATION COMPLETE")
    print("=" * 70)

if __name__ == '__main__':
    main()
