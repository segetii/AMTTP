"""
Top-3 Algorithms on Reduced Tensor Descriptor — No-Leakage
============================================================

Pipeline: Raw X → ReducedTensorDescriptor → D → Engine → Score

The RTD transforms raw d=5 features into a (d+7)=12-dimensional
descriptor containing gradient norm, Hessian eigenvalues, Mahalanobis
distance, medoid distance, trace(H), det(Sigma), Morse index.

Top 3 methods (by no-leakage AUROC on raw features):
  1. Fisher   (AUROC 0.719 on raw)
  2. QuadSurf (AUROC 0.706 on raw)
  3. Base/FusedScorer (AUROC 0.607 on raw)

No-leakage protocol:
  (i)   Expanding window: train [0,t], test t+1
  (ii)  RTD fit on training only
  (iii) StandardScaler fit on training only (applied to D)
  (iv)  Frozen threshold from pre-crisis D-scores
  (v)   No label access at test time
"""
import sys, os, time, warnings, json, gc
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'research', 'udl'))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from udl.system_mode import (
    MolecularEngine, ReducedTensorDescriptor, BSDTChannels,
    _MFLSFisherBSDT, _MFLSQuadSurf,
)

warnings.filterwarnings("ignore")

ROOT = r'C:\amttp'
CACHE_DIR = os.path.join(ROOT, 'research', 'adaptive-friction',
                         'banklevel_enhanced', 'gsib_cache_real')
npz = np.load(os.path.join(CACHE_DIR, 'gsib_real_panel.npz'))
X_3d = npz['X']

with open(os.path.join(CACHE_DIR, 'gsib_real_meta.json'), encoding='utf-8') as f:
    meta = json.load(f)

dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:X_3d.shape[0]]
T, N, d = X_3d.shape

CRISIS_QUARTERS = {
    '2007-12-31','2008-03-31','2008-06-30','2008-09-30',
    '2008-12-31','2009-03-31','2009-06-30',
    '2020-03-31','2020-06-30',
    '2011-09-30','2011-12-31','2012-03-31','2012-06-30',
}
y_crisis = np.array([1 if str(d.date()) in CRISIS_QUARTERS else 0
                     for d in dates])

print('=' * 70)
print('  TOP-3 ON REDUCED TENSOR DESCRIPTOR (no-leakage)')
print('  Pipeline: Raw X → RTD → D → Engine → Score')
print('=' * 70)
print(f'Panel: T={T}, N={N}, d_raw={d}')
print(f'Crisis: {int(y_crisis.sum())}/{T} quarters')
print()

BURN_IN = 4
calib_end = pd.Timestamp('2007-09-30')
n_calib = int((dates <= calib_end).sum())

FROZEN_PARAMS_BASE = dict(
    epsilon=1.0, sigma_lj=1.0, alpha_radial=0.1, eta=0.01,
    iterations=80, k_neighbors=10, max_samples=2000,
    use_fused=True, use_bsdt_damping=True, normalize=False,
)
FROZEN_PARAMS_POSTHOC = dict(
    epsilon=1.0, sigma_lj=1.0, alpha_radial=0.1, eta=0.01,
    iterations=80, k_neighbors=10, max_samples=2000,
    use_fused=False, use_bsdt_damping=True, normalize=False,
)

