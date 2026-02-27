"""
Operator Uniqueness Probe
==========================
For each operator, record PER-SAMPLE anomaly scores on test data.
Then answer:
  1. Which anomalies does each operator detect that others MISS?
  2. Which operators are redundant (detecting the same anomalies)?
  3. What is the minimum set of operators that covers ALL detectable anomalies?

This is NOT about mean AUC. It's about complementary coverage.
"""
import numpy as np
import sys, os, copy, json
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
    GraphNeighborhoodSpectrum, DensityRatioSpectrum,
    TopologicalSpectrum, DependencyCopulaSpectrum,
    CompressibilitySpectrum, KernelRKHSSpectrum,
)


def get_per_sample_scores(ops_list, X_train, X_test, y_train):
    """Return per-sample anomaly scores for test points, or None on failure."""
    try:
        pipe = UDLPipeline(
            operators=copy.deepcopy(ops_list),
            centroid_method='auto',
            projection_method='fisher',
        )
        pipe.fit(X_train, y_train)
        scores = pipe.score(X_test)
        return scores
    except Exception as e:
        print(f"      ERROR: {e}")
        return None


def detected_set(scores, y_test, top_k_pct=0.20):
    """
    Which TRUE anomalies does this operator detect?
    Uses top-k% scoring threshold (rank-based, not absolute).
    Returns set of indices into the ANOMALY-ONLY subset.
    """
    if scores is None:
        return set()
    
    anomaly_mask = y_test == 1
    anomaly_indices = np.where(anomaly_mask)[0]
    n_anomalies = len(anomaly_indices)
    
    # Rank all test samples by score (descending = more anomalous)
    threshold = np.percentile(scores, 100 * (1 - top_k_pct))
    
    # Which anomalies have score above threshold?
    detected = set()
    for i, idx in enumerate(anomaly_indices):
        if scores[idx] >= threshold:
            detected.add(i)  # index into anomaly-only list
    
    return detected


