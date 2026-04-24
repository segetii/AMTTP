"""Unified per-snapshot diagnostics for all three engines (§I–XXVII).

Single entry point ``engine_diagnostics(op, snap, *, V=None, network=None)``
that returns a closed-form dict containing every primary output of the §I–XXVII
master operator spec — usable identically from Gravity, Molecular and Hybrid.

Layers exposed
--------------
1. §XI Master Pipeline (10 outputs)        via op.pipeline(snap, network=...)
2. §XIV Three collapse conditions          (spectral, angular, energetic)
3. §XVI Lyapunov certificate               P_t, Q_t, R_t, dV/dt, M_t, γ*_min, θ_ceiling
4. §XXV Per-channel decomposition          V̇_C, V̇_G, V̇_A, V̇_T   (drift + control + η + a_k)
5. §XII.5 Channel attribution               c_k = [g_k]² / ||g||²    + dominant channel
6. §XVII + §XXVI.3  6-signal EWS           ξ_1…ξ_6 + composite score + reliability ξ_6
7. Engine kinematics                        kinetic energy, ||V|| when V is supplied

Pure read-only — does not advance the system.
"""
from __future__ import annotations
from typing import Optional
import numpy as np

from ..control import MasterOperator
from ..state import Snapshot
from ..lyapunov import LyapunovCertificate
from ..geometry import CollapseGeometry
from ..ews import EarlyWarning
from ..network import LedoitWolfNetwork


def engine_diagnostics(op: MasterOperator,
                       snap: Snapshot,
                       *,
                       V: Optional[np.ndarray] = None,
                       mass: float = 1.0,
                       network: Optional[LedoitWolfNetwork] = None,
                       sigma_ell: Optional[float] = None) -> dict:
    """Compute every §I–XXVII primary output for a single snapshot.

    Parameters
    ----------
    op         : calibrated MasterOperator (shared by all three engines)
    snap       : current Snapshot X_t  (with X_prev / history populated for δ_A, δ_T)
    V          : optional velocity matrix (N,d) — Molecular / Hybrid only
    mass       : particle mass for kinetic energy when V is supplied
    network    : optional pre-built LedoitWolfNetwork; otherwise built from leverage col
    sigma_ell  : optional cross-sectional std of leverage; default snap.X[:,0].std()

    Returns
    -------
    dict with grouped keys: 'pipeline', 'conditions', 'lyapunov', 'channels',
    'attribution', 'ews', 'kinematics'.  Flat scalars at top level for the most
    commonly queried quantities (e_t, MFLS_state, MFLS_channel, rho_MFLS, psi,
    xi6, gamma_star, ews_score).
    """
    # 1. §XI master pipeline (already includes ψ, ξ6, ρ_MFLS, etc.)
    pipe = op.pipeline(snap, network=network, sigma_ell=sigma_ell)

    # 2. §XIV three equivalent collapse conditions
    geom = CollapseGeometry(op=op)
    conditions = geom.all_conditions(snap)
    conditions["tan_theta"]      = geom.tan_theta(snap)
    conditions["tan_theta_star"] = geom.tan_theta_star(snap)

    # 3. §XVI Lyapunov bundle + scalars + ceiling
    lyap = LyapunovCertificate(op=op)
    bundle = lyap._bundle(snap)
    lyapunov = dict(
        P_t          = bundle["Pt"],
        Q_t          = bundle["Qt"],
        R_t          = bundle["Rt"],
        g_norm2      = bundle["gnorm2"],
        dV_dt        = lyap.dV_dt(snap),
        margin       = lyap.margin(snap),
        gamma_min    = lyap.gamma_min(snap),
        theta_ceiling= lyap.theta_ceiling(snap),
        mfls_rate    = lyap.mfls_rate(snap),
    )

    # 4. §XXV per-channel decomposition (V̇_k drift / control / total / η / attribution)
    channels = lyap.channel_decomposition(snap)

    # 5. §XII.5 channel attribution c_k from gradient (purely from g_t)
    S = op.bsdt.channel_state(snap)
    attribution = dict(
        c_k             = op.energy.channel_attribution(S).tolist(),
        dominant_channel= ("C", "G", "A", "T")[op.energy.dominant_channel(S)],
    )

    # 6. §XVII + §XXVI.3 six-signal EWS (build a network if not supplied)
    if network is None:
        try:
            lev = snap.X[:, 0:1].T
            net_for_ews = LedoitWolfNetwork.from_panel(np.vstack([lev, lev + 1e-6]))
        except Exception:
            net_for_ews = None
    else:
        net_for_ews = network
    ew = EarlyWarning(op=op, geom=geom)
    sigs  = ew.signals(snap, net_for_ews)
    score = ew.score(snap, net_for_ews)
    ews   = dict(**sigs, score=score)

    # 7. Engine kinematics  (Gravity has no V → zeros)
    if V is None:
        V = np.zeros_like(snap.X)
    kinematics = dict(
        kinetic_energy = float(0.5 * mass * (V * V).sum()),
        speed_mean     = float(np.linalg.norm(V, axis=1).mean()),
        speed_max      = float(np.linalg.norm(V, axis=1).max(initial=0.0)),
    )

    return dict(
        # Grouped layers
        pipeline    = pipe,
        conditions  = conditions,
        lyapunov    = lyapunov,
        channels    = channels,
        attribution = attribution,
        ews         = ews,
        kinematics  = kinematics,
        # Flat scalars (most common queries)
        e_t          = pipe["e_t"],
        gamma_star   = pipe["gamma_star"],
        MFLS_state   = pipe["MFLS_state"],
        MFLS_channel = pipe["MFLS_channel"],
        rho_MFLS     = pipe["rho_MFLS"],
        psi          = pipe["psi"],
        xi6          = pipe["xi6"],
        ews_score    = score,
        margin       = lyapunov["margin"],
    )
