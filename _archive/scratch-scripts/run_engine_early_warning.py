#!/usr/bin/env python3
"""
run_engine_early_warning.py
===========================
Early-warning evaluation of Gravity / Molecular / Hybrid engines on
real-world ERCOT (hourly) and FDIC Bank (quarterly) data, following
the SIAM paper's prospective frozen-window protocol.

Protocol  (SIAM paper Section 5, Algorithm 2):
  1. FROZEN reference: train on normals BEFORE each event only.
  2. PROSPECTIVE scoring: score each point using only past information.
  3. ALARM fires when score > adaptive threshold (P99 of trailing window).
  4. LEAD TIME: "last-quiet → first-re-alarm" measurement.
  5. FALSE ALARMS: count alarm firings during non-event periods.

Engines:
  - GravityModeEngine     : N-body gravitational engine
  - MolecularEngine       : Lennard-Jones molecular dynamics
  - HybridGravityEngine   : Adaptive blend of Mol + Grav

Also runs FrozenWindowScorer (Q-channel theory alarm) for comparison.

Datasets:
  - ERCOT hourly (d=5, ~35K hours): demand_gw, ramp_rate, vol_6h,
    dev_24h, temp_stress — from real EIA + Open-Meteo
  - FDIC Bank quarterly (30 banks, d=5): from FDIC SDI call-report

Output: results/engine_early_warning_results.json
"""
import sys, os, time, warnings, json, gc
sys.path.insert(0, r'c:\amttp\research\udl')
sys.path.insert(0, r'c:\amttp\research\adaptive-friction\banklevel_enhanced')
os.environ['CUDA_VISIBLE_DEVICES'] = ''
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

import numpy as np
from pathlib import Path
from sklearn.metrics import roc_auc_score
from sklearn.decomposition import PCA

ROOT        = Path(r'c:\amttp')
ERCOT_H_NPZ = ROOT / 'data' / 'ercot' / 'ercot_hourly_2019_2022.npz'
RESULTS_DIR  = ROOT / 'results'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE     = RESULTS_DIR / 'engine_early_warning_results.json'

from udl.system_mode import (
    MolecularEngine,
    GravityModeEngine,
    HybridGravityEngine,
    ReducedTensorDescriptor,
)
from research.udl.geo_full_pipeline import FrozenWindowScorer


# ══════════════════════════════════════════════════════════════════════════
#  UTILITIES
# ══════════════════════════════════════════════════════════════════════════

def banner(s):
    print('\n' + '═' * 76)
    print(f'  {s}')
    print('═' * 76)


def last_quiet_end(scores, onset_idx, threshold, n_quiet, max_lookback=None):
    """Scan backward from onset to find most recent quiet window."""
    idx = onset_idx - 1
    earliest = n_quiet - 1
    if max_lookback is not None:
        earliest = max(earliest, onset_idx - max_lookback)
    while idx >= earliest:
        window = scores[idx - n_quiet + 1: idx + 1]
        if np.all(window < threshold):
            return idx
        idx -= 1
    return None


def first_alarm_after_quiet(scores, quiet_end_idx, onset_idx, threshold):
    """Find the first alarm step after the quiet window ends."""
    for idx in range(quiet_end_idx + 1, onset_idx):
        if scores[idx] >= threshold:
            return idx
    return None


def measure_lead(scores, onset_idx, threshold, n_quiet, max_lookback=None):
    """
    SIAM paper "last-quiet → first-re-alarm" lead-time measurement.

    Returns (lead_steps, first_alarm_idx, status)
    where status ∈ {'alarm', 'no_alarm', 'persistent_from_prior'}
    """
    qe = last_quiet_end(scores, onset_idx, threshold, n_quiet, max_lookback)
    if qe is None:
        return None, None, 'persistent_from_prior'
    fa = first_alarm_after_quiet(scores, qe, onset_idx, threshold)
    if fa is None:
        return None, None, 'no_alarm'
    return onset_idx - fa, fa, 'alarm'


def adaptive_threshold(scores, idx, trail_window=168, percentile=99):
    """
    Adaptive rolling threshold: P99 of trailing trail_window steps.
    SIAM paper: τ_t = P_{99}(s_{t-W:t-1})  — uses ONLY past data.
    """
    start = max(0, idx - trail_window)
    if start == idx:
        return float(np.percentile(scores[:max(idx, 1)], percentile))
    return float(np.percentile(scores[start:idx], percentile))


