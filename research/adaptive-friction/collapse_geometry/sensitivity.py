"""§XXI Agent sensitivity — who pushes the system across the manifold?

S_i = ∂λ_max(∇²Φ) / ∂x_i  via Hadamard first variation
        = v_1ᵀ (∂∇²Φ/∂x_i) v_1   with v_1 the principal eigenvector.

We compute via finite-difference on the Gershgorin bound (closed-form proxy).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .control import MasterOperator
from .state import Snapshot


@dataclass
class AgentSensitivity:
    op: MasterOperator

    def importance(self, snap: Snapshot, eps: float = 1e-4) -> np.ndarray:
        """(N,) systemic-importance vector — each agent's effect on λ_max bound."""
        D0 = snap.distance_matrix()
        base = self.op.potential.lambda_max_bound(D0)
        N, d = snap.X.shape
        S = np.zeros(N)
        for i in range(N):
            grad = np.zeros(d)
            for j in range(d):
                Xp = snap.X.copy(); Xp[i, j] += eps
                Dp = Snapshot(X=Xp).distance_matrix()
                grad[j] = (self.op.potential.lambda_max_bound(Dp) - base) / eps
            S[i] = float(np.linalg.norm(grad))
        return S

    def normalised(self, snap: Snapshot) -> np.ndarray:
        S = self.importance(snap)
        Z = S.sum() + 1e-12
        return S / Z

    def critical_institution(self, snap: Snapshot) -> int:
        return int(np.argmax(self.importance(snap)))
