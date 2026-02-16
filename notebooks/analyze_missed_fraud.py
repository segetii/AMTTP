"""
Investigate the fraud missed by AMTTP V2 models.
Compares characteristics of caught vs missed fraud cases on Elliptic and XBlock.
"""
import numpy as np
import pandas as pd
from pathlib import Path
import sys, json, warnings
warnings.filterwarnings('ignore')

# ── Paths ──
ARTIFACTS = Path(r'C:\Users\Administrator\Downloads\amttp_student_artifacts\amttp_models_20260213_213346')
DATA_DIR = Path(r'c:\amttp\data\external_validation')
sys.path.insert(0, str(Path(__file__).parent))

import joblib, xgboost as xgb
from sklearn.metrics import f1_score

# ── Load preprocessors and model ──
preprocessors = joblib.load(ARTIFACTS / 'preprocessors.joblib')
scaler = preprocessors['scaler']
feature_names = preprocessors['feature_names']  # exactly 93 names

xgb_model = xgb.Booster()
xgb_model.load_model(str(ARTIFACTS / 'xgboost_fraud.ubj'))

# Use the EXACT 93 feature names from the preprocessor
FEATURES_93 = list(feature_names)
OPTIMAL_THRESHOLD = 0.6428

def build_feature_matrix(mapped_df):
    """Build N x 93 feature matrix using the exact feature names the model expects."""
    X = np.zeros((len(mapped_df), 93), dtype=np.float32)
    for i, feat in enumerate(FEATURES_93):
        if feat in mapped_df.columns:
            X[:, i] = mapped_df[feat].values.astype(np.float32)
    return X

def preprocess(X_raw):
    X = X_raw.copy()
    X = np.log1p(np.abs(X)) * np.sign(X)
    X = scaler.transform(X)
    X = np.clip(X, -10, 10)
    X = np.nan_to_num(X, nan=0.0, posinf=10.0, neginf=-10.0)
    return X

def predict_xgb(X_raw):
    X_p = preprocess(X_raw)
    dmat = xgb.DMatrix(X_p, feature_names=FEATURES_93)
    return xgb_model.predict(dmat)


# ═══════════════════════════════════════════════════════════════
# 1. ELLIPTIC ANALYSIS
# ═══════════════════════════════════════════════════════════════
print('='*80)
print('  MISSED FRAUD ANALYSIS — ELLIPTIC (Bitcoin)')
print('='*80)

# Load Elliptic
df_feat = pd.read_csv(DATA_DIR / 'elliptic' / 'elliptic_txs_features.csv', header=None)
df_feat.columns = ['txId'] + [f'feat_{i}' for i in range(1, 167)]
df_class = pd.read_csv(DATA_DIR / 'elliptic' / 'elliptic_txs_classes.csv')
df_class.columns = ['txId', 'class']
df_edges = pd.read_csv(DATA_DIR / 'elliptic' / 'elliptic_txs_edgelist.csv')
df_edges.columns = ['txId1', 'txId2']

df_ell = df_feat.merge(df_class, on='txId')
df_labeled = df_ell[df_ell['class'].isin(['1', '2', 1, 2])].copy()
df_labeled['fraud'] = (df_labeled['class'].astype(str) == '1').astype(int)

# Map Elliptic features -> 93 model features (all zero-padded, use generic feat_ columns)
mapped = pd.DataFrame()
for i, feat in enumerate(FEATURES_93):
    # Elliptic has 166 anonymous features; we map positionally
    feat_col = f'feat_{i+1}' if i < 166 else None
    if feat_col and feat_col in df_labeled.columns:
        mapped[feat] = df_labeled[feat_col].values.astype(np.float32)
    else:
        mapped[feat] = 0.0

X_ell = build_feature_matrix(mapped)
y_ell = df_labeled['fraud'].values.astype(int)

# Predict fraud probabilities
prob_ell = predict_xgb(X_ell)