def main():
    datasets = load_all_datasets()
    ds_order = [d for d in ["synthetic", "mimic", "mammography", "shuttle", "pendigits"]
                if d in datasets]

    # ALL operators we have
    all_ops = {
        # Existing
        "Statistical":  lambda: [("stat", StatisticalSpectrum())],
        "Spectral":     lambda: [("freq", SpectralSpectrum())],
        "Geometric":    lambda: [("geom", GeometricSpectrum())],
        "Exponential":  lambda: [("exp", ExponentialSpectrum(alpha=1.0))],
        "Recon":        lambda: [("recon", ReconstructionSpectrum())],
        "RankOrder":    lambda: [("rank", RankOrderSpectrum())],
        # Experimental
        "Fourier":      lambda: [("fourier", FourierBasisSpectrum(n_coeffs=8))],
        "BSpline":      lambda: [("bspline", BSplineBasisSpectrum(n_basis=6))],
        "Wavelet":      lambda: [("wavelet", WaveletBasisSpectrum(max_levels=4))],
        "Legendre":     lambda: [("legendre", LegendreBasisSpectrum(n_degree=6))],
        "Phase":        lambda: [("phase", PhaseCurveSpectrum())],
        "GramEigen":    lambda: [("gram", GramEigenSpectrum())],
        "Polar":        lambda: [("polar", PolarSpectrum())],
        "Radar":        lambda: [("radar", RadarPolygonSpectrum())],
        # New operators
        "Graph":        lambda: [("graph", GraphNeighborhoodSpectrum(k=10))],
        "Topological":  lambda: [("topo", TopologicalSpectrum(k=15))],
        "Dependency":   lambda: [("dep", DependencyCopulaSpectrum())],
        "KernelRKHS":   lambda: [("kernel", KernelRKHSSpectrum())],
        # Skip DensityRatio and Compressibility - too slow / poor
    }

    for ds_name in ds_order:
        X, y = datasets[ds_name]
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=42
        )
        n_anomalies = int(y_test.sum())
        n_total = len(y_test)

        print(f"\n{'='*100}")
        print(f"  DATASET: {ds_name.upper()} — {n_total} test samples, {n_anomalies} anomalies")
        print(f"{'='*100}")

        # ── Step 1: Get per-sample scores from each operator ──
        op_scores = {}
        op_detections = {}
        for name, fn in all_ops.items():
            scores = get_per_sample_scores(fn(), X_train, X_test, y_train)
            if scores is not None:
                auc = roc_auc_score(y_test, scores)
                op_scores[name] = scores
                # Use adaptive threshold: top-(anomaly_rate * 2) of scores
                anom_rate = y_test.mean()
                top_k = min(max(anom_rate * 2, 0.05), 0.30)
                det = detected_set(scores, y_test, top_k_pct=top_k)
                op_detections[name] = det
                print(f"  {name:<16s}  AUC={auc:.4f}  detects {len(det)}/{n_anomalies} anomalies ({100*len(det)/n_anomalies:.0f}%)")
            else:
                print(f"  {name:<16s}  FAILED")

        # ── Step 2: UNIQUENESS ANALYSIS ──
        print(f"\n  --- UNIQUENESS: anomalies detected by ONE operator and NO other ---")
        
        # For each operator, find anomalies it detects that NO other detects
        all_detected = set()
        for det in op_detections.values():
            all_detected |= det
        
        uniqueness = {}
        for name, det in op_detections.items():
            others = set()
            for other_name, other_det in op_detections.items():
                if other_name != name:
                    others |= other_det
            unique = det - others
            uniqueness[name] = unique

        # Sort by unique contribution
        sorted_by_unique = sorted(uniqueness.items(), key=lambda x: len(x[1]), reverse=True)
        for name, unique in sorted_by_unique:
            n_det = len(op_detections[name])
            n_uniq = len(unique)
            if n_uniq > 0:
                print(f"    {name:<16s}  detects {n_det:>3d}, UNIQUE: {n_uniq:>3d}  "
                      f"({100*n_uniq/n_anomalies:.1f}% of all anomalies)")
            else:
                print(f"    {name:<16s}  detects {n_det:>3d}, unique: 0  (fully redundant)")

        never_detected = set(range(n_anomalies)) - all_detected
        print(f"\n    NEVER DETECTED by any operator: {len(never_detected)}/{n_anomalies} "
              f"({100*len(never_detected)/n_anomalies:.1f}%)")

        # ── Step 3: OVERLAP MATRIX ──
        print(f"\n  --- OVERLAP MATRIX (Jaccard similarity) ---")
        op_names = list(op_detections.keys())
        n_ops = len(op_names)
        
        # Find pairs with HIGH overlap (redundant) and LOW overlap (complementary)
        pairs = []
        for i in range(n_ops):
            for j in range(i+1, n_ops):
                a = op_detections[op_names[i]]
                b = op_detections[op_names[j]]
                if len(a | b) == 0:
                    jaccard = 0
                else:
                    jaccard = len(a & b) / len(a | b)
                union_coverage = len(a | b) / n_anomalies if n_anomalies > 0 else 0
                pairs.append((op_names[i], op_names[j], jaccard, union_coverage, len(a & b), len(a | b)))

        # Most complementary pairs (low Jaccard, high union coverage)
        print(f"\n    TOP COMPLEMENTARY PAIRS (low overlap, high combined coverage):")
        comp_score = [(n1, n2, j, u, inter, union) for n1, n2, j, u, inter, union in pairs]
        comp_score.sort(key=lambda x: x[3] - x[2], reverse=True)  # high coverage - low overlap
        for n1, n2, j, u, inter, union in comp_score[:15]:
            print(f"      {n1:<14s} + {n2:<14s}  overlap={j:.2f}  union_cover={100*u:.0f}%  "
                  f"({inter} shared, {union} total)")

        # Most redundant pairs
        print(f"\n    MOST REDUNDANT PAIRS (high overlap):")
        pairs.sort(key=lambda x: x[2], reverse=True)
        for n1, n2, j, u, inter, union in pairs[:10]:
            print(f"      {n1:<14s} ≈ {n2:<14s}  overlap={j:.2f}  "
                  f"({inter} shared of {union} total)")

        # ── Step 4: GREEDY SET COVER ──
        print(f"\n  --- GREEDY SET COVER: minimum operators to detect ALL detectable anomalies ---")
        remaining_anomalies = all_detected.copy()
        selected = []
        remaining_ops = dict(op_detections)
        
        while remaining_anomalies and remaining_ops:
            # Pick operator that covers the most remaining anomalies
            best_name = max(remaining_ops.keys(), 
                          key=lambda n: len(remaining_ops[n] & remaining_anomalies))
            best_covers = remaining_ops[best_name] & remaining_anomalies
            if len(best_covers) == 0:
                break
            selected.append((best_name, len(best_covers)))
            remaining_anomalies -= best_covers
            del remaining_ops[best_name]
            covered_so_far = all_detected - remaining_anomalies
            print(f"    + {best_name:<16s}  covers {len(best_covers):>3d} new  "
                  f"(total: {len(covered_so_far)}/{len(all_detected)})")

        print(f"\n    MINIMUM COVER SET: {[s[0] for s in selected]}")
        print(f"    Covers {len(all_detected)}/{n_anomalies} detectable anomalies with {len(selected)} operators")

        # ── Step 5: Per-anomaly heatmap (which operators see which anomalies) ──
        if n_anomalies <= 100:
            print(f"\n  --- PER-ANOMALY DETECTION MAP (rows=anomalies, cols=operators) ---")
            # Only show operators that detect at least 1 anomaly
            active_ops = [n for n in op_names if len(op_detections[n]) > 0]
            header = f"  {'anom#':<7s}" + "".join(f"{n[:6]:>7s}" for n in active_ops) + f"  {'#det':>5s}"
            print(header)
            print("  " + "-" * (len(header) - 2))
            
            anomaly_indices = np.where(y_test == 1)[0]
            for ai in range(n_anomalies):
                row = f"  {ai:<7d}"
                n_det = 0
                for n in active_ops:
                    if ai in op_detections[n]:
                        row += f"{'  ████':>7s}"
                        n_det += 1
                    else:
                        row += f"{'     ·':>7s}"
                row += f"  {n_det:>5d}"
                print(row)

        # ── Step 6: Score correlation analysis ──
        print(f"\n  --- SCORE CORRELATION (Spearman rank on anomaly scores) ---")
        from scipy.stats import spearmanr
        
        # Only among anomalous samples
        anomaly_mask = y_test == 1
        corr_ops = list(op_scores.keys())
        n_c = len(corr_ops)
        corr_matrix = np.zeros((n_c, n_c))
        
        for i in range(n_c):
            for j in range(n_c):
                s1 = op_scores[corr_ops[i]][anomaly_mask]
                s2 = op_scores[corr_ops[j]][anomaly_mask]
                r, _ = spearmanr(s1, s2)
                corr_matrix[i, j] = r

        # Show most UNcorrelated pairs (different views)
        uncorr_pairs = []
        for i in range(n_c):
            for j in range(i+1, n_c):
                uncorr_pairs.append((corr_ops[i], corr_ops[j], corr_matrix[i,j]))
        uncorr_pairs.sort(key=lambda x: x[2])

        print(f"    MOST UNCORRELATED (different anomaly rankings):")
        for n1, n2, r in uncorr_pairs[:12]:
            print(f"      {n1:<14s} vs {n2:<14s}  ρ={r:+.3f}")
        
        print(f"\n    MOST CORRELATED (redundant views):")
        for n1, n2, r in uncorr_pairs[-8:]:
            print(f"      {n1:<14s} ≈ {n2:<14s}  ρ={r:+.3f}")


if __name__ == "__main__":
    main()
