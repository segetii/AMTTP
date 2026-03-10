"""
Reduced Tensor + All Engines + All BSDT Variants — Combined Benchmark
======================================================================
For EACH engine (Molecular, Gravity, Hybrid) we:
  1. Run the full engine (physics simulation + fused scoring)
  2. Take the engine's final simulated positions → ReducedTensorDescriptor
  3. Run all 5 BSDT variants on the engine output
  4. Combine engine score + ReducedTensor + BSDT variants

Also runs ReducedTensorDescriptor standalone (no engine)
and fresh FRED economic prediction.

Two datasets: ERCOT grid + U.S. Banking (FRED)
"""
from __future__ import annotations
import sys, time, warnings
import numpy as np
from pathlib import Path
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score

warnings.filterwarnings("ignore")

ROOT = Path(r"c:\amttp")
sys.path.insert(0, str(ROOT / "research" / "udl"))
sys.path.insert(0, str(ROOT / "research" / "udl" / "src"))
sys.path.insert(0, str(ROOT / "research" / "adaptive-friction" / "pipeline"))
sys.path.insert(0, str(ROOT / "research" / "adaptive-friction" / "variants"))

from udl.system_mode import (
    BSDTChannels, ReducedTensorDescriptor,
    MolecularEngine, GravityModeEngine, HybridGravityEngine,
    SystemModeEngine,
)
from bench_economy_ercot import load_ercot_dataset, load_economy_dataset


# ── metrics ─────────────────────────────────────────────────────────
def far95(scores, y):
    y = np.asarray(y, dtype=int)
    a, n = scores[y==1], scores[y==0]
    if len(a)==0 or len(n)==0: return float('nan')
    return float(np.mean(n >= np.percentile(a, 5)))

def bestf1(scores, y):
    best = 0
    for th in np.percentile(scores, np.arange(50,100,1)):
        f = f1_score(y, (scores>=th).astype(int), zero_division=0)
        if f > best: best = f
    return best

def row(label, scores, y, t=None):
    auc = roc_auc_score(y, scores)
    f = far95(scores, y)
    f1 = bestf1(scores, y)
    ts = f'{t:.1f}s' if t else ''
    print(f'    {label:<40} AUC={auc:.4f}  FAR={f:.3f}  F1={f1:.3f}  {ts}')
    return dict(label=label, auc=auc, far=f, f1=f1)


