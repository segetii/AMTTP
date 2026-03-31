"""
ercot_adaptive_posthoc.py
=========================
Paper-compliant ERCOT expanding-window benchmark with BSDT/MFLS corrections.

Follows the EXACT protocol from test_insample_calibrated.py (SIAM paper):
  1. Expanding window: at each monitoring week w, train on weeks [0..w]
  2. Engine fit_score(X_up, y_zeros) with BSDT adaptive damping
  3. BSDTChannels fitted on eng.X_final_ (converged simulation positions)
  4. Channels extracted on X_up (original data)
  5. MFLS correction layer on channels -> final score for week w

MFLS variants:
  - Fisher:   _MFLSFisherBSDT (unsupervised, Fisher VR channel weighting)
  - QuadSurf: _MFLSQuadSurf   (supervised ridge on polynomial channels)
  - ExpoGate: _MFLSExpoGate   (supervised: tanh-gated QuadSurf output)
  - BSDT E_BS: BSDTChannels.energy (unsupervised baseline)
  When no crisis labels available yet -> falls back to Fisher (paper protocol)

Calibration methods:
  Fixed mu+3sig | Fixed P99 | Fixed med+3MAD |
  Adaptive z>3 | Adaptive z>2 | Adaptive P99 |
  Isotonic | Platt sigmoid | Conformal p-value

Caching: Phase A caches all variant scores per engine.
         Phase B applies calibrations (fast, repeatable).
"""
from __future__ import annotations
import sys, os, time, json, warnings, gc
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional
from sklearn.metrics import roc_auc_score
from sklearn.isotonic import IsotonicRegression
from sklearn.preprocessing import StandardScaler

os.environ['CUDA_VISIBLE_DEVICES'] = ''
warnings.filterwarnings("ignore")

ROOT = Path(r"c:\amttp")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "udl"))

from research.udl.udl.system_mode import (
    MolecularEngine, GravityModeEngine, HybridGravityEngine,
    BSDTChannels, FusedSystemScorer,
    _MFLSFisherBSDT, _MFLSQuadSurf, _MFLSExpoGate,
)

H = 168  # hours per week
CACHE = ROOT / "results" / "ercot_paper_compliant_cache.json"

EVENT_ONSETS = {
    "SummerPeak2019":     pd.Timestamp("2019-08-12"),
    "COVID_Collapse":     pd.Timestamp("2020-03-23"),
    "WinterStormUri":     pd.Timestamp("2021-02-10"),
    "WinterStormElliott": pd.Timestamp("2022-12-22"),
}


# =====================================================================
#  Load ERCOT
# =====================================================================

def load_ercot():
    npz = np.load(ROOT / "data" / "ercot" / "ercot_hourly_2019_2022.npz",
                  allow_pickle=True)
    X = npz["X"]; dates = pd.to_datetime(npz["dates"])
    y = npz["y"].astype(int); labels = npz["labels"]

    n_weeks = len(X) // H; n_hours = n_weeks * H
    X_t = X[:n_hours]; d_t = dates[:n_hours]; y_t = y[:n_hours]
    lb_t = labels[:n_hours]

    X_3d = X_t.reshape(n_weeks, H, X.shape[1])
    week_dates = d_t[::H]
    y_week = np.array([y_t[i*H:(i+1)*H].any()
                       for i in range(n_weeks)]).astype(int)
    wk_labels = []
    for i in range(n_weeks):
        chunk = lb_t[i*H:(i+1)*H]
        nn = [l for l in chunk if l != 'Normal']
        wk_labels.append(nn[0] if nn else 'Normal')

    calib_mask = week_dates <= pd.Timestamp("2019-06-30")
    n_calib = int(calib_mask.sum())
    return X_3d, X_t, week_dates, y_week, np.array(wk_labels), n_calib


# =====================================================================
#  Paper-Compliant Expanding-Window Scoring
#  (Mirrors test_insample_calibrated.py::prospective_score_posthoc)
# =====================================================================

