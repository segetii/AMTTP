"""§XVIII Collapse-time prediction — analytical escape time.

τ_lin  = (e* − e_t) / ė_t
τ_quad = (-ė + √(ė² + 2 ë (e* − e))) / ë
τ_safe = τ_lin − 1/(α + λ_max(L))         — collapse horizon

e_t comes from §VI; ė_t from §XXV  V̇ ≈ ⟨g, F⟩(1 − γ*).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .control import MasterOperator
from .lyapunov import LyapunovCertificate
from .state import Snapshot


@dataclass
class EscapeTime:
    op: MasterOperator
    lyap: LyapunovCertificate

    def linear(self, snap: Snapshot, e_star: float) -> float:
        e = self.op.damp.e_BSDT(snap)
        edot = self.lyap.dV_dt(snap)
        if edot <= 0:
            return float("inf")
        return (e_star - e) / edot

    def quadratic(self, snap: Snapshot, e_star: float, dt: float = 1e-2) -> float:
        e = self.op.damp.e_BSDT(snap)
        edot = self.lyap.dV_dt(snap)
        # finite-diff ë via small forward step
        next_snap = self.op.integrate(snap, dt=dt, steps=1)
        edot_next = self.lyap.dV_dt(next_snap)
        eddot = (edot_next - edot) / dt
        disc = edot * edot + 2.0 * eddot * (e_star - e)
        if disc < 0 or eddot == 0:
            return self.linear(snap, e_star)
        return (-edot + float(np.sqrt(disc))) / eddot

    def safe_horizon(self, snap: Snapshot, e_star: float) -> float:
        D = snap.distance_matrix()
        K = self.op.forces.kernel(D)
        L = self.op.forces.laplacian(K)
        try:
            lam_L = float(np.linalg.eigvalsh(L)[-1])
        except np.linalg.LinAlgError:
            n = L.shape[0]
            try:
                lam_L = float(np.linalg.eigvalsh(L + 1e-8 * np.eye(n))[-1])
            except np.linalg.LinAlgError:
                lam_L = float(np.linalg.norm(L, ord='fro'))
        relax = 1.0 / (self.op.potential.alpha + max(lam_L, 1e-12))
        return self.linear(snap, e_star) - relax
