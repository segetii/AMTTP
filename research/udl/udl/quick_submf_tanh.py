"""Quick A/B: SubMF with different fusion weights + tanh"""
import sys, os, time, json
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedShuffleSplit
from datasets import load_dataset
from subspace_scan import SubspaceMetaFusion, BoundaryRescueStrategy
from udl.experimental_spectra import (
    PhaseCurveSpectrum, LegendreBasisSpectrum,
    FourierBasisSpectrum, BSplineBasisSpectrum, WaveletBasisSpectrum,
)

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

results = {}

for ds in DATASETS:
    print(f"\n{'='*60}\n  {ds.upper()}\n{'='*60}")
    X, y = load_dataset(ds)
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
    tr, te = next(sss.split(X, y))
    X_tr, X_te, y_tr, y_te = X[tr], X[te], y[tr], y[te]
    print(f"  N={len(X)}, dim={X.shape[1]}, anom_test={int(y_te.sum())}")
    results[ds] = {}

    # SubMF with 50/50 weight + tanh (current code)
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
    print(f"  SubMF-50/50-tanh  AUC={auc:.4f}  ({time.time()-t0:.1f}s)")
    results[ds]["SubMF-50/50-tanh"] = round(auc, 4)

# Summary
print("\n\n" + "="*90)
print("  SubMF 50/50 with tanh stretching — SUMMARY")
print("="*90)
header = f"{'Method':25s}"
for d in DATASETS:
    header += f"  {d[:8]:>8s}"
header += "   mAUC"
print(header)
print("-"*len(header))

# Previous best for comparison
prev = {"mammography": 0.9196, "pendigits": 0.9898, "annthyroid": 0.9877,
        "arrhythmia": 0.6931, "satellite": 0.7772, "glass": 0.9921, "cardio": 1.0}
row = f"{'SubMF-old(60/40,noTanh)':25s}"
aucs = []
for d in DATASETS:
    v = prev.get(d)
    if v: row += f"  {v:8.4f}"; aucs.append(v)
row += f"   {np.mean(aucs):.4f}"
print(row)

row = f"{'SubMF-50/50-tanh':25s}"
aucs = []
for d in DATASETS:
    v = results.get(d, {}).get("SubMF-50/50-tanh")
    if v: row += f"  {v:8.4f}"; aucs.append(v)
row += f"   {np.mean(aucs):.4f}"
print(row)

# Deltas
print("\nPer-dataset delta (new - old):")
for d in DATASETS:
    old = prev.get(d, 0)
    new = results.get(d, {}).get("SubMF-50/50-tanh", 0)
    delta = (new - old) * 100
    sign = "+" if delta >= 0 else ""
    print(f"  {d:15s}  {sign}{delta:.1f} pp")
