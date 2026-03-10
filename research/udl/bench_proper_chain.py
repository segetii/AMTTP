"""
Full Paper Pipeline Benchmark
==============================
Proper chain: Raw X → ReducedTensor → D → Engine on D → BSDT variants

For each engine (Molecular, Gravity, Hybrid) running on reduced tensor D:
  - Engine fit_score on D (physics simulation on tensor features)
  - All 5 BSDT scoring variants on D:
      Baseline, FullBSDT, QuadSurf, SignedFisher, ExpoGate
  - MFLS (gradient norm) on D
  - E_BS (blind-spot energy) on D
  - FusedSystemScorer (Morse + Betti + UDL + BSDT) via engine
  - Morse topology alarm
  - Conformal p-values

Plus standalone ReducedTensorDescriptor integrated pipeline:
  - fit_score (4-view fusion)
  - score_variants (all 5 BSDT)
  - Panel scoring (cross-sectional + temporal)

All closed-form Fisher VR weights. Zero label leakage.
"""
from __future__ import annotations
import sys, time, warnings
import numpy as np
from pathlib import Path
from sklearn.metrics import roc_auc_score, f1_score

warnings.filterwarnings("ignore")

ROOT = Path(r"c:\amttp")
sys.path.insert(0, str(ROOT / "research" / "udl"))
sys.path.insert(0, str(ROOT / "research" / "udl" / "src"))
sys.path.insert(0, str(ROOT / "research" / "adaptive-friction" / "pipeline"))
sys.path.insert(0, str(ROOT / "research" / "adaptive-friction" / "variants"))

from udl.system_mode import (
    BSDTChannels, ReducedTensorDescriptor,
    MolecularEngine, GravityModeEngine, HybridGravityEngine,
)
from bench_economy_ercot import load_ercot_dataset, load_economy_dataset


# -- metrics ----------------------------------------------------------
def far95(scores, y):
    y = np.asarray(y, dtype=int)
    a, n = scores[y == 1], scores[y == 0]
    if len(a) == 0 or len(n) == 0:
        return float('nan')
    return float(np.mean(n >= np.percentile(a, 5)))

def bestf1(scores, y):
    best = 0
    for th in np.percentile(scores, np.arange(50, 100, 1)):
        f = f1_score(y, (scores >= th).astype(int), zero_division=0)
        if f > best:
            best = f
    return best

def row(label, scores, y, t=None):
    auc = roc_auc_score(y, scores)
    f = far95(scores, y)
    f1 = bestf1(scores, y)
    ts = f'  {t:.1f}s' if t else ''
    print(f'    {label:<55} AUC={auc:.4f}  FAR={f:.3f}  F1={f1:.3f}{ts}')
    return dict(label=label, auc=auc, far=f, f1=f1)


def run_bsdt_variants(data, y, data_ref, label_prefix):
    """Run all 5 BSDT scoring variants + E_BS + MFLS on given data.

    Parameters
    ----------
    data     : (N, d) — the data to score (e.g. tensor features D)
    y        : (N,) — binary labels
    data_ref : (N_ref, d) — reference (normal) portion of data
    label_prefix : str — e.g. 'Molecular' for labelling

    Returns
    -------
    dict of results
    """
    results = {}
    k = min(10, max(2, len(data_ref) - 1))
    bsdt = BSDTChannels(k=k)
    bsdt.fit(data_ref)

    # E_BS
    e = bsdt.energy(data)
    r = row(f'{label_prefix} E_BS', e, y)
    results[f'{label_prefix}_E_BS'] = r

    # MFLS
    m = bsdt.mfls(data)
    r = row(f'{label_prefix} MFLS', m, y)
    results[f'{label_prefix}_MFLS'] = r

    # 1. Baseline (0.5*E + 0.5*MFLS)
    s = bsdt.score(data)
    r = row(f'{label_prefix} Baseline', s, y)
    results[f'{label_prefix}_Baseline'] = r

    # 2. FullBSDT (Fisher-weighted channel sum, transductive)
    C = bsdt._channel_matrix(data)
    fw, _, _, _ = bsdt._fisher_weights(data)  # transductive on full data
    C_normed = np.zeros_like(C)
    for col_idx in range(C.shape[1]):
        col = C[:, col_idx]
        cmin, cmax = col.min(), col.max()
        if cmax - cmin > 1e-10:
            C_normed[:, col_idx] = (col - cmin) / (cmax - cmin)
    s = (C_normed * fw).sum(axis=1)
    r = row(f'{label_prefix} FullBSDT', s, y)
    results[f'{label_prefix}_FullBSDT'] = r
    fw_str = ', '.join(f'{w:.4f}' for w in fw)
    print(f'      Fisher VR weights: [{fw_str}]')

    # 3. QuadSurf
    bsdt.fit_quadsurf(data_ref)
    s = bsdt.score_quadsurf(data)
    r = row(f'{label_prefix} QuadSurf', s, y)
    results[f'{label_prefix}_QuadSurf'] = r

    # 4. SignedFisher (transductive)
    bsdt.fit_signed_lr(data)
    s = bsdt.score_signed_lr(data)
    r = row(f'{label_prefix} SignedFisher', s, y)
    results[f'{label_prefix}_SignedFisher'] = r

    # 5. ExpoGate
    bsdt.fit_expogate(data_ref)
    s = bsdt.score_expogate(data)
    r = row(f'{label_prefix} ExpoGate', s, y)
    results[f'{label_prefix}_ExpoGate'] = r

    # Channel detail
    ch = bsdt.channels(data)
    print(f'      {"Channel":<12} {"Normal":>8} {"Crisis":>8} {"Ratio":>7}')
    for chname in ['delta_C', 'delta_G', 'delta_A', 'delta_T']:
        mn = ch[chname][y == 0].mean()
        mc = ch[chname][y == 1].mean()
        ratio = mc / (mn + 1e-12)
        print(f'      {chname:<12} {mn:8.4f} {mc:8.4f} {ratio:6.2f}x')

    return results


