"""Benchmark MolecularEngine + stacked BSDT posthoc correction layers.

Architecture:
  Phase 1: MolecularEngine iteration (LJ + Algorithm 1 adaptive damping)
  Phase 2: BSDT channel extraction on final positions (delta_C, delta_G, delta_A, delta_T)
  Phase 3: Stacked posthoc correction (Fisher / QuadSurf / ExpoGate)

Same stacked-layer architecture as Mode6/Mode7 but with molecular physics.
"""
import sys, os, time, warnings, json, gc
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'research', 'udl'))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from udl.system_mode import (
    MolecularEngine, BSDTChannels,
    _MFLSFisherBSDT, _MFLSQuadSurf, _MFLSExpoGate,
)

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


def molecular_with_posthoc(X, y, posthoc='fisher', k_neighbors=10,
                           max_samples=2000, iterations=80):
    """Run MolecularEngine -> BSDT channels -> stacked posthoc correction.

    Phase 1: MolecularEngine iteration (Algorithm 1 damping)
    Phase 2: BSDT channel extraction on final positions
    Phase 3: Fisher / QuadSurf / ExpoGate stacked correction layer
    """
    # Phase 1: Molecular dynamics simulation
    eng = MolecularEngine(
        iterations=iterations,
        k_neighbors=k_neighbors,
        max_samples=max_samples,
        use_bsdt_damping=True,
        use_fused=False,   # skip FusedSystemScorer — we'll use posthoc instead
    )
    # Run simulation (scores ignored — we only want final positions)
    _ = eng.fit_score(X, y)

    # Get final positions + scaler for full-data scoring
    X_final = eng.X_final_
    scaler = eng.scaler_

    # Scale all data consistently
    if scaler is not None:
        X_all = scaler.transform(X).astype(np.float64)
    else:
        X_all = X.astype(np.float64)

    # Determine which points were in the simulation subsample
    n = len(X_all)
    n_sim = len(X_final)
    subsampled = n_sim < n

    # Normal mask on simulation points
    normal_mask_all = (y == 0) if y is not None else np.ones(n, dtype=bool)

    # Phase 2: BSDT channel extraction on final positions
    # Fit on normal-subset of final positions
    if subsampled:
        # Reconstruct sim_idx (same RNG as MolecularEngine)
        rng = np.random.RandomState(42)
        anom_idx = np.where(y == 1)[0] if y is not None else np.array([], dtype=int)
        other_idx = np.where(y != 1)[0] if y is not None else np.arange(n)
        if len(anom_idx) >= max_samples:
            n_anom = min(len(anom_idx), max_samples // 2)
            n_other = max_samples - n_anom
            anom_sample = rng.choice(anom_idx, n_anom, replace=False)
            other_sample = rng.choice(other_idx, min(n_other, len(other_idx)), replace=False)
            sim_idx = np.sort(np.concatenate([anom_sample, other_sample]))
        else:
            n_other = max(0, max_samples - len(anom_idx))
            if len(other_idx) > n_other:
                other_sample = rng.choice(other_idx, n_other, replace=False)
            else:
                other_sample = other_idx
            sim_idx = np.sort(np.concatenate([anom_idx, other_sample]))
        normal_mask_sim = normal_mask_all[sim_idx]
    else:
        normal_mask_sim = normal_mask_all

    X_ref_final = X_final[normal_mask_sim]
    if len(X_ref_final) < 2:
        X_ref_final = X_final

    bsdt = BSDTChannels(k=min(k_neighbors, max(len(X_ref_final) - 1, 1)))
    bsdt.fit(X_ref_final)

    # Score all points (use X_all for full coverage)
    X_scored = X_all
    ch = bsdt.channels(X_scored)
    C = np.column_stack([ch['delta_C'], ch['delta_G'],
                         ch['delta_A'], ch['delta_T']])

    # Phase 3: Stacked correction layer
    has_labels = y is not None and y.sum() > 0

    if posthoc == 'fisher':
        layer = _MFLSFisherBSDT()
        layer.fit(C)
        scores = layer.score(C)
    elif has_labels:
        y_scored = y.astype(float)
        if posthoc == 'expogate':
            layer = _MFLSExpoGate(ridge_alpha=1.0, smooth_sigma=1.0, gate_scale=3.0)
        else:
            layer = _MFLSQuadSurf(ridge_alpha=1.0)
        layer.fit(C, y_scored)
        scores = layer.score(C)
    else:
        # Unsupervised fallback
        if posthoc == 'expogate':
            bsdt.fit_expogate(X_ref_final)
            scores = bsdt.score_expogate(X_scored)
        else:
            bsdt.fit_quadsurf(X_ref_final)
            scores = bsdt.score_quadsurf(X_scored)

    del eng
    return scores


POSTHOCS = ['fisher', 'quadsurf', 'expogate']

for posthoc in POSTHOCS:
    gc.collect()
    eng_name = f'Molecular+{posthoc.capitalize()}'
    print(f'\n{"="*60}')
    print(f'  Engine: {eng_name}')
    print(f'{"="*60}')

    calib_end = pd.Timestamp('2007-09-30')
    n_calib = int((dates <= calib_end).sum())
    q_scores = np.full(T, np.nan)

    t0 = time.time()

    # Phase 1: calibration period
    X_calib = X_3d[:n_calib].reshape(n_calib * N, d)
    y_calib = np.zeros(n_calib * N, dtype=int)
    for t_idx in range(n_calib):
        if str(dates[t_idx].date()) in CRISIS_QUARTERS:
            y_calib[t_idx*N:(t_idx+1)*N] = 1

    scores_calib = molecular_with_posthoc(X_calib, y_calib, posthoc=posthoc)
    for t in range(n_calib):
        q_scores[t] = scores_calib[t*N:(t+1)*N].mean()
    del scores_calib, X_calib, y_calib
    gc.collect()

    threshold = np.nanpercentile(q_scores[:n_calib], 99)
    print(f'Threshold (99th pctl): {threshold:.4f}')

    # Phase 2: expanding window
    for t in range(n_calib, T):
        n_pts = (t + 1) * N
        X_up = X_3d[:t+1].reshape(n_pts, d)
        y_up = np.zeros(n_pts, dtype=int)
        for t_idx in range(t + 1):
            if str(dates[t_idx].date()) in CRISIS_QUARTERS:
                y_up[t_idx*N:(t_idx+1)*N] = 1

        scores_all = molecular_with_posthoc(X_up, y_up, posthoc=posthoc)
        q_scores[t] = scores_all[-N:].mean()
        del scores_all, X_up, y_up
        gc.collect()

    elapsed = time.time() - t0

    valid = ~np.isnan(q_scores)
    q_valid = q_scores[valid]
    y_valid = y_crisis[valid]

    auroc = roc_auc_score(y_valid, q_valid) if 0 < y_valid.sum() < len(y_valid) else float('nan')
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

print('\n' + '='*60)
print('  Reference results (previous benchmarks):')
print('  Molecular (FusedScorer):  AUROC=0.9304  FAR=14.3%  Recall=53.8%')
print('  Mode7-Fisher (gravity):   AUROC=0.8486  FAR=3.2%   Recall=46.2%')
print('  Mode6-Fisher (gravity):   AUROC=0.7851  FAR=3.2%   Recall=30.8%')
print('='*60)
print('\nDone.')
