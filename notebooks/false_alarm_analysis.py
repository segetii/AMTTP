"""
False Alarm Pattern Analysis for BSDT Correction
==================================================
Examines WHERE false alarms concentrate in the component space
and identifies patterns that can be exploited to reduce them.
"""

import numpy as np
import pandas as pd
import scipy.io as sio
from pathlib import Path
import sys, warnings, json
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

# Load AMTTP model
preprocessors = joblib.load(ARTIFACTS / 'preprocessors.joblib')
scaler = preprocessors['scaler']
FEATURES_93 = list(preprocessors['feature_names'])
xgb_model = xgb.Booster()
xgb_model.load_model(str(ARTIFACTS / 'xgboost_fraud.ubj'))

OPTIMAL_THRESHOLD = 0.6428
IDX_SENT = 7
IDX_RECV = 60


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

def components(X, *s):
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


def preprocess(X):
    X2 = np.log1p(np.abs(X)) * np.sign(X)
    X2 = scaler.transform(X2)
    X2 = np.clip(X2, -10, 10)
    return np.nan_to_num(X2, nan=0.0, posinf=10.0, neginf=-10.0)


def predict(X):
    return xgb_model.predict(xgb.DMatrix(preprocess(X), feature_names=FEATURES_93))


def build_X_generic(features_df):
    X = np.zeros((len(features_df), 93), dtype=np.float32)
    for i, f in enumerate(FEATURES_93):
        if f in features_df.columns:
            X[:, i] = features_df[f].values.astype(np.float32)
    return X


# ══════════════════════════════════════════════════════
# Load datasets
# ══════════════════════════════════════════════════════

def load_datasets():
    datasets = {}
    
    # 1. Credit Card Fraud
    cc = pd.read_csv(DATA_DIR / 'creditcard' / 'creditcard.csv')
    feat = cc.drop(columns=['Class'])
    X_cc = build_X_generic(feat)
    y_cc = cc['Class'].values.astype(np.int32)
    datasets['Credit Card'] = (X_cc, y_cc)
    
    # 2. Shuttle
    mat = sio.loadmat(DATA_DIR / 'odds' / 'shuttle.mat')
    X_sh_raw = np.asarray(mat['X'], dtype=np.float32)
    y_sh_raw = np.asarray(mat['y'], dtype=np.int32).ravel()
    df = pd.DataFrame(X_sh_raw, columns=[f'V{i}' for i in range(X_sh_raw.shape[1])])
    X_sh = build_X_generic(df)
    datasets['Shuttle'] = (X_sh, y_sh_raw)
    
    # 3. Mammography
    mat = sio.loadmat(DATA_DIR / 'odds' / 'mammography.mat')
    X_mm_raw = np.asarray(mat['X'], dtype=np.float32)
    y_mm_raw = np.asarray(mat['y'], dtype=np.int32).ravel()
    df = pd.DataFrame(X_mm_raw, columns=[f'V{i}' for i in range(X_mm_raw.shape[1])])
    X_mm = build_X_generic(df)
    datasets['Mammography'] = (X_mm, y_mm_raw)
    
    # 4. Pendigits
    mat = sio.loadmat(DATA_DIR / 'odds' / 'pendigits.mat')
    X_pd_raw = np.asarray(mat['X'], dtype=np.float32)
    y_pd_raw = np.asarray(mat['y'], dtype=np.int32).ravel()
    df = pd.DataFrame(X_pd_raw, columns=[f'V{i}' for i in range(X_pd_raw.shape[1])])
    X_pd = build_X_generic(df)
    datasets['Pendigits'] = (X_pd, y_pd_raw)
    
    return datasets


# ══════════════════════════════════════════════════════
# ANALYSIS: False Alarm Patterns
# ══════════════════════════════════════════════════════

print("Loading datasets...")
datasets = load_datasets()

print("\n" + "="*80)
print("  FALSE ALARM PATTERN ANALYSIS")
print("="*80)

# Store results for all datasets
all_patterns = {}

