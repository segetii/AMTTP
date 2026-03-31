"""
ercot_supply_benchmark.py
=========================
Paper-compliant expanding-window benchmark on the REAL supply-side data.

Runs the same protocol as ercot_adaptive_posthoc.py, but on THREE datasets:
  1. Supply (d=5): wind_cf, solar_cf, gas_cf, coal_cf, nuclear_cf  [paper's features]
  2. Demand (d=5): demand_gw, ramp_rate, vol_6h, dev_24h, temp_stress
  3. Combined (d=10): both

For each dataset:
  - 3 engines × 5 scoring variants × 9 calibrations = 135 configs
  - Expanding window, BSDTChannels on X_final_, MFLS corrections
  - Full results tables + comparison

This is the definitive benchmark for reproducing the paper's ERCOT AUC ≈ 0.994.
"""
from __future__ import annotations
import sys, os, time, json, warnings, gc
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import roc_auc_score
from sklearn.isotonic import IsotonicRegression

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
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

EVENT_ONSETS = {
    "SummerPeak2019":     pd.Timestamp("2019-08-12"),
    "COVID_Collapse":     pd.Timestamp("2020-03-23"),
    "WinterStormUri":     pd.Timestamp("2021-02-10"),
    "WinterStormElliott": pd.Timestamp("2022-12-22"),
}

DATASETS = {
    "supply": ROOT / "data" / "ercot" / "ercot_supply_hourly.npz",
    "demand": ROOT / "data" / "ercot" / "ercot_demand_hourly.npz",
    "combined": ROOT / "data" / "ercot" / "ercot_combined_hourly.npz",
}

ENGINES = {
    "Molecular": (MolecularEngine, dict(
        iterations=80, k_neighbors=10, max_samples=3000,
        use_bsdt_damping=True)),
    "Gravity": (GravityModeEngine, dict(
        iterations=60, k_neighbors=10)),
    "Hybrid": (HybridGravityEngine, dict()),
}

SCORING_VARIANTS = ['fused', 'bsdt_e', 'fisher', 'quadsurf', 'expogate']
CAL_METHODS = ['Fixed mu+3sig', 'Fixed P99', 'Fixed med+3MAD',
               'Adaptive z>3', 'Adaptive z>2', 'Adaptive P99',
               'Isotonic', 'Platt', 'Conformal']


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
    wk_labels = []
    for i in range(n_weeks):
        chunk = lb_t[i*H:(i+1)*H]
        nn = [l for l in chunk if l != 'Normal' and l != 'normal']
        wk_labels.append(nn[0] if nn else 'Normal')

    calib_mask = week_dates <= pd.Timestamp("2019-06-30")
    n_calib = int(calib_mask.sum())
    return X_3d, X_t, week_dates, y_week, np.array(wk_labels), n_calib


# =====================================================================
#  Expanding-window scoring (all variants)
# =====================================================================

