"""
AMTTP ML Pipeline - Graph API Endpoints

FastAPI endpoints for graph-based fraud detection.
Integrates Memgraph graph analysis with ML predictions.
"""
import os
import time
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

# Force CPU mode
os.environ["CUDA_VISIBLE_DEVICES"] = ""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AMTTP Graph-Enhanced Fraud Detection API",
    description="Hybrid fraud detection using ML + Memgraph graph analysis",
    version="1.0.0",
)

# Global instances (lazy loaded)
_hybrid_predictor = None
_graph_service = None
_graph_updater = None


def get_hybrid_predictor():
    """Get or create hybrid predictor."""
    global _hybrid_predictor
    if _hybrid_predictor is None:
        from .hybrid_predictor import HybridPredictor
        
        models_dir = Path(__file__).parent.parent / "models" / "trained"
        _hybrid_predictor = HybridPredictor(models_dir=str(models_dir))
        logger.info("Hybrid predictor initialized")
    
    return _hybrid_predictor


def get_graph_service():
    """Get or create graph service."""
    global _graph_service
    if _graph_service is None:
        from .service import get_memgraph_service
        _graph_service = get_memgraph_service()
    return _graph_service


def get_graph_updater():
    """Get or create graph updater."""
    global _graph_updater
    if _graph_updater is None:
        from .updater import GraphUpdater
        _graph_updater = GraphUpdater(get_graph_service())
    return _graph_updater


# ============================================================
# Request/Response Models
# ============================================================

class HybridPredictRequest(BaseModel):
    transaction_id: str = Field(..., description="Transaction identifier")
    features: Dict[str, float] = Field(..., description="Tabular features")
    from_address: Optional[str] = Field(None, description="Sender address")
    to_address: Optional[str] = Field(None, description="Receiver address")


class HybridPredictResponse(BaseModel):
    transaction_id: str
    # Tabular results
    tabular_risk_score: float
    tabular_action: str
    # Graph results
    graph_risk_score: float
    graph_features: Dict[str, Any]
    # Combined
    combined_risk_score: float
    combined_action: str
    confidence: float
    processing_time_ms: float


class BatchPredictRequest(BaseModel):
    transactions: List[HybridPredictRequest]


class BatchPredictResponse(BaseModel):
    predictions: List[HybridPredictResponse]
    total_processed: int
    avg_processing_time_ms: float


class AddressRiskRequest(BaseModel):
    address: str = Field(..., description="Ethereum address")


class AddressRiskResponse(BaseModel):
    address: str
    graph_risk_score: float
    sanctions_distance: int
    is_sanctioned_neighbor: bool
    is_mixer_connected: bool
    in_degree: int
    out_degree: int
    community_id: int
    community_risk: float


class AddTransactionRequest(BaseModel):
    hash: str
    from_address: str
    to_address: str
    value: float
    timestamp: int
    block_number: int = 0


class TagAddressRequest(BaseModel):
    address: str
    tag: str = Field(..., description="Tag: sanctioned, mixer, exchange, etc.")


# ============================================================
# Endpoints
# ============================================================

@app.get("/")
async def root():
    predictor = get_hybrid_predictor()
    return {
        "service": "AMTTP Graph-Enhanced Fraud Detection API",
        "version": "1.0.0",
        "mode": "hybrid" if predictor.is_graph_available() else "tabular-only",
        "endpoints": [
            "/predict/hybrid",
            "/predict/batch",
            "/graph/address-risk",
            "/graph/stats",
            "/graph/add-transaction",
            "/graph/tag-address",
            "/health",
        ],
    }


@app.get("/health")
async def health():
    predictor = get_hybrid_predictor()
    
    result = {
        "status": "healthy",
        "tabular_model": predictor.tabular.primary_model,
        "graph_available": predictor.is_graph_available(),
    }
    
    if predictor.is_graph_available():
        try:
            graph_health = get_graph_service().health_check()
            result["graph"] = graph_health
        except Exception as e:
            result["graph"] = {"status": "error", "message": str(e)}
    
    return result


