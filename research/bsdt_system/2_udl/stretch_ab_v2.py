"""Clean A/B: raw vs tanh vs softplus stretching (3 variants)."""
import sys, os, time
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


def make_br(tanh_stretch, exp_stretch, gamma=3.0, alpha=2.0):
    pipe = BoundaryRescueStrategy(
        operators=comba(), n_projections=200,
        subspace_dim='auto', method='mixed', aggregation='softmax',
        use_magnifier=True, magnifier_weight=0.3,
    )
    pipe.scanner.tanh_stretch = tanh_stretch
    pipe.scanner.exp_stretch = exp_stretch
    pipe.scanner.stretch_gamma = gamma
    pipe.scanner.exp_alpha = alpha
    return pipe


def make_submf(tanh_stretch, exp_stretch, gamma=3.0):
    """Build SubMF and patch its internal scanner before fit."""
    class PatchedSubMF(SubspaceMetaFusion):
        def __init__(self, ts, es, g, **kw):
            super().__init__(**kw)
            self._ts = ts; self._es = es; self._g = g
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
            self._boundary_rescue.scanner.tanh_stretch = self._ts
            self._boundary_rescue.scanner.exp_stretch = self._es
            self._boundary_rescue.scanner.stretch_gamma = self._g
            self._boundary_rescue.fit(X, y)
            self._fitted = True
            return self

    return PatchedSubMF(
        ts=tanh_stretch, es=exp_stretch, g=gamma,
        operators=comba(),
        strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo',
                    'signed_lr', 'magnifier'],
        n_projections=200, fusion_mode='mean', verbose=False,
    )


def eval_pipe(name, pipe, X_tr, y_tr, X_te, y_te):
    t0 = time.time()
    pipe.fit(X_tr, y_tr)
    sc = pipe.score(X_te)
    auc = max(roc_auc_score(y_te, sc), 1 - roc_auc_score(y_te, sc))
    dt = time.time() - t0
    print(f"    {name:30s} AUC={auc:.4f}  ({dt:.1f}s)")
    return round(auc, 4)


VARIANTS = {
    #       (tanh_stretch, exp_stretch, gamma)
    "BR-raw":        (False, False, 3.0),
    "BR-tanh":       (True,  False, 3.0),
    "BR-softplus":   (True,  True,  3.0),  # exp_stretch=True now means softplus
    "SubMF-raw":     (False, False, 3.0),
    "SubMF-tanh":    (True,  False, 3.0),
    "SubMF-softplus":(True,  True,  3.0),
}


results = {}
for ds in DATASETS:
    print(f"\n{'='*60}\n  {ds.upper()}\n{'='*60}")
    X, y = load_dataset(ds)
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
    tr, te = next(sss.split(X, y))
    X_tr, X_te, y_tr, y_te = X[tr], X[te], y[tr], y[te]
    print(f"  N={len(X)}, dim={X.shape[1]}, anom_test={int(y_te.sum())}")
    results[ds] = {}

    for name, (ts, es, g) in VARIANTS.items():
        if name.startswith("BR"):
            pipe = make_br(ts, es, g)
        else:
            pipe = make_submf(ts, es, g)
        auc = eval_pipe(name, pipe, X_tr, y_tr, X_te, y_te)
        results[ds][name] = auc


# Summary
print("\n\n" + "="*110)
print("  RAW vs TANH vs SOFTPLUS — SUMMARY")
print("="*110)

header = f"{'Method':20s}"
for d in DATASETS:
    header += f"  {d[:8]:>8s}"
header += "   mAUC"
print(header)
print("-"*len(header))

for name in VARIANTS:
    row = f"{name:20s}"
    aucs = []
    for d in DATASETS:
        v = results.get(d, {}).get(name)
        if v is not None:
            row += f"  {v:8.4f}"; aucs.append(v)
        else:
            row += f"  {'---':>8s}"
    if aucs:
        row += f"   {np.mean(aucs):.4f}"
    print(row)

# Deltas vs raw
print("\nDeltas vs raw:")
for prefix in ["BR", "SubMF"]:
    raw_key = f"{prefix}-raw"
    for variant in ["tanh", "softplus"]:
        var_key = f"{prefix}-{variant}"
        deltas = []
        for d in DATASETS:
            raw = results.get(d, {}).get(raw_key, 0)
            var = results.get(d, {}).get(var_key, 0)
            deltas.append((d, (var - raw) * 100))
        mean_d = np.mean([x[1] for x in deltas])
        sign = "+" if mean_d >= 0 else ""
        print(f"\n  {var_key} vs {raw_key}:  {sign}{mean_d:.1f} pp overall")
        for d, delta in deltas:
            s = "+" if delta >= 0 else ""
            print(f"    {d:15s}  {s}{delta:.1f} pp")

import json
os.makedirs("results", exist_ok=True)
with open("results/stretch_ab_v2.json", "w") as f:
    json.dump(results, f, indent=2)
print("\nSaved to results/stretch_ab_v2.json")
