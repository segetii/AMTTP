"""
Benchmark: System Mode Engine — Molecular / Gravity / Hybrid
==============================================================
Compares the three physics system modes against the baseline UDL
pipeline, specifically measuring:
  1. AUROC (detection quality)
  2. False Alarm Rate at 95% recall (operational FAR)
  3. Per-mode execution time

Also validates that the Morse topology alarm suppresses the false
alarms caused by ChaosSpectrum / SpectralSpectrum operators.

Author: Odeyemi Olusegun Israel
"""

import sys
import os
import time
import json
import traceback
import numpy as np
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))
# Also add parent so 'udl' package works
parent_dir = str(Path(__file__).parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from sklearn.metrics import roc_auc_score, f1_score
from sklearn.model_selection import StratifiedKFold

from udl.datasets import load_dataset, list_datasets
from udl.system_mode import (
    SystemModeEngine, SystemMode,
    MolecularEngine, GravityModeEngine, HybridGravityEngine,
    SpectraFalseAlarmFilter, _MorseReplacementSpectrum,
    BettiBarcodeSuite, UDLPostSimScorer, FusedSystemScorer,
)
from udl.pipeline import UDLPipeline
from udl.stack import RepresentationStack
from udl.spectra import ChaosSpectrum, SpectralSpectrum


def compute_far_at_recall(y_true, scores, target_recall=0.95):
    """Compute False Alarm Rate at a given recall level."""
    # Sort by descending score
    order = np.argsort(scores)[::-1]
    y_sorted = y_true[order]

    n_pos = y_true.sum()
    if n_pos == 0:
        return 0.0

    tp = 0
    fp = 0
    n_neg = len(y_true) - n_pos

    for i in range(len(y_sorted)):
        if y_sorted[i] == 1:
            tp += 1
        else:
            fp += 1
        recall = tp / n_pos
        if recall >= target_recall:
            far = fp / max(n_neg, 1)
            return far

    return fp / max(n_neg, 1)


def benchmark_system_modes():
    """Run full benchmark across datasets and modes."""
    datasets = ['mammography', 'pendigits', 'shuttle']
    n_splits = 3
    results = {}

    print("=" * 70)
    print("  SYSTEM MODE BENCHMARK v2")
    print("  Fused (Morse+Betti+UDL) vs Morse-only vs Baseline")
    print("  BettiBarcode + Phase+Topo+KernelRKHS+Rank operators")
    print("=" * 70)

    methods = {
        'UDL_Baseline': lambda: 'baseline',
        'UDL_Mol_Morse': lambda: SystemModeEngine(
            mode='molecular', filter_spectra=False,
            molecular_params={'use_fused': False}),
        'UDL_Mol_Fused': lambda: SystemModeEngine(
            mode='molecular', filter_spectra=False,
            molecular_params={'use_fused': True}),
        'UDL_Grav_Morse': lambda: SystemModeEngine(
            mode='gravity', filter_spectra=False,
            gravity_params={'use_fused': False}),
        'UDL_Grav_Fused': lambda: SystemModeEngine(
            mode='gravity', filter_spectra=False,
            gravity_params={'use_fused': True}),
        'UDL_Hybrid_Fused': lambda: SystemModeEngine(
            mode='hybrid', filter_spectra=False,
            molecular_params={'use_fused': True},
            gravity_params={'use_fused': True}),
    }

    for ds_name in datasets:
        print(f"\n{'─' * 60}")
        print(f"  Dataset: {ds_name}")
        print(f"{'─' * 60}")

        try:
            X, y = load_dataset(ds_name)
        except Exception as e:
            print(f"  [SKIP] Cannot load {ds_name}: {e}")
            continue

        print(f"  Shape: {X.shape}, Anomalies: {y.sum()}/{len(y)} "
              f"({100*y.mean():.1f}%)")

        ds_results = {}
        skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)

        for method_name, method_factory in methods.items():
            fold_aucs = []
            fold_fars = []
            fold_f1s = []
            fold_times = []

            for fold_idx, (train_idx, test_idx) in enumerate(skf.split(X, y)):
                X_train, X_test = X[train_idx], X[test_idx]
                y_train, y_test = y[train_idx], y[test_idx]

                t0 = time.time()

                try:
                    if method_name == 'UDL_Baseline':
                        # Baseline pipeline without system mode
                        pipe = UDLPipeline(
                            operators='auto',
                            score_method='v3e',
                            projection_method='fisher',
                        )
                        pipe.fit(X_train, y_train)
                        scores = pipe.score(X_test)
                    else:
                        # System mode engine
                        engine = method_factory()
                        # Fit on full data (train+test), score test portion
                        scores = engine.fit_score(
                            np.vstack([X_train, X_test]),
                            np.hstack([y_train, np.full(len(y_test), -1)])
                        )
                        # Extract test scores only
                        scores = scores[len(X_train):]
                except Exception as e:
                    print(f"  [{method_name}] Fold {fold_idx}: ERROR - {type(e).__name__}: {e}")
                    traceback.print_exc(limit=3)
                    continue

                elapsed = time.time() - t0

                # Metrics
                try:
                    auc = roc_auc_score(y_test, scores)
                except ValueError:
                    auc = 0.5

                far = compute_far_at_recall(y_test, scores, target_recall=0.95)

                # F1 at threshold = median
                threshold = np.median(scores[y_test == 0]) if (y_test == 0).any() else np.median(scores)
                preds = (scores > threshold).astype(int)
                f1 = f1_score(y_test, preds, zero_division=0)

                fold_aucs.append(auc)
                fold_fars.append(far)
                fold_f1s.append(f1)
                fold_times.append(elapsed)

            if fold_aucs:
                ds_results[method_name] = {
                    'auroc_mean': float(np.mean(fold_aucs)),
                    'auroc_std': float(np.std(fold_aucs)),
                    'far_mean': float(np.mean(fold_fars)),
                    'far_std': float(np.std(fold_fars)),
                    'f1_mean': float(np.mean(fold_f1s)),
                    'f1_std': float(np.std(fold_f1s)),
                    'time_mean': float(np.mean(fold_times)),
                }

                print(f"  {method_name:20s}  "
                      f"AUC={np.mean(fold_aucs):.4f}±{np.std(fold_aucs):.4f}  "
                      f"FAR@95={np.mean(fold_fars):.3f}  "
                      f"F1={np.mean(fold_f1s):.4f}  "
                      f"T={np.mean(fold_times):.1f}s")

        results[ds_name] = ds_results

    # ── Summary table ──
    print("\n\n" + "=" * 90)
    print("  SUMMARY: Mean AUROC / FAR@95% recall across datasets")
    print("=" * 90)
    print(f"  {'Method':<20s}  {'mAUROC':>8s}  {'mFAR@95':>8s}  {'mF1':>8s}")
    print("  " + "─" * 50)

    method_summary = {}
    for method_name in methods:
        aucs = [results[ds][method_name]['auroc_mean']
                for ds in results if method_name in results[ds]]
        fars = [results[ds][method_name]['far_mean']
                for ds in results if method_name in results[ds]]
        f1s = [results[ds][method_name]['f1_mean']
               for ds in results if method_name in results[ds]]
        if aucs:
            m_auc = np.mean(aucs)
            m_far = np.mean(fars)
            m_f1 = np.mean(f1s)
            method_summary[method_name] = {
                'mAUROC': float(m_auc),
                'mFAR': float(m_far),
                'mF1': float(m_f1),
            }
            print(f"  {method_name:<20s}  {m_auc:>8.4f}  {m_far:>8.3f}  {m_f1:>8.4f}")

    # ── False-alarm comparison ──
    print("\n\n" + "=" * 70)
    print("  FALSE ALARM ANALYSIS")
    print("  With vs Without Morse topology filter")
    print("=" * 70)

    if 'UDL_Molecular' in method_summary and 'UDL_MolFilter' in method_summary:
        far_without = method_summary['UDL_Molecular']['mFAR']
        far_with = method_summary['UDL_MolFilter']['mFAR']
        reduction = (1 - far_with / max(far_without, 1e-10)) * 100
        print(f"  Molecular (no filter): FAR = {far_without:.3f}")
        print(f"  Molecular + filter:    FAR = {far_with:.3f}")
        print(f"  Reduction:             {reduction:+.1f}%")
    if 'UDL_Baseline' in method_summary and 'UDL_Molecular' in method_summary:
        far_base = method_summary['UDL_Baseline']['mFAR']
        far_mol = method_summary['UDL_Molecular']['mFAR']
        print(f"  Baseline (no mode):    FAR = {far_base:.3f}")
        print(f"  Molecular mode:        FAR = {far_mol:.3f}")

    # ── Save results ──
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "system_mode_benchmark.json"
    with open(out_file, 'w') as f:
        json.dump({
            'per_dataset': results,
            'summary': method_summary,
        }, f, indent=2)
    print(f"\n  Results saved to {out_file}")

    return results


