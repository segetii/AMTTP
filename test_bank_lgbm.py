#!/usr/bin/env python3
"""
LGBM Banking Benchmark — ReducedTensor + BSDT → LGBM | Morse → Early Warning
=============================================================================

Architecture (two-layer):
  Layer 1 — LGBM Risk Classifier:
    ReducedTensor + BSDT features → LightGBM → continuous crisis probability
    (Morse is NOT an LGBM feature — it is a separate alarm)

  Layer 2 — Morse Early Warning Alarm:
    MorseTopologyAlarm runs as unsupervised structural alarm on raw data.
    It detects manifold-level shifts BEFORE crisis appears in the labels.
    Reports binary alarm (yes/no) with lead-time.

Pipeline per expanding-window step:
  1. Expanding window [0..t] — train; [t+1] — test
  2. StandardScaler fit on training only
  3. Lyapunov-controlled EnergyFlow preprocessing (optional)
  4. ReducedTensorDescriptor → (n_eigs+6)-D descriptor per point
  5. BSDTChannels → 4 channels (δ_C, δ_G, δ_A, δ_T) + energy + MFLS
  6. Concatenate [RT, BSDT] → LightGBM classifier → risk score
  7. Morse alarm scored SEPARATELY (unsupervised, threshold-based)

LGBM Variants:
  A. LGBM on [ReducedTensor + BSDT]               (full pipeline)
  B. LGBM on [ReducedTensor only]                  (ablation)
  C. LGBM on [BSDT only]                           (ablation)
  D. LGBM on [ReducedTensor + BSDT + EnergyFlow]  (+ Lyapunov preproc)

Morse Alarm (always runs separately, no LGBM):
  - Unsupervised kNN structural alarm
  - 4 features: mean_knn, d1_isolation, persistence, density_ratio
  - Threshold: calibration μ + 3σ / μ + 2σ
  - Reports: detection rate, lead-time, FAR

Data: FDIC + ECB MIR + World Bank GFDD
  T=76 quarters, N=25 G-SIBs, d=5
  (loan_to_asset, equity_ratio, npl_ratio, roa, funding_cost)

Crises: GFC (2007Q4-2009Q2), EU Sovereign (2011Q3-2012Q2),
        COVID (2020Q1-Q2)

Author: Odeyemi Olusegun Israel — AMTTP/UDL Project
"""
import sys, os, time, warnings, json, gc
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'research', 'udl'))
os.environ['CUDA_VISIBLE_DEVICES'] = ''
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings("ignore")

from sklearn.metrics import roc_auc_score, f1_score
from sklearn.preprocessing import StandardScaler
from lightgbm import LGBMClassifier

from udl.system_mode import (
    MorseTopologyAlarm,
    BettiBarcodeSuite,
    BSDTChannels,
    ReducedTensorDescriptor,
    LyapunovStabiliser,
)

# ══════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════
ROOT = r'C:\amttp'
CACHE_DIR = os.path.join(ROOT, 'research', 'adaptive-friction',
                         'banklevel_enhanced', 'gsib_cache_real')
RESULTS_DIR = os.path.join(ROOT, 'results')
os.makedirs(RESULTS_DIR, exist_ok=True)

CRISIS_QUARTERS = {
    '2007-12-31', '2008-03-31', '2008-06-30', '2008-09-30',
    '2008-12-31', '2009-03-31', '2009-06-30',
    '2020-03-31', '2020-06-30',
    '2011-09-30', '2011-12-31', '2012-03-31', '2012-06-30',
}
CALIB_END = '2007-09-30'   # Pre-crisis calibration boundary
BURN_IN = 4                 # Minimum quarters before scoring
FEATURE_NAMES = ['loan_to_asset', 'equity_ratio', 'npl_ratio', 'roa', 'funding_cost']

# Crisis event groups for per-event reporting
CRISIS_EVENTS = {
    'GFC':          ['2007-12-31', '2008-03-31', '2008-06-30', '2008-09-30',
                     '2008-12-31', '2009-03-31', '2009-06-30'],
    'EU_Sovereign': ['2011-09-30', '2011-12-31', '2012-03-31', '2012-06-30'],
    'COVID':        ['2020-03-31', '2020-06-30'],
}


