"""
run_causality_extended.py
=========================
Full causality test battery on the FDIC bank-level MFLS signal.

Runs:
  A. Existing linear / threshold suite (threshold_granger.py):
     - Linear VAR-Granger (baseline, expected to fail)
     - Threshold Granger (Hansen-Seo style, upper-regime)
     - Quantile causality (Jeong-Hardle-Song, nonparametric kernel)
     - Exceedance regression (logistic)

  B. Extended nonlinear suite (nonlinear_causality.py):
     - HSIC-Granger (kernel independence of nonlinear AR residuals)
     - Transfer Entropy KSG (k-NN directed information)
     - Convergent Cross Mapping (Sugihara 2012 state-space)
     - Lagged MI profile (KSG, lags 1-8)
     - NN-Granger (MLP residual comparison)
     - Direction check (forward vs. reverse)

  C. Combined LaTeX table across both suites.

Usage:
    python run_causality_extended.py
    python run_causality_extended.py --n_perm 2000 --n_perm_nl 1000
    python run_causality_extended.py --lag 2
"""
from __future__ import annotations
import sys, json, time, argparse
import numpy as np
import pandas as pd
from pathlib import Path

THIS_DIR     = Path(__file__).parent
UPGRADED_DIR = THIS_DIR.parent / "upgraded"
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(UPGRADED_DIR))

from bank_level_loader import build_bank_panel
from network_builder   import lw_correlation_network, spectral_radius, leading_eigenvec
from gravity_engine    import BSDTChannelOperator, ALPHA
from eval_protocol     import build_binary_labels, CRISIS_WINDOWS_EVAL
from threshold_granger import (run_all_causality_tests, latex_causality_table)
from nonlinear_causality import (run_nonlinear_causality_suite,
                                  latex_nonlinear_causality_table)

RESULTS_DIR  = THIS_DIR / "results" / "causality"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

NORMAL_START = "1994-01-01"
NORMAL_END   = "2003-12-31"


def _build_mfls(n_banks: int = 30, force_refresh: bool = False):
    """Rebuild FDIC panel and MFLS signal (uses cache if available)."""
    print("[setup] Loading FDIC bank panel ...")
    panel = build_bank_panel(n_banks=n_banks, force_refresh=force_refresh)
    X_raw = panel["X"]
    dates = panel["dates"]
    N     = panel["n_banks_actual"]
    T, _, d_base = X_raw.shape

    # Yield-curve append
    slope_cache = UPGRADED_DIR / "fred_cache" / "t10y2y.json"
    if slope_cache.exists():
        with open(slope_cache) as f:
            raw = json.load(f)
        s = pd.Series(raw.get("values", {}))
        s.index = pd.to_datetime(s.index)
        s = s.apply(pd.to_numeric, errors="coerce").dropna().resample("QE").mean()
        slope = s.reindex(dates, method="ffill").fillna(0.0).values
    else:
        slope = np.zeros(T)

    X = np.concatenate([X_raw, slope[:, None, None] * np.ones((T, N, 1))], axis=2)
    d = X.shape[2]

    norm_mask = (dates >= pd.Timestamp(NORMAL_START)) & (dates <= pd.Timestamp(NORMAL_END))
    X_ref  = X[norm_mask]
    mu_ref = X_ref.reshape(-1, d).mean(axis=0)
    sd_ref = X_ref.reshape(-1, d).std(axis=0) + 1e-9
    X_std  = (X - mu_ref) / sd_ref

    W, _  = lw_correlation_network(X_std)
    lmax  = spectral_radius(W)
    v_W   = leading_eigenvec(W)

    bsdt  = BSDTChannelOperator(v_W=v_W)
    bsdt.fit(X_std[norm_mask])
    mfls  = np.array([bsdt.mfls_score(X_std[t]) for t in range(T)])

    print(f"[setup] Panel: T={T}, N={N}, d={d}  lambdamax={lmax:.3f}")
    print(f"[setup] MFLS range: [{mfls.min():.3f}, {mfls.max():.3f}]")
    return mfls, dates, T, N


