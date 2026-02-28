"""
mfls_variants.py — MFLS Scoring Variants for Stability Pipeline
=================================================================

Implements 4 MFLS scoring strategies from the UDL/BSDT framework,
adapted for macro stability analysis on BSDT channel scores.

Variants
--------
1. Baseline (Mahalanobis gradient norm) — the v2 pipeline's original
2. Full BSDT  — uniform-weighted 4-channel sum (no learned weights)
3. QuadSurf   — degree-2 polynomial on channel magnitudes + ridge
4. Signed LR  — logistic regression on channel scores
5. Expo Gate  — quadratic + tanh saturation + sigmoid gating

Variants 3-5 are supervised: they need crisis labels for training.
Crisis labels are derived from NBER recession dates + FDIC problem-bank
spikes (objective, published data — no researcher judgment).

Reference
---------
Odeyemi O.I., "Blind Spot Decomposition Theory", 2025.
UDL mfls_weighting.py — QuadSurf, logistic, quadratic_smooth methods.
"""

from __future__ import annotations
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Crisis labels (objective, from NBER + FDIC published dates)
# ─────────────────────────────────────────────────────────────────────────────

# NBER recession quarters + banking stress periods
CRISIS_QUARTERS = {
    # S&L tail (1990-1991 recession)
    "1990-06-30", "1990-09-30", "1990-12-31", "1991-03-31",
    # GFC (Dec 2007 – Jun 2009)
    "2007-12-31", "2008-03-31", "2008-06-30", "2008-09-30",
    "2008-12-31", "2009-03-31", "2009-06-30",
    # COVID (Feb–Apr 2020)
    "2020-03-31", "2020-06-30",
}


def make_crisis_labels(dates, crisis_quarters=CRISIS_QUARTERS):
    """
    Binary labels: 1 = crisis quarter, 0 = normal.
    Uses NBER recession dates — objective, published, no researcher choice.
    """
    y = np.zeros(len(dates), dtype=int)
    for i, d in enumerate(dates):
        ds = str(d.date()) if hasattr(d, "date") else str(d)
        if ds in crisis_quarters:
            y[i] = 1
    return y


# ─────────────────────────────────────────────────────────────────────────────
# Variant 1: Baseline (Mahalanobis gradient norm) — for comparison
# ─────────────────────────────────────────────────────────────────────────────

class MFLSBaseline:
    """MFLS = ||∇E_BS||_F = ||2 Σ₀⁻¹ (X - μ₀)||_F  (current pipeline)."""

    name = "Baseline (Mahalanobis)"

    def __init__(self):
        self.mu0_ = None
        self.Sigma0_inv_ = None

    def fit(self, X_normal: np.ndarray, y=None):
        Xf = X_normal.reshape(-1, X_normal.shape[-1])
        self.mu0_ = Xf.mean(axis=0)
        cov = np.cov(Xf.T) + 1e-6 * np.eye(Xf.shape[1])
        self.Sigma0_inv_ = np.linalg.inv(cov)
        return self

    def score_series(self, X_series: np.ndarray) -> np.ndarray:
        """Score each time step. Returns (T,)."""
        T = X_series.shape[0]
        scores = np.zeros(T)
        for t in range(T):
            z = X_series[t] - self.mu0_
            G = 2.0 * (z @ self.Sigma0_inv_.T)
            scores[t] = float(np.linalg.norm(G))
        return scores


# ─────────────────────────────────────────────────────────────────────────────
# Variant 2: Full BSDT (uniform-weighted 4-channel)
# ─────────────────────────────────────────────────────────────────────────────

class MFLSFullBSDT:
    """
    MFLS = Σ_k δ_k(X)  with uniform weights.
    No learned parameters — purely structural decomposition.
    """

    name = "Full BSDT (4-channel uniform)"

    def fit(self, channels_train: np.ndarray, y=None):
        """No fitting needed — uniform weights."""
        return self

    def score(self, channels: np.ndarray) -> np.ndarray:
        """
        channels : (T, 4) — the four BSDT operator scores
        Returns  : (T,)
        """
        # Normalise each channel to [0, 1] then sum
        normed = np.zeros_like(channels)
        for k in range(channels.shape[1]):
            col = channels[:, k]
            cmin, cmax = col.min(), col.max()
            if cmax - cmin > 1e-10:
                normed[:, k] = (col - cmin) / (cmax - cmin)
        return normed.sum(axis=1)


# ─────────────────────────────────────────────────────────────────────────────
# Variant 3: QuadSurf (F2_QuadSurf from UDL)
# ─────────────────────────────────────────────────────────────────────────────

