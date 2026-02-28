"""
eval_protocol.py
================
Tight evaluation protocol for the MFLS early-warning signal.

Replaces Granger causality as the primary validity test with metrics that are
consistent with phase-transition crisis dynamics:

  1. Hit Rate (HR)        - fraction of crisis-window quarters above threshold
  2. False-Alarm Rate (FAR) - fraction of calm quarters above threshold
  3. Selectivity          - HR / FAR  (precision-recall style ratio)
  4. Time-to-First-Alarm  - quarters from first threshold crossing to crisis onset
  5. AUROC                - area under the ROC curve
  6. AUPRC                - area under the precision-recall curve (handles class imbalance)
  7. Robustness sweep     - repeat all metrics under ?1Q window boundary shifts
"""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from sklearn.metrics import roc_auc_score, average_precision_score
    _SKLEARN = True
except ImportError:
    _SKLEARN = False


# ?? Crisis / calm window definitions ????????????????????????????????????????
# Each entry: (name, onset_quarter_str, end_quarter_str)
# onset = first "officially distressed" quarter (used for time-to-alarm)
CRISIS_WINDOWS_EVAL = [
    ("GFC",        "2007-10-01", "2009-12-31"),
    ("COVID",      "2020-01-01", "2021-06-30"),
    ("RateShock",  "2022-01-01", "2023-12-31"),
]


def _quarter_label(dates: pd.DatetimeIndex) -> bool:
    return True  # placeholder for type hint


def build_binary_labels(
    dates: pd.DatetimeIndex,
    crisis_windows: List[Tuple[str, str, str]],
    shift_quarters: int = 0,
) -> np.ndarray:
    """
    Return a binary array (1=crisis, 0=calm) aligned to ``dates``.

    shift_quarters: positive shifts window boundaries later (robustness test).
    """
    shift = pd.DateOffset(months=3 * shift_quarters)
    labels = np.zeros(len(dates), dtype=int)
    for _name, start_str, end_str in crisis_windows:
        s = pd.Timestamp(start_str) + shift
        e = pd.Timestamp(end_str) + shift
        mask = (dates >= s) & (dates <= e)
        labels[mask] = 1
    return labels


def threshold_metrics(
    signal: np.ndarray,
    labels: np.ndarray,
    threshold: float,
) -> Dict[str, float]:
    """Binary classification metrics at a fixed threshold."""
    pred = (signal >= threshold).astype(int)
    crisis_mask = labels == 1
    calm_mask   = labels == 0

    n_crisis = crisis_mask.sum()
    n_calm   = calm_mask.sum()

    hr  = pred[crisis_mask].sum() / n_crisis if n_crisis > 0 else 0.0
    far = pred[calm_mask].sum()   / n_calm   if n_calm   > 0 else 0.0
    selectivity = hr / far if far > 1e-9 else (float("inf") if hr > 0 else 0.0)

    tp = pred[crisis_mask].sum()
    fp = pred[calm_mask].sum()
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0

    return dict(hr=hr, far=far, selectivity=selectivity,
                precision=precision, recall=hr,
                tp=int(tp), fp=int(fp),
                n_crisis=int(n_crisis), n_calm=int(n_calm))


def time_to_first_alarm(
    signal: np.ndarray,
    dates: pd.DatetimeIndex,
    threshold: float,
    crisis_onset: str,
) -> float | None:
    """
    Quarters from the first signal crossing above threshold to the crisis onset.
    Positive = alarm fires before onset; None = no alarm before onset.
    """
    onset = pd.Timestamp(crisis_onset)
    pre_onset_mask = dates < onset
    crossing = np.where((signal >= threshold) & pre_onset_mask)[0]
    if len(crossing) == 0:
        return None
    first_idx = crossing[0]
    first_date = dates[first_idx]
    # approximate quarters
    delta_months = (onset.year - first_date.year) * 12 + (onset.month - first_date.month)
    return round(delta_months / 3, 1)


def roc_auprc(signal: np.ndarray, labels: np.ndarray) -> Dict[str, float]:
    """AUROC and AUPRC. Falls back to trapezoidal if sklearn not available."""
    if _SKLEARN:
        auroc = float(roc_auc_score(labels, signal)) if labels.sum() > 0 else 0.5
        auprc = float(average_precision_score(labels, signal)) if labels.sum() > 0 else 0.0
        return dict(auroc=auroc, auprc=auprc)

    # Manual trapezoid AUROC
    thresholds = np.percentile(signal, np.linspace(0, 100, 200))[::-1]
    tprs, fprs = [0.0], [0.0]
    lpos = labels.sum()
    lneg = (1 - labels).sum()
    for thr in thresholds:
        pred = (signal >= thr).astype(int)
        tpr = pred[labels == 1].sum() / lpos if lpos else 0
        fpr = pred[labels == 0].sum() / lneg if lneg else 0
        tprs.append(tpr); fprs.append(fpr)
    tprs.append(1.0); fprs.append(1.0)
    auroc = float(np.trapz(tprs, fprs))
    return dict(auroc=auroc, auprc=float("nan"))


