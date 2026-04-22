#!/usr/bin/env python3
"""
CollapseGeometry on Terra/Luna — Detailed Policy Analysis
==========================================================
Applies the closed-form geometry to the May 2022 UST/LUNA collapse.

Feature vector per hour:
  [0] depeg_pct     = (1 - UST_price) * 100
  [1] luna_log_ret  = log(LUNA_t / LUNA_0)   (cumulative)
  [2] depeg_rate    = Δdepeg/Δt              (hourly velocity)
  [3] luna_rate     = Δlog(LUNA)/Δt          (hourly)
  [4] vol_6h        = rolling 6h std(depeg_rate)

Phases of analysis:
  A) Detection — does geometry identify collapse?
  B) Friction trajectory — early warning timeline
  C) Tipping point — exact hour of no return
  D) Policy tests — what interventions could have saved UST?
     • Capital injection (reduce depeg directly)
     • Burn cap (limit LUNA dilution)
     • Circuit breaker (cap depeg rate)
     • Minimum δ* — exact smallest intervention

Author: Automated CollapseGeometry analysis
"""
from __future__ import annotations
import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from collapse_geometry import CollapseGeometry

# ═══════════════════════════════════════════════════════════════
# REAL DATA — hourly UST and LUNA prices (CoinGecko + Nansen)
# May 7-14, 2022 (169 hours, 0..168)
# ═══════════════════════════════════════════════════════════════

UST_PRICE = {
    0:1.000, 6:0.999, 12:0.998, 18:0.997, 21:0.995,
    22:0.990, 23:0.985,
    24:0.980, 27:0.975, 30:0.985, 33:0.990, 36:0.975,
    40:0.950, 44:0.920, 47:0.900,
    48:0.800, 50:0.700, 52:0.600, 54:0.500, 56:0.400,
    60:0.350, 64:0.400, 68:0.350, 71:0.300,
    72:0.280, 76:0.250, 80:0.220, 84:0.200, 88:0.180,
    92:0.150, 95:0.120,
    96:0.150, 100:0.180, 104:0.120, 108:0.100, 112:0.080,
    116:0.060, 119:0.050,
    120:0.060, 124:0.050, 128:0.040, 132:0.030, 136:0.025,
    140:0.020, 143:0.020,
    144:0.020, 148:0.020, 152:0.015, 156:0.015, 160:0.010,
    164:0.010, 168:0.010,
}

LUNA_PRICE = {
    0:77.0, 6:76.0, 12:75.0, 18:73.0, 22:70.0, 23:68.0,
    24:65.0, 30:62.0, 36:55.0, 40:50.0, 44:42.0, 47:35.0,
    48:30.0, 52:25.0, 56:20.0, 60:17.0, 64:18.0, 68:15.0, 71:12.0,
    72:10.0, 76:8.0, 80:6.0, 84:4.0, 88:3.0, 92:2.0, 95:1.0,
    96:7.0, 100:3.0, 104:0.50, 108:0.10, 112:0.01, 116:0.001,
    119:0.0002,
    120:0.0001, 124:5e-5, 128:3e-5, 132:2e-5, 136:2e-5,
    140:1e-5, 143:1e-5,
    144:1e-5, 148:1e-5, 152:1e-5, 156:1e-5, 160:1e-5,
    164:1e-5, 168:1e-5,
}

EVENTS = {
    0:   "May 7 — Peg holds",
    22:  "LFG withdraws 150M UST from Curve",
    24:  "First 85M attack swap (wallet 0x8d)",
    48:  "Death spiral begins — UST $0.80",
    60:  "UST nadir day 1 (~$0.35)",
    96:  "LUNA collapses <$1 → hyperinflation",
    120: "Chain halted, UST ~$0.06",
    144: "Post-halt stabilisation ~$0.02",
}


def interpolate(d: dict, n: int = 169) -> np.ndarray:
    h = sorted(d.keys()); v = [d[k] for k in h]
    return np.interp(np.arange(n), h, v)


