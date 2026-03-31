"""
ercot_betti_morse_alarm.py
===========================
Early Warning System using Morse Topology + Betti Barcode Suite
on ERCOT supply-side data.

The paper's early warning alarm comes from the foundational
Morse + Betti topology layer — NOT just BSDT channel scores.

Architecture:
  1. Engine (Molecular/Gravity/Hybrid) runs physics simulation
     → produces X_final_ (post-simulation positions)
  2. MorseTopologyAlarm scores X_final_ (4 structural features)
  3. BettiBarcodeSuite scores X_final_ (19 topology features)  
  4. Fisher VR fusion → foundation alarm score
  5. Optionally: BSDT channels as enrichment layer on top

This runs the expanding-window protocol on the supply dataset,
using cached engine positions where possible, otherwise re-fitting.

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
    MolecularEngine, GravityModeEngine, HybridGravityEngine,
    MorseTopologyAlarm, BettiBarcodeSuite,
    BSDTChannels, FusedSystemScorer,
    _MFLSFisherBSDT, _MFLSQuadSurf, _MFLSExpoGate,
)

H = 168  # hours per week
RESULTS_DIR = ROOT / "results"

EVENT_ONSETS = {
    "SummerPeak2019":     pd.Timestamp("2019-08-12"),
    "COVID_Collapse":     pd.Timestamp("2020-03-23"),
    "WinterStormUri":     pd.Timestamp("2021-02-10"),
}

SUPPLY_PATH = ROOT / "data" / "ercot" / "ercot_supply_hourly.npz"

ENGINES = {
    "Molecular": (MolecularEngine, dict(
        iterations=80, k_neighbors=10, max_samples=3000,
        use_bsdt_damping=True)),
    "Gravity": (GravityModeEngine, dict(
        iterations=60, k_neighbors=10)),
    "Hybrid": (HybridGravityEngine, dict(
        iterations=60, k_neighbors=10)),
}


# =====================================================================
#  Fisher VR fusion (same as paper)
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
    p80 = np.percentile(total, 80)
    p50 = np.percentile(total, 50)
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
    y = npz["y"].astype(int); labels = npz["labels"]

    n_weeks = len(X) // H; n_hours = n_weeks * H
    X_t = X[:n_hours]; d_t = dates[:n_hours]; y_t = y[:n_hours]
    lb_t = labels[:n_hours]

    X_3d = X_t.reshape(n_weeks, H, X.shape[1])
    week_dates = d_t[::H]
    y_week = np.array([y_t[i*H:(i+1)*H].any()
                       for i in range(n_weeks)]).astype(int)

    calib_mask = week_dates <= pd.Timestamp("2019-06-30")
    n_calib = int(calib_mask.sum())
    return X_3d, X_t, week_dates, y_week, n_calib


# =====================================================================
#  Scoring variants using Morse + Betti foundation
# =====================================================================

SCORING_VARIANTS = [
    'morse_only',          # Pure Morse topology alarm
    'betti_only',          # Pure Betti barcode suite
    'morse_betti_fused',   # Fisher VR fusion of Morse + Betti
    'foundation_bsdt',     # Morse + Betti + BSDT enrichment
    'foundation_full',     # Morse + Betti + BSDT + MFLS(ExpoGate)
    'bsdt_only',           # BSDT alone (for comparison)
    'expogate_only',       # ExpoGate MFLS alone (prev best)
]


def score_topology_variants(X_final, X_test_norm, k=10):
    """
    Score X_test_norm using Morse/Betti topology learned from X_final_.
    
    X_final:     post-simulation positions (~3000 subsampled points)
    X_test_norm: normalised test data to score (e.g., last week = 168 pts)
    
    Architecture:
      - Morse/Betti/BSDT: fitted on X_final_, score X_test_norm
      - ExpoGate: fitted on BSDT channels of X_final_, score test channels
    
    Returns dict {variant_name: score_array_of_len_N}.
    """
    X_ref = X_final  # all "normal" in our protocol (y = all zeros)
    k_safe = min(k, max(len(X_ref) - 1, 1))
    
    scores = {}
    
    # --- Morse Topology Alarm ---
    morse = MorseTopologyAlarm(k=k_safe)
    morse.fit(X_ref)
    s_morse = morse.score(X_test_norm)
    scores['morse_only'] = s_morse
    
    # --- Betti Barcode Suite ---
    betti = BettiBarcodeSuite(k=min(k_safe + 5, 25, len(X_ref) - 1), n_scales=8)
    betti.fit(X_ref)
    s_betti = betti.score(X_test_norm)
    scores['betti_only'] = s_betti
    
    # --- Morse + Betti Fisher VR fusion ---
    m_norm = _robust_norm(s_morse)
    b_norm = _robust_norm(s_betti)
    s_fused, fw = fisher_vr_fuse([m_norm, b_norm])
    scores['morse_betti_fused'] = s_fused
    
    # --- BSDT channels ---
    k_bsdt = min(10, max(len(X_ref) - 1, 1))
    bsdt = BSDTChannels(k=k_bsdt)
    bsdt.fit(X_ref)
    
    # Channels on X_final_ for ExpoGate training
    ch_ref = bsdt.channels(X_ref)
    C_ref = np.column_stack([ch_ref['delta_C'], ch_ref['delta_G'],
                             ch_ref['delta_A'], ch_ref['delta_T']])
    
    # Channels on test data for scoring
    ch_test = bsdt.channels(X_test_norm)
    C_test = np.column_stack([ch_test['delta_C'], ch_test['delta_G'],
                              ch_test['delta_A'], ch_test['delta_T']])
    s_bsdt = bsdt.energy(X_test_norm)
    scores['bsdt_only'] = s_bsdt
    
    # --- Foundation + BSDT enrichment ---
    bsdt_norm = _robust_norm(s_bsdt)
    s_foundation_bsdt, _ = fisher_vr_fuse([m_norm, b_norm, bsdt_norm])
    scores['foundation_bsdt'] = s_foundation_bsdt
    
    # --- ExpoGate: fit on reference channels, score test channels ---
    try:
        eg = _MFLSExpoGate()
        eg.fit(C_ref)                # fit on ~3000 reference channels
        s_eg = eg.score(C_test)      # score test channels
        eg_norm = _robust_norm(s_eg)
        s_full, _ = fisher_vr_fuse([m_norm, b_norm, bsdt_norm, eg_norm])
        scores['foundation_full'] = s_full
        scores['expogate_only'] = s_eg
    except Exception:
        scores['foundation_full'] = s_foundation_bsdt
        scores['expogate_only'] = s_bsdt
    
    return scores


# =====================================================================
#  Expanding-window engine fit + topology scoring
# =====================================================================

SCORE_WINDOW = 4  # score last N weeks per step (bounded context)

def expanding_window_betti_morse(X_3d, X_flat, y_week, engine_cls,
                                  engine_kwargs, n_calib, eng_name):
    n_weeks, Hw, d = X_3d.shape
    weekly = {v: np.full(n_weeks, np.nan) for v in SCORING_VARIANTS}

    is_hybrid = (engine_cls == HybridGravityEngine)

    # For non-Hybrid: use_fused=False to get clean Morse alarm from engine
    if is_hybrid:
        kwargs = {**engine_kwargs}
    else:
        kwargs = {**engine_kwargs, 'use_fused': False}

    def _get_X_final(eng):
        if is_hybrid and hasattr(eng, 'molecular'):
            return eng.molecular.X_final_
        return eng.X_final_

    # === Calibration period ===
    n_h_cal = n_calib * Hw
    X_cal_flat = X_3d[:n_calib].reshape(n_h_cal, d)
    y_zeros = np.zeros(n_h_cal, dtype=int)

    eng = engine_cls(**kwargs)
    _ = eng.fit_score(X_cal_flat, y_zeros)

    # Normalise full calib data using engine's scaler
    if eng.scaler_ is not None:
        X_cal_norm = eng.scaler_.transform(X_cal_flat).astype(np.float64)
    else:
        X_cal_norm = X_cal_flat.astype(np.float64)

    X_ref = _get_X_final(eng)
    # Score last SCORE_WINDOW weeks of calibration
    sw = min(SCORE_WINDOW, n_calib)
    X_test_cal = X_cal_norm[-(sw*Hw):]
    var_scores = score_topology_variants(X_ref, X_test_cal)
    for v in SCORING_VARIANTS:
        if v in var_scores:
            s = var_scores[v]
            for w_off in range(sw):
                w_idx = n_calib - sw + w_off
                weekly[v][w_idx] = float(np.nanmean(s[w_off*Hw:(w_off+1)*Hw]))

    del eng; gc.collect()
    print(f"    Calib done (w=0..{n_calib-1})")

    # === Expanding window ===
    for t in range(n_calib, n_weeks):
        n_h = (t + 1) * Hw
        X_up = X_3d[:t+1].reshape(n_h, d)
        y_eng = np.zeros(n_h, dtype=int)

        eng = engine_cls(**kwargs)
        _ = eng.fit_score(X_up, y_eng)

        # Score bounded recent window (last SCORE_WINDOW weeks)
        sw = min(SCORE_WINDOW, t + 1)
        X_recent = X_3d[t+1-sw:t+1].reshape(sw * Hw, d)
        if eng.scaler_ is not None:
            X_recent_norm = eng.scaler_.transform(X_recent).astype(np.float64)
        else:
            X_recent_norm = X_recent.astype(np.float64)

        X_ref = _get_X_final(eng)
        var_scores = score_topology_variants(X_ref, X_recent_norm)
        for v in SCORING_VARIANTS:
            if v in var_scores:
                s = var_scores[v]
                # Last week's mean
                weekly[v][t] = float(np.nanmean(s[-Hw:]))

        if t % 13 == 0:
            auc_strs = []
            for v in ['morse_betti_fused', 'foundation_full', 'expogate_only']:
                ws_t = weekly[v][:t+1]
                valid = ~np.isnan(ws_t)
                yw = y_week[:t+1]
                if valid.sum() >= 2 and len(np.unique(yw[valid])) >= 2:
                    a = roc_auc_score(yw[valid], ws_t[valid])
                    auc_strs.append(f"{v[:8]}={a:.4f}")
                else:
                    auc_strs.append(f"{v[:8]}=N/A")
            print(f"    w={t:>3}  {' '.join(auc_strs)}", flush=True)

        del eng; gc.collect()

    return weekly


# =====================================================================
#  Calibration + Evaluate
# =====================================================================

def apply_calibrations(weekly_scores, y_week, n_calib, n_weeks):
    """Fixed + Adaptive + Isotonic calibrations."""
    from sklearn.isotonic import IsotonicRegression

    cs = weekly_scores[:n_calib]
    cs_clean = cs[~np.isnan(cs)]
    if len(cs_clean) < 3:
        return {}
    mu_c = np.nanmean(cs_clean); sig_c = np.nanstd(cs_clean)
    med_c = np.nanmedian(cs_clean)
    mad_c = np.nanmedian(np.abs(cs_clean - med_c))
    p99_c = np.nanpercentile(cs_clean, 99)

    results = {}
    results['Fixed P99'] = weekly_scores > p99_c
    results['Fixed mu+3sig'] = weekly_scores > (mu_c + 3 * sig_c)

    # Adaptive z-score
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

    # Adaptive P99
    alarm_p99 = np.zeros(n_weeks, dtype=bool)
    for t in range(n_calib, n_weeks):
        past = weekly_scores[:t]; past_v = past[~np.isnan(past)]
        if len(past_v) >= 3:
            alarm_p99[t] = weekly_scores[t] > np.percentile(past_v, 99)
    results['Adaptive P99'] = alarm_p99

    # FARTarget calibration
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
    print("  ERCOT EARLY WARNING: Morse Topology + Betti Barcode Suite")
    print("  Supply-side data (d=5): wind_cf, solar_cf, gas_cf, coal_cf, nuclear_cf")
    print("=" * 90)

    X_3d, X_flat, week_dates, y_week, n_calib = load_dataset(SUPPLY_PATH)
    n_weeks = len(y_week)
    print(f"\n  Shape: {X_3d.shape}  (n_weeks={n_weeks}, d={X_3d.shape[2]})")
    print(f"  Calib: {n_calib} weeks  Monitor: {n_weeks - n_calib} weeks")
    print(f"  Events: {int(y_week[n_calib:].sum())} event-weeks in monitor")
    print(f"  Scoring: {len(SCORING_VARIANTS)} variants per engine")

    all_results = {}
    cache_path = RESULTS_DIR / "ercot_betti_morse_cache.json"
    
    # Check for existing cache
    cache = {}
    if cache_path.exists():
        try:
            cache = json.load(open(cache_path))
            print(f"\n  Loaded cache: {list(cache.keys())}")
        except Exception:
            cache = {}

    for eng_name, (engine_cls, engine_kwargs) in ENGINES.items():
        if eng_name in cache:
            print(f"\n  == Engine: {eng_name} (CACHED) ==")
            weekly = {v: np.array(s) for v, s in cache[eng_name].items()}
        else:
            print(f"\n  == Engine: {eng_name} ==")
            eng_t0 = time.time()
            weekly = expanding_window_betti_morse(
                X_3d, X_flat, y_week, engine_cls, engine_kwargs,
                n_calib, eng_name
            )
            elapsed = time.time() - eng_t0
            print(f"  {eng_name} done in {elapsed:.0f}s")

            # Cache
            cache[eng_name] = {v: s.tolist() for v, s in weekly.items()}
            with open(cache_path, 'w') as f:
                json.dump(cache, f)
            print(f"  Cached -> {cache_path.name}")

        # === Evaluate all variants ===
        eng_results = {}
        for var_name in SCORING_VARIANTS:
            ws = weekly[var_name]
            cals = apply_calibrations(ws, y_week, n_calib, n_weeks)
            var_results = {}
            for cal_name, alarm_mask in cals.items():
                r = evaluate(ws, alarm_mask, y_week, week_dates, n_calib)
                var_results[cal_name] = r
            eng_results[var_name] = var_results
        all_results[eng_name] = eng_results

    # =====================================================================
    #  Print Results
    # =====================================================================
    total_time = time.time() - t0

    print(f"\n\n{'=' * 90}")
    print(f"  AUC TABLE: Morse + Betti Foundation Scoring")
    print(f"{'=' * 90}")
    print(f"  {'Engine':<12} {'Variant':<22} {'AUC':>8}")
    print(f"  {'-' * 45}")

    for eng_name in ENGINES:
        for var_name in SCORING_VARIANTS:
            cals = all_results[eng_name][var_name]
            if cals:
                first = next(iter(cals.values()))
                a = first.get('auc')
                auc_s = f"{a:.4f}" if a else "  N/A"
            else:
                auc_s = "  N/A"
            marker = " <--" if var_name in ('morse_betti_fused', 'foundation_full') else ""
            print(f"  {eng_name:<12} {var_name:<22} {auc_s:>8}{marker}")
        print()

    # Top configs
    print(f"\n{'=' * 90}")
    print(f"  TOP 25 OPERATIONAL CONFIGS (3/3 events, sorted by FAR)")
    print(f"{'=' * 90}")
    print(f"  {'#':<3} {'Engine/Variant':<35} {'Calibration':<18} "
          f"{'Ev':>3} {'Lead':>5} {'FAR%':>6} {'AUC':>7}  Events")
    print(f"  {'-' * 105}")

    overall = []
    for eng_name in ENGINES:
        for var_name in SCORING_VARIANTS:
            cals = all_results[eng_name][var_name]
            for cal_name, r in cals.items():
                if r['n_ev'] > 0:
                    evs = " ".join(f"{e}={l}w" for e, l in r['events_detected'].items())
                    auc_s = f"{r['auc']:.4f}" if r['auc'] else "  N/A"
                    overall.append({
                        'key': f"{eng_name}/{var_name}",
                        'cal': cal_name,
                        'n_ev': r['n_ev'], 'lead': r['lead'],
                        'far': r['far'], 'auc': r['auc'] or 0,
                        'evs': evs, 'auc_s': auc_s,
                    })

    overall.sort(key=lambda x: (-x['n_ev'], x['far'], -x['lead']))
    for i, c in enumerate(overall[:25], 1):
        print(f"  {i:<3} {c['key']:<35} {c['cal']:<18} "
              f"{c['n_ev']:>3} {c['lead']:>4}w {c['far']:>5.1f}% "
              f"{c['auc_s']:>7}  {c['evs']}")

    # Comparison with previous best
    print(f"\n\n{'=' * 90}")
    print(f"  COMPARISON: Betti+Morse vs Previous BSDT-only Results")
    print(f"{'=' * 90}")
    print(f"  Previous best (BSDT/ExpoGate):  AUC = 0.8598 (Gravity/expogate)")
    print(f"  Previous best fused:             AUC = 0.5289 (Gravity/fused)")
    print(f"  Paper baseline:                  AUC = 0.9940")
    print()

    for eng_name in ENGINES:
        print(f"  {eng_name}:")
        for var_name in SCORING_VARIANTS:
            cals = all_results[eng_name][var_name]
            if cals:
                first = next(iter(cals.values()))
                a = first.get('auc')
                auc_s = f"{a:.4f}" if a else "N/A"
                # Best operational
                best = None
                for cal_name, r in cals.items():
                    if r['n_ev'] >= 3:
                        if best is None or r['far'] < best['far']:
                            best = {**r, 'cal': cal_name}
                op = ""
                if best:
                    op = f"  3/3ev FAR={best['far']:.1f}% lead={best['lead']}w [{best['cal']}]"
                print(f"    {var_name:<22} AUC={auc_s}{op}")
        print()

    print(f"\n  Total time: {total_time:.0f}s ({total_time/60:.1f}min)")

    # Save
    out_path = RESULTS_DIR / "ercot_betti_morse_results.json"
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"  Saved -> {out_path}")


if __name__ == '__main__':
    main()
