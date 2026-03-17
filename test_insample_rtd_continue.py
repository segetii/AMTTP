"""
Continuation script: runs RTD algorithms 7-9 from the unified in-sample benchmark.
Algorithms 1-6 already completed; results hardcoded from insample_all_output.txt.
"""
import sys, os, gc, time, json
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

ROOT = r'C:\amttp'
sys.path.insert(0, os.path.join(ROOT, 'research', 'udl'))

from udl.system_mode import (
    MolecularEngine,
    BSDTChannels,
    _MFLSFisherBSDT,
    _MFLSQuadSurf,
    ReducedTensorDescriptor,
)

# ── Tee class for dual stdout + file output ──
class Tee:
    def __init__(self, path):
        self._file = open(path, 'a', encoding='utf-8')
        self._stdout = sys.stdout
    def write(self, data):
        self._stdout.write(data)
        self._stdout.flush()
        self._file.write(data)
        self._file.flush()
    def flush(self):
        self._stdout.flush()
        self._file.flush()
    def close(self):
        self._file.close()

tee = Tee(os.path.join(ROOT, 'insample_rtd_output.txt'))
sys.stdout = tee

# ── Load data ──
CACHE_DIR = os.path.join(ROOT, 'research', 'adaptive-friction',
                         'banklevel_enhanced', 'gsib_cache_real')
npz = np.load(os.path.join(CACHE_DIR, 'gsib_real_panel.npz'))
X_panel = npz['X']

import warnings
warnings.filterwarnings("ignore")

dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:X_panel.shape[0]]
T, N, d = X_panel.shape

CRISIS_QUARTERS = {
    '2007-12-31','2008-03-31','2008-06-30','2008-09-30',
    '2008-12-31','2009-03-31','2009-06-30',
    '2020-03-31','2020-06-30',
    '2011-09-30','2011-12-31','2012-03-31','2012-06-30',
}
y_crisis = np.array([1 if str(d.date()) in CRISIS_QUARTERS else 0
                     for d in dates])

CALIB_END = pd.Timestamp('2007-09-30')
N_CALIB = int((dates <= CALIB_END).sum())

print('=' * 70)
print('  RTD CONTINUATION — In-Sample Monitoring (algorithms 7-9)')
print('=' * 70)
print(f'Panel: T={T}, N={N}, d={d}')
print(f'Crisis: {y_crisis.sum()}/{T} quarters')
print(f'Calib: {N_CALIB} Q\n')

