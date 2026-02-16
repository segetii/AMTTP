# AMTTP — Full Product Architecture

## Technology Provider View — With Tools & Security Embedded

**Version:** 2.2  
**Date:** January 2026  
**Classification:** Technical Whitepaper / Regulator Pack / Due Diligence  
**Last Updated:** Production Explainability Module

---

## Executive Summary

AMTTP (Anti-Money Laundering Transaction Trust Protocol) is a **transaction trust and enforcement protocol** that embeds security directly into protocol logic. Unlike traditional fraud APIs, blockchain monitors, or compliance dashboards, AMTTP provides:

- **Stacked Ensemble ML** (GraphSAGE + LGBM + XGBoost + Linear Meta-Learner) directly controlling execution
- **VAE latent features** + **Graph embeddings** for advanced anomaly detection
- **KYC, disputes, ML, and contracts** as one cohesive system
- **Security as protocol logic**, not infrastructure

---

## 🔍 EVIDENCE & CONTROLS INDEX

This section maps each architectural claim to verifiable artifacts for audit/regulatory review.

| Claim | Evidence Location | Verification Method | Maturity |
|-------|-------------------|---------------------|----------|
| "ROC-AUC ~0.94" | `notebooks/vae_gnn_pipeline.ipynb` (Step 10 output) | Time-based test set (days 27-30), address-holdout | ✅ Validated |
| "<50ms P99 latency" | `/monitoring/metrics` endpoint (design target) | Prometheus histogram `risk_score_duration_ms_p99` | 🔶 Target |
| "Ed25519 signatures on all risk scores" | `backend/oracle-service/src/` (signer modules) | Verify with public key in contract `PolicyEngine.oraclePublicKey()` | 🔶 Implemented |
| "IPFS audit logs" | `backend/compliance-service/storage.py` (Helia client) | CID retrieval via IPFS gateway + hash verification | 🔶 Implemented |
| "Merkle tree training batches" | Design spec (provenance system) | Recompute from batch hashes when implemented | 🔷 Planned |
| "6 AML rules" | `backend/compliance-service/monitoring_rules.py` (lines 1-90) | Rule trigger logs in MongoDB `alerts` collection | ✅ Implemented |
| "Emergency pause" | `contracts/AMTTPPolicyEngine.sol` (line 526) | Test `test/foundry/AMTTPPolicyEngine.fuzz.t.sol` | ✅ Implemented |
| "Nonce replay protection" | `client-sdk/src/` + Redis backend design | Check nonce uniqueness in SDK signing flow | 🔶 Implemented |
| "K-Fold cross-validation" | `notebooks/vae_gnn_pipeline.ipynb` (Steps 8-9) | 5-fold stratified split visible in notebook outputs | ✅ Validated |

**Maturity Legend:**
- ✅ **Validated** – Implemented and tested with evidence in repo
- 🔶 **Implemented** – Code exists, requires operational verification
- 🔷 **Planned** – Design spec exists, implementation pending

**Audit Instructions:**
- All ML metrics measured on Ethereum mainnet data (from BigQuery `crypto_ethereum.transactions`)
- Test set: time-ordered split (last 4 days), address-holdout via `GroupShuffleSplit`
- Training notebooks: `notebooks/vae_gnn_pipeline.ipynb` (production), `Hope_machine` variations (baseline XGB only)
- Address leakage check: 0% train/test overlap enforced via `sklearn.model_selection.GroupShuffleSplit`

---

## 🌐 1. USER, CUSTOMER & PARTNER INTERFACES (UNTRUSTED ZONE)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        🌐 USER & PARTNER INTERFACES                          │
├──────────────────────────────────────────────────────────────────────────────┤
│ 📱 Flutter Web App    │ 🖥 Next.js SIEM       │ 🔗 Partner Integrations       │
│ (Port 80 - /)         │ (Port 80 - /siem/)   │                               │
│ - WalletConnect       │ - Risk dashboards     │ - Exchanges / PSPs            │
│ - Transfer UI         │ - Compliance View     │ - Custodians                  │
│ - Detection Studio    │ - SIEM Monitoring     │ - DeFi protocols              │
│   (iframe embed)      │ - Entity Investigation│ - AML vendors                 │
└───────────────┬───────────────────┬───────────────────┬──────────────────────┘
                │                   │                   │
                ▼                   ▼                   ▼
```

### 🔐 Embedded Security

| Control | Implementation |
|---------|----------------|
| Wallet Authentication | Cryptographic signature verification (EIP-712) |
| Replay Protection | **Server-enforced nonce + TTL + idempotency** (Redis storage, 300s TTL) |
| Request Integrity | Deterministic request signing via SDK |
| Iframe Security | CSP headers, X-Frame-Options configured for embedding |

---

## 📦 2. AMTTP CLIENT SDK LAYER (PRODUCT DISTRIBUTION)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           📦 AMTTP CLIENT SDK                                │
├──────────────────────────────────────────────────────────────────────────────┤
│ TypeScript SDK (~257 KB, versioned, signed)                                  │
│                                                                              │
│ ├── AMTTPClient.ts        – Identity binding, signing                        │
│ ├── TransactionService    – Secure tx orchestration                         │
│ ├── RiskService           – Stacked ensemble ML scoring                      │
│ ├── PolicyService         – Fetch & enforce policies                         │
│ ├── CrossChainService     – LayerZero cross-chain safety                     │
│ ├── AtomicSwapService     – Cross-chain safety logic                         │
│ └── TelemetryClient       – Risk & decision telemetry                        │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 🔐 Embedded Security

| Control | Implementation |
|---------|----------------|
| SDK Integrity | NPM package signing, checksum verification |
| Secure Defaults | Strict mode enabled, no unsafe operations |
| Version Pinning | Lockfile enforcement, downgrade attack prevention |
| MEV Protection | Private mempool submission support |

### 🔐 Nonce + Signature Scheme

| Component | Implementation |
|-----------|----------------|
| **Nonce Generation** | Client-side: `keccak256(timestamp + random_bytes(32))` |
| **Server Enforcement** | Redis: `SETNX used_nonces:{address}:{nonce} 1 EX 300` (5 min TTL) |
| **Signature Scope** | `sign(keccak256(nonce ‖ from ‖ to ‖ amount ‖ chain_id ‖ timestamp))` |
| **Timestamp Validity** | Server rejects if `|server_time - request_timestamp| > 60s` |
| **Key Rotation** | Ed25519 oracle key rotated every 90 days, old keys valid for 7 days |
| **Signature Verification** | Client SDK verifies oracle response signature before enforcing |

**Canonical Signing Format (EIP-712 style):**
```typescript
// filepath: client-sdk/src/signing.ts
const domain = {
  name: 'AMTTP Risk Oracle',
  version: '2.1',
  chainId: chainId,
  verifyingContract: policyEngineAddress
};

const types = {
  RiskRequest: [
    { name: 'nonce', type: 'bytes32' },
    { name: 'from', type: 'address' },
    { name: 'to', type: 'address' },
    { name: 'amount', type: 'uint256' },
    { name: 'timestamp', type: 'uint256' }
  ]
};

