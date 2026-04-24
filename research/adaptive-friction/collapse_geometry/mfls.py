"""§XII.4 + §XXIV.4 + §XXVI  Two MFLS quantities and the misalignment angle ψ.

    g_t            = ∇_S E_BS(S_t)             ∈ R⁴   (channel-space gradient)
    G̃_t            = Σ_k g_k · ∂δ_k/∂X         ∈ R^{N×d}  (state-space pullback)
    MFLS_channel   = ||g_t||                            (abstract intensity)
    MFLS_state     = ||G̃_t||_F                         (physical intensity)
    ρ_MFLS         = MFLS_state / MFLS_channel          (amplification factor)
    cos ψ_t        = ⟨G̃_t, g_t·…⟩ / (||G̃_t||·||g_t||)   — see §XXVI
                   ≡ ⟨G̃_t, R_t-decomp⟩ / norms

Note on ψ_t: g_t lives in R⁴, G̃_t in R^{N×d}; the cosine is computed via
the scalar  R_t = Σ_k g_k ⟨∂_X δ_k, g_t⟩_F ÷ ||·||  in §XXV.
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

    # ── ψ_t misalignment angle (§XXVI) ──────────────────────────
    def psi(self, snap: Snapshot) -> float:
        """ψ_t = arccos(R_t / (||G̃||·||g||))  with R_t = Σ g_k ⟨∂δ_k, G̃⟩_F / ||g||
        Equivalently: cos ψ = ⟨G̃, G̃⟩_F / (||G̃||·||G̃||) when same construction →
        we use the canonical form  cos ψ = ⟨G̃, J g⟩ / (norms)  where J g rebuilds G̃.
        Since G̃ ≡ Σ g_k J_k by construction, the natural angle is between G̃ and the
        component obtained by projecting onto the g-direction in ⟨∂δ_k,·⟩ space."""
        g = self.channel_gradient(snap)
        J = self.bsdt.jacobians(snap)
        Gtilde = g[0]*J["C"] + g[1]*J["G"] + g[2]*J["A"] + g[3]*J["T"]
        # R_t in §XXV.4: Σ_k g_k ⟨∂δ_k, g_t⟩_F
        # Here ⟨·,·⟩_F is between (N,d) matrix and a vector — interpret as
        # ⟨Σ g_k ∂δ_k, Σ g_k ∂δ_k⟩_F / (norms) = 1 in trivial case;
        # the meaningful misalignment is between G̃ and the *uniform-weight* pullback.
        Gtilde_uniform = J["C"] + J["G"] + J["A"] + J["T"]
        a = np.linalg.norm(Gtilde, "fro")
        b = np.linalg.norm(Gtilde_uniform, "fro")
        if a < 1e-12 or b < 1e-12:
            return 0.0
        cos_psi = float(np.clip((Gtilde * Gtilde_uniform).sum() / (a * b), -1.0, 1.0))
        return float(np.arccos(cos_psi))