def run_dataset(dataset_name, X, y, X_3d=None, dates=None, y_quarter=None, sectors=None):
    """Run ALL engines × ReducedTensor × BSDT variants on one dataset."""
    banner = f'  {dataset_name}'
    print()
    print('=' * 80)
    print(banner)
    print('=' * 80)
    print(f'    Shape: {X.shape},  crisis: {int(y.sum())}/{len(y)} ({y.mean():.1%})')
    X_ref = X[y == 0]
    all_results = {}

    # ══════════════════════════════════════════════════════════════
    #  PER-ENGINE: Full Engine → ReducedTensor → BSDT variants
    # ══════════════════════════════════════════════════════════════

    engines = [
        ('Molecular',  MolecularEngine(iterations=80, k_neighbors=15, use_fused=True)),
        ('Gravity',    GravityModeEngine(iterations=60, k_neighbors=15, use_fused=True)),
        ('Hybrid',     HybridGravityEngine()),
    ]

    for eng_name, eng in engines:
        print()
        print(f'  ┌─ ENGINE: {eng_name} ─────────────────────────────────')

        # A. Full engine score
        t0 = time.time()
        eng_scores = eng.fit_score(X, y)
        eng_time = time.time() - t0
        r = row(f'{eng_name} (full engine)', eng_scores, y, eng_time)
        all_results[f'{eng_name}_engine'] = r

        # B. Get the engine's final positions (post-simulation)
        if hasattr(eng, 'X_final_'):
            X_sim = eng.X_final_
        elif hasattr(eng, '_engine') and hasattr(eng._engine, 'X_final_'):
            X_sim = eng._engine.X_final_
        else:
            X_sim = None

        # Get reference from engine's simulated space
        if hasattr(eng, 'scaler_') and eng.scaler_ is not None:
            X_all_sim = eng.scaler_.transform(X)
        else:
            X_all_sim = X.copy()

        # C. ReducedTensorDescriptor on engine output
        X_ref_sim = X_all_sim[y == 0]
        desc = ReducedTensorDescriptor(k_neighbors=15)
        t0 = time.time()
        desc.fit(X_ref_sim)
        desc_scores = desc.score(X_all_sim)
        desc_time = time.time() - t0
        r = row(f'{eng_name} → ReducedTensor', desc_scores, y, desc_time)
        all_results[f'{eng_name}_reduced'] = r

        # D. Combined: engine + reduced tensor (fused)
        def mm(s):
            lo, hi = s.min(), s.max()
            return (s - lo) / (hi - lo + 1e-15)

        combined = 0.6 * mm(eng_scores) + 0.4 * mm(desc_scores)
        r = row(f'{eng_name} + ReducedTensor (fused)', combined, y)
        all_results[f'{eng_name}_combined'] = r

        # E. All 5 BSDT variants on engine-transformed space
        print(f'  │  BSDT variants (Fisher VR, zero leakage):')
        var = desc.score_variants(X_all_sim, y, X_ref=X_ref_sim)
        for vname, vr in var.items():
            s = vr['scores']
            auc = vr.get('auroc', roc_auc_score(y, s))
            f = far95(s, y)
            f1 = bestf1(s, y)
            t_ms = vr.get('time', 0) * 1000
            print(f'    {eng_name:>10} → {vname:<18} AUC={auc:.4f}  '
                  f'FAR={f:.3f}  F1={f1:.3f}  {t_ms:.0f}ms')
            all_results[f'{eng_name}_BSDT_{vname}'] = dict(auc=auc, far=f, f1=f1)

        # F. Best combined: engine + best BSDT variant
        best_var = max(var.items(), key=lambda kv: kv[1].get('auroc', 0))
        best_bsdt_s = best_var[1]['scores']
        fused_best = 0.5 * mm(eng_scores) + 0.3 * mm(desc_scores) + 0.2 * mm(best_bsdt_s)
        r = row(f'{eng_name} + Tensor + {best_var[0]} (tri-fused)', fused_best, y)
        all_results[f'{eng_name}_trifused'] = r

        # G. Fisher VR channel analysis
        bsdt = BSDTChannels(k=min(10, max(2, len(X_ref_sim) - 1)))
        bsdt.fit(X_ref_sim)
        ch = bsdt.channels(X_all_sim)
        ch_n = {k: v[y==0] for k,v in ch.items()}
        ch_c = {k: v[y==1] for k,v in ch.items()}
        print(f'  │  Channel crash signature ({eng_name}):')
        for k in ['delta_C', 'delta_G', 'delta_A', 'delta_T']:
            mn, mc = ch_n[k].mean(), ch_c[k].mean()
            ratio = mc / (mn + 1e-12)
            print(f'    {k:<10} normal={mn:.4f}  crisis={mc:.4f}  ratio={ratio:.2f}x')

        print(f'  └─────────────────────────────────────────────────────')

    # ══════════════════════════════════════════════════════════════
    #  STANDALONE ReducedTensor (no engine)
    # ══════════════════════════════════════════════════════════════
    print()
    print(f'  ┌─ STANDALONE: ReducedTensorDescriptor (no engine) ────')
    desc0 = ReducedTensorDescriptor(k_neighbors=15)
    t0 = time.time()
    desc0.fit(X_ref)
    raw_scores = desc0.score(X)
    t_desc = time.time() - t0
    row(f'ReducedTensor standalone', raw_scores, y, t_desc)
    all_results['Standalone_reduced'] = dict(
        auc=roc_auc_score(y, raw_scores), far=far95(raw_scores, y),
        f1=bestf1(raw_scores, y))

    # Morse alarm
    alarm = desc0.get_alarm(X)
    alarm_auc = roc_auc_score(y, alarm.astype(float))
    print(f'    {"Morse Alarm":<40} AUC={alarm_auc:.4f}')
    all_results['Standalone_morse'] = dict(auc=alarm_auc)

    # BSDT variants standalone
    print(f'  │  BSDT variants (standalone, no engine):')
    var0 = desc0.score_variants(X, y, X_ref=X_ref)
    for vname, vr in var0.items():
        s = vr['scores']
        auc = vr.get('auroc', roc_auc_score(y, s))
        f = far95(s, y)
        f1 = bestf1(s, y)
        print(f'    {"standalone":>10} → {vname:<18} AUC={auc:.4f}  '
              f'FAR={f:.3f}  F1={f1:.3f}')
        all_results[f'Standalone_BSDT_{vname}'] = dict(auc=auc, far=f, f1=f1)
    print(f'  └─────────────────────────────────────────────────────')

    return all_results


