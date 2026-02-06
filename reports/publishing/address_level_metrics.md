# Address-Level Evaluation Metrics (Computed)

Computed at (UTC): 2026-02-06T16:53:55.664723+00:00

**IMPORTANT:** The `fraud` label in this dataset exactly matches `risk_level in {CRITICAL,HIGH}`.
This report is therefore a *proxy-label consistency* check and should not be interpreted as independent model generalization performance.

## Dataset

- Source: `processed\eth_addresses_labeled.csv`
- Columns used: fraud, hybrid_score, xgb_normalized, soph_normalized, risk_level

## Continuous-Score Metrics

Scores are monotone-scaled to [0,1] before AUC computation; this does not change AUC values.

### hybrid_score

- n: 625168
- positives: 372
- positive_rate: 0.0006
- ROC-AUC: 1.0000
- PR-AUC: 1.0000

### xgb_normalized

- n: 625168
- positives: 372
- positive_rate: 0.0006
- ROC-AUC: 0.9969
- PR-AUC: 0.0879

### soph_normalized

- n: 625168
- positives: 372
- positive_rate: 0.0006
- ROC-AUC: 1.0000
- PR-AUC: 0.9767

## Discrete Predicate Metrics

### risk_level_is_critical_or_high

- predicate: risk_level in {CRITICAL,HIGH}
- precision: 1.0000
- recall: 1.0000
- f1: 1.0000

### risk_level_is_medium_or_higher

- predicate: risk_level in {CRITICAL,HIGH,MEDIUM}
- precision: 0.2002
- recall: 1.0000
- f1: 0.3336

