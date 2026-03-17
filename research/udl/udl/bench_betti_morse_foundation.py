"""
Betti + Morse Foundation Benchmark
====================================
New approach: BettiBarcodeSuite + MorseTopologyAlarm form the
**foundational scoring layer** for every engine variant. All other
methods (BSDT, ReducedTensor, MDN Tensor, SubspaceScan, EnergyFlow)
are enrichment layers that build atop this foundation via Fisher VR
fusion.

LyapunovStabiliser is used STRICTLY for iteration control (Armijo
step acceptance, La Salle convergence, barrier force clamping) in
the EnergyFlow gradient-descent preprocessing — it NEVER contributes
to the final prediction score.

Protocol (UNCHANGED):
  - Trained on normal period only (y=0 always)
  - Expanding window (calibration 2005-Q1→2007-Q3, then online)
  - Parameter freeze (no look-ahead)
  - Threshold sweep: percentile, z-score, p-value

Criterion for OPERATIONAL: F1≥40, Recall≥50%, Prec≥30%, FAR<25%,
  AUROC≥0.65, GFC-AUC≥0.80, alarm before 2007-Q4

This is a NEW script — bench_operational.py and
bench_international_banks.py are untouched.

Author: Odeyemi Olusegun Israel
"""
import sys, os, time, warnings, json, gc
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
warnings.filterwarnings("ignore")

from sklearn.metrics import roc_auc_score

# ── Foundation imports ──
from udl.system_mode import (
    MorseTopologyAlarm,
    BettiBarcodeSuite,
    BSDTChannels,
    ReducedTensorDescriptor,
    FusedSystemScorer,
    LyapunovStabiliser,
)
from udl.stack import RepresentationStack
from udl.tensor import AnomalyTensor
from udl.spectra import (
    StatisticalSpectrum, ChaosSpectrum, SpectralSpectrum,
    GeometricSpectrum, ReconstructionSpectrum, RankOrderSpectrum,
)

# Optional enrichment imports
try:
    from udl.experimental_spectra import PhaseCurveSpectrum
except ImportError:
    PhaseCurveSpectrum = None
try:
    from udl.new_spectra import TopologicalSpectrum
except ImportError:
    TopologicalSpectrum = None
try:
    from udl.subspace_scan import SubspaceScanScorer
except ImportError:
    SubspaceScanScorer = None
try:
    from udl.energy import EnergyFlow
except ImportError:
    EnergyFlow = None


# ==================================================================
#  CONSTANTS (identical to bench_operational.py)
# ==================================================================
ROOT = r'C:\amttp'
CACHE_DIR = os.path.join(ROOT, 'research', 'adaptive-friction',
                         'banklevel_enhanced', 'gsib_cache_real')
ARTIFACT_DIR = os.path.join(ROOT, 'model_artifacts', 'betti_morse_foundation')

CRISIS_QUARTERS = {
    '2007-12-31', '2008-03-31', '2008-06-30', '2008-09-30',
    '2008-12-31', '2009-03-31', '2009-06-30',
    '2020-03-31', '2020-06-30',
    '2011-09-30', '2011-12-31', '2012-03-31', '2012-06-30',
}
CALIB_END = '2007-09-30'

PCTL_SWEEP = [99, 97, 95, 93, 90, 85, 80]
Z_SWEEP    = [2.5, 2.0, 1.5, 1.25, 1.0, 0.75, 0.5]
P_SWEEP    = [0.01, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]

OP_F1 = 40; OP_RECALL = 50; OP_PREC = 30; OP_FAR = 25
OP_AUROC = 0.65; OP_GFC = 0.80


# ==================================================================
#  FISHER VR FUSION  (same algorithm as FusedSystemScorer)
# ==================================================================
def _robust_norm(s):
    """Percentile [1, 99] normalization to [0, 1]."""
    q1, q99 = np.percentile(s, [1, 99])
    if q99 - q1 > 1e-15:
        return np.clip((s - q1) / (q99 - q1), 0.0, 1.0)
    return np.zeros_like(s)


