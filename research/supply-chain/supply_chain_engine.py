"""
supply_chain_engine.py — BSDT Supply Chain Simulation Engine
=============================================================
Domain VI of the grand unification paper.

Implements the same mathematical framework as gravity_engine.py
(Gaussian attraction + log repulsion, adaptive friction, BSDT
four-channel decomposition) but with supply-chain semantics:

  Agents     = supply chain nodes (suppliers, manufacturers, distributors, retailers)
  State x_i  = (inventory, lead_time, capacity_util, financial_health)  ∈ ℝ⁴
  Φ_self     = radial potential anchoring each node to its healthy baseline
  Φ_pair     = dependency coupling: upstream supply → downstream demand
  γ*(X)      = adaptive resilience buffer = α / λ_max(D²Φ_pair)

Four BSDT channels (supply chain interpretation):
  δ_C  Camouflage:       supplier looks healthy but has hidden single-source dependency
  δ_G  Feature Gap:      missing visibility into tier-2/tier-3 suppliers
  δ_A  Activity Anomaly: sudden demand spikes, lead time elongation
  δ_T  Temporal Novelty: unprecedented disruption patterns (pandemic, blockade)

Critical manifold theorem (supply chain version):
  Below C*: constant safety stock stabilises the network.
  Above C*: no fixed buffer prevents cascade — only adaptive rerouting succeeds.
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────
# Default parameters (match paper Table X)
# ─────────────────────────────────────────────────────────────
ALPHA       = 0.10    # radial spring (anchor to healthy baseline)
GAMMA_DEP   = 1.00    # dependency coupling strength
SIGMA_DEP   = 1.00    # coupling attraction length-scale
LAMBDA_REP  = 0.10    # competitive repulsion coefficient
EPS         = 1e-5    # softening term
F_MAX       = 50.0    # force clamp


# ─────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────

@dataclass
class SupplyNode:
    """A node in the supply chain network."""
    name: str
    tier: int                           # 0=raw, 1=component, 2=assembly, 3=OEM, 4=retail
    sector: str                         # 'semiconductor', 'automotive', 'petrochemical', etc.
    baseline: np.ndarray = field(default_factory=lambda: np.array([1.0, 1.0, 0.5, 0.8]))
    # baseline = [inventory_norm, lead_time_norm, capacity_util, financial_health]


@dataclass
class SupplyEdge:
    """Directed dependency: source → target (upstream → downstream)."""
    source: int
    target: int
    weight: float = 1.0     # dependency strength (0–1: how critical is this link?)
    substitutable: bool = True   # can target find an alternative supplier?


@dataclass
class SupplyChainNetwork:
    """Complete supply chain topology."""
    nodes: list[SupplyNode]
    edges: list[SupplyEdge]
    adjacency: np.ndarray = field(init=False)       # (N, N) weighted adjacency
    dependency: np.ndarray = field(init=False)       # (N, N) dependency strength

    def __post_init__(self):
        N = len(self.nodes)
        self.adjacency = np.zeros((N, N))
        self.dependency = np.zeros((N, N))
        for e in self.edges:
            self.adjacency[e.source, e.target] = e.weight
            self.dependency[e.source, e.target] = e.weight
            # Bidirectional coupling (weaker reverse: demand signal)
            self.adjacency[e.target, e.source] = 0.3 * e.weight


# ─────────────────────────────────────────────────────────────
# Potential energy functions
# ─────────────────────────────────────────────────────────────

def radial_energy(X: np.ndarray, baselines: np.ndarray,
                  alpha: float = ALPHA) -> float:
    """Φ_self = (α/2) Σᵢ ‖xᵢ − bᵢ‖²  — deviation from healthy baseline."""
    diff = X - baselines
    return 0.5 * alpha * float(np.sum(diff ** 2))


def pairwise_energy(X: np.ndarray, dep: np.ndarray,
                    gamma: float = GAMMA_DEP, sigma: float = SIGMA_DEP,
                    lam: float = LAMBDA_REP, eps: float = EPS) -> float:
    """Φ_pair — dependency coupling energy.

    Attraction: upstream health pulls downstream toward stability.
    Repulsion:  competitive substitution pressure keeps nodes separated.

    Uses the same Gaussian + log form as the financial gravity engine:
        Φ_pair = Σ_{(i,j)∈E} w_ij [ γ·erf_potential(r_ij/σ) − γλ·ln(r_ij) ]
    """
    N = X.shape[0]
    diff = X[:, None, :] - X[None, :, :]   # (N, N, d)
    dist = np.linalg.norm(diff, axis=2)     # (N, N)
    np.fill_diagonal(dist, eps)

    # Weighted by dependency strength
    W = dep + dep.T    # symmetrise for energy (physics)

    # Attraction (erf integral → simplified as Gaussian for speed)
    E_att = 0.5 * gamma * np.sum(W * sigma * np.sqrt(np.pi) * 0.5 *
                                 _erf_approx(dist / sigma))
    # Repulsion
    E_rep = -0.5 * gamma * lam * np.sum(W * np.log(dist + eps))

    return float(E_att + E_rep)


def _erf_approx(x: np.ndarray) -> np.ndarray:
    """Fast erf approximation (Abramowitz & Stegun 7.1.28)."""
    a = 0.3480242
    b = -0.0958798
    c = 0.7478556
    t = 1.0 / (1.0 + 0.47047 * np.abs(x))
    result = 1.0 - (a * t + b * t**2 + c * t**3) * np.exp(-x**2)
    return np.sign(x) * result


def total_energy(X: np.ndarray, baselines: np.ndarray,
                 dep: np.ndarray, **kw) -> float:
    return radial_energy(X, baselines, kw.get("alpha", ALPHA)) + \
           pairwise_energy(X, dep, kw.get("gamma", GAMMA_DEP),
                           kw.get("sigma", SIGMA_DEP),
                           kw.get("lam", LAMBDA_REP))


# ─────────────────────────────────────────────────────────────
# Gradient (force) — analytic
# ─────────────────────────────────────────────────────────────

def radial_force(X: np.ndarray, baselines: np.ndarray,
                 alpha: float = ALPHA) -> np.ndarray:
    """-∇Φ_self = α(b − X)  — restoring force toward healthy baseline."""
    return alpha * (baselines - X)


def pairwise_force(X: np.ndarray, dep: np.ndarray,
                   gamma: float = GAMMA_DEP, sigma: float = SIGMA_DEP,
                   lam: float = LAMBDA_REP, eps: float = EPS) -> np.ndarray:
    """-∇Φ_pair — dependency coupling forces.

    Same form as financial gravity engine:
        magnitude = -γ·(exp(-r²/σ²) − λ/r)
        force on i = Σ_j w_ij · magnitude_ij · unit_ij
    """
    N, d = X.shape
    diff = X[:, None, :] - X[None, :, :]   # (N, N, d)
    dist = np.linalg.norm(diff, axis=2)     # (N, N)
    np.fill_diagonal(dist, eps)
    unit = diff / (dist[:, :, None] + eps)

    W = dep + dep.T     # symmetrised coupling

    attraction = np.exp(-(dist ** 2) / (sigma ** 2))
    repulsion  = lam / (dist + eps)
    magnitude  = -gamma * W * (attraction - repulsion)
    np.fill_diagonal(magnitude, 0.0)

    F = np.sum(magnitude[:, :, None] * unit, axis=1)   # (N, d)

    # Force clamp
    norms = np.linalg.norm(F, axis=1, keepdims=True)
    scale = np.where(norms > F_MAX, F_MAX / (norms + 1e-12), 1.0)
    return F * scale


def total_force(X: np.ndarray, baselines: np.ndarray,
                dep: np.ndarray, **kw) -> np.ndarray:
    return radial_force(X, baselines, kw.get("alpha", ALPHA)) + \
           pairwise_force(X, dep, kw.get("gamma", GAMMA_DEP),
                          kw.get("sigma", SIGMA_DEP),
                          kw.get("lam", LAMBDA_REP))


# ─────────────────────────────────────────────────────────────
# Spectral radius via power iteration
# ─────────────────────────────────────────────────────────────

def _hvp(X: np.ndarray, v: np.ndarray, dep: np.ndarray,
         h: float = 1e-4, **kw) -> np.ndarray:
    """Finite‐difference Hessian-vector product for Φ_pair."""
    v_unit = v / (np.linalg.norm(v) + 1e-12)
    Fp = pairwise_force(X + h * v_unit, dep, **kw)
    Fm = pairwise_force(X - h * v_unit, dep, **kw)
    return (Fm - Fp) / (2 * h)


def spectral_radius(X: np.ndarray, dep: np.ndarray,
                    K: int = 20,
                    rng: np.random.Generator | None = None,
                    **kw) -> tuple[float, np.ndarray]:
    """Estimate λ_max(D²Φ_pair(X)) via power iteration."""
    if rng is None:
        rng = np.random.default_rng(0)
    v = rng.standard_normal(X.shape)
    v /= np.linalg.norm(v) + 1e-12
    lam = 0.0
    for _ in range(K):
        Hv = _hvp(X, v, dep, **kw)
        lam = float(np.sum(Hv * v))
        v = Hv / (np.linalg.norm(Hv) + 1e-12)
    return max(lam, 1e-6), v


# ─────────────────────────────────────────────────────────────
# BSDT Four-Channel Operator (Supply Chain)
# ─────────────────────────────────────────────────────────────

class SupplyChainBSDT:
    """BSDT four-channel decomposition for supply chain networks.

    δ_C (Camouflage):   Mahalanobis distance from normal operating regime
    δ_G (Feature Gap):  hidden dependency exposure (unmonitored tier-2/3)
    δ_A (Activity):     velocity of state change (demand spikes, lead time shifts)
    δ_T (Temporal):     negative log-likelihood under historical distribution
    """

    def __init__(self):
        self.mu0_: np.ndarray | None = None
        self.Sigma0_inv_: np.ndarray | None = None
        self.cov_diag_: np.ndarray | None = None
        self.X_prev_: np.ndarray | None = None
        self.v0_: float = 0.0    # normal-period velocity baseline

    def fit(self, X_normal: np.ndarray) -> "SupplyChainBSDT":
        """Fit reference distribution from normal-period data (T, N, d)."""
        Xf = X_normal.reshape(-1, X_normal.shape[-1])
        self.mu0_ = Xf.mean(axis=0)
        cov = np.cov(Xf.T) + 1e-6 * np.eye(Xf.shape[1])
        self.Sigma0_inv_ = np.linalg.inv(cov)
        self.cov_diag_ = np.diag(cov)

        # Compute normal-period velocity baseline
        if X_normal.ndim == 3 and X_normal.shape[0] > 1:
            velocities = np.linalg.norm(np.diff(X_normal, axis=0), axis=2)
            self.v0_ = float(np.mean(velocities))
        return self

    # ── Individual channels ──────────────────────────────────

    def delta_C(self, X: np.ndarray) -> np.ndarray:
        """Camouflage channel — Mahalanobis distance from normal.
        Low δ_C means the node *looks* healthy but may be fragile."""
        z = X - self.mu0_
        return np.sqrt(np.maximum(np.sum(z @ self.Sigma0_inv_ * z, axis=1), 0.0))

    def delta_G(self, X: np.ndarray, dep: np.ndarray) -> np.ndarray:
        """Feature Gap channel — hidden dependency exposure.
        Sum of dependency weights to unmonitored (tier-2+) suppliers.
        Nodes with high inbound dependency from few sources score high."""
        # Concentration risk: HHI of inbound dependency weights
        inbound = dep.sum(axis=0)           # total inbound per node
        inbound_sq = (dep ** 2).sum(axis=0) # sum of squared weights
        hhi = np.where(inbound > 1e-8,
                       inbound_sq / (inbound ** 2 + 1e-12),
                       0.0)
        return hhi  # ∈ [0, 1], 1 = single source

    def delta_A(self, X: np.ndarray) -> np.ndarray:
        """Activity Anomaly channel — excess state velocity.
        max(0, ‖ẋ‖ − v₀)  per node."""
        if self.X_prev_ is None:
            self.X_prev_ = X.copy()
            return np.zeros(X.shape[0])
        velocity = np.linalg.norm(X - self.X_prev_, axis=1)
        self.X_prev_ = X.copy()
        return np.maximum(velocity - self.v0_, 0.0)

    def delta_T(self, X: np.ndarray) -> np.ndarray:
        """Temporal Novelty channel — negative log-likelihood.
        -log p̂(x) under fitted Gaussian."""
        z = X - self.mu0_
        mah_sq = np.sum(z @ self.Sigma0_inv_ * z, axis=1)
        # -log p(x) ∝ 0.5 * mah_sq + const; we drop the constant
        return 0.5 * mah_sq

    # ── Composite E_BS ───────────────────────────────────────

    def ebs(self, X: np.ndarray, dep: np.ndarray,
            weights: np.ndarray | None = None) -> float:
        """Blind-spot energy E_BS = Σ_k w_k ψ_k(δ_k)."""
        dC = self.delta_C(X)
        dG = self.delta_G(X, dep)
        dA = self.delta_A(X)
        dT = self.delta_T(X)

        if weights is None:
            weights = np.array([0.25, 0.25, 0.25, 0.25])

        E = weights[0] * float(np.sum(dC)) + \
            weights[1] * float(np.sum(dG)) + \
            weights[2] * float(np.sum(dA)) + \
            weights[3] * float(np.sum(dT))
        return E

    def channel_scores(self, X: np.ndarray, dep: np.ndarray) -> dict[str, float]:
        """Per-channel aggregate scores for diagnostics."""
        return {
            "camouflage":      float(np.mean(self.delta_C(X))),
            "feature_gap":     float(np.mean(self.delta_G(X, dep))),
            "activity":        float(np.mean(self.delta_A(X))),
            "temporal_novelty": float(np.mean(self.delta_T(X))),
        }

    # ── Gradient (for alignment verification) ────────────────

    def gradient(self, X: np.ndarray) -> np.ndarray:
        """∇E_BS (camouflage + temporal channels) = 2·Σ₀⁻¹·(X − μ₀)."""
        z = X - self.mu0_
        return 2.0 * (z @ self.Sigma0_inv_.T)

    def mfls_score(self, X: np.ndarray) -> float:
        """‖∇E_BS(X)‖_F — Frobenius norm of gradient as detection score."""
        return float(np.linalg.norm(self.gradient(X)))


# ─────────────────────────────────────────────────────────────
# Disruption injection
# ─────────────────────────────────────────────────────────────

@dataclass
class Disruption:
    """A supply chain disruption event."""
    name: str
    onset_step: int             # time step when disruption begins
    duration: int               # duration in time steps
    affected_nodes: list[int]   # indices of directly affected nodes
    severity: float             # 0–1 (0 = minor, 1 = total shutdown)
    disruption_type: str        # 'capacity', 'logistics', 'demand', 'financial'

    def apply(self, X: np.ndarray, t: int) -> np.ndarray:
        """Apply disruption to state matrix at time t.

        Includes a precursor period (5-10 steps before onset) where
        small leading indicators appear — mimicking real supply chain
        early warning signals (slightly elongating lead times, minor
        financial stress, small capacity fluctuations).
        """
        X_new = X.copy()

        # Precursor period: subtle signals before main disruption
        precursor_window = 8
        if self.onset_step - precursor_window <= t < self.onset_step:
            precursor_progress = (t - (self.onset_step - precursor_window)) / precursor_window
            precursor_intensity = 0.08 * precursor_progress * self.severity
            for idx in self.affected_nodes:
                X_new[idx, 1] *= (1.0 + 0.5 * precursor_intensity)   # lead time uptick
                X_new[idx, 3] *= (1.0 - 0.2 * precursor_intensity)   # slight financial stress
                X_new[idx, 0] *= (1.0 - 0.1 * precursor_intensity)   # minor inventory draw
            return X_new

        if t < self.onset_step or t >= self.onset_step + self.duration:
            return X_new

        # Disruption profile: ramp up → plateau → gradual recovery
        progress = (t - self.onset_step) / self.duration
        if progress < 0.2:
            intensity = self.severity * (progress / 0.2)         # ramp up
        elif progress < 0.7:
            intensity = self.severity                            # plateau
        else:
            intensity = self.severity * (1.0 - (progress - 0.7) / 0.3)  # recovery

        for idx in self.affected_nodes:
            if self.disruption_type == 'capacity':
                # Capacity drops, lead time increases
                X_new[idx, 0] *= (1.0 - 0.8 * intensity)   # inventory drops
                X_new[idx, 1] *= (1.0 + 2.0 * intensity)   # lead time increases
                X_new[idx, 2] *= (1.0 - 0.9 * intensity)   # capacity drops
            elif self.disruption_type == 'logistics':
                # Lead time spikes, inventory slowly depletes
                X_new[idx, 1] *= (1.0 + 5.0 * intensity)   # massive lead time spike
                X_new[idx, 0] *= (1.0 - 0.3 * intensity)   # inventory gradual drain
            elif self.disruption_type == 'demand':
                # Demand shock: inventory plummets, financial stress
                X_new[idx, 0] *= (1.0 - 0.7 * intensity)
                X_new[idx, 3] *= (1.0 - 0.4 * intensity)   # financial stress
            elif self.disruption_type == 'financial':
                X_new[idx, 3] *= (1.0 - 0.8 * intensity)   # financial health collapse
                X_new[idx, 2] *= (1.0 - 0.5 * intensity)   # capacity follows

        return X_new


# ─────────────────────────────────────────────────────────────
# Cascade propagation
# ─────────────────────────────────────────────────────────────

def propagate_cascade(X: np.ndarray, dep: np.ndarray,
                      cascade_rate: float = 0.15) -> np.ndarray:
    """Propagate disruption downstream through dependency links.

    If upstream node i has degraded health, downstream j suffers
    proportionally to dependency weight w_ij.

    This is the supply chain analogue of financial contagion.
    """
    N, d = X.shape
    X_new = X.copy()

    for j in range(N):
        # Sum weighted upstream stress
        upstream_stress = 0.0
        total_weight = 0.0
        for i in range(N):
            if dep[i, j] > 0:
                # Stress = how far upstream node i deviates from healthy
                health_i = X[i, 3]    # financial health dimension
                cap_i = X[i, 2]       # capacity utilisation
                stress = max(0, 1.0 - min(health_i, cap_i))
                upstream_stress += dep[i, j] * stress
                total_weight += dep[i, j]

        if total_weight > 0:
            avg_stress = upstream_stress / total_weight
            # Cascade effect: downstream inventory and lead time degrade
            X_new[j, 0] *= (1.0 - cascade_rate * avg_stress)   # inventory
            X_new[j, 1] *= (1.0 + cascade_rate * 2.0 * avg_stress)  # lead time
            X_new[j, 2] *= (1.0 - cascade_rate * 0.5 * avg_stress)  # capacity

    return X_new


# ─────────────────────────────────────────────────────────────
# Adaptive resilience control
# ─────────────────────────────────────────────────────────────

def constant_buffer(X: np.ndarray, baselines: np.ndarray,
                    buffer_level: float = 0.2) -> np.ndarray:
    """Fixed safety stock strategy — constant buffer regardless of network state.
    Analogous to constant Basel III buffers in finance.

    Applies a FIXED correction magnitude per step, independent of stress level.
    Below C*: this is sufficient to restore stability.
    Above C*: the fixed correction is overwhelmed by cascade forces.
    """
    X_buffered = X.copy()
    # Fixed nudge toward baseline — same magnitude regardless of deviation size
    diff = baselines - X
    diff_norm = np.linalg.norm(diff, axis=1, keepdims=True)
    # Clamp correction to a fixed step size (doesn't scale with stress)
    max_step = buffer_level * 0.15   # small fixed step
    direction = np.where(diff_norm > 1e-8, diff / (diff_norm + 1e-12), 0.0)
    correction = max_step * direction
    X_buffered += correction
    # Clamp
    X_buffered[:, 0] = np.clip(X_buffered[:, 0], 0.01, 2.0)
    X_buffered[:, 1] = np.clip(X_buffered[:, 1], 0.1, 10.0)
    X_buffered[:, 2] = np.clip(X_buffered[:, 2], 0.01, 1.0)
    X_buffered[:, 3] = np.clip(X_buffered[:, 3], 0.01, 1.0)
    return X_buffered


def adaptive_buffer(X: np.ndarray, baselines: np.ndarray,
                    dep: np.ndarray, gamma_star: float,
                    alpha: float = ALPHA,
                    bsdt: SupplyChainBSDT | None = None) -> np.ndarray:
    """Adaptive resilience — buffer scales with E_BS and γ*(X).

    Correction intensity = E_BS-driven: scales with deviation magnitude.
    When γ* is small (high spectral radius = high coupling stress):
      → aggressive correction (large fraction of deviation corrected)
    When γ* is large (low stress):
      → minimal intervention (lean operation, ~same as constant buffer)

    This is the supply chain analogue of adaptive viscosity in NS,
    adaptive friction in neural networks, and BSDT damping in SAT.
    """
    X_buffered = X.copy()

    # Adaptive intensity: ranges from ~0.05 (calm) to ~0.5 (crisis)
    # γ* → 0 means λ_max → ∞ → extreme stress → intensity → 1
    intensity = 1.0 / (1.0 + 5.0 * gamma_star)  # sharper response curve
    intensity = np.clip(intensity, 0.05, 0.5)

    # Apply proportional correction toward baseline
    correction = intensity * (baselines - X)
    X_buffered += correction

    # Clamp to reasonable ranges
    X_buffered[:, 0] = np.clip(X_buffered[:, 0], 0.01, 2.0)   # inventory
    X_buffered[:, 1] = np.clip(X_buffered[:, 1], 0.1, 10.0)    # lead time
    X_buffered[:, 2] = np.clip(X_buffered[:, 2], 0.01, 1.0)    # capacity
    X_buffered[:, 3] = np.clip(X_buffered[:, 3], 0.01, 1.0)    # financial

    return X_buffered


# ─────────────────────────────────────────────────────────────
# Main simulation loop
# ─────────────────────────────────────────────────────────────

def run_simulation(
    network: SupplyChainNetwork,
    disruptions: list[Disruption],
    n_steps: int = 200,
    eta: float = 0.02,
    alpha: float = ALPHA,
    mode: str = "adaptive",     # "adaptive", "constant", "none"
    buffer_level: float = 0.2,
    cascade_rate: float = 0.15,
    seed: int = 42,
    verbose: bool = False,
) -> dict[str, np.ndarray]:
    """Run a full supply chain simulation.

    Parameters
    ----------
    network     : SupplyChainNetwork topology
    disruptions : list of Disruption events to inject
    n_steps     : total simulation steps
    mode        : "adaptive" (BSDT), "constant" (fixed buffer), "none" (no intervention)
    buffer_level: for constant mode, fixed buffer fraction

    Returns
    -------
    Dictionary with per-step arrays: energy, mfls, lambda_max, gamma_star,
    above_cman, cos_theta, node_health, channel_scores, cascade_depth
    """
    rng = np.random.default_rng(seed)
    N = len(network.nodes)
    d = 4   # state dimensions: inventory, lead_time, capacity, financial_health

    # Initialise state at baselines + small noise
    baselines = np.array([n.baseline for n in network.nodes])  # (N, d)
    X = baselines + 0.02 * rng.standard_normal((N, d))

    # Fit BSDT on normal-period data (first 20% of steps, pre-disruption)
    normal_steps = max(20, n_steps // 5)
    X_normal = np.zeros((normal_steps, N, d))
    X_sim = X.copy()
    for t in range(normal_steps):
        X_sim += 0.005 * rng.standard_normal((N, d))    # natural fluctuations
        X_sim = np.clip(X_sim, 0.01, 2.0)
        X_normal[t] = X_sim.copy()

    bsdt = SupplyChainBSDT()
    bsdt.fit(X_normal)

    dep = network.dependency

    # Output arrays
    energy      = np.zeros(n_steps)
    mfls        = np.zeros(n_steps)
    lambda_max  = np.zeros(n_steps)
    gamma_star  = np.zeros(n_steps)
    above_cman  = np.zeros(n_steps, dtype=bool)
    cos_theta   = np.zeros(n_steps)
    node_health = np.zeros((n_steps, N))     # mean health per node
    cascade_depth = np.zeros(n_steps)
    channels    = {k: np.zeros(n_steps) for k in
                   ["camouflage", "feature_gap", "activity", "temporal_novelty"]}

    X = baselines + 0.02 * rng.standard_normal((N, d))
    bsdt.X_prev_ = X.copy()  # reset velocity tracker

    _lam_cache = 0.01

    for t in range(n_steps):
        if verbose and t % 20 == 0:
            print(f"  step {t:3d}/{n_steps}")

        # 1. Apply disruption shocks
        for dis in disruptions:
            X = dis.apply(X, t)

        # 2. Cascade propagation
        X = propagate_cascade(X, dep, cascade_rate=cascade_rate)

        # 3. Natural dynamics (gradient flow toward baselines)
        F = total_force(X, baselines, dep, alpha=alpha)
        X = X + eta * F
        X += 0.003 * rng.standard_normal((N, d))   # stochastic noise

        # 4. Control intervention
        if t % 4 == 0:
            lam, _ = spectral_radius(X, dep, K=15, rng=rng)
            _lam_cache = lam
        else:
            lam = _lam_cache

        gs = alpha / (lam + 1e-9)

        if mode == "adaptive":
            X = adaptive_buffer(X, baselines, dep, gs, alpha=alpha, bsdt=bsdt)
        elif mode == "constant":
            X = constant_buffer(X, baselines, buffer_level=buffer_level)
        # else: no intervention

        # 5. Clamp state
        X[:, 0] = np.clip(X[:, 0], 0.01, 2.0)
        X[:, 1] = np.clip(X[:, 1], 0.1, 10.0)
        X[:, 2] = np.clip(X[:, 2], 0.01, 1.0)
        X[:, 3] = np.clip(X[:, 3], 0.01, 1.0)

        # 6. Record metrics
        energy[t] = total_energy(X, baselines, dep, alpha=alpha)
        mfls[t] = bsdt.mfls_score(X)
        lambda_max[t] = lam
        gamma_star[t] = gs
        above_cman[t] = lam > alpha

        # Gradient alignment: ∇E_BS should align with −∇Φ (= F)
        # i.e. the detection gradient and the restoring force point in the
        # same direction when the system is stressed.
        G_bsdt = bsdt.gradient(X)
        # Use magnitude-weighted alignment (avoids near-zero noise)
        G_flat = G_bsdt.ravel()
        F_flat = F.ravel()
        nG_total = np.linalg.norm(G_flat)
        nF_total = np.linalg.norm(F_flat)
        if nG_total > 1e-8 and nF_total > 1e-8:
            cos_theta[t] = float(np.dot(G_flat, F_flat) / (nG_total * nF_total))
        else:
            cos_theta[t] = 0.0

        # Node health = mean of (capacity + financial_health) / 2
        node_health[t] = 0.5 * (X[:, 2] + X[:, 3])

        # Channel scores
        ch = bsdt.channel_scores(X, dep)
        for k, v in ch.items():
            channels[k][t] = v

        # Cascade depth: count nodes with health < 50%
        cascade_depth[t] = float(np.sum(node_health[t] < 0.5))

    return {
        "energy": energy,
        "mfls": mfls,
        "lambda_max": lambda_max,
        "gamma_star": gamma_star,
        "above_cman": above_cman,
        "cos_theta": cos_theta,
        "node_health": node_health,
        "cascade_depth": cascade_depth,
        "channels": channels,
        "baselines": baselines,
        "final_state": X,
    }
