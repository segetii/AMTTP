"""Explainability Service — ML risk-score explanations."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

ImpactLevel = Literal["none", "low", "medium", "high", "critical"]
RecommendedAction = Literal["allow", "review", "block", "escalate"]


class ExplanationFactor(BaseModel):
    name: str = ""
    weight: float = 0
    value: float = 0
    description: str = ""
    impact: str = "low"


class TypologyMatch(BaseModel):
    name: str = ""
    confidence: float = 0
    description: str = ""
    indicators: List[str] = []


class ExplainRequest(BaseModel):
    address: str
    include_typologies: bool = True
    include_recommendations: bool = True


class RiskExplanation(BaseModel):
    address: str = ""
    risk_score: float = 0
    risk_level: str = "low"
    factors: List[ExplanationFactor] = []
    typologies: List[TypologyMatch] = []
    recommended_action: str = "allow"
    explanation_text: str = ""
    generated_at: str = ""


class TransactionExplainRequest(BaseModel):
    from_address: str
    to_address: str
    value_eth: float
    chain_id: int = 1


class TransactionExplanation(BaseModel):
    transaction_risk_score: float = 0
    factors: List[ExplanationFactor] = []
    sender_risk: Optional[Dict[str, Any]] = None
    recipient_risk: Optional[Dict[str, Any]] = None
    typologies: List[TypologyMatch] = []
    recommended_action: str = "allow"
    explanation_text: str = ""


class Typology(BaseModel):
    id: str = ""
    name: str = ""
    description: str = ""
    indicators: List[str] = []
    severity: str = "medium"


# ── service ───────────────────────────────────────────────────────────────────


class ExplainabilityService(BaseService):
    """Risk explanation and ML interpretability."""

    async def explain(self, request: ExplainRequest) -> RiskExplanation:
        """Get explanation for an address risk score."""
        resp = await self._http.post("/explain", json=request.model_dump())
        resp.raise_for_status()
        data = RiskExplanation.model_validate(resp.json())
        self._events.emit("explainability:explained", data.model_dump())
        return data

    async def explain_address(self, address: str) -> RiskExplanation:
        """Shorthand: explain risk for a single address."""
        return await self.explain(ExplainRequest(address=address))

    async def explain_transaction(
        self, request: TransactionExplainRequest
    ) -> TransactionExplanation:
        """Get explanation for a transaction risk assessment."""
        resp = await self._http.post(
            "/explain/transaction", json=request.model_dump(exclude_none=True)
        )
        resp.raise_for_status()
        return TransactionExplanation.model_validate(resp.json())

    async def get_typologies(self) -> List[Typology]:
        """Get known money-laundering typologies."""
        resp = await self._http.get("/explain/typologies")
        resp.raise_for_status()
        return [Typology.model_validate(t) for t in resp.json().get("typologies", [])]

    async def health(self) -> Dict[str, Any]:
        """Check service health."""
        resp = await self._http.get("/explain/health")
        resp.raise_for_status()
        return resp.json()
