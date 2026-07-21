"""
Threshold Calibration Sweep -- NO retraining
=============================================
Uses the SAME engines & parameters as bench_international_banks.py.
Regenerates quarter-scores via single full-panel fit_score (fast, ~5s each)
then sweeps:
  - Percentile thresholds: [99, 97, 95, 93, 90, 85, 80, 75]
  - Z-score thresholds:    [2.5, 2.0, 1.75, 1.5, 1.25, 1.0, 0.75]
  - P-value thresholds:    [0.01, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]

Picks the operating point that maximises  F1  (harmonic mean of recall
and precision) while keeping FAR < 25%.

Author: Odeyemi Olusegun Israel
"""
import sys, os, json, warnings, gc, time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
warnings.filterwarnings("ignore")

from sklearn.metrics import roc_auc_score
from udl.system_mode import MolecularEngine, GravityModeEngine, HybridGravityEngine

ROOT = r'C:\amttp'
CACHE = os.path.join(ROOT, 'research', 'adaptive-friction',
                     'banklevel_enhanced', 'gsib_cache_real')

CRISIS_QUARTERS = {
    '2007-12-31', '2008-03-31', '2008-06-30', '2008-09-30',
    '2008-12-31', '2009-03-31', '2009-06-30',
    '2020-03-31', '2020-06-30',
    '2011-09-30', '2011-12-31', '2012-03-31', '2012-06-30',
}
CALIB_END = '2007-09-30'

ENGINES = {
    'Molecular': (MolecularEngine, dict(
        iterations=80, k_neighbors=10, use_fused=True,
        max_samples=2000, normalize=False)),
    'Gravity': (GravityModeEngine, dict(
        iterations=60, k_neighbors=10, use_fused=True)),
    'Hybrid': (HybridGravityEngine, dict()),
}

PCTL_SWEEP   = [99, 97, 95, 93, 90, 85, 80, 75]
Z_SWEEP      = [2.5, 2.0, 1.75, 1.5, 1.25, 1.0, 0.75]
P_SWEEP      = [0.01, 0.03, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]


# ------------------------------------------------------------------
#  Load data (same as bench)
# ------------------------------------------------------------------
def load_panel():
    npz = np.load(os.path.join(CACHE, 'gsib_real_panel.npz'))
    X = npz['X']
    with open(os.path.join(CACHE, 'gsib_real_meta.json'), encoding='utf-8') as f:
        meta = json.load(f)
    if X.shape[1] > len(meta):
        X = X[:, :len(meta), :]
    dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:X.shape[0]]
    return X, meta, dates


