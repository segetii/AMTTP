"""Fast combo search — only fast operators, focused on CombA+Phase variations."""
import numpy as np
import sys, os, copy, time, json
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
    TopologicalSpectrum, DependencyCopulaSpectrum,
    KernelRKHSSpectrum, CompressibilitySpectrum,
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
        print(f"      ERROR: {e}")
        return None


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

    # Focused combos around the best finding: CombA+Phase = 0.9661
    combos = {
        "CombA (baseline)": [
            ("fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("bspline", BSplineBasisSpectrum(n_basis=6)),
            ("wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("legendre", LegendreBasisSpectrum(n_degree=6)),
        ],
        "CombA+Phase": [
            ("fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("bspline", BSplineBasisSpectrum(n_basis=6)),
            ("wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("legendre", LegendreBasisSpectrum(n_degree=6)),
            ("phase", PhaseCurveSpectrum()),
        ],
        "CombA+Phase+Geom": [
            ("fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("bspline", BSplineBasisSpectrum(n_basis=6)),
            ("wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("legendre", LegendreBasisSpectrum(n_degree=6)),
            ("phase", PhaseCurveSpectrum()),
            ("geom", GeometricSpectrum()),
        ],
        "CombA+Phase+Kernel": [
            ("fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("bspline", BSplineBasisSpectrum(n_basis=6)),
            ("wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("legendre", LegendreBasisSpectrum(n_degree=6)),
            ("phase", PhaseCurveSpectrum()),
            ("kernel", KernelRKHSSpectrum()),
        ],
        "CombA+Phase+Dep": [
            ("fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("bspline", BSplineBasisSpectrum(n_basis=6)),
            ("wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("legendre", LegendreBasisSpectrum(n_degree=6)),
            ("phase", PhaseCurveSpectrum()),
            ("dep", DependencyCopulaSpectrum()),
        ],
        "CombA+Phase+Exp": [
            ("fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("bspline", BSplineBasisSpectrum(n_basis=6)),
            ("wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("legendre", LegendreBasisSpectrum(n_degree=6)),
            ("phase", PhaseCurveSpectrum()),
            ("exp", ExponentialSpectrum(alpha=1.0)),
        ],
        "CombA+Phase+Stat": [
            ("fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("bspline", BSplineBasisSpectrum(n_basis=6)),
            ("wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("legendre", LegendreBasisSpectrum(n_degree=6)),
            ("phase", PhaseCurveSpectrum()),
            ("stat", StatisticalSpectrum()),
        ],
        "CombA+Phase+Recon": [
            ("fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("bspline", BSplineBasisSpectrum(n_basis=6)),
            ("wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("legendre", LegendreBasisSpectrum(n_degree=6)),
            ("phase", PhaseCurveSpectrum()),
            ("recon", ReconstructionSpectrum()),
        ],
        "CombA+Phase+Rank": [
            ("fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("bspline", BSplineBasisSpectrum(n_basis=6)),
            ("wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("legendre", LegendreBasisSpectrum(n_degree=6)),
            ("phase", PhaseCurveSpectrum()),
            ("rank", RankOrderSpectrum()),
        ],
        "CombA+Phase+Recon+Rank": [
            ("fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("bspline", BSplineBasisSpectrum(n_basis=6)),
            ("wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("legendre", LegendreBasisSpectrum(n_degree=6)),
            ("phase", PhaseCurveSpectrum()),
            ("recon", ReconstructionSpectrum()),
            ("rank", RankOrderSpectrum()),
        ],
        "CombA+Phase+Geom+Recon": [
            ("fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("bspline", BSplineBasisSpectrum(n_basis=6)),
            ("wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("legendre", LegendreBasisSpectrum(n_degree=6)),
            ("phase", PhaseCurveSpectrum()),
            ("geom", GeometricSpectrum()),
            ("recon", ReconstructionSpectrum()),
        ],
        "CombA+Geom": [
            ("fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("bspline", BSplineBasisSpectrum(n_basis=6)),
            ("wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("legendre", LegendreBasisSpectrum(n_degree=6)),
            ("geom", GeometricSpectrum()),
        ],
        "CombA+Exp": [
            ("fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("bspline", BSplineBasisSpectrum(n_basis=6)),
            ("wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("legendre", LegendreBasisSpectrum(n_degree=6)),
            ("exp", ExponentialSpectrum(alpha=1.0)),
        ],
        # Completely different base: Phase+Topo pair
        "Phase+Topo": [
            ("phase", PhaseCurveSpectrum()),
            ("topo", TopologicalSpectrum(k=15)),
        ],
        "Phase+Topo+Kernel": [
            ("phase", PhaseCurveSpectrum()),
            ("topo", TopologicalSpectrum(k=15)),
            ("kernel", KernelRKHSSpectrum()),
        ],
        # Minimal powerful stacks
        "Phase+Geom": [
            ("phase", PhaseCurveSpectrum()),
            ("geom", GeometricSpectrum()),
        ],
        "Phase+Exp": [
            ("phase", PhaseCurveSpectrum()),
            ("exp", ExponentialSpectrum(alpha=1.0)),
        ],
        "Phase+Fourier": [
            ("phase", PhaseCurveSpectrum()),
            ("fourier", FourierBasisSpectrum(n_coeffs=8)),
        ],
        "Phase+Wavelet": [
            ("phase", PhaseCurveSpectrum()),
            ("wavelet", WaveletBasisSpectrum(max_levels=4)),
        ],
    }

    print("=" * 100)
    print("  FOCUSED COMBO SEARCH — variations around CombA+Phase")
    print("=" * 100)

    results = {}
    for combo_name, ops in combos.items():
        combo_results = {}
        t0_total = time.time()
        for ds_name in ds_order:
            X_train, X_test, y_train, y_test = splits[ds_name]
            auc = run_single(ops, X_train, X_test, y_train, y_test)
            combo_results[ds_name] = auc
        elapsed = time.time() - t0_total
        vals = [v for v in combo_results.values() if v is not None]
        mean_auc = np.mean(vals) if vals else 0.0
        results[combo_name] = {"per_ds": combo_results, "mean": mean_auc, "n_ops": len(ops)}
        ds_str = "  ".join(f"{combo_results.get(d, 0):.4f}" for d in ds_order)
        print(f"  {combo_name:<30s}  mean={mean_auc:.4f}  [{ds_str}]  ({elapsed:.1f}s)")

    # Leaderboard
    print(f"\n{'=' * 100}")
    print("  LEADERBOARD — sorted by mean AUC")
    print(f"{'=' * 100}")
    header = f"{'#':<4s} {'Combo':<30s} {'#ops':>5s}" + "".join(f"{d:>14s}" for d in ds_order) + f"{'Mean':>10s}"
    print(header)
    print("-" * len(header))

    sorted_combos = sorted(results.keys(), key=lambda k: results[k]["mean"], reverse=True)
    for rank, name in enumerate(sorted_combos, 1):
        r = results[name]
        row = f"{rank:<4d} {name:<30s} {r['n_ops']:>5d}"
        for d in ds_order:
            v = r["per_ds"].get(d, 0)
            row += f"{v:>14.4f}"
        row += f"{r['mean']:>10.4f}"
        print(row)

    # Compare to KNN baseline
    print(f"\n  REFERENCE: KNN-Distance baseline (from 21-method comparison)")
    print(f"  KNN mean AUC ≈ 0.967 across 5-seed evaluation")

    best_name = sorted_combos[0]
    best = results[best_name]
    print(f"\n  OUR BEST:  {best_name}")
    print(f"  Mean AUC:  {best['mean']:.4f}")
    print(f"  Operators: {best['n_ops']}")

    # Save
    out_file = os.path.join(os.path.dirname(__file__), "combo_search_final.json")
    with open(out_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Saved to {out_file}")


if __name__ == "__main__":
    main()
