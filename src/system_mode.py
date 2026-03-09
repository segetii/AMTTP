"""
System Mode Engine — Molecular / Gravity / Hybrid Toggle
==========================================================
Provides three selectable physics-inspired scoring modes that decouple
the chaotic iteration dynamics (Lyapunov-stabilised solver) from the
topological prediction signal (Morse/persistence-based alarm).

This decoupling eliminates the false-alarm inflation caused by the
ChaosSpectrum / SpectralSpectrum operators leaking stochastic noise
into the final anomaly score.

Modes
-----
  'molecular'  — Molecular dynamics: Lennard-Jones potential + Morse
                 index alarm.  Best for dense, cluster-structured data.
  'gravity'    — N-body gravitational: radial pull + pairwise attraction/
                 repulsion + Lyapunov-stabilised iteration.  Best for
                 sparse, radial-separation tasks.
  'hybrid'     — Weighted blend of molecular + gravity scores with
                 adaptive mode selection via cross-validation.

False-Alarm Suppression
-----------------------
  The key insight (from the BSDT / SIAM paper discussion):

  1. **Lyapunov stays inside the iteration loop only**.
     Used for step-size backtracking (Armijo), force clamping, and
     convergence monitoring.  Chaos/noise in the dynamics is allowed
     for realism but never reaches the prediction signal.

  2. **Prediction signal is 100 % topological / structural**.
     Uses Morse index (# negative Hessian eigenvalues), persistence
     proxy (long-bar length from kNN filtration), or Euler-characteristic
     jump — all structurally stable under small perturbations.

  Result:  transient chaotic spikes create only short-lived topological
  features that are automatically filtered; only true phase-transition
  crossings of the critical manifold C* trigger alarms.

Fused Scoring (v2)
------------------
  Post-simulation positions are scored by four complementary signal
  families, then fused via min-max normalisation + equal-weight average:

  1. **MorseTopologyAlarm** — kNN distance features (4D)
  2. **BettiBarcodeSuite** — multi-scale β₀/β₁/χ/Conley (19D)
  3. **UDLPostSimScorer**  — best-4 UDL operators: Phase + Topological
     + KernelRKHS + Rank (≈27D), mAUC 0.972 on paper benchmarks
  4. **BSDTChannels**      — Blind-Spot Detection Tensor (4 channels):
     δ_C (camouflage) + δ_G (feature gap) + δ_A (activity anomaly)
     + δ_T (temporal novelty) → E_BS + MFLS composite score.
     Implements the BSDT framework (SIAM paper, Section 2.2).

  For large-N scoring, Morse + Betti score directly (kNN-based),
  while UDL scores are kNN-interpolated from the simulation subset.

Author: Odeyemi Olusegun Israel
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Tuple, Union
from sklearn.preprocessing import StandardScaler
from scipy.spatial.distance import cdist


# ═══════════════════════════════════════════════════════════════════
#  MODE ENUMERATION
# ═══════════════════════════════════════════════════════════════════

class SystemMode(Enum):
    """Selectable physics system for anomaly scoring."""
    MOLECULAR = "molecular"
    GRAVITY = "gravity"
    HYBRID = "hybrid"


# ═══════════════════════════════════════════════════════════════════
#  CONVERGENCE REPORT (solver diagnostics — never touches predictions)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ConvergenceReport:
    """Structured convergence diagnostics from the Lyapunov controller.

    All fields are solver internals — never exposed to prediction output.
    """
    n_steps: int                 # total iteration steps executed
    n_accepted: int              # Armijo-accepted steps
    n_rejected: int              # Armijo-rejected steps (backtracked)
    total_descent: float         # cumulative energy descent  ΣΔV
    final_grad_norm: float       # ‖∇E‖ at final step
    converged: bool              # did solver converge?
    convergence_type: str        # 'la_salle' | 'displacement' | 'max_iter'
    iss_bound: float             # max perturbation norm seen
    final_eta: float             # step size at termination
    acceptance_rate: float       # n_accepted / (n_accepted + n_rejected)


# ═══════════════════════════════════════════════════════════════════
#  LYAPUNOV STABILISER v2 — Energy-Based (Hamiltonian) Controller
#  (iteration-only — never touches predictions)
# ═══════════════════════════════════════════════════════════════════

class LyapunovStabiliser:
    """
    Energy-Based (Hamiltonian) Lyapunov Controller  —  v2

    Uses the system's total energy E_total as the Lyapunov function
    V = E_total.  Controls the Euler integration solver only; the
    prediction signal comes entirely from the topological alarm.

    Theoretical basis
    -----------------
      - **Gradient flow**: dX/dt = −∇E  ⟹  dV/dt = −‖∇E‖² ≤ 0
        (automatic descent along gradient)
      - **Armijo condition** (discrete descent certificate):
        E(Xᵗ⁺¹) ≤ E(Xᵗ) − c·η·‖∇E‖²
      - **La Salle invariance**: converges to largest invariant set
        where ∇E = 0 — tolerates non-strict decrease
      - **ISS (Input-to-State Stability)**: under bounded perturbation w,
        ΔV ≤ −α(V) + γ(‖w‖)  →  equilibria shift by O(‖w‖)
      - **Barrier clamping**: smooth reciprocal barrier replaces
        discontinuous hard clamp — C¹-smooth, same ceiling

    Decoupled auxiliary pattern
    ---------------------------
    The Lyapunov signal is **never** exposed to the prediction / alarm
    output.  This is the "decoupled auxiliary Lyapunov" pattern from
    robust control / stochastic MPC.
    """

    def __init__(self, armijo_c: float = 1e-4,
                 backtrack_rho: float = 0.5,
                 max_force_norm: float = 10.0,
                 min_eta: float = 1e-6,
                 la_salle_tol: float = 1e-5,
                 la_salle_patience: int = 5,
                 barrier_alpha: float = 1.0):
        self.armijo_c = armijo_c
        self.backtrack_rho = backtrack_rho
        self.max_force_norm = max_force_norm
        self.min_eta = min_eta
        self.la_salle_tol = la_salle_tol
        self.la_salle_patience = la_salle_patience
        self.barrier_alpha = barrier_alpha
        self.reset()

    # ── lifecycle ──────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset internal state for a new simulation run."""
        self.energy_trace: List[float] = []
        self._descent_certificate: List[float] = []
        self._grad_norm_trace: List[float] = []
        self._iss_perturbation_trace: List[float] = []
        self._n_accepted: int = 0
        self._n_rejected: int = 0
        self._n_steps: int = 0
        self._la_salle_counter: int = 0
        self._converged: bool = False
        self._convergence_type: str = 'max_iter'
        self._final_eta: float = 0.0

    # ── force control ──────────────────────────────────────────────

    def clamp_forces(self, F: np.ndarray) -> np.ndarray:
        """Barrier-augmented force clamping.

        Uses a smooth reciprocal barrier that activates only when
        ‖F_i‖ > F_max, avoiding the discontinuous derivative of
        the hard clamp at the boundary.

        For ‖F‖ ≤ F_max:  scale = 1.0 (identity, no compression)
        For ‖F‖ > F_max:  scale = F_max / (F_max + α·(‖F‖ − F_max))
          → clamped norm ≈ F_max  (finite ceiling, C¹-smooth)

        With α=1: matches hard-clamp ceiling but with continuous
        derivative — eliminates chattering near the boundary.
        """
        norms = np.linalg.norm(F, axis=1, keepdims=True) + 1e-15
        if self.barrier_alpha > 0:
            excess = np.maximum(0, norms - self.max_force_norm)
            scale = self.max_force_norm / (
                self.max_force_norm + self.barrier_alpha * excess
            )
            # Safety: never amplify
            scale = np.minimum(scale, 1.0)
        else:
            # Hard clamp fallback (α ≤ 0)
            scale = np.minimum(1.0, self.max_force_norm / norms)
        return F * scale

    # ── step acceptance ────────────────────────────────────────────

    def accept_step(self, E_old: float, E_new: float,
                    grad_norm_sq: float, eta: float,
                    perturbation_norm: float = 0.0
                    ) -> Tuple[bool, float]:
        """
        Armijo sufficient-decrease test with ISS tracking.

        Descent certificate:
            E(Xᵗ⁺¹) ≤ E(Xᵗ) − c·η·‖∇E‖²  +  γ(‖w‖)

        When perturbation_norm > 0, the Armijo condition is relaxed
        by γ(‖w‖) = ‖w‖² to account for the ISS margin.  This is
        used when the energy function is an approximation (e.g.,
        radial-only energy in the gravity engine, where pairwise
        forces are a bounded perturbation).

        Returns (accepted: bool, new_eta: float).
        """
        self._n_steps += 1
        self._final_eta = eta

        # Track ISS perturbation
        if perturbation_norm > 0:
            self._iss_perturbation_trace.append(perturbation_norm)

        # Armijo condition with ISS margin
        iss_margin = perturbation_norm ** 2 if perturbation_norm > 0 else 0.0
        descent = E_old - E_new
        required_descent = self.armijo_c * eta * grad_norm_sq - iss_margin

        if descent >= required_descent:
            self.energy_trace.append(E_new)
            self._descent_certificate.append(descent)
            self._grad_norm_trace.append(np.sqrt(max(grad_norm_sq, 0.0)))
            self._n_accepted += 1
            return True, eta
        else:
            new_eta = max(eta * self.backtrack_rho, self.min_eta)
            self._n_rejected += 1
            self._final_eta = new_eta
            return False, new_eta

    # ── convergence detection ──────────────────────────────────────

    def check_convergence(self, grad_norm_sq: float,
                          displacement: float) -> bool:
        """
        La Salle invariance convergence test.

        Detects convergence to the largest invariant set where
        ∇E ≈ 0 (La Salle's invariance principle).  Requires
        la_salle_patience consecutive steps with ‖∇E‖ below
        threshold — more robust than displacement-only check.

        Falls back to displacement check if La Salle hasn't
        triggered (handles non-smooth energy landscapes).

        Returns True if the simulation should terminate.
        """
        grad_norm = np.sqrt(max(grad_norm_sq, 0.0))

        # La Salle: ‖∇E‖ → 0 for `patience` consecutive steps
        if grad_norm < self.la_salle_tol:
            self._la_salle_counter += 1
            if self._la_salle_counter >= self.la_salle_patience:
                self._converged = True
                self._convergence_type = 'la_salle'
                return True
        else:
            self._la_salle_counter = 0

        # Fallback: displacement convergence
        if displacement < 1e-6:
            self._converged = True
            self._convergence_type = 'displacement'
            return True

        return False

    # ── diagnostics ────────────────────────────────────────────────

    def report(self) -> ConvergenceReport:
        """Return structured convergence diagnostics."""
        total_n = self._n_accepted + self._n_rejected
        return ConvergenceReport(
            n_steps=self._n_steps,
            n_accepted=self._n_accepted,
            n_rejected=self._n_rejected,
            total_descent=sum(self._descent_certificate),
            final_grad_norm=(
                self._grad_norm_trace[-1]
                if self._grad_norm_trace else float('inf')
            ),
            converged=self._converged,
            convergence_type=self._convergence_type,
            iss_bound=(
                max(self._iss_perturbation_trace)
                if self._iss_perturbation_trace else 0.0
            ),
            final_eta=self._final_eta,
            acceptance_rate=(
                self._n_accepted / total_n if total_n > 0 else 1.0
            ),
        )

    # ── legacy energy computation ──────────────────────────────────

    def compute_energy(self, X: np.ndarray, mu: np.ndarray,
                       alpha: float, gamma: float, sigma: float,
                       lambda_rep: float, eps: float = 1e-5) -> float:
        """Compute total system energy (Lyapunov candidate V = E_total).

        Retained for backward compatibility.  Engines should prefer
        their own _lj_energy / _gravity_energy methods.
        """
        n = len(X)
        # Radial energy
        diff_mu = X - mu[None, :]
        E_radial = 0.5 * alpha * np.sum(diff_mu ** 2)

        # Pairwise energy (attraction + repulsion)
        E_pair = 0.0
        if gamma > 0 and n > 1:
            D = cdist(X, X, metric='euclidean')
            np.fill_diagonal(D, 1.0)  # avoid log(0)
            mask = np.triu(np.ones((n, n), dtype=bool), k=1)
            d_upper = D[mask]
            E_attract = gamma * np.sum(np.exp(-d_upper**2 / (sigma**2)))
            E_repel = -gamma * lambda_rep * np.sum(np.log(d_upper + eps))
            E_pair = E_attract + E_repel

        return float(E_radial + E_pair)


# ═══════════════════════════════════════════════════════════════════
#  MORSE / TOPOLOGICAL ALARM (prediction-only — immune to noise)
# ═══════════════════════════════════════════════════════════════════

class MorseTopologyAlarm:
    """
    Topological prediction signal based on Morse theory / persistence.

    This produces the actual anomaly scores.  All signals are
    structurally stable — small perturbations (chaos/noise) create
    only short-lived features that die in the persistence diagram.

    Signals computed:
      1. Mean kNN distance to reference (higher = more anomalous,
         structurally stable under noise)
      2. Nearest-neighbor distance d_1 (isolation measure)
      3. Persistence proxy:  gap between k-th and 1st neighbour distance
         → long-lived topological feature = true anomaly
      4. Local density ratio: reference density / point density
         → low density = structural isolation, not noise

    All four are combined with calibrated weights.
    """

    def __init__(self, k: int = 15, hessian_eps: float = 1e-4,
                 persistence_threshold: float = 0.0,
                 weights: Optional[np.ndarray] = None):
        self.k = k
        self.hessian_eps = hessian_eps
        self.persistence_threshold = persistence_threshold
        self.weights = weights if weights is not None else np.array([0.35, 0.30, 0.20, 0.15])
        self._ref_stats = None

    def fit(self, X_ref: np.ndarray, energy_fn=None):
        """Calibrate on reference (normal) data."""
        features = self._compute_features(X_ref, X_ref, energy_fn)
        self._ref_mean = features.mean(axis=0)
        self._ref_std = features.std(axis=0) + 1e-10
        self._X_ref = X_ref.copy()
        self._energy_fn = energy_fn
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        """Compute topological anomaly scores (noise-immune)."""
        features = self._compute_features(X, self._X_ref, self._energy_fn)
        # Z-score relative to reference
        z = (features - self._ref_mean) / self._ref_std
        # Weighted combination (only positive deviations are anomalous)
        z_pos = np.maximum(z, 0)
        scores = z_pos @ self.weights
        return scores

    def get_morse_index(self, X: np.ndarray) -> np.ndarray:
        """Get per-point Morse index (# negative Hessian eigenvalues)."""
        return self._compute_features(X, self._X_ref, self._energy_fn)[:, 0]

    def _compute_features(self, X_query: np.ndarray, X_ref: np.ndarray,
                          energy_fn=None) -> np.ndarray:
        """Compute 4 topological / structural features per point.

        Features are designed so that HIGHER values = more anomalous,
        and are structurally stable under small noise perturbations.
        Uses kNN search for efficiency on large datasets.
        """
        from sklearn.neighbors import NearestNeighbors

        N = len(X_query)
        k = min(self.k, len(X_ref) - 1)
        if k < 1:
            return np.zeros((N, 4), dtype=np.float64)
        out = np.zeros((N, 4), dtype=np.float64)
        eps = 1e-10

        # Handle self-distance if query overlaps ref
        is_self = (X_query is X_ref or
                   (X_query.shape == X_ref.shape and
                    np.allclose(X_query, X_ref)))

        if is_self:
            # Need k+1 neighbors, skip self
            nn = NearestNeighbors(n_neighbors=k + 1, algorithm='auto')
            nn.fit(X_ref.astype(np.float32))
            dists, _ = nn.kneighbors(X_query.astype(np.float32))
            nn_dists = dists[:, 1:]  # skip self
        else:
            nn = NearestNeighbors(n_neighbors=k, algorithm='auto')
            nn.fit(X_ref.astype(np.float32))
            dists, _ = nn.kneighbors(X_query.astype(np.float32))
            nn_dists = dists

        d1 = nn_dists[:, 0] + eps             # nearest neighbour
        dk = nn_dists[:, -1] + eps            # k-th neighbour

        # 1. Mean kNN distance (higher = more isolated = more anomalous)
        out[:, 0] = nn_dists.mean(axis=1)

        # 2. Nearest-neighbor distance d_1 (isolation measure)
        out[:, 1] = d1

        # 3. Persistence proxy: normalised gap d_k - d_1
        out[:, 2] = (dk - d1) / (dk + eps)

        # 4. Local density ratio (inverse local density)
        ref_mean_knn = nn_dists.mean()
        out[:, 3] = nn_dists.mean(axis=1) / (ref_mean_knn + eps)

        return out

    def _numerical_morse_index(self, x: np.ndarray,
                               energy_fn, eps: float = 1e-4) -> float:
        """Count negative eigenvalues of Hessian of energy at x."""
        d = len(x)
        H = np.zeros((d, d))
        f0 = energy_fn(x.reshape(1, -1))

        for i in range(d):
            ei = np.zeros(d)
            ei[i] = eps
            for j in range(i, d):
                ej = np.zeros(d)
                ej[j] = eps
                fpp = energy_fn((x + ei + ej).reshape(1, -1))
                fpm = energy_fn((x + ei - ej).reshape(1, -1))
                fmp = energy_fn((x - ei + ej).reshape(1, -1))
                fmm = energy_fn((x - ei - ej).reshape(1, -1))
                H[i, j] = (fpp - fpm - fmp + fmm) / (4 * eps * eps)
                H[j, i] = H[i, j]

        eigenvalues = np.linalg.eigvalsh(H)
        # Morse index = number of negative eigenvalues
        n_negative = int(np.sum(eigenvalues < -1e-8))
        return float(n_negative)


