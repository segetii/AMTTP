#!/usr/bin/env python3
"""
Physics Engine — ERCOT Supply-Only (d=5)
==========================================
Runs MolecularEngine / GravityModeEngine / HybridGravityEngine
on ERCOT supply-side capacity factors: wind_cf, solar_cf, gas_cf, coal_cf, nuclear_cf.

HEADLINE METRICS (per event):
  TABLE 1  LEAD-TIME: days of warning before each collapse event
  TABLE 2  FALSE ALARMS: #false triggers in normal windows around each event
  TABLE 3  PER-EVENT DETECTION: caught/missed per event per engine
  TABLE 4  AUC & F1 (standard accuracy)
  TABLE 5  AUC ranking across representations
  TABLE 6  Timing

Also runs combined (d=10) for direct comparison.
"""
from __future__ import annotations
import sys, os, time, warnings, json
import numpy as np

warnings.filterwarnings("ignore")

ROOT = r"c:\amttp"
HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.join(ROOT, "research", "udl"))
sys.path.insert(0, os.path.join(ROOT, "research", "udl", "src"))
sys.path.insert(0, HERE)

from test_full_collapse_x_domains import (
    build_reps, auc_manual, clean_array,
    load_ercot, daily_aggregate, ERCOT_DIR,
)
from udl.system_mode import MolecularEngine, GravityModeEngine, HybridGravityEngine

W = 110
ENGINE_NAMES = ['Molecular(LJ)', 'Gravity(N-body)', 'Hybrid(Mol+Grav)']


# ═══════════════════════════════════════════════════════════════════
# METRIC HELPERS
# ═══════════════════════════════════════════════════════════════════

def _f1_metrics(y_true, scores):
    a = auc_manual(y_true, scores)
    n_pos, n_neg = int(y_true.sum()), int(len(y_true) - y_true.sum())
    if n_pos == 0 or n_neg == 0:
        return dict(auc=a, thresh=0, prec=0, rec=0, f1=0, far=0)
    threshs = np.unique(scores)
    if len(threshs) > 200:
        threshs = np.percentile(scores, np.linspace(0, 100, 200))
    best = dict(f1=0, thresh=0, prec=0, rec=0, far=0)
    for th in threshs:
        pred = scores >= th
        tp = int((pred & (y_true == 1)).sum())
        fp = int((pred & (y_true == 0)).sum())
        fn = int((~pred & (y_true == 1)).sum())
        p = tp / (tp + fp) if (tp + fp) else 0
        r = tp / (tp + fn) if (tp + fn) else 0
        f1 = 2 * p * r / (p + r) if (p + r) else 0
        far = fp / n_neg
        if f1 > best['f1']:
            best = dict(f1=f1, thresh=th, prec=p, rec=r, far=far)
    best['auc'] = a
    return best


def _lead_time_days(scores, dates, onset_date, threshold):
    """Days score > threshold BEFORE onset_date. Returns (lead_days, first_alarm_date)."""
    onset_idx = np.where(dates >= onset_date)[0]
    if len(onset_idx) == 0:
        return None, None
    onset_idx = onset_idx[0]
    pre = scores[:onset_idx]
    above = np.where(pre > threshold)[0]
    if len(above) == 0:
        return 0, None
    first = above[0]
    lead = onset_idx - first
    return int(lead), str(dates[first])


def _false_alarms_around_event(scores, dates, lab, onset_date, threshold, window_days=30):
    """Count false alarms in the normal window BEFORE the event (window_days before onset).
    Returns (n_false_alarms, n_normal_days_in_window)."""
    onset_idx = np.where(dates >= onset_date)[0]
    if len(onset_idx) == 0:
        return 0, 0
    onset_idx = onset_idx[0]
    start = max(0, onset_idx - window_days)
    window_mask = np.zeros(len(dates), dtype=bool)
    window_mask[start:onset_idx] = True
    # Only count normal days
    normal_in_window = window_mask & (lab == "normal")
    n_normal = int(normal_in_window.sum())
    if n_normal == 0:
        return 0, 0
    n_fa = int((scores[normal_in_window] > threshold).sum())
    return n_fa, n_normal


