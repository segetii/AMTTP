# Etherscan External Validation Metrics (Computed)

Computed at (UTC): 2026-02-06T16:51:40.327634+00:00

## Dataset

- Source: `processed\etherscan_full_validation.csv`
- Rows: 23
- Rows with numeric score: 23

## Continuous-Score Metrics

- positives (FRAUD): 3 / 23 (rate=0.1304)
- ROC-AUC (score): 0.4417
- PR-AUC  (score): 0.4185

## Discrete Predicate Metrics

### our_prediction_is_fraud

- predicate: our_prediction == 'FRAUD'
- precision: 1.0000
- recall: 0.3333
- f1: 0.5000

### risk_level_is_high_or_critical

- predicate: risk_level in {HIGH,CRITICAL}
- precision: 1.0000
- recall: 0.3333
- f1: 0.5000

## Confusion Matrix

For predicate: risk_level in {HIGH,CRITICAL}

- layout: [[tn, fp], [fn, tp]]
- matrix: [[20, 0], [2, 1]]

## Notes

- This is a small, manually-curated external label set derived from the CSV in processed/.
- Treat results as a sanity check, not a statistically powered benchmark.
