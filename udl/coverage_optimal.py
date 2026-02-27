"""
Coverage-Optimal Stack Builder
================================
Build stacks based on COMPLEMENTARY COVERAGE, not mean AUC.
For each dataset, measure: what fraction of detectable anomalies
does this stack catch? Then pick the stack that maximizes
minimum coverage across all datasets.
"""
import numpy as np
import sys, os, copy, json, itertools
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from udl.compare_sota import load_all_datasets, evaluate_scores
from udl.pipeline import UDLPipeline

from udl.experimental_spectra import (
    FourierBasisSpectrum, BSplineBasisSpectrum,
    WaveletBasisSpectrum, LegendreBasisSpectrum,
    PhaseCurveSpectrum, GramEigenSpectrum,
    PolarSpectrum, RadarPolygonSpectrum,
)
from udl.spectra import (
    StatisticalSpectrum, SpectralSpectrum,
    GeometricSpectrum, ExponentialSpectrum,
    ReconstructionSpectrum, RankOrderSpectrum,
)
from udl.new_spectra import (
    GraphNeighborhoodSpectrum, TopologicalSpectrum,
    DependencyCopulaSpectrum, KernelRKHSSpectrum,
)


ALL_OPS = {
    "Stat":      lambda: [("stat", StatisticalSpectrum())],
    "Spectral":  lambda: [("freq", SpectralSpectrum())],
    "Geom":      lambda: [("geom", GeometricSpectrum())],
    "Exp":       lambda: [("exp", ExponentialSpectrum(alpha=1.0))],
    "Recon":     lambda: [("recon", ReconstructionSpectrum())],
    "Rank":      lambda: [("rank", RankOrderSpectrum())],
    "Fourier":   lambda: [("fourier", FourierBasisSpectrum(n_coeffs=8))],
    "BSpline":   lambda: [("bspline", BSplineBasisSpectrum(n_basis=6))],
    "Wavelet":   lambda: [("wavelet", WaveletBasisSpectrum(max_levels=4))],
    "Legendre":  lambda: [("legendre", LegendreBasisSpectrum(n_degree=6))],
    "Phase":     lambda: [("phase", PhaseCurveSpectrum())],
    "Gram":      lambda: [("gram", GramEigenSpectrum())],
    "Polar":     lambda: [("polar", PolarSpectrum())],
    "Radar":     lambda: [("radar", RadarPolygonSpectrum())],
    "Topo":      lambda: [("topo", TopologicalSpectrum(k=15))],
    "Dep":       lambda: [("dep", DependencyCopulaSpectrum())],
    "Kernel":    lambda: [("kernel", KernelRKHSSpectrum())],
}


def get_scores(ops_list, X_train, X_test, y_train):
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


def detection_set(scores, y_test, top_k_pct):
    if scores is None:
        return set()
    anomaly_indices = np.where(y_test == 1)[0]
    threshold = np.percentile(scores, 100 * (1 - top_k_pct))
    return {i for i, idx in enumerate(anomaly_indices) if scores[idx] >= threshold}


