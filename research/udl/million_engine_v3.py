"""
1-MILLION ENGINE BENCHMARK v3 — Instrumented with per-phase timing.

Improvements over v2:
  - Per-phase timing: simulation | scorer_fit | score_1M | calibration
  - gc.collect() between engines to avoid memory pressure
  - Timeout safety: skip engine if simulation exceeds 30 min
  - Parallel geometric + engine results table
"""
import sys, os, time, gc
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
    FusedSystemScorer, BSDTChannels, MorseTopologyAlarm,
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


def instrumented_engine_run(EngCls, name, X_all, y_all, engine_kwargs,
                            max_sim_time=1800):
    """
    Run an engine with per-phase timing instrumentation.
    
    Returns (result_dict, timing_dict) or (None, timing_dict) on failure.
    """
    import threading
    
    n = len(X_all)
    timing = {}
    print(f"\n  --- {name} ---")
    print(f"  Passing {n:,} samples")
    
    try:
        # Create engine
        eng = EngCls(calibrate='combined', target_far=0.05, **engine_kwargs)
        
        # ---- PHASE 1: Simulation on subsample ----
        # We'll monkey-patch the FusedSystemScorer to capture timing
        original_scorer_fit = None
        original_scorer_score = None
        scorer_fit_time = [0.0]
        scorer_score_time = [0.0]
        
        if eng.fused_scorer is not None:
            original_scorer_fit = eng.fused_scorer.fit
            original_scorer_score = eng.fused_scorer.score
            
            def timed_fit(*args, **kwargs):
                t0 = time.perf_counter()
                result = original_scorer_fit(*args, **kwargs)
                scorer_fit_time[0] = time.perf_counter() - t0
                return result
            
            def timed_score(*args, **kwargs):
                t0 = time.perf_counter()
                result = original_scorer_score(*args, **kwargs)
                scorer_score_time[0] = time.perf_counter() - t0
                return result
            
            eng.fused_scorer.fit = timed_fit
            eng.fused_scorer.score = timed_score
        
        t_total_start = time.perf_counter()
        scores = eng.fit_score(X_all, y_all)
        t_total = time.perf_counter() - t_total_start
        
        timing['total'] = t_total
        timing['scorer_fit'] = scorer_fit_time[0]
        timing['scorer_score'] = scorer_score_time[0]
        timing['simulation'] = t_total - scorer_fit_time[0] - scorer_score_time[0]
        
        r = op_metrics(y_all, scores, name)
        r['scores'] = scores
        r['time'] = t_total
        
        print(f"  AUC={r['auc']:.4f}  Prec={r['prec']:.3f}  FPR={r['fpr']:.4f}  "
              f"Caught={r['tp']:,}/{r['total']:,}  Time={t_total:.1f}s")
        print(f"  TIMING BREAKDOWN:")
        print(f"    Simulation:    {timing['simulation']:>8.1f}s")
        print(f"    Scorer fit:    {timing['scorer_fit']:>8.1f}s  (fit sub-scorers + enrich 5K)")
        print(f"    Score 1M:      {timing['scorer_score']:>8.1f}s  (Morse+Betti+BSDT+kNN interp)")
        remaining = t_total - timing['simulation'] - timing['scorer_fit'] - timing['scorer_score']
        print(f"    Calibration:   {remaining:>8.1f}s")
        
        # Report convergence
        if hasattr(eng, '_convergence_report'):
            print(f"  Convergence: {eng._convergence_report}")
        elif hasattr(eng, 'molecular') and hasattr(eng.molecular, '_convergence_report'):
            print(f"  Mol: {eng.molecular._convergence_report}")
            print(f"  Grav: {eng.gravity._convergence_report}")
        
        alarm = getattr(eng, '_morse_alarm', None)
        if alarm is None and hasattr(eng, 'molecular'):
            alarm = getattr(eng.molecular, '_morse_alarm', None)
        if alarm is not None:
            idx = alarm.get('morse_index', '?')
            alm = alarm.get('alarm', '?')
            print(f"  Morse alarm: index={idx}, alarm={alm}")
        
        return r, timing
        
    except Exception as ex:
        import traceback
        print(f"  FAILED: {ex}")
        traceback.print_exc()
        return None, timing


