"""
domain_real_climate.py
======================
Domain IX (REAL DATA) — Earth Systems: NASA GISTEMP global land+ocean monthly
temperature anomaly (1880-present).

Data: https://data.giss.nasa.gov/gistemp/tabledata_v4/GLB.Ts+dSST.csv

Detection engine: STRICT LOCKED CANONICAL-v4 ODE  (canonical_v4_engine.py)
  S=(X-mu0)/sigma0, G=Sigma0^{-1}, J=I, g_X=2GS, E=S'GS, F=F_base-g_X,
  gamma=E/(E+theta), X_dot = F - gamma * <F,g_X>/||g_X||^2 g_X,
  BSDT channels delta_C/A/T/G defined from locked-ODE quantities.

Presentation style: Odeyemi 2026 BSDT paper
  Fisher-VR weights (eq. 2.4) over the v4 BSDT channels,
  composite E_paper = sum_k w_k z_k(delta_k),
  split-conformal p-values (eq. 6.9) on the v4 anomaly score,
  adaptive rolling P99 threshold (sec. 7.12).
Reference (frozen normal) = pre-industrial baseline 1880-1949 monthly anomalies.
Crisis epoch              = post-2000 (accelerated warming).
"""
from __future__ import annotations
import json, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from canonical_v4_engine import FrozenCanonicalV4
from canonical_v4_paper_style import (
    evaluate_paper_style, channel_dominance_weighted, first_alarm_lead,
)

DATA = r"C:\amttp\data\external_validation\climate\gistemp_GLB_TsdSST.csv"
OUTDIR = r"c:\amttp\research\neural-stability\figures"
RESULTDIR = r"c:\amttp\research\neural-stability\results"
os.makedirs(OUTDIR, exist_ok=True); os.makedirs(RESULTDIR, exist_ok=True)
OUT_PNG = os.path.join(OUTDIR, "domain_real_climate.png")
OUT_JSON = os.path.join(RESULTDIR, "domain_real_climate.json")

NAVY, GOLD, RUST, TEAL = "#1f3b73", "#c9a227", "#a23a1f", "#1a5f5f"
BSDT_CLR = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3"]
MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def load_gistemp(path: str = DATA) -> pd.DataFrame:
    # GISTEMP CSV has 1 metadata row at top.
    df = pd.read_csv(path, skiprows=1)
    # Keep Year + 12 monthly columns
    df = df[["Year"] + MONTHS].copy()
    for m in MONTHS:
        df[m] = pd.to_numeric(df[m], errors="coerce")
    df = df.dropna(subset=MONTHS)
    return df.reset_index(drop=True)


