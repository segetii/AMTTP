"""
GEOMETRIC COLLAPSE DETECTOR  — bidirectional + velocity-field trig
==================================================================

Key insight from geo_sync_angular.py diagnosis:
  GFC buildup  -> Q_mean DROPS below reference (banks converge toward centroid)
  SVB 2022-23  -> Q_mean RISES above reference (banks diverge outward)

So we need a BIDIRECTIONAL detector, not just an above-threshold alarm.

Two signals:
  (A) Q_deficit(t) = max(0, Q_P01_trailing - Q_mean(t))   <- collapse/systemic
  (B) Q_excess(t)  = max(0, Q_mean(t) - Q_P99_trailing)   <- expansion/individual

Plus the trigonometric velocity-field:
  (C) ΔD_i(t) = Δx_i(t) / ||Δx_i(t)||    <- direction of change for bank i
      R_v(t)  = || mean_i(ΔD_i(t)) ||     <- velocity alignment on C*
      High R_v -> all banks moving in same direction (synchronised motion)

      GFC: all banks CONTRACTING simultaneously -> ΔD_i all point inward
           -> R_v HIGH during 2007 buildup
      SVB: only a few banks moving, others unchanged -> R_v LOW

This is the angular/trig signal that DOES separate GFC from SVB.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import roc_auc_score
import warnings
warnings.filterwarnings('ignore')

# ── data ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "research" / "adaptive-friction" / "banklevel_enhanced" / \
        "gsib_cache_real" / "gsib_real_panel.npz"

data  = np.load(CACHE, allow_pickle=True)
X_raw = data['X']          # (T, N, d) = (76, 25, 5)
T, N, d = X_raw.shape
dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:T]

# crisis labels (quarter-level)
CRISIS_QUARTERS = {
    "2007-12-31", "2008-03-31", "2008-06-30", "2008-09-30",
    "2008-12-31", "2009-03-31", "2009-06-30",           # GFC
    "2011-09-30", "2011-12-31", "2012-03-31", "2012-06-30",  # Euro
}
y = np.array([1 if str(d)[:10] in CRISIS_QUARTERS else 0 for d in dates])

# ── prospective calibration (frozen ref: first 8 quarters = 2005Q1–2006Q4) ──
REF = 8
WINDOW = 8

from sklearn.preprocessing import RobustScaler
scaler = RobustScaler().fit(X_raw[:REF].reshape(-1, d))
X_s = np.array([scaler.transform(X_raw[t]) for t in range(T)])   # (T, N, d)

# ellipsoid semi-axes from reference covariance (frozen)
X_ref_flat = X_s[:REF].reshape(-1, d)
cov_ref = np.cov(X_ref_flat.T)
eigvals = np.linalg.eigvalsh(cov_ref)
alpha2  = np.maximum(eigvals, 1e-6)           # a_k^2
a2      = np.sort(alpha2)[::-1]               # descending

# ── ellipsoidal direction vectors ────────────────────────────────────────────
def ellipsoidal_directions(X_qt, a2):
    """Unit ellipsoidal normals: d_i = (x_i/a²) / ||x_i/a²||  ∈ S^(d-1)"""
    grad = X_qt / a2
    norm = np.linalg.norm(grad, axis=1, keepdims=True) + 1e-12
    return grad / norm

# ── Q scores ─────────────────────────────────────────────────────────────────
Q_all = np.array([np.mean(np.sum(X_s[t]**2 / a2, axis=1)) for t in range(T)])

# ── velocity directions ───────────────────────────────────────────────────────
def velocity_resultant(X_s, t):
    """R_v(t) = ||mean_i(Δx_i(t)/||Δx_i(t)||)||  -- velocity alignment"""
    if t == 0:
        return 0.0
    delta = X_s[t] - X_s[t-1]        # (N, d)  change in scaled features
    norms = np.linalg.norm(delta, axis=1, keepdims=True) + 1e-12
    vel_dirs = delta / norms           # unit velocity vectors
    return float(np.linalg.norm(vel_dirs.mean(axis=0)))

R_v = np.array([velocity_resultant(X_s, t) for t in range(T)])

# ── build scores using ADAPTIVE TRAILING WINDOW (no labels) ──────────────────
def trailing_bounds(series, t, window, lo_pct=1, hi_pct=99):
    start = max(0, t - window)
    hist = series[start:t]
    if len(hist) < 2:
        return np.nan, np.nan
    return np.percentile(hist, lo_pct), np.percentile(hist, hi_pct)

Q_deficit   = np.zeros(T)   # signal A: collapse (Q below P01)
Q_excess    = np.zeros(T)   # signal B: expansion (Q above P99)
R_v_excess  = np.zeros(T)   # signal C: velocity alignment above P90
Q_bidir     = np.zeros(T)   # A + B combined

for t in range(REF, T):
    p01, p99 = trailing_bounds(Q_all, t, WINDOW, 1, 99)
    _, pv90  = trailing_bounds(R_v,   t, WINDOW, 10, 90)
    if np.isnan(p01):
        continue
    Q_deficit[t]  = max(0.0, p01        - Q_all[t])
    Q_excess[t]   = max(0.0, Q_all[t]   - p99)
    R_v_excess[t] = max(0.0, R_v[t]     - pv90) if not np.isnan(pv90) else 0.0
    Q_bidir[t]    = Q_deficit[t] + Q_excess[t]

# also: 1/Q_raw for direct AUROC check
Q_inv = 1.0 / (Q_all + 1e-6)

# ── AUROC ─────────────────────────────────────────────────────────────────────
mask = np.arange(REF, T)
def auroc(sig):
    try: return roc_auc_score(y[mask], sig[mask])
    except: return float('nan')

print("=" * 72)
print("BIDIRECTIONAL GEOMETRIC COLLAPSE DETECTOR")
print("=" * 72)
print(f"{'Method':<28}  AUROC")
print("-" * 40)
print(f"{'Q_raw (above-only)':<28}  {auroc(Q_all):.4f}   [inverted GFC signal]")
print(f"{'Q_deficit (below P01)':<28}  {auroc(Q_deficit):.4f}   [collapse signal]")
print(f"{'Q_excess (above P99)':<28}  {auroc(Q_excess):.4f}   [expansion signal]")
print(f"{'Q_bidir (deficit+excess)':<28}  {auroc(Q_bidir):.4f}   [both directions]")
print(f"{'Q_inv (1/Q_raw)':<28}  {auroc(Q_inv):.4f}   [symmetry check -> ~0.72]")
print(f"{'R_v (velocity alignment)':<28}  {auroc(R_v):.4f}   [trig velocity field]")
print(f"{'R_v_excess (above P90)':<28}  {auroc(R_v_excess):.4f}   [velocity sync signal]")
print()

# ── Timeline with all signals ─────────────────────────────────────────────────
EVENTS = {
    "2007-03-31": "",
    "2007-06-30": "Bear Stearns HF",
    "2007-09-30": "Northern Rock",
    "2007-12-31": "*** CRISIS  <- paper 1st alarm",
    "2008-03-31": "*** CRISIS  Bear Stearns",
    "2008-06-30": "*** CRISIS",
    "2008-09-30": "*** CRISIS  LEHMAN",
    "2008-12-31": "*** CRISIS",
    "2009-03-31": "*** CRISIS",
    "2009-06-30": "*** CRISIS  GFC end",
    "2020-03-31": "COVID shock",
    "2023-03-31": "SVB/CS",
}

header = f"{'Date':<14}  {'Crisis':>8}  {'Q_raw':>7}  {'R_v':>5}  {'Deficit':>7}  " \
         f"{'Bidir':>6}  Note"
print(header)
print("-" * 80)
for t in range(T):
    ds = str(dates[t])[:10]
    is_crisis = "***" if ds in CRISIS_QUARTERS else ""
    note = EVENTS.get(ds, "")
    if is_crisis or note or t < REF + 1 or ds == "2006-12-31":
        print(f"{ds:<14}  {is_crisis:>8}  {Q_all[t]:>7.3f}  {R_v[t]:>5.3f}  "
              f"{Q_deficit[t]:>7.4f}  {Q_bidir[t]:>6.4f}  {note}")

print()
print("─" * 72)
print("VELOCITY FIELD DIAGNOSIS")
print("─" * 72)
# Compute mean R_v by period
def period_mean(arr, date_strs, start, end):
    vals = [arr[t] for t in range(T) if start <= str(dates[t])[:10] <= end]
    return np.mean(vals) if vals else 0.0

print(f"Reference 2005-2006:  mean R_v = {period_mean(R_v, dates, '2005-01-01', '2006-12-31'):.4f}")
print(f"GFC buildup 2007  :  mean R_v = {period_mean(R_v, dates, '2007-01-01', '2007-12-31'):.4f}")
print(f"GFC acute 2008    :  mean R_v = {period_mean(R_v, dates, '2008-01-01', '2008-12-31'):.4f}")
print(f"Recovery 2010-19  :  mean R_v = {period_mean(R_v, dates, '2010-01-01', '2019-12-31'):.4f}")
print(f"SVB/CS 2022-23    :  mean R_v = {period_mean(R_v, dates, '2022-01-01', '2023-12-31'):.4f}")
print()
print("EXPECTED:")
print("  R_v HIGH in 2007  -> all banks simultaneously contracting (synchronised motion)")
print("  R_v LOW  in 2023  -> idiosyncratic failures, diverse directions")
