"""
Prepare complex real-world datasets for multi-domain anomaly detection benchmark.

Datasets:
  1. Credit Card Fraud (Kaggle)     — 284k txn, 492 fraud (~0.17%), 28 PCA features
  2. IEEE-CIS Fraud Detection       — 590k txn, ~3.5% fraud, 400+ mixed features
  3. ODDS benchmarks (4 datasets)   — classical anomaly detection benchmarks
  4. KDDCup99 (already prepped)     — network intrusion, 108k, 10% attack

Output: single .npz per dataset in data/external_validation/prepped/
"""
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.decomposition import PCA
import scipy.io as sio
import warnings
warnings.filterwarnings('ignore')

ROOT = Path(r'c:\amttp')
EXT  = ROOT / 'data' / 'external_validation'
OUT  = EXT / 'prepped'
OUT.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════
#  1. CREDIT CARD FRAUD (European cardholders, Sept 2013, 2 days)
#     284,807 transactions, 492 fraud (0.173%)
#     V1-V28 are PCA components, plus Time and Amount
# ═══════════════════════════════════════════════════════════════════════════
print("═" * 70)
print("  1. Credit Card Fraud Detection")
print("═" * 70)

cc_path = EXT / 'creditcard' / 'creditcard.csv'
if cc_path.exists():
    df_cc = pd.read_csv(cc_path)
    print(f"  Raw: {len(df_cc):,} rows, {df_cc.shape[1]} cols")
    print(f"  Fraud: {df_cc['Class'].sum():,} ({100*df_cc['Class'].mean():.3f}%)")
    
    # Features: V1-V28 (already PCA), Time, Amount
    feat_cols = [c for c in df_cc.columns if c not in ('Class',)]
    X_cc = df_cc[feat_cols].values.astype(np.float64)
    y_cc = df_cc['Class'].values.astype(np.int32)
    
    # Scale Time and Amount (V1-V28 already scaled)
    scaler = StandardScaler()
    X_cc[:, 0] = scaler.fit_transform(X_cc[:, 0:1]).ravel()  # Time
    X_cc[:, -1] = scaler.fit_transform(X_cc[:, -1:]).ravel()  # Amount
    
    # Also create PCA-reduced versions (10D, 5D) for comparability
    pca10 = PCA(n_components=10, random_state=42)
    X_cc10 = pca10.fit_transform(X_cc)
    pca5 = PCA(n_components=5, random_state=42)
    X_cc5 = pca5.fit_transform(X_cc)
    
    print(f"  Full: {X_cc.shape}, PCA10: {X_cc10.shape}, PCA5: {X_cc5.shape}")
    print(f"  PCA10 variance: {pca10.explained_variance_ratio_.sum():.3f}")
    
    np.savez_compressed(OUT / 'creditcard_fraud.npz',
                        X_full=X_cc, X10=X_cc10, X5=X_cc5,
                        y=y_cc, feature_names=np.array(feat_cols))
    print(f"  → Saved {OUT / 'creditcard_fraud.npz'}")
else:
    print(f"  [SKIP] {cc_path} not found")

# ═══════════════════════════════════════════════════════════════════════════
#  2. IEEE-CIS Fraud Detection (Vesta Corporation, real e-commerce)
#     590,540 transactions, ~20,663 fraud (3.5%)
#     TransactionDT, TransactionAmt, card1-6, addr1-2, email, C1-14, D1-15,
#     M1-9, V1-339 (anonymous engineered features)
#     This is the most complex/realistic financial fraud dataset available.
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  2. IEEE-CIS Fraud Detection (e-commerce)")
print("═" * 70)

