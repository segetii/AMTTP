#!/usr/bin/env python3
"""
run_early_warning.py
====================
Early-warning lead-time analysis using the SIAM-paper
Frozen-Window protocol ("The Geometry of System Collapse", Algorithm 2).

Scorer:  FrozenWindowScorer  (research.udl.geo_full_pipeline)
  • Freeze reference geometry (C* ellipsoid) from training normals.
  • Score full time-series with score_with_friction() — adaptive
    C* boundary reflection amplifies anomaly/normal separation.
  • Theory threshold τ_Q = χ²_{0.99}(d) (Wilson-Hilferty approx).
    Mapped to score space as 99th pct of reference-window scores.

Alarm logic ("last-quiet → first-re-alarm"):
  For each event onset index i_event:
    1. Scan backward from i_event to find the most recent QUIET window
       (n_quiet consecutive steps with score < τ_score).
    2. Starting from the end of that quiet window, scan forward to
       find the FIRST step where score ≥ τ_score.
    3. lead = i_event − i_first_alarm
    4. If no quiet window found → alarm was PERSISTENT from a prior
       event → report 'persistent_from_prior'.

This prevents spurious carry-over of the GFC alarm into COVID/RateShock.

Reports:
  ERCOT : lead in DAYS / HOURS before event onset
  Bank  : lead in QUARTERS / MONTHS / HOURS before event onset

Output: results/early_warning_results.json
"""
import sys, os, time, warnings, json
sys.path.insert(0, r'c:\amttp\research\udl')
sys.path.insert(0, r'c:\amttp\research\adaptive-friction\banklevel_enhanced')
os.environ['CUDA_VISIBLE_DEVICES'] = ''
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

import numpy as np
from pathlib import Path

ROOT        = Path(r'c:\amttp')
ERCOT_NPZ   = ROOT / 'data' / 'ercot' / 'ercot_daily_2018_2022.npz'
RESULTS_DIR = ROOT / 'results'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE    = RESULTS_DIR / 'early_warning_results.json'

from research.udl.geo_full_pipeline import FrozenWindowScorer



# ══════════════════════════════════════════════════════════════════════════
#  FROZEN-WINDOW SCORING
# ══════════════════════════════════════════════════════════════════════════

def frozen_score_full_series(X_all, train_norm_mask, k_steps=10, eta=0.25):
    r"""
    Freeze FrozenWindowScorer on training normals, extract Q-channel
    from friction-processed features.

    SIAM paper alarm condition (Section 4, "Geometry of System Collapse"):
      The system has "escaped the manifold" when Q(x) > τ_Q, where
        Q(x) = Σ_j x_j² / a_j²  (radial Mahalanobis in body coordinates)
        τ_Q = χ²_{0.99}(d)       (exact theory — zero data calibration)

    Adaptive friction amplifies the separation:
      x_{t+1} = x_t + sign(Q−θ)·|θ−Q|/(Q+θ)·η·d̃(x_t)
    so normals (Q<1) contract toward C* and anomalies (Q>1) diverge
    outward, making the Q > τ_Q boundary sharper.

    Returns
    -------
    Q_friction : (T,) Q-values after adaptive friction
    tau_Q      : float — χ²_{0.99}(d) theory threshold
    fws        : fitted FrozenWindowScorer (carries _tau_Q, _a2, etc.)
    """
    X_norm = X_all[train_norm_mask]
    print(f"    FrozenWindowScorer: fitting on {X_norm.shape[0]} normals …", end='', flush=True)
    t0 = time.perf_counter()
    fws = FrozenWindowScorer()
    fws.fit(X_norm)
    tau_Q = float(fws._tau_Q)
    d     = X_norm.shape[1]
    print(f" done ({time.perf_counter()-t0:.1f}s)  d={d}  τ_Q={tau_Q:.3f}")

    # Extract full feature matrix after adaptive friction.
    # Column 0 = Q (radial Mahalanobis) — the primary SIAM paper alarm channel.
    print(f"    features_with_friction(k_steps={k_steps}, η={eta}, θ=τ_Q) …", end='', flush=True)
    t0 = time.perf_counter()
    # CRITICAL: use theta = tau_Q, not theta=1.
    # Under χ²(d) with d >> 1,  E[Q] = d >> 1, so Q=1 is deep inside the
    # distribution.  Setting theta = tau_Q = χ²_{0.99}(d) places the friction
    # boundary at the 99th-percentile ellipsoid so normals (Q < tau_Q)
    # converge inward and anomalies (Q > tau_Q) diverge outward.
    F = fws.features_with_friction(X_all, k_steps=k_steps, eta=eta, theta=tau_Q)
    Q_friction = F[:, 0]      # Q in body frame after tau_Q-boundary friction
    print(f" done ({time.perf_counter()-t0:.1f}s)")

    # Sanity: fraction of reference window INSIDE C* (should be ~99%)
    inside_ref = float((Q_friction[train_norm_mask] < tau_Q).mean())
    print(f"    Reference window inside C* (Q < τ_Q): {inside_ref*100:.1f}%  "
          f"(theory: 99%)")

    return Q_friction, tau_Q, fws


