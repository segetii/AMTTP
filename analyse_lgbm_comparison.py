"""
Comprehensive comparison: Did LGBM work? What alternatives are better?
Loads all saved benchmark results and compares approaches.
Uses same feature extraction as test_bank_lgbm.py for consistency.
"""
import json, numpy as np, sys, os, pandas as pd
sys.path.insert(0, 'research/udl')

from udl.system_mode import (ReducedTensorDescriptor, MorseTopologyAlarm,
                              BettiBarcodeSuite, BSDTChannels)
from sklearn.preprocessing import StandardScaler

CACHE_DIR = 'research/adaptive-friction/banklevel_enhanced/gsib_cache_real'

CRISIS_QUARTERS = {
    '2007-12-31', '2008-03-31', '2008-06-30', '2008-09-30',
    '2008-12-31', '2009-03-31', '2009-06-30',
    '2011-09-30', '2011-12-31', '2012-03-31', '2012-06-30',
    '2020-03-31', '2020-06-30',
}

print("="*90)
print("  DID LGBM WORK?  Comprehensive Algorithm Comparison for Banking Early Warning")
print("="*90)

# ─── Load bank data (same as test_bank_lgbm.py) ─────────────────────
npz = np.load(os.path.join(CACHE_DIR, 'gsib_real_panel.npz'))
X_3d = npz['X']  # (T, N, d)

with open(os.path.join(CACHE_DIR, 'gsib_real_meta.json'), encoding='utf-8') as f:
    meta = json.load(f)

N_meta = len(meta)
if X_3d.shape[1] > N_meta:
    X_3d = X_3d[:, :N_meta, :]

T, N, d = X_3d.shape
dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:T]
y_crisis = np.array([1 if str(d.date()) in CRISIS_QUARTERS else 0 for d in dates], dtype=int)
qlabels = [f"{d.year}-Q{d.quarter}" for d in dates]

BURN_IN = 11  # calibration (2005-Q1 to 2007-Q3)
print(f"\n  Data: T={T} quarters, N={N} banks, d={d} features")
print(f"  Crisis quarters: {int(np.sum(y_crisis))} / {T}")
print(f"  Calibration: {BURN_IN} quarters, Monitor: {T - BURN_IN}")

# ─── Feature extraction per quarter (expanding window) ──────────────
print("\n  Extracting topology features per quarter (expanding window)...")

quarter_features = {}

for t in range(BURN_IN, T):
    X_train = X_3d[:t].reshape(-1, d)
    X_test  = X_3d[t]  # (N, d)

    scaler = StandardScaler()
    X_tr = scaler.fit_transform(X_train)
    X_te = scaler.transform(X_test)

    k = min(15, len(X_tr) - 1)
    views = []

    # ReducedTensor (11D via transform)
    rt = ReducedTensorDescriptor(k_neighbors=k)
    rt.fit(X_tr)
    rt_feat = rt.transform(X_te)  # (N, 11)
    views.append(np.nanmean(rt_feat, axis=0))  # (11,)

    # BSDT (6D: 4 channels + energy + mfls)
    bsdt = BSDTChannels()
    bsdt.fit(X_tr)
    ch = bsdt.channels(X_te)
    C = np.column_stack([ch['delta_C'], ch['delta_G'], ch['delta_A'], ch['delta_T']])
    E = bsdt.energy(X_te)[:, None]
    M = bsdt.mfls(X_te)[:, None]
    bsdt_feat = np.column_stack([C, E, M])
    views.append(np.nanmean(bsdt_feat, axis=0))  # (6,)

    # Betti (19D)
    betti = BettiBarcodeSuite(k=min(k+5, 25), n_scales=8)
    betti.fit(X_tr)
    b_raw = betti._compute_features(X_te, betti._X_ref)
    views.append(np.nanmean(b_raw, axis=0))  # (19,)

    feat = np.concatenate(views)  # 11+6+19 = 36D
    quarter_features[t] = feat

    if t % 10 == 0 or t == T-1:
        print(f"    t={t} ({qlabels[t]}) features={feat.shape[0]}D")

# ─── Now test multiple algorithms ───────────────────────────────────
from sklearn.ensemble import (RandomForestClassifier, GradientBoostingClassifier,
                               AdaBoostClassifier, ExtraTreesClassifier)
from sklearn.svm import SVC
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import roc_auc_score, f1_score
from sklearn.exceptions import ConvergenceWarning
import warnings
warnings.filterwarnings('ignore', category=ConvergenceWarning)

# Feature subsets (RT=0:11, BSDT=11:17, Betti=17:36)
FEAT_SLICES = {
    'RT_only':      slice(0, 11),     # ReducedTensor 11D
    'BSDT_only':    slice(11, 17),    # BSDT 6D
    'RT+BSDT':      None,             # [0:17] = 17D
    'ALL_36D':      slice(0, 36),     # everything
    'Betti_only':   slice(17, 36),    # Betti 19D
    'RT+Betti':     None,             # [0:11]+[17:36] = 30D
    'BSDT+Betti':   slice(11, 36),   # BSDT+Betti = 25D
}

