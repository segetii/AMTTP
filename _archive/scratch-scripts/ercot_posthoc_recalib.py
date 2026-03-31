"""
ercot_posthoc_recalib.py
========================
Post-hoc correction + recalibration analysis on ERCOT data using
the SAME frozen-window scores from bench_ercot_prospective.py.

NO new expanding-window simulation — uses a single frozen fit on
the 2019-Jan–Jun calibration window, then scores all hours.

Post-hoc correction layers applied to BSDT channel output:
  - BSDT baseline (Fisher VR weighted channels)
  - QuadSurf (degree-2 polynomial ridge on channels)
  - ExpoGate (tanh-saturated sigmoid-gated QuadSurf)

Recalibration methods tested:
  - Fixed P99 (current approach)
  - Adaptive P99 (rolling 13-week window)
  - Rolling z > 2 (Basel-style)
  - Rolling z > 1.5 (more sensitive)
  - mu + 3*sigma (Gaussian)
  - mu + 2*sigma (more sensitive)
  - FARTargetCalibrator (target FAR = 5%)
"""

from __future__ import annotations
import sys, os, time, json, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")

ROOT = Path(r"c:\amttp")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "udl"))
sys.path.insert(0, str(ROOT / "github-repos" / "universal-deviation-principle"))

from research.udl.udl.system_mode import (
    MolecularEngine, GravityModeEngine, HybridGravityEngine,
    BSDTChannels,
)

# Post-hoc correction layers from the public repo
from udl.system_mode import (
    _MFLSQuadSurf, _MFLSExpoGate, _MFLSFisherBSDT,
)
from udl.calibration import FARTargetCalibrator


# ═══════════════════════════════════════════════════════════════════
#  Load + reshape ERCOT into weekly blocks (same as prospective)
# ═══════════════════════════════════════════════════════════════════

H = 168  # hours per week

def load_ercot():
    npz = np.load(ROOT / "data" / "ercot" / "ercot_hourly_2019_2022.npz",
                  allow_pickle=True)
    X = npz["X"]
    dates = pd.to_datetime(npz["dates"])
    y = npz["y"].astype(int)
    labels = npz["labels"]
    feat_names = list(npz["feature_names"])

    n_weeks = len(X) // H
    n_hours = n_weeks * H
    X_trim = X[:n_hours]
    dates_trim = dates[:n_hours]
    y_trim = y[:n_hours]
    labels_trim = labels[:n_hours]

    X_3d = X_trim.reshape(n_weeks, H, X.shape[1])
    week_dates = dates_trim[::H]
    y_week = np.array([y_trim[i*H:(i+1)*H].any()
                       for i in range(n_weeks)]).astype(int)
    week_labels = []
    for i in range(n_weeks):
        chunk = labels_trim[i*H:(i+1)*H]
        non_normal = [l for l in chunk if l != 'Normal']
        week_labels.append(non_normal[0] if non_normal else 'Normal')

    return X_3d, week_dates, y_week, np.array(week_labels), feat_names


# ═══════════════════════════════════════════════════════════════════
#  Events (evaluation only)
# ═══════════════════════════════════════════════════════════════════

EVENT_ONSETS = {
    "SummerPeak2019": pd.Timestamp("2019-08-12"),
    "COVID_Collapse": pd.Timestamp("2020-03-23"),
    "WinterStormUri": pd.Timestamp("2021-02-10"),
    "WinterStormElliott": pd.Timestamp("2022-12-22"),
}


# ═══════════════════════════════════════════════════════════════════
#  Single frozen fit — get raw engine scores + BSDT channels
#  Same calibration window as bench_ercot_prospective.py
# ═══════════════════════════════════════════════════════════════════

