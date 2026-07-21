# -*- coding: utf-8 -*-
"""Lead/FPR threshold frontier for canonical early-warning domains."""
from __future__ import annotations
import os, json, sys
import numpy as np
import pandas as pd

THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, THIS)
import canonical_early_warning_all_domains as C

OUTDIR = os.path.join(THIS, "results", "canonical_early_warning_all_domains")
os.makedirs(OUTDIR, exist_ok=True)

THR_QUANTILES = [0.90, 0.95, 0.975, 0.98, 0.99, 0.995, 0.999]


def grade(fp):
    if fp < 5: return "deployment"
    if fp < 20: return "research"
    if fp < 100: return "exploratory"
    return "too_noisy"


def eval_threshold(panel, E, thr):
    alarms = E > thr
    T = len(E)
    excluded = C._mask_windows(T, panel.crisis_windows, pad_pre=panel.max_pre)
    normal = ~excluded
    fp1000 = 1000.0 * alarms[normal].sum() / max(1, normal.sum())
    event_rows = []
    for ev, onset in panel.events.items():
        s, e = panel.crisis_windows[ev]
        lo = max(0, onset - panel.max_pre)
        pre = np.where(alarms[lo:onset])[0]
        inside = np.where(alarms[onset:e])[0]
        if len(pre):
            idx = int(lo + pre[0]); lead = int(onset - idx); timing = "before"
        elif len(inside):
            idx = int(onset + inside[0]); lead = -int(idx - onset); timing = "inside"
        else:
            idx = None; lead = None; timing = "miss"
        mask = np.zeros(T, bool); mask[s:e] = True
        event_rows.append(dict(event=ev, lead=lead, timing=timing,
                               hit_rate=float(alarms[mask].mean()) if mask.any() else np.nan))
    valid = [r["lead"] for r in event_rows if r["lead"] is not None]
    early = [x for x in valid if x > 0]
    return dict(fp_per_1000=float(fp1000), grade=grade(float(fp1000)),
                n_detected=sum(r["lead"] is not None for r in event_rows),
                n_early=len(early), median_early_lead=(float(np.median(early)) if early else None),
                mean_hit_rate=float(np.nanmean([r["hit_rate"] for r in event_rows])),
                events=event_rows)


def load_all_panels():
    panels = []
    for loader in [C.load_gsib, C.load_fdic, C.load_ercot_combined]:
        try: panels.append(loader())
        except Exception as e: print(f"[WARN] {loader.__name__}: {e}")
    try: panels.extend(C.load_protein_all())
    except Exception as e: print(f"[WARN] protein: {e}")
    try: panels.extend(C.load_supply_chain_all())
    except Exception as e: print(f"[WARN] supply: {e}")
    return panels


def main():
    rows = []
    best = {}
    for panel in load_all_panels():
        if panel.ref_mask.sum() < max(5, panel.X.shape[1] + 1):
            ref = np.zeros(len(panel.X), bool); ref[:max(10, len(panel.X)//4)] = True; panel.ref_mask = ref
        eng = C.CanonicalAlarm().fit(panel.X[panel.ref_mask])
        out = eng.evaluate(panel.X)
        E = np.asarray(out["E"])
        T = len(E)
        normal = ~C._mask_windows(T, panel.crisis_windows, pad_pre=panel.max_pre)
        bg = E[normal] if normal.any() else E[panel.ref_mask]
        thresholds = {"canonical_mu2sigma": float(out["threshold"])}
        for q in THR_QUANTILES:
            thresholds[f"bg_q{q:.3f}"] = float(np.quantile(bg, q))
        domain_rows = []
        for name, thr in thresholds.items():
            m = eval_threshold(panel, E, thr)
            row = dict(domain=panel.name, threshold_name=name, threshold=thr,
                       unit=panel.step_unit, **{k:v for k,v in m.items() if k != "events"})
            rows.append(row); domain_rows.append(row)
        feasible = [r for r in domain_rows if r["fp_per_1000"] < 20]
        if feasible:
            choice = sorted(feasible, key=lambda r: (r["n_early"], r["mean_hit_rate"], r["median_early_lead"] or -1), reverse=True)[0]
        else:
            choice = sorted(domain_rows, key=lambda r: (r["fp_per_1000"], -r["n_early"]))[0]
        best[panel.name] = choice
        med = "n/a" if choice["median_early_lead"] is None else f"{choice['median_early_lead']:.0f}{panel.step_unit}"
        print(f"{panel.name:<34} best={choice['threshold_name']:<18} early={choice['n_early']}/{len(panel.events)} med={med:>8} FP/1000={choice['fp_per_1000']:.1f} grade={choice['grade']}")
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUTDIR, "gap_threshold_frontier.csv"), index=False)
    with open(os.path.join(OUTDIR, "gap_threshold_best.json"), "w") as f:
        json.dump(best, f, indent=2, default=str)
    print("wrote frontier + best threshold files")

if __name__ == "__main__":
    main()
