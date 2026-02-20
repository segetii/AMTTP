"""MEV Protection — Flashbots / private mempool support."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

MEVProtectionLevel = Literal["none", "basic", "standard", "maximum"]


class MEVConfig(BaseModel):
    enabled: bool = True
    protection_level: str = "standard"
    flashbots_relay_url: str = "https://relay.flashbots.net"
    max_priority_fee_gwei: float = 3.0
    private_mempool: bool = True


class MEVAnalysis(BaseModel):
    transaction_hash: Optional[str] = None
    is_vulnerable: bool = False
    vulnerability_type: Optional[str] = None
    estimated_mev_value_eth: float = 0
    recommended_protection: str = "none"
    risk_factors: List[str] = []


class MEVProtectedTransaction(BaseModel):
    id: str = ""
    original_hash: str = ""
    protected_hash: Optional[str] = None
    protection_level: str = "standard"
    status: str = "pending"
    submitted_via: str = "flashbots"
    created_at: str = ""


class FlashbotsBundle(BaseModel):
    bundle_id: str = ""
    transactions: List[str] = []
    target_block: int = 0
    status: str = "pending"
    simulation_success: bool = False


# ── service ───────────────────────────────────────────────────────────────────


class MEVProtection(BaseService):
    """MEV protection via Flashbots and private mempools."""

    def __init__(self, http: Any, events: Any) -> None:
        super().__init__(http, events)
        self._config = MEVConfig()

    def set_config(self, config: Dict[str, Any]) -> None:
        """Set MEV protection configuration."""
        self._config = MEVConfig.model_validate(config)

    def get_config(self) -> MEVConfig:
        """Get current MEV protection configuration."""
        return self._config

    async def analyze(self, transaction_hash: str) -> MEVAnalysis:
        """Analyse a transaction for MEV vulnerability."""
        resp = await self._http.post("/mev/analyze", json={"transactionHash": transaction_hash})
        resp.raise_for_status()
        return MEVAnalysis.model_validate(resp.json())

    async def protect(self, transaction_data: Dict[str, Any]) -> MEVProtectedTransaction:
        """Submit a transaction with MEV protection."""
        payload = {
            **transaction_data,
            "protection_level": self._config.protection_level,
            "flashbots_relay_url": self._config.flashbots_relay_url,
        }
        resp = await self._http.post("/mev/protect", json=payload)
        resp.raise_for_status()
        return MEVProtectedTransaction.model_validate(resp.json())

    async def get_status(self, protected_tx_id: str) -> MEVProtectedTransaction:
        """Get status of a protected transaction."""
        resp = await self._http.get(f"/mev/status/{protected_tx_id}")
        resp.raise_for_status()
        return MEVProtectedTransaction.model_validate(resp.json())

    async def create_bundle(self, transactions: List[str], target_block: int) -> FlashbotsBundle:
        """Create a Flashbots bundle."""
        resp = await self._http.post("/mev/bundle", json={
            "transactions": transactions,
            "targetBlock": target_block,
        })
        resp.raise_for_status()
        return FlashbotsBundle.model_validate(resp.json())

    async def simulate_bundle(self, bundle_id: str) -> Dict[str, Any]:
        """Simulate a bundle execution."""
        resp = await self._http.post(f"/mev/bundle/{bundle_id}/simulate")
        resp.raise_for_status()
        return resp.json()

    async def health(self) -> Dict[str, Any]:
        """Check MEV protection service health."""
        resp = await self._http.get("/mev/health")
        resp.raise_for_status()
        return resp.json()