const signature = await wallet._signTypedData(domain, types, request);
```

### SDK Location

```
client-sdk/
├── src/
│   ├── client.ts           # Main AMTTP client
│   ├── risk.ts             # Risk scoring service
│   ├── policy.ts           # Policy management
│   ├── crosschain.ts       # LayerZero integration
│   ├── signing.ts          # EIP-712 signature utilities
│   └── abi.ts              # Contract ABIs
├── MEV_PROTECTION.md       # MEV protection documentation
└── package.json
```

---

## 🔙 3. AMTTP ORACLE & CONTROL PLANE (CORE PRODUCT)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                      🔙 AMTTP ORACLE & CONTROL PLANE                         │
├──────────────────────────────────────────────────────────────────────────────┤
│ Runtime: Python (FastAPI) / Node.js                                          │
│                                                                              │
│ 🎯 Risk & Decision APIs                                                      │
│  ├── /risk/score            → Stacked ensemble ML inference                  │
│  ├── /risk/hybrid           → GraphSAGE + LGBM + XGBoost ensemble           │
│  ├── /tx/validate           → Pre-onchain enforcement                        │
│  ├── /label/submit          → Analyst / system labels                        │
│                                                                              │
│ 🔍 Identity, KYC & Compliance Integrations                                   │
│  - Sumsub         → KYC / KYB / identity proofing                            │
│  - Kleros         → Decentralized dispute resolution                         │
│                                                                              │
│ 📋 Backend Services (via NGINX Reverse Proxy)                                │
│  ├── /api/          → Orchestrator (8007) - Profile mgmt, tx evaluation     │
│  ├── /risk/         → Risk Engine (8000) - ML scoring                        │
│  ├── /sanctions/    → Sanctions (8004) - OFAC/HMT/EU/UN screening           │
│  ├── /monitoring/   → Monitoring (8005) - 6 AML rules, alerts               │
│  ├── /geo/          → Geo Risk (8006) - FATF country risk                   │
│  └── /integrity/    → Integrity (8008) - UI verification, tamper detection  │
│                                                                              │
│ 🗄 Core Data Stores                                                          │
│  - MongoDB        → User metadata, profiles, transaction logs                │
│  - MinIO          → Models, features, evidence, artifacts                    │
│  - IPFS (Helia)   → Immutable audit & decision logs                          │
│  - Memgraph       → Real-time graph analytics (PageRank, clustering)         │
│  - Redis          → Session cache, rate limiting, nonce storage              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 🔐 Embedded Security

| Control | Implementation |
|---------|----------------|
| Oracle Response Signing | Ed25519 signatures on all risk scores |
| Tamper-Evident Audit | IPFS content-addressed storage |
| Deterministic Schemas | OpenAPI 3.0 strict validation |
| Trust Scoring | Confidence intervals on all ML outputs |

---

## 📝 EXPLAINABILITY SYSTEM

AMTTP provides **human-readable explanations** for every risk decision, not raw model scores.

### Problem: Raw Scores Are Meaningless

❌ **What analysts DON'T need:**
```json
{
  "risk_score": 0.73,
  "xgb_prob": 0.71,
  "vae_recon_error": 2.1,
  "sage_prob": 0.68
}
```

✅ **What analysts NEED:**
```json
{
  "risk_score": 0.73,
  "action": "ESCROW",
  "summary": "Transaction held in escrow - layering pattern detected",
  "top_reasons": [
    "Transaction amount ($847K) is 12x larger than sender's 30-day average",
    "Recipient has received funds from sanctioned addresses (2 hops away)",
    "Account was dormant for 190 days before this activity",
    "Complex transaction chain detected with 4 hops"
  ],
  "typology_matches": [
    {"typology": "layering", "confidence": 0.85, "indicators": ["4-hop chain", "rapid movement"]}
  ],
  "recommendations": [
    "Trace full transaction chain origin",
    "Request additional KYC documentation"
  ]
}
```

### Explanation Pipeline

```
Raw Features → Feature Explainer → Human-Readable Factors
                    ↓
Graph Context → Typology Matcher → Pattern Matches
                    ↓
Rule Results → Reason Generator → Top Reasons + Summary
                    ↓
                Recommendation Engine → Actionable Next Steps
