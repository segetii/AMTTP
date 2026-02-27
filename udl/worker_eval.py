"""Worker script: evaluate all 6 methods on one dataset. Called by validate_phase2.py."""
import gc, os, sys, json, copy
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from copy import deepcopy

from udl.compare_sota import load_all_datasets
from udl.pipeline import UDLPipeline
from udl.rank_fusion import RankFusionPipeline
from udl.hybrid_pipeline import HybridPipeline
from udl.rl_fusion import RLFusionAgent
from udl.experimental_spectra import PhaseCurveSpectrum
from udl.spectra import RankOrderSpectrum
from udl.new_spectra import TopologicalSpectrum, KernelRKHSSpectrum

OPS = [
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
        return {"auc": auc, "cov": cov, "det": det, "n": n, "info": info}
    except Exception as e:
        return {"auc": 0.0, "cov": 0.0, "det": 0, "n": int(y_te.sum()), "info": f"ERR: {e}"}
    finally:
        del pipe
        gc.collect()


def main():
    ds_name = sys.argv[1]
    priors_path = sys.argv[2] if len(sys.argv) > 2 else ""

    ds = load_all_datasets()
    X, y = ds[ds_name]
    del ds
    gc.collect()

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=42
    )
    anom_rate = y_te.mean()
    top_k = min(max(anom_rate * 2, 0.05), 0.30)

    results = {}

    # 1. Fisher
    results["Fisher"] = run_method(
        lambda: UDLPipeline(operators=deepcopy(OPS), centroid_method='auto',
                            projection_method='fisher'),
        X_tr, X_te, y_tr, y_te, top_k)

    # 2. RankFuse
    results["RankFuse"] = run_method(
        lambda: RankFusionPipeline(operators=deepcopy(OPS), fusion='mean'),
        X_tr, X_te, y_tr, y_te, top_k)

    # 3. Hybrid-auto
    results["Hybrid-auto"] = run_method(
        lambda: HybridPipeline(operators=deepcopy(OPS), mode='auto'),
        X_tr, X_te, y_tr, y_te, top_k)

    # 4. Hybrid-blend
    results["Hybrid-blend"] = run_method(
        lambda: HybridPipeline(operators=deepcopy(OPS), mode='blend'),
        X_tr, X_te, y_tr, y_te, top_k)

    # 5. RL-fresh
    results["RL-fresh"] = run_method(
        lambda: RLFusionAgent(operators=deepcopy(OPS), strategy='thompson',
                              exploration_rounds=3, verbose=False),
        X_tr, X_te, y_tr, y_te, top_k)

    # 6. RL-pretrained
    def make_rl_pretrained():
        agent = RLFusionAgent(operators=deepcopy(OPS), strategy='thompson',
                              exploration_rounds=3, verbose=False)
        if priors_path and os.path.exists(priors_path):
            agent.load_priors(priors_path)
        return agent

    results["RL-pretrained"] = run_method(
        make_rl_pretrained, X_tr, X_te, y_tr, y_te, top_k)

    print("RESULTS_JSON:" + json.dumps(results))


if __name__ == "__main__":
    main()