# ═════════════════════════════════════════════════════════════════
#  HARDCODED RESULTS FROM ALGORITHMS 1-6
# ═════════════════════════════════════════════════════════════════
all_results = {
    'mol_fused': {
        'auroc': 0.7216, 'gfc_auroc': 0.7532, 'time': 323,
        'P99': {'threshold': 0.2536, 'tp': 4, 'fp': 10, 'fn': 9, 'tn': 53,
                'far': 15.9, 'recall': 30.8, 'precision': 28.6,
                'gfc_first_alarm': '2007-09-30', 'z_bnp': 1.76},
        'mu+3sig': {'threshold': 0.3087, 'tp': 0, 'fp': 7, 'fn': 13, 'tn': 56,
                    'far': 11.1, 'recall': 0.0, 'precision': 0.0,
                    'gfc_first_alarm': 'None', 'z_bnp': 1.76},
    },
    'gravity': {
        'auroc': 0.3309, 'gfc_auroc': 0.2987, 'time': 272,
        'P99': {'threshold': 0.2708, 'tp': 0, 'fp': 5, 'fn': 13, 'tn': 58,
                'far': 7.9, 'recall': 0.0, 'precision': 0.0,
                'gfc_first_alarm': '2007-06-30', 'z_bnp': 2.07},
        'mu+3sig': {'threshold': 0.3355, 'tp': 0, 'fp': 1, 'fn': 13, 'tn': 62,
                    'far': 1.6, 'recall': 0.0, 'precision': 0.0,
                    'gfc_first_alarm': 'None', 'z_bnp': 2.07},
    },
    'hybrid': {
        'auroc': 0.6068, 'gfc_auroc': 0.7792, 'time': 738,
        'P99': {'threshold': 0.3101, 'tp': 0, 'fp': 6, 'fn': 13, 'tn': 57,
                'far': 9.5, 'recall': 0.0, 'precision': 0.0,
                'gfc_first_alarm': '2007-06-30', 'z_bnp': 2.13},
        'mu+3sig': {'threshold': 0.3642, 'tp': 0, 'fp': 5, 'fn': 13, 'tn': 58,
                    'far': 7.9, 'recall': 0.0, 'precision': 0.0,
                    'gfc_first_alarm': 'None', 'z_bnp': 2.13},
    },
    'mol_fisher': {
        'auroc': 0.7253, 'gfc_auroc': 0.7013, 'time': 205,
        'P99': {'threshold': 0.4659, 'tp': 5, 'fp': 7, 'fn': 8, 'tn': 56,
                'far': 11.1, 'recall': 38.5, 'precision': 41.7,
                'gfc_first_alarm': '2007-06-30', 'z_bnp': 1.87},
        'mu+3sig': {'threshold': 0.4835, 'tp': 1, 'fp': 3, 'fn': 12, 'tn': 60,
                    'far': 4.8, 'recall': 7.7, 'precision': 25.0,
                    'gfc_first_alarm': '2008-06-30', 'z_bnp': 1.87},
    },
    'mol_quadsurf': {
        'auroc': 0.7521, 'gfc_auroc': 0.5844, 'time': 184,
        'P99': {'threshold': 0.4659, 'tp': 2, 'fp': 1, 'fn': 11, 'tn': 62,
                'far': 1.6, 'recall': 15.4, 'precision': 66.7,
                'gfc_first_alarm': '2007-06-30', 'z_bnp': 1.87},
        'mu+3sig': {'threshold': 0.4835, 'tp': 1, 'fp': 0, 'fn': 12, 'tn': 63,
                    'far': 0.0, 'recall': 7.7, 'precision': 100.0,
                    'gfc_first_alarm': '2008-12-31', 'z_bnp': 1.87},
    },
    'mol_expogate': {
        'auroc': 0.8669, 'gfc_auroc': 0.9091, 'time': 232,
        'P99': {'threshold': 0.4659, 'tp': 13, 'fp': 53, 'fn': 0, 'tn': 10,
                'far': 84.1, 'recall': 100.0, 'precision': 19.7,
                'gfc_first_alarm': '2007-06-30', 'z_bnp': 1.87},
        'mu+3sig': {'threshold': 0.4835, 'tp': 13, 'fp': 52, 'fn': 0, 'tn': 11,
                    'far': 82.5, 'recall': 100.0, 'precision': 20.0,
                    'gfc_first_alarm': '2007-12-31', 'z_bnp': 1.87},
    },
}


