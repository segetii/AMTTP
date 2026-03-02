#!/usr/bin/env python3
"""
Global Multi-Variant MFLS Analysis
====================================
Runs ALL five BSDT scoring variants across 24 institutions (5 regions):
  1. Baseline (Mahalanobis)
  2. FullBSDT (4-channel uniform sum)
  3. QuadSurf (polynomial ridge - supervised)
  4. SignedLR (logistic - supervised)
  5. ExpoGate (quad+tanh+sigmoid - supervised)

Produces per-variant x per-region risk matrix and diagnostic comparisons.
"""

import sys, os, json, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))

from mfls.core.bsdt import BSDTOperator, BSDTOperators, BSDTChannels
from mfls.core.scoring import (
    MFLSBaseline, MFLSFullBSDT, MFLSQuadSurf, MFLSSignedLR, MFLSExpoGate,
    ALL_VARIANTS,
)
from mfls.core.network import lw_correlation_network
from mfls.data.loaders import build_gsib_panel

# Crisis windows for supervised fitting and evaluation
CRISIS_WINDOWS = [
    ("GFC", "2007-10-01", "2009-12-31"),
    ("COVID", "2020-01-01", "2021-06-30"),
    ("RateShock", "2022-01-01", "2023-12-31"),
]


def build_crisis_labels(dates, windows=CRISIS_WINDOWS):
    labels = np.zeros(len(dates), dtype=float)
    for _, onset, end in windows:
        mask = (dates >= pd.Timestamp(onset)) & (dates <= pd.Timestamp(end))
        labels[mask] = 1.0
    return labels


def compute_auroc(signal, labels):
    if labels.sum() == 0 or labels.sum() == len(labels):
        return None
    desc = np.argsort(-signal)
    sorted_labels = labels[desc]
    n_pos = labels.sum()
    n_neg = len(labels) - n_pos
    tp = fp = 0
    auroc = 0.0
    prev_tp = prev_fp = 0
    for i in range(len(sorted_labels)):
        if sorted_labels[i] == 1:
            tp += 1
        else:
            fp += 1
        if i == len(sorted_labels) - 1 or signal[desc[i]] != signal[desc[i + 1]]:
            auroc += (fp - prev_fp) * (tp + prev_tp) / 2.0
            prev_tp = tp
            prev_fp = fp
    return float(auroc / (n_pos * n_neg)) if n_pos * n_neg > 0 else None


def compute_hr_far(signal, labels, threshold):
    alarm = signal > threshold
    crisis = labels == 1
    calm = labels == 0
    hr = float(alarm[crisis].mean()) if crisis.sum() > 0 else None
    far = float(alarm[calm].mean()) if calm.sum() > 0 else None
    return hr, far


def run_variant(variant_name, X_std, channels, dates, normal_mask, labels):
    """Run a single variant and return metrics."""
    T = X_std.shape[0]
    X_normal = X_std[normal_mask]
    ch_all = channels.channels  # (T, 4)

    # Supervised variants need training data that INCLUDES crises.
    # Use a train/test split: train on first 70% of timeline, test on rest.
    # The normal_mask is used only for the unsupervised baseline calibration.
    train_cutoff = int(T * 0.70)
    train_mask = np.zeros(T, dtype=bool)
    train_mask[:train_cutoff] = True

    if variant_name == "baseline":
        var = MFLSBaseline()
        var.fit(X_normal)
        signal = var.score_series(X_std)
    elif variant_name == "full_bsdt":
        var = MFLSFullBSDT()
        var.fit(ch_all)
        signal = var.score(ch_all)
    elif variant_name == "quadsurf":
        var = MFLSQuadSurf(ridge_alpha=1.0)
        var.fit(ch_all[train_mask], labels[train_mask])
        signal = var.score(ch_all)
    elif variant_name == "signed_lr":
        var = MFLSSignedLR(lr=0.05, n_iter=2000, reg=0.001)
        var.fit(ch_all[train_mask], labels[train_mask])
        signal = var.score(ch_all)
    elif variant_name == "expo_gate":
        var = MFLSExpoGate(ridge_alpha=1.0, smooth_sigma=2.0, gate_scale=5.0)
        var.fit(ch_all[train_mask], labels[train_mask])
        signal = var.score(ch_all)
    else:
        raise ValueError(f"Unknown variant: {variant_name}")

    # Compute threshold from normal period
    normal_signal = signal[normal_mask]
    threshold = float(np.percentile(normal_signal, 75))

    # AUROC
    auroc = compute_auroc(signal, labels)
    hr, far = compute_hr_far(signal, labels, threshold)

    # GFC lead
    gfc_onset = pd.Timestamp("2007-10-01")
    alarm_dates = dates[signal > threshold]
    pre_gfc = alarm_dates[alarm_dates < gfc_onset]
    gfc_lead = None
    if len(pre_gfc) > 0:
        first_alarm = pre_gfc[0]
        gfc_lead = max(0, int((gfc_onset.year - first_alarm.year) * 4 +
                               (gfc_onset.quarter - first_alarm.quarter)))

    # Current state
    current_signal = float(signal[-1])
    z = float((current_signal - np.mean(signal[1:])) / np.std(signal[1:])) if np.std(signal[1:]) > 0 else 0.0

    # Channel weights (for supervised variants)
    weights = None
    if hasattr(var, 'channel_weights'):
        weights = var.channel_weights
    elif hasattr(var, 'beta_') and var.beta_ is not None:
        w = var.beta_
        if len(w) == 15:  # QuadSurf poly features
            weights = {"beta_norm": float(np.linalg.norm(w))}
        else:
            weights = {f"w{i}": float(w[i]) for i in range(len(w))}

    return {
        "name": variant_name,
        "signal": signal,
        "auroc": auroc,
        "hit_rate": hr,
        "false_alarm_rate": far,
        "gfc_lead": gfc_lead,
        "threshold": threshold,
        "current_signal": current_signal,
        "z_score": z,
        "weights": weights,
    }


