#!/usr/bin/env python3
"""
LGBM with BSDT-Damped Internal Iteration — Banking Benchmark
=============================================================

Key Innovation: BSDT damping INSIDE LGBM's boosting rounds.

In the Gravity Engine (SIAM §6):
  Each iteration:  X_new = X + η * (F_physics − γ(E_BS)·∇E_BS)
  γ(E) = E_combined / (E_combined + θ)   — BSDT adaptive friction
  Lyapunov: Armijo step control on η

In this LGBM Engine:
  Each boosting round, LGBM computes gradient g and hessian h.
  We inject BSDT damping directly:

    g_damped[i] = g[i] * (1 − γ(E_BS[i]))
    h_damped[i] = h[i] * (1 − γ(E_BS[i])) + ε

  Where γ = E_combined / (E_combined + θ):
    - Points near blind spots (high E_BS) → γ≈1 → gradient~0 → tree ignores them
    - Points in well-modeled regions (low E_BS) → γ≈0 → full gradient → tree learns

  This is the EXACT analogue of BSDT damping in the Gravity engine,
  but applied to LGBM's internal gradient descent in function space.

  Lyapunov controls the boosting:
    - Monitor train loss per round
    - If loss increase detected → reduce learning rate (Armijo analogue)
    - Early stopping via La Salle convergence (loss plateau)

Architecture:
  Layer 1: BSDT-damped LGBM (internal iteration control)
  Layer 2: BSDT early warning (E_BS + MFLS on raw data)
  Layer 3: Morse + Betti structural confirmation

Variants:
  A. LGBM_BSDT_damped(RT+BSDT)      — full: ReducedTensor + BSDT features, BSDT-damped objective
  B. LGBM_BSDT_damped(RT_only)       — ablation: RT features, BSDT-damped objective
  C. LGBM_standard(RT+BSDT)          — control: standard LGBM (no BSDT damping) for comparison
  D. LGBM_BSDT_damped(Betti)         — Betti features, BSDT-damped objective
  E. LGBM_BSDT_damped(RT+Betti)      — RT+Betti features, BSDT-damped objective

Data: FDIC + ECB MIR + World Bank GFDD
  T=76 quarters, N=25 G-SIBs, d=5

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
import lightgbm as lgb

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
CALIB_END = '2007-09-30'
BURN_IN = 4
FEATURE_NAMES = ['loan_to_asset', 'equity_ratio', 'npl_ratio', 'roa', 'funding_cost']

CRISIS_EVENTS = {
    'GFC':          ['2007-12-31', '2008-03-31', '2008-06-30', '2008-09-30',
                     '2008-12-31', '2009-03-31', '2009-06-30'],
    'EU_Sovereign': ['2011-09-30', '2011-12-31', '2012-03-31', '2012-06-30'],
    'COVID':        ['2020-03-31', '2020-06-30'],
}


# ══════════════════════════════════════════════════════════════════
#  BSDT-DAMPED OBJECTIVE FUNCTION (Theorem C analogue)
# ══════════════════════════════════════════════════════════════════
class BSDTDampedObjective:
    """
    Custom LGBM objective that applies BSDT adaptive damping
    to the gradient and hessian at each boosting round.

    Gravity engine:   F_total = F_physics − γ(E_BS)·∇E_BS
    LGBM analogue:    g_damped = g_loss · (1 − γ(E_BS))

    γ(E) = E_combined / (E_combined + θ)
    E_combined = E_BS + β·MFLS

    Effect:
      - High E_BS (near blind spot) → γ≈1 → gradient suppressed → tree ignores
      - Low E_BS (well-modeled)     → γ≈0 → full gradient → tree learns normally
    """

    def __init__(self, gamma_weights):
        """
        Parameters
        ----------
        gamma_weights : array of shape (n_train,)
            Pre-computed γ(E_BS[i]) ∈ [0, 1] for each training point.
            γ=0 → no damping (normal), γ=1 → full damping (blind spot)
        """
        self.gamma = gamma_weights
        self._round = 0

    def __call__(self, y_true, y_pred):
        """
        BSDT-damped binary cross-entropy.

        Standard BCE gradient:  g = sigmoid(y_pred) − y_true
        Standard BCE hessian:   h = sigmoid(y_pred) * (1 − sigmoid(y_pred))

        BSDT-damped:
          g_damped = g * (1 − γ)
          h_damped = h * (1 − γ) + ε    (ε for numerical stability)

        This is the exact analogue of F_total = F_physics − γ·∇E_BS
        in the gravity engine, where the damping suppresses learning
        from points that lie in BSDT blind spots.
        """
        self._round += 1

        # Standard binary cross-entropy gradient/hessian
        p = 1.0 / (1.0 + np.exp(-y_pred))
        g = p - y_true
        h = p * (1.0 - p)

        # BSDT adaptive damping: suppress gradient at blind spots
        damping = 1.0 - self.gamma  # (n_train,)
        g_damped = g * damping
        h_damped = h * damping + 1e-6  # ε stability floor

        return g_damped, h_damped


def compute_bsdt_gamma(X_train, X_ref, k=15, beta_mfls_scale=1.0):
    """
    Compute per-point BSDT damping coefficient γ(E_BS).

    Exactly mirrors the gravity engine's damping computation:
      1. Fit BSDTChannels on reference (normal) data
      2. θ = median(E_BS(X_ref))
      3. β = θ / median(MFLS(X_ref))
      4. E_combined = E_BS + β·MFLS
      5. γ = E_combined / (E_combined + θ)

    Returns
    -------
    gamma : (n_train,) array ∈ [0, 1]
    bsdt : fitted BSDTChannels object (reused for test scoring)
    """
    bsdt = BSDTChannels(k=min(k, len(X_ref) - 1))
    bsdt.fit(X_ref)

    # θ = median E_BS on reference (same as gravity engine)
    e_ref = bsdt.energy(X_ref)
    theta_bs = float(np.median(e_ref)) + 1e-10

    # MFLS scaling (same as gravity engine)
    mfls_ref = bsdt.mfls(X_ref)
    mfls_med = float(np.median(mfls_ref)) + 1e-10
    beta = theta_bs / mfls_med * beta_mfls_scale

    # Compute on training data
    e_bs = bsdt.energy(X_train)
    mfls_train = bsdt.mfls(X_train)
    e_combined = e_bs + beta * mfls_train

    # Adaptive friction coefficient: γ = E / (E + θ)
    gamma = e_combined / (e_combined + theta_bs)
    gamma = np.clip(gamma, 0.0, 0.99)  # cap at 0.99 to keep some learning

    return gamma, bsdt, theta_bs, beta


# ══════════════════════════════════════════════════════════════════
#  LYAPUNOV BOOSTING CONTROLLER
# ══════════════════════════════════════════════════════════════════
class LyapunovBoostingController:
    """
    Monitors LGBM training loss per round and applies
    Lyapunov-style step control to the boosting process.

    Gravity engine analogue:
      - Armijo backtracking → reduce learning rate if loss increases
      - La Salle invariance → early stop if loss plateaus

    Implementation:
      - LGBM callback that tracks eval metric per round
      - Adjusts learning rate via model parameters (not possible mid-train)
      - Instead: uses early_stopping_rounds + custom eval to achieve same effect
    """

    def __init__(self, patience=15, min_improvement=1e-5):
        self.patience = patience
        self.min_improvement = min_improvement
        self.losses = []
        self.best_loss = np.inf
        self.rounds_no_improve = 0
        self.stopped_round = None

    def callback(self, env):
        """LightGBM callback for Lyapunov-style monitoring."""
        # Get current training loss
        if env.evaluation_result_list:
            # Use first eval metric
            current_loss = env.evaluation_result_list[0][2]
            self.losses.append(current_loss)

            # Armijo-like: check sufficient decrease
            if current_loss < self.best_loss - self.min_improvement:
                self.best_loss = current_loss
                self.rounds_no_improve = 0
            else:
                self.rounds_no_improve += 1

            # La Salle convergence: stop if no improvement for patience rounds
            if self.rounds_no_improve >= self.patience:
                self.stopped_round = env.iteration
                raise lgb.callback.EarlyStopException(
                    env.iteration, env.evaluation_result_list)


# ══════════════════════════════════════════════════════════════════
#  FEATURE EXTRACTION (same as test_bank_lgbm.py)
# ══════════════════════════════════════════════════════════════════
def extract_features(X, X_ref, k=15, include_rt=True,
                     include_bsdt=True, include_betti=False):
    """Extract topology/tensor features for LGBM input."""
    views = []
    names = []

    if include_rt:
        desc = ReducedTensorDescriptor(k_neighbors=k)
        desc.fit(X_ref)
        D = desc.transform(X)
        n_eigs = desc.n_eigs
        views.append(D)
        rt_names = ['rt_grad_norm']
        rt_names += [f'rt_eig_{i}' for i in range(n_eigs)]
        rt_names += ['rt_mahalanobis', 'rt_medoid_dist',
                     'rt_trace_H', 'rt_det_sigma', 'rt_morse_index']
        names.extend(rt_names)

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

    N_meta = len(meta)
    if X_3d.shape[1] > N_meta:
        X_3d = X_3d[:, :N_meta, :]

    dates = pd.date_range('2005-01-01', '2023-12-31',
                          freq='QE')[:X_3d.shape[0]]

    y_crisis = np.array([1 if str(d.date()) in CRISIS_QUARTERS else 0
                         for d in dates], dtype=int)

    return X_3d, dates, y_crisis, meta


# ══════════════════════════════════════════════════════════════════
#  EXPANDING-WINDOW BENCHMARK
# ══════════════════════════════════════════════════════════════════
def run_variant(X_3d, dates, y_crisis, variant_name,
                include_rt=True, include_bsdt=True, include_betti=False,
                use_bsdt_damping=True, k=15):
    """
    Expanding-window benchmark with BSDT-damped or standard LGBM.

    At each quarter t:
      1. Train = quarters [0..t], Test = quarter [t+1]
      2. StandardScaler fit on training only
      3. Extract RT + BSDT + Betti features
      4. Compute BSDT γ-damping weights for training points
      5. Train LGBM with BSDT-damped objective (or standard)
      6. Lyapunov controller monitors boosting convergence
      7. Score test quarter
    """
    T, N, d = X_3d.shape
    calib_end_dt = pd.Timestamp(CALIB_END)
    n_calib = int((dates <= calib_end_dt).sum())

    q_scores = np.full(T, np.nan)
    gamma_means = np.full(T, np.nan)  # track mean damping per quarter

    print(f'\n  Variant: {variant_name}')
    print(f'  Features: RT={include_rt} BSDT={include_bsdt} Betti={include_betti}')
    print(f'  BSDT damping: {"YES (inside LGBM boosting)" if use_bsdt_damping else "NO (standard LGBM)"}')
    t0 = time.time()

    for t in range(BURN_IN, T - 1):
        # ── 1. Expanding window ──
        n_q = t + 1
        X_train_raw = X_3d[:n_q].reshape(n_q * N, d)
        X_test_raw = X_3d[t + 1].reshape(N, d)

        y_train = np.zeros(n_q * N, dtype=int)
        for t_idx in range(n_q):
            if str(dates[t_idx].date()) in CRISIS_QUARTERS:
                y_train[t_idx * N:(t_idx + 1) * N] = 1

        # ── 2. Scale (no leakage) ──
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train_raw).astype(np.float64)
        X_test = scaler.transform(X_test_raw).astype(np.float64)
        X_train = np.nan_to_num(X_train, nan=0.0, posinf=5.0, neginf=-5.0)
        X_test = np.nan_to_num(X_test, nan=0.0, posinf=5.0, neginf=-5.0)

        # ── 3. Normal reference ──
        normal_mask = (y_train == 0)
        X_ref = X_train[normal_mask]
        if len(X_ref) < 10:
            X_ref = X_train

        # ── 4. Extract features ──
        try:
            F_train, feat_names = extract_features(
                X_train, X_ref, k=k,
                include_rt=include_rt, include_bsdt=include_bsdt,
                include_betti=include_betti)
            F_test, _ = extract_features(
                X_test, X_ref, k=k,
                include_rt=include_rt, include_bsdt=include_bsdt,
                include_betti=include_betti)
        except Exception:
            F_train = X_train
            F_test = X_test
            feat_names = FEATURE_NAMES

        F_train = np.nan_to_num(F_train, nan=0.0, posinf=5.0, neginf=-5.0)
        F_test = np.nan_to_num(F_test, nan=0.0, posinf=5.0, neginf=-5.0)

        # ── 5. Train LGBM ──
        n_crisis = int(y_train.sum())
        n_normal = int((y_train == 0).sum())

        if n_crisis == 0:
            # Pre-crisis: unsupervised fallback
            if include_rt:
                desc = ReducedTensorDescriptor(k_neighbors=k)
                desc.fit(X_ref)
                test_scores = desc.score(X_test)
            else:
                test_scores = np.linalg.norm(
                    X_test - X_ref.mean(axis=0), axis=1)
        else:
            scale_pos = max(n_normal / max(n_crisis, 1), 1.0)

            if use_bsdt_damping:
                # ── BSDT damping: compute γ weights ──
                # This is the EXACT analogue of the gravity engine's
                # BSDT adaptive damping (Theorem C, eq:bsdamped)
                gamma, bsdt_obj, theta, beta = compute_bsdt_gamma(
                    X_train, X_ref, k=k)
                gamma_means[t + 1] = float(gamma.mean())

                # Create BSDT-damped objective
                objective = BSDTDampedObjective(gamma)

                # Lyapunov boosting controller
                lyapunov = LyapunovBoostingController(
                    patience=15, min_improvement=1e-5)

                # Train with custom objective + Lyapunov monitoring
                lgbm = lgb.LGBMClassifier(
                    n_estimators=300,
                    max_depth=6,
                    learning_rate=0.05,
                    num_leaves=31,
                    min_child_samples=max(5, n_crisis // 10),
                    scale_pos_weight=scale_pos,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    reg_alpha=0.1,
                    reg_lambda=1.0,
                    objective=objective,  # BSDT-damped objective
                    verbosity=-1,
                    random_state=42,
                    n_jobs=1,
                )

                # Fit with Lyapunov callback + eval set for monitoring
                try:
                    lgbm.fit(
                        F_train, y_train,
                        eval_set=[(F_train, y_train)],
                        eval_metric='binary_logloss',
                        callbacks=[
                            lyapunov.callback,
                            lgb.callback.log_evaluation(period=0),
                        ],
                    )
                except lgb.callback.EarlyStopException:
                    pass  # Lyapunov controller stopped — this is expected

                # Score: use raw leaf output → sigmoid for probability
                raw_pred = lgbm.predict(F_test, raw_score=True)
                test_scores = 1.0 / (1.0 + np.exp(-raw_pred))

            else:
                # ── Standard LGBM (control: no BSDT damping) ──
                lgbm = LGBMClassifier(
                    n_estimators=200,
                    max_depth=6,
                    learning_rate=0.05,
                    num_leaves=31,
                    min_child_samples=max(5, n_crisis // 10),
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
                test_scores = lgbm.predict_proba(F_test)[:, 1]

        q_scores[t + 1] = float(test_scores.mean())

        # Progress
        ds = str(dates[t + 1].date())
        crisis_mark = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
        if (t + 1) % 10 == 0 or ds in CRISIS_QUARTERS:
            valid = ~np.isnan(q_scores[:t + 2])
            y_sub = y_crisis[:t + 2]
            s_sub = q_scores[:t + 2]
            gamma_str = f'  γ̄={gamma_means[t+1]:.3f}' if not np.isnan(gamma_means[t+1]) else ''
            if valid.sum() > 2 and y_sub[valid].sum() > 0 and y_sub[valid].sum() < valid.sum():
                run_auc = roc_auc_score(y_sub[valid], s_sub[valid])
                print(f'    t={t+1:3d} {ds}  score={q_scores[t+1]:.4f}  '
                      f'runAUC={run_auc:.4f}{gamma_str}{crisis_mark}')
            else:
                print(f'    t={t+1:3d} {ds}  score={q_scores[t+1]:.4f}{gamma_str}{crisis_mark}')

        gc.collect()

    elapsed = time.time() - t0

    # ── Metrics ──
    valid = ~np.isnan(q_scores)
    y_v = y_crisis[valid]
    s_v = q_scores[valid]

    auc = roc_auc_score(y_v, s_v) if (y_v.sum() > 0 and y_v.sum() < len(y_v)) else 0.5

    # Calibration thresholds
    calib_s = q_scores[BURN_IN + 1:n_calib + 1]
    calib_s = calib_s[~np.isnan(calib_s)]
    if len(calib_s) >= 3:
        mu_c, sig_c = calib_s.mean(), calib_s.std()
        thresh_3s = mu_c + 3 * sig_c
    else:
        thresh_3s = np.nanpercentile(q_scores[valid], 90)

    # GFC-specific AUC
    gfc_set = set(CRISIS_EVENTS['GFC'])
    gfc_mask = np.array([str(dates[i].date()) in gfc_set for i in range(T)])
    gfc_or_normal = valid & (gfc_mask | (y_crisis == 0))
    gfc_auc = roc_auc_score(y_crisis[gfc_or_normal], q_scores[gfc_or_normal]) \
        if (gfc_or_normal.sum() > 2 and y_crisis[gfc_or_normal].sum() > 0) else 0.5

    # FAR
    normal_valid = valid & (y_crisis == 0)
    far_3s = float(np.mean(q_scores[normal_valid] > thresh_3s) * 100)

    # Per-event detection
    event_results = {}
    for ev_name, ev_dates in CRISIS_EVENTS.items():
        ev_mask = np.array([str(dates[i].date()) in ev_dates for i in range(T)])
        ev_scores = q_scores[ev_mask & valid]
        detected = int(np.sum(ev_scores > thresh_3s))
        total_ev = int(ev_mask.sum())
        max_ev = float(ev_scores.max()) if len(ev_scores) > 0 else 0
        event_results[ev_name] = {
            'detected_3sigma': detected,
            'total_quarters': total_ev,
            'max_score': max_ev,
        }

    # Best F1
    best_f1 = 0.0
    for pctl in range(50, 100, 1):
        thr = np.percentile(s_v, pctl)
        pred = (s_v > thr).astype(int)
        f = f1_score(y_v, pred, zero_division=0)
        if f > best_f1:
            best_f1 = f

    return {
        'variant': variant_name,
        'auc': auc,
        'gfc_auc': gfc_auc,
        'best_f1': best_f1,
        'far_3sigma': far_3s,
        'events': event_results,
        'time_sec': elapsed,
        'bsdt_damped': use_bsdt_damping,
    }, q_scores, gamma_means


# ══════════════════════════════════════════════════════════════════
#  LAYER 2: BSDT EARLY WARNING
# ══════════════════════════════════════════════════════════════════
def run_bsdt_alarm(X_3d, dates, y_crisis, k=15):
    """BSDT E_BS + MFLS direct early warning on raw data."""
    T, N, d = X_3d.shape
    n_calib = int((dates <= pd.Timestamp(CALIB_END)).sum())

    e_bs_scores = np.full(T, np.nan)
    mfls_scores = np.full(T, np.nan)

    t0 = time.time()
    for t in range(BURN_IN, T - 1):
        n_q = t + 1
        X_train_raw = X_3d[:n_q].reshape(n_q * N, d)
        X_test_raw = X_3d[t + 1].reshape(N, d)

        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train_raw).astype(np.float64)
        X_test = scaler.transform(X_test_raw).astype(np.float64)
        X_train = np.nan_to_num(X_train, nan=0.0, posinf=5.0, neginf=-5.0)
        X_test = np.nan_to_num(X_test, nan=0.0, posinf=5.0, neginf=-5.0)

        # Normal reference
        y_train_labels = np.zeros(n_q, dtype=int)
        for t_idx in range(n_q):
            if str(dates[t_idx].date()) in CRISIS_QUARTERS:
                y_train_labels[t_idx] = 1
        normal_q = np.where(y_train_labels == 0)[0]
        X_ref = np.vstack([X_train[qi * N:(qi + 1) * N] for qi in normal_q]) \
            if len(normal_q) > 0 else X_train

        try:
            bsdt = BSDTChannels(k=min(k, len(X_ref) - 1))
            bsdt.fit(X_ref)
            e_bs_scores[t + 1] = float(bsdt.energy(X_test).mean())
            mfls_scores[t + 1] = float(bsdt.mfls(X_test).mean())
        except Exception:
            pass

    elapsed = time.time() - t0
    return e_bs_scores, mfls_scores, elapsed


# ══════════════════════════════════════════════════════════════════
#  LAYER 3: MORSE + BETTI CONFIRMATION
# ══════════════════════════════════════════════════════════════════
def run_morse_betti(X_3d, dates, y_crisis, k=15):
    """Morse + Betti structural confirmation on raw data."""
    T, N, d = X_3d.shape

    morse_scores = np.full(T, np.nan)
    betti_scores = np.full(T, np.nan)

    t0 = time.time()
    for t in range(BURN_IN, T - 1):
        n_q = t + 1
        X_train_raw = X_3d[:n_q].reshape(n_q * N, d)
        X_test_raw = X_3d[t + 1].reshape(N, d)

        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train_raw).astype(np.float64)
        X_test = scaler.transform(X_test_raw).astype(np.float64)
        X_train = np.nan_to_num(X_train, nan=0.0, posinf=5.0, neginf=-5.0)
        X_test = np.nan_to_num(X_test, nan=0.0, posinf=5.0, neginf=-5.0)

        # Normal reference
        y_train_labels = np.zeros(n_q, dtype=int)
        for t_idx in range(n_q):
            if str(dates[t_idx].date()) in CRISIS_QUARTERS:
                y_train_labels[t_idx] = 1
        normal_q = np.where(y_train_labels == 0)[0]
        X_ref = np.vstack([X_train[qi * N:(qi + 1) * N] for qi in normal_q]) \
            if len(normal_q) > 0 else X_train

        try:
            morse = MorseTopologyAlarm(k=k)
            morse.fit(X_ref)
            morse_scores[t + 1] = float(morse.score(X_test).mean())
        except Exception:
            pass

        try:
            betti = BettiBarcodeSuite(k=min(k + 5, 25), n_scales=8)
            betti.fit(X_ref)
            betti_scores[t + 1] = float(betti.score(X_test).mean())
        except Exception:
            pass

    elapsed = time.time() - t0
    return morse_scores, betti_scores, elapsed


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════
def main():
    t_global = time.time()

    print('=' * 90)
    print('  LGBM with BSDT-Damped Internal Iteration — Banking Benchmark')
    print('  BSDT damping INSIDE LGBM boosting rounds (Theorem C analogue)')
    print('  Lyapunov v2 controls boosting convergence')
    print('=' * 90)

    X_3d, dates, y_crisis, meta = load_bank_panel()
    T, N, d = X_3d.shape
    print(f'\n  Panel: T={T} quarters, N={N} banks, d={d} features')
    print(f'  Crisis quarters: {int(y_crisis.sum())}/{T}')
    print(f'  Normal quarters: {int((y_crisis == 0).sum())}/{T}')

    # ── LGBM VARIANTS ──
    variants = {
        'LGBM_BSDT_damped(RT+BSDT)': dict(
            include_rt=True, include_bsdt=True, include_betti=False,
            use_bsdt_damping=True),
        'LGBM_standard(RT+BSDT)': dict(
            include_rt=True, include_bsdt=True, include_betti=False,
            use_bsdt_damping=False),
        'LGBM_BSDT_damped(RT_only)': dict(
            include_rt=True, include_bsdt=False, include_betti=False,
            use_bsdt_damping=True),
        'LGBM_BSDT_damped(Betti)': dict(
            include_rt=False, include_bsdt=False, include_betti=True,
            use_bsdt_damping=True),
        'LGBM_BSDT_damped(RT+Betti)': dict(
            include_rt=True, include_bsdt=False, include_betti=True,
            use_bsdt_damping=True),
    }

    all_results = {}
    all_scores = {}

    for vname, vparams in variants.items():
        print(f'\n{"─"*70}')
        try:
            result, q_scores, gamma_means = run_variant(
                X_3d, dates, y_crisis, vname, k=15, **vparams)
            all_results[vname] = result
            all_scores[vname] = q_scores.tolist()

            print(f'\n  {vname}:')
            print(f'    AUC={result["auc"]:.4f}  GFC-AUC={result["gfc_auc"]:.4f}  '
                  f'F1={result["best_f1"]:.3f}  FAR(3σ)={result["far_3sigma"]:.1f}%  '
                  f'Time={result["time_sec"]:.1f}s')
            for ev, er in result['events'].items():
                print(f'    {ev}: {er["detected_3sigma"]}/{er["total_quarters"]} (3σ)  '
                      f'max={er["max_score"]:.4f}')

            # Gamma stats
            g_valid = gamma_means[~np.isnan(gamma_means)]
            if len(g_valid) > 0:
                print(f'    BSDT γ̄: mean={g_valid.mean():.3f} '
                      f'min={g_valid.min():.3f} max={g_valid.max():.3f}')

        except Exception as e:
            print(f'  ERROR: {e}')
            import traceback; traceback.print_exc()

    # ── LAYER 2: BSDT EARLY WARNING ──
    print(f'\n{"═"*70}')
    print('  LAYER 2: BSDT Early Warning (E_BS + MFLS)')
    print(f'{"═"*70}')

    e_bs, mfls, dt_l2 = run_bsdt_alarm(X_3d, dates, y_crisis)

    valid = ~np.isnan(mfls)
    y_v = y_crisis[valid]
    if y_v.sum() > 0 and y_v.sum() < len(y_v):
        mfls_auc = roc_auc_score(y_v, mfls[valid])
        ebs_auc = roc_auc_score(y_v, e_bs[valid])
    else:
        mfls_auc = ebs_auc = 0.5

    print(f'  BSDT_mfls  AUC={mfls_auc:.4f}  Time={dt_l2:.1f}s')
    print(f'  BSDT_e_bs  AUC={ebs_auc:.4f}')

    # ── LAYER 3: MORSE + BETTI ──
    print(f'\n{"═"*70}')
    print('  LAYER 3: Morse + Betti Structural Confirmation')
    print(f'{"═"*70}')

    morse_s, betti_s, dt_l3 = run_morse_betti(X_3d, dates, y_crisis)

    valid_m = ~np.isnan(morse_s)
    valid_b = ~np.isnan(betti_s)
    morse_auc = roc_auc_score(y_crisis[valid_m], morse_s[valid_m]) \
        if (y_crisis[valid_m].sum() > 0 and y_crisis[valid_m].sum() < valid_m.sum()) else 0.5
    betti_auc = roc_auc_score(y_crisis[valid_b], betti_s[valid_b]) \
        if (y_crisis[valid_b].sum() > 0 and y_crisis[valid_b].sum() < valid_b.sum()) else 0.5

    print(f'  Morse      AUC={morse_auc:.4f}  Time={dt_l3:.1f}s')
    print(f'  Betti      AUC={betti_auc:.4f}')

    # ── SUMMARY ──
    total_time = time.time() - t_global
    print(f'\n\n{"═"*90}')
    print('  SUMMARY: BSDT-Damped vs Standard LGBM')
    print(f'{"═"*90}')
    print(f'  {"Variant":<35} {"AUC":>6} {"GFC":>6} {"F1":>6} {"FAR%":>6} {"Time":>6}')
    print(f'  {"─"*35} {"─"*6} {"─"*6} {"─"*6} {"─"*6} {"─"*6}')

    for vname, r in all_results.items():
        print(f'  {vname:<35} {r["auc"]:6.4f} {r["gfc_auc"]:6.4f} '
              f'{r["best_f1"]:6.3f} {r["far_3sigma"]:5.1f}% {r["time_sec"]:5.0f}s')

    print(f'  {"─"*35} {"─"*6} {"─"*6} {"─"*6} {"─"*6} {"─"*6}')
    print(f'  {"BSDT_mfls (Layer 2)":<35} {mfls_auc:6.4f}')
    print(f'  {"BSDT_e_bs (Layer 2)":<35} {ebs_auc:6.4f}')
    print(f'  {"Morse (Layer 3)":<35} {morse_auc:6.4f}')
    print(f'  {"Betti (Layer 3)":<35} {betti_auc:6.4f}')

    print(f'\n  Total time: {total_time:.0f}s ({total_time/60:.1f} min)')

    # ── SAVE ──
    save_data = {
        'description': 'LGBM with BSDT-damped internal iteration (banking)',
        'variants': all_results,
        'layer1_scores': all_scores,
        'layer2_scores': {
            'e_bs': [float(x) if not np.isnan(x) else None for x in e_bs],
            'mfls': [float(x) if not np.isnan(x) else None for x in mfls],
        },
        'layer3_scores': {
            'morse': [float(x) if not np.isnan(x) else None for x in morse_s],
            'betti': [float(x) if not np.isnan(x) else None for x in betti_s],
        },
        'layer2_auc': {'mfls': mfls_auc, 'e_bs': ebs_auc},
        'layer3_auc': {'morse': morse_auc, 'betti': betti_auc},
    }

    out_path = os.path.join(RESULTS_DIR, 'bank_lgbm_bsdt_damped_results.json')
    with open(out_path, 'w') as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f'\n  Saved → {out_path}')


if __name__ == '__main__':
    main()