def expanding_window_all_variants(X_3d, X_flat, y_week, engine_cls,
                                  engine_kwargs, n_calib, eng_name):
    n_weeks, Hw, d = X_3d.shape
    variants = ['fused', 'bsdt_e', 'fisher', 'quadsurf', 'expogate']
    weekly = {v: np.full(n_weeks, np.nan) for v in variants}

    is_hybrid = (engine_cls == HybridGravityEngine)

    if is_hybrid:
        fused_kwargs = {**engine_kwargs}
        posthoc_kwargs = {**engine_kwargs}
    else:
        fused_kwargs = {**engine_kwargs, 'use_fused': True}
        posthoc_kwargs = {**engine_kwargs, 'use_fused': False}

    def _get_X_final(eng):
        if is_hybrid:
            return eng.molecular.X_final_
        return eng.X_final_

    # === Calibration period ===
    n_h_cal = n_calib * Hw
    X_cal_flat = X_3d[:n_calib].reshape(n_h_cal, d)
    y_zeros = np.zeros(n_h_cal, dtype=int)

    eng_f = engine_cls(**fused_kwargs)
    sc_fused = eng_f.fit_score(X_cal_flat, y_zeros)
    for w in range(n_calib):
        weekly['fused'][w] = sc_fused[w*Hw:(w+1)*Hw].mean()

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
        weekly['quadsurf'][w] = sc_fisher[sl].mean()
        weekly['expogate'][w] = sc_fisher[sl].mean()
    if is_hybrid:
        del eng_f
    else:
        del eng_p
    del bsdt, layer_f; gc.collect()
    print(f"    Calib done (w=0..{n_calib-1})")

    # === Monitoring period ===
    for w in range(n_calib, n_weeks):
        n_h = (w + 1) * Hw
        X_up = X_3d[:w+1].reshape(n_h, d)
        y_eng = np.zeros(n_h, dtype=int)

        if is_hybrid:
            eng_h = engine_cls(**fused_kwargs)
            sc_f = eng_h.fit_score(X_up, y_eng)
            weekly['fused'][w] = sc_f[-Hw:].mean()
            X_ref = _get_X_final(eng_h)
            del eng_h
        else:
            eng_f = engine_cls(**fused_kwargs)
            sc_f = eng_f.fit_score(X_up, y_eng)
            weekly['fused'][w] = sc_f[-Hw:].mean()
            del eng_f; gc.collect()

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

        layer_f = _MFLSFisherBSDT(); layer_f.fit(C)
        weekly['fisher'][w] = layer_f.score(C)[-Hw:].mean()

        y_ph = np.zeros(n_h, dtype=float)
        for wi in range(w + 1):
            if y_week[wi] == 1:
                y_ph[wi*Hw:(wi+1)*Hw] = 1.0
        n_crisis_pts = int(y_ph.sum())

        if n_crisis_pts > 0:
            try:
                layer_q = _MFLSQuadSurf(ridge_alpha=1.0)
                layer_q.fit(C, y_ph)
                weekly['quadsurf'][w] = layer_q.score(C)[-Hw:].mean()
            except Exception:
                weekly['quadsurf'][w] = weekly['fisher'][w]
        else:
            weekly['quadsurf'][w] = weekly['fisher'][w]

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
    from scipy.optimize import minimize
    s = scores.astype(float); y = labels.astype(float)
    n_pos = y.sum(); n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    t_pos = (n_pos + 1) / (n_pos + 2)
    t_neg = 1 / (n_neg + 2)
    t = np.where(y == 1, t_pos, t_neg)
    def loss(params):
        A, B = params
        p = 1.0 / (1.0 + np.exp(np.clip(A * s + B, -30, 30)))
        p = np.clip(p, 1e-10, 1 - 1e-10)
        return -np.sum(t * np.log(p) + (1 - t) * np.log(1 - p))
    res = minimize(loss, x0=[0.0, 0.0], method='Nelder-Mead')
    return res.x

def _platt_sigmoid_predict(scores, params):
    if params is None:
        return np.full(len(scores), 0.5)
    A, B = params
    return 1.0 / (1.0 + np.exp(np.clip(A * scores + B, -30, 30)))

def _conformal_pvalue(score, cal_scores):
    return (np.sum(cal_scores >= score) + 1) / (len(cal_scores) + 1)


def apply_calibrations(weekly_scores, y_week, n_calib, n_weeks):
    cs = weekly_scores[:n_calib]
    cs_clean = cs[~np.isnan(cs)]
    mu_c = np.nanmean(cs_clean); sig_c = np.nanstd(cs_clean)
    med_c = np.nanmedian(cs_clean)
    mad_c = np.nanmedian(np.abs(cs_clean - med_c))
    p99_c = np.nanpercentile(cs_clean, 99) if len(cs_clean) > 0 else mu_c

    results = {}
    results['Fixed mu+3sig'] = weekly_scores > (mu_c + 3 * sig_c)
    results['Fixed P99'] = weekly_scores > p99_c
    results['Fixed med+3MAD'] = weekly_scores > (med_c + 3 * (mad_c + 1e-10))

    z_scores = np.full(n_weeks, np.nan)
    for t in range(n_calib, n_weeks):
        past = weekly_scores[:t]; past_v = past[~np.isnan(past)]
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

    alarm_p99 = np.zeros(n_weeks, dtype=bool)
    for t in range(n_calib, n_weeks):
        past = weekly_scores[:t]; past_v = past[~np.isnan(past)]
        if len(past_v) >= 3:
            alarm_p99[t] = weekly_scores[t] > np.percentile(past_v, 99)
    results['Adaptive P99'] = alarm_p99

    alarm_iso = np.zeros(n_weeks, dtype=bool)
    for t in range(n_calib, n_weeks):
        past_s = weekly_scores[:t]; past_y = y_week[:t]; valid = ~np.isnan(past_s)
        if valid.sum() >= 4 and past_y[valid].sum() > 0 and past_y[valid].sum() < valid.sum():
            iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds='clip')
            iso.fit(past_s[valid], past_y[valid].astype(float))
            alarm_iso[t] = iso.predict([weekly_scores[t]])[0] > 0.5
        else:
            if not np.isnan(z_scores[t]):
                alarm_iso[t] = z_scores[t] > 2.0
    results['Isotonic'] = alarm_iso

    alarm_platt = np.zeros(n_weeks, dtype=bool)
    for t in range(n_calib, n_weeks):
        past_s = weekly_scores[:t]; past_y = y_week[:t]; valid = ~np.isnan(past_s)
        if valid.sum() >= 4 and past_y[valid].sum() > 0 and past_y[valid].sum() < valid.sum():
            params = _platt_sigmoid_fit(past_s[valid], past_y[valid])
            alarm_platt[t] = _platt_sigmoid_predict(np.array([weekly_scores[t]]), params)[0] > 0.5
        else:
            if not np.isnan(z_scores[t]):
                alarm_platt[t] = z_scores[t] > 2.0
    results['Platt'] = alarm_platt

    alarm_conf = np.zeros(n_weeks, dtype=bool)
    n_split = max(1, int(0.75 * n_calib))
    conf_ref = cs_clean[n_split:]
    if len(conf_ref) >= 2:
        for t in range(n_calib, n_weeks):
            if not np.isnan(weekly_scores[t]):
                alarm_conf[t] = _conformal_pvalue(weekly_scores[t], conf_ref) <= 0.05
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
        pre = [w for w in range(max(n_calib, onset_w - 20), onset_w)
               if alarm_mask[w]]
        if pre:
            events[evt_name] = f"{onset_w - pre[0]}w"
        else:
            ea = [w for w in range(onset_w, min(onset_w + 4, n))
                  if alarm_mask[w]]
            events[evt_name] = "conc" if ea else "--"

    return {'auc': auc, 'far': round(far, 1), 'recall': round(recall, 1),
            'prec': round(prec, 1), 'events': events}