def fisher_vr_fuse(views):
    """
    Fisher Variance-Ratio fusion across multiple score views.

    Each view is a 1-D array of length N. We split samples into
    high/low alarm groups (by total score p80/p50), then compute
    FR_v = (mu_hi - mu_lo)^2 / (var_hi + var_lo) per view. Weights
    are normalised FR values.

    Returns: fused scores (N,), weights (V,)
    """
    V = np.column_stack(views)          # (N, n_views)
    N, n_v = V.shape
    total = V.sum(axis=1)
    p80 = np.percentile(total, 80)
    p50 = np.percentile(total, 50)
    hi = total >= p80
    lo = total <= p50

    if hi.sum() < 3 or lo.sum() < 3:
        # Fallback: equal weights
        w = np.ones(n_v) / n_v
    else:
        fr = np.zeros(n_v)
        for j in range(n_v):
            mu_hi = V[hi, j].mean()
            mu_lo = V[lo, j].mean()
            var_hi = V[hi, j].var() + 1e-15
            var_lo = V[lo, j].var() + 1e-15
            fr[j] = (mu_hi - mu_lo) ** 2 / (var_hi + var_lo)

        s = fr.sum()
        w = fr / s if s > 1e-15 else np.ones(n_v) / n_v

    fused = (V * w[None, :]).sum(axis=1)
    return fused, w


# ==================================================================
#  FOUNDATION SCORER (Betti + Morse)
# ==================================================================
class BettiMorseFoundation:
    """
    The foundational scoring layer: always present in every config.

    1. MorseTopologyAlarm  → structural anomaly from Morse theory
    2. BettiBarcodeSuite   → persistent-homology proxies

    These are fused via Fisher VR to produce the base signal.
    Enrichment layers add additional views on top.
    """

    def __init__(self, k=15, n_scales=8):
        self.k = k
        self.morse = MorseTopologyAlarm(k=k)
        self.betti = BettiBarcodeSuite(k=min(k + 5, 25), n_scales=n_scales)
        self._fitted = False

    def fit(self, X_ref):
        self.morse.fit(X_ref)
        self.betti.fit(X_ref)
        self._fitted = True

    def score(self, X):
        """Return Morse scores, Betti scores, and fused foundation score."""
        m_scores = self.morse.score(X)
        b_scores = self.betti.score(X)
        m_norm = _robust_norm(m_scores)
        b_norm = _robust_norm(b_scores)
        fused, weights = fisher_vr_fuse([m_norm, b_norm])
        return fused, m_norm, b_norm, weights

    def score_views(self, X):
        """Return normalised views for downstream fusion."""
        m_scores = _robust_norm(self.morse.score(X))
        b_scores = _robust_norm(self.betti.score(X))
        return m_scores, b_scores


# ==================================================================
#  ENRICHMENT LAYER RUNNERS
# ==================================================================

def _enrich_none(X, foundation, params):
    """Variant A: Foundation-only (pure Betti + Morse)."""
    fused, _, _, _ = foundation.score(X)
    return fused


def _enrich_bsdt(X, foundation, params):
    """Variant B: Foundation + BSDT channels."""
    m_view, b_view = foundation.score_views(X)
    k = params.get('k', foundation.k)
    bsdt = BSDTChannels(k=k)
    bsdt.fit(X)
    bsdt_score = _robust_norm(bsdt.energy(X) + bsdt.mfls(X))
    fused, _ = fisher_vr_fuse([m_view, b_view, bsdt_score])
    return fused


def _enrich_reduced_tensor(X, foundation, params):
    """Variant C: Foundation + ReducedTensor descriptor score."""
    m_view, b_view = foundation.score_views(X)
    k = params.get('k', foundation.k)
    desc = ReducedTensorDescriptor(k_neighbors=k)
    desc.fit(X)
    rt_score = _robust_norm(desc.score(X))
    fused, _ = fisher_vr_fuse([m_view, b_view, rt_score])
    return fused


