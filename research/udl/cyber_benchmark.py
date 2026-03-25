"""
Focused cybersecurity benchmark: NSL-KDD + UNSW-NB15 + CyberOps Synthetic + KDDCup99 (legacy)

Runs all scoring variants + per-attack-type breakdown.
Skips ERCOT/G-SIB to save time.  Uses ASCII only for Windows cp1252 safety.
"""
import sys, os, time
import numpy as np
from pathlib import Path
from sklearn.metrics import roc_auc_score

# Force CPU for reproducibility
os.environ['CUDA_VISIBLE_DEVICES'] = ''

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geo_full_pipeline import (
    adaptive_friction, _build_ellipsoid,
    GeometricMorse, GeometricBetti, GeometricBSDT, GeometricUDL, GeometricTrigScore,
    GeometricFusedScorer,
)
from udl.system_mode import MolecularEngine, GravityModeEngine, HybridGravityEngine
from collections import Counter

ROOT = Path(r'c:\amttp')
CYBER_DIR  = ROOT / 'data' / 'external_validation' / 'cyber'
LEGACY_KDD = ROOT / 'data' / 'external_validation' / 'kddcup99_cyber.npz'


# ---- metrics helpers ----
def op_metrics(y, scores, label):
    thr = float(np.percentile(scores, 100 * (1 - y.mean())))
    yp  = (scores > thr).astype(int)
    auc = roc_auc_score(y, scores)
    tp = int(((y == 1) & (yp == 1)).sum())
    fn = int(((y == 1) & (yp == 0)).sum())
    fp = int(((y == 0) & (yp == 1)).sum())
    tn = int(((y == 0) & (yp == 0)).sum())
    fpr = fp / max(fp + tn, 1)
    fnr = fn / max(fn + tp, 1)
    prec = tp / max(tp + fp, 1)
    return dict(label=label, auc=auc, fpr=fpr, fnr=fnr, prec=prec,
                tp=tp, fn=fn, fp=fp, tn=tn, total=int(y.sum()), scores=scores)


def print_op_table(rows, title=""):
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


def per_attack_table(rows, y, attack_types, key_methods=None):
    """Per-attack-type detection breakdown for selected methods."""
    if key_methods is None:
        key_methods = ['QuadSurf', 'ExpoGate(MFLS)', 'Hybrid(Mol+Grav)',
                       'GeoFused(6-view)', 'Molecular(LJ)', 'Gravity(N-body)']

    methods = {}
    for r in rows:
        if r['label'] in key_methods:
            thr = float(np.percentile(r['scores'], 100 * (1 - y.mean())))
            methods[r['label']] = (r['scores'] > thr).astype(int)

    if not methods:
        return

    mnames = list(methods.keys())
    print(f"\n    Per-attack-type detection (Caught / Total):")
    hdr = f"    {'Attack':<20} {'Total':>5}"
    for mn in mnames:
        hdr += f"  {mn[:14]:>16}"
    print(hdr)
    print("    " + "-" * (26 + 18 * len(mnames)))

    at_arr = np.array(attack_types)
    cat_counts = Counter(at_arr[y == 1])
    for atype, count in sorted(cat_counts.items(), key=lambda x: -x[1])[:15]:
        ma = (at_arr == atype)
        line = f"    {str(atype):<20} {count:>5}"
        for mn in mnames:
            n_det = int(methods[mn][ma].sum())
            pct   = n_det / count * 100 if count > 0 else 0
            line += f"  {n_det:>6} ({pct:5.1f}%)"
        print(line)


def replace_bsdt_in_fusion(gfs, X, ell, variant_scores):
    X_p = (adaptive_friction(X, ell, gfs.k_af, gfs.eta_af)
           if gfs.k_af > 0 else X.astype(np.float64))
    a2 = ell.semi_axes ** 2
    s_qraw  = gfs._robust_norm(np.sum(X_p ** 2 / a2, axis=1))
    s_morse = gfs._robust_norm(gfs.morse.score(X_p))
    s_betti = gfs._robust_norm(gfs.betti.score(X_p))
    s_udl   = gfs._robust_norm(gfs.udl.score(X_p))
    s_trig  = gfs._robust_norm(gfs.trig.score(X_p))
    s_var   = gfs._robust_norm(variant_scores)
    return gfs._fisher_fuse([s_qraw, s_morse, s_betti, s_udl, s_trig, s_var])


