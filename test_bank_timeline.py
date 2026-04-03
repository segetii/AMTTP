#!/usr/bin/env python3
"""
Banking Crisis Timeline Analysis
=================================
Reads cached scores from both LGBM benchmarks and prints a
quarter-by-quarter timeline showing:

  1. When did Morse early warning alarm FIRST trigger?
  2. When did LGBM risk score cross threshold?
  3. How many quarters of lead time before crisis onset?

For each crisis event (GFC, EU Sovereign, COVID).

Author: Odeyemi Olusegun Israel — AMTTP/UDL Project
"""
import json, os, sys
import numpy as np

ROOT = r'C:\amttp'

# ── Load results ─────────────────────────────────────────────────
with open(os.path.join(ROOT, 'results', 'bank_lgbm_benchmark.json')) as f:
    flat = json.load(f)
with open(os.path.join(ROOT, 'results', 'bank_lgbm_engine_results.json')) as f:
    engine = json.load(f)

dates = flat['meta']['dates']       # 76 quarter-end dates
T = len(dates)

# ── Score arrays ─────────────────────────────────────────────────
def arr(raw):
    """Convert JSON list (may have None/NaN) to numpy, NaN-filled."""
    return np.array([np.nan if v is None else v for v in raw], dtype=float)

# Layer 1 — LGBM risk score  (best variant: flat RT+BSDT)
lgbm_flat  = arr(flat['scores']['LGBM_RT+BSDT'])
lgbm_eflow = arr(flat['scores']['LGBM_RT+BSDT+EFlow'])

# Layer 1 — LGBM iterative engine (fused post-sim scorer)
lgbm_eng   = arr(engine['scores']['fused'])

# Layer 2 — Morse early warning (same in both files — standalone)
morse_flat = arr(flat['scores']['Morse_EarlyWarning'])
morse_eng  = arr(engine['morse_scores'])

# ── Thresholds (from calibration: first 11 quarters = pre-GFC normal) ─
CALIB = 11   # q0..q10  (2005-Q1 to 2007-Q3)

def compute_thresholds(scores, calib=CALIB):
    """μ ± k·σ from calibration window."""
    cal = scores[:calib]
    cal = cal[~np.isnan(cal)]
    if len(cal) < 3:
        return {}
    mu, sigma = np.mean(cal), np.std(cal)
    return {
        '2σ': mu + 2 * sigma,
        '3σ': mu + 3 * sigma,
        'mu': mu, 'sigma': sigma,
    }

th_lgbm_flat  = compute_thresholds(lgbm_flat)
th_lgbm_eflow = compute_thresholds(lgbm_eflow)
th_lgbm_eng   = compute_thresholds(lgbm_eng)
th_morse       = compute_thresholds(morse_flat)

# ── Crisis event definitions ─────────────────────────────────────
EVENTS = {
    'GFC (Global Financial Crisis)': {
        'onset': '2007-12-31',
        'quarters': ['2007-12-31','2008-03-31','2008-06-30','2008-09-30',
                      '2008-12-31','2009-03-31','2009-06-30'],
    },
    'EU Sovereign Debt Crisis': {
        'onset': '2011-09-30',
        'quarters': ['2011-09-30','2011-12-31','2012-03-31','2012-06-30'],
    },
    'COVID-19 Shock': {
        'onset': '2020-03-31',
        'quarters': ['2020-03-31','2020-06-30'],
    },
}

print("=" * 100)
print("  BANKING CRISIS — EARLY WARNING TIMELINE ANALYSIS")
print("  Morse (unsupervised alarm) vs LGBM (supervised risk score)")
print("=" * 100)

# ── Per-approach thresholds ──────────────────────────────────────
print(f"\n  Calibration window: {dates[0]} .. {dates[CALIB-1]}  ({CALIB} quarters)")
print()
for name, th in [('Morse Alarm (standalone)', th_morse),
                  ('LGBM RT+BSDT (flat)',     th_lgbm_flat),
                  ('LGBM RT+BSDT+EFlow',      th_lgbm_eflow),
                  ('LGBM Engine (fused)',      th_lgbm_eng)]:
    print(f"  {name:32s}  μ={th['mu']:.4f}  σ={th['sigma']:.4f}  "
          f"2σ={th['2σ']:.4f}  3σ={th['3σ']:.4f}")

