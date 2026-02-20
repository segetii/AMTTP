"""Label Service — address labelling and classification."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

LabelCategory = Literal["exchange", "defi", "mixing", "gambling", "scam", "darknet", "unknown"]
LabelSeverity = Literal["none", "low", "medium", "high", "critical"]


class AddressLabel(BaseModel):
    address: str = ""
    label: str = ""
    category: str = "unknown"
    severity: str = "none"
    source: str = ""
    confidence: float = 0
    added_at: str = ""
    metadata: Optional[Dict[str, Any]] = None


class LabelSearchResult(BaseModel):
    labels: List[AddressLabel] = []
    total: int = 0


class LabelStatistics(BaseModel):
    total_labels: int = 0
    by_category: Dict[str, int] = {}
    by_severity: Dict[str, int] = {}
    sources: List[str] = []


# ── service ───────────────────────────────────────────────────────────────────


class LabelService(BaseService):
    """Address label management."""

    async def get_labels(self, address: str) -> List[AddressLabel]:
        """Get labels for an address."""
        resp = await self._http.get(f"/labels/{address}")
        resp.raise_for_status()
        return [AddressLabel.model_validate(l) for l in resp.json().get("labels", [])]

    async def add_label(
        self,
        address: str,
        *,
        label: str,
        category: str = "unknown",
        severity: str = "none",
        source: str = "manual",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AddressLabel:
        """Add a label to an address."""
        payload: Dict[str, Any] = {
            "address": address,
            "label": label,
            "category": category,
            "severity": severity,
            "source": source,
        }
        if metadata:
            payload["metadata"] = metadata
        resp = await self._http.post("/labels", json=payload)
        resp.raise_for_status()
        return AddressLabel.model_validate(resp.json())

    async def remove_label(self, address: str, label_id: str) -> None:
        """Remove a label."""
        resp = await self._http.delete(f"/labels/{address}/{label_id}")
        resp.raise_for_status()

    async def search(
        self,
        *,
        query: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> LabelSearchResult:
        """Search labels."""
        params: Dict[str, Any] = {}
        if query:
            params["q"] = query
        if category:
            params["category"] = category
        if severity:
            params["severity"] = severity
        if limit is not None:
            params["limit"] = limit
        resp = await self._http.get("/labels/search", params=params)
        resp.raise_for_status()
        return LabelSearchResult.model_validate(resp.json())

    async def get_statistics(self) -> LabelStatistics:
        """Get label statistics."""
        resp = await self._http.get("/labels/stats")
        resp.raise_for_status()
        return LabelStatistics.model_validate(resp.json())
