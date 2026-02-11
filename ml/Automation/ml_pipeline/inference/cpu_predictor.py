"""
AMTTP ML Pipeline - CPU-Only Inference Service

Optimized for systems without GPU. Uses XGBoost and LightGBM
which run efficiently on CPU for inference.

Threshold strategy: percentile-based (rank within reference distribution)
rather than absolute probability cutoffs, because raw model probabilities
are poorly calibrated across different data distributions.
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
    
    Threshold strategy:
      - Binary classification uses a calibrated threshold loaded from
        training metadata (``thresholds.json``), falling back to
        percentile-based search on a reference score distribution.
      - Risk-level actions (BLOCK / ESCROW / REVIEW / MONITOR / APPROVE)
        are assigned by percentile rank within the reference distribution
        so they remain valid even when raw probability scales shift.
    """
    
    # Percentile-based risk tiers (top-N% of reference distribution)
    # These are used ONLY when a reference distribution is available.
    RISK_PERCENTILES = {
        "BLOCK":   99.0,   # top 1%
        "ESCROW":  95.0,   # top 5%
        "REVIEW":  85.0,   # top 15%
        "MONITOR": 70.0,   # top 30%
        # everything below → APPROVE
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
        
        self.model = None
        self.calibrator = None
        self.feature_names: List[str] = []
        self.threshold: float = 0.5            # default; overridden below
        self.reference_scores: Optional[np.ndarray] = None
        self.risk_cutoffs: Dict[str, float] = {}
        
        self._load_feature_schema()
        self._load_thresholds()
        self._load_reference_distribution()
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
    
    def _load_thresholds(self):
        """Load calibrated binary-classification threshold from training metadata.
        
        Looks for ``thresholds.json`` next to the model files.  Format::
        
            {"xgb": 0.0004, "lgbm": 0.0005, ...}
        
        These values are the *optimal F1 thresholds* computed during training
        and may be very small if the model's raw probabilities are compressed.
        """
        th_path = self.models_dir.parent / "thresholds.json"
        if th_path.exists():
            with open(th_path, "r") as f:
                th_data = json.load(f)
            if self.primary_model in th_data:
                self.threshold = float(th_data[self.primary_model])
                logger.info(f"Loaded calibrated threshold for {self.primary_model}: {self.threshold}")
                return
        # Fallback: use a percentile-based threshold if reference distribution exists
        logger.info("No thresholds.json found; will use percentile-based threshold")
    
    def _load_reference_distribution(self):
        """Load a saved reference score distribution from training.
        
        The file ``reference_scores_<model>.npy`` stores the sorted raw
        probabilities from the validation set, enabling percentile-rank
        conversion at inference time.
        """
        ref_path = self.models_dir.parent / f"reference_scores_{self.primary_model}.npy"
        if not ref_path.exists():
            ref_path = self.models_dir.parent / "reference_scores.npy"
        
        if ref_path.exists():
            self.reference_scores = np.sort(np.load(ref_path).ravel())
            # Pre-compute absolute cutoffs from percentile tiers
            for level, pctile in self.RISK_PERCENTILES.items():
                self.risk_cutoffs[level] = float(np.percentile(self.reference_scores, pctile))
            logger.info(
                f"Loaded reference distribution ({len(self.reference_scores)} scores). "
                f"Risk cutoffs: { {k: f'{v:.6f}' for k, v in self.risk_cutoffs.items()} }"
            )
            # If no calibrated threshold was loaded, derive one from the reference
            # distribution at the 85th percentile (top-15% flagged as fraud).
            th_path = self.models_dir.parent / "thresholds.json"
            if not th_path.exists():
                self.threshold = float(np.percentile(self.reference_scores, 85))
                logger.info(f"Derived threshold from reference distribution (p85): {self.threshold}")
        else:
            logger.warning("No reference score distribution found — risk tiers will use fallback heuristic")
    
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
        """Get binary predictions using the calibrated threshold."""
        return (self.predict_proba(X) >= self.threshold).astype(int)
    
    def _score_to_percentile(self, scores: np.ndarray) -> np.ndarray:
        """Convert raw scores to percentile ranks within the reference distribution.
        
        Returns values in [0, 100].  If no reference distribution is loaded,
        falls back to rank within the current batch (less stable for small
        batches but still distribution-agnostic).
        """
        if self.reference_scores is not None and len(self.reference_scores) > 0:
            # np.searchsorted gives the insertion point in the sorted reference
            ranks = np.searchsorted(self.reference_scores, scores, side="right")
            return 100.0 * ranks / len(self.reference_scores)
        else:
            # Fallback: rank within the batch itself
            if len(scores) <= 1:
                return np.array([50.0] * len(scores))
            order = scores.argsort().argsort()  # rank
            return 100.0 * order / (len(scores) - 1)
    
    def predict_with_action(self, X: Union[np.ndarray, pd.DataFrame, Dict]) -> List[Dict[str, Any]]:
        """Get predictions with recommended actions based on percentile rank.
        
        Risk tiers are assigned by where a score falls in the reference
        distribution (or in-batch rank as fallback), NOT by absolute
        probability cutoffs.  This ensures consistent behaviour even when
        the model's probability scale changes across datasets.
        """
        proba = self.predict_proba(X)
        pctiles = self._score_to_percentile(proba)
        
        results = []
        for score, pct in zip(proba, pctiles):
            if self.risk_cutoffs:
                # Use pre-computed absolute cutoffs from reference distribution
                if score >= self.risk_cutoffs.get("BLOCK", float("inf")):
                    action = "BLOCK"
                elif score >= self.risk_cutoffs.get("ESCROW", float("inf")):
                    action = "ESCROW"
                elif score >= self.risk_cutoffs.get("REVIEW", float("inf")):
                    action = "REVIEW"
                elif score >= self.risk_cutoffs.get("MONITOR", float("inf")):
                    action = "MONITOR"
                else:
                    action = "APPROVE"
            else:
                # Fallback: use percentile rank directly
                if pct >= self.RISK_PERCENTILES["BLOCK"]:
                    action = "BLOCK"
                elif pct >= self.RISK_PERCENTILES["ESCROW"]:
                    action = "ESCROW"
                elif pct >= self.RISK_PERCENTILES["REVIEW"]:
                    action = "REVIEW"
                elif pct >= self.RISK_PERCENTILES["MONITOR"]:
                    action = "MONITOR"
                else:
                    action = "APPROVE"
            
            results.append({
                "risk_score": float(score),
                "percentile": float(pct),
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