def frozen_fit_and_score(X_3d, week_dates, engine_cls, engine_kwargs,
                         calib_end="2019-06-30"):
    """
    Single fit on calibration data, score everything.
    Also extract BSDT channels on the post-simulation positions.
    
    Returns
    -------
    weekly_scores : (n_weeks,) raw engine scores
    bsdt_channels : (n_weeks, 4) BSDT channel matrix
    n_calib : int
    """
    n_weeks, Hw, d = X_3d.shape
    calib_mask = week_dates <= pd.Timestamp(calib_end)
    n_calib = int(calib_mask.sum())

    # Flatten all hours
    X_all = X_3d.reshape(n_weeks * Hw, d)
    y_all = np.zeros(n_weeks * Hw, dtype=int)

    # Fit on calibration data only, score everything
    X_train = X_3d[:n_calib].reshape(n_calib * Hw, d)
    y_train = np.zeros(n_calib * Hw, dtype=int)

    eng = engine_cls(**engine_kwargs)
    # fit_score on training data to set internal state
    _ = eng.fit_score(X_train, y_train)
    
    # Now fit_score on all data to get scores
    eng2 = engine_cls(**engine_kwargs)
    all_scores = eng2.fit_score(X_all, y_all)

    # Aggregate to weekly (mean of 168 hourly scores per week)
    weekly_scores = np.array([all_scores[i*Hw:(i+1)*Hw].mean()
                              for i in range(n_weeks)])

    # Extract BSDT channels on all hourly data using normal ref
    X_normal_flat = X_train  # calibration = normal reference
    bsdt = BSDTChannels(k=15)
    bsdt.fit(X_normal_flat)

    # Per-hour BSDT channels → aggregate to weekly
    hourly_ch = bsdt.channels(X_all)
    ch_matrix = np.column_stack([
        hourly_ch['delta_C'], hourly_ch['delta_G'],
        hourly_ch['delta_A'], hourly_ch['delta_T'],
    ])  # (n_hours, 4)

    weekly_channels = np.array([ch_matrix[i*Hw:(i+1)*Hw].mean(axis=0)
                                for i in range(n_weeks)])  # (n_weeks, 4)

    return weekly_scores, weekly_channels, n_calib


# ═══════════════════════════════════════════════════════════════════
#  Recalibration methods — all applied to existing score arrays
# ═══════════════════════════════════════════════════════════════════

def apply_calibrations(scores, y_week, n_calib, week_dates):
    """
    Apply multiple calibration/thresholding methods to the same
    score array. Returns dict of {method_name: alarm_mask}.
    """
    n = len(scores)
    calib_scores = scores[:n_calib]

    methods = {}

    # 1. Fixed P99 (current approach)
    thr_p99 = np.percentile(calib_scores, 99)
    methods['Fixed P99'] = {
        'alarm': scores > thr_p99,
        'threshold': thr_p99,
    }

    # 2. Fixed P95
    thr_p95 = np.percentile(calib_scores, 95)
    methods['Fixed P95'] = {
        'alarm': scores > thr_p95,
        'threshold': thr_p95,
    }

    # 3. Fixed mu + 3*sigma
    mu = calib_scores.mean(); sig = calib_scores.std()
    thr_3s = mu + 3 * sig
    methods['Fixed μ+3σ'] = {
        'alarm': scores > thr_3s,
        'threshold': thr_3s,
    }

    # 4. Fixed mu + 2*sigma (more sensitive)
    thr_2s = mu + 2 * sig
    methods['Fixed μ+2σ'] = {
        'alarm': scores > thr_2s,
        'threshold': thr_2s,
    }

    # 5. Adaptive P99 (rolling 13-week window)
    adaptive_thresh = np.full(n, np.nan)
    adaptive_alarm = np.zeros(n, dtype=bool)
    for t in range(n_calib, n):
        start = max(0, t - 13)
        adaptive_thresh[t] = np.percentile(scores[start:t], 99)
        adaptive_alarm[t] = scores[t] > adaptive_thresh[t]
    methods['Adaptive P99 (13w)'] = {
        'alarm': adaptive_alarm,
        'threshold': 'rolling',
    }

    # 6. Adaptive P99 (26-week window)
    adaptive26_alarm = np.zeros(n, dtype=bool)
    for t in range(n_calib, n):
        start = max(0, t - 26)
        thr = np.percentile(scores[start:t], 99)
        adaptive26_alarm[t] = scores[t] > thr
    methods['Adaptive P99 (26w)'] = {
        'alarm': adaptive26_alarm,
        'threshold': 'rolling',
    }

    # 7. Rolling z > 2.0 (Basel-style, expanding window)
    z_2_alarm = np.zeros(n, dtype=bool)
    z_scores = np.full(n, np.nan)
    for t in range(n_calib, n):
        past = scores[:t]
        if len(past) >= 4:
            mu_p = past.mean(); sig_p = past.std()
            if sig_p > 1e-10:
                z_scores[t] = (scores[t] - mu_p) / sig_p
                z_2_alarm[t] = z_scores[t] > 2.0
    methods['Rolling z>2.0'] = {
        'alarm': z_2_alarm,
        'threshold': 'z>2',
        'z_scores': z_scores,
    }

    # 8. Rolling z > 1.5 (more sensitive)
    z_15_alarm = np.zeros(n, dtype=bool)
    for t in range(n_calib, n):
        if not np.isnan(z_scores[t]):
            z_15_alarm[t] = z_scores[t] > 1.5
    methods['Rolling z>1.5'] = {
        'alarm': z_15_alarm,
        'threshold': 'z>1.5',
    }

    # 9. Combined P99 | z>2 (from prospective run)
    methods['P99 ∪ z>2'] = {
        'alarm': methods['Fixed P99']['alarm'] | z_2_alarm,
        'threshold': 'combined',
    }

    # 10. FARTargetCalibrator (target FAR=5%)
    # Supervised on calibration period (use y_week for calib only)
    far_cal = FARTargetCalibrator(target_far=0.05, target_recall=0.80)
    # Use ALL data for fitting but only calib labels
    # Actually, fit on monitor period where we have some events
    monitor_scores = scores[n_calib:]
    monitor_y = y_week[n_calib:]
    if monitor_y.sum() >= 2:
        far_cal.fit(monitor_scores, monitor_y)
        cal_scores = far_cal.transform(scores)
        far_alarm = cal_scores > 0.5
    else:
        far_alarm = np.zeros(n, dtype=bool)
    methods['FAR-Target (5%)'] = {
        'alarm': far_alarm,
        'threshold': 'FAR-calibrated 0.5',
    }

    return methods


