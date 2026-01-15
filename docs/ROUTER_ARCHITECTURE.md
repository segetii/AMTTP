# AMTTP Router Architecture

## Recommended: Off-Chain Router Pattern

The AMTTP protocol uses an **off-chain router** for maximum gas efficiency. This means the routing decision happens in the SDK/frontend, not on-chain.

## Architecture Comparison

### ❌ On-Chain Router (Not Recommended)
```
User → [On-Chain Router] → [AMTTPCore/AMTTPNFT]
         ↑
         Extra 21,000 gas per transaction
         Extra deployment cost (~0.036 ETH)
```

### ✅ Off-Chain Router (Recommended)
```
User → [SDK Router] → [AMTTPCore/AMTTPNFT]
         ↑
         Zero gas overhead
         Zero deployment cost
         Instant updates
```

## Contract Addresses (Sepolia)

| Contract | Address | Purpose |
|----------|---------|---------|
| **AMTTPCore** | `0x2cF0a1D4FB44C97E80c7935E136a181304A67923` | ETH/ERC20 escrow |
| **AMTTPNFT** | `0x49Acc645E22c69263fCf7eFC165B6c3018d5Db5f` | ERC721/NFT escrow |
| **PolicyEngine** | `0x520393A448543FF55f02ddA1218881a8E5851CEc` | Risk assessment |
| **DisputeResolver** | `0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade` | Kleros arbitration |
| **CrossChain** | `0xc8d887665411ecB4760435fb3d20586C1111bc37` | LayerZero messaging |

## Routing Logic

The SDK automatically routes based on asset type:

```javascript
// ETH or ERC20 → AMTTPCore
if (assetType === 'ETH' || assetType === 'ERC20') {
    return contracts.core;
}

// NFT → AMTTPNFT
if (assetType === 'ERC721' || assetType === 'NFT_TO_NFT') {
    return contracts.nft;
}
```

## Gas Savings

| Operation | On-Chain Router | Off-Chain Router | Savings |
|-----------|-----------------|------------------|---------|
| initiateSwap | ~180,000 | ~159,000 | **-12%** |
| completeSwap | ~85,000 | ~64,000 | **-25%** |
| refundSwap | ~75,000 | ~54,000 | **-28%** |
| getStats | ~15,000 | **FREE** | **-100%** |

## Usage

```javascript
import { AMTTPRouter } from '@amttp/client-sdk';

const router = new AMTTPRouter(signer);

// ETH swap - routes to AMTTPCore
await router.swapETH(seller, hashlock, timelock, riskScore, kycHash, sig, amount);

// NFT swap - routes to AMTTPNFT  
await router.swapNFTforETH(buyer, nftContract, tokenId, price, hashlock, timelock, riskScore, kycHash, sig);

// Universal complete - auto-detects contract
await router.completeSwap(swapId, preimage);
```

## On-Chain Router (Still Available)

If you need full on-chain routing (for smart contract integrations), the `AMTTPRouter` contract is deployed at:

- **Sepolia**: `0xbe6EC386ECDa39F3B7c120d9E239e1fBC78d52e3`

Use this only when:
- Your integration MUST be from another smart contract
- You need fully trustless routing logic
- Gas cost is not a concern
