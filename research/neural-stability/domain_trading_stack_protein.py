# -*- coding: utf-8 -*-
"""
domain_trading_stack_protein.py
================================
Mode A: apply trading-stack brakes to the canonical-v4 protein pipeline.

For each PDB protein:
  1. Fetch B-factor profile (RCSB).
  2. Build (n_residues, 5) state matrix (existing helper).
  3. Fit FrozenCanonicalV4 on bottom-50% B-factor residues (ordered core).
  4. Sweep ~100 brake configs; for each, compute AUROC / hit-rate / FAR /
     lead-time vs B-factor > mu+2*sigma "disorder" mask.
  5. Save per-config metrics CSV + summary JSON; render top-3 PNG.

Baseline ("OFF") config = no brakes; matches the existing v2 gateway up to
the CB direction convention.
"""
from __future__ import annotations

import json
import os
import sys
import time
from itertools import product

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from canonical_v4_engine import FrozenCanonicalV4
from domain_v2_protein import PDB_IDS, PROTEIN_NAMES, fetch_pdb_bfactors, bfactors_to_state_matrix
import trading_stack_brakes as TSB

OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "trading_stack_protein")
FIGDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
os.makedirs(OUTDIR, exist_ok=True)
os.makedirs(FIGDIR, exist_ok=True)

REF_B_FRACTION  = 0.50
CRISIS_B_ZSCORE = 2.0

# Sweep grid (≈108 cells per protein after pruning trivial duplicates)
KAPPA_GRID    = [None, 10, 20]
OMEGA_GRID    = [0.0, 0.5, 1.0]
ADMISS_GRID   = [0.0, 1.0, 2.0]
DD_GRID       = [None, (0.10, 1.0, 0.20), (0.20, 2.0, 0.40)]   # (dd_thr, beta, k_min)
G24_GRID      = [(0.0, 0), (1e-4, 100), (3e-4, 100)]            # (eta, lock_min)
RELEASE_GRID  = [0.0, 0.55]

CB_HALT       = 0.08
CB_RESUME     = 0.04


def crisis_mask_from_bfactors(bf: np.ndarray) -> np.ndarray:
    mu, s = bf.mean(), bf.std()
    return bf > (mu + CRISIS_B_ZSCORE * s)