def main(
    n_banks:    int  = 30,
    lag:        int  = 1,
    n_perm:     int  = 2000,
    n_perm_nl:  int  = 500,
    force_refresh: bool = False,
):
    t0 = time.time()
    print("=" * 70)
    print("  Extended Causality Battery -- FDIC Bank-Level MFLS")
    print("  Suite A: Linear / Threshold / Quantile / Exceedance")
    print("  Suite B: HSIC-Granger / TE-KSG / CCM / MI / NN-Granger")
    print("=" * 70)

    # 1. Build MFLS signal
    mfls, dates, T, N = _build_mfls(n_banks=n_banks, force_refresh=force_refresh)

    # 2. Crisis labels
    crisis = build_binary_labels(dates, CRISIS_WINDOWS_EVAL, shift_quarters=0)
    print(f"\n  Crisis labels: {int(crisis.sum())} crisis quarters / {T} total")

    # -----------------------------------------------------------------------
    # SUITE A: Linear + threshold + quantile (existing module)
    # -----------------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"  SUITE A: Linear / Threshold / Quantile Causality  (n_perm={n_perm})")
    print(f"{'='*70}")
    suite_a = run_all_causality_tests(
        mfls_signal=mfls,
        crisis_labels=crisis,
        dates=dates,
        lags=[1, 2, 4],
        n_boot=n_perm,
        out_path=RESULTS_DIR / "suite_a_causality_fdic.json",
        verbose=True,
    )

    # -----------------------------------------------------------------------
    # SUITE B: Extended nonlinear suite
    # -----------------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"  SUITE B: Nonlinear Causality Suite  (n_perm_nl={n_perm_nl})")
    print(f"{'='*70}")
    suite_b = run_nonlinear_causality_suite(
        mfls_signal=mfls,
        crisis_labels=crisis,
        dates=dates,
        lag=lag,
        n_perm_hsic=n_perm_nl,
        n_perm_te=n_perm_nl // 2,
        n_perm_nn=n_perm_nl // 2,
        verbose=True,
        out_path=RESULTS_DIR / "suite_b_nonlinear_fdic.json",
    )

    # -----------------------------------------------------------------------
    # Combined summary
    # -----------------------------------------------------------------------
    sa_summ  = suite_a["summary"]
    sb_summ  = suite_b["summary"]

    combined_summary = {
        "data":  "FDIC bank-level, N=30, T=140Q",
        "suite_a": {
            "linear_granger_min_p":    sa_summ["linear_granger_min_p"],
            "linear_verdict":          sa_summ["linear_granger_verdict"],
            "threshold_granger_min_p": sa_summ["threshold_granger_min_p"],
            "threshold_verdict":       sa_summ["threshold_verdict"],
            "quantile_min_p":          sa_summ["quantile_min_p"],
            "quantile_verdict":        sa_summ["quantile_verdict"],
        },
        "suite_b": {
            "hsic_p":                  sb_summ["hsic_p"],
            "hsic_verdict":            suite_b["hsic_granger"]["verdict"],
            "te_x_to_y":              sb_summ["te_x_to_y"],
            "te_y_to_x":              sb_summ["te_y_to_x"],
            "te_p":                    sb_summ["te_p"],
            "te_verdict":              suite_b["transfer_entropy"]["verdict"],
            "ccm_peak_rho":            sb_summ["ccm_peak_rho_XfromY"],
            "ccm_convergent":          sb_summ["ccm_convergent"],
            "ccm_p":                   sb_summ["ccm_p"],
            "ccm_verdict":             suite_b["ccm"]["verdict"],
            "mi_peak_lag":             sb_summ["mi_peak_lag"],
            "mi_peak_val":             sb_summ["mi_peak_val"],
            "nn_granger_p":            sb_summ["nn_granger_p"],
            "nn_rss_reduction_pct":    sb_summ["nn_rss_reduction_pct"],
            "nn_verdict":              suite_b["nn_granger"]["verdict"],
            "direction_correct":       sb_summ["direction_correct"],
            "overall_verdict":         sb_summ["overall_verdict"],
        },
        "runtime_sec": round(time.time() - t0, 1),
    }

    out_path = RESULTS_DIR / "combined_causality_summary.json"
    with open(out_path, "w") as f:
        json.dump(combined_summary, f, indent=2,
                  default=lambda o: bool(o) if isinstance(o, (np.bool_,)) else
                           float(o) if hasattr(o, "__float__") else str(o))

    # LaTeX tables
    tex_a = latex_causality_table(suite_a)
    tex_b = latex_nonlinear_causality_table(suite_b)
    (RESULTS_DIR / "table_suite_a_causality.tex").write_text(tex_a)
    (RESULTS_DIR / "table_suite_b_nonlinear.tex").write_text(tex_b)

    # -----------------------------------------------------------------------
    # Final print
    # -----------------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"  COMBINED CAUSALITY BATTERY -- FINAL RESULTS")
    print(f"{'='*70}")
    print(f"  Data: FDIC bank-level N={N}, T={T}")
    print(f"")
    print(f"  --- Suite A: Linear / Parametric ---")
    print(f"  Linear VAR-Granger:       p={sa_summ['linear_granger_min_p']:.4f}  "
          f"[{sa_summ['linear_granger_verdict']}]")
    print(f"  Threshold Granger:        p={sa_summ['threshold_granger_min_p']:.4f}  "
          f"[{sa_summ['threshold_verdict']}]")
    print(f"  Quantile causality:       p={sa_summ['quantile_min_p']:.4f}  "
          f"[{sa_summ['quantile_verdict']}]")
    print(f"")
    print(f"  --- Suite B: Nonlinear / Nonparametric ---")
    sb = combined_summary["suite_b"]
    print(f"  HSIC-Granger:             p={sb['hsic_p']:.4f}  [{sb['hsic_verdict']}]")
    print(f"  Transfer Entropy (KSG):   p={sb['te_p']:.4f}  [{sb['te_verdict']}]  "
          f"TE(MFLS→)={sb['te_x_to_y']:.4f}  TE(←MFLS)={sb['te_y_to_x']:.4f}")
    print(f"  CCM (Sugihara):           p={sb['ccm_p']:.4f}  [{sb['ccm_verdict']}]  "
          f"peak_rho={sb['ccm_peak_rho']:.4f}  convergent={sb['ccm_convergent']}")
    print(f"  MI peak:                  lag={sb['mi_peak_lag']}  MI={sb['mi_peak_val']:.4f}")
    print(f"  NN-Granger:               p={sb['nn_granger_p']:.4f}  [{sb['nn_verdict']}]  "
          f"RSS reduction={sb['nn_rss_reduction_pct']:.1f}%")
    print(f"  Direction correct:        {sb['direction_correct']}  (MFLS leads crisis, not reverse)")
    print(f"")
    print(f"  Nonlinear suite overall:  {sb['overall_verdict']}")
    print(f"  Output:                   {RESULTS_DIR}")
    print(f"  Runtime: {time.time()-t0:.1f}s")
    print(f"{'='*70}")
    return combined_summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_banks",    type=int,  default=30)
    parser.add_argument("--lag",        type=int,  default=1)
    parser.add_argument("--n_perm",     type=int,  default=2000,
                        help="Bootstrap reps for Suite A (threshold/quantile)")
    parser.add_argument("--n_perm_nl",  type=int,  default=500,
                        help="Permutation reps for Suite B (HSIC/TE/NN)")
    parser.add_argument("--force_refresh", action="store_true")
    args = parser.parse_args()
    main(
        n_banks=args.n_banks,
        lag=args.lag,
        n_perm=args.n_perm,
        n_perm_nl=args.n_perm_nl,
        force_refresh=args.force_refresh,
    )
