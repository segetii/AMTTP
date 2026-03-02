#!/usr/bin/env python3
"""
Global Multi-Region MFLS Analysis
==================================
Runs the full BSDT pipeline across US, UK, EU, Asia, and Africa (Nigeria),
producing per-region and global risk assessments.

Uses the MFLSEngine for proper calibration and scoring.
"""

import sys, os, json, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))

from mfls.engine import MFLSEngine
from mfls.core.bsdt import BSDTOperator, BSDTOperators
from mfls.core.network import lw_correlation_network
from mfls.data.loaders import build_gsib_panel, GSIB_CATALOGUE


def classify_regime(signal, threshold):
    if signal > threshold * 1.5:
        return "CRITICAL"
    elif signal > threshold:
        return "ELEVATED"
    elif signal > threshold * 0.7:
        return "WATCH"
    else:
        return "NORMAL"


def main():
    print("=" * 70)
    print("     GLOBAL MULTI-REGION MFLS ANALYSIS")
    print("     US | UK | EU | Asia | Africa (Nigeria)")
    print("=" * 70)

    # ── 1. BUILD GLOBAL PANEL ──
    print("\n[1/6] Building global G-SIB panel (25 institutions)...")
    panel_raw = build_gsib_panel(
        start="2003-01-01",
        end="2024-12-31",
        force_refresh=False,
        min_coverage=0.25,
        verbose=True,
    )

    X = panel_raw["X"]
    dates = panel_raw["dates"]
    meta = panel_raw["meta"]
    T, N, d = X.shape
    feature_names = panel_raw["feature_names"]

    print(f"\n  Panel shape: T={T} quarters, N={N} institutions, d={d} features")
    print(f"  Date range: {dates[0].strftime('%Y-%m-%d')} to {dates[-1].strftime('%Y-%m-%d')}")

    # Count by region
    regions_count = {}
    for m in meta:
        r = m["region"]
        regions_count[r] = regions_count.get(r, 0) + 1
    print(f"  By region: {regions_count}")
    print(f"  Institutions: {', '.join(m['name'] for m in meta)}")

    # ── 2. FIT ENGINE & SCORE ──
    print("\n[2/6] Fitting MFLS engine...")
    engine = MFLSEngine(
        normal_start="2003-01-01",
        normal_end="2006-12-31",
        n_boot=200,
        threshold_pctl=75.0,
    )

    names = [m["name"] for m in meta]
    panel = engine.load_custom_panel(
        X, dates, names, feature_names,
        normal_start="2003-01-01",
        normal_end="2006-12-31",
    )

    result = engine.fit_and_score(panel, verbose=True)

    # ── 3. GLOBAL SUMMARY ──
    print("\n[3/6] Global risk assessment...")
    sig = result.signal
    threshold = result.threshold
    current_signal = sig[-1]
    z = (current_signal - np.mean(sig[1:])) / np.std(sig[1:]) if np.std(sig[1:]) > 0 else 0
    regime = classify_regime(current_signal, threshold)

    print(f"\n  {'='*55}")
    print(f"  GLOBAL RISK ASSESSMENT (N={N} institutions)")
    print(f"  {'='*55}")
    print(f"  Current signal:   {current_signal:.4f}")
    print(f"  Threshold:        {threshold:.4f}")
    print(f"  Z-score:          {z:+.2f}s")
    print(f"  Regime:           {regime}")
    print(f"  AUROC:            {result.auroc:.4f}" if result.auroc else "  AUROC:            N/A")
    if result.auroc_ci:
        print(f"  95% CI:           [{result.auroc_ci[0]:.4f}, {result.auroc_ci[1]:.4f}]")
    print(f"  Spectral radius:  {result.spectral_radius:.4f}")
    print(f"  Peak CCyB:        {result.peak_ccyb:.0f} bps")

    # BSDT channel decomposition
    if result.bsdt_channels is not None:
        ch = result.bsdt_channels
        print(f"\n  Channel composition (latest):")
        for ch_name, ch_series in [
            ("d_C (Credit)", ch.delta_C),
            ("d_G (Gravity)", ch.delta_G),
            ("d_A (Adaptive)", ch.delta_A),
            ("d_T (Temporal)", ch.delta_T),
        ]:
            if ch_series is not None:
                print(f"    {ch_name}:  {ch_series[-1]:.4f}")

    # ── 4. PER-REGION ANALYSIS ──
    print(f"\n[4/6] Per-region breakdown...")
    region_names = sorted(set(m["region"] for m in meta))
    region_results = {}

    for region in region_names:
        idx = [i for i, m in enumerate(meta) if m["region"] == region]
        if len(idx) < 1:
            continue
        X_r = X[:, idx, :]
        names_r = [meta[i]["name"] for i in idx]

        # Fit a separate engine for this region
        try:
            eng_r = MFLSEngine(
                normal_start="2003-01-01",
                normal_end="2006-12-31",
                n_boot=100,
                threshold_pctl=75.0,
            )
            panel_r = eng_r.load_custom_panel(
                X_r, dates, names_r, feature_names,
                normal_start="2003-01-01",
                normal_end="2006-12-31",
            )
            result_r = eng_r.fit_and_score(panel_r, verbose=False)
            region_results[region] = {
                "n_banks": len(idx),
                "signal": result_r.signal,
                "current_signal": float(result_r.signal[-1]),
                "threshold": float(result_r.threshold),
                "auroc": result_r.auroc,
                "regime": classify_regime(result_r.signal[-1], result_r.threshold),
                "z_score": float(
                    (result_r.signal[-1] - np.mean(result_r.signal[1:]))
                    / np.std(result_r.signal[1:])
                ) if np.std(result_r.signal[1:]) > 0 else 0.0,
                "spectral_radius": result_r.spectral_radius,
                "peak_ccyb": float(result_r.peak_ccyb),
                "names": names_r,
            }
        except Exception as e:
            print(f"  {region}: FAILED - {e}")
            region_results[region] = {
                "n_banks": len(idx), "regime": "ERROR",
                "current_signal": 0, "threshold": 0, "z_score": 0,
                "auroc": None, "spectral_radius": 0, "peak_ccyb": 0,
                "names": names_r,
            }

    print(f"\n  {'Region':<10} {'N':>3} {'Signal':>10} {'Threshold':>10} {'Z-score':>10} {'Regime':<12} {'AUROC':>8}")
    print(f"  {'-'*70}")
    for region in region_names:
        r = region_results[region]
        auroc_str = f"{r['auroc']:.4f}" if r.get('auroc') else "N/A"
        print(f"  {region:<10} {r['n_banks']:>3} {r['current_signal']:>10.4f} {r['threshold']:>10.4f} {r['z_score']:>+10.2f}s {r['regime']:<12} {auroc_str:>8}")

    # ── 5. INSTITUTION RANKINGS ──
    print(f"\n[5/6] Institution-level risk ranking...")

    # Per-institution deviation at latest time step
    audit = engine.bsdt_audit(panel, t=-1)
    inst_data = []
    for i in range(N):
        inst_data.append({
            "name": meta[i]["name"],
            "region": meta[i]["region"],
            "score": float(audit.total_score[i]),
            "dominant": audit.dominant_channel[i] if hasattr(audit, 'dominant_channel') else "N/A",
        })
    # Sort by score
    inst_data.sort(key=lambda x: -x["score"])
    scores_list = [d["score"] for d in inst_data]
    mu_s, sigma_s = np.mean(scores_list), np.std(scores_list)

    print(f"\n  {'Rank':>4} {'Institution':<22} {'Region':<8} {'Deviation':>10} {'Z-score':>10} {'Dominant':<8}")
    print(f"  {'-'*68}")
    for i, d in enumerate(inst_data):
        z_i = (d["score"] - mu_s) / sigma_s if sigma_s > 0 else 0
        d["z_score"] = z_i
        marker = " !!" if z_i > 1.5 else ""
        print(f"  {i+1:>4} {d['name']:<22} {d['region']:<8} {d['score']:>10.4f} {z_i:>+10.2f}s {d['dominant']:<8}{marker}")

    # ── 6. CRISIS WINDOW ANALYSIS ──
    print(f"\n[6/6] Historical crisis window performance...")
    crisis_windows = {
        "GFC Build-up (2006-07)": ("2006-01-01", "2007-06-30"),
        "GFC Peak (2007-09)":     ("2007-07-01", "2009-03-31"),
        "Euro Debt (2010-12)":    ("2010-01-01", "2012-12-31"),
        "China Stress (2015-16)": ("2015-04-01", "2016-03-31"),
        "COVID-19 (2020)":        ("2020-01-01", "2020-09-30"),
        "Rate Shock (2022-23)":   ("2022-01-01", "2023-06-30"),
        "Current (2024)":         ("2024-01-01", "2024-12-31"),
    }

    print(f"\n  {'Window':<30} {'Mean Sig':>10} {'Max Sig':>10} {'CCyB max':>10}")
    print(f"  {'-'*65}")
    for label, (start, end) in crisis_windows.items():
        mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
        if mask.sum() == 0:
            continue
        s_w = sig[mask]
        ccyb_w = result.ccyb_bps[mask] if result.ccyb_bps is not None else np.array([0])
        print(f"  {label:<30} {np.mean(s_w):>10.4f} {np.max(s_w):>10.4f} {np.max(ccyb_w):>10.0f} bps")

    # ── EXECUTIVE SUMMARY ──
    print(f"\n{'='*70}")
    print(f"  EXECUTIVE SUMMARY - GLOBAL MFLS")
    print(f"{'='*70}")
    print(f"  Assessment date:    {dates[-1].strftime('%Y-%m-%d')}")
    print(f"  Total institutions: {N} across {len(region_names)} regions ({', '.join(region_names)})")
    print(f"  Global signal:      {current_signal:.4f} (threshold {threshold:.4f})")
    print(f"  Global regime:      {regime}")
    if result.auroc:
        print(f"  Global AUROC:       {result.auroc:.4f}")
    if result.auroc_ci:
        print(f"  Global 95% CI:      [{result.auroc_ci[0]:.4f}, {result.auroc_ci[1]:.4f}]")
    print()

    # Regional ranking
    print(f"  Regional risk ranking:")
    ranked = sorted(
        [(r, region_results[r]) for r in region_names if r in region_results],
        key=lambda x: -x[1]["current_signal"]
    )
    for i, (region, r) in enumerate(ranked):
        auroc_str = f", AUROC={r['auroc']:.3f}" if r.get('auroc') else ""
        print(f"    {i+1}. {region:<10} - {r['regime']:<10} (signal={r['current_signal']:.4f}, Z={r['z_score']:+.2f}s, N={r['n_banks']}{auroc_str})")
    print()

    # Top outliers
    outliers = [d for d in inst_data if d.get("z_score", 0) > 1.0]
    if outliers:
        print(f"  Outlier institutions (Z > +1.0s):")
        for d in outliers:
            print(f"    - {d['name']} ({d['region']}): Z={d['z_score']:+.2f}s, dominant={d['dominant']}")
    else:
        print(f"  No outlier institutions (all within +/-1.0s)")
    print()

    # Save results
    results_out = {
        "timestamp": pd.Timestamp.now().isoformat(),
        "global": {
            "n_institutions": int(N),
            "n_quarters": int(T),
            "current_signal": float(current_signal),
            "threshold": float(threshold),
            "z_score": float(z),
            "regime": regime,
            "auroc": float(result.auroc) if result.auroc else None,
            "auroc_ci": list(result.auroc_ci) if result.auroc_ci else None,
            "spectral_radius": float(result.spectral_radius),
            "peak_ccyb_bps": float(result.peak_ccyb),
        },
        "regions": {
            region: {
                "n_banks": r["n_banks"],
                "signal": r["current_signal"],
                "threshold": r["threshold"],
                "z_score": r["z_score"],
                "regime": r["regime"],
                "auroc": float(r["auroc"]) if r.get("auroc") else None,
                "banks": r["names"],
            }
            for region, r in region_results.items()
        },
        "institution_rankings": [
            {
                "name": d["name"],
                "region": d["region"],
                "score": round(d["score"], 4),
                "z_score": round(d.get("z_score", 0), 4),
                "dominant_channel": d["dominant"],
            }
            for d in inst_data
        ],
    }

    out_file = os.path.join(os.path.dirname(__file__), "global_analysis_results.json")
    with open(out_file, "w") as f:
        json.dump(results_out, f, indent=2)
    print(f"  Results saved to: {out_file}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
