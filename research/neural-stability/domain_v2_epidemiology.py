"""
domain_v2_epidemiology.py
=========================
Domain II (REAL DATA v2) — Epidemiology: JHU COVID-19 daily confirmed cases.

Data source:  C:\\amttp\\data\\external_validation\\epi\\jhu_covid19_confirmed_global.csv
              (Johns Hopkins CSSE — 2020-01-22 to 2023-03-10, 189 countries)

v2 improvements over domain_real_epidemiology.py:
  * ConfidenceGate: veto alarm when 2nd-derivative of log-cases ≤ 0
    (acceleration of growth required to fire a wave onset alarm)
  * DomainCircuitBreaker: after surging wave confirmed (score +8% above
    rolling peak), suppress alarms until wave deceleration restores score
    within 1% of halt peak

Crisis ground truth: R_eff > 1 estimated from weekly doubling-time.

Engine:  STRICT LOCKED CANONICAL-v4 ODE  (canonical_v4_engine.py)
         Agents = countries (top-20 by total cases), features = log-diff cases.
"""
from __future__ import annotations
import json, os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canonical_v4_engine import FrozenCanonicalV4
from canonical_v4_paper_style import evaluate_paper_style, channel_dominance_weighted, first_alarm_lead
from domain_bsdt_gateway_v2 import run_v2_gateway, rolling_derivative, rolling_corr_mean

CSV_PATH  = r"c:\amttp\data\external_validation\epi\jhu_covid19_confirmed_global.csv"
OUTDIR    = r"c:\amttp\research\neural-stability\figures"
RESULTDIR = r"c:\amttp\research\neural-stability\results"
os.makedirs(OUTDIR, exist_ok=True); os.makedirs(RESULTDIR, exist_ok=True)
OUT_PNG   = os.path.join(OUTDIR,    "domain_v2_epidemiology.png")
OUT_JSON  = os.path.join(RESULTDIR, "domain_v2_epidemiology.json")

NAVY, GOLD, RUST, TEAL = "#1f3b73", "#c9a227", "#a23a1f", "#1a5f5f"
N_COUNTRIES   = 20
REF_DAYS      = 60      # first 60 days (Jan-Mar 2020) as "normal" pre-epidemic reference
SMOOTH_WIN    = 7       # 7-day rolling mean for noisy case counts
EPI_CB_WINDOW = 90      # 90-day rolling max for circuit breaker


def load_jhu(csv_path: str) -> tuple[np.ndarray, list[str], list[str]]:
    """
    Load JHU CSV → smoothed log-daily-new-cases matrix.

    Returns:
        X      : (T, N) float array — log(1 + weekly-smoothed daily new cases)
        dates  : list[str] length T
        countries: list[str] length N
    """
    df = pd.read_csv(csv_path)
    # Drop non-date cols; aggregate by Country/Region (sum provinces)
    meta_cols = ["Province/State", "Country/Region", "Lat", "Long"]
    date_cols = [c for c in df.columns if c not in meta_cols]

    agg = df.groupby("Country/Region")[date_cols].sum()   # (n_countries, n_dates)
    cum = agg.values.astype(float)   # cumulative confirmed

    # Daily new cases (diff along date axis)
    daily = np.diff(cum, axis=1)
    daily = np.clip(daily, 0, None)  # remove data-correction negatives
    dates = date_cols[1:]            # drop first date column after diff

    # Select top-N by total confirmed
    totals = cum[:, -1]
    top_idx = np.argsort(totals)[-N_COUNTRIES:][::-1]
    daily_top = daily[top_idx]               # (N_countries, T)
    countries  = list(agg.index[top_idx])

    # 7-day rolling smooth
    def _smooth(arr):
        return np.convolve(arr, np.ones(SMOOTH_WIN)/SMOOTH_WIN, mode="same")
    smooth = np.stack([_smooth(daily_top[i]) for i in range(N_COUNTRIES)], axis=0)

    X = np.log1p(smooth).T    # (T, N) — log(1 + new cases)
    return X, dates, countries


