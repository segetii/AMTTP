"""Enhanced Due Diligence (EDD) Service."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

EDDStatus = Literal[
    "open", "in_progress", "pending_review", "completed", "closed", "escalated"
]
EDDTrigger = Literal["high_risk_score", "pep_match", "sanctions_hit", "manual", "volume_threshold"]


class EDDDocument(BaseModel):
    id: str = ""
    type: str = ""
    name: str = ""
    content_hash: str = ""
    uploaded_at: str = ""
    verified: bool = False


class EDDNote(BaseModel):
    id: str = ""
    author: str = ""
    content: str = ""
    created_at: str = ""


class EDDTimelineEvent(BaseModel):
    type: str = ""
    description: str = ""
    timestamp: str = ""
    actor: Optional[str] = None


class EDDCase(BaseModel):
    id: str = ""
    address: str = ""
    status: str = "open"
    trigger: str = ""
    risk_score: float = 0
    assigned_to: Optional[str] = None
    documents: List[EDDDocument] = []
    notes: List[EDDNote] = []
    timeline: List[EDDTimelineEvent] = []
    created_at: str = ""
    updated_at: str = ""
    closed_at: Optional[str] = None
    outcome: Optional[str] = None


class EDDCreateRequest(BaseModel):
    address: str
    trigger: str = "manual"
    risk_score: Optional[float] = None
    notes: Optional[str] = None


# ── service ───────────────────────────────────────────────────────────────────


class EDDService(BaseService):
    """Enhanced Due Diligence case management."""

    async def create(self, request: EDDCreateRequest) -> EDDCase:
        """Create an EDD case."""
        resp = await self._http.post("/edd", json=request.model_dump(exclude_none=True))
        resp.raise_for_status()
        return EDDCase.model_validate(resp.json())

    async def get(self, case_id: str) -> EDDCase:
        """Get EDD case details."""
        resp = await self._http.get(f"/edd/{case_id}")
        resp.raise_for_status()
        return EDDCase.model_validate(resp.json())

    async def list_cases(
        self,
        *,
        status: Optional[str] = None,
        address: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[EDDCase]:
        """List EDD cases."""
        params: Dict[str, Any] = {}
        if status:
            params["status"] = status
        if address:
            params["address"] = address
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        resp = await self._http.get("/edd", params=params)
        resp.raise_for_status()
        return [EDDCase.model_validate(c) for c in resp.json().get("cases", [])]

    async def update_status(self, case_id: str, status: str) -> EDDCase:
        """Update EDD case status."""
        resp = await self._http.put(f"/edd/{case_id}/status", json={"status": status})
        resp.raise_for_status()
        return EDDCase.model_validate(resp.json())

    async def add_document(
        self, case_id: str, *, doc_type: str, name: str, content_hash: str
    ) -> EDDDocument:
        """Upload a document to an EDD case."""
        resp = await self._http.post(f"/edd/{case_id}/documents", json={
            "type": doc_type, "name": name, "contentHash": content_hash,
        })
        resp.raise_for_status()
        return EDDDocument.model_validate(resp.json())

    async def add_note(self, case_id: str, *, author: str, content: str) -> EDDNote:
        """Add a note to an EDD case."""
        resp = await self._http.post(f"/edd/{case_id}/notes", json={
            "author": author, "content": content,
        })
        resp.raise_for_status()
        return EDDNote.model_validate(resp.json())

    async def close(self, case_id: str, *, outcome: str) -> EDDCase:
        """Close an EDD case."""
        resp = await self._http.post(f"/edd/{case_id}/close", json={"outcome": outcome})
        resp.raise_for_status()
        return EDDCase.model_validate(resp.json())

    async def assign(self, case_id: str, *, assignee: str) -> EDDCase:
        """Assign an EDD case."""
        resp = await self._http.post(f"/edd/{case_id}/assign", json={"assignee": assignee})
        resp.raise_for_status()
        return EDDCase.model_validate(resp.json())