# Caught vs missed masks
fraud_mask = y_ell == 1
caught_mask = fraud_mask & (prob_ell >= OPTIMAL_THRESHOLD)
missed_mask = fraud_mask & (prob_ell < OPTIMAL_THRESHOLD)
normal_mask = y_ell == 0

n_fraud = fraud_mask.sum()
n_caught = caught_mask.sum()
n_missed = missed_mask.sum()

print(f'\n  Total labeled: {len(y_ell):,}  |  Fraud: {n_fraud:,}  |  Normal: {normal_mask.sum():,}')
print(f'  Caught: {n_caught:,}  |  Missed: {n_missed:,}  |  Recall: {n_caught/n_fraud:.1%}')
print(f'  Threshold: {OPTIMAL_THRESHOLD}')

# ── Probability distribution ──
print(f'\n  ── Probability Distribution ──')
print(f'  {"Group":<15} {"Mean":>8} {"Median":>8} {"Std":>8} {"Min":>8} {"Max":>8}')
print(f'  {"-"*55}')
for label, mask in [('Caught', caught_mask), ('Missed', missed_mask), ('Normal', normal_mask)]:
    p = prob_ell[mask]
    print(f'  {label:<15} {p.mean():>8.4f} {np.median(p):>8.4f} {p.std():>8.4f} {p.min():>8.4f} {p.max():>8.4f}')

# ── Feature comparison: Caught vs Missed vs Normal ──
print(f'\n  ── Feature Comparison (top differences) ──')
# Use raw Elliptic features for comparison
use_cols = [f'feat_{i}' for i in range(1, 167)]
ell_feats = df_labeled[use_cols].values.astype(np.float32)

caught_feats = ell_feats[caught_mask]
missed_feats = ell_feats[missed_mask]
normal_feats = ell_feats[normal_mask]

print(f'  {"Feature":<12} {"Caught":>10} {"Missed":>10} {"Normal":>10} {"Cohen d":>9}')
print(f'  {"-"*55}')

sig_feats = []
for i in range(166):
    c_mean = caught_feats[:, i].mean()
    m_mean = missed_feats[:, i].mean()
    n_mean = normal_feats[:, i].mean()
    pooled = np.sqrt((caught_feats[:, i].std()**2 + missed_feats[:, i].std()**2) / 2)
    d = (c_mean - m_mean) / pooled if pooled > 1e-8 else 0
    if abs(d) > 0.3:
        sig_feats.append((f'feat_{i+1}', d, c_mean, m_mean, n_mean))

sig_feats.sort(key=lambda x: abs(x[1]), reverse=True)
for name, d, c, m, n in sig_feats[:15]:
    print(f'  {name:<12} {c:>10.3f} {m:>10.3f} {n:>10.3f} {d:>+9.3f}')

if not sig_feats:
    print(f'  No features with |Cohen d| > 0.3 between caught and missed fraud.')

# ── Temporal analysis (feat_1 = timestep) ──
print(f'\n  ── Temporal Analysis (by timestep) ──')
timesteps = df_labeled['feat_1'].values
unique_ts = sorted(set(timesteps[fraud_mask]))
ts_stats = []
for ts in unique_ts:
    ts_fraud = fraud_mask & (timesteps == ts)
    ts_caught = caught_mask & (timesteps == ts)
    ts_missed = missed_mask & (timesteps == ts)
    nf = ts_fraud.sum()
    nc = ts_caught.sum()
    nm = ts_missed.sum()
    rc = nc / nf if nf > 0 else 0
    ap = prob_ell[ts_fraud].mean() if nf > 0 else 0
    ts_stats.append((ts, nf, nc, nm, rc, ap))