ieee_txn = EXT / 'ieee_cis' / 'train_transaction.csv'
ieee_id  = EXT / 'ieee_cis' / 'train_identity.csv'
if ieee_txn.exists():
    df_txn = pd.read_csv(ieee_txn)
    print(f"  Transactions: {len(df_txn):,} rows, {df_txn.shape[1]} cols")
    print(f"  Fraud: {df_txn['isFraud'].sum():,} ({100*df_txn['isFraud'].mean():.2f}%)")
    
    # Merge identity if available
    if ieee_id.exists():
        df_id = pd.read_csv(ieee_id)
        df = df_txn.merge(df_id, on='TransactionID', how='left')
        print(f"  After identity merge: {df.shape[1]} cols")
    else:
        df = df_txn
    
    y_ieee = df['isFraud'].values.astype(np.int32)
    
    # Select numeric features only (drop ID, target)
    drop = ['TransactionID', 'isFraud']
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    num_cols = [c for c in num_cols if c not in drop]
    
    X_ieee_raw = df[num_cols].values.astype(np.float64)
    
    # Handle NaN: fill with column median
    col_medians = np.nanmedian(X_ieee_raw, axis=0)
    nan_mask = np.isnan(X_ieee_raw)
    for j in range(X_ieee_raw.shape[1]):
        X_ieee_raw[nan_mask[:, j], j] = col_medians[j]
    
    # Remove columns that are still all-NaN or constant
    valid_cols = []
    for j in range(X_ieee_raw.shape[1]):
        if np.std(X_ieee_raw[:, j]) > 1e-10 and not np.any(np.isnan(X_ieee_raw[:, j])):
            valid_cols.append(j)
    X_ieee_clean = X_ieee_raw[:, valid_cols]
    feat_names_ieee = [num_cols[j] for j in valid_cols]
    print(f"  Numeric features after cleanup: {X_ieee_clean.shape[1]}")
    
    # Standardize
    scaler = StandardScaler()
    X_ieee_std = scaler.fit_transform(X_ieee_clean)
    
    # Clip extreme outliers (cap at ±10σ to prevent PCA distortion)
    X_ieee_std = np.clip(X_ieee_std, -10, 10)
    
    # PCA reductions
    pca10 = PCA(n_components=10, random_state=42)
    X_ieee10 = pca10.fit_transform(X_ieee_std)
    pca20 = PCA(n_components=20, random_state=42)
    X_ieee20 = pca20.fit_transform(X_ieee_std)
    pca5 = PCA(n_components=5, random_state=42)
    X_ieee5 = pca5.fit_transform(X_ieee_std)
    
    print(f"  PCA10 var: {pca10.explained_variance_ratio_.sum():.3f}, "
          f"PCA20 var: {pca20.explained_variance_ratio_.sum():.3f}")
    
    # Subsample for tractability (keep all fraud, downsample normal)
    fraud_idx = np.where(y_ieee == 1)[0]
    normal_idx = np.where(y_ieee == 0)[0]
    rng = np.random.RandomState(42)
    # Keep ~50k normal + all fraud ≈ 70k total
    n_normal_keep = min(50000, len(normal_idx))
    normal_sub = rng.choice(normal_idx, n_normal_keep, replace=False)
    keep_idx = np.sort(np.concatenate([fraud_idx, normal_sub]))
    
    X_ieee10_sub = X_ieee10[keep_idx]
    X_ieee20_sub = X_ieee20[keep_idx]
    X_ieee5_sub  = X_ieee5[keep_idx]
    y_ieee_sub   = y_ieee[keep_idx]
    
    print(f"  Subsampled: {len(keep_idx):,} (fraud={y_ieee_sub.sum():,}, "
          f"rate={100*y_ieee_sub.mean():.2f}%)")
    
    np.savez_compressed(OUT / 'ieee_cis_fraud.npz',
                        X10=X_ieee10_sub, X20=X_ieee20_sub, X5=X_ieee5_sub,
                        y=y_ieee_sub,
                        X10_full=X_ieee10, X20_full=X_ieee20,
                        y_full=y_ieee)
    print(f"  → Saved {OUT / 'ieee_cis_fraud.npz'}")
else:
    print(f"  [SKIP] {ieee_txn} not found")

