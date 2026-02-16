# ML Pipeline Tests

Scripts that evaluate and validate the machine learning pipeline.
Each script maps to a specific section and table in the paper.

| Script | Paper Reference | What It Tests |
|---|---|---|
| `evaluate_teacher_vs_student.py` | §VI-C | Knowledge distillation: Brier score, JSD, calibration |
| `cross_validate_v2_model.py` | §VI-B, Table VI | 5-fold stratified CV on 625,168 addresses (372 fraud) |
| `cross_domain_validation.py` | §VI-G, Tables VIII–IX | Elliptic, XBlock, Forta, OOD datasets |
| `compute_address_level_metrics.py` | §VI-A, Table V | Per-component ROC-AUC and PR-AUC |
| `compute_etherscan_validation_metrics.py` | §VI-G | 23-address Etherscan sanity check |
| `orthogonality_proof.py` | BSDT Paper §7 | Pairwise correlation, MI, VIF analysis |
| `comprehensive_bsdt_test.py` | BSDT Paper §6.10 | 36-combination (6 models × 6 datasets) evaluation |
| `mfls_variants_test.py` | BSDT Paper §6.11 | 13 alternative MFLS combination strategies |
| `false_alarm_analysis_v3.py` | BSDT Paper §6.9 | Direction reversal, signed LR correction |

## Pre-computed Results

Results are stored in:
- `data/external_validation/cross_validation_v2_results.json`
- `data/external_validation/cross_validation_results.json`
- `ml/evaluation_results/teacher_vs_student_results.json`
- `papers/bsdt_evidence.json`
- `reports/publishing/etherscan_validation_metrics.json`
