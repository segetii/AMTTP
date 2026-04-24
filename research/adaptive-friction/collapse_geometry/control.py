"""§XIII + §XV  Master Operator — the single equation governing controlled dynamics.

    Ẋ_t = F_t  −  γ*_t · ⟨F_t, u_t⟩ · u_t

where u_t is the *state-space* unit collapse direction (§XXIV.2):

    u_state_t = G̃_t / ||G̃_t||_F

This is the corrected form (the older code projected onto channel-space u, which
only equals u_state when ψ_t = 0 — pure δ_C regime).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .state import CalibrationState, Snapshot
from .potential import Potential
from .forces import ForceField
from .bsdt import BSDT
from .unified_energy import UnifiedEnergy
from .mfls import MFLS
from .damping import AdaptiveDamping


@dataclass
class MasterOperator:
    cal: CalibrationState
    potential: Potential
    forces: ForceField
    bsdt: BSDT
    energy: UnifiedEnergy
    mfls: MFLS
    damp: AdaptiveDamping

    # ── one-shot constructor from normal-period panel ───────────────
    @classmethod
    def calibrate(cls, X_normal: np.ndarray, *,
                  k: int = 4, theta: float = 1.0,
                  potential: Potential | None = None,
                  energy: UnifiedEnergy | None = None,
                  F_max: float = 100.0) -> "MasterOperator":
        cal = CalibrationState.fit(X_normal, k=k)
        pot = potential or Potential()
        fld = ForceField(pot=pot, F_max=F_max)
        ue  = energy or UnifiedEnergy.pure_mahalanobis()
        b   = BSDT(cal=cal)
        m   = MFLS(bsdt=b, energy=ue)
        d   = AdaptiveDamping(cal=cal, theta=theta)
        return cls(cal, pot, fld, b, ue, m, d)

    # ── core: free force, control direction, parallel/perpendicular ─
    def force(self, snap: Snapshot) -> np.ndarray:
        D = snap.distance_matrix()
        return self.forces.force(snap.X, self.cal.mu0, D)

    def collapse_direction_state(self, snap: Snapshot) -> np.ndarray:
        Gt = self.mfls.state_pullback(snap)
        n = np.linalg.norm(Gt, "fro")
        return Gt / n if n > 1e-12 else np.zeros_like(Gt)

    def decompose(self, F: np.ndarray, u: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        proj = float((F * u).sum())   # ⟨F, u⟩ on (N,d) tensors
        F_par = proj * u
        F_per = F - F_par
        return F_par, F_per, proj

    # ── master equation (§XV master operator) ───────────────────────
    def step(self, snap: Snapshot) -> np.ndarray:
        """Return Ẋ_t — the controlled state-space velocity."""
        F = self.force(snap)
        u = self.collapse_direction_state(snap)
        F_par, F_per, proj = self.decompose(F, u)
        gamma = self.damp.gamma_star(snap)
        return F_per + (1.0 - gamma) * F_par   # equivalently F − γ ⟨F,u⟩ u

    def integrate(self, snap: Snapshot, dt: float = 1.0,
                  steps: int = 1) -> Snapshot:
        """Forward-Euler integration of the master operator."""
        s = snap
        for _ in range(steps):
            dXdt = self.step(s)
            X_new = s.X + dt * dXdt
            s = Snapshot(X=X_new, X_prev=s.X, history=s.history)
        return s