# ══════════════════════════════════════════════════════════════════
#  LYAPUNOV-CONTROLLED ENERGY FLOW (iteration control only)
# ══════════════════════════════════════════════════════════════════
def lyapunov_energy_flow(X, n_iter=30, eta=0.01, alpha_radial=0.1):
    """
    Gradient-flow preprocessing with Lyapunov-stabilised iteration.

    The Lyapunov stabiliser controls ONLY:
      - clamp_forces(): barrier-smooth force limiting
      - accept_step(): Armijo descent certificate
      - check_convergence(): La Salle invariance termination

    It NEVER contributes to the final prediction score.
    """
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

    return X_flow


# ══════════════════════════════════════════════════════════════════
#  FEATURE EXTRACTION
# ══════════════════════════════════════════════════════════════════
def extract_features(X, X_ref, k=15, include_rt=True,
                     include_morse=True, include_bsdt=True,
                     include_betti=False):
    """
    Extract topology/tensor features for LGBM input.

    Parameters
    ----------
    X       : (N, d) array — points to featurise
    X_ref   : (N_ref, d) array — normal reference data
    k       : int — k-neighbours
    include_rt    : bool — include ReducedTensorDescriptor features
    include_morse : bool — include MorseTopologyAlarm features
    include_bsdt  : bool — include BSDT channel features
    include_betti : bool — include BettiBarcodeSuite features

    Returns
    -------
    F : (N, F_dim) feature matrix
    names : list of feature names
    """
    views = []
    names = []

    if include_rt:
        desc = ReducedTensorDescriptor(k_neighbors=k)
        desc.fit(X_ref)
        D = desc.transform(X)
        n_eigs = desc.n_eigs
        # D columns: [grad_norm, λ₁..λ_n_eigs, mahalanobis, medoid_dist,
        #             trace_H, det_sigma, morse_index]
        views.append(D)
        rt_names = ['rt_grad_norm']
        rt_names += [f'rt_eig_{i}' for i in range(n_eigs)]
        rt_names += ['rt_mahalanobis', 'rt_medoid_dist',
                     'rt_trace_H', 'rt_det_sigma', 'rt_morse_index']
        names.extend(rt_names)

    if include_morse:
        morse = MorseTopologyAlarm(k=k)
        morse.fit(X_ref)
        m_raw = morse._compute_features(X, morse._X_ref, morse._energy_fn)
        views.append(m_raw)
        names.extend(['morse_mean_knn', 'morse_d1_isolation',
                       'morse_persistence', 'morse_density_ratio'])

    if include_bsdt:
        bsdt = BSDTChannels(k=k)
        bsdt.fit(X_ref)
        ch = bsdt.channels(X)
        C = np.column_stack([ch['delta_C'], ch['delta_G'],
                             ch['delta_A'], ch['delta_T']])
        E = bsdt.energy(X)[:, None]
        M = bsdt.mfls(X)[:, None]
        views.append(C)
        views.append(E)
        views.append(M)
        names.extend(['bsdt_delta_C', 'bsdt_delta_G',
                       'bsdt_delta_A', 'bsdt_delta_T',
                       'bsdt_energy', 'bsdt_mfls'])

    if include_betti:
        betti = BettiBarcodeSuite(k=min(k + 5, 25), n_scales=8)
        betti.fit(X_ref)
        b_raw = betti._compute_features(X, betti._X_ref)
        views.append(b_raw)
        n_betti = b_raw.shape[1]
        names.extend([f'betti_{i}' for i in range(n_betti)])

    if not views:
        raise ValueError("At least one feature set must be enabled")

    F = np.hstack(views)
    F = np.nan_to_num(F, nan=0.0, posinf=5.0, neginf=-5.0)
    return F, names


