"""Clean A/B: SubMF with tanh forced on vs forced off."""
import sys, os, time
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedShuffleSplit
from datasets import load_dataset
from subspace_scan import SubspaceMetaFusion, BoundaryRescueStrategy, SubspaceScanScorer
from udl.experimental_spectra import (
    PhaseCurveSpectrum, LegendreBasisSpectrum,
    FourierBasisSpectrum, BSplineBasisSpectrum, WaveletBasisSpectrum,
)
import copy

def comba():
    return [
        ("fourier",   FourierBasisSpectrum(n_coeffs=8)),
        ("bspline",   BSplineBasisSpectrum()),
        ("wavelet",   WaveletBasisSpectrum()),
        ("legendre",  LegendreBasisSpectrum(n_degree=6)),
        ("phase",     PhaseCurveSpectrum()),
    ]

DATASETS = ['mammography', 'pendigits', 'annthyroid',
            'arrhythmia', 'satellite', 'glass', 'cardio']


class SubMF_NoTanh(SubspaceMetaFusion):
    """SubMF but force tanh_stretch=False in BoundaryRescue."""
    def fit(self, X, y):
        import copy as cp
        try:
            from udl.meta_fusion import MetaFusionPipeline, default_operators
        except ImportError:
            from meta_fusion import MetaFusionPipeline, default_operators

        ops = self.operators or default_operators()
        self._meta = MetaFusionPipeline(
            operators=cp.deepcopy(ops),
            strategies=self.strategies,
            fusion_mode=self.fusion_mode,
            verbose=self.verbose,
        )
        self._meta.fit(X, y)

        self._boundary_rescue = BoundaryRescueStrategy(
            operators=cp.deepcopy(ops),
            n_projections=self.n_projections,
            subspace_dim=self.subspace_dim,
            use_magnifier=True,
            magnifier_weight=0.3,
        )
        # Force tanh OFF
        self._boundary_rescue.scanner.tanh_stretch = False
        self._boundary_rescue.fit(X, y)

        self._fitted = True
        return self


results = {}
for ds in DATASETS:
    print(f"\n{'='*60}\n  {ds.upper()}\n{'='*60}")
    X, y = load_dataset(ds)
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
    tr, te = next(sss.split(X, y))
    X_tr, X_te, y_tr, y_te = X[tr], X[te], y[tr], y[te]
    print(f"  N={len(X)}, dim={X.shape[1]}, anom_test={int(y_te.sum())}")
    results[ds] = {}

    # 1) SubMF NO tanh
    pipe = SubMF_NoTanh(
        operators=comba(),
        strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo',
                    'signed_lr', 'magnifier'],
        n_projections=200, fusion_mode='mean', verbose=False,
    )
    t0 = time.time()
    pipe.fit(X_tr, y_tr)
    sc = pipe.score(X_te)
    auc = max(roc_auc_score(y_te, sc), 1 - roc_auc_score(y_te, sc))
    print(f"  SubMF-noTanh   AUC={auc:.4f}  ({time.time()-t0:.1f}s)")
    results[ds]["SubMF-noTanh"] = round(auc, 4)

    # 2) SubMF WITH tanh (default)
    pipe = SubspaceMetaFusion(
        operators=comba(),
        strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo',
                    'signed_lr', 'magnifier'],
        n_projections=200, fusion_mode='mean', verbose=False,
    )
    t0 = time.time()
    pipe.fit(X_tr, y_tr)
    sc = pipe.score(X_te)
    auc = max(roc_auc_score(y_te, sc), 1 - roc_auc_score(y_te, sc))
    print(f"  SubMF-tanh     AUC={auc:.4f}  ({time.time()-t0:.1f}s)")
    results[ds]["SubMF-tanh"] = round(auc, 4)

    # 3) BR standalone NO tanh
    pipe = BoundaryRescueStrategy(
        operators=comba(), n_projections=200,
        subspace_dim='auto', method='mixed', aggregation='softmax',
        use_magnifier=True, magnifier_weight=0.3,
    )
    pipe.scanner.tanh_stretch = False
    t0 = time.time()
    pipe.fit(X_tr, y_tr)
    sc = pipe.score(X_te)
    auc = max(roc_auc_score(y_te, sc), 1 - roc_auc_score(y_te, sc))
    print(f"  BR-noTanh      AUC={auc:.4f}  ({time.time()-t0:.1f}s)")
    results[ds]["BR-noTanh"] = round(auc, 4)

    # 4) BR standalone WITH tanh
    pipe = BoundaryRescueStrategy(
        operators=comba(), n_projections=200,
        subspace_dim='auto', method='mixed', aggregation='softmax',
        use_magnifier=True, magnifier_weight=0.3,
    )
    # tanh_stretch=True is default
    t0 = time.time()
    pipe.fit(X_tr, y_tr)
    sc = pipe.score(X_te)
    auc = max(roc_auc_score(y_te, sc), 1 - roc_auc_score(y_te, sc))
    print(f"  BR-tanh        AUC={auc:.4f}  ({time.time()-t0:.1f}s)")
    results[ds]["BR-tanh"] = round(auc, 4)


# Summary
print("\n\n" + "="*100)
print("  CLEAN A/B: tanh ON vs OFF")
print("="*100)
methods = ["BR-noTanh", "BR-tanh", "SubMF-noTanh", "SubMF-tanh"]
header = f"{'Method':20s}"
for d in DATASETS:
    header += f"  {d[:8]:>8s}"
header += "   mAUC"
print(header)
print("-"*len(header))

for m in methods:
    row = f"{m:20s}"
    aucs = []
    for d in DATASETS:
        v = results.get(d, {}).get(m)
        if v is not None:
            row += f"  {v:8.4f}"; aucs.append(v)
        else:
            row += f"  {'---':>8s}"
    if aucs:
        row += f"   {np.mean(aucs):.4f}"
    print(row)

# Deltas
print("\nDeltas (tanh - noTanh):")
for prefix in ["BR", "SubMF"]:
    off_key = f"{prefix}-noTanh"
    on_key = f"{prefix}-tanh"
    print(f"\n  {prefix}:")
    for d in DATASETS:
        off = results.get(d, {}).get(off_key, 0)
        on = results.get(d, {}).get(on_key, 0)
        delta = (on - off) * 100
        sign = "+" if delta >= 0 else ""
        print(f"    {d:15s}  {sign}{delta:.1f} pp")
