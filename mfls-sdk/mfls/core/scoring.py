"""
MFLS scoring variants.

Five independent scoring functions mapping BSDT channels to a scalar
detection signal:

  1. Baseline       — Mahalanobis gradient norm (unsupervised)
  2. FullBSDT       — 4-channel uniform sum (unsupervised)
  3. QuadSurf       — polynomial ridge regression (supervised)
  4. SignedLR       — logistic regression with class-weight rebalancing (supervised)
  5. ExpoGate       — quadratic + tanh + sigmoid gating (supervised)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Type

import numpy as np


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class VariantResult:
    """Result from scoring a single variant."""
    name: str
    signal: np.ndarray          # (T,)
    mode: str                   # "unsupervised" | "supervised"
    weights: Optional[Dict[str, float]] = None  # learned channel weights (if supervised)


# ---------------------------------------------------------------------------
# Variant base
# ---------------------------------------------------------------------------

class MFLSVariant:
    """Abstract base for MFLS scoring variants."""
    name: str = "base"
    mode: str = "unsupervised"

    def fit(self, channels_train: np.ndarray, y: Optional[np.ndarray] = None) -> "MFLSVariant":
        raise NotImplementedError

    def score(self, channels: np.ndarray) -> np.ndarray:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# 1. Baseline (Mahalanobis gradient norm)
# ---------------------------------------------------------------------------

class MFLSBaseline(MFLSVariant):
    """
    MFLS = ||grad E_bs(X)||_F  (Frobenius norm of the blind-spot energy gradient).

    Operates on raw (T, N, d) state matrices, not BSDT channels.
    """
    name = "Baseline (Mahalanobis)"
    mode = "unsupervised"

    def __init__(self):
        self.mu0_: Optional[np.ndarray] = None
        self.Sigma0_inv_: Optional[np.ndarray] = None

    def fit(self, X_normal: np.ndarray, y=None) -> "MFLSBaseline":
        """Fit on normal-period state matrices (T, N, d)."""
        flat = X_normal.reshape(-1, X_normal.shape[-1])
        self.mu0_ = flat.mean(axis=0)
        cov = np.cov(flat, rowvar=False)
        cov += 1e-8 * np.eye(cov.shape[0])
        self.Sigma0_inv_ = np.linalg.inv(cov)
        return self

    def score_series(self, X_series: np.ndarray) -> np.ndarray:
        """Score a full time series.  (T, N, d) → (T,)."""
        T = X_series.shape[0]
        out = np.empty(T)
        for t in range(T):
            grad = 2.0 * (X_series[t] - self.mu0_) @ self.Sigma0_inv_
            out[t] = np.linalg.norm(grad, "fro")
        return out

    def score(self, channels: np.ndarray) -> np.ndarray:
        """Not applicable for Baseline — use score_series instead."""
        raise TypeError("Baseline operates on (T,N,d) state matrices, not channels. Use score_series().")


# ---------------------------------------------------------------------------
# 2. Full BSDT (4-channel uniform sum)
# ---------------------------------------------------------------------------

class MFLSFullBSDT(MFLSVariant):
    """Sum of min-max normalised BSDT channels.  Unsupervised."""
    name = "Full BSDT (4-channel uniform)"
    mode = "unsupervised"

    def fit(self, channels_train: np.ndarray, y=None) -> "MFLSFullBSDT":
        """No-op — unsupervised, no parameters to learn."""
        return self

    def score(self, channels: np.ndarray) -> np.ndarray:
        """channels shape (T, 4) → (T,).  Min-max normalise then sum."""
        normed = np.zeros_like(channels)
        for k in range(channels.shape[1]):
            col = channels[:, k]
            lo, hi = col.min(), col.max()
            if hi - lo > 1e-12:
                normed[:, k] = (col - lo) / (hi - lo)
            else:
                normed[:, k] = 0.0
        return normed.sum(axis=1)


# ---------------------------------------------------------------------------
# 3. QuadSurf (polynomial ridge)
# ---------------------------------------------------------------------------

class MFLSQuadSurf(MFLSVariant):
    """Degree-2 polynomial features on channels + ridge regression."""
    name = "QuadSurf (polynomial ridge)"
    mode = "supervised"

    def __init__(self, ridge_alpha: float = 1.0):
        self.ridge_alpha = ridge_alpha
        self.beta_: Optional[np.ndarray] = None
        self.channel_means_: Optional[np.ndarray] = None
        self.channel_stds_: Optional[np.ndarray] = None

    @staticmethod
    def _poly_features(C: np.ndarray) -> np.ndarray:
        """(T, K) → (T, 1 + K + K*(K+1)/2)."""
        T, K = C.shape
        feats = [np.ones((T, 1)), C]
        for i in range(K):
            for j in range(i, K):
                feats.append((C[:, i] * C[:, j]).reshape(-1, 1))
        return np.hstack(feats)

    def fit(self, channels_train: np.ndarray, y: np.ndarray) -> "MFLSQuadSurf":
        self.channel_means_ = channels_train.mean(axis=0)
        self.channel_stds_ = channels_train.std(axis=0) + 1e-10
        C = (channels_train - self.channel_means_) / self.channel_stds_
        Phi = self._poly_features(C)
        A = Phi.T @ Phi + self.ridge_alpha * np.eye(Phi.shape[1])
        self.beta_ = np.linalg.solve(A, Phi.T @ y)
        return self

    def score(self, channels: np.ndarray) -> np.ndarray:
        C = (channels - self.channel_means_) / self.channel_stds_
        return np.maximum(0.0, self._poly_features(C) @ self.beta_)


# ---------------------------------------------------------------------------
# 4. SignedLR (logistic with class-weight rebalancing)
# ---------------------------------------------------------------------------

class MFLSSignedLR(MFLSVariant):
    """
    Logistic regression on BSDT channels with class-imbalanced weighting.

    The learned weights reveal channel importance — notably, a negative
    weight on delta_T indicates convergent herding before crises.
    """
    name = "Signed LR (logistic)"
    mode = "supervised"

    def __init__(self, lr: float = 0.1, n_iter: int = 500, reg: float = 0.01):
        self.lr = lr
        self.n_iter = n_iter
        self.reg = reg
        self.beta_: Optional[np.ndarray] = None
        self.channel_means_: Optional[np.ndarray] = None
        self.channel_stds_: Optional[np.ndarray] = None

    @staticmethod
    def _sigmoid(z: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))

    def fit(self, channels_train: np.ndarray, y: np.ndarray) -> "MFLSSignedLR":
        self.channel_means_ = channels_train.mean(axis=0)
        self.channel_stds_ = channels_train.std(axis=0) + 1e-10
        C = (channels_train - self.channel_means_) / self.channel_stds_
        T, K = C.shape

        # Class-weight rebalancing
        n_pos = max(y.sum(), 0.5)
        n_neg = max(T - n_pos, 0.5)
        w = np.where(y == 1, T / (2 * n_pos), T / (2 * n_neg))

        # Gradient descent
        beta = np.zeros(K + 1)
        C_bias = np.hstack([np.ones((T, 1)), C])
        for _ in range(self.n_iter):
            p = self._sigmoid(C_bias @ beta)
            grad = C_bias.T @ (w * (p - y)) / T + self.reg * beta
            beta -= self.lr * grad

        self.beta_ = beta
        return self

    def score(self, channels: np.ndarray) -> np.ndarray:
        C = (channels - self.channel_means_) / self.channel_stds_
        C_bias = np.hstack([np.ones((C.shape[0], 1)), C])
        return self._sigmoid(C_bias @ self.beta_)

    @property
    def channel_weights(self) -> Dict[str, float]:
        """Return learned channel weights as a dict."""
        if self.beta_ is None:
            return {}
        names = ["bias", "delta_C", "delta_G", "delta_A", "delta_T"]
        return {n: float(self.beta_[i]) for i, n in enumerate(names)}


# ---------------------------------------------------------------------------
# 5. ExpoGate (quad + tanh + sigmoid)
# ---------------------------------------------------------------------------

class MFLSExpoGate(MFLSVariant):
    """QuadSurf output capped by tanh saturation and sigmoid gating."""
    name = "Expo Gate (quad+tanh+sigmoid)"
    mode = "supervised"

    def __init__(self, ridge_alpha: float = 1.0, smooth_sigma: float = 1.0, gate_scale: float = 3.0):
        self.smooth_sigma = smooth_sigma
        self.gate_scale = gate_scale
        self._quad = MFLSQuadSurf(ridge_alpha=ridge_alpha)

    def fit(self, channels_train: np.ndarray, y: np.ndarray) -> "MFLSExpoGate":
        self._quad.fit(channels_train, y)
        return self

    def score(self, channels: np.ndarray) -> np.ndarray:
        raw = self._quad.score(channels)
        gated = np.tanh(raw / self.smooth_sigma)
        return 1.0 / (1.0 + np.exp(-self.gate_scale * gated))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_VARIANTS: Dict[str, Type[MFLSVariant]] = {
    "baseline": MFLSBaseline,
    "full_bsdt": MFLSFullBSDT,
    "quadsurf": MFLSQuadSurf,
    "signed_lr": MFLSSignedLR,
    "expo_gate": MFLSExpoGate,
}
