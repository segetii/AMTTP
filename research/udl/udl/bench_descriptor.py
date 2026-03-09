#!/usr/bin/env python
"""Benchmark ReducedTensorDescriptor vs full engines on ERCOT + Bank-level data.

Checks for:
  1.  AUC parity  — descriptor should not lose >0.05 AUC vs full engines
  2.  Morse index non-degeneracy — at least some points should have index > 0
  3.  Fresh-prediction consistency — re-fitting on same data gives same scores
"""
import sys, os, json, time, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import roc_auc_score

# ── project root for imports ──────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent.parent  # udl/udl → amttp

sys.path.insert(0, str(ROOT / 'research' / 'udl'))
from udl.system_mode import (
    MolecularEngine, GravityModeEngine, HybridGravityEngine,
    ReducedTensorDescriptor,
)

warnings.filterwarnings('ignore', category=FutureWarning)


# ═══════════════════════════════════════════════════════════════════
#  DATASET 1:   ERCOT Texas Grid   (synthetic, 240 hours × 65 agents)
# ═══════════════════════════════════════════════════════════════════
def build_ercot_data():
    """Reproduce the hardcoded ERCOT scenario from bench_economy_ercot."""
    T = 241
    hours = np.arange(T)

    # ── hourly curves (piecewise-linear) ──
    cap_pts  = {0: 1.0, 48: 0.85, 72: 0.55, 96: 0.35,
                120: 0.27, 144: 0.30, 168: 0.45, 192: 0.70,
                216: 0.90, 240: 1.0}
    temp_pts = {0: 0.0, 48: 0.3, 72: 0.6, 96: 0.85,
                120: 1.0, 144: 0.9, 168: 0.65, 192: 0.35,
                216: 0.1, 240: 0.0}
    dem_pts  = {0: 0.70, 48: 0.80, 72: 0.95, 96: 1.15,
                120: 1.32, 144: 1.25, 168: 1.05, 192: 0.85,
                216: 0.72, 240: 0.65}

    def interp(pts):
        xx = sorted(pts); return np.interp(hours, xx, [pts[x] for x in xx])

    capacity = interp(cap_pts)
    temperature = interp(temp_pts)
    demand = interp(dem_pts)

    rng = np.random.default_rng(42)

    # ── 65 agents ──
    agents = (['gas'] * 25 + ['wind'] * 15 + ['thermal'] * 10 +
              ['consumer'] * 10 + ['gas_supply'] * 5)
    N = len(agents)
    D = 5  # capacity_loss, demand_stress, fuel_supply, cascade, temp

    X_3d = np.zeros((T, N, D))
    for j, atype in enumerate(agents):
        noise = rng.normal(0, 0.03, (T, D))
        cap_loss = 1.0 - capacity
        dem_stress = np.maximum(demand - capacity, 0)
        fuel = temperature * 0.5
        cascade = cap_loss * dem_stress
        temp_f = temperature

        if atype == 'gas':
            mult = np.array([1.3, 1.0, 1.2, 1.5, 0.8])
        elif atype == 'wind':
            mult = np.array([1.5, 0.8, 0.3, 1.0, 1.2])
        elif atype == 'thermal':
            mult = np.array([1.0, 1.2, 1.5, 1.3, 0.7])
        elif atype == 'consumer':
            mult = np.array([0.5, 1.5, 0.4, 0.8, 1.0])
        else:  # gas_supply
            mult = np.array([0.8, 0.6, 1.8, 1.2, 0.5])

        base = np.column_stack([cap_loss, dem_stress, fuel, cascade, temp_f])
        X_3d[:, j, :] = base * mult + noise

    # Crisis labels: low capacity AND demand > capacity
    y_hour = ((capacity < 0.50) & (demand > capacity)).astype(int)

    X_panel = X_3d.reshape(T * N, D)
    y_panel = np.repeat(y_hour, N)
    return X_panel, y_panel, T, N


# ═══════════════════════════════════════════════════════════════════
#  DATASET 2:   Bank-level G-SIB  (cached real data)
# ═══════════════════════════════════════════════════════════════════
CRISIS_QUARTERS = {
    "2007-12-31", "2008-03-31", "2008-06-30", "2008-09-30",
    "2008-12-31", "2009-03-31", "2009-06-30",
    "2020-03-31", "2020-06-30",
    "2011-09-30", "2011-12-31", "2012-03-31", "2012-06-30",
}