# ══════════════════════════════════════════════════════════════════════════
#  ALARM LOGIC — last-quiet → first-re-alarm (SIAM paper pattern)
# ══════════════════════════════════════════════════════════════════════════

def last_quiet_end(scores, event_onset_idx, threshold, n_quiet,
                   max_lookback=None):
    """
    Scan backward from event_onset_idx − 1 to find the most recent
    consecutive quiet window of length ≥ n_quiet (score < threshold).

    max_lookback : if set, only search within the last max_lookback steps
                   before the onset (event-specific context window).

    Returns index of the LAST step of that quiet window (i.e. the step
    just before the system started rising again), or None if no quiet
    window exists.
    """
    idx = event_onset_idx - 1
    earliest = n_quiet - 1
    if max_lookback is not None:
        earliest = max(earliest, event_onset_idx - max_lookback)
    while idx >= earliest:
        # Check window [idx-n_quiet+1 .. idx] — all below threshold?
        window = scores[idx - n_quiet + 1: idx + 1]
        if np.all(window < threshold):
            return idx          # end of the last quiet window
        idx -= 1
    return None


def first_alarm_after_quiet(scores, quiet_end_idx, event_onset_idx, threshold):
    """
    From quiet_end_idx + 1 onward, find the first step ≥ threshold
    that precedes event_onset_idx.
    """
    for idx in range(quiet_end_idx + 1, event_onset_idx):
        if scores[idx] >= threshold:
            return idx
    return None


def measure_lead(scores, event_onset_idx, threshold, n_quiet,
                 max_lookback=None):
    """
    Full lead-time measurement via SIAM frozen-geometry protocol.

    Returns
    -------
    lead_steps        : int or None           steps of advance warning
    first_alarm_idx   : int or None           absolute index of alarm
    status            : str                   'alarm' | 'no_alarm' |
                                              'persistent_from_prior'
    """
    qe = last_quiet_end(scores, event_onset_idx, threshold, n_quiet,
                        max_lookback=max_lookback)
    if qe is None:
        # Never quiet before this event — alarm was persistent from prior event
        return None, None, 'persistent_from_prior'

    fa = first_alarm_after_quiet(scores, qe, event_onset_idx, threshold)
    if fa is None:
        return None, None, 'no_alarm'

    lead = event_onset_idx - fa
    return lead, fa, 'alarm'


def banner(s):
    print('\n' + '═' * 72)
    print(f'  {s}')
    print('═' * 72)


def rolling_deviation(X, window=30):
    T, d = X.shape
    Xd = np.zeros_like(X)
    for col in range(d):
        for i in range(T):
            start = max(0, i - window)
            chunk = X[start:i, col]
            chunk = chunk[~np.isnan(chunk)]
            if len(chunk) >= 5:
                mu_ = chunk.mean(); sd_ = chunk.std() + 1e-9
                Xd[i, col] = (X[i, col] - mu_) / sd_ if not np.isnan(X[i, col]) else 0.0
    return Xd