def expanding_window_all_variants(X_3d, X_flat, y_week, engine_cls,
                                  engine_kwargs, n_calib, eng_name):
    """Run engine expanding-window and extract ALL scoring variants.

    For each week w, simultaneously extracts:
      - 'fused'    : FusedSystemScorer output (engine's own fused score)
      - 'bsdt_e'   : BSDTChannels.energy  (unsupervised baseline)
      - 'fisher'   : _MFLSFisherBSDT  (unsupervised, Fisher VR weights)
      - 'quadsurf' : _MFLSQuadSurf    (supervised if labels available)
      - 'expogate' : _MFLSExpoGate    (supervised if labels available)

    Returns dict of {variant_name: np.array(n_weeks)}.
    """
    n_weeks, Hw, d = X_3d.shape
    variants = ['fused', 'bsdt_e', 'fisher', 'quadsurf', 'expogate']
    weekly = {v: np.full(n_weeks, np.nan) for v in variants}

    is_hybrid = (engine_cls == HybridGravityEngine)

    # Engine kwargs: for fused variant, use_fused=True
    # For posthoc variants, use_fused=False (channels only)
    # HybridGravityEngine doesn't accept use_fused (passes through to sub-engines)
    if is_hybrid:
        fused_kwargs = {**engine_kwargs}
        posthoc_kwargs = {**engine_kwargs}  # extract X_final_ from internal mol
    else:
        fused_kwargs = {**engine_kwargs, 'use_fused': True}
        posthoc_kwargs = {**engine_kwargs, 'use_fused': False}

    def _get_X_final(eng):
        """Extract converged positions from engine (handles Hybrid)."""
        if is_hybrid:
            return eng.molecular.X_final_
        return eng.X_final_

    # === Calibration period ===
    n_h_cal = n_calib * Hw
    X_cal_flat = X_3d[:n_calib].reshape(n_h_cal, d)
    y_zeros = np.zeros(n_h_cal, dtype=int)

    # Fused score on calibration
    eng_f = engine_cls(**fused_kwargs)
    sc_fused = eng_f.fit_score(X_cal_flat, y_zeros)
    for w in range(n_calib):
        weekly['fused'][w] = sc_fused[w*Hw:(w+1)*Hw].mean()

    # BSDT posthoc on calibration (reuse fused engine for Hybrid)
    if is_hybrid:
        X_ref = _get_X_final(eng_f)
    else:
        del eng_f; gc.collect()
        eng_p = engine_cls(**posthoc_kwargs)
        _ = eng_p.fit_score(X_cal_flat, y_zeros)
        X_ref = _get_X_final(eng_p)

    k_bsdt = min(10, max(len(X_ref) - 1, 1))
    bsdt = BSDTChannels(k=k_bsdt)
    bsdt.fit(X_ref)
    ch = bsdt.channels(X_cal_flat)
    C_cal = np.column_stack([ch['delta_C'], ch['delta_G'],
                             ch['delta_A'], ch['delta_T']])
    e_cal = bsdt.energy(X_cal_flat)

    layer_f = _MFLSFisherBSDT(); layer_f.fit(C_cal)
    sc_fisher = layer_f.score(C_cal)
    for w in range(n_calib):
        sl = slice(w*Hw, (w+1)*Hw)
        weekly['bsdt_e'][w] = e_cal[sl].mean()
        weekly['fisher'][w] = sc_fisher[sl].mean()
        weekly['quadsurf'][w] = sc_fisher[sl].mean()   # Fisher fallback
        weekly['expogate'][w] = sc_fisher[sl].mean()   # Fisher fallback
    if is_hybrid:
        del eng_f
    else:
        del eng_p
    del bsdt, layer_f; gc.collect()

    print(f"    Calib done (w=0..{n_calib-1})")

    # === Monitoring period (expanding window) ===
    for w in range(n_calib, n_weeks):
        n_h = (w + 1) * Hw
        X_up = X_3d[:w+1].reshape(n_h, d)
        y_eng = np.zeros(n_h, dtype=int)

        if is_hybrid:
            # Hybrid: single engine run, extract X_final_ from mol sub-engine
            eng_h = engine_cls(**fused_kwargs)
            sc_f = eng_h.fit_score(X_up, y_eng)
            weekly['fused'][w] = sc_f[-Hw:].mean()
            X_ref = _get_X_final(eng_h)
            del eng_h
        else:
            # -- Fused score --
            eng_f = engine_cls(**fused_kwargs)
            sc_f = eng_f.fit_score(X_up, y_eng)
            weekly['fused'][w] = sc_f[-Hw:].mean()
            del eng_f; gc.collect()

            # -- Posthoc engine run (use_fused=False) --
            eng_p = engine_cls(**posthoc_kwargs)
            _ = eng_p.fit_score(X_up, y_eng)
            X_ref = _get_X_final(eng_p)
            del eng_p
        k_bsdt = min(10, max(len(X_ref) - 1, 1))
        bsdt = BSDTChannels(k=k_bsdt)
        bsdt.fit(X_ref)

        ch = bsdt.channels(X_up)
        C = np.column_stack([ch['delta_C'], ch['delta_G'],
                             ch['delta_A'], ch['delta_T']])
        e_bs = bsdt.energy(X_up)
        weekly['bsdt_e'][w] = e_bs[-Hw:].mean()

        # Fisher (always unsupervised)
        layer_f = _MFLSFisherBSDT(); layer_f.fit(C)
        weekly['fisher'][w] = layer_f.score(C)[-Hw:].mean()

        # Build supervised labels from KNOWN past events
        # (paper protocol: crisis labels known for past quarters)
        y_ph = np.zeros(n_h, dtype=float)
        for wi in range(w + 1):
            if y_week[wi] == 1:
                y_ph[wi*Hw:(wi+1)*Hw] = 1.0
        n_crisis_pts = int(y_ph.sum())

        # QuadSurf (supervised if labels available, else Fisher)
        if n_crisis_pts > 0:
            try:
                layer_q = _MFLSQuadSurf(ridge_alpha=1.0)
                layer_q.fit(C, y_ph)
                weekly['quadsurf'][w] = layer_q.score(C)[-Hw:].mean()
            except Exception:
                weekly['quadsurf'][w] = weekly['fisher'][w]
        else:
            weekly['quadsurf'][w] = weekly['fisher'][w]

        # ExpoGate (supervised if labels available, else Fisher)
        if n_crisis_pts > 0:
            try:
                layer_e = _MFLSExpoGate(ridge_alpha=1.0,
                                        smooth_sigma=1.0, gate_scale=3.0)
                layer_e.fit(C, y_ph)
                weekly['expogate'][w] = layer_e.score(C)[-Hw:].mean()
            except Exception:
                weekly['expogate'][w] = weekly['fisher'][w]
        else:
            weekly['expogate'][w] = weekly['fisher'][w]

        del bsdt; gc.collect()

        if (w - n_calib) % 13 == 0 or w == n_weeks - 1:
            print(f"    w={w:3d}  fused={weekly['fused'][w]:.4f}  "
                  f"fisher={weekly['fisher'][w]:.4f}  "
                  f"qs={weekly['quadsurf'][w]:.4f}  "
                  f"eg={weekly['expogate'][w]:.4f}  "
                  f"n_cr={n_crisis_pts}")

    return weekly