```

### Feature-to-Explanation Mapping

| Raw Feature | Human Explanation |
|-------------|-------------------|
| `amount_vs_average > 10` | "Transaction is 12x larger than sender's 30-day average" |
| `hops_to_sanctioned = 2` | "Recipient has received funds from sanctioned addresses (2 hops away)" |
| `dormancy_days = 190` | "Account was dormant for 190 days before this activity" |
| `vae_recon_error > 2.0` | "Transaction pattern is highly unusual compared to normal behavior" |
| `pagerank > 0.001` | "Address has unusually high network influence" |
| `clustering_coef > 0.8` | "Address is part of a tightly connected cluster" |

### Typology Detection

The system matches transactions against known AML/fraud typologies:

| Typology | Detection Method | Example Indicator |
|----------|------------------|-------------------|
| **Structuring** | Multiple txs < threshold | "3 transactions totaling 29.5 ETH (< 10 ETH each)" |
| **Layering** | Multi-hop rapid chains | "4-hop chain with value preserved within 2 hours" |
| **Round-trip** | Funds return to origin | "847 ETH sent, 820 ETH returned via 2 intermediaries" |
| **Fan-out** | One sender → many recipients | "Distributed to 47 unique addresses in 24h" |
| **Fan-in** | Many senders → one recipient | "Aggregated from 125 unique addresses in 24h" |
| **Dormant Activation** | Long inactivity then activity | "Account inactive 190 days, now high activity" |
| **Mixer Interaction** | Proximity to mixers | "2 hops from known Tornado Cash deposit" |
| **Sanctions Proximity** | Graph distance to sanctioned | "Direct transaction with OFAC-listed address" |

### Analyst Recommendations

Based on action and typology, the system generates actionable recommendations:

| Action | Typology | Recommendation |
|--------|----------|----------------|
| BLOCK | Any | "File SAR within 24 hours", "Preserve evidence" |
| ESCROW | Layering | "Trace full transaction chain origin" |
| REVIEW | Structuring | "Check for additional structured transactions" |
| REVIEW | Mixer | "Flag all related addresses for enhanced monitoring" |

### Implementation

| Component | Location | Purpose |
|-----------|----------|---------|
| **Production Explainability Module** | `backend/oracle-service/src/risk/explainability/` | Full production system |
| TypeScript Types | `backend/oracle-service/src/risk/explainability/types.ts` | Type definitions for all interfaces |
| Configuration | `backend/oracle-service/src/risk/explainability/config.ts` | Configurable thresholds, templates |
| Templates | `backend/oracle-service/src/risk/explainability/templates.ts` | Feature-to-human-readable mapping |
| Typologies | `backend/oracle-service/src/risk/explainability/typologies.ts` | AML pattern detection |
| Explainer | `backend/oracle-service/src/risk/explainability/explainer.ts` | Core explanation engine |
| Service | `backend/oracle-service/src/risk/explainability/service.ts` | Production service with caching, metrics |
| Metrics | `backend/oracle-service/src/risk/explainability/metrics.ts` | Prometheus metrics, structured logging |
| Tests | `backend/oracle-service/src/risk/explainability/explainability.test.ts` | 27 unit tests |
| Python Explainer | `backend/compliance-service/explainability.py` | Python version for ML pipeline |
| Risk Service | `backend/oracle-service/src/risk/risk.service.ts` | `scoreRiskWithExplanation()` integration |

### Production Features

| Feature | Description | Status |
|---------|-------------|--------|
| **LRU Cache** | TTL-based caching with configurable size | ✅ Implemented |
| **Circuit Breaker** | Graceful degradation under failure | ✅ Implemented |
| **Prometheus Metrics** | `/metrics` endpoint with counters, histograms | ✅ Implemented |
| **Structured Logging** | JSON logs with PII redaction | ✅ Implemented |
| **Configurable Thresholds** | Environment-based configuration | ✅ Implemented |
| **Regulatory References** | FATF, FCA, OFAC references in explanations | ✅ Implemented |
| **SAR Narratives** | Pre-written SAR text for each typology | ✅ Implemented |
| **27 Unit Tests** | Full test coverage | ✅ Passing |

---

### Backend Service Architecture

| Service | Runtime | Port | Auth | Datastores | SLA | Maturity |
|---------|---------|------|------|------------|-----|----------|
| Orchestrator | Python 3.11 (FastAPI) | 8007 | JWT + IP whitelist | MongoDB, Redis | Target: 99.9% uptime | 🔶 Implemented |
| Risk Engine | Python 3.11 (FastAPI) | 8000 | API key + rate limit | MinIO (models), Redis (cache), Memgraph | Target: <50ms P99 | 🔶 Implemented |
| Sanctions | Python 3.11 (FastAPI) | 8004 | API key | MongoDB (OFAC lists), Redis | Target: <20ms P99 | ✅ Production |
| Monitoring | Python 3.11 (FastAPI) | 8005 | API key | MongoDB (alerts), Redis | Target: 99.5% uptime | ✅ Production |
| Geo Risk | Python 3.11 (FastAPI) | 8006 | API key | MongoDB (FATF data) | Target: <10ms P99 | ✅ Production |
| Integrity | Node.js 20 (Express) | 8008 | HMAC signature | Redis, IPFS (Helia) | Target: 99.9% uptime | 🔶 Implemented |
| SIEM Dashboard | Next.js 15.5.3 | 3005 | OAuth2 (internal only) | MongoDB (read replica) | Internal tool | ✅ Production |

> **Note:** SLA values are *design targets*. Production SLA verification requires operational monitoring dashboards (Prometheus/Grafana). Actual measured latencies may vary based on deployment environment.

**Internal Auth Flow:**
1. NGINX terminates TLS, extracts JWT from `Authorization: Bearer` header
2. Validates JWT signature (RS256, public key in Redis)
3. Forwards to backend with `X-User-Id` and `X-Roles` headers
4. Backend services trust NGINX-injected headers (network policy enforced)

**Rate Limiting (NGINX + Redis):**
- `/risk/score`: 100 req/min per API key
- `/sanctions/check`: 500 req/min per API key
- Burst: 2x limit for 10 seconds
- Exceeded: HTTP 429 with `Retry-After` header

### API Endpoints (Production via NGINX)

| Route | Backend Service | Port | Purpose |
|-------|-----------------|------|---------|
| `/api/` | Orchestrator | 8007 | Profile management, compliance decisions |
| `/risk/` | Risk Engine | 8000 | Stacked ensemble ML scoring |
| `/sanctions/` | Sanctions | 8004 | OFAC, HMT, EU, UN screening |
| `/monitoring/` | Monitoring | 8005 | 6 AML rules, alert management |
| `/geo/` | Geo Risk | 8006 | FATF country risk assessment |
| `/integrity/` | Integrity | 8008 | UI verification, tamper detection |
| `/siem/` | Next.js | 3005 | SIEM dashboard (internal port) |

---

## 🧠 4. FRAUD INTELLIGENCE, GRAPH & ML STACK (CORE DIFFERENTIATOR)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    🧠 FRAUD INTELLIGENCE & ML STACK                          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ 📊 Feature Engineering                                                       │
│  - Amount normalization (log transform)                                      │
│  - Velocity / burst detection                                                │
│  - Temporal spacing analysis                                                 │
│  - Gas price anomaly detection                                               │
│  - Contract interaction patterns                                             │
│  - Sender statistics (total_sent, total_received, sophisticated_score)       │
│                                                                              │
│ 🌐 Graph Intelligence (Memgraph)                                             │
│  - In-degree / out-degree ratio                                              │
│  - PageRank for address importance                                           │
│  - Clustering coefficient                                                    │
│  - Betweenness centrality                                                    │
│  - Hop-distance to known bad actors                                          │
│  - Layering / peeling chain detection                                        │
│                                                                              │
│ 🤖 Machine Learning Pipeline (Two-Notebook System)                            │
│  ┌─────────────────────────────────────────────────────────────────┐         │
│  │ Notebook 1: Hope_machine(4).ipynb - Weak Labeling Only          │         │
│  │  - Training: Kaggle ETH Fraud Dataset (labeled)                 │         │
│  │  - Model: XGBoost v1 (baseline for pseudo-labeling)             │         │
│  │  - Output: Pseudo-labels for unlabeled ETH data                 │         │
│  │  - Note: ONLY XGBoost used; other models (SAINT, RNN,           │         │
│  │          Wide&Deep, LGBM, CatBoost) are exploratory             │         │
│  └─────────────────────────────────────────────────────────────────┘         │
│  ┌─────────────────────────────────────────────────────────────────┐         │
│  │ Notebook 2: vae_gnn_pipeline(2).ipynb - Production Pipeline     │         │
│  │  STAGE 1: Data Prep (Steps 1-3)                                │         │
│  │   - Load 1.7M Ethereum transactions                             │         │
│  │   - Preprocessing: log1p → RobustScaler → clip outliers         │         │
│  │   - Build transaction graph (from/to edges)                     │         │
│  │                                                                 │         │
│  │  STAGE 2: Unsupervised Feature Extraction (Steps 4-5)          │         │
│  │   - β-VAE: Latent z (64D) + recon_error (anomaly score)        │         │
│  │   - VGAE: Graph z (32D) + edge_recon_score                     │         │
│  │                                                                 │         │
│  │  STAGE 3: Supervised GNN (Steps 6-7)                           │         │
│  │   - GATv2: Attention-based GNN → gat_prob + uncertainty        │         │
│  │   - GraphSAGE-Large: High-capacity aggregation → sage_prob     │         │
│  │                                                                 │         │
│  │  STAGE 4: Gradient Boosting (Steps 8-9)                        │         │
│  │   - XGBoost v2 (5-Fold CV, GPU) → xgb_oof                      │         │
│  │   - LightGBM (5-Fold CV, CPU) → lgb_oof                        │         │
│  │                                                                 │         │
│  │  STAGE 5: Meta-Ensemble (Step 10)                              │         │
│  │   - Logistic Regression stacking of 7 features:                │         │
│  │     1. recon_error (VAE)  2. edge_recon (VGAE)                 │         │
│  │     3. gat_prob (GATv2)   4. gat_uncertainty                   │         │
│  │     5. sage_prob (SAGE)   6. xgb_oof   7. lgb_oof              │         │
│  │   - Output: meta_prob (final fraud probability)                │         │
│  └─────────────────────────────────────────────────────────────────┘         │
│                                                                              │
│ 📈 Model Ops                                                                 │
│  - MLflow → model registry & lineage                                         │
│  - Feature versioning (VAE latent, GraphSAGE embeddings)                     │
│  - Drift & reward monitoring                                                 │
│  - K-Fold cross-validation (5-fold for XGBoost/LGBM)                        │
│  - GPU acceleration (CUDA, cuML when available)                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 🧩 WHY THIS COMPLEXITY EXISTS

The multi-stage architecture is intentional. Each component addresses a distinct failure mode:

| Component | What It Catches | Ablation Impact | Remove First If... |
|-----------|-----------------|-----------------|---------------------|
| **β-VAE** | Novel transaction patterns (OOD detection) | -0.02 AUC | Latency-constrained deployment |
| **VGAE** | Anomalous graph structure (missing edges) | -0.01 AUC | Graph data unavailable |
| **GATv2** | Local neighborhood patterns | -0.03 AUC | Graph construction fails |
| **GraphSAGE** | Multi-hop propagation patterns | -0.04 AUC | Need tabular-only fallback |
| **XGBoost v2** | Tabular feature interactions | -0.06 AUC | Never (core model) |
| **LightGBM** | Diverse gradient boosting ensemble | -0.02 AUC | Compute-constrained |
| **Meta-Learner** | Model disagreement signals | -0.01 AUC | Single-model deployment |

**Degradation Priority (remove in this order):**
1. VGAE (least impact, most graph-dependent)
2. β-VAE (unsupervised, can be slow)
3. GATv2 (redundant with GraphSAGE)
4. LightGBM (redundant with XGBoost)
5. GraphSAGE (significant impact – triggers tabular-only mode)
6. XGBoost v2 (never remove – core production model)

**Monitoring per component:**
- Each model outputs a probability + uncertainty estimate
- Ensemble disagreement (std across models) triggers manual review
- Individual model drift monitored separately via KL divergence

### Real-Time Inference Architecture (<50ms Target)

```
Client Request
    ↓
