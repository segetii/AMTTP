"""
Full System Benchmark — Reduced Tensor + All Engines + All BSDT Variants
=========================================================================
Runs:
  1. ReducedTensorDescriptor with Molecular, Gravity, Hybrid engines
  2. All 5 BSDT scoring variants (Baseline, Full-BSDT, QuadSurf, SignedFisher, ExpoGate)
  3. Fresh FRED economic prediction for March 2026 outlook

Datasets: ERCOT grid failure + U.S. Banking (FRED macro)
"""
from __future__ import annotations
import sys, time, warnings, json
import numpy as np
from pathlib import Path
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score

warnings.filterwarnings("ignore")

ROOT = Path(r"c:\amttp")
UDL_DIR = ROOT / "research" / "udl"
AF_DIR  = ROOT / "research" / "adaptive-friction"

sys.path.insert(0, str(UDL_DIR))
sys.path.insert(0, str(UDL_DIR / "src"))
sys.path.insert(0, str(AF_DIR / "pipeline"))
sys.path.insert(0, str(AF_DIR / "variants"))

from udl.system_mode import (
    BSDTChannels, ReducedTensorDescriptor,
    MolecularEngine, GravityModeEngine, HybridGravityEngine,
    SystemModeEngine,
)
from bench_economy_ercot import load_ercot_dataset, load_economy_dataset


# ── helpers ─────────────────────────────────────────────────────────

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


def print_row(label, scores, y, elapsed=None):
    auc = roc_auc_score(y, scores)
    far = far_at_recall(scores, y, 0.95)
    th, f1 = best_f1(scores, y)
    preds = (scores >= th).astype(int)
    prec = precision_score(y, preds, zero_division=0)
    rec  = recall_score(y, preds, zero_division=0)
    t_str = f'{elapsed:.1f}s' if elapsed else '—'
    print(f'  {label:<32} AUC={auc:.4f}  FAR={far:.3f}  '
          f'F1={f1:.3f}  P={prec:.3f}  R={rec:.3f}  T={t_str}')
    return dict(label=label, auc=auc, far=far, f1=f1, prec=prec, rec=rec)


def sep(title):
    print()
    print('=' * 80)
    print(f'  {title}')
    print('=' * 80)


# ═════════════════════════════════════════════════════════════════════
#  SECTION 1: ALL ENGINES — ERCOT
# ═════════════════════════════════════════════════════════════════════

