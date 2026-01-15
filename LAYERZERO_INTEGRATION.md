# AMTTP LayerZero Cross-Chain Integration

## Overview

AMTTP now supports cross-chain risk scoring and global address blocking via LayerZero V1 integration. This enables:

- **Cross-Chain Risk Propagation**: Send risk scores from one chain to all others
- **Global Address Blocking**: Block fraudulent addresses across all supported chains
- **Dispute Result Sync**: Propagate Kleros dispute outcomes cross-chain
- **Aggregated Risk View**: Get the maximum risk score from any chain

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AMTTP Cross-Chain Flow                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Ethereum                Polygon                 Arbitrum              │
│   ┌──────────┐           ┌──────────┐           ┌──────────┐           │
│   │ CrossChain│ ──LZ──▶  │ CrossChain│ ──LZ──▶  │ CrossChain│          │
│   │ Contract  │          │ Contract  │          │ Contract  │          │
│   └────┬─────┘           └────┬─────┘           └────┬─────┘           │
│        │                      │                      │                  │
│        ▼                      ▼                      ▼                  │
│   ┌──────────┐           ┌──────────┐           ┌──────────┐           │
│   │ Policy   │           │ Policy   │           │ Policy   │           │
│   │ Engine   │           │ Engine   │           │ Engine   │           │
│   └──────────┘           └──────────┘           └──────────┘           │
│                                                                         │
│   Risk detected on any chain → Propagated to ALL chains instantly      │
└─────────────────────────────────────────────────────────────────────────┘
```

## Supported Chains

| Chain | LayerZero Chain ID | Status |
|-------|-------------------|--------|
| Ethereum | 101 | ✅ Configured |
| Polygon | 109 | ✅ Configured |
| Arbitrum | 110 | ✅ Configured |
| Optimism | 111 | ✅ Configured |
| Base | 184 | ✅ Configured |
| BSC | 102 | ✅ Configured |
| Avalanche | 106 | ✅ Configured |

## Contract Addresses

### Local Hardhat (Testing)
```
LayerZero Endpoint: 0x9A676e781A523b5d0C0e43731313A708CB607508
AMTTPCrossChain:    0x0B306BF915C4d645ff596e518fAf3F9669b97016
PolicyEngine:       0x8A791620dd6260079BF849Dc5567aDC3F2FdC318
```

## Usage

### 1. Send Risk Score to Another Chain

```solidity
// Solidity
uint16 polygonChainId = 109;
address targetAddress = 0x...;
uint256 riskScore = 850; // High risk (0-1000)

uint256 fee = crossChain.estimateRiskScoreFee(polygonChainId, targetAddress, riskScore);
crossChain.sendRiskScore{value: fee}(polygonChainId, targetAddress, riskScore, "0x");
```

```typescript
// TypeScript SDK
import { CrossChainService, createCrossChainService } from '@amttp/client-sdk';

const crossChain = createCrossChainService({
  crossChainAddress: '0x0B306BF915C4d645ff596e518fAf3F9669b97016',
  provider,
  signer
});

const result = await crossChain.sendRiskScore('polygon', targetAddress, 850);
console.log(`Sent to Polygon, tx: ${result.transactionHash}`);
```

### 2. Block Address Globally

```solidity
// Block on Polygon, Arbitrum, and Base simultaneously
uint16[] memory chains = new uint16[](3);
chains[0] = 109; // Polygon
chains[1] = 110; // Arbitrum
chains[2] = 184; // Base

crossChain.blockAddressGlobally{value: totalFee}(
    chains,
    fraudsterAddress,
    "Confirmed fraud - Kleros ruling"
);
```

```typescript
// TypeScript SDK
await crossChain.blockAddressGlobally(
  ['polygon', 'arbitrum', 'base'],
  fraudsterAddress,
  'Confirmed fraud - Kleros ruling'
);
```

### 3. Check Aggregated Risk Score

```solidity
// Get highest risk score from any chain
(uint256 maxScore, uint16 sourceChain) = crossChain.getAggregatedRiskScore(targetAddress);

if (maxScore >= 700) {
    // Block transaction - high cross-chain risk
}
```

```typescript
// TypeScript SDK
const riskData = await crossChain.getAggregatedRiskScore(targetAddress);
console.log(`Max risk: ${riskData.maxScore} from ${riskData.chainName}`);

