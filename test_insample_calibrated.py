"""
In-Sample Monitoring with ADAPTIVE CALIBRATION
===============================================
Re-runs all 8 completed algorithms, saves raw q_scores, and evaluates with:
  1. Fixed P99 threshold (baseline)
  2. Fixed mu+3sig threshold (baseline)
  3. Adaptive rolling z-score (recommended fix)
  4. Adaptive rolling percentile

The adaptive approach recomputes the threshold at each quarter t using
all scores s_0..s_{t-1} (strictly causal), eliminating score drift.
"""
import sys, os, time, warnings, json, gc
sys.stdout.reconfigure(line_buffering=True)

class Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, s):
        for st in self.streams:
            st.write(s)
            st.flush()
    def flush(self):
        for st in self.streams:
            st.flush()

ROOT = r'C:\amttp'
_logf = open(os.path.join(ROOT, 'insample_calibrated_output.txt'), 'w', encoding='utf-8')
sys.stdout = Tee(sys.__stdout__, _logf)

sys.path.insert(0, os.path.join(ROOT, 'research', 'udl'))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from udl.system_mode import (
    MolecularEngine, GravityModeEngine, HybridGravityEngine,
    BSDTChannels, FusedSystemScorer, ReducedTensorDescriptor,
    _MFLSFisherBSDT, _MFLSQuadSurf, _MFLSExpoGate,
)
warnings.filterwarnings("ignore")

# ═══════════ Data ═══════════
CACHE_DIR = os.path.join(ROOT, 'research', 'adaptive-friction',
                         'banklevel_enhanced', 'gsib_cache_real')
npz = np.load(os.path.join(CACHE_DIR, 'gsib_real_panel.npz'))
X_3d = npz['X']

dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:X_3d.shape[0]]
T, N, d = X_3d.shape

CRISIS_QUARTERS = {
    '2007-12-31','2008-03-31','2008-06-30','2008-09-30',
    '2008-12-31','2009-03-31','2009-06-30',
    '2020-03-31','2020-06-30',
    '2011-09-30','2011-12-31','2012-03-31','2012-06-30',
}
y_crisis = np.array([1 if str(dt.date()) in CRISIS_QUARTERS else 0 for dt in dates])

CALIB_END = pd.Timestamp('2007-09-30')
N_CALIB = int((dates <= CALIB_END).sum())

print('=' * 80)
print('  IN-SAMPLE MONITORING WITH ADAPTIVE CALIBRATION')
print('  Protocol: expanding window | y=zeros | in-sample | q_scores saved')
print('=' * 80)
print(f'Panel: T={T}, N={N}, d={d}, Crisis: {y_crisis.sum()}/{T}')
print(f'Calib: {N_CALIB} Q  ({dates[0].date()} → {dates[N_CALIB-1].date()})\n')


# ═══════════════════════════════════════════════════════════════
#  SCORING FUNCTIONS (same as test_insample_all.py)
# ═══════════════════════════════════════════════════════════════
def prospective_score(X_panel, dates, engine_cls, engine_kwargs,
                      n_calib, N_banks, verbose=True):
    T_total, N_b, d_feat = X_panel.shape
    q_scores = np.full(T_total, np.nan)
    X_calib = X_panel[:n_calib].reshape(n_calib * N_b, d_feat)
    y_calib = np.zeros(n_calib * N_b, dtype=int)
    eng = engine_cls(**engine_kwargs)
    sc = eng.fit_score(X_calib, y_calib)
    for t in range(n_calib):
        q_scores[t] = sc[t * N_b:(t + 1) * N_b].mean()
    del eng, sc; gc.collect()

    for t in range(n_calib, T_total):
        n_pts = (t + 1) * N_b
        X_up = X_panel[:t + 1].reshape(n_pts, d_feat)
        y_d = np.zeros(n_pts, dtype=int)
        eng = engine_cls(**engine_kwargs)
        sc = eng.fit_score(X_up, y_d)
        q_scores[t] = sc[-N_b:].mean()
        del eng, sc; gc.collect()
        if verbose and ((t - n_calib) % 16 == 0 or t == T_total - 1):
            ds = str(dates[t].date())
            tag = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
            print(f'    t={t:3d}  {ds}  score={q_scores[t]:.4f}{tag}')
    return q_scores


