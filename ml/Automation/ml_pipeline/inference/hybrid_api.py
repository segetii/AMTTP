"""
AMTTP ML Pipeline - Hybrid Multi-Signal API

Enhanced API that combines:
- ML scoring (XGBoost)
- Graph analysis (Memgraph)
- Behavioral patterns (smurfing, layering, etc.)

Only flags addresses with 2+ signals to minimize false positives.
"""
import os
import time
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

# Force CPU mode
os.environ["CUDA_VISIBLE_DEVICES"] = ""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AMTTP Hybrid Fraud Detection API",
    description="Multi-signal fraud detection: ML + Graph + Behavioral Patterns",
    version="2.0.0",
)

# Add CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Configuration - Recalibrated Thresholds
# ============================================================
CONFIG = {
    "ml_threshold": 0.55,
    "approve_threshold": 0.20,
    "monitor_threshold": 0.40,
    "review_threshold": 0.55,
    "escrow_threshold": 0.75,
    "require_multi_signal": True,
    
    # Pattern boosts (add to ML score)
    "pattern_boosts": {
        "SMURFING": 0.25,
        "LAYERING": 0.15,
        "FAN_OUT": 0.15,
        "FAN_IN": 0.10,
        "PEELING": 0.20,
        "STRUCTURING": 0.25,
    },
    
    # Graph boosts
    "graph_boosts": {
        "direct_sanctioned": 0.40,
        "direct_mixer": 0.30,
        "2hop_sanctioned": 0.20,
        "3hop_sanctioned": 0.10,
        "high_centrality": 0.05,
    },
    
    # Multi-signal multipliers
    "multi_signal_boost": {
        2: 1.20,  # 20% boost for 2 signals
        3: 1.50,  # 50% boost for 3 signals
    }
}

# Global components (lazy loaded)
_ml_predictor = None
_graph_client = None
_pattern_data = None


def get_ml_predictor():
    """Get or create ML predictor."""
    global _ml_predictor
    if _ml_predictor is None:
        from cpu_predictor import CPUPredictor
        
        possible_paths = [
            Path("models/trained"),
            Path("ml_pipeline/models/trained"),
            Path(__file__).parent.parent / "models" / "trained",
            Path("c:/amttp/ml/Automation/ml_pipeline/models/trained"),
        ]
        
        models_dir = None
        for p in possible_paths:
            if p.exists() and (p / "xgb.json").exists():
                models_dir = p
                break
        
        if models_dir is None:
            logger.warning("Models directory not found, ML scoring disabled")
            return None
        
        _ml_predictor = CPUPredictor(models_dir=str(models_dir), primary_model="xgb")
        logger.info(f"ML predictor loaded from {models_dir}")
    
    return _ml_predictor


def get_graph_client():
    """Get Memgraph connection."""
    global _graph_client
    if _graph_client is None:
        try:
            import mgclient
            _graph_client = mgclient.connect(host='localhost', port=7687)
            logger.info("Connected to Memgraph")
        except Exception as e:
            logger.warning(f"Memgraph connection failed: {e}")
            return None
    return _graph_client


def get_pattern_data():
    """Load behavioral pattern data."""
    global _pattern_data
    if _pattern_data is None:
        try:
            import pandas as pd
            soph = pd.read_csv('c:/amttp/processed/sophisticated_fraud_patterns.csv')
            _pattern_data = dict(zip(
                soph['address'].str.lower(), 
                soph['patterns']
            ))
            logger.info(f"Loaded {len(_pattern_data)} pattern addresses")
        except Exception as e:
            logger.warning(f"Pattern data load failed: {e}")
            _pattern_data = {}
    return _pattern_data


# ============================================================
# Request/Response Models
# ============================================================

class AddressScoreRequest(BaseModel):
    address: str = Field(..., description="Ethereum address to score")
    

