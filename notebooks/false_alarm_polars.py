"""
False Alarm Pattern Analysis — Polars + Vectorised
====================================================
Uses Polars for fast I/O, vectorised NumPy for grid search.
The old script had ~50K Python-level f1_score calls per dataset.
This version computes TP/FP/FN via broadcasting — ~100x faster.
"""

import numpy as np
import polars as pl
import scipy.io as sio
from pathlib import Path
import warnings, json, time
warnings.filterwarnings('ignore')

ARTIFACTS = Path(r'C:\Users\Administrator\Downloads\amttp_student_artifacts\amttp_models_20260213_213346')
DATA_DIR = Path(r'c:\amttp\data\external_validation')

import joblib, xgboost as xgb
from sklearn.metrics import roc_auc_score, mutual_info_score
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedShuffleSplit

preprocessors = joblib.load(ARTIFACTS / 'preprocessors.joblib')
scaler = preprocessors['scaler']
FEATURES_93 = list(preprocessors['feature_names'])
xgb_model = xgb.Booster()
xgb_model.load_model(str(ARTIFACTS / 'xgboost_fraud.ubj'))
IDX_SENT = 7; IDX_RECV = 60

# ── BSDT core (pure numpy) ──
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
    c = np.column_stack([camouflage_score(X, s[0], s[1]),
                         feature_gap_score(X),
                         activity_anomaly_score(X, s[4], s[5]),
                         temporal_novelty_score(X, s[2], s[3])])
    return np.nan_to_num(c, nan=0.0)
def mi_weights(comp, y, nb=20):
    mi = np.zeros(4)
    for i in range(4):
        b = np.digitize(comp[:, i], np.linspace(comp[:, i].min(), comp[:, i].max()+1e-8, nb))
        mi[i] = mutual_info_score(y, b)
    t = mi.sum()
    return (mi / t if t > 1e-10 else np.ones(4)/4)

def preprocess(X):
    X2 = np.log1p(np.abs(X)) * np.sign(X)
    X2 = scaler.transform(X2)
    X2 = np.clip(X2, -10, 10)
    return np.nan_to_num(X2, nan=0.0, posinf=10.0, neginf=-10.0)
def predict(X):
    return xgb_model.predict(xgb.DMatrix(preprocess(X), feature_names=FEATURES_93))


# ══════════════════════════════════════════════════════
# VECTORISED GRID SEARCH — the key speedup
# ══════════════════════════════════════════════════════

def vectorised_f1(y_true, scores, thresholds):
    """
    Compute F1, recall, precision for MANY thresholds at once.
    y_true: (N,) bool/int
    scores: (N,) float  (corrected probabilities)
    thresholds: (T,) float
    Returns: (T,) f1, (T,) recall, (T,) precision
    """
    # scores: N, thresholds: T → preds: (T, N)
    preds = scores[np.newaxis, :] >= thresholds[:, np.newaxis]  # (T, N)
    y = y_true.astype(bool)
    tp = (preds & y).sum(axis=1).astype(np.float64)        # (T,)
    fp = (preds & ~y).sum(axis=1).astype(np.float64)        # (T,)
    fn = (~preds & y).sum(axis=1).astype(np.float64)        # (T,)
    prec = np.where(tp + fp > 0, tp / (tp + fp), 0.0)
    rec  = np.where(tp + fn > 0, tp / (tp + fn), 0.0)
    f1   = np.where(prec + rec > 0, 2 * prec * rec / (prec + rec), 0.0)
    return f1, rec, prec, tp.astype(int), fp.astype(int)