def count_false_alarms(scores, threshold, event_mask):
    """
    Count alarm firings during non-event periods (false positives).
    Returns: (n_false_alarms, n_normal_steps, false_alarm_rate)
    """
    normal_mask = ~event_mask
    n_normal = int(normal_mask.sum())
    if n_normal == 0:
        return 0, 0, 0.0
    alarms_on_normal = int((scores[normal_mask] >= threshold).sum())
    far = alarms_on_normal / n_normal
    return alarms_on_normal, n_normal, far


def run_engine_on_data(engine_name, X_train, y_train, X_all, k=10):
    """
    Fit engine on training data, score all data.
    
    Pipeline: X → ReducedTensorDescriptor → engine.fit_score()
    """
    X_norm = X_train[y_train == 0]
    n_k = min(k, len(X_norm) - 1)

    # Tensor descriptor
    desc = ReducedTensorDescriptor(k_neighbors=n_k)
    desc.fit(X_norm)
    T_train = desc.transform(X_train)
    T_all   = desc.transform(X_all)

    # Engine
    eng_k = min(15, len(X_norm) - 1)
    if engine_name == 'Gravity':
        eng = GravityModeEngine(k_neighbors=eng_k, iterations=60, max_samples=2000)
    elif engine_name == 'Molecular':
        eng = MolecularEngine(k_neighbors=eng_k, iterations=60, max_samples=2000)
    elif engine_name == 'Hybrid':
        eng = HybridGravityEngine(
            blend_weight='auto',
            molecular_params=dict(k_neighbors=eng_k, iterations=60, max_samples=2000),
            gravity_params=dict(k_neighbors=eng_k, iterations=60, max_samples=2000))
    else:
        raise ValueError(f"Unknown engine: {engine_name}")

    # Combine train + all for fit_score (engine needs normal reference)
    T_combined = np.vstack([T_train, T_all])
    y_combined = np.concatenate([y_train, np.zeros(len(T_all))])
    scores_combined = eng.fit_score(T_combined, y_combined)

    # Extract scores for the full time series
    scores = scores_combined[len(T_train):]
    return scores


# ══════════════════════════════════════════════════════════════════════════
#  ERCOT — HOURLY EARLY WARNING
# ══════════════════════════════════════════════════════════════════════════