# ══════════════════════════════════════════════════════════════════════════
#  ERCOT EARLY WARNING
# ══════════════════════════════════════════════════════════════════════════

def analyse_ercot():
    banner("ERCOT — Frozen-Window Early Warning  (days / hours before onset)")

    npz    = np.load(ERCOT_NPZ, allow_pickle=True)
    X_raw  = npz['X'].astype(np.float64)
    y_raw  = npz['y'].astype(int)
    dates  = npz['dates']

    # Forward-fill NaNs
    for col in range(X_raw.shape[1]):
        lv = np.nanmean(X_raw[:, col]) if not np.all(np.isnan(X_raw[:, col])) else 0.0
        for i in range(len(X_raw)):
            if np.isnan(X_raw[i, col]): X_raw[i, col] = lv
            else: lv = X_raw[i, col]

    # Rolling deviation features
    X_dev = rolling_deviation(X_raw, window=30)

    # Standardise on 2018-2019 normals
    norm_mask = np.array([str(d)[:10] < '2020-01-01' for d in dates]) & (y_raw == 0)
    mu = X_raw[norm_mask].mean(0); sd = X_raw[norm_mask].std(0) + 1e-9
    X_s = np.nan_to_num(np.clip((X_raw - mu) / sd, -8, 8))
    X_c = np.hstack([X_s, X_dev])

    # Re-standardise all 12 dims on training normals (prevents singular C*)
    mu2 = X_c[norm_mask].mean(0); sd2 = X_c[norm_mask].std(0) + 1e-9
    X_c = np.clip((X_c - mu2) / sd2, -8, 8)

    print(f"  Total: {len(X_c)} days  —  training normals: {norm_mask.sum()}")

    # PCA to remove degenerate directions (rolling-deviation features are
    # correlated with level features → near-zero eigenvalues → Q → ∞).
    # Keep components that explain ≥ 99% of variance on training normals.
    from sklearn.decomposition import PCA
    pca = PCA(n_components=0.99).fit(X_c[norm_mask])
    X_pca = pca.transform(X_c)
    n_pca  = X_pca.shape[1]
    print(f"  PCA retained {n_pca} components (99% variance on training normals)")

    # ── Frozen-window scoring ──────────────────────────────────────────────
    Q_friction, tau_Q, fws = frozen_score_full_series(
        X_pca, norm_mask, k_steps=10, eta=0.25)

    # Quiet window = 14 consecutive days with Q < τ_Q (inside C*)
    N_QUIET = 14

    events = {
        'WinterStorm_Uri'    : '2021-02-10',
        'COVID_Demand_Crash'  : '2020-03-15',
        'WinterStorm_Elliott': '2022-12-22',
    }

    date_strs = np.array([str(d)[:10] for d in dates])
    results = {}

    for evt_name, onset_date in events.items():
        evt_idx = np.where(date_strs >= onset_date)[0]
        if len(evt_idx) == 0:
            print(f"  {evt_name}: onset date out of range"); continue
        onset_idx = int(evt_idx[0])
        onset_str = date_strs[onset_idx]

        lead, alarm_idx, status = measure_lead(
            Q_friction, onset_idx, tau_Q, n_quiet=N_QUIET)

        if status == 'alarm':
            alarm_str = date_strs[alarm_idx]
            lead_h    = lead * 24
            print(f"  {evt_name:<26}  onset={onset_str}  "
                  f"alarm={alarm_str}  lead={lead:>4} d  ({lead_h:>6,} h)")
            results[evt_name] = {
                'onset': onset_str, 'first_alarm': alarm_str,
                'lead_days': lead, 'lead_hours': lead_h,
                'tau_Q': round(tau_Q, 4), 'status': 'alarm',
            }
        elif status == 'persistent_from_prior':
            print(f"  {evt_name:<26}  onset={onset_str}  PERSISTENT ALARM "
                  f"(system never re-entered C* before this event)")
            results[evt_name] = {
                'onset': onset_str, 'first_alarm': None,
                'lead_days': None, 'lead_hours': None,
                'tau_Q': round(tau_Q, 4), 'status': 'persistent_from_prior',
            }
        else:
            print(f"  {evt_name:<26}  onset={onset_str}  NO alarm before onset "
                  f"(system inside C* until onset)")
            results[evt_name] = {
                'onset': onset_str, 'first_alarm': None,
                'lead_days': None, 'lead_hours': None,
                'tau_Q': round(tau_Q, 4), 'status': 'no_alarm',
            }

    return results


