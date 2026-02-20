"""
Universal Deviation Law — Comprehensive Approach Benchmark
============================================================
Tests ALL candidate law domains (8 experimental + 5 original)
across multiple datasets. Results determine which approaches
become official law domains.

Experiment Design:
  1. Each candidate operator is tested SOLO as the only law domain
  2. Each is tested COMBINED with the original 5 law domains
  3. All-together combinations are tested
  4. Per-dataset and aggregate metrics are reported

Metrics: AUC-ROC, Average Precision, F1
"""

import numpy as np
import time
import sys
import os
import warnings
warnings.filterwarnings("ignore")

# Ensure udl is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, average_precision_score, f1_score

from udl.spectra import (
    StatisticalSpectrum, ChaosSpectrum, SpectralSpectrum,
    GeometricSpectrum, ExponentialSpectrum,
)
from udl.experimental_spectra import (
    FourierBasisSpectrum, BSplineBasisSpectrum,
    WaveletBasisSpectrum, LegendreBasisSpectrum,
    PolarSpectrum, RadarPolygonSpectrum,
    PhaseCurveSpectrum, GramEigenSpectrum,
)
from udl.pipeline import UDLPipeline
from udl.stack import RepresentationStack
from udl.datasets import make_synthetic, make_mimic_anomalies


# ═══════════════════════════════════════════════════════════════════
# DATASET LOADERS (including real-world)
# ═══════════════════════════════════════════════════════════════════

def load_all_datasets():
    """Load all benchmark datasets. Fall back to synthetics if OpenML fails."""
    datasets = {}

    # Always available
    datasets["synthetic"] = make_synthetic()
    datasets["mimic"] = make_mimic_anomalies()

    # Real-world datasets
    try:
        from udl.datasets import load_mammography
        datasets["mammography"] = load_mammography()
    except Exception as e:
    log(f"  [SKIP] mammography: {e}")

    try:
        from udl.datasets import load_shuttle
        X, y = load_shuttle()
        # Subsample for speed
        rng = np.random.RandomState(42)
        idx = rng.choice(len(y), min(5000, len(y)), replace=False)
        datasets["shuttle"] = (X[idx], y[idx])
    except Exception as e:
    log(f"  [SKIP] shuttle: {e}")

    try:
        from udl.datasets import load_pendigits
        datasets["pendigits"] = load_pendigits()
    except Exception as e:
    log(f"  [SKIP] pendigits: {e}")

    return datasets


# ═══════════════════════════════════════════════════════════════════
# OPERATOR REGISTRY
# ═══════════════════════════════════════════════════════════════════

def get_original_operators():
    """The 5 original UDL law domains."""
    return [
        ("stat", StatisticalSpectrum()),
        ("chaos", ChaosSpectrum()),
        ("freq", SpectralSpectrum()),
        ("geom", GeometricSpectrum()),
        ("exp", ExponentialSpectrum(alpha=1.0)),
    ]

def get_experimental_operators():
    """All 8 experimental candidate operators."""
    return {
        # Approach A: Functional Reduction
        "A1_fourier":   ("A1_fourier",   FourierBasisSpectrum(n_coeffs=8)),
        "A2_bspline":   ("A2_bspline",   BSplineBasisSpectrum(n_basis=6)),
        "A3_wavelet":   ("A3_wavelet",   WaveletBasisSpectrum(max_levels=4)),
        "A4_legendre":  ("A4_legendre",  LegendreBasisSpectrum(n_degree=6)),
        # Approach B: Coordinate System
        "B1_polar":     ("B1_polar",     PolarSpectrum()),
        "B2_radar":     ("B2_radar",     RadarPolygonSpectrum()),
        "B3_phase":     ("B3_phase",     PhaseCurveSpectrum()),
        "B4_gram":      ("B4_gram",      GramEigenSpectrum()),
    }


# ═══════════════════════════════════════════════════════════════════
# SINGLE EVALUATION
# ═══════════════════════════════════════════════════════════════════

def evaluate_operators(operators, X, y, name=""):
    """Run UDL pipeline with given operators and return metrics."""
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=42
        )

        pipe = UDLPipeline(operators=operators)
        pipe.fit(X_train, y_train)
        scores = pipe.score(X_test)

        auc = roc_auc_score(y_test, scores)
        ap = average_precision_score(y_test, scores)

        # F1 at optimal threshold
        from sklearn.metrics import precision_recall_curve
        precision, recall, thresholds = precision_recall_curve(y_test, scores)
        f1s = 2 * precision * recall / (precision + recall + 1e-10)
        best_f1 = np.max(f1s)

        return {"auc": auc, "ap": ap, "f1": best_f1, "status": "ok"}

    except Exception as e:
        return {"auc": 0.0, "ap": 0.0, "f1": 0.0, "status": f"FAIL: {e}"}