def fast_grid_search(p, mfls, y, lam_range, tau_range, pt_range):
    """
    Vectorised grid search over λ, τ, prediction threshold.
    Returns best {f1, rec, prec, tp, fp, lam, tau, pt}.
    """
    best = {'f1': 0.0}
    y_arr = np.asarray(y, dtype=bool)
    pt_arr = np.asarray(pt_range, dtype=np.float64)
    
    for lam in lam_range:
        for tau in tau_range:
            below = (p < tau).astype(np.float64)
            pc = np.clip(p + lam * mfls * (1.0 - p) * below, 0.0, 1.0)
            
            # Vectorise over ALL prediction thresholds at once
            f1s, recs, precs, tps, fps = vectorised_f1(y_arr, pc, pt_arr)
            
            idx = np.argmax(f1s)
            if f1s[idx] > best['f1']:
                best = {'f1': float(f1s[idx]), 'rec': float(recs[idx]),
                        'prec': float(precs[idx]), 'tp': int(tps[idx]),
                        'fp': int(fps[idx]), 'lam': float(lam),
                        'tau': float(tau), 'pt': float(pt_arr[idx])}
    return best


# ══════════════════════════════════════════════════════
# DATA LOADERS — Polars for speed
# ══════════════════════════════════════════════════════

AMTTP_TARGETS = [
    'sender_total_sent','sender_avg_sent','sender_sent_count','value_eth',
    'sender_total_transactions','sender_balance','receiver_total_received',
    'sender_in_out_ratio','receiver_avg_received','sender_unique_counterparties',
    'sender_degree','sender_neighbors','sender_in_degree','sender_out_degree',
    'sender_unique_receivers','receiver_unique_senders','sender_max_sent',
    'sender_min_sent','receiver_max_received','receiver_min_received',
    'receiver_received_count','sender_avg_time_between_txns','sender_stddev_sent',
    'receiver_stddev_received','sender_cluster_coeff','sender_pagerank',
    'sender_betweenness','sender_closeness',
]

def map_to_93(mapped_dict):
    """Build 93-feature numpy array from {amttp_name: values} dict."""
    feat_idx = {f: i for i, f in enumerate(FEATURES_93)}
    n = len(next(iter(mapped_dict.values())))
    X = np.zeros((n, 93), dtype=np.float32)
    for name, vals in mapped_dict.items():
        if name in feat_idx:
            X[:, feat_idx[name]] = vals
    return X


def load_creditcard():
    t0 = time.time()
    df = pl.read_csv(DATA_DIR / 'creditcard' / 'creditcard.csv')
    y = df['Class'].to_numpy().astype(np.int32)
    
    v_cols = [c for c in df.columns if c.startswith('V')]
    mapped = {}
    for i, col in enumerate(v_cols):
        if i < len(AMTTP_TARGETS):
            mapped[AMTTP_TARGETS[i]] = df[col].to_numpy().astype(np.float32)
    mapped['value_eth'] = df['Amount'].to_numpy().astype(np.float32)
    
    X = map_to_93(mapped)
    print(f"  Credit Card: {len(y):,} samples, {y.sum()} fraud — loaded in {time.time()-t0:.1f}s (Polars)")
    return X, y


def load_odds(name):
    t0 = time.time()
    d = sio.loadmat(str(DATA_DIR / 'odds' / f'{name}.mat'))
    X_raw, y_raw = d['X'].astype(np.float32), d['y'].ravel().astype(np.int32)
    
    mapped = {}
    for i in range(min(X_raw.shape[1], len(AMTTP_TARGETS))):
        mapped[AMTTP_TARGETS[i]] = X_raw[:, i]
    
    X = map_to_93(mapped)
    print(f"  {name}: {len(y_raw):,} samples, {y_raw.sum()} anomalies — loaded in {time.time()-t0:.2f}s")
    return X, y_raw


