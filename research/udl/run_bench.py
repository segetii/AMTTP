"""
run_bench.py — Full benchmark: 8 ODDS datasets × UDL methods + baselines
=========================================================================
Run from: c:/amttp/research/udl/
Usage:    python run_bench.py [--datasets mamm shuttle ...] [--out results/bench.json]
"""
import sys, json, time, argparse, warnings
import numpy as np
sys.path.insert(0, "c:/amttp/research/udl")
warnings.filterwarnings("ignore")

from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM
from sklearn.covariance import EllipticEnvelope
from sklearn.neighbors import KNeighborsClassifier
from copy import deepcopy

from udl.compare_sota import load_all_datasets, REAL_DATASETS
from udl.pipeline import UDLPipeline
from udl.rank_fusion import RankFusionPipeline
from udl.hybrid_pipeline import HybridPipeline
from udl.meta_fusion import MetaFusionPipeline, default_operators
from udl.experimental_spectra import PhaseCurveSpectrum
from udl.spectra import RankOrderSpectrum
from udl.new_spectra import TopologicalSpectrum, KernelRKHSSpectrum

# ── Helpers ────────────────────────────────────────────────────────────────

def cov_at_k(scores, y, k_frac):
    """Fraction of true anomalies in top-k% of scores."""
    anom_idx = np.where(y == 1)[0]
    if len(anom_idx) == 0:
        return 0.0
    thresh = np.percentile(scores, 100.0 * (1.0 - k_frac))
    return float(np.sum(scores[anom_idx] >= thresh)) / len(anom_idx)


def run_udl(builder_fn, X_tr, X_te, y_tr, y_te, top_k):
    try:
        t0 = time.time()
        pipe = builder_fn()
        pipe.fit(X_tr, y_tr)
        s = pipe.score(X_te)
        auc = float(roc_auc_score(y_te, s))
        cov = cov_at_k(s, y_te, top_k)
        return {"auc": auc, "cov": cov, "time_s": round(time.time()-t0, 1), "err": ""}
    except Exception as e:
        return {"auc": 0.0, "cov": 0.0, "time_s": 0, "err": str(e)[:120]}


def run_baseline(name, X_tr, X_te, y_tr, y_te, top_k):
    try:
        t0 = time.time()
        if name == "IsolationForest":
            m = IsolationForest(n_estimators=200, contamination="auto", random_state=42)
            m.fit(X_tr)
            s = -m.score_samples(X_te)
        elif name == "LOF":
            m = LocalOutlierFactor(n_neighbors=20, novelty=True)
            m.fit(X_tr)
            s = -m.score_samples(X_te)
        elif name == "OneClassSVM":
            m = OneClassSVM(kernel="rbf", nu=0.05)
            m.fit(X_tr[y_tr == 0])
            s = -m.score_samples(X_te)
        elif name == "EllipticEnvelope":
            try:
                m = EllipticEnvelope(contamination=max(0.01, y_tr.mean()), random_state=42)
                m.fit(X_tr[y_tr == 0])
                s = -m.score_samples(X_te)
            except Exception:
                return {"auc": 0.0, "cov": 0.0, "time_s": 0, "err": "EllipticEnvelope failed (singular)"}
        elif name == "kNN":
            from sklearn.neighbors import NearestNeighbors
            nn = NearestNeighbors(n_neighbors=10)
            nn.fit(X_tr[y_tr == 0])
            dist, _ = nn.kneighbors(X_te)
            s = dist.mean(axis=1)
        elif name == "ECOD":
            try:
                from pyod.models.ecod import ECOD
                m = ECOD()
                m.fit(X_tr)
                s = m.decision_function(X_te)
            except ImportError:
                return {"auc": 0.0, "cov": 0.0, "time_s": 0, "err": "pyod not installed"}
        else:
            return {"auc": 0.0, "cov": 0.0, "time_s": 0, "err": f"unknown baseline {name}"}

        auc = float(roc_auc_score(y_te, s))
        cov = cov_at_k(s, y_te, top_k)
        return {"auc": auc, "cov": cov, "time_s": round(time.time()-t0, 1), "err": ""}
    except Exception as e:
        return {"auc": 0.0, "cov": 0.0, "time_s": 0, "err": str(e)[:120]}


# ── Lean 5-op stack ─────────────────────────────────────────────────────────
OPS_4 = lambda: [
    ("phase", PhaseCurveSpectrum()),
    ("topo",  TopologicalSpectrum(k=15)),
    ("kernel",KernelRKHSSpectrum()),
    ("rank",  RankOrderSpectrum()),
]

# ── Main ────────────────────────────────────────────────────────────────────

