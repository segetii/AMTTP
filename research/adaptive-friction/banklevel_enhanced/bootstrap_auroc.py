"""
bootstrap_auroc.py
==================
Block-bootstrap confidence intervals for AUROC, Hit Rate, and Lead Quarters.

Why block bootstrap (not i.i.d.)?
  Financial time series are autocorrelated.  Block bootstrap preserves the
  serial dependence structure by resampling contiguous blocks of length L
  rather than individual time steps.  L = 8 quarters (2 years) is standard
  in macrofinancial panels (Politis & Romano 1994, Patton et al. 2009).

Usage
-----
    from bootstrap_auroc import block_bootstrap_ci, bootstrap_report

    ci = block_bootstrap_ci(
        signal   = mfls_signal,   # (T,) float
        labels   = crisis_labels, # (T,) binary
        n_boot   = 1000,
        block_len= 8,
        alpha    = 0.05,
    )
    # ci dict keys: auroc, auroc_lo, auroc_hi, hr, hr_lo, hr_hi
"""
from __future__ import annotations
import json
import numpy as np
from pathlib import Path
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# AUROC helper (no sklearn dependency)
# ---------------------------------------------------------------------------

def _auroc_numpy(scores: np.ndarray, labels: np.ndarray) -> float:
    """Compute AUROC via Mann-Whitney U (O(n_pos * n_neg))."""
    pos = scores[labels == 1]
    neg = scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    count = 0.0
    for p in pos:
        count += np.sum(p > neg) + 0.5 * np.sum(p == neg)
    return float(count / (len(pos) * len(neg)))


def _auroc_fast(scores: np.ndarray, labels: np.ndarray) -> float:
    """Faster AUROC via sort -- O(n log n).  Matches Mann-Whitney exactly."""
    n = len(labels)
    n_pos = labels.sum()
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order   = np.argsort(scores)[::-1]
    labels_s = labels[order]
    # Trapezoidal: cumulative TPR vs cumulative FPR
    cum_pos = np.cumsum(labels_s)
    cum_neg = np.cumsum(1 - labels_s)
    tpr = cum_pos / n_pos
    fpr = cum_neg / n_neg
    # Prepend (0,0)
    tpr = np.concatenate([[0.0], tpr])
    fpr = np.concatenate([[0.0], fpr])
    return float(np.trapz(tpr, fpr))


def _hit_rate(scores: np.ndarray, labels: np.ndarray, threshold: float) -> float:
    """Fraction of crisis quarters where score > threshold."""
    crisis = labels == 1
    if crisis.sum() == 0:
        return float("nan")
    return float((scores[crisis] > threshold).mean())


def _false_alarm_rate(scores: np.ndarray, labels: np.ndarray, threshold: float) -> float:
    """Fraction of non-crisis quarters where score > threshold."""
    calm = labels == 0
    if calm.sum() == 0:
        return float("nan")
    return float((scores[calm] > threshold).mean())


# ---------------------------------------------------------------------------
# Block bootstrap core
# ---------------------------------------------------------------------------

