"""
1-MILLION ENGINE BENCHMARK using ReducedTensorDescriptor scoring.

Strategy:
  1. Engines simulate on subsample (max_samples=5000) as usual
  2. ReducedTensorDescriptor scores ALL 1M points in O(Nd+d^3)
     instead of O(N^2 d) kNN — the key to scaling to 1M
  3. Morse index from descriptor = topological anomaly signal
  4. Full (d+7)-dim descriptor fed into a simple threshold scorer

All 3 engines: Molecular(LJ), Gravity(N-body), Hybrid(Mol+Grav)
"""
import sys, os, time
import numpy as np
from pathlib import Path
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from collections import Counter

os.environ['CUDA_VISIBLE_DEVICES'] = ''
sys.path.insert(0, str(Path(__file__).resolve().parent))

from geo_full_pipeline import (
    adaptive_friction, _build_ellipsoid,
    GeometricMorse, GeometricBetti, GeometricBSDT, GeometricUDL, GeometricTrigScore,
    GeometricFusedScorer,
)
from udl.system_mode import (
    MolecularEngine, GravityModeEngine, HybridGravityEngine,
    ReducedTensorDescriptor, SystemModeEngine,
)

CYBER_DIR = Path(r'c:\amttp\data\external_validation\cyber')


# ---- metrics ----
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
    hdr = (f"    {'Method':<36} {'AUC':>6} {'Prec':>6} {'FPR':>7} {'FNR':>7}"
           f" {'Caught':>14} {'Missed':>11} {'FalseAlm':>9}")
    sep = "    " + "-" * 108
    print(hdr); print(sep)
    for r in rows:
        caught = f"{r['tp']:>7,}/{r['total']:,}"
        missed = f"{r['fn']:>7,}/{r['total']:,}"
        print(f"    {r['label']:<36} {r['auc']:6.4f} {r['prec']:6.3f} {r['fpr']:7.4f} {r['fnr']:7.4f}"
              f" {caught:>14} {missed:>11} {r['fp']:>9,}")
    print(sep)


def per_attack_table(rows, y, at, methods=None):
    if methods is None:
        methods = [r['label'] for r in rows]
    # Collect scores for per-attack detection
    print(f"\n    Per-attack-type detection (top methods):")
    at_arr = np.array(at)
    cat_counts = Counter(at_arr[y == 1])
    for atype, count in sorted(cat_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"      {str(atype)[:28]:<28s}  {count:>7,} attacks")


def descriptor_score(desc_features, y_ref_mask):
    """
    Score using the full reduced tensor descriptor.
    Combines: grad_norm, Mahalanobis, medoid_dist, trace_H, Morse index
    into a single anomaly score via rank-based fusion.
    """
    N, D = desc_features.shape

    # Extract key channels from descriptor
    grad_norm = desc_features[:, 0]
    # Hessian eigenvalues are in columns 1..n_eigs
    # Then: mahalanobis, medoid_dist, trace_H, det_sigma, morse_index
    mahalanobis = desc_features[:, -5]
    medoid_dist = desc_features[:, -4]
    trace_H = desc_features[:, -3]
    det_sigma = desc_features[:, -2]
    morse_idx = desc_features[:, -1]

    # Rank-based fusion (robust to scale differences)
    channels = [grad_norm, mahalanobis, medoid_dist, np.abs(trace_H), morse_idx]
    ranks = []
    for ch in channels:
        r = np.argsort(np.argsort(ch)).astype(np.float64) / N
        ranks.append(r)
    
    # Fisher-VR rank fusion: mean of ranks
    fused = np.mean(ranks, axis=0)
    return fused


def descriptor_morse_score(desc_features):
    """Score using just Morse index + Mahalanobis (the theoretical signal)."""
    morse_idx = desc_features[:, -1]
    mahalanobis = desc_features[:, -5]
    
    # Morse index >= 1 means saddle point (anomaly)
    # Weight by Mahalanobis distance for calibration
    r_morse = np.argsort(np.argsort(morse_idx)).astype(np.float64) / len(morse_idx)
    r_maha = np.argsort(np.argsort(mahalanobis)).astype(np.float64) / len(mahalanobis)
    return 0.6 * r_morse + 0.4 * r_maha


# ============================================================
print("=" * 90)
print("  1-MILLION ENGINE BENCHMARK -- Reduced Tensor Descriptor Scoring")
print("  CIC-IDS-2017 V2 | 1M samples | All 3 engines | O(Nd+d^3) scoring")
print("=" * 90)

# Load dataset
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
N1 = len(y)
Na1 = int(y.sum())
print(f"  1M subsample: {N1:,} samples | {Na1:,} attacks ({100*Na1/N1:.1f}%)")

