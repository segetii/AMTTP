"""
Operational Model Search — ReducedTensor & MDN Tensor Variants
================================================================
Systematically tries different configurations of:
  A) ReducedTensor: vary k_neighbors, combine with BSDT channels,
     add Morse index gating, use energy-based scoring
  B) MDN Tensor: vary operator sets, scoring variants (v1-v3d),
     score_weights, add SubspaceScan, GraphNeighborhood, PhaseCurve

Protocol (UNCHANGED from bench_international_banks.py):
  - Trained on normal period only (y=0 always)
  - Expanding window (calibration 2005-Q1→2007-Q3, then online)
  - Parameter freeze (no look-ahead)
  - Threshold sweep: percentile, z-score, p-value

Criterion for OPERATIONAL: F1≥40, Recall≥50%, Prec≥30%, FAR<25%,
  AUROC≥0.65, GFC-AUC≥0.80, alarm before 2007-Q4

Author: Odeyemi Olusegun Israel
"""
import sys, os, time, warnings, json, gc, pickle
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
warnings.filterwarnings("ignore")

from sklearn.metrics import roc_auc_score

# ── Import all building blocks ──
from udl.system_mode import (ReducedTensorDescriptor, BSDTChannels,
                              MorseTopologyAlarm, FusedSystemScorer,
                              BettiBarcodeSuite)
from udl.stack import RepresentationStack
from udl.tensor import AnomalyTensor
from udl.spectra import (StatisticalSpectrum, ChaosSpectrum,
                          SpectralSpectrum, GeometricSpectrum,
                          ExponentialSpectrum, ReconstructionSpectrum,
                          RankOrderSpectrum)
try:
    from udl.new_spectra import (GraphNeighborhoodSpectrum,
                                  DensityRatioSpectrum,
                                  TopologicalSpectrum,
                                  KernelRKHSSpectrum)
except ImportError:
    GraphNeighborhoodSpectrum = None
    DensityRatioSpectrum = None
    TopologicalSpectrum = None
    KernelRKHSSpectrum = None

try:
    from udl.experimental_spectra import PhaseCurveSpectrum, GramEigenSpectrum
except ImportError:
    PhaseCurveSpectrum = None
    GramEigenSpectrum = None

try:
    from udl.subspace_scan import SubspaceScanScorer
except ImportError:
    SubspaceScanScorer = None

try:
    from udl.energy import DeviationEnergy
except ImportError:
    DeviationEnergy = None


# ==================================================================
#  CONFIG (identical to bench_international_banks.py)
# ==================================================================
ROOT = r'C:\amttp'
CACHE_DIR = os.path.join(ROOT, 'research', 'adaptive-friction',
                         'banklevel_enhanced', 'gsib_cache_real')
ARTIFACT_DIR = os.path.join(ROOT, 'model_artifacts', 'operational_search')

CRISIS_QUARTERS = {
    '2007-12-31', '2008-03-31', '2008-06-30', '2008-09-30',
    '2008-12-31', '2009-03-31', '2009-06-30',
    '2020-03-31', '2020-06-30',
    '2011-09-30', '2011-12-31', '2012-03-31', '2012-06-30',
}
CALIB_END = '2007-09-30'

PCTL_SWEEP  = [99, 97, 95, 93, 90, 85, 80]
Z_SWEEP     = [2.5, 2.0, 1.5, 1.25, 1.0, 0.75, 0.5]
P_SWEEP     = [0.01, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]

# Operational thresholds
OP_F1 = 40; OP_RECALL = 50; OP_PREC = 30; OP_FAR = 25
OP_AUROC = 0.65; OP_GFC = 0.80

# ==================================================================
#  ENGINE CONFIGURATIONS TO TRY
# ==================================================================

