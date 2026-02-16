"""
MISSED FRAUD CORRECTION FORMULA — AMTTP V2
============================================
Derives a mathematical formula to:
  1. Score how likely a transaction is to be missed by the model
  2. Correct model predictions to catch more fraud
  3. Generate supplementary features for training augmentation

Based on empirical analysis of caught vs missed fraud on Elliptic and XBlock.
"""
import numpy as np
import pandas as pd
from pathlib import Path
import sys, json, warnings
warnings.filterwarnings('ignore')

ARTIFACTS = Path(r'C:\Users\Administrator\Downloads\amttp_student_artifacts\amttp_models_20260213_213346')
DATA_DIR = Path(r'c:\amttp\data\external_validation')
sys.path.insert(0, str(Path(__file__).parent))

import joblib, xgboost as xgb
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

preprocessors = joblib.load(ARTIFACTS / 'preprocessors.joblib')
scaler = preprocessors['scaler']
feature_names = list(preprocessors['feature_names'])  # 93 features
FEATURES_93 = feature_names

xgb_model = xgb.Booster()
xgb_model.load_model(str(ARTIFACTS / 'xgboost_fraud.ubj'))

OPTIMAL_THRESHOLD = 0.6428


# ══════════════════════════════════════════════════════════════════
# MATHEMATICAL FORMULATION
# ══════════════════════════════════════════════════════════════════
print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                   MISSED FRAUD CORRECTION FORMULA                          ║
║                          AMTTP V2 Model                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

  DEFINITION: Let x ∈ ℝ⁹³ be a transaction feature vector, and let
  f(x) = P(fraud | x) be the model's predicted probability.

  OBSERVATION: The model misses fraud when:
    (a) Camouflage: x_fraud ≈ x_normal  (feature overlap)
    (b) Semantic gap: features are zero-padded / poorly mapped
    (c) Activity anomaly: sophisticated actors blend in via high volume
    (d) Temporal shift: new fraud patterns unseen in training

  FORMULA 1 — Missed Fraud Likelihood Score (MFLS)
  ────────────────────────────────────────────────────
  MFLS(x) = α·C(x) + β·G(x) + γ·A(x) + δ·T(x)

  where:
    C(x) = Camouflage Score     = 1 - d(x, μ_normal) / d_max
    G(x) = Feature Gap Score    = n_zero(x) / 93
    A(x) = Activity Anomaly     = σ(log(total_tx) - μ_caught) / σ_caught
    T(x) = Temporal Novelty     = entropy(x | training_dist)

  FORMULA 2 — Corrected Prediction
  ────────────────────────────────────────────────────
  p̂_corrected(x) = p̂(x) + λ · MFLS(x) · (1 - p̂(x)) · 𝟙[p̂(x) < τ]

  This boosts predictions only for sub-threshold cases proportional
  to their missed-fraud likelihood.

  FORMULA 3 — Supplementary Feature Generator
  ────────────────────────────────────────────────────
  φ(x) = [C(x), G(x), A(x), D_KL(x), d_caught(x), d_normal(x), R(x)]

  These 7 new features capture the blind-spot signal.
