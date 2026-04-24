"""GravityEngine — first-order overdamped dynamics under the master operator.

This is the canonical engine: each agent moves along the controlled force field
with no inertia.  Direct realisation of §XV.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from ..control import MasterOperator
from ..state import Snapshot


@dataclass
class Gravity:
    op: MasterOperator
    dt: float = 1e-2
    controlled: bool = True

    def step(self, snap: Snapshot) -> Snapshot:
        if self.controlled:
            dXdt = self.op.step(snap)
        else:
            dXdt = self.op.force(snap)
        X_new = snap.X + self.dt * dXdt
        return Snapshot(X=X_new, X_prev=snap.X, history=snap.history)

    def trajectory(self, snap: Snapshot, T: int) -> np.ndarray:
        out = np.empty((T + 1, *snap.X.shape))
        out[0] = snap.X
        s = snap
        for t in range(T):
            s = self.step(s)
            out[t + 1] = s.X
        return out
