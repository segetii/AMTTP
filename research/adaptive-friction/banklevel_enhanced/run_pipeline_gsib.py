"""
run_pipeline_gsib.py
====================
MFLS pipeline on the Global Systemically Important Bank (G-SIB) panel.

Scope upgrade over banklevel (N=30 US banks):
  N ~ 22 G-SIBs spanning US, Europe, Asia (FSB list 2023)
  US Tier-1 banks: real FDIC call-report data
  Non-US Tier-2:  synthetic BIS proxies (clearly labelled)

This tests the paper's core claim that the BSDT framework detects
cross-border systemic risk -- not just US-domestic leverage cycles.

Produces
--------
  results/gsib/pipeline_stats_gsib.json
  results/gsib/bootstrap_ci_gsib.json
  results/gsib/causality_gsib.json
  results/gsib/eval_table_gsib.tex
  results/gsib/comp_gsib_vs_banklevel.json    <- comparison table

Usage
-----
    python run_pipeline_gsib.py
    python run_pipeline_gsib.py --force_refresh --n_boot 500
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
from gravity_engine    import BSDTOperator, analyse_trajectory, ALPHA
from eval_protocol     import (
    eval_all_variants,
    latex_eval_table,
    CRISIS_WINDOWS_EVAL,
    build_binary_labels,
)
from robustness_checks import run_all_robustness

from bootstrap_auroc   import block_bootstrap_ci, latex_bootstrap_table
from threshold_granger import run_all_causality_tests, latex_causality_table
from gsib_loader       import build_gsib_panel, FEATURE_NAMES
from robustness_checks import run_all_robustness, latex_robustness_table

RESULTS_DIR = THIS_DIR / "results" / "gsib"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

NORMAL_START = "1994-01-01"
NORMAL_END   = "2003-12-31"

def _make_crisis_labels(dates: pd.DatetimeIndex) -> np.ndarray:
    """Binary labels aligned with the paper's evaluation protocol windows."""
    return build_binary_labels(dates, CRISIS_WINDOWS_EVAL, shift_quarters=0)