# =====================================================================
#  Calibration Methods
# =====================================================================

def _platt_sigmoid_fit(scores, labels):
    """Fit a two-parameter sigmoid: P(y=1|s) = 1/(1+exp(A*s+B)).
    Uses Newton's method (Platt, 1999)."""
    from scipy.optimize import minimize
    s = scores.astype(float)
    y = labels.astype(float)
    n_pos = y.sum(); n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    # Target priors (Platt)
    t_pos = (n_pos + 1) / (n_pos + 2)
    t_neg = 1 / (n_neg + 2)
    t = np.where(y == 1, t_pos, t_neg)

    def loss(params):
        A, B = params
        p = 1.0 / (1.0 + np.exp(np.clip(A * s + B, -30, 30)))
        p = np.clip(p, 1e-10, 1 - 1e-10)
        return -np.sum(t * np.log(p) + (1 - t) * np.log(1 - p))

    res = minimize(loss, x0=[0.0, 0.0], method='Nelder-Mead')
    return res.x  # (A, B)


def _platt_sigmoid_predict(scores, params):
    """Apply fitted sigmoid."""
    if params is None:
        return np.full(len(scores), 0.5)
    A, B = params
    return 1.0 / (1.0 + np.exp(np.clip(A * scores + B, -30, 30)))


