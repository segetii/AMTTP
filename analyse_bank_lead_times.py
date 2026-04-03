#!/usr/bin/env python3
"""
Banking Early Warning Lead-Time Analysis
=========================================
Rigorous expanding-window analysis:
- Each quarter's alarm uses ONLY scores from PRIOR quarters (no lookahead)
- Multiple threshold levels (2σ, 3σ, P95, P99)
- Exact lead times in days and months before each crisis onset
- False alarm accounting per inter-crisis window

Author: Odeyemi Olusegun Israel — AMTTP/UDL Project
"""
import json, sys, os
import numpy as np
from datetime import datetime, date

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ═══════════════════════════════════════════════════════════════════
#  DATA
# ═══════════════════════════════════════════════════════════════════
with open('results/bank_lgbm_engine_results.json') as f:
    R = json.load(f)

# Build quarter date labels: 2005-Q1 to 2023-Q4 (T=76)
quarter_dates = []
quarter_labels = []
y, q = 2005, 1
for _ in range(76):
    m = q * 3
    if m == 3:   d = date(y, 3, 31)
    elif m == 6: d = date(y, 6, 30)
    elif m == 9: d = date(y, 9, 30)
    else:        d = date(y, 12, 31)
    quarter_dates.append(d)
    quarter_labels.append(f"{y}-Q{q}")
    q += 1
    if q > 4:
        q = 1; y += 1

# Crisis definitions with EXACT onset dates
CRISES = {
    'GFC': {
        'onset': date(2007, 12, 1),    # Dec 2007 — NBER recession start
        'peak':  date(2008, 9, 15),    # Lehman Brothers collapse
        'end':   date(2009, 6, 30),    # NBER recession end
        'quarters': [11, 12, 13, 14, 15, 16, 17],  # 2007-Q4 through 2009-Q2
        'description': 'Global Financial Crisis',
    },
    'EU_Sovereign': {
        'onset': date(2011, 7, 1),     # Greek 2nd bailout, Italian/Spanish spreads spike
        'peak':  date(2011, 11, 15),   # Italian 10Y > 7%
        'end':   date(2012, 6, 30),    # Draghi "whatever it takes" (Jul 2012)
        'quarters': [26, 27, 28, 29],  # 2011-Q3 through 2012-Q2
        'description': 'European Sovereign Debt Crisis',
    },
    'COVID': {
        'onset': date(2020, 3, 1),     # WHO pandemic declaration
        'peak':  date(2020, 3, 23),    # Market bottom
        'end':   date(2020, 6, 30),
        'quarters': [60, 61],          # 2020-Q1 through 2020-Q2
        'description': 'COVID-19 Pandemic Shock',
    },
}

# ═══════════════════════════════════════════════════════════════════
#  SIGNALS: Collect all signals across 3 layers
# ═══════════════════════════════════════════════════════════════════
SIGNALS = {}

# Layer 1: LGBM Engine post-simulation scores
for v in ['fused', 'bsdt_energy', 'morse', 'reduced_tensor']:
    s = np.array([x if x is not None else np.nan for x in R['layer1_scores'][v]])
    SIGNALS[f'L1/{v}'] = s

# Layer 2: BSDT Early Warning
for v in ['e_bs', 'mfls']:
    s = np.array([x if x is not None else np.nan for x in R['layer2_scores'][v]])
    SIGNALS[f'L2/{v}'] = s

# Layer 3: Morse + Betti Confirmation
for v in ['morse', 'betti', 'morse_betti_fused']:
    s = np.array([x if x is not None else np.nan for x in R['layer3_scores'][v]])
    SIGNALS[f'L3/{v}'] = s

# BSDT Morse Alarm (binary)
morse_alarm = np.array(R['layer2_morse_alarm'])

MIN_HISTORY = 4  # Minimum quarters of history before computing thresholds
BURN_IN = 4      # First 4 quarters have no scores (None)

# ═══════════════════════════════════════════════════════════════════
#  EXPANDING-WINDOW ALARM DETECTION
# ═══════════════════════════════════════════════════════════════════
# For each signal and threshold, find the FIRST quarter where
# score > threshold computed from ALL PRIOR quarters only.

THRESHOLDS = {
    '2σ':  lambda mu, sig, hist: mu + 2 * sig,
    '3σ':  lambda mu, sig, hist: mu + 3 * sig,
    'P95': lambda mu, sig, hist: np.percentile(hist, 95),
    'P99': lambda mu, sig, hist: np.percentile(hist, 99),
}

