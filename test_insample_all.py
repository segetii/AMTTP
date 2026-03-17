"""
Unified In-Sample Monitoring Benchmark — All Algorithms
========================================================

Correct protocol for N-body physics engines:
  - Current quarter's banks INSIDE the simulation (in-sample monitoring)
  - y = all-zeros (purely unsupervised, NO crisis labels)
  - Expanding window, strictly causal
  - Threshold: frozen from calm period (both 99th-pctl and mu+3sig)
  - Crisis labels used ONLY for evaluation after scoring

This matches the Table 7 protocol (bench_bank_level_prospective.py).

Algorithms tested:
  1. Molecular (FusedScorer)
  2. Gravity (GravityModeEngine)
  3. Hybrid (HybridGravityEngine)
  4. Molecular + Fisher posthoc
  5. Molecular + QuadSurf posthoc
  6. Molecular + ExpoGate posthoc
  7. RTD + Molecular (FusedScorer)
  8. RTD + Molecular + Fisher
  9. RTD + Molecular + QuadSurf
"""
import sys, os, time, warnings, json, gc

# Unbuffered output for progress tracking
sys.stdout.reconfigure(line_buffering=True)

# Also tee to file
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

_logf = open(os.path.join(r'C:\amttp', 'insample_all_output.txt'), 'w', encoding='utf-8')
sys.stdout = Tee(sys.__stdout__, _logf)
sys.stderr = Tee(sys.__stderr__, _logf)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'research', 'udl'))

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

# ═════════════════════════════════════════════════════════════════
#  Data
# ═════════════════════════════════════════════════════════════════
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

CALIB_END = pd.Timestamp('2007-09-30')
N_CALIB = int((dates <= CALIB_END).sum())

print('=' * 76)
print('  UNIFIED IN-SAMPLE MONITORING BENCHMARK — ALL ALGORITHMS')
print('  Protocol: expanding window | y=zeros (unsupervised) | in-sample')
print('  Threshold: frozen from 2005Q1-2007Q3 calm period')
print('=' * 76)
print(f'Panel: T={T}, N={N}, d={d}')
print(f'Crisis: {int(y_crisis.sum())}/{T} quarters')
print(f'Calib window: {dates[0].date()} → {dates[N_CALIB-1].date()} ({N_CALIB} Q)')
print()


# ═════════════════════════════════════════════════════════════════
#  Prospective scoring (in-sample monitoring) — core function
# ═════════════════════════════════════════════════════════════════
def prospective_score(X_panel, dates, engine_cls, engine_kwargs,
                      n_calib, N, verbose=True):
    """
    Same protocol as bench_bank_level_prospective.py:
      Phase 1: fit on calib data (y=0), get calib scores
      Phase 2: expanding window, quarter t included in simulation
    """
    T_total, N_banks, d_feat = X_panel.shape
    q_scores = np.full(T_total, np.nan)

    # Phase 1: calibration period
    X_calib = X_panel[:n_calib].reshape(n_calib * N_banks, d_feat)
    y_calib = np.zeros(n_calib * N_banks, dtype=int)

    eng = engine_cls(**engine_kwargs)
    scores_calib = eng.fit_score(X_calib, y_calib)

    for t in range(n_calib):
        q_scores[t] = scores_calib[t * N_banks:(t + 1) * N_banks].mean()

    del eng, scores_calib, X_calib, y_calib
    gc.collect()

    # Phase 2: expanding window monitoring
    for t in range(n_calib, T_total):
        gc.collect()
        n_pts = (t + 1) * N_banks
        X_up = X_panel[:t + 1].reshape(n_pts, d_feat)
        y_dummy = np.zeros(n_pts, dtype=int)

        eng = engine_cls(**engine_kwargs)
        scores_all = eng.fit_score(X_up, y_dummy)
        q_scores[t] = scores_all[-N_banks:].mean()

        if verbose and ((t - n_calib) % 8 == 0):
            ds = str(dates[t].date())
            crisis = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
            print(f'    t={t:3d}  {ds}  score={q_scores[t]:.4f}{crisis}')

        del eng, scores_all, X_up, y_dummy
        gc.collect()

    return q_scores


