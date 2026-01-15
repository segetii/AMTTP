# AMTTP ML Pipeline
"""
AMTTP Machine Learning Pipeline - Production Inference

A streamlined fraud detection pipeline for CPU inference with:
- XGBoost CPU inference
- Memgraph graph-based features
- Hybrid prediction (tabular + graph)

Usage:
    # CPU Inference
    from ml_pipeline.inference import CPUPredictor
    
    predictor = CPUPredictor()
    result = predictor.predict(features)
    
    # Graph-enhanced prediction
    from ml_pipeline.graph import MemgraphService, HybridPredictor
    
    hybrid = HybridPredictor()
    result = hybrid.predict(address, features)
"""

__version__ = "2.0.0"
__author__ = "AMTTP Team"

# Inference exports
from .inference.cpu_predictor import CPUPredictor

# Graph exports  
from .graph.service import MemgraphService, MemgraphConfig, get_memgraph_service
from .graph.features import GraphFeatureExtractor
from .graph.hybrid_predictor import HybridPredictor

__all__ = [
    # Inference
    "CPUPredictor",
    # Graph
    "MemgraphService",
    "MemgraphConfig", 
    "get_memgraph_service",
    "GraphFeatureExtractor",
    "HybridPredictor",
]