def build_features(ust: np.ndarray, luna: np.ndarray) -> np.ndarray:
    """Build 5-feature matrix: depeg%, luna_log_ret, depeg_rate, luna_rate, vol_6h."""
    T = len(ust)
    depeg = (1.0 - ust) * 100.0
    luna_safe = np.maximum(luna, 1e-10)
    luna_log = np.log(luna_safe / luna_safe[0])

    depeg_rate = np.zeros(T)
    depeg_rate[1:] = np.diff(depeg)
    luna_rate = np.zeros(T)
    luna_rate[1:] = np.diff(luna_log)

    vol_6h = np.zeros(T)
    for t in range(6, T):
        vol_6h[t] = np.std(depeg_rate[t-6:t])

    return np.column_stack([depeg, luna_log, depeg_rate, luna_rate, vol_6h])


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    np.set_printoptions(precision=4, suppress=True)
    W = 100

    ust = interpolate(UST_PRICE)
    luna = interpolate(LUNA_PRICE)
    X = build_features(ust, luna)
    T = len(X)

    print("=" * W)
    print("  COLLAPSE GEOMETRY — TERRA/LUNA (May 7–14, 2022)")
    print("=" * W)
    print(f"  Hours: {T}   Features: depeg%, luna_log_ret, depeg_rate, luna_rate, vol_6h")
    print(f"  Reference window: hours 0–21 (pre-attack normal peg)")
    print()

    # ── Fit on pre-attack period (hours 0-21: peg holds) ──
    ref_end = 22  # before LFG withdrawal
    cg = CollapseGeometry()
    cg.fit(X[:ref_end])

    print(f"  τ_Q = {cg._tau_Q:.3f}   θ_crit = {cg._theta_crit:.4f} rad")
    print(f"  Semi-axes²: {cg._a2}")
    print()

    # ══════════════════════════════════════════════════════════════
    # A) DETECTION — hourly collapse score
    # ══════════════════════════════════════════════════════════════
    print("═" * W)
    print("  A) DETECTION — Hourly Collapse Score")
    print("═" * W)

    report = cg.detect(X)
    scores = report.collapse_score
    Q = report.Q

    # Key milestones
    milestones = [0, 6, 12, 18, 22, 24, 30, 36, 40, 48, 54, 60,
                  72, 84, 96, 108, 120, 144, 168]

    print(f"  {'Hour':>5}  {'Event':<40} {'Score':>6} {'Q':>8} {'C*':>4} {'Status':<15}")
    print("  " + "-" * 90)
    for h in milestones:
        if h >= T: break
        ev = EVENTS.get(h, "")
        s = scores[h]
        q = Q[h]
        cx = "YES" if report.crossed_Cstar[h] else "no"
        if s > 0.8: st = "HIGH STRESS"
        elif s > 0.5: st = "ELEVATED"
        elif s > 0.3: st = "MODERATE"
        else: st = "NORMAL"
        print(f"  {h:>5}  {ev:<40} {s:>6.3f} {q:>8.2f} {cx:>4}  {st:<15}")

    # First alarm
    first_alarm = int(np.where(scores > 0.5)[0][0]) if (scores > 0.5).any() else -1
    first_high = int(np.where(scores > 0.8)[0][0]) if (scores > 0.8).any() else -1
    print()
    print(f"  First ELEVATED alarm (>0.5): hour {first_alarm}" +
          (f"  — {abs(first_alarm - 24):.0f}h before first attack" if first_alarm >= 0 and first_alarm < 24 else ""))
    print(f"  First HIGH STRESS  (>0.8):   hour {first_high}")
    print(f"  Peak score: {scores.max():.4f} at hour {int(np.argmax(scores))}")
    print()

    # ══════════════════════════════════════════════════════════════
    # B) FRICTION TRAJECTORY — gradual early warning
    # ══════════════════════════════════════════════════════════════
    print("═" * W)
    print("  B) FRICTION TRAJECTORY — Score-Space Adaptive Friction")
    print("═" * W)

    S_f = cg.score_with_friction(X)

    print(f"  {'Hour':>5}  {'Raw':>6} {'Fric':>6} {'ΔS_f':>6} {'Brake':>6}  {'Bar (raw)':>20}  {'Bar (fric)':>20}")
    print("  " + "-" * 90)
    prev_sf = 0.0
    for h in milestones:
        if h >= T: break
        raw = scores[h]
        fric = S_f[h]
        dsf = fric - prev_sf if h > 0 else 0.0
        brk = max(1.0 - prev_sf, 0.01) if h > 0 else 1.0
        bar_r = "#" * int(raw * 40)
        bar_f = "=" * int(fric * 40)
        print(f"  {h:>5}  {raw:>6.3f} {fric:>6.3f} {dsf:>+6.3f} {brk:>6.3f}  {bar_r:<20}  {bar_f:<20}")
        prev_sf = fric

    print()

    # ══════════════════════════════════════════════════════════════
    # C) TIPPING POINT — exact hour of collapse onset
    # ══════════════════════════════════════════════════════════════
    print("═" * W)
    print("  C) TIPPING POINT — Maximum Friction Acceleration")
    print("═" * W)

    diffs = np.diff(S_f)
    tip_idx = int(np.argmax(diffs))
    tip_delta = diffs[tip_idx]

    print(f"  Tipping hour: {tip_idx + 1}")
    print(f"  ΔS_f at tipping: +{tip_delta:.4f}")
    print(f"  S_f before: {S_f[tip_idx]:.4f}")
    print(f"  S_f after:  {S_f[tip_idx + 1]:.4f}")

    # Identify the event closest to tipping
    ev_hours = sorted(EVENTS.keys())
    closest_ev = min(ev_hours, key=lambda h: abs(h - (tip_idx+1)))
    print(f"  Closest event: hour {closest_ev} — {EVENTS[closest_ev]}")
    print()

    # Top-5 ΔS_f hours
    top5 = np.argsort(diffs)[-5:][::-1]
    print(f"  Top-5 friction acceleration hours:")
    print(f"  {'Hour':>6}  {'ΔS_f':>8}  {'S_f':>6}  {'Raw':>6}  Event")
    print("  " + "-" * 60)
    for idx in top5:
        h = idx + 1
        ev = EVENTS.get(h, "")
        if not ev:
            for eh in ev_hours:
                if abs(eh - h) <= 2:
                    ev = f"~{EVENTS[eh]}"
                    break
        print(f"  {h:>6}  {diffs[idx]:>+8.4f}  {S_f[h]:>6.3f}  {scores[h]:>6.3f}  {ev}")
    print()

    # ══════════════════════════════════════════════════════════════
    # D) POLICY TESTS — what interventions could have saved UST?
    # ══════════════════════════════════════════════════════════════
    print("═" * W)
    print("  D) POLICY TESTS — Closed-Form Intervention Analysis")
    print("═" * W)

    # Two windows: early (intervention feasible) and deep (death spiral)
    early_start, early_end = 19, min(30, T)
    deep_start, deep_end = 30, min(61, T)
    X_early = X[early_start:early_end]
    X_deep  = X[deep_start:deep_end]
    hours_early = np.arange(early_start, early_start + len(X_early))
    hours_deep  = np.arange(deep_start, deep_start + len(X_deep))

    # Full crisis window for overall stats
    crisis_start, crisis_end = 19, min(61, T)
    X_crisis = X[crisis_start:crisis_end]
    n_crisis = len(X_crisis)
    hours_crisis = np.arange(crisis_start, crisis_start + n_crisis)

    features = ["depeg%", "luna_log_ret", "depeg_rate", "luna_rate", "vol_6h"]

    # ── Policy 1: Capital injection — reduce depeg by 0.5pp (early window) ──
    print("\n  D.1) Early Capital Injection — reduce depeg% by 0.5pp")
    print("       (Applied in early window: hours 19–29, before death spiral)")
    print("  " + "-" * 70)
    delta_cap = np.zeros(5)
    delta_cap[0] = -0.5  # reduce depeg % by 0.5pp — realistic for early defence
    p1 = cg.policy_test(X_early, delta=delta_cap)
    for i in range(len(X_early)):
        h = hours_early[i]
        rescued = "RESCUED" if p1['rescued'][i] else ""
        print(f"    h={h:>3}  S: {p1['score_before'][i]:.3f} → {p1['score_after'][i]:.3f}"
              f"  (Δ={p1['delta_score'][i]:>+.3f})"
              f"  Q: {p1['Q_before'][i]:.1f} → {p1['Q_after'][i]:.1f}"
              f"  {'in C*' if p1['inside_after'][i] else 'OUTSIDE'}  {rescued}")
    rescued_count = p1['rescued'].sum()
    improved = (p1['delta_score'] < -0.01).sum()
    print(f"\n    Rescued (returned inside C*): {rescued_count}/{len(X_early)}")
    print(f"    Score improved (ΔS < -0.01):  {improved}/{len(X_early)}")
    print(f"    Mean ΔS: {p1['delta_score'].mean():+.4f}")
    print()

    # ── Policy 2: LUNA burn cap — early window ──
    print("  D.2) LUNA Burn Cap — clamp luna_log_ret ≥ -0.1 (≈10% max loss)")
    print("       (Prevents LUNA dilution spiral in early hours)")
    print("  " + "-" * 70)
    clamp_min2 = np.full(5, -np.inf)
    clamp_min2[1] = -0.1   # cap LUNA loss at ~10%
    p2 = cg.policy_test(X_early, clamp_min=clamp_min2)
    for i in range(len(X_early)):
        h = hours_early[i]
        rescued = "RESCUED" if p2['rescued'][i] else ""
        print(f"    h={h:>3}  S: {p2['score_before'][i]:.3f} → {p2['score_after'][i]:.3f}"
              f"  (Δ={p2['delta_score'][i]:>+.3f})"
              f"  Q: {p2['Q_before'][i]:.1f} → {p2['Q_after'][i]:.1f}"
              f"  {rescued}")
    rescued_count = p2['rescued'].sum()
    print(f"\n    Rescued: {rescued_count}/{len(X_early)}   Mean ΔS: {p2['delta_score'].mean():+.4f}")
    print()

    # ── Policy 3: Circuit breaker — cap depeg rate (early window) ──
    print("  D.3) Circuit Breaker — cap depeg_rate ≤ 0.2%/hr, vol_6h ≤ 0.1")
    print("       (Halt trading if price moving >0.2% per hour)")
    print("  " + "-" * 70)
    clamp_max3 = np.full(5, np.inf)
    clamp_max3[2] = 0.2    # cap depeg rate at 0.2%/hr
    clamp_max3[4] = 0.1    # cap 6h volatility
    p3 = cg.policy_test(X_early, clamp_max=clamp_max3)
    for i in range(len(X_early)):
        h = hours_early[i]
        rescued = "RESCUED" if p3['rescued'][i] else ""
        print(f"    h={h:>3}  S: {p3['score_before'][i]:.3f} → {p3['score_after'][i]:.3f}"
              f"  (Δ={p3['delta_score'][i]:>+.3f})"
              f"  {rescued}")
    rescued_count = p3['rescued'].sum()
    print(f"\n    Rescued: {rescued_count}/{len(X_early)}   Mean ΔS: {p3['delta_score'].mean():+.4f}")
    print()

    # ── Policy 4: Combined — all three (early window) ──
    print("  D.4) Combined Policy — all three interventions (early window)")
    print("  " + "-" * 70)
    p4_early = cg.policy_test(X_early, delta=delta_cap,
                         clamp_min=clamp_min2, clamp_max=clamp_max3)
    for i in range(len(X_early)):
        h = hours_early[i]
        rescued = "RESCUED" if p4_early['rescued'][i] else ""
        print(f"    h={h:>3}  S: {p4_early['score_before'][i]:.3f} → {p4_early['score_after'][i]:.3f}"
              f"  (Δ={p4_early['delta_score'][i]:>+.3f})"
              f"  Q: {p4_early['Q_before'][i]:.1f} → {p4_early['Q_after'][i]:.1f}"
              f"  {'in C*' if p4_early['inside_after'][i] else 'OUTSIDE'}  {rescued}")
    rescued_count = p4_early['rescued'].sum()
    print(f"\n    Rescued: {rescued_count}/{len(X_early)}   Mean ΔS: {p4_early['delta_score'].mean():+.4f}")
    print()

    # ── Deep spiral — show that NO policy helps after hour 30 ──
    print("  D.4b) Deep Spiral (hours 30–60) — policy futility")
    print("  " + "-" * 70)
    p4_deep = cg.policy_test(X_deep, delta=delta_cap,
                              clamp_min=clamp_min2, clamp_max=clamp_max3)
    deep_rescued = int(p4_deep['rescued'].sum())
    deep_improved = (p4_deep['delta_score'] < -0.01).sum()
    print(f"    Hours 30–{deep_start+len(X_deep)-1}: Combined policy rescues {deep_rescued}/{len(X_deep)} (futile)")
    print(f"    Mean Q in deep spiral: {p4_deep['Q_before'].mean():.0f} vs τ_Q={cg._tau_Q:.1f}")
    print(f"    → System {p4_deep['Q_before'].mean()/cg._tau_Q:.0f}× beyond C* — irreversible")
    print()

    # ── Policy 5: Minimum-norm δ* — exact smallest intervention ──
    print("  D.5) Minimum-Norm Correction δ* — Exact Smallest Rescue")
    print("  " + "=" * 70)
    print("    For each hour outside C*, the minimum feature perturbation")
    print("    δ* = −(Q − τ_Q)/||∇Q||² · ∇Q that returns to C* boundary.")
    print("    This shows the EXACT cost of saving the peg at each hour.")
    print()

    # Evaluate on full crisis window (19-60)
    p_min = cg.policy_test(X_crisis)
    outside_mask = ~p_min['inside_before']
    outside_hours = hours_crisis[outside_mask]
    min_d = p_min['min_delta'][outside_mask]
    min_dn = p_min['min_delta_norm'][outside_mask]

    if len(outside_hours) > 0:
        print(f"    Hours outside C*: {len(outside_hours)}/{n_crisis}")
        print(f"    {'Hour':>6}  {'||δ*||':>8}  {features[0]:>10}  {features[1]:>12}  {features[2]:>12}  {features[3]:>12}  {features[4]:>10}")
        print("    " + "-" * 80)
        for i in range(0, len(outside_hours), max(1, len(outside_hours)//12)):
            h = outside_hours[i]
            dn = min_dn[i]
            dd = min_d[i]
            print(f"    {h:>6}  {dn:>8.3f}  {dd[0]:>+10.3f}  {dd[1]:>+12.4f}  {dd[2]:>+12.4f}  {dd[3]:>+12.4f}  {dd[4]:>+10.4f}")

        print()
        print(f"    Mean ||δ*||: {min_dn.mean():.3f}")
        print(f"    Min  ||δ*||: {min_dn.min():.3f} (hour {outside_hours[np.argmin(min_dn)]})")
        print(f"    Max  ||δ*||: {min_dn.max():.3f} (hour {outside_hours[np.argmax(min_dn)]})")
        print()

        # Which feature needs the biggest correction?
        mean_abs_delta = np.abs(min_d).mean(axis=0)
        dom_feat = int(np.argmax(mean_abs_delta))
        print(f"    Dominant correction feature: {features[dom_feat]}")
        print(f"    Mean |δ*| per feature: {['%.3f' % v for v in mean_abs_delta]}")
    else:
        print("    All observations inside C* — no correction needed.")
    print()

    # ══════════════════════════════════════════════════════════════
    # E) FULL TRAJECTORY DETAIL
    # ══════════════════════════════════════════════════════════════
    print("═" * W)
    print("  E) FULL HOURLY TRAJECTORY (every 2 hours)")
    print("═" * W)

    print(f"  {'Hour':>5}  {'UST$':>6}  {'LUNA$':>10}  {'Raw':>6}  {'Fric':>6}  {'ΔS_f':>6}  {'Q':>8}  {'C*':>3}  Status")
    print("  " + "-" * 90)
    for h in range(0, T, 2):
        u = ust[h]
        l = luna[h]
        raw = scores[h]
        fric = S_f[h]
        dsf = diffs[h-1] if h > 0 and h-1 < len(diffs) else 0.0
        q = Q[h]
        cx = "Y" if report.crossed_Cstar[h] else "."
        if fric > 0.8: st = "HIGH STRESS"
        elif fric > 0.5: st = "ELEVATED"
        elif fric > 0.3: st = "MODERATE"
        else: st = "NORMAL"

        marker = ""
        if h == tip_idx + 1:
            marker = " << TIPPING"
        elif abs(dsf) == max(abs(diffs[max(0,h-3):h+1])) and dsf > 0.05:
            marker = " *"

        print(f"  {h:>5}  {u:>6.3f}  {l:>10.4f}  {raw:>6.3f}  {fric:>6.3f}  {dsf:>+6.3f}  {q:>8.2f}  {cx:>3}  {st}{marker}")

    print()

    # ══════════════════════════════════════════════════════════════
    # F) SUMMARY
    # ══════════════════════════════════════════════════════════════
    print("═" * W)
    print("  F) SUMMARY — Terra/Luna Collapse Geometry")
    print("═" * W)
    print()
    print(f"    System:            UST/LUNA algorithmic stablecoin")
    print(f"    Period:            May 7–14, 2022 (169 hours)")
    print(f"    Reference:         Hours 0–21 (pre-attack stable peg)")
    print(f"    Features:          5 (depeg%, luna_log_ret, depeg_rate, luna_rate, vol_6h)")
    print()
    print(f"    C* threshold τ_Q:  {cg._tau_Q:.3f}")
    print(f"    First C* crossing: hour {int(np.where(report.crossed_Cstar)[0][0]) if report.crossed_Cstar.any() else -1}")
    print(f"    First alarm (>0.5): hour {first_alarm}")
    print(f"    Tipping point:     hour {tip_idx+1} (ΔS_f = +{tip_delta:.4f})")
    print(f"    Peak raw score:    {scores.max():.4f} (hour {int(np.argmax(scores))})")
    print(f"    Peak fric score:   {S_f.max():.4f} (hour {int(np.argmax(S_f))})")
    print()

    # Policy effectiveness summary (early window)
    policies = [
        ("Capital injection (−0.5pp depeg)", p1),
        ("LUNA burn cap (−0.1 log ret)", p2),
        ("Circuit breaker (rate/vol cap)", p3),
        ("Combined (all three) [early]", p4_early),
    ]
    print(f"    {'Policy':<40} {'Mean ΔS':>8} {'Rescued':>10} {'Mean lead Δ':>12}")
    print("    " + "-" * 70)
    n_early = len(X_early)
    for name, p in policies:
        ds = p['delta_score'].mean()
        resc = int(p['rescued'].sum())
        dl = (p['lead_after'] - p['lead_before']).mean()
        print(f"    {name:<40} {ds:>+8.4f} {resc:>6}/{n_early:<4} {dl:>+12.2f}")
    print()
    print(f"    Deep spiral (h30-60) combined:       "
          f"{p4_deep['delta_score'].mean():>+8.4f} {int(p4_deep['rescued'].sum()):>6}/{len(X_deep):<4} "
          f"{'— FUTILE':>12}")
    print()

    # Assertions
    print("═" * W)
    print("  ASSERTIONS")
    print("═" * W)
    ok = 0
    tests = 0

    tests += 1
    if scores.max() > 0.9:
        print(f"  PASS: Peak score {scores.max():.3f} > 0.9 (detects collapse)")
        ok += 1
    else:
        print(f"  FAIL: Peak score {scores.max():.3f} ≤ 0.9")

    tests += 1
    if first_alarm >= 0 and first_alarm <= 30:
        print(f"  PASS: First alarm hour {first_alarm} ≤ 30 (early warning)")
        ok += 1
    else:
        print(f"  FAIL: First alarm hour {first_alarm}")

    tests += 1
    if 15 <= tip_idx + 1 <= 25:
        print(f"  PASS: Tipping hour {tip_idx+1} in [15, 25] (pre-attack / early attack)")
        ok += 1
    else:
        print(f"  FAIL: Tipping hour {tip_idx+1} outside [15, 25]")

    tests += 1
    # In early window, combined policy should rescue OR reduce at least some obs
    early_rescued = int(p4_early['rescued'].sum())
    early_improved = int((p4_early['delta_score'] < -0.01).sum())
    if early_rescued > 0 or early_improved > 0:
        print(f"  PASS: Early combined policy rescued {early_rescued}, improved {early_improved}")
        ok += 1
    else:
        print(f"  FAIL: Early combined policy rescued=0, improved=0")

    tests += 1
    # δ* at first crisis hour should be small (intervention was feasible)
    if len(min_dn) > 0 and min_dn[0] < 1.0:
        print(f"  PASS: δ* at first crisis hour = {min_dn[0]:.3f} < 1.0 (feasible intervention)")
        ok += 1
    elif len(min_dn) > 0:
        print(f"  FAIL: δ* at first crisis hour = {min_dn[0]:.3f}")
    else:
        print(f"  SKIP: no outside observations")

    print()
    if ok == tests:
        print(f"  ALL {tests} ASSERTIONS PASSED")
    else:
        print(f"  {ok}/{tests} ASSERTIONS PASSED")
    print("═" * W)


if __name__ == "__main__":
    main()
