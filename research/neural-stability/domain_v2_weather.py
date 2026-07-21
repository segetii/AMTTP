"""
domain_v2_weather.py
====================
Domain IV (REAL DATA v2) — Climate / Weather: NASA GISTEMP temperature anomaly.

Data source:  C:\\amttp\\data\\external_validation\\climate\\gistemp_GLB_TsdSST.csv
              NASA GISS Surface Temperature Analysis (GISTEMP v4)
              Monthly global mean surface temperature anomaly relative to
              1951-1980 base period  (°C)

Crisis ground truth:  post-2000 accelerating warming trend.
                      Annual anomaly > 0.5 °C (IPCC "significant" threshold).

v2 improvements over domain_real_climate.py:
  * ConfidenceGate: veto alarm when 12-month rolling slope of temperature
    anomaly < 0.47th percentile of historical slopes (only fire when trend
    is actively worsening, not during plateau)
  * DomainCircuitBreaker: suppress alarms when anomaly score surges +8%
    above rolling 180-month peak, until relative recovery within 1%

Engine:  STRICT LOCKED CANONICAL-v4 ODE  (canonical_v4_engine.py)
         T = months, agents = 12 rolling climate features derived from
         anomaly time-series (lags, seasonal decomposition, etc.)
"""
from __future__ import annotations
import json, os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canonical_v4_engine import FrozenCanonicalV4
from canonical_v4_paper_style import evaluate_paper_style, channel_dominance_weighted, first_alarm_lead
from domain_bsdt_gateway_v2 import run_v2_gateway, percentile_rank_norm

CSV_PATH  = r"c:\amttp\data\external_validation\climate\gistemp_GLB_TsdSST.csv"
OUTDIR    = r"c:\amttp\research\neural-stability\figures"
RESULTDIR = r"c:\amttp\research\neural-stability\results"
os.makedirs(OUTDIR, exist_ok=True); os.makedirs(RESULTDIR, exist_ok=True)
OUT_PNG   = os.path.join(OUTDIR,    "domain_v2_weather.png")
OUT_JSON  = os.path.join(RESULTDIR, "domain_v2_weather.json")

NAVY, GOLD, RUST, TEAL = "#1f3b73", "#c9a227", "#a23a1f", "#1a5f5f"
BASE_YEAR     = 1951     # GISTEMP base period start
BASE_END_YEAR = 1980     # GISTEMP base period end
CRISIS_YEAR   = 2000     # accelerating warming
CRISIS_THRESH = 0.5      # °C — crisis anomaly threshold
CB_WINDOW     = 180      # 180-month rolling max
SLOPE_WIN     = 12       # 12-month rolling slope for confidence signal


def load_gistemp(csv_path: str) -> tuple[np.ndarray, np.ndarray]:
    """
    Parse GISTEMP CSV.  Multiple layouts supported:
      1. Wide:  Year, Jan, Feb, ..., Dec   (one row per year)
      2. Long:  Year, Month, Anomaly
      3. Single 'Anomaly' column with DatetimeIndex

    Returns:
        anomaly  : (T,) np.float array monthly anomaly (°C)
        year_mon : (T,) float year fraction
    """
    df = pd.read_csv(csv_path, skiprows=1, na_values=["***", "****", "nan", ""])
    df.columns = df.columns.str.strip()

    # Layout 1: wide format with Year + month columns
    month_cols = [c for c in df.columns if c in [
        "Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec",
        "JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC",
        " Jan"," Feb"," Mar",
    ]]
    year_col = next((c for c in df.columns if c.strip().lower() in ["year","yr"]), None)

    if month_cols and year_col:
        month_cols = [c for c in month_cols if c in df.columns][:12]
        df2 = df[[year_col] + month_cols].dropna(subset=[year_col])
        years = df2[year_col].values.astype(int)
        months_data = df2[month_cols].values.astype(float)     # (n_years, 12)
        anomaly  = months_data.flatten()
        # Create year fractions
        ym = []
        for y in years:
            for m in range(1, 13):
                ym.append(y + (m - 0.5) / 12)
        year_mon = np.array(ym[:len(anomaly)])
    elif "Anomaly" in df.columns or "anomaly" in df.columns:
        a_col = "Anomaly" if "Anomaly" in df.columns else "anomaly"
        anomaly  = df[a_col].values.astype(float)
        if year_col:
            year_mon = df[year_col].values.astype(float)
        else:
            year_mon = np.arange(len(anomaly), dtype=float)
    else:
        # Try parsing first two numeric columns
        numeric = df.select_dtypes(include="number")
        if numeric.shape[1] >= 2:
            year_mon = numeric.iloc[:, 0].values.astype(float)
            anomaly  = numeric.iloc[:, 1].values.astype(float)
        else:
            raise ValueError(f"Cannot parse GISTEMP CSV: {csv_path}")

    # Drop NaN
    mask     = ~np.isnan(anomaly)
    anomaly  = anomaly[mask]
    year_mon = year_mon[mask]
    return anomaly, year_mon