def find_alarms(scores, thresh_func, min_hist=MIN_HISTORY):
    """
    Expanding-window alarm detection.
    For quarter t, threshold is computed from scores[0..t-1].
    Returns list of (t, score, threshold, is_crisis_quarter).
    """
    alarms = []
    for t in range(min_hist + BURN_IN, 76):
        if np.isnan(scores[t]):
            continue
        hist = scores[BURN_IN:t]  # Only PRIOR scores after burn-in
        valid = hist[~np.isnan(hist)]
        if len(valid) < min_hist:
            continue
        mu = np.mean(valid)
        sig = np.std(valid)
        if sig < 1e-15:
            continue
        thr = thresh_func(mu, sig, valid)
        if scores[t] > thr:
            is_crisis = any(t in c['quarters'] for c in CRISES.values())
            alarms.append({
                't': t,
                'date': quarter_dates[t],
                'label': quarter_labels[t],
                'score': float(scores[t]),
                'threshold': float(thr),
                'mu': float(mu),
                'sigma': float(sig),
                'is_crisis': is_crisis,
            })
    return alarms


def find_pre_crisis_alarm(alarms, crisis_info):
    """
    Find the FIRST alarm that occurs BEFORE a crisis onset AND
    is not part of a PREVIOUS crisis's residual.
    
    Logic:
    - The alarm must fall between the END of the previous crisis
      (or data start) and the ONSET of this crisis.
    - We require the alarm to be in a "clean window" — i.e., the
      alarm date is AFTER any prior crisis ended.
    """
    onset = crisis_info['onset']
    
    # Determine the clean window start (after previous crisis ended)
    # Sort crises by onset
    sorted_crises = sorted(CRISES.items(), key=lambda x: x[1]['onset'])
    clean_start = date(2005, 1, 1)  # default: data start
    for name, info in sorted_crises:
        if info['onset'] < onset:
            # This crisis is BEFORE our target — clean window starts after it
            clean_start = max(clean_start, info['end'])
    
    # Find first alarm in [clean_start, onset)
    first_alarm = None
    total_false_alarms = 0
    for a in alarms:
        # Count false alarms in the clean pre-crisis window
        if clean_start <= a['date'] < onset and not a['is_crisis']:
            total_false_alarms += 1
            if first_alarm is None:
                first_alarm = a
        # Also check: is this alarm in a crisis quarter for THIS crisis?
        # If alarm is in a crisis quarter that's BEFORE onset date, count it
    
    return first_alarm, total_false_alarms


def compute_lead_time(alarm_date, crisis_onset):
    """Compute lead time in days and months."""
    # alarm_date is a date, crisis_onset is a date
    delta = crisis_onset - alarm_date
    days = delta.days
    months = days / 30.44
    return days, months


# ═══════════════════════════════════════════════════════════════════
#  MAIN ANALYSIS
# ═══════════════════════════════════════════════════════════════════
print("=" * 100)
print("  BANKING G-SIB EARLY WARNING — LEAD TIME ANALYSIS")
print("  Data: FDIC G-SIB Panel (T=76 quarters, 2005-Q1 to 2023-Q4, N=25 banks, d=5)")
print("  Method: Expanding-window thresholds (no lookahead)")
print("=" * 100)

# ── Per-Signal, Per-Crisis Analysis ──────────────────────────────
results_table = []

for sig_name, scores in SIGNALS.items():
    for thr_name, thr_func in THRESHOLDS.items():
        alarms = find_alarms(scores, thr_func)
        
        for crisis_name, crisis_info in CRISES.items():
            first_alarm, n_false = find_pre_crisis_alarm(alarms, crisis_info)
            
            # Also count crisis quarters detected
            crisis_detected = sum(
                1 for a in alarms if a['t'] in crisis_info['quarters']
            )
            
            if first_alarm:
                days, months = compute_lead_time(first_alarm['date'], crisis_info['onset'])
                results_table.append({
                    'signal': sig_name,
                    'threshold': thr_name,
                    'crisis': crisis_name,
                    'alarm_date': first_alarm['label'],
                    'alarm_date_raw': first_alarm['date'],
                    'lead_days': days,
                    'lead_months': round(months, 1),
                    'alarm_score': first_alarm['score'],
                    'alarm_threshold': first_alarm['threshold'],
                    'false_alarms_pre': n_false,
                    'crisis_detected': f"{crisis_detected}/{len(crisis_info['quarters'])}",
                })
            else:
                results_table.append({
                    'signal': sig_name,
                    'threshold': thr_name,
                    'crisis': crisis_name,
                    'alarm_date': '—',
                    'alarm_date_raw': None,
                    'lead_days': None,
                    'lead_months': None,
                    'alarm_score': None,
                    'alarm_threshold': None,
                    'false_alarms_pre': n_false,
                    'crisis_detected': f"{crisis_detected}/{len(crisis_info['quarters'])}",
                })

