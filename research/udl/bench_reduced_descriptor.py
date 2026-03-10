"""
ReducedTensorDescriptor — Degeneracy Test on Real-World Data
==============================================================
Compares FULL SystemMode engine scores vs ReducedTensorDescriptor
predictions on:

  1. ERCOT Texas Grid failure (65 agents × 5D, 241 hours)
  2. G-SIB Bank-Level panel  (25 banks × 5D, 76 quarters)

Tests whether the O(Nd+d³) reduced descriptor degenerates
(loses detection power) compared to the full O(N²d) engine.

Metrics: AUC, FAR@95% recall, F1, Morse-index alarm accuracy.
"""
from __future__ import annotations
import sys, time, warnings, json
import numpy as np
from pathlib import Path
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score

warnings.filterwarnings("ignore")

ROOT = Path(r"c:\amttp")
UDL_DIR = ROOT / "research" / "udl"
sys.path.insert(0, str(UDL_DIR))

from udl.system_mode import (
    MolecularEngine, GravityModeEngine, HybridGravityEngine,
    SystemModeEngine, ReducedTensorDescriptor,
)
from udl.bench_economy_ercot import load_ercot_dataset


# ── helpers ─────────────────────────────────────────────────────

def far_at_recall(scores, y, target_recall=0.95):
    y = np.asarray(y, dtype=int)
    anom, norm = scores[y == 1], scores[y == 0]
    if len(anom) == 0 or len(norm) == 0:
        return float('nan')
    thresh = np.percentile(anom, 100 * (1 - target_recall))
    return float(np.mean(norm >= thresh))


def best_f1(scores, y):
    thresholds = np.percentile(scores, np.arange(50, 100, 1))
    best, best_th = 0, 0.5
    for th in thresholds:
        preds = (scores >= th).astype(int)
        f = f1_score(y, preds, zero_division=0)
        if f > best:
            best, best_th = f, th
    return best_th, best


def score_from_descriptor(D, n_eigs):
    """Combined anomaly score from descriptor columns.

    Uses: grad_norm + mahalanobis + medoid_dist (normalised, averaged).
    This is a 'fresh prediction' — no engine scores, pure descriptor.
    """
    grad_norm = D[:, 0]
    mahalanobis = D[:, n_eigs + 1]
    medoid_dist = D[:, n_eigs + 2]
    morse_idx   = D[:, n_eigs + 5]

    # Min-max normalise each
    def mm(x):
        lo, hi = x.min(), x.max()
        return (x - lo) / (hi - lo + 1e-15)

    # Weighted combination: Morse index is binary signal, others continuous
    score = (0.30 * mm(grad_norm) +
             0.30 * mm(mahalanobis) +
             0.20 * mm(medoid_dist) +
             0.20 * mm(morse_idx))
    return score


def print_metrics(label, scores, y, elapsed=None):
    auc = roc_auc_score(y, scores)
    far = far_at_recall(scores, y, 0.95)
    th, f1 = best_f1(scores, y)
    preds = (scores >= th).astype(int)
    prec = precision_score(y, preds, zero_division=0)
    rec = recall_score(y, preds, zero_division=0)
    t_str = f'{elapsed:.1f}s' if elapsed else '—'
    print(f'    {label:<28} AUC={auc:.4f}  FAR={far:.3f}  '
          f'F1={f1:.3f}  P={prec:.3f}  R={rec:.3f}  T={t_str}')
    return dict(auc=auc, far=far, f1=f1, prec=prec, rec=rec)


# ═══════════════════════════════════════════════════════════════════
#  DATASET 1 — ERCOT
# ═══════════════════════════════════════════════════════════════════

