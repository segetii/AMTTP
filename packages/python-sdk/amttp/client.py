"""
AMTTP Python SDK - Main Client

Provides easy integration with AMTTP fraud detection and policy engine.
"""
import os
import json
import logging
import hashlib
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from datetime import datetime

import requests
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account

from .types import (
    RiskScore,
    PolicyAction,
    RiskLevel,
    TransactionRequest,
    TransactionResult,
    KYCStatus,
    PolicySettings,
    FeatureVector,
)
from .exceptions import (
    AMTTPError,
    RiskAssessmentError,
    ContractError,
    ConfigurationError,
    KYCError,
    PolicyViolationError,
)

logger = logging.getLogger(__name__)


@dataclass
class AMTTPConfig:
    """AMTTP Client configuration."""
    # Network
    rpc_url: str
    chain_id: int = 1
    
    # Contracts
    amttp_contract: str = ""
    policy_engine_contract: str = ""
    policy_manager_contract: str = ""
    
    # Oracle/API
    oracle_url: str = "http://localhost:3000"
    ml_api_url: str = "http://localhost:8000"
    
    # Authentication
    private_key: Optional[str] = None
    
    # Timeouts
    request_timeout: int = 30
    
    @classmethod
    def from_env(cls) -> "AMTTPConfig":
        """Create config from environment variables."""
        return cls(
            rpc_url=os.environ.get("RPC_URL", "http://localhost:8545"),
            chain_id=int(os.environ.get("CHAIN_ID", "1")),
            amttp_contract=os.environ.get("AMTTP_CONTRACT", ""),
            policy_engine_contract=os.environ.get("POLICY_ENGINE_CONTRACT", ""),
            policy_manager_contract=os.environ.get("POLICY_MANAGER_CONTRACT", ""),
            oracle_url=os.environ.get("ORACLE_URL", "http://localhost:3000"),
            ml_api_url=os.environ.get("ML_API_URL", "http://localhost:8000"),
            private_key=os.environ.get("PRIVATE_KEY"),
            request_timeout=int(os.environ.get("REQUEST_TIMEOUT", "30")),
        )


