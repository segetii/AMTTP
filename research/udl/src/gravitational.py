"""
Gravitational Cluster Transform
================================
Two gravitational approaches that pull data points toward their
class centroids (and repel from the opposing class), widening the
decision gap before classification.

Approach C — GravitationalTransform  (fixed field, before QDA)
  Learns class centroids during fit(). At transform time, uses
  known labels (train) or a two-pass strategy (inference) to apply:
    attract:  x' += α · (μ_own - x) / ||x - μ_own||^β
    repel:    x' -= γ · (μ_other - x) / ||x - μ_other||^(β+1)

Approach A — TwoPassGravity  (soft-probability weighted)
  Pass 1: Get QDA soft probabilities.
  Pass 2: Pull each point toward both centroids, weighted by
          probability.  Re-classify on warped space.

Both operate on the magnified (post-DimensionMagnifier) representation
so the pipeline becomes:
  Raw → Stack → Centroid → Tensor → Magnify → **Gravitate** → QDA
"""

import numpy as np
from sklearn.preprocessing import StandardScaler


class GravitationalTransform:
    """
    Approach C — Dual-force gravitational field.

    During fit(), learns per-class centroids and spread (σ).
    During transform(), warps points with attraction + repulsion.

    Parameters
    ----------
    alpha : float
        Attraction strength toward own-class centroid.
    gamma : float
        Repulsion strength from opposing-class centroid.
    beta : float
        Distance decay exponent for attraction.
        β=0 → constant pull (all same), β=1 → linear (like spring),
        β=2 → inverse-square (gravity).
    n_iterations : int
        Number of iterative warp passes (1 is usually fine,
        2+ for stronger separation).
    normalize : bool
        Whether to re-standardise after warping so QDA sees
        well-scaled features.
    """

    def __init__(self, alpha=0.3, gamma=0.1, beta=1.0,
                 n_iterations=1, normalize=True):
        self.alpha = alpha
        self.gamma = gamma
        self.beta = beta
        self.n_iterations = n_iterations
        self.normalize = normalize

        self.mu_0_ = None          # normal centroid
        self.mu_1_ = None          # anomaly centroid
        self.sigma_0_ = None       # normal spread (per-dim std)
        self.sigma_1_ = None       # anomaly spread
        self._scaler = None
        self._fitted = False

    def fit(self, R, y):
        """
        Learn class centroids and spreads from labelled training data.

        Parameters
        ----------
        R : ndarray (N, D) — post-magnification representation
        y : ndarray (N,) — binary labels {0, 1}
        """
        mask_0 = (y == 0)
        mask_1 = (y == 1)

        self.mu_0_ = R[mask_0].mean(axis=0)
        self.mu_1_ = R[mask_1].mean(axis=0)
        self.sigma_0_ = R[mask_0].std(axis=0) + 1e-8
        self.sigma_1_ = R[mask_1].std(axis=0) + 1e-8

        self._fitted = True
        return self

    def transform(self, R, y=None):
        """
        Apply gravitational warp.

        Parameters
        ----------
        R : ndarray (N, D)
        y : ndarray (N,) or None
            If provided (training), uses true labels for pull direction.
            If None (inference), uses nearest-centroid assignment.

        Returns
        -------
        R_warped : ndarray (N, D)
        """
        if not self._fitted:
            raise RuntimeError("Call fit() first")

        R_w = R.copy().astype(np.float64)

        for _ in range(self.n_iterations):
            # Determine class assignment for each point
            if y is not None:
                labels = y.astype(int)
            else:
                # Nearest-centroid assignment (Mahalanobis-like)
                d0 = np.linalg.norm((R_w - self.mu_0_) / self.sigma_0_, axis=1)
                d1 = np.linalg.norm((R_w - self.mu_1_) / self.sigma_1_, axis=1)
                labels = (d1 < d0).astype(int)

            for i in range(len(R_w)):
                if labels[i] == 1:
                    mu_own, mu_other = self.mu_1_, self.mu_0_
                else:
                    mu_own, mu_other = self.mu_0_, self.mu_1_

                # ── Attraction: pull toward own centroid ──
                delta_own = mu_own - R_w[i]
                dist_own = np.linalg.norm(delta_own) + 1e-10
                direction_own = delta_own / dist_own
                # Closer points get weaker pull (already near centre)
                pull = self.alpha * (dist_own ** self.beta) / (1.0 + dist_own ** self.beta)
                R_w[i] += pull * direction_own

                # ── Repulsion: push away from opposing centroid ──
                delta_other = mu_other - R_w[i]
                dist_other = np.linalg.norm(delta_other) + 1e-10
                direction_other = delta_other / dist_other
                # Inverse-square: strong when close to wrong class
                repel = self.gamma / (dist_other ** (self.beta + 1) + 1e-6)
                # Cap repulsion to avoid explosion
                repel = min(repel, 2.0 * self.alpha)
                R_w[i] -= repel * direction_other

        # Optional normalisation
        if self.normalize:
            self._scaler = StandardScaler()
            R_w = self._scaler.fit_transform(R_w)

        return R_w

    def fit_transform(self, R, y):
        """Fit and transform in one call."""
        self.fit(R, y)
        return self.transform(R, y=y)


