"""
New Operator Evaluation: Solo + Incremental Stacking
=====================================================
1. Test each of the 6 new operators solo
2. Take the best existing stack (CombinedA = 0.961 mean AUC)
3. Incrementally add operators in order of solo performance
4. Report the optimal stack

Uses same protocol as compare_sota.py: 70/30 split, seed=42,
Fisher projection, semi-supervised.
"""
import numpy as np
import sys, os, copy, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

from udl.compare_sota import load_all_datasets, evaluate_scores
from udl.pipeline import UDLPipeline

# Existing best spectra
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

# New operators
from udl.new_spectra import (
    GraphNeighborhoodSpectrum,
    DensityRatioSpectrum,
    TopologicalSpectrum,
    DependencyCopulaSpectrum,
    CompressibilitySpectrum,
    KernelRKHSSpectrum,
)


def run_single(ops_list, X_train, X_test, y_train, y_test):
    """Run UDL with given operator list, return AUC or None."""
    try:
        pipe = UDLPipeline(
            operators=copy.deepcopy(ops_list),
            centroid_method='auto',
            projection_method='fisher',
        )
        pipe.fit(X_train, y_train)
        scores = pipe.score(X_test)
        return evaluate_scores(scores, y_test)["auc"]
    except Exception as e:
        print(f"      ERROR: {e}")
        return None


