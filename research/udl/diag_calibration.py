"""Diagnose calibration/threshold issues for each engine on KDDCup99."""
import numpy as np
from udl.system_mode import MolecularEngine, GravityModeEngine, HybridGravityEngine
from sklearn.metrics import roc_auc_score, precision_recall_curve

# Load KDDCup99
cdata = np.load('../../data/external_validation/kddcup99_cyber.npz')
X, y = cdata['X10'], cdata['y']
print(f'KDDCup99: {X.shape}, attacks={int(y.sum())}/{len(y)} ({100*y.mean():.1f}%)')

engines = [
    ('Molecular(LJ)',   MolecularEngine,    {}),
    ('Gravity(N-body)', GravityModeEngine,  {}),
    ('Hybrid(Mol+Grav)',HybridGravityEngine,{}),
]

# Also run with calibration='combined' to compare
engines_cal = [
    ('Molecular+cal',   MolecularEngine,    {'calibrate':'combined','target_far':0.05}),
    ('Gravity+cal',     GravityModeEngine,  {'calibrate':'combined','target_far':0.05}),
    ('Hybrid+cal',      HybridGravityEngine,{'calibrate':'combined','target_far':0.05}),
]

print('\n' + '='*90)
print('  RAW SCORE DISTRIBUTIONS — No calibration')
print('='*90)

for name, Eng, kw in engines:
    eng = Eng(**kw)
    s = eng.fit_score(X, y)
    auc = roc_auc_score(y, s)

    s_atk = s[y == 1]
    s_nrm = s[y == 0]

    # Percentile threshold (what _op_metrics uses)
    thr = float(np.percentile(s, 100 * (1 - y.mean())))
    caught_pct = int((s_atk > thr).sum())
    fp_pct = int((s_nrm > thr).sum())

    # Optimal F1 threshold
    prec_arr, rec_arr, thresholds = precision_recall_curve(y, s)
    f1_arr = 2 * prec_arr * rec_arr / (prec_arr + rec_arr + 1e-12)
    best_idx = np.argmax(f1_arr)
    best_thr = thresholds[min(best_idx, len(thresholds)-1)]
    caught_opt = int((s_atk > best_thr).sum())
    fp_opt = int((s_nrm > best_thr).sum())

    print(f'\n── {name} ──')
    print(f'  AUC = {auc:.4f}')
    print(f'  Normal  scores: min={s_nrm.min():.8f}  p50={np.median(s_nrm):.8f}  p95={np.percentile(s_nrm,95):.8f}  max={s_nrm.max():.8f}')
    print(f'  Attack  scores: min={s_atk.min():.8f}  p50={np.median(s_atk):.8f}  p95={np.percentile(s_atk,95):.8f}  max={s_atk.max():.8f}')
    print(f'  Score spread:   normal_std={s_nrm.std():.8f}  attack_std={s_atk.std():.8f}')
    print(f'  Separation:     (atk_mean - nrm_mean) / pooled_std = {(s_atk.mean()-s_nrm.mean()) / (s.std()+1e-12):.4f}')
    print()
    print(f'  Percentile thr ({100*(1-y.mean()):.0f}th) = {thr:.8f}')
    print(f'    → Caught: {caught_pct:>6}/{len(s_atk)}  FP: {fp_pct:>6}  FNR: {1-caught_pct/len(s_atk):.4f}  FPR: {fp_pct/len(s_nrm):.4f}')
    print(f'  Optimal F1 thr         = {best_thr:.8f}')
    print(f'    → Caught: {caught_opt:>6}/{len(s_atk)}  FP: {fp_opt:>6}  FNR: {1-caught_opt/len(s_atk):.4f}  FPR: {fp_opt/len(s_nrm):.4f}')
    print()
    print(f'  % attacks BELOW normal median: {(s_atk < np.median(s_nrm)).mean()*100:.1f}%')
    print(f'  % attacks ABOVE normal p95:    {(s_atk > np.percentile(s_nrm,95)).mean()*100:.1f}%')
    
    # Unique score check (degenerate?)
    unique = len(np.unique(np.round(s, 8)))
    print(f'  Unique scores: {unique:,} / {len(s):,}  ({"OK" if unique > 100 else "DEGENERATE"})')
    
    # Score distribution shape
    pcts = np.percentile(s, [0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100])
    print(f'  Score quantiles: [p0={pcts[0]:.6f}, p1={pcts[1]:.6f}, p5={pcts[2]:.6f}, p10={pcts[3]:.6f}, '
          f'p25={pcts[4]:.6f}, p50={pcts[5]:.6f}, p75={pcts[6]:.6f}, p90={pcts[7]:.6f}, '
          f'p95={pcts[8]:.6f}, p99={pcts[9]:.6f}, p100={pcts[10]:.6f}]')

print('\n' + '='*90)
print('  WITH CALIBRATION (combined, FAR=5%)')
print('='*90)

for name, Eng, kw in engines_cal:
    eng = Eng(**kw)
    s = eng.fit_score(X, y)
    auc = roc_auc_score(y, s)
    s_atk = s[y == 1]
    s_nrm = s[y == 0]
    
    thr = float(np.percentile(s, 100 * (1 - y.mean())))
    caught_pct = int((s_atk > thr).sum())
    fp_pct = int((s_nrm > thr).sum())
    
    # Optimal F1 threshold
    prec_arr, rec_arr, thresholds = precision_recall_curve(y, s)
    f1_arr = 2 * prec_arr * rec_arr / (prec_arr + rec_arr + 1e-12)
    best_idx = np.argmax(f1_arr)
    best_thr = thresholds[min(best_idx, len(thresholds)-1)]
    caught_opt = int((s_atk > best_thr).sum())
    fp_opt = int((s_nrm > best_thr).sum())
    
    print(f'\n── {name} ──')
    print(f'  AUC = {auc:.4f}')
    print(f'  Normal:  min={s_nrm.min():.6f}  p50={np.median(s_nrm):.6f}  p95={np.percentile(s_nrm,95):.6f}  max={s_nrm.max():.6f}')
    print(f'  Attack:  min={s_atk.min():.6f}  p50={np.median(s_atk):.6f}  p95={np.percentile(s_atk,95):.6f}  max={s_atk.max():.6f}')
    print(f'  Percentile thr: caught {caught_pct}/{len(s_atk)}  FP={fp_pct}  FNR={1-caught_pct/len(s_atk):.4f}  FPR={fp_pct/len(s_nrm):.4f}')
    print(f'  Optimal F1:     caught {caught_opt}/{len(s_atk)}  FP={fp_opt}  FNR={1-caught_opt/len(s_atk):.4f}  FPR={fp_opt/len(s_nrm):.4f}')
    pcts = np.percentile(s, [0, 25, 50, 75, 90, 95, 99, 100])
    print(f'  Quantiles: p0={pcts[0]:.6f} p25={pcts[1]:.6f} p50={pcts[2]:.6f} p75={pcts[3]:.6f} p90={pcts[4]:.6f} p95={pcts[5]:.6f} p99={pcts[6]:.6f} p100={pcts[7]:.6f}')
