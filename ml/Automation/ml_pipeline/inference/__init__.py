# AMTTP ML Pipeline - Inference Module
"""
Inference module for CPU-based fraud detection.

Provides:
- CPUPredictor: XGBoost/LightGBM CPU inference
- InferenceService: FastAPI service wrapper

Usage:
    from ml_pipeline.inference import CPUPredictor
    
    predictor = CPUPredictor()
    results = predictor.predict_with_action(features_df)
"""

from .cpu_predictor import CPUPredictor
from .cpu_api import app as inference_app

__all__ = [
    "CPUPredictor",
    "inference_app",
]