def _conformal_pvalue(score, calibration_scores):
    """Split conformal p-value: fraction of cal scores >= this score, +1."""
    n_cal = len(calibration_scores)
    return (np.sum(calibration_scores >= score) + 1) / (n_cal + 1)


def apply_calibrations(weekly_scores, y_week, n_calib, n_weeks):
    """Apply multiple calibration/thresholding strategies.

    Returns dict of {method_name: alarm_mask}.
    """
    cs = weekly_scores[:n_calib]
    cs_clean = cs[~np.isnan(cs)]
    mu_c = np.nanmean(cs_clean)
    sig_c = np.nanstd(cs_clean)
    med_c = np.nanmedian(cs_clean)
    mad_c = np.nanmedian(np.abs(cs_clean - med_c))
    p99_c = np.nanpercentile(cs_clean, 99) if len(cs_clean) > 0 else mu_c

    results = {}

    # ---- Fixed thresholds (from calibration) ----
    results['Fixed mu+3sig'] = weekly_scores > (mu_c + 3 * sig_c)
    results['Fixed P99'] = weekly_scores > p99_c
    results['Fixed med+3MAD'] = weekly_scores > (med_c + 3 * (mad_c + 1e-10))

    # ---- Adaptive z-scores (expanding window) ----
    z_scores = np.full(n_weeks, np.nan)
    for t in range(n_calib, n_weeks):
        past = weekly_scores[:t]
        past_v = past[~np.isnan(past)]
        if len(past_v) >= 3:
            m = past_v.mean(); s = past_v.std()
            if s > 1e-10:
                z_scores[t] = (weekly_scores[t] - m) / s

    alarm_z3 = np.zeros(n_weeks, dtype=bool)
    alarm_z2 = np.zeros(n_weeks, dtype=bool)
    for t in range(n_calib, n_weeks):
        if not np.isnan(z_scores[t]):
            alarm_z3[t] = z_scores[t] > 3.0
            alarm_z2[t] = z_scores[t] > 2.0
    results['Adaptive z>3'] = alarm_z3
    results['Adaptive z>2'] = alarm_z2

    # ---- Adaptive P99 (expanding percentile) ----
    alarm_p99 = np.zeros(n_weeks, dtype=bool)
    for t in range(n_calib, n_weeks):
        past = weekly_scores[:t]
        past_v = past[~np.isnan(past)]
        if len(past_v) >= 3:
            alarm_p99[t] = weekly_scores[t] > np.percentile(past_v, 99)
    results['Adaptive P99'] = alarm_p99

    # ---- Isotonic regression (expanding, needs >=1 event) ----
    alarm_iso = np.zeros(n_weeks, dtype=bool)
    for t in range(n_calib, n_weeks):
        past_s = weekly_scores[:t]
        past_y = y_week[:t]
        valid = ~np.isnan(past_s)
        if valid.sum() >= 4 and past_y[valid].sum() > 0 and past_y[valid].sum() < valid.sum():
            iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds='clip')
            iso.fit(past_s[valid], past_y[valid].astype(float))
            prob = iso.predict([weekly_scores[t]])[0]
            alarm_iso[t] = prob > 0.5
        else:
            # Fallback to z>2 before events available
            if not np.isnan(z_scores[t]):
                alarm_iso[t] = z_scores[t] > 2.0
    results['Isotonic'] = alarm_iso

    # ---- Platt sigmoid (expanding, needs >=1 event) ----
    alarm_platt = np.zeros(n_weeks, dtype=bool)
    for t in range(n_calib, n_weeks):
        past_s = weekly_scores[:t]
        past_y = y_week[:t]
        valid = ~np.isnan(past_s)
        if valid.sum() >= 4 and past_y[valid].sum() > 0 and past_y[valid].sum() < valid.sum():
            params = _platt_sigmoid_fit(past_s[valid], past_y[valid])
            prob = _platt_sigmoid_predict(np.array([weekly_scores[t]]), params)[0]
            alarm_platt[t] = prob > 0.5
        else:
            if not np.isnan(z_scores[t]):
                alarm_platt[t] = z_scores[t] > 2.0
    results['Platt'] = alarm_platt

    # ---- Conformal p-value (split conformal, alpha=0.05) ----
    alarm_conf = np.zeros(n_weeks, dtype=bool)
    # Split calibration into 75% train / 25% cal for conformal
    n_split = max(1, int(0.75 * n_calib))
    conf_ref = cs_clean[n_split:]  # calibration fold scores
    if len(conf_ref) >= 2:
        for t in range(n_calib, n_weeks):
            if not np.isnan(weekly_scores[t]):
                p_val = _conformal_pvalue(weekly_scores[t], conf_ref)
                alarm_conf[t] = p_val <= 0.05
    results['Conformal'] = alarm_conf

    return results