def get_sim_normal_mask(y_train, n_sim, max_samples):
    n_all = len(y_train)
    if n_sim < n_all:
        rng = np.random.RandomState(42)
        anom_idx = np.where(y_train == 1)[0]
        other_idx = np.where(y_train != 1)[0]
        if len(anom_idx) >= max_samples:
            n_anom = min(len(anom_idx), max_samples // 2)
            n_other = max_samples - n_anom
            anom_s = rng.choice(anom_idx, n_anom, replace=False)
            other_s = rng.choice(other_idx, min(n_other, len(other_idx)), replace=False)
            sim_idx = np.sort(np.concatenate([anom_s, other_s]))
        else:
            n_other = max(0, max_samples - len(anom_idx))
            if len(other_idx) > n_other:
                other_s = rng.choice(other_idx, n_other, replace=False)
            else:
                other_s = other_idx
            sim_idx = np.sort(np.concatenate([anom_idx, other_s]))
        return (y_train[sim_idx] == 0)
    else:
        return (y_train == 0)

VARIANTS = ['base', 'fisher', 'quadsurf']
all_results = {}

for variant in VARIANTS:
    gc.collect()
    label = {
        'base': 'RTD+Molecular (FusedScorer)',
        'fisher': 'RTD+Molecular+Fisher',
        'quadsurf': 'RTD+Molecular+QuadSurf',
    }[variant]
    is_base = (variant == 'base')

    print(f'\n{"="*70}')
    print(f'  {label}  (no-leakage, expanding window)')
    print(f'{"="*70}')

    params = FROZEN_PARAMS_BASE if is_base else FROZEN_PARAMS_POSTHOC
    q_scores = np.full(T, np.nan)
    t0 = time.time()

    for t in range(BURN_IN, T - 1):
        n_train_q = t + 1
        X_train_raw = X_3d[:n_train_q].reshape(n_train_q * N, d)

        y_train = np.zeros(n_train_q * N, dtype=int)
        for t_idx in range(n_train_q):
            if str(dates[t_idx].date()) in CRISIS_QUARTERS:
                y_train[t_idx * N:(t_idx + 1) * N] = 1

        X_test_raw = X_3d[t + 1].reshape(N, d)

        # ── Step 1: Fit RTD on TRAINING normal data only ──
        normal_train_mask = (y_train == 0)
        X_ref = X_train_raw[normal_train_mask]
        if len(X_ref) < 10:
            X_ref = X_train_raw

        rtd = ReducedTensorDescriptor(k_neighbors=min(10, len(X_ref) - 1),
                                       n_eigs=d)
        rtd.fit(X_ref)

        # ── Step 2: Transform to descriptor space ──
        D_train = rtd.transform(X_train_raw)
        D_test = rtd.transform(X_test_raw)
        d_desc = D_train.shape[1]

        # ── Step 3: Scaler fit on TRAINING D only ──
        scaler = StandardScaler()
        D_train_s = scaler.fit_transform(D_train).astype(np.float64)
        D_test_s = scaler.transform(D_test).astype(np.float64)

        # ── Step 4: Engine on D ──
        eng = MolecularEngine(**{**params, 'k_neighbors': min(10, len(D_train_s) - 1)})
        _ = eng.fit_score(D_train_s, y_train)

        if is_base:
            if eng.fused_scorer is not None:
                test_scores = eng.fused_scorer.score(D_test_s)
            elif hasattr(eng, 'alarm') and eng.alarm is not None:
                test_scores = eng.alarm.score(D_test_s)
            else:
                test_scores = np.linalg.norm(D_test_s - D_test_s.mean(axis=0), axis=1)
        else:
            X_final = eng.X_final_
            normal_mask_sim = get_sim_normal_mask(y_train, len(X_final), params['max_samples'])
            X_ref_sim = X_final[normal_mask_sim]
            if len(X_ref_sim) < 2:
                X_ref_sim = X_final

            k_bsdt = min(10, max(len(X_ref_sim) - 1, 1))
            bsdt = BSDTChannels(k=k_bsdt)
            bsdt.fit(X_ref_sim)

            ch_train = bsdt.channels(D_train_s)
            C_train = np.column_stack([ch_train['delta_C'], ch_train['delta_G'],
                                       ch_train['delta_A'], ch_train['delta_T']])
            ch_test = bsdt.channels(D_test_s)
            C_test = np.column_stack([ch_test['delta_C'], ch_test['delta_G'],
                                      ch_test['delta_A'], ch_test['delta_T']])

            n_crisis_train = int(y_train.sum())
            try:
                if variant == 'fisher':
                    layer = _MFLSFisherBSDT()
                    layer.fit(C_train)
                    test_scores = layer.score(C_test)
                elif variant == 'quadsurf':
                    if n_crisis_train > 0:
                        layer = _MFLSQuadSurf(ridge_alpha=1.0)
                        layer.fit(C_train, y_train.astype(float))
                        test_scores = layer.score(C_test)
                    else:
                        layer = _MFLSFisherBSDT()
                        layer.fit(C_train)
                        test_scores = layer.score(C_test)
            except Exception:
                test_scores = bsdt.energy(D_test_s)
            del bsdt

        q_scores[t + 1] = float(test_scores.mean())

        ds = str(dates[t + 1].date())
        crisis_mark = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
        if (t + 1) % 10 == 0 or ds in CRISIS_QUARTERS:
            print(f'  t={t+1:3d}  {ds}  score={q_scores[t+1]:.4f}{crisis_mark}')

        del eng, rtd
        gc.collect()

    elapsed = time.time() - t0

    # ── Fixed threshold from pre-crisis baseline ──
    calib_scores = q_scores[BURN_IN + 1:n_calib + 1]
    calib_scores = calib_scores[~np.isnan(calib_scores)]
    if len(calib_scores) < 3:
        calib_scores = q_scores[:n_calib + 1]
        calib_scores = calib_scores[~np.isnan(calib_scores)]

    mu_cal = calib_scores.mean()
    std_cal = calib_scores.std() + 1e-10
    FIXED_THR = mu_cal + 3.0 * std_cal

    # ── Evaluate ──
    valid = ~np.isnan(q_scores)
    q_valid = q_scores[valid]
    y_valid = y_crisis[valid]

    auroc = roc_auc_score(y_valid, q_valid) if 0 < y_valid.sum() < len(y_valid) else float('nan')

    y_pred = (q_valid >= FIXED_THR).astype(int)
    TP = int(((y_pred == 1) & (y_valid == 1)).sum())
    FP = int(((y_pred == 1) & (y_valid == 0)).sum())
    FN = int(((y_pred == 0) & (y_valid == 1)).sum())
    TN = int(((y_pred == 0) & (y_valid == 0)).sum())
    n_normal = TN + FP
    far = FP / n_normal * 100 if n_normal > 0 else 0
    recall = TP / (TP + FN) * 100 if (TP + FN) > 0 else 0
    prec = TP / (TP + FP) * 100 if (TP + FP) > 0 else 0

    gfc_qs = {'2007-12-31','2008-03-31','2008-06-30','2008-09-30',
               '2008-12-31','2009-03-31','2009-06-30'}
    gfc_mask = np.array([str(dates[i].date()) in gfc_qs for i in range(T)])
    gfc_or_norm = valid & (gfc_mask | (y_crisis == 0))
    auroc_gfc = roc_auc_score(y_crisis[gfc_or_norm], q_scores[gfc_or_norm]) \
        if gfc_or_norm.sum() > 2 and y_crisis[gfc_or_norm].sum() > 0 else float('nan')

    print(f'\n  {label}:')
    print(f'  d_descriptor:  {d_desc}  (vs raw d={d})')
    print(f'  AUROC (full):  {auroc:.4f}')
    print(f'  AUROC (GFC):   {auroc_gfc:.4f}')
    print(f'  Threshold:     {FIXED_THR:.4f}  (mu+3sig, frozen)')
    print(f'  TP={TP}  FP={FP}  FN={FN}  TN={TN}')
    print(f'  FAR:           {far:.1f}%')
    print(f'  Recall:        {recall:.1f}%')
    print(f'  Precision:     {prec:.1f}%')
    print(f'  Time:          {elapsed:.1f}s')

    # Alarm timeline
    print(f'\n  Alarms:')
    for i in range(T):
        if not valid[i]:
            continue
        s = q_scores[i]
        ds = str(dates[i].date())
        is_crisis = ds in CRISIS_QUARTERS
        is_alarm = s >= FIXED_THR
        if is_alarm or is_crisis:
            if is_crisis and is_alarm:   tag = 'CRISIS + ALARM'
            elif is_crisis:              tag = 'CRISIS (missed)'
            elif is_alarm:               tag = 'FALSE ALARM'
            print(f'    {ds}  score={s:.4f}  {tag}')

    all_results[variant] = {
        'auroc': float(auroc), 'auroc_gfc': float(auroc_gfc),
        'far': float(far), 'recall': float(recall), 'precision': float(prec),
        'threshold': float(FIXED_THR), 'mu_cal': float(mu_cal),
        'std_cal': float(std_cal), 'd_descriptor': int(d_desc),
        'TP': TP, 'FP': FP, 'FN': FN, 'TN': TN,
        'time': float(elapsed),
        'scores': {str(dates[i].date()): float(q_scores[i])
                   for i in range(T) if not np.isnan(q_scores[i])},
    }

# ══════════════════════════════════════════════════════════════════
#  Comparison table
# ══════════════════════════════════════════════════════════════════
print(f'\n\n{"="*80}')
print(f'  COMPARISON: Raw Features vs Reduced Tensor Descriptor')
print(f'  No-leakage, expanding window, mu+3sig threshold')
print(f'{"="*80}')
hdr = f'  {"Method":<30s} {"Input":>5s} {"AUROC":>6s} {"GFC-AUC":>8s} {"FAR%":>6s} {"Recall%":>8s} {"Prec%":>6s}'
print(hdr)
print(f'  {"-"*30} {"-"*5} {"-"*6} {"-"*8} {"-"*6} {"-"*8} {"-"*6}')

# Raw feature results (from previous runs)
raw_results = {
    'base':     {'auroc': 0.607, 'auroc_gfc': 0.837, 'far': 22.4, 'recall': 38.5, 'precision': 27.8},
    'fisher':   {'auroc': 0.719, 'auroc_gfc': 0.823, 'far': 0.0, 'recall': 0.0, 'precision': 0.0},
    'quadsurf': {'auroc': 0.706, 'auroc_gfc': 0.818, 'far': 6.9, 'recall': 23.1, 'precision': 42.9},
}
labels_short = {'base': 'Base (FusedScorer)', 'fisher': 'Fisher', 'quadsurf': 'QuadSurf'}

for v in VARIANTS:
    rr = raw_results[v]
    print(f'  {labels_short[v]+" (raw d=5)":<30s} {"d=5":>5s} {rr["auroc"]:6.3f} {rr["auroc_gfc"]:8.3f} {rr["far"]:5.1f}% {rr["recall"]:7.1f}% {rr["precision"]:5.1f}%')

print()
for v in VARIANTS:
    r = all_results[v]
    dd = r['d_descriptor']
    print(f'  {labels_short[v]+f" (RTD d={dd})":<30s} {"d="+str(dd):>5s} {r["auroc"]:6.3f} {r["auroc_gfc"]:8.3f} {r["far"]:5.1f}% {r["recall"]:7.1f}% {r["precision"]:5.1f}%')

# ── Save results ──
out_path = os.path.join(ROOT, 'no_leakage_rtd_results.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(all_results, f, indent=2, default=float)
print(f'\nResults saved to {out_path}')
print('Done.')
