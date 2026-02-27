"""Evaluation: Per-operator solo AUC + full stacks.
Shows which individual operators contribute and where."""
import numpy as np
import time
import sys
sys.path.insert(0, ".")

from udl.compare_sota import load_all_datasets, evaluate_scores
from udl.spectra import (
    StatisticalSpectrum, ChaosSpectrum, SpectralSpectrum,
    GeometricSpectrum, ExponentialSpectrum,
)
from udl.experimental_spectra import PhaseCurveSpectrum
from udl.pipeline import UDLPipeline


def main():
    datasets = load_all_datasets()

    # Solo operators to compare
    solo_ops = {
        "Chaos (old)":   lambda: [("chaos", ChaosSpectrum())],
        "Phase (new)":   lambda: [("phase", PhaseCurveSpectrum())],
        "Statistical":   lambda: [("stat", StatisticalSpectrum())],
        "Spectral":      lambda: [("freq", SpectralSpectrum())],
        "Geometric":     lambda: [("geom", GeometricSpectrum())],
        "Exponential":   lambda: [("exp", ExponentialSpectrum(alpha=1.0))],
    }

    # Full stacks
    from udl.compare_sota import get_original_operators, get_tabular_operators, get_signal_operators
    full_stacks = {
        "5laws-old":  get_original_operators,
        "StackT":     get_tabular_operators,
        "StackS":     get_signal_operators,
    }

    ds_order = ["synthetic", "mimic", "mammography", "shuttle", "pendigits"]
    all_results = {}

    for ds_name, (X, y) in datasets.items():
        print(f"\n=== {ds_name} (n={len(y)}, m={X.shape[1]}) ===")
        rng = np.random.RandomState(42)
        idx = rng.permutation(len(y))
        split = int(0.6 * len(y))
        X_train, X_test = X[idx[:split]], X[idx[split:]]
        y_train, y_test = y[idx[:split]], y[idx[split:]]

        print("  --- Solo operators ---")
        for name, ops_fn in solo_ops.items():
            t0 = time.time()
            try:
                ops = ops_fn()
                pipe = UDLPipeline(operators=ops, centroid_method="auto",
                                   projection_method="fisher")
                pipe.fit(X_train, y_train)
                scores = pipe.score(X_test)
                metrics = evaluate_scores(scores, y_test)
                elapsed = time.time() - t0
                auc = metrics["auc"]
                print(f"    {name:<16s} AUC={auc:.4f}  ({elapsed:.1f}s)")
                key = f"Solo-{name}"
                if key not in all_results:
                    all_results[key] = {}
                all_results[key][ds_name] = auc
            except Exception as e:
                print(f"    {name:<16s} ERROR: {e}")

        print("  --- Full stacks ---")
        for name, ops_fn in full_stacks.items():
            t0 = time.time()
            try:
                ops = ops_fn()
                pipe = UDLPipeline(operators=ops, centroid_method="auto",
                                   projection_method="fisher")
                pipe.fit(X_train, y_train)
                scores = pipe.score(X_test)
                metrics = evaluate_scores(scores, y_test)
                elapsed = time.time() - t0
                auc = metrics["auc"]
                print(f"    {name:<16s} AUC={auc:.4f}  ({elapsed:.1f}s)")
                if name not in all_results:
                    all_results[name] = {}
                all_results[name][ds_name] = auc
            except Exception as e:
                print(f"    {name:<16s} ERROR: {e}")

    # Summary
    print(f"\n{'='*80}")
    print("SOLO OPERATOR COMPARISON (head-to-head)")
    print(f"{'='*80}")
    header = f"{'Operator':<20s}" + "".join(f"{d:>13s}" for d in ds_order) + f"{'Mean':>10s}"
    print(header)
    print("-" * len(header))
    for name in solo_ops:
        key = f"Solo-{name}"
        row = f"{name:<20s}"
        vals = []
        for d in ds_order:
            v = all_results.get(key, {}).get(d, float("nan"))
            vals.append(v)
            row += f"{v:>13.4f}"
        row += f"{np.nanmean(vals):>10.4f}"
        print(row)

    print(f"\n{'='*80}")
    print("FULL STACK COMPARISON")
    print(f"{'='*80}")
    header = f"{'Stack':<20s}" + "".join(f"{d:>13s}" for d in ds_order) + f"{'Mean':>10s}"
    print(header)
    print("-" * len(header))
    for name in full_stacks:
        row = f"{name:<20s}"
        vals = []
        for d in ds_order:
            v = all_results.get(name, {}).get(d, float("nan"))
            vals.append(v)
            row += f"{v:>13.4f}"
        row += f"{np.nanmean(vals):>10.4f}"
        print(row)

    # Delta
    print(f"\n{'='*80}")
    print("PHASE vs CHAOS (delta)")
    print(f"{'='*80}")
    for d in ds_order:
        phase = all_results.get("Solo-Phase (new)", {}).get(d, float("nan"))
        chaos = all_results.get("Solo-Chaos (old)", {}).get(d, float("nan"))
        delta = phase - chaos if not (np.isnan(phase) or np.isnan(chaos)) else float("nan")
        winner = "PHASE" if delta > 0 else ("CHAOS" if delta < 0 else "TIE")
        print(f"  {d:<15s}  Phase={phase:.4f}  Chaos={chaos:.4f}  Δ={delta:+.4f}  → {winner}")


if __name__ == "__main__":
    main()
