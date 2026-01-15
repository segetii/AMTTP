# AMTTP Python SDK

ML-powered fraud detection SDK for blockchain transactions.

## Installation

```bash
pip install amttp
```

## Quick Start

```python
from amttp import AMTTPClient, AMTTPConfig

# Configure client
config = AMTTPConfig(
    rpc_url="https://mainnet.infura.io/v3/YOUR_KEY",
    oracle_url="https://oracle.amttp.io",
    ml_api_url="https://ml.amttp.io",
    private_key="0x...",  # Optional: for sending transactions
)

client = AMTTPClient(config)

# Score transaction risk
risk = client.score_transaction(
    to="0x742d35Cc6634C0532925a3b844Bc9e7595f9EBEB",
    value=1_000_000_000_000_000_000,  # 1 ETH in wei
    features={
        "velocity_24h": 5,
        "account_age_days": 30,
    }
)

print(f"Risk Score: {risk.risk_score:.2%}")
print(f"Action: {risk.action.name}")
print(f"Recommendations: {risk.recommendations}")
```

## Features

### Risk Scoring

```python
# Single transaction
risk = client.score_transaction(to="0x...", value=1e18)

# Batch scoring
risks = client.score_batch([
    {"to": "0x...", "value": 1e18, "features": {...}},
    {"to": "0x...", "value": 2e18, "features": {...}},
])
```

### Policy Validation

```python
# Validate against on-chain policy
result = client.validate_transaction(
    to="0x...",
    value=1e18,
    kyc_hash="0x..."
)

if result.success:
    print(f"Transaction allowed: {result.action_taken.name}")
else:
    print(f"Transaction blocked: {result.error}")
```

### Policy Management

```python
from amttp import PolicySettings

# Set your policy
policy = PolicySettings(
    max_amount=100 * 10**18,  # 100 ETH
    daily_limit=50 * 10**18,
    risk_threshold=700,  # 0.70
    auto_approve=True,
)
tx_hash = client.set_policy(policy)
```

## Risk Levels

| Level | Score Range | Default Action |
|-------|-------------|----------------|
| MINIMAL | 0.00 - 0.25 | APPROVE |
| LOW | 0.25 - 0.40 | APPROVE |
| MEDIUM | 0.40 - 0.70 | REVIEW |
| HIGH | 0.70 - 1.00 | ESCROW/BLOCK |

## Model Performance

- **Test AP**: 0.685 (XGBoost)
- **Test AUC**: 0.983
- **Test F1**: 0.661
- **Training Data**: 2.6M transactions, 113:1 imbalance ratio

## Environment Variables

```bash
RPC_URL=https://mainnet.infura.io/v3/YOUR_KEY
CHAIN_ID=1
ORACLE_URL=https://oracle.amttp.io
ML_API_URL=https://ml.amttp.io
PRIVATE_KEY=0x...
POLICY_ENGINE_CONTRACT=0x...
POLICY_MANAGER_CONTRACT=0x...
```

## License

MIT
