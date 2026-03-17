"""
International Banking Benchmark -- BSDT Prospective Early Warning
==================================================================
Replicates the EXACT pipeline from bench_bank_level_prospective.py
across regional subsets of the G-SIB panel.

Protocol (matches the paper / real-world bank supervision):
  1. Calibration window: 2005-Q1 to 2007-Q3 (pre-GFC stable period)
     - Alarm threshold = calibrated percentile of calibration scores
  2. Expanding window online scoring (2007-Q4 onward):
     - Fit on ALL data up to quarter t (y = zeros, pure unsupervised)
     - Score = mean engine score of current-quarter banks
  3. Three alarm channels (CALIBRATED thresholds from sweep):
     a) Raw threshold: score > Pth percentile of calibration
     b) Rolling z-score: z(t) = (score(t) - running_mean) / running_std
     c) Conformal p-value: (1 + rank_in_calibration) / (n_cal + 1)
  4. Model artifacts saved: fitted engine state, raw scores,
     per-bank scores, z-scores, p-values, calibration reference

NO crisis labels used during scoring -- purely unsupervised.
Labels used ONLY for evaluation AFTER all scoring is complete.

Data: FDIC call reports (US) + ECB MIR (EU) + World Bank GFDD (rest)

Author: Odeyemi Olusegun Israel
"""
import sys, os, time, warnings, json, gc, pickle
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

warnings.filterwarnings("ignore")

from sklearn.metrics import roc_auc_score
from udl.system_mode import (MolecularEngine, GravityModeEngine,
                              HybridGravityEngine, ReducedTensorDescriptor,
                              BSDTChannels)
from udl.stack import RepresentationStack
from udl.tensor import AnomalyTensor


# ==================================================================
#  ENGINE WRAPPERS (for non-simulation engines)
# ==================================================================

class ReducedTensorEngine:
    """Wrapper around ReducedTensorDescriptor for fit_score() interface.

    Uses GMM-based energy landscape, Hessian eigenvalues, Morse index,
    Mahalanobis distance, medoid distance, local covariance.
    Score = Fisher-VR-weighted z-score combination of descriptor.
    """
    def __init__(self, k_neighbors=20, n_eigs=None):
        self.k_neighbors = k_neighbors
        self.n_eigs = n_eigs

    def fit_score(self, X, y=None):
        desc = ReducedTensorDescriptor(
            k_neighbors=self.k_neighbors, n_eigs=self.n_eigs)
        desc.fit(X)  # unsupervised: fit on all data (y=0 always)
        return desc.score(X)


class MDNTensorEngine:
    """MDN (Magnitude-Direction-Novelty) Tensor engine.

    Passes data through RepresentationStack (multi-spectrum operators),
    then decomposes via AnomalyTensor into magnitude, per-law magnitudes,
    and novelty.  Uses Variant D hybrid 3-channel scoring:
      Ch1: total magnitude quantile
      Ch2: max per-law z-score one-sided activation
      Ch3: angular novelty
    """
    def __init__(self, standardize=True):
        self.standardize = standardize

    def fit_score(self, X, y=None):
        stack = RepresentationStack(standardize=self.standardize)
        stack.fit(X)
        R = stack.transform(X)

        tensor = AnomalyTensor()
        tensor.fit(R)

        # Build on reference to capture per-law stats
        result_ref = tensor.build(R, stack.law_dims_)
        tensor.store_ref_law_stats(result_ref)

        # Rebuild with ref stats available
        result = tensor.build(R, stack.law_dims_)
        return result.anomaly_score_v3d()


