"""
domain_v2_information_flow.py
==============================
Domain III (REAL DATA v2) — Information Flow / Viral Cascade Detection.

Data source:  C:\\amttp\\data\\external_validation\\social\\wikipedia_pageviews_ai.json
              Wikipedia REST API pageviews for AI-related articles.
              Crisis event: ChatGPT launch (2022-11-30) → viral cascade.

v2 improvements over domain_real_social_media.py:
  * ConfidenceGate: veto alarm when rolling cross-article Pearson correlation
    < 0.47 (require synchronized surge across articles before firing)
  * DomainCircuitBreaker: after viral cascade detected (anomaly score +8%
    above rolling peak), suppress until correlation returns below 0.20

Engine:  STRICT LOCKED CANONICAL-v4 ODE  (canonical_v4_engine.py)
         Agents = articles (Wikipedia AI topic pages),
         features = log-pageviews daily timeseries.
"""
from __future__ import annotations
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canonical_v4_engine import FrozenCanonicalV4
from canonical_v4_paper_style import evaluate_paper_style, channel_dominance_weighted, first_alarm_lead
from domain_bsdt_gateway_v2 import run_v2_gateway, rolling_corr_mean

JSON_PATH = r"c:\amttp\data\external_validation\social\wikipedia_pageviews_ai.json"
OUTDIR    = r"c:\amttp\research\neural-stability\figures"
RESULTDIR = r"c:\amttp\research\neural-stability\results"
os.makedirs(OUTDIR, exist_ok=True); os.makedirs(RESULTDIR, exist_ok=True)
OUT_PNG   = os.path.join(OUTDIR,    "domain_v2_information_flow.png")
OUT_JSON  = os.path.join(RESULTDIR, "domain_v2_information_flow.json")

NAVY, GOLD, RUST, TEAL = "#1f3b73", "#c9a227", "#a23a1f", "#1a5f5f"
CRISIS_DATE   = "2022-11-30"   # ChatGPT launch
REF_DAYS      = 90             # 90-day pre-crisis reference
CB_WINDOW     = 60             # days


def load_wikipedia(json_path: str) -> tuple[np.ndarray, list[str], list[str]]:
    """
    Load Wikipedia pageviews JSON.
    Expected structure:
      {article_title: {date: views, ...}, ...}
    OR list of records with article/date/views.

    Returns:
        X       : (T, N) log-pageviews matrix
        dates   : list[str] YYYY-MM-DD
        articles: list[str]
    """
    with open(json_path, "r", encoding="utf-8-sig") as f:
        raw = json.load(f)

    def _ts_to_date(ts: str) -> str:
        """Convert Wikipedia API timestamp YYYYMMDDXX → YYYY-MM-DD."""
        s = ts[:8]
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else ts

    def _parse_records(records: list) -> "dict[str, dict[str, float]]":
        art_f  = next((k for k in ["article", "title", "page"] if k in records[0]), "article")
        date_f = next((k for k in ["timestamp", "date", "day"] if k in records[0]), "timestamp")
        view_f = next((k for k in ["views", "pageviews", "count"] if k in records[0]), "views")
        out: dict[str, dict[str, float]] = {}
        for rec in records:
            art = str(rec.get(art_f, "")).replace("_", " ")
            dt  = _ts_to_date(str(rec.get(date_f, "")))
            v   = float(rec.get(view_f, 0))
            out.setdefault(art, {})[dt] = v
        return out

    # Normalise to dict[str, dict[str, int]]
    if isinstance(raw, dict):
        if "items" in raw:
            # {"items": [flat records...]}
            data = _parse_records(raw["items"])
        else:
            # Could be {article: {date: views}} or {article: [records...]}
            first_val = next(iter(raw.values()))
            if isinstance(first_val, list):
                # {article: [records...]}  ← the actual Wikipedia API cache format
                data: dict[str, dict[str, float]] = {}
                for art_key, records in raw.items():
                    art_name = art_key.replace("_", " ")
                    for rec in records:
                        date_f = next((k for k in ["timestamp", "date", "day"] if k in rec), "timestamp")
                        view_f = next((k for k in ["views", "pageviews", "count"] if k in rec), "views")
                        dt = _ts_to_date(str(rec.get(date_f, "")))
                        v  = float(rec.get(view_f, 0))
                        data.setdefault(art_name, {})[dt] = v
            else:
                # {article: {date: views}}
                data = {art: {d: float(v) for d, v in dct.items()} for art, dct in raw.items()
                        if isinstance(dct, dict)}
    elif isinstance(raw, list):
        data = _parse_records(raw)
    else:
        raise ValueError(f"Unexpected JSON format: {type(raw)}")

    # Align dates across all articles
    all_dates = sorted({d for dct in data.values() for d in dct})
    articles  = sorted(data.keys())
    N_art = len(articles); T = len(all_dates)
    X_raw = np.zeros((T, N_art), dtype=float)
    for j, art in enumerate(articles):
        for i, d in enumerate(all_dates):
            X_raw[i, j] = data[art].get(d, 0.0)

    X = np.log1p(X_raw)
    return X, all_dates, articles


