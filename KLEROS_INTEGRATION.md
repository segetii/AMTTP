# AMTTP Architecture with Kleros Dispute Resolution

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AMTTP FRAUD DETECTION SYSTEM                       │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────────┐
                              │  Users/dApps/    │
                              │  Wallets/CEX     │
                              └────────┬─────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              API LAYER                                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐               │
│  │  Client SDK     │  │  Python SDK     │  │  REST API       │               │
│  │  (TypeScript)   │  │  (AMTTP Client) │  │  (FastAPI)      │               │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘               │
└───────────┼────────────────────┼────────────────────┼────────────────────────┘
            │                    │                    │
            └────────────────────┼────────────────────┘
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         ML RISK ENGINE (Hybrid API)                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐               │
│  │  XGBoost Model  │  │  Graph Analysis │  │  Pattern Rules  │               │
│  │  (Trained on    │  │  (Memgraph)     │  │  (FAN_OUT,      │               │
│  │   real fraud)   │  │                 │  │   SMURFING...)  │               │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘               │
│           │                    │                    │                        │
│           └────────────────────┼────────────────────┘                        │
│                                ▼                                             │
│                    ┌───────────────────────┐                                 │
│                    │  Multi-Signal Scorer  │                                 │
│                    │  (2+ signals = HIGH)  │                                 │
│                    └───────────┬───────────┘                                 │
└────────────────────────────────┼─────────────────────────────────────────────┘
                                 │
                                 ▼ Risk Score (0-1000)
┌──────────────────────────────────────────────────────────────────────────────┐
│                         SMART CONTRACT LAYER                                  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │                    AMTTPPolicyEngine (UUPS Proxy)                   │     │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │     │
│  │  │ User Policy │  │ Risk Policy │  │ Compliance  │                 │     │
│  │  │ (limits,    │  │ (thresholds │  │ (KYC,       │                 │     │
│  │  │  allowlist) │  │  actions)   │  │  approvers) │                 │     │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                 │     │
│  │                                                                     │     │
│  │  ┌─────────────────────────────────────────────────────────────┐   │     │
│  │  │             DECISION ROUTER                                  │   │     │
│  │  │  riskScore < 400  →  APPROVE (auto-execute)                 │   │     │
│  │  │  riskScore < 700  →  FLAG (review required)                 │   │     │
│  │  │  riskScore >= 700 →  ESCROW (Kleros dispute)                │   │     │
│  │  └─────────────────────────────────────────────────────────────┘   │     │
│  └──────────────────────────────────┬──────────────────────────────────┘     │
│                                     │                                        │
│                    ┌────────────────┼────────────────┐                       │
│                    ▼                ▼                ▼                       │
│              ┌──────────┐    ┌──────────┐    ┌──────────────────┐            │
│              │ APPROVE  │    │  FLAG    │    │ ROUTE TO KLEROS  │            │
│              │ Execute  │    │ Pending  │    │ Escrow Funds     │            │
│              │ Transfer │    │ Review   │    │                  │            │
│              └──────────┘    └──────────┘    └────────┬─────────┘            │
│                                                       │                      │
└───────────────────────────────────────────────────────┼──────────────────────┘
                                                        │
                                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      KLEROS DISPUTE RESOLUTION                               │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │                    AMTTPDisputeResolver                              │     │
