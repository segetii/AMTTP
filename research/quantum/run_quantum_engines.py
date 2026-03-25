"""
run_quantum_engines.py — Full BSDT Engine Benchmark for Quantum QPT
=====================================================================

Compares four detection approaches on the transverse-field Ising QPT:

  1. Bare BSDT        — raw z-score 4-channel (no dynamics)
  2. Molecular Engine  — LJ 6-12 pairwise + BSDT damping + Morse/Betti
  3. Gravity Engine    — erf/log pairwise + BSDT damping + Morse/Betti
  4. Hybrid Engine     — CV-weighted blend of Molecular + Gravity

For each engine: scores, MFLS, Morse alarm, AUC vs labels.
Multi-size comparison: N = 8, 10, 12, 14.

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations

import json
import time
import sys
import os
import numpy as np
from pathlib import Path
from sklearn.metrics import roc_auc_score

# Ensure import paths
sys.path.insert(0, str(Path(__file__).parent))

from quantum_engine import (
    TransverseFieldIsing, sweep_field, label_qpt,
    label_postqpt, QuantumBSDT, compute_mfls
)
from quantum_gravity_engine import (
    run_quantum_engine, compute_engine_mfls,
    QuantumMolecularEngine, QuantumGravityEngine, QuantumHybridEngine,
)


def compute_peak_accuracy(scores, h_vals, J=1.0, tol=0.15):
    """How close the score peak is to the true critical point."""
    idx_peak = np.argmax(scores)
    h_peak = h_vals[idx_peak]
    error = abs(h_peak / J - 1.0)
    return float(h_peak), float(error), error < tol


def safe_auc(y_true, scores):
    """AUC with fallback for degenerate cases."""
    if len(np.unique(y_true)) < 2:
        return float('nan')
    try:
        return float(roc_auc_score(y_true, scores))
    except Exception:
        return float('nan')


def run_experiment(N=12, n_points=100, verbose=True):
    """Run all engines for a single system size."""
    J = 1.0
    h_vals = np.linspace(0.01, 2.0, n_points)
    y_crit = label_qpt(h_vals, J=J, width=0.15)
    y_post = label_postqpt(h_vals, J=J)

    if verbose:
        print(f"\n{'='*60}")
        print(f"  Quantum QPT Engine Benchmark  —  N = {N} qubits")
        print(f"  h/J ∈ [0.01, 2.0],  {n_points} points,  h_c/J = 1.0")
        print(f"{'='*60}")

    # ── Exact diag sweep ──
    t0 = time.time()
    model = TransverseFieldIsing(N=N, J=J)
    results = sweep_field(model, h_vals, verbose=verbose)
    t_sweep = time.time() - t0

    obs_list = [r['obs'] for r in results]
    psi_list = [r['psi'] for r in results]

    if verbose:
        print(f"\n  Exact diag sweep: {t_sweep:.1f}s  (dim = 2^{N} = {2**N})")

    # ── Engine results container ──
    engine_results = {}

    # ── 1. Bare BSDT (baseline) ──
    if verbose:
        print("\n── 1. Bare BSDT (z-score, no dynamics) ──")
    t0 = time.time()
    bsdt = QuantumBSDT()
    bsdt.fit(obs_list, psi_list, N)
    ebs_bare = np.array([bsdt.ebs(o, p) for o, p in zip(obs_list, psi_list)])
    mfls_bare = compute_mfls(h_vals, ebs_bare)
    scores_bare = bsdt.score_batch(obs_list, psi_list)
    t_bare = time.time() - t0

    auc_ebs_crit = safe_auc(y_crit, ebs_bare)
    auc_mfls_crit = safe_auc(y_crit, mfls_bare)
    auc_score_crit = safe_auc(y_crit, scores_bare)
    auc_ebs_post = safe_auc(y_post, ebs_bare)
    auc_mfls_post = safe_auc(y_post, mfls_bare)

    h_peak_mfls, err_mfls, on_target_mfls = compute_peak_accuracy(
        mfls_bare, h_vals)

    engine_results['bare_bsdt'] = {
        'time': t_bare,
        'auc_ebs_crit': auc_ebs_crit,
        'auc_mfls_crit': auc_mfls_crit,
        'auc_score_crit': auc_score_crit,
        'auc_ebs_post': auc_ebs_post,
        'auc_mfls_post': auc_mfls_post,
        'peak_h': h_peak_mfls,
        'peak_error': err_mfls,
        'on_target': on_target_mfls,
        'scores': scores_bare.tolist(),
        'ebs': ebs_bare.tolist(),
        'mfls': mfls_bare.tolist(),
    }

    if verbose:
        print(f"  E_BS  AUC_crit={auc_ebs_crit:.3f}  AUC_post={auc_ebs_post:.3f}")
        print(f"  MFLS  AUC_crit={auc_mfls_crit:.3f}  peak h/J={h_peak_mfls:.2f} "
              f"(err={err_mfls:.3f})  on_target={on_target_mfls}")
        print(f"  Score AUC_crit={auc_score_crit:.3f}")
        print(f"  Time: {t_bare:.2f}s")

    # ── Engine configs ──
    engine_configs = {
        'molecular': {
            'engine_type': 'molecular',
            'kwargs': dict(eta=0.005, max_iter=200, k_nn=8,
                           alpha_radial=0.3, verbose=verbose),
        },
        'gravity': {
            'engine_type': 'gravity',
            'kwargs': dict(eta=0.005, max_iter=200, k_nn=8,
                           alpha_radial=0.3, gamma_attract=0.8,
                           lambda_repel=0.05, verbose=verbose),
        },
        'hybrid': {
            'engine_type': 'hybrid',
            'kwargs': dict(eta=0.005, max_iter=200, k_nn=8,
                           alpha_radial=0.3, verbose=verbose),
        },
    }

    # ── 2-4. Run each engine ──
    for idx, (name, cfg) in enumerate(engine_configs.items(), start=2):
        if verbose:
            print(f"\n── {idx}. {name.title()} Engine ──")

        t0 = time.time()
        try:
            scores, diag = run_quantum_engine(
                obs_list, h_vals,
                engine_type=cfg['engine_type'],
                ref_cutoff=0.5,
                **cfg['kwargs'],
            )
            t_engine = time.time() - t0

            mfls_engine = compute_engine_mfls(h_vals, scores)

            auc_score_crit = safe_auc(y_crit, scores)
            auc_score_post = safe_auc(y_post, scores)
            auc_mfls_crit = safe_auc(y_crit, mfls_engine)

            h_peak, err, on_target = compute_peak_accuracy(
                mfls_engine, h_vals)

            # Morse alarm
            morse_info = diag.get('morse_alarm', {})
            if isinstance(morse_info, dict):
                morse_idx = morse_info.get('morse_index', 0)
                morse_alarm = morse_info.get('alarm', False)
            else:
                morse_idx = 0
                morse_alarm = False

            engine_results[name] = {
                'time': t_engine,
                'auc_score_crit': auc_score_crit,
                'auc_score_post': auc_score_post,
                'auc_mfls_crit': auc_mfls_crit,
                'peak_h': h_peak,
                'peak_error': err,
                'on_target': on_target,
                'morse_index': morse_idx,
                'morse_alarm': morse_alarm,
                'converged': diag.get('converged', False),
                'convergence_type': diag.get('convergence_type', '?'),
                'n_iter': diag.get('n_iter', 0),
                'scores': scores.tolist(),
                'mfls': mfls_engine.tolist(),
            }

            if verbose:
                print(f"  Score AUC_crit={auc_score_crit:.3f}  "
                      f"AUC_post={auc_score_post:.3f}")
                print(f"  MFLS  AUC_crit={auc_mfls_crit:.3f}  "
                      f"peak h/J={h_peak:.2f} (err={err:.3f})")
                print(f"  Morse index={morse_idx}  alarm={morse_alarm}  "
                      f"converged={diag.get('converged')}")
                print(f"  Time: {t_engine:.2f}s")

        except Exception as e:
            t_engine = time.time() - t0
            engine_results[name] = {
                'error': str(e), 'time': t_engine,
            }
            if verbose:
                print(f"  ERROR: {e}")

    return {
        'N': N,
        'n_points': n_points,
        'h_vals': h_vals.tolist(),
        'y_crit': y_crit.tolist(),
        'y_post': y_post.tolist(),
        'sweep_time': t_sweep,
        'engines': engine_results,
    }


def run_multi_size(sizes=None, n_points=100, verbose=True):
    """Run benchmark across multiple system sizes."""
    if sizes is None:
        sizes = [8, 10, 12, 14]

    all_results = {}
    for N in sizes:
        result = run_experiment(N=N, n_points=n_points, verbose=verbose)
        all_results[str(N)] = result

    return all_results


def print_summary(results: dict):
    """Print comparison table."""
    print(f"\n{'='*80}")
    print("  ENGINE COMPARISON SUMMARY")
    print(f"{'='*80}")

    for size_key in sorted(results.keys(), key=int):
        r = results[size_key]
        N = r['N']
        print(f"\n  N = {N} qubits (dim = 2^{N} = {2**N})")
        print(f"  {'Engine':<15} {'AUC_crit':>10} {'AUC_post':>10} "
              f"{'MFLS_AUC':>10} {'Peak h/J':>10} {'Morse':>8} "
              f"{'Time':>8}")
        print(f"  {'-'*15} {'-'*10} {'-'*10} {'-'*10} {'-'*10} "
              f"{'-'*8} {'-'*8}")

        engines = r['engines']
        for name, eng in engines.items():
            if 'error' in eng:
                print(f"  {name:<15} ERROR: {eng['error'][:40]}")
                continue

            auc_crit = eng.get('auc_score_crit', eng.get('auc_mfls_crit', 0))
            auc_post = eng.get('auc_score_post', eng.get('auc_ebs_post', 0))
            auc_mfls = eng.get('auc_mfls_crit', 0)
            peak = eng.get('peak_h', 0)
            morse = eng.get('morse_index', eng.get('morse_alarm', '-'))
            t = eng.get('time', 0)

            print(f"  {name:<15} {auc_crit:>10.3f} {auc_post:>10.3f} "
                  f"{auc_mfls:>10.3f} {peak:>10.2f} {str(morse):>8} "
                  f"{t:>7.1f}s")

    # ── Best engine per metric ──
    print(f"\n  {'─'*50}")
    print("  Best per metric (N=14 if available, else largest):")
    best_key = max(results.keys(), key=int)
    engines = results[best_key]['engines']

    metrics = ['auc_score_crit', 'auc_mfls_crit', 'peak_error']
    for metric in metrics:
        best_name, best_val = None, -1 if 'error' not in metric else 999
        for name, eng in engines.items():
            if 'error' in eng:
                continue
            val = eng.get(metric, None)
            if val is None:
                continue
            if 'error' in metric:
                if val < best_val:
                    best_val, best_name = val, name
            else:
                if val > best_val:
                    best_val, best_name = val, name

        if best_name:
            print(f"  {metric:<20}: {best_name} ({best_val:.4f})")


def main():
    """Main entry point."""
    out_dir = Path(__file__).parent / 'results'
    out_dir.mkdir(exist_ok=True)

    # Single-size detailed run
    print("Phase 1: Detailed N=12 benchmark")
    result_12 = run_experiment(N=12, n_points=100, verbose=True)

    # Multi-size comparison
    print("\n\nPhase 2: Multi-size comparison")
    multi = run_multi_size(sizes=[8, 10, 12, 14], n_points=100, verbose=True)

    # ── Summary ──
    print_summary(multi)

    # ── Save ──
    save_data = {
        'detailed_N12': result_12,
        'multi_size': multi,
    }

    out_path = out_dir / 'engine_benchmark.json'
    # Convert for JSON serialisation
    def make_serialisable(obj):
        if isinstance(obj, dict):
            return {k: make_serialisable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [make_serialisable(v) for v in obj]
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.bool_,)):
            return bool(obj)
        return obj

    with open(out_path, 'w') as f:
        json.dump(make_serialisable(save_data), f, indent=2)

    print(f"\n  Results saved to {out_path}")
    return save_data


if __name__ == '__main__':
    main()