def run_engines_ercot():
    sep('SECTION 1: ALL ENGINES — ERCOT Grid Failure')
    X, y, y_hour, T_h, N_ag, agent_types, capacity = load_ercot_dataset()
    X_ref = X[y == 0]
    print(f'  Data: {X.shape}, crisis={int(y.sum())}/{len(y)} ({y.mean():.1%})')
    print()

    results = {}

    # ── A. Full engines ───────────────────────────────────────────
    print('  A. Full Engine Scores')
    for name, eng in [
        ('Molecular',   MolecularEngine(iterations=80, k_neighbors=15, use_fused=True)),
        ('Gravity',     GravityModeEngine(iterations=60, k_neighbors=15, use_fused=True)),
        ('Hybrid',      HybridGravityEngine()),
    ]:
        t0 = time.time()
        scores = eng.fit_score(X, y)
        results[name] = print_row(name, scores, y, time.time() - t0)

    # ── B. ReducedTensorDescriptor ─────────────────────────────────
    print()
    print('  B. ReducedTensorDescriptor (O(Nd+d³))')
    desc = ReducedTensorDescriptor(k_neighbors=15)
    t0 = time.time()
    desc.fit(X_ref)
    desc_scores = desc.score(X)
    elapsed = time.time() - t0
    results['Reduced_Tensor'] = print_row('ReducedTensor', desc_scores, y, elapsed)

    # Morse alarm
    alarm = desc.get_alarm(X)
    alarm_auc = roc_auc_score(y, alarm.astype(float))
    alarm_f1 = f1_score(y, alarm.astype(int), zero_division=0)
    print(f'  {"  Morse Alarm":<32} AUC={alarm_auc:.4f}  F1={alarm_f1:.3f}')
    results['Morse_Alarm'] = dict(auc=alarm_auc, f1=alarm_f1)

    # ── C. All 5 BSDT Variants ────────────────────────────────────
    print()
    print('  C. BSDT Scoring Variants (Fisher VR weights)')
    var_results = desc.score_variants(X, y, X_ref=X_ref)
    for vname, vr in var_results.items():
        s = vr['scores']
        auc = vr.get('auroc', roc_auc_score(y, s))
        far = far_at_recall(s, y, 0.95)
        th, f1 = best_f1(s, y)
        t_ms = vr.get('time', 0) * 1000
        print(f'  {"  " + vname:<32} AUC={auc:.4f}  FAR={far:.3f}  '
              f'F1={f1:.3f}  T={t_ms:.0f}ms')
        results[f'BSDT_{vname}'] = dict(auc=auc, far=far, f1=f1)

    # ── D. Fisher VR channel weights ───────────────────────────────
    print()
    print('  D. Fisher VR Channel Analysis')
    bsdt = BSDTChannels(k=15)
    bsdt.fit(X_ref)
    ch = bsdt.channels(X)
    try:
        fw = bsdt._fisher_weights(X)
        if isinstance(fw, dict):
            w = fw.get('weights', np.ones(4)/4)
            signs = fw.get('signs', np.ones(4))
        else:
            w, signs = fw[0], fw[1]
        names = ['δ_C', 'δ_G', 'δ_A', 'δ_T']
        print(f'    {"Channel":<8} {"Weight":>8} {"Sign":>6}')
        for i in range(4):
            print(f'    {names[i]:<8} {w[i]:8.4f} {signs[i]:+6.0f}')
    except Exception as e:
        print(f'    [Fisher weights error: {e}]')

    # Channel-level crash signature
    print()
    print('  E. Channel Crash Signature')
    ch_normal = {k: v[y == 0] for k, v in ch.items()}
    ch_crisis = {k: v[y == 1] for k, v in ch.items()}
    for k in ['delta_C', 'delta_G', 'delta_A', 'delta_T']:
        mn = ch_normal[k].mean()
        mc = ch_crisis[k].mean()
        ratio = mc / (mn + 1e-12)
        print(f'    {k:<10} normal={mn:.4f}  crisis={mc:.4f}  ratio={ratio:.2f}x')

    return results, X, y, X_ref


# ═════════════════════════════════════════════════════════════════════
#  SECTION 2: ALL ENGINES — U.S. BANKING (FRED)
# ═════════════════════════════════════════════════════════════════════