for name, (X, y) in datasets.items():
    print(f"\n{'─'*70}")
    print(f"  {name}")
    print(f"{'─'*70}")
    
    # Predict and calibrate
    p_raw = predict(X)
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.8, random_state=42)
    cal_i, eval_i = next(sss.split(X, y))
    lr = LogisticRegression(random_state=42, max_iter=1000)
    lr.fit(p_raw[cal_i].reshape(-1,1), y[cal_i])
    p = lr.predict_proba(p_raw[eval_i].reshape(-1,1))[:,1]
    y_e = y[eval_i]
    X_e = X[eval_i]
    
    # Compute stats and components
    s = ref_stats(X_e, y_e)
    comp = components(X_e, *s)
    
    # MI weights
    w, _ = mi_weights(comp, y_e)
    mfls = comp @ w
    
    # Apply current correction (MI-optimised)
    best_lam, best_th, best_pt = 1.0, 0.1, 0.15  # defaults
    best_f1 = 0
    for lam in np.arange(0.05, 2.5, 0.05):
        for th in np.arange(0.1, 0.95, 0.1):
            pc_test = correct(p, comp, w, float(lam), float(th))
            for t2 in np.arange(0.15, 0.9, 0.1):
                pred_test = (pc_test >= t2).astype(np.int32)
                f1_test = f1_score(y_e, pred_test, zero_division=0)
                if f1_test > best_f1:
                    best_f1 = f1_test
                    best_lam, best_th, best_pt = float(lam), float(th), float(t2)
    
    pc = correct(p, comp, w, best_lam, best_th)
    pred = (pc >= best_pt).astype(np.int32)
    
    # Classify outcomes
    TP = (pred == 1) & (y_e == 1)  # True positives (fraud caught)
    FP = (pred == 1) & (y_e == 0)  # FALSE ALARMS
    TN = (pred == 0) & (y_e == 0)  # True negatives
    FN = (pred == 0) & (y_e == 1)  # Missed fraud
    
    n_tp, n_fp, n_tn, n_fn = TP.sum(), FP.sum(), TN.sum(), FN.sum()
    
    print(f"  Baseline model prob range: [{p.min():.4f}, {p.max():.4f}]")
    print(f"  Correction: λ={best_lam:.2f}, τ={best_th:.2f}, pred_th={best_pt:.2f}")
    print(f"  TP={n_tp}, FP={n_fp}, TN={n_tn}, FN={n_fn}")
    print(f"  Precision={n_tp/(n_tp+n_fp):.4f}, Recall={n_tp/(n_tp+n_fn):.4f}")
    print(f"  False Alarm Rate: {n_fp}/{n_fp+n_tp} = {n_fp/(n_fp+n_tp):.1%}")
    
    # ── PATTERN 1: MFLS score distributions ──
    print(f"\n  ▸ MFLS Distribution by outcome:")
    print(f"    True Positives  (real fraud, flagged):  mean={mfls[TP].mean():.4f}, std={mfls[TP].std():.4f}, median={np.median(mfls[TP]):.4f}")
    if n_fp > 0:
        print(f"    False Positives (legit, flagged):       mean={mfls[FP].mean():.4f}, std={mfls[FP].std():.4f}, median={np.median(mfls[FP]):.4f}")
    print(f"    True Negatives  (legit, not flagged):   mean={mfls[TN].mean():.4f}, std={mfls[TN].std():.4f}, median={np.median(mfls[TN]):.4f}")
    if n_fn > 0:
        print(f"    False Negatives (fraud, missed):        mean={mfls[FN].mean():.4f}, std={mfls[FN].std():.4f}, median={np.median(mfls[FN]):.4f}")
    
    # ── PATTERN 2: Component-level breakdown for FP vs TP ──
    comp_names = ['C (Camouflage)', 'G (Feature Gap)', 'A (Activity)', 'T (Temporal)']
    print(f"\n  ▸ Component means: TP vs FP")
    print(f"    {'Component':<20} {'TP mean':>8} {'FP mean':>8} {'Diff':>8} {'FP > TP?':>10}")
    for i, cn in enumerate(comp_names):
        tp_m = comp[TP, i].mean() if n_tp > 0 else 0
        fp_m = comp[FP, i].mean() if n_fp > 0 else 0
        diff = fp_m - tp_m
        print(f"    {cn:<20} {tp_m:8.4f} {fp_m:8.4f} {diff:+8.4f} {'YES' if diff > 0.01 else 'no':>10}")
    
    # ── PATTERN 3: Base model probability of false positives ──
    print(f"\n  ▸ Base model p(fraud) for false positives:")
    if n_fp > 0:
        fp_p = p[FP]
        print(f"    Range: [{fp_p.min():.4f}, {fp_p.max():.4f}]")
        print(f"    Mean:  {fp_p.mean():.4f}")
        print(f"    Median: {np.median(fp_p):.4f}")
        pct_very_low = (fp_p < 0.01).mean()
        pct_low = ((fp_p >= 0.01) & (fp_p < 0.1)).mean()
        pct_med = ((fp_p >= 0.1) & (fp_p < 0.3)).mean()
        pct_high = (fp_p >= 0.3).mean()
        print(f"    <0.01: {pct_very_low:.1%} | 0.01-0.10: {pct_low:.1%} | 0.10-0.30: {pct_med:.1%} | >0.30: {pct_high:.1%}")
    
    # ── PATTERN 4: Corrected probability of FP vs TP ──
    print(f"\n  ▸ Corrected p*(x) for false positives vs true positives:")
    if n_tp > 0:
        print(f"    TP p* range:  [{pc[TP].min():.4f}, {pc[TP].max():.4f}], mean={pc[TP].mean():.4f}")
    if n_fp > 0:
        print(f"    FP p* range:  [{pc[FP].min():.4f}, {pc[FP].max():.4f}], mean={pc[FP].mean():.4f}")
        # How many FP are just barely over the threshold?
        margin = pc[FP] - best_pt
        pct_marginal = (margin < 0.10).mean()
        pct_strong = (margin >= 0.10).mean()
        print(f"    FP margin over threshold: <0.10 = {pct_marginal:.1%}, ≥0.10 = {pct_strong:.1%}")
    
    # ── PATTERN 5: Component agreement (how many components flag each sample) ──
    print(f"\n  ▸ Component agreement (# components > 0.5):")
    high_comp = (comp > 0.5).astype(int).sum(axis=1)
    for g in [0, 1, 2, 3, 4]:
        mask = high_comp == g
        n_in_tp = (mask & TP).sum()
        n_in_fp = (mask & FP).sum()
        n_in_tn = (mask & TN).sum()
        n_in_fn = (mask & FN).sum()
        total_flagged = n_in_tp + n_in_fp
        prec_here = n_in_tp / max(total_flagged, 1)
        print(f"    {g} components high: TP={n_in_tp:>5}, FP={n_in_fp:>5}, precision={prec_here:.3f}")

    # ── Store summary ──
    all_patterns[name] = {
        'n_tp': int(n_tp), 'n_fp': int(n_fp), 'n_tn': int(n_tn), 'n_fn': int(n_fn),
        'mfls_tp_mean': float(mfls[TP].mean()) if n_tp > 0 else 0,
        'mfls_fp_mean': float(mfls[FP].mean()) if n_fp > 0 else 0,
        'mfls_gap': float(mfls[TP].mean() - mfls[FP].mean()) if (n_tp > 0 and n_fp > 0) else 0,
        'fp_base_p_mean': float(p[FP].mean()) if n_fp > 0 else 0,
        'fp_marginal_pct': float((pc[FP] - best_pt < 0.10).mean()) if n_fp > 0 else 0,
        'weights': w.tolist(),
    }