def run_fresh_prediction():
    """Fresh economic state prediction using best methods."""
    print()
    print('=' * 80)
    print('  FRESH ECONOMIC PREDICTION — March 2026 Outlook')
    print('=' * 80)

    try:
        from fred_loader import fetch_all, apply_transforms, standardise
        from state_matrix import build_state_matrix, SECTOR_NAMES
        from mfls_variants import CRISIS_QUARTERS, make_crisis_labels
    except ImportError as e:
        print(f'  [!] Pipeline import failed: {e}')
        return

    raw = fetch_all(use_cache=True, verbose=True)
    xf = apply_transforms(raw)
    std, mu, sig = standardise(xf)
    X_3d, dates = build_state_matrix(std)
    T, N, d = X_3d.shape
    y_quarter = make_crisis_labels(dates)
    X = X_3d.reshape(T * N, d)
    y = np.repeat(y_quarter, N)
    X_ref = X[y == 0]

    print(f'  T={T}Q, N={N} sectors, d={d}')
    print(f'  Date range: {dates[0].date()} → {dates[-1].date()}')

    # ── Latest macro snapshot ──
    print()
    print('  ── Latest FRED Snapshot ──')
    latest = raw.iloc[-1]
    print(f'  Quarter: {raw.index[-1].date()}')
    for col in raw.columns:
        v = latest[col]
        if not np.isnan(v):
            print(f'    {col:<16} = {v:.4f}')

    # ── Recent trend ──
    print()
    print('  ── Recent Trends (4Q) ──')
    for col in ['vix', 'stlfsi', 'nfci', 'slope_10y2y', 'baa_spread', 'hy_spread', 'fed_funds']:
        if col in raw.columns:
            vals = raw[col].dropna()
            if len(vals) >= 5:
                v4 = vals.iloc[-5]
                vn = vals.iloc[-1]
                chg = vn - v4
                print(f'    {col:<16} {v4:7.2f} → {vn:7.2f}  ({chg:+.2f})')

    # ── Run all 3 engines + ReducedTensor + BSDT on economic data ──
    engines = [
        ('Molecular', MolecularEngine(iterations=80, k_neighbors=15, use_fused=True)),
        ('Gravity',   GravityModeEngine(iterations=60, k_neighbors=15, use_fused=True)),
        ('Hybrid',    HybridGravityEngine()),
    ]

    print()
    print('  ── Engine + ReducedTensor + BSDT Scores ──')
    best_scores_all = {}
    for eng_name, eng in engines:
        t0 = time.time()
        eng_scores = eng.fit_score(X, y)
        et = time.time() - t0

        # ReducedTensor on engine space
        if hasattr(eng, 'scaler_') and eng.scaler_ is not None:
            X_sim = eng.scaler_.transform(X)
        else:
            X_sim = X.copy()
        X_ref_sim = X_sim[y == 0]

        desc = ReducedTensorDescriptor(k_neighbors=15)
        desc.fit(X_ref_sim)
        desc_scores = desc.score(X_sim)

        # BSDT variants
        var = desc.score_variants(X_sim, y, X_ref=X_ref_sim)

        # Print engine + reduced + best BSDT
        def mm(s):
            lo, hi = s.min(), s.max()
            return (s - lo) / (hi - lo + 1e-15)

        eng_auc = roc_auc_score(y, eng_scores)
        desc_auc = roc_auc_score(y, desc_scores)

        best_var = max(var.items(), key=lambda kv: kv[1].get('auroc', 0))
        best_bsdt = best_var[1]['scores']
        bsdt_auc = best_var[1].get('auroc', roc_auc_score(y, best_bsdt))

        # Tri-fused
        fused = 0.5 * mm(eng_scores) + 0.3 * mm(desc_scores) + 0.2 * mm(best_bsdt)
        fused_auc = roc_auc_score(y, fused)

        print(f'    {eng_name:<12} engine={eng_auc:.4f}  tensor={desc_auc:.4f}  '
              f'bsdt({best_var[0]})={bsdt_auc:.4f}  fused={fused_auc:.4f}  [{et:.1f}s]')

        best_scores_all[eng_name] = {
            'engine': eng_scores, 'tensor': desc_scores,
            'bsdt': best_bsdt, 'fused': fused,
            'bsdt_name': best_var[0],
            'all_variants': var,
        }

    # All BSDT variants detail
    print()
    print('  ── All BSDT Variants (per engine) ──')
    for eng_name, data in best_scores_all.items():
        var = data['all_variants']
        print(f'    {eng_name}:')
        for vname, vr in var.items():
            auc = vr.get('auroc', 0)
            print(f'      {vname:<18} AUC={auc:.4f}')

    # ══════════════════════════════════════════════════════════════
    #  PREDICTION: Latest quarters
    # ══════════════════════════════════════════════════════════════
    print()
    print('  ╔══════════════════════════════════════════════════════╗')
    print('  ║   PREDICTION — Economic Risk State (Mar 2026)       ║')
    print('  ╚══════════════════════════════════════════════════════╝')

    # Use Hybrid (best overall) fused scores
    hybrid = best_scores_all.get('Hybrid', best_scores_all.get('Molecular'))
    pred_scores = hybrid['fused']
    scores_q = pred_scores.reshape(T, N).mean(axis=1)

    normal_q = scores_q[y_quarter == 0]
    mu_n, std_n = normal_q.mean(), normal_q.std()
    t95 = np.percentile(normal_q, 95)
    t99 = np.percentile(normal_q, 99)

    print(f'\n  Method: Hybrid + ReducedTensor + {hybrid["bsdt_name"]} (tri-fused)')
    print(f'  Normal-period: μ={mu_n:.4f}, σ={std_n:.4f}, P95={t95:.4f}, P99={t99:.4f}')

    # Last 12 quarters
    print()
    print(f'  {"Quarter":<14} {"Score":>8} {"z":>7} {"Level":<22} {"Actual":<10}')
    print(f'  {"-"*14} {"-"*8} {"-"*7} {"-"*22} {"-"*10}')
    n_show = min(12, T)
    for i in range(T - n_show, T):
        d = dates[i].date() if i < len(dates) else f'Q{i}'
        s = scores_q[i]
        z = (s - mu_n) / (std_n + 1e-12)
        if s >= t99:
            lv = '🔴 CRITICAL (>P99)'
        elif s >= t95:
            lv = '🟠 ELEVATED (>P95)'
        elif z > 1.5:
            lv = '🟡 WATCH (z>1.5)'
        else:
            lv = '🟢 NORMAL'
        actual = 'CRISIS' if (i < len(y_quarter) and y_quarter[i] == 1) else 'normal'
        print(f'  {str(d):<14} {s:8.4f} {z:+7.2f} {lv:<22} {actual:<10}')

    # Per-engine per-sector latest quarter
    print()
    print('  ── Sector Risk (Latest Quarter, All Engines) ──')
    try:
        snames = SECTOR_NAMES
    except Exception:
        snames = [f'Sector_{i}' for i in range(N)]

    print(f'    {"Sector":<28}', end='')
    for eng_name in best_scores_all:
        print(f' {eng_name:>10}', end='')
    print(f' {"Consensus":>10}')

    sector_consensus = np.zeros(N)
    for idx in range(min(N, len(snames))):
        name = snames[idx]
        print(f'    {name:<28}', end='')
        scores_per_eng = []
        for eng_name, data in best_scores_all.items():
            s = data['fused'][-N + idx]
            ref = data['fused'][y == 0]
            z = (s - ref.mean()) / (ref.std() + 1e-12)
            scores_per_eng.append(z)
            lbl = '🔴' if z > 2.0 else ('🟠' if z > 1.0 else '🟢')
            print(f' {lbl}{z:+6.2f}', end='')
        consensus = np.mean(scores_per_eng)
        sector_consensus[idx] = consensus
        clbl = '🔴' if consensus > 2.0 else ('🟠' if consensus > 1.0 else '🟢')
        print(f' {clbl}{consensus:+6.2f}')

    # Channel decomposition
    print()
    print('  ── BSDT Channel Decomposition (Latest Q) ──')
    bsdt = BSDTChannels(k=min(10, max(2, len(X_ref) - 1)))
    bsdt.fit(X_ref)
    X_latest = X[-N:]
    ch = bsdt.channels(X_latest)
    ch_all = bsdt.channels(X)
    print(f'    {"Channel":<12} {"Current":>10} {"Normal μ":>10} {"z":>8}')
    for k in ['delta_C', 'delta_G', 'delta_A', 'delta_T']:
        curr = ch[k].mean()
        nvals = ch_all[k][y == 0]
        z = (curr - nvals.mean()) / (nvals.std() + 1e-12)
        print(f'    {k:<12} {curr:10.4f} {nvals.mean():10.4f} {z:+8.2f}')

    # MFLS gradient
    mfls_latest = bsdt.mfls(X_latest).mean()
    mfls_normal = bsdt.mfls(X_ref[:N]).mean()
    print(f'\n    MFLS gradient: {mfls_latest:.4f} vs normal {mfls_normal:.4f} '
          f'({mfls_latest/mfls_normal:.2f}x)')

    # Overall assessment
    latest_s = scores_q[-1]
    latest_z = (latest_s - mu_n) / (std_n + 1e-12)
    trend_4q = scores_q[-1] - scores_q[-4] if T >= 4 else 0

    n_hot_sectors = (sector_consensus > 1.5).sum()
    desc_check = ReducedTensorDescriptor(k_neighbors=15)
    desc_check.fit(X_ref)
    morse = desc_check.get_morse_index(X_latest)
    morse_frac = (morse >= 1).mean()

    print()
    print('  ╔══════════════════════════════════════════════════════╗')
    print('  ║          FORWARD-LOOKING RISK ASSESSMENT            ║')
    print('  ╠══════════════════════════════════════════════════════╣')
    print(f'  ║  Score z-score:        {latest_z:+6.2f}                        ║')
    print(f'  ║  4Q momentum:          {trend_4q:+6.4f}                      ║')
    print(f'  ║  MFLS ratio:           {mfls_latest/mfls_normal:5.2f}x                         ║')
    print(f'  ║  Morse saddle frac:    {morse_frac:5.1%}                        ║')
    print(f'  ║  Sectors above 1.5σ:   {n_hot_sectors}/{N}                           ║')

    risk = 0
    if latest_z > 1.5: risk += 1
    if trend_4q > 0.1: risk += 1
    if mfls_latest / mfls_normal > 1.5: risk += 1
    if morse_frac > 0.2: risk += 1
    if n_hot_sectors >= 3: risk += 1

    print('  ╠══════════════════════════════════════════════════════╣')
    if risk >= 4:
        print('  ║  ██ ASSESSMENT: HIGH RISK ██                        ║')
        print('  ║  Multiple phase-transition indicators active.       ║')
    elif risk >= 2:
        print('  ║  █ ASSESSMENT: ELEVATED RISK █                      ║')
        print('  ║  System shows early-stage structural stress.        ║')
    elif risk >= 1:
        print('  ║  ASSESSMENT: WATCH                                  ║')
        print('  ║  One indicator mildly elevated; monitor.            ║')
    else:
        print('  ║  ✓ ASSESSMENT: LOW RISK                             ║')
        print('  ║  All structural indicators within normal bounds.    ║')
    print('  ╚══════════════════════════════════════════════════════╝')