# Reference normal data (small subsample for descriptor fitting)
X_normal = X[y == 0]
# Take 10K random normals for descriptor reference
rng2 = np.random.RandomState(99)
ref_idx = rng2.choice(len(X_normal), min(10000, len(X_normal)), replace=False)
X_ref = X_normal[ref_idx]
print(f"  Descriptor reference: {len(X_ref):,} normal samples")

# ============================================================
# Phase 1: Standard engine scoring (simulation + kNN)  
# This is the old approach for comparison (on 100K subsample)
# ============================================================
print(f"\n{'='*90}")
print(f"  PHASE 1: Standard engine scoring (100K subsample, kNN-based)")
print(f"{'='*90}")

ENGINE_N = 100_000
idx_e = rng2.choice(N1, ENGINE_N, replace=False)
X_e, y_e, at_e = X[idx_e], y[idx_e], at[idx_e]

rows_standard = []
for EngCls, name in [(MolecularEngine, "Molecular(LJ)"),
                      (GravityModeEngine, "Gravity(N-body)"),
                      (HybridGravityEngine, "Hybrid(Mol+Grav)")]:
    print(f"\n  {name} on {ENGINE_N:,}...", end="", flush=True)
    try:
        eng = EngCls(calibrate='combined', target_far=0.05)
        t0 = time.perf_counter()
        s = eng.fit_score(X_e, y_e)
        elapsed = time.perf_counter() - t0
        r = op_metrics(y_e, s, f"{name} [kNN, 100K]")
        rows_standard.append(r)
        print(f" AUC={r['auc']:.4f} ({elapsed:.1f}s)")
    except Exception as ex:
        print(f" FAILED: {ex}")

print_table(rows_standard, "Standard kNN scoring (100K subsample)")

# ============================================================
# Phase 2: Reduced Tensor Descriptor on FULL 1M
# Simulate on subsample, then score 1M via O(Nd+d^3) descriptor
# ============================================================
print(f"\n{'='*90}")
print(f"  PHASE 2: Reduced Tensor Descriptor scoring on FULL 1,000,000 samples")
print(f"  Simulation: 5000 particles | Scoring: O(Nd+d^3) descriptor on 1M")
print(f"{'='*90}")

rows_tensor = []

