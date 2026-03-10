"""
Benchmark: Compare all BSDT scoring variants on ERCOT + Bank datasets.
"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'udl'))

import numpy as np
from sklearn.metrics import roc_auc_score
from system_mode import (
    BSDTChannels, ReducedTensorDescriptor,
    MolecularEngine, GravityModeEngine, HybridGravityEngine,
)

np.random.seed(42)

# ── ERCOT-like data ──────────────────────────────────────────────
def make_ercot():
    rng = np.random.RandomState(42)
    N_ref, N_test = 200, 100
    d = 6
    X_ref = rng.randn(N_ref, d)
    X_normal = rng.randn(N_test // 2, d)
    X_anom = rng.randn(N_test // 2, d) * 0.5 + np.array([3, 2, 2.5, 3, 1.5, 2])
    X = np.vstack([X_ref, X_normal, X_anom])
    y = np.array([0] * (N_ref + N_test // 2) + [1] * (N_test // 2))
    return X, y, X_ref

# ── Bank-like data ───────────────────────────────────────────────
def make_bank():
    rng = np.random.RandomState(123)
    N_ref, N_test = 150, 80
    d = 8
    X_ref = rng.randn(N_ref, d) * 0.8
    X_normal = rng.randn(N_test // 2, d) * 0.8
    # Subtler anomalies
    X_anom = rng.randn(N_test // 2, d) * 0.8 + np.array([1.5, 1.2, 1.3, 1.1, 0.9, 1.0, 1.4, 1.2])
    X = np.vstack([X_ref, X_normal, X_anom])
    y = np.array([0] * (N_ref + N_test // 2) + [1] * (N_test // 2))
    return X, y, X_ref


results = {}

for name, make_fn in [('ERCOT', make_ercot), ('Bank', make_bank)]:
    X, y, X_ref = make_fn()
    
    print(f"\n{'='*60}")
    print(f"  {name} Dataset  (N={len(X)}, d={X.shape[1]}, anomaly%={y.mean()*100:.0f}%)")
    print(f"{'='*60}")

    # ── Descriptor with score_variants() ──
    desc = ReducedTensorDescriptor(k_neighbors=10)
    desc.fit(X_ref)
    
    var_results = desc.score_variants(X, y, X_ref=X_ref)
    
    print(f"\n  {'Variant':<15} {'AUROC':>8} {'Time(ms)':>10}")
    print(f"  {'-'*35}")
    
    dataset_results = {}
    for vname in ['baseline', 'full_bsdt', 'quadsurf', 'signed_lr', 'expo_gate']:
        r = var_results[vname]
        auroc = r['auroc']
        t_ms = r['time'] * 1000
        
        marker = ''
        if vname == 'quadsurf':
            marker = ' <-- post-hoc champion'
        elif vname == 'signed_lr' and 'weights' in r:
            # Show which channels matter
            w = r['weights']
            ch_names = ['bias', 'delta_C', 'delta_G', 'delta_A', 'delta_T']
            signs = [f"{ch_names[i]}={w[i]:+.2f}" for i in range(len(w))]
            marker = f"  [{', '.join(signs[1:])}]"
        
        print(f"  {vname:<15} {auroc:>8.4f} {t_ms:>8.1f}ms{marker}")
        dataset_results[vname] = {'auroc': auroc, 'time_ms': t_ms}
        if vname == 'signed_lr' and 'weights' in r:
            dataset_results[vname]['weights'] = r['weights']
    
    # Also run the engines for reference
    print(f"\n  {'Engine':<20} {'AUROC':>8}")
    print(f"  {'-'*30}")
    
    for EngineClass, ename in [
        (MolecularEngine, 'Molecular'),
        (GravityModeEngine, 'Gravity'),
        (HybridGravityEngine, 'Hybrid'),
    ]:
        try:
            eng = EngineClass()
            scores = eng.fit_score(X, y)
            auroc = float(roc_auc_score(y, scores))
            print(f"  {ename:<20} {auroc:>8.4f}")
            dataset_results[f'engine_{ename}'] = {'auroc': auroc}
        except Exception as e:
            print(f"  {ename:<20} ERROR: {e}")
    
    # Descriptor scores
    desc_score = desc.score(X)
    desc_auroc = float(roc_auc_score(y, desc_score))
    print(f"  {'Desc_Score':<20} {desc_auroc:>8.4f}")
    dataset_results['desc_score'] = {'auroc': desc_auroc}
    
    results[name] = dataset_results

# Save results
out_file = os.path.join(os.path.dirname(__file__), 'udl', 'bench_variant_results.json')
with open(out_file, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to {out_file}")

# Summary
print(f"\n{'='*60}")
print("  SUMMARY: Best variant per dataset")
print(f"{'='*60}")
for name, dr in results.items():
    variant_names = ['baseline', 'full_bsdt', 'quadsurf', 'signed_lr', 'expo_gate']
    best = max(variant_names, key=lambda v: dr[v]['auroc'])
    print(f"  {name}: {best} (AUROC={dr[best]['auroc']:.4f})")
