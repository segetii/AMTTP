# AMTTP — End-to-End Product Flow (What it solves, how it works)

**AMTTP (Anti-Money Laundering Transaction Trust Protocol)** is a transaction trust and enforcement platform designed to make compliance decisions **actionable at the point of transaction execution**.

Instead of treating compliance as a reporting add-on (post-facto dashboards) or a single fraud API call, AMTTP combines:
- a **hybrid end-user + institutional UI layer** (Flutter + Next.js)
- a **control plane/orchestrator** that coordinates checks and policy decisions
- **specialized microservices** (sanctions, geographic risk, monitoring rules, integrity)
- an **ML risk engine + explainability service**
- **durable stores** (MongoDB, Redis, Memgraph) for auditability and low-latency state
- optional on-chain policy enforcement (smart contracts) where applicable

This document walks through the product end-to-end: actors, components, data flow, and the core problems AMTTP solves.

---

## The problem AMTTP solves

### 1) Compliance tooling is often disconnected from execution
Traditional setups tend to look like:
- user initiates transfer
- transaction executes
- *later* analysts investigate suspicious activity

That gap is expensive: once funds move, containment becomes hard (especially cross-chain).

AMTTP shifts the posture to **pre-transaction checks and consistent enforcement**, so high-risk activity can be routed into actions such as **approve, monitor, escrow/manual review, or reject**.

### 2) Risk scores without explanations don’t help operators
A raw score is rarely sufficient for:
- case analysts
- compliance officers
- auditors
- partners integrating the system

AMTTP includes an **Explainability System** so every decision can be accompanied by:
- “top reasons” (human-readable)
- typology matches (pattern-based summaries)
- actionable recommendations

### 3) Real systems need layered signals, not a single model
Fraud/AML decisions typically need:
- deterministic rule triggers (monitoring)
- sanctions hits (screening)
- geographic risk context
- network/graph context
- ML anomaly detection

AMTTP is built as an orchestration layer that can fuse these signals and produce a **consistent, policy-driven decision**.

---

## Architecture diagram

This is the project’s system architecture diagram as maintained in [ARCHITECTURE_DIAGRAM.md](../ARCHITECTURE_DIAGRAM.md).

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                🌐 USER INTERFACES                                    │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  📱 Mobile dApp    │  🖥️ Web Dashboard    │  🔗 DeFi Integration  │  📊 Admin Panel │
│  - Wallet connect │  - Policy management │  - SDK integration   │  - Monitoring   │
│  - Secure transfer │  - Transaction view  │  - API endpoints     │  - Analytics    │
└─────────────────┬───────────────────────┬─────────────────────┬───────────────────┘
                  │                       │                     │
                  ▼                       ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              📦 CLIENT SDK LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  📚 AMTTP TypeScript SDK (257KB)                                                    │
│  ├── 🎯 AMTTPClient.ts           # Core client with fraud protection                │
│  ├── 🛡️ RiskService.ts          # Risk assessment integration                      │
│  ├── 🎛️ PolicyService.ts        # Policy management                               │
│  ├── 💸 TransactionService.ts    # Secure transaction handling                     │
│  └── ⚡ AtomicSwapService.ts     # Cross-chain atomic swaps                        │
└─────────────────┬───────────────────────┬─────────────────────┬───────────────────┘
                  │                       │                     │
                  ▼                       ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                🔙 BACKEND SERVICES                                  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  🌐 Oracle Service API (Express.js + MongoDB)                                      │
│  ├── 🎯 Risk Scoring Endpoints                                                     │
│  │   ├── POST /api/risk/dqn-score      # DQN-enhanced fraud detection             │
│  │   ├── POST /api/risk/score          # Original heuristic scoring               │
│  │   └── GET  /api/risk/score/:txId    # Risk score retrieval                     │
│  ├── 🔍 KYC Verification Endpoints                                                 │
│  │   ├── POST /api/kyc/verify          # Document verification                     │
│  │   └── GET  /api/kyc/status/:address # Verification status                      │
│  ├── 💸 Transaction Endpoints                                                      │
│  │   ├── POST /api/transaction/validate # Pre-transaction validation              │
│  │   └── GET  /api/transaction/:id     # Transaction details                      │
│  └── 🗄️ Data Services                                                             │
│      ├── 📊 MongoDB Collections        # Users, transactions, risk_scores         │
│      ├── 📁 MinIO Object Storage       # Documents, models, backups               │
│      └── 🌐 IPFS (Helia)              # Immutable transaction logs                │
└─────────────────┬───────────────────────┬─────────────────────┬───────────────────┘
                  │                       │                     │
                  ▼                       ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                               🧠 MACHINE LEARNING LAYER                             │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  🤖 DQN Fraud Detection Engine (F1=0.669)                                          │