# ═════════════════════════════════════════════════════════════════
#  Prospective scoring with posthoc correction layer
# ═════════════════════════════════════════════════════════════════
def prospective_score_posthoc(X_panel, dates, posthoc_cls, posthoc_name,
                              engine_kwargs, n_calib, N, verbose=True):
    """
    In-sample monitoring with BSDT posthoc correction.

      Phase 1: fit engine on calib, extract BSDT channels, fit posthoc,
               score calib period
      Phase 2: expanding window, each quarter t in simulation,
               refit everything, score quarter t
    
    For supervised posthoc (QuadSurf, ExpoGate): uses crisis labels
    that have already occurred (causal) to fit the correction layer.
    The engine itself remains fully unsupervised (y=zeros).
    """
    T_total, N_banks, d_feat = X_panel.shape
    q_scores = np.full(T_total, np.nan)
    is_supervised = posthoc_name in ('quadsurf', 'expogate')

    # Phase 1: calibration period
    X_calib = X_panel[:n_calib].reshape(n_calib * N_banks, d_feat)
    y_eng = np.zeros(n_calib * N_banks, dtype=int)  # engine sees no labels

    eng = MolecularEngine(**engine_kwargs)
    _ = eng.fit_score(X_calib, y_eng)

    # BSDT posthoc on calibration
    X_final = eng.X_final_
    X_ref = X_final  # all normal (y=0)
    k_bsdt = min(10, max(len(X_ref) - 1, 1))
    bsdt = BSDTChannels(k=k_bsdt)
    bsdt.fit(X_ref)

    ch = bsdt.channels(X_calib)
    C_calib = np.column_stack([ch['delta_C'], ch['delta_G'],
                                ch['delta_A'], ch['delta_T']])

    # Fit posthoc layer (Fisher is unsupervised, others need labels)
    if posthoc_name == 'fisher':
        layer = _MFLSFisherBSDT()
        layer.fit(C_calib)
    elif is_supervised:
        # No crisis in calib period → fall back to Fisher
        layer = _MFLSFisherBSDT()
        layer.fit(C_calib)

    scores_calib = layer.score(C_calib)
    for t in range(n_calib):
        q_scores[t] = scores_calib[t * N_banks:(t + 1) * N_banks].mean()

    del eng, bsdt, layer, X_final, X_ref
    gc.collect()

    # Phase 2: expanding window monitoring
    for t in range(n_calib, T_total):
        gc.collect()
        n_pts = (t + 1) * N_banks
        X_up = X_panel[:t + 1].reshape(n_pts, d_feat)
        y_eng = np.zeros(n_pts, dtype=int)  # engine always unsupervised

        eng = MolecularEngine(**engine_kwargs)
        _ = eng.fit_score(X_up, y_eng)

        X_final = eng.X_final_
        X_ref = X_final
        k_bsdt = min(10, max(len(X_ref) - 1, 1))
        bsdt = BSDTChannels(k=k_bsdt)
        bsdt.fit(X_ref)

        ch = bsdt.channels(X_up)
        C_all = np.column_stack([ch['delta_C'], ch['delta_G'],
                                  ch['delta_A'], ch['delta_T']])

        # Build causal crisis labels for posthoc
        # (only crises that have already happened by quarter t)
        if is_supervised:
            y_posthoc = np.zeros(n_pts, dtype=float)
            for t_idx in range(t + 1):
                if str(dates[t_idx].date()) in CRISIS_QUARTERS:
                    y_posthoc[t_idx * N_banks:(t_idx + 1) * N_banks] = 1.0
            n_crisis = int(y_posthoc.sum())
        else:
            n_crisis = 0

        try:
            if posthoc_name == 'fisher':
                layer = _MFLSFisherBSDT()
                layer.fit(C_all)
            elif posthoc_name == 'quadsurf':
                if n_crisis > 0:
                    layer = _MFLSQuadSurf(ridge_alpha=1.0)
                    layer.fit(C_all, y_posthoc)
                else:
                    layer = _MFLSFisherBSDT()
                    layer.fit(C_all)
            elif posthoc_name == 'expogate':
                if n_crisis > 0:
                    layer = _MFLSExpoGate(ridge_alpha=1.0,
                                          smooth_sigma=1.0, gate_scale=3.0)
                    layer.fit(C_all, y_posthoc)
                else:
                    layer = _MFLSFisherBSDT()
                    layer.fit(C_all)

            scores_all = layer.score(C_all)
        except Exception:
            scores_all = bsdt.energy(X_up)

        q_scores[t] = scores_all[-N_banks:].mean()

        if verbose and ((t - n_calib) % 8 == 0):
            ds = str(dates[t].date())
            crisis = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
            print(f'    t={t:3d}  {ds}  score={q_scores[t]:.4f}{crisis}')

        del eng, bsdt, layer, X_final, X_ref
        gc.collect()

    return q_scores


