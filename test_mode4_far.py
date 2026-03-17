"""
Verify Mode4GravityEngine reproduces FAR=1.6% on G-SIB prospective benchmark.
Expected (from bb43ff5): AUROC=0.5788, TP=0, FP=1, FN=13, TN=62, FAR=1.6%

Only runs the Gravity engine (Mode4) for speed.
"""
import sys, os, time, warnings, json
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")

ROOT = r'C:\amttp'
sys.path.insert(0, os.path.join(ROOT, 'research', 'udl'))
sys.path.insert(0, os.path.join(ROOT, 'research', 'udl', 'src'))
sys.path.insert(0, os.path.join(ROOT, 'research', 'adaptive-friction', 'banklevel_enhanced'))

from udl.system_mode import Mode4GravityEngine, Mode5GravityEngine, Mode6GravityEngine

# ── Load data ──
CACHE_DIR = os.path.join(ROOT, 'research', 'adaptive-friction',
                         'banklevel_enhanced', 'gsib_cache_real')
npz = np.load(os.path.join(CACHE_DIR, 'gsib_real_panel.npz'))
X_3d = npz['X']
with open(os.path.join(CACHE_DIR, 'gsib_real_meta.json')) as f:
    meta = json.load(f)

dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:X_3d.shape[0]]
T, N, d = X_3d.shape

# Crisis labels (evaluation only)
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
    'Mode4': (Mode4GravityEngine, {}),
    'Mode5': (Mode5GravityEngine, {}),
    'Mode6-QS': (Mode6GravityEngine, {'posthoc': 'quadsurf'}),
    'Mode6-EG': (Mode6GravityEngine, {'posthoc': 'expogate'}),
}

for eng_name, (EngClass, extra_kw) in ENGINES.items():
    print(f'\n{"="*60}')
    print(f'  Engine: {eng_name}')
    print(f'{"="*60}')

    # ── Prospective scoring ──
    calib_end = pd.Timestamp('2007-09-30')
    n_calib = int((dates <= calib_end).sum())
    q_scores = np.full(T, np.nan)
    kwargs = dict(iterations=60, k_neighbors=10, use_fused=True, **extra_kw)

    print(f'\nCalibration: {dates[0].date()} -> {dates[n_calib-1].date()} ({n_calib} quarters)')
    t0 = time.time()

    # Phase 1: calibration period
    X_calib = X_3d[:n_calib].reshape(n_calib * N, d)
    y_calib = np.zeros(n_calib * N, dtype=int)
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
        y_dum = np.zeros(n_pts, dtype=int)
        eng = EngClass(**kwargs)
        scores_all = eng.fit_score(X_up, y_dum)
        q_scores[t] = scores_all[-N:].mean()
        if (t - n_calib) % 8 == 0:
            alarm = '*** ALARM' if q_scores[t] > threshold else ''
            print(f'  {dates[t].date()}  score={q_scores[t]:.4f} {alarm}')

    elapsed = time.time() - t0

    # ── Evaluate ──
    valid = ~np.isnan(q_scores)
    auc = roc_auc_score(y_crisis[valid], q_scores[valid])
    alarm_mask = q_scores > threshold
    crisis_mask = y_crisis.astype(bool)

    tp = int((alarm_mask & crisis_mask & valid).sum())
    fp = int((alarm_mask & ~crisis_mask & valid).sum())
    fn = int((~alarm_mask & crisis_mask & valid).sum())
    tn = int((~alarm_mask & ~crisis_mask & valid).sum())
    far = fp / max(fp + tn, 1)
    recall = tp / max(tp + fn, 1)

    print(f'\n  {eng_name}:')
    print(f'  AUROC:     {auc:.4f}')
    print(f'  Threshold: {threshold:.4f}')
    print(f'  TP={tp}  FP={fp}  FN={fn}  TN={tn}')
    print(f'  FAR:       {far:.1%}')
    print(f'  Recall:    {recall:.1%}')
    print(f'  Time:      {elapsed:.1f}s')
