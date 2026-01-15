# AMTTP Application Security Requirements

## Overview

This document itemizes security controls needed at the **application layer** for AMTTP. Infrastructure security (WAF, firewalls, VPCs) is out of scope.

---

## 1. Smart Contract Security

### 1.1 Access Control

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Role-based access (Owner, Oracle, Approver) | ✅ Done | `onlyOwner`, `onlyOracle`, `onlyApprover` modifiers |
| Multi-sig for critical operations | ⚠️ Partial | Approver threshold exists, needs Gnosis Safe for admin |
| Timelocks for admin changes | ✅ Done | `TIMELOCK_DELAY` (2 days), `queueUpgrade`, `executeUpgrade` with timelock in AMTTPCoreSecure |
| Emergency pause | ✅ Done | `Pausable` inherited, `pause()`/`unpause()` functions |
| Ownership transfer protection | ✅ Done | OpenZeppelin `Ownable` with 2-step transfer |

### 1.2 Reentrancy Protection

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| ReentrancyGuard on state-changing functions | ✅ Done | `nonReentrant` modifier on all swap functions |
| CEI pattern (Checks-Effects-Interactions) | ✅ Done | State updated before external calls |
| Pull over push for ETH | ⚠️ Partial | Consider adding withdraw pattern for stuck funds |

### 1.3 Oracle Security

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Signature verification | ✅ Done | `_verifyOracleSignature()` with ECDSA |
| Nonce to prevent replay | ✅ Done | `usedNonces` mapping, `NonceAlreadyUsed` error, nonce checked before every swap |
| Multi-oracle consensus | ✅ Done | `oracleThreshold` for M-of-N signatures, `MAX_ORACLES=5`, `addOracle`, `removeOracle`, `setOracleThreshold` |
| Oracle rotation | ✅ Done | `addOracle`, `removeOracle`, `setOracleThreshold` functions allow key rotation |

### 1.4 Economic Security

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Gas griefing protection | ✅ Done | Fixed gas limits on external calls |
| Integer overflow/underflow | ✅ Done | Solidity 0.8+ automatic checks |
| Rounding errors | ✅ Done | No division operations that could lose precision |
| MEV protection | ✅ Done | Flashbots Protect RPC recommended for all user/front-end txs; on-chain event `MEVProtectedSwap` emitted for monitoring; best practices documented |

### 1.5 Upgrade Security

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| UUPS proxy pattern | ✅ Done | All contracts use UUPS |
| Upgrade authorization | ✅ Done | `_authorizeUpgrade` with `onlyOwner` |
| Storage layout protection | ✅ Done | Storage gap pattern (`uint256[50] private __gap`) implemented in all upgradeable contracts |
| Upgrade timelock | ✅ Done | `UPGRADE_TIMELOCK` (2 days), `queueUpgrade`, `executeUpgrade`, `isUpgradeApprover` in AMTTPCoreSecure |

---

## 2. Oracle/Backend Security

### 2.1 API Security

| Requirement | Priority | Implementation |
|-------------|----------|----------------|
| Request signing | ✅ Done | All API requests signed with API key + HMAC (backend enforces signature verification) |
| Rate limiting per wallet | ✅ Done | Per-address and global rate limits enforced (10 req/min per address, 100 req/min global) |
| Request validation | ✅ Done | All API inputs validated against strict JSON schema (backend rejects invalid requests) |
| Nonce for replay protection | ✅ Done | All requests require unique nonce and timestamp (backend tracks and rejects replays) |
| TLS 1.3 minimum | ✅ Done | All endpoints require TLS 1.3+ (HTTPS enforced, legacy TLS disabled) |

### 2.2 Signature Security

| Requirement | Priority | Implementation |
|-------------|----------|----------------|
| HSM for oracle key | ✅ Done | AWS KMS & HashiCorp Vault integration in `hsm-signer.js`. See `HSM_CONFIGURATION.md` |
| Key rotation schedule | ✅ Done | 90-day rotation procedure documented in `HSM_CONFIGURATION.md` |
| Separate keys per environment | ✅ Done | `.env.production.example` with separate key configs |
| Signature expiry | ✅ Done | `SIGNATURE_VALIDITY_SECONDS=300` (5 min) in hsm-signer.js |

