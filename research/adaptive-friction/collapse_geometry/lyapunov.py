"""§XVI Lyapunov certificate (corrected) + §XXV per-channel decomposition.

V(X)        = E_BSDT(B(X))                      — §XVI.1
G̃           = Σ_k g_k ∂δ_k/∂X                   — §XXIV.1
P_t = ⟨G̃, F⟩_F                                 — §XVI.6
R_t = Σ_k g_k ⟨∂δ_k, g⟩  (control coupling)    — §XXIV.5
Q_t = ⟨F, g⟩ · R_t                              — §XVI.6
dV/dt = P_t − γ* Q_t / ||g||²                   — §XVI.4
M_t (stability margin) = (γ* Q/||g||² − P) / (|P| + |Q|/||g||²)   — §XXIV.5
γ*_min = ||g||² P / Q  (when both > 0)          — §XVI.6

Per channel (§XXV):
    V̇_k = g_k [⟨∂δ_k, F⟩ − γ* ⟨F,g⟩/||g||² · ⟨∂δ_k, g⟩]
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .control import MasterOperator
from .state import Snapshot


@dataclass
class LyapunovCertificate:
    op: MasterOperator

    # ── building blocks ─────────────────────────────────────────
    def _bundle(self, snap: Snapshot) -> dict:
        F = self.op.force(snap)
        g = self.op.mfls.channel_gradient(snap)         # (4,)
        J = self.op.bsdt.jacobians(snap)
        Gtilde = g[0]*J["C"] + g[1]*J["G"] + g[2]*J["A"] + g[3]*J["T"]
        gamma = self.op.damp.gamma_star(snap)
        # ⟨F, g_channel⟩ — but g lives in R⁴ → use ⟨F, J·g⟩ = ⟨F, Gtilde⟩ in state-space
        # The §XVI scalars ⟨F, g⟩ and ⟨∂δ_k, g⟩ are interpreted via the pullback:
        # ⟨F, g⟩ ≡ Σ_k g_k ⟨∂δ_k, F⟩_F = ⟨Gtilde, F⟩_F by linearity.
        Fg = float((F * Gtilde).sum())                  # ⟨F, g⟩ via pullback
        # ⟨∂δ_k, g⟩ ≡ Σ_l g_l ⟨∂δ_k, ∂δ_l⟩_F
        inner = np.zeros((4, 4))
        keys = ("C", "G", "A", "T")
        for i, ki in enumerate(keys):
            for j, kj in enumerate(keys):
                inner[i, j] = (J[ki] * J[kj]).sum()
        kg = inner @ g                                  # (4,)
        Rt = float((g * kg).sum())                      # control coupling sum
        gnorm2 = float((g * g).sum())                   # ||g||² in R⁴
        Pt = float((Gtilde * F).sum())                  # ⟨G̃, F⟩_F
        Qt = Fg * Rt
        return dict(F=F, g=g, J=J, Gtilde=Gtilde, gamma=gamma,
                    Fg=Fg, kg=kg, Rt=Rt, gnorm2=gnorm2, Pt=Pt, Qt=Qt)

    # ── §XVI dV/dt ─────────────────────────────────────────────
    def dV_dt(self, snap: Snapshot) -> float:
        b = self._bundle(snap)
        return b["Pt"] - b["gamma"] * b["Qt"] / max(b["gnorm2"], 1e-12)

    # ── §XVI.7 MFLS decay rate  d MFLS/dt = M_t · (|P|+|Q|/||g||²) / ||g|| ────
    def mfls_rate(self, snap: Snapshot) -> float:
        b = self._bundle(snap)
        gn = float(np.sqrt(max(b["gnorm2"], 1e-12)))
        gn2 = max(b["gnorm2"], 1e-12)
        scale = abs(b["Pt"]) + abs(b["Qt"]) / gn2
        return self.margin(snap) * scale / gn

    # ── §XXIV.5 stability margin M_t ───────────────────────────
    def margin(self, snap: Snapshot) -> float:
        b = self._bundle(snap)
        gn2 = max(b["gnorm2"], 1e-12)
        num = b["gamma"] * b["Qt"] / gn2 - b["Pt"]
        den = abs(b["Pt"]) + abs(b["Qt"]) / gn2
        return num / max(den, 1e-12)

    # ── critical control γ*_min  (§XVI.6) ─────────────────────
    def gamma_min(self, snap: Snapshot) -> float | None:
        b = self._bundle(snap)
        if b["Pt"] <= 0 or b["Qt"] <= 0:
            return None  # already self-stabilising or uncontrollable
        return b["gnorm2"] * b["Pt"] / b["Qt"]

    # ── §XVI.7 intervention-cost ceiling  θ < e_t · (Q/(||g||²P) − 1) ────
    def theta_ceiling(self, snap: Snapshot) -> float | None:
        """Maximum intervention cost θ for which the control γ* = e/(e+θ) is
        still strong enough to satisfy V̇ ≤ 0.  Returns None when the system is
        in the uncontrollable regime (P≤0 or Q≤0) — no finite θ suffices."""
        b = self._bundle(snap)
        if b["Pt"] <= 0 or b["Qt"] <= 0:
            return None
        et = self.op.damp.e_BSDT(snap)
        ratio = b["Qt"] / (b["gnorm2"] * b["Pt"])
        return et * (ratio - 1.0)

    # ── §XXV per-channel V̇_k decomposition ────────────────────
    def channel_decomposition(self, snap: Snapshot) -> dict[str, dict]:
        b = self._bundle(snap)
        F, g, J = b["F"], b["g"], b["J"]
        out = {}
        keys = ("C", "G", "A", "T")
        Fg = b["Fg"]
        gn2 = max(b["gnorm2"], 1e-12)
        gamma = b["gamma"]
        for i, k in enumerate(keys):
            inner_F = float((J[k] * F).sum())          # ⟨∂δ_k, F⟩
            inner_g = float(b["kg"][i])                # ⟨∂δ_k, g⟩
            v_drift = g[i] * inner_F
            v_ctrl  = -g[i] * gamma * Fg / gn2 * inner_g
            v_total = v_drift + v_ctrl
            eta = (-v_ctrl / v_drift) if abs(v_drift) > 1e-12 else 0.0
            out[k] = dict(v_drift=v_drift, v_control=v_ctrl,
                          v_total=v_total, eta=eta)
        # attribution a_k
        pos = {k: max(0.0, v["v_total"]) for k, v in out.items()}
        Z = sum(pos.values()) + 1e-12
        for k in out: out[k]["attribution"] = pos[k] / Z
        return out
