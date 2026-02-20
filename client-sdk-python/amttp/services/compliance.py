"""Compliance Service — unified compliance evaluation via the Orchestrator."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

# ── types ─────────────────────────────────────────────────────────────────────

ComplianceAction = Literal["ALLOW", "REQUIRE_INFO", "REQUIRE_ESCROW", "BLOCK", "REVIEW"]
EntityType = Literal["RETAIL", "INSTITUTIONAL", "VASP", "HIGH_NET_WORTH", "PEP", "UNVERIFIED"]
KYCLevel = Literal["NONE", "BASIC", "STANDARD", "ENHANCED"]
RiskTolerance = Literal["STRICT", "MODERATE", "RELAXED"]


class EntityProfile(BaseModel):
    address: str
    entity_type: str = "UNVERIFIED"
    kyc_level: str = "NONE"
    risk_tolerance: str = "MODERATE"
    jurisdiction: str = ""
    daily_limit_eth: float = 0
    monthly_limit_eth: float = 0
    single_tx_limit_eth: float = 0
    sanctions_checked: bool = False
    pep_checked: bool = False
    source_of_funds_verified: bool = False
    travel_rule_threshold_eth: float = 0
    total_transactions: int = 0
    daily_volume_eth: float = 0
    monthly_volume_eth: float = 0
    risk_score_cache: Optional[float] = None
    last_activity: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


class ComplianceCheck(BaseModel):
    service: str = ""
    check_type: str = ""
    passed: bool = False
    score: Optional[float] = None
    details: Optional[Dict[str, Any]] = None
    action_required: Optional[str] = None
    reason: Optional[str] = None


class EvaluateRequest(BaseModel):
    from_address: str
    to_address: str
    value_eth: float
    asset: Optional[str] = None
    chain_id: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class EvaluateResponse(BaseModel):
    decision_id: str = ""
    timestamp: str = ""
    from_address: str = ""
    to_address: str = ""
    value_eth: float = 0
    originator_profile: Optional[EntityProfile] = None
    beneficiary_profile: Optional[EntityProfile] = None
    checks: List[ComplianceCheck] = []
    action: str = "REVIEW"
    risk_score: float = 0
    reasons: List[str] = []
    requires_travel_rule: bool = False
    requires_sar: bool = False
    requires_escrow: bool = False
    escrow_duration_hours: int = 0
    processing_time_ms: float = 0


class DashboardStats(BaseModel):
    total_transactions: int = 0
    transactions_today: int = 0
    high_risk_count: int = 0
    blocked_count: int = 0
    pending_review: int = 0
    total_value_eth: float = 0
    avg_risk_score: float = 0
    compliance_rate: float = 0


class DashboardAlert(BaseModel):
    id: str = ""
    severity: str = "low"
    type: str = ""
    message: str = ""
    address: str = ""
    timestamp: str = ""
    acknowledged: bool = False


class TimelineDataPoint(BaseModel):
    timestamp: str = ""
    transactions: int = 0
    volume: float = 0
    risk_score: float = 0
    blocked: int = 0


class DecisionRecord(BaseModel):
    decision_id: str = ""
    timestamp: str = ""
    from_address: str = ""
    to_address: str = ""
    value_eth: float = 0
    action: str = ""
    risk_score: float = 0


# ── service ───────────────────────────────────────────────────────────────────


class ComplianceService(BaseService):
    """Unified compliance evaluation (Orchestrator)."""

    async def evaluate(self, request: EvaluateRequest) -> EvaluateResponse:
        """Evaluate a transaction for compliance."""
        resp = await self._http.post("/evaluate", json=request.model_dump(exclude_none=True))
        resp.raise_for_status()
        data = EvaluateResponse.model_validate(resp.json())
        self._events.emit("compliance:evaluated", data.model_dump())
        return data

    async def evaluate_with_integrity(
        self, request: EvaluateRequest, snapshot_hash: str
    ) -> Dict[str, Any]:
        """Evaluate with UI integrity verification."""
        payload = {**request.model_dump(exclude_none=True), "ui_snapshot_hash": snapshot_hash}
        resp = await self._http.post("/evaluate-with-integrity", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_dashboard_stats(self) -> DashboardStats:
        """Get dashboard statistics."""
        resp = await self._http.get("/dashboard/stats")
        resp.raise_for_status()
        return DashboardStats.model_validate(resp.json())

    async def get_dashboard_alerts(
        self, *, limit: Optional[int] = None, severity: Optional[str] = None
    ) -> List[DashboardAlert]:
        """Get dashboard alerts."""
        params: Dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if severity:
            params["severity"] = severity
        resp = await self._http.get("/dashboard/alerts", params=params)
        resp.raise_for_status()
        return [DashboardAlert.model_validate(a) for a in resp.json().get("alerts", [])]

    async def get_timeline_data(
        self, *, hours: Optional[int] = None, interval: Optional[str] = None
    ) -> List[TimelineDataPoint]:
        """Get timeline data for charts."""
        params: Dict[str, Any] = {}
        if hours is not None:
            params["hours"] = hours
        if interval:
            params["interval"] = interval
        resp = await self._http.get("/dashboard/timeline", params=params)
        resp.raise_for_status()
        return [TimelineDataPoint.model_validate(d) for d in resp.json().get("data", [])]

    async def get_sankey_flow(self, *, limit: Optional[int] = None) -> Dict[str, Any]:
        """Get Sankey flow data for value visualization."""
        params = {"limit": limit} if limit else {}
        resp = await self._http.get("/sankey-flow", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_profile(self, address: str) -> EntityProfile:
        """Get entity profile by address."""
        resp = await self._http.get(f"/profiles/{address}")
        resp.raise_for_status()
        return EntityProfile.model_validate(resp.json())

    async def update_profile(self, address: str, updates: Dict[str, Any]) -> EntityProfile:
        """Update entity profile."""
        resp = await self._http.put(f"/profiles/{address}", json=updates)
        resp.raise_for_status()
        data = EntityProfile.model_validate(resp.json())
        self._events.emit("profile:updated", data.model_dump())
        return data

    async def set_entity_type(self, address: str, entity_type: str) -> EntityProfile:
        """Set entity type for an address."""
        resp = await self._http.post(f"/profiles/{address}/set-type/{entity_type}")
        resp.raise_for_status()
        return EntityProfile.model_validate(resp.json())

    async def list_profiles(
        self, *, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> List[EntityProfile]:
        """List all profiles."""
        params: Dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        resp = await self._http.get("/profiles", params=params)
        resp.raise_for_status()
        return [EntityProfile.model_validate(p) for p in resp.json().get("profiles", [])]

    async def list_decisions(
        self,
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        action: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[DecisionRecord]:
        """Get decision history."""
        params: Dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if action:
            params["action"] = action
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date
        resp = await self._http.get("/decisions", params=params)
        resp.raise_for_status()
        return [DecisionRecord.model_validate(d) for d in resp.json().get("decisions", [])]

    async def get_entity_types(self) -> List[Dict[str, str]]:
        """Get available entity types."""
        resp = await self._http.get("/entity-types")
        resp.raise_for_status()
        return resp.json().get("entity_types", [])

    async def health(self) -> Dict[str, Any]:
        """Check orchestrator service health."""
        resp = await self._http.get("/health")
        resp.raise_for_status()
        return resp.json()
