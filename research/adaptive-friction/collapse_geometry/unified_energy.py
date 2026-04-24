"""§XII Unified blind-spot energy = Quadsurf + Expogate + Signed LR.

Inputs: channel-state vector S = (δ_C, δ_G, δ_A, δ_T) ∈ R⁴.
Energies:
    Quadsurf : SᵀAS                          (curvature)
    Expogate : Σ_k exp(β_k S_k)              (threshold explosion)
    SignedLR : wᵀS                           (linear bias)
Gradient g = ∇_S E = 2AS + (β_k e^{β_k S_k})_k + w
Hessian  H = 2A + diag(β_k² e^{β_k S_k})
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass
class UnifiedEnergy:
    A: np.ndarray = field(default_factory=lambda: np.eye(4))     # (4,4) SPD
    beta: np.ndarray = field(default_factory=lambda: np.zeros(4))  # (4,)
    w: np.ndarray = field(default_factory=lambda: np.zeros(4))     # (4,)

    def __post_init__(self) -> None:
        self.A = 0.5 * (self.A + self.A.T)  # symmetrise

    # ── pieces
    def E_quad(self, S):  return float(S @ self.A @ S)
    def E_expo(self, S):  return float(np.exp(self.beta * S).sum())
    def E_lr(self, S):    return float(self.w @ S)
    def E_total(self, S): return self.E_quad(S) + self.E_expo(S) + self.E_lr(S)

    # ── gradient + hessian
    def grad(self, S: np.ndarray) -> np.ndarray:
        return 2.0 * self.A @ S + self.beta * np.exp(self.beta * S) + self.w

    def hessian(self, S: np.ndarray) -> np.ndarray:
        return 2.0 * self.A + np.diag(self.beta ** 2 * np.exp(self.beta * S))

    def lambda_max_bound(self, S: np.ndarray) -> float:
        """§XIV.5 closed-form bound on λ_max(∇² E_BS)."""
        lam_A = float(np.linalg.eigvalsh(self.A).max())
        explosion = float((self.beta ** 2 * np.exp(self.beta * S)).max(initial=0.0))
        return 2.0 * lam_A + explosion

    # §XII.4 unit collapse direction in channel space
    def unit_direction(self, S: np.ndarray) -> np.ndarray:
        g = self.grad(S)
        n = float(np.linalg.norm(g))
        return g / max(n, 1e-12)

    # §XII.5 per-channel collapse attribution  c_k = [g]_k² / ||g||²
    def channel_attribution(self, S: np.ndarray) -> np.ndarray:
        g = self.grad(S)
        g2 = g ** 2
        return g2 / max(g2.sum(), 1e-12)

    # §XII.5 dominant channel  k* = argmax_k c_k
    def dominant_channel(self, S: np.ndarray) -> int:
        return int(np.argmax(self.channel_attribution(S)))

    @classmethod
    def pure_mahalanobis(cls) -> "UnifiedEnergy":
        """§XII.6 reduction: A=I, β=0, w=0  → recovers original BSDT."""
        return cls(A=np.eye(4), beta=np.zeros(4), w=np.zeros(4))
