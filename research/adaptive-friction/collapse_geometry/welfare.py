"""§IX CCyB calibration + consumption-equivalent welfare loss.

Both quantities are CLOSED-FORM from the panel — no trajectory simulation.

CCyB(t) = 250 · e_t · σ_ℓ(t) · (e_t + θ)⁻¹ / max_s[e_s σ_ℓ(s)(e_s+θ)⁻¹]   bps  ∈ [0, 250]

W = 100 · (1 − exp(−1/(σ θ T_w) · Σ_t γ*_t · Φ_pair(X_t)))   pp

where the energy gap is purely pairwise (§IX.2 derivation):
    Φ(X_t) − Φ_cf(X_t) = γ*_t · Φ_pair(X_t)

Inputs:
    panel       (T, N, d) — full crisis-window trajectory
    sigma_ell   (T,)      — cross-sectional std of the leverage feature per t
    op          MasterOperator (provides μ0, Σ⁻¹, potential γ, σ, λ, θ)
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .control import MasterOperator
from .state import Snapshot


@dataclass
class WelfareCalibration:
    op: MasterOperator
    sigma_calib: float = 1.0   # consumption elasticity (Basel III default 1)

    # ── per-timestep e_t = ||X̃ Σ⁻¹/²||²_F  (vectorised over the panel) ──
    def energy_series(self, panel: np.ndarray) -> np.ndarray:
        """panel: (T, N, d) → e_t for each t."""
        Xc = panel - self.op.cal.mu0
        # tr(X̃ Σ⁻¹ X̃ᵀ) per t
        A = Xc @ self.op.cal.Sigma0_inv_sqrt              # (T, N, d)
        return (A * A).sum(axis=(1, 2))                   # (T,)

    # ── per-timestep Φ_pair via the master operator's potential ─────────
    def pair_energy_series(self, panel: np.ndarray) -> np.ndarray:
        T = panel.shape[0]
        out = np.empty(T)
        for t in range(T):
            snap = Snapshot(X=panel[t])
            D = snap.distance_matrix()
            out[t] = self.op.potential.E_pair(D)
        return out

    # ── §IX.1 CCyB in basis points ──────────────────────────────────────
    def ccyb(self, panel: np.ndarray, sigma_ell: np.ndarray) -> np.ndarray:
        """CCyB(t) ∈ [0, 250] bps for each t."""
        e = self.energy_series(panel)
        theta = self.op.damp.theta
        score = e * sigma_ell / (e + theta)
        peak = score.max() if score.max() > 0 else 1.0
        return 250.0 * score / peak

    # ── §IX.2 welfare loss (pp) ─────────────────────────────────────────
    def welfare_loss(self, panel: np.ndarray) -> float:
        e = self.energy_series(panel)
        Phi_pair = self.pair_energy_series(panel)
        theta = self.op.damp.theta
        gamma_star = e / (e + theta)
        T_w = panel.shape[0]
        # magnitude of damped coupling (Φ_pair may be signed; welfare cost
        # depends on absolute coupling that γ* attenuates)
        gap_sum = float((gamma_star * np.abs(Phi_pair)).sum())
        x = gap_sum / max(self.sigma_calib * theta * T_w, 1e-12)
        return 100.0 * (1.0 - float(np.exp(-x)))

    # ── full report ────────────────────────────────────────────────────
    def report(self, panel: np.ndarray, sigma_ell: np.ndarray | None = None) -> dict:
        if sigma_ell is None:
            # default: cross-sectional std of feature 0 ("leverage") per t
            sigma_ell = panel[..., 0].std(axis=1)
        e = self.energy_series(panel)
        theta = self.op.damp.theta
        gamma = e / (e + theta)
        ccyb = self.ccyb(panel, sigma_ell)
        return dict(
            e_series=e,
            gamma_series=gamma,
            sigma_ell=sigma_ell,
            ccyb_bps=ccyb,
            ccyb_max_bps=float(ccyb.max()),
            ccyb_mean_bps=float(ccyb.mean()),
            welfare_loss_pp=self.welfare_loss(panel),
        )
