"""Risk Assessment Service — wraps ``/risk`` endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

# ── types ─────────────────────────────────────────────────────────────────────

RiskLevel = Literal["low", "medium", "high", "critical"]


class RiskFactor(BaseModel):
    name: str
    weight: float
    value: float
    description: str


class LabelInfo(BaseModel):
    label: str
    category: str
    severity: str
    source: str


class RiskAssessmentRequest(BaseModel):
    address: str
    transaction_hash: Optional[str] = None
    amount: Optional[str] = None
    counterparty: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class RiskAssessmentResponse(BaseModel):
    address: str
    risk_score: float = 0
    risk_level: str = "low"
    factors: List[RiskFactor] = []
    labels: List[LabelInfo] = []
    timestamp: str = ""
    expires_at: str = ""
    cached: bool = False

    model_config = {"populate_by_name": True}


class RiskScore(BaseModel):
    address: str
    score: float
    level: str
    timestamp: str
    expires_at: str


class BatchRiskRequest(BaseModel):
    addresses: List[str]
    include_labels: Optional[bool] = None
    include_factors: Optional[bool] = None


class BatchRiskResponse(BaseModel):
    results: List[RiskAssessmentResponse] = []
    processed_count: int = 0
    failed_count: int = 0
    failures: List[Dict[str, str]] = []


class RiskThreshold(BaseModel):
    level: str
    min_score: float
    max_score: float
    action: Literal["allow", "review", "block"]


# ── service ───────────────────────────────────────────────────────────────────


class RiskService(BaseService):
    """Risk assessment operations."""

    async def assess(self, request: RiskAssessmentRequest) -> RiskAssessmentResponse:
        """Assess risk for a single address."""
        resp = await self._http.post("/risk/assess", json=request.model_dump(exclude_none=True))
        resp.raise_for_status()
        data = RiskAssessmentResponse.model_validate(resp.json())
        self._events.emit("risk:assessed", {
            "address": request.address,
            "risk_level": data.risk_level,
            "risk_score": data.risk_score,
        })
        return data

    async def get_score(self, address: str) -> Optional[RiskScore]:
        """Get cached risk score for an address."""
        from amttp.errors import AMTTPError, AMTTPErrorCode

        try:
            resp = await self._http.get(f"/risk/score/{address}")
            resp.raise_for_status()
            return RiskScore.model_validate(resp.json())
        except AMTTPError as e:
            if e.code == AMTTPErrorCode.NOT_FOUND:
                return None
            raise

    async def batch_assess(self, request: BatchRiskRequest) -> BatchRiskResponse:
        """Batch-assess multiple addresses."""
        resp = await self._http.post("/risk/batch", json=request.model_dump(exclude_none=True))
        resp.raise_for_status()
        data = BatchRiskResponse.model_validate(resp.json())
        self._events.emit("risk:batchCompleted", {
            "processed_count": data.processed_count,
            "failed_count": data.failed_count,
        })
        return data

    async def get_thresholds(self) -> List[RiskThreshold]:
        """Get risk threshold configuration."""
        resp = await self._http.get("/risk/thresholds")
        resp.raise_for_status()
        return [RiskThreshold.model_validate(t) for t in resp.json()["thresholds"]]

    async def check_threshold(
        self, address: str, max_risk_level: RiskLevel = "medium"
    ) -> Dict[str, Any]:
        """Check if address passes risk threshold."""
        resp = await self._http.post(
            "/risk/check-threshold",
            json={"address": address, "maxRiskLevel": max_risk_level},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_history(
        self,
        address: str,
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get risk history for an address."""
        params: Dict[str, str] = {}
        if limit is not None:
            params["limit"] = str(limit)
        if offset is not None:
            params["offset"] = str(offset)
        if start_date:
            params["startDate"] = start_date.isoformat()
        if end_date:
            params["endDate"] = end_date.isoformat()
        resp = await self._http.get(f"/risk/history/{address}", params=params)
        resp.raise_for_status()
        return resp.json()

    async def invalidate_cache(self, address: str) -> None:
        """Invalidate cached risk score."""
        resp = await self._http.delete(f"/risk/cache/{address}")
        resp.raise_for_status()
        self._events.emit("risk:cacheInvalidated", {"address": address})

    async def get_factors(self) -> Dict[str, Any]:
        """Get risk factors configuration."""
        resp = await self._http.get("/risk/factors")
        resp.raise_for_status()
        return resp.json()