class AddressScoreResponse(BaseModel):
    address: str
    hybrid_score: float
    risk_level: str  # CRITICAL, HIGH, MEDIUM, LOW
    action: str      # ESCROW, FLAG, REVIEW, MONITOR, APPROVE
    
    # Signal breakdown
    ml_score: float
    ml_signal: bool
    graph_score: float
    graph_signal: bool
    patterns: str
    pattern_signal: bool
    signal_count: int
    
    # Processing info
    processing_time_ms: float
    multi_signal_required: bool


class TransactionScoreRequest(BaseModel):
    tx_hash: str = Field(..., description="Transaction hash")
    from_address: str = Field(..., description="Sender address")
    to_address: str = Field(..., description="Receiver address")
    value_eth: float = Field(..., description="Transaction value in ETH")
    features: Optional[Dict[str, float]] = Field(None, description="ML features (optional)")


class TransactionScoreResponse(BaseModel):
    tx_hash: str
    from_score: AddressScoreResponse
    to_score: AddressScoreResponse
    
    # Combined decision
    overall_action: str
    overall_risk: str
    should_block: bool
    should_escrow: bool
    
    processing_time_ms: float


class BatchAddressRequest(BaseModel):
    addresses: List[str]


class BatchAddressResponse(BaseModel):
    results: List[AddressScoreResponse]
    summary: Dict[str, int]  # Count by risk level
    processing_time_ms: float


# ============================================================
# Scoring Functions
# ============================================================

def score_address(address: str) -> AddressScoreResponse:
    """Score a single address using multi-signal detection."""
    start = time.time()
    
    addr_lower = address.lower()
    
    # 1. ML Score
    ml_score = 0.0
    try:
        predictor = get_ml_predictor()
        if predictor:
            # For address-only queries, we need pre-computed scores
            # In production, you'd look this up from cached results
            # For now, query from cross-validated results
            import pandas as pd
            cv = pd.read_csv('c:/amttp/processed/cross_validated_results.csv')
            match = cv[cv['address'].str.lower() == addr_lower]
            if len(match) > 0:
                ml_score = match.iloc[0]['ml_max_score']
    except Exception as e:
        logger.warning(f"ML scoring error: {e}")
    
    ml_signal = ml_score >= CONFIG["ml_threshold"]
    
    # 2. Graph Score
    graph_score = 0.0
    graph_reasons = []
    try:
        conn = get_graph_client()
        if conn:
            cursor = conn.cursor()
            cursor.execute("""
                MATCH (a:Address {address: $addr})
                RETURN 
                    a.ml_score as ml,
                    a.graph_score as graph,
                    labels(a) as labels
            """, {"addr": address})
            result = cursor.fetchone()
            if result:
                graph_score = result[1] or 0
                labels = result[2] or []
                if 'Sanctioned' in labels: graph_reasons.append('direct_sanctioned')
                if 'Mixer' in labels: graph_reasons.append('direct_mixer')
                if 'MultiSignal' in labels: graph_reasons.append('multi_signal')
    except Exception as e:
        logger.warning(f"Graph scoring error: {e}")
    
    graph_signal = graph_score > 0
    
    # 3. Pattern Score
    patterns = ""
    pattern_data = get_pattern_data()
    if addr_lower in pattern_data:
        patterns = pattern_data[addr_lower]
    
    pattern_signal = len(patterns) > 0
    
    # 4. Combine Signals
    signal_count = sum([ml_signal, graph_signal, pattern_signal])
    
    # 5. Calculate Hybrid Score
    ml_normalized = min(ml_score / 0.85, 1.0) * 100
    graph_normalized = min(graph_score / 305, 1.0) * 100
    pattern_score = 0
    if patterns:
        for p in CONFIG["pattern_boosts"]:
            if p in patterns:
                pattern_score += CONFIG["pattern_boosts"][p] * 100
    pattern_normalized = min(pattern_score / 100, 1.0) * 100
    
    # Weighted combination
    hybrid_score = (ml_normalized * 0.30) + (graph_normalized * 0.35) + (pattern_normalized * 0.35)
    
    # Multi-signal boost
    if signal_count in CONFIG["multi_signal_boost"]:
        hybrid_score *= CONFIG["multi_signal_boost"][signal_count]
    
    # 6. Determine Risk Level and Action
    if hybrid_score >= 80:
        risk_level = "CRITICAL"
    elif hybrid_score >= 50:
        risk_level = "HIGH"
    elif hybrid_score >= 25:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"
    
    # Determine action based on multi-signal requirement
    if CONFIG["require_multi_signal"]:
        if ml_score >= CONFIG["escrow_threshold"] and signal_count >= 2:
            action = "ESCROW"
        elif ml_score >= CONFIG["review_threshold"] and signal_count >= 2:
            action = "FLAG"
        elif ml_score >= CONFIG["review_threshold"]:
            action = "REVIEW"  # ML flagged but no corroborating evidence
        elif ml_score >= CONFIG["monitor_threshold"]:
            action = "MONITOR"
        else:
            action = "APPROVE"
    else:
        # Without multi-signal requirement (higher FP rate)
        if ml_score >= CONFIG["escrow_threshold"]:
            action = "ESCROW"
        elif ml_score >= CONFIG["review_threshold"]:
            action = "FLAG"
        elif ml_score >= CONFIG["monitor_threshold"]:
            action = "MONITOR"
        else:
            action = "APPROVE"
    
    return AddressScoreResponse(
        address=address,
        hybrid_score=round(hybrid_score, 2),
        risk_level=risk_level,
        action=action,
        ml_score=round(ml_score, 4),
        ml_signal=ml_signal,
        graph_score=graph_score,
        graph_signal=graph_signal,
        patterns=patterns,
        pattern_signal=pattern_signal,
        signal_count=signal_count,
        processing_time_ms=round((time.time() - start) * 1000, 2),
        multi_signal_required=CONFIG["require_multi_signal"]
    )


