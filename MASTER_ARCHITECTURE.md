# AMTTP — Master Architecture & Deployment Reference

> **Last updated:** 2026-04-12  
> **Deployer wallet:** `0xBc270F0ce5bbE8Ed8489f11262eF1a1527CaF23F`  
> **Network:** Ethereum Sepolia + Base Sepolia + Arbitrum Sepolia (L2)

---

## 1. System Architecture

```
                    ┌─────────────────────────────┐
                    │     Cloudflare Tunnel        │
                    │     amttp.com → gateway:80   │
                    └──────────┬──────────────────┘
                               │
                    ┌──────────▼──────────────────┐
                    │   nginx Gateway (:8888→80)    │
                    │   Rate limit, CORS, routing   │
                    └──────────┬──────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                     │
  ┌───────▼───────┐   ┌───────▼───────┐   ┌────────▼────────┐
  │  Next.js War  │   │  Orchestrator │   │  Flutter App    │
  │  Room (:3006) │   │  (:8007)      │   │  (:3010/8889)   │
  │  R3-R6 Users  │   │  API Gateway  │   │  R1-R2 Users    │
  └───────┬───────┘   └───────┬───────┘   └─────────────────┘
          │                    │
          │           ┌────────┼────────────────────────────────┐
          │           │        │        │       │       │       │
          │     ┌─────▼─┐ ┌───▼───┐ ┌──▼──┐ ┌──▼──┐ ┌─▼──┐ ┌─▼──┐
          │     │ML Risk│ │Graph  │ │Sanct│ │Monit│ │Geo │ │FCA │
          │     │:8000  │ │:8001  │ │:8004│ │:8005│ │:8006│ │:8002│
          │     └───────┘ └───────┘ └─────┘ └─────┘ └────┘ └────┘
          │           │        │       │       │       │       │
          │     ┌─────▼────────▼───────▼───────▼───────▼───────▼─┐
          │     │           Infrastructure Layer                  │
          │     │  MongoDB(:27017) Redis(:6379) Memgraph(:7687)  │
          │     │  MinIO(:9000) Vault(:8200) IPFS(:5001)         │
          │     └────────────────────────────────────────────────┘
          │
   ┌──────▼─────────────────────────────────┐
   │           Blockchain Layer              │
   │  Oracle Service (:3001) → RPC Nodes    │
   │  zkNAF Service (:8010) → ZK Proofs     │
   │                                         │
   │  ┌─────────┐ ┌──────────┐ ┌──────────┐ │
   │  │ Sepolia │ │  Base    │ │ Arbitrum │ │
   │  │ LZ:10161│ │ LZ:10245│ │ LZ:10231 │ │
   │  └────┬────┘ └────┬─────┘ └────┬─────┘ │
   │       └──── LayerZero V1 ──────┘        │
   └─────────────────────────────────────────┘
```

---

## 2. Smart Contract Addresses

### 2.1 Ethereum Sepolia (Chain 11155111, LZ 10161)

| Contract | Proxy Address | Type |
|----------|---------------|------|
| AMTTP Token | `0x05687FBb0f8921ff502BdEbC180b24Ed2B14b612` | UUPS |
| PolicyManager | `0x4eECb1348988A041B89acA4Aa9348F6e1DD9BcD3` | UUPS |
| PolicyEngine | `0xe774E01CbFC63cfb64a0ec054821fDb5A61d8703` | UUPS |
| DisputeResolver | `0x9EB935E68DEa685B6feAa9DAB51a46Dcd4da53D7` | UUPS |
| **CrossChain V2** | `0x4f21b16D56e67c8Fa6AB0e3457deAB2805432953` | UUPS |
| RiskRouter | `0xE722A6466F9000e0e891254Dc96Bac6a5a49F932` | UUPS |
| MockArbitrator | `0x86832c8EF025805B2B246c89D6B22b806075A7d1` | Direct |
| SanctionsVerifier | `0xdef3f2fff995eB2B0Cb3577A3cA9B55916005145` | Direct |
| RiskVerifier | `0x434FE5D136C20dF81a2E8240F911c2020C10D3b2` | Direct |
| KYCVerifier | `0xf4BEaF8263cCB9f67736512BC168ea8D5ECBDfaA` | Direct |
| ZkNAFVerifierRouter | `0xa5D36782089002F945167a83Bd3d2a237820F77C` | Direct |
| MockZkNAF | `0x0Ab56245e4CE65c7be788d99aCD5cA592a07E321` | Direct |

