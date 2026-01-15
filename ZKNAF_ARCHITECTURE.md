# AMTTP zkNAF - Zero-Knowledge Non-Disclosing Anti-Fraud

## Overview

zkNAF (Zero-Knowledge Non-Disclosing Anti-Fraud) is a privacy-preserving compliance verification system that allows users to prove regulatory compliance without revealing sensitive personal information.

**Key Innovation:** Users can interact with DeFi protocols while proving they meet compliance requirements, without exposing their identity, exact risk scores, or KYC details.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER / PUBLIC LAYER                               │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        ZK Proofs (Privacy-Preserving)                 │  │
│  │                                                                       │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐       │  │
│  │  │  Sanctions      │  │  Risk Range     │  │  KYC Verified   │       │  │
│  │  │  Non-Membership │  │  Proof          │  │  Proof          │       │  │
│  │  │                 │  │                 │  │                 │       │  │
│  │  │  "I am NOT on   │  │  "My risk is    │  │  "I passed KYC  │       │  │
│  │  │   any list"     │  │   LOW (<40)"    │  │   verification" │       │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘       │  │
│  │                                                                       │  │
│  │  What's HIDDEN:           What's HIDDEN:      What's HIDDEN:         │  │
│  │  • Sanctions list         • Exact score       • Real name            │  │
│  │  • User identity          • ML features       • Date of birth        │  │
│  │  • Check details          • XAI explanation   • Address / ID         │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ ZK Proof Only
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ON-CHAIN VERIFICATION (AMTTPzkNAF.sol)                 │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  • Groth16 proof verification (BN254 curve)                           │  │
│  │  • Proof storage with expiration                                      │  │
│  │  • Compliance status registry                                         │  │
│  │  • DeFi protocol integration                                          │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ Proof Records
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REGULATED ENTITY LAYER (AMTTP)                           │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │           Full Data (Encrypted at Rest, 5-Year Retention)             │  │
│  │                                                                       │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐       │  │
│  │  │  KYC Records    │  │  Risk Scores    │  │  Audit Trail    │       │  │
│  │  │  • Full name    │  │  • Exact score  │  │  • All proofs   │       │  │
│  │  │  • DOB          │  │  • ML features  │  │  • Revocations  │       │  │
│  │  │  • Address      │  │  • XAI explain  │  │  • Timestamps   │       │  │
│  │  │  • Documents    │  │  • Model ver.   │  │  • Integrity    │       │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘       │  │
│  │                                                                       │  │
│  │  Disclosed ONLY for:                                                  │  │
│  │  • SAR filing to NCA (FSMA s.330)                                     │  │
│  │  • Law enforcement requests                                           │  │
│  │  • FCA regulatory audits                                              │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## FCA Compliance Compatibility

### Regulatory Requirements Met

| Requirement | Regulation | How zkNAF Complies |
|-------------|------------|-------------------|
| **Customer Due Diligence** | MLR 2017 Reg. 27-38 | Full KYC records maintained; ZK proof just for external verification |
| **Ongoing Monitoring** | MLR 2017 Reg. 28(11) | Actual risk scores stored; proofs show range only |
| **Record Keeping** | MLR 2017 Reg. 40 | 5-year retention of all proof records with full data |
| **SAR Reporting** | FSMA s.330 | Full underlying data available for SAR submission |
| **Travel Rule** | FATF Rec. 16 | Original data maintained; ZK proofs are supplementary |
| **XAI Explainability** | FCA Guidance | Full XAI explanations stored, not exposed in proofs |

### What zkNAF Does NOT Replace

❌ **SAR Filing** - Full data required for NCA submission
❌ **Travel Rule Exchange** - Actual names/addresses must be transmitted
❌ **Law Enforcement Requests** - Full records produced on request
❌ **Regulatory Audits** - Complete audit trail with actual values

### What zkNAF DOES Enable

✅ **Privacy for DeFi** - Users prove compliance without revealing identity
✅ **Sanctions Screening** - Prove non-membership without list disclosure
✅ **Risk Verification** - Prove acceptable risk without exact score
✅ **KYC Status** - Prove verified status without PII exposure

---

## Proof Types

### 1. Sanctions Non-Membership Proof

**Proves:** The user's address is NOT on any sanctions list (HMT, OFAC, EU, UN)

**Circuit:** `sanctions_non_membership.circom`
- Uses sorted Merkle tree for non-membership proof
- Proves address falls between two known sanctioned addresses

**Public Inputs:**
- Sanctions list Merkle root
- Current timestamp

**Hidden:**
- User's address (hashed)
- Actual sanctions list contents
- Neighbor addresses in proof