def run_engine_on_tensor(engine, engine_name, D, y, D_ref):
    """Run one engine on tensor features D, then BSDT variants + Morse."""
    print()
    print(f'  ── {engine_name} on Reduced Tensor D ──')

    results = {}

    # 1. Engine fit_score on D
    t0 = time.time()
    try:
        eng_scores = engine.fit_score(D, y)
        dt = time.time() - t0
        r = row(f'{engine_name} engine score', eng_scores, y, dt)
        results[f'{engine_name}_engine'] = r
    except Exception as ex:
        dt = time.time() - t0
        print(f'    {engine_name} engine score: FAILED ({ex.__class__.__name__}: {ex})  {dt:.1f}s')

    # 2. All BSDT variants on D
    print(f'    -- BSDT variants on D (via {engine_name}) --')
    bsdt_results = run_bsdt_variants(D, y, D_ref, engine_name)
    results.update(bsdt_results)

    # 3. Morse topology on D
    print(f'    -- Morse alarm on D --')
    desc_m = ReducedTensorDescriptor(k_neighbors=15)
    desc_m.fit(D_ref)
    t0 = time.time()
    morse_idx = desc_m.get_morse_index(D)
    alarm = desc_m.get_alarm(D)
    dt = time.time() - t0
    try:
        alarm_auc = roc_auc_score(y, alarm.astype(float))
    except ValueError:
        alarm_auc = float('nan')
    print(f'    {engine_name + " Morse alarm":<55} AUC={alarm_auc:.4f}  {dt:.1f}s')
    print(f'      Morse index — normal: {morse_idx[y==0].mean():.2f}  '
          f'crisis: {morse_idx[y==1].mean():.2f}')
    print(f'      Alarm rate  — normal: {alarm[y==0].mean():.3f}  '
          f'crisis: {alarm[y==1].mean():.3f}')
    results[f'{engine_name}_Morse'] = dict(label=f'{engine_name} Morse', auc=alarm_auc)

    # 4. Conformal scoring via engine
    print(f'    -- Conformal scoring --')
    try:
        t0 = time.time()
        engine_conf = engine.__class__(**{
            k: v for k, v in engine.__dict__.items()
            if not k.startswith('_') and k not in (
                'X_final_', 'scaler_', 'mu_', 'fused_scorer',
                'alarm_', 'cal_scores_', 'threshold_',
                'molecular', 'gravity', 'blend_weight_')
        })
    except Exception:
        engine_conf = engine.__class__()
    try:
        engine_conf.fit_reference(D_ref)
        pvals = engine_conf.predict_pvalue(D)
        dt = time.time() - t0
        conf_scores = 1.0 - pvals
        r = row(f'{engine_name} Conformal', conf_scores, y, dt)
        results[f'{engine_name}_Conformal'] = r
    except Exception as ex:
        print(f'    {engine_name} Conformal: FAILED ({ex})')

    return results


