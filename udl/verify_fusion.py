"""
Verify score-fusion achieves real coverage gains.
Run each operator independently, rank-fuse their scores,
and measure actual AUC + detection coverage.
"""
import numpy as np
import sys, os, copy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from udl.compare_sota import load_all_datasets, evaluate_scores
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
    TopologicalSpectrum, DependencyCopulaSpectrum,
    KernelRKHSSpectrum,
)


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


def rank_normalize(s):
    return s.argsort().argsort() / (len(s) - 1)


def detection_set(scores, y_test, top_k_pct):
    if scores is None:
        return set()
    anom_idx = np.where(y_test == 1)[0]
    threshold = np.percentile(scores, 100 * (1 - top_k_pct))
    return {i for i, idx in enumerate(anom_idx) if scores[idx] >= threshold}


def main():
    datasets = load_all_datasets()
    ds_order = [d for d in ["synthetic", "mimic", "mammography", "shuttle", "pendigits"]
                if d in datasets]

    # Stacks to compare
    stacks = {
        # Candidate 1: Coverage-optimal from probe
        "RankFuse:Phase+Topo+Rank+Radar": {
            "ops": {
                "Phase": lambda: [("phase", PhaseCurveSpectrum())],
                "Topo": lambda: [("topo", TopologicalSpectrum(k=15))],
                "Rank": lambda: [("rank", RankOrderSpectrum())],
                "Radar": lambda: [("radar", PhaseCurveSpectrum())],  # placeholder
            },
            "method": "rank_fuse"
        },
        # Candidate 2: Coverage-optimal smaller
        "RankFuse:Phase+Topo+Kernel": {
            "ops": {
                "Phase": lambda: [("phase", PhaseCurveSpectrum())],
                "Topo": lambda: [("topo", TopologicalSpectrum(k=15))],
                "Kernel": lambda: [("kernel", KernelRKHSSpectrum())],
            },
            "method": "rank_fuse"
        },
        # Candidate 3: Score fusion of CombA components + Phase
        "RankFuse:CombA+Phase": {
            "ops": {
                "Fourier": lambda: [("fourier", FourierBasisSpectrum(n_coeffs=8))],
                "BSpline": lambda: [("bspline", BSplineBasisSpectrum(n_basis=6))],
                "Wavelet": lambda: [("wavelet", WaveletBasisSpectrum(max_levels=4))],
                "Legendre": lambda: [("legendre", LegendreBasisSpectrum(n_degree=6))],
                "Phase": lambda: [("phase", PhaseCurveSpectrum())],
            },
            "method": "rank_fuse"
        },
        # Candidate 4: Same CombA+Phase through Fisher pipeline
        "Fisher:CombA+Phase": {
            "ops": {
                "CombA+Phase": lambda: [
                    ("fourier", FourierBasisSpectrum(n_coeffs=8)),
                    ("bspline", BSplineBasisSpectrum(n_basis=6)),
                    ("wavelet", WaveletBasisSpectrum(max_levels=4)),
                    ("legendre", LegendreBasisSpectrum(n_degree=6)),
                    ("phase", PhaseCurveSpectrum()),
                ],
            },
            "method": "fisher"
        },
        # Candidate 5: Best of both worlds — CombA+Phase+Topo+Kernel
        "RankFuse:CombA+Phase+Topo+Kernel": {
            "ops": {
                "Fourier": lambda: [("fourier", FourierBasisSpectrum(n_coeffs=8))],
                "BSpline": lambda: [("bspline", BSplineBasisSpectrum(n_basis=6))],
                "Wavelet": lambda: [("wavelet", WaveletBasisSpectrum(max_levels=4))],
                "Legendre": lambda: [("legendre", LegendreBasisSpectrum(n_degree=6))],
                "Phase": lambda: [("phase", PhaseCurveSpectrum())],
                "Topo": lambda: [("topo", TopologicalSpectrum(k=15))],
                "Kernel": lambda: [("kernel", KernelRKHSSpectrum())],
            },
            "method": "rank_fuse"
        },
        # Candidate 6: Fisher pipeline with Phase+Topo+Kernel
        "Fisher:Phase+Topo+Kernel": {
            "ops": {
                "Phase+Topo+Kernel": lambda: [
                    ("phase", PhaseCurveSpectrum()),
                    ("topo", TopologicalSpectrum(k=15)),
                    ("kernel", KernelRKHSSpectrum()),
                ],
            },
            "method": "fisher"
        },
    }

    print("=" * 120)
    print("  RANK-FUSION vs FISHER PIPELINE: AUC + COVERAGE COMPARISON")
    print("=" * 120)

    all_results = {}
    for stack_name, config in stacks.items():
        print(f"\n  --- {stack_name} ---")
        stack_results = {}
        for ds_name in ds_order:
            X, y = datasets[ds_name]
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.3, stratify=y, random_state=42
            )
            anom_rate = y_test.mean()
            top_k = min(max(anom_rate * 2, 0.05), 0.30)

            if config["method"] == "rank_fuse":
                # Run each operator solo, rank-fuse
                ranked_scores = []
                for op_name, op_fn in config["ops"].items():
                    s = solo_score(op_fn(), X_train, X_test, y_train)
                    if s is not None:
                        ranked_scores.append(rank_normalize(s))
                if ranked_scores:
                    final_scores = np.mean(ranked_scores, axis=0)
                else:
                    final_scores = None
            else:
                # Fisher pipeline (single combined run)
                all_ops = []
                for op_fn in config["ops"].values():
                    all_ops = op_fn()
                final_scores = solo_score(all_ops, X_train, X_test, y_train)

            if final_scores is not None:
                auc = roc_auc_score(y_test, final_scores)
                det = detection_set(final_scores, y_test, top_k)
                # Need all_detectable for coverage fraction
                # Compute from all individual operators
                all_det = set()
                for op_fn in config["ops"].values():
                    s = solo_score(op_fn(), X_train, X_test, y_train)
                    if s is not None:
                        all_det |= detection_set(s, y_test, top_k)

                n_anom = int(y_test.sum())
                cov = len(det) / n_anom if n_anom > 0 else 0
                stack_results[ds_name] = {"auc": auc, "cov": cov, "det": len(det), "n_anom": n_anom}
                print(f"    {ds_name:<14s}  AUC={auc:.4f}  Cover={len(det)}/{n_anom} ({100*cov:.0f}%)")
            else:
                stack_results[ds_name] = {"auc": 0, "cov": 0, "det": 0, "n_anom": 0}
                print(f"    {ds_name:<14s}  FAILED")

        all_results[stack_name] = stack_results

    # Summary
    print(f"\n{'='*120}")
    print("  FINAL COMPARISON")
    print(f"{'='*120}")
    header = f"{'Stack':<40s}" + "".join(f"{'AUC-'+d[:5]:>12s}" for d in ds_order) + f"{'mAUC':>8s}" + "".join(f"{'Cov-'+d[:5]:>12s}" for d in ds_order) + f"{'mCov':>8s}"
    print(header)
    print("-" * len(header))

    for stack_name, results in all_results.items():
        aucs = [results.get(d, {}).get("auc", 0) for d in ds_order]
        covs = [results.get(d, {}).get("cov", 0) for d in ds_order]
        row = f"{stack_name:<40s}"
        for a in aucs:
            row += f"{a:>12.4f}"
        row += f"{np.mean(aucs):>8.4f}"
        for c in covs:
            row += f"{100*c:>11.0f}%"
        row += f"{100*np.mean(covs):>7.0f}%"
        print(row)


if __name__ == "__main__":
    main()
