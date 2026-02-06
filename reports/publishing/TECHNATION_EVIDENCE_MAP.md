# AMTTP: Tech Nation Evidence Map (Repository-Backed)

This is a claim→evidence map intended to help you assemble a Tech Nation application pack without over-claiming beyond what is implemented and recorded in this repository.

## A) Product + Engineering Execution

### A1. Multi-surface user experience implemented

- Evidence: `frontend/` (Next.js admin UI) and `frontend/amttp_app/` (Flutter consumer app)
- Recorded tests:
  - `test_results.json` (route and service smoke checks)
  - `browser_test_results.json` (browser interaction + screenshots)
  - `ui_test_results.json` (DOM/structure heuristics; includes failures to disclose honestly)

### A2. Backend orchestration exists as code

- Evidence:
  - `backend/compliance-service/orchestrator.py` (service orchestration + processing / timing fields)
  - Docker compose files (`docker-compose*.yml`) and start scripts (`START_*.ps1`) demonstrate operational wiring.

## B) Technical Innovation (As Implemented)

### B1. Hybrid risk scoring and labeling pipeline

- Evidence:
  - Risk scoring scripts in `scripts/` (e.g., `scripts/sophisticated_fraud_detection_ultra.py` and related dataset builders)
  - Implemented fusion and calibration documentation: `MATHEMATICAL_FORMULATION.md`
  - Produced intermediate datasets and artifacts under `processed/` (e.g., `processed/sophisticated_xgb_combined.csv`, `processed/eth_addresses_labeled.parquet`, `processed/eth_transactions_full_labeled.parquet`)

### B2. ZK verification components exist in artifacts

- Evidence:
  - Solidity verifier artifacts under `forge-out/` (e.g., Groth16 verifier JSONs)
  - ZK math specification: `MATHEMATICAL_FORMULATION.md` section on Groth16

## C) Measured / Recorded Results (Only What Is File-Backed)

### C1. System test evidence

- Evidence: `reports/publishing/RESULTS_CONSOLIDATED.md` (aggregates JSON test artifacts)

### C2. ML evaluation evidence

- Evidence:
  - `reports/publishing/address_level_metrics.md` (explicitly marked as proxy-label consistency)
  - `reports/publishing/etherscan_validation_metrics.md` (small external sanity set)

## D) Research / Publication Pack Assets

- Journal-style manuscript draft (implementation-backed): `AMTTP_ACADEMIC_ARTICLE.md` (to be updated to remove unverified claims) or a new manuscript under `reports/publishing/`.
- Full math appendix (implementation-backed): `MATHEMATICAL_FORMULATION.md`
- Architecture context:
  - `AMTTP_PRODUCT_ARCHITECTURE.md`
  - `ARCHITECTURE_DIAGRAM.md`

## E) What Not To Claim Without Extra Evidence

These appear in some docs in the repo but are not currently supported by a directly reproducible metrics artifact:

- Large-sample ROC-AUC / PR-AUC / F1 on “mainnet transaction data” unless you also provide the exact evaluation script, dataset snapshot, and a recorded run artifact.
- Performance/latency claims (e.g., <50ms P99) unless you include a benchmark log artifact.
- Legal compliance statements framed as guarantees (e.g., “mathematically prove adherence to FCA regulations”).
