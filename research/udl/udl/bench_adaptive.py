"""
Benchmark: Adaptive per-subspace stretching vs raw SubspaceScan
================================================================
Tests the key hypothesis: per-subspace disc_j-weighted blend of
linear (clear subspaces) + tanh (weak subspaces) should improve
arrhythmia (+boundary stretch) WITHOUT hurting pendigits (+preserve ranking).
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


DATASETS = ['mammography', 'pendigits', 'annthyroid',
            'arrhythmia', 'satellite', 'glass', 'cardio']


def eval_pipe(name, pipe, X_tr, y_tr, X_te, y_te):
    t0 = time.time()
    pipe.fit(X_tr, y_tr)
    sc = pipe.score(X_te)
    auc = max(roc_auc_score(y_te, sc), 1 - roc_auc_score(y_te, sc))
    dt = time.time() - t0
    print(f"    {name:35s} AUC={auc:.4f}  ({dt:.1f}s)")
    return round(auc, 4)


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
            operators=cp.deepcopy(ops), n_projections=self.n_projections,
            subspace_dim=self.subspace_dim, use_magnifier=True, magnifier_weight=0.3,
        )
        # Patch the scanner before fit
        self._boundary_rescue.scanner.adaptive_stretch = self._adap
        self._boundary_rescue.scanner.stretch_gamma = self._gamma
        self._boundary_rescue.fit(X, y)
        self._fitted = True
        return self


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

    # 1. BoundaryRescue — no stretch (baseline)
    pipe = BoundaryRescueStrategy(
        operators=comba(), n_projections=200,
        subspace_dim='auto', method='mixed', aggregation='softmax',
        use_magnifier=True, magnifier_weight=0.3,
    )
    pipe.scanner.adaptive_stretch = False
    auc = eval_pipe("BR-raw", pipe, X_tr, y_tr, X_te, y_te)
    results[ds]["BR-raw"] = auc

    # 2. BoundaryRescue — adaptive stretch (γ=3)
    pipe = BoundaryRescueStrategy(
        operators=comba(), n_projections=200,
        subspace_dim='auto', method='mixed', aggregation='softmax',
        use_magnifier=True, magnifier_weight=0.3,
    )
    # adaptive_stretch=True is default now
    auc = eval_pipe("BR-adaptive(γ=3)", pipe, X_tr, y_tr, X_te, y_te)
    results[ds]["BR-adaptive-3"] = auc

    # 3. BoundaryRescue — adaptive stretch (γ=5)
    pipe = BoundaryRescueStrategy(
        operators=comba(), n_projections=200,
        subspace_dim='auto', method='mixed', aggregation='softmax',
        use_magnifier=True, magnifier_weight=0.3,
    )
    pipe.scanner.stretch_gamma = 5.0
    auc = eval_pipe("BR-adaptive(γ=5)", pipe, X_tr, y_tr, X_te, y_te)
    results[ds]["BR-adaptive-5"] = auc

    # 4. SubMF — no stretch (baseline)
    pipe = PatchedSubMF(
        adaptive=False, gamma=3.0,
        operators=comba(),
        strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo',
                    'signed_lr', 'magnifier'],
        n_projections=200, fusion_mode='mean', verbose=False,
    )
    auc = eval_pipe("SubMF-raw", pipe, X_tr, y_tr, X_te, y_te)
    results[ds]["SubMF-raw"] = auc

    # 5. SubMF — adaptive stretch (γ=3)
    pipe = PatchedSubMF(
        adaptive=True, gamma=3.0,
        operators=comba(),
        strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo',
                    'signed_lr', 'magnifier'],
        n_projections=200, fusion_mode='mean', verbose=False,
    )
    auc = eval_pipe("SubMF-adaptive(γ=3)", pipe, X_tr, y_tr, X_te, y_te)
    results[ds]["SubMF-adaptive-3"] = auc

    # 6. SubMF — adaptive stretch (γ=5)
    pipe = PatchedSubMF(
        adaptive=True, gamma=5.0,
        operators=comba(),
        strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo',
                    'signed_lr', 'magnifier'],
        n_projections=200, fusion_mode='mean', verbose=False,
    )
    auc = eval_pipe("SubMF-adaptive(γ=5)", pipe, X_tr, y_tr, X_te, y_te)
    results[ds]["SubMF-adaptive-5"] = auc

    # Print per-subspace disc stats for the last adaptive run
    if hasattr(pipe, '_boundary_rescue') and pipe._boundary_rescue is not None:
        stats = pipe._boundary_rescue.scanner._sub_stats
        if stats:
            discs = [s[2] for s in stats]
            print(f"  ── Subspace disc scores: min={min(discs):.3f} "
                  f"mean={np.mean(discs):.3f} max={max(discs):.3f} "
                  f"std={np.std(discs):.3f}")
            n_weak = sum(1 for d in discs if d < 0.3)
            n_mid  = sum(1 for d in discs if 0.3 <= d < 0.7)
            n_clear = sum(1 for d in discs if d >= 0.7)
            print(f"     weak(<0.3): {n_weak}  mid(0.3-0.7): {n_mid}  "
                  f"clear(>0.7): {n_clear}  total: {len(discs)}")


# ══════════════════════════════════════════════════════════════
#  SUMMARY TABLE
# ══════════════════════════════════════════════════════════════
print("\n\n" + "="*120)
print("  ADAPTIVE STRETCHING A/B — FINAL RESULTS")
print("="*120)

methods = ["BR-raw", "BR-adaptive-3", "BR-adaptive-5",
           "SubMF-raw", "SubMF-adaptive-3", "SubMF-adaptive-5"]

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

# Per-dataset deltas for the key comparison
print("\n── Per-dataset deltas: adaptive(γ=3) - raw ──")
for prefix in ["BR", "SubMF"]:
    raw_k = f"{prefix}-raw"
    adap_k = f"{prefix}-adaptive-3"
    print(f"\n  {prefix}:")
    for d in DATASETS:
        raw = results.get(d, {}).get(raw_k, 0)
        adap = results.get(d, {}).get(adap_k, 0)
        delta = (adap - raw) * 100
        sign = "+" if delta >= 0 else ""
        print(f"    {d:15s}  {raw:.4f} → {adap:.4f}  ({sign}{delta:.1f}pp)")

print("="*120)

os.makedirs("results", exist_ok=True)
with open("results/adaptive_stretch_results.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\nSaved to results/adaptive_stretch_results.json")