[SDK] Nonce + Signature
    ↓
[NGINX] → /risk/score
    ↓
[FastAPI Risk Engine]
    ├─→ Redis: Fetch cached embeddings (GraphSAGE, VGAE) ← precomputed hourly
    ├─→ Compute: Tabular features (amount_log, gas_anomaly, velocity) ← on-demand
    ├─→ Memgraph: Fetch graph props (pagerank, degree) ← indexed query <5ms
    ├─→ Model: XGBoost.predict(features + embeddings) ← GPU inference <10ms
    ├─→ Model: LGBM.predict(...) ← CPU inference <8ms
    ├─→ Meta-Learner: LogisticRegression.predict([xgb, lgbm, gat, graphsage]) ← <2ms
    └─→ Sign response with Ed25519 + return {score, confidence_interval}
    ↓
[Client] Verify signature + enforce policy
```

**Latency Budget (P99):**
- Feature computation: 15ms
- Redis embedding fetch: 5ms
- Memgraph query: 5ms
- Model inference: 20ms (GPU XGBoost + LGBM + meta-learner)
- Signature generation: 3ms
- Network overhead: 2ms
- **Total: ~50ms**

**Fallback Behavior (if GraphSAGE embeddings unavailable):**
- Use last known embeddings from Redis (max staleness: 1 hour)
- If Redis miss: fall back to tabular-only model (XGBoost without graph features)
- Flag in response: `"embedding_freshness": "stale"` or `"degraded_mode": true`

**Cache Strategy:**
- GraphSAGE/VGAE embeddings: Precomputed every 60 minutes, stored in Redis

---

### 📋 INFERENCE CONTRACT

This section defines the **exact inputs, outputs, and dependencies** required at inference time.

#### Required Inputs (Tier 0 – Always Available)

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `from_address` | `address` | Sender address | Client SDK |
| `to_address` | `address` | Recipient address | Client SDK |
| `amount` | `uint256` | Transaction value (wei) | Client SDK |
| `chain_id` | `uint256` | Network identifier | Client SDK |
| `timestamp` | `uint256` | Request timestamp (Unix) | Client SDK |
| `nonce` | `bytes32` | Request nonce | Client SDK |
| `signature` | `bytes` | EIP-712 signature | Client SDK |

#### Enriched Features (Tier 1 – Sanctions/Compliance)

| Field | Source Service | Fallback |
|-------|----------------|----------|
| `sanctions_match` | Sanctions Service (8004) | `null` → assume no match |
| `fatf_country_risk` | Geo Risk Service (8006) | `null` → assume "unknown" |
| `kyc_level` | Orchestrator (8007) | `null` → assume "none" |

#### Graph Features (Tier 2 – Graph Intelligence)

| Field | Source | Fallback | Staleness |
|-------|--------|----------|-----------|
| `pagerank` | Memgraph (real-time) | `0.0` (new address) | <10 min |
| `in_degree` | Memgraph (real-time) | `0` | <10 min |
| `out_degree` | Memgraph (real-time) | `0` | <10 min |
| `clustering_coef` | Memgraph (real-time) | `0.0` | <10 min |
| `graphsage_embedding` | Redis (precomputed) | Zeros (64D) | <60 min |
| `vgae_embedding` | Redis (precomputed) | Zeros (32D) | <60 min |

#### Inference Output Schema

```json
{
  "risk_score": 0.73,              // Float [0.0, 1.0]
  "confidence_interval": [0.68, 0.78],
  "action": "ESCROW",              // ALLOW | REVIEW | ESCROW | BLOCK
  "features_used": ["tier0", "tier1", "tier2"],
  "degraded_mode": false,          // True if graph unavailable
  "embedding_freshness": "fresh",  // "fresh" | "stale" | "missing"
  "model_version": "ensemble-v2.0",
  "signature": "0x...",            // Ed25519 signature over response
  "timestamp": 1705312800
}
```

#### Degradation Tiers

| Condition | Behavior | Expected AUC Impact |
|-----------|----------|---------------------|
| Tier 2 unavailable (Memgraph down) | Use cached embeddings or zeros | -0.02 to -0.05 |
| Tier 1 unavailable (Sanctions down) | Skip sanctions features, widen CI | -0.01 |
| All enrichment unavailable | Tabular-only (amount, gas) | -0.08 to -0.12 |

> **Design Note:** The system is designed to **fail closed** – if the oracle cannot score a transaction within the timeout, the smart contract reverts and the transaction is rejected. This is safer than allowing unscored transactions through.
- Memgraph properties: Indexed real-time queries (pagerank updated every 10 min)
- Nonce storage: Redis TTL=300s (5 minutes)

### Label Sources & Training Protocol

**Ground Truth Labels (High Confidence):**
1. **Sanctions Hits** – OFAC/HMT/EU/UN confirmed matches (auto-labeled)
2. **Law Enforcement Reports** – Subpoenaed addresses (manually verified)
3. **Exchange Freezes** – Addresses frozen by CEXs (external data feeds)
4. **Kleros Dispute Outcomes** – Arbitrated fraud cases (on-chain evidence)

**Weak Labels (Medium Confidence):**
1. **AML Rule Triggers** – 6 AML rules (used only for REVIEW/ESCROW, not training)
2. **XGBoost v1 Pseudo-Labels** – From Hope_machine(4).ipynb, confidence > 0.85
3. **Analyst Flags** – Human-submitted reports (subject to validation)

**Two-Notebook Training Flow:**

```
Hope_machine(4).ipynb (Notebook 1):
───────────────────────────────────
Kaggle Labeled Data → XGBoost v1 → Pseudo-Label Unlabeled ETH Data
                                          ↓
                                 (Only high confidence: prob > 0.85 or < 0.15)
                                          ↓
                                 Weakly-Labeled Dataset
                                          ↓
                                          ▼
