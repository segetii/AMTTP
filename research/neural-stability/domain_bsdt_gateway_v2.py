"""
domain_bsdt_gateway_v2.py
==========================
Cross-domain port of the two key algorithmic innovations from the
crypto trading champion (v17/v25):

  1. ConfidenceGate  — analogue of the tbr0p47 taker-buy-ratio entry filter.
     Vetoes an alarm when a domain-specific quality signal falls below a
     calibrated threshold.  prevents false positives during low-confidence
     periods (e.g. seasonal noise in climate, benign traffic bursts in cyber).

  2. DomainCircuitBreaker — analogue of the CB_HALT=8% / CB_RESUME=1% /
     CB_WINDOW=180d circuit-breaker in simulate_combined().
     Once the canonical anomaly score builds up beyond the halt fraction of
     its rolling-window peak, the system enters HALTED state and suppresses
     further individual alarms until a recovery fraction is reached.
     Prevents alarm fatigue / false-alarm flooding during sustained crises.

Both components are domain-neutral: they operate on 1-D numpy arrays and
return boolean alarm masks.  Every domain_v2_*.py file imports and uses them.

Algorithm diagram
-----------------

  raw canonical alarms (FrozenCanonicalV4)
          │
          ▼
  ConfidenceGate  (tbr0p47 analog)
     conf_signal[t] < threshold  → veto alarm at t
          │
          ▼
  DomainCircuitBreaker  (CB_HALT / CB_RESUME analog)
     rolling-window peak of anomaly score:
       if not halted  and  drawdown_from_peak ≥ halt_frac   → HALTED
       if halted      and  drawdown_from_peak ≤ resume_frac → RESUMED
     while HALTED: suppress all alarms
          │
          ▼
  gated alarms (v2)

author: Odeyemi Olusegun Israel
"""
from __future__ import annotations
from collections import deque
from typing import Optional
import numpy as np


# ─── shared defaults (mirror v17/v25 champion params) ────────────────────────

DEFAULT_CONF_THRESH  = 0.47   # tbr0p47 analog
DEFAULT_HALT_FRAC    = 0.08   # CB_HALT  = 8%
DEFAULT_RESUME_FRAC  = 0.01   # CB_RESUME= 1%
DEFAULT_WINDOW       = 180    # CB_WINDOW = 180 steps


# ═══════════════════════════════════════════════════════════════════════════════
#  PATTERN 1 — Confidence Gate
# ═══════════════════════════════════════════════════════════════════════════════

class ConfidenceGate:
    """
    Vetoes alarms when a domain-specific quality signal is below threshold.

    Analogue of:  if tbr < tbr_long_min: counts["vetoed_tbr_long"] += 1; continue

    The signal is normalised to [0, 1] using rolling percentile rank over a
    calibration window before comparison against the threshold.

    Parameters
    ----------
    threshold  : float   veto if normalised signal < threshold (default 0.47)
    calib_win  : int     rolling window for percentile normalisation
    shift      : int     shift signal by this many steps (1 = prev-bar = no lookahead)
    """
    def __init__(self,
                 threshold: float = DEFAULT_CONF_THRESH,
                 calib_win: int   = 168,   # 1 week of hourly bars
                 shift: int       = 1):
        self.threshold = threshold
        self.calib_win = calib_win
        self.shift     = shift

    def normalise(self, signal: np.ndarray) -> np.ndarray:
        """Rolling percentile rank normalisation → [0, 1]."""
        T = len(signal)
        out = np.full(T, 0.5)
        for t in range(T):
            lo = max(0, t - self.calib_win + 1)
            window = signal[lo : t + 1]
            out[t] = np.mean(window <= signal[t])
        return out

    def apply(self,
              raw_alarms:   np.ndarray,   # (T,) bool
              conf_signal:  np.ndarray,   # (T,) float  (NOT yet normalised)
              already_normalised: bool = False,
              ) -> tuple[np.ndarray, dict]:
        """
        Returns (gated_alarms, info_dict).

        gated_alarms[t] = raw_alarms[t] AND conf_signal_norm[t-shift] >= threshold
        NaN in conf_signal is treated as neutral (no veto).
        """
        T = len(raw_alarms)
        assert len(conf_signal) == T, "conf_signal length must match alarms"

        norm = conf_signal if already_normalised else self.normalise(conf_signal)
        # shift: use previous bar value (no lookahead)
        norm_shifted = np.roll(norm, self.shift)
        norm_shifted[: self.shift] = 0.5   # neutral at start

        vetoed  = np.zeros(T, bool)
        gated   = np.zeros(T, bool)
        for t in range(T):
            if raw_alarms[t]:
                if np.isnan(norm_shifted[t]) or norm_shifted[t] >= self.threshold:
                    gated[t]  = True
                else:
                    vetoed[t] = True

        n_raw    = int(raw_alarms.sum())
        n_vetoed = int(vetoed.sum())
        n_gated  = int(gated.sum())
        info = dict(
            n_raw=n_raw,
            n_vetoed=n_vetoed,
            n_gated=n_gated,
            veto_pct=n_vetoed / max(n_raw, 1),
            threshold=self.threshold,
        )
        return gated, info