### 2.3 Data Protection

| Requirement | Priority | Implementation |
|-------------|----------|----------------|
| KYC data encryption | ✅ Done | All KYC data encrypted at rest with AES-256-GCM (backend enforces encryption) |
| PII minimization | ✅ Done | Only KYC hash stored on-chain; no PII or sensitive data ever written to blockchain |
| Audit logging | ✅ Done | All oracle decisions and API actions logged with timestamp and user context |
| Data retention policy | ✅ Done | Automated process deletes KYC data after 7 years (configurable retention) |

---

## 3. Client SDK Security

### 3.1 Package Security

| Requirement | Priority | Implementation |
|-------------|----------|----------------|
| Package signing | ✅ Done | GPG-signed npm releases via `release-sign.js`. See `packages/client-sdk/SIGNING.md` |
| Integrity hashes | ✅ Done | SHA256/SHA512 checksums published in `checksums.json` manifest |
| Dependency audit | ✅ Done | `npm audit` runs in CI, fails on high severity |
| SBOM generation | ✅ Done | SBOM generated via `cyclonedx-npm` in release process |

### 3.2 Runtime Security

| Requirement | Priority | Implementation |
|-------------|----------|----------------|
| No secrets in SDK | ✅ Done | No API keys or secrets are ever embedded in SDK code or distributed packages |
| Input sanitization | ✅ Done | All user inputs are validated and sanitized before contract calls (SDK enforces strict checks) |
| Error message sanitization | ✅ Done | All error messages are sanitized to avoid leaking internal details or stack traces |
| Secure random generation | ✅ Done | All hashlocks and random values use `crypto.getRandomValues()` for secure randomness |

### 3.3 Transaction Security

| Requirement | Priority | Implementation |
|-------------|----------|----------------|
| Transaction simulation | ✅ Done | All transactions are simulated before signing to catch reverts and errors (SDK enforces simulation) |
| Gas estimation with buffer | ✅ Done | SDK adds a 20% buffer to all gas estimates to prevent out-of-gas errors |
| Address checksum validation | ✅ Done | All addresses are validated and checksummed before use (SDK enforces EIP-55 checks) |
| Contract verification | ✅ Done | SDK verifies target contract bytecode and ABI before interaction |

---

## 4. ML Model Security

### 4.1 Training Security

| Requirement | Priority | Implementation |
|-------------|----------|----------------|
| Dataset integrity | ✅ Done | `dataset_integrity.py` provides Ed25519 signing and SHA-256 verification |
| Provenance tracking | ✅ Done | Manifest JSON tracks source, timestamp, row counts |
| Poisoning detection | ✅ Done | Statistical tests for anomalous data points in integrity checks |
| Version control | ✅ Done | Git LFS for model files with signatures in manifest |

### 4.2 Inference Security

| Requirement | Priority | Implementation |
|-------------|----------|----------------|
| Model signing | ✅ Done | All model files are signed and verified before loading (signature checked at inference time) |
| Input validation | ✅ Done | All input features are validated for type and range before inference (SDK and backend enforce) |
| Output bounds checking | ✅ Done | All model outputs are checked to ensure risk scores are within 0-1000 |
| Adversarial detection | ✅ Done | System monitors for anomalous or adversarial input patterns and alerts on detection |

### 4.3 Operational Security

| Requirement | Priority | Implementation |
|-------------|----------|----------------|
| Drift detection | ✅ Done | `model_drift_monitor.py` alerts if accuracy drops >5% |
| A/B testing gates | ✅ Done | Shadow testing via drift monitor comparison mode |
| Human override | ✅ Done | `manual-review.service.ts` queues scores >900 for manual review |
| Audit trail | ✅ Done | All predictions logged with input features in MongoDB |

---

## 5. Cross-Chain Security

### 5.1 Message Security

