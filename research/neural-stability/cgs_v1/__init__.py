"""
CGS-v1 — Canonical Geometric System, version 1.

Implements the seven theorem-level extensions of CEK-v4 plus the
gap-closure addenda (G1 numerics, G2 Fisher-noise SDE, port-Hamiltonian
composition, closed-form collapse horizon).

Reference manuscripts:
    research/adaptive-friction/pipeline/results/canonicaldocument_pdf.pdf
    research/adaptive-friction/pipeline/results/canonicalgapdocument_pdf.pdf
    research/adaptive-friction/pipeline/results/CGS_v1_manuscript.pdf
    research/adaptive-friction/pipeline/results/Complete_Derivations_Full.pdf
    research/adaptive-friction/pipeline/results/math reference corrected.pdf

The CEK-v4 Euclidean kernel (frozen) lives in
    research/neural-stability/canonical_v4_engine.py
and is the special case of CGSCore with identity projection.

Author: Odeyemi Olusegun Israel
"""
from .core import CanonicalTriple, CGSCore, canonical_step, EPS
from .integrators import (
    euler_step, rk4_step, adaptive_euler_rollout,
    energy_increment_bound,
)
from .symplectic import SymplecticCanonical
from .lie_group import LieGroupCanonical, so_n_bracket, se3_log, se3_exp
from .pareto import ParetoCanonical, common_descent_cone_projection
from .graph_wavelet import GraphWaveletCanonical, diffusion_wavelet_basis
from .kurtosis_spd import KurtosisCorrectedSPD
from .robust import RobustAdversarialCanonical
from .delay import DelayCanonical, lyapunov_krasovskii_value
from .port_hamiltonian import PortHamiltonianComposite
from .fisher_sde import FisherNoiseSDE, free_energy
from .collapse_horizon import (
    closed_form_collapse_horizon,
    spectral_radius_proxy,
    ledoit_wolf_shrinkage,
)

__all__ = [
    "CanonicalTriple", "CGSCore", "canonical_step", "EPS",
    "euler_step", "rk4_step", "adaptive_euler_rollout", "energy_increment_bound",
    "SymplecticCanonical",
    "LieGroupCanonical", "so_n_bracket", "se3_log", "se3_exp",
    "ParetoCanonical", "common_descent_cone_projection",
    "GraphWaveletCanonical", "diffusion_wavelet_basis",
    "KurtosisCorrectedSPD",
    "RobustAdversarialCanonical",
    "DelayCanonical", "lyapunov_krasovskii_value",
    "PortHamiltonianComposite",
    "FisherNoiseSDE", "free_energy",
    "closed_form_collapse_horizon", "spectral_radius_proxy", "ledoit_wolf_shrinkage",
]
