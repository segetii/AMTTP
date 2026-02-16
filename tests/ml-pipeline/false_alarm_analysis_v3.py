"""
False Alarm Pattern Analysis for BSDT — V3
=============================================
Uses the EXACT same data loading as cross_domain_validation.py.
Analyzes component-level false alarm patterns and tests improvements.
"""

import numpy as np
import pandas as pd
import scipy.io as sio
from pathlib import Path
import warnings, json
warnings.filterwarnings('ignore')

ARTIFACTS = Path(r'C:\Users\Administrator\Downloads\amttp_student_artifacts\amttp_models_20260213_213346')
DATA_DIR = Path(r'c:\amttp\data\external_validation')

import joblib, xgboost as xgb
from sklearn.metrics import (
    roc_auc_score, f1_score, precision_score, recall_score,
    mutual_info_score
)
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedShuffleSplit

preprocessors = joblib.load(ARTIFACTS / 'preprocessors.joblib')
scaler = preprocessors['scaler']
FEATURES_93 = list(preprocessors['feature_names'])
xgb_model = xgb.Booster()
xgb_model.load_model(str(ARTIFACTS / 'xgboost_fraud.ubj'))

IDX_SENT = 7; IDX_RECV = 60

# ── BSDT functions ──
def camouflage_score(X, mu, dmax):
    return 1.0 - np.clip(np.linalg.norm(X - mu, axis=1) / dmax, 0, 1)

def feature_gap_score(X):
    return (np.abs(X) < 1e-8).sum(axis=1).astype(np.float64) / X.shape[1]

def activity_anomaly_score(X, mu_c, sig_c):
    tx = np.abs(X[:, IDX_SENT]) + np.abs(X[:, IDX_RECV]) + 1e-8
    z = (np.log1p(tx) - mu_c) / max(sig_c, 1e-8)
    return 1.0 / (1.0 + np.exp(-z))

def temporal_novelty_score(X, rm, rv):
    d = X - rm
    m = np.sum(d * d / rv, axis=1) / X.shape[1]
    return 1.0 / (1.0 + np.exp(-0.5 * (m - 2.0)))

def ref_stats(X, y):
    n = X[y == 0]; f = X[y == 1]
    mu = n.mean(0); d = np.percentile(np.linalg.norm(X - mu, axis=1), 99)
    rm = f.mean(0); rv = f.var(0) + 1e-8
    tx = np.abs(f[:, IDX_SENT]) + np.abs(f[:, IDX_RECV]) + 1e-8
    return mu, d, rm, rv, np.log1p(tx).mean(), max(np.log1p(tx).std(), 1e-8)

def get_components(X, *s):
    return np.column_stack([camouflage_score(X, s[0], s[1]),
                            feature_gap_score(X),
                            activity_anomaly_score(X, s[4], s[5]),
                            temporal_novelty_score(X, s[2], s[3])])

def mi_weights(comp, y, nb=20):
    mi = np.zeros(4)
    for i in range(4):
        b = np.digitize(comp[:, i], np.linspace(comp[:, i].min(), comp[:, i].max()+1e-8, nb))
        mi[i] = mutual_info_score(y, b)
    t = mi.sum()
    return (mi / t if t > 1e-10 else np.ones(4)/4), mi

def correct(prob, comp, w, lam, th):
    mfls = comp @ np.array(w, dtype=np.float64)
    below = (prob < th).astype(np.float64)
    return np.clip(prob + lam * mfls * (1.0 - prob) * below, 0.0, 1.0)

def build_X_generic(features_df):
    X = np.zeros((len(features_df), 93), dtype=np.float32)
    for i, f in enumerate(FEATURES_93):
        if f in features_df.columns:
            X[:, i] = features_df[f].values.astype(np.float32)
    return X

def preprocess(X):
    X2 = np.log1p(np.abs(X)) * np.sign(X)
    X2 = scaler.transform(X2)
    X2 = np.clip(X2, -10, 10)
    return np.nan_to_num(X2, nan=0.0, posinf=10.0, neginf=-10.0)

def predict(X):
    return xgb_model.predict(xgb.DMatrix(preprocess(X), feature_names=FEATURES_93))