def build_bank_data():
    """Load real G-SIB panel from cached npz."""
    cache = ROOT / 'research' / 'adaptive-friction' / 'banklevel_enhanced' / 'gsib_cache_real'
    npz_path = cache / 'gsib_real_panel.npz'
    if not npz_path.exists():
        print(f'[WARN] Bank-level cache not found at {npz_path}, generating synthetic.')
        return build_synthetic_bank_data()

    dat = np.load(npz_path)
    X = dat['X']  # (T, N, d)
    T_data, N_banks, d = X.shape
    dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:T_data]

    y_quarter = np.array([1 if str(dt.date()) in CRISIS_QUARTERS else 0
                          for dt in dates])

    X_panel = X.reshape(T_data * N_banks, d)
    y_panel = np.repeat(y_quarter, N_banks)
    return X_panel, y_panel, T_data, N_banks


def build_synthetic_bank_data():
    """Fallback: synthetic bank-like data with embedded crisis."""
    rng = np.random.default_rng(123)
    T, N, d = 76, 19, 5  # ~19 years × 4 quarters, 19 banks, 5 features
    X_normal = rng.normal(0, 1, (T, N, d))

    # Inject crisis signal in quarters 12-18 (GFC-like) and 60-61 (COVID-like)
    crisis_q = list(range(12, 19)) + [60, 61]
    for q in crisis_q:
        X_normal[q, :, 0] += 2.5  # loan-to-asset spike
        X_normal[q, :, 2] += 3.0  # NPL spike
        X_normal[q, :, 3] -= 1.5  # ROA drop

    y_quarter = np.zeros(T, dtype=int)
    for q in crisis_q:
        y_quarter[q] = 1

    X_panel = X_normal.reshape(T * N, d)
    y_panel = np.repeat(y_quarter, N)
    return X_panel, y_panel, T, N


# ═══════════════════════════════════════════════════════════════════
#  BENCHMARK RUNNER
# ═══════════════════════════════════════════════════════════════════
def safe_auc(y, s):
    if len(np.unique(y)) < 2:
        return float('nan')
    return roc_auc_score(y, s)


def run_engine(name, engine, X, y, T, N):
    """Fit a full engine via fit_score and return AUC + timing."""
    t0 = time.perf_counter()
    try:
        scores = engine.fit_score(X, y)
    except Exception as e:
        return {'name': name, 'auc': float('nan'), 'time': 0, 'error': str(e)}
    dt = time.perf_counter() - t0
    auc = safe_auc(y, scores)
    return {'name': name, 'auc': auc, 'time': dt, 'error': None}


def run_descriptor(name, X_train, X_test, y_test, T, N):
    """Fit ReducedTensorDescriptor and return AUC + Morse stats."""
    desc = ReducedTensorDescriptor(n_eigs=5, k_neighbors=15)
    t0 = time.perf_counter()
    desc.fit(X_train)
    D = desc.transform(X_test)
    scores = desc.score(X_test)
    dt = time.perf_counter() - t0

    n_eigs = min(desc.n_eigs, X_test.shape[1])
    morse_col = D[:, n_eigs + 5]

    auc = safe_auc(y_test, scores)

    # ── Morse index degeneracy check ──
    n_nonzero = int(np.sum(morse_col > 0))
    pct_nonzero = 100 * n_nonzero / len(morse_col) if len(morse_col) else 0
    max_morse = int(morse_col.max()) if len(morse_col) else 0
    mean_morse = float(morse_col.mean()) if len(morse_col) else 0

    # ── Fresh prediction check ──
    desc2 = ReducedTensorDescriptor(n_eigs=5, k_neighbors=15)
    desc2.fit(X_train)
    scores2 = desc2.score(X_test)
    score_diff = np.abs(scores - scores2).max()

    return {
        'name': name,
        'auc': auc,
        'time': dt,
        'morse_nonzero_pct': pct_nonzero,
        'morse_max': max_morse,
        'morse_mean': mean_morse,
        'fresh_pred_max_diff': score_diff,
        'error': None,
    }


