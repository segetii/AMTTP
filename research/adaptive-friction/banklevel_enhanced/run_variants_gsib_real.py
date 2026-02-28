"""
run_variants_gsib_real.py
=========================
Run all 5 MFLS scoring variants on the REAL-DATA G-SIB panel (N=20)
and compare their crisis early-warning performance.

Data: FDIC call-report (US) + World Bank GFDD + ECB MIR (non-US).
NO SYNTHETIC DATA.

Variants
--------
  1. Baseline   - Mahalanobis gradient norm ||nabla E_BS||_F
  2. FullBSDT   - uniform-weighted 4-channel sum (unsupervised)
  3. QuadSurf   - degree-2 polynomial ridge on channels (supervised)
  4. SignedLR   - logistic regression on channels (supervised)
  5. ExpoGate   - quadratic + tanh + sigmoid gate (supervised)

OOS Protocol
-------------
  Normal/calibration : 2005 Q1 - 2006 Q4 (pre-GFC)
  Train (supervised) : 2005 Q1 - 2006 Q4 (no crisis visible => all y=0)
  Test               : 2007 Q1 - 2023 Q4 (GFC + COVID + RateShock)

Note: supervised variants only see calm-period labels for training (y=0
everywhere in 2005-2006). This is an honest but harsh test: the models
must generalise from a zero-crisis training set.

Output
------
  results/gsib_real/variant_comparison_gsib_real.json
  results/gsib_real/variant_comparison_gsib_real.txt

Usage
-----
    python run_variants_gsib_real.py
    python run_variants_gsib_real.py --force_refresh
"""
from __future__ import annotations
import sys, json, warnings, time
import numpy as np
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
THIS_DIR     = Path(__file__).parent
UPGRADED_DIR = THIS_DIR.parent / "upgraded"
VARIANT_DIR  = THIS_DIR.parent / "variants"
for p in [str(THIS_DIR), str(UPGRADED_DIR), str(VARIANT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from gsib_loader_real  import build_gsib_panel_real
from mfls_variants     import (MFLSBaseline, MFLSFullBSDT, MFLSQuadSurf,
                                MFLSSignedLR, MFLSExpoGate)
from bsdt_operators    import BSDTOperators
from eval_protocol     import (build_binary_labels, CRISIS_WINDOWS_EVAL,
                                roc_auprc)
from bootstrap_auroc   import block_bootstrap_ci

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
NORMAL_START = "2005-01-01"
NORMAL_END   = "2006-12-31"
TRAIN_END    = "2006-12-31"    # supervised variants train on this window
GFC_ONSET    = "2007-10-01"
LEHMAN       = "2008-09-15"
GFC_END      = "2009-12-31"

RESULTS_DIR = THIS_DIR / "results" / "gsib_real"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _auroc(scores, labels):
    """AUROC via sklearn, fallback to Mann-Whitney."""
    try:
        from sklearn.metrics import roc_auc_score
        if labels.sum() == 0 or labels.sum() == len(labels):
            return float("nan")
        return float(roc_auc_score(labels, scores))
    except Exception:
        pos = scores[labels == 1]
        neg = scores[labels == 0]
        if len(pos) == 0 or len(neg) == 0:
            return float("nan")
        count = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
        return float(count / (len(pos) * len(neg)))


def _oos_backtest(signal, dates, train_end=TRAIN_END):
    """OOS alarm test: threshold = P75 of training signal."""
    train_mask = dates <= pd.Timestamp(train_end)
    if train_mask.sum() < 2:
        return {"p75_threshold": None, "alarm_date": None, "lead_quarters": 0,
                "gfc_hit_rate": 0.0, "false_alarm_rate": None}

    threshold = float(np.percentile(signal[train_mask], 75))

    # Full test window
    test_mask  = dates > pd.Timestamp(train_end)
    gfc_mask   = (dates >= pd.Timestamp(GFC_ONSET)) & \
                 (dates <= pd.Timestamp(GFC_END))
    calm_mask  = test_mask & ~gfc_mask

    # Crisis detection in GFC window
    gfc_hr = float((signal[gfc_mask] > threshold).mean()) if gfc_mask.any() else 0.0

    # FAR in calm quarters of test window
    if calm_mask.any():
        far = float((signal[calm_mask] > threshold).mean())
    else:
        far = None

    # First alarm and lead time
    test_signal = signal[test_mask]
    test_dates  = dates[test_mask]
    alarm_date  = None
    lead_q      = 0
    if (test_signal > threshold).any():
        idx = int(np.argmax(test_signal > threshold))
        alarm_date = str(test_dates[idx].date())
        alarm_dt   = test_dates[idx]
        lehman_dt  = pd.Timestamp(LEHMAN)
        if alarm_dt < lehman_dt:
            lead_q = max(0, int(round((lehman_dt - alarm_dt).days / 91.25)))

    return {
        "p75_threshold":    round(threshold, 4),
        "alarm_date":       alarm_date,
        "lead_quarters":    lead_q,
        "gfc_hit_rate":     round(gfc_hr, 4),
        "false_alarm_rate": round(far, 4) if far is not None else None,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(force_refresh: bool = False, n_boot: int = 500,
         train_end_override: str | None = None):
    t0 = time.time()
    sep = "=" * 72
    print(sep)
    print("  MFLS Variants on Real G-SIB Panel (N=20)")
    print("  US: FDIC call-report  |  Non-US: World Bank GFDD + ECB MIR")
    print("  NO SYNTHETIC DATA")
    print(sep)

    # ------------------------------------------------------------------
    # 1. Load real G-SIB panel
    # ------------------------------------------------------------------
    print("\n[1/6] Loading real-data G-SIB panel...")
    panel = build_gsib_panel_real(
        quarters_start="2005-01-01", quarters_end="2023-12-31",
        force_refresh=force_refresh, min_coverage=0.50, verbose=True,
    )
    X_raw = panel["X"]       # (T, N, d)
    dates = panel["dates"]
    meta  = panel["meta"]
    T, N, d = X_raw.shape
    print(f"  Panel: T={T}, N={N}, d={d}")

    # ------------------------------------------------------------------
    # 2. Standardise on normal period
    # ------------------------------------------------------------------
    print("\n[2/6] Standardising on normal period...")
    norm_mask = (dates >= pd.Timestamp(NORMAL_START)) & \
                (dates <= pd.Timestamp(NORMAL_END))
    n_norm = int(norm_mask.sum())
    if n_norm < 4:
        warnings.warn(f"Only {n_norm} normal quarters; using first 8.")
        norm_mask[:] = False
        norm_mask[:min(8, T)] = True
        n_norm = int(norm_mask.sum())

    X_ref  = X_raw[norm_mask]
    mu_ref = X_ref.reshape(-1, d).mean(axis=0)
    sd_ref = X_ref.reshape(-1, d).std(axis=0) + 1e-9
    X_std  = (X_raw - mu_ref) / sd_ref
    print(f"  Normal: {n_norm}Q ({NORMAL_START} -> {NORMAL_END})")

    # ------------------------------------------------------------------
    # 3. Compute BSDT 4-channel scores
    # ------------------------------------------------------------------
    print("\n[3/6] Fitting BSDTOperators and computing channels...")
    ops = BSDTOperators(n_components=min(4, d - 1))
    ops.fit(X_std[norm_mask])
    ch_dict  = ops.compute_channels(X_std, verbose=True)
    channels = ch_dict["channels"]   # (T, 4)
    print(f"  Channels: {channels.shape}")
    for i, name in enumerate(["delta_C", "delta_G", "delta_A", "delta_T"]):
        lo, hi = channels[:, i].min(), channels[:, i].max()
        print(f"    {name}: [{lo:.3f}, {hi:.3f}]")

    # ------------------------------------------------------------------
    # 4. Labels
    # ------------------------------------------------------------------
    print("\n[4/6] Crisis labels (eval_protocol windows)...")
    y_all = build_binary_labels(dates, CRISIS_WINDOWS_EVAL, shift_quarters=0)
    print(f"  Crisis quarters: {y_all.sum()} / {T}")

    # Training labels: use override if provided
    effective_train_end = train_end_override or TRAIN_END
    train_mask = dates <= pd.Timestamp(effective_train_end)
    ch_train   = channels[train_mask]
    y_train    = y_all[train_mask]
    print(f"  Train end: {effective_train_end}")
    print(f"  Train: {train_mask.sum()}Q, crisis labels in train: {y_train.sum()}")

    if y_train.sum() == 0:
        print("  NOTE: Zero crisis quarters in training window.")
        print("  Supervised variants will see only calm data.")
        print("  This is an honest but harsh OOS test.")

    # ------------------------------------------------------------------
    # 5. Run all 5 variants
    # ------------------------------------------------------------------
    print(f"\n[5/6] Running 5 MFLS variants...")
    print("-" * 72)

    variants = [
        ("Baseline",  MFLSBaseline(),               "baseline"),
        ("FullBSDT",  MFLSFullBSDT(),               "channel_unsup"),
        ("QuadSurf",  MFLSQuadSurf(ridge_alpha=1),  "channel_sup"),
        ("SignedLR",  MFLSSignedLR(),                "channel_sup"),
        ("ExpoGate",  MFLSExpoGate(ridge_alpha=1),  "channel_sup"),
    ]

    results = {}
    signals = {}

    for vname, model, mode in variants:
        print(f"\n  >> {vname} ({mode})")

        try:
            if mode == "baseline":
                # Mahalanobis gradient on raw state matrices
                model.fit(X_std[norm_mask])
                signal = model.score_series(X_std)
            elif mode == "channel_unsup":
                # Unsupervised: fit on training channels, no labels
                model.fit(ch_train)
                signal = model.score(channels)
            elif mode == "channel_sup":
                # Supervised: fit on training channels + labels
                if y_train.sum() == 0:
                    # All zeros in training -> supervised models learn nothing useful
                    # Still fit (they'll just learn a flat predictor)
                    print(f"     Warning: y_train is all zeros; {vname} has no signal to learn from")
                model.fit(ch_train, y_train)
                signal = model.score(channels)

            # Ensure signal is valid
            if np.isnan(signal).any():
                signal = np.nan_to_num(signal, nan=0.0)
            if np.isinf(signal).any():
                signal = np.nan_to_num(signal, posinf=signal[np.isfinite(signal)].max(),
                                       neginf=0.0)

        except Exception as e:
            print(f"     ERROR: {e}")
            signal = np.zeros(T)

        signals[vname] = signal

        # AUROC (full panel)
        auc_full = _auroc(signal, y_all)

        # AUROC (test-only)
        test_mask = ~train_mask
        auc_test = _auroc(signal[test_mask], y_all[test_mask])

        # OOS backtest
        bt = _oos_backtest(signal, dates, train_end=effective_train_end)

        # Bootstrap CI on AUROC (full panel)
        ci = {"auroc_lo": None, "auroc_hi": None}
        try:
            if not np.isnan(auc_full) and n_boot > 0:
                thr = bt["p75_threshold"] if bt["p75_threshold"] else float(np.percentile(signal, 75))
                ci_result = block_bootstrap_ci(
                    signal=signal, labels=y_all, threshold=thr,
                    n_boot=n_boot, block_len=8, alpha=0.05, verbose=False,
                )
                ci = {"auroc_lo": ci_result["auroc_lo"],
                      "auroc_hi": ci_result["auroc_hi"]}
        except Exception as e:
            print(f"     Bootstrap failed: {e}")

        row = {
            "variant":           vname,
            "mode":              mode,
            "signal_range":      [round(float(signal.min()), 4),
                                  round(float(signal.max()), 4)],
            "auroc_full":        round(auc_full, 4) if not np.isnan(auc_full) else None,
            "auroc_test":        round(auc_test, 4) if not np.isnan(auc_test) else None,
            "auroc_95ci":        [ci["auroc_lo"], ci["auroc_hi"]],
            **{f"oos_{k}": v for k, v in bt.items()},
        }
        results[vname] = row

        auc_s = f"{auc_full:.4f}" if not np.isnan(auc_full) else "NaN"
        auc_t = f"{auc_test:.4f}" if not np.isnan(auc_test) else "NaN"
        ci_s  = f"[{ci['auroc_lo']}, {ci['auroc_hi']}]" if ci["auroc_lo"] else ""
        print(f"     Signal: [{signal.min():.3f}, {signal.max():.3f}]")
        print(f"     AUROC: {auc_s} {ci_s}  (test-only: {auc_t})")
        print(f"     Alarm: {bt['alarm_date']}  lead={bt['lead_quarters']}Q  "
              f"HR={bt['gfc_hit_rate']:.1%}  FAR={bt['false_alarm_rate']}")

    # ------------------------------------------------------------------
    # 6. Region-level AUROC per variant
    # ------------------------------------------------------------------
    print(f"\n  >> Region-level AUROC per variant...")
    region_aurocs = {}
    for region in ["US", "EU", "Asia"]:
        idx = [i for i, m in enumerate(meta) if m["region"] == region]
        if len(idx) < 2:
            continue
        X_reg = X_std[:, idx, :]
        # Baseline on sub-panel
        bl = MFLSBaseline()
        bl.fit(X_reg[norm_mask])
        sig_r = bl.score_series(X_reg)
        auc_r = _auroc(sig_r, y_all)
        region_aurocs[region] = round(auc_r, 4) if not np.isnan(auc_r) else None
        print(f"     {region} (Baseline, N={len(idx)}): AUROC={auc_r:.4f}")

    # ------------------------------------------------------------------
    # 7. Save
    # ------------------------------------------------------------------
    print(f"\n[6/6] Saving results...")
    summary = {
        "data_source": "REAL DATA: FDIC (US) + World Bank GFDD + ECB MIR (non-US)",
        "NO_SYNTHETIC_DATA": True,
        "T": T, "N": N, "d": d,
        "date_range": f"{dates[0].date()} to {dates[-1].date()}",
        "normal_period": f"{NORMAL_START} to {NORMAL_END}",
        "train_end": TRAIN_END,
        "crisis_quarters_total": int(y_all.sum()),
        "crisis_in_train": int(y_train.sum()),
        "region_auroc_baseline": region_aurocs,
        "variants": results,
    }

    out_json = RESULTS_DIR / "variant_comparison_gsib_real.json"
    with open(out_json, "w") as f:
        json.dump(summary, f, indent=2,
                  default=lambda o: float(o) if hasattr(o, '__float__') else str(o))
    print(f"  -> {out_json}")

    # Text table
    out_txt = RESULTS_DIR / "variant_comparison_gsib_real.txt"
    with open(out_txt, "w") as f:
        f.write("MFLS Variants on Real G-SIB Panel (N=20)\n")
        f.write("Data: FDIC (US) + World Bank (non-US). NO SYNTHETIC.\n")
        f.write(f"Panel: T={T}, N={N}, d={d}  ({dates[0].date()} to {dates[-1].date()})\n")
        f.write(f"Normal: {NORMAL_START} to {NORMAL_END}  |  Train end: {TRAIN_END}\n")
        f.write(f"Crisis quarters in train: {y_train.sum()}  |  Total: {y_all.sum()}\n")
        f.write("-" * 88 + "\n")
        hdr = (f"{'Variant':<12} {'Mode':<14} {'AUROC':>7} {'95% CI':>20} "
               f"{'Alarm':>12} {'Lead':>5} {'HR':>7} {'FAR':>7}\n")
        f.write(hdr)
        f.write("-" * 88 + "\n")
        for vname, row in results.items():
            auc = f"{row['auroc_full']:.4f}" if row['auroc_full'] else "  N/A"
            ci  = row['auroc_95ci']
            ci_s = f"[{ci[0]:.4f}, {ci[1]:.4f}]" if ci[0] is not None else "N/A"
            alarm = row['oos_alarm_date'] or "N/A"
            lead  = row['oos_lead_quarters']
            hr    = f"{row['oos_gfc_hit_rate']:.1%}"
            far_v = row['oos_false_alarm_rate']
            far   = f"{far_v:.1%}" if far_v is not None else "N/A"
            f.write(f"{vname:<12} {row['mode']:<14} {auc:>7} {ci_s:>20} "
                    f"{alarm:>12} {lead:>5} {hr:>7} {far:>7}\n")
        f.write("-" * 88 + "\n")
        f.write(f"\nRegion AUROCs (Baseline): {region_aurocs}\n")
    print(f"  -> {out_txt}")

    # ------------------------------------------------------------------
    # Print summary table
    # ------------------------------------------------------------------
    elapsed = time.time() - t0
    print(f"\n{sep}")
    print(f"  VARIANT COMPARISON ON REAL G-SIB DATA (N={N}, T={T})")
    print(f"{sep}")
    print(f"  {'Variant':<12} {'AUROC':>7} {'95% CI':>20} {'Lead':>5} {'HR':>7} {'FAR':>7}")
    print(f"  {'-'*66}")
    for vname, row in results.items():
        auc = f"{row['auroc_full']:.4f}" if row['auroc_full'] else "  N/A"
        ci  = row['auroc_95ci']
        ci_s = f"[{ci[0]:.4f}, {ci[1]:.4f}]" if ci[0] is not None else "N/A"
        lead  = row['oos_lead_quarters']
        hr    = f"{row['oos_gfc_hit_rate']:.1%}"
        far_v = row['oos_false_alarm_rate']
        far   = f"{far_v:.1%}" if far_v is not None else "N/A"
        print(f"  {vname:<12} {auc:>7} {ci_s:>20} {lead:>5} {hr:>7} {far:>7}")
    print(f"  {'-'*66}")
    print(f"  Region AUROCs (Baseline): {region_aurocs}")
    print(f"  Runtime: {elapsed:.1f}s")
    print(sep)

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force_refresh", action="store_true")
    parser.add_argument("--n_boot", type=int, default=500)
    parser.add_argument("--train_end", type=str, default=None,
                        help="Override train end date, e.g. 2012-12-31")
    args = parser.parse_args()
    main(force_refresh=args.force_refresh, n_boot=args.n_boot,
         train_end_override=args.train_end)