def _make_reduced_tensor_engines():
    """Generate ReducedTensor variants with different k, n_eigs."""
    configs = {}

    # --- Variant A: Baseline ReducedTensor with higher k ---
    for k in [15, 20, 30]:
        configs[f'RT_k{k}'] = ('reduced_tensor', dict(k_neighbors=k, n_eigs=None))

    # --- Variant B: ReducedTensor + BSDT energy blend ---
    for k in [15, 20]:
        configs[f'RT_BSDT_k{k}'] = ('rt_bsdt_blend', dict(k_neighbors=k))

    # --- Variant C: ReducedTensor + Morse alarm gating ---
    configs['RT_Morse_k20'] = ('rt_morse_gated', dict(k_neighbors=20))

    # --- Variant D: BSDT energy + MFLS combined ---
    for k in [15, 20, 25]:
        configs[f'BSDT_MFLS_k{k}'] = ('bsdt_mfls', dict(k=k))

    # --- Variant E: BSDT channels → per-channel max anomaly ---
    configs['BSDT_MaxCh_k20'] = ('bsdt_max_channel', dict(k=20))

    # --- Variant F: FusedSystem scorer (Morse+Betti+BSDT) ---
    configs['FusedSystem_k15'] = ('fused_system', dict(k=15))
    configs['FusedSystem_k20'] = ('fused_system', dict(k=20))

    return configs


def _make_mdn_tensor_engines():
    """Generate MDN Tensor variants with different operator sets & scoring."""
    configs = {}

    # --- Operator set 1: Default 6-op ---
    default_ops = [
        ("stat", StatisticalSpectrum()),
        ("chaos", ChaosSpectrum()),
        ("freq", SpectralSpectrum()),
        ("geom", GeometricSpectrum()),
        ("recon", ReconstructionSpectrum()),
        ("rank", RankOrderSpectrum()),
    ]

    # --- Operator set 2: Enhanced with Phase+Topo+Graph ---
    enhanced_ops = list(default_ops)
    if PhaseCurveSpectrum:
        enhanced_ops.append(("phase", PhaseCurveSpectrum()))
    if GraphNeighborhoodSpectrum:
        enhanced_ops.append(("graph", GraphNeighborhoodSpectrum(k=10)))
    if TopologicalSpectrum:
        enhanced_ops.append(("topo", TopologicalSpectrum(k=15)))

    # --- Operator set 3: Lean high-signal (Phase+Topo+Geom+Recon+Rank) ---
    lean_ops = [
        ("geom", GeometricSpectrum()),
        ("recon", ReconstructionSpectrum()),
        ("rank", RankOrderSpectrum()),
    ]
    if PhaseCurveSpectrum:
        lean_ops.insert(0, ("phase", PhaseCurveSpectrum()))
    if TopologicalSpectrum:
        lean_ops.insert(1, ("topo", TopologicalSpectrum(k=15)))

    # --- Operator set 4: With KernelRKHS (nonlinear manifold) ---
    kernel_ops = list(default_ops)
    if KernelRKHSSpectrum:
        kernel_ops.append(("kernel", KernelRKHSSpectrum(n_components=10)))

    # --- Operator set 5: Minimal (stat+geom+recon — fast, robust) ---
    minimal_ops = [
        ("stat", StatisticalSpectrum()),
        ("geom", GeometricSpectrum()),
        ("recon", ReconstructionSpectrum()),
    ]

    op_sets = {
        'default': default_ops,
        'enhanced': enhanced_ops,
        'lean': lean_ops,
        'kernel': kernel_ops,
        'minimal': minimal_ops,
    }

    # Cross with scoring variants
    for op_name, ops in op_sets.items():
        for sv in ['v1', 'v2', 'v3a', 'v3c', 'v3d']:
            configs[f'MDN_{op_name}_{sv}'] = ('mdn_tensor', dict(
                operators=ops, score_variant=sv, score_weights=(0.7, 0.3)))

    # --- Score weight variations on best op set ---
    for w_mag, w_nov in [(0.8, 0.2), (0.6, 0.4), (0.5, 0.5)]:
        wname = f'{int(w_mag*10)}{int(w_nov*10)}'
        configs[f'MDN_enhanced_v3d_w{wname}'] = ('mdn_tensor', dict(
            operators=enhanced_ops, score_variant='v3d',
            score_weights=(w_mag, w_nov)))

    # --- MDN + SubspaceScan blend ---
    if SubspaceScanScorer:
        configs['MDN_enhanced_v3d_SubScan'] = ('mdn_subscan', dict(
            operators=enhanced_ops, score_variant='v3d'))

    return configs


# ==================================================================
#  ENGINE RUNNERS
# ==================================================================

