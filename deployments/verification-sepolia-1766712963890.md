# AMTTP Contract Verification Report

**Network:** sepolia  
**Date:** 2025-12-26T01:36:03.890Z  
**Status:** 0/3 verified

## Verified Contracts

| Contract | Address | Status | Etherscan |
|----------|---------|--------|-----------|
| AMTTPPolicyEngine | `0x520393A448543FF55f02ddA1218881a8E5851CEc` | ❌ api-error | [View](https://sepolia.etherscan.io/address/0x520393A448543FF55f02ddA1218881a8E5851CEc#code) |
| AMTTPDisputeResolver | `0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade` | ❌ api-error | [View](https://sepolia.etherscan.io/address/0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade#code) |
| AMTTPCrossChain | `0xc8d887665411ecB4760435fb3d20586C1111bc37` | ❌ api-error | [View](https://sepolia.etherscan.io/address/0xc8d887665411ecB4760435fb3d20586C1111bc37#code) |

## Contract Details

### AMTTPPolicyEngine
- **Purpose:** Risk policy management, transaction thresholds, compliance rules
- **Type:** UUPS Upgradeable Proxy
- **Address:** `0x520393A448543FF55f02ddA1218881a8E5851CEc`

### AMTTPDisputeResolver  
- **Purpose:** Kleros integration for dispute arbitration
- **Arbitrator:** `0x90992fB4e15cE0C59AEfFb376460FDc4d1fDD2f8` (Kleros Sepolia)
- **Address:** `0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade`

### AMTTPCrossChain
- **Purpose:** LayerZero cross-chain policy synchronization
- **LayerZero Endpoint:** `0xae92d5aD7583AD66E49A0c67BAd18F6ba52dDDc1`
- **Chain ID:** 10161 (Sepolia)
- **Address:** `0xc8d887665411ecB4760435fb3d20586C1111bc37`

## Next Steps


### Failed Verifications
Some contracts failed to verify. Try:
1. Ensure ETHERSCAN_API_KEY is set in .env
2. Wait and retry (rate limiting)
3. Verify manually at https://sepolia.etherscan.io/verifyContract


## Manual Verification Commands

```bash
# PolicyEngine (no constructor args)
npx hardhat verify --network sepolia 0x520393A448543FF55f02ddA1218881a8E5851CEc

# DisputeResolver
npx hardhat verify --network sepolia 0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade \
  "0x90992fB4e15cE0C59AEfFb376460FDc4d1fDD2f8" "ipfs://QmAMTTPMetaEvidence"

# CrossChain
npx hardhat verify --network sepolia 0xc8d887665411ecB4760435fb3d20586C1111bc37 \
  "0xae92d5aD7583AD66E49A0c67BAd18F6ba52dDDc1" "0x520393A448543FF55f02ddA1218881a8E5851CEc"
```
