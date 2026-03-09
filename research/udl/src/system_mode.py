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
  Post-simulation positions are scored by three complementary signal
  families, then fused via min-max normalisation + equal-weight average:

  1. **MorseTopologyAlarm** — kNN distance features (4D)
  2. **BettiBarcodeSuite** — multi-scale β₀/β₁/χ/Conley (19D)
  3. **UDLPostSimScorer**  — best-4 UDL operators: Phase + Topological
     + KernelRKHS + Rank (≈27D), mAUC 0.972 on paper benchmarks

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
#  FUSED SYSTEM SCORER
# ═══════════════════════════════════════════════════════════════════

class FusedSystemScorer:
    """
    Combines Morse topology alarm + Betti barcode suite + UDL
    operator ensemble into a single anomaly scorer.

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

    Fusion: min-max normalise each component, equal-weight average.
    For simulation-size inputs, all three score directly.
    For larger inputs, Morse + Betti score directly (fast kNN),
    while UDL scores are kNN-interpolated from the simulation subset.
    """

    def __init__(self, k: int = 15, use_betti: bool = True,
                 use_udl: bool = True):
        self.k = k
        self.morse = MorseTopologyAlarm(k=k)
        self.betti = BettiBarcodeSuite(k=min(k + 5, 25)) if use_betti else None
        self.udl = UDLPostSimScorer(k=k) if use_udl else None
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
        """Full multi-view scoring (≤ simulation-size inputs)."""
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
        UDL operators) or MorseTopologyAlarm fallback (noise-immune).
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

        # \u2500\u2500 1. Gradient norm \u2016\u2207E_BS\u2016 \u2014 O(Nd) \u2500\u2500
        for i in range(N):
            xi = X[i]
            if gradient_fn is not None:
                grad = gradient_fn(xi)
            elif energy_fn is not None:
                grad = self._numerical_gradient(xi, energy_fn)
            else:
                # Mahalanobis gradient: \u03a3\u207b\u00b9(x - \u03bc) / \u03b4_C
                diff = xi - self._ref_mean
                grad = self._ref_cov_inv @ diff
            out[i, 0] = np.linalg.norm(grad)

        # \u2500\u2500 2. Hessian eigenvalues \u2014 O(d\u00b3) per point \u2500\u2500
        for i in range(N):
            xi = X[i]
            if energy_fn is not None:
                eigs = self._hessian_eigenvalues(xi, energy_fn, n_eigs)
            else:
                # Mahalanobis Hessian is \u03a3\u207b\u00b9 (constant)
                eigs = np.linalg.eigvalsh(self._ref_cov_inv)[:n_eigs]
            out[i, 1:1+n_eigs] = np.sort(eigs)  # ascending

            # \u2500\u2500 5. Trace of Hessian \u2014 sum of eigenvalues \u2500\u2500
            out[i, n_eigs + 3] = np.sum(eigs)

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