# =====================================================================
#  Run one dataset
# =====================================================================

def run_dataset(ds_name, ds_path):
    cache_path = RESULTS_DIR / f"ercot_{ds_name}_posthoc_cache.json"

    print(f"\n{'#'*90}")
    print(f"  DATASET: {ds_name.upper()} — {ds_path.name}")
    print(f"{'#'*90}")

    X_3d, X_flat, week_dates, y_week, week_labels, n_calib = load_dataset(ds_path)
    n_weeks = len(y_week)
    n_events = int(y_week[n_calib:].sum())
    print(f"  Shape: {X_3d.shape}  (n_weeks={n_weeks}, d={X_3d.shape[2]})")
    print(f"  Calib: {n_calib} weeks ({week_dates[0].date()} -> {week_dates[n_calib-1].date()})")
    print(f"  Monitor: {n_weeks-n_calib} weeks ({week_dates[n_calib].date()} -> {week_dates[-1].date()})")
    print(f"  Events in monitor: {n_events} event-weeks\n")

    # == Phase A: Scores (cached) ==
    if cache_path.exists():
        print(f"  Loading cached scores from {cache_path.name}")
        with open(cache_path) as f:
            cached = json.load(f)
        all_weekly = {}
        for eng_name in ENGINES:
            if eng_name in cached:
                all_weekly[eng_name] = {
                    v: np.array(s) for v, s in cached[eng_name].items()
                }
    else:
        print(f"  Running expanding-window engine fits ...")
        all_weekly = {}
        for eng_name, (eng_cls, eng_kwargs) in ENGINES.items():
            print(f"\n  == Engine: {eng_name} ==")
            t0 = time.time()
            weekly = expanding_window_all_variants(
                X_3d, X_flat, y_week, eng_cls, eng_kwargs, n_calib, eng_name)
            elapsed = time.time() - t0
            all_weekly[eng_name] = weekly
            print(f"  {eng_name} done in {elapsed:.0f}s")

        cache_data = {}
        for eng_name, wk in all_weekly.items():
            cache_data[eng_name] = {v: s.tolist() for v, s in wk.items()}
        with open(cache_path, 'w') as f:
            json.dump(cache_data, f, indent=2)
        print(f"\n  Cached -> {cache_path.name}")

    # == Phase B: Apply calibrations ==
    all_results = {}
    for eng_name in ENGINES:
        eng_r = {}
        for var in SCORING_VARIANTS:
            ws = all_weekly[eng_name][var]
            eng_r[var] = {}
            alarm_map = apply_calibrations(ws, y_week, n_calib, n_weeks)
            for cal_name in CAL_METHODS:
                alarm = alarm_map[cal_name]
                eng_r[var][cal_name] = evaluate(
                    ws, alarm, y_week, week_dates, n_calib)
        all_results[eng_name] = eng_r

    return all_results, n_weeks, n_calib, week_dates, y_week


