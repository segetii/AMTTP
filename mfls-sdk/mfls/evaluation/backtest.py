"""
Out-of-sample backtest and robustness checks.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from mfls.core.bsdt import BSDTOperator


def backtest_oos(
    signal: np.ndarray,
    dates: pd.DatetimeIndex,
    labels: np.ndarray,
    train_end: str,
    threshold_pctl: float = 75.0,
) -> Dict:
    """
    Out-of-sample backtest: train threshold on [start, train_end],
    evaluate on (train_end, end].

    Returns
    -------
    dict with keys: threshold, oos_auroc, oos_hr, oos_far, first_alarm_date
    """
    train_mask = dates <= pd.Timestamp(train_end)
    test_mask = ~train_mask

    sig_train = signal[train_mask]
    sig_test = signal[test_mask]
    lab_test = labels[test_mask]
    dates_test = dates[test_mask]

    threshold = float(np.percentile(sig_train, threshold_pctl))

    # AUROC
    n_pos = lab_test.sum()
    n_neg = len(lab_test) - n_pos
    auroc = 0.5
    if n_pos > 0 and n_neg > 0:
        desc = np.argsort(-sig_test)
        sorted_lab = lab_test[desc]
        tp = 0
        auc_sum = 0.0
        for i in range(len(sorted_lab)):
            if sorted_lab[i] == 1:
                tp += 1
            else:
                auc_sum += tp
        auroc = auc_sum / (n_pos * n_neg)

    alarm = sig_test > threshold
    hr = float(alarm[lab_test == 1].mean()) if (lab_test == 1).sum() > 0 else 0.0
    far = float(alarm[lab_test == 0].mean()) if (lab_test == 0).sum() > 0 else 0.0

    first_alarm = None
    alarm_dates = dates_test[alarm]
    if len(alarm_dates) > 0:
        first_alarm = str(alarm_dates[0].date())

    return {
        "threshold": threshold,
        "oos_auroc": float(auroc),
        "oos_hr": hr,
        "oos_far": far,
        "first_alarm_date": first_alarm,
        "n_test": int(test_mask.sum()),
        "n_crisis_test": int(lab_test.sum()),
    }


def robustness_alternate_normal(
    X: np.ndarray,
    dates: pd.DatetimeIndex,
    labels: np.ndarray,
    normal_periods: Dict[str, Tuple[str, str]],
    threshold_pctl: float = 75.0,
) -> Dict:
    """
    Re-fit BSDT on alternative normal periods and compare AUROC.

    Parameters
    ----------
    X : ndarray (T, N, d)
    dates : DatetimeIndex
    labels : ndarray (T,)
    normal_periods : dict mapping name → (start, end)
    threshold_pctl : float

    Returns
    -------
    dict keyed by period name → {auroc, hr, far, threshold}
    """
    results = {}
    for name, (ns, ne) in normal_periods.items():
        mask = (dates >= pd.Timestamp(ns)) & (dates <= pd.Timestamp(ne))
        X_ref = X[mask]
        if X_ref.shape[0] < 4:
            continue

        bsdt = BSDTOperator()
        bsdt.fit(X_ref)
        signal = bsdt.score_series(X)

        normal_sig = signal[mask]
        thr = float(np.percentile(normal_sig, threshold_pctl))

        alarm = signal > thr
        n_pos = labels.sum()
        n_neg = len(labels) - n_pos
        auroc = 0.5
        if n_pos > 0 and n_neg > 0:
            desc = np.argsort(-signal)
            tp = 0
            auc = 0.0
            for i in range(len(desc)):
                if labels[desc[i]] == 1:
                    tp += 1
                else:
                    auc += tp
            auroc = auc / (n_pos * n_neg)

        hr = float(alarm[labels == 1].mean()) if n_pos > 0 else 0.0
        far = float(alarm[labels == 0].mean()) if n_neg > 0 else 0.0

        results[name] = {
            "normal_period": f"{ns} to {ne}",
            "n_ref_quarters": int(mask.sum()),
            "threshold": thr,
            "auroc": float(auroc),
            "hr": hr,
            "far": far,
        }

    return results


def robustness_loco(
    signal: np.ndarray,
    dates: pd.DatetimeIndex,
    labels: np.ndarray,
    crisis_windows: List[Tuple[str, str, str]],
    threshold_pctl: float = 75.0,
) -> Dict:
    """
    Leave-one-crisis-out threshold calibration.

    For each crisis, calibrate the threshold on all *other* calm periods
    (excluding the held-out crisis) and evaluate on the held-out crisis.

    Returns
    -------
    dict keyed by crisis name → {threshold, hr, far}
    """
    results = {}
    for cname, onset, end in crisis_windows:
        crisis_mask = (dates >= pd.Timestamp(onset)) & (dates <= pd.Timestamp(end))
        calm_mask = labels == 0
        # Exclude this crisis from threshold calibration
        other_calm = calm_mask & ~crisis_mask
        if other_calm.sum() < 4:
            continue

        thr = float(np.percentile(signal[other_calm], threshold_pctl))
        alarm = signal > thr
        crisis_labels = labels[crisis_mask]
        calm_labels = labels[~crisis_mask]

        hr = float(alarm[crisis_mask].mean()) if crisis_mask.sum() > 0 else 0.0
        far = float(alarm[~crisis_mask & calm_mask].mean()) if (~crisis_mask & calm_mask).sum() > 0 else 0.0

        results[cname] = {
            "threshold": thr,
            "hr": hr,
            "far": far,
            "n_crisis_quarters": int(crisis_mask.sum()),
        }

    return results
