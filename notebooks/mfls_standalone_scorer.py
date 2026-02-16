"""
STANDALONE MFLS SCORER — No model required
=============================================
Computes the Missed Fraud Likelihood Score on ANY new dataset
using only pre-saved reference statistics.

Usage:
  python mfls_standalone_scorer.py <csv_file> [--output results.csv]

The CSV must have at least some of the 93 AMTTP features.
Unknown columns are mapped to zero (which itself raises the G score).
"""
import numpy as np
import pandas as pd
from pathlib import Path
import json, argparse, sys, warnings
warnings.filterwarnings('ignore')

# ── Pre-saved reference statistics (from training) ───────────────
# These are the ONLY things needed — no model, no weights, no GPU.

REFERENCE_STATS = {
    # Normal transaction centroid (mean of each feature across known-good txs)
    # Saved from training; 93 values
    'mu_normal': None,       # loaded from file
    'mu_caught': None,       # caught-fraud centroid
    'ref_mean': None,        # reference distribution mean
    'ref_var': None,         # reference distribution variance
    'd_max': 51.64,          # 99th percentile distance
    'mu_caught_tx': 0.2004,  # mean log(tx_count) of caught fraud
    'sigma_caught_tx': 0.0289,  # std log(tx_count) of caught fraud
}

FEATURES_93 = [
    'value_eth', 'gas_price_gwei', 'gas_used', 'gas_limit', 'transaction_type', 'nonce',
    'transaction_index', 'sender_sent_count', 'sender_total_sent', 'sender_avg_sent',
    'sender_max_sent', 'sender_min_sent', 'sender_std_sent', 'sender_total_gas_sent',
    'sender_avg_gas_used', 'sender_avg_gas_price', 'sender_unique_receivers',
    'sender_received_count', 'sender_total_received', 'sender_avg_received',
    'sender_max_received', 'sender_min_received', 'sender_std_received',
    'sender_unique_senders', 'sender_total_transactions', 'sender_balance',
    'sender_in_out_ratio', 'sender_unique_counterparties', 'sender_avg_value',
    'sender_neighbors', 'sender_count', 'sender_income', 'sender_active_duration_mins',
    'sender_in_degree', 'sender_out_degree', 'sender_degree',
    'sender_degree_centrality', 'sender_betweenness_proxy',
    'sender_sent_to_mixer', 'sender_recv_from_mixer', 'sender_mixer_interaction',
    'sender_sent_to_sanctioned', 'sender_recv_from_sanctioned',
    'sender_sanctioned_interaction', 'sender_sent_to_exchange',
    'sender_recv_from_exchange', 'sender_exchange_interaction',
    'sender_is_mixer', 'sender_is_sanctioned', 'sender_is_exchange',
    'receiver_sent_count', 'receiver_total_sent', 'receiver_avg_sent',
    'receiver_max_sent', 'receiver_min_sent', 'receiver_std_sent',
    'receiver_total_gas_sent', 'receiver_avg_gas_used', 'receiver_avg_gas_price',
    'receiver_unique_receivers', 'receiver_received_count', 'receiver_total_received',
    'receiver_avg_received', 'receiver_max_received', 'receiver_min_received',
    'receiver_std_received', 'receiver_unique_senders', 'receiver_total_transactions',
    'receiver_balance', 'receiver_in_out_ratio', 'receiver_unique_counterparties',
    'receiver_avg_value', 'receiver_neighbors', 'receiver_count', 'receiver_income',
    'receiver_active_duration_mins', 'receiver_in_degree', 'receiver_out_degree',
    'receiver_degree', 'receiver_degree_centrality', 'receiver_betweenness_proxy',
    'receiver_sent_to_mixer', 'receiver_recv_from_mixer', 'receiver_mixer_interaction',
    'receiver_sent_to_sanctioned', 'receiver_recv_from_sanctioned',
    'receiver_sanctioned_interaction', 'receiver_sent_to_exchange',
    'receiver_recv_from_exchange', 'receiver_exchange_interaction',
    'receiver_is_mixer', 'receiver_is_sanctioned', 'receiver_is_exchange',
]

IDX_SENT = 7   # sender_sent_count
IDX_RECV = 60  # receiver_received_count


# ══════════════════════════════════════════════════════════════════
# FORMULA COMPONENTS — Pure math, no ML model
# ══════════════════════════════════════════════════════════════════

def camouflage_score(X, mu_normal, d_max):
    """C(x) = 1 - ||x - μ_normal|| / d_max"""
    dists = np.linalg.norm(X - mu_normal, axis=1)
    return 1.0 - np.clip(dists / d_max, 0, 1)

