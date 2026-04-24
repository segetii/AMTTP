"""§XIV Collapse geometry — tan θ, three equivalent collapse conditions.

cos θ_state  = ⟨G̃, F⟩ / (||G̃|| ||F||)             (the right one for stability)
tan θ_true   = ||F_perp_true|| / ||F_par_true||
Three conditions at C_man:
    Spectral:  λ_max(∇²Φ) > 1
    Angular:   tan θ < tan θ*
    Energetic: λ_max(∇² E_BS) > MFLS²/e_t
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .control import MasterOperator
from .state import Snapshot


@dataclass
class CollapseGeometry:
    op: MasterOperator

    def _F_u(self, snap: Snapshot):
        F = self.op.force(snap)
        u = self.op.collapse_direction_state(snap)
        return F, u

    def cos_theta_state(self, snap: Snapshot) -> float:
        F, u = self._F_u(snap)
        nF = np.linalg.norm(F, "fro")
        return float((F * u).sum() / nF) if nF > 1e-12 else 0.0

    def tan_theta(self, snap: Snapshot) -> float:
        c = self.cos_theta_state(snap)
        c = float(np.clip(abs(c), 1e-12, 1.0))
        return float(np.sqrt(1.0 / (c * c) - 1.0))

    def tan_theta_star(self, snap: Snapshot) -> float:
        """Critical angle threshold (§XIV.4)."""
        F = self.op.force(snap)
        nF2 = float((F * F).sum())
        mfls = self.op.mfls.state_mfls(snap)
        gamma = self.op.damp.gamma_star(snap)
        x = nF2 - (mfls * gamma) ** 2
        if x <= 0 or mfls * gamma < 1e-12:
            return float("inf")
        return float(np.sqrt(x) / (mfls * gamma))

    # ── three equivalent conditions ─────────────────────────────
    def spectral_condition(self, snap: Snapshot) -> bool:
        D = snap.distance_matrix()
        return self.op.potential.lambda_max_bound(D) > 1.0

    def angular_condition(self, snap: Snapshot) -> bool:
        return self.tan_theta(snap) < self.tan_theta_star(snap)

    def energetic_condition(self, snap: Snapshot) -> bool:
        S = self.op.bsdt.channel_state(snap)
        lam = self.op.energy.lambda_max_bound(S)
        e = self.op.damp.e_BSDT(snap)
        mfls2 = self.op.mfls.state_mfls(snap) ** 2
        return lam * max(e, 1e-12) > mfls2

    def all_conditions(self, snap: Snapshot) -> dict[str, bool]:
        return dict(spectral=self.spectral_condition(snap),
                    angular=self.angular_condition(snap),
                    energetic=self.energetic_condition(snap))
