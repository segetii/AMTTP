"""
1-MILLION-SAMPLE cybersecurity benchmark on CIC-IDS-2017 V2.
Uses 1M stratified sample for geometric methods, 100K for simulation engines.
"""
import sys, os, time
import numpy as np
from pathlib import Path
from sklearn.metrics import roc_auc_score
from collections import Counter

os.environ['CUDA_VISIBLE_DEVICES'] = ''
sys.path.insert(0, str(Path(__file__).resolve().parent))

from geo_full_pipeline import (
    adaptive_friction, _build_ellipsoid,
    GeometricMorse, GeometricBetti, GeometricBSDT, GeometricUDL, GeometricTrigScore,
    GeometricFusedScorer,
)
from udl.system_mode import MolecularEngine, GravityModeEngine, HybridGravityEngine

CYBER_DIR = Path(r'c:\amttp\data\external_validation\cyber')

# ---- helpers ----
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

def print_table(rows, title=""):
    if title:
        print(f"\n  {title}")
    hdr = (f"    {'Method':<24} {'AUC':>6} {'Prec':>6} {'FPR':>7} {'FNR':>7}"
           f" {'Caught':>14} {'Missed':>11} {'FalseAlm':>9}")
    sep = "    " + "-" * 96
    print(hdr); print(sep)
    for r in rows:
        caught = f"{r['tp']:>7,}/{r['total']:,}"
        missed = f"{r['fn']:>7,}/{r['total']:,}"
        print(f"    {r['label']:<24} {r['auc']:6.4f} {r['prec']:6.3f} {r['fpr']:7.4f} {r['fnr']:7.4f}"
              f" {caught:>14} {missed:>11} {r['fp']:>9,}")
    print(sep)

def per_attack_table(rows, y, attack_types, methods=None):
    if methods is None:
        methods = ['GeoFused(6-view)', 'QuadSurf', 'ExpoGate(MFLS)']
    mdata = {}
    for r in rows:
        if r['label'] in methods:
            thr = float(np.percentile(r['scores'], 100 * (1 - y.mean())))
            mdata[r['label']] = (r['scores'] > thr).astype(int)
    if not mdata:
        return
    mnames = list(mdata.keys())
    print(f"\n    Per-attack-type detection (Caught / Total):")
    hdr = f"    {'Attack':<24} {'Total':>7}"
    for mn in mnames:
        hdr += f"  {mn[:16]:>18}"
    print(hdr)
    print("    " + "-" * (33 + 20 * len(mnames)))
    at_arr = np.array(attack_types)
    for atype, count in sorted(Counter(at_arr[y==1]).items(), key=lambda x: -x[1])[:20]:
        ma = (at_arr == atype)
        line = f"    {str(atype)[:24]:<24} {count:>7,}"
        for mn in mnames:
            n_det = int(mdata[mn][ma].sum())
            pct   = n_det / count * 100 if count > 0 else 0
            line += f"  {n_det:>7,} ({pct:5.1f}%)"
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


# ============================================================
print("=" * 90)
print("  1-MILLION-SAMPLE CYBERSECURITY BENCHMARK")
print("  CIC-IDS-2017 V2 -- 1,000,000 stratified sample from 2.7M real network flows")
print("=" * 90)

# Load full dataset
ds_path = CYBER_DIR / 'cicids2017_v2.npz'
d = np.load(ds_path, allow_pickle=True)
X_full = d['X10']
y_full = d['y']
at_full = np.array(d['attack_types'])
N = len(y_full)
Na = int(y_full.sum())
print(f"\n  Full dataset: {N:,} samples | {Na:,} attacks ({100*Na/N:.1f}%) | {N-Na:,} normal")
print(f"  Attack types: {len(set(at_full[y_full==1]))}")

# ---- Stratified subsample to 1,000,000 ----
TARGET = 1_000_000
rng = np.random.RandomState(42)
idx_a = np.where(y_full == 1)[0]
idx_n = np.where(y_full == 0)[0]
n_a = min(len(idx_a), int(TARGET * y_full.mean()))
n_n = TARGET - n_a
idx_use = np.concatenate([
    rng.choice(idx_a, n_a, replace=False),
    rng.choice(idx_n, min(n_n, len(idx_n)), replace=False)
])
idx_use.sort()
X = X_full[idx_use]
y = y_full[idx_use]
at = at_full[idx_use]

N1 = len(y); Na1 = int(y.sum())
print(f"\n  1M subsample: {N1:,} samples | {Na1:,} attacks ({100*Na1/N1:.1f}%) | {N1-Na1:,} normal")
print(f"  Attack distribution:")
for atype, cnt in sorted(Counter(at[y==1]).items(), key=lambda x: -x[1]):
    print(f"    {atype:<30s} {cnt:>8,}  ({100*cnt/Na1:5.1f}%)")