def benchmark_dataset(dataset_name, X, y, T, N):
    print(f'\n{"="*70}')
    print(f'  {dataset_name}   (T={T}, N={N}, d={X.shape[1]}, '
          f'samples={len(X)}, crisis_rate={y.mean():.3f})')
    print(f'{"="*70}')

    results = []

    # ── Full engines ──
    engines = [
        ('Hybrid',    HybridGravityEngine()),
        ('Gravity',   GravityModeEngine(iterations=60, k_neighbors=10,
                                        use_fused=True)),
        ('Molecular', MolecularEngine(iterations=80, k_neighbors=10,
                                      use_fused=True)),
    ]
    for ename, eng in engines:
        print(f'  Running {ename}...', end='', flush=True)
        r = run_engine(ename, eng, X, y, T, N)
        results.append(r)
        if r['error']:
            print(f' ERROR: {r["error"]}')
        else:
            print(f' AUC={r["auc"]:.4f}  ({r["time"]:.1f}s)')

    # ── ReducedTensorDescriptor ──
    print(f'  Running Descriptor (GMM)...', end='', flush=True)
    r = run_descriptor('Descriptor_GMM', X, X, y, T, N)
    results.append(r)
    if r['error']:
        print(f' ERROR: {r["error"]}')
    else:
        print(f' AUC={r["auc"]:.4f}  ({r["time"]:.1f}s)')
        print(f'    Morse index: {r["morse_nonzero_pct"]:.1f}% non-zero, '
              f'max={r["morse_max"]}, mean={r["morse_mean"]:.3f}')
        print(f'    Fresh-prediction max-diff: {r["fresh_pred_max_diff"]:.2e}')

    # ── Degeneracy summary ──
    full_aucs = [r['auc'] for r in results if 'Descriptor' not in r['name']
                 and not np.isnan(r['auc'])]
    desc_auc = [r['auc'] for r in results if 'Descriptor' in r['name']]

    if full_aucs and desc_auc and not np.isnan(desc_auc[0]):
        best_full = max(full_aucs)
        gap = best_full - desc_auc[0]
        degenerate = gap > 0.05
        print(f'\n  >> Best full-engine AUC: {best_full:.4f}')
        print(f'  >> Descriptor AUC:      {desc_auc[0]:.4f}')
        print(f'  >> Gap:                 {gap:+.4f}  '
              f'{"*** DEGENERATE ***" if degenerate else "OK"}')

    return results


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print('='*70)
    print('  ReducedTensorDescriptor — ERCOT + Bank-Level Benchmark')
    print('  GMM-based energy for non-trivial Morse indices')
    print('='*70)

    all_results = {}

    # ── Dataset 1: ERCOT ──
    X_e, y_e, T_e, N_e = build_ercot_data()
    all_results['ERCOT'] = benchmark_dataset('ERCOT Texas Grid', X_e, y_e, T_e, N_e)

    # ── Dataset 2: Bank-Level ──
    X_b, y_b, T_b, N_b = build_bank_data()
    all_results['Bank'] = benchmark_dataset('Bank-Level G-SIB', X_b, y_b, T_b, N_b)

    # ── Save results ──
    out_path = Path(__file__).parent / 'bench_descriptor_results.json'
    flat = {}
    for ds, results in all_results.items():
        for r in results:
            key = f'{ds}_{r["name"]}'
            flat[key] = {k: (v if not isinstance(v, float) or not np.isnan(v)
                             else None) for k, v in r.items()}
    with open(out_path, 'w') as f:
        json.dump(flat, f, indent=2)
    print(f'\nResults saved to {out_path}')

    # ── Final summary table ──
    print('\n' + '='*70)
    print('  SUMMARY TABLE')
    print('='*70)
    print(f'  {"Dataset":<15} {"Engine":<18} {"AUC":>7} {"Time":>7}  Morse%')
    print(f'  {"-"*15} {"-"*18} {"-"*7} {"-"*7}  {"-"*8}')
    for ds, results in all_results.items():
        for r in results:
            auc_s = f'{r["auc"]:.4f}' if not np.isnan(r.get('auc', float('nan'))) else '  N/A'
            time_s = f'{r["time"]:.1f}s'
            morse_s = f'{r.get("morse_nonzero_pct", 0):.1f}%' if 'Descriptor' in r['name'] else '   -'
            print(f'  {ds:<15} {r["name"]:<18} {auc_s:>7} {time_s:>7}  {morse_s}')