# ══════════════════════════════════════════════════════
# Load datasets (SAME as cross_domain_validation.py)
# ══════════════════════════════════════════════════════

def load_creditcard():
    df = pd.read_csv(DATA_DIR / 'creditcard' / 'creditcard.csv')
    y = df['Class'].astype(int).values
    mapped = pd.DataFrame()
    feature_mapping = {
        'V1': 'sender_total_sent', 'V2': 'sender_avg_sent', 'V3': 'sender_sent_count',
        'V4': 'value_eth', 'V5': 'sender_total_transactions', 'V6': 'sender_balance',
        'V7': 'receiver_total_received', 'V8': 'sender_in_out_ratio',
        'V9': 'receiver_avg_received', 'V10': 'sender_unique_counterparties',
        'V11': 'sender_degree', 'V12': 'sender_neighbors',
        'V13': 'sender_in_degree', 'V14': 'sender_out_degree',
        'V15': 'sender_unique_receivers', 'V16': 'receiver_unique_senders',
        'V17': 'sender_max_sent', 'V18': 'sender_min_sent',
        'V19': 'receiver_max_received', 'V20': 'receiver_min_received',
        'V21': 'receiver_received_count', 'V22': 'sender_avg_time_between_txns',
        'V23': 'sender_stddev_sent', 'V24': 'receiver_stddev_received',
        'V25': 'sender_cluster_coeff', 'V26': 'sender_pagerank',
        'V27': 'sender_betweenness', 'V28': 'sender_closeness',
    }
    for src, dst in feature_mapping.items():
        if src in df.columns:
            mapped[dst] = df[src].values.astype(np.float32)
    if 'Amount' in df.columns:
        mapped['value_eth'] = df['Amount'].values.astype(np.float32)
    return build_X_generic(mapped), y

def load_odds(name):
    d = sio.loadmat(str(DATA_DIR / 'odds' / f'{name}.mat'))
    X_raw, y_raw = d['X'], d['y'].ravel()
    mapped = pd.DataFrame()
    targets = [
        'sender_total_sent', 'sender_avg_sent', 'sender_sent_count',
        'value_eth', 'sender_total_transactions', 'sender_balance',
        'receiver_total_received', 'sender_in_out_ratio',
        'receiver_avg_received', 'sender_unique_counterparties',
        'sender_degree', 'sender_neighbors', 'sender_in_degree',
        'sender_out_degree', 'sender_unique_receivers', 'receiver_unique_senders',
        'sender_max_sent', 'sender_min_sent', 'receiver_max_received',
        'receiver_min_received', 'receiver_received_count',
        'sender_avg_time_between_txns', 'sender_stddev_sent',
        'receiver_stddev_received', 'sender_cluster_coeff',
        'sender_pagerank', 'sender_betweenness', 'sender_closeness',
    ]
    for i in range(min(X_raw.shape[1], len(targets))):
        mapped[targets[i]] = X_raw[:, i].astype(np.float32)
    return build_X_generic(mapped), y_raw.astype(np.int32)

def load_elliptic():
    ell_dir = DATA_DIR / 'elliptic'
    features = pd.read_csv(ell_dir / 'elliptic_txs_features.csv', header=None)
    classes = pd.read_csv(ell_dir / 'elliptic_txs_classes.csv')
    classes.columns = ['txId', 'class']
    feat_cols = ['txId'] + [f'feat_{i}' for i in range(1, features.shape[1])]
    features.columns = feat_cols
    merged = features.merge(classes, on='txId')
    labelled = merged[merged['class'].isin(['1', '2'])].copy()
    labelled['label'] = (labelled['class'] == '2').astype(np.int32)
    X_raw = labelled[[f'feat_{i}' for i in range(1, 167)]].values.astype(np.float32)
    y = labelled['label'].values
    X = np.zeros((len(X_raw), 93), dtype=np.float32)
    for i in range(min(93, X_raw.shape[1])):
        X[:, i] = X_raw[:, i]
    return X, y


# ══════════════════════════════════════════════════════
# MAIN ANALYSIS
# ══════════════════════════════════════════════════════