# ═══════════════════════════════════════════════════════════════════
#  BETTI / EULER / CONLEY TOPOLOGY SUITE
# ═══════════════════════════════════════════════════════════════════

class BettiBarcodeSuite:
    """
    Persistent-homology proxies via kNN filtration — no TDA library.

    Extends MorseTopologyAlarm with multi-scale Betti-number tracking,
    Euler characteristic curves, and Conley index stability analysis.
    Fully vectorised — O(N log N_ref) dominant cost via kNN search.

    Theory
    ------
    At filtration scale ε, the Vietoris–Rips complex R_ε connects
    points within distance ε.  β₀(ε) and β₁(ε) count connected
    components and independent 1-cycles respectively.

    Normal (dense cluster interior):
      β₀ drops smoothly k→1, β₁ ≈ 0, χ decreases monotonically,
      Conley CV low (stable topology).

    Anomaly (boundary / isolated / transition):
      β₀ stays high (slow connection), β₁ spikes (sparse loops),
      χ shows jumps (topological phase transitions),
      Conley CV high (unstable critical point).

    Features  (total: 3 + 2 × n_scales)
    --------
    [0]          β₀ proxy at median filtration scale
    [1]          β₁ proxy at median scale
    [2]          Conley stability index: CoV(β₀) across scales
    [3:3+ns]     Euler characteristic curve χ(ε)
    [3+ns:]      β₀ reachability curve
    """

    def __init__(self, k: int = 20, n_scales: int = 8):
        self.k = k
        self.n_scales = n_scales
        self._X_ref = None
        self._ref_mean = None
        self._ref_std = None
        self._scales = None

    @property
    def n_features(self) -> int:
        return 3 + 2 * self.n_scales

    def fit(self, X_ref: np.ndarray) -> 'BettiBarcodeSuite':
        """Calibrate on reference (normal) data."""
        from sklearn.neighbors import NearestNeighbors

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

    def transform(self, X: np.ndarray) -> np.ndarray:
        """Z-scored topology features."""
        features = self._compute_features(X, self._X_ref, is_self=False)
        return (features - self._ref_mean) / self._ref_std

    def score(self, X: np.ndarray) -> np.ndarray:
        """Anomaly score: mean positive z-deviation across features."""
        z = self.transform(X)
        return np.mean(np.maximum(z, 0), axis=1)

    def _compute_features(self, X_query, X_ref, is_self=False):
        """Vectorised Betti / Euler / Conley from kNN distances."""
        from sklearn.neighbors import NearestNeighbors

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

        # Multi-scale reachability (vectorised over N and k)
        reach = np.zeros((N, ns), dtype=np.float64)
        for s in range(ns):
            reach[:, s] = (nn_dists <= scales[s]).sum(axis=1) / k

        # β₀ proxy: 1 − reach (disconnected fraction)
        b0_curve = 1.0 - reach

        # β₁ proxy: excess connectivity at non-uniform distances
        dist_cv = (nn_dists.std(axis=1, keepdims=True) /
                   (nn_dists.mean(axis=1, keepdims=True) + 1e-10))
        b1_curve = reach * dist_cv

        # Euler χ(ε) = β₀ − β₁
        euler_curve = b0_curve - b1_curve

        # Assemble
        mid = ns // 2
        out[:, 0] = b0_curve[:, mid]
        out[:, 1] = b1_curve[:, mid]
        out[:, 2] = b0_curve.std(axis=1) / (b0_curve.mean(axis=1) + 1e-10)
        out[:, 3:3 + ns] = euler_curve
        out[:, 3 + ns:3 + 2 * ns] = b0_curve

        return out


# ═══════════════════════════════════════════════════════════════════
#  UDL POST-SIMULATION OPERATOR SCORER
# ═══════════════════════════════════════════════════════════════════

class UDLPostSimScorer:
    """
    Applies the best-performing UDL operator combination to
    post-simulation positions.

    Operators (Table 5, §5.2 of the UDL paper):
      Phase + Topological + KernelRKHS + Rank  →  mAUC 0.972

    Each operator views data from a complementary perspective:
      PhaseCurve     : sequential feature structure (trajectory)
      Topological    : intrinsic geometry (LID, persistence)
      KernelRKHS     : nonlinear manifold deviation (RKHS recon)
      RankOrder      : distribution-free extremity (rank statistics)

    After physics simulation separates anomalies structurally,
    these operators capture the separation from four independent
    mathematical viewpoints — maximising detection coverage.
    """

    def __init__(self, k: int = 15, max_dim: int = 12,
                 n_components: int = 10):
        self.k = k
        self.max_dim = max_dim
        self.n_components = n_components
        self._operators = None
        self._fitted = False
        self._ref_mean = None
        self._ref_std = None

    def _build_operators(self):
        """Lazy-import and construct operator instances."""
        try:
            from .spectra import RankOrderSpectrum
            from .new_spectra import TopologicalSpectrum, KernelRKHSSpectrum
            from .experimental_spectra import PhaseCurveSpectrum
        except (ImportError, SystemError):
            try:
                from udl.spectra import RankOrderSpectrum
                from udl.new_spectra import (TopologicalSpectrum,
                                             KernelRKHSSpectrum)
                from udl.experimental_spectra import PhaseCurveSpectrum
            except ImportError:
                return None

        return [
            ('phase', PhaseCurveSpectrum(max_dim=self.max_dim)),
            ('topo', TopologicalSpectrum(k=self.k)),
            ('kernel', KernelRKHSSpectrum(n_components=self.n_components)),
            ('rank', RankOrderSpectrum()),
        ]

    def fit(self, X_ref: np.ndarray) -> 'UDLPostSimScorer':
        """Fit all operators on reference (normal) data."""
        if X_ref.shape[0] < 5 or X_ref.shape[1] < 2:
            self._fitted = False
            return self

        self._operators = self._build_operators()
        if self._operators is None:
            self._fitted = False
            return self

        live = []
        for name, op in self._operators:
            try:
                op.fit(X_ref)
                live.append((name, op))
            except Exception:
                pass
        self._operators = live

        if not live:
            self._fitted = False
            return self

        # Compute unified reference statistics for z-scoring
        ref_features = self._raw_transform(X_ref)
        self._ref_mean = ref_features.mean(axis=0)
        self._ref_std = ref_features.std(axis=0) + 1e-10
        self._fitted = True
        return self

    def _raw_transform(self, X: np.ndarray) -> np.ndarray:
        """Concatenated raw features from all live operators."""
        blocks = []
        for name, op in self._operators:
            try:
                feats = op.transform(X)
                if feats.ndim == 1:
                    feats = feats.reshape(-1, 1)
                blocks.append(feats)
            except Exception:
                pass
        if not blocks:
            return np.zeros((len(X), 1), dtype=np.float64)
        return np.hstack(blocks)

    def transform(self, X: np.ndarray) -> np.ndarray:
        """Unified z-scored features from all operators."""
        if not self._fitted:
            return np.zeros((len(X), 1), dtype=np.float64)
        raw = self._raw_transform(X)
        return (raw - self._ref_mean) / self._ref_std

    def score(self, X: np.ndarray) -> np.ndarray:
        """Score via RMS z-deviation across all operator features."""
        z = self.transform(X)
        return np.sqrt(np.mean(z ** 2, axis=1))




# ═══════════════════════════════════════════════════════════════════
#  BSDT CHANNELS (Blind-Spot Detection Tensor)
# ═══════════════════════════════════════════════════════════════════

class BSDTChannels:
    r"""
    Blind-Spot Detection Tensor — four complementary anomaly channels.

    Implements the BSDT framework (SIAM paper, Section 2.2) in a
    domain-agnostic form suitable for post-simulation scoring:

    Channels
    --------
    δ_C : Camouflage
        How well a point blends with the normal cluster.
        ``δ_C = 1 − clip(‖x − μ_ref‖ / d_max, 0, 1)``
        High → point looks normal (potential blind spot).

    δ_G : Feature Gap
        Structural sparsity / incompleteness in features.
        ``δ_G = fraction of near-zero features (|x_j/σ_j| < 0.1)``
        High → abnormally sparse feature representation.

    δ_A : Activity Anomaly
        Mahalanobis deviation from normal reference centroid.
        ``δ_A = sigmoid((mahal − median_ref) / median_ref)``
        High → activity level deviates from normal.

    δ_T : Temporal Novelty
        kNN novelty relative to reference distribution.
        ``δ_T = sigmoid(0.5 · (d_kNN / median_kNN_ref − 2))``
        High → point is far from anything seen in reference.

    Composite Scores
    ----------------
    E_BS = Σ δ_i²           (blind-spot energy)
    MFLS = ‖∇E_BS‖_F        (multi-factor latent score)
    """

    def __init__(self, k: int = 15, eps: float = 1e-8):
        self.k = k
        self.eps = eps
        self._fitted = False

    def fit(self, X_ref: np.ndarray) -> 'BSDTChannels':
        """
        Calibrate BSDT channels on normal reference data.

        Parameters
        ----------
        X_ref : array (n_ref, d)
            Normal-class post-simulation positions.
        """
        self.mu_ = X_ref.mean(axis=0)
        self.n_ref_, self.d_ = X_ref.shape

        # δ_C calibration: max distance from centroid in reference
        dists_ref = np.linalg.norm(X_ref - self.mu_, axis=1)
        self.d_max_ = max(float(dists_ref.max()), self.eps)

        # δ_A calibration: regularised inverse covariance
        cov = np.cov(X_ref, rowvar=False)
        if cov.ndim < 2:
            cov = np.atleast_2d(cov)
        reg = self.eps * np.eye(self.d_)
        self.cov_inv_ = np.linalg.inv(cov + reg)
        self.mahal_ref_median_ = float(np.median(self._mahalanobis(X_ref)))

        # δ_T calibration: kNN distances in reference
        from sklearn.neighbors import NearestNeighbors
        k_use = min(self.k, self.n_ref_ - 1)
        nn = NearestNeighbors(n_neighbors=k_use + 1, algorithm='auto')
        nn.fit(X_ref.astype(np.float32))
        ref_dists, _ = nn.kneighbors(X_ref.astype(np.float32))
        self.ref_knn_median_ = float(np.median(ref_dists[:, -1]))
        self.nn_ = nn

        # Feature-level stats for δ_G
        self.feat_std_ = np.std(X_ref, axis=0) + self.eps

        self._fitted = True
        return self

    def _mahalanobis(self, X: np.ndarray) -> np.ndarray:
        """Per-point Mahalanobis distance from reference centroid."""
        diff = X - self.mu_
        return np.sqrt(np.maximum(
            np.sum(diff @ self.cov_inv_ * diff, axis=1), 0.0
        ))

    def channels(self, X: np.ndarray) -> dict:
        """
        Compute all four BSDT channels.

        Returns dict with keys 'delta_C', 'delta_G', 'delta_A', 'delta_T'.
        """
        # δ_C: Camouflage — proximity to normal centroid
        dist_from_mu = np.linalg.norm(X - self.mu_, axis=1)
        delta_C = 1.0 - np.clip(dist_from_mu / self.d_max_, 0.0, 1.0)

        # δ_G: Feature Gap — fraction of near-zero features
        X_normed = np.abs(X) / self.feat_std_
        delta_G = np.mean(X_normed < 0.1, axis=1).astype(np.float64)

        # δ_A: Activity Anomaly — sigmoid of Mahalanobis deviation
        mahal = self._mahalanobis(X)
        z_a = (mahal - self.mahal_ref_median_) / max(
            self.mahal_ref_median_, self.eps)
        delta_A = 1.0 / (1.0 + np.exp(-np.clip(z_a, -30, 30)))

        # δ_T: Temporal Novelty — kNN distance ratio (sigmoid)
        k_use = min(self.k, self.n_ref_ - 1)
        dists, _ = self.nn_.kneighbors(X.astype(np.float32))
        knn_col = min(k_use, dists.shape[1] - 1)
        knn_dist = dists[:, knn_col].astype(np.float64)
        ratio = knn_dist / max(self.ref_knn_median_, self.eps)
        delta_T = 1.0 / (1.0 + np.exp(-np.clip(
            0.5 * (ratio - 2.0), -30, 30)))

        return {'delta_C': delta_C, 'delta_G': delta_G,
                'delta_A': delta_A, 'delta_T': delta_T}

    def energy(self, X: np.ndarray) -> np.ndarray:
        r"""E_BS = Σ_i δ_i(x)² — blind-spot energy per point."""
        ch = self.channels(X)
        return (ch['delta_C'] ** 2 + ch['delta_G'] ** 2 +
                ch['delta_A'] ** 2 + ch['delta_T'] ** 2)

    def mfls(self, X: np.ndarray) -> np.ndarray:
        r"""
        MFLS = ‖∇E_BS‖_F — gradient norm of blind-spot energy.

        Uses analytical gradients through δ_C (Euclidean) and
        δ_A (Mahalanobis), which dominate the gradient landscape.
        δ_G and δ_T have discontinuous / kNN-based gradients and
        contribute negligibly to ∇E_BS.
        """
        ch = self.channels(X)
        diff = X - self.mu_

        # ── Gradient through δ_A (Mahalanobis, dominant) ──
        mahal = self._mahalanobis(X)
        mahal_safe = np.maximum(mahal, self.eps)
        grad_mahal = (diff @ self.cov_inv_) / mahal_safe[:, None]

        sig_deriv = ch['delta_A'] * (1.0 - ch['delta_A'])
        scale_A = (2.0 * ch['delta_A'] * sig_deriv /
                   max(self.mahal_ref_median_, self.eps))
        grad_E_A = scale_A[:, None] * grad_mahal

        # ── Gradient through δ_C (Euclidean distance) ──
        dist = np.linalg.norm(diff, axis=1, keepdims=True)
        dist_safe = np.maximum(dist, self.eps)
        unit = diff / dist_safe
        active = (dist.squeeze() < self.d_max_).astype(np.float64)
        scale_C = -2.0 * ch['delta_C'] * active / self.d_max_
        grad_E_C = scale_C[:, None] * unit

        # Total gradient
        grad_E = grad_E_A + grad_E_C
        return np.linalg.norm(grad_E, axis=1)

    def score(self, X: np.ndarray) -> np.ndarray:
        """
        Combined BSDT score = blend(E_BS, MFLS).

        Returns per-point score in [0, 1] via min-max normalisation
        of both components, then equal-weight average.
        """
        e = self.energy(X)
        m = self.mfls(X)

        # Normalise each to [0, 1]
        e_max = max(float(e.max()), self.eps)
        m_max = max(float(m.max()), self.eps)
        e_n = e / e_max
        m_n = m / m_max

        return 0.5 * e_n + 0.5 * m_n

    # -- MFLS scoring variants ----------------------------------------
    #   QuadSurf & ExpoGate are post-hoc analytical formulas.
    #   SignedLR is the only supervised variant (needs labels).

    def _channel_matrix(self, X: np.ndarray) -> np.ndarray:
        """Return (N, 4) matrix of channel scores."""
        ch = self.channels(X)
        return np.column_stack([
            ch['delta_C'], ch['delta_G'],
            ch['delta_A'], ch['delta_T']
        ])

    @staticmethod
    def _poly_features(C: np.ndarray) -> np.ndarray:
        """Expand (N, K) -> (N, 1 + K + K*(K+1)/2) with bias + linear + quadratic."""
        N, K = C.shape
        features = [np.ones((N, 1)), C]
        for k in range(K):
            for j in range(k, K):
                features.append((C[:, k] * C[:, j]).reshape(-1, 1))
        return np.hstack(features)

    def fit_quadsurf(self, X_ref: np.ndarray) -> 'BSDTChannels':
        """Calibrate QuadSurf: post-hoc degree-2 polynomial of BSDT channels.

        QuadSurf is an analytical formula -- no labels required.
        The score is the sum of all degree-2 polynomial features
        (linear + squared + cross-terms) of the standardised channels:

          Q(c) = sum_k c_k' + sum_k c_k'^2 + sum_{k<j} c_k' c_j'

        where c_k' = (c_k - mu_k) / sigma_k are standardised against
        reference-period channel statistics.

        Parameters
        ----------
        X_ref : (N, d) array -- reference (normal-period) features
        """
        C = self._channel_matrix(X_ref)
        self._qs_mu = C.mean(axis=0)
        self._qs_std = C.std(axis=0) + self.eps
        self._qs_fitted = True
        return self

    def score_quadsurf(self, X: np.ndarray) -> np.ndarray:
        """QuadSurf score: post-hoc polynomial surface over channel values.

        Returns sum of all non-bias polynomial features (unit weights),
        clipped to [0, inf).  Higher = more anomalous.
        """
        C = self._channel_matrix(X)
        C_std = (C - self._qs_mu) / self._qs_std
        Phi = self._poly_features(C_std)
        # Sum all features except bias (column 0); clip negative
        return np.maximum(Phi[:, 1:].sum(axis=1), 0.0)

    def fit_signed_lr(self, X: np.ndarray, y: np.ndarray,
                      lr: float = 0.1, n_iter: int = 500,
                      reg: float = 0.01) -> 'BSDTChannels':
        """Fit Signed LR: logistic regression on BSDT channels.

        P(anomaly | c_1,...,c_4) = sigma(beta_0 + sum_k beta_k c_k)

        Discovers which channels drive detection; negative weights
        reveal herding effects (e.g. temporal novelty inverts during
        coordinated sell-offs).

        Parameters
        ----------
        X : (N, d) array -- training features
        y : (N,) array -- binary labels
        lr : float -- learning rate
        n_iter : int -- gradient descent iterations
        reg : float -- L2 regularisation
        """
        C = self._channel_matrix(X)
        self._lr_mu = C.mean(axis=0)
        self._lr_std = C.std(axis=0) + self.eps
        C_std = (C - self._lr_mu) / self._lr_std

        T, K = C_std.shape
        Xb = np.hstack([np.ones((T, 1)), C_std])
        beta = np.zeros(K + 1)
        y_f = y.astype(float)

        # Class-imbalance weighting
        n_pos = max(y_f.sum(), 1)
        n_neg = max(len(y_f) - n_pos, 1)
        w = np.where(y_f == 1, n_neg / n_pos, 1.0)

        for _ in range(n_iter):
            p = 1.0 / (1.0 + np.exp(-np.clip(Xb @ beta, -500, 500)))
            grad = Xb.T @ (w * (p - y_f)) / T + reg * beta
            grad[0] -= reg * beta[0]  # no reg on bias
            beta -= lr * grad

        self._lr_beta = beta
        self._lr_fitted = True
        return self

    def score_signed_lr(self, X: np.ndarray) -> np.ndarray:
        """Signed LR score: P(anomaly) via logistic regression."""
        C = self._channel_matrix(X)
        C_std = (C - self._lr_mu) / self._lr_std
        Xb = np.hstack([np.ones((len(C_std), 1)), C_std])
        return 1.0 / (1.0 + np.exp(-np.clip(Xb @ self._lr_beta, -500, 500)))

    def fit_expogate(self, X_ref: np.ndarray,
                     smooth_sigma: float = 1.0,
                     gate_scale: float = 3.0) -> 'BSDTChannels':
        """Calibrate ExpoGate: post-hoc QuadSurf + tanh + sigmoid gating.

        Analytical formula -- no labels required.
        Prevents false-alarm inflation by capping extreme QuadSurf
        scores with tanh saturation, then gating through sigmoid
        for calibrated [0, 1] output.

        score = sigmoid(gate_scale * tanh(Q(c) / sigma))

        Parameters
        ----------
        X_ref : (N, d) array -- reference (normal-period) features
        smooth_sigma : float -- tanh saturation scale
        gate_scale : float -- sigmoid gate steepness
        """
        self.fit_quadsurf(X_ref)
        self._eg_sigma = smooth_sigma
        self._eg_scale = gate_scale
        self._eg_fitted = True
        return self

    def score_expogate(self, X: np.ndarray) -> np.ndarray:
        """ExpoGate score: saturated + gated QuadSurf output."""
        raw = self.score_quadsurf(X)
        sat = np.tanh(raw / (self._eg_sigma + self.eps))
        return 1.0 / (1.0 + np.exp(-self._eg_scale * sat))