def _per_event_detection(scores, lab, threshold, event_names):
    """For each event, how many event-days were caught (score > threshold)."""
    out = {}
    for ev in event_names:
        ev_mask = lab == ev
        n_total = int(ev_mask.sum())
        if n_total == 0:
            out[ev] = (0, 0)
            continue
        n_caught = int((scores[ev_mask] > threshold).sum())
        out[ev] = (n_caught, n_total)
    return out


# ═══════════════════════════════════════════════════════════════════
# DATA LOADER
# ═══════════════════════════════════════════════════════════════════

def _load_ercot(mode):
    if not os.path.exists(ERCOT_DIR):
        return None
    X_hr, features, dates_hr, y_hr, labels_hr, ev_onsets = load_ercot(mode)
    X_daily, dates, y_daily, lab = daily_aggregate(X_hr, dates_hr, y_hr, labels_hr)
    N, d = X_daily.shape
    for c in range(d):
        bad = np.isnan(X_daily[:, c])
        if bad.any():
            X_daily[bad, c] = np.nanmean(X_daily[:, c])

    ref_mask = (dates >= "2019-04-01") & (dates < "2019-07-01")
    X_ref = X_daily[ref_mask]

    return dict(X_ref=X_ref, X_all=X_daily, y=y_daily,
                dates=dates, lab=lab, features=features,
                event_onsets=ev_onsets, mode=mode)


# ═══════════════════════════════════════════════════════════════════
# RUN PHYSICS ENGINES
# ═══════════════════════════════════════════════════════════════════

def _run_single_engine(name, X, y):
    t0 = time.perf_counter()
    try:
        if name == 'Molecular(LJ)':
            eng = MolecularEngine(calibrate='combined', target_far=0.05)
        elif name == 'Gravity(N-body)':
            eng = GravityModeEngine(calibrate='combined', target_far=0.05)
        elif name == 'Hybrid(Mol+Grav)':
            eng = HybridGravityEngine(calibrate='combined', target_far=0.05)
        else:
            return None, 0
        scores = eng.fit_score(X, y)
        elapsed = (time.perf_counter() - t0) * 1000
        return scores, elapsed
    except Exception as ex:
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"      [{name} FAILED: {ex}]")
        return None, elapsed


def _run_all(data, tag):
    X_ref, X_all, y = data['X_ref'], data['X_all'], data['y']
    dates, lab = data['dates'], data['lab']

    print(f"\n  Building 5 UDL representations …")
    reps = build_reps(X_ref, X_all)
    rep_names = ['Raw'] + list(reps.keys())
    print(f"  Built: {rep_names}")

    # results[rep_name][engine_name] = {'scores', 'time_ms', 'auc'}
    results = {}
    for rn in rep_names:
        Ra = X_all if rn == 'Raw' else reps[rn]['all']
        D = Ra.shape[1]
        print(f"\n  ── {rn} ({D}D) ──")
        results[rn] = {}
        for eng_name in ENGINE_NAMES:
            print(f"    {eng_name} …", end='', flush=True)
            scores, t_ms = _run_single_engine(eng_name, Ra, y)
            if scores is not None:
                auc = auc_manual(y, scores)
                results[rn][eng_name] = {'scores': scores, 'time_ms': t_ms, 'auc': auc}
                print(f"  AUC={auc:.4f}  ({t_ms:.0f}ms)")
            else:
                results[rn][eng_name] = None
                print(f"  FAILED ({t_ms:.0f}ms)")

    return results, rep_names


# ═══════════════════════════════════════════════════════════════════
# SUMMARY TABLES — LEAD-TIME & FALSE ALARM FOCUS
# ═══════════════════════════════════════════════════════════════════