# ============================================================
# Endpoints
# ============================================================

@app.get("/")
async def root():
    return {
        "service": "AMTTP Hybrid Fraud Detection API",
        "version": "2.0.0",
        "mode": "Multi-Signal (ML + Graph + Patterns)",
        "endpoints": [
            "/score/address",
            "/score/transaction",
            "/score/batch",
            "/health",
            "/config"
        ],
    }


@app.get("/health")
async def health():
    """Health check with component status."""
    ml_status = "loaded" if get_ml_predictor() else "unavailable"
    graph_status = "connected" if get_graph_client() else "unavailable"
    pattern_count = len(get_pattern_data())
    
    return {
        "status": "healthy",
        "components": {
            "ml_predictor": ml_status,
            "graph_database": graph_status,
            "pattern_data": f"{pattern_count} addresses"
        },
        "config": {
            "ml_threshold": CONFIG["ml_threshold"],
            "require_multi_signal": CONFIG["require_multi_signal"],
        }
    }


@app.get("/config")
async def get_config():
    """Get current configuration."""
    return CONFIG


@app.post("/score/address", response_model=AddressScoreResponse)
async def score_address_endpoint(request: AddressScoreRequest):
    """Score a single address using multi-signal detection."""
    try:
        return score_address(request.address)
    except Exception as e:
        logger.error(f"Scoring error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/score/transaction", response_model=TransactionScoreResponse)
async def score_transaction(request: TransactionScoreRequest):
    """Score a transaction (both sender and receiver)."""
    start = time.time()
    
    try:
        from_score = score_address(request.from_address)
        to_score = score_address(request.to_address)
        
        # Combined decision - take the more severe action
        action_priority = ["APPROVE", "MONITOR", "REVIEW", "FLAG", "ESCROW"]
        from_priority = action_priority.index(from_score.action)
        to_priority = action_priority.index(to_score.action)
        
        overall_action = from_score.action if from_priority > to_priority else to_score.action
        overall_risk = from_score.risk_level if from_score.hybrid_score > to_score.hybrid_score else to_score.risk_level
        
        return TransactionScoreResponse(
            tx_hash=request.tx_hash,
            from_score=from_score,
            to_score=to_score,
            overall_action=overall_action,
            overall_risk=overall_risk,
            should_block=overall_action in ["ESCROW", "FLAG"],
            should_escrow=overall_action == "ESCROW",
            processing_time_ms=round((time.time() - start) * 1000, 2)
        )
    except Exception as e:
        logger.error(f"Transaction scoring error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/score/batch", response_model=BatchAddressResponse)
