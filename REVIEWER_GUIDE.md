# AMTTP — Reviewer Guide

**Anti-Money Laundering Transaction Trust Protocol, Version 4.0**
Author: Odeyemi Olusegun Israel | Derby, UK | segettii@gmail.com

---

## Quick Navigation

| What you want to see | Where to find it |
|---|---|
| **Paper (LaTeX source)** | Submit via Overleaf; source in author's local copy |
| **Smart contracts (18 Solidity)** | [`contracts/`](contracts/) |
| **Backend microservices (4)** | [`backend/`](backend/) |
| **ML training pipeline** | [`pipeline/`](pipeline/) + [`notebooks/`](notebooks/) |
| **Frontend apps** | [`frontend/`](frontend/) (Flutter + Next.js) |
| **All test scripts** | [`tests/`](tests/) ← **start here for verification** |
| **Pre-computed results** | [`data/external_validation/`](data/external_validation/) |
| **BSDT companion paper data** | [`papers/`](papers/) |
| **Docker deployment** | [`docker-compose.yml`](docker-compose.yml) |
| **Security audit material** | [`audit/`](audit/) |

---

## Repository Structure

```
amttp/
├── README.md                   Project overview
├── REVIEWER_GUIDE.md           ← You are here
├── CHANGELOG.md                Version history
│
├── contracts/                  18 Solidity smart contracts (Sepolia)
│   ├── AMTTPCore.sol           Risk oracle, escrow, threshold signatures
│   ├── AMTTPCoreSecure.sol     Hardened variant with reentrancy guards
│   ├── AMTTPCrossChain.sol     LayerZero cross-chain relay
│   ├── AMTTPDisputeResolver.sol Kleros arbitration integration
│   ├── AMTTPNFT.sol            KYC credential badges (ERC-721)
│   ├── AMTTPPolicyEngine.sol   Rule & threshold configuration
│   ├── AMTTPRiskRouter.sol     Multi-chain score routing
│   └── zknaf/                  Groth16 zero-knowledge circuits
│
├── backend/                    4 FastAPI microservices
│   ├── auth-gateway/           JWT + RBAC authentication
│   ├── compliance-service/     Orchestrator, decision matrix
│   ├── oracle-service/         ML risk engine (production CPU)
│   └── policy-service/         Policy management
│
├── pipeline/                   Offline ML training pipeline
│   ├── step0_fetch_bigquery.py Data acquisition (BigQuery/Etherscan)
│   ├── step1_pattern_detection.py FATF AML pattern scoring
│   ├── step2_build_labeled_dataset.py Teacher pseudo-labelling
│   ├── step3_relabel_teacher.py Teacher composite fusion
│   ├── step4_create_gat_dataset.py GNN dataset preparation
│   └── step5_validate_metrics.py Pipeline validation
│
├── notebooks/                  Jupyter notebooks (Colab GPU training)
│   ├── vae_gnn_pipeline_v2.ipynb  β-VAE + GNN + XGBoost full pipeline
│   ├── cross_validate_external.ipynb External dataset evaluation
│   └── pac_bayes_security_proofs.ipynb Formal verification (§VI-H)
│
├── frontend/
│   ├── amttp_app/              Flutter consumer app (MetaMask)
│   └── frontend/               Next.js War Room dashboard
│
├── tests/                      ★ Organised test suite (see tests/README.md)
│   ├── smart-contracts/        Hardhat + Foundry contract tests
│   ├── ml-pipeline/            Model evaluation & cross-validation
│   ├── api-integration/        End-to-end API tests (53 routes)
│   ├── ui/                     Browser interaction tests (32 tests)
│   ├── external-validation/    Cross-domain dataset tests
│   └── security/               Slither, Echidna, zkNAF tests
│
├── data/
│   └── external_validation/    Pre-computed evaluation results
│       ├── cross_validation_v2_results.json   5-fold CV (Table VI)
│       ├── cross_validation_results.json      External datasets (Table VIII)
│       ├── elliptic/            Elliptic Bitcoin dataset
│       ├── xblock/              XBlock Ethereum Phishing dataset
│       ├── forta/               Forta threat intelligence
│       └── odds/                ODDS benchmark datasets
│
├── papers/                     Companion BSDT theory + evidence
│   ├── blind_spot_decomposition_theory.md  Full theory paper
│   └── bsdt_evidence.json     36-combination evaluation data
│
├── reports/
│   └── publishing/             Publication-ready metrics & drafts
│
├── audit/                      Security audit tools & reports
│   ├── SECURITY_AUDIT_REPORT.md
│   └── slither.config.json
│
├── docs/                       Technical documentation
├── docker-compose.yml          17-service deployment stack
├── Dockerfile                  Production container
├── hardhat.config.cjs          Smart contract tooling config
├── foundry.toml                Foundry fuzz test config
├── package.json                Node.js dependencies
│
└── _archive/                   Historical build logs & drafts (not for review)
```

---

## How to Verify Key Claims

### Claim 1: Five-fold CV ROC-AUC = 0.9965 (Table VI)
```bash
# Pre-computed results:
cat data/external_validation/cross_validation_v2_results.json
# Reproduction:
python tests/ml-pipeline/cross_validate_v2_model.py
```

### Claim 2: External dataset generalization (Tables VIII–IX)
```bash
cat data/external_validation/cross_validation_results.json
cat reports/publishing/etherscan_validation_metrics.json
```

### Claim 3: Gas benchmarks (Table X)
```bash
npx hardhat test test/GasAnalysis.test.mjs
```

### Claim 4: 53 API routes pass, 32 UI tests pass (§VI-J)
```bash
python tests/api-integration/automated_testing.py
python tests/ui/browser_ui_test.py
```

### Claim 5: Smart contract security
```bash
# Slither static analysis
cd audit && ./run-audit.ps1
# Foundry fuzz testing
forge test --match-path test/foundry/*.sol -vvv
```

---

## Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Smart Contracts | Solidity | 0.8.24 |
| Contract Testing | Hardhat + Foundry | 2.22 / 0.2 |
| Backend APIs | FastAPI (Python) | 0.104+ |
| ML Models | XGBoost, LightGBM, PyTorch | 2.1 / 4.3 / 2.1 |
| Graph DB | Memgraph | 2.x |
| Frontend (Consumer) | Flutter + Dart | 3.x |
| Frontend (Dashboard) | Next.js + React | 14.x |
| Deployment | Docker Compose | 17 services |
| Zero-Knowledge | Groth16 (snarkjs) | — |
| Blockchain | Ethereum Sepolia testnet | — |

---

## Source Code

Full repository: https://github.com/segetii/fintech