def _enrich_mdn_tensor(X, foundation, params):
    """Variant D: Foundation + MDN Tensor decomposition score."""
    m_view, b_view = foundation.score_views(X)

    operators = params.get('operators', None)
    sv = params.get('score_variant', 'v3d')
    weights = params.get('score_weights', (0.7, 0.3))

    if operators is None:
        operators = [
            ("stat", StatisticalSpectrum()),
            ("chaos", ChaosSpectrum()),
            ("freq", SpectralSpectrum()),
            ("geom", GeometricSpectrum()),
            ("recon", ReconstructionSpectrum()),
            ("rank", RankOrderSpectrum()),
        ]

    stack = RepresentationStack(operators=operators, standardize=True)
    stack.fit(X)
    R = stack.transform(X)

    tensor = AnomalyTensor()
    tensor.fit(R)
    result_ref = tensor.build(R, stack.law_dims_)
    tensor.store_ref_law_stats(result_ref)
    result = tensor.build(R, stack.law_dims_)

    score_fn = {
        'v1': lambda: result.anomaly_score(weights),
        'v3a': lambda: result.anomaly_score_v3a(weights),
        'v3c': lambda: result.anomaly_score_v3c(weights),
        'v3d': lambda: result.anomaly_score_v3d(weights),
    }
    raw = score_fn.get(sv, score_fn['v3d'])()
    mdn_score = _robust_norm(raw)

    fused, _ = fisher_vr_fuse([m_view, b_view, mdn_score])
    return fused


def _enrich_subscan(X, foundation, params):
    """Variant E: Foundation + SubspaceScan."""
    if SubspaceScanScorer is None:
        return _enrich_none(X, foundation, params)

    m_view, b_view = foundation.score_views(X)
    sscan = SubspaceScanScorer(n_projections=200)
    sscan.fit(X, np.zeros(len(X), dtype=int))
    ss_score = _robust_norm(sscan.score(X))
    fused, _ = fisher_vr_fuse([m_view, b_view, ss_score])
    return fused


def _enrich_full_fused(X, foundation, params):
    """Variant F: Foundation + BSDT + ReducedTensor (4-view)."""
    m_view, b_view = foundation.score_views(X)
    k = params.get('k', foundation.k)

    bsdt = BSDTChannels(k=k)
    bsdt.fit(X)
    bsdt_score = _robust_norm(bsdt.energy(X) + bsdt.mfls(X))

    desc = ReducedTensorDescriptor(k_neighbors=k)
    desc.fit(X)
    rt_score = _robust_norm(desc.score(X))

    fused, _ = fisher_vr_fuse([m_view, b_view, bsdt_score, rt_score])
    return fused


def _enrich_energy_flow(X, foundation, params):
    """
    Variant G: EnergyFlow preprocessing → Foundation scoring.

    LyapunovStabiliser controls ONLY the gradient-flow iteration:
      - clamp_forces(): barrier-smooth force limiting
      - accept_step(): Armijo descent certificate
      - check_convergence(): La Salle invariance termination

    It NEVER contributes to the final prediction score. After the
    flow converges, the repositioned points are scored by the
    Betti + Morse foundation.
    """
    n_iter = params.get('n_iter', 30)
    eta = params.get('eta', 0.01)
    alpha_radial = params.get('alpha_radial', 0.1)

    # --- Lyapunov-controlled gradient flow (iteration only) ---
    stabiliser = LyapunovStabiliser(
        armijo_c=1e-4,
        backtrack_rho=0.5,
        max_force_norm=10.0,
        min_eta=1e-6,
        la_salle_tol=1e-5,
        la_salle_patience=5,
    )
    stabiliser.reset()

    mu = X.mean(axis=0)
    X_flow = X.copy()
    current_eta = eta

    for it in range(n_iter):
        # Radial gradient toward centroid
        diff = X_flow - mu[None, :]
        grad = alpha_radial * diff

        # Clamp forces via Lyapunov barrier
        grad = stabiliser.clamp_forces(grad)

        # Compute energy before step
        E_old = 0.5 * alpha_radial * np.sum(diff ** 2)

        # Candidate step
        X_candidate = X_flow - current_eta * grad

        # Energy after
        diff_new = X_candidate - mu[None, :]
        E_new = 0.5 * alpha_radial * np.sum(diff_new ** 2)

        # Armijo check (Lyapunov ISS — iteration control only)
        grad_norm_sq = float(np.sum(grad ** 2))
        accepted, current_eta = stabiliser.accept_step(
            E_old, E_new, grad_norm_sq, current_eta
        )

        if accepted:
            displacement = float(np.max(np.abs(X_candidate - X_flow)))
            X_flow = X_candidate

            # La Salle convergence (Lyapunov — iteration control only)
            if stabiliser.check_convergence(grad_norm_sq, displacement):
                break
    # --- End of Lyapunov-controlled iteration ---
    # Lyapunov has NO role beyond this point — all scoring is Betti+Morse

    m_view, b_view = foundation.score_views(X_flow)
    fused, _ = fisher_vr_fuse([m_view, b_view])
    return fused


