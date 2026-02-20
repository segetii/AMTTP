"""Webhook Service — wraps ``/webhook`` endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService


class Webhook(BaseModel):
    id: str = ""
    url: str = ""
    events: List[str] = []
    secret: str = ""
    active: bool = True
    created_at: str = ""
    updated_at: str = ""


class WebhookDelivery(BaseModel):
    id: str = ""
    webhook_id: str = ""
    event: str = ""
    status: str = ""
    response_code: Optional[int] = None
    delivered_at: str = ""
    payload: Optional[Dict[str, Any]] = None


class WebhookCreateRequest(BaseModel):
    url: str
    events: List[str]
    secret: Optional[str] = None


WebhookEventType = str  # e.g. "risk:assessed", "transaction:completed"


# ── service ───────────────────────────────────────────────────────────────────


class WebhookService(BaseService):
    """Webhook management."""

    async def create(self, request: WebhookCreateRequest) -> Webhook:
        """Create a new webhook."""
        resp = await self._http.post("/webhook", json=request.model_dump(exclude_none=True))
        resp.raise_for_status()
        return Webhook.model_validate(resp.json())

    async def list_webhooks(self) -> List[Webhook]:
        """List all webhooks."""
        resp = await self._http.get("/webhook")
        resp.raise_for_status()
        return [Webhook.model_validate(w) for w in resp.json().get("webhooks", [])]

    async def get(self, webhook_id: str) -> Webhook:
        """Get webhook details."""
        resp = await self._http.get(f"/webhook/{webhook_id}")
        resp.raise_for_status()
        return Webhook.model_validate(resp.json())

    async def update(self, webhook_id: str, updates: Dict[str, Any]) -> Webhook:
        """Update a webhook."""
        resp = await self._http.put(f"/webhook/{webhook_id}", json=updates)
        resp.raise_for_status()
        return Webhook.model_validate(resp.json())

    async def delete(self, webhook_id: str) -> None:
        """Delete a webhook."""
        resp = await self._http.delete(f"/webhook/{webhook_id}")
        resp.raise_for_status()

    async def get_deliveries(
        self, webhook_id: str, *, limit: Optional[int] = None
    ) -> List[WebhookDelivery]:
        """Get webhook delivery history."""
        params = {"limit": limit} if limit else {}
        resp = await self._http.get(f"/webhook/{webhook_id}/deliveries", params=params)
        resp.raise_for_status()
        return [WebhookDelivery.model_validate(d) for d in resp.json().get("deliveries", [])]

    async def test(self, webhook_id: str) -> Dict[str, Any]:
        """Send a test event to a webhook."""
        resp = await self._http.post(f"/webhook/{webhook_id}/test")
        resp.raise_for_status()
        return resp.json()

    async def get_event_types(self) -> List[str]:
        """Get available webhook event types."""
        resp = await self._http.get("/webhook/event-types")
        resp.raise_for_status()
        return resp.json().get("event_types", [])
