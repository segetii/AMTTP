"""Lyapunov certificate — canonical_system_v4 (Lemma 6.7 / §H.1.3).

Energy functional:   E(X) = S(X)ᵀ G S(X)   (= e_BSDT, scalar)
State gradient:      g_X   = 2JᵀGS = G̃      (N×d pullback)
Canonical Ė formula (Lemma 6.7, frozen):

    Ė = (1−γ) · (Pt − Rt)

where:
    Pt  = ⟨g_X, F_base⟩_F   (⟨G̃, F⟩_F  in code)
    Rt  = ‖g_X‖²_F          (= g^T Gram g = ‖G̃‖²_F  in code)
    γ   = E/(E+θ)             (adaptive gain ∈ [0,1))

Stability criterion:  Ė ≤ 0  iff  Pt ≤ Rt  (geometry-driven, γ-independent).

Stability margin:  M_t = (Rt − Pt) / (|Rt| + |Pt|)  ∈ [-1, 1]
    M > 0 → stable (Rt > Pt),  M < 0 → energy growing.

Per-channel decomposition (§XXV, canonical form):
    V̇_k = g_k [⟨J_k, F_mod⟩ − γ · (Pt−Rt)/Rt · ⟨J_k, g_X⟩]
    where F_mod = F_base − g_X  (canonical modified force)
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
        def _compute():
            F = self.op.force(snap)
            g = self.op.mfls.channel_gradient(snap)         # (4,)
            J = self.op.bsdt.jacobians(snap)
            # state-space pullback: reuse cached/einsum version (logic-equivalent)
            Gtilde = self.op.mfls.state_pullback(snap)
            gamma = self.op.damp.gamma_star(snap)
            # ⟨F, g_channel⟩ — but g lives in R⁴ → use ⟨F, J·g⟩ = ⟨F, Gtilde⟩ in state-space
            # The §XVI scalars ⟨F, g⟩ and ⟨∂δ_k, g⟩ are interpreted via the pullback:
            # ⟨F, g⟩ ≡ Σ_k g_k ⟨∂δ_k, F⟩_F = ⟨Gtilde, F⟩_F by linearity.
            Fg = float((F * Gtilde).sum())                  # ⟨F, g⟩ via pullback
            # ⟨∂δ_k, g⟩ ≡ Σ_l g_l ⟨∂δ_k, ∂δ_l⟩_F   — Gram matrix via single BLAS call
            Js = self.op.bsdt.jacobians_stacked(snap)       # (4, N, d)
            inner = np.einsum("ind,jnd->ij", Js, Js)        # (4, 4)
            kg = inner @ g                                  # (4,)
            Rt = float((g * kg).sum())                      # control coupling sum
            gnorm2 = float((g * g).sum())                   # ||g||² in R⁴
            Pt = float((Gtilde * F).sum())                  # ⟨G̃, F⟩_F
            Qt = Fg * Rt
            return dict(F=F, g=g, J=J, Gtilde=Gtilde, gamma=gamma,
                        Fg=Fg, kg=kg, Rt=Rt, gnorm2=gnorm2, Pt=Pt, Qt=Qt)
        return snap.memo("lyap_bundle", _compute)

    # ── canonical Ė = (1−γ)(Pt − Rt)  [Lemma 6.7] ─────────────
    def dV_dt(self, snap: Snapshot) -> float:
        """Canonical energy rate: Ė = (1−γ)(⟨g_X, F_base⟩ − ‖g_X‖²).

        Lemma 6.7 of canonical_system_v4 (frozen formula).
        Positive → energy growing (pre-collapse); negative → decaying (stable).
        """
        b = self._bundle(snap)
        return (1.0 - b["gamma"]) * (b["Pt"] - b["Rt"])

    # ── §XVI.7 MFLS decay rate  d MFLS/dt ≈ Ė / (2·‖g_X‖) ─────
    def mfls_rate(self, snap: Snapshot) -> float:
        """Approximate rate of change of MFLS_state = ‖g_X‖_F.

        Since E = ‖g_X‖²_F = Rt and MFLS_state = sqrt(Rt),
        d(MFLS)/dt ≈ Ė / (2·MFLS) = (1−γ)(Pt−Rt) / (2·sqrt(Rt)).
        """
        b = self._bundle(snap)
        mfls = float(np.sqrt(max(b["Rt"], 1e-12)))
        return (1.0 - b["gamma"]) * (b["Pt"] - b["Rt"]) / (2.0 * mfls)

    # ── canonical stability margin M_t ─────────────────────────
    def margin(self, snap: Snapshot) -> float:
        """Canonical stability margin: M_t = (Rt − Pt) / (|Rt| + |Pt|) ∈ [-1, 1].

        Stable (Ė ≤ 0) iff Pt ≤ Rt (M ≥ 0).
        Stability is geometry-driven — independent of γ.
        """
        b = self._bundle(snap)
        num = b["Rt"] - b["Pt"]
        den = abs(b["Rt"]) + abs(b["Pt"])
        return num / max(den, 1e-12)

    # ── canonical γ*_min: not applicable (stability is geometry-driven) ──
    def gamma_min(self, snap: Snapshot) -> float | None:
        """Under canonical v4, Ė = (1−γ)(Pt−Rt).

        Stability (Pt ≤ Rt) is a property of the geometry, not of γ.
        No γ ∈ [0,1) can make Ė ≤ 0 when Pt > Rt.
        Returns None in all cases — use margin() to assess stability.
        """
        return None

    # ── canonical θ_ceiling: max θ before energy growth becomes unbounded ──
    def theta_ceiling(self, snap: Snapshot) -> float | None:
        """Maximum intervention cost θ before energy growth reaches the open-loop rate.

        With γ = e/(e+θ), energy rate Ė = (θ/(e+θ)) · (Pt−Rt).
        System is unconditionally stable when Pt ≤ Rt (return None — no θ limit).
        When Pt > Rt (energy growing), no finite θ cures instability; return None.
        """
        b = self._bundle(snap)
        if b["Pt"] <= b["Rt"]:
            return None   # self-stabilising — no θ constraint
        return None       # unstable: stability cannot be restored via θ alone

    # ── canonical per-channel V̇_k decomposition ──────────────────
    def channel_decomposition(self, snap: Snapshot) -> dict[str, dict]:
        """Per-channel energy rate using canonical F_mod = F_base − g_X.

        V̇_k = g_k [⟨J_k, F_mod⟩ − γ · (Pt−Rt)/Rt · ⟨J_k, g_X⟩]

        where F_mod = F_base − g_X  (canonical modified force, §H.1 step 6).

        Sum over k: Σ V̇_k = (1−γ)(Pt−Rt) = Ė  ✓
        """
        b = self._bundle(snap)
        F_base, g, J = b["F"], b["g"], b["J"]
        # g_X = G̃ = state_pullback; ⟨J_k, G̃⟩_F = (Gram·g)[k] = kg[k] (Gram identity)
        Rt     = b["Rt"]              # ‖g_X‖²_F
        Pt     = b["Pt"]              # ⟨g_X, F_base⟩
        gamma  = b["gamma"]
        # (Pt−Rt)/Rt: projection coefficient for the control term
        proj_coeff = (Pt - Rt) / max(Rt, 1e-12)
        out = {}
        keys = ("C", "G", "A", "T")
        for i, k in enumerate(keys):
            inner_Fbase  = float((J[k] * F_base).sum())    # ⟨J_k, F_base⟩
            kg_k         = float(b["kg"][i])               # ⟨J_k, g_X⟩ = (Gram·g)[k]
            inner_Fmod   = inner_Fbase - kg_k              # ⟨J_k, F_mod⟩
            v_drift = g[i] * inner_Fmod
            v_ctrl  = -g[i] * gamma * proj_coeff * kg_k   # −g_k γ(Pt−Rt)/Rt ⟨J_k,g_X⟩
            v_total = v_drift + v_ctrl
            eta = (-v_ctrl / v_drift) if abs(v_drift) > 1e-12 else 0.0
            out[k] = dict(v_drift=v_drift, v_control=v_ctrl,
                          v_total=v_total, eta=eta)
        # attribution a_k
        pos = {k: max(0.0, v["v_total"]) for k, v in out.items()}
        Z = sum(pos.values()) + 1e-12
        for k in out: out[k]["attribution"] = pos[k] / Z
        return out
