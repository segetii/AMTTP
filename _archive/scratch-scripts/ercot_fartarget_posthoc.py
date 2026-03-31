"""
ercot_fartarget_posthoc.py
==========================
Post-hoc analysis on cached scores — adds FARTargetCalibrator (the paper's
calibration method) and focuses on 'fused' scores (paper's primary metric).

Uses saved per-week score caches from ercot_supply_benchmark.py, so NO engine
re-fitting needed.  Applies:
  1. FARTargetCalibrator from the paper's calibration module
  2. Re-evaluates all score variants with the new calibrations
  3. Compares fused scores across datasets side by side

Paper baseline: AUC = 0.9940 (Hybrid, supply d=5, FARTargetCalibrator)
"""
from __future__ import annotations
import sys, os, json, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import roc_auc_score
from sklearn.isotonic import IsotonicRegression

os.environ['CUDA_VISIBLE_DEVICES'] = ''
warnings.filterwarnings("ignore")

ROOT = Path(r"c:\amttp")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "udl"))

from research.udl.udl.calibration import FARTargetCalibrator

H = 168  # hours per week

EVENT_ONSETS = {
    "SummerPeak2019":     pd.Timestamp("2019-08-12"),
    "COVID_Collapse":     pd.Timestamp("2020-03-23"),
    "WinterStormUri":     pd.Timestamp("2021-02-10"),
    "WinterStormElliott": pd.Timestamp("2022-12-22"),
}

DATASETS = {
    "supply":   ROOT / "data" / "ercot" / "ercot_supply_hourly.npz",
    "demand":   ROOT / "data" / "ercot" / "ercot_demand_hourly.npz",
    "combined": ROOT / "data" / "ercot" / "ercot_combined_hourly.npz",
}

CACHES = {
    "supply":   ROOT / "results" / "ercot_supply_posthoc_cache.json",
    "demand":   ROOT / "results" / "ercot_demand_posthoc_cache.json",
    "combined": ROOT / "results" / "ercot_combined_posthoc_cache.json",
}

ENGINES = ["Molecular", "Gravity", "Hybrid"]
VARIANTS = ["fused", "bsdt_e", "fisher", "quadsurf", "expogate"]

# FARTarget configs to sweep: (target_far, target_recall, method)
FARTARGET_CONFIGS = [
    (0.01,  0.95,  'combined',  'FARTarget_1%'),
    (0.02,  0.95,  'combined',  'FARTarget_2%'),
    (0.05,  0.95,  'combined',  'FARTarget_5%'),
    (0.05,  0.80,  'combined',  'FARTarget_5%_R80'),
    (0.10,  0.95,  'combined',  'FARTarget_10%'),
    (0.05,  0.95,  'isotonic',  'FARTarget_5%_iso'),
    (0.05,  0.95,  'quantile',  'FARTarget_5%_q'),
]

# Original calibrations for comparison
ORIGINAL_CALS = [
    'Fixed mu+3sig', 'Fixed P99', 'Fixed med+3MAD',
    'Adaptive z>3', 'Adaptive z>2', 'Adaptive P99',
    'Isotonic', 'Platt', 'Conformal',
]


def load_data_labels(path):
    """Load dataset and return weekly labels / dates."""
    npz = np.load(path, allow_pickle=True)
    X = npz["X"]; dates = pd.to_datetime(npz["dates"])
    y = npz["y"].astype(int); labels = npz["labels"]

    n_weeks = len(X) // H; n_hours = n_weeks * H
    y_t = y[:n_hours]; d_t = dates[:n_hours]; lb_t = labels[:n_hours]
    week_dates = d_t[::H]
    y_week = np.array([y_t[i*H:(i+1)*H].any()
                       for i in range(n_weeks)]).astype(int)
    wk_labels = []
    for i in range(n_weeks):
        chunk = lb_t[i*H:(i+1)*H]
        nn = [l for l in chunk if l != 'Normal' and l != 'normal']
        wk_labels.append(nn[0] if nn else 'Normal')

    calib_mask = week_dates <= pd.Timestamp("2019-06-30")
    n_calib = int(calib_mask.sum())
    return week_dates, y_week, np.array(wk_labels), n_calib, n_weeks


def load_cache(path):
    """Load cached weekly scores: {engine: {variant: [208 floats]}}"""
    with open(path) as f:
        return json.load(f)


# =====================================================================
#  Original calibrations (from supply benchmark)
# =====================================================================