# ═══════════════════════════════════════════════════════════════════════════
#  3. ODDS Benchmarks (classical anomaly detection)
#     - Shuttle:      49,097 samples, 7D, 3,511 anomalies (7.2%)
#     - Mammography:  11,183 samples, 6D,   260 anomalies (2.3%)
#     - Pendigits:    6,870 samples, 16D,   156 anomalies (2.3%)
#     - SMTP:         95,156 samples, 3D,    30 anomalies (0.03%)
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  3. ODDS Anomaly Detection Benchmarks")
print("═" * 70)

odds_dir = EXT / 'odds'
odds_datasets = {}

for mat_file in sorted(odds_dir.glob('*.mat')):
    name = mat_file.stem
    data = sio.loadmat(str(mat_file))
    X = data['X'].astype(np.float64)
    y = data['y'].ravel().astype(np.int32)
    
    n_anom = int(y.sum())
    print(f"  {name:<15} {X.shape[0]:>7,} samples  {X.shape[1]:>3}D  "
          f"{n_anom:>5,} anomalies ({100*y.mean():.2f}%)")
    
    # Standardize
    scaler = StandardScaler()
    X_std = scaler.fit_transform(X)
    
    # PCA to 5D if d > 5
    if X.shape[1] > 5:
        pca5 = PCA(n_components=5, random_state=42)
        X5 = pca5.fit_transform(X_std)
    else:
        X5 = X_std[:, :min(5, X.shape[1])]
    
    odds_datasets[name] = {'X': X_std, 'X5': X5, 'y': y, 
                           'n': len(y), 'd': X.shape[1], 'n_anom': n_anom}

# Save all ODDS in one file
if odds_datasets:
    save_dict = {}
    for name, d in odds_datasets.items():
        save_dict[f'{name}_X'] = d['X']
        save_dict[f'{name}_X5'] = d['X5']
        save_dict[f'{name}_y'] = d['y']
    np.savez_compressed(OUT / 'odds_benchmarks.npz', **save_dict)
    print(f"  → Saved {OUT / 'odds_benchmarks.npz'}")

# ═══════════════════════════════════════════════════════════════════════════
#  4. Synthetic Complex: Multi-cluster with concept drift
#     Simulates real operational data characteristics:
#     - Multiple normal clusters (different business units/regions)
#     - Concept drift (distribution shift over time)
#     - Multi-modal anomalies (point, contextual, collective)
#     - High-dimensional with irrelevant features
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  4. Synthetic Operational (multi-cluster + drift + multi-modal anomalies)")
print("═" * 70)

rng = np.random.RandomState(42)
N = 50000
d = 20  # intrinsic dim
d_noise = 30  # noise dims (total = 50)

# Normal data: 5 clusters with drift
n_clusters = 5
cluster_sizes = rng.multinomial(N, [1/n_clusters]*n_clusters)
X_parts = []
for c_i, n_c in enumerate(cluster_sizes):
    center = rng.randn(d) * 3
    cov = np.eye(d) * (0.5 + rng.rand())
    # Add correlation structure
    A = rng.randn(d, d) * 0.3
    cov = cov + A @ A.T * 0.1
    X_c = rng.multivariate_normal(center, cov, size=n_c)
    # Concept drift: shift center linearly over time
    drift = np.linspace(0, 1, n_c)[:, None] * rng.randn(1, d) * 0.5
    X_c += drift
    X_parts.append(X_c)

X_normal = np.vstack(X_parts)

# Add noise dimensions
X_normal = np.hstack([X_normal, rng.randn(N, d_noise) * 0.1])

# Anomalies: 3 types
n_anom = 2500  # 5% anomaly rate

# Type 1: Point anomalies — extreme outliers (uniform in expanded range)
n_point = n_anom // 3
X_point = rng.uniform(-8, 8, size=(n_point, d + d_noise))