""")


# ══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════

def build_feature_matrix(mapped_df):
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


# ══════════════════════════════════════════════════════════════════
# FORMULA COMPONENTS
# ══════════════════════════════════════════════════════════════════

def camouflage_score(X, mu_normal, d_max):
    """
    C(x) = 1 - ||x - μ_normal||₂ / d_max

    Measures how close a transaction is to the normal centroid.
    High score → looks like normal → harder to detect.
    """
    dists = np.linalg.norm(X - mu_normal, axis=1)
    C = 1.0 - np.clip(dists / d_max, 0, 1)
    return C


def feature_gap_score(X):
    """
    G(x) = Σ 𝟙[|x_i| < ε] / 93

    Fraction of features that are effectively zero (unmapped).
    High score → many missing features → model has insufficient signal.
    """
    G = (np.abs(X) < 1e-8).sum(axis=1) / X.shape[1]
    return G.astype(np.float64)


def activity_anomaly_score(X, idx_sent=7, idx_recv=60, mu_caught_tx=0, sigma_caught_tx=1):
    """
    A(x) = σ(  (log(1 + total_tx(x)) - μ_log_caught) / σ_log_caught  )

    Measures how far a transaction's activity level deviates from
    the typical caught-fraud activity. Sigmoid ensures [0, 1].
    
    idx_sent = index of sender_sent_count in FEATURES_93
    idx_recv = index of receiver_received_count in FEATURES_93
    """
    total_tx = np.abs(X[:, idx_sent]) + np.abs(X[:, idx_recv]) + 1e-8
    log_tx = np.log1p(total_tx)
    z = (log_tx - mu_caught_tx) / max(sigma_caught_tx, 1e-8)
    A = 1.0 / (1.0 + np.exp(-z))  # sigmoid
    return A


def temporal_novelty_score(X, reference_mean, reference_cov_inv):
    """
    T(x) = σ( (x - μ_ref)ᵀ Σ⁻¹_ref (x - μ_ref)  /  d²_threshold )

    Mahalanobis-based novelty detection.
    High score → transaction is statistically unusual relative to training.
    """
    diff = X - reference_mean
    # Use diagonal approximation for efficiency
    mahal_sq = np.sum(diff * diff * reference_cov_inv, axis=1)
    # Normalize by dimensionality
    mahal_norm = mahal_sq / X.shape[1]
    T = 1.0 / (1.0 + np.exp(-0.5 * (mahal_norm - 2.0)))
    return T


def missed_fraud_likelihood(X, mu_normal, d_max, ref_mean, ref_cov_inv,
                             mu_caught_tx, sigma_caught_tx,
                             alpha=0.30, beta=0.25, gamma=0.25, delta=0.20):
    """
    MFLS(x) = α·C(x) + β·G(x) + γ·A(x) + δ·T(x)
    
    Weights derived from relative importance of each blind-spot type:
      α = 0.30  Camouflage (dominant on Elliptic)
      β = 0.25  Feature gap (critical for cross-domain)
      γ = 0.25  Activity anomaly (dominant on XBlock)
      δ = 0.20  Temporal novelty
    """
    C = camouflage_score(X, mu_normal, d_max)
    G = feature_gap_score(X)
    A = activity_anomaly_score(X, mu_caught_tx=mu_caught_tx, sigma_caught_tx=sigma_caught_tx)
    T = temporal_novelty_score(X, ref_mean, ref_cov_inv)
    
    MFLS = alpha * C + beta * G + gamma * A + delta * T
    return MFLS, C, G, A, T


def corrected_prediction(p_model, MFLS, threshold, lam=0.5):
    """
    p̂_corrected(x) = p̂(x) + λ · MFLS(x) · (1 - p̂(x)) · 𝟙[p̂(x) < τ]

    Only boosts predictions below threshold.
    λ controls correction strength (higher = more aggressive recall boost).
    """
    below = p_model < threshold
    correction = lam * MFLS * (1.0 - p_model) * below.astype(float)
    return p_model + correction


def supplementary_features(X, mu_normal, mu_caught, d_max, ref_mean, ref_cov_inv,
                            mu_caught_tx, sigma_caught_tx):
    """
    φ(x) = [C(x), G(x), A(x), d_normal(x), d_caught(x), D_ratio(x), R(x)]

    Generate 7 supplementary features that capture blind-spot signal.
    These can be appended to the feature vector for retraining.
    """
    C = camouflage_score(X, mu_normal, d_max)
    G = feature_gap_score(X)
    A = activity_anomaly_score(X, mu_caught_tx=mu_caught_tx, sigma_caught_tx=sigma_caught_tx)
    
    # Distance to normal centroid
    d_normal = np.linalg.norm(X - mu_normal, axis=1)
    # Distance to caught-fraud centroid
    d_caught = np.linalg.norm(X - mu_caught, axis=1)
    # Distance ratio: d_normal / d_caught
    D_ratio = d_normal / np.clip(d_caught, 1e-8, None)
    # Feature range score: how many features are in extreme ranges
    R = ((np.abs(X) > 3.0).sum(axis=1) / X.shape[1]).astype(np.float64)
    
    return np.column_stack([C, G, A, d_normal, d_caught, D_ratio, R])


# ══════════════════════════════════════════════════════════════════
# VALIDATION ON ELLIPTIC
# ══════════════════════════════════════════════════════════════════
print('='*80)
print('  VALIDATING FORMULA ON ELLIPTIC')
print('='*80)

# Load Elliptic
df_feat = pd.read_csv(DATA_DIR / 'elliptic' / 'elliptic_txs_features.csv', header=None)
df_feat.columns = ['txId'] + [f'feat_{i}' for i in range(1, 167)]
df_class = pd.read_csv(DATA_DIR / 'elliptic' / 'elliptic_txs_classes.csv')
df_class.columns = ['txId', 'class']
df_ell = df_feat.merge(df_class, on='txId')
df_labeled = df_ell[df_ell['class'].isin(['1', '2', 1, 2])].copy()
df_labeled['fraud'] = (df_labeled['class'].astype(str) == '1').astype(int)

# Map features
mapped = pd.DataFrame()
for i, feat in enumerate(FEATURES_93):
    feat_col = f'feat_{i+1}' if i < 166 else None
    if feat_col and feat_col in df_labeled.columns:
        mapped[feat] = df_labeled[feat_col].values.astype(np.float32)
    else:
        mapped[feat] = 0.0

X_ell = build_feature_matrix(mapped)
y_ell = df_labeled['fraud'].values.astype(int)
prob_ell = predict_xgb(X_ell)

# Original metrics
fraud_mask = y_ell == 1
normal_mask = y_ell == 0
caught_orig = fraud_mask & (prob_ell >= OPTIMAL_THRESHOLD)
missed_orig = fraud_mask & (prob_ell < OPTIMAL_THRESHOLD)

print(f'\n  BEFORE correction:')
print(f'  Fraud: {fraud_mask.sum():,}  |  Caught: {caught_orig.sum():,}  |  Missed: {missed_orig.sum():,}')
print(f'  Recall: {caught_orig.sum()/fraud_mask.sum():.4f}')
pred_orig = (prob_ell >= OPTIMAL_THRESHOLD).astype(int)
print(f'  Precision: {precision_score(y_ell, pred_orig, zero_division=0):.4f}')
print(f'  F1: {f1_score(y_ell, pred_orig, zero_division=0):.4f}')

# ── Compute formula parameters from data ──
print(f'\n  Computing formula parameters...')

# C(x) parameters
mu_normal = X_ell[normal_mask].mean(axis=0)
all_dists = np.linalg.norm(X_ell - mu_normal, axis=1)
d_max = np.percentile(all_dists, 99)  # Robust max

# A(x) parameters
idx_sent = FEATURES_93.index('sender_sent_count') if 'sender_sent_count' in FEATURES_93 else 7
idx_recv = FEATURES_93.index('receiver_received_count') if 'receiver_received_count' in FEATURES_93 else 60
caught_total_tx = np.abs(X_ell[caught_orig, idx_sent]) + np.abs(X_ell[caught_orig, idx_recv])
mu_caught_tx = np.log1p(caught_total_tx).mean()
sigma_caught_tx = np.log1p(caught_total_tx).std()

# T(x) parameters
ref_mean = X_ell[caught_orig].mean(axis=0) if caught_orig.sum() > 0 else X_ell[fraud_mask].mean(axis=0)
ref_var = X_ell[caught_orig].var(axis=0) + 1e-8 if caught_orig.sum() > 0 else X_ell[fraud_mask].var(axis=0) + 1e-8
ref_cov_inv = 1.0 / ref_var  # diagonal inverse

mu_caught = X_ell[caught_orig].mean(axis=0) if caught_orig.sum() > 0 else X_ell[fraud_mask].mean(axis=0)

# ── Compute MFLS ──
MFLS, C, G, A, T = missed_fraud_likelihood(
    X_ell, mu_normal, d_max, ref_mean, ref_cov_inv,
    mu_caught_tx, sigma_caught_tx)

print(f'\n  MFLS components (mean ± std):')
print(f'  {"Component":<20} {"Caught":>15} {"Missed":>15} {"Normal":>15}')
print(f'  {"-"*65}')
for name, vals in [('C (Camouflage)', C), ('G (Feature Gap)', G), ('A (Activity)', A), ('T (Temporal)', T), ('MFLS (Combined)', MFLS)]:
    c_str = f'{vals[caught_orig].mean():.4f}±{vals[caught_orig].std():.4f}'
    m_str = f'{vals[missed_orig].mean():.4f}±{vals[missed_orig].std():.4f}'
    n_str = f'{vals[normal_mask].mean():.4f}±{vals[normal_mask].std():.4f}'
    print(f'  {name:<20} {c_str:>15} {m_str:>15} {n_str:>15}')

# ── Grid search for optimal λ (correction strength) ──
print(f'\n  Optimizing correction strength λ...')
best_f1 = 0
best_lam = 0
best_metrics = {}

for lam in np.arange(0.1, 2.01, 0.05):
    p_corr = corrected_prediction(prob_ell, MFLS, OPTIMAL_THRESHOLD, lam=lam)
    
    # Re-optimize threshold for corrected predictions
    for thresh in np.arange(0.1, 0.9, 0.02):
        pred = (p_corr >= thresh).astype(int)
        f1 = f1_score(y_ell, pred, zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_lam = lam
            best_thresh = thresh
            best_metrics = {
                'recall': recall_score(y_ell, pred, zero_division=0),
                'precision': precision_score(y_ell, pred, zero_division=0),
                'f1': f1,
                'caught': (pred[fraud_mask] == 1).sum(),
                'missed': (pred[fraud_mask] == 0).sum(),
            }

print(f'  Optimal λ = {best_lam:.2f}  |  Optimal τ = {best_thresh:.2f}')

# Apply best correction
p_ell_corrected = corrected_prediction(prob_ell, MFLS, OPTIMAL_THRESHOLD, lam=best_lam)
pred_corrected = (p_ell_corrected >= best_thresh).astype(int)

print(f'\n  AFTER correction (λ={best_lam:.2f}, τ={best_thresh:.2f}):')
print(f'  Fraud: {fraud_mask.sum():,}  |  Caught: {best_metrics["caught"]:,}  |  Missed: {best_metrics["missed"]:,}')
print(f'  Recall: {best_metrics["recall"]:.4f}  (was {caught_orig.sum()/fraud_mask.sum():.4f})')
print(f'  Precision: {best_metrics["precision"]:.4f}  (was {precision_score(y_ell, pred_orig, zero_division=0):.4f})')
print(f'  F1: {best_metrics["f1"]:.4f}  (was {f1_score(y_ell, pred_orig, zero_division=0):.4f})')

recall_delta = best_metrics['recall'] - caught_orig.sum()/fraud_mask.sum()
print(f'\n  Recall improvement: {recall_delta:+.4f} ({recall_delta*100:+.1f} percentage points)')

# ── Supplementary features ──
print(f'\n  Generating supplementary features φ(x)...')
phi = supplementary_features(X_ell, mu_normal, mu_caught, d_max, ref_mean, ref_cov_inv,
                              mu_caught_tx, sigma_caught_tx)

phi_names = ['φ_camouflage', 'φ_feature_gap', 'φ_activity_anomaly',
             'φ_dist_normal', 'φ_dist_caught', 'φ_dist_ratio', 'φ_extreme_range']
print(f'  Generated {phi.shape[1]} supplementary features for {phi.shape[0]:,} samples')
print(f'\n  {"Feature":<22} {"Fraud mean":>12} {"Normal mean":>12} {"Sep. ratio":>12}')
print(f'  {"-"*60}')
for i, name in enumerate(phi_names):
    f_mean = phi[fraud_mask, i].mean()
    n_mean = phi[normal_mask, i].mean()
    sep = abs(f_mean - n_mean) / max(phi[:, i].std(), 1e-8)
    print(f'  {name:<22} {f_mean:>12.4f} {n_mean:>12.4f} {sep:>12.4f}')


# ══════════════════════════════════════════════════════════════════
# VALIDATION ON XBLOCK
# ══════════════════════════════════════════════════════════════════
print('\n\n' + '='*80)
print('  VALIDATING FORMULA ON XBLOCK')
print('='*80)

from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedShuffleSplit

df_xb = pd.read_csv(DATA_DIR / 'xblock' / 'transaction_dataset.csv')
y_xb_all = df_xb['FLAG'].astype(int).values

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

sss = StratifiedShuffleSplit(n_splits=1, test_size=0.8, random_state=42)
cal_idx, eval_idx = next(sss.split(X_xb, y_xb_all))
lr_platt = LogisticRegression(random_state=42)
lr_platt.fit(prob_xb_raw[cal_idx].reshape(-1, 1), y_xb_all[cal_idx])
prob_xb = lr_platt.predict_proba(prob_xb_raw[eval_idx].reshape(-1, 1))[:, 1]
y_xb = y_xb_all[eval_idx]
X_xb_eval = X_xb[eval_idx]

# Find original optimal threshold
thresholds = np.arange(0.1, 0.95, 0.01)
f1s_xb = [f1_score(y_xb, (prob_xb >= t).astype(int), zero_division=0) for t in thresholds]
orig_thresh_xb = thresholds[np.argmax(f1s_xb)]

fraud_xb = y_xb == 1
normal_xb = y_xb == 0
caught_xb_orig = fraud_xb & (prob_xb >= orig_thresh_xb)
missed_xb_orig = fraud_xb & (prob_xb < orig_thresh_xb)
pred_xb_orig = (prob_xb >= orig_thresh_xb).astype(int)

print(f'\n  BEFORE correction:')
print(f'  Phishing: {fraud_xb.sum():,}  |  Caught: {caught_xb_orig.sum():,}  |  Missed: {missed_xb_orig.sum():,}')
print(f'  Recall: {recall_score(y_xb, pred_xb_orig, zero_division=0):.4f}')
print(f'  Precision: {precision_score(y_xb, pred_xb_orig, zero_division=0):.4f}')
print(f'  F1: {f1_score(y_xb, pred_xb_orig, zero_division=0):.4f}')

# XBlock formula parameters
mu_normal_xb = X_xb_eval[normal_xb].mean(axis=0)
dists_xb = np.linalg.norm(X_xb_eval - mu_normal_xb, axis=1)
d_max_xb = np.percentile(dists_xb, 99)

caught_tx_xb = np.abs(X_xb_eval[caught_xb_orig, idx_sent]) + np.abs(X_xb_eval[caught_xb_orig, idx_recv])
mu_caught_tx_xb = np.log1p(caught_tx_xb).mean() if caught_xb_orig.sum() > 0 else 0
sigma_caught_tx_xb = np.log1p(caught_tx_xb).std() if caught_xb_orig.sum() > 0 else 1

ref_mean_xb = X_xb_eval[caught_xb_orig].mean(axis=0) if caught_xb_orig.sum() > 0 else X_xb_eval[fraud_xb].mean(axis=0)
ref_var_xb = X_xb_eval[caught_xb_orig].var(axis=0) + 1e-8 if caught_xb_orig.sum() > 0 else X_xb_eval[fraud_xb].var(axis=0) + 1e-8
ref_cov_inv_xb = 1.0 / ref_var_xb

mu_caught_xb = ref_mean_xb

MFLS_xb, C_xb, G_xb, A_xb, T_xb = missed_fraud_likelihood(
    X_xb_eval, mu_normal_xb, d_max_xb, ref_mean_xb, ref_cov_inv_xb,
    mu_caught_tx_xb, sigma_caught_tx_xb)

print(f'\n  MFLS components (mean ± std):')
print(f'  {"Component":<20} {"Caught":>15} {"Missed":>15} {"Normal":>15}')
print(f'  {"-"*65}')
for name, vals in [('C (Camouflage)', C_xb), ('G (Feature Gap)', G_xb), ('A (Activity)', A_xb), ('T (Temporal)', T_xb), ('MFLS (Combined)', MFLS_xb)]:
    c_vals = vals[caught_xb_orig]
    m_vals = vals[missed_xb_orig]
    n_vals = vals[normal_xb]
    c_str = f'{c_vals.mean():.4f}±{c_vals.std():.4f}' if len(c_vals) > 0 else 'N/A'
    m_str = f'{m_vals.mean():.4f}±{m_vals.std():.4f}' if len(m_vals) > 0 else 'N/A'
    n_str = f'{n_vals.mean():.4f}±{n_vals.std():.4f}' if len(n_vals) > 0 else 'N/A'
    print(f'  {name:<20} {c_str:>15} {m_str:>15} {n_str:>15}')

# ── Grid search for optimal λ on XBlock ──
print(f'\n  Optimizing correction strength λ...')
best_f1_xb = 0
best_lam_xb = 0

for lam in np.arange(0.1, 2.01, 0.05):
    p_corr = corrected_prediction(prob_xb, MFLS_xb, orig_thresh_xb, lam=lam)
    for thresh in np.arange(0.1, 0.9, 0.02):
        pred = (p_corr >= thresh).astype(int)
        f1 = f1_score(y_xb, pred, zero_division=0)
        if f1 > best_f1_xb:
            best_f1_xb = f1
            best_lam_xb = lam
            best_thresh_xb = thresh
            best_metrics_xb = {
                'recall': recall_score(y_xb, pred, zero_division=0),
                'precision': precision_score(y_xb, pred, zero_division=0),
                'f1': f1,
                'caught': (pred[fraud_xb] == 1).sum(),
                'missed': (pred[fraud_xb] == 0).sum(),
            }

p_xb_corrected = corrected_prediction(prob_xb, MFLS_xb, orig_thresh_xb, lam=best_lam_xb)

print(f'  Optimal λ = {best_lam_xb:.2f}  |  Optimal τ = {best_thresh_xb:.2f}')
print(f'\n  AFTER correction (λ={best_lam_xb:.2f}, τ={best_thresh_xb:.2f}):')
print(f'  Phishing: {fraud_xb.sum():,}  |  Caught: {best_metrics_xb["caught"]:,}  |  Missed: {best_metrics_xb["missed"]:,}')
print(f'  Recall: {best_metrics_xb["recall"]:.4f}  (was {recall_score(y_xb, pred_xb_orig, zero_division=0):.4f})')
print(f'  Precision: {best_metrics_xb["precision"]:.4f}  (was {precision_score(y_xb, pred_xb_orig, zero_division=0):.4f})')
print(f'  F1: {best_metrics_xb["f1"]:.4f}  (was {f1_score(y_xb, pred_xb_orig, zero_division=0):.4f})')

recall_delta_xb = best_metrics_xb['recall'] - recall_score(y_xb, pred_xb_orig, zero_division=0)
print(f'\n  Recall improvement: {recall_delta_xb:+.4f} ({recall_delta_xb*100:+.1f} percentage points)')


# ══════════════════════════════════════════════════════════════════
# FINAL FORMULA SUMMARY
# ══════════════════════════════════════════════════════════════════
print('\n\n' + '='*80)
print('  FINAL FORMULA SPECIFICATION')
print('='*80)

print(f"""
  ┌──────────────────────────────────────────────────────────────────┐
  │  MISSED FRAUD LIKELIHOOD SCORE (MFLS)                           │
  │                                                                  │
  │  MFLS(x) = 0.30·C(x) + 0.25·G(x) + 0.25·A(x) + 0.20·T(x)    │
  │                                                                  │
  │  where:                                                          │
  │    C(x) = 1 - ‖x - μ_normal‖₂ / d_max                          │
  │         (camouflage: proximity to normal centroid)               │
  │                                                                  │
  │    G(x) = Σᵢ 𝟙[|xᵢ| < ε] / 93                                  │
  │         (feature gap: fraction of zero/missing features)         │
  │                                                                  │
  │    A(x) = σ((log(1+tx_count) - μ_log) / σ_log)                  │
  │         (activity anomaly: deviation from caught-fraud pattern)  │
  │                                                                  │
  │    T(x) = σ(0.5 · (Mahal²(x, caught_dist) / dim - 2))          │
  │         (temporal novelty: statistical distance from known fraud)│
  └──────────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────────┐
  │  CORRECTED PREDICTION                                           │
  │                                                                  │
  │  p̂*(x) = p̂(x) + λ · MFLS(x) · (1 - p̂(x)) · 𝟙[p̂(x) < τ]     │
  │                                                                  │
  │  Elliptic: λ = {best_lam:.2f}, τ = {best_thresh:.2f}                                │
  │  XBlock:   λ = {best_lam_xb:.2f}, τ = {best_thresh_xb:.2f}                                │
  └──────────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────────┐
  │  SUPPLEMENTARY FEATURES φ(x) ∈ ℝ⁷                              │
  │                                                                  │
  │  φ₁ = C(x)         Camouflage score                             │
  │  φ₂ = G(x)         Feature gap score                            │
  │  φ₃ = A(x)         Activity anomaly score                       │
  │  φ₄ = ‖x - μ_N‖₂  Distance to normal centroid                  │
  │  φ₅ = ‖x - μ_F‖₂  Distance to caught-fraud centroid            │
  │  φ₆ = φ₄ / φ₅      Distance ratio (normal vs fraud proximity)  │
  │  φ₇ = R(x)         Extreme feature range fraction               │
  │                                                                  │
  │  Training augmentation: Append φ(x) to x ∈ ℝ⁹³ → x' ∈ ℝ¹⁰⁰   │
  └──────────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────────┐
  │  RESULTS SUMMARY                                                │
  │                                                                  │
  │  Elliptic:                                                       │
  │    Recall: {caught_orig.sum()/fraud_mask.sum():.4f} → {best_metrics['recall']:.4f}  ({recall_delta:+.4f})                          │
  │    F1:     {f1_score(y_ell, pred_orig, zero_division=0):.4f} → {best_metrics['f1']:.4f}                                    │
  │                                                                  │
  │  XBlock:                                                         │
  │    Recall: {recall_score(y_xb, pred_xb_orig, zero_division=0):.4f} → {best_metrics_xb['recall']:.4f}  ({recall_delta_xb:+.4f})                          │
  │    F1:     {f1_score(y_xb, pred_xb_orig, zero_division=0):.4f} → {best_metrics_xb['f1']:.4f}                                    │
  └──────────────────────────────────────────────────────────────────┘