vae_gnn_pipeline(2).ipynb (Notebook 2):
───────────────────────────────────────
Enriched Data (XGB scores + graph + rules) → Full 10-Step Pipeline
```

**Label Timestamp Protocol:**
- All labels stored with `decision_time` and `event_time`
- Training: Only use labels where `decision_time ≤ train_cutoff_date`
- Test set: Evaluate on labels confirmed *after* model training date
- Example: Model trained on 2025-12-20 can only use labels confirmed by 2025-12-20

**Pseudo-Labeling Controls (Hope_machine):**
- XGBoost v1 predictions used to label unlabeled ETH data
- **Confidence threshold:** Only pseudo-label if `prob > 0.85` or `prob < 0.15`
- **Human review:** Random 10% sample of pseudo-labels reviewed monthly
- **Feedback loop detection:** Monitor label distribution drift (KL divergence < 0.05)
- **Important:** Other models in Hope_machine (SAINT, RNN, Wide&Deep, LGBM, CatBoost) are exploratory only

**Anti-Poisoning:**
- Analyst labels require 2-of-3 approval for training inclusion
- Outlier detection on label submissions (IsolationForest on label features)
- Label versioning: All training sets tagged with `label_snapshot_date`

---

### 🚀 MODEL PROMOTION PIPELINE

This section describes how models move from training to production.

#### Current State (Manual Process)

| Stage | Description | Artifacts | Owner |
|-------|-------------|-----------|-------|
| **1. Training** | Run `vae_gnn_pipeline.ipynb` in Colab/local | Notebook outputs, model files | ML Engineer |
| **2. Export** | Save model artifacts (`.pkl`, `.pt`, ONNX) | `xgboost_v2.pkl`, `lgbm_v2.pkl`, `meta_lr.pkl` | ML Engineer |
| **3. Validation** | Run on held-out test set, check metrics | Metrics JSON, confusion matrix | ML Engineer |
| **4. Upload** | Upload to MinIO model bucket | `models/ensemble-v2.0/` | ML Engineer |
| **5. Review** | Manual review of metrics + notebook diff | PR/approval record | ML Lead |
| **6. Deploy** | Update model path in Risk Engine config | `.env` or config file | DevOps |
| **7. Canary** | Route 5% traffic to new model | Feature flag | DevOps |
| **8. Full Rollout** | Route 100% after 24h validation | Config update | DevOps |

#### Artifact Locations (Current)

```
MinIO: models/
├── ensemble-v2.0/
│   ├── xgboost_v2.pkl          # XGBoost model (K-fold trained)
│   ├── lgbm_v2.pkl             # LightGBM model (K-fold trained)
│   ├── meta_lr.pkl             # Logistic regression meta-learner
│   ├── vae_encoder.pt          # β-VAE encoder (PyTorch)
│   ├── graphsage.pt            # GraphSAGE model (PyTorch Geometric)
│   ├── scaler.pkl              # RobustScaler (preprocessing)
│   └── metrics.json            # Validation metrics + checksum
└── ensemble-v1.0/              # Previous version (rollback target)
```

#### Planned Improvements (Roadmap)

| Improvement | Status | Priority |
|-------------|--------|----------|
| MLflow model registry integration | � Planned | High |
| Automated CI/CD pipeline (notebook → model) | 🔷 Planned | High |
| A/B testing infrastructure | 🔷 Planned | Medium |
| Model signing (GPG/cosign) | 🔷 Planned | Medium |
| Automated drift-triggered retraining | 🔷 Planned | Low |

> **Audit Note:** Model promotion is currently a **manual, human-in-the-loop process**. This is intentional for a high-risk AML system where automatic deployment could introduce undetected bias or errors. All model changes require explicit human approval.

---

### �🔐 Embedded Security

| Control | Implementation | Status |
|---------|----------------|--------|
| Model Version Pinning | SHA256 model checksums | ✅ Implemented |
| Training Data Provenance | Merkle tree of training batches | 🔷 Planned |
| Drift Detection | KL divergence monitoring | 🔶 Implemented |
| Poisoning Prevention | Anomaly detection on label submissions | 🔶 Implemented |
| Human Override | Analyst escalation path for all decisions | ✅ Implemented |

### Model Architecture

```
Training Pipeline (Two-Notebook System):
────────────────────────────────────────

NOTEBOOK 1: Hope_machine(4).ipynb
─────────────────────────────────
Kaggle ETH Data ──► XGBoost v1 ──► Pseudo-Label Fresh Data (confidence > 0.85)
                                        │
                                        ▼
                              Weakly-Labeled Dataset
                                        │
                    ┌───────────────────┘
                    │
                    ▼
NOTEBOOK 2: vae_gnn_pipeline(2).ipynb
──────────────────────────────────────
              Enriched Data (+ XGB scores + rules + graph props)
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
       β-VAE              VGAE
    (latent z)         (graph z)
          │                   │
          └─────────┬─────────┘
                    ▼
    ┌───────────────────────────────────┐
    │     Supervised GNN (L0a)          │
    │  GATv2 (attention) + GraphSAGE    │
    └───────────────┬───────────────────┘
                    │
    ┌───────────────────────────────────┐
    │  Gradient Boosting (L0b)          │
    │  XGBoost v2 + LightGBM (5-Fold)   │
    └───────────────┬───────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │     Meta-Learner (L1)             │
    │     Logistic Regression           │
    │     Input: 7 features             │
    │     y = Σ wᵢ·featᵢ + b            │
    └───────────────┬───────────────────┘
                    ▼
            Final Prediction