def _load_wb(fn):
    p = os.path.join(CACHE, fn)
    if not os.path.exists(p):
        return pd.Series(dtype=float)
    with open(p, encoding='utf-8') as f:
        raw = json.load(f)
    s = pd.Series(raw, dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def build_nigeria(dates):
    wb = {'loan_to_asset': 'wb_NGA_GFDD.DI.01.json',
          'equity_ratio':  'wb_NGA_FB.BNK.CAPA.ZS.json',
          'npl_ratio':     'wb_NGA_FB.AST.NPER.ZS.json',
          'roa':           'wb_NGA_GFDD.SI.01.json',
          'funding_cost':  'wb_NGA_FR.INR.LEND.json'}
    T = len(dates)
    X = np.full((T, 1, 5), np.nan)
    for fi, (fn, fname) in enumerate(wb.items()):
        s = _load_wb(fname)
        if len(s) == 0 and fn == 'funding_cost':
            s = _load_wb('wb_NGA_FR.INR.DPST.json')
        if len(s) == 0:
            continue
        sq = s.resample('QE').interpolate('linear')
        for t, dt in enumerate(dates):
            near = sq.index[sq.index <= dt]
            if len(near):
                X[t, 0, fi] = sq.loc[near[-1]]
    return X


def subset(X, meta, iso_list):
    idx = [i for i, b in enumerate(meta) if b['iso'] in iso_list]
    if not idx:
        return None, []
    return X[:, idx, :], [meta[i]['name'] for i in idx]


REGIONS = {
    'Full G-SIB Panel':  None,
    'USA (FDIC)':        ['USA'],
    'Europe + UK':       ['GBR', 'FRA', 'DEU', 'ITA', 'NLD'],
    'Asia (JP + CN)':    ['JPN', 'CHN'],
    'Nigeria (WB-GFDD)': ['NGA'],
}


# ------------------------------------------------------------------
#  Fast score generation: SINGLE fit_score on full panel
#  (not expanding window -- purely for calibration threshold tuning)
# ------------------------------------------------------------------
def generate_scores(X_3d, dates, eng_cls, eng_kw):
    """Single fit on full panel, extract per-quarter mean scores."""
    T, N, d = X_3d.shape
    X_flat = np.nan_to_num(X_3d.reshape(T * N, d), nan=0.0)
    y_flat = np.zeros(T * N, dtype=int)

    eng = eng_cls(**eng_kw)
    scores = eng.fit_score(X_flat, y_flat)
    del eng; gc.collect()

    q_scores = np.array([scores[t * N:(t + 1) * N].mean() for t in range(T)])
    return q_scores


# ------------------------------------------------------------------
#  Compute derived scores (z-score, p-value) from q_scores
# ------------------------------------------------------------------
def derive_channels(q_scores, dates, n_calib):
    T = len(q_scores)
    valid = ~np.isnan(q_scores)

    # Z-scores (expanding window)
    z = np.full(T, np.nan)
    for t in range(4, T):
        if not valid[t]:
            continue
        past = q_scores[:t][valid[:t]]
        if len(past) < 4:
            continue
        mu, sig = past.mean(), past.std()
        if sig < 1e-10:
            continue
        z[t] = (q_scores[t] - mu) / sig

    # Conformal p-values (calibration as reference)
    cal = q_scores[:n_calib]
    cal = cal[~np.isnan(cal)]
    cal_sorted = np.sort(cal)
    n_cal = len(cal_sorted)

    pv = np.full(T, np.nan)
    for t in range(T):
        if not valid[t]:
            continue
        rank = n_cal - np.searchsorted(cal_sorted, q_scores[t], side='left')
        pv[t] = (1 + rank) / (n_cal + 1)

    return z, pv


# ------------------------------------------------------------------
#  Evaluate at a specific threshold
# ------------------------------------------------------------------
def eval_at_threshold(scores, alarm_mask, y_crisis, dates):
    T = len(dates)
    valid = ~np.isnan(scores)
    crisis = y_crisis.astype(bool)

    # AUROC on valid entries
    y_v = y_crisis[valid]
    s_v = scores[valid]
    auroc = roc_auc_score(y_v, s_v) if 0 < y_v.sum() < len(y_v) else float('nan')

    # GFC-specific
    gfc_set = {'2007-12-31', '2008-03-31', '2008-06-30', '2008-09-30',
               '2008-12-31', '2009-03-31', '2009-06-30'}
    gfc_m = np.array([str(dates[i].date()) in gfc_set for i in range(T)])
    gfc_or_norm = valid & (gfc_m | (y_crisis == 0))
    if gfc_or_norm.sum() > 2 and y_crisis[gfc_or_norm].sum() > 0:
        auroc_gfc = roc_auc_score(y_crisis[gfc_or_norm], s_v[gfc_or_norm[valid]])
    else:
        auroc_gfc = float('nan')

    tp = int((alarm_mask & crisis & valid).sum())
    fp = int((alarm_mask & ~crisis & valid).sum())
    fn = int((~alarm_mask & crisis & valid).sum())
    tn = int((~alarm_mask & ~crisis & valid).sum())
    far = fp / max(fp + tn, 1) * 100
    recall = tp / max(tp + fn, 1) * 100
    prec = tp / max(tp + fp, 1) * 100
    f1 = 2 * prec * recall / max(prec + recall, 1e-10)

    alarm_dates = [str(dates[i].date()) for i in range(T) if alarm_mask[i]]
    first = alarm_dates[0] if alarm_dates else 'none'
    pre_gfc = [d for d in alarm_dates if '2007-01-01' <= d < '2007-12-31']
    gfc_lead = pre_gfc[0] if pre_gfc else None

    return dict(auroc=auroc, auroc_gfc=auroc_gfc, far=far, recall=recall,
                prec=prec, f1=f1, tp=tp, fp=fp, fn=fn, tn=tn,
                first_alarm=first, gfc_lead=gfc_lead)


# ------------------------------------------------------------------
#  SWEEP
# ------------------------------------------------------------------
def sweep_all(q_scores, z_scores, p_values, n_calib, dates, y_crisis):
    T = len(dates)
    valid_q = ~np.isnan(q_scores)
    valid_z = ~np.isnan(z_scores)
    valid_p = ~np.isnan(p_values)
    results = {}

    # --- Percentile sweep ---
    calib_q = q_scores[:n_calib]
    calib_q = calib_q[~np.isnan(calib_q)]
    pctl_results = []
    for pctl in PCTL_SWEEP:
        thresh = float(np.percentile(calib_q, pctl)) if len(calib_q) > 2 else 1e10
        alarm = np.zeros(T, dtype=bool)
        alarm[valid_q] = q_scores[valid_q] > thresh
        r = eval_at_threshold(q_scores, alarm, y_crisis, dates)
        r['threshold'] = thresh
        r['pctl'] = pctl
        pctl_results.append(r)
    results['percentile'] = pctl_results

    # --- Z-score sweep ---
    z_results = []
    for z_thresh in Z_SWEEP:
        alarm = np.zeros(T, dtype=bool)
        alarm[valid_z] = z_scores[valid_z] > z_thresh
        r = eval_at_threshold(z_scores, alarm, y_crisis, dates)
        r['z_thresh'] = z_thresh
        z_results.append(r)
    results['z_score'] = z_results

    # --- P-value sweep (alarm when p < threshold, scores = -p for AUROC) ---
    pv_results = []
    for p_thresh in P_SWEEP:
        alarm = np.zeros(T, dtype=bool)
        alarm[valid_p] = p_values[valid_p] < p_thresh
        # Use negative p for AUROC (lower p = more anomalous)
        r = eval_at_threshold(-p_values, alarm, y_crisis, dates)
        r['p_thresh'] = p_thresh
        pv_results.append(r)
    results['p_value'] = pv_results

    return results


# ------------------------------------------------------------------
#  MAIN
# ------------------------------------------------------------------
def main():
    print('=' * 100)
    print('  CALIBRATION SWEEP -- Threshold Tuning on Existing Scores')
    print('  No retraining. Single fit_score per region/engine for score recovery.')
    print('  Sweeping: Percentile | Z-score | P-value thresholds')
    print('=' * 100)

    X_3d, meta, dates = load_panel()
    T = X_3d.shape[0]
    y_crisis = np.array([1 if str(dt.date()) in CRISIS_QUARTERS else 0
                         for dt in dates])
    n_calib = int((dates <= pd.Timestamp(CALIB_END)).sum())

    all_best = {}

    for region_name, iso_list in REGIONS.items():
        print(f'\n{"=" * 98}')
        print(f'  REGION: {region_name}')
        print(f'{"=" * 98}')

        if region_name == 'Nigeria (WB-GFDD)':
            X_sub = build_nigeria(dates)
            banks = ['Nigeria Banking Sector']
        elif iso_list is None:
            X_sub = X_3d
            banks = [b['name'] for b in meta]
        else:
            X_sub, banks = subset(X_3d, meta, iso_list)

        if X_sub is None:
            print('  [SKIP]')
            continue

        print(f'  Banks: {len(banks)}')
        region_best = {}

        for eng_name, (eng_cls, eng_kw) in ENGINES.items():
            print(f'\n  -- {eng_name} --')
            t0 = time.time()

            q_scores = generate_scores(X_sub, dates, eng_cls, eng_kw)
            z_scores, p_values = derive_channels(q_scores, dates, n_calib)
            elapsed = time.time() - t0
            print(f'     Score generation: {elapsed:.1f}s')

            sweep = sweep_all(q_scores, z_scores, p_values,
                              n_calib, dates, y_crisis)

            # --- Print percentile sweep ---
            print(f'\n     PERCENTILE SWEEP:')
            print(f'     {"Pctl":>5s}  {"Thresh":>7s}  {"AUROC":>6s}  '
                  f'{"GFC":>6s}  {"FAR%":>5s}  {"Recall%":>7s}  '
                  f'{"Prec%":>6s}  {"F1":>5s}  {"TP":>3s} {"FP":>3s}  '
                  f'{"1st Alarm":<12s}')
            print(f'     {"-" * 90}')
            for r in sweep['percentile']:
                gfc_a = f'{r["auroc_gfc"]:.4f}' if not np.isnan(r['auroc_gfc']) else '  N/A '
                print(f'     {r["pctl"]:5d}  {r["threshold"]:7.4f}  '
                      f'{r["auroc"]:6.4f}  {gfc_a}  '
                      f'{r["far"]:4.1f}%  {r["recall"]:6.1f}%  '
                      f'{r["prec"]:5.1f}%  {r["f1"]:5.1f}  '
                      f'{r["tp"]:3d} {r["fp"]:3d}  {r["first_alarm"]:<12s}')

            # --- Print z-score sweep ---
            print(f'\n     Z-SCORE SWEEP:')
            print(f'     {"Z":>5s}  {"AUROC":>6s}  {"GFC":>6s}  '
                  f'{"FAR%":>5s}  {"Recall%":>7s}  {"Prec%":>6s}  '
                  f'{"F1":>5s}  {"TP":>3s} {"FP":>3s}  {"1st Alarm":<12s}')
            print(f'     {"-" * 82}')
            for r in sweep['z_score']:
                gfc_a = f'{r["auroc_gfc"]:.4f}' if not np.isnan(r['auroc_gfc']) else '  N/A '
                print(f'     {r["z_thresh"]:5.2f}  {r["auroc"]:6.4f}  '
                      f'{gfc_a}  {r["far"]:4.1f}%  {r["recall"]:6.1f}%  '
                      f'{r["prec"]:5.1f}%  {r["f1"]:5.1f}  '
                      f'{r["tp"]:3d} {r["fp"]:3d}  {r["first_alarm"]:<12s}')

            # --- Print p-value sweep ---
            print(f'\n     P-VALUE SWEEP:')
            print(f'     {"P":>5s}  {"AUROC":>6s}  {"GFC":>6s}  '
                  f'{"FAR%":>5s}  {"Recall%":>7s}  {"Prec%":>6s}  '
                  f'{"F1":>5s}  {"TP":>3s} {"FP":>3s}  {"1st Alarm":<12s}')
            print(f'     {"-" * 82}')
            for r in sweep['p_value']:
                gfc_a = f'{r["auroc_gfc"]:.4f}' if not np.isnan(r['auroc_gfc']) else '  N/A '
                print(f'     {r["p_thresh"]:5.2f}  {r["auroc"]:6.4f}  '
                      f'{gfc_a}  {r["far"]:4.1f}%  {r["recall"]:6.1f}%  '
                      f'{r["prec"]:5.1f}%  {r["f1"]:5.1f}  '
                      f'{r["tp"]:3d} {r["fp"]:3d}  {r["first_alarm"]:<12s}')

            # --- Best per channel (max F1 with FAR < 25%) ---
            best = {}
            for ch_name, ch_data, param_key in [
                ('percentile', sweep['percentile'], 'pctl'),
                ('z_score',    sweep['z_score'],    'z_thresh'),
                ('p_value',    sweep['p_value'],    'p_thresh'),
            ]:
                candidates = [r for r in ch_data
                              if r['far'] < 25 and not np.isnan(r['f1'])
                              and r['f1'] > 0]
                if candidates:
                    best_r = max(candidates, key=lambda x: x['f1'])
                    best[ch_name] = best_r
                    print(f'\n     >> BEST {ch_name}: '
                          f'{param_key}={best_r[param_key]}  '
                          f'F1={best_r["f1"]:.1f}  '
                          f'Recall={best_r["recall"]:.1f}%  '
                          f'FAR={best_r["far"]:.1f}%  '
                          f'GFC-AUC={best_r["auroc_gfc"]:.4f}')
                else:
                    # Relax FAR constraint
                    candidates2 = [r for r in ch_data
                                   if not np.isnan(r['f1']) and r['f1'] > 0]
                    if candidates2:
                        best_r = max(candidates2, key=lambda x: x['f1'])
                        best[ch_name] = best_r
                        print(f'\n     >> BEST {ch_name} (relaxed): '
                              f'{param_key}={best_r[param_key]}  '
                              f'F1={best_r["f1"]:.1f}  '
                              f'Recall={best_r["recall"]:.1f}%  '
                              f'FAR={best_r["far"]:.1f}%')
                    else:
                        print(f'\n     >> BEST {ch_name}: no valid operating point')

            region_best[eng_name] = best

        all_best[region_name] = region_best

    # ==============================================================
    #  FINAL SUMMARY: Optimal thresholds per region
    # ==============================================================
    print('\n\n' + '=' * 100)
    print('  OPTIMAL CALIBRATION SUMMARY')
    print('  Criterion: max F1 with FAR < 25%')
    print('=' * 100)

    for region_name in REGIONS:
        if region_name not in all_best:
            continue
        print(f'\n  {region_name}:')
        rb = all_best[region_name]
        for eng_name in ENGINES:
            if eng_name not in rb:
                continue
            eb = rb[eng_name]
            best_overall = None
            best_f1 = -1
            for ch_name, r in eb.items():
                if r.get('f1', 0) > best_f1:
                    best_f1 = r['f1']
                    best_overall = (ch_name, r)
            if best_overall:
                ch, r = best_overall
                print(f'    {eng_name:<12s}  Channel={ch:<12s}  '
                      f'F1={r["f1"]:.1f}  '
                      f'AUROC={r["auroc"]:.4f}  '
                      f'GFC-AUC={r.get("auroc_gfc", 0):.4f}  '
                      f'Recall={r["recall"]:.1f}%  '
                      f'FAR={r["far"]:.1f}%  '
                      f'Prec={r["prec"]:.1f}%')
            else:
                print(f'    {eng_name:<12s}  No valid operating point')

    print('\nDone.')


if __name__ == '__main__':
    main()
