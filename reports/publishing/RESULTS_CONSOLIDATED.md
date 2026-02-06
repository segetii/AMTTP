# AMTTP: Publication-Facing Results (Repository-Backed)

This document consolidates results that are directly computable from, or recorded in, files present in this repository.

## 1) System / UI Test Runs (Recorded JSON Artifacts)

### 1.1 End-to-End Route Availability Tests

- Source: `test_results.json`
- Timestamp: `2026-01-23T01:00:20.274731`
- Summary: `53/53` passed (`100%`)
- Scope: Next.js routes + Flutter web routes + basic API health + risk engine endpoint shape.

### 1.2 Browser-Based UI Interaction Test

- Source: `browser_test_results.json`
- Timestamp: `2026-01-29T16:43:28.062974`
- Summary: `32/32` passed
- Scope: Next.js login flow (including demo mode), dashboard navigation, screenshots; Flutter routing smoke checks.

### 1.3 UI Structure / DOM Heuristic Tests

- Source: `ui_test_results.json`
- Timestamp: `2026-01-29T16:43:48.423862`
- Summary: `20` passed / `8` failed
- Notes: Several failures relate to missing DOM form fields in the Flutter web build (e.g. no `<form>`, missing `main.dart.js` markers). This is a UI packaging/markup signal, not an ML metric.

## 2) ML / Risk Scoring Evaluation (Computed from `processed/`)

### 2.1 Address-Level Proxy-Label Consistency Check

- Source report: `reports/publishing/address_level_metrics.md`
- Computation script: `scripts/compute_address_level_metrics.py`
- Underlying dataset: `processed/eth_addresses_labeled.csv`

Important: the `fraud` label in `processed/eth_addresses_labeled.csv` is a proxy label that matches `risk_level in {CRITICAL,HIGH}`. Metrics in that report therefore measure internal consistency of the labeling/scoring pipeline, not independent generalization performance.

### 2.2 External Sanity Check on Etherscan-Labeled Addresses (Small-N)

- Source report: `reports/publishing/etherscan_validation_metrics.md`
- Computation script: `scripts/compute_etherscan_validation_metrics.py`
- Underlying dataset: `processed/etherscan_full_validation.csv`
- Dataset size: `N=23` addresses (positives FRAUD: `3`)

This is a small curated set and should be treated as a sanity check rather than a statistically powered benchmark.

## 3) Reproducibility

- Address-level metrics can be regenerated with:
  - `C:/Users/Administrator/AppData/Local/Programs/Python/Python313/python.exe scripts/compute_address_level_metrics.py`
  - `C:/Users/Administrator/AppData/Local/Programs/Python/Python313/python.exe scripts/compute_etherscan_validation_metrics.py`
