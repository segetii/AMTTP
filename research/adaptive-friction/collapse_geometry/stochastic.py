"""§XIX Stochastic extension — Itô correction, Fokker-Planck stationary, Kramers.

dX_t = (controlled drift) dt + σ_n dW_t.
Itô:  d e_t = (⟨g,F⟩(1-γ*) + σ_n²/2 · tr(∇²E_BS)) dt + σ_n ⟨g, dW⟩
P(τ_cross < τ) ≈ 1 − exp(−τ / τ_Kramers)
τ_Kramers = 2π/√(|μ'(e_t)|·|μ'(e*)|) · exp(2(e*-e_t)/σ_n²)
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .control import MasterOperator
from .lyapunov import LyapunovCertificate
from .state import Snapshot


@dataclass
class StochasticExtension:
    op: MasterOperator
    lyap: LyapunovCertificate
    sigma_n: float = 1e-2  # noise amplitude

    def ito_correction(self, snap: Snapshot) -> float:
        S = self.op.bsdt.channel_state(snap)
        H = self.op.energy.hessian(S)
        return 0.5 * self.sigma_n ** 2 * float(np.trace(H))

    def expected_dV(self, snap: Snapshot) -> float:
        """E[dV/dt] under noise = deterministic dV + Itô."""
        return self.lyap.dV_dt(snap) + self.ito_correction(snap)

    def stable_in_expectation(self, snap: Snapshot) -> bool:
        return self.expected_dV(snap) < 0

    def kramers_time(self, snap: Snapshot, e_star: float,
                     dt: float = 1e-2) -> float:
        e = self.op.damp.e_BSDT(snap)
        if e_star <= e:
            return 0.0
        # μ_e(e) = ⟨g,F⟩(1-γ*) + Itô; differentiate via finite diff in e
        mu_now = self.expected_dV(snap)
        snap_next = self.op.integrate(snap, dt=dt, steps=1)
        mu_next = self.expected_dV(snap_next)
        dmu = abs(mu_next - mu_now) / max(dt, 1e-12)
        if dmu < 1e-12:
            return float("inf")
        prefac = 2.0 * np.pi / dmu
        barrier = np.exp(2.0 * (e_star - e) / max(self.sigma_n ** 2, 1e-12))
        return float(prefac * barrier)

    def cross_probability(self, snap: Snapshot, e_star: float,
                          tau: float, dt: float = 1e-2) -> float:
        tau_K = self.kramers_time(snap, e_star, dt)
        if tau_K == float("inf"):
            return 0.0
        return float(1.0 - np.exp(-tau / tau_K))
