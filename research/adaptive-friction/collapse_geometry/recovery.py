"""§XXII Recovery dynamics & hysteresis.

Equilibria: F(X*) = 0 ⇔ -α(X* - 1μᵀ) = L X*
Critical coupling for multiple equilibria:
    γ_crit = α σ √π / 2 · 1 / max_i Σ_{j≠i} exp(-D*²_ij / σ²)
Recovery operator (sign-reversed control):
    Ẋ_rec = F + γ_rec ⟨F, u_rec⟩ u_rec    with u_rec = -u (toward normal basin)
"""
from __future__ import annotations
from dataclasses import dataclass
from math import pi, sqrt
import numpy as np
from .control import MasterOperator
from .state import Snapshot


@dataclass
class RecoveryDynamics:
    op: MasterOperator

    def gamma_critical(self, snap: Snapshot) -> float:
        D = snap.distance_matrix()
        N = D.shape[0]
        mask = ~np.eye(N, dtype=bool)
        gauss = np.exp(-(D ** 2) / self.op.potential.sigma ** 2)
        gauss[~mask] = 0.0
        denom = max(gauss.sum(axis=1).max(), 1e-12)
        return float(self.op.potential.alpha * self.op.potential.sigma * sqrt(pi) / 2.0 / denom)

    def has_crisis_equilibria(self, snap: Snapshot) -> bool:
        return self.op.potential.gamma > self.gamma_critical(snap)

    def recover_step(self, snap: Snapshot, gamma_rec: float = 1.0) -> np.ndarray:
        F = self.op.force(snap)
        u = -self.op.collapse_direction_state(snap)
        proj = float((F * u).sum())
        return F + gamma_rec * proj * u