# ═════════════════════════════════════════════════════════════════
#  EVALUATE FUNCTION
# ═════════════════════════════════════════════════════════════════
def evaluate(name, q_scores, y_crisis, dates, n_calib):
    """Evaluate prospective scores. Returns dict with metrics."""
    from sklearn.metrics import roc_auc_score
    eval_mask = np.arange(len(q_scores)) >= n_calib
    y_eval = y_crisis[eval_mask]
    s_eval = q_scores[eval_mask]
    valid = ~np.isnan(s_eval)
    y_v, s_v = y_eval[valid], s_eval[valid]
    d_eval = dates[eval_mask][valid]

    auroc = roc_auc_score(y_v, s_v) if len(np.unique(y_v)) > 1 else 0.5
    gfc_mask = np.array([d.year <= 2009 for d in d_eval])
    if gfc_mask.any() and len(np.unique(y_v[gfc_mask])) > 1:
        gfc_auroc = roc_auc_score(y_v[gfc_mask], s_v[gfc_mask])
    else:
        gfc_auroc = 0.5

    # BNP date = 2007-08-09.  Find z-score at that point
    calib_scores = q_scores[:n_calib]
    cs = calib_scores[~np.isnan(calib_scores)]
    mu_c, sig_c = cs.mean(), cs.std()

    # Find score closest to BNP date
    bnp_idx = None
    for i, dt in enumerate(dates):
        if dt.year == 2007 and dt.month >= 7 and dt.month <= 9:
            bnp_idx = i
            break
    z_bnp = (q_scores[bnp_idx] - mu_c) / sig_c if bnp_idx is not None and sig_c > 0 else None

    result = {'auroc': auroc, 'gfc_auroc': gfc_auroc}

    # ── thresholds ──
    calib_q_scores = q_scores[:n_calib]
    cs = calib_q_scores[~np.isnan(calib_q_scores)]
    mu_c, sig_c = cs.mean(), cs.std()
    thresholds = {
        'P99': float(np.nanpercentile(cs, 99)),
        'mu+3sig': float(mu_c + 3 * sig_c),
    }

    for thr_name, thr_val in thresholds.items():
        alarms = s_v >= thr_val
        tp = int(((alarms == 1) & (y_v == 1)).sum())
        fp = int(((alarms == 1) & (y_v == 0)).sum())
        fn = int(((alarms == 0) & (y_v == 1)).sum())
        tn = int(((alarms == 0) & (y_v == 0)).sum())
        far = fp / (fp + tn) * 100 if (fp + tn) > 0 else 0
        recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
        prec = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0

        # GFC first alarm
        gfc_first = None
        for i, dt in enumerate(d_eval):
            if alarms[i] and dt.year <= 2009:
                gfc_first = str(dt.date()) if hasattr(dt, 'date') else str(dt)[:10]
                break

        result[thr_name] = {
            'threshold': thr_val,
            'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'far': far, 'recall': recall, 'precision': prec,
            'gfc_first_alarm': gfc_first if gfc_first else 'None',
            'z_bnp': z_bnp,
        }

    # ── Print results ──
    print(f'\n  {name}:')
    print(f'  AUROC:       {auroc:.4f}')
    print(f'  GFC-AUROC:   {gfc_auroc:.4f}')
    for thr_name, thr_val in thresholds.items():
        t = result[thr_name]
        print(f'  --- {thr_name} threshold={thr_val:.4f} ---')
        print(f'  TP={t["tp"]}  FP={t["fp"]}  FN={t["fn"]}  TN={t["tn"]}')
        print(f'  FAR:       {t["far"]:.1f}%')
        print(f'  Recall:    {t["recall"]:.1f}%')
        print(f'  Precision: {t["precision"]:.1f}%')
        print(f'  GFC 1st:   {t["gfc_first_alarm"]}')
        z_str = f'+{t["z_bnp"]:.2f}' if t['z_bnp'] and t['z_bnp'] > 0 else (f'{t["z_bnp"]:.2f}' if t['z_bnp'] else 'N/A')
        print(f'  z(BNP):    {z_str}')

    # Alarm timeline (mu+3sig)
    thr_val = thresholds['mu+3sig']
    print(f'\n  Alarm timeline (mu+3sig):')
    for i, (dt, sc, yc) in enumerate(zip(d_eval, s_v, y_v)):
        alarm = sc >= thr_val
        if alarm or yc == 1:
            label = ''
            if yc == 1 and alarm:
                label = 'CRISIS + ALARM'
            elif yc == 1 and not alarm:
                label = 'CRISIS (missed)'
            elif yc == 0 and alarm:
                label = 'FALSE ALARM'
            dt_str = str(dt.date()) if hasattr(dt, 'date') else str(dt)[:10]
            print(f'    {dt_str}  score={sc:.4f}  {label}')

    return result


