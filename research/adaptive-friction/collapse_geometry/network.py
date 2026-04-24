"""§II Inter-institution correlation network with Ledoit-Wolf shrinkage.

All formulas are CLOSED-FORM:
  ρ (shrinkage intensity)        — eq. 2.2
  Σ̂ = (1-ρ) S + ρ T* I           — eq. 2.2
  W (correlation, symm, unit-diag) — eq. 2.3
  λ_max(W) via eigh OR closed-form proxy  ρ̃ = 1 + (N-1) W̄_off  — eq. 2.4
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass
class LedoitWolfNetwork:
    S: np.ndarray            # (N, N) sample covariance of leverage feature
    Sigma_hat: np.ndarray    # (N, N) shrunk covariance
    W: np.ndarray            # (N, N) correlation, unit-diag
    rho: float               # shrinkage intensity ∈ [0,1]
    T_star: float            # tr(S)/N
    lam_max: float           # ρ(W) — true spectral radius
    rho_proxy: float         # 1 + (N-1) W̄_off  (closed-form, no eigensolver)
    W_bar_off: float
    W_max_off: float

    @classmethod
    def from_panel(cls, panel: np.ndarray) -> "LedoitWolfNetwork":
        """panel: (T, N) leverage time series for N institutions."""
        T, N = panel.shape
        ell_bar = panel.mean(axis=0)
        Xc = panel - ell_bar
        S = (Xc.T @ Xc) / T
        T_star = float(np.trace(S) / N)
        # closed-form ρ (§II eq. shown)
        Xc_sq = Xc * Xc
        num = (np.linalg.norm(Xc_sq, "fro") ** 2) / (T * T * N * N) \
              - (np.linalg.norm(S, "fro") ** 2) / (T * N * N)
        den = np.linalg.norm(S, "fro") ** 2 - (np.trace(S) ** 2) / N
        rho = float(np.clip(num / den, 0.0, 1.0)) if den > 0 else 1.0
        Sigma_hat = (1.0 - rho) * S + rho * T_star * np.eye(N)
        d = np.sqrt(np.clip(np.diag(Sigma_hat), 1e-12, None))
        W = Sigma_hat / np.outer(d, d)
        W = 0.5 * (W + W.T)
        np.fill_diagonal(W, 1.0)
        # spectral radius — fall back to Frobenius bound if eigh fails to converge
        try:
            lam_max = float(np.linalg.eigvalsh(W)[-1])
        except np.linalg.LinAlgError:
            # add tiny jitter to break degeneracy and retry; if still failing,
            # use the closed-form Frobenius bound (§II.4)
            try:
                lam_max = float(np.linalg.eigvalsh(W + 1e-8 * np.eye(N))[-1])
            except np.linalg.LinAlgError:
                off = W - np.eye(N)
                W_max_off_tmp = float(np.max(np.abs(off))) if N > 1 else 0.0
                lam_max = float(np.sqrt(1.0 + (N - 1) * W_max_off_tmp ** 2))
        # proxy
        off = W - np.eye(N)
        n_off = N * (N - 1)
        W_bar_off = float(off.sum() / n_off) if n_off > 0 else 0.0
        W_max_off = float(np.max(np.abs(off))) if N > 1 else 0.0
        rho_proxy = 1.0 + (N - 1) * W_bar_off
        return cls(S, Sigma_hat, W, rho, T_star, lam_max,
                   rho_proxy, W_bar_off, W_max_off)

    def gershgorin_bound(self) -> float:
        """Frobenius/Gershgorin upper bound — no eigensolver."""
        return float(np.sqrt(1.0 + (self.W.shape[0] - 1) * self.W_max_off ** 2))
