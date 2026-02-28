"""
run_variants.py - Compare MFLS Scoring Variants on Real FDIC Data
==================================================================

Runs 5 MFLS scoring variants on the same FDIC call-report panel:

    1. Baseline      - Mahalanobis gradient norm (current pipeline)
    2. Full BSDT     - 4-channel uniform-weighted (?_C + ?_G + ?_A + ?_T)
    3. QuadSurf      - degree-2 polynomial + ridge on BSDT channels
    4. Signed LR     - logistic regression on BSDT channels
    5. Expo Gate     - quadratic + tanh saturation + sigmoid gate

For each variant, computes:
    - Lead times vs STLFSI/VIX/NFCI/SRISK-proxy
    - Granger causality (MFLS -> SRISK-proxy)
    - OOS backtest (train ? 2006, test 2007-2009)
    - Bootstrap CIs on lead times

All variants use the same FDIC data (T=140, N=7, d=6) - the only
difference is how the detection signal is computed.

Usage
-----
    python run_variants.py [--no-cache] [--fast]
"""

from __future__ import annotations
import sys, json, time, argparse
import numpy as np
import pandas as pd
from pathlib import Path

# Import from the upgraded pipeline (reuse data loading)
UPGRADED_DIR = Path(__file__).parent.parent / "upgraded"
sys.path.insert(0, str(UPGRADED_DIR))
sys.path.insert(0, str(Path(__file__).parent))

from fred_loader     import fetch_all
from fdic_loader     import fetch_fdic_specgrp
from state_matrix    import build_state_matrix_fdic, standardise_panel, get_normal_period
from network_builder import lw_correlation_network, spectral_radius as net_spectral_radius, describe_network
from crisis_analysis import CRISIS_WINDOWS, bootstrap_lead_ci

# Local modules
from bsdt_operators  import BSDTOperators
from mfls_variants   import (MFLSBaseline, MFLSFullBSDT, MFLSQuadSurf,
                              MFLSSignedLR, MFLSExpoGate, make_crisis_labels)

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

ALPHA = 0.10


# ?????????????????????????????????????????????????????????????????????????????
# Helpers (reused from run_pipeline.py)
# ?????????????????????????????????????????????????????????????????????????????

def _reindex(series, dates, fill=0.0):
    if series is None or (isinstance(series, pd.Series) and series.empty):
        return np.full(len(dates), fill)
    s = series.copy()
    s.index = pd.to_datetime(s.index)
    return s.reindex(dates, method="ffill").fillna(fill).values


def _build_srisk_proxy(raw_fred, dates):
    def _rn(x):
        r = pd.Series(x).rank(pct=True).values
        return (r - r.mean()) / (r.std() + 1e-12)
    stlfsi = _reindex(raw_fred.get("stlfsi"), dates)
    vix    = _reindex(raw_fred.get("vix"),    dates)
    hy     = _reindex(raw_fred.get("hy_spread"), dates)
    return (_rn(stlfsi) + _rn(vix) + _rn(hy)) / 3.0


def _lead_time(mfls_signal, bench_signal, dates, crisis_start, crisis_end):
    """Peak lead time: how many quarters MFLS peak precedes benchmark peak."""
    mask = (dates >= crisis_start) & (dates <= crisis_end)
    if not mask.any():
        return 0.0
    m_peak_idx = np.argmax(mfls_signal[mask])
    b_peak_idx = np.argmax(bench_signal[mask])
    return float(b_peak_idx - m_peak_idx)


def _granger_test(mfls_signal, target_signal, max_lag=6):
    """Granger causality: mfls -> target. Returns list of (lag, F, p)."""
    from statsmodels.tsa.stattools import grangercausalitytests
    import warnings
    data = np.column_stack([target_signal, mfls_signal])
    # Remove NaN/Inf
    valid = np.isfinite(data).all(axis=1)
    data = data[valid]
    results = []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            gc = grangercausalitytests(data, maxlag=max_lag, verbose=False)
        for lag in range(1, max_lag + 1):
            f_stat = gc[lag][0]["ssr_ftest"][0]
            p_val  = gc[lag][0]["ssr_ftest"][1]
            results.append({"lag": lag, "F": round(f_stat, 3), "p": round(p_val, 4)})
    except Exception as e:
        for lag in range(1, max_lag + 1):
            results.append({"lag": lag, "F": 0.0, "p": 1.0, "error": str(e)})
    return results


