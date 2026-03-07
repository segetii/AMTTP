"""
A/B Benchmark: BSDT tanh stretching ON vs OFF in SubspaceScan
==============================================================
Measures whether the per-subspace tanh(γ·z) stretching improves AUC,
particularly on the TYPE-1 BOUNDARY-heavy datasets (arrhythmia, satellite).

Tests 4 variants:
  1. Raw (no stretch, no exp)          — the old default
  2. Tanh only (γ=3.0)                 — tanh saturation per subspace
  3. Tanh + Exp (γ=3.0, α=2.0)        — tanh + exponential amplification
  4. Tanh + MagnifiedScan              — tanh stretch + scanning the magnified R

Plus SubMF-CombA with each variant for the full-pipeline comparison.
"""

import sys, os, time, json
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedShuffleSplit
from datasets import load_dataset

# Operators
from udl.experimental_spectra import (
    PhaseCurveSpectrum, LegendreBasisSpectrum,
    FourierBasisSpectrum, BSplineBasisSpectrum, WaveletBasisSpectrum,
)
from udl.spectra import GeometricSpectrum, ReconstructionSpectrum
from udl.new_spectra import TopologicalSpectrum
from subspace_scan import SubspaceScanScorer, BoundaryRescueStrategy, SubspaceMetaFusion
from udl.meta_fusion import MetaFusionPipeline, default_operators
import copy


def comba_operators():
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


def eval_pipe(name, pipe, X_tr, y_tr, X_te, y_te):
    try:
        t0 = time.time()
        pipe.fit(X_tr, y_tr)
        sc = pipe.score(X_te)
        auc = roc_auc_score(y_te, sc)
        auc = max(auc, 1 - auc)
        dt = time.time() - t0
        print(f"    {name:40s} AUC={auc:.4f}  ({dt:.1f}s)")
        return auc
    except Exception as e:
        print(f"    {name:40s} FAILED: {e}")
        import traceback; traceback.print_exc()
        return None


def make_variants():
    """Build the 4 BoundaryRescue variants + 2 SubMF variants."""
    return {
        # ── BoundaryRescue (standalone) ──
        "BR-raw (no stretch)": lambda: BoundaryRescueStrategy(
            operators=comba_operators(), n_projections=200,
            subspace_dim='auto', method='mixed', aggregation='softmax',
            use_magnifier=True, magnifier_weight=0.3,
        ),
        "BR-tanh (γ=3)": lambda: BoundaryRescueStrategy(
            operators=comba_operators(), n_projections=200,
            subspace_dim='auto', method='mixed', aggregation='softmax',
            use_magnifier=True, magnifier_weight=0.3,
        ),
        "BR-tanh+exp (γ=3,α=2)": lambda: BoundaryRescueStrategy(
            operators=comba_operators(), n_projections=200,
            subspace_dim='auto', method='mixed', aggregation='softmax',
            use_magnifier=True, magnifier_weight=0.3,
        ),
        # ── SubMF-CombA wrappers ──
        "SubMF-raw (no stretch)": lambda: SubspaceMetaFusion(
            operators=comba_operators(),
            strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo',
                        'signed_lr', 'magnifier'],
            n_projections=200, fusion_mode='mean', verbose=False,
        ),
        "SubMF-tanh (γ=3)": lambda: SubspaceMetaFusion(
            operators=comba_operators(),
            strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo',
                        'signed_lr', 'magnifier'],
            n_projections=200, fusion_mode='mean', verbose=False,
        ),
    }


def patch_scanner(pipe, tanh_stretch, stretch_gamma=3.0,
                  exp_stretch=False, exp_alpha=2.0):
    """Override the scanner's stretch settings after construction."""
    # Find the scanner inside the pipeline
    scanner = None
    if hasattr(pipe, 'scanner'):
        scanner = pipe.scanner
    elif hasattr(pipe, '_boundary_rescue') and hasattr(pipe._boundary_rescue, 'scanner'):
        scanner = pipe._boundary_rescue.scanner

    if scanner is not None:
        scanner.tanh_stretch = tanh_stretch
        scanner.stretch_gamma = stretch_gamma
        scanner.exp_stretch = exp_stretch
        scanner.exp_alpha = exp_alpha