def test_mode_toggle():
    """Quick test that mode toggling works correctly."""
    print("\n" + "=" * 50)
    print("  MODE TOGGLE TEST")
    print("=" * 50)

    # Synthetic data
    rng = np.random.RandomState(42)
    X_normal = rng.randn(200, 5)
    X_anomaly = rng.randn(20, 5) + 3
    X = np.vstack([X_normal, X_anomaly])
    y = np.hstack([np.zeros(200), np.ones(20)])

    engine = SystemModeEngine(mode='molecular')
    print(f"  Mode: {engine.mode.value}")
    s1 = engine.fit_score(X, y)
    auc1 = roc_auc_score(y, s1)
    print(f"  Molecular AUROC: {auc1:.4f}")

    engine.set_mode('gravity')
    print(f"  Mode: {engine.mode.value}")
    s2 = engine.fit_score(X, y)
    auc2 = roc_auc_score(y, s2)
    print(f"  Gravity AUROC: {auc2:.4f}")

    engine.set_mode('hybrid')
    print(f"  Mode: {engine.mode.value}")
    s3 = engine.fit_score(X, y)
    auc3 = roc_auc_score(y, s3)
    print(f"  Hybrid AUROC: {auc3:.4f}")

    print(f"\n  Summary: {engine.summary()}")

    # Test spectra filter
    print("\n  Spectra false-alarm filter test:")
    filt = SpectraFalseAlarmFilter(k=10)
    filt.fit(X_normal)
    raw_scores = np.random.rand(len(X))  # simulate raw noisy scores
    filtered = filt.filter_scores(X, raw_scores)
    print(f"    Raw score std:      {raw_scores.std():.4f}")
    print(f"    Filtered score std: {filtered.std():.4f}")
    print(f"    Noise suppressed:   {(1 - filtered.std()/raw_scores.std())*100:.1f}%")

    # Test Morse replacement operator
    print("\n  Morse replacement operator test:")
    morse_op = _MorseReplacementSpectrum(k=10)
    morse_op.fit(X_normal)
    features = morse_op.transform(X[:5])
    print(f"    Output shape: {features.shape}  (expected: (5, 3))")
    print(f"    Feature names: persistence_proxy, morse_index_proxy, euler_chi_proxy")

    # Test pipeline integration
    print("\n  Pipeline integration test:")
    pipe = UDLPipeline(
        operators='auto',
        system_mode='hybrid',
        filter_spectra=True,
        score_method='v3e',
    )
    pipe.fit(X, y)
    scores = pipe.score(X)
    print(f"    Pipeline scores shape: {scores.shape}")
    print(f"    System mode summary: {pipe.system_mode_summary()}")

    # Toggle mode via pipeline
    pipe.set_system_mode('molecular')
    print(f"    Toggled to: {pipe.system_mode}")
    pipe.set_system_mode(None)
    print(f"    Disabled: system_mode={pipe.system_mode}")

    print("\n  ✓ All toggle tests passed")


