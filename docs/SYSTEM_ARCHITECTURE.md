# AMTTP System Architecture

**Version:** 3.0  
**Date:** February 2026  
**Author:** DevOps Engineering  

---

## Table of Contents

1. [Overview](#overview)
2. [System Diagram](#system-diagram)
3. [Component Architecture](#component-architecture)
4. [Service Communication Flow](#service-communication-flow)
5. [Data Flow Diagrams](#data-flow-diagrams)
6. [Deployment Architecture](#deployment-architecture)
7. [Security Architecture](#security-architecture)
8. [RBAC Architecture](#rbac-architecture)
9. [API Reference](#api-reference)
10. [Port Reference](#port-reference)

---

## Overview

AMTTP (Anti-Money Laundering Transaction Trust Protocol) is a comprehensive compliance and risk management platform for blockchain transactions. The system integrates:

- **ML-powered risk scoring** (Stacked Ensemble: GraphSAGE + LGBM + XGBoost + Linear Meta-Learner)
- **VAE latent features** for anomaly compression
- **GraphSAGE embeddings** for structural pattern detection
- **Real-time sanctions screening** (OFAC, HMT, EU, UN)
- **Transaction monitoring** with 6 AML detection rules
- **Geographic risk assessment** (FATF Black/Grey lists)
- **Smart contract enforcement** on Ethereum
- **zkNAF zero-knowledge proofs** for privacy-preserving compliance
- **FCA/AMLD6 regulatory compliance** module
- **ML Explainability** (XAI) for transparent risk decisions

### Recent Updates (February 2026)

- **Flutter Consumer App**: Fully standardized with design tokens and real MetaMask wallet integration
- **War Room**: Landing page as entry point (SIEM dashboard removed)
- **Authentication**: Multi-method auth (wallet, email, demo mode)
- **RBAC**: Unified 6-tier role system across all applications
- **zkNAF Proofs**: Zero-knowledge compliance proofs (KYC credentials, risk range, sanctions non-membership)
- **FCA Compliance API**: SAR submission, Travel Rule validation, XAI explanations
- **Explainability Service**: ML decision transparency and typology analysis
- **Policy Service**: Policy CRUD with whitelist/blacklist management
- **Graph API**: Memgraph-backed entity relationship analysis
- **Multiple Deployment Modes**: Unified, full-stack, production (Cloudflare tunnel), and bare-metal
- **Cloudflare Tunnel**: Production exposure via `cloudflared` (replaces ngrok for production)
- **Oracle Service Expansion**: PEP screening, EDD, bulk scoring, dispute resolution, webhooks/SSE

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    AMTTP PLATFORM                                        │
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                              PRESENTATION LAYER                                      ││
│  │  ┌──────────────────────┐    ┌──────────────────────┐    ┌────────────────────────┐ ││
│  │  │  Flutter Consumer    │    │   Next.js War Room   │    │    External Clients    │ ││
│  │  │    (Port 3010)       │    │     (Port 3006)      │    │    (SDK / REST API)    │ ││
│  │  │                      │    │                      │    │                        │ ││
│  │  │  • MetaMask Wallet   │    │  • Login/Auth        │    │  • TypeScript SDK      │ ││
│  │  │  • Transfer UI       │    │  • Compliance View   │    │  • REST/JSON API       │ ││
│  │  │  • Balance Display   │◄──►│  • Detection Studio  │    │  • WebSocket Events    │ ││
│  │  │  • Transaction List  │    │  • Policy Engine     │    │  • Webhooks / SSE      │ ││
│  │  │  • zkNAF Proofs      │    │  • Graph Explorer    │    │                        │ ││
│  │  │  • Safe Wallet       │    │  • Dispute Mgmt      │    │                        │ ││
│  │  │  • Cross-Chain       │    │  • Vault / Escrow    │    │                        │ ││
│  │  └──────────┬───────────┘    └──────────┬───────────┘    └───────────┬────────────┘ ││
│  └─────────────┼────────────────────────────┼───────────────────────────┼──────────────┘│
│                │                            │                           │               │
│                ▼                            ▼                           ▼               │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                          NGINX REVERSE PROXY / GATEWAY                               ││
│  │                            (Port 80 or 8888)                                         ││
│  │                                                                                      ││
│  │   /              → Flutter Web (static)      /sanctions/   → Sanctions Service      ││
│  │   /warroom/      → Next.js War Room          /monitoring/  → Monitoring Service     ││
│  │   /api/          → Orchestrator              /geo/         → Geographic Risk        ││
│  │   /ml/           → ML Risk Engine            /integrity/   → Integrity Service      ││
│  │   /zknaf/        → zkNAF Service             /explain/     → Explainability         ││
│  │   /policy/       → Policy Service            /graph/       → Graph API              ││
│  │   /fca/          → FCA Compliance            /_next/       → Next.js Assets         ││
│  │   /risk/         → Risk Engine                                                      ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                │              │              │              │              │             │
│                ▼              ▼              ▼              ▼              ▼             │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                              BACKEND SERVICES LAYER                                  ││
│  │                                                                                      ││
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐         ││
│  │  │  Orchestrator │  │ ML Risk Eng  │  │  Sanctions    │  │  Monitoring   │         ││
│  │  │  (Port 8007)  │  │ (Port 8000)   │  │  (Port 8004)  │  │  (Port 8005)  │         ││
│  │  │               │  │               │  │               │  │               │         ││
│  │  │ • Profile Mgmt│  │ • GraphSAGE   │  │ • OFAC/HMT    │  │ • 6 AML Rules │         ││
│  │  │ • Tx Evaluate │  │ • LGBM        │  │ • EU/UN Lists │  │ • Alert Mgmt  │         ││
│  │  │ • Compliance  │  │ • XGBoost     │  │ • Address DB  │  │ • Thresholds  │         ││
│  │  │ • API Keys    │  │ • Linear Meta │  │ • Batch Check │  │ • Reporting   │         ││
│  │  │ • Dashboard   │  │ • DQN Hybrid  │  │ • Name Match  │  │ • Stats       │         ││
│  │  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘         ││
│  │          │                  │                  │                  │                 ││
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐         ││
│  │  │ Geographic    │  │  Integrity    │  │  Explainabil  │  │   zkNAF       │         ││
│  │  │ Risk (8006)   │  │  Svc (8008)   │  │  ity (8009)   │  │  Demo (8010)  │         ││
│  │  │               │  │               │  │               │  │               │         ││
│  │  │ • FATF Lists  │  │ • UI Verify   │  │ • XAI Engine  │  │ • ZK Proofs   │         ││
│  │  │ • Country Risk│  │ • Tamper Det  │  │ • Typologies  │  │ • KYC Creds   │         ││
│  │  │ • Tax Havens  │  │ • Hash Check  │  │ • Tx Explain  │  │ • Sanctions   │         ││
│  │  │ • IP Risk     │  │ • Violations  │  │               │  │ • Risk Range  │         ││
│  │  └───────────────┘  └───────────────┘  └───────────────┘  └───────────────┘         ││
│  │                                                                                      ││
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐         ││
│  │  │ FCA Compliance│  │ Policy Svc    │  │  Oracle       │  │  Graph API    │         ││
│  │  │  (Port 8002)  │  │ (Port 8003)   │  │  (Port 3001)  │  │  (Port 8001)  │         ││
│  │  │               │  │               │  │               │  │               │         ││
│  │  │ • SAR Submit  │  │ • Policy CRUD │  │ • KYC / Risk  │  │ • Entity Rel  │         ││
│  │  │ • Travel Rule │  │ • Whitelist   │  │ • Chainlink   │  │ • Risk Paths  │         ││
│  │  │ • FCA Reports │  │ • Blacklist   │  │ • PEP / EDD   │  │ • Clustering  │         ││
│  │  │ • Audit Logs  │  │ • Evaluate    │  │ • Bulk Score  │  │ • Memgraph    │         ││
│  │  └───────────────┘  └───────────────┘  └───────────────┘  └───────────────┘         ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                          │                                              │
│                                          ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                              BLOCKCHAIN LAYER                                        ││
│  │                                                                                      ││
│  │  ┌─────────────────────────────────────────────────────────────────────────────────┐││
│  │  │                          ETHEREUM (Mainnet / Testnet)                           │││
│  │  │                                                                                 │││
│  │  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │││
│  │  │  │   AMTTPCore     │  │ AMTTPPolicyMgr  │  │ AMTTPDispute    │                 │││
│  │  │  │  (+ Secure,     │  │ (+ PolicyEngine)│  │   Resolver      │                 │││
│  │  │  │   Streamlined)  │  │                 │  │                 │                 │││
│  │  │  │ • Risk Oracle   │  │ • Policy CRUD   │  │ • Kleros Integ  │                 │││
│  │  │  │ • Tx Validation │  │ • Threshold Mgmt│  │ • Arbitration   │                 │││
│  │  │  │ • Escrow Logic  │  │ • Role Access   │  │ • MetaEvidence  │                 │││
│  │  │  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │││
│  │  │                                                                                 │││
│  │  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │││
│  │  │  │   AMTTPNFT      │  │ AMTTPCrossChain │  │ AMTTPRiskRouter │                 │││
│  │  │  │                 │  │                 │  │  (+ Router)     │                 │││
│  │  │  │ • KYC Badges    │  │ • LayerZero     │  │ • ML Routing    │                 │││
│  │  │  │ • Compliance ID │  │ • Bridge Safety │  │ • Score Relay   │                 │││
│  │  │  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │││
│  │  │                                                                                 │││
│  │  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │││
│  │  │  │ AMTTPCoreZkNAF  │  │ AMTTPSafeModule │  │ AMTTPBiconomy   │                 │││
│  │  │  │                 │  │                 │  │   Module        │                 │││
│  │  │  │ • ZK Proofs     │  │ • Safe{Wallet}  │  │ • Account       │                 │││
│  │  │  │ • Privacy AML   │  │ • Multi-sig     │  │   Abstraction   │                 │││
│  │  │  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │││
│  │  │                                                                                 │││
│  │  │  ┌───────────────── zkNAF Circuits ─────────────────────────┐                   │││
│  │  │  │  kyc_credential.circom  │  risk_range_proof.circom       │                   │││
│  │  │  │  sanctions_non_membership.circom  │  ZkNAFVerifierRouter │                   │││
│  │  │  └─────────────────────────────────────────────────────────┘                   │││
│  │  └─────────────────────────────────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                              DATA STORAGE LAYER                                      ││
│  │                                                                                      ││
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐         ││
│  │  │   MongoDB      │  │    MinIO      │  │    Redis      │  │   Helia       │         ││
│  │  │   (:27017)     │  │   (S3-compat) │  │   (Cache)     │  │   (IPFS)      │         ││
│  │  │               │  │   (:9000)     │  │   (:6379)     │  │   (:5001)     │         ││
│  │  │ • Profiles    │  │ • ML Models   │  │ • Sessions    │  │ • Audit Logs  │         ││
│  │  │ • Alerts      │  │ • Audit Logs  │  │ • Rate Limits │  │ • Evidence    │         ││
│  │  │ • Tx History  │  │ • Evidence    │  │ • Hot Data    │  │ • Compliance  │         ││
│  │  └───────────────┘  └───────────────┘  └───────────────┘  └───────────────┘         ││
│  │                                                                                      ││
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                            ││
│  │  │  Memgraph     │  │ HashiCorp     │  │  Hardhat      │                            ││
│  │  │  (Graph DB)   │  │   Vault       │  │  (Dev Chain)  │                            ││
│  │  │  (:7687)      │  │  (:8200)      │  │  (:8545)      │                            ││
│  │  │               │  │               │  │               │                            ││
│  │  │ • Entity Rel  │  │ • Secrets     │  │ • Local ETH   │                            ││
│  │  │ • Clustering  │  │ • API Keys    │  │ • Testing     │                            ││
│  │  └───────────────┘  └───────────────┘  └───────────────┘                            ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Architecture

### Frontend Components

| Component | Technology | Port (Dev) | Port (Docker) | Description |
|-----------|------------|------------|---------------|-------------|
| Flutter Web App | Dart/Flutter 3.24 | 3010 | 80 (static via nginx) | Consumer wallet UI, MetaMask, zkNAF, Safe wallet |
| Next.js War Room | React 19 / Next.js 15.5 | 3006 | 3004-3005 (internal) | Compliance dashboard, detection studio, graph explorer |
| Embedded Views | iframe in Flutter | - | - | `/war-room`, `/detection-studio`, `/graph-explorer` via `embed=true` |

### Backend Services

| Service | Technology | Port | Health Endpoint | Description |
|---------|------------|------|-----------------|-------------|
| ML Risk Engine | Python/FastAPI | 8000 | `/health` | Stacked ensemble ML scoring (GraphSAGE + LGBM + XGBoost) |
| Graph API | Python/FastAPI | 8001 | `/health` | Memgraph entity relationship server |
| FCA Compliance | Python/FastAPI | 8002 | `/compliance/health` | SAR submission, Travel Rule, FCA/AMLD6 reports |
| Policy Service | Python/FastAPI | 8003 | `/health` | Policy CRUD, whitelist/blacklist, evaluation |
| Sanctions | Python/FastAPI | 8004 | `/health` | OFAC/HMT/EU/UN screening, batch checks |
| Monitoring | Python/FastAPI | 8005 | `/health` | 6 AML rules engine, alert management |
| Geographic Risk | Python/FastAPI | 8006 | `/health` | FATF/country risk, IP risk, tax havens |
| Orchestrator | Python/FastAPI | 8007 | `/health` | Central compliance coordinator, profiles, decisions |
| Integrity | Python/FastAPI | 8008 | `/health` | UI tamper detection, hash verification |
| Explainability | Python/FastAPI | 8009 | `/health` | ML decision XAI, typology analysis |
| zkNAF Demo | Python/FastAPI | 8010 | `/zknaf/health` | Zero-knowledge proof generation & verification |
| Oracle Service | Node.js/Express | 3001 (ext) | `/health` | KYC, risk (DQN/XGBoost), PEP, EDD, bulk scoring, disputes |

### ML Pipeline

The risk engine uses a **stacked ensemble with knowledge distillation**:

```
Kaggle ETH Fraud → XGBoost v1 → Predict on fresh data
                              ↓
            + Custom Rules + Memgraph Graph Properties
                              ↓
                     Enriched Dataset
                              ↓
              VAE Latent → GraphSAGE Embeddings
                              ↓
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                     ↓
    GraphSAGE              LGBM                 XGBoost v2
        └─────────────────────┼─────────────────────┘
                              ↓
                    Linear Meta-Learner
                              ↓
                     Final Risk Score
```

**Key insight**: The final model has rules, graph detection, and base XGBoost patterns "baked in" through the training data enrichment process.

### Smart Contracts

| Contract | Network | Description |
|----------|---------|-------------|
| AMTTPCore | Ethereum | Main protocol logic, risk oracle integration, escrow |
| AMTTPCoreSecure | Ethereum | Hardened variant with additional security checks |
| AMTTPCoreZkNAF | Ethereum | Core + zero-knowledge proof integration |
| AMTTPStreamlined | Ethereum | Optimized lightweight variant |
| AMTTPPolicyManager | Ethereum | Policy CRUD, threshold management |
| AMTTPPolicyEngine | Ethereum | On-chain rule evaluation engine |
| AMTTPDisputeResolver | Ethereum | Kleros arbitration integration, metaEvidence |
| AMTTPNFT | Ethereum | KYC/compliance NFT badges |
| AMTTPCrossChain | Ethereum | LayerZero bridge integration |
| AMTTPRiskRouter | Ethereum | ML score routing & relay |
| AMTTPRouter | Ethereum | Transaction routing |
| AMTTPSafeModule | Ethereum | Safe{Wallet} multi-sig module |
| AMTTPBiconomyModule | Ethereum | Biconomy account abstraction |
| AMTTPzkNAF | Ethereum | Zero-knowledge NAF verifier contract |
| ZkNAFVerifierRouter | Ethereum | Routes ZK proofs to appropriate verifiers |

#### zkNAF Circuits (Circom)

| Circuit | Description |
|---------|-------------|
| `kyc_credential.circom` | Prove KYC completion without revealing PII |
| `risk_range_proof.circom` | Prove risk score is within acceptable range |
| `sanctions_non_membership.circom` | Prove address is not on sanctions lists |

---

## Service Communication Flow

### Transaction Evaluation Flow

```
┌────────────┐     ┌─────────┐     ┌─────────────┐     ┌──────────────┐
│   Client   │────►│  Nginx  │────►│ Orchestrator│────►│ Risk Engine  │
│  (Flutter) │     │ (Proxy) │     │   (8007)    │     │   (8000)     │
└────────────┘     └─────────┘     └──────┬──────┘     └──────────────┘
                                          │
                   ┌──────────────────────┼──────────────────────┐
                   │                      │                      │
                   ▼                      ▼                      ▼
            ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
            │  Sanctions   │       │  Monitoring  │       │ Geographic   │
            │   (8004)     │       │   (8005)     │       │ Risk (8006)  │
            └──────────────┘       └──────────────┘       └──────────────┘
```

### Detailed Transaction Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           TRANSACTION EVALUATION SEQUENCE                            │
└─────────────────────────────────────────────────────────────────────────────────────┘

  User          Flutter App       Nginx         Orchestrator      Services        Chain
   │                │               │                │               │              │
   │  1. Initiate   │               │                │               │              │
   │  Transfer      │               │                │               │              │
   │───────────────►│               │                │               │              │
   │                │               │                │               │              │
   │                │ 2. POST       │                │               │              │
   │                │ /api/evaluate │                │               │              │
   │                │──────────────►│                │               │              │
   │                │               │                │               │              │
   │                │               │ 3. Forward     │               │              │
   │                │               │ /evaluate      │               │              │
   │                │               │───────────────►│               │              │
   │                │               │                │               │              │
   │                │               │                │ 4. Fan-out    │              │
   │                │               │                │ to services   │              │
   │                │               │                │──────────────►│              │
   │                │               │                │               │              │
   │                │               │                │   ┌───────────┴───────────┐  │
   │                │               │                │   │                       │  │
   │                │               │                │   ▼                       ▼  │
   │                │               │                │ ┌─────┐  ┌─────┐  ┌─────┐   │
   │                │               │                │ │Risk │  │Sanc.│  │Geo  │   │
   │                │               │                │ │Score│  │Check│  │Risk │   │
   │                │               │                │ └──┬──┘  └──┬──┘  └──┬──┘   │
   │                │               │                │    │        │        │      │
   │                │               │                │◄───┴────────┴────────┘      │
   │                │               │                │                             │
   │                │               │                │ 5. Aggregate                │
   │                │               │                │ Decision                    │
   │                │               │                │                             │
   │                │               │ 6. Decision    │                             │
   │                │               │◄───────────────│                             │
   │                │               │                │                             │
   │                │ 7. Response   │                │                             │
   │                │◄──────────────│                │                             │
   │                │               │                │                             │
   │                │               │                │                             │
   │  8. Decision   │               │                │                             │
   │◄───────────────│               │                │                             │
   │                │               │                │                             │
   │  [If ALLOW]    │               │                │                             │
   │                │               │                │                             │
   │  9. Sign &     │               │                │                             │
   │  Submit TX     │               │                │              10. Execute    │
   │────────────────┼───────────────┼────────────────┼──────────────────────────►  │
   │                │               │                │                             │
   │                │               │                │              11. On-chain   │
   │                │               │                │                  verify     │
   │                │               │                │◄─────────────────────────── │
   │                │               │                │                             │
   │  12. Confirm   │               │                │                             │
   │◄───────────────┼───────────────┼────────────────┼─────────────────────────────│
   │                │               │                │                             │

```

---

## Data Flow Diagrams

### Compliance Decision Flow

```
                              ┌─────────────────────────────────────┐
                              │        COMPLIANCE DECISION          │
                              │              ENGINE                 │
                              └─────────────────────────────────────┘
                                              │
                 ┌────────────────────────────┼────────────────────────────┐
                 │                            │                            │
                 ▼                            ▼                            ▼
    ┌────────────────────┐      ┌────────────────────┐      ┌────────────────────┐
    │   RISK SCORING     │      │  SANCTIONS CHECK   │      │   GEO RISK CHECK   │
    │                    │      │                    │      │                    │
    │  ┌──────────────┐  │      │  ┌──────────────┐  │      │  ┌──────────────┐  │
    │  │  GraphSAGE   │  │      │  │ OFAC List    │  │      │  │ FATF Black   │  │
    │  │  Embeddings  │  │      │  │ (7,800+ ent) │  │      │  │ (3 countries)│  │
    │  └──────────────┘  │      │  └──────────────┘  │      │  └──────────────┘  │
    │  ┌──────────────┐  │      │  ┌──────────────┐  │      │  ┌──────────────┐  │
    │  │  LGBM +      │  │      │  │ HMT List     │  │      │  │ FATF Grey    │  │
    │  │  XGBoost     │  │      │  │ (UK Treasury)│  │      │  │ (19 countries│  │
    │  └──────────────┘  │      │  └──────────────┘  │      │  └──────────────┘  │
    │  ┌──────────────┐  │      │  ┌──────────────┐  │      │  ┌──────────────┐  │
    │  │ Linear Meta  │  │      │  │ EU Sanctions │  │      │  │ EU High Risk │  │
    │  │   Learner    │  │      │  │              │  │      │  │ (14 countries│  │
    │  └──────────────┘  │      │  └──────────────┘  │      │  └──────────────┘  │
    │                    │      │  ┌──────────────┐  │      │                    │
    │  Output:           │      │  │ UN Sanctions │  │      │  Output:           │
    │  score: 0.0-1.0    │      │  └──────────────┘  │      │  risk_level: str   │
    │                    │      │                    │      │  is_prohibited: bool│
    └─────────┬──────────┘      │  ┌──────────────┐  │      └─────────┬──────────┘
              │                 │  │ Crypto Addr  │  │                │
              │                 │  │ (22 known)   │  │                │
              │                 │  └──────────────┘  │                │
              │                 │                    │                │
              │                 │  Output:           │                │
              │                 │  is_sanctioned:bool│                │
              │                 └─────────┬──────────┘                │
              │                           │                           │
              └───────────────────────────┼───────────────────────────┘
                                          │
                                          ▼
                              ┌─────────────────────────────────────┐
                              │         DECISION MATRIX             │
                              │                                     │
                              │  Risk Score    Sanctions   Geo Risk │
                              │  ──────────    ─────────   ──────── │
                              │  < 0.4         No          Low      │  → ALLOW
                              │  0.4 - 0.7     No          Medium   │  → REVIEW
                              │  > 0.7         No          High     │  → ESCROW
                              │  Any           Yes         Any      │  → BLOCK
                              │  Any           Any         FATF BL  │  → BLOCK
                              └─────────────────────────────────────┘
                                          │
                                          ▼
                              ┌─────────────────────────────────────┐
                              │         COMPLIANCE DECISION         │
                              │                                     │
                              │  {                                  │
                              │    action: "ALLOW|REVIEW|ESCROW|    │
                              │             BLOCK|MANUAL_REVIEW",   │
                              │    risk_score: 0.0-1.0,            │
                              │    reasons: [...],                  │
                              │    requires_travel_rule: bool,      │
                              │    requires_sar: bool,              │
                              │    escrow_duration_hours: int       │
                              │  }                                  │
                              └─────────────────────────────────────┘
```

### AML Monitoring Rules

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                            AML MONITORING ENGINE                                     │
│                                 (6 Rules)                                           │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ RULE 1: Large Transaction Detection                                          │    │
│  │ ─────────────────────────────────────                                        │    │
│  │ Trigger: Single tx > 10,000 ETH equivalent                                   │    │
│  │ Action: Generate HIGH severity alert                                         │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ RULE 2: Rapid Succession                                                     │    │
│  │ ─────────────────────────────                                                │    │
│  │ Trigger: > 5 transactions within 10 minutes from same address               │    │
│  │ Action: Generate MEDIUM severity alert, flag for structuring                │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ RULE 3: Structuring Detection (Smurfing)                                     │    │
│  │ ────────────────────────────────────────                                     │    │
│  │ Trigger: Multiple txs just below 10K threshold within 24h                    │    │
│  │ Action: Generate HIGH severity alert, SAR consideration                      │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ RULE 4: Mixer/Tumbler Interaction                                            │    │
│  │ ─────────────────────────────────                                            │    │
│  │ Trigger: Transaction involving known mixer addresses (Tornado, etc.)         │    │
│  │ Action: BLOCK transaction, generate CRITICAL alert                           │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ RULE 5: Dormant Account Activity                                             │    │
│  │ ────────────────────────────────                                             │    │
│  │ Trigger: Large tx from account inactive > 180 days                           │    │
│  │ Action: Generate MEDIUM alert, enhanced verification                         │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ RULE 6: High-Risk Jurisdiction                                               │    │
│  │ ─────────────────────────────                                                │    │
│  │ Trigger: Transaction to/from FATF blacklist country                          │    │
│  │ Action: BLOCK transaction, generate CRITICAL alert                           │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Deployment Architecture

The platform supports four deployment modes:

| Mode | Compose File | Description |
|------|-------------|-------------|
| **Development** | `docker-compose.yml` | Individual containers, all ports exposed |
| **Unified** | `docker-compose.unified.yml` | Single container via supervisord |
| **Full-Stack** | `docker-compose.full.yml` | All microservices + Cloudflare tunnel |
| **Production** | `docker-compose.production.yml` | Hardened, Prometheus/Grafana, Cloudflare |
| **Cloudflare** | `docker-compose.cloudflare.yml` | Single platform image + Cloudflare tunnel |
| **Gateway-Only** | `docker-compose.gateway.yml` | Nginx gateway + ngrok (host services) |

### Full-Stack Deployment (docker-compose.full.yml)

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           DOCKER FULL-STACK DEPLOYMENT                               │
│                                (amttp-network)                                      │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                      NGINX GATEWAY (amttp-gateway)                           │    │
│  │                           Port 8888:80                                       │    │
│  │                                                                              │    │
│  │  /             → flutter-app:80          /monitoring/ → monitoring:8005      │    │
│  │  /warroom/     → nextjs-warroom:3000     /explain/    → explainability:8009  │    │
│  │  /api/         → orchestrator:8007       /policy/     → policy-service:8003  │    │
│  │  /sanctions/   → sanctions:8004          /integrity/  → ui-integrity:8008   │    │
│  │  /zknaf/       → zknaf:8010              /fca/        → fca-compliance:8002 │    │
│  │  /geo/         → geo-risk:8006           /ml/         → ml-risk-engine:8000 │    │
│  │  /graph/       → graph-api:8001                                              │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                      │                                               │
│     ┌────────┬────────┬──────────────┼──────────────┬────────┬────────┐             │
│     ▼        ▼        ▼              ▼              ▼        ▼        ▼             │
│  ┌───────┐┌───────┐┌──────────┐┌──────────┐┌──────────┐┌───────┐┌──────────┐      │
│  │Flutter││Next.js││Orchestr- ││Sanctions ││Monitoring││Geo    ││FCA       │      │
│  │:80    ││:3000  ││ator:8007 ││:8004     ││:8005     ││Risk   ││Comply    │      │
│  │       ││(War   ││          ││          ││          ││:8006  ││:8002     │      │
│  │       ││Room)  ││          ││          ││          ││       ││          │      │
│  └───────┘└───────┘└──────────┘└──────────┘└──────────┘└───────┘└──────────┘      │
│                                                                                      │
│  ┌───────┐┌───────┐┌──────────┐┌──────────┐┌──────────┐┌───────┐                   │
│  │Policy ││Integr-││Explain-  ││ML Risk   ││Graph API ││zkNAF  │                   │
│  │Svc    ││ity    ││ability   ││Engine    ││:8001     ││:8010  │                   │
│  │:8003  ││:8008  ││:8009     ││:8000     ││          ││       │                   │
│  └───────┘└───────┘└──────────┘└──────────┘└──────────┘└───────┘                   │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                        INFRASTRUCTURE                                        │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                    │    │
│  │  │ MongoDB  │  │  Redis   │  │ Memgraph │  │Cloudflare│                    │    │
│  │  │ :27017   │  │  :6379   │  │  :7687   │  │ Tunnel   │                    │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘                    │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Unified Container Deployment (docker-compose.unified.yml)

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           DOCKER UNIFIED CONTAINER                                   │
│                              (amttp-unified)                                        │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                           SUPERVISORD                                        │    │
│  │                     (Process Manager)                                        │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                      │                                               │
│     ┌──────────────┬─────────────────┼─────────────────┬──────────────┐             │
│     │              │                 │                 │              │             │
│     ▼              ▼                 ▼                 ▼              ▼             │
│  ┌──────┐    ┌───────────┐    ┌────────────┐    ┌──────────┐    ┌─────────┐        │
│  │Nginx │    │ Next.js   │    │Orchestrator│    │Sanctions │    │Monitoring│        │
│  │:80   │    │ :3005     │    │  :8007     │    │ :8004    │    │ :8005   │        │
│  └──────┘    └───────────┘    └────────────┘    └──────────┘    └─────────┘        │
│                                      │                                              │
│                      ┌───────────────┼───────────────┐                              │
│                      │               │               │                              │
│                      ▼               ▼               ▼                              │
│                 ┌─────────┐    ┌──────────┐    ┌──────────┐                         │
│                 │Geo Risk │    │Integrity │    │ (future) │                         │
│                 │ :8006   │    │  :8008   │    │          │                         │
│                 └─────────┘    └──────────┘    └──────────┘                         │
│                                                                                      │
│  Exposed Ports: 80, 3003, 3004, 8002, 8004, 8005, 8006, 8007                       │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                        VOLUME MOUNTS                                         │    │
│  │                                                                              │    │
│  │  /var/www/flutter    ← Flutter web build (static files)                     │    │
│  │  /app/nextjs         ← Next.js application (standalone)                     │    │
│  │  /app/backend        ← Python services                                      │    │
│  │  /var/log/supervisor ← Service logs                                         │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘

                                      │
                              Docker Network
                              (amttp-network)
                                      │
     ┌──────────────────────────────────┼──────────────────────────────────┐
     │                                  │                                  │
     ▼                                  ▼                                  ▼
┌──────────────┐               ┌──────────────┐               ┌──────────────┐
│ risk-engine  │               │   mongodb    │               │    minio     │
│   :8000      │               │   :27017     │               │   :9000      │
└──────────────┘               └──────────────┘               └──────────────┘
     │
     ▼
┌──────────────┐               ┌──────────────┐               ┌──────────────┐
│oracle-service│               │ hardhat-node │               │ vault-server │
│   :3001      │               │   :8545      │               │   :8200      │
└──────────────┘               └──────────────┘               └──────────────┘
```

### Production Deployment (Cloudflare Tunnel)

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           PRODUCTION DEPLOYMENT                                      │
│                      (docker-compose.production.yml)                                │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│              ┌─────────────────────────────────────┐                                │
│              │       Cloudflare Tunnel              │                                │
│              │         (cloudflared)                │                                │
│              │                                     │                                │
│              │  amttp.domain.com      → gateway:80 │                                │
│              │  api.amttp.domain.com  → gateway:80 │                                │
│              │  dash.amttp.domain.com → gateway:80 │                                │
│              └──────────────┬──────────────────────┘                                │
│                             │                                                        │
│                             ▼                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                    NGINX GATEWAY (3 server blocks)                           │    │
│  │                                                                              │    │
│  │  Port 80:   Flutter SPA + API routing (rate limited: 100r/s)               │    │
│  │  Port 3005: Next.js Dashboard direct                                        │    │
│  │  Port 8080: API Gateway (/v1/, /zknaf/, /risk/)                            │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  Internal Network: amttp-internal (172.28.0.0/16)                           │    │
│  │                                                                              │    │
│  │  Services: orchestrator, sanctions, monitoring, geo-risk,                   │    │
│  │            integrity, zknaf, risk-engine, oracle, nextjs                    │    │
│  │                                                                              │    │
│  │  Monitoring Profile: Prometheus + Grafana (optional)                        │    │
│  │  Storage: MongoDB 7, Redis 7, Memgraph, MinIO, Helia (IPFS)               │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Network Topology

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                NETWORK TOPOLOGY                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────────┐
                    │           INTERNET                  │
                    │                                     │
                    │     (Optional: ngrok tunnel)        │
                    │      https://xxx.ngrok.app          │
                    └───────────────────┬─────────────────┘
                                        │
                                        ▼
                    ┌─────────────────────────────────────┐
                    │         HOST MACHINE                │
                    │         Port 80 (HTTP)              │
                    └───────────────────┬─────────────────┘
                                        │
                                        ▼
                    ┌─────────────────────────────────────┐
                    │       DOCKER BRIDGE NETWORK         │
                    │         (amttp-network)             │
                    │                                     │
                    │   Subnet: 172.18.0.0/16            │
                    └───────────────────┬─────────────────┘
                                        │
           ┌────────────────────────────┼────────────────────────────┐
           │                            │                            │
           ▼                            ▼                            ▼
    ┌─────────────┐             ┌─────────────┐             ┌─────────────┐
    │amttp-unified│             │ risk-engine │             │   mongodb   │
    │ 172.18.0.2  │◄───────────►│ 172.18.0.3  │             │ 172.18.0.4  │
    │             │             │             │             │             │
    │ Ports:      │             │ Port: 8000  │             │ Port: 27017 │
    │ 80 (nginx)  │             │ (internal)  │             │ (internal)  │
    │ 3004(debug) │             │             │             │             │
    └─────────────┘             └─────────────┘             └─────────────┘
```

---

## Security Architecture

### Authentication & Authorization

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                            SECURITY LAYERS                                           │
└─────────────────────────────────────────────────────────────────────────────────────┘

  Layer 1: Network Security
  ─────────────────────────
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  • TLS termination at nginx (for production)                                    │
  │  • Rate limiting per IP                                                         │
  │  • CORS headers for browser security                                            │
  │  • No direct service exposure (all via nginx proxy)                             │
  └─────────────────────────────────────────────────────────────────────────────────┘

  Layer 2: Application Security
  ─────────────────────────────
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  • Wallet signature verification (EIP-712)                                      │
  │  • Request integrity hashing                                                    │
  │  • UI tamper detection (integrity service)                                      │
  │  • Input validation & sanitization                                              │
  └─────────────────────────────────────────────────────────────────────────────────┘

  Layer 3: Smart Contract Security
  ────────────────────────────────
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  • Role-based access control (RBAC)                                             │
  │  • Escrow mechanisms for high-risk transactions                                 │
  │  • On-chain risk score verification                                             │
  │  • Emergency pause functionality                                                │
  └─────────────────────────────────────────────────────────────────────────────────┘

  Layer 4: Data Security
  ──────────────────────
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  • Encrypted storage for sensitive data                                         │
  │  • Audit logging to IPFS (immutable)                                            │
  │  • PII minimization (addresses only)                                            │
  │  • GDPR-compliant data handling                                                 │
  └─────────────────────────────────────────────────────────────────────────────────┘
```

---

## RBAC Architecture

### Unified 6-Tier Role System

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         RBAC ROLE HIERARCHY                                          │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  R1 – End User              │  Focus Mode (bottom nav)                       │    │
│  │  ──────────────────────────────────────────────────────────────              │    │
│  │  Wallet, Transfer, History, Trust Check, NFT Swap                           │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  R2 – Power User / PEP     │  Focus Mode + Pro Tools                        │    │
│  │  ──────────────────────────────────────────────────────────────              │    │
│  │  R1 + zkNAF, Safe Wallet, Session Keys, Cross-Chain, Disputes              │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  R3 – Institution Ops      │  War Room (sidebar nav)                        │    │
│  │  ──────────────────────────────────────────────────────────────              │    │
│  │  Compliance View, FATF Rules, War Room, Detection Studio                    │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  R4 – Institution Compliance │  War Room + Governance                       │    │
│  │  ──────────────────────────────────────────────────────────────              │    │
│  │  R3 + Graph Explorer, Transaction Approver                                  │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  R5 – Platform Admin       │  Admin Mode                                    │    │
│  │  ──────────────────────────────────────────────────────────────              │    │
│  │  Admin Panel, Settings, Team Management                                     │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  R6 – Super Admin / Auditor │  War Room (read-only)                         │    │
│  │  ──────────────────────────────────────────────────────────────              │    │
│  │  Full audit access, read-only compliance views                              │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## API Reference

### Service Endpoints

#### Orchestrator (Port 8007 via /api/)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Service health check |
| POST | `/api/evaluate` | Evaluate transaction compliance |
| POST | `/api/evaluate-with-integrity` | Evaluate with UI integrity check |
| POST | `/api/risk/score` | Direct risk scoring |
| GET | `/api/profiles` | List all entity profiles |
| GET | `/api/profiles/{address}` | Get entity profile |
| PUT | `/api/profiles/{address}` | Update entity profile |
| POST | `/api/profiles/{address}/set-type/{type}` | Set profile entity type |
| GET | `/api/decisions` | List compliance decisions |
| GET | `/api/entity-types` | List available entity types |
| GET | `/api/dashboard/stats` | Dashboard statistics |
| GET | `/api/dashboard/alerts` | Dashboard alert feed |
| GET | `/api/dashboard/timeline` | Activity timeline |
| GET | `/api/sankey-flow` | Transaction flow visualization data |
| POST | `/api/api-keys` | Create API key |
| GET | `/api/api-keys` | List API keys |
| DELETE | `/api/api-keys/{key_prefix}` | Revoke API key |

#### ML Risk Engine (Port 8000 via /ml/ or /risk/)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health |
| GET | `/config` | Model configuration |
| POST | `/score/address` | Score single address |
| POST | `/score/transaction` | Score single transaction |
| POST | `/score/batch` | Batch scoring |
| POST | `/contract/should-block` | On-chain block decision |
| POST | `/contract/risk-score` | On-chain risk score |
| GET | `/dashboard/stats` | ML dashboard stats |
| GET | `/dashboard/timeline` | Scoring timeline |
| GET | `/alerts` | Active alerts |
| GET | `/entity/{address}` | Entity risk details |
| POST | `/alerts/{alert_id}/action` | Action on alert |

#### Sanctions (Port 8004 via /sanctions/)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sanctions/health` | Service health |
| POST | `/sanctions/check` | Check address/name |
| POST | `/sanctions/batch-check` | Batch screening |
| POST | `/sanctions/refresh` | Refresh sanctions lists |
| GET | `/sanctions/stats` | Database statistics |
| GET | `/sanctions/lists` | Available lists info |

#### Monitoring (Port 8005 via /monitoring/)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/monitoring/health` | Service health |
| POST | `/monitor/transaction` | Analyze single transaction |
| POST | `/monitor/batch` | Batch analysis |
| GET | `/alerts` | List alerts |
| GET | `/alerts/{alert_id}` | Get alert details |
| PATCH | `/alerts/{alert_id}` | Update alert status |
| GET | `/rules` | List active rules |
| GET | `/stats` | Monitoring statistics |

#### Geographic Risk (Port 8006 via /geo/)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/geo/health` | Service health |
| POST | `/geo/country-risk` | Assess country risk |
| POST | `/geo/ip-risk` | IP-based risk lookup |
| POST | `/geo/transaction-risk` | Transaction geographic risk |
| GET | `/geo/country/{country_code}` | Get specific country risk |
| GET | `/geo/lists/fatf-black` | FATF blacklist |
| GET | `/geo/lists/fatf-grey` | FATF greylist |
| GET | `/geo/lists/eu-high-risk` | EU high-risk list |
| GET | `/geo/lists/tax-havens` | Tax haven jurisdictions |

#### Integrity (Port 8008 via /integrity/)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health |
| POST | `/verify-integrity` | Verify UI integrity hash |
| POST | `/submit-payment` | Submit verified payment |
| POST | `/register-hash` | Register new UI hash |
| GET | `/violations` | List integrity violations |

#### Explainability (Port 8009 via /explain/)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health |
| POST | `/explain` | General explanation |
| POST | `/explain/transaction` | Transaction-level XAI |
| GET | `/typologies` | AML typology catalog |

#### FCA Compliance (Port 8002 via /fca/)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/compliance/health` | Service health |
| POST | `/compliance/sar/submit` | Submit SAR report |
| GET | `/compliance/sar/{sar_id}` | Get SAR details |
| GET | `/compliance/sar/list` | List SAR reports |
| POST | `/compliance/sanctions/check` | FCA sanctions check |
| POST | `/compliance/sanctions/batch-check` | Batch FCA screening |
| POST | `/compliance/travel-rule/validate` | FATF Rec. 16 validation |
| POST | `/compliance/xai/explain` | XAI risk explanation |
| GET | `/compliance/xai/model-info` | Model information |
| GET | `/compliance/audit/logs` | Audit log listing |
| GET | `/compliance/audit/verify/{log_id}` | Verify audit entry |
| GET | `/compliance/reports/periodic` | Periodic reports |
| GET | `/compliance/reports/fca-mlr` | FCA MLR reports |

#### Policy Service (Port 8003 via /policy/)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health |
| GET | `/policies` | List policies |
| POST | `/policies` | Create policy |
| GET | `/policies/{id}` | Get policy |
| PATCH | `/policies/{id}` | Update policy |
| DELETE | `/policies/{id}` | Delete policy |
| POST | `/policies/{id}/set-default` | Set as default policy |
| POST | `/policies/{id}/whitelist` | Add to whitelist |
| DELETE | `/policies/{id}/whitelist/{address}` | Remove from whitelist |
| POST | `/policies/{id}/blacklist` | Add to blacklist |
| DELETE | `/policies/{id}/blacklist/{address}` | Remove from blacklist |
| POST | `/policies/{id}/evaluate` | Evaluate against policy |

#### zkNAF Demo (Port 8010 via /zknaf/)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/zknaf/health` | Service health |
| GET | `/zknaf/info` | zkNAF system info |
| POST | `/zknaf/demo/generate-all` | Generate all demo proofs |
| GET | `/zknaf/demo/compliance/{address}` | Demo compliance status |
| GET | `/zknaf/sanctions/check/{address}` | ZK sanctions check |
| GET | `/zknaf/proofs/{address}` | Get proofs for address |
| POST | `/zknaf/kyc/create` | Create KYC credential proof |
| GET | `/zknaf/kyc/status/{userId}` | KYC status |
| POST | `/zknaf/wallet/link` | Link wallet to identity |
| GET | `/zknaf/wallet/info/{address}` | Wallet compliance info |
| POST | `/zknaf/transaction/verify` | Verify transaction ZK proof |
| GET | `/zknaf/transactions` | List all transactions |
| GET | `/zknaf/transactions/approved` | Approved transactions |
| GET | `/zknaf/transactions/blocked` | Blocked transactions |
| GET | `/zknaf/transactions/by-address/{address}` | Transactions by address |
| GET | `/zknaf/transactions/{tx_id}` | Transaction details |
| GET | `/zknaf/audit/summary` | Audit summary |

#### Oracle Service (Port 3001)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health |
| POST | `/kyc/*` | KYC verification workflows |
| POST | `/risk/*` | Risk scoring (DQN/XGBoost hybrid) |
| POST | `/tx/*` | Transaction submission |
| POST | `/policy/*` | Policy engine (FCA/AMLD6) |
| POST | `/label/*` | Label submission (RBAC + dual-control) |
| POST | `/explainability/*` | ML decision explanations |
| POST | `/dispute/*` | P2P dispute resolution (Kleros) |
| POST | `/reputation/*` | On-chain reputation |
| POST | `/bulk/*` | Bulk transaction scoring (1000+ tx/batch) |
| POST | `/webhook/*` | Webhooks & SSE streaming |
| POST | `/pep/*` | PEP database screening |
| POST | `/edd/*` | Enhanced Due Diligence |
| POST | `/monitoring/*` | Ongoing PEP/sanctions re-screening |

---

## Port Reference

### Frontend Services

| Service | Dev Port | Docker Port | Notes |
|---------|----------|-------------|-------|
| Flutter Web App | 3010 | 80 (nginx static) | `npx serve -s -l 3010` |
| Next.js War Room | 3006 | 3004-3005 (internal) | `npm run dev -- -p 3006` |

### Backend Services (Python/FastAPI)

| Service | Port | Health Endpoint |
|---------|------|-----------------|
| ML Risk Engine | 8000 | `/health` |
| Graph API | 8001 | `/health` |
| FCA Compliance | 8002 | `/compliance/health` |
| Policy Service | 8003 | `/health` |
| Sanctions Service | 8004 | `/health` |
| Monitoring Service | 8005 | `/health` |
| Geographic Risk | 8006 | `/health` |
| Orchestrator | 8007 | `/health` |
| Integrity Service | 8008 | `/health` |
| Explainability | 8009 | `/health` |
| zkNAF Demo | 8010 | `/zknaf/health` |

### Backend Services (Node.js)

| Service | External Port | Internal Port | Notes |
|---------|--------------|---------------|-------|
| Oracle Service | 3001 | 3000 | Express, TypeScript |

### Infrastructure

| Service | Port(s) | Credentials |
|---------|---------|-------------|
| MongoDB | 27017 | admin:changeme (dev) |
| Redis | 6379 | (none) |
| MinIO (S3) | 9000, 9001 (console) | localtest:localtest123 |
| IPFS (Helia/Kubo) | 5001, 8080 | (none) |
| Memgraph | 7687 | (none) |
| Memgraph Lab | 3000 | (none) |
| HashiCorp Vault | 8200 | root token: root (dev) |
| Hardhat Node | 8545 | (none) |

### Gateway / Proxy

| Config | Port | Use Case |
|--------|------|----------|
| Nginx (unified) | 80 | Single-container deployment |
| Nginx (full-stack) | 8888 | Docker full-stack gateway |
| Nginx (production) | 80, 3005, 8080 | Production multi-server |
| ngrok | 4040 (admin) | Dev tunnel |
| Cloudflare Tunnel | (none) | Production exposure |

---

## Quick Start

### Local Development (Host Services)

```bash
# Start infrastructure
docker-compose up -d mongo redis memgraph minio

# Start backend services (each in a separate terminal)
cd backend/compliance-service
python orchestrator.py          # Port 8007
python sanctions_service.py     # Port 8004
python monitoring_rules.py      # Port 8005
python geographic_risk.py       # Port 8006
python integrity_service.py     # Port 8008
python explainability_service.py # Port 8009
python zknaf_demo.py            # Port 8010

# Start ML risk engine
cd ml/Automation/risk_engine
python integration_service.py   # Port 8000

# Start frontends
cd frontend/frontend && npm run dev -- -p 3006    # Next.js on 3006
cd frontend/amttp_app && npx serve -s build/web -l 3010  # Flutter on 3010
```

### Docker Unified

```bash
# Start all-in-one container
docker-compose -f docker-compose.unified.yml up -d

# Verify services
curl http://localhost/api/health
curl http://localhost/sanctions/health
curl http://localhost/monitoring/health
curl http://localhost/geo/health

# Access UI
open http://localhost          # Flutter app
open http://localhost/siem     # Next.js dashboard
```

### Docker Full-Stack (with Cloudflare)

```bash
# Start full platform with gateway
docker-compose -f docker-compose.full.yml up -d

# Access via gateway
open http://localhost:8888           # Flutter via gateway
open http://localhost:8888/warroom/  # Next.js War Room

# Cloudflare tunnel provides public URL automatically
docker logs amttp-cloudflared 2>&1 | findstr "trycloudflare"
```

### Docker Production

```bash
# Start production deployment
docker-compose -f docker-compose.production.yml up -d

# Optional: enable monitoring stack
docker-compose -f docker-compose.production.yml --profile monitoring up -d
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 3.0 | Feb 2026 | Full-stack deployment, zkNAF, FCA compliance, explainability, policy service, RBAC docs, Cloudflare tunnel, expanded API reference |
| 2.0 | Jan 2026 | Unified Docker, nginx proxy, iframe embedding |
| 1.0 | Dec 2025 | Initial architecture |
