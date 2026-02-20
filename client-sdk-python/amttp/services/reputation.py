"""Reputation Service — wraps ``/reputation`` endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

ReputationTier = Literal["bronze", "silver", "gold", "platinum", "diamond"]


class Badge(BaseModel):
    id: str = ""
    name: str = ""
    description: str = ""
    earned_at: str = ""


class ReputationEvent(BaseModel):
    type: str = ""
    description: str = ""
    impact: float = 0
    timestamp: str = ""


class ReputationProfile(BaseModel):
    address: str = ""
    tier: str = "bronze"
    score: float = 0
    total_transactions: int = 0
    successful_transactions: int = 0
    badges: List[Badge] = []
    events: List[ReputationEvent] = []
    created_at: str = ""
    updated_at: str = ""


class TierRequirements(BaseModel):
    tier: str = ""
    min_score: float = 0
    min_transactions: int = 0
    features: List[str] = []


class LeaderboardEntry(BaseModel):
    rank: int = 0
    address: str = ""
    score: float = 0
    tier: str = ""
    total_transactions: int = 0


# ── service ───────────────────────────────────────────────────────────────────


class ReputationService(BaseService):
    """Reputation management."""

    async def get_profile(self, address: str) -> ReputationProfile:
        """Get reputation profile."""
        resp = await self._http.get(f"/reputation/{address}")
        resp.raise_for_status()
        return ReputationProfile.model_validate(resp.json())

    async def get_score(self, address: str) -> float:
        """Get reputation score."""
        profile = await self.get_profile(address)
        return profile.score

    async def get_tier(self, address: str) -> str:
        """Get reputation tier."""
        profile = await self.get_profile(address)
        return profile.tier

    async def calculate_impact(
        self, address: str, *, transaction_type: str, amount: str
    ) -> Dict[str, Any]:
        """Calculate reputation impact of a transaction."""
        resp = await self._http.post("/reputation/impact", json={
            "address": address,
            "transactionType": transaction_type,
            "amount": amount,
        })
        resp.raise_for_status()
        data = resp.json()
        self._events.emit("reputation:impactCalculated", data)
        return data

    async def get_tier_requirements(self) -> List[TierRequirements]:
        """Get tier requirements."""
        resp = await self._http.get("/reputation/tiers")
        resp.raise_for_status()
        return [TierRequirements.model_validate(t) for t in resp.json().get("tiers", [])]

    async def get_leaderboard(self, *, limit: int = 10) -> List[LeaderboardEntry]:
        """Get reputation leaderboard."""
        resp = await self._http.get("/reputation/leaderboard", params={"limit": limit})
        resp.raise_for_status()
        return [LeaderboardEntry.model_validate(e) for e in resp.json().get("entries", [])]

    async def get_badges(self, address: str) -> List[Badge]:
        """Get badges earned by address."""
        profile = await self.get_profile(address)
        return profile.badges