# ---- Build ellipsoid on 1M ----
print(f"\n  Building ellipsoid on {N1:,} samples...")
t0 = time.perf_counter()
ell = _build_ellipsoid(X)
t_ell = time.perf_counter() - t0
print(f"  Ellipsoid built in {t_ell:.1f}s")

rows = []
X_ref = X[y == 0]

# ---- Geometric Fused Scorer (6-view) ----
print(f"\n  Fitting GeometricFusedScorer on {N1:,} samples...")
gfs = GeometricFusedScorer(k_af=5, eta_af=0.25)
t0 = time.perf_counter()
gfs.fit(X, ell)
s_fused = gfs.score(X)
t1 = time.perf_counter() - t0
r = op_metrics(y, s_fused, "GeoFused(6-view)")
rows.append(r)
print(f"  GeoFused: AUC={r['auc']:.4f}  ({t1*1000:.0f}ms)")

# ---- BSDT Baseline ----
bsdt = GeometricBSDT()
bsdt.fit(X_ref, ell)
s_base = bsdt.score(X)
rows.append(op_metrics(y, s_base, "BSDT Baseline"))
print(f"  BSDT Baseline: AUC={rows[-1]['auc']:.4f}")

# ---- QuadSurf ----
print(f"  Fitting QuadSurf on {N1:,}... ", end="", flush=True)
t0 = time.perf_counter()
bsdt.fit_quadsurf(X, y)
s_qs = bsdt.score_quadsurf(X)
t_qs = time.perf_counter() - t0
r = op_metrics(y, s_qs, "QuadSurf")
rows.append(r)
print(f"AUC={r['auc']:.4f}  ({t_qs*1000:.0f}ms)")

# ---- SignedLR ----
print(f"  Fitting SignedLR on {N1:,}... ", end="", flush=True)
t0 = time.perf_counter()
bsdt.fit_signed_lr(X, y)
s_lr = bsdt.score_signed_lr(X)
t_lr = time.perf_counter() - t0
r = op_metrics(y, s_lr, "SignedLR")
rows.append(r)
w = bsdt.lr_weights()
ch = ['bias', 'd_C', 'd_G', 'd_A', 'd_T', 'MFLS']
print(f"AUC={r['auc']:.4f}  ({t_lr*1000:.0f}ms)")
print(f"    Weights: {', '.join(f'{n}={v:+.3f}' for n,v in zip(ch, w))}")

# ---- ExpoGate ----
print(f"  Fitting ExpoGate on {N1:,}... ", end="", flush=True)
t0 = time.perf_counter()
bsdt.fit_expogate(X, y)
s_eg = bsdt.score_expogate(X)
t_eg = time.perf_counter() - t0
r = op_metrics(y, s_eg, "ExpoGate(MFLS)")
rows.append(r)
print(f"AUC={r['auc']:.4f}  ({t_eg*1000:.0f}ms)")

# ---- Fused variants ----
s_qs_f = replace_bsdt_in_fusion(gfs, X, ell, s_qs)
rows.append(op_metrics(y, s_qs_f, "GeoFused+QuadSurf"))
s_eg_f = replace_bsdt_in_fusion(gfs, X, ell, s_eg)
rows.append(op_metrics(y, s_eg_f, "GeoFused+ExpoGate"))

# ---- Simulation engines on 100K subsample ----
ENGINE_N = 100_000
rng2 = np.random.RandomState(99)
idx_e = rng2.choice(N1, ENGINE_N, replace=False)
X_e, y_e = X[idx_e], y[idx_e]
print(f"\n  Simulation engines on {ENGINE_N:,} subsample...")

for EngCls, name in [(MolecularEngine, "Molecular(LJ)"),
                      (GravityModeEngine, "Gravity(N-body)"),
                      (HybridGravityEngine, "Hybrid(Mol+Grav)")]:
    try:
        eng = EngCls(calibrate='combined', target_far=0.05)
        t0 = time.perf_counter()
        s = eng.fit_score(X_e, y_e)
        t_eng = time.perf_counter() - t0
        r = op_metrics(y_e, s, name)
        rows.append(r)
        print(f"    {name}: AUC={r['auc']:.4f}  ({t_eng*1000:.0f}ms)")
    except Exception as ex:
        print(f"    {name} FAILED: {ex}")

# ---- Results table ----
print_table(rows, f"CIC-IDS-2017V2 -- 1,000,000 Sample Benchmark")

# ---- Per-attack breakdown ----
full_rows = [r for r in rows if r['total'] == int(y.sum())]
per_attack_table(full_rows, y, at)

# ---- Scale comparison (200K vs 1M) ----
print(f"\n  NOTE: Previous 200K subsample had: GeoFused=0.7787, QuadSurf=0.8766, ExpoGate=0.8766")
print(f"  Scaling to 1M tests whether AUC changes with more data or holds stable.")

print("\n  Done.")
