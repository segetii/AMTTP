"""
AMTTP ML Pipeline - Real-time Scoring API

FastAPI endpoints for real-time fraud scoring with:
- REST endpoints for transaction scoring
- WebSocket for streaming updates
- Batch processing support
"""
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from .realtime import (
    RealtimeScorer, 
    Transaction, 
    RealtimeScore, 
    get_realtime_scorer,
)
from .service import get_memgraph_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="AMTTP Real-time Fraud Scoring API",
    description="Real-time blockchain transaction scoring using Memgraph + ML",
    version="2.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connection manager
class ConnectionManager:
    """Manages WebSocket connections for real-time streaming."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._score_queue: asyncio.Queue = asyncio.Queue()
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
    
    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send message to specific client."""
        await websocket.send_json(message)


manager = ConnectionManager()

# Global scorer (lazy loaded)
_scorer: Optional[RealtimeScorer] = None


def get_scorer() -> RealtimeScorer:
    """Get or create realtime scorer."""
    global _scorer
    if _scorer is None:
        _scorer = get_realtime_scorer()
        # Add broadcast callback for WebSocket streaming
        _scorer.subscribe(lambda score: asyncio.create_task(
            broadcast_score(score)
        ))
    return _scorer


async def broadcast_score(score: RealtimeScore):
    """Broadcast score to all WebSocket clients."""
    if manager.active_connections:
        await manager.broadcast(score.to_dict())


# =============================================================================
# Request/Response Models
# =============================================================================

class TransactionRequest(BaseModel):
    """Request model for scoring a single transaction."""
    tx_hash: str = Field(..., description="Transaction hash")
    from_address: str = Field(..., description="Sender address")
    to_address: str = Field(..., description="Receiver address")
    value: float = Field(..., description="Transaction value in ETH")
    timestamp: int = Field(..., description="Unix timestamp")
    block_number: int = Field(0, description="Block number")
    gas_price: float = Field(0.0, description="Gas price in Gwei")
    gas_used: int = Field(0, description="Gas used")


class BatchTransactionRequest(BaseModel):
    """Request model for batch scoring."""
    transactions: List[TransactionRequest]


class ScoreResponse(BaseModel):
    """Response model for transaction score."""
    tx_hash: str
    from_address: str
    to_address: str
    risk_scores: Dict[str, float]
    graph_insights: Dict[str, Any]
    action: str
    confidence: float
    processing_time_ms: float
    timestamp: str


class AddressRiskRequest(BaseModel):
    """Request for address risk lookup."""
    address: str


class AddressRiskResponse(BaseModel):
    """Response for address risk lookup."""
    address: str
    risk_score: float
    features: Dict[str, Any]
    action: str


class GraphStatsResponse(BaseModel):
    """Response for graph statistics."""
    nodes: int
    edges: int
    sanctioned_addresses: int
    mixer_addresses: int
    fraud_addresses: int
    density: float


# =============================================================================
# REST Endpoints
# =============================================================================