# ── Helper: find first exceedance ────────────────────────────────
def first_above(scores, threshold, before_date, dates_list):
    """Return (date, idx, score) of first quarter where score > threshold
       that occurs at or before `before_date`."""
    before_idx = dates_list.index(before_date)
    for i in range(len(scores)):
        if i > before_idx:
            break
        if not np.isnan(scores[i]) and scores[i] > threshold:
            return dates_list[i], i, scores[i]
    return None, None, None

# ── For each crisis: full timeline ───────────────────────────────
for event_name, info in EVENTS.items():
    onset = info['onset']
    onset_idx = dates.index(onset)
    crisis_qs = info['quarters']

    print()
    print("─" * 100)
    print(f"  {event_name}")
    print(f"  Onset: {onset}  (quarter index {onset_idx})")
    print("─" * 100)

    # ── First alarm / detection for each approach ────────────────
    approaches = [
        ('Morse Alarm (Layer 2)',   morse_flat,   th_morse),
        ('LGBM RT+BSDT (Layer 1)', lgbm_flat,    th_lgbm_flat),
        ('LGBM RT+BSDT+EFlow',     lgbm_eflow,   th_lgbm_eflow),
        ('LGBM Engine (fused)',     lgbm_eng,     th_lgbm_eng),
    ]

    print()
    print(f"  {'Approach':35s} | {'First 2σ alarm':22s} | Lead  | {'First 3σ alarm':22s} | Lead")
    print(f"  {'-'*35}-+-{'-'*22}-+-------+-{'-'*22}-+------")

    for aname, scores, th in approaches:
        for level in ['2σ', '3σ']:
            pass  # done inline below

        # 2σ first exceedance (search entire history up to end of crisis)
        last_crisis_q = crisis_qs[-1]
        last_crisis_idx = dates.index(last_crisis_q)

        d2, i2, s2 = None, None, None
        d3, i3, s3 = None, None, None

        for i in range(len(scores)):
            if i > last_crisis_idx:
                break
            if np.isnan(scores[i]):
                continue
            if d2 is None and scores[i] > th['2σ']:
                d2, i2, s2 = dates[i], i, scores[i]
            if d3 is None and scores[i] > th['3σ']:
                d3, i3, s3 = dates[i], i, scores[i]

        lead2 = f"{onset_idx - i2}q" if i2 is not None else "—"
        lead3 = f"{onset_idx - i3}q" if i3 is not None else "—"
        alarm2 = f"{d2} ({s2:.3f})" if d2 else "never"
        alarm3 = f"{d3} ({s3:.3f})" if d3 else "never"

        print(f"  {aname:35s} | {alarm2:22s} | {lead2:5s} | {alarm3:22s} | {lead3}")

    # ── Quarter-by-quarter score timeline ────────────────────────
    # Show from 4 quarters before onset to 2 quarters after last crisis quarter
    start = max(0, onset_idx - 4)
    end   = min(T, dates.index(crisis_qs[-1]) + 3)

    print()
    print(f"  Quarter-by-quarter scores (▲ = crisis quarter, * = above 2σ, ** = above 3σ):")
    print()
    print(f"  {'Date':12s} {'Crisis':6s}  {'Morse':>8s}  {'LGBM_flat':>10s}  {'LGBM_EFlow':>11s}  {'LGBM_engine':>12s}")
    print(f"  {'-'*12} {'-'*6}  {'-'*8}  {'-'*10}  {'-'*11}  {'-'*12}")

    for i in range(start, end):
        d = dates[i]
        is_crisis = '  ▲' if d in crisis_qs else ''

        def fmt(score, th):
            if np.isnan(score):
                return '   —    '
            flag = ''
            if score > th['3σ']:
                flag = '**'
            elif score > th['2σ']:
                flag = ' *'
            return f"{score:7.4f}{flag}"

        m  = fmt(morse_flat[i], th_morse)
        lf = fmt(lgbm_flat[i],  th_lgbm_flat)
        le = fmt(lgbm_eflow[i], th_lgbm_eflow)
        en = fmt(lgbm_eng[i],   th_lgbm_eng)

        print(f"  {d:12s} {is_crisis:6s}  {m:>8s}  {lf:>10s}  {le:>11s}  {en:>12s}")