# Type 2: Contextual anomalies — in normal region but wrong cluster assignment
# (feature values individually normal but combination is unusual)
n_ctx = n_anom // 3
idx_a = rng.choice(N, n_ctx)
idx_b = rng.choice(N, n_ctx)
X_ctx = np.zeros((n_ctx, d + d_noise))
split = (d + d_noise) // 2
X_ctx[:, :split] = X_normal[idx_a, :split]   # first half from one point
X_ctx[:, split:] = X_normal[idx_b, split:]    # second half from another

# Type 3: Collective anomalies — tight cluster in unusual location
n_coll = n_anom - n_point - n_ctx
coll_center = rng.randn(d + d_noise) * 6
X_coll = rng.randn(n_coll, d + d_noise) * 0.2 + coll_center

X_synth = np.vstack([X_normal, X_point, X_ctx, X_coll])
y_synth = np.concatenate([np.zeros(N), np.ones(n_anom)])
anom_types = np.array(['normal'] * N + ['point'] * n_point + 
                       ['contextual'] * n_ctx + ['collective'] * (n_anom - n_point - n_ctx))

# Shuffle
perm = rng.permutation(len(y_synth))
X_synth = X_synth[perm]
y_synth = y_synth[perm].astype(np.int32)
anom_types = anom_types[perm]

# Standardize
scaler = StandardScaler()
X_synth_std = scaler.fit_transform(X_synth)

# PCA reductions
pca10 = PCA(n_components=10, random_state=42)
X_synth10 = pca10.fit_transform(X_synth_std)
pca5 = PCA(n_components=5, random_state=42)
X_synth5 = pca5.fit_transform(X_synth_std)

print(f"  Total: {len(y_synth):,}  Anomalies: {int(y_synth.sum()):,} ({100*y_synth.mean():.1f}%)")
from collections import Counter
type_counts = Counter(anom_types[y_synth == 1])
for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
    print(f"    {t:<15} {c:>5}")
print(f"  Dims: full={X_synth_std.shape[1]}, PCA10 var={pca10.explained_variance_ratio_.sum():.3f}")

np.savez_compressed(OUT / 'synthetic_operational.npz',
                    X_full=X_synth_std, X10=X_synth10, X5=X_synth5,
                    y=y_synth, anomaly_types=anom_types)
print(f"  → Saved {OUT / 'synthetic_operational.npz'}")

# ═══════════════════════════════════════════════════════════════════════════
#  SUMMARY
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  DATASET SUMMARY")
print("═" * 70)
print(f"  {'Dataset':<30} {'Samples':>10} {'Anomalies':>10} {'Rate':>7} {'Dims':>6}")
print(f"  {'─'*30} {'─'*10} {'─'*10} {'─'*7} {'─'*6}")

datasets = [
    ("ERCOT Grid Failure", 15665, 5915, 37.8, 5),
    ("G-SIB Banking Panel", 1900, 325, 17.1, 5),
    ("KDDCup99 Intrusion", 108085, 10808, 10.0, 10),
]

if cc_path.exists():
    datasets.append(("Credit Card Fraud", len(y_cc), int(y_cc.sum()), 100*y_cc.mean(), 30))
if ieee_txn.exists():
    datasets.append(("IEEE-CIS e-Commerce", len(y_ieee_sub), int(y_ieee_sub.sum()), 100*y_ieee_sub.mean(), 10))
for name, d in odds_datasets.items():
    datasets.append((f"ODDS/{name}", d['n'], d['n_anom'], 100*d['n_anom']/d['n'], d['d']))
datasets.append(("Synthetic Operational", len(y_synth), int(y_synth.sum()), 100*y_synth.mean(), 50))

for dname, n, na, rate, dims in datasets:
    print(f"  {dname:<30} {n:>10,} {na:>10,} {rate:>6.2f}% {dims:>5}D")

print(f"\n  Total datasets: {len(datasets)}")
print("  Ready for benchmark pipeline.")
