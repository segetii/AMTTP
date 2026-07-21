"""Canonical Dynamical Geometry System v4 — reference implementation.

This subpackage is the literal, line-by-line implementation of
``canonical_system_v4.pdf`` (dated 2026-05-07).  Every public symbol here
maps to a numbered section of the PDF; the docstring of each class/function
cites the exact section.

Hierarchy
---------
* :mod:`core`         §3–§5, §7, §C.5, §D.3, §H.1   — the locked ODE kernel
* :mod:`verification` §10, §H.1.2                   — checklist & grad-check
* :mod:`domains`      §8.1–§8.4                     — 4 domain instantiations
* :mod:`extensions`   App. D–K                      — fractal / contact / flow / Fisher

The frozen kernel exposes a ``CanonicalSystem`` class.  All four domains and
all four extensions are instantiations of this same class — the locked ODE,
the gradient formula g_X = 2JᵀGS, and the Euclidean projection are NEVER
modified.  See :doc:`§11 (Structure Freeze)` for the immutability contract.
"""
from .core import CanonicalSystem, IntegrationResult
from .verification import (
    verify_gradient_fd,
    verification_checklist,
    ChecklistResult,
)
from .domains import (
    TradingDomain,
    GalerkinDomain,
    OptimisationDomain,
    RoboticsDomain,
)
from .extensions import (
    FractalRepresentation,
    ContactRepresentation,
    GeometricFlowMetric,
    FisherInformationMetric,
    natural_gradient,
    info_geometric_hessian,
    NaturalGradientFlow,
    MLEInstance,
    VIInstance,
)
from .stochastic import (
    fisher_noise,
    CanonicalSDE,
    SDETrajectory,
    expected_dE_dt,
    trace_correction,
    mean_square_ultimate_bound,
    natural_gradient_langevin,
)

__all__ = [
    "CanonicalSystem", "IntegrationResult",
    "verify_gradient_fd", "verification_checklist", "ChecklistResult",
    "TradingDomain", "GalerkinDomain", "OptimisationDomain", "RoboticsDomain",
    "FractalRepresentation", "ContactRepresentation",
    "GeometricFlowMetric", "FisherInformationMetric", "natural_gradient",
    "info_geometric_hessian", "NaturalGradientFlow",
    "MLEInstance", "VIInstance",
    "fisher_noise", "CanonicalSDE", "SDETrajectory",
    "expected_dE_dt", "trace_correction",
    "mean_square_ultimate_bound", "natural_gradient_langevin",
]