def _oos_backtest(mfls_signal, dates, train_end="2006-12-31",
                  crisis_start="2007-01-01", crisis_peak="2008-09-30"):
    """OOS backtest: train threshold on pre-2006 data, test alarm timing."""
    train_mask = dates <= train_end
    test_mask  = dates > train_end

    train_signal = mfls_signal[train_mask]
    test_signal  = mfls_signal[test_mask]
    test_dates   = dates[test_mask]

    if len(train_signal) == 0 or len(test_signal) == 0:
        return {"alarm_date": None, "alarm_lead_quarters": 0, "hit_rate": 0.0}

    threshold = float(np.percentile(train_signal, 75))

    above = test_signal > threshold
    crisis_mask = (test_dates >= crisis_start) & (test_dates <= crisis_peak)

    alarm_date = None
    alarm_lead = 0
    if above.any():
        first_alarm_idx = np.argmax(above)
        alarm_date = str(test_dates[first_alarm_idx].date())
        # Lead = quarters between alarm and crisis peak
        peak_dt = pd.Timestamp(crisis_peak)
        alarm_dt = test_dates[first_alarm_idx]
        alarm_lead = max(0, int((peak_dt - alarm_dt).days / 91))

    hit_rate = float(above[crisis_mask].mean()) if crisis_mask.any() else 0.0

    # False alarm rate in calm period (pre-crisis test)
    calm_mask = test_dates < crisis_start
    false_alarm_rate = float(above[calm_mask].mean()) if calm_mask.any() else None

    return {
        "threshold_p75": round(threshold, 4),
        "alarm_date": alarm_date,
        "alarm_lead_quarters": alarm_lead,
        "hit_rate": round(hit_rate, 4),
        "false_alarm_rate": round(false_alarm_rate, 4) if false_alarm_rate is not None else None,
    }


# ?????????????????????????????????????????????????????????????????????????????
# Main
# ?????????????????????????????????????????????????????????????????????????????

