"""§IV Restoring forces — closed-form Laplacian formulation.

K_ij = (1/D_ij)[ (2γ/√π) exp(-D²_ij/σ²) - λ/D_ij ]   (i ≠ j)
L = diag(K1) - K
F = -α(X - 1μᵀ) - L X
"""
from __future__ import annotations
from dataclasses import dataclass
from math import pi, sqrt
import numpy as np
from .potential import Potential


@dataclass
class ForceField:
    pot: Potential
    F_max: float = 100.0  # post-clamp magnitude (per row)

    def kernel(self, D: np.ndarray) -> np.ndarray:
        N = D.shape[0]
        d = D + self.pot.eps
        K = ((2.0 * self.pot.gamma / sqrt(pi)) * np.exp(-(D ** 2) / self.pot.sigma ** 2)
             - self.pot.lam / d) / d
        np.fill_diagonal(K, 0.0)
        return K

    def laplacian(self, K: np.ndarray) -> np.ndarray:
        return np.diag(K.sum(axis=1)) - K

    def force(self, X: np.ndarray, mu: np.ndarray, D: np.ndarray) -> np.ndarray:
        K = self.kernel(D)
        L = self.laplacian(K)
        F = -self.pot.alpha * (X - mu) - L @ X
        # row-wise clamp
        norms = np.linalg.norm(F, axis=1, keepdims=True)
        scale = np.minimum(1.0, self.F_max / np.clip(norms, 1e-12, None))
        return F * scale
