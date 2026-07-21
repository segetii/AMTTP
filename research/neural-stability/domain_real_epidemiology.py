"""
domain_real_epidemiology.py
===========================
Domain XI (REAL DATA) — Epidemiology: JHU CSSE COVID-19 confirmed cases (global).

Data: csse_covid_19_time_series/time_series_covid19_confirmed_global.csv
Source: https://github.com/CSSEGISandData/COVID-19

Detection engine: STRICT LOCKED CANONICAL-v4 ODE  (canonical_v4_engine.py)
Presentation style: Odeyemi 2026 BSDT paper
  Fisher-VR weights (eq. 2.4) over the v4 BSDT channels,
  composite E_paper = sum_k w_k z_k(delta_k),
  split-conformal p-values (eq. 6.9) on the v4 anomaly score,
  adaptive rolling P99 threshold (sec. 7.12).
Multi-region tensor: top-N countries by terminal cases.
Reference window: first 60 days of the time series (Jan-Feb 2020 baseline).
Crisis epoch:     WHO pandemic declaration 2020-03-11.
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

DATA = r"C:\amttp\data\external_validation\epi\jhu_covid19_confirmed_global.csv"
OUTDIR = r"c:\amttp\research\neural-stability\figures"
RESULTDIR = r"c:\amttp\research\neural-stability\results"
os.makedirs(OUTDIR, exist_ok=True); os.makedirs(RESULTDIR, exist_ok=True)
OUT_PNG = os.path.join(OUTDIR, "domain_real_epidemiology.png")
OUT_JSON = os.path.join(RESULTDIR, "domain_real_epidemiology.json")

NAVY, GOLD, RUST, TEAL = "#1f3b73", "#c9a227", "#a23a1f", "#1a5f5f"
BSDT_CLR = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3"]


def load_jhu(path: str = DATA, top_n: int = 12):
    df = pd.read_csv(path)
    date_cols = [c for c in df.columns if c not in ("Province/State","Country/Region","Lat","Long")]
    g = df.groupby("Country/Region")[date_cols].sum()
    # Top N by terminal total
    top = g.iloc[:, -1].sort_values(ascending=False).head(top_n).index.tolist()
    g = g.loc[top]
    # Convert to daily new cases (positive only)
    new = g.diff(axis=1).clip(lower=0).fillna(0.0)
    new = new.iloc[:, 1:]                                 # drop the first NaN diff col
    dates = pd.to_datetime(new.columns, format="%m/%d/%y")
    X = new.values.T.astype(float)                        # (n_days, n_countries)
    # Mild log scaling (heavy-tailed counts, fit-free)
    X = np.log1p(X)
    return X, dates, top


def main() -> None:
    X, dates, countries = load_jhu()
    print(f"  JHU days: {X.shape[0]}  countries: {X.shape[1]} -> {countries}")
    print(f"  Date range: {dates.min().date()} .. {dates.max().date()}")

    # Reference: first 60 days = pre-pandemic baseline (Jan 22 .. Mar 22 2020).
    REF = 60
    crisis_date = pd.Timestamp("2020-03-11")             # WHO pandemic declaration
    crisis_idx = int(np.argmin(np.abs(dates - crisis_date)))
    print(f"  Reference window: first {REF} days  crisis (WHO declaration): index {crisis_idx} ({dates[crisis_idx].date()})")

    eng = FrozenCanonicalV4(thresh_percentile=99.0).fit(X[:REF])
    res = evaluate_paper_style(eng, X, X[:REF], alpha_alarm=0.01,
                               rolling_window=60)
    cv4 = res.canonical
    dom = channel_dominance_weighted(res, mask=np.arange(len(X)) >= crisis_idx)
    lead = first_alarm_lead(res.alarms_paper, crisis_idx)
    fa = int(np.argmax(res.alarms_paper)) if np.any(res.alarms_paper) else -1
    n_alarms_pre  = int(res.alarms_paper[:crisis_idx].sum())
    n_alarms_post = int(res.alarms_paper[crisis_idx:].sum())
    print(f"  First alarm: {dates[fa].date() if fa >= 0 else 'none'}  lead = {lead} days vs WHO declaration")
    print(f"  Pre-crisis alarms: {n_alarms_pre}/{crisis_idx}  Post: {n_alarms_post}/{len(X)-crisis_idx}")
    print(f"  Fisher-VR weights  C={res.weights[0]:.3f}  G={res.weights[1]:.3f}  A={res.weights[2]:.3f}  T={res.weights[3]:.3f}")
    print("  BSDT dominance (post-crisis, weighted z):")
    for k, v in sorted(dom.items(), key=lambda kv: -kv[1]):
        print(f"    {k:<8} {v:.4f}")

    # ---- plot ----
    fig = plt.figure(figsize=(16, 10), facecolor="white")
    fig.suptitle("Domain XI (REAL) — JHU COVID-19 (top 12 countries)  ·  Canonical v4 ODE (paper-style presentation)",
                 fontsize=13, weight="bold", color=NAVY, y=0.98)
    gs = GridSpec(3, 3, figure=fig, hspace=0.42, wspace=0.32, top=0.91, bottom=0.07, left=0.07, right=0.97)

    ax = fig.add_subplot(gs[0, :])
    for i, c in enumerate(countries[:6]):
        ax.plot(dates, X[:, i], lw=0.6, alpha=0.85, label=c)
    ax.axvspan(dates[0], dates[REF-1], color=TEAL, alpha=0.12, label=f"Frozen ref ({REF}d)")
    ax.axvline(dates[crisis_idx], color=RUST, ls="--", label="WHO 2020-03-11")
    ax.set_title("log(1+new daily cases) by country", fontsize=10, weight="bold")
    ax.legend(fontsize=7, ncol=4)

    ax = fig.add_subplot(gs[1, 0])
    ax.plot(dates, cv4.score, color=NAVY, lw=0.9, label="v4 anomaly score")
    ax.plot(dates, res.E_paper, color=GOLD, lw=0.7, ls="--", label="E_paper = Σ wₖ zₖ(δₖ)")
    ax.axvline(dates[crisis_idx], color=RUST, ls="--")
    ax.set_title("v4 score vs paper-style composite", fontsize=10, weight="bold"); ax.legend(fontsize=7)

    ax = fig.add_subplot(gs[1, 1])
    ax.semilogy(dates, np.clip(res.pvalue, 1e-4, 1.0), color=GOLD)
    ax.axhline(res.info["alpha_alarm_effective"], color=RUST, ls="--",
               label=f"α_eff = {res.info['alpha_alarm_effective']:.3f}")
    ax.axvline(dates[crisis_idx], color=RUST, ls="--")
    ax.set_title("Split-conformal p-value (on v4 score)", fontsize=10, weight="bold"); ax.legend(fontsize=7)

    ax = fig.add_subplot(gs[1, 2])
    ax.plot(dates, cv4.score, color=NAVY, lw=0.7, label="v4 score")
    ax.plot(dates, res.threshold_adaptive, color=RUST, ls="--", lw=0.7, label="adaptive P99")
    ax.axhline(cv4.threshold, color=GOLD, ls=":", lw=0.7, label=f"frozen p99 = {cv4.threshold:.3f}")
    ax.axvline(dates[crisis_idx], color=RUST, ls=":")
    ax.set_title("v4 score vs adaptive + frozen thresholds", fontsize=10, weight="bold"); ax.legend(fontsize=7)

    ax = fig.add_subplot(gs[2, :2])
    for i, key in enumerate(["delta_C","delta_G","delta_A","delta_T"]):
        v = getattr(cv4, key); v = (v - v.min())/(v.max()-v.min()+1e-12)
        ax.plot(dates, v, color=BSDT_CLR[i], lw=0.8,
                label=f"{key} (w={res.weights[i]:.2f})")
    ax.axvline(dates[crisis_idx], color=RUST, ls="--")
    ax.set_title("Canonical-v4 BSDT channels (min-max normalised) with Fisher-VR weights", fontsize=10, weight="bold")
    ax.legend(fontsize=8, ncol=4)

    ax = fig.add_subplot(gs[2, 2]); ax.axis("off")
    txt = ("Canonical v4 ODE (math)  ·  Paper-style presentation\n"
           "Source: JHU CSSE (github.com/CSSEGISandData)\n"
           f"Days: {X.shape[0]}  Countries: {X.shape[1]}\n"
           f"Reference: first {REF} d (frozen)\n"
           f"Frozen v4 p99: {cv4.threshold:.4f}\n"
           f"Fisher-VR weights (over v4 channels):\n"
           f"  δ_C={res.weights[0]:.3f}  δ_G={res.weights[1]:.3f}\n"
           f"  δ_A={res.weights[2]:.3f}  δ_T={res.weights[3]:.3f}\n"
           f"Crisis: WHO pandemic 2020-03-11 (idx {crisis_idx})\n\n"
           f"Conformal alarm α_eff: {res.info['alpha_alarm_effective']:.3f}\n"
           f"First alarm: {dates[fa].date() if fa>=0 else 'none'}\n"
           f"Lead vs WHO: {lead} days\n"
           f"Pre-crisis alarms:  {n_alarms_pre}/{crisis_idx}\n"
           f"Post-crisis alarms: {n_alarms_post}/{len(X)-crisis_idx}\n\n"
           "BSDT dominance (post, weighted z):\n"
           + "\n".join(f"  {k:<8} {v:.3f}" for k,v in sorted(dom.items(), key=lambda kv:-kv[1])))
    ax.text(0.0, 1.0, txt, va="top", ha="left", fontsize=7.8, family="monospace",
            color=NAVY, bbox=dict(boxstyle="round,pad=0.5", fc="#f5f0e8", ec=GOLD))

    fig.savefig(OUT_PNG, dpi=150, bbox_inches="tight"); plt.close(fig)
    out = {
        "dataset": "JHU CSSE COVID-19 confirmed (global, daily)",
        "source_url": "https://github.com/CSSEGISandData/COVID-19",
        "engine": "FrozenCanonicalV4 (canonical-v4 ODE)",
        "presentation": "Odeyemi 2026 paper-style",
        "countries": countries,
        "days": int(X.shape[0]),
        "reference_days": REF,
        "crisis_index": crisis_idx,
        "crisis_date": str(dates[crisis_idx].date()),
        "fisher_vr_weights": {"C": float(res.weights[0]), "G": float(res.weights[1]),
                              "A": float(res.weights[2]), "T": float(res.weights[3])},
        "frozen_v4_threshold_p99": float(cv4.threshold),
        "alpha_alarm_effective": float(res.info["alpha_alarm_effective"]),
        "first_alarm_index": int(fa),
        "first_alarm_date": str(dates[fa].date()) if fa >= 0 else None,
        "lead_days": int(lead),
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