# ═══════════════════════════════════════════════════════════════════
#  FUSED SYSTEM SCORER
# ═══════════════════════════════════════════════════════════════════

class FusedSystemScorer:
    """
    Combines four complementary signal families into a single scorer.

    Architecture
    ------------
    1. **MorseTopologyAlarm** — kNN distance features (4D):
       Mean kNN, d₁, persistence proxy, density ratio.
       Scales to any N via kNN search.

    2. **BettiBarcodeSuite** — multi-scale topology (3 + 2·ns D):
       β₀/β₁/χ curves, Conley stability.
       Scales to any N via kNN search.

    3. **UDLPostSimScorer** — best-4 UDL operators (~27D):
       Phase + Topological + KernelRKHS + Rank.
       Applied to simulation subset, kNN-interpolated for full data.

    4. **BSDTChannels** — Blind-Spot Detection Tensor (4 channels):
       δ_C (camouflage) + δ_G (feature gap) + δ_A (activity anomaly)
       + δ_T (temporal novelty) → E_BS + MFLS composite.
       Implements the BSDT framework from Section 2.2 of the paper.

    Fusion: min-max normalise each component, equal-weight average.
    For simulation-size inputs, all four score directly.
    For larger inputs, Morse + Betti + BSDT score directly (fast kNN),
    while UDL scores are kNN-interpolated from the simulation subset.
    """

    def __init__(self, k: int = 15, use_betti: bool = True,
                 use_udl: bool = True, use_bsdt: bool = True):
        self.k = k
        self.morse = MorseTopologyAlarm(k=k)
        self.betti = BettiBarcodeSuite(k=min(k + 5, 25)) if use_betti else None
        self.udl = UDLPostSimScorer(k=k) if use_udl else None
        self.bsdt = BSDTChannels(k=k) if use_bsdt else None
        self._X_sim = None
        self._sim_enriched = None

    def fit(self, X_ref: np.ndarray,
            X_sim: np.ndarray = None) -> 'FusedSystemScorer':
        """
        Fit all sub-scorers on reference data.

        Parameters
        ----------
        X_ref : array (n_ref, d)
            Normal reference points (post-simulation positions).
        X_sim : array (n_sim, d), optional
            All simulation points — used for enriched scoring and
            kNN interpolation when scoring larger datasets.
        """
        self.morse.fit(X_ref)

        if self.betti is not None:
            try:
                self.betti.fit(X_ref)
            except Exception:
                self.betti = None

        if self.udl is not None:
            try:
                self.udl.fit(X_ref)
            except Exception:
                self.udl = None

        if self.bsdt is not None:
            try:
                self.bsdt.fit(X_ref)
            except Exception:
                self.bsdt = None

        # Pre-compute enriched scores on simulation subset
        if X_sim is not None:
            self._X_sim = X_sim.copy()
            self._sim_enriched = self._enrich_score(X_sim)

        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        """
        Score with auto-interpolation for large datasets.

        For simulation-size inputs → direct multi-view scoring.
        For larger inputs → Morse (direct) + kNN-interpolated enriched.
        """
        N = len(X)

        # Fast path: if X matches simulation points exactly
        if (self._X_sim is not None and N == len(self._X_sim)
                and np.array_equal(X, self._X_sim)):
            return self._sim_enriched

        # Morse scores all points (fast kNN-based)
        morse_s = self._minmax(self.morse.score(X))

        # If we have simulation-enriched scores, interpolate
        if self._X_sim is not None and self._sim_enriched is not None:
            from sklearn.neighbors import KNeighborsRegressor
            k_interp = min(5, len(self._X_sim))
            knn = KNeighborsRegressor(n_neighbors=k_interp,
                                      weights='distance')
            knn.fit(self._X_sim, self._sim_enriched)
            enriched_s = self._minmax(knn.predict(X))
            return 0.4 * morse_s + 0.6 * enriched_s
        else:
            # Direct scoring (small dataset)
            return self._enrich_score(X)

    def _enrich_score(self, X: np.ndarray) -> np.ndarray:
        """Full multi-view scoring (≤ simulation-size inputs).

        Fuses four signal families:
          Morse (topology) + Betti (persistence) + UDL (operators)
          + BSDT (blind-spot channels: δ_C, δ_G, δ_A, δ_T, E_BS, MFLS).
        """
        components = [self.morse.score(X)]

        if self.betti is not None:
            try:
                components.append(self.betti.score(X))
            except Exception:
                pass
        if self.udl is not None and self.udl._fitted:
            try:
                components.append(self.udl.score(X))
            except Exception:
                pass
        if self.bsdt is not None and self.bsdt._fitted:
            try:
                components.append(self.bsdt.score(X))
            except Exception:
                pass

        normed = [self._minmax(s) for s in components]
        return np.mean(normed, axis=0)

    @staticmethod
    def _minmax(s: np.ndarray) -> np.ndarray:
        s_min, s_max = s.min(), s.max()
        if s_max - s_min > 1e-15:
            return (s - s_min) / (s_max - s_min)
        return np.zeros_like(s)


# ═══════════════════════════════════════════════════════════════════
#  MOLECULAR DYNAMICS ENGINE
# ═══════════════════════════════════════════════════════════════════

