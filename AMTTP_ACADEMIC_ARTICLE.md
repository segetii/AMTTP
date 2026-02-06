# Private Compliance Controls for Public Blockchains: An Implementation Report of AMTTP

**Author:** [Your Name]  
**Affiliation:** [Your Affiliation]  
**Date:** February 6, 2026  

## Abstract

This paper reports the implemented AMTTP prototype, a repository-backed system for (i) privacy-preserving verification using Groth16 verifier artifacts and (ii) multi-signal risk scoring for Ethereum addresses/transactions using a combination of learned models and deterministic feature pipelines. The codebase contains notebook-driven training workflows (β-VAE/VGAE/GATv2 and gradient boosting components), multiple implemented inference paths (notebook stacking, scripted recalibration, and a hybrid multi-signal API), and committed processed datasets under `processed/` that are consumed by the pipelines. We provide an implementation-traceable mathematical appendix and a publication-facing results bundle derived from recorded system test artifacts and a small external sanity dataset included in-repo.

**Important scope constraint:** This manuscript only claims results that are directly reproducible from, or recorded in, repository artifacts. It does not claim large-scale benchmark performance unless a dataset snapshot + evaluation script + recorded run artifact are present.

## 1. Introduction

Public blockchains enable auditability but complicate privacy-preserving compliance checks. AMTTP is a prototype that explores a “pre-execution” control posture: compute risk signals before allowing an operation to proceed, while supporting privacy-preserving proof verification for certain checks.

## 2. Implemented System Components

### 2.1 Risk scoring: implemented fusion paths

The repository implements multiple scoring paths (documented in `MATHEMATICAL_FORMULATION.md`):

- Notebook stacking path (`notebooks/vae_gnn_pipeline.ipynb`)
- Scripted percentile / calibration path (`scripts/recalibrated_inference.py`, `scripts/sophisticated_fraud_detection_ultra.py`)
- Hybrid multi-signal API fusion (`ml/Automation/ml_pipeline/inference/hybrid_api.py`)

### 2.2 Data pipeline artifacts

The repository includes generated datasets under `processed/` (examples):

- `processed/eth_addresses_labeled.csv` / `processed/eth_addresses_labeled.parquet`
- `processed/eth_transactions_full_labeled.parquet`
- `processed/sophisticated_xgb_combined.csv`

These artifacts enable end-to-end traceability from feature extraction and scoring to downstream training inputs.

### 2.3 Zero-knowledge verification artifacts

The repository contains Groth16 verifier artifacts (e.g., under `forge-out/`) and a mathematical description of Groth16 verification constraints in `MATHEMATICAL_FORMULATION.md`.

## 3. Mathematics (Implementation-Backed)

The authoritative, implementation-backed mathematical appendix is `MATHEMATICAL_FORMULATION.md`. It formalizes:

- β-VAE and VGAE objectives as instantiated in the notebooks (including MSE-based reconstruction)
- GATv2 supervised objective, uncertainty estimation (MC Dropout), and optimization details (EMA, OneCycleLR)
- Implemented fusion/calibration equations used in scripts and the hybrid API
- Groth16 verification equation as reflected by Solidity verifier patterns

## 4. Results and Evaluation (Repository-Backed)

### 4.1 System test evidence

Recorded JSON artifacts demonstrate UI routes and basic service wiring:

- `test_results.json`
- `browser_test_results.json`
- `ui_test_results.json`

A consolidated summary is provided in `reports/publishing/RESULTS_CONSOLIDATED.md`.

### 4.2 Proxy-label provenance and implications

The committed address-level dataset `processed/eth_addresses_labeled.csv` contains a `fraud` label that is a proxy label derived from risk-level categorization (i.e., it matches `risk_level in {CRITICAL,HIGH}`). This is confirmed by a computed provenance check:

- `reports/publishing/address_level_metrics.md`

Implication: metrics computed against this proxy label quantify internal consistency of the scoring/labeling pipeline rather than independent model generalization.

### 4.3 External sanity dataset (Etherscan-labeled addresses)

The repository includes a small curated dataset `processed/etherscan_full_validation.csv` with labels `type ∈ {FRAUD, LEGITIMATE}`. We compute a sanity-check evaluation from this file:

- `reports/publishing/etherscan_validation_metrics.md`

At the time of computation (UTC timestamp embedded in the report), the dataset has N=23 with 3 labeled FRAUD addresses. Discrete predicates (`risk_level in {HIGH,CRITICAL}` and `our_prediction == 'FRAUD'`) both yield precision 1.0 and recall 0.3333 on this set (confusion matrix also recorded in the report). Continuous-score ROC-AUC/PR-AUC values are also recorded.

Limitations: the dataset is small and should not be treated as a statistically powered benchmark.

## 5. Limitations and Threats to Validity

- Proxy labels: a large portion of the training/evaluation flow uses proxy labeling derived from heuristics and multi-signal scoring; this can inflate apparent performance if treated as ground truth.
- External validation: the in-repo external validation set is small.
- Reproducibility of “mainnet” claims: claims about performance on large-scale mainnet transaction distributions require a pinned dataset snapshot and a recorded evaluation run.

## 6. Reproducibility

Recompute the publication-facing metrics:

- `python scripts/compute_address_level_metrics.py`
- `python scripts/compute_etherscan_validation_metrics.py`

## References

(Provide final bibliography appropriate for the target journal; this manuscript does not include non-repo benchmark claims.)
