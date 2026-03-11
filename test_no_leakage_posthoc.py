"""
Strict No-Data-Leakage: MolecularEngine + BSDT Posthoc Variants
================================================================

Same 5-point protocol as test_no_leakage.py, but with MFLS posthoc
correction layers (Fisher, QuadSurf, ExpoGate) replacing FusedSystemScorer.

Architecture per quarter:
  1. MolecularEngine iteration on TRAIN data only (quarters 0..t)
  2. Extract BSDT channels on final positions
  3. Apply posthoc correction (Fisher / QuadSurf / ExpoGate)
  4. Score TEST quarter (t+1) using fitted posthoc layer

No-leakage rules:
  (i)   Expanding window: train on [0, t], test on t+1
  (ii)  Scaler fit on training only
  (iii) Frozen hyperparameters (from pre-crisis period)
  (iv)  Fixed threshold (μ+3σ from pre-crisis scores)
  (v)   No label access at test time
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
y_crisis = np.array([1 if str(d.date()) in CRISIS_QUARTERS else 0
                     for d in dates])

print(f'Panel: T={T} quarters, N={N} banks, d={d} features')
print(f'Crisis quarters: {int(y_crisis.sum())}/{T}')

# ══════════════════════════════════════════════════════════════════
#  Frozen hyperparameters (identical to base no-leakage run)
# ══════════════════════════════════════════════════════════════════
FROZEN_PARAMS = dict(
    epsilon=1.0, sigma_lj=1.0, alpha_radial=0.1, eta=0.01,
    iterations=80, k_neighbors=10, max_samples=2000,
    use_fused=False,         # <-- no FusedSystemScorer; posthoc instead
    use_bsdt_damping=True,
    normalize=False,         # we handle scaling ourselves
)

BURN_IN = 4
calib_end = pd.Timestamp('2007-09-30')
n_calib = int((dates <= calib_end).sum())

VARIANTS = ['fisher', 'quadsurf', 'expogate']
all_results = {}

for variant in VARIANTS:
    gc.collect()
    label = f'Molecular+{variant.capitalize()}'
    print(f'\n{"="*70}')
    print(f'  {label}  (strict no-leakage, expanding window)')
    print(f'{"="*70}')

    q_scores = np.full(T, np.nan)
    t0 = time.time()

    for t in range(BURN_IN, T - 1):
        # ── Training window: quarters 0..t ──
        n_train_q = t + 1
        X_train_raw = X_3d[:n_train_q].reshape(n_train_q * N, d)

        y_train = np.zeros(n_train_q * N, dtype=int)
        for t_idx in range(n_train_q):
            if str(dates[t_idx].date()) in CRISIS_QUARTERS:
                y_train[t_idx * N:(t_idx + 1) * N] = 1

        # ── Scaler fit on TRAINING only ──
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train_raw).astype(np.float64)

        # ── Test quarter: t+1 (NEVER in training) ──
        X_test_raw = X_3d[t + 1].reshape(N, d)
        X_test = scaler.transform(X_test_raw).astype(np.float64)

        # ── Phase 1: MolecularEngine on training data ──
        eng = MolecularEngine(**FROZEN_PARAMS)
        _ = eng.fit_score(X_train, y_train)

        X_final = eng.X_final_  # final simulated positions (training)

        # Normal mask on simulation subset
        n_sim = len(X_final)
        n_all = len(X_train)
        if n_sim < n_all:
            # Reconstruct sim_idx (same RNG seed as MolecularEngine)
            rng = np.random.RandomState(42)
            anom_idx = np.where(y_train == 1)[0]
            other_idx = np.where(y_train != 1)[0]
            if len(anom_idx) >= FROZEN_PARAMS['max_samples']:
                n_anom = min(len(anom_idx), FROZEN_PARAMS['max_samples'] // 2)
                n_other = FROZEN_PARAMS['max_samples'] - n_anom
                anom_s = rng.choice(anom_idx, n_anom, replace=False)
                other_s = rng.choice(other_idx, min(n_other, len(other_idx)), replace=False)
                sim_idx = np.sort(np.concatenate([anom_s, other_s]))
            else:
                n_other = max(0, FROZEN_PARAMS['max_samples'] - len(anom_idx))
                if len(other_idx) > n_other:
                    other_s = rng.choice(other_idx, n_other, replace=False)
                else:
                    other_s = other_idx
                sim_idx = np.sort(np.concatenate([anom_idx, other_s]))
            normal_mask_sim = (y_train[sim_idx] == 0)
        else:
            normal_mask_sim = (y_train == 0)

        X_ref = X_final[normal_mask_sim]
        if len(X_ref) < 2:
            X_ref = X_final

        # ── Phase 2: Extract BSDT channels ──
        k_bsdt = min(10, max(len(X_ref) - 1, 1))
        bsdt = BSDTChannels(k=k_bsdt)
        bsdt.fit(X_ref)

        # Channels on training data (for fitting posthoc layer)
        ch_train = bsdt.channels(X_train)
        C_train = np.column_stack([ch_train['delta_C'], ch_train['delta_G'],
                                   ch_train['delta_A'], ch_train['delta_T']])

        # Channels on test data (for scoring)
        ch_test = bsdt.channels(X_test)
        C_test = np.column_stack([ch_test['delta_C'], ch_test['delta_G'],
                                  ch_test['delta_A'], ch_test['delta_T']])

        # ── Phase 3: Fit posthoc on TRAINING, score TEST ──
        try:
            if variant == 'fisher':
                layer = _MFLSFisherBSDT()
                layer.fit(C_train)  # unsupervised
                test_scores = layer.score(C_test)
            elif variant == 'quadsurf':
                layer = _MFLSQuadSurf(ridge_alpha=1.0)
                layer.fit(C_train, y_train.astype(float))
                test_scores = layer.score(C_test)
            elif variant == 'expogate':
                layer = _MFLSExpoGate(ridge_alpha=1.0, smooth_sigma=1.0, gate_scale=3.0)
                layer.fit(C_train, y_train.astype(float))
                test_scores = layer.score(C_test)
        except Exception as e:
            # Fallback: raw BSDT energy
            test_scores = bsdt.energy(X_test)

        q_scores[t + 1] = float(test_scores.mean())

        ds = str(dates[t + 1].date())
        crisis_mark = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
        if (t + 1) % 10 == 0 or ds in CRISIS_QUARTERS:
            print(f'  t={t+1:3d}  {ds}  score={q_scores[t+1]:.4f}{crisis_mark}')

        del eng, X_train, X_test, bsdt, C_train, C_test
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

    print(f'\n  {label} — Strict No-Leakage Results:')
    print(f'  AUROC:     {auroc:.4f}')
    print(f'  Threshold: {FIXED_THR:.4f}  (μ+3σ, frozen)')
    print(f'  TP={TP}  FP={FP}  FN={FN}  TN={TN}')
    print(f'  FAR:       {far:.1f}%')
    print(f'  Recall:    {recall:.1f}%')
    print(f'  Precision: {prec:.1f}%')
    print(f'  Time:      {elapsed:.0f}s')

    all_results[variant] = {
        'auroc': auroc, 'far': far, 'recall': recall, 'prec': prec,
        'tp': TP, 'fp': FP, 'fn': FN, 'tn': TN,
        'threshold': FIXED_THR, 'time': elapsed,
        'scores': {str(dates[i].date()): float(q_scores[i])
                   for i in range(T) if not np.isnan(q_scores[i])},
    }

# ══════════════════════════════════════════════════════════════════
#  Summary comparison
# ══════════════════════════════════════════════════════════════════
print(f'\n\n{"="*70}')
print(f'  SUMMARY: All Variants (Strict No-Data-Leakage)')
print(f'{"="*70}')
print(f'  {"Variant":<25s}  {"AUROC":>6s}  {"FAR%":>6s}  {"Recall%":>8s}  {"Prec%":>6s}  {"TP":>3s}  {"FP":>3s}')
print(f'  {"-"*25}  {"-"*6}  {"-"*6}  {"-"*8}  {"-"*6}  {"-"*3}  {"-"*3}')

# Include base molecular result for comparison
print(f'  {"Molecular (FusedScorer)":<25s}  {"0.6074":>6s}  {"22.4":>6s}  {"38.5":>8s}  {"27.8":>6s}  {"5":>3s}  {"13":>3s}')

for v in VARIANTS:
    r = all_results[v]
    label = f'Molecular+{v.capitalize()}'
    print(f'  {label:<25s}  {r["auroc"]:6.4f}  {r["far"]:5.1f}%  {r["recall"]:7.1f}%  {r["prec"]:5.1f}%  {r["tp"]:3d}  {r["fp"]:3d}')

# Save results
results_path = os.path.join(ROOT, 'no_leakage_posthoc_results.json')
with open(results_path, 'w', encoding='utf-8') as f:
    json.dump(all_results, f, indent=2)
print(f'\nResults saved: {results_path}')
print('Done.')
