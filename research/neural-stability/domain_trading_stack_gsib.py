# -*- coding: utf-8 -*-
"""
domain_trading_stack_gsib.py
=============================
Mode A: apply trading-stack brakes to the canonical-v4 engine on the real
G-SIB panel (FDIC bank-level + World Bank country-aggregate, 2005-Q1 → 2024-Q4).

Pipeline:
  1. Load (T, N, d) panel from `gsib_loader_real.build_gsib_panel_real`.
  2. Aggregate to (T, d) by cross-sectional mean across banks (per quarter).
  3. Reference window = quarters chronologically before 2008-01-01 (pre-GFC).
  4. Crisis truth windows:
       GFC      2008-Q3 → 2009-Q1
       Euro     2011-Q3 → 2012-Q1
       COVID    2020-Q1 → 2020-Q2
       SVB      2023-Q1 → 2023-Q2
  5. Sweep ~100 brake configs; record AUROC / hit-rate / FAR / lead-time.

Outputs:
  results/trading_stack_gsib/sweep_results.csv
  results/trading_stack_gsib/summary.json
  figures/trading_stack_gsib_top3.png
"""
from __future__ import annotations

import json
import os
import sys
import time
from itertools import product

import numpy as np
import pandas as pd

THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, THIS)
sys.path.insert(0, os.path.abspath(os.path.join(THIS, "..", "adaptive-friction", "banklevel_enhanced")))

from canonical_v4_engine import FrozenCanonicalV4
import trading_stack_brakes as TSB
from gsib_loader_real import build_gsib_panel_real, FEATURE_NAMES

OUTDIR = os.path.join(THIS, "results", "trading_stack_gsib")
FIGDIR = os.path.join(THIS, "figures")
os.makedirs(OUTDIR, exist_ok=True)
os.makedirs(FIGDIR, exist_ok=True)

REF_END   = pd.Timestamp("2008-01-01")
CRISIS_WINDOWS = [
    ("GFC",   "2008-09-30", "2009-03-31"),
    ("Euro",  "2011-09-30", "2012-03-31"),
    ("COVID", "2020-03-31", "2020-06-30"),
    ("SVB",   "2023-03-31", "2023-06-30"),
]

KAPPA_GRID    = [None, 10, 20]
OMEGA_GRID    = [0.0, 0.5, 1.0]
ADMISS_GRID   = [0.0, 1.0, 2.0]
DD_GRID       = [None, (0.10, 1.0, 0.20), (0.20, 2.0, 0.40)]
G24_GRID      = [(0.0, 0), (1e-4, 4), (3e-4, 4)]
RELEASE_GRID  = [0.0, 0.55]

CB_HALT       = 0.08
CB_RESUME     = 0.04
CB_WINDOW     = 12   # 12 quarters = 3 years rolling


def build_crisis_mask(dates: pd.DatetimeIndex) -> tuple[np.ndarray, dict]:
    mask = np.zeros(len(dates), dtype=bool)
    spans = {}
    for label, lo, hi in CRISIS_WINDOWS:
        in_win = np.asarray((dates >= pd.Timestamp(lo)) & (dates <= pd.Timestamp(hi)))
        mask |= in_win
        spans[label] = int(in_win.sum())
    return mask, spans


