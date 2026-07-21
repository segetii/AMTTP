# -*- coding: utf-8 -*-
"""
canonical_gap_protocol_report.py
================================
Post-process the canonical early-warning results with the Gap-Closure G5
validation protocol:

  - finite pre-crisis lead window
  - false positives per 1,000 non-crisis steps
  - lead / precision / hit-rate frontier under multiple thresholds
  - benchmark grades:
      deployment-grade: FP/1000 < 5
      research-grade:   FP/1000 < 20

This script does not rerun loaders; it consumes:
  results/canonical_early_warning_all_domains/summary.json
  results/canonical_early_warning_all_domains/domain_results.csv
and writes:
  results/canonical_early_warning_all_domains/gap_protocol_summary.json
  results/canonical_early_warning_all_domains/gap_protocol_table.csv
"""
from __future__ import annotations

import json
import os
import pandas as pd
import numpy as np

THIS = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(THIS, "results", "canonical_early_warning_all_domains")
SUMMARY = os.path.join(OUTDIR, "summary.json")
CSV = os.path.join(OUTDIR, "domain_results.csv")


def grade(fp_per_1000: float) -> str:
    if not np.isfinite(fp_per_1000):
        return "unknown"
    if fp_per_1000 < 5:
        return "deployment-grade"
    if fp_per_1000 < 20:
        return "research-grade"
    if fp_per_1000 < 100:
        return "exploratory"
    return "too noisy"


def lead_status(lead, unit: str) -> str:
    if pd.isna(lead):
        return "miss"
    lead = int(lead)
    if lead > 0:
        return f"early +{lead}{unit}"
    if lead == 0:
        return "at onset"
    return f"late {lead}{unit}"


def main() -> None:
    if not os.path.exists(SUMMARY) or not os.path.exists(CSV):
        raise FileNotFoundError("Run canonical_early_warning_all_domains.py first")
    with open(SUMMARY) as f:
        summary = json.load(f)
    df = pd.read_csv(CSV)

    rows = []
    for _, r in df.iterrows():
        fp = float(r["fp_per_1000"])
        rows.append(dict(
            domain=r["domain"],
            event=r["event"],
            onset=r["onset_label"],
            alarm=r["alarm_label"] if isinstance(r["alarm_label"], str) else None,
            lead=r["lead"] if not pd.isna(r["lead"]) else None,
            unit=r["step_unit"],
            lead_status=lead_status(r["lead"], r["step_unit"]),
            hit_rate=float(r["hit_rate"]),
            false_alarm_rate=float(r["far"]),
            fp_per_1000=fp,
            grade=grade(fp),
            peak_label=r["peak_label"],
            peak_E=float(r["peak_E"]),
        ))

    table = pd.DataFrame(rows)
    table_path = os.path.join(OUTDIR, "gap_protocol_table.csv")
    table.to_csv(table_path, index=False)

    domain_summary = {}
    for domain, sub in table.groupby("domain"):
        valid_leads = [int(x) for x in sub["lead"].dropna().tolist()]
        early = [x for x in valid_leads if x > 0]
        domain_summary[domain] = dict(
            n_events=int(len(sub)),
            n_detected=int(sub["alarm"].notna().sum()),
            n_early=int((sub["lead"].fillna(-999) > 0).sum()),
            median_lead=float(np.median(early)) if early else None,
            unit=str(sub["unit"].iloc[0]),
            mean_hit_rate=float(sub["hit_rate"].mean()),
            fp_per_1000=float(sub["fp_per_1000"].iloc[0]),
            grade=grade(float(sub["fp_per_1000"].iloc[0])),
            usable=bool(float(sub["fp_per_1000"].iloc[0]) < 20),
            interpretation="",
        )

    # Manual interpretation based on observed dynamics.
    for domain, ds in domain_summary.items():
        if domain.startswith("protein"):
            ds["interpretation"] = "Structural proxy only: labels are B-factor hot residues derived from same profile; not independent prediction."
        elif domain == "gsib":
            ds["interpretation"] = "Banking stress remains elevated after GFC; high FAR means early alarms are not actionable without regime reset."
        elif domain == "fdic":
            ds["interpretation"] = "Best real financial panel: detects banking stress with moderate FAR, but still above G5 research-grade threshold."
        elif domain == "ercot_demand_supply_hourly":
            ds["interpretation"] = "Demand+supply concatenation gives long apparent lead but FP/1000 is too high; needs stricter seasonal/weather baseline before deployment."
        elif domain.startswith("supply_"):
            ds["interpretation"] = "Simulation contains engineered precursors; early leads are expected, but high FAR means raw canonical E is too sensitive."

    out = dict(
        protocol="Gap Closure G5: lead + false positives per 1,000 non-crisis steps",
        benchmark=dict(deployment_grade="FP/1000 < 5", research_grade="FP/1000 < 20"),
        domains=domain_summary,
        warning="High lead time is not meaningful when FP/1000 is high; grade must be reported with lead.",
    )
    out_path = os.path.join(OUTDIR, "gap_protocol_summary.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    print("=" * 110)
    print("  Canonical early-warning — Gap G5 protocol summary")
    print("=" * 110)
    print(f"  {'Domain':<34} {'Events':>6} {'Early':>6} {'MedLead':>10} {'HR':>6} {'FP/1000':>9} {'Grade':>18}")
    print("  " + "-" * 104)
    for domain, ds in domain_summary.items():
        med = "n/a" if ds["median_lead"] is None else f"{ds['median_lead']:.0f}{ds['unit']}"
        print(f"  {domain:<34} {ds['n_events']:>6d} {ds['n_early']:>6d} {med:>10} "
              f"{ds['mean_hit_rate']:>6.2f} {ds['fp_per_1000']:>9.1f} {ds['grade']:>18}")
    print("\n  Per-event table written to:", table_path)
    print("  Summary written to:       ", out_path)


if __name__ == "__main__":
    main()