def prospective_score_posthoc(X_panel, dates, posthoc_name, engine_kwargs,
                              n_calib, N_banks, verbose=True):
    T_total, N_b, d_feat = X_panel.shape
    q_scores = np.full(T_total, np.nan)
    is_supervised = posthoc_name in ('quadsurf', 'expogate')

    X_calib = X_panel[:n_calib].reshape(n_calib * N_b, d_feat)
    y_eng = np.zeros(n_calib * N_b, dtype=int)
    eng = MolecularEngine(**engine_kwargs)
    _ = eng.fit_score(X_calib, y_eng)
    X_ref = eng.X_final_
    k_bsdt = min(10, max(len(X_ref) - 1, 1))
    bsdt = BSDTChannels(k=k_bsdt)
    bsdt.fit(X_ref)
    ch = bsdt.channels(X_calib)
    C_calib = np.column_stack([ch['delta_C'], ch['delta_G'],
                                ch['delta_A'], ch['delta_T']])
    layer = _MFLSFisherBSDT()
    layer.fit(C_calib)
    sc = layer.score(C_calib)
    for t in range(n_calib):
        q_scores[t] = sc[t * N_b:(t + 1) * N_b].mean()
    del eng, bsdt, layer; gc.collect()

    for t in range(n_calib, T_total):
        gc.collect()
        n_pts = (t + 1) * N_b
        X_up = X_panel[:t + 1].reshape(n_pts, d_feat)
        y_eng = np.zeros(n_pts, dtype=int)
        eng = MolecularEngine(**engine_kwargs)
        _ = eng.fit_score(X_up, y_eng)
        X_ref = eng.X_final_
        k_bsdt = min(10, max(len(X_ref) - 1, 1))
        bsdt = BSDTChannels(k=k_bsdt)
        bsdt.fit(X_ref)
        ch = bsdt.channels(X_up)
        C_all = np.column_stack([ch['delta_C'], ch['delta_G'],
                                  ch['delta_A'], ch['delta_T']])
        if is_supervised:
            y_ph = np.zeros(n_pts, dtype=float)
            for ti in range(t + 1):
                if str(dates[ti].date()) in CRISIS_QUARTERS:
                    y_ph[ti * N_b:(ti + 1) * N_b] = 1.0
            n_cr = int(y_ph.sum())
        else:
            n_cr = 0
        try:
            if posthoc_name == 'fisher':
                layer = _MFLSFisherBSDT(); layer.fit(C_all)
            elif posthoc_name == 'quadsurf' and n_cr > 0:
                layer = _MFLSQuadSurf(ridge_alpha=1.0); layer.fit(C_all, y_ph)
            elif posthoc_name == 'expogate' and n_cr > 0:
                layer = _MFLSExpoGate(ridge_alpha=1.0, smooth_sigma=1.0, gate_scale=3.0)
                layer.fit(C_all, y_ph)
            else:
                layer = _MFLSFisherBSDT(); layer.fit(C_all)
            sc = layer.score(C_all)
        except Exception:
            sc = bsdt.energy(X_up)
        q_scores[t] = sc[-N_b:].mean()
        del eng, bsdt, layer; gc.collect()
        if verbose and ((t - n_calib) % 16 == 0 or t == T_total - 1):
            ds = str(dates[t].date())
            tag = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
            print(f'    t={t:3d}  {ds}  score={q_scores[t]:.4f}{tag}')
    return q_scores


