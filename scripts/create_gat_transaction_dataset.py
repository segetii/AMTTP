"""
Create Complete Transaction-Level Dataset for GAT/GNN Training
================================================================
1. Load 1.67M transactions from eth_merged_dataset.parquet
2. Join sender address features (35 columns)
3. Join receiver address features (35 columns)
4. Add fraud labels
5. Create graph structure (edge_index) for GAT training
6. Export complete dataset

Output:
- Transaction-level dataset with sender/receiver features
- Graph data for PyTorch Geometric (GAT, GraphSAGE, etc.)
"""
import pandas as pd
import numpy as np
import polars as pl
from pathlib import Path
import pickle
import time

print("=" * 70)
print("CREATE TRANSACTION-LEVEL DATASET FOR GAT/GNN TRAINING")
print("=" * 70)

start_time = time.time()

# Paths
ETH_DATA = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
ADDR_FEATURES = r"c:\amttp\processed\eth_addresses_labeled.parquet"
OUTPUT_DIR = r"c:\amttp\processed"

Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

# ============================================================================
# STEP 1: Load transactions
# ============================================================================
print("\n[1/6] Loading transactions...")
tx_df = pl.read_parquet(ETH_DATA)
print(f"   Loaded {len(tx_df):,} transactions")

# Convert to pandas
tx_pd = tx_df.to_pandas()

# ============================================================================
# STEP 2: Load address features
# ============================================================================
print("\n[2/6] Loading address features with hybrid model scores...")
addr_df = pd.read_parquet(ADDR_FEATURES)
print(f"   Loaded {len(addr_df):,} addresses with {len(addr_df.columns)} features")

# Features to join (all hybrid model features + computed features)
join_features = [
    'address',
    # Computed features
    'sent_count', 'received_count', 'total_transactions',
    'total_sent', 'total_received', 'balance',
    'avg_sent', 'avg_received',
    'max_sent', 'max_received',
    'unique_receivers', 'unique_senders', 'unique_counterparties',
    'in_out_ratio', 'active_duration_mins',
    # Hybrid model features
    'sophisticated_score', 'pattern_count',
    'xgb_raw_score', 'xgb_normalized',
    'pattern_boost', 'soph_normalized', 'hybrid_score',
    'risk_level', 'fraud', 'risk_class'
]

# Keep only needed columns
addr_features = addr_df[[c for c in join_features if c in addr_df.columns]].copy()
print(f"   Using {len(addr_features.columns)} features per address")

# ============================================================================
# STEP 3: Join sender features to transactions
# ============================================================================
print("\n[3/6] Joining sender (from_address) features...")

# Rename columns for sender
sender_cols = {col: f'sender_{col}' for col in addr_features.columns if col != 'address'}
sender_features = addr_features.rename(columns=sender_cols)
sender_features = sender_features.rename(columns={'address': 'from_address'})

# Join
tx_pd = tx_pd.merge(sender_features, on='from_address', how='left')
print(f"   Joined sender features: {len(sender_cols)} columns")

# ============================================================================
# STEP 4: Join receiver features to transactions
# ============================================================================
print("\n[4/6] Joining receiver (to_address) features...")

# Rename columns for receiver
receiver_cols = {col: f'receiver_{col}' for col in addr_features.columns if col != 'address'}
receiver_features = addr_features.rename(columns=receiver_cols)
receiver_features = receiver_features.rename(columns={'address': 'to_address'})

# Join
tx_pd = tx_pd.merge(receiver_features, on='to_address', how='left')
print(f"   Joined receiver features: {len(receiver_cols)} columns")

# Fill NaN with 0 for numeric columns
numeric_cols = tx_pd.select_dtypes(include=[np.number]).columns
tx_pd[numeric_cols] = tx_pd[numeric_cols].fillna(0)

# Fill NaN for string columns
string_cols = tx_pd.select_dtypes(include=['object']).columns
tx_pd[string_cols] = tx_pd[string_cols].fillna('')

# ============================================================================
# STEP 5: Create fraud labels for transactions
# ============================================================================
print("\n[5/6] Creating transaction-level fraud labels...")

# Transaction is fraudulent if sender OR receiver is fraud
tx_pd['sender_is_fraud'] = tx_pd['sender_fraud'].fillna(0).astype(int)
tx_pd['receiver_is_fraud'] = tx_pd['receiver_fraud'].fillna(0).astype(int)
tx_pd['fraud'] = ((tx_pd['sender_is_fraud'] == 1) | (tx_pd['receiver_is_fraud'] == 1)).astype(int)