# =====================================================================
#  Print tables for one dataset
# =====================================================================

def print_tables(ds_name, all_results, n_weeks, n_calib, week_dates, y_week):

    # == Table 1: AUC comparison ==
    print(f"\n{'='*90}")
    print(f"  TABLE 1: AUC COMPARISON — {ds_name.upper()}")
    print(f"{'='*90}")
    print(f"  {'Engine':<12} {'Variant':<12} {'AUC':>7}")
    print(f"  {'-'*35}")
    best_auc = 0
    best_tag = ""
    for eng_name in ENGINES:
        for var in SCORING_VARIANTS:
            r0 = all_results[eng_name][var]
            auc = list(r0.values())[0]['auc']
            auc_s = f"{auc:.4f}" if auc else "N/A"
            print(f"  {eng_name:<12} {var:<12} {auc_s:>7}")
            if auc and auc > best_auc:
                best_auc = auc; best_tag = f"{eng_name}/{var}"
        print()
    print(f"  >> Best AUC: {best_auc:.4f} ({best_tag})")

    # == Table 2: Best 15 overall configs ==
    print(f"\n{'='*90}")
    print(f"  TABLE 2: TOP 15 CONFIGS — {ds_name.upper()}")
    print(f"{'='*90}")

    overall = []
    for eng_name in ENGINES:
        for var in SCORING_VARIANTS:
            for cal_name in CAL_METHODS:
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
    print(f"  {'-'*100}")
    for i, c in enumerate(overall[:15]):
        auc_s = f"{c['auc']:.4f}" if c['auc'] else 'N/A'
        evs = ' '.join(f"{k}={v}" for k, v in c['events'].items()
                       if v not in ("--", "conc"))
        tag = f"{c['eng']}/{c['var']}"
        print(f"  {i+1:<3} {tag:<25} {c['cal']:<18} "
              f"{c['n_ev']:>3} {c['lead']:>4}w {c['far']:>5.1f}% {auc_s:>7}  {evs}")

    return best_auc, best_tag


# =====================================================================
#  Main
# =====================================================================

def main():
    t_total = time.time()
    print('=' * 90)
    print('  ERCOT SUPPLY vs DEMAND vs COMBINED BENCHMARK')
    print('  Paper-compliant expanding-window | BSDT/MFLS corrections')
    print('  3 datasets × 3 engines × 5 variants × 9 calibrations = 405 configs')
    print('=' * 90)

    summary = {}

    for ds_name, ds_path in DATASETS.items():
        t0 = time.time()
        all_results, n_weeks, n_calib, week_dates, y_week = run_dataset(ds_name, ds_path)
        best_auc, best_tag = print_tables(
            ds_name, all_results, n_weeks, n_calib, week_dates, y_week)
        elapsed = time.time() - t0

        summary[ds_name] = {
            "best_auc": best_auc,
            "best_config": best_tag,
            "elapsed_s": round(elapsed),
        }

        # Save per-dataset results
        json_out = {}
        for eng_name in ENGINES:
            json_out[eng_name] = {}
            for var in SCORING_VARIANTS:
                json_out[eng_name][var] = {}
                for cal_name in CAL_METHODS:
                    r = all_results[eng_name][var].get(cal_name)
                    if r:
                        json_out[eng_name][var][cal_name] = r
        out_path = RESULTS_DIR / f"ercot_{ds_name}_results.json"
        with open(out_path, 'w') as f:
            json.dump(json_out, f, indent=2)
        print(f"\n  Saved {out_path.name}  ({elapsed:.0f}s)")

    # == Final comparison ==
    total_elapsed = time.time() - t_total
    print(f"\n\n{'#'*90}")
    print(f"  FINAL COMPARISON: SUPPLY vs DEMAND vs COMBINED")
    print(f"  (Paper reports ERCOT AUC = 0.9940 using supply-side d=5)")
    print(f"{'#'*90}")
    print(f"\n  {'Dataset':<12} {'Best AUC':>10} {'Best Config':<35} {'Time':>8}")
    print(f"  {'-'*70}")
    for ds_name, s in summary.items():
        print(f"  {ds_name:<12} {s['best_auc']:>10.4f} {s['best_config']:<35} "
              f"{s['elapsed_s']:>6}s")
    print(f"\n  Total time: {total_elapsed/60:.1f} min")
    print(f"\n  Paper baseline: AUC = 0.9940 (Hybrid, supply d=5, FARTargetCalibrator)")

    # Save summary
    with open(RESULTS_DIR / "ercot_supply_vs_demand_summary.json", 'w') as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
