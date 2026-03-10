"""
Benchmark: BSDT channel impact on engine performance.

Compares engines with and without BSDTChannels on synthetic
ERCOT-like and Bank-like datasets to measure AUROC impact.
"""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'udl'))
import numpy as np
from sklearn.metrics import roc_auc_score
from system_mode import (
    BSDTChannels, FusedSystemScorer,
    MolecularEngine, GravityModeEngine, HybridGravityEngine
)

np.random.seed(42)

# ── Generate synthetic benchmark datasets ──

def make_ercot_like(n_normal=400, n_anom=40, d=8):
    """Synthetic ERCOT-like energy data."""
    rng = np.random.RandomState(42)
    X_norm = rng.randn(n_normal, d) * 0.5
    # Anomalies: shifted + some sparse features
    X_anom = rng.randn(n_anom, d) * 0.8 + 2.5
    X_anom[:, ::2] *= 0.05  # sparsify every other feature (targets δ_G)
    X = np.vstack([X_norm, X_anom])
    y = np.array([0]*n_normal + [1]*n_anom)
    return X, y

def make_bank_like(n_normal=300, n_anom=30, d=6):
    """Synthetic Bank crisis data."""
    rng = np.random.RandomState(99)
    X_norm = rng.randn(n_normal, d) * 0.4
    # Anomalies: camouflaged (close to normal centroid but with subtle shifts)
    X_anom = rng.randn(n_anom, d) * 0.4 + 1.5
    X = np.vstack([X_norm, X_anom])
    y = np.array([0]*n_normal + [1]*n_anom)
    return X, y

datasets = {
    'ERCOT_synthetic': make_ercot_like(),
    'Bank_synthetic': make_bank_like(),
}

# ── Benchmark engines ──

results = {}

for ds_name, (X, y) in datasets.items():
    print(f"\n{'='*60}")
    print(f"Dataset: {ds_name}  (N={len(X)}, d={X.shape[1]}, "
          f"anomaly_rate={y.mean():.3f})")
    print(f"{'='*60}")

    # 1. BSDT standalone
    t0 = time.time()
    bsdt = BSDTChannels(k=10)
    bsdt.fit(X[y == 0])
    bsdt_scores = bsdt.score(X)
    bsdt_time = time.time() - t0
    bsdt_auc = roc_auc_score(y, bsdt_scores)

    ch = bsdt.channels(X)
    ch_anom = {k: float(np.mean(v[y == 1])) for k, v in ch.items()}
    ch_norm = {k: float(np.mean(v[y == 0])) for k, v in ch.items()}
    e_bs_anom = float(np.mean(bsdt.energy(X[y == 1])))
    e_bs_norm = float(np.mean(bsdt.energy(X[y == 0])))
    mfls_anom = float(np.mean(bsdt.mfls(X[y == 1])))
    mfls_norm = float(np.mean(bsdt.mfls(X[y == 0])))

    print(f"\n  BSDT standalone:  AUROC={bsdt_auc:.4f}  ({bsdt_time:.2f}s)")
    print(f"    Channel means [anomaly / normal]:")
    for k in ['delta_C', 'delta_G', 'delta_A', 'delta_T']:
        print(f"      {k}: {ch_anom[k]:.4f} / {ch_norm[k]:.4f}")
    print(f"      E_BS:   {e_bs_anom:.4f} / {e_bs_norm:.4f}")
    print(f"      MFLS:   {mfls_anom:.4f} / {mfls_norm:.4f}")

    results[f'{ds_name}_BSDT'] = {
        'auroc': bsdt_auc, 'time': bsdt_time,
        'channels_anom': ch_anom, 'channels_norm': ch_norm,
        'E_BS_anom': e_bs_anom, 'E_BS_norm': e_bs_norm,
        'MFLS_anom': mfls_anom, 'MFLS_norm': mfls_norm,
    }

    # 2. Engines with BSDT vs without
    for EngClass, eng_name in [
        (MolecularEngine, 'Molecular'),
        (GravityModeEngine, 'Gravity'),
    ]:
        for use_bsdt in [False, True]:
            label = f"{eng_name}{'_BSDT' if use_bsdt else '_noBSDT'}"

            # Temporarily control BSDT via monkey-patching FusedSystemScorer
            t0 = time.time()
            engine = EngClass(
                iterations=15, k_neighbors=10,
                max_samples=500, use_fused=True
            )
            # Set BSDT flag on fused scorer
            if engine.fused_scorer is not None:
                if not use_bsdt:
                    engine.fused_scorer.bsdt = None

            scores = engine.fit_score(X, y)
            elapsed = time.time() - t0
            auc = roc_auc_score(y, scores)

            bsdt_fitted = (engine.fused_scorer is not None and
                          engine.fused_scorer.bsdt is not None and
                          engine.fused_scorer.bsdt._fitted)

            print(f"\n  {label}: AUROC={auc:.4f}  ({elapsed:.2f}s)"
                  f"  [BSDT fitted: {bsdt_fitted}]")

            results[f'{ds_name}_{label}'] = {
                'auroc': auc, 'time': elapsed,
                'bsdt_fitted': bsdt_fitted,
            }

    # 3. Hybrid with BSDT
    t0 = time.time()
    hybrid = HybridGravityEngine(
        molecular_params={'iterations': 15, 'k_neighbors': 10, 'max_samples': 500},
        gravity_params={'iterations': 15, 'k_neighbors': 10, 'max_samples': 500},
    )
    hybrid_scores = hybrid.fit_score(X, y)
    hybrid_time = time.time() - t0
    hybrid_auc = roc_auc_score(y, hybrid_scores)
    print(f"\n  Hybrid_BSDT: AUROC={hybrid_auc:.4f}  ({hybrid_time:.2f}s)")
    results[f'{ds_name}_Hybrid_BSDT'] = {
        'auroc': hybrid_auc, 'time': hybrid_time,
    }

# ── Summary ──
print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
for k, v in results.items():
    print(f"  {k:40s}  AUROC={v['auroc']:.4f}  time={v['time']:.2f}s")

# Save
out_path = os.path.join(os.path.dirname(__file__), 'bsdt_benchmark_results.json')
with open(out_path, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to {out_path}")
