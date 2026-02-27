"""
Universal Deviation Law (UDL) — Python Framework
=================================================
A multi-spectrum tensor framework for anomaly detection.

Extends BSDT (Blind Spot Decomposition Theory) into a universal,
law-based observation framework that detects anomalies across:
  - Statistical/probabilistic law domain
  - Chaos/dynamical law domain
  - Spectral/frequency law domain
  - Geometric/manifold law domain
  - Exponential/energy amplification layer

Pipeline:
  Raw Observation → Representation Stack → Tensor → Centroid → Projection → Detection

Author: Research Framework
License: Proprietary — IP Protected
"""

__version__ = "0.1.0"

from .spectra import (
    StatisticalSpectrum,
    ChaosSpectrum,
    SpectralSpectrum,
    GeometricSpectrum,
    ExponentialSpectrum,
    ReconstructionSpectrum,
    RankOrderSpectrum,
)
from .stack import RepresentationStack
from .centroid import CentroidEstimator
from .tensor import AnomalyTensor, TensorResult
from .projection import HyperplaneProjector
from .pipeline import UDLPipeline
from .rank_fusion import RankFusionPipeline
from .hybrid_pipeline import HybridPipeline
from .rl_fusion import RLFusionAgent
from .meta_fusion import MetaFusionPipeline
from .datasets import load_dataset, list_datasets
from .bsdt_bridge import BSDTSpectrum, BSDTAugmentedStack
from .mfls_weighting import MFLSWeighting
from .calibration import ScoreCalibrator
from .law_matrix import DataProfile, select_laws, get_law_matrix_table
from .energy import DeviationEnergy, OperatorDiversity, EnergyFlow, StabilityAnalyser
from .gravity import GravityEngine, run_gravity_clustering
from .backend import xp, jit, vmap, to_numpy, from_numpy, BACKEND

__all__ = [
    # Core pipeline
    "UDLPipeline",
    "RankFusionPipeline",
    "HybridPipeline",
    "RLFusionAgent",
    "RepresentationStack",
    "AnomalyTensor",
    "TensorResult",
    "CentroidEstimator",
    "HyperplaneProjector",
    # Spectrum operators
    "StatisticalSpectrum",
    "ChaosSpectrum",
    "SpectralSpectrum",
    "GeometricSpectrum",
    "ExponentialSpectrum",
    "ReconstructionSpectrum",
    "RankOrderSpectrum",
    # Datasets
    "load_dataset",
    "list_datasets",
    # BSDT Bridge
    "BSDTSpectrum",
    "BSDTAugmentedStack",
    # Calibration
    "ScoreCalibrator",
    # Law auto-selection
    "DataProfile",
    "select_laws",
    "get_law_matrix_table",
    # Energy functional
    "DeviationEnergy",
    "OperatorDiversity",
    "EnergyFlow",
    "StabilityAnalyser",
    # Gravity engine
    "GravityEngine",
    "run_gravity_clustering",
    # Backend (JAX / CuPy / NumPy)
    "xp",
    "jit",
    "vmap",
    "to_numpy",
    "from_numpy",
    "BACKEND",
]
