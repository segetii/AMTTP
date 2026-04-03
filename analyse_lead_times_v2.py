"""
Lead-time analysis v2 — Expanding-window thresholds.
Each quarter's alarm threshold is computed from ALL PRIOR quarters only.
This is the operationally correct measure: "given what we knew at the time,
when would the system have first alarmed?"
"""
import json, numpy as np
from datetime import datetime

with open("results/bank_lgbm_engine_results.json") as f:
    R = json.load(f)

# Quarter end-dates  (2005-Q1 … 2023-Q4, 76 quarters)
dates = []
y, q = 2005, 1
for _ in range(76):
    m = q * 3
    if m == 3:  d = datetime(y, 3, 31)
    elif m == 6:  d = datetime(y, 6, 30)
    elif m == 9:  d = datetime(y, 9, 30)
    else:         d = datetime(y, 12, 31)
    dates.append(d)
    q += 1
    if q > 4: q = 1; y += 1

def qlabel(t):
    d = dates[t]
    return f"{d.year}-Q{(d.month-1)//3+1}"

# Crisis definitions
CRISES = [
    ("GFC",          datetime(2007, 12, 1),  datetime(2009, 6, 30)),
    ("EU Sovereign", datetime(2011,  7, 1),  datetime(2012, 6, 30)),
    ("COVID-19",     datetime(2020,  1, 1),  datetime(2020, 6, 30)),
]

# All score series
all_scores = {}
for v, s in R["layer1_scores"].items():
    all_scores[f"L1/{v}"] = np.array(s, dtype=float)
for v, s in R["layer2_scores"].items():
    all_scores[f"L2/{v}"] = np.array(s, dtype=float)
for v, s in R["layer3_scores"].items():
    all_scores[f"L3/{v}"] = np.array(s, dtype=float)

MIN_HISTORY = 4   # need at least 4 quarters to estimate mu/sigma

SEP = "=" * 120

print(SEP)
print("  EARLY WARNING LEAD-TIME ANALYSIS v2")
print("  Expanding-window thresholds: alarm at quarter t if score(t) > mean(0..t-1) + n*std(0..t-1)")
print("  This measures: 'when would the system have FIRST raised an alarm given ONLY past data?'")
print(SEP)

for crisis_name, onset, end in CRISES:
    # Find onset quarter index
    onset_t = None
    for t in range(76):
        if dates[t] >= onset:
            onset_t = t
            break

    print(f"\n{'='*120}")
    print(f"  {crisis_name}  |  Onset: {onset.strftime('%B %d, %Y')}  |  Quarter: {qlabel(onset_t)} (t={onset_t})")
    print(f"{'='*120}")

    results = []

    for sname, scores in all_scores.items():
        for n_sigma in [2, 3]:
            first_alarm_t = None

            for t in range(MIN_HISTORY, onset_t):
                history = scores[:t]
                valid = history[~np.isnan(history)]
                if len(valid) < MIN_HISTORY:
                    continue
                mu  = float(np.mean(valid))
                sig = float(np.std(valid))
                if sig < 1e-15:
                    continue
                thresh = mu + n_sigma * sig

                if scores[t] > thresh:
                    first_alarm_t = t
                    break

            if first_alarm_t is not None:
                alarm_date = dates[first_alarm_t]
                delta = onset - alarm_date
                days  = delta.days
                months = days / 30.44
                results.append(dict(
                    signal=sname, n_sigma=n_sigma,
                    alarm_t=first_alarm_t, alarm_q=qlabel(first_alarm_t),
                    alarm_date=alarm_date, days=days, months=months,
                    score=float(scores[first_alarm_t]),
                    mu=float(np.mean(scores[:first_alarm_t])),
                    sigma=float(np.std(scores[:first_alarm_t])),
                ))

    if not results:
        print("  NO pre-crisis alarm by any signal.\n")
        continue

    results.sort(key=lambda r: (-r["days"], r["n_sigma"]))

    print(f"  {'Signal':<24s} {'Thr':<6s} {'Alarm Quarter':<16s} "
          f"{'Lead (days)':>12s} {'Lead (months)':>14s}  "
          f"{'Score':>8s}  {'mu+n*sig':>10s}")
    print(f"  {'-'*110}")
    for r in results:
        thr_str = f"{r['mu']:.4f}+{r['n_sigma']}*{r['sigma']:.4f}={r['mu']+r['n_sigma']*r['sigma']:.4f}"
        print(f"  {r['signal']:<24s} {r['n_sigma']}-sig  "
              f"{r['alarm_q']:<16s} {r['days']:>8d} d    {r['months']:>8.1f} mo    "
              f"{r['score']:>8.4f}  {thr_str}")

# ── MASTER TIMELINE: GFC ──────────────────────────────────────────────
print(f"\n\n{'='*120}")
print("  MASTER TIMELINE: GFC  |  Quarter-by-quarter, all signals, with expanding-window 2-sigma flags")
print(f"{'='*120}")

