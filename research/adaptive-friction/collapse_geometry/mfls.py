"""§XII.4 + §XXIV.4 + §XXVI  Two MFLS quantities and the misalignment angle ψ.

    g_t            = ∇_S E_BS(S_t)             ∈ R⁴   (channel-space gradient)
    G̃_t            = Σ_k g_k · ∂δ_k/∂X         ∈ R^{N×d}  (state-space pullback)
    MFLS_channel   = ||g_t||                            (abstract intensity)
    MFLS_state     = ||G̃_t||_F                         (physical intensity)
    ρ_MFLS         = MFLS_state / MFLS_channel          (amplification factor)

§XXVI.1 — Correct formula for ψ_t (misalignment angle):

    R_t = Σ_k [g_t]_k ⟨∂_X δ_k, G̃_t⟩_F
        = Σ_k [g_t]_k [Gram · g_t]_k          (Gram_{ij} = ⟨J_i, J_j⟩_F)
        = g_t^T Gram g_t
        = ||G̃_t||_F^2                          (by definition of G̃_t)

    cos ψ_t = R_t / (||G̃_t||_F · ||g_t||)
            = ||G̃_t||_F^2 / (||G̃_t||_F · ||g_t||)
            = ||G̃_t||_F / ||g_t||
            = ρ_MFLS

    ψ_t = arccos(min(1, ρ_MFLS))   (clamped — ρ > 1 means over-amplification, ψ → 0)
    ξ_6 = cos² ψ_t = min(1, ρ_MFLS²)    ∈ [0, 1]

Interpretation:
    ρ_MFLS < 1  (ψ > 0)  : state does not fully transmit channel risk  → contained
    ρ_MFLS = 1  (ψ = 0)  : perfect transmission — channel MFLS = state MFLS
    ρ_MFLS > 1  (ψ = 0)  : state over-amplifies channel signal         → real collapse
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .bsdt import BSDT
from .unified_energy import UnifiedEnergy
from .state import Snapshot


@dataclass
class MFLS:
    bsdt: BSDT
    energy: UnifiedEnergy

    # ── channel-space (R⁴) ───────────────────────────────────────
    def channel_gradient(self, snap: Snapshot) -> np.ndarray:
        S = self.bsdt.channel_state(snap)
        return self.energy.grad(S)

    def channel_mfls(self, snap: Snapshot) -> float:
        return float(np.linalg.norm(self.channel_gradient(snap)))

    # ── state-space pullback G̃_t (N×d) ─────────────────────────────
    def state_pullback(self, snap: Snapshot) -> np.ndarray:
        g = self.channel_gradient(snap)             # (4,)
        J = self.bsdt.jacobians(snap)               # dict of (N,d)
        return (g[0] * J["C"] + g[1] * J["G"]
                + g[2] * J["A"] + g[3] * J["T"])

    def state_mfls(self, snap: Snapshot) -> float:
        return float(np.linalg.norm(self.state_pullback(snap), "fro"))

    # ── amplification ρ_MFLS  (§XXIV.4) ─────────────────────────
    def rho_mfls(self, snap: Snapshot) -> float:
        ch = self.channel_mfls(snap)
        return self.state_mfls(snap) / ch if ch > 1e-12 else 0.0

    # ── ψ_t misalignment angle (§XXVI.1) ────────────────────────
    def psi(self, snap: Snapshot) -> float:
        """ψ_t = arccos(min(1, ρ_MFLS))  per §XXVI.1.

        Derivation (see module docstring):
            R_t = g_t^T Gram g_t = ||G̃_t||_F^2
            cos ψ_t = R_t / (||G̃_t||_F · ||g_t||) = ρ_MFLS

        Clamped to [0, 1] so arccos is always defined.
        ρ > 1 (over-amplified) maps to ψ = 0 (fully aligned → real collapse).
        ρ < 1 (under-amplified) gives ψ > 0 (risk is partially contained).
        """
        rho = min(1.0, self.rho_mfls(snap))
        return float(np.arccos(rho))
