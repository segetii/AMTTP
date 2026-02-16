"""
False Alarm Pattern Analysis — Final (fast)
============================================
Focused analysis: what PATTERNS cause false alarms and what fixes them?
Uses coarser grid for speed.
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
    m = np.sum(d*d / rv, axis=1) / X.shape[1]
    return 1.0 / (1.0 + np.exp(-0.5*(m-2.0)))
def ref_stats(X, y):
    n = X[y==0]; f = X[y==1]
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

# ── Data loaders ──
def load_creditcard():
    df = pd.read_csv(DATA_DIR/'creditcard'/'creditcard.csv')
    y = df['Class'].astype(int).values
    mapped = pd.DataFrame()
    for i, col in enumerate([c for c in df.columns if c.startswith('V')]):
        targets = ['sender_total_sent','sender_avg_sent','sender_sent_count','value_eth',
                   'sender_total_transactions','sender_balance','receiver_total_received',
                   'sender_in_out_ratio','receiver_avg_received','sender_unique_counterparties',
                   'sender_degree','sender_neighbors','sender_in_degree','sender_out_degree',
                   'sender_unique_receivers','receiver_unique_senders','sender_max_sent',
                   'sender_min_sent','receiver_max_received','receiver_min_received',
                   'receiver_received_count','sender_avg_time_between_txns','sender_stddev_sent',
                   'receiver_stddev_received','sender_cluster_coeff','sender_pagerank',
                   'sender_betweenness','sender_closeness']
        if i < len(targets):
            mapped[targets[i]] = df[col].values.astype(np.float32)
    if 'Amount' in df.columns:
        mapped['value_eth'] = df['Amount'].values.astype(np.float32)
    return build_X_generic(mapped), y
def load_odds(name):
    d = sio.loadmat(str(DATA_DIR/'odds'/f'{name}.mat'))
    X_raw, y_raw = d['X'], d['y'].ravel()
    mapped = pd.DataFrame()
    targets = ['sender_total_sent','sender_avg_sent','sender_sent_count','value_eth',
               'sender_total_transactions','sender_balance','receiver_total_received',
               'sender_in_out_ratio','receiver_avg_received','sender_unique_counterparties',
               'sender_degree','sender_neighbors','sender_in_degree','sender_out_degree',
               'sender_unique_receivers','receiver_unique_senders','sender_max_sent',
               'sender_min_sent','receiver_max_received','receiver_min_received']
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
    labelled = merged[merged['class'].isin(['1','2'])].copy()
    labelled['label'] = (labelled['class']=='2').astype(np.int32)
    X_raw = labelled[[f'feat_{i}' for i in range(1, 167)]].values.astype(np.float32)
    y = labelled['label'].values
    X = np.zeros((len(X_raw), 93), dtype=np.float32)
    for i in range(min(93, X_raw.shape[1])):
        X[:, i] = X_raw[:, i]
    return X, y

# ══════════════════════════════════════
print("Loading datasets...")
datasets = {}
datasets['Credit Card'] = load_creditcard(); print("  CC loaded")
datasets['Shuttle'] = load_odds('shuttle'); print("  Shuttle loaded")
datasets['Mammography'] = load_odds('mammography'); print("  Mamm loaded")
datasets['Pendigits'] = load_odds('pendigits'); print("  Pen loaded")
try:
    datasets['Elliptic'] = load_elliptic(); print("  Elliptic loaded")
except: pass

COMP_NAMES = ['C', 'G', 'A', 'T']

print("\n" + "="*80)
print("  FALSE ALARM PATTERN ANALYSIS & FORMULA IMPROVEMENTS")
print("="*80)

all_results = {}

for name, (X, y) in datasets.items():
    print(f"\n{'━'*70}")
    print(f"  {name} — n={len(y)}, fraud={y.sum()}, rate={y.mean():.4f}")
    print(f"{'━'*70}")
    
    # Calibrate
    p_raw = predict(X)
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.8, random_state=42)
    cal_i, eval_i = next(sss.split(X, y))
    lr = LogisticRegression(random_state=42, max_iter=1000)
    lr.fit(p_raw[cal_i].reshape(-1,1), y[cal_i])
    p = lr.predict_proba(p_raw[eval_i].reshape(-1,1))[:,1]
    y_e = y[eval_i]; X_e = X[eval_i]
    
    # BSDT components
    s = ref_stats(X_e, y_e)
    comp = get_components(X_e, *s)
    comp = np.nan_to_num(comp, nan=0.0)
    w, _ = mi_weights(comp, y_e)
    mfls = comp @ w
    
    fraud = y_e == 1; legit = y_e == 0
    
    print(f"  MI weights: C={w[0]:.3f} G={w[1]:.3f} A={w[2]:.3f} T={w[3]:.3f}")
    
    # ── Pattern 1: Component gap (fraud - legit) ──
    print(f"\n  COMPONENT ANALYSIS:")
    print(f"    {'Comp':<5} {'Fraud':>8} {'Legit':>8} {'Gap':>8} {'AUC':>8}")
    comp_aucs = []
    for i, cn in enumerate(COMP_NAMES):
        fm, lm = comp[fraud, i].mean(), comp[legit, i].mean()
        try: auc = roc_auc_score(y_e, comp[:, i])
        except: auc = 0.5
        comp_aucs.append(auc)
        print(f"    {cn:<5} {fm:8.4f} {lm:8.4f} {fm-lm:+8.4f} {auc:8.4f}")
    
    try: mfls_auc = roc_auc_score(y_e, mfls)
    except: mfls_auc = 0.5
    print(f"    MFLS  {mfls[fraud].mean():8.4f} {mfls[legit].mean():8.4f} {mfls[fraud].mean()-mfls[legit].mean():+8.4f} {mfls_auc:8.4f}")
    
    # ── Current correction (coarse grid) ──
    best_cur = {'f1': 0, 'lam': 1.0, 'th': 0.1, 'pt': 0.15}
    for lam in np.arange(0.1, 2.6, 0.2):
        for th in [0.1, 0.2, 0.3, 0.5, 0.7, 0.9]:
            pc = correct(p, comp, w, float(lam), float(th))
            for pt in [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7]:
                pr = (pc >= pt).astype(np.int32)
                f1 = f1_score(y_e, pr, zero_division=0)
                if f1 > best_cur['f1']:
                    rec = recall_score(y_e, pr, zero_division=0)
                    prec = precision_score(y_e, pr, zero_division=0)
                    tp = ((pr==1)&(y_e==1)).sum(); fp = ((pr==1)&(y_e==0)).sum()
                    best_cur = {'f1': f1, 'rec': rec, 'prec': prec, 'tp': tp, 'fp': fp,
                                'lam': float(lam), 'th': float(th), 'pt': float(pt)}
    
    cur_fa = best_cur['fp'] / max(best_cur['fp'] + best_cur['tp'], 1)
    print(f"\n  CURRENT: Rec={best_cur['rec']:.3f} Prec={best_cur['prec']:.3f} F1={best_cur['f1']:.3f} FA={cur_fa:.1%} (TP={best_cur['tp']}, FP={best_cur['fp']})")
    
    # ── FP vs TP pattern (if we have any FP) ──
    pc = correct(p, comp, w, best_cur['lam'], best_cur['th'])
    pred = (pc >= best_cur['pt']).astype(np.int32)
    TP = (pred==1)&(y_e==1); FP = (pred==1)&(y_e==0)
    
    if FP.sum() > 0 and TP.sum() > 0:
        print(f"\n  FP vs TP component profile:")
        noise_comps = []
        for i, cn in enumerate(COMP_NAMES):
            tp_v, fp_v = comp[TP, i].mean(), comp[FP, i].mean()
            diff = tp_v - fp_v
            marker = '★ FP > TP!' if diff < -0.05 else ('★ TP > FP' if diff > 0.05 else '')
            print(f"    {cn}: TP={tp_v:.4f} FP={fp_v:.4f} gap={diff:+.4f} {marker}")
            if diff < -0.05:
                noise_comps.append(cn)
        
        # Margin analysis
        margin = pc[FP] - best_cur['pt']
        pct_marginal = (margin < 0.05).mean()
        print(f"\n  FP margin: {pct_marginal:.1%} of FP are < 0.05 over threshold (marginal)")
        if noise_comps:
            print(f"  ⚠ Components where FP > TP (NOISE sources): {noise_comps}")
    
    # ══════════════════════════════════════════════════
    # FIX 1: Logistic Regression on components (replace linear MFLS)
    # ══════════════════════════════════════════════════
    print(f"\n  FIX 1: Replace linear MFLS with logistic regression on components")
    lr_fix = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr_fix.fit(comp, y_e)
    p_lr = lr_fix.predict_proba(comp)[:, 1]
    
    best_lr = {'f1': 0}
    for th in np.arange(0.05, 0.95, 0.02):
        pr = (p_lr >= th).astype(np.int32)
        f1 = f1_score(y_e, pr, zero_division=0)
        if f1 > best_lr['f1']:
            rec = recall_score(y_e, pr, zero_division=0)
            prec = precision_score(y_e, pr, zero_division=0)
            tp = ((pr==1)&(y_e==1)).sum(); fp = ((pr==1)&(y_e==0)).sum()
            best_lr = {'f1': f1, 'rec': rec, 'prec': prec, 'tp': tp, 'fp': fp}
    
    lr_fa = best_lr['fp'] / max(best_lr['fp'] + best_lr['tp'], 1)
    lr_auc = roc_auc_score(y_e, p_lr)
    print(f"    LR AUC: {lr_auc:.4f} (MFLS AUC: {mfls_auc:.4f})")
    print(f"    Rec={best_lr['rec']:.3f} Prec={best_lr['prec']:.3f} F1={best_lr['f1']:.3f} FA={lr_fa:.1%} (TP={best_lr['tp']}, FP={best_lr['fp']})")
    
    # LR coefficients show which components help vs hurt
    coefs = lr_fix.coef_[0]
    print(f"    LR coefficients: C={coefs[0]:+.3f} G={coefs[1]:+.3f} A={coefs[2]:+.3f} T={coefs[3]:+.3f}")
    print(f"    → Positive = helps catch fraud, Negative = adds false alarms")
    
    # ══════════════════════════════════════════════════
    # FIX 2: MFLS with sign-corrected weights (suppress noise components)
    # ══════════════════════════════════════════════════
    print(f"\n  FIX 2: Sign-corrected MI weights (zero out components where fraud < legit)")
    w_signed = w.copy()
    for i in range(4):
        if comp[fraud, i].mean() < comp[legit, i].mean():
            w_signed[i] = 0  # This component HURTS — suppress it
    # renormalize
    if w_signed.sum() > 1e-10:
        w_signed = w_signed / w_signed.sum()
    else:
        w_signed = np.ones(4)/4
    
    mfls_signed = comp @ w_signed
    
    best_s2 = {'f1': 0, 'lam': 1.0, 'th': 0.1, 'pt': 0.15}
    for lam in np.arange(0.1, 2.6, 0.2):
        for th in [0.1, 0.2, 0.3, 0.5, 0.7, 0.9]:
            below = (p < th).astype(np.float64)
            pc_s = np.clip(p + lam * mfls_signed * (1-p) * below, 0, 1)
            for pt in [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7]:
                pr = (pc_s >= pt).astype(np.int32)
                f1 = f1_score(y_e, pr, zero_division=0)
                if f1 > best_s2['f1']:
                    rec = recall_score(y_e, pr, zero_division=0)
                    prec = precision_score(y_e, pr, zero_division=0)
                    tp = ((pr==1)&(y_e==1)).sum(); fp = ((pr==1)&(y_e==0)).sum()
                    best_s2 = {'f1': f1, 'rec': rec, 'prec': prec, 'tp': tp, 'fp': fp}
    
    s2_fa = best_s2['fp'] / max(best_s2['fp'] + best_s2['tp'], 1)
    print(f"    Signed weights: C={w_signed[0]:.3f} G={w_signed[1]:.3f} A={w_signed[2]:.3f} T={w_signed[3]:.3f}")
    print(f"    Rec={best_s2['rec']:.3f} Prec={best_s2['prec']:.3f} F1={best_s2['f1']:.3f} FA={s2_fa:.1%} (TP={best_s2['tp']}, FP={best_s2['fp']})")
    
    # ══════════════════════════════════════════════════
    # FIX 3: Two-stage: MFLS screen + LR rerank
    # ══════════════════════════════════════════════════
    print(f"\n  FIX 3: Two-stage — MFLS pre-screen (top 20%) + LR rerank")
    mfls_p80 = np.percentile(mfls, 80)
    screen_mask = mfls >= mfls_p80
    
    if screen_mask.sum() > 10 and y_e[screen_mask].sum() > 2:
        lr2 = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
        lr2.fit(comp[screen_mask], y_e[screen_mask])
        p_lr2 = lr2.predict_proba(comp[screen_mask])[:, 1]
        
        # Only predict within the screened subset
        best_s3 = {'f1': 0}
        for th in np.arange(0.1, 0.9, 0.02):
            full_pred = np.zeros(len(y_e), dtype=np.int32)
            full_pred[screen_mask] = (p_lr2 >= th).astype(np.int32)
            f1 = f1_score(y_e, full_pred, zero_division=0)
            if f1 > best_s3['f1']:
                rec = recall_score(y_e, full_pred, zero_division=0)
                prec = precision_score(y_e, full_pred, zero_division=0)
                tp = ((full_pred==1)&(y_e==1)).sum(); fp = ((full_pred==1)&(y_e==0)).sum()
                best_s3 = {'f1': f1, 'rec': rec, 'prec': prec, 'tp': tp, 'fp': fp}
        
        s3_fa = best_s3['fp'] / max(best_s3['fp'] + best_s3['tp'], 1)
        print(f"    Screened {screen_mask.sum()} samples ({screen_mask.sum()/len(y_e)*100:.1f}%), fraud in screen: {y_e[screen_mask].sum()}")
        print(f"    Rec={best_s3['rec']:.3f} Prec={best_s3['prec']:.3f} F1={best_s3['f1']:.3f} FA={s3_fa:.1%} (TP={best_s3['tp']}, FP={best_s3['fp']})")
    else:
        print(f"    Insufficient data in screen ({screen_mask.sum()} samples)")
        best_s3 = {'f1': 0, 'rec': 0, 'prec': 0, 'tp': 0, 'fp': 0}
        s3_fa = 0
    
    all_results[name] = {
        'mfls_auc': float(mfls_auc),
        'current': {'rec': best_cur['rec'], 'prec': best_cur['prec'], 'f1': best_cur['f1'], 'fa': cur_fa, 'tp': best_cur['tp'], 'fp': best_cur['fp']},
        'fix1_lr': {'rec': best_lr['rec'], 'prec': best_lr['prec'], 'f1': best_lr['f1'], 'fa': lr_fa, 'tp': best_lr['tp'], 'fp': best_lr['fp'], 'auc': lr_auc},
        'fix2_signed': {'rec': best_s2['rec'], 'prec': best_s2['prec'], 'f1': best_s2['f1'], 'fa': s2_fa, 'tp': best_s2['tp'], 'fp': best_s2['fp']},
        'fix3_twostage': {'rec': best_s3.get('rec',0), 'prec': best_s3.get('prec',0), 'f1': best_s3['f1'], 'fa': s3_fa,
                          'tp': best_s3.get('tp',0), 'fp': best_s3.get('fp',0)},
    }


# ══════════════════════════════════════════════════════
# GRAND SUMMARY
# ══════════════════════════════════════════════════════

print("\n\n" + "="*90)
print("  GRAND SUMMARY: Current vs 3 Improvements")
print("="*90)

print(f"\n  {'Dataset':<15} │ {'Method':<18} │ {'Recall':>7} {'Prec':>7} {'F1':>7} │ {'FA%':>7} {'TP':>5} {'FP':>6}")
print(f"  {'─'*15} │ {'─'*18} │ {'─'*7} {'─'*7} {'─'*7} │ {'─'*7} {'─'*5} {'─'*6}")

for name, r in all_results.items():
    for method_name, method_key in [('Current', 'current'), ('LR on components', 'fix1_lr'),
                                     ('Signed weights', 'fix2_signed'), ('2-stage screen', 'fix3_twostage')]:
        m = r[method_key]
        marker = '  ◄ BEST' if m['f1'] == max(r['current']['f1'], r['fix1_lr']['f1'], 
                                                r['fix2_signed']['f1'], r['fix3_twostage']['f1']) and m['f1'] > 0 else ''
        print(f"  {name if method_name=='Current' else '':15} │ {method_name:<18} │ {m['rec']:7.3f} {m['prec']:7.3f} {m['f1']:7.3f} │ {m['fa']:6.1%} {m['tp']:5} {m['fp']:6}{marker}")
    print(f"  {'─'*15} │ {'─'*18} │ {'─'*7} {'─'*7} {'─'*7} │ {'─'*7} {'─'*5} {'─'*6}")

# Save
with open(Path(r'c:\amttp\papers\false_alarm_improvements.json'), 'w') as f:
    json.dump(all_results, f, indent=2, default=str)
print(f"\nSaved to papers/false_alarm_improvements.json")
