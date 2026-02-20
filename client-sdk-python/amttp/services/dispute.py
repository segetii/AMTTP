"""Dispute Service — wraps ``/dispute`` endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

# ── types ─────────────────────────────────────────────────────────────────────

DisputeStatus = Literal[
    "open", "in_review", "awaiting_evidence", "resolved", "appealed", "closed"
]
DisputeRuling = Literal["claimant_wins", "respondent_wins", "split", "dismissed"]


class Evidence(BaseModel):
    id: str = ""
    type: str = ""
    content_hash: str = ""
    description: str = ""
    submitted_by: str = ""
    submitted_at: str = ""


class TimelineEvent(BaseModel):
    type: str = ""
    description: str = ""
    timestamp: str = ""
    actor: Optional[str] = None


class Dispute(BaseModel):
    id: str = ""
    transaction_hash: str = ""
    claimant: str = ""
    respondent: str = ""
    status: str = "open"
    ruling: Optional[str] = None
    amount: str = ""
    reason: str = ""
    evidence: List[Evidence] = []
    timeline: List[TimelineEvent] = []
    created_at: str = ""
    updated_at: str = ""
    resolved_at: Optional[str] = None


class DisputeCreateRequest(BaseModel):
    transaction_hash: str
    claimant: str
    respondent: str
    amount: str
    reason: str
    evidence_hash: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# ── service ───────────────────────────────────────────────────────────────────


class DisputeService(BaseService):
    """Dispute management (Kleros-compatible)."""

    async def create(self, request: DisputeCreateRequest) -> Dispute:
        """Create a new dispute."""
        resp = await self._http.post("/dispute", json=request.model_dump(exclude_none=True))
        resp.raise_for_status()
        data = Dispute.model_validate(resp.json())
        self._events.emit("dispute:created", data.model_dump())
        return data

    async def get(self, dispute_id: str) -> Dispute:
        """Get dispute details."""
        resp = await self._http.get(f"/dispute/{dispute_id}")
        resp.raise_for_status()
        return Dispute.model_validate(resp.json())

    async def list_disputes(
        self,
        *,
        status: Optional[str] = None,
        claimant: Optional[str] = None,
        respondent: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dispute]:
        """List disputes with optional filters."""
        params: Dict[str, Any] = {}
        if status:
            params["status"] = status
        if claimant:
            params["claimant"] = claimant
        if respondent:
            params["respondent"] = respondent
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        resp = await self._http.get("/dispute", params=params)
        resp.raise_for_status()
        return [Dispute.model_validate(d) for d in resp.json().get("disputes", [])]

    async def submit_evidence(
        self, dispute_id: str, *, content_hash: str, description: str, submitted_by: str
    ) -> Evidence:
        """Submit evidence for a dispute."""
        resp = await self._http.post(f"/dispute/{dispute_id}/evidence", json={
            "contentHash": content_hash,
            "description": description,
            "submittedBy": submitted_by,
        })
        resp.raise_for_status()
        data = Evidence.model_validate(resp.json())
        self._events.emit("dispute:evidenceSubmitted", {
            "dispute_id": dispute_id,
            "evidence_id": data.id,
        })
        return data

    async def escalate(self, dispute_id: str) -> Dispute:
        """Escalate a dispute."""
        resp = await self._http.post(f"/dispute/{dispute_id}/escalate")
        resp.raise_for_status()
        data = Dispute.model_validate(resp.json())
        self._events.emit("dispute:escalated", {"dispute_id": dispute_id})
        return data

    async def resolve(self, dispute_id: str, ruling: str, *, reason: Optional[str] = None) -> Dispute:
        """Resolve a dispute."""
        payload: Dict[str, Any] = {"ruling": ruling}
        if reason:
            payload["reason"] = reason
        resp = await self._http.post(f"/dispute/{dispute_id}/resolve", json=payload)
        resp.raise_for_status()
        data = Dispute.model_validate(resp.json())
        self._events.emit("dispute:resolved", dispute_id, ruling)
        return data

    async def appeal(self, dispute_id: str, *, reason: str) -> Dispute:
        """Appeal a dispute ruling."""
        resp = await self._http.post(f"/dispute/{dispute_id}/appeal", json={"reason": reason})
        resp.raise_for_status()
        data = Dispute.model_validate(resp.json())
        self._events.emit("dispute:appealed", {"dispute_id": dispute_id})
        return data

    async def withdraw(self, dispute_id: str) -> Dispute:
        """Withdraw a dispute."""
        resp = await self._http.post(f"/dispute/{dispute_id}/withdraw")
        resp.raise_for_status()
        data = Dispute.model_validate(resp.json())
        self._events.emit("dispute:withdrawn", {"dispute_id": dispute_id})
        return data
