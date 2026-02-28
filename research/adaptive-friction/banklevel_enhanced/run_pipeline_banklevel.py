"""
run_pipeline_banklevel.py
=========================
Full MFLS pipeline on institution-level FDIC data (N = top-30 banks).

Produces the same outputs as run_pipeline.py (v2) but with N > 7,
providing the network-story credibility boost needed for submission.
"""
from __future__ import annotations
import sys, json, time
import numpy as np
import pandas as pd
from pathlib import Path

# ?? path bootstrapping ????????????????????????????????????????????????????????
THIS_DIR     = Path(__file__).parent
UPGRADED_DIR = THIS_DIR.parent / "upgraded"
VARIANT_DIR  = THIS_DIR.parent / "upgraded"   # variants live in same upgraded dir
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(UPGRADED_DIR))

from bank_level_loader import build_bank_panel, FEATURE_NAMES
from network_builder   import lw_correlation_network, spectral_radius, describe_network
from gravity_engine    import BSDTOperator, analyse_trajectory, ALPHA
from eval_protocol     import eval_all_variants, latex_eval_table, CRISIS_WINDOWS_EVAL
from robustness_checks import run_all_robustness, latex_robustness_table

RESULTS_DIR = THIS_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ?? Normal period ?????????????????????????????????????????????????????????????
NORMAL_START = "1994-01-01"
NORMAL_END   = "2003-12-31"

# ?? FRED yield-curve slope ???????????????????????????????????????????????????
def _fetch_t10y2y(dates: pd.DatetimeIndex) -> np.ndarray:
    """Return T10Y2Y quarterly average aligned to dates."""
    cache = UPGRADED_DIR / "fred_cache" / "t10y2y.json"
    if cache.exists():
        with open(cache) as f:
            raw = json.load(f)
        series = pd.Series(raw.get("values", {}))
        series.index = pd.to_datetime(series.index)
        series = series.apply(pd.to_numeric, errors="coerce").dropna()
        series = series.resample("QE").mean()
        aligned = series.reindex(dates, method="ffill").fillna(0.0).values
        return aligned
    return np.zeros(len(dates))


def _build_srisk_proxy(dates: pd.DatetimeIndex) -> np.ndarray:
    """Load pre-cached FRED stress indices and build equal-weight composite."""
    fred_dir = UPGRADED_DIR / "fred_cache"
    def _load(name):
        p = fred_dir / f"{name}.json"
        if not p.exists():
            return np.zeros(len(dates))
        with open(p) as f:
            raw = json.load(f)
        s = pd.Series(raw.get("values", {}))
        s.index = pd.to_datetime(s.index)
        s = s.apply(pd.to_numeric, errors="coerce").dropna()
        s = s.resample("QE").mean()
        return s.reindex(dates, method="ffill").fillna(0.0).values

    stlfsi = _load("stlfsi")
    vix    = _load("vix")
    hy     = _load("hy_spread")

    def _rn(x):
        r = pd.Series(x).rank(pct=True).values
        return (r - r.mean()) / (r.std() + 1e-12)

    return (_rn(stlfsi) + _rn(vix) + _rn(hy)) / 3.0