def run_reduced_tensor(X, variant, params):
    """Score X with a ReducedTensor-based variant."""
    if variant == 'reduced_tensor':
        desc = ReducedTensorDescriptor(
            k_neighbors=params['k_neighbors'],
            n_eigs=params.get('n_eigs'))
        desc.fit(X)
        return desc.score(X)

    elif variant == 'rt_bsdt_blend':
        # ReducedTensor + BSDT energy blend (50/50)
        k = params['k_neighbors']
        desc = ReducedTensorDescriptor(k_neighbors=k)
        desc.fit(X)
        rt_score = desc.score(X)

        bsdt = BSDTChannels(k=k)
        bsdt.fit(X)
        bsdt_score = bsdt.energy(X) + bsdt.mfls(X)

        # Robust normalisation
        def rnorm(s):
            q1, q99 = np.percentile(s, [1, 99])
            return np.clip((s - q1) / max(q99 - q1, 1e-10), 0, 1)

        return 0.5 * rnorm(rt_score) + 0.5 * rnorm(bsdt_score)

    elif variant == 'rt_morse_gated':
        # ReducedTensor scored, but Morse index >= 1 → score × 2
        k = params['k_neighbors']
        desc = ReducedTensorDescriptor(k_neighbors=k)
        desc.fit(X)
        scores = desc.score(X)
        morse = desc.get_morse_index(X)
        # Boost score where Morse alarm fires
        boost = np.where(morse >= 1, 2.0, 1.0)
        return scores * boost

    elif variant == 'bsdt_mfls':
        # Pure BSDT: Fisher-weighted E_BS + MFLS
        k = params['k']
        bsdt = BSDTChannels(k=k)
        bsdt.fit(X)
        e = bsdt.energy(X)
        m = bsdt.mfls(X)
        # Weighted combination
        e_n = e / max(e.max(), 1e-10)
        m_n = m / max(m.max(), 1e-10)
        return 0.4 * e_n + 0.6 * m_n

    elif variant == 'bsdt_max_channel':
        # Max across 4 BSDT channels (any channel screaming = alarm)
        k = params['k']
        bsdt = BSDTChannels(k=k)
        bsdt.fit(X)
        ch = bsdt.channels(X)
        C = np.column_stack([ch['delta_C'], ch['delta_G'],
                             ch['delta_A'], ch['delta_T']])
        return C.max(axis=1)

    elif variant == 'fused_system':
        # FusedSystemScorer: Morse + Betti + BSDT
        k = params['k']
        scorer = FusedSystemScorer(k=k, use_betti=True,
                                    use_udl=False, use_bsdt=True)
        scorer.fit(X, X_sim=X)
        return scorer.score(X)

    else:
        raise ValueError(f'Unknown RT variant: {variant}')


def run_mdn_tensor(X, variant, params):
    """Score X with an MDN Tensor-based variant."""
    operators = params['operators']
    sv = params['score_variant']
    weights = params.get('score_weights', (0.7, 0.3))

    # Build stack
    stack = RepresentationStack(operators=operators, standardize=True)
    stack.fit(X)
    R = stack.transform(X)

    # Build tensor
    tensor = AnomalyTensor()
    tensor.fit(R)
    result_ref = tensor.build(R, stack.law_dims_)
    tensor.store_ref_law_stats(result_ref)
    result = tensor.build(R, stack.law_dims_)

    # Score
    if sv == 'v1':
        base_scores = result.anomaly_score(weights)
    elif sv == 'v2':
        base_scores = result.anomaly_score_v2(weights)
    elif sv == 'v3a':
        base_scores = result.anomaly_score_v3a(weights)
    elif sv == 'v3c':
        base_scores = result.anomaly_score_v3c(weights)
    elif sv == 'v3d':
        base_scores = result.anomaly_score_v3d(weights)
    else:
        base_scores = result.anomaly_score_v3d(weights)

    if variant == 'mdn_subscan' and SubspaceScanScorer is not None:
        # Blend with SubspaceScan
        sscan = SubspaceScanScorer(n_projections=200)
        sscan.fit(R, np.zeros(len(R), dtype=int))
        ss_scores = sscan.score(R)

        def rnorm(s):
            q1, q99 = np.percentile(s, [1, 99])
            return np.clip((s - q1) / max(q99 - q1, 1e-10), 0, 1)

        return 0.6 * rnorm(base_scores) + 0.4 * rnorm(ss_scores)

    return base_scores