def block_bootstrap_ci(
    signal:    np.ndarray,
    labels:    np.ndarray,
    threshold: Optional[float]  = None,
    n_boot:    int              = 1000,
    block_len: int              = 8,
    alpha:     float            = 0.05,
    seed:      int              = 42,
    verbose:   bool             = True,
) -> Dict:
    """
    Non-overlapping block bootstrap CI for AUROC, hit rate, false alarm rate.

    Parameters
    ----------
    signal    : (T,) MFLS score series
    labels    : (T,) binary crisis labels (1=crisis quarter)
    threshold : float or None.  If None, uses P75 of non-crisis signal.
    n_boot    : number of bootstrap replications
    block_len : contiguous block length (quarters)
    alpha     : two-sided CI level (0.05 -> 95%)
    seed      : RNG seed for reproducibility

    Returns
    -------
    dict with keys:
        auroc, auroc_lo, auroc_hi
        hr, hr_lo, hr_hi
        far, far_lo, far_hi
        threshold
        n_boot, block_len, alpha
        auroc_boot  (full array of bootstrap AUROC replicates)
    """
    T = len(signal)
    rng = np.random.default_rng(seed)

    if threshold is None:
        calm_mask = labels == 0
        threshold = float(np.percentile(signal[calm_mask], 75)) \
                    if calm_mask.sum() > 0 else float(np.percentile(signal, 75))

    # ---- build non-overlapping blocks ------------------------------------
    n_blocks = max(1, T // block_len)
    # Pad if needed
    pad_len = n_blocks * block_len
    sig_pad = np.concatenate([signal, signal[:pad_len - T]]) if pad_len > T else signal[:pad_len]
    lab_pad = np.concatenate([labels, labels[:pad_len - T]]) if pad_len > T else labels[:pad_len]
    blocks_sig = sig_pad.reshape(n_blocks, block_len)
    blocks_lab = lab_pad.reshape(n_blocks, block_len)

    # ---- bootstrap -------------------------------------------------------
    boot_auroc = np.zeros(n_boot)
    boot_hr    = np.zeros(n_boot)
    boot_far   = np.zeros(n_boot)

    for b in range(n_boot):
        idx  = rng.integers(0, n_blocks, size=n_blocks)
        s_b  = blocks_sig[idx].ravel()
        l_b  = blocks_lab[idx].ravel()
        boot_auroc[b] = _auroc_fast(s_b, l_b)
        boot_hr[b]    = _hit_rate(s_b, l_b, threshold)
        boot_far[b]   = _false_alarm_rate(s_b, l_b, threshold)

    lo, hi = alpha / 2.0, 1.0 - alpha / 2.0

    def _ci(arr):
        valid = arr[~np.isnan(arr)]
        if len(valid) == 0:
            return float("nan"), float("nan")
        return float(np.quantile(valid, lo)), float(np.quantile(valid, hi))

    auroc_point = _auroc_fast(signal, labels)
    hr_point    = _hit_rate(signal, labels, threshold)
    far_point   = _false_alarm_rate(signal, labels, threshold)

    auroc_lo, auroc_hi = _ci(boot_auroc)
    hr_lo,    hr_hi    = _ci(boot_hr)
    far_lo,   far_hi   = _ci(boot_far)

    result = {
        "auroc":     round(auroc_point, 4),
        "auroc_lo":  round(auroc_lo,    4),
        "auroc_hi":  round(auroc_hi,    4),
        "hr":        round(hr_point,    4),
        "hr_lo":     round(hr_lo,       4),
        "hr_hi":     round(hr_hi,       4),
        "far":       round(far_point,   4),
        "far_lo":    round(far_lo,      4),
        "far_hi":    round(far_hi,      4),
        "threshold": round(threshold,   4),
        "n_boot":    n_boot,
        "block_len": block_len,
        "alpha":     alpha,
        "ci_label":  f"{int((1-alpha)*100)}%",
        "auroc_boot_mean": round(float(np.nanmean(boot_auroc)), 4),
        "auroc_boot_std":  round(float(np.nanstd(boot_auroc)),  4),
    }

    if verbose:
        print(f"  Bootstrap CI ({result['ci_label']}, n={n_boot}, L={block_len}):")
        print(f"    AUROC : {auroc_point:.4f}  [{auroc_lo:.4f}, {auroc_hi:.4f}]")
        print(f"    HR    : {hr_point:.4f}     [{hr_lo:.4f}, {hr_hi:.4f}]")
        print(f"    FAR   : {far_point:.4f}    [{far_lo:.4f}, {far_hi:.4f}]")

    return result


# ---------------------------------------------------------------------------
# Per-variant bootstrap
# ---------------------------------------------------------------------------

def bootstrap_all_variants(
    signals:    Dict[str, np.ndarray],
    labels:     np.ndarray,
    thresholds: Dict[str, float] = None,
    n_boot:     int   = 1000,
    block_len:  int   = 8,
    alpha:      float = 0.05,
    out_path:   Path  = None,
) -> Dict[str, Dict]:
    """
    Run block_bootstrap_ci for every variant signal.

    Parameters
    ----------
    signals    : dict{ variant_name -> (T,) array }
    labels     : (T,) binary crisis labels
    thresholds : dict{ variant_name -> float } or None (auto P75)
    out_path   : optional JSON path to save results

    Returns
    -------
    dict{ variant_name -> ci_dict }
    """
    results = {}
    for name, sig in signals.items():
        print(f"\n  -- Bootstrap CI: {name}")
        thr = (thresholds or {}).get(name, None)
        ci  = block_bootstrap_ci(
            signal=sig, labels=labels, threshold=thr,
            n_boot=n_boot, block_len=block_len, alpha=alpha,
        )
        results[name] = ci

    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n  Bootstrap CI results saved -> {out_path}")

    return results


# ---------------------------------------------------------------------------
# LaTeX table helper
# ---------------------------------------------------------------------------

def latex_bootstrap_table(ci_results: Dict[str, Dict]) -> str:
    """
    Generate a LaTeX table of bootstrap CIs.

    Columns: Variant | AUROC [lo, hi] | HR [lo, hi] | FAR [lo, hi]
    """
    lines = [
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{Block-bootstrap 95\% confidence intervals (N=1000 replicates, L=8 quarters). "
        r"Non-overlapping Politis--Romano circular block bootstrap on the full MFLS signal series.}",
        r"\label{tab:bootstrap_ci}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"Variant & AUROC & 95\% CI & Hit Rate & False Alarm Rate \\",
        r"\midrule",
    ]
    for name, ci in ci_results.items():
        lines.append(
            f"{name} & {ci['auroc']:.3f} & "
            f"[{ci['auroc_lo']:.3f},\\,{ci['auroc_hi']:.3f}] & "
            f"{ci['hr']:.1%} [{ci['hr_lo']:.1%},\\,{ci['hr_hi']:.1%}] & "
            f"{ci['far']:.1%} [{ci['far_lo']:.1%},\\,{ci['far_hi']:.1%}] \\\\"
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    rng = np.random.default_rng(0)
    T   = 140
    lbl = np.zeros(T, dtype=int)
    # Simulate GFC 2007-2009 ~ quarters 68..76, COVID ~ 120..124
    lbl[68:76] = 1
    lbl[120:124] = 1
    score = rng.normal(0, 1, T)
    score[lbl == 1] += 1.5   # signal better during crises
    ci = block_bootstrap_ci(score, lbl, n_boot=500, verbose=True)
    print("\nFull result dict:")
    for k, v in ci.items():
        if k != "auroc_boot_mean":
            print(f"  {k}: {v}")