def _enrich_energy_flow_bsdt(X, foundation, params):
    """
    Variant H: EnergyFlow preprocessing → Foundation + BSDT.

    Same Lyapunov-controlled iteration as Variant G, but adds
    BSDT channels as a 3rd enrichment view after flow converges.
    """
    n_iter = params.get('n_iter', 30)
    eta = params.get('eta', 0.01)
    alpha_radial = params.get('alpha_radial', 0.1)
    k = params.get('k', foundation.k)

    stabiliser = LyapunovStabiliser(min_eta=1e-6)
    stabiliser.reset()

    mu = X.mean(axis=0)
    X_flow = X.copy()
    current_eta = eta

    for it in range(n_iter):
        diff = X_flow - mu[None, :]
        grad = alpha_radial * diff
        grad = stabiliser.clamp_forces(grad)
        E_old = 0.5 * alpha_radial * np.sum(diff ** 2)
        X_candidate = X_flow - current_eta * grad
        diff_new = X_candidate - mu[None, :]
        E_new = 0.5 * alpha_radial * np.sum(diff_new ** 2)
        grad_norm_sq = float(np.sum(grad ** 2))
        accepted, current_eta = stabiliser.accept_step(
            E_old, E_new, grad_norm_sq, current_eta)
        if accepted:
            displacement = float(np.max(np.abs(X_candidate - X_flow)))
            X_flow = X_candidate
            if stabiliser.check_convergence(grad_norm_sq, displacement):
                break

    # Score the flowed positions — Lyapunov never touches scoring
    m_view, b_view = foundation.score_views(X_flow)
    bsdt = BSDTChannels(k=k)
    bsdt.fit(X_flow)
    bsdt_score = _robust_norm(bsdt.energy(X_flow) + bsdt.mfls(X_flow))
    fused, _ = fisher_vr_fuse([m_view, b_view, bsdt_score])
    return fused


# ==================================================================
#  ENGINE CONFIGURATIONS
# ==================================================================