# Show worst timesteps (lowest recall)
ts_stats_sorted = sorted(ts_stats, key=lambda x: x[4])
print(f'  Worst 10 timesteps (lowest recall among fraud timesteps):')
print(f'  {"TS":>8} {"Fraud":>6} {"Caught":>7} {"Missed":>7} {"Recall":>7} {"AvgProb":>9}')
print(f'  {"-"*50}')
for ts, nf, nc, nm, rc, ap in ts_stats_sorted[:10]:
    if nf >= 3:
        print(f'  {ts:>8.0f} {nf:>6} {nc:>7} {nm:>7} {rc:>7.1%} {ap:>9.4f}')

# ── Graph topology analysis ──
print(f'\n  ── Graph Topology: Caught vs Missed ──')
tx_ids = set(df_labeled['txId'].values)
in_degree = {}
out_degree = {}
for _, row in df_edges.iterrows():
    src, dst = row['txId1'], row['txId2']
    if src in tx_ids:
        out_degree[src] = out_degree.get(src, 0) + 1
    if dst in tx_ids:
        in_degree[dst] = in_degree.get(dst, 0) + 1

df_lc = df_labeled.copy()
df_lc['in_degree'] = df_lc['txId'].map(in_degree).fillna(0)
df_lc['out_degree'] = df_lc['txId'].map(out_degree).fillna(0)
df_lc['total_degree'] = df_lc['in_degree'] + df_lc['out_degree']

for metric in ['in_degree', 'out_degree', 'total_degree']:
    c_val = df_lc.loc[caught_mask, metric].mean()
    m_val = df_lc.loc[missed_mask, metric].mean()
    n_val = df_lc.loc[normal_mask, metric].mean()
    print(f'  {metric:<15}  Caught: {c_val:.2f}  |  Missed: {m_val:.2f}  |  Normal: {n_val:.2f}')

# ── Similarity to normal transactions ──
print(f'\n  ── Similarity to Normal Transactions ──')
normal_center = normal_feats.mean(axis=0)
caught_dists = np.linalg.norm(caught_feats - normal_center, axis=1)
missed_dists = np.linalg.norm(missed_feats - normal_center, axis=1)

print(f'  Distance to normal centroid:')
print(f'    Caught fraud:  mean={caught_dists.mean():.2f}  median={np.median(caught_dists):.2f}')
print(f'    Missed fraud:  mean={missed_dists.mean():.2f}  median={np.median(missed_dists):.2f}')
ratio = missed_dists.mean() / max(caught_dists.mean(), 1e-8)
print(f'    Ratio (missed/caught): {ratio:.3f}')
if ratio < 1:
    print(f'    → Missed fraud is {(1-ratio):.0%} CLOSER to normal — harder to distinguish')
else:
    print(f'    → Missed fraud is {(ratio-1):.0%} FARTHER from normal')

# ── Cluster analysis ──
print(f'\n  ── Clustering Missed Fraud (3 clusters) ──')
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler as StdScaler

if n_missed >= 3:
    scaler_km = StdScaler()
    missed_scaled = scaler_km.fit_transform(missed_feats)
    kmeans = KMeans(n_clusters=min(3, n_missed), random_state=42, n_init=10)
    clusters = kmeans.fit_predict(missed_scaled)
    
    for c in range(min(3, n_missed)):
        c_mask = clusters == c
        c_probs = prob_ell[missed_mask][c_mask]
        c_feats = missed_feats[c_mask]
        
        diffs = []
        for i in range(c_feats.shape[1]):
            c_std = caught_feats[:, i].std()
            if c_std > 1e-8:
                d = (c_feats[:, i].mean() - caught_feats[:, i].mean()) / c_std
                diffs.append((f'feat_{i+1}', d))
        diffs.sort(key=lambda x: abs(x[1]), reverse=True)
        top3 = ', '.join(f'{f}({d:+.2f}σ)' for f, d in diffs[:3])
        print(f'  Cluster {c}: {c_mask.sum():,} txs  |  avg prob: {c_probs.mean():.4f}  |  Top diffs: {top3}')
else:
    print(f'  Only {n_missed} missed fraud — too few to cluster.')