# ---------------------------------------------------------------------------
# Region-level decomposition helper
# ---------------------------------------------------------------------------
def _region_subpanel(X_std: np.ndarray, meta: list, region: str) -> np.ndarray:
    """Return standardised panel slice for a specific region."""
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
    print("  MFLS G-SIB Pipeline  (Global Systemically Important Banks)")
    print("  FSB 2023 list  |  US: FDIC  |  Non-US: BIS synthetic proxy")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 1. Load G-SIB panel
    # ------------------------------------------------------------------
    print("\n[1/8] Building G-SIB panel...")
    panel  = build_gsib_panel(force_refresh=force_refresh, verbose=True)
    X_raw  = panel["X"]         # (T, N, d=5)
    dates  = panel["dates"]
    meta   = panel["meta"]
    N      = panel["n_gsib"]
    T, _, d_base = X_raw.shape
    print(f"\n  Panel: T={T}, N={N}, d={d_base}")
    print(f"  US real FDIC: {panel['n_us']}  |  Non-US synthetic: {panel['n_non_us']}")

    # ------------------------------------------------------------------
    # 2. Standardise on normal period
    # ------------------------------------------------------------------
    norm_mask = (dates >= pd.Timestamp(NORMAL_START)) & \
                (dates <= pd.Timestamp(NORMAL_END))
    X_ref  = X_raw[norm_mask]
    mu_ref = X_ref.reshape(-1, d_base).mean(axis=0)
    sd_ref = X_ref.reshape(-1, d_base).std(axis=0) + 1e-9
    X_std  = (X_raw - mu_ref) / sd_ref
    print(f"  Normal period: {norm_mask.sum()}Q  ({NORMAL_START} - {NORMAL_END})")

    # ------------------------------------------------------------------
    # 3. Ledoit-Wolf network (global)
    # ------------------------------------------------------------------
    print("\n[2/8] Building global G-SIB Ledoit-Wolf network...")
    W, rho_star = lw_correlation_network(X_std)
    lmax        = spectral_radius(W)
    print(f"  rho*={rho_star:.4f}  lambdamax(W)={lmax:.4f}")
    print(f"  Baseline (US N=30): lambdamax was ~12.1  --  "
          f"G-SIB: {lmax:.3f} {'(higher = more integrated)' if lmax > 12.1 else '(lower = more diverse)'}")

    # Region-level lambdamax
    for region in ["US", "EU", "Asia"]:
        sub = _region_subpanel(X_std, meta, region)
        if sub is not None and sub.shape[1] >= 2:
            W_sub, _ = lw_correlation_network(sub)
            lm_sub   = spectral_radius(W_sub)
            print(f"  lambdamax({region}): {lm_sub:.4f}  (N={sub.shape[1]})")

    # ------------------------------------------------------------------
    # 4. MFLS signal (full G-SIB panel)
    # ------------------------------------------------------------------
    print("\n[3/8] Fitting BSDT on normal period and computing MFLS signal...")
    bsdt        = BSDTOperator()
    bsdt.fit(X_std[norm_mask])
    mfls_signal = np.array([bsdt.mfls_score(X_std[t]) for t in range(T)])
    print(f"  MFLS range: [{mfls_signal.min():.3f}, {mfls_signal.max():.3f}]")

    # Region-level MFLS signals
    region_signals = {}
    for region in ["US", "EU", "Asia"]:
        sub = _region_subpanel(X_std, meta, region)
        if sub is not None and sub.shape[1] >= 2:
            bsdt_r = BSDTOperator()
            bsdt_r.fit(sub[norm_mask])
            sig_r  = np.array([bsdt_r.mfls_score(sub[t]) for t in range(T)])
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
    pre07   = dates < pd.Timestamp("2007-01-01")
    p75_thr = float(np.percentile(mfls_signal[pre07], 75))

    post07     = dates >= pd.Timestamp("2007-01-01")
    gfc_window = (dates >= pd.Timestamp("2007-01-01")) & \
                 (dates <= pd.Timestamp("2009-12-31"))
    alarm_idx  = np.where(post07 & (mfls_signal > p75_thr))[0]
    first_alarm = dates[alarm_idx[0]] if len(alarm_idx) else None
    gfc_hr      = float((mfls_signal[gfc_window] > p75_thr).mean())
    lehman      = pd.Timestamp("2008-09-15")
    lead_q      = int(round((lehman - first_alarm).days / 91.25)) if first_alarm else 0

    oos = {
        "first_alarm":   str(first_alarm),
        "lead_quarters": lead_q,
        "gfc_hit_rate":  round(gfc_hr, 4),
        "p75_threshold": round(p75_thr, 4),
    }
    print(f"  First alarm: {first_alarm}  Lead: {lead_q}Q  HR={gfc_hr:.1%}")

    # ------------------------------------------------------------------
    # 7. Bootstrap CIs (global + per-region)
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

    all_ci = {"G-SIB Global": ci_global, **{f"G-SIB {r}": v for r, v in ci_by_region.items()}}

    ci_path = RESULTS_DIR / "bootstrap_ci_gsib.json"
    with open(ci_path, "w") as f:
        json.dump(all_ci, f, indent=2)

    ci_table = latex_bootstrap_table(all_ci)
    (RESULTS_DIR / "bootstrap_ci_gsib_table.tex").write_text(ci_table)

    # ------------------------------------------------------------------
    # 8. Causality tests
    # ------------------------------------------------------------------
    print(f"\n[7/8] Causality analysis (B={n_boot_causality})...")
    causality = run_all_causality_tests(
        mfls_signal   = mfls_signal,
        crisis_labels = crisis_labels,
        dates         = dates,
        lags          = [1, 2, 4],
        n_boot        = n_boot_causality,
        out_path      = RESULTS_DIR / "causality_gsib.json",
        verbose       = True,
    )

    caus_table = latex_causality_table(causality)
    (RESULTS_DIR / "causality_table_gsib.tex").write_text(caus_table)

    # ------------------------------------------------------------------
    # 9. Eval protocol + robustness
    # ------------------------------------------------------------------
    print("\n[8/8] Standard eval + robustness...")
    eval_results = eval_all_variants(
        signals_dict  = {"MFLS_GSIB": mfls_signal},
        dates         = dates,
        thresholds    = {"MFLS_GSIB": p75_thr},
        crisis_windows= CRISIS_WINDOWS_EVAL,
        out_path      = RESULTS_DIR / "eval_protocol_gsib.json",
    )
    rob_results = run_all_robustness(
        X_std, dates, mfls_signal,
        out_path = RESULTS_DIR / "robustness_gsib.json",
    )

    ep = eval_results["MFLS_GSIB"]["primary"]

    # LaTeX tables
    eval_tex = latex_eval_table(eval_results)
    rob_tex  = latex_robustness_table(rob_results)
    (RESULTS_DIR / "eval_table_gsib.tex").write_text(eval_tex)
    (RESULTS_DIR / "robustness_table_gsib.tex").write_text(rob_tex)

    # ------------------------------------------------------------------
    # 10. Comparison: G-SIB vs original N=30 US-only
    # ------------------------------------------------------------------
    # Load original results if available
    orig_path = THIS_DIR.parent / "banklevel" / "results" / "pipeline_stats_banklevel.json"
    orig_auroc = None
    orig_lead  = None
    orig_lmax  = None
    if orig_path.exists():
        with open(orig_path) as f:
            orig = json.load(f)
        orig_auroc = orig.get("auroc")
        orig_lead  = orig.get("time_to_alarm_gfc")
        orig_lmax  = orig.get("lambda_max_W")

    comp = {
        "banklevel_N30_US_only": {
            "N":         30,
            "auroc":     orig_auroc,
            "lead_q":    orig_lead,
            "lambda_max":orig_lmax,
            "scope":     "US banks only (FDIC call-report)",
        },
        "gsib_global": {
            "N":         N,
            "auroc":     ci_global["auroc"],
            "auroc_95ci":[ci_global["auroc_lo"], ci_global["auroc_hi"]],
            "lead_q":    lead_q,
            "lambda_max":float(lmax),
            "scope":     "G-SIBs global (US FDIC + Non-US synthetic proxy)",
        },
    }
    for region, ci_r in ci_by_region.items():
        comp[f"gsib_{region.lower()}"] = {
            "N":         sum(1 for m in meta if m["region"] == region),
            "auroc":     ci_r["auroc"],
            "auroc_95ci":[ci_r["auroc_lo"], ci_r["auroc_hi"]],
            "scope":     f"G-SIBs {region} only",
        }

    comp_path = RESULTS_DIR / "comp_gsib_vs_banklevel.json"
    with open(comp_path, "w") as f:
        json.dump(comp, f, indent=2)

    # ------------------------------------------------------------------
    # Master summary
    # ------------------------------------------------------------------
    summary = {
        "data_source":       "G-SIB panel (FSB 2023 list)",
        "T_quarters":        int(T),
        "N_gsib":            int(N),
        "n_us_real":         int(panel["n_us"]),
        "n_non_us_synthetic":int(panel["n_non_us"]),
        "d_features":        int(d_base),
        "lambda_max_W":      float(lmax),
        "rho_star":          float(rho_star),
        "auroc":             ci_global["auroc"],
        "auroc_95ci":        [ci_global["auroc_lo"], ci_global["auroc_hi"]],
        "hit_rate":          ci_global["hr"],
        "hit_rate_95ci":     [ci_global["hr_lo"], ci_global["hr_hi"]],
        "false_alarm_rate":  ci_global["far"],
        "lead_quarters_gfc": lead_q,
        "gfc_alarm_date":    oos["first_alarm"],
        "causality": {
            "linear_granger_min_p":    causality["summary"]["linear_granger_min_p"],
            "linear_verdict":          causality["summary"]["linear_granger_verdict"],
            "threshold_granger_min_p": causality["summary"]["threshold_granger_min_p"],
            "threshold_verdict":       causality["summary"]["threshold_verdict"],
            "quantile_min_p":          causality["summary"]["quantile_min_p"],
            "quantile_verdict":        causality["summary"]["quantile_verdict"],
        },
        "region_auroc": {r: ci_by_region[r]["auroc"] for r in ci_by_region},
        "runtime_sec":  round(time.time() - t0, 1),
    }

    with open(RESULTS_DIR / "pipeline_stats_gsib.json", "w") as f:
        json.dump(summary, f, indent=2, default=lambda o: str(o))

    # ------------------------------------------------------------------
    # Print
    # ------------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"  G-SIB PIPELINE RESULTS")
    print(f"{'='*70}")
    print(f"  Panel:    T={T}, N={N} (US real={panel['n_us']}, non-US proxy={panel['n_non_us']})")
    print(f"  lambdamax(W) = {lmax:.3f}")
    print(f"  OOS alarm:   {oos['first_alarm']}  lead={lead_q}Q  HR={gfc_hr:.1%}")
    print(f"")
    print(f"  AUROC: {ci_global['auroc']:.4f}  [{ci_global['auroc_lo']:.4f}, {ci_global['auroc_hi']:.4f}]")
    print(f"  HR:    {ci_global['hr']:.4f}     [{ci_global['hr_lo']:.4f}, {ci_global['hr_hi']:.4f}]")
    print(f"  FAR:   {ci_global['far']:.4f}    [{ci_global['far_lo']:.4f}, {ci_global['far_hi']:.4f}]")
    print(f"")
    print(f"  Region AUROC: " +
          "  ".join(f"{r}={ci_by_region[r]['auroc']:.3f}" for r in ci_by_region))
    print(f"")
    print(f"  Causality:  Linear Granger {summary['causality']['linear_verdict']}")
    print(f"              Threshold {summary['causality']['threshold_verdict']}"
          f"  (p={summary['causality']['threshold_granger_min_p']:.4f})")
    print(f"              Quantile  {summary['causality']['quantile_verdict']}"
          f"  (p={summary['causality']['quantile_min_p']:.4f})")
    print(f"")
    print(f"  vs. original N=30 US-only: lambdamax was ~12.1, AUROC ~0.805")
    print(f"  Output: {RESULTS_DIR}")
    print(f"  Runtime: {summary['runtime_sec']}s")
    print(f"{'='*70}")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MFLS G-SIB Pipeline")
    parser.add_argument("--n_boot",           type=int,  default=1000)
    parser.add_argument("--boot_block_len",   type=int,  default=8)
    parser.add_argument("--n_boot_causality", type=int,  default=2000)
    parser.add_argument("--force_refresh",    action="store_true")
    args = parser.parse_args()

    main(
        n_boot           = args.n_boot,
        boot_block_len   = args.boot_block_len,
        n_boot_causality = args.n_boot_causality,
        force_refresh    = args.force_refresh,
    )