# ---- variant benchmark ----
def variant_bench(X, y, ell, dataset_name, attack_types=None, max_engine_samples=50000, max_geo_samples=200000):
    print(f"\n== {dataset_name} ==")
    N = len(y); Na = int(y.sum()); Nn = N - Na
    print(f"    Samples: {N:,}  |  Attacks: {Na:,} ({100*Na/N:.1f}%)  |  Normal: {Nn:,}")

    # Subsample for geometric methods if dataset is very large
    if N > max_geo_samples:
        rng_g = np.random.RandomState(42)
        # Stratified: keep attack ratio
        idx_a = np.where(y == 1)[0]
        idx_n = np.where(y == 0)[0]
        n_a = min(len(idx_a), int(max_geo_samples * y.mean()))
        n_n = max_geo_samples - n_a
        idx_use = np.concatenate([
            rng_g.choice(idx_a, n_a, replace=False),
            rng_g.choice(idx_n, min(n_n, len(idx_n)), replace=False)
        ])
        idx_use.sort()
        X_geo = X[idx_use]
        y_geo = y[idx_use]
        at_geo = attack_types[idx_use] if attack_types is not None else None
        ell = _build_ellipsoid(X_geo)  # refit ellipsoid on subsample
        print(f"    [Geometric methods subsampled to {len(y_geo):,} (stratified)]")
    else:
        X_geo, y_geo, at_geo = X, y, attack_types

    X_ref = X_geo[y_geo == 0]
    rows = []

    # GeometricFusedScorer (6-view)
    gfs = GeometricFusedScorer(k_af=5, eta_af=0.25)
    t0 = time.perf_counter()
    gfs.fit(X_geo, ell)
    s_fused = gfs.score(X_geo)
    t_fused = (time.perf_counter() - t0) * 1000
    rows.append(op_metrics(y_geo, s_fused, "GeoFused(6-view)"))
    print(f"    GeoFused: AUC={rows[-1]['auc']:.4f}  ({t_fused:.0f}ms)")

    # BSDT Baseline
    bsdt = GeometricBSDT()
    bsdt.fit(X_ref, ell)
    s_base = bsdt.score(X_geo)
    rows.append(op_metrics(y_geo, s_base, "BSDT Baseline"))

    # QuadSurf
    bsdt.fit_quadsurf(X_geo, y_geo)
    s_qs = bsdt.score_quadsurf(X_geo)
    rows.append(op_metrics(y_geo, s_qs, "QuadSurf"))

    # SignedLR
    bsdt.fit_signed_lr(X_geo, y_geo)
    s_lr = bsdt.score_signed_lr(X_geo)
    rows.append(op_metrics(y_geo, s_lr, "SignedLR"))
    w = bsdt.lr_weights()
    ch_names = ['bias', 'd_C', 'd_G', 'd_A', 'd_T', 'MFLS']
    print(f"    SignedLR weights: {', '.join(f'{n}={v:+.3f}' for n,v in zip(ch_names, w))}")

    # ExpoGate
    bsdt.fit_expogate(X_geo, y_geo)
    s_eg = bsdt.score_expogate(X_geo)
    rows.append(op_metrics(y_geo, s_eg, "ExpoGate(MFLS)"))

    # Fused + QuadSurf / ExpoGate
    s_qs_f = replace_bsdt_in_fusion(gfs, X_geo, ell, s_qs)
    rows.append(op_metrics(y_geo, s_qs_f, "GeoFused+QuadSurf"))
    s_eg_f = replace_bsdt_in_fusion(gfs, X_geo, ell, s_eg)
    rows.append(op_metrics(y_geo, s_eg_f, "GeoFused+ExpoGate"))

    # Simulation engines (subsample further if huge)
    N_geo = len(y_geo)
    if N_geo > max_engine_samples:
        rng = np.random.RandomState(42)
        idx = rng.choice(N_geo, max_engine_samples, replace=False)
        X_sub, y_sub = X_geo[idx], y_geo[idx]
        print(f"    [Engines subsampled to {max_engine_samples:,} for speed]")
    else:
        X_sub, y_sub = X_geo, y_geo

    for EngCls, name in [(MolecularEngine, "Molecular(LJ)"),
                          (GravityModeEngine, "Gravity(N-body)"),
                          (HybridGravityEngine, "Hybrid(Mol+Grav)")]:
        try:
            eng = EngCls(calibrate='combined', target_far=0.05)
            t0 = time.perf_counter()
            s = eng.fit_score(X_sub, y_sub)
            t_eng = (time.perf_counter() - t0) * 1000
            rows.append(op_metrics(y_sub, s, name))
            print(f"    {name}: AUC={rows[-1]['auc']:.4f}  ({t_eng:.0f}ms)")
        except Exception as ex:
            print(f"    [{name} skipped: {ex}]")

    # Print full table
    print_op_table(rows, dataset_name)

    # Per-attack-type
    if at_geo is not None and len(set(at_geo[y_geo == 1])) > 1:
        # Use only non-engine rows (full-size) for per-attack-type
        full_rows = [r for r in rows if r['total'] == int(y_geo.sum())]
        per_attack_table(full_rows, y_geo, at_geo)

    return rows


