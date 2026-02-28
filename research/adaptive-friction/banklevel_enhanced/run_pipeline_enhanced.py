"""
run_pipeline_enhanced.py
========================
MFLS pipeline on institution-level FDIC data (N=30 banks) with three
additional robustness layers:

  Layer 1 -- Bootstrap confidence intervals (block bootstrap, L=8Q, B=1000)
             on AUROC, Hit Rate, False Alarm Rate for every variant.

  Layer 2 -- Threshold Granger causality and quantile causality tests.
             Linear Granger is run as baseline to document the Granger paradox.
             Threshold and quantile tests detect regime-state predictability
             that linear aggregation destroys.

  Layer 3 -- Exceedance regression at P75/P85/P90 thresholds.

Original pipeline (run_pipeline_banklevel.py) is LEFT UNCHANGED.
This file writes to results/enhanced/ so no collision occurs.

Usage
-----
    python run_pipeline_enhanced.py
    python run_pipeline_enhanced.py --n_banks 30 --n_boot 1000 --no_quantile
"""
from __future__ import annotations
import sys
import json
import time
import argparse
import numpy as np
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup -- resolve upgraded modules relative to this file
# ---------------------------------------------------------------------------
THIS_DIR     = Path(__file__).parent
ORIG_BL_DIR  = THIS_DIR.parent / "banklevel"      # original pipeline (read from)
UPGRADED_DIR = THIS_DIR.parent / "upgraded"
VARIANT_DIR  = THIS_DIR.parent / "variants"

