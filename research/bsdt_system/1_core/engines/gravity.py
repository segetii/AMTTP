"""GravityEngine — first-order overdamped controlled dynamics.

dt is data-derived from the GravityEngine's own force scale and the panel's
spatial scale.  Specifically:

    dt  =  ε_dt · σ_min / F_max

where σ_min is the 1st-percentile pairwise distance in the normal panel and
F_max is the gravity force clamp.  Each step moves each agent by at most
ε_dt · σ_min — well below the smallest agent-spacing, guaranteeing no
positional pathology.  ε_dt = 0.1 is the structural CFL constant
(10% of the smallest length per step).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from ..control import MasterOperator
from ..state import Snapshot


@dataclass
class Gravity:
    op: MasterOperator
    dt: float
    controlled: bool = True

    @classmethod
    def from_panel(cls, op: MasterOperator, panel: np.ndarray, *,
                   eps_dt: float = 0.1, controlled: bool = True) -> "Gravity":
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
        return cls(op=op, dt=dt, controlled=controlled)

    def step(self, snap: Snapshot) -> Snapshot:
        dXdt = self.op.step(snap) if self.controlled else self.op.force(snap)
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

    # ── §I–XXVII full diagnostics ─────────────────────────────────────────
    def diagnostics(self, snap: Snapshot) -> dict:
        """Per-snapshot §I–XXVII closed-form diagnostics (read-only)."""
        from .diagnostics import engine_diagnostics
        return engine_diagnostics(self.op, snap, V=None)

    def trajectory_with_diagnostics(self, snap: Snapshot, T: int) -> tuple:
        """Forward integrate AND record per-step diagnostics.

        Returns
        -------
        Xs    : (T+1, N, d) trajectory
        diags : list of length T+1 of diagnostic dicts (one per snapshot)
        """
        Xs = np.empty((T + 1, *snap.X.shape))
        Xs[0] = snap.X
        diags = [self.diagnostics(snap)]
        s = snap
        for t in range(T):
            s = self.step(s)
            Xs[t + 1] = s.X
            diags.append(self.diagnostics(s))
        return Xs, diags

    def report(self) -> dict:
        return dict(dt=self.dt, controlled=self.controlled)