def load_elliptic():
    t0 = time.time()
    features = pl.read_csv(DATA_DIR / 'elliptic' / 'elliptic_txs_features.csv', has_header=False)
    classes = pl.read_csv(DATA_DIR / 'elliptic' / 'elliptic_txs_classes.csv')
    
    # Rename columns
    feat_cols = ['txId'] + [f'feat_{i}' for i in range(1, features.shape[1])]
    features = features.rename({old: new for old, new in zip(features.columns, feat_cols)})
    classes = classes.rename({classes.columns[0]: 'txId', classes.columns[1]: 'class'})
    
    merged = features.join(classes, on='txId')
    labelled = merged.filter(pl.col('class').is_in(['1', '2']))
    
    y = (labelled['class'].cast(pl.Utf8) == '2').to_numpy().astype(np.int32)
    
    # Extract feature columns as numpy
    feat_names = [f'feat_{i}' for i in range(1, 167)]
    available = [f for f in feat_names if f in labelled.columns]
    X_raw = labelled.select(available).to_numpy().astype(np.float32)
    
    X = np.zeros((len(X_raw), 93), dtype=np.float32)
    for i in range(min(93, X_raw.shape[1])):
        X[:, i] = X_raw[:, i]
    
    print(f"  Elliptic: {len(y):,} samples, {y.sum()} fraud — loaded in {time.time()-t0:.1f}s (Polars)")
    return X, y


# ══════════════════════════════════════════════════════
# MAIN ANALYSIS
# ══════════════════════════════════════════════════════

total_start = time.time()
print("Loading datasets with Polars...")

datasets = {}
datasets['Credit Card'] = load_creditcard()
datasets['Shuttle'] = load_odds('shuttle')
datasets['Mammography'] = load_odds('mammography')
datasets['Pendigits'] = load_odds('pendigits')
try:
    datasets['Elliptic'] = load_elliptic()
except Exception as e:
    print(f"  Elliptic: skipped ({e})")

load_time = time.time() - total_start
print(f"All datasets loaded in {load_time:.1f}s\n")

# Grid search parameters
LAM_RANGE = np.arange(0.1, 2.6, 0.15)          # 17 values
TAU_RANGE = np.array([0.1, 0.2, 0.3, 0.5, 0.7, 0.9])  # 6 values
PT_RANGE  = np.arange(0.10, 0.85, 0.03)         # 25 values

COMP_NAMES = ['C', 'G', 'A', 'T']

print("="*85)
print("  FALSE ALARM ANALYSIS + IMPROVEMENTS (Polars + Vectorised)")
print("="*85)

all_results = {}

