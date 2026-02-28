"""
crisis_analysis.py
==================
Crisis window definitions, lead-lag test, and benchmark comparisons.

Implements §8 of the paper:
  - Mark three crisis windows (2008 GFC, 2020 COVID, 2022-23 rate shock)
  - Compute peak-signal timing for our model vs STLFSI / VIX benchmarks
  - Lead-lag regression: lead(model signal, benchmark) → t-test
  - Output: Table 8.1 (lead time by window) and Figure 8.1 (trajectory plot)
"""

from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from scipy import stats as spstats

# ─────────────────────────────────────────────────────────────────────────────
# Crisis window definitions (quarter start / end, peak label)
# ─────────────────────────────────────────────────────────────────────────────
CRISIS_WINDOWS = {
    "GFC 2008":    ("2007-01-01", "2009-06-30", "2008-09-15"),   # Lehman
    "COVID 2020":  ("2019-10-01", "2021-03-31", "2020-03-31"),   # March trough
    "Rate Shock 2022": ("2022-01-01", "2023-06-30", "2022-10-31"),
}

OUTPUT_DIR = Path(__file__).parent / "results"


# ─────────────────────────────────────────────────────────────────────────────
# Lead-lag analysis helpers
# ─────────────────────────────────────────────────────────────────────────────

