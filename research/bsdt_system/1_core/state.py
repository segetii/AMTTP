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
    I_minus_VVT: np.ndarray  # (d,d) precomputed I − V_k V_kᵀ  (perf: used by grad_delta_G)

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
        # robust to LAPACK convergence failures: try eigh → jitter → SVD on centered data
        try:
            w, V = np.linalg.eigh(Sigma0)
        except np.linalg.LinAlgError:
            try:
                w, V = np.linalg.eigh(Sigma0 + 1e-6 * np.eye(d))
            except np.linalg.LinAlgError:
                # SVD-based fallback: c = U S V^T  ⇒  Σ = V (S²/(T0 N)) V^T
                # SVD uses different LAPACK driver (gesdd) and is more numerically stable
                _, s, Vt = np.linalg.svd(c, full_matrices=False)
                V = Vt.T
                w = (s ** 2) / (T0 * N) + jitter
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
        I_minus_VVT = np.eye(d) - Vk @ Vk.T  # calibration-time constant; reused per snapshot
        return cls(mu0, Sigma0, Sigma0_inv, Sigma0_inv_sqrt, Vk, v0, w, I_minus_VVT)


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

    # ── per-snapshot memoization (perf: avoids recomputing shared intermediates) ──
    def memo(self, key, fn):
        """Return cached value for `key`, computing via `fn()` on first miss.

        Cache lives on self.__dict__['_cache'] so the dataclass __init__
        signature stays unchanged and a fresh Snapshot starts empty.
        """
        c = self.__dict__.get("_cache")
        if c is None:
            c = {}
            self.__dict__["_cache"] = c
        v = c.get(key)
        if v is None:
            v = fn()
            c[key] = v
        return v

    def centred(self, mu0: np.ndarray) -> np.ndarray:
        return self.memo(("centred", id(mu0)), lambda: self.X - mu0)

    def distance_matrix(self, eps: float = 1e-8) -> np.ndarray:
        """D_ij = ||x_i - x_j||  via D² = q1ᵀ + 1qᵀ - 2XXᵀ."""
        def _compute():
            X = self.X
            q = (X * X).sum(axis=1)
            D2 = q[:, None] + q[None, :] - 2.0 * (X @ X.T)
            np.fill_diagonal(D2, 0.0)
            return np.sqrt(np.clip(D2, 0.0, None) + eps) - np.sqrt(eps)
        return self.memo(("D", eps), _compute)
