"""
Validate Hybrid + RL pipelines against Fisher and RankFusion baselines.
Tests all 4 approaches on 5 datasets measuring both AUC and Coverage.
"""
import numpy as np, sys, os, gc, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from copy import deepcopy
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
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
    th = np.percentile(scores, 100*(1-k))
    return int(np.sum(scores[anom] >= th)), len(anom)


def run_pipe(builder_fn, X_tr, X_te, y_tr, y_te, top_k):
    """Run a pipeline builder and return (auc, coverage)."""
    gc.collect()
    try:
        pipe = builder_fn()
        pipe.fit(X_tr, y_tr)
        s = pipe.score(X_te)
        auc = roc_auc_score(y_te, s)
        det, n = cov_at_k(s, y_te, top_k)
        cov = det / n if n > 0 else 0
        info = ""
        # Extract strategy info if available
        if hasattr(pipe, '_strategy'):
            info = f" [{pipe._strategy}]"
        elif hasattr(pipe, 'selected_arm'):
            info = f" [{pipe.selected_arm}]"
        return auc, cov, det, n, info
    except Exception as e:
        import traceback; traceback.print_exc()
        return 0, 0, 0, int(y_te.sum()), f" [ERR: {e}]"
    finally:
        del pipe
        gc.collect()


def main():
    # ── PHASE 1: Meta-learn RL agent across datasets ──
    print("=" * 110)
    print("  PHASE 1: RL Meta-Learning")
    print("=" * 110)

    # First meta-learn the RL agent on all datasets so it has good priors
    datasets = load_all_datasets()
    meta_agent = RLFusionAgent(
        operators=deepcopy(OPS),
        strategy='thompson',
        exploration_rounds=8,
        verbose=True,
    )
    meta_agent.meta_learn(datasets, n_rounds_per_dataset=8)
    meta_agent.save_priors(os.path.join(os.path.dirname(__file__), "rl_priors.json"))
    del meta_agent, datasets
    gc.collect()

    # ── PHASE 2: Evaluate all approaches per-dataset ──
    print(f"\n\n{'='*110}")
    print("  PHASE 2: Per-Dataset Evaluation (seed=42)")
    print("=" * 110)

    methods = ["Fisher", "RankFuse", "Hybrid-auto", "Hybrid-blend", "RL-fresh", "RL-pretrained"]
    results = {m: {} for m in methods}
    ds_order = ["synthetic", "mimic", "mammography", "shuttle", "pendigits"]

    seed = 42
    # Reload datasets one at a time to reduce peak memory
    all_datasets = load_all_datasets()
    for ds_name in ds_order:
        if ds_name not in all_datasets:
            continue
        X, y = all_datasets[ds_name]
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=seed
        )
        anom_rate = y_te.mean()
        top_k = min(max(anom_rate * 2, 0.05), 0.30)

        print(f"\n  --- {ds_name} (n={len(X)}, d={X.shape[1]}, anom={anom_rate:.3f}, top_k={top_k:.1%}) ---")

        # 1. Fisher baseline
        auc, cov, det, n, info = run_pipe(
            lambda: UDLPipeline(operators=deepcopy(OPS), centroid_method='auto',
                                projection_method='fisher'),
            X_tr, X_te, y_tr, y_te, top_k
        )
        results["Fisher"][ds_name] = {"auc": auc, "cov": cov}
        print(f"    Fisher        AUC={auc:.4f}  Cov={det}/{n} ({100*cov:.0f}%){info}")
        gc.collect()

        # 2. RankFusion baseline
        auc, cov, det, n, info = run_pipe(
            lambda: RankFusionPipeline(operators=deepcopy(OPS), fusion='mean'),
            X_tr, X_te, y_tr, y_te, top_k
        )
        results["RankFuse"][ds_name] = {"auc": auc, "cov": cov}
        print(f"    RankFuse      AUC={auc:.4f}  Cov={det}/{n} ({100*cov:.0f}%){info}")
        gc.collect()

        # 3. Hybrid-auto
        auc, cov, det, n, info = run_pipe(
            lambda: HybridPipeline(operators=deepcopy(OPS), mode='auto'),
            X_tr, X_te, y_tr, y_te, top_k
        )
        results["Hybrid-auto"][ds_name] = {"auc": auc, "cov": cov}
        print(f"    Hybrid-auto   AUC={auc:.4f}  Cov={det}/{n} ({100*cov:.0f}%){info}")

        # 4. Hybrid-blend
        auc, cov, det, n, info = run_pipe(
            lambda: HybridPipeline(operators=deepcopy(OPS), mode='blend'),
            X_tr, X_te, y_tr, y_te, top_k
        )
        results["Hybrid-blend"][ds_name] = {"auc": auc, "cov": cov}
        print(f"    Hybrid-blend  AUC={auc:.4f}  Cov={det}/{n} ({100*cov:.0f}%){info}")

        # 5. RL-fresh (no priors)
        auc, cov, det, n, info = run_pipe(
            lambda: RLFusionAgent(operators=deepcopy(OPS), strategy='thompson',
                                  exploration_rounds=5, verbose=False),
            X_tr, X_te, y_tr, y_te, top_k
        )
        results["RL-fresh"][ds_name] = {"auc": auc, "cov": cov}
        print(f"    RL-fresh      AUC={auc:.4f}  Cov={det}/{n} ({100*cov:.0f}%){info}")

        # 6. RL-pretrained (with meta-learned priors)
        def make_rl_pretrained():
            agent = RLFusionAgent(operators=deepcopy(OPS), strategy='thompson',
                                  exploration_rounds=5, verbose=False)
            agent.load_priors(os.path.join(os.path.dirname(__file__), "rl_priors.json"))
            return agent

        auc, cov, det, n, info = run_pipe(
            make_rl_pretrained, X_tr, X_te, y_tr, y_te, top_k
        )
        results["RL-pretrained"][ds_name] = {"auc": auc, "cov": cov}
        print(f"    RL-pretrained AUC={auc:.4f}  Cov={det}/{n} ({100*cov:.0f}%){info}")

    # ── Summary ──
    print(f"\n\n{'='*110}")
    print("  SUMMARY TABLE")
    print(f"{'='*110}")

    header = f"  {'Method':<18s}"
    for dn in ds_order:
        header += f"  {dn[:8]+'-A':>10s} {dn[:8]+'-C':>8s}"
    header += f"  {'mAUC':>8s} {'mCov':>8s} {'minCov':>8s}"
    print(header)
    print("-" * len(header))

    for method in methods:
        row = f"  {method:<18s}"
        aucs, covs = [], []
        for dn in ds_order:
            r = results[method].get(dn, {"auc": 0, "cov": 0})
            row += f"  {r['auc']:>10.4f} {100*r['cov']:>7.0f}%"
            aucs.append(r['auc'])
            covs.append(r['cov'])
        row += f"  {np.mean(aucs):>8.4f} {100*np.mean(covs):>7.0f}% {100*min(covs):>7.0f}%"
        print(row)

    json.dump(results, open(os.path.join(os.path.dirname(__file__), "hybrid_rl_results.json"), "w"), indent=2)
    print(f"\nSaved to udl/hybrid_rl_results.json")


if __name__ == "__main__":
    main()