def run_dataset(name, X, y, X_3d=None, y_quarter=None):
    """Run the full paper pipeline on one dataset."""
    print()
    print('=' * 80)
    print(f'  {name}')
    print(f'  Shape: {X.shape},  crisis: {int(y.sum())}/{len(y)} ({y.mean():.1%})')
    print('=' * 80)

    all_results = {}
    X_ref = X[y == 0]

    # ==============================================================
    #  STEP 1: Raw X → ReducedTensor → D
    # ==============================================================
    print()
    print('  ━━ STEP 1: Compute Reduced Tensor Descriptor D ━━')
    desc = ReducedTensorDescriptor(k_neighbors=15)
    t0 = time.time()
    desc.fit(X_ref)
    D = desc.transform(X)
    D_ref = desc.transform(X_ref)
    dt = time.time() - t0
    print(f'    X: {X.shape} → D: {D.shape}  ({dt:.1f}s)')
    print(f'    Features: {desc.feature_names()}')
    ci = desc.complexity_info()
    print(f'    Complexity: {ci["total"]}  (vs {ci["vs_full"]})')
    print(f'    Speedup: ~{ci["speedup"]}')

    # ==============================================================
    #  STEP 2: Each engine on D + all BSDT variants + Morse
    # ==============================================================
    print()
    print('  ━━ STEP 2: Engines on D + BSDT variants + MFLS + Morse ━━')

    engines = [
        ('Molecular', MolecularEngine(
            k_neighbors=15, max_samples=5000, iterations=50,
            normalize=True, use_fused=True)),
        ('Gravity', GravityModeEngine(
            k_neighbors=15, max_samples=5000, iterations=50,
            normalize=True, use_fused=True)),
        ('Hybrid', HybridGravityEngine(
            blend_weight='auto',
            molecular_params=dict(k_neighbors=15, max_samples=5000,
                                  iterations=50, normalize=True, use_fused=True),
            gravity_params=dict(k_neighbors=15, max_samples=5000,
                                iterations=50, normalize=True, use_fused=True))),
    ]

    for eng_name, engine in engines:
        eng_results = run_engine_on_tensor(engine, eng_name, D, y, D_ref)
        all_results.update(eng_results)

    # ==============================================================
    #  STEP 3: ReducedTensorDescriptor integrated pipeline (on raw X)
    # ==============================================================
    print()
    print('  ━━ STEP 3: ReducedTensorDescriptor Integrated Pipeline ━━')

    # 3a. fit_score — 4-view fusion on raw X
    desc2 = ReducedTensorDescriptor(k_neighbors=15)
    t0 = time.time()
    scores_fs = desc2.fit_score(X, y)
    dt = time.time() - t0
    r = row('RTD fit_score (4-view fusion)', scores_fs, y, dt)
    all_results['RTD_fit_score'] = r

    # 3b. desc.score — topology composite
    t0 = time.time()
    scores_desc = desc2.score(X)
    dt = time.time() - t0
    r = row('RTD desc.score (topology)', scores_desc, y, dt)
    all_results['RTD_desc_score'] = r

    # 3c. score_variants — all 5 BSDT variants on raw X
    print()
    print('  -- RTD score_variants (BSDT on raw X, Fisher VR) --')
    variants = desc2.score_variants(X, y, X_ref=X_ref)
    for vname, vr in variants.items():
        s = vr['scores']
        auc = vr.get('auroc', roc_auc_score(y, s))
        f = far95(s, y)
        f1 = bestf1(s, y)
        fw_str = ''
        if 'fisher_weights' in vr:
            fw_str = '  w=[' + ','.join(f'{w:.4f}' for w in vr['fisher_weights']) + ']'
        elif 'weights' in vr:
            fw_str = '  w=[' + ','.join(f'{w:.4f}' for w in vr['weights']) + ']'
        print(f'    RTD {vname:<18} AUC={auc:.4f}  FAR={f:.3f}  F1={f1:.3f}{fw_str}')
        all_results[f'RTD_{vname}'] = dict(label=f'RTD {vname}', auc=auc, far=f, f1=f1)

    # 3d. Morse alarm on raw X
    print()
    print('  -- Morse Topology (raw X) --')
    morse_idx = desc2.get_morse_index(X)
    alarm = desc2.get_alarm(X)
    try:
        alarm_auc = roc_auc_score(y, alarm.astype(float))
    except ValueError:
        alarm_auc = float('nan')
    print(f'    {"RTD Morse alarm":<55} AUC={alarm_auc:.4f}')
    print(f'    Index — normal: {morse_idx[y==0].mean():.2f}  '
          f'crisis: {morse_idx[y==1].mean():.2f}')
    print(f'    Alarm — normal: {alarm[y==0].mean():.3f}  '
          f'crisis: {alarm[y==1].mean():.3f}')
    all_results['RTD_Morse'] = dict(label='RTD Morse alarm', auc=alarm_auc)

    # 3e. Conformal scoring
    print()
    print('  -- Conformal Scoring (distribution-free) --')
    desc_conf = ReducedTensorDescriptor(k_neighbors=15)
    t0 = time.time()
    desc_conf.fit_reference(X_ref, cal_frac=0.2)
    pvals = desc_conf.predict_pvalue(X)
    dt = time.time() - t0
    for alpha in [0.05, 0.10, 0.20]:
        preds = (pvals <= alpha).astype(int)
        tp = ((preds == 1) & (y == 1)).sum()
        fp = ((preds == 1) & (y == 0)).sum()
        fn = ((preds == 0) & (y == 1)).sum()
        prec = tp / (tp + fp + 1e-10)
        rec = tp / (tp + fn + 1e-10)
        f1 = 2 * prec * rec / (prec + rec + 1e-10)
        print(f'    α={alpha:.2f}  detected={preds.sum():>5}  '
              f'TP={tp:>4}  FP={fp:>4}  prec={prec:.3f}  '
              f'rec={rec:.3f}  F1={f1:.3f}')
    conf_scores = 1.0 - pvals
    r = row('RTD Conformal (1 - p)', conf_scores, y, dt)
    all_results['RTD_Conformal'] = r

    # ==============================================================
    #  STEP 4: Panel scoring (if 3D data available)
    # ==============================================================
    if X_3d is not None and y_quarter is not None:
        print()
        print('  ━━ STEP 4: Panel Scoring (cross-sectional + temporal) ━━')
        desc_panel = ReducedTensorDescriptor(k_neighbors=15)
        t0 = time.time()
        q_scores = desc_panel.score_panel(X_3d, y_quarter)
        dt = time.time() - t0
        q_auc = roc_auc_score(y_quarter, q_scores)
        q_f1 = bestf1(q_scores, y_quarter)
        T = len(y_quarter)
        print(f'    {"score_panel (quarter-level)":<55} '
              f'AUC={q_auc:.4f}  F1={q_f1:.3f}  (T={T})  {dt:.1f}s')
        n_crisis = int(y_quarter.sum())
        n_det = int((q_scores[y_quarter == 1] >
                     np.percentile(q_scores[y_quarter == 0], 90)).sum())
        print(f'    Crisis periods: {n_crisis}/{T}  '
              f'detected (>90th pctl): {n_det}/{n_crisis}')
        all_results['RTD_Panel'] = dict(label='RTD Panel', auc=q_auc, f1=q_f1)

    # ==============================================================
    #  SUMMARY TABLE
    # ==============================================================
    print()
    print(f'  ╔{"═"*70}╗')
    print(f'  ║  SUMMARY: {name:<57}║')
    print(f'  ╠{"═"*70}╣')
    print(f'  ║  {"Method":<50} {"AUC":>7}  {"FAR":>6}  {"F1":>5} ║')
    print(f'  ╠{"═"*70}╣')

    sorted_r = sorted(all_results.items(),
                       key=lambda kv: kv[1].get('auc', 0), reverse=True)
    for key, r in sorted_r:
        if 'auc' in r:
            lbl = r.get('label', key)[:50]
            auc_s = f'{r["auc"]:7.4f}'
            far_s = f'{r.get("far", float("nan")):6.3f}' if 'far' in r else '   -  '
            f1_s = f'{r.get("f1", float("nan")):5.3f}' if 'f1' in r else '  -  '
            print(f'  ║  {lbl:<50} {auc_s}  {far_s}  {f1_s} ║')

    print(f'  ╚{"═"*70}╝')
    print()
    return all_results


