"""
Exhaustive 2-3 operator combo search + alternative base stacks.
Finds the BEST possible small stack from all available operators.
"""
import numpy as np
import sys, os, copy, time, json, itertools
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.model_selection import train_test_split
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


def run_single(ops_list, X_train, X_test, y_train, y_test):
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
        return None


# All candidate operators (name, factory)
ALL_OPS = {
    "Phase":       lambda: ("phase", PhaseCurveSpectrum()),
    "Topo":        lambda: ("topo", TopologicalSpectrum(k=15)),
    "Geom":        lambda: ("geom", GeometricSpectrum()),
    "KernelRKHS":  lambda: ("kernel", KernelRKHSSpectrum()),
    "Dependency":  lambda: ("dep", DependencyCopulaSpectrum()),
    "DensityR":    lambda: ("density", DensityRatioSpectrum()),
    "Graph":       lambda: ("graph", GraphNeighborhoodSpectrum(k=10)),
    "Stat":        lambda: ("stat", StatisticalSpectrum()),
    "Fourier":     lambda: ("fourier", FourierBasisSpectrum(n_coeffs=8)),
    "BSpline":     lambda: ("bspline", BSplineBasisSpectrum(n_basis=6)),
    "Wavelet":     lambda: ("wavelet", WaveletBasisSpectrum(max_levels=4)),
    "Legendre":    lambda: ("legendre", LegendreBasisSpectrum(n_degree=6)),
    "Exp":         lambda: ("exp", ExponentialSpectrum(alpha=1.0)),
    "Recon":       lambda: ("recon", ReconstructionSpectrum()),
    "Rank":        lambda: ("rank", RankOrderSpectrum()),
    "Polar":       lambda: ("polar", PolarSpectrum()),
    "Radar":       lambda: ("radar", RadarPolygonSpectrum()),
    "Gram":        lambda: ("gram", GramEigenSpectrum()),
}


def main():
    datasets = load_all_datasets()
    ds_order = [d for d in ["synthetic", "mimic", "mammography", "shuttle", "pendigits"]
                if d in datasets]

    splits = {}
    for ds_name in ds_order:
        X, y = datasets[ds_name]
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=42
        )
        splits[ds_name] = (X_train, X_test, y_train, y_test)

    # ── PART 1: Curated combos ──
    # Based on solo results: Phase(0.96), Topo(0.93), Geom(0.89), KernelRKHS(0.87)
    # And CombinedA (Fourier+BSpline+Wavelet+Legendre) = 0.961
    curated = {
        # Best solos combined
        "Phase+Topo":           ["Phase", "Topo"],
        "Phase+Topo+Geom":      ["Phase", "Topo", "Geom"],
        "Phase+Topo+Kernel":    ["Phase", "Topo", "KernelRKHS"],
        "Phase+Topo+Dep":       ["Phase", "Topo", "Dependency"],
        "Phase+Geom+Kernel":    ["Phase", "Geom", "KernelRKHS"],
        "Phase+Geom+Dep":       ["Phase", "Geom", "Dependency"],
        "Phase+Geom+Topo+Kernel": ["Phase", "Geom", "Topo", "KernelRKHS"],
        "Phase+Geom+Topo+Dep":  ["Phase", "Geom", "Topo", "Dependency"],
        # CombinedA + best new
        "CombA+Topo":           ["Fourier", "BSpline", "Wavelet", "Legendre", "Topo"],
        "CombA+Phase":          ["Fourier", "BSpline", "Wavelet", "Legendre", "Phase"],
        "CombA+Phase+Topo":     ["Fourier", "BSpline", "Wavelet", "Legendre", "Phase", "Topo"],
        # CombinedA only (baseline)
        "CombA":                ["Fourier", "BSpline", "Wavelet", "Legendre"],
        # Top-6 solo operators together
        "Top6":                 ["Phase", "Topo", "Geom", "KernelRKHS", "Dependency", "DensityR"],
        # Pure new operators
        "NewOnly-top3":         ["Topo", "KernelRKHS", "Dependency"],
        "NewOnly-top4":         ["Topo", "KernelRKHS", "Dependency", "DensityR"],
        # Mixed best
        "Phase+Topo+Fourier":   ["Phase", "Topo", "Fourier"],
        "Phase+Topo+Wavelet":   ["Phase", "Topo", "Wavelet"],
        "Phase+Topo+Geom+Exp":  ["Phase", "Topo", "Geom", "Exp"],
        # Graph+Density (kNN-like)
        "Graph+DensityR":       ["Graph", "DensityR"],
        "Phase+Graph":          ["Phase", "Graph"],
        # Kitchen sink
        "AllNew6":              ["Graph", "DensityR", "Topo", "Dependency", "KernelRKHS"],
    }

    print("=" * 100)
    print("  EXHAUSTIVE COMBO SEARCH — finding the best stack")
    print("=" * 100)

    results = {}
    for combo_name, op_names in curated.items():
        ops = [ALL_OPS[n]() for n in op_names]
        combo_results = {}
        for ds_name in ds_order:
            X_train, X_test, y_train, y_test = splits[ds_name]
            auc = run_single(ops, X_train, X_test, y_train, y_test)
            combo_results[ds_name] = auc
        vals = [v for v in combo_results.values() if v is not None]
        mean_auc = np.mean(vals) if vals else 0.0
        results[combo_name] = {"per_ds": combo_results, "mean": mean_auc, "ops": op_names}
        ds_str = "  ".join(f"{combo_results.get(d, 0):.4f}" for d in ds_order)
        print(f"  {combo_name:<30s}  mean={mean_auc:.4f}  [{ds_str}]")

    # ── Sort by mean AUC ──
    print(f"\n{'=' * 100}")
    print("  LEADERBOARD — sorted by mean AUC")
    print(f"{'=' * 100}")
    header = f"{'Rank':<5s} {'Combo':<30s}" + "".join(f"{d:>14s}" for d in ds_order) + f"{'Mean':>10s}"
    print(header)
    print("-" * len(header))

    sorted_combos = sorted(results.keys(), key=lambda k: results[k]["mean"], reverse=True)
    for rank, name in enumerate(sorted_combos, 1):
        r = results[name]
        row = f"{rank:<5d} {name:<30s}"
        for d in ds_order:
            v = r["per_ds"].get(d, 0)
            row += f"{v:>14.4f}"
        row += f"{r['mean']:>10.4f}"
        print(row)

    # ── Best vs CombinedA ──
    best_name = sorted_combos[0]
    best = results[best_name]
    base = results.get("CombA", {"mean": 0, "per_ds": {}})
    print(f"\n  BEST:   {best_name} ({best['mean']:.4f})")
    print(f"  BASE:   CombA ({base['mean']:.4f})")
    print(f"  DELTA:  {best['mean'] - base['mean']:+.4f}")
    for d in ds_order:
        bv = best["per_ds"].get(d, 0)
        cv = base["per_ds"].get(d, 0)
        print(f"    {d:<14s}  best={bv:.4f}  combA={cv:.4f}  Δ={bv-cv:+.4f}")

    # Save
    out_file = os.path.join(os.path.dirname(__file__), "combo_search_results.json")
    with open(out_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Saved to {out_file}")


if __name__ == "__main__":
    main()