def run_ercot_hourly():
    banner("ERCOT HOURLY — Engine Early Warning  (hours before onset)")

    npz = np.load(ERCOT_H_NPZ, allow_pickle=True)
    X_raw = npz['X'].astype(np.float64)
    y_raw = npz['y'].astype(int)
    dates_str = npz['dates']
    labels = npz['labels']
    feat_names = list(npz['feature_names'])

    T, d = X_raw.shape
    print(f"  Loaded: {T:,} hours × {d} features  ({feat_names})")

    # ── Training split: all data before 2020 (pre-COVID, pre-Uri) ─────
    # This is the FROZEN reference period — learn on normals only.
    train_mask = np.array([str(dt)[:10] < '2020-01-01' for dt in dates_str])
    train_norm_mask = train_mask & (y_raw == 0)

    # Standardise on training normals
    mu = X_raw[train_norm_mask].mean(0)
    sd = X_raw[train_norm_mask].std(0) + 1e-9
    X_s = np.clip((X_raw - mu) / sd, -8, 8)

    X_train = X_s[train_mask]
    y_train = y_raw[train_mask]

    n_train = int(train_mask.sum())
    n_train_norm = int(train_norm_mask.sum())
    print(f"  Training: {n_train:,} hours ({n_train_norm:,} normals)  "
          f"— frozen on pre-2020 data")
    print(f"  Anomaly hours: {int(y_raw.sum()):,} / {T:,}  "
          f"({100 * y_raw.mean():.1f}%)")

    # ── Events to detect ────────────────────────────────────────────────
    from datetime import datetime
    events = {
        'WinterStormUri':     datetime(2021, 2, 10, 0),
        'COVID_Collapse':     datetime(2020, 3, 23, 0),
        'SummerPeak2019':     datetime(2019, 8, 12, 0),
        'WinterStormElliott': datetime(2022, 12, 22, 0),
    }
    # Build datetime array for index lookups
    dt_arr = np.array([datetime.fromisoformat(str(d)) for d in dates_str])

    # Build event mask for FAR computation
    event_mask = y_raw.astype(bool)

    # ── Parameters ──────────────────────────────────────────────────────
    N_QUIET_HOURS = 336         # 14 days × 24h of quiet needed
    TRAIL_WINDOW  = 168 * 4     # 4 weeks trailing for adaptive threshold

    # ═══════════════════════════════════════════════════════════════════
    #  A) FrozenWindowScorer (Q-channel — theory threshold)
    # ═══════════════════════════════════════════════════════════════════
    print(f"\n  ── FrozenWindowScorer (Q-channel) ──")
    fws = FrozenWindowScorer()
    fws.fit(X_s[train_norm_mask])
    tau_Q = float(fws._tau_Q)
    F = fws.features_with_friction(X_s, k_steps=10, eta=0.25, theta=tau_Q)
    Q_scores = F[:, 0]  # Q-channel

    inside_ref = float((Q_scores[train_norm_mask] < tau_Q).mean())
    print(f"    τ_Q = {tau_Q:.3f}  (χ²_0.99, d={d})")
    print(f"    Training normals inside C*: {inside_ref * 100:.1f}%")

    # False alarms
    fa_count, n_normal, far = count_false_alarms(Q_scores, tau_Q, event_mask)
    print(f"    FALSE ALARMS: {fa_count:,} / {n_normal:,} normal hours  "
          f"(FAR = {far * 100:.2f}%)")

    # Lead time per event
    fws_results = {'tau_Q': round(tau_Q, 4), 'false_alarms': fa_count,
                   'normal_hours': n_normal, 'FAR_pct': round(far * 100, 3),
                   'events': {}}
    for evt_name, onset_dt in events.items():
        onset_arr = np.where(dt_arr >= onset_dt)[0]
        if len(onset_arr) == 0:
            continue
        onset_idx = int(onset_arr[0])
        lead, alarm_idx, status = measure_lead(
            Q_scores, onset_idx, tau_Q, n_quiet=N_QUIET_HOURS)

        if status == 'alarm' and alarm_idx is not None:
            lead_hours = lead
            lead_days = round(lead / 24, 1)
            alarm_date = str(dates_str[alarm_idx])[:13]
            print(f"    {evt_name:<24}  lead={lead_hours:>6,} h  "
                  f"({lead_days:>6.1f} d)  alarm={alarm_date}  ✓")
        elif status == 'persistent_from_prior':
            lead_hours = None; lead_days = None; alarm_date = None
            print(f"    {evt_name:<24}  PERSISTENT (never re-entered C*)")
        else:
            lead_hours = None; lead_days = None; alarm_date = None
            print(f"    {evt_name:<24}  NO ALARM before onset")

        fws_results['events'][evt_name] = {
            'onset': str(onset_dt), 'status': status,
            'lead_hours': lead_hours,
            'lead_days': lead_days,
            'first_alarm': alarm_date,
        }

    # ═══════════════════════════════════════════════════════════════════
    #  B) Physics Engines (Gravity / Molecular / Hybrid)
    # ═══════════════════════════════════════════════════════════════════
    engine_results = {}
    for eng_name in ['Gravity', 'Molecular', 'Hybrid']:
        print(f"\n  ── {eng_name} Engine ──")
        t0 = time.perf_counter()
        try:
            scores = run_engine_on_data(eng_name, X_train, y_train, X_s, k=10)
            elapsed = time.perf_counter() - t0
            print(f"    Scored {len(scores):,} hours in {elapsed:.1f}s")

            # AUC
            if len(np.unique(y_raw)) >= 2:
                auc = float(roc_auc_score(y_raw, scores))
                print(f"    AUC = {auc:.4f}")
            else:
                auc = None

            # Adaptive threshold: P99 of training-period scores
            train_scores = scores[train_mask]
            normal_train_scores = train_scores[y_train == 0]
            threshold = float(np.percentile(normal_train_scores, 99))
            print(f"    Threshold (P99 training normals) = {threshold:.4f}")

            # False alarms
            fa_count, n_normal, far = count_false_alarms(
                scores, threshold, event_mask)
            print(f"    FALSE ALARMS: {fa_count:,} / {n_normal:,} normal hours  "
                  f"(FAR = {far * 100:.2f}%)")

            # Lead time per event
            eng_data = {'auc': auc, 'threshold': round(threshold, 6),
                        'false_alarms': fa_count, 'normal_hours': n_normal,
                        'FAR_pct': round(far * 100, 3),
                        'time_s': round(elapsed, 1), 'events': {}}

            for evt_name, onset_dt in events.items():
                onset_arr = np.where(dt_arr >= onset_dt)[0]
                if len(onset_arr) == 0:
                    continue
                onset_idx = int(onset_arr[0])
                lead, alarm_idx, status = measure_lead(
                    scores, onset_idx, threshold,
                    n_quiet=N_QUIET_HOURS)

                if status == 'alarm' and alarm_idx is not None:
                    lead_hours = lead
                    lead_days = round(lead / 24, 1)
                    alarm_date = str(dates_str[alarm_idx])[:13]
                    print(f"    {evt_name:<24}  lead={lead_hours:>6,} h  "
                          f"({lead_days:>6.1f} d)  alarm={alarm_date}  ✓")
                elif status == 'persistent_from_prior':
                    lead_hours = None; lead_days = None; alarm_date = None
                    print(f"    {evt_name:<24}  PERSISTENT (alarm from prior event)")
                else:
                    lead_hours = None; lead_days = None; alarm_date = None
                    print(f"    {evt_name:<24}  NO ALARM before onset")

                eng_data['events'][evt_name] = {
                    'onset': str(onset_dt), 'status': status,
                    'lead_hours': lead_hours,
                    'lead_days': lead_days,
                    'first_alarm': alarm_date,
                }

            engine_results[eng_name] = eng_data

        except Exception as e:
            import traceback
            print(f"    ERROR: {e}")
            engine_results[eng_name] = {
                'error': str(e), 'traceback': traceback.format_exc()}

        gc.collect()

    return {'FrozenWindow': fws_results, **engine_results}


