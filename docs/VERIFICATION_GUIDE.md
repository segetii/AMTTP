# AMTTP Contract Verification Guide

## 🔑 Quick Start

### Step 1: Get Etherscan API Key (Free)

1. Go to [Etherscan.io](https://etherscan.io)
2. Create a free account
3. Go to **My Account** → **API Keys**
4. Click **Add** to create a new API key
5. Copy the key

### Step 2: Add to Environment

Create or edit `.env` file in the project root:

```bash
# Add your Etherscan API key
ETHERSCAN_API_KEY=your_api_key_here
```

### Step 3: Run Verification

```bash
# Verify all contracts
npx hardhat run scripts/verify-contracts.cjs --network sepolia

# Or verify individually:
npx hardhat verify --network sepolia 0x520393A448543FF55f02ddA1218881a8E5851CEc
```

---

## 📋 Deployed Contracts (Sepolia)

| Contract | Address | Constructor Args |
|----------|---------|-----------------|
| AMTTPPolicyEngine | `0x520393A448543FF55f02ddA1218881a8E5851CEc` | None (proxy) |
| AMTTPDisputeResolver | `0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade` | Arbitrator, MetaEvidence |
| AMTTPCrossChain | `0xc8d887665411ecB4760435fb3d20586C1111bc37` | Endpoint, PolicyEngine |

---

## 🔗 View on Etherscan (Without Verification)

Even without verification, you can view the contracts:

- [PolicyEngine](https://sepolia.etherscan.io/address/0x520393A448543FF55f02ddA1218881a8E5851CEc)
- [DisputeResolver](https://sepolia.etherscan.io/address/0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade)
- [CrossChain](https://sepolia.etherscan.io/address/0xc8d887665411ecB4760435fb3d20586C1111bc37)

---

## 📝 Manual Verification Commands

If the script fails, verify manually:

```powershell
# 1. PolicyEngine (Upgradeable - verifies implementation)
npx hardhat verify --network sepolia 0x520393A448543FF55f02ddA1218881a8E5851CEc

# 2. DisputeResolver (with constructor args)
npx hardhat verify --network sepolia 0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade "0x90992fB4e15cE0C59AEfFb376460FDc4d1fDD2f8" "ipfs://QmAMTTPMetaEvidence"

# 3. CrossChain (with constructor args)
npx hardhat verify --network sepolia 0xc8d887665411ecB4760435fb3d20586C1111bc37 "0xae92d5aD7583AD66E49A0c67BAd18F6ba52dDDc1" "0x520393A448543FF55f02ddA1218881a8E5851CEc"
```

---

## 🌐 Multi-Chain Verification

For other networks, add API keys to `.env`:

```bash
ETHERSCAN_API_KEY=your_etherscan_key
POLYGONSCAN_API_KEY=your_polygonscan_key
ARBISCAN_API_KEY=your_arbiscan_key
BASESCAN_API_KEY=your_basescan_key
```

Get free API keys:
- [Etherscan](https://etherscan.io/myapikey) - Ethereum
- [Polygonscan](https://polygonscan.com/myapikey) - Polygon
- [Arbiscan](https://arbiscan.io/myapikey) - Arbitrum
- [Basescan](https://basescan.org/myapikey) - Base

---

## ❓ Troubleshooting

### "Already Verified"
The contract is already verified - this is good!

### "Bytecode does not match"
- Ensure you're using the exact same compiler settings
- Check `hardhat.config.cjs` optimizer settings match deployment

### Rate Limiting
- Etherscan limits to 5 calls/second
- The script waits 2 seconds between verifications
- If still rate limited, wait a few minutes

### Proxy Verification
PolicyEngine uses UUPS proxy. Hardhat automatically detects and verifies:
1. The proxy contract
2. The implementation contract

---

## 📊 Verification Benefits

Once verified on Etherscan:
- ✅ Source code readable by anyone
- ✅ "Read Contract" and "Write Contract" tabs available
- ✅ ABI automatically extracted
- ✅ Increased trust and transparency
- ✅ Required for many DeFi integrations
