"""
run_pipeline_banklevel.py  (canonical v2)
=========================================
Full canonical MFLS pipeline on institution-level FDIC call-report data.

Data: FDIC SDI -- top-30 US commercial banks, quarterly 1990-2024.
      Yield-curve slope appended as d+1 macro feature.

Capabilities (full parity with GSIB real pipeline):
  - 4-channel BSDTChannelOperator (§XXIV.4): C/G/A/T
  - Windowed MFLS_st with admissibility & safety ratios (§12)
  - Bank size-group sub-signals (Mega top-10 vs. Regional)
  - Block-bootstrap 95% CIs on AUROC / HR / FAR
  - Causality analysis (Linear Granger, Threshold Granger, Quantile)
  - Full eval protocol across all crisis windows
  - Robustness checks

Outputs: results/banklevel/
  pipeline_stats_banklevel.json
  bootstrap_ci_banklevel.json
  causality_banklevel.json
  eval_protocol_banklevel.json
  robustness_banklevel.json
  *.tex  (LaTeX tables)

Usage:
    python run_pipeline_banklevel.py
    python run_pipeline_banklevel.py --n_banks 30 --n_boot 1000 --n_boot_causality 2000
    python run_pipeline_banklevel.py --force_refresh
"""
from __future__ import annotations
import sys, json, time, argparse
import numpy as np
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
THIS_DIR     = Path(__file__).parent
UPGRADED_DIR = THIS_DIR.parent / "upgraded"
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(UPGRADED_DIR))

from bank_level_loader import build_bank_panel, FEATURE_NAMES
from network_builder   import lw_correlation_network, spectral_radius, leading_eigenvec
from gravity_engine    import BSDTChannelOperator, analyse_trajectory_full, ALPHA
from eval_protocol     import (eval_all_variants, latex_eval_table,
                               CRISIS_WINDOWS_EVAL, build_binary_labels, roc_auprc)
from robustness_checks import run_all_robustness, latex_robustness_table
from bootstrap_auroc   import block_bootstrap_ci, latex_bootstrap_table
from threshold_granger import run_all_causality_tests, latex_causality_table

RESULTS_DIR = THIS_DIR / "results" / "banklevel"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Normal period (pre-bubble, avoid GFC contamination)
# ---------------------------------------------------------------------------
NORMAL_START = "1994-01-01"
NORMAL_END   = "2003-12-31"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fetch_t10y2y(dates: pd.DatetimeIndex) -> np.ndarray:
    """Return T10Y2Y quarterly average aligned to dates (zeros if not cached)."""
    cache = UPGRADED_DIR / "fred_cache" / "t10y2y.json"
    if cache.exists():
        with open(cache) as f:
            raw = json.load(f)
        s = pd.Series(raw.get("values", {}))
        s.index = pd.to_datetime(s.index)
        s = s.apply(pd.to_numeric, errors="coerce").dropna()
        s = s.resample("QE").mean()
        return s.reindex(dates, method="ffill").fillna(0.0).values
    return np.zeros(len(dates))