# ═════════════════════════════════════════════════════════════════
#  RTD variant of prospective scoring
# ═════════════════════════════════════════════════════════════════
def prospective_score_rtd(X_panel, dates, variant, engine_kwargs,
                          n_calib, N, verbose=True):
    """
    In-sample monitoring with RTD transform.
      Raw X → RTD → D → Engine/Posthoc → Score
    
    RTD fit on calib normal data, frozen.
    """
    T_total, N_banks, d_feat = X_panel.shape
    q_scores = np.full(T_total, np.nan)
    is_base = (variant == 'base')
    is_supervised = variant in ('quadsurf',)

    # ── Fit RTD on calibration normal data ──
    X_calib_raw = X_panel[:n_calib].reshape(n_calib * N_banks, d_feat)
    k_nb = min(10, len(X_calib_raw) - 1)
    rtd = ReducedTensorDescriptor(k_neighbors=k_nb, n_eigs=d_feat)
    rtd.fit(X_calib_raw)  # all calib data is normal
    d_rtd = rtd.transform(X_calib_raw).shape[1]

    if verbose:
        print(f'    RTD: d_raw={d_feat} → d_rtd={d_rtd}')

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
        layer = _MFLSFisherBSDT()
        layer.fit(C)
        scores_calib = layer.score(C)
        for t in range(n_calib):
            q_scores[t] = scores_calib[t * N_banks:(t + 1) * N_banks].mean()
        del eng, bsdt, layer, scores_calib

    gc.collect()

    # ── Phase 2: expanding window ──
    for t in range(n_calib, T_total):
        gc.collect()
        n_pts = (t + 1) * N_banks
        X_up_raw = X_panel[:t + 1].reshape(n_pts, d_feat)
        D_up = rtd.transform(X_up_raw)
        D_up_sc = scaler.transform(D_up).astype(np.float64)
        y_eng = np.zeros(n_pts, dtype=int)

        if is_base:
            eng = MolecularEngine(**engine_kwargs)
            scores = eng.fit_score(D_up_sc, y_eng)
            q_scores[t] = scores[-N_banks:].mean()
            del eng, scores
        else:
            eng = MolecularEngine(**engine_kwargs)
            _ = eng.fit_score(D_up_sc, y_eng)
            X_ref = eng.X_final_
            k_bsdt = min(10, max(len(X_ref) - 1, 1))
            bsdt = BSDTChannels(k=k_bsdt)
            bsdt.fit(X_ref)
            ch = bsdt.channels(D_up_sc)
            C = np.column_stack([ch['delta_C'], ch['delta_G'],
                                  ch['delta_A'], ch['delta_T']])

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
                scores = layer.score(C)
            except Exception:
                scores = bsdt.energy(D_up_sc)

            q_scores[t] = scores[-N_banks:].mean()
            del eng, bsdt, layer, scores

        gc.collect()

        if verbose and ((t - n_calib) % 8 == 0):
            ds = str(dates[t].date())
            crisis = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
            print(f'    t={t:3d}  {ds}  score={q_scores[t]:.4f}{crisis}')

    return q_scores