def build_configs():
    """Generate all Betti+Morse foundation configs with enrichments."""
    configs = {}

    # --- A: Foundation-only (pure Betti + Morse) ---
    for k in [15, 20, 25]:
        configs[f'BM_pure_k{k}'] = ('none', dict(k=k))

    # --- B: Foundation + BSDT ---
    for k in [15, 20, 25]:
        configs[f'BM_BSDT_k{k}'] = ('bsdt', dict(k=k))

    # --- C: Foundation + ReducedTensor ---
    for k in [15, 20]:
        configs[f'BM_RT_k{k}'] = ('reduced_tensor', dict(k=k))

    # --- D: Foundation + MDN Tensor (score variants × operator sets) ---
    default_ops = [
        ("stat", StatisticalSpectrum()),
        ("chaos", ChaosSpectrum()),
        ("freq", SpectralSpectrum()),
        ("geom", GeometricSpectrum()),
        ("recon", ReconstructionSpectrum()),
        ("rank", RankOrderSpectrum()),
    ]

    enhanced_ops = list(default_ops)
    if PhaseCurveSpectrum:
        enhanced_ops.append(("phase", PhaseCurveSpectrum()))
    if TopologicalSpectrum:
        enhanced_ops.append(("topo", TopologicalSpectrum(k=15)))

    minimal_ops = [
        ("stat", StatisticalSpectrum()),
        ("geom", GeometricSpectrum()),
        ("recon", ReconstructionSpectrum()),
    ]

    op_sets = {
        'def': default_ops,
        'enh': enhanced_ops,
        'min': minimal_ops,
    }
    for op_name, ops in op_sets.items():
        for sv in ['v1', 'v3a', 'v3c', 'v3d']:
            configs[f'BM_MDN_{op_name}_{sv}'] = ('mdn_tensor', dict(
                operators=ops, score_variant=sv, k=20))

    # --- E: Foundation + SubspaceScan ---
    if SubspaceScanScorer is not None:
        configs['BM_SubScan_k20'] = ('subscan', dict(k=20))

    # --- F: Foundation + BSDT + ReducedTensor (full 4-view) ---
    for k in [15, 20]:
        configs[f'BM_Full4_k{k}'] = ('full_fused', dict(k=k))

    # --- G: EnergyFlow → Foundation ---
    configs['BM_EFlow_k20'] = ('energy_flow', dict(k=20, n_iter=30))

    # --- H: EnergyFlow → Foundation + BSDT ---
    configs['BM_EFlow_BSDT_k20'] = ('energy_flow_bsdt', dict(k=20, n_iter=30))

    return configs


# Dispatch table
ENRICHMENT_FNS = {
    'none':             _enrich_none,
    'bsdt':             _enrich_bsdt,
    'reduced_tensor':   _enrich_reduced_tensor,
    'mdn_tensor':       _enrich_mdn_tensor,
    'subscan':          _enrich_subscan,
    'full_fused':       _enrich_full_fused,
    'energy_flow':      _enrich_energy_flow,
    'energy_flow_bsdt': _enrich_energy_flow_bsdt,
}


# ==================================================================
#  DATA LOADING (copied from bench_operational.py, unchanged)
# ==================================================================
def load_panel():
    npz = np.load(os.path.join(CACHE_DIR, 'gsib_real_panel.npz'))
    X_3d = npz['X']
    with open(os.path.join(CACHE_DIR, 'gsib_real_meta.json'),
              encoding='utf-8') as f:
        meta = json.load(f)
    N_meta = len(meta)
    if X_3d.shape[1] > N_meta:
        X_3d = X_3d[:, :N_meta, :]
    dates = pd.date_range('2005-01-01', '2023-12-31',
                          freq='QE')[:X_3d.shape[0]]
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
def prospective_score(X_3d_sub, dates, enrichment_fn, foundation_k,
                      enrichment_type, params):
    """
    Expanding-window prospective scoring.

    At each quarter:
      1. Fit BettiMorseFoundation on all data up to this point
      2. Score with foundation + enrichment via Fisher VR fusion
    """
    T, N, d = X_3d_sub.shape
    calib_end_dt = pd.Timestamp(CALIB_END)
    n_calib = int((dates <= calib_end_dt).sum())

    quarter_scores = np.full(T, np.nan)
    bank_scores_all = np.full((T, N), np.nan)

    # Phase 1: Calibration window
    X_calib = X_3d_sub[:n_calib].reshape(n_calib * N, d)
    X_calib = np.nan_to_num(X_calib, nan=0.0)

    foundation = BettiMorseFoundation(k=foundation_k)
    foundation.fit(X_calib)

    scores_calib = enrichment_fn(X_calib, foundation, params)
    for t in range(n_calib):
        bs = scores_calib[t * N:(t + 1) * N]
        bank_scores_all[t, :] = bs
        quarter_scores[t] = float(bs.mean())

    # Phase 2: Expanding window
    for t in range(n_calib, T):
        n_pts = (t + 1) * N
        X_up_to_t = X_3d_sub[:t + 1].reshape(n_pts, d)
        X_up_to_t = np.nan_to_num(X_up_to_t, nan=0.0)

        foundation_t = BettiMorseFoundation(k=foundation_k)
        foundation_t.fit(X_up_to_t)

        scores_all = enrichment_fn(X_up_to_t, foundation_t, params)
        bs_t = scores_all[-N:]
        bank_scores_all[t, :] = bs_t
        quarter_scores[t] = float(bs_t.mean())
        gc.collect()

    return quarter_scores, bank_scores_all, n_calib