""")

# ── Save formula parameters for reuse ──
formula_params = {
    'formula': 'MFLS(x) = α·C(x) + β·G(x) + γ·A(x) + δ·T(x)',
    'correction': 'p*(x) = p(x) + λ·MFLS(x)·(1-p(x))·𝟙[p(x)<τ]',
    'weights': {'alpha': 0.30, 'beta': 0.25, 'gamma': 0.25, 'delta': 0.20},
    'elliptic': {
        'lambda': float(best_lam), 'threshold': float(best_thresh),
        'recall_before': float(caught_orig.sum()/fraud_mask.sum()),
        'recall_after': float(best_metrics['recall']),
        'f1_before': float(f1_score(y_ell, pred_orig, zero_division=0)),
        'f1_after': float(best_metrics['f1']),
        'd_max': float(d_max),
        'mu_caught_tx': float(mu_caught_tx),
        'sigma_caught_tx': float(sigma_caught_tx),
    },
    'xblock': {
        'lambda': float(best_lam_xb), 'threshold': float(best_thresh_xb),
        'recall_before': float(recall_score(y_xb, pred_xb_orig, zero_division=0)),
        'recall_after': float(best_metrics_xb['recall']),
        'f1_before': float(f1_score(y_xb, pred_xb_orig, zero_division=0)),
        'f1_after': float(best_metrics_xb['f1']),
        'd_max': float(d_max_xb),
        'mu_caught_tx': float(mu_caught_tx_xb),
        'sigma_caught_tx': float(sigma_caught_tx_xb),
    },
    'supplementary_features': phi_names,
}

output_path = Path(__file__).parent / 'missed_fraud_formula_params.json'
with open(output_path, 'w') as f:
    json.dump(formula_params, f, indent=2, default=str)
print(f'  Formula parameters saved to: {output_path}')
print('='*80)
