"""Governance Service — WYAS multi-sig action management."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

ActionType = Literal["policy_override", "risk_threshold", "whitelist", "blacklist", "config_change"]
ActionStatus = Literal["pending", "approved", "rejected", "executed", "cancelled", "expired"]
ActionScope = Literal["global", "per_address", "per_policy"]


class RiskContext(BaseModel):
    risk_score: float = 0
    risk_level: str = "low"
    affected_address: Optional[str] = None


class Signature(BaseModel):
    signer: str = ""
    signature: str = ""
    signed_at: str = ""


class GovernanceAction(BaseModel):
    id: str = ""
    type: str = ""
    status: str = "pending"
    scope: str = "global"
    description: str = ""
    proposed_by: str = ""
    risk_context: Optional[RiskContext] = None
    signatures: List[Signature] = []
    required_signatures: int = 0
    parameters: Optional[Dict[str, Any]] = None
    created_at: str = ""
    executed_at: Optional[str] = None
    expires_at: Optional[str] = None


class CreateActionRequest(BaseModel):
    type: str
    scope: str = "global"
    description: str = ""
    proposed_by: str = ""
    parameters: Optional[Dict[str, Any]] = None
    required_signatures: int = 2


class SignActionRequest(BaseModel):
    signer: str
    signature: str


class SigningResult(BaseModel):
    action_id: str = ""
    signer: str = ""
    total_signatures: int = 0
    required_signatures: int = 0
    quorum_reached: bool = False


class ExecutionResult(BaseModel):
    action_id: str = ""
    executed: bool = False
    tx_hash: Optional[str] = None
    error: Optional[str] = None


class WYASSummary(BaseModel):
    total_actions: int = 0
    pending: int = 0
    approved: int = 0
    executed: int = 0
    rejected: int = 0
    avg_approval_time_hours: float = 0


# ── service ───────────────────────────────────────────────────────────────────


class GovernanceService(BaseService):
    """WYAS governance actions with multi-sig approval."""

    async def create_action(self, request: CreateActionRequest) -> GovernanceAction:
        """Propose a new governance action."""
        resp = await self._http.post(
            "/governance/actions", json=request.model_dump(exclude_none=True)
        )
        resp.raise_for_status()
        data = GovernanceAction.model_validate(resp.json())
        self._events.emit("governance:action_created", data.model_dump())
        return data

    async def get_action(self, action_id: str) -> GovernanceAction:
        """Get governance action details."""
        resp = await self._http.get(f"/governance/actions/{action_id}")
        resp.raise_for_status()
        return GovernanceAction.model_validate(resp.json())

    async def list_actions(
        self,
        *,
        status: Optional[str] = None,
        action_type: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[GovernanceAction]:
        """List governance actions."""
        params: Dict[str, Any] = {}
        if status:
            params["status"] = status
        if action_type:
            params["type"] = action_type
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        resp = await self._http.get("/governance/actions", params=params)
        resp.raise_for_status()
        return [GovernanceAction.model_validate(a) for a in resp.json().get("actions", [])]

    async def sign_action(self, action_id: str, request: SignActionRequest) -> SigningResult:
        """Sign a governance action."""
        resp = await self._http.post(
            f"/governance/actions/{action_id}/sign", json=request.model_dump()
        )
        resp.raise_for_status()
        data = SigningResult.model_validate(resp.json())
        self._events.emit("governance:signature_added", {
            "action_id": action_id, "signer": request.signer
        })
        if data.quorum_reached:
            self._events.emit("governance:quorum_reached", {"action_id": action_id})
        return data

    async def execute_action(self, action_id: str) -> ExecutionResult:
        """Execute an approved governance action."""
        resp = await self._http.post(f"/governance/actions/{action_id}/execute")
        resp.raise_for_status()
        data = ExecutionResult.model_validate(resp.json())
        if data.executed:
            self._events.emit("governance:action_executed", {"action_id": action_id})
        return data

    async def cancel_action(self, action_id: str) -> GovernanceAction:
        """Cancel a governance action."""
        resp = await self._http.post(f"/governance/actions/{action_id}/cancel")
        resp.raise_for_status()
        data = GovernanceAction.model_validate(resp.json())
        self._events.emit("governance:action_cancelled", {"action_id": action_id})
        return data

    async def get_summary(self) -> WYASSummary:
        """Get governance summary."""
        resp = await self._http.get("/governance/summary")
        resp.raise_for_status()
        return WYASSummary.model_validate(resp.json())

    async def health(self) -> Dict[str, Any]:
        """Check service health."""
        resp = await self._http.get("/governance/health")
        resp.raise_for_status()
        return resp.json()
