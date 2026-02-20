"""Transaction Service — wraps ``/tx`` endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

# ── types ─────────────────────────────────────────────────────────────────────

TransactionStatus = Literal["pending", "processing", "completed", "failed", "cancelled"]


class TransactionRequest(BaseModel):
    from_address: str
    to_address: str
    amount: str
    token_address: Optional[str] = None
    chain_id: int = 1
    memo: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TransactionRecord(BaseModel):
    id: str
    hash: Optional[str] = None
    from_address: str = ""
    to_address: str = ""
    amount: str = ""
    token_address: Optional[str] = None
    chain_id: int = 1
    status: str = "pending"
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None
    policy_result: Optional[Dict[str, Any]] = None
    created_at: str = ""
    updated_at: str = ""
    completed_at: Optional[str] = None
    memo: Optional[str] = None


class TransactionValidation(BaseModel):
    valid: bool = False
    risk_score: float = 0
    risk_level: str = "low"
    policy_result: Optional[Dict[str, Any]] = None
    label_warnings: List[Dict[str, Any]] = []
    estimated_gas: Optional[str] = None


# ── service ───────────────────────────────────────────────────────────────────


class TransactionService(BaseService):
    """Transaction management operations."""

    async def validate(self, request: TransactionRequest) -> TransactionValidation:
        """Validate a transaction before submission."""
        resp = await self._http.post(
            "/tx/validate",
            json=request.model_dump(exclude_none=True, by_alias=True),
        )
        resp.raise_for_status()
        data = TransactionValidation.model_validate(resp.json())
        self._events.emit("transaction:validated", data.model_dump())
        return data

    async def submit(self, request: TransactionRequest) -> TransactionRecord:
        """Submit a new transaction."""
        resp = await self._http.post(
            "/tx/submit",
            json=request.model_dump(exclude_none=True, by_alias=True),
        )
        resp.raise_for_status()
        data = TransactionRecord.model_validate(resp.json())
        self._events.emit("transaction:submitted", {"id": data.id, "hash": data.hash})
        return data

    async def get_status(self, tx_id: str) -> TransactionRecord:
        """Get transaction status."""
        resp = await self._http.get(f"/tx/{tx_id}")
        resp.raise_for_status()
        return TransactionRecord.model_validate(resp.json())

    async def get_history(
        self,
        address: str,
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get transaction history for an address."""
        params: Dict[str, str] = {}
        if limit is not None:
            params["limit"] = str(limit)
        if offset is not None:
            params["offset"] = str(offset)
        if status:
            params["status"] = status
        resp = await self._http.get(f"/tx/history/{address}", params=params)
        resp.raise_for_status()
        return resp.json()

    async def cancel(self, tx_id: str) -> TransactionRecord:
        """Cancel a pending transaction."""
        resp = await self._http.post(f"/tx/{tx_id}/cancel")
        resp.raise_for_status()
        data = TransactionRecord.model_validate(resp.json())
        self._events.emit("transaction:cancelled", {"id": data.id})
        return data

    async def retry(self, tx_id: str) -> TransactionRecord:
        """Retry a failed transaction."""
        resp = await self._http.post(f"/tx/{tx_id}/retry")
        resp.raise_for_status()
        data = TransactionRecord.model_validate(resp.json())
        self._events.emit("transaction:retried", {"id": data.id})
        return data