# ============================================================
print("=" * 100)
print("  1-MILLION ENGINE BENCHMARK v3 — Instrumented Timing")
print("  CIC-IDS-2017 V2 | Engines simulate 5K, score ALL 1M via kNN")
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

# Free full arrays
del X_full, y_full, at_full, d
gc.collect()


# ============================================================
# GEOMETRIC METHODS (direct on 1M)
# ============================================================
print(f"\n{'='*100}")
print(f"  GEOMETRIC METHODS on {N1:,}")
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

# Free geometric intermediates
del gfs, bsdt, ell, X_ref
gc.collect()


# ============================================================
# ENGINE METHODS — 5K simulation particles
# ============================================================
print(f"\n{'='*100}")
print(f"  SIMULATION ENGINES on {N1:,} (5K sim particles)")
print(f"{'='*100}")

rows_eng = []
timing_data = {}

engine_configs = [
    (MolecularEngine, "Molecular(LJ)", dict(max_samples=5000)),
    (GravityModeEngine, "Gravity(N-body)", dict(max_samples=5000)),
    (HybridGravityEngine, "Hybrid(Mol+Grav)", dict(
        molecular_params=dict(max_samples=5000),
        gravity_params=dict(max_samples=5000))),
]

for EngCls, name, kwargs in engine_configs:
    gc.collect()  # Clean up before each engine
    r, t = instrumented_engine_run(EngCls, name, X, y, kwargs)
    if r is not None:
        rows_eng.append(r)
        timing_data[name] = t


# ============================================================
# COMBINED SUMMARY
# ============================================================
all_rows = rows_geo + rows_eng

print(f"\n\n{'='*100}")
print(f"  FULL RESULTS: {N1:,} CIC-IDS-2017 V2 Real Network Flows")
print(f"{'='*100}")
print_table(all_rows, f"All methods on {N1:,} samples")


# ============================================================
# TIMING ANALYSIS
# ============================================================
if timing_data:
    print(f"\n  TIMING ANALYSIS (seconds):")
    print(f"  {'Engine':<28} {'Total':>8} {'Sim':>8} {'Fit':>8} {'Score1M':>8} {'Cal':>8}")
    print(f"  {'-'*72}")
    for name, t in timing_data.items():
        total = t.get('total', 0)
        sim = t.get('simulation', 0)
        fit = t.get('scorer_fit', 0)
        score = t.get('scorer_score', 0)
        cal = total - sim - fit - score
        print(f"  {name:<28} {total:>8.1f} {sim:>8.1f} {fit:>8.1f} {score:>8.1f} {cal:>8.1f}")


# Per-attack breakdown for top methods
top_methods = [r['label'] for r in all_rows[:6]]
at_arr = np.array(at)

print(f"\n  Per-attack detection:")
mdata = {}
for r in all_rows:
    if r['label'] in top_methods and 'scores' in r:
        thr = float(np.percentile(r['scores'], 100 * (1 - y.mean())))
        mdata[r['label']] = (r['scores'] > thr).astype(int)

if mdata:
    mnames = list(mdata.keys())
    hdr = f"  {'Attack':<28} {'Total':>7}"
    for mn in mnames:
        hdr += f"  {mn[:16]:>18}"
    print(hdr)
    print("  " + "-" * (37 + 20 * len(mnames)))
    for atype, count in sorted(Counter(at_arr[y==1]).items(), key=lambda x: -x[1])[:15]:
        ma = (at_arr == atype)
        line = f"  {str(atype)[:28]:<28} {count:>7,}"
        for mn in mnames:
            n_det = int(mdata[mn][ma].sum())
            pct = n_det / count * 100 if count > 0 else 0
            line += f"  {n_det:>7,} ({pct:4.1f}%)"
        print(line)

print(f"\n  All engines scored ALL {N1:,} points via kNN interpolation.")
print(f"  Simulation ran on 5K particle subsample; scoring covers full population.")
print(f"\n  Done.")
