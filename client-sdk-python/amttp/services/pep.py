"""PEP (Politically Exposed Persons) Service."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService


class PEPMatch(BaseModel):
    name: str = ""
    position: str = ""
    country: str = ""
    confidence: float = 0
    source: str = ""
    match_type: str = ""
    pep_type: str = ""


class PEPScreeningRequest(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    date_of_birth: Optional[str] = None
    threshold: float = 0.85


class PEPScreeningResult(BaseModel):
    is_pep: bool = False
    matches: List[PEPMatch] = []
    screened_at: str = ""
    processing_time_ms: float = 0


class PEPHistoryEntry(BaseModel):
    id: str = ""
    query: Optional[Dict[str, Any]] = None
    is_pep: bool = False
    match_count: int = 0
    screened_at: str = ""


# ── service ───────────────────────────────────────────────────────────────────


class PEPService(BaseService):
    """PEP screening."""

    async def screen(self, request: PEPScreeningRequest) -> PEPScreeningResult:
        """Screen an individual against PEP lists."""
        resp = await self._http.post("/pep/screen", json=request.model_dump(exclude_none=True))
        resp.raise_for_status()
        return PEPScreeningResult.model_validate(resp.json())

    async def screen_address(self, address: str) -> PEPScreeningResult:
        """Screen an address for PEP associations."""
        return await self.screen(PEPScreeningRequest(address=address))

    async def screen_name(self, name: str, *, threshold: float = 0.85) -> PEPScreeningResult:
        """Screen a name against PEP lists."""
        return await self.screen(PEPScreeningRequest(name=name, threshold=threshold))

    async def get_history(
        self, *, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> List[PEPHistoryEntry]:
        """Get PEP screening history."""
        params: Dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        resp = await self._http.get("/pep/history", params=params)
        resp.raise_for_status()
        return [PEPHistoryEntry.model_validate(h) for h in resp.json().get("history", [])]

    async def health(self) -> Dict[str, Any]:
        """Check service health."""
        resp = await self._http.get("/pep/health")
        resp.raise_for_status()
        return resp.json()