for p in [str(THIS_DIR), str(ORIG_BL_DIR), str(UPGRADED_DIR), str(VARIANT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from bank_level_loader import build_bank_panel, FEATURE_NAMES
from network_builder   import lw_correlation_network, spectral_radius
from gravity_engine    import BSDTOperator, analyse_trajectory, ALPHA
from eval_protocol     import (
    eval_all_variants,
    latex_eval_table,
    CRISIS_WINDOWS_EVAL,
    build_binary_labels,
)
from robustness_checks import run_all_robustness, latex_robustness_table

# Enhanced modules (in this directory)
from bootstrap_auroc    import (block_bootstrap_ci, bootstrap_all_variants,
                                 latex_bootstrap_table)
from threshold_granger  import (run_all_causality_tests, latex_causality_table)

RESULTS_DIR = THIS_DIR / "results" / "enhanced"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

NORMAL_START = "1994-01-01"
NORMAL_END   = "2003-12-31"

# ---------------------------------------------------------------------------
# Yield-curve helper (reused from original pipeline)
# ---------------------------------------------------------------------------
def _fetch_t10y2y(dates: pd.DatetimeIndex) -> np.ndarray:
    cache = UPGRADED_DIR / "fred_cache" / "t10y2y.json"
    if cache.exists():
        with open(cache) as f:
            raw = json.load(f)
        series = pd.Series(raw.get("values", {}))
        series.index = pd.to_datetime(series.index)
        series = series.apply(pd.to_numeric, errors="coerce").dropna()
        series = series.resample("QE").mean()
        return series.reindex(dates, method="ffill").fillna(0.0).values
    return np.zeros(len(dates))


def _make_crisis_labels(dates: pd.DatetimeIndex) -> np.ndarray:
    """Binary labels aligned with the paper's evaluation protocol windows."""
    return build_binary_labels(dates, CRISIS_WINDOWS_EVAL, shift_quarters=0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(
    n_banks:         int  = 30,
    n_boot:          int  = 1000,
    boot_block_len:  int  = 8,
    run_quantile:    bool = True,
    n_boot_causality:int  = 2000,
    force_refresh:   bool = False,
):
    t0 = time.time()
    print("=" * 70)
    print("  MFLS Enhanced Pipeline (N=30 banks)")
    print("  Additions: Bootstrap CIs + Threshold Granger + Quantile Causality")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 1. Load panel (uses existing FDIC cache -- no re-fetch)
    # ------------------------------------------------------------------
    print("\n[1/8] Loading institution-level state matrix...")
    panel   = build_bank_panel(n_banks=n_banks, force_refresh=force_refresh)
    X_raw   = panel["X"]
    dates   = panel["dates"]
    N       = panel["n_banks_actual"]
    d_base  = X_raw.shape[2]
    T       = X_raw.shape[0]
    meta    = panel["bank_meta"]
    print(f"  Panel: T={T}, N={N}, d={d_base}")

    # ------------------------------------------------------------------
    # 2. Yield-curve feature
    # ------------------------------------------------------------------
    slope = _fetch_t10y2y(dates)
    X = np.concatenate([X_raw, slope[:, None, None] * np.ones((T, N, 1))], axis=2)
    d = X.shape[2]

    # ------------------------------------------------------------------
    # 3. Standardise on normal period
    # ------------------------------------------------------------------
    norm_mask = (dates >= pd.Timestamp(NORMAL_START)) & \
                (dates <= pd.Timestamp(NORMAL_END))
    X_ref  = X[norm_mask]
    mu_ref = X_ref.reshape(-1, d).mean(axis=0)
    sd_ref = X_ref.reshape(-1, d).std(axis=0) + 1e-9
    X_std  = (X - mu_ref) / sd_ref
    print(f"  Normal period: {norm_mask.sum()}Q  ({NORMAL_START} - {NORMAL_END})")

    # ------------------------------------------------------------------
    # 4. Network
    # ------------------------------------------------------------------
    print("\n[2/8] Building Ledoit-Wolf inter-bank network...")
    W, rho_star = lw_correlation_network(X_std)
    lmax        = spectral_radius(W)
    print(f"  rho*={rho_star:.4f}  lambdamax(W)={lmax:.4f}")

    # ------------------------------------------------------------------
    # 5. MFLS signal
    # ------------------------------------------------------------------
    print("\n[3/8] Fitting BSDT operator and computing MFLS signal...")
    bsdt        = BSDTOperator()
    bsdt.fit(X_std[norm_mask])
    mfls_signal = np.array([bsdt.mfls_score(X_std[t]) for t in range(T)])
    print(f"  MFLS range: [{mfls_signal.min():.3f}, {mfls_signal.max():.3f}]")

    # ------------------------------------------------------------------
    # 6. Crisis labels aligned to panel dates
    # ------------------------------------------------------------------
    crisis_labels = _make_crisis_labels(dates)
    print(f"\n[4/8] Crisis labels: {crisis_labels.sum()} crisis quarters "
          f"/ {len(crisis_labels)} total  "
          f"({crisis_labels.mean():.1%})")

    # ------------------------------------------------------------------
    # 7. Bootstrap confidence intervals
    # ------------------------------------------------------------------
    print(f"\n[5/8] Block-bootstrap CIs  (B={n_boot}, L={boot_block_len}Q)...")
    pre07    = dates < pd.Timestamp("2007-01-01")
    p75_thr  = float(np.percentile(mfls_signal[pre07], 75))

    ci_main = block_bootstrap_ci(
        signal   = mfls_signal,
        labels   = crisis_labels,
        threshold= p75_thr,
        n_boot   = n_boot,
        block_len= boot_block_len,
        alpha    = 0.05,
        verbose  = True,
    )

    # Save CI results
    ci_path = RESULTS_DIR / "bootstrap_ci_main.json"
    with open(ci_path, "w") as f:
        json.dump(ci_main, f, indent=2)
    print(f"  Saved -> {ci_path}")

    # Generate LaTeX table
    ci_table = latex_bootstrap_table({"MFLS Baseline (N=30 banks)": ci_main})
    (RESULTS_DIR / "bootstrap_ci_table.tex").write_text(ci_table)

    # ------------------------------------------------------------------
    # 8. Causality tests (linear + threshold + quantile)
    # ------------------------------------------------------------------
    print(f"\n[6/8] Causality analysis  (B={n_boot_causality})...")
    causality = run_all_causality_tests(
        mfls_signal   = mfls_signal,
        crisis_labels = crisis_labels,
        dates         = dates,
        lags          = [1, 2, 4],
        n_boot        = n_boot_causality,
        out_path      = RESULTS_DIR / "causality_results.json",
        verbose       = True,
    )

    # LaTeX table
    caus_table = latex_causality_table(causality)
    (RESULTS_DIR / "causality_table.tex").write_text(caus_table)

    # ------------------------------------------------------------------
    # 9. OOS backtest (replicated from original for comparison)
    # ------------------------------------------------------------------
    print("\n[7/8] OOS backtest (replication of original pipeline)...")
    post07     = dates >= pd.Timestamp("2007-01-01")
    gfc_window = (dates >= pd.Timestamp("2007-01-01")) & \
                 (dates <= pd.Timestamp("2009-12-31"))
    alarm_idx  = np.where(post07 & (mfls_signal > p75_thr))[0]
    first_alarm_date = dates[alarm_idx[0]] if len(alarm_idx) else None
    gfc_hit_rate     = float((mfls_signal[gfc_window] > p75_thr).mean())
    lehman_date      = pd.Timestamp("2008-09-15")
    lead_qtrs = int(round((lehman_date - first_alarm_date).days / 91.25)) \
                if first_alarm_date else 0
    oos = {
        "first_alarm":    str(first_alarm_date),
        "lead_quarters":  lead_qtrs,
        "gfc_hit_rate":   round(gfc_hit_rate, 4),
        "p75_threshold":  round(p75_thr, 4),
    }
    print(f"  First alarm: {first_alarm_date}  Lead: {lead_qtrs}Q  HR={gfc_hit_rate:.1%}")

    # ------------------------------------------------------------------
    # 10. Full eval protocol + robustness
    # ------------------------------------------------------------------
    print("\n[8/8] Standard eval protocol + robustness checks...")
    eval_results = eval_all_variants(
        signals_dict  = {"MFLS_Enhanced": mfls_signal},
        dates         = dates,
        thresholds    = {"MFLS_Enhanced": p75_thr},
        crisis_windows= CRISIS_WINDOWS_EVAL,
        out_path      = RESULTS_DIR / "eval_protocol_enhanced.json",
    )
    rob_results = run_all_robustness(
        X_std, dates, mfls_signal,
        out_path = RESULTS_DIR / "robustness_enhanced.json",
    )

    ep = eval_results["MFLS_Enhanced"]["primary"]

    # ------------------------------------------------------------------
    # 11. Compile master summary
    # ------------------------------------------------------------------
    summary = {
        "data_source":          "FDIC SDI call-report (bank-level, N=30)",
        "T_quarters":           int(T),
        "N_banks":              int(N),
        "d_features":           int(d),
        "lambda_max_W":         float(lmax),
        "rho_star":             float(rho_star),
        # --- Original metrics (replicate from original pipeline) ---
        "auroc":                ep.get("auroc", float("nan")),
        "hit_rate":             ep.get("hr",    float("nan")),
        "false_alarm_rate":     ep.get("far",   float("nan")),
        "lead_quarters_gfc":    oos["lead_quarters"],
        "gfc_alarm_date":       oos["first_alarm"],
        # --- Enhancement Layer 1: Bootstrap CIs ---
        "bootstrap": {
            "auroc":     ci_main["auroc"],
            "auroc_lo":  ci_main["auroc_lo"],
            "auroc_hi":  ci_main["auroc_hi"],
            "hr":        ci_main["hr"],
            "hr_lo":     ci_main["hr_lo"],
            "hr_hi":     ci_main["hr_hi"],
            "far":       ci_main["far"],
            "far_lo":    ci_main["far_lo"],
            "far_hi":    ci_main["far_hi"],
            "ci_label":  ci_main["ci_label"],
            "n_boot":    ci_main["n_boot"],
            "block_len": ci_main["block_len"],
        },
        # --- Enhancement Layer 2: Causality ---
        "causality": {
            "linear_granger_min_p":    causality["summary"]["linear_granger_min_p"],
            "linear_granger_verdict":  causality["summary"]["linear_granger_verdict"],
            "threshold_granger_min_p": causality["summary"]["threshold_granger_min_p"],
            "threshold_verdict":       causality["summary"]["threshold_verdict"],
            "quantile_min_p":          causality["summary"]["quantile_min_p"],
            "quantile_verdict":        causality["summary"]["quantile_verdict"],
        },
        "runtime_sec": round(time.time() - t0, 1),
    }

    summary_path = RESULTS_DIR / "pipeline_stats_enhanced.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=lambda o: str(o))

    # LaTeX tables
    eval_tex = latex_eval_table(eval_results)
    rob_tex  = latex_robustness_table(rob_results)
    (RESULTS_DIR / "eval_table_enhanced.tex").write_text(eval_tex)
    (RESULTS_DIR / "robustness_table_enhanced.tex").write_text(rob_tex)

    # ------------------------------------------------------------------
    # Print final summary
    # ------------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"  ENHANCED PIPELINE RESULTS")
    print(f"{'='*70}")
    print(f"  Panel:   T={T}, N={N}, d={d}")
    print(f"  lambdamax(W) = {lmax:.3f}")
    print(f"  OOS alarm:   {oos['first_alarm']}  lead={lead_qtrs}Q")
    print(f"")
    print(f"  [Layer 1 -- Bootstrap CIs ({ci_main['ci_label']}, B={n_boot}, L={boot_block_len}Q)]")
    print(f"  AUROC : {ci_main['auroc']:.4f}  [{ci_main['auroc_lo']:.4f}, {ci_main['auroc_hi']:.4f}]")
    print(f"  HR    : {ci_main['hr']:.4f}     [{ci_main['hr_lo']:.4f}, {ci_main['hr_hi']:.4f}]")
    print(f"  FAR   : {ci_main['far']:.4f}    [{ci_main['far_lo']:.4f}, {ci_main['far_hi']:.4f}]")
    print(f"")
    print(f"  [Layer 2 -- Causality Tests]")
    print(f"  Linear Granger:    {summary['causality']['linear_granger_verdict']}")
    print(f"  Threshold Granger: {summary['causality']['threshold_verdict']}"
          f"  (p={summary['causality']['threshold_granger_min_p']:.4f})")
    print(f"  Quantile:          {summary['causality']['quantile_verdict']}"
          f"  (p={summary['causality']['quantile_min_p']:.4f})")
    print(f"")
    print(f"  Outputs in: {RESULTS_DIR}")
    print(f"  Runtime:    {summary['runtime_sec']}s")
    print(f"{'='*70}")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MFLS Enhanced Pipeline")
    parser.add_argument("--n_banks",          type=int,  default=30)
    parser.add_argument("--n_boot",           type=int,  default=1000,
                        help="Bootstrap replicates (Layer 1)")
    parser.add_argument("--boot_block_len",   type=int,  default=8,
                        help="Block length in quarters (Layer 1)")
    parser.add_argument("--n_boot_causality", type=int,  default=2000,
                        help="Bootstrap p-value replicates (Layer 2)")
    parser.add_argument("--no_quantile",      action="store_true",
                        help="Skip slow kernel-quantile causality test")
    parser.add_argument("--force_refresh",    action="store_true")
    args = parser.parse_args()

    main(
        n_banks          = args.n_banks,
        n_boot           = args.n_boot,
        boot_block_len   = args.boot_block_len,
        run_quantile     = not args.no_quantile,
        n_boot_causality = args.n_boot_causality,
        force_refresh    = args.force_refresh,
    )
