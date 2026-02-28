"""
Worker script — evaluate lean method set on one dataset.
Called by validate_phase2.py in a subprocess for memory isolation.

Methods (paper-ready, non-redundant):
  Lean 5-op stack: Phase, Topo, Legendre, Geometric, Recon
  (selected by correlation audit -- diverse, high-coverage, no redundancy)
"""
import gc, os, sys, json
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from copy import deepcopy

from udl.compare_sota import load_all_datasets
from udl.pipeline import UDLPipeline
from udl.rank_fusion import RankFusionPipeline
from udl.hybrid_pipeline import HybridPipeline
from udl.meta_fusion import MetaFusionPipeline, default_operators

from udl.experimental_spectra import PhaseCurveSpectrum
from udl.spectra import RankOrderSpectrum
from udl.new_spectra import TopologicalSpectrum, KernelRKHSSpectrum

# Old 4-op stack for comparison
OPS_OLD = [
    ("phase", PhaseCurveSpectrum()),
    ("topo", TopologicalSpectrum(k=15)),
    ("kernel", KernelRKHSSpectrum()),
    ("rank", RankOrderSpectrum()),
]


def cov_at_k(scores, y, k):
    anom = np.where(y == 1)[0]
    if len(anom) == 0:
        return 0, 0
    th = np.percentile(scores, 100 * (1 - k))
    return int(np.sum(scores[anom] >= th)), len(anom)


def run_method(builder_fn, X_tr, X_te, y_tr, y_te, top_k):
    gc.collect()
    pipe = None
    try:
        pipe = builder_fn()
        pipe.fit(X_tr, y_tr)
        s = pipe.score(X_te)
        auc = float(roc_auc_score(y_te, s))
        det, n = cov_at_k(s, y_te, top_k)
        cov = det / n if n > 0 else 0.0
        info = ""
        if hasattr(pipe, '_strategy'):
            info = str(pipe._strategy)
        elif hasattr(pipe, 'selected_arm'):
            info = str(pipe.selected_arm)
        elif hasattr(pipe, 'strategy_names'):
            info = "+".join(pipe.strategy_names)
        return {"auc": auc, "cov": cov, "det": det, "n": n, "info": info}
    except Exception as e:
        return {"auc": 0.0, "cov": 0.0, "det": 0, "n": int(y_te.sum()), "info": "ERR: " + str(e)}
    finally:
        del pipe
        gc.collect()


def main():
    ds_name = sys.argv[1]

    ds = load_all_datasets()
    X, y = ds[ds_name]
    del ds
    gc.collect()

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=42
    )
    anom_rate = y_te.mean()
    top_k = min(max(anom_rate * 2, 0.05), 0.30)

    LEAN = default_operators  # function that returns fresh ops
    results = {}

    # ---- Lean 5-op stack (paper methods) ----

    # 1. Fisher (lean)
    results["Fisher-lean"] = run_method(
        lambda: UDLPipeline(operators=deepcopy(LEAN()), centroid_method='auto',
                            projection_method='fisher'),
        X_tr, X_te, y_tr, y_te, top_k)

    # 2. RankFuse (lean)
    results["Fuse-lean"] = run_method(
        lambda: RankFusionPipeline(operators=deepcopy(LEAN()), fusion='mean'),
        X_tr, X_te, y_tr, y_te, top_k)

    # 3. QuadSurf (lean)
    results["QuadSurf-lean"] = run_method(
        lambda: UDLPipeline(operators=deepcopy(LEAN()), centroid_method='auto',
                            projection_method='fisher', mfls_method='quadratic'),
        X_tr, X_te, y_tr, y_te, top_k)

    # 4. MetaFusion (default: fisher + fusion + quadsurf)
    results["MetaFusion"] = run_method(
        lambda: MetaFusionPipeline(
            operators=LEAN(),
            strategies=['fisher', 'fusion', 'quadsurf'],
            verbose=False),
        X_tr, X_te, y_tr, y_te, top_k)

    # 5. MetaFusion-full (all 6 strategies)
    results["MetaFusion+"] = run_method(
        lambda: MetaFusionPipeline(
            operators=LEAN(),
            strategies=['fisher', 'fusion', 'quadsurf', 'qs_expo', 'signed_lr', 'magnifier'],
            verbose=False),
        X_tr, X_te, y_tr, y_te, top_k)

    # 6. Hybrid-auto (lean)
    results["Hybrid-lean"] = run_method(
        lambda: HybridPipeline(operators=deepcopy(LEAN()), mode='auto'),
        X_tr, X_te, y_tr, y_te, top_k)

    # ---- Old 4-op stack for comparison ----

    # 7. Fisher (old 4-op)
    results["Fisher-4op"] = run_method(
        lambda: UDLPipeline(operators=deepcopy(OPS_OLD), centroid_method='auto',
                            projection_method='fisher'),
        X_tr, X_te, y_tr, y_te, top_k)

    # 8. RankFuse (old 4-op)
    results["Fuse-4op"] = run_method(
        lambda: RankFusionPipeline(operators=deepcopy(OPS_OLD), fusion='mean'),
        X_tr, X_te, y_tr, y_te, top_k)

    # 9. Hybrid-auto (old 4-op)
    results["Hybrid-4op"] = run_method(
        lambda: HybridPipeline(operators=deepcopy(OPS_OLD), mode='auto'),
        X_tr, X_te, y_tr, y_te, top_k)

    print("RESULTS_JSON:" + json.dumps(results))


if __name__ == "__main__":
    main()
