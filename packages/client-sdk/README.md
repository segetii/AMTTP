# @amttp/client-sdk

TypeScript SDK for integrating with the AMTTP (AI-powered Multi-signature Transaction Trust Protocol) fraud detection system.

## Features

- 🤖 **ML-Powered Risk Scoring**: Stacked Ensemble (ROC-AUC=0.94, PR-AUC=0.87, F1=0.87)
- 🔒 **Smart Contract Integration**: Policy engine & manager contracts
- 🆔 **KYC Integration**: Automatic compliance checking
- 📊 **Real-time Inference**: Sub-100ms transaction scoring
- 🛡️ **Policy Engine**: User-defined transaction limits and risk thresholds
- ⚡ **Multi-chain Ready**: Designed for Ethereum, Polygon, Arbitrum

## Installation

```bash
npm install @amttp/client-sdk
# or
yarn add @amttp/client-sdk
```

## Quick Start

### Basic Risk Scoring

```typescript
import { MLService, PolicyAction, utils } from '@amttp/client-sdk';

// Create ML service
const mlService = new MLService('http://localhost:8000');

// Score a transaction
const risk = await mlService.scoreTransaction('tx_001', {
  amount: 1.5,           // ETH
  velocity_24h: 3,
  account_age_days: 90,
});

console.log(`Risk: ${utils.formatRiskScore(risk.riskScore)}`);  // "97.2%"
console.log(`Action: ${PolicyAction[risk.action]}`);            // "ESCROW"
```

### Full Client Integration

```typescript
import { AMTTPClient } from '@amttp/client-sdk';

// Initialize client
const client = new AMTTPClient({
  rpcUrl: 'https://eth-mainnet.alchemyapi.io/v2/YOUR_KEY',
  contractAddress: '0x...', // Your deployed AMTTP contract
  oracleUrl: 'https://oracle.amttp.io',
  mlApiUrl: 'https://ml.amttp.io',  // ML inference API
  privateKey: 'YOUR_PRIVATE_KEY'
});

// Submit a transaction with fraud protection
const result = await client.submitTransaction({
  to: '0x742d35cc6638C0532925a3b8c17fb67C5b13f01e',
  value: ethers.parseEther('1.0'),
  metadata: {
    purpose: 'payment',
    counterparty: 'merchant_xyz'
  }
});

if (result.success) {
  console.log('Transaction submitted:', result.transactionHash);
  console.log('Risk score:', result.riskScore);
} else {
  console.error('Transaction failed:', result.error);
}
```

## Advanced Usage

### Risk Scoring

```typescript
// Get risk assessment for a transaction
const riskScore = await client.scoreTransactionRisk({
  from: '0x...',
  to: '0x...',
  amount: 1000,
  metadata: { category: 'defi' }
});

console.log(`Risk: ${riskScore.riskCategory} (${riskScore.riskScore})`);
console.log('Recommendations:', riskScore.recommendations);
```

### Atomic Swaps

```typescript
// Create secure atomic swap for high-risk transactions
const preimage = ethers.randomBytes(32);
const hashlock = ethers.keccak256(preimage);

const swapResult = await client.createAtomicSwap({
  seller: '0x...',
  hashlock,
  timelock: Math.floor(Date.now() / 1000) + 3600, // 1 hour
  assetType: 'ETH',
  amount: ethers.parseEther('5.0')
});

console.log('Swap created:', swapResult.swapId);
```

### Policy Management

```typescript
// Get user's current policy
const policy = await client.getUserPolicy('0x...');

// Update policy settings
await client.updateUserPolicy({
  maxAmount: ethers.parseEther('10'),
  riskThreshold: 0.8,
  autoApprove: false
});
```

## Configuration

```typescript
interface AMTTPConfig {
  rpcUrl: string;              // Ethereum RPC endpoint
  contractAddress: string;     // AMTTP contract address
  oracleUrl: string;          // Oracle service URL
  privateKey?: string;        // Private key for signing
  provider?: ethers.Provider; // Custom provider
  signer?: ethers.Signer;    // Custom signer
}
```

## Risk Categories

- **MINIMAL** (0-0.2): Auto-approve, minimal monitoring
- **LOW** (0.2-0.4): Approve with logging
- **MEDIUM** (0.4-0.7): Review recommended
- **HIGH** (0.7+): Requires approval or escrow

