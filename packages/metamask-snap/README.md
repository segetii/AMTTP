# AMTTP MetaMask Snap

🛡️ **AI-Powered Transaction Risk Assessment for MetaMask**

This MetaMask Snap provides real-time fraud detection and policy enforcement directly in your wallet. Every transaction is analyzed for risk before you confirm it.

## Features

- **🔍 Real-Time Risk Scoring** - AI/ML analysis of every transaction
- **🚫 Sanctions Screening** - HMT/OFAC compliance checking
- **⚙️ Custom Policies** - Set your own risk thresholds
- **📋 Allowlist/Blocklist** - Manage trusted and blocked addresses
- **📊 Transaction History** - Track all risk assessments

## Risk Levels

| Level | Score | Action |
|-------|-------|--------|
| 🟢 LOW | 0-39 | Auto-approve |
| 🟡 MEDIUM | 40-69 | Warning shown |
| 🔴 HIGH | 70-84 | Requires confirmation |
| ⛔ CRITICAL | 85-100 | Blocked by policy |

## Installation

### Requirements
- MetaMask Flask (for development) or MetaMask v11.4+
- Node.js 18+
- Yarn 3+

### Build from Source

```bash
cd packages/metamask-snap
yarn install
yarn build
```

### Install in MetaMask

1. Open MetaMask Flask
2. Go to Settings → Snaps
3. Install from `http://localhost:8080`

Or use the connect button on the AMTTP dApp.

## Usage

### Automatic Protection

Once installed, the Snap automatically analyzes every transaction:

1. Initiate a transaction in any dApp
2. See the **AMTTP Risk Assessment** panel
3. Review risk score, factors, and recommendation
4. Confirm or reject based on the assessment

### RPC Methods

DApps can interact with the Snap via RPC:

```javascript
// Get current policy
const policy = await ethereum.request({
  method: 'wallet_invokeSnap',
  params: {
    snapId: 'npm:@amttp/metamask-snap',
    request: { method: 'amttp_getPolicy' }
  }
});

// Update policy
await ethereum.request({
  method: 'wallet_invokeSnap',
  params: {
    snapId: 'npm:@amttp/metamask-snap',
    request: {
      method: 'amttp_setPolicy',
      params: {
        maxRiskThreshold: 60,
        blockHighRisk: true
      }
    }
  }
});

// Add to allowlist
await ethereum.request({
  method: 'wallet_invokeSnap',
  params: {
    snapId: 'npm:@amttp/metamask-snap',
    request: {
      method: 'amttp_addToAllowlist',
      params: { address: '0x...' }
    }
  }
});

// Check risk for an address
const risk = await ethereum.request({
  method: 'wallet_invokeSnap',
  params: {
    snapId: 'npm:@amttp/metamask-snap',
    request: {
      method: 'amttp_checkRisk',
      params: { to: '0x...', value: '1000000000000000000' }
    }
  }
});
```

### Available Methods

| Method | Description |
|--------|-------------|
| `amttp_getPolicy` | Get current user policy |
| `amttp_setPolicy` | Update policy settings |
| `amttp_addToAllowlist` | Add address to trusted list |
| `amttp_addToBlocklist` | Block an address |
| `amttp_removeFromAllowlist` | Remove from trusted list |
| `amttp_removeFromBlocklist` | Unblock an address |
| `amttp_getHistory` | Get transaction history |
| `amttp_getStats` | Get approval/block statistics |
| `amttp_checkRisk` | Check risk score for address |

## Policy Configuration

```typescript
interface UserPolicy {
  maxRiskThreshold: number;      // 0-100, default: 70
  blockHighRisk: boolean;        // Auto-block high risk, default: true
  requireConfirmation: boolean;  // Require user confirmation, default: true
  allowedAddresses: string[];    // Trusted addresses (skip checks)
  blockedAddresses: string[];    // Blocked addresses (always reject)
  dailyLimit: string;            // Daily ETH limit
  notifyOnMediumRisk: boolean;   // Show warnings for medium risk
}
```

## API Integration

The Snap connects to:

- **AMTTP ML API** (`localhost:8000`) - Hybrid risk scoring
- **FCA Compliance API** (`localhost:8002`) - Sanctions checking

For production, update `snap.config.js` with your API endpoints.

## Development

```bash
# Start development server
yarn start

# Build for production
yarn build

# Run tests
yarn test

# Lint code
yarn lint
```

## Security

- All risk assessments are performed server-side
- User policies are stored locally in MetaMask
- No transaction data is stored externally
- Sanctions lists are checked in real-time

## License

MIT License - See LICENSE file

## Support

For issues and feature requests, visit:
https://github.com/segetii/fintech/issues