**LayerZero V1 Endpoint:** `0xae92d5aD7583AD66E49A0c67BAd18F6ba52dDDc1`  
**Kleros Arbitrator:** `0x90992fB4e15cE0C59AEfFb376460FDc4d1fDD2f8`

### 2.2 Base Sepolia (Chain 84532, LZ 10245)

| Contract | Proxy Address | Type |
|----------|---------------|------|
| PolicyManager | `0x520393A448543FF55f02ddA1218881a8E5851CEc` | UUPS |
| PolicyEngine | `0xc8d887665411ecB4760435fb3d20586C1111bc37` | UUPS |
| **CrossChain V2** | `0x2cF0a1D4FB44C97E80c7935E136a181304A67923` | UUPS |
| RiskRouter | `0xCE9Ee9c5A0dfe5F7AdF9e5fA1bD03cCBb1Fdb9Fd` | UUPS |
| SanctionsVerifier | `0x80F5ebCC9f672756cDCAbD489375a90835A3fcb8` | Direct |
| RiskVerifier | `0x6d480c511436351d95c52Adf30f43F159E1AEa1c` | Direct |
| KYCVerifier | `0x49Acc645E22c69263fCf7eFC165B6c3018d5Db5f` | Direct |
| ZkNAFVerifierRouter | `0x0bed53eE194365D96B2245D80C628f4f7276856E` | Direct |

**LayerZero V1 Endpoint:** `0x6EDCE65403992e310A62460808c4b910D972f10f`

### 2.3 Arbitrum Sepolia (Chain 421614, LZ 10231)

| Contract | Proxy Address | Type |
|----------|---------------|------|
| PolicyManager | `0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade` | UUPS |
| PolicyEngine | `0xD353597994f9e68b36aDffdF6C07a6F0a033B718` | UUPS |
| **CrossChain V2** | `0xeD749700e531a19eDcB5A709c13d967bbF0fea2f` | UUPS |
| RiskRouter | `0x11D170a86d03285D1Ede6164BE41D1A5F2eB820a` | UUPS |
| SanctionsVerifier | `0xCE9Ee9c5A0dfe5F7AdF9e5fA1bD03cCBb1Fdb9Fd` | Direct |
| RiskVerifier | `0x80F5ebCC9f672756cDCAbD489375a90835A3fcb8` | Direct |
| KYCVerifier | `0x6d480c511436351d95c52Adf30f43F159E1AEa1c` | Direct |
| ZkNAFVerifierRouter | `0x49Acc645E22c69263fCf7eFC165B6c3018d5Db5f` | Direct |

**LayerZero V1 Endpoint:** `0x6EDCE65403992e310A62460808c4b910D972f10f`

### 2.4 Localhost / Hardhat (Chain 31337)

| Contract | Address |
|----------|---------|
| AMTTP Token | `0x0DCd1Bf9A1b36cE34237eEaFef220932846BCD82` |
| PolicyManager | `0xA51c1fc2f0D1a1b8494Ed1FE312d7C3a78Ed91C0` |
| PolicyEngine | `0x0B306BF915C4d645ff596e518fAf3F9669b97016` |
| DisputeResolver | `0x68B1D87F95878fE05B998F19b66F4baba5De1aed` |
| CrossChain | `0x59b670e9fA9D0A427751Af201D676719a970857b` |
| RiskRouter | `0x322813Fd9A801c5507c9de605d63CEA4f2CE6c44` |

### 2.5 Cross-Chain Trusted Remotes (Bidirectional)

```
Sepolia  ←──LZ V1──→  Base Sepolia
   ↕                       ↕
Arbitrum Sepolia ←────→ (both linked)
```

| Source | Destination | LZ Chain ID | Status |
|--------|-------------|-------------|--------|
| Sepolia | Base Sepolia | 10245 | ✅ Linked |
| Sepolia | Arbitrum Sepolia | 10231 | ✅ Linked |
| Base Sepolia | Sepolia | 10161 | ✅ Linked |
| Base Sepolia | Arbitrum Sepolia | 10231 | ✅ Linked |
| Arbitrum Sepolia | Sepolia | 10161 | ✅ Linked |
| Arbitrum Sepolia | Base Sepolia | 10245 | ✅ Linked |

---

## 3. CrossChain V2 Security Features