@app.get("/")
async def root():
    """API info."""
    return {
        "service": "AMTTP Real-time Fraud Scoring API",
        "version": "2.0.0",
        "mode": "Real-time Graph Scoring",
        "endpoints": {
            "score": "POST /score - Score a single transaction",
            "batch": "POST /score/batch - Score multiple transactions",
            "address": "GET /address/{addr}/risk - Get address risk",
            "stream": "WS /ws/stream - Real-time score streaming",
            "ingest": "POST /ingest - Ingest transaction without scoring",
            "stats": "GET /stats - Get scoring statistics",
            "graph": "GET /graph/stats - Get graph statistics",
            "health": "GET /health - Health check",
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        scorer = get_scorer()
        graph_health = scorer.service.health_check()
        return {
            "status": "healthy",
            "graph": graph_health,
            "scorer_stats": scorer.get_stats(),
            "websocket_connections": len(manager.active_connections),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }


@app.post("/score", response_model=ScoreResponse)
async def score_transaction(request: TransactionRequest):
    """
    Score a single transaction in real-time.
    
    This will:
    1. Ingest the transaction into the graph
    2. Extract sender/receiver features
    3. Compute combined risk score
    4. Return action recommendation
    """
    try:
        scorer = get_scorer()
        
        tx = Transaction(
            tx_hash=request.tx_hash,
            from_address=request.from_address,
            to_address=request.to_address,
            value=request.value,
            timestamp=request.timestamp,
            block_number=request.block_number,
            gas_price=request.gas_price,
            gas_used=request.gas_used,
        )
        
        score = scorer.score_transaction(tx)
        return score.to_dict()
        
    except Exception as e:
        logger.error(f"Score error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/score/batch")
async def batch_score_transactions(request: BatchTransactionRequest):
    """Score multiple transactions."""
    try:
        scorer = get_scorer()
        
        transactions = [
            Transaction(
                tx_hash=tx.tx_hash,
                from_address=tx.from_address,
                to_address=tx.to_address,
                value=tx.value,
                timestamp=tx.timestamp,
                block_number=tx.block_number,
                gas_price=tx.gas_price,
                gas_used=tx.gas_used,
            )
            for tx in request.transactions
        ]
        
        scores = scorer.batch_score(transactions)
        
        return {
            "count": len(scores),
            "scores": [s.to_dict() for s in scores],
            "summary": {
                "blocked": sum(1 for s in scores if s.action == "BLOCK"),
                "escrow": sum(1 for s in scores if s.action == "ESCROW"),
                "review": sum(1 for s in scores if s.action == "REVIEW"),
                "approved": sum(1 for s in scores if s.action in ["APPROVE", "MONITOR"]),
                "avg_risk": sum(s.transaction_risk_score for s in scores) / len(scores) if scores else 0,
            }
        }
        
    except Exception as e:
        logger.error(f"Batch score error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/address/{address}/risk", response_model=AddressRiskResponse)
async def get_address_risk(address: str):
    """Get risk assessment for a specific address."""
    try:
        scorer = get_scorer()
        features = scorer.feature_extractor.extract_features(address.lower())
        risk = scorer._compute_address_risk(features)
        action = scorer._determine_action(risk)
        
        return {
            "address": address.lower(),
            "risk_score": risk,
            "features": features.to_dict(),
            "action": action,
        }
        
    except Exception as e:
        logger.error(f"Address risk error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest")
async def ingest_transaction(request: TransactionRequest):
    """
    Ingest a transaction into the graph without scoring.
    
    Useful for bulk historical data loading.
    """
    try:
        scorer = get_scorer()
        
        tx = Transaction(
            tx_hash=request.tx_hash,
            from_address=request.from_address,
            to_address=request.to_address,
            value=request.value,
            timestamp=request.timestamp,
            block_number=request.block_number,
            gas_price=request.gas_price,
            gas_used=request.gas_used,
        )
        
        success = scorer.ingest_transaction(tx)
        
        return {
            "success": success,
            "tx_hash": request.tx_hash,
        }
        
    except Exception as e:
        logger.error(f"Ingest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/batch")
async def batch_ingest_transactions(request: BatchTransactionRequest):
    """Bulk ingest transactions without scoring."""
    try:
        scorer = get_scorer()
        
        success_count = 0
        for tx_req in request.transactions:
            tx = Transaction(
                tx_hash=tx_req.tx_hash,
                from_address=tx_req.from_address,
                to_address=tx_req.to_address,
                value=tx_req.value,
                timestamp=tx_req.timestamp,
                block_number=tx_req.block_number,
                gas_price=tx_req.gas_price,
                gas_used=tx_req.gas_used,
            )
            if scorer.ingest_transaction(tx):
                success_count += 1
        
        return {
            "total": len(request.transactions),
            "success": success_count,
            "failed": len(request.transactions) - success_count,
        }
        
    except Exception as e:
        logger.error(f"Batch ingest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_scoring_stats():
    """Get scoring statistics."""
    try:
        scorer = get_scorer()
        return scorer.get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph/stats", response_model=GraphStatsResponse)
async def get_graph_stats():
    """Get graph statistics."""
    try:
        scorer = get_scorer()
        stats = scorer.service.get_graph_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# WebSocket Endpoints
# =============================================================================

@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time score streaming.
    
    Clients receive all scored transactions in real-time.
    
    Messages sent to client:
    {
        "type": "score",
        "data": { ... score data ... }
    }
    
    Messages from client:
    {
        "type": "subscribe",
        "filters": { "min_risk": 0.5 }  // optional filters
    }
    """
    await manager.connect(websocket)
    
    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to AMTTP real-time scoring stream",
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        while True:
            # Wait for client messages (filters, ping, etc.)
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=30.0  # Send ping every 30s
                )
                
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@app.websocket("/ws/score")
async def websocket_score(websocket: WebSocket):
    """
    WebSocket endpoint for interactive scoring.
    
    Send transactions to be scored and receive results immediately.
    
    Client sends:
    {
        "tx_hash": "0x...",
        "from_address": "0x...",
        "to_address": "0x...",
        "value": 1.5,
        "timestamp": 1703123456
    }
    
    Server responds:
    {
        "type": "score",
        "data": { ... score result ... }
    }
    """
    await manager.connect(websocket)
    scorer = get_scorer()
    
    try:
        await websocket.send_json({
            "type": "ready",
            "message": "Send transactions to score",
        })
        
        while True:
            data = await websocket.receive_json()
            
            try:
                tx = Transaction(
                    tx_hash=data.get("tx_hash", "unknown"),
                    from_address=data["from_address"],
                    to_address=data["to_address"],
                    value=float(data.get("value", 0)),
                    timestamp=int(data.get("timestamp", int(time.time()))),
                    block_number=int(data.get("block_number", 0)),
                )
                
                score = scorer.score_transaction(tx)
                
                await websocket.send_json({
                    "type": "score",
                    "data": score.to_dict(),
                })
                
            except KeyError as e:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Missing field: {e}",
                })
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": str(e),
                })
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket score error: {e}")
        manager.disconnect(websocket)


# =============================================================================
# Sanctions Management
# =============================================================================

@app.post("/sanctions/add")
async def add_sanctioned_address(address: str = Query(...)):
    """Add an address to sanctions list."""
    try:
        scorer = get_scorer()
        query = """
        MERGE (a:Address {id: $addr})
        SET a:Sanctions
        RETURN a.id
        """
        scorer.service.execute(query, {"addr": address.lower()})
        return {"success": True, "address": address.lower()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mixer/add")
async def add_mixer_address(address: str = Query(...)):
    """Tag an address as a mixer."""
    try:
        scorer = get_scorer()
        query = """
        MERGE (a:Address {id: $addr})
        SET a:Mixer
        RETURN a.id
        """
        scorer.service.execute(query, {"addr": address.lower()})
        return {"success": True, "address": address.lower()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Run server
# =============================================================================

def run_server(host: str = "0.0.0.0", port: int = 8001):
    """Run the real-time scoring server."""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
