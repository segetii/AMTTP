"""Profile Service — entity profile management shorthand."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService


class ProfileSummary(BaseModel):
    address: str = ""
    entity_type: str = "UNVERIFIED"
    kyc_level: str = "NONE"
    risk_score: Optional[float] = None
    total_transactions: int = 0
    created_at: str = ""


# ── service ───────────────────────────────────────────────────────────────────


class ProfileService(BaseService):
    """Convenience wrapper for entity profile operations (delegated to Compliance)."""

    async def get(self, address: str) -> Dict[str, Any]:
        """Get entity profile."""
        resp = await self._http.get(f"/profiles/{address}")
        resp.raise_for_status()
        return resp.json()

    async def update(self, address: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update entity profile."""
        resp = await self._http.put(f"/profiles/{address}", json=updates)
        resp.raise_for_status()
        return resp.json()

    async def set_entity_type(self, address: str, entity_type: str) -> Dict[str, Any]:
        """Set entity type."""
        resp = await self._http.post(f"/profiles/{address}/set-type/{entity_type}")
        resp.raise_for_status()
        return resp.json()

    async def list_all(
        self, *, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> List[ProfileSummary]:
        """List all profiles."""
        params: Dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        resp = await self._http.get("/profiles", params=params)
        resp.raise_for_status()
        return [ProfileSummary.model_validate(p) for p in resp.json().get("profiles", [])]
