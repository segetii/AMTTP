"""Quick benchmark for Mode6/Mode7 stacked-layer architecture."""
import sys, os, time, warnings, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'research', 'udl'))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from udl.system_mode import Mode6GravityEngine, Mode7GravityEngine

warnings.filterwarnings("ignore")

ROOT = r'C:\amttp'
# ── Data ──
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

ENGINES = {
    'Mode6-Fisher': (Mode6GravityEngine, {'posthoc': 'fisher'}),
    'Mode6-QS': (Mode6GravityEngine, {'posthoc': 'quadsurf'}),
    'Mode6-EG': (Mode6GravityEngine, {'posthoc': 'expogate'}),
    'Mode7-Fisher': (Mode7GravityEngine, {'posthoc': 'fisher'}),
    'Mode7-QS': (Mode7GravityEngine, {'posthoc': 'quadsurf'}),
    'Mode7-EG': (Mode7GravityEngine, {'posthoc': 'expogate'}),
}

for eng_name, (EngClass, extra_kw) in ENGINES.items():
    print(f'\n{"="*60}')
    print(f'  Engine: {eng_name}')
    print(f'{"="*60}')

    calib_end = pd.Timestamp('2007-09-30')
    n_calib = int((dates <= calib_end).sum())
    q_scores = np.full(T, np.nan)
    kwargs = dict(iterations=60, k_neighbors=10, **extra_kw)

    print(f'\nCalibration: {dates[0].date()} -> {dates[n_calib-1].date()} ({n_calib} quarters)')
    t0 = time.time()

    # Phase 1: calibration period
    X_calib = X_3d[:n_calib].reshape(n_calib * N, d)
    # Build per-entity crisis labels from NBER dates
    y_calib = np.zeros(n_calib * N, dtype=int)
    for t_idx in range(n_calib):
        ds = str(dates[t_idx].date())
        if ds in CRISIS_QUARTERS:
            y_calib[t_idx*N:(t_idx+1)*N] = 1
    eng = EngClass(**kwargs)
    scores_calib = eng.fit_score(X_calib, y_calib)
    for t in range(n_calib):
        q_scores[t] = scores_calib[t*N:(t+1)*N].mean()

    threshold = np.nanpercentile(q_scores[:n_calib], 99)
    print(f'Alarm threshold (99th pctl): {threshold:.4f}')

    # Phase 2: expanding window
    for t in range(n_calib, T):
        n_pts = (t + 1) * N
        X_up = X_3d[:t+1].reshape(n_pts, d)
        # Build per-entity crisis labels from NBER dates
        y_up = np.zeros(n_pts, dtype=int)
        for t_idx in range(t + 1):
            ds = str(dates[t_idx].date())
            if ds in CRISIS_QUARTERS:
                y_up[t_idx*N:(t_idx+1)*N] = 1
        eng = EngClass(**kwargs)
        scores_all = eng.fit_score(X_up, y_up)
        q_scores[t] = scores_all[-N:].mean()

        ds = str(dates[t].date())
        if ds[:4] in ('2007','2009','2011','2013','2015','2017','2019','2021','2023'):
            if ds.endswith('12-31'):
                print(f'  {ds}  score={q_scores[t]:.4f} {"<< ALARM" if q_scores[t] >= threshold else ""}')

    elapsed = time.time() - t0

    # Evaluation
    valid = ~np.isnan(q_scores)
    q_valid = q_scores[valid]
    y_valid = y_crisis[valid]

    auroc = roc_auc_score(y_valid, q_valid) if y_valid.sum() > 0 and y_valid.sum() < len(y_valid) else float('nan')

    y_pred = (q_valid >= threshold).astype(int)
    TP = int(((y_pred == 1) & (y_valid == 1)).sum())
    FP = int(((y_pred == 1) & (y_valid == 0)).sum())
    FN = int(((y_pred == 0) & (y_valid == 1)).sum())
    TN = int(((y_pred == 0) & (y_valid == 0)).sum())
    n_normal = TN + FP
    far = FP / n_normal * 100 if n_normal > 0 else float('nan')
    recall = TP / (TP + FN) * 100 if (TP + FN) > 0 else 0.0

    print(f'\n  {eng_name}:')
    print(f'  AUROC:     {auroc:.4f}')
    print(f'  Threshold: {threshold:.4f}')
    print(f'  TP={TP}  FP={FP}  FN={FN}  TN={TN}')
    print(f'  FAR:       {far:.1f}%')
    print(f'  Recall:    {recall:.1f}%')
    print(f'  Time:      {elapsed:.1f}s')

print('\nDone.')
