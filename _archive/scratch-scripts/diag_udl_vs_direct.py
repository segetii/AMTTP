"""
diag_udl_vs_direct.py - diagnose why UDL drops signal for ERCOT
Compare:
  A) Direct Mahalanobis on raw+deviation features
  B) UDL projection + FrozenWindow
"""
import sys, os, warnings
sys.path.insert(0, r'c:\amttp\research\udl')
sys.path.insert(0, r'c:\amttp\research\adaptive-friction\banklevel_enhanced')
os.environ['CUDA_VISIBLE_DEVICES'] = ''
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

import numpy as np
from pathlib import Path
from sklearn.metrics import roc_auc_score
from sklearn.covariance import EmpiricalCovariance, MinCovDet

ERCOT_NPZ = Path(r'c:\amttp\data\ercot\ercot_daily_2018_2022.npz')

def rolling_deviation(X, window=30):
    T, d = X.shape
    X_dev = np.zeros_like(X)
    for col in range(d):
        for i in range(T):
            start = max(0, i - window)
            chunk = X[start:i, col]
            chunk = chunk[~np.isnan(chunk)]
            if len(chunk) >= 5:
                mu = chunk.mean()
                sd = chunk.std() + 1e-9
                X_dev[i, col] = (X[i, col] - mu) / sd if not np.isnan(X[i, col]) else 0.0
    return X_dev

# ── Load features ────────────────────────────────────────────────────────────
npz    = np.load(ERCOT_NPZ, allow_pickle=True)
X_raw  = npz['X'].astype(np.float64)
y_raw  = npz['y'].astype(int)
dates  = npz['dates']
labels = npz['labels']

# Forward-fill NaNs
for col in range(X_raw.shape[1]):
    last_v = np.nanmean(X_raw[:, col]) if not np.all(np.isnan(X_raw[:, col])) else 0.0
    for i in range(len(X_raw)):
        if np.isnan(X_raw[i, col]):
            X_raw[i, col] = last_v
        else:
            last_v = X_raw[i, col]

X_dev = rolling_deviation(X_raw, window=30)

# Standardise on training normals
test_day  = np.array([str(d)[:10] >= '2020-01-01' for d in dates])
train_day = ~test_day
norm_mask = train_day & (y_raw == 0)
mu_r = X_raw[norm_mask].mean(0); sd_r = X_raw[norm_mask].std(0) + 1e-9
X_abs = np.nan_to_num(np.clip((X_raw - mu_r) / sd_r, -8, 8))
X_comb = np.hstack([X_abs, X_dev])  # 12-dim

X_train = X_comb[train_day]; y_train = y_raw[train_day]
X_test  = X_comb[test_day];  y_test  = y_raw[test_day]

print("=" * 70)
print("  ERCOT ANOMALY DETECTION — METHOD COMPARISON")
print("=" * 70)
print(f"  Train: {len(X_train):,} days (normals={int((y_train==0).sum())})")
print(f"  Test:  {len(X_test):,} days (anomalies={int(y_test.sum())})")
print()

# ── A: Direct Mahalanobis on raw 12 features ────────────────────────────────
X_norm_train = X_train[y_train == 0]
try:
    cov = MinCovDet(support_fraction=0.9).fit(X_norm_train)
    scores_mah = cov.mahalanobis(X_test) ** 0.5
except Exception:
    cov = EmpiricalCovariance().fit(X_norm_train)
    scores_mah = cov.mahalanobis(X_test) ** 0.5
auc_mah = roc_auc_score(y_test, scores_mah)
print(f"  [A] Direct MCD Mahalanobis (12 features): AUC = {auc_mah:.4f}")