def main() -> None:
    print("=" * 68)
    print("  DOMAIN III v2 — Information Flow: Wikipedia AI pageviews")
    print("=" * 68)

    if not os.path.exists(JSON_PATH):
        print(f"  [ERROR] Wikipedia pageviews JSON not found: {JSON_PATH}")
        return

    print(f"  Loading {JSON_PATH} ...")
    X, dates, articles = load_wikipedia(JSON_PATH)
    T, N = X.shape
    print(f"  Shape: T={T} days, N={N} articles  dates={dates[0]}..{dates[-1]}")
    print(f"  Articles: {', '.join(articles[:5])} ...")

    # Crisis date index
    if CRISIS_DATE in dates:
        crisis_idx = dates.index(CRISIS_DATE)
    else:
        # Find nearest date
        crisis_idx = next((i for i, d in enumerate(dates) if d >= CRISIS_DATE), T//2)
    print(f"  Crisis date: {CRISIS_DATE} → index={crisis_idx}")

    # Reference: REF_DAYS before crisis
    ref_start = max(0, crisis_idx - REF_DAYS)
    ref_mask  = np.zeros(T, dtype=bool)
    ref_mask[ref_start:crisis_idx] = True
    if ref_mask.sum() < 10:
        ref_mask[:min(REF_DAYS, T//5)] = True   # fallback

    # Canonical v4
    engine = FrozenCanonicalV4(alpha_base=1.0)
    engine.fit(X[ref_mask])
    result = engine.evaluate(X)

    ps = evaluate_paper_style(engine, X, X[ref_mask])

    # Crisis mask: post-crisis surge
    crisis_mask = np.zeros(T, dtype=bool)
    crisis_mask[crisis_idx:] = True

    # Confidence gate signal: rolling cross-article correlation
    conf_signal = rolling_corr_mean(X, window=14)

    # v2 gateway  (resume_corr_below=0.20 hard-coded in gateway as 0.01 relative)
    v2 = run_v2_gateway(
        v1_alarms     = ps.alarms_paper,
        anomaly_score = result.score,
        conf_signal   = conf_signal,
        crisis_mask   = crisis_mask,
        conf_threshold= 0.47,
        halt_frac     = 0.08,
        resume_frac   = 0.01,
        cb_window     = CB_WINDOW,
    )

    _crisis_idx = int(np.argmax(crisis_mask)) if crisis_mask.any() else T
    lead_v1 = first_alarm_lead(ps.alarms_paper, _crisis_idx)
    lead_v2 = first_alarm_lead(v2["alarms_v2"],  _crisis_idx)
    imp     = v2.get("improvement", {})
    al1     = ps.alarms_paper.astype(bool)
    al2     = v2["alarms_v2"].astype(bool)
    print(f"\n  v1 alarms: {al1.sum()}  v2 alarms: {al2.sum()}")
    print(f"  Lead time  v1={lead_v1}d  v2={lead_v2}d")
    print(f"  Precision  v1={imp.get('v1',{}).get('precision',0):.3f}  "
          f"v2={imp.get('v2',{}).get('precision',0):.3f}")

    # ── Plot ──────────────────────────────────────────────────────────────────
    t = np.arange(T)
    mean_views = X.mean(axis=1)
    cr = crisis_mask.astype(bool)

    fig, axes = plt.subplots(3, 1, figsize=(15, 10), facecolor="white")

    ax = axes[0]
    for j in range(min(N, 8)):
        ax.plot(t, X[:, j], lw=0.6, alpha=0.5)
    ax.plot(t, mean_views, color=NAVY, lw=2.0, label="Mean log-views")
    ax.axvline(crisis_idx, color=RUST, lw=1.5, ls="--", label=f"ChatGPT launch {CRISIS_DATE}")
    ax.fill_between(t, 0, mean_views.max(), where=cr, color=RUST, alpha=0.08)
    ax.set_title("Wikipedia AI Article Pageviews (log-scale)", fontsize=10, fontweight="bold")
    ax.set_ylabel("log(1 + views)"); ax.legend(fontsize=8)
    step = max(1, T // 10)
    ax.set_xticks(t[::step])
    ax.set_xticklabels([dates[i] for i in range(0, T, step)], rotation=30, fontsize=7)

    ax = axes[1]
    ax.plot(t, result.score, color=TEAL, lw=1.4, label="Canonical V4 score")
    ax.scatter(t[al1], result.score[al1], color=GOLD, s=20, zorder=5, label=f"v1 alarms ({al1.sum()})")
    ax.scatter(t[al2], result.score[al2], color=NAVY, s=20, marker="^", zorder=6, label=f"v2 alarms ({al2.sum()})")
    ax.fill_between(t, 0, result.score.max()*1.1, where=cr, color=RUST, alpha=0.10)
    ax.axvline(crisis_idx, color=RUST, lw=1.5, ls="--")
    ax.set_title("Canonical V4 score + v2 gated alarms", fontsize=10, fontweight="bold")
    ax.set_ylabel("Anomaly score"); ax.legend(fontsize=8)
    ax.set_xticks(t[::step])
    ax.set_xticklabels([dates[i] for i in range(0, T, step)], rotation=30, fontsize=7)

    ax = axes[2]
    ax.plot(t, conf_signal, color=GOLD, lw=1.2, label="Cross-article correlation")
    ax.axhline(0.47, color=NAVY, ls="--", lw=1.0, label="Gate threshold (0.47)")
    cb_on  = np.array(v2["cb_info"].get("cb_halted", [False]*T), dtype=float)
    ax.fill_between(t, 0, 1, where=cb_on.astype(bool), color=RUST, alpha=0.25, label="CB halted")
    ax.fill_between(t, 0, 1, where=cr, color=TEAL, alpha=0.12, label="Crisis period")
    ax.axvline(crisis_idx, color=RUST, lw=1.5, ls="--")
    ax.set_title("Confidence gate signal & circuit breaker", fontsize=10, fontweight="bold")
    ax.set_xlabel("Day"); ax.set_ylim(-0.1, 1.2); ax.legend(fontsize=8)
    ax.set_xticks(t[::step])
    ax.set_xticklabels([dates[i] for i in range(0, T, step)], rotation=30, fontsize=7)

    fig.suptitle("Domain III v2 — Information Flow: Wikipedia AI Pageviews\n"
                 "FrozenCanonicalV4 + tbr0p47 ConfidenceGate + CB halt/resume",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.96])
    fig.savefig(OUT_PNG, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Figure → {OUT_PNG}")

    payload = dict(
        domain="information_flow",
        version="v2",
        engine="FrozenCanonicalV4",
        gateway="tbr0p47_ConfidenceGate + DomainCircuitBreaker",
        data_source="Wikipedia Pageviews REST API (AI articles)",
        T=T, N=N,
        articles=articles,
        date_range=[dates[0], dates[-1]],
        crisis_event=CRISIS_DATE,
        crisis_idx=crisis_idx,
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
