"""§XIII + §XV  Master Operator — canonical ODE (canonical_system_v4, §H.1).

    F_mod = F_base(X) − g_X(X)                          (§H.1 step 6)
    Ẋ = F_mod − γ(X) · ⟨F_mod, g_X/‖g_X‖⟩ · g_X/‖g_X‖  (§H.1 step 9)
       = F_mod_per + (1−γ) · F_mod_par

where g_X = 2JᵀGS is the state-space gradient (= G̃) and
      u = g_X / ‖g_X‖_F is the unit collapse direction.

Four inviolable rules (canonical §4):
  1. Geometry enters only through g_X.
  2. All projections use Euclidean inner product.
  3. G_pull = JᵀGJ is for curvature analysis ONLY — not in dynamics.
  4. No duplication of g_X definitions.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .state import CalibrationState, Snapshot
from .potential import Potential
from .forces import ForceField
from .bsdt import BSDT
from .unified_energy import UnifiedEnergy
from .mfls import MFLS
from .damping import AdaptiveDamping


@dataclass
class MasterOperator:
    cal: CalibrationState
    potential: Potential
    forces: ForceField
    bsdt: BSDT
    energy: UnifiedEnergy
    mfls: MFLS
    damp: AdaptiveDamping

    # ── one-shot constructor from normal-period panel ───────────────
    @classmethod
    def calibrate(cls, X_normal: np.ndarray, *,
                  k: int = 4, theta: float = 1.0,
                  potential: Potential | None = None,
                  energy: UnifiedEnergy | None = None,
                  F_max: float = 100.0) -> "MasterOperator":
        cal = CalibrationState.fit(X_normal, k=k)
        pot = potential or Potential()
        fld = ForceField(pot=pot, F_max=F_max)
        ue  = energy or UnifiedEnergy.pure_mahalanobis()
        b   = BSDT(cal=cal)
        m   = MFLS(bsdt=b, energy=ue)
        d   = AdaptiveDamping(cal=cal, theta=theta)
        return cls(cal, pot, fld, b, ue, m, d)

    # ── core: free force, control direction, parallel/perpendicular ─
    def force(self, snap: Snapshot) -> np.ndarray:
        def _compute():
            D = snap.distance_matrix()
            return self.forces.force(snap.X, self.cal.mu0, D)
        return snap.memo("force", _compute)

    def collapse_direction_state(self, snap: Snapshot) -> np.ndarray:
        def _compute():
            Gt = self.mfls.state_pullback(snap)
            n = np.linalg.norm(Gt, "fro")
            return Gt / n if n > 1e-12 else np.zeros_like(Gt)
        return snap.memo("collapse_dir", _compute)

    def decompose(self, F: np.ndarray, u: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        proj = float((F * u).sum())   # ⟨F, u⟩ on (N,d) tensors
        F_par = proj * u
        F_per = F - F_par
        return F_par, F_per, proj

    # ── master equation (canonical ODE §H.1 steps 6–9) ─────────────
    def step(self, snap: Snapshot) -> np.ndarray:
        """Return Ẋ_t per canonical ODE (canonical_system_v4 §H.1).

        Step 6: F_mod = F_base − g_X          (g_X = G̃ = 2JᵀGS)
        Step 9: Ẋ = F_mod − γ·⟨F_mod, u⟩·u   (u = g_X/‖g_X‖_F)
               = F_mod_per + (1−γ)·F_mod_par
        """
        F_base = self.force(snap)
        g_X    = self.mfls.state_pullback(snap)      # G̃ = g_X = 2JᵀGS (§H.1 step 3)
        F_mod  = F_base - g_X                         # §H.1 step 6: modified force
        u      = self.collapse_direction_state(snap)  # g_X/‖g_X‖_F  (cached)
        F_par, F_per, proj = self.decompose(F_mod, u)
        gamma  = self.damp.gamma_star(snap)
        return F_per + (1.0 - gamma) * F_par          # F_mod − γ·⟨F_mod,u⟩·u

    def integrate(self, snap: Snapshot, dt: float = 1.0,
                  steps: int = 1) -> Snapshot:
        """Forward-Euler integration of the master operator."""
        s = snap
        for _ in range(steps):
            dXdt = self.step(s)
            X_new = s.X + dt * dXdt
            s = Snapshot(X=X_new, X_prev=s.X, history=s.history)
        return s

    # ── §XI Master Pipeline — all 10 closed-form outputs per snapshot ──
    def pipeline(self, snap: Snapshot,
                 network=None,
                 sigma_ell: float | None = None) -> dict:
        """§XI Master Pipeline: compute all 10 closed-form outputs in order.

        Steps 1–8 require only the current snapshot.  Step 9 (CCyB) requires
        σ_ℓ(t) — the cross-sectional std of the leverage feature — passed as
        `sigma_ell`; if None it is estimated from snap.X[:, 0].  Step 10
        (welfare loss W) requires the full crisis window which is not available
        per-snapshot; it is omitted here and exposed via WelfareCalibration.

        All formulas reference the §XI dependency graph.

        Parameters
        ----------
        snap        : current state snapshot X_t ∈ R^{N×d}
        network     : optional LedoitWolfNetwork for ρ̃ (step 8); if None the
                      proxy is computed directly from the correlation matrix of
                      snap.X[:, 0] (leverage feature)
        sigma_ell   : cross-sectional std of leverage at time t; if None,
                      estimated as snap.X[:, 0].std()

        Returns
        -------
        dict with keys matching the §XI step labels:
            Xt_centred   (N,d)    step 1   X̃_t
            D            (N,N)    step 2   distance matrix
            e_t          float    step 3   BSDT energy
            MFLS_t       float    step 4   Mahalanobis MFLS = 2||X̃Σ⁻¹₀||_F
            gamma_star   float    step 5   optimal damping
            Phi_t        float    step 6   total potential energy
            lambda_bound float    step 7   Gershgorin bound on λ_max(∇²Φ)
            supercritical bool    step 7   λ_bound > 1
            rho_proxy    float    step 8   1 + (N-1) W̄_off
            ccyb_norm    float    step 9   CCyB score (unnormalised; divide by
                                           max over panel for bps)
            -- additional closed-form quantities --
            F_t          (N,d)            restoring force matrix
            MFLS_state   float            ||G̃_t||_F (general 4-channel MFLS)
            MFLS_channel float            ||g_t||   (abstract channel MFLS)
            rho_MFLS     float            amplification factor ρ_MFLS
            psi          float   rad      misalignment angle ψ_t (§XXVI)
            xi6          float            cos² ψ_t ∈ [0,1]  (§XXVI.3 ξ_6)
            cos_theta_ch float            §VII gradient-alignment (channel)
            cos_theta_st float            §XXIV.3 gradient-alignment (state)
            Phi_pair     float            pairwise energy Φ_pair(X_t)
        """
        from scipy.special import erf  # late import to avoid circular
        # ── Step 1: centred state matrix ─────────────────────────────
        Xt_centred = snap.centred(self.cal.mu0)                # (N, d)

        # ── Step 2: Euclidean distance matrix (one matmul) ───────────
        D = snap.distance_matrix()                              # (N, N)

        # ── Step 3: BSDT Mahalanobis energy e_t ──────────────────────
        A_mat = Xt_centred @ self.cal.Sigma0_inv_sqrt           # (N, d)
        e_t   = float((A_mat * A_mat).sum())                    # tr(X̃ Σ⁻¹ X̃ᵀ)

        # ── Step 4: Mahalanobis MFLS = 2||X̃ Σ⁻¹₀||_F (§VI + §XI.④) ─
        A2 = Xt_centred @ self.cal.Sigma0_inv                   # (N, d)
        MFLS_mah = 2.0 * float(np.linalg.norm(A2, "fro"))

        # ── Step 5: optimal adaptive damping γ* ──────────────────────
        gamma = e_t / (e_t + self.damp.theta)

        # ── Step 6: total potential energy Φ_t ───────────────────────
        Phi_rad  = 0.5 * self.potential.alpha * float(
            np.linalg.norm(snap.X - self.cal.mu0, "fro") ** 2)
        N = snap.N
        mask = ~np.eye(N, dtype=bool)
        d_off = D[mask] + self.potential.eps
        Phi_pair = float(0.5 * (
            -self.potential.gamma * self.potential.sigma * erf(d_off / self.potential.sigma).sum()
            + self.potential.lam * np.log(d_off).sum()
        ))
        Phi_t = Phi_rad + Phi_pair

        # ── Step 7: Gershgorin bound on λ_max(∇²Φ) — no eigensolver ─
        lam_bound = self.potential.lambda_max_bound(D)

        # ── Step 8: network spectral radius proxy ρ̃_t ────────────────
        if network is not None:
            rho_proxy = float(network.rho_proxy)
            W_bar_off = float(network.W_bar_off)
        else:
            # build from leverage feature (column 0) of current snapshot
            from .network import LedoitWolfNetwork
            lev = snap.X[:, 0:1].T                             # (1, N)
            # need at least 2 time points; approximate with small perturbation
            lev2 = np.vstack([lev, lev + 1e-6])
            _net = LedoitWolfNetwork.from_panel(lev2)
            rho_proxy = float(_net.rho_proxy)
            W_bar_off = float(_net.W_bar_off)

        # ── Step 9: CCyB score (unnormalised) ────────────────────────
        if sigma_ell is None:
            sigma_ell = float(snap.X[:, 0].std()) if snap.d > 0 else 1.0
        ccyb_norm = float(e_t * sigma_ell / (e_t + self.damp.theta))

        # ── Additional quantities ────────────────────────────────────
        F_t          = self.forces.force(snap.X, self.cal.mu0, D)
        MFLS_state   = self.mfls.state_mfls(snap)
        MFLS_channel = self.mfls.channel_mfls(snap)
        rho_MFLS     = self.mfls.rho_mfls(snap)
        psi          = self.mfls.psi(snap)
        xi6          = float(np.cos(psi) ** 2)                 # = min(1, ρ²)

        # cos θ (state — bounded ∈ [-1,1], used in EWS ξ_4 and Lyapunov)
        # cos θ (channel — uses ||g|| denominator; may exceed ±1 when ρ≫1;
        #         theoretical diagnostic, not used in constraints)
        Gtilde = self.mfls.state_pullback(snap)                 # (N, d)
        nF = float(np.linalg.norm(F_t, "fro"))
        nG = float(np.linalg.norm(Gtilde, "fro"))
        g  = self.mfls.channel_gradient(snap)
        ng = float(np.linalg.norm(g))
        inner_GF = float((Gtilde * F_t).sum())
        # §XXIV.3 state cosine ∈ [-1,1]:  ⟨G̃, F⟩/(||G̃||_F · ||F||_F)
        cos_theta_state = float(inner_GF / (nG * nF)) \
                          if nG > 1e-12 and nF > 1e-12 else 0.0
        # §XXIV.3 channel cosine (raw): ⟨G̃, F⟩/(||g|| · ||F||_F)  — unbounded when ρ≫1
        cos_theta_channel_raw = float(inner_GF / (ng * nF)) \
                                if ng > 1e-12 and nF > 1e-12 else 0.0

        return dict(
            # §XI pipeline outputs
            Xt_centred=Xt_centred,
            D=D,
            e_t=e_t,
            MFLS_t=MFLS_mah,
            gamma_star=gamma,
            Phi_t=Phi_t,
            lambda_bound=lam_bound,
            supercritical=lam_bound > 1.0,
            rho_proxy=rho_proxy,
            W_bar_off=W_bar_off,
            ccyb_norm=ccyb_norm,
            # additional closed-form outputs
            F_t=F_t,
            Phi_pair=Phi_pair,
            MFLS_state=MFLS_state,
            MFLS_channel=MFLS_channel,
            rho_MFLS=rho_MFLS,
            psi=psi,
            xi6=xi6,
            cos_theta_state=cos_theta_state,            # ∈ [-1,1]
            cos_theta_channel_raw=cos_theta_channel_raw,  # unbounded (theoretical)
        )