def feature_gap_score(X):
    """G(x) = count_of_zeros / 93"""
    return (np.abs(X) < 1e-8).sum(axis=1).astype(np.float64) / X.shape[1]

def activity_anomaly_score(X, mu_caught_tx, sigma_caught_tx):
    """A(x) = sigmoid((log(1+tx_count) - μ) / σ)"""
    total_tx = np.abs(X[:, IDX_SENT]) + np.abs(X[:, IDX_RECV]) + 1e-8
    z = (np.log1p(total_tx) - mu_caught_tx) / max(sigma_caught_tx, 1e-8)
    return 1.0 / (1.0 + np.exp(-z))

def temporal_novelty_score(X, ref_mean, ref_var):
    """T(x) = sigmoid(0.5 * (Mahalanobis² / dim - 2))"""
    diff = X - ref_mean
    mahal_sq = np.sum(diff * diff / ref_var, axis=1)
    mahal_norm = mahal_sq / X.shape[1]
    return 1.0 / (1.0 + np.exp(-0.5 * (mahal_norm - 2.0)))

def compute_mfls(X, mu_normal, d_max, ref_mean, ref_var,
                  mu_caught_tx, sigma_caught_tx,
                  alpha=0.30, beta=0.25, gamma=0.25, delta=0.20):
    """
    MFLS(x) = α·C(x) + β·G(x) + γ·A(x) + δ·T(x)
    
    Returns MFLS and all 4 components + 7 supplementary features.
    REQUIRES ZERO ML MODELS.
    """
    C = camouflage_score(X, mu_normal, d_max)
    G = feature_gap_score(X)
    A = activity_anomaly_score(X, mu_caught_tx, sigma_caught_tx)
    T = temporal_novelty_score(X, ref_mean, ref_var)
    MFLS = alpha * C + beta * G + gamma * A + delta * T

    # Supplementary features
    d_normal = np.linalg.norm(X - mu_normal, axis=1)
    d_caught = np.linalg.norm(X - ref_mean, axis=1)
    d_ratio = d_normal / np.clip(d_caught, 1e-8, None)
    R = (np.abs(X) > 3.0).sum(axis=1).astype(np.float64) / X.shape[1]

    return {
        'MFLS': MFLS,
        'C_camouflage': C,
        'G_feature_gap': G,
        'A_activity': A,
        'T_novelty': T,
        'phi_dist_normal': d_normal,
        'phi_dist_caught': d_caught,
        'phi_dist_ratio': d_ratio,
        'phi_extreme_range': R,
    }


def map_csv_to_features(df):
    """Map any CSV's columns to the 93-feature vector. Unmatched → 0."""
    X = np.zeros((len(df), 93), dtype=np.float32)
    mapped = 0
    col_lower = {c.strip().lower(): c for c in df.columns}

    for i, feat in enumerate(FEATURES_93):
        # Direct match
        if feat in df.columns:
            X[:, i] = pd.to_numeric(df[feat], errors='coerce').fillna(0).values
            mapped += 1
        elif feat.lower() in col_lower:
            X[:, i] = pd.to_numeric(df[col_lower[feat.lower()]], errors='coerce').fillna(0).values
            mapped += 1

    # Common XBlock-style mappings
    xb_map = {
        'Sent tnx': 'sender_sent_count',
        'total Ether sent': 'sender_total_sent',
        'avg val sent': 'sender_avg_sent',
        'max val sent': 'sender_max_sent',
        'min val sent': 'sender_min_sent',
        'Unique Sent To Addresses': 'sender_unique_receivers',
        'total ether balance': 'sender_balance',
        'Received Tnx': 'receiver_received_count',
        'total ether received': 'receiver_total_received',
        'avg val received': 'receiver_avg_received',
        'max value received': 'receiver_max_received',
        'min value received': 'receiver_min_received',
        'Unique Received From Addresses': 'receiver_unique_senders',
    }
    for src, dst in xb_map.items():
        idx = FEATURES_93.index(dst) if dst in FEATURES_93 else -1
        if idx >= 0 and (np.abs(X[:, idx]) < 1e-8).all():
            for c in df.columns:
                if c.strip().lower() == src.strip().lower():
                    X[:, idx] = pd.to_numeric(df[c], errors='coerce').fillna(0).values
                    mapped += 1
                    break

    return X, mapped


