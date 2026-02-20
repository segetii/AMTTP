# AMTTP Python SDK

> Python client library for the **Advanced Money Transfer Transaction Protocol** (AMTTP) compliance platform.

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Installation

```bash
pip install amttp-sdk
```

Or install from source:

```bash
cd client-sdk-python
pip install -e ".[dev]"
```

## Quick Start

```python
import asyncio
from amttp import AMTTPClient
from amttp.services.risk import RiskAssessmentRequest
from amttp.services.compliance import EvaluateRequest

async def main():
    async with AMTTPClient("http://localhost:8888", api_key="your-key") as client:
        # Health check
        health = await client.health_check()
        print(f"API Status: {health['status']}")

        # Risk assessment
        risk = await client.risk.assess(
            RiskAssessmentRequest(address="0xabc123...")
        )
        print(f"Risk: {risk.risk_score} ({risk.risk_level})")

        # Full compliance evaluation
        decision = await client.compliance.evaluate(
            EvaluateRequest(
                from_address="0xabc123...",
                to_address="0xdef456...",
                value_eth=1.5,
            )
        )
        print(f"Decision: {decision.action} (score: {decision.risk_score})")

        # Sanctions check
        sanctions = await client.sanctions.check_crypto_address("0xabc123...")
        print(f"Sanctioned: {sanctions.is_sanctioned}")

asyncio.run(main())
```

## Features

The SDK mirrors the [TypeScript SDK](../client-sdk/) and provides access to all AMTTP services:

| Service | Description |
|---------|-------------|
| `client.risk` | ML-based risk scoring (Stacked Ensemble) |
| `client.kyc` | KYC document submission and verification |
| `client.transactions` | Transaction validation and submission |
| `client.compliance` | Unified compliance evaluation (Orchestrator) |
| `client.sanctions` | OFAC/EU/UN sanctions screening |
| `client.geographic` | Country & IP geographic risk |
| `client.pep` | Politically Exposed Persons screening |
| `client.edd` | Enhanced Due Diligence case management |
| `client.monitoring` | Real-time transaction monitoring |
| `client.labels` | Address labelling and classification |
| `client.policy` | Compliance policy management |
| `client.disputes` | Kleros-compatible dispute resolution |
| `client.reputation` | Multi-tier reputation scoring |
| `client.governance` | WYAS multi-sig governance actions |
| `client.explainability` | ML risk-score explanations |
| `client.integrity` | UI snapshot integrity verification |
| `client.dashboard` | Analytics and visualisation |
| `client.bulk` | Batch scoring operations |
| `client.webhooks` | Webhook management |
| `client.mev` | MEV protection (Flashbots) |
| `client.profiles` | Entity profile management |

## Event System

```python
client = AMTTPClient("http://localhost:8888")

# Listen for risk events
client.events.on("risk:assessed", lambda data: print(f"Risk assessed: {data}"))
client.events.on("sanctions:match", lambda addr, list_name: print(f"MATCH: {addr} on {list_name}"))
client.events.on("error", lambda err: print(f"Error: {err}"))
```

## Error Handling

```python
from amttp import AMTTPClient, AMTTPError, AMTTPErrorCode

async def safe_assess():
    async with AMTTPClient("http://localhost:8888") as client:
        try:
            result = await client.risk.assess(
                RiskAssessmentRequest(address="0xabc...")
            )
        except AMTTPError as e:
            if e.code == AMTTPErrorCode.SANCTIONED_ADDRESS:
                print("Address is sanctioned!")
            elif e.code == AMTTPErrorCode.RATE_LIMITED:
                print("Rate limited, try again later")
            elif e.is_retryable():
                print(f"Retryable error: {e}")
            else:
                raise
```

## Configuration

```python
client = AMTTPClient(
    base_url="http://localhost:8888",
    api_key="your-api-key",          # X-API-Key header
    timeout=30.0,                     # Request timeout (seconds)
    retry_attempts=3,                 # Auto-retry for retryable errors
    debug=True,                       # Verbose logging
    mev_config={                      # MEV protection settings
        "enabled": True,
        "protection_level": "standard",
    },
)
```

## Type Safety

All request/response models use [Pydantic v2](https://docs.pydantic.dev/) for runtime validation and IDE autocompletion. The package ships with `py.typed` for full `mypy` support.

## Architecture

```
amttp/
├── __init__.py          # Package entry point
├── client.py            # AMTTPClient class
├── errors.py            # AMTTPError + error codes
├── events.py            # EventEmitter
├── py.typed             # PEP 561 marker
└── services/
    ├── __init__.py      # Service barrel exports
    ├── base.py          # BaseService class
    ├── risk.py          # Risk scoring
    ├── kyc.py           # KYC verification
    ├── transaction.py   # Transaction management
    ├── compliance.py    # Compliance orchestration
    ├── sanctions.py     # Sanctions screening
    ├── geographic.py    # Geographic risk
    ├── pep.py           # PEP screening
    ├── edd.py           # Enhanced Due Diligence
    ├── monitoring.py    # Real-time monitoring
    ├── label.py         # Address labels
    ├── policy.py        # Policy engine
    ├── dispute.py       # Dispute resolution
    ├── reputation.py    # Reputation system
    ├── governance.py    # WYAS governance
    ├── explainability.py # ML explanations
    ├── integrity.py     # UI integrity
    ├── dashboard.py     # Dashboard analytics
    ├── bulk.py          # Batch operations
    ├── webhook.py       # Webhooks
    ├── mev.py           # MEV protection
    └── profile.py       # Entity profiles
```

## Development

```bash
pip install -e ".[dev]"
pytest
mypy amttp/
ruff check amttp/
```

## License

MIT — see [LICENSE](LICENSE) for details.
