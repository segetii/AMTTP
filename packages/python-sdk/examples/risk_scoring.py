"""
AMTTP SDK Examples - Risk Scoring

Demonstrates ML-powered fraud detection usage.
"""
from amttp import AMTTPClient, AMTTPConfig, PolicySettings, PolicyAction

# ============================================================
# Example 1: Basic Risk Scoring
# ============================================================

def basic_scoring():
    """Score a single transaction."""
    
    # Configure client (can also use AMTTPConfig.from_env())
    config = AMTTPConfig(
        rpc_url="https://mainnet.infura.io/v3/YOUR_KEY",
        oracle_url="http://localhost:3000",
        ml_api_url="http://localhost:8000",
    )
    
    client = AMTTPClient(config)
    
    # Score a transaction
    risk = client.score_transaction(
        to="0x742d35Cc6634C0532925a3b844Bc9e7595f9EBEB",
        value=1_000_000_000_000_000_000,  # 1 ETH
        features={
            "velocity_24h": 3,
            "account_age_days": 90,
            "country_risk": 0.2,
        }
    )
    
    print(f"Risk Score: {risk.risk_score:.2%}")
    print(f"Risk Level: {risk.risk_level.name}")
    print(f"Action: {risk.action.name}")
    print(f"Confidence: {risk.confidence:.2%}")
    print(f"Model: {risk.model_version}")
    print("\nRecommendations:")
    for rec in risk.recommendations:
        print(f"  - {rec}")


# ============================================================
# Example 2: Batch Scoring
# ============================================================

def batch_scoring():
    """Score multiple transactions at once."""
    
    config = AMTTPConfig.from_env()
    client = AMTTPClient(config)
    
    transactions = [
        {"to": "0x111...", "value": 1e18, "features": {"velocity_24h": 1}},
        {"to": "0x222...", "value": 5e18, "features": {"velocity_24h": 10}},
        {"to": "0x333...", "value": 50e18, "features": {"velocity_24h": 50}},
    ]
    
    risks = client.score_batch(transactions)
    
    for i, risk in enumerate(risks):
        print(f"Transaction {i+1}: {risk.risk_score:.2%} -> {risk.action.name}")


# ============================================================
# Example 3: Policy Validation
# ============================================================

def validate_with_policy():
    """Validate transaction against on-chain policy."""
    
    config = AMTTPConfig(
        rpc_url="https://mainnet.infura.io/v3/YOUR_KEY",
        policy_manager_contract="0x...",  # Your deployed contract
        oracle_url="http://localhost:3000",
        ml_api_url="http://localhost:8000",
        private_key="0x...",  # Your private key
    )
    
    client = AMTTPClient(config)
    
    # Validate transaction
    result = client.validate_transaction(
        to="0x742d35Cc6634C0532925a3b844Bc9e7595f9EBEB",
        value=10_000_000_000_000_000_000,  # 10 ETH
    )
    
    if result.success:
        print(f"✅ Transaction allowed")
        print(f"   Action: {result.action_taken.name}")
        
        if result.action_taken == PolicyAction.ESCROW:
            print(f"   Escrow ID: {result.escrow_id}")
            print("   Funds will be held until release conditions met")
    else:
        print(f"❌ Transaction blocked: {result.error}")


# ============================================================
# Example 4: Set User Policy
# ============================================================

def set_user_policy():
    """Configure custom policy on-chain."""
    
    config = AMTTPConfig(
        rpc_url="https://mainnet.infura.io/v3/YOUR_KEY",
        policy_manager_contract="0x...",
        private_key="0x...",
    )
    
    client = AMTTPClient(config)
    
    # Define policy
    policy = PolicySettings(
        max_amount=100 * 10**18,   # 100 ETH max per transaction
        daily_limit=50 * 10**18,   # 50 ETH daily limit
        weekly_limit=200 * 10**18,
        monthly_limit=500 * 10**18,
        risk_threshold=600,        # Block transactions with risk > 0.60
        auto_approve=True,         # Auto-approve low risk
        cooldown_period=3600,      # 1 hour between large transactions
    )
    
    # Set policy on-chain
    tx_hash = client.set_policy(policy)
    print(f"Policy updated: {tx_hash}")


# ============================================================
# Example 5: Integration with Web Application
# ============================================================

def web_app_integration():
    """Example FastAPI integration."""
    
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    
    app = FastAPI()
    
    # Initialize client once
    config = AMTTPConfig.from_env()
    amttp = AMTTPClient(config)
    
    class TransactionRequest(BaseModel):
        to: str
        value: int  # in wei
        velocity_24h: int = 1
        account_age_days: int = 30
    
    @app.post("/api/check-transaction")
    async def check_transaction(req: TransactionRequest):
        # Score the transaction
        risk = amttp.score_transaction(
            to=req.to,
            value=req.value,
            features={
                "velocity_24h": req.velocity_24h,
                "account_age_days": req.account_age_days,
            }
        )
        
        # Return assessment
        return {
            "allowed": risk.action != PolicyAction.BLOCK,
            "risk_score": risk.risk_score,
            "action": risk.action.name,
            "recommendations": risk.recommendations,
        }


# ============================================================
# Example 6: Health Check
# ============================================================

def health_check():
    """Check all services status."""
    
    config = AMTTPConfig.from_env()
    client = AMTTPClient(config)
    
    status = client.health_check()
    
    print("Service Status:")
    print(f"  Web3 Connected: {status['web3_connected']}")
    print(f"  Chain ID: {status['chain_id']}")
    print(f"  Address: {status['address']}")
    print(f"  ML API: {status['ml_api']['status']}")
    print(f"  Oracle: {status['oracle']['status']}")


if __name__ == "__main__":
    print("=" * 60)
    print("AMTTP SDK Examples")
    print("=" * 60)
    
    # Run basic scoring example
    print("\n[Example 1: Basic Scoring]")
    basic_scoring()