def prospective_score_rtd(X_panel, dates, variant, engine_kwargs,
                          n_calib, N_banks, verbose=True):
    T_total, N_b, d_feat = X_panel.shape
    q_scores = np.full(T_total, np.nan)
    is_base = (variant == 'base')
    is_supervised = variant in ('quadsurf',)

    X_calib_raw = X_panel[:n_calib].reshape(n_calib * N_b, d_feat)
    k_nb = min(10, len(X_calib_raw) - 1)
    rtd = ReducedTensorDescriptor(k_neighbors=k_nb, n_eigs=d_feat)
    rtd.fit(X_calib_raw)
    d_rtd = rtd.transform(X_calib_raw).shape[1]
    if verbose:
        print(f'    RTD: d={d_feat} -> d_rtd={d_rtd}')

    D_calib = rtd.transform(X_calib_raw)
    scaler = StandardScaler()
    D_calib_sc = scaler.fit_transform(D_calib).astype(np.float64)
    y_eng = np.zeros(n_calib * N_b, dtype=int)

    if is_base:
        eng = MolecularEngine(**engine_kwargs)
        sc = eng.fit_score(D_calib_sc, y_eng)
        for t in range(n_calib):
            q_scores[t] = sc[t * N_b:(t + 1) * N_b].mean()
        del eng, sc
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
        layer = _MFLSFisherBSDT(); layer.fit(C)
        sc = layer.score(C)
        for t in range(n_calib):
            q_scores[t] = sc[t * N_b:(t + 1) * N_b].mean()
        del eng, bsdt, layer, sc
    gc.collect()

    for t in range(n_calib, T_total):
        n_pts = (t + 1) * N_b
        X_flat = X_panel[:t + 1].reshape(n_pts, d_feat)
        D_flat = rtd.transform(X_flat)
        D_sc = scaler.transform(D_flat).astype(np.float64)
        y_eng = np.zeros(n_pts, dtype=int)
        if is_base:
            eng = MolecularEngine(**engine_kwargs)
            sc = eng.fit_score(D_sc, y_eng)
            q_scores[t] = sc[-N_b:].mean()
            del eng, sc
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
            if is_supervised:
                y_ph = np.zeros(n_pts, dtype=float)
                for ti in range(t + 1):
                    if str(dates[ti].date()) in CRISIS_QUARTERS:
                        y_ph[ti * N_b:(ti + 1) * N_b] = 1.0
                n_cr = int(y_ph.sum())
            else:
                n_cr = 0
            try:
                if variant == 'fisher':
                    layer = _MFLSFisherBSDT(); layer.fit(C)
                elif variant == 'quadsurf' and n_cr > 0:
                    layer = _MFLSQuadSurf(ridge_alpha=1.0); layer.fit(C, y_ph)
                else:
                    layer = _MFLSFisherBSDT(); layer.fit(C)
                sc = layer.score(C)
            except Exception:
                sc = bsdt.energy(D_sc)
            q_scores[t] = sc[-N_b:].mean()
            del eng, bsdt, layer, sc
        gc.collect()
        if verbose and ((t - n_calib) % 16 == 0 or t == T_total - 1):
            ds = str(dates[t].date())
            tag = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
            print(f'    t={t:3d}  {ds}  score={q_scores[t]:.4f}{tag}')
    return q_scores


