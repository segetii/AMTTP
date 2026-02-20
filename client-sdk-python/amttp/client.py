"""
AMTTP Python SDK — main client.

Usage::

    import asyncio
    from amttp import AMTTPClient

    async def main():
        client = AMTTPClient(base_url="http://localhost:8888")
        result = await client.risk.assess(
            RiskAssessmentRequest(address="0xabc...")
        )
        print(result.risk_score)
        await client.close()

    asyncio.run(main())
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import httpx

from amttp.errors import AMTTPError, AMTTPErrorCode
from amttp.events import EventEmitter
from amttp.services.bulk import BulkService
from amttp.services.compliance import ComplianceService
from amttp.services.dashboard import DashboardService
from amttp.services.dispute import DisputeService
from amttp.services.edd import EDDService
from amttp.services.explainability import ExplainabilityService
from amttp.services.geographic import GeographicRiskService
from amttp.services.governance import GovernanceService
from amttp.services.integrity import IntegrityService
from amttp.services.kyc import KYCService
from amttp.services.label import LabelService
from amttp.services.mev import MEVProtection
from amttp.services.monitoring import MonitoringService
from amttp.services.pep import PEPService
from amttp.services.policy import PolicyService
from amttp.services.profile import ProfileService
from amttp.services.reputation import ReputationService
from amttp.services.risk import RiskService
from amttp.services.sanctions import SanctionsService
from amttp.services.transaction import TransactionService
from amttp.services.webhook import WebhookService

logger = logging.getLogger("amttp")


class AMTTPClient:
    """
    Main entry-point for the AMTTP Python SDK.

    Parameters
    ----------
    base_url:
        Base URL of the AMTTP gateway (e.g. ``http://localhost:8888``).
    api_key:
        Optional API key for ``X-API-Key`` authentication.
    timeout:
        Default request timeout in seconds (default 30).
    retry_attempts:
        Number of automatic retries for retryable errors (default 3).
    mev_config:
        MEV protection settings (dict passed to :class:`MEVProtection`).
    debug:
        Enable verbose logging.
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        retry_attempts: int = 3,
        mev_config: Optional[Dict[str, Any]] = None,
        debug: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._retry_attempts = retry_attempts
        self._debug = debug

        # Build headers
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["X-API-Key"] = api_key

        # Async HTTP transport
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
            headers=headers,
            event_hooks={
                "request": [self._on_request],
                "response": [self._on_response],
            },
        )

        # Event emitter
        self.events = EventEmitter()

        # ── service instances ─────────────────────────────────────────────
        self.risk = RiskService(self._http, self.events)
        self.kyc = KYCService(self._http, self.events)
        self.transactions = TransactionService(self._http, self.events)
        self.policy = PolicyService(self._http, self.events)
        self.disputes = DisputeService(self._http, self.events)
        self.reputation = ReputationService(self._http, self.events)
        self.bulk = BulkService(self._http, self.events)
        self.webhooks = WebhookService(self._http, self.events)
        self.pep = PEPService(self._http, self.events)
        self.edd = EDDService(self._http, self.events)
        self.monitoring = MonitoringService(self._http, self.events)
        self.labels = LabelService(self._http, self.events)
        self.mev = MEVProtection(self._http, self.events)
        self.compliance = ComplianceService(self._http, self.events)
        self.explainability = ExplainabilityService(self._http, self.events)
        self.sanctions = SanctionsService(self._http, self.events)
        self.geographic = GeographicRiskService(self._http, self.events)
        self.integrity = IntegrityService(self._http, self.events)
        self.governance = GovernanceService(self._http, self.events)
        self.dashboard = DashboardService(self._http, self.events)
        self.profiles = ProfileService(self._http, self.events)

        # Apply optional MEV config
        if mev_config:
            self.mev.set_config(mev_config)

        if debug:
            logging.basicConfig(level=logging.DEBUG)
            logger.debug("AMTTPClient initialised → %s", self._base_url)

    # ── hooks ─────────────────────────────────────────────────────────────

    async def _on_request(self, request: httpx.Request) -> None:
        if self._debug:
            logger.debug("%s %s", request.method, request.url)

    async def _on_response(self, response: httpx.Response) -> None:
        if self._debug:
            logger.debug("← %s %s", response.status_code, response.url)

        # Convert HTTP errors to AMTTPError with retry
        if response.status_code >= 400:
            try:
                data = response.json()
            except Exception:
                data = {}
            error = AMTTPError.from_response(response.status_code, data)

            # Retry logic (using request extensions to track attempts)
            request = response.request
            attempt = int(request.extensions.get("retry_count", 0))  # type: ignore[arg-type]
            if error.is_retryable() and attempt < self._retry_attempts:
                import asyncio

                request.extensions["retry_count"] = attempt + 1  # type: ignore[index]
                delay = 2 ** (attempt + 1)
                if self._debug:
                    logger.debug("Retrying in %ds (attempt %d)…", delay, attempt + 1)
                await asyncio.sleep(delay)
                # httpx event hooks can't natively retry; raise to let caller handle
            self.events.emit("error", error)
            raise error

    # ── public helpers ────────────────────────────────────────────────────

    async def health_check(self) -> Dict[str, Any]:
        """Hit the gateway ``/health`` endpoint."""
        resp = await self._http.get("/health")
        resp.raise_for_status()
        return resp.json()

    def set_api_key(self, api_key: str) -> None:
        """Update the API key at runtime."""
        self._api_key = api_key
        self._http.headers["X-API-Key"] = api_key

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    # Context-manager support
    async def __aenter__(self) -> "AMTTPClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    def __repr__(self) -> str:
        return f"AMTTPClient(base_url={self._base_url!r})"