# ==================================================================
#  CHANNEL DERIVATION + THRESHOLD SWEEPS
# ==================================================================
def derive_channels(q_scores, n_calib):
    T = len(q_scores)
    valid = ~np.isnan(q_scores)

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


def eval_at_alarm(scores, alarm_mask, y_crisis, dates,
                  flip_for_auroc=False):
    T = len(dates)
    valid = ~np.isnan(scores)
    crisis = y_crisis.astype(bool)
    y_v = y_crisis[valid]
    s_v = -scores[valid] if flip_for_auroc else scores[valid]
    auroc = (roc_auc_score(y_v, s_v)
             if 0 < y_v.sum() < len(y_v) else float('nan'))

    gfc_set = {'2007-12-31', '2008-03-31', '2008-06-30', '2008-09-30',
               '2008-12-31', '2009-03-31', '2009-06-30'}
    gfc_m = np.array([str(dates[i].date()) in gfc_set for i in range(T)])
    gfc_or_norm = valid & (gfc_m | (y_crisis == 0))
    if gfc_or_norm.sum() > 2 and y_crisis[gfc_or_norm].sum() > 0:
        auroc_gfc = roc_auc_score(
            y_crisis[gfc_or_norm], s_v[gfc_or_norm[valid]])
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


def sweep_and_best(q_scores, z_scores, p_values, n_calib, dates,
                   y_crisis):
    T = len(dates)
    valid_q = ~np.isnan(q_scores)
    valid_z = ~np.isnan(z_scores)
    valid_p = ~np.isnan(p_values)
    calib_q = q_scores[:n_calib][~np.isnan(q_scores[:n_calib])]

    best_results = {}

    # --- Percentile sweep ---
    pctl_cands = []
    for pctl in PCTL_SWEEP:
        thresh = (float(np.percentile(calib_q, pctl))
                  if len(calib_q) > 2 else 1e10)
        alarm = np.zeros(T, dtype=bool)
        alarm[valid_q] = q_scores[valid_q] > thresh
        r = eval_at_alarm(q_scores, alarm, y_crisis, dates)
        r['pctl'] = pctl
        r['threshold'] = thresh
        r['channel'] = 'percentile'
        pctl_cands.append(r)
    if pctl_cands:
        op_ok = [c for c in pctl_cands if c['far'] < OP_FAR and c['f1'] > 0]
        best_results['percentile'] = max(
            op_ok if op_ok else pctl_cands, key=lambda x: x['f1'])

    # --- Z-score sweep ---
    z_cands = []
    for z_th in Z_SWEEP:
        alarm = np.zeros(T, dtype=bool)
        alarm[valid_z] = z_scores[valid_z] > z_th
        r = eval_at_alarm(z_scores, alarm, y_crisis, dates)
        r['z_thresh'] = z_th
        r['channel'] = 'z_score'
        z_cands.append(r)
    if z_cands:
        op_ok = [c for c in z_cands if c['far'] < OP_FAR and c['f1'] > 0]
        best_results['z_score'] = max(
            op_ok if op_ok else z_cands, key=lambda x: x['f1'])

    # --- P-value sweep ---
    p_cands = []
    for p_th in P_SWEEP:
        alarm = np.zeros(T, dtype=bool)
        alarm[valid_p] = p_values[valid_p] < p_th
        r = eval_at_alarm(-p_values, alarm, y_crisis, dates,
                          flip_for_auroc=False)
        r['p_thresh'] = p_th
        r['channel'] = 'p_value'
        p_cands.append(r)
    if p_cands:
        op_ok = [c for c in p_cands if c['far'] < OP_FAR and c['f1'] > 0]
        best_results['p_value'] = max(
            op_ok if op_ok else p_cands, key=lambda x: x['f1'])

    return best_results