for name, (X, y) in datasets.items():
    ds_start = time.time()
    print(f"\n{'━'*75}")
    print(f"  {name} — n={len(y):,}, fraud={y.sum()}, rate={y.mean():.4f}")
    print(f"{'━'*75}")
    
    # ── Calibrate ──
    p_raw = predict(X)
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.8, random_state=42)
    cal_i, eval_i = next(sss.split(X, y))
    lr_cal = LogisticRegression(random_state=42, max_iter=1000)
    lr_cal.fit(p_raw[cal_i].reshape(-1,1), y[cal_i])
    p = lr_cal.predict_proba(p_raw[eval_i].reshape(-1,1))[:,1]
    y_e = y[eval_i]; X_e = X[eval_i]
    
    # ── BSDT components ──
    s = ref_stats(X_e, y_e)
    comp = get_components(X_e, *s)
    w = mi_weights(comp, y_e)
    mfls = comp @ w
    
    fraud = y_e == 1; legit = y_e == 0
    print(f"  MI weights: C={w[0]:.3f} G={w[1]:.3f} A={w[2]:.3f} T={w[3]:.3f}")
    
    # ── Component analysis ──
    print(f"\n  COMPONENTS (Fraud vs Legit):")
    print(f"    {'Comp':<5} {'Fraud':>8} {'Legit':>8} {'Gap':>8} {'AUC':>7}")
    comp_aucs = []
    for i, cn in enumerate(COMP_NAMES):
        fm, lm = comp[fraud,i].mean(), comp[legit,i].mean()
        try: auc = roc_auc_score(y_e, comp[:,i])
        except: auc = 0.5
        comp_aucs.append(auc)
        dir_marker = '↑' if fm > lm + 0.01 else ('↓' if fm < lm - 0.01 else '=')
        print(f"    {cn:<5} {fm:8.4f} {lm:8.4f} {fm-lm:+8.4f} {auc:7.4f} {dir_marker}")
    
    try: mfls_auc = roc_auc_score(y_e, mfls)
    except: mfls_auc = 0.5
    print(f"    MFLS  {mfls[fraud].mean():8.4f} {mfls[legit].mean():8.4f} {mfls[fraud].mean()-mfls[legit].mean():+8.4f} {mfls_auc:7.4f}")
    
    # ════════════════════════════════════════
    # CURRENT FORMULA (vectorised grid search)
    # ════════════════════════════════════════
    t0 = time.time()
    best_cur = fast_grid_search(p, mfls, y_e, LAM_RANGE, TAU_RANGE, PT_RANGE)
    cur_fa = best_cur['fp'] / max(best_cur['fp'] + best_cur['tp'], 1)
    print(f"\n  CURRENT: Rec={best_cur['rec']:.3f} Prec={best_cur['prec']:.3f} F1={best_cur['f1']:.3f} FA={cur_fa:.1%} TP={best_cur['tp']} FP={best_cur['fp']}  [{time.time()-t0:.1f}s]")
    
    # ── FP analysis ──
    pc = np.clip(p + best_cur['lam'] * mfls * (1-p) * (p < best_cur['tau']).astype(float), 0, 1)
    pred = (pc >= best_cur['pt']).astype(np.int32)
    TP_mask = (pred==1)&(y_e==1); FP_mask = (pred==1)&(y_e==0)
    
    if FP_mask.sum() > 0 and TP_mask.sum() > 0:
        print(f"\n  FP vs TP profile:")
        noise_comps = []
        for i, cn in enumerate(COMP_NAMES):
            tp_v, fp_v = comp[TP_mask,i].mean(), comp[FP_mask,i].mean()
            gap = tp_v - fp_v
            if gap < -0.03:
                noise_comps.append((i, cn, gap))
                print(f"    {cn}: TP={tp_v:.4f} FP={fp_v:.4f} gap={gap:+.4f} ⚠ NOISE")
            elif gap > 0.03:
                print(f"    {cn}: TP={tp_v:.4f} FP={fp_v:.4f} gap={gap:+.4f} ✓ HELPS")
            else:
                print(f"    {cn}: TP={tp_v:.4f} FP={fp_v:.4f} gap={gap:+.4f}   neutral")
        
        margin = pc[FP_mask] - best_cur['pt']
        print(f"    FP marginal (<0.05 over threshold): {(margin<0.05).mean():.1%}")
        
        if noise_comps:
            print(f"    ⚠ Noise components: {[c[1] for c in noise_comps]}")
    
    # ════════════════════════════════════════
    # FIX 1: Logistic Regression on components
    # ════════════════════════════════════════
    t0 = time.time()
    lr_fix = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr_fix.fit(comp, y_e)
    p_lr = lr_fix.predict_proba(comp)[:, 1]
    
    f1s, recs, precs, tps, fps = vectorised_f1(y_e, p_lr, PT_RANGE)
    idx = np.argmax(f1s)
    best_lr = {'f1': float(f1s[idx]), 'rec': float(recs[idx]), 'prec': float(precs[idx]),
               'tp': int(tps[idx]), 'fp': int(fps[idx])}
    lr_fa = best_lr['fp'] / max(best_lr['fp'] + best_lr['tp'], 1)
    lr_auc = roc_auc_score(y_e, p_lr)
    
    coefs = lr_fix.coef_[0]
    print(f"\n  FIX 1 (LR on components): Rec={best_lr['rec']:.3f} Prec={best_lr['prec']:.3f} F1={best_lr['f1']:.3f} FA={lr_fa:.1%} AUC={lr_auc:.4f}  [{time.time()-t0:.1f}s]")
    print(f"    LR coefs: C={coefs[0]:+.2f} G={coefs[1]:+.2f} A={coefs[2]:+.2f} T={coefs[3]:+.2f}")
    
    # ════════════════════════════════════════
    # FIX 2: Direction-aware weights (suppress noise components)
    # ════════════════════════════════════════
    t0 = time.time()
    w_dir = w.copy()
    for i in range(4):
        if comp[fraud,i].mean() < comp[legit,i].mean():
            w_dir[i] = 0  # suppress noise
    if w_dir.sum() > 1e-10:
        w_dir /= w_dir.sum()
    else:
        w_dir = np.ones(4)/4
    
    mfls_dir = comp @ w_dir
    best_dir = fast_grid_search(p, mfls_dir, y_e, LAM_RANGE, TAU_RANGE, PT_RANGE)
    dir_fa = best_dir['fp'] / max(best_dir['fp'] + best_dir['tp'], 1)
    print(f"\n  FIX 2 (Direction-aware): Rec={best_dir['rec']:.3f} Prec={best_dir['prec']:.3f} F1={best_dir['f1']:.3f} FA={dir_fa:.1%}  [{time.time()-t0:.1f}s]")
    print(f"    Weights: C={w_dir[0]:.3f} G={w_dir[1]:.3f} A={w_dir[2]:.3f} T={w_dir[3]:.3f}")
    
    # ════════════════════════════════════════
    # FIX 3: Two-stage — MFLS pre-screen + LR refine
    # ════════════════════════════════════════
    t0 = time.time()
    best_s3 = {'f1': 0, 'rec': 0, 'prec': 0, 'tp': 0, 'fp': 0}
    for pctile in [70, 80, 90]:
        mfls_th = np.percentile(mfls, pctile)
        screen = mfls >= mfls_th
        
        if screen.sum() > 10 and y_e[screen].sum() > 2:
            lr2 = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
            lr2.fit(comp[screen], y_e[screen])
            p_stage2 = lr2.predict_proba(comp[screen])[:, 1]
            
            # Build full predictions for each threshold
            for th in np.arange(0.1, 0.9, 0.03):
                full_pred = np.zeros(len(y_e), dtype=np.int32)
                full_pred[screen] = (p_stage2 >= th).astype(np.int32)
                tp = ((full_pred==1)&(y_e==1)).sum()
                fp = ((full_pred==1)&(y_e==0)).sum()
                fn = ((full_pred==0)&(y_e==1)).sum()
                prec_v = tp / max(tp+fp, 1)
                rec_v = tp / max(tp+fn, 1)
                f1_v = 2*prec_v*rec_v / max(prec_v+rec_v, 1e-10) if (prec_v+rec_v) > 0 else 0
                if f1_v > best_s3['f1']:
                    best_s3 = {'f1': f1_v, 'rec': rec_v, 'prec': prec_v, 'tp': int(tp), 'fp': int(fp), 'pctile': pctile}
    
    s3_fa = best_s3['fp'] / max(best_s3['fp'] + best_s3['tp'], 1)
    print(f"\n  FIX 3 (2-stage screen+LR): Rec={best_s3['rec']:.3f} Prec={best_s3['prec']:.3f} F1={best_s3['f1']:.3f} FA={s3_fa:.1%}  [{time.time()-t0:.1f}s]")
    
    # ════════════════════════════════════════
    # FIX 4: MFLS² — quadratic weighting (amplifies high-MFLS separation)
    # ════════════════════════════════════════
    t0 = time.time()
    mfls_sq = mfls ** 2  # Amplify high scores, suppress low ones
    best_sq = fast_grid_search(p, mfls_sq, y_e, LAM_RANGE, TAU_RANGE, PT_RANGE)
    sq_fa = best_sq['fp'] / max(best_sq['fp'] + best_sq['tp'], 1)
    print(f"\n  FIX 4 (MFLS²): Rec={best_sq['rec']:.3f} Prec={best_sq['prec']:.3f} F1={best_sq['f1']:.3f} FA={sq_fa:.1%}  [{time.time()-t0:.1f}s]")
    
    ds_time = time.time() - ds_start
    print(f"\n  Dataset total: {ds_time:.1f}s")
    
    all_results[name] = {
        'n': len(y_e), 'fraud': int(y_e.sum()), 'mfls_auc': float(mfls_auc),
        'current':   {'rec': best_cur['rec'], 'prec': best_cur['prec'], 'f1': best_cur['f1'], 'fa': cur_fa, 'tp': best_cur['tp'], 'fp': best_cur['fp']},
        'fix1_lr':   {'rec': best_lr['rec'],  'prec': best_lr['prec'],  'f1': best_lr['f1'],  'fa': lr_fa,  'tp': best_lr['tp'],  'fp': best_lr['fp'], 'auc': lr_auc, 'coefs': coefs.tolist()},
        'fix2_dir':  {'rec': best_dir['rec'], 'prec': best_dir['prec'], 'f1': best_dir['f1'], 'fa': dir_fa, 'tp': best_dir['tp'], 'fp': best_dir['fp'], 'w': w_dir.tolist()},
        'fix3_2stg': {'rec': best_s3['rec'],  'prec': best_s3['prec'],  'f1': best_s3['f1'],  'fa': s3_fa,  'tp': best_s3['tp'],  'fp': best_s3['fp']},
        'fix4_sq':   {'rec': best_sq['rec'],  'prec': best_sq['prec'],  'f1': best_sq['f1'],  'fa': sq_fa,  'tp': best_sq['tp'],  'fp': best_sq['fp']},
        'noise_components': [c[1] for c in noise_comps] if FP_mask.sum() > 0 and TP_mask.sum() > 0 else [],
    }


