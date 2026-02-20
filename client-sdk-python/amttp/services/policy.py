"""Policy Service — wraps ``/policy`` endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

# ── types ─────────────────────────────────────────────────────────────────────

PolicyDecision = Literal["allow", "deny", "review", "escalate"]


class PolicyCondition(BaseModel):
    field: str = ""
    operator: str = ""
    value: Any = None


class PolicyAction(BaseModel):
    type: str = ""
    parameters: Optional[Dict[str, Any]] = None


class Policy(BaseModel):
    id: str = ""
    name: str = ""
    description: str = ""
    conditions: List[PolicyCondition] = []
    actions: List[PolicyAction] = []
    priority: int = 0
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""


class PolicyEvaluationRequest(BaseModel):
    address: str
    transaction_type: Optional[str] = None
    amount: Optional[str] = None
    chain_id: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class PolicyEvaluationResult(BaseModel):
    decision: str = "review"
    applied_policies: List[str] = []
    reasons: List[str] = []
    required_approvals: int = 0
    actions: List[PolicyAction] = []


class PolicyCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    conditions: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []
    priority: int = 0
    enabled: bool = True


# ── service ───────────────────────────────────────────────────────────────────


class PolicyService(BaseService):
    """Policy management and evaluation."""

    async def evaluate(self, request: PolicyEvaluationRequest) -> PolicyEvaluationResult:
        """Evaluate policies for a transaction."""
        resp = await self._http.post("/policy/evaluate", json=request.model_dump(exclude_none=True))
        resp.raise_for_status()
        data = PolicyEvaluationResult.model_validate(resp.json())
        self._events.emit("policy:evaluated", data.model_dump())
        return data

    async def list_policies(self) -> List[Policy]:
        """List all policies."""
        resp = await self._http.get("/policy")
        resp.raise_for_status()
        return [Policy.model_validate(p) for p in resp.json().get("policies", [])]

    async def get_policy(self, policy_id: str) -> Policy:
        """Get a specific policy."""
        resp = await self._http.get(f"/policy/{policy_id}")
        resp.raise_for_status()
        return Policy.model_validate(resp.json())

    async def create(self, request: PolicyCreateRequest) -> Policy:
        """Create a new policy."""
        resp = await self._http.post("/policy", json=request.model_dump(exclude_none=True))
        resp.raise_for_status()
        data = Policy.model_validate(resp.json())
        self._events.emit("policy:created", data.model_dump())
        return data

    async def update(self, policy_id: str, updates: Dict[str, Any]) -> Policy:
        """Update a policy."""
        resp = await self._http.put(f"/policy/{policy_id}", json=updates)
        resp.raise_for_status()
        data = Policy.model_validate(resp.json())
        self._events.emit("policy:updated", data.model_dump())
        return data

    async def delete(self, policy_id: str) -> None:
        """Delete a policy."""
        resp = await self._http.delete(f"/policy/{policy_id}")
        resp.raise_for_status()
        self._events.emit("policy:deleted", {"policy_id": policy_id})