def _platt_sigmoid_fit(scores, labels):
    from scipy.optimize import minimize
    s = scores.astype(float); y = labels.astype(float)
    n_pos = y.sum(); n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    t_pos = (n_pos + 1) / (n_pos + 2)
    t_neg = 1 / (n_neg + 2)
    t = np.where(y == 1, t_pos, t_neg)
    def loss(params):
        A, B = params
        p = 1.0 / (1.0 + np.exp(np.clip(A * s + B, -30, 30)))
        p = np.clip(p, 1e-10, 1 - 1e-10)
        return -np.sum(t * np.log(p) + (1 - t) * np.log(1 - p))
    res = minimize(loss, x0=[0.0, 0.0], method='Nelder-Mead')
    return res.x

def _platt_sigmoid_predict(scores, params):
    if params is None:
        return np.full(len(scores), 0.5)
    A, B = params
    return 1.0 / (1.0 + np.exp(np.clip(A * scores + B, -30, 30)))

def _conformal_pvalue(score, cal_scores):
    return (np.sum(cal_scores >= score) + 1) / (len(cal_scores) + 1)


def apply_original_calibrations(weekly_scores, y_week, n_calib, n_weeks):
    """Apply the 9 original calibration methods (fixed/adaptive/isotonic/platt/conformal)."""
    cs = weekly_scores[:n_calib]
    cs_clean = cs[~np.isnan(cs)]
    mu_c = np.nanmean(cs_clean); sig_c = np.nanstd(cs_clean)
    med_c = np.nanmedian(cs_clean)
    mad_c = np.nanmedian(np.abs(cs_clean - med_c))
    p99_c = np.nanpercentile(cs_clean, 99) if len(cs_clean) > 0 else mu_c

    results = {}
    results['Fixed mu+3sig'] = weekly_scores > (mu_c + 3 * sig_c)
    results['Fixed P99'] = weekly_scores > p99_c
    results['Fixed med+3MAD'] = weekly_scores > (med_c + 3 * (mad_c + 1e-10))

    z_scores = np.full(n_weeks, np.nan)
    for t in range(n_calib, n_weeks):
        past = weekly_scores[:t]; past_v = past[~np.isnan(past)]
        if len(past_v) >= 3:
            m = past_v.mean(); s = past_v.std()
            if s > 1e-10:
                z_scores[t] = (weekly_scores[t] - m) / s

    alarm_z3 = np.zeros(n_weeks, dtype=bool)
    alarm_z2 = np.zeros(n_weeks, dtype=bool)
    for t in range(n_calib, n_weeks):
        if not np.isnan(z_scores[t]):
            alarm_z3[t] = z_scores[t] > 3.0
            alarm_z2[t] = z_scores[t] > 2.0
    results['Adaptive z>3'] = alarm_z3
    results['Adaptive z>2'] = alarm_z2

    alarm_p99 = np.zeros(n_weeks, dtype=bool)
    for t in range(n_calib, n_weeks):
        past = weekly_scores[:t]; past_v = past[~np.isnan(past)]
        if len(past_v) >= 3:
            alarm_p99[t] = weekly_scores[t] > np.percentile(past_v, 99)
    results['Adaptive P99'] = alarm_p99

    alarm_iso = np.zeros(n_weeks, dtype=bool)
    for t in range(n_calib, n_weeks):
        past_s = weekly_scores[:t]; past_y = y_week[:t]; valid = ~np.isnan(past_s)
        if valid.sum() >= 4 and past_y[valid].sum() > 0 and past_y[valid].sum() < valid.sum():
            iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds='clip')
            iso.fit(past_s[valid], past_y[valid].astype(float))
            alarm_iso[t] = iso.predict([weekly_scores[t]])[0] > 0.5
        else:
            if not np.isnan(z_scores[t]):
                alarm_iso[t] = z_scores[t] > 2.0
    results['Isotonic'] = alarm_iso

    alarm_platt = np.zeros(n_weeks, dtype=bool)
    for t in range(n_calib, n_weeks):
        past_s = weekly_scores[:t]; past_y = y_week[:t]; valid = ~np.isnan(past_s)
        if valid.sum() >= 4 and past_y[valid].sum() > 0 and past_y[valid].sum() < valid.sum():
            params = _platt_sigmoid_fit(past_s[valid], past_y[valid])
            alarm_platt[t] = _platt_sigmoid_predict(
                np.array([weekly_scores[t]]), params)[0] > 0.5
        else:
            if not np.isnan(z_scores[t]):
                alarm_platt[t] = z_scores[t] > 2.0
    results['Platt'] = alarm_platt

    alarm_conf = np.zeros(n_weeks, dtype=bool)
    n_split = max(1, int(0.75 * n_calib))
    conf_ref = cs_clean[n_split:]
    if len(conf_ref) >= 2:
        for t in range(n_calib, n_weeks):
            if not np.isnan(weekly_scores[t]):
                alarm_conf[t] = _conformal_pvalue(weekly_scores[t], conf_ref) <= 0.05
    results['Conformal'] = alarm_conf

    return results