def run_engines_economy():
    sep('SECTION 2: ALL ENGINES — U.S. Economy (FRED Macro)')
    try:
        X, y, dates, sector_names, y_quarter, X_3d = load_economy_dataset()
    except Exception as e:
        print(f'  [!] FRED data unavailable: {e}')
        print(f'  Falling back to synthetic banking data...')
        return run_engines_bank_synthetic()

    T, N, d = X_3d.shape
    X_ref = X[y == 0]
    print(f'  Data: T={T}Q, N={N} sectors, d={d} features')
    print(f'  Panel: {X.shape}, crisis={int(y.sum())}/{len(y)} ({y.mean():.1%})')
    print(f'  Date range: {dates[0].date()} → {dates[-1].date()}')
    print()

    results = {}

    # ── A. Full engines ───────────────────────────────────────────
    print('  A. Full Engine Scores')
    for name, eng in [
        ('Molecular',   MolecularEngine(iterations=80, k_neighbors=15, use_fused=True)),
        ('Gravity',     GravityModeEngine(iterations=60, k_neighbors=15, use_fused=True)),
        ('Hybrid',      HybridGravityEngine()),
    ]:
        t0 = time.time()
        scores = eng.fit_score(X, y)
        results[name] = print_row(name, scores, y, time.time() - t0)

    # ── B. ReducedTensorDescriptor ─────────────────────────────────
    print()
    print('  B. ReducedTensorDescriptor (O(Nd+d³))')
    desc = ReducedTensorDescriptor(k_neighbors=15)
    t0 = time.time()
    desc.fit(X_ref)
    desc_scores = desc.score(X)
    elapsed = time.time() - t0
    results['Reduced_Tensor'] = print_row('ReducedTensor', desc_scores, y, elapsed)

    # Morse alarm
    alarm = desc.get_alarm(X)
    alarm_auc = roc_auc_score(y, alarm.astype(float))
    alarm_f1 = f1_score(y, alarm.astype(int), zero_division=0)
    print(f'  {"  Morse Alarm":<32} AUC={alarm_auc:.4f}  F1={alarm_f1:.3f}')

    # ── C. All 5 BSDT Variants ────────────────────────────────────
    print()
    print('  C. BSDT Scoring Variants (Fisher VR weights)')
    var_results = desc.score_variants(X, y, X_ref=X_ref)
    for vname, vr in var_results.items():
        s = vr['scores']
        auc = vr.get('auroc', roc_auc_score(y, s))
        far = far_at_recall(s, y, 0.95)
        th, f1 = best_f1(s, y)
        t_ms = vr.get('time', 0) * 1000
        print(f'  {"  " + vname:<32} AUC={auc:.4f}  FAR={far:.3f}  '
              f'F1={f1:.3f}  T={t_ms:.0f}ms')
        results[f'BSDT_{vname}'] = dict(auc=auc, far=far, f1=f1)

    # ── D. Fisher VR channel analysis ──────────────────────────────
    print()
    print('  D. Fisher VR Channel Analysis')
    bsdt = BSDTChannels(k=15)
    bsdt.fit(X_ref)
    ch = bsdt.channels(X)
    try:
        fw = bsdt._fisher_weights(X)
        if isinstance(fw, dict):
            w = fw.get('weights', np.ones(4)/4)
            signs = fw.get('signs', np.ones(4))
        else:
            w, signs = fw[0], fw[1]
        names = ['δ_C', 'δ_G', 'δ_A', 'δ_T']
        print(f'    {"Channel":<8} {"Weight":>8} {"Sign":>6}')
        for i in range(4):
            print(f'    {names[i]:<8} {w[i]:8.4f} {signs[i]:+6.0f}')
    except Exception as e:
        print(f'    [Fisher weights error: {e}]')

    # ── E. Quarter-level detection ─────────────────────────────────
    print()
    print('  E. Quarter-Level Detection')
    # Use best variant
    best_var = max(var_results.items(), key=lambda kv: kv[1].get('auroc', 0))
    best_scores = best_var[1]['scores']
    scores_q = best_scores.reshape(T, N).mean(axis=1)
    q_auc = roc_auc_score(y_quarter, scores_q)
    normal_q_scores = scores_q[y_quarter == 0]
    thresh95 = np.percentile(normal_q_scores, 95)
    crisis_q = np.where(y_quarter == 1)[0]
    detected = np.sum(scores_q[crisis_q] >= thresh95)
    print(f'    Best variant: {best_var[0]}')
    print(f'    Quarter-level AUC: {q_auc:.4f}')
    print(f'    Detected crisis Q: {detected}/{len(crisis_q)}')

    # GFC early warning
    import pandas as pd
    gfc_q = [i for i, d in enumerate(dates)
             if d >= pd.Timestamp("2007-12-31") and d <= pd.Timestamp("2009-06-30")]
    if gfc_q:
        pre_gfc = [i for i, d in enumerate(dates)
                   if d >= pd.Timestamp("2007-03-31") and d < pd.Timestamp("2007-12-31")]
        if pre_gfc:
            pre_scores = scores_q[pre_gfc]
            flagged = sum(1 for s in pre_scores if s >= thresh95)
            print(f'    GFC early warning: {flagged}/{len(pre_gfc)} pre-crisis Q flagged')

    return results, X, y, X_ref, dates, y_quarter, X_3d, sector_names