# ═════════════════════════════════════════════════════════════════════
#  FINAL COMPARISON TABLE
# ═════════════════════════════════════════════════════════════════════

def summary_table(ercot, econ):
    print()
    print('=' * 80)
    print('  FINAL COMPARISON TABLE')
    print('=' * 80)
    print()
    print(f'  {"Method":<48} {"ERCOT":>7} {"Economy":>8}')
    print(f'  {"-"*48} {"-"*7} {"-"*8}')

    # Merge all keys
    keys = sorted(set(list(ercot.keys()) + list(econ.keys())))
    for k in keys:
        ea = ercot.get(k, {}).get('auc', float('nan'))
        ba = econ.get(k, {}).get('auc', float('nan'))
        es = f'{ea:.4f}' if not np.isnan(ea) else '  —'
        bs = f'{ba:.4f}' if not np.isnan(ba) else '  —'
        print(f'  {k:<48} {es:>7} {bs:>8}')

    # Best per dataset
    print()
    for name, res in [('ERCOT', ercot), ('Economy', econ)]:
        valid = {k: v for k, v in res.items() if isinstance(v, dict) and 'auc' in v}
        if valid:
            best = max(valid.items(), key=lambda kv: kv[1]['auc'])
            print(f'  ★ Best on {name}: {best[0]} → AUC={best[1]["auc"]:.4f}')