### 2. Risk Range Proof

**Proves:** User's risk score falls within a specific range

**Ranges:**
- **LOW:** 0-39 (standard transactions allowed)
- **MEDIUM:** 40-69 (enhanced monitoring)
- **HIGH:** 70-100 (blocked - no proof generated)

**Circuit:** `risk_range_proof.circom`
- Range proof using comparators
- Oracle signature verification

**Public Inputs:**
- Oracle signature commitment
- User address hash
- Range bounds (min, max)
- Current timestamp

**Hidden:**
- Exact risk score
- Oracle signing secret
- ML feature contributions

### 3. KYC Credential Proof

**Proves:** User has passed KYC verification by an authorized provider

**Circuit:** `kyc_credential.circom`
- Verifies KYC provider authorization
- Checks age requirement (18+)
- Confirms not a PEP
- Validates KYC not expired

**Public Inputs:**
- Provider commitment
- User address hash
- Current timestamp
- Minimum age requirement

**Hidden:**
- User's real name
- Date of birth
- Address / ID numbers
- KYC provider details

---

## Components

### Smart Contract: `AMTTPzkNAF.sol`

```solidity
// Verify and store a proof on-chain
function verifyAndStore(
    ProofType proofType,
    Proof calldata proof,
    uint256[] calldata publicInputs
) external returns (bytes32 proofHash);

// Check if address has valid proof
function hasValidProof(address account, ProofType proofType) external view returns (bool);

// Check full compliance status
function isCompliant(address account) external view returns (
    bool sanctionsProof,
    bool riskProof,
    bool kycProof,
    bool fullyCompliant
);
```

### Integration Contract: `AMTTPCoreZkNAF.sol`

This module integrates zkNAF with AMTTPCore for pre-transfer compliance verification:

```solidity
// Verify a transfer is allowed based on zkNAF proofs
function verifyTransfer(
    address from,
    address to,
    uint256 amount
) external view returns (bool allowed, string memory reason);

// Get compliance status summary for an address
function getComplianceStatus(address account) external view returns (
    bool hasSanctionsProof,
    bool hasRiskProof,
    bool hasKYCProof,
    uint256 maxAllowedTier
);

// Batch verify multiple addresses (for multi-sig, etc.)
function batchVerify(
    address[] calldata addresses,
    ProofType proofType
) external view returns (bool allValid, address[] memory invalidAddresses);
```

**Transfer Tiers:**

| Tier | Max Amount | Sanctions Proof | Risk Proof | KYC Proof |
|------|------------|-----------------|------------|-----------|
| 0 | 1,000 | ✅ Required | ❌ Optional | ❌ Optional |
| 1 | 10,000 | ✅ Required | ✅ Required | ❌ Optional |
| 2 | 100,000 | ✅ Required | ✅ Required | ✅ Required |
| 3 | Unlimited | ✅ Required | ✅ Low Only | ✅ Required |

**Integration with AMTTPCore:**

```solidity
// In AMTTPCore.initiateSwap()
if (address(zkNAFModule) != address(0)) {
    (bool allowed, string memory reason) = zkNAFModule.verifyTransfer(
        msg.sender, 
        _seller, 
        msg.value
    );
    require(allowed, reason);
}
```

### Circom Circuits

Located in `contracts/zknaf/circuits/`:

| Circuit | Purpose | Constraints |
|---------|---------|-------------|
| `sanctions_non_membership.circom` | Sanctions list non-membership | ~50k |
| `risk_range_proof.circom` | Risk score range verification | ~10k |
| `kyc_credential.circom` | KYC status verification | ~15k |

### TypeScript SDK

```typescript
import { ZkNAFService, ProofType } from '@amttp/client-sdk/zknaf';

const zknaf = new ZkNAFService();
await zknaf.connect(rpcUrl, contractAddress);

// Generate sanctions proof
const sanctionsProof = await zknaf.generateSanctionsProof({
  addressToCheck: userAddress,
  sanctionsListRoot: currentRoot,
  // ... Merkle proof data
});

// Submit to chain
const proofHash = await zknaf.submitProofOnChain(signer, sanctionsProof);

// Check compliance status
const status = await zknaf.getComplianceStatus(userAddress);
console.log(status.fullyCompliant); // true/false
```

### Backend Service

**Port:** 8003

**Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/zknaf/health` | GET | Health check |
| `/zknaf/info` | GET | Service info |
| `/zknaf/proof/sanctions` | POST | Generate sanctions proof |
| `/zknaf/proof/risk` | POST | Generate risk range proof |
| `/zknaf/proof/kyc` | POST | Generate KYC proof |
| `/zknaf/proofs/:address` | GET | Get proofs for address |
| `/zknaf/sanctions/check/:address` | GET | Check if address is sanctioned |

### FCA Compliance Endpoints

Added to FCA Compliance API (port 8002):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/compliance/zknaf/records/:address` | GET | Get full proof records (compliance officers only) |
| `/compliance/zknaf/report` | GET | Generate zkNAF compliance report |
| `/compliance/zknaf/export` | POST | Export records for regulatory request |
| `/compliance/zknaf/integrity` | GET | Verify audit chain integrity |

### Flutter UI

Located in `frontend/amttp_app/lib/features/zknaf/`:

- Proof status dashboard
- Generate individual proofs
- Generate all proofs button
- Compliance status indicator
- FCA compliance notice
- How-it-works guide

---

## Trusted Setup

zkNAF uses Groth16 proofs which require a trusted setup ceremony.

### Powers of Tau (Phase 1)

Uses existing Hermez or Perpetual Powers of Tau ceremony.

### Circuit-Specific (Phase 2)

Each circuit requires Phase 2 contributions:

```bash
# Generate initial zkey
snarkjs groth16 setup circuit.r1cs pot_final.ptau circuit_0000.zkey

# Contribute (repeat with multiple participants)
snarkjs zkey contribute circuit_0000.zkey circuit_0001.zkey --name="Contributor 1"

# Export verification key
snarkjs zkey export verificationkey circuit_final.zkey verification_key.json
```

### Ceremony Verification

```bash
# Verify the final zkey
snarkjs zkey verify circuit.r1cs pot_final.ptau circuit_final.zkey
```

---

## Security Considerations

### Proof Validity

- Proofs expire after 24 hours
- Revocation mechanism for compromised proofs
- On-chain timestamp verification

### Oracle Security

- Oracle secrets stored in HSM
- Signature commitment prevents forgery
- Multi-sig for sanctions list updates

### Circuit Security

- Circuits audited for soundness
- Constraint system verified
- No underconstraint vulnerabilities

---

## Integration Guide

### For DeFi Protocols

```solidity
import {AMTTPzkNAF} from "./AMTTPzkNAF.sol";

contract MyDeFiProtocol {
    AMTTPzkNAF public zknaf;
    
    modifier onlyCompliant() {
        (,,,bool compliant) = zknaf.isCompliant(msg.sender);
        require(compliant, "User not compliant");
        _;
    }
    
    function swap(uint256 amount) external onlyCompliant {
        // User has valid ZK proofs
        // Protocol doesn't see their identity or exact risk score
    }
}
```

### For Users

1. Connect wallet to AMTTP dApp
2. Navigate to zkNAF Privacy Proofs page
3. Generate required proofs (sanctions, risk, KYC)
4. Proofs are stored on-chain for 24 hours
5. Interact with privacy-preserving DeFi protocols

---

## Files

| Path | Description |
|------|-------------|
| `contracts/zknaf/AMTTPzkNAF.sol` | Main verifier contract |
| `contracts/zknaf/circuits/*.circom` | Circom circuits |
| `packages/client-sdk/src/zknaf.ts` | TypeScript SDK |
| `backend/oracle-service/src/zknaf/zknaf-service.ts` | Backend API |
| `backend/oracle-service/src/compliance/zknaf-compliance.ts` | FCA integration |
| `frontend/amttp_app/lib/features/zknaf/` | Flutter UI |

---

## Roadmap

### Phase 1 (Current)
- ✅ Circom circuits designed
- ✅ Solidity verifier contract
- ✅ TypeScript SDK
- ✅ Backend service
- ✅ FCA compliance integration
- ✅ Flutter UI

### Phase 2 (Next)
- [ ] Trusted setup ceremony
- [ ] Circuit audit
- [ ] Testnet deployment
- [ ] DeFi protocol integrations

### Phase 3 (Future)
- [ ] Mainnet deployment
- [ ] Additional proof types
- [ ] Cross-chain proof verification
- [ ] Mobile proof generation

---

## References

- [Groth16 Paper](https://eprint.iacr.org/2016/260.pdf)
- [Circom Documentation](https://docs.circom.io/)
- [snarkjs Library](https://github.com/iden3/snarkjs)
- [FCA MLR 2017 Guidance](https://www.fca.org.uk/firms/financial-crime/money-laundering-regulations)
- [FATF Recommendation 16](https://www.fatf-gafi.org/en/topics/fatf-recommendations.html)

---

**Document Version:** 1.0  
**Last Updated:** January 2026  
**Classification:** Technical Documentation