class GravitationalTransformVec:
    """
    Vectorised version of GravitationalTransform — same physics,
    but operates on entire arrays at once (much faster).

    Parameters
    ----------
    alpha : float
        Attraction strength toward own-class centroid.
    gamma : float
        Repulsion strength from opposing-class centroid.
    beta : float
        Distance decay exponent. 1.0 = linear spring, 0.5 = sqrt.
    n_iterations : int
        Number of iterative warp passes.
    normalize : bool
        Re-standardise output features.
    """

    def __init__(self, alpha=0.3, gamma=0.1, beta=1.0,
                 n_iterations=1, normalize=True):
        self.alpha = alpha
        self.gamma = gamma
        self.beta = beta
        self.n_iterations = n_iterations
        self.normalize = normalize

        self.mu_0_ = None
        self.mu_1_ = None
        self.sigma_0_ = None
        self.sigma_1_ = None
        self._scaler = None
        self._fitted = False

    def fit(self, R, y):
        """Learn class centroids and spreads."""
        mask_0 = (y == 0)
        mask_1 = (y == 1)
        self.mu_0_ = R[mask_0].mean(axis=0)
        self.mu_1_ = R[mask_1].mean(axis=0)
        self.sigma_0_ = R[mask_0].std(axis=0) + 1e-8
        self.sigma_1_ = R[mask_1].std(axis=0) + 1e-8
        self._fitted = True
        return self

    def transform(self, R, y=None):
        """
        Vectorised gravitational warp.

        Parameters
        ----------
        R : ndarray (N, D)
        y : ndarray or None — true labels (train) or None (inference)
        """
        if not self._fitted:
            raise RuntimeError("Call fit() first")

        R_w = R.copy().astype(np.float64)

        for _ in range(self.n_iterations):
            # ── Assign classes ──
            if y is not None:
                labels = y.astype(int)
            else:
                d0 = np.linalg.norm((R_w - self.mu_0_) / self.sigma_0_, axis=1)
                d1 = np.linalg.norm((R_w - self.mu_1_) / self.sigma_1_, axis=1)
                labels = (d1 < d0).astype(int)

            mask_1 = (labels == 1)
            mask_0 = ~mask_1

            # ── Anomaly class: attract → mu_1, repel ← mu_0 ──
            if mask_1.any():
                R_w[mask_1] = self._warp_group(
                    R_w[mask_1], mu_own=self.mu_1_, mu_other=self.mu_0_
                )

            # ── Normal class: attract → mu_0, repel ← mu_1 ──
            if mask_0.any():
                R_w[mask_0] = self._warp_group(
                    R_w[mask_0], mu_own=self.mu_0_, mu_other=self.mu_1_
                )

        if self.normalize:
            self._scaler = StandardScaler()
            R_w = self._scaler.fit_transform(R_w)

        return R_w

    def _warp_group(self, X, mu_own, mu_other):
        """Apply attraction + repulsion to a group of same-class points."""
        # Attraction toward own centroid
        delta_own = mu_own - X                          # (n, D)
        dist_own = np.linalg.norm(delta_own, axis=1, keepdims=True) + 1e-10
        direction_own = delta_own / dist_own
        pull = self.alpha * (dist_own ** self.beta) / (1.0 + dist_own ** self.beta)
        X_new = X + pull * direction_own

        # Repulsion from opposing centroid
        delta_other = mu_other - X_new                  # (n, D)
        dist_other = np.linalg.norm(delta_other, axis=1, keepdims=True) + 1e-10
        direction_other = delta_other / dist_other
        repel = self.gamma / (dist_other ** (self.beta + 1) + 1e-6)
        repel = np.minimum(repel, 2.0 * self.alpha)     # cap
        X_new = X_new - repel * direction_other

        return X_new

    def fit_transform(self, R, y):
        self.fit(R, y)
        return self.transform(R, y=y)


