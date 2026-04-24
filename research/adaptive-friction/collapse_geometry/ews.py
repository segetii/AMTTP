"""§XVII + §XXVI.3  Early Warning Score — six normalised signals, geometric mean.

ξ_1 = γ*                                     energy saturation
ξ_2 = min(λ_max(∇²Φ), 1)                     spectral criticality
ξ_3 = W̄_off                                  network synchrony
ξ_4 = max(0, cos θ_state)                    alignment (state-space)
ξ_5 = MFLS / (1 + MFLS)                      MFLS saturation
ξ_6 = cos² ψ_t                               channel/state coherence

EWS = (Π ξ_k^{w_k})^{1/Σw}  with default equal weights.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .control import MasterOperator
from .geometry import CollapseGeometry
from .network import LedoitWolfNetwork
from .state import Snapshot


@dataclass
class EarlyWarning:
    op: MasterOperator
    geom: CollapseGeometry
    weights: np.ndarray = None  # type: ignore

    def __post_init__(self):
        if self.weights is None:
            self.weights = np.ones(6) / 6.0

    def signals(self, snap: Snapshot, network: LedoitWolfNetwork | None) -> dict:
        gamma  = self.op.damp.gamma_star(snap)
        D      = snap.distance_matrix()
        lamPhi = min(self.op.potential.lambda_max_bound(D), 1.0)
        Wbar   = network.W_bar_off if network is not None else 0.0
        # alignment magnitude (|cos θ|): collapse manifold is reached when the
        # Mahalanobis projection onto the collapse normal saturates regardless
        # of sign — clipping negatives to 0 (per the original §XVII.1 wording)
        # made EWS structurally unable to fire on real crises whose drift is
        # opposite to the calibration mean direction. Using |cos θ| restores
        # the early-warning capability the prior pipeline had.
        cos_t  = abs(self.geom.cos_theta_state(snap))
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

    def score(self, snap: Snapshot, network: LedoitWolfNetwork | None = None) -> float:
        s = self.signals(snap, network)
        xi = np.array([s["xi1"], s["xi2"], s["xi3"], s["xi4"], s["xi5"], s["xi6"]])
        xi = np.clip(xi, 1e-12, 1.0)
        return float(np.exp((self.weights * np.log(xi)).sum()))

    # §XVII.2 critical threshold  EWS* = Π ξ_k*^{w_k}  at the manifold (ξ_2*=1, ξ_4*=1)
    def threshold(self, theta: float, e_star: float) -> float:
        """Closed-form EWS* assuming spectral & alignment at criticality, others at
        their normal-period 1-σ default (xi_3* = 0.5, xi_5* tied to e_star)."""
        gamma_star = e_star / (e_star + theta)
        xi_star = np.array([gamma_star, 1.0, 0.5, 1.0,
                            e_star / (1.0 + e_star), 1.0])
        xi_star = np.clip(xi_star, 1e-12, 1.0)
        return float(np.exp((self.weights * np.log(xi_star)).sum()))