def main(use_cache=True, fast=False, verbose=True):
    t0 = time.perf_counter()
    Sep = "=" * 70
    print(Sep)
    print("  MFLS Variant Comparison - Real FDIC Call-Report Data")
    print("  5 variants ? same panel ? same metrics")
    print(Sep)

    # ?? 1. Load data (reuse from upgraded pipeline) ??
    print("\n[1/5] Loading FDIC + FRED data...")
    raw_fred = fetch_all(use_cache=use_cache, verbose=verbose)
    slope_col = "slope_10y2y" if "slope_10y2y" in raw_fred.columns else raw_fred.columns[0]
    fred_slope = raw_fred[slope_col].copy()

    fdic_df = fetch_fdic_specgrp(start="1990-01-01", end="2024-12-31",
                                  use_cache=use_cache, verbose=verbose)

    X_all, dates, sector_names = build_state_matrix_fdic(fdic_df, fred_slope)
    T, N, d = X_all.shape
    print(f"  Panel: T={T}, N={N}, d={d}  ({dates[0].date()} -> {dates[-1].date()})")

    # Normal period + standardise
    X_normal, dates_normal = get_normal_period(X_all, dates)
    X_std, _, _ = standardise_panel(X_all, X_ref=X_normal)
    X_norm_std, _, _ = standardise_panel(X_normal, X_ref=X_normal)
    print(f"  Normal: {dates_normal[0].date()} -> {dates_normal[-1].date()} ({len(dates_normal)}Q)")

    # Benchmark stress indices
    raw_aligned = raw_fred.copy()
    raw_aligned.index = pd.to_datetime(raw_aligned.index)

    stlfsi = _reindex(raw_fred.get("stlfsi"), dates)
    vix    = _reindex(raw_fred.get("vix"), dates)
    nfci   = _reindex(raw_fred.get("nfci"), dates)
    srisk  = _build_srisk_proxy(raw_fred, dates)

    benchmarks = {"STLFSI": stlfsi, "VIX": vix, "NFCI": nfci, "SRISK-proxy": srisk}

    # Crisis labels for supervised variants
    y_labels = make_crisis_labels(dates)
    print(f"  Crisis quarters: {y_labels.sum()}/{len(y_labels)}")

    # ?? 2. Compute BSDT channels ??
    print("\n[2/5] Computing BSDT operators (?_C, ?_G, ?_A, ?_T)...")
    ops = BSDTOperators(n_components=4, velocity_pctl=95.0)
    ops.fit(X_norm_std)
    channels = ops.compute_channels(X_std, verbose=verbose)
    ch = channels["channels"]  # (T, 4)
    print(f"  Channel correlations:")
    ch_names = ["?_C (Camouflage)", "?_G (Feature Gap)", "?_A (Activity)", "?_T (Temporal)"]
    for k, name in enumerate(ch_names):
        corr_srisk = float(np.corrcoef(ch[:, k], srisk)[0, 1])
        print(f"    {name:25s}: mean={ch[:, k].mean():.2f}  "
              f"std={ch[:, k].std():.2f}  corr(SRISK)={corr_srisk:+.3f}")

    # ?? 3. Run all variants ??
    print("\n[3/5] Running 5 MFLS variants...")

    # Train/test split for supervised variants
    train_mask = dates <= "2006-12-31"
    ch_train = ch[train_mask]
    y_train  = y_labels[train_mask]

    variant_results = {}

    # --- Variant 1: Baseline ---
    print("\n  --- Variant 1: Baseline (Mahalanobis gradient norm) ---")
    v1 = MFLSBaseline()
    v1.fit(X_norm_std)
    sig1 = v1.score_series(X_std)
    variant_results["baseline"] = {"signal": sig1, "name": v1.name}
    print(f"    Signal range: [{sig1.min():.2f}, {sig1.max():.2f}]")

    # --- Variant 2: Full BSDT ---
    print("\n  --- Variant 2: Full BSDT (4-channel uniform) ---")
    v2 = MFLSFullBSDT()
    v2.fit(ch_train)
    sig2 = v2.score(ch)
    variant_results["full_bsdt"] = {"signal": sig2, "name": v2.name}
    print(f"    Signal range: [{sig2.min():.2f}, {sig2.max():.2f}]")

    # --- Variant 3: QuadSurf ---
    print("\n  --- Variant 3: QuadSurf (polynomial ridge) ---")
    v3 = MFLSQuadSurf(ridge_alpha=1.0)
    v3.fit(ch_train, y_train)
    sig3 = v3.score(ch)
    variant_results["quadsurf"] = {"signal": sig3, "name": v3.name}
    print(f"    Signal range: [{sig3.min():.2f}, {sig3.max():.2f}]")
    # Print learned coefficients
    if v3.beta_ is not None:
        print(f"    Beta (top 5): {np.sort(np.abs(v3.beta_))[-5:][::-1].round(4)}")

    # --- Variant 4: Signed LR ---
    print("\n  --- Variant 4: Signed LR (logistic regression) ---")
    v4 = MFLSSignedLR(lr=0.1, n_iter=1000, reg=0.01)
    v4.fit(ch_train, y_train)
    sig4 = v4.score(ch)
    variant_results["signed_lr"] = {"signal": sig4, "name": v4.name}
    print(f"    Signal range: [{sig4.min():.4f}, {sig4.max():.4f}]")
    if v4.beta_ is not None:
        labels = ["bias", "?_C", "?_G", "?_A", "?_T"]
        for i, (lbl, b) in enumerate(zip(labels, v4.beta_)):
            print(f"    beta_{lbl} = {b:+.4f}")

    # --- Variant 5: Expo Gate ---
    print("\n  --- Variant 5: Expo Gate (quad + tanh + sigmoid) ---")
    v5 = MFLSExpoGate(ridge_alpha=1.0, smooth_sigma=1.0, gate_scale=3.0)
    v5.fit(ch_train, y_train)
    sig5 = v5.score(ch)
    variant_results["expo_gate"] = {"signal": sig5, "name": v5.name}
    print(f"    Signal range: [{sig5.min():.4f}, {sig5.max():.4f}]")

    # ?? 4. Compare all variants ??
    print(f"\n[4/5] Comparing variants across all metrics...")
    print(f"\n{'='*70}")

    comparison = {}

    for vname, vdata in variant_results.items():
        sig = vdata["signal"]
        display_name = vdata["name"]
        print(f"\n  ? {display_name}")

        vresult = {"name": display_name}

        # Lead times
        lead_times = {}
        for crisis_name, (cs, ce, cp) in CRISIS_WINDOWS.items():
            for bname, bsig in benchmarks.items():
                lt = _lead_time(sig, bsig, dates, cs, ce)
                lead_times[f"{crisis_name}/{bname}"] = lt
        vresult["lead_times"] = lead_times

        # Print GFC leads
        gfc_leads = {k: v for k, v in lead_times.items() if "GFC" in k}
        print(f"    GFC leads: " + ", ".join(f"{k.split('/')[1]}={v:+.0f}Q" for k, v in gfc_leads.items()))

        # Granger
        granger = _granger_test(sig, srisk, max_lag=6)
        vresult["granger"] = granger
        best_granger = min(granger, key=lambda x: x["p"])
        print(f"    Granger best: lag={best_granger['lag']} F={best_granger['F']:.3f} p={best_granger['p']:.4f}")

        # OOS backtest
        oos = _oos_backtest(sig, dates)
        vresult["oos_backtest"] = oos
        print(f"    OOS: alarm={oos['alarm_date']}  lead={oos['alarm_lead_quarters']}Q  "
              f"hit={oos['hit_rate']:.1%}  FP={oos['false_alarm_rate']}")

        # Correlation with SRISK proxy
        corr = float(np.corrcoef(sig, srisk)[0, 1])
        vresult["corr_srisk"] = round(corr, 4)
        print(f"    Corr(MFLS, SRISK-proxy) = {corr:+.4f}")

        # Fraction of time above threshold in calm vs crisis
        p75 = np.percentile(sig[train_mask], 75)
        crisis_frac = float((sig[y_labels == 1] > p75).mean()) if (y_labels == 1).any() else 0
        calm_frac   = float((sig[y_labels == 0] > p75).mean()) if (y_labels == 0).any() else 0
        vresult["selectivity"] = {
            "crisis_above_p75": round(crisis_frac, 4),
            "calm_above_p75":   round(calm_frac, 4),
            "ratio": round(crisis_frac / (calm_frac + 1e-10), 2),
        }
        print(f"    Selectivity: crisis={crisis_frac:.1%} vs calm={calm_frac:.1%} "
              f"(ratio={crisis_frac / (calm_frac + 1e-10):.1f}x)")

        comparison[vname] = vresult

    # ?? 5. Summary table ??
    print(f"\n\n{'='*70}")
    print("  SUMMARY COMPARISON TABLE")
    print(f"{'='*70}")
    print(f"\n{'Variant':<35s} {'GFC Lead':<10s} {'Granger p':<11s} {'OOS Alarm':<12s} "
          f"{'Hit Rate':<10s} {'FP Rate':<10s} {'Select.':<8s}")
    print("-" * 96)

    for vname, vdata in comparison.items():
        name = vdata["name"][:34]
        # GFC lead vs STLFSI
        gfc_lead = vdata["lead_times"].get("GFC 2008/STLFSI", 0)
        # Best Granger p
        best_p = min(vdata["granger"], key=lambda x: x["p"])["p"]
        # OOS
        oos = vdata["oos_backtest"]
        alarm = oos["alarm_date"] or "none"
        hit = f"{oos['hit_rate']:.1%}"
        fp = f"{oos['false_alarm_rate']:.1%}" if oos["false_alarm_rate"] is not None else "n/a"
        # Selectivity
        sel = f"{vdata['selectivity']['ratio']:.1f}x"

        print(f"{name:<35s} {gfc_lead:>+6.0f}Q   {best_p:>9.4f}   {alarm:<12s} "
              f"{hit:<10s} {fp:<10s} {sel:<8s}")

    # ?? Save ??
    print(f"\n\n[5/5] Saving results...")
    out = {
        "data_source": "FDIC SDI call-report (real)",
        "T": T, "N": N, "d": d,
        "date_range": [str(dates[0].date()), str(dates[-1].date())],
        "normal_period": [str(dates_normal[0].date()), str(dates_normal[-1].date())],
        "crisis_quarters_used": int(y_labels.sum()),
        "channel_stats": {
            name: {
                "mean": round(float(ch[:, k].mean()), 4),
                "std": round(float(ch[:, k].std()), 4),
                "corr_srisk": round(float(np.corrcoef(ch[:, k], srisk)[0, 1]), 4),
            }
            for k, name in enumerate(ch_names)
        },
        "variants": {},
    }
    for vname, vdata in comparison.items():
        out["variants"][vname] = vdata

    with open(RESULTS_DIR / "variant_comparison.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"  Wrote: {RESULTS_DIR / 'variant_comparison.json'}")

    # ?? Plot ??
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(3, 1, figsize=(16, 14), sharex=True)

        # Panel A: All signals normalised
        ax = axes[0]
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
        for i, (vname, vdata) in enumerate(variant_results.items()):
            sig = vdata["signal"]
            sig_n = (sig - sig.min()) / (sig.max() - sig.min() + 1e-10)
            ax.plot(dates, sig_n, label=vdata["name"], lw=1.5, color=colors[i], alpha=0.8)
        # Crisis shading
        for cname, (cs, ce, cp) in CRISIS_WINDOWS.items():
            ax.axvspan(pd.Timestamp(cs), pd.Timestamp(ce), alpha=0.15, color="red")
        ax.set_ylabel("Normalised MFLS Score")
        ax.set_title("Panel A: MFLS Variant Signals (normalised to [0,1])")
        ax.legend(fontsize=8, loc="upper left")
        ax.grid(alpha=0.3)

        # Panel B: BSDT channels
        ax = axes[1]
        ch_colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
        for k in range(4):
            col = ch[:, k]
            col_n = (col - col.min()) / (col.max() - col.min() + 1e-10)
            ax.plot(dates, col_n, label=ch_names[k], lw=1.2, color=ch_colors[k])
        for cname, (cs, ce, cp) in CRISIS_WINDOWS.items():
            ax.axvspan(pd.Timestamp(cs), pd.Timestamp(ce), alpha=0.15, color="red")
        ax.set_ylabel("Normalised Channel Score")
        ax.set_title("Panel B: Individual BSDT Operator Channels")
        ax.legend(fontsize=8, loc="upper left")
        ax.grid(alpha=0.3)

        # Panel C: OOS backtest region highlighted
        ax = axes[2]
        ax.axvline(pd.Timestamp("2006-12-31"), color="black", ls="--", lw=1, label="Train/Test split")
        for i, (vname, vdata) in enumerate(variant_results.items()):
            sig = vdata["signal"]
            sig_n = (sig - sig.min()) / (sig.max() - sig.min() + 1e-10)
            test_mask_plot = dates > "2006-12-31"
            ax.plot(dates[test_mask_plot], sig_n[test_mask_plot],
                    label=vdata["name"], lw=1.5, color=colors[i], alpha=0.8)
        for cname, (cs, ce, cp) in CRISIS_WINDOWS.items():
            ax.axvspan(pd.Timestamp(cs), pd.Timestamp(ce), alpha=0.15, color="red")
        ax.set_ylabel("Normalised Score (OOS only)")
        ax.set_title("Panel C: Out-of-Sample Performance (post-2006)")
        ax.legend(fontsize=8, loc="upper left")
        ax.grid(alpha=0.3)

        plt.tight_layout()
        fig.savefig(RESULTS_DIR / "variant_comparison.pdf", dpi=150, bbox_inches="tight")
        fig.savefig(RESULTS_DIR / "variant_comparison.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Wrote: variant_comparison.pdf/png")
    except Exception as e:
        print(f"  [warn] Plot failed: {e}")

    elapsed = time.perf_counter() - t0
    print(f"\n{Sep}\n  Variant comparison complete in {elapsed:.1f}s\n{Sep}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--fast",     action="store_true")
    p.add_argument("--quiet",    action="store_true")
    a = p.parse_args()
    main(use_cache=not a.no_cache, fast=a.fast, verbose=not a.quiet)