# Multi-class: max risk class of sender/receiver
tx_pd['risk_class'] = tx_pd[['sender_risk_class', 'receiver_risk_class']].max(axis=1).fillna(0).astype(int)

# Hybrid score: max of sender/receiver
tx_pd['max_hybrid_score'] = tx_pd[['sender_hybrid_score', 'receiver_hybrid_score']].max(axis=1).fillna(0)

print(f"   Fraud transactions: {tx_pd['fraud'].sum():,} ({tx_pd['fraud'].mean()*100:.2f}%)")
print(f"   Normal transactions: {(tx_pd['fraud'] == 0).sum():,}")

# ============================================================================
# STEP 6: Create graph structure for GAT
# ============================================================================
print("\n[6/6] Creating graph structure for GAT training...")

# Get unique addresses and create mapping
all_addresses = list(set(tx_pd['from_address'].unique()) | set(tx_pd['to_address'].unique()))
addr_to_idx = {addr: idx for idx, addr in enumerate(all_addresses)}
idx_to_addr = {idx: addr for addr, idx in addr_to_idx.items()}

print(f"   Unique nodes (addresses): {len(all_addresses):,}")

# Create edge index
tx_pd['from_idx'] = tx_pd['from_address'].map(addr_to_idx)
tx_pd['to_idx'] = tx_pd['to_address'].map(addr_to_idx)

edge_index = np.array([
    tx_pd['from_idx'].values,
    tx_pd['to_idx'].values
], dtype=np.int64)

print(f"   Edges (transactions): {edge_index.shape[1]:,}")

# Edge features (transaction features)
edge_features = tx_pd[['value_eth', 'gas_price_gwei', 'gas_used', 'gas_limit']].values.astype(np.float32)
print(f"   Edge features shape: {edge_features.shape}")

# Node features (from address features)
node_feature_cols = [
    'sent_count', 'received_count', 'total_transactions',
    'total_sent', 'total_received', 'balance',
    'avg_sent', 'avg_received',
    'max_sent', 'max_received',
    'unique_receivers', 'unique_senders', 'unique_counterparties',
    'in_out_ratio', 'active_duration_mins',
    'sophisticated_score', 'pattern_count',
    'xgb_raw_score', 'xgb_normalized',
    'pattern_boost', 'soph_normalized', 'hybrid_score'
]

# Create node feature matrix
node_features = np.zeros((len(all_addresses), len(node_feature_cols)), dtype=np.float32)
addr_df_indexed = addr_df.set_index('address')

for addr, idx in addr_to_idx.items():
    if addr in addr_df_indexed.index:
        row = addr_df_indexed.loc[addr]
        for i, col in enumerate(node_feature_cols):
            if col in row.index:
                val = row[col]
                if pd.notna(val) and not isinstance(val, str):
                    node_features[idx, i] = float(val)

print(f"   Node features shape: {node_features.shape}")

# Node labels
node_labels = np.zeros(len(all_addresses), dtype=np.int64)
for addr, idx in addr_to_idx.items():
    if addr in addr_df_indexed.index:
        fraud_val = addr_df_indexed.loc[addr, 'fraud']
        if pd.notna(fraud_val):
            node_labels[idx] = int(fraud_val)

print(f"   Node labels: {(node_labels == 1).sum():,} fraud, {(node_labels == 0).sum():,} normal")

# Normalize node features
from sklearn.preprocessing import StandardScaler
scaler = StandardScaler()
node_features_normalized = scaler.fit_transform(node_features)

# ============================================================================
# SAVE DATASETS
# ============================================================================
print("\n" + "=" * 70)
print("SAVING DATASETS")
print("=" * 70)

# 1. Save transaction-level dataset
tx_path = f"{OUTPUT_DIR}/eth_transactions_full_labeled.parquet"
tx_pd.to_parquet(tx_path, index=False)
print(f"\n1. Transaction dataset: {tx_path}")
print(f"   Shape: {tx_pd.shape}")

# 2. Save graph data as numpy arrays
np.save(f"{OUTPUT_DIR}/graph_node_features.npy", node_features_normalized)
np.save(f"{OUTPUT_DIR}/graph_edge_index.npy", edge_index)
np.save(f"{OUTPUT_DIR}/graph_edge_features.npy", edge_features)
np.save(f"{OUTPUT_DIR}/graph_node_labels.npy", node_labels)
print(f"\n2. Graph numpy files saved:")
print(f"   - graph_node_features.npy: {node_features_normalized.shape}")
print(f"   - graph_edge_index.npy: {edge_index.shape}")
print(f"   - graph_edge_features.npy: {edge_features.shape}")
print(f"   - graph_node_labels.npy: {node_labels.shape}")

