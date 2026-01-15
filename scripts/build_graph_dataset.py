"""
Build Graph Dataset for GNN Training (GAT, GraphSAGE, etc.)
============================================================
Uses:
- eth_merged_dataset.parquet → Graph structure (nodes + edges)
- sophisticated_xgb_combined.csv → Labels from hybrid model

Output:
- PyTorch Geometric Data object
- Node features, edge index, labels
"""
import pandas as pd
import numpy as np
import polars as pl
from pathlib import Path
import pickle
import time

print("=" * 70)
print("BUILDING GRAPH DATASET FOR GNN TRAINING")
print("=" * 70)

start_time = time.time()

# Paths
ETH_DATA = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
LABELS_DATA = r"c:\amttp\processed\sophisticated_xgb_combined.csv"
OUTPUT_DIR = r"c:\amttp\processed\graph_data"

Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

# ============================================================================
# STEP 1: Load labeled data from hybrid model
# ============================================================================
print("\n[1/5] Loading labels from hybrid model...")
labels_df = pd.read_csv(LABELS_DATA)
print(f"   Loaded {len(labels_df):,} labeled addresses")

# Create binary labels: CRITICAL/HIGH = 1 (fraud), others = 0
labels_df['label'] = labels_df['risk_level'].isin(['CRITICAL', 'HIGH']).astype(int)
fraud_addresses = set(labels_df[labels_df['label'] == 1]['address'].values)
all_labeled_addresses = set(labels_df['address'].values)

print(f"   Fraud addresses (CRITICAL/HIGH): {len(fraud_addresses):,}")
print(f"   Normal addresses (MEDIUM/LOW): {len(all_labeled_addresses) - len(fraud_addresses):,}")

# ============================================================================
# STEP 2: Load transactions and build graph
# ============================================================================
print("\n[2/5] Loading transactions and building graph...")
df = pl.read_parquet(ETH_DATA)
print(f"   Loaded {len(df):,} transactions")

# Get unique addresses
all_senders = df['from_address'].unique().to_list()
all_receivers = df['to_address'].unique().to_list()
all_addresses = list(set(all_senders + all_receivers))
print(f"   Unique addresses: {len(all_addresses):,}")

# Create address to index mapping
addr_to_idx = {addr: idx for idx, addr in enumerate(all_addresses)}
idx_to_addr = {idx: addr for addr, idx in addr_to_idx.items()}

# ============================================================================
# STEP 3: Build edge list (transaction graph)
# ============================================================================
print("\n[3/5] Building edge list...")

# Convert to pandas for edge processing
edges_df = df.select(['from_address', 'to_address', 'value_eth']).to_pandas()

# Create edge index (source -> target)
edge_source = edges_df['from_address'].map(addr_to_idx).values
edge_target = edges_df['to_address'].map(addr_to_idx).values

# Remove self-loops and invalid edges
valid_mask = (edge_source != edge_target) & (~np.isnan(edge_source)) & (~np.isnan(edge_target))
edge_source = edge_source[valid_mask].astype(np.int64)
edge_target = edge_target[valid_mask].astype(np.int64)

# Edge index in PyG format: [2, num_edges]
edge_index = np.stack([edge_source, edge_target], axis=0)
print(f"   Edges: {edge_index.shape[1]:,}")

# Edge weights (transaction values)
edge_weight = edges_df['value_eth'].values[valid_mask]
print(f"   Edge weights computed (transaction values)")

# ============================================================================
# STEP 4: Compute node features
# ============================================================================
print("\n[4/5] Computing node features...")

# Aggregate features per address
print("   Computing sender features...")
sender_stats = df.group_by('from_address').agg([
    pl.len().alias('sent_count'),
    pl.col('value_eth').sum().alias('total_sent'),
    pl.col('value_eth').mean().alias('avg_sent'),
    pl.col('value_eth').max().alias('max_sent'),
    pl.col('value_eth').min().alias('min_sent'),
    pl.col('value_eth').std().alias('std_sent'),
    pl.col('gas_used').sum().alias('total_gas_sent'),
    pl.col('gas_price_gwei').mean().alias('avg_gas_price'),
    pl.col('to_address').n_unique().alias('unique_receivers'),
    pl.col('block_timestamp').min().alias('first_sent'),
    pl.col('block_timestamp').max().alias('last_sent'),
]).to_pandas().rename(columns={'from_address': 'address'})