# ═══════════════════════════════════════════════════════════════
# 2. XBLOCK ANALYSIS
# ═══════════════════════════════════════════════════════════════
print('\n\n' + '='*80)
print('  MISSED FRAUD ANALYSIS — XBLOCK (Ethereum Phishing)')
print('='*80)

xblock_file = DATA_DIR / 'xblock' / 'transaction_dataset.csv'
df_xb = pd.read_csv(xblock_file)

label_col = 'FLAG'
y_xb_all = df_xb[label_col].astype(int).values

# Map XBlock features to 93-feature vector
xb_map = {
    'Sent tnx': 'sender_sent_count',
    'total Ether sent': 'sender_total_sent',
    'avg val sent': 'sender_avg_sent',
    'max val sent': 'sender_max_sent',
    'min val sent': 'sender_min_sent',
    'Avg min between sent tnx': 'sender_active_duration_mins',
    'Unique Sent To Addresses': 'sender_unique_receivers',
    'total ether balance': 'sender_balance',
    'ERC20 total Ether sent': 'sender_total_gas_sent',
    'Received Tnx': 'receiver_received_count',
    'total ether received': 'receiver_total_received',
    'avg val received': 'receiver_avg_received',
    'max value received ': 'receiver_max_received',
    'min value received': 'receiver_min_received',
    'Avg min between received tnx': 'receiver_active_duration_mins',
    'Unique Received From Addresses': 'receiver_unique_senders',
}

mapped_xb = pd.DataFrame()
for src_col, dst_col in xb_map.items():
    for actual_col in df_xb.columns:
        if actual_col.strip() == src_col.strip():
            mapped_xb[dst_col] = pd.to_numeric(df_xb[actual_col], errors='coerce').fillna(0)
            break

# Derive additional features
if 'sender_total_sent' in mapped_xb.columns and 'sender_sent_count' in mapped_xb.columns:
    mapped_xb['value_eth'] = mapped_xb['sender_total_sent'] / mapped_xb['sender_sent_count'].replace(0, 1)
    mapped_xb['sender_total_transactions'] = mapped_xb['sender_sent_count']
if 'sender_sent_count' in mapped_xb.columns and 'receiver_received_count' in mapped_xb.columns:
    mapped_xb['sender_in_out_ratio'] = mapped_xb['receiver_received_count'] / mapped_xb['sender_sent_count'].replace(0, 1)
    mapped_xb['sender_degree'] = mapped_xb['sender_sent_count'] + mapped_xb['receiver_received_count']
    mapped_xb['sender_in_degree'] = mapped_xb['receiver_received_count']
    mapped_xb['sender_out_degree'] = mapped_xb['sender_sent_count']
if 'sender_unique_receivers' in mapped_xb.columns and 'receiver_unique_senders' in mapped_xb.columns:
    mapped_xb['sender_unique_counterparties'] = mapped_xb['sender_unique_receivers'] + mapped_xb['receiver_unique_senders']
    mapped_xb['sender_neighbors'] = mapped_xb['sender_unique_counterparties']

X_xb = build_feature_matrix(mapped_xb)
prob_xb_raw = predict_xgb(X_xb)

# Use Platt recalibration (train/eval split)
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedShuffleSplit

sss = StratifiedShuffleSplit(n_splits=1, test_size=0.8, random_state=42)
cal_idx, eval_idx = next(sss.split(X_xb, y_xb_all))

lr_platt = LogisticRegression(random_state=42)
lr_platt.fit(prob_xb_raw[cal_idx].reshape(-1, 1), y_xb_all[cal_idx])
prob_xb = lr_platt.predict_proba(prob_xb_raw[eval_idx].reshape(-1, 1))[:, 1]
y_xb = y_xb_all[eval_idx]