# ══════════════════════════════════════════════════════
# CROSS-DATASET PATTERN SUMMARY
# ══════════════════════════════════════════════════════

print("\n" + "="*80)
print("  CROSS-DATASET FALSE ALARM PATTERNS")
print("="*80)

print(f"\n  {'Dataset':<15} {'FP Count':>8} {'TP Count':>8} {'FA Rate':>8} {'MFLS Gap':>10} {'FP base p':>10} {'FP marginal%':>13}")
for name, pat in all_patterns.items():
    fa_rate = pat['n_fp'] / max(pat['n_fp'] + pat['n_tp'], 1)
    print(f"  {name:<15} {pat['n_fp']:>8} {pat['n_tp']:>8} {fa_rate:>8.1%} {pat['mfls_gap']:>+10.4f} {pat['fp_base_p_mean']:>10.4f} {pat['fp_marginal_pct']:>12.1%}")

print(f"""
────────────────────────────────────────────────────
KEY OBSERVATIONS TO LOOK FOR:
  1. MFLS Gap (TP mean - FP mean): If positive, true fraud has higher MFLS 
     → a HIGHER MFLS threshold could separate them
  2. FP base p: If false alarms have very low base model probability
     → the model is CONFIDENT they're legit → should require STRONGER MFLS to override
  3. FP marginal %: If most FP are barely over the threshold
     → a small threshold increase would eliminate them with minimal recall loss
  4. Component agreement: If FP typically have fewer high components than TP
     → a MINIMUM AGREEMENT FILTER (e.g., ≥2 components high) could help
────────────────────────────────────────────────────
""")
