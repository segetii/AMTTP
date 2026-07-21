"""
canonical_v4_paper_style.py
===========================
Paper-style presentation wrapper around the strict locked Canonical-v4 ODE
engine (canonical_v4_engine.FrozenCanonicalV4).

The MATH is canonical v4 (Lyapunov energy E, gradient g_X, brake gamma,
projected dynamics, BSDT channels delta_C/A/T/G defined from locked-ODE
quantities).  Only the PRESENTATION mimics Odeyemi 2026:

    * Fisher Variance-Ratio weights (eq. 2.4) computed over the four
      canonical-v4 BSDT channels (transductive on full series, no labels).
    * Composite paper-style score
          E_paper(t) = sum_k w_k * z_k(delta_k(t))
      with z_k z-scored on the FROZEN reference window.
    * Split-conformal p-values (eq. 6.9) using the canonical-v4 anomaly
      score on a held-out fraction of the reference.
    * Adaptive rolling P99 threshold on the canonical-v4 anomaly score
      (paper section 7.12).
    * Alarms = canonical-v4 alarms (score > frozen p99) AND adaptive
      threshold gate AND conformal p < alpha_eff.

Nothing in canonical_v4_engine.py is modified; this file only consumes its
output.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
import numpy as np

from canonical_v4_engine import FrozenCanonicalV4, CanonicalV4Result

EPS = 1e-12


@dataclass
class PaperStyleResult:
    canonical: CanonicalV4Result      # the underlying v4 result (unchanged math)
    z_channels: np.ndarray            # (T, 4)  z-scored BSDT channels
    weights: np.ndarray               # (4,)    Fisher-VR weights
    E_paper: np.ndarray               # (T,)    composite paper-style score
    pvalue: np.ndarray                # (T,)    split-conformal p-value
    threshold_adaptive: np.ndarray    # (T,)    adaptive rolling P99 of v4 score
    alarms_paper: np.ndarray          # (T,) bool  combined paper-style alarm
    info: dict


def _fisher_vr_weights(channel_mat: np.ndarray, q_lo: float = 0.50,
                       q_hi: float = 0.80) -> np.ndarray:
    """Fisher Variance-Ratio weights (Odeyemi 2026, eq. 2.4)."""
    M = channel_mat.sum(axis=1)
    thr_lo = np.quantile(M, q_lo)
    thr_hi = np.quantile(M, q_hi)
    low = M <= thr_lo
    high = M >= thr_hi
    if low.sum() < 2 or high.sum() < 2:
        return np.ones(channel_mat.shape[1]) / channel_mat.shape[1]
    FR = np.zeros(channel_mat.shape[1])
    for k in range(channel_mat.shape[1]):
        mu_h = channel_mat[high, k].mean()
        mu_l = channel_mat[low, k].mean()
        v_h = channel_mat[high, k].var(ddof=1) + EPS
        v_l = channel_mat[low, k].var(ddof=1) + EPS
        FR[k] = (mu_h - mu_l) ** 2 / (v_h + v_l)
    s = FR.sum()
    return FR / s if s > 0 else np.ones_like(FR) / FR.size


def evaluate_paper_style(eng: FrozenCanonicalV4, X: np.ndarray, X_ref: np.ndarray,
                         alpha_alarm: float = 0.01, alpha_cal: float = 0.25,
                         rolling_window: int = 32, seed: int = 0
                         ) -> PaperStyleResult:
    """Score X with canonical-v4 math, then dress in paper-style outputs.

    Parameters
    ----------
    eng : FrozenCanonicalV4
        Already .fit(X_ref) on the frozen reference window.
    X : (T, d)  full timeline.
    X_ref : (n_ref, d)  the SAME reference window passed to eng.fit; required
        so we can compute reference statistics for z-scoring and conformal
        calibration without leakage.
    """
    if not eng.fitted:
        raise RuntimeError("FrozenCanonicalV4 must be .fit() before paper-style eval.")
    res_full: CanonicalV4Result = eng.evaluate(X)
    res_ref: CanonicalV4Result = eng.evaluate(X_ref)

    # --- Fisher-VR weights over v4 BSDT channels (full series, transductive) ---
    ch_full = np.column_stack([res_full.delta_C, res_full.delta_G,
                               res_full.delta_A, res_full.delta_T])
    ch_ref = np.column_stack([res_ref.delta_C, res_ref.delta_G,
                              res_ref.delta_A, res_ref.delta_T])
    weights = _fisher_vr_weights(ch_full)

    # --- z-score on REFERENCE statistics (no leakage) ---
    mu = ch_ref.mean(axis=0)
    sd = ch_ref.std(axis=0, ddof=1)
    sd = np.where(sd < EPS, 1.0, sd)
    z_full = (ch_full - mu) / sd
    E_paper = z_full @ weights                # paper-style composite

    # --- Split-conformal p-values on the v4 anomaly score (eq. 6.9) ---
    rng = np.random.default_rng(seed)
    n_ref = X_ref.shape[0]
    idx = rng.permutation(n_ref)
    n_cal = max(2, int(round(alpha_cal * n_ref)))
    cal_idx = idx[:n_cal]
    cal_scores = res_ref.score[cal_idx]
    ranks = np.sum(cal_scores[None, :] >= res_full.score[:, None], axis=1)
    pvalue = (ranks + 1.0) / (n_cal + 1.0)
    alpha_eff = max(float(alpha_alarm), 2.0 / (n_cal + 1.0))

    # --- Adaptive rolling P99 of v4 score (section 7.12) ---
    T = X.shape[0]
    W = max(8, min(rolling_window, T // 4))
    ref_p99 = float(np.quantile(res_ref.score, 0.99))
    threshold_adaptive = np.empty(T)
    for t in range(T):
        if t < W:
            threshold_adaptive[t] = ref_p99
        else:
            threshold_adaptive[t] = float(np.quantile(res_full.score[t - W:t], 0.99))

    # --- Combined paper-style alarm ---
    # canonical v4 frozen alarm  AND  adaptive threshold cross  AND  conformal p < alpha_eff
    alarms_paper = (res_full.alarms
                    & (res_full.score > threshold_adaptive)
                    & (pvalue <= alpha_eff))

    info = {
        "engine": "FrozenCanonicalV4 (canonical-v4 ODE)",
        "presentation": "Odeyemi 2026 paper-style",
        "n_ref": int(n_ref),
        "n_cal": int(n_cal),
        "rolling_window": int(W),
        "frozen_p99_ref_v4": float(eng.threshold_),
        "adaptive_p99_ref_v4": ref_p99,
        "alpha_alarm": float(alpha_alarm),
        "alpha_alarm_effective": float(alpha_eff),
        "weights_order": ["delta_C", "delta_G", "delta_A", "delta_T"],
        "weights": weights.tolist(),
    }
    return PaperStyleResult(
        canonical=res_full,
        z_channels=z_full,
        weights=weights,
        E_paper=E_paper,
        pvalue=pvalue,
        threshold_adaptive=threshold_adaptive,
        alarms_paper=alarms_paper,
        info=info,
    )


def channel_dominance_weighted(res: PaperStyleResult, mask: np.ndarray) -> Dict[str, float]:
    """Weighted-z dominance over a window: w_k * mean(z_k_+)."""
    z_pos = np.clip(res.z_channels[mask], 0.0, None).mean(axis=0)
    contrib = res.weights * z_pos
    s = contrib.sum() + EPS
    return {
        "delta_C": float(contrib[0] / s),
        "delta_G": float(contrib[1] / s),
        "delta_A": float(contrib[2] / s),
        "delta_T": float(contrib[3] / s),
    }


def first_alarm_lead(alarms: np.ndarray, crisis_idx: int) -> int:
    if not np.any(alarms):
        return 0
    return int(crisis_idx - int(np.argmax(alarms)))
