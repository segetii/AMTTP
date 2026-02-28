"""
run_pipeline_gsib_real.py
=========================
MFLS pipeline on the REAL-DATA G-SIB panel.

Data sources (NO synthetic data):
  US G-SIBs:     FDIC call-report (individual bank-level, quarterly)
  Non-US G-SIBs: World Bank GFDD + ECB MIR (country banking-sector aggregate,
                 annual interpolated to quarterly / monthly to quarterly)

Produces
--------
  results/gsib_real/pipeline_stats_gsib_real.json
  results/gsib_real/bootstrap_ci_gsib_real.json
  results/gsib_real/causality_gsib_real.json
  results/gsib_real/eval_protocol_gsib_real.json

Usage
-----
    python run_pipeline_gsib_real.py
    python run_pipeline_gsib_real.py --force_refresh --n_boot 1000
"""
from __future__ import annotations
import sys
import json
import time
import argparse
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
THIS_DIR     = Path(__file__).parent
ORIG_BL_DIR  = THIS_DIR.parent / "banklevel"
UPGRADED_DIR = THIS_DIR.parent / "upgraded"
VARIANT_DIR  = THIS_DIR.parent / "variants"

for p in [str(THIS_DIR), str(ORIG_BL_DIR), str(UPGRADED_DIR), str(VARIANT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from network_builder   import lw_correlation_network, spectral_radius
from gravity_engine    import BSDTOperator
from eval_protocol     import (eval_all_variants, CRISIS_WINDOWS_EVAL,
                               build_binary_labels, roc_auprc)
from robustness_checks import run_all_robustness, latex_robustness_table
from bootstrap_auroc   import block_bootstrap_ci, latex_bootstrap_table
from threshold_granger import run_all_causality_tests, latex_causality_table
from gsib_loader_real  import build_gsib_panel_real, FEATURE_NAMES

RESULTS_DIR = THIS_DIR / "results" / "gsib_real"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

NORMAL_START = "2005-03-31"   # panel starts 2005
NORMAL_END   = "2006-12-31"   # use 2005-2006 as normal calibration (pre-GFC)


def _make_crisis_labels(dates: pd.DatetimeIndex) -> np.ndarray:
    """Binary labels from eval_protocol crisis windows."""
    return build_binary_labels(dates, CRISIS_WINDOWS_EVAL, shift_quarters=0)


def _region_subpanel(X_std, meta, region):
    """Extract standardised sub-panel for a region."""
    idx = [i for i, m in enumerate(meta) if m["region"] == region]
    if not idx:
        return None
    return X_std[:, idx, :]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(
    n_boot:           int  = 1000,
    boot_block_len:   int  = 8,
    n_boot_causality: int  = 2000,
    force_refresh:    bool = False,
):
    t0 = time.time()
    print("=" * 70)
    print("  MFLS G-SIB Pipeline -- REAL DATA ONLY")
    print("  US: FDIC call-report  |  Non-US: World Bank GFDD + ECB MIR")
    print("  NO SYNTHETIC DATA")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 1. Load real G-SIB panel
    # ------------------------------------------------------------------
    print("\n[1/8] Building real-data G-SIB panel...")
    panel = build_gsib_panel_real(
        quarters_start="2005-01-01",
        quarters_end="2023-12-31",
        force_refresh=force_refresh,
        min_coverage=0.50,
        verbose=True,
    )
    X_raw = panel["X"]
    dates = panel["dates"]
    meta  = panel["meta"]
    N     = panel["n_gsib"]
    T, _, d = X_raw.shape

    print(f"\n  Panel: T={T}, N={N}, d={d}")
    print(f"  US (FDIC bank-level): {panel['n_us']}")
    print(f"  Non-US (World Bank country-aggregate): {panel['n_non_us']}")

    # ------------------------------------------------------------------
    # 2. Standardise on normal period
    # ------------------------------------------------------------------
    norm_mask = (dates >= pd.Timestamp(NORMAL_START)) & \
                (dates <= pd.Timestamp(NORMAL_END))
    n_norm = norm_mask.sum()
    if n_norm < 4:
        warnings.warn(f"Only {n_norm} normal-period quarters. Using first 8 quarters instead.")
        norm_mask[:] = False
        norm_mask[:min(8, T)] = True
        n_norm = norm_mask.sum()

    X_ref  = X_raw[norm_mask]
    mu_ref = X_ref.reshape(-1, d).mean(axis=0)
    sd_ref = X_ref.reshape(-1, d).std(axis=0) + 1e-9
    X_std  = (X_raw - mu_ref) / sd_ref
    print(f"  Normal period: {n_norm}Q ({NORMAL_START} to {NORMAL_END})")

    # ------------------------------------------------------------------
    # 3. Network
    # ------------------------------------------------------------------
    print("\n[2/8] Building G-SIB Ledoit-Wolf network...")
    W, rho_star = lw_correlation_network(X_std)
    lmax        = spectral_radius(W)
    print(f"  rho*={rho_star:.4f}  lambdamax(W)={lmax:.4f}")

    # Region-level lambdamax
    for region in ["US", "EU", "Asia"]:
        sub = _region_subpanel(X_std, meta, region)
        if sub is not None and sub.shape[1] >= 2:
            W_sub, _ = lw_correlation_network(sub)
            lm_sub   = spectral_radius(W_sub)
            print(f"  lambdamax({region}): {lm_sub:.4f}  (N={sub.shape[1]})")

    # ------------------------------------------------------------------
    # 4. MFLS signal
    # ------------------------------------------------------------------
    print("\n[3/8] Fitting BSDT and computing MFLS signal...")
    bsdt = BSDTOperator()
    bsdt.fit(X_std[norm_mask])
    mfls_signal = np.array([bsdt.mfls_score(X_std[t]) for t in range(T)])
    print(f"  MFLS range: [{mfls_signal.min():.3f}, {mfls_signal.max():.3f}]")

    # Region-level signals
    region_signals = {}
    for region in ["US", "EU", "Asia"]:
        sub = _region_subpanel(X_std, meta, region)
        if sub is not None and sub.shape[1] >= 2:
            bsdt_r = BSDTOperator()
            bsdt_r.fit(sub[norm_mask])
            sig_r = np.array([bsdt_r.mfls_score(sub[t]) for t in range(T)])
            region_signals[region] = sig_r
            print(f"  {region} MFLS range: [{sig_r.min():.3f}, {sig_r.max():.3f}]")

    # ------------------------------------------------------------------
    # 5. Crisis labels
    # ------------------------------------------------------------------
    crisis_labels = _make_crisis_labels(dates)
    print(f"\n[4/8] Crisis labels: {crisis_labels.sum()} crisis quarters / {T} total")

    # ------------------------------------------------------------------
    # 6. OOS backtest
    # ------------------------------------------------------------------
    print("\n[5/8] OOS backtest...")
    # Use pre-GFC data only for threshold
    pre07   = dates < pd.Timestamp("2007-01-01")
    if pre07.sum() < 4:
        # Very short pre-crisis window; use first 50% of data
        pre07 = np.zeros(T, dtype=bool)
        pre07[:T // 2] = True
    p75_thr = float(np.percentile(mfls_signal[pre07], 75))

    post07     = dates >= pd.Timestamp("2007-01-01")
    gfc_window = (dates >= pd.Timestamp("2007-10-01")) & \
                 (dates <= pd.Timestamp("2009-12-31"))
    alarm_idx  = np.where(post07 & (mfls_signal > p75_thr))[0]
    first_alarm = dates[alarm_idx[0]] if len(alarm_idx) else None
    gfc_hr      = float((mfls_signal[gfc_window] > p75_thr).mean()) if gfc_window.any() else 0.0
    lehman      = pd.Timestamp("2008-09-15")
    lead_q      = int(round((lehman - first_alarm).days / 91.25)) if first_alarm else 0

    oos = {
        "first_alarm":   str(first_alarm),
        "lead_quarters": lead_q,
        "gfc_hit_rate":  round(gfc_hr, 4),
        "p75_threshold": round(p75_thr, 4),
    }
    print(f"  First alarm: {first_alarm}  Lead: {lead_q}Q  GFC HR={gfc_hr:.1%}")

    # ------------------------------------------------------------------
    # 7. Bootstrap CIs
    # ------------------------------------------------------------------
    print(f"\n[6/8] Block-bootstrap CIs (B={n_boot}, L={boot_block_len}Q)...")
    ci_global = block_bootstrap_ci(
        signal=mfls_signal, labels=crisis_labels, threshold=p75_thr,
        n_boot=n_boot, block_len=boot_block_len, alpha=0.05, verbose=True,
    )

    ci_by_region = {}
    for region, sig_r in region_signals.items():
        print(f"  -- Region: {region}")
        p75_r = float(np.percentile(sig_r[pre07], 75))
        ci_by_region[region] = block_bootstrap_ci(
            signal=sig_r, labels=crisis_labels, threshold=p75_r,
            n_boot=n_boot, block_len=boot_block_len, alpha=0.05, verbose=True,
        )

    # ------------------------------------------------------------------
    # 8. Causality tests
    # ------------------------------------------------------------------
    print(f"\n[7/8] Causality analysis (B={n_boot_causality})...")
    causality = run_all_causality_tests(
        mfls_signal=mfls_signal, crisis_labels=crisis_labels, dates=dates,
        lags=[1, 2, 4], n_boot=n_boot_causality,
        out_path=RESULTS_DIR / "causality_gsib_real.json", verbose=True,
    )

    # ------------------------------------------------------------------
    # 9. Eval protocol + robustness
    # ------------------------------------------------------------------
    print("\n[8/8] Standard eval + robustness...")
    eval_results = eval_all_variants(
        signals_dict={"MFLS_RealGSIB": mfls_signal},
        dates=dates,
        thresholds={"MFLS_RealGSIB": p75_thr},
        crisis_windows=CRISIS_WINDOWS_EVAL,
        out_path=RESULTS_DIR / "eval_protocol_gsib_real.json",
    )
    rob = run_all_robustness(
        X_std, dates, mfls_signal,
        out_path=RESULTS_DIR / "robustness_gsib_real.json",
    )

    ep = eval_results["MFLS_RealGSIB"]["primary"]

    # ------------------------------------------------------------------
    # Save summary
    # ------------------------------------------------------------------
    summary = {
        "data_source": "REAL DATA: FDIC call-report (US) + World Bank GFDD + ECB MIR (non-US)",
        "NO_SYNTHETIC_DATA": True,
        "T_quarters": T,
        "date_range": f"{dates[0].date()} to {dates[-1].date()}",
        "N_gsib": N,
        "n_us_real_fdic": panel["n_us"],
        "n_nonus_real_worldbank": panel["n_non_us"],
        "d_features": d,
        "lambda_max_W": float(lmax),
        "rho_star": float(rho_star),
        "auroc": float(ep["auroc"]),
        "auroc_95ci": [ci_global["auroc_lo"], ci_global["auroc_hi"]],
        "hit_rate": float(ep["hr"]),
        "hit_rate_95ci": [ci_global["hr_lo"], ci_global["hr_hi"]],
        "false_alarm_rate": float(ep["far"]),
        "lead_quarters_gfc": lead_q,
        "gfc_alarm_date": str(first_alarm),
        "causality": {
            "linear_granger_min_p":    causality["summary"]["linear_granger_min_p"],
            "linear_verdict":          causality["summary"]["linear_granger_verdict"],
            "threshold_granger_min_p": causality["summary"]["threshold_granger_min_p"],
            "threshold_verdict":       causality["summary"]["threshold_verdict"],
            "quantile_min_p":          causality["summary"]["quantile_min_p"],
            "quantile_verdict":        causality["summary"]["quantile_verdict"],
        },
        "region_auroc": {},
        "bank_meta": meta,
        "runtime_sec": round(time.time() - t0, 1),
    }

    # Region AUROCs
    for region, sig_r in region_signals.items():
        r_labels = crisis_labels
        r_roc = roc_auprc(sig_r, r_labels)
        summary["region_auroc"][region] = round(r_roc["auroc"], 4)

    stats_path = RESULTS_DIR / "pipeline_stats_gsib_real.json"
    with open(stats_path, "w") as f:
        json.dump(summary, f, indent=2, default=lambda o: float(o) if hasattr(o, '__float__') else str(o))
    print(f"\n  Saved -> {stats_path}")

    # ------------------------------------------------------------------
    # Print summary
    # ------------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"  G-SIB REAL DATA PIPELINE RESULTS")
    print(f"{'='*70}")
    print(f"  Panel:    T={T}, N={N} (US FDIC={panel['n_us']}, Non-US WB={panel['n_non_us']})")
    print(f"  lambdamax(W) = {lmax:.3f}")
    print(f"  OOS alarm:   {first_alarm}  lead={lead_q}Q  GFC HR={gfc_hr:.1%}")
    print(f"")
    print(f"  AUROC: {ep['auroc']:.4f}  [{ci_global['auroc_lo']:.4f}, {ci_global['auroc_hi']:.4f}]")
    print(f"  HR:    {ep['hr']:.4f}     [{ci_global['hr_lo']:.4f}, {ci_global['hr_hi']:.4f}]")
    print(f"  FAR:   {ep['far']:.4f}    [{ci_global['far_lo']:.4f}, {ci_global['far_hi']:.4f}]")
    print(f"")
    for region in ["US", "EU", "Asia"]:
        if region in summary["region_auroc"]:
            r_auroc = summary["region_auroc"][region]
            r_ci = ci_by_region.get(region, {})
            lo = r_ci.get("auroc_lo", "?")
            hi = r_ci.get("auroc_hi", "?")
            print(f"  Region {region}: AUROC={r_auroc:.4f}  [{lo}, {hi}]")
    print(f"")
    print(f"  Causality:  Linear Granger {causality['summary']['linear_granger_verdict']}")
    print(f"              Threshold {causality['summary']['threshold_verdict']} (p={causality['summary']['threshold_granger_min_p']:.4f})")
    print(f"              Quantile  {causality['summary']['quantile_verdict']} (p={causality['summary']['quantile_min_p']:.4f})")
    print(f"")
    print(f"  Output: {RESULTS_DIR}")
    print(f"  Runtime: {time.time()-t0:.1f}s")
    print(f"{'='*70}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_boot", type=int, default=1000)
    parser.add_argument("--n_boot_causality", type=int, default=2000)
    parser.add_argument("--force_refresh", action="store_true")
    args = parser.parse_args()
    main(
        n_boot=args.n_boot,
        n_boot_causality=args.n_boot_causality,
        force_refresh=args.force_refresh,
    )
