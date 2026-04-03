#!/usr/bin/env python3
"""
LGBM Iterative Engine — Banking Benchmark
==========================================

Replaces Gravity/Molecular physics forces with LGBM gradient forces
while maintaining the SIAM paper's iteration architecture (§6):

  Standard engine:   Ẋ = F_physics(X) − γ(E_BS)·∇E_BS(X)
  LGBM engine:       Ẋ = F_lgbm(X)   − γ(E_BS)·∇E_BS(X)

Where:
  F_lgbm(x) = β · P(crisis|x) · ∇_x P(crisis|x)   [LGBM gradient force]
  F_radial   = −α · (x − μ)                          [centering spring]
  F_damp     = −γ(E_BS) · ∇E_BS(x)                   [BSDT adaptive damping]
  γ(E)       = E_BS / (E_BS + θ)                      [Theorem C, eq:bsdamped]
  V(X)       = α/2 · Σ‖x_i − μ‖²                     [Lyapunov candidate]

Lyapunov v2 (Proposition lyapv2):
  Armijo–ISS descent on V, treating F_lgbm as bounded perturbation.
  La Salle invariance termination.

Post-simulation scoring (on X_final_):
  ReducedTensor + Morse + Betti + BSDT + ExpoGate + FusedSystemScorer

Layer 2 — BSDT Early Warning Alarm (primary detector, Algorithm 1):
  E_BS (blind-spot energy), MFLS (‖∇E_BS‖), morse_alarm (∇²E_BS Hessian)
  BSDT detects FIRST — via Hessian eigenvalue analysis of E_BS.
  Morse index ≥ 1 at saddle ⇒ phase transition ⇒ alarm.

Layer 3 — Morse + Betti Structural Confirmation:
  MorseTopologyAlarm (4D kNN) + BettiBarcodeSuite (19D topology)
  Confirms BSDT alarms reflect genuine structural manifold changes.

Data: FDIC G-SIB panel (T=76, N=25, d=5)

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
    FusedSystemScorer,
    LyapunovStabiliser,
    _MFLSExpoGate,
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

CRISIS_EVENTS = {
    'GFC':          ['2007-12-31', '2008-03-31', '2008-06-30', '2008-09-30',
                     '2008-12-31', '2009-03-31', '2009-06-30'],
    'EU_Sovereign': ['2011-09-30', '2011-12-31', '2012-03-31', '2012-06-30'],
    'COVID':        ['2020-03-31', '2020-06-30'],
}

SCORING_VARIANTS = [
    'fused', 'expogate', 'reduced_tensor', 'morse', 'bsdt_energy',
]

CHECKPOINT_PATH = os.path.join(RESULTS_DIR, 'bank_lgbm_engine_checkpoint.json')


def save_checkpoint(q_scores, last_t, layer_tag='layer1'):
    """Save progress so we can resume if terminal dies."""
    data = {
        'last_t': last_t,
        'layer': layer_tag,
        'scores': {v: [float(x) if not np.isnan(x) else None
                       for x in q_scores[v]]
                   for v in q_scores},
    }
    with open(CHECKPOINT_PATH, 'w') as f:
        json.dump(data, f)


def load_checkpoint(expected_variants):
    """Load checkpoint if available. Returns (q_scores, last_t) or None."""
    if not os.path.exists(CHECKPOINT_PATH):
        return None
    try:
        with open(CHECKPOINT_PATH) as f:
            data = json.load(f)
        q_scores = {}
        for v in expected_variants:
            arr = np.full(76, np.nan)  # T=76
            if v in data.get('scores', {}):
                for i, val in enumerate(data['scores'][v]):
                    if val is not None:
                        arr[i] = val
            q_scores[v] = arr
        return q_scores, data['last_t']
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════
#  LGBM ITERATIVE ENGINE  (replaces Gravity/Molecular physics)
# ══════════════════════════════════════════════════════════════════

class LGBMIterativeEngine:
    """
    LGBM-driven iterative engine with BSDT damping + Lyapunov v2.

    Replaces the pairwise physics force (LJ / Gaussian+Coulomb) with
    LGBM-predicted gradient forces.  The iteration loop, BSDT damping,
    and Lyapunov stability controller are IDENTICAL to the SIAM paper
    engines (§6, Prop. lyapv2).

    Force decomposition:
      F_total = F_lgbm + F_radial + F_damp

    F_lgbm   = β · P(x) · ∇_x P(x)
               P = LGBM-predicted crisis probability (trained on labels)
               ∇P = finite-difference gradient in feature space
               Anomalous points (high P) get large forces in the risk
               gradient direction.  Normal points (P ≈ 0) barely move.

    F_radial = −α · (x − μ)
               Same centering spring as Gravity engine.

    F_damp   = −γ(E_BS) · ∇E_BS(x)
               BSDT adaptive friction (Theorem C, eq:bsdamped).
               Prevents collapse above the critical manifold C*.
               γ(E) = E_combined / (E_combined + θ)
               E_combined = E_BS + β_mfls · ‖∇E_BS‖

    Lyapunov candidate: V(X) = α/2 · Σ‖x_i − μ‖²  (radial energy).
    F_lgbm treated as bounded ISS perturbation (same as Gravity engine
    treats pairwise force).

    After convergence → score X_final_ with:
      ReducedTensor, Morse, Betti, BSDT, ExpoGate, FusedSystemScorer
    """

    def __init__(self,
                 alpha_radial: float = 0.1,
                 eta: float = 0.05,
                 iterations: int = 60,
                 k_neighbors: int = 15,
                 beta_lgbm: float = 2.0,
                 fd_eps: float = 0.01,
                 normalize: bool = True,
                 use_fused: bool = True):
        self.alpha_radial = alpha_radial
        self.eta = eta
        self.iterations = iterations
        self.k_neighbors = k_neighbors
        self.beta_lgbm = beta_lgbm
        self.fd_eps = fd_eps
        self.normalize = normalize
        self.use_fused = use_fused

        self.stabiliser = LyapunovStabiliser(min_eta=1e-5)

        self.scaler_ = None
        self.mu_ = None
        self.X_final_ = None
        self._convergence_report = None

    @staticmethod
    def _train_force_lgbm(X, y):
        """Train a smooth LGBM force model (low complexity for stable gradients)."""
        n_pos = int(y.sum())
        n_neg = int(len(y) - n_pos)
        if n_pos < 2 or n_neg < 2:
            return None

        lgbm = LGBMClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            num_leaves=15,
            min_child_samples=max(5, n_pos // 5),
            scale_pos_weight=max(n_neg / max(n_pos, 1), 1.0),
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            verbosity=-1,
            random_state=42,
            n_jobs=1,
        )
        lgbm.fit(X, y)
        return lgbm

    def _lgbm_gradient(self, X, lgbm):
        """
        Vectorized finite-difference gradient of P(crisis).

        Batches all 2*d perturbations into a single predict_proba call
        for ~5x speedup over the per-dimension loop.

        Returns
        -------
        P      : (n,) crisis probability
        grad_P : (n, d) gradient vectors
        """
        n, d = X.shape
        eps = self.fd_eps

        # Build batch: [X, X+eps*e1, X-eps*e1, X+eps*e2, X-eps*e2, ...]
        # Shape: ((1 + 2*d) * n, d)
        batch_parts = [X]
        for j in range(d):
            X_p = X.copy(); X_p[:, j] += eps
            X_m = X.copy(); X_m[:, j] -= eps
            batch_parts.append(X_p)
            batch_parts.append(X_m)
        batch = np.vstack(batch_parts)

        # Single predict_proba call for entire batch
        P_all = lgbm.predict_proba(batch)[:, 1]

        P = P_all[:n]
        grad = np.zeros((n, d))
        for j in range(d):
            P_p = P_all[(1 + 2*j) * n : (2 + 2*j) * n]
            P_m = P_all[(2 + 2*j) * n : (3 + 2*j) * n]
            grad[:, j] = (P_p - P_m) / (2 * eps)

        grad = np.clip(grad, -10.0, 10.0)
        return P, grad

    def _radial_energy(self, X):
        """Radial Lyapunov candidate: V = α/2 · Σ‖x − μ‖²."""
        return 0.5 * self.alpha_radial * float(np.sum((X - self.mu_) ** 2))

    def fit_score(self, X, y=None):
        """
        Run LGBM iterative engine → X_final_ → multi-method scores.

        Parameters
        ----------
        X : (n, d) — all data points (train + test together)
        y : (n,) — labels: 0=normal, 1=crisis, -1=unlabeled (test)
            LGBM trains only on y ∈ {0,1}. Points with y=-1 are
            simulated but not used for training or calibration.
        """
        # ── 1. Normalize ──
        if self.normalize:
            self.scaler_ = StandardScaler()
            X_work = self.scaler_.fit_transform(X).astype(np.float64)
        else:
            X_work = X.astype(np.float64).copy()

        n, d = X_work.shape

        # Masks
        if y is not None:
            labeled_mask = (y >= 0)
            normal_mask = (y == 0)
        else:
            labeled_mask = np.ones(n, dtype=bool)
            normal_mask = np.ones(n, dtype=bool)

        self.mu_ = (X_work[normal_mask].mean(axis=0) if normal_mask.sum() > 0
                    else X_work.mean(axis=0))

        # ── 2. Train LGBM force model (on labeled data only) ──
        lgbm = None
        if y is not None and labeled_mask.sum() > 10:
            lgbm = self._train_force_lgbm(
                X_work[labeled_mask], y[labeled_mask])

        # ── 3. BSDT calibration on initial normal positions ──
        k_use = min(self.k_neighbors, max(n - 1, 2))
        bsdt_damper = BSDTChannels(k=k_use)
        X_ref_init = (X_work[normal_mask] if normal_mask.sum() > 5
                      else X_work)
        bsdt_damper.fit(X_ref_init)
        e_ref = bsdt_damper.energy(X_ref_init)
        theta_bs = float(np.median(e_ref)) + 1e-10
        mfls_ref = bsdt_damper.mfls(X_ref_init)
        mfls_med = float(np.median(mfls_ref)) + 1e-10
        beta_mfls = theta_bs / mfls_med

        # ── 4. Euler iteration with Lyapunov v2 + BSDT damping ──
        self.stabiliser.reset()
        eta = self.eta

        for step in range(self.iterations):
            # ── LGBM gradient force ──
            if lgbm is not None:
                P, grad_P = self._lgbm_gradient(X_work, lgbm)
                # F = β · P · ∇P  (risk-weighted gradient ascent)
                F_lgbm = self.beta_lgbm * P[:, None] * grad_P
            else:
                F_lgbm = np.zeros_like(X_work)

            # ── Radial centering spring (same as Gravity engine) ──
            F_radial = -self.alpha_radial * (X_work - self.mu_)

            # ── BSDT + MFLS adaptive damping (Theorem C, eq:bsdamped) ──
            e_bs = bsdt_damper.energy(X_work)
            grad_bs = bsdt_damper._gradient_vectors(X_work)
            mfls_bs = np.linalg.norm(grad_bs, axis=1)
            e_combined = e_bs + beta_mfls * mfls_bs
            gamma_bs = e_combined / (e_combined + theta_bs)
            F_damp = -gamma_bs[:, None] * grad_bs

            # ── Combined force ──
            F_total = F_lgbm + F_radial + F_damp
            F_total = self.stabiliser.clamp_forces(F_total)

            # ── Armijo on radial energy with ISS margin for F_lgbm ──
            E_old = self._radial_energy(X_work)
            grad_norm_sq = float(np.sum(F_total ** 2))
            perturbation_norm = float(np.sqrt(np.sum(F_lgbm ** 2)))

            X_candidate = X_work + eta * F_total
            E_new = self._radial_energy(X_candidate)

            accept, eta = self.stabiliser.accept_step(
                E_old, E_new, grad_norm_sq, eta,
                perturbation_norm=perturbation_norm
            )

            if accept:
                X_work = X_candidate
            else:
                X_work = X_work + eta * F_total

            displacement = eta * np.max(np.linalg.norm(F_total, axis=1))
            if self.stabiliser.check_convergence(grad_norm_sq, displacement):
                break

        self.X_final_ = X_work
        self._convergence_report = self.stabiliser.report()

        # ── 5. Post-simulation scoring on X_final_ ──
        X_ref_final = X_work[normal_mask]
        if len(X_ref_final) < 5:
            X_ref_final = X_work
        k_post = min(self.k_neighbors, len(X_ref_final) - 1)

        scores = {}

        # A. FusedSystemScorer (Morse + Betti + UDL + BSDT, eq:fusion)
        try:
            fused = FusedSystemScorer(k=k_post)
            fused.fit(X_ref_final, X_sim=X_work)
            scores['fused'] = fused.score(X_work)
        except Exception:
            scores['fused'] = np.zeros(n)

        # B. ExpoGate MFLS (BSDT channels → supervised MFLS)
        try:
            bsdt_post = BSDTChannels(k=k_post)
            bsdt_post.fit(X_ref_final)
            ch_ref = bsdt_post.channels(X_ref_final)
            C_ref = np.column_stack([ch_ref['delta_C'], ch_ref['delta_G'],
                                     ch_ref['delta_A'], ch_ref['delta_T']])
            ch_all = bsdt_post.channels(X_work)
            C_all = np.column_stack([ch_all['delta_C'], ch_all['delta_G'],
                                     ch_all['delta_A'], ch_all['delta_T']])
            # ExpoGate supervised labels: normal ref = 0
            y_expo = np.zeros(len(X_ref_final), dtype=int)
            expo = _MFLSExpoGate()
            expo.fit(C_ref, y_expo)
            scores['expogate'] = expo.score(C_all)
        except Exception:
            scores['expogate'] = np.zeros(n)

        # C. ReducedTensor descriptor score
        try:
            k_rt = min(k_post, len(X_ref_final) - 1)
            rt = ReducedTensorDescriptor(k_neighbors=max(k_rt, 2))
            rt.fit(X_ref_final)
            scores['reduced_tensor'] = rt.score(X_work)
        except Exception:
            scores['reduced_tensor'] = np.zeros(n)

        # D. MorseTopologyAlarm
        try:
            morse = MorseTopologyAlarm(k=k_post)
            morse.fit(X_ref_final)
            scores['morse'] = morse.score(X_work)
        except Exception:
            scores['morse'] = np.zeros(n)

        # E. BSDT energy (post-simulation)
        try:
            bsdt_e = BSDTChannels(k=k_post)
            bsdt_e.fit(X_ref_final)
            scores['bsdt_energy'] = bsdt_e.energy(X_work)
        except Exception:
            scores['bsdt_energy'] = np.zeros(n)

        return scores


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
def run_benchmark(X_3d, dates, y_crisis):
    """
    Per-quarter expanding-window LGBM iterative engine.

    At each step t:
      1. All data [0..t+1] simulated together (train + test)
      2. LGBM trained on [0..t] labels only (no future leakage)
      3. BSDT calibrated on normals from [0..t]
      4. Iterate: F_lgbm + F_radial + F_damp, Lyapunov-controlled
      5. Score X_final_ with 5 methods
      6. Test quarter [t+1] score = mean of last N point scores
    """
    T, N, d = X_3d.shape
    calib_end_dt = pd.Timestamp(CALIB_END)
    n_calib = int((dates <= calib_end_dt).sum())

    # Per-variant quarterly scores
    q_scores = {v: np.full(T, np.nan) for v in SCORING_VARIANTS}

    print(f'\n  Expanding window: T={T}, N={N}, d={d}')
    print(f'  Calibration: {n_calib} quarters (→ {CALIB_END})')
    print(f'  BURN_IN: {BURN_IN}')
    t0 = time.time()

    # Resume from checkpoint if available
    ckpt = load_checkpoint(SCORING_VARIANTS)
    resume_from = BURN_IN
    if ckpt is not None:
        q_scores_ckpt, last_t = ckpt
        if last_t > BURN_IN:
            q_scores = q_scores_ckpt
            resume_from = last_t + 1
            print(f'  *** Resuming from checkpoint t={last_t} ***')

    for t in range(resume_from, T - 1):
        # ── 1. Assemble data [0..t+1] ──
        n_q = t + 2  # quarters 0 to t+1
        X_all = X_3d[:n_q].reshape(n_q * N, d)

        # Labels: 0/1 for training quarters [0..t], -1 for test [t+1]
        y_all = np.full(n_q * N, -1, dtype=int)
        for q_idx in range(t + 1):  # 0..t (training only)
            label = 1 if str(dates[q_idx].date()) in CRISIS_QUARTERS else 0
            y_all[q_idx * N : (q_idx + 1) * N] = label

        # ── 2. Run LGBM iterative engine ──
        engine = LGBMIterativeEngine(
            alpha_radial=0.1,
            eta=0.05,
            iterations=60,
            k_neighbors=15,
            beta_lgbm=2.0,
            fd_eps=0.01,
        )

        try:
            scores_dict = engine.fit_score(X_all, y_all)
        except Exception as e:
            print(f'    ERROR at t={t}: {e}')
            continue

        # ── 3. Extract test-quarter scores (last N points) ──
        for v in SCORING_VARIANTS:
            if v in scores_dict and len(scores_dict[v]) >= N:
                q_scores[v][t + 1] = float(scores_dict[v][-N:].mean())

        # ── 4. Progress reporting ──
        ds = str(dates[t + 1].date())
        crisis_mark = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
        elapsed = time.time() - t0

        if (t + 1) % 10 == 0 or ds in CRISIS_QUARTERS:
            # Running AUC for best variant
            best_v = 'fused'
            valid = ~np.isnan(q_scores[best_v][:t + 2])
            y_sub = y_crisis[:t + 2]
            if valid.sum() > 2 and y_sub[valid].sum() > 0 and y_sub[valid].sum() < valid.sum():
                run_auc = roc_auc_score(y_sub[valid], q_scores[best_v][:t + 2][valid])
                print(f'    t={t+1:3d} {ds}  fused={q_scores["fused"][t+1]:.4f}  '
                      f'rt={q_scores["reduced_tensor"][t+1]:.4f}  '
                      f'runAUC={run_auc:.4f}  '
                      f'{elapsed:.0f}s{crisis_mark}')
            else:
                print(f'    t={t+1:3d} {ds}  fused={q_scores["fused"][t+1]:.4f}  '
                      f'rt={q_scores["reduced_tensor"][t+1]:.4f}  '
                      f'{elapsed:.0f}s{crisis_mark}')

        # Checkpoint every 5 quarters
        if (t + 1) % 5 == 0:
            save_checkpoint(q_scores, t)

        gc.collect()

    # Final checkpoint
    save_checkpoint(q_scores, T - 2)
    total_time = time.time() - t0
    return q_scores, total_time


# ══════════════════════════════════════════════════════════════════
#  METRICS
# ══════════════════════════════════════════════════════════════════
def compute_metrics(q_scores, dates, y_crisis, variant_name):
    """Compute AUC, FAR, detection, lead time for a scoring variant."""
    T = len(dates)
    N_calib = int((dates <= pd.Timestamp(CALIB_END)).sum())
    s = q_scores

    valid = ~np.isnan(s)
    y_v = y_crisis[valid]
    s_v = s[valid]

    # AUC
    if y_v.sum() > 0 and y_v.sum() < len(y_v):
        auc = roc_auc_score(y_v, s_v)
    else:
        auc = 0.5

    # Calibration threshold
    calib_s = s[BURN_IN + 1 : N_calib + 1]
    calib_s = calib_s[~np.isnan(calib_s)]
    if len(calib_s) >= 3:
        mu_c, sig_c = calib_s.mean(), calib_s.std()
        thresh_3s = mu_c + 3 * max(sig_c, 1e-8)
        thresh_2s = mu_c + 2 * max(sig_c, 1e-8)
    else:
        thresh_3s = thresh_2s = np.nanpercentile(s_v, 90)

    # FAR on normals
    normal_valid = valid & (y_crisis == 0)
    normal_s = s[normal_valid]
    far_3s = float(np.mean(normal_s > thresh_3s) * 100)

    # GFC-specific AUC
    gfc_set = set(CRISIS_EVENTS['GFC'])
    gfc_mask = np.array([str(dates[i].date()) in gfc_set for i in range(T)])
    gfc_normal = valid & (gfc_mask | (y_crisis == 0))
    if gfc_normal.sum() > 2 and y_crisis[gfc_normal].sum() > 0:
        gfc_auc = roc_auc_score(y_crisis[gfc_normal], s[gfc_normal])
    else:
        gfc_auc = 0.5

    # Best F1
    best_f1 = 0.0
    for pctl in range(50, 100):
        thr = np.percentile(s_v, pctl)
        pred = (s_v > thr).astype(int)
        f = f1_score(y_v, pred, zero_division=0)
        if f > best_f1:
            best_f1 = f

    # Per-event detection
    events = {}
    for ev_name, ev_dates in CRISIS_EVENTS.items():
        ev_mask = np.array([str(dates[i].date()) in ev_dates for i in range(T)])
        ev_scores = s[ev_mask & valid]
        detected_3s = int(np.sum(ev_scores > thresh_3s))
        total = int(ev_mask.sum())
        max_sc = float(ev_scores.max()) if len(ev_scores) > 0 else 0
        events[ev_name] = {
            'detected': detected_3s, 'total': total, 'max': max_sc
        }

    # Lead time: first alarm before GFC
    gfc_first = pd.Timestamp('2007-12-31')
    lead = None
    for i in range(T):
        if valid[i] and s[i] > thresh_3s and dates[i] < gfc_first:
            lead = str(dates[i].date())
            break

    return {
        'variant': variant_name,
        'auc': auc,
        'gfc_auc': gfc_auc,
        'best_f1': best_f1,
        'far_3sigma': far_3s,
        'events': events,
        'gfc_lead': lead,
        'threshold_3s': thresh_3s,
    }


# ══════════════════════════════════════════════════════════════════
#  LAYER 2: BSDT EARLY WARNING ALARM (primary detector)
#  Uses E_BS, MFLS, and morse_alarm() on Hessian of E_BS
#  This is the SIAM paper's Algorithm 1 — BSDT detects first.
# ══════════════════════════════════════════════════════════════════
def run_bsdt_early_warning(X_3d, dates, y_crisis):
    """BSDT-based early warning — primary detector per SIAM §2.2.

    Computes per-quarter:
      - E_BS:  blind-spot energy (Fisher-weighted sum of δ²)
      - MFLS:  ||∇E_BS|| gradient-norm (multi-factor latent score)
      - bsdt_score: blended 0.5*E_BS + 0.5*MFLS (normalised)
      - morse_alarm: Hessian eigenvalues of E_BS → Morse index
        ind ≥ 1 ⇒ saddle ⇒ phase transition alarm
    """
    T, N, d = X_3d.shape

    bsdt_e_scores   = np.full(T, np.nan)  # E_BS per quarter
    bsdt_mfls_scores = np.full(T, np.nan) # MFLS per quarter
    bsdt_blend_scores = np.full(T, np.nan) # blended
    morse_index_arr  = np.full(T, np.nan)  # Morse index of E_BS
    morse_alarm_arr  = np.full(T, False)   # ind >= 1 alarm
    hessian_trace    = np.full(T, np.nan)
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
        y_labels = np.zeros(n_q, dtype=int)
        for q_idx in range(n_q):
            if str(dates[q_idx].date()) in CRISIS_QUARTERS:
                y_labels[q_idx] = 1
        normal_q = np.where(y_labels == 0)[0]
        X_ref = np.vstack([X_train[q * N:(q + 1) * N] for q in normal_q]) \
            if len(normal_q) > 0 else X_train

        try:
            k_use = min(15, len(X_ref) - 1)
            bsdt = BSDTChannels(k=max(k_use, 2))
            bsdt.fit(X_ref)

            # E_BS and MFLS on test quarter
            e_bs = bsdt.energy(X_test)
            mfls = bsdt.mfls(X_test)
            bsdt_score = bsdt.score(X_test)   # blended 0.5*E + 0.5*MFLS

            bsdt_e_scores[t + 1] = float(e_bs.mean())
            bsdt_mfls_scores[t + 1] = float(mfls.mean())
            bsdt_blend_scores[t + 1] = float(bsdt_score.mean())

            # Morse alarm on E_BS Hessian (Algorithm 1)
            alarm_result = bsdt.morse_alarm(X_test)
            morse_index_arr[t + 1] = alarm_result['morse_index']
            morse_alarm_arr[t + 1] = alarm_result['alarm']
            hessian_trace[t + 1] = alarm_result['trace']

        except Exception as e:
            bsdt_e_scores[t + 1] = 0.0
            bsdt_mfls_scores[t + 1] = 0.0
            bsdt_blend_scores[t + 1] = 0.0

    dt = time.time() - t0
    return {
        'e_bs': bsdt_e_scores,
        'mfls': bsdt_mfls_scores,
        'bsdt_blend': bsdt_blend_scores,
        'morse_index': morse_index_arr,
        'morse_alarm': morse_alarm_arr,
        'hessian_trace': hessian_trace,
    }, dt


# ══════════════════════════════════════════════════════════════════
#  LAYER 3: MORSE + BETTI STRUCTURAL CONFIRMATION
#  Confirms BSDT alarms with topological persistence analysis
# ══════════════════════════════════════════════════════════════════
def run_morse_betti_confirmation(X_3d, dates, y_crisis):
    """Morse + Betti structural confirmation — validates BSDT alarms.

    Runs MorseTopologyAlarm (4D kNN features) and BettiBarcodeSuite
    (19D multi-scale topology) on raw data to confirm whether BSDT
    alarms reflect genuine structural changes in the data manifold.
    """
    T, N, d = X_3d.shape

    morse_scores = np.full(T, np.nan)
    betti_scores = np.full(T, np.nan)
    fused_mb_scores = np.full(T, np.nan)  # Fisher VR fusion of Morse+Betti
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
        y_labels = np.zeros(n_q, dtype=int)
        for q_idx in range(n_q):
            if str(dates[q_idx].date()) in CRISIS_QUARTERS:
                y_labels[q_idx] = 1
        normal_q = np.where(y_labels == 0)[0]
        X_ref = np.vstack([X_train[q * N:(q + 1) * N] for q in normal_q]) \
            if len(normal_q) > 0 else X_train

        k_use = min(15, len(X_ref) - 1)

        # Morse
        try:
            morse = MorseTopologyAlarm(k=max(k_use, 2))
            morse.fit(X_ref)
            ms = morse.score(X_test)
            morse_scores[t + 1] = float(ms.mean())
        except Exception:
            morse_scores[t + 1] = 0.0

        # Betti
        try:
            betti = BettiBarcodeSuite(k=min(max(k_use + 5, 5), 25))
            betti.fit(X_ref)
            bs = betti.score(X_test)
            betti_scores[t + 1] = float(bs.mean())
        except Exception:
            betti_scores[t + 1] = 0.0

        # Fisher VR fusion of Morse + Betti
        m_val = morse_scores[t + 1]
        b_val = betti_scores[t + 1]
        if not (np.isnan(m_val) or np.isnan(b_val)):
            # Simple Fisher-style: weight by signal magnitude
            total = abs(m_val) + abs(b_val) + 1e-10
            fused_mb_scores[t + 1] = (m_val * abs(m_val) + b_val * abs(b_val)) / total
        else:
            fused_mb_scores[t + 1] = m_val if not np.isnan(m_val) else b_val

    dt = time.time() - t0
    return {
        'morse': morse_scores,
        'betti': betti_scores,
        'morse_betti_fused': fused_mb_scores,
    }, dt


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════
def main():
    t_global = time.time()

    print('=' * 80)
    print('  LGBM ITERATIVE ENGINE — Banking Benchmark (3-Layer Architecture)')
    print('  Layer 1: LGBM Engine (risk quantification)')
    print('  Layer 2: BSDT Early Warning (primary detector — E_BS + MFLS + ∇²E_BS)')
    print('  Layer 3: Morse + Betti Structural Confirmation')
    print('=' * 80)

    # Load data
    X_3d, dates, y_crisis, meta = load_bank_panel()
    T, N, d = X_3d.shape
    print(f'\n  Panel: T={T} quarters, N={N} banks, d={d} features')
    print(f'  Date range: {dates[0].date()} → {dates[-1].date()}')
    print(f'  Crisis quarters: {int(y_crisis.sum())}/{T}')
    for ev, qs in CRISIS_EVENTS.items():
        print(f'    {ev}: {len(qs)} quarters ({qs[0]} → {qs[-1]})')

    # ── Layer 1: LGBM Iterative Engine ──
    print(f'\n{"="*70}')
    print(f'  LAYER 1: LGBM Iterative Engine (60 iterations, BSDT-guided)')
    print(f'{"="*70}')

    q_scores, bench_time = run_benchmark(X_3d, dates, y_crisis)

    # Compute metrics per variant
    all_metrics = {}
    for v in SCORING_VARIANTS:
        m = compute_metrics(q_scores[v], dates, y_crisis, v)
        all_metrics[v] = m

    # Print Layer 1 per-quarter scores for key variant
    print(f'\n  Layer 1 per-quarter fused scores:')
    for i in range(BURN_IN + 1, T):
        if np.isnan(q_scores['fused'][i]):
            continue
        ds = str(dates[i].date())
        crisis_mark = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
        print(f'    {ds}  fused={q_scores["fused"][i]:.4f}  '
              f'bsdt_e={q_scores["bsdt_energy"][i]:.4f}  '
              f'morse={q_scores["morse"][i]:.4f}{crisis_mark}')

    # ── Layer 2: BSDT Early Warning (primary detector) ──
    print(f'\n{"="*70}')
    print(f'  LAYER 2: BSDT Early Warning (E_BS + MFLS + Morse Alarm on E_BS)')
    print(f'  Primary detector per SIAM §2.2, Algorithm 1')
    print(f'{"="*70}')

    bsdt_ew, bsdt_ew_time = run_bsdt_early_warning(X_3d, dates, y_crisis)
    bsdt_ew_metrics = {}
    for bk in ['e_bs', 'mfls', 'bsdt_blend']:
        bsdt_ew_metrics[bk] = compute_metrics(
            bsdt_ew[bk], dates, y_crisis, f'BSDT_{bk}')

    # Print BSDT alarm timeline
    print(f'\n  BSDT Morse-Alarm Timeline (Hessian of E_BS):')
    print(f'  {"Date":<12s} {"E_BS":>7s} {"MFLS":>7s} {"Blend":>7s} '
          f'{"Morse_idx":>9s} {"Alarm":>6s} {"trace(H)":>9s}')
    print(f'  {"-"*65}')
    for i in range(BURN_IN + 1, T):
        if np.isnan(bsdt_ew['bsdt_blend'][i]):
            continue
        ds = str(dates[i].date())
        crisis_mark = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
        alarm_mark = ' ██ ALARM' if bsdt_ew['morse_alarm'][i] else ''
        midx = bsdt_ew['morse_index'][i]
        midx_s = f'{int(midx)}' if not np.isnan(midx) else 'N/A'
        tr = bsdt_ew['hessian_trace'][i]
        tr_s = f'{tr:9.4f}' if not np.isnan(tr) else '      N/A'
        print(f'  {ds:<12s} {bsdt_ew["e_bs"][i]:7.4f} {bsdt_ew["mfls"][i]:7.4f} '
              f'{bsdt_ew["bsdt_blend"][i]:7.4f} {midx_s:>9s} '
              f'{"YES" if bsdt_ew["morse_alarm"][i] else "no":>6s} '
              f'{tr_s}{crisis_mark}{alarm_mark}')

    # ── Layer 3: Morse + Betti Structural Confirmation ──
    print(f'\n{"="*70}')
    print(f'  LAYER 3: Morse + Betti Structural Confirmation')
    print(f'  Confirms BSDT alarms with topological persistence analysis')
    print(f'{"="*70}')

    mb_confirm, mb_time = run_morse_betti_confirmation(X_3d, dates, y_crisis)
    mb_metrics = {}
    for mk in ['morse', 'betti', 'morse_betti_fused']:
        mb_metrics[mk] = compute_metrics(
            mb_confirm[mk], dates, y_crisis, f'Confirm_{mk}')

    # ── Summary Table ──
    total_time = time.time() - t_global
    print(f'\n\n{"="*80}')
    print(f'  RESULTS — 3-Layer Architecture (Banking)')
    print(f'  Layer 1: LGBM Engine (risk quantification)')
    print(f'  Layer 2: BSDT Early Warning (primary detector — E_BS + MFLS + Morse on ∇²E_BS)')
    print(f'  Layer 3: Morse + Betti (structural confirmation)')
    print(f'{"="*80}')

    # Layer 1 results
    print(f'\n  ── LAYER 1: LGBM Engine ──')
    print(f'  {"Variant":<25s} {"AUC":>6s} {"GFC-AUC":>8s} {"F1":>5s} '
          f'{"FAR%":>5s} {"GFC Lead":>12s}')
    print(f'  {"-"*70}')
    for v in SCORING_VARIANTS:
        m = all_metrics[v]
        lead = m['gfc_lead'] if m['gfc_lead'] else 'none'
        print(f'  {v:<25s} {m["auc"]:6.4f} {m["gfc_auc"]:8.4f} '
              f'{m["best_f1"]:5.3f} {m["far_3sigma"]:5.1f} {lead:>12s}')

    # Layer 2 results
    print(f'\n  ── LAYER 2: BSDT Early Warning (PRIMARY DETECTOR) ──')
    print(f'  {"Signal":<25s} {"AUC":>6s} {"GFC-AUC":>8s} {"F1":>5s} '
          f'{"FAR%":>5s} {"GFC Lead":>12s}')
    print(f'  {"-"*70}')
    for bk in ['e_bs', 'mfls', 'bsdt_blend']:
        bm = bsdt_ew_metrics[bk]
        lead = bm['gfc_lead'] if bm['gfc_lead'] else 'none'
        print(f'  BSDT_{bk:<20s} {bm["auc"]:6.4f} {bm["gfc_auc"]:8.4f} '
              f'{bm["best_f1"]:5.3f} {bm["far_3sigma"]:5.1f} {lead:>12s}')

    # Morse alarm summary (from Layer 2)
    n_alarms = int(np.nansum(bsdt_ew['morse_alarm']))
    n_crisis_alarms = 0
    n_normal_alarms = 0
    for i in range(T):
        if bsdt_ew['morse_alarm'][i]:
            if str(dates[i].date()) in CRISIS_QUARTERS:
                n_crisis_alarms += 1
            else:
                n_normal_alarms += 1
    print(f'\n  BSDT Morse Alarm (Hessian ind≥1 = saddle = phase transition):')
    print(f'    Total alarms: {n_alarms} | Crisis: {n_crisis_alarms} | '
          f'Normal: {n_normal_alarms} | Precision: '
          f'{n_crisis_alarms/max(n_alarms,1)*100:.1f}%')

    # Layer 3 results
    print(f'\n  ── LAYER 3: Morse + Betti Confirmation ──')
    print(f'  {"Signal":<25s} {"AUC":>6s} {"GFC-AUC":>8s} {"F1":>5s} '
          f'{"FAR%":>5s} {"GFC Lead":>12s}')
    print(f'  {"-"*70}')
    for mk in ['morse', 'betti', 'morse_betti_fused']:
        mm = mb_metrics[mk]
        lead = mm['gfc_lead'] if mm['gfc_lead'] else 'none'
        print(f'  {mk:<25s} {mm["auc"]:6.4f} {mm["gfc_auc"]:8.4f} '
              f'{mm["best_f1"]:5.3f} {mm["far_3sigma"]:5.1f} {lead:>12s}')

    # Per-event detection
    print(f'\n  PER-EVENT DETECTION (3σ threshold):')
    print(f'  Layer 1:')
    for v in SCORING_VARIANTS:
        m = all_metrics[v]
        parts = []
        for ev, er in m['events'].items():
            parts.append(f'{ev}={er["detected"]}/{er["total"]}')
        print(f'    {v:<25s} {" | ".join(parts)}')
    print(f'  Layer 2 (BSDT):')
    for bk in ['e_bs', 'mfls', 'bsdt_blend']:
        bm = bsdt_ew_metrics[bk]
        parts = []
        for ev, er in bm['events'].items():
            parts.append(f'{ev}={er["detected"]}/{er["total"]}')
        print(f'    BSDT_{bk:<20s} {" | ".join(parts)}')
    print(f'  Layer 3 (Confirmation):')
    for mk in ['morse', 'betti', 'morse_betti_fused']:
        mm = mb_metrics[mk]
        parts = []
        for ev, er in mm['events'].items():
            parts.append(f'{ev}={er["detected"]}/{er["total"]}')
        print(f'    {mk:<25s} {" | ".join(parts)}')

    # Comparison
    print(f'\n  COMPARISON:')
    print(f'    Flat LGBM (RT+BSDT):      AUC = 0.8316  GFC-AUC = 0.8892')
    print(f'    Paper Gravity/ExpoGate:    AUC = 0.867   (FDIC benchmark)')
    best_v = max(SCORING_VARIANTS, key=lambda v: all_metrics[v]['auc'])
    bm_best = all_metrics[best_v]
    print(f'    LGBM Engine (best={best_v}):  AUC = {bm_best["auc"]:.4f}  '
          f'GFC-AUC = {bm_best["gfc_auc"]:.4f}')
    best_bsdt = max(['e_bs', 'mfls', 'bsdt_blend'],
                    key=lambda k: bsdt_ew_metrics[k]['auc'])
    bb = bsdt_ew_metrics[best_bsdt]
    print(f'    BSDT EW (best={best_bsdt}):    AUC = {bb["auc"]:.4f}  '
          f'GFC-AUC = {bb["gfc_auc"]:.4f}')

    print(f'\n  Engine time: {bench_time:.1f}s  |  BSDT EW: {bsdt_ew_time:.1f}s  '
          f'|  Morse+Betti: {mb_time:.1f}s  |  Total: {total_time:.1f}s')

    # ── Save results ──
    # ── Save results ──
    def _safe(val):
        if isinstance(val, (np.floating, float)):
            return float(val)
        if isinstance(val, (np.integer, int)):
            return int(val)
        if isinstance(val, (np.bool_, bool)):
            return bool(val)
        return val

    save_data = {
        'architecture': '3-Layer: LGBM Engine + BSDT EarlyWarning + Morse/Betti Confirm',
        'description': 'Layer1: LGBM iterative engine (risk quantification). '
                       'Layer2: BSDT early warning (primary detector — E_BS, MFLS, '
                       'morse_alarm on ∇²E_BS). '
                       'Layer3: Morse + Betti structural confirmation.',
        'engine_params': {
            'alpha_radial': 0.1, 'eta': 0.05, 'iterations': 60,
            'k_neighbors': 15, 'beta_lgbm': 2.0, 'fd_eps': 0.01,
        },
        'layer1_metrics': {v: {k: _safe(val) for k, val in m.items()}
                           for v, m in all_metrics.items()},
        'layer2_bsdt_ew_metrics': {bk: {k: _safe(val) for k, val in bm.items()}
                                    for bk, bm in bsdt_ew_metrics.items()},
        'layer3_confirmation_metrics': {mk: {k: _safe(val) for k, val in mm.items()}
                                        for mk, mm in mb_metrics.items()},
        'layer1_scores': {v: [float(x) if not np.isnan(x) else None
                              for x in q_scores[v]]
                          for v in SCORING_VARIANTS},
        'layer2_scores': {bk: [float(x) if not np.isnan(x) else None
                               for x in bsdt_ew[bk]]
                          for bk in ['e_bs', 'mfls', 'bsdt_blend']},
        'layer2_morse_alarm': [bool(x) if not (isinstance(x, float) and np.isnan(x))
                               else None for x in bsdt_ew['morse_alarm']],
        'layer2_morse_index': [int(x) if not np.isnan(x) else None
                               for x in bsdt_ew['morse_index']],
        'layer3_scores': {mk: [float(x) if not np.isnan(x) else None
                               for x in mb_confirm[mk]]
                          for mk in ['morse', 'betti', 'morse_betti_fused']},
        'total_time_sec': total_time,
    }
    out_path = os.path.join(RESULTS_DIR, 'bank_lgbm_engine_results.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f'\n  Saved → {out_path}')


if __name__ == '__main__':
    main()