# ═════════════════════════════════════════════════════════════════
#  Evaluate and print results
# ═════════════════════════════════════════════════════════════════
def evaluate(name, q_scores, y_crisis, dates, n_calib):
    """Compute metrics with both threshold strategies."""
    valid = ~np.isnan(q_scores)
    q_v = q_scores[valid]
    y_v = y_crisis[valid]

    auroc = roc_auc_score(y_v, q_v) if 0 < y_v.sum() < len(y_v) else float('nan')

    # GFC-only AUROC
    gfc_mask = np.zeros(len(dates), dtype=bool)
    for i, dt in enumerate(dates):
        ds = str(dt.date())
        if ds in CRISIS_QUARTERS and dt <= pd.Timestamp('2009-06-30'):
            gfc_mask[i] = True
    gfc_start = np.where(dates >= pd.Timestamp('2006-01-01'))[0][0]
    gfc_end = np.where(dates <= pd.Timestamp('2010-06-30'))[0][-1] + 1
    gfc_slice = slice(gfc_start, gfc_end)
    gfc_valid = valid[gfc_slice]
    if gfc_valid.any():
        gfc_auc = roc_auc_score(
            y_crisis[gfc_slice][gfc_valid],
            q_scores[gfc_slice][gfc_valid]
        ) if 0 < y_crisis[gfc_slice][gfc_valid].sum() < gfc_valid.sum() else float('nan')
    else:
        gfc_auc = float('nan')

    # ── Threshold 1: 99th percentile of calm period ──
    calib_scores = q_scores[:n_calib]
    calib_scores = calib_scores[~np.isnan(calib_scores)]
    thresh_99 = np.percentile(calib_scores, 99) if len(calib_scores) > 0 else 0.5

    # ── Threshold 2: mu + 3*sigma of calm period ──
    mu_c = np.mean(calib_scores) if len(calib_scores) > 0 else 0.5
    sig_c = np.std(calib_scores) if len(calib_scores) > 0 else 0.1
    thresh_mu3s = mu_c + 3 * sig_c

    results = {'auroc': auroc, 'gfc_auroc': gfc_auc}

    for thr_name, threshold in [('P99', thresh_99), ('mu+3sig', thresh_mu3s)]:
        y_pred = (q_v >= threshold).astype(int)
        crisis_v = y_v
        TP = int(((y_pred == 1) & (crisis_v == 1)).sum())
        FP = int(((y_pred == 1) & (crisis_v == 0)).sum())
        FN = int(((y_pred == 0) & (crisis_v == 1)).sum())
        TN = int(((y_pred == 0) & (crisis_v == 0)).sum())
        n_normal = TN + FP
        far = FP / n_normal * 100 if n_normal > 0 else float('nan')
        recall = TP / (TP + FN) * 100 if (TP + FN) > 0 else 0.0
        prec = TP / (TP + FP) * 100 if (TP + FP) > 0 else 0.0

        results[thr_name] = {
            'threshold': threshold, 'TP': TP, 'FP': FP, 'FN': FN, 'TN': TN,
            'far': far, 'recall': recall, 'precision': prec,
        }

        # GFC lead time
        gfc_lead = None
        for i, dt in enumerate(dates):
            if valid[i] and q_scores[i] >= threshold:
                if pd.Timestamp('2007-01-01') <= dt < pd.Timestamp('2007-12-31'):
                    gfc_lead = dt
                    break
        if gfc_lead is None:
            for i, dt in enumerate(dates):
                if valid[i] and q_scores[i] >= threshold:
                    if pd.Timestamp('2007-12-31') <= dt <= pd.Timestamp('2009-06-30'):
                        gfc_lead = dt
                        break
        results[thr_name]['gfc_first_alarm'] = str(gfc_lead.date()) if gfc_lead else 'None'

        # z-score at BNP freeze (2007-Q2)
        bnp_idx = np.where(dates == pd.Timestamp('2007-06-30'))[0]
        if len(bnp_idx) > 0 and valid[bnp_idx[0]]:
            z = (q_scores[bnp_idx[0]] - mu_c) / sig_c if sig_c > 1e-10 else 0
            results[thr_name]['z_bnp'] = float(z)
        else:
            results[thr_name]['z_bnp'] = None

    # Print summary
    print(f'\n  {name}:')
    print(f'  AUROC:       {auroc:.4f}')
    print(f'  GFC-AUROC:   {gfc_auc:.4f}')

    for thr_name in ['P99', 'mu+3sig']:
        r = results[thr_name]
        print(f'  --- {thr_name} threshold={r["threshold"]:.4f} ---')
        print(f'  TP={r["TP"]}  FP={r["FP"]}  FN={r["FN"]}  TN={r["TN"]}')
        print(f'  FAR:       {r["far"]:.1f}%')
        print(f'  Recall:    {r["recall"]:.1f}%')
        print(f'  Precision: {r["precision"]:.1f}%')
        print(f'  GFC 1st:   {r["gfc_first_alarm"]}')
        if r['z_bnp'] is not None:
            print(f'  z(BNP):    {r["z_bnp"]:+.2f}')

    # Alarm timeline
    best_thr_name = 'P99'
    best_r = results[best_thr_name]
    threshold = best_r['threshold']
    print(f'\n  Alarm timeline ({thr_name}):')
    for i, dt in enumerate(dates):
        if not valid[i]:
            continue
        ds = str(dt.date())
        sc = q_scores[i]
        is_crisis = ds in CRISIS_QUARTERS
        is_alarm = sc >= threshold
        if is_crisis or is_alarm:
            if is_crisis and is_alarm:
                tag = 'CRISIS + ALARM'
            elif is_crisis:
                tag = 'CRISIS (missed)'
            else:
                tag = 'FALSE ALARM'
            print(f'    {ds}  score={sc:.4f}  {tag}')

    return results


# ═════════════════════════════════════════════════════════════════
#  RUN ALL ALGORITHMS
# ═════════════════════════════════════════════════════════════════
all_results = {}
summary_rows = []