# ══════════════════════════════════════════════════════════════════════════
#  BANK EARLY WARNING
# ══════════════════════════════════════════════════════════════════════════

def analyse_bank():
    banner("BANK — Frozen-Window Early Warning  (quarters / months / hours before onset)")
    import pandas as pd
    from bank_level_loader import build_bank_panel

    panel  = build_bank_panel(n_banks=30, force_refresh=False)
    X_raw  = panel['X']; dates = panel['dates']
    T, N, d = X_raw.shape
    feat_names = panel.get('feature_names', [f'f{i}' for i in range(d)])

    # ── System-level stress features (6 per quarter, no windowing) ────────
    # Economically motivated: systemic levels + tail behaviour for
    # the three most crisis-sensitive FDIC metrics.
    # This preserves the quarterly resolution needed to detect pre-crisis buildup.
    npl_i  = feat_names.index('npl_ratio')
    eq_i   = feat_names.index('equity_ratio')
    fc_i   = feat_names.index('funding_cost')

    X_sys = np.column_stack([
        # Level indicators (mean across N banks)
        X_raw[:, :, npl_i ].mean(axis=1),          # systemic NPL level
        X_raw[:, :, eq_i  ].mean(axis=1),          # systemic capital level
        X_raw[:, :, fc_i  ].mean(axis=1),          # systemic funding cost
        # Tail / dispersion (stress concentration)
        np.percentile(X_raw[:, :, npl_i ], 75, axis=1),  # NPL upper tail
        np.percentile(X_raw[:, :, eq_i  ], 25, axis=1),  # equity lower tail
        np.percentile(X_raw[:, :, fc_i  ], 75, axis=1),  # funding cost upper tail
    ])  # (T, 6)

    # Normalise on 1994–2003 training reference (pre-GFC normal)
    ref_mask = (dates >= pd.Timestamp('1994-01-01')) & \
               (dates <= pd.Timestamp('2003-12-31'))
    mu_s = X_sys[ref_mask].mean(axis=0)
    sd_s = X_sys[ref_mask].std(axis=0) + 1e-9
    X_s  = np.clip((X_sys - mu_s) / sd_s, -8, 8)  # (T, 6)

    # Training normals = 1994–2006 reference (pre-GFC, no anomaly labels needed)
    train_norm_mask = (dates >= pd.Timestamp('1994-01-01')) & \
                      (dates <  pd.Timestamp('2007-01-01'))
    n_train_bank = train_norm_mask.sum()
    wd = dates   # full time axis — no window shift

    print(f"  Features: {['npl_mean','eq_mean','fc_mean','npl_p75','eq_p25','fc_p75']}")
    print(f"  Total: {T} quarters  —  training normals: {n_train_bank} "
          f"(1994–2006,  n/d={n_train_bank//6})")

    # ── Frozen-window scoring ──────────────────────────────────────────────
    Q_friction, tau_Q, fws = frozen_score_full_series(
        X_s, train_norm_mask, k_steps=10, eta=0.25)

    # Quiet window = 3 consecutive quarters with Q < τ_Q (inside C*)
    # (9 months of calm required to separate distinct event alarms)
    N_QUIET = 3

    events = {
        'GFC'      : pd.Timestamp('2007-01-01'),
        'COVID'    : pd.Timestamp('2020-01-01'),
        'RateShock': pd.Timestamp('2022-01-01'),
    }

    # ── Diagnostic: Q quantiles for event vs normal windows ──────────────
    Q_normal = Q_friction[train_norm_mask]
    Q_all    = Q_friction
    print(f"\n  Q diagnostics (after tau_Q-friction, tau_Q={tau_Q:.2f}):")
    print(f"    Training normals : min={Q_normal.min():.2f}  med={np.median(Q_normal):.2f}  "
          f"p95={np.percentile(Q_normal, 95):.2f}  max={Q_normal.max():.2f}")
    print(f"    Full series      : min={Q_all.min():.2f}  med={np.median(Q_all):.2f}  "
          f"p95={np.percentile(Q_all, 95):.2f}  max={Q_all.max():.2f}")
    # Events spot-check
    for evt_name, onset_ts in events.items():
        onset_arr_d = np.where(wd >= onset_ts)[0]
        if len(onset_arr_d) == 0: continue
        oi = int(onset_arr_d[0])
        window_start = max(0, oi-6)
        qs = Q_friction[window_start:oi+2]
        dates_w = [str(wd[i])[:10] for i in range(window_start, min(oi+2, len(wd)))]
        pairs = "  ".join(f"{dt}:{q:.1f}" for dt, q in zip(dates_w, qs))
        print(f"    {evt_name:<12}  Q around onset: {pairs}")
    print()

    bank_results = {}
    for evt_name, onset_ts in events.items():
        onset_arr = np.where(wd >= onset_ts)[0]
        if len(onset_arr) == 0: continue
        onset_idx = int(onset_arr[0])
        onset_str = str(wd[onset_idx])[:10]

        lead, alarm_idx, status = measure_lead(
            Q_friction, onset_idx, tau_Q, n_quiet=N_QUIET,
            max_lookback=20)   # 5-year context; prevents GFC alarm attribution to later events

        if status == 'alarm':
            alarm_str   = str(wd[alarm_idx])[:10]
            lead_months = round(lead * 3, 1)
            lead_hours  = round(lead * 91.25 * 24)
            print(f"  {evt_name:<12}  onset={onset_str}  "
                  f"alarm={alarm_str}  "
                  f"lead={lead:>3} Q  ({lead_months:>5.1f} m / {lead_hours:>7,} h)")
            bank_results[evt_name] = {
                'onset': onset_str, 'first_alarm': alarm_str,
                'lead_quarters': lead, 'lead_months': lead_months,
                'lead_hours': lead_hours,
                'tau_Q': round(tau_Q, 4), 'status': 'alarm',
            }
        elif status == 'persistent_from_prior':
            print(f"  {evt_name:<12}  onset={onset_str}  PERSISTENT ALARM "
                  f"(C* never re-entered between prior crisis and this onset)")
            bank_results[evt_name] = {
                'onset': onset_str, 'first_alarm': None,
                'lead_quarters': None, 'lead_months': None, 'lead_hours': None,
                'tau_Q': round(tau_Q, 4), 'status': 'persistent_from_prior',
            }
        else:
            print(f"  {evt_name:<12}  onset={onset_str}  NO alarm before onset "
                  f"(system inside C* throughout run-up)")
            bank_results[evt_name] = {
                'onset': onset_str, 'first_alarm': None,
                'lead_quarters': None, 'lead_months': None, 'lead_hours': None,
                'tau_Q': round(tau_Q, 4), 'status': 'no_alarm',
            }

    return bank_results


