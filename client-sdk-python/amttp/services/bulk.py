"""Bulk Scoring Service — wraps ``/bulk`` endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService


class BulkTransaction(BaseModel):
    from_address: str = ""
    to_address: str = ""
    amount: str = ""
    chain_id: int = 1


class TransactionScoreResult(BaseModel):
    from_address: str = ""
    to_address: str = ""
    risk_score: float = 0
    risk_level: str = "low"
    action: str = "allow"
    error: Optional[str] = None


class BulkScoringRequest(BaseModel):
    transactions: List[BulkTransaction] = []
    include_factors: bool = False


class BulkScoringResult(BaseModel):
    results: List[TransactionScoreResult] = []
    processed_count: int = 0
    failed_count: int = 0


class BulkJobStatus(BaseModel):
    job_id: str = ""
    status: str = "pending"
    progress: float = 0
    total: int = 0
    completed: int = 0
    failed: int = 0
    created_at: str = ""
    completed_at: Optional[str] = None


# ── service ───────────────────────────────────────────────────────────────────


class BulkService(BaseService):
    """Bulk scoring operations."""

    async def score(self, request: BulkScoringRequest) -> BulkScoringResult:
        """Score transactions in bulk (synchronous)."""
        resp = await self._http.post("/bulk/score", json=request.model_dump())
        resp.raise_for_status()
        return BulkScoringResult.model_validate(resp.json())

    async def submit_job(self, request: BulkScoringRequest) -> BulkJobStatus:
        """Submit an async bulk scoring job."""
        resp = await self._http.post("/bulk/submit", json=request.model_dump())
        resp.raise_for_status()
        return BulkJobStatus.model_validate(resp.json())

    async def get_job_status(self, job_id: str) -> BulkJobStatus:
        """Get bulk job status."""
        resp = await self._http.get(f"/bulk/job/{job_id}")
        resp.raise_for_status()
        return BulkJobStatus.model_validate(resp.json())

    async def get_job_results(self, job_id: str) -> BulkScoringResult:
        """Get bulk job results."""
        resp = await self._http.get(f"/bulk/job/{job_id}/results")
        resp.raise_for_status()
        return BulkScoringResult.model_validate(resp.json())

    async def cancel_job(self, job_id: str) -> Dict[str, Any]:
        """Cancel a running bulk job."""
        resp = await self._http.post(f"/bulk/job/{job_id}/cancel")
        resp.raise_for_status()
        return resp.json()