# ═══════════════════════════════════════════════════════════════
#  ADAPTIVE CALIBRATION EVALUATION
# ═══════════════════════════════════════════════════════════════
def evaluate_all_thresholds(name, q_scores, y_crisis, dates, n_calib):
    """
    Evaluate with 4 thresholding strategies:
      1. Fixed P99 (from calm period only)
      2. Fixed mu+3sig (from calm period only)
      3. Adaptive rolling z-score: alarm if z_t > 3 using all past scores
      4. Adaptive rolling percentile: alarm if s_t > P99 of all past scores
    """
    valid = ~np.isnan(q_scores)
    q_v = q_scores[valid]
    y_v = y_crisis[valid]

    auroc = roc_auc_score(y_v, q_v) if 0 < y_v.sum() < len(y_v) else float('nan')

    # GFC-only AUROC
    gfc_start = np.where(dates >= pd.Timestamp('2006-01-01'))[0][0]
    gfc_end = np.where(dates <= pd.Timestamp('2010-06-30'))[0][-1] + 1
    gfc_sl = slice(gfc_start, gfc_end)
    gfc_v = valid[gfc_sl]
    if gfc_v.any() and 0 < y_crisis[gfc_sl][gfc_v].sum() < gfc_v.sum():
        gfc_auc = roc_auc_score(y_crisis[gfc_sl][gfc_v], q_scores[gfc_sl][gfc_v])
    else:
        gfc_auc = float('nan')

    # -- Calm-period stats --
    cs = q_scores[:n_calib]
    cs = cs[~np.isnan(cs)]
    mu_c, sig_c = cs.mean(), cs.std()
    thresh_p99 = np.percentile(cs, 99)
    thresh_m3s = mu_c + 3 * sig_c

    # -- Build adaptive thresholds --
    # At each quarter t, threshold is computed from scores s_0..s_{t-1}
    adaptive_z_thresh = np.full(len(dates), np.nan)
    adaptive_p99_thresh = np.full(len(dates), np.nan)
    adaptive_z_scores = np.full(len(dates), np.nan)  # the z-score itself

    for t in range(n_calib, len(dates)):
        past = q_scores[:t]
        past_valid = past[~np.isnan(past)]
        if len(past_valid) >= 3:
            mu_t = past_valid.mean()
            sig_t = past_valid.std()
            if sig_t > 1e-10:
                adaptive_z_thresh[t] = mu_t + 3 * sig_t
                adaptive_z_scores[t] = (q_scores[t] - mu_t) / sig_t
            else:
                adaptive_z_thresh[t] = mu_t + 0.01
                adaptive_z_scores[t] = 0.0
            adaptive_p99_thresh[t] = np.percentile(past_valid, 99)

    # z-score at BNP (2007-Q2 = index 9)
    bnp_idx = np.where(dates == pd.Timestamp('2007-06-30'))[0]
    z_bnp = float((q_scores[bnp_idx[0]] - mu_c) / sig_c) if len(bnp_idx) > 0 and sig_c > 1e-10 else None

    result = {'auroc': auroc, 'gfc_auroc': gfc_auc, 'z_bnp': z_bnp}

    # ── Evaluate each thresholding strategy ──
    strategies = {
        'Fixed P99': ('fixed', thresh_p99),
        'Fixed mu+3sig': ('fixed', thresh_m3s),
        'Adaptive z>3': ('adaptive_z', None),
        'Adaptive P99': ('adaptive_p99', None),
    }

    for strat_name, (mode, fixed_val) in strategies.items():
        alarms = np.zeros(len(dates), dtype=int)
        for t in range(n_calib, len(dates)):
            if np.isnan(q_scores[t]):
                continue
            if mode == 'fixed':
                alarms[t] = int(q_scores[t] >= fixed_val)
            elif mode == 'adaptive_z':
                if not np.isnan(adaptive_z_scores[t]):
                    alarms[t] = int(adaptive_z_scores[t] >= 3.0)
            elif mode == 'adaptive_p99':
                if not np.isnan(adaptive_p99_thresh[t]):
                    alarms[t] = int(q_scores[t] >= adaptive_p99_thresh[t])

        # Only evaluate post-calibration
        ev_mask = np.arange(len(dates)) >= n_calib
        a_ev = alarms[ev_mask]
        y_ev = y_crisis[ev_mask]
        v_ev = valid[ev_mask]
        a_v = a_ev[v_ev]
        y_ev_v = y_ev[v_ev]

        tp = int(((a_v == 1) & (y_ev_v == 1)).sum())
        fp = int(((a_v == 1) & (y_ev_v == 0)).sum())
        fn = int(((a_v == 0) & (y_ev_v == 1)).sum())
        tn = int(((a_v == 0) & (y_ev_v == 0)).sum())
        far = fp / (fp + tn) * 100 if (fp + tn) > 0 else 0
        recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
        prec = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0

        # GFC first alarm
        gfc_first = None
        for i in range(len(dates)):
            if alarms[i] and dates[i] <= pd.Timestamp('2009-06-30'):
                gfc_first = str(dates[i].date())
                break

        result[strat_name] = {
            'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'far': far, 'recall': recall, 'precision': prec,
            'gfc_first': gfc_first or 'None',
        }

    return result, q_scores, adaptive_z_scores


