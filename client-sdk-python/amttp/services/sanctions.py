"""Sanctions Service — OFAC / EU / UN sanctions screening."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

# ── types ─────────────────────────────────────────────────────────────────────

MatchType = Literal["address", "name", "fuzzy_name", "alias"]


class SanctionedEntity(BaseModel):
    id: str = ""
    name: str = ""
    aliases: List[str] = []
    source_list: str = ""
    sanctions_type: str = ""
    country: Optional[str] = None
    listed_date: Optional[str] = None
    addresses: List[str] = []
    programs: List[str] = []


class SanctionsMatch(BaseModel):
    match_type: str = ""
    confidence: float = 0
    entity: Optional[SanctionedEntity] = None
    matched_field: Optional[str] = None
    matched_value: Optional[str] = None


class SanctionsCheckRequest(BaseModel):
    address: Optional[str] = None
    name: Optional[str] = None
    country: Optional[str] = None
    include_fuzzy: Optional[bool] = None
    threshold: Optional[float] = None


class SanctionsCheckResponse(BaseModel):
    query: Optional[Dict[str, Any]] = None
    is_sanctioned: bool = False
    matches: List[SanctionsMatch] = []
    check_timestamp: str = ""
    lists_checked: List[str] = []
    processing_time_ms: float = 0


class BatchCheckResult(BaseModel):
    address: str = ""
    is_sanctioned: bool = False
    matches: List[SanctionsMatch] = []


class BatchCheckResponse(BaseModel):
    results: List[BatchCheckResult] = []
    total_checked: int = 0
    total_sanctioned: int = 0
    check_timestamp: str = ""


class SanctionsStats(BaseModel):
    total_entities: int = 0
    indexed_names: int = 0
    indexed_addresses: int = 0
    indexed_countries: int = 0
    hardcoded_crypto_addresses: int = 0
    last_refresh: Dict[str, str] = {}
    load_timestamp: str = ""


class SanctionsList(BaseModel):
    id: str = ""
    name: str = ""
    source: str = ""
    entity_count: int = 0
    last_updated: str = ""


# ── service ───────────────────────────────────────────────────────────────────


class SanctionsService(BaseService):
    """Sanctions screening."""

    async def check(self, request: SanctionsCheckRequest) -> SanctionsCheckResponse:
        """Check an address or name against sanctions lists."""
        resp = await self._http.post(
            "/sanctions/check", json=request.model_dump(exclude_none=True)
        )
        resp.raise_for_status()
        data = SanctionsCheckResponse.model_validate(resp.json())
        self._events.emit("sanctions:checked", data.model_dump())
        if data.is_sanctioned and data.matches:
            entity = data.matches[0].entity
            if entity:
                self._events.emit(
                    "sanctions:match", request.address or "", entity.source_list
                )
        return data

    async def batch_check(self, addresses: List[str], *, include_fuzzy: bool = False) -> BatchCheckResponse:
        """Check multiple addresses in batch."""
        resp = await self._http.post(
            "/sanctions/batch-check",
            json={"addresses": addresses, "include_fuzzy": include_fuzzy},
        )
        resp.raise_for_status()
        return BatchCheckResponse.model_validate(resp.json())

    async def check_crypto_address(self, address: str) -> SanctionsCheckResponse:
        """Check a crypto address (e.g. Tornado Cash, Lazarus)."""
        return await self.check(SanctionsCheckRequest(
            address=address.lower(), include_fuzzy=False
        ))

    async def check_name(self, name: str, threshold: float = 0.85) -> SanctionsCheckResponse:
        """Check a name with fuzzy matching."""
        return await self.check(SanctionsCheckRequest(
            name=name, include_fuzzy=True, threshold=threshold
        ))

    async def refresh(self) -> Dict[str, str]:
        """Refresh sanctions lists from sources."""
        resp = await self._http.post("/sanctions/refresh")
        resp.raise_for_status()
        return resp.json()

    async def get_stats(self) -> SanctionsStats:
        """Get sanctions database statistics."""
        resp = await self._http.get("/sanctions/stats")
        resp.raise_for_status()
        return SanctionsStats.model_validate(resp.json())

    async def get_lists(self) -> List[SanctionsList]:
        """Get available sanctions lists."""
        resp = await self._http.get("/sanctions/lists")
        resp.raise_for_status()
        return [SanctionsList.model_validate(s) for s in resp.json().get("lists", [])]

    async def health(self) -> Dict[str, Any]:
        """Check service health."""
        resp = await self._http.get("/health")
        resp.raise_for_status()
        return resp.json()
