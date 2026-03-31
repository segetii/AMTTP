"""
UDL System Mode — ERCOT Prospective Engine Early Warning
=========================================================
Adapts bench_bank_level_prospective.py's exact pipeline for ERCOT
hourly power-grid data.  Same structural protocol:

  Bank pipeline                    ERCOT pipeline
  ─────────────────────────────    ─────────────────────────────
  Unit of time:   quarter (3 mo)   week (168 h)
  Cross-section:  N=25 banks       24 hours-in-day  (not used — 1D)
  Features:       d=5 bank ratios  d=5 grid features
  Re-fit:         every quarter    every week
  Score:          mean of N banks  mean of 168 hourly scores
  Threshold:      P99 of calib Q   P99 of calib weeks
  Label:          y=0 always       y=0 always
  Z-score:        Basel z>2        Same z>2

Protocol  (replicates bench_bank_level_prospective.py)
───────────────────────────────────────────────────────
1. Calibration window: 2019-Jan-01 → 2019-Jun-30  (~26 weeks)
   — Alarm threshold set from this period only
2. Expanding window online scoring:
   For each monitoring week w ≥ 2019-Jul:
     • X = all hourly observations from week 0 … w
     • y = zeros  (pure unsupervised — NO event labels)
     • Score(w) = mean engine score of week w's 168 hours
3. Alarm fires when score > threshold (P99 of calibration weeks)
   OR z-score > 2.0 (Basel-style cyclical gap)
4. Evaluation done AFTER all scoring: AUROC, lead time, FAR

Data source:  EIA hourly demand + Open-Meteo temperature (d=5)
Events:       SummerPeak2019, COVID_Collapse, WinterStormUri,
              WinterStormElliott
"""
from __future__ import annotations
import sys, os, time, json, warnings, gc
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")

ROOT = Path(r"c:\amttp")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "udl"))

from research.udl.udl.system_mode import (
    MolecularEngine, GravityModeEngine, HybridGravityEngine
)


# ═══════════════════════════════════════════════════════════════════
#  Load ERCOT hourly panel
# ═══════════════════════════════════════════════════════════════════

def load_ercot():
    """Load hourly ERCOT data, reshape into weekly blocks."""
    npz = np.load(ROOT / "data" / "ercot" / "ercot_hourly_2019_2022.npz",
                  allow_pickle=True)
    X = npz["X"]              # (35064, 5)
    dates = pd.to_datetime(npz["dates"])
    y = npz["y"].astype(int)  # per-hour anomaly flag
    labels = npz["labels"]    # per-hour event name
    feat_names = list(npz["feature_names"])
    event_onsets = json.loads(str(npz["event_onsets"]))

    # ── Reshape into weekly blocks (168 hours each) ──
    HOURS_PER_WEEK = 168
    n_full_weeks = len(X) // HOURS_PER_WEEK
    n_hours_used = n_full_weeks * HOURS_PER_WEEK

    X_trim = X[:n_hours_used]
    dates_trim = dates[:n_hours_used]
    y_trim = y[:n_hours_used]
    labels_trim = labels[:n_hours_used]

    X_3d = X_trim.reshape(n_full_weeks, HOURS_PER_WEEK, X.shape[1])
    # Weekly date = first hour of each week
    week_dates = dates_trim[::HOURS_PER_WEEK]
    # Weekly anomaly label: 1 if ANY hour in that week is anomalous
    y_week = np.array([y_trim[i*HOURS_PER_WEEK:(i+1)*HOURS_PER_WEEK].any()
                       for i in range(n_full_weeks)]).astype(int)
    # Weekly event label = dominant non-Normal label
    week_labels = []
    for i in range(n_full_weeks):
        chunk = labels_trim[i*HOURS_PER_WEEK:(i+1)*HOURS_PER_WEEK]
        non_normal = [l for l in chunk if l != 'Normal']
        week_labels.append(non_normal[0] if non_normal else 'Normal')
    week_labels = np.array(week_labels)

    return {
        "X_3d": X_3d,           # (n_weeks, 168, d)
        "X_flat": X_trim,       # (n_hours_used, d)
        "dates_hourly": dates_trim,
        "dates_weekly": week_dates,
        "y_hourly": y_trim,
        "y_weekly": y_week,
        "labels_weekly": week_labels,
        "feat_names": feat_names,
        "event_onsets": event_onsets,
        "hours_per_week": HOURS_PER_WEEK,
    }