algorithms = {
    'LGBM':              None,  # handled separately (needs lightgbm)
    'RandomForest':      RandomForestClassifier(n_estimators=100, max_depth=4, random_state=42, class_weight='balanced'),
    'GradientBoosting':  GradientBoostingClassifier(n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42),
    'ExtraTrees':        ExtraTreesClassifier(n_estimators=100, max_depth=4, random_state=42, class_weight='balanced'),
    'AdaBoost':          AdaBoostClassifier(n_estimators=50, random_state=42),
    'SVM_RBF':           SVC(kernel='rbf', probability=True, class_weight='balanced', random_state=42),
    'LogisticReg':       LogisticRegression(max_iter=1000, class_weight='balanced', random_state=42),
    'KNN_5':             KNeighborsClassifier(n_neighbors=5),
    'KNN_3':             KNeighborsClassifier(n_neighbors=3),
    'MLP':               MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=500, random_state=42),
}

try:
    from lightgbm import LGBMClassifier
    algorithms['LGBM'] = LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.1, 
                                         random_state=42, verbose=-1, is_unbalance=True)
except:
    pass

print("\n  Running expanding-window evaluation for all algorithms...")
print(f"  {len(algorithms)} algorithms x {len(FEAT_SLICES)} feature sets = {len(algorithms)*len(FEAT_SLICES)} configs\n")

# GFC / EU / COVID quarter indices
GFC_Q = set(range(11, 18))
EU_Q  = set(range(26, 30))
COV_Q = set(range(60, 62))

results = {}

for feat_name, feat_slice in FEAT_SLICES.items():
    for algo_name, clf_template in algorithms.items():
        if clf_template is None:
            continue
            
        # Build feature matrix and labels using expanding window
        q_scores = np.full(T, np.nan)
        
        for t in range(BURN_IN, T):
            # Build training set from all past quarters
            X_list = []
            y_list = []
            for s in range(BURN_IN, t):
                if s in quarter_features:
                    X_list.append(quarter_features[s])
                    y_list.append(y_crisis[s])
            
            if len(X_list) < 4 or sum(y_list) < 1 or sum(y_list) == len(y_list):
                continue  # need at least some of each class
            
            X_tr = np.array(X_list)
            y_tr = np.array(y_list)
            
            # Select features
            if feat_name == 'RT+BSDT':
                X_tr_f = X_tr[:, :17]  # RT(11) + BSDT(6)
                x_te_f = quarter_features[t][:17].reshape(1, -1)
            elif feat_name == 'RT+Betti':
                X_tr_f = np.column_stack([X_tr[:, :11], X_tr[:, 17:36]])
                x_test_full = quarter_features[t]
                x_te_f = np.concatenate([x_test_full[:11], x_test_full[17:36]]).reshape(1, -1)
            else:
                X_tr_f = X_tr[:, feat_slice]
                x_te_f = quarter_features[t][feat_slice].reshape(1, -1)
            
            # Handle NaN
            X_tr_f = np.nan_to_num(X_tr_f, nan=0.0)
            x_te_f = np.nan_to_num(x_te_f, nan=0.0)
            
            # Clone and fit
            from sklearn.base import clone
            clf = clone(clf_template)
            try:
                clf.fit(X_tr_f, y_tr)
                prob = clf.predict_proba(x_te_f)[0]
                q_scores[t] = prob[1] if len(prob) > 1 else prob[0]
            except Exception:
                continue
        
        # Compute metrics
        valid = ~np.isnan(q_scores)
        valid_monitor = valid.copy()
        valid_monitor[:BURN_IN] = False
        
        if np.sum(valid_monitor) < 10:
            continue
            
        y_valid = y_crisis[valid_monitor]
        s_valid = q_scores[valid_monitor]
        
        try:
            auc = roc_auc_score(y_valid, s_valid)
        except:
            auc = 0.5
        
        # GFC-specific AUC
        gfc_mask = np.zeros(T, dtype=bool)
        gfc_mask[list(GFC_Q)] = True
        # include some normals around GFC for AUC computation
        for t_idx in range(BURN_IN, 25):
            gfc_mask[t_idx] = True
        gfc_valid = gfc_mask & valid_monitor
        if np.sum(gfc_valid) > 5:
            try:
                gfc_auc = roc_auc_score(y_crisis[gfc_valid], q_scores[gfc_valid])
            except:
                gfc_auc = 0.5
        else:
            gfc_auc = 0.5
        
        # F1 at optimal threshold
        thresholds = np.linspace(0, 1, 50)
        best_f1 = 0
        for thr in thresholds:
            preds = (s_valid >= thr).astype(int)
            f1 = f1_score(y_valid, preds, zero_division=0)
            if f1 > best_f1:
                best_f1 = f1
        
        # FAR at 3-sigma
        calib = q_scores[BURN_IN:BURN_IN+4]
        calib_v = calib[~np.isnan(calib)]
        if len(calib_v) >= 2:
            mu, sig = np.mean(calib_v), np.std(calib_v)
            thr_3s = mu + 3 * max(sig, 1e-6)
            normal_idx = [t for t in range(BURN_IN, T) if valid_monitor[t] and y_crisis[t] == 0]
            if len(normal_idx) > 0:
                far = np.mean([q_scores[t] > thr_3s for t in normal_idx]) * 100
            else:
                far = 0
        else:
            far = 0
        
        # GFC early detection
        gfc_det = sum(1 for t in GFC_Q if valid_monitor[t] and q_scores[t] > (mu + 2*max(sig,1e-6)))
        
        # Pre-GFC alarm (lead time)
        lead_q = None
        for t in range(BURN_IN, 11):
            if valid_monitor[t] and q_scores[t] > (mu + 2*max(sig,1e-6)):
                lead_q = t
                break
        
        config_name = f"{algo_name}/{feat_name}"
        results[config_name] = {
            'auc': auc, 'gfc_auc': gfc_auc, 'best_f1': best_f1, 
            'far': far, 'gfc_det': gfc_det, 'lead_q': lead_q
        }