def compute_growth_accel(X: np.ndarray) -> np.ndarray:
    """
    Confidence gate signal: 2nd derivative of log-cases (mean across countries).
    Positive = accelerating epidemic growth.
    """
    global_mean = X.mean(axis=1)         # (T,)
    first_deriv = np.gradient(global_mean)
    second_deriv = np.gradient(first_deriv)
    return second_deriv


def estimate_crisis_mask(X: np.ndarray, window: int = 14) -> np.ndarray:
    """
    Crisis = days when rolling growth rate suggest R_eff > 1.
    Heuristic: 2-week rolling slope of log(mean_new_cases) > 0.
    """
    mean_cases = np.expm1(X.mean(axis=1))    # back to case counts
    T = len(mean_cases)
    slopes = np.zeros(T)
    for t in range(window, T):
        seg = np.log1p(mean_cases[t-window:t]).clip(min=0)
        x_  = np.arange(window, dtype=float)
        if seg.std() > 0:
            slopes[t] = np.polyfit(x_, seg, 1)[0]
    return slopes > 0   # growing = crisis


def main() -> None:
    print("=" * 68)
    print("  DOMAIN II v2 — Epidemiology: JHU COVID-19 Real Data")
    print("=" * 68)

    if not os.path.exists(CSV_PATH):
        print(f"  [ERROR] JHU CSV not found: {CSV_PATH}")
        return

    print(f"  Loading {CSV_PATH} ...")
    X, dates, countries = load_jhu(CSV_PATH)
    T, N = X.shape
    print(f"  Shape: T={T} days, N={N} countries  dates={dates[0]}..{dates[-1]}")
    print(f"  Countries: {', '.join(countries[:8])} ...")

    # Reference window (pre-pandemic)
    ref_days  = min(REF_DAYS, T // 5)
    ref_mask  = np.zeros(T, dtype=bool)
    ref_mask[:ref_days] = True

    # Canonical v4 engine
    engine = FrozenCanonicalV4(alpha_base=1.0)
    engine.fit(X[ref_mask])
    result = engine.evaluate(X)

    ps = evaluate_paper_style(engine, X, X[ref_mask])

    crisis_mask = estimate_crisis_mask(X)
    conf_signal = compute_growth_accel(X)

    # v2 gateway
    v2 = run_v2_gateway(
        v1_alarms     = ps.alarms_paper,
        anomaly_score = result.score,
        conf_signal   = conf_signal,
        crisis_mask   = crisis_mask,
        conf_threshold= 0.47,
        halt_frac     = 0.08,
        resume_frac   = 0.01,
        cb_window     = EPI_CB_WINDOW,
    )

    _crisis_idx = int(np.argmax(crisis_mask)) if crisis_mask.any() else T
    lead_v1 = first_alarm_lead(ps.alarms_paper, _crisis_idx)
    lead_v2 = first_alarm_lead(v2["alarms_v2"],  _crisis_idx)
    imp     = v2.get("improvement", {})
    print(f"\n  v1 alarms: {ps.alarms_paper.sum()}  v2 alarms: {v2['alarms_v2'].sum()}")
    print(f"  Lead time  v1={lead_v1}d   v2={lead_v2}d")
    print(f"  Precision  v1={imp.get('v1',{}).get('precision',0):.3f}  v2={imp.get('v2',{}).get('precision',0):.3f}")
    print(f"  CB suppress: {v2['cb_info']['suppress_pct']:.1f}%  Gate veto: {v2['conf_info']['veto_pct']:.1f}%")

    # ── Plot ──────────────────────────────────────────────────────────────────
    t       = np.arange(T)
    mean_lc = X.mean(axis=1)
    al1     = ps.alarms_paper.astype(bool)
    al2     = v2["alarms_v2"].astype(bool)
    cr      = crisis_mask.astype(bool)

    fig, axes = plt.subplots(3, 1, figsize=(15, 10), facecolor="white")

    ax = axes[0]
    ax.stackplot(t, X.T * 0.05, alpha=0.4, linewidth=0)  # suppress huge legend
    ax.plot(t, mean_lc, color=NAVY, lw=1.8, label="Global mean log-cases")
    ax.fill_between(t, 0, mean_lc.max(), where=cr, color=RUST, alpha=0.12, label="Crisis (R>1)")
    ax.set_title("COVID-19 Daily New Cases (log-scale) — top 20 countries", fontsize=10, fontweight="bold")
    ax.set_ylabel("log(1 + new cases)"); ax.legend(fontsize=8)

    # Sample of tick labels
    step = T // 10
    ax.set_xticks(t[::step])
    ax.set_xticklabels([dates[i] for i in range(0, T, step)], rotation=30, fontsize=7)

    ax = axes[1]
    ax.plot(t, result.score, color=TEAL, lw=1.4, label="Canonical V4 score")
    ax.scatter(t[al1], result.score[al1], color=GOLD, s=20, zorder=5, label=f"v1 alarms ({al1.sum()})")
    ax.scatter(t[al2], result.score[al2], color=NAVY, s=20, marker="^", zorder=6, label=f"v2 alarms ({al2.sum()})")
    ax.fill_between(t, 0, result.score.max()*1.1, where=cr, color=RUST, alpha=0.10)
    ax.set_title("Canonical V4 anomaly score + v2 gated alarms", fontsize=10, fontweight="bold")
    ax.set_ylabel("Anomaly score"); ax.legend(fontsize=8)
    ax.set_xticks(t[::step])
    ax.set_xticklabels([dates[i] for i in range(0, T, step)], rotation=30, fontsize=7)

    ax = axes[2]
    cb_on  = np.array(v2["cb_info"].get("cb_halted", [False]*T), dtype=float)
    gate_v = np.array(v2["conf_info"].get("vetoed", [False]*T), dtype=float)
    ax.fill_between(t, 0, 1, where=cb_on.astype(bool),   color=RUST, alpha=0.3, label="CB halted")
    ax.fill_between(t, 0, 1, where=gate_v.astype(bool),  color=GOLD, alpha=0.3, label="Gate vetoed")
    ax.fill_between(t, 0, 1, where=cr,                   color=TEAL, alpha=0.15, label="Crisis")
    ax.set_title("Circuit breaker & confidence gate activity", fontsize=10, fontweight="bold")
    ax.set_xlabel("Day"); ax.set_ylim(0, 1.2); ax.legend(fontsize=8)
    ax.set_xticks(t[::step])
    ax.set_xticklabels([dates[i] for i in range(0, T, step)], rotation=30, fontsize=7)

    fig.suptitle("Domain II v2 — Epidemiology: JHU COVID-19\n"
                 "FrozenCanonicalV4 + tbr0p47 ConfidenceGate + CB halt/resume",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.96])
    fig.savefig(OUT_PNG, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Figure → {OUT_PNG}")

    payload = dict(
        domain="epidemiology",
        version="v2",
        engine="FrozenCanonicalV4",
        gateway="tbr0p47_ConfidenceGate + DomainCircuitBreaker",
        data_source="JHU COVID-19 Confirmed Cases (CSSE)",
        T=T, N=N,
        countries=countries,
        date_range=[dates[0], dates[-1]],
        crisis_days=int(cr.sum()),
        v1_alarms=int(al1.sum()),
        v2_alarms=int(al2.sum()),
        lead_time_v1=lead_v1,
        lead_time_v2=lead_v2,
        conf_veto_pct=v2["conf_info"]["veto_pct"],
        cb_suppress_pct=v2["cb_info"]["suppress_pct"],
        improvement=imp,
        channel_dominance=channel_dominance_weighted(ps, crisis_mask if crisis_mask.any() else np.ones(T, bool)),
    )
    def _j(o):
        if isinstance(o, np.ndarray): return o.tolist()
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        raise TypeError(type(o))
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2, default=_j)
    print(f"  JSON  → {OUT_JSON}")
    print("=" * 68)


if __name__ == "__main__":
    main()