# ══════════════════════════════════════════════════════════════════════════
#  SUMMARY TABLE
# ══════════════════════════════════════════════════════════════════════════

def print_summary(ercot_r, bank_r):
    banner("FROZEN-WINDOW EARLY WARNING SUMMARY  (SIAM paper Algorithm 2)")

    print(f"  Scorer : FrozenWindowScorer — features_with_friction(k=10, η=0.25) → Q channel")
    print(f"  Threshold: τ_Q = χ²_{{0.99}}(d)  (pure theory, zero calibration data)")
    print(f"             Alarm fires when Q(x) > τ_Q  i.e. state vector escapes C*")
    print(f"  Alarm  : last-quiet-window (Q<τ_Q for n_quiet steps) → first-re-alarm")

    print(f"\n  ERCOT — lead time in DAYS / HOURS  (quiet window = 14 days)")
    hdr = f"  {'Event':<26}  {'Lead (days)':>11}  {'Lead (hours)':>13}  {'Status':<22}  Alarm date"
    print(f"  {'-'*85}")
    print(hdr)
    print(f"  {'-'*85}")
    for evt in ['WinterStorm_Uri', 'COVID_Demand_Crash', 'WinterStorm_Elliott']:
        d = ercot_r.get(evt, {})
        ld = d.get('lead_days'); lh = d.get('lead_hours')
        st = d.get('status', '—'); fa = d.get('first_alarm', '—') or '—'
        if ld is not None and st == 'alarm':
            print(f"  {evt:<26}  {ld:>11} d  {lh:>12,} h  {st:<22}  {fa}")
        else:
            print(f"  {evt:<26}  {'—':>11}   {'—':>13}  {st:<22}  —")

    print(f"\n  BANK — lead time in QUARTERS / MONTHS  (quiet window = 3 quarters)")
    hdr2 = f"  {'Event':<14}  {'Lead (Q)':>9}  {'Lead (months)':>14}  {'Lead (hours)':>13}  {'Status':<26}  Alarm date"
    print(f"  {'-'*95}")
    print(hdr2)
    print(f"  {'-'*95}")
    for evt in ['GFC', 'COVID', 'RateShock']:
        d = bank_r.get(evt, {})
        lq = d.get('lead_quarters'); lm = d.get('lead_months'); lh = d.get('lead_hours')
        st = d.get('status', '—'); fa = d.get('first_alarm', '—') or '—'
        if lq is not None and st == 'alarm':
            print(f"  {evt:<14}  {lq:>9} Q  {lm:>13.1f} m  {lh:>12,} h  {st:<26}  {fa}")
        else:
            print(f"  {evt:<14}  {'—':>9}   {'—':>14}  {'—':>13}  {st:<26}  —")


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