def _size_subpanel(X_std: np.ndarray, meta: list, tier: str):
    """Return sub-panel for 'mega' (top-10 by asset rank) or 'regional' banks."""
    # meta list is already ranked by asset size descending (from FDIC query)
    n = len(meta)
    if tier == "mega":
        idx = list(range(min(10, n)))
    else:
        idx = list(range(min(10, n), n))
    if len(idx) < 2:
        return None
    return X_std[:, idx, :]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(
    n_banks:          int  = 30,
    n_boot:           int  = 1000,
    boot_block_len:   int  = 8,
    n_boot_causality: int  = 2000,
    force_refresh:    bool = False,
):
    t0 = time.time()
    print("=" * 70)
    print(f"  MFLS Bank-Level Pipeline -- CANONICAL v2  (N={n_banks} FDIC institutions)")
    print(f"  Data: FDIC SDI call-report, quarterly 1990-2024")
    print(f"  REAL DATA ONLY -- no synthetic data")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 1. Build institution-level state matrix
    # ------------------------------------------------------------------
    print("\n[1/9] Building institution-level state matrix ...")
    panel  = build_bank_panel(n_banks=n_banks, force_refresh=force_refresh)
    X_raw  = panel["X"]          # (T, N, d)
    dates  = panel["dates"]
    N      = panel["n_banks_actual"]
    T      = X_raw.shape[0]
    d_base = X_raw.shape[2]
    meta   = panel["bank_meta"]
    print(f"  Panel: T={T}, N={N}, d={d_base}  ({dates[0].date()} to {dates[-1].date()})")

    # ------------------------------------------------------------------
    # 2. Append yield-curve slope + standardise on normal period
    # ------------------------------------------------------------------
    slope = _fetch_t10y2y(dates)
    X = np.concatenate([X_raw, slope[:, None, None] * np.ones((T, N, 1))], axis=2)
    d = X.shape[2]
    print(f"  Features (base + yield-curve): d={d}")

    norm_mask = (dates >= pd.Timestamp(NORMAL_START)) & (dates <= pd.Timestamp(NORMAL_END))
    n_norm    = norm_mask.sum()
    X_ref     = X[norm_mask]
    mu_ref    = X_ref.reshape(-1, d).mean(axis=0)
    sd_ref    = X_ref.reshape(-1, d).std(axis=0) + 1e-9
    X_std     = (X - mu_ref) / sd_ref
    print(f"  Normal period: {n_norm}Q ({NORMAL_START} to {NORMAL_END})")

    # ------------------------------------------------------------------
    # 3. Ledoit-Wolf inter-bank network
    # ------------------------------------------------------------------
    print("\n[2/9] Building Ledoit-Wolf inter-bank network ...")
    W, rho_star = lw_correlation_network(X_std)
    lmax        = spectral_radius(W)
    v_W         = leading_eigenvec(W)
    print(f"  rho*={rho_star:.4f}  lambdamax(W)={lmax:.4f}")

    # Size-tier network lambdamax
    for tier in ["mega", "regional"]:
        sub = _size_subpanel(X_std, meta, tier)
        if sub is not None and sub.shape[1] >= 2:
            W_sub, _ = lw_correlation_network(sub)
            lm_sub   = spectral_radius(W_sub)
            label    = "Top-10 Mega" if tier == "mega" else f"Regional (N={sub.shape[1]})"
            print(f"  lambdamax({label}): {lm_sub:.4f}")

    # ------------------------------------------------------------------
    # 4. BSDT fit + MFLS signal + full 4-channel trajectory
    # ------------------------------------------------------------------
    print("\n[3/9] Fitting BSDT and computing canonical MFLS signal ...")
    bsdt = BSDTChannelOperator(v_W=v_W)
    bsdt.fit(X_std[norm_mask])
    mfls_signal = np.array([bsdt.mfls_score(X_std[t]) for t in range(T)])
    print(f"  MFLS range: [{mfls_signal.min():.3f}, {mfls_signal.max():.3f}]")

    print("  Running 4-channel admissibility analysis (§12, §XXIV.4)...")
    traj = analyse_trajectory_full(
        X_std, mu_ref, bsdt, lam_W=lmax,
        alpha=ALPHA, lead_window=4, theta=ALPHA, M_max=1.0,
    )
    print(f"  MFLS_st range: [{traj['mfls_st'].min():.3f}, {traj['mfls_st'].max():.3f}]  (physical-space)")
    print(f"  Inadmissible A>1: {np.mean(traj['admissibility']>1.0):.1%}   "
          f"Safe rho>=1: {np.mean(traj['safety']>=1.0):.1%}   "
          f"mean psi: {np.mean(traj['psi_deg']):.1f} deg")

    # ------------------------------------------------------------------
    # 5. Size-group sub-signals (Mega top-10 vs. Regional)
    # ------------------------------------------------------------------
    print("\n[4/9] Computing bank size-group sub-signals ...")
    tier_signals = {}
    for tier in ["mega", "regional"]:
        sub = _size_subpanel(X_std, meta, tier)
        if sub is not None and sub.shape[1] >= 2:
            bsdt_t = BSDTChannelOperator()
            bsdt_t.fit(sub[norm_mask])
            sig_t = np.array([bsdt_t.mfls_score(sub[t]) for t in range(T)])
            tier_signals[tier] = sig_t
            label = "Top-10 Mega" if tier == "mega" else f"Regional (N={sub.shape[1]})"
            print(f"  {label} MFLS range: [{sig_t.min():.3f}, {sig_t.max():.3f}]")

    # ------------------------------------------------------------------
    # 6. Crisis labels + OOS backtest
    # ------------------------------------------------------------------
    crisis_labels = build_binary_labels(dates, CRISIS_WINDOWS_EVAL, shift_quarters=0)
    print(f"\n[5/9] Crisis labels: {crisis_labels.sum()} crisis quarters / {T} total")

    print("  OOS backtest (p75 threshold, pre-2007 calibration)...")
    pre07      = dates < pd.Timestamp("2007-01-01")
    p75_thr    = float(np.percentile(mfls_signal[pre07], 75))
    post07     = dates >= pd.Timestamp("2007-01-01")
    gfc_window = (dates >= pd.Timestamp("2007-10-01")) & (dates <= pd.Timestamp("2009-12-31"))
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
    # 7. Block-bootstrap 95% CIs
    # ------------------------------------------------------------------
    print(f"\n[6/9] Block-bootstrap CIs (B={n_boot}, L={boot_block_len}Q)...")
    ci_global = block_bootstrap_ci(
        signal=mfls_signal, labels=crisis_labels, threshold=p75_thr,
        n_boot=n_boot, block_len=boot_block_len, alpha=0.05, verbose=True,
    )

    ci_by_tier = {}
    for tier, sig_t in tier_signals.items():
        label = "Mega" if tier == "mega" else "Regional"
        print(f"  -- Tier: {label}")
        p75_t = float(np.percentile(sig_t[pre07], 75))
        ci_by_tier[tier] = block_bootstrap_ci(
            signal=sig_t, labels=crisis_labels, threshold=p75_t,
            n_boot=n_boot, block_len=boot_block_len, alpha=0.05, verbose=True,
        )

    # ------------------------------------------------------------------
    # 8. Causality analysis
    # ------------------------------------------------------------------
    print(f"\n[7/9] Causality analysis (B={n_boot_causality})...")
    causality = run_all_causality_tests(
        mfls_signal=mfls_signal, crisis_labels=crisis_labels, dates=dates,
        lags=[1, 2, 4], n_boot=n_boot_causality,
        out_path=RESULTS_DIR / "causality_banklevel.json", verbose=True,
    )

    # ------------------------------------------------------------------
    # 9. Eval protocol + robustness
    # ------------------------------------------------------------------
    print("\n[8/9] Standard eval protocol + robustness ...")
    signals_dict    = {"MFLS_BankLevel": mfls_signal}
    thresholds_dict = {"MFLS_BankLevel": p75_thr}
    for tier, sig_t in tier_signals.items():
        key = f"MFLS_{tier.capitalize()}"
        signals_dict[key]    = sig_t
        thresholds_dict[key] = float(np.percentile(sig_t[pre07], 75))

    eval_results = eval_all_variants(
        signals_dict=signals_dict,
        dates=dates,
        thresholds=thresholds_dict,
        crisis_windows=CRISIS_WINDOWS_EVAL,
        out_path=RESULTS_DIR / "eval_protocol_banklevel.json",
    )
    print("\n[9/9] Robustness checks ...")
    rob = run_all_robustness(
        X_std, dates, mfls_signal,
        out_path=RESULTS_DIR / "robustness_banklevel.json",
    )

    # ------------------------------------------------------------------
    # Assemble summary
    # ------------------------------------------------------------------
    ep = eval_results["MFLS_BankLevel"]["primary"]
    tta_gfc = eval_results["MFLS_BankLevel"]["time_to_alarm_quarters"].get("GFC")

    tier_auroc = {}
    for tier, sig_t in tier_signals.items():
        r_roc = roc_auprc(sig_t, crisis_labels)
        tier_auroc[tier] = round(r_roc["auroc"], 4)

    summary = {
        "data_source":            "FDIC SDI call-report (individual bank-level, quarterly)",
        "NO_SYNTHETIC_DATA":      True,
        "T_quarters":             int(T),
        "date_range":             f"{dates[0].date()} to {dates[-1].date()}",
        "N_banks":                int(N),
        "d_features":             int(d),
        "lambda_max_W":           float(lmax),
        "rho_star":               float(rho_star),
        "auroc":                  float(ep["auroc"]),
        "auroc_95ci":             [ci_global["auroc_lo"], ci_global["auroc_hi"]],
        "hit_rate":               float(ep["hr"]),
        "hit_rate_95ci":          [ci_global["hr_lo"], ci_global["hr_hi"]],
        "false_alarm_rate":       float(ep["far"]),
        "false_alarm_rate_95ci":  [ci_global["far_lo"], ci_global["far_hi"]],
        "lead_quarters_gfc":      lead_q,
        "gfc_alarm_date":         str(first_alarm),
        "gfc_hit_rate":           gfc_hr,
        "causality": {
            "linear_granger_min_p":    causality["summary"]["linear_granger_min_p"],
            "linear_verdict":          causality["summary"]["linear_granger_verdict"],
            "threshold_granger_min_p": causality["summary"]["threshold_granger_min_p"],
            "threshold_verdict":       causality["summary"]["threshold_verdict"],
            "quantile_min_p":          causality["summary"]["quantile_min_p"],
            "quantile_verdict":        causality["summary"]["quantile_verdict"],
        },
        "tier_auroc":             tier_auroc,
        "bank_meta_sample":       meta[:10],
        "runtime_sec":            round(time.time() - t0, 1),
        "admissibility_analysis": {
            "lead_window_Q": 4,
            "theta":         float(ALPHA),
            "M_max":         1.0,
            "g_ch_names":    ["C_contagion", "G_geometry", "A_activity", "T_topology"],
            "g_ch_mean":     traj["g_ch"].mean(axis=0).tolist(),
            "mfls_st_range": [float(traj["mfls_st"].min()), float(traj["mfls_st"].max())],
            "mfls_ch_range": [float(traj["mfls_ch"].min()), float(traj["mfls_ch"].max())],
            "admissibility_mean": float(np.mean(traj["admissibility"])),
            "admissibility_max":  float(np.max(traj["admissibility"])),
            "frac_inadmissible":  float(np.mean(traj["admissibility"] > 1.0)),
            "safety_mean":        float(np.mean(traj["safety"])),
            "frac_safe":          float(np.mean(traj["safety"] >= 1.0)),
            "rho_mfls_mean":      float(np.mean(traj["rho_mfls"])),
            "psi_deg_mean":       float(np.mean(traj["psi_deg"])),
        },
    }

    stats_path = RESULTS_DIR / "pipeline_stats_banklevel.json"
    with open(stats_path, "w") as f:
        json.dump(summary, f, indent=2, default=lambda o: float(o) if hasattr(o, "__float__") else str(o))
    print(f"\n  Saved -> {stats_path}")

    # LaTeX tables
    (RESULTS_DIR / "eval_table_banklevel.tex").write_text(latex_eval_table(eval_results))
    (RESULTS_DIR / "robustness_table_banklevel.tex").write_text(latex_robustness_table(rob))
    (RESULTS_DIR / "bootstrap_table_banklevel.tex").write_text(
        latex_bootstrap_table({"MFLS_BankLevel": ci_global}))
    (RESULTS_DIR / "causality_table_banklevel.tex").write_text(
        latex_causality_table(causality))

    # ------------------------------------------------------------------
    # Print final summary
    # ------------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"  FDIC BANK-LEVEL PIPELINE -- CANONICAL RESULTS")
    print(f"{'='*70}")
    print(f"  Panel:   T={T}, N={N} banks, d={d} features")
    print(f"  lambdamax(W) = {lmax:.3f}  rho* = {rho_star:.4f}")
    print(f"  OOS alarm:   {first_alarm}  lead={lead_q}Q  GFC HR={gfc_hr:.1%}")
    print(f"")
    print(f"  AUROC: {ep['auroc']:.4f}  [{ci_global['auroc_lo']:.4f}, {ci_global['auroc_hi']:.4f}]")
    print(f"  HR:    {ep['hr']:.4f}     [{ci_global['hr_lo']:.4f}, {ci_global['hr_hi']:.4f}]")
    print(f"  FAR:   {ep['far']:.4f}    [{ci_global['far_lo']:.4f}, {ci_global['far_hi']:.4f}]")
    print(f"  GFC TTA: {tta_gfc}Q")
    print(f"")
    for tier in ["mega", "regional"]:
        if tier in tier_auroc:
            t_ci = ci_by_tier.get(tier, {})
            label = "Top-10 Mega" if tier == "mega" else "Regional"
            print(f"  Tier {label}: AUROC={tier_auroc[tier]:.4f}  "
                  f"[{t_ci.get('auroc_lo', '?')}, {t_ci.get('auroc_hi', '?')}]")
    print(f"")
    print(f"  Causality:  Linear Granger  {causality['summary']['linear_granger_verdict']}")
    print(f"              Threshold Granger {causality['summary']['threshold_verdict']}  "
          f"(p={causality['summary']['threshold_granger_min_p']:.4f})")
    print(f"              Quantile          {causality['summary']['quantile_verdict']}  "
          f"(p={causality['summary']['quantile_min_p']:.4f})")
    print(f"")
    print(f"  Admissibility (§12, L=4Q, theta={ALPHA}, M_max=1.0):")
    print(f"  MFLS_st: [{traj['mfls_st'].min():.3f}, {traj['mfls_st'].max():.3f}]  (physical-space pullback)")
    print(f"  frac inadmissible A>1: {np.mean(traj['admissibility']>1.0):.1%}   "
          f"mean A={np.mean(traj['admissibility']):.3f}")
    print(f"  frac safe rho>=1:      {np.mean(traj['safety']>=1.0):.1%}   "
          f"mean rho={np.mean(traj['safety']):.3f}")
    print(f"  mean rho_MFLS: {np.mean(traj['rho_mfls']):.3f}   mean psi: {np.mean(traj['psi_deg']):.1f} deg")
    print(f"  channel g_ch means: C={traj['g_ch'][:,0].mean():.3f}  "
          f"G={traj['g_ch'][:,1].mean():.3f}  "
          f"A={traj['g_ch'][:,2].mean():.3f}  "
          f"T={traj['g_ch'][:,3].mean():.3f}")
    print(f"")
    print(f"  Output: {RESULTS_DIR}")
    print(f"  Runtime: {time.time()-t0:.1f}s")
    print(f"{'='*70}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_banks",          type=int,  default=30)
    parser.add_argument("--n_boot",           type=int,  default=1000)
    parser.add_argument("--n_boot_causality", type=int,  default=2000)
    parser.add_argument("--force_refresh",    action="store_true")
    args = parser.parse_args()
    main(
        n_banks=args.n_banks,
        n_boot=args.n_boot,
        n_boot_causality=args.n_boot_causality,
        force_refresh=args.force_refresh,
    )
