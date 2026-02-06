# AMTTP (Implementation Report): Private Compliance Controls for Public-Chain Transfers

**Date:** February 6, 2026

## Abstract

This manuscript reports an implementation of AMTTP, a repository-backed prototype that combines (a) zero-knowledge proof verification artifacts (Groth16 verifier contracts/artifacts) with (b) a multi-signal risk scoring pipeline for Ethereum-address and transaction risk. The machine-learning components include notebook-based training workflows (β-VAE, VGAE, GATv2, and gradient-boosted tabular models) and multiple implemented scoring paths (stacking in notebooks; scripted recalibration; and a hybrid multi-signal inference API). The data engineering path constructs proxy labels using multi-signal heuristics and produces labeled datasets under `processed/` that are consumed by training notebooks. We provide an implementation-traceable mathematical specification and a reproducible evaluation summary based on artifacts committed in the repository, including system test outputs and a small external sanity check dataset.

## 1. Introduction

Public blockchains provide transparency but create compliance and privacy tensions. This work documents an implemented pipeline intended to support pre-execution risk assessment and privacy-preserving checks. This manuscript is strictly limited to what is implemented and recorded in the repository.

## Research Areas (Itemised)

This work (as implemented in the repository) sits across the following research/engineering areas:

1. **Graph-based financial crime analytics**: graph-derived exposure/proximity signals and GNN-based modeling (GraphSAGE/GATv2 paths exist in notebooks and architecture docs).
2. **Representation learning for anomaly/risk scoring**: β-VAE/VGAE components used to learn latent features that support downstream classification and scoring.
3. **Imbalanced classification and uncertainty estimation**: focal loss / calibration patterns in the ML stack; MC Dropout-based uncertainty estimation in the implemented training workflow.
4. **Ensemble learning and model fusion**: gradient-boosted models (XGBoost/LightGBM) with stacking/meta-learning; additional fusion with graph/rule signals in the hybrid inference API.
5. **Rule-based typology detection**: deterministic AML-pattern/rule checks used as explicit features and as gating/boosting signals in scoring.
6. **Privacy-preserving compliance via zero-knowledge proofs**: Groth16 verifier artifacts and Solidity verification logic, designed to enable proving compliance predicates without disclosing underlying attributes.
7. **Applied MLOps and reproducible evaluation**: repository-backed scripts that compute metrics from committed datasets and write timestamped reports under `reports/publishing/`.

## 2. System Overview (As Implemented)

### 2.1 Multi-signal risk scoring

Implemented scoring paths are documented in `MATHEMATICAL_FORMULATION.md` and correspond to:

- Notebook stacking (`notebooks/vae_gnn_pipeline.ipynb`)
- Scripted score recalibration (`scripts/recalibrated_inference.py`)
- Hybrid inference API fusion (`ml/Automation/ml_pipeline/inference/hybrid_api.py`)

### 2.2 Data products committed in-repo

The repository includes generated datasets under `processed/`, including:

- `processed/eth_addresses_labeled.parquet` / `processed/eth_addresses_labeled.csv`
- `processed/eth_transactions_full_labeled.parquet`
- `processed/sophisticated_xgb_combined.csv`

## 3. Implemented Mathematics

The full implementation-backed mathematical appendix is `MATHEMATICAL_FORMULATION.md`. It includes:

- β-VAE (MSE reconstruction + KL; β set in notebook)
- VGAE objective (recon + weighted KL)
- GATv2 supervised loss (focal loss + smoothing) plus EMA and OneCycleLR details
- Implemented fusion/calibration equations for scripts and APIs
- Groth16 verification equation for Solidity verifier artifacts

## 4. Experimental Setup and Evaluation (Repository-Backed)

### 4.1 Proxy-label datasets (training signal provenance)

The committed labeled address dataset uses a proxy label derived from risk-level categorization. The repository provides a computed check showing that `fraud` equals `risk_level in {CRITICAL,HIGH}` for `processed/eth_addresses_labeled.csv`.

- Evidence: `reports/publishing/address_level_metrics.md`

This is a labeling/provenance fact and implies that metrics computed against this label are not independent measures of generalization.

### 4.2 External sanity check dataset

A small curated dataset with `type ∈ {FRAUD, LEGITIMATE}` is committed as `processed/etherscan_full_validation.csv`. We compute score-based and discrete-predicate metrics on this dataset.

- Evidence: `reports/publishing/etherscan_validation_metrics.md`

Limitations: the dataset is small (N=23) and should be treated as a sanity check.

### 4.3 System test artifacts

System/UI test outputs are recorded in JSON artifacts and summarized in:

- `reports/publishing/RESULTS_CONSOLIDATED.md`

## 5. Limitations

- Large-scale ML performance claims (e.g., ROC-AUC on “mainnet data”) require a fully specified evaluation protocol + dataset snapshot + recorded run artifact. Where such artifacts are not present, this manuscript does not claim them.
- The external Etherscan sanity dataset is small and not suitable for strong statistical conclusions.

## 6. Reproducibility

- Recompute publication-facing results:
  - `python scripts/compute_address_level_metrics.py`
  - `python scripts/compute_etherscan_validation_metrics.py`

## References

References should be finalized to match the exact models used (VAE, GATv2, Groth16) and the compliance context. This draft does not include non-repo claims.