print("Loading datasets...")
datasets = {}
datasets['Credit Card'] = load_creditcard()
print(f"  Credit Card: {datasets['Credit Card'][0].shape}")
datasets['Shuttle'] = load_odds('shuttle')
print(f"  Shuttle: {datasets['Shuttle'][0].shape}")
datasets['Mammography'] = load_odds('mammography')
print(f"  Mammography: {datasets['Mammography'][0].shape}")
datasets['Pendigits'] = load_odds('pendigits')
print(f"  Pendigits: {datasets['Pendigits'][0].shape}")
try:
    datasets['Elliptic'] = load_elliptic()
    print(f"  Elliptic: {datasets['Elliptic'][0].shape}")
except Exception as e:
    print(f"  Elliptic: skipped ({e})")

comp_names = ['C (Camouflage)', 'G (Feature Gap)', 'A (Activity)', 'T (Temporal)']

print("\n" + "="*80)
print("  FALSE ALARM PATTERN ANALYSIS")
print("="*80)

results_summary = {}

for name, (X, y) in datasets.items():
    print(f"\n{'─'*70}")
    print(f"  {name} — n={len(y)}, fraud={y.sum()}, rate={y.mean():.4f}")
    print(f"{'─'*70}")
    
    # Get model predictions + calibrate
    p_raw = predict(X)
    print(f"  Raw model p range: [{p_raw.min():.6f}, {p_raw.max():.6f}], std={p_raw.std():.6f}")
    
    # Calibrate
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.8, random_state=42)
    cal_i, eval_i = next(sss.split(X, y))
    lr = LogisticRegression(random_state=42, max_iter=1000)
    lr.fit(p_raw[cal_i].reshape(-1,1), y[cal_i])
    p = lr.predict_proba(p_raw[eval_i].reshape(-1,1))[:,1]
    y_e = y[eval_i]
    X_e = X[eval_i]
    
    print(f"  Calibrated p range: [{p.min():.6f}, {p.max():.6f}], std={p.std():.6f}")
    print(f"  Unique calibrated values: {len(np.unique(np.round(p, 6)))}")
    
    # Find best baseline threshold
    ths = np.arange(0.05, 0.95, 0.01)
    f1s = [f1_score(y_e, (p >= t).astype(np.int32), zero_division=0) for t in ths]
    th_best = float(ths[np.argmax(f1s)])
    pred_base = (p >= th_best).astype(np.int32)
    base_rec = recall_score(y_e, pred_base, zero_division=0)
    base_prec = precision_score(y_e, pred_base, zero_division=0) 
    base_f1 = f1_score(y_e, pred_base, zero_division=0)
    print(f"  Baseline: th={th_best:.2f}, recall={base_rec:.3f}, prec={base_prec:.3f}, f1={base_f1:.3f}")
    
    # Compute BSDT components
    s = ref_stats(X_e, y_e)
    comp = get_components(X_e, *s)
    
    # Check for NaN
    nan_mask = np.isnan(comp).any(axis=1)
    if nan_mask.sum() > 0:
        print(f"  ⚠ {nan_mask.sum()} NaN rows in components — replacing with 0")
        comp = np.nan_to_num(comp, nan=0.0)
    
    # MI weights
    w, raw_mi = mi_weights(comp, y_e)
    mfls = comp @ w
    
    print(f"  MI weights: C={w[0]:.3f}, G={w[1]:.3f}, A={w[2]:.3f}, T={w[3]:.3f}")
    print(f"  MFLS range: [{mfls.min():.4f}, {mfls.max():.4f}], std={mfls.std():.4f}")
    
    fraud_mask = y_e == 1
    legit_mask = y_e == 0
    
    # ── Component distributions ──
    print(f"\n  ▸ Component distributions:")
    print(f"    {'Comp':<20} {'Fraud':>8} {'Legit':>8} {'Gap':>8} {'Var(F)':>8} {'Var(L)':>8}")
    for i, cn in enumerate(comp_names):
        fm, lm = comp[fraud_mask, i].mean(), comp[legit_mask, i].mean()
        fv, lv = comp[fraud_mask, i].var(), comp[legit_mask, i].var()
        print(f"    {cn:<20} {fm:8.4f} {lm:8.4f} {fm-lm:+8.4f} {fv:8.4f} {lv:8.4f}")
    
    print(f"\n  ▸ MFLS distribution:")
    print(f"    Fraud: mean={mfls[fraud_mask].mean():.4f}, P10={np.percentile(mfls[fraud_mask],10):.4f}, P50={np.percentile(mfls[fraud_mask],50):.4f}, P90={np.percentile(mfls[fraud_mask],90):.4f}")
    print(f"    Legit: mean={mfls[legit_mask].mean():.4f}, P10={np.percentile(mfls[legit_mask],10):.4f}, P50={np.percentile(mfls[legit_mask],50):.4f}, P90={np.percentile(mfls[legit_mask],90):.4f}")
    
    # MFLS AUC (can it separate fraud from legit?)
    try:
        mfls_auc = roc_auc_score(y_e, mfls)
    except:
        mfls_auc = 0.5
    print(f"    MFLS AUC (fraud vs legit): {mfls_auc:.4f}")
    
    # ── Apply correction and analyze false alarms ──
    # Grid search
    best = {'f1': 0, 'lam': 1.0, 'th': 0.1, 'pt': 0.15}
    for lam in np.arange(0.1, 2.5, 0.1):
        for th in np.arange(0.1, 0.95, 0.1):
            pc = correct(p, comp, w, float(lam), float(th))
            for pt in np.arange(0.1, 0.9, 0.05):
                pr = (pc >= pt).astype(np.int32)
                f1 = f1_score(y_e, pr, zero_division=0)
                if f1 > best['f1']:
                    best = {'f1': f1, 'lam': float(lam), 'th': float(th), 'pt': float(pt)}
    
    pc = correct(p, comp, w, best['lam'], best['th'])
    pred = (pc >= best['pt']).astype(np.int32)
    
    TP = (pred == 1) & (y_e == 1)
    FP = (pred == 1) & (y_e == 0) 
    TN = (pred == 0) & (y_e == 0)
    FN = (pred == 0) & (y_e == 1)
    n_tp, n_fp, n_tn, n_fn = TP.sum(), FP.sum(), TN.sum(), FN.sum()
    
    corr_rec = n_tp / max(n_tp + n_fn, 1)
    corr_prec = n_tp / max(n_tp + n_fp, 1)
    fa_rate = n_fp / max(n_tp + n_fp, 1)
    
    print(f"\n  ▸ After correction (λ={best['lam']:.1f}, τ={best['th']:.1f}, pt={best['pt']:.2f}):")
    print(f"    TP={n_tp}, FP={n_fp}, TN={n_tn}, FN={n_fn}")
    print(f"    Recall={corr_rec:.3f}, Precision={corr_prec:.3f}, F1={best['f1']:.3f}")
    print(f"    False Alarm Rate: {fa_rate:.1%}")
    
    if n_fp > 0 and n_tp > 0:
        # ── FALSE ALARM PROFILE ──
        print(f"\n  ▸ FALSE ALARM vs TRUE POSITIVE component profile:")
        print(f"    {'Component':<20} {'TP mean':>8} {'FP mean':>8} {'Gap (TP-FP)':>12}")
        separable_comps = []
        for i, cn in enumerate(comp_names):
            tp_v = comp[TP, i].mean()
            fp_v = comp[FP, i].mean()
            gap = tp_v - fp_v
            marker = ' ★' if abs(gap) > 0.05 else ''
            print(f"    {cn:<20} {tp_v:8.4f} {fp_v:8.4f} {gap:+12.4f}{marker}")
            if abs(gap) > 0.05:
                separable_comps.append((i, cn, gap))
        
        print(f"\n  ▸ MFLS of false alarms vs true positives:")
        print(f"    TP MFLS: mean={mfls[TP].mean():.4f}, median={np.median(mfls[TP]):.4f}")
        print(f"    FP MFLS: mean={mfls[FP].mean():.4f}, median={np.median(mfls[FP]):.4f}")
        print(f"    Gap: {mfls[TP].mean() - mfls[FP].mean():+.4f}")
        
        # Corrected probability margins  
        fp_margin = pc[FP] - best['pt']
        print(f"\n  ▸ FP margin over threshold (how 'barely' they got flagged):")
        print(f"    < 0.05: {(fp_margin < 0.05).mean():.1%}")
        print(f"    < 0.10: {(fp_margin < 0.10).mean():.1%}")
        print(f"    < 0.20: {(fp_margin < 0.20).mean():.1%}")
        print(f"    ≥ 0.20: {(fp_margin >= 0.20).mean():.1%}")
        
        # Base probability of FP
        print(f"\n  ▸ Base model confidence for false alarms (how confident model was they're legit):")
        fp_base = p[FP]
        print(f"    FP base p(fraud): mean={fp_base.mean():.4f}, max={fp_base.max():.4f}")
        
        # ── COMPONENT AGREEMENT ──
        high_comp = (comp > 0.5).astype(int).sum(axis=1)
        print(f"\n  ▸ Component agreement (# of 4 components > 0.5):")
        print(f"    {'# high':<8}  {'TP':>6}  {'FP':>6}  {'Precision':>10}")
        for g in range(5):
            tp_g = ((high_comp == g) & TP).sum()
            fp_g = ((high_comp == g) & FP).sum()
            prec_g = tp_g / max(tp_g + fp_g, 1)
            print(f"    {g:<8}  {tp_g:>6}  {fp_g:>6}  {prec_g:>10.3f}")
    
    # ══════════════════════════════════════════════════
    # TEST FORMULA IMPROVEMENTS
    # ══════════════════════════════════════════════════
    
    print(f"\n  ═══ TESTING FORMULA IMPROVEMENTS ═══")
    
    # Current baseline
    print(f"\n  [Current formula] Recall={corr_rec:.3f}, Prec={corr_prec:.3f}, F1={best['f1']:.3f}, FA={fa_rate:.1%}")
    
    # ── IMPROVEMENT A: Confidence-scaled correction ──
    # Higher MFLS required when model is very confident the txn is legit
    # p*(x) = p(x) + λ·MFLS(x)·(1-p(x))^α·𝟙[p<τ]  where α > 1 penalizes low-p more
    print(f"\n  [A] Confidence-penalty correction: p* = p + λ·MFLS·(1-p)^α")
    for alpha in [1.5, 2.0, 3.0]:
        best_a = {'f1': 0, 'lam': 1.0, 'th': 0.1, 'pt': 0.15}
        for lam in np.arange(0.1, 3.0, 0.2):
            for th in np.arange(0.1, 0.95, 0.1):
                mfls_w = comp @ w
                below = (p < th).astype(np.float64)
                pc_a = np.clip(p + lam * mfls_w * np.power(1.0 - p, alpha) * below, 0.0, 1.0)
                for pt in np.arange(0.1, 0.9, 0.05):
                    pr = (pc_a >= pt).astype(np.int32)
                    f1 = f1_score(y_e, pr, zero_division=0)
                    if f1 > best_a['f1']:
                        rec = recall_score(y_e, pr, zero_division=0)
                        prec = precision_score(y_e, pr, zero_division=0)
                        fa = (((pr == 1) & (y_e == 0)).sum()) / max(pr.sum(), 1)
                        best_a = {'f1': f1, 'rec': rec, 'prec': prec, 'fa': fa,
                                  'lam': lam, 'th': th, 'pt': pt}
        print(f"    α={alpha}: Rec={best_a.get('rec',0):.3f}, Prec={best_a.get('prec',0):.3f}, F1={best_a['f1']:.3f}, FA={best_a.get('fa',0):.1%}")
    
    # ── IMPROVEMENT B: Component agreement gate ──
    # Only correct if ≥N components are elevated (> 0.5)
    print(f"\n  [B] Component agreement gate: only correct if ≥N components > 0.5")
    high_comp = (comp > 0.5).astype(int).sum(axis=1)
    for min_agree in [1, 2]:
        gate = (high_comp >= min_agree).astype(np.float64)
        best_b = {'f1': 0}
        for lam in np.arange(0.1, 3.0, 0.2):
            for th in np.arange(0.1, 0.95, 0.1):
                mfls_w = comp @ w
                below = (p < th).astype(np.float64)
                pc_b = np.clip(p + lam * mfls_w * (1.0 - p) * below * gate, 0.0, 1.0)
                for pt in np.arange(0.1, 0.9, 0.05):
                    pr = (pc_b >= pt).astype(np.int32)
                    f1 = f1_score(y_e, pr, zero_division=0)
                    if f1 > best_b['f1']:
                        rec = recall_score(y_e, pr, zero_division=0)
                        prec = precision_score(y_e, pr, zero_division=0)
                        fa = (((pr == 1) & (y_e == 0)).sum()) / max(pr.sum(), 1)
                        best_b = {'f1': f1, 'rec': rec, 'prec': prec, 'fa': fa}
        print(f"    ≥{min_agree} agree: Rec={best_b.get('rec',0):.3f}, Prec={best_b.get('prec',0):.3f}, F1={best_b['f1']:.3f}, FA={best_b.get('fa',0):.1%}")
    
    # ── IMPROVEMENT C: MFLS percentile threshold ──
    # Instead of a fixed MFLS contribution, only correct if MFLS is in top K%
    print(f"\n  [C] MFLS percentile gate: only correct if MFLS > P-th percentile")
    for pctile in [50, 70, 90]:
        mfls_th = np.percentile(mfls, pctile)
        gate_c = (mfls >= mfls_th).astype(np.float64)
        best_c = {'f1': 0}
        for lam in np.arange(0.1, 3.0, 0.2):
            for th in np.arange(0.1, 0.95, 0.1):
                below = (p < th).astype(np.float64)
                pc_c = np.clip(p + lam * mfls * (1.0 - p) * below * gate_c, 0.0, 1.0)
                for pt in np.arange(0.1, 0.9, 0.05):
                    pr = (pc_c >= pt).astype(np.int32)
                    f1 = f1_score(y_e, pr, zero_division=0)
                    if f1 > best_c['f1']:
                        rec = recall_score(y_e, pr, zero_division=0)
                        prec = precision_score(y_e, pr, zero_division=0)
                        fa = (((pr == 1) & (y_e == 0)).sum()) / max(pr.sum(), 1)
                        best_c = {'f1': f1, 'rec': rec, 'prec': prec, 'fa': fa}
        print(f"    P{pctile}: Rec={best_c.get('rec',0):.3f}, Prec={best_c.get('prec',0):.3f}, F1={best_c['f1']:.3f}, FA={best_c.get('fa',0):.1%}")
    
    # ── IMPROVEMENT D: Combined — confidence penalty + agreement gate ──
    print(f"\n  [D] Combined: confidence penalty (α=2) + agreement gate (≥2)")
    gate = (high_comp >= 2).astype(np.float64)
    best_d = {'f1': 0}
    for lam in np.arange(0.1, 3.0, 0.2):
        for th in np.arange(0.1, 0.95, 0.1):
            mfls_w = comp @ w
            below = (p < th).astype(np.float64)
            pc_d = np.clip(p + lam * mfls_w * np.power(1.0 - p, 2.0) * below * gate, 0.0, 1.0)
            for pt in np.arange(0.1, 0.9, 0.05):
                pr = (pc_d >= pt).astype(np.int32)
                f1 = f1_score(y_e, pr, zero_division=0)
                if f1 > best_d['f1']:
                    rec = recall_score(y_e, pr, zero_division=0)
                    prec = precision_score(y_e, pr, zero_division=0)
                    fa = (((pr == 1) & (y_e == 0)).sum()) / max(pr.sum(), 1)
                    n_tp_d = ((pr == 1) & (y_e == 1)).sum()
                    n_fp_d = ((pr == 1) & (y_e == 0)).sum()
                    best_d = {'f1': f1, 'rec': rec, 'prec': prec, 'fa': fa,
                              'tp': n_tp_d, 'fp': n_fp_d}
    print(f"    Rec={best_d.get('rec',0):.3f}, Prec={best_d.get('prec',0):.3f}, F1={best_d['f1']:.3f}, FA={best_d.get('fa',0):.1%}")
    
    results_summary[name] = {
        'current': {'recall': corr_rec, 'precision': corr_prec, 'f1': best['f1'], 'fa': fa_rate,
                    'tp': int(n_tp), 'fp': int(n_fp)},
    }

print("\n" + "="*80)
print("  ANALYSIS COMPLETE")
print("="*80)