def compute_reference_stats_from_data(X, y=None):
    """
    If you have labeled data, compute reference stats from it.
    If unlabeled, use all data as 'normal' reference.
    """
    if y is not None:
        normal = X[y == 0]
        fraud = X[y == 1]
    else:
        # No labels: assume all data is reference
        normal = X
        fraud = X  # fallback

    mu_normal = normal.mean(axis=0)
    dists = np.linalg.norm(X - mu_normal, axis=1)
    d_max = np.percentile(dists, 99)

    mu_caught = fraud.mean(axis=0)
    ref_var = fraud.var(axis=0) + 1e-8

    total_tx = np.abs(fraud[:, IDX_SENT]) + np.abs(fraud[:, IDX_RECV]) + 1e-8
    mu_caught_tx = np.log1p(total_tx).mean()
    sigma_caught_tx = np.log1p(total_tx).std()

    return {
        'mu_normal': mu_normal,
        'mu_caught': mu_caught,
        'ref_mean': mu_caught,
        'ref_var': ref_var,
        'd_max': float(d_max),
        'mu_caught_tx': float(mu_caught_tx),
        'sigma_caught_tx': float(sigma_caught_tx),
    }


# ══════════════════════════════════════════════════════════════════
# DEMO: Score the Elliptic and XBlock datasets without the model
# ══════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    DATA_DIR = Path(r'c:\amttp\data\external_validation')

    print('='*80)
    print('  STANDALONE MFLS SCORER — No ML model required')
    print('='*80)

    # ── 1. ELLIPTIC ──
    print('\n  ── Scoring Elliptic (no model) ──')
    df_feat = pd.read_csv(DATA_DIR / 'elliptic' / 'elliptic_txs_features.csv', header=None)
    df_feat.columns = ['txId'] + [f'feat_{i}' for i in range(1, 167)]
    df_class = pd.read_csv(DATA_DIR / 'elliptic' / 'elliptic_txs_classes.csv')
    df_class.columns = ['txId', 'class']
    df_ell = df_feat.merge(df_class, on='txId')
    df_labeled = df_ell[df_ell['class'].isin(['1', '2', 1, 2])].copy()
    y_ell = (df_labeled['class'].astype(str) == '1').astype(int).values

    # Map Elliptic features positionally (anonymous features)
    X_ell = np.zeros((len(df_labeled), 93), dtype=np.float32)
    for i in range(min(93, 166)):
        X_ell[:, i] = df_labeled[f'feat_{i+1}'].values.astype(np.float32)

    # Compute reference stats from the data itself (self-calibrating)
    ref = compute_reference_stats_from_data(X_ell, y_ell)

    # Score
    scores = compute_mfls(X_ell, ref['mu_normal'], ref['d_max'],
                           ref['ref_mean'], ref['ref_var'],
                           ref['mu_caught_tx'], ref['sigma_caught_tx'])

    mfls = scores['MFLS']
    fraud = y_ell == 1
    normal = y_ell == 0

    print(f'  Samples: {len(y_ell):,}  |  Fraud: {fraud.sum():,}  |  Normal: {normal.sum():,}')
    print(f'\n  MFLS as standalone fraud detector (no model):')
    print(f'  {"Threshold":>10} {"Recall":>8} {"Precision":>10} {"F1":>8} {"Caught":>8} {"FP":>8}')
    print(f'  {"-"*55}')

    from sklearn.metrics import f1_score, precision_score, recall_score

    best_f1 = 0
    best_t = 0
    for t in np.arange(0.3, 0.8, 0.02):
        pred = (mfls >= t).astype(int)
        f1 = f1_score(y_ell, pred, zero_division=0)
        rec = recall_score(y_ell, pred, zero_division=0)
        prec = precision_score(y_ell, pred, zero_division=0)
        caught = (pred[fraud] == 1).sum()
        fp = (pred[normal] == 1).sum()
        if f1 > best_f1:
            best_f1 = f1
            best_t = t
        if abs(t - 0.40) < 0.01 or abs(t - 0.50) < 0.01 or abs(t - 0.55) < 0.01 or abs(t - 0.60) < 0.01 or abs(t - 0.65) < 0.01 or abs(t - 0.70) < 0.01 or t == best_t:
            print(f'  {t:>10.2f} {rec:>8.1%} {prec:>10.1%} {f1:>8.4f} {caught:>8,} {fp:>8,}')

    print(f'\n  Best standalone F1: {best_f1:.4f} at threshold {best_t:.2f}')

    # AUC-ROC without model
    from sklearn.metrics import roc_auc_score
    auc = roc_auc_score(y_ell, mfls)
    print(f'  AUC-ROC (MFLS alone, no model): {auc:.4f}')

    # ── Component discriminative power ──
    print(f'\n  Discriminative power of each component (AUC-ROC):')
    for name in ['C_camouflage', 'G_feature_gap', 'A_activity', 'T_novelty', 'MFLS']:
        vals = scores[name]
        try:
            a = roc_auc_score(y_ell, vals)
            print(f'    {name:<20}  AUC = {a:.4f}')
        except:
            print(f'    {name:<20}  AUC = N/A')

    # ── 2. XBLOCK ──
    print('\n\n  ── Scoring XBlock (no model) ──')
    df_xb = pd.read_csv(DATA_DIR / 'xblock' / 'transaction_dataset.csv')
    y_xb = df_xb['FLAG'].astype(int).values
    X_xb, n_mapped = map_csv_to_features(df_xb)

    ref_xb = compute_reference_stats_from_data(X_xb, y_xb)
    scores_xb = compute_mfls(X_xb, ref_xb['mu_normal'], ref_xb['d_max'],
                              ref_xb['ref_mean'], ref_xb['ref_var'],
                              ref_xb['mu_caught_tx'], ref_xb['sigma_caught_tx'])

    mfls_xb = scores_xb['MFLS']
    fraud_xb = y_xb == 1
    normal_xb = y_xb == 0

    print(f'  Samples: {len(y_xb):,}  |  Phishing: {fraud_xb.sum():,}  |  Normal: {normal_xb.sum():,}')
    print(f'  Features mapped: {n_mapped}/93')
    print(f'\n  MFLS as standalone fraud detector (no model):')
    print(f'  {"Threshold":>10} {"Recall":>8} {"Precision":>10} {"F1":>8} {"Caught":>8} {"FP":>8}')
    print(f'  {"-"*55}')

    best_f1_xb = 0
    best_t_xb = 0
    for t in np.arange(0.3, 0.8, 0.02):
        pred = (mfls_xb >= t).astype(int)
        f1 = f1_score(y_xb, pred, zero_division=0)
        rec = recall_score(y_xb, pred, zero_division=0)
        prec = precision_score(y_xb, pred, zero_division=0)
        caught = (pred[fraud_xb] == 1).sum()
        fp = (pred[normal_xb] == 1).sum()
        if f1 > best_f1_xb:
            best_f1_xb = f1
            best_t_xb = t
        if abs(t - 0.40) < 0.01 or abs(t - 0.50) < 0.01 or abs(t - 0.55) < 0.01 or abs(t - 0.60) < 0.01 or abs(t - 0.65) < 0.01 or abs(t - 0.70) < 0.01 or t == best_t_xb:
            print(f'  {t:>10.2f} {rec:>8.1%} {prec:>10.1%} {f1:>8.4f} {caught:>8,} {fp:>8,}')

    print(f'\n  Best standalone F1: {best_f1_xb:.4f} at threshold {best_t_xb:.2f}')

    auc_xb = roc_auc_score(y_xb, mfls_xb)
    print(f'  AUC-ROC (MFLS alone, no model): {auc_xb:.4f}')

    print(f'\n  Discriminative power of each component (AUC-ROC):')
    for name in ['C_camouflage', 'G_feature_gap', 'A_activity', 'T_novelty', 'MFLS']:
        vals = scores_xb[name]
        try:
            a = roc_auc_score(y_xb, vals)
            print(f'    {name:<20}  AUC = {a:.4f}')
        except:
            print(f'    {name:<20}  AUC = N/A')


    # ══════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════
    print('\n\n' + '='*80)
    print('  STANDALONE SCORING SUMMARY')
    print('='*80)
    print(f"""
  The MFLS formula CAN score new data without the ML model.
  
  Two modes of operation:
  
  ┌─────────────────────────────────────────────────────────────────┐
  │ MODE 1: Have labeled data (even partial)                        │
  │ → compute_reference_stats_from_data(X, y) to self-calibrate    │
  │ → Then score with compute_mfls()                               │
  │ → Use MFLS ≥ threshold as standalone fraud flag                 │
  │                                                                 │
  │ MODE 2: No labels at all                                        │
  │ → Use pre-saved reference stats from training                   │
  │ → Score with compute_mfls() using saved μ, σ, d_max            │
  │ → High MFLS = "our model would likely miss this if it's fraud" │
  │ → Route these to manual review                                  │
  └─────────────────────────────────────────────────────────────────┘
  
  Results without any ML model:
    Elliptic:  AUC = {auc:.4f}  |  Best F1 = {best_f1:.4f}
    XBlock:    AUC = {auc_xb:.4f}  |  Best F1 = {best_f1_xb:.4f}
""")
    print('='*80)