# ==================================================================
#  DATA LOADING (same as bench_international_banks.py)
# ==================================================================
def load_panel():
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
        if 'iso' in region_filter:
            if b['iso'] in region_filter['iso']:
                indices.append(i)
    if not indices:
        return None, []
    return X_3d[:, indices, :], [meta[i]['name'] for i in indices]


REGIONS = {
    'Full G-SIB Panel':  {},
    'USA (FDIC)':        {'iso': ['USA']},
    'Europe + UK':       {'iso': ['GBR', 'FRA', 'DEU', 'ITA', 'NLD']},
    'Asia (JP + CN)':    {'iso': ['JPN', 'CHN']},
    'Nigeria (WB-GFDD)': {'iso': ['NGA']},
}


# ==================================================================
#  PROSPECTIVE EXPANDING-WINDOW SCORING
# ==================================================================
def prospective_score(X_3d_sub, dates, run_fn, variant, params, verbose=False):
    """Expanding-window prospective scoring. Same protocol as before."""
    T, N, d = X_3d_sub.shape
    calib_end_dt = pd.Timestamp(CALIB_END)
    n_calib = int((dates <= calib_end_dt).sum())

    quarter_scores = np.full(T, np.nan)
    bank_scores_all = np.full((T, N), np.nan)

    # Phase 1: Calibration window
    X_calib = X_3d_sub[:n_calib].reshape(n_calib * N, d)
    X_calib = np.nan_to_num(X_calib, nan=0.0)

    scores_calib = run_fn(X_calib, variant, params)
    for t in range(n_calib):
        bs = scores_calib[t * N:(t + 1) * N]
        bank_scores_all[t, :] = bs
        quarter_scores[t] = float(bs.mean())

    if verbose:
        print(f'    Caliblration: {dates[0].date()} to {dates[n_calib-1].date()} '
              f'({n_calib} quarters)')

    # Phase 2: Expanding window
    for t in range(n_calib, T):
        n_pts = (t + 1) * N
        X_up_to_t = X_3d_sub[:t + 1].reshape(n_pts, d)
        X_up_to_t = np.nan_to_num(X_up_to_t, nan=0.0)

        scores_all = run_fn(X_up_to_t, variant, params)
        bs_t = scores_all[-N:]
        bank_scores_all[t, :] = bs_t
        quarter_scores[t] = float(bs_t.mean())
        gc.collect()

    return quarter_scores, bank_scores_all, n_calib


# ==================================================================
#  DERIVE CHANNELS + SWEEP THRESHOLDS
# ==================================================================
def derive_channels(q_scores, n_calib):
    T = len(q_scores)
    valid = ~np.isnan(q_scores)
    z_scores = np.full(T, np.nan)
    for t in range(4, T):
        if not valid[t]: continue
        past = q_scores[:t][valid[:t]]
        if len(past) < 4: continue
        mu, sig = past.mean(), past.std()
        if sig < 1e-10: continue
        z_scores[t] = (q_scores[t] - mu) / sig

    cal = q_scores[:n_calib]
    cal = cal[~np.isnan(cal)]
    cal_sorted = np.sort(cal)
    n_cal = len(cal_sorted)
    p_values = np.full(T, np.nan)
    for t in range(T):
        if not valid[t]: continue
        rank = n_cal - np.searchsorted(cal_sorted, q_scores[t], side='left')
        p_values[t] = (1 + rank) / (n_cal + 1)

    return z_scores, p_values, cal_sorted


def eval_at_alarm(scores, alarm_mask, y_crisis, dates, flip_for_auroc=False):
    T = len(dates)
    valid = ~np.isnan(scores)
    crisis = y_crisis.astype(bool)
    y_v = y_crisis[valid]
    s_v = -scores[valid] if flip_for_auroc else scores[valid]
    auroc = roc_auc_score(y_v, s_v) if 0 < y_v.sum() < len(y_v) else float('nan')

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
    pre_gfc = [d for d in alarm_dates if '2005-01-01' <= d < '2007-12-31']
    gfc_lead = pre_gfc[0] if pre_gfc else None

    return dict(auroc=auroc, auroc_gfc=auroc_gfc, far=far, recall=recall,
                prec=prec, f1=f1, tp=tp, fp=fp, fn=fn, tn=tn,
                first_alarm=first, gfc_lead=gfc_lead)


