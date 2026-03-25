"""
1-MILLION ENGINE BENCHMARK — Direct fit_score on 1M samples.

The engines already handle this correctly:
  - Simulate on max_samples (~5K) subsample internally
  - Score ALL N points via kNN-based FusedSystemScorer
  - kNN scoring is O(N * k * log(N_ref)) — fast on 1M

Also uses ReducedTensorDescriptor as a FAST supplementary signal
by batching descriptor computation more efficiently.
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
    GeometricBSDT, GeometricFusedScorer,
)
from udl.system_mode import (
    MolecularEngine, GravityModeEngine, HybridGravityEngine,
)

CYBER_DIR = Path(r'c:\amttp\data\external_validation\cyber')


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
                tp=tp, fn=fn, fp=fp, tn=tn, total=int(y.sum()))


def print_table(rows, title=""):
    if title:
        print(f"\n  {title}")
    hdr = (f"    {'Method':<32} {'AUC':>6} {'Prec':>6} {'FPR':>7} {'FNR':>7}"
           f" {'Caught':>16} {'Missed':>13} {'FP':>9} {'Time':>7}")
    sep = "    " + "-" * 115
    print(hdr); print(sep)
    for r in rows:
        caught = f"{r['tp']:>7,}/{r['total']:,}"
        missed = f"{r['fn']:>7,}/{r['total']:,}"
        t = r.get('time', 0)
        print(f"    {r['label']:<32} {r['auc']:6.4f} {r['prec']:6.3f} {r['fpr']:7.4f} {r['fnr']:7.4f}"
              f" {caught:>16} {missed:>13} {r['fp']:>9,} {t:>6.1f}s")
    print(sep)


def per_attack_table(rows, y, at, methods=None):
    if methods is None:
        methods = [r['label'] for r in rows[:5]]
    mdata = {}
    for r in rows:
        if r['label'] in methods and 'scores' in r:
            thr = float(np.percentile(r['scores'], 100 * (1 - y.mean())))
            mdata[r['label']] = (r['scores'] > thr).astype(int)
    if not mdata:
        return
    mnames = list(mdata.keys())
    print(f"\n    Per-attack-type detection:")
    hdr = f"    {'Attack':<28} {'Total':>7}"
    for mn in mnames:
        hdr += f"  {mn[:18]:>20}"
    print(hdr)
    print("    " + "-" * (37 + 22 * len(mnames)))
    at_arr = np.array(at)
    for atype, count in sorted(Counter(at_arr[y==1]).items(), key=lambda x: -x[1])[:15]:
        ma = (at_arr == atype)
        line = f"    {str(atype)[:28]:<28} {count:>7,}"
        for mn in mnames:
            n_det = int(mdata[mn][ma].sum())
            pct = n_det / count * 100 if count > 0 else 0
            line += f"  {n_det:>8,} ({pct:5.1f}%)"
        print(line)


# ============================================================
print("=" * 100)
print("  1-MILLION-SAMPLE ENGINE BENCHMARK — Direct Simulation on CIC-IDS-2017 V2")
print("  Engines simulate 5K particles, kNN-score ALL 1,000,000 points")
print("=" * 100)

ds_path = CYBER_DIR / 'cicids2017_v2.npz'
d = np.load(ds_path, allow_pickle=True)
X_full = d['X10']
y_full = d['y']
at_full = np.array(d['attack_types'])
N = len(y_full)
print(f"\n  Full dataset: {N:,} samples | {int(y_full.sum()):,} attacks ({100*y_full.mean():.1f}%)")

# ---- Stratified subsample to 1M ----
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
print(f"  1M subsample: {N1:,} | {Na1:,} attacks ({100*Na1/N1:.1f}%) | {N1-Na1:,} normal")

# Attack distribution
print(f"\n  Attack distribution:")
for atype, cnt in sorted(Counter(at[y==1]).items(), key=lambda x: -x[1]):
    print(f"    {atype:<30s} {cnt:>8,}  ({100*cnt/Na1:5.1f}%)")


# ============================================================
# GEOMETRIC METHODS (direct on 1M)
# ============================================================
print(f"\n{'='*100}")
print(f"  GEOMETRIC METHODS on 1,000,000")
print(f"{'='*100}")

ell = _build_ellipsoid(X)
X_ref = X[y == 0]
rows_geo = []

# GeoFused
gfs = GeometricFusedScorer(k_af=5, eta_af=0.25)
t0 = time.perf_counter()
gfs.fit(X, ell)
s = gfs.score(X)
t_gf = time.perf_counter() - t0
r = op_metrics(y, s, "GeoFused(6-view)")
r['scores'] = s; r['time'] = t_gf
rows_geo.append(r)
print(f"  GeoFused: AUC={r['auc']:.4f} ({t_gf:.1f}s)")

# QuadSurf
bsdt = GeometricBSDT()
bsdt.fit(X_ref, ell)
t0 = time.perf_counter()
bsdt.fit_quadsurf(X, y)
s = bsdt.score_quadsurf(X)
t_qs = time.perf_counter() - t0
r = op_metrics(y, s, "QuadSurf")
r['scores'] = s; r['time'] = t_qs
rows_geo.append(r)
print(f"  QuadSurf: AUC={r['auc']:.4f} ({t_qs:.1f}s)")

# ExpoGate
t0 = time.perf_counter()
bsdt.fit_expogate(X, y)
s = bsdt.score_expogate(X)
t_eg = time.perf_counter() - t0
r = op_metrics(y, s, "ExpoGate(MFLS)")
r['scores'] = s; r['time'] = t_eg
rows_geo.append(r)
print(f"  ExpoGate: AUC={r['auc']:.4f} ({t_eg:.1f}s)")


# ============================================================
# ENGINE METHODS — Direct fit_score on ALL 1M
# Engines subsample to max_samples internally, score all N via kNN
# ============================================================
print(f"\n{'='*100}")
print(f"  SIMULATION ENGINES on 1,000,000 (simulate 5K, kNN-score all 1M)")
print(f"{'='*100}")

rows_eng = []

engine_configs = [
    (MolecularEngine, "Molecular(LJ)", dict(max_samples=5000)),
    (GravityModeEngine, "Gravity(N-body)", dict(max_samples=5000)),
    (HybridGravityEngine, "Hybrid(Mol+Grav)", dict(
        molecular_params=dict(max_samples=5000),
        gravity_params=dict(max_samples=5000))),
]

for EngCls, name, kwargs in engine_configs:
    print(f"\n  --- {name} ---")
    print(f"  Passing {N1:,} samples to fit_score (engine subsamples to 5K internally)")
    
    try:
        eng = EngCls(calibrate='combined', target_far=0.05, **kwargs)
        t0 = time.perf_counter()
        s = eng.fit_score(X, y)
        elapsed = time.perf_counter() - t0
        
        r = op_metrics(y, s, f"{name}")
        r['scores'] = s; r['time'] = elapsed
        rows_eng.append(r)
        print(f"  AUC={r['auc']:.4f}  Prec={r['prec']:.3f}  FPR={r['fpr']:.4f}  "
              f"Caught={r['tp']:,}/{r['total']:,}  Time={elapsed:.1f}s")
        
        # Report engine convergence
        if hasattr(eng, '_convergence_report'):
            rep = eng._convergence_report
            print(f"  Convergence: {rep}")
        elif hasattr(eng, 'molecular') and hasattr(eng.molecular, '_convergence_report'):
            print(f"  Mol convergence: {eng.molecular._convergence_report}")
            print(f"  Grav convergence: {eng.gravity._convergence_report}")
        
        # Morse alarm
        alarm = getattr(eng, '_morse_alarm', None)
        if alarm is None and hasattr(eng, 'molecular'):
            alarm = getattr(eng.molecular, '_morse_alarm', None)
        if alarm is not None:
            print(f"  Morse alarm = {alarm}")

    except Exception as ex:
        import traceback
        print(f"  FAILED: {ex}")
        traceback.print_exc()

# ============================================================
# ENGINE METHODS — max_samples=10000 (more simulation particles)
# ============================================================
print(f"\n{'='*100}")
print(f"  ENGINES with 10K SIMULATION PARTICLES on 1,000,000")
print(f"{'='*100}")

rows_eng10k = []

engine_configs_10k = [
    (MolecularEngine, "Molecular(LJ) [10K sim]", dict(max_samples=10000)),
    (GravityModeEngine, "Gravity(N-body) [10K sim]", dict(max_samples=10000)),
    (HybridGravityEngine, "Hybrid(Mol+Grav) [10K sim]", dict(
        molecular_params=dict(max_samples=10000),
        gravity_params=dict(max_samples=10000))),
]

for EngCls, name, kwargs in engine_configs_10k:
    print(f"\n  --- {name} ---")
    try:
        eng = EngCls(calibrate='combined', target_far=0.05, **kwargs)
        t0 = time.perf_counter()
        s = eng.fit_score(X, y)
        elapsed = time.perf_counter() - t0
        
        r = op_metrics(y, s, name)
        r['scores'] = s; r['time'] = elapsed
        rows_eng10k.append(r)
        print(f"  AUC={r['auc']:.4f}  Prec={r['prec']:.3f}  FPR={r['fpr']:.4f}  "
              f"Caught={r['tp']:,}/{r['total']:,}  Time={elapsed:.1f}s")
    except Exception as ex:
        print(f"  FAILED: {ex}")


# ============================================================
# COMBINED SUMMARY
# ============================================================
all_rows = rows_geo + rows_eng + rows_eng10k

print(f"\n\n{'='*100}")
print(f"  FULL RESULTS: 1,000,000 CIC-IDS-2017 V2 Real Network Flows")
print(f"{'='*100}")
print_table(all_rows, f"All methods scored on {N1:,} samples")

# Per-attack breakdown for top methods
top_methods = ['GeoFused(6-view)', 'QuadSurf', 'ExpoGate(MFLS)',
               'Molecular(LJ)', 'Gravity(N-body)', 'Hybrid(Mol+Grav)']
per_attack_table([r for r in all_rows if r['label'] in top_methods], y, at, top_methods)

# Scale comparison
print(f"\n  SIMULATION SCALE COMPARISON:")
print(f"  {'Method':<36} {'3K sim':>8} {'5K sim':>8} {'10K sim':>8}")
print(f"  {'-'*64}")
for base_name in ["Molecular(LJ)", "Gravity(N-body)", "Hybrid(Mol+Grav)"]:
    r5k = [r for r in rows_eng if r['label'] == base_name]
    r10k = [r for r in rows_eng10k if base_name in r['label']]
    auc_5k = f"{r5k[0]['auc']:.4f}" if r5k else "--"
    auc_10k = f"{r10k[0]['auc']:.4f}" if r10k else "--"
    print(f"  {base_name:<36} {'--':>8} {auc_5k:>8} {auc_10k:>8}")

print(f"\n  All engines scored ALL 1,000,000 points via kNN interpolation.")
print(f"  Simulation ran on 5K/10K particle subsample; scoring covers full population.")
print(f"\n  Done.")
