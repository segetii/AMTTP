"""Integrity Service — UI snapshot hashing and audit-trail verification."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService


class SnapshotData(BaseModel):
    snapshot_hash: str = ""
    ui_state: Optional[Dict[str, Any]] = None
    timestamp: str = ""
    verified: bool = False


class RegisterHashRequest(BaseModel):
    snapshot_hash: str
    ui_state: Optional[Dict[str, Any]] = None
    decision_id: Optional[str] = None


class RegisterHashResponse(BaseModel):
    id: str = ""
    snapshot_hash: str = ""
    registered_at: str = ""
    on_chain: bool = False
    tx_hash: Optional[str] = None


class VerifyIntegrityRequest(BaseModel):
    snapshot_hash: str
    decision_id: Optional[str] = None


class VerifyIntegrityResponse(BaseModel):
    verified: bool = False
    snapshot_hash: str = ""
    registered_at: Optional[str] = None
    on_chain_verified: bool = False
    mismatch_details: Optional[Dict[str, Any]] = None


class PaymentSubmission(BaseModel):
    from_address: str
    to_address: str
    value_eth: float
    ui_snapshot_hash: str
    chain_id: int = 1


class PaymentSubmissionResponse(BaseModel):
    submission_id: str = ""
    integrity_verified: bool = False
    decision_id: Optional[str] = None
    tx_hash: Optional[str] = None


class IntegrityViolation(BaseModel):
    id: str = ""
    type: str = ""
    description: str = ""
    snapshot_hash: str = ""
    detected_at: str = ""
    severity: str = "high"


# ── service ───────────────────────────────────────────────────────────────────


class IntegrityService(BaseService):
    """UI integrity verification for audit trails."""

    async def register_hash(self, request: RegisterHashRequest) -> RegisterHashResponse:
        """Register a UI snapshot hash."""
        resp = await self._http.post("/integrity/register", json=request.model_dump(exclude_none=True))
        resp.raise_for_status()
        return RegisterHashResponse.model_validate(resp.json())

    async def verify(self, request: VerifyIntegrityRequest) -> VerifyIntegrityResponse:
        """Verify a UI snapshot hash."""
        resp = await self._http.post("/integrity/verify", json=request.model_dump(exclude_none=True))
        resp.raise_for_status()
        data = VerifyIntegrityResponse.model_validate(resp.json())
        self._events.emit("integrity:verified", data.model_dump())
        if not data.verified:
            self._events.emit("integrity:violation", data.model_dump())
        return data

    async def submit_payment(self, request: PaymentSubmission) -> PaymentSubmissionResponse:
        """Submit a payment with integrity binding."""
        resp = await self._http.post(
            "/integrity/submit-payment", json=request.model_dump(exclude_none=True)
        )
        resp.raise_for_status()
        return PaymentSubmissionResponse.model_validate(resp.json())

    async def get_violations(
        self, *, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> List[IntegrityViolation]:
        """Get integrity violations."""
        params: Dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        resp = await self._http.get("/integrity/violations", params=params)
        resp.raise_for_status()
        return [IntegrityViolation.model_validate(v) for v in resp.json().get("violations", [])]

    async def health(self) -> Dict[str, Any]:
        """Check service health."""
        resp = await self._http.get("/integrity/health")
        resp.raise_for_status()
        return resp.json()