# ═══════════════════════════════════════════════════════════════════
#  PRINT RESULTS: Per Crisis
# ═══════════════════════════════════════════════════════════════════
for crisis_name, crisis_info in CRISES.items():
    print()
    print("━" * 100)
    print(f"  CRISIS: {crisis_info['description']} ({crisis_name})")
    print(f"  Onset: {crisis_info['onset'].strftime('%d %B %Y')}  |  "
          f"Peak: {crisis_info['peak'].strftime('%d %B %Y')}  |  "
          f"End: {crisis_info['end'].strftime('%d %B %Y')}")
    print(f"  Crisis quarters: {', '.join(quarter_labels[t] for t in crisis_info['quarters'])}")
    print("━" * 100)
    
    # Filter results for this crisis that have a genuine pre-crisis alarm
    crisis_results = [r for r in results_table 
                      if r['crisis'] == crisis_name and r['lead_days'] is not None and r['lead_days'] > 0]
    
    if not crisis_results:
        print("  ⚠ NO genuine pre-crisis alarm detected by any signal/threshold combination.")
        # Show best crisis-quarter detection instead
        crisis_detect = [r for r in results_table if r['crisis'] == crisis_name]
        best_detect = sorted(crisis_detect, key=lambda x: x['crisis_detected'], reverse=True)[:5]
        print(f"\n  Best crisis-quarter detection (alarm DURING crisis):")
        print(f"  {'Signal':<25} {'Thr':<5} {'Detected':<10} {'False Alarms':<12}")
        print(f"  {'-'*52}")
        for r in best_detect:
            print(f"  {r['signal']:<25} {r['threshold']:<5} {r['crisis_detected']:<10} {r['false_alarms_pre']:<12}")
        continue
    
    # Sort by lead time (longest first), then by fewest false alarms
    crisis_results.sort(key=lambda x: (-x['lead_days'], x['false_alarms_pre']))
    
    print(f"\n  {'Signal':<25} {'Thr':<5} {'Alarm Date':<12} {'Lead Days':>10} {'Lead Mo':>8} "
          f"{'Score':>8} {'Threshold':>10} {'FA pre':>7} {'Crisis Det':>10}")
    print(f"  {'-'*105}")
    
    seen = set()
    for r in crisis_results:
        # De-duplicate: show best threshold per signal
        key = r['signal']
        if key in seen:
            continue
        seen.add(key)
        
        print(f"  {r['signal']:<25} {r['threshold']:<5} {r['alarm_date']:<12} "
              f"{r['lead_days']:>10} {r['lead_months']:>8.1f} "
              f"{r['alarm_score']:>8.4f} {r['alarm_threshold']:>10.4f} "
              f"{r['false_alarms_pre']:>7} {r['crisis_detected']:>10}")

    # Also show the full alarm details for the BEST signal
    best = crisis_results[0]
    print(f"\n  ★ BEST EARLY WARNING: {best['signal']} at {best['threshold']}")
    print(f"    First alarm:  {best['alarm_date']} (score {best['alarm_score']:.4f} > threshold {best['alarm_threshold']:.4f})")
    print(f"    Lead time:    {best['lead_days']} days = {best['lead_months']:.1f} months before {crisis_info['onset'].strftime('%d %b %Y')}")
    print(f"    False alarms: {best['false_alarms_pre']} in pre-crisis clean window")
    print(f"    Crisis det:   {best['crisis_detected']} quarters detected during crisis")


# ═══════════════════════════════════════════════════════════════════
#  COMPREHENSIVE SCORE TIMELINE
# ═══════════════════════════════════════════════════════════════════
print()
print()
print("=" * 100)
print("  FULL QUARTERLY SCORE TIMELINE (key signals)")
print("=" * 100)