def build_feature_matrix(anomaly: np.ndarray, year_mon: np.ndarray) -> np.ndarray:
    """
    Build (T, N_features) matrix from 1-D anomaly series.
    Features:
      0 anomaly_raw
      1 anomaly_12m_mean
      2 anomaly_12m_std
      3 12m_slope
      4 anomaly_lag1
      5 anomaly_lag3
      6 anomaly_lag6
      7 anomaly_lag12
      8 annual_max
      9 annual_min
     10 deviation_from_base (relative to 1951-1980 base)
     11 seasonal_deviation (departure from that month's climatology)
    """
    T = len(anomaly)
    base_mean = np.nanmean(anomaly[(year_mon >= BASE_YEAR) & (year_mon <= BASE_END_YEAR)])

    def roll_mean(a, w): return np.array([a[max(0,i-w):i+1].mean() for i in range(T)])
    def roll_std(a, w):  return np.array([a[max(0,i-w):i+1].std()+1e-8 for i in range(T)])
    def roll_slope(a, w):
        slopes = np.zeros(T)
        for i in range(w, T):
            x_ = np.arange(w, dtype=float)
            slopes[i] = np.polyfit(x_, a[i-w:i], 1)[0]
        return slopes
    def lag(a, k): return np.concatenate([np.full(k, a[0]), a[:-k]])

    # Monthly climatology (mean per calendar month over entire series)
    m_idx = (np.round((year_mon % 1.0) * 12)).astype(int) % 12
    month_clim = np.array([anomaly[m_idx == m].mean() for m in range(12)])
    seasonal_dev = anomaly - month_clim[m_idx]

    ann_max = roll_mean(anomaly, 12)    # approximate annual extremes
    ann_min = roll_std(anomaly, 12) * -1

    X = np.stack([
        anomaly,
        roll_mean(anomaly, 12),
        roll_std(anomaly, 12),
        roll_slope(anomaly, SLOPE_WIN),
        lag(anomaly, 1),
        lag(anomaly, 3),
        lag(anomaly, 6),
        lag(anomaly, 12),
        ann_max,
        ann_min,
        anomaly - base_mean,
        seasonal_dev,
    ], axis=1)   # (T, 12)
    return X


def compute_slope_signal(anomaly: np.ndarray, year_mon: np.ndarray) -> np.ndarray:
    """
    Confidence gate signal: 12-month rolling slope (trend acceleration).
    Normalise to [0,1] via percentile_rank_norm.
    """
    T = len(anomaly)
    slopes = np.zeros(T)
    for i in range(SLOPE_WIN, T):
        x_ = np.arange(SLOPE_WIN, dtype=float)
        slopes[i] = np.polyfit(x_, anomaly[i-SLOPE_WIN:i], 1)[0]
    return percentile_rank_norm(slopes, window=60)


