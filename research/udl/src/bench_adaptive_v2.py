"""
Benchmark v2: Gated adaptive stretching (only weak subspaces get tanh)
======================================================================
Fix: clear subspaces keep raw mahal. Only disc < 0.4 get tanh stretch.
Quick test on pendigits + arrhythmia to verify.
"""
import sys, os, time, json
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


class PatchedSubMF(SubspaceMetaFusion):
    """SubMF with configurable adaptive_stretch."""
    def __init__(self, adaptive, gamma, **kw):
        super().__init__(**kw)
        self._adap = adaptive
        self._gamma = gamma

    def fit(self, X, y):
        import copy as cp
        try:
            from udl.meta_fusion import MetaFusionPipeline, default_operators
        except ImportError:
            from meta_fusion import MetaFusionPipeline, default_operators
        ops = self.operators or default_operators()
        self._meta = MetaFusionPipeline(
            operators=cp.deepcopy(ops), strategies=self.strategies,
            fusion_mode=self.fusion_mode, verbose=self.verbose,
        )
        self._meta.fit(X, y)
        self._boundary_rescue = BoundaryRescueStrategy(
            operators=cp.deepcopy(ops), n_projections=200,
            subspace_dim='auto', use_magnifier=True, magnifier_weight=0.3,
        )
        self._boundary_rescue.scanner.adaptive_stretch = self._adap
        self._boundary_rescue.scanner.stretch_gamma = self._gamma
        self._boundary_rescue.fit(X, y)
        self._fitted = True
        return self


# Quick test: the two datasets that matter most
DATASETS = ['pendigits', 'arrhythmia', 'mammography', 'satellite']


def eval_pipe(name, pipe, X_tr, y_tr, X_te, y_te):
    t0 = time.time()
    pipe.fit(X_tr, y_tr)
    sc = pipe.score(X_te)
    auc = max(roc_auc_score(y_te, sc), 1 - roc_auc_score(y_te, sc))
    dt = time.time() - t0
    return round(auc, 4), dt


results = {}
for ds in DATASETS:
    print(f"\n{'='*65}")
    print(f"  {ds.upper()}")
    print(f"{'='*65}")
    X, y = load_dataset(ds)
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
    tr, te = next(sss.split(X, y))
    X_tr, X_te, y_tr, y_te = X[tr], X[te], y[tr], y[te]
    print(f"  N={len(X)}, dim={X.shape[1]}, anom_test={int(y_te.sum())}")
    results[ds] = {}

    configs = [
        ("BR-raw",       False, 3.0, "BR"),
        ("BR-gate-γ3",   True,  3.0, "BR"),
        ("BR-gate-γ5",   True,  5.0, "BR"),
        ("SubMF-raw",    False, 3.0, "SubMF"),
        ("SubMF-gate-γ3",True,  3.0, "SubMF"),
        ("SubMF-gate-γ5",True,  5.0, "SubMF"),
    ]

    for name, adaptive, gamma, kind in configs:
        if kind == "BR":
            pipe = BoundaryRescueStrategy(
                operators=comba(), n_projections=200,
                subspace_dim='auto', method='mixed', aggregation='softmax',
                use_magnifier=True, magnifier_weight=0.3,
            )
            pipe.scanner.adaptive_stretch = adaptive
            pipe.scanner.stretch_gamma = gamma
        else:
            pipe = PatchedSubMF(
                adaptive=adaptive, gamma=gamma,
                operators=comba(),
                strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo',
                            'signed_lr', 'magnifier'],
                n_projections=200, fusion_mode='mean', verbose=False,
            )

        auc, dt = eval_pipe(name, pipe, X_tr, y_tr, X_te, y_te)
        results[ds][name] = auc
        print(f"    {name:25s} AUC={auc:.4f}  ({dt:.1f}s)")

        # Print disc stats
        scanner = None
        if kind == "BR" and hasattr(pipe, 'scanner'):
            scanner = pipe.scanner
        elif kind == "SubMF" and hasattr(pipe, '_boundary_rescue'):
            scanner = pipe._boundary_rescue.scanner
        if scanner and scanner._sub_stats and adaptive:
            discs = [s[2] for s in scanner._sub_stats]
            n_weak = sum(1 for d in discs if d < 0.3)
            n_mid  = sum(1 for d in discs if 0.3 <= d < 0.7)
            n_clear = sum(1 for d in discs if d >= 0.7)
            # Count gated (gate > 0.01)
            n_gated = sum(1 for d in discs
                         if 1/(1+np.exp(20*(d-0.4))) > 0.01)
            print(f"      disc: min={min(discs):.3f} mean={np.mean(discs):.3f}"
                  f" max={max(discs):.3f}")
            print(f"      weak(<0.3)={n_weak} mid={n_mid} clear(>0.7)={n_clear}"
                  f" gated(stretched)={n_gated}/{len(discs)}")


# Summary
print("\n\n" + "="*90)
print("  GATED ADAPTIVE STRETCHING — RESULTS")
print("="*90)
methods = ["BR-raw", "BR-gate-γ3", "BR-gate-γ5",
           "SubMF-raw", "SubMF-gate-γ3", "SubMF-gate-γ5"]

header = f"{'Method':22s}"
for d in DATASETS:
    header += f"  {d[:8]:>8s}"
header += "    mAUC   Δ(raw)"
print(header)
print("-"*len(header))

raw_means = {}
for m in methods:
    aucs = [results.get(d, {}).get(m) for d in DATASETS]
    valid = [a for a in aucs if a is not None]
    raw_means[m] = np.mean(valid) if valid else 0

for m in methods:
    row = f"{m:22s}"
    aucs = []
    for d in DATASETS:
        v = results.get(d, {}).get(m)
        if v is not None:
            row += f"  {v:8.4f}"; aucs.append(v)
        else:
            row += f"  {'---':>8s}"
    if aucs:
        mean_auc = np.mean(aucs)
        base_key = "BR-raw" if m.startswith("BR") else "SubMF-raw"
        base = raw_means.get(base_key, mean_auc)
        delta = (mean_auc - base) * 100
        sign = "+" if delta >= 0 else ""
        row += f"   {mean_auc:.4f}  {sign}{delta:.1f}pp"
    print(row)

print("\n── Per-dataset deltas: gate(γ=3) vs raw ──")
for prefix in ["BR", "SubMF"]:
    raw_k = f"{prefix}-raw"
    adap_k = f"{prefix}-gate-γ3"
    print(f"\n  {prefix}:")
    for d in DATASETS:
        raw = results.get(d, {}).get(raw_k, 0)
        adap = results.get(d, {}).get(adap_k, 0)
        delta = (adap - raw) * 100
        sign = "+" if delta >= 0 else ""
        print(f"    {d:15s}  {raw:.4f} → {adap:.4f}  ({sign}{delta:.1f}pp)")

print("="*90)
