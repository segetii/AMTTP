"""MolecularEngine — second-order Langevin dynamics with thermal noise.

    M Ẍ = F_controlled − ζ Ẋ + √(2 ζ k_B T) ξ_t

where F_controlled comes from the master operator (§XV). Velocity-Verlet
integrator. Provides the *molecular dynamics* analogue of GravityEngine —
useful when inertia and temperature matter (financial liquidity buffers,
molecular folding analogue, neural net momentum).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from ..control import MasterOperator
from ..state import Snapshot


@dataclass
class Molecular:
    op: MasterOperator
    dt: float = 1e-2
    mass: float = 1.0
    zeta: float = 0.10           # friction (Langevin damping)
    kT: float = 1e-3             # thermal energy
    controlled: bool = True
    rng: np.random.Generator = None  # type: ignore

    def __post_init__(self):
        if self.rng is None:
            self.rng = np.random.default_rng(0)

    def _accel(self, snap: Snapshot, V: np.ndarray) -> np.ndarray:
        F = self.op.step(snap) if self.controlled else self.op.force(snap)
        noise_std = float(np.sqrt(2.0 * self.zeta * self.kT / self.dt))
        xi = self.rng.standard_normal(size=snap.X.shape)
        return (F - self.zeta * V + noise_std * xi) / self.mass

    def step(self, snap: Snapshot, V: np.ndarray) -> tuple[Snapshot, np.ndarray]:
        """Velocity-Verlet half-step."""
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