# ═══════════════════════════════════════════════════════════════════
#  Event definitions (for evaluation ONLY)
# ═══════════════════════════════════════════════════════════════════

EVENT_PERIODS = {
    "SummerPeak2019": (pd.Timestamp("2019-08-12"), pd.Timestamp("2019-08-17")),
    "COVID_Collapse": (pd.Timestamp("2020-03-23"), pd.Timestamp("2021-02-01")),
    "WinterStormUri": (pd.Timestamp("2021-02-10"), pd.Timestamp("2021-02-21")),
    "WinterStormElliott": (pd.Timestamp("2022-12-22"), pd.Timestamp("2022-12-27")),
}


# ═══════════════════════════════════════════════════════════════════
#  Prospective expanding-window scoring
#  (exact mirror of bench_bank_level_prospective.prospective_score)
# ═══════════════════════════════════════════════════════════════════

def prospective_score(X_3d, week_dates, engine_cls, engine_kwargs,
                      calib_end="2019-06-30", verbose=True):
    """
    Strictly prospective scoring — no future data leaks.

    At each monitoring week w:
      1. X = all hours from week 0 to week w  (expanding window)
      2. y = zeros  (unsupervised)
      3. fit_score → extract last 168 scores → mean = weekly score

    Parameters
    ----------
    X_3d : (n_weeks, 168, d) — weekly blocks of hourly data
    week_dates : DatetimeIndex — start date of each week
    calib_end : last date of calibration window
    """
    n_weeks, H, d = X_3d.shape
    calib_end_dt = pd.Timestamp(calib_end)
    calib_mask = week_dates <= calib_end_dt
    n_calib = int(calib_mask.sum())

    if verbose:
        print(f"    Calibration: {week_dates[0].date()} → "
              f"{week_dates[n_calib-1].date()} "
              f"({n_calib} weeks, {n_calib*H:,} hours)")

    weekly_scores = np.full(n_weeks, np.nan)

    # Phase 1: Score calibration period (single fit)
    X_calib = X_3d[:n_calib].reshape(n_calib * H, d)
    y_calib = np.zeros(n_calib * H, dtype=int)  # NO event labels

    eng = engine_cls(**engine_kwargs)
    scores_calib = eng.fit_score(X_calib, y_calib)

    for w in range(n_calib):
        hourly_scores = scores_calib[w * H: (w + 1) * H]
        weekly_scores[w] = hourly_scores.mean()

    # Alarm threshold from calibration period only
    calib_w_scores = weekly_scores[:n_calib]
    alarm_threshold = float(np.nanpercentile(calib_w_scores, 99))

    if verbose:
        print(f"    Alarm threshold (99th pctl of calm period): "
              f"{alarm_threshold:.4f}")

    # Phase 2: Expanding window monitoring
    n_monitor = n_weeks - n_calib
    if verbose:
        print(f"    Monitoring: week {n_calib} → {n_weeks-1} "
              f"({n_monitor} weeks) ...")

    for w in range(n_calib, n_weeks):
        n_hours = (w + 1) * H
        X_up_to_w = X_3d[:w + 1].reshape(n_hours, d)
        y_dummy = np.zeros(n_hours, dtype=int)  # NO labels — ever

        eng_w = engine_cls(**engine_kwargs)
        scores_all = eng_w.fit_score(X_up_to_w, y_dummy)

        # Weekly score = mean of last H=168 scores (this week's hours)
        weekly_scores[w] = scores_all[-H:].mean()
        del eng_w
        gc.collect()

        if verbose and (w - n_calib) % 13 == 0:  # print every ~quarter
            dt = week_dates[w]
            ws = weekly_scores[w]
            alarm = "*** ALARM" if ws > alarm_threshold else ""
            print(f"    {dt.date()}  score={ws:.4f} {alarm}")

    return weekly_scores, alarm_threshold, n_calib