def _print_tables(tag, results, rep_names, data):
    y = data['y']
    dates = data['dates']
    lab = data['lab']
    ev_onsets = data['event_onsets']
    event_names = list(ev_onsets.keys())

    print(f"\n{'█' * W}")
    print(f"  {tag} — PHYSICS ENGINE RESULTS")
    print(f"{'█' * W}")

    # ── First, compute F1-optimal thresholds per engine×rep ──
    # We'll use these for lead-time and false alarm calculations
    thresholds = {}
    for rn in rep_names:
        thresholds[rn] = {}
        for eng_name in ENGINE_NAMES:
            r = results[rn].get(eng_name)
            if r is None:
                thresholds[rn][eng_name] = 0.5
                continue
            m = _f1_metrics(y, r['scores'])
            thresholds[rn][eng_name] = m['thresh']

    # ══════════════════════════════════════════════════════════
    # TABLE 1: LEAD-TIME PER EVENT
    # ══════════════════════════════════════════════════════════
    print(f"\n{'═' * W}")
    print(f"  TABLE 1 — LEAD-TIME BEFORE EACH COLLAPSE EVENT  [{tag}]")
    print(f"{'═' * W}")
    print(f"  Lead = days score > F1-optimal threshold BEFORE event onset")
    print(f"  Also showing fixed thresholds: ↑=score>0.5, ↑↑=score>0.7\n")

    for ev in event_names:
        onset = ev_onsets[ev][:10]
        ev_days = int((lab == ev).sum())
        print(f"  ┌─ {ev}  (onset: {onset}, {ev_days} event days)")
        print(f"  │ {'Engine':<18s} {'Rep':<16s} │ {'Lead(F1θ)':>10s} │ {'Lead(>0.5)':>10s} │ "
              f"{'Lead(>0.7)':>10s} │ {'1st alarm':>12s}")
        print(f"  │ {'─' * 90}")

        for eng_name in ENGINE_NAMES:
            # Find best rep for this engine (by AUC)
            best_rn, best_auc = None, -1
            for rn in rep_names:
                r = results[rn].get(eng_name)
                if r is not None and r['auc'] > best_auc:
                    best_rn, best_auc = rn, r['auc']

            for rn in rep_names:
                r = results[rn].get(eng_name)
                if r is None:
                    continue
                scores = r['scores']
                th_f1 = thresholds[rn][eng_name]

                l_f1, d_f1 = _lead_time_days(scores, dates, onset, th_f1)
                l_50, d_50 = _lead_time_days(scores, dates, onset, 0.5)
                l_70, d_70 = _lead_time_days(scores, dates, onset, 0.7)

                marker = " ◄" if rn == best_rn else ""
                l_f1_s = f"{l_f1:>6d} d" if l_f1 is not None and l_f1 > 0 else "    — "
                l_50_s = f"{l_50:>6d} d" if l_50 is not None and l_50 > 0 else "    — "
                l_70_s = f"{l_70:>6d} d" if l_70 is not None and l_70 > 0 else "    — "
                d_show = d_f1 if d_f1 else "—"

                print(f"  │ {eng_name:<18s} {rn:<16s} │ {l_f1_s:>10s} │ {l_50_s:>10s} │ "
                      f"{l_70_s:>10s} │ {d_show:>12s}{marker}")

            if eng_name != ENGINE_NAMES[-1]:
                print(f"  │ {'· · ·':^90s}")
        print(f"  └{'─' * (W-2)}")

    # ══════════════════════════════════════════════════════════
    # TABLE 2: FALSE ALARMS PER EVENT (30-day pre-event window)
    # ══════════════════════════════════════════════════════════
    print(f"\n{'═' * W}")
    print(f"  TABLE 2 — FALSE ALARMS IN 30-DAY PRE-EVENT WINDOW  [{tag}]")
    print(f"{'═' * W}")
    print(f"  FA = normal days with score > F1-threshold in the 30 days before event onset")
    print(f"  Lower is better. Shows FA/total_normal_days_in_window.\n")

    print(f"  {'Engine':<18s} {'Rep':<16s} │", end='')
    for ev in event_names:
        print(f" {ev[:12]:>12s} │", end='')
    print(f" {'Total FA':>8s} │ {'Global FAR':>10s}")
    print(f"  {'─' * (34 + 14 * len(event_names) + 24)}")

    for eng_name in ENGINE_NAMES:
        for rn in rep_names:
            r = results[rn].get(eng_name)
            if r is None:
                continue
            scores = r['scores']
            th = thresholds[rn][eng_name]
            row = f"  {eng_name:<18s} {rn:<16s} │"
            total_fa = 0
            total_norm = 0
            for ev in event_names:
                onset = ev_onsets[ev][:10]
                fa, nn = _false_alarms_around_event(scores, dates, lab, onset, th, 30)
                total_fa += fa
                total_norm += nn
                row += f" {fa:>5d}/{nn:<5d} │"
            # Global FAR
            global_fa = int((scores[lab == "normal"] > th).sum())
            global_nn = int((lab == "normal").sum())
            global_far = global_fa / global_nn if global_nn > 0 else 0
            row += f" {total_fa:>8d} │ {global_far:9.1%}"
            print(row)
        print(f"  {'─' * (34 + 14 * len(event_names) + 24)}")

    # ══════════════════════════════════════════════════════════
    # TABLE 3: PER-EVENT DETECTION
    # ══════════════════════════════════════════════════════════
    print(f"\n{'═' * W}")
    print(f"  TABLE 3 — PER-EVENT DETECTION (caught/total event-days)  [{tag}]")
    print(f"{'═' * W}")
    print(f"  Threshold = F1-optimal per engine×rep.\n")

    print(f"  {'Engine':<18s} {'Rep':<16s} │", end='')
    for ev in event_names:
        n_ev = int((lab == ev).sum())
        print(f" {ev[:12]+f'({n_ev})':>16s} │", end='')
    print(f" {'Total':>10s}")
    print(f"  {'─' * (34 + 18 * len(event_names) + 14)}")

    for eng_name in ENGINE_NAMES:
        best_rn = max(rep_names,
                      key=lambda rn: results[rn].get(eng_name, {}).get('auc', -1)
                      if results[rn].get(eng_name) else -1)
        for rn in rep_names:
            r = results[rn].get(eng_name)
            if r is None:
                continue
            scores = r['scores']
            th = thresholds[rn][eng_name]
            det = _per_event_detection(scores, lab, th, event_names)
            row = f"  {eng_name:<18s} {rn:<16s} │"
            total_caught, total_days = 0, 0
            for ev in event_names:
                c, t = det[ev]
                total_caught += c
                total_days += t
                pct = f"{100*c/t:.0f}%" if t > 0 else "—"
                row += f" {c:>5d}/{t:<4d} {pct:>4s} │"
            marker = " ◄" if rn == best_rn else ""
            row += f" {total_caught:>4d}/{total_days:<4d}{marker}"
            print(row)
        print(f"  {'─' * (34 + 18 * len(event_names) + 14)}")

    # ══════════════════════════════════════════════════════════
    # TABLE 4: AUC & F1 ACCURACY
    # ══════════════════════════════════════════════════════════
    print(f"\n{'═' * W}")
    print(f"  TABLE 4 — AUC & F1 ACCURACY  [{tag}]")
    print(f"{'═' * W}")

    for eng_name in ENGINE_NAMES:
        print(f"\n  {eng_name}:")
        print(f"  {'Rep':<16s} │ {'AUC':>6s} │ {'θ*':>8s} │ {'Prec':>6s} │ {'Rec':>6s} │ "
              f"{'F1':>6s} │ {'FAR':>6s} │ {'FP':>5s} │ {'FN':>5s}")
        print(f"  {'─' * 78}")
        for rn in rep_names:
            r = results[rn].get(eng_name)
            if r is None:
                continue
            m = _f1_metrics(y, r['scores'])
            n_pos = int(y.sum())
            n_neg = len(y) - n_pos
            fp = int(m['far'] * n_neg)
            fn = int((1 - m['rec']) * n_pos) if m['rec'] > 0 else n_pos
            print(f"  {rn:<16s} │ {m['auc']:6.4f} │ {m['thresh']:8.3f} │ "
                  f"{m['prec']:6.3f} │ {m['rec']:6.3f} │ {m['f1']:6.3f} │ "
                  f"{m['far']:6.3f} │ {fp:>5d} │ {fn:>5d}")

    # Best per rep
    print(f"\n  Best Engine per Representation:")
    print(f"  {'Rep':<16s} │ {'Engine':<18s} │ {'AUC':>6s} │ {'F1':>6s} │ {'FAR':>6s}")
    print(f"  {'─' * 65}")
    for rn in rep_names:
        best_eng, best_auc = None, -1
        for eng_name in ENGINE_NAMES:
            r = results[rn].get(eng_name)
            if r is not None and r['auc'] > best_auc:
                best_eng, best_auc = eng_name, r['auc']
        if best_eng:
            m = _f1_metrics(y, results[rn][best_eng]['scores'])
            print(f"  {rn:<16s} │ {best_eng:<18s} │ {m['auc']:6.4f} │ {m['f1']:6.3f} │ {m['far']:6.3f}")

    # ══════════════════════════════════════════════════════════
    # TABLE 5: AUC RANKING
    # ══════════════════════════════════════════════════════════
    print(f"\n{'═' * W}")
    print(f"  TABLE 5 — AUC RANKING  [{tag}]")
    print(f"{'═' * W}")

    hdr = f"  {'Engine':<18s} │"
    for rn in rep_names:
        hdr += f" {rn[:14]:>14s} │"
    hdr += f" {'Mean':>6s} │ {'Best Rep':<16s}"
    print(f"\n{hdr}")
    print(f"  {'─' * (18 + 16 * len(rep_names) + 30)}")

    for eng_name in ENGINE_NAMES:
        row = f"  {eng_name:<18s} │"
        vals = []
        best_rn_eng, best_a = None, -1
        for rn in rep_names:
            r = results[rn].get(eng_name)
            if r is not None:
                row += f" {r['auc']:14.4f} │"
                vals.append(r['auc'])
                if r['auc'] > best_a:
                    best_rn_eng, best_a = rn, r['auc']
            else:
                row += f" {'FAIL':>14s} │"
        mn = np.mean(vals) if vals else 0
        row += f" {mn:6.4f} │ {best_rn_eng or 'N/A':<16s}"
        print(row)

    # ══════════════════════════════════════════════════════════
    # TABLE 6: TIMING
    # ══════════════════════════════════════════════════════════
    print(f"\n{'═' * W}")
    print(f"  TABLE 6 — EXECUTION TIME  [{tag}]")
    print(f"{'═' * W}")
    hdr = f"  {'Engine':<18s} │"
    for rn in rep_names:
        hdr += f" {rn[:14]:>14s} │"
    hdr += f" {'Mean':>8s}"
    print(f"\n{hdr}")
    print(f"  {'─' * (18 + 16 * len(rep_names) + 12)}")
    for eng_name in ENGINE_NAMES:
        row = f"  {eng_name:<18s} │"
        times = []
        for rn in rep_names:
            r = results[rn].get(eng_name)
            if r is not None:
                row += f" {r['time_ms']:13.0f}ms │"
                times.append(r['time_ms'])
            else:
                row += f" {'FAIL':>14s} │"
        mn = np.mean(times) if times else 0
        row += f" {mn:7.0f}ms"
        print(row)


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    t_start = time.perf_counter()

    print("=" * W)
    print("  ERCOT PHYSICS ENGINE BENCHMARK")
    print("  MolecularEngine (LJ) │ GravityModeEngine (N-body) │ HybridGravityEngine")
    print("  Supply-Only (d=5): wind_cf, solar_cf, gas_cf, coal_cf, nuclear_cf")
    print("  Combined (d=10):  + demand_gw, ramp_rate, vol_6h, dev_24h, temp_stress")
    print("  × 5 UDL representations")
    print("  FOCUS: Lead-time before event, False alarms per event, Per-event detection")
    print("=" * W)

    # ── SUPPLY-ONLY ──
    print(f"\n{'█' * W}")
    print(f"  ERCOT SUPPLY-ONLY (d=5: wind_cf, solar_cf, gas_cf, coal_cf, nuclear_cf)")
    print(f"{'█' * W}")

    data_sup = _load_ercot("supply")
    if data_sup is None:
        print("  SKIPPED: ERCOT data not found")
    else:
        X_ref, X_all = data_sup['X_ref'], data_sup['X_all']
        print(f"  Features: {data_sup['features']}")
        print(f"  Daily: {X_all.shape}  ref: {X_ref.shape}  crisis frac: {data_sup['y'].mean():.1%}")
        print(f"  Events: {list(data_sup['event_onsets'].keys())}")
        for ev_name in data_sup['event_onsets']:
            n = int((data_sup['lab'] == ev_name).sum())
            print(f"    {ev_name}: onset={data_sup['event_onsets'][ev_name][:10]}, {n} days")

        results_sup, reps_sup = _run_all(data_sup, "ERCOT-Supply")
        _print_tables("ERCOT SUPPLY-ONLY (d=5)", results_sup, reps_sup, data_sup)

    # ── COMBINED ──
    print(f"\n\n{'█' * W}")
    print(f"  ERCOT COMBINED (d=10: demand + supply)")
    print(f"{'█' * W}")

    data_comb = _load_ercot("combined")
    if data_comb is None:
        print("  SKIPPED: ERCOT data not found")
    else:
        X_ref, X_all = data_comb['X_ref'], data_comb['X_all']
        print(f"  Features: {data_comb['features']}")
        print(f"  Daily: {X_all.shape}  ref: {X_ref.shape}  crisis frac: {data_comb['y'].mean():.1%}")

        results_comb, reps_comb = _run_all(data_comb, "ERCOT-Combined")
        _print_tables("ERCOT COMBINED (d=10)", results_comb, reps_comb, data_comb)

    # ── HEAD-TO-HEAD: Supply vs Combined ──
    if data_sup and data_comb:
        print(f"\n{'█' * W}")
        print(f"  HEAD-TO-HEAD: Supply (d=5) vs Combined (d=10)")
        print(f"{'█' * W}")

        print(f"\n  Best AUC per engine:")
        print(f"  {'Engine':<18s} │ {'Supply best':>14s} │ {'Combined best':>14s} │ {'Winner':>10s}")
        print(f"  {'─' * 65}")
        for eng_name in ENGINE_NAMES:
            best_s = max((results_sup[rn].get(eng_name, {}).get('auc', -1)
                         if results_sup[rn].get(eng_name) else -1)
                        for rn in reps_sup)
            best_c = max((results_comb[rn].get(eng_name, {}).get('auc', -1)
                         if results_comb[rn].get(eng_name) else -1)
                        for rn in reps_comb)
            winner = "Supply" if best_s > best_c else ("Combined" if best_c > best_s else "Tie")
            print(f"  {eng_name:<18s} │ {best_s:14.4f} │ {best_c:14.4f} │ {winner:>10s}")

        # Per-event lead-time comparison (best engine×rep for each mode)
        print(f"\n  Best lead-time per event (best engine×rep, F1-optimal threshold):")
        ev_names = list(data_sup['event_onsets'].keys())
        print(f"  {'Event':<22s} │ {'Supply lead':>14s} │ {'Combined lead':>14s}")
        print(f"  {'─' * 55}")

        for ev in ev_names:
            onset = data_sup['event_onsets'][ev][:10]
            # Find best lead for supply
            best_lead_s = 0
            for rn in reps_sup:
                for eng_name in ENGINE_NAMES:
                    r = results_sup[rn].get(eng_name)
                    if r is None:
                        continue
                    m = _f1_metrics(data_sup['y'], r['scores'])
                    l, _ = _lead_time_days(r['scores'], data_sup['dates'], onset, m['thresh'])
                    if l is not None and l > best_lead_s:
                        best_lead_s = l
            # Find best lead for combined
            best_lead_c = 0
            for rn in reps_comb:
                for eng_name in ENGINE_NAMES:
                    r = results_comb[rn].get(eng_name)
                    if r is None:
                        continue
                    m = _f1_metrics(data_comb['y'], r['scores'])
                    l, _ = _lead_time_days(r['scores'], data_comb['dates'], onset, m['thresh'])
                    if l is not None and l > best_lead_c:
                        best_lead_c = l

            print(f"  {ev:<22s} │ {best_lead_s:>11d} d  │ {best_lead_c:>11d} d")

    elapsed = time.perf_counter() - t_start
    print(f"\n{'=' * W}")
    print(f"  COMPLETED in {elapsed:.1f}s")
    print(f"{'=' * W}")
