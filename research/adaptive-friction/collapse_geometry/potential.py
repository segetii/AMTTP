"""§III Potential energy landscape + §V Hessian bound (closed form).

Φ(X) = (α/2)||X - 1μᵀ||²_F + Σ_{i<j}[ -γσ erf(D_ij/σ) + λ ln(D_ij + ε) ]
"""
from __future__ import annotations
from dataclasses import dataclass
from math import pi, sqrt
import numpy as np
from scipy.special import erf  # type: ignore


@dataclass
class Potential:
    alpha: float = 0.10   # radial spring
    gamma: float = 1.00   # pairwise attraction amplitude
    sigma: float = 1.00   # attraction length-scale
    lam:   float = 0.10   # log repulsion
    eps:   float = 1e-5   # softening

    # ─── §III closed-form energies ──────────────────────────────────────
    def E_rad(self, X: np.ndarray, mu: np.ndarray) -> float:
        return 0.5 * self.alpha * float(np.linalg.norm(X - mu, "fro") ** 2)

    def E_pair(self, D: np.ndarray) -> float:
        """One Frobenius-style sum on the OFF-DIAGONAL of D."""
        N = D.shape[0]
        mask = ~np.eye(N, dtype=bool)
        d = D[mask] + self.eps
        return float(0.5 * (-self.gamma * self.sigma * erf(d / self.sigma).sum()
                            + self.lam * np.log(d).sum()))

    def E_total(self, X: np.ndarray, mu: np.ndarray, D: np.ndarray) -> float:
        return self.E_rad(X, mu) + self.E_pair(D)

    # ─── §V Gershgorin bound on λ_max(∇²Φ) — replaces power iteration ───
    def lambda_max_bound(self, D: np.ndarray) -> float:
        N = D.shape[0]
        mask = ~np.eye(N, dtype=bool)
        d = D + self.eps
        kernel = (2.0 * self.gamma / (sqrt(pi) * self.sigma)) * np.exp(-(D ** 2) / self.sigma ** 2) \
                 + self.lam / (d ** 2)
        kernel[~mask] = 0.0
        row_sum = kernel.sum(axis=1)
        return float(self.alpha + row_sum.max())

    def supercritical(self, D: np.ndarray) -> bool:
        return self.lambda_max_bound(D) > 1.0

    # ─── §V trajectory-level supercritical fraction p̂_SC ───────────────
    def supercritical_fraction(self, panel: np.ndarray) -> float:
        """p̂_SC = (1/T) Σ 𝟙[λ_max(t) > 1] over a (T, N, d) trajectory."""
        from .state import Snapshot
        T = panel.shape[0]
        hits = 0
        for t in range(T):
            D = Snapshot(X=panel[t]).distance_matrix()
            if self.supercritical(D):
                hits += 1
        return hits / T
