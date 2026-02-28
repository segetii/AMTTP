"""
run_variants_banklevel.py
=========================
Run all 5 MFLS scoring variants on the institution-level (N=30 banks)
panel and compare their GFC early-warning performance.

Strict OOS protocol
-------------------
  Train : 1990 - 2006  (fits variant weights; only S&L crisis labels visible)
  Test  : 2007 - 2024  (GFC + COVID; threshold set at train-period P75)

Output
------
  results/variant_comparison_banklevel.json   -- machine-readable
  results/variant_comparison_banklevel.txt    -- printable table
"""
from __future__ import annotations
import sys, json, warnings, time
import numpy as np
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrapping
# ---------------------------------------------------------------------------
THIS_DIR     = Path(__file__).parent
UPGRADED_DIR = THIS_DIR.parent / "upgraded"
VARIANT_DIR  = THIS_DIR.parent / "variants"
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(UPGRADED_DIR))
sys.path.insert(0, str(VARIANT_DIR))

from bank_level_loader import build_bank_panel
from mfls_variants     import (MFLSBaseline, MFLSFullBSDT, MFLSQuadSurf,
                                MFLSSignedLR, MFLSExpoGate, make_crisis_labels)
from bsdt_operators    import BSDTOperators

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
NORMAL_START = "1994-01-01"
NORMAL_END   = "2003-12-31"
TRAIN_END    = "2006-12-31"
GFC_START    = "2007-01-01"
GFC_PEAK     = "2008-09-30"    # Lehman quarter
GFC_END      = "2009-06-30"
RESULTS_DIR  = THIS_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helper: AUROC
# ---------------------------------------------------------------------------
def _auroc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Compute AUROC (trapezoidal)."""
    from sklearn.metrics import roc_auc_score
    if labels.sum() == 0 or labels.sum() == len(labels):
        return float("nan")
    try:
        return float(roc_auc_score(labels, scores))
    except Exception:
        return float("nan")


def _try_auroc(scores, labels):
    """AUROC without sklearn dependency."""
    pos = scores[labels == 1]
    neg = scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    # Mann-Whitney U
    count = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return float(count / (len(pos) * len(neg)))


def auroc(scores, labels):
    try:
        return _auroc(scores, labels)
    except Exception:
        return _try_auroc(scores, labels)


# ---------------------------------------------------------------------------
# Helper: OOS backtest
# ---------------------------------------------------------------------------
def oos_backtest(signal: np.ndarray, dates: pd.DatetimeIndex,
                 train_end: str = TRAIN_END,
                 gfc_start: str = GFC_START,
                 gfc_peak:  str = GFC_PEAK,
                 gfc_end:   str = GFC_END) -> dict:
    """
    Train threshold on [start, train_end]; test on [gfc_start, gfc_end].
    Lead is measured to gfc_peak (Lehman quarter, Sep-2008), consistent
    with the baseline 6Q figure in the paper.
    """
    train_mask = dates <= pd.Timestamp(train_end)
    test_mask  = dates >  pd.Timestamp(train_end)
    gfc_mask   = (dates >= pd.Timestamp(gfc_start)) & (dates <= pd.Timestamp(gfc_end))
    calm_mask  = test_mask & ~gfc_mask

    if train_mask.sum() == 0 or gfc_mask.sum() == 0:
        return {"alarm_date": None, "lead_quarters": 0,
                "hit_rate": 0.0, "false_alarm_rate": None}

    threshold = float(np.percentile(signal[train_mask], 75))

    above_gfc  = signal[gfc_mask] > threshold
    above_calm = signal[calm_mask] > threshold if calm_mask.sum() > 0 else np.array([])

    hit_rate = float(above_gfc.mean()) if len(above_gfc) > 0 else 0.0
    far      = float(above_calm.mean()) if len(above_calm) > 0 else None

    # First alarm in full test window
    test_signal = signal[test_mask]
    test_dates  = dates[test_mask]
    alarm_date  = None
    lead_q      = 0
    if (test_signal > threshold).any():
        idx = int(np.argmax(test_signal > threshold))
        alarm_date = str(test_dates[idx].date())
        # Lead = quarters between first alarm and Lehman peak
        peak_dt  = pd.Timestamp(gfc_peak)
        alarm_dt = test_dates[idx]
        lead_q   = max(0, int(round((peak_dt - alarm_dt).days / 91.25)))

    return {
        "threshold_p75": round(threshold, 4),
        "alarm_date":    alarm_date,
        "lead_quarters": lead_q,
        "hit_rate":      round(hit_rate, 4),
        "false_alarm_rate": round(far, 4) if far is not None else None,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(n_banks: int = 30, force_refresh: bool = False):
    t0 = time.time()
    sep = "=" * 68
    print(sep)
    print("  MFLS Variants on Institution-Level Panel (N=30 banks)")
    print("  OOS protocol: train 1990-2006 | test 2007+ (GFC + COVID)")
    print(sep)

    # ------------------------------------------------------------------
    # 1. Load bank panel
    # ------------------------------------------------------------------
    print("\n[1/5] Loading institution-level state matrix...")
    panel = build_bank_panel(n_banks=n_banks, force_refresh=force_refresh)
    X_raw = panel["X"]       # (T, N, d)
    dates = panel["dates"]   # DatetimeIndex
    T, N, d_base = X_raw.shape
    print(f"  Panel: T={T}, N={N}, d={d_base}  "
          f"({dates[0].date()} -> {dates[-1].date()})")

    # ------------------------------------------------------------------
    # 2. Standardise on normal period
    # ------------------------------------------------------------------
    norm_mask = (dates >= pd.Timestamp(NORMAL_START)) & \
                (dates <= pd.Timestamp(NORMAL_END))
    X_ref  = X_raw[norm_mask]
    mu_ref = X_ref.reshape(-1, d_base).mean(axis=0)
    sd_ref = X_ref.reshape(-1, d_base).std(axis=0) + 1e-9
    X_std  = (X_raw - mu_ref) / sd_ref
    print(f"  Normal period: {norm_mask.sum()}Q  "
          f"({NORMAL_START} to {NORMAL_END})")

    # ------------------------------------------------------------------
    # 3. Compute BSDT channel scores  (T, 4)
    # ------------------------------------------------------------------
    print("\n[2/5] Fitting BSDTOperators on normal period...")
    ops = BSDTOperators(n_components=min(4, d_base - 1))
    ops.fit(X_std[norm_mask])
    print("  Computing channels over full timeline...")
    ch_dict = ops.compute_channels(X_std, verbose=False)
    channels = ch_dict["channels"]   # (T, 4)
    print(f"  Channels shape: {channels.shape}")
    for i, name in enumerate(["dC", "dG", "dA", "dT"]):
        print(f"    {name}: [{channels[:,i].min():.3f}, {channels[:,i].max():.3f}]")

    # ------------------------------------------------------------------
    # 4. Prepare labels and train/test split
    # ------------------------------------------------------------------
    print("\n[3/5] Preparing crisis labels and train/test split...")
    y_all    = make_crisis_labels(dates)
    train_m  = dates <= pd.Timestamp(TRAIN_END)
    # For supervised variants: only S&L crisis is visible in training
    # (GFC/COVID labels are OOS -- excluded from fitting)
    y_train  = make_crisis_labels(
        dates[train_m],
        crisis_quarters={
            # S&L tail (1990-1991)
            "1990-06-30", "1990-09-30", "1990-12-31", "1991-03-31",
        }
    )
    X_train   = X_std[train_m]
    ch_train  = channels[train_m]
    print(f"  Train: {train_m.sum()}Q, crisis labels: {y_train.sum()}")
    print(f"  Test : {(~train_m).sum()}Q")

    # Full-panel labels for AUROC (includes GFC + COVID)
    y_full = make_crisis_labels(dates)
    gfc_mask = (dates >= pd.Timestamp(GFC_START)) & \
               (dates <= pd.Timestamp(GFC_END))
    print(f"  GFC quarters: {gfc_mask.sum()}")

    # ------------------------------------------------------------------
    # 5. Run variants
    # ------------------------------------------------------------------
    print("\n[4/5] Running 5 MFLS variants...")
    print("-" * 68)

    variants = [
        ("Baseline",  MFLSBaseline(),              "baseline"),
        ("FullBSDT",  MFLSFullBSDT(),              "channel"),
        ("QuadSurf",  MFLSQuadSurf(ridge_alpha=1), "channel"),
        ("SignedLR",  MFLSSignedLR(),               "channel"),
        ("ExpoGate",  MFLSExpoGate(ridge_alpha=1),  "channel"),
    ]

    results = {}

    for vname, model, mode in variants:
        print(f"\n  >> {vname}")
        # Fit
        if mode == "baseline":
            model.fit(X_std[norm_mask])
            signal = model.score_series(X_std)      # (T,)
        else:
            # channel-based variants
            if hasattr(model, "beta_") or isinstance(
                model, (MFLSQuadSurf, MFLSSignedLR, MFLSExpoGate)
            ):
                # supervised -- fit on training channels + S&L labels
                model.fit(ch_train, y_train)
            else:
                # unsupervised (FullBSDT)
                model.fit(ch_train)
            signal = model.score(channels)          # (T,)

        # AUROC across full test period (GFC + COVID labels)
        test_m   = ~train_m
        auc_full = auroc(signal, y_full)
        auc_gfc  = auroc(signal[test_m], gfc_mask[test_m].astype(int))

        # OOS alarm metrics
        bt = oos_backtest(signal, dates, gfc_peak=GFC_PEAK)

        # Signal range
        sig_min = float(signal.min())
        sig_max = float(signal.max())

        row = {
            "variant":           vname,
            "signal_min":        round(sig_min, 4),
            "signal_max":        round(sig_max, 4),
            "auroc_full":        round(auc_full, 4) if not np.isnan(auc_full) else None,
            "auroc_gfc":         round(auc_gfc, 4)  if not np.isnan(auc_gfc)  else None,
            **{f"oos_{k}": v for k, v in bt.items()},
        }
        results[vname] = row

        print(f"     Signal: [{sig_min:.3f}, {sig_max:.3f}]")
        print(f"     AUROC (full/GFC): {auc_full:.3f} / "
              f"{'nan' if np.isnan(auc_gfc) else f'{auc_gfc:.3f}'}")
        print(f"     Alarm: {bt['alarm_date']}  lead={bt['lead_quarters']}Q  "
              f"HR={bt['hit_rate']:.1%}  FAR={bt['false_alarm_rate']}")

    # ------------------------------------------------------------------
    # 6. Save results
    # ------------------------------------------------------------------
    print("\n[5/5] Saving results...")
    out_json = RESULTS_DIR / "variant_comparison_banklevel.json"
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  -> {out_json}")

    # Text table
    out_txt = RESULTS_DIR / "variant_comparison_banklevel.txt"
    with open(out_txt, "w") as f:
        f.write("MFLS Variants on Institution-Level Panel (N=30 banks)\n")
        f.write("OOS: train<=2006, test>=2007; threshold=P75 of train signal\n")
        f.write("-" * 78 + "\n")
        hdr = f"{'Variant':<18} {'AUROC':>6} {'Alarm':>12} {'Lead':>5} {'HR':>7} {'FAR':>7}\n"
        f.write(hdr)
        f.write("-" * 78 + "\n")
        for vname, row in results.items():
            auc  = f"{row['auroc_full']:.3f}" if row['auroc_full'] else "  N/A"
            alrm = row['oos_alarm_date'] or "  N/A      "
            lead = row['oos_lead_quarters']
            hr   = f"{row['oos_hit_rate']:.1%}"
            far  = f"{row['oos_false_alarm_rate']:.1%}" if row['oos_false_alarm_rate'] else "N/A"
            f.write(f"{vname:<18} {auc:>6} {alrm:>12} {lead:>5} {hr:>7} {far:>7}\n")
        f.write("-" * 78 + "\n")
    print(f"  -> {out_txt}")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")
    return results


if __name__ == "__main__":
    main()
