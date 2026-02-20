"""
Example: Event-driven monitoring with the AMTTP SDK.

Run:
    python examples/event_monitoring.py
"""

import asyncio
from amttp import AMTTPClient, AMTTPError
from amttp.services.risk import RiskAssessmentRequest


ADDRESSES_TO_MONITOR = [
    "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18",
    "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
]


async def main() -> None:
    async with AMTTPClient("http://localhost:8888", debug=True) as client:
        # Register event listeners
        client.events.on(
            "risk:assessed",
            lambda data: print(f"  [EVENT] Risk assessed: {data['address']} → {data['risk_level']}"),
        )
        client.events.on(
            "sanctions:match",
            lambda addr, list_name: print(f"  [ALERT] Sanctions match: {addr} on {list_name}"),
        )
        client.events.on(
            "error",
            lambda err: print(f"  [ERROR] {err}"),
        )

        print("Monitoring addresses...")
        for addr in ADDRESSES_TO_MONITOR:
            try:
                # Risk check
                risk = await client.risk.assess(RiskAssessmentRequest(address=addr))
                print(f"{addr[:10]}… → score={risk.risk_score:.1f} level={risk.risk_level}")

                # Sanctions check
                sanctions = await client.sanctions.check_crypto_address(addr)
                status = "SANCTIONED" if sanctions.is_sanctioned else "CLEAN"
                print(f"  Sanctions: {status}")

            except AMTTPError as e:
                print(f"  Error for {addr[:10]}…: {e.code.value} — {e}")

        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