# ─── Sort and display ───────────────────────────────────────────────
print("\n" + "="*90)
print("  RESULTS: All Algorithms x Feature Sets (sorted by AUC)")
print("="*90)
print(f"  {'Config':<35} {'AUC':>6} {'GFC-AUC':>8} {'F1':>6} {'FAR%':>6} {'GFC':>4} {'LeadQ':>6}")
print("  " + "─"*80)

sorted_results = sorted(results.items(), key=lambda x: x[1]['auc'], reverse=True)
for name, m in sorted_results[:30]:
    lead_str = qlabels[m['lead_q']] if m['lead_q'] is not None else "—"
    print(f"  {name:<35} {m['auc']:>6.4f} {m['gfc_auc']:>8.4f} {m['best_f1']:>6.3f} {m['far']:>5.1f}% {m['gfc_det']:>3}/7 {lead_str:>8}")

# ─── Best per algorithm ─────────────────────────────────────────────
print("\n" + "="*90)
print("  BEST CONFIG PER ALGORITHM (sorted by AUC)")
print("="*90)
algo_best = {}
for name, m in results.items():
    algo = name.split('/')[0]
    if algo not in algo_best or m['auc'] > algo_best[algo][1]['auc']:
        algo_best[algo] = (name, m)

for algo, (name, m) in sorted(algo_best.items(), key=lambda x: x[1][1]['auc'], reverse=True):
    lead_str = qlabels[m['lead_q']] if m['lead_q'] is not None else "—"
    feat = name.split('/')[1]
    print(f"  {algo:<20} best feat={feat:<12} AUC={m['auc']:.4f}  GFC-AUC={m['gfc_auc']:.4f}  F1={m['best_f1']:.3f}  FAR={m['far']:.1f}%  GFC={m['gfc_det']}/7  Lead={lead_str}")

# ─── Best per feature set ───────────────────────────────────────────
print("\n" + "="*90)
print("  BEST CONFIG PER FEATURE SET (sorted by AUC)")
print("="*90)
feat_best = {}
for name, m in results.items():
    feat = name.split('/')[1]
    if feat not in feat_best or m['auc'] > feat_best[feat][1]['auc']:
        feat_best[feat] = (name, m)

for feat, (name, m) in sorted(feat_best.items(), key=lambda x: x[1][1]['auc'], reverse=True):
    algo = name.split('/')[0]
    lead_str = qlabels[m['lead_q']] if m['lead_q'] is not None else "—"
    print(f"  {feat:<15} best algo={algo:<20} AUC={m['auc']:.4f}  GFC-AUC={m['gfc_auc']:.4f}  F1={m['best_f1']:.3f}")

# ─── Final verdict ──────────────────────────────────────────────────
print("\n" + "="*90)
print("  VERDICT: Did LGBM work?")
print("="*90)

# Find LGBM best
lgbm_best_name, lgbm_best = algo_best.get('LGBM', (None, None))
overall_best_name, overall_best = sorted_results[0]

print(f"\n  LGBM best:    {lgbm_best_name}  AUC={lgbm_best['auc']:.4f}" if lgbm_best else "  LGBM: not tested")
print(f"  Overall best:  {overall_best_name}  AUC={overall_best['auc']:.4f}")

if lgbm_best:
    diff = overall_best['auc'] - lgbm_best['auc']
    if diff < 0.02:
        print(f"\n  → LGBM is competitive (within {diff:.4f} of best)")
    elif diff < 0.05:
        print(f"\n  → LGBM is slightly worse than {overall_best_name.split('/')[0]} (Δ={diff:.4f})")
    else:
        print(f"\n  → LGBM is significantly outperformed by {overall_best_name.split('/')[0]} (Δ={diff:.4f})")

# Save
results_save = {
    'all_results': {k: v for k, v in results.items()},
    'algo_best': {k: {'config': v[0], 'metrics': v[1]} for k, v in algo_best.items()},
    'feat_best': {k: {'config': v[0], 'metrics': v[1]} for k, v in feat_best.items()},
}
with open('results/algorithm_comparison.json', 'w') as f:
    json.dump(results_save, f, indent=2, default=str)
print(f"\n  Saved → results/algorithm_comparison.json")
