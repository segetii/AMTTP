#!/usr/bin/env python
"""
Benchmark: Fisher VR + Betti + Z-score — no heuristic weights.

Implementation contract:
  - ALL view/component weights determined by Fisher Variance Ratio
  - BettiBarcodeSuite integrated as View E in _reference_score
  - Z-score normalization against reference distribution throughout
  - Engines run on RAW X (not on tensor D)

Datasets: ERCOT (energy grid) + G-SIB (banking panel).
"""
import sys, os, time, json, warnings
import numpy as np
from pathlib import Path
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parent.parent.parent  # → amttp
sys.path.insert(0, str(ROOT / 'research' / 'udl'))

from udl.system_mode import (
    MolecularEngine, GravityModeEngine, HybridGravityEngine,
    ReducedTensorDescriptor, BSDTChannels, BettiBarcodeSuite,
    SystemModeEngine,
)

warnings.filterwarnings('ignore')
np.set_printoptions(precision=4, suppress=True)


# ===================================================================
#  DATASET BUILDERS
# ===================================================================
def build_ercot():
    """ERCOT Texas Grid: 241 hours × 65 agents × 5D."""
    T = 241
    hours = np.arange(T)
    cap_pts  = {0:1.0, 48:0.85, 72:0.55, 96:0.35, 120:0.27,
                144:0.30, 168:0.45, 192:0.70, 216:0.90, 240:1.0}
    temp_pts = {0:0.0, 48:0.3, 72:0.6, 96:0.85, 120:1.0,
                144:0.9, 168:0.65, 192:0.35, 216:0.1, 240:0.0}
    dem_pts  = {0:0.70, 48:0.80, 72:0.95, 96:1.15, 120:1.32,
                144:1.25, 168:1.05, 192:0.85, 216:0.72, 240:0.65}
    def interp(pts):
        xx = sorted(pts); return np.interp(hours, xx, [pts[x] for x in xx])
    capacity = interp(cap_pts)
    temperature = interp(temp_pts)
    demand = interp(dem_pts)

    rng = np.random.default_rng(42)
    agents = ['gas']*25 + ['wind']*15 + ['thermal']*10 + ['consumer']*10 + ['gas_supply']*5
    N = len(agents); D = 5
    X_3d = np.zeros((T, N, D))
    mults = {'gas': [1.3,1.0,1.2,1.5,0.8], 'wind': [1.5,0.8,0.3,1.0,1.2],
             'thermal': [1.0,1.2,1.5,1.3,0.7], 'consumer': [0.5,1.5,0.4,0.8,1.0],
             'gas_supply': [0.8,0.6,1.8,1.2,0.5]}
    cap_loss = 1.0 - capacity
    dem_stress = np.maximum(demand - capacity, 0)
    fuel = temperature * 0.5
    cascade = cap_loss * dem_stress
    base = np.column_stack([cap_loss, dem_stress, fuel, cascade, temperature])
    for j, atype in enumerate(agents):
        noise = rng.normal(0, 0.03, (T, D))
        X_3d[:, j, :] = base * np.array(mults[atype]) + noise

    y_hour = ((capacity < 0.50) & (demand > capacity)).astype(int)
    X = X_3d.reshape(T * N, D)
    y = np.repeat(y_hour, N)
    return X, y, T, N


CRISIS_Q = {"2007-12-31","2008-03-31","2008-06-30","2008-09-30",
            "2008-12-31","2009-03-31","2009-06-30",
            "2020-03-31","2020-06-30",
            "2011-09-30","2011-12-31","2012-03-31","2012-06-30"}

