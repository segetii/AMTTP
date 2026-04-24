"""HybridEngine — gravity (long-range attraction) + molecular (short-range LJ
repulsion) + BSDT-controlled adaptive damping.

Force decomposition:
    F_total = F_gravity (erf-log + radial spring)
            + F_LJ      (Lennard-Jones short-range hard core)
            − ζ V        (Langevin friction)
            − γ*_t · ⟨F_total, u_state⟩ · u_state    (master-operator damping)

Captures both the macro coupling structure (Gravity) and micro hard-core
repulsion (Molecular) in one engine — the production engine of choice when
data has both regimes (e.g. crowded but finite-size institutions).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from ..control import MasterOperator
from ..state import Snapshot


@dataclass
class Hybrid:
    op: MasterOperator
    dt: float = 1e-2
    mass: float = 1.0
    zeta: float = 0.10
    kT: float = 1e-3
    lj_eps: float = 1.0          # Lennard-Jones well depth
    lj_sigma: float = 0.5        # LJ characteristic distance
    cutoff: float = 2.5          # in units of lj_sigma
    rng: np.random.Generator = None  # type: ignore

    def __post_init__(self):
        if self.rng is None:
            self.rng = np.random.default_rng(0)

    # ── short-range LJ force on each agent ──────────────────────
    def _lj_force(self, X: np.ndarray) -> np.ndarray:
        N, d = X.shape
        diff = X[:, None, :] - X[None, :, :]            # (N, N, d)
        r2 = (diff * diff).sum(axis=2) + 1e-12          # (N, N)
        r2_safe = np.where(r2 < (self.cutoff * self.lj_sigma) ** 2, r2, np.inf)
        sr2 = (self.lj_sigma ** 2) / r2_safe
        sr6 = sr2 ** 3
        sr12 = sr6 ** 2
        # F_ij = 24 ε (2 sr12 - sr6) / r²  · (x_i - x_j)
        coef = 24.0 * self.lj_eps * (2.0 * sr12 - sr6) / r2_safe
        np.fill_diagonal(coef, 0.0)
        return (coef[:, :, None] * diff).sum(axis=1)

    # ── master-controlled total force ──────────────────────────
    def _total_force(self, snap: Snapshot, V: np.ndarray) -> np.ndarray:
        F_grav = self.op.force(snap)
        F_lj   = self._lj_force(snap.X)
        F_drag = -self.zeta * V
        # noise
        noise_std = float(np.sqrt(2.0 * self.zeta * self.kT / self.dt))
        xi = self.rng.standard_normal(size=snap.X.shape)
        F = F_grav + F_lj + F_drag + noise_std * xi
        # apply master damping along state-space u
        u = self.op.collapse_direction_state(snap)
        proj = float((F * u).sum())
        gamma = self.op.damp.gamma_star(snap)
        return F - gamma * proj * u

    def step(self, snap: Snapshot, V: np.ndarray) -> tuple[Snapshot, np.ndarray]:
        a = self._total_force(snap, V) / self.mass
        V_half = V + 0.5 * self.dt * a
        X_new = snap.X + self.dt * V_half
        snap_new = Snapshot(X=X_new, X_prev=snap.X, history=snap.history)
        a_new = self._total_force(snap_new, V_half) / self.mass
        V_new = V_half + 0.5 * self.dt * a_new
        return snap_new, V_new

    def trajectory(self, snap: Snapshot, T: int,
                   V0: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        V = np.zeros_like(snap.X) if V0 is None else V0
        Xs = np.empty((T + 1, *snap.X.shape))
        Vs = np.empty_like(Xs)
        Xs[0], Vs[0] = snap.X, V
        s = snap
        for t in range(T):
            s, V = self.step(s, V)
            Xs[t + 1], Vs[t + 1] = s.X, V
        return Xs, Vs