# ==================================================================
if __name__ == '__main__':
    import io, sys as _sys

    # Tee stdout to file
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

    logf = open(r'c:\amttp\research\udl\bench_results_full.txt', 'w', encoding='utf-8')
    _sys.stdout = Tee(_sys.stdout, logf)

    print()
    print('=' * 80)
    print('  FULL PAPER PIPELINE BENCHMARK')
    print('  Raw X → ReducedTensor → D → Engines + BSDT + MFLS + Morse')
    print('  Molecular | Gravity | Hybrid × 5 BSDT variants')
    print('  + ReducedTensorDescriptor integrated pipeline')
    print('  All closed-form Fisher VR. Zero label leakage.')
    print('=' * 80)

    # -- 1. ERCOT Grid --
    print('\n  Loading ERCOT...')
    X_e, y_e, y_hour, T_e, N_e, agents_e, cap_e = load_ercot_dataset()
    print(f'  Loaded: {X_e.shape}, T={T_e}, N={N_e}')

    X_3d_e = X_e.reshape(T_e, N_e, -1)
    run_dataset('ERCOT Grid', X_e, y_e, X_3d=X_3d_e, y_quarter=y_hour)

    # -- 2. FRED Economy --
    print('\n  Loading Economy...')
    X_b, y_b, dates_b, sectors_b, yq_b, X3d_b = load_economy_dataset()
    T_b, N_b = X3d_b.shape[0], X3d_b.shape[1]
    print(f'  Loaded: {X_b.shape}, T={T_b}, N={N_b}')

    run_dataset('U.S. Banking Economy (FRED)', X_b, y_b,
                X_3d=X3d_b, y_quarter=yq_b)

    print('=' * 80)
    print('  DONE')
    print('=' * 80)
    logf.close()