# ── B: Individual feature z-score (max abs deviation) ───────────────────────
# Use temp and load_std deviation features specifically
# feat 4 = temp_f (index in abs), feat 1 = load_std
scores_t = -X_abs[:, 4]              # lower temp = anomaly
scores_l = -X_abs[:, 0]              # lower mean load = anomaly (COVID)
scores_d = np.abs(X_dev[:, 4]) + np.abs(X_dev[:, 1]) + np.abs(X_dev[:, 5])
test_scores_t = scores_t[test_day]
test_scores_l = scores_l[test_day]
test_scores_d = scores_d[test_day]
auc_t = roc_auc_score(y_test, test_scores_t)
auc_l = roc_auc_score(y_test, test_scores_l)
auc_d = roc_auc_score(y_test, test_scores_d)
print(f"  [B] -temp_f (low temp = anomaly):         AUC = {auc_t:.4f}")
print(f"  [B] -load_mean (low load = anomaly):      AUC = {auc_l:.4f}")
print(f"  [B] |dev sum| (temp+std+ixn devs):        AUC = {auc_d:.4f}")

# ── C: UDL projection + Mahalanobis ─────────────────────────────────────────
from udl.system_mode import UDLPostSimScorer
X_norm2 = X_train[y_train == 0]
scorer = UDLPostSimScorer(k=min(15, len(X_norm2)-1), max_dim=12, n_components=min(10,len(X_norm2)-1))
scorer.fit(X_norm2)
Z_train = scorer.transform(X_train)
Z_test  = scorer.transform(X_test)
Z_norm  = Z_train[y_train == 0]
try:
    cov2 = MinCovDet(support_fraction=0.9).fit(Z_norm)
    scores_udl_mah = cov2.mahalanobis(Z_test) ** 0.5
except Exception:
    cov2 = EmpiricalCovariance().fit(Z_norm)
    scores_udl_mah = cov2.mahalanobis(Z_test) ** 0.5
auc_udl_mah = roc_auc_score(y_test, scores_udl_mah)
print(f"  [C] UDL(22-dim) + MCD Mahalanobis:        AUC = {auc_udl_mah:.4f}")

# ── D: UDL + FrozenWindow ────────────────────────────────────────────────────
from geo_full_pipeline import FrozenWindowScorer
fw = FrozenWindowScorer()
fw.fit(Z_norm)
scores_fw = fw.score(Z_test)
auc_fw = roc_auc_score(y_test, scores_fw)
print(f"  [D] UDL(22-dim) + FrozenWindow:           AUC = {auc_fw:.4f}")

# ── E: UDL + FW SignedLR (supervised) ───────────────────────────────────────
fw.fit_signed_lr(Z_train, y_train)
scores_lr = fw.score_signed_lr(Z_test)
auc_lr = roc_auc_score(y_test, scores_lr)
print(f"  [E] UDL(22-dim) + FW+SignedLR(sup):       AUC = {auc_lr:.4f}")

# Best overall
best_auc = max(auc_mah, auc_t, auc_l, auc_d, auc_udl_mah, auc_fw, auc_lr)
print(f"\n  Best AUC: {best_auc:.4f}")

# ── Per-event breakdown for method A and best ────────────────────────────────
test_labels = labels[test_day]
methods = {
    'MCD-Mahal': scores_mah,
    'DevSum':    test_scores_d,
    'UDL+FW':    scores_fw,
    'UDL+LR':    scores_lr,
}
print(f"\n  Per-event AUC:")
print(f"  {'Event':<26} {'MCD-Mah':>9} {'DevSum':>9} {'UDL+FW':>9} {'UDL+LR':>9}")
print(f"  {'-'*62}")
for evt in ['WinterStormUri', 'COVID_Collapse', 'WinterStormElliott']:
    evt_mask = test_labels == evt
    if not evt_mask.any():
        continue
    # Per-event AUC: anomaly class = this event, normal = all Normal days
    norm_mask2 = test_labels == 'Normal'
    combined_mask = evt_mask | norm_mask2
    aucs = []
    for nm, sc in methods.items():
        try:
            a = roc_auc_score(y_test[combined_mask], sc[combined_mask])
        except Exception:
            a = 0.5
        aucs.append(a)
    print(f"  {evt:<26} {aucs[0]:9.4f} {aucs[1]:9.4f} {aucs[2]:9.4f} {aucs[3]:9.4f}")
