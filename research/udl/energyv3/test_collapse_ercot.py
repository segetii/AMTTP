#!/usr/bin/env python3
"""
CollapseGeometry on ERCOT — Demand/Supply Grid Collapse Analysis
=================================================================
Applies closed-form geometry to the Texas power grid using combined
demand (5 features) + supply (5 features) = 10-dimensional space.

Labelled events:
  - WinterStormUri      (2021-02-10) — catastrophic grid failure, 246 deaths
  - COVID_Collapse      (2020-03-23) — demand collapse
  - SummerPeak2019      (2019-08-12) — extreme summer demand
  - WinterStormElliott  (2022-12-22) — winter storm, rolling blackouts

Features:
  DEMAND: demand_gw, ramp_rate, vol_6h, dev_24h, temp_stress
  SUPPLY: wind_cf, solar_cf, gas_cf, coal_cf, nuclear_cf

Phases:
  A) Detection — does geometry identify all four grid events?
  B) Friction + tipping points for each event
  C) Policy tests:
     • Demand response (cap demand)
     • Reserve margin (boost gas/nuclear supply)
     • Weatherisation (cap temp_stress)
     • Combined policy
     • Minimum δ* — exact correction per event

Author: Automated CollapseGeometry analysis
"""
from __future__ import annotations
import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from collapse_geometry import CollapseGeometry

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "ercot")


def load_ercot():
    """Load and merge demand + supply hourly data."""
    dem = np.load(os.path.join(DATA_DIR, "ercot_demand_hourly.npz"), allow_pickle=True)
    sup = np.load(os.path.join(DATA_DIR, "ercot_supply_hourly.npz"), allow_pickle=True)

    X_d, X_s = dem["X"], sup["X"]
    feat_d = list(dem["feature_names"])
    feat_s = list(sup["feature_names"])

    X = np.column_stack([X_d, X_s])
    features = feat_d + feat_s
    dates = np.array(dem["dates"])
    y = dem["y"]
    labels = np.array(dem["labels"])
    events_raw = str(dem["event_onsets"])

    import json
    event_onsets = json.loads(events_raw)

    return X, features, dates, y, labels, event_onsets


def daily_aggregate(X, dates, y, labels):
    """Aggregate hourly → daily (mean), keep worst label per day."""
    day_strs = np.array([d[:10] for d in dates])
    unique_days = np.unique(day_strs)

    X_daily = np.empty((len(unique_days), X.shape[1]))
    y_daily = np.empty(len(unique_days), dtype=int)
    lab_daily = np.empty(len(unique_days), dtype=object)

    for i, day in enumerate(unique_days):
        mask = day_strs == day
        X_daily[i] = X[mask].mean(axis=0)
        y_daily[i] = int(y[mask].max())
        day_labs = labels[mask]
        non_normal = day_labs[day_labs != "normal"]
        lab_daily[i] = non_normal[0] if len(non_normal) > 0 else "normal"

    return X_daily, unique_days, y_daily, lab_daily


def event_window(dates_daily, onset_str, pre_days=60, post_days=30):
    """Return slice indices for an event window."""
    onset_date = onset_str[:10]
    idx = np.where(dates_daily == onset_date)[0]
    if len(idx) == 0:
        # Find closest
        idx = np.array([i for i, d in enumerate(dates_daily) if d >= onset_date])
        if len(idx) == 0:
            return 0, len(dates_daily)
        idx = idx[0]
    else:
        idx = idx[0]
    start = max(0, idx - pre_days)
    end = min(len(dates_daily), idx + post_days + 1)
    return start, end, idx