for EngCls, name in [(MolecularEngine, "Molecular(LJ)"),
                      (GravityModeEngine, "Gravity(N-body)"),
                      (HybridGravityEngine, "Hybrid(Mol+Grav)")]:
    
    print(f"\n  --- {name} ---")
    
    # Step 1: Run simulation (subsample internally to max_samples)
    print(f"  [1] Simulating ({name})...", end="", flush=True)
    t0 = time.perf_counter()
    eng = EngCls(max_samples=5000)
    # Run on a small chunk to get the simulation state
    # Use 20K for simulation input so the engine subsamples to 5K internally
    sim_n = 20000
    idx_sim = rng2.choice(N1, sim_n, replace=False)
    X_sim, y_sim = X[idx_sim], y[idx_sim]
    _ = eng.fit_score(X_sim, y_sim)
    t_sim = time.perf_counter() - t0
    print(f" done ({t_sim:.1f}s)")
    
    # Step 2: Get reference data from engine's final normal positions
    if hasattr(eng, 'X_final_') and eng.X_final_ is not None:
        X_ref_eng = eng.X_final_
        # Get normal mask from simulation
        if hasattr(eng, 'molecular'):
            # Hybrid: use molecular's final state
            X_ref_eng = eng.molecular.X_final_
        print(f"  [2] Engine final state: {X_ref_eng.shape[0]} particles in {X_ref_eng.shape[1]}D")
    elif hasattr(eng, 'molecular'):
        X_ref_eng = eng.molecular.X_final_
        print(f"  [2] Hybrid molecular state: {X_ref_eng.shape[0]} particles")
    else:
        X_ref_eng = X_ref[:5000]
        print(f"  [2] Using raw reference: {X_ref_eng.shape[0]} samples")
    
    # Step 3: Fit ReducedTensorDescriptor on reference normals
    print(f"  [3] Fitting ReducedTensorDescriptor on reference...", end="", flush=True)
    t0 = time.perf_counter()
    desc = ReducedTensorDescriptor(k_neighbors=15, n_eigs=10)
    desc.fit(X_ref_eng)
    t_fit = time.perf_counter() - t0
    print(f" done ({t_fit:.1f}s)")
    print(f"      Complexity: {desc.complexity_info()['total']}")
    
    # Step 4: Transform ALL 1M points through the descriptor
    # Process in batches to manage memory
    BATCH = 100_000
    n_batches = (N1 + BATCH - 1) // BATCH
    print(f"  [4] Scoring {N1:,} samples via descriptor ({n_batches} batches of {BATCH:,})...")
    
    # Normalize all data with the same scaler as the engine used
    if hasattr(eng, 'scaler_') and eng.scaler_ is not None:
        scaler = eng.scaler_
    elif hasattr(eng, 'molecular') and eng.molecular.scaler_ is not None:
        scaler = eng.molecular.scaler_
    else:
        scaler = StandardScaler().fit(X)
    
    X_scaled = scaler.transform(X)
    
    all_descs = []
    t0 = time.perf_counter()
    for b in range(n_batches):
        start = b * BATCH
        end = min(start + BATCH, N1)
        X_batch = X_scaled[start:end]
        D_batch = desc.transform(X_batch)
        all_descs.append(D_batch)
        elapsed = time.perf_counter() - t0
        speed = (end) / elapsed if elapsed > 0 else 0
        print(f"\r      Batch {b+1}/{n_batches}: {end:,}/{N1:,} ({speed:,.0f} pts/s)  ", end="", flush=True)
    
    D_all = np.concatenate(all_descs, axis=0)
    t_score = time.perf_counter() - t0
    print(f"\n      Total scoring time: {t_score:.1f}s ({N1/t_score:,.0f} pts/s)")
    print(f"      Descriptor shape: {D_all.shape} ({desc.feature_names()[:3]}...{desc.feature_names()[-3:]})")
    
    # Step 5: Compute anomaly scores from descriptor
    # Method A: Full descriptor rank fusion
    s_full = descriptor_score(D_all, y == 0)
    r_full = op_metrics(y, s_full, f"{name} RTD-Full")
    rows_tensor.append(r_full)
    print(f"      RTD-Full AUC: {r_full['auc']:.4f}")
    
    # Method B: Morse index + Mahalanobis
    s_morse = descriptor_morse_score(D_all)
    r_morse = op_metrics(y, s_morse, f"{name} RTD-Morse")
    rows_tensor.append(r_morse)
    print(f"      RTD-Morse AUC: {r_morse['auc']:.4f}")
    
    # Method C: Just grad_norm (simplest signal)
    s_grad = D_all[:, 0]
    r_grad = op_metrics(y, s_grad, f"{name} RTD-Grad")
    rows_tensor.append(r_grad)
    print(f"      RTD-Grad AUC: {r_grad['auc']:.4f}")
    
    # Method D: Mahalanobis only
    s_maha = D_all[:, -5]
    r_maha = op_metrics(y, s_maha, f"{name} RTD-Maha")
    rows_tensor.append(r_maha)
    print(f"      RTD-Maha AUC: {r_maha['auc']:.4f}")
    
    # Stats
    morse_vals = D_all[:, -1]
    morse_anom = morse_vals[y == 1]
    morse_norm = morse_vals[y == 0]
    print(f"      Morse index stats: Normal={morse_norm.mean():.2f}+/-{morse_norm.std():.2f}, "
          f"Anomaly={morse_anom.mean():.2f}+/-{morse_anom.std():.2f}")
    t_total = t_sim + t_fit + t_score
    print(f"      TOTAL TIME: {t_total:.1f}s (sim={t_sim:.1f}, fit={t_fit:.1f}, score={t_score:.1f})")

# ============================================================
# Summary table
# ============================================================
print(f"\n\n{'='*90}")
print(f"  SUMMARY: 1M CIC-IDS-2017V2 Engine Benchmark")
print(f"{'='*90}")

print_table(rows_standard + rows_tensor, 
            f"All methods on CIC-IDS-2017 V2 ({N1:,} samples)")

# Scale comparison
print(f"\n  SCALE COMPARISON:")
print(f"  {'Method':<40} {'100K kNN':>10} {'1M RTD-Full':>12} {'1M RTD-Morse':>14}")
print(f"  {'-'*78}")
for ename in ["Molecular(LJ)", "Gravity(N-body)", "Hybrid(Mol+Grav)"]:
    std_match = [r for r in rows_standard if ename in r['label']]
    full_match = [r for r in rows_tensor if r['label'] == f"{ename} RTD-Full"]
    morse_match = [r for r in rows_tensor if r['label'] == f"{ename} RTD-Morse"]
    std_auc = f"{std_match[0]['auc']:.4f}" if std_match else "--"
    full_auc = f"{full_match[0]['auc']:.4f}" if full_match else "--"
    morse_auc = f"{morse_match[0]['auc']:.4f}" if morse_match else "--"
    print(f"  {ename:<40} {std_auc:>10} {full_auc:>12} {morse_auc:>14}")

print(f"\n  NOTE: RTD = Reduced Tensor Descriptor (O(Nd+d^3) vs O(N^2 d))")
print(f"  Standard kNN on 100K for baseline. RTD scores ALL 1M points.")
print(f"\n  Done.")