# ══════════════════════════════════════════════════════════════════
#  DATA LOADING
# ══════════════════════════════════════════════════════════════════
def load_bank_panel():
    """Load G-SIB bank panel from cached NPZ."""
    npz = np.load(os.path.join(CACHE_DIR, 'gsib_real_panel.npz'))
    X_3d = npz['X']  # (T, N, d)

    with open(os.path.join(CACHE_DIR, 'gsib_real_meta.json'),
              encoding='utf-8') as f:
        meta = json.load(f)

    # Trim to meta length (some panels have extra columns)
    N_meta = len(meta)
    if X_3d.shape[1] > N_meta:
        X_3d = X_3d[:, :N_meta, :]

    dates = pd.date_range('2005-01-01', '2023-12-31',
                          freq='QE')[:X_3d.shape[0]]

    y_crisis = np.array([1 if str(d.date()) in CRISIS_QUARTERS else 0
                         for d in dates], dtype=int)

    return X_3d, dates, y_crisis, meta


# ══════════════════════════════════════════════════════════════════
#  LGBM EXPANDING-WINDOW BENCHMARK
# ══════════════════════════════════════════════════════════════════
def run_lgbm_variant(X_3d, dates, y_crisis, variant_name,
                     include_rt=True, include_morse=True,
                     include_bsdt=True, include_betti=False,
                     use_energy_flow=False, k=15):
    """
    Expanding-window LGBM benchmark.

    At each quarter t:
      1. Train = quarters [0..t], Test = quarter [t+1]
      2. Scale on training only (no leakage)
      3. Optionally apply Lyapunov EnergyFlow to training
      4. Extract ReducedTensor + Morse + BSDT features
      5. Train LGBM on features + crisis labels
      6. Score test quarter with LGBM predict_proba
    """
    T, N, d = X_3d.shape
    calib_end_dt = pd.Timestamp(CALIB_END)
    n_calib = int((dates <= calib_end_dt).sum())

    q_scores = np.full(T, np.nan)
    q_proba = np.full((T, N), np.nan)  # per-bank probabilities

    print(f'\n  Variant: {variant_name}')
    print(f'  Features: RT={include_rt} Morse={include_morse} '
          f'BSDT={include_bsdt} Betti={include_betti} EFlow={use_energy_flow}')
    print(f'  Calibration: {n_calib} quarters (→ {CALIB_END})')
    t0_total = time.time()

    for t in range(BURN_IN, T - 1):
        # ── 1. Expanding window: train=[0..t], test=[t+1] ──
        n_q = t + 1
        X_train_raw = X_3d[:n_q].reshape(n_q * N, d)
        X_test_raw = X_3d[t + 1].reshape(N, d)

        # Crisis labels for training
        y_train = np.zeros(n_q * N, dtype=int)
        for t_idx in range(n_q):
            if str(dates[t_idx].date()) in CRISIS_QUARTERS:
                y_train[t_idx * N:(t_idx + 1) * N] = 1

        # ── 2. Scaler fit on training only ──
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train_raw).astype(np.float64)
        X_test = scaler.transform(X_test_raw).astype(np.float64)

        # Replace NaN/Inf
        X_train = np.nan_to_num(X_train, nan=0.0, posinf=5.0, neginf=-5.0)
        X_test = np.nan_to_num(X_test, nan=0.0, posinf=5.0, neginf=-5.0)

        # ── 3. Optional Lyapunov EnergyFlow (iteration control only) ──
        if use_energy_flow:
            X_train = lyapunov_energy_flow(X_train)
            X_test_flow = lyapunov_energy_flow(
                np.vstack([X_train, X_test]))[-N:]
            X_test = X_test_flow

        # ── 4. Reference data = normal quarters in training ──
        normal_mask = (y_train == 0)
        X_ref = X_train[normal_mask]
        if len(X_ref) < 10:
            X_ref = X_train  # fallback

        # ── 5. Extract features ──
        try:
            F_train, feat_names = extract_features(
                X_train, X_ref, k=k,
                include_rt=include_rt, include_morse=include_morse,
                include_bsdt=include_bsdt, include_betti=include_betti)

            F_test, _ = extract_features(
                X_test, X_ref, k=k,
                include_rt=include_rt, include_morse=include_morse,
                include_bsdt=include_bsdt, include_betti=include_betti)
        except Exception as e:
            # Fallback: use raw features
            F_train = X_train
            F_test = X_test
            feat_names = FEATURE_NAMES

        # Sanitise
        F_train = np.nan_to_num(F_train, nan=0.0, posinf=5.0, neginf=-5.0)
        F_test = np.nan_to_num(F_test, nan=0.0, posinf=5.0, neginf=-5.0)

        # ── 6. Train LGBM ──
        n_crisis_train = int(y_train.sum())
        n_normal_train = int((y_train == 0).sum())

        if n_crisis_train == 0:
            # No crisis data yet — use unsupervised score fallback
            # (ReducedTensor auto-score if available)
            if include_rt:
                desc = ReducedTensorDescriptor(k_neighbors=k)
                desc.fit(X_ref)
                test_scores = desc.score(X_test)
            else:
                test_scores = np.linalg.norm(
                    X_test - X_ref.mean(axis=0), axis=1)
        else:
            # Compute class weight for imbalanced data
            scale_pos = max(n_normal_train / max(n_crisis_train, 1), 1.0)

            lgbm = LGBMClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.05,
                num_leaves=31,
                min_child_samples=max(5, n_crisis_train // 10),
                scale_pos_weight=scale_pos,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                verbosity=-1,
                random_state=42,
                n_jobs=1,
            )
            lgbm.fit(F_train, y_train)
            test_proba = lgbm.predict_proba(F_test)[:, 1]
            test_scores = test_proba

        q_proba[t + 1, :] = test_scores
        q_scores[t + 1] = float(test_scores.mean())

        # Progress
        ds = str(dates[t + 1].date())
        crisis_mark = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
        if (t + 1) % 10 == 0 or ds in CRISIS_QUARTERS:
            # Running AUC
            valid = ~np.isnan(q_scores[:t + 2])
            y_sub = y_crisis[:t + 2]
            s_sub = q_scores[:t + 2]
            if valid.sum() > 2 and y_sub[valid].sum() > 0 and y_sub[valid].sum() < valid.sum():
                run_auc = roc_auc_score(y_sub[valid], s_sub[valid])
                print(f'    t={t+1:3d} {ds}  score={q_scores[t+1]:.4f}  '
                      f'runAUC={run_auc:.4f}{crisis_mark}')
            else:
                print(f'    t={t+1:3d} {ds}  score={q_scores[t+1]:.4f}{crisis_mark}')

        gc.collect()

    elapsed = time.time() - t0_total

    # ── Compute metrics ──
    valid = ~np.isnan(q_scores)
    y_v = y_crisis[valid]
    s_v = q_scores[valid]

    if y_v.sum() > 0 and y_v.sum() < len(y_v):
        auc = roc_auc_score(y_v, s_v)
    else:
        auc = 0.5

    # Fixed threshold from calibration
    calib_s = q_scores[BURN_IN + 1:n_calib + 1]
    calib_s = calib_s[~np.isnan(calib_s)]
    if len(calib_s) >= 3:
        mu_c, sig_c = calib_s.mean(), calib_s.std()
        thresh_3s = mu_c + 3 * sig_c
        thresh_2s = mu_c + 2 * sig_c
    else:
        thresh_3s = thresh_2s = np.nanpercentile(q_scores[valid], 90)

    # Per-crisis detection
    event_results = {}
    for ev_name, ev_dates in CRISIS_EVENTS.items():
        ev_mask = np.array([str(dates[i].date()) in ev_dates for i in range(T)])
        ev_scores = q_scores[ev_mask & valid]
        detected_3s = int(np.sum(ev_scores > thresh_3s))
        detected_2s = int(np.sum(ev_scores > thresh_2s))
        total_ev = int(ev_mask.sum())
        event_results[ev_name] = {
            'detected_3sigma': detected_3s,
            'detected_2sigma': detected_2s,
            'total_quarters': total_ev,
            'max_score': float(ev_scores.max()) if len(ev_scores) > 0 else 0,
        }

    # FAR (false alarm rate on normal quarters)
    normal_mask_valid = valid & (y_crisis == 0)
    normal_scores = q_scores[normal_mask_valid]
    far_3s = float(np.mean(normal_scores > thresh_3s) * 100)
    far_2s = float(np.mean(normal_scores > thresh_2s) * 100)

    # GFC-specific AUC
    gfc_dates_set = set(CRISIS_EVENTS['GFC'])
    gfc_mask = np.array([str(dates[i].date()) in gfc_dates_set for i in range(T)])
    gfc_or_normal = valid & (gfc_mask | (y_crisis == 0))
    if gfc_or_normal.sum() > 2 and y_crisis[gfc_or_normal].sum() > 0:
        gfc_auc = roc_auc_score(y_crisis[gfc_or_normal],
                                q_scores[gfc_or_normal])
    else:
        gfc_auc = 0.5

    # Best F1
    best_f1 = 0.0
    for pctl in range(50, 100, 1):
        thr = np.percentile(s_v, pctl)
        pred = (s_v > thr).astype(int)
        f = f1_score(y_v, pred, zero_division=0)
        if f > best_f1:
            best_f1 = f

    # First alarm before GFC
    alarm_mask = q_scores > thresh_3s
    pre_gfc_alarms = []
    gfc_first = pd.Timestamp('2007-12-31')
    for i in range(T):
        if alarm_mask[i] and dates[i] < gfc_first:
            pre_gfc_alarms.append(str(dates[i].date()))
    gfc_lead = pre_gfc_alarms[0] if pre_gfc_alarms else None

    results = {
        'variant': variant_name,
        'auc': auc,
        'gfc_auc': gfc_auc,
        'best_f1': best_f1,
        'far_3sigma': far_3s,
        'far_2sigma': far_2s,
        'gfc_lead': gfc_lead,
        'events': event_results,
        'time_sec': elapsed,
        'n_features': len(feat_names) if 'feat_names' in dir() else 0,
        'feature_names': feat_names if 'feat_names' in dir() else [],
    }

    return results, q_scores


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════
def main():
    t_global = time.time()

    print('=' * 80)
    print('  LGBM Banking Benchmark — Two-Layer Architecture')
    print('  Layer 1: ReducedTensor + BSDT → LGBM (risk classification)')
    print('  Layer 2: Morse Early Warning Alarm (unsupervised, standalone)')
    print('  Data: FDIC + ECB MIR + World Bank GFDD (G-SIB Panel)')
    print('=' * 80)

    X_3d, dates, y_crisis, meta = load_bank_panel()
    T, N, d = X_3d.shape
    print(f'\n  Panel: T={T} quarters, N={N} banks, d={d} features')
    print(f'  Features: {FEATURE_NAMES}')
    print(f'  Banks: {len(meta)} G-SIBs')
    print(f'  Date range: {dates[0].date()} to {dates[-1].date()}')
    print(f'  Crisis quarters: {int(y_crisis.sum())}/{T}')
    print(f'  Normal quarters: {int((y_crisis == 0).sum())}/{T}')

    for ev, qs in CRISIS_EVENTS.items():
        print(f'    {ev}: {len(qs)} quarters ({qs[0]} → {qs[-1]})')

    # ── Define LGBM variants (NO Morse — Morse is separate alarm) ──
    variants = {
        'LGBM_RT+BSDT': dict(
            include_rt=True, include_morse=False,
            include_bsdt=True, include_betti=False,
            use_energy_flow=False),
        'LGBM_RT_only': dict(
            include_rt=True, include_morse=False,
            include_bsdt=False, include_betti=False,
            use_energy_flow=False),
        'LGBM_BSDT_only': dict(
            include_rt=False, include_morse=False,
            include_bsdt=True, include_betti=False,
            use_energy_flow=False),
        'LGBM_RT+BSDT+EFlow': dict(
            include_rt=True, include_morse=False,
            include_bsdt=True, include_betti=False,
            use_energy_flow=True),
    }

    all_results = {}
    all_scores = {}

    for vname, vparams in variants.items():
        print(f'\n{"="*70}')
        print(f'  {vname}  (strict no-leakage, expanding window, LGBM)')
        print(f'{"="*70}')

        try:
            result, q_scores = run_lgbm_variant(
                X_3d, dates, y_crisis, vname, k=15, **vparams)
            all_results[vname] = result
            all_scores[vname] = q_scores.tolist()

            print(f'\n  {vname} RESULTS:')
            print(f'    AUC (full):   {result["auc"]:.4f}')
            print(f'    AUC (GFC):    {result["gfc_auc"]:.4f}')
            print(f'    Best F1:      {result["best_f1"]:.3f}')
            print(f'    FAR (3σ):     {result["far_3sigma"]:.1f}%')
            print(f'    FAR (2σ):     {result["far_2sigma"]:.1f}%')
            print(f'    GFC Lead:     {result["gfc_lead"]}')
            print(f'    Time:         {result["time_sec"]:.1f}s')

            for ev, ev_res in result['events'].items():
                print(f'    {ev}: {ev_res["detected_3sigma"]}'
                      f'/{ev_res["total_quarters"]} (3σ)'
                      f'  {ev_res["detected_2sigma"]}'
                      f'/{ev_res["total_quarters"]} (2σ)'
                      f'  max_score={ev_res["max_score"]:.4f}')

        except Exception as e:
            print(f'  ERROR: {e}')
            import traceback; traceback.print_exc()
            all_results[vname] = {'error': str(e)}

    # ══════════════════════════════════════════════════════════════
    #  LAYER 2 — MORSE EARLY WARNING ALARM (standalone, unsupervised)
    # ══════════════════════════════════════════════════════════════
    print(f'\n\n{"="*70}')
    print('  MORSE EARLY WARNING ALARM (unsupervised, separate from LGBM)')
    print(f'{"="*70}')

    t0_morse = time.time()
    calib_end_dt = pd.Timestamp(CALIB_END)
    n_calib = int((dates <= calib_end_dt).sum())

    morse_scores = np.full(T, np.nan)
    morse_features_all = np.full((T, 4), np.nan)  # 4 Morse features per quarter

    for t in range(BURN_IN, T - 1):
        n_q = t + 1
        X_train_raw = X_3d[:n_q].reshape(n_q * N, d)
        X_test_raw = X_3d[t + 1].reshape(N, d)

        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train_raw).astype(np.float64)
        X_test = scaler.transform(X_test_raw).astype(np.float64)
        X_train = np.nan_to_num(X_train, nan=0.0, posinf=5.0, neginf=-5.0)
        X_test = np.nan_to_num(X_test, nan=0.0, posinf=5.0, neginf=-5.0)

        # Reference = normal quarters only
        y_train_labels = np.zeros(n_q, dtype=int)
        for t_idx in range(n_q):
            if str(dates[t_idx].date()) in CRISIS_QUARTERS:
                y_train_labels[t_idx] = 1
        normal_q_mask = (y_train_labels == 0)
        normal_indices = np.where(normal_q_mask)[0]
        X_ref_list = [X_train[qi * N:(qi + 1) * N] for qi in normal_indices]
        X_ref = np.vstack(X_ref_list) if len(X_ref_list) > 0 else X_train

        try:
            morse = MorseTopologyAlarm(k=15)
            morse.fit(X_ref)
            m_test = morse._compute_features(X_test, morse._X_ref, morse._energy_fn)
            # m_test: (N, 4) — [mean_knn, d1_isolation, persistence, density_ratio]
            morse_features_all[t + 1, :] = m_test.mean(axis=0)
            # Alarm score = Fisher VR weighted combination (as morse.score does)
            test_score_raw = morse.score(X_test)
            morse_scores[t + 1] = float(test_score_raw.mean())
        except Exception:
            morse_scores[t + 1] = 0.0

        ds = str(dates[t + 1].date())
        crisis_mark = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
        if (t + 1) % 10 == 0 or ds in CRISIS_QUARTERS:
            print(f'    t={t+1:3d} {ds}  morse={morse_scores[t+1]:.4f}{crisis_mark}')

    dt_morse = time.time() - t0_morse

    # Morse alarm thresholds from calibration period
    calib_morse = morse_scores[BURN_IN + 1:n_calib + 1]
    calib_morse = calib_morse[~np.isnan(calib_morse)]
    if len(calib_morse) >= 3:
        mu_m, sig_m = calib_morse.mean(), calib_morse.std()
        thresh_m3 = mu_m + 3 * sig_m
        thresh_m2 = mu_m + 2 * sig_m
    else:
        thresh_m3 = thresh_m2 = np.nanpercentile(
            morse_scores[~np.isnan(morse_scores)], 90)

    # Morse detection report
    valid_m = ~np.isnan(morse_scores)
    y_m = y_crisis[valid_m]
    s_m = morse_scores[valid_m]
    if y_m.sum() > 0 and y_m.sum() < len(y_m):
        morse_auc = roc_auc_score(y_m, s_m)
    else:
        morse_auc = 0.5

    # Morse FAR
    normal_m = valid_m & (y_crisis == 0)
    morse_far_3s = float(np.mean(morse_scores[normal_m] > thresh_m3) * 100)
    morse_far_2s = float(np.mean(morse_scores[normal_m] > thresh_m2) * 100)

    # Per-event Morse detection
    print(f'\n  MORSE EARLY WARNING RESULTS:')
    print(f'    AUC:          {morse_auc:.4f}')
    print(f'    Threshold 3σ: {thresh_m3:.4f}  (μ={mu_m:.4f}, σ={sig_m:.4f})')
    print(f'    FAR (3σ):     {morse_far_3s:.1f}%')
    print(f'    FAR (2σ):     {morse_far_2s:.1f}%')
    print(f'    Time:         {dt_morse:.1f}s')

    morse_event_results = {}
    for ev_name, ev_dates in CRISIS_EVENTS.items():
        ev_mask = np.array([str(dates[i].date()) in ev_dates for i in range(T)])
        ev_scores = morse_scores[ev_mask & valid_m]
        detected_3s = int(np.sum(ev_scores > thresh_m3))
        detected_2s = int(np.sum(ev_scores > thresh_m2))
        total_ev = int(ev_mask.sum())
        max_ev = float(ev_scores.max()) if len(ev_scores) > 0 else 0

        # Lead time: first alarm before this event
        ev_first_date = pd.Timestamp(ev_dates[0])
        lead_alarms = []
        for i in range(T):
            if valid_m[i] and morse_scores[i] > thresh_m3 and dates[i] < ev_first_date:
                lead_alarms.append(i)
        if lead_alarms:
            first_alarm_idx = lead_alarms[0]
            lead_quarters = int((ev_first_date - dates[first_alarm_idx]).days / 91)
            lead_str = f'{lead_quarters}q ({dates[first_alarm_idx].date()})'
        else:
            lead_quarters = 0
            lead_str = 'none'

        morse_event_results[ev_name] = {
            'detected_3sigma': detected_3s,
            'detected_2sigma': detected_2s,
            'total_quarters': total_ev,
            'max_score': max_ev,
            'lead_quarters': lead_quarters,
            'lead_str': lead_str,
        }
        print(f'    {ev_name}: {detected_3s}/{total_ev} (3σ)  '
              f'{detected_2s}/{total_ev} (2σ)  '
              f'max={max_ev:.4f}  lead={lead_str}')

    # Add Morse alarm to results
    all_results['Morse_EarlyWarning'] = {
        'variant': 'Morse_EarlyWarning',
        'auc': morse_auc,
        'gfc_auc': morse_auc,  # computed below
        'best_f1': 0.0,
        'far_3sigma': morse_far_3s,
        'far_2sigma': morse_far_2s,
        'gfc_lead': None,
        'events': morse_event_results,
        'time_sec': dt_morse,
        'role': 'EARLY WARNING ALARM (unsupervised, not LGBM feature)',
    }
    all_scores['Morse_EarlyWarning'] = morse_scores.tolist()

    # GFC-specific Morse AUC
    gfc_dates_set = set(CRISIS_EVENTS['GFC'])
    gfc_mask = np.array([str(dates[i].date()) in gfc_dates_set for i in range(T)])
    gfc_or_normal_m = valid_m & (gfc_mask | (y_crisis == 0))
    if gfc_or_normal_m.sum() > 2 and y_crisis[gfc_or_normal_m].sum() > 0:
        morse_gfc_auc = roc_auc_score(y_crisis[gfc_or_normal_m],
                                       morse_scores[gfc_or_normal_m])
    else:
        morse_gfc_auc = 0.5
    all_results['Morse_EarlyWarning']['gfc_auc'] = morse_gfc_auc

    # Morse best F1
    morse_best_f1 = 0.0
    for pctl in range(50, 100, 1):
        thr = np.percentile(s_m, pctl)
        pred = (s_m > thr).astype(int)
        f = f1_score(y_m, pred, zero_division=0)
        if f > morse_best_f1:
            morse_best_f1 = f
    all_results['Morse_EarlyWarning']['best_f1'] = morse_best_f1

    # GFC lead for Morse
    gfc_first = pd.Timestamp('2007-12-31')
    morse_pre_gfc = []
    for i in range(T):
        if valid_m[i] and morse_scores[i] > thresh_m3 and dates[i] < gfc_first:
            morse_pre_gfc.append(str(dates[i].date()))
    all_results['Morse_EarlyWarning']['gfc_lead'] = (
        morse_pre_gfc[0] if morse_pre_gfc else None)

    # ══════════════════════════════════════════════════════════════
    #  SUMMARY TABLE
    # ══════════════════════════════════════════════════════════════
    dt_total = time.time() - t_global
    print('\n\n' + '=' * 80)
    print('  RESULTS SUMMARY — LGBM (risk) + Morse (early warning)')
    print('=' * 80)
    print('  [LGBM variants = risk classification;  Morse = standalone early warning alarm]')
    hdr = (f'  {"Variant":<30} {"AUC":>6} {"GFC-AUC":>8} '
           f'{"F1":>6} {"FAR3σ":>6} {"GFC-Lead":>12} {"Time":>7}')
    print(hdr)
    print('  ' + '-' * 78)

    for vname, res in all_results.items():
        if 'error' in res:
            print(f'  {vname:<30} ERROR: {res["error"][:40]}')
            continue
        gfc_lead_str = res['gfc_lead'] if res['gfc_lead'] else 'none'
        print(f'  {vname:<30} {res["auc"]:6.4f} {res["gfc_auc"]:8.4f} '
              f'{res["best_f1"]:6.3f} {res["far_3sigma"]:5.1f}% '
              f'{gfc_lead_str:>12} {res["time_sec"]:6.1f}s')

    print('  ' + '-' * 78)

    # Best variant
    valid_results = {k: v for k, v in all_results.items() if 'error' not in v}
    if valid_results:
        best = max(valid_results, key=lambda k: valid_results[k]['auc'])
        print(f'\n  BEST: {best}  AUC={valid_results[best]["auc"]:.4f}  '
              f'GFC-AUC={valid_results[best]["gfc_auc"]:.4f}')

    print(f'\n  Total time: {dt_total:.1f}s ({dt_total/60:.1f}min)')

    # ── Save results ──
    out_path = os.path.join(RESULTS_DIR, 'bank_lgbm_benchmark.json')
    save_data = {
        'results': {},
        'scores': all_scores,
        'meta': {
            'T': T, 'N': N, 'd': d,
            'dates': [str(d.date()) for d in dates],
            'crisis_quarters': list(CRISIS_QUARTERS),
            'pipeline': 'Layer1: ReducedTensor+BSDT→LGBM (risk) | Layer2: Morse (early warning alarm)',
        }
    }
    for k, v in all_results.items():
        if 'error' not in v:
            # Remove non-serializable items
            save_v = {kk: vv for kk, vv in v.items()
                      if kk != 'feature_names' or isinstance(vv, list)}
            save_data['results'][k] = save_v
        else:
            save_data['results'][k] = v

    with open(out_path, 'w') as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f'  Saved → {out_path}')


if __name__ == '__main__':
    main()
