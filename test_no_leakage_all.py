"""
Strict No-Data-Leakage: All Variants on Real-World GSIB Banking Data
=====================================================================

Data: FDIC call reports + ECB MIR + World Bank GFDD
  T=76 quarters, N=25 G-SIBs, d=5 features
  (loan_to_asset, equity_ratio, npl_ratio, roa, funding_cost)

Variants tested:
  1. Base: MolecularEngine + FusedSystemScorer
  2. Molecular+Fisher (unsupervised BSDT channels)
  3. Molecular+QuadSurf (supervised BSDT channels)
  4. Molecular+ExpoGate (supervised BSDT channels)

No-leakage protocol (identical for ALL variants):
  (i)   Expanding window: train on [0, t], test on t+1
  (ii)  StandardScaler fit on training only
  (iii) Frozen hyperparameters (from pre-crisis 2005Q1-2007Q3)
  (iv)  Fixed threshold (μ+3σ from pre-crisis scores)
  (v)   No label access at test time

KEY FIX from previous run: QuadSurf/ExpoGate are supervised.
They need crisis labels in train. The expanding window naturally
provides these once t >= 2007Q4 (first crisis quarter). For early
windows with no crisis data, we fall back to Fisher (unsupervised).
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

with open(os.path.join(CACHE_DIR, 'gsib_real_meta.json'), encoding='utf-8') as f:
    meta = json.load(f)

dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:X_3d.shape[0]]
T, N, d = X_3d.shape

FEATURE_NAMES = ['loan_to_asset', 'equity_ratio', 'npl_ratio', 'roa', 'funding_cost']

CRISIS_QUARTERS = {
    '2007-12-31','2008-03-31','2008-06-30','2008-09-30',
    '2008-12-31','2009-03-31','2009-06-30',
    '2020-03-31','2020-06-30',
    '2011-09-30','2011-12-31','2012-03-31','2012-06-30',
}
y_crisis = np.array([1 if str(d.date()) in CRISIS_QUARTERS else 0
                     for d in dates])

print(f'Data source: FDIC call reports + ECB MIR + World Bank GFDD')
print(f'Panel: T={T} quarters, N={N} G-SIBs, d={d} features')
print(f'Features: {FEATURE_NAMES}')
print(f'Banks: {len(meta)} G-SIBs (JPMorgan, BofA, Citi, Wells Fargo, etc.)')
print(f'Date range: {dates[0].date()} to {dates[-1].date()}')
print(f'Crisis quarters: {int(y_crisis.sum())}/{T}')

# ══════════════════════════════════════════════════════════════════
#  Frozen hyperparameters (from pre-crisis validation)
# ══════════════════════════════════════════════════════════════════
FROZEN_PARAMS_BASE = dict(
    epsilon=1.0, sigma_lj=1.0, alpha_radial=0.1, eta=0.01,
    iterations=80, k_neighbors=10, max_samples=2000,
    use_fused=True,          # FusedSystemScorer for base
    use_bsdt_damping=True,
    normalize=False,
)
FROZEN_PARAMS_POSTHOC = dict(
    epsilon=1.0, sigma_lj=1.0, alpha_radial=0.1, eta=0.01,
    iterations=80, k_neighbors=10, max_samples=2000,
    use_fused=False,         # no FusedSystemScorer; posthoc instead
    use_bsdt_damping=True,
    normalize=False,
)

BURN_IN = 4
calib_end = pd.Timestamp('2007-09-30')
n_calib = int((dates <= calib_end).sum())

# ══════════════════════════════════════════════════════════════════
#  Helper: reconstruct subsampling indices (same RNG as engine)
# ══════════════════════════════════════════════════════════════════
def get_sim_normal_mask(y_train, n_sim, max_samples):
    """Reconstruct which training points were in the simulation."""
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


# ══════════════════════════════════════════════════════════════════
#  Run all variants
# ══════════════════════════════════════════════════════════════════
VARIANTS = ['base', 'fisher', 'quadsurf', 'expogate']
all_results = {}

for variant in VARIANTS:
    gc.collect()
    label = 'Molecular (FusedScorer)' if variant == 'base' else f'Molecular+{variant.capitalize()}'
    is_base = (variant == 'base')
    is_supervised = variant in ('quadsurf', 'expogate')

    print(f'\n{"="*70}')
    print(f'  {label}  (strict no-leakage, expanding window)')
    print(f'  Data: Real-world FDIC/ECB/WB G-SIB panel')
    print(f'{"="*70}')

    params = FROZEN_PARAMS_BASE if is_base else FROZEN_PARAMS_POSTHOC
    q_scores = np.full(T, np.nan)
    t0 = time.time()

    for t in range(BURN_IN, T - 1):
        # ── Training: quarters 0..t ──
        n_train_q = t + 1
        X_train_raw = X_3d[:n_train_q].reshape(n_train_q * N, d)

        y_train = np.zeros(n_train_q * N, dtype=int)
        for t_idx in range(n_train_q):
            if str(dates[t_idx].date()) in CRISIS_QUARTERS:
                y_train[t_idx * N:(t_idx + 1) * N] = 1

        # ── Scaler fit on TRAINING only ──
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train_raw).astype(np.float64)

        # ── Test quarter t+1 (NEVER in training) ──
        X_test_raw = X_3d[t + 1].reshape(N, d)
        X_test = scaler.transform(X_test_raw).astype(np.float64)

        # ── Phase 1: MolecularEngine on training data ──
        eng = MolecularEngine(**params)
        _ = eng.fit_score(X_train, y_train)

        if is_base:
            # ── Base: score test with fitted FusedSystemScorer ──
            if eng.fused_scorer is not None:
                test_scores = eng.fused_scorer.score(X_test)
            elif hasattr(eng, 'alarm'):
                test_scores = eng.alarm.score(X_test)
            else:
                test_scores = np.linalg.norm(X_test - X_test.mean(axis=0), axis=1)
        else:
            # ── Posthoc: BSDT channels → correction layer ──
            X_final = eng.X_final_
            normal_mask_sim = get_sim_normal_mask(
                y_train, len(X_final), params['max_samples'])

            X_ref = X_final[normal_mask_sim]
            if len(X_ref) < 2:
                X_ref = X_final

            k_bsdt = min(10, max(len(X_ref) - 1, 1))
            bsdt = BSDTChannels(k=k_bsdt)
            bsdt.fit(X_ref)

            # Channels on training data (for fitting posthoc)
            ch_train = bsdt.channels(X_train)
            C_train = np.column_stack([ch_train['delta_C'], ch_train['delta_G'],
                                       ch_train['delta_A'], ch_train['delta_T']])

            # Channels on test data (for scoring)
            ch_test = bsdt.channels(X_test)
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
                        # Pre-crisis: no labels → fall back to Fisher
                        layer = _MFLSFisherBSDT()
                        layer.fit(C_train)
                        test_scores = layer.score(C_test)

                elif variant == 'expogate':
                    if n_crisis_train > 0:
                        layer = _MFLSExpoGate(ridge_alpha=1.0,
                                              smooth_sigma=1.0, gate_scale=3.0)
                        layer.fit(C_train, y_train.astype(float))
                        test_scores = layer.score(C_test)
                    else:
                        # Pre-crisis: no labels → fall back to Fisher
                        layer = _MFLSFisherBSDT()
                        layer.fit(C_train)
                        test_scores = layer.score(C_test)

            except Exception as e:
                # Fallback: raw BSDT energy
                test_scores = bsdt.energy(X_test)

            del bsdt

        q_scores[t + 1] = float(test_scores.mean())

        ds = str(dates[t + 1].date())
        crisis_mark = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
        if (t + 1) % 10 == 0 or ds in CRISIS_QUARTERS:
            print(f'  t={t+1:3d}  {ds}  score={q_scores[t+1]:.4f}{crisis_mark}')

        del eng
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

    # GFC-only AUROC
    gfc_mask = np.array([str(dates[i].date()) in
        {'2007-12-31','2008-03-31','2008-06-30','2008-09-30',
         '2008-12-31','2009-03-31','2009-06-30'}
        for i in range(T)])
    gfc_or_norm = valid & (gfc_mask | (y_crisis == 0))
    auroc_gfc = roc_auc_score(y_crisis[gfc_or_norm], q_scores[gfc_or_norm]) \
        if gfc_or_norm.sum() > 2 else float('nan')

    print(f'\n  {label} — Results:')
    print(f'  AUROC (full):   {auroc:.4f}')
    print(f'  AUROC (GFC):    {auroc_gfc:.4f}')
    print(f'  Threshold:      {FIXED_THR:.4f}  (μ+3σ, frozen)')
    print(f'  TP={TP}  FP={FP}  FN={FN}  TN={TN}')
    print(f'  FAR:            {far:.1f}%')
    print(f'  Recall:         {recall:.1f}%')
    print(f'  Precision:      {prec:.1f}%')
    print(f'  Time:           {elapsed:.0f}s')

    # Alarm timeline
    print(f'\n  Alarms:')
    for i in range(T):
        if np.isnan(q_scores[i]):
            continue
        alarm = q_scores[i] >= FIXED_THR
        ds = str(dates[i].date())
        crisis = ds in CRISIS_QUARTERS
        if alarm or crisis:
            if crisis and alarm:  tag = 'CRISIS + ALARM ✓'
            elif crisis:          tag = 'CRISIS (missed) ✗'
            elif alarm:           tag = 'FALSE ALARM'
            print(f'    {ds}  score={q_scores[i]:.4f}  {tag}')

    all_results[variant] = {
        'label': label,
        'auroc': float(auroc),
        'auroc_gfc': float(auroc_gfc),
        'far': float(far),
        'recall': float(recall),
        'prec': float(prec),
        'tp': TP, 'fp': FP, 'fn': FN, 'tn': TN,
        'threshold': float(FIXED_THR),
        'mu_cal': float(mu_cal),
        'std_cal': float(std_cal),
        'time': float(elapsed),
        'scores': {str(dates[i].date()): float(q_scores[i])
                   for i in range(T) if not np.isnan(q_scores[i])},
    }

# ══════════════════════════════════════════════════════════════════
#  Final Summary
# ══════════════════════════════════════════════════════════════════
print(f'\n\n{"="*78}')
print(f'  FINAL COMPARISON: All Variants — Strict No-Data-Leakage')
print(f'  Data: Real-world FDIC/ECB/WB G-SIB panel (T=76, N=25)')
print(f'{"="*78}')
print(f'  {"Variant":<25s}  {"AUROC":>6s}  {"GFC-AUC":>7s}  {"FAR%":>6s}  {"Recall%":>8s}  {"Prec%":>6s}  {"TP":>3s}  {"FP":>3s}  {"Time":>5s}')
print(f'  {"-"*25}  {"-"*6}  {"-"*7}  {"-"*6}  {"-"*8}  {"-"*6}  {"-"*3}  {"-"*3}  {"-"*5}')

for v in VARIANTS:
    r = all_results[v]
    print(f'  {r["label"]:<25s}  {r["auroc"]:6.4f}  {r["auroc_gfc"]:7.4f}  {r["far"]:5.1f}%  {r["recall"]:7.1f}%  {r["prec"]:5.1f}%  {r["tp"]:3d}  {r["fp"]:3d}  {r["time"]:4.0f}s')

# Best variant by AUROC
best = max(VARIANTS, key=lambda v: all_results[v]['auroc'])
print(f'\n  Best by AUROC:     {all_results[best]["label"]} ({all_results[best]["auroc"]:.4f})')
best_gfc = max(VARIANTS, key=lambda v: all_results[v]['auroc_gfc'])
print(f'  Best by GFC-AUROC: {all_results[best_gfc]["label"]} ({all_results[best_gfc]["auroc_gfc"]:.4f})')

# Save
results_path = os.path.join(ROOT, 'no_leakage_all_variants.json')
with open(results_path, 'w', encoding='utf-8') as f:
    json.dump(all_results, f, indent=2)
print(f'\n  Results saved: {results_path}')
print('Done.')
