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
ADDR_FEATURES = r"c:\amttp\processed\eth_addresses_labeled_v2.parquet"  # v2: 80 cols, 613 fraud
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

# Dynamically select all numeric + key categorical columns from v2
# Always include 'address' as the join key
_numeric = addr_df.select_dtypes(include=[np.number]).columns.tolist()
_keep = ['address'] + _numeric
# Also keep string risk columns if present
for _extra in ['risk_level', 'risk_class']:
    if _extra in addr_df.columns and _extra not in _keep:
        _keep.append(_extra)
addr_features = addr_df[[c for c in _keep if c in addr_df.columns]].copy()
print(f"   Using {len(addr_features.columns)} features per address (v2 dataset)")

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

# Defragment after the two large merges to avoid PerformanceWarning
tx_pd = tx_pd.copy()

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

# Node features (dynamically from all available numeric address features)
node_feature_cols = [c for c in addr_features.select_dtypes(include=[np.number]).columns
                     if c != 'address']
print(f"   Node feature columns: {len(node_feature_cols)}")

# Create node feature matrix — VECTORIZED (fast)
# Build a DataFrame indexed by all_addresses (preserves order → addr_to_idx)
addr_order = pd.Series(range(len(all_addresses)), index=all_addresses, name='idx')
addr_df_numeric = addr_df.set_index('address')[node_feature_cols].reindex(addr_order.index)
addr_df_numeric = addr_df_numeric.fillna(0).astype(np.float32)
node_features = addr_df_numeric.values
print(f"   Node features shape: {node_features.shape}")

# Node labels — VECTORIZED
fraud_series = addr_df.set_index('address')['fraud'].reindex(addr_order.index).fillna(0).astype(np.int64)
node_labels = fraud_series.values
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
