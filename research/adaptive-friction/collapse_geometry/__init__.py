"""Collapse Geometry — full implementation of the §I–XXVII master operator spec.

Replaces the previous scattered "shadow" code (mfls-sdk, variants/, pipeline/, udl/)
with a single coherent package that implements every closed-form expression in the
mathematical anatomy document:

    state   §I             →  state.CalibrationState, state.Snapshot
    net     §II            →  network.LedoitWolfNetwork
    pot     §III           →  potential.Potential
    force   §IV            →  forces.ForceField
    bsdt    §VI, §XXIV.1   →  bsdt.BSDT  (4 channels + Jacobians)
    energy  §XII           →  unified_energy.UnifiedEnergy (Quadsurf+Expogate+SignedLR)
    mfls    §XXIV.4, §XXVI →  mfls.MFLS (channel + state + ρ + ψ)
    damp    §VIII          →  damping.AdaptiveDamping
    ctrl    §XIII, §XV     →  control.MasterOperator
    lyap    §XVI, §XXV     →  lyapunov.LyapunovCertificate
    geom    §XIV           →  geometry.CollapseGeometry (tan θ, three eq. conditions)
    ews     §XVII, §XXVI.3 →  ews.EarlyWarning (6 signals)
    esc     §XVIII         →  escape.EscapeTime
    sde     §XIX           →  stochastic.StochasticExtension
    inv     §XX            →  inverse.ParameterIdentification
    sens    §XXI           →  sensitivity.AgentSensitivity
    rec     §XXII          →  recovery.RecoveryDynamics
    info    §XXIII         →  info_theory.InformationGeometry
    eng     ---            →  engines.Gravity, engines.Molecular, engines.Hybrid

Public façade:
    >>> from collapse_geometry import MasterOperator
    >>> M = MasterOperator.calibrate(X_normal)
    >>> dXdt = M.step(X_t)
"""
from .state import CalibrationState, Snapshot
from .network import LedoitWolfNetwork
from .potential import Potential
from .forces import ForceField
from .bsdt import BSDT
from .unified_energy import UnifiedEnergy
from .mfls import MFLS
from .damping import AdaptiveDamping
from .control import MasterOperator
from .lyapunov import LyapunovCertificate
from .geometry import CollapseGeometry
from .ews import EarlyWarning
from .escape import EscapeTime
from .stochastic import StochasticExtension
from .inverse import ParameterIdentification
from .sensitivity import AgentSensitivity
from .recovery import RecoveryDynamics
from .info_theory import InformationGeometry
from .welfare import WelfareCalibration
from .engines import Gravity, Molecular, Hybrid

__all__ = [
    "CalibrationState", "Snapshot",
    "LedoitWolfNetwork", "Potential", "ForceField",
    "BSDT", "UnifiedEnergy", "MFLS",
    "AdaptiveDamping", "MasterOperator",
    "LyapunovCertificate", "CollapseGeometry", "EarlyWarning",
    "EscapeTime", "StochasticExtension",
    "ParameterIdentification", "AgentSensitivity", "RecoveryDynamics",
    "InformationGeometry", "WelfareCalibration",
    "Gravity", "Molecular", "Hybrid",
]
__version__ = "1.0.0"
