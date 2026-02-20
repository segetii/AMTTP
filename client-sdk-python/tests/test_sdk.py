"""
AMTTP Python SDK — test suite.

Uses pytest-httpx to mock the httpx client.
"""

import pytest
import pytest_asyncio
import httpx

from amttp import AMTTPClient, AMTTPError, AMTTPErrorCode
from amttp.events import EventEmitter
from amttp.services.risk import RiskAssessmentRequest


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest_asyncio.fixture
async def client():
    """Create a client that won't actually connect anywhere."""
    c = AMTTPClient("http://test-amttp:8888", api_key="test-key")
    yield c
    await c.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests — errors
# ═══════════════════════════════════════════════════════════════════════════════

class TestAMTTPError:
    def test_from_response_400(self):
        err = AMTTPError.from_response(400, {"message": "Bad request"})
        assert err.code == AMTTPErrorCode.INVALID_PARAMETERS
        assert err.status_code == 400
        assert not err.is_retryable()

    def test_from_response_401(self):
        err = AMTTPError.from_response(401)
        assert err.code == AMTTPErrorCode.UNAUTHORIZED

    def test_from_response_403_sanctions(self):
        err = AMTTPError.from_response(403, {"message": "Blocked", "code": "SANCTIONED"})
        assert err.code == AMTTPErrorCode.SANCTIONED_ADDRESS

    def test_from_response_429_retryable(self):
        err = AMTTPError.from_response(429)
        assert err.code == AMTTPErrorCode.RATE_LIMITED
        assert err.is_retryable()

    def test_from_response_500_retryable(self):
        err = AMTTPError.from_response(500)
        assert err.code == AMTTPErrorCode.SERVER_ERROR
        assert err.is_retryable()

    def test_repr(self):
        err = AMTTPError("test", AMTTPErrorCode.TIMEOUT, 408)
        assert "TIMEOUT" in repr(err)


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests — event emitter
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventEmitter:
    def test_on_emit(self):
        emitter = EventEmitter()
        received = []
        emitter.on("test", lambda data: received.append(data))
        emitter.emit("test", {"key": "value"})
        assert len(received) == 1
        assert received[0]["key"] == "value"

    def test_off(self):
        emitter = EventEmitter()
        received = []
        handler = lambda data: received.append(data)
        emitter.on("test", handler)
        emitter.off("test", handler)
        emitter.emit("test", "should not appear")
        assert len(received) == 0

    def test_once(self):
        emitter = EventEmitter()
        received = []
        emitter.once("test", lambda: received.append(1))
        emitter.emit("test")
        emitter.emit("test")
        assert len(received) == 1

    def test_remove_all(self):
        emitter = EventEmitter()
        received = []
        emitter.on("a", lambda: received.append("a"))
        emitter.on("b", lambda: received.append("b"))
        emitter.remove_all_listeners()
        emitter.emit("a")
        emitter.emit("b")
        assert len(received) == 0

    def test_event_names(self):
        emitter = EventEmitter()
        emitter.on("alpha", lambda: None)
        emitter.on("beta", lambda: None)
        assert set(emitter.event_names) == {"alpha", "beta"}


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests — client initialisation
# ═══════════════════════════════════════════════════════════════════════════════

class TestClientInit:
    @pytest.mark.asyncio
    async def test_client_has_all_services(self, client: AMTTPClient):
        service_names = [
            "risk", "kyc", "transactions", "policy", "disputes",
            "reputation", "bulk", "webhooks", "pep", "edd",
            "monitoring", "labels", "mev", "compliance",
            "explainability", "sanctions", "geographic",
            "integrity", "governance", "dashboard", "profiles",
        ]
        for name in service_names:
            assert hasattr(client, name), f"Missing service: {name}"

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with AMTTPClient("http://test:8888") as client:
            assert repr(client) == "AMTTPClient(base_url='http://test:8888')"

    @pytest.mark.asyncio
    async def test_set_api_key(self, client: AMTTPClient):
        client.set_api_key("new-key")
        assert client._http.headers["X-API-Key"] == "new-key"


# ═══════════════════════════════════════════════════════════════════════════════
# Integration-style tests (with mocked HTTP)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRiskServiceMocked:
    @pytest.mark.asyncio
    async def test_assess(self, client: AMTTPClient, httpx_mock):
        httpx_mock.add_response(
            url="http://test-amttp:8888/risk/assess",
            json={
                "address": "0xabc",
                "riskScore": 42.5,
                "riskLevel": "medium",
                "factors": [],
                "labels": [],
                "timestamp": "2025-01-01T00:00:00Z",
                "expiresAt": "2025-01-02T00:00:00Z",
                "cached": False,
            },
        )
        result = await client.risk.assess(RiskAssessmentRequest(address="0xabc"))
        assert result.address == "0xabc"

    @pytest.mark.asyncio
    async def test_get_score_not_found(self, client: AMTTPClient, httpx_mock):
        httpx_mock.add_response(
            url="http://test-amttp:8888/risk/score/0xnotfound",
            status_code=404,
        )
        result = await client.risk.get_score("0xnotfound")
        assert result is None


class TestSanctionsServiceMocked:
    @pytest.mark.asyncio
    async def test_check(self, client: AMTTPClient, httpx_mock):
        httpx_mock.add_response(
            url="http://test-amttp:8888/sanctions/check",
            json={
                "query": {"address": "0xabc"},
                "is_sanctioned": False,
                "matches": [],
                "check_timestamp": "2025-01-01T00:00:00Z",
                "lists_checked": ["OFAC_SDN", "EU_CONSOLIDATED"],
                "processing_time_ms": 12.5,
            },
        )
        from amttp.services.sanctions import SanctionsCheckRequest
        result = await client.sanctions.check(SanctionsCheckRequest(address="0xabc"))
        assert not result.is_sanctioned
        assert "OFAC_SDN" in result.lists_checked


class TestComplianceServiceMocked:
    @pytest.mark.asyncio
    async def test_evaluate(self, client: AMTTPClient, httpx_mock):
        httpx_mock.add_response(
            url="http://test-amttp:8888/evaluate",
            json={
                "decision_id": "dec-001",
                "timestamp": "2025-01-01T00:00:00Z",
                "from_address": "0xabc",
                "to_address": "0xdef",
                "value_eth": 1.0,
                "checks": [],
                "action": "ALLOW",
                "risk_score": 15.0,
                "reasons": [],
                "requires_travel_rule": False,
                "requires_sar": False,
                "requires_escrow": False,
                "escrow_duration_hours": 0,
                "processing_time_ms": 45.2,
            },
        )
        from amttp.services.compliance import EvaluateRequest
        result = await client.compliance.evaluate(
            EvaluateRequest(from_address="0xabc", to_address="0xdef", value_eth=1.0)
        )
        assert result.action == "ALLOW"
        assert result.risk_score == 15.0


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health(self, client: AMTTPClient, httpx_mock):
        httpx_mock.add_response(
            url="http://test-amttp:8888/health",
            json={"status": "healthy", "version": "4.0.0"},
        )
        result = await client.health_check()
        assert result["status"] == "healthy"