print("   Computing receiver features...")
receiver_stats = df.group_by('to_address').agg([
    pl.len().alias('received_count'),
    pl.col('value_eth').sum().alias('total_received'),
    pl.col('value_eth').mean().alias('avg_received'),
    pl.col('value_eth').max().alias('max_received'),
    pl.col('value_eth').min().alias('min_received'),
    pl.col('value_eth').std().alias('std_received'),
    pl.col('from_address').n_unique().alias('unique_senders'),
    pl.col('block_timestamp').min().alias('first_received'),
    pl.col('block_timestamp').max().alias('last_received'),
]).to_pandas().rename(columns={'to_address': 'address'})

# Merge features
print("   Merging features...")
node_features = pd.DataFrame({'address': all_addresses})
node_features = node_features.merge(sender_stats, on='address', how='left')
node_features = node_features.merge(receiver_stats, on='address', how='left')

# Compute derived features
node_features['total_transactions'] = node_features['sent_count'].fillna(0) + node_features['received_count'].fillna(0)
node_features['balance'] = node_features['total_received'].fillna(0) - node_features['total_sent'].fillna(0)
node_features['in_out_ratio'] = node_features['received_count'].fillna(0) / (node_features['sent_count'].fillna(0) + 1)
node_features['unique_counterparties'] = node_features['unique_receivers'].fillna(0) + node_features['unique_senders'].fillna(0)

# Time-based features
node_features['first_activity'] = node_features[['first_sent', 'first_received']].min(axis=1)
node_features['last_activity'] = node_features[['last_sent', 'last_received']].max(axis=1)
node_features['active_duration'] = (node_features['last_activity'] - node_features['first_activity']).dt.total_seconds() / 60  # minutes

# Fill NaN with 0
node_features = node_features.fillna(0)

# Select features for GNN
feature_columns = [
    'sent_count', 'received_count', 'total_transactions',
    'total_sent', 'total_received', 'balance',
    'avg_sent', 'avg_received',
    'max_sent', 'max_received',
    'min_sent', 'min_received',
    'std_sent', 'std_received',
    'total_gas_sent', 'avg_gas_price',
    'unique_receivers', 'unique_senders', 'unique_counterparties',
    'in_out_ratio', 'active_duration'
]

# Ensure address order matches index
node_features = node_features.set_index('address')
node_features = node_features.reindex([idx_to_addr[i] for i in range(len(all_addresses))])

# Extract feature matrix
X = node_features[feature_columns].values.astype(np.float32)
print(f"   Node features shape: {X.shape}")
print(f"   Features: {feature_columns}")

# Normalize features (important for GNNs)
from sklearn.preprocessing import StandardScaler
scaler = StandardScaler()
X_normalized = scaler.fit_transform(X)
print(f"   Features normalized (StandardScaler)")

# ============================================================================
# STEP 5: Assign labels
# ============================================================================
print("\n[5/5] Assigning labels...")

# Create label array
y = np.zeros(len(all_addresses), dtype=np.int64)
labeled_mask = np.zeros(len(all_addresses), dtype=bool)

for addr, idx in addr_to_idx.items():
    if addr in fraud_addresses:
        y[idx] = 1
        labeled_mask[idx] = True
    elif addr in all_labeled_addresses:
        y[idx] = 0
        labeled_mask[idx] = True

print(f"   Labeled nodes: {labeled_mask.sum():,} ({labeled_mask.sum()/len(all_addresses)*100:.2f}%)")
print(f"   Fraud (1): {(y == 1).sum():,}")
print(f"   Normal (0): {((y == 0) & labeled_mask).sum():,}")
print(f"   Unlabeled: {(~labeled_mask).sum():,}")

# ============================================================================
# SAVE DATA
# ============================================================================
print("\n" + "=" * 70)
print("SAVING GRAPH DATA")
print("=" * 70)