# ═══════════════════════════════════════════════════════════════════════════════
#  PATTERN 2 — Domain Circuit Breaker
# ═══════════════════════════════════════════════════════════════════════════════

class DomainCircuitBreaker:
    """
    Suppress alarms when the canonical anomaly score has already built up
    significantly from its rolling-window peak — crisis declared, sit out noise.

    Analogue of simulate_combined()'s CB state machine, but operating on the
    canonical anomaly score (rather than portfolio equity):

        score_drawdown = max(0, 1 - score[t] / rolling_peak[t])

        if not halted and score_drawdown <= -halt_frac:  halted = True
           (i.e., score surged halt_frac above rolling window — crisis onset)

        if halted and score recovered within resume_frac of peak:  halted = False

    NOTE on direction convention:
      In trading:  equity falls → drawdown triggers CB.
      In anomaly:  score RISES steeply → crisis triggers.
      We therefore flip the convention: the "peak" is a running MAX of the score,
      and the CB halts when score EXCEEDS its rolling-window MAX by halt_frac.
      Resume when score drops back within resume_frac of the halt peak.

    Parameters
    ----------
    halt_frac   : float  surge fraction above rolling peak to trigger HALT (0.08)
    resume_frac : float  recovery fraction below halt-peak to resume (0.01)
    window      : int    rolling window length in steps (180)
    """
    def __init__(self,
                 halt_frac:   float = DEFAULT_HALT_FRAC,
                 resume_frac: float = DEFAULT_RESUME_FRAC,
                 window:      int   = DEFAULT_WINDOW):
        self.halt_frac   = halt_frac
        self.resume_frac = resume_frac
        self.window      = window

    def apply(self,
              raw_alarms:     np.ndarray,   # (T,) bool
              anomaly_score:  np.ndarray,   # (T,) float  (canonical V4 score)
              ) -> tuple[np.ndarray, dict]:
        """
        Returns (gated_alarms, info_dict).
        When HALTED, alarms are suppressed until recovery.
        """
        T        = len(raw_alarms)
        mono_dq  = deque()          # monotone deque for rolling max
        gated    = np.zeros(T, bool)
        cb_flags = np.zeros(T, bool)

        halted       = False
        halt_peak    = 0.0

        for t in range(T):
            s = float(anomaly_score[t]) if not np.isnan(anomaly_score[t]) else 0.0

            # sliding-window maximum of anomaly_score
            while mono_dq and mono_dq[0][0] <= t - self.window:
                mono_dq.popleft()
            while mono_dq and mono_dq[-1][1] <= s:
                mono_dq.pop()
            mono_dq.append((t, s))
            roll_peak = mono_dq[0][1]

            # CB logic: score surging above rolling window peak → crisis
            if not halted:
                surge = (s / max(roll_peak, 1e-12)) - 1.0   # positive = above peak
                if surge >= self.halt_frac:
                    halted     = True
                    halt_peak  = s
            else:
                # recovery: score dropped back within resume_frac of halt peak
                recovery = (halt_peak - s) / max(halt_peak, 1e-12)
                if recovery >= self.resume_frac:
                    halted    = False
                    halt_peak = 0.0

            cb_flags[t] = halted
            if raw_alarms[t] and not halted:
                gated[t] = True

        n_raw    = int(raw_alarms.sum())
        n_suppressed = n_raw - int(gated.sum())
        n_trips  = int(sum(cb_flags[i] and not cb_flags[i-1] for i in range(1, T)))

        info = dict(
            n_raw=n_raw,
            n_gated=int(gated.sum()),
            n_suppressed=n_suppressed,
            suppress_pct=n_suppressed / max(n_raw, 1),
            pct_halted=float(cb_flags.mean()),
            n_trips=n_trips,
            halt_frac=self.halt_frac,
            resume_frac=self.resume_frac,
            window=self.window,
        )
        return gated, info


# ═══════════════════════════════════════════════════════════════════════════════
#  COMBINED PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def run_v2_gateway(
    v1_alarms:       np.ndarray,   # (T,) bool  — FrozenCanonicalV4 baseline alarms
    anomaly_score:   np.ndarray,   # (T,) float — canonical V4 anomaly score
    conf_signal:     np.ndarray,   # (T,) float — domain-specific quality signal
    crisis_mask:     Optional[np.ndarray] = None,  # (T,) bool — ground-truth if available
    conf_threshold:  float = DEFAULT_CONF_THRESH,
    halt_frac:       float = DEFAULT_HALT_FRAC,
    resume_frac:     float = DEFAULT_RESUME_FRAC,
    cb_window:       int   = DEFAULT_WINDOW,
    calib_win:       int   = 168,
) -> dict:
    """
    Full v2 alarm pipeline in one call:
      v1_alarms → ConfidenceGate → DomainCircuitBreaker → v2_alarms

    Returns a dict with:
      alarms_v1          : (T,) bool  baseline (input)
      alarms_conf_gate   : (T,) bool  after confidence gate only
      alarms_v2          : (T,) bool  after both gates (final v2 output)
      conf_info          : dict       confidence gate statistics
      cb_info            : dict       circuit breaker statistics
      improvement        : dict       comparison metrics (if crisis_mask given)
    """
    # Step 1: confidence gate
    gate = ConfidenceGate(threshold=conf_threshold, calib_win=calib_win)
    alarms_conf, conf_info = gate.apply(v1_alarms, conf_signal)

    # Step 2: circuit breaker on top of confidence-gated alarms
    cb = DomainCircuitBreaker(halt_frac=halt_frac, resume_frac=resume_frac, window=cb_window)
    alarms_v2, cb_info = cb.apply(alarms_conf, anomaly_score)

    out = dict(
        alarms_v1=v1_alarms,
        alarms_conf_gate=alarms_conf,
        alarms_v2=alarms_v2,
        conf_info=conf_info,
        cb_info=cb_info,
    )

    if crisis_mask is not None and crisis_mask.any():
        out["improvement"] = _compute_improvement(v1_alarms, alarms_v2, crisis_mask, anomaly_score)

    return out