def main() -> None:
    print("=" * 68)
    print("  DOMAIN IV v2 — Weather / Climate: NASA GISTEMP")
    print("=" * 68)

    if not os.path.exists(CSV_PATH):
        print(f"  [ERROR] GISTEMP CSV not found: {CSV_PATH}")
        return

    print(f"  Loading {CSV_PATH} ...")
    anomaly, year_mon = load_gistemp(CSV_PATH)
    T = len(anomaly)
    print(f"  T={T} months  year_range=[{year_mon.min():.1f}, {year_mon.max():.1f}]")
    print(f"  Anomaly: mean={anomaly.mean():.3f}  max={anomaly.max():.3f}°C")

    X = build_feature_matrix(anomaly, year_mon)

    # Reference: base period 1951-1980
    ref_mask = (year_mon >= BASE_YEAR) & (year_mon <= BASE_END_YEAR)
    if ref_mask.sum() < 20:
        ref_mask = np.zeros(T, dtype=bool)
        ref_mask[:T//5] = True
    print(f"  Reference window: {ref_mask.sum()} months ({BASE_YEAR}-{BASE_END_YEAR})")

    engine = FrozenCanonicalV4(alpha_base=1.0)
    engine.fit(X[ref_mask])
    result = engine.evaluate(X)

    ps = evaluate_paper_style(engine, X, X[ref_mask])

    # Crisis mask: post-CRISIS_YEAR with anomaly > CRISIS_THRESH
    crisis_mask = (year_mon >= CRISIS_YEAR) & (anomaly > CRISIS_THRESH)

    # Confidence signal: rolling slope of anomaly
    conf_signal = compute_slope_signal(anomaly, year_mon)

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
    print(f"  Lead time  v1={lead_v1}mo  v2={lead_v2}mo")
    print(f"  Precision  v1={imp.get('v1',{}).get('precision',0):.3f}  "
          f"v2={imp.get('v2',{}).get('precision',0):.3f}")

    # ── Plot ──────────────────────────────────────────────────────────────────
    t   = year_mon
    cr  = crisis_mask.astype(bool)

    fig, axes = plt.subplots(3, 1, figsize=(15, 10), facecolor="white")

    ax = axes[0]
    ax.fill_between(t, 0, anomaly, where=anomaly > 0, color=RUST, alpha=0.6, label="Warm anomaly")
    ax.fill_between(t, anomaly, 0, where=anomaly < 0, color=TEAL, alpha=0.5, label="Cool anomaly")
    ax.axhline(CRISIS_THRESH, color=RUST, ls="--", lw=1.2, label=f"Crisis threshold {CRISIS_THRESH}°C")
    ax.axvline(CRISIS_YEAR,   color=NAVY, ls="--", lw=1.2, label=f"{CRISIS_YEAR} crisis onset")
    ax.set_title("NASA GISTEMP Monthly Temperature Anomaly (vs 1951-1980)", fontsize=10, fontweight="bold")
    ax.set_ylabel("°C anomaly"); ax.legend(fontsize=8)

    ax = axes[1]
    ax.plot(t, result.score, color=TEAL, lw=1.4, label="Canonical V4 score")
    ax.scatter(t[al1], result.score[al1], color=GOLD, s=20, zorder=5, label=f"v1 alarms ({al1.sum()})")
    ax.scatter(t[al2], result.score[al2], color=NAVY, s=20, marker="^", zorder=6, label=f"v2 alarms ({al2.sum()})")
    ax.fill_between(t, 0, result.score.max()*1.1, where=cr, color=RUST, alpha=0.10)
    ax.set_title("Canonical V4 score + v2 gated alarms", fontsize=10, fontweight="bold")
    ax.set_ylabel("Anomaly score"); ax.legend(fontsize=8)

    ax = axes[2]
    ax.plot(t, conf_signal, color=GOLD, lw=1.2, label="Slope percentile rank")
    ax.axhline(0.47, color=NAVY, ls="--", lw=1.0, label="Gate threshold (0.47)")
    cb_on = np.array(v2["cb_info"].get("cb_halted", [False]*T), dtype=float)
    ax.fill_between(t, 0, 1, where=cb_on.astype(bool), color=RUST, alpha=0.25, label="CB halted")
    ax.fill_between(t, 0, 1, where=cr, color=TEAL, alpha=0.12, label="Crisis")
    ax.set_title("Confidence gate signal & circuit breaker", fontsize=10, fontweight="bold")
    ax.set_xlabel("Year"); ax.set_ylim(-0.05, 1.15); ax.legend(fontsize=8)

    for ax in axes:
        ax.set_xlim(t.min(), t.max())

    fig.suptitle("Domain IV v2 — Climate / Weather: NASA GISTEMP\n"
                 "FrozenCanonicalV4 + tbr0p47 ConfidenceGate + CB halt/resume",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.96])
    fig.savefig(OUT_PNG, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Figure → {OUT_PNG}")

    payload = dict(
        domain="climate_weather",
        version="v2",
        engine="FrozenCanonicalV4",
        gateway="tbr0p47_ConfidenceGate + DomainCircuitBreaker",
        data_source="NASA GISTEMP v4 (GLB.Ts+dSST)",
        T=T,
        year_range=[float(year_mon.min()), float(year_mon.max())],
        base_period=[BASE_YEAR, BASE_END_YEAR],
        crisis_year=CRISIS_YEAR,
        crisis_months=int(crisis_mask.sum()),
        v1_alarms=int(al1.sum()),
        v2_alarms=int(al2.sum()),
        lead_time_v1=lead_v1,
        lead_time_v2=lead_v2,
        conf_veto_pct=v2["conf_info"]["veto_pct"],
        cb_suppress_pct=v2["cb_info"]["suppress_pct"],
        improvement=imp,
        channel_dominance=channel_dominance_weighted(ps, crisis_mask if crisis_mask.any() else np.ones(T, bool)),
        mean_anomaly=float(anomaly.mean()),
        max_anomaly=float(anomaly.max()),
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