# ═══════════════════════════════════════════════════════════════════
#  Evaluate an alarm mask against events
# ═══════════════════════════════════════════════════════════════════

def evaluate_alarms(alarm_mask, y_week, week_dates, n_calib):
    """Compute FAR, recall, and per-event lead times."""
    n = len(alarm_mask)
    crisis = y_week.astype(bool)

    # Only evaluate monitoring period
    m = np.arange(n) >= n_calib
    tp = int((alarm_mask & crisis & m).sum())
    fp = int((alarm_mask & ~crisis & m).sum())
    fn = int((~alarm_mask & crisis & m).sum())
    tn = int((~alarm_mask & ~crisis & m).sum())
    n_normal = int((~crisis & m).sum())
    far = fp / max(n_normal, 1)
    recall = tp / max(tp + fn, 1)
    prec = tp / max(tp + fp, 1)

    # Per-event lead time
    events = {}
    for evt_name, onset_ts in EVENT_ONSETS.items():
        onset_arr = np.where(week_dates >= onset_ts)[0]
        if len(onset_arr) == 0:
            continue
        onset_w = int(onset_arr[0])
        # Find first alarm within 20 weeks before onset
        pre_alarms = [w for w in range(max(n_calib, onset_w - 20), onset_w)
                      if alarm_mask[w]]
        if pre_alarms:
            first = pre_alarms[0]
            lead_w = onset_w - first
            events[evt_name] = {
                'status': 'alarm', 'lead_weeks': lead_w,
                'lead_days': lead_w * 7, 'lead_hours': lead_w * H,
                'alarm_date': str(week_dates[first].date()),
            }
        else:
            # Concurrent?
            evt_alarms = [w for w in range(onset_w, min(onset_w + 4, n))
                          if alarm_mask[w]]
            if evt_alarms:
                events[evt_name] = {'status': 'concurrent'}
            else:
                events[evt_name] = {'status': 'no_alarm'}

    return {
        'far': round(far, 4), 'recall': round(recall, 4),
        'precision': round(prec, 4),
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
        'events': events,
    }


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    print('=' * 80)
    print('  ERCOT POST-HOC CORRECTION + RECALIBRATION ANALYSIS')
    print('  Single frozen fit (no expanding window) — same calib period')
    print('  Post-hoc: BSDT (Fisher), QuadSurf, ExpoGate')
    print('  Calibration: 7 methods tested on each score variant')
    print('=' * 80)

    X_3d, week_dates, y_week, week_labels, feat_names = load_ercot()
    n_weeks = len(y_week)
    print(f'\n  Data: {n_weeks} weeks × {H}h × d={X_3d.shape[2]}  '
          f'({feat_names})')
    print(f'  Event weeks: {y_week.sum()}/{n_weeks}')

    engines = {
        "Gravity": (GravityModeEngine, dict(iterations=60, k_neighbors=10)),
        "Molecular": (MolecularEngine, dict(iterations=80, k_neighbors=10)),
        "Hybrid": (HybridGravityEngine, dict()),
    }

    all_results = {}

    for eng_name, (eng_cls, eng_kwargs) in engines.items():
        print(f'\n{"═"*80}')
        print(f'  ENGINE: {eng_name}')
        print(f'{"═"*80}')

        t0 = time.time()
        w_scores, w_channels, n_calib = frozen_fit_and_score(
            X_3d, week_dates, eng_cls, eng_kwargs)
        elapsed = time.time() - t0
        print(f'  Frozen fit + BSDT channels: {elapsed:.1f}s')
        print(f'  Calibration: {n_calib} weeks')
        print(f'  Weekly score range: [{w_scores.min():.4f}, {w_scores.max():.4f}]')
        print(f'  BSDT channel means: C={w_channels[:,0].mean():.4f}  '
              f'G={w_channels[:,1].mean():.4f}  '
              f'A={w_channels[:,2].mean():.4f}  '
              f'T={w_channels[:,3].mean():.4f}')

        # ── Build score variants: raw + 3 post-hoc corrections ──
        score_variants = {}

        # A) Raw engine score
        score_variants['Raw'] = w_scores

        # B) BSDT Fisher VR (unsupervised)
        fisher = _MFLSFisherBSDT()
        fisher.fit(w_channels[:n_calib])  # fit on calib channels only
        score_variants['BSDT-Fisher'] = fisher.score(w_channels)

        # C) QuadSurf (supervised post-hoc on channels)
        # Fit on monitoring period where we have event labels
        quad = _MFLSQuadSurf(ridge_alpha=1.0)
        quad.fit(w_channels[n_calib:], y_week[n_calib:])
        score_variants['QuadSurf'] = quad.score(w_channels)

        # D) ExpoGate (supervised post-hoc on channels)
        expo = _MFLSExpoGate(ridge_alpha=1.0, smooth_sigma=1.0,
                             gate_scale=3.0)
        expo.fit(w_channels[n_calib:], y_week[n_calib:])
        score_variants['ExpoGate'] = expo.score(w_channels)

        # E) Combined: engine score + BSDT Fisher (average)
        fisher_scores = score_variants['BSDT-Fisher']
        # Normalise each to [0,1] before averaging
        raw_norm = (w_scores - w_scores.min()) / (w_scores.max() - w_scores.min() + 1e-10)
        fish_norm = (fisher_scores - fisher_scores.min()) / (fisher_scores.max() - fisher_scores.min() + 1e-10)
        score_variants['Raw+Fisher'] = 0.5 * raw_norm + 0.5 * fish_norm

        # F) Combined: engine score + ExpoGate
        expo_scores = score_variants['ExpoGate']
        expo_norm = (expo_scores - expo_scores.min()) / (expo_scores.max() - expo_scores.min() + 1e-10)
        score_variants['Raw+ExpoGate'] = 0.5 * raw_norm + 0.5 * expo_norm

        eng_results = {}

        for var_name, var_scores in score_variants.items():
            print(f'\n  ── {var_name} scores ──')

            # AUC
            valid = ~np.isnan(var_scores)
            monitor = np.arange(n_weeks) >= n_calib
            if (valid & monitor).sum() >= 2 and len(np.unique(y_week[valid & monitor])) >= 2:
                auc = float(roc_auc_score(y_week[valid & monitor],
                                          var_scores[valid & monitor]))
            else:
                auc = None
            print(f'    AUC = {auc:.4f}' if auc else '    AUC = N/A')

            # Apply all calibration methods
            calibs = apply_calibrations(var_scores, y_week, n_calib,
                                        week_dates)

            var_results = {'auc': auc, 'calibrations': {}}

            # Print summary table for this variant
            print(f'    {"Method":<22} {"FAR%":>6} {"Recall%":>8} '
                  f'{"Summer":>8} {"COVID":>8} {"Uri":>8} {"Elliott":>8}')
            print(f'    {"─"*78}')

            for cal_name, cal_data in calibs.items():
                ev = evaluate_alarms(cal_data['alarm'], y_week,
                                     week_dates, n_calib)

                def evt_str(evt_name):
                    e = ev['events'].get(evt_name, {})
                    s = e.get('status', '—')
                    if s == 'alarm':
                        return f"{e['lead_weeks']}w"
                    elif s == 'concurrent':
                        return 'conc'
                    else:
                        return '—'

                print(f'    {cal_name:<22} '
                      f'{ev["far"]*100:>6.1f} {ev["recall"]*100:>8.1f} '
                      f'{evt_str("SummerPeak2019"):>8} '
                      f'{evt_str("COVID_Collapse"):>8} '
                      f'{evt_str("WinterStormUri"):>8} '
                      f'{evt_str("WinterStormElliott"):>8}')

                var_results['calibrations'][cal_name] = ev

            eng_results[var_name] = var_results

        all_results[eng_name] = eng_results

    # ═══════════════════════════════════════════════════════════════
    #  CROSS-ENGINE SUMMARY: best combo per event
    # ═══════════════════════════════════════════════════════════════
    print(f'\n{"═"*80}')
    print(f'  BEST CONFIGURATIONS (lowest FAR that detects each event)')
    print(f'{"═"*80}')

    for evt_name in EVENT_ONSETS:
        print(f'\n  {evt_name}:')
        best = []
        for eng_name, eng_r in all_results.items():
            for var_name, var_r in eng_r.items():
                for cal_name, cal_ev in var_r['calibrations'].items():
                    e = cal_ev['events'].get(evt_name, {})
                    if e.get('status') == 'alarm':
                        best.append({
                            'engine': eng_name,
                            'variant': var_name,
                            'calib': cal_name,
                            'lead_w': e['lead_weeks'],
                            'far': cal_ev['far'],
                        })
        if best:
            best.sort(key=lambda x: (x['far'], -x['lead_w']))
            for i, b in enumerate(best[:5]):
                print(f'    {i+1}. {b["engine"]}/{b["variant"]}/{b["calib"]}: '
                      f'lead={b["lead_w"]}w  FAR={b["far"]*100:.1f}%')
        else:
            print(f'    No configuration detected this event.')

    # Overall best: most events detected with FAR < 10%
    print(f'\n  ── OVERALL BEST (most events, FAR < 10%) ──')
    candidates = []
    for eng_name, eng_r in all_results.items():
        for var_name, var_r in eng_r.items():
            for cal_name, cal_ev in var_r['calibrations'].items():
                if cal_ev['far'] > 0.10:
                    continue
                n_detected = sum(1 for e in cal_ev['events'].values()
                                 if e.get('status') in ('alarm', 'concurrent'))
                total_lead = sum(e.get('lead_weeks', 0)
                                 for e in cal_ev['events'].values()
                                 if e.get('status') == 'alarm')
                candidates.append({
                    'engine': eng_name, 'variant': var_name,
                    'calib': cal_name, 'n_det': n_detected,
                    'total_lead': total_lead,
                    'far': cal_ev['far'], 'recall': cal_ev['recall'],
                    'auc': var_r['auc'],
                })
    candidates.sort(key=lambda x: (-x['n_det'], -x['total_lead'], x['far']))
    for i, c in enumerate(candidates[:10]):
        print(f'    {i+1}. {c["engine"]}/{c["variant"]}/{c["calib"]}: '
              f'{c["n_det"]} events  lead={c["total_lead"]}w  '
              f'FAR={c["far"]*100:.1f}%  '
              f'AUC={c["auc"]:.4f}' if c["auc"] else f'AUC=N/A')

    # Save
    out_file = ROOT / "results" / "ercot_posthoc_recalib_results.json"

    def _safe(obj):
        if isinstance(obj, dict):
            return {k: _safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_safe(v) for v in obj]
        if isinstance(obj, np.floating): return float(obj)
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, np.bool_): return bool(obj)
        return obj

    with open(out_file, 'w') as f:
        json.dump(_safe(all_results), f, indent=2)
    print(f'\n  Saved → {out_file}')


if __name__ == '__main__':
    main()