```

### Model Performance (Auditable Metrics)

> **Important:** These metrics are from **offline evaluation** on the notebook pipeline (`vae_gnn_pipeline.ipynb`). Production metrics may differ due to:
> - Data distribution drift over time
> - Degraded mode inference (missing graph features)
> - Adversarial behavior adaptation
> 
> **Verification:** Run Step 10 of `notebooks/vae_gnn_pipeline.ipynb` to reproduce.

**Dataset:**
- Source: Ethereum Mainnet (BigQuery `crypto_ethereum.transactions`)
- Window: Representative sample (exact dates vary by training run)
- Labels: Confirmed fraud (sanctions + exchange freezes + law enforcement)
- Split: Time-ordered (train → validation → test), strict temporal separation

**Leakage Controls:**
- Address holdout: `GroupShuffleSplit` on `from_address` (0% overlap)
- Graph contamination: Test addresses never in training graph neighborhoods
- Feature computation: Only use data available *before* transaction time

**Performance (Offline Test Set):**
| Metric | Value | Measurement | Verified |
|--------|-------|-------------|----------|
| ROC-AUC | ~0.94 | Bootstrap resampling | ✅ Notebook |
| PR-AUC | ~0.87 | Precision-Recall curve | ✅ Notebook |
| F1 @ 0.5 threshold | ~0.87 | Balanced precision/recall | ✅ Notebook |
| **Precision @ BLOCK (0.8)** | ~0.91 | 9% FP rate at BLOCK | ✅ Notebook |
| **Recall @ BLOCK (0.8)** | ~0.73 | 73% fraud caught at BLOCK | ✅ Notebook |
| Alert Load @ REVIEW (0.4) | ~3% of transactions | Analyst queue size | ✅ Notebook |
| Calibration (ECE) | <0.05 | Expected Calibration Error | ✅ Notebook |

> **Note:** Tilde (~) indicates approximate values that may vary ±0.02 across training runs due to random initialization and fold splits.

**Operating Points (Design Thresholds):**
- **ALLOW (0.0-0.4):** Low-risk pass-through
- **REVIEW (0.4-0.7):** Analyst queue for manual review
- **ESCROW (0.7-0.8):** Reversible hold pending investigation
- **BLOCK (0.8-1.0):** Hard reject + SAR filing

**Cost-Based Metrics (Illustrative – Assumptions Required):**
> These are illustrative calculations. Actual costs depend on:
> - Transaction volume (varies by deployment)
> - Analyst cost per case (varies by jurisdiction)
> - Fraud loss per case (varies by transaction type)
- **Total Expected Loss:** $6.03M/day (baseline: $8.2M/day without AMTTP → **26% reduction**)

---

## 🎛 5. POLICY, RULE & GOVERNANCE ENGINE (PRODUCT LOGIC)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                       🎛 POLICY & GOVERNANCE ENGINE                          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ • Risk Banding (On-Chain Enforcement)                                        │
│   ┌─────────────────────────────────────────────────────────────────┐        │
│   │  Score Range  │  Action      │  Smart Contract Response        │        │
│   ├───────────────┼──────────────┼─────────────────────────────────┤        │
│   │  0.0 - 0.4    │  ALLOW       │  secureTransfer() executes      │        │
│   │  0.4 - 0.7    │  REVIEW      │  Escrow + analyst notification  │        │
│   │  0.7 - 0.8    │  ESCROW      │  Held pending investigation     │        │
│   │  0.8 - 1.0    │  BLOCK       │  Transaction rejected + SAR     │        │
│   └─────────────────────────────────────────────────────────────────┘        │
│                                                                              │
│ • 6 AML Detection Rules (Monitoring Service)                                 │
│   - Large Transaction (> 10,000 ETH equivalent)                              │
│   - Rapid Succession (> 5 tx in 10 minutes)                                  │
│   - Structuring Detection (near-threshold patterns)                          │
│   - Mixer/Tumbler Interaction                                                │
│   - Dormant Account Activation (> 180 days)                                  │
│   - High-Risk Geography (FATF blacklist)                                     │
│                                                                              │
│ • Typology Rules                                                             │
│   - Layering detection (multi-hop rapid transfers)                           │
│   - Smurfing detection (structured deposits)                                 │
│   - Fan-in / fan-out patterns                                                │
│   - Bridge abuse patterns                                                    │
│                                                                              │
│ • Governance                                                                 │
│   - Analyst approval workflows                                               │
│   - Kleros dispute escalation                                                │
│   - Emergency pause (multi-sig)                                              │
│   - Policy versioning with audit trail                                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 🔐 Embedded Security

| Control | Implementation |
|---------|----------------|
| Policy Versioning | Git-style version control |
| Decision Explainability | XAI output for every risk score (SHAP for XGBoost, feature importance) |
| Non-Repudiation | Signed analyst approvals (Ed25519 signatures stored in MongoDB) |
| Emergency Controls | Multi-sig pause with 2-of-3 threshold (24-hour timelock before unpausing) |

---

## ⚠️ FAILURE MODES & SAFETY MECHANISMS

### Scenario 1: Oracle Service Down
**Trigger:** Risk Engine (8000) unresponsive for >5 seconds  
**Behavior:**
- Smart contract reverts with `OracleTimeout()` error
- Client SDK retries 3x with exponential backoff (1s, 2s, 4s)
- If all retries fail: transaction **rejected** (fail-closed by default)
- User can override with `--force-allow` flag (logs warning + higher escrow threshold)

### Scenario 2: Graph Data Stale (Memgraph)
**Trigger:** Last GraphSAGE embedding update >2 hours ago  
**Behavior:**
- Risk Engine logs warning: `"graph_freshness": "stale"`
- Inference: Use last known embeddings from Redis + tabular-only fallback
- Confidence interval widened by 20% (e.g., [0.3, 0.5] → [0.25, 0.55])
- Alert sent to ops team via Slack webhook

### Scenario 3: Model Drift Detected
**Trigger:** KL divergence(live_scores, baseline_distribution) > 0.08  
**Behavior:**
- Automatic rollback to previous model version (MLflow registry)
- Alert to ML team + freeze new training runs
- Manual investigation required before re-enabling latest model

### Scenario 4: Redis Cache Miss (Embeddings)
**Trigger:** GraphSAGE embedding not found in Redis for address  
**Behavior:**
- Compute embedding on-demand (GraphSAGE forward pass) ← adds 200ms latency
- If >5% of requests hit this path: auto-trigger full embedding refresh job
- Temporary degradation: return `"degraded_mode": true` in response

### Scenario 5: Smart Contract Paused (Emergency)
**Trigger:** Multi-sig pause call (2-of-3 approval)  
**Behavior:**
- All `secureTransfer()` calls revert with `ContractPaused()` error
- Only `release()` (for escrowed funds) remains callable
- 24-hour timelock before unpausing (governance vote required)

### Scenario 6: IPFS Storage Unavailable
**Trigger:** Helia client cannot pin audit logs  
**Behavior:**
- Logs written to MinIO backup (encrypted S3-compatible storage)
- Background job retries IPFS pinning every 5 minutes
- Critical: If both IPFS + MinIO fail, oracle refuses to sign responses (fail-closed)

### Monitoring & Alerting
- **Prometheus** metrics exported by all services (port 9090)
- **Grafana** dashboards: latency, error rate, cache hit ratio, model drift
- **PagerDuty** integration: P1 alerts for oracle down, graph stale, drift detected
- **Slack** webhooks: P2 alerts for degraded mode, cache misses

---

## ⛓ 6. SMART CONTRACT & ON-CHAIN ENFORCEMENT

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                     ⛓ AMTTP SMART CONTRACT SUITE                             │
├──────────────────────────────────────────────────────────────────────────────┤
│ Tooling:                                                                     │
│  - Solidity 0.8.24                                                           │
│  - OpenZeppelin Contracts 4.x (Upgradeable)                                  │
│  - Hardhat (build, test, deploy)                                             │
│  - LayerZero V1 (cross-chain messaging)                                      │
│                                                                              │
│ Core Contracts                                                               │
│  ┌─────────────────────────────────────────────────────────────────┐         │
│  │ AMTTPStreamlined.sol                                            │         │
│  │  • secureTransfer() - Risk-checked transfers                    │         │
│  │  • escrow / release - Conditional execution                     │         │
│  │  • ERC721 compliance certification                              │         │
│  └─────────────────────────────────────────────────────────────────┘         │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐         │
│  │ AMTTPPolicyEngine.sol (Upgradeable - UUPS)                      │         │
│  │  • Risk threshold configuration                                 │         │
│  │  • User-specific policy overrides                               │         │
│  │  • Escrow threshold management                                  │         │
│  └─────────────────────────────────────────────────────────────────┘         │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐         │
│  │ AMTTPDisputeResolver.sol (Kleros Integration)                   │         │
│  │  • IArbitrable implementation                                   │         │
│  │  • Escrow management                                            │         │
│  │  • Appeal handling                                              │         │
│  └─────────────────────────────────────────────────────────────────┘         │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐         │
│  │ AMTTPCrossChain.sol (LayerZero)                                 │         │
│  │  • sendRiskScore() - Cross-chain risk propagation               │         │
│  │  • blockAddressGlobally() - Multi-chain blocklist               │         │
│  │  • syncDisputeResult() - Dispute outcome sync                   │         │
│  └─────────────────────────────────────────────────────────────────┘         │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 🔐 Embedded Security

| Control | Implementation |
|---------|----------------|
| Reentrancy Protection | OpenZeppelin ReentrancyGuard |
| Multi-Sig Enforcement | 2-of-3 for critical operations |
| Upgrade Safety | UUPS pattern with timelock |
| Formal Verification | Slither + Mythril CI integration |
| Access Control | Role-based (Owner, Operator, Oracle) |

### Deployed Contracts (Sepolia Testnet)

| Contract | Address |
|----------|---------|
| PolicyEngine | `0x520393A448543FF55f02ddA1218881a8E5851CEc` |
| DisputeResolver | `0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade` |
| CrossChain | `0xc8d887665411ecB4760435fb3d20586C1111bc37` |

---

## 🌐 7. BLOCKCHAIN EXECUTION ENVIRONMENT

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         🌐 BLOCKCHAIN NETWORKS                               │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Production Networks                                                         │
│  ┌────────────┬────────────┬────────────┬────────────┬────────────┐         │
│  │  Ethereum  │  Polygon   │  Arbitrum  │  Optimism  │    BSC     │         │
│  │  Mainnet   │  Mainnet   │    One     │  Mainnet   │  Mainnet   │         │
│  └────────────┴────────────┴────────────┴────────────┴────────────┘         │
│                                                                              │
│  Test Networks                                                               │
│  ┌────────────┬────────────┬────────────┬────────────┬────────────┐         │
│  │  Sepolia   │  Polygon   │  Arbitrum  │    Base    │  Hardhat   │         │
│  │            │   Amoy     │  Sepolia   │  Sepolia   │   Local    │         │
│  └────────────┴────────────┴────────────┴────────────┴────────────┘         │
│                                                                              │
│  Cross-Chain Messaging                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐         │
│  │  LayerZero V1 - Omnichain Interoperability Protocol             │         │
│  │  Supported Chain IDs: 101, 109, 110, 111, 184, 102, 106         │         │
│  └─────────────────────────────────────────────────────────────────┘         │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔌 8. METAMASK SNAP INTEGRATION

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                      🔌 AMTTP RISK GUARD SNAP                                │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Permissions                                                                 │
│  ├── endowment:transaction-insight  → Pre-tx risk display                   │
│  ├── endowment:network-access       → API connectivity                      │
│  ├── snap_dialog                    → Policy configuration                  │
│  ├── snap_manageState               → User preference storage               │
│  └── snap_notify                    → High-risk alerts                      │
│                                                                              │
│  Features                                                                    │
│  ├── Real-time risk scoring before transaction confirmation                 │
│  ├── User-configurable risk thresholds                                      │
│  ├── Visual risk indicators (🟢 LOW / 🟡 MEDIUM / 🔴 HIGH)                  │
│  └── Automatic blocking of transactions exceeding threshold                 │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 ARCHITECTURE SUMMARY

### Technology Stack

| Layer | Technologies |
|-------|--------------|
| **Frontend** | Flutter Web (main), Next.js 15.5.3 (SIEM), TailwindCSS |
| **SDK** | TypeScript, ethers.js v6, Viem |
| **API Gateway** | NGINX reverse proxy (port 80) |
| **Backend** | Python FastAPI (Orchestrator, Services) |
| **ML/AI** | GraphSAGE, LGBM, XGBoost, β-VAE, VGAE, GATv2, PyTorch, scikit-learn |
| **Graph** | Memgraph (Cypher queries, PageRank, clustering) |
| **Storage** | MongoDB, MinIO, Redis, IPFS (Helia) |
| **Blockchain** | Solidity 0.8.24, OpenZeppelin, Hardhat, Foundry |
| **Cross-Chain** | LayerZero V1 |
| **Disputes** | Kleros Arbitrator |
| **Compliance** | Sumsub KYC, FCA MLR 2017, FATF Rec. 16 |

### Security Architecture

| Principle | Implementation | Status |
|-----------|----------------|--------|
| **Defense in Depth** | Multi-layer validation (SDK → NGINX → Oracle → Contract) | ✅ Implemented |
| **Zero Trust** | All inputs validated, all outputs signed | 🔶 Partial |
| **Immutability** | IPFS audit logs, blockchain state | 🔶 Implemented |
| **Explainability** | XAI for every ML decision (SHAP feature importance) | 🔷 Planned |
| **Non-Repudiation** | Cryptographic signatures on all actions | 🔶 Implemented |

### 🛡️ THREAT MODEL SUMMARY

> **Scope:** This threat model covers the AMTTP risk scoring and enforcement system. Smart contract security is covered separately in audit reports.

| Threat | Mitigation | Status |
|--------|------------|--------|
| **Oracle key compromise** | Key rotation every 90 days, HSM storage (optional) | 🔶 Implemented |
| **Replay attacks** | Nonce + timestamp + TTL enforcement | ✅ Implemented |
| **Model poisoning (training)** | 2-of-3 label approval, outlier detection | 🔶 Implemented |
| **Model evasion (inference)** | Ensemble disagreement detection, human review queue | 🔶 Implemented |
| **Graph manipulation** | Read-only graph (populated from blockchain events) | ✅ By design |
| **Sanctions list tampering** | External feeds (OFAC/HMT), cryptographic verification | 🔶 Implemented |
| **DoS on oracle** | Rate limiting (NGINX + Redis), fail-closed design | ✅ Implemented |
| **UI tampering** | Integrity hashes, CSP headers | ✅ Implemented |

**Not in scope (customer responsibility):**
- Network-level DDoS protection
- HSM key management infrastructure
- Wallet custody security
- Regulatory classification decisions

**Known limitations:**
- Adversarial ML attacks: The system can be probed. Mitigated by rate limiting and ensemble disagreement detection.
- New fraud patterns: Requires model retraining. Mitigated by continuous monitoring and drift detection.
- Cross-chain oracle relay: LayerZero trust assumptions apply.

---

## 🎯 WHAT MAKES AMTTP UNIQUE

### This is NOT:
- ❌ A fraud API (passive detection)
- ❌ A blockchain monitor (observation only)
- ❌ A compliance dashboard (reporting only)

### This IS:
- ✅ **A transaction trust and enforcement protocol**
- ✅ Security embedded as **protocol logic**
- ✅ **Stacked Ensemble ML** (GraphSAGE + LGBM + XGBoost) **directly controlling execution**
- ✅ VAE + Graph embeddings for **deep anomaly detection**
- ✅ KYC, disputes, ML, and contracts as **one cohesive system**

---

## 📈 KEY METRICS

| Metric | Value | Evidence | Status |
|--------|-------|----------|--------|
| ML Model ROC-AUC | ~0.94 | `notebooks/vae_gnn_pipeline.ipynb` | ✅ Offline validated |
| ML Model PR-AUC | ~0.87 | `notebooks/vae_gnn_pipeline.ipynb` | ✅ Offline validated |
| Precision @ BLOCK (0.8) | ~0.91 | Notebook Step 10 output | ✅ Offline validated |
| Recall @ BLOCK (0.8) | ~0.73 | Notebook Step 10 output | ✅ Offline validated |
| Transaction Latency (P99) | <50ms target | Design spec | 🔶 Requires production measurement |
| Graph Detection Improvement | ~2x vs tabular-only | Ablation in notebook | ✅ Offline validated |
| Cross-Chain Coverage | 7 networks | `contracts/AMTTPCrossChain.sol` | ✅ Implemented |
| Regulatory Alignment | MLR 2017, FATF Rec. 16 | Design patterns | 🔶 Requires legal review |
| Audit Retention | 5 years target | IPFS + MongoDB design | 🔶 Operational config |
| AML Rules | 6 detection rules | `backend/compliance-service/monitoring_rules.py` | ✅ Implemented |

> **Note:** Metrics marked "Offline validated" are from notebook evaluation. Production performance requires operational monitoring.

---

## 📁 Repository Structure

```
amttp/
├── contracts/              # Solidity smart contracts
│   ├── AMTTPCore.sol
│   ├── AMTTPCoreSecure.sol
│   ├── AMTTPCoreZkNAF.sol
│   ├── AMTTPPolicyEngine.sol
│   ├── AMTTPPolicyManager.sol
│   ├── AMTTPDisputeResolver.sol
│   ├── AMTTPCrossChain.sol
│   ├── AMTTPRiskRouter.sol
│   └── AMTTPNFT.sol
├── client-sdk/             # TypeScript SDK
│   ├── src/
│   │   ├── signing.ts      # EIP-712 signature utilities
│   │   └── ...
│   └── MEV_PROTECTION.md
├── ml/                     # ML automation (planned)
│   └── Automation/         # Future: MLflow, model registry
├── notebooks/              # Training notebooks (source of truth)
│   ├── vae_gnn_pipeline.ipynb        # Production 10-step pipeline
│   ├── amttp_bigquery_colab.ipynb    # BigQuery data extraction
│   ├── bigquery_full_export.ipynb    # Full ETH export
│   └── download_full_eth_data.ipynb  # Data download utilities
├── backend/
│   ├── oracle-service/     # Risk oracle + signing (8007)
│   │   ├── src/            # TypeScript source
│   │   └── fca_compliance_api.py
│   └── compliance-service/ # Sanctions, monitoring, geo risk
│       ├── orchestrator.py         # Main orchestrator (8007)
│       ├── sanctions_service.py    # OFAC/HMT screening (8004)
│       ├── monitoring_rules.py     # 6 AML rules (8005)
│       ├── geographic_risk.py      # FATF country risk (8006)
│       └── integrity_service.py    # UI integrity (8008)
├── frontend/
│   ├── amttp_app/          # Flutter Web app (main UI)
│   └── frontend/           # Next.js SIEM dashboard
├── docker/
│   ├── nginx.conf          # Reverse proxy config
│   └── supervisord.conf    # Process management
├── automation/             # Data ingestion (BigQuery, ETH)
├── audit/                  # Security audit tools (Echidna, Slither)
├── test/                   # Contract tests (Hardhat, Foundry)
│   ├── foundry/            # Fuzz tests
│   └── audit/              # Audit-specific tests
├── docs/                   # Architecture documentation
│   ├── SYSTEM_ARCHITECTURE.md
│   ├── ML_ARCHITECTURE.md
│   ├── FLOW_CHARTS.md
│   └── COMPONENT_DIAGRAM.md
└── reports/                # Compliance reports
```

> **Note:** `Hope_machine` notebooks are development artifacts stored separately. Only `vae_gnn_pipeline.ipynb` is the production training source.

---

## RESPONSIBILITY MATRIX

### AMTTP Product Responsibility

| Component | AMTTP Provides |
|-----------|----------------|
| Risk Scoring | **Production:** Stacked ensemble (GATv2 + GraphSAGE + XGBoost v2 + LGBM + Meta-Learner) from vae_gnn_pipeline(2).ipynb<br>**Training:** XGBoost v1 baseline from Hope_machine(4).ipynb for pseudo-labeling |
| Feature Engineering | VAE/VGAE embeddings, graph properties (PageRank, clustering), tabular features |
| Policy Engine | Smart contracts, threshold configuration (ALLOW/REVIEW/ESCROW/BLOCK) |
| Cross-Chain | LayerZero integration, global blocklists |
| Disputes | Kleros integration, escrow management |
| Compliance | Sanctions screening (OFAC/HMT/EU/UN), 6 AML rules, FATF country risk |
| SDK | TypeScript client, secure defaults, MEV protection, EIP-712 signing |
| SIEM Dashboard | Next.js monitoring, entity investigation, compliance views |

### Customer Operations Responsibility

| Component | Customer Manages |
|-----------|------------------|
| Infrastructure | WAF, CDN, load balancers |
| Network Security | Firewalls, DDoS protection |
| Key Management | HSMs, wallet custody |
| Deployment | CI/CD, container orchestration |
| Monitoring | APM, SIEM integration |

---

**Document Version:** 2.2  
**Last Updated:** January 2026  
**Classification:** Technical Whitepaper

---

## 📝 DOCUMENT VERIFICATION CHECKLIST

Use this checklist to verify claims in this document against the codebase:

| Section | Verification Command | Expected Result |
|---------|----------------------|-----------------|
| AML Rules (6) | `grep -c "class.*Rule\|def.*detect" backend/compliance-service/monitoring_rules.py` | Count ≥ 6 |
| Contract Pause | `grep "emergencyPause\|setEmergencyPause" contracts/AMTTPPolicyEngine.sol` | Matches found |
| Notebook exists | `ls notebooks/vae_gnn_pipeline.ipynb` | File exists |
| SDK services | `ls client-sdk/src/services/` | 10+ service files |
| NGINX routing | `grep "upstream\|location" docker/nginx.conf` | Multiple matches |
| Foundry tests | `ls test/foundry/*.t.sol` | Test files exist |

**For auditors:**
1. Run `notebooks/vae_gnn_pipeline.ipynb` to verify ML metrics
2. Run `npx hardhat test` to verify contract tests pass
3. Run `forge test` for fuzz tests
4. Review `audit/SECURITY_AUDIT_REPORT.md` for security findings

---

*For regulatory inquiries: compliance@amttp.protocol*  
*For technical inquiries: tech@amttp.protocol*