def _safe(obj):
    if isinstance(obj, dict):    return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)): return [_safe(v) for v in obj]
    if isinstance(obj, np.floating): return float(obj)
    if isinstance(obj, np.integer):  return int(obj)
    return obj


def main():
    t0 = time.perf_counter()

    ercot_results = {}
    bank_results  = {}

    try:
        ercot_results = analyse_ercot()
    except Exception:
        import traceback; traceback.print_exc()

    try:
        bank_results = analyse_bank()
    except Exception:
        import traceback; traceback.print_exc()

    print_summary(ercot_results, bank_results)

    out = {
        'meta': {
            'run_date': '2026-03-28',
            'scorer': 'FrozenWindowScorer (research.udl.geo_full_pipeline)',
            'method': 'Frozen Calibration Protocol — Algorithm 2, '
                      '"The Geometry of System Collapse" (SIAM paper)',
            'friction': {'k_steps': 10, 'eta': 0.25, 'theta': 1.0},
            'threshold': 'tau_Q = chi2_0.99(d) Wilson-Hilferty approx — '
                         'pure theory, zero calibration data. '
                         'Alarm when Q(x) > tau_Q (state escapes C*).',
            'alarm_logic': 'last-quiet-window -> first-re-alarm: '
                           'find most-recent n_quiet consecutive steps '
                           'score<tau BEFORE onset, then first step >= tau '
                           'after that window. Prevents GFC alarm carry-over.',
            'n_quiet_ercot_days': 14,
            'n_quiet_bank_quarters': 3,
        },
        'ERCOT': {'unit': 'days/hours', 'results': ercot_results},
        'Bank' : {'unit': 'quarters/months/hours', 'results': bank_results},
    }
    with open(OUT_FILE, 'w') as f:
        json.dump(_safe(out), f, indent=2)

    print(f"\n  Runtime: {time.perf_counter()-t0:.1f}s")
    print(f"  Saved  → {OUT_FILE}")


if __name__ == '__main__':
    main()