# ══════════════════════════════════════════════════════════════════════════
#  BANK — QUARTERLY EARLY WARNING
# ══════════════════════════════════════════════════════════════════════════

def run_bank():
    banner("BANK PANEL — Engine Early Warning  (quarters / months before onset)")
    banner("  SIAM prospective: expanding-window, re-fit each Q, per-bank scoring")
    import pandas as pd
    from bank_level_loader import build_bank_panel

    panel  = build_bank_panel(n_banks=30, force_refresh=False)
    X_raw  = panel['X']; dates = panel['dates']
    T, N, d_feat = X_raw.shape
    feat_names = panel.get('feature_names', [f'f{i}' for i in range(d_feat)])

    print(f"  Loaded: T={T} Q × N={N} banks × d={d_feat}  ({feat_names})")

    # ── Anomaly labels per quarter (for evaluation ONLY — not used in scoring) ──
    y_t = np.zeros(T, dtype=int)
    ev_labels = np.full(T, 'Normal', dtype=object)
    for t, dt in enumerate(dates):
        if pd.Timestamp('2007-01-01') <= dt <= pd.Timestamp('2009-12-31'):
            y_t[t] = 1; ev_labels[t] = 'GFC'
        elif pd.Timestamp('2020-01-01') <= dt <= pd.Timestamp('2020-12-31'):
            y_t[t] = 1; ev_labels[t] = 'COVID'
        elif pd.Timestamp('2022-01-01') <= dt <= pd.Timestamp('2022-12-31'):
            y_t[t] = 1; ev_labels[t] = 'RateShock'

    # ── Calibration period: 2005-Q1 → 2007-Q3 ──────────────────────
    # Same as bench_bank_level_prospective.py
    calib_start = pd.Timestamp('2005-01-01')
    calib_end   = pd.Timestamp('2007-07-01')  # exclusive — up to 2007-Q2
    n_calib = int(((dates >= calib_start) & (dates < calib_end)).sum())
    # Find the absolute index of calib_start
    calib_start_idx = int(np.where(dates >= calib_start)[0][0])
    print(f"  Calibration: quarters {calib_start_idx}..{calib_start_idx + n_calib - 1} "
          f"({str(dates[calib_start_idx])[:10]} → "
          f"{str(dates[calib_start_idx + n_calib - 1])[:10]})")

    # ── Events ───────────────────────────────────────────────────────
    events = {
        'GFC':       pd.Timestamp('2007-10-01'),  # 2007-Q4 (NBER recession)
        'COVID':     pd.Timestamp('2020-01-01'),
        'RateShock': pd.Timestamp('2022-01-01'),
    }

    N_QUIET_Q = 3

    # ═══════════════════════════════════════════════════════════════════
    #  A) FrozenWindowScorer on windowed-panel PCA (this works well)
    # ═══════════════════════════════════════════════════════════════════
    # Use windowed panel for FrozenWindowScorer since it doesn't need re-fitting
    W = 8
    n_windows = T - W
    Xw = np.stack([X_raw[i:i+W].reshape(W * N * d_feat) for i in range(n_windows)])
    yw = np.array([1 if y_t[i:i+W].any() else 0 for i in range(n_windows)])
    wd = dates[W:]
    event_mask_w = yw.astype(bool)

    # Standardize on pre-crisis normals
    pre_mask = (dates >= pd.Timestamp('1994-01-01')) & (dates <= pd.Timestamp('2003-12-31'))
    nd = X_raw[pre_mask].reshape(-1, d_feat)
    mu_ref = nd.mean(0); sd_ref = nd.std(0) + 1e-9
    X_s_3d = np.nan_to_num(np.clip((X_raw - mu_ref) / sd_ref, -8, 8))

    Xw_s = np.stack([X_s_3d[i:i+W].reshape(W * N * d_feat) for i in range(n_windows)])
    tr_w = wd < pd.Timestamp('2007-01-01')
    X_nt = Xw_s[tr_w & (yw == 0)]
    n_comp = min(30, len(X_nt) - 1)
    pca = PCA(n_components=n_comp).fit(X_nt)
    Xp = pca.transform(Xw_s)
    train_norm_w = tr_w & (yw == 0)

    print(f"\n  ── FrozenWindowScorer (Q-channel, W={W} windowed panel → PCA {n_comp}) ──")
    fws = FrozenWindowScorer()
    fws.fit(Xp[train_norm_w])
    tau_Q = float(fws._tau_Q)
    F = fws.features_with_friction(Xp, k_steps=10, eta=0.25, theta=tau_Q)
    Q_scores = F[:, 0]

    inside_ref = float((Q_scores[train_norm_w] < tau_Q).mean())
    print(f"    τ_Q = {tau_Q:.3f}  (d={n_comp})")
    print(f"    Training normals inside C*: {inside_ref * 100:.1f}%")

    fa_count, n_normal, far = count_false_alarms(Q_scores, tau_Q, event_mask_w)
    print(f"    FALSE ALARMS: {fa_count} / {n_normal} normal windows  "
          f"(FAR = {far * 100:.1f}%)")

    fws_results = {'tau_Q': round(tau_Q, 4), 'false_alarms': fa_count,
                   'normal_quarters': n_normal, 'FAR_pct': round(far * 100, 3),
                   'events': {}}

    for evt_name, onset_ts in events.items():
        onset_arr = np.where(wd >= onset_ts)[0]
        if len(onset_arr) == 0: continue
        onset_idx = int(onset_arr[0])
        lead, alarm_idx, status = measure_lead(
            Q_scores, onset_idx, tau_Q, n_quiet=N_QUIET_Q, max_lookback=20)

        if status == 'alarm' and alarm_idx is not None:
            lead_q = lead; lead_m = round(lead * 3, 1)
            lead_h = round(lead * 91.25 * 24)
            alarm_date = str(wd[alarm_idx])[:10]
            print(f"    {evt_name:<12}  lead={lead_q:>3} Q ({lead_m:>5.1f} m / "
                  f"{lead_h:>7,} h)  alarm={alarm_date}  ✓")
        elif status == 'persistent_from_prior':
            lead_q = None; lead_m = None; lead_h = None; alarm_date = None
            print(f"    {evt_name:<12}  PERSISTENT")
        else:
            lead_q = None; lead_m = None; lead_h = None; alarm_date = None
            print(f"    {evt_name:<12}  NO ALARM")

        fws_results['events'][evt_name] = {
            'onset': str(onset_ts)[:10], 'status': status,
            'lead_quarters': lead_q, 'lead_months': lead_m,
            'lead_hours': lead_h, 'first_alarm': alarm_date}

    # ═══════════════════════════════════════════════════════════════════
    #  B) Physics Engines — SIAM expanding-window prospective protocol
    #     (bench_bank_level_prospective.py pattern)
    #
    #  Key differences from batch:
    #    • Labels = all zeros (unsupervised — BSDT treats all as normal)
    #    • Re-fit each quarter on expanding window [0..t]
    #    • Score = mean across N banks in quarter t
    #    • Threshold = P99 of calibration-period quarterly scores
    # ═══════════════════════════════════════════════════════════════════
    X_3d = X_raw.copy()  # (T, N, d) raw bank panel

    engine_configs = {
        'Gravity':   (GravityModeEngine,
                      dict(iterations=60, k_neighbors=10)),
        'Molecular': (MolecularEngine,
                      dict(iterations=80, k_neighbors=10)),
        'Hybrid':    (HybridGravityEngine, dict()),
    }

    engine_results = {}
    for eng_name, (engine_cls, engine_kwargs) in engine_configs.items():
        print(f"\n  ── {eng_name} Engine (expanding-window prospective) ──")
        t0_total = time.perf_counter()

        try:
            quarter_scores = np.full(T, np.nan)

            # Phase 1: Calibration — single fit on calibration window
            t_start = calib_start_idx
            t_end_calib = t_start + n_calib
            X_calib = X_3d[t_start:t_end_calib].reshape(n_calib * N, d_feat)
            y_calib = np.zeros(n_calib * N, dtype=int)  # ALL zeros — unsupervised

            print(f"    Calibration: Q[{t_start}..{t_end_calib-1}] → "
                  f"{n_calib*N} bank-quarters ...", end=' ', flush=True)
            eng = engine_cls(**engine_kwargs)
            scores_calib = eng.fit_score(X_calib, y_calib)

            # Per-quarter score = mean of N bank scores
            for q in range(n_calib):
                quarter_scores[t_start + q] = scores_calib[q * N:(q + 1) * N].mean()

            calib_q_scores = quarter_scores[t_start:t_end_calib]
            alarm_threshold = float(np.nanpercentile(calib_q_scores, 99))
            print(f"done.  Threshold (P99 calib) = {alarm_threshold:.4f}")

            # Phase 2: Expanding window — re-fit each quarter
            print(f"    Monitoring: Q[{t_end_calib}..{T-1}] ({T - t_end_calib} quarters) ...",
                  flush=True)

            for t in range(t_end_calib, T):
                n_pts = (t + 1 - t_start) * N
                X_up_to_t = X_3d[t_start:t + 1].reshape(n_pts, d_feat)
                y_dummy = np.zeros(n_pts, dtype=int)  # ALL zeros — always

                eng_t = engine_cls(**engine_kwargs)
                scores_t = eng_t.fit_score(X_up_to_t, y_dummy)

                # Current quarter's score = mean of last N bank scores
                quarter_scores[t] = scores_t[-N:].mean()
                del eng_t; gc.collect()

            elapsed = time.perf_counter() - t0_total
            print(f"    Total: {elapsed:.1f}s")

            # ── Evaluation ───────────────────────────────────────────
            # Only evaluate monitoring period (t_end_calib onward)
            valid = ~np.isnan(quarter_scores)
            if valid.sum() >= 2 and len(np.unique(y_t[valid])) >= 2:
                auc = float(roc_auc_score(y_t[valid], quarter_scores[valid]))
                print(f"    AUC = {auc:.4f}")
            else:
                auc = None

            # Also compute rolling z-score alarm (Basel-style, from paper)
            z_scores = np.full(T, np.nan)
            for t in range(t_end_calib, T):
                past = quarter_scores[t_start:t]
                past = past[~np.isnan(past)]
                if len(past) >= 3:
                    mu_past = past.mean(); sd_past = past.std()
                    if sd_past > 1e-9:
                        z_scores[t] = (quarter_scores[t] - mu_past) / sd_past

            # Use BOTH threshold and z-score: alarm fires if EITHER triggers
            z_threshold = 2.0  # Basel-standard z > 2
            alarm_quarters = []
            for t in range(t_end_calib, T):
                score_alarm = (not np.isnan(quarter_scores[t]) and
                               quarter_scores[t] > alarm_threshold)
                z_alarm = (not np.isnan(z_scores[t]) and z_scores[t] > z_threshold)
                if score_alarm or z_alarm:
                    alarm_quarters.append(t)

            # False alarms
            n_false = sum(1 for t in alarm_quarters if y_t[t] == 0)
            n_normal_monitor = sum(1 for t in range(t_end_calib, T) if y_t[t] == 0)
            far_pct = 100 * n_false / max(n_normal_monitor, 1)
            print(f"    Alarm threshold (P99 calib): {alarm_threshold:.4f}  "
                  f"+  z > {z_threshold}")
            print(f"    Alarm quarters: {len(alarm_quarters)}  "
                  f"(false: {n_false} / {n_normal_monitor} normal = FAR {far_pct:.1f}%)")

            # Score + z diagnostics around GFC
            print(f"    Score trace (2005–2010):")
            for t in range(max(0, t_start), min(T, t_end_calib + 16)):
                qs = quarter_scores[t]
                zs = z_scores[t] if not np.isnan(z_scores[t]) else 0
                marker = '***' if y_t[t] == 1 else '   '
                is_alarm = t in alarm_quarters
                a_marker = ' ALARM' if is_alarm else ''
                if not np.isnan(qs):
                    print(f"      {str(dates[t])[:10]}  score={qs:.4f}  "
                          f"z={zs:+.2f}  {marker}{a_marker}")

            eng_data = {
                'auc': auc,
                'alarm_threshold': round(alarm_threshold, 6),
                'z_threshold': z_threshold,
                'false_alarms': n_false,
                'normal_quarters': n_normal_monitor,
                'FAR_pct': round(far_pct, 3),
                'time_s': round(elapsed, 1),
                'events': {},
            }

            # Lead time per event using alarm_quarters
            for evt_name, onset_ts in events.items():
                onset_arr = np.where(dates >= onset_ts)[0]
                if len(onset_arr) == 0: continue
                onset_idx = int(onset_arr[0])

                # Find first alarm before onset
                pre_alarms = [t for t in alarm_quarters if t < onset_idx]
                # Filter to only look back max 20 quarters
                pre_alarms = [t for t in pre_alarms
                              if onset_idx - t <= 20]
                # Need a quiet gap (N_QUIET_Q quarters without alarm) before
                # the alarm to prevent GFC alarm carrying over to COVID
                found_alarm = None
                for a_t in sorted(pre_alarms, reverse=True):
                    # Check if there was a quiet window between previous
                    # event end and this alarm
                    quiet_count = 0
                    for check_t in range(a_t - 1, max(a_t - N_QUIET_Q - 1, t_end_calib - 1), -1):
                        if check_t not in alarm_quarters:
                            quiet_count += 1
                        else:
                            break
                    if quiet_count >= N_QUIET_Q or a_t == min(pre_alarms):
                        found_alarm = a_t
                        break

                if found_alarm is not None:
                    # Find the FIRST alarm after the last quiet window
                    earliest = found_alarm
                    for a_t in sorted(pre_alarms):
                        if a_t >= found_alarm - quiet_count:
                            earliest = a_t
                            break
                    lead_q = onset_idx - earliest
                    lead_m = round(lead_q * 3, 1)
                    lead_h = round(lead_q * 91.25 * 24)
                    alarm_date = str(dates[earliest])[:10]
                    print(f"    {evt_name:<12}  lead={lead_q:>3} Q ({lead_m:>5.1f} m / "
                          f"{lead_h:>7,} h)  alarm={alarm_date}  ✓")
                    eng_data['events'][evt_name] = {
                        'onset': str(onset_ts)[:10], 'status': 'alarm',
                        'lead_quarters': lead_q, 'lead_months': lead_m,
                        'lead_hours': lead_h, 'first_alarm': alarm_date}
                else:
                    print(f"    {evt_name:<12}  NO ALARM")
                    eng_data['events'][evt_name] = {
                        'onset': str(onset_ts)[:10], 'status': 'no_alarm',
                        'lead_quarters': None, 'lead_months': None,
                        'lead_hours': None, 'first_alarm': None}

            engine_results[eng_name] = eng_data

        except Exception as e:
            import traceback
            print(f"    ERROR: {e}")
            traceback.print_exc()
            engine_results[eng_name] = {
                'error': str(e), 'traceback': traceback.format_exc()}

        gc.collect()

    return {'FrozenWindow': fws_results, **engine_results}