def run_ercot():
    print('=' * 76)
    print('  DATASET 1: ERCOT Texas Grid — Power Failure Prediction')
    print('  Source: Real ERCOT data (Feb 10-20, 2021), 65 agents × 5D')
    print('=' * 76)

    X, y, y_hour, T_h, N_ag, agent_types, capacity = load_ercot_dataset()
    print(f'  Shape: {X.shape}, Crisis: {int(y.sum())}/{len(y)} ({y.mean():.1%})')
    print()

    results = {}

    # ── A. Full engine scores (baseline) ──────────────────────────
    print('  A. Full engine scores (O(N²d) baseline)')
    for name, eng in [
        ('Mol_Full',   MolecularEngine(iterations=80, k_neighbors=15, use_fused=True)),
        ('Grav_Full',  GravityModeEngine(iterations=60, k_neighbors=15, use_fused=True)),
        ('Hybrid_Full', HybridGravityEngine()),
    ]:
        t0 = time.time()
        scores = eng.fit_score(X, y)
        results[name] = print_metrics(name, scores, y, time.time() - t0)

    # ── B. ReducedTensorDescriptor scores ─────────────────────────
    print()
    print('  B. ReducedTensorDescriptor (O(Nd+d³) reduced)')

    # Fit on normal subset
    X_ref = X[y == 0]
    desc = ReducedTensorDescriptor(k_neighbors=15, n_eigs=None)
    t0 = time.time()
    desc.fit(X_ref)
    n_eigs = desc.n_eigs

    # Transform ALL points (fresh prediction — no engine needed)
    D = desc.transform(X)
    elapsed_desc = time.time() - t0
    d = X.shape[1]

    print(f'    Descriptor shape: {D.shape}  (n_eigs={n_eigs}, d={d})')
    print(f'    Complexity: {desc.complexity_info()["total"]}')
    print(f'    Compute time: {elapsed_desc:.2f}s')
    print()

    # Score from descriptor columns (manual)
    desc_scores = score_from_descriptor(D, n_eigs)
    results['Desc_Combined'] = print_metrics('Desc_Combined', desc_scores, y, elapsed_desc)

    # Score via built-in method (adaptive weights)
    desc_auto_scores = desc.score(X)
    results['Desc_Auto'] = print_metrics('Desc_Auto', desc_auto_scores, y)

    # Individual descriptor components
    results['Desc_GradNorm'] = print_metrics('Desc_GradNorm', D[:, 0], y)
    results['Desc_Mahalanobis'] = print_metrics('Desc_Mahalanobis', D[:, n_eigs+1], y)
    results['Desc_MedoidDist'] = print_metrics('Desc_MedoidDist', D[:, n_eigs+2], y)

    # Morse index alarm
    alarm = desc.get_alarm(X)
    alarm_auc = roc_auc_score(y, alarm.astype(float))
    alarm_f1 = f1_score(y, alarm.astype(int), zero_division=0)
    print(f'    {"Desc_MorseAlarm":<28} AUC={alarm_auc:.4f}  '
          f'F1={alarm_f1:.3f}  (binary: ind≥1)')
    results['Desc_MorseAlarm'] = dict(auc=alarm_auc, f1=alarm_f1)

    # ── C. SystemModeEngine.get_reduced_descriptor() ──────────────
    print()
    print('  C. Via SystemModeEngine.get_reduced_descriptor()')
    engine = SystemModeEngine(mode='hybrid')
    t0 = time.time()
    engine_scores = engine.fit_score(X, y)
    desc2 = engine.get_reduced_descriptor(X_ref=X_ref)
    D2 = desc2.transform(X)
    elapsed2 = time.time() - t0
    desc2_scores = score_from_descriptor(D2, desc2.n_eigs)
    results['Engine+Desc'] = print_metrics('Engine+Desc', desc2_scores, y, elapsed2)

    # ── D. Degeneracy check ───────────────────────────────────────
    print()
    print('  D. DEGENERACY CHECK — Full vs Reduced')
    full_auc = results['Hybrid_Full']['auc']
    reduced_auc = max(results['Desc_Combined']['auc'],
                      results.get('Desc_Auto', {}).get('auc', 0))
    delta = reduced_auc - full_auc
    print(f'    Full Hybrid AUC:     {full_auc:.4f}')
    print(f'    Best Reduced AUC:    {reduced_auc:.4f}')
    print(f'    Delta:               {delta:+.4f}')
    if abs(delta) < 0.02:
        print(f'    ✓ NO DEGENERACY — descriptor matches full engine (|Δ|<0.02)')
    elif delta > 0:
        print(f'    ✓ IMPROVED — reduced descriptor outperforms full engine')
    else:
        print(f'    ✗ DEGENERATE — reduced descriptor lost {abs(delta):.4f} AUC')

    return results


