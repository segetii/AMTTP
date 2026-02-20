"""
Example: Basic AMTTP SDK usage.

Run:
    python examples/basic_usage.py
"""

import asyncio
from amttp import AMTTPClient
from amttp.services.risk import RiskAssessmentRequest
from amttp.services.compliance import EvaluateRequest
from amttp.services.sanctions import SanctionsCheckRequest


async def main() -> None:
    # Connect to the AMTTP gateway
    async with AMTTPClient(
        base_url="http://localhost:8888",
        api_key="your-api-key",
        debug=True,
    ) as client:
        # ── 1. Health check ───────────────────────────────────────────────
        print("=== Health Check ===")
        health = await client.health_check()
        print(f"Status: {health}")

        # ── 2. Risk assessment ────────────────────────────────────────────
        print("\n=== Risk Assessment ===")
        risk = await client.risk.assess(
            RiskAssessmentRequest(
                address="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18",
                amount="1.5",
            )
        )
        print(f"Risk Score: {risk.risk_score}")
        print(f"Risk Level: {risk.risk_level}")
        print(f"Factors: {len(risk.factors)}")

        # ── 3. Sanctions screening ────────────────────────────────────────
        print("\n=== Sanctions Screening ===")
        sanctions = await client.sanctions.check(
            SanctionsCheckRequest(
                address="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18"
            )
        )
        print(f"Is Sanctioned: {sanctions.is_sanctioned}")
        print(f"Lists Checked: {sanctions.lists_checked}")

        # ── 4. Full compliance evaluation ─────────────────────────────────
        print("\n=== Compliance Evaluation ===")
        decision = await client.compliance.evaluate(
            EvaluateRequest(
                from_address="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18",
                to_address="0xdAC17F958D2ee523a2206206994597C13D831ec7",
                value_eth=2.5,
            )
        )
        print(f"Decision: {decision.action}")
        print(f"Risk Score: {decision.risk_score}")
        print(f"Reasons: {decision.reasons}")
        print(f"Requires Travel Rule: {decision.requires_travel_rule}")
        print(f"Processing Time: {decision.processing_time_ms}ms")

        # ── 5. Geographic risk ────────────────────────────────────────────
        print("\n=== Geographic Risk ===")
        geo = await client.geographic.get_country_risk("NG")
        print(f"Country: {geo.country_code}")
        print(f"Risk Level: {geo.risk_level}")
        print(f"FATF Status: black={geo.is_fatf_black_list}, grey={geo.is_fatf_grey_list}")

        # ── 6. Dashboard ─────────────────────────────────────────────────
        print("\n=== Dashboard Stats ===")
        stats = await client.dashboard.get_stats()
        print(f"Total Transactions: {stats.total_transactions}")
        print(f"High Risk: {stats.high_risk_count}")
        print(f"Compliance Rate: {stats.compliance_rate}%")


if __name__ == "__main__":
    asyncio.run(main())