# =====================================================================
#  FARTargetCalibrator — expanding window (prospective)
# =====================================================================

def apply_fartarget_calibrations(weekly_scores, y_week, n_calib, n_weeks):
    """
    Apply FARTargetCalibrator in expanding-window prospective mode:
    At each week t, fit on all data up to t-1, then classify week t.
    
    Returns dict of {config_name: alarm_mask}
    """
    results = {}
    
    for target_far, target_recall, method, name in FARTARGET_CONFIGS:
        alarm = np.zeros(n_weeks, dtype=bool)
        
        for t in range(n_calib, n_weeks):
            past_s = weekly_scores[:t]
            past_y = y_week[:t]
            valid = ~np.isnan(past_s)
            
            if valid.sum() < 10 or past_y[valid].sum() < 1:
                # Not enough data — skip
                continue
            
            if np.isnan(weekly_scores[t]):
                continue
            
            try:
                cal = FARTargetCalibrator(
                    target_far=target_far,
                    target_recall=target_recall,
                    method=method,
                )
                cal.fit(past_s[valid], past_y[valid])
                calibrated = cal.transform(np.array([weekly_scores[t]]))
                alarm[t] = calibrated[0] > 0.5
            except Exception:
                # Fallback to z-score
                past_v = past_s[valid]
                m, s = past_v.mean(), past_v.std()
                if s > 1e-10:
                    z = (weekly_scores[t] - m) / s
                    alarm[t] = z > 2.0
        
        results[name] = alarm
    
    return results


# =====================================================================
#  Evaluate
# =====================================================================

def evaluate(weekly_scores, alarm_mask, y_week, week_dates, n_calib):
    n = len(y_week)
    crisis = y_week.astype(bool)
    monitor = np.arange(n) >= n_calib
    valid = ~np.isnan(weekly_scores)

    m_valid = monitor & valid
    if m_valid.sum() >= 2 and len(np.unique(y_week[m_valid])) >= 2:
        auc = float(roc_auc_score(y_week[m_valid], weekly_scores[m_valid]))
    else:
        auc = None

    tp = int((alarm_mask & crisis & monitor).sum())
    fp = int((alarm_mask & ~crisis & monitor).sum())
    n_norm = int((~crisis & monitor).sum())
    n_cr_mon = int((crisis & monitor).sum())

    recall = 100 * tp / max(n_cr_mon, 1)
    far = 100 * fp / max(n_norm, 1)

    events_detected = {}
    total_lead = 0
    for ev_name, onset in EVENT_ONSETS.items():
        ev_mask = (week_dates >= onset) & crisis & monitor
        if not ev_mask.any():
            continue
        first_crisis_idx = np.where(ev_mask)[0][0]
        det_before = alarm_mask[:first_crisis_idx] & monitor[:first_crisis_idx]
        if det_before.any():
            first_alarm = np.where(det_before)[0][-1]
            lead = first_crisis_idx - first_alarm
        else:
            det_during = alarm_mask & ev_mask
            lead = 0 if det_during.any() else -1
        if lead >= 0:
            events_detected[ev_name] = int(lead)
            total_lead += lead

    return {
        'auc': auc,
        'far': round(far, 1),
        'recall': round(recall, 1),
        'events_detected': events_detected,
        'n_ev': len(events_detected),
        'lead': total_lead,
    }


# =====================================================================
#  Main
# =====================================================================