def main() -> None:
    t0 = time.time()
    print("=" * 100)
    print("  trading-stack brakes on G-SIB (FDIC + World Bank) — Mode A")
    print("=" * 100)

    print("\n[load] gsib panel (cache reuse) ...")
    panel = build_gsib_panel_real(verbose=False)
    X = panel["X"]                       # (T, N, d)
    dates = pd.DatetimeIndex(panel["dates"])
    T, N, d = X.shape
    print(f"  panel shape T={T}, N={N}, d={d}, dates {dates[0].date()}..{dates[-1].date()}")

    # Cross-sectional mean per quarter, ignoring NaN
    Xagg = np.nanmean(X, axis=1)         # (T, d)
    # Replace any remaining NaN with column median
    for j in range(Xagg.shape[1]):
        col = Xagg[:, j]
        if np.isnan(col).any():
            med = float(np.nanmedian(col))
            col[np.isnan(col)] = med
            Xagg[:, j] = col
    print(f"  aggregated (T,d) = {Xagg.shape}, features = {FEATURE_NAMES}")

    # Reference window
    ref_mask = np.asarray(dates < REF_END)
    if ref_mask.sum() < 8:
        ref_mask = np.zeros(T, bool); ref_mask[: max(8, T // 4)] = True
    X_ref = Xagg[ref_mask]
    print(f"  ref window: {int(ref_mask.sum())} quarters (pre-{REF_END.date()})")

    crisis, spans = build_crisis_mask(dates)
    print(f"  crisis mask: total {int(crisis.sum())} quarters  spans={spans}")
    if crisis.sum() == 0:
        print("  ERROR: empty crisis mask — abort"); return

    rows = []
    for kappa_max in KAPPA_GRID:
        engine = FrozenCanonicalV4(alpha_base=0.05)
        engine.fit(X_ref)
        lam_g7 = TSB.apply_g7_to_engine(engine, kappa_max)
        psi_star = TSB.compute_psi_star_from_engine(engine, X_ref)
        rank_Ix = TSB.fisher_rank(engine.G_)
        result = engine.evaluate(Xagg)
        score = result.score
        gamma = result.gamma
        rhs = result.delta_A
        thr = float(engine.threshold_)

        # baseline
        base = TSB.run_brake_pipeline(
            score, gamma, rhs, threshold=thr,
            cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window=CB_WINDOW,
        )
        m = TSB.crisis_metrics(base["score_mod"], base["alarms"], crisis)
        rows.append(dict(
            kappa_max=str(kappa_max), lam_g7=lam_g7, psi_star=psi_star,
            omega_a=0.0, admiss_c=0.0, dd_thr="off", beta=0.0, k_min=1.0,
            g24_eta=0.0, g24_lock_min=0, release_thr=0.0,
            mean_kmod=base["mean_kmod"], mean_kdd=base["mean_kdd"],
            pct_halted=base["pct_halted"], n_g24=base["n_g24"],
            n_blocked=base["n_blocked"], n_brake=base["n_brake"],
            cb_window=CB_WINDOW, threshold=thr, **m, config="BASELINE",
        ))

        for omega_a, admiss_c, dd_cfg, g24_cfg, rel in product(
            OMEGA_GRID, ADMISS_GRID, DD_GRID, G24_GRID, RELEASE_GRID
        ):
            if omega_a == 0.0 and admiss_c == 0.0 and dd_cfg is None and g24_cfg == (0.0, 0) and rel == 0.0:
                continue
            if dd_cfg is None:
                dd_thr, beta, k_min_v = None, 0.0, 1.0
            else:
                dd_thr, beta, k_min_v = dd_cfg
            g24_eta, g24_lm = g24_cfg
            out = TSB.run_brake_pipeline(
                score, gamma, rhs, threshold=thr,
                omega_a=omega_a, admiss_c=admiss_c, psi_star=psi_star,
                dd_thr=dd_thr, beta=beta, k_min=k_min_v, dd_stop=0.40,
                cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window=CB_WINDOW,
                g24_eta=g24_eta, g24_lock_min=g24_lm, g24_rank_Ix=rank_Ix,
                release_thr=rel, release_ext=2,
            )
            m = TSB.crisis_metrics(out["score_mod"], out["alarms"], crisis)
            rows.append(dict(
                kappa_max=str(kappa_max), lam_g7=lam_g7, psi_star=psi_star,
                omega_a=omega_a, admiss_c=admiss_c,
                dd_thr=("off" if dd_thr is None else f"{dd_thr:.2f}"),
                beta=beta, k_min=k_min_v,
                g24_eta=g24_eta, g24_lock_min=g24_lm, release_thr=rel,
                mean_kmod=out["mean_kmod"], mean_kdd=out["mean_kdd"],
                pct_halted=out["pct_halted"], n_g24=out["n_g24"],
                n_blocked=out["n_blocked"], n_brake=out["n_brake"],
                cb_window=CB_WINDOW, threshold=thr, **m, config="SWEEP",
            ))

    df = pd.DataFrame(rows)
    csv_path = os.path.join(OUTDIR, "sweep_results.csv")
    df.to_csv(csv_path, index=False)
    print(f"\n  -> {csv_path}  ({len(df)} rows)")

    baseline = df[df["config"] == "BASELINE"].sort_values("auroc", ascending=False).head(1)
    base_auc = float(baseline["auroc"].iloc[0]) if not baseline.empty else float("nan")
    base_lead = int(baseline["lead_time"].iloc[0]) if not baseline.empty else 0
    finite = df[np.isfinite(df["auroc"])]
    best = finite.sort_values("auroc", ascending=False).head(1)
    b = best.iloc[0]
    summary = dict(
        domain="gsib", T=int(T), N=int(N), d=int(d),
        date_start=str(dates[0].date()), date_end=str(dates[-1].date()),
        crisis_quarters=int(crisis.sum()), crisis_spans=spans,
        baseline_auroc=base_auc, baseline_lead=base_lead,
        best_auroc=float(b["auroc"]), best_lead=int(b["lead_time"]),
        best_far=float(b["far"]), best_hr=float(b["hit_rate"]),
        best_n_alarms=int(b["n_alarms"]),
        best_config=dict(
            kappa_max=str(b["kappa_max"]), omega_a=float(b["omega_a"]),
            admiss_c=float(b["admiss_c"]), dd_thr=str(b["dd_thr"]),
            beta=float(b["beta"]), k_min=float(b["k_min"]),
            g24_eta=float(b["g24_eta"]), g24_lock_min=int(b["g24_lock_min"]),
            release_thr=float(b["release_thr"]),
        ),
        delta_auroc=float(b["auroc"]) - base_auc if np.isfinite(base_auc) else None,
        delta_lead=int(b["lead_time"]) - base_lead,
    )
    json_path = os.path.join(OUTDIR, "summary.json")
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  -> {json_path}")

    # Top-3 PNG
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    top3 = finite.sort_values("auroc", ascending=False).head(3)
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    fig.suptitle("G-SIB — Top-3 brake configs by AUROC")
    # rebuild score for top configs (need engine + same modulators) — for visualisation only
    # We'll just plot the crisis mask + alarms_mod indicator from re-running each best config
    for ax, (_, r) in zip(axes, top3.iterrows()):
        # rebuild
        engine = FrozenCanonicalV4(alpha_base=0.05); engine.fit(X_ref)
        lam_g7 = TSB.apply_g7_to_engine(engine, None if r["kappa_max"] == "None" else int(r["kappa_max"]))
        psi_star = TSB.compute_psi_star_from_engine(engine, X_ref)
        rank_Ix = TSB.fisher_rank(engine.G_)
        res = engine.evaluate(Xagg)
        dd_thr = None if r["dd_thr"] == "off" else float(r["dd_thr"])
        out = TSB.run_brake_pipeline(
            res.score, res.gamma, res.delta_A, threshold=float(engine.threshold_),
            omega_a=float(r["omega_a"]), admiss_c=float(r["admiss_c"]), psi_star=psi_star,
            dd_thr=dd_thr, beta=float(r["beta"]), k_min=float(r["k_min"]),
            dd_stop=0.40, cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window=CB_WINDOW,
            g24_eta=float(r["g24_eta"]), g24_lock_min=int(r["g24_lock_min"]),
            g24_rank_Ix=rank_Ix, release_thr=float(r["release_thr"]), release_ext=2,
        )
        ax.fill_between(dates, 0, crisis.astype(int), color="red", alpha=0.2, label="crisis")
        ax2 = ax.twinx()
        ax2.plot(dates, out["score_mod"], color="navy", lw=1.0, label="score_mod")
        ax2.axhline(float(engine.threshold_), color="gray", ls="--", lw=0.7)
        idx = np.where(out["alarms"])[0]
        if len(idx) > 0:
            ax2.scatter(dates[idx], out["score_mod"][idx], color="orange", s=18, zorder=3, label="alarm")
        ax.set_title(
            f"k={r['kappa_max']} ω={r['omega_a']:.1f} c={r['admiss_c']:.1f} "
            f"dd={r['dd_thr']} g24η={r['g24_eta']:.0e} | "
            f"AUROC={r['auroc']:.3f} HR={r['hit_rate']:.2f} FAR={r['far']:.3f} "
            f"lead={int(r['lead_time'])}",
            fontsize=8,
        )
        ax.set_yticks([])
    fig.tight_layout()
    png = os.path.join(FIGDIR, "trading_stack_gsib_top3.png")
    fig.savefig(png, dpi=120); plt.close(fig)
    print(f"  -> {png}")

    print("\n[Summary]")
    print(f"  baseline AUROC={base_auc:.3f} lead={base_lead}")
    print(f"  best     AUROC={summary['best_auroc']:.3f} lead={summary['best_lead']} "
          f"HR={summary['best_hr']:.2f} FAR={summary['best_far']:.3f}")
    print(f"  Δ AUROC = {summary['delta_auroc']:+.3f}  Δ lead = {summary['delta_lead']:+d} quarters")
    print(f"  best config = {summary['best_config']}")
    print(f"  elapsed = {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
