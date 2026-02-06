# AMTTP Project Summary

## Overview

AMTTP (Anti‑Money Laundering Transaction Transfer/Trust Protocol) is a DeFi compliance and transaction‑enforcement stack that combines:
- **ML risk scoring** (risk-engine) + **graph analytics** (graph-api/Memgraph) + **deterministic rules** (monitoring/policy)
- **Regulatory/compliance services** (sanctions, geo‑risk, FCA-oriented checks)
- **Real‑time transaction monitoring** and operator workflows (War Room)
- **Privacy‑preserving verification** via **zkNAF** (Groth16 verification contracts)
- **On‑chain enforcement primitives** (escrow + timelocks + policy actions) with optional disputes and cross‑chain sync

---

## System Architecture (Full Stack Deployment)

This diagram reflects the default “full” docker stack in `docker-compose.full.yml` (ports included).

```
┌────────────────────────────────────────────────────────────────────────────┐
│                               USER INTERFACES                              │
├────────────────────────────────────────────────────────────────────────────┤
│  Flutter Web App (8889)                 Next.js War Room (3006)             │
│  - Wallet integration                   - Service health / monitoring       │
│  - Risk display                         - Case/alert workflows             │
└──────────────────────────────┬─────────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                           NGINX GATEWAY (8888)                              │
│                 Single origin routing to all internal services              │
└──────────────────────────────┬─────────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                          ORCHESTRATOR / CONTROL PLANE (8007)                │
│                 Coordinates ML + Graph + Rules + Compliance checks          │
└──────────────────────────────┬─────────────────────────────────────────────┘
              ┌────────────────┼───────────────────┬────────────────────────┐
              ▼                ▼                   ▼                        ▼
┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
│ ML + Explainability│  │ Graph Analytics    │  │ Rules / Policy     │  │ Compliance Services│
│                   │  │                   │  │                   │  │                   │
│ ML Risk Engine     │  │ Graph API (8001)  │  │ Monitoring (8005) │  │ Sanctions (8004)  │
│ (8000)             │  │ (Memgraph-backed) │  │ Policy (8003)     │  │ GeoRisk (8006)    │
│ Explainability     │  │                   │  │                   │  │ FCA Compliance(8002)
│ (8009)             │  │                   │  │                   │  │                   │
└───────────────────┘  └───────────────────┘  └───────────────────┘  └───────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                                SECURITY SERVICES                            │
├────────────────────────────────────────────────────────────────────────────┤
│  UI Integrity (8008)  — defensive checks against UI manipulation patterns   │
└────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────┐
│                                 DATA / INFRA                                │
├────────────────────────────────────────────────────────────────────────────┤
│  MongoDB (27017)   Redis (6379)   Memgraph (7687)                           │
│  Optional (other compose): MinIO, IPFS/Helia, Vault                          │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Functionality (What the solution does)

AMTTP’s runtime behavior can be understood as two coupled planes:
- **Off-chain decisioning plane (ML + Graph + Rules)** that produces a decision payload and audit evidence.
- **On-chain enforcement plane** (optional in deployments) that can escrow/approve/block actions based on oracle-attested risk inputs and policy.

### 1) Transaction / entity evaluation (control plane)
The orchestrator is the main coordination point for “what should happen to this transaction?”. It provides:
- **Health + service status** aggregation for the stack.
- **Evaluation endpoints** that fan out to ML, sanctions, geo-risk, and rules.
- **Decision journaling** and retrieval for dashboards.

Typical functional flow:
1) Client submits a transaction/context for evaluation.
2) Orchestrator calls downstream services in parallel (ML risk, sanctions, geo-risk, monitoring rules, graph signals where applicable).
3) Orchestrator normalizes outputs into an actionable decision and persists the decision/audit trail.

### 2) ML risk scoring (real-time)
The ML risk engine provides low-latency scoring APIs and model metadata:
- **Single scoring**: score a transaction payload and return a risk score.
- **Batch scoring**: score multiple transactions in one call.
- **Model info**: exposes model architecture/metrics metadata as reported by the service.
- **Operational dashboards**: stats/timeline/alerts endpoints to support operator views.

Implementation behavior (as coded):
- Loads model artifacts with a priority order (stacking LightGBM → LightGBM → XGBoost; optional CatBoost + calibration).
- Falls back to heuristic scoring if no model artifacts are present.

### 3) Graph analytics (network-context risk)
AMTTP includes a graph service and Memgraph backing to add “network context” to decisioning:
- **Ingest** transaction edges (single/batch) into a graph representation.
- **Compute address risk** using exposure/proximity patterns and graph statistics.
- **Produce graph-derived signals** that can be fused with ML/rules.

This is the “Graph” part of **ML + Graph + Rules**.

### 4) Rules and monitoring (deterministic enforcement)
AMTTP includes deterministic rules and monitoring to complement ML:
- **Monitor transaction** (single/batch): evaluate rule triggers/thresholds.
- **Alerts store**: list alerts and inspect a specific alert.
- **Rules inventory + stats**: expose what rules exist and aggregate counts.

This is the “Rules” part of **ML + Graph + Rules**.

### 5) Compliance services (sanctions + geo-risk + FCA)
AMTTP provides dedicated compliance checks that integrate into the orchestrated evaluation:

- **Sanctions**
  - Check an entity/address against sanctions lists.
  - Batch-check for high-throughput screening.
  - Refresh list data and expose basic stats/list inventory.

- **Geo-risk**
  - Score jurisdiction/geographic risk signals used for decisioning.

- **FCA compliance**
  - FCA-oriented endpoints (service exposed in the full stack) for compliance workflows.

### 6) Explainability and evidence
Explainability turns model/rule/graph outputs into an operator-usable explanation package:
- Human-readable reasons (why a decision was made)
- Evidence references (hashes / optional object storage / optional IPFS)

This enables auditability and reproducible investigations.

### 7) UI integrity and anti-manipulation controls
AMTTP includes an integrity service designed to detect UI-side tampering patterns:
- Verify integrity signals
- Record violations
- Support administrative workflows around integrity events

### 8) Operator dashboards and case workflows
Across the orchestrator and the risk engine services, AMTTP provides dashboard-style endpoints that power the War Room experience:
- aggregated stats
- alerts lists and timelines
- decision history
- entity profiles

### 9) Protocol enforcement (smart contracts)
When used in “protocol mode”, AMTTP can enforce decisions at transaction execution:

- **Escrowed swaps (ETH/ERC20/NFT)**
  - Initiate swap with risk inputs + oracle signature(s).
  - Complete swap with HTLC preimage.
  - Refund swap after timelock expiry.

- **Risk gating**
  - Risk score is validated against a fixed scale (0–1000).
  - Policy evaluation can map risk into Approve / Review / Escrow / Block.

- **Oracle attestation verification**
  - v1 core (`AMTTPCore.sol`): single oracle ECDSA signature with domain separation.
  - v2 core (`AMTTPCoreSecure.sol`): multi-oracle threshold signatures + nonce replay protection + signature expiry window.

- **Disputes**
  - Escrowed flows can enter dispute; dispute resolver triggers the final settlement path.

- **Cross-chain sync (optional)**
  - Cross-chain contract supports propagating risk/policy state across networks (LayerZero).

- **Privacy-preserving zkNAF (optional)**
  - zkNAF contracts provide Groth16 proof verification.
  - Core can be configured to require zkNAF verification before allowing transfers.

---

## Core Smart Contracts

| Contract | Purpose |
|---|---|
| `AMTTPRouter.sol` | Unified entrypoint that routes operations across Core/NFT/cross-module flows. |
| `AMTTPCore.sol` | Main escrow + swap + risk gating for ETH/ERC20; includes optional zkNAF integration hook; single-oracle signature verification. |
| `AMTTPCoreSecure.sol` | Hardened core variant with multi-oracle threshold signatures, nonce-based replay protection, signature validity window, and governance/timelock hardening. |
| `AMTTPPolicyEngine.sol` | On-chain policy evaluation: risk thresholds, velocity limits, compliance rules, and actions (Approve/Review/Escrow/Block); tracks `activeModelVersion` and model scores. |
| `AMTTPDisputeResolver.sol` | Kleros-based dispute workflow for escrowed/contested swaps (evidence + ruling execution). |
| `AMTTPCrossChain.sol` | LayerZero-based cross-chain propagation of risk/policy state (trusted remotes, replay/rate limits). |
| `AMTTPNFT.sol` | NFT-to-ETH and NFT-to-NFT swap flows with similar risk gating primitives. |
| `AMTTPCoreZkNAF.sol` | zkNAF module used by `AMTTPCore` to verify privacy-preserving compliance status for transfers. |
| `zknaf/AMTTPzkNAF.sol` | Groth16 verification and zkNAF proof/state management (BN254 pairing checks). |

---

## ML/AI Pipeline (ML + Graph + Rules)

AMTTP’s decisioning plane is explicitly **ML + Graph + Rules**.

### ML (risk-engine)
- A FastAPI service (`ml-risk-engine` in the full compose) provides real-time scoring and model/version metadata.
- In the implementation, the risk engine loads models with a priority order (stacking LightGBM → LightGBM → XGBoost; with optional CatBoost/calibration) and falls back to heuristics if no model artifacts exist.

### Graph (graph-api + Memgraph)
- A graph API service (`graph-api` in the full compose) is configured to connect to Memgraph and provide graph-derived signals (exposure/proximity/cluster risk).
- The ML workspace also includes a “graph-temporal” training pipeline (TGN-first with fallbacks) designed for time-evolving transaction edges exported from Memgraph.

### Rules (monitoring + policy)
- **Monitoring** provides deterministic triggers (alerts/flags).
- **Policy service** and **PolicyEngine** encode threshold/action mapping (e.g., review/escrow/block) and can be aligned with on-chain enforcement.

### Model stack (as reported by the CPU inference API)
The CPU inference API includes a `/model/info` endpoint that reports an architecture string:
- “Stacked Ensemble (GraphSAGE + LGBM + XGBoost + Linear Meta‑Learner)”

and a metrics object (reported values):

For reproducible evaluation artifacts in this repository (including explicit caveats about label provenance and dataset size), see:
- `reports/publishing/address_level_metrics.md`
- `reports/publishing/etherscan_validation_metrics.md`

If you want API-reported metrics to be “source-of-truth” benchmarks, the repo’s training/evaluation scripts should be the canonical place to reproduce them and to record an auditable run artifact.

---

## Risk‑Based Actions (On‑Chain Defaults)

AMTTP uses a risk score scale of **0–1000** (`RISK_SCALE = 1000`). Two important on-chain thresholds are:
- `HIGH_RISK_THRESHOLD = 700`
- `BLOCK_THRESHOLD = 900`

A practical mapping consistent with these defaults:

| Risk score (0–1000) | Typical action | Behavior |
|---:|---|---|
| 0–250 | APPROVE | Transaction can proceed. |
| 250–400 | APPROVE / REVIEW | Usually allow, optionally flag. |
| 400–700 | REVIEW | Require additional checks / manual approval workflow. |
| 700–900 | ESCROW | Hold funds pending investigation / dispute path. |
| 900–1000 | BLOCK | Reject (and emit auditable reason/events). |

Note: The exact mapping is configurable via policy logic; the table is a protocol-friendly default aligned to the constants.

---

## Key Features

- **ML-powered fraud detection**: real-time scoring with model artifact loading + versioning hooks.
- **Graph analytics**: Memgraph-backed network signals to catch laundering patterns that are invisible in tabular-only models.
- **Explainability**: separate service for human-readable outputs and evidence hashes.
- **Regulatory/compliance primitives**: sanctions screening, geo-risk, FCA-oriented checks, monitoring rules.
- **Privacy-preserving zkNAF**: Groth16 verification path that can prove compliance status without disclosing raw PII.
- **Cross-chain support**: LayerZero-based propagation of risk/policy state.
- **Dispute resolution**: Kleros workflow for contested escrowed activity.

---

## Infrastructure (Full Stack Ports)

| Service | Port | Purpose |
|---|---:|---|
| Gateway (NGINX) | 8888 | Single-origin routing to internal services |
| Flutter Web App | 8889 | End-user UI |
| Next.js War Room | 3006 | Operator/compliance UI |
| Orchestrator | 8007 | Coordinates ML + Graph + Rules + compliance checks |
| ML Risk Engine | 8000 | Risk scoring |
| Graph API | 8001 | Graph analytics API |
| Sanctions | 8004 | Screening |
| Monitoring | 8005 | Rules/alerts |
| Geo Risk | 8006 | Geographic risk |
| Policy Service | 8003 | Policy management |
| Explainability | 8009 | Explanations/evidence |
| UI Integrity | 8008 | UI manipulation detection |
| FCA Compliance | 8002 | FCA/compliance endpoints |
| MongoDB | 27017 | Audit logs, entities, transactions |
| Redis | 6379 | Cache, rate limiting, ephemeral state |
| Memgraph | 7687 | Graph store |

---

## Security Controls (as implemented)

- **Oracle signatures (EVM)**: ECDSA (secp256k1) signatures verified on-chain (EIP‑191 style in the contracts).
- **Replay protection**:
  - v2 core (`AMTTPCoreSecure`) uses `nonce` + `usedNonces` mapping and a signature validity window.
- **Reentrancy protection**: OpenZeppelin `ReentrancyGuard` on core flows.
- **Emergency pause**: `Pausable` in the core; policy engine also has an emergency pause flag.
- **Upgrade safety**: UUPS upgradeable patterns and governance/timelock hardening in the secure core variant.
- **UI integrity service**: separate service designed to catch “Bybit-style” UI manipulation patterns.

---

## Contract Addresses (Sepolia)

These addresses are taken from `deployments/router-sepolia-1766717664907.json`.

| Contract | Address |
|---|---|
| Router | `0xbe6EC386ECDa39F3B7c120d9E239e1fBC78d52e3` |
| Core | `0x2cF0a1D4FB44C97E80c7935E136a181304A67923` |
| NFT | `0x49Acc645E22c69263fCf7eFC165B6c3018d5Db5f` |
| PolicyEngine | `0x520393A448543FF55f02ddA1218881a8E5851CEc` |
| DisputeResolver | `0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade` |
| CrossChain | `0xc8d887665411ecB4760435fb3d20586C1111bc37` |

---

## Quick Start (Full Stack)

- Start the full stack:
  - `docker-compose -f docker-compose.full.yml up -d`
- Open:
  - Gateway: `http://localhost:8888/`
  - Flutter: `http://localhost:8889/`
  - War Room: `http://localhost:3006/`

For deeper protocol details (trust model + attestation formats), see:
- `documentation/AMTTP_PROTOCOL_WRITEUP.md`
- `documentation/AMTTP_PROPOSED_REFERENCE_ARCHITECTURE.md`