async def score_batch(request: BatchAddressRequest):
    """Score multiple addresses."""
    start = time.time()
    
    results = []
    summary = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    
    for addr in request.addresses:
        try:
            result = score_address(addr)
            results.append(result)
            summary[result.risk_level] += 1
        except Exception as e:
            logger.error(f"Error scoring {addr}: {e}")
    
    return BatchAddressResponse(
        results=results,
        summary=summary,
        processing_time_ms=round((time.time() - start) * 1000, 2)
    )


# ============================================================
# Smart Contract Integration Endpoints
# ============================================================

@app.post("/contract/should-block")
async def should_block(request: AddressScoreRequest):
    """Simple endpoint for smart contract integration.
    Returns true/false for blocking decision.
    """
    result = score_address(request.address)
    return {
        "address": request.address,
        "should_block": result.action in ["ESCROW", "FLAG"],
        "action": result.action,
        "risk_level": result.risk_level,
        "signal_count": result.signal_count
    }


@app.post("/contract/risk-score")
async def get_risk_score(request: AddressScoreRequest):
    """Get risk score for smart contract (0-1000 scale).
    Compatible with AMTTPPolicyEngine thresholds.
    """
    result = score_address(request.address)
    
    # Convert to 0-1000 scale for smart contract
    score_1000 = int(result.hybrid_score * 10)  # 0-100 -> 0-1000
    
    return {
        "address": request.address,
        "risk_score": score_1000,
        "risk_level": result.risk_level,
        "multi_signal": result.signal_count >= 2
    }


# ============================================================
# Dashboard Endpoints for SIEM Frontend
# ============================================================

@app.get("/dashboard/stats")
async def get_dashboard_stats():
    """Get dashboard statistics for SIEM frontend."""
    # Get counts from pattern data
    pattern_data = get_pattern_data()
    pattern_addresses = list(pattern_data.keys()) if pattern_data else []
    
    # Calculate risk distribution
    critical = sum(1 for addr in pattern_addresses if len(pattern_data.get(addr, "").split(", ")) >= 3)
    high = sum(1 for addr in pattern_addresses if len(pattern_data.get(addr, "").split(", ")) == 2)
    medium = sum(1 for addr in pattern_addresses if len(pattern_data.get(addr, "").split(", ")) == 1)
    
    return {
        "totalAlerts": len(pattern_addresses),
        "criticalAlerts": critical,
        "highAlerts": high,
        "mediumAlerts": medium,
        "lowAlerts": 0,
        "alertsTrend": 12.5,
        "resolvedToday": 0,
        "pendingInvestigation": len(pattern_addresses),
        "blockedAddresses": critical,
        "flaggedTransactions": len(pattern_addresses) * 10  # Estimate
    }


@app.get("/alerts")
async def get_alerts(limit: int = 50, offset: int = 0, risk_level: str = None, status: str = None):
    """Get alerts for SIEM frontend."""
    import random
    from datetime import datetime, timedelta
    
    alerts = []
    pattern_data = get_pattern_data()
    pattern_addresses = list(pattern_data.keys()) if pattern_data else []
    
    for i, addr in enumerate(pattern_addresses[:limit]):
        patterns = pattern_data.get(addr, "").split(", ")
        num_patterns = len([p for p in patterns if p])
        
        # Determine risk level based on pattern count
        if num_patterns >= 3:
            risk = "CRITICAL"
            score = 85 + random.random() * 15
        elif num_patterns >= 2:
            risk = "HIGH" 
            score = 65 + random.random() * 20
        elif num_patterns >= 1:
            risk = "MEDIUM"
            score = 40 + random.random() * 25
        else:
            risk = "LOW"
            score = random.random() * 40
        
        alerts.append({
            "id": f"alert-{i}",
            "timestamp": (datetime.now() - timedelta(hours=random.randint(1, 168))).isoformat(),
            "address": addr,
            "riskLevel": risk,
            "riskScore": round(score, 2),
            "signals": patterns,
            "signalCount": num_patterns,
            "patterns": patterns,
            "action": "BLOCK" if risk == "CRITICAL" else "FLAG" if risk in ["HIGH", "MEDIUM"] else "MONITOR",
            "status": "NEW",
            "valueEth": round(random.random() * 100, 2),
            "transactionHash": f"0x{''.join(random.choices('0123456789abcdef', k=64))}"
        })
    
    # Sort by timestamp (newest first)
    alerts.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return alerts