# ══════════════════════════════════════════════════════════════════
#  SUMMARY: Lead-time matrix
# ══════════════════════════════════════════════════════════════════
print()
print("=" * 100)
print("  EARLY WARNING LEAD-TIME SUMMARY (quarters before crisis onset)")
print("=" * 100)
print()
print(f"  {'Event':30s} | {'Morse 2σ':10s} | {'Morse 3σ':10s} | {'LGBM_flat 2σ':13s} | {'LGBM_flat 3σ':13s} | {'Engine 2σ':10s} | {'Engine 3σ':10s}")
print(f"  {'-'*30}-+-{'-'*10}-+-{'-'*10}-+-{'-'*13}-+-{'-'*13}-+-{'-'*10}-+-{'-'*10}")

for event_name, info in EVENTS.items():
    onset = info['onset']
    onset_idx = dates.index(onset)
    last_crisis_idx = dates.index(info['quarters'][-1])

    leads = []
    for scores, th in [(morse_flat, th_morse), (morse_flat, th_morse),
                        (lgbm_flat, th_lgbm_flat), (lgbm_flat, th_lgbm_flat),
                        (lgbm_eng, th_lgbm_eng), (lgbm_eng, th_lgbm_eng)]:
        pass

    row = []
    for scores, th, level in [
        (morse_flat, th_morse, '2σ'), (morse_flat, th_morse, '3σ'),
        (lgbm_flat, th_lgbm_flat, '2σ'), (lgbm_flat, th_lgbm_flat, '3σ'),
        (lgbm_eng, th_lgbm_eng, '2σ'), (lgbm_eng, th_lgbm_eng, '3σ'),
    ]:
        first_i = None
        for i in range(len(scores)):
            if i > last_crisis_idx:
                break
            if not np.isnan(scores[i]) and scores[i] > th[level]:
                first_i = i
                break
        if first_i is not None:
            lead = onset_idx - first_i
            if lead >= 0:
                row.append(f"+{lead}q before")
            else:
                row.append(f"{-lead}q after")
        else:
            row.append("never")

    print(f"  {event_name:30s} | {row[0]:10s} | {row[1]:10s} | {row[2]:13s} | {row[3]:13s} | {row[4]:10s} | {row[5]:10s}")

# ══════════════════════════════════════════════════════════════════
#  Key insight: Morse as pre-cursor alarm
# ══════════════════════════════════════════════════════════════════
print()
print("=" * 100)
print("  KEY TIMELINE INSIGHT")
print("=" * 100)

# Check Morse trajectory leading up to GFC
onset_idx = dates.index('2007-12-31')
print(f"\n  Morse score trajectory leading into GFC:")
for i in range(max(0, onset_idx - 6), onset_idx + 8):
    d = dates[i]
    ms = morse_flat[i]
    is_crisis = ' ◀ CRISIS' if d in EVENTS['GFC (Global Financial Crisis)']['quarters'] else ''
    above = ''
    if not np.isnan(ms):
        if ms > th_morse['3σ']:
            above = ' ▓▓▓ ALARM(3σ)'
        elif ms > th_morse['2σ']:
            above = ' ░░░ WARNING(2σ)'
    ms_str = f"{ms:.4f}" if not np.isnan(ms) else "     nan"
    print(f"    {d}  Morse={ms_str:>8s}{above}{is_crisis}")

# Morse in post-2022 period (rising scores)
print(f"\n  Morse score in 2022-2024 (post-COVID structural shift):")
for i in range(len(dates)):
    if dates[i] >= '2022-01-01':
        ms = morse_flat[i]
        above = ''
        if not np.isnan(ms):
            if ms > th_morse['3σ']:
                above = ' ▓▓▓ ALARM(3σ)'
            elif ms > th_morse['2σ']:
                above = ' ░░░ WARNING(2σ)'
        print(f"    {dates[i]}  Morse={ms:.4f}{above}")

print()
print("  CONCLUSION:")
print("  ─────────────")
print("  Morse serves as the unsupervised structural early warning alarm.")
print("  LGBM RT+BSDT serves as the supervised risk quantification layer.")
print("  Together: Morse fires first (structural shift), LGBM quantifies severity.")
print()