# Minimal ABI for policy contracts
POLICY_ENGINE_ABI = [
    {
        "inputs": [
            {"name": "user", "type": "address"},
            {"name": "counterparty", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "dqnRiskScore", "type": "uint256"},
            {"name": "modelVersion", "type": "string"},
            {"name": "kycHash", "type": "bytes32"}
        ],
        "name": "validateTransaction",
        "outputs": [
            {"name": "action", "type": "uint8"},
            {"name": "reason", "type": "string"}
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"name": "user", "type": "address"}],
        "name": "userPolicies",
        "outputs": [
            {"name": "maxAmount", "type": "uint256"},
            {"name": "dailyLimit", "type": "uint256"},
            {"name": "riskThreshold", "type": "uint256"},
            {"name": "autoApprove", "type": "bool"},
            {"name": "enabled", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
]

POLICY_MANAGER_ABI = [
    {
        "inputs": [
            {"name": "user", "type": "address"},
            {"name": "counterparty", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "riskScore", "type": "uint256"}
        ],
        "name": "validateTransaction",
        "outputs": [
            {"name": "allowed", "type": "bool"},
            {"name": "recommendedRiskLevel", "type": "uint8"},
            {"name": "reason", "type": "string"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "user", "type": "address"},
            {"name": "maxAmount", "type": "uint256"},
            {"name": "riskThreshold", "type": "uint256"}
        ],
        "name": "setUserPolicy",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
]


class AMTTPClient:
    """
    AMTTP Python Client
    
    Integrates ML-based fraud detection with blockchain policy enforcement.
    
    Usage:
        ```python
        from amttp import AMTTPClient, AMTTPConfig
        
        config = AMTTPConfig(
            rpc_url="https://mainnet.infura.io/v3/YOUR_KEY",
            oracle_url="https://oracle.amttp.io",
            ml_api_url="https://ml.amttp.io",
            private_key="0x..."
        )
        
        client = AMTTPClient(config)
        
        # Score a transaction
        risk = client.score_transaction(
            to="0x...",
            value=1000000000000000000,  # 1 ETH
            features={"velocity_24h": 5, "account_age_days": 30}
        )
        
        print(f"Risk: {risk.risk_score} -> {risk.action.name}")
        ```
    """
    
    def __init__(self, config: AMTTPConfig):
        """
        Initialize AMTTP client.
        
        Args:
            config: Client configuration
        """
        self.config = config
        self._session = requests.Session()
        self._session.timeout = config.request_timeout
        
        # Setup Web3
        self.w3 = Web3(Web3.HTTPProvider(config.rpc_url))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        # Setup account if private key provided
        self.account = None
        if config.private_key:
            self.account = Account.from_key(config.private_key)
        
        # Setup contracts
        self._policy_engine = None
        self._policy_manager = None
        
        if config.policy_engine_contract:
            self._policy_engine = self.w3.eth.contract(
                address=Web3.to_checksum_address(config.policy_engine_contract),
                abi=POLICY_ENGINE_ABI
            )
        
        if config.policy_manager_contract:
            self._policy_manager = self.w3.eth.contract(
                address=Web3.to_checksum_address(config.policy_manager_contract),
                abi=POLICY_MANAGER_ABI
            )
        
        logger.info(f"AMTTPClient initialized for chain {config.chain_id}")
    
    @property
    def address(self) -> Optional[str]:
        """Get the client's address."""
        return self.account.address if self.account else None
    
    # ================================================================
    # Risk Scoring
    # ================================================================
    
    def score_transaction(
        self,
        to: str,
        value: int,
        features: Optional[Dict[str, float]] = None,
        from_address: Optional[str] = None,
    ) -> RiskScore:
        """
        Score transaction risk using ML model.
        
        Args:
            to: Recipient address
            value: Transaction value in wei
            features: Additional feature dictionary
            from_address: Sender address (defaults to client address)
            
        Returns:
            RiskScore with ML assessment
        """
        from_addr = from_address or self.address
        if not from_addr:
            raise ConfigurationError("No sender address available")
        
        # Prepare request
        payload = {
            "transaction_id": f"score_{datetime.now().timestamp()}",
            "features": {
                "amount": float(value) / 10**18,  # Convert to ETH
                "to": to,
                "from": from_addr,
                **(features or {}),
            }
        }
        
        try:
            # Call ML API
            response = self._session.post(
                f"{self.config.ml_api_url}/predict",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            
            return RiskScore.from_api_response(data)
            
        except requests.RequestException as e:
            logger.warning(f"ML API error: {e}, using fallback")
            # Try oracle fallback
            return self._score_via_oracle(from_addr, to, value, features)
    
    def _score_via_oracle(
        self,
        from_addr: str,
        to: str,
        value: int,
        features: Optional[Dict[str, float]] = None,
    ) -> RiskScore:
        """Score via oracle service fallback."""
        try:
            response = self._session.post(
                f"{self.config.oracle_url}/risk/dqn-score",
                json={
                    "from": from_addr,
                    "to": to,
                    "amount": float(value) / 10**18,
                    **(features or {}),
                }
            )
            response.raise_for_status()
            return RiskScore.from_api_response(response.json())
            
        except requests.RequestException as e:
            logger.error(f"Oracle fallback failed: {e}")
            # Return high-risk fallback
            return RiskScore(
                risk_score=0.8,
                risk_score_int=800,
                risk_level=RiskLevel.HIGH,
                action=PolicyAction.ESCROW,
                confidence=0.5,
                model_version="fallback-v1.0",
                recommendations=["Service unavailable - using safe fallback"],
            )
    
    def score_batch(
        self,
        transactions: List[Dict[str, Any]],
    ) -> List[RiskScore]:
        """
        Score multiple transactions in batch.
        
        Args:
            transactions: List of transaction dicts with to, value, features
            
        Returns:
            List of RiskScore objects
        """
        payload = {
            "transactions": [
                {
                    "transaction_id": f"batch_{i}",
                    "features": {
                        "amount": float(tx.get("value", 0)) / 10**18,
                        **tx.get("features", {}),
                    }
                }
                for i, tx in enumerate(transactions)
            ]
        }
        
        try:
            response = self._session.post(
                f"{self.config.ml_api_url}/predict/batch",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            
            return [
                RiskScore.from_api_response(pred)
                for pred in data.get("predictions", [])
            ]
            
        except requests.RequestException as e:
            logger.error(f"Batch scoring failed: {e}")
            raise RiskAssessmentError(str(e))
    
    # ================================================================
    # Policy Validation
    # ================================================================
    
    def validate_transaction(
        self,
        to: str,
        value: int,
        risk_score: Optional[RiskScore] = None,
        kyc_hash: str = "0x" + "0" * 64,
    ) -> TransactionResult:
        """
        Validate transaction against on-chain policy.
        
        Args:
            to: Recipient address
            value: Transaction value in wei
            risk_score: Pre-computed risk score (will compute if not provided)
            kyc_hash: User's KYC hash
            
        Returns:
            TransactionResult with validation outcome
        """
        if not self.address:
            raise ConfigurationError("No sender address available")
        
        # Get risk score if not provided
        if risk_score is None:
            risk_score = self.score_transaction(to, value)
        
        # Try policy engine first
        if self._policy_engine:
            try:
                action, reason = self._policy_engine.functions.validateTransaction(
                    Web3.to_checksum_address(self.address),
                    Web3.to_checksum_address(to),
                    value,
                    risk_score.risk_score_int,
                    risk_score.model_version,
                    bytes.fromhex(kyc_hash[2:]) if kyc_hash.startswith("0x") else bytes.fromhex(kyc_hash),
                ).call()
                
                return TransactionResult(
                    success=action != PolicyAction.BLOCK,
                    risk_score=risk_score,
                    action_taken=PolicyAction(action),
                    error=reason if action == PolicyAction.BLOCK else None,
                )
                
            except Exception as e:
                logger.warning(f"Policy engine call failed: {e}")
        
        # Fallback to policy manager
        if self._policy_manager:
            try:
                allowed, risk_level, reason = self._policy_manager.functions.validateTransaction(
                    Web3.to_checksum_address(self.address),
                    Web3.to_checksum_address(to),
                    value,
                    risk_score.risk_score_int,
                ).call()
                
                action = PolicyAction(risk_level) if allowed else PolicyAction.BLOCK
                
                return TransactionResult(
                    success=allowed,
                    risk_score=risk_score,
                    action_taken=action,
                    error=reason if not allowed else None,
                )
                
            except Exception as e:
                logger.warning(f"Policy manager call failed: {e}")
        
        # Local validation fallback
        return self._local_policy_check(risk_score, value)
    
    def _local_policy_check(
        self,
        risk_score: RiskScore,
        value: int,
    ) -> TransactionResult:
        """Local policy validation fallback."""
        # Simple threshold-based check
        if risk_score.risk_score >= 0.9:
            return TransactionResult(
                success=False,
                risk_score=risk_score,
                action_taken=PolicyAction.BLOCK,
                error="Risk score too high",
            )
        elif risk_score.risk_score >= 0.7:
            return TransactionResult(
                success=True,
                risk_score=risk_score,
                action_taken=PolicyAction.ESCROW,
            )
        elif risk_score.risk_score >= 0.4:
            return TransactionResult(
                success=True,
                risk_score=risk_score,
                action_taken=PolicyAction.REVIEW,
            )
        else:
            return TransactionResult(
                success=True,
                risk_score=risk_score,
                action_taken=PolicyAction.APPROVE,
            )
    
    # ================================================================
    # Policy Management
    # ================================================================
    
    def set_policy(self, policy: PolicySettings) -> str:
        """
        Set user policy on-chain.
        
        Args:
            policy: Policy settings to apply
            
        Returns:
            Transaction hash
        """
        if not self.account:
            raise ConfigurationError("Private key required for policy updates")
        
        if not self._policy_manager:
            raise ConfigurationError("Policy manager contract not configured")
        
        # Build transaction
        tx = self._policy_manager.functions.setUserPolicy(
            Web3.to_checksum_address(self.address),
            policy.max_amount,
            policy.risk_threshold,
        ).build_transaction({
            "from": self.address,
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "gas": 100000,
            "gasPrice": self.w3.eth.gas_price,
            "chainId": self.config.chain_id,
        })
        
        # Sign and send
        signed = self.w3.eth.account.sign_transaction(tx, self.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        
        logger.info(f"Policy update tx: {tx_hash.hex()}")
        return tx_hash.hex()
    
    def get_policy(self, address: Optional[str] = None) -> Dict[str, Any]:
        """
        Get user policy from chain.
        
        Args:
            address: Address to query (defaults to client address)
            
        Returns:
            Policy settings dictionary
        """
        addr = address or self.address
        if not addr:
            raise ConfigurationError("No address available")
        
        if self._policy_engine:
            result = self._policy_engine.functions.userPolicies(
                Web3.to_checksum_address(addr)
            ).call()
            return {
                "max_amount": result[0],
                "daily_limit": result[1],
                "risk_threshold": result[2],
                "auto_approve": result[3],
                "enabled": result[4],
            }
        
        return {"error": "Policy contract not configured"}
    
    # ================================================================
    # KYC
    # ================================================================
    
    def get_kyc_status(self, address: Optional[str] = None) -> KYCStatus:
        """
        Get KYC status for address.
        
        Args:
            address: Address to check (defaults to client address)
            
        Returns:
            KYCStatus object
        """
        addr = address or self.address
        if not addr:
            raise ConfigurationError("No address available")
        
        try:
            response = self._session.get(
                f"{self.config.oracle_url}/kyc/status-by-address/{addr}"
            )
            response.raise_for_status()
            return KYCStatus.from_api_response(response.json())
            
        except requests.RequestException:
            return KYCStatus(
                status="pending",
                kyc_hash="0x" + "0" * 64,
            )
    
    # ================================================================
    # Utilities
    # ================================================================
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get ML model information."""
        try:
            response = self._session.get(f"{self.config.ml_api_url}/model/info")
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            return {"error": "Unable to fetch model info"}
    
    def health_check(self) -> Dict[str, Any]:
        """Check service health."""
        results = {
            "web3_connected": self.w3.is_connected(),
            "chain_id": self.config.chain_id,
            "address": self.address,
        }
        
        # Check ML API
        try:
            r = self._session.get(f"{self.config.ml_api_url}/health", timeout=5)
            results["ml_api"] = r.json() if r.ok else {"status": "error"}
        except:
            results["ml_api"] = {"status": "unreachable"}
        
        # Check Oracle
        try:
            r = self._session.get(f"{self.config.oracle_url}/health", timeout=5)
            results["oracle"] = r.json() if r.ok else {"status": "error"}
        except:
            results["oracle"] = {"status": "unreachable"}
        
        return results