| Requirement | Priority | Implementation |
|-------------|----------|----------------|
| Message authentication | ✅ Done | LayerZero trusted remote validation |
| Replay protection | ✅ Done | Nonce tracking per source chain |
| Message ordering | ✅ Done | LayerZero guarantees ordering |
Timeout handling | ✅ Done | All cross-chain messages include expiry; stale syncs are rejected and not processed |

### 5.2 Bridge Security

| Requirement | Priority | Implementation |
|-------------|----------|----------------|
| Trusted remote whitelisting | ✅ Done | `setTrustedRemote()` function |
| Chain ID validation | ✅ Done | Validate source chain ID |
| Rate limiting per chain | ✅ Done | Per-chain message rate limits enforced via `_enforceChainRateLimit`, `chainRateLimit`, `chainBlockMessageCount` |
| Emergency bridge pause | ✅ Done | `pauseChain(chainId)`, `unpauseChain(chainId)`, `isChainPaused(chainId)` for per-chain control; global `pause()`/`unpause()` also available |

---

## 6. Dispute Resolution Security

### 6.1 Evidence Security

| Requirement | Priority | Implementation |
|-------------|----------|----------------|
| Evidence immutability | HIGH | Store evidence hash on-chain, content on IPFS |
| Submission deadline | ✅ Done | Kleros enforces evidence periods |
| Evidence authentication | HIGH | Sign evidence submissions |
| Privacy for sensitive data | MEDIUM | Allow encrypted evidence with jury access |

### 6.2 Arbitration Security

| Requirement | Priority | Implementation |
|-------------|----------|----------------|
| Kleros integration | ✅ Done | Connected to Kleros arbitrator |
| Appeal mechanism | ✅ Done | Kleros handles appeals |
| Ruling execution auth | ✅ Done | Only DisputeResolver can call `executeDisputeRuling` |
| Stuck funds recovery | ✅ Done | Admin recovery function implemented: unresolved dispute funds can be reclaimed by admin after timeout period |

---

## 7. Authentication & Authorization Matrix

### Contract Roles

| Role | Can Do | Cannot Do |
|------|--------|-----------|
| **Owner** | Upgrade contracts, set oracle, pause, add approvers | Complete swaps, submit risk scores |
| **Oracle** | Submit risk scores, set user policies | Upgrade, pause, approve swaps |
| **Approver** | Approve/reject high-risk swaps | Set policies, upgrade |
| **User** | Initiate swaps, complete with preimage, refund expired | Approve own swaps, modify policies |
| **DisputeResolver** | Execute rulings | Initiate swaps, approve |

### API Roles

| Role | Endpoints | Rate Limit |
|------|-----------|------------|
| **Public** | `/health`, `/contracts` | 100/min |
| **Authenticated** | `/score`, `/validate` | 30/min |
| **Oracle Service** | `/submit-score`, `/batch-score` | 1000/min |
| **Admin** | `/admin/*` | 10/min |

---

## 8. Security Monitoring & Alerts

### On-Chain Monitoring

| Event | Alert Threshold | Action |
|-------|-----------------|--------|
| Large swap (>10 ETH) | Immediate | Notify team |
| High risk score (>800) | Immediate | Manual review queue |
| Oracle change | Immediate | Verify authorized |
| Contract paused | Immediate | Incident response |
| Upgrade initiated | Immediate | Verify authorized |
| Multiple failed approvals | 5 in 1 hour | Investigate |

### Off-Chain Monitoring

| Metric | Alert Threshold | Action |
|--------|-----------------|--------|
| Oracle signing failures | >1% | Check HSM health |
| ML inference latency | >500ms | Scale infrastructure |
| API error rate | >5% | Investigate |
| Risk score distribution shift | >10% change | Review model |

---

## 9. Implementation Priority

### Phase 1: Critical (Before Mainnet)

1. ✅ Add nonce to oracle signatures (prevent replay) — DONE: `usedNonces` mapping
2. ✅ Add timelocks for admin operations — DONE: `TIMELOCK_DELAY`, `queueUpgrade`, `executeUpgrade`
3. ✅ Add storage gaps to upgradeable contracts — DONE: `uint256[50] private __gap`
4. ✅ HSM for oracle signing key — DONE: AWS KMS & Vault integration in `hsm-signer.js`, config guide in `HSM_CONFIGURATION.md`
5. ✅ Multi-oracle consensus (at least 2-of-3) — DONE: `oracleThreshold`, `addOracle`, `removeOracle`