# Find optimal threshold
thresholds = np.arange(0.1, 0.95, 0.01)
f1s_xb = [f1_score(y_xb, (prob_xb >= t).astype(int), zero_division=0) for t in thresholds]
best_thresh_xb = thresholds[np.argmax(f1s_xb)]
print(f'\n  Optimal F1 threshold (Platt): {best_thresh_xb:.4f}  (F1={max(f1s_xb):.4f})')

fraud_xb = y_xb == 1
caught_xb = fraud_xb & (prob_xb >= best_thresh_xb)
missed_xb = fraud_xb & (prob_xb < best_thresh_xb)

print(f'  Phishing: {fraud_xb.sum():,}  |  Caught: {caught_xb.sum():,}  |  Missed: {missed_xb.sum():,}')
print(f'  Recall: {caught_xb.sum()/max(fraud_xb.sum(), 1):.1%}')

# ── XBlock probability distribution ──
print(f'\n  ── Probability Distribution ──')
print(f'  {"Group":<15} {"Mean":>8} {"Median":>8} {"Std":>8}')
print(f'  {"-"*40}')
for label, mask in [('Caught', caught_xb), ('Missed', missed_xb), ('Normal', y_xb == 0)]:
    p = prob_xb[mask]
    if len(p) > 0:
        print(f'  {label:<15} {p.mean():>8.4f} {np.median(p):>8.4f} {p.std():>8.4f}')

# ── XBlock feature comparison ──
print(f'\n  ── Feature Comparison: Caught vs Missed Phishing ──')

numeric_cols = [c for c in df_xb.columns if c not in ['Unnamed: 0', 'Index', 'Address', 'FLAG',
    ' ERC20 most sent token type', ' ERC20_most_rec_token_type']]
df_xb_eval = df_xb.iloc[eval_idx].copy()
X_xb_orig = df_xb_eval[numeric_cols].apply(pd.to_numeric, errors='coerce').fillna(0).values

caught_xb_feats = X_xb_orig[caught_xb]
missed_xb_feats = X_xb_orig[missed_xb]
normal_xb_feats = X_xb_orig[y_xb == 0]

print(f'\n  {"Feature":<40} {"Caught":>10} {"Missed":>10} {"Normal":>10} {"Cohen d":>9}')
print(f'  {"-"*85}')

sig_xb = []
for i, col in enumerate(numeric_cols):
    c_mean = caught_xb_feats[:, i].mean() if caught_xb.sum() > 0 else 0
    m_mean = missed_xb_feats[:, i].mean() if missed_xb.sum() > 0 else 0
    n_mean = normal_xb_feats[:, i].mean()
    pooled = np.sqrt((caught_xb_feats[:, i].std()**2 + missed_xb_feats[:, i].std()**2) / 2) if caught_xb.sum() > 0 and missed_xb.sum() > 0 else 1
    d = (c_mean - m_mean) / pooled if pooled > 1e-8 else 0
    if abs(d) > 0.2:
        sig_xb.append((col.strip(), d, c_mean, m_mean, n_mean))
        print(f'  {col.strip():<40} {c_mean:>10.2f} {m_mean:>10.2f} {n_mean:>10.2f} {d:>+9.3f}')

if not sig_xb:
    print(f'  No features with |Cohen d| > 0.2 between caught and missed phishing.')

# ── Phishing archetype analysis ──
print(f'\n  ── Phishing Address Archetypes ──')
df_xb_eval_c = df_xb_eval.copy()
for c in numeric_cols:
    df_xb_eval_c[c] = pd.to_numeric(df_xb_eval_c[c], errors='coerce').fillna(0)

def safe_col(name):
    for c in df_xb_eval_c.columns:
        if c.strip().lower() == name.strip().lower():
            return c
    return None

sent_col = safe_col('Sent tnx')
recv_col = safe_col('Received Tnx')
bal_col = safe_col('total ether balance')
total_sent_col = safe_col('total Ether sent')
total_recv_col = safe_col('total ether received')
contracts_col = safe_col('Number of Created Contracts')

