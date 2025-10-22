# @amttp/client-sdk

TypeScript SDK for integrating with the AMTTP (AI-powered Multi-signature Transaction Trust Protocol) fraud detection system.

## Features

- 🤖 **AI-Powered Risk Scoring**: Integrates with your trained DQN model (F1=0.669+)
- 🔒 **Atomic Swaps**: Secure transaction escrow for high-risk transactions
- 🆔 **KYC Integration**: Automatic compliance checking
- 📊 **Real-time Monitoring**: Transaction risk assessment and logging
- 🛡️ **Policy Engine**: User-defined transaction limits and risk thresholds
- ⚡ **Multi-chain Ready**: Designed for Ethereum, Polygon, Arbitrum

## Installation

```bash
npm install @amttp/client-sdk
# or
yarn add @amttp/client-sdk
```

## Quick Start

```typescript
import { AMTTPClient } from '@amttp/client-sdk';

// Initialize client
const client = new AMTTPClient({
  rpcUrl: 'https://eth-mainnet.alchemyapi.io/v2/YOUR_KEY',
  contractAddress: '0x...', // Your deployed AMTTP contract
  oracleUrl: 'https://api.amttp.io', // Your oracle service
  privateKey: 'YOUR_PRIVATE_KEY' // Or connect to MetaMask
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

## DQN Model Integration

The SDK integrates with your trained DQN fraud detection model:

- **Performance**: F1 Score = 0.669+ (Production Ready)
- **Training Data**: 28,457 real fraud transactions
- **Features**: 20-dimensional feature vectors
- **Real-time**: < 100ms response time

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Your dApp     │    │   AMTTP Client   │    │  Oracle Service │
│                 │───▶│      SDK         │───▶│   + DQN Model   │
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