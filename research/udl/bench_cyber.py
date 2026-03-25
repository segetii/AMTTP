"""
Benchmark modern cybersecurity datasets against all engines.
Runs: NSL-KDD + UNSW-NB15 + CyberOps Synthetic + KDDCup99 (legacy)
"""
import sys, os, time
sys.path.insert(0, r'c:\amttp\research\udl')
os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['PYTHONIOENCODING'] = 'utf-8'

import numpy as np
from pathlib import Path
from sklearn.metrics import roc_auc_score
from collections import Counter

ROOT = Path(r'c:\amttp')
CYBER_DIR = ROOT / 'data' / 'external_validation' / 'cyber'

# -- Import engines --
from geo_full_pipeline import (
    GeometricFusedScorer, GeometricBSDT, GeometricMorse, GeometricBetti,
    GeometricUDL, GeometricTrigScore, adaptive_friction
)

class _Ell:
    def __init__(self, center, semi_axes):
        self.center = center
        self.semi_axes = semi_axes

def _build_ellipsoid(X):
    mu = X.mean(axis=0)
    Xc = X - mu
    cov = np.cov(Xc, rowvar=False)
    evals = np.linalg.eigvalsh(cov)
    evals = np.maximum(evals, 1e-12)
    semi = np.sqrt(evals)
    return _Ell(mu, semi)

def _op_metrics(y, scores, label):
    thr = float(np.percentile(scores, 100 * (1 - y.mean())))
    yp  = (scores > thr).astype(int)
    auc  = roc_auc_score(y, scores)
    tp = int(((y == 1) & (yp == 1)).sum())
    fn = int(((y == 1) & (yp == 0)).sum())
    fp = int(((y == 0) & (yp == 1)).sum())
    tn = int(((y == 0) & (yp == 0)).sum())
    total_attacks = int(y.sum())
    fpr = fp / max(fp + tn, 1)
    fnr = fn / max(fn + tp, 1)
    prec = tp / max(tp + fp, 1)
    return {'label': label, 'auc': auc, 'fpr': fpr, 'fnr': fnr,
            'prec': prec, 'tp': tp, 'fn': fn, 'fp': fp, 'tn': tn,
            'total': total_attacks, 'scores': scores}

def _print_table(rows, title=""):
    if title:
        print(f"\n  {title}")
    hdr = (f"    {'Method':<24} {'AUC':>6} {'Prec':>6} {'FPR':>7} {'FNR':>7}"
           f" {'Caught':>12} {'Missed':>9} {'FalseAlm':>9}")
    sep = "    " + "-" * 88
    print(hdr)
    print(sep)
    for r in rows:
        caught = f"{r['tp']:>5}/{r['total']:<5}"
        missed = f"{r['fn']:>4}/{r['total']:<4}"
        print(f"    {r['label']:<24} {r['auc']:6.4f} {r['prec']:6.3f} {r['fpr']:7.4f} {r['fnr']:7.4f}"
              f" {caught:>12} {missed:>9} {r['fp']:>9}")
    print(sep)


def bench_dataset(name, X, y, attack_types=None, max_sim_samples=30000):
    """Run all methods on a dataset, with per-attack breakdown."""
    print(f"\n{'='*92}")
    print(f"  {name}")
    print(f"{'='*92}")
    N = len(y)
    Na = int(y.sum())
    print(f"  Samples: {N:,}  |  Attacks: {Na:,} ({100*Na/N:.1f}%)  |  Normal: {N-Na:,}")

    ell = _build_ellipsoid(X)
    a2 = ell.semi_axes ** 2
    X_ref = X[y == 0]

    rows = []

    # -- Q_raw --
    t0 = time.perf_counter()
    Q_raw = np.sum(X**2 / a2, axis=1)
    t_qr = (time.perf_counter() - t0)*1000
    rows.append(_op_metrics(y, Q_raw, "Q(x) raw"))

    # -- GeomFused --
    gfs = GeometricFusedScorer(k_af=5, eta_af=0.25)
    t0 = time.perf_counter()
    gfs.fit(X, ell)
    s_fused = gfs.score(X)
    t_gf = (time.perf_counter() - t0)*1000
    rows.append(_op_metrics(y, s_fused, "GeoFused(6-view)"))

    # -- BSDT variants --
    bsdt = GeometricBSDT()
    bsdt.fit(X_ref, ell)
    s_base = bsdt.score(X)
    rows.append(_op_metrics(y, s_base, "BSDT Baseline"))

    bsdt.fit_quadsurf(X, y)
    s_qs = bsdt.score_quadsurf(X)
    rows.append(_op_metrics(y, s_qs, "QuadSurf"))

    bsdt.fit_expogate(X, y)
    s_eg = bsdt.score_expogate(X)
    rows.append(_op_metrics(y, s_eg, "ExpoGate(MFLS)"))

    # -- Simulation engines (subsample if too large) --
    from udl.system_mode import MolecularEngine, GravityModeEngine, HybridGravityEngine

    if N > max_sim_samples:
        rng = np.random.RandomState(42)
        idx = rng.choice(N, max_sim_samples, replace=False)
        X_sub, y_sub = X[idx], y[idx]
        sub_note = f" [subsampled {max_sim_samples:,}/{N:,}]"
    else:
        X_sub, y_sub = X, y
        sub_note = ""

    for EngCls, eng_name in [(MolecularEngine, "Molecular(LJ)"),
                              (GravityModeEngine, "Gravity(N-body)"),
                              (HybridGravityEngine, "Hybrid(Mol+Grav)")]:
        try:
            eng = EngCls(calibrate='combined', target_far=0.05)
            t0 = time.perf_counter()
            s_eng = eng.fit_score(X_sub, y_sub)
            t_eng = (time.perf_counter() - t0)*1000
            r = _op_metrics(y_sub, s_eng, f"{eng_name}{sub_note}")
            rows.append(r)
        except Exception as ex:
            print(f"    [{eng_name} skipped: {ex}]")

    _print_table(rows)

    # -- Per-attack-type breakdown --
    if attack_types is not None:
        at = np.array(attack_types)
        atk_mask = y == 1
        unique_cats = Counter(at[atk_mask])
        if len(unique_cats) > 1:
            print(f"\n  Per-attack-type detection:")
            # Use key methods from full-size runs
            key_methods = {}
            for r in rows:
                if r['label'].startswith(('QuadSurf', 'ExpoGate', 'GeoFused(6', 'Q(x) raw')):
                    thr = float(np.percentile(r['scores'], 100 * (1 - y.mean())))
                    key_methods[r['label']] = (r['scores'] > thr).astype(int)

            # Also add simulation methods for subsampled
            sim_key = {}
            for r in rows:
                if 'Molecular' in r['label'] or 'Gravity' in r['label'] or 'Hybrid' in r['label']:
                    if N > max_sim_samples:
                        thr = float(np.percentile(r['scores'], 100 * (1 - y_sub.mean())))
                        sim_key[r['label'].split('[')[0].strip()] = {
                            'pred': (r['scores'] > thr).astype(int),
                            'is_sub': True
                        }
                    else:
                        thr = float(np.percentile(r['scores'], 100 * (1 - y.mean())))
                        sim_key[r['label']] = {
                            'pred': (r['scores'] > thr).astype(int),
                            'is_sub': False
                        }

            mnames = list(key_methods.keys())
            hdr = f"    {'Attack':<18} {'Total':>5}"
            for mn in mnames:
                hdr += f"  {mn[:14]:>16}"
            print(hdr)
            print("    " + "-" * (24 + 18*len(mnames)))

            for atype, count in sorted(unique_cats.items(), key=lambda x: -x[1])[:12]:
                ma = (at == atype) & (y == 1)
                line = f"    {str(atype):<18} {count:>5}"
                for mn in mnames:
                    yp = key_methods[mn]
                    n_det = int(yp[ma].sum())
                    pct = n_det/count*100 if count > 0 else 0
                    line += f"  {n_det:>6} ({pct:5.1f}%)"
                print(line)

    return rows


# ========== Run benchmarks ==========
all_results = {}

# 1. NSL-KDD
f = CYBER_DIR / 'nsl_kdd.npz'
if f.exists():
    d = np.load(f, allow_pickle=True)
    akey = 'attack_categories' if 'attack_categories' in d else 'attack_types'
    all_results['NSL-KDD'] = bench_dataset(
        "NSL-KDD (148K, improved KDDCup99, 4 attack categories)",
        d['X10'], d['y'], d[akey])

# 2. UNSW-NB15
f = CYBER_DIR / 'unsw_nb15.npz'
if f.exists():
    d = np.load(f, allow_pickle=True)
    all_results['UNSW-NB15'] = bench_dataset(
        "UNSW-NB15 (54K, modern attacks, 9 categories)",
        d['X10'], d['y'], d['attack_types'])

# 3. Synthetic CyberOps
f = CYBER_DIR / 'cyberops_synthetic.npz'
if f.exists():
    d = np.load(f, allow_pickle=True)
    all_results['CyberOps'] = bench_dataset(
        "CyberOps Synthetic (78K, 7 attack campaigns, realistic SOC traffic)",
        d['X10'], d['y'], d['attack_types'])

# 4. Legacy KDDCup99
f = ROOT / 'data' / 'external_validation' / 'kddcup99_cyber.npz'
if f.exists():
    d = np.load(f, allow_pickle=True)
    all_results['KDDCup99'] = bench_dataset(
        "KDDCup99 (108K, legacy 1999, 12 attack types)",
        d['X10'], d['y'], d['attack_types'])


# ========== Cross-dataset summary ==========
print(f"\n\n{'='*92}")
print(f"  CROSS-DATASET SUMMARY  --  Best AUC per method per dataset")
print(f"{'='*92}")

# Collect method names across all datasets
method_set = set()
for ds_rows in all_results.values():
    for r in ds_rows:
        method_set.add(r['label'].split('[')[0].strip())

# Print header
datasets = list(all_results.keys())
hdr = f"  {'Method':<24}"
for ds in datasets:
    hdr += f"  {ds:>16}"
print(hdr)
print("  " + "-" * (24 + 18*len(datasets)))

# Collect into a matrix
for method in ['Q(x) raw', 'GeoFused(6-view)', 'BSDT Baseline', 'QuadSurf',
               'ExpoGate(MFLS)', 'Molecular(LJ)', 'Gravity(N-body)', 'Hybrid(Mol+Grav)']:
    line = f"  {method:<24}"
    for ds in datasets:
        found = False
        for r in all_results.get(ds, []):
            if r['label'].startswith(method):
                line += f"  {r['auc']:>16.4f}"
                found = True
                break
        if not found:
            line += f"  {'---':>16}"
    print(line)

print("\nDone.")
