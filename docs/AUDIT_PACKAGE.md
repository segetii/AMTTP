# AMTTP Smart Contract Audit Package

## 1. Project Overview

**Project Name:** AMTTP (Anti-Money-Laundering & Transaction Transparency Protocol)  
**Version:** 1.0.0  
**Audit Scope:** Smart Contracts  
**Target Chains:** Ethereum, Polygon, Arbitrum, Base, Optimism  

### Description

AMTTP is a decentralized escrow and risk management protocol that:
- Uses ML-based risk scoring for transaction monitoring
- Implements multi-oracle consensus for risk score submission
- Provides cross-chain risk score propagation via LayerZero
- Integrates with Kleros for decentralized dispute resolution

---

## 2. Contracts in Scope

| Contract | LOC | Complexity | Description |
|----------|-----|------------|-------------|
| AMTTPCoreSecure.sol | ~1000 | High | Main escrow, swap lifecycle, multi-oracle consensus |
| AMTTPDisputeResolver.sol | ~420 | Medium | Kleros integration, dispute lifecycle |
| AMTTPCrossChain.sol | ~860 | High | LayerZero integration, cross-chain messaging |
| AMTTPPolicyEngine.sol | ~400 | Medium | Policy rules, risk thresholds |
| AMTTPNFT.sol | ~300 | Low | NFT receipts for completed transactions |

**Total Lines of Code:** ~3,000 (excluding tests/mocks)

---

## 3. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         User/Frontend                            │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       AMTTPCoreSecure                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Swap Mgmt    │  │ Multi-Oracle │  │ Timelock     │           │
│  │ (HTLC)       │  │ Consensus    │  │ Upgrades     │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
          │                    │                    │
          ▼                    ▼                    ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ PolicyEngine     │  │ DisputeResolver  │  │ CrossChain       │
│ (Risk Rules)     │  │ (Kleros)         │  │ (LayerZero)      │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

---

## 4. Key Security Features

### 4.1 Access Control
- Role-based: Owner, Oracle, Approver, DisputeResolver
- Multi-oracle consensus (M-of-N signatures)
- Timelock for admin operations (2 days)
- UUPS upgradeable with governance

### 4.2 Reentrancy Protection
- `nonReentrant` modifier on all state-changing functions
- CEI (Checks-Effects-Interactions) pattern
- No delegatecall to untrusted contracts

### 4.3 Replay Protection
- Per-user nonce tracking (`usedNonces` mapping)
- Signature expiry (5 minute validity)
- Unique swap IDs via keccak256

### 4.4 Cross-Chain Security
- Trusted remote whitelisting
- Per-chain rate limiting
- Per-chain pause functionality
- Message authentication via LayerZero

### 4.5 Dispute Resolution
- Kleros arbitration integration
- Evidence immutability (IPFS + on-chain hash)
- Emergency fund recovery after 30 days

---

## 5. Known Issues / Design Decisions

| Issue | Severity | Status | Notes |
|-------|----------|--------|-------|
| Single-point oracle initially | Medium | Mitigated | Can upgrade to multi-oracle |
| No on-chain KYC data | Design | Intentional | Only hash stored, PII off-chain |
| Timelock bypass by owner | Design | Accepted | Emergency pause still possible |
| LayerZero trust assumption | Medium | Accepted | Using trusted remote pattern |

---

## 6. External Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| OpenZeppelin Contracts | 4.9.x | Access control, upgrades, security |
| OpenZeppelin Upgradeable | 4.9.x | UUPS proxy pattern |
| LayerZero | v1 | Cross-chain messaging |
| Kleros | v2 | Decentralized arbitration |

---

## 7. Test Coverage

| Contract | Unit Tests | Integration | Gas Analysis |
|----------|------------|-------------|--------------|
| AMTTPCoreSecure | ✅ | ✅ | ✅ |
| AMTTPDisputeResolver | ✅ | ✅ | ✅ |
| AMTTPCrossChain | ✅ | ⚠️ Partial | ✅ |
| AMTTPPolicyEngine | ✅ | ✅ | ⚠️ Partial |

### Running Tests

```bash
# All tests
npx hardhat test

# With gas reporting
npx hardhat test --grep "Gas"

# Coverage
npx hardhat coverage
```

---

## 8. Deployment Information

### Testnet Deployments (Sepolia)

| Contract | Address | Verified |
|----------|---------|----------|
| AMTTPCoreSecure | See deployments/ | ✅ |
| AMTTPDisputeResolver | See deployments/ | ✅ |
| AMTTPCrossChain | See deployments/ | ✅ |

### Gas Costs (Optimized)

| Operation | Gas |
|-----------|-----|
| initiateSwap (ETH) | ~300,000 |
| completeSwap | ~80,000 |
| escrowTransaction | ~283,000 |
| emergencyWithdraw | ~41,000 |

---

## 9. Focus Areas for Audit

### Critical Priority
1. **Swap lifecycle** - Can funds be stolen or locked?
2. **Multi-oracle consensus** - Signature verification correctness
3. **Upgrade mechanism** - Can attacker bypass timelock?
4. **Reentrancy** - Any unprotected external calls?

### High Priority
1. **Cross-chain message handling** - Replay, ordering, authentication
2. **Dispute resolution** - Can funds be stuck forever?
3. **Rate limiting** - Can it be bypassed or griefed?
4. **Access control** - Role escalation vulnerabilities

### Medium Priority
1. **Gas optimization** - DoS via high gas consumption
2. **Event emissions** - Missing or incorrect events
3. **Error handling** - Information leakage

---

## 10. Audit Timeline Request

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Initial Review | 2 weeks | Preliminary findings |
| Deep Dive | 2 weeks | Detailed analysis |
| Remediation | 1 week | Fix verification |
| Final Report | 1 week | Publishable audit report |

**Preferred Auditors:**
1. Trail of Bits
2. OpenZeppelin
3. Spearbit
4. Consensys Diligence

---

## 11. Contact Information

**Technical Lead:** [Your Name]  
**Email:** [your@email.com]  
**Repository:** https://github.com/segetii/fintech  
**Branch:** sync/merge-2025-10-22  

---

## 12. File Checklist for Auditors

```
contracts/
├── AMTTPCoreSecure.sol      ✅ In scope
├── AMTTPDisputeResolver.sol ✅ In scope
├── AMTTPCrossChain.sol      ✅ In scope
├── AMTTPPolicyEngine.sol    ✅ In scope
├── AMTTPNFT.sol             ✅ In scope
├── interfaces/
│   ├── IKleros.sol          ✅ In scope
│   └── ILayerZero.sol       ✅ In scope
└── mocks/                   ❌ Out of scope

test/
├── GasAnalysis.test.mjs     ❌ Out of scope
├── AMTTPDisputeResolver.test.mjs ❌ Out of scope
└── ...

spec/
└── AMTTPCoreSecure.spec.sol ✅ Reference for invariants
```
