"""
AMTTP Python SDK - Type Definitions
"""
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Dict, Any, Optional, List


class PolicyAction(IntEnum):
    """Policy action types matching smart contract enum."""
    APPROVE = 0
    REVIEW = 1
    ESCROW = 2
    BLOCK = 3


class RiskLevel(IntEnum):
    """Risk level types matching smart contract enum."""
    MINIMAL = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class KYCStatusType(str, Enum):
    """KYC status types."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class RiskScore:
    """Risk assessment result from ML model."""
    risk_score: float  # 0.0 - 1.0
    risk_score_int: int  # 0 - 1000 (for contract)
    risk_level: RiskLevel
    action: PolicyAction
    confidence: float
    model_version: str
    recommendations: List[str] = field(default_factory=list)
    features_hash: str = ""
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "RiskScore":
        """Create from API response."""
        return cls(
            risk_score=data.get("risk_score", data.get("riskScore", 0)) / 1000 
                if data.get("risk_score", data.get("riskScore", 0)) > 1 
                else data.get("risk_score", data.get("riskScore", 0)),
            risk_score_int=int(data.get("risk_score", data.get("riskScore", 0)) * 1000) 
                if data.get("risk_score", data.get("riskScore", 0)) <= 1 
                else data.get("risk_score", data.get("riskScore", 0)),
            risk_level=RiskLevel[data.get("risk_level", data.get("riskLevel", "MEDIUM")).upper()]
                if isinstance(data.get("risk_level", data.get("riskLevel")), str)
                else RiskLevel(data.get("risk_level", data.get("riskLevel", 2))),
            action=PolicyAction[data.get("action", "REVIEW").upper()]
                if isinstance(data.get("action"), str)
                else PolicyAction(data.get("action", 1)),
            confidence=data.get("confidence", 0.5),
            model_version=data.get("model_version", data.get("modelVersion", "unknown")),
            recommendations=data.get("recommendations", []),
            features_hash=data.get("features_hash", data.get("featuresHash", "")),
        )
    
    def to_contract_args(self) -> Dict[str, Any]:
        """Format for smart contract call."""
        return {
            "riskScore": self.risk_score_int,
            "modelVersion": self.model_version,
        }


@dataclass
class KYCStatus:
    """KYC verification status."""
    status: KYCStatusType
    kyc_hash: str
    verified_at: Optional[str] = None
    expires_at: Optional[str] = None
    level: int = 1
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "KYCStatus":
        """Create from API response."""
        return cls(
            status=KYCStatusType(data.get("status", "pending")),
            kyc_hash=data.get("kycHash", data.get("kyc_hash", "0x" + "0" * 64)),
            verified_at=data.get("verifiedAt", data.get("verified_at")),
            expires_at=data.get("expiresAt", data.get("expires_at")),
            level=data.get("level", 1),
        )
    
    @property
    def is_valid(self) -> bool:
        """Check if KYC is valid for transactions."""
        return self.status == KYCStatusType.APPROVED


@dataclass
class TransactionRequest:
    """Transaction submission request."""
    to: str  # Recipient address
    value: int  # Amount in wei
    data: bytes = b""  # Transaction data
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "to": self.to,
            "value": str(self.value),
            "data": self.data.hex() if self.data else "",
            "metadata": self.metadata,
        }


@dataclass
class TransactionResult:
    """Transaction submission result."""
    success: bool
    transaction_hash: Optional[str] = None
    risk_score: Optional[RiskScore] = None
    action_taken: Optional[PolicyAction] = None
    escrow_id: Optional[str] = None
    error: Optional[str] = None
    gas_used: Optional[int] = None
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "TransactionResult":
        """Create from API response."""
        risk_data = data.get("riskScore")
        return cls(
            success=data.get("success", False),
            transaction_hash=data.get("transactionHash", data.get("transaction_hash")),
            risk_score=RiskScore.from_api_response(risk_data) if risk_data else None,
            action_taken=PolicyAction(data["actionTaken"]) if "actionTaken" in data else None,
            escrow_id=data.get("escrowId", data.get("escrow_id")),
            error=data.get("error"),
            gas_used=data.get("gasUsed", data.get("gas_used")),
        )


@dataclass
class PolicySettings:
    """User policy settings."""
    max_amount: int  # Maximum transaction amount in wei
    daily_limit: int  # Daily limit in wei
    weekly_limit: int  # Weekly limit in wei
    monthly_limit: int  # Monthly limit in wei
    risk_threshold: int  # Risk threshold (0-1000)
    auto_approve: bool  # Auto-approve low risk transactions
    cooldown_period: int  # Cooldown between large transactions (seconds)
    
    def to_contract_args(self) -> tuple:
        """Format for smart contract call."""
        return (
            self.max_amount,
            self.daily_limit,
            self.weekly_limit,
            self.monthly_limit,
            self.risk_threshold,
            self.auto_approve,
            self.cooldown_period,
        )
    
    @classmethod
    def default(cls) -> "PolicySettings":
        """Create default policy settings."""
        return cls(
            max_amount=100 * 10**18,  # 100 ETH
            daily_limit=50 * 10**18,   # 50 ETH
            weekly_limit=200 * 10**18, # 200 ETH
            monthly_limit=500 * 10**18, # 500 ETH
            risk_threshold=700,  # 0.70
            auto_approve=True,
            cooldown_period=3600,  # 1 hour
        )


@dataclass
class FeatureVector:
    """Transaction feature vector for ML model."""
    amount: float
    gas_price: float
    nonce: int
    hour: int
    day_of_week: int
    velocity_1h: int
    velocity_24h: int
    account_age_days: int
    country_risk: float
    is_contract: bool
    # Add more as needed
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to feature dictionary."""
        return {
            "amount": self.amount,
            "gas_price": self.gas_price,
            "nonce": float(self.nonce),
            "hour": float(self.hour),
            "day_of_week": float(self.day_of_week),
            "velocity_1h": float(self.velocity_1h),
            "velocity_24h": float(self.velocity_24h),
            "account_age_days": float(self.account_age_days),
            "country_risk": self.country_risk,
            "is_contract": float(self.is_contract),
        }
