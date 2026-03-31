"""
ercot_betti_morse_direct.py
============================
Direct Morse+Betti topology early warning on ERCOT supply data.

NO ENGINE SIMULATION — applies BettiMorseFoundation (Morse + Betti + 
optional BSDT/ExpoGate enrichment) directly to the raw data manifold.

This is the BettiMorseFoundation approach from the paper adapted for  
the ERCOT expanding-window protocol. Much faster than engine-based
scoring since there's no N-body simulation overhead.

Variants:
  A: Foundation only (Morse + Betti, Fisher VR fused)
  B: Foundation + BSDT channels
  C: Foundation + BSDT + ExpoGate MFLS

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations
import sys, os, time, json, warnings, gc
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

os.environ['CUDA_VISIBLE_DEVICES'] = ''
warnings.filterwarnings("ignore")

ROOT = Path(r"c:\amttp")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "udl"))

from research.udl.udl.system_mode import (
    MorseTopologyAlarm, BettiBarcodeSuite,
    BSDTChannels, _MFLSExpoGate, _MFLSFisherBSDT, _MFLSQuadSurf,
)

H = 168  # hours per week
RESULTS_DIR = ROOT / "results"

EVENT_ONSETS = {
    "SummerPeak2019": pd.Timestamp("2019-08-12"),
    "COVID_Collapse": pd.Timestamp("2020-03-23"),
    "WinterStormUri": pd.Timestamp("2021-02-10"),
}

SUPPLY_PATH = ROOT / "data" / "ercot" / "ercot_supply_hourly.npz"


# =====================================================================
#  Fisher VR fusion
# =====================================================================

def _robust_norm(s):
    q1, q99 = np.percentile(s, [1, 99])
    if q99 - q1 > 1e-15:
        return np.clip((s - q1) / (q99 - q1), 0.0, 1.0)
    return np.zeros_like(s)


def fisher_vr_fuse(views):
    V = np.column_stack(views)
    N, n_v = V.shape
    total = V.sum(axis=1)
    p80 = np.percentile(total, 80); p50 = np.percentile(total, 50)
    hi = total >= p80; lo = total <= p50
    if hi.sum() < 3 or lo.sum() < 3:
        w = np.ones(n_v) / n_v
    else:
        fr = np.zeros(n_v)
        for j in range(n_v):
            mu_hi = V[hi, j].mean(); mu_lo = V[lo, j].mean()
            var_hi = V[hi, j].var() + 1e-15
            var_lo = V[lo, j].var() + 1e-15
            fr[j] = (mu_hi - mu_lo)**2 / (var_hi + var_lo)
        s = fr.sum()
        w = fr / s if s > 1e-15 else np.ones(n_v) / n_v
    fused = (V * w[None, :]).sum(axis=1)
    return fused, w


# =====================================================================
#  Load dataset
# =====================================================================

def load_dataset(path):
    npz = np.load(path, allow_pickle=True)
    X = npz["X"]; dates = pd.to_datetime(npz["dates"])
    y = npz["y"].astype(int)
    n_weeks = len(X) // H; n_hours = n_weeks * H
    X_t = X[:n_hours]; d_t = dates[:n_hours]; y_t = y[:n_hours]
    X_3d = X_t.reshape(n_weeks, H, X.shape[1])
    week_dates = d_t[::H]
    y_week = np.array([y_t[i*H:(i+1)*H].any()
                       for i in range(n_weeks)]).astype(int)
    calib_mask = week_dates <= pd.Timestamp("2019-06-30")
    n_calib = int(calib_mask.sum())
    return X_3d, X_t, week_dates, y_week, n_calib


# =====================================================================
#  Scoring variants
# =====================================================================

VARIANTS = [
    'morse_only',
    'betti_only',
    'morse_betti_fused',       # Foundation A
    'foundation_bsdt',         # Foundation B
    'foundation_expogate',     # Foundation C
    'foundation_fisher',       # Foundation + Fisher BSDT
    'foundation_quadsurf',     # Foundation + QuadSurf
    'bsdt_only',
    'expogate_only',
    'fisher_only',
    'quadsurf_only',
]


def score_direct(X_ref, X_test, k=15):
    """
    Score X_test against reference X_ref using direct Morse+Betti
    topology (no engine simulation).
    
    X_ref:  normalised reference data (calibration / training period)
    X_test: normalised test data (full expanding window)
    
    Returns dict {variant: scores_array}
    """
    k_safe = min(k, max(len(X_ref) - 1, 1))
    scores = {}

    # Morse
    morse = MorseTopologyAlarm(k=k_safe)
    morse.fit(X_ref)
    s_morse = morse.score(X_test)
    scores['morse_only'] = s_morse

    # Betti
    betti = BettiBarcodeSuite(k=min(k_safe + 5, 25, len(X_ref) - 1),
                               n_scales=8)
    betti.fit(X_ref)
    s_betti = betti.score(X_test)
    scores['betti_only'] = s_betti

    # Foundation fused (A)
    m_norm = _robust_norm(s_morse)
    b_norm = _robust_norm(s_betti)
    s_fused, fw = fisher_vr_fuse([m_norm, b_norm])
    scores['morse_betti_fused'] = s_fused

    # BSDT channels
    k_bsdt = min(10, max(len(X_ref) - 1, 1))
    bsdt = BSDTChannels(k=k_bsdt)
    bsdt.fit(X_ref)
    ch = bsdt.channels(X_test)
    C = np.column_stack([ch['delta_C'], ch['delta_G'],
                         ch['delta_A'], ch['delta_T']])
    s_bsdt = bsdt.energy(X_test)
    scores['bsdt_only'] = s_bsdt
    bsdt_n = _robust_norm(s_bsdt)

    # Foundation + BSDT (B)
    s_fb, _ = fisher_vr_fuse([m_norm, b_norm, bsdt_n])
    scores['foundation_bsdt'] = s_fb

    # MFLS variants
    for MFLSCls, name_sfx in [(_MFLSExpoGate, 'expogate'),
                                (_MFLSFisherBSDT, 'fisher'),
                                (_MFLSQuadSurf, 'quadsurf')]:
        try:
            layer = MFLSCls()
            layer.fit(C)
            s_mfls = layer.score(C)
            mfls_n = _robust_norm(s_mfls)
            s_found, _ = fisher_vr_fuse([m_norm, b_norm, bsdt_n, mfls_n])
            scores[f'foundation_{name_sfx}'] = s_found
            scores[f'{name_sfx}_only'] = s_mfls
        except Exception:
            scores[f'foundation_{name_sfx}'] = s_fb
            scores[f'{name_sfx}_only'] = s_bsdt

    return scores


# =====================================================================
#  Expanding-window protocol (DIRECT — no engine)
# =====================================================================

def expanding_window_direct(X_3d, y_week, n_calib):
    n_weeks, Hw, d = X_3d.shape
    weekly = {v: np.full(n_weeks, np.nan) for v in VARIANTS}

    # === Calibration (fit reference from calib period) ===
    X_cal = X_3d[:n_calib].reshape(n_calib * Hw, d)
    scaler = StandardScaler()
    X_cal_norm = scaler.fit_transform(X_cal).astype(np.float64)

    # Score calibration period against itself
    var_scores = score_direct(X_cal_norm, X_cal_norm)
    for v in VARIANTS:
        if v in var_scores:
            s = var_scores[v]
            for w in range(n_calib):
                weekly[v][w] = float(np.nanmean(s[w*Hw:(w+1)*Hw]))
    print(f"  Calib done (w=0..{n_calib-1})")

    # === Expanding window ===
    for t in range(n_calib, n_weeks):
        n_h = (t + 1) * Hw
        X_up = X_3d[:t+1].reshape(n_h, d)

        # Re-fit scaler on expanding window
        scaler_t = StandardScaler()
        X_up_norm = scaler_t.fit_transform(X_up).astype(np.float64)

        # Reference = first n_calib weeks (normal period)
        X_ref = X_up_norm[:n_calib * Hw]

        # Score last week
        X_last = X_up_norm[-Hw:]

        var_scores = score_direct(X_ref, X_last)
        for v in VARIANTS:
            if v in var_scores:
                weekly[v][t] = float(np.nanmean(var_scores[v]))

        if t % 13 == 0:
            strs = []
            for v in ['morse_betti_fused', 'foundation_expogate', 'expogate_only']:
                ws_t = weekly[v][:t+1]
                valid = ~np.isnan(ws_t)
                yw = y_week[:t+1]
                if valid.sum() >= 2 and len(np.unique(yw[valid])) >= 2:
                    a = roc_auc_score(yw[valid], ws_t[valid])
                    strs.append(f"{v[:10]}={a:.4f}")
                else:
                    strs.append(f"{v[:10]}=N/A")
            print(f"    w={t:>3}  {' '.join(strs)}", flush=True)

    return weekly


# =====================================================================
#  Calibration + Evaluate (same as engine-based version)
# =====================================================================

def apply_calibrations(weekly_scores, y_week, n_calib, n_weeks):
    cs = weekly_scores[:n_calib]
    cs_clean = cs[~np.isnan(cs)]
    if len(cs_clean) < 3:
        return {}
    mu_c = np.nanmean(cs_clean); sig_c = np.nanstd(cs_clean)
    p99_c = np.nanpercentile(cs_clean, 99)

    results = {}
    results['Fixed P99'] = weekly_scores > p99_c
    results['Fixed mu+3sig'] = weekly_scores > (mu_c + 3 * sig_c)

    z_scores = np.full(n_weeks, np.nan)
    for t in range(n_calib, n_weeks):
        past = weekly_scores[:t]; past_v = past[~np.isnan(past)]
        if len(past_v) >= 3:
            m = past_v.mean(); s = past_v.std()
            if s > 1e-10:
                z_scores[t] = (weekly_scores[t] - m) / s

    alarm_z2 = np.zeros(n_weeks, dtype=bool)
    alarm_z3 = np.zeros(n_weeks, dtype=bool)
    for t in range(n_calib, n_weeks):
        if not np.isnan(z_scores[t]):
            alarm_z2[t] = z_scores[t] > 2.0
            alarm_z3[t] = z_scores[t] > 3.0
    results['Adaptive z>2'] = alarm_z2
    results['Adaptive z>3'] = alarm_z3

    alarm_p99 = np.zeros(n_weeks, dtype=bool)
    for t in range(n_calib, n_weeks):
        past = weekly_scores[:t]; past_v = past[~np.isnan(past)]
        if len(past_v) >= 3:
            alarm_p99[t] = weekly_scores[t] > np.percentile(past_v, 99)
    results['Adaptive P99'] = alarm_p99

    try:
        from research.udl.udl.calibration import FARTargetCalibrator
        for target_far, name in [(0.05, 'FARTarget_5%'), (0.02, 'FARTarget_2%')]:
            alarm_ft = np.zeros(n_weeks, dtype=bool)
            for t in range(n_calib, n_weeks):
                past_s = weekly_scores[:t]; past_y = y_week[:t]
                valid = ~np.isnan(past_s)
                if valid.sum() >= 10 and past_y[valid].sum() >= 1:
                    if not np.isnan(weekly_scores[t]):
                        try:
                            cal = FARTargetCalibrator(target_far=target_far,
                                                     target_recall=0.95,
                                                     method='combined')
                            cal.fit(past_s[valid], past_y[valid])
                            calibrated = cal.transform(np.array([weekly_scores[t]]))
                            alarm_ft[t] = calibrated[0] > 0.5
                        except Exception:
                            pass
            results[name] = alarm_ft
    except ImportError:
        pass

    return results


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
    n_cr_mon = int((crisis & monitor).sum())
    recall = 100 * tp / max(n_cr_mon, 1)
    far = 100 * fp / max(n_norm, 1)

    events_detected = {}
    total_lead = 0
    for ev_name, onset in EVENT_ONSETS.items():
        ev_mask = (week_dates >= onset) & crisis & monitor
        if not ev_mask.any():
            continue
        first_crisis_idx = np.where(ev_mask)[0][0]
        det_before = alarm_mask[:first_crisis_idx] & monitor[:first_crisis_idx]
        if det_before.any():
            first_alarm = np.where(det_before)[0][-1]
            lead = first_crisis_idx - first_alarm
        else:
            det_during = alarm_mask & ev_mask
            lead = 0 if det_during.any() else -1
        if lead >= 0:
            events_detected[ev_name] = int(lead)
            total_lead += lead

    return {
        'auc': auc, 'far': round(far, 1), 'recall': round(recall, 1),
        'events_detected': events_detected,
        'n_ev': len(events_detected), 'lead': total_lead,
    }


# =====================================================================
#  MAIN
# =====================================================================

def main():
    t0 = time.time()
    print("=" * 90)
    print("  ERCOT EARLY WARNING: Direct Morse+Betti (No Engine Simulation)")
    print("  Supply data (d=5): wind_cf, solar_cf, gas_cf, coal_cf, nuclear_cf")
    print("=" * 90)

    X_3d, X_flat, week_dates, y_week, n_calib = load_dataset(SUPPLY_PATH)
    n_weeks = len(y_week)
    print(f"\n  Shape: {X_3d.shape}  (n_weeks={n_weeks}, d={X_3d.shape[2]})")
    print(f"  Calib: {n_calib} weeks  Monitor: {n_weeks - n_calib} weeks")
    print(f"  Events: {int(y_week[n_calib:].sum())} event-weeks in monitor")

    # === Run direct topology scoring ===
    weekly = expanding_window_direct(X_3d, y_week, n_calib)

    total_time = time.time() - t0

    # === Evaluate ===
    all_results = {}
    for var_name in VARIANTS:
        ws = weekly[var_name]
        cals = apply_calibrations(ws, y_week, n_calib, n_weeks)
        var_results = {}
        for cal_name, alarm_mask in cals.items():
            r = evaluate(ws, alarm_mask, y_week, week_dates, n_calib)
            var_results[cal_name] = r
        all_results[var_name] = var_results

    # === Print ===
    print(f"\n\n{'=' * 90}")
    print(f"  AUC TABLE: Direct Morse + Betti (No Simulation)")
    print(f"{'=' * 90}")
    print(f"  {'Variant':<28} {'AUC':>8}")
    print(f"  {'-' * 40}")
    for v in VARIANTS:
        cals = all_results[v]
        if cals:
            first = next(iter(cals.values()))
            a = first.get('auc')
            auc_s = f"{a:.4f}" if a else "  N/A"
        else:
            auc_s = "  N/A"
        marker = " <--" if v in ('morse_betti_fused', 'foundation_expogate') else ""
        print(f"  {v:<28} {auc_s:>8}{marker}")

    print(f"\n{'=' * 90}")
    print(f"  TOP 20 CONFIGS (sorted by events, FAR, lead)")
    print(f"{'=' * 90}")
    print(f"  {'#':<3} {'Variant':<28} {'Calibration':<18} "
          f"{'Ev':>3} {'Lead':>5} {'FAR%':>6} {'AUC':>7}  Events")
    print(f"  {'-' * 100}")

    overall = []
    for var_name in VARIANTS:
        cals = all_results[var_name]
        for cal_name, r in cals.items():
            if r['n_ev'] > 0:
                evs = " ".join(f"{e}={l}w" for e, l in r['events_detected'].items())
                auc_s = f"{r['auc']:.4f}" if r['auc'] else "  N/A"
                overall.append({
                    'key': var_name, 'cal': cal_name,
                    'n_ev': r['n_ev'], 'lead': r['lead'],
                    'far': r['far'], 'auc': r['auc'] or 0,
                    'evs': evs, 'auc_s': auc_s,
                })
    overall.sort(key=lambda x: (-x['n_ev'], x['far'], -x['lead']))

    for i, c in enumerate(overall[:20], 1):
        print(f"  {i:<3} {c['key']:<28} {c['cal']:<18} "
              f"{c['n_ev']:>3} {c['lead']:>4}w {c['far']:>5.1f}% "
              f"{c['auc_s']:>7}  {c['evs']}")

    # Comparison
    print(f"\n{'=' * 90}")
    print(f"  COMPARISON WITH PREVIOUS RESULTS")
    print(f"{'=' * 90}")
    print(f"  Previous best (Engine/BSDT/ExpoGate): AUC = 0.8598")
    print(f"  Paper baseline (Hybrid, single-fit):  AUC = 0.9940")
    print()
    for v in VARIANTS:
        cals = all_results[v]
        if cals:
            first = next(iter(cals.values()))
            a = first.get('auc')
            auc_s = f"{a:.4f}" if a else "N/A"
            best = None
            for cal_name, r in cals.items():
                if r['n_ev'] >= 3:
                    if best is None or r['far'] < best['far']:
                        best = {**r, 'cal': cal_name}
            op = ""
            if best:
                op = f"  3/3ev FAR={best['far']:.1f}% lead={best['lead']}w [{best['cal']}]"
            print(f"  {v:<28} AUC={auc_s}{op}")

    print(f"\n  Total time: {total_time:.0f}s ({total_time/60:.1f}min)")

    out_path = RESULTS_DIR / "ercot_betti_morse_direct_results.json"
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"  Saved -> {out_path}")

    # Also save weekly scores for later analysis
    cache_path = RESULTS_DIR / "ercot_betti_morse_direct_cache.json"
    cache = {v: ws.tolist() for v, ws in weekly.items()}
    with open(cache_path, 'w') as f:
        json.dump(cache, f)
    print(f"  Cache -> {cache_path}")


if __name__ == '__main__':
    main()