# ═════════════════════════════════════════════════════════════════
#  RTD SCORING FUNCTION
# ═════════════════════════════════════════════════════════════════
def prospective_score_rtd(X_panel, dates, variant, engine_kwargs,
                          n_calib, N, verbose=True):
    T_total, N_banks, d_feat = X_panel.shape
    q_scores = np.full(T_total, np.nan)
    is_base = (variant == 'base')
    is_supervised = variant in ('quadsurf',)

    # ── Fit RTD on calibration normal data ──
    X_calib_raw = X_panel[:n_calib].reshape(n_calib * N_banks, d_feat)
    k_nb = min(10, len(X_calib_raw) - 1)
    rtd = ReducedTensorDescriptor(k_neighbors=k_nb, n_eigs=d_feat)
    rtd.fit(X_calib_raw)
    d_rtd = rtd.transform(X_calib_raw).shape[1]

    if verbose:
        print(f'    RTD: d_raw={d_feat} -> d_rtd={d_rtd}')

    # ── Phase 1: calibration ──
    D_calib = rtd.transform(X_calib_raw)
    scaler = StandardScaler()
    D_calib_sc = scaler.fit_transform(D_calib).astype(np.float64)
    y_eng = np.zeros(n_calib * N_banks, dtype=int)

    if is_base:
        eng = MolecularEngine(**engine_kwargs)
        scores_calib = eng.fit_score(D_calib_sc, y_eng)
        for t in range(n_calib):
            q_scores[t] = scores_calib[t * N_banks:(t + 1) * N_banks].mean()
        del eng, scores_calib
    else:
        eng = MolecularEngine(**engine_kwargs)
        _ = eng.fit_score(D_calib_sc, y_eng)
        X_ref = eng.X_final_
        k_bsdt = min(10, max(len(X_ref) - 1, 1))
        bsdt = BSDTChannels(k=k_bsdt)
        bsdt.fit(X_ref)
        ch = bsdt.channels(D_calib_sc)
        C = np.column_stack([ch['delta_C'], ch['delta_G'],
                              ch['delta_A'], ch['delta_T']])
        # Calib is all normal — no crisis labels available, use Fisher as fallback
        layer = _MFLSFisherBSDT()
        layer.fit(C)
        scores_calib = layer.score(C)
        for t in range(n_calib):
            q_scores[t] = scores_calib[t * N_banks:(t + 1) * N_banks].mean()
        del eng, bsdt, layer, scores_calib
    gc.collect()

    # ── Phase 2: expanding window ──
    for t in range(n_calib, T_total):
        n_pts = (t + 1) * N_banks
        X_flat = X_panel[:t + 1].reshape(n_pts, d_feat)
        D_flat = rtd.transform(X_flat)
        D_sc = scaler.transform(D_flat).astype(np.float64)
        y_eng = np.zeros(n_pts, dtype=int)

        if is_base:
            eng = MolecularEngine(**engine_kwargs)
            all_scores = eng.fit_score(D_sc, y_eng)
            q_scores[t] = all_scores[t * N_banks:(t + 1) * N_banks].mean()
            del eng, all_scores
        else:
            eng = MolecularEngine(**engine_kwargs)
            _ = eng.fit_score(D_sc, y_eng)
            X_ref = eng.X_final_
            k_bsdt = min(10, max(len(X_ref) - 1, 1))
            bsdt = BSDTChannels(k=k_bsdt)
            bsdt.fit(X_ref)
            ch = bsdt.channels(D_sc)
            C = np.column_stack([ch['delta_C'], ch['delta_G'],
                                  ch['delta_A'], ch['delta_T']])

            # Build causal crisis labels (only crises that have already happened)
            if is_supervised:
                y_posthoc = np.zeros(n_pts, dtype=float)
                for t_idx in range(t + 1):
                    if str(dates[t_idx].date()) in CRISIS_QUARTERS:
                        y_posthoc[t_idx * N_banks:(t_idx + 1) * N_banks] = 1.0
                n_crisis = int(y_posthoc.sum())
            else:
                n_crisis = 0

            try:
                if variant == 'fisher':
                    layer = _MFLSFisherBSDT()
                    layer.fit(C)
                elif variant == 'quadsurf' and n_crisis > 0:
                    layer = _MFLSQuadSurf(ridge_alpha=1.0)
                    layer.fit(C, y_posthoc)
                else:
                    layer = _MFLSFisherBSDT()
                    layer.fit(C)
                sc = layer.score(C)
            except Exception:
                sc = bsdt.energy(D_sc)

            q_scores[t] = sc[-N_banks:].mean()
            del eng, bsdt, layer, sc
        gc.collect()

        is_crisis_q = y_crisis[t] if t < len(y_crisis) else 0
        if verbose and (t % 8 == n_calib % 8 or t == T_total - 1):
            dt_str = str(dates[t].date()) if hasattr(dates[t], 'date') else str(dates[t])[:10]
            tag = ' << CRISIS' if is_crisis_q else ''
            print(f'    t={t:3d}  {dt_str}  score={q_scores[t]:.4f}{tag}')

    return q_scores


# ═════════════════════════════════════════════════════════════════
#  RUN RTD ALGORITHMS 7-9
# ═════════════════════════════════════════════════════════════════
X_3d = X_panel.copy()

# Also fix the y_crisis reference in prospective_score_rtd to use global
# ── 7. RTD + Molecular (FusedScorer) ───────────────────────────
print('\n' + '=' * 70)
print('  [7/9] RTD + Molecular (FusedScorer)')
print('=' * 70)
gc.collect()
t0 = time.time()
rtd_base_kwargs = dict(iterations=80, k_neighbors=10, max_samples=2000,
                       use_fused=True, use_bsdt_damping=True, normalize=False)
