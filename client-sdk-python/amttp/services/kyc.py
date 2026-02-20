"""KYC (Know Your Customer) Service — wraps ``/kyc`` endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

# ── types ─────────────────────────────────────────────────────────────────────

KYCStatus = Literal["none", "pending", "verified", "rejected", "expired"]
KYCLevel = Literal["none", "basic", "standard", "enhanced"]


class KYCSubmission(BaseModel):
    address: str
    document_type: Literal["passport", "driving_license", "national_id"]
    document_number: str
    first_name: str
    last_name: str
    date_of_birth: str
    nationality: str
    document_front_hash: Optional[str] = None
    document_back_hash: Optional[str] = None
    selfie_hash: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class KYCVerificationResult(BaseModel):
    address: str
    status: str = "none"
    level: str = "none"
    verified_at: Optional[str] = None
    expires_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    required_documents: Optional[List[str]] = None
    provider: Optional[str] = None


class KYCDocument(BaseModel):
    id: str
    type: str
    status: Literal["pending", "verified", "rejected"]
    uploaded_at: str
    verified_at: Optional[str] = None
    expires_at: Optional[str] = None


class KYCRequirements(BaseModel):
    level: str
    required_documents: List[str] = []
    max_transaction_limit: str = ""
    features: List[str] = []


# ── service ───────────────────────────────────────────────────────────────────


class KYCService(BaseService):
    """KYC verification operations."""

    async def submit(self, submission: KYCSubmission) -> KYCVerificationResult:
        """Submit KYC documents for verification."""
        resp = await self._http.post("/kyc/submit", json=submission.model_dump(exclude_none=True))
        resp.raise_for_status()
        data = KYCVerificationResult.model_validate(resp.json())
        self._events.emit("kyc:submitted", {
            "address": submission.address,
            "document_type": submission.document_type,
        })
        return data

    async def get_status(self, address: str) -> KYCVerificationResult:
        """Get KYC status for an address."""
        resp = await self._http.get(f"/kyc/status/{address}")
        resp.raise_for_status()
        return KYCVerificationResult.model_validate(resp.json())

    async def is_verified(self, address: str) -> bool:
        """Check if address is KYC verified."""
        status = await self.get_status(address)
        return status.status == "verified"

    async def get_level(self, address: str) -> str:
        """Get KYC level for an address."""
        status = await self.get_status(address)
        return status.level

    async def upload_document(
        self,
        address: str,
        *,
        doc_type: str,
        content_hash: str,
        mime_type: str,
        encrypted_content: Optional[str] = None,
    ) -> Dict[str, str]:
        """Upload a document for KYC verification."""
        payload: Dict[str, Any] = {
            "type": doc_type,
            "contentHash": content_hash,
            "mimeType": mime_type,
        }
        if encrypted_content:
            payload["encryptedContent"] = encrypted_content
        resp = await self._http.post(f"/kyc/documents/{address}", json=payload)
        resp.raise_for_status()
        result = resp.json()
        self._events.emit("kyc:documentUploaded", {
            "address": address,
            "document_type": doc_type,
            "document_id": result.get("documentId"),
        })
        return result

    async def get_documents(self, address: str) -> List[KYCDocument]:
        """Get uploaded documents for an address."""
        resp = await self._http.get(f"/kyc/documents/{address}")
        resp.raise_for_status()
        return [KYCDocument.model_validate(d) for d in resp.json().get("documents", [])]

    async def get_requirements(self, level: Optional[str] = None) -> List[KYCRequirements]:
        """Get KYC requirements for a specific level."""
        url = f"/kyc/requirements?level={level}" if level else "/kyc/requirements"
        resp = await self._http.get(url)
        resp.raise_for_status()
        return [KYCRequirements.model_validate(r) for r in resp.json().get("requirements", [])]

    async def request_upgrade(self, address: str, target_level: str) -> Dict[str, Any]:
        """Request KYC level upgrade."""
        resp = await self._http.post("/kyc/upgrade", json={
            "address": address, "targetLevel": target_level,
        })
        resp.raise_for_status()
        result = resp.json()
        self._events.emit("kyc:upgradeRequested", {
            "address": address,
            "target_level": target_level,
            "request_id": result.get("requestId"),
        })
        return result

    async def verify_on_chain(self, address: str, chain_id: int) -> Dict[str, Any]:
        """Verify KYC attestation on-chain."""
        resp = await self._http.get(f"/kyc/verify-onchain/{address}?chainId={chain_id}")
        resp.raise_for_status()
        return resp.json()

    async def renew(self, address: str) -> KYCVerificationResult:
        """Renew expiring KYC."""
        resp = await self._http.post(f"/kyc/renew/{address}")
        resp.raise_for_status()
        self._events.emit("kyc:renewed", {"address": address})
        return KYCVerificationResult.model_validate(resp.json())

    async def check_expiry(self, address: str) -> Dict[str, Any]:
        """Check if KYC is expiring soon."""
        resp = await self._http.get(f"/kyc/expiry/{address}")
        resp.raise_for_status()
        return resp.json()