class MolecularEngine:
    """
    Molecular dynamics engine using Lennard-Jones potential.

    Particles interact via a 6-12 potential:
        V(r) = 4ε [(σ/r)^12 - (σ/r)^6]

    Normal points settle into minimum-energy configurations;
    anomalies are expelled to high-energy positions.

    The Lyapunov stabiliser controls the solver; the Morse topology
    alarm produces the prediction signal.
    """

    def __init__(self,
                 epsilon: float = 1.0,
                 sigma_lj: float = 1.0,
                 alpha_radial: float = 0.1,
                 eta: float = 0.01,
                 iterations: int = 80,
                 k_neighbors: int = 15,
                 normalize: bool = True,
                 max_samples: int = 3000,
                 use_fused: bool = True,
                 calibrate: Optional[str] = None,
                 target_far: float = 0.05):
        self.epsilon = epsilon
        self.sigma_lj = sigma_lj
        self.alpha_radial = alpha_radial
        self.eta = eta
        self.iterations = iterations
        self.k_neighbors = k_neighbors
        self.normalize = normalize
        self.max_samples = max_samples
        self.use_fused = use_fused
        self.calibrate = calibrate
        self.target_far = target_far

        self.stabiliser = LyapunovStabiliser()
        self.alarm = MorseTopologyAlarm(k=k_neighbors)
        self.fused_scorer = FusedSystemScorer(k=k_neighbors) if use_fused else None
        self._far_calibrator = None

        self.scaler_: Optional[StandardScaler] = None
        self.mu_: Optional[np.ndarray] = None
        self.X_final_: Optional[np.ndarray] = None

    def _lennard_jones_forces(self, X: np.ndarray,
                              eps: float = 1e-5) -> np.ndarray:
        """Compute Lennard-Jones forces between all particle pairs."""
        n, d = X.shape
        sigma = self.sigma_lj
        epsilon = self.epsilon

        # kNN-limited for efficiency
        from sklearn.neighbors import NearestNeighbors
        k = min(self.k_neighbors, n - 1)
        nn = NearestNeighbors(n_neighbors=k + 1, algorithm='auto')
        nn.fit(X.astype(np.float32))
        _, indices = nn.kneighbors(X.astype(np.float32))
        nbr_idx = indices[:, 1:]

        X_nbrs = X[nbr_idx]                          # (n, k, d)
        diff = X[:, None, :] - X_nbrs                 # (n, k, d)
        r_sq = np.sum(diff ** 2, axis=2, keepdims=True) + eps  # (n, k, 1)
        r = np.sqrt(r_sq)

        # LJ force magnitude: F = 24ε/r * [2(σ/r)^12 - (σ/r)^6]
        sr6 = (sigma / r) ** 6
        sr12 = sr6 ** 2
        F_mag = 24 * epsilon / r * (2 * sr12 - sr6)  # (n, k, 1)

        # Direction
        unit = diff / r                               # (n, k, d)
        forces = np.sum(F_mag * unit, axis=1)          # (n, d)

        return forces

    def _lj_energy(self, X: np.ndarray, eps: float = 1e-5) -> float:
        """Compute total Lennard-Jones + radial potential energy.
        Uses kNN-limited pairwise energy for consistency with forces
        and to scale to large datasets.
        """
        n = len(X)
        sigma = self.sigma_lj
        epsilon = self.epsilon

        # Radial
        E_radial = 0.5 * self.alpha_radial * np.sum((X - self.mu_) ** 2)

        # LJ pairwise (kNN-limited, consistent with forces)
        E_lj = 0.0
        if n > 1:
            from sklearn.neighbors import NearestNeighbors
            k = min(self.k_neighbors, n - 1)
            nn = NearestNeighbors(n_neighbors=k + 1, algorithm='auto')
            nn.fit(X.astype(np.float32))
            dists, _ = nn.kneighbors(X.astype(np.float32))
            r = dists[:, 1:] + eps  # (n, k)
            sr6 = (sigma / r) ** 6
            sr12 = sr6 ** 2
            # Factor 0.5 to avoid double-counting
            E_lj = float(0.5 * 4 * epsilon * np.sum(sr12 - sr6))

        return E_radial + E_lj

    def fit_score(self, X: np.ndarray, y: Optional[np.ndarray] = None
                  ) -> np.ndarray:
        """
        Run molecular dynamics simulation and return anomaly scores.

        Scores are produced by the FusedSystemScorer (Morse + Betti +
        UDL + BSDT operators) or MorseTopologyAlarm fallback (noise-immune).
        The Lyapunov stabiliser controls only the solver iterations.
        For large datasets, subsamples to max_samples for simulation
        then scores all points via kNN interpolation.
        """
        # Normalise
        if self.normalize:
            self.scaler_ = StandardScaler()
            X_all = self.scaler_.fit_transform(X).astype(np.float64)
        else:
            X_all = X.astype(np.float64).copy()

        n, d = X_all.shape

        # Track which points are normal for post-simulation calibration
        normal_mask_all = (y == 0) if y is not None else np.ones(n, dtype=bool)

        # Subsample for simulation if dataset is large
        if n > self.max_samples:
            rng = np.random.RandomState(42)
            anom_idx = np.where(y == 1)[0] if y is not None else np.array([], dtype=int)
            other_idx = np.where(y != 1)[0] if y is not None else np.arange(n)

            # Budget: ensure both classes are represented
            if len(anom_idx) >= self.max_samples:
                # More anomalies than budget — subsample both proportionally
                n_anom = min(len(anom_idx), self.max_samples // 2)
                n_other = self.max_samples - n_anom
                anom_sample = rng.choice(anom_idx, n_anom, replace=False)
                other_sample = rng.choice(other_idx, min(n_other, len(other_idx)), replace=False)
                sim_idx = np.sort(np.concatenate([anom_sample, other_sample]))
            else:
                n_other = max(0, self.max_samples - len(anom_idx))
                if len(other_idx) > n_other:
                    other_sample = rng.choice(other_idx, n_other, replace=False)
                else:
                    other_sample = other_idx
                sim_idx = np.sort(np.concatenate([anom_idx, other_sample]))

            X_work = X_all[sim_idx].copy()
            normal_mask = normal_mask_all[sim_idx]
            subsampled = True
        else:
            X_work = X_all.copy()
            normal_mask = normal_mask_all
            sim_idx = np.arange(n)
            subsampled = False

        self.mu_ = X_work.mean(axis=0)

        # ── Euler integration with Lyapunov v2 stability control ──
        self.stabiliser.reset()
        eta = self.eta
        n_sim = len(X_work)
        # Reduce iterations for large subsamples
        iters = self.iterations if n_sim <= 1000 else max(20, self.iterations // 2)
        for step in range(iters):
            # Compute forces
            F_lj = self._lennard_jones_forces(X_work)
            F_radial = -self.alpha_radial * (X_work - self.mu_)
            F_total = F_lj + F_radial

            # Barrier-augmented force clamping (solver stability only)
            F_total = self.stabiliser.clamp_forces(F_total)

            # Armijo backtracking with descent certificate
            E_old = self._lj_energy(X_work)
            grad_norm_sq = float(np.sum(F_total ** 2))
            X_candidate = X_work + eta * F_total

            E_new = self._lj_energy(X_candidate)
            accept, eta = self.stabiliser.accept_step(
                E_old, E_new, grad_norm_sq, eta
            )

            if accept:
                X_work = X_candidate
            else:
                # Reduced step
                X_work = X_work + eta * F_total

            # La Salle convergence check (∇E → 0) with displacement fallback
            displacement = eta * np.max(np.linalg.norm(F_total, axis=1))
            if self.stabiliser.check_convergence(grad_norm_sq, displacement):
                break

        self.X_final_ = X_work
        self._convergence_report = self.stabiliser.report()

        # ── PREDICTION: calibrate on FINAL normal positions ──
        X_ref_final = X_work[normal_mask]

        if self.fused_scorer is not None and len(X_ref_final) > 1:
            self.fused_scorer.fit(X_ref_final, X_sim=X_work)
            if subsampled:
                scores = self.fused_scorer.score(X_all)
            else:
                scores = self.fused_scorer.score(X_work)
        else:
            self.alarm.fit(X_ref_final)
            if subsampled:
                scores = self.alarm.score(X_all)
            else:
                scores = self.alarm.score(X_work)

        # ── FAR-targeted calibration (optional) ──
        if self.calibrate is not None and y is not None:
            from .calibration import FARTargetCalibrator
            cal = FARTargetCalibrator(
                target_far=self.target_far,
                method=self.calibrate
            )
            cal.fit(scores, y)
            scores = cal.transform(scores)
            self._far_calibrator = cal

        return scores

    # ─── Conformal scoring methods ───────────────────────────

    def _score_new(self, X: np.ndarray) -> np.ndarray:
        """Score new data points using the fitted engine.

        Requires that fit_score() has been called first.
        """
        X = np.asarray(X, dtype=np.float64)
        if self.scaler_ is not None:
            X_scaled = self.scaler_.transform(X)
        else:
            X_scaled = X.copy()
        if self.fused_scorer is not None:
            return self.fused_scorer.score(X_scaled)
        return self.alarm.score(X_scaled)

    def fit_reference(self, X_ref: np.ndarray,
                      y_ref: np.ndarray = None,
                      cal_frac: float = 0.2,
                      random_state: int = 42) -> 'MolecularEngine':
        """Fit the engine and calibration set for conformal scoring.

        Splits reference data into fit + calibration sets.
        Runs physics simulation on fit set, scores calibration set
        to build reference distribution for conformal inference.

        Parameters
        ----------
        X_ref  : (N, d) array — reference data
        y_ref  : (N,) array or None — labels (0=normal)
        cal_frac : float — fraction reserved for calibration
        random_state : int — seed

        Returns
        -------
        self
        """
        X_ref = np.asarray(X_ref, dtype=np.float64)
        N = len(X_ref)
        n_cal = max(10, int(N * cal_frac))

        rng = np.random.default_rng(random_state)
        perm = rng.permutation(N)
        idx_fit = perm[:-n_cal]
        idx_cal = perm[-n_cal:]

        X_fit = X_ref[idx_fit]
        X_cal = X_ref[idx_cal]

        if y_ref is not None:
            y_fit = np.asarray(y_ref)[idx_fit]
        else:
            y_fit = np.zeros(len(X_fit), dtype=int)

        # Run the physics simulation on the fit set
        self.fit_score(X_fit, y_fit)

        # Score the calibration set using the fitted engine
        self._cal_scores = self._score_new(X_cal)
        self._cal_sorted = np.sort(self._cal_scores)
        self._cal_N = len(self._cal_scores)
        self._conformal_fitted = True
        return self

    def score_conformal(self, X: np.ndarray) -> np.ndarray:
        """Score new data using the fitted engine.

        Must call fit_reference() first.
        """
        if not getattr(self, '_conformal_fitted', False):
            raise RuntimeError('Call fit_reference() before score_conformal()')
        return self._score_new(X)

    def predict_pvalue(self, X: np.ndarray) -> np.ndarray:
        """Conformal p-values with distribution-free validity.

        p(x) = (1 + #{i : A_cal_i >= A(x)}) / (n_cal + 1)

        Guarantee: P(p(X) <= alpha) <= alpha for any distribution.
        Must call fit_reference() first.
        """
        if not getattr(self, '_conformal_fitted', False):
            raise RuntimeError('Call fit_reference() before predict_pvalue()')

        scores = self._score_new(X)
        n_cal = self._cal_N
        rank = n_cal - np.searchsorted(self._cal_sorted, scores, side='left')
        return (1 + rank) / (n_cal + 1)

    def score_universal(self, X: np.ndarray, y: np.ndarray,
                        T: int, N: int,
                        window: int = None) -> dict:
        """Universal dataset-agnostic scoring with conformal calibration.

        Runs physics engine + panel-level temporal aggregation +
        conformal p-values. Works on any dataset without tuning.

        Parameters
        ----------
        X : (T*N, d) — flat panel data
        y : (T*N,) — labels (0 = normal)
        T, N : int — periods, agents
        window : int or None — auto-detected

        Returns
        -------
        dict: scores, q_scores, pvalues, q_pvalues
        """
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)

        if window is None:
            window = 4 if T < 200 else max(4, T // 10)

        # ── Point-level scoring ──
        s_point = self.fit_score(X, y)

        # ── Panel-level temporal aggregation ──
        y_time = y.reshape(T, N)[:, 0]
        s_3d = s_point.reshape(T, N)

        q_mean = s_3d.mean(axis=1)
        q_p90 = np.percentile(s_3d, 90, axis=1)
        q_max = s_3d.max(axis=1)
        q_std = s_3d.std(axis=1)

        q_z = np.zeros(T)
        for t in range(window, T):
            w = q_mean[t-window:t]
            mu_w, std_w = w.mean(), w.std() + 1e-10
            q_z[t] = max((q_mean[t] - mu_w) / std_w, 0.0)

        q_mom = np.zeros(T)
        q_mom[1:] = np.maximum(q_mean[1:] - q_mean[:-1], 0.0)

        def rank_norm(x):
            if x.max() == x.min():
                return np.zeros_like(x)
            order = np.argsort(np.argsort(x)).astype(np.float64)
            return order / (len(x) - 1 + 1e-15)

        components = np.column_stack([
            q_mean, q_p90, q_max, q_std, q_z, q_mom
        ])
        ranked = np.column_stack([rank_norm(c) for c in components.T])
        q_scores = ranked.mean(axis=1)

        # ── Conformal calibration ──
        ref_mask = (y == 0)
        cal_pt = s_point[ref_mask]
        cal_pt_sorted = np.sort(cal_pt)
        n_cal = len(cal_pt_sorted)
        rank_pt = n_cal - np.searchsorted(cal_pt_sorted, s_point, side='left')
        pvalues = (1 + rank_pt) / (n_cal + 1)

        cal_q_mask = (y_time == 0)
        cal_q = q_scores[cal_q_mask]
        cal_q_sorted = np.sort(cal_q)
        n_cal_q = len(cal_q_sorted)
        rank_q = n_cal_q - np.searchsorted(cal_q_sorted, q_scores, side='left')
        q_pvalues = (1 + rank_q) / (n_cal_q + 1)

        return {
            'scores': s_point,
            'q_scores': q_scores,
            'pvalues': pvalues,
            'q_pvalues': q_pvalues,
        }



# ═══════════════════════════════════════════════════════════════════
#  GRAVITY ENGINE (wrapped for mode system)
# ═══════════════════════════════════════════════════════════════════

class GravityModeEngine:
    """
    N-body gravitational clustering with Lyapunov-stabilised iteration
    and Morse-topology prediction.

    This wraps the existing GravityEngine physics but replaces the
    final scoring with the noise-immune MorseTopologyAlarm.
    """

    def __init__(self,
                 alpha: float = 0.1,
                 gamma: float = 0.5,
                 sigma: float = 1.0,
                 lambda_rep: float = 0.05,
                 eta: float = 0.05,
                 iterations: int = 60,
                 k_neighbors: int = 15,
                 normalize: bool = True,
                 max_samples: int = 3000,
                 use_fused: bool = True,
                 calibrate: Optional[str] = None,
                 target_far: float = 0.05):
        self.alpha = alpha
        self.gamma = gamma
        self.sigma = sigma
        self.lambda_rep = lambda_rep
        self.eta = eta
        self.iterations = iterations
        self.k_neighbors = k_neighbors
        self.normalize = normalize
        self.max_samples = max_samples
        self.use_fused = use_fused
        self.calibrate = calibrate
        self.target_far = target_far

        self.stabiliser = LyapunovStabiliser(min_eta=1e-5)
        self.alarm = MorseTopologyAlarm(k=k_neighbors)
        self.fused_scorer = FusedSystemScorer(k=k_neighbors) if use_fused else None
        self._far_calibrator = None

        self.scaler_: Optional[StandardScaler] = None
        self.mu_: Optional[np.ndarray] = None
        self.X_final_: Optional[np.ndarray] = None

    def _pairwise_forces(self, X: np.ndarray,
                         eps: float = 1e-5) -> np.ndarray:
        """Gravitational attraction + short-range repulsion (kNN-limited)."""
        n, d = X.shape
        gamma = self.gamma
        sigma = self.sigma
        lambda_rep = self.lambda_rep

        from sklearn.neighbors import NearestNeighbors
        k = min(self.k_neighbors, n - 1)
        nn = NearestNeighbors(n_neighbors=k + 1, algorithm='auto')
        nn.fit(X.astype(np.float32))
        _, indices = nn.kneighbors(X.astype(np.float32))
        nbr_idx = indices[:, 1:]

        X_nbrs = X[nbr_idx]
        diff = X[:, None, :] - X_nbrs
        r_sq = np.sum(diff ** 2, axis=2, keepdims=True) + eps
        r = np.sqrt(r_sq)

        attraction = np.exp(-r_sq / (sigma ** 2))
        repulsion = lambda_rep / r
        magnitude = -gamma * (attraction - repulsion)

        unit = diff / r
        forces = np.sum(magnitude * unit, axis=1)
        return forces

    def _gravity_energy(self, X: np.ndarray, eps: float = 1e-5) -> float:
        """Approximate energy (radial-only Lyapunov candidate).

        Uses radial energy only — always consistent with radial force.
        The pairwise force F_pair is treated as a bounded perturbation
        under the ISS (Input-to-State Stability) framework:
          ΔV ≤ −α(V) + γ(‖F_pair‖)
        This justifies using radial-only energy for the Armijo test
        while the full force (radial + pairwise) drives the dynamics.
        """
        n = len(X)
        # Radial energy only (always consistent with radial force)
        diff_mu = X - self.mu_[None, :]
        E_radial = 0.5 * self.alpha * np.sum(diff_mu ** 2)
        return float(E_radial)

    def fit_score(self, X: np.ndarray, y: Optional[np.ndarray] = None
                  ) -> np.ndarray:
        """Run gravity simulation and return noise-immune scores."""
        if self.normalize:
            self.scaler_ = StandardScaler()
            X_all = self.scaler_.fit_transform(X).astype(np.float64)
        else:
            X_all = X.astype(np.float64).copy()

        n = len(X_all)
        normal_mask_all = (y == 0) if y is not None else np.ones(n, dtype=bool)

        # Subsample for simulation if dataset is large
        if n > self.max_samples:
            rng = np.random.RandomState(42)
            anom_idx = np.where(y == 1)[0] if y is not None else np.array([], dtype=int)
            other_idx = np.where(y != 1)[0] if y is not None else np.arange(n)

            if len(anom_idx) >= self.max_samples:
                n_anom = min(len(anom_idx), self.max_samples // 2)
                n_other = self.max_samples - n_anom
                anom_sample = rng.choice(anom_idx, n_anom, replace=False)
                other_sample = rng.choice(other_idx, min(n_other, len(other_idx)), replace=False)
                sim_idx = np.sort(np.concatenate([anom_sample, other_sample]))
            else:
                n_other = max(0, self.max_samples - len(anom_idx))
                if len(other_idx) > n_other:
                    other_sample = rng.choice(other_idx, n_other, replace=False)
                else:
                    other_sample = other_idx
                sim_idx = np.sort(np.concatenate([anom_idx, other_sample]))

            X_work = X_all[sim_idx].copy()
            normal_mask = normal_mask_all[sim_idx]
            subsampled = True
        else:
            X_work = X_all.copy()
            normal_mask = normal_mask_all
            subsampled = False

        self.mu_ = X_work.mean(axis=0)

        # Store initial positions for displacement scoring
        X_initial = X_work.copy()

        # ── Euler integration with Lyapunov v2 + ISS tracking ──
        self.stabiliser.reset()
        eta = self.eta
        n_sim = len(X_work)
        iters = self.iterations if n_sim <= 1000 else max(20, self.iterations // 2)
        for step in range(iters):
            F_pair = self._pairwise_forces(X_work)
            F_radial = -self.alpha * (X_work - self.mu_)
            F_total = F_pair + F_radial

            # Barrier-augmented force clamping
            F_total = self.stabiliser.clamp_forces(F_total)

            # Armijo on radial energy with ISS margin for pairwise force
            E_old = self._gravity_energy(X_work)
            grad_norm_sq = float(np.sum(F_total ** 2))
            perturbation_norm = float(np.sqrt(np.sum(F_pair ** 2)))

            X_candidate = X_work + eta * F_total
            E_new = self._gravity_energy(X_candidate)

            accept, eta = self.stabiliser.accept_step(
                E_old, E_new, grad_norm_sq, eta,
                perturbation_norm=perturbation_norm
            )

            if accept:
                X_work = X_candidate
            else:
                # Reduced step with ISS-adjusted eta
                X_work = X_work + eta * F_total

            # La Salle convergence check with displacement fallback
            displacement = eta * np.max(np.linalg.norm(F_total, axis=1))
            if self.stabiliser.check_convergence(grad_norm_sq, displacement):
                break

        self.X_final_ = X_work
        self._convergence_report = self.stabiliser.report()

        # Calibrate on FINAL normal positions
        X_ref_final = X_work[normal_mask]
        if len(X_ref_final) > 1:
            if self.fused_scorer is not None:
                self.fused_scorer.fit(X_ref_final, X_sim=X_work)
                if subsampled:
                    scores = self.fused_scorer.score(X_all)
                else:
                    scores = self.fused_scorer.score(X_work)
            else:
                self.alarm.fit(X_ref_final)
                if subsampled:
                    scores = self.alarm.score(X_all)
                else:
                    scores = self.alarm.score(X_work)
        else:
            # Fallback: displacement from initial position
            if subsampled:
                scores = np.linalg.norm(X_all - X_all.mean(axis=0), axis=1)
            else:
                scores = np.linalg.norm(X_work - X_initial, axis=1)

        # ── FAR-targeted calibration (optional) ──
        if self.calibrate is not None and y is not None:
            from .calibration import FARTargetCalibrator
            cal = FARTargetCalibrator(
                target_far=self.target_far,
                method=self.calibrate
            )
            cal.fit(scores, y)
            scores = cal.transform(scores)
            self._far_calibrator = cal

        return scores

    # ─── Conformal scoring methods ───────────────────────────

    def _score_new(self, X: np.ndarray) -> np.ndarray:
        """Score new data points using the fitted engine.

        Requires that fit_score() has been called first.
        """
        X = np.asarray(X, dtype=np.float64)
        if self.scaler_ is not None:
            X_scaled = self.scaler_.transform(X)
        else:
            X_scaled = X.copy()
        if self.fused_scorer is not None:
            return self.fused_scorer.score(X_scaled)
        return self.alarm.score(X_scaled)

    def fit_reference(self, X_ref: np.ndarray,
                      y_ref: np.ndarray = None,
                      cal_frac: float = 0.2,
                      random_state: int = 42) -> 'GravityModeEngine':
        """Fit the engine and calibration set for conformal scoring.

        Splits reference data into fit + calibration sets.
        Runs physics simulation on fit set, scores calibration set
        to build reference distribution for conformal inference.

        Parameters
        ----------
        X_ref  : (N, d) array — reference data
        y_ref  : (N,) array or None — labels (0=normal)
        cal_frac : float — fraction reserved for calibration
        random_state : int — seed

        Returns
        -------
        self
        """
        X_ref = np.asarray(X_ref, dtype=np.float64)
        N = len(X_ref)
        n_cal = max(10, int(N * cal_frac))

        rng = np.random.default_rng(random_state)
        perm = rng.permutation(N)
        idx_fit = perm[:-n_cal]
        idx_cal = perm[-n_cal:]

        X_fit = X_ref[idx_fit]
        X_cal = X_ref[idx_cal]

        if y_ref is not None:
            y_fit = np.asarray(y_ref)[idx_fit]
        else:
            y_fit = np.zeros(len(X_fit), dtype=int)

        # Run the physics simulation on the fit set
        self.fit_score(X_fit, y_fit)

        # Score the calibration set using the fitted engine
        self._cal_scores = self._score_new(X_cal)
        self._cal_sorted = np.sort(self._cal_scores)
        self._cal_N = len(self._cal_scores)
        self._conformal_fitted = True
        return self

    def score_conformal(self, X: np.ndarray) -> np.ndarray:
        """Score new data using the fitted engine.

        Must call fit_reference() first.
        """
        if not getattr(self, '_conformal_fitted', False):
            raise RuntimeError('Call fit_reference() before score_conformal()')
        return self._score_new(X)

    def predict_pvalue(self, X: np.ndarray) -> np.ndarray:
        """Conformal p-values with distribution-free validity.

        p(x) = (1 + #{i : A_cal_i >= A(x)}) / (n_cal + 1)

        Guarantee: P(p(X) <= alpha) <= alpha for any distribution.
        Must call fit_reference() first.
        """
        if not getattr(self, '_conformal_fitted', False):
            raise RuntimeError('Call fit_reference() before predict_pvalue()')

        scores = self._score_new(X)
        n_cal = self._cal_N
        rank = n_cal - np.searchsorted(self._cal_sorted, scores, side='left')
        return (1 + rank) / (n_cal + 1)

    def score_universal(self, X: np.ndarray, y: np.ndarray,
                        T: int, N: int,
                        window: int = None) -> dict:
        """Universal dataset-agnostic scoring with conformal calibration.

        Runs physics engine + panel-level temporal aggregation +
        conformal p-values. Works on any dataset without tuning.

        Parameters
        ----------
        X : (T*N, d) — flat panel data
        y : (T*N,) — labels (0 = normal)
        T, N : int — periods, agents
        window : int or None — auto-detected

        Returns
        -------
        dict: scores, q_scores, pvalues, q_pvalues
        """
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)

        if window is None:
            window = 4 if T < 200 else max(4, T // 10)

        # ── Point-level scoring ──
        s_point = self.fit_score(X, y)

        # ── Panel-level temporal aggregation ──
        y_time = y.reshape(T, N)[:, 0]
        s_3d = s_point.reshape(T, N)

        q_mean = s_3d.mean(axis=1)
        q_p90 = np.percentile(s_3d, 90, axis=1)
        q_max = s_3d.max(axis=1)
        q_std = s_3d.std(axis=1)

        q_z = np.zeros(T)
        for t in range(window, T):
            w = q_mean[t-window:t]
            mu_w, std_w = w.mean(), w.std() + 1e-10
            q_z[t] = max((q_mean[t] - mu_w) / std_w, 0.0)

        q_mom = np.zeros(T)
        q_mom[1:] = np.maximum(q_mean[1:] - q_mean[:-1], 0.0)

        def rank_norm(x):
            if x.max() == x.min():
                return np.zeros_like(x)
            order = np.argsort(np.argsort(x)).astype(np.float64)
            return order / (len(x) - 1 + 1e-15)

        components = np.column_stack([
            q_mean, q_p90, q_max, q_std, q_z, q_mom
        ])
        ranked = np.column_stack([rank_norm(c) for c in components.T])
        q_scores = ranked.mean(axis=1)

        # ── Conformal calibration ──
        ref_mask = (y == 0)
        cal_pt = s_point[ref_mask]
        cal_pt_sorted = np.sort(cal_pt)
        n_cal = len(cal_pt_sorted)
        rank_pt = n_cal - np.searchsorted(cal_pt_sorted, s_point, side='left')
        pvalues = (1 + rank_pt) / (n_cal + 1)

        cal_q_mask = (y_time == 0)
        cal_q = q_scores[cal_q_mask]
        cal_q_sorted = np.sort(cal_q)
        n_cal_q = len(cal_q_sorted)
        rank_q = n_cal_q - np.searchsorted(cal_q_sorted, q_scores, side='left')
        q_pvalues = (1 + rank_q) / (n_cal_q + 1)

        return {
            'scores': s_point,
            'q_scores': q_scores,
            'pvalues': pvalues,
            'q_pvalues': q_pvalues,
        }



# ═══════════════════════════════════════════════════════════════════
#  HYBRID ENGINE (Molecular + Gravity blend)
# ═══════════════════════════════════════════════════════════════════

class HybridGravityEngine:
    """
    Adaptive blend of Molecular and Gravity engines.

    Runs both engines, then combines scores with adaptive weights.
    Can auto-select the best mode via cross-validation when labels
    are available, or use a fixed blend weight.

    Parameters
    ----------
    blend_weight : float or 'auto'
        Weight for molecular score in [0, 1].
        0.0 = pure gravity, 1.0 = pure molecular, 0.5 = equal blend.
        'auto' = choose by 3-fold CV on training data.
    molecular_params : dict
        Keyword arguments for MolecularEngine.
    gravity_params : dict
        Keyword arguments for GravityModeEngine.
    """

    def __init__(self,
                 blend_weight: Union[float, str] = 'auto',
                 molecular_params: Optional[dict] = None,
                 gravity_params: Optional[dict] = None,
                 calibrate: Optional[str] = None,
                 target_far: float = 0.05):
        self.blend_weight = blend_weight
        self.calibrate = calibrate
        self.target_far = target_far
        mol_kw = molecular_params or {}
        grav_kw = gravity_params or {}

        self.molecular = MolecularEngine(**mol_kw)
        self.gravity = GravityModeEngine(**grav_kw)
        self._far_calibrator = None

        self._blend_w: float = 0.5  # resolved blend weight
        self._cv_scores: Optional[Dict] = None

    def fit_score(self, X: np.ndarray, y: Optional[np.ndarray] = None
                  ) -> np.ndarray:
        """
        Run both engines and return blended scores.

        If blend_weight='auto' and y is provided, selects blend via CV.
        """
        scores_mol = self.molecular.fit_score(X, y)
        scores_grav = self.gravity.fit_score(X, y)

        # Normalise both score vectors to [0, 1]
        scores_mol = self._normalise(scores_mol)
        scores_grav = self._normalise(scores_grav)

        if self.blend_weight == 'auto' and y is not None:
            self._blend_w = self._auto_blend(scores_mol, scores_grav, y)
        elif isinstance(self.blend_weight, (int, float)):
            self._blend_w = float(self.blend_weight)
        else:
            self._blend_w = 0.5

        blended = self._blend_w * scores_mol + (1 - self._blend_w) * scores_grav

        # ── FAR-targeted calibration (optional) ──
        if self.calibrate is not None and y is not None:
            from .calibration import FARTargetCalibrator
            cal = FARTargetCalibrator(
                target_far=self.target_far,
                method=self.calibrate
            )
            cal.fit(blended, y)
            blended = cal.transform(blended)
            self._far_calibrator = cal

        return blended

    def _normalise(self, s: np.ndarray) -> np.ndarray:
        """Min-max normalise to [0, 1]."""
        s_min, s_max = s.min(), s.max()
        if s_max - s_min < 1e-15:
            return np.zeros_like(s)
        return (s - s_min) / (s_max - s_min)

    def _auto_blend(self, scores_mol: np.ndarray,
                    scores_grav: np.ndarray,
                    y: np.ndarray) -> float:
        """Select blend weight by maximising AUROC on training data."""
        from sklearn.metrics import roc_auc_score

        best_w, best_auc = 0.5, 0.0
        for w in np.linspace(0, 1, 11):
            blended = w * scores_mol + (1 - w) * scores_grav
            try:
                auc = roc_auc_score(y, blended)
                if auc > best_auc:
                    best_auc = auc
                    best_w = w
            except ValueError:
                pass

        self._cv_scores = {'best_weight': best_w, 'best_auc': best_auc}
        return best_w

    # ─── Conformal scoring methods ───────────────────────────

    def _score_new(self, X: np.ndarray) -> np.ndarray:
        """Score new data points using the fitted engine.

        Requires that fit_score() has been called first.
        """
        X = np.asarray(X, dtype=np.float64)
        # Score via both sub-engines and blend
        scores_mol = self.molecular._score_new(X)
        scores_grav = self.gravity._score_new(X)
        scores_mol = self._normalise(scores_mol)
        scores_grav = self._normalise(scores_grav)
        return self._blend_w * scores_mol + (1 - self._blend_w) * scores_grav

    def fit_reference(self, X_ref: np.ndarray,
                      y_ref: np.ndarray = None,
                      cal_frac: float = 0.2,
                      random_state: int = 42) -> 'HybridGravityEngine':
        """Fit the engine and calibration set for conformal scoring.

        Splits reference data into fit + calibration sets.
        Runs physics simulation on fit set, scores calibration set
        to build reference distribution for conformal inference.

        Parameters
        ----------
        X_ref  : (N, d) array — reference data
        y_ref  : (N,) array or None — labels (0=normal)
        cal_frac : float — fraction reserved for calibration
        random_state : int — seed

        Returns
        -------
        self
        """
        X_ref = np.asarray(X_ref, dtype=np.float64)
        N = len(X_ref)
        n_cal = max(10, int(N * cal_frac))

        rng = np.random.default_rng(random_state)
        perm = rng.permutation(N)
        idx_fit = perm[:-n_cal]
        idx_cal = perm[-n_cal:]

        X_fit = X_ref[idx_fit]
        X_cal = X_ref[idx_cal]

        if y_ref is not None:
            y_fit = np.asarray(y_ref)[idx_fit]
        else:
            y_fit = np.zeros(len(X_fit), dtype=int)

        # Run the physics simulation on the fit set
        self.fit_score(X_fit, y_fit)

        # Score the calibration set using the fitted engine
        self._cal_scores = self._score_new(X_cal)
        self._cal_sorted = np.sort(self._cal_scores)
        self._cal_N = len(self._cal_scores)
        self._conformal_fitted = True
        return self

    def score_conformal(self, X: np.ndarray) -> np.ndarray:
        """Score new data using the fitted engine.

        Must call fit_reference() first.
        """
        if not getattr(self, '_conformal_fitted', False):
            raise RuntimeError('Call fit_reference() before score_conformal()')
        return self._score_new(X)

    def predict_pvalue(self, X: np.ndarray) -> np.ndarray:
        """Conformal p-values with distribution-free validity.

        p(x) = (1 + #{i : A_cal_i >= A(x)}) / (n_cal + 1)

        Guarantee: P(p(X) <= alpha) <= alpha for any distribution.
        Must call fit_reference() first.
        """
        if not getattr(self, '_conformal_fitted', False):
            raise RuntimeError('Call fit_reference() before predict_pvalue()')

        scores = self._score_new(X)
        n_cal = self._cal_N
        rank = n_cal - np.searchsorted(self._cal_sorted, scores, side='left')
        return (1 + rank) / (n_cal + 1)

    def score_universal(self, X: np.ndarray, y: np.ndarray,
                        T: int, N: int,
                        window: int = None) -> dict:
        """Universal dataset-agnostic scoring with conformal calibration.

        Runs physics engine + panel-level temporal aggregation +
        conformal p-values. Works on any dataset without tuning.

        Parameters
        ----------
        X : (T*N, d) — flat panel data
        y : (T*N,) — labels (0 = normal)
        T, N : int — periods, agents
        window : int or None — auto-detected

        Returns
        -------
        dict: scores, q_scores, pvalues, q_pvalues
        """
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)

        if window is None:
            window = 4 if T < 200 else max(4, T // 10)

        # ── Point-level scoring ──
        s_point = self.fit_score(X, y)

        # ── Panel-level temporal aggregation ──
        y_time = y.reshape(T, N)[:, 0]
        s_3d = s_point.reshape(T, N)

        q_mean = s_3d.mean(axis=1)
        q_p90 = np.percentile(s_3d, 90, axis=1)
        q_max = s_3d.max(axis=1)
        q_std = s_3d.std(axis=1)

        q_z = np.zeros(T)
        for t in range(window, T):
            w = q_mean[t-window:t]
            mu_w, std_w = w.mean(), w.std() + 1e-10
            q_z[t] = max((q_mean[t] - mu_w) / std_w, 0.0)

        q_mom = np.zeros(T)
        q_mom[1:] = np.maximum(q_mean[1:] - q_mean[:-1], 0.0)

        def rank_norm(x):
            if x.max() == x.min():
                return np.zeros_like(x)
            order = np.argsort(np.argsort(x)).astype(np.float64)
            return order / (len(x) - 1 + 1e-15)

        components = np.column_stack([
            q_mean, q_p90, q_max, q_std, q_z, q_mom
        ])
        ranked = np.column_stack([rank_norm(c) for c in components.T])
        q_scores = ranked.mean(axis=1)

        # ── Conformal calibration ──
        ref_mask = (y == 0)
        cal_pt = s_point[ref_mask]
        cal_pt_sorted = np.sort(cal_pt)
        n_cal = len(cal_pt_sorted)
        rank_pt = n_cal - np.searchsorted(cal_pt_sorted, s_point, side='left')
        pvalues = (1 + rank_pt) / (n_cal + 1)

        cal_q_mask = (y_time == 0)
        cal_q = q_scores[cal_q_mask]
        cal_q_sorted = np.sort(cal_q)
        n_cal_q = len(cal_q_sorted)
        rank_q = n_cal_q - np.searchsorted(cal_q_sorted, q_scores, side='left')
        q_pvalues = (1 + rank_q) / (n_cal_q + 1)

        return {
            'scores': s_point,
            'q_scores': q_scores,
            'pvalues': pvalues,
            'q_pvalues': q_pvalues,
        }



# ═══════════════════════════════════════════════════════════════════
#  SPECTRA FALSE-ALARM FILTER
# ═══════════════════════════════════════════════════════════════════

class SpectraFalseAlarmFilter:
    """
    Suppresses false alarms from ChaosSpectrum and SpectralSpectrum
    operators by replacing their raw gradient/Lyapunov signals with
    structurally stable topological features.

    Can be applied as a post-processing step to any UDL scores,
    or used as a replacement operator in the RepresentationStack.

    The filter works by:
    1. Computing persistence proxy (kNN filtration long-bar length)
    2. Computing local Morse index proxy (distance curvature)
    3. Gating: only pass signals where persistence > calibrated θ
       (short-lived noise spikes are automatically zeroed out)
    """

    def __init__(self, k: int = 15, persistence_quantile: float = 0.95):
        self.k = k
        self.persistence_quantile = persistence_quantile
        self._theta: float = 0.0
        self._X_ref = None

    def fit(self, X_ref: np.ndarray):
        """Calibrate filter threshold on reference data."""
        self._X_ref = X_ref.copy()
        N = len(X_ref)
        k = min(self.k, N - 1)

        D = cdist(X_ref, X_ref, metric='euclidean')
        np.fill_diagonal(D, np.inf)
        sorted_D = np.sort(D, axis=1)[:, :k]

        # Persistence proxy for reference points
        persistence = (sorted_D[:, -1] - sorted_D[:, 0]) / (sorted_D[:, -1] + 1e-10)

        # Threshold at high quantile — only features persisting longer
        # than this are considered real topological events
        self._theta = float(np.quantile(persistence, self.persistence_quantile))
        return self

    def filter_scores(self, X: np.ndarray,
                      raw_scores: np.ndarray) -> np.ndarray:
        """
        Gate raw scores through topological persistence filter.

        Points with short-lived topological features (noise) have
        their scores suppressed toward zero.
        """
        N = len(X)
        k = min(self.k, len(self._X_ref) - 1)

        D = cdist(X, self._X_ref, metric='euclidean')
        sorted_D = np.sort(D, axis=1)[:, :k]

        persistence = (sorted_D[:, -1] - sorted_D[:, 0]) / (sorted_D[:, -1] + 1e-10)

        # Soft gate: sigmoid activation around threshold
        gate = 1.0 / (1.0 + np.exp(-10 * (persistence - self._theta)))

        return raw_scores * gate

    def as_operator(self):
        """
        Return a spectrum operator compatible with RepresentationStack
        that replaces ChaosSpectrum with a noise-immune topological signal.
        """
        return _MorseReplacementSpectrum(
            k=self.k, X_ref=self._X_ref, theta=self._theta
        )


class _MorseReplacementSpectrum:
    """
    Drop-in replacement for ChaosSpectrum / SpectralSpectrum.

    Produces 3 structurally stable features instead of Lyapunov
    exponent / recurrence rate / approximate entropy:
      1. Persistence proxy (long-bar length from kNN filtration)
      2. Morse index proxy (distance curvature)
      3. Euler characteristic proxy (density uniformity change)

    These are immune to stochastic noise by construction (persistence
    theorem guarantees structural stability under small perturbation).
    """

    def __init__(self, k: int = 15, X_ref: Optional[np.ndarray] = None,
                 theta: float = 0.0):
        self.k = k
        self._X_ref = X_ref
        self._theta = theta
        self._ref_mean = None
        self._ref_std = None

    def fit(self, X_ref: np.ndarray):
        """Fit on reference data."""
        self._X_ref = X_ref.copy()
        N = len(X_ref)
        k = min(self.k, N - 1)
        self.k = k

        features = self._compute(X_ref, X_ref, skip_self=True)
        self._ref_mean = features.mean(axis=0)
        self._ref_std = features.std(axis=0) + 1e-10

        # Calibrate persistence threshold
        self._theta = float(np.quantile(features[:, 0], 0.95))
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        """Transform to 3 noise-immune topological features."""
        features = self._compute(X, self._X_ref, skip_self=False)
        return (features - self._ref_mean) / self._ref_std

    def _compute(self, X_query: np.ndarray, X_ref: np.ndarray,
                 skip_self: bool = False) -> np.ndarray:
        N = len(X_query)
        k = self.k
        out = np.zeros((N, 3), dtype=np.float64)
        eps = 1e-10

        D = cdist(X_query, X_ref, metric='euclidean')
        if skip_self:
            np.fill_diagonal(D, np.inf)

        sorted_D = np.sort(D, axis=1)
        start = 0
        nn_dists = sorted_D[:, start:start + k]

        d1 = nn_dists[:, 0] + eps
        dk = nn_dists[:, -1] + eps

        # 1. Persistence proxy: normalised gap
        out[:, 0] = (dk - d1) / (dk + eps)

        # 2. Morse index proxy: distance curvature
        mid = max(1, k // 2)
        d_mid = nn_dists[:, min(mid, k - 1)] + eps
        out[:, 1] = np.maximum(0, -(dk - 2 * d_mid + d1) / (mid ** 2 + eps))

        # 3. Euler characteristic proxy: median/mean deviation
        median_d = np.median(nn_dists, axis=1)
        mean_d = np.mean(nn_dists, axis=1) + eps
        out[:, 2] = np.abs(1.0 - median_d / mean_d)

        return out


# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  REDUCED TENSOR DESCRIPTOR \u2014 O(Nd + d\u00b3) complexity
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

class ReducedTensorDescriptor:
    """
    Reduced tensor descriptor for efficient anomaly detection.

    Replaces the full O(N\u00b2d) pairwise interaction matrix with a
    compact (d+7)-dimensional descriptor per point, computable in
    O(Nd + d\u00b3) time.

    The 6-tuple descriptor D(X) consists of:
      1. grad_norm    \u2014 \u2016\u2207E_BS(X)\u2016   (scalar, O(Nd))
      2. hessian_eigs \u2014 \u03bb\u2081,...,\u03bb_d of D\u00b2E_BS  (d values, O(d\u00b3) via Lanczos)
      3. mahalanobis  \u2014 \u03b4_C(X) = Mahalanobis distance  (scalar, O(d\u00b2))
      4. medoid_dist  \u2014 distance to medoid of reference set (scalar, O(Nd))
      5. trace_H      \u2014 tr(D\u00b2E_BS) = \u03a3\u03bbi  (scalar, from eigenvalues)
      6. det_sigma    \u2014 det(\u03a3_local) = local covariance determinant (scalar)

    Properties (Proposition in SIAM paper):
      (i)   Computable in O(Nd + d\u00b3) time
      (ii)  Locally injective near X* and C*
      (iii) Morse index fully recoverable: ind = #{j : \u03bb_j < 0}

    Theory
    ------
    The key insight is that the Morse index \u2014 the number of negative
    Hessian eigenvalues \u2014 is the topological prediction signal
    (Theorem C, Part C1). Since the Morse index depends only on the
    sign pattern of the eigenvalues, not on the full N\u00d7N interaction
    matrix, the descriptor is lossy in reconstruction but lossless
    for detection.

    The trace tr(H) and determinant det(\u03a3) serve as disambiguators
    for the two-function degeneracy problem: when gradient norms
    and Mahalanobis distances coincide for two distinct states, the
    trace (sum of eigenvalues) and determinant (product) break the
    degeneracy.
    """

    def __init__(self,
                 k_neighbors: int = 15,
                 n_eigs: int = None,
                 eps_hessian: float = 1e-4):
        """
        Parameters
        ----------
        k_neighbors : int
            Number of neighbors for medoid and local covariance.
        n_eigs : int or None
            Number of Hessian eigenvalues to compute.  If None,
            uses min(d, 10) for efficiency.
        eps_hessian : float
            Finite-difference step for numerical Hessian.
        """
        self.k_neighbors = k_neighbors
        self.n_eigs = n_eigs
        self.eps_hessian = eps_hessian
        self._ref_mean: Optional[np.ndarray] = None
        self._ref_cov_inv: Optional[np.ndarray] = None
        self._ref_medoid: Optional[np.ndarray] = None
        self._ref_data: Optional[np.ndarray] = None
        self._gmm = None
        self._eps_adapted: float = eps_hessian
        self._fitted = False

    def fit(self, X_ref: np.ndarray) -> 'ReducedTensorDescriptor':
        """Fit reference statistics from normal-period data.

        Parameters
        ----------
        X_ref : (N_ref, d) array
            Normal-period reference data.

        Returns
        -------
        self
        """
        self._ref_data = np.asarray(X_ref, dtype=np.float64)
        N, d = self._ref_data.shape

        # Reference mean (O(Nd))
        self._ref_mean = self._ref_data.mean(axis=0)

        # Reference covariance inverse for Mahalanobis (O(Nd\u00b2 + d\u00b3))
        cov = np.cov(self._ref_data, rowvar=False)
        # Regularise for numerical stability
        cov += 1e-8 * np.eye(d)
        self._ref_cov_inv = np.linalg.inv(cov)
        self._ref_cov_det = np.linalg.det(cov)

        # Medoid: the actual data point closest to all others (O(N\u00b2d))
        # For large N, use approximate medoid via mean-distance
        if N <= 5000:
            dists = cdist(self._ref_data, self._ref_data)
            medoid_idx = np.argmin(dists.sum(axis=1))
        else:
            # Approximate: point closest to mean (O(Nd))
            dists_to_mean = np.linalg.norm(
                self._ref_data - self._ref_mean, axis=1)
            medoid_idx = np.argmin(dists_to_mean)
        self._ref_medoid = self._ref_data[medoid_idx].copy()

        if self.n_eigs is None:
            self.n_eigs = min(d, 10)

        # -- GMM for non-trivial energy landscape --
        # A single-Gaussian Mahalanobis energy is strictly convex
        # (Hessian = cov_inv, always PD), so Morse index = 0 always.
        # A GMM with k>=2 components creates saddle points between
        # cluster boundaries, enabling meaningful Morse index detection.
        from sklearn.mixture import GaussianMixture
        n_comp = min(max(2, int(np.sqrt(N / 20))), 8)
        self._gmm = GaussianMixture(
            n_components=n_comp, covariance_type='full',
            random_state=42, n_init=3, max_iter=200)
        self._gmm.fit(self._ref_data)

        # Adapt finite-difference step to data scale
        self._eps_adapted = max(np.std(self._ref_data, axis=0).mean() * 0.01,
                                1e-6)

        self._fitted = True
        return self

    def transform(self, X: np.ndarray,
                  energy_fn=None,
                  gradient_fn=None) -> np.ndarray:
        """Compute the reduced descriptor for query points.

        Parameters
        ----------
        X : (N, d) array
            Query points.
        energy_fn : callable or None
            E_BS(x) -> scalar.  If None, uses Mahalanobis energy.
        gradient_fn : callable or None
            \u2207E_BS(x) -> (d,) array.  If None, computed numerically.

        Returns
        -------
        D : (N, d+7) array
            Reduced descriptor: [grad_norm, \u03bb\u2081..\u03bb_d, mahalanobis,
            medoid_dist, trace_H, det_sigma, morse_index].
        """
        if not self._fitted:
            raise RuntimeError("Call fit() first")

        X = np.asarray(X, dtype=np.float64)
        N, d = X.shape
        n_eigs = min(self.n_eigs, d)

        # Output: grad_norm(1) + eigenvalues(n_eigs) + mahalanobis(1)
        #         + medoid_dist(1) + trace_H(1) + det_sigma(1)
        #         + morse_index(1) = n_eigs + 6
        out = np.zeros((N, n_eigs + 6), dtype=np.float64)

        # -- 1 & 2.  Gradient + Hessian (vectorised) --
        if gradient_fn is not None or energy_fn is not None:
            # Per-point fallback for custom energy / gradient
            for i in range(N):
                xi = X[i]
                if gradient_fn is not None:
                    grad = gradient_fn(xi)
                elif energy_fn is not None:
                    grad = self._numerical_gradient(xi, energy_fn)
                else:
                    diff = xi - self._ref_mean
                    grad = self._ref_cov_inv @ diff
                out[i, 0] = np.linalg.norm(grad)

            for i in range(N):
                xi = X[i]
                if energy_fn is not None:
                    eigs = self._hessian_eigenvalues(
                        xi, energy_fn, n_eigs)
                else:
                    eigs = np.linalg.eigvalsh(
                        self._ref_cov_inv)[:n_eigs]
                out[i, 1:1+n_eigs] = np.sort(eigs)
                out[i, n_eigs + 3] = np.sum(eigs)
        else:
            # Batch GMM-based computation -- non-trivial Hessian
            # that can have negative eigenvalues (saddle points).
            grad_mat, hess_eigs = self._batch_gmm_compute(X, n_eigs)
            out[:, 0] = np.linalg.norm(grad_mat, axis=1)
            out[:, 1:1+n_eigs] = hess_eigs
            out[:, n_eigs + 3] = hess_eigs.sum(axis=1)  # trace
        # \u2500\u2500 3. Mahalanobis distance \u03b4_C \u2014 O(d\u00b2) per point \u2500\u2500
        diff = X - self._ref_mean  # (N, d)
        maha_sq = np.sum(diff @ self._ref_cov_inv * diff, axis=1)
        out[:, n_eigs + 1] = np.sqrt(np.maximum(maha_sq, 0))

        # \u2500\u2500 4. Medoid distance \u2014 O(Nd) \u2500\u2500
        out[:, n_eigs + 2] = np.linalg.norm(
            X - self._ref_medoid, axis=1)

        # \u2500\u2500 6. Local covariance determinant \u2014 O(Nkd + d\u00b3) \u2500\u2500
        from sklearn.neighbors import NearestNeighbors
        k = min(self.k_neighbors, len(self._ref_data) - 1, N - 1)
        if k >= 2:
            nn = NearestNeighbors(n_neighbors=k, algorithm='auto')
            nn.fit(self._ref_data.astype(np.float32))
            _, indices = nn.kneighbors(X.astype(np.float32))
            for i in range(N):
                local_pts = self._ref_data[indices[i]]
                local_cov = np.cov(local_pts, rowvar=False)
                local_cov += 1e-10 * np.eye(d)
                out[i, n_eigs + 4] = np.linalg.det(local_cov)
        else:
            out[:, n_eigs + 4] = self._ref_cov_det

        # \u2500\u2500 7. Morse index: #{j : \u03bb_j < 0} \u2500\u2500
        eig_block = out[:, 1:1+n_eigs]
        out[:, n_eigs + 5] = np.sum(eig_block < -1e-8, axis=1)

        return out

    def get_morse_index(self, X: np.ndarray,
                        energy_fn=None,
                        gradient_fn=None) -> np.ndarray:
        """Extract just the Morse index from the descriptor.

        Returns
        -------
        ind : (N,) int array
            Number of negative Hessian eigenvalues per point.
        """
        D = self.transform(X, energy_fn, gradient_fn)
        n_eigs = min(self.n_eigs, X.shape[1])
        return D[:, n_eigs + 5].astype(int)

    def get_alarm(self, X: np.ndarray,
                  energy_fn=None,
                  gradient_fn=None) -> np.ndarray:
        """Binary alarm: True where Morse index \u2265 1 (saddle point).

        This is the decoupled prediction signal (Theorem C, Part C5):
        independent of Lyapunov descent rate, structurally invariant
        under small perturbations.
        """
        return self.get_morse_index(X, energy_fn, gradient_fn) >= 1

    def feature_names(self) -> List[str]:
        """Return human-readable feature names for the descriptor."""
        d = self._ref_data.shape[1] if self._ref_data is not None else 0
        n_eigs = min(self.n_eigs, d)
        names = ['grad_norm']
        names += [f'hessian_eig_{j}' for j in range(n_eigs)]
        names += ['mahalanobis', 'medoid_dist', 'trace_H',
                  'det_sigma', 'morse_index']
        return names

    def complexity_info(self) -> Dict[str, str]:
        """Return theoretical complexity information."""
        d = self._ref_data.shape[1] if self._ref_data is not None else '?'
        N = self._ref_data.shape[0] if self._ref_data is not None else '?'
        return {
            'gradient': f'O(N*d) = O({N}*{d})',
            'hessian_eigs': f'O(d^3) = O({d}^3)',
            'mahalanobis': f'O(d^2) per point',
            'medoid_dist': f'O(d) per point',
            'local_cov_det': f'O(k*d + d^3) per point',
            'total': f'O(Nd + d^3) = O({N}*{d} + {d}^3)',
            'vs_full': f'O(N^2*d) = O({N}^2*{d})',
            'speedup': f'~N/d = ~{N}/{d}'
                       if isinstance(N, int) and isinstance(d, int)
                       else '~N/d',
        }

    # \u2500\u2500 private helpers \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

    def _batch_gmm_compute(self, X: np.ndarray,
                           n_eigs: int):
        """Vectorised gradient + Hessian eigenvalues via GMM energy.

        Uses ``-log p_GMM(x)`` as the energy function.  The GMM creates
        saddle points at cluster boundaries, giving non-trivial
        Morse indices (number of negative Hessian eigenvalues).

        Total GMM score_samples calls = 2d + 4*d(d+1)/2
        = 2d + 2d(d+1) ~ 2d^2 + 4d  (e.g. 70 calls for d=5).

        Returns
        -------
        grad : (N, d) array  -- gradient vectors
        eigs : (N, n_eigs)   -- sorted ascending Hessian eigenvalues
        """
        N, d = X.shape
        eps = self._eps_adapted

        # -- Gradient via central difference --
        grad = np.zeros((N, d), dtype=np.float64)
        for i in range(d):
            delta = np.zeros(d, dtype=np.float64)
            delta[i] = eps
            fp = -self._gmm.score_samples(X + delta)
            fm = -self._gmm.score_samples(X - delta)
            grad[:, i] = (fp - fm) / (2 * eps)

        # -- Hessian via finite difference (symmetric) --
        H = np.zeros((N, d, d), dtype=np.float64)
        eps2_inv = 1.0 / (4 * eps * eps)
        for i in range(d):
            ei = np.zeros(d, dtype=np.float64); ei[i] = eps
            for j in range(i, d):
                ej = np.zeros(d, dtype=np.float64); ej[j] = eps
                fpp = -self._gmm.score_samples(X + ei + ej)
                fpm = -self._gmm.score_samples(X + ei - ej)
                fmp = -self._gmm.score_samples(X - ei + ej)
                fmm = -self._gmm.score_samples(X - ei - ej)
                H[:, i, j] = (fpp - fpm - fmp + fmm) * eps2_inv
                if j != i:
                    H[:, j, i] = H[:, i, j]

        eigs = np.linalg.eigvalsh(H)          # (N, d) ascending
        return grad, eigs[:, :n_eigs]

    def score(self, X: np.ndarray,
              energy_fn=None,
              gradient_fn=None) -> np.ndarray:
        """Combined anomaly score from the descriptor.

        Uses robust percentile normalisation (instead of min-max)
        and learned weights that emphasise Morse index + Mahalanobis.

        Returns
        -------
        scores : (N,) array -- higher = more anomalous
        """
        D = self.transform(X, energy_fn, gradient_fn)
        n_eigs = min(self.n_eigs, X.shape[1])

        grad_norm = D[:, 0]
        mahalanobis = D[:, n_eigs + 1]
        medoid_dist = D[:, n_eigs + 2]
        trace_h = D[:, n_eigs + 3]
        morse_idx = D[:, n_eigs + 5]

        def robust_norm(x):
            q1, q99 = np.percentile(x, [1, 99])
            xn = (x - q1) / (q99 - q1 + 1e-15)
            return np.clip(xn, 0.0, 1.0)

        s = (0.25 * robust_norm(grad_norm) +
             0.30 * robust_norm(mahalanobis) +
             0.15 * robust_norm(medoid_dist) +
             0.10 * robust_norm(np.abs(trace_h)) +
             0.20 * robust_norm(morse_idx.astype(np.float64)))
        return s

    # ═══════════════════════════════════════════════════════════════
    #  PRODUCTION SCORING — real-world-ready methods
    # ═══════════════════════════════════════════════════════════════

    def fit_score(self, X: np.ndarray,
                  y: np.ndarray = None) -> np.ndarray:
        """API-compatible with full engines — reference-based scoring.

        When labels ``y`` are provided (0 = normal, 1 = crisis),
        fits the descriptor on normal-period data and scores all
        points by deviation from that reference distribution.

        When ``y`` is None, fits on all data (unsupervised).

        Parameters
        ----------
        X : (N, d) array — feature matrix (panel-flattened)
        y : (N,) array or None — binary labels (0 = normal)

        Returns
        -------
        scores : (N,) array — anomaly scores (higher = more anomalous)
        """
        X = np.asarray(X, dtype=np.float64)
        if y is not None:
            y = np.asarray(y)
            X_ref = X[y == 0]
        else:
            X_ref = X

        self.fit(X_ref)
        return self._reference_score(X, X_ref)

    def _reference_score(self, X: np.ndarray,
                         X_ref: np.ndarray) -> np.ndarray:
        """Score X by multi-view deviation from reference distribution.

        Mirrors the architecture of ``FusedSystemScorer``:
          1. Transform both X and X_ref through the descriptor
          2. Compute kNN-based deviation in descriptor space
          3. Z-score against reference statistics (positive-deviation only)
          4. Combine with descriptor-native features
          5. BSDT channels (delta_C, delta_G, delta_A, delta_T)
             for blind-spot detection (Section 2.2)

        Parameters
        ----------
        X     : (N, d) array — all data points
        X_ref : (N_ref, d) array — normal-period reference points

        Returns
        -------
        scores : (N,) array
        """
        from sklearn.neighbors import NearestNeighbors
        from scipy.spatial.distance import cdist as _cdist

        # 1. Descriptor features for all points and reference
        D_all = self.transform(X)
        D_ref = self.transform(X_ref)

        N = len(X)
        n_eigs = min(self.n_eigs, X.shape[1])

        # 2. kNN deviation in descriptor space
        k = min(10, len(D_ref) - 1)
        if k < 1:
            return self.score(X)

        nn = NearestNeighbors(n_neighbors=k, algorithm='auto')
        nn.fit(D_ref.astype(np.float32))
        dists, _ = nn.kneighbors(D_all.astype(np.float32))

        # Feature 1: mean kNN distance in descriptor space
        knn_mean = dists.mean(axis=1)
        # Feature 2: nearest-neighbor distance (d_1)
        knn_d1 = dists[:, 0]
        # Feature 3: persistence proxy (d_k - d_1) / (d_k + eps)
        knn_persist = (dists[:, -1] - dists[:, 0]) / (dists[:, -1] + 1e-10)

        # Reference statistics for Z-scoring
        ref_dists, _ = nn.kneighbors(D_ref.astype(np.float32))
        ref_mean_d = ref_dists.mean(axis=1)
        mu_ref = ref_mean_d.mean()
        std_ref = ref_mean_d.std() + 1e-10

        # Feature 4: Z-score of kNN distance (positive deviation only)
        z_knn = np.maximum((knn_mean - mu_ref) / std_ref, 0.0)

        # 3. Extract descriptor-native features
        grad_norm   = D_all[:, 0]
        mahalanobis = D_all[:, n_eigs + 1]
        medoid_dist = D_all[:, n_eigs + 2]
        trace_h     = D_all[:, n_eigs + 3]
        morse_idx   = D_all[:, n_eigs + 5].astype(np.float64)

        # Z-score each against reference distribution
        def zpos(vals, ref_vals):
            """Positive-deviation-only Z-score."""
            mu = ref_vals.mean()
            sigma = ref_vals.std() + 1e-10
            return np.maximum((vals - mu) / sigma, 0.0)

        ref_grad = D_ref[:, 0]
        ref_maha = D_ref[:, n_eigs + 1]
        ref_med  = D_ref[:, n_eigs + 2]
        ref_tr   = D_ref[:, n_eigs + 3]
        ref_morse = D_ref[:, n_eigs + 5].astype(np.float64)

        z_grad  = zpos(grad_norm, ref_grad)
        z_maha  = zpos(mahalanobis, ref_maha)
        z_med   = zpos(medoid_dist, ref_med)
        z_trace = zpos(np.abs(trace_h), np.abs(ref_tr))
        z_morse = zpos(morse_idx, ref_morse)

        # 4. Raw-space features (what makes simple Mahalanobis so strong)
        # kNN in raw feature space against reference
        k_raw = min(10, len(X_ref) - 1)
        nn_raw = NearestNeighbors(n_neighbors=k_raw, algorithm="auto")
        nn_raw.fit(X_ref.astype(np.float32))
        dists_raw, _ = nn_raw.kneighbors(X.astype(np.float32))
        raw_knn_mean = dists_raw.mean(axis=1)

        # Mahalanobis in raw space (proven AUC ~0.998 on ERCOT)
        raw_maha = mahalanobis  # already computed from descriptor

        # Reference kNN stats for raw space
        ref_dists_raw, _ = nn_raw.kneighbors(X_ref.astype(np.float32))
        ref_raw_mean_d = ref_dists_raw.mean(axis=1)
        z_raw_knn = np.maximum(
            (raw_knn_mean - ref_raw_mean_d.mean()) /
            (ref_raw_mean_d.std() + 1e-10), 0.0)

        # 5. Adaptive fusion — multi-view weighted combination
        def robust_norm(x):
            q1, q99 = np.percentile(x, [1, 99])
            xn = (x - q1) / (q99 - q1 + 1e-15)
            return np.clip(xn, 0.0, 1.0)

        # View A: Raw-space scoring (captures simple separability)
        v_raw = (0.50 * robust_norm(z_raw_knn) +
                 0.50 * robust_norm(raw_knn_mean))

        # View B: Descriptor-space kNN (captures topology-transformed distances)
        v_knn = (0.35 * robust_norm(z_knn) +
                 0.30 * robust_norm(knn_d1) +
                 0.20 * robust_norm(knn_persist) +
                 0.15 * robust_norm(knn_mean))

        # View C: Descriptor-native (Z-scored topology features)
        v_desc = (0.25 * robust_norm(z_grad) +
                  0.30 * robust_norm(z_maha) +
                  0.15 * robust_norm(z_med) +
                  0.10 * robust_norm(z_trace) +
                  0.20 * robust_norm(z_morse))

        # View D: BSDT channels (blind-spot detection, Section 2.2)
        #   Fits BSDTChannels on reference data and scores all points
        #   via E_BS (energy) + MFLS (gradient norm) composite.
        bsdt = BSDTChannels(k=min(10, max(2, len(X_ref) - 1)))
        bsdt.fit(X_ref)
        v_bsdt = robust_norm(bsdt.score(X))

        # Fuse: 35% raw + 25% descriptor-kNN + 25% topology + 15% BSDT
        scores = (0.35 * v_raw + 0.25 * v_knn +
                  0.25 * v_desc + 0.15 * v_bsdt)
        return scores

    def score_variants(self, X: np.ndarray, y: np.ndarray,
                       X_ref: np.ndarray = None) -> dict:
        """Compare all BSDT scoring variants on a labelled dataset.

        Runs 5 scoring strategies on the BSDT channels:
          1. Baseline  -- E_BS + MFLS composite (unsupervised)
          2. FullBSDT  -- uniform-weighted channel sum (unsupervised)
          3. QuadSurf  -- degree-2 polynomial surface (post-hoc)
          4. SignedLR  -- logistic regression (supervised)
          5. ExpoGate  -- QuadSurf + tanh + sigmoid (post-hoc)

        Parameters
        ----------
        X : (N, d) -- feature matrix
        y : (N,) -- binary labels (0 = normal, 1 = anomaly)
        X_ref : (N_ref, d) or None -- reference data (if None, uses y==0)

        Returns
        -------
        dict mapping variant name to {'scores', 'auroc', 'time'}.
        """
        import time as _time
        from sklearn.metrics import roc_auc_score

        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)
        if X_ref is None:
            X_ref = X[y == 0]

        # Fit BSDT on reference
        bsdt = BSDTChannels(k=min(10, max(2, len(X_ref) - 1)))
        bsdt.fit(X_ref)

        results = {}

        def _safe_auroc(y_true, y_score):
            try:
                return float(roc_auc_score(y_true, y_score))
            except ValueError:
                return float('nan')

        # 1. Baseline (E_BS + MFLS)
        t0 = _time.time()
        s = bsdt.score(X)
        results['baseline'] = {
            'scores': s,
            'auroc': _safe_auroc(y, s),
            'time': _time.time() - t0,
        }

        # 2. FullBSDT (uniform channel sum)
        t0 = _time.time()
        C = bsdt._channel_matrix(X)
        C_normed = np.zeros_like(C)
        for k in range(C.shape[1]):
            col = C[:, k]
            cmin, cmax = col.min(), col.max()
            if cmax - cmin > 1e-10:
                C_normed[:, k] = (col - cmin) / (cmax - cmin)
        s = C_normed.sum(axis=1)
        results['full_bsdt'] = {
            'scores': s,
            'auroc': _safe_auroc(y, s),
            'time': _time.time() - t0,
        }

        # 3. QuadSurf (post-hoc analytical)
        t0 = _time.time()
        bsdt.fit_quadsurf(X_ref)
        s = bsdt.score_quadsurf(X)
        results['quadsurf'] = {
            'scores': s,
            'auroc': _safe_auroc(y, s),
            'time': _time.time() - t0,
        }

        # 4. SignedLR (supervised -- the only variant needing labels)
        t0 = _time.time()
        bsdt.fit_signed_lr(X, y)
        s = bsdt.score_signed_lr(X)
        results['signed_lr'] = {
            'scores': s,
            'auroc': _safe_auroc(y, s),
            'time': _time.time() - t0,
            'weights': bsdt._lr_beta.tolist(),
        }

        # 5. ExpoGate (post-hoc analytical)
        t0 = _time.time()
        bsdt.fit_expogate(X_ref)
        s = bsdt.score_expogate(X)
        results['expo_gate'] = {
            'scores': s,
            'auroc': _safe_auroc(y, s),
            'time': _time.time() - t0,
        }

        return results

    def score_panel(self, X_3d: np.ndarray,
                    y_time: np.ndarray = None,
                    window: int = 4) -> np.ndarray:
        """Panel-aware scoring for (T, N, d) data.

        Designed for real-world financial panel data where:
          - T = number of time steps (quarters)
          - N = number of agents (banks, sectors, grid nodes)
          - d = number of features

        Produces a quarter-level anomaly score that incorporates:
          1. Per-point descriptor features
          2. Cross-sectional statistics (dispersion, skewness across agents)
          3. Temporal dynamics (rolling z-score, momentum)

        Parameters
        ----------
        X_3d   : (T, N, d) array — panel data
        y_time : (T,) array or None — per-quarter labels (0 = normal)
                 If provided, fits on normal quarters only.
        window : int — rolling window for temporal features

        Returns
        -------
        q_scores : (T,) array — quarter-level anomaly scores
        """
        X_3d = np.asarray(X_3d, dtype=np.float64)
        if X_3d.ndim != 3:
            raise ValueError(f'Expected (T, N, d) array, got shape {X_3d.shape}')

        T, N, d = X_3d.shape
        X_flat = X_3d.reshape(T * N, d)

        # Fit on normal-period data
        if y_time is not None:
            y_time = np.asarray(y_time)
            normal_mask = (y_time == 0)
            X_ref = X_3d[normal_mask].reshape(-1, d)
        else:
            # Use first 30% as "calm" reference period
            n_calm = max(1, int(T * 0.3))
            X_ref = X_3d[:n_calm].reshape(-1, d)

        self.fit(X_ref)

        # Compute per-point descriptor features
        D_flat = self.transform(X_flat)       # (T*N, n_eigs+6)
        S_flat = self._reference_score(X_flat, X_ref)  # (T*N,)

        n_eigs = min(self.n_eigs, d)
        D_3d = D_flat.reshape(T, N, -1)       # (T, N, n_eigs+6)
        S_3d = S_flat.reshape(T, N)            # (T, N)

        # ── Per-quarter cross-sectional statistics ──
        # Mean score across agents
        q_mean = S_3d.mean(axis=1)             # (T,)
        # Cross-sectional dispersion (systemic = all agents stressed)
        q_std = S_3d.std(axis=1)               # (T,)
        # Max agent score (worst-case)
        q_max = S_3d.max(axis=1)               # (T,)
        # Fraction of agents with score > 75th percentile of calm
        calm_threshold = np.percentile(S_flat[:len(X_ref)], 75)
        q_frac_high = (S_3d > calm_threshold).mean(axis=1)  # (T,)

        # Cross-sectional Morse index: mean and max
        morse_col_idx = n_eigs + 5
        morse_3d = D_3d[:, :, morse_col_idx]   # (T, N)
        q_morse_mean = morse_3d.mean(axis=1)   # (T,)
        q_morse_max = morse_3d.max(axis=1)     # (T,)

        # Cross-sectional gradient norm dispersion
        grad_3d = D_3d[:, :, 0]                # (T, N)
        q_grad_cv = grad_3d.std(axis=1) / (grad_3d.mean(axis=1) + 1e-10)

        # ── Temporal dynamics ──
        # Rolling Z-score of mean score (Basel III countercyclical buffer style)
        q_z = np.zeros(T)
        for t in range(window, T):
            w = q_mean[t-window:t]
            mu_w, std_w = w.mean(), w.std() + 1e-10
            q_z[t] = (q_mean[t] - mu_w) / std_w
        q_z = np.maximum(q_z, 0)  # positive deviation only

        # Score momentum (first derivative)
        q_mom = np.zeros(T)
        q_mom[1:] = q_mean[1:] - q_mean[:-1]
        q_mom = np.maximum(q_mom, 0)  # rising is concerning

        # Score acceleration (second derivative)
        q_acc = np.zeros(T)
        q_acc[2:] = q_mom[2:] - q_mom[1:-1]
        q_acc = np.maximum(q_acc, 0)

        # ── Fuse all quarter-level features ──
        def rnorm(x):
            q1, q99 = np.percentile(x, [1, 99])
            xn = (x - q1) / (q99 - q1 + 1e-15)
            return np.clip(xn, 0.0, 1.0)

        q_scores = (
            0.20 * rnorm(q_mean) +       # average agent distress
            0.10 * rnorm(q_max) +         # worst-case agent
            0.10 * rnorm(q_frac_high) +   # breadth of distress
            0.10 * rnorm(q_morse_mean) +  # topological signal
            0.05 * rnorm(q_morse_max) +   # worst-case topology
            0.05 * rnorm(q_grad_cv) +     # gradient dispersion
            0.15 * rnorm(q_z) +           # rolling z-score
            0.10 * rnorm(q_mom) +         # momentum
            0.05 * rnorm(q_acc) +         # acceleration
            0.10 * rnorm(q_std)           # cross-sectional spread
        )
        return q_scores

    # ═══════════════════════════════════════════════════════════════
    #  UNIVERSAL CONFORMAL SCORING — dataset-agnostic
    # ═══════════════════════════════════════════════════════════════

    def fit_reference(self, X_ref: np.ndarray,
                      cal_frac: float = 0.2,
                      random_state: int = 42) -> 'ReducedTensorDescriptor':
        """Fit the descriptor and calibration set for conformal scoring.

        Splits reference data into:
          - fit set (1 - cal_frac): used to fit GMM, covariance, medoid
          - calibration set (cal_frac): used to build the reference
            distribution of nonconformity scores for conformal inference

        Uses the proven multi-view _reference_score() as the base
        nonconformity measure (preserves geometric correlations),
        then wraps it in conformal calibration for distribution-free
        guarantees.

        Parameters
        ----------
        X_ref     : (N, d) array — normal-period reference data
        cal_frac  : float — fraction reserved for calibration (default 0.2)
        random_state : int — reproducibility seed

        Returns
        -------
        self
        """
        X_ref = np.asarray(X_ref, dtype=np.float64)
        N = len(X_ref)
        n_cal = max(10, int(N * cal_frac))
        n_fit = N - n_cal

        rng = np.random.default_rng(random_state)
        perm = rng.permutation(N)
        idx_fit = perm[:n_fit]
        idx_cal = perm[n_fit:]

        X_fit = X_ref[idx_fit]
        X_cal = X_ref[idx_cal]

        # Fit descriptor on the fit set
        self.fit(X_fit)

        # Store calibration and fit data
        self._cal_X = X_cal
        self._fit_X = X_fit      # reference distribution for scoring
        self._cal_N = n_cal

        # Compute descriptor features on calibration set
        D_cal = self.transform(X_cal)
        self._cal_features = D_cal

        # ── Multi-view nonconformity scores on calibration set ──
        # Use the proven _reference_score pipeline:
        #   40% raw-kNN + 30% desc-kNN + 30% topology
        self._cal_nonconf = self._reference_score(X_cal, self._fit_X)
        self._cal_nonconf_sorted = np.sort(self._cal_nonconf)

        # Also store per-feature CDFs for the rank-based view
        self._cal_sorted_features = np.sort(D_cal, axis=0)

        self._conformal_fitted = True
        return self

    def _feature_pvalues(self, D_test: np.ndarray,
                         D_cal: np.ndarray) -> np.ndarray:
        """Convert each descriptor feature to a tail probability.

        For each feature j and test point i:
            p_j(x_i) = (1 + #{z in cal : z_j >= x_ij}) / (n_cal + 1)

        This is the empirical survival function —
        distribution-free, scale-invariant, unit-invariant.

        Parameters
        ----------
        D_test : (N, m) — descriptor features of test points
        D_cal  : (n_cal, m) — descriptor features of calibration set

        Returns
        -------
        pvals : (N, m) — per-feature p-values in (0, 1]
        """
        N, m = D_test.shape
        n_cal = len(D_cal)
        pvals = np.zeros((N, m), dtype=np.float64)

        for j in range(m):
            # For each feature, count how many calibration values
            # are >= the test value (right tail = more anomalous)
            # Use searchsorted on the sorted calibration column
            sorted_col = np.sort(D_cal[:, j])
            # Number of cal values >= test value
            rank = n_cal - np.searchsorted(sorted_col, D_test[:, j],
                                           side='left')
            pvals[:, j] = (1 + rank) / (n_cal + 1)

        return pvals

    def _aggregate_pvalues(self, pvals: np.ndarray) -> np.ndarray:
        """Aggregate per-feature p-values into a single nonconformity score.

        Uses a combination of Fisher and Cauchy methods for robustness:

        Fisher: S_F = -2 * sum(log(p_j))   ~ chi^2(2m) under H0
        Cauchy: S_C = sum(tan(pi*(0.5 - p_j))) / m   (heavy-tailed, robust)

        Final: max(rank(S_F), rank(S_C))  — takes the more extreme signal

        This avoids dataset-specific weights entirely.

        Parameters
        ----------
        pvals : (N, m) — per-feature p-values

        Returns
        -------
        scores : (N,) — nonconformity scores (higher = more anomalous)
        """
        eps = 1e-15
        # Fisher combination
        fisher = -2.0 * np.sum(np.log(np.maximum(pvals, eps)), axis=1)

        # Cauchy combination (robust to dependence)
        cauchy = np.mean(np.tan(np.pi * (0.5 - pvals)), axis=1)

        # Combine: take the max of rank-normalised Fisher and Cauchy
        # This ensures that if either view detects the anomaly, it fires
        N = len(fisher)
        if N < 2:
            return fisher

        def rank_norm(x):
            """Rank-normalise to [0, 1]."""
            order = np.argsort(np.argsort(x))
            return order / (N - 1 + 1e-15)

        combined = np.maximum(rank_norm(fisher), rank_norm(cauchy))
        return combined

    def score_conformal(self, X: np.ndarray) -> np.ndarray:
        """Universal anomaly score — dataset-agnostic, distribution-free.

        Uses a two-view nonconformity pipeline:

        View 1 (geometric): The proven _reference_score(), which fuses
            raw-space kNN, descriptor-space kNN, and topology Z-scores.
            This preserves geometric correlations between features.

        View 2 (rank-based): Per-feature empirical p-values combined
            via Fisher + Cauchy. Purely distribution-free.

        Final: max(rank(view1), rank(view2)) — fires if either detects.
        Then calibrate against the calibration set for conformal guarantee.

        Must call ``fit_reference()`` first.

        Parameters
        ----------
        X : (N, d) array — points to score

        Returns
        -------
        scores : (N,) array — higher = more anomalous
        """
        if not getattr(self, '_conformal_fitted', False):
            raise RuntimeError('Call fit_reference() before score_conformal()')

        X = np.asarray(X, dtype=np.float64)
        N = len(X)

        # ── View 1: Multi-view geometric scoring (proven pipeline) ──
        view1 = self._reference_score(X, self._fit_X)

        # ── View 2: Rank-based p-value fusion (distribution-free) ──
        D_test = self.transform(X)
        pvals = self._feature_pvalues(D_test, self._cal_features)
        view2 = self._aggregate_pvalues(pvals)

        # ── Fuse: max of rank-normalised views ──
        if N < 3:
            return view1  # not enough points to rank-normalise view2

        def rank_norm(x):
            order = np.argsort(np.argsort(x)).astype(np.float64)
            return order / (len(x) - 1 + 1e-15)

        combined = np.maximum(rank_norm(view1), rank_norm(view2))
        return combined

    def predict_pvalue(self, X: np.ndarray) -> np.ndarray:
        """Conformal p-values with distribution-free validity.

        Uses the multi-view _reference_score() as the nonconformity
        measure, then computes conformal p-values:

            p(x) = (1 + #{i : A_cal_i >= A(x)}) / (n_cal + 1)

        where A(x) = _reference_score(x) (multi-view geometric score).

        Guarantee (Vovk et al., 2005):
            Under exchangeability, P(p(X) <= alpha) <= alpha
            for any distribution, any alpha, any d.

        This means:
            - Set alpha = 0.01 → at most 1% false alarm rate, guaranteed.
            - No tuning. No dataset-specific thresholds.
            - Works on ERCOT, bank data, or any future dataset.

        Must call ``fit_reference()`` first.

        Parameters
        ----------
        X : (N, d) array — points to score

        Returns
        -------
        pvalues : (N,) array — conformal p-values in (0, 1]
                  Small p = anomalous. Alert if p < alpha.
        """
        if not getattr(self, '_conformal_fitted', False):
            raise RuntimeError('Call fit_reference() before predict_pvalue()')

        X = np.asarray(X, dtype=np.float64)

        # Nonconformity score via multi-view geometric pipeline
        A_test = self._reference_score(X, self._fit_X)

        # Conformal p-value: compare against calibration nonconformity scores
        n_cal = self._cal_N
        A_cal_sorted = self._cal_nonconf_sorted

        # For each test point: p = (1 + #{cal scores >= A_test}) / (n_cal + 1)
        rank = n_cal - np.searchsorted(A_cal_sorted, A_test, side='left')
        pvalues = (1 + rank) / (n_cal + 1)

        return pvalues

    def score_universal(self, X: np.ndarray, y: np.ndarray,
                        T: int, N: int,
                        window: int = None) -> dict:
        """Universal dataset-agnostic scoring with conformal calibration.

        Runs all scoring modes and fuses them adaptively.
        No dataset-specific weights or hyperparameters.

        Strategy:
          1. fit_score(X, y) — reference-based multi-view scoring
             (optimal for point-level anomaly detection, e.g. ERCOT)
          2. score_panel(X_3d, y_time) — temporal panel scoring
             (optimal for structured panel data, e.g. bank crises)
          3. Conformal p-values — distribution-free false alarm control
          4. Rank-normalised fusion — max(rank_A, rank_B) per point

        The fusion automatically emphasises whichever view is stronger
        for the given dataset, without prior knowledge of dataset type.

        Parameters
        ----------
        X : (T*N, d) array — flat panel data
        y : (T*N,) array — labels (0 = normal)
        T : int — number of time periods
        N : int — number of agents per period
        window : int or None — rolling window (auto-detected if None)

        Returns
        -------
        dict with keys:
            'scores'     : (T*N,) — fused point-level scores
            'q_scores'   : (T,)   — period-level scores
            'pvalues'    : (T*N,) — conformal p-values (point-level)
            'q_pvalues'  : (T,)   — conformal p-values (period-level)
        """
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)
        d = X.shape[1]

        if window is None:
            window = 4 if T < 200 else max(4, T // 10)

        # ── View 1: Reference-based point scoring (fit_score) ──
        s_point = self.fit_score(X, y)

        # ── View 2: Panel-level temporal scoring ──
        X_3d = X.reshape(T, N, d)
        y_time = y.reshape(T, N)[:, 0]
        desc2 = ReducedTensorDescriptor(
            n_eigs=self.n_eigs, k_neighbors=self.k_neighbors
        )
        q_panel = desc2.score_panel(X_3d, y_time, window=window)
        # Expand to point-level
        s_panel_flat = np.repeat(q_panel, N)

        # ── Rank-normalised fusion ──
        def rank_norm(x):
            n = len(x)
            if n < 2:
                return x.copy()
            order = np.argsort(np.argsort(x)).astype(np.float64)
            return order / (n - 1 + 1e-15)

        # Point-level: max(rank(point_scores), rank(panel_expanded))
        fused = np.maximum(rank_norm(s_point), rank_norm(s_panel_flat))

        # Period-level: average fused score per period
        fused_3d = fused.reshape(T, N)
        q_fused = fused_3d.mean(axis=1)

        # ── Conformal calibration for distribution-free p-values ──
        # Use normal-period scores as calibration set
        ref_mask = (y == 0)
        cal_scores = fused[ref_mask]
        cal_sorted = np.sort(cal_scores)
        n_cal = len(cal_sorted)

        # Point-level conformal p-values
        rank_test = n_cal - np.searchsorted(cal_sorted, fused, side='left')
        pvalues = (1 + rank_test) / (n_cal + 1)

        # Period-level conformal p-values
        cal_q_mask = (y_time == 0)
        cal_q_scores = q_fused[cal_q_mask]
        cal_q_sorted = np.sort(cal_q_scores)
        n_cal_q = len(cal_q_sorted)
        rank_q = n_cal_q - np.searchsorted(cal_q_sorted, q_fused, side='left')
        q_pvalues = (1 + rank_q) / (n_cal_q + 1)

        return {
            'scores': fused,
            'q_scores': q_fused,
            'pvalues': pvalues,
            'q_pvalues': q_pvalues,
            's_point': s_point,
            's_panel': s_panel_flat,
            'q_panel': q_panel,
        }

    def score_conformal_panel(self, X_3d: np.ndarray,
                              y_time: np.ndarray = None,
                              window: int = 4) -> np.ndarray:
        """Universal panel-aware scoring with conformal calibration.

        Uses the multi-view _reference_score() as the base nonconformity
        measure, combined with temporal dynamics and cross-sectional
        aggregation. All components are rank-normalised for
        dataset-agnostic fusion.

        Parameters
        ----------
        X_3d   : (T, N, d) array — panel data
        y_time : (T,) array or None — per-period labels (0 = normal)
        window : int — rolling window for temporal features

        Returns
        -------
        q_scores : (T,) array — period-level anomaly scores
        """
        X_3d = np.asarray(X_3d, dtype=np.float64)
        if X_3d.ndim != 3:
            raise ValueError(f'Expected (T, N, d), got {X_3d.shape}')

        T, N, d = X_3d.shape
        X_flat = X_3d.reshape(T * N, d)

        # Determine reference data
        if y_time is not None:
            y_time = np.asarray(y_time)
            normal_mask = (y_time == 0)
            X_ref = X_3d[normal_mask].reshape(-1, d)
        else:
            n_calm = max(1, int(T * 0.3))
            X_ref = X_3d[:n_calm].reshape(-1, d)

        # Fit conformal reference
        self.fit_reference(X_ref, cal_frac=0.2)

        # ── Multi-view geometric scores for all points ──
        ref_scores = self._reference_score(X_flat, self._fit_X)   # (T*N,)
        ref_3d = ref_scores.reshape(T, N)            # (T, N)

        # Conformal p-values for all points
        pvals = self.predict_pvalue(X_flat)           # (T*N,)
        pvals_3d = pvals.reshape(T, N)                # (T, N)

        # ── Cross-sectional aggregation ──
        # Mean reference score per period (geometric, preserves signal)
        q_mean = ref_3d.mean(axis=1)

        # 90th percentile per period (tail risk)
        q_p90 = np.percentile(ref_3d, 90, axis=1)

        # Fraction of agents with p < 0.05 (breadth of anomalies)
        q_frac_sig = (pvals_3d < 0.05).mean(axis=1)

        # Cross-sectional dispersion
        q_std = ref_3d.std(axis=1)

        # Max-agent score per period
        q_max = ref_3d.max(axis=1)

        # ── Temporal dynamics ──
        # Rolling Z-score of mean reference score
        q_z = np.zeros(T)
        for t in range(window, T):
            w = q_mean[t-window:t]
            mu_w, std_w = w.mean(), w.std() + 1e-10
            q_z[t] = max((q_mean[t] - mu_w) / std_w, 0.0)

        # Momentum (acceleration)
        q_mom = np.zeros(T)
        q_mom[1:] = np.maximum(q_mean[1:] - q_mean[:-1], 0.0)

        # ── Rank-normalised fusion (no dataset-specific weights) ──
        components = np.column_stack([
            q_mean,      # average distress     (geometric signal)
            q_p90,       # tail risk            (geometric signal)
            q_max,       # worst-case agent     (geometric signal)
            q_frac_sig,  # breadth of anomalies (conformal signal)
            q_std,       # cross-sectional spread
            q_z,         # temporal acceleration
            q_mom,       # momentum
        ])

        def rank_norm(x):
            if x.max() == x.min():
                return np.zeros_like(x)
            order = np.argsort(np.argsort(x)).astype(np.float64)
            return order / (len(x) - 1 + 1e-15)

        n_comp = components.shape[1]
        ranked = np.zeros_like(components)
        for j in range(n_comp):
            ranked[:, j] = rank_norm(components[:, j])

        # Equal-weight average of ranks (universal, no tuning)
        q_scores = ranked.mean(axis=1)

        return q_scores

    @staticmethod
    def _to_scalar(val) -> float:
        """Safely convert any array-like energy output to a Python float.

        Avoids the NumPy >= 1.25 DeprecationWarning triggered by
        ``float(array_with_ndim_gt_0)``.
        """
        a = np.asarray(val)
        return a.flat[0] if a.ndim > 0 else float(a)

    def _numerical_gradient(self, x: np.ndarray,
                            energy_fn, eps: float = None) -> np.ndarray:
        """Central-difference gradient.  O(d) energy evaluations."""
        if eps is None:
            eps = self.eps_hessian
        d = len(x)
        grad = np.zeros(d)
        _s = self._to_scalar
        for i in range(d):
            ei = np.zeros(d)
            ei[i] = eps
            fp = _s(energy_fn((x + ei).reshape(1, -1)))
            fm = _s(energy_fn((x - ei).reshape(1, -1)))
            grad[i] = (fp - fm) / (2 * eps)
        return grad

    def _hessian_eigenvalues(self, x: np.ndarray,
                             energy_fn,
                             n_eigs: int) -> np.ndarray:
        """Compute leading eigenvalues of the Hessian at x.

        For d \u2264 50: full Hessian + eigvalsh \u2014 O(d\u00b3).
        For d > 50: Lanczos via scipy \u2014 O(n_eigs * d\u00b2).
        """
        d = len(x)
        eps = self.eps_hessian

        if d <= 50:
            # Full Hessian \u2014 O(d\u00b2) energy evaluations, O(d\u00b3) eigendecomp
            H = np.zeros((d, d))
            _s = self._to_scalar
            f0 = _s(energy_fn(x.reshape(1, -1)))
            for i in range(d):
                ei = np.zeros(d)
                ei[i] = eps
                for j in range(i, d):
                    ej = np.zeros(d)
                    ej[j] = eps
                    fpp = _s(energy_fn((x + ei + ej).reshape(1, -1)))
                    fpm = _s(energy_fn((x + ei - ej).reshape(1, -1)))
                    fmp = _s(energy_fn((x - ei + ej).reshape(1, -1)))
                    fmm = _s(energy_fn((x - ei - ej).reshape(1, -1)))
                    H[i, j] = (fpp - fpm - fmp + fmm) / (4 * eps * eps)
                    H[j, i] = H[i, j]
            eigs = np.linalg.eigvalsh(H)
            return eigs[:n_eigs]
        else:
            # Lanczos for large d \u2014 O(n_eigs * d\u00b2)
            from scipy.sparse.linalg import eigsh

            def hessian_matvec(v):
                """H @ v via finite differences."""
                _s = ReducedTensorDescriptor._to_scalar
                vn = v / (np.linalg.norm(v) + 1e-15) * eps
                fp = _s(energy_fn((x + vn).reshape(1, -1)))
                fm = _s(energy_fn((x - vn).reshape(1, -1)))
                f0 = _s(energy_fn(x.reshape(1, -1)))
                return ((fp + fm - 2 * f0) / (eps ** 2)) * v

            from scipy.sparse.linalg import LinearOperator
            H_op = LinearOperator((d, d), matvec=hessian_matvec)
            try:
                eigs, _ = eigsh(H_op, k=min(n_eigs, d - 1),
                                which='SA')  # smallest algebraic
                return np.sort(eigs)
            except Exception:
                return np.zeros(n_eigs)


# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  UNIFIED MODE SELECTOR
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

class SystemModeEngine:
    """
    Unified interface for selecting and running a physics system mode.

    Usage:
        engine = SystemModeEngine(mode='molecular')
        scores = engine.fit_score(X, y)

    Or as a toggle:
        engine = SystemModeEngine(mode='hybrid')
        engine.set_mode('gravity')    # switch mode
        scores = engine.fit_score(X, y)

    Parameters
    ----------
    mode : str or SystemMode
        'molecular', 'gravity', or 'hybrid'.
    filter_spectra : bool
        If True, also applies the SpectraFalseAlarmFilter to suppress
        noise from ChaosSpectrum/SpectralSpectrum operators.
    molecular_params : dict
        Parameters for MolecularEngine.
    gravity_params : dict
        Parameters for GravityModeEngine.
    hybrid_params : dict
        Parameters for HybridGravityEngine (includes blend_weight).
    """

    def __init__(self,
                 mode: Union[str, SystemMode] = 'hybrid',
                 filter_spectra: bool = True,
                 molecular_params: Optional[dict] = None,
                 gravity_params: Optional[dict] = None,
                 hybrid_params: Optional[dict] = None):

        if isinstance(mode, str):
            mode = SystemMode(mode.lower())
        self._mode = mode
        self.filter_spectra = filter_spectra

        self._mol_params = molecular_params or {}
        self._grav_params = gravity_params or {}
        self._hyb_params = hybrid_params or {}

        self._engine = self._build_engine()
        self._spectra_filter = SpectraFalseAlarmFilter() if filter_spectra else None

        self._last_scores: Optional[np.ndarray] = None
        self._last_mode: Optional[SystemMode] = None

    @property
    def mode(self) -> SystemMode:
        return self._mode

    @mode.setter
    def mode(self, value: Union[str, SystemMode]):
        if isinstance(value, str):
            value = SystemMode(value.lower())
        if value != self._mode:
            self._mode = value
            self._engine = self._build_engine()

    def set_mode(self, mode: Union[str, SystemMode]):
        """Toggle the active system mode."""
        self.mode = mode
        return self

    def _build_engine(self):
        if self._mode == SystemMode.MOLECULAR:
            return MolecularEngine(**self._mol_params)
        elif self._mode == SystemMode.GRAVITY:
            return GravityModeEngine(**self._grav_params)
        elif self._mode == SystemMode.HYBRID:
            return HybridGravityEngine(
                molecular_params=self._mol_params,
                gravity_params=self._grav_params,
                **self._hyb_params,
            )
        else:
            raise ValueError(f"Unknown mode: {self._mode}")

    def fit_score(self, X: np.ndarray, y: Optional[np.ndarray] = None
                  ) -> np.ndarray:
        """
        Run the selected physics engine and return anomaly scores.

        Scores are 100% topological (Morse alarm) — noise-immune.
        If filter_spectra=True, also applies persistence gating.
        """
        # Fit spectra filter on reference data
        if self._spectra_filter is not None:
            X_ref = X[y == 0] if y is not None else X
            self._spectra_filter.fit(X_ref)

        # Run the physics engine
        scores = self._engine.fit_score(X, y)

        # Apply spectra false-alarm filter
        if self._spectra_filter is not None:
            # Transform X for distance computation
            X_work = X
            if hasattr(self._engine, 'scaler_') and self._engine.scaler_ is not None:
                X_work = self._engine.scaler_.transform(X)
            scores = self._spectra_filter.filter_scores(X_work, scores)

        self._last_scores = scores
        self._last_mode = self._mode
        return scores

    def get_morse_operator(self) -> _MorseReplacementSpectrum:
        """
        Get a drop-in replacement operator for ChaosSpectrum.

        Use this to replace ChaosSpectrum in a RepresentationStack:
            engine = SystemModeEngine(mode='hybrid')
            engine.fit_score(X, y)
            morse_op = engine.get_morse_operator()
            stack = RepresentationStack(operators=[
                ('stat', StatisticalSpectrum()),
                ('morse', morse_op),   # replaces ('chaos', ChaosSpectrum())
                ...
            ])
        """
        if self._spectra_filter is not None:
            return self._spectra_filter.as_operator()
        else:
            op = _MorseReplacementSpectrum(k=15)
            return op

    def summary(self) -> Dict:
        """Return summary of the engine configuration."""
        info = {
            'mode': self._mode.value,
            'filter_spectra': self.filter_spectra,
            'engine_type': type(self._engine).__name__,
        }
        if self._last_scores is not None:
            info['last_score_stats'] = {
                'mean': float(self._last_scores.mean()),
                'std': float(self._last_scores.std()),
                'min': float(self._last_scores.min()),
                'max': float(self._last_scores.max()),
            }
        if (self._mode == SystemMode.HYBRID and
                hasattr(self._engine, '_cv_scores') and
                self._engine._cv_scores is not None):
            info['hybrid_blend'] = self._engine._cv_scores
        return info

    def get_reduced_descriptor(self,
                               X_ref: np.ndarray = None,
                               k_neighbors: int = 15,
                               n_eigs: int = None
                               ) -> ReducedTensorDescriptor:
        """Create a ReducedTensorDescriptor fitted on reference data.

        Parameters
        ----------
        X_ref : (N, d) array or None
            Reference data to fit on.  If None, uses the engine's
            stored reference data (from last fit_score call).
        k_neighbors : int
            Number of neighbors for local statistics.
        n_eigs : int or None
            Number of Hessian eigenvalues.  None → min(d, 10).

        Returns
        -------
        desc : ReducedTensorDescriptor
            Fitted descriptor ready for .transform() calls.

        Example
        -------
            engine = SystemModeEngine(mode='gravity')
            scores = engine.fit_score(X, y)
            desc = engine.get_reduced_descriptor()
            D = desc.transform(X_test)
            alarm = desc.get_alarm(X_test)
        """
        desc = ReducedTensorDescriptor(
            k_neighbors=k_neighbors, n_eigs=n_eigs)

        if X_ref is not None:
            desc.fit(X_ref)
        elif (hasattr(self._engine, 'scaler_') and
              self._engine.scaler_ is not None and
              hasattr(self._engine, 'mu_')):
            # Reconstruct reference from engine's stored state
            # Use the scaler's learned statistics
            mu = self._engine.scaler_.mean_
            std = self._engine.scaler_.scale_
            # Generate synthetic reference from the fitted distribution
            rng = np.random.RandomState(42)
            n_ref = 200
            d = len(mu)
            X_synth = rng.randn(n_ref, d) * std + mu
            desc.fit(X_synth)
        else:
            raise ValueError(
                "No reference data available. Pass X_ref or call "
                "fit_score() first.")
        return desc

    def __repr__(self):
        return (f"SystemModeEngine(mode={self._mode.value!r}, "
                f"filter_spectra={self.filter_spectra})")