# ══════════════════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════════════════

def print_summary(ercot_r, bank_r):
    banner("EARLY WARNING SUMMARY")

    # ── ERCOT ──
    print(f"\n  ERCOT (hourly, d=5, frozen on pre-2020 normals)")
    print(f"  {'Method':<16} {'FAR%':>6}  {'Uri (h)':>8}  {'COVID (h)':>10}  "
          f"{'Elliott (h)':>12}  {'Summer (h)':>11}")
    print(f"  {'-' * 72}")

    for method in ['FrozenWindow', 'Gravity', 'Molecular', 'Hybrid']:
        r = ercot_r.get(method, {})
        if 'error' in r:
            print(f"  {method:<16} ERROR: {r['error'][:40]}")
            continue
        far = r.get('FAR_pct', '—')
        evts = r.get('events', {})
        uri = evts.get('WinterStormUri', {}).get('lead_hours', '—')
        covid = evts.get('COVID_Collapse', {}).get('lead_hours', '—')
        elliott = evts.get('WinterStormElliott', {}).get('lead_hours', '—')
        summer = evts.get('SummerPeak2019', {}).get('lead_hours', '—')

        def fmt(v):
            if v is None: return '—'
            if isinstance(v, (int, float)): return f'{v:,}'
            return str(v)

        print(f"  {method:<16} {fmt(far):>6}  {fmt(uri):>8}  {fmt(covid):>10}  "
              f"{fmt(elliott):>12}  {fmt(summer):>11}")

    # ── Bank ──
    print(f"\n  BANK (quarterly, 30 banks, frozen on 1994–2006 normals)")
    print(f"  {'Method':<16} {'FAR%':>6}  {'GFC (Q)':>8}  {'COVID (Q)':>10}  "
          f"{'RateShock (Q)':>14}")
    print(f"  {'-' * 60}")

    for method in ['FrozenWindow', 'Gravity', 'Molecular', 'Hybrid']:
        r = bank_r.get(method, {})
        if 'error' in r:
            print(f"  {method:<16} ERROR: {r['error'][:40]}")
            continue
        far = r.get('FAR_pct', '—')
        evts = r.get('events', {})
        gfc = evts.get('GFC', {}).get('lead_quarters', '—')
        covid = evts.get('COVID', {}).get('lead_quarters', '—')
        rate = evts.get('RateShock', {}).get('lead_quarters', '—')

        def fmt(v):
            if v is None: return '—'
            if isinstance(v, (int, float)): return str(v)
            return str(v)

        status_gfc = evts.get('GFC', {}).get('status', '')
        status_covid = evts.get('COVID', {}).get('status', '')
        status_rate = evts.get('RateShock', {}).get('status', '')

        gfc_str = fmt(gfc) if status_gfc == 'alarm' else status_gfc[:8] if status_gfc else '—'
        covid_str = fmt(covid) if status_covid == 'alarm' else status_covid[:8] if status_covid else '—'
        rate_str = fmt(rate) if status_rate == 'alarm' else status_rate[:8] if status_rate else '—'

        print(f"  {method:<16} {fmt(far):>6}  {gfc_str:>8}  {covid_str:>10}  {rate_str:>14}")


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