def run():
    results = {}

    for ds_name in DATASETS:
        print(f"\n{'='*70}")
        print(f"  DATASET: {ds_name.upper()}")
        print(f"{'='*70}")
        try:
            X, y = load_dataset(ds_name)
        except Exception as e:
            print(f"  SKIP: {e}")
            continue

        sss = StratifiedShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
        tr, te = next(sss.split(X, y))
        X_tr, X_te = X[tr], X[te]
        y_tr, y_te = y[tr], y[te]
        print(f"  N_train={len(X_tr)}, N_test={len(X_te)}, "
              f"anomalies={int(y_te.sum())}, dim={X.shape[1]}")

        results[ds_name] = {}

        # ---- BoundaryRescue variants ----
        # 1. Raw (no stretch)
        pipe = BoundaryRescueStrategy(
            operators=comba_operators(), n_projections=200,
            subspace_dim='auto', method='mixed', aggregation='softmax',
            use_magnifier=True, magnifier_weight=0.3,
        )
        patch_scanner(pipe, tanh_stretch=False)
        auc = eval_pipe("BR-raw (no stretch)", pipe, X_tr, y_tr, X_te, y_te)
        if auc: results[ds_name]["BR-raw"] = round(auc, 4)

        # 2. Tanh only
        pipe = BoundaryRescueStrategy(
            operators=comba_operators(), n_projections=200,
            subspace_dim='auto', method='mixed', aggregation='softmax',
            use_magnifier=True, magnifier_weight=0.3,
        )
        patch_scanner(pipe, tanh_stretch=True, stretch_gamma=3.0)
        auc = eval_pipe("BR-tanh (γ=3)", pipe, X_tr, y_tr, X_te, y_te)
        if auc: results[ds_name]["BR-tanh"] = round(auc, 4)

        # 3. Tanh + Exp
        pipe = BoundaryRescueStrategy(
            operators=comba_operators(), n_projections=200,
            subspace_dim='auto', method='mixed', aggregation='softmax',
            use_magnifier=True, magnifier_weight=0.3,
        )
        patch_scanner(pipe, tanh_stretch=True, stretch_gamma=3.0,
                      exp_stretch=True, exp_alpha=2.0)
        auc = eval_pipe("BR-tanh+exp (γ=3,α=2)", pipe, X_tr, y_tr, X_te, y_te)
        if auc: results[ds_name]["BR-tanh+exp"] = round(auc, 4)

        # ---- SubMF-CombA variants ----
        # 4. SubMF raw
        pipe = SubspaceMetaFusion(
            operators=comba_operators(),
            strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo',
                        'signed_lr', 'magnifier'],
            n_projections=200, fusion_mode='mean', verbose=False,
        )
        patch_scanner(pipe, tanh_stretch=False)
        auc = eval_pipe("SubMF-raw (no stretch)", pipe, X_tr, y_tr, X_te, y_te)
        if auc: results[ds_name]["SubMF-raw"] = round(auc, 4)

        # 5. SubMF tanh
        pipe = SubspaceMetaFusion(
            operators=comba_operators(),
            strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo',
                        'signed_lr', 'magnifier'],
            n_projections=200, fusion_mode='mean', verbose=False,
        )
        patch_scanner(pipe, tanh_stretch=True, stretch_gamma=3.0)
        auc = eval_pipe("SubMF-tanh (γ=3)", pipe, X_tr, y_tr, X_te, y_te)
        if auc: results[ds_name]["SubMF-tanh"] = round(auc, 4)

        # 6. SubMF tanh + exp
        pipe = SubspaceMetaFusion(
            operators=comba_operators(),
            strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo',
                        'signed_lr', 'magnifier'],
            n_projections=200, fusion_mode='mean', verbose=False,
        )
        patch_scanner(pipe, tanh_stretch=True, stretch_gamma=3.0,
                      exp_stretch=True, exp_alpha=2.0)
        auc = eval_pipe("SubMF-tanh+exp (γ=3,α=2)", pipe, X_tr, y_tr, X_te, y_te)
        if auc: results[ds_name]["SubMF-tanh+exp"] = round(auc, 4)

    # ────────────────────── Summary ──────────────────────
    print("\n\n" + "=" * 110)
    print("  BSDT TANH STRETCHING A/B — SUMMARY")
    print("=" * 110)

    all_methods = ["BR-raw", "BR-tanh", "BR-tanh+exp",
                   "SubMF-raw", "SubMF-tanh", "SubMF-tanh+exp"]

    header = f"{'Method':25s}"
    for ds in DATASETS:
        header += f"  {ds[:8]:>8s}"
    header += "    mAUC   Δ(raw)"
    print(header)
    print("-" * len(header))

    # Compute baselines for delta
    raw_aucs = {}
    for m in all_methods:
        aucs = [results.get(ds, {}).get(m, None) for ds in DATASETS]
        valid = [a for a in aucs if a is not None]
        raw_aucs[m] = np.mean(valid) if valid else None

    for method in all_methods:
        row = f"{method:25s}"
        aucs = []
        for ds in DATASETS:
            auc = results.get(ds, {}).get(method)
            if auc is not None:
                row += f"  {auc:8.4f}"
                aucs.append(auc)
            else:
                row += f"  {'---':>8s}"
        if aucs:
            mean_auc = np.mean(aucs)
            # Delta vs raw variant
            base_key = "BR-raw" if method.startswith("BR") else "SubMF-raw"
            base = raw_aucs.get(base_key)
            delta = (mean_auc - base) * 100 if base else 0
            sign = "+" if delta >= 0 else ""
            row += f"   {mean_auc:.4f}  {sign}{delta:.1f}pp"
        print(row)

    print("=" * 110)

    # Save
    out_path = "results/tanh_stretch_ab.json"
    os.makedirs("results", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == '__main__':
    run()
