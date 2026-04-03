"""
Lead-time analysis: How many days/months before each crisis did each signal fire?
Uses saved results from bank_lgbm_engine_results.json (3-layer architecture).
"""
import json, numpy as np, sys
from datetime import datetime

with open("results/bank_lgbm_engine_results.json") as f:
    R = json.load(f)

# ── Quarter end-dates (2005-Q1 … 2023-Q4, 76 quarters) ──────────────
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

# ── Crisis onsets ─────────────────────────────────────────────────────
CRISES = [
    ("GFC (Global Financial Crisis)", datetime(2007, 12, 1)),
    ("EU Sovereign Debt Crisis",     datetime(2011, 7, 1)),
    ("COVID-19 Shock",               datetime(2020, 1, 1)),
]

# ── Collect all score series ──────────────────────────────────────────
all_scores = {}
for v, s in R["layer1_scores"].items():
    all_scores[f"L1 Engine/{v}"] = s
for v, s in R["layer2_scores"].items():
    all_scores[f"L2 BSDT-EW/{v}"] = s
for v, s in R["layer3_scores"].items():
    all_scores[f"L3 Confirm/{v}"] = s

BURN = 11  # calibration quarters

SEP = "=" * 110

# ── Per-crisis analysis ──────────────────────────────────────────────
print(SEP)
print("  EARLY WARNING LEAD-TIME ANALYSIS  |  Banking G-SIB Panel  |  3-Layer LGBM Engine")
print("  Question: How many days / months before crisis onset did each signal FIRST fire?")
print(SEP)

summary_rows = []

for crisis_name, onset in CRISES:
    print(f"\n{SEP}")
    print(f"  CRISIS: {crisis_name}")
    print(f"  Onset : {onset.strftime('%B %d, %Y')}")
    print(SEP)

    rows = []
    for sname, scores in all_scores.items():
        s = np.array(scores, dtype=float)
        # Calibration: first 15 post-burn quarters
        calib = s[BURN : BURN + 15]
        calib = calib[~np.isnan(calib)]
        if len(calib) < 3:
            continue
        mu  = float(np.mean(calib))
        sig = float(np.std(calib))
        if sig < 1e-12:
            continue

        for n_sigma, label in [(2, "2-sigma"), (3, "3-sigma")]:
            thresh = mu + n_sigma * sig
            first_t = None
            for t in range(BURN, len(s)):
                if dates[t] >= onset:
                    break          # reached crisis — no pre-crisis alarm
                if s[t] > thresh:
                    first_t = t
                    break

            if first_t is not None:
                alarm_date = dates[first_t]
                delta_days = (onset - alarm_date).days
                delta_months = delta_days / 30.44
                rows.append(dict(
                    signal=sname, thresh_label=label, n_sigma=n_sigma,
                    alarm_date=alarm_date, days=delta_days,
                    months=delta_months, score=s[first_t], thresh=thresh,
                ))

    if not rows:
        print("\n  >> NO pre-crisis alarm fired by any signal at any threshold.\n")
        summary_rows.append((crisis_name, onset, None, None))
        continue

    # Sort: most lead first
    rows.sort(key=lambda r: (-r["days"], r["n_sigma"]))

    hdr = (f"  {'Signal':<28s} {'Thresh':<9s} {'Alarm Date':<14s} "
           f"{'Lead':>8s} {'':>12s} {'Score':>8s}  {'Thr':>8s}")
    print(hdr)
    print(f"  {'-' * 100}")
    for r in rows:
        lead_str = f"{r['days']:>5d} days"
        mo_str   = f"({r['months']:.1f} months)"
        print(f"  {r['signal']:<28s} {r['thresh_label']:<9s} "
              f"{r['alarm_date'].strftime('%Y-%m-%d'):<14s} "
              f"{lead_str:>10s} {mo_str:>12s} "
              f"{r['score']:>8.4f}  {r['thresh']:>8.4f}")

    # Best per crisis
    best_2 = [r for r in rows if r["n_sigma"] == 2]
    best_3 = [r for r in rows if r["n_sigma"] == 3]
    b2 = best_2[0] if best_2 else None
    b3 = best_3[0] if best_3 else None
    summary_rows.append((crisis_name, onset, b2, b3))

# ── Grand summary ────────────────────────────────────────────────────
print(f"\n\n{SEP}")
print("  GRAND SUMMARY — Earliest Alarm per Crisis")
print(SEP)
print(f"  {'Crisis':<32s} {'Threshold':<10s} {'Signal':<28s} {'Alarm':<14s} {'Lead':>12s}")
print(f"  {'-' * 100}")

