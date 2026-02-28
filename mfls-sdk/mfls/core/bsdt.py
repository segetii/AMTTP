"""
Blind-Spot Detection Theory (BSDT) operators.

Four complementary deviation channels calibrated on normal-period data:
  delta_C  –  Camouflage (Mahalanobis distance)
  delta_G  –  Feature Gap (PCA residual in low-variance directions)
  delta_A  –  Activity Anomaly (excess velocity)
  delta_T  –  Temporal Novelty (KDE self-history novelty)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
from numpy.linalg import eigh, inv


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class BSDTChannels:
    """Output of a full BSDT channel computation over a time series."""
    delta_C: np.ndarray          # (T,)  mean camouflage per timestep
    delta_G: np.ndarray          # (T,)  mean feature-gap per timestep
    delta_A: np.ndarray          # (T,)  mean activity anomaly per timestep
    delta_T: np.ndarray          # (T,)  mean temporal novelty per timestep
    channels: np.ndarray         # (T, 4)  stacked
    per_agent: np.ndarray        # (T, N, 4)  per-agent detail


@dataclass
class BSDTAudit:
    """Per-institution blind-spot audit at a single point in time."""
    institution_names: list[str]
    delta_C: np.ndarray          # (N,)
    delta_G: np.ndarray          # (N,)
    delta_A: np.ndarray          # (N,)
    delta_T: np.ndarray          # (N,)
    total_score: np.ndarray      # (N,)
    dominant_channel: list[str]  # (N,)  name of highest-contributing channel


# ---------------------------------------------------------------------------
# Single-channel operator (Mahalanobis baseline)
# ---------------------------------------------------------------------------

class BSDTOperator:
    """
    Baseline BSDT operator — Mahalanobis distance from normal-period
    distribution.  Used for the Baseline MFLS scoring variant.

    Parameters
    ----------
    shrinkage : float
        Ledoit-Wolf-style shrinkage toward identity.  0 = no shrinkage,
        1 = pure identity.  Default 0.0 (use empirical covariance).
    """

    def __init__(self, shrinkage: float = 0.0):
        self.shrinkage = shrinkage
        self.mu0_: Optional[np.ndarray] = None
        self.Sigma0_inv_: Optional[np.ndarray] = None
        self._fitted = False

    def fit(self, X_normal: np.ndarray) -> "BSDTOperator":
        """
        Fit on normal-period state matrices.

        Parameters
        ----------
        X_normal : ndarray, shape (T_normal, N, d)
            State matrices from the calibration (normal) period.

        Returns
        -------
        self
        """
        flat = X_normal.reshape(-1, X_normal.shape[-1])
        self.mu0_ = flat.mean(axis=0)
        cov = np.cov(flat, rowvar=False)
        if self.shrinkage > 0:
            cov = (1 - self.shrinkage) * cov + self.shrinkage * np.eye(cov.shape[0])
        cov += 1e-8 * np.eye(cov.shape[0])
        self.Sigma0_inv_ = inv(cov)
        self._fitted = True
        return self

    def deviation(self, X: np.ndarray) -> np.ndarray:
        """Mahalanobis deviation per agent.  X shape (N, d) → (N,)."""
        self._check_fitted()
        diff = X - self.mu0_
        return np.sum(diff @ self.Sigma0_inv_ * diff, axis=1)

    def energy_score(self, X: np.ndarray) -> float:
        """Total blind-spot energy.  X shape (N, d) → scalar."""
        return float(self.deviation(X).sum())

    def gradient(self, X: np.ndarray) -> np.ndarray:
        """Gradient of the energy.  X shape (N, d) → (N, d)."""
        self._check_fitted()
        return 2.0 * (X - self.mu0_) @ self.Sigma0_inv_

    def mfls_score(self, X: np.ndarray) -> float:
        """MFLS score = Frobenius norm of the gradient.  X shape (N, d) → scalar."""
        return float(np.linalg.norm(self.gradient(X), "fro"))

    def score_series(self, X_series: np.ndarray) -> np.ndarray:
        """Score a full time series.  X_series shape (T, N, d) → (T,)."""
        self._check_fitted()
        return np.array([self.mfls_score(X_series[t]) for t in range(X_series.shape[0])])

    def _check_fitted(self):
        if not self._fitted:
            raise RuntimeError("BSDTOperator.fit() must be called before scoring.")


# ---------------------------------------------------------------------------
# Full 4-channel BSDT operator suite
# ---------------------------------------------------------------------------

class BSDTOperators:
    """
    Full BSDT operator suite producing four independent deviation channels.

    Parameters
    ----------
    n_components : int
        Number of PCA components to retain for delta_G.  Default 4.
    velocity_pctl : float
        Percentile of normal-period velocities for delta_A threshold.
    kde_bandwidth : float or None
        KDE bandwidth for delta_T.  None = Scott's rule.
    """

    CHANNEL_NAMES = ["delta_C", "delta_G", "delta_A", "delta_T"]

    def __init__(
        self,
        n_components: int = 4,
        velocity_pctl: float = 95.0,
        kde_bandwidth: Optional[float] = None,
    ):
        self.n_components = n_components
        self.velocity_pctl = velocity_pctl
        self.kde_bandwidth = kde_bandwidth
        self._fitted = False

    def fit(self, X_normal: np.ndarray) -> "BSDTOperators":
        """
        Calibrate all four operators on normal-period data.

        Parameters
        ----------
        X_normal : ndarray, shape (T_norm, N, d)
        """
        flat = X_normal.reshape(-1, X_normal.shape[-1])
        self.mu0_ = flat.mean(axis=0)
        cov = np.cov(flat, rowvar=False)
        cov += 1e-8 * np.eye(cov.shape[0])
        self.Sigma0_ = cov
        self.Sigma0_inv_ = inv(cov)

        # PCA for delta_G
        eigvals, eigvecs = eigh(cov)
        idx = np.argsort(eigvals)[::-1]
        k = min(self.n_components, len(eigvals))
        self.Vk_ = eigvecs[:, idx[:k]]        # top-k directions
        self.V_gap_ = eigvecs[:, idx[k:]]      # residual directions

        # Velocity threshold for delta_A
        T_n, N, d = X_normal.shape
        velocities = []
        for t in range(1, T_n):
            v = np.linalg.norm(X_normal[t] - X_normal[t - 1], axis=1)
            velocities.extend(v.tolist())
        if velocities:
            self.v0_ = float(np.percentile(velocities, self.velocity_pctl))
        else:
            self.v0_ = 1.0
        self.normal_velocities_ = np.array(velocities)

        self._fitted = True
        return self

    # ----- Individual channels -----

    def delta_C(self, X: np.ndarray) -> np.ndarray:
        """Camouflage: Mahalanobis distance.  X (N, d) → (N,)."""
        self._check_fitted()
        diff = X - self.mu0_
        return np.sum(diff @ self.Sigma0_inv_ * diff, axis=1)

    def delta_G(self, X: np.ndarray) -> np.ndarray:
        """Feature Gap: PCA residual norm.  X (N, d) → (N,)."""
        self._check_fitted()
        diff = X - self.mu0_
        total = np.sum(diff ** 2, axis=1)
        projected = np.sum((diff @ self.Vk_) ** 2, axis=1)
        return total - projected

    def delta_A(self, X_curr: np.ndarray, X_prev: np.ndarray) -> np.ndarray:
        """Activity Anomaly: excess velocity.  (N, d), (N, d) → (N,)."""
        self._check_fitted()
        v = np.linalg.norm(X_curr - X_prev, axis=1)
        return np.maximum(0.0, v - self.v0_)

    def delta_T(self, X: np.ndarray, history: list[np.ndarray]) -> np.ndarray:
        """Temporal Novelty: KDE self-history novelty.  X (N, d) → (N,)."""
        self._check_fitted()
        N, d = X.shape
        if len(history) < 2:
            return np.zeros(N)
        bw = self.kde_bandwidth
        if bw is None:
            bw = max(1.0, len(history) ** (-1.0 / (d + 4)))  # Scott's rule
        result = np.zeros(N)
        for i in range(N):
            past = np.array([h[i] for h in history])  # (H, d)
            diff = past - X[i]
            sq = np.sum(diff ** 2, axis=1) / (bw ** 2)
            log_p = np.log(np.mean(np.exp(-0.5 * sq)) + 1e-30) - 0.5 * d * np.log(2 * np.pi * bw ** 2)
            result[i] = max(0.0, -log_p)
        return result

    # ----- Full computation -----

    def compute_channels(self, X_series: np.ndarray, verbose: bool = False) -> BSDTChannels:
        """
        Compute all four channels over a full time series.

        Parameters
        ----------
        X_series : ndarray, shape (T, N, d)

        Returns
        -------
        BSDTChannels
        """
        self._check_fitted()
        T, N, d = X_series.shape
        per_agent = np.zeros((T, N, 4))

        for t in range(T):
            per_agent[t, :, 0] = self.delta_C(X_series[t])
            per_agent[t, :, 1] = self.delta_G(X_series[t])
            if t > 0:
                per_agent[t, :, 2] = self.delta_A(X_series[t], X_series[t - 1])
            history = [X_series[s] for s in range(max(0, t - 20), t)]
            per_agent[t, :, 3] = self.delta_T(X_series[t], history)

            if verbose and (t + 1) % 20 == 0:
                print(f"  BSDT channels: {t + 1}/{T}")

        # Aggregate: mean across agents per timestep
        agg = per_agent.mean(axis=1)  # (T, 4)
        return BSDTChannels(
            delta_C=agg[:, 0],
            delta_G=agg[:, 1],
            delta_A=agg[:, 2],
            delta_T=agg[:, 3],
            channels=agg,
            per_agent=per_agent,
        )

    def audit(
        self,
        X_curr: np.ndarray,
        X_prev: np.ndarray,
        history: list[np.ndarray],
        institution_names: list[str],
    ) -> BSDTAudit:
        """
        Per-institution blind-spot audit at a single point in time.

        Parameters
        ----------
        X_curr : ndarray (N, d) — current state
        X_prev : ndarray (N, d) — previous state
        history : list of ndarray (N, d) — recent history for delta_T
        institution_names : list of str — names for each institution

        Returns
        -------
        BSDTAudit
        """
        self._check_fitted()
        dc = self.delta_C(X_curr)
        dg = self.delta_G(X_curr)
        da = self.delta_A(X_curr, X_prev)
        dt = self.delta_T(X_curr, history)
        total = dc + dg + da + dt

        channel_names = self.CHANNEL_NAMES
        stacked = np.stack([dc, dg, da, dt], axis=1)  # (N, 4)
        dominant = [channel_names[int(np.argmax(stacked[i]))] for i in range(len(dc))]

        return BSDTAudit(
            institution_names=institution_names,
            delta_C=dc,
            delta_G=dg,
            delta_A=da,
            delta_T=dt,
            total_score=total,
            dominant_channel=dominant,
        )

    def _check_fitted(self):
        if not self._fitted:
            raise RuntimeError("BSDTOperators.fit() must be called first.")