def build_bank():
    """G-SIB bank-level panel (cached real or synthetic fallback)."""
    import pandas as pd
    cache = ROOT / 'research' / 'adaptive-friction' / 'banklevel_enhanced' / 'gsib_cache_real'
    npz = cache / 'gsib_real_panel.npz'
    if npz.exists():
        dat = np.load(npz)
        X3 = dat['X']
        T, N, d = X3.shape
        dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:T]
        yq = np.array([1 if str(dt.date()) in CRISIS_Q else 0 for dt in dates])
        return X3.reshape(T*N, d), np.repeat(yq, N), T, N
    # Synthetic fallback
    rng = np.random.default_rng(123)
    T, N, d = 76, 19, 5
    X = rng.normal(0, 1, (T, N, d))
    crisis = list(range(12,19)) + [60,61]
    for q in crisis:
        X[q,:,0] += 2.5; X[q,:,2] += 3.0; X[q,:,3] -= 1.5
    yq = np.zeros(T, dtype=int)
    for q in crisis: yq[q] = 1
    return X.reshape(T*N, d), np.repeat(yq, N), T, N


def safe_auc(y, s):
    if len(np.unique(y)) < 2: return float('nan')
    return roc_auc_score(y, s)


# ===================================================================
#  BENCHMARK
# ===================================================================
def benchmark(name, X, y, T, N):
    print(f'\n{"="*72}')
    print(f'  {name}  (T={T}, N={N}, d={X.shape[1]}, '
          f'samples={len(X)}, crisis={y.mean():.3f})')
    print(f'{"="*72}')

    X_ref = X[y == 0]
    results = {}

    # ── A. Full engines on RAW X (paper methodology) ────────────
    print('\n  [A] Full Engines on Raw X')
    for ename, eng in [
        ('Hybrid',    HybridGravityEngine()),
        ('Gravity',   GravityModeEngine(iterations=60, k_neighbors=10, use_fused=True)),
        ('Molecular', MolecularEngine(iterations=80, k_neighbors=10, use_fused=True)),
    ]:
        t0 = time.perf_counter()
        try:
            scores = eng.fit_score(X, y)
            auc = safe_auc(y, scores)
        except Exception as e:
            auc = float('nan'); scores = np.zeros(len(X))
            print(f'      {ename}: ERROR {e}')
            continue
        dt = time.perf_counter() - t0
        results[f'Engine_{ename}'] = auc
        print(f'      {ename:<12}  AUC={auc:.4f}  ({dt:.1f}s)')

    # ── B. ReducedTensorDescriptor: score() [Fisher VR, z-scored] ──
    print('\n  [B] RTD score() — Fisher VR weighted, z-scored')
    desc = ReducedTensorDescriptor(n_eigs=5, k_neighbors=15)
    desc.fit(X_ref)
    t0 = time.perf_counter()
    s_desc = desc.score(X)
    dt = time.perf_counter() - t0
    auc_desc = safe_auc(y, s_desc)
    results['RTD_score'] = auc_desc
    print(f'      RTD.score()       AUC={auc_desc:.4f}  ({dt:.1f}s)')

    # ── C. ReducedTensorDescriptor: fit_score() [_reference_score with Betti] ──
    print('\n  [C] RTD fit_score() — Fisher VR + Betti + BSDT + z-score')
    desc2 = ReducedTensorDescriptor(n_eigs=5, k_neighbors=15)
    t0 = time.perf_counter()
    s_fitscore = desc2.fit_score(X, y)
    dt = time.perf_counter() - t0
    auc_fs = safe_auc(y, s_fitscore)
    results['RTD_fit_score'] = auc_fs
    print(f'      RTD.fit_score()   AUC={auc_fs:.4f}  ({dt:.1f}s)')

    # ── D. BSDT Variants (Fisher VR, closed-form) ──
    print('\n  [D] BSDT Scoring Variants (Fisher VR)')
    desc3 = ReducedTensorDescriptor(n_eigs=5, k_neighbors=15)
    desc3.fit(X_ref)
    variants = desc3.score_variants(X, y, X_ref)
    for vname, vd in variants.items():
        auc_v = vd['auroc']
        results[f'BSDT_{vname}'] = auc_v
        fw_str = ''
        if 'fisher_weights' in vd:
            fw_str = f'  FW={np.array(vd["fisher_weights"])}'
        print(f'      {vname:<14}  AUC={auc_v:.4f}{fw_str}')

    # ── E. Betti Barcode Suite standalone ──
    print('\n  [E] BettiBarcodeSuite standalone')
    betti = BettiBarcodeSuite(k=20)
    betti.fit(X_ref)
    t0 = time.perf_counter()
    s_betti = betti.score(X)
    dt = time.perf_counter() - t0
    auc_betti = safe_auc(y, s_betti)
    results['Betti_standalone'] = auc_betti
    print(f'      Betti             AUC={auc_betti:.4f}  ({dt:.1f}s)')

    # ── F. SystemModeEngine (Hybrid + spectra filter) ──
    print('\n  [F] SystemModeEngine (Hybrid, spectra filter)')
    sme = SystemModeEngine(mode='hybrid', filter_spectra=True)
    t0 = time.perf_counter()
    try:
        s_sme = sme.fit_score(X, y)
        auc_sme = safe_auc(y, s_sme)
    except Exception as e:
        auc_sme = float('nan')
        print(f'      ERROR: {e}')
    dt = time.perf_counter() - t0
    results['SME_Hybrid'] = auc_sme
    print(f'      SME Hybrid        AUC={auc_sme:.4f}  ({dt:.1f}s)')

    # ── G. Fisher VR view weights diagnostics ──
    print('\n  [G] Fisher VR View Weight Diagnostics')
    desc4 = ReducedTensorDescriptor(n_eigs=5, k_neighbors=15)
    desc4.fit(X_ref)
    # Reproduce the view computation to report weights
    D_all = desc4.transform(X)
    D_ref_t = desc4.transform(X_ref)
    n_eigs = min(desc4.n_eigs, X.shape[1])

    def robust_norm(x):
        q1, q99 = np.percentile(x, [1, 99])
        xn = (x - q1) / (q99 - q1 + 1e-15)
        return np.clip(xn, 0.0, 1.0)

    def zpos(vals, ref_col):
        mu = ref_col.mean(); sigma = ref_col.std() + 1e-10
        return np.maximum((vals - mu) / sigma, 0.0)

    # View A: Raw kNN z-score
    from sklearn.neighbors import NearestNeighbors
    k_raw = min(10, len(X_ref) - 1)
    nn_raw = NearestNeighbors(n_neighbors=k_raw, algorithm='auto')
    nn_raw.fit(X_ref.astype(np.float32))
    dr, _ = nn_raw.kneighbors(X.astype(np.float32))
    raw_mean = dr.mean(axis=1)
    dr_ref, _ = nn_raw.kneighbors(X_ref.astype(np.float32))
    z_raw = np.maximum((raw_mean - dr_ref.mean(axis=1).mean()) /
                       (dr_ref.mean(axis=1).std() + 1e-10), 0.0)
    v_raw = robust_norm(z_raw)

    # View B: Descriptor kNN z-score
    nn_d = NearestNeighbors(n_neighbors=min(10, len(D_ref_t)-1), algorithm='auto')
    nn_d.fit(D_ref_t.astype(np.float32))
    dd, _ = nn_d.kneighbors(D_all.astype(np.float32))
    knn_mean = dd.mean(axis=1)
    dd_ref, _ = nn_d.kneighbors(D_ref_t.astype(np.float32))
    z_knn = np.maximum((knn_mean - dd_ref.mean(axis=1).mean()) /
                       (dd_ref.mean(axis=1).std() + 1e-10), 0.0)
    v_knn = robust_norm(z_knn)

    # View C: Descriptor-native z-scores
    z_grad  = zpos(D_all[:, 0], D_ref_t[:, 0])
    z_maha  = zpos(D_all[:, n_eigs+1], D_ref_t[:, n_eigs+1])
    z_med   = zpos(D_all[:, n_eigs+2], D_ref_t[:, n_eigs+2])
    z_trace = zpos(np.abs(D_all[:, n_eigs+3]), np.abs(D_ref_t[:, n_eigs+3]))
    z_morse = zpos(D_all[:, n_eigs+5].astype(float), D_ref_t[:, n_eigs+5].astype(float))
    z_stack = np.column_stack([z_grad, z_maha, z_med, z_trace, z_morse])
    v_desc = robust_norm(z_stack.mean(axis=1))

    # View D: BSDT
    bsdt = BSDTChannels(k=min(10, max(2, len(X_ref)-1)))
    bsdt.fit(X_ref)
    v_bsdt = robust_norm(bsdt.score(X))

    # View E: Betti
    betti2 = BettiBarcodeSuite(k=min(20, 25))
    betti2.fit(X_ref)
    v_betti = robust_norm(betti2.score(X))

    # Fisher VR
    views = np.column_stack([v_raw, v_knn, v_desc, v_bsdt, v_betti])
    total_sig = views.sum(axis=1)
    p80 = np.percentile(total_sig, 80)
    p50 = np.percentile(total_sig, 50)
    hi = total_sig >= p80; lo = total_sig <= p50
    n_v = views.shape[1]
    view_names = ['Raw_kNN', 'Desc_kNN', 'Topology', 'BSDT', 'Betti']

    if hi.sum() >= 2 and lo.sum() >= 2:
        fr = np.zeros(n_v)
        for v in range(n_v):
            mu_h = views[hi, v].mean(); mu_l = views[lo, v].mean()
            var_h = views[hi, v].var();  var_l = views[lo, v].var()
            fr[v] = (mu_h - mu_l)**2 / max(var_h + var_l, 1e-10)
        w = fr / fr.sum() if fr.sum() > 1e-10 else np.ones(n_v) / n_v
    else:
        w = np.ones(n_v) / n_v
        fr = np.ones(n_v) / n_v

    for i, vn in enumerate(view_names):
        auc_v = safe_auc(y, views[:, i])
        print(f'      {vn:<10}  FR={fr[i]:.4f}  w={w[i]:.4f}  solo_AUC={auc_v:.4f}')

    fused = (views * w).sum(axis=1)
    auc_fused = safe_auc(y, fused)
    results['FisherVR_fused'] = auc_fused
    print(f'      Fisher-fused      AUC={auc_fused:.4f}')

    return results


