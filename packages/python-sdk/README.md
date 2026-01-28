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

The AMTTP ML pipeline uses a **Stacked Ensemble** architecture with knowledge distillation:

| Model | Component | Role |
|-------|-----------|------|
| GraphSAGE | Graph Neural Network | Structural fraud patterns via neighbor aggregation |
| LightGBM | Gradient Boosting | Fast feature interactions with leaf-wise growth |
| XGBoost | Gradient Boosting | Non-linear patterns with strong regularization |
| Linear Meta-Learner | Ensemble | Optimal weighting: `y = w₁·GraphSAGE + w₂·LGBM + w₃·XGB + b` |

### Validated Metrics (Time-Based Test Split, Days 27-30)

| Metric | Score | Notes |
|--------|-------|-------|
| **ROC-AUC** | ~0.94 | Overall discriminative ability |
| **PR-AUC** | ~0.87 | Primary metric for imbalanced fraud detection |
| **F1 @ 0.5** | ~0.87 | Balanced precision/recall at default threshold |

## Explainability

The SDK includes a powerful explainability module for human-readable risk explanations:

```python
from amttp import ExplainabilityService, format_explanation

# Create explainability service
explainer = ExplainabilityService("http://localhost:8009")

# Get explanation for a risk score
explanation = explainer.explain(
    risk_score=0.73,
    features={
        "amount_eth": 50,
        "tx_count_24h": 15,
        "hops_to_sanctioned": 2
    }
)

print(explanation.summary)
# "High-risk transaction due to large amount and proximity to flagged addresses"

print(explanation.top_reasons)
# ["Large transaction (50 ETH)", "2 hops from sanctioned address", "15 txs in 24h"]

print(explanation.action)
# "ESCROW"

# Explain a specific transaction
tx_explanation = explainer.explain_transaction(
    transaction_hash="0xabc123...",
    risk_score=0.85,
    sender="0x1234...",
    receiver="0xabcd...",
    amount=100,
    features={"tx_count_24h": 25}
)

# Format for display
print(format_explanation(explanation))
```

### Detected Typologies

| Typology | Description |
|----------|-------------|
| `structuring` | Breaking large transactions into smaller ones |
| `layering` | Complex chains to obscure fund origins |
| `smurfing` | Using multiple accounts to move funds |
| `fan_out` / `fan_in` | Distribution or consolidation patterns |
| `mixer_interaction` | Funds through mixing services |
| `sanctions_proximity` | Near sanctioned entities |
| `dormant_activation` | Inactive account suddenly active |

### Training Pipeline

1. **Stage 1**: Base XGBoost trained on Kaggle ETH Fraud Dataset
2. **Stage 2**: Fresh ETH data enriched with XGB scores, AML rules, graph properties
3. **Stage 3**: VAE latent features + GraphSAGE embeddings extracted
4. **Stage 4**: Stacked ensemble (GraphSAGE + LGBM + XGB v2) with linear meta-learner

The final model has all knowledge "baked in": fraud patterns, 6 AML rules, graph topology, and optimal ensemble weighting.

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