# =====================================================================
#  Evaluate
# =====================================================================

def evaluate(weekly_scores, alarm_mask, y_week, week_dates, n_calib):
    n = len(y_week)
    crisis = y_week.astype(bool)
    monitor = np.arange(n) >= n_calib
    valid = ~np.isnan(weekly_scores)

    m_valid = monitor & valid
    if m_valid.sum() >= 2 and len(np.unique(y_week[m_valid])) >= 2:
        auc = float(roc_auc_score(y_week[m_valid], weekly_scores[m_valid]))
    else:
        auc = None

    tp = int((alarm_mask & crisis & monitor).sum())
    fp = int((alarm_mask & ~crisis & monitor).sum())
    n_norm = int((~crisis & monitor).sum())
    n_cris = int((crisis & monitor).sum())
    far = 100 * fp / max(n_norm, 1)
    recall = 100 * tp / max(n_cris, 1)
    prec = 100 * tp / max(tp + fp, 1)

    events = {}
    for evt_name, onset_ts in EVENT_ONSETS.items():
        onset_arr = np.where(week_dates >= onset_ts)[0]
        if len(onset_arr) == 0:
            events[evt_name] = "--"
            continue
        onset_w = int(onset_arr[0])
        # Look for pre-event alarms (up to 20 weeks before onset)
        pre = [w for w in range(max(n_calib, onset_w - 20), onset_w)
               if alarm_mask[w]]
        if pre:
            events[evt_name] = f"{onset_w - pre[0]}w"
        else:
            # Concurrent detection (within 4 weeks of onset)
            ea = [w for w in range(onset_w, min(onset_w + 4, n))
                  if alarm_mask[w]]
            events[evt_name] = "conc" if ea else "--"

    return {'auc': auc, 'far': round(far, 1), 'recall': round(recall, 1),
            'prec': round(prec, 1), 'events': events}


# =====================================================================
#  Main
# =====================================================================

