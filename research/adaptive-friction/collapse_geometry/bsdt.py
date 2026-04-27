"""§VI BSDT 4 channels  +  §XXIV.1 per-channel Jacobians ∂δ_k/∂X.

Channels (per-agent scalars δ_k^{(i)} ≥ 0):
    δ_C  Mahalanobis        (x-μ)ᵀ Σ⁻¹ (x-μ)
    δ_G  Feature gap        ||(I - V_k V_kᵀ)(x-μ)||²
    δ_A  Activity anomaly   max(0, ||x_t - x_{t-1}|| - v0)
    δ_T  Temporal novelty   max(0, -log p̂_h(x_t))     (Gaussian KDE)

Jacobians return (N, d) matrices ∂δ_k / ∂X (channel-summed gradient).
"""
from __future__ import annotations
from dataclasses import dataclass
from math import pi
import numpy as np
from .state import CalibrationState, Snapshot


@dataclass
class BSDT:
    cal: CalibrationState

    # ─────────── channel scores  (returns (N,) vectors) ───────────
    def delta_C(self, snap: Snapshot) -> np.ndarray:
        Xt = snap.centred(self.cal.mu0)
        return np.einsum("ij,jk,ik->i", Xt, self.cal.Sigma0_inv, Xt)

    def delta_G(self, snap: Snapshot) -> np.ndarray:
        Xt = snap.centred(self.cal.mu0)
        proj = Xt @ self.cal.Vk
        return (Xt * Xt).sum(axis=1) - (proj * proj).sum(axis=1)

    def delta_A(self, snap: Snapshot) -> np.ndarray:
        if snap.X_prev is None:
            return np.zeros(snap.N)
        v = np.linalg.norm(snap.X - snap.X_prev, axis=1)
        return np.maximum(0.0, v - self.cal.v0)

    def delta_T(self, snap: Snapshot, h: float | None = None) -> np.ndarray:
        if snap.history is None or snap.history.shape[0] == 0:
            return np.zeros(snap.N)
        H, N, d = snap.history.shape
        if h is None:
            h = max(1e-3, H ** (-1.0 / (d + 4)))
        # Per-agent KDE over its own history
        diffs = snap.X[None, :, :] - snap.history          # (H, N, d)
        sq = (diffs * diffs).sum(axis=2)                    # (H, N)
        log_norm = -0.5 * d * np.log(2 * pi * h * h)
        log_kernels = log_norm - sq / (2.0 * h * h)         # (H, N)
        log_p = _logsumexp(log_kernels, axis=0) - np.log(H) # (N,)
        return np.maximum(0.0, -log_p)

    # ───────── total channel state vector S = (δ_C, δ_G, δ_A, δ_T) summed over agents ─────────
    def channel_state(self, snap: Snapshot) -> np.ndarray:
        return snap.memo("channel_state", lambda: np.array([
            self.delta_C(snap).sum(),
            self.delta_G(snap).sum(),
            self.delta_A(snap).sum(),
            self.delta_T(snap).sum()]))

    # ──────── §XXIV.1 spatial Jacobians ∂δ_k/∂X  (each returns (N,d)) ─────────
    def grad_delta_C(self, snap: Snapshot) -> np.ndarray:
        return 2.0 * snap.centred(self.cal.mu0) @ self.cal.Sigma0_inv

    def grad_delta_G(self, snap: Snapshot) -> np.ndarray:
        # uses precomputed I − V_k V_kᵀ from CalibrationState (perf)
        return 2.0 * snap.centred(self.cal.mu0) @ self.cal.I_minus_VVT

    def grad_delta_A(self, snap: Snapshot) -> np.ndarray:
        if snap.X_prev is None:
            return np.zeros_like(snap.X)
        diff = snap.X - snap.X_prev
        v = np.linalg.norm(diff, axis=1, keepdims=True) + 1e-12
        active = (v.flatten() > self.cal.v0).astype(float)[:, None]
        return active * (diff / v)

    def grad_delta_T(self, snap: Snapshot, h: float | None = None) -> np.ndarray:
        if snap.history is None or snap.history.shape[0] == 0:
            return np.zeros_like(snap.X)
        H, N, d = snap.history.shape
        if h is None:
            h = max(1e-3, H ** (-1.0 / (d + 4)))
        diffs = snap.X[None, :, :] - snap.history          # (H, N, d)
        sq = (diffs * diffs).sum(axis=2)                    # (H, N)
        # softmax weights w_s ∝ exp(-||·||²/2h²)
        w = np.exp(-(sq - sq.min(axis=0, keepdims=True)) / (2.0 * h * h))
        w /= w.sum(axis=0, keepdims=True) + 1e-12           # (H, N)
        # Σ_s w_s (x_t - x_{t-s}) / h²
        return (w[:, :, None] * diffs).sum(axis=0) / (h * h)

    def jacobians(self, snap: Snapshot) -> dict[str, np.ndarray]:
        return snap.memo("jacobians", lambda: {
            "C": self.grad_delta_C(snap),
            "G": self.grad_delta_G(snap),
            "A": self.grad_delta_A(snap),
            "T": self.grad_delta_T(snap),
        })

    def jacobians_stacked(self, snap: Snapshot) -> np.ndarray:
        """(4, N, d) tensor stacked along axis 0 in order (C, G, A, T).

        Used by einsum-based pullback (mfls.state_pullback) and Gram
        contraction (lyapunov._bundle).  Cached per snapshot.
        """
        def _stack():
            J = self.jacobians(snap)
            return np.stack([J["C"], J["G"], J["A"], J["T"]], axis=0)
        return snap.memo("jacobians_stacked", _stack)


def _logsumexp(a: np.ndarray, axis: int) -> np.ndarray:
    m = a.max(axis=axis, keepdims=True)
    return (m + np.log(np.exp(a - m).sum(axis=axis, keepdims=True))).squeeze(axis)