# ═══════════════════════════════════════════════════════════════════
#  DATASET 2 — G-SIB Bank-Level
# ═══════════════════════════════════════════════════════════════════

def load_bank_data():
    """Load G-SIB panel — try cached real data, fallback to synthetic."""
    CACHE_DIR = ROOT / "research" / "adaptive-friction" / "banklevel_enhanced" / "gsib_cache_real"
    npz_path = CACHE_DIR / "gsib_real_panel.npz"

    if npz_path.exists():
        import pandas as pd
        npz = np.load(npz_path)
        X_3d = npz["X"]  # (T, N, d)
        with open(CACHE_DIR / "gsib_real_meta.json") as f:
            meta = json.load(f)
        dates = pd.date_range("2005-01-01", "2023-12-31", freq="QE")[:X_3d.shape[0]]

        # Crisis labels
        CRISIS_QUARTERS = {
            "2007-12-31", "2008-03-31", "2008-06-30", "2008-09-30",
            "2008-12-31", "2009-03-31", "2009-06-30",
            "2020-03-31", "2020-06-30",
            "2011-09-30", "2011-12-31", "2012-03-31", "2012-06-30",
        }
        y_quarter = np.array([1 if str(d.date()) in CRISIS_QUARTERS else 0
                              for d in dates], dtype=int)
        source = 'FDIC + World Bank (real cached)'
        return X_3d, dates, y_quarter, meta, source

    # Synthetic fallback — 25 banks, 76 quarters, 5 features
    print('    [Using synthetic G-SIB data — cache not found]')
    rng = np.random.RandomState(42)
    T, N, d = 76, 25, 5
    X_3d = rng.randn(T, N, d) * 0.3

    # Inject GFC crisis signature (Q12-Q18 ≈ 2007Q4–2009Q2)
    for t in range(12, 19):
        X_3d[t, :, 0] += 2.0  # credit spike
        X_3d[t, :, 1] += 1.5  # stress
        X_3d[t, :, 2] += 1.0  # spread widening
        X_3d[t, :, 3] -= 1.0  # yield curve inversion
        X_3d[t, :, 4] += 2.5  # VIX spike
        X_3d[t] += rng.randn(N, d) * 0.2

    # COVID shock (Q60-Q61)
    for t in range(60, 62):
        X_3d[t, :, 0] += 1.5
        X_3d[t, :, 1] += 2.0
        X_3d[t, :, 4] += 3.0
        X_3d[t] += rng.randn(N, d) * 0.15

    y_quarter = np.zeros(T, dtype=int)
    y_quarter[12:19] = 1  # GFC
    y_quarter[60:62] = 1  # COVID

    import pandas as pd
    dates = pd.date_range("2005-01-01", periods=T, freq="QE")
    meta = [{'name': f'Bank_{i}', 'data_source': 'synthetic'} for i in range(N)]
    source = 'synthetic (25 banks, 76Q)'
    return X_3d, dates, y_quarter, meta, source


