"""
AMTTP Explainability Service
FastAPI service wrapper for the explainability module.
Runs on port 8008.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
import uvicorn

from explainability import explain_risk_decision, RiskExplainer

app = FastAPI(
    title="AMTTP Explainability Service",
    description="Human-readable explanations for ML risk decisions",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class ExplainRequest(BaseModel):
    """Request body for explanation"""
    risk_score: float
    features: Dict[str, Any]
    graph_context: Optional[Dict[str, Any]] = None
    rule_results: Optional[List[Dict[str, Any]]] = None
    model_contributions: Optional[Dict[str, float]] = None

class TransactionExplainRequest(BaseModel):
    """Request body for transaction explanation"""
    transaction_hash: str
    risk_score: float
    sender: str
    receiver: str
    amount: float
    features: Dict[str, Any]
    graph_context: Optional[Dict[str, Any]] = None

# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    """Service info"""
    return {
        "service": "AMTTP Explainability Service",
        "version": "1.0.0",
        "endpoints": {
            "GET /health": "Health check",
            "POST /explain": "Get explanation for a risk score",
            "POST /explain/transaction": "Get explanation for a transaction",
            "GET /typologies": "List known fraud typologies",
        }
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "explainability",
        "version": "1.0.0"
    }

@app.post("/explain")
async def explain(request: ExplainRequest):
    """
    Generate human-readable explanation for a risk score.
    
    Returns:
        - summary: One-sentence summary
        - action: ALLOW/REVIEW/BLOCK
        - factors: List of contributing factors with impact levels
        - typologies: Detected fraud patterns
        - recommendations: Suggested actions
    """
    try:
        result = explain_risk_decision(
            risk_score=request.risk_score,
            features=request.features,
            graph_context=request.graph_context,
            rule_results=request.rule_results
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/explain/transaction")
async def explain_transaction(request: TransactionExplainRequest):
    """
    Generate explanation for a specific transaction.
    Includes transaction context in the explanation.
    """
    try:
        # Add transaction context to features
        enriched_features = {
            **request.features,
            "amount_eth": request.amount,
            "sender": request.sender,
            "receiver": request.receiver,
        }
        
        result = explain_risk_decision(
            risk_score=request.risk_score,
            features=enriched_features,
            graph_context=request.graph_context,
        )
        
        # Add transaction reference
        result["transaction"] = {
            "hash": request.transaction_hash,
            "sender": request.sender,
            "receiver": request.receiver,
            "amount": request.amount
        }
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/typologies")
async def list_typologies():
    """List all known fraud/AML typologies that can be detected."""
    return {
        "typologies": [
            {
                "id": "structuring",
                "name": "Structuring",
                "description": "Breaking large transactions into smaller ones to avoid reporting thresholds"
            },
            {
                "id": "layering",
                "name": "Layering",
                "description": "Complex chains of transactions to obscure the source of funds"
            },
            {
                "id": "round_trip",
                "name": "Round Trip",
                "description": "Funds returning to origin through intermediaries"
            },
            {
                "id": "smurfing",
                "name": "Smurfing",
                "description": "Using multiple accounts/people to move funds"
            },
            {
                "id": "fan_out",
                "name": "Fan Out",
                "description": "Single source distributing to many destinations"
            },
            {
                "id": "fan_in",
                "name": "Fan In",
                "description": "Many sources consolidating to single destination"
            },
            {
                "id": "dormant_activation",
                "name": "Dormant Account Activation",
                "description": "Previously inactive account suddenly active with large amounts"
            },
            {
                "id": "mixer_interaction",
                "name": "Mixer Interaction",
                "description": "Funds passing through known mixing services"
            },
            {
                "id": "sanctions_proximity",
                "name": "Sanctions Proximity",
                "description": "Close network connection to sanctioned entities"
            },
            {
                "id": "high_risk_geography",
                "name": "High Risk Geography",
                "description": "Transaction involving FATF high-risk jurisdictions"
            },
            {
                "id": "unusual_timing",
                "name": "Unusual Timing",
                "description": "Transactions at atypical hours or rapid succession"
            },
            {
                "id": "rapid_movement",
                "name": "Rapid Movement",
                "description": "Funds moved through multiple hops in short time"
            }
        ]
    }

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Starting AMTTP Explainability Service on port 8009...")
    uvicorn.run(app, host="0.0.0.0", port=8009)
