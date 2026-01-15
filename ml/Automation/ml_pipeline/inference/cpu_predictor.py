"""
AMTTP ML Pipeline - CPU-Only Inference Service

Optimized for systems without GPU. Uses XGBoost and LightGBM
which run efficiently on CPU for inference.
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Force CPU mode
os.environ["CUDA_VISIBLE_DEVICES"] = ""


class CPUPredictor:
    """
    CPU-optimized fraud predictor.
    
    Uses XGBoost/LightGBM which are fast on CPU for inference.
    Handles feature name alignment automatically.
    """
    
    # OPTIMIZED thresholds - balanced for detection vs false positives
    # Based on F1 score optimization (Dec 2024)
    THRESHOLDS = {
        "xgb": 0.55,      # Optimal F1 score
        "lgbm": 0.55,     # Optimal F1 score
        "stacking": 0.60, # Slightly higher for ensemble
        "catboost": 0.55, # Optimal F1 score
    }
    
    def __init__(
        self,
        models_dir: str = "models/trained",
        primary_model: str = "xgb",  # xgb or lgbm recommended for CPU
    ):
        """
        Initialize CPU predictor.
        
        Args:
            models_dir: Path to trained models
            primary_model: Model to use (xgb, lgbm, stacking, catboost)
        """
        self.models_dir = Path(models_dir)
        self.primary_model = primary_model
        self.threshold = self.THRESHOLDS.get(primary_model, 0.5)
        
        self.model = None
        self.calibrator = None
        self.feature_names: List[str] = []
        
        self._load_feature_schema()
        self._load_model()
    
    def _load_feature_schema(self):
        """Load feature schema from JSON."""
        schema_path = self.models_dir.parent / "feature_schema.json"
        if schema_path.exists():
            with open(schema_path, "r") as f:
                schema = json.load(f)
                self.feature_names = schema.get("feature_names", [])
                logger.info(f"Loaded feature schema: {len(self.feature_names)} features")
        else:
            logger.warning(f"Feature schema not found at {schema_path}")
    
    def _load_model(self):
        """Load the primary model."""
        model_files = {
            "xgb": "xgb.json",
            "lgbm": "lgbm.txt",
            "stacking": "stacking_lgbm.txt",
            "catboost": "catboost.cbm",
        }
        
        model_file = model_files.get(self.primary_model)
        if not model_file:
            raise ValueError(f"Unknown model: {self.primary_model}")
        
        model_path = self.models_dir / model_file
        
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")
        
        # Load based on type
        if self.primary_model == "xgb":
            import xgboost as xgb
            self.model = xgb.Booster()
            self.model.load_model(str(model_path))
            # Get feature names from model if not loaded from schema
            if not self.feature_names and self.model.feature_names:
                self.feature_names = self.model.feature_names
            logger.info(f"Loaded XGBoost model from {model_path}")
            
        elif self.primary_model in ("lgbm", "stacking"):
            import lightgbm as lgb
            self.model = lgb.Booster(model_file=str(model_path))
            logger.info(f"Loaded LightGBM model from {model_path}")
            
        elif self.primary_model == "catboost":
            from catboost import CatBoostClassifier
            self.model = CatBoostClassifier()
            self.model.load_model(str(model_path))
            logger.info(f"Loaded CatBoost model from {model_path}")
        
        # Load calibrator if available
        calibrator_path = self.models_dir / f"{self.primary_model}_calibrator.joblib"
        if not calibrator_path.exists():
            calibrator_path = self.models_dir / "stacking_calibrator.joblib"
        
        if calibrator_path.exists():
            import joblib
            self.calibrator = joblib.load(calibrator_path)
            logger.info(f"Loaded calibrator from {calibrator_path}")
    
    def _prepare_features(self, X: Union[np.ndarray, pd.DataFrame, Dict[str, Any]]) -> np.ndarray:
        """
        Prepare features for prediction.
        
        Handles:
        - numpy arrays (must match feature count)
        - pandas DataFrames (columns aligned to feature names)
        - dict (single sample, keys are feature names)
        
        Returns:
            numpy array ready for model prediction
        """
        if isinstance(X, dict):
            # Single sample as dict
            X = pd.DataFrame([X])
        
        if isinstance(X, pd.DataFrame):
            # Align columns to expected features
            if self.feature_names:
                # Create DataFrame with all required features, fill missing with 0
                aligned = pd.DataFrame(0.0, index=X.index, columns=self.feature_names)
                for col in X.columns:
                    if col in self.feature_names:
                        aligned[col] = X[col]
                return aligned.values.astype(np.float32)
            else:
                return X.values.astype(np.float32)
        
        # numpy array - check dimensions
        X = np.asarray(X, dtype=np.float32)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        
        return X
    
    def predict_proba(self, X: Union[np.ndarray, pd.DataFrame, Dict]) -> np.ndarray:
        """
        Get fraud probability scores.
        
        Args:
            X: Feature matrix (n_samples, n_features), DataFrame, or dict
            
        Returns:
            Array of fraud probabilities (0-1)
        """
        X_prepared = self._prepare_features(X)
        
        if self.primary_model == "xgb":
            import xgboost as xgb
            # Create DMatrix with feature names
            if self.feature_names and X_prepared.shape[1] == len(self.feature_names):
                dmatrix = xgb.DMatrix(X_prepared, feature_names=self.feature_names)
            else:
                dmatrix = xgb.DMatrix(X_prepared)
            proba = self.model.predict(dmatrix)
            
        elif self.primary_model in ("lgbm", "stacking"):
            proba = self.model.predict(X_prepared)
            
        elif self.primary_model == "catboost":
            proba = self.model.predict_proba(X_prepared)[:, 1]
        
        # Apply calibration if available
        if self.calibrator is not None:
            proba = self.calibrator.predict_proba(proba.reshape(-1, 1))[:, 1]
        
        return proba
    
    def predict(self, X: Union[np.ndarray, pd.DataFrame, Dict]) -> np.ndarray:
        """Get binary predictions."""
        return (self.predict_proba(X) >= self.threshold).astype(int)
    
    def predict_with_action(self, X: Union[np.ndarray, pd.DataFrame, Dict]) -> List[Dict[str, Any]]:
        """Get predictions with recommended actions."""
        proba = self.predict_proba(X)
        
        results = []
        for score in proba:
            if score >= 0.99:
                action = "BLOCK"
            elif score >= 0.90:
                action = "ESCROW"
            elif score >= self.threshold:
                action = "REVIEW"
            elif score >= 0.5:
                action = "MONITOR"
            else:
                action = "APPROVE"
            
            results.append({
                "risk_score": float(score),
                "prediction": int(score >= self.threshold),
                "action": action,
            })
        
        return results
    
    def get_feature_names(self) -> List[str]:
        """Return expected feature names."""
        return self.feature_names.copy()
    
    def get_num_features(self) -> int:
        """Return number of expected features."""
        return len(self.feature_names)


def create_cpu_predictor(
    models_dir: str = "models/trained",
    model: str = "xgb",
) -> CPUPredictor:
    """Factory function to create CPU predictor."""
    return CPUPredictor(models_dir=models_dir, primary_model=model)