│  │                                                                      │     │
│  │  1. escrowTransaction()  - Hold funds with ML evidence              │     │
│  │  2. Challenge Window     - 24 hours for anyone to dispute           │     │
│  │  3. challengeTransaction() - Create Kleros dispute (pay fee)        │     │
│  │  4. submitEvidence()     - Both parties submit evidence             │     │
│  │                                                                      │     │
│  └──────────────────────────────────┬──────────────────────────────────┘     │
│                                     │                                        │
│                    ┌────────────────┼────────────────┐                       │
│                    ▼                                 ▼                       │
│         ┌─────────────────────┐           ┌─────────────────────┐           │
│         │  NO CHALLENGE       │           │  CHALLENGED         │           │
│         │  (24h passes)       │           │  (Dispute created)  │           │
│         │                     │           │                     │           │
│         │  → Auto-approve     │           │  → Kleros Court     │           │
│         │  → Release funds    │           │  → Jurors vote      │           │
│         └─────────────────────┘           └──────────┬──────────┘           │
│                                                      │                       │
│                                                      ▼                       │
│                                           ┌─────────────────────┐           │
│                                           │   KLEROS COURT      │           │
│                                           │   (On-chain)        │           │
│                                           │                     │           │
│                                           │  • 3 Jurors minimum │           │
│                                           │  • Review evidence  │           │
│                                           │  • Vote: 1=Approve  │           │
│                                           │         2=Reject    │           │
│                                           └──────────┬──────────┘           │
│                                                      │                       │
│                                     ┌────────────────┼────────────────┐      │
│                                     ▼                                ▼      │
│                           ┌─────────────────┐              ┌─────────────────┐
│                           │  RULING: 1      │              │  RULING: 2      │
│                           │  APPROVE        │              │  REJECT         │
│                           │                 │              │                 │
│                           │  → Release to   │              │  → Return to    │
│                           │    recipient    │              │    sender       │
│                           └─────────────────┘              └─────────────────┘
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────────┐
                              │   SIEM Dashboard │
                              │   (Next.js)      │
                              │                  │
                              │  • Alert Table   │
                              │  • Risk Charts   │
                              │  • Investigation │
                              │  • Dispute Status│
                              └──────────────────┘
```

## Contract Addresses

| Contract | Network | Address |
|----------|---------|---------|
| Kleros Arbitrator | Sepolia | `0x90992fb4E15ce0C59aEFfb376460Fdc4Bfa6E1f6` |
| Kleros Arbitrator | Mainnet | `0x988b3A538b618C7A603e1c11Ab82Cd16dbE28069` |
| AMTTPDisputeResolver | Sepolia | TBD (after deployment) |
| AMTTPPolicyEngine | Sepolia | TBD (after deployment) |
| AMTTPPolicyEngine | Hardhat Local | `0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0` |

## Transaction Flow

### Normal Transaction (Low Risk)
```
User → API → ML Score (350) → PolicyEngine → APPROVE → Execute Transfer
```

### Flagged Transaction (Medium Risk)
```
User → API → ML Score (550) → PolicyEngine → FLAG → Review Queue → Manual Decision
```

### Disputed Transaction (High Risk)
```
User → API → ML Score (750) → PolicyEngine → ESCROW → DisputeResolver
                                                         │
                                         ┌───────────────┴───────────────┐
                                         │                               │
                                    No Challenge                    Challenge
                                    (24h timeout)                   (Kleros)
                                         │                               │
                                         ▼                               ▼
                                   Auto-Release                   Juror Vote
                                   to Recipient                        │
                                                          ┌────────────┴────────────┐
                                                          │                         │
                                                     Approve (1)              Reject (2)
                                                          │                         │
                                                     Release to              Return to
                                                     Recipient               Sender
```

## Evidence Structure (IPFS)

```json
{
  "title": "AMTTP Fraud Detection Evidence",
  "description": "ML-based fraud detection evidence for transaction dispute",
  "transaction": {
    "txId": "0x...",
    "from": "0x...",
    "to": "0x...",
    "value": "1.5 ETH",
    "timestamp": "2025-12-22T10:00:00Z"
  },
  "riskAssessment": {
    "mlScore": 0.78,
    "graphScore": 0.65,
    "patternScore": 0.85,
    "combinedScore": 780,
    "signals": ["FAN_OUT", "SMURFING", "ROUND_AMOUNTS"],
    "signalCount": 3,
    "confidence": 0.92
  },
  "graphAnalysis": {
    "degree": 45,
    "clustering": 0.12,
    "pageRank": 0.0023,
    "connectedToKnownFraud": true
  },
  "historicalData": {
    "totalTransactions": 156,
    "flaggedTransactions": 23,
    "previousDisputes": 2
  }
}
```

## Deployment Commands

### Local Testing (Hardhat)
```bash
npx hardhat node
npx hardhat run scripts/deploy-with-kleros.cjs --network localhost
```

### Sepolia Testnet
```bash
npx hardhat run scripts/deploy-with-kleros.cjs --network sepolia
```

### Verify Contracts
```bash
npx hardhat verify --network sepolia <CONTRACT_ADDRESS> <CONSTRUCTOR_ARGS>
```