# ============================================================
#  MAIN
# ============================================================
print("=" * 80)
print("  CYBERSECURITY BENCHMARK - Modern Real-World Datasets (1999-2023)")
print("  CIC-IoT-2023 | HIKARI-2021 | TON-IoT-2020 | CIC-IDS-2017 V2 | UNSW-NB15 ...")
print("=" * 80)

datasets = [
    ('cic_iot_2023',       'CIC-IoT-2023 (113K, 16 IoT attack types, NEWEST)'),
    ('hikari_2021',        'HIKARI-2021 (555K, encrypted+real traffic, 4 attack types)'),
    ('ton_iot_2020',       'TON_IoT-2020 (82K, IoT network intrusion)'),
    ('cicids2017_v2',      'CIC-IDS-2017 V2 (2.7M real flows, 15 attack types)'),
    ('unsw_nb15',          'UNSW-NB15 (54K, 9 modern attack types)'),
    ('nsl_kdd',            'NSL-KDD (148K, improved KDD, 4 attack cats)'),
    ('kddcup99_full',      'KDDCup99-Full (494K, complete dataset)'),
    ('cyberops_synthetic', 'CyberOps Synthetic (78K, 7 campaigns)'),
]

all_results = {}

for ds_file, ds_name in datasets:
    ds_path = CYBER_DIR / f'{ds_file}.npz'
    if not ds_path.exists():
        print(f"\n  [SKIPPED] {ds_name} -- file not found")
        continue
    d = np.load(ds_path, allow_pickle=True)
    X  = d['X10'] if 'X10' in d else d['X']
    y  = d['y']
    at = d.get('attack_types', None)
    if at is not None:
        at = np.array(at)

    ell = _build_ellipsoid(X)
    rows = variant_bench(X, y, ell, ds_name, attack_types=at)
    all_results[ds_file] = rows

# Legacy KDDCup99
if LEGACY_KDD.exists():
    d = np.load(LEGACY_KDD, allow_pickle=True)
    X  = d['X10']
    y  = d['y']
    at = np.array(d.get('attack_types', []))
    ell = _build_ellipsoid(X)
    rows = variant_bench(X, y, ell, "KDDCup99 (legacy, 108K, 12 types)", attack_types=at)
    all_results['kddcup99'] = rows


# ============================================================
#  CROSS-DATASET SUMMARY
# ============================================================
print("\n\n" + "=" * 100)
print("  CROSS-DATASET SUMMARY  (AUC by method)")
print("=" * 100)

# Collect method names across all datasets
all_methods = []
for ds, rows in all_results.items():
    for r in rows:
        if r['label'] not in all_methods:
            all_methods.append(r['label'])

hdr = f"  {'Method':<24}"
for ds in all_results:
    hdr += f"  {ds[:16]:>16}"
print(hdr)
print("  " + "-" * (24 + 18 * len(all_results)))

for method in all_methods:
    line = f"  {method:<24}"
    for ds, rows in all_results.items():
        match = [r for r in rows if r['label'] == method]
        if match:
            line += f"  {match[0]['auc']:>16.4f}"
        else:
            line += f"  {'--':>16}"
    print(line)

print("\n  Done.")
