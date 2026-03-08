"""
Benchmark: Calibrated vs Raw FAR across datasets.
Tests FARTargetCalibrator with target_far=0.05 (FCA compliance).
"""
import sys, time
import numpy as np
from sklearn.metrics import roc_auc_score

sys.path.insert(0, r'c:\amttp\research\udl')

from udl.system_mode import MolecularEngine, GravityModeEngine, HybridGravityEngine
from udl.datasets import load_dataset


def far_at_recall(scores, y, target_recall=0.95):
    """Compute FAR at a given recall level."""
    y = np.asarray(y, dtype=int)
    anom = scores[y == 1]
    norm = scores[y == 0]
    if len(anom) == 0 or len(norm) == 0:
        return float('nan')
    # Threshold that catches target_recall of anomalies
    thresh = np.percentile(anom, 100 * (1 - target_recall))
    far = float(np.mean(norm >= thresh))
    return far


datasets = ['mammography', 'pendigits', 'shuttle']
methods = [
    ('Hybrid_Raw',  dict(calibrate=None)),
    ('Hybrid_Cal',  dict(calibrate='combined', target_far=0.05)),
    ('Mol_Raw',     dict(calibrate=None)),
    ('Mol_Cal',     dict(calibrate='combined', target_far=0.05)),
    ('Grav_Raw',    dict(calibrate=None)),
    ('Grav_Cal',    dict(calibrate='combined', target_far=0.05)),
]

print('=' * 76)
print('  CALIBRATION BENCHMARK: Raw vs FAR-Calibrated Scoring')
print('  Target FAR: 5% (FCA/PRA compliance level)')
print('=' * 76)

all_results = {}

for ds_name in datasets:
    X, y = load_dataset(ds_name)
    n_anom = int(y.sum())
    print(f'\n  Dataset: {ds_name}  ({len(X)} samples, {n_anom} anomalies, '
          f'{n_anom/len(X):.1%} contamination)')
    print('  ' + '-' * 70)
    
    for method_name, cal_kwargs in methods:
        calibrate = cal_kwargs.get('calibrate')
        target_far = cal_kwargs.get('target_far', 0.05)
        
        t0 = time.time()
        
        if method_name.startswith('Hybrid'):
            eng = HybridGravityEngine(
                calibrate=calibrate,
                target_far=target_far,
            )
        elif method_name.startswith('Mol'):
            eng = MolecularEngine(
                iterations=80, k_neighbors=15, max_samples=3000,
                use_fused=True,
                calibrate=calibrate,
                target_far=target_far,
            )
        elif method_name.startswith('Grav'):
            eng = GravityModeEngine(
                iterations=60, k_neighbors=15, max_samples=3000,
                use_fused=True,
                calibrate=calibrate,
                target_far=target_far,
            )
        
        scores = eng.fit_score(X, y)
        elapsed = time.time() - t0
        
        auc = roc_auc_score(y, scores)
        far = far_at_recall(scores, y, 0.95)
        
        tag = 'CAL' if calibrate else 'RAW'
        print(f'    {method_name:<16} AUC={auc:.4f}  FAR@95={far:.3f}  T={elapsed:.1f}s  [{tag}]')
        
        all_results.setdefault(ds_name, {})[method_name] = {
            'auc': auc, 'far': far, 'time': elapsed
        }

# Summary
print('\n' + '=' * 76)
print('  SUMMARY: Per-dataset FAR improvement (Raw -> Calibrated)')
print('=' * 76)

for prefix in ['Hybrid', 'Mol', 'Grav']:
    print(f'\n  {prefix} engine:')
    raw_key = f'{prefix}_Raw'
    cal_key = f'{prefix}_Cal'
    for ds in datasets:
        if raw_key in all_results.get(ds, {}) and cal_key in all_results.get(ds, {}):
            r = all_results[ds][raw_key]
            c = all_results[ds][cal_key]
            far_drop = (r['far'] - c['far']) / r['far'] * 100 if r['far'] > 0 else 0
            auc_delta = c['auc'] - r['auc']
            meets = 'YES' if c['far'] < 0.05 else ('CLOSE' if c['far'] < 0.10 else 'NO')
            print(f'    {ds:<14} FAR: {r["far"]:.3f} -> {c["far"]:.3f} '
                  f'({far_drop:+.0f}%)  AUC delta: {auc_delta:+.4f}  '
                  f'FCA<5%: {meets}')

# Overall
print('\n  ' + '-' * 70)
print('  MEAN across datasets:')
for prefix in ['Hybrid', 'Mol', 'Grav']:
    raw_key = f'{prefix}_Raw'
    cal_key = f'{prefix}_Cal'
    raw_fars = [all_results[ds][raw_key]['far'] for ds in datasets 
                if raw_key in all_results.get(ds, {})]
    cal_fars = [all_results[ds][cal_key]['far'] for ds in datasets 
                if cal_key in all_results.get(ds, {})]
    raw_aucs = [all_results[ds][raw_key]['auc'] for ds in datasets 
                if raw_key in all_results.get(ds, {})]
    cal_aucs = [all_results[ds][cal_key]['auc'] for ds in datasets 
                if cal_key in all_results.get(ds, {})]
    if raw_fars and cal_fars:
        print(f'    {prefix:<10} FAR: {np.mean(raw_fars):.3f} -> {np.mean(cal_fars):.3f}  '
              f'AUC: {np.mean(raw_aucs):.4f} -> {np.mean(cal_aucs):.4f}')

print()
print('  DEPLOYMENT VERDICT:')
for ds in datasets:
    best_far = min(all_results[ds][m]['far'] for m in all_results[ds])
    best_method = min(all_results[ds], key=lambda m: all_results[ds][m]['far'])
    meets_fca = best_far < 0.05
    meets_fda = best_far < 0.10
    if meets_fca:
        verdict = f'FCA COMPLIANT (FAR={best_far:.1%})'
    elif meets_fda:
        verdict = f'FDA COMPLIANT (FAR={best_far:.1%})'
    else:
        verdict = f'NOT YET COMPLIANT (FAR={best_far:.1%})'
    print(f'    {ds:<14} {verdict}  [{best_method}]')
