# AMTTP Protocol — Three-Layer System Architecture

> **IEEE Technical White Paper Diagram**  
> Version 1.0 | February 2026  
> Anti-Money Laundering Transaction Trust Protocol (AMTTP)

---

## Architecture Overview

The AMTTP Protocol follows a three-layer architecture pattern. Transactions flow top-down from the Integration Layer through the Protocol Logic & Computation layer (The Singular Stack) to the Production & Deployment infrastructure.

### Layer Summary

| Layer | Purpose | Key Components |
|-------|---------|----------------|
| **I — Integration & Access** | External-facing interfaces | SDK, REST API, Web Apps (Flutter + Next.js) |
| **II — Protocol Logic (The Singular Stack)** | Compliance computation | Identity Mgmt, Tx Sequencing, Graph-Powered Risk Engine |
| **III — Production & Deployment** | Infrastructure & persistence | API Gateway, On-Chain Contracts, Databases, Cloud Hosting |

---

## Mermaid.js Diagram

```mermaid
graph TB
    classDef integrationLayer fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef logicLayer fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef productionLayer fill:#FFF3E0,stroke:#E65100,stroke-width:2px,color:#BF360C
    classDef protocolCore fill:#F3E5F5,stroke:#6A1B9A,stroke-width:2px,color:#4A148C
    classDef riskEngine fill:#FCE4EC,stroke:#B71C1C,stroke-width:2px,color:#B71C1C
    classDef dataLayer fill:#ECEFF1,stroke:#37474F,stroke-width:2px,color:#263238
    classDef arrow stroke:#455A64,stroke-width:1.5px

    subgraph L1["<b>LAYER I — INTEGRATION & ACCESS</b>"]
        direction TB
        SDK["<b>AMTTP Open-Source SDK</b><br/><i>TypeScript / Python Client Library</i><br/>──────────────────<br/>• Transaction Construction<br/>• Wallet Signature (EIP-712)<br/>• WebSocket Event Streaming<br/>• Batch Scoring Interface"]
        API_IF["<b>RESTful API Interface</b><br/><i>JSON/HTTP + WebSocket</i><br/>──────────────────<br/>• POST /evaluate<br/>• POST /score/address<br/>• GET /profiles/{addr}<br/>• SSE /webhook/stream"]
        WEBAPP["<b>Web Application Layer</b><br/><i>Flutter Consumer App + Next.js War Room</i><br/>──────────────────<br/>• MetaMask Wallet Integration<br/>• Compliance Dashboard (RBAC R1–R6)<br/>• Detection Studio & Graph Explorer<br/>• zkNAF Proof Verification UI"]
    end

    subgraph L2["<b>LAYER II — PROTOCOL LOGIC & COMPUTATION (The Singular Stack)</b>"]
        direction TB
        ORCH["<b>Compliance Orchestrator</b><br/><i>Central Decision Coordinator</i><br/>──────────────────<br/>• Fan-out to downstream services<br/>• Aggregate multi-signal decisions<br/>• Profile & entity management<br/>• API key issuance & RBAC"]

        subgraph IDENTITY["<b>§2.1 Identity Management Module</b>"]
            direction LR
            SANC["<b>Sanctions Screening</b><br/><i>OFAC · HMT · EU · UN</i><br/>──────────────<br/>7,800+ entities<br/>22 crypto addresses<br/>Fuzzy name matching"]
            KYC["<b>KYC / PEP / EDD</b><br/><i>Enhanced Due Diligence</i><br/>──────────────<br/>PEP database screening<br/>Dual-control label submission<br/>Travel Rule (FATF Rec. 16)"]
            ZKNAF["<b>zkNAF Proofs</b><br/><i>Zero-Knowledge Compliance</i><br/>──────────────<br/>KYC Credential Circuit<br/>Risk Range Proof<br/>Sanctions Non-Membership"]
        end

        subgraph TXSEQ["<b>§2.2 Transaction Sequencing Module</b>"]
            direction LR
            MON["<b>AML Monitoring Engine</b><br/><i>6 Detection Rules</i><br/>──────────────<br/>Large Tx Detection<br/>Rapid Succession<br/>Structuring (Smurfing)<br/>Mixer Interaction<br/>Dormant Account<br/>FATF Jurisdiction Block"]
            POL["<b>Policy Engine</b><br/><i>Configurable Rulesets</i><br/>──────────────<br/>Policy CRUD lifecycle<br/>Whitelist / Blacklist<br/>Threshold management<br/>Per-entity evaluation"]
            GEO["<b>Geographic Risk</b><br/><i>Jurisdiction Analysis</i><br/>──────────────<br/>FATF Black / Grey Lists<br/>EU High-Risk (14 countries)<br/>Tax Haven Detection<br/>IP Geolocation Risk"]
        end

        subgraph RISK["<b>§2.3 Graph-Powered Risk Engine (ML/DL Heuristics)</b>"]
            direction TB
            FEAT["<b>Feature Extraction</b><br/><i>Multi-Modal Encoding</i><br/>──────────────────<br/>• VAE Latent Features (anomaly compression)<br/>• GraphSAGE Embeddings (structural topology)<br/>• Memgraph Entity-Relationship Clustering"]
            ENSEMBLE["<b>Stacked Ensemble Classifier</b><br/><i>Knowledge Distillation Pipeline</i><br/>──────────────────<br/>• Base: XGBoost v1 (Kaggle ETH Fraud)<br/>• L1: GraphSAGE · LightGBM · XGBoost v2<br/>• Meta: Linear Meta-Learner (α₁·f₁ + α₂·f₂ + α₃·f₃)<br/>• Output: P(fraud) ∈ [0, 1]"]
            XAI["<b>Explainability Module</b><br/><i>Regulatory Transparency (XAI)</i><br/>──────────────────<br/>• SHAP feature attribution<br/>• Typology classification<br/>• FCA/AMLD6 audit trail"]
        end

        DECISION["<b>Compliance Decision Matrix</b><br/><i>Deterministic Action Resolution</i><br/>──────────────────<br/>P < 0.4 ∧ ¬sanctioned ∧ geo=LOW → <b>ALLOW</b><br/>0.4 ≤ P < 0.7 ∧ ¬sanctioned → <b>REVIEW</b><br/>P ≥ 0.7 ∧ ¬sanctioned → <b>ESCROW</b><br/>sanctioned ∨ FATF_blacklist → <b>BLOCK</b>"]
    end

    subgraph L3["<b>LAYER III — PRODUCTION & DEPLOYMENT</b>"]
        direction TB
        GW["<b>API Gateway</b><br/><i>NGINX Reverse Proxy</i><br/>──────────────────<br/>• TLS termination<br/>• Rate limiting (100 req/s API)<br/>• Path-based routing (/api, /risk, /geo, ...)<br/>• Cloudflare Tunnel (production)"]

        subgraph CHAIN["<b>§3.1 On-Chain Verification (Ethereum)</b>"]
            direction LR
            CORE["<b>AMTTPCore</b><br/>Risk Oracle<br/>Escrow Logic<br/>Tx Validation"]
            NFT["<b>AMTTPNFT</b><br/>KYC Badges<br/>Compliance ID"]
            DISPUTE["<b>DisputeResolver</b><br/>Kleros Arbitration<br/>MetaEvidence"]
            CROSS["<b>CrossChain</b><br/>LayerZero Bridge<br/>Score Relay"]
        end

        subgraph DATA["<b>§3.2 Data Persistence Layer</b>"]
            direction LR
            MONGO["<b>MongoDB</b><br/><i>Document Store</i><br/>────────<br/>Profiles<br/>Alerts<br/>Tx History"]
            REDIS["<b>Redis</b><br/><i>Cache Layer</i><br/>────────<br/>Sessions<br/>Rate Limits<br/>Hot Data"]
            MEMGRAPH["<b>Memgraph</b><br/><i>Graph Database</i><br/>────────<br/>Entity Relations<br/>Risk Paths<br/>Clustering"]
            IPFS["<b>Helia (IPFS)</b><br/><i>Immutable Store</i><br/>────────<br/>Audit Logs<br/>Evidence<br/>Compliance"]
        end

        CLOUD["<b>Cloud Infrastructure</b><br/><i>Container Orchestration</i><br/>──────────────────<br/>• Docker Compose (multi-mode: unified / full-stack / production)<br/>• Supervisord process management<br/>• Prometheus + Grafana observability<br/>• HashiCorp Vault (secrets management)"]
    end

    SDK -->|"HTTP/WS<br/>JSON payload"| API_IF
    API_IF -->|"Browser / Mobile"| WEBAPP
    API_IF -->|"Authenticated request"| GW

    GW -->|"Route: /api/*"| ORCH

    ORCH -->|"§2.1 Identity<br/>verification"| IDENTITY
    ORCH -->|"§2.2 Transaction<br/>rule evaluation"| TXSEQ
    ORCH -->|"§2.3 ML risk<br/>scoring request"| RISK

    SANC --- KYC --- ZKNAF
    MON --- POL --- GEO

    FEAT -->|"Feature vector<br/>x ∈ ℝᵈ"| ENSEMBLE
    ENSEMBLE -->|"P(fraud), SHAP values"| XAI

    IDENTITY -->|"sanctions_hit: bool<br/>kyc_status: enum"| DECISION
    TXSEQ -->|"rule_alerts: list<br/>geo_risk: enum"| DECISION
    XAI -->|"risk_score: float<br/>explanations: list"| DECISION

    DECISION -->|"action ∈ {ALLOW,<br/>REVIEW, ESCROW, BLOCK}"| GW

    GW -->|"On-chain verification<br/>(if ALLOW)"| CHAIN
    CORE --- NFT --- DISPUTE --- CROSS

    ORCH -->|"Read/Write"| DATA
    ENSEMBLE -->|"Graph queries"| MEMGRAPH
    ORCH -->|"Audit persistence"| IPFS

    GW -->|"Deployed on"| CLOUD
    DATA -->|"Hosted within"| CLOUD

    class SDK,API_IF,WEBAPP integrationLayer
    class ORCH,DECISION logicLayer
    class SANC,KYC,ZKNAF logicLayer
    class MON,POL,GEO logicLayer
    class FEAT,ENSEMBLE,XAI riskEngine
    class GW,CLOUD productionLayer
    class CORE,NFT,DISPUTE,CROSS protocolCore
    class MONGO,REDIS,MEMGRAPH,IPFS dataLayer
```