def is_operational(r):
    if r is None:
        return False
    return (r['f1'] >= OP_F1
            and r['recall'] >= OP_RECALL
            and r['prec'] >= OP_PREC
            and r['far'] < OP_FAR
            and r['auroc'] >= OP_AUROC
            and not np.isnan(r.get('auroc_gfc', float('nan')))
            and r.get('auroc_gfc', 0) >= OP_GFC
            and r.get('first_alarm', 'none') != 'none'
            and r.get('first_alarm', '2099') < '2007-12-31')


# ==================================================================
#  MAIN
# ==================================================================
def main():
    print('=' * 90)
    print('  BETTI + MORSE FOUNDATION BENCHMARK')
    print('  Foundation: BettiBarcodeSuite + MorseTopologyAlarm')
    print('  Enrichments: BSDT, ReducedTensor, MDN Tensor, SubspaceScan, EnergyFlow')
    print('  Lyapunov ISS: iteration control ONLY (never touches prediction)')
    print('  Protocol: expanding-window, normal-period-only, parameter freeze')
    print('=' * 90)

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    X_3d, meta, dates = load_panel()
    T, N, d = X_3d.shape
    y_crisis = np.array([1 if str(dt.date()) in CRISIS_QUARTERS else 0
                         for dt in dates])

    print(f'\n  Panel: T={T}, N={N}, d={d}')
    print(f'  Crisis quarters: {int(y_crisis.sum())}/{T}')

    all_configs = build_configs()
    print(f'  Total configurations: {len(all_configs)}')

    # Results
    operational = []
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
            print('  [SKIP] No data')
            continue

        nan_pct = np.isnan(X_sub).mean() * 100
        print(f'  Banks: {len(bank_names)}, Shape: {X_sub.shape}, '
              f'NaN: {nan_pct:.1f}%')

        region_results = {}

        for cfg_name, (enrichment_type, params) in all_configs.items():
            t0 = time.time()
            try:
                k = params.get('k', 20)
                enrich_fn = ENRICHMENT_FNS[enrichment_type]

                q_scores, bank_scores, n_calib = prospective_score(
                    X_sub, dates, enrich_fn, k,
                    enrichment_type, params)
                elapsed = time.time() - t0

                z_scores_ch, p_values_ch, cal_sorted = derive_channels(
                    q_scores, n_calib)
                best = sweep_and_best(
                    q_scores, z_scores_ch, p_values_ch,
                    n_calib, dates, y_crisis)

                # Find best across channels
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
                    far_ok = 'Y' if r['far'] < OP_FAR else 'N'
                    gfc_v = r.get('auroc_gfc', 0)
                    gfc_ok = 'Y' if gfc_v >= OP_GFC else 'N'

                    print(f'  {cfg_name:<30s} '
                          f'F1={r["f1"]:5.1f}  R={r["recall"]:5.1f}%  '
                          f'P={r["prec"]:5.1f}%  FAR={r["far"]:4.1f}%'
                          f'[{far_ok}] '
                          f'GFC={gfc_v:.3f}[{gfc_ok}]  '
                          f'Ch={ch}  Alarm={r.get("first_alarm","?")}  '
                          f'{elapsed:.1f}s{tag}')

                    if op:
                        operational.append(
                            (cfg_name, region_name, ch, r, elapsed))

                    region_results[cfg_name] = {
                        'best_channel': ch,
                        'best': r,
                        'all_channels': best,
                        'time': elapsed,
                        'operational': op,
                    }
                else:
                    print(f'  {cfg_name:<30s}  NO VALID SCORES  '
                          f'{time.time()-t0:.1f}s')

            except Exception as e:
                elapsed = time.time() - t0
                print(f'  {cfg_name:<30s}  ERROR: '
                      f'{type(e).__name__}: {e}  {elapsed:.1f}s')

            gc.collect()

        all_results[region_name] = region_results

    # ==============================================================
    #  FINAL REPORT
    # ==============================================================
    print('\n\n' + '=' * 100)
    print('  OPERATIONAL MODELS (Betti+Morse Foundation)')
    print('  Criteria: F1>=40, Recall>=50%, Prec>=30%, FAR<25%, '
          'AUROC>=0.65, GFC-AUC>=0.80')
    print('=' * 100)

    if not operational:
        print('\n  *** NO OPERATIONAL MODELS FOUND ***')
        print('  Top-20 near-misses:\n')
        near = []
        for region_name, rr in all_results.items():
            for cfg_name, data in rr.items():
                if 'best' in data:
                    r = data['best']
                    near.append((cfg_name, region_name,
                                 data['best_channel'], r,
                                 data.get('time', 0)))
        near.sort(key=lambda x: x[3].get('f1', 0), reverse=True)

        hdr = (f'  {"Config":<30s} {"Region":<18s} {"Ch":<12s} '
               f'{"F1":>5s} {"Rec%":>5s} {"Prec%":>5s} {"FAR%":>5s} '
               f'{"AUROC":>6s} {"GFC":>6s} {"Alarm":<12s}')
        print(hdr)
        print(f'  {"-"*120}')
        for cfg, reg, ch, r, t in near[:20]:
            gfc = r.get('auroc_gfc', 0)
            print(f'  {cfg:<30s} {reg:<18s} {ch:<12s} '
                  f'{r["f1"]:5.1f} {r["recall"]:5.1f} '
                  f'{r["prec"]:5.1f} {r["far"]:5.1f} '
                  f'{r["auroc"]:6.3f} {gfc:6.3f} '
                  f'{r.get("first_alarm","?"):<12s}')
    else:
        operational.sort(key=lambda x: x[3]['f1'], reverse=True)

        hdr = (f'\n  {"Config":<30s} {"Region":<18s} {"Ch":<12s} '
               f'{"F1":>5s} {"Rec%":>5s} {"Prec%":>5s} {"FAR%":>5s} '
               f'{"AUROC":>6s} {"GFC":>6s} {"Alarm":<12s} '
               f'{"Time":>6s}')
        print(hdr)
        print(f'  {"-"*130}')
        for cfg, reg, ch, r, t in operational:
            gfc = r.get('auroc_gfc', 0)
            print(f'  {cfg:<30s} {reg:<18s} {ch:<12s} '
                  f'{r["f1"]:5.1f} {r["recall"]:5.1f} '
                  f'{r["prec"]:5.1f} {r["far"]:5.1f} '
                  f'{r["auroc"]:6.3f} {gfc:6.3f} '
                  f'{r.get("first_alarm","?"):<12s} {t:5.1f}s')

    # Save results
    def sanitize(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, float) and np.isnan(obj):
            return None
        return obj

    results_path = os.path.join(ROOT, 'operational_betti_morse_search.json')
    clean = json.loads(json.dumps(all_results, default=sanitize))
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(clean, f, indent=2)
    print(f'\n  Results JSON: {results_path}')

    if operational:
        op_path = os.path.join(ARTIFACT_DIR, 'operational_configs.json')
        op_data = []
        for cfg, reg, ch, r, t in operational:
            entry = {
                'config': cfg, 'region': reg, 'channel': ch,
                'f1': r['f1'], 'recall': r['recall'],
                'prec': r['prec'], 'far': r['far'],
                'auroc': r['auroc'],
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