# ═══════════════════════════════════════════════════════════════════
#  Main evaluation
# ═══════════════════════════════════════════════════════════════════

def run_prospective_benchmark():
    print('=' * 76)
    print('  ERCOT HOURLY — PROSPECTIVE ENGINE EARLY WARNING')
    print('  Real data: EIA hourly demand + Open-Meteo temperature')
    print('  Protocol: expanding window (weekly), NO labels used in scoring')
    print('  Alarm threshold: set from 2019-Jan to 2019-Jun calm period only')
    print('  (Exact mirror of bench_bank_level_prospective.py)')
    print('=' * 76)

    data = load_ercot()
    X_3d = data["X_3d"]
    week_dates = data["dates_weekly"]
    y_week = data["y_weekly"]
    week_labels = data["labels_weekly"]
    feat_names = data["feat_names"]

    n_weeks, H, d = X_3d.shape
    print(f'\n  Panel: W={n_weeks} weeks × {H} hours/week × d={d}')
    print(f'  Date range: {week_dates[0].date()} → {week_dates[-1].date()}')
    print(f'  Features: {feat_names}')
    print(f'  Event weeks: {int(y_week.sum())}/{n_weeks}')

    # ── Engine configurations ──
    engines = {
        "Gravity": (GravityModeEngine,
                    dict(iterations=60, k_neighbors=10)),
        "Molecular": (MolecularEngine,
                      dict(iterations=80, k_neighbors=10)),
        "Hybrid": (HybridGravityEngine, dict()),
    }

    results = {}
    for name, (cls, kwargs) in engines.items():
        print(f'\n  {"─"*70}')
        print(f'  Engine: {name}')
        print(f'  {"─"*70}')
        t0 = time.time()

        try:
            w_scores, threshold, n_calib = prospective_score(
                X_3d, week_dates, cls, kwargs,
                calib_end="2019-06-30", verbose=True
            )
        except Exception as e:
            import traceback
            print(f"    ERROR: {e}")
            traceback.print_exc()
            results[name] = {"error": str(e)}
            continue

        elapsed = time.time() - t0
        print(f'    Total time: {elapsed:.1f}s')

        # ── Evaluate (labels used ONLY here, AFTER all scoring) ──
        valid = ~np.isnan(w_scores)
        if valid.sum() >= 2 and len(np.unique(y_week[valid])) >= 2:
            auc = float(roc_auc_score(y_week[valid], w_scores[valid]))
        else:
            auc = None

        # Alarm analysis
        alarm_mask = w_scores > threshold
        crisis_mask = y_week.astype(bool)

        tp = int((alarm_mask & crisis_mask & valid).sum())
        fp = int((alarm_mask & ~crisis_mask & valid).sum())
        fn = int((~alarm_mask & crisis_mask & valid).sum())
        tn = int((~alarm_mask & ~crisis_mask & valid).sum())

        far = fp / max(fp + tn, 1)
        recall = tp / max(tp + fn, 1)
        precision = tp / max(tp + fp, 1)

        print(f'\n    AUROC: {auc:.4f}' if auc else '\n    AUROC: N/A')
        print(f'    Alarm threshold: {threshold:.4f} (99th pctl of calm)')
        print(f'    TP={tp}  FP={fp}  FN={fn}  TN={tn}')
        print(f'    Recall: {recall:.1%}')
        print(f'    Precision: {precision:.1%}')
        print(f'    FAR: {far:.1%}')

        # ── Rolling z-score (Basel-style) ──
        z_scores = np.full(n_weeks, np.nan)
        for w in range(n_calib, n_weeks):
            past = w_scores[:w][valid[:w]]
            if len(past) >= 4:
                mu = past.mean(); sigma = past.std()
                if sigma > 1e-10:
                    z_scores[w] = (w_scores[w] - mu) / sigma

        # Combined alarm: P99 OR z>2
        z_alarm_mask = np.array([not np.isnan(z_scores[w]) and z_scores[w] > 2.0
                                 for w in range(n_weeks)])
        combined_alarm = alarm_mask | z_alarm_mask

        tp_c = int((combined_alarm & crisis_mask & valid).sum())
        fp_c = int((combined_alarm & ~crisis_mask & valid).sum())
        n_normal = int((~crisis_mask & valid).sum())
        far_c = fp_c / max(n_normal, 1)
        rec_c = tp_c / max(int(crisis_mask.sum()), 1)

        print(f'\n    Combined (P99 | z>2):')
        print(f'    Recall: {rec_c:.1%}  FAR: {far_c:.1%}')

        # ── Per-event early warning ──
        print(f'\n    Per-event early warning:')
        event_results = {}

        for evt_name, (onset_ts, end_ts) in EVENT_PERIODS.items():
            # Find onset week
            onset_arr = np.where(week_dates >= onset_ts)[0]
            if len(onset_arr) == 0:
                continue
            onset_w = int(onset_arr[0])

            # Find first alarm before onset (within 20 weeks lookback)
            pre_alarms_p99 = [w for w in range(max(n_calib, onset_w - 20), onset_w)
                              if alarm_mask[w]]
            pre_alarms_z = [w for w in range(max(n_calib, onset_w - 20), onset_w)
                            if z_alarm_mask[w]]
            pre_alarms = sorted(set(pre_alarms_p99 + pre_alarms_z))

            if pre_alarms:
                first_alarm_w = pre_alarms[0]
                lead_weeks = onset_w - first_alarm_w
                lead_hours = lead_weeks * H
                lead_days = lead_weeks * 7
                alarm_date = str(week_dates[first_alarm_w].date())
                onset_date = str(week_dates[onset_w].date())
                print(f'      {evt_name:<22} lead={lead_weeks:>3} weeks '
                      f'({lead_days:>4} d / {lead_hours:>6,} h)  '
                      f'alarm={alarm_date}  ✓')
                event_results[evt_name] = {
                    "onset": onset_date, "status": "alarm",
                    "lead_weeks": lead_weeks, "lead_days": lead_days,
                    "lead_hours": lead_hours, "first_alarm": alarm_date,
                }
            else:
                # Check if alarm fires during the event itself
                evt_alarms = [w for w in range(onset_w, min(onset_w + 8, n_weeks))
                              if combined_alarm[w]]
                if evt_alarms:
                    print(f'      {evt_name:<22} detected at '
                          f'{week_dates[evt_alarms[0]].date()} (concurrent)')
                    event_results[evt_name] = {
                        "onset": str(week_dates[onset_w].date()),
                        "status": "concurrent",
                    }
                else:
                    print(f'      {evt_name:<22} NO ALARM')
                    event_results[evt_name] = {
                        "onset": str(week_dates[onset_w].date()),
                        "status": "no_alarm",
                    }

        # ── Score timeline (key weeks) ──
        key_dates = [
            ("2019-03-01", "Early 2019 calm"),
            ("2019-06-01", "Calib end"),
            ("2019-08-01", "SummerPeak onset"),
            ("2019-08-15", "SummerPeak"),
            ("2019-12-01", "Pre-COVID calm"),
            ("2020-03-01", "COVID build-up"),
            ("2020-03-22", "COVID onset"),
            ("2020-06-01", "COVID Q2"),
            ("2020-09-01", "COVID recovery"),
            ("2021-01-01", "Pre-Uri"),
            ("2021-02-01", "Uri build-up"),
            ("2021-02-15", "Uri peak"),
            ("2021-06-01", "Post-Uri"),
            ("2022-06-01", "Mid-2022"),
            ("2022-12-01", "Pre-Elliott"),
            ("2022-12-22", "Elliott onset"),
        ]

        print(f'\n    Score timeline (selected weeks):')
        print(f'    {"Date":<14} {"Score":>8} {"Thresh":>8} '
              f'{"Z":>6} {"Status":<18} {"Event"}')
        print(f'    {"─"*76}')
        for ds, event in key_dates:
            dt = pd.Timestamp(ds)
            idx = np.argmin(np.abs(week_dates - dt))
            if idx < len(w_scores) and not np.isnan(w_scores[idx]):
                sc = w_scores[idx]
                z = z_scores[idx] if not np.isnan(z_scores[idx]) else 0.0
                is_event = y_week[idx] == 1
                is_alarm = combined_alarm[idx]
                if is_alarm and is_event:
                    status = "TRUE ALARM"
                elif is_alarm and not is_event:
                    # Near-event?
                    near = any(abs(idx - j) <= 2
                               for j in np.where(crisis_mask)[0])
                    status = "EARLY WARNING" if near else "FALSE ALARM"
                elif not is_alarm and is_event:
                    status = "MISSED"
                else:
                    status = "quiet"
                marker = "***" if is_alarm else "   "
                print(f'    {week_dates[idx].date()!s:<14} {sc:>8.4f} '
                      f'{threshold:>8.4f} {z:>+6.2f} '
                      f'{status:<18} {event} {marker}')

        # ── Z-score early warning timeline ──
        print(f'\n    Z-score timeline (alarms only):')
        z_alarm_weeks = [w for w in range(n_calib, n_weeks) if z_alarm_mask[w]]
        for w in z_alarm_weeks[:20]:  # first 20
            evt = week_labels[w]
            print(f'      {week_dates[w].date()}  z={z_scores[w]:+.2f}  '
                  f'score={w_scores[w]:.4f}  '
                  f'{"EVENT: " + evt if evt != "Normal" else ""}')
        if len(z_alarm_weeks) > 20:
            print(f'      ... ({len(z_alarm_weeks) - 20} more)')

        results[name] = {
            "auc": auc, "far": far, "recall": recall,
            "precision": precision, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "threshold": round(threshold, 6),
            "far_combined": round(far_c, 4),
            "recall_combined": round(rec_c, 4),
            "elapsed": round(elapsed, 1),
            "events": event_results,
        }
        gc.collect()

    # ═══════════════════════════════════════════════════════════════
    #  Summary
    # ═══════════════════════════════════════════════════════════════
    print(f'\n{"="*76}')
    print(f'  PROSPECTIVE ERCOT EARLY WARNING VERDICT')
    print(f'  (no hindsight — threshold from Jan-Jun 2019 calm only)')
    print(f'{"="*76}')
    for name, r in results.items():
        if "error" in r:
            print(f'\n  {name}: ERROR — {r["error"][:60]}')
            continue
        print(f'\n  {name}:')
        print(f'    AUROC:     {r["auc"]:.4f}' if r["auc"] else '    AUROC: N/A')
        print(f'    Recall:    {r["recall"]:.1%} (P99 only) / '
              f'{r["recall_combined"]:.1%} (combined)')
        print(f'    FAR:       {r["far"]:.1%} (P99 only) / '
              f'{r["far_combined"]:.1%} (combined)')
        print(f'    Time:      {r["elapsed"]:.0f}s')
        for evt, er in r.get("events", {}).items():
            if er["status"] == "alarm":
                print(f'    {evt}: {er["lead_weeks"]}w / '
                      f'{er["lead_days"]}d / {er["lead_hours"]:,}h lead')
            else:
                print(f'    {evt}: {er["status"]}')

    # ── Save ──
    out_file = ROOT / "results" / "ercot_prospective_results.json"

    def _safe(obj):
        if isinstance(obj, dict):
            return {k: _safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_safe(v) for v in obj]
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    with open(out_file, 'w') as f:
        json.dump(_safe({
            "meta": {
                "protocol": "Expanding-window prospective (bench_bank_level_"
                            "prospective.py mirror)",
                "refit": "weekly (168h blocks)",
                "threshold": "P99 of calibration weeks + z>2 Basel-style",
                "calibration": "2019-Jan to 2019-Jun (~26 weeks)",
                "data": "EIA hourly demand + Open-Meteo temp, d=5",
                "run_date": time.strftime("%Y-%m-%d %H:%M"),
            },
            "engines": results,
        }), f, indent=2)
    print(f'\n  Saved → {out_file}')


if __name__ == "__main__":
    run_prospective_benchmark()