# ═══════════════════════════════════════════════════════════════════
# MAIN BENCHMARK
# ═══════════════════════════════════════════════════════════════════

_log_file = None

def log(msg=""):
    """Write to log file and optionally stderr for progress."""
    global _log_file
    if _log_file:
        _log_file.write(msg + "\n")
        _log_file.flush()
    # Also print short progress to stderr (ASCII only)
    import sys
    try:
        ascii_msg = msg.encode('ascii', errors='replace').decode('ascii')
        sys.stderr.write(ascii_msg + "\n")
    except Exception:
        pass

def run_benchmark():
    log("=" * 80)
    log("  UNIVERSAL DEVIATION LAW -- COMPREHENSIVE APPROACH BENCHMARK")
    log("=" * 80)
    log()

    # Load datasets
    log("Loading datasets...")
    datasets = load_all_datasets()
    log(f"  Loaded {len(datasets)} datasets: {list(datasets.keys())}")
    log()

    exp_ops = get_experimental_operators()

    # Results storage: results[experiment_name][dataset_name] = metrics dict
    all_results = {}

    # ── EXPERIMENT 1: Baseline (Original 5 laws) ──
    log("─" * 80)
    log("  EXPERIMENT 1: BASELINE — Original 5 Law Domains")
    log("─" * 80)
    baseline_results = {}
    for ds_name, (X, y) in datasets.items():
        ops = get_original_operators()
        metrics = evaluate_operators(ops, X, y, ds_name)
        baseline_results[ds_name] = metrics
    log(f"  {ds_name:15s}  AUC={metrics['auc']:.4f}  AP={metrics['ap']:.4f}  F1={metrics['f1']:.4f}  {metrics['status']}")
    all_results["baseline_5laws"] = baseline_results
    log()

    # ── EXPERIMENT 2: Each experimental operator SOLO ──
    log("─" * 80)
    log("  EXPERIMENT 2: SOLO — Each Candidate Operator Alone")
    log("─" * 80)
    for exp_name, (op_name, op_instance) in exp_ops.items():
    log(f"\n  >> {exp_name}")
        solo_results = {}
        for ds_name, (X, y) in datasets.items():
            # Fresh operator instance for each dataset
            import copy
            fresh_op = copy.deepcopy(op_instance)
            ops = [(op_name, fresh_op)]
            metrics = evaluate_operators(ops, X, y, ds_name)
            solo_results[ds_name] = metrics
            status = "" if metrics["status"] == "ok" else f"  [{metrics['status']}]"
    log(f"     {ds_name:15s}  AUC={metrics['auc']:.4f}  AP={metrics['ap']:.4f}  F1={metrics['f1']:.4f}{status}")
        all_results[f"solo_{exp_name}"] = solo_results
    log()

    # ── EXPERIMENT 3: Each experimental operator ADDED to baseline 5 ──
    log("─" * 80)
    log("  EXPERIMENT 3: AUGMENTED — Baseline 5 + Each Candidate")
    log("─" * 80)
    for exp_name, (op_name, op_instance) in exp_ops.items():
    log(f"\n  >> baseline + {exp_name}")
        aug_results = {}
        for ds_name, (X, y) in datasets.items():
            import copy
            fresh_op = copy.deepcopy(op_instance)
            ops = get_original_operators() + [(op_name, fresh_op)]
            metrics = evaluate_operators(ops, X, y, ds_name)
            aug_results[ds_name] = metrics
            # Compute delta vs baseline
            delta = metrics['auc'] - baseline_results[ds_name]['auc']
            arrow = "▲" if delta > 0.001 else ("▼" if delta < -0.001 else "─")
    log(f"     {ds_name:15s}  AUC={metrics['auc']:.4f} ({arrow}{delta:+.4f})  AP={metrics['ap']:.4f}  F1={metrics['f1']:.4f}")
        all_results[f"aug_{exp_name}"] = aug_results
    log()

    # ── EXPERIMENT 4: Approach A combined (all 4 functional basis) ──
    log("─" * 80)
    log("  EXPERIMENT 4: APPROACH A COMBINED — All Functional Basis Operators")
    log("─" * 80)
    log("  >> A1+A2+A3+A4 solo")
    a_combined_results = {}
    for ds_name, (X, y) in datasets.items():
        ops = [
            ("A1_fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("A2_bspline", BSplineBasisSpectrum(n_basis=6)),
            ("A3_wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("A4_legendre", LegendreBasisSpectrum(n_degree=6)),
        ]
        metrics = evaluate_operators(ops, X, y, ds_name)
        a_combined_results[ds_name] = metrics
    log(f"     {ds_name:15s}  AUC={metrics['auc']:.4f}  AP={metrics['ap']:.4f}  F1={metrics['f1']:.4f}")
    all_results["combined_A"] = a_combined_results

    log("\n  >> Baseline 5 + all A operators")
    a_aug_results = {}
    for ds_name, (X, y) in datasets.items():
        ops = get_original_operators() + [
            ("A1_fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("A2_bspline", BSplineBasisSpectrum(n_basis=6)),
            ("A3_wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("A4_legendre", LegendreBasisSpectrum(n_degree=6)),
        ]
        metrics = evaluate_operators(ops, X, y, ds_name)
        a_aug_results[ds_name] = metrics
        delta = metrics['auc'] - baseline_results[ds_name]['auc']
        arrow = "▲" if delta > 0.001 else ("▼" if delta < -0.001 else "─")
    log(f"     {ds_name:15s}  AUC={metrics['auc']:.4f} ({arrow}{delta:+.4f})  AP={metrics['ap']:.4f}  F1={metrics['f1']:.4f}")
    all_results["aug_all_A"] = a_aug_results
    log()

    # ── EXPERIMENT 5: Approach B combined (all 4 coordinate system) ──
    log("─" * 80)
    log("  EXPERIMENT 5: APPROACH B COMBINED — All Coordinate System Operators")
    log("─" * 80)
    log("  >> B1+B2+B3+B4 solo")
    b_combined_results = {}
    for ds_name, (X, y) in datasets.items():
        ops = [
            ("B1_polar", PolarSpectrum()),
            ("B2_radar", RadarPolygonSpectrum()),
            ("B3_phase", PhaseCurveSpectrum()),
            ("B4_gram", GramEigenSpectrum()),
        ]
        metrics = evaluate_operators(ops, X, y, ds_name)
        b_combined_results[ds_name] = metrics
    log(f"     {ds_name:15s}  AUC={metrics['auc']:.4f}  AP={metrics['ap']:.4f}  F1={metrics['f1']:.4f}")
    all_results["combined_B"] = b_combined_results

    log("\n  >> Baseline 5 + all B operators")
    b_aug_results = {}
    for ds_name, (X, y) in datasets.items():
        ops = get_original_operators() + [
            ("B1_polar", PolarSpectrum()),
            ("B2_radar", RadarPolygonSpectrum()),
            ("B3_phase", PhaseCurveSpectrum()),
            ("B4_gram", GramEigenSpectrum()),
        ]
        metrics = evaluate_operators(ops, X, y, ds_name)
        b_aug_results[ds_name] = metrics
        delta = metrics['auc'] - baseline_results[ds_name]['auc']
        arrow = "▲" if delta > 0.001 else ("▼" if delta < -0.001 else "─")
    log(f"     {ds_name:15s}  AUC={metrics['auc']:.4f} ({arrow}{delta:+.4f})  AP={metrics['ap']:.4f}  F1={metrics['f1']:.4f}")
    all_results["aug_all_B"] = b_aug_results
    log()

    # ── EXPERIMENT 6: GRAND UNIFIED — All 13 operators ──
    log("─" * 80)
    log("  EXPERIMENT 6: GRAND UNIFIED — All 13 Operators (5 original + 4A + 4B)")
    log("─" * 80)
    grand_results = {}
    for ds_name, (X, y) in datasets.items():
        ops = get_original_operators() + [
            ("A1_fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("A2_bspline", BSplineBasisSpectrum(n_basis=6)),
            ("A3_wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("A4_legendre", LegendreBasisSpectrum(n_degree=6)),
            ("B1_polar", PolarSpectrum()),
            ("B2_radar", RadarPolygonSpectrum()),
            ("B3_phase", PhaseCurveSpectrum()),
            ("B4_gram", GramEigenSpectrum()),
        ]
        metrics = evaluate_operators(ops, X, y, ds_name)
        grand_results[ds_name] = metrics
        delta = metrics['auc'] - baseline_results[ds_name]['auc']
        arrow = "▲" if delta > 0.001 else ("▼" if delta < -0.001 else "─")
    log(f"     {ds_name:15s}  AUC={metrics['auc']:.4f} ({arrow}{delta:+.4f})  AP={metrics['ap']:.4f}  F1={metrics['f1']:.4f}")
    all_results["grand_unified"] = grand_results
    log()

    # ═══════════════════════════════════════════════════════════════════
    #  SUMMARY TABLE
    # ═══════════════════════════════════════════════════════════════════
    log("=" * 80)
    log("  SUMMARY: MEAN AUC ACROSS ALL DATASETS")
    log("=" * 80)
    log()
    log(f"  {'Experiment':<35s} {'Mean AUC':>10s} {'Δ vs Base':>10s} {'Verdict':>10s}")
    log("  " + "─" * 70)

    baseline_mean = np.mean([v['auc'] for v in baseline_results.values()])

    ranked = []
    for exp_name, results in sorted(all_results.items()):
        mean_auc = np.mean([v['auc'] for v in results.values()])
        delta = mean_auc - baseline_mean
        if delta > 0.005:
            verdict = "IMPROVE"
        elif delta < -0.005:
            verdict = "WORSE"
        else:
            verdict = "NEUTRAL"
        ranked.append((exp_name, mean_auc, delta, verdict))

    # Sort by mean AUC descending
    ranked.sort(key=lambda x: x[1], reverse=True)

    for exp_name, mean_auc, delta, verdict in ranked:
        marker = "★" if exp_name == "baseline_5laws" else " "
    log(f"  {marker}{exp_name:<34s} {mean_auc:10.4f} {delta:+10.4f} {verdict:>10s}")

    log()
    log("=" * 80)
    log("  SOLO OPERATOR RANKING (discriminative power as standalone law)")
    log("=" * 80)
    log()

    solo_ranks = []
    for exp_name, results in all_results.items():
        if exp_name.startswith("solo_"):
            mean_auc = np.mean([v['auc'] for v in results.values()])
            solo_ranks.append((exp_name.replace("solo_", ""), mean_auc))

    solo_ranks.sort(key=lambda x: x[1], reverse=True)
    log(f"  {'Operator':<25s} {'Mean AUC':>10s} {'Rank':>6s}")
    log("  " + "─" * 45)
    for rank, (name, auc) in enumerate(solo_ranks, 1):
        bar = "█" * int(auc * 30)
    log(f"  {name:<25s} {auc:10.4f} #{rank:>4d}  {bar}")

    log()
    log("=" * 80)
    log("  AUGMENTATION VALUE (Δ AUC when added to baseline)")
    log("=" * 80)
    log()

    aug_ranks = []
    for exp_name, results in all_results.items():
        if exp_name.startswith("aug_") and exp_name not in ("aug_all_A", "aug_all_B"):
            mean_auc = np.mean([v['auc'] for v in results.values()])
            delta = mean_auc - baseline_mean
            aug_ranks.append((exp_name.replace("aug_", ""), mean_auc, delta))

    aug_ranks.sort(key=lambda x: x[2], reverse=True)
    log(f"  {'Operator':<25s} {'AUC':>8s} {'Δ AUC':>10s} {'Verdict':>10s}")
    log("  " + "─" * 55)
    for name, auc, delta in aug_ranks:
        if delta > 0.005:
            verdict = "✓ KEEP"
        elif delta > -0.005:
            verdict = "~ NEUTRAL"
        else:
            verdict = "✗ DROP"
    log(f"  {name:<25s} {auc:8.4f} {delta:+10.4f} {verdict:>10s}")

    # ── Per-dataset winner analysis ──
    log()
    log("=" * 80)
    log("  PER-DATASET ANALYSIS: Which approach wins where?")
    log("=" * 80)

    for ds_name in datasets.keys():
    log(f"\n  {ds_name.upper():}")
        ds_results = []
        for exp_name, results in all_results.items():
            if ds_name in results:
                ds_results.append((exp_name, results[ds_name]['auc']))
        ds_results.sort(key=lambda x: x[1], reverse=True)
        for rank, (name, auc) in enumerate(ds_results[:5], 1):
            marker = "→" if rank == 1 else " "
    log(f"    {marker} #{rank} {name:<35s} AUC={auc:.4f}")

    log()
    log("=" * 80)
    log("  BENCHMARK COMPLETE — Results determine law domain selection")
    log("=" * 80)

    return all_results


if __name__ == "__main__":
    results = run_benchmark()
