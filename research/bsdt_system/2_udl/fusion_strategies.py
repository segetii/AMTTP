"""
Test different fusion strategies for preserving per-sample coverage:
  - Mean rank: average of rank-normalized scores
  - Max rank: maximum rank-normalized score across operators
  - Top-2 mean: average of top-2 rank-normalized scores per sample
  - Fisher pipeline: standard UDL Fisher projection

Key question: which fusion preserves the unique detections
that individual operators make?
"""
import numpy as np
import sys, os, copy, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from udl.compare_sota import load_all_datasets
from udl.pipeline import UDLPipeline

from udl.experimental_spectra import (
    FourierBasisSpectrum, BSplineBasisSpectrum,
    WaveletBasisSpectrum, LegendreBasisSpectrum,
    PhaseCurveSpectrum,
)
from udl.spectra import (
    StatisticalSpectrum, SpectralSpectrum,
    GeometricSpectrum, ExponentialSpectrum,
    ReconstructionSpectrum, RankOrderSpectrum,
)
from udl.new_spectra import (
    TopologicalSpectrum, KernelRKHSSpectrum,
)


def rank_normalize(s):
    return s.argsort().argsort() / (len(s) - 1)


def solo_score(ops_list, X_train, X_test, y_train):
    try:
        pipe = UDLPipeline(
            operators=copy.deepcopy(ops_list),
            centroid_method='auto',
            projection_method='fisher',
        )
        pipe.fit(X_train, y_train)
        return pipe.score(X_test)
    except:
        return None


def coverage_at_k(scores, y_test, top_k_pct):
    """Fraction of true anomalies caught in top-k% of scores."""
    anom_idx = np.where(y_test == 1)[0]
    threshold = np.percentile(scores, 100 * (1 - top_k_pct))
    caught = np.sum(scores[anom_idx] >= threshold)
    return caught / len(anom_idx) if len(anom_idx) > 0 else 0


# Coverage stacks to test
STACKS = {
    "Phase+Topo+Rank": {
        "Phase": [("phase", PhaseCurveSpectrum())],
        "Topo": [("topo", TopologicalSpectrum(k=15))],
        "Rank": [("rank", RankOrderSpectrum())],
    },
    "Phase+Topo+Kernel+Rank": {
        "Phase": [("phase", PhaseCurveSpectrum())],
        "Topo": [("topo", TopologicalSpectrum(k=15))],
        "Kernel": [("kernel", KernelRKHSSpectrum())],
        "Rank": [("rank", RankOrderSpectrum())],
    },
    "Phase+Topo+Rank+Radar": {
        "Phase": [("phase", PhaseCurveSpectrum())],
        "Topo": [("topo", TopologicalSpectrum(k=15))],
        "Rank": [("rank", RankOrderSpectrum())],
        "Radar": [("radar", PhaseCurveSpectrum())],
    },
    "Phase+Topo+Kernel+Rank+Radar": {
        "Phase": [("phase", PhaseCurveSpectrum())],
        "Topo": [("topo", TopologicalSpectrum(k=15))],
        "Kernel": [("kernel", KernelRKHSSpectrum())],
        "Rank": [("rank", RankOrderSpectrum())],
        "Radar": [("radar", PhaseCurveSpectrum())],
    },
    "CombA+Phase": {
        "Fourier": [("fourier", FourierBasisSpectrum(n_coeffs=8))],
        "BSpline": [("bspline", BSplineBasisSpectrum(n_basis=6))],
        "Wavelet": [("wavelet", WaveletBasisSpectrum(max_levels=4))],
        "Legendre": [("legendre", LegendreBasisSpectrum(n_degree=6))],
        "Phase": [("phase", PhaseCurveSpectrum())],
    },
}


