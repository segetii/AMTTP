"""
AMTTP Python SDK — errors module.

Custom exception hierarchy mirroring the TypeScript SDK error codes.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional


class AMTTPErrorCode(str, Enum):
    """All error codes emitted by the AMTTP SDK."""

    # Network
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"

    # Auth
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"

    # Validation
    INVALID_ADDRESS = "INVALID_ADDRESS"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    INVALID_PARAMETERS = "INVALID_PARAMETERS"

    # Risk / compliance
    HIGH_RISK_BLOCKED = "HIGH_RISK_BLOCKED"
    SANCTIONED_ADDRESS = "SANCTIONED_ADDRESS"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    KYC_REQUIRED = "KYC_REQUIRED"
    EDD_REQUIRED = "EDD_REQUIRED"

    # Transaction
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    TRANSACTION_FAILED = "TRANSACTION_FAILED"
    ESCROW_REQUIRED = "ESCROW_REQUIRED"

    # Dispute
    DISPUTE_NOT_FOUND = "DISPUTE_NOT_FOUND"
    EVIDENCE_REJECTED = "EVIDENCE_REJECTED"

    # General
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    SERVER_ERROR = "SERVER_ERROR"
    UNKNOWN = "UNKNOWN"


_STATUS_CODE_MAP: Dict[int, AMTTPErrorCode] = {
    400: AMTTPErrorCode.INVALID_PARAMETERS,
    401: AMTTPErrorCode.UNAUTHORIZED,
    403: AMTTPErrorCode.FORBIDDEN,
    404: AMTTPErrorCode.NOT_FOUND,
    429: AMTTPErrorCode.RATE_LIMITED,
    451: AMTTPErrorCode.POLICY_VIOLATION,
    500: AMTTPErrorCode.SERVER_ERROR,
    502: AMTTPErrorCode.SERVER_ERROR,
    503: AMTTPErrorCode.SERVER_ERROR,
}

_RETRYABLE = {
    AMTTPErrorCode.NETWORK_ERROR,
    AMTTPErrorCode.TIMEOUT,
    AMTTPErrorCode.SERVER_ERROR,
    AMTTPErrorCode.RATE_LIMITED,
}


class AMTTPError(Exception):
    """Base exception for all AMTTP SDK errors."""

    def __init__(
        self,
        message: str,
        code: AMTTPErrorCode = AMTTPErrorCode.UNKNOWN,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details or {}

    def is_retryable(self) -> bool:
        return self.code in _RETRYABLE

    @classmethod
    def from_response(cls, status: int, data: Optional[Dict[str, Any]] = None) -> "AMTTPError":
        """Create an :class:`AMTTPError` from an HTTP response."""
        data = data or {}
        message = data.get("message", "An error occurred")
        raw_code = data.get("code", "")
        code = _STATUS_CODE_MAP.get(status, AMTTPErrorCode.UNKNOWN)
        # Sanctions-specific override
        if status == 403 and raw_code == "SANCTIONED":
            code = AMTTPErrorCode.SANCTIONED_ADDRESS
        return cls(message=message, code=code, status_code=status, details=data.get("details"))

    def __repr__(self) -> str:
        return f"AMTTPError({self.code.value!r}, {str(self)!r}, status={self.status_code})"
