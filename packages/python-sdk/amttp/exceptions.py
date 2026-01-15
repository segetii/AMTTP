"""
AMTTP Python SDK - Custom Exceptions
"""


class AMTTPError(Exception):
    """Base exception for AMTTP SDK."""
    pass


class ConfigurationError(AMTTPError):
    """Configuration error."""
    pass


class RiskAssessmentError(AMTTPError):
    """Risk assessment failed."""
    def __init__(self, message: str, fallback_score: float = 0.8):
        super().__init__(message)
        self.fallback_score = fallback_score


class ContractError(AMTTPError):
    """Smart contract interaction error."""
    def __init__(self, message: str, tx_hash: str = None):
        super().__init__(message)
        self.tx_hash = tx_hash


class KYCError(AMTTPError):
    """KYC verification error."""
    pass


class PolicyViolationError(AMTTPError):
    """Transaction violates policy."""
    def __init__(self, message: str, action: str = "BLOCK"):
        super().__init__(message)
        self.action = action


class InsufficientFundsError(AMTTPError):
    """Insufficient funds for transaction."""
    pass


class NetworkError(AMTTPError):
    """Network communication error."""
    pass