# 3. Save mappings
with open(f"{OUTPUT_DIR}/graph_mappings.pkl", 'wb') as f:
    pickle.dump({
        'addr_to_idx': addr_to_idx,
        'idx_to_addr': idx_to_addr,
        'node_feature_cols': node_feature_cols,
        'scaler': scaler
    }, f)
print(f"\n3. Mappings saved: graph_mappings.pkl")

# 4. Try to create PyTorch Geometric Data object
try:
    import torch
    from torch_geometric.data import Data
    
    data = Data(
        x=torch.tensor(node_features_normalized, dtype=torch.float),
        edge_index=torch.tensor(edge_index, dtype=torch.long),
        edge_attr=torch.tensor(edge_features, dtype=torch.float),
        y=torch.tensor(node_labels, dtype=torch.long),
    )
    
    torch.save(data, f"{OUTPUT_DIR}/pyg_gat_data.pt")
    print(f"\n4. PyTorch Geometric Data: pyg_gat_data.pt")
    print(f"   x: {data.x.shape}")
    print(f"   edge_index: {data.edge_index.shape}")
    print(f"   edge_attr: {data.edge_attr.shape}")
    print(f"   y: {data.y.shape}")
    print(f"   Fraud nodes: {(data.y == 1).sum().item()}")
    
except ImportError:
    print("\n4. PyTorch Geometric not installed. Install with:")
    print("   pip install torch torch-geometric")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print("COMPLETE DATASET SUMMARY")
print("=" * 70)

print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    TRANSACTION-LEVEL DATASET FOR GAT                         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ TRANSACTIONS:                                                                ║
║   Total:            {len(tx_pd):>10,}                                                ║
║   Features:         {len(tx_pd.columns):>10} columns                                        ║
║   Fraud (1):        {tx_pd['fraud'].sum():>10,} ({tx_pd['fraud'].mean()*100:.2f}%)                             ║
║   Normal (0):       {(tx_pd['fraud'] == 0).sum():>10,}                                                ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ GRAPH STRUCTURE:                                                             ║
║   Nodes:            {len(all_addresses):>10,}                                                ║
║   Edges:            {edge_index.shape[1]:>10,}                                                ║
║   Node features:    {node_features.shape[1]:>10} per node                                       ║
║   Edge features:    {edge_features.shape[1]:>10} per edge                                       ║
║   Fraud nodes:      {(node_labels == 1).sum():>10,}                                                ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ HYBRID MODEL FEATURES INCLUDED (sender & receiver):                          ║
║   - sophisticated_score, pattern_count                                       ║
║   - xgb_raw_score, xgb_normalized                                           ║
║   - pattern_boost, soph_normalized, hybrid_score                            ║
║   - risk_level, fraud, risk_class                                           ║
╚══════════════════════════════════════════════════════════════════════════════╝

FILES CREATED:
1. {tx_path}
2. {OUTPUT_DIR}/graph_node_features.npy
3. {OUTPUT_DIR}/graph_edge_index.npy
4. {OUTPUT_DIR}/graph_edge_features.npy
5. {OUTPUT_DIR}/graph_node_labels.npy
6. {OUTPUT_DIR}/graph_mappings.pkl
7. {OUTPUT_DIR}/pyg_gat_data.pt (if PyG installed)

USAGE FOR GAT TRAINING:
```python
import torch
from torch_geometric.data import Data
from torch_geometric.nn import GATConv

# Load graph
data = torch.load('c:/amttp/processed/pyg_gat_data.pt')

# GAT Model
class GAT(torch.nn.Module):
    def __init__(self, in_channels, hidden_channels, out_channels, heads=8):
        super().__init__()
        self.conv1 = GATConv(in_channels, hidden_channels, heads=heads)
        self.conv2 = GATConv(hidden_channels * heads, out_channels, heads=1)
    
    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu()
        x = self.conv2(x, edge_index)
        return x

model = GAT(in_channels={node_features.shape[1]}, hidden_channels=64, out_channels=2)
```
""")

elapsed = time.time() - start_time
print(f"\nCompleted in {elapsed:.2f} seconds")
print("=" * 70)
