"""HybridEngine — gravity (long-range) + Lennard-Jones (short-range) + master control.

EVERY physical scale is derived from the calibration panel. No heuristics:

    σ_LJ    = 1st percentile of pairwise distances in normal period
              (sets the LJ wall just inside the tail of typical crowding)
    ε_LJ    = F_max · σ_LJ / 24
              (LJ force magnitude at r=σ matches gravity F_max — same scale)
    cutoff  = median(pairwise distance) / σ_LJ
              (above the median, gravity owns the long range)
    dt      = 2π / (20 · ω_LJ),  ω_LJ = √(72ε/(m σ²))
              (20 velocity-Verlet steps per LJ vibration period — MD CFL identity)
    ζ       = 2 √(72 ε m / σ²)
              (critical Langevin damping at the LJ minimum — fastest non-osc decay)
    kT      = m · ⟨‖Δx‖²⟩ / d
              (equipartition from observed normal-period displacements)
    F_max_LJ = ForceField.F_max    (structural clamp = gravity clamp, same scale)

All physical constants are MD identities (LJ functional form, equipartition,
fluctuation-dissipation), not user-tuned numbers.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from math import pi, sqrt
import numpy as np
from ..control import MasterOperator
from ..state import Snapshot


@dataclass
class Hybrid:
    op: MasterOperator
    dt: float
    mass: float
    zeta: float
    kT: float
    lj_eps: float
    lj_sigma: float
    cutoff: float
    F_max_lj: float
    rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(0))

    # ────────────────────────── data-driven constructor ──────────────────────────
    @classmethod
    def from_panel(cls, op: MasterOperator, panel: np.ndarray, *,
                   mass: float = 1.0,
                   percentile_sigma: float = 1.0,
                   percentile_cutoff: float = 50.0,
                   steps_per_period: int = 20,
                   seed: int = 0) -> "Hybrid":
        """Derive every physical scale from the (T0, N, d) calibration panel."""
        T0, N, d = panel.shape
        # ── spatial scales: pairwise distance distribution
        D_all = []
        for t in range(T0):
            X = panel[t]
            q = (X * X).sum(axis=1)
            D2 = q[:, None] + q[None, :] - 2.0 * (X @ X.T)
            mask = ~np.eye(N, dtype=bool)
            D_all.append(np.sqrt(np.clip(D2[mask], 0.0, None)))
        D_norm = np.concatenate(D_all)
        sigma = float(np.percentile(D_norm, percentile_sigma))
        median_d = float(np.percentile(D_norm, percentile_cutoff))
        if sigma <= 0:
            sigma = float(D_norm[D_norm > 0].min()) if (D_norm > 0).any() else 1e-3
        cutoff = max(median_d / sigma, 1.5)  # 1.5 = LJ minimum r/σ — never below

        # ── force scale: match gravity clamp at r = σ
        F_max = op.forces.F_max
        eps = F_max * sigma / 24.0

        # ── time scale: 20 steps per LJ vibration period
        omega = sqrt(72.0 * eps / (mass * sigma * sigma))
        dt = 2.0 * pi / (steps_per_period * omega)

        # ── Langevin damping: critical at LJ minimum
        zeta = 2.0 * sqrt(72.0 * eps * mass / (sigma * sigma))

        # ── thermal: equipartition from observed displacements
        if T0 >= 2:
            disp = np.diff(panel, axis=0)
            kT = float(mass * (disp * disp).sum(axis=2).mean() / d)
        else:
            kT = 0.0

        return cls(op=op, dt=dt, mass=mass, zeta=zeta, kT=kT,
                   lj_eps=eps, lj_sigma=sigma, cutoff=cutoff,
                   F_max_lj=F_max, rng=np.random.default_rng(seed))

    # ───────────────────────────── force computation ────────────────────────────
    def _lj_force(self, X: np.ndarray) -> np.ndarray:
        N, d = X.shape
        diff = X[:, None, :] - X[None, :, :]
        r2 = (diff * diff).sum(axis=2) + 1e-12
        r2_safe = np.where(r2 < (self.cutoff * self.lj_sigma) ** 2, r2, np.inf)
        sr2 = (self.lj_sigma ** 2) / r2_safe
        sr6 = sr2 ** 3
        sr12 = sr6 ** 2
        coef = 24.0 * self.lj_eps * (2.0 * sr12 - sr6) / r2_safe
        np.fill_diagonal(coef, 0.0)
        F_lj = (coef[:, :, None] * diff).sum(axis=1)
        # structural clamp — same scale as gravity field
        norms = np.linalg.norm(F_lj, axis=1, keepdims=True)
        scale = np.minimum(1.0, self.F_max_lj / np.clip(norms, 1e-12, None))
        return F_lj * scale

    def _total_force(self, snap: Snapshot, V: np.ndarray) -> np.ndarray:
        F_grav = self.op.force(snap)
        F_lj   = self._lj_force(snap.X)
        F_drag = -self.zeta * V
        noise_std = float(np.sqrt(2.0 * self.zeta * self.kT / max(self.dt, 1e-12)))
        xi = self.rng.standard_normal(size=snap.X.shape)
        F = F_grav + F_lj + F_drag + noise_std * xi
        u = self.op.collapse_direction_state(snap)
        proj = float((F * u).sum())
        gamma = self.op.damp.gamma_star(snap)
        return F - gamma * proj * u

    # ───────────────────────────────── stepping ─────────────────────────────────
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

    def report(self) -> dict:
        """Inspect the data-derived physics scales."""
        return dict(sigma=self.lj_sigma, eps=self.lj_eps, cutoff=self.cutoff,
                    dt=self.dt, zeta=self.zeta, kT=self.kT, mass=self.mass,
                    F_max=self.F_max_lj)
