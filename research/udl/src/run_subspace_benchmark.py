"""
Benchmark — SubspaceScan Boundary Rescue vs Previous Best
==========================================================
Tests:
  1. SubspaceScan standalone (lean operators)
  2. SubspaceScan standalone (CombA operators)
  3. MetaFusion + SubspaceScan (lean) — adds subspace_scan as 7th strategy
  4. MetaFusion + SubspaceScan (CombA)
  5. SubspaceMetaFusion (full wrapper: MetaFusion-CombA + BoundaryRescue)

Compares against:
  - MetaFusion-CombA (previous best, mAUC=0.901)
  - BSDT-Fuse (mAUC=0.889)
  - Fuse-lean (mAUC=0.879)
"""

import sys, os, json, time
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedShuffleSplit

# UDL imports
from udl.experimental_spectra import PhaseCurveSpectrum, LegendreBasisSpectrum
from udl.spectra import GeometricSpectrum, ReconstructionSpectrum
from udl.new_spectra import TopologicalSpectrum

# Subspace scan
from subspace_scan import SubspaceScanScorer, BoundaryRescueStrategy, SubspaceMetaFusion

# MetaFusion
from udl.meta_fusion import MetaFusionPipeline, default_operators

# Datasets
from datasets import load_dataset

# ── Operator families ──
def lean_operators():
    return [
        ("phase",     PhaseCurveSpectrum()),
        ("topo",      TopologicalSpectrum(k=15)),
        ("legendre",  LegendreBasisSpectrum(n_degree=6)),
        ("geometric", GeometricSpectrum()),
        ("recon",     ReconstructionSpectrum()),
    ]

def comba_operators():
    from udl.experimental_spectra import FourierBasisSpectrum, BSplineBasisSpectrum, WaveletBasisSpectrum
    return [
        ("fourier",   FourierBasisSpectrum(n_coeffs=8)),
        ("bspline",   BSplineBasisSpectrum()),
        ("wavelet",   WaveletBasisSpectrum()),
        ("legendre",  LegendreBasisSpectrum(n_degree=6)),
        ("phase",     PhaseCurveSpectrum()),
    ]

DATASETS = [
    'mammography', 'pendigits', 'annthyroid',
    'arrhythmia', 'satellite', 'glass', 'cardio',
]

CHECKPOINT_FILE = "results/subspace_scan_results.json"


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {}


