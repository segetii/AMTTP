"""Molecular FAR analysis: threshold sweep + FAR-targeted calibration."""
import sys, os, time, warnings, json, gc
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'research', 'udl'))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from udl.system_mode import MolecularEngine

warnings.filterwarnings("ignore")

ROOT = r'C:\amttp'
CACHE_DIR = os.path.join(ROOT, 'research', 'adaptive-friction',
                         'banklevel_enhanced', 'gsib_cache_real')
npz = np.load(os.path.join(CACHE_DIR, 'gsib_real_panel.npz'))
X_3d = npz['X']
with open(os.path.join(CACHE_DIR, 'gsib_real_meta.json')) as f:
    meta = json.load(f)

dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:X_3d.shape[0]]
T, N, d = X_3d.shape

CRISIS_QUARTERS = {
    '2007-12-31','2008-03-31','2008-06-30','2008-09-30',
    '2008-12-31','2009-03-31','2009-06-30',
    '2020-03-31','2020-06-30',
    '2011-09-30','2011-12-31','2012-03-31','2012-06-30',
}
y_crisis = np.array([1 if str(d.date()) in CRISIS_QUARTERS else 0 for d in dates])

print(f'Panel: T={T}, N={N}, d={d}')
print(f'Crisis quarters: {int(y_crisis.sum())}/{T}')

# ── Run molecular once, collect all quarter scores ──
print('\nRunning MolecularEngine (expanding window)...')
calib_end = pd.Timestamp('2007-09-30')
n_calib = int((dates <= calib_end).sum())
q_scores = np.full(T, np.nan)
kwargs = dict(iterations=80, k_neighbors=10, max_samples=2000)

t0 = time.time()

# Calibration period
X_calib = X_3d[:n_calib].reshape(n_calib * N, d)
y_calib = np.zeros(n_calib * N, dtype=int)
for t_idx in range(n_calib):
    if str(dates[t_idx].date()) in CRISIS_QUARTERS:
        y_calib[t_idx*N:(t_idx+1)*N] = 1
eng = MolecularEngine(**kwargs)
scores_calib = eng.fit_score(X_calib, y_calib)
for t in range(n_calib):
    q_scores[t] = scores_calib[t*N:(t+1)*N].mean()
del eng, scores_calib, X_calib, y_calib
gc.collect()

# Expanding window
for t in range(n_calib, T):
    n_pts = (t + 1) * N
    X_up = X_3d[:t+1].reshape(n_pts, d)
    y_up = np.zeros(n_pts, dtype=int)
    for t_idx in range(t + 1):
        if str(dates[t_idx].date()) in CRISIS_QUARTERS:
            y_up[t_idx*N:(t_idx+1)*N] = 1
    eng = MolecularEngine(**kwargs)
    scores_all = eng.fit_score(X_up, y_up)
    q_scores[t] = scores_all[-N:].mean()
    del eng, scores_all, X_up, y_up
    gc.collect()

elapsed = time.time() - t0
print(f'Simulation done in {elapsed:.0f}s')

valid = ~np.isnan(q_scores)
q_valid = q_scores[valid]
y_valid = y_crisis[valid]
auroc = roc_auc_score(y_valid, q_valid)
print(f'AUROC: {auroc:.4f}')

# ── Score distribution analysis ──
calib_scores = q_scores[:n_calib]
calib_scores = calib_scores[~np.isnan(calib_scores)]

print(f'\n{"="*70}')
print(f'  Calibration-period score distribution (n={len(calib_scores)})')
print(f'{"="*70}')
for p in [90, 95, 97, 98, 99, 99.5]:
    v = np.percentile(calib_scores, p)
    print(f'  P{p:5.1f}: {v:.4f}')

# ── Threshold sweep ──
print(f'\n{"="*70}')
print(f'  Threshold sweep (calibration percentile)')
print(f'{"="*70}')
print(f'  {"Pctl":>6s}  {"Thresh":>8s}  {"TP":>3s}  {"FP":>3s}  {"FN":>3s}  {"TN":>3s}  {"FAR%":>6s}  {"Recall%":>8s}  {"Prec%":>6s}')
print(f'  {"-"*6}  {"-"*8}  {"-"*3}  {"-"*3}  {"-"*3}  {"-"*3}  {"-"*6}  {"-"*8}  {"-"*6}')

for pctl in [90, 92, 94, 95, 96, 97, 97.5, 98, 98.5, 99, 99.5]:
    threshold = np.percentile(calib_scores, pctl)
    y_pred = (q_valid >= threshold).astype(int)
    TP = int(((y_pred == 1) & (y_valid == 1)).sum())
    FP = int(((y_pred == 1) & (y_valid == 0)).sum())
    FN = int(((y_pred == 0) & (y_valid == 1)).sum())
    TN = int(((y_pred == 0) & (y_valid == 0)).sum())
    n_normal = TN + FP
    far = FP / n_normal * 100 if n_normal > 0 else 0
    recall = TP / (TP + FN) * 100 if (TP + FN) > 0 else 0
    prec = TP / (TP + FP) * 100 if (TP + FP) > 0 else 0
    print(f'  {pctl:6.1f}  {threshold:8.4f}  {TP:3d}  {FP:3d}  {FN:3d}  {TN:3d}  {far:5.1f}%  {recall:7.1f}%  {prec:5.1f}%')

# ── Alternative: Z-score based threshold ──
print(f'\n{"="*70}')
print(f'  Z-score threshold (μ + k·σ of calibration scores)')
print(f'{"="*70}')
mu_cal = calib_scores.mean()
std_cal = calib_scores.std()
print(f'  Calibration μ={mu_cal:.4f}, σ={std_cal:.4f}')
print(f'  {"k":>6s}  {"Thresh":>8s}  {"TP":>3s}  {"FP":>3s}  {"FN":>3s}  {"TN":>3s}  {"FAR%":>6s}  {"Recall%":>8s}')
print(f'  {"-"*6}  {"-"*8}  {"-"*3}  {"-"*3}  {"-"*3}  {"-"*3}  {"-"*6}  {"-"*8}')

for k in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]:
    threshold = mu_cal + k * std_cal
    y_pred = (q_valid >= threshold).astype(int)
    TP = int(((y_pred == 1) & (y_valid == 1)).sum())
    FP = int(((y_pred == 1) & (y_valid == 0)).sum())
    FN = int(((y_pred == 0) & (y_valid == 1)).sum())
    TN = int(((y_pred == 0) & (y_valid == 0)).sum())
    n_normal = TN + FP
    far = FP / n_normal * 100 if n_normal > 0 else 0
    recall = TP / (TP + FN) * 100 if (TP + FN) > 0 else 0
    print(f'  {k:6.1f}  {threshold:8.4f}  {TP:3d}  {FP:3d}  {FN:3d}  {TN:3d}  {far:5.1f}%  {recall:7.1f}%')

# ── Show which quarters trigger alarms at key thresholds ──
print(f'\n{"="*70}')
print(f'  Alarm timeline at P98 threshold')
print(f'{"="*70}')
thresh98 = np.percentile(calib_scores, 98)
for t in range(T):
    if np.isnan(q_scores[t]):
        continue
    alarm = q_scores[t] >= thresh98
    ds = str(dates[t].date())
    crisis = ds in CRISIS_QUARTERS
    if alarm or crisis:
        tag = ''
        if crisis and alarm: tag = '  ✓ CRISIS + ALARM'
        elif crisis:         tag = '  ✗ CRISIS (missed)'
        elif alarm:          tag = '  ⚠ FALSE ALARM'
        print(f'  {ds}  score={q_scores[t]:.4f}  {tag}')

print('\nDone.')