def main():
    print("=" * 90)
    print("  FARTargetCalibrator Post-hoc Analysis on Cached Scores")
    print("  Paper uses: Hybrid engine + fused score + FARTargetCalibrator")
    print("=" * 90)

    all_results = {}

    for ds_name, ds_path in DATASETS.items():
        cache_path = CACHES[ds_name]
        if not cache_path.exists():
            print(f"\n  SKIP {ds_name} — cache not found")
            continue

        print(f"\n{'#' * 90}")
        print(f"  DATASET: {ds_name.upper()}")
        print(f"{'#' * 90}")

        # Load labels
        week_dates, y_week, wk_labels, n_calib, n_weeks = load_data_labels(ds_path)
        print(f"  Weeks: {n_weeks}  Calib: {n_calib}  "
              f"Monitor: {n_weeks - n_calib}  Events: {int(y_week[n_calib:].sum())} event-weeks")

        # Load cached scores
        cache = load_cache(cache_path)

        ds_results = {}

        for eng_name in ENGINES:
            if eng_name not in cache:
                print(f"  SKIP engine {eng_name} — not in cache")
                continue

            eng_scores = cache[eng_name]

            for var_name in VARIANTS:
                if var_name not in eng_scores:
                    continue

                ws = np.array(eng_scores[var_name], dtype=float)

                # Apply all calibrations: original + FARTarget
                orig_cals = apply_original_calibrations(ws, y_week, n_calib, n_weeks)
                far_cals = apply_fartarget_calibrations(ws, y_week, n_calib, n_weeks)

                all_cals = {**orig_cals, **far_cals}

                for cal_name, alarm_mask in all_cals.items():
                    r = evaluate(ws, alarm_mask, y_week, week_dates, n_calib)
                    key = f"{eng_name}/{var_name}"
                    if key not in ds_results:
                        ds_results[key] = {}
                    ds_results[key][cal_name] = r

        all_results[ds_name] = ds_results

        # === Print AUC table (all variants, FARTarget calibrations) ===
        print(f"\n{'=' * 90}")
        print(f"  TABLE A: AUC — {ds_name.upper()} (score-level, independent of calibration)")
        print(f"{'=' * 90}")
        print(f"  {'Engine':<12} {'Variant':<12} {'AUC':>8}")
        print(f"  {'-'*35}")
        for eng in ENGINES:
            for var in VARIANTS:
                key = f"{eng}/{var}"
                if key in ds_results and ds_results[key]:
                    first_cal = next(iter(ds_results[key].values()))
                    a = first_cal.get('auc')
                    auc_s = f"{a:.4f}" if a else "  N/A"
                    print(f"  {eng:<12} {var:<12} {auc_s:>8}")
            print()

        # === Print FARTarget results (focus on fused) ===
        print(f"\n{'=' * 90}")
        print(f"  TABLE B: FARTarget CALIBRATION RESULTS — {ds_name.upper()}")
        print(f"  (Showing all engines × fused + best other variants)")
        print(f"{'=' * 90}")
        print(f"  {'Engine/Variant':<25} {'Calibration':<22} "
              f"{'Ev':>3} {'Lead':>5} {'FAR%':>6} {'AUC':>7}  Events")
        print(f"  {'-' * 95}")

        rows = []
        for key, cals in ds_results.items():
            for cal_name, r in cals.items():
                if r['n_ev'] > 0:
                    evs = " ".join(f"{e}={l}w" for e, l in r['events_detected'].items())
                    auc_s = f"{r['auc']:.4f}" if r['auc'] else "  N/A"
                    rows.append({
                        'key': key, 'cal': cal_name,
                        'n_ev': r['n_ev'], 'lead': r['lead'],
                        'far': r['far'], 'auc': r['auc'] or 0,
                        'evs': evs, 'auc_s': auc_s,
                        'is_fartarget': cal_name.startswith('FARTarget'),
                    })

        # Sort: most events, lowest FAR, most lead
        rows.sort(key=lambda x: (-x['n_ev'], x['far'], -x['lead']))

        # Print FARTarget rows first
        far_rows = [r for r in rows if r['is_fartarget']]
        orig_rows = [r for r in rows if not r['is_fartarget']]

        print(f"\n  --- FARTarget calibrations ---")
        for i, c in enumerate(far_rows[:25], 1):
            print(f"  {i:<3} {c['key']:<25} {c['cal']:<22} "
                  f"{c['n_ev']:>3} {c['lead']:>4}w {c['far']:>5.1f}% {c['auc_s']:>7}  {c['evs']}")

        print(f"\n  --- Best original calibrations (top 10) ---")
        for i, c in enumerate(orig_rows[:10], 1):
            print(f"  {i:<3} {c['key']:<25} {c['cal']:<22} "
                  f"{c['n_ev']:>3} {c['lead']:>4}w {c['far']:>5.1f}% {c['auc_s']:>7}  {c['evs']}")

    # =====================================================================
    #  FINAL: Cross-dataset FUSED-score comparison
    # =====================================================================
    print(f"\n\n{'#' * 90}")
    print(f"  FINAL: FUSED-score comparison across datasets")
    print(f"  (Paper's primary: Hybrid/fused + FARTargetCalibrator)")
    print(f"{'#' * 90}")

    print(f"\n  {'Dataset':<12} {'Engine':<12} {'AUC':>8}  "
          f"{'Best FARTarget':<22} {'Ev':>3} {'FAR%':>6} {'Lead':>5}")
    print(f"  {'-' * 75}")

    comparison = {}
    for ds_name in ['supply', 'demand', 'combined']:
        if ds_name not in all_results:
            continue
        ds = all_results[ds_name]
        for eng in ENGINES:
            key = f"{eng}/fused"
            if key not in ds:
                continue
            cals = ds[key]
            # AUC from any calibration (it's score-level)
            auc = next(iter(cals.values())).get('auc')
            auc_s = f"{auc:.4f}" if auc else "  N/A"

            # Best FARTarget calibration: most events, lowest FAR
            best_far = None
            for cal_name, r in cals.items():
                if not cal_name.startswith('FARTarget'):
                    continue
                if best_far is None or (
                    r['n_ev'] > best_far['n_ev'] or
                    (r['n_ev'] == best_far['n_ev'] and r['far'] < best_far['far'])
                ):
                    best_far = {**r, 'cal': cal_name}

            if best_far:
                bf_s = (f"{best_far['cal']:<22} {best_far['n_ev']:>3} "
                        f"{best_far['far']:>5.1f}% {best_far['lead']:>4}w")
            else:
                bf_s = "N/A"

            print(f"  {ds_name:<12} {eng:<12} {auc_s:>8}  {bf_s}")

            comp_key = f"{ds_name}/{eng}"
            comparison[comp_key] = {
                'auc': auc,
                'best_fartarget': best_far,
            }

        print()

    # Also show best non-fused variant per dataset for comparison
    print(f"\n  {'Dataset':<12} {'Best Config':<25} {'AUC':>8}  "
          f"{'Best Calib':<22} {'Ev':>3} {'FAR%':>6} {'Lead':>5}")
    print(f"  {'-' * 80}")

    for ds_name in ['supply', 'demand', 'combined']:
        if ds_name not in all_results:
            continue
        ds = all_results[ds_name]
        best_auc = 0; best_key = None
        for key, cals in ds.items():
            auc = next(iter(cals.values())).get('auc')
            if auc and auc > best_auc:
                best_auc = auc; best_key = key

        if best_key:
            a_s = f"{best_auc:.4f}"
            best_cal = None
            for cal_name, r in ds[best_key].items():
                if best_cal is None or (
                    r['n_ev'] > best_cal['n_ev'] or
                    (r['n_ev'] == best_cal['n_ev'] and r['far'] < best_cal['far'])
                ):
                    best_cal = {**r, 'cal': cal_name}
            if best_cal:
                bc_s = (f"{best_cal['cal']:<22} {best_cal['n_ev']:>3} "
                        f"{best_cal['far']:>5.1f}% {best_cal['lead']:>4}w")
            else:
                bc_s = ""
            print(f"  {ds_name:<12} {best_key:<25} {a_s:>8}  {bc_s}")

    print(f"\n  Paper baseline: AUC = 0.9940 (Hybrid, supply d=5, FARTargetCalibrator)")
    print(f"  Protocol diff: paper = single-fit 1yr; ours = expanding-window 4yr prospective")

    # Save
    out_path = ROOT / "results" / "ercot_fartarget_results.json"
    with open(out_path, 'w') as f:
        json.dump({
            'comparison': {k: {
                'auc': v['auc'],
                'best_fartarget_cal': v['best_fartarget']['cal'] if v['best_fartarget'] else None,
                'best_fartarget_far': v['best_fartarget']['far'] if v['best_fartarget'] else None,
                'best_fartarget_events': v['best_fartarget']['n_ev'] if v['best_fartarget'] else 0,
            } for k, v in comparison.items()},
            'all_results': {
                ds: {key: {cal: r for cal, r in cals.items()}
                     for key, cals in ds_data.items()}
                for ds, ds_data in all_results.items()
            }
        }, f, indent=2, default=str)
    print(f"\n  Saved -> {out_path}")


if __name__ == '__main__':
    main()