def run_engines_bank_synthetic():
    """Fallback with synthetic bank data."""
    rng = np.random.RandomState(42)
    T, N, d = 76, 25, 5
    X_3d = rng.randn(T, N, d) * 0.3
    for t in range(12, 19):
        X_3d[t, :, 0] += 2.0; X_3d[t, :, 1] += 1.5
        X_3d[t, :, 2] += 1.0; X_3d[t, :, 3] -= 1.0; X_3d[t, :, 4] += 2.5
    for t in range(60, 62):
        X_3d[t, :, 0] += 1.5; X_3d[t, :, 1] += 2.0; X_3d[t, :, 4] += 3.0

    y_quarter = np.zeros(T, dtype=int)
    y_quarter[12:19] = 1; y_quarter[60:62] = 1

    X = X_3d.reshape(T * N, d)
    y = np.repeat(y_quarter, N)
    X_ref = X[y == 0]

    import pandas as pd
    dates = pd.date_range("2005-01-01", periods=T, freq="QE")

    results = {}
    print('  [Using synthetic 25-bank panel]')
    print(f'  Data: T={T}Q, N={N} banks, d={d}')
    print(f'  Crisis: {int(y_quarter.sum())}/{T} quarters')
    print()

    # A. Full engines
    print('  A. Full Engine Scores')
    for name, eng in [
        ('Molecular',   MolecularEngine(iterations=80, k_neighbors=15, use_fused=True)),
        ('Gravity',     GravityModeEngine(iterations=60, k_neighbors=15, use_fused=True)),
        ('Hybrid',      HybridGravityEngine()),
    ]:
        t0 = time.time()
        scores = eng.fit_score(X, y)
        results[name] = print_row(name, scores, y, time.time() - t0)

    # B. Reduced Tensor
    print()
    print('  B. ReducedTensorDescriptor')
    desc = ReducedTensorDescriptor(k_neighbors=15)
    t0 = time.time()
    desc.fit(X_ref)
    desc_scores = desc.score(X)
    elapsed = time.time() - t0
    results['Reduced_Tensor'] = print_row('ReducedTensor', desc_scores, y, elapsed)

    # C. BSDT variants
    print()
    print('  C. BSDT Scoring Variants')
    var_results = desc.score_variants(X, y, X_ref=X_ref)
    for vname, vr in var_results.items():
        s = vr['scores']
        auc = vr.get('auroc', roc_auc_score(y, s))
        far = far_at_recall(s, y, 0.95)
        th, f1 = best_f1(s, y)
        print(f'  {"  " + vname:<32} AUC={auc:.4f}  FAR={far:.3f}  F1={f1:.3f}')
        results[f'BSDT_{vname}'] = dict(auc=auc, far=far, f1=f1)

    return results, X, y, X_ref, dates, y_quarter, X_3d, ['Bank'] * N


# ═════════════════════════════════════════════════════════════════════
#  SECTION 3: FRESH ECONOMIC PREDICTION — March 2026
# ═════════════════════════════════════════════════════════════════════