for crisis_name, onset, b2, b3 in summary_rows:
    for label, b in [("2-sigma", b2), ("3-sigma", b3)]:
        if b:
            lead_str = f"{b['days']} d / {b['months']:.1f} mo"
            print(f"  {crisis_name:<32s} {label:<10s} {b['signal']:<28s} "
                  f"{b['alarm_date'].strftime('%Y-%m-%d'):<14s} {lead_str:>12s}")
        else:
            print(f"  {crisis_name:<32s} {label:<10s} {'—':>28s} {'NO ALARM':>14s}")

# ── Per-quarter score table for GFC (most important) ─────────────────
print(f"\n\n{SEP}")
print("  GFC QUARTER-BY-QUARTER TIMELINE (key signals)")
print(SEP)
gfc_onset = datetime(2007, 12, 1)

key_signals = [
    ("L1 Engine/fused",    "Engine Fused"),
    ("L2 BSDT-EW/mfls",   "BSDT MFLS"),
    ("L2 BSDT-EW/e_bs",   "BSDT E_BS"),
    ("L3 Confirm/morse",   "Morse"),
    ("L3 Confirm/betti",   "Betti"),
]

# Print header
hdr_parts = [f"  {'Quarter':<12s}"]
for _, lbl in key_signals:
    hdr_parts.append(f"{lbl:>14s}")
hdr_parts.append(f"  {'Status':<30s}")
print("".join(hdr_parts))
print(f"  {'-' * 110}")

# Show t=11 to t=30 (2007-Q4 to 2012-Q3 — covers GFC + EU Sovereign)
for t in range(BURN, min(40, 76)):
    qdate = dates[t]
    label = f"{qdate.year}-Q{(qdate.month-1)//3+1}"
    parts = [f"  {label:<12s}"]

    for sname, _ in key_signals:
        s = all_scores[sname]
        val = s[t] if t < len(s) else float("nan")
        parts.append(f"{val:>14.4f}")

    # Status
    status = ""
    if datetime(2007, 10, 1) <= qdate <= datetime(2009, 6, 30):
        status = "  << GFC CRISIS"
    elif datetime(2011, 7, 1) <= qdate <= datetime(2012, 6, 30):
        status = "  << EU SOVEREIGN"
    elif qdate < gfc_onset:
        # Check if any signal alarmed
        for sname, _ in key_signals:
            s = np.array(all_scores[sname], dtype=float)
            calib = s[BURN:BURN+15]
            calib = calib[~np.isnan(calib)]
            if len(calib) < 3: continue
            mu, sg = float(np.mean(calib)), float(np.std(calib))
            if sg < 1e-12: continue
            if s[t] > mu + 2*sg:
                status = "  ** PRE-CRISIS ALARM **"
                break
    parts.append(status)
    print("".join(parts))

# ── COVID timeline ────────────────────────────────────────────────────
print(f"\n\n{SEP}")
print("  COVID QUARTER-BY-QUARTER TIMELINE (key signals)")
print(SEP)

hdr_parts = [f"  {'Quarter':<12s}"]
for _, lbl in key_signals:
    hdr_parts.append(f"{lbl:>14s}")
hdr_parts.append(f"  {'Status':<30s}")
print("".join(hdr_parts))
print(f"  {'-' * 110}")

for t in range(52, min(68, 76)):  # ~2018-Q1 to 2021-Q4
    qdate = dates[t]
    label = f"{qdate.year}-Q{(qdate.month-1)//3+1}"
    parts = [f"  {label:<12s}"]
    for sname, _ in key_signals:
        s = all_scores[sname]
        val = s[t] if t < len(s) else float("nan")
        parts.append(f"{val:>14.4f}")
    status = ""
    if datetime(2020, 1, 1) <= qdate <= datetime(2020, 6, 30):
        status = "  << COVID CRISIS"
    parts.append(status)
    print("".join(parts))

# ── 2022-2023 structural shift ───────────────────────────────────────
print(f"\n\n{SEP}")
print("  2022-2023 STRUCTURAL SHIFT TIMELINE (Morse detects SVB precursor)")
print(SEP)

hdr_parts = [f"  {'Quarter':<12s}"]
for _, lbl in key_signals:
    hdr_parts.append(f"{lbl:>14s}")
print("".join(hdr_parts))
print(f"  {'-' * 110}")

for t in range(64, 76):  # 2021-Q1 to 2023-Q4
    qdate = dates[t]
    label = f"{qdate.year}-Q{(qdate.month-1)//3+1}"
    parts = [f"  {label:<12s}"]
    for sname, _ in key_signals:
        s = all_scores[sname]
        val = s[t] if t < len(s) else float("nan")
        parts.append(f"{val:>14.4f}")
    print("".join(parts))

print(f"\n{SEP}")
print("  Done.")
print(SEP)