def main():
    print('=' * 90)
    print('  PAPER-COMPLIANT ERCOT BENCHMARK')
    print('  Protocol: expanding window | BSDTChannels on X_final_ | MFLS corrections')
    print('  Variants: Fused | BSDT-E | Fisher | QuadSurf | ExpoGate')
    print('  Calibration: Fixed mu+3sig | P99 | med+3MAD | Adaptive z>3/z>2/P99 |')
    print('               Isotonic | Platt | Conformal')
    print('=' * 90)

    X_3d, X_flat, week_dates, y_week, week_labels, n_calib = load_ercot()
    n_weeks = len(y_week)
    n_events = int(y_week[n_calib:].sum())
    print(f"  Data: {n_weeks} weeks, calib={n_calib}, monitor={n_weeks-n_calib}")
    print(f"  Events in monitor: {n_events} event-weeks")
    print(f"  Calib: {week_dates[0].date()} -> {week_dates[n_calib-1].date()}")
    print(f"  Monitor: {week_dates[n_calib].date()} -> {week_dates[-1].date()}\n")

    engines = {
        "Molecular": (MolecularEngine, dict(
            iterations=80, k_neighbors=10, max_samples=3000,
            use_bsdt_damping=True)),
        "Gravity": (GravityModeEngine, dict(
            iterations=60, k_neighbors=10)),
        "Hybrid": (HybridGravityEngine, dict()),
    }

    # == Phase A: Scores (cached) ==
    if CACHE.exists():
        print(f"  Loading cached scores from {CACHE.name}")
        with open(CACHE) as f:
            cached = json.load(f)
        all_weekly = {}
        for eng_name in engines:
            if eng_name in cached:
                all_weekly[eng_name] = {
                    v: np.array(s) for v, s in cached[eng_name].items()
                }
    else:
        print(f"  Running expanding-window engine fits (this takes hours)...")
        all_weekly = {}
        for eng_name, (eng_cls, eng_kwargs) in engines.items():
            print(f"\n  == Engine: {eng_name} ==")
            t0 = time.time()
            weekly = expanding_window_all_variants(
                X_3d, X_flat, y_week, eng_cls, eng_kwargs, n_calib, eng_name)
            elapsed = time.time() - t0
            all_weekly[eng_name] = weekly
            print(f"  {eng_name} done in {elapsed:.0f}s")

        # Save cache
        cache_data = {}
        for eng_name, wk in all_weekly.items():
            cache_data[eng_name] = {v: s.tolist() for v, s in wk.items()}
        os.makedirs(ROOT / "results", exist_ok=True)
        with open(CACHE, 'w') as f:
            json.dump(cache_data, f, indent=2)
        print(f"\n  Cached -> {CACHE}")

    # == Phase B: Apply calibrations (fast) ==
    scoring_variants = ['fused', 'bsdt_e', 'fisher', 'quadsurf', 'expogate']
    cal_methods = ['Fixed mu+3sig', 'Fixed P99', 'Fixed med+3MAD',
                   'Adaptive z>3', 'Adaptive z>2', 'Adaptive P99',
                   'Isotonic', 'Platt', 'Conformal']

    all_results = {}
    for eng_name in engines:
        eng_r = {}
        for var in scoring_variants:
            ws = all_weekly[eng_name][var]
            eng_r[var] = {}
            alarm_map = apply_calibrations(ws, y_week, n_calib, n_weeks)
            for cal_name in cal_methods:
                alarm = alarm_map[cal_name]
                eng_r[var][cal_name] = evaluate(
                    ws, alarm, y_week, week_dates, n_calib)
        all_results[eng_name] = eng_r

    # =================================================================
    #  Print Results
    # =================================================================

    # == Table 1: AUC comparison (engine x variant) ==
    print(f"\n{'='*90}")
    print(f"  TABLE 1: AUC COMPARISON (engine x variant)")
    print(f"  AUC is threshold-independent; shown for quick ranking")
    print(f"{'='*90}")
    print(f"  {'Engine':<12} {'Variant':<12} {'AUC':>7}")
    print(f"  {'-'*35}")
    for eng_name in engines:
        for var in scoring_variants:
            r0 = all_results[eng_name][var]
            auc = list(r0.values())[0]['auc']
            auc_s = f"{auc:.4f}" if auc else "N/A"
            print(f"  {eng_name:<12} {var:<12} {auc_s:>7}")
        print()

    # == Table 2: Full grid (engine x variant x calibration) ==
    print(f"\n{'='*90}")
    print(f"  TABLE 2: FULL GRID (engine x variant x calibration)")
    print(f"{'='*90}")

    for eng_name in engines:
        eng_r = all_results[eng_name]
        print(f"\n  == {eng_name} ==")

        for var in scoring_variants:
            print(f"\n    -- {var} --")
            print(f"    {'Calibration':<18} {'AUC':>6} {'FAR%':>6} {'Rec%':>6} "
                  f"{'Prec%':>6}  {'Summer':>7} {'COVID':>7} {'Uri':>7} {'Elliott':>8}")
            print(f"    {'-'*82}")

            for cal_name in cal_methods:
                r = eng_r[var].get(cal_name)
                if r is None:
                    continue
                auc_s = f"{r['auc']:.4f}" if r['auc'] else "  N/A"
                ev = r['events']
                print(f"    {cal_name:<18} {auc_s:>6} {r['far']:>6.1f} "
                      f"{r['recall']:>6.1f} {r['prec']:>6.1f}"
                      f"  {ev.get('SummerPeak2019','--'):>7} "
                      f"{ev.get('COVID_Collapse','--'):>7} "
                      f"{ev.get('WinterStormUri','--'):>7} "
                      f"{ev.get('WinterStormElliott','--'):>8}")

    # == Table 3: Best per event ==
    print(f"\n{'='*90}")
    print(f"  TABLE 3: BEST PER EVENT (early detection + low FAR)")
    print(f"{'='*90}")

    for evt_name in EVENT_ONSETS:
        print(f"\n  {evt_name}:")
        cands = []
        for eng_name in engines:
            for var in scoring_variants:
                for cal_name in cal_methods:
                    r = all_results[eng_name][var].get(cal_name)
                    if r is None:
                        continue
                    e = r['events'].get(evt_name, "--")
                    if e not in ("--", "conc"):
                        cands.append({
                            'eng': eng_name, 'var': var, 'cal': cal_name,
                            'lead': e, 'far': r['far'], 'auc': r['auc'],
                            'recall': r['recall'], 'prec': r['prec']})
        cands.sort(key=lambda x: (x['far'], -int(x['lead'].replace('w',''))))
        for i, c in enumerate(cands[:8]):
            auc_s = f"{c['auc']:.4f}" if c['auc'] else 'N/A'
            print(f"    {i+1}. {c['eng']}/{c['var']:<10} {c['cal']:<18}"
                  f" lead={c['lead']:>4}  FAR={c['far']:.1f}%  AUC={auc_s}")
        if not cands:
            print(f"    Not detected by any variant.")

    # == Table 4: Overall ranking ==
    print(f"\n{'='*90}")
    print(f"  TABLE 4: OVERALL RANKING (most events, lowest FAR)")
    print(f"{'='*90}")

    overall = []
    for eng_name in engines:
        for var in scoring_variants:
            for cal_name in cal_methods:
                r = all_results[eng_name][var].get(cal_name)
                if r is None:
                    continue
                n_det = sum(1 for e in r['events'].values()
                            if e not in ("--", "conc"))
                lead_sum = sum(int(e.replace('w', ''))
                               for e in r['events'].values()
                               if e not in ("--", "conc"))
                if n_det > 0:
                    overall.append({
                        'eng': eng_name, 'var': var, 'cal': cal_name,
                        'n_ev': n_det, 'lead': lead_sum,
                        'far': r['far'], 'auc': r['auc'],
                        'recall': r['recall'], 'prec': r['prec'],
                        'events': r['events']})
    overall.sort(key=lambda x: (-x['n_ev'], x['far'], -x['lead']))

    print(f"\n  {'#':<3} {'Engine/Variant':<25} {'Calibration':<18} "
          f"{'Ev':>3} {'Lead':>5} {'FAR%':>6} {'AUC':>7}  Events")
    print(f"  {'-'*95}")
    for i, c in enumerate(overall[:20]):
        auc_s = f"{c['auc']:.4f}" if c['auc'] else 'N/A'
        evs = ' '.join(f"{k}={v}" for k, v in c['events'].items()
                       if v not in ("--", "conc"))
        tag = f"{c['eng']}/{c['var']}"
        print(f"  {i+1:<3} {tag:<25} {c['cal']:<18} "
              f"{c['n_ev']:>3} {c['lead']:>4}w {c['far']:>5.1f}% {auc_s:>7}  {evs}")

    # == Save JSON results ==
    json_out = {}
    for eng_name in engines:
        json_out[eng_name] = {}
        for var in scoring_variants:
            json_out[eng_name][var] = {}
            for cal_name in cal_methods:
                r = all_results[eng_name][var].get(cal_name)
                if r:
                    json_out[eng_name][var][cal_name] = r

    results_path = ROOT / "results" / "ercot_paper_compliant_results.json"
    with open(results_path, 'w') as f:
        json.dump(json_out, f, indent=2, default=str)
    print(f"\n  Results saved -> {results_path}")


if __name__ == '__main__':
    main()
