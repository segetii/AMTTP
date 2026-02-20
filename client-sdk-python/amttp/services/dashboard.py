"""Dashboard Service — analytics and visualization endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

TimeRange = Literal["1h", "6h", "24h", "7d", "30d", "90d"]


class DashboardStats(BaseModel):
    total_transactions: int = 0
    transactions_today: int = 0
    high_risk_count: int = 0
    blocked_count: int = 0
    pending_review: int = 0
    total_value_eth: float = 0
    avg_risk_score: float = 0
    compliance_rate: float = 0


class Alert(BaseModel):
    id: str = ""
    severity: str = "low"
    type: str = ""
    message: str = ""
    address: str = ""
    timestamp: str = ""
    read: bool = False
    dismissed: bool = False


class RiskDistribution(BaseModel):
    low: int = 0
    medium: int = 0
    high: int = 0
    critical: int = 0


class ActivityMetric(BaseModel):
    timestamp: str = ""
    transactions: int = 0
    volume_eth: float = 0
    risk_score_avg: float = 0
    blocked: int = 0


class SankeyNode(BaseModel):
    id: str = ""
    name: str = ""
    category: str = ""


class SankeyLink(BaseModel):
    source: str = ""
    target: str = ""
    value: float = 0


class SankeyData(BaseModel):
    nodes: List[SankeyNode] = []
    links: List[SankeyLink] = []


class TopRiskEntity(BaseModel):
    address: str = ""
    risk_score: float = 0
    risk_level: str = ""
    transaction_count: int = 0
    total_value_eth: float = 0


class GeographicRiskMap(BaseModel):
    country_code: str = ""
    country_name: str = ""
    risk_score: float = 0
    transaction_count: int = 0
    blocked_count: int = 0


# ── service ───────────────────────────────────────────────────────────────────


class DashboardService(BaseService):
    """Dashboard analytics and visualisation."""

    async def get_stats(self) -> DashboardStats:
        """Get dashboard statistics."""
        resp = await self._http.get("/dashboard/stats")
        resp.raise_for_status()
        data = DashboardStats.model_validate(resp.json())
        self._events.emit("dashboard:stats_updated", data.model_dump())
        return data

    async def get_alerts(
        self,
        *,
        limit: Optional[int] = None,
        severity: Optional[str] = None,
        unread_only: bool = False,
    ) -> List[Alert]:
        """Get dashboard alerts."""
        params: Dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if severity:
            params["severity"] = severity
        if unread_only:
            params["unread_only"] = True
        resp = await self._http.get("/dashboard/alerts", params=params)
        resp.raise_for_status()
        return [Alert.model_validate(a) for a in resp.json().get("alerts", [])]

    async def mark_alert_read(self, alert_id: str) -> Alert:
        """Mark an alert as read."""
        resp = await self._http.post(f"/dashboard/alerts/{alert_id}/read")
        resp.raise_for_status()
        data = Alert.model_validate(resp.json())
        self._events.emit("dashboard:alert_read", {"alert_id": alert_id})
        return data

    async def dismiss_alert(self, alert_id: str) -> Alert:
        """Dismiss an alert."""
        resp = await self._http.post(f"/dashboard/alerts/{alert_id}/dismiss")
        resp.raise_for_status()
        data = Alert.model_validate(resp.json())
        self._events.emit("dashboard:alert_dismissed", {"alert_id": alert_id})
        return data

    async def get_risk_distribution(self, *, time_range: Optional[str] = None) -> RiskDistribution:
        """Get risk level distribution."""
        params = {"time_range": time_range} if time_range else {}
        resp = await self._http.get("/dashboard/risk-distribution", params=params)
        resp.raise_for_status()
        return RiskDistribution.model_validate(resp.json())

    async def get_activity(
        self, *, time_range: str = "24h", interval: Optional[str] = None
    ) -> List[ActivityMetric]:
        """Get activity metrics over time."""
        params: Dict[str, Any] = {"time_range": time_range}
        if interval:
            params["interval"] = interval
        resp = await self._http.get("/dashboard/activity", params=params)
        resp.raise_for_status()
        return [ActivityMetric.model_validate(m) for m in resp.json().get("metrics", [])]

    async def get_sankey_data(self, *, limit: Optional[int] = None) -> SankeyData:
        """Get Sankey flow data."""
        params = {"limit": limit} if limit else {}
        resp = await self._http.get("/dashboard/sankey", params=params)
        resp.raise_for_status()
        return SankeyData.model_validate(resp.json())

    async def get_top_risk_entities(self, *, limit: int = 10) -> List[TopRiskEntity]:
        """Get top risk entities."""
        resp = await self._http.get("/dashboard/top-risk", params={"limit": limit})
        resp.raise_for_status()
        return [TopRiskEntity.model_validate(e) for e in resp.json().get("entities", [])]

    async def get_geographic_risk_map(self) -> List[GeographicRiskMap]:
        """Get geographic risk heat-map data."""
        resp = await self._http.get("/dashboard/geo-risk-map")
        resp.raise_for_status()
        return [GeographicRiskMap.model_validate(g) for g in resp.json().get("countries", [])]
