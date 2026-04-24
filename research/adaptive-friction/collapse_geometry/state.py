"""§I State space + calibration.

X_t ∈ R^{N×d}.  Calibration produces (μ0, Σ0, Σ0^{-1}, Σ0^{-1/2}, V_k, v0)
fitted ONCE on a normal-period panel of shape (T0, N, d).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class CalibrationState:
    mu0: np.ndarray          # (d,)
    Sigma0: np.ndarray       # (d,d)
    Sigma0_inv: np.ndarray   # (d,d)
    Sigma0_inv_sqrt: np.ndarray  # (d,d) symmetric square root of inverse
    Vk: np.ndarray           # (d,k) top-k PCA basis
    v0: float                # 95-percentile velocity
    eig_Sigma0: np.ndarray   # (d,) eigenvalues of Σ0  (for ellipsoid axes)

    @property
    def d(self) -> int: return int(self.mu0.shape[0])
    @property
    def k(self) -> int: return int(self.Vk.shape[1])

    @classmethod
    def fit(cls, X_normal: np.ndarray, k: int = 4, jitter: float = 1e-8) -> "CalibrationState":
        """X_normal: (T0, N, d). Returns global mean + pooled covariance."""
        T0, N, d = X_normal.shape
        flat = X_normal.reshape(T0 * N, d)
        mu0 = flat.mean(axis=0)
        c = flat - mu0
        Sigma0 = (c.T @ c) / (T0 * N) + jitter * np.eye(d)
        # eigendecomp once → both inverse, sqrt-inverse, PCA basis
        w, V = np.linalg.eigh(Sigma0)
        w = np.clip(w, jitter, None)
        order = np.argsort(w)[::-1]
        w, V = w[order], V[:, order]
        Sigma0_inv = (V / w) @ V.T
        Sigma0_inv_sqrt = (V / np.sqrt(w)) @ V.T
        kk = min(k, d)
        Vk = V[:, :kk]
        # velocity threshold: ||x_t^i - x_{t-1}^i||
        if T0 >= 2:
            diffs = np.linalg.norm(np.diff(X_normal, axis=0), axis=2).ravel()
            v0 = float(np.percentile(diffs, 95))
        else:
            v0 = 0.0
        return cls(mu0, Sigma0, Sigma0_inv, Sigma0_inv_sqrt, Vk, v0, w)


@dataclass
class Snapshot:
    """A single time-slice (X_t, optional X_{t-1}, optional history)."""
    X: np.ndarray                  # (N, d)
    X_prev: np.ndarray | None = None
    history: np.ndarray | None = None  # (H, N, d) for KDE

    @property
    def N(self) -> int: return int(self.X.shape[0])
    @property
    def d(self) -> int: return int(self.X.shape[1])

    def centred(self, mu0: np.ndarray) -> np.ndarray:
        return self.X - mu0  # broadcasts over rows

    def distance_matrix(self, eps: float = 1e-8) -> np.ndarray:
        """D_ij = ||x_i - x_j||  via D² = q1ᵀ + 1qᵀ - 2XXᵀ."""
        X = self.X
        q = (X * X).sum(axis=1)
        D2 = q[:, None] + q[None, :] - 2.0 * (X @ X.T)
        np.fill_diagonal(D2, 0.0)
        return np.sqrt(np.clip(D2, 0.0, None) + eps) - np.sqrt(eps)