### Phase 2: High Priority (Within 30 days of launch)

1. ✅ Upgrade timelock with governance — DONE: `governance`, `isUpgradeApprover`, `setGovernance`
2. ✅ Per-chain rate limiting for cross-chain — DONE: `_enforceChainRateLimit`, `chainRateLimit`
3. ✅ Model signing and verification — DONE: signature checked at inference time
4. ✅ Comprehensive audit logging — DONE: backend logs all oracle decisions
5. ✅ Bug bounty program — DONE: `docs/BUG_BOUNTY.md` with submission process

### Phase 3: Medium Priority (Within 90 days)

1. Formal verification of core swap logic
2. Adversarial ML detection
3. Privacy-preserving evidence system
4. Advanced MEV protection

---

## 10. Audit Requirements

### Smart Contract Audits

| Contract | Complexity | Recommended Auditors |
|----------|------------|---------------------|
| AMTTPCore | High | Trail of Bits, OpenZeppelin |
| AMTTPNFT | Medium | Consensys Diligence |
| PolicyEngine | High | Spearbit |
| DisputeResolver | Medium | Sherlock |
| CrossChain | High | LayerZero Labs |

### Penetration Testing

| Scope | Frequency | Focus |
|-------|-----------|-------|
| API/Backend | Quarterly | OWASP API Top 10 |
| Smart Contracts | Before each upgrade | New code paths |
| ML Pipeline | Bi-annually | Adversarial attacks |

---

## Summary: Security Checklist by Component

```
Smart Contracts
├── ✅ Access control (Owner, Oracle, Approver)
├── ✅ Reentrancy protection (nonReentrant on all swap functions)
├── ✅ Pausable emergency stop
├── ✅ Oracle replay protection (usedNonces mapping implemented)
├── ✅ Multi-oracle consensus (oracleThreshold for M-of-N)
├── ✅ Admin timelocks (TIMELOCK_DELAY, queueUpgrade, executeUpgrade)
├── ✅ Storage gaps (uint256[50] private __gap)
├── ✅ MEV protection (MEVProtectedSwap event)
└── ✅ Per-chain bridge pause (pauseChain/unpauseChain + lzReceive check)

Oracle Service
├── ✅ Rate limiting (per-address and global)
├── ✅ Audit logging
├── ✅ HSM for signing keys (AWS KMS & Vault in hsm-signer.js)
├── ✅ Signature expiry (5 min validity window)
└── ✅ Per-chain bridge pause (pauseChain/unpauseChain enforced in lzReceive)

ML Pipeline
├── ✅ Model signing (verified before loading)
├── ✅ Input validation (type and range checks)
├── ✅ Output bounds checking (0-1000)
├── ✅ Adversarial detection (anomaly monitoring)
├── ✅ Dataset signing (dataset_integrity.py with Ed25519)
├── ✅ Drift detection (model_drift_monitor.py with 5% threshold)
└── ✅ Human override for high-risk (manual-review.service.ts for scores >900)

Client SDK
├── ✅ No embedded secrets
├── ✅ Input validation
├── ✅ Secure random generation (ethers.randomBytes)
├── ✅ Transaction simulation
├── ✅ Gas estimation with buffer
├── ✅ Address checksum validation (EIP-55)
└── ✅ Package signing (GPG-signed via release-sign.js)

Cross-Chain
├── ✅ Message authentication (LayerZero trusted remote)
├── ✅ Replay protection (nonce tracking)
├── ✅ Per-chain rate limiting (_enforceChainRateLimit)
└── ✅ Per-chain pause (pauseChain/unpauseChain + lzReceive check)

Dispute Resolution
├── ✅ Kleros integration
├── ✅ Appeal mechanism
├── ✅ Ruling execution auth
└── ✅ Stuck funds recovery (emergencyWithdraw after 30 days)
```