# ═══════════════════════════════════════════════════════════════
#  RUN ALL ALGORITHMS
# ═══════════════════════════════════════════════════════════════
algorithms = [
    ('mol_fused',     'Molecular (Fused)',
     lambda: prospective_score(X_3d, dates, MolecularEngine,
                               dict(iterations=80, k_neighbors=10, max_samples=2000,
                                    use_fused=True, use_bsdt_damping=True),
                               N_CALIB, N)),
    ('gravity',       'Gravity',
     lambda: prospective_score(X_3d, dates, GravityModeEngine,
                               dict(iterations=60, k_neighbors=10, use_fused=True),
                               N_CALIB, N)),
    ('hybrid',        'Hybrid',
     lambda: prospective_score(X_3d, dates, HybridGravityEngine,
                               dict(),
                               N_CALIB, N)),
    ('mol_fisher',    'Mol+Fisher',
     lambda: prospective_score_posthoc(X_3d, dates, 'fisher',
                                        dict(iterations=80, k_neighbors=10, max_samples=2000,
                                             use_fused=False, use_bsdt_damping=True),
                                        N_CALIB, N)),
    ('mol_quadsurf',  'Mol+QuadSurf',
     lambda: prospective_score_posthoc(X_3d, dates, 'quadsurf',
                                        dict(iterations=80, k_neighbors=10, max_samples=2000,
                                             use_fused=False, use_bsdt_damping=True),
                                        N_CALIB, N)),
    ('mol_expogate',  'Mol+ExpoGate',
     lambda: prospective_score_posthoc(X_3d, dates, 'expogate',
                                        dict(iterations=80, k_neighbors=10, max_samples=2000,
                                             use_fused=False, use_bsdt_damping=True),
                                        N_CALIB, N)),
    ('rtd_mol',       'RTD+Mol (Fused)',
     lambda: prospective_score_rtd(X_3d, dates, 'base',
                                    dict(iterations=80, k_neighbors=10, max_samples=2000,
                                         use_fused=True, use_bsdt_damping=True, normalize=False),
                                    N_CALIB, N)),
    ('rtd_fisher',    'RTD+Fisher',
     lambda: prospective_score_rtd(X_3d, dates, 'fisher',
                                    dict(iterations=80, k_neighbors=10, max_samples=2000,
                                         use_fused=False, use_bsdt_damping=True, normalize=False),
                                    N_CALIB, N)),
]

all_results = {}
all_scores = {}

for idx, (key, label, scorer_fn) in enumerate(algorithms):
    print('\n' + '=' * 70)
    print(f'  [{idx+1}/{len(algorithms)}] {label}')
    print('=' * 70)
    gc.collect()
    t0 = time.time()
    q = scorer_fn()
    elapsed = time.time() - t0
    print(f'  Time: {elapsed:.0f}s')

    r, raw_scores, z_scores = evaluate_all_thresholds(label, q, y_crisis, dates, N_CALIB)
    r['time'] = elapsed
    all_results[key] = r
    all_scores[key] = raw_scores.tolist()  # save for JSON

    # Brief summary for this algorithm
    print(f'\n  {label}:  AUROC={r["auroc"]:.4f}  GFC-AUC={r["gfc_auroc"]:.4f}  z(BNP)={r["z_bnp"]:+.2f}' if r['z_bnp'] else f'\n  {label}:  AUROC={r["auroc"]:.4f}')
    for sn in ['Fixed P99', 'Fixed mu+3sig', 'Adaptive z>3', 'Adaptive P99']:
        s = r[sn]
        print(f'    {sn:<16s}  FAR={s["far"]:5.1f}%  Recall={s["recall"]:5.1f}%  Prec={s["precision"]:5.1f}%  GFC-1st={s["gfc_first"]}')

    del q, raw_scores, z_scores; gc.collect()