def cross_correlation(x: np.ndarray, y: np.ndarray,
                      max_lag: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute cross-correlation of x and y at lags -max_lag … +max_lag.
    Returns (lags, correlations).
    Positive lag = x leads y.
    """
    x = (x - x.mean()) / (x.std() + 1e-12)
    y = (y - y.mean()) / (y.std() + 1e-12)
    lags = np.arange(-max_lag, max_lag + 1)
    corrs = np.array([
        float(np.corrcoef(x[:len(x)-abs(k)], y[abs(k):])[0, 1])
        if k <= 0 else
        float(np.corrcoef(x[k:], y[:len(y)-k])[0, 1])
        for k in lags
    ])
    return lags, corrs


def peak_lead_quarters(model_signal: np.ndarray,
                       benchmark: np.ndarray,
                       dates: pd.DatetimeIndex,
                       window_start: str,
                       window_end: str) -> float:
    """
    Within [window_start, window_end]:
    Find peak quarter of model_signal and peak quarter of benchmark.
    Return model_peak_date − benchmark_peak_date in quarters (positive = model leads).
    """
    mask = (dates >= window_start) & (dates <= window_end)
    if mask.sum() < 2:
        return np.nan
    ms = model_signal[mask]
    bs = benchmark[mask]
    dt = dates[mask]

    model_peak_dt  = dt[np.argmax(ms)]
    bench_peak_dt  = dt[np.argmax(bs)]
    # Convert to quarters
    q_model = (model_peak_dt.year - 2000) * 4 + (model_peak_dt.month - 1) // 3
    q_bench = (bench_peak_dt.year - 2000) * 4 + (bench_peak_dt.month - 1) // 3
    return float(q_model - q_bench)    # positive = model leads


def granger_causality_test(
    predictor: np.ndarray,
    outcome: np.ndarray,
    max_lag: int = 6
) -> pd.DataFrame:
    """
    Simple Granger-causality: OLS regression of outcome on its own lags
    and on predictor lags.  Returns F-stat and p-value for each lag depth.
    """
    from statsmodels.tsa.stattools import grangercausalitytests
    data = np.column_stack([outcome, predictor])
    with pd.option_context("mode.chained_assignment", None):
        results = grangercausalitytests(data, maxlag=max_lag, verbose=False)
    rows = []
    for lag, res in results.items():
        f_stat = res[0]["ssr_ftest"][0]
        p_val  = res[0]["ssr_ftest"][1]
        rows.append({"lag_quarters": lag, "F_stat": round(f_stat, 3), "p_value": round(p_val, 4)})
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Main analysis function
# ─────────────────────────────────────────────────────────────────────────────

def run_crisis_analysis(
    stats: dict[str, np.ndarray],
    dates: pd.DatetimeIndex,
    fred_raw: pd.DataFrame,
    verbose: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Parameters
    ----------
    stats     : output of gravity_engine.analyse_trajectory()
    dates     : pd.DatetimeIndex, length T
    fred_raw  : raw (pre-standardised) FRED DataFrame indexed by quarter

    Returns
    -------
    lead_table  : DataFrame — lead time by crisis window
    granger_df  : DataFrame — Granger causality results
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    model_signal = stats["mfls"]           # primary detection signal
    energy       = stats["energy"]
    gamma_star   = stats["gamma_star"]
    above_cman   = stats["above_cman"]

    # Align benchmarks to same dates
    stlfsi   = _align(fred_raw.get("stlfsi",   pd.Series(dtype=float)), dates, fill=0.0)
    vix      = _align(fred_raw.get("vix",      pd.Series(dtype=float)), dates, fill=0.0)
    hy_sprd  = _align(fred_raw.get("hy_spread",pd.Series(dtype=float)), dates, fill=0.0)
    nfci     = _align(fred_raw.get("nfci",     pd.Series(dtype=float)), dates, fill=0.0)

    # Composite SRISK-like benchmark = mean rank of stlfsi + vix + hy_spread
    def _rank_norm(x):
        r = pd.Series(x).rank(pct=True).values
        return (r - r.mean()) / (r.std() + 1e-12)

    srisk_proxy = (_rank_norm(stlfsi) + _rank_norm(vix) + _rank_norm(hy_sprd)) / 3.0
    nfci_norm   = _rank_norm(nfci)

    # ── Lead table ──────────────────────────────────────────────────────────
    rows = []
    for window_name, (wstart, wend, _peak) in CRISIS_WINDOWS.items():
        for bench_name, bench in [("STLFSI", stlfsi),
                                   ("VIX",    vix),
                                   ("SRISK-proxy", srisk_proxy),
                                   ("NFCI",   nfci_norm)]:
            lead_q = peak_lead_quarters(model_signal, bench, dates, wstart, wend)
            rows.append({
                "Crisis":    window_name,
                "Benchmark": bench_name,
                "Lead (quarters)": round(lead_q, 1) if not np.isnan(lead_q) else "—",
            })
    lead_table = pd.DataFrame(rows)

    if verbose:
        print("\n===  Lead-Time Table  ===")
        print(lead_table.to_string(index=False))

    # ── Granger causality ──────────────────────────────────────────────────
    granger_df = granger_causality_test(model_signal, srisk_proxy, max_lag=6)

    if verbose:
        print("\n===  Granger Causality (model → SRISK-proxy)  ===")
        print(granger_df.to_string(index=False))

    # ── Cross-correlation plot  ────────────────────────────────────────────
    lags, corrs_stlfsi  = cross_correlation(model_signal, stlfsi, max_lag=8)
    lags, corrs_vix     = cross_correlation(model_signal, vix,    max_lag=8)
    lags, corrs_srisk   = cross_correlation(model_signal, srisk_proxy, max_lag=8)

    fig, axes = plt.subplots(3, 1, figsize=(12, 14))

    # Panel 1: Energy + MFLS trajectory with crisis bands
    ax = axes[0]
    ax.plot(dates, energy / (energy.max() + 1e-9), label="Normalised energy Φ(X)", lw=2, color="steelblue")
    ax.plot(dates, model_signal / (model_signal.max() + 1e-9), label="MFLS score", lw=2, color="darkorange", ls="--")
    _shade_crises(ax, dates)
    ax.set_ylabel("Normalised score"); ax.legend(loc="upper left"); ax.set_title("Panel A: GravityEngine Energy and MFLS Detection Signal")
    ax.axhline(0, color="k", lw=0.5)

    # Panel 2: gamma*(t) and spectral radius
    ax = axes[1]
    ax2 = ax.twinx()
    ax.plot(dates, gamma_star, label="γ*(t) adaptive coupling", lw=2, color="purple")
    ax2.plot(dates, stats["lambda_max"], label="λ_max(t)", lw=1.5, color="red", ls=":")
    ax2.axhline(ALPHA := 0.1, color="red", lw=0.8, ls="--", label=f"α={ALPHA} (critical threshold)")
    ax.set_ylabel("γ*(t)"); ax2.set_ylabel("λ_max", color="red")
    _shade_crises(ax, dates)
    handles1, lbls1 = ax.get_legend_handles_labels()
    handles2, lbls2 = ax2.get_legend_handles_labels()
    ax.legend(handles1 + handles2, lbls1 + lbls2, loc="upper left", fontsize=8)
    ax.set_title("Panel B: Adaptive Coupling γ*(t) and Spectral Radius λ_max(t)")

    # Panel 3: cross-correlation
    ax = axes[2]
    ax.bar(lags - 0.25, corrs_stlfsi, 0.25, label="vs STLFSI", color="steelblue", alpha=0.8)
    ax.bar(lags,         corrs_vix,   0.25, label="vs VIX",    color="darkorange", alpha=0.8)
    ax.bar(lags + 0.25,  corrs_srisk, 0.25, label="vs SRISK-proxy", color="green", alpha=0.8)
    ax.axvline(0, color="k", lw=0.5); ax.axhline(0, color="k", lw=0.5)
    ax.set_xlabel("Lag (quarters, positive = model leads)"); ax.set_ylabel("Cross-correlation")
    ax.set_title("Panel C: Cross-correlation of MFLS with Benchmark Stress Indices")
    ax.legend()

    plt.tight_layout()
    fig_path = OUTPUT_DIR / "crisis_analysis.pdf"
    plt.savefig(fig_path, bbox_inches="tight")
    plt.savefig(str(fig_path).replace(".pdf", ".png"), dpi=150, bbox_inches="tight")
    plt.close()
    if verbose:
        print(f"\n[plot] Saved: {fig_path}")

    return lead_table, granger_df


def _align(series: pd.Series | float, dates: pd.DatetimeIndex, fill: float = 0.0) -> np.ndarray:
    """Reindex a FRED series to pipeline dates, forward-fill, return np.ndarray."""
    if not isinstance(series, pd.Series) or series.empty:
        return np.full(len(dates), fill)
    series.index = pd.to_datetime(series.index)
    aligned = series.reindex(dates, method="ffill").fillna(fill)
    return aligned.values


def _shade_crises(ax: plt.Axes, dates: pd.DatetimeIndex) -> None:
    colours = ["#FFB3B3", "#B3FFB3", "#B3D9FF"]
    for (name, (wstart, wend, _)), c in zip(CRISIS_WINDOWS.items(), colours):
        mask = (dates >= wstart) & (dates <= wend)
        if mask.any():
            ax.axvspan(dates[mask][0], dates[mask][-1], alpha=0.25, color=c, label=name)


# ─────────────────────────────────────────────────────────────────────────────
# LaTeX table generator for §8
# ─────────────────────────────────────────────────────────────────────────────

def latex_lead_table(lead_table: pd.DataFrame) -> str:
    """Generate the LaTeX table for §8 (Table 8.1)."""
    lines = [
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{Lead time of MFLS detection signal versus benchmark stress indices "
        r"(quarters, positive = model peak precedes benchmark peak).}",
        r"\label{tab:lead_times}",
        r"\begin{tabular}{llr}",
        r"\toprule",
        r"Crisis Window & Benchmark & Lead (quarters) \\",
        r"\midrule",
    ]
    prev_crisis = None
    for _, row in lead_table.iterrows():
        crisis = row["Crisis"] if row["Crisis"] != prev_crisis else ""
        prev_crisis = row["Crisis"]
        lines.append(f"{crisis} & {row['Benchmark']} & {row['Lead (quarters)']} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def latex_granger_table(granger_df: pd.DataFrame) -> str:
    """Generate the LaTeX table for §8 (Table 8.2)."""
    lines = [
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{Granger causality: MFLS $\to$ SRISK-proxy. "
        r"$H_0$: MFLS does not Granger-cause the composite stress index.}",
        r"\label{tab:granger}",
        r"\begin{tabular}{rrr}",
        r"\toprule",
        r"Lag (quarters) & F-stat & $p$-value \\",
        r"\midrule",
    ]
    for _, row in granger_df.iterrows():
        sig = r"$^{**}$" if row["p_value"] < 0.01 else (r"$^{*}$" if row["p_value"] < 0.05 else "")
        lines.append(f"{int(row['lag_quarters'])} & {row['F_stat']:.3f} & {row['p_value']:.4f}{sig} \\\\")
    lines += [
        r"\midrule",
        r"\multicolumn{3}{l}{\footnotesize $^{*}p<0.05$, $^{**}p<0.01$.} \\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]
    return "\n".join(lines)