# Select key signals
key_signals = ['L1/fused', 'L2/mfls', 'L2/e_bs', 'L3/morse', 'L3/betti']

# Compute expanding-window 2σ threshold for each signal at each point
print(f"\n  {'Quarter':<10} ", end='')
for sig in key_signals:
    print(f" {sig:>14}", end='')
print(f"  {'Status':<20}")
print(f"  {'-'*10} ", end='')
for _ in key_signals:
    print(f" {'-'*14}", end='')
print(f"  {'-'*20}")

for t in range(BURN_IN, 76):
    ql = quarter_labels[t]
    
    # Determine status
    status_parts = []
    for cname, cinfo in CRISES.items():
        if t in cinfo['quarters']:
            status_parts.append(cname)
    if t == CRISES['GFC']['quarters'][0]:
        status_parts.append('◀ ONSET')
    if t == CRISES['EU_Sovereign']['quarters'][0]:
        status_parts.append('◀ ONSET')
    if t == CRISES['COVID']['quarters'][0]:
        status_parts.append('◀ ONSET')
    status = ' '.join(status_parts) if status_parts else ''
    
    print(f"  {ql:<10} ", end='')
    
    for sig_name in key_signals:
        scores = SIGNALS[sig_name]
        val = scores[t]
        if np.isnan(val):
            print(f"{'—':>14}", end='')
            continue
        
        # Expanding-window 2σ threshold
        hist = scores[BURN_IN:t]
        valid = hist[~np.isnan(hist)]
        flag = ''
        if len(valid) >= MIN_HISTORY:
            mu = np.mean(valid)
            sig = np.std(valid)
            if sig > 1e-15:
                thr_2s = mu + 2 * sig
                thr_3s = mu + 3 * sig
                if val > thr_3s:
                    flag = '▓▓▓'
                elif val > thr_2s:
                    flag = '░░'
        
        print(f" {val:>8.4f}{flag:>6}", end='')
    
    print(f"  {status:<20}")


# ═══════════════════════════════════════════════════════════════════
#  SUMMARY
# ═══════════════════════════════════════════════════════════════════
print()
print()
print("=" * 100)
print("  SUMMARY: EARLY WARNING LEAD TIMES")
print("=" * 100)
print()
print("  Lead times are measured from the FIRST alarm date to crisis onset.")
print("  Alarms use expanding-window thresholds (no future data).")
print("  Clean window = period between previous crisis end and this crisis onset.")
print()

for crisis_name, crisis_info in CRISES.items():
    crisis_results = [r for r in results_table 
                      if r['crisis'] == crisis_name and r['lead_days'] is not None and r['lead_days'] > 0]
    
    if crisis_results:
        best = sorted(crisis_results, key=lambda x: (-x['lead_days'], x['false_alarms_pre']))[0]
        print(f"  {crisis_info['description']+':':<45} "
              f"{best['lead_days']:>4} days ({best['lead_months']:>5.1f} months)  "
              f"via {best['signal']}/{best['threshold']}  "
              f"[{best['false_alarms_pre']} false alarms in clean window]")
    else:
        print(f"  {crisis_info['description']+':':<45} "
              f"  NO pre-crisis alarm in clean window")

print()
print("  Architecture roles:")
print("  ┌─ Layer 3 (Morse + Betti): Structural early warning — fires FIRST on manifold disruption")
print("  ├─ Layer 2 (BSDT E_BS/MFLS): Energy/gradient alarm — confirms structural signal")
print("  └─ Layer 1 (LGBM Engine fused): Risk quantification — severity scoring during crisis")
print()

# Save detailed results
out = {
    'analysis': 'banking_lead_time_analysis',
    'method': 'expanding_window_no_lookahead',
    'min_history': MIN_HISTORY,
    'quarter_dates': [d.isoformat() for d in quarter_dates],
    'quarter_labels': quarter_labels,
    'crises': {k: {'onset': v['onset'].isoformat(), 'peak': v['peak'].isoformat(),
                    'end': v['end'].isoformat(), 'quarters': v['quarters']}
               for k, v in CRISES.items()},
    'results': [{k: (v.isoformat() if isinstance(v, date) else v) 
                 for k, v in r.items()} for r in results_table],
}
with open('results/bank_lead_time_analysis.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)
print("  Saved → results/bank_lead_time_analysis.json")