# ═══════════════════════════════════════════════════════════════
#  FINAL COMPARISON TABLES
# ═══════════════════════════════════════════════════════════════
print('\n\n' + '=' * 95)
print('  FINAL COMPARISON: FIXED vs ADAPTIVE CALIBRATION')
print('  (correct in-sample protocol, all thresholds strictly causal)')
print('=' * 95)

labels_map = {
    'mol_fused':     'Molecular (Fused)',
    'gravity':       'Gravity',
    'hybrid':        'Hybrid',
    'mol_fisher':    'Mol+Fisher',
    'mol_quadsurf':  'Mol+QuadSurf',
    'mol_expogate':  'Mol+ExpoGate',
    'rtd_mol':       'RTD+Mol (Fused)',
    'rtd_fisher':    'RTD+Fisher',
}

for strat_name in ['Fixed P99', 'Fixed mu+3sig', 'Adaptive z>3', 'Adaptive P99']:
    print(f'\n  Threshold: {strat_name}')
    print(f'  {"Method":<22s} AUROC  GFC-AUC  FAR%  Recall%  Prec%   GFC-1st      z(BNP)')
    print(f'  {"-"*22} {"-"*5}  {"-"*7}  {"-"*4}  {"-"*7}  {"-"*5}   {"-"*10}   {"-"*6}')
    for key in labels_map:
        if key not in all_results:
            continue
        r = all_results[key]
        s = r.get(strat_name, {})
        z_str = f'{r["z_bnp"]:+.2f}' if r.get('z_bnp') else 'N/A'
        print(f'  {labels_map[key]:<22s} {r["auroc"]:.3f}  {r["gfc_auroc"]:.3f}    '
              f'{s.get("far",0):4.1f}%   {s.get("recall",0):5.1f}%  '
              f'{s.get("precision",0):4.1f}%   {str(s.get("gfc_first","?")):<10s}   {z_str}')

# ── Side-by-side improvement table ──
print('\n\n' + '=' * 95)
print('  CALIBRATION IMPROVEMENT: Fixed mu+3sig → Adaptive z>3')
print('=' * 95)
print(f'  {"Method":<22s} {"--- Fixed mu+3sig ---":^30s}  {"--- Adaptive z>3 ---":^30s}  AUROC')
print(f'  {"":22s} {"FAR%":>6s} {"Recall%":>8s} {"Prec%":>7s}   {"FAR%":>6s} {"Recall%":>8s} {"Prec%":>7s}')
print(f'  {"-"*22} {"-"*6} {"-"*8} {"-"*7}   {"-"*6} {"-"*8} {"-"*7}  {"-"*5}')
for key in labels_map:
    if key not in all_results:
        continue
    r = all_results[key]
    f_ = r.get('Fixed mu+3sig', {})
    a_ = r.get('Adaptive z>3', {})
    print(f'  {labels_map[key]:<22s} {f_.get("far",0):5.1f}% {f_.get("recall",0):7.1f}% {f_.get("precision",0):6.1f}%'
          f'   {a_.get("far",0):5.1f}% {a_.get("recall",0):7.1f}% {a_.get("precision",0):6.1f}%'
          f'  {r["auroc"]:.3f}')

# Save everything
out = {'results': all_results, 'scores': all_scores,
       'dates': [str(d.date()) for d in dates],
       'crisis_quarters': list(CRISIS_QUARTERS),
       'n_calib': N_CALIB}
with open(os.path.join(ROOT, 'insample_calibrated_results.json'), 'w', encoding='utf-8') as f:
    json.dump(out, f, indent=2, default=str)
print(f'\nResults saved to insample_calibrated_results.json')
print('Done.')
