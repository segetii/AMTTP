# External Validation Tests

These scripts reproduce the cross-domain evaluation described in **§VI-G** of the paper.
They apply the trained AMTTP model to independent external datasets to demonstrate generalisability.

| Script | Paper Reference | Dataset |
|---|---|---|
| `cross_domain_validation.py` | §VI-G, Tables VIII–IX | Elliptic, XBlock-Ethereum, Forta, OOD |
| `cross_validate_v2_model.py` | §VI-B, Table VI | Internal 5-fold CV (625,168 addresses) |
| `comprehensive_bsdt_test.py` | BSDT §6.10 | 36-combination grid (6 models × 6 datasets) |
| `compute_etherscan_validation_metrics.py` | §VI-G | 23 real Etherscan-labelled addresses |

## Pre-computed Results

External validation data and results live in:
- `data/external_validation/` — raw external datasets
- `data/external_validation/cross_validation_v2_results.json`
- `reports/publishing/etherscan_validation_metrics.json`
- `papers/bsdt_evidence.json`