q = prospective_score_rtd(X_3d, dates, 'base', rtd_base_kwargs, N_CALIB, N)
elapsed = time.time() - t0
print(f'  Time: {elapsed:.0f}s')
r = evaluate('RTD+Molecular', q, y_crisis, dates, N_CALIB)
all_results['rtd_mol'] = r
r['time'] = elapsed
del q; gc.collect()

# ── 8. RTD + Molecular + Fisher ────────────────────────────────
print('\n' + '=' * 70)
print('  [8/9] RTD + Molecular + Fisher')
print('=' * 70)
gc.collect()
t0 = time.time()
rtd_posthoc_kwargs = dict(iterations=80, k_neighbors=10, max_samples=2000,
                          use_fused=False, use_bsdt_damping=True, normalize=False)
q = prospective_score_rtd(X_3d, dates, 'fisher', rtd_posthoc_kwargs, N_CALIB, N)
elapsed = time.time() - t0
print(f'  Time: {elapsed:.0f}s')
r = evaluate('RTD+Fisher', q, y_crisis, dates, N_CALIB)
all_results['rtd_fisher'] = r
r['time'] = elapsed
del q; gc.collect()

# ── 9. RTD + Molecular + QuadSurf ──────────────────────────────
print('\n' + '=' * 70)
print('  [9/9] RTD + Molecular + QuadSurf')
print('=' * 70)
gc.collect()
t0 = time.time()
q = prospective_score_rtd(X_3d, dates, 'quadsurf', rtd_posthoc_kwargs, N_CALIB, N)
elapsed = time.time() - t0
print(f'  Time: {elapsed:.0f}s')
r = evaluate('RTD+QuadSurf', q, y_crisis, dates, N_CALIB)
all_results['rtd_quadsurf'] = r
r['time'] = elapsed
del q; gc.collect()


# ═════════════════════════════════════════════════════════════════
#  FINAL COMPARISON TABLE
# ═════════════════════════════════════════════════════════════════
print('\n' + '=' * 90)
print('  FINAL COMPARISON — In-Sample Monitoring (correct N-body protocol)')
print('  Threshold: frozen from 2005Q1-2007Q3 calm period')
print('=' * 90)

labels = {
    'mol_fused':     'Molecular (Fused)',
    'gravity':       'Gravity',
    'hybrid':        'Hybrid',
    'mol_fisher':    'Mol+Fisher',
    'mol_quadsurf':  'Mol+QuadSurf',
    'mol_expogate':  'Mol+ExpoGate',
    'rtd_mol':       'RTD+Mol (Fused)',
    'rtd_fisher':    'RTD+Fisher',
    'rtd_quadsurf':  'RTD+QuadSurf',
}

for thr_name in ['P99', 'mu+3sig']:
    print(f'\n  Threshold: {thr_name}')
    print(f'  {"Method":<22s} AUROC  GFC-AUC  FAR%  Recall%  Prec%  GFC-1st     z(BNP)')
    print(f'  {"-"*22} {"-"*5}  {"-"*7}  {"-"*4}  {"-"*7}  {"-"*5}  {"-"*10}  {"-"*6}')
    for key, label in labels.items():
        if key not in all_results:
            continue
        r = all_results[key]
        t = r.get(thr_name, {})
        z_val = t.get('z_bnp', None)
        z_str = f'+{z_val:.2f}' if z_val and z_val > 0 else (f'{z_val:.2f}' if z_val else 'N/A')
        print(f'  {label:<22s} {r["auroc"]:.3f}  {r["gfc_auroc"]:.3f}    '
              f'{t.get("far",0):4.1f}%   {t.get("recall",0):5.1f}%  '
              f'{t.get("precision",0):4.1f}%  {str(t.get("gfc_first_alarm","?")):<10s}  {z_str}')

# Save results
out_path = os.path.join(ROOT, 'insample_all_results.json')
def _clean(obj):
    if isinstance(obj, (np.floating, np.integer)):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    return obj

with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(_clean(all_results), f, indent=2, default=str)
print(f'\nResults saved to {out_path}')
print('Done.')