class TwoPassGravity:
    """
    Approach A — Two-pass soft-probability gravitational pull.

    Pass 1:  Fit QDA, get P(anomaly|x) for each point.
    Pass 2:  Warp each point toward BOTH centroids, weighted by
             probability.  Points strongly classified get pulled hard
             toward their class; borderline points get mild tug from
             both sides — whichever wins slightly creates a cascade.
    Pass 3:  Re-fit QDA on warped data, re-classify.

    The warp equation:
      x' = x + strength * [P1 * (μ1 - x)/||·|| + P0 * (μ0 - x)/||·||]

    Because P1 + P0 = 1, this is a probability-weighted interpolation
    of the two gravitational pulls.

    Parameters
    ----------
    strength : float
        Overall pull magnitude (0.1–0.5 is typical).
    n_passes : int
        Number of warp→re-classify iterations (2–3 is typical).
    normalize : bool
        Re-standardise after warping.
    """

    def __init__(self, strength=0.3, n_passes=2, normalize=True):
        self.strength = strength
        self.n_passes = n_passes
        self.normalize = normalize

        self.mu_0_ = None
        self.mu_1_ = None
        self._qda = None
        self._scaler = None
        self._fitted = False

    def fit(self, R, y, qda_reg=1e-4):
        """
        Fit the two-pass gravitational system.

        Parameters
        ----------
        R : ndarray (N, D) — post-magnification representation
        y : ndarray (N,) — binary labels
        qda_reg : float — QDA regularisation
        """
        from sklearn.discriminant_analysis import QuadraticDiscriminantAnalysis

        self.mu_0_ = R[y == 0].mean(axis=0)
        self.mu_1_ = R[y == 1].mean(axis=0)

        R_w = R.copy().astype(np.float64)

        for pass_i in range(self.n_passes):
            # Fit QDA on current representation
            qda = QuadraticDiscriminantAnalysis(reg_param=qda_reg)
            qda.fit(R_w, y)

            # Get soft probabilities
            probs_1 = qda.predict_proba(R_w)[:, 1]  # P(anomaly)
            probs_0 = 1.0 - probs_1                  # P(normal)

            # Apply soft gravitational pull
            R_w = self._soft_warp(R_w, probs_0, probs_1)

            # Update centroids in warped space
            self.mu_0_ = R_w[y == 0].mean(axis=0)
            self.mu_1_ = R_w[y == 1].mean(axis=0)

        # Final QDA on fully warped space
        if self.normalize:
            self._scaler = StandardScaler()
            R_w = self._scaler.fit_transform(R_w)
            self.mu_0_ = R_w[y == 0].mean(axis=0)
            self.mu_1_ = R_w[y == 1].mean(axis=0)

        self._qda = QuadraticDiscriminantAnalysis(reg_param=qda_reg)
        self._qda.fit(R_w, y)

        self._R_train_warped = R_w
        self._y_train = y
        self._fitted = True
        return self

    def _soft_warp(self, R, probs_0, probs_1):
        """Probability-weighted gravitational pull."""
        R_w = R.copy()

        # Direction + distance to normal centroid
        delta_0 = self.mu_0_ - R                  # (N, D)
        dist_0 = np.linalg.norm(delta_0, axis=1, keepdims=True) + 1e-10
        dir_0 = delta_0 / dist_0

        # Direction + distance to anomaly centroid
        delta_1 = self.mu_1_ - R                  # (N, D)
        dist_1 = np.linalg.norm(delta_1, axis=1, keepdims=True) + 1e-10
        dir_1 = delta_1 / dist_1

        # Weighted pull
        p0 = probs_0.reshape(-1, 1)
        p1 = probs_1.reshape(-1, 1)

        # Pull proportional to probability × distance-decay
        pull_0 = p0 * dir_0 * np.minimum(dist_0, 1.0)   # capped
        pull_1 = p1 * dir_1 * np.minimum(dist_1, 1.0)

        R_w += self.strength * (pull_0 + pull_1)
        return R_w

    def transform(self, R):
        """Transform test data through the same gravitational field."""
        if not self._fitted:
            raise RuntimeError("Call fit() first")

        R_w = R.copy().astype(np.float64)

        # Apply same soft warp using QDA probabilities
        for _ in range(self.n_passes):
            probs_1 = self._qda.predict_proba(R_w)[:, 1]
            probs_0 = 1.0 - probs_1
            R_w = self._soft_warp(R_w, probs_0, probs_1)

        if self.normalize and self._scaler is not None:
            R_w = self._scaler.transform(R_w)

        return R_w

    def predict_proba(self, R):
        """Get anomaly probabilities on (optionally warped) data."""
        R_w = self.transform(R)
        return self._qda.predict_proba(R_w)[:, 1]

    def predict(self, R, threshold=0.5):
        """Binary predictions."""
        return (self.predict_proba(R) >= threshold).astype(int)

    def fit_transform(self, R, y, qda_reg=1e-4):
        self.fit(R, y, qda_reg=qda_reg)
        return self._R_train_warped