def run_bank():
    print()
    print('=' * 76)
    print('  DATASET 2: G-SIB Bank-Level Panel — Crisis Early Warning')
    print('=' * 76)

    X_3d, dates, y_quarter, meta, source = load_bank_data()
    T, N, d = X_3d.shape
    print(f'  Source: {source}')
    print(f'  Panel: T={T} quarters, N={N} banks, d={d} features')
    print(f'  Crisis quarters: {int(y_quarter.sum())}/{T}')
    print()

    # Flatten to panel
    X_panel = X_3d.reshape(T * N, d)
    y_panel = np.repeat(y_quarter, N)

    results = {}

    # ── A. Full engine scores ─────────────────────────────────────
    print('  A. Full engine scores (O(N²d) baseline)')
    for name, eng in [
        ('Mol_Full',    MolecularEngine(iterations=80, k_neighbors=15, use_fused=True)),
        ('Grav_Full',   GravityModeEngine(iterations=60, k_neighbors=15, use_fused=True)),
        ('Hybrid_Full', HybridGravityEngine()),
    ]:
        t0 = time.time()
        scores = eng.fit_score(X_panel, y_panel)
        results[name] = print_metrics(name, scores, y_panel, time.time() - t0)

    # ── B. ReducedTensorDescriptor ─────────────────────────────────
    print()
    print('  B. ReducedTensorDescriptor (O(Nd+d³) reduced)')

    X_ref = X_panel[y_panel == 0]
    desc = ReducedTensorDescriptor(k_neighbors=15)
    t0 = time.time()
    desc.fit(X_ref)
    D = desc.transform(X_panel)
    elapsed_desc = time.time() - t0
    n_eigs = desc.n_eigs

    print(f'    Descriptor shape: {D.shape}  (n_eigs={n_eigs})')
    print(f'    Complexity: {desc.complexity_info()["total"]}')
    print(f'    Compute time: {elapsed_desc:.2f}s')
    print()

    desc_scores = score_from_descriptor(D, n_eigs)
    results['Desc_Combined'] = print_metrics('Desc_Combined', desc_scores, y_panel, elapsed_desc)

    # Score via built-in method
    desc_auto_scores = desc.score(X_panel)
    results['Desc_Auto'] = print_metrics('Desc_Auto', desc_auto_scores, y_panel)

    results['Desc_GradNorm'] = print_metrics('Desc_GradNorm', D[:, 0], y_panel)
    results['Desc_Mahalanobis'] = print_metrics('Desc_Mahalanobis', D[:, n_eigs+1], y_panel)
    results['Desc_MedoidDist'] = print_metrics('Desc_MedoidDist', D[:, n_eigs+2], y_panel)

    alarm = desc.get_alarm(X_panel)
    alarm_auc = roc_auc_score(y_panel, alarm.astype(float))
    alarm_f1 = f1_score(y_panel, alarm.astype(int), zero_division=0)
    print(f'    {"Desc_MorseAlarm":<28} AUC={alarm_auc:.4f}  '
          f'F1={alarm_f1:.3f}  (binary: ind≥1)')
    results['Desc_MorseAlarm'] = dict(auc=alarm_auc, f1=alarm_f1)

    # ── C. Quarter-level analysis ─────────────────────────────────
    print()
    print('  C. Quarter-level detection (aggregated per quarter)')
    scores_q = desc_scores.reshape(T, N).mean(axis=1)
    normal_q = np.where(y_quarter == 0)[0]
    crisis_q = np.where(y_quarter == 1)[0]
    thresh_95 = np.percentile(scores_q[normal_q], 95)
    detected = np.sum(scores_q[crisis_q] >= thresh_95)
    false_alarms = np.sum(scores_q[normal_q] >= thresh_95)
    print(f'    Detected crisis Q: {detected}/{len(crisis_q)}')
    print(f'    False alarm Q:     {false_alarms}/{len(normal_q)}')
    print(f'    Quarter-level AUC: {roc_auc_score(y_quarter, scores_q):.4f}')

    # Morse alarm per quarter
    alarm_q = alarm.reshape(T, N).mean(axis=1)
    alarm_q_auc = roc_auc_score(y_quarter, alarm_q)
    print(f'    Morse alarm Q-AUC: {alarm_q_auc:.4f}')

    # ── D. Degeneracy check ───────────────────────────────────────
    print()
    print('  D. DEGENERACY CHECK — Full vs Reduced')
    full_auc = results['Hybrid_Full']['auc']
    reduced_auc = max(results['Desc_Combined']['auc'],
                      results.get('Desc_Auto', {}).get('auc', 0))
    delta = reduced_auc - full_auc
    print(f'    Full Hybrid AUC:     {full_auc:.4f}')
    print(f'    Best Reduced AUC:    {reduced_auc:.4f}')
    print(f'    Delta:               {delta:+.4f}')
    if abs(delta) < 0.02:
        print(f'    ✓ NO DEGENERACY — descriptor matches full engine (|Δ|<0.02)')
    elif delta > 0:
        print(f'    ✓ IMPROVED — reduced descriptor outperforms full engine')
    else:
        print(f'    ✗ DEGENERATE — reduced descriptor lost {abs(delta):.4f} AUC')

    return results


# ═══════════════════════════════════════════════════════════════════
#  FRESH PREDICTION — descriptor-only, no engine scores
# ═══════════════════════════════════════════════════════════════════