class QuadSurfEngine:
    """QuadSurf (Fisher-weighted degree-2 polynomial surface) engine.

    Uses BSDT 4-channel decomposition (delta_C, delta_G, delta_A, delta_T)
    then applies Fisher-VR-weighted quadratic polynomial surface:
      Q(c) = sum_k w_k c_k' + sum_k w_k c_k'^2
             + sum_{k<j} sqrt(w_k w_j) c_k' c_j'
    where c_k' = (c_k - mu_k) / sigma_k.
    """
    def __init__(self, k=20):
        self.k = k

    def fit_score(self, X, y=None):
        bsdt = BSDTChannels(k=self.k)
        bsdt.fit(X)

        # Channel matrix
        ch = bsdt.channels(X)
        C = np.column_stack([ch['delta_C'], ch['delta_G'],
                             ch['delta_A'], ch['delta_T']])
        K = C.shape[1]
        eps = 1e-8

        # Fisher VR weights (same logic as src/system_mode.py)
        total_mag = C.sum(axis=1)
        p80 = np.percentile(total_mag, 80)
        p50 = np.percentile(total_mag, 50)
        high_mask = total_mag >= p80
        low_mask = total_mag <= p50

        if high_mask.sum() >= 2 and low_mask.sum() >= 2:
            fr = np.zeros(K)
            for ki in range(K):
                mu_h = C[high_mask, ki].mean()
                mu_l = C[low_mask, ki].mean()
                var_h = C[high_mask, ki].var()
                var_l = C[low_mask, ki].var()
                fr[ki] = (mu_h - mu_l)**2 / max(var_h + var_l, eps)
            total_fr = fr.sum()
            w = fr / total_fr if total_fr > eps else np.ones(K) / K
        else:
            w = np.ones(K) / K

        mu = C.mean(axis=0)
        std = C.std(axis=0) + eps

        # QuadSurf polynomial
        C_std = (C - mu) / std
        linear = (C_std * w).sum(axis=1)
        squared = (C_std**2 * w).sum(axis=1)
        cross = np.zeros(len(C_std))
        for ki in range(K):
            for kj in range(ki + 1, K):
                cross += np.sqrt(w[ki] * w[kj]) * C_std[:, ki] * C_std[:, kj]

        return np.maximum(linear + squared + cross, 0.0)


# ==================================================================
#  CONFIG
# ==================================================================
ROOT = r'C:\amttp'
CACHE_DIR = os.path.join(ROOT, 'research', 'adaptive-friction',
                         'banklevel_enhanced', 'gsib_cache_real')
ARTIFACT_DIR = os.path.join(ROOT, 'model_artifacts', 'international_banks')

CRISIS_QUARTERS = {
    '2007-12-31', '2008-03-31', '2008-06-30', '2008-09-30',
    '2008-12-31', '2009-03-31', '2009-06-30',
    '2020-03-31', '2020-06-30',
    '2011-09-30', '2011-12-31', '2012-03-31', '2012-06-30',
}

FEATURE_NAMES = ['loan_to_asset', 'equity_ratio', 'npl_ratio',
                 'roa', 'funding_cost']

CALIB_END = '2007-09-30'   # last quarter of calm calibration window

# CALIBRATED thresholds (from calibrate_thresholds.py sweep)
PCTL_SWEEP  = [99, 95, 93, 90, 85]   # percentile thresholds to evaluate
Z_SWEEP     = [2.0, 1.5, 1.25, 1.0, 0.75]
P_SWEEP     = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]


# ==================================================================
#  ENGINE CONFIGS (pure unsupervised -- NO crisis labels, ever)
# ==================================================================
ENGINES = {
    'ReducedTensor': (ReducedTensorEngine, dict(
        k_neighbors=20, n_eigs=None,
    )),
    'MDN_Tensor': (MDNTensorEngine, dict(
        standardize=True,
    )),
    'QuadSurf': (QuadSurfEngine, dict(
        k=20,
    )),
}


# ==================================================================
#  LOAD DATA
# ==================================================================
def load_panel():
    """Load the real G-SIB panel and metadata."""
    npz = np.load(os.path.join(CACHE_DIR, 'gsib_real_panel.npz'))
    X_3d = npz['X']
    with open(os.path.join(CACHE_DIR, 'gsib_real_meta.json'), encoding='utf-8') as f:
        meta = json.load(f)
    N_meta = len(meta)
    if X_3d.shape[1] > N_meta:
        X_3d = X_3d[:, :N_meta, :]
    dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:X_3d.shape[0]]
    return X_3d, meta, dates


