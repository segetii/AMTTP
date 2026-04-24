"""MolecularEngine — second-order Langevin (velocity-Verlet) dynamics.

All scales derived from the calibration panel:

    dt   = ε_dt · σ_min / F_max     (CFL — same as Gravity)
    ζ    = 2 √(α m)                  (critical damping at the radial spring scale)
    kT   = m · ⟨‖Δx‖²⟩ / d           (equipartition from observed displacements)

The radial spring α is the only intrinsic stiffness in the un-coupled limit;
critical damping there guarantees no oscillation in the dominant mode.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from math import sqrt
import numpy as np
from ..control import MasterOperator
from ..state import Snapshot


@dataclass
class Molecular:
    op: MasterOperator
    dt: float
    mass: float
    zeta: float
    kT: float
    controlled: bool = True
    rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(0))

    @classmethod
    def from_panel(cls, op: MasterOperator, panel: np.ndarray, *,
                   mass: float = 1.0, eps_dt: float = 0.1,
                   controlled: bool = True, seed: int = 0) -> "Molecular":
        T0, N, d = panel.shape
        D_all = []
        for t in range(T0):
            X = panel[t]
            q = (X * X).sum(axis=1)
            D2 = q[:, None] + q[None, :] - 2.0 * (X @ X.T)
            mask = ~np.eye(N, dtype=bool)
            D_all.append(np.sqrt(np.clip(D2[mask], 0.0, None)))
        D_norm = np.concatenate(D_all)
        sigma_min = float(np.percentile(D_norm, 1.0))
        if sigma_min <= 0:
            sigma_min = float(D_norm[D_norm > 0].min()) if (D_norm > 0).any() else 1e-3
        dt = eps_dt * sigma_min / max(op.forces.F_max, 1e-12)
        zeta = 2.0 * sqrt(op.potential.alpha * mass)
        if T0 >= 2:
            disp = np.diff(panel, axis=0)
            kT = float(mass * (disp * disp).sum(axis=2).mean() / d)
        else:
            kT = 0.0
        return cls(op=op, dt=dt, mass=mass, zeta=zeta, kT=kT,
                   controlled=controlled, rng=np.random.default_rng(seed))

    def _accel(self, snap: Snapshot, V: np.ndarray) -> np.ndarray:
        F = self.op.step(snap) if self.controlled else self.op.force(snap)
        noise_std = float(np.sqrt(2.0 * self.zeta * self.kT / max(self.dt, 1e-12)))
        xi = self.rng.standard_normal(size=snap.X.shape)
        return (F - self.zeta * V + noise_std * xi) / self.mass

    def step(self, snap: Snapshot, V: np.ndarray) -> tuple[Snapshot, np.ndarray]:
        a = self._accel(snap, V)
        V_half = V + 0.5 * self.dt * a
        X_new = snap.X + self.dt * V_half
        snap_new = Snapshot(X=X_new, X_prev=snap.X, history=snap.history)
        a_new = self._accel(snap_new, V_half)
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
        return dict(dt=self.dt, mass=self.mass, zeta=self.zeta, kT=self.kT,
                    controlled=self.controlled)