def run_one_protein(pdb_id: str) -> list[dict]:
    print(f"\n[{pdb_id}] fetching ...")
    data = fetch_pdb_bfactors(pdb_id)
    if data is None:
        print(f"[{pdb_id}] FETCH FAILED — skipping")
        return []
    bf = data["bfactors"]
    n = len(bf)
    X = bfactors_to_state_matrix(bf)
    crisis = crisis_mask_from_bfactors(bf)
    ref_cut = np.percentile(bf, REF_B_FRACTION * 100)
    ref_mask = bf <= ref_cut
    X_ref = X[ref_mask]

    cb_window = max(8, n // 4)
    rows = []

    for kappa_max in KAPPA_GRID:
        engine = FrozenCanonicalV4(alpha_base=1.0)
        engine.fit(X_ref)
        lam_g7 = TSB.apply_g7_to_engine(engine, kappa_max)
        psi_star = TSB.compute_psi_star_from_engine(engine, X_ref)
        rank_Ix = TSB.fisher_rank(engine.G_)
        result = engine.evaluate(X)
        score = result.score
        gamma = result.gamma
        rhs = result.delta_A   # MFLS analogue of rhs_norm

        # Baseline OFF run for this kappa
        baseline = TSB.run_brake_pipeline(
            score, gamma, rhs, threshold=engine.threshold_,
            cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window=cb_window,
        )
        m = TSB.crisis_metrics(baseline["score_mod"], baseline["alarms"], crisis)
        rows.append(dict(
            pdb_id=pdb_id, n_res=n, n_crisis=int(crisis.sum()),
            kappa_max=str(kappa_max), lam_g7=lam_g7, psi_star=psi_star,
            omega_a=0.0, curv_b=0.0, admiss_c=0.0,
            dd_thr="off", beta=0.0, k_min=1.0,
            g24_eta=0.0, g24_lock_min=0,
            release_thr=0.0,
            mean_kmod=baseline["mean_kmod"], mean_kdd=baseline["mean_kdd"],
            pct_halted=baseline["pct_halted"], n_g24=baseline["n_g24"],
            n_blocked=baseline["n_blocked"], n_brake=baseline["n_brake"],
            cb_window=cb_window, threshold=float(engine.threshold_),
            **m, config="BASELINE",
        ))

        for omega_a, admiss_c, dd_cfg, g24_cfg, rel in product(
            OMEGA_GRID, ADMISS_GRID, DD_GRID, G24_GRID, RELEASE_GRID
        ):
            if omega_a == 0.0 and admiss_c == 0.0 and dd_cfg is None and g24_cfg == (0.0, 0) and rel == 0.0:
                continue  # already captured as BASELINE
            if dd_cfg is None:
                dd_thr, beta, k_min_v = None, 0.0, 1.0
            else:
                dd_thr, beta, k_min_v = dd_cfg
            g24_eta, g24_lm = g24_cfg
            out = TSB.run_brake_pipeline(
                score, gamma, rhs, threshold=engine.threshold_,
                omega_a=omega_a, admiss_c=admiss_c, psi_star=psi_star,
                dd_thr=dd_thr, beta=beta, k_min=k_min_v, dd_stop=0.40,
                cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window=cb_window,
                g24_eta=g24_eta, g24_lock_min=g24_lm, g24_rank_Ix=rank_Ix,
                release_thr=rel, release_ext=max(2, n // 20),
            )
            m = TSB.crisis_metrics(out["score_mod"], out["alarms"], crisis)
            rows.append(dict(
                pdb_id=pdb_id, n_res=n, n_crisis=int(crisis.sum()),
                kappa_max=str(kappa_max), lam_g7=lam_g7, psi_star=psi_star,
                omega_a=omega_a, curv_b=0.0, admiss_c=admiss_c,
                dd_thr=("off" if dd_thr is None else f"{dd_thr:.2f}"),
                beta=beta, k_min=k_min_v,
                g24_eta=g24_eta, g24_lock_min=g24_lm,
                release_thr=rel,
                mean_kmod=out["mean_kmod"], mean_kdd=out["mean_kdd"],
                pct_halted=out["pct_halted"], n_g24=out["n_g24"],
                n_blocked=out["n_blocked"], n_brake=out["n_brake"],
                cb_window=cb_window, threshold=float(engine.threshold_),
                **m, config="SWEEP",
            ))
    return rows


def render_top3_png(df: pd.DataFrame, pdb_id: str, n_res: int, crisis: np.ndarray) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sub = df[(df["pdb_id"] == pdb_id) & np.isfinite(df["auroc"])]
    if sub.empty:
        return
    top = sub.sort_values("auroc", ascending=False).head(3)
    fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
    fig.suptitle(f"{pdb_id} — Top-3 brake configs by AUROC")
    for ax, (_, r) in zip(axes, top.iterrows()):
        ax.plot(crisis.astype(int), color="red", alpha=0.3, label="disorder (B>μ+2σ)")
        ax.set_title(
            f"k={r['kappa_max']} ω={r['omega_a']:.1f} c={r['admiss_c']:.1f} "
            f"dd={r['dd_thr']} g24η={r['g24_eta']:.0e} | "
            f"AUROC={r['auroc']:.3f} HR={r['hit_rate']:.2f} FAR={r['far']:.3f} "
            f"lead={int(r['lead_time'])}",
            fontsize=8,
        )
        ax.legend(loc="upper right", fontsize=7)
    axes[-1].set_xlabel("residue index")
    fig.tight_layout()
    out = os.path.join(FIGDIR, f"trading_stack_protein_{pdb_id}_top3.png")
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"  -> {out}")


def main() -> None:
    t0 = time.time()
    print("=" * 100)
    print("  trading-stack brakes on PROTEIN domain (Mode A — crisis detection)")
    print("=" * 100)

    all_rows: list[dict] = []
    crisis_cache: dict[str, np.ndarray] = {}
    for pdb in PDB_IDS:
        rows = run_one_protein(pdb)
        all_rows.extend(rows)
        # rerun a cheap fetch to cache crisis mask for plotting
        data = fetch_pdb_bfactors(pdb)
        if data is not None:
            crisis_cache[pdb] = crisis_mask_from_bfactors(data["bfactors"])
        n_kept = len(rows)
        if rows:
            best = max(rows, key=lambda r: (r["auroc"] if np.isfinite(r["auroc"]) else -1))
            print(f"[{pdb}] sweep rows={n_kept}  best AUROC={best['auroc']:.3f}  "
                  f"(k={best['kappa_max']} ω={best['omega_a']:.1f} c={best['admiss_c']:.1f} "
                  f"dd={best['dd_thr']} g24η={best['g24_eta']:.0e})")

    df = pd.DataFrame(all_rows)
    csv_path = os.path.join(OUTDIR, "sweep_results.csv")
    df.to_csv(csv_path, index=False)
    print(f"\n  -> {csv_path}  ({len(df)} rows)")

    # summary: per protein, best by AUROC and lift over baseline
    summary = {}
    for pdb in PDB_IDS:
        sub = df[df["pdb_id"] == pdb]
        if sub.empty:
            continue
        baseline = sub[sub["config"] == "BASELINE"]
        base_auc = float(baseline["auroc"].max()) if not baseline.empty else float("nan")
        base_lead = int(baseline["lead_time"].max()) if not baseline.empty else 0
        finite = sub[np.isfinite(sub["auroc"])]
        best = finite.sort_values("auroc", ascending=False).head(1)
        if best.empty:
            continue
        b = best.iloc[0]
        summary[pdb] = dict(
            n_res=int(b["n_res"]), n_crisis=int(b["n_crisis"]),
            baseline_auroc=base_auc, baseline_lead=base_lead,
            best_auroc=float(b["auroc"]), best_lead=int(b["lead_time"]),
            best_far=float(b["far"]), best_hr=float(b["hit_rate"]),
            best_config=dict(
                kappa_max=str(b["kappa_max"]), omega_a=float(b["omega_a"]),
                admiss_c=float(b["admiss_c"]), dd_thr=str(b["dd_thr"]),
                beta=float(b["beta"]), k_min=float(b["k_min"]),
                g24_eta=float(b["g24_eta"]), g24_lock_min=int(b["g24_lock_min"]),
                release_thr=float(b["release_thr"]),
            ),
            delta_auroc=float(b["auroc"]) - base_auc if np.isfinite(base_auc) else None,
            delta_lead=int(b["lead_time"]) - base_lead if base_lead else None,
        )
        if pdb in crisis_cache:
            render_top3_png(df, pdb, int(b["n_res"]), crisis_cache[pdb])

    json_path = os.path.join(OUTDIR, "summary.json")
    with open(json_path, "w") as f:
        json.dump({"domain": "protein", "by_pdb": summary, "elapsed_s": time.time() - t0}, f, indent=2)
    print(f"  -> {json_path}")

    print("\n[Summary]")
    for pdb, s in summary.items():
        print(f"  {pdb} ({PROTEIN_NAMES.get(pdb, pdb)}): "
              f"baseline AUROC={s['baseline_auroc']:.3f}  "
              f"best AUROC={s['best_auroc']:.3f} "
              f"(Δ={(s['delta_auroc'] if s['delta_auroc'] is not None else float('nan')):+.3f})  "
              f"HR={s['best_hr']:.2f}  FAR={s['best_far']:.3f}")
    print(f"\n  total elapsed = {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