if (riskData.isGloballyBlocked) {
    console.log('Address is blocked globally!');
}
```

### 4. Check if Address is Globally Blocked

```solidity
bool isBlocked = crossChain.isGloballyBlocked(suspiciousAddress);
```

```typescript
const isBlocked = await crossChain.isGloballyBlocked(suspiciousAddress);
```

## Message Types

| Type | Value | Description |
|------|-------|-------------|
| MSG_RISK_SCORE | 1 | Risk score update |
| MSG_BLOCK_ADDRESS | 2 | Block address globally |
| MSG_UNBLOCK_ADDRESS | 3 | Unblock address |
| MSG_POLICY_UPDATE | 4 | Policy configuration sync |
| MSG_DISPUTE_RESULT | 5 | Kleros dispute outcome |

## Events

```solidity
// Emitted when risk score sent
event RiskScoreSent(uint16 indexed dstChainId, address indexed targetAddress, uint256 riskScore, bytes32 messageId);

// Emitted when risk score received from another chain
event RiskScoreReceived(uint16 indexed srcChainId, address indexed targetAddress, uint256 riskScore, uint64 nonce);

// Emitted when address blocked globally
event AddressBlockedGlobally(address indexed targetAddress, uint16 indexed originChain, string reason);

// Emitted when address unblocked
event AddressUnblockedGlobally(address indexed targetAddress, uint16 indexed originChain);
```

## Deployment

### Deploy to Local Hardhat
```bash
npx hardhat run scripts/deploy-layerzero.cjs --network localhost
```

### Deploy to Testnet (requires PRIVATE_KEY env)
```bash
# Polygon Mumbai
npx hardhat run scripts/deploy-layerzero.cjs --network polygonMumbai

# Arbitrum Sepolia
npx hardhat run scripts/deploy-layerzero.cjs --network arbitrumSepolia
```

### Configure Trusted Remotes

After deploying to multiple chains, set trusted remotes:

```javascript
// On Ethereum
await ethereumCrossChain.setTrustedRemotePath(109, 
  ethers.solidityPacked(['address', 'address'], [polygonCrossChainAddr, ethereumCrossChainAddr])
);

// On Polygon
await polygonCrossChain.setTrustedRemotePath(101,
  ethers.solidityPacked(['address', 'address'], [ethereumCrossChainAddr, polygonCrossChainAddr])
);
```

## Security Considerations

1. **Trusted Remotes**: Only messages from configured trusted remotes are accepted
2. **Nonce Protection**: Each message has a unique nonce to prevent replay attacks
3. **Failed Message Retry**: Failed messages can be retried without re-sending
4. **Pausable**: Owner can pause cross-chain operations in emergency
5. **High Risk Auto-Block**: Scores ≥700 automatically trigger global block

## Fee Estimation

LayerZero fees vary by:
- Destination chain
- Payload size
- Gas price on destination

Always estimate before sending:

```typescript
const fee = await crossChain.estimateRiskScoreFee('polygon', targetAddress, 850);
console.log(`Fee: ${ethers.formatEther(fee)} ETH`);
```

## Integration with ML Pipeline

When the ML API detects high-risk transactions:

```python
# Python API - hybrid_api.py
@app.post("/cross-chain/propagate-risk")
async def propagate_risk(request: RiskPropagationRequest):
    # Send risk score to all chains
    for chain in ['polygon', 'arbitrum', 'base']:
        await crosschain_service.send_risk_score(
            chain, 
            request.address, 
            request.risk_score
        )
    return {"status": "propagated", "chains": 3}
```

## Files Created

- `contracts/interfaces/ILayerZero.sol` - LayerZero interfaces
- `contracts/AMTTPCrossChain.sol` - Main cross-chain contract
- `contracts/mocks/MockLayerZeroEndpoint.sol` - Local testing mock
- `scripts/deploy-layerzero.cjs` - Deployment script
- `packages/client-sdk/src/crosschain.ts` - TypeScript SDK

## Next Steps

1. Deploy to testnets (Sepolia, Mumbai, Arbitrum Sepolia)
2. Configure production LayerZero endpoints
3. Add cross-chain risk to dashboard UI
4. Implement automatic propagation from ML API