def save_checkpoint(results):
    os.makedirs("results", exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(results, f, indent=2)


def eval_method(method_name, pipe, X_train, y_train, X_test, y_test):
    """Fit & score a pipeline, return AUC."""
    try:
        t0 = time.time()
        pipe.fit(X_train, y_train)
        scores = pipe.score(X_test)
        auc = roc_auc_score(y_test, scores)
        auc = max(auc, 1 - auc)
        elapsed = time.time() - t0
        print(f"    {method_name:30s}  AUC={auc:.4f}  ({elapsed:.1f}s)")
        return auc
    except Exception as e:
        print(f"    {method_name:30s}  FAILED: {e}")
        return None


def run_benchmark():
    results = load_checkpoint()
    import copy

    methods = {
        # Standalone subspace scan with lean operators
        "SubScan-lean": lambda: BoundaryRescueStrategy(
            operators=lean_operators(),
            n_projections=200,
            subspace_dim='auto',
            method='mixed',
            aggregation='softmax',
            use_magnifier=True,
            magnifier_weight=0.3,
        ),
        # Standalone subspace scan with CombA operators
        "SubScan-CombA": lambda: BoundaryRescueStrategy(
            operators=comba_operators(),
            n_projections=200,
            subspace_dim='auto',
            method='mixed',
            aggregation='softmax',
            use_magnifier=True,
            magnifier_weight=0.3,
        ),
        # MetaFusion-lean + SubspaceScan as 7th strategy
        "MF+SubScan-lean": lambda: MetaFusionPipeline(
            operators=lean_operators(),
            strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo',
                        'signed_lr', 'magnifier', 'subspace_scan'],
            fusion_mode='mean',
        ),
        # MetaFusion-CombA + SubspaceScan as 7th strategy
        "MF+SubScan-CombA": lambda: MetaFusionPipeline(
            operators=comba_operators(),
            strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo',
                        'signed_lr', 'magnifier', 'subspace_scan'],
            fusion_mode='mean',
        ),
        # Full SubspaceMetaFusion wrapper (MetaFusion-CombA + BoundaryRescue)
        "SubMF-CombA": lambda: SubspaceMetaFusion(
            operators=comba_operators(),
            strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo',
                        'signed_lr', 'magnifier'],
            n_projections=200,
            fusion_mode='mean',
        ),
        # Pure subspace scan (no magnifier blend) — ablation
        "SubScan-pure-lean": lambda: BoundaryRescueStrategy(
            operators=lean_operators(),
            n_projections=300,
            subspace_dim='auto',
            method='mixed',
            aggregation='top_k',
            use_magnifier=False,
        ),
    }

    for ds_name in DATASETS:
        print(f"\n{'='*70}")
        print(f"  DATASET: {ds_name.upper()}")
        print(f"{'='*70}")

        try:
            X, y = load_dataset(ds_name)
        except Exception as e:
            print(f"  Failed to load: {e}")
            continue

        # 70/30 stratified split (same as worker_eval.py)
        sss = StratifiedShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
        train_idx, test_idx = next(sss.split(X, y))
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        n_anom_test = y_test.sum()
        print(f"  N_train={len(X_train)}, N_test={len(X_test)}, "
              f"anomalies_test={int(n_anom_test)}, features={X.shape[1]}")

        if ds_name not in results:
            results[ds_name] = {}

        for method_name, make_pipe in methods.items():
            if method_name in results[ds_name]:
                print(f"    {method_name:30s}  AUC={results[ds_name][method_name]:.4f}  (cached)")
                continue

            pipe = make_pipe()
            auc = eval_method(method_name, pipe, X_train, y_train, X_test, y_test)
            if auc is not None:
                results[ds_name][method_name] = round(auc, 4)
                save_checkpoint(results)

    # Print summary table
    print("\n\n" + "=" * 100)
    print("SUBSPACE SCAN BENCHMARK — SUMMARY TABLE")
    print("=" * 100)

    # Load previous best results for comparison
    prev_file = "results/full_benchmark_checkpoint.json"
    prev_results = {}
    if os.path.exists(prev_file):
        with open(prev_file) as f:
            prev_results = json.load(f)

    all_methods = list(methods.keys())
    # Add baseline methods from previous results
    baselines = ['MetaFusion-CombA', 'BSDT-Fuse', 'Fuse-lean']

    header = f"{'Method':30s}"
    for ds in DATASETS:
        header += f"  {ds[:8]:>8s}"
    header += "   mAUC"
    print(header)
    print("-" * len(header))

    # Print baselines first
    for method in baselines:
        row = f"{method:30s}"
        aucs = []
        for ds in DATASETS:
            auc = None
            if ds in prev_results and method in prev_results[ds]:
                auc = prev_results[ds][method]
            if auc is not None:
                row += f"  {auc:8.4f}"
                aucs.append(auc)
            else:
                row += f"  {'---':>8s}"
        if aucs:
            row += f"   {np.mean(aucs):.4f}"
        print(row)

    print("-" * len(header))

    # Print new methods
    for method in all_methods:
        row = f"{method:30s}"
        aucs = []
        for ds in DATASETS:
            auc = results.get(ds, {}).get(method)
            if auc is not None:
                row += f"  {auc:8.4f}"
                aucs.append(auc)
            else:
                row += f"  {'---':>8s}"
        if aucs:
            row += f"   {np.mean(aucs):.4f}"
        print(row)

    print("=" * 100)


if __name__ == '__main__':
    run_benchmark()