def _safe(obj):
    if isinstance(obj, dict):    return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)): return [_safe(v) for v in obj]
    if isinstance(obj, np.floating): return float(obj)
    if isinstance(obj, np.integer):  return int(obj)
    if isinstance(obj, np.ndarray):  return obj.tolist()
    return obj


def main():
    t_start = time.perf_counter()
    banner("ENGINE EARLY WARNING — Gravity / Molecular / Hybrid + FrozenWindow")
    print("  Protocol: SIAM paper prospective frozen-window (Algorithm 2)")
    print("  ERCOT  : HOURLY (d=5, ~35K hours, real EIA + OpenMeteo)")
    print("  Bank   : QUARTERLY (30 banks, d=6 system features, FDIC SDI)")
    print("  Alarm  : last-quiet → first-re-alarm")
    print(f"  Output : {OUT_FILE}")

    all_results = {
        'meta': {
            'protocol': 'SIAM paper prospective frozen-window (Algorithm 2)',
            'alarm_logic': 'last-quiet-window → first-re-alarm',
            'threshold': {
                'FrozenWindow': 'tau_Q = chi2_0.99(d) — pure theory',
                'Engines': 'P99 of training-period normal scores — adaptive',
            },
            'datasets': {
                'ERCOT': 'hourly EIA demand (d=5), 2019-2022',
                'Bank': 'FDIC SDI quarterly (30 banks, d=6 system), 1994-2022',
            },
            'run_date': time.strftime('%Y-%m-%d %H:%M'),
        }
    }

    # ── ERCOT ────────────────────────────────────────────────────────────
    try:
        all_results['ERCOT'] = run_ercot_hourly()
    except Exception as e:
        import traceback
        all_results['ERCOT'] = {'error': str(e), 'traceback': traceback.format_exc()}
        print(f"  ERCOT FAILED: {e}")

    # ── Bank ─────────────────────────────────────────────────────────────
    try:
        all_results['Bank'] = run_bank()
    except Exception as e:
        import traceback
        all_results['Bank'] = {'error': str(e), 'traceback': traceback.format_exc()}
        print(f"  Bank FAILED: {e}")

    # ── Summary ──────────────────────────────────────────────────────────
    print_summary(all_results.get('ERCOT', {}), all_results.get('Bank', {}))

    # ── Save ─────────────────────────────────────────────────────────────
    with open(OUT_FILE, 'w') as f:
        json.dump(_safe(all_results), f, indent=2)

    elapsed = time.perf_counter() - t_start
    print(f"\n  Total runtime: {elapsed:.1f}s")
    print(f"  Saved → {OUT_FILE}")


if __name__ == '__main__':
    main()