class MFLSQuadSurf:
    """
    QuadSurf: degree-2 polynomial features on BSDT channels + ridge regression.

    From UDL mfls_weighting.py — the champion variant (+43% F1, -88% FP).
    Learns which channel interactions and squared terms matter for crisis
    detection.  Ridge regularisation prevents overfitting on sparse crisis labels.

    Score = β₀ + Σ_k β_k·c_k + Σ_{k≤j} β_{kj}·c_k·c_j
    """

    name = "QuadSurf (polynomial ridge)"

    def __init__(self, ridge_alpha: float = 1.0):
        self.ridge_alpha = ridge_alpha
        self.beta_ = None
        self.channel_means_ = None
        self.channel_stds_ = None

    def _poly_features(self, C: np.ndarray) -> np.ndarray:
        """Expand (T, K) → (T, 1 + K + K*(K+1)/2) with bias, linear, quadratic."""
        T, K = C.shape
        features = [np.ones((T, 1))]   # bias
        features.append(C)              # linear terms

        # Quadratic: c_k * c_j for k <= j
        for k in range(K):
            for j in range(k, K):
                features.append((C[:, k] * C[:, j]).reshape(-1, 1))

        return np.hstack(features)

    def fit(self, channels_train: np.ndarray, y: np.ndarray):
        """
        channels_train : (T_train, 4)
        y              : (T_train,) binary crisis labels
        """
        # Standardise channels
        self.channel_means_ = channels_train.mean(axis=0)
        self.channel_stds_ = channels_train.std(axis=0) + 1e-10
        C_std = (channels_train - self.channel_means_) / self.channel_stds_

        # Polynomial features
        Phi = self._poly_features(C_std)

        # Ridge regression: β = (Φᵀ Φ + αI)⁻¹ Φᵀ y
        n_feat = Phi.shape[1]
        I = np.eye(n_feat)
        I[0, 0] = 0  # don't regularise bias
        self.beta_ = np.linalg.solve(
            Phi.T @ Phi + self.ridge_alpha * I,
            Phi.T @ y.astype(float)
        )
        return self

    def score(self, channels: np.ndarray) -> np.ndarray:
        """channels : (T, 4) → scores : (T,)"""
        C_std = (channels - self.channel_means_) / self.channel_stds_
        Phi = self._poly_features(C_std)
        raw = Phi @ self.beta_
        # Clip and rescale to [0, ∞)
        return np.maximum(raw, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Variant 4: Signed LR (logistic regression)
# ─────────────────────────────────────────────────────────────────────────────

class MFLSSignedLR:
    """
    Logistic regression on BSDT channel scores.
    Learns optimal linear projection for crisis probability.

    P(crisis | c₁,...,c₄) = σ(β₀ + Σ_k β_k·c_k)
    """

    name = "Signed LR (logistic)"

    def __init__(self, lr: float = 0.1, n_iter: int = 500, reg: float = 0.01):
        self.lr = lr
        self.n_iter = n_iter
        self.reg = reg
        self.beta_ = None
        self.channel_means_ = None
        self.channel_stds_ = None

    def _sigmoid(self, z):
        return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))

    def fit(self, channels_train: np.ndarray, y: np.ndarray):
        """Fit logistic regression via gradient descent."""
        self.channel_means_ = channels_train.mean(axis=0)
        self.channel_stds_ = channels_train.std(axis=0) + 1e-10
        C_std = (channels_train - self.channel_means_) / self.channel_stds_

        # Add bias column
        T, K = C_std.shape
        X = np.hstack([np.ones((T, 1)), C_std])
        self.beta_ = np.zeros(K + 1)
        y_f = y.astype(float)

        # Handle class imbalance: weight crisis samples higher
        n_pos = max(y_f.sum(), 1)
        n_neg = max(len(y_f) - n_pos, 1)
        w = np.where(y_f == 1, n_neg / n_pos, 1.0)

        for _ in range(self.n_iter):
            p = self._sigmoid(X @ self.beta_)
            grad = X.T @ (w * (p - y_f)) / T + self.reg * self.beta_
            grad[0] -= self.reg * self.beta_[0]  # no reg on bias
            self.beta_ -= self.lr * grad

        return self

    def score(self, channels: np.ndarray) -> np.ndarray:
        """channels : (T, 4) → P(crisis) : (T,)"""
        C_std = (channels - self.channel_means_) / self.channel_stds_
        X = np.hstack([np.ones((len(C_std), 1)), C_std])
        return self._sigmoid(X @ self.beta_)


# ─────────────────────────────────────────────────────────────────────────────
# Variant 5: Expo Gate (quadratic + tanh saturation)
# ─────────────────────────────────────────────────────────────────────────────

class MFLSExpoGate:
    """
    Quadratic + tanh saturation + sigmoid gating.

    From UDL 'quadratic_smooth' — prevents false alarm inflation by
    capping extreme scores with tanh, then gating through sigmoid
    to produce calibrated probabilities.

    raw  = QuadSurf polynomial output
    sat  = tanh(raw / σ)          — saturation
    gate = sigmoid(sat * scale)   — probability calibration
    """

    name = "Expo Gate (quad+tanh+sigmoid)"

    def __init__(self, ridge_alpha: float = 1.0, smooth_sigma: float = 1.0,
                 gate_scale: float = 3.0):
        self.ridge_alpha = ridge_alpha
        self.smooth_sigma = smooth_sigma
        self.gate_scale = gate_scale
        self._quad = MFLSQuadSurf(ridge_alpha=ridge_alpha)

    def fit(self, channels_train: np.ndarray, y: np.ndarray):
        self._quad.fit(channels_train, y)
        return self

    def score(self, channels: np.ndarray) -> np.ndarray:
        """channels : (T, 4) → gated scores : (T,)"""
        raw = self._quad.score(channels)
        # Tanh saturation
        sat = np.tanh(raw / (self.smooth_sigma + 1e-10))
        # Sigmoid gate
        return 1.0 / (1.0 + np.exp(-self.gate_scale * sat))


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

ALL_VARIANTS = {
    "baseline":   MFLSBaseline,
    "full_bsdt":  MFLSFullBSDT,
    "quadsurf":   MFLSQuadSurf,
    "signed_lr":  MFLSSignedLR,
    "expo_gate":  MFLSExpoGate,
}