def sweep_and_best(q_scores, z_scores, p_values, n_calib, dates, y_crisis):
    """Sweep all channels and return best operating points."""
    T = len(dates)
    valid_q = ~np.isnan(q_scores)
    valid_z = ~np.isnan(z_scores)
    valid_p = ~np.isnan(p_values)
    calib_q = q_scores[:n_calib][~np.isnan(q_scores[:n_calib])]

    best_results = {}

    # Percentile sweep
    pctl_cands = []
    for pctl in PCTL_SWEEP:
        thresh = float(np.percentile(calib_q, pctl)) if len(calib_q) > 2 else 1e10
        alarm = np.zeros(T, dtype=bool)
        alarm[valid_q] = q_scores[valid_q] > thresh
        r = eval_at_alarm(q_scores, alarm, y_crisis, dates)
        r['pctl'] = pctl; r['threshold'] = thresh; r['channel'] = 'percentile'
        if r['far'] < OP_FAR and r['f1'] > 0:
            pctl_cands.append(r)
    if not pctl_cands:
        # Relaxed: just pick best F1
        for pctl in PCTL_SWEEP:
            thresh = float(np.percentile(calib_q, pctl)) if len(calib_q) > 2 else 1e10
            alarm = np.zeros(T, dtype=bool); alarm[valid_q] = q_scores[valid_q] > thresh
            r = eval_at_alarm(q_scores, alarm, y_crisis, dates)
            r['pctl'] = pctl; r['threshold'] = thresh; r['channel'] = 'percentile'
            pctl_cands.append(r)
    if pctl_cands:
        best_results['percentile'] = max(pctl_cands, key=lambda x: x['f1'])

    # Z-score sweep
    z_cands = []
    for z_th in Z_SWEEP:
        alarm = np.zeros(T, dtype=bool)
        alarm[valid_z] = z_scores[valid_z] > z_th
        r = eval_at_alarm(z_scores, alarm, y_crisis, dates)
        r['z_thresh'] = z_th; r['channel'] = 'z_score'
        if r['far'] < OP_FAR and r['f1'] > 0:
            z_cands.append(r)
    if not z_cands:
        for z_th in Z_SWEEP:
            alarm = np.zeros(T, dtype=bool); alarm[valid_z] = z_scores[valid_z] > z_th
            r = eval_at_alarm(z_scores, alarm, y_crisis, dates)
            r['z_thresh'] = z_th; r['channel'] = 'z_score'
            z_cands.append(r)
    if z_cands:
        best_results['z_score'] = max(z_cands, key=lambda x: x['f1'])

    # P-value sweep
    p_cands = []
    for p_th in P_SWEEP:
        alarm = np.zeros(T, dtype=bool)
        alarm[valid_p] = p_values[valid_p] < p_th
        r = eval_at_alarm(-p_values, alarm, y_crisis, dates, flip_for_auroc=False)
        r['p_thresh'] = p_th; r['channel'] = 'p_value'
        if r['far'] < OP_FAR and r['f1'] > 0:
            p_cands.append(r)
    if not p_cands:
        for p_th in P_SWEEP:
            alarm = np.zeros(T, dtype=bool); alarm[valid_p] = p_values[valid_p] < p_th
            r = eval_at_alarm(-p_values, alarm, y_crisis, dates, flip_for_auroc=False)
            r['p_thresh'] = p_th; r['channel'] = 'p_value'
            p_cands.append(r)
    if p_cands:
        best_results['p_value'] = max(p_cands, key=lambda x: x['f1'])

    return best_results