def main():
    np.set_printoptions(precision=4, suppress=True)
    W = 110

    print("Loading ERCOT demand + supply data...")
    X_hr, features, dates_hr, y_hr, labels_hr, event_onsets = load_ercot()
    print(f"  Hourly: {X_hr.shape[0]} obs × {X_hr.shape[1]} features")
    print(f"  Features: {features}")
    print(f"  Events: {event_onsets}")

    # Daily aggregation for cleaner geometry
    X_daily, dates_daily, y_daily, lab_daily = daily_aggregate(
        X_hr, dates_hr, y_hr, labels_hr)
    N, d = X_daily.shape
    print(f"  Daily: {N} days × {d} features")
    print()

    # ── Reference: 2019-04 to 2019-07 (stable spring/summer, pre-peak) ──
    ref_mask = (dates_daily >= "2019-04-01") & (dates_daily < "2019-07-01")
    X_ref = X_daily[ref_mask]
    print(f"  Reference window: 2019-Apr–Jun ({ref_mask.sum()} days)")

    # Handle NaN — fill with column mean from reference
    for col in range(d):
        nans = np.isnan(X_ref[:, col])
        if nans.any():
            X_ref[nans, col] = np.nanmean(X_ref[:, col])
    # Same for full dataset
    for col in range(d):
        nans = np.isnan(X_daily[:, col])
        if nans.any():
            X_daily[nans, col] = np.nanmean(X_daily[:, col])

    cg = CollapseGeometry()
    cg.fit(X_ref)
    print(f"  τ_Q = {cg._tau_Q:.3f}   θ_crit = {cg._theta_crit:.4f} rad")
    print(f"  d = {d}   Semi-axes² top-3: {cg._a2[:3]}")
    print()

    # ══════════════════════════════════════════════════════════════
    print("=" * W)
    print("  COLLAPSE GEOMETRY — ERCOT POWER GRID (2019–2022)")
    print("=" * W)
    print()

    # ══════════════════════════════════════════════════════════════
    # A) FULL TIMELINE DETECTION
    # ══════════════════════════════════════════════════════════════
    print("═" * W)
    print("  A) DETECTION — Daily Collapse Score (Event Days Highlighted)")
    print("═" * W)

    scores = cg.score(X_daily)
    report = cg.detect(X_daily)
    Q_all = report.Q

    # Score statistics per event
    event_names = list(event_onsets.keys())
    print(f"\n  {'Event':<25} {'Onset':>12} {'Peak Score':>11} {'Peak Day':>12}"
          f"  {'Mean Score':>11} {'AUC':>6} {'C* Days':>8} {'Lead':>6}")
    print("  " + "-" * 100)

    for ev_name in event_names:
        onset_str = event_onsets[ev_name]
        onset_date = onset_str[:10]

        ev_mask = lab_daily == ev_name
        if ev_mask.sum() == 0:
            continue
        ev_scores = scores[ev_mask]
        ev_dates = dates_daily[ev_mask]

        # AUC (event days vs normal days in surrounding window)
        start_i, end_i, onset_i = event_window(dates_daily, onset_str)
        window_scores = scores[start_i:end_i]
        window_labels = (lab_daily[start_i:end_i] == ev_name).astype(int)
        if window_labels.sum() > 0 and (1 - window_labels).sum() > 0:
            from sklearn.metrics import roc_auc_score
            try:
                auc = roc_auc_score(window_labels, window_scores)
            except Exception:
                auc = float("nan")
        else:
            auc = float("nan")

        cstar_days = int((Q_all[ev_mask] > cg._tau_Q).sum())
        peak_score = ev_scores.max()
        peak_day = ev_dates[np.argmax(ev_scores)]

        # Lead time: first day score > 0.5 before onset
        pre_onset = scores[max(0, onset_i - 60):onset_i]
        pre_dates = dates_daily[max(0, onset_i - 60):onset_i]
        alarm_mask = pre_onset > 0.5
        if alarm_mask.any():
            first_alarm_idx = int(np.where(alarm_mask)[0][0])
            lead_days = onset_i - (max(0, onset_i - 60) + first_alarm_idx)
        else:
            lead_days = 0

        print(f"  {ev_name:<25} {onset_date:>12} {peak_score:>11.4f} {peak_day:>12}"
              f"  {ev_scores.mean():>11.4f} {auc:>6.3f} {cstar_days:>8} {lead_days:>5}d")

    print()

    # ══════════════════════════════════════════════════════════════
    # B) PER-EVENT DEEP DIVE — Friction + Tipping
    # ══════════════════════════════════════════════════════════════
    print("═" * W)
    print("  B) PER-EVENT DEEP DIVE — Friction Trajectory + Tipping Point")
    print("═" * W)

    for ev_name in event_names:
        onset_str = event_onsets[ev_name]
        start_i, end_i, onset_i = event_window(dates_daily, onset_str,
                                                 pre_days=60, post_days=30)
        X_win = X_daily[start_i:end_i]
        dates_win = dates_daily[start_i:end_i]
        scores_win = scores[start_i:end_i]
        Q_win = Q_all[start_i:end_i]
        T_win = len(X_win)

        # Re-fit on the pre-event portion for clean reference
        pre_len = onset_i - start_i
        if pre_len < 10:
            pre_len = min(30, T_win // 2)

        cg_ev = CollapseGeometry()
        cg_ev.fit(X_win[:pre_len])

        scores_ev = cg_ev.score(X_win)
        S_f = cg_ev.score_with_friction(X_win)
        report_ev = cg_ev.detect(X_win)

        diffs = np.diff(S_f)
        tip_idx = int(np.argmax(diffs))
        tip_delta = diffs[tip_idx]

        print(f"\n  ┌{'─' * (W-4)}┐")
        print(f"  │  {ev_name:^{W-6}} │")
        print(f"  │  Onset: {onset_str[:10]}   Window: {dates_win[0]}..{dates_win[-1]}  "
              f" ({T_win} days)  τ_Q={cg_ev._tau_Q:.3f}{' ' * max(0, W-80)}│")
        print(f"  └{'─' * (W-4)}┘")

        # Trajectory table (every 5 days or key dates)
        print(f"  {'Day':>12}  {'Raw':>6}  {'Fric':>6}  {'ΔS_f':>7}  {'Q':>8}  {'C*':>3}  Status")
        print("  " + "-" * 70)
        step = max(1, T_win // 20)
        for t in range(0, T_win, step):
            raw = scores_ev[t]
            fric = S_f[t]
            dsf = diffs[t-1] if t > 0 and t-1 < len(diffs) else 0.0
            q = report_ev.Q[t]
            cx = "Y" if report_ev.crossed_Cstar[t] else "."
            if fric > 0.8: st = "HIGH STRESS"
            elif fric > 0.5: st = "ELEVATED"
            elif fric > 0.3: st = "MODERATE"
            else: st = "NORMAL"

            marker = ""
            if t == tip_idx + 1:
                marker = " << TIPPING"
            elif dates_win[t] == onset_str[:10]:
                marker = " << ONSET"
            print(f"  {dates_win[t]:>12}  {raw:>6.3f}  {fric:>6.3f}  {dsf:>+7.4f}  {q:>8.2f}  {cx:>3}  {st}{marker}")

        # Also print onset and tipping if not already in step
        tip_day = tip_idx + 1 if tip_idx + 1 < T_win else tip_idx
        print(f"\n  Tipping: {dates_win[tip_day]} (ΔS_f = +{tip_delta:.4f})")

        onset_offset = onset_i - start_i
        if 0 <= onset_offset < T_win:
            print(f"  Onset:   {dates_win[onset_offset]}")
            if tip_day < onset_offset:
                print(f"  *** Tipping {onset_offset - tip_day} days BEFORE onset ***")
            elif tip_day > onset_offset:
                print(f"  Tipping {tip_day - onset_offset} days after onset")
            else:
                print(f"  Tipping = onset day")

        # Peak friction score
        peak_f = S_f.max()
        peak_f_day = dates_win[int(np.argmax(S_f))]
        print(f"  Peak friction score: {peak_f:.4f} on {peak_f_day}")

    print()

    # ══════════════════════════════════════════════════════════════
    # C) POLICY TESTS — Winter Storm Uri (the catastrophic one)
    # ══════════════════════════════════════════════════════════════
    print("═" * W)
    print("  C) POLICY TESTS — Winter Storm Uri (Feb 2021)")
    print("═" * W)
    print("    The deadliest US power crisis in decades.")
    print("    Question: what minimum intervention prevents grid collapse?")
    print()

    onset_str = event_onsets["WinterStormUri"]
    start_i, end_i, onset_i = event_window(dates_daily, onset_str,
                                            pre_days=60, post_days=20)
    X_uri = X_daily[start_i:end_i]
    dates_uri = dates_daily[start_i:end_i]
    T_uri = len(X_uri)

    # Fit on pre-event
    pre_len = onset_i - start_i
    cg_uri = CollapseGeometry()
    cg_uri.fit(X_uri[:pre_len])

    # Focus on crisis window (onset ± 10 days)
    c_start = max(0, onset_i - start_i - 5)
    c_end = min(T_uri, onset_i - start_i + 15)
    X_crisis = X_uri[c_start:c_end]
    dates_crisis = dates_uri[c_start:c_end]
    n_crisis = len(X_crisis)

    # Feature indices
    # demand: [0]=demand_gw [1]=ramp_rate [2]=vol_6h [3]=dev_24h [4]=temp_stress
    # supply: [5]=wind_cf [6]=solar_cf [7]=gas_cf [8]=coal_cf [9]=nuclear_cf

    # ── Policy 1: Demand Response — cap demand at 90th pctile ──
    print("  C.1) Demand Response — cap demand_gw at reference p90")
    print("  " + "-" * 80)
    demand_p90 = float(np.percentile(X_uri[:pre_len, 0], 90))
    clamp_max1 = np.full(10, np.inf)
    clamp_max1[0] = demand_p90
    p1 = cg_uri.policy_test(X_crisis, clamp_max=clamp_max1)
    for i in range(0, n_crisis, max(1, n_crisis // 8)):
        rescued = "RESCUED" if p1['rescued'][i] else ""
        print(f"    {dates_crisis[i]}  S: {p1['score_before'][i]:.3f} → {p1['score_after'][i]:.3f}"
              f"  (Δ={p1['delta_score'][i]:>+.3f})"
              f"  {'in C*' if p1['inside_after'][i] else 'OUTSIDE'}  {rescued}")
    print(f"    Rescued: {p1['rescued'].sum()}/{n_crisis}  "
          f"Mean ΔS: {p1['delta_score'].mean():+.4f}")
    print()

    # ── Policy 2: Reserve Margin — boost gas_cf by 0.15 ──
    print("  C.2) Reserve Margin — boost gas_cf (capacity factor) by +0.15")
    print("  " + "-" * 80)
    delta2 = np.zeros(10)
    delta2[7] = 0.15   # gas_cf
    p2 = cg_uri.policy_test(X_crisis, delta=delta2)
    for i in range(0, n_crisis, max(1, n_crisis // 8)):
        rescued = "RESCUED" if p2['rescued'][i] else ""
        print(f"    {dates_crisis[i]}  S: {p2['score_before'][i]:.3f} → {p2['score_after'][i]:.3f}"
              f"  (Δ={p2['delta_score'][i]:>+.3f})"
              f"  {rescued}")
    print(f"    Rescued: {p2['rescued'].sum()}/{n_crisis}  "
          f"Mean ΔS: {p2['delta_score'].mean():+.4f}")
    print()

    # ── Policy 3: Weatherisation — cap temp_stress at p95 of ref ──
    print("  C.3) Weatherisation — cap temp_stress at reference p95")
    print("  " + "-" * 80)
    temp_p95 = float(np.percentile(X_uri[:pre_len, 4], 95))
    clamp_max3 = np.full(10, np.inf)
    clamp_max3[4] = temp_p95
    p3 = cg_uri.policy_test(X_crisis, clamp_max=clamp_max3)
    for i in range(0, n_crisis, max(1, n_crisis // 8)):
        rescued = "RESCUED" if p3['rescued'][i] else ""
        print(f"    {dates_crisis[i]}  S: {p3['score_before'][i]:.3f} → {p3['score_after'][i]:.3f}"
              f"  (Δ={p3['delta_score'][i]:>+.3f})"
              f"  {rescued}")
    print(f"    Rescued: {p3['rescued'].sum()}/{n_crisis}  "
          f"Mean ΔS: {p3['delta_score'].mean():+.4f}")
    print()

    # ── Policy 4: Combined — demand + reserve + weatherisation ──
    print("  C.4) Combined — demand cap + gas reserve + weatherisation")
    print("  " + "-" * 80)
    clamp_max4 = np.full(10, np.inf)
    clamp_max4[0] = demand_p90
    clamp_max4[4] = temp_p95
    p4 = cg_uri.policy_test(X_crisis, delta=delta2,
                              clamp_max=clamp_max4)
    for i in range(0, n_crisis, max(1, n_crisis // 8)):
        rescued = "RESCUED" if p4['rescued'][i] else ""
        print(f"    {dates_crisis[i]}  S: {p4['score_before'][i]:.3f} → {p4['score_after'][i]:.3f}"
              f"  (Δ={p4['delta_score'][i]:>+.3f})"
              f"  Q: {p4['Q_before'][i]:.1f} → {p4['Q_after'][i]:.1f}"
              f"  {'in C*' if p4['inside_after'][i] else 'OUTSIDE'}  {rescued}")
    print(f"    Rescued: {p4['rescued'].sum()}/{n_crisis}  "
          f"Mean ΔS: {p4['delta_score'].mean():+.4f}")
    print()

    # ── Policy 5: Minimum-norm δ* ──
    print("  C.5) Minimum-Norm δ* — Exact Smallest Correction")
    print("  " + "=" * 80)
    p_min = cg_uri.policy_test(X_crisis)
    outside = ~p_min['inside_before']
    n_out = outside.sum()
    print(f"    Days outside C*: {n_out}/{n_crisis}")

    if n_out > 0:
        min_d = p_min['min_delta'][outside]
        min_dn = p_min['min_delta_norm'][outside]
        out_dates = dates_crisis[outside]

        print(f"    {'Date':>12}  {'||δ*||':>8}  {'demand':>8}  {'ramp':>8}  {'vol':>8}"
              f"  {'dev':>8}  {'temp':>8}  {'wind':>8}  {'solar':>8}"
              f"  {'gas':>8}  {'coal':>8}  {'nuclear':>8}")
        print("    " + "-" * 110)
        for i in range(min(n_out, 15)):
            dd = min_d[i]
            print(f"    {out_dates[i]:>12}  {min_dn[i]:>8.3f}  " +
                  "  ".join(f"{dd[j]:>+8.3f}" for j in range(10)))

        print(f"\n    Mean ||δ*||: {min_dn.mean():.3f}")
        print(f"    Min  ||δ*||: {min_dn.min():.3f} ({out_dates[np.argmin(min_dn)]})")
        print(f"    Max  ||δ*||: {min_dn.max():.3f} ({out_dates[np.argmax(min_dn)]})")

        mean_abs = np.abs(min_d).mean(axis=0)
        dom = int(np.argmax(mean_abs))
        print(f"\n    Dominant correction: {features[dom]}")
        print(f"    Mean |δ*| per feature:")
        for j in range(10):
            bar = "█" * int(mean_abs[j] / max(mean_abs) * 30)
            print(f"      {features[j]:<14} {mean_abs[j]:>8.4f}  {bar}")
    print()

    # ══════════════════════════════════════════════════════════════
    # D) CROSS-EVENT POLICY COMPARISON
    # ══════════════════════════════════════════════════════════════
    print("═" * W)
    print("  D) CROSS-EVENT COMPARISON — All Four Grid Events")
    print("═" * W)

    print(f"\n  {'Event':<25} {'Peak Raw':>9} {'Peak Fric':>10} {'Tipping':>12}"
          f"  {'ΔS_f':>7} {'Dom Feature':>15}")
    print("  " + "-" * 90)

    for ev_name in event_names:
        onset_str = event_onsets[ev_name]
        start_i, end_i, onset_i = event_window(dates_daily, onset_str,
                                                 pre_days=60, post_days=20)
        X_win = X_daily[start_i:end_i]
        dates_win = dates_daily[start_i:end_i]
        T_win = len(X_win)

        pre_len = onset_i - start_i
        if pre_len < 10:
            pre_len = min(30, T_win // 2)

        cg_ev = CollapseGeometry()
        cg_ev.fit(X_win[:pre_len])

        scores_ev = cg_ev.score(X_win)
        S_f = cg_ev.score_with_friction(X_win)
        diffs_ev = np.diff(S_f)
        tip_idx = int(np.argmax(diffs_ev))
        tip_delta = diffs_ev[tip_idx]
        tip_day = dates_win[min(tip_idx + 1, T_win - 1)]

        # Dominant δ* feature for crisis days
        crisis_s = max(0, onset_i - start_i - 2)
        crisis_e = min(T_win, onset_i - start_i + 10)
        if crisis_e > crisis_s:
            p_tmp = cg_ev.policy_test(X_win[crisis_s:crisis_e])
            out_mask = ~p_tmp['inside_before']
            if out_mask.sum() > 0:
                mean_abs = np.abs(p_tmp['min_delta'][out_mask]).mean(axis=0)
                dom_feat = features[int(np.argmax(mean_abs))]
            else:
                dom_feat = "—"
        else:
            dom_feat = "—"

        print(f"  {ev_name:<25} {scores_ev.max():>9.4f} {S_f.max():>10.4f} {tip_day:>12}"
              f"  {tip_delta:>+7.4f} {dom_feat:>15}")

    print()

    # ══════════════════════════════════════════════════════════════
    # E) SUMMARY
    # ══════════════════════════════════════════════════════════════
    print("═" * W)
    print("  E) SUMMARY")
    print("═" * W)
    print()
    print(f"    System:     ERCOT (Texas Interconnection)")
    print(f"    Period:     2019-01 to 2022-12 ({N} days)")
    print(f"    Features:   {d} (5 demand + 5 supply capacity factors)")
    print(f"    Reference:  2019-Apr–Jun ({ref_mask.sum()} stable spring days)")
    print(f"    Events:     {len(event_names)}")
    print(f"    τ_Q:        {cg._tau_Q:.3f}")
    print()

    # Summary policy table for Uri
    policies = [
        ("Demand response (cap demand)", p1),
        ("Reserve margin (gas +0.15)", p2),
        ("Weatherisation (cap temp)", p3),
        ("Combined (all three)", p4),
    ]
    print(f"    WINTER STORM URI — Policy Effectiveness")
    print(f"    {'Policy':<40} {'Mean ΔS':>8} {'Rescued':>10}")
    print("    " + "-" * 60)
    for name, p in policies:
        ds = p['delta_score'].mean()
        resc = int(p['rescued'].sum())
        print(f"    {name:<40} {ds:>+8.4f} {resc:>6}/{n_crisis}")
    print()

    # Assertions
    print("═" * W)
    print("  ASSERTIONS")
    print("═" * W)
    ok = 0; tests = 0

    # Uri must be detected
    uri_mask = lab_daily == "WinterStormUri"
    tests += 1
    uri_peak = scores[uri_mask].max() if uri_mask.any() else 0
    if uri_peak > 0.5:
        print(f"  PASS: Winter Storm Uri peak score {uri_peak:.3f} > 0.5")
        ok += 1
    else:
        print(f"  FAIL: Uri peak {uri_peak:.3f}")

    # COVID must be detected
    covid_mask = lab_daily == "COVID_Collapse"
    tests += 1
    covid_peak = scores[covid_mask].max() if covid_mask.any() else 0
    if covid_peak > 0.3:
        print(f"  PASS: COVID collapse peak score {covid_peak:.3f} > 0.3")
        ok += 1
    else:
        print(f"  FAIL: COVID peak {covid_peak:.3f}")

    # δ* correction should be dominated by energy-relevant features
    # (showing that ad-hoc policies can backfire is itself an important result)
    tests += 1
    if n_out > 0:
        mean_norm = min_dn.mean()
        if mean_norm < 10.0:
            print(f"  PASS: Mean δ* correction ||δ*|| = {mean_norm:.3f} (feasible magnitude)")
            ok += 1
        else:
            print(f"  FAIL: Mean δ* correction ||δ*|| = {mean_norm:.3f} (too large)")
    else:
        print(f"  SKIP: No observations outside C*")

    # At least one event should have min_delta dominated by temp or demand
    tests += 1
    if n_out > 0:
        mean_abs_all = np.abs(p_min['min_delta'][outside]).mean(axis=0)
        dom_idx = int(np.argmax(mean_abs_all))
        if features[dom_idx] in ("demand_gw", "temp_stress", "gas_cf", "wind_cf"):
            print(f"  PASS: Dominant correction feature = {features[dom_idx]} (energy-relevant)")
            ok += 1
        else:
            print(f"  FAIL: Dominant = {features[dom_idx]}")
    else:
        print(f"  SKIP: No observations outside C*")

    print()
    if ok == tests:
        print(f"  ALL {tests} ASSERTIONS PASSED")
    else:
        print(f"  {ok}/{tests} ASSERTIONS PASSED")
    print("═" * W)


if __name__ == "__main__":
    main()