def main() -> None:
    df = load_gistemp()
    years = df["Year"].values.astype(int)
    X = df[MONTHS].values.astype(float)             # (n_years, 12) monthly anomaly °C
    print(f"  GISTEMP rows: {len(df)}  years {years.min()}..{years.max()}  features=12 months")

    # Frozen reference: 1880..1949 (pre-acceleration baseline, no crisis).
    ref_mask = (years >= 1880) & (years <= 1949)
    crisis_year = 2000
    crisis_idx = int(np.argmax(years >= crisis_year))
    print(f"  Reference window: 1880..1949 ({ref_mask.sum()} years)  crisis epoch: {crisis_year}")

    eng = FrozenCanonicalV4(thresh_percentile=99.0).fit(X[ref_mask])
    res = evaluate_paper_style(eng, X, X[ref_mask], alpha_alarm=0.01,
                               rolling_window=16)
    cv4 = res.canonical                # underlying canonical-v4 result
    dom = channel_dominance_weighted(res, mask=(years >= crisis_year))
    lead = first_alarm_lead(res.alarms_paper, crisis_idx)
    n_alarms_pre = int(res.alarms_paper[:crisis_idx].sum())
    n_alarms_post = int(res.alarms_paper[crisis_idx:].sum())
    fa_idx = int(np.argmax(res.alarms_paper)) if res.alarms_paper.any() else -1
    fa_year = int(years[fa_idx]) if fa_idx >= 0 else None
    print(f"  First alarm: year {fa_year}  lead = {lead} years before crisis epoch")
    print(f"  Pre-crisis alarms: {n_alarms_pre}/{crisis_idx} years   post-crisis: {n_alarms_post}/{len(years)-crisis_idx}")
    print(f"  Fisher-VR weights  C={res.weights[0]:.3f}  G={res.weights[1]:.3f}  A={res.weights[2]:.3f}  T={res.weights[3]:.3f}")
    print("  BSDT dominance (post-crisis, weighted z):")
    for k, v in sorted(dom.items(), key=lambda kv: -kv[1]):
        print(f"    {k:<8} {v:.4f}")

    # ----- plot -----
    fig = plt.figure(figsize=(16, 10), facecolor="white")
    fig.suptitle("Domain IX (REAL) — NASA GISTEMP Global Temperature  ·  Canonical v4 ODE (paper-style presentation)",
                 fontsize=13, weight="bold", color=NAVY, y=0.98)
    gs = GridSpec(3, 3, figure=fig, hspace=0.42, wspace=0.32, top=0.91, bottom=0.07, left=0.07, right=0.97)

    ax = fig.add_subplot(gs[0, :])
    ax.plot(years, X.mean(axis=1), color=NAVY, lw=1.2, label="Annual mean anomaly (°C)")
    ax.axvspan(1880, 1949, color=TEAL, alpha=0.12, label="Frozen reference 1880-1949")
    ax.axvline(crisis_year, color=RUST, ls="--", lw=1.2, label=f"Crisis epoch {crisis_year}")
    alarm_yrs = years[res.alarms_paper]
    if len(alarm_yrs):
        ax.scatter(alarm_yrs, np.full_like(alarm_yrs, X.mean(axis=1).max(), dtype=float),
                   marker="v", color=RUST, s=22, label="Canonical-v4 alarm")
    ax.set_xlabel("Year"); ax.set_ylabel("Anomaly (°C)")
    ax.set_title("Annual mean anomaly with canonical-v4 alarms", fontsize=10, weight="bold")
    ax.legend(fontsize=8, ncol=4)

    ax = fig.add_subplot(gs[1, 0])
    ax.plot(years, cv4.score, color=NAVY, lw=1.0, label="v4 anomaly score")
    ax.plot(years, res.E_paper, color=GOLD, lw=0.8, ls="--", label="E_paper = Σ wₖ zₖ(δₖ)")
    ax.axvline(crisis_year, color=RUST, ls="--")
    ax.set_title("v4 score (math) vs paper-style composite", fontsize=10, weight="bold")
    ax.set_xlabel("Year"); ax.legend(fontsize=7)

    ax = fig.add_subplot(gs[1, 1])
    ax.semilogy(years, np.clip(res.pvalue, 1e-4, 1.0), color=GOLD)
    ax.axhline(res.info["alpha_alarm_effective"], color=RUST, ls="--",
               label=f"α_eff = {res.info['alpha_alarm_effective']:.3f}")
    ax.axvline(crisis_year, color=RUST, ls="--")
    ax.set_title("Split-conformal p-value (on v4 score)", fontsize=10, weight="bold"); ax.set_xlabel("Year"); ax.legend(fontsize=7)

    ax = fig.add_subplot(gs[1, 2])
    ax.plot(years, cv4.score, color=NAVY, lw=0.9, label="v4 score")
    ax.plot(years, res.threshold_adaptive, color=RUST, ls="--", lw=0.9, label="adaptive P99")
    ax.axhline(cv4.threshold, color=GOLD, ls=":", lw=0.9, label=f"frozen p99 = {cv4.threshold:.3f}")
    ax.axvline(crisis_year, color=RUST, ls=":")
    ax.set_title("v4 score vs adaptive + frozen thresholds", fontsize=10, weight="bold"); ax.set_xlabel("Year"); ax.legend(fontsize=7)

    ax = fig.add_subplot(gs[2, :2])
    for i, key in enumerate(["delta_C","delta_G","delta_A","delta_T"]):
        v = getattr(cv4, key)
        v = (v - v.min())/(v.max()-v.min()+1e-12)
        ax.plot(years, v, color=BSDT_CLR[i], lw=0.9,
                label=f"{key} (w={res.weights[i]:.2f})")
    ax.axvline(crisis_year, color=RUST, ls="--")
    ax.set_title("Canonical-v4 BSDT channels (min-max normalised) with Fisher-VR weights", fontsize=10, weight="bold")
    ax.set_xlabel("Year"); ax.legend(fontsize=8, ncol=4)

    ax = fig.add_subplot(gs[2, 2]); ax.axis("off")
    txt = ("Canonical v4 ODE (math)  ·  Paper-style presentation\n"
           f"Source: NASA GISTEMP (giss.nasa.gov)\n"
           f"Years: {years.min()}..{years.max()}  N={len(years)}\n"
           f"Reference: 1880..1949 ({int(ref_mask.sum())} yr, frozen)\n"
           f"Frozen v4 p99: {cv4.threshold:.4f}\n"
           f"Fisher-VR weights (over v4 channels):\n"
           f"  δ_C={res.weights[0]:.3f}  δ_G={res.weights[1]:.3f}\n"
           f"  δ_A={res.weights[2]:.3f}  δ_T={res.weights[3]:.3f}\n"
           f"Crisis epoch: {crisis_year}\n\n"
           f"Conformal alarm α_eff: {res.info['alpha_alarm_effective']:.3f}\n"
           f"First alarm: {fa_year}  lead = {lead} yr\n"
           f"Pre-crisis alarms:  {n_alarms_pre}/{crisis_idx}\n"
           f"Post-crisis alarms: {n_alarms_post}/{len(years)-crisis_idx}\n\n"
           "BSDT dominance (post, weighted z):\n"
           + "\n".join(f"  {k:<8} {v:.3f}" for k,v in sorted(dom.items(), key=lambda kv:-kv[1])))
    ax.text(0.0, 1.0, txt, va="top", ha="left", fontsize=8.0, family="monospace",
            color=NAVY, bbox=dict(boxstyle="round,pad=0.5", fc="#f5f0e8", ec=GOLD))

    fig.savefig(OUT_PNG, dpi=150, bbox_inches="tight"); plt.close(fig)
    out = {
        "dataset": "NASA GISTEMP GLB.Ts+dSST",
        "source_url": "https://data.giss.nasa.gov/gistemp/tabledata_v4/GLB.Ts+dSST.csv",
        "engine": "FrozenCanonicalV4 (canonical-v4 ODE)",
        "presentation": "Odeyemi 2026 paper-style",
        "years": [int(years.min()), int(years.max())],
        "reference_window": "1880-1949",
        "crisis_epoch_year": int(crisis_year),
        "fisher_vr_weights": {"C": float(res.weights[0]), "G": float(res.weights[1]),
                              "A": float(res.weights[2]), "T": float(res.weights[3])},
        "frozen_v4_threshold_p99": float(cv4.threshold),
        "alpha_alarm_effective": float(res.info["alpha_alarm_effective"]),
        "first_alarm_year": fa_year,
        "lead_years": int(lead),
        "pre_crisis_alarms": n_alarms_pre,
        "post_crisis_alarms": n_alarms_post,
        "bsdt_dominance_post_crisis": dom,
        "engine_info": res.info,
        "outputs": {"figure": OUT_PNG, "json": OUT_JSON},
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"  Saved {OUT_PNG}\n  Saved {OUT_JSON}")


if __name__ == "__main__":
    main()
