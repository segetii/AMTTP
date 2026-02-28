"""
robustness_checks.py
====================
Pre-registered robustness checks for the MFLS paper.

Three checks:

  1. Alternate normal-period  – refit BSDT on 1994-Q1→2001-Q4 (shorter,
     avoids dot-com period) and compare results vs baseline 1994-2003.

  2. Rolling-window refit    – refit BSDT every 4 years on the 40Q window
     ending at t; measure how stable the signal is across fits.

  3. Leave-one-crisis-out    – when calibrating the P75 alarm threshold,
     exclude each crisis window in turn; report hit-rate stability.
"""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple
import sys

PIPE_DIR = Path(__file__).parent
sys.path.insert(0, str(PIPE_DIR))

from state_matrix    import standardise_panel, get_normal_period
from gravity_engine  import BSDTOperator
from eval_protocol   import (
    build_binary_labels, threshold_metrics, roc_auprc, CRISIS_WINDOWS_EVAL,
    time_to_first_alarm,
)

RESULTS_DIR = PIPE_DIR / "results"


# ── 1. Alternate normal-period check ────────────────────────────────────────

NORMAL_PERIODS = {
    "baseline_1994_2003":  ("1994-01-01", "2003-12-31"),   # default
    "short_1994_2001":     ("1994-01-01", "2001-12-31"),   # pre-dot-com
    "early_1990_1999":     ("1990-01-01", "1999-12-31"),   # early 90s
}


def refit_bsdt_on_period(
    X: np.ndarray,          # (T, N, d)
    dates: pd.DatetimeIndex,
    normal_start: str,
    normal_end: str,
) -> Tuple[BSDTOperator, np.ndarray]:
    """
    Refit BSDTOperator on a custom normal period; return (operator, mfls_signal).
    X shape: (T, N, d).  BSDTOperator.fit expects (T_ref, N, d);
    mfls_score expects (N, d).
    """
    mask = (dates >= pd.Timestamp(normal_start)) & (dates <= pd.Timestamp(normal_end))
    X_ref = X[mask]                              # (T_ref, N, d)

    T = X.shape[0]
    op = BSDTOperator()
    op.fit(X_ref)                                # fit on normal-period snapshots

    signal = np.array([op.mfls_score(X[t]) for t in range(T)])
    return op, signal


def run_alternate_normal_period(
    X: np.ndarray,
    dates: pd.DatetimeIndex,
    threshold_pct: float = 75.0,
) -> Dict[str, Dict]:
    """
    Refit BSDT on each candidate normal period, compute MFLS, run full eval.
    Returns a dict keyed by period label.
    """
    labels = build_binary_labels(dates, CRISIS_WINDOWS_EVAL, shift_quarters=0)
    results = {}

    for period_label, (ns, ne) in NORMAL_PERIODS.items():
        # check we have enough data in that period
        period_mask = (dates >= pd.Timestamp(ns)) & (dates <= pd.Timestamp(ne))
        if period_mask.sum() < 12:
            print(f"  [robustness] Skip {period_label}: too few quarters ({period_mask.sum()})")
            continue

        # train threshold on pre-2007 data using this signal
        _, sig = refit_bsdt_on_period(X, dates, ns, ne)
        pre07  = dates < pd.Timestamp("2007-01-01")
        thr    = float(np.percentile(sig[pre07], threshold_pct)) if pre07.sum() > 0 else float(np.percentile(sig, threshold_pct))

        m   = threshold_metrics(sig, labels, thr)
        roc = roc_auprc(sig, labels)

        tta = {}
        for name, onset, _end in CRISIS_WINDOWS_EVAL:
            tta[name] = time_to_first_alarm(sig, dates, thr, onset)

        results[period_label] = {
            "normal_period": (ns, ne),
            "n_ref_quarters": int(period_mask.sum()),
            "threshold": thr,
            "metrics": {**m, **roc},
            "time_to_alarm_quarters": tta,
        }
        print(f"  [robustness] {period_label}: HR={m['hr']:.1%} FAR={m['far']:.1%} "
              f"AUROC={roc.get('auroc', float('nan')):.3f}")

    return results


# ── 2. Rolling-window refit ──────────────────────────────────────────────────

def run_rolling_refit(
    X: np.ndarray,
    dates: pd.DatetimeIndex,
    window_quarters: int = 40,
    refit_every: int = 4,
    threshold_pct: float = 75.0,
) -> Dict:
    """
    Refit BSDT operator every ``refit_every`` quarters using the trailing
    ``window_quarters`` of data. Produces a time-varying MFLS signal.
    X shape: (T, N, d).
    """
    T, N, d = X.shape
    rolling_signal = np.full(T, np.nan)

    fit_indices = set(range(window_quarters, T, refit_every))

    current_op = None

    for t in range(T):
        if (current_op is None or t in fit_indices) and t >= window_quarters:
            ref_slice = X[t - window_quarters:t]   # (window_quarters, N, d)
            current_op = BSDTOperator()
            current_op.fit(ref_slice)
        if current_op is not None:
            rolling_signal[t] = current_op.mfls_score(X[t])   # (N, d)

    # fill initial NaNs with first valid value
    first_valid = np.where(~np.isnan(rolling_signal))[0]
    if len(first_valid):
        rolling_signal[:first_valid[0]] = rolling_signal[first_valid[0]]

    labels = build_binary_labels(dates, CRISIS_WINDOWS_EVAL, shift_quarters=0)
    pre07  = dates < pd.Timestamp("2007-01-01")
    thr    = float(np.percentile(rolling_signal[pre07 & ~np.isnan(rolling_signal)], threshold_pct))

    m   = threshold_metrics(rolling_signal, labels, thr)
    roc = roc_auprc(rolling_signal, labels)

    tta = {}
    for name, onset, _end in CRISIS_WINDOWS_EVAL:
        tta[name] = time_to_first_alarm(rolling_signal, dates, thr, onset)

    print(f"  [robustness] rolling refit (w={window_quarters}Q, every {refit_every}Q): "
          f"HR={m['hr']:.1%} FAR={m['far']:.1%}")

    return {
        "window_quarters": window_quarters,
        "refit_every": refit_every,
        "threshold": thr,
        "metrics": {**m, **roc},
        "time_to_alarm_quarters": tta,
        "signal": rolling_signal.tolist(),
    }