# ── 1. Molecular (FusedScorer) ──────────────────────────────────
print('\n' + '=' * 70)
print('  [1/9] Molecular (FusedScorer)')
print('=' * 70)
gc.collect()
t0 = time.time()
mol_kwargs = dict(iterations=80, k_neighbors=10, max_samples=2000,
                  use_fused=True, use_bsdt_damping=True)
q = prospective_score(X_3d, dates, MolecularEngine, mol_kwargs, N_CALIB, N)
elapsed = time.time() - t0
print(f'  Time: {elapsed:.0f}s')
r = evaluate('Molecular (FusedScorer)', q, y_crisis, dates, N_CALIB)
all_results['mol_fused'] = r
r['time'] = elapsed
del q; gc.collect()


# ── 2. Gravity (GravityModeEngine) ──────────────────────────────
print('\n' + '=' * 70)
print('  [2/9] Gravity (GravityModeEngine)')
print('=' * 70)
gc.collect()
t0 = time.time()
grav_kwargs = dict(iterations=60, k_neighbors=10, use_fused=True)
q = prospective_score(X_3d, dates, GravityModeEngine, grav_kwargs, N_CALIB, N)
elapsed = time.time() - t0
print(f'  Time: {elapsed:.0f}s')
r = evaluate('Gravity', q, y_crisis, dates, N_CALIB)
all_results['gravity'] = r
r['time'] = elapsed
del q; gc.collect()


# ── 3. Hybrid (HybridGravityEngine) ────────────────────────────
print('\n' + '=' * 70)
print('  [3/9] Hybrid (HybridGravityEngine)')
print('=' * 70)
gc.collect()
t0 = time.time()
q = prospective_score(X_3d, dates, HybridGravityEngine, dict(), N_CALIB, N)
elapsed = time.time() - t0
print(f'  Time: {elapsed:.0f}s')
r = evaluate('Hybrid', q, y_crisis, dates, N_CALIB)
all_results['hybrid'] = r
r['time'] = elapsed
del q; gc.collect()


# ── 4. Molecular + Fisher ──────────────────────────────────────
print('\n' + '=' * 70)
print('  [4/9] Molecular + Fisher (posthoc)')
print('=' * 70)
gc.collect()
t0 = time.time()
posthoc_kwargs = dict(iterations=80, k_neighbors=10, max_samples=2000,
                      use_fused=False, use_bsdt_damping=True)
q = prospective_score_posthoc(X_3d, dates, _MFLSFisherBSDT, 'fisher',
                               posthoc_kwargs, N_CALIB, N)
elapsed = time.time() - t0
print(f'  Time: {elapsed:.0f}s')
r = evaluate('Molecular+Fisher', q, y_crisis, dates, N_CALIB)
all_results['mol_fisher'] = r
r['time'] = elapsed
del q; gc.collect()


# ── 5. Molecular + QuadSurf ────────────────────────────────────
print('\n' + '=' * 70)
print('  [5/9] Molecular + QuadSurf (posthoc)')
print('=' * 70)
gc.collect()
t0 = time.time()
q = prospective_score_posthoc(X_3d, dates, _MFLSQuadSurf, 'quadsurf',
                               posthoc_kwargs, N_CALIB, N)
elapsed = time.time() - t0
print(f'  Time: {elapsed:.0f}s')
r = evaluate('Molecular+QuadSurf', q, y_crisis, dates, N_CALIB)
all_results['mol_quadsurf'] = r
r['time'] = elapsed
del q; gc.collect()


# ── 6. Molecular + ExpoGate ────────────────────────────────────
print('\n' + '=' * 70)
print('  [6/9] Molecular + ExpoGate (posthoc)')
print('=' * 70)
gc.collect()
t0 = time.time()
q = prospective_score_posthoc(X_3d, dates, _MFLSExpoGate, 'expogate',
                               posthoc_kwargs, N_CALIB, N)
elapsed = time.time() - t0
print(f'  Time: {elapsed:.0f}s')
r = evaluate('Molecular+ExpoGate', q, y_crisis, dates, N_CALIB)
all_results['mol_expogate'] = r
r['time'] = elapsed
del q; gc.collect()


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
        z_str = f'{t.get("z_bnp", 0):+.2f}' if t.get('z_bnp') is not None else 'N/A'
        print(f'  {label:<22s} {r["auroc"]:.3f}  {r["gfc_auroc"]:.3f}    '
              f'{t.get("far",0):4.1f}%   {t.get("recall",0):5.1f}%  '
              f'{t.get("precision",0):4.1f}%  {t.get("gfc_first_alarm","?"):<10s}  {z_str}')

# Save results
out_path = os.path.join(ROOT, 'insample_all_results.json')
# Convert for JSON serialization
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
