"""
AMTTP Python SDK
================

Full-featured Python client for the **A**dvanced **M**oney **T**ransfer
**T**ransaction **P**rotocol compliance platform.

Quick start::

    import asyncio
    from amttp import AMTTPClient
    from amttp.services.risk import RiskAssessmentRequest

    async def main():
        async with AMTTPClient("http://localhost:8888") as client:
            # Health check
            print(await client.health_check())

            # Risk assessment
            result = await client.risk.assess(
                RiskAssessmentRequest(address="0xabc...")
            )
            print(f"Risk score: {result.risk_score} ({result.risk_level})")

    asyncio.run(main())
"""

from amttp.client import AMTTPClient
from amttp.errors import AMTTPError, AMTTPErrorCode
from amttp.events import EventEmitter

__version__ = "1.0.0"

__all__ = [
    "AMTTPClient",
    "AMTTPError",
    "AMTTPErrorCode",
    "EventEmitter",
    "__version__",
]