def run_fresh_prediction():
    sep('SECTION 3: FRESH ECONOMIC PREDICTION — March 2026 Outlook')

    try:
        from fred_loader import fetch_all, apply_transforms, standardise
        from state_matrix import build_state_matrix, SECTOR_NAMES, get_normal_period
        from mfls_variants import CRISIS_QUARTERS, make_crisis_labels
    except ImportError as e:
        print(f'  [!] Pipeline import failed: {e}')
        return None

    # ── Fetch fresh FRED data ──────────────────────────────────────
    print('  Fetching FRED macro data (cached or live)...')
    try:
        raw = fetch_all(use_cache=True, verbose=True)
    except Exception as e:
        print(f'  [!] FRED fetch failed: {e}')
        return None

    xf = apply_transforms(raw)
    std, mu, sig = standardise(xf)
    X_3d, dates = build_state_matrix(std)
    T, N, d = X_3d.shape

    print(f'\n  Macro data: T={T} quarters, N={N} sectors, d={d} features')
    print(f'  Date range: {dates[0].date()} → {dates[-1].date()}')

    # Crisis labels
    y_quarter = make_crisis_labels(dates)
    X_panel = X_3d.reshape(T * N, d)
    y_panel = np.repeat(y_quarter, N)
    X_ref = X_panel[y_panel == 0]

    # ── Latest data snapshot ───────────────────────────────────────
    print()
    print('  ── Latest FRED Data Snapshot ──')
    latest = raw.iloc[-1]
    print(f'  Latest quarter: {raw.index[-1].date()}')
    for col in raw.columns:
        val = latest[col]
        if not np.isnan(val):
            print(f'    {col:<16} = {val:.4f}')

    # ── Show recent trend (last 8 quarters) ────────────────────────
    print()
    print('  ── Recent Trend (last 8 quarters) ──')
    n_recent = min(8, len(raw))
    recent = raw.iloc[-n_recent:]
    for col in ['vix', 'stlfsi', 'slope_10y2y', 'baa_spread', 'fed_funds']:
        if col in recent.columns:
            vals = recent[col].dropna()
            if len(vals) >= 2:
                trend = 'RISING' if vals.iloc[-1] > vals.iloc[-4] else 'FALLING'
                print(f'    {col:<16} {vals.iloc[-4]:.2f} → {vals.iloc[-1]:.2f}  [{trend}]')

    # ── Run engines on full history ────────────────────────────────
    print()
    print('  ── Engine Scores on Full Economic History ──')
    results = {}
    for name, eng in [
        ('Molecular',  MolecularEngine(iterations=80, k_neighbors=15, use_fused=True)),
        ('Gravity',    GravityModeEngine(iterations=60, k_neighbors=15, use_fused=True)),
        ('Hybrid',     HybridGravityEngine()),
    ]:
        t0 = time.time()
        scores = eng.fit_score(X_panel, y_panel)
        results[name] = print_row(name, scores, y_panel, time.time() - t0)

    # ── ReducedTensorDescriptor ────────────────────────────────────
    print()
    print('  ── ReducedTensorDescriptor ──')
    desc = ReducedTensorDescriptor(k_neighbors=15)
    t0 = time.time()
    desc.fit(X_ref)
    desc_scores = desc.score(X_panel)
    elapsed = time.time() - t0
    results['Reduced_Tensor'] = print_row('ReducedTensor', desc_scores, y_panel, elapsed)

    # ── All 5 BSDT variants ───────────────────────────────────────
    print()
    print('  ── BSDT Scoring Variants ──')
    var_results = desc.score_variants(X_panel, y_panel, X_ref=X_ref)
    for vname, vr in var_results.items():
        s = vr['scores']
        auc = vr.get('auroc', roc_auc_score(y_panel, s))
        far = far_at_recall(s, y_panel, 0.95)
        th, f1 = best_f1(s, y_panel)
        print(f'  {"  " + vname:<32} AUC={auc:.4f}  FAR={far:.3f}  F1={f1:.3f}')
        results[f'BSDT_{vname}'] = dict(auc=auc, far=far, f1=f1)

    # ── PREDICTION: Score the LAST 4 quarters ──────────────────────
    print()
    print('  ══════════════════════════════════════════════════════')
    print('  ██  FRESH PREDICTION — Current Economic State  ██')
    print('  ══════════════════════════════════════════════════════')

    # Use the best-performing BSDT variant scores
    best_var_name = max(var_results.items(),
                        key=lambda kv: kv[1].get('auroc', 0))[0]
    best_scores = var_results[best_var_name]['scores']

    # Reshape to (T, N) and get quarter-level scores
    scores_q = best_scores.reshape(T, N).mean(axis=1)

    # Normal-period score statistics
    normal_mask = y_quarter == 0
    mu_norm = scores_q[normal_mask].mean()
    std_norm = scores_q[normal_mask].std()
    thresh_95 = np.percentile(scores_q[normal_mask], 95)
    thresh_99 = np.percentile(scores_q[normal_mask], 99)

    print(f'\n  Scoring method: {best_var_name} (Fisher VR, zero label leakage)')
    print(f'  Normal-period: μ={mu_norm:.4f}, σ={std_norm:.4f}')
    print(f'  95th pctile threshold: {thresh_95:.4f}')
    print(f'  99th pctile threshold: {thresh_99:.4f}')

    # Last 8 quarters timeline
    print()
    print(f'  {"Quarter":<14} {"Score":>8} {"z-score":>8} {"Status":<20}')
    print(f'  {"-"*14} {"-"*8} {"-"*8} {"-"*20}')
    n_show = min(8, T)
    for i in range(T - n_show, T):
        q_date = dates[i].date() if i < len(dates) else f'Q{i}'
        s = scores_q[i]
        z = (s - mu_norm) / (std_norm + 1e-12)
        if s >= thresh_99:
            status = '🔴 CRITICAL (>99%)'
        elif s >= thresh_95:
            status = '🟠 ELEVATED (>95%)'
        elif z > 1.5:
            status = '🟡 WATCH (z>1.5)'
        else:
            status = '🟢 NORMAL'
        is_crisis = '  [CRISIS]' if (i < len(y_quarter) and y_quarter[i] == 1) else ''
        print(f'  {str(q_date):<14} {s:8.4f} {z:+8.3f} {status}{is_crisis}')

    # ── BSDT channel decomposition for latest quarter ────────────
    print()
    print('  ── Channel Decomposition — Latest Quarter ──')
    bsdt = BSDTChannels(k=15)
    bsdt.fit(X_ref)
    X_latest = X_panel[-N:]  # last quarter = N agents
    ch = bsdt.channels(X_latest)
    ch_all = bsdt.channels(X_panel)

    ch_names = ['delta_C', 'delta_G', 'delta_A', 'delta_T']
    print(f'    {"Channel":<12} {"Current":>10} {"Normal μ":>10} {"Normal σ":>10} {"z-score":>10}')
    for k in ch_names:
        curr = ch[k].mean()
        norm_vals = ch_all[k][y_panel == 0]
        nm, ns = norm_vals.mean(), norm_vals.std()
        z = (curr - nm) / (ns + 1e-12)
        print(f'    {k:<12} {curr:10.4f} {nm:10.4f} {ns:10.4f} {z:+10.3f}')

    # ── Forward-looking risk assessment ────────────────────────────
    print()
    print('  ── Forward-Looking Risk Assessment (March 2026) ──')
    latest_score = scores_q[-1]
    latest_z = (latest_score - mu_norm) / (std_norm + 1e-12)

    # Trend: rising or falling over last 4 quarters
    if T >= 4:
        trend_4q = scores_q[-1] - scores_q[-4]
        trend_dir = 'RISING' if trend_4q > 0 else 'FALLING'
        momentum = abs(trend_4q) / (std_norm + 1e-12)
    else:
        trend_4q, trend_dir, momentum = 0, 'FLAT', 0

    # MFLS gradient (is gradient landscape degenerating?)
    mfls_latest = bsdt.mfls(X_latest)
    mfls_normal = bsdt.mfls(X_ref[:N])
    mfls_ratio = mfls_latest.mean() / (mfls_normal.mean() + 1e-12)

    # Morse index (saddle point detection)
    morse = desc.get_morse_index(X_latest)
    morse_frac = (morse >= 1).mean()

    print(f'    Current score:       {latest_score:.4f} (z={latest_z:+.2f})')
    print(f'    4Q trend:            {trend_dir} (Δ={trend_4q:+.4f}, '
          f'momentum={momentum:.2f}σ)')
    print(f'    MFLS ratio:          {mfls_ratio:.3f}x normal '
          f'({"⚠ ELEVATED" if mfls_ratio > 1.5 else "normal"})')
    print(f'    Morse saddle frac:   {morse_frac:.1%} '
          f'({"⚠ UNSTABLE" if morse_frac > 0.2 else "stable"})')

    # Overall assessment
    risk_signals = 0
    if latest_z > 1.5: risk_signals += 1
    if trend_dir == 'RISING' and momentum > 1.0: risk_signals += 1
    if mfls_ratio > 1.5: risk_signals += 1
    if morse_frac > 0.2: risk_signals += 1

    print()
    if risk_signals >= 3:
        print('    ████ ASSESSMENT: HIGH RISK — multiple indicators elevated ████')
        print('    Multiple structural risk channels are activated.')
        print('    The system may be approaching a phase transition.')
    elif risk_signals >= 2:
        print('    ██ ASSESSMENT: ELEVATED RISK — some indicators above normal ██')
        print('    Monitor closely; system shows early-stage stress.')
    elif risk_signals >= 1:
        print('    █ ASSESSMENT: WATCH — one indicator mildly elevated █')
        print('    No immediate concern but continued monitoring warranted.')
    else:
        print('    ✓ ASSESSMENT: LOW RISK — all indicators within normal range')
        print('    Economic system operating within historical normal bounds.')

    # Specific sector risks
    print()
    print('  ── Sector-Level Risk (Latest Quarter) ──')
    sector_scores = best_scores[-N:]
    sector_z = (sector_scores - best_scores[y_panel == 0].mean()) / \
               (best_scores[y_panel == 0].std() + 1e-12)

    # Get sector names
    try:
        snames = SECTOR_NAMES[:N]
    except Exception:
        snames = [f'Sector_{i}' for i in range(N)]

    # Sort by risk (highest first)
    order = np.argsort(-sector_z)
    print(f'    {"Sector":<28} {"Score":>8} {"z":>6} {"Risk":<12}')
    for idx in order[:min(N, 12)]:
        s = sector_scores[idx]
        z = sector_z[idx]
        risk = '🔴 HIGH' if z > 2.0 else ('🟠 ELEVATED' if z > 1.0 else '🟢 LOW')
        name = snames[idx] if idx < len(snames) else f'Sector_{idx}'
        print(f'    {name:<28} {s:8.4f} {z:+6.2f} {risk}')

    return results, scores_q, dates, y_quarter, var_results