# Pick the most relevant signals
key_sigs = ["L1/fused", "L2/mfls", "L2/e_bs", "L3/morse", "L3/betti"]
key_labels = ["Engine", "MFLS", "E_BS", "Morse", "Betti"]

# Header
hdr = f"  {'Quarter':<10s}"
for lbl in key_labels:
    hdr += f" {lbl:>10s}"
hdr += f"  {'Flags':<40s}"
print(hdr)
print(f"  {'-'*120}")

for t in range(0, 30):  # 2005-Q1 to 2012-Q2
    q = qlabel(t)
    line = f"  {q:<10s}"
    flags = []

    for i, sname in enumerate(key_sigs):
        s = all_scores[sname]
        val = s[t] if t < len(s) else float("nan")
        line += f" {val:>10.4f}"

        # Check expanding-window 2-sigma
        if t >= MIN_HISTORY:
            hist = s[:t]
            valid = hist[~np.isnan(hist)]
            if len(valid) >= MIN_HISTORY:
                mu = float(np.mean(valid))
                sig = float(np.std(valid))
                if sig > 1e-15 and val > mu + 2*sig:
                    flags.append(f"{key_labels[i]}!")
                if sig > 1e-15 and val > mu + 3*sig:
                    flags[-1] = f"{key_labels[i]}!!!"

    # Crisis markers
    d = dates[t]
    marker = ""
    if datetime(2007, 10, 1) <= d <= datetime(2009, 6, 30):
        marker = " [GFC]"
    elif d < datetime(2007, 12, 1) and flags:
        marker = " ** EARLY WARNING **"

    flag_str = " ".join(flags)
    line += f"  {flag_str:<30s}{marker}"
    print(line)

# ── MASTER TIMELINE: COVID ────────────────────────────────────────────
print(f"\n\n{'='*120}")
print("  MASTER TIMELINE: COVID  |  Quarter-by-quarter with expanding-window 2-sigma flags")
print(f"{'='*120}")

hdr = f"  {'Quarter':<10s}"
for lbl in key_labels:
    hdr += f" {lbl:>10s}"
hdr += f"  {'Flags':<40s}"
print(hdr)
print(f"  {'-'*120}")

for t in range(50, 68):  # 2017-Q3 to 2022-Q1
    q = qlabel(t)
    line = f"  {q:<10s}"
    flags = []

    for i, sname in enumerate(key_sigs):
        s = all_scores[sname]
        val = s[t] if t < len(s) else float("nan")
        line += f" {val:>10.4f}"

        if t >= MIN_HISTORY:
            hist = s[:t]
            valid = hist[~np.isnan(hist)]
            if len(valid) >= MIN_HISTORY:
                mu = float(np.mean(valid))
                sig = float(np.std(valid))
                if sig > 1e-15 and val > mu + 2*sig:
                    flags.append(f"{key_labels[i]}!")
                if sig > 1e-15 and val > mu + 3*sig:
                    flags[-1] = f"{key_labels[i]}!!!"

    d = dates[t]
    marker = ""
    if datetime(2020, 1, 1) <= d <= datetime(2020, 6, 30):
        marker = " [COVID]"
    elif d < datetime(2020, 1, 1) and flags:
        marker = " ** EARLY WARNING **"

    flag_str = " ".join(flags)
    line += f"  {flag_str:<30s}{marker}"
    print(line)

# ── FINAL ANSWER ──────────────────────────────────────────────────────
print(f"\n\n{'='*120}")
print("  FINAL ANSWER: LEAD TIMES")
print(f"{'='*120}")

for crisis_name, onset, end in CRISES:
    onset_t = next(t for t in range(76) if dates[t] >= onset)
    print(f"\n  {crisis_name} (onset {onset.strftime('%Y-%m-%d')}):")

    for n_sigma in [2, 3]:
        best = None
        for sname, scores in all_scores.items():
            for t in range(MIN_HISTORY, onset_t):
                hist = scores[:t]
                valid = hist[~np.isnan(hist)]
                if len(valid) < MIN_HISTORY: continue
                mu, sig = float(np.mean(valid)), float(np.std(valid))
                if sig < 1e-15: continue
                if scores[t] > mu + n_sigma * sig:
                    days = (onset - dates[t]).days
                    if best is None or days > best[0]:
                        best = (days, sname, dates[t], qlabel(t))
                    break

        if best:
            days, sig_name, dt, ql = best
            mo = days / 30.44
            yr = days / 365.25
            print(f"    {n_sigma}-sigma earliest: {sig_name:<24s} at {ql}  "
                  f"=> {days} days = {mo:.1f} months = {yr:.2f} years BEFORE crisis")
        else:
            print(f"    {n_sigma}-sigma: NO pre-crisis alarm")

print(f"\n{'='*120}")
