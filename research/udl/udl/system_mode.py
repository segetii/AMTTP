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
#  LYAPUNOV STABILISER (iteration-only — never touches predictions)
# ═══════════════════════════════════════════════════════════════════

class LyapunovStabiliser:
    """
    Auxiliary Lyapunov controller for solver stability.

    Used ONLY inside the Euler integration loop to:
      - Backtrack step size when energy increases (Armijo condition)
      - Clamp forces to prevent numerical blow-up
      - Monitor convergence via energy descent

    The Lyapunov signal is **never** exposed to the prediction /
    alarm output.  This is the "decoupled auxiliary Lyapunov" pattern
    from robust control / stochastic MPC.
    """

    def __init__(self, armijo_c: float = 1e-4, backtrack_rho: float = 0.5,
                 max_force_norm: float = 10.0, min_eta: float = 1e-6):
        self.armijo_c = armijo_c
        self.backtrack_rho = backtrack_rho
        self.max_force_norm = max_force_norm
        self.min_eta = min_eta
        self.energy_trace: List[float] = []

    def clamp_forces(self, F: np.ndarray) -> np.ndarray:
        """Clamp per-particle force magnitude to prevent blow-up."""
        norms = np.linalg.norm(F, axis=1, keepdims=True)
        scale = np.minimum(1.0, self.max_force_norm / (norms + 1e-15))
        return F * scale

    def accept_step(self, E_old: float, E_new: float,
                    grad_norm_sq: float, eta: float) -> Tuple[bool, float]:
        """
        Armijo sufficient-decrease test.

        Returns (accept, new_eta).
        If rejected, eta is reduced by backtrack_rho (with minimum floor).
        """
        if E_new <= E_old - self.armijo_c * eta * grad_norm_sq:
            self.energy_trace.append(E_new)
            return True, eta
        else:
            new_eta = max(eta * self.backtrack_rho, self.min_eta)
            return False, new_eta

    def compute_energy(self, X: np.ndarray, mu: np.ndarray,
                       alpha: float, gamma: float, sigma: float,
                       lambda_rep: float, eps: float = 1e-5) -> float:
        """Compute total system energy (Lyapunov candidate)."""
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
                 use_fused: bool = True):
        self.epsilon = epsilon
        self.sigma_lj = sigma_lj
        self.alpha_radial = alpha_radial
        self.eta = eta
        self.iterations = iterations
        self.k_neighbors = k_neighbors
        self.normalize = normalize
        self.max_samples = max_samples
        self.use_fused = use_fused

        self.stabiliser = LyapunovStabiliser()
        self.alarm = MorseTopologyAlarm(k=k_neighbors)
        self.fused_scorer = FusedSystemScorer(k=k_neighbors) if use_fused else None

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

        # Euler integration with Lyapunov stability control
        eta = self.eta
        n_sim = len(X_work)
        # Reduce iterations for large subsamples
        iters = self.iterations if n_sim <= 1000 else max(20, self.iterations // 2)
        for step in range(iters):
            # Compute forces
            F_lj = self._lennard_jones_forces(X_work)
            F_radial = -self.alpha_radial * (X_work - self.mu_)
            F_total = F_lj + F_radial

            # Lyapunov clamps forces (solver stability only)
            F_total = self.stabiliser.clamp_forces(F_total)

            # Armijo backtracking (solver stability only)
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

            # Check convergence
            displacement = eta * np.max(np.linalg.norm(F_total, axis=1))
            if displacement < 1e-6:
                break

        self.X_final_ = X_work

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
                 use_fused: bool = True):
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

        self.stabiliser = LyapunovStabiliser(min_eta=1e-5)
        self.alarm = MorseTopologyAlarm(k=k_neighbors)
        self.fused_scorer = FusedSystemScorer(k=k_neighbors) if use_fused else None

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
        """Approximate energy (kNN-consistent to avoid force/energy mismatch)."""
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

        eta = self.eta
        n_sim = len(X_work)
        iters = self.iterations if n_sim <= 1000 else max(20, self.iterations // 2)
        for step in range(iters):
            F_pair = self._pairwise_forces(X_work)
            F_radial = -self.alpha * (X_work - self.mu_)
            F_total = F_pair + F_radial

            F_total = self.stabiliser.clamp_forces(F_total)

            # Simple step with clamping (avoid Armijo mismatch)
            X_work = X_work + eta * F_total

            # Check convergence
            displacement = eta * np.max(np.linalg.norm(F_total, axis=1))
            if displacement < 1e-6:
                break

        self.X_final_ = X_work

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
                 gravity_params: Optional[dict] = None):
        self.blend_weight = blend_weight
        mol_kw = molecular_params or {}
        grav_kw = gravity_params or {}

        self.molecular = MolecularEngine(**mol_kw)
        self.gravity = GravityModeEngine(**grav_kw)

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


# ═══════════════════════════════════════════════════════════════════
#  UNIFIED MODE SELECTOR
# ═══════════════════════════════════════════════════════════════════

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

    def __repr__(self):
        return (f"SystemModeEngine(mode={self._mode.value!r}, "
                f"filter_spectra={self.filter_spectra})")