@app.post("/predict/hybrid", response_model=HybridPredictResponse)
async def predict_hybrid(request: HybridPredictRequest):
    """
    Make a hybrid prediction using tabular ML + graph features.
    
    Combines:
    - XGBoost tabular model (70% weight)
    - Memgraph graph analysis (30% weight)
    """
    start = time.time()
    
    try:
        predictor = get_hybrid_predictor()
        
        result = predictor.predict(
            transaction_id=request.transaction_id,
            tabular_features=request.features,
            from_address=request.from_address,
            to_address=request.to_address,
        )
        
        return HybridPredictResponse(
            transaction_id=result.transaction_id,
            tabular_risk_score=result.tabular_risk_score,
            tabular_action=result.tabular_action,
            graph_risk_score=result.graph_risk_score,
            graph_features=result.graph_features,
            combined_risk_score=result.combined_risk_score,
            combined_action=result.combined_action,
            confidence=result.confidence,
            processing_time_ms=(time.time() - start) * 1000,
        )
    except Exception as e:
        logger.error(f"Hybrid prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict/batch", response_model=BatchPredictResponse)
async def predict_batch(request: BatchPredictRequest):
    """Batch hybrid predictions."""
    start = time.time()
    
    try:
        predictor = get_hybrid_predictor()
        
        transactions = [
            {
                "transaction_id": t.transaction_id,
                "features": t.features,
                "from_address": t.from_address,
                "to_address": t.to_address,
            }
            for t in request.transactions
        ]
        
        results = predictor.predict_batch(transactions)
        
        total_time = (time.time() - start) * 1000
        per_sample = total_time / len(results) if results else 0
        
        predictions = [
            HybridPredictResponse(
                transaction_id=r.transaction_id,
                tabular_risk_score=r.tabular_risk_score,
                tabular_action=r.tabular_action,
                graph_risk_score=r.graph_risk_score,
                graph_features=r.graph_features,
                combined_risk_score=r.combined_risk_score,
                combined_action=r.combined_action,
                confidence=r.confidence,
                processing_time_ms=per_sample,
            )
            for r in results
        ]
        
        return BatchPredictResponse(
            predictions=predictions,
            total_processed=len(predictions),
            avg_processing_time_ms=per_sample,
        )
    except Exception as e:
        logger.error(f"Batch prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/graph/address-risk", response_model=AddressRiskResponse)
async def get_address_risk(request: AddressRiskRequest):
    """Get graph-based risk analysis for an address."""
    try:
        predictor = get_hybrid_predictor()
        
        if not predictor.is_graph_available():
            raise HTTPException(status_code=503, detail="Graph service unavailable")
        
        from .features import GraphFeatureExtractor
        extractor = GraphFeatureExtractor(get_graph_service())
        features = extractor.extract_features(request.address)
        risk_score = extractor.get_risk_score_from_graph(request.address)
        
        return AddressRiskResponse(
            address=request.address.lower(),
            graph_risk_score=risk_score,
            sanctions_distance=features.sanctions_distance,
            is_sanctioned_neighbor=features.sanctions_distance <= 1,
            is_mixer_connected=features.is_mixer_connected,
            in_degree=features.in_degree,
            out_degree=features.out_degree,
            community_id=features.community_id,
            community_risk=features.community_risk_score,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Address risk error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph/stats")
async def get_graph_stats():
    """Get Memgraph statistics."""
    try:
        service = get_graph_service()
        stats = service.get_graph_stats()
        stats["health"] = service.health_check()
        return stats
    except Exception as e:
        logger.error(f"Graph stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/graph/add-transaction")
async def add_transaction(request: AddTransactionRequest):
    """Add a transaction to the graph."""
    try:
        from .updater import Transaction
        
        updater = get_graph_updater()
        txn = Transaction(
            hash=request.hash,
            from_address=request.from_address,
            to_address=request.to_address,
            value=request.value,
            timestamp=request.timestamp,
            block_number=request.block_number,
        )
        
        success = updater.add_transaction(txn)
        
        return {
            "success": success,
            "hash": request.hash,
        }
    except Exception as e:
        logger.error(f"Add transaction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/graph/tag-address")
async def tag_address(request: TagAddressRequest):
    """Tag an address (sanctioned, mixer, exchange, etc.)."""
    try:
        updater = get_graph_updater()
        success = updater.tag_address(request.address, request.tag)
        
        return {
            "success": success,
            "address": request.address.lower(),
            "tag": request.tag,
        }
    except Exception as e:
        logger.error(f"Tag address error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph/address/{address}")
async def get_address_details(address: str):
    """Get all details for an address from the graph."""
    try:
        from .features import GraphFeatureExtractor
        
        service = get_graph_service()
        extractor = GraphFeatureExtractor(service)
        features = extractor.extract_features(address)
        
        return features.to_dict()
    except Exception as e:
        logger.error(f"Address details error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/model/info")
async def model_info():
    """Get hybrid model information."""
    predictor = get_hybrid_predictor()
    return predictor.get_model_info()


# ============================================================
# Run: python -m uvicorn graph.api:app --host 0.0.0.0 --port 8001
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