def fresh_prediction_ercot():
    """Completely fresh prediction using only ReducedTensorDescriptor.
    No engines, no fused scoring — pure descriptor from fit(X_normal).
    """
    print()
    print('=' * 76)
    print('  FRESH PREDICTION — ERCOT (descriptor-only, no engine)')
    print('=' * 76)

    X, y, y_hour, T_h, N_ag, _, capacity = load_ercot_dataset()

    # Use first 60% as 'normal' reference (before crisis onset)
    n_ref = int(0.6 * len(X))
    X_ref = X[:n_ref]

    desc = ReducedTensorDescriptor(k_neighbors=15)
    t0 = time.time()
    desc.fit(X_ref)
    D = desc.transform(X)
    elapsed = time.time() - t0

    n_eigs = desc.n_eigs
    scores = score_from_descriptor(D, n_eigs)
    scores_auto = desc.score(X)
    alarm = desc.get_alarm(X)
    morse_idx = desc.get_morse_index(X)

    auc = roc_auc_score(y, scores)
    auc_auto = roc_auc_score(y, scores_auto)
    best_scores = scores_auto if auc_auto > auc else scores
    best_auc = max(auc, auc_auto)
    far = far_at_recall(best_scores, y, 0.95)
    th, f1 = best_f1(best_scores, y)
    alarm_auc = roc_auc_score(y, alarm.astype(float))

    print(f'  Ref: first {n_ref} samples (pre-crisis)')
    print(f'  Time: {elapsed:.2f}s')
    print(f'  AUC (manual): {auc:.4f}')
    print(f'  AUC (auto):   {auc_auto:.4f}')
    print(f'  FAR@95R:    {far:.3f}')
    print(f'  F1:         {f1:.3f}')
    print(f'  Alarm AUC:  {alarm_auc:.4f}')
    print(f'  Morse dist: ind=0: {(morse_idx==0).sum()}, ind≥1: {(morse_idx>=1).sum()}')

    # Hourly timeline
    scores_h = best_scores.reshape(T_h, N_ag).mean(axis=1)
    alarm_h = alarm.reshape(T_h, N_ag).mean(axis=1)
    crisis_start_h = np.where(y_hour == 1)[0][0]
    normal_scores = scores_h[:crisis_start_h]
    thresh_h = np.percentile(normal_scores, 95)
    first_alarm_h = np.where(scores_h >= thresh_h)[0]
    if len(first_alarm_h) > 0:
        lead = crisis_start_h - first_alarm_h[0]
        print(f'  First alarm: hour {first_alarm_h[0]} '
              f'({lead}h = {lead/24:.1f}d before crisis)')

    return dict(auc=best_auc, far=far, f1=f1, alarm_auc=alarm_auc)


def fresh_prediction_bank():
    """Completely fresh prediction on bank-level data."""
    print()
    print('=' * 76)
    print('  FRESH PREDICTION — BANK-LEVEL (descriptor-only, no engine)')
    print('=' * 76)

    X_3d, dates, y_quarter, meta, source = load_bank_data()
    T, N, d = X_3d.shape
    X_panel = X_3d.reshape(T * N, d)
    y_panel = np.repeat(y_quarter, N)

    # Calibration window: first 10 quarters (assumed normal)
    n_calib_q = 10
    n_calib = n_calib_q * N
    X_ref = X_panel[:n_calib]

    desc = ReducedTensorDescriptor(k_neighbors=15)
    t0 = time.time()
    desc.fit(X_ref)
    D = desc.transform(X_panel)
    elapsed = time.time() - t0

    n_eigs = desc.n_eigs
    scores = score_from_descriptor(D, n_eigs)
    scores_auto = desc.score(X_panel)
    alarm = desc.get_alarm(X_panel)
    morse_idx = desc.get_morse_index(X_panel)

    auc = roc_auc_score(y_panel, scores)
    auc_auto = roc_auc_score(y_panel, scores_auto)
    best_scores = scores_auto if auc_auto > auc else scores
    best_auc = max(auc, auc_auto)
    far = far_at_recall(best_scores, y_panel, 0.95)
    th, f1 = best_f1(best_scores, y_panel)
    alarm_auc = roc_auc_score(y_panel, alarm.astype(float))

    print(f'  Source: {source}')
    print(f'  Ref: first {n_calib_q} quarters ({n_calib} bank-quarters)')
    print(f'  Time: {elapsed:.2f}s')
    print(f'  AUC (manual): {auc:.4f}')
    print(f'  AUC (auto):   {auc_auto:.4f}')
    print(f'  FAR@95R:    {far:.3f}')
    print(f'  Fbest_1:         {f1:.3f}')
    print(f'  Alarm AUC:  {alarm_auc:.4f}')
    print(f'  Morse dist: ind=0: {(morse_idx==0).sum()}, ind≥1: {(morse_idx>=1).sum()}')

    # Quarter-level
    scores_q = scores.reshape(T, N).mean(axis=1)
    q_auc = roc_auc_score(y_quarter, scores_q)
    print(f'  Quarter AUC: {q_auc:.4f}')

    # GFC early warning
    import pandas as pd
    gfc_start = pd.Timestamp("2007-12-31")
    buildup_q = [i for i, d in enumerate(dates)
                 if d >= pd.Timestamp("2007-03-31") and d < gfc_start]
    if buildup_q:
        buildup_scores = scores_q[buildup_q]
        normal_scorebest_s = scores_q[y_quarter == 0]
        thresh_99 = np.percentile(normal_scores, 99)
        flagged = sum(1 for s in buildup_scores if s >= thresh_99)
        print(f'  GFC build-up: {flagged}/{len(buildup_q)} quarters flagged (early warning)')

    return dict(auc=auc, far=far, f1=f1, alarm_auc=alarm_auc, q_auc=q_auc)