## ML Model Integration

The SDK integrates with the AMTTP Stacked Ensemble fraud detection model:

- **Architecture**: GraphSAGE + LGBM + XGBoost + Linear Meta-Learner
- **ROC-AUC**: ~0.94 (Overall discriminative ability)
- **PR-AUC**: ~0.87 (Primary metric for imbalanced fraud detection)
- **F1 Score**: ~0.87 (Balanced precision/recall at default threshold)
- **Training Data**: 28,457 real fraud transactions (time-based split, days 27-30 test)
- **Features**: 20-dimensional feature vectors with graph embeddings
- **Real-time**: < 100ms response time

## Explainability

The SDK includes a powerful explainability module that converts raw ML scores into human-readable explanations:

```typescript
import { ExplainabilityService, formatExplanationForDisplay } from '@amttp/client-sdk';

// Create explainability service
const explainer = new ExplainabilityService('http://localhost:8009');

// Get explanation for a risk score
const explanation = await explainer.explain({
  riskScore: 0.73,
  features: {
    amount_eth: 50,
    tx_count_24h: 15,
    hops_to_sanctioned: 2
  }
});

console.log(explanation.summary);
// "High-risk transaction due to large amount and proximity to flagged addresses"

console.log(explanation.topReasons);
// ["Large transaction (50 ETH)", "2 hops from sanctioned address", "15 transactions in 24h"]

console.log(explanation.action);
// "ESCROW"

// Explain a specific transaction
const txExplanation = await explainer.explainTransaction({
  transactionHash: '0xabc123...',
  riskScore: 0.85,
  sender: '0x1234...',
  receiver: '0xabcd...',
  amount: 100,
  features: { tx_count_24h: 25 }
});

// Format for display
console.log(formatExplanationForDisplay(explanation));
```

### Explanation Features

- **Factor Analysis**: Detailed breakdown of each risk factor's contribution
- **Typology Detection**: Identifies specific fraud patterns (structuring, layering, smurfing, etc.)
- **Graph Explanations**: Network-based risk factors (proximity to bad actors)
- **Recommendations**: Actionable next steps based on risk level
- **Degraded Mode**: Falls back to local explanations when service unavailable

### Detected Typologies

| Typology | Description |
|----------|-------------|
| `structuring` | Breaking large transactions into smaller ones |
| `layering` | Complex chains to obscure fund origins |
| `smurfing` | Using multiple accounts to move funds |
| `fan_out` | Single source distributing to many |
| `fan_in` | Many sources consolidating to one |
| `mixer_interaction` | Funds through mixing services |
| `sanctions_proximity` | Near sanctioned entities |
| `dormant_activation` | Inactive account suddenly active |

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Your dApp     │    │   AMTTP Client   │    │  Oracle Service │
│                 │───▶│      SDK         │───▶│ + Stacked Model │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌──────────────────┐    ┌─────────────────┐
                       │ AMTTP Contract   │    │   MongoDB       │
                       │   (On-chain)     │    │  (Risk Logs)    │
                       └──────────────────┘    └─────────────────┘
```

## Examples

See the `/examples` directory for complete integration examples:

- **Basic Integration**: Simple transaction protection
- **DeFi Integration**: DEX transaction monitoring
- **Wallet Integration**: MetaMask Snap example
- **E-commerce**: Payment processing with fraud detection

## API Reference

### AMTTPClient

#### Methods

- `submitTransaction(request)` - Submit transaction with fraud protection
- `scoreTransactionRisk(params)` - Get risk assessment
- `createAtomicSwap(params)` - Create secure atomic swap
- `getKYCStatus(address)` - Check KYC status
- `getUserPolicy(address)` - Get user policy settings
- `updateUserPolicy(policy)` - Update policy settings

#### Events

- `riskScoreCalculated` - When risk assessment completes
- `transactionSubmitted` - When transaction is sent
- `approvalRequired` - When manual approval needed

## Security

- All private keys are handled securely
- Risk models run in isolated environments
- Smart contracts are upgradeable with timelock
- Comprehensive audit trail maintained

## License

MIT

## Support

- Documentation: https://docs.amttp.io
- Discord: https://discord.gg/amttp
- GitHub: https://github.com/your-org/amttp

---

Built with ❤️ by the AMTTP team