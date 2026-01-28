# AMTTP Python Client SDK
from .client import AMTTPClient, AMTTPConfig
from .types import (
    RiskScore,
    PolicyAction,
    TransactionRequest,
    TransactionResult,
    KYCStatus,
    PolicySettings,
)
from .exceptions import (
    AMTTPError,
    RiskAssessmentError,
    ContractError,
    ConfigurationError,
)
from .explainability import (
    ExplainabilityService,
    RiskExplanation,
    ExplanationFactor,
    TypologyMatch,
    ImpactLevel,
    TypologyType,
    TYPOLOGIES,
    format_explanation,
)

__version__ = "1.0.0"
__all__ = [
    # Client
    "AMTTPClient",
    "AMTTPConfig",
    # Types
    "RiskScore",
    "PolicyAction",
    "TransactionRequest",
    "TransactionResult",
    "KYCStatus",
    "PolicySettings",
    # Exceptions
    "AMTTPError",
    "RiskAssessmentError",
    "ContractError",
    "ConfigurationError",
    # Explainability
    "ExplainabilityService",
    "RiskExplanation",
    "ExplanationFactor",
    "TypologyMatch",
    "ImpactLevel",
    "TypologyType",
    "TYPOLOGIES",
    "format_explanation",
]