# ═══════════════════════════════════════════════════════════════════
#  SUMMARY
# ═══════════════════════════════════════════════════════════════════

def print_summary(ercot_res, bank_res, ercot_fresh, bank_fresh):
    print()
    print('=' * 76)
    print('  SUMMARY — Full Engine vs ReducedTensorDescriptor')
    print('=' * 76)
    print()
    print(f'  {"Dataset":<20} {"Method":<22} {"AUC":>7} {"FAR":>7} {"F1":>7}')
    print(f'  {"-"*20} {"-"*22} {"-"*7} {"-"*7} {"-"*7}')

    for ds_name, res in [('ERCOT', ercot_res), ('Bank-Level', bank_res)]:
        for m in ['Hybrid_Full', 'Desc_Combined']:
            if m in res:
                r = res[m]
                print(f'  {ds_name:<20} {m:<22} {r["auc"]:7.4f} '
                      f'{r.get("far",0):7.3f} {r.get("f1",0):7.3f}')
        print()

    print(f'  {"ERCOT (fresh)":<20} {"Desc-Only":<22} '
          f'{ercot_fresh["auc"]:7.4f} {ercot_fresh["far"]:7.3f} {ercot_fresh["f1"]:7.3f}')
    print(f'  {"Bank (fresh)":<20} {"Desc-Only":<22} '
          f'{bank_fresh["auc"]:7.4f} {bank_fresh["far"]:7.3f} {bank_fresh["f1"]:7.3f}')

    print()
    # Overall verdict
    all_aucs = []
    for r in [ercot_res, bank_res]:
        if 'Hybrid_Full' in r and 'Desc_Combined' in r:
            delta = r['Desc_Combined']['auc'] - r['Hybrid_Full']['auc']
            all_aucs.append(delta)
    avg_delta = np.mean(all_aucs)
    print(f'  Average AUC delta (Reduced - Full): {avg_delta:+.4f}')
    if avg_delta >= -0.02:
        print(f'  VERDICT: ✓ NO DEGENERACY — ReducedTensorDescriptor is viable')
    else:
        print(f'  VERDICT: ✗ DEGENERATE — Reduced descriptor loses too much')


# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print()
    print('╔' + '═' * 74 + '╗')
    print('║  ReducedTensorDescriptor — Degeneracy Test on Real-World Data       ║')
    print('║  O(Nd+d³) vs O(N²d): does the reduced descriptor degenerate?        ║')
    print('╚' + '═' * 74 + '╝')
    print()

    ercot_res = run_ercot()
    bank_res = run_bank()
    ercot_fresh = fresh_prediction_ercot()
    bank_fresh = fresh_prediction_bank()
    print_summary(ercot_res, bank_res, ercot_fresh, bank_fresh)