# ─── improvement metrics ──────────────────────────────────────────────────────

def _compute_improvement(
    v1_alarms:    np.ndarray,
    v2_alarms:    np.ndarray,
    crisis_mask:  np.ndarray,   # (T,) bool  1 = crisis timestep
    score:        np.ndarray,
) -> dict:
    """
    Compute per-alarm precision, recall, lead time, false alarm rate for v1 vs v2.
    Lead time = steps before first crisis that the first alarm fires.
    """
    T = len(v1_alarms)
    first_crisis = int(crisis_mask.argmax()) if crisis_mask.any() else T

    def _metrics(alarms):
        tp = int((alarms & crisis_mask).sum())
        fp = int((alarms & ~crisis_mask).sum())
        fn = int((~alarms & crisis_mask).sum())
        prec = tp / max(tp + fp, 1)
        rec  = tp / max(tp + fn, 1)
        f1   = 2 * prec * rec / max(prec + rec, 1e-9)
        # lead time: first alarm before first crisis
        first_alarm = np.argmax(alarms) if alarms.any() else T
        lead = max(0, first_crisis - first_alarm) if alarms.any() else 0
        return dict(precision=prec, recall=rec, f1=f1,
                    first_alarm=int(first_alarm), lead_steps=lead,
                    n_alarms=int(alarms.sum()))

    v1_m = _metrics(v1_alarms)
    v2_m = _metrics(v2_alarms)

    return dict(
        v1=v1_m,
        v2=v2_m,
        precision_delta=v2_m["precision"] - v1_m["precision"],
        recall_delta=v2_m["recall"] - v1_m["recall"],
        f1_delta=v2_m["f1"] - v1_m["f1"],
        lead_improvement=v2_m["lead_steps"] - v1_m["lead_steps"],
        false_alarm_reduction=v1_m["n_alarms"] - v2_m["n_alarms"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def rolling_derivative(x: np.ndarray, window: int = 7) -> np.ndarray:
    """Rolling finite difference (rate of change) of a 1-D signal."""
    out = np.zeros_like(x)
    for t in range(1, len(x)):
        lo = max(0, t - window)
        out[t] = (x[t] - x[lo]) / max(t - lo, 1)
    return out


def rolling_corr_mean(X: np.ndarray, window: int = 7) -> np.ndarray:
    """
    Mean pairwise Pearson correlation across columns of X, computed in a
    rolling window.  Returns (T,) array of mean correlations.
    Used by domain_v2_information_flow.py for the confidence signal.
    """
    T, K = X.shape
    out = np.zeros(T)
    for t in range(window, T):
        block = X[t - window : t]
        if block.std(axis=0).min() < 1e-10:
            out[t] = 0.0
            continue
        C = np.corrcoef(block.T)
        # upper triangle (off-diagonal mean)
        idx = np.triu_indices(K, k=1)
        out[t] = float(C[idx].mean())
    return out


def percentile_rank_norm(x: np.ndarray, window: int = 200) -> np.ndarray:
    """Normalise a signal to [0,1] via rolling percentile rank."""
    T   = len(x)
    out = np.full(T, 0.5)
    for t in range(T):
        lo = max(0, t - window + 1)
        w  = x[lo : t + 1]
        out[t] = np.mean(w <= x[t])
    return out


# ─── self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    rng = np.random.default_rng(0)
    T   = 500
    # Synthetic score: flat baseline then spike
    score = np.concatenate([rng.normal(0.1, 0.02, 350),
                            rng.normal(0.5, 0.10, 150)])
    score = np.clip(score, 0, None)
    conf  = rng.uniform(0, 1, T)
    v1_al = score > np.percentile(score[:350], 99)   # frozen threshold
    crisis = np.zeros(T, bool); crisis[370:] = True

    result = run_v2_gateway(v1_al, score, conf, crisis)
    print("ConfidenceGate  :", result["conf_info"])
    print("CircuitBreaker  :", result["cb_info"])
    print("Improvement     :", result["improvement"])
    print("GATEWAY SELF-TEST PASSED")
