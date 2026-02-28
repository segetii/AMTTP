"""
Block-bootstrap confidence intervals for AUROC, hit rate, and false alarm rate.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np


def _auroc_fast(signal: np.ndarray, labels: np.ndarray) -> float:
    """Sort-based O(n log n) AUROC computation."""
    n_pos = labels.sum()
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    desc = np.argsort(-signal)
    sorted_labels = labels[desc]
    tp = 0
    fp = 0
    auroc = 0.0
    prev_tp = 0
    prev_fp = 0
    for i in range(len(sorted_labels)):
        if sorted_labels[i] == 1:
            tp += 1
        else:
            fp += 1
            auroc += tp
    return float(auroc / (n_pos * n_neg))


def block_bootstrap_ci(
    signal: np.ndarray,
    labels: np.ndarray,
    threshold: Optional[float] = None,
    n_boot: int = 1000,
    block_len: int = 8,
    alpha: float = 0.05,
    seed: int = 42,
    verbose: bool = False,
) -> Dict:
    """
    Block-bootstrap 95% confidence intervals for AUROC, HR, FAR.

    Uses overlapping block bootstrap to preserve temporal autocorrelation.

    Parameters
    ----------
    signal : ndarray (T,)
    labels : ndarray (T,) binary
    threshold : float or None (auto = P75 on calm periods)
    n_boot : int — number of bootstrap replicates
    block_len : int — block length (quarters)
    alpha : float — significance level
    seed : int
    verbose : bool

    Returns
    -------
    dict with keys: auroc, auroc_lo, auroc_hi, hr, hr_lo, hr_hi,
                    far, far_lo, far_hi, threshold, n_boot, block_len
    """
    T = len(signal)
    rng = np.random.default_rng(seed)

    if threshold is None:
        calm = labels == 0
        if calm.sum() > 0:
            threshold = float(np.percentile(signal[calm], 75))
        else:
            threshold = float(np.median(signal))

    # Observed metrics
    auroc_obs = _auroc_fast(signal, labels)
    alarm = signal > threshold
    hr_obs = float(alarm[labels == 1].mean()) if (labels == 1).sum() > 0 else 0.0
    far_obs = float(alarm[labels == 0].mean()) if (labels == 0).sum() > 0 else 0.0

    # Bootstrap
    auroc_boot = np.zeros(n_boot)
    hr_boot = np.zeros(n_boot)
    far_boot = np.zeros(n_boot)

    n_blocks = (T + block_len - 1) // block_len + 1

    for b in range(n_boot):
        # Draw overlapping blocks
        starts = rng.integers(0, T - block_len + 1, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block_len) for s in starts])[:T]

        sig_b = signal[idx]
        lab_b = labels[idx]
        alarm_b = sig_b > threshold

        auroc_boot[b] = _auroc_fast(sig_b, lab_b)
        crisis_b = lab_b == 1
        calm_b = lab_b == 0
        hr_boot[b] = float(alarm_b[crisis_b].mean()) if crisis_b.sum() > 0 else 0.0
        far_boot[b] = float(alarm_b[calm_b].mean()) if calm_b.sum() > 0 else 0.0

    lo = alpha / 2 * 100
    hi = (1 - alpha / 2) * 100

    return {
        "auroc": auroc_obs,
        "auroc_lo": float(np.percentile(auroc_boot, lo)),
        "auroc_hi": float(np.percentile(auroc_boot, hi)),
        "hr": hr_obs,
        "hr_lo": float(np.percentile(hr_boot, lo)),
        "hr_hi": float(np.percentile(hr_boot, hi)),
        "far": far_obs,
        "far_lo": float(np.percentile(far_boot, lo)),
        "far_hi": float(np.percentile(far_boot, hi)),
        "threshold": threshold,
        "n_boot": n_boot,
        "block_len": block_len,
        "alpha": alpha,
        "ci_label": f"{100*(1-alpha):.0f}%",
        "auroc_boot_mean": float(auroc_boot.mean()),
        "auroc_boot_std": float(auroc_boot.std()),
    }