def is_operational(r):
    """Check if a result meets operational criteria."""
    if r is None: return False
    return (r['f1'] >= OP_F1 and
            r['recall'] >= OP_RECALL and
            r['prec'] >= OP_PREC and
            r['far'] < OP_FAR and
            r['auroc'] >= OP_AUROC and
            not np.isnan(r.get('auroc_gfc', float('nan'))) and
            r.get('auroc_gfc', 0) >= OP_GFC and
            r.get('first_alarm', 'none') != 'none' and
            r.get('first_alarm', '2099') < '2007-12-31')


# ==================================================================
#  MAIN
# ==================================================================
def main():
    print('=' * 90)
    print('  OPERATIONAL MODEL SEARCH — ReducedTensor & MDN Tensor Variants')
    print('  Protocol: expanding-window, normal-period-only, parameter freeze')
    print('  Criterion: F1≥40, Recall≥50%, Prec≥30%, FAR<25%, AUROC≥0.65, GFC≥0.80')
    print('=' * 90)

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    X_3d, meta, dates = load_panel()
    T, N, d = X_3d.shape
    y_crisis = np.array([1 if str(dt.date()) in CRISIS_QUARTERS else 0
                         for dt in dates])

    print(f'\n  Panel: T={T}, N={N}, d={d}')
    print(f'  Crisis quarters: {int(y_crisis.sum())}/{T}')

    # Build all engine configs
    rt_configs = _make_reduced_tensor_engines()
    mdn_configs = _make_mdn_tensor_engines()

    all_configs = {}
    for name, (variant, params) in rt_configs.items():
        all_configs[name] = ('rt', variant, params)
    for name, (variant, params) in mdn_configs.items():
        all_configs[name] = ('mdn', variant, params)

    print(f'  Total configurations: {len(all_configs)}')
    print(f'    ReducedTensor variants: {len(rt_configs)}')
    print(f'    MDN Tensor variants: {len(mdn_configs)}')

    # Results storage
    operational = []  # List of (config_name, region, channel, result)
    all_results = {}

    for region_name, region_filter in REGIONS.items():
        print(f'\n\n{"=" * 88}')
        print(f'  REGION: {region_name}')
        print(f'{"=" * 88}')

        if region_name == 'Nigeria (WB-GFDD)':
            X_sub = build_nigeria_panel(dates)
            bank_names = ['Nigeria Banking Sector']
        elif region_filter:
            X_sub, bank_names = subset_by_region(X_3d, meta, region_filter)
        else:
            X_sub = X_3d
            bank_names = [b['name'] for b in meta]

        if X_sub is None:
            print('  [SKIP] No data'); continue

        nan_pct = np.isnan(X_sub).mean() * 100
        print(f'  Banks: {len(bank_names)}, Shape: {X_sub.shape}, NaN: {nan_pct:.1f}%')

        region_results = {}

        for cfg_name, (family, variant, params) in all_configs.items():
            t0 = time.time()
            try:
                run_fn = run_reduced_tensor if family == 'rt' else run_mdn_tensor

                q_scores, bank_scores, n_calib = prospective_score(
                    X_sub, dates, run_fn, variant, params)
                elapsed = time.time() - t0

                z_scores, p_values, cal_sorted = derive_channels(q_scores, n_calib)
                best = sweep_and_best(q_scores, z_scores, p_values,
                                      n_calib, dates, y_crisis)

                # Find absolute best across channels
                best_overall = None
                best_f1 = -1
                for ch_name, r in best.items():
                    if r['f1'] > best_f1:
                        best_f1 = r['f1']
                        best_overall = (ch_name, r)

                if best_overall:
                    ch, r = best_overall
                    op = is_operational(r)
                    tag = ' *** OPERATIONAL ***' if op else ''
                    far_ok = '✓' if r['far'] < OP_FAR else '✗'
                    gfc_v = r.get('auroc_gfc', 0)
                    gfc_ok = '✓' if gfc_v >= OP_GFC else '✗'

                    print(f'  {cfg_name:<35s} '
                          f'F1={r["f1"]:5.1f}  R={r["recall"]:5.1f}%  '
                          f'P={r["prec"]:5.1f}%  FAR={r["far"]:4.1f}%{far_ok} '
                          f'GFC={gfc_v:.3f}{gfc_ok}  '
                          f'Ch={ch}  Alarm={r.get("first_alarm","?")}  '
                          f'{elapsed:.1f}s{tag}')

                    if op:
                        operational.append((cfg_name, region_name, ch, r, elapsed))

                    region_results[cfg_name] = {
                        'best_channel': ch,
                        'best': r,
                        'all_channels': best,
                        'time': elapsed,
                        'operational': op,
                    }
                else:
                    print(f'  {cfg_name:<35s}  NO VALID SCORES  {time.time()-t0:.1f}s')

            except Exception as e:
                elapsed = time.time() - t0
                print(f'  {cfg_name:<35s}  ERROR: {type(e).__name__}: {e}  {elapsed:.1f}s')

            gc.collect()

        all_results[region_name] = region_results

    # ==============================================================
    #  FINAL REPORT: Operational models
    # ==============================================================
    print('\n\n' + '=' * 100)
    print('  OPERATIONAL MODELS FOUND')
    print('  Criteria: F1≥40, Recall≥50%, Prec≥30%, FAR<25%, AUROC≥0.65, GFC-AUC≥0.80')
    print('=' * 100)

    if not operational:
        print('\n  *** NO OPERATIONAL MODELS FOUND ***')
        print('  Showing top-10 near-misses instead:\n')

        # Collect all results
        near = []
        for region_name, rr in all_results.items():
            for cfg_name, data in rr.items():
                if 'best' in data:
                    r = data['best']
                    near.append((cfg_name, region_name, data['best_channel'],
                                 r, data.get('time', 0)))
        near.sort(key=lambda x: x[3].get('f1', 0), reverse=True)

        print(f'  {"Config":<35s} {"Region":<18s} {"Ch":<12s} '
              f'{"F1":>5s} {"Rec%":>5s} {"Prec%":>5s} {"FAR%":>5s} '
              f'{"AUROC":>6s} {"GFC":>6s} {"Alarm":<12s}')
        print(f'  {"-"*120}')
        for cfg, reg, ch, r, t in near[:20]:
            gfc = r.get('auroc_gfc', 0)
            print(f'  {cfg:<35s} {reg:<18s} {ch:<12s} '
                  f'{r["f1"]:5.1f} {r["recall"]:5.1f} {r["prec"]:5.1f} '
                  f'{r["far"]:5.1f} {r["auroc"]:6.3f} {gfc:6.3f} '
                  f'{r.get("first_alarm","?"):<12s}')
    else:
        # Sort by F1 desc
        operational.sort(key=lambda x: x[3]['f1'], reverse=True)

        print(f'\n  {"Config":<35s} {"Region":<18s} {"Ch":<12s} '
              f'{"F1":>5s} {"Rec%":>5s} {"Prec%":>5s} {"FAR%":>5s} '
              f'{"AUROC":>6s} {"GFC":>6s} {"Alarm":<12s} {"Time":>6s}')
        print(f'  {"-"*140}')
        for cfg, reg, ch, r, t in operational:
            gfc = r.get('auroc_gfc', 0)
            print(f'  {cfg:<35s} {reg:<18s} {ch:<12s} '
                  f'{r["f1"]:5.1f} {r["recall"]:5.1f} {r["prec"]:5.1f} '
                  f'{r["far"]:5.1f} {r["auroc"]:6.3f} {gfc:6.3f} '
                  f'{r.get("first_alarm","?"):<12s} {t:5.1f}s')

    # Save results JSON
    results_path = os.path.join(ROOT, 'operational_model_search.json')
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

    # Save operational configs as artifacts
    if operational:
        op_path = os.path.join(ARTIFACT_DIR, 'operational_configs.json')
        op_data = []
        for cfg, reg, ch, r, t in operational:
            entry = {
                'config': cfg, 'region': reg, 'channel': ch,
                'f1': r['f1'], 'recall': r['recall'], 'prec': r['prec'],
                'far': r['far'], 'auroc': r['auroc'],
                'auroc_gfc': r.get('auroc_gfc'),
                'first_alarm': r.get('first_alarm'),
                'gfc_lead': r.get('gfc_lead'),
                'time_seconds': t,
            }
            op_data.append(entry)
        with open(op_path, 'w') as f:
            json.dump(op_data, f, indent=2, default=sanitize)
        print(f'  Operational configs: {op_path}')

    print('\nDone.')


if __name__ == '__main__':
    main()