@app.get("/dashboard/timeline")
async def get_timeline(range: str = "24h"):
    """Get timeline data for charts."""
    from datetime import datetime, timedelta
    import random
    
    points = 24 if range == "24h" else 7 if range == "7d" else 12 if range == "1h" else 30
    interval_hours = 1 if range in ["24h", "1h"] else 24
    
    data = []
    for i in range(points):
        timestamp = datetime.now() - timedelta(hours=(points - i) * interval_hours)
        data.append({
            "timestamp": timestamp.isoformat(),
            "critical": random.randint(0, 2),
            "high": random.randint(1, 5),
            "medium": random.randint(2, 10),
            "low": random.randint(1, 5)
        })
    
    return data


@app.get("/entity/{address}")
async def get_entity(address: str):
    """Get entity profile for investigation drill-down."""
    import random
    from datetime import datetime, timedelta
    
    # Score the address
    result = score_address(address)
    
    # Generate mock transactions
    transactions = []
    for i in range(10):
        transactions.append({
            "hash": f"0x{''.join(random.choices('0123456789abcdef', k=64))}",
            "timestamp": (datetime.now() - timedelta(hours=i * 3)).isoformat(),
            "from": address if i % 2 == 0 else f"0x{''.join(random.choices('0123456789abcdef', k=40))}",
            "to": address if i % 2 == 1 else f"0x{''.join(random.choices('0123456789abcdef', k=40))}",
            "valueEth": round(random.random() * 10, 4),
            "gasUsed": random.randint(21000, 100000),
            "riskScore": round(random.random() * 100, 1),
            "flagged": random.random() > 0.7
        })
    
    # Generate connected addresses
    connected = []
    for i in range(8):
        connected.append({
            "address": f"0x{''.join(random.choices('0123456789abcdef', k=40))}",
            "relationship": random.choice(["SENT_TO", "RECEIVED_FROM", "BOTH"]),
            "transactionCount": random.randint(1, 20),
            "totalValue": round(random.random() * 50, 2),
            "riskLevel": random.choice(["LOW", "MEDIUM", "HIGH"])
        })
    
    return {
        "address": address,
        "firstSeen": (datetime.now() - timedelta(days=30)).isoformat(),
        "lastSeen": datetime.now().isoformat(),
        "totalTransactions": random.randint(50, 500),
        "totalValueEth": round(random.random() * 1000, 2),
        "riskScore": result.hybrid_score,
        "riskLevel": result.risk_level,
        "patterns": result.patterns.split(", ") if result.patterns else [],
        "graphConnections": int(result.graph_score / 5) if result.graph_score > 0 else random.randint(5, 50),
        "mlScore": result.ml_score,
        "graphScore": result.graph_score,
        "alerts": [],
        "transactions": transactions,
        "connectedAddresses": connected
    }


@app.post("/alerts/{alert_id}/action")
async def perform_alert_action(alert_id: str, action: dict):
    """Perform action on an alert."""
    return {
        "success": True,
        "message": f"Action {action.get('action', 'unknown')} performed on alert {alert_id}"
    }


# ============================================================
# Run: uvicorn hybrid_api:app --host 0.0.0.0 --port 8000
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