def main():
    datasets = load_all_datasets()
    ds_order = [d for d in ["synthetic", "mimic", "mammography", "shuttle", "pendigits"]
                if d in datasets]

    # Fusion modes
    FUSE_MODES = {
        "mean_rank": lambda ranks: np.mean(ranks, axis=0),
        "max_rank": lambda ranks: np.max(ranks, axis=0),
        "top2_mean": lambda ranks: np.sort(ranks, axis=0)[-min(2, len(ranks)):].mean(axis=0),
        "softmax_rank": lambda ranks: np.log(np.sum(np.exp(ranks * 5), axis=0)),  # smooth max
    }

    print("=" * 130)
    print("  FUSION STRATEGY COMPARISON: AUC + COVERAGE")
    print("  (Coverage = fraction of true anomalies in top-k% of scores)")
    print("=" * 130)

    big_results = {}

    for stack_name, operators in STACKS.items():
        print(f"\n{'='*130}")
        print(f"  STACK: {stack_name}  ({len(operators)} operators)")
        print(f"{'='*130}")

        stack_results = {}

        for ds_name in ds_order:
            X, y = datasets[ds_name]
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.3, stratify=y, random_state=42
            )
            anom_rate = y_test.mean()
            top_k = min(max(anom_rate * 2, 0.05), 0.30)

            # Get per-operator solo scores
            op_scores = {}
            for op_name, op_spec in operators.items():
                s = solo_score(copy.deepcopy(op_spec), X_train, X_test, y_train)
                if s is not None:
                    op_scores[op_name] = s
                    op_auc = roc_auc_score(y_test, s)
                    op_cov = coverage_at_k(s, y_test, top_k)

            if not op_scores:
                continue

            # Test each fusion mode
            ranks = np.array([rank_normalize(s) for s in op_scores.values()])

            ds_results = {}
            print(f"\n  {ds_name} (n_test={len(y_test)}, n_anom={int(y_test.sum())}, top_k={top_k:.1%}):")

            for fuse_name, fuse_fn in FUSE_MODES.items():
                fused = fuse_fn(ranks)
                auc = roc_auc_score(y_test, fused)
                cov = coverage_at_k(fused, y_test, top_k)
                ds_results[fuse_name] = {"auc": auc, "cov": cov}
                print(f"    {fuse_name:<15s}  AUC={auc:.4f}  Coverage={cov:.1%}")

            # Also test Fisher pipeline
            all_ops = []
            for op_spec in operators.values():
                all_ops.extend(copy.deepcopy(op_spec))
            fisher_scores = solo_score(all_ops, X_train, X_test, y_train)
            if fisher_scores is not None:
                auc = roc_auc_score(y_test, fisher_scores)
                cov = coverage_at_k(fisher_scores, y_test, top_k)
                ds_results["fisher"] = {"auc": auc, "cov": cov}
                print(f"    {'fisher':<15s}  AUC={auc:.4f}  Coverage={cov:.1%}")

            # Per-operator individual coverage for reference
            print(f"    --- per-operator solo ---")
            for op_name, s in op_scores.items():
                auc = roc_auc_score(y_test, s)
                cov = coverage_at_k(s, y_test, top_k)
                print(f"    {op_name:<15s}  AUC={auc:.4f}  Coverage={cov:.1%}")

            # Union coverage (theoretical max)
            anom_idx = np.where(y_test == 1)[0]
            caught_union = set()
            for s in op_scores.values():
                threshold = np.percentile(s, 100 * (1 - top_k))
                for i, idx in enumerate(anom_idx):
                    if s[idx] >= threshold:
                        caught_union.add(i)
            union_cov = len(caught_union) / len(anom_idx) if len(anom_idx) > 0 else 0
            print(f"    {'UNION (max)':<15s}         --  Coverage={union_cov:.1%}  ({len(caught_union)}/{len(anom_idx)})")

            stack_results[ds_name] = ds_results

        big_results[stack_name] = stack_results

    # Final summary
    print(f"\n\n{'='*130}")
    print("  SUMMARY: Mean Coverage across datasets by fusion strategy")
    print(f"{'='*130}")
    print(f"  {'Stack':<35s}  {'mean_rank':>10s}  {'max_rank':>10s}  {'top2_mean':>10s}  {'softmax':>10s}  {'fisher':>10s}")
    print("-" * 100)
    for stack_name, results in big_results.items():
        row = f"  {stack_name:<35s}"
        for fuse_name in ["mean_rank", "max_rank", "top2_mean", "softmax_rank", "fisher"]:
            covs = []
            for ds_name in ds_order:
                if ds_name in results and fuse_name in results[ds_name]:
                    covs.append(results[ds_name][fuse_name]["cov"])
            if covs:
                row += f"  {np.mean(covs):>9.1%}"
            else:
                row += f"  {'--':>10s}"
        print(row)

    print(f"\n  {'Stack':<35s}  {'mean_rank':>10s}  {'max_rank':>10s}  {'top2_mean':>10s}  {'softmax':>10s}  {'fisher':>10s}")
    print(f"  {'(MIN coverage / worst dataset)':}")
    print("-" * 100)
    for stack_name, results in big_results.items():
        row = f"  {stack_name:<35s}"
        for fuse_name in ["mean_rank", "max_rank", "top2_mean", "softmax_rank", "fisher"]:
            covs = []
            for ds_name in ds_order:
                if ds_name in results and fuse_name in results[ds_name]:
                    covs.append(results[ds_name][fuse_name]["cov"])
            if covs:
                row += f"  {min(covs):>9.1%}"
            else:
                row += f"  {'--':>10s}"
        print(row)

    # AUC summary
    print(f"\n  {'Stack':<35s}  {'mean_rank':>10s}  {'max_rank':>10s}  {'top2_mean':>10s}  {'softmax':>10s}  {'fisher':>10s}")
    print(f"  {'(MEAN AUC)':}")
    print("-" * 100)
    for stack_name, results in big_results.items():
        row = f"  {stack_name:<35s}"
        for fuse_name in ["mean_rank", "max_rank", "top2_mean", "softmax_rank", "fisher"]:
            aucs = []
            for ds_name in ds_order:
                if ds_name in results and fuse_name in results[ds_name]:
                    aucs.append(results[ds_name][fuse_name]["auc"])
            if aucs:
                row += f"  {np.mean(aucs):>9.4f}"
            else:
                row += f"  {'--':>10s}"
        print(row)


if __name__ == "__main__":
    main()
