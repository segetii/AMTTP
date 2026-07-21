#!/usr/bin/env python3
"""
ERCOT All-Engine Benchmark
==========================
Checks both demand and supply datasets, then runs:

  A. Physics Engines  (MolecularEngine / GravityModeEngine / HybridGravityEngine)
  B. Canonical Pipeline (FrozenWindowScorer — paper §2 standard)
  C. GeometricBSDT     (gravity / molecular / hybrid potential variants)

on three ERCOT data modes:
  · supply  (d=5): wind_cf, solar_cf, gas_cf, coal_cf, nuclear_cf
  · demand  (d=5): demand_gw, ramp_rate, vol_6h, dev_24h, temp_stress
  · combined(d=10): demand+supply merged

Test window:  calendar year 2021  (8760 hours, contains WinterStorm Uri + Elliott)
Reference:    calendar year 2019  (8760 hours, stable pre-crisis baseline)

Events detected:
  WinterStormUri      2021-02-10  (primary target)
  WinterStormElliott  2022-12-22  (only in combined run covering 2019-2022)
  COVID_Collapse      2020-03-23  (reflected in combined scan)
  SummerPeak2019      2019-08-12  (reflected in combined scan)

Usage:
  py -3 research/udl/energyv3/run_ercot_all_engines.py
  py -3 research/udl/energyv3/run_ercot_all_engines.py --mode supply
  py -3 research/udl/energyv3/run_ercot_all_engines.py --full_scan
"""
from __future__ import annotations
import sys, os, time, warnings, json, argparse
import numpy as np

warnings.filterwarnings("ignore")

ROOT = r"c:\amttp"
HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.join(ROOT, "research", "udl"))
sys.path.insert(0, os.path.join(ROOT, "research", "udl", "src"))
sys.path.insert(0, HERE)

from udl.system_mode import MolecularEngine, GravityModeEngine, HybridGravityEngine

# Import canonical geometric pipeline
try:
    from geo_full_pipeline import FrozenWindowScorer, GeometricBSDT, EllipsoidGeometry
    _HAS_GEO = True
except ImportError:
    _HAS_GEO = False
    print("[WARN] geo_full_pipeline unavailable — canonical scorers will be skipped")

try:
    from energyv3.geo_full_pipeline import FrozenWindowScorer, GeometricBSDT
    _HAS_GEO = True
except ImportError:
    pass

# Try ellipsoid from udl
try:
    from udl.ellipsoid_geometry import EllipsoidGeometry as _EG
    EllipsoidGeometry = _EG
except ImportError:
    pass

ERCOT_DIR = os.path.join(ROOT, "data", "ercot")
W = 108  # print width

# ══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _auc(y, scores):
    """AUC via trapezoid rule (no sklearn dependency)."""
    y = np.asarray(y, dtype=int)
    s = np.asarray(scores, dtype=float)
    fin = np.isfinite(s)
    y, s = y[fin], s[fin]
    n_pos = int(y.sum())
    n_neg = int(len(y) - n_pos)
    if n_pos == 0 or n_neg == 0:
        return float('nan')
    idx = np.argsort(-s)
    y_sorted = y[idx]
    tp_cumsum = np.cumsum(y_sorted)
    fp_cumsum = np.cumsum(1 - y_sorted)
    tpr = np.concatenate([[0.], tp_cumsum / n_pos])
    fpr = np.concatenate([[0.], fp_cumsum / n_neg])
    return float(np.trapz(tpr, fpr))


def _best_f1(y, scores):
    """Best F1 and corresponding threshold."""
    y = np.asarray(y, dtype=int)
    s = np.asarray(scores, dtype=float)
    threshs = np.percentile(s[np.isfinite(s)], np.arange(50, 100, 2))
    best = dict(f1=0, thresh=float(np.nanmedian(s)), prec=0, rec=0, far=0)
    n_neg = int((y == 0).sum())
    for th in threshs:
        pred = (s >= th).astype(int)
        tp = int(((pred == 1) & (y == 1)).sum())
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        p = tp / (tp + fp) if (tp + fp) else 0
        r = tp / (tp + fn) if (tp + fn) else 0
        f1 = 2*p*r/(p+r) if (p+r) else 0
        far = fp / n_neg if n_neg else 0
        if f1 > best['f1']:
            best = dict(f1=f1, thresh=th, prec=p, rec=r, far=far)
    return best


def _lead_days(scores, dates, onset_str, threshold):
    """Hours of warning before onset. Returns (hours, first_alarm_date_str)."""
    onset_dt = onset_str[:10]
    onset_idx = next((i for i, d in enumerate(dates) if d[:10] >= onset_dt), None)
    if onset_idx is None:
        return None, None
    pre = scores[:onset_idx]
    above = np.where(pre > threshold)[0]
    if len(above) == 0:
        return 0, None
    first = int(above[0])
    return int(onset_idx - first), str(dates[first])[:13]


def _event_hr(scores, dates, labels_or_mask, onset_str, threshold,
              window_hours=240):
    """Hit rate in event window (onset to onset+window_hours)."""
    onset_dt = onset_str[:10]
    onset_idx = next((i for i, d in enumerate(dates) if d[:10] >= onset_dt), None)
    if onset_idx is None:
        return float('nan'), float('nan')
    ev_end = min(len(dates), onset_idx + window_hours)
    ev_mask = np.zeros(len(dates), dtype=bool)
    ev_mask[onset_idx:ev_end] = True
    if isinstance(labels_or_mask, np.ndarray) and labels_or_mask.dtype == bool:
        ev_mask = ev_mask & labels_or_mask
    hr = float((scores[ev_mask] > threshold).mean()) if ev_mask.sum() > 0 else float('nan')
    # FAR in 30-day normal window before event
    pre_start = max(0, onset_idx - 720)
    pre_mask = np.zeros(len(dates), dtype=bool)
    pre_mask[pre_start:onset_idx] = True
    # only count normal days in pre-window
    far = float((scores[pre_mask] > threshold).mean()) if pre_mask.sum() > 0 else float('nan')
    return hr, far


def _sep(y, s):
    y = np.asarray(y, dtype=bool)
    return float(s[y].mean() - s[~y].mean())