# ===================================================================
#  MAIN
# ===================================================================
if __name__ == '__main__':
    print('='*72)
    print('  Fisher VR + Betti + Z-score Benchmark')
    print('  (data determines ALL weights — zero heuristics)')
    print('='*72)

    all_results = {}

    # ERCOT
    X_e, y_e, T_e, N_e = build_ercot()
    all_results['ERCOT'] = benchmark('ERCOT Texas Grid', X_e, y_e, T_e, N_e)

    # G-SIB
    X_b, y_b, T_b, N_b = build_bank()
    all_results['Bank'] = benchmark('G-SIB Bank-Level', X_b, y_b, T_b, N_b)

    # ── Summary ──
    print('\n' + '='*72)
    print('  FINAL SUMMARY')
    print('='*72)
    print(f'  {"Dataset":<10} {"Method":<20} {"AUC":>8}')
    print(f'  {"-"*10} {"-"*20} {"-"*8}')
    for ds, res in all_results.items():
        for method, auc in res.items():
            auc_s = f'{auc:.4f}' if not np.isnan(auc) else '  N/A'
            print(f'  {ds:<10} {method:<20} {auc_s:>8}')

    # Save
    out = Path(__file__).parent / 'bench_fisher_betti_results.json'
    flat = {}
    for ds, res in all_results.items():
        for m, a in res.items():
            flat[f'{ds}_{m}'] = None if (isinstance(a, float) and np.isnan(a)) else a
    with open(out, 'w') as f:
        json.dump(flat, f, indent=2)
    print(f'\n  Results saved to {out}')