def main(n_banks: int = 30, force_refresh: bool = False):
    t0 = time.time()
    print("=" * 64)
    print(f"  MFLS Bank-Level Pipeline  (N={n_banks} institutions)")
    print("=" * 64)

    # ?? 1. Load bank-level panel ??????????????????????????????????????????????
    print("\n[1/7] Building institution-level state matrix ...")
    panel   = build_bank_panel(n_banks=n_banks, force_refresh=force_refresh)
    X_raw   = panel["X"]      # (T, N, d)
    dates   = panel["dates"]
    N       = panel["n_banks_actual"]
    d_base  = X_raw.shape[2]
    T       = X_raw.shape[0]
    meta    = panel["bank_meta"]
    print(f"  Panel: T={T}, N={N}, d={d_base}")

    # ?? 2. Append yield-curve slope as feature d+1 ????????????????????????????
    slope = _fetch_t10y2y(dates)
    X = np.concatenate([X_raw, slope[:, None, None] * np.ones((T, N, 1))], axis=2)
    d = X.shape[2]
    print(f"  Features after yield-curve append: d={d}")

    # ?? 3. Standardise on normal period ??????????????????????????????????????
    norm_mask = (dates >= pd.Timestamp(NORMAL_START)) & (dates <= pd.Timestamp(NORMAL_END))
    X_ref     = X[norm_mask]
    mu_ref    = X_ref.reshape(-1, d).mean(axis=0)
    sd_ref    = X_ref.reshape(-1, d).std(axis=0) + 1e-9
    X_std     = (X - mu_ref) / sd_ref
    print(f"  Normal period: {norm_mask.sum()} quarters  ({NORMAL_START} - {NORMAL_END})")

    # ?? 4. Build Ledoit-Wolf network ?????????????????????????????????????????
    print("\n[2/7] Building Ledoit-Wolf inter-bank network ...")
    W, rho_star = lw_correlation_network(X_std)
    lmax        = spectral_radius(W)
    print(f"  rho* = {rho_star:.4f}, lambdamax(W) = {lmax:.4f}")

    # ?? 5. Fit BSDT on normal period ?????????????????????????????????????????
    print("\n[3/7] Fitting BSDT operator on normal period ...")
    bsdt = BSDTOperator()
    bsdt.fit(X_std[norm_mask])
    mfls_signal = np.array([bsdt.mfls_score(X_std[t]) for t in range(T)])
    print(f"  MFLS signal range: [{mfls_signal.min():.3f}, {mfls_signal.max():.3f}]")

    # ?? 6. Analysis: trajectory stats ????????????????????????????????????????
    print("\n[4/7] Analysing full trajectory ...")
    traj = analyse_trajectory(X_std, mu_ref, bsdt, alpha=ALPHA)

    # ?? 7a. OOS backtest (inline ? oos_backtest() API differs) ???????????????
    print("\n[5/7] OOS backtest ...")
    pre07 = dates < pd.Timestamp("2007-01-01")
    p75   = float(np.percentile(mfls_signal[pre07], 75))
    # GFC alarm
    post07 = dates >= pd.Timestamp("2007-01-01")
    gfc_window = (dates >= pd.Timestamp("2007-01-01")) & (dates <= pd.Timestamp("2009-12-31"))
    alarm_idx  = np.where(post07 & (mfls_signal > p75))[0]
    first_alarm_date = dates[alarm_idx[0]] if len(alarm_idx) else None
    gfc_hit_rate     = float((mfls_signal[gfc_window] > p75).mean())
    lehman_date      = pd.Timestamp("2008-09-15")
    if first_alarm_date is not None:
        lead_qtrs = int(round((lehman_date - first_alarm_date).days / 91.25))
    else:
        lead_qtrs = 0
    oos = {"first_alarm": str(first_alarm_date), "lead_quarters": lead_qtrs,
           "gfc_hit_rate": gfc_hit_rate, "p75_threshold": p75}
    print(f"  First alarm: {first_alarm_date}  Lead: {lead_qtrs}Q  HR={gfc_hit_rate:.1%}")

    # ?? 7b. Full evaluation protocol ?????????????????????????????????????????
    print("\n[6/7] Running evaluation protocol ...")
    eval_results = eval_all_variants(
        signals_dict={"Baseline_BankLevel": mfls_signal},
        dates=dates,
        thresholds={"Baseline_BankLevel": p75},
        crisis_windows=CRISIS_WINDOWS_EVAL,
        out_path=RESULTS_DIR / "eval_protocol_banklevel.json",
    )

    # ?? 7c. Robustness checks ?????????????????????????????????????????????????
    print("\n[7/7] Running robustness checks ...")
    rob_results = run_all_robustness(
        X_std, dates, mfls_signal,
        out_path=RESULTS_DIR / "robustness_banklevel.json",
    )

    # ?? Summary stats ?????????????????????????????????????????????????????????
    frac_super = float((traj["lmax_series"] > ALPHA).mean()) if "lmax_series" in traj else float("nan")
    primary_ep = eval_results["Baseline_BankLevel"]["primary"]
    tta_gfc    = eval_results["Baseline_BankLevel"]["time_to_alarm_quarters"].get("GFC")

    stats = {
        "data_source":        "FDIC SDI call-report (bank-level)",
        "T_quarters":         int(T),
        "N_banks":            int(N),
        "d_features":         int(d),
        "lw_rho_star":        float(rho_star),
        "lambda_max_W":       float(lmax),
        "frac_above_cman":    frac_super,
        "mfls_p75_threshold": float(p75),
        "oos_alarm_date":     str(oos.get("first_alarm_date", "")),
        "oos_hit_rate":       float(oos.get("hit_rate", float("nan"))),
        "hit_rate":           float(primary_ep.get("hr", float("nan"))),
        "false_alarm_rate":   float(primary_ep.get("far", float("nan"))),
        "selectivity":        float(primary_ep.get("selectivity", float("nan"))),
        "auroc":              float(primary_ep.get("auroc", float("nan"))),
        "time_to_alarm_gfc":  tta_gfc,
        "bank_meta":          meta[:10],  # first 10 for readability
        "runtime_sec":        round(time.time() - t0, 1),
    }

    stats_path = RESULTS_DIR / "pipeline_stats_banklevel.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2, default=lambda o: str(o))
    print(f"\n[done] Saved -> {stats_path}")

    # ?? LaTeX tables ?????????????????????????????????????????????????????????
    eval_tex = latex_eval_table(eval_results)
    rob_tex  = latex_robustness_table(rob_results)
    (RESULTS_DIR / "eval_table_banklevel.tex").write_text(eval_tex)
    (RESULTS_DIR / "robustness_table_banklevel.tex").write_text(rob_tex)

    print(f"\n{'='*64}")
    print(f"  T={T} N={N} d={d}  lambdamax={lmax:.3f}")
    print(f"  OOS alarm: {stats['oos_alarm_date']}  hit={oos.get('hit_rate', 0):.1%}")
    print(f"  HR={primary_ep['hr']:.1%}  FAR={primary_ep['far']:.1%}  "
          f"AUROC={primary_ep.get('auroc', float('nan')):.3f}")
    print(f"  GFC lead: {tta_gfc}Q")
    print(f"  Runtime: {stats['runtime_sec']}s")
    print("=" * 64)
    return stats


if __name__ == "__main__":
    main()