---

## Transaction Flow Summary

1. **SDK → API Interface**: Client constructs a transaction via the AMTTP SDK (TypeScript/Python), signs with EIP-712, and submits via HTTP/WebSocket.
2. **API Gateway Routing**: The NGINX gateway terminates TLS, applies rate limiting, and routes to the Compliance Orchestrator.
3. **Parallel Module Evaluation**:
   - **§2.1 Identity Management**: Sanctions screening (OFAC/HMT/EU/UN), KYC/PEP verification, zkNAF zero-knowledge proofs.
   - **§2.2 Transaction Sequencing**: 6 AML detection rules, policy engine evaluation, geographic risk analysis.
   - **§2.3 Risk Engine**: Feature extraction (VAE + GraphSAGE) → Stacked Ensemble (XGBoost + LightGBM + GraphSAGE → Meta-Learner) → SHAP Explainability.
4. **Compliance Decision Matrix**: Deterministic resolution — P(fraud) thresholds and sanctions status map to {ALLOW, REVIEW, ESCROW, BLOCK}.
5. **On-Chain Verification**: Allowed transactions are recorded via Ethereum smart contracts (AMTTPCore, AMTTPNFT, DisputeResolver, CrossChain).
6. **Data Persistence**: All results persisted across MongoDB, Redis, Memgraph, and Helia/IPFS for audit compliance.

---

## Color Legend

| Color | Layer | Scope |
|-------|-------|-------|
| 🔵 Blue (`#E3F2FD`) | Integration & Access | SDK, API, Web Apps |
| 🟢 Green (`#E8F5E9`) | Protocol Logic | Orchestrator, Identity, Tx Sequencing, Decision Matrix |
| 🔴 Red (`#FCE4EC`) | Risk Engine | Feature Extraction, Ensemble Classifier, Explainability |
| 🟠 Orange (`#FFF3E0`) | Production | API Gateway, Cloud Infrastructure |
| 🟣 Purple (`#F3E5F5`) | On-Chain | Ethereum Smart Contracts |
| ⚪ Grey (`#ECEFF1`) | Data Layer | MongoDB, Redis, Memgraph, IPFS |

---

*Document generated for IEEE Technical White Paper submission — AMTTP Protocol v3.0*
