# AMTTP System Architecture

**Version:** 2.0  
**Date:** January 2026  
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
8. [API Reference](#api-reference)

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

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    AMTTP PLATFORM                                        │
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                              PRESENTATION LAYER                                      ││
│  │  ┌──────────────────────┐    ┌──────────────────────┐    ┌────────────────────────┐ ││
│  │  │    Flutter Web App   │    │   Next.js Dashboard  │    │    External Clients    │ ││
│  │  │    (Port 80 - /)     │    │   (Port 80 - /siem)  │    │    (SDK / REST API)    │ ││
│  │  │                      │    │                      │    │                        │ ││
│  │  │  • Wallet Connect    │    │  • Risk Dashboard    │    │  • TypeScript SDK      │ ││
│  │  │  • Transfer UI       │    │  • Compliance View   │    │  • REST/JSON API       │ ││
│  │  │  • Detection Studio  │◄──►│  • SIEM Monitoring   │    │  • WebSocket Events    │ ││
│  │  │    (iframe embed)    │    │  • Entity Investigation│   │                        │ ││
│  │  └──────────┬───────────┘    └──────────┬───────────┘    └───────────┬────────────┘ ││
│  └─────────────┼────────────────────────────┼───────────────────────────┼──────────────┘│
│                │                            │                           │               │
│                ▼                            ▼                           ▼               │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                              NGINX REVERSE PROXY                                     ││
│  │                                   (Port 80)                                          ││
│  │                                                                                      ││
│  │   /              → Flutter Web (static)      /sanctions/   → Sanctions Service      ││
│  │   /siem/         → Next.js Dashboard         /monitoring/  → Monitoring Service     ││
│  │   /api/          → Orchestrator              /geo/         → Geographic Risk        ││
│  │   /risk/         → Risk Engine               /integrity/   → Integrity Service      ││
│  │   /_next/        → Next.js Assets                                                   ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                │              │              │              │              │             │
│                ▼              ▼              ▼              ▼              ▼             │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                              BACKEND SERVICES LAYER                                  ││
│  │                                                                                      ││
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐         ││
│  │  │  Orchestrator │  │ Risk Engine   │  │  Sanctions    │  │  Monitoring   │         ││
│  │  │  (Port 8007)  │  │ (Port 8000)   │  │  (Port 8004)  │  │  (Port 8005)  │         ││
│  │  │               │  │               │  │               │  │               │         ││
│  │  │ • Profile Mgmt│  │ • GraphSAGE   │  │ • OFAC/HMT    │  │ • 6 AML Rules │         ││
│  │  │ • Tx Evaluate │  │ • LGBM        │  │ • EU/UN Lists │  │ • Alert Mgmt  │         ││
│  │  │ • Compliance  │  │ • XGBoost     │  │ • Address DB  │  │ • Thresholds  │         ││
│  │  │   Decisions   │  │ • Linear Meta │  │ • Name Match  │  │ • Reporting   │         ││
│  │  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘         ││
│  │          │                  │                  │                  │                 ││
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐         ││
│  │  │ Geographic    │  │  Integrity    │  │  Oracle       │  │   Graph DB    │         ││
│  │  │ Risk (8006)   │  │  Svc (8008)   │  │  Service      │  │  (Memgraph)   │         ││
│  │  │               │  │               │  │               │  │               │         ││
│  │  │ • FATF Lists  │  │ • UI Verify   │  │ • Chainlink   │  │ • Entity Rel  │         ││
│  │  │ • Country Risk│  │ • Tamper Det  │  │ • Price Feed  │  │ • Risk Paths  │         ││
│  │  │ • Travel Rule │  │ • Hash Check  │  │ • Off-chain   │  │ • Clustering  │         ││
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
│  │  │  │                 │  │                 │  │   Resolver      │                 │││
│  │  │  │ • Risk Oracle   │  │ • Policy CRUD   │  │                 │                 │││
│  │  │  │ • Tx Validation │  │ • Threshold Mgmt│  │ • Kleros Integ  │                 │││
│  │  │  │ • Escrow Logic  │  │ • Role Access   │  │ • Arbitration   │                 │││
│  │  │  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │││
│  │  │                                                                                 │││
│  │  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │││
│  │  │  │   AMTTPNFT      │  │ AMTTPCrossChain │  │ AMTTPRiskRouter │                 │││
│  │  │  │                 │  │                 │  │                 │                 │││
│  │  │  │ • KYC Badges    │  │ • LayerZero     │  │ • ML Routing    │                 │││
│  │  │  │ • Compliance ID │  │ • Bridge Safety │  │ • Score Relay   │                 │││
│  │  │  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │││
│  │  └─────────────────────────────────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                              DATA STORAGE LAYER                                      ││
│  │                                                                                      ││
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐         ││
│  │  │   MongoDB     │  │    MinIO      │  │    Redis      │  │   Helia       │         ││
│  │  │               │  │   (S3-compat) │  │   (Cache)     │  │   (IPFS)      │         ││
│  │  │               │  │               │  │               │  │               │         ││
│  │  │ • Profiles    │  │ • ML Models   │  │ • Sessions    │  │ • Audit Logs  │         ││
│  │  │ • Alerts      │  │ • Audit Logs  │  │ • Rate Limits │  │ • Evidence    │         ││
│  │  │ • Tx History  │  │ • Evidence    │  │ • Hot Data    │  │ • Compliance  │         ││
│  │  └───────────────┘  └───────────────┘  └───────────────┘  └───────────────┘         ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Architecture

### Frontend Components

| Component | Technology | Port | Description |
|-----------|------------|------|-------------|
| Flutter Web App | Dart/Flutter | 80 (static) | Main user interface for wallet operations |
| Next.js Dashboard | React/Next.js 15 | 3005 (internal) | SIEM dashboard, compliance views |
| Detection Studio | Embedded iframe | - | Next.js embedded in Flutter |

### Backend Services

| Service | Technology | Port | Health Endpoint | Description |
|---------|------------|------|-----------------|-------------|
| Orchestrator | Python/FastAPI | 8007 | `/health` | Central compliance coordinator |
| Risk Engine | Python/FastAPI | 8000 | `/health` | Stacked ensemble ML scoring |
| Sanctions | Python/FastAPI | 8004 | `/health` | OFAC/HMT/EU/UN screening |
| Monitoring | Python/FastAPI | 8005 | `/health` | AML rule engine |
| Geographic Risk | Python/FastAPI | 8006 | `/health` | FATF/country risk |
| Integrity | Python/FastAPI | 8008 | `/health` | UI tamper detection |

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
| AMTTPCore | Ethereum | Main protocol logic, risk oracle integration |
| AMTTPPolicyManager | Ethereum | Policy CRUD, threshold management |
| AMTTPPolicyEngine | Ethereum | Rule evaluation engine |
| AMTTPDisputeResolver | Ethereum | Kleros arbitration integration |
| AMTTPNFT | Ethereum | KYC/compliance NFT badges |
| AMTTPCrossChain | Ethereum | LayerZero bridge integration |
| AMTTPRiskRouter | Ethereum | ML score routing |

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

### Docker Unified Deployment

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
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                        VOLUME MOUNTS                                         │    │
│  │                                                                              │    │
│  │  /var/www/flutter    ← Flutter web build (static files)                     │    │
│  │  /app/nextjs         ← Next.js application                                  │    │
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
│   :8080      │               │   :8545      │               │   :8200      │
└──────────────┘               └──────────────┘               └──────────────┘
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

## API Reference

### Service Endpoints

#### Orchestrator (Port 8007 via /api/)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Service health check |
| POST | `/api/evaluate` | Evaluate transaction compliance |
| GET | `/api/profiles/{address}` | Get entity profile |
| POST | `/api/profiles/{address}/set-type/{type}` | Set profile type |

#### Sanctions (Port 8004 via /sanctions/)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sanctions/health` | Service health |
| POST | `/sanctions/check` | Check address/name |
| GET | `/sanctions/stats` | Database statistics |

#### Monitoring (Port 8005 via /monitoring/)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/monitoring/health` | Service health |
| GET | `/monitoring/alerts` | List alerts |
| POST | `/monitoring/analyze` | Analyze transaction |

#### Geographic Risk (Port 8006 via /geo/)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/geo/health` | Service health |
| GET | `/geo/risk/{country_code}` | Get country risk |
| GET | `/geo/lists/fatf-black` | FATF blacklist |
| GET | `/geo/lists/fatf-grey` | FATF greylist |

#### Risk Engine (Port 8000 via /risk/)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/risk/health` | Service health |
| POST | `/risk/score` | Get ML risk score |
| POST | `/risk/hybrid` | Ensemble scoring |

---

## Quick Start

### Local Development

```bash
# Start unified container
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

### Public Exposure (ngrok)

```bash
# Start tunnel
ngrok http 80

# Set environment for Next.js dev
set NEXT_PUBLIC_GATEWAY_ORIGIN=https://your-tunnel.ngrok-free.app
npm run dev:turbo

# Set dart-define for Flutter
flutter run -d chrome --web-port=3003 \
  --dart-define=API_BASE_URL=https://your-tunnel.ngrok-free.app \
  --dart-define=DETECTION_STUDIO_URL=https://your-tunnel.ngrok-free.app/siem/
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | Jan 2026 | Unified Docker, nginx proxy, iframe embedding |
| 1.0 | Dec 2025 | Initial architecture |