│  ├── 📊 Feature Engineering Pipeline                                               │
│  ├── 🧠 DQN Neural Network                                                         │
│  ├── 🎯 Training Results                                                           │
│  └── ⚡ Real-time Inference                                                        │
└─────────────────┬───────────────────────┬─────────────────────┬───────────────────┘
                  │                       │                     │
                  ▼                       ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                               ⛓️ BLOCKCHAIN LAYER                                   │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  🏗️ Modular Smart Contract Architecture (All under 24,576 byte limit)            │
│  - Core token + policy manager + policy engine                                    │
│  - Escrow/reject decision paths for high-risk activity                             │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Components (how the product is actually assembled)

### User interfaces
The repo describes a hybrid UI approach:
- **Flutter app** as the “main shell” (end-user experience, multi-platform)
- **Next.js War Room** for institutional/compliance operations

This aligns with the “Hybrid Flutter + Next.js Architecture” diagram in [README.md](../README.md).

### Client SDK layer
AMTTP distributes a TypeScript SDK that handles:
- request signing / identity binding
- orchestrating calls to the backend control plane
- consuming risk decisions and (optionally) enforcing client-side policy controls

### Gateway + service routing
In the dockerized setup, an **NGINX gateway** routes:
- `/api/` → orchestrator
- `/sanctions/` → sanctions service
- `/geo/` → geographic risk service
- `/monitoring/` → monitoring rules/alerts
- `/integrity/` → UI integrity checks
- `/ml/`, `/graph/`, `/explain/` → ML/graph/explainability

This gives the UI a single origin to call, while services remain independently deployable.

### Orchestrator (control plane)
The orchestrator is the product’s coordination point:
- accepts a transaction/context payload
- calls downstream services in parallel (sanctions, geo risk, monitoring rules, ML scoring, graph checks)
- merges outputs into a unified decision with a clear action

### Data stores
AMTTP relies on common production primitives:
- **MongoDB** for persistent records (users, alerts, transactions, audit trails)
- **Redis** for short-lived state (nonces, idempotency, rate limits)
- **Memgraph** for graph/network analytics

---

## End-to-end flow (from user action to compliance decision)

### 1) End-user initiates a transfer (Flutter app)
A user action (send/transfer) triggers:
- identity binding (wallet signature / auth session)
- request preparation (nonce, timestamp, payload)

### 2) UI calls the gateway
The client uses the gateway as the single origin (docker default: port `8888`).

### 3) Orchestrator fans out checks
The orchestrator coordinates:
- sanctions screening (OFAC/EU/UN style lists)
- geographic risk scoring (FATF lists, high-risk jurisdictions)
- monitoring rules (rule-based AML triggers)
- ML risk scoring (model inference)
- optional graph context checks (network proximity / clustering)

### 4) Policy evaluation produces an action
Outputs are normalized into an action such as:
- **APPROVE** (low risk)
- **MONITOR** (medium risk; allow but watch)
- **ESCROW / MANUAL REVIEW** (high risk; requires review)
- **REJECT** (very high risk)

### 5) Explainability package is generated
The explainability service converts model/rule outputs into:
- summary + top reasons
- typology matches
- recommended next steps

### 6) Auditability and operational workflow
The system records enough context for:
- future audit/regulatory review
- analyst workflows in the War Room
- alert/monitoring pipelines

---

## A concrete example flow (what a “risky transaction” looks like)

1. User attempts a transfer.
2. Orchestrator checks show:
   - geo risk elevated (jurisdiction risk)
   - monitoring rules triggered (velocity anomaly)
   - ML risk score elevated (outlier compared to sender history)
3. Decision returns `ESCROW` (or `REJECT`, depending on policy thresholds).
4. War Room shows:
   - reasons + typology match
   - the linked alerts/events
   - next-step recommendations

---

## Operational reliability: a real issue we solved in this repo

During integration, the compliance UI showed services as “unhealthy” even though the services themselves were running.

**Root cause:** the NGINX gateway was proxying to stale container IPs after services were recreated.

**Fix applied:** update NGINX routing to:
- use Docker DNS resolver (`127.0.0.11`)
- resolve upstreams via variables inside each `location` block
- rewrite the path explicitly before proxying

This stabilizes service health checks like:
- `http://localhost:8888/api/health`
- `http://localhost:8888/sanctions/health`
- `http://localhost:8888/geo/health`
- `http://localhost:8888/monitoring/health`

---

## Where to go next

- For full technical details and evidence mapping, see [AMTTP_PRODUCT_ARCHITECTURE.md](../AMTTP_PRODUCT_ARCHITECTURE.md)
- For developer startup steps, see [README.md](../README.md)
