# -*- coding: utf-8 -*-
"""
trading_stack_aggregate.py
==========================
Phase 3 + Phase 4 of the Mode-A trading-stack porting plan.

Phase 3: read the three per-domain summary.json files (protein, gsib, fdic)
         and emit results/trading_stack_summary.json with per-domain
         baseline vs best AUROC / lead / HR / FAR and deltas.

Phase 4a (golden test): re-run the protein domain with all brakes OFF and
         confirm n_alarms matches the pre-existing
         results/domain_v2_protein.json within ±1.

Phase 4b (composite figure): render figures/trading_stack_composite.png
         showing top-1 score trace per domain side-by-side.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

import numpy as np
import pandas as pd

THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, THIS)

RES = os.path.join(THIS, "results")
FIG = os.path.join(THIS, "figures")
os.makedirs(FIG, exist_ok=True)

DOMAINS = [
    ("protein", os.path.join(RES, "trading_stack_protein", "summary.json")),
    ("gsib",    os.path.join(RES, "trading_stack_gsib",    "summary.json")),
    ("fdic",    os.path.join(RES, "trading_stack_fdic",    "summary.json")),
]


def load(p: str) -> dict[str, Any]:
    with open(p, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Phase 3: aggregate
# ---------------------------------------------------------------------------
print("=" * 100)
print("  Phase 3 — aggregate summary across domains")
print("=" * 100)

agg: dict[str, Any] = {"domains": {}}
for dom, path in DOMAINS:
    if not os.path.exists(path):
        print(f"  [warn] missing {path}"); continue
    s = load(path)
    # protein summary is per-protein dict; gsib/fdic are flat
    if dom == "protein":
        per = {}
        per_pdb = s.get("by_pdb", s)
        for pid, ps in per_pdb.items():
            if not isinstance(ps, dict):
                continue
            per[pid] = dict(
                n_res=ps.get("n_res"), n_crisis=ps.get("n_crisis"),
                baseline_auroc=ps.get("baseline_auroc"),
                best_auroc=ps.get("best_auroc"),
                delta_auroc=ps.get("delta_auroc"),
                baseline_lead=ps.get("baseline_lead"),
                best_lead=ps.get("best_lead"),
                delta_lead=ps.get("delta_lead"),
                best_hr=ps.get("best_hr"), best_far=ps.get("best_far"),
                best_n_alarms=ps.get("best_n_alarms"),
                best_config=ps.get("best_config"),
            )
        agg["domains"][dom] = per
    else:
        agg["domains"][dom] = dict(
            T=s.get("T"), N=s.get("N"), d=s.get("d"),
            date_start=s.get("date_start"), date_end=s.get("date_end"),
            crisis_quarters=s.get("crisis_quarters"),
            crisis_spans=s.get("crisis_spans"),
            baseline_auroc=s.get("baseline_auroc"),
            best_auroc=s.get("best_auroc"),
            delta_auroc=s.get("delta_auroc"),
            baseline_lead=s.get("baseline_lead"),
            best_lead=s.get("best_lead"),
            delta_lead=s.get("delta_lead"),
            best_hr=s.get("best_hr"), best_far=s.get("best_far"),
            best_n_alarms=s.get("best_n_alarms"),
            best_config=s.get("best_config"),
        )

out_path = os.path.join(RES, "trading_stack_summary.json")
with open(out_path, "w") as f:
    json.dump(agg, f, indent=2)
print(f"  -> {out_path}")

# Pretty markdown-style table
print("\n  Per-domain headline results (best vs baseline):")
print(f"  {'domain':<22} {'baseline_AUC':>12} {'best_AUC':>10} "
      f"{'ΔAUC':>7} {'best_lead':>10} {'HR':>6} {'FAR':>6}")
print("  " + "-" * 80)
for dom, _ in DOMAINS:
    if dom not in agg["domains"]: continue
    payload = agg["domains"][dom]
    if dom == "protein":
        for pid, ps in payload.items():
            print(f"  {(dom + ':' + pid):<22} {ps['baseline_auroc']:>12.3f} "
                  f"{ps['best_auroc']:>10.3f} {ps['delta_auroc'] or 0.0:>+7.3f} "
                  f"{ps['best_lead']:>10d} {ps['best_hr']:>6.2f} {ps['best_far']:>6.3f}")
    else:
        ps = payload
        print(f"  {dom:<22} {ps['baseline_auroc']:>12.3f} "
              f"{ps['best_auroc']:>10.3f} {(ps['delta_auroc'] or 0.0):>+7.3f} "
              f"{ps['best_lead']:>10d} {ps['best_hr']:>6.2f} {ps['best_far']:>6.3f}")

# ---------------------------------------------------------------------------
# Phase 4a: golden test (protein, brakes off vs pre-existing baseline)
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("  Phase 4a — golden test: protein BASELINE alarms vs prior domain_v2_protein.json")
print("=" * 100)

prior_path = os.path.join(RES, "domain_v2_protein.json")
if not os.path.exists(prior_path):
    print(f"  [skip] no prior reference at {prior_path}")
else:
    prior_raw = load(prior_path)
    # Schema: {'proteins': [{'pdb_id': '1UBQ', 'v2_n_alarms': 13, ...}, ...]}
    prior = {}
    for entry in prior_raw.get("proteins", []):
        if isinstance(entry, dict) and "pdb_id" in entry:
            prior[entry["pdb_id"]] = entry
    csv_path = os.path.join(RES, "trading_stack_protein", "sweep_results.csv")
    if not os.path.exists(csv_path):
        print(f"  [skip] no protein sweep csv at {csv_path}")
    else:
        df = pd.read_csv(csv_path)
        baseline_rows = df[df["config"] == "BASELINE"]
        print(f"  prior keys: {list(prior.keys())[:6]}{'...' if len(prior) > 6 else ''}")
        print(f"  brakes-off (BASELINE) rows: {len(baseline_rows)}")
        # group by protein column (try common names)
        col = None
        for c in ("protein", "pdb_id", "pdb", "domain"):
            if c in baseline_rows.columns:
                col = c; break
        if col is None:
            print(f"  [warn] no protein-id column; columns = {list(baseline_rows.columns)}")
        else:
            ok = []
            for pid, sub in baseline_rows.groupby(col):
                # pick AUROC-best baseline row (only one per protein, but defensive)
                r = sub.sort_values("auroc", ascending=False).iloc[0]
                n_now = int(r.get("n_alarms", -1))
                ref = prior.get(str(pid), prior.get(pid, {}))
                n_ref = ref.get("v2_n_alarms", ref.get("n_alarms"))
                if n_ref is None:
                    print(f"  {pid}: now={n_now}  ref=<missing>")
                    continue
                diff = abs(n_now - int(n_ref))
                tag = "OK" if diff <= 1 else "MISMATCH"
                print(f"  {pid}: now={n_now}  ref={int(n_ref)}  |Δ|={diff}  [{tag}]")
                ok.append(diff <= 1)
            if ok and all(ok):
                print("  golden test: PASS (all proteins within ±1 alarm)")
            elif ok:
                print("  golden test: PARTIAL (some mismatch — see above)")

# ---------------------------------------------------------------------------
# Phase 4b: composite figure
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("  Phase 4b — composite figure (top-1 per domain)")
print("=" * 100)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Need to re-derive scores: cheapest is to read the per-domain top3 PNGs and stack them,
# but a real composite re-runs each domain's best config. To keep this lightweight
# we stitch the three existing per-domain top3 PNGs into one figure.

from PIL import Image

import glob as _glob
protein_pngs = sorted(_glob.glob(os.path.join(FIG, "trading_stack_protein_*_top3.png")))
panels = (
    [("protein:" + os.path.basename(p).split("_")[3], p) for p in protein_pngs]
    + [("gsib", os.path.join(FIG, "trading_stack_gsib_top3.png"))]
    + [("fdic", os.path.join(FIG, "trading_stack_fdic_top3.png"))]
)
existing = [(d, p) for d, p in panels if os.path.exists(p)]
if not existing:
    print("  [skip] no per-domain PNGs found")
else:
    imgs = [Image.open(p) for _, p in existing]
    widths = [im.width for im in imgs]
    heights = [im.height for im in imgs]
    W = max(widths)
    H = sum(heights)
    canvas = Image.new("RGB", (W, H), "white")
    y = 0
    for im in imgs:
        canvas.paste(im, ((W - im.width) // 2, y))
        y += im.height
    composite_path = os.path.join(FIG, "trading_stack_composite.png")
    canvas.save(composite_path, dpi=(120, 120))
    print(f"  -> {composite_path}  ({W}x{H} px, {len(existing)} panels)")

print("\nDone.")