def run_full_eval(
    signal: np.ndarray,
    dates: pd.DatetimeIndex,
    threshold: float,
    label: str = "Baseline",
    crisis_windows: List[Tuple[str, str, str]] | None = None,
    robustness_shifts: List[int] | None = None,
) -> Dict:
    """
    Run the complete evaluation protocol for a single MFLS signal.

    Returns a nested dict with primary metrics + robustness sweep.
    """
    if crisis_windows is None:
        crisis_windows = CRISIS_WINDOWS_EVAL
    if robustness_shifts is None:
        robustness_shifts = [-1, 0, 1]   # ?1 quarter

    results: Dict = {"label": label, "threshold": threshold}

    # ?? Primary evaluation (shift=0) ????????????????????????????????????????
    labels_0 = build_binary_labels(dates, crisis_windows, shift_quarters=0)
    base_metrics = threshold_metrics(signal, labels_0, threshold)
    base_roc     = roc_auprc(signal, labels_0)
    results["primary"] = {**base_metrics, **base_roc}

    # ?? Time-to-first-alarm per crisis ??????????????????????????????????????
    tta = {}
    for name, onset_str, _end_str in crisis_windows:
        tta[name] = time_to_first_alarm(signal, dates, threshold, onset_str)
    results["time_to_alarm_quarters"] = tta

    # ?? Robustness sweep ????????????????????????????????????????????????????
    sweep = []
    for shift in robustness_shifts:
        lab = build_binary_labels(dates, crisis_windows, shift_quarters=shift)
        m   = threshold_metrics(signal, lab, threshold)
        rr  = roc_auprc(signal, lab)
        sweep.append({"shift_quarters": shift, **m, **rr})
    results["robustness_sweep"] = sweep

    # ?? Robustness summary (mean ? std across shifts) ???????????????????????
    hr_vals   = [s["hr"]   for s in sweep]
    far_vals  = [s["far"]  for s in sweep]
    auroc_vals = [s["auroc"] for s in sweep]
    results["robustness_summary"] = dict(
        hr_mean=np.mean(hr_vals),   hr_std=np.std(hr_vals),
        far_mean=np.mean(far_vals), far_std=np.std(far_vals),
        auroc_mean=np.mean(auroc_vals), auroc_std=np.std(auroc_vals),
    )

    return results


def eval_all_variants(
    signals_dict: Dict[str, np.ndarray],
    dates: pd.DatetimeIndex,
    thresholds: Dict[str, float],
    crisis_windows: List[Tuple[str, str, str]] | None = None,
    out_path: Path | None = None,
) -> Dict[str, Dict]:
    """
    Evaluate every variant in ``signals_dict`` and save a unified JSON.
    """
    all_results = {}
    for name, sig in signals_dict.items():
        thr = thresholds.get(name, np.percentile(sig, 75))
        all_results[name] = run_full_eval(
            sig, dates, thr, label=name,
            crisis_windows=crisis_windows,
        )

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            def _serial(o):
                if isinstance(o, (np.integer,)):  return int(o)
                if isinstance(o, (np.floating,)): return None if np.isnan(o) else float(o)
                if isinstance(o, (np.ndarray,)):  return o.tolist()
                raise TypeError(f"Not serializable: {type(o)}")
            json.dump(all_results, f, indent=2, default=_serial)
        print(f"[eval_protocol] Saved -> {out_path}")

    return all_results


def latex_eval_table(results: Dict[str, Dict]) -> str:
    """Render a LaTeX table summarising the evaluation protocol results."""
    header = (
        r"\begin{table}[htbp]" "\n"
        r"\centering" "\n"
        r"\caption{Evaluation protocol: hit rate, FAR, selectivity, AUROC, and "
        r"time-to-alarm across MFLS variants. "
        r"All metrics computed on real FDIC data (T=140, N=7, d=6). "
        r"Threshold = P75 of pre-2007 training signal. "
        r"Robustness mean?std computed under ?1Q window boundary shifts.}" "\n"
        r"\label{tab:eval_protocol}" "\n"
        r"\begin{tabular}{lcccccc}" "\n"
        r"\toprule" "\n"
        r"Variant & HR & FAR & Select. & AUROC & GFC lead & COVID lead \\" "\n"
        r"\midrule" "\n"
    )
    rows = []
    for name, res in results.items():
        p = res["primary"]
        tta = res["time_to_alarm_quarters"]
        gfc_lead   = tta.get("GFC")
        covid_lead = tta.get("COVID")
        gfc_str   = f"{gfc_lead:.0f}Q" if gfc_lead is not None else "---"
        covid_str = f"{covid_lead:.0f}Q" if covid_lead is not None else "---"
        rob = res["robustness_summary"]
        rows.append(
            f"{name} & "
            f"{p['hr']:.1%} & "
            f"{p['far']:.1%} & "
            f"{p['selectivity']:.1f}$\\times$ & "
            f"{p['auroc']:.3f} & "
            f"{gfc_str} & "
            f"{covid_str} \\\\"
        )
    footer = (
        r"\bottomrule" "\n"
        r"\end{tabular}" "\n"
        r"\end{table}" "\n"
    )
    return header + "\n".join(rows) + "\n" + footer


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from run_pipeline import main as run_main  # noqa: F401
    print("[eval_protocol] Run via reproduce.py for full integration.")