def bench_dataset(ds_name, X, y):
    print(f"\n{'─'*60}")
    print(f"  {ds_name.upper()}  n={len(y)}  d={X.shape[1]}  "
          f"anom%={100*y.mean():.1f}%")
    print(f"{'─'*60}")

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=42
    )
    anom_rate = float(y_te.mean())
    top_k = min(max(anom_rate * 2, 0.05), 0.30)
    results = {}

    # ── UDL methods ──────────────────────────────────────────────────────
    udl_methods = {
        "UDL-Hybrid":    lambda: HybridPipeline(operators=deepcopy(OPS_4()), mode='auto'),
        "UDL-RankFuse":  lambda: RankFusionPipeline(operators=deepcopy(OPS_4()), fusion='mean'),
        "UDL-Fisher":    lambda: UDLPipeline(operators=deepcopy(OPS_4()),
                                              centroid_method='auto',
                                              projection_method='fisher'),
        "UDL-Meta":      lambda: MetaFusionPipeline(operators=default_operators(),
                                                     strategies=['fisher','fusion','quadsurf'],
                                                     verbose=False),
        "MDN-unsup":     lambda: RankFusionPipeline(operators=deepcopy(OPS_4()),
                                                     fusion='mean'),  # no labels passed
    }

    for mname, builder in udl_methods.items():
        # MDN variant is unsupervised: fit without labels
        use_y = None if mname == "MDN-unsup" else y_tr
        try:
            t0 = time.time()
            pipe = builder()
            pipe.fit(X_tr, use_y)
            s = pipe.score(X_te)
            auc = float(roc_auc_score(y_te, s))
            cov = cov_at_k(s, y_te, top_k)
            results[mname] = {"auc": auc, "cov": cov,
                               "time_s": round(time.time()-t0, 1), "err": ""}
        except Exception as e:
            results[mname] = {"auc": 0.0, "cov": 0.0, "time_s": 0,
                               "err": str(e)[:120]}
        r = results[mname]
        tag = f"  [{r['err'][:60]}]" if r['err'] else ""
        print(f"  {mname:<16s}  AUC={r['auc']:.4f}  Cov={100*r['cov']:4.0f}%"
              f"  t={r['time_s']}s{tag}")

    # ── Baselines ─────────────────────────────────────────────────────────
    baselines = ["IsolationForest", "LOF", "OneClassSVM",
                 "EllipticEnvelope", "kNN", "ECOD"]
    for bname in baselines:
        results[bname] = run_baseline(bname, X_tr, X_te, y_tr, y_te, top_k)
        r = results[bname]
        tag = f"  [{r['err'][:60]}]" if r['err'] else ""
        print(f"  {bname:<16s}  AUC={r['auc']:.4f}  Cov={100*r['cov']:4.0f}%"
              f"  t={r['time_s']}s{tag}")

    return results


def print_summary(all_results, datasets):
    udl_cols  = ["UDL-Hybrid", "UDL-RankFuse", "UDL-Fisher", "UDL-Meta", "MDN-unsup"]
    base_cols = ["IsolationForest", "LOF", "OneClassSVM",
                 "EllipticEnvelope", "kNN", "ECOD"]
    all_methods = udl_cols + base_cols
    short = {d: d[:7] for d in datasets}

    print(f"\n\n{'='*110}")
    print("  FULL BENCHMARK SUMMARY  (AUC | Coverage)")
    print(f"{'='*110}")
    hdr = f"  {'Method':<17s}"
    for d in datasets:
        hdr += f"  {short[d]:^14s}"
    hdr += f"  {'mAUC':>6s}  {'mCov':>5s}"
    print(hdr); print("  " + "─"*108)

    for m in all_methods:
        row = f"  {m:<17s}"
        aucs, covs = [], []
        for d in datasets:
            r = all_results.get(d, {}).get(m, {"auc": 0.0, "cov": 0.0})
            row += f"  {r['auc']:5.3f}/{100*r['cov']:4.0f}%  "
            if r['auc'] > 0:
                aucs.append(r['auc']); covs.append(r['cov'])
        ma = np.mean(aucs) if aucs else 0.0
        mc = np.mean(covs) if covs else 0.0
        row += f"  {ma:6.4f}  {100*mc:4.0f}%"
        print(row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", nargs="*", default=None,
                        help="Subset of datasets to run (default: all 8)")
    parser.add_argument("--out", default="results/bench_8ds.json")
    args = parser.parse_args()

    datasets = args.datasets or REAL_DATASETS
    print(f"Loading {len(datasets)} datasets: {datasets}")

    all_data = load_all_datasets(subset=datasets)
    all_results = {}

    for ds_name in datasets:
        X, y = all_data[ds_name]
        all_results[ds_name] = bench_dataset(ds_name, X, y)

    print_summary(all_results, datasets)

    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved → {args.out}")


if __name__ == "__main__":
    main()