def main():
    print("=" * 78)
    print("  GLOBAL MULTI-VARIANT MFLS ANALYSIS")
    print("  5 variants x 5 regions x 24 institutions")
    print("=" * 78)

    # ── 1. BUILD PANEL ──
    print("\n[1/5] Building global panel...")
    panel_raw = build_gsib_panel(
        start="2003-01-01", end="2024-12-31",
        force_refresh=False, min_coverage=0.25, verbose=True,
    )
    X = panel_raw["X"]
    dates = panel_raw["dates"]
    meta = panel_raw["meta"]
    T, N, d = X.shape
    feature_names = panel_raw["feature_names"]

    print(f"\n  Panel: T={T}, N={N}, d={d}")
    regions_count = {}
    for m in meta:
        regions_count[m["region"]] = regions_count.get(m["region"], 0) + 1
    print(f"  Regions: {regions_count}")

    # Standardise
    normal_start, normal_end = "2003-01-01", "2006-12-31"
    normal_mask = (dates >= pd.Timestamp(normal_start)) & (dates <= pd.Timestamp(normal_end))
    X_ref = X[normal_mask].reshape(-1, d)
    mu, sigma = X_ref.mean(axis=0), X_ref.std(axis=0) + 1e-10
    X_std = (X - mu) / sigma

    # Crisis labels
    labels = build_crisis_labels(dates)
    print(f"  Crisis quarters: {int(labels.sum())}/{T}")
    print(f"  Normal period: {normal_start} to {normal_end} ({normal_mask.sum()} quarters)")

    # ── 2. COMPUTE BSDT CHANNELS ──
    print("\n[2/5] Computing 4-channel BSDT decomposition...")
    bsdt = BSDTOperators()
    bsdt.fit(X_std[normal_mask])
    channels = bsdt.compute_channels(X_std, verbose=True)

    print(f"\n  Channel statistics (mean / std / max):")
    for i, name in enumerate(["delta_C", "delta_G", "delta_A", "delta_T"]):
        ch = channels.channels[:, i]
        print(f"    {name}: {ch.mean():.4f} / {ch.std():.4f} / {ch.max():.4f}")

    # ── 3. RUN ALL VARIANTS (GLOBAL) ──
    print("\n[3/5] Running all 5 variants on global panel...")
    variant_names = ["baseline", "full_bsdt", "quadsurf", "signed_lr", "expo_gate"]
    display_names = {
        "baseline": "Baseline (Mahalanobis)",
        "full_bsdt": "FullBSDT (4-ch uniform)",
        "quadsurf": "QuadSurf (poly ridge)",
        "signed_lr": "SignedLR (logistic)",
        "expo_gate": "ExpoGate (quad+tanh+sig)",
    }
    global_results = {}
    for vn in variant_names:
        try:
            r = run_variant(vn, X_std, channels, dates, normal_mask, labels)
            global_results[vn] = r
            print(f"  {display_names[vn]:<30} AUROC={r['auroc']:.4f}" if r['auroc'] else
                  f"  {display_names[vn]:<30} AUROC=N/A")
        except Exception as e:
            print(f"  {display_names[vn]:<30} FAILED: {e}")
            global_results[vn] = None

    # ── VARIANT COMPARISON TABLE ──
    print(f"\n{'='*78}")
    print(f"  VARIANT COMPARISON (Global, N={N}, T={T})")
    print(f"{'='*78}")
    print(f"\n  {'Variant':<26} {'AUROC':>8} {'HR':>8} {'FAR':>8} {'Lead':>6} {'Signal':>10} {'Z':>8} {'Thr':>10}")
    print(f"  {'-'*90}")
    for vn in variant_names:
        r = global_results.get(vn)
        if r is None:
            print(f"  {display_names[vn]:<26} {'FAILED':>8}")
            continue
        auroc_s = f"{r['auroc']:.4f}" if r['auroc'] is not None else "N/A"
        hr_s = f"{r['hit_rate']:.1%}" if r['hit_rate'] is not None else "N/A"
        far_s = f"{r['false_alarm_rate']:.1%}" if r['false_alarm_rate'] is not None else "N/A"
        lead_s = f"{r['gfc_lead']}Q" if r['gfc_lead'] is not None else "N/A"
        print(f"  {display_names[vn]:<26} {auroc_s:>8} {hr_s:>8} {far_s:>8} {lead_s:>6} {r['current_signal']:>10.4f} {r['z_score']:>+8.2f}s {r['threshold']:>10.4f}")

    # ── SIGNED LR CHANNEL WEIGHTS ──
    slr = global_results.get("signed_lr")
    if slr and slr.get("weights"):
        print(f"\n  SignedLR channel weights (what drives crisis detection):")
        for k, v in slr["weights"].items():
            marker = " <-- herding signal" if k == "delta_T" and v < 0 else ""
            print(f"    {k:<12} {v:>+8.4f}{marker}")

    # ── 4. PER-REGION x PER-VARIANT MATRIX ──
    print(f"\n[4/5] Per-region x per-variant AUROC matrix...")
    region_names = sorted(set(m["region"] for m in meta))
    region_variant_results = {}

    for region in region_names:
        idx = [i for i, m in enumerate(meta) if m["region"] == region]
        if len(idx) < 1:
            continue
        X_r = X[:, idx, :]
        X_r_std = (X_r - mu) / sigma  # same standardisation as global

        # Build region-level BSDT channels
        bsdt_r = BSDTOperators()
        bsdt_r.fit(X_r_std[normal_mask])
        ch_r = bsdt_r.compute_channels(X_r_std, verbose=False)

        region_variant_results[region] = {}
        for vn in variant_names:
            try:
                r = run_variant(vn, X_r_std, ch_r, dates, normal_mask, labels)
                region_variant_results[region][vn] = r
            except Exception as e:
                region_variant_results[region][vn] = {
                    "auroc": None, "hit_rate": None, "false_alarm_rate": None,
                    "current_signal": 0, "z_score": 0, "threshold": 0,
                    "gfc_lead": None, "name": vn,
                }

    # Print AUROC matrix
    print(f"\n  {'Region':<10}", end="")
    for vn in variant_names:
        print(f"  {vn:>12}", end="")
    print()
    print(f"  {'-'*75}")
    for region in region_names:
        print(f"  {region:<10}", end="")
        for vn in variant_names:
            r = region_variant_results[region].get(vn, {})
            auroc = r.get("auroc")
            if auroc is not None:
                print(f"  {auroc:>12.4f}", end="")
            else:
                print(f"  {'N/A':>12}", end="")
        print()
    # Global row
    print(f"  {'GLOBAL':<10}", end="")
    for vn in variant_names:
        r = global_results.get(vn)
        auroc = r["auroc"] if r else None
        if auroc is not None:
            print(f"  {auroc:>12.4f}", end="")
        else:
            print(f"  {'N/A':>12}", end="")
    print()

    # Print Hit Rate matrix
    print(f"\n  Hit Rate matrix:")
    print(f"  {'Region':<10}", end="")
    for vn in variant_names:
        print(f"  {vn:>12}", end="")
    print()
    print(f"  {'-'*75}")
    for region in region_names:
        print(f"  {region:<10}", end="")
        for vn in variant_names:
            r = region_variant_results[region].get(vn, {})
            hr = r.get("hit_rate")
            if hr is not None:
                print(f"  {hr:>11.1%}", end="")
            else:
                print(f"  {'N/A':>12}", end="")
        print()

    # Print current signal / Z-score matrix
    print(f"\n  Current signal Z-score matrix:")
    print(f"  {'Region':<10}", end="")
    for vn in variant_names:
        print(f"  {vn:>12}", end="")
    print()
    print(f"  {'-'*75}")
    for region in region_names:
        print(f"  {region:<10}", end="")
        for vn in variant_names:
            r = region_variant_results[region].get(vn, {})
            z = r.get("z_score", 0)
            print(f"  {z:>+11.2f}s", end="")
        print()

    # ── 5. VARIANT INSIGHTS & DIAGNOSTIC ──
    print(f"\n[5/5] Variant diagnostic insights...")

    # Cross-variant signal correlation
    print(f"\n  Signal correlation matrix (global):")
    valid_variants = [vn for vn in variant_names if global_results.get(vn) is not None]
    if len(valid_variants) > 1:
        signals_matrix = np.column_stack([
            global_results[vn]["signal"] for vn in valid_variants
        ])
        corr = np.corrcoef(signals_matrix, rowvar=False)
        print(f"  {'':>12}", end="")
        for vn in valid_variants:
            print(f"  {vn:>12}", end="")
        print()
        for i, vn in enumerate(valid_variants):
            print(f"  {vn:>12}", end="")
            for j in range(len(valid_variants)):
                print(f"  {corr[i,j]:>12.3f}", end="")
            print()

    # Variant agreement on regime
    print(f"\n  Variant agreement on current regime:")
    for vn in variant_names:
        r = global_results.get(vn)
        if r is None:
            continue
        sig, thr = r["current_signal"], r["threshold"]
        above = sig > thr
        regime = "ELEVATED" if above else "NORMAL"
        if sig > thr * 1.5:
            regime = "CRITICAL"
        print(f"    {display_names[vn]:<26}: {regime:<10} (signal={sig:.4f}, threshold={thr:.4f})")

    # Where variants DISAGREE most (region-level)
    print(f"\n  Cross-variant AUROC spread by region (agreement/disagreement):")
    for region in region_names:
        aurocs = []
        for vn in variant_names:
            r = region_variant_results[region].get(vn, {})
            a = r.get("auroc")
            if a is not None:
                aurocs.append(a)
        if len(aurocs) >= 2:
            spread = max(aurocs) - min(aurocs)
            best_vn = variant_names[np.argmax([
                (region_variant_results[region].get(vn, {}).get("auroc") or 0)
                for vn in variant_names
            ])]
            print(f"    {region:<10}: spread={spread:.4f}, best={best_vn} ({max(aurocs):.4f}), worst={min(aurocs):.4f}")

    # Channel dominance per variant (for supervised)
    print(f"\n  Supervised variant channel analysis:")
    for vn in ["signed_lr"]:
        r = global_results.get(vn)
        if r and r.get("weights"):
            print(f"\n    {display_names[vn]} weights:")
            w = r["weights"]
            for k in ["bias", "delta_C", "delta_G", "delta_A", "delta_T"]:
                if k in w:
                    bar_len = int(min(abs(w[k]) * 10, 40))
                    bar = ("+" if w[k] > 0 else "-") * bar_len
                    print(f"      {k:<12} {w[k]:>+8.4f}  {bar}")
            if "delta_T" in w and w["delta_T"] < 0:
                print(f"\n      >>> HERDING CONFIRMED: negative delta_T weight ({w['delta_T']:+.4f})")
                print(f"      >>> Pre-crisis institutions become MORE predictable (less novel)")

    # Per-region SignedLR analysis
    print(f"\n  Per-region SignedLR channel weights:")
    print(f"  {'Region':<10} {'bias':>8} {'delta_C':>8} {'delta_G':>8} {'delta_A':>8} {'delta_T':>8} {'Herding?':>8}")
    print(f"  {'-'*65}")
    for region in region_names:
        r = region_variant_results[region].get("signed_lr", {})
        w = r.get("weights", {})
        if w:
            herding = "YES" if w.get("delta_T", 0) < 0 else "no"
            print(f"  {region:<10} {w.get('bias',0):>+8.3f} {w.get('delta_C',0):>+8.3f} {w.get('delta_G',0):>+8.3f} {w.get('delta_A',0):>+8.3f} {w.get('delta_T',0):>+8.3f} {herding:>8}")

    # ── EXECUTIVE SUMMARY ──
    print(f"\n{'='*78}")
    print(f"  EXECUTIVE SUMMARY - MULTI-VARIANT GLOBAL MFLS")
    print(f"{'='*78}")
    print(f"  Assessment:     {dates[-1].strftime('%Y-%m-%d')}")
    print(f"  Institutions:   {N} across {len(region_names)} regions")
    print(f"  Quarters:       {T}")
    print()

    # Best variant per region
    print(f"  Best variant by AUROC per region:")
    for region in region_names:
        best_auroc = -1
        best_vn = "N/A"
        for vn in variant_names:
            r = region_variant_results[region].get(vn, {})
            a = r.get("auroc")
            if a is not None and a > best_auroc:
                best_auroc = a
                best_vn = display_names[vn]
        print(f"    {region:<10}: {best_vn:<28} AUROC={best_auroc:.4f}")

    # Global best
    best_global = max(
        [(vn, global_results[vn]["auroc"]) for vn in variant_names
         if global_results.get(vn) and global_results[vn].get("auroc") is not None],
        key=lambda x: x[1]
    )
    print(f"\n  Global best:    {display_names[best_global[0]]:<28} AUROC={best_global[1]:.4f}")

    # Key insights
    print(f"\n  Key Insights:")
    slr_w = global_results.get("signed_lr", {}).get("weights", {})
    if slr_w.get("delta_T", 0) < 0:
        print(f"    1. HERDING SIGNAL CONFIRMED: SignedLR learns negative delta_T")
        print(f"       weight ({slr_w['delta_T']:+.4f}), meaning pre-crisis periods show")
        print(f"       DECREASED temporal novelty = convergent herding.")

    # Compare unsupervised vs supervised
    bl_auroc = global_results.get("baseline", {}).get("auroc")
    fb_auroc = global_results.get("full_bsdt", {}).get("auroc")
    qs_auroc = global_results.get("quadsurf", {}).get("auroc")
    eg_auroc = global_results.get("expo_gate", {}).get("auroc")
    if all(x is not None for x in [bl_auroc, fb_auroc, qs_auroc, eg_auroc]):
        unsup = max(bl_auroc, fb_auroc)
        sup = max(qs_auroc, eg_auroc)
        if sup > unsup:
            print(f"    2. Supervised variants outperform unsupervised:")
            print(f"       Best supervised: {max(qs_auroc, eg_auroc):.4f} vs best unsupervised: {unsup:.4f}")
        else:
            print(f"    2. Unsupervised variants competitive with supervised:")
            print(f"       Best unsupervised: {unsup:.4f} vs best supervised: {sup:.4f}")

    # ExpoGate gating
    eg = global_results.get("expo_gate")
    if eg:
        sig_eg = eg["signal"]
        saturation = np.mean(sig_eg > 0.9)
        print(f"    3. ExpoGate sigmoid saturation: {saturation:.1%} of quarters saturated (>0.9)")
        if saturation > 0.5:
            print(f"       High saturation indicates persistent systemic stress.")
        else:
            print(f"       Low saturation means the model discriminates well between regimes.")

    # FullBSDT vs Baseline: does adding channels help?
    if fb_auroc and bl_auroc:
        delta = fb_auroc - bl_auroc
        print(f"    4. FullBSDT vs Baseline AUROC delta: {delta:+.4f}")
        if delta > 0.05:
            print(f"       The 3 additional channels (gap, activity, temporal) ADD significant value.")
        elif delta < -0.05:
            print(f"       Baseline Mahalanobis ALONE outperforms 4-channel sum.")
            print(f"       Suggests credit camouflage dominates; other channels add noise.")
        else:
            print(f"       Minimal difference: credit camouflage carries most information.")

    print()

    # Save results
    results_out = {
        "timestamp": pd.Timestamp.now().isoformat(),
        "panel": {"T": T, "N": N, "d": d, "regions": regions_count},
        "global_variants": {
            vn: {
                "auroc": r["auroc"],
                "hit_rate": r["hit_rate"],
                "false_alarm_rate": r["false_alarm_rate"],
                "gfc_lead": r["gfc_lead"],
                "current_signal": r["current_signal"],
                "z_score": r["z_score"],
                "threshold": r["threshold"],
                "weights": r.get("weights"),
            }
            for vn, r in global_results.items() if r is not None
        },
        "region_variant_aurocs": {
            region: {
                vn: region_variant_results[region].get(vn, {}).get("auroc")
                for vn in variant_names
            }
            for region in region_names
        },
    }

    out_file = os.path.join(os.path.dirname(__file__), "variant_analysis_results.json")
    with open(out_file, "w") as f:
        json.dump(results_out, f, indent=2)
    print(f"  Results saved to: {out_file}")
    print(f"{'='*78}")


if __name__ == "__main__":
    main()
