"""§XVII + §XXVI.3  Early Warning Score — two-layer system.

Layer B (geometry, §XVII.1): six normalised signals, geometric mean.
  ξ_1 = γ*                                     energy saturation
  ξ_2 = min(λ_max(∇²Φ), 1)                     spectral criticality
  ξ_3 = W̄_off                                  network synchrony
  ξ_4 = |cos θ_state|                          alignment magnitude
  ξ_5 = MFLS / (1 + MFLS)                      MFLS saturation
  ξ_6 = cos² ψ_t                               channel/state coherence
  EWS_B = (Π ξ_k^{w_k})^{1/Σw}  threshold: §XVII.2 closed-form / empirical μ+2σ

Layer A (precursor, §XVI.6 / §XXVI): four raw signals, normalised vs P95.
  p1 = max(0, P_t)           positive Lyapunov power (drift toward manifold)
  p2 = 1 − cos ψ_t           channel-misalignment growth
  p3 = std(S_t)              channel-state dispersion
  p4 = Σ_k |ΔS_k|            channel-state velocity (requires snap_prev)
  EWS_A = Σ_k w_k p_k / scale_k   threshold: 1.0 (P95-normalised)

PrecursorScale.from_panel(M, X_normal, pct=95) self-calibrates from the normal period.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np
from .control import MasterOperator
from .geometry import CollapseGeometry
from .lyapunov import LyapunovCertificate
from .network import LedoitWolfNetwork
from .state import Snapshot


# ─────────────────────────── Layer A: PrecursorScale ────────────────────────

@dataclass
class PrecursorScale:
    """95th-percentile denominators for the four Layer-A precursor signals.

    Calibrated from the normal period via from_panel(); alarms when the
    normalised precursor score reaches 1.0 (i.e. crosses its P95 baseline).

    Attributes
    ----------
    P_scale   : 95th-pct of max(0, P_t)   over the normal period
    psi_scale : 95th-pct of 1 − cos ψ_t  over the normal period
    S_scale   : 95th-pct of std(S_t)      over the normal period
    V_scale   : 95th-pct of Σ|ΔS_k|      over the normal period
    """
    P_scale: float
    psi_scale: float
    S_scale: float
    V_scale: float

    @classmethod
    def from_panel(cls, M: MasterOperator, X_normal: np.ndarray,
                   pct: float = 95.0) -> "PrecursorScale":
        """Calibrate scale denominators by sweeping the normal period.

        Parameters
        ----------
        M        : calibrated MasterOperator
        X_normal : (T0, N, d) normal-period panel (z-scored)
        pct      : percentile to use as alarm threshold denominator (default 95)
        """
        T0 = X_normal.shape[0]
        lyap = LyapunovCertificate(op=M)
        P_vals, psi_vals, S_vals, V_vals = [], [], [], []
        snap_prev: Optional[Snapshot] = None
        for t in range(T0):
            snap = Snapshot(
                X=X_normal[t],
                X_prev=X_normal[t - 1] if t > 0 else X_normal[0],
                history=X_normal[max(0, t - 5):t] if t > 0 else X_normal[0:1],
            )
            try:
                Pt = float(lyap._bundle(snap)["Pt"])
            except Exception:
                Pt = 0.0
            P_vals.append(max(0.0, Pt))

            try:
                p2 = float(1.0 - np.cos(M.mfls.psi(snap)))
            except Exception:
                p2 = 0.0
            psi_vals.append(p2)

            try:
                p3 = float(np.std(M.bsdt.channel_state(snap)))
            except Exception:
                p3 = 0.0
            S_vals.append(p3)

            if snap_prev is not None:
                try:
                    p4 = float(np.sum(np.abs(
                        M.bsdt.channel_state(snap) - M.bsdt.channel_state(snap_prev)
                    )))
                except Exception:
                    p4 = 0.0
            else:
                p4 = 0.0
            V_vals.append(p4)
            snap_prev = snap

        def _pct(arr: list) -> float:
            v = float(np.percentile(arr, pct))
            return max(v, 1e-9)   # floor prevents division-by-zero

        return cls(
            P_scale=_pct(P_vals),
            psi_scale=_pct(psi_vals),
            S_scale=_pct(S_vals),
            V_scale=_pct(V_vals),
        )


# ─────────────────────────── EarlyWarning ───────────────────────────────────

@dataclass
class EarlyWarning:
    op: MasterOperator
    geom: CollapseGeometry
    weights: np.ndarray = None          # type: ignore  Layer B (6 signals)
    precursor_weights: np.ndarray = None  # type: ignore  Layer A (4 signals)
    precursor_scale: Optional[PrecursorScale] = None

    def __post_init__(self):
        if self.weights is None:
            self.weights = np.ones(6) / 6.0
        if self.precursor_weights is None:
            self.precursor_weights = np.ones(4) / 4.0

    # ── Layer B: geometry signals (§XVII.1) ──────────────────────

    def signals(self, snap: Snapshot, network: Optional[LedoitWolfNetwork]) -> dict:
        gamma  = self.op.damp.gamma_star(snap)
        D      = snap.distance_matrix()
        lamPhi = max(0.0, min(self.op.potential.lambda_max_bound(D), 1.0))
        Wbar   = network.W_bar_off if network is not None else 0.0
        # ξ₄ = (1 + cos θ)/2 ∈ [0,1]: affine map, monotone in alignment.
        # Use cos_theta_channel (4D BSDT channel space) not cos_theta_state (64D):
        # in 64D, concentration of measure pins cosθ ≈ 0 always (std ≈ 0.002);
        # projecting via BSDT Jacobians into R⁴ gives cosθ std ≈ 0.5 → real variance.
        cos_t  = 0.5 * (1.0 + float(self.geom.cos_theta_channel(snap)))
        mfls_s = self.op.mfls.state_mfls(snap)
        psi    = self.op.mfls.psi(snap)
        return dict(
            xi1=gamma,
            xi2=lamPhi,
            xi3=max(0.0, min(1.0, Wbar)),
            xi4=cos_t,
            xi5=mfls_s / (1.0 + mfls_s),
            xi6=float(np.cos(psi) ** 2),
        )

    def score(self, snap: Snapshot,
              network: Optional[LedoitWolfNetwork] = None) -> float:
        s = self.signals(snap, network)
        xi = np.array([s["xi1"], s["xi2"], s["xi3"], s["xi4"], s["xi5"], s["xi6"]])
        xi = np.clip(xi, 1e-12, 1.0)
        return float(np.exp((self.weights * np.log(xi)).sum()))

    def threshold(self, theta: float, e_star: float) -> float:
        """§XVII.2 closed-form EWS* at the collapse manifold.

        Assumes spectral (ξ_2*=1) and alignment (ξ_4*=1) at criticality;
        network synchrony ξ_3*=0.5; energy saturation tied to e_star.
        """
        gamma_star = e_star / (e_star + theta)
        xi_star = np.array([gamma_star, 1.0, 0.5, 1.0,
                            e_star / (1.0 + e_star), 1.0])
        xi_star = np.clip(xi_star, 1e-12, 1.0)
        return float(np.exp((self.weights * np.log(xi_star)).sum()))

    # ── Layer A: precursor signals (§XVI.6 / §XXVI) ─────────────

    def precursor_signals(self, snap: Snapshot,
                          snap_prev: Optional[Snapshot] = None) -> dict:
        """Four raw (un-normalised) Layer-A precursor signals.

        p1 = max(0, P_t)  — positive Lyapunov power: drift toward manifold
        p2 = 1 − cos ψ_t  — channel-misalignment growth
        p3 = std(S_t)      — channel-state dispersion
        p4 = Σ|ΔS_k|       — channel-state velocity (0 when snap_prev=None)
        """
        lyap = LyapunovCertificate(op=self.op)
        try:
            p1 = max(0.0, float(lyap._bundle(snap)["Pt"]))
        except Exception:
            p1 = 0.0

        try:
            p2 = float(1.0 - np.cos(self.op.mfls.psi(snap)))
        except Exception:
            p2 = 0.0

        try:
            p3 = float(np.std(self.op.bsdt.channel_state(snap)))
        except Exception:
            p3 = 0.0

        p4 = 0.0
        if snap_prev is not None:
            try:
                p4 = float(np.sum(np.abs(
                    self.op.bsdt.channel_state(snap)
                    - self.op.bsdt.channel_state(snap_prev)
                )))
            except Exception:
                p4 = 0.0

        return dict(p1=p1, p2=p2, p3=p3, p4=p4)

    def precursor_score(self, snap: Snapshot,
                        snap_prev: Optional[Snapshot] = None) -> float:
        """Normalised Layer-A score.  ≥ 1.0 → alarm (above P95 normal boundary).

        When no PrecursorScale is attached, raw signals are summed with equal
        weights (useful for relative comparisons but not threshold-calibrated).
        """
        sigs = self.precursor_signals(snap, snap_prev)
        p = np.array([sigs["p1"], sigs["p2"], sigs["p3"], sigs["p4"]])
        if self.precursor_scale is not None:
            scales = np.array([
                self.precursor_scale.P_scale,
                self.precursor_scale.psi_scale,
                self.precursor_scale.S_scale,
                self.precursor_scale.V_scale,
            ])
        else:
            scales = np.ones(4)
        # max over channels: alarm when ANY single signal exceeds its P95 normal
        # baseline — gives earliest possible trigger (vs sum which dilutes spikes)
        return float(np.max(p / scales))

    # ── Combined two-layer decision ──────────────────────────────

    def two_layer(self, snap: Snapshot,
                  network: Optional[LedoitWolfNetwork],
                  snap_prev: Optional[Snapshot],
                  e_star: float,
                  geometry_threshold: Optional[float] = None) -> dict:
        """Evaluate Layer A and Layer B and return combined alarm state.

        Parameters
        ----------
        geometry_threshold : override for Layer B threshold (e.g. empirical μ+2σ);
                             falls back to the §XVII.2 closed-form if None.

        Returns
        -------
        dict with keys:
          geometry_score    : float  Layer B geometric mean score
          precursor_score   : float  Layer A normalised score (alarm at ≥ 1.0)
          geometry_alarm    : bool   Layer B ≥ geometry_threshold
          precursor_alarm   : bool   Layer A ≥ 1.0
          alarm             : bool   either layer alarming
          layer             : str    "A", "B", "AB", or ""
          geometry_signals  : dict   raw ξ values
          precursor_signals : dict   raw p values
        """
        geom_score = self.score(snap, network)
        geom_sigs  = self.signals(snap, network)
        pre_score  = self.precursor_score(snap, snap_prev)
        pre_sigs   = self.precursor_signals(snap, snap_prev)

        if geometry_threshold is None:
            geometry_threshold = self.threshold(
                theta=self.op.damp.theta, e_star=e_star
            )
        g_alarm = geom_score >= geometry_threshold
        a_alarm = pre_score >= 1.0
        layers  = ("A" if a_alarm else "") + ("B" if g_alarm else "")
        return dict(
            geometry_score=geom_score,
            precursor_score=pre_score,
            geometry_alarm=g_alarm,
            precursor_alarm=a_alarm,
            alarm=g_alarm or a_alarm,
            layer=layers,
            geometry_signals=geom_sigs,
            precursor_signals=pre_sigs,
        )