# ══════════════════════════════════════════════════════
# GRAND SUMMARY
# ══════════════════════════════════════════════════════

total_time = time.time() - total_start
print(f"\n\n{'='*95}")
print(f"  GRAND SUMMARY — Total runtime: {total_time:.1f}s")
print(f"{'='*95}")

methods = [('Current',  'current'),
           ('LR on 4 comp', 'fix1_lr'),
           ('Dir-aware wts', 'fix2_dir'),
           ('2-stage scr', 'fix3_2stg'),
           ('MFLS²', 'fix4_sq')]

print(f"\n  {'Dataset':<15} {'Method':<16} {'Recall':>7} {'Prec':>7} {'F1':>7} {'FA%':>7} {'TP':>5} {'FP':>6}")
print(f"  {'─'*15} {'─'*16} {'─'*7} {'─'*7} {'─'*7} {'─'*7} {'─'*5} {'─'*6}")

for dname, r in all_results.items():
    best_f1 = max(r[mk]['f1'] for _, mk in methods)
    for i, (mname, mk) in enumerate(methods):
        m = r[mk]
        marker = ' ★' if m['f1'] == best_f1 and m['f1'] > 0 else ''
        label = dname if i == 0 else ''
        print(f"  {label:<15} {mname:<16} {m['rec']:7.3f} {m['prec']:7.3f} {m['f1']:7.3f} {m['fa']:6.1%} {m['tp']:5} {m['fp']:6}{marker}")
    print(f"  {'─'*15} {'─'*16} {'─'*7} {'─'*7} {'─'*7} {'─'*7} {'─'*5} {'─'*6}")

# Average improvement
print(f"\n  AVERAGE ACROSS DATASETS:")
for mname, mk in methods:
    avg_f1 = np.mean([r[mk]['f1'] for r in all_results.values()])
    avg_fa = np.mean([r[mk]['fa'] for r in all_results.values()])
    avg_rec = np.mean([r[mk]['rec'] for r in all_results.values()])
    avg_prec = np.mean([r[mk]['prec'] for r in all_results.values()])
    print(f"    {mname:<16} F1={avg_f1:.3f}  Rec={avg_rec:.3f}  Prec={avg_prec:.3f}  FA={avg_fa:.1%}")

with open(Path(r'c:\amttp\papers\false_alarm_improvements.json'), 'w') as f:
    json.dump(all_results, f, indent=2, default=str)
print(f"\nResults saved → papers/false_alarm_improvements.json")
print(f"Total runtime: {total_time:.1f}s")
