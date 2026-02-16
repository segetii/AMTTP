"""
False Alarm Pattern Analysis for BSDT — V2
=============================================
Skips the Platt calibration issue. Instead, analyzes the MFLS component
distributions directly to understand WHY false alarms happen and what
patterns could reduce them.

Key question: In MFLS component space, how do fraud and legitimate 
samples differ? Where does the separation fail?
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

preprocessors = joblib.load(ARTIFACTS / 'preprocessors.joblib')
scaler = preprocessors['scaler']
FEATURES_93 = list(preprocessors['feature_names'])
xgb_model = xgb.Booster()
xgb_model.load_model(str(ARTIFACTS / 'xgboost_fraud.ubj'))

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

def build_X_generic(features_df):
    X = np.zeros((len(features_df), 93), dtype=np.float32)
    for i, f in enumerate(FEATURES_93):
        if f in features_df.columns:
            X[:, i] = features_df[f].values.astype(np.float32)
    return X


# ══════════════════════════════════════════════════════
# Load datasets
# ══════════════════════════════════════════════════════
print("Loading datasets...")

datasets = {}

# Credit Card
cc = pd.read_csv(DATA_DIR / 'creditcard' / 'creditcard.csv')
feat = cc.drop(columns=['Class'])
datasets['Credit Card'] = (build_X_generic(feat), cc['Class'].values.astype(np.int32))

# Shuttle
mat = sio.loadmat(DATA_DIR / 'odds' / 'shuttle.mat')
df = pd.DataFrame(np.asarray(mat['X'], dtype=np.float32), columns=[f'V{i}' for i in range(mat['X'].shape[1])])
datasets['Shuttle'] = (build_X_generic(df), np.asarray(mat['y'], dtype=np.int32).ravel())

# Mammography
mat = sio.loadmat(DATA_DIR / 'odds' / 'mammography.mat')
df = pd.DataFrame(np.asarray(mat['X'], dtype=np.float32), columns=[f'V{i}' for i in range(mat['X'].shape[1])])
datasets['Mammography'] = (build_X_generic(df), np.asarray(mat['y'], dtype=np.int32).ravel())

# Pendigits
mat = sio.loadmat(DATA_DIR / 'odds' / 'pendigits.mat')
df = pd.DataFrame(np.asarray(mat['X'], dtype=np.float32), columns=[f'V{i}' for i in range(mat['X'].shape[1])])
datasets['Pendigits'] = (build_X_generic(df), np.asarray(mat['y'], dtype=np.int32).ravel())


# Also load Elliptic (in-domain, where we have real FP/TP data)
ell_dir = DATA_DIR / 'elliptic'
try:
    features = pd.read_csv(ell_dir / 'elliptic_txs_features.csv', header=None)
    classes = pd.read_csv(ell_dir / 'elliptic_txs_classes.csv')
    classes.columns = ['txId', 'class']
    feat_cols = ['txId'] + [f'feat_{i}' for i in range(1, features.shape[1])]
    features.columns = feat_cols
    merged = features.merge(classes, on='txId')
    labelled = merged[merged['class'].isin(['1', '2'])].copy()
    labelled['label'] = (labelled['class'] == '2').astype(np.int32)
    X_e = labelled[[f'feat_{i}' for i in range(1, 167)]].values.astype(np.float32)
    y_e = labelled['label'].values
    # Map to 93 features
    X_ell = np.zeros((len(X_e), 93), dtype=np.float32)
    for i in range(min(93, X_e.shape[1])):
        X_ell[:, i] = X_e[:, i]
    datasets['Elliptic'] = (X_ell, y_e)
    print("  Loaded Elliptic (in-domain)")
except Exception as e:
    print(f"  Could not load Elliptic: {e}")


print(f"\nLoaded {len(datasets)} datasets")

# ══════════════════════════════════════════════════════
# ANALYSIS
# ══════════════════════════════════════════════════════

print("\n" + "="*80)
print("  MFLS COMPONENT DISTRIBUTION ANALYSIS: FRAUD vs LEGITIMATE")
print("="*80)

comp_names = ['C (Camouflage)', 'G (Feature Gap)', 'A (Activity)', 'T (Temporal)']

all_results = {}

for name, (X, y) in datasets.items():
    print(f"\n{'─'*70}")
    print(f"  {name} — n={len(y)}, fraud={y.sum()}, rate={y.mean():.4f}")
    print(f"{'─'*70}")
    
    # Compute reference stats and components
    s = ref_stats(X, y)
    comp = get_components(X, *s)
    
    fraud = y == 1
    legit = y == 0
    
    # MI weights
    w, _ = mi_weights(comp, y)
    mfls = comp @ w
    
    print(f"\n  MI Weights: C={w[0]:.3f}, G={w[1]:.3f}, A={w[2]:.3f}, T={w[3]:.3f}")
    
    # ── 1. Component distributions ──
    print(f"\n  ▸ Component distributions (Fraud vs Legit):")
    print(f"    {'Component':<20} {'Fraud mean':>10} {'Legit mean':>10} {'Gap':>8} {'Fraud std':>10} {'Legit std':>10}")
    for i, cn in enumerate(comp_names):
        fm = comp[fraud, i].mean()
        lm = comp[legit, i].mean()
        fs = comp[fraud, i].std()
        ls = comp[legit, i].std()
        print(f"    {cn:<20} {fm:10.4f} {lm:10.4f} {fm-lm:+8.4f} {fs:10.4f} {ls:10.4f}")
    
    # ── 2. MFLS distribution ──
    print(f"\n  ▸ MFLS composite score:")
    print(f"    Fraud:  mean={mfls[fraud].mean():.4f}, std={mfls[fraud].std():.4f}, "
          f"P10={np.percentile(mfls[fraud], 10):.4f}, P50={np.percentile(mfls[fraud], 50):.4f}, P90={np.percentile(mfls[fraud], 90):.4f}")
    print(f"    Legit:  mean={mfls[legit].mean():.4f}, std={mfls[legit].std():.4f}, "
          f"P10={np.percentile(mfls[legit], 10):.4f}, P50={np.percentile(mfls[legit], 50):.4f}, P90={np.percentile(mfls[legit], 90):.4f}")
    
    # ── 3. OVERLAP ZONE: legit samples with high MFLS ──
    # These are the samples that WOULD become false alarms
    mfls_auc = roc_auc_score(y, mfls)
    print(f"\n  ▸ MFLS AUC (fraud vs legit): {mfls_auc:.4f}")
    
    # Find optimal MFLS threshold
    thresholds = np.percentile(mfls, np.arange(1, 100))
    best_f1_mfls = 0
    best_th_mfls = 0.5
    for th in thresholds:
        pred = (mfls >= th).astype(np.int32)
        f1 = f1_score(y, pred, zero_division=0)
        if f1 > best_f1_mfls:
            best_f1_mfls = f1
            best_th_mfls = th
    
    pred_mfls = (mfls >= best_th_mfls).astype(np.int32)
    tp_m = ((pred_mfls == 1) & fraud).sum()
    fp_m = ((pred_mfls == 1) & legit).sum()
    fn_m = ((pred_mfls == 0) & fraud).sum()
    rec_m = tp_m / max(tp_m + fn_m, 1)
    pre_m = tp_m / max(tp_m + fp_m, 1)
    
    print(f"  ▸ Best MFLS-only threshold: {best_th_mfls:.4f}")
    print(f"    TP={tp_m}, FP={fp_m}, FN={fn_m}")
    print(f"    Recall={rec_m:.3f}, Precision={pre_m:.3f}, F1={best_f1_mfls:.3f}")
    print(f"    False Alarm Rate: {fp_m/(fp_m+tp_m):.1%}")
    
    # ── 4. FALSE ALARM COMPONENT PROFILE ──
    fp_mask = (pred_mfls == 1) & legit
    tp_mask = (pred_mfls == 1) & fraud
    
    if fp_m > 0 and tp_m > 0:
        print(f"\n  ▸ Component profile: FALSE ALARMS vs TRUE CATCHES")
        print(f"    {'Component':<20} {'TP mean':>8} {'FP mean':>8} {'Diff':>8} {'Separable?':>10}")
        for i, cn in enumerate(comp_names):
            tp_v = comp[tp_mask, i].mean()
            fp_v = comp[fp_mask, i].mean()
            diff = tp_v - fp_v
            separable = 'YES' if abs(diff) > 0.05 else 'marginal' if abs(diff) > 0.02 else 'no'
            print(f"    {cn:<20} {tp_v:8.4f} {fp_v:8.4f} {diff:+8.4f} {separable:>10}")
    
    # ── 5. COMPONENT AGREEMENT ANALYSIS ──
    # Key question: Do true fraud samples trigger MORE components simultaneously?
    high_comp = (comp > 0.5).astype(int).sum(axis=1)
    
    print(f"\n  ▸ # of components > 0.5 (agreement analysis):")
    print(f"    {'# high':<8} {'Fraud %':>8} {'Legit %':>8} {'Fraud n':>8} {'Legit n':>8} {'Purity':>8}")
    for g in range(5):
        mask = high_comp == g
        nf = (mask & fraud).sum()
        nl = (mask & legit).sum()
        total = nf + nl
        purity = nf / max(total, 1)
        pf = nf / max(fraud.sum(), 1) * 100
        pl = nl / max(legit.sum(), 1) * 100
        print(f"    {g:<8} {pf:7.1f}% {pl:7.1f}% {nf:>8} {nl:>8} {purity:7.3f}")
    
    # ── 6. WHAT IF: Multi-component agreement filter ──
    # Only flag if MFLS > threshold AND ≥2 components > 0.5
    print(f"\n  ▸ IMPROVEMENT: MFLS + agreement filter (≥N components > 0.5):")
    for min_agree in [1, 2, 3]:
        combined_pred = ((mfls >= best_th_mfls) & (high_comp >= min_agree)).astype(np.int32)
        tp_c = ((combined_pred == 1) & fraud).sum()
        fp_c = ((combined_pred == 1) & legit).sum()
        fn_c = ((combined_pred == 0) & fraud).sum()
        rec_c = tp_c / max(tp_c + fn_c, 1)
        pre_c = tp_c / max(tp_c + fp_c, 1)
        f1_c = f1_score(y, combined_pred, zero_division=0)
        fa_c = fp_c / max(fp_c + tp_c, 1)
        print(f"    ≥{min_agree} agree: TP={tp_c:>5}, FP={fp_c:>5}, Recall={rec_c:.3f}, Precision={pre_c:.3f}, F1={f1_c:.3f}, FA={fa_c:.1%}")

    # ── 7. WHAT IF: Weighted MFLS with confidence penalty ──
    # p*(x) = p(x) + λ·MFLS(x)·(1-p(x))·𝟙[p(x)<τ]
    # New idea: add penalty based on model CONFIDENCE that it's legit
    # If model is VERY confident (p very low), require higher MFLS
    # Effectively: require MFLS > α / (1 - p(x)) instead of flat threshold
    print(f"\n  ▸ IMPROVEMENT: Adaptive MFLS threshold (require higher MFLS when model is confident):")
    # Simulate: use MFLS percentile ranking as the "corrected" score
    # and add a penalty: effective_mfls = mfls - β * (1 - mfls_rank_among_similar_p)
    
    # Simple version: MFLS * component_agreement_score
    agreement_weight = high_comp / 4.0  # 0 to 1
    enhanced_mfls = mfls * (0.5 + 0.5 * agreement_weight)  # weight by agreement
    enhanced_auc = roc_auc_score(y, enhanced_mfls)
    
    # Find best threshold for enhanced MFLS
    thresholds_e = np.percentile(enhanced_mfls, np.arange(1, 100))
    best_f1_e = 0
    best_th_e = 0.5
    for th in thresholds_e:
        pred = (enhanced_mfls >= th).astype(np.int32)
        f1 = f1_score(y, pred, zero_division=0)
        if f1 > best_f1_e:
            best_f1_e = f1
            best_th_e = th
    
    pred_e = (enhanced_mfls >= best_th_e).astype(np.int32)
    tp_e = ((pred_e == 1) & fraud).sum()
    fp_e = ((pred_e == 1) & legit).sum()
    fn_e = ((pred_e == 0) & fraud).sum()
    rec_e = tp_e / max(tp_e + fn_e, 1)
    pre_e = tp_e / max(tp_e + fp_e, 1)
    fa_e = fp_e / max(fp_e + tp_e, 1)
    
    print(f"    Enhanced MFLS AUC: {enhanced_auc:.4f} (was {mfls_auc:.4f})")
    print(f"    TP={tp_e}, FP={fp_e}, Recall={rec_e:.3f}, Precision={pre_e:.3f}, F1={best_f1_e:.3f}, FA={fa_e:.1%}")
    
    all_results[name] = {
        'mfls_auc': mfls_auc,
        'enhanced_auc': enhanced_auc,
        'mfls_only': {'tp': tp_m, 'fp': fp_m, 'recall': rec_m, 'precision': pre_m, 'f1': best_f1_mfls},
        'enhanced': {'tp': int(tp_e), 'fp': int(fp_e), 'recall': rec_e, 'precision': pre_e, 'f1': best_f1_e},
        'weights': w.tolist(),
        'fraud_mfls_mean': float(mfls[fraud].mean()),
        'legit_mfls_mean': float(mfls[legit].mean()),
    }

# ══════════════════════════════════════════════════════
# GRAND SUMMARY
# ══════════════════════════════════════════════════════

print("\n" + "="*80)
print("  GRAND SUMMARY: CURRENT vs IMPROVED")
print("="*80)

print(f"\n  {'Dataset':<15} {'MFLS AUC':>9} {'Enh AUC':>9} │ {'Cur Prec':>9} {'Enh Prec':>9} {'Cur FA%':>8} {'Enh FA%':>8} │ {'Cur Rec':>8} {'Enh Rec':>8}")
print(f"  {'─'*13}   {'─'*9} {'─'*9} │ {'─'*9} {'─'*9} {'─'*8} {'─'*8} │ {'─'*8} {'─'*8}")
for name, r in all_results.items():
    cur = r['mfls_only']
    enh = r['enhanced']
    cur_fa = cur['fp'] / max(cur['fp'] + cur['tp'], 1)
    enh_fa = enh['fp'] / max(enh['fp'] + enh['tp'], 1)
    print(f"  {name:<15} {r['mfls_auc']:9.4f} {r['enhanced_auc']:9.4f} │ {cur['precision']:9.3f} {enh['precision']:9.3f} {cur_fa:7.1%} {enh_fa:7.1%} │ {cur['recall']:7.3f} {enh['recall']:7.3f}")

# Save results
with open(Path(r'c:\amttp\papers\false_alarm_analysis.json'), 'w') as f:
    json.dump(all_results, f, indent=2)
print(f"\nResults saved to papers/false_alarm_analysis.json")