def main():
    datasets = load_all_datasets()
    ds_order = [d for d in ["synthetic", "mimic", "mammography", "shuttle", "pendigits"]
                if d in datasets]

    # ── Phase 1: Collect per-operator detection sets ──
    print("=" * 100)
    print("  COLLECTING PER-OPERATOR DETECTION SETS")
    print("=" * 100)

    # {ds_name: {op_name: set_of_detected_anomaly_indices}}
    all_detections = {}
    all_scores = {}  # {ds_name: {op_name: scores_array}}
    splits = {}
    all_detectable = {}  # {ds_name: set of anomalies detected by ANY operator}

    for ds_name in ds_order:
        X, y = datasets[ds_name]
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=42
        )
        splits[ds_name] = (X_train, X_test, y_train, y_test)
        n_anom = int(y_test.sum())
        anom_rate = y_test.mean()
        top_k = min(max(anom_rate * 2, 0.05), 0.30)

        all_detections[ds_name] = {}
        all_scores[ds_name] = {}
        for op_name, op_fn in ALL_OPS.items():
            scores = get_scores(op_fn(), X_train, X_test, y_train)
            if scores is not None:
                det = detection_set(scores, y_test, top_k)
                all_detections[ds_name][op_name] = det
                all_scores[ds_name][op_name] = scores
                auc = roc_auc_score(y_test, scores)
                print(f"  {ds_name:<14s} {op_name:<10s} AUC={auc:.4f} detects {len(det)}/{n_anom}")

        all_detectable[ds_name] = set()
        for det in all_detections[ds_name].values():
            all_detectable[ds_name] |= det

    # ── Phase 2: Cross-dataset complementarity matrix ──
    print(f"\n{'='*100}")
    print("  CROSS-DATASET COMPLEMENTARITY")
    print(f"{'='*100}")

    op_names = list(ALL_OPS.keys())

    # For each pair of operators, compute union coverage on EACH dataset
    print(f"\n  Per-operator coverage fraction (of detectable anomalies):")
    for op in op_names:
        coverages = []
        for ds in ds_order:
            det = all_detections[ds].get(op, set())
            total = len(all_detectable[ds])
            coverages.append(len(det) / total if total > 0 else 0)
        avg = np.mean(coverages)
        min_c = np.min(coverages)
        ds_str = "  ".join(f"{c:.2f}" for c in coverages)
        print(f"    {op:<10s}  [{ds_str}]  avg={avg:.3f} min={min_c:.3f}")

    # ── Phase 3: Score-rank combination (per sample) ──
    # Instead of just using Fisher on a stack, combine at the SCORE level
    # Average the rank-normalized scores from different operators
    print(f"\n{'='*100}")
    print("  SCORE-LEVEL COMBINATION (rank-average fusion)")
    print(f"{'='*100}")

    def rank_normalize(scores):
        """Convert scores to percentile ranks [0,1]."""
        order = scores.argsort().argsort()
        return order / (len(order) - 1)

    def fuse_scores(op_list, ds_name):
        """Fuse by averaging rank-normalized scores."""
        ranked = []
        for op in op_list:
            s = all_scores[ds_name].get(op)
            if s is not None:
                ranked.append(rank_normalize(s))
        if not ranked:
            return None
        return np.mean(ranked, axis=0)

    # Test many combos via score fusion (much faster than re-running pipelines)
    combos_to_test = {
        # Solo references
        "Phase": ["Phase"],
        "Wavelet": ["Wavelet"],
        "Topo": ["Topo"],
        # Pairs — coverage-motivated
        "Phase+Topo": ["Phase", "Topo"],
        "Phase+Kernel": ["Phase", "Kernel"],
        "Wavelet+Stat": ["Wavelet", "Stat"],
        "Phase+Stat": ["Phase", "Stat"],
        "Wavelet+Topo": ["Wavelet", "Topo"],
        "Polar+Stat": ["Polar", "Stat"],
        "Topo+Kernel": ["Topo", "Kernel"],
        # Triples
        "Phase+Topo+Kernel": ["Phase", "Topo", "Kernel"],
        "Phase+Topo+Stat": ["Phase", "Topo", "Stat"],
        "Phase+Topo+Rank": ["Phase", "Topo", "Rank"],
        "Wavelet+Topo+Stat": ["Wavelet", "Topo", "Stat"],
        "Phase+Kernel+Stat": ["Phase", "Kernel", "Stat"],
        "Phase+Kernel+Rank": ["Phase", "Kernel", "Rank"],
        "Phase+Radar+Kernel": ["Phase", "Radar", "Kernel"],
        # Quads
        "Phase+Topo+Kernel+Stat": ["Phase", "Topo", "Kernel", "Stat"],
        "Phase+Topo+Kernel+Rank": ["Phase", "Topo", "Kernel", "Rank"],
        "Phase+Topo+Rank+Radar": ["Phase", "Topo", "Rank", "Radar"],
        # Set-cover motivated (mammography optimized)
        "Phase+Topo+Kernel+Rank+Radar": ["Phase", "Topo", "Kernel", "Rank", "Radar"],
        # CombA + uniqueness operators
        "CombA-fuse": ["Fourier", "BSpline", "Wavelet", "Legendre"],
        "CombA+Phase-fuse": ["Fourier", "BSpline", "Wavelet", "Legendre", "Phase"],
        "CombA+Phase+Kernel-fuse": ["Fourier", "BSpline", "Wavelet", "Legendre", "Phase", "Kernel"],
        "CombA+Phase+Topo-fuse": ["Fourier", "BSpline", "Wavelet", "Legendre", "Phase", "Topo"],
        "CombA+Phase+Topo+Kernel-fuse": ["Fourier", "BSpline", "Wavelet", "Legendre", "Phase", "Topo", "Kernel"],
        "CombA+Topo+Kernel-fuse": ["Fourier", "BSpline", "Wavelet", "Legendre", "Topo", "Kernel"],
        # All strong operators
        "All-strong": ["Phase", "Wavelet", "Topo", "Kernel", "Polar", "Radar", "Stat"],
    }

    combo_results = {}
    for combo_name, ops in combos_to_test.items():
        ds_aucs = {}
        ds_coverages = {}
        for ds_name in ds_order:
            y_test = splits[ds_name][3]
            fused = fuse_scores(ops, ds_name)
            if fused is not None:
                auc = roc_auc_score(y_test, fused)
                ds_aucs[ds_name] = auc
                # Coverage
                anom_rate = y_test.mean()
                top_k = min(max(anom_rate * 2, 0.05), 0.30)
                det = detection_set(fused, y_test, top_k)
                total = len(all_detectable[ds_name])
                ds_coverages[ds_name] = len(det) / total if total > 0 else 0

        mean_auc = np.mean(list(ds_aucs.values())) if ds_aucs else 0
        min_cov = min(ds_coverages.values()) if ds_coverages else 0
        mean_cov = np.mean(list(ds_coverages.values())) if ds_coverages else 0
        combo_results[combo_name] = {
            "aucs": ds_aucs, "coverages": ds_coverages,
            "mean_auc": mean_auc, "min_cov": min_cov, "mean_cov": mean_cov,
            "n_ops": len(ops), "ops": ops,
        }

    # ── Leaderboard by coverage ──
    print(f"\n  LEADERBOARD — sorted by MEAN COVERAGE (fraction of detectable anomalies)")
    header = f"{'#':<4s} {'Combo':<35s} {'#':>3s}" + "".join(f"{d[:8]:>10s}" for d in ds_order) + f"{'mCov':>8s} {'minCov':>8s} {'mAUC':>8s}"
    print(f"  {header}")
    print(f"  {'-' * len(header)}")

    sorted_by_cov = sorted(combo_results.keys(),
                           key=lambda k: combo_results[k]["mean_cov"], reverse=True)
    for rank, name in enumerate(sorted_by_cov, 1):
        r = combo_results[name]
        row = f"{rank:<4d} {name:<35s} {r['n_ops']:>3d}"
        for d in ds_order:
            row += f"{r['coverages'].get(d, 0):>10.3f}"
        row += f"{r['mean_cov']:>8.3f} {r['min_cov']:>8.3f} {r['mean_auc']:>8.4f}"
        print(f"  {row}")

    # ── Now build the ACTUAL stacks (pipeline, not score-fusion) for top candidates ──
    print(f"\n{'='*100}")
    print("  ACTUAL PIPELINE EVALUATION (Fisher projection, not score fusion)")
    print(f"{'='*100}")

    # Pick top-5 from score fusion + key baselines
    top_candidates = sorted_by_cov[:8]
    # Always include CombA baseline and CombA+Phase
    for must_have in ["CombA-fuse", "CombA+Phase-fuse"]:
        if must_have not in top_candidates:
            top_candidates.append(must_have)

    for combo_name in top_candidates:
        ops = combo_results[combo_name]["ops"]
        # Build actual operator list
        actual_ops = []
        for op_name in ops:
            actual_ops.extend(ALL_OPS[op_name]())

        # Run through UDL pipeline
        ds_aucs = {}
        ds_coverages = {}
        for ds_name in ds_order:
            X_train, X_test, y_train, y_test = splits[ds_name]
            scores = get_scores(actual_ops, X_train, X_test, y_train)
            if scores is not None:
                auc = roc_auc_score(y_test, scores)
                ds_aucs[ds_name] = auc
                anom_rate = y_test.mean()
                top_k = min(max(anom_rate * 2, 0.05), 0.30)
                det = detection_set(scores, y_test, top_k)
                total = len(all_detectable[ds_name])
                ds_coverages[ds_name] = len(det) / total if total > 0 else 0

        mean_auc = np.mean(list(ds_aucs.values())) if ds_aucs else 0
        mean_cov = np.mean(list(ds_coverages.values())) if ds_coverages else 0
        min_cov = min(ds_coverages.values()) if ds_coverages else 0

        auc_str = "  ".join(f"{ds_aucs.get(d, 0):.4f}" for d in ds_order)
        cov_str = "  ".join(f"{ds_coverages.get(d, 0):.3f}" for d in ds_order)
        print(f"  {combo_name:<35s}")
        print(f"    AUC: [{auc_str}]  mean={mean_auc:.4f}")
        print(f"    COV: [{cov_str}]  mean={mean_cov:.3f} min={min_cov:.3f}")
        print()

    # Save
    out = os.path.join(os.path.dirname(__file__), "coverage_optimal.json")
    with open(out, 'w') as f:
        json.dump({k: {kk: vv for kk, vv in v.items() if kk != "scores"}
                   for k, v in combo_results.items()}, f, indent=2, default=str)
    print(f"  Saved to {out}")


if __name__ == "__main__":
    main()
