# AMTTP: A Privacy-Preserving Protocol for Regulatory Compliance in Decentralized Finance
## Technical Whitepaper for UK Global Talent Visa Endorsement

**Version:** 1.0 (Final Submission)  
**Date:** February 2026  
**Author:** Lead Architect / AMTTP Team  
**Focus Area:** RegTech, Blockchain, Artificial Intelligence  

---

## Abstract

The rapid adoption of Decentralized Finance (DeFi) creates a regulatory and operational gap: how to apply AML-style risk controls without unnecessarily disclosing user data. This whitepaper introduces the **Anti-Money Laundering Transaction Transfer Protocol (AMTTP)** as implemented in the accompanying repository: a prototype that combines (1) multi-signal risk scoring (ML + graph- and pattern-derived signals) and (2) zero-knowledge verifier artifacts (Groth16-style verifiers) that can be used as privacy-preserving checks. This document is written as an implementation report and avoids claims that cannot be directly tied to repository artifacts.

---

## 1. Introduction: The Compliance Paradox

DeFi protocols manage billions in assets yet lack the native controls required for institutional adoption. Current solutions rely on either:
1.  **Centralised Gatekeepers:** Removing the "Decentralized" aspect of DeFi.
2.  **Post-Event Analysis:** Detecting fraud only *after* funds have been stolen or laundered.

AMTTP proposes a third way: **"Security as Protocol Logic."** By moving risk assessment to the pre-execution phase, utilizing an Oracle-driven risk engine, we prevent illicit transactions before they are confirmed on-chain.

## 2. Regulatory Alignment (UK & Global Standards)

AMTTP is engineered specifically to address the requirements of high-standard regulatory environments, with a primary focus on the **UK jurisdiction**.

*   **FCA MLR 2017 (Money Laundering Regulations):** The repository includes risk scoring, policy routing, and audit-style artifacts that can be used to support risk-based controls (see `FCA_COMPLIANCE.md` and the orchestrator code).
*   **FATF "Travel Rule" (Recommendation 16):** This repository contains components relevant to travel-rule style flows (policy/orchestration, identity/KYC-related verifier artifacts), but any operational compliance claim depends on deployment configuration and jurisdiction-specific integration.
*   **SAR workflow support:** The codebase contains data collection and audit trail mechanisms; however, it does not by itself constitute regulatory filing automation without an explicit operational integration.

## 3. Core Technical Innovation

The platform distinguishes itself through three core technical pillars that go beyond standard industry implementations.


### 3.1 The "Graph-Augmented" Active Learning Pipeline
Financial crime evolves faster than static training datasets can capture. In this repository, model updating is implemented as a **staged teacher→pseudo-label→learner pipeline** spanning notebooks and scripts (rather than a fully automated active-learning service loop).

1.  **Phase 1: Bootstrap model training (supervised):**
    The repository contains a teacher-style training notebook (`notebooks/Hope_machine (4).ipynb`) that trains tabular models and exports model artifacts.

2.  **Phase 2: Heuristic and graph/pattern enrichment:**
    The repository implements rule/pattern detectors and graph-informed signals that are incorporated into downstream scoring and dataset construction (see scripts and `processed/` outputs such as `processed/sophisticated_xgb_combined.csv`).

3.  **Phase 3: Teacher→pseudo-label→learner training:**
    The repository implements a teacher/learner separation where teacher artifacts and multi-signal scoring outputs can be used to construct pseudo-label datasets consumed by a learner notebook (`notebooks/vae_gnn_pipeline.ipynb`). The learner notebook includes β-VAE/VGAE/GATv2 components (see `MATHEMATICAL_FORMULATION.md`).

4.  **Phase 4: Defense-in-depth inference (implemented as multiple scoring paths):**
    The repository contains multiple implemented scoring paths (notebook stacking, scripted recalibration, and a hybrid multi-signal API). These are enumerated in `MATHEMATICAL_FORMULATION.md`.

### 3.2 Zero-Knowledge Privacy (ZK-NAF)
To solve the privacy-compliance trade-off, we developed **ZK-NAF (Zero-Knowledge Network Analysis Framework)**.
*   **Mechanism:** Using Groth16 proofs implemented in Solidity (`AMTTPzkNAF.sol`), users can generate a cryptographic proof that they are *not* on a sanctions list (e.g., HMT Consolidated List) without revealing their identity or wallet balance.
*   **Impact:** This allows "Private Compliance," enabling institutional players to participate in public blockchains while adhering to GDPR and data privacy laws.

### 3.3 The "Oracle Orchestrator" Microservices Architecture
The system is not a monolith but a distributed network of specialized agents managed by a central Orchestrator (`backend/compliance-service/orchestrator.py`):
*   **Sanctions Service:** Real-time synchronization with UK HM Treasury and OFAC lists.
*   **Policy Engine:** A dynamic rule-set engine that allows compliance officers to update risk thresholds (e.g., "Block all >£5k transfers to Jurisdiction X") without code changes.

## 4. System Architecture

The solution utilizes a modern, scalable stack:

1.  **Frontend Shell (Flutter):** A unified cross-platform secure enclave for mobile and desktop, handling private key management and proof generation.
2.  **Visualization Layer (Next.js):** Embedded views enabling complex "War Room" analytics (ECharts, Memgraph) for compliance officers.
3.  **Off-Chain Compute (Python/FastAPI):** Handling heavy ML inference and graph traversal.
4.  **On-Chain Enforcement (Solicity):** Smart contracts that act as the final gatekeeper, rejecting any transaction lacking a valid "Risk Certificate."

## 5. Case Study: Prevention of "Smurfing" Attacks

A common laundering technique involves breaking large illicit funds into small, seemingly innocent transactions ("smurfing").

*   **Traditional System:** Sees 50 small transactions of £200. None trigger the £10,000 alert. Passed.
*   **AMTTP System (as implemented/configured):**
    1.  **Graph Layer:** The Memgraph integration detects a "Fan-Out/Fan-In" topology typical of smurfing.
    2.  **Temporal Layer:** The `monitoring_rules.py` service detects high-velocity transfers within a 1-hour window.
    3.  **Result (configuration-driven):** Pattern and graph boost weights are configurable. Example boost magnitudes are defined in `ml/Automation/ml_pipeline/config/calibrated_thresholds.json` (e.g., `SMURFING: 0.25`, `2hop_sanctioned: 0.2`).

## 6. Project Maturity & Roadmap

This repository contains a working prototype with committed datasets under `processed/` and recorded system test artifacts (`test_results.json`, `browser_test_results.json`, `ui_test_results.json`). Forward-looking roadmap statements are intentionally omitted from this publication-facing version.

## 7. Conclusion

AMTTP represents a significant leap forward in regulatory technology. By treating **compliance as a computational problem** rather than an administrative one, it provides the robust infrastructure necessary for the UK to maintain its position as a global leader in safe, regulated Fintech innovation.

---
*Note: This whitepaper describes the AMTTP codebase as of February 2026. Publication-facing results are consolidated in `reports/publishing/RESULTS_CONSOLIDATED.md` and evaluation scripts under `scripts/`.*