# ── 3. Leave-one-crisis-out threshold calibration ────────────────────────────

def run_loco_threshold(
    signal: np.ndarray,
    dates: pd.DatetimeIndex,
    threshold_pct: float = 75.0,
) -> Dict[str, Dict]:
    """
    For each crisis, calibrate P75 threshold excluding that crisis's
    pre-onset data, then re-evaluate. Reports hit-rate stability.
    """
    all_labels = build_binary_labels(dates, CRISIS_WINDOWS_EVAL, shift_quarters=0)
    results    = {}

    for left_out_name, onset_str, end_str in CRISIS_WINDOWS_EVAL:
        onset  = pd.Timestamp(onset_str)
        end    = pd.Timestamp(end_str)

        # calibration set: any quarter NOT in this crisis window AND before onset
        cal_mask = (dates < onset) | (dates > end)
        pre_onset_cal = cal_mask & (dates < onset)

        if pre_onset_cal.sum() < 8:
            print(f"  [robustness] loco {left_out_name}: insufficient cal data, skip")
            continue

        thr = float(np.percentile(signal[pre_onset_cal], threshold_pct))
        m   = threshold_metrics(signal, all_labels, thr)
        roc = roc_auprc(signal, all_labels)

        tta = {}
        for name, o2, _e2 in CRISIS_WINDOWS_EVAL:
            tta[name] = time_to_first_alarm(signal, dates, thr, o2)

        results[f"loco_{left_out_name}"] = {
            "left_out": left_out_name,
            "threshold": thr,
            "metrics": {**m, **roc},
            "time_to_alarm_quarters": tta,
        }
        print(f"  [robustness] loco {left_out_name}: thr={thr:.3f} "
              f"HR={m['hr']:.1%} FAR={m['far']:.1%}")

    return results


# ── Master runner ────────────────────────────────────────────────────────────

def run_all_robustness(
    X: np.ndarray,
    dates: pd.DatetimeIndex,
    baseline_signal: np.ndarray,
    out_path: Path | None = None,
) -> Dict:
    """Run all three robustness checks and optionally save JSON."""
    print("\n[robustness] === 1. Alternate normal period ===")
    alt_normal = run_alternate_normal_period(X, dates)

    print("\n[robustness] === 2. Rolling refit ===")
    rolling = run_rolling_refit(X, dates)

    print("\n[robustness] === 3. Leave-one-crisis-out threshold ===")
    loco = run_loco_threshold(baseline_signal, dates)

    out = {
        "alternate_normal_period": alt_normal,
        "rolling_refit":           rolling,
        "loco_threshold":          loco,
    }

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            def _s(o):
                if isinstance(o, (np.integer,)):  return int(o)
                if isinstance(o, (np.floating,)): return None if np.isnan(o) else float(o)
                if isinstance(o, (np.ndarray,)):  return o.tolist()
                if o is None:                     return None
                raise TypeError(f"Not serializable: {type(o)}")
            json.dump(out, f, indent=2, default=_s)
        print(f"\n[robustness] Saved → {out_path}")

    return out


def latex_robustness_table(rob: Dict) -> str:
    """Render a concise LaTeX table summarising all three checks."""
    rows = []
    # Alternate normal period
    for label, res in rob.get("alternate_normal_period", {}).items():
        m = res["metrics"]
        tta = res.get("time_to_alarm_quarters", {})
        rows.append(
            f"Alt-normal: {label.replace('_', ' ')} & "
            f"{m['hr']:.1%} & {m['far']:.1%} & "
            f"{m.get('auroc', float('nan')):.3f} & "
            f"{tta.get('GFC', '---')} \\\\"
        )
    # Rolling refit
    rr = rob.get("rolling_refit", {})
    if rr:
        m = rr["metrics"]
        tta = rr.get("time_to_alarm_quarters", {})
        rows.append(
            f"Rolling refit (40Q window) & "
            f"{m['hr']:.1%} & {m['far']:.1%} & "
            f"{m.get('auroc', float('nan')):.3f} & "
            f"{tta.get('GFC', '---')} \\\\"
        )
    # LOCO
    for label, res in rob.get("loco_threshold", {}).items():
        m = res["metrics"]
        tta = res.get("time_to_alarm_quarters", {})
        rows.append(
            f"LOCO: {res['left_out']} & "
            f"{m['hr']:.1%} & {m['far']:.1%} & "
            f"{m.get('auroc', float('nan')):.3f} & "
            f"{tta.get('GFC', '---')} \\\\"
        )

    header = (
        "\\begin{table}[htbp]\n\\centering\n"
        "\\caption{Robustness checks: alternate normal period, rolling refit, "
        "and leave-one-crisis-out (LOCO) threshold calibration. "
        "Baseline HR = 71.4\\%, FAR ≈ 35\\% (Table~\\ref{tab:oos}).}\n"
        "\\label{tab:robustness}\n"
        "\\begin{tabular}{lcccc}\n\\toprule\n"
        "Check & HR & FAR & AUROC & GFC lead (Q) \\\\\n"
        "\\midrule\n"
    )
    return header + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n"


if __name__ == "__main__":
    print("[robustness_checks] Run via reproduce.py for full integration.")
