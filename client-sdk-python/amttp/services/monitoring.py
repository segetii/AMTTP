"""Monitoring Service — real-time transaction monitoring and alerting."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

AlertSeverity = Literal["low", "medium", "high", "critical"]
AlertStatus = Literal["active", "acknowledged", "resolved", "dismissed"]
AlertType = Literal["threshold", "pattern", "sanctions", "volume", "velocity", "geographic"]


class RuleCondition(BaseModel):
    field: str = ""
    operator: str = ""
    value: Any = None


class MonitoringRule(BaseModel):
    id: str = ""
    name: str = ""
    description: str = ""
    conditions: List[RuleCondition] = []
    severity: str = "medium"
    enabled: bool = True
    created_at: str = ""


class MonitoringAlert(BaseModel):
    id: str = ""
    rule_id: str = ""
    address: str = ""
    type: str = ""
    severity: str = "medium"
    status: str = "active"
    message: str = ""
    details: Optional[Dict[str, Any]] = None
    created_at: str = ""
    acknowledged_at: Optional[str] = None
    resolved_at: Optional[str] = None


class MonitoredAddress(BaseModel):
    address: str = ""
    added_at: str = ""
    risk_score: float = 0
    alert_count: int = 0
    last_activity: Optional[str] = None
    tags: List[str] = []


class MonitoringConfig(BaseModel):
    enabled: bool = True
    default_interval_seconds: int = 60
    max_alerts_per_address: int = 100
    auto_escalate_critical: bool = True


# ── service ───────────────────────────────────────────────────────────────────


class MonitoringService(BaseService):
    """Real-time monitoring and alerting."""

    async def get_alerts(
        self,
        *,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        address: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[MonitoringAlert]:
        """Get monitoring alerts."""
        params: Dict[str, Any] = {}
        if status:
            params["status"] = status
        if severity:
            params["severity"] = severity
        if address:
            params["address"] = address
        if limit is not None:
            params["limit"] = limit
        resp = await self._http.get("/monitoring/alerts", params=params)
        resp.raise_for_status()
        return [MonitoringAlert.model_validate(a) for a in resp.json().get("alerts", [])]

    async def acknowledge_alert(self, alert_id: str) -> MonitoringAlert:
        """Acknowledge an alert."""
        resp = await self._http.post(f"/monitoring/alerts/{alert_id}/acknowledge")
        resp.raise_for_status()
        data = MonitoringAlert.model_validate(resp.json())
        self._events.emit("monitoring:alert", alert_id, data.address, data.type)
        return data

    async def resolve_alert(self, alert_id: str) -> MonitoringAlert:
        """Resolve an alert."""
        resp = await self._http.post(f"/monitoring/alerts/{alert_id}/resolve")
        resp.raise_for_status()
        return MonitoringAlert.model_validate(resp.json())

    async def dismiss_alert(self, alert_id: str) -> MonitoringAlert:
        """Dismiss an alert."""
        resp = await self._http.post(f"/monitoring/alerts/{alert_id}/dismiss")
        resp.raise_for_status()
        return MonitoringAlert.model_validate(resp.json())

    async def add_address(self, address: str, *, tags: Optional[List[str]] = None) -> MonitoredAddress:
        """Add an address to monitoring."""
        payload: Dict[str, Any] = {"address": address}
        if tags:
            payload["tags"] = tags
        resp = await self._http.post("/monitoring/addresses", json=payload)
        resp.raise_for_status()
        return MonitoredAddress.model_validate(resp.json())

    async def remove_address(self, address: str) -> None:
        """Remove an address from monitoring."""
        resp = await self._http.delete(f"/monitoring/addresses/{address}")
        resp.raise_for_status()

    async def get_monitored_addresses(self) -> List[MonitoredAddress]:
        """Get all monitored addresses."""
        resp = await self._http.get("/monitoring/addresses")
        resp.raise_for_status()
        return [MonitoredAddress.model_validate(a) for a in resp.json().get("addresses", [])]

    async def rescreen(self, address: str) -> Dict[str, Any]:
        """Re-screen a monitored address."""
        resp = await self._http.post(f"/monitoring/addresses/{address}/rescreen")
        resp.raise_for_status()
        data = resp.json()
        self._events.emit("monitoring:re-screened", address, data.get("new_score", 0))
        return data

    async def list_rules(self) -> List[MonitoringRule]:
        """List monitoring rules."""
        resp = await self._http.get("/monitoring/rules")
        resp.raise_for_status()
        return [MonitoringRule.model_validate(r) for r in resp.json().get("rules", [])]

    async def create_rule(self, rule: Dict[str, Any]) -> MonitoringRule:
        """Create a monitoring rule."""
        resp = await self._http.post("/monitoring/rules", json=rule)
        resp.raise_for_status()
        return MonitoringRule.model_validate(resp.json())

    async def get_config(self) -> MonitoringConfig:
        """Get monitoring config."""
        resp = await self._http.get("/monitoring/config")
        resp.raise_for_status()
        return MonitoringConfig.model_validate(resp.json())