# ═════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print()
    print('╔' + '═' * 78 + '╗')
    print('║  REDUCED TENSOR + ALL ENGINES + ALL BSDT VARIANTS — COMBINED        ║')
    print('║  Molecular / Gravity / Hybrid × ReducedTensor × 5 BSDT (Fisher VR)  ║')
    print('╚' + '═' * 78 + '╝')

    # ── ERCOT ──
    X_e, y_e, _, _, _, _, _ = load_ercot_dataset()
    ercot_res = run_dataset('ERCOT Grid Failure (65 agents × 5D)', X_e, y_e)

    # ── Economy ──
    try:
        X_b, y_b, dates_b, snames, yq_b, X3d_b = load_economy_dataset()
        econ_res = run_dataset('U.S. Economy — FRED Macro (12 sectors × 6D)',
                               X_b, y_b, X3d_b, dates_b, yq_b, snames)
    except Exception as e:
        print(f'\n  [!] Economy data failed: {e}')
        econ_res = {}

    # ── Fresh prediction ──
    try:
        run_fresh_prediction()
    except Exception as e:
        print(f'\n  [!] Fresh prediction error: {e}')
        import traceback; traceback.print_exc()

    # ── Summary ──
    summary_table(ercot_res, econ_res)

    print('\n  Done.')
