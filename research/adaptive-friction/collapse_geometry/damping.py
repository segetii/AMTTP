"""§VIII Optimal adaptive damping  γ*(X) = E_BSDT(X) / (E_BSDT(X) + θ).

E_BSDT here is the Mahalanobis sum  e_t = ||X̃ Σ⁻¹/² ||²_F  (§VI eq. ⑤).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .state import CalibrationState, Snapshot


@dataclass
class AdaptiveDamping:
    cal: CalibrationState
    theta: float = 1.0   # intervention cost

    def e_BSDT(self, snap: Snapshot) -> float:
        def _compute():
            Xt = snap.centred(self.cal.mu0) @ self.cal.Sigma0_inv_sqrt
            return float(np.linalg.norm(Xt, "fro") ** 2)
        return snap.memo("e_BSDT", _compute)

    def gamma_star(self, snap: Snapshot) -> float:
        def _compute():
            e = self.e_BSDT(snap)
            return e / (e + self.theta)
        return snap.memo("gamma_star", _compute)