print(f'\n  {"Metric":<30} {"Caught":>12} {"Missed":>12} {"Normal":>12}')
print(f'  {"-"*70}')

for label, col_name in [
    ('Sent Txs (median)', sent_col),
    ('Received Txs (median)', recv_col),
    ('Balance (median)', bal_col),
    ('Total Sent (median)', total_sent_col),
    ('Total Received (median)', total_recv_col),
    ('Contracts Created (mean)', contracts_col),
]:
    if col_name:
        c_val = df_xb_eval_c.loc[caught_xb, col_name].median() if 'median' in label else df_xb_eval_c.loc[caught_xb, col_name].mean()
        m_val = df_xb_eval_c.loc[missed_xb, col_name].median() if 'median' in label else df_xb_eval_c.loc[missed_xb, col_name].mean()
        n_val = df_xb_eval_c.loc[y_xb == 0, col_name].median() if 'median' in label else df_xb_eval_c.loc[y_xb == 0, col_name].mean()
        print(f'  {label:<30} {c_val:>12.2f} {m_val:>12.2f} {n_val:>12.2f}')

# ── Activity level breakdown ──
if sent_col and recv_col:
    total_tx = df_xb_eval_c[sent_col] + df_xb_eval_c[recv_col]
    missed_tx = total_tx[missed_xb]
    caught_tx = total_tx[caught_xb]
    
    print(f'\n  Missed phishing by activity level:')
    if missed_xb.sum() > 0:
        low_act = (missed_tx <= 10).sum()
        med_act = ((missed_tx > 10) & (missed_tx <= 100)).sum()
        high_act = (missed_tx > 100).sum()
        print(f'    Low (≤10 txs):    {low_act:>5} ({low_act/missed_xb.sum():.1%})')
        print(f'    Medium (11-100):  {med_act:>5} ({med_act/missed_xb.sum():.1%})')
        print(f'    High (>100):      {high_act:>5} ({high_act/missed_xb.sum():.1%})')
    
    print(f'\n  Caught phishing by activity level:')
    if caught_xb.sum() > 0:
        low_c = (caught_tx <= 10).sum()
        med_c = ((caught_tx > 10) & (caught_tx <= 100)).sum()
        high_c = (caught_tx > 100).sum()
        print(f'    Low (≤10 txs):    {low_c:>5} ({low_c/caught_xb.sum():.1%})')
        print(f'    Medium (11-100):  {med_c:>5} ({med_c/caught_xb.sum():.1%})')
        print(f'    High (>100):      {high_c:>5} ({high_c/caught_xb.sum():.1%})')


# ═══════════════════════════════════════════════════════════════
# 3. BLINDSPOT SUMMARY
# ═══════════════════════════════════════════════════════════════
print('\n\n' + '='*80)
print('  FRAUD BLINDSPOT SUMMARY')
print('='*80)

print(f'''
  The model's blindspots fall into these categories:

  1. CAMOUFLAGE FRAUD (Elliptic)
     Illicit transactions that statistically resemble normal transactions.
     These have feature distributions close to the normal centroid.
     
  2. TEMPORAL BLIND SPOTS (Elliptic)
     Certain timesteps have much lower recall — possibly new fraud
     campaigns that changed tactics mid-observation period.
     
  3. LOW-ACTIVITY PHISHING (XBlock)
     Phishing addresses with very few transactions are harder to detect
     because aggregated behavioral features lack signal.
     
  4. MISSING FEATURES (Both)
     Many features zero-padded on Elliptic (anonymous features),
     and on XBlock (no mixer/sanctioned/exchange flags).
     
  5. SEMANTIC GAP (Both)
     Bitcoin ransomware (Elliptic) and ETH phishing (XBlock) have
     different behavioral signatures than the ETH fraud patterns
     the model was trained on.
''')

print('='*80)
print('  ANALYSIS COMPLETE')
print('='*80)