| Feature | Detail |
|---------|--------|
| Ownership | **Ownable2Step** — requires `acceptOwnership()` |
| Endpoint Change | 48h timelock via `proposeEndpointChange` → `executeEndpointChange` |
| Trusted Remote Validation | Must be exactly 20 bytes (address) or 40 bytes (path) |
| Failed Message Expiry | 7-day window; expired messages auto-cleaned |
| Retry Access | `onlyOwnerOrGuardian` (not public) |
| Reentrancy | `nonReentrant` on all external mutators |
| ETH Recovery | `recoverETH()` for stuck funds; excess auto-refunded |
| Contract Check | `extcodesize` on every endpoint change |
| Guardian Role | Can pause (fast) but cannot unpause or change config |
| Upgrade Cooldown | 24h minimum between UUPS upgrades |
| Auto-Block Threshold | 800 (raised from V1's 700) |
| Risk Score Staleness | 30-day max age; `getAggregatedRiskScore()` returns `isStale` |
| Rate Limiting | Per-chain, per-block configurable |
| Emergency Disconnect | `removeTrustedRemote()` to sever chain links |

---

## 4. RPC Endpoints & Keys

| Network | RPC URL | Provider |
|---------|---------|----------|
| Ethereum Sepolia | `https://sepolia.infura.io/v3/17e45820418f4461a48ceb80774afecb` | Infura |
| Base Sepolia | `https://sepolia.base.org` | Public |
| Arbitrum Sepolia | `https://arb-sepolia.g.alchemy.com/v2/89pxLpYGB_qLyt6T-mVQC` | Alchemy |
| Localhost | `http://127.0.0.1:8545` | Hardhat |

**API Keys:**
- Infura: `17e45820418f4461a48ceb80774afecb`
- Alchemy: `89pxLpYGB_qLyt6T-mVQC`
- Etherscan: `YNX9YKZ4CJ1EV678NR3KGZU2P6353YT7B8`

---

## 5. Service Port Map

### 5.1 Backend Microservices

| Port | Service | Language | Framework |
|------|---------|----------|-----------|
| 3001 | Oracle Service | TypeScript | Express.js |
| 8000 | ML Risk Engine | Python | FastAPI |
| 8001 | Graph Service | Python | FastAPI |
| 8002 | FCA Compliance | Python | FastAPI |
| 8003 | Policy Service | Python | FastAPI |
| 8004 | Sanctions Screening | Python | FastAPI |
| 8005 | AML Monitoring | Python | FastAPI |
| 8006 | GeoRisk Service | Python | FastAPI |
| 8007 | Compliance Orchestrator | Python | FastAPI |
| 8008 | UI Integrity Service | Python | FastAPI |
| 8009 | Explainability (XAI) | Python | FastAPI |
| 8010 | zkNAF Service | TypeScript | Fastify |

### 5.2 Infrastructure

| Port | Service | Version |
|------|---------|---------|
| 27017 | MongoDB | 6.x |
| 6379 | Redis | 7.x |
| 7687 | Memgraph | Latest |
| 9000 | MinIO (S3) | Latest |
| 9001 | MinIO Console | Latest |
| 8200 | HashiCorp Vault | 1.17.6 |
| 5001 | IPFS (Kubo/Helia) | Latest |
| 8545 | Hardhat Node | Local |

### 5.3 Frontend

| Port | Service | Framework | Users |
|------|---------|-----------|-------|
| 3006 | War Room Dashboard | Next.js 14 (App Router) | R3-R6 |
| 3010 | Consumer App (dev) | Flutter Web | R1-R2 |
| 8889 | Consumer App (Docker) | Flutter Web | R1-R2 |
| 8888 | nginx Gateway | nginx | All |

### 5.4 Gateway Routing (nginx :8888 → internal)

| External Path | Internal Target | Service |
|---------------|-----------------|---------|
| `/api/data/*`, `/api/explain`, `/api/sankey` | `nextjs-dashboard:3000` | Next.js data APIs |
| `/api/*` (catch-all) | `orchestrator:8007` | Orchestrator |
| `/risk/*` | `risk-engine:8000` | ML scoring |
| `/sanctions/*` | `sanctions:8004` | OFAC/UN screening |
| `/monitoring/*` | `monitoring:8005` | AML monitoring |
| `/policy/*` | `policy-service:8003` | Policy engine |
| `/geo/*` | `geo-risk:8006` | Geo risk |
| `/graph/*` | `graph-api:8001` | Graph analytics |
| `/fca/*` | `fca-compliance:8002` | FCA compliance |
| `/explain/*` | `explainability:8009` | XAI/SHAP |
| `/integrity/*` | `integrity:8008` | UI integrity |
| `/zknaf/*` | `zknaf:8010` | ZK proofs |
| `/oracle/*` | `oracle-service:3000` | Oracle gateway |
| `/war-room`, `/compliance`, `/` | `nextjs-dashboard:3000` | Dashboard |

---

## 6. RBAC Model

| Role | ID | Level | Interface | Description |
|------|----|-------|-----------|-------------|
| End User | R1 | 1 | Flutter (Focus Mode) | Own transactions only |
| End User PEP | R2 | 2 | Flutter (Focus Mode) | Enhanced features: NFT, cross-chain, zkNAF, Safe |
| Institution Ops | R3 | 3 | Next.js (War Room) | View all tx, Detection Studio, Graph Explorer |
| Institution Compliance | R4 | 4 | Next.js (War Room) | Edit policies, trigger enforcement, multisig |
| Platform Admin | R5 | 5 | Next.js (War Room) | User management, system settings |
| Super Admin | R6 | 6 | Next.js (War Room) | Emergency override, ML retrain, full access |

---

## 7. Database Schema

| Database | Collections/Tables | Record Count |
|----------|--------------------|--------------|
| MongoDB (`amttp`) | 13 collections | ~920K transactions, ~421K flagged, ~452K wallet profiles |
| Redis | Cache layer | TTL 300-3600s, prefix `amttp:` |
| Memgraph | Graph relationships | Wallet → Transaction edges |

---

## 8. ML Pipeline

| Component | Path | Framework |
|-----------|------|-----------|
| Risk Engine API | `ml/Automation/risk_engine/` | FastAPI + scikit-learn + XGBoost |
| Training Pipeline | `ml/Automation/ml_pipeline/` | Polars + NumPy + scikit-learn |
| Models | `ml/Automation/models/cloud/` | joblib + `*_meta.json` |
| Graph ML | `ml/Automation/ml_pipeline/graph_ml/` | Memgraph + networkx |

**Config:** CPU-only (`CUDA_VISIBLE_DEVICES=""`), distilled student model for inference.

---

## 9. Wallet Balances (as of 2026-04-12)

| Network | Address | Balance |
|---------|---------|---------|
| Ethereum Sepolia | `0xBc270F0ce5bbE8Ed8489f11262eF1a1527CaF23F` | ~0.103 ETH |
| Base Sepolia | `0xBc270F0ce5bbE8Ed8489f11262eF1a1527CaF23F` | ~0.030 ETH |
| Arbitrum Sepolia | `0xBc270F0ce5bbE8Ed8489f11262eF1a1527CaF23F` | ~0.030 ETH |

---

## 10. Deployment Scripts Reference

| Script | Purpose | Network |
|--------|---------|---------|
| `scripts/deploy-full-stack.cjs` | Full 13-contract deploy | Any |
| `scripts/deploy-l2.cjs` | L2 deployment (PM, PE, CC, RR, ZkNAF) | baseSepolia, arbitrumSepolia |
| `scripts/upgrade-crosschain-v2.cjs` | Upgrade CrossChain proxy → V2 + real LZ | All 3 |
| `scripts/link-trusted-remotes.cjs` | Bidirectional trusted remote linking | All 3 |
| `scripts/deploy-sepolia-continue.cjs` | Continuation deploy (steps 5-9) | sepolia |

---

## 11. Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| Solidity | 0.8.24 | Smart contracts |
| OpenZeppelin | 4.9.6 | UUPS, Access, Security |
| LayerZero | solidity-examples (GitHub) | Cross-chain messaging |
| Hardhat | 2.26.3 | Dev framework |
| ethers.js | 6.15.0 | Blockchain interaction |
| Next.js | 14.x | War Room dashboard |
| Flutter | 3.x | Consumer app |
| FastAPI | Latest | Python microservices |

---

## 12. How to Start

```powershell
# Full stack (Docker + all services)
.\START_SERVICES.ps1

# Backend only
.\START_SERVICES.ps1 -BackendOnly

# Frontend only
.\START_SERVICES.ps1 -FrontendOnly

# Compile contracts
npx hardhat compile

# Run contract tests
npx hardhat test

# Deploy to Sepolia
npx hardhat run scripts/deploy-full-stack.cjs --network sepolia

# Deploy to L2s
npx hardhat run scripts/deploy-l2.cjs --network baseSepolia
npx hardhat run scripts/deploy-l2.cjs --network arbitrumSepolia

# Link trusted remotes
npx hardhat run scripts/link-trusted-remotes.cjs --network sepolia
npx hardhat run scripts/link-trusted-remotes.cjs --network baseSepolia
npx hardhat run scripts/link-trusted-remotes.cjs --network arbitrumSepolia
```