# Save as numpy arrays (compatible with any framework)
np.save(f"{OUTPUT_DIR}/node_features.npy", X_normalized)
np.save(f"{OUTPUT_DIR}/edge_index.npy", edge_index)
np.save(f"{OUTPUT_DIR}/edge_weight.npy", edge_weight)
np.save(f"{OUTPUT_DIR}/labels.npy", y)
np.save(f"{OUTPUT_DIR}/labeled_mask.npy", labeled_mask)

print(f"   Saved: node_features.npy ({X_normalized.shape})")
print(f"   Saved: edge_index.npy ({edge_index.shape})")
print(f"   Saved: edge_weight.npy ({edge_weight.shape})")
print(f"   Saved: labels.npy ({y.shape})")
print(f"   Saved: labeled_mask.npy ({labeled_mask.shape})")

# Save address mapping
addr_mapping = {'addr_to_idx': addr_to_idx, 'idx_to_addr': idx_to_addr}
with open(f"{OUTPUT_DIR}/address_mapping.pkl", 'wb') as f:
    pickle.dump(addr_mapping, f)
print(f"   Saved: address_mapping.pkl")

# Save feature names and scaler
with open(f"{OUTPUT_DIR}/feature_info.pkl", 'wb') as f:
    pickle.dump({'feature_columns': feature_columns, 'scaler': scaler}, f)
print(f"   Saved: feature_info.pkl")

# Try to create PyTorch Geometric Data object
try:
    import torch
    from torch_geometric.data import Data
    
    data = Data(
        x=torch.tensor(X_normalized, dtype=torch.float),
        edge_index=torch.tensor(edge_index, dtype=torch.long),
        edge_attr=torch.tensor(edge_weight, dtype=torch.float).unsqueeze(1),
        y=torch.tensor(y, dtype=torch.long),
    )
    
    # Add masks for semi-supervised learning
    data.train_mask = torch.tensor(labeled_mask, dtype=torch.bool)
    data.labeled_mask = torch.tensor(labeled_mask, dtype=torch.bool)
    
    torch.save(data, f"{OUTPUT_DIR}/pyg_graph_data.pt")
    print(f"   Saved: pyg_graph_data.pt (PyTorch Geometric)")
    
    print(f"\n   PyG Data object:")
    print(f"      x: {data.x.shape}")
    print(f"      edge_index: {data.edge_index.shape}")
    print(f"      edge_attr: {data.edge_attr.shape}")
    print(f"      y: {data.y.shape}")
    print(f"      train_mask: {data.train_mask.sum().item()} nodes")
    
except ImportError:
    print("   PyTorch Geometric not installed, skipping .pt export")
    print("   Install with: pip install torch-geometric")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print("GRAPH DATASET SUMMARY")
print("=" * 70)

print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                        GRAPH DATA FOR GNN TRAINING                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ NODES (Addresses):                                                           ║
║   Total:            {len(all_addresses):>10,}                                                ║
║   Features:         {len(feature_columns):>10} per node                                       ║
║   Labeled:          {labeled_mask.sum():>10,} ({labeled_mask.sum()/len(all_addresses)*100:.1f}%)                                   ║
║   Fraud (1):        {(y == 1).sum():>10,}                                                ║
║   Normal (0):       {((y == 0) & labeled_mask).sum():>10,}                                                ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ EDGES (Transactions):                                                        ║
║   Total:            {edge_index.shape[1]:>10,}                                                ║
║   With weights:     Yes (transaction values)                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ OUTPUT FILES:                                                                ║
║   {OUTPUT_DIR}/                                           ║
║   ├── node_features.npy                                                      ║
║   ├── edge_index.npy                                                         ║
║   ├── edge_weight.npy                                                        ║
║   ├── labels.npy                                                             ║
║   ├── labeled_mask.npy                                                       ║
║   ├── address_mapping.pkl                                                    ║
║   ├── feature_info.pkl                                                       ║
║   └── pyg_graph_data.pt (if PyG installed)                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

USAGE EXAMPLE (PyTorch Geometric):
```python
import torch
from torch_geometric.data import Data

# Load the graph
data = torch.load('c:/amttp/processed/graph_data/pyg_graph_data.pt')

# Train GAT/GraphSAGE
from torch_geometric.nn import GATConv, SAGEConv
...
```
""")

elapsed = time.time() - start_time
print(f"Completed in {elapsed:.2f} seconds")
print("=" * 70)