# ═════════════════════════════════════════════════════════════════════
#  SUMMARY TABLE
# ═════════════════════════════════════════════════════════════════════

def print_final_summary(ercot_res, econ_res):
    sep('FINAL SUMMARY — All Engines × All Datasets')
    print()
    print(f'  {"Method":<32} {"ERCOT AUC":>10} {"Economy AUC":>12}')
    print(f'  {"-"*32} {"-"*10} {"-"*12}')

    all_keys = sorted(set(list(ercot_res.keys()) + list(econ_res.keys())))
    for k in all_keys:
        e_auc = ercot_res.get(k, {}).get('auc', float('nan'))
        b_auc = econ_res.get(k, {}).get('auc', float('nan'))
        e_str = f'{e_auc:.4f}' if not np.isnan(e_auc) else '—'
        b_str = f'{b_auc:.4f}' if not np.isnan(b_auc) else '—'
        print(f'  {k:<32} {e_str:>10} {b_str:>12}')

    print()
    # Best per dataset
    for name, res in [('ERCOT', ercot_res), ('Economy', econ_res)]:
        valid = {k: v for k, v in res.items() if isinstance(v, dict) and 'auc' in v}
        if valid:
            best = max(valid.items(), key=lambda kv: kv[1]['auc'])
            print(f'  Best on {name}: {best[0]} (AUC={best[1]["auc"]:.4f})')


# ═════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print()
    print('╔' + '═' * 78 + '╗')
    print('║  Full System Benchmark — ReducedTensor + Engines + BSDT + Prediction      ║')
    print('║  Fisher VR weights (zero label leakage) — All methods, All datasets       ║')
    print('╚' + '═' * 78 + '╝')

    # Section 1: ERCOT
    ercot_res, *_ = run_engines_ercot()

    # Section 2: Economy
    try:
        econ_out = run_engines_economy()
        econ_res = econ_out[0]
    except Exception as e:
        print(f'\n  [!] Economy benchmark failed: {e}')
        econ_res = {}

    # Section 3: Fresh prediction
    try:
        pred_out = run_fresh_prediction()
    except Exception as e:
        print(f'\n  [!] Fresh prediction failed: {e}')
        import traceback; traceback.print_exc()

    # Final summary
    print_final_summary(ercot_res, econ_res)

    print()
    print('  Done.')
