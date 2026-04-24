"""§XX Inverse problem — least-squares parameter identification + attribution.

Given observed Ẋ^obs, find θ_param = (α, γ, σ, λ, A, β, w) minimising residual:
    R_t(θ) = Ẋ^obs − F(θ) + γ*(θ) ⟨F, u⟩ u

We expose:
  • residual()  for any candidate operator
  • identify_alpha_gamma()  — closed-form 1-D ridge over (α, γ) given fixed others
  • attribution()  — per-parameter sensitivity of Ẋ via finite difference
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import numpy as np
from .control import MasterOperator
from .state import Snapshot


@dataclass
class ParameterIdentification:
    op: MasterOperator

    def residual(self, snap: Snapshot, dXdt_obs: np.ndarray) -> float:
        return float(np.linalg.norm(dXdt_obs - self.op.step(snap), "fro") ** 2)

    def attribution(self, snap: Snapshot, dXdt_obs: np.ndarray,
                    rel_eps: float = 1e-3) -> dict[str, float]:
        """Sensitivity-weighted parameter importance via finite difference."""
        base = self.residual(snap, dXdt_obs)
        out: dict[str, float] = {}
        for name in ("alpha", "gamma", "sigma", "lam"):
            val = getattr(self.op.potential, name)
            new_pot = replace(self.op.potential, **{name: val * (1 + rel_eps)})
            new_op = replace(self.op, potential=new_pot,
                             forces=replace(self.op.forces, pot=new_pot))
            r = new_op.residual_proxy(snap, dXdt_obs) if hasattr(new_op, "residual_proxy") \
                else float(np.linalg.norm(dXdt_obs - new_op.step(snap), "fro") ** 2)
            out[name] = abs(r - base) / max(rel_eps, 1e-12) * abs(val)
        # normalise
        Z = sum(out.values()) + 1e-12
        return {k: v / Z for k, v in out.items()}