def main():
    print("=" * 90)
    print("  NEW OPERATOR SOLO + INCREMENTAL STACKING EVALUATION")
    print("=" * 90)

    datasets = load_all_datasets()
    ds_order = [d for d in ["synthetic", "mimic", "mammography", "shuttle", "pendigits"]
                if d in datasets]
    print(f"  Datasets: {ds_order}\n")

    # ── Define new solo operators ──
    new_ops = {
        "Graph/kNN":       lambda: [("graph", GraphNeighborhoodSpectrum(k=10))],
        "DensityRatio":    lambda: [("density", DensityRatioSpectrum())],
        "Topological":     lambda: [("topo", TopologicalSpectrum(k=15))],
        "Dependency":      lambda: [("dep", DependencyCopulaSpectrum())],
        "Compressibility": lambda: [("compress", CompressibilitySpectrum())],
        "KernelRKHS":      lambda: [("kernel", KernelRKHSSpectrum())],
    }

    # ── Define existing best operators for comparison ──
    existing_solo = {
        "Phase(B3)":    lambda: [("phase", PhaseCurveSpectrum())],
        "Geometric":    lambda: [("geom", GeometricSpectrum())],
        "Spectral":     lambda: [("freq", SpectralSpectrum())],
        "Statistical":  lambda: [("stat", StatisticalSpectrum())],
    }

    # ── Base stack: CombinedA (best existing, mean 0.961) ──
    def make_base_stack():
        return [
            ("A1_fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("A2_bspline", BSplineBasisSpectrum(n_basis=6)),
            ("A3_wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("A4_legendre", LegendreBasisSpectrum(n_degree=6)),
        ]

    # ═══════════════════════════════════════════════════════
    # PHASE 1: SOLO EVALUATION
    # ═══════════════════════════════════════════════════════
    print("=" * 90)
    print("  PHASE 1: SOLO OPERATOR AUC")
    print("=" * 90)

    solo_results = {}  # name -> {ds: auc}

    # Prepare data splits (same for all)
    splits = {}
    for ds_name in ds_order:
        X, y = datasets[ds_name]
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=42
        )
        splits[ds_name] = (X_train, X_test, y_train, y_test)

    all_solo = {**existing_solo, **new_ops}
    for op_name, op_fn in all_solo.items():
        solo_results[op_name] = {}
        for ds_name in ds_order:
            X_train, X_test, y_train, y_test = splits[ds_name]
            t0 = time.time()
            auc = run_single(op_fn(), X_train, X_test, y_train, y_test)
            elapsed = time.time() - t0
            solo_results[op_name][ds_name] = auc
            status = f"{auc:.4f}" if auc is not None else "FAIL"
            print(f"  {op_name:<18s} {ds_name:<14s} AUC={status}  ({elapsed:.1f}s)")

    # Print solo summary table
    print(f"\n{'=' * 90}")
    print("  SOLO SUMMARY — sorted by mean AUC")
    print(f"{'=' * 90}")
    header = f"{'Operator':<20s}" + "".join(f"{d:>14s}" for d in ds_order) + f"{'Mean':>10s}"
    print(header)
    print("-" * len(header))

    # Compute means and sort
    solo_means = {}
    for name, results in solo_results.items():
        vals = [results.get(d) for d in ds_order]
        vals = [v for v in vals if v is not None]
        solo_means[name] = np.mean(vals) if vals else 0.0

    for name in sorted(solo_means, key=lambda n: solo_means[n], reverse=True):
        row = f"{name:<20s}"
        for d in ds_order:
            v = solo_results[name].get(d)
            row += f"{v:>14.4f}" if v is not None else f"{'FAIL':>14s}"
        row += f"{solo_means[name]:>10.4f}"
        print(row)

    # ═══════════════════════════════════════════════════════
    # PHASE 2: BASE STACK PERFORMANCE
    # ═══════════════════════════════════════════════════════
    print(f"\n{'=' * 90}")
    print("  PHASE 2: BASE STACK (CombinedA) PERFORMANCE")
    print(f"{'=' * 90}")

    base_results = {}
    for ds_name in ds_order:
        X_train, X_test, y_train, y_test = splits[ds_name]
        auc = run_single(make_base_stack(), X_train, X_test, y_train, y_test)
        base_results[ds_name] = auc
        print(f"  CombinedA  {ds_name:<14s}  AUC={auc:.4f}")

    base_mean = np.mean([v for v in base_results.values() if v is not None])
    print(f"  CombinedA  {'MEAN':<14s}  AUC={base_mean:.4f}")

    # ═══════════════════════════════════════════════════════
    # PHASE 3: INCREMENTAL STACKING
    # ═══════════════════════════════════════════════════════
    print(f"\n{'=' * 90}")
    print("  PHASE 3: INCREMENTAL STACKING (greedy-add to CombinedA)")
    print(f"{'=' * 90}")

    # Sort new operators by solo mean AUC (best first)
    new_sorted = sorted(new_ops.keys(), key=lambda n: solo_means.get(n, 0), reverse=True)
    print(f"  Add order (by solo mean): {new_sorted}\n")

    # Also include some existing strong operators that aren't in CombinedA
    extra_candidates = {
        "Phase(B3)":    lambda: ("phase", PhaseCurveSpectrum()),
        "Geometric":    lambda: ("geom", GeometricSpectrum()),
        "Recon":        lambda: ("recon", ReconstructionSpectrum()),
        "RankOrder":    lambda: ("rank", RankOrderSpectrum()),
    }

    # Build candidate pool: new ops + extra existing
    candidate_pool = {}
    for name in new_sorted:
        def _make(n=name):
            ops = new_ops[n]()
            return ops[0]  # (tag, operator)
        candidate_pool[name] = _make
    for name, fn in extra_candidates.items():
        candidate_pool[name] = fn

    current_stack_names = ["CombinedA-base"]
    current_stack_fn = make_base_stack
    best_mean = base_mean

    stacking_log = [{
        "stack": "CombinedA-base",
        "mean_auc": base_mean,
        "per_ds": dict(base_results),
    }]

    # Greedy: try adding each remaining candidate, pick the one that
    # improves mean AUC the most
    remaining = list(candidate_pool.keys())
    added_ops = []  # list of (name, tag, operator_fn)

    while remaining:
        best_candidate = None
        best_candidate_mean = best_mean
        best_candidate_results = None

        for cand_name in remaining:
            # Build stack: base + already added + this candidate
            trial_ops = make_base_stack()
            for _, prev_fn in added_ops:
                trial_ops.append(prev_fn())
            trial_ops.append(candidate_pool[cand_name]())

            trial_results = {}
            for ds_name in ds_order:
                X_train, X_test, y_train, y_test = splits[ds_name]
                auc = run_single(trial_ops, X_train, X_test, y_train, y_test)
                trial_results[ds_name] = auc

            trial_vals = [v for v in trial_results.values() if v is not None]
            trial_mean = np.mean(trial_vals) if trial_vals else 0.0

            delta = trial_mean - best_mean
            print(f"    + {cand_name:<18s}  mean={trial_mean:.4f}  Δ={delta:+.4f}")

            if trial_mean > best_candidate_mean:
                best_candidate = cand_name
                best_candidate_mean = trial_mean
                best_candidate_results = trial_results

        if best_candidate is None or best_candidate_mean <= best_mean + 0.0001:
            print(f"\n  ⛔ No candidate improves mean AUC. Stopping.")
            break

        # Accept this candidate
        best_mean = best_candidate_mean
        added_ops.append((best_candidate, candidate_pool[best_candidate]))
        remaining.remove(best_candidate)
        current_stack_names.append(best_candidate)

        stacking_log.append({
            "added": best_candidate,
            "stack": " + ".join(current_stack_names),
            "mean_auc": best_mean,
            "per_ds": dict(best_candidate_results),
        })

        print(f"\n  ✅ ADDED: {best_candidate}  →  mean={best_mean:.4f}")
        print(f"     Stack: {' + '.join(current_stack_names)}")
        for d in ds_order:
            v = best_candidate_results.get(d, 0)
            b = base_results.get(d, 0)
            print(f"       {d:<14s}  {v:.4f}  (Δ from base: {v-b:+.4f})")
        print()

    # ═══════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ═══════════════════════════════════════════════════════
    print(f"\n{'=' * 90}")
    print("  FINAL OPTIMAL STACK")
    print(f"{'=' * 90}")
    print(f"  Stack: {' + '.join(current_stack_names)}")
    print(f"  Mean AUC: {best_mean:.4f}")
    print(f"\n  Stacking progression:")
    for entry in stacking_log:
        print(f"    {entry['stack']:<50s}  mean={entry['mean_auc']:.4f}")

    # Save results
    results_file = os.path.join(os.path.dirname(__file__), "new_ops_evaluation.json")
    with open(results_file, 'w') as f:
        json.dump({
            "solo_results": solo_results,
            "solo_means": solo_means,
            "base_stack_results": base_results,
            "stacking_log": stacking_log,
            "final_stack": current_stack_names,
            "final_mean_auc": best_mean,
        }, f, indent=2, default=str)
    print(f"\n  Results saved to {results_file}")


if __name__ == "__main__":
    main()
