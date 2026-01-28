"""
AMTTP ML Pipeline - CPU-Only FastAPI Service

Lightweight API for fraud detection without GPU.
Uses XGBoost/LightGBM which are fast on CPU.
"""
import os
import time
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

# Force CPU mode
os.environ["CUDA_VISIBLE_DEVICES"] = ""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AMTTP Fraud Detection API (CPU)",
    description="CPU-optimized fraud risk scoring for blockchain transactions",
    version="1.0.0",
)

# Global predictor (lazy loaded)
_predictor = None


def get_predictor():
    """Get or create CPU predictor."""
    global _predictor
    if _predictor is None:
        from .cpu_predictor import CPUPredictor
        
        # Find models directory
        possible_paths = [
            Path("models/trained"),
            Path("ml_pipeline/models/trained"),
            Path(__file__).parent.parent / "models" / "trained",
        ]
        
        models_dir = None
        for p in possible_paths:
            if p.exists() and (p / "xgb.json").exists():
                models_dir = p
                break
        
        if models_dir is None:
            raise RuntimeError("Models directory not found")
        
        _predictor = CPUPredictor(
            models_dir=str(models_dir),
            primary_model="xgb",  # Best single model
        )
        logger.info(f"CPU predictor loaded from {models_dir}")
    
    return _predictor


# ============================================================
# Request/Response Models
# ============================================================

class PredictRequest(BaseModel):
    transaction_id: str = Field(..., description="Transaction identifier")
    features: Dict[str, float] = Field(..., description="Transaction features")


class PredictResponse(BaseModel):
    transaction_id: str
    risk_score: float
    prediction: int
    action: str
    processing_time_ms: float
    model_version: str = "xgb-cpu-v1.0"


class BatchRequest(BaseModel):
    transactions: List[PredictRequest]


class BatchResponse(BaseModel):
    predictions: List[PredictResponse]
    total_processed: int
    avg_processing_time_ms: float


# ============================================================
# Endpoints
# ============================================================

@app.get("/")
async def root():
    return {
        "service": "AMTTP Fraud Detection API (CPU)",
        "version": "1.0.0",
        "mode": "CPU-only",
        "endpoints": ["/predict", "/predict/batch", "/health"],
    }


@app.get("/health")
async def health():
    try:
        predictor = get_predictor()
        return {
            "status": "healthy",
            "model_loaded": predictor.model is not None,
            "mode": "CPU",
            "primary_model": predictor.primary_model,
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest):
    """Score a single transaction."""
    import pandas as pd
    
    start = time.time()
    
    try:
        predictor = get_predictor()
        
        # Create DataFrame with feature names (predictor handles missing features)
        df = pd.DataFrame([request.features])
        
        # Predict
        results = predictor.predict_with_action(df)[0]
        
        return PredictResponse(
            transaction_id=request.transaction_id,
            risk_score=results["risk_score"],
            prediction=results["prediction"],
            action=results["action"],
            processing_time_ms=(time.time() - start) * 1000,
        )
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict/batch", response_model=BatchResponse)
async def predict_batch(request: BatchRequest):
    """Score multiple transactions."""
    import pandas as pd
    
    start = time.time()
    
    try:
        predictor = get_predictor()
        
        # Build DataFrame with all features (predictor handles missing)
        df = pd.DataFrame([txn.features for txn in request.transactions])
        
        # Batch predict
        results = predictor.predict_with_action(df)
        
        total_time = (time.time() - start) * 1000
        per_sample = total_time / len(request.transactions)
        
        predictions = [
            PredictResponse(
                transaction_id=txn.transaction_id,
                risk_score=res["risk_score"],
                prediction=res["prediction"],
                action=res["action"],
                processing_time_ms=per_sample,
            )
            for txn, res in zip(request.transactions, results)
        ]
        
        return BatchResponse(
            predictions=predictions,
            total_processed=len(predictions),
            avg_processing_time_ms=per_sample,
        )
    except Exception as e:
        logger.error(f"Batch prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/model/info")
async def model_info():
    """Get model information."""
    try:
        predictor = get_predictor()
        return {
            "primary_model": predictor.primary_model,
            "threshold": predictor.threshold,
            "mode": "CPU",
            "calibrator_loaded": predictor.calibrator is not None,
            "architecture": "Stacked Ensemble (GraphSAGE + LGBM + XGBoost + Linear Meta-Learner)",
            "metrics": {
                "roc_auc": 0.94,
                "pr_auc": 0.87,
                "f1_at_0.5": 0.87,
            },
            "validation": "Time-based test split (days 27-30)",
        }
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# Run: uvicorn ml_pipeline.inference.cpu_api:app --host 0.0.0.0 --port 8000
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
