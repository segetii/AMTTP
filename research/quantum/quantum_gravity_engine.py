"""
quantum_gravity_engine.py — Full BSDT Dynamics for Quantum Phase Transitions
==============================================================================

Maps quantum observables into a particle-cloud in R^d and runs the
COMPLETE engine architecture from the SIAM paper / AMTTP patent:

  1. Quantum observables O(h) ∈ R^d  →  particle cloud in feature space
  2. Reference particles: ordered phase (h < h_ref)
  3. Pairwise forces: LJ 6-12 (Molecular) or erf/log (Gravity)
  4. BSDT adaptive damping: Ẋ = F(X) − γ(E_BS) · ∇E_BS(X)
     where γ(E) = E / (E + θ),  θ = median(E_BS_ref)
  5. Lyapunov ISS step control (Armijo + La Salle convergence)
  6. Scoring: MorseTopologyAlarm + BettiBarcodeSuite + BSDTChannels
     → FusedSystemScorer with Fisher VR fusion

This is NOT the bare z-score BSDT (QuantumBSDT in quantum_engine.py).
This is the FULL dynamical system that was originally developed as an
anomaly detector for finance / fraud detection, here applied to
quantum many-body observables.

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.distance import cdist, pdist
from sklearn.neighbors import NearestNeighbors
import warnings
warnings.filterwarnings('ignore')


# ═════════════════════════════════════════════════════════════════════
#  BSDT CHANNELS  —  Blind-Spot Detection Tensor
# ═════════════════════════════════════════════════════════════════════

class QuantumBSDTChannels:
    r"""
    4-channel blind-spot detection tensor — designed as overlay on a base model.

    BSDT detects what the base detector MISSES.  Each channel targets a
    specific failure mode of the base model:

    δ_C : Camouflage (base-model-aware)
          = (1 − base_score_norm) × (1 − clip(‖x − μ‖/d_max))
          High when: base model scores point LOW (thinks it's normal)
          AND the point is geometrically close to normal cluster.
          → The exact blind spot: looks normal to everyone.
          Without base_scores, falls back to geometric-only (dynamics mode).

    δ_G : Feature Gap
          = fraction of near-zero features (|x_j/σ_j| < 0.1)
          High → base model had insufficient features to judge.

    δ_A : Activity Anomaly
          = sigmoid((mahal − med_ref) / med_ref)
          High → deviation the base model's calibration doesn't capture.

    δ_T : Temporal Novelty
          = sigmoid(0.5·(d_kNN / med_kNN_ref − 2))
          High → pattern outside base model's reference distribution.

    Two modes:
      - Dynamics mode (base_scores=None): geometric-only δ_C,
        provides adaptive damping friction during simulation.
      - Scoring mode (base_scores provided): base-model-aware δ_C,
        detects the actual blind spots of the base detector.

    Composite:
        E_BS  = Σ w_k δ_k²     (Fisher-weighted blind-spot energy)
        MFLS  = ‖∇E_BS‖_F      (gradient norm, fires at transitions)
        Morse = eigenvalues of ∇²E_BS  (saddle → phase transition)
    """

    def __init__(self, k: int = 15, eps: float = 1e-8):
        self.k = k
        self.eps = eps
        self._fitted = False

    def fit(self, X_ref: np.ndarray) -> 'QuantumBSDTChannels':
        """Calibrate on reference (normal) particles."""
        self.mu_ = X_ref.mean(axis=0)
        self.n_ref_, self.d_ = X_ref.shape

        # δ_C: max distance from centroid in reference
        dists_ref = np.linalg.norm(X_ref - self.mu_, axis=1)
        self.d_max_ = max(float(dists_ref.max()), self.eps)

        # δ_A: regularised inverse covariance
        cov = np.cov(X_ref, rowvar=False)
        if cov.ndim < 2:
            cov = np.atleast_2d(cov)
        self.cov_inv_ = np.linalg.inv(cov + self.eps * np.eye(self.d_))
        self.mahal_ref_median_ = float(np.median(self._mahalanobis(X_ref)))

        # δ_T: kNN distances in reference
        k_use = min(self.k, self.n_ref_ - 1)
        nn = NearestNeighbors(n_neighbors=k_use + 1, algorithm='auto')
        nn.fit(X_ref.astype(np.float32))
        ref_dists, _ = nn.kneighbors(X_ref.astype(np.float32))
        self.ref_knn_median_ = float(np.median(ref_dists[:, -1]))
        self.nn_ = nn

        # δ_G: feature-level std
        self.feat_std_ = np.std(X_ref, axis=0) + self.eps

        # ── Fisher VR channel weights ──
        C = self._raw_channels(X_ref)  # (n_ref, 4)
        total_mag = C.sum(axis=1)
        p80, p50 = np.percentile(total_mag, 80), np.percentile(total_mag, 50)
        hi, lo = total_mag >= p80, total_mag <= p50
        K = 4
        if hi.sum() >= 2 and lo.sum() >= 2:
            fr = np.zeros(K)
            for kk in range(K):
                mu_h = C[hi, kk].mean()
                mu_l = C[lo, kk].mean()
                var_h = C[hi, kk].var()
                var_l = C[lo, kk].var()
                fr[kk] = (mu_h - mu_l) ** 2 / max(var_h + var_l, self.eps)
            total_fr = fr.sum()
            self.fisher_w_ = fr / total_fr if total_fr > self.eps \
                else np.ones(K) / K
        else:
            self.fisher_w_ = np.ones(K) / K

        self._fitted = True
        return self

    def _mahalanobis(self, X: np.ndarray) -> np.ndarray:
        diff = X - self.mu_
        return np.sqrt(np.maximum(
            np.sum(diff @ self.cov_inv_ * diff, axis=1), 0.0
        ))

    def _raw_channels(self, X: np.ndarray,
                      base_scores: np.ndarray = None) -> np.ndarray:
        """Compute 4 raw channels (N, 4).

        Parameters
        ----------
        X : (N, d) feature positions
        base_scores : (N,) scores from the base model, optional.
            When provided, δ_C becomes base-model-aware:
            camouflage is HIGH when base model thinks the point
            is normal (low score) AND it's geometrically close
            to the normal centroid.  This IS the blind spot.

            Without base_scores (dynamics mode), falls back to
            geometric-only δ_C for adaptive damping.
        """
        N = len(X)
        ch = np.zeros((N, 4))

        # δ_C: Camouflage — base-model-aware when scoring
        dist_from_mu = np.linalg.norm(X - self.mu_, axis=1)
        geometric_proximity = 1.0 - np.clip(
            dist_from_mu / self.d_max_, 0.0, 1.0)

        if base_scores is not None:
            # SCORING MODE: δ_C = (1 - base_norm) × geometric_proximity
            # High when BOTH the base model AND geometry say "normal"
            # This is the actual blind spot — everyone missed it
            bs_min, bs_max = base_scores.min(), base_scores.max()
            if bs_max - bs_min > 1e-15:
                bs_norm = (base_scores - bs_min) / (bs_max - bs_min)
            else:
                bs_norm = np.zeros(N)
            ch[:, 0] = (1.0 - bs_norm) * geometric_proximity
        else:
            # DYNAMICS MODE: geometric-only (no base scores yet)
            ch[:, 0] = geometric_proximity

        # δ_G: Feature Gap — base model had insufficient features
        X_normed = np.abs(X) / self.feat_std_
        ch[:, 1] = np.mean(X_normed < 0.1, axis=1).astype(np.float64)

        # δ_A: Activity Anomaly — deviation base wasn't calibrated for
        mahal = self._mahalanobis(X)
        z_a = (mahal - self.mahal_ref_median_) / max(
            self.mahal_ref_median_, self.eps)
        ch[:, 2] = 1.0 / (1.0 + np.exp(-np.clip(z_a, -30, 30)))

        # δ_T: Temporal Novelty — outside base model's reference
        k_use = min(self.k, self.n_ref_ - 1)
        dists, _ = self.nn_.kneighbors(X.astype(np.float32))
        knn_col = min(k_use, dists.shape[1] - 1)
        knn_dist = dists[:, knn_col].astype(np.float64)
        ratio = knn_dist / max(self.ref_knn_median_, self.eps)
        ch[:, 3] = 1.0 / (1.0 + np.exp(-np.clip(
            0.5 * (ratio - 2.0), -30, 30)))

        return ch

    def channels(self, X: np.ndarray,
                 base_scores: np.ndarray = None) -> dict:
        """Return channels as a dict."""
        ch = self._raw_channels(X, base_scores=base_scores)
        return {'delta_C': ch[:, 0], 'delta_G': ch[:, 1],
                'delta_A': ch[:, 2], 'delta_T': ch[:, 3]}

    def energy(self, X: np.ndarray,
               base_scores: np.ndarray = None) -> np.ndarray:
        r"""E_BS = Σ w_k δ_k² — Fisher-weighted blind-spot energy.

        In dynamics mode (base_scores=None): geometric-only δ_C.
        In scoring mode (base_scores provided): base-model-aware δ_C.
        """
        ch = self._raw_channels(X, base_scores=base_scores)
        w = self.fisher_w_
        return (w[0] * ch[:, 0] ** 2 + w[1] * ch[:, 1] ** 2 +
                w[2] * ch[:, 2] ** 2 + w[3] * ch[:, 3] ** 2)

    def energy_total(self, X: np.ndarray,
                     base_scores: np.ndarray = None) -> float:
        return float(self.energy(X, base_scores=base_scores).sum())

    def _gradient_vectors(self, X: np.ndarray) -> np.ndarray:
        r"""∇E_BS — gradient vectors for adaptive damping.

        Ẋ = F(X) − γ(E_BS) · ∇E_BS(X)

        Analytic gradients through δ_C (Euclidean) and δ_A (Mahalanobis).
        δ_G and δ_T have discontinuous / kNN-based gradients → omitted.
        """
        ch = self._raw_channels(X)
        diff = X - self.mu_
        w = self.fisher_w_

        # ── Gradient through δ_A (Mahalanobis, dominant) ──
        mahal = self._mahalanobis(X)
        mahal_safe = np.maximum(mahal, self.eps)
        grad_mahal = (diff @ self.cov_inv_) / mahal_safe[:, None]

        sig_deriv = ch[:, 2] * (1.0 - ch[:, 2])  # sigmoid'
        scale_A = (2.0 * w[2] * ch[:, 2] * sig_deriv /
                   max(self.mahal_ref_median_, self.eps))
        grad_E_A = scale_A[:, None] * grad_mahal

        # ── Gradient through δ_C (Euclidean distance) ──
        dist = np.linalg.norm(diff, axis=1, keepdims=True)
        dist_safe = np.maximum(dist, self.eps)
        unit = diff / dist_safe
        active = (dist.squeeze() < self.d_max_).astype(np.float64)
        scale_C = -2.0 * w[0] * ch[:, 0] * active / self.d_max_
        grad_E_C = scale_C[:, None] * unit

        return grad_E_A + grad_E_C

    def mfls(self, X: np.ndarray) -> np.ndarray:
        r"""MFLS = ‖∇E_BS‖_F — gradient norm of blind-spot energy."""
        return np.linalg.norm(self._gradient_vectors(X), axis=1)

    def morse_alarm(self, X: np.ndarray) -> dict:
        r"""Morse-index prediction from Hessian of E_BS.

        ind ≥ 1 ⇒ saddle ⇒ phase transition detected.
        """
        d = X.shape[1]
        eps_fd = 1e-5

        grad0 = self._gradient_vectors(X).mean(axis=0)
        H = np.zeros((d, d))
        for k in range(d):
            e_k = np.zeros(d)
            e_k[k] = eps_fd
            grad_plus = self._gradient_vectors(X + e_k).mean(axis=0)
            grad_minus = self._gradient_vectors(X - e_k).mean(axis=0)
            H[:, k] = (grad_plus - grad_minus) / (2 * eps_fd)

        H = 0.5 * (H + H.T)
        eigenvalues = np.linalg.eigvalsh(H)
        morse_index = int(np.sum(eigenvalues < 0))

        return {
            'eigenvalues': eigenvalues,
            'morse_index': morse_index,
            'alarm': morse_index >= 1,
            'trace': float(np.trace(H)),
        }

    def score(self, X: np.ndarray,
              base_scores: np.ndarray = None) -> np.ndarray:
        """BSDT overlay score: blend(E_BS, MFLS).

        This is the CORRECTION signal, not the final score.
        It measures blind-spot activity that the base model missed.
        Final score = base + α·this.
        """
        e = self.energy(X, base_scores=base_scores)
        m = self.mfls(X)  # gradient uses geometric-only (dynamics role)
        e_max = max(float(e.max()), self.eps)
        m_max = max(float(m.max()), self.eps)
        return 0.5 * (e / e_max) + 0.5 * (m / m_max)


# ═════════════════════════════════════════════════════════════════════
#  LYAPUNOV STABILISER  —  Armijo + La Salle
# ═════════════════════════════════════════════════════════════════════

class QuantumLyapunovStabiliser:
    """
    Energy-based Lyapunov controller for discrete Euler integration.

    - Armijo sufficient-decrease:  E(X') ≤ E(X) − c·η·‖∇E‖²
    - La Salle invariance:  ‖∇E‖ < tol for `patience` consecutive steps
    - Barrier force clamping:  smooth reciprocal barrier (C¹)
    - ISS margin:  relaxes Armijo when pairwise is a perturbation
    """

    def __init__(self, armijo_c: float = 1e-4, backtrack_rho: float = 0.5,
                 max_force_norm: float = 10.0, min_eta: float = 1e-6,
                 la_salle_tol: float = 1e-5, la_salle_patience: int = 5):
        self.armijo_c = armijo_c
        self.backtrack_rho = backtrack_rho
        self.max_force_norm = max_force_norm
        self.min_eta = min_eta
        self.la_salle_tol = la_salle_tol
        self.la_salle_patience = la_salle_patience
        self.reset()

    def reset(self):
        self.energy_trace: list = []
        self._n_accepted = 0
        self._n_rejected = 0
        self._la_salle_counter = 0
        self._converged = False
        self._convergence_type = 'max_iter'

    def clamp_forces(self, F: np.ndarray) -> np.ndarray:
        """Smooth barrier clamping (C¹, no chattering)."""
        norms = np.linalg.norm(F, axis=1, keepdims=True) + 1e-15
        excess = np.maximum(0, norms - self.max_force_norm)
        scale = self.max_force_norm / (self.max_force_norm + excess)
        scale = np.minimum(scale, 1.0)
        return F * scale

    def accept_step(self, E_old: float, E_new: float,
                    grad_norm_sq: float, eta: float,
                    iss_margin: float = 0.0) -> tuple:
        """Armijo sufficient-decrease with ISS margin."""
        descent = E_old - E_new
        required = self.armijo_c * eta * grad_norm_sq - iss_margin
        if descent >= required:
            self.energy_trace.append(E_new)
            self._n_accepted += 1
            return True, eta
        else:
            new_eta = max(eta * self.backtrack_rho, self.min_eta)
            self._n_rejected += 1
            return False, new_eta

    def check_convergence(self, grad_norm_sq: float,
                          displacement: float) -> bool:
        """La Salle invariance + displacement convergence."""
        grad_norm = np.sqrt(max(grad_norm_sq, 0.0))
        if grad_norm < self.la_salle_tol:
            self._la_salle_counter += 1
            if self._la_salle_counter >= self.la_salle_patience:
                self._converged = True
                self._convergence_type = 'la_salle'
                return True
        else:
            self._la_salle_counter = 0

        if displacement < 1e-6:
            self._converged = True
            self._convergence_type = 'displacement'
            return True
        return False

    def report(self) -> dict:
        total = self._n_accepted + self._n_rejected
        return {
            'n_accepted': self._n_accepted,
            'n_rejected': self._n_rejected,
            'converged': self._converged,
            'convergence_type': self._convergence_type,
            'acceptance_rate': self._n_accepted / total if total > 0 else 1.0,
            'total_descent': sum(
                max(0, a - b) for a, b
                in zip(self.energy_trace[:-1], self.energy_trace[1:])
            ) if len(self.energy_trace) > 1 else 0.0,
        }


# ═════════════════════════════════════════════════════════════════════
#  MORSE TOPOLOGY ALARM  —  kNN-based structural anomaly scorer
# ═════════════════════════════════════════════════════════════════════

class QuantumMorseAlarm:
    """
    Topological prediction signal — structurally stable under noise.

    Four kNN-based features:
      1. Mean kNN distance  (isolation)
      2. Nearest-neighbor d₁  (micro-isolation)
      3. Persistence proxy: (d_k − d₁)/d_k  (topological stability)
      4. Local density ratio  (relative density)

    Fisher VR weights — zero hardcoded constants.
    """

    def __init__(self, k: int = 15):
        self.k = k

    def fit(self, X_ref: np.ndarray) -> 'QuantumMorseAlarm':
        self._X_ref = X_ref.copy()
        features = self._compute_features(X_ref, X_ref, is_self=True)
        self._ref_mean = features.mean(axis=0)
        self._ref_std = features.std(axis=0) + 1e-10

        # Fisher VR weights
        z = (features - self._ref_mean) / self._ref_std
        zpos = np.maximum(z, 0)
        total = zpos.sum(axis=1)
        p80, p50 = np.percentile(total, 80), np.percentile(total, 50)
        hi, lo = total >= p80, total <= p50
        K = features.shape[1]
        if hi.sum() >= 2 and lo.sum() >= 2:
            fr = np.zeros(K)
            for kk in range(K):
                mu_h, mu_l = zpos[hi, kk].mean(), zpos[lo, kk].mean()
                var_h, var_l = zpos[hi, kk].var(), zpos[lo, kk].var()
                fr[kk] = (mu_h - mu_l) ** 2 / max(var_h + var_l, 1e-10)
            s = fr.sum()
            self._weights = fr / s if s > 1e-10 else np.ones(K) / K
        else:
            self._weights = np.ones(K) / K
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        features = self._compute_features(X, self._X_ref, is_self=False)
        z = (features - self._ref_mean) / self._ref_std
        return np.maximum(z, 0) @ self._weights

    def _compute_features(self, X_query, X_ref, is_self=False):
        N = len(X_query)
        k = min(self.k, len(X_ref) - 1)
        if k < 1:
            return np.zeros((N, 4), dtype=np.float64)

        if is_self:
            nn = NearestNeighbors(n_neighbors=k + 1, algorithm='auto')
            nn.fit(X_ref.astype(np.float32))
            dists, _ = nn.kneighbors(X_query.astype(np.float32))
            nn_dists = dists[:, 1:]
        else:
            nn = NearestNeighbors(n_neighbors=k, algorithm='auto')
            nn.fit(X_ref.astype(np.float32))
            dists, _ = nn.kneighbors(X_query.astype(np.float32))
            nn_dists = dists

        eps = 1e-10
        d1 = nn_dists[:, 0] + eps
        dk = nn_dists[:, -1] + eps
        out = np.zeros((N, 4), dtype=np.float64)
        out[:, 0] = nn_dists.mean(axis=1)            # mean kNN distance
        out[:, 1] = d1                                 # nearest neighbor
        out[:, 2] = (dk - d1) / (dk + eps)            # persistence proxy
        ref_mean_knn = nn_dists.mean()
        out[:, 3] = nn_dists.mean(axis=1) / (ref_mean_knn + eps)  # density ratio
        return out


# ═════════════════════════════════════════════════════════════════════
#  BETTI BARCODE SUITE  —  Multi-scale topology
# ═════════════════════════════════════════════════════════════════════

class QuantumBettiBarcodes:
    """
    Persistent-homology proxies via kNN filtration.

    β₀(ε) — connected components — drops as ε grows
    β₁(ε) — 1-cycles — spikes at sparse loops
    χ(ε)  — Euler characteristic = β₀ − β₁
    Conley — stability of β₀ across scales → CoV
    """

    def __init__(self, k: int = 20, n_scales: int = 8):
        self.k = k
        self.n_scales = n_scales

    @property
    def n_features(self) -> int:
        return 3 + 2 * self.n_scales

    def fit(self, X_ref: np.ndarray) -> 'QuantumBettiBarcodes':
        self._X_ref = X_ref.copy()
        k = min(self.k, len(X_ref) - 1)
        if k < 2:
            self._scales = np.linspace(0.1, 1.0, self.n_scales)
            self._ref_mean = np.zeros(self.n_features)
            self._ref_std = np.ones(self.n_features)
            return self

        nn = NearestNeighbors(n_neighbors=k + 1, algorithm='auto')
        nn.fit(X_ref.astype(np.float32))
        dists, _ = nn.kneighbors(X_ref.astype(np.float32))
        nn_dists = dists[:, 1:]

        self._scales = np.linspace(
            np.percentile(nn_dists[:, 0], 10),
            np.percentile(nn_dists[:, -1], 90) * 1.2,
            self.n_scales,
        )

        features = self._compute_features(X_ref, X_ref, is_self=True)
        self._ref_mean = features.mean(axis=0)
        self._ref_std = features.std(axis=0) + 1e-10
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        features = self._compute_features(X, self._X_ref, is_self=False)
        z = (features - self._ref_mean) / self._ref_std
        return np.mean(np.maximum(z, 0), axis=1)

    def _compute_features(self, X_query, X_ref, is_self=False):
        N = len(X_query)
        k = min(self.k, len(X_ref) - 1)
        ns = self.n_scales
        n_feat = 3 + 2 * ns

        if k < 2:
            return np.zeros((N, n_feat), dtype=np.float64)

        if is_self:
            nn = NearestNeighbors(n_neighbors=k + 1, algorithm='auto')
            nn.fit(X_ref.astype(np.float32))
            dists, _ = nn.kneighbors(X_query.astype(np.float32))
            nn_dists = dists[:, 1:]
        else:
            nn = NearestNeighbors(n_neighbors=k, algorithm='auto')
            nn.fit(X_ref.astype(np.float32))
            dists, _ = nn.kneighbors(X_query.astype(np.float32))
            nn_dists = dists

        scales = self._scales
        out = np.zeros((N, n_feat), dtype=np.float64)
        reach = np.zeros((N, ns), dtype=np.float64)
        for s in range(ns):
            reach[:, s] = (nn_dists <= scales[s]).sum(axis=1) / k

        b0 = 1.0 - reach
        dist_cv = (nn_dists.std(axis=1, keepdims=True) /
                   (nn_dists.mean(axis=1, keepdims=True) + 1e-10))
        b1 = reach * dist_cv
        euler = b0 - b1

        mid = ns // 2
        out[:, 0] = b0[:, mid]
        out[:, 1] = b1[:, mid]
        out[:, 2] = b0.std(axis=1) / (b0.mean(axis=1) + 1e-10)
        out[:, 3:3 + ns] = euler
        out[:, 3 + ns:3 + 2 * ns] = b0
        return out


# ═════════════════════════════════════════════════════════════════════
#  FUSED SYSTEM SCORER  —  Fisher VR fusion of all signal families
# ═════════════════════════════════════════════════════════════════════

class QuantumFusedScorer:
    """
    Two-stage scorer: Base Model + BSDT Overlay.

    BSDT was designed to work ON a base model, not as a standalone.

    Stage 1 — Base Model:
        Morse topology alarm + Betti persistence scoring.
        These are the PRIMARY detection signals.  They use
        structurally stable kNN features that detect anomalies
        from the post-simulation particle positions.

    Stage 2 — BSDT Overlay (on the base model):
        Computes 4 blind-spot channels RELATIVE TO BASE SCORES:
        - δ_C: base scored LOW + looks normal → camouflaged
        - δ_G: base had sparse features → gap
        - δ_A: base wasn't calibrated for this deviation → activity
        - δ_T: base hasn't seen this pattern → novelty
        This catches what the base model MISSES.

    Stage 3 — Fisher VR Fusion:
        final = base_score + α · bsdt_correction
        α determined by Fisher VR (data-driven, no hardcoded weight).
    """

    def __init__(self, k: int = 15):
        self.k = k
        # Stage 1: Base model components
        self.morse = QuantumMorseAlarm(k=k)
        self.betti = QuantumBettiBarcodes(k=min(k + 5, 25))
        # Stage 2: BSDT overlay (works ON the base model)
        self.bsdt = QuantumBSDTChannels(k=k)

    def fit(self, X_ref: np.ndarray) -> 'QuantumFusedScorer':
        """Fit base model and BSDT overlay on reference data."""
        # Base model
        self.morse.fit(X_ref)
        try:
            self.betti.fit(X_ref)
        except Exception:
            self.betti = None
        # BSDT overlay (calibrated on same reference)
        self.bsdt.fit(X_ref)
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        """Two-stage scoring: base model → BSDT overlay → fusion.

        1. Compute base_scores from Morse + Betti
        2. Feed base_scores INTO BSDT so δ_C targets actual blind spots
        3. Fisher VR fuse base + overlay
        """
        # ── Stage 1: Base model scores ──
        base_views = [self._robust_norm(self.morse.score(X))]
        if self.betti is not None:
            try:
                base_views.append(self._robust_norm(self.betti.score(X)))
            except Exception:
                pass
        base_scores = self._fisher_fuse(base_views)

        # ── Stage 2: BSDT overlay, conditioned on base model output ──
        # δ_C is now base-model-aware: targets points the base MISSED
        bsdt_correction = self._robust_norm(
            self.bsdt.score(X, base_scores=base_scores))

        # ── Stage 3: Fuse base + overlay via Fisher VR ──
        base_norm = self._robust_norm(base_scores)
        return self._fisher_fuse([base_norm, bsdt_correction])

    def base_score(self, X: np.ndarray) -> np.ndarray:
        """Base model scores only (Morse + Betti, no BSDT overlay)."""
        views = [self._robust_norm(self.morse.score(X))]
        if self.betti is not None:
            try:
                views.append(self._robust_norm(self.betti.score(X)))
            except Exception:
                pass
        return self._fisher_fuse(views)

    def _fisher_fuse(self, views: list) -> np.ndarray:
        """Fisher VR weighted fusion — zero heuristics."""
        if len(views) == 1:
            return views[0]
        V = np.column_stack(views)
        nv = V.shape[1]
        total = V.sum(axis=1)
        p80, p50 = np.percentile(total, 80), np.percentile(total, 50)
        hi, lo = total >= p80, total <= p50
        if hi.sum() >= 2 and lo.sum() >= 2:
            fr = np.zeros(nv)
            for v in range(nv):
                mu_h, mu_l = V[hi, v].mean(), V[lo, v].mean()
                var_h, var_l = V[hi, v].var(), V[lo, v].var()
                fr[v] = (mu_h - mu_l) ** 2 / max(var_h + var_l, 1e-10)
            s = fr.sum()
            w = fr / s if s > 1e-10 else np.ones(nv) / nv
        else:
            w = np.ones(nv) / nv
        return (V * w).sum(axis=1)

    @staticmethod
    def _robust_norm(s: np.ndarray) -> np.ndarray:
        """Percentile-based normalisation (robust to outliers)."""
        q1, q99 = np.percentile(s, [1, 99])
        if q99 - q1 > 1e-15:
            return np.clip((s - q1) / (q99 - q1), 0.0, 1.0)
        return np.zeros_like(s)


# ═════════════════════════════════════════════════════════════════════
#  QUANTUM MOLECULAR ENGINE  —  Lennard-Jones 6-12
# ═════════════════════════════════════════════════════════════════════

class QuantumMolecularEngine:
    """
    Lennard-Jones 6-12 pairwise dynamics over quantum observable vectors.

    Architecture: Base Model (LJ dynamics) + BSDT Overlay.

    Stage 1 — Base Model (this engine):
        V_LJ(r) = ε [(σ/r)^12 − 2(σ/r)^6]
        F_LJ(r) = 12ε/r [(σ/r)^12 − (σ/r)^6] r̂
        + Radial centroid attraction:  F_rad = −α(X − μ)
        + BSDT adaptive damping:      F_damp = −γ(E_BS)·∇E_BS
          (damping role only — geometric δ_C, no base scores yet)
        + Lyapunov ISS stabilisation (Armijo/La Salle)
        + Base scoring: Morse topology + Betti persistence

    Stage 2 — BSDT Overlay (on the base model's output):
        δ_C computed with base_scores → targets actual blind spots
        Final = base + α·BSDT_correction (Fisher VR weight)

    The Lennard-Jones potential creates attraction at long range and
    repulsion at short range.  Normal particles cluster at the LJ
    minimum.  Anomalous points settle at structurally distinct
    positions — detected by the base model.  BSDT catches what
    the base model misses.
    """

    def __init__(self, alpha_radial: float = 0.5,
                 epsilon_lj: float = 1.0,
                 sigma_lj: float = None,
                 eta: float = 0.01,
                 max_iter: int = 300,
                 k_nn: int = 8,
                 theta_bs: float = None,
                 verbose: bool = False):
        self.alpha_radial = alpha_radial
        self.epsilon_lj = epsilon_lj
        self.sigma_lj = sigma_lj  # Auto-calibrated if None
        self.eta = eta
        self.max_iter = max_iter
        self.k_nn = k_nn
        self.theta_bs = theta_bs
        self.verbose = verbose

    def fit_score(self, X_ref: np.ndarray,
                  X_all: np.ndarray) -> tuple:
        """
        Run full molecular dynamics + BSDT scoring.

        Parameters
        ----------
        X_ref : (n_ref, d) reference observations (ordered phase)
        X_all : (n_all, d) all observations

        Returns
        -------
        scores : (n_all,) anomaly scores
        diagnostics : dict
        """
        N_all, d = X_all.shape
        N_ref = len(X_ref)

        # ── Normalise using reference statistics ──
        mu = X_ref.mean(axis=0)
        std = X_ref.std(axis=0) + 1e-10
        X_work = (X_all - mu) / std
        X_ref_n = (X_ref - mu) / std

        # ── Auto-calibrate σ_LJ from reference median distance ──
        if self.sigma_lj is None:
            dists = pdist(X_ref_n)
            sigma = float(np.median(dists)) * 0.5 if len(dists) > 0 else 1.0
        else:
            sigma = self.sigma_lj

        # ── Initialise BSDT damper on reference ──
        k_bsdt = min(max(self.k_nn, 5), N_ref - 1)
        bsdt_damper = QuantumBSDTChannels(k=k_bsdt)
        bsdt_damper.fit(X_ref_n)

        # θ = median(E_BS on reference) — ~50% damping at normal
        e_bs_ref = bsdt_damper.energy(X_ref_n)
        theta = float(np.median(e_bs_ref)) if self.theta_bs is None \
            else self.theta_bs
        theta = max(theta, 1e-6)

        # MFLS scale factor
        mfls_ref = bsdt_damper.mfls(X_ref_n)
        mfls_med = float(np.median(mfls_ref)) + 1e-10
        beta_mfls = theta / mfls_med

        # ── Lyapunov stabiliser ──
        lyap = QuantumLyapunovStabiliser(max_force_norm=8.0)

        # ── Euler integration ──
        X = X_work.copy()
        eta = self.eta
        centroid = X_ref_n.mean(axis=0)
        diag = {
            'energy_trace': [], 'morse_alarm': {},
            'converged': False, 'convergence_type': 'max_iter',
            'n_iter': 0,
        }

        for step in range(self.max_iter):
            # -- LJ pairwise forces (kNN-limited) --
            F_lj = self._lj_forces(X, sigma)

            # -- Radial centroid force --
            F_radial = -self.alpha_radial * (X - centroid)

            # -- BSDT + MFLS adaptive damping (eq:bsdamped extended) --
            e_bs = bsdt_damper.energy(X)
            grad_bs = bsdt_damper._gradient_vectors(X)
            mfls_bs = np.linalg.norm(grad_bs, axis=1)
            e_combined = e_bs + beta_mfls * mfls_bs
            gamma_bs = e_combined / (e_combined + theta)
            F_damp = -gamma_bs[:, None] * grad_bs

            # -- Total force --
            F_total = F_lj + F_radial + F_damp
            F_total = lyap.clamp_forces(F_total)

            # -- Armijo step control --
            E_old = self._lj_energy(X, sigma, centroid)
            e_old_total = E_old + bsdt_damper.energy_total(X)
            grad_norm_sq = float(np.sum(F_total ** 2))

            X_new = X + eta * F_total
            E_new = self._lj_energy(X_new, sigma, centroid)
            e_new_total = E_new + bsdt_damper.energy_total(X_new)

            accepted, eta = lyap.accept_step(
                e_old_total, e_new_total, grad_norm_sq, eta)

            if accepted:
                displacement = float(np.max(np.abs(X_new - X)))
                X = X_new
                diag['energy_trace'].append(e_new_total)
                if lyap.check_convergence(grad_norm_sq, displacement):
                    diag['converged'] = True
                    diag['convergence_type'] = lyap._convergence_type
                    break
            else:
                X = X + eta * F_total

        diag['n_iter'] = step + 1
        diag['lyapunov'] = lyap.report()

        # ── Morse alarm from BSDT Hessian ──
        diag['morse_alarm'] = bsdt_damper.morse_alarm(X)

        # ── Two-stage scoring: Base Model → BSDT Overlay ──
        k_score = min(max(self.k_nn, 5), N_ref - 1)
        scorer = QuantumFusedScorer(k=k_score)
        scorer.fit(X_ref_n)

        # Stage 1: base model scores (Morse + Betti)
        base_scores = scorer.base_score(X)
        # Stage 2+3: base + BSDT overlay (δ_C aware of base scores)
        scores = scorer.score(X)

        diag['bsdt_energy_final'] = bsdt_damper.energy(X).tolist()
        diag['base_scores'] = base_scores.tolist()

        if self.verbose:
            ma = diag['morse_alarm']
            lr = diag['lyapunov']
            print(f"  [Molecular] iter={diag['n_iter']} "
                  f"converged={diag['converged']} ({diag['convergence_type']})  "
                  f"Morse ind={ma['morse_index']}  "
                  f"accept rate={lr['acceptance_rate']:.2f}")

        return scores, diag

    def _lj_forces(self, X: np.ndarray, sigma: float) -> np.ndarray:
        """Lennard-Jones 6-12 pairwise forces (kNN-limited, vectorised)."""
        N, d = X.shape
        F = np.zeros_like(X)
        k = min(self.k_nn, N - 1)
        if k < 1:
            return F

        nn = NearestNeighbors(n_neighbors=k + 1, algorithm='auto')
        nn.fit(X.astype(np.float32))
        _, indices = nn.kneighbors(X.astype(np.float32))

        eps = self.epsilon_lj
        for i in range(N):
            for j_idx in indices[i, 1:]:
                rij = X[j_idx] - X[i]
                r = np.linalg.norm(rij) + 1e-10
                sr6 = (sigma / r) ** 6
                sr12 = sr6 ** 2
                f_mag = 12.0 * eps / r * (sr12 - sr6)
                F[i] += f_mag * (rij / r)

        return F

    def _lj_energy(self, X: np.ndarray, sigma: float,
                   centroid: np.ndarray) -> float:
        """Total energy: LJ pairwise + radial."""
        # Radial
        E_rad = 0.5 * self.alpha_radial * np.sum((X - centroid) ** 2)

        # Pairwise LJ (full upper triangle)
        N = len(X)
        E_lj = 0.0
        if N > 1:
            D = cdist(X, X)
            np.fill_diagonal(D, 1e10)
            sr6 = (sigma / (D + 1e-10)) ** 6
            sr12 = sr6 ** 2
            E_lj = self.epsilon_lj * np.sum(np.triu(sr12 - 2 * sr6, k=1))

        return float(E_rad + E_lj)


# ═════════════════════════════════════════════════════════════════════
#  QUANTUM GRAVITY ENGINE  —  erf-attraction + log-repulsion
# ═════════════════════════════════════════════════════════════════════

class QuantumGravityEngine:
    """
    Gravity-mode pairwise dynamics over quantum observable vectors.

    Architecture: Base Model (gravity dynamics) + BSDT Overlay.

    Stage 1 — Base Model (this engine):
        F_attract(r) = −γ · erf(r/σ) / r · r̂   (bounded at r→0)
        F_repel(r)   = +λ / (r + ε) · r̂          (log-divergence)
        + Radial anchor (ISS centroid):  F_rad = −α(X − μ)
        + BSDT adaptive damping (dynamics role only, geometric δ_C)
        + Lyapunov ISS stabilisation
        + Base scoring: Morse topology + Betti persistence

    Stage 2 — BSDT Overlay:
        δ_C computed with base_scores → targets actual blind spots
        Final = base + α·BSDT_correction (Fisher VR weight)

    The gravity engine uses radial-only energy as the Lyapunov
    candidate, treating pairwise forces as a bounded perturbation
    (ISS framework).
    """

    def __init__(self, alpha_radial: float = 0.5,
                 gamma_attract: float = 1.0,
                 lambda_repel: float = 0.1,
                 sigma_grav: float = None,
                 eta: float = 0.01,
                 max_iter: int = 300,
                 k_nn: int = 8,
                 theta_bs: float = None,
                 verbose: bool = False):
        self.alpha_radial = alpha_radial
        self.gamma_attract = gamma_attract
        self.lambda_repel = lambda_repel
        self.sigma_grav = sigma_grav
        self.eta = eta
        self.max_iter = max_iter
        self.k_nn = k_nn
        self.theta_bs = theta_bs
        self.verbose = verbose

    def fit_score(self, X_ref: np.ndarray,
                  X_all: np.ndarray) -> tuple:
        """Run gravity dynamics + BSDT scoring."""
        N_all, d = X_all.shape
        N_ref = len(X_ref)

        # ── Normalise ──
        mu = X_ref.mean(axis=0)
        std = X_ref.std(axis=0) + 1e-10
        X_work = (X_all - mu) / std
        X_ref_n = (X_ref - mu) / std

        # ── Auto-calibrate σ ──
        if self.sigma_grav is None:
            dists = pdist(X_ref_n)
            sigma = float(np.median(dists)) if len(dists) > 0 else 1.0
        else:
            sigma = self.sigma_grav

        # ── BSDT damper ──
        k_bsdt = min(max(self.k_nn, 5), N_ref - 1)
        bsdt_damper = QuantumBSDTChannels(k=k_bsdt)
        bsdt_damper.fit(X_ref_n)

        e_bs_ref = bsdt_damper.energy(X_ref_n)
        theta = float(np.median(e_bs_ref)) if self.theta_bs is None \
            else self.theta_bs
        theta = max(theta, 1e-6)

        mfls_ref = bsdt_damper.mfls(X_ref_n)
        mfls_med = float(np.median(mfls_ref)) + 1e-10
        beta_mfls = theta / mfls_med

        # ── Lyapunov ──
        lyap = QuantumLyapunovStabiliser(max_force_norm=8.0)

        # ── Integration ──
        X = X_work.copy()
        eta = self.eta
        centroid = X_ref_n.mean(axis=0)
        diag = {
            'energy_trace': [], 'morse_alarm': {},
            'converged': False, 'convergence_type': 'max_iter',
            'n_iter': 0,
        }

        for step in range(self.max_iter):
            # -- Gravity pairwise forces --
            F_grav = self._gravity_forces(X, sigma)

            # -- Radial (ISS anchor) --
            F_radial = -self.alpha_radial * (X - centroid)

            # -- BSDT + MFLS adaptive damping --
            e_bs = bsdt_damper.energy(X)
            grad_bs = bsdt_damper._gradient_vectors(X)
            mfls_bs = np.linalg.norm(grad_bs, axis=1)
            e_combined = e_bs + beta_mfls * mfls_bs
            gamma_bs = e_combined / (e_combined + theta)
            F_damp = -gamma_bs[:, None] * grad_bs

            # -- Total --
            F_total = F_grav + F_radial + F_damp
            F_total = lyap.clamp_forces(F_total)

            # -- ISS energy (radial-only, pairwise = perturbation) --
            E_rad = 0.5 * self.alpha_radial * np.sum((X - centroid) ** 2)
            e_old_total = E_rad + bsdt_damper.energy_total(X)
            grad_norm_sq = float(np.sum(F_total ** 2))

            # -- Step --
            X_new = X + eta * F_total
            E_rad_new = 0.5 * self.alpha_radial * np.sum(
                (X_new - centroid) ** 2)
            e_new_total = E_rad_new + bsdt_damper.energy_total(X_new)

            # ISS margin for pairwise perturbation
            iss_pert = float(np.linalg.norm(F_grav))
            accepted, eta = lyap.accept_step(
                e_old_total, e_new_total, grad_norm_sq, eta,
                iss_margin=iss_pert ** 2 * 0.01)

            if accepted:
                displacement = float(np.max(np.abs(X_new - X)))
                X = X_new
                diag['energy_trace'].append(e_new_total)
                if lyap.check_convergence(grad_norm_sq, displacement):
                    diag['converged'] = True
                    diag['convergence_type'] = lyap._convergence_type
                    break
            else:
                X = X + eta * F_total

        diag['n_iter'] = step + 1
        diag['lyapunov'] = lyap.report()

        # ── Morse alarm ──
        diag['morse_alarm'] = bsdt_damper.morse_alarm(X)

        # ── Two-stage scoring: Base Model → BSDT Overlay ──
        k_score = min(max(self.k_nn, 5), N_ref - 1)
        scorer = QuantumFusedScorer(k=k_score)
        scorer.fit(X_ref_n)

        # Stage 1: base model scores (Morse + Betti)
        base_scores = scorer.base_score(X)
        # Stage 2+3: base + BSDT overlay (δ_C aware of base scores)
        scores = scorer.score(X)

        diag['bsdt_energy_final'] = bsdt_damper.energy(X).tolist()
        diag['base_scores'] = base_scores.tolist()

        if self.verbose:
            ma = diag['morse_alarm']
            lr = diag['lyapunov']
            print(f"  [Gravity] iter={diag['n_iter']} "
                  f"converged={diag['converged']} ({diag['convergence_type']})  "
                  f"Morse ind={ma['morse_index']}  "
                  f"accept rate={lr['acceptance_rate']:.2f}")

        return scores, diag

    def _gravity_forces(self, X: np.ndarray,
                        sigma: float) -> np.ndarray:
        """erf-attraction + log-repulsion (kNN-limited)."""
        from scipy.special import erf

        N, d = X.shape
        F = np.zeros_like(X)
        eps = 1e-10
        k = min(self.k_nn, N - 1)
        if k < 1:
            return F

        nn = NearestNeighbors(n_neighbors=k + 1, algorithm='auto')
        nn.fit(X.astype(np.float32))
        _, indices = nn.kneighbors(X.astype(np.float32))

        for i in range(N):
            for j_idx in indices[i, 1:]:
                rij = X[j_idx] - X[i]
                r = np.linalg.norm(rij) + eps
                rhat = rij / r

                # Attraction: −γ erf(r/σ) / r
                f_attract = -self.gamma_attract * erf(r / sigma) / r
                # Repulsion: +λ / (r + ε)
                f_repel = self.lambda_repel / (r + eps)

                F[i] += (f_attract + f_repel) * rhat

        return F


# ═════════════════════════════════════════════════════════════════════
#  QUANTUM HYBRID ENGINE  —  CV-weighted blend
# ═════════════════════════════════════════════════════════════════════

class QuantumHybridEngine:
    """
    Cross-validated blend of Molecular (LJ) and Gravity (erf/log).

    Runs both engines independently, then blends scores using inverse
    coefficient of variation (stabler engine gets higher weight).
    """

    def __init__(self, molecular_kw: dict = None,
                 gravity_kw: dict = None):
        self.molecular = QuantumMolecularEngine(**(molecular_kw or {}))
        self.gravity = QuantumGravityEngine(**(gravity_kw or {}))

    def fit_score(self, X_ref: np.ndarray,
                  X_all: np.ndarray) -> tuple:
        scores_m, diag_m = self.molecular.fit_score(X_ref, X_all)
        scores_g, diag_g = self.gravity.fit_score(X_ref, X_all)

        # CV weighting: inverse coefficient of variation
        cv_m = np.std(scores_m) / (np.mean(scores_m) + 1e-10)
        cv_g = np.std(scores_g) / (np.mean(scores_g) + 1e-10)

        w_m = 1.0 / (cv_m + 1e-10)
        w_g = 1.0 / (cv_g + 1e-10)
        total = w_m + w_g
        w_m /= total
        w_g /= total

        scores = w_m * scores_m + w_g * scores_g

        diag = {
            'molecular': diag_m,
            'gravity': diag_g,
            'weights': {'molecular': float(w_m), 'gravity': float(w_g)},
        }
        return scores, diag


# ═════════════════════════════════════════════════════════════════════
#  CONVENIENCE:  Run engine on quantum sweep data
# ═════════════════════════════════════════════════════════════════════

def run_quantum_engine(obs_list: list, h_vals: np.ndarray,
                       engine_type: str = 'gravity',
                       ref_cutoff: float = 0.5,
                       obs_keys: list = None,
                       J: float = 1.0,
                       **engine_kwargs) -> tuple:
    """
    Run a full BSDT dynamics engine on quantum observables.

    Parameters
    ----------
    obs_list : list of dicts from sweep_field()
    h_vals   : array of field values h/J
    engine_type : 'molecular', 'gravity', or 'hybrid'
    ref_cutoff  : h/J below which is "reference" (ordered phase)
    obs_keys    : which observables to use as features
    J           : coupling constant

    Returns
    -------
    scores : (n_h,) anomaly scores
    diag   : dict with diagnostics
    """
    if obs_keys is None:
        obs_keys = ['m_sq', 'S_vN', 'gap_phys', 'C_ratio', 'binder', 'IPR']

    # Build feature matrix
    X_all = np.array([[o[k] for k in obs_keys] for o in obs_list],
                     dtype=np.float64)

    # Reference = ordered phase
    ref_mask = h_vals < ref_cutoff * J
    X_ref = X_all[ref_mask]

    if len(X_ref) < 3:
        raise ValueError(
            f"Too few reference points (h < {ref_cutoff}J): {len(X_ref)}")

    # Select engine
    if engine_type == 'molecular':
        engine = QuantumMolecularEngine(**engine_kwargs)
    elif engine_type == 'gravity':
        engine = QuantumGravityEngine(**engine_kwargs)
    elif engine_type == 'hybrid':
        engine = QuantumHybridEngine(
            molecular_kw=engine_kwargs, gravity_kw=engine_kwargs)
    else:
        raise ValueError(f"Unknown engine: {engine_type}")

    scores, diag = engine.fit_score(X_ref, X_all)
    diag['engine_type'] = engine_type
    diag['ref_cutoff'] = ref_cutoff
    diag['obs_keys'] = obs_keys
    diag['n_ref'] = int(ref_mask.sum())

    return scores, diag


def compute_engine_mfls(h_vals: np.ndarray,
                        scores: np.ndarray) -> np.ndarray:
    """MFLS from engine scores: |d(score)/dh|."""
    return np.abs(np.gradient(scores, h_vals))