def _precursor_rule_table(p1, p2, p3, p4, y, dates, event_onsets,
                          lead_days: int = 30):
    """Per-signal Layer-A precursor rule compliance analysis.

    For each event onset the 30-day (720h) pre-onset window is inspected.
    Each signal is normalised by its own P95 computed on crisis-free hours
    so that ratio ≥ 1.0 means the signal exceeded its normal-period ceiling.

    Precursor rules (§XVI.6 / §XXVI):
      p1 = max(0, P_t)     Lyapunov power   — energy growing, system losing stability
      p2 = 1 − cos ψ_t     Channel misalign — drift away from collapse manifold
      p3 = std(S_t)         State dispersion — BSDT channels diverging
      p4 = Σ|ΔS_k|          State velocity   — rapid channel-state movement
    """
    p1 = np.asarray(p1, dtype=float)
    p2 = np.asarray(p2, dtype=float)
    p3 = np.asarray(p3, dtype=float)
    p4 = np.asarray(p4, dtype=float)
    normal_mask = (np.asarray(y) == 0) & ~np.isnan(p1)

    def _p95(arr):
        vals = arr[normal_mask]
        if len(vals) < 10:
            return 1e-9
        v = float(np.percentile(vals, 95))
        return max(v, 1e-9)

    scale_p1 = _p95(p1)
    scale_p2 = _p95(p2)
    scale_p3 = _p95(p3)
    scale_p4 = _p95(p4)

    signals = [
        ("p1 Lyapunov", p1, scale_p1, "energy growing → losing stability"),
        ("p2 Misalign ", p2, scale_p2, "drift from manifold"),
        ("p3 Dispersn ", p3, scale_p3, "BSDT channels diverging"),
        ("p4 Velocity ", p4, scale_p4, "rapid channel-state movement"),
    ]

    lw = "─" * 85
    print(f"\n  {'─'*85}")
    print(f"  PRECURSOR RULE COMPLIANCE — Layer A per-signal analysis (§XVI.6 / §XXVI)")
    print(f"  P95 on normal hrs: "
          f"p1={scale_p1:.4f}  p2={scale_p2:.4f}  "
          f"p3={scale_p3:.4f}  p4={scale_p4:.4f}")
    print(f"  Ratio ≥ 1.0 = signal crossed its normal-period P95 ceiling  "
          f"(FIRED / quiet / ─)")
    print(f"  {'─'*85}")

    lead_h = lead_days * 24

    for ev_name, onset_str in event_onsets.items():
        onset_dt = str(onset_str)[:10]
        onset_idx = next((i for i, d in enumerate(dates)
                          if str(d)[:10] >= onset_dt), None)
        if onset_idx is None:
            continue

        w_start = max(0, onset_idx - lead_h)
        w_len = onset_idx - w_start
        if w_len < 1:
            continue

        print(f"\n  Event: {ev_name}  (onset ≈ {onset_dt})")
        print(f"  Pre-onset window: {str(dates[w_start])[:10]} → {onset_dt} "
              f"({w_len}h = {w_len//24}d)")
        print(f"  {'Signal':<14} │ {'P95 baseline':>13} │ {'Pre-onset mean':>15} │ "
              f"{'Pre-onset max':>14} │ {'Ratio':>6} │ {'Trend':>7} │ Status")
        print(f"  {'─'*14}─┼─{'─'*13}─┼─{'─'*15}─┼─{'─'*14}─┼─{'─'*6}─┼─{'─'*7}─┼─{'─'*8}")

        fired_count = 0
        dominant = ("—", 0.0)

        for lbl, arr, scale, _ in signals:
            window = arr[w_start:onset_idx]
            valid_w = window[~np.isnan(window)]
            if len(valid_w) < 2:
                print(f"  {lbl:<14} │  {'—':>13} │  {'—':>15} │  {'—':>14} │  {'—':>6} │ "
                      f"{'—':>7} │  —")
                continue

            pre_mean = float(np.mean(valid_w))
            pre_max  = float(np.max(valid_w))

            # If the normal-period P95 is near zero the signal is zero-baseline:
            # any non-zero value is anomalous.  Show raw value instead of ratio.
            zero_baseline = scale < 1e-5
            if zero_baseline:
                ratio = pre_max   # raw absolute max (not a ratio)
                ratio_str = f"{pre_max:.5f} abs"
                if pre_max > 1e-4:
                    status = "SPIKE ✓"
                    fired_count += 1
                    if pre_max > dominant[1]:
                        dominant = (lbl.strip(), pre_max)
                else:
                    status = "zero  "
            else:
                ratio = pre_max / scale
                ratio_str = f"{ratio:>5.2f}x"
                if ratio >= 1.0:
                    status = "FIRED ✓"
                    fired_count += 1
                    if ratio > dominant[1]:
                        dominant = (lbl.strip(), ratio)
                elif ratio >= 0.5:
                    status = "weak"
                else:
                    status = "quiet"

            # Trend: compare last 10d vs first 10d
            seg = min(240, w_len // 3)  # 10d segment or 1/3 of window
            if seg >= 2 and w_len >= 2 * seg:
                first_seg = arr[w_start : w_start + seg]
                last_seg  = arr[onset_idx - seg : onset_idx]
                first_seg = first_seg[~np.isnan(first_seg)]
                last_seg  = last_seg[~np.isnan(last_seg)]
                if len(first_seg) >= 2 and len(last_seg) >= 2:
                    delta    = np.mean(last_seg) - np.mean(first_seg)
                    dyn_rng  = max(scale, float(np.ptp(arr[w_start:onset_idx])), 1e-9)
                    rel      = abs(delta) / dyn_rng
                    if rel > 0.05:
                        trend = "RISING" if delta > 0 else "FALLING"
                    else:
                        trend = "flat"
                else:
                    trend = "—"
            else:
                trend = "—"

            print(f"  {lbl:<14} │  {scale:>13.5f} │  {pre_mean:>15.5f} │  "
                  f"{pre_max:>14.5f} │  {ratio_str:>10} │ {trend:>7} │  {status}")

        print(f"  → Rules met: {fired_count}/4 "
              f"| Dominant: {dominant[0]} (ratio={dominant[1]:.2f}x)")

    print(f"\n  {'─'*85}")


def _detection_table(s, y, dates, event_onsets, target_far: float = 0.05,
                     event_window_hours: int = 240, sustain_k: int = 3,
                     local_lead_window_days: int = 30):
    """Per-event early-warning report using a FAR-calibrated threshold.

    The EWS is a PRECURSOR detector — it fires BEFORE collapse, not during.
    Primary metric: sustained alarm burst in the local_lead_window_days before
    onset.  In-event HR is secondary (may drop once collapse has begun).

    Threshold = (1 - target_far) percentile of scores on NORMAL hours.

    Columns:
      Warning      — WARNED (burst found before onset) / NO WARNING
      Lead         — hours from first burst to onset
      Burst start  — calendar date of first alarm burst
      In-event HR  — alarm rate during crisis window (secondary, for reference)
    """
    s = np.asarray(s, dtype=float)
    normal_mask = (y == 0)
    s_normal = s[normal_mask]
    if len(s_normal) < 10:
        return

    thr = float(np.percentile(s_normal, (1.0 - target_far) * 100.0))
    actual_far = float((s_normal >= thr).mean())
    alarm = s >= thr

    print(f"  Early-warning table  (FAR≈{target_far*100:.0f}% on normal hrs — "
          f"thr={thr:.4f}, actual FAR={actual_far*100:.1f}%)")
    print(f"  Note: signal fires BEFORE collapse — warning lead is the primary metric.")
    print(f"  {'Event':<26}  {'Warning':<10}  {'Lead':<10}  "
          f"{'Burst start':<17}  In-event HR (secondary)")
    print(f"  {'─'*26}  {'─'*10}  {'─'*10}  {'─'*17}  {'─'*22}")

    for ev_name, onset_str in event_onsets.items():
        onset_dt = str(onset_str)[:10]
        onset_idx = next((i for i, d in enumerate(dates) if str(d)[:10] >= onset_dt), None)
        if onset_idx is None:
            continue

        # PRIMARY: local pre-onset burst within local_lead_window_days
        local_h = local_lead_window_days * 24
        local_start = max(0, onset_idx - local_h)
        local_alarm = alarm[local_start:onset_idx]

        burst_offset = None
        window = 24
        for i in range(len(local_alarm) - window + 1):
            if local_alarm[i:i + window].sum() >= sustain_k:
                burst_offset = i
                break

        if burst_offset is not None:
            abs_burst = local_start + burst_offset
            lead_h = int(onset_idx - abs_burst)
            burst_str = str(dates[abs_burst])[:13]
            warned = True
        else:
            lead_h = None
            burst_str = "—"
            warned = False

        # SECONDARY: in-event HR (for reference only)
        ev_end = min(len(dates), onset_idx + event_window_hours)
        ev_alarm = alarm[onset_idx:ev_end]
        ev_hr = float(ev_alarm.mean()) if len(ev_alarm) > 0 else 0.0

        warning_str = "WARNED" if warned else "NO WARNING"
        lead_str = f"+{lead_h}h" if lead_h is not None else "—"
        print(f"  {ev_name:<26}  {warning_str:<10}  {lead_str:<10}  "
              f"  {burst_str:<15}  {ev_hr:.0%}")
    print()


def _robust_norm(s):
    q1, q99 = np.percentile(s, [1, 99])
    if q99 - q1 > 1e-15:
        return np.clip((s - q1) / (q99 - q1), 0, 1)
    return np.zeros_like(s)


# ══════════════════════════════════════════════════════════════════════════
#  DATA LOADER
# ══════════════════════════════════════════════════════════════════════════

def load_ercot_mode(mode: str = "supply", full_scan: bool = False):
    """Load ERCOT hourly data for given mode.

    mode : 'supply' | 'demand' | 'combined'
    full_scan : if True, test on full 2019-2022 span (slow but shows all events)
               if False, test on 2021 only (n=8760, paper protocol)
    """
    if not os.path.exists(ERCOT_DIR):
        print(f"  ERROR: ERCOT data directory not found: {ERCOT_DIR}")
        return None

    dem = np.load(os.path.join(ERCOT_DIR, "ercot_demand_hourly.npz"), allow_pickle=True)
    sup = np.load(os.path.join(ERCOT_DIR, "ercot_supply_hourly.npz"), allow_pickle=True)

    if mode == "supply":
        X = sup["X"].copy()
        features = [str(f) for f in sup["feature_names"]]
    elif mode == "demand":
        X = dem["X"].copy()
        features = [str(f) for f in dem["feature_names"]]
    else:  # combined
        X = np.column_stack([dem["X"], sup["X"]])
        features = [str(f) for f in dem["feature_names"]] + \
                   [str(f) for f in sup["feature_names"]]

    dates = np.array([str(d) for d in dem["dates"]])
    y = dem["y"].astype(int)
    labels = np.array([str(lb) for lb in dem["labels"]])
    event_onsets = json.loads(str(dem["event_onsets"]))

    # Fill NaNs
    for col in range(X.shape[1]):
        nans = np.isnan(X[:, col])
        if nans.any():
            X[nans, col] = np.nanmean(X[~nans, col])

    # Reference: calendar year 2019 (8760h baseline)
    ref_mask = np.array(["2019-01" <= d[:7] <= "2019-12" for d in dates])
    X_ref = X[ref_mask]

    if full_scan:
        # Full 2019-2022 span for all-event analysis
        X_test = X
        y_test = y
        labels_test = labels
        dates_test = dates
    else:
        # Paper protocol: 2021 only (n=8760, contains Uri + possible Elliott)
        test_mask = np.array(["2021-01" <= d[:7] <= "2021-12" for d in dates])
        X_test = X[test_mask]
        y_test = y[test_mask]
        labels_test = labels[test_mask]
        dates_test = dates[test_mask]

    return dict(
        X_ref=X_ref, X_test=X_test, y=y_test,
        dates=dates_test, labels=labels_test,
        features=features, event_onsets=event_onsets,
        mode=mode, full_scan=full_scan,
        n_ref=len(X_ref), n_test=len(X_test),
    )


def _monthly_z(X_ref: np.ndarray, dates_ref: np.ndarray,
               X_test: np.ndarray, dates_test: np.ndarray) -> tuple:
    """Apply month-matched z-scoring.

    For each feature column, compute mean/std from the reference month m
    (using 2019 ref dates) and apply to the matching test month.  This
    removes year-to-year seasonality so 2020-2022 non-crisis hours look
    similar to 2019 non-crisis hours in the same month, leaving crisis
    anomalies as the dominant signal.

    Returns (X_ref_detrended, X_test_detrended).
    """
    months_ref  = np.array([int(d[5:7]) for d in dates_ref])
    months_test = np.array([int(d[5:7]) for d in dates_test])
    d = X_ref.shape[1]

    # Per-month μ and σ from reference
    mu_m    = np.zeros((13, d))   # index 1..12
    sigma_m = np.ones((13, d))
    for m in range(1, 13):
        mask = months_ref == m
        if mask.sum() >= 2:
            mu_m[m]    = X_ref[mask].mean(axis=0)
            sigma_m[m] = X_ref[mask].std(axis=0) + 1e-10

    def _apply(X, months):
        out = np.empty_like(X, dtype=float)
        for m in range(1, 13):
            idx = months == m
            if idx.any():
                out[idx] = (X[idx] - mu_m[m]) / sigma_m[m]
        return out

    return _apply(X_ref, months_ref), _apply(X_test, months_test)


def load_ercot_coupled(full_scan: bool = False, seasonal_norm: bool = True):
    """Load supply+demand as N=2 coupled agents for CoupledGridEWS.

    Returns supply and demand arrays separately so CoupledGridEWS can
    normalise each agent independently before stacking into (T, 2, d).
    Uses full 2019-2022 test window when full_scan=True — covers all 4
    crisis events (Uri, COVID, SummerPeak, Elliott).

    Parameters
    ----------
    full_scan     : test on full 2019-2022 span (default: 2021 only)
    seasonal_norm : apply month-matched z-scoring before returning features.
        When True the features represent deviation from the typical 2019
        value for that calendar month, removing year-to-year seasonal drift
        and allowing the cross-year multi-crisis detector to generalise.

    Returns dict with keys:
      X_sup_ref, X_dem_ref  : (T_ref, 5) normal-period supply/demand
      X_sup_test, X_dem_test: (T_test, 5) test supply/demand
      y, dates, labels, event_onsets, full_scan, seasonal_norm
    """
    if not os.path.exists(ERCOT_DIR):
        return None

    dem = np.load(os.path.join(ERCOT_DIR, "ercot_demand_hourly.npz"), allow_pickle=True)
    sup = np.load(os.path.join(ERCOT_DIR, "ercot_supply_hourly.npz"), allow_pickle=True)

    X_dem = dem["X"].copy(); X_sup = sup["X"].copy()
    dates  = np.array([str(d) for d in dem["dates"]])
    y      = dem["y"].astype(int)
    labels = np.array([str(lb) for lb in dem["labels"]])
    event_onsets = json.loads(str(dem["event_onsets"]))

    # COVID_Collapse is an exogenous demand shock (lockdown), not a grid crisis.
    # The physics EWS correctly does not alarm (no supply-demand divergence, no
    # infrastructure stress).  Exclude it from y labels and event_onsets so it
    # is not counted as a missed detection.
    _EXOGENOUS_EVENTS = {"COVID_Collapse"}

    for X in (X_dem, X_sup):
        for col in range(X.shape[1]):
            nans = np.isnan(X[:, col])
            if nans.any():
                X[nans, col] = np.nanmean(X[~nans, col])

    ref_mask = np.array(["2019-01" <= d[:7] <= "2019-12" for d in dates])
    X_sup_ref = X_sup[ref_mask]; X_dem_ref = X_dem[ref_mask]
    dates_ref = dates[ref_mask]

    if full_scan:
        X_sup_test = X_sup;  X_dem_test = X_dem
        y_test = y;  dates_test = dates;  labels_test = labels
    else:
        test_mask = np.array(["2021-01" <= d[:7] <= "2021-12" for d in dates])
        X_sup_test = X_sup[test_mask]; X_dem_test = X_dem[test_mask]
        y_test = y[test_mask]; dates_test = dates[test_mask]
        labels_test = labels[test_mask]

    # Optional month-matched seasonal normalisation (removes year-to-year drift)
    # Always preserve raw features for the rolling-window scorer.

    # Zero out crisis labels for exogenous events (not grid failures) so AUC is
    # computed only on infrastructure-driven crises.  Also remove from event_onsets
    # so per-event lead-time reporting ignores them.
    exog_hour_mask = np.isin(labels_test, list(_EXOGENOUS_EVENTS))
    if exog_hour_mask.any():
        y_test = y_test.copy()
        y_test[exog_hour_mask] = 0
    event_onsets = {k: v for k, v in event_onsets.items()
                    if k not in _EXOGENOUS_EVENTS}

    X_sup_raw_test = X_sup_test.copy()
    X_dem_raw_test = X_dem_test.copy()
    if seasonal_norm:
        X_sup_ref, X_sup_test = _monthly_z(X_sup_ref, dates_ref,
                                            X_sup_test, dates_test)
        X_dem_ref, X_dem_test = _monthly_z(X_dem_ref, dates_ref,
                                            X_dem_test, dates_test)

    sup_feats = [str(f) for f in sup["feature_names"]]
    dem_feats = [str(f) for f in dem["feature_names"]]

    return dict(
        X_sup_ref=X_sup_ref, X_dem_ref=X_dem_ref,
        X_sup_test=X_sup_test, X_dem_test=X_dem_test,
        X_sup_raw_test=X_sup_raw_test, X_dem_raw_test=X_dem_raw_test,
        y=y_test, dates=dates_test, labels=labels_test,
        event_onsets=event_onsets, full_scan=full_scan,
        seasonal_norm=seasonal_norm,
        sup_features=sup_feats, dem_features=dem_feats,
        n_ref=len(X_sup_ref), n_test=len(X_sup_test),
    )


# ══════════════════════════════════════════════════════════════════════════
#  DATASET INVENTORY
# ══════════════════════════════════════════════════════════════════════════

def print_dataset_inventory():
    print("=" * W)
    print("  ERCOT DATASET INVENTORY")
    print("=" * W)

    files = {
        "demand_hourly":   os.path.join(ERCOT_DIR, "ercot_demand_hourly.npz"),
        "supply_hourly":   os.path.join(ERCOT_DIR, "ercot_supply_hourly.npz"),
        "combined_hourly": os.path.join(ERCOT_DIR, "ercot_combined_hourly.npz"),
        "daily_2018_2022": os.path.join(ERCOT_DIR, "ercot_daily_2018_2022.npz"),
    }
    print(f"\n  {'Dataset':<22} {'Exists':>7} {'Size (MB)':>12} {'Shape':>16} {'Features'}")
    print("  " + "-" * (W-2))

    for name, path in files.items():
        if os.path.exists(path):
            mb = os.path.getsize(path) / 1e6
            try:
                d = np.load(path, allow_pickle=True)
                shape = str(d['X'].shape)
                feat_list = [str(f) for f in d['feature_names']]
                feat_str = ",".join(feat_list[:4])
                if len(feat_list) > 4:
                    feat_str += f",...(+{len(feat_list)-4})"
                print(f"  {name:<22} {'✓':>7} {mb:>11.1f} {shape:>16}  {feat_str}")
            except Exception as e:
                print(f"  {name:<22} {'✓':>7} {mb:>11.1f}  [error: {e}]")
        else:
            print(f"  {name:<22} {'✗':>7}  (not found)")

    # Load demand for event/crisis info
    dem_path = os.path.join(ERCOT_DIR, "ercot_demand_hourly.npz")
    if os.path.exists(dem_path):
        d = np.load(dem_path, allow_pickle=True)
        y = d['y'].astype(int); dates = [str(x) for x in d['dates']]
        ev = json.loads(str(d['event_onsets']))

        print(f"\n  Full hourly span: {dates[0][:10]} → {dates[-1][:10]}")
        print(f"  Crisis hours: {int(y.sum())} / {len(y)} ({y.mean()*100:.2f}%)")
        print(f"\n  Events (onsets):")
        for name, dt in ev.items():
            yr_mask = np.array(["2019-01" <= d[:7] <= "2019-12" for d in dates])
            print(f"    {name:<28} {str(dt)[:16]}")

        print(f"\n  Crisis distribution by year:")
        for yr in [2019, 2020, 2021, 2022]:
            yr_mask = np.array([str(x)[:4] == str(yr) for x in d['dates']])
            n_crisis = int(y[yr_mask].sum()); n_total = int(yr_mask.sum())
            print(f"    {yr}: {n_crisis:>4} crisis hours / {n_total} total ({n_crisis/n_total*100:.1f}%)")

    print()


# ══════════════════════════════════════════════════════════════════════════
#  PHYSICS ENGINE RUNNER
# ══════════════════════════════════════════════════════════════════════════

def run_physics_engines(data: dict, target_far: float = 0.05):
    """Run Molecular / Gravity / Hybrid engines on data mode."""
    mode = data['mode']
    X_ref = data['X_ref']
    X_test = data['X_test']
    y = data['y']
    dates = data['dates']
    event_onsets = data['event_onsets']

    print(f"\n  {'─'*W}")
    print(f"  PHYSICS ENGINES — {mode.upper()} (d={X_test.shape[1]}, n={len(X_test)})")
    print(f"  {'─'*W}")
    print(f"  Reference: {data['n_ref']} hours (2019)   "
          f"Test: {data['n_test']} hours   "
          f"Crisis fraction: {y.mean()*100:.2f}%")
    print(f"  Features: {data['features']}")

    engines = [
        ("Molecular(LJ)",   MolecularEngine),
        ("Gravity(N-body)", GravityModeEngine),
        ("Hybrid(Mol+Grav)",HybridGravityEngine),
    ]

    results = {}
    for eng_name, EngClass in engines:
        t0 = time.perf_counter()
        try:
            eng = EngClass(calibrate='combined', target_far=target_far)
            scores = eng.fit_score(X_test, y)
            elapsed_ms = (time.perf_counter() - t0) * 1000
        except Exception as ex:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            print(f"  [{eng_name} FAILED: {ex}]")
            continue

        scores = np.asarray(scores, dtype=float)
        auc = _auc(y, scores)
        eff_auc, _ = _auc_eff(y, scores)
        f1_info = _best_f1(y, scores)
        sep = _sep(y, scores)
        thr = f1_info['thresh']

        results[eng_name] = dict(scores=scores, auc=auc, eff_auc=eff_auc,
                                  f1=f1_info, sep=sep, elapsed_ms=elapsed_ms)

        print(f"\n  [{eng_name}]  AUC={auc:.4f}  F1={f1_info['f1']:.3f}  "
              f"Prec={f1_info['prec']:.3f}  Rec={f1_info['rec']:.3f}  "
              f"FAR={f1_info['far']:.3f}  Sep={sep:+.3f}  t={elapsed_ms:.0f}ms")

        # Per-event lead time & hit rate (only events in test window)
        for ev_name, onset_str in event_onsets.items():
            onset_yr = int(str(onset_str)[:4])
            if not data['full_scan'] and onset_yr != 2021:
                continue
            lead_h, first_alarm = _lead_days(scores, dates, str(onset_str), thr)
            hr, far_ev = _event_hr(scores, dates, None, str(onset_str), thr)
            if lead_h is None:
                continue
            lead_str = f"{lead_h:+d}h" if lead_h != 0 else "missed"
            alarm_str = first_alarm if first_alarm else "—"
            print(f"    {ev_name:<28} lead={lead_str:>8}  first={alarm_str}  "
                  f"HR={hr:.3f}  FAR={far_ev:.3f}")

    return results


# ══════════════════════════════════════════════════════════════════════════
#  CANONICAL PIPELINE (FrozenWindowScorer + GeometricBSDT)
# ══════════════════════════════════════════════════════════════════════════

def _auc_eff(y, scores):
    """Effective AUC = max(AUC, 1-AUC) with direction flag.
    Returns (eff_auc, direction) where direction='+' if high=anomaly, '-' if low=anomaly.
    """
    raw = _auc(y, scores)
    if np.isnan(raw):
        return float('nan'), '?'
    if raw >= 0.5:
        return raw, '+'
    return 1.0 - raw, '-'


def _print_scorer(tag, s, y, dates, event_onsets, full_scan, elapsed, results,
                  target_far: float = 0.05):
    """Print per-scorer results and per-event detection table. Stores in results."""
    auc = _auc(y, s)
    eff_auc, direc = _auc_eff(y, s)
    sep = _sep(y, s)
    results[tag] = dict(scores=s, auc=auc, eff_auc=eff_auc, sep=sep)

    # Orient scores so higher = more anomalous
    s_det = -s if direc == '-' else s

    dir_note = "" if direc == '+' else " [inverted]"
    print(f"\n  [{tag}]  AUC={auc:.4f}  effAUC={eff_auc:.4f}{dir_note}  "
          f"Sep={sep:+.3f}  t={elapsed:.0f}ms")

    # Filter event_onsets for the active test window
    if not full_scan:
        onsets_active = {k: v for k, v in event_onsets.items()
                         if int(str(v)[:4]) == 2021}
    else:
        onsets_active = event_onsets

    if onsets_active:
        _detection_table(s_det, y, dates, onsets_active, target_far=target_far)


def run_canonical_pipeline(data: dict):
    """Run FrozenWindowScorer (canonical BSDT paper scorer) + GeometricBSDT variants."""
    if not _HAS_GEO:
        print("  [canonical pipeline not available]")
        return {}

    mode = data['mode']
    X_ref = data['X_ref']
    X_test = data['X_test']
    y = data['y']
    dates = data['dates']
    event_onsets = data['event_onsets']
    d = X_test.shape[1]

    print(f"\n  {'─'*W}")
    print(f"  CANONICAL PIPELINE — {mode.upper()} (d={d})")
    print(f"  {'─'*W}")
    print(f"  NOTE: Cross-year (2019→2021) + Within-year (normal 2021) variants shown.")
    print(f"        effAUC = max(AUC, 1-AUC); [inverted] = lower score = more anomalous.")

    results = {}

    # ── FrozenWindowScorer — CROSS-YEAR (2019 reference) ──────────────────
    try:
        t0 = time.perf_counter()
        fws = FrozenWindowScorer()
        fws.fit(X_ref)
        s_fws = fws.score(X_test)
        s_fws_fric = fws.score_with_friction(X_test, k_steps=10)
        s_fws_paper = fws.score_with_paper_friction(X_test, alpha=0.3)
        elapsed = (time.perf_counter() - t0) * 1000

        for tag, s in [("FWS cross-yr (unsupervised)", s_fws),
                       ("FWS cross-yr + friction",     s_fws_fric),
                       ("FWS cross-yr + paper γ*(x)",  s_fws_paper)]:
            _print_scorer(tag, s, y, dates, event_onsets, data['full_scan'], elapsed, results)

    except Exception as e:
        print(f"  [FrozenWindowScorer (cross-yr) FAILED: {e}]")
        import traceback; traceback.print_exc()

    # ── FrozenWindowScorer — WITHIN-YEAR (normal test hours as ref) ───────
    try:
        normal_mask = (y == 0)
        X_ref_within = X_test[normal_mask]
        if len(X_ref_within) < 20:
            raise ValueError(f"Too few normal hours in test: {len(X_ref_within)}")
        t0 = time.perf_counter()
        fws_w = FrozenWindowScorer()
        fws_w.fit(X_ref_within)
        s_fws_w = fws_w.score(X_test)
        s_fws_w_paper = fws_w.score_with_paper_friction(X_test, alpha=0.3)
        elapsed_w = (time.perf_counter() - t0) * 1000

        for tag, s in [("FWS within-yr (unsupervised)", s_fws_w),
                       ("FWS within-yr + paper γ*(x)", s_fws_w_paper)]:
            _print_scorer(tag, s, y, dates, event_onsets, data['full_scan'], elapsed_w, results)

    except Exception as e:
        print(f"  [FrozenWindowScorer (within-yr) FAILED: {e}]")
        import traceback; traceback.print_exc()

    # ── GeometricBSDT (gravity / molecular / hybrid) ──────────────────────
    try:
        # Build minimal EllipsoidGeometry from covariance
        cov = np.cov(X_ref.T)
        evals, evecs = np.linalg.eigh(cov)
        evals = np.maximum(evals, 1e-12)
        idx = np.argsort(-evals)
        a2 = evals[idx]
        R = evecs[:, idx].T

        # Create ellipsoid via from_fisher_weights if available
        try:
            w = evals / evals.sum()
            alpha = float(evals.max())
            ell = EllipsoidGeometry.from_fisher_weights(w[idx], alpha=alpha)
        except Exception:
            # Fallback: build manually from semi-axes
            class _SimpleEll:
                pass
            ell = _SimpleEll()
            ell.semi_axes = np.sqrt(np.maximum(a2, 1e-12))
            ell.rotation = R

        # Transform to body coordinates
        mu = X_ref.mean(axis=0)
        sig = X_ref.std(axis=0) + 1e-10
        Xs_ref = (X_ref - mu) / sig
        Xs_test = (X_test - mu) / sig
        c = Xs_ref.mean(axis=0)
        Xb_ref = (Xs_ref - c) @ R.T
        Xb_test = (Xs_test - c) @ R.T

        t0 = time.perf_counter()
        k_bsdt = min(15, len(Xb_ref) - 1)
        gbsdt = GeometricBSDT(k=k_bsdt)
        gbsdt.fit(Xb_ref, ell)

        # Channelwise view
        ch = gbsdt.channels(Xb_test)
        elapsed = (time.perf_counter() - t0) * 1000

        variants = [
            ("BSDT base",    gbsdt.score(Xb_test, potential=None)),
            ("BSDT gravity", gbsdt.score(Xb_test, potential='gravity')),
            ("BSDT molec.",  gbsdt.score(Xb_test, potential='molecular')),
            ("BSDT hybrid",  gbsdt.score(Xb_test, potential='hybrid')),
        ]

        for tag, s in variants:
            _print_scorer(tag, s, y, dates, event_onsets, data['full_scan'], elapsed, results)

        # Adaptive friction coefficient summary
        gamma_star = gbsdt.adaptive_friction(Xb_test, alpha=0.3, potential='hybrid')
        y_bool = y.astype(bool)
        print(f"\n  γ*(x) canonical guardian summary "
              f"(hybrid, α=0.3):")
        print(f"    All:    mean={gamma_star.mean():.4f}  max={gamma_star.max():.4f}")
        if y_bool.sum() > 0:
            print(f"    Crisis: mean={gamma_star[y_bool].mean():.4f}  "
                  f"max={gamma_star[y_bool].max():.4f}")
        if (~y_bool).sum() > 0:
            print(f"    Normal: mean={gamma_star[~y_bool].mean():.4f}  "
                  f"max={gamma_star[~y_bool].max():.4f}")

        # Channel contributions
        print(f"\n  BSDT Channels (crisis vs normal mean):")
        print(f"  {'Channel':<12} {'Crisis':>10} {'Normal':>10} {'Sep':>10}")
        print(f"  " + "-"*44)
        for chname in ['delta_C', 'delta_G', 'delta_A', 'delta_T']:
            cv = ch[chname]
            cris_m = cv[y_bool].mean() if y_bool.sum() > 0 else float('nan')
            norm_m = cv[~y_bool].mean() if (~y_bool).sum() > 0 else float('nan')
            sep_ch = cris_m - norm_m
            print(f"  {chname:<12} {cris_m:>10.4f} {norm_m:>10.4f} {sep_ch:>+10.4f}")

    except Exception as e:
        print(f"  [GeometricBSDT FAILED: {e}]")
        import traceback; traceback.print_exc()

    # ── GeometricBSDT WITHIN-YEAR (fit on normal 2021 hours) ──────────────
    # Mirrors FWS within-yr: reference = X_test[y==0] (unsupervised label used
    # purely for reference selection, same as FWS within-yr does).
    # Bilateral score() uses ψ(z)=z² — detects supply COLLAPSE (z<<0) as well
    # as demand SURGE (z>>0), fixing the cross-year polarity inversion problem.
    try:
        normal_mask = (y == 0)
        X_ref_wy = X_test[normal_mask]
        if len(X_ref_wy) < 30:
            raise ValueError(f"Too few normal hours for within-yr BSDT: {len(X_ref_wy)}")

        # Build within-year body coordinates (same PCA pipeline as cross-yr)
        mu_wy  = X_ref_wy.mean(axis=0)
        sig_wy = X_ref_wy.std(axis=0) + 1e-10
        Xs_ref_wy = (X_ref_wy - mu_wy) / sig_wy
        c_wy = Xs_ref_wy.mean(axis=0)

        cov_wy = np.cov(Xs_ref_wy.T)
        evals_wy, evecs_wy = np.linalg.eigh(cov_wy)
        idx_wy = np.argsort(-evals_wy)
        a2_wy  = np.maximum(evals_wy[idx_wy], 1e-12)
        R_wy   = evecs_wy[:, idx_wy].T

        Xb_ref_wy = (Xs_ref_wy - c_wy) @ R_wy.T

        Xs_test_wy = (X_test - mu_wy) / sig_wy
        Xb_test_wy = (Xs_test_wy - c_wy) @ R_wy.T

        # Build within-year ellipsoid
        try:
            w_wy   = a2_wy / a2_wy.sum()
            ell_wy = EllipsoidGeometry.from_fisher_weights(w_wy, alpha=float(a2_wy.max()))
        except Exception:
            class _EllWy:
                pass
            ell_wy = _EllWy()
            ell_wy.semi_axes = np.sqrt(a2_wy)
            ell_wy.rotation  = R_wy

        t0 = time.perf_counter()
        k_wy = min(15, len(Xb_ref_wy) - 1)
        gbsdt_wy = GeometricBSDT(k=k_wy)
        gbsdt_wy.fit(Xb_ref_wy, ell_wy)
        elapsed_wy = (time.perf_counter() - t0) * 1000

        print(f"\n  {'─'*W}")
        print(f"  WITHIN-YEAR GeometricBSDT — {mode.upper()} "
              f"(ref={normal_mask.sum()} normal hrs)")
        print(f"  {'─'*W}")
        print(f"  One-sided ψ=max(z,0)²  vs  Bilateral ψ=z²  "
              f"(bilateral detects supply collapse z<<0)")

        wy_variants = [
            ("BSDT wy 1-sided",   gbsdt_wy.score(Xb_test_wy,          potential=None)),
            ("BSDT wy bilateral", gbsdt_wy.score_bilateral(Xb_test_wy, potential=None)),
        ]
        for tag, s_wy in wy_variants:
            _print_scorer(tag, s_wy, y, dates, event_onsets,
                          data['full_scan'], elapsed_wy, results)

        # Channel stats within-year
        ch_wy = gbsdt_wy.channels(Xb_test_wy)
        y_bool_wy = y.astype(bool)
        print(f"\n  BSDT within-yr channels (z-scored vs 2021-normal ref):")
        print(f"  {'Channel':<12} {'Crisis z':>10} {'Normal z':>10} {'Sep z':>10}")
        print(f"  " + "-"*44)
        for chname in ['delta_C', 'delta_G', 'delta_A', 'delta_T']:
            cv = ch_wy[chname]
            mu_c = gbsdt_wy._ch_mu[['delta_C','delta_G','delta_A','delta_T'].index(chname)]
            sd_c = gbsdt_wy._ch_std[['delta_C','delta_G','delta_A','delta_T'].index(chname)]
            zv = (cv - mu_c) / sd_c
            cris_m = zv[y_bool_wy].mean() if y_bool_wy.sum() > 0 else float('nan')
            norm_m = zv[~y_bool_wy].mean() if (~y_bool_wy).sum() > 0 else float('nan')
            sep_ch = cris_m - norm_m
            print(f"  {chname:<12} {cris_m:>10.4f} {norm_m:>10.4f} {sep_ch:>+10.4f}")

        # Supply ensemble: polarity-aligned FWS cross-yr + bilateral within-yr
        # FWS cross-yr is inverted on supply → negate; bilateral within-yr is correct
        for fws_tag in ("FWS cross-yr (unsupervised)",):
            if fws_tag in results:
                s_fws_raw = results[fws_tag]['scores']
                s_bi_raw  = wy_variants[1][1]        # bilateral within-yr
                # Polarity-align: FWS inverted → AUC<0.5 → negate
                fws_auc = results[fws_tag]['auc']
                s_fws_aligned = -s_fws_raw if fws_auc < 0.5 else s_fws_raw
                s_ens = 0.5 * _robust_norm(s_fws_aligned) + \
                        0.5 * _robust_norm(s_bi_raw)
                _print_scorer(
                    "Ensemble FWS×BSDTwy",
                    s_ens, y, dates, event_onsets,
                    data['full_scan'], elapsed_wy, results)

    except Exception as e:
        print(f"  [GeometricBSDT within-yr FAILED: {e}]")
        import traceback; traceback.print_exc()

    # ── §XVII + §XXVI.3  Two-Layer Early Warning System (EWS) ─────────────
    # Ports the crypto trading pipeline two-layer EWS to ERCOT.
    # Calibrated on the same within-year normal reference as BSDT-wy.
    # Layer A (precursor): p1=Lyapunov, p2=misalignment, p3=dispersion, p4=velocity
    # Layer B (geometry):  ξ1=γ*, ξ2=spectral, ξ3=network, ξ4=alignment,
    #                      ξ5=MFLS saturation, ξ6=cos²ψ
    try:
        from geo_full_pipeline import EWS_ERCOT, _HAS_EWS
        if not _HAS_EWS:
            raise ImportError("collapse_geometry package unavailable")

        normal_mask_ews = (y == 0)
        X_ref_ews = X_test[normal_mask_ews]
        if len(X_ref_ews) < 50:
            raise ValueError(f"Too few normal hours to calibrate EWS: {len(X_ref_ews)}")

        t0_ews = time.perf_counter()
        ews = EWS_ERCOT(history_len=5).fit(X_ref_ews)
        ews_out = ews.score_series(X_test)
        elapsed_ews = (time.perf_counter() - t0_ews) * 1000

        print(f"\n  {'─'*W}")
        print(f"  TWO-LAYER EWS §XVII+§XXVI.3 — {mode.upper()}  "
              f"(ref={normal_mask_ews.sum()} normal hrs  "
              f"geom_thr={ews_out['geom_threshold']:.4f}  "
              f"e*={ews_out['e_star']:.4f}  t={elapsed_ews:.0f}ms)")
        print(f"  {'─'*W}")
        print(f"  Layer A precursor: p1=Lyapunov  p2=1-cos(ψ)  "
              f"p3=std(S)  p4=Σ|ΔS|   alarm≥P95 normal")
        print(f"  Layer B geometry:  ξ1=γ*  ξ2=spectral  ξ3=net  "
              f"ξ4=align  ξ5=MFLS/(1+MFLS)  ξ6=cos²ψ")

        for tag, s_ews in [
            ("EWS Layer A (precursor)",  ews_out['precursor']),
            ("EWS Layer B (geometry)",   ews_out['geometry']),
            ("EWS combined (A|B)",       ews_out['combined']),
        ]:
            _print_scorer(tag, s_ews, y, dates, event_onsets,
                          data['full_scan'], elapsed_ews, results)

        # Precursor signal breakdown on crisis vs normal hours
        prec = ews_out['precursor']
        geom = ews_out['geometry']
        y_bool = y.astype(bool)
        print(f"\n  EWS signal means (crisis / normal):")
        for lbl, arr in [("precursor_score", prec), ("geometry_score", geom)]:
            cm = arr[y_bool].mean()  if y_bool.sum()  > 0 else float('nan')
            nm = arr[~y_bool].mean() if (~y_bool).sum() > 0 else float('nan')
            print(f"    {lbl:<22}  crisis={cm:.4f}  normal={nm:.4f}  "
                  f"sep={cm-nm:+.4f}")

    except Exception as e:
        print(f"  [Two-layer EWS FAILED: {e}]")
        import traceback; traceback.print_exc()

    return results


# ══════════════════════════════════════════════════════════════════════════
#  COUPLED N=2 PIPELINE (supply + demand as interacting agents)
# ══════════════════════════════════════════════════════════════════════════

def run_coupled_pipeline(data: dict):
    """Run §XVII+§XXVI.3 CoupledGridEWS: supply+demand as N=2 agents.

    With N=2 all 6 Layer B signals are meaningful — the supply-demand
    coupling distance drives ξ₂ (spectral), ξ₃ (network synchrony),
    and ξ₄ (force-energy alignment).  Layer A precursor signals fire
    when either agent drifts from its calibrated channel-state.

    The full_scan path tests on 2019-2022 covering all 4 crisis events:
      WinterStormUri   (2021-02-10) — supply collapse + demand surge
      COVID_Collapse   (2020-03-23) — demand collapse
      SummerPeak2019   (2019-08-12) — demand surge
      WinterStormElliott (2022-12-22) — supply stress
    """
    if not _HAS_GEO:
        print("  [CoupledGridEWS not available — geo_full_pipeline missing]")
        return {}

    try:
        from geo_full_pipeline import CoupledGridEWS, _HAS_EWS
        if not _HAS_EWS:
            raise ImportError("collapse_geometry package unavailable")
    except ImportError as e:
        print(f"  [CoupledGridEWS import failed: {e}]")
        return {}

    y = data['y']
    dates = data['dates']
    event_onsets = data['event_onsets']
    full_scan = data['full_scan']

    d_sup = data['X_sup_ref'].shape[1]
    d_dem = data['X_dem_ref'].shape[1]
    d_a   = min(d_sup, d_dem)   # per-agent dimensionality

    print(f"\n  {'─'*W}")
    print(f"  COUPLED N=2 EWS §XVII+§XXVI.3  "
          f"(supply d={d_sup} + demand d={d_dem} → d_agent={d_a})")
    print(f"  {'─'*W}")
    print(f"  Reference: {data['n_ref']} normal hrs (2019)  "
          f"Test: {data['n_test']} hrs  "
          f"Crisis fraction: {y.mean()*100:.2f}%")
    sn_tag = "  seasonal_norm=ON (month-matched z-score)" if data.get('seasonal_norm') else ""
    print(f"  Active Layer B signals (ξ₃=W_bar_off zeroed: anti-correlated in power domain; "
          f"ξ₄=align zeroed: degenerate):{sn_tag}")
    print(f"  ξ₁=γ* [w=0.25]  ξ₂=spectral [w=0.25]  ξ₅=MFLS [w=0.25]  ξ₆=cos²ψ [w=0.25]")
    if full_scan:
        print(f"  Full 2019-2022 scan → 3 grid-intrinsic crises: "
              f"Uri · SummerPeak · Elliott  (COVID_Collapse excluded: exogenous)")
    print()

    results = {}

    t0 = time.perf_counter()
    try:
        ews = CoupledGridEWS(d_agent=d_a, history_len=5)
        ews.fit(data['X_sup_ref'], data['X_dem_ref'])
        ews_out = ews.score_series(data['X_sup_test'], data['X_dem_test'])
        elapsed = (time.perf_counter() - t0) * 1000

        print(f"  Calibrated: geom_thr={ews_out['geom_threshold']:.4f}  "
              f"e*={ews_out['e_star']:.4f}  t={elapsed:.0f}ms")

        y_bool = y.astype(bool)
        for tag, s_ews in [
            ("Coupled EWS Layer A (precursor)", ews_out['precursor']),
            ("Coupled EWS Layer B (geometry)",  ews_out['geometry']),
            ("Coupled EWS combined (A|B)",      ews_out['combined']),
        ]:
            _print_scorer(tag, s_ews, y, dates, event_onsets,
                          full_scan, elapsed, results)

        print(f"\n  Coupled EWS signal means (crisis / normal):")
        for lbl, arr in [("precursor_score", ews_out['precursor']),
                         ("geometry_score",  ews_out['geometry'])]:
            cm = arr[y_bool].mean()  if y_bool.sum()  > 0 else float('nan')
            nm = arr[~y_bool].mean() if (~y_bool).sum() > 0 else float('nan')
            print(f"    {lbl:<24}  crisis={cm:.4f}  normal={nm:.4f}  sep={cm-nm:+.4f}")

    except Exception as e:
        print(f"  [CoupledGridEWS FAILED: {e}]")
        import traceback; traceback.print_exc()

    return results


def run_coupled_rolling(data: dict, window_days: int = 30,
                         refit_days: int = 7) -> dict:
    """Rolling-window Coupled EWS: re-calibrates from recent data.

    Instead of a fixed 2019 annual reference, the reference window rolls
    forward in time: at each refit point t, the preceding ``window_days``
    of supply+demand data (crisis-free by recency assumption for 30 days)
    is used to calibrate CoupledGridEWS.  This removes year-to-year drift
    and allows detection of crises relative to the RECENT normal state.

    Parameters
    ----------
    window_days : size of the rolling reference window (default 30 days)
    refit_days  : how often to re-calibrate (default 7 days)
    """
    if not _HAS_GEO:
        print("  [CoupledGridEWS not available — geo_full_pipeline missing]")
        return {}

    try:
        from geo_full_pipeline import CoupledGridEWS, _HAS_EWS
        if not _HAS_EWS:
            raise ImportError("collapse_geometry package unavailable")
    except ImportError as e:
        print(f"  [CoupledGridEWS import failed: {e}]")
        return {}

    # Use raw (un-normalised) features — the rolling EWS normalises internally
    X_sup = data['X_sup_raw_test']
    X_dem = data['X_dem_raw_test']
    y     = data['y']
    dates = data['dates']
    event_onsets = data['event_onsets']
    full_scan    = data['full_scan']
    T            = len(y)

    W_h   = window_days * 24   # reference window in hours
    R_h   = refit_days  * 24   # refit interval in hours

    d_sup = X_sup.shape[1]
    d_dem = X_dem.shape[1]
    d_a   = min(d_sup, d_dem)

    print(f"\n  {'─'*W}")
    print(f"  COUPLED N=2 EWS — ROLLING WINDOW (window={window_days}d, refit={refit_days}d)")
    print(f"  Supply d={d_sup} + demand d={d_dem} → d_agent={d_a}")
    print(f"  {'─'*W}")
    print(f"  Test: {T} hrs  Crisis fraction: {y.mean()*100:.2f}%")
    print(f"  ξ₁=γ* [0.25]  ξ₂=spectral [0.25]  ξ₅=MFLS [0.25]  ξ₆=cos²ψ [0.25]")
    if full_scan:
        print(f"  Full 2019-2022 scan → 3 grid-intrinsic crises: "
              f"Uri · SummerPeak · Elliott  (COVID_Collapse excluded: exogenous)")
    print()

    t_start = time.perf_counter()
    geom_scores = np.full(T, np.nan)
    prec_scores = np.full(T, np.nan)
    p1_scores   = np.full(T, np.nan)
    p2_scores   = np.full(T, np.nan)
    p3_scores   = np.full(T, np.nan)
    p4_scores   = np.full(T, np.nan)

    ews = CoupledGridEWS(d_agent=d_a, history_len=5)

    # Batch-mode rolling: fit on [t-W_h : t], score [t : t+R_h] in one call.
    # This avoids the overhead of per-hour score_series() invocations.
    score_starts = list(range(W_h, T, R_h))
    for i, t in enumerate(score_starts):
        ref_sup = X_sup[t - W_h : t]
        ref_dem = X_dem[t - W_h : t]
        try:
            ews.fit(ref_sup, ref_dem)
        except Exception:
            continue

        # Score until next refit point (or end of data)
        t_end = min(t + R_h, T)
        try:
            out = ews.score_series(X_sup[t:t_end], X_dem[t:t_end])
            geom_scores[t:t_end] = out['geometry']
            prec_scores[t:t_end] = out['precursor']
            p1_scores[t:t_end]   = out.get('p1', np.zeros(t_end - t))
            p2_scores[t:t_end]   = out.get('p2', np.zeros(t_end - t))
            p3_scores[t:t_end]   = out.get('p3', np.zeros(t_end - t))
            p4_scores[t:t_end]   = out.get('p4', np.zeros(t_end - t))
        except Exception:
            pass

        if (i + 1) % 10 == 0:
            pct = 100.0 * t / T
            print(f"    ...rolling refit {i+1}/{len(score_starts)}  "
                  f"t={t}/{T} ({pct:.0f}%)", end='\r', flush=True)

    print()  # newline after progress

    elapsed = (time.perf_counter() - t_start) * 1000

    # Drop hours before the first valid window
    valid = ~np.isnan(geom_scores)
    if valid.sum() < 10:
        print(f"  [Rolling EWS: too few valid scores ({valid.sum()}), aborting]")
        return {}

    # Fill NaN in early window with median
    med_g = float(np.nanmedian(geom_scores))
    med_p = float(np.nanmedian(prec_scores))
    geom_scores = np.where(valid, geom_scores, med_g)
    prec_scores = np.where(valid, prec_scores, med_p)

    def _rn(s):
        lo, hi = np.percentile(s, [5, 95])
        rng = hi - lo
        return (s - lo) / rng if rng > 1e-9 else np.zeros_like(s)

    combined = 0.9 * _rn(geom_scores) + 0.1 * _rn(prec_scores)

    results = {}
    for tag, s in [
        ("Rolling EWS Layer A (precursor)", prec_scores),
        ("Rolling EWS Layer B (geometry)",  geom_scores),
        ("Rolling EWS combined (A|B)",      combined),
    ]:
        _print_scorer(tag, s, y, dates, event_onsets,
                      full_scan, elapsed, results)

    y_bool = y.astype(bool)
    print(f"\n  Rolling EWS signal means (crisis / normal):")
    for lbl, arr in [("precursor_score", prec_scores),
                     ("geometry_score",  geom_scores)]:
        cm = arr[y_bool].mean()  if y_bool.sum()  > 0 else float('nan')
        nm = arr[~y_bool].mean() if (~y_bool).sum() > 0 else float('nan')
        print(f"    {lbl:<24}  crisis={cm:.4f}  normal={nm:.4f}  sep={cm-nm:+.4f}")

    # Per-signal precursor rule compliance table
    # Use nanmedian to fill p1-p4 in the early invalid window
    for arr in [p1_scores, p2_scores, p3_scores, p4_scores]:
        med = float(np.nanmedian(arr[valid])) if valid.sum() > 0 else 0.0
        arr[~valid] = med
    _precursor_rule_table(p1_scores, p2_scores, p3_scores, p4_scores,
                          y, dates, event_onsets, lead_days=30)

    return results


# ══════════════════════════════════════════════════════════════════════════
#  COMPARISON SUMMARY TABLE
# ══════════════════════════════════════════════════════════════════════════

def print_comparison_table(all_results: dict):
    """Print cross-mode, cross-engine AUC summary table."""
    print("\n" + "=" * W)
    print("  CROSS-MODE COMPARISON SUMMARY")
    print("=" * W)

    modes = list(all_results.keys())
    # Collect all engine/scorer names
    all_scorers = []
    for mode_res in all_results.values():
        for section in ('physics', 'canonical'):
            if section in mode_res:
                for k in mode_res[section]:
                    if k not in all_scorers:
                        all_scorers.append(k)

    # Header
    hdr = f"  {'Scorer':<30}"
    for m in modes:
        hdr += f"  {m.upper()[:8]:>10} AUC"
    print(hdr)
    print("  " + "-" * (30 + len(modes) * 15))

    for sc in all_scorers:
        row = f"  {sc:<30}"
        for mode in modes:
            mode_res = all_results[mode]
            found = False
            for section in ('physics', 'canonical'):
                if section in mode_res and sc in mode_res[section]:
                    eff = mode_res[section][sc].get('eff_auc',
                          mode_res[section][sc].get('auc', float('nan')))
                    row += f"  {eff:>12.4f}"
                    found = True
                    break
            if not found:
                row += f"  {'—':>12}"
        print(row)

    # Best per mode (by effective AUC)
    print(f"\n  Best effAUC per mode:")
    for mode in modes:
        mode_res = all_results[mode]
        best_auc = 0.0
        best_name = "—"
        for section in ('physics', 'canonical'):
            for k, v in mode_res.get(section, {}).items():
                a = v.get('eff_auc', v.get('auc', 0))
                if a > best_auc:
                    best_auc = a
                    best_name = k
        print(f"    {mode.upper():<12} → {best_name:<35} effAUC={best_auc:.4f}")

    # Demand vs Supply comparison
    if 'demand' in all_results and 'supply' in all_results:
        print(f"\n  Demand vs Supply AUC delta (demand − supply):")
        for sc in all_scorers:
            a_d = a_s = None
            for section in ('physics', 'canonical'):
                if 'demand' in all_results and section in all_results['demand'] \
                        and sc in all_results['demand'][section]:
                    a_d = all_results['demand'][section][sc].get('auc')
                if 'supply' in all_results and section in all_results['supply'] \
                        and sc in all_results['supply'][section]:
                    a_s = all_results['supply'][section][sc].get('auc')
            if a_d is not None and a_s is not None:
                delta = a_d - a_s
                arrow = "▲demand" if delta > 0 else "▼supply"
                print(f"    {sc:<30} Δ={delta:+.4f}  [{arrow}]")


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="ERCOT All-Engine Benchmark (demand + supply)")
    parser.add_argument("--mode", choices=["supply", "demand", "combined", "all"],
                        default="all",
                        help="Which data mode(s) to run (default: all)")
    parser.add_argument("--target_far", type=float, default=0.05,
                        help="Target FAR for physics engine calibration (default: 0.05)")
    parser.add_argument("--full_scan", action="store_true",
                        help="Test on full 2019-2022 span (shows all events; slower)")
    parser.add_argument("--no_canonical", action="store_true",
                        help="Skip canonical pipeline (FWS + GeometricBSDT)")
    parser.add_argument("--no_physics", action="store_true",
                        help="Skip physics engines (Molecular/Gravity/Hybrid)")
    parser.add_argument("--coupled", action="store_true",
                        help="Run N=2 coupled supply+demand EWS pipeline")
    parser.add_argument("--coupled_full_scan", action="store_true",
                        help="Run coupled EWS on full 2019-2022 (all 4 crises)")
    parser.add_argument("--coupled_rolling", action="store_true",
                        help="Run rolling-window coupled EWS (adaptive reference)")
    parser.add_argument("--window_days", type=int, default=30,
                        help="Rolling reference window size in days (default 30)")
    parser.add_argument("--refit_days", type=int, default=7,
                        help="Rolling re-calibration interval in days (default 7)")
    args = parser.parse_args()

    t_global = time.perf_counter()

    print("=" * W)
    print("  ERCOT ALL-ENGINE BENCHMARK")
    print(f"  Mode(s): {args.mode}   target_FAR={args.target_far}   "
          f"full_scan={args.full_scan}")
    print(f"  Canonical: {not args.no_canonical}   Physics: {not args.no_physics}   "
          f"Coupled N=2: {args.coupled or args.coupled_full_scan}   "
          f"Rolling: {args.coupled_rolling}")
    print("=" * W)

    # 1. Dataset inventory
    print_dataset_inventory()

    # 2. Determine modes
    if args.mode == "all":
        modes = ["supply", "demand", "combined"]
    else:
        modes = [args.mode]

    all_results = {}

    for mode in modes:
        print("\n" + "█" * W)
        print(f"  MODE: {mode.upper()}")
        print("█" * W)

        t_mode = time.perf_counter()

        data = load_ercot_mode(mode=mode, full_scan=args.full_scan)
        if data is None:
            print(f"  SKIPPED: data load failed")
            continue

        mode_res = {}

        # Physics engines
        if not args.no_physics:
            try:
                phys = run_physics_engines(data, target_far=args.target_far)
                mode_res['physics'] = phys
            except Exception as e:
                print(f"  [Physics engines error: {e}]")
                import traceback; traceback.print_exc()

        # Canonical pipeline
        if not args.no_canonical:
            try:
                canon = run_canonical_pipeline(data)
                mode_res['canonical'] = canon
            except Exception as e:
                print(f"  [Canonical pipeline error: {e}]")
                import traceback; traceback.print_exc()

        elapsed_mode = time.perf_counter() - t_mode
        print(f"\n  Mode '{mode}' completed in {elapsed_mode:.1f}s")
        all_results[mode] = mode_res

    # 3. Coupled N=2 pipeline (supply + demand as interacting agents)
    if args.coupled or args.coupled_full_scan:
        print("\n" + "█" * W)
        print("  MODE: COUPLED N=2 (supply + demand as interacting agents)")
        print("█" * W)
        t_coup = time.perf_counter()
        use_full = args.coupled_full_scan
        coup_data = load_ercot_coupled(full_scan=use_full)
        if coup_data is not None:
            try:
                coup_res = run_coupled_pipeline(coup_data)
                all_results['coupled'] = {'canonical': coup_res}
            except Exception as e:
                print(f"  [Coupled pipeline error: {e}]")
                import traceback; traceback.print_exc()
        elapsed_coup = time.perf_counter() - t_coup
        print(f"\n  Mode 'coupled' completed in {elapsed_coup:.1f}s")

    # 4. Rolling-window coupled EWS
    if args.coupled_rolling:
        print("\n" + "█" * W)
        print("  MODE: COUPLED N=2 — ROLLING WINDOW (adaptive reference)")
        print("█" * W)
        t_roll = time.perf_counter()
        # Always use full 2019-2022 scan for rolling (window covers all years)
        roll_data = load_ercot_coupled(full_scan=True, seasonal_norm=False)
        if roll_data is not None:
            try:
                roll_res = run_coupled_rolling(
                    roll_data,
                    window_days=args.window_days,
                    refit_days=args.refit_days,
                )
                all_results['rolling'] = {'canonical': roll_res}
            except Exception as e:
                print(f"  [Rolling coupled pipeline error: {e}]")
                import traceback; traceback.print_exc()
        elapsed_roll = time.perf_counter() - t_roll
        print(f"\n  Mode 'rolling' completed in {elapsed_roll:.1f}s")

    # 5. Cross-mode summary
    if len(all_results) > 1 or (len(all_results) == 1 and
                                  any(len(v) > 0 for v in all_results.values())):
        print_comparison_table(all_results)

    total = time.perf_counter() - t_global
    print(f"\n{'=' * W}")
    print(f"  COMPLETED in {total:.1f}s")
    print(f"{'=' * W}")


if __name__ == "__main__":
    main()