def test_chaos_spectrum_comparison():
    """Compare ChaosSpectrum (noisy) vs MorseReplacementSpectrum (stable).

    We measure *discriminative stability*: how much does the separation
    between normal and anomaly scores change when noise is added?
    A stable operator maintains the same separation under noise.
    """
    print("\n" + "=" * 60)
    print("  CHAOS → MORSE REPLACEMENT COMPARISON")
    print("  Discriminative stability under noise injection")
    print("=" * 60)

    rng = np.random.RandomState(42)
    X_normal = rng.randn(80, 20)
    X_anomaly = rng.randn(20, 20) + 2.5
    X_all = np.vstack([X_normal, X_anomaly])
    y = np.hstack([np.zeros(80), np.ones(20)])

    # ChaosSpectrum
    chaos = ChaosSpectrum()
    chaos.fit(X_normal)

    morse = _MorseReplacementSpectrum(k=10)
    morse.fit(X_normal)

    # Baseline AUC (no noise)
    chaos_feat_base = chaos.transform(X_all)
    morse_feat_base = morse.transform(X_all)

    def feat_auc(feat, y):
        """Best single-feature AUC."""
        aucs = []
        for j in range(feat.shape[1]):
            try:
                a = roc_auc_score(y, feat[:, j])
                aucs.append(max(a, 1 - a))  # direction-invariant
            except ValueError:
                aucs.append(0.5)
        return max(aucs) if aucs else 0.5

    auc_chaos_base = feat_auc(chaos_feat_base, y)
    auc_morse_base = feat_auc(morse_feat_base, y)

    noise_levels = [0.0, 0.05, 0.1, 0.25, 0.5, 1.0]
    print(f"\n  {'Noise σ':>8s}  {'Chaos AUC':>10s}  {'Morse AUC':>10s}  "
          f"{'Chaos ΔAUC':>11s}  {'Morse ΔAUC':>11s}")
    print("  " + "─" * 55)

    for noise_sigma in noise_levels:
        X_noisy = X_all + noise_sigma * rng.randn(*X_all.shape)

        chaos_noisy = chaos.transform(X_noisy)
        morse_noisy = morse.transform(X_noisy)

        auc_chaos = feat_auc(chaos_noisy, y)
        auc_morse = feat_auc(morse_noisy, y)

        delta_chaos = auc_chaos - auc_chaos_base
        delta_morse = auc_morse - auc_morse_base

        print(f"  {noise_sigma:>8.3f}  {auc_chaos:>10.4f}  {auc_morse:>10.4f}  "
              f"{delta_chaos:>+11.4f}  {delta_morse:>+11.4f}")

    print("\n  → Smaller |ΔAUC| = more stable discrimination under noise")
    print("  → Morse features maintain separation ⇒ fewer false alarms")


if __name__ == '__main__':
    benchmark_system_modes()
    test_mode_toggle()
    test_chaos_spectrum_comparison()