def _load_wb_json(filename):
    path = os.path.join(CACHE_DIR, filename)
    if not os.path.exists(path):
        return pd.Series(dtype=float)
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    s = pd.Series(raw, dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def build_nigeria_panel(dates):
    """Build Nigeria banking-sector features from cached WB data."""
    wb_map = {
        'loan_to_asset': 'wb_NGA_GFDD.DI.01.json',
        'equity_ratio':  'wb_NGA_FB.BNK.CAPA.ZS.json',
        'npl_ratio':     'wb_NGA_FB.AST.NPER.ZS.json',
        'roa':           'wb_NGA_GFDD.SI.01.json',
        'funding_cost':  'wb_NGA_FR.INR.LEND.json',
    }
    T = len(dates)
    X = np.full((T, 1, 5), np.nan)
    for feat_idx, (feat_name, fname) in enumerate(wb_map.items()):
        s = _load_wb_json(fname)
        if len(s) == 0 and feat_name == 'funding_cost':
            s = _load_wb_json('wb_NGA_FR.INR.DPST.json')
        if len(s) == 0:
            continue
        s_q = s.resample('QE').interpolate(method='linear')
        for t, dt in enumerate(dates):
            nearest = s_q.index[s_q.index <= dt]
            if len(nearest) > 0:
                X[t, 0, feat_idx] = s_q.loc[nearest[-1]]
    cov = float((~np.isnan(X)).mean())
    print(f'  Nigeria WB coverage: {cov:.1%}')
    return X


def subset_by_region(X_3d, meta, region_filter):
    indices = []
    for i, b in enumerate(meta):
        if 'names' in region_filter:
            if b['name'] in region_filter['names']:
                indices.append(i); continue
        if 'iso' in region_filter:
            if b['iso'] in region_filter['iso']:
                indices.append(i); continue
    if not indices:
        return None, []
    return X_3d[:, indices, :], [meta[i]['name'] for i in indices]


# ==================================================================
#  REGIONS
# ==================================================================
REGIONS = {
    'Full G-SIB Panel':  {},
    'USA (FDIC)':        {'iso': ['USA']},
    'Europe + UK':       {'iso': ['GBR', 'FRA', 'DEU', 'ITA', 'NLD']},
    'Asia (JP + CN)':    {'iso': ['JPN', 'CHN']},
    'Nigeria (WB-GFDD)': {'iso': ['NGA']},
}


# ==================================================================
#  PROSPECTIVE SCORING (from bench_bank_level_prospective.py)
#  + saves model artifacts
# ==================================================================
def prospective_score(X_3d_sub, dates, engine_cls, engine_kwargs,
                      region_name, eng_name, verbose=False):
    """Strictly prospective scoring -- no future data leaks.
    Saves fitted engine + score arrays as artifacts.

    Protocol:
      Phase 1: Fit on calibration window (2005-Q1 to 2007-Q3), y=0 always
               Extract per-quarter mean scores
      Phase 2: Expanding window (2007-Q4 onward)
               Fit on ALL data up to quarter t, y=0 always
               Score = mean of last N entries (current quarter's banks)
    """
    T, N, d = X_3d_sub.shape
    calib_end_dt = pd.Timestamp(CALIB_END)
    n_calib = int((dates <= calib_end_dt).sum())

    quarter_scores = np.full(T, np.nan)
    bank_scores_all = np.full((T, N), np.nan)  # per-bank scores each quarter

    # -- Phase 1: Calibration window --
    X_calib = X_3d_sub[:n_calib].reshape(n_calib * N, d)
    X_calib = np.nan_to_num(X_calib, nan=0.0)
    y_calib = np.zeros(n_calib * N, dtype=int)  # NO labels

    eng = engine_cls(**engine_kwargs)
    scores_calib = eng.fit_score(X_calib, y_calib)

    for t in range(n_calib):
        bs = scores_calib[t * N:(t + 1) * N]
        bank_scores_all[t, :] = bs
        quarter_scores[t] = float(bs.mean())

    if verbose:
        print(f'    Calibration: {dates[0].date()} to {dates[n_calib-1].date()} '
              f'({n_calib} quarters)')

    # Save calibration engine as artifact
    artifact_subdir = os.path.join(
        ARTIFACT_DIR,
        region_name.replace(' ', '_').replace('(', '').replace(')', ''),
        eng_name)
    os.makedirs(artifact_subdir, exist_ok=True)
    try:
        with open(os.path.join(artifact_subdir, 'engine_calib.pkl'), 'wb') as f:
            pickle.dump(eng, f)
    except Exception as e:
        print(f'    [WARN] Could not pickle calib engine: {e}')

    del eng; gc.collect()

    # -- Phase 2: Expanding window (2007-Q4 onward) --
    last_eng = None
    for t in range(n_calib, T):
        n_pts = (t + 1) * N
        X_up_to_t = X_3d_sub[:t + 1].reshape(n_pts, d)
        X_up_to_t = np.nan_to_num(X_up_to_t, nan=0.0)
        y_dummy = np.zeros(n_pts, dtype=int)  # NO labels -- ever

        eng = engine_cls(**engine_kwargs)
        scores_all = eng.fit_score(X_up_to_t, y_dummy)

        # Current quarter's score = mean of last N entries
        bs_t = scores_all[-N:]
        bank_scores_all[t, :] = bs_t
        quarter_scores[t] = float(bs_t.mean())

        if last_eng is not None:
            del last_eng
        last_eng = eng
        gc.collect()

    # Save final (most recent) fitted engine
    if last_eng is not None:
        try:
            with open(os.path.join(artifact_subdir, 'engine_final.pkl'), 'wb') as f:
                pickle.dump(last_eng, f)
        except Exception as e:
            print(f'    [WARN] Could not pickle final engine: {e}')
        del last_eng; gc.collect()

    # Save raw score arrays
    np.savez_compressed(
        os.path.join(artifact_subdir, 'scores.npz'),
        quarter_scores=quarter_scores,
        bank_scores=bank_scores_all,
        dates=np.array([str(d.date()) for d in dates]),
        n_calib=np.array(n_calib),
    )

    return quarter_scores, bank_scores_all, n_calib


# ==================================================================
#  DERIVE Z-SCORES AND P-VALUES
# ==================================================================
def derive_channels(q_scores, n_calib):
    """Compute rolling z-scores and conformal p-values."""
    T = len(q_scores)
    valid = ~np.isnan(q_scores)

    # Rolling z-scores (expanding window)
    z_scores = np.full(T, np.nan)
    for t in range(4, T):
        if not valid[t]:
            continue
        past = q_scores[:t][valid[:t]]
        if len(past) < 4:
            continue
        mu, sig = past.mean(), past.std()
        if sig < 1e-10:
            continue
        z_scores[t] = (q_scores[t] - mu) / sig

    # Conformal p-values
    cal = q_scores[:n_calib]
    cal = cal[~np.isnan(cal)]
    cal_sorted = np.sort(cal)
    n_cal = len(cal_sorted)

    p_values = np.full(T, np.nan)
    for t in range(T):
        if not valid[t]:
            continue
        rank = n_cal - np.searchsorted(cal_sorted, q_scores[t], side='left')
        p_values[t] = (1 + rank) / (n_cal + 1)

    return z_scores, p_values, cal_sorted


# ==================================================================
#  EVALUATE AT SPECIFIC THRESHOLDS
# ==================================================================
def eval_at_alarm(scores, alarm_mask, y_crisis, dates, flip_for_auroc=False):
    """Compute AUROC, GFC-AUC, confusion matrix at a given alarm mask."""
    T = len(dates)
    valid = ~np.isnan(scores)
    crisis = y_crisis.astype(bool)

    y_v = y_crisis[valid]
    s_v = -scores[valid] if flip_for_auroc else scores[valid]
    auroc = roc_auc_score(y_v, s_v) if 0 < y_v.sum() < len(y_v) else float('nan')

    # GFC-specific AUROC
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


def sweep_thresholds(q_scores, z_scores, p_values, n_calib, dates, y_crisis):
    """Sweep all three channels across calibrated threshold grids."""
    T = len(dates)
    valid_q = ~np.isnan(q_scores)
    valid_z = ~np.isnan(z_scores)
    valid_p = ~np.isnan(p_values)
    calib_q = q_scores[:n_calib]
    calib_q = calib_q[~np.isnan(calib_q)]

    results = {'percentile': [], 'z_score': [], 'p_value': []}

    for pctl in PCTL_SWEEP:
        thresh = float(np.percentile(calib_q, pctl)) if len(calib_q) > 2 else 1e10
        alarm = np.zeros(T, dtype=bool)
        alarm[valid_q] = q_scores[valid_q] > thresh
        r = eval_at_alarm(q_scores, alarm, y_crisis, dates)
        r['pctl'] = pctl; r['threshold'] = thresh
        results['percentile'].append(r)

    for z_th in Z_SWEEP:
        alarm = np.zeros(T, dtype=bool)
        alarm[valid_z] = z_scores[valid_z] > z_th
        r = eval_at_alarm(z_scores, alarm, y_crisis, dates)
        r['z_thresh'] = z_th
        results['z_score'].append(r)

    for p_th in P_SWEEP:
        alarm = np.zeros(T, dtype=bool)
        alarm[valid_p] = p_values[valid_p] < p_th
        r = eval_at_alarm(-p_values, alarm, y_crisis, dates, flip_for_auroc=False)
        r['p_thresh'] = p_th
        results['p_value'].append(r)

    return results


# ==================================================================
#  MAIN
# ==================================================================
def main():
    print('=' * 80)
    print('  INTERNATIONAL BANKING BENCHMARK -- Prospective Early Warning')
    print('  Pipeline: bench_bank_level_prospective.py protocol')
    print('  Protocol: expanding-window, NO labels, pure unsupervised')
    print('  Calibration: sweep percentile / z-score / p-value thresholds')
    print('  Artifacts: engine pickles + raw scores saved to disk')
    print('=' * 80)

    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    X_3d, meta, dates = load_panel()
    T, N, d = X_3d.shape
    y_crisis = np.array([1 if str(dt.date()) in CRISIS_QUARTERS else 0
                         for dt in dates])

    print(f'\n  Panel: T={T}, N={N}, d={d}')
    print(f'  Features: {FEATURE_NAMES}')
    print(f'  Crisis quarters: {int(y_crisis.sum())}/{T}')
    print(f'  Artifacts dir: {ARTIFACT_DIR}')

    all_results = {}

    for region_name, region_filter in REGIONS.items():
        print(f'\n\n{"=" * 78}')
        print(f'  REGION: {region_name}')
        print(f'{"=" * 78}')

        if region_name == 'Nigeria (WB-GFDD)':
            X_sub = build_nigeria_panel(dates)
            bank_names = ['Nigeria Banking Sector']
        elif region_filter:
            X_sub, bank_names = subset_by_region(X_3d, meta, region_filter)
        else:
            X_sub = X_3d
            bank_names = [b['name'] for b in meta]

        if X_sub is None or len(bank_names) == 0:
            print(f'  [SKIP] No banks matched')
            continue

        nan_pct = np.isnan(X_sub).mean() * 100
        print(f'  Banks ({len(bank_names)}): {", ".join(bank_names)}')
        print(f'  Shape: {X_sub.shape}, NaN: {nan_pct:.1f}%')

        region_results = {}

        for eng_name, (eng_cls, eng_kwargs) in ENGINES.items():
            print(f'\n  -- {eng_name} --', flush=True)
            t0 = time.time()

            try:
                q_scores, bank_scores, n_calib = prospective_score(
                    X_sub, dates, eng_cls, eng_kwargs,
                    region_name, eng_name, verbose=True)
                elapsed = time.time() - t0
                print(f'     Expanding window: {elapsed:.0f}s', flush=True)

                # Derive z-scores and p-values
                z_scores, p_values, cal_sorted = derive_channels(
                    q_scores, n_calib)

                # Save derived channels as artifacts
                art_dir = os.path.join(
                    ARTIFACT_DIR,
                    region_name.replace(' ', '_').replace('(', '').replace(')', ''),
                    eng_name)
                np.savez_compressed(
                    os.path.join(art_dir, 'channels.npz'),
                    z_scores=z_scores,
                    p_values=p_values,
                    cal_sorted=cal_sorted,
                )

                # Sweep thresholds
                sweep = sweep_thresholds(
                    q_scores, z_scores, p_values,
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
                    cands = [r for r in ch_data
                             if r['far'] < 25 and not np.isnan(r['f1']) and r['f1'] > 0]
                    if not cands:
                        cands = [r for r in ch_data
                                 if not np.isnan(r['f1']) and r['f1'] > 0]
                    if cands:
                        best_r = max(cands, key=lambda x: x['f1'])
                        best[ch_name] = best_r
                        print(f'\n     >> BEST {ch_name}: '
                              f'{param_key}={best_r[param_key]}  '
                              f'F1={best_r["f1"]:.1f}  '
                              f'Recall={best_r["recall"]:.1f}%  '
                              f'Prec={best_r["prec"]:.1f}%  '
                              f'FAR={best_r["far"]:.1f}%  '
                              f'GFC-AUC={best_r["auroc_gfc"]:.4f}')
                    else:
                        print(f'\n     >> BEST {ch_name}: no valid operating point')

                region_results[eng_name] = {
                    'sweep': sweep,
                    'best': best,
                    'time': elapsed,
                }

                # Save calibration config as artifact
                calib_config = {
                    'region': region_name,
                    'engine': eng_name,
                    'n_calib': int(n_calib),
                    'best_thresholds': {},
                    'time_seconds': elapsed,
                    'banks': bank_names,
                }
                for ch_name, best_r in best.items():
                    calib_config['best_thresholds'][ch_name] = {
                        k: v for k, v in best_r.items()
                        if k in ('pctl', 'z_thresh', 'p_thresh', 'threshold',
                                 'f1', 'recall', 'prec', 'far', 'auroc',
                                 'auroc_gfc', 'first_alarm', 'gfc_lead')
                    }
                def sanitize_val(o):
                    if isinstance(o, (np.integer,)):  return int(o)
                    if isinstance(o, (np.floating,)): return float(o)
                    if isinstance(o, float) and np.isnan(o): return None
                    return o
                calib_clean = json.loads(json.dumps(calib_config, default=sanitize_val))
                with open(os.path.join(art_dir, 'calibration.json'), 'w') as f:
                    json.dump(calib_clean, f, indent=2)

            except Exception as e:
                print(f'     ERROR: {type(e).__name__}: {e}')
                import traceback; traceback.print_exc(limit=5)
                region_results[eng_name] = {'error': str(e)}

        all_results[region_name] = region_results

    # ==============================================================
    #  FINAL SUMMARY: Best operating point per region
    # ==============================================================
    print('\n\n' + '=' * 100)
    print('  OPTIMAL CALIBRATION -- EXPANDING WINDOW (Prospective, Unsupervised)')
    print('  Criterion: max F1 with FAR < 25%')
    print('=' * 100)

    for region_name in REGIONS:
        if region_name not in all_results:
            continue
        print(f'\n  {region_name}:')
        for eng_name in ENGINES:
            rr = all_results[region_name].get(eng_name, {})
            if 'error' in rr or 'best' not in rr:
                print(f'    {eng_name:<12s}  ERROR')
                continue
            best_overall = None
            best_f1 = -1
            for ch_name, r in rr['best'].items():
                if r.get('f1', 0) > best_f1:
                    best_f1 = r['f1']
                    best_overall = (ch_name, r)
            if best_overall:
                ch, r = best_overall
                gfc_str = f'{r.get("auroc_gfc", 0):.4f}'
                lead = r.get('gfc_lead') or 'none'
                print(f'    {eng_name:<12s}  Ch={ch:<12s}  '
                      f'F1={r["f1"]:.1f}  '
                      f'AUROC={r["auroc"]:.4f}  '
                      f'GFC={gfc_str}  '
                      f'Recall={r["recall"]:.1f}%  '
                      f'Prec={r["prec"]:.1f}%  '
                      f'FAR={r["far"]:.1f}%  '
                      f'Lead={lead}')

    # Save summary JSON
    results_path = os.path.join(ROOT, 'international_bank_benchmark_extended.json')
    def sanitize(obj):
        if isinstance(obj, (np.integer,)):   return int(obj)
        if isinstance(obj, (np.floating,)):  return float(obj)
        if isinstance(obj, np.ndarray):      return obj.tolist()
        if isinstance(obj, float) and np.isnan(obj): return None
        return obj
    clean = json.loads(json.dumps(all_results, default=sanitize))
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(clean, f, indent=2)
    print(f'\n  Results JSON: {results_path}')
    print(f'  Artifacts:    {ARTIFACT_DIR}')

    # List artifacts
    print('\n  Saved artifacts:')
    for root_dir, dirs, files in os.walk(ARTIFACT_DIR):
        for fn in files:
            fp = os.path.join(root_dir, fn)
            sz = os.path.getsize(fp) / 1024
            rel = os.path.relpath(fp, ARTIFACT_DIR)
            print(f'    {rel:<60s}  {sz:7.1f} KB')

    print('\nDone.')


if __name__ == '__main__':
    main()
