# AMTTP Test Suite

This directory consolidates all test scripts into a reviewer-friendly structure.
Each subdirectory targets a distinct layer of the AMTTP architecture.

## Directory Map

```
tests/
├── smart-contracts/        ← Layer IV: On-chain enforcement
│   ├── hardhat/            ← 8 Hardhat test suites (Mocha/Chai, Ethers.js)
│   │   ├── AMTTP1.test.mjs                 Core oracle, escrow, threshold sigs
│   │   ├── AMTTPDisputeResolver.test.mjs   Kleros arbitration integration
│   │   ├── AMTTPModular.test.cjs           Modular contract architecture
│   │   ├── AMTTPModular.test.mjs           ESM variant of above
│   │   ├── AMTTPPolicyEngine.test.mjs      Rule & threshold configuration
│   │   ├── AMTTPRiskRouter.test.cjs        Multi-chain score routing
│   │   ├── GasAnalysis.test.mjs            Gas benchmarks (Table X in paper)
│   │   └── ZkNAFVerifierRouter.test.mjs    Zero-knowledge proof verification
│   └── foundry/            ← 3 Foundry fuzz test suites (Solidity)
│       ├── AMTTPCore.fuzz.t.sol            Property-based fuzz: core invariants
│       ├── AMTTPPolicyEngine.fuzz.t.sol    Fuzz: policy engine edge cases
│       └── AMTTPzkNAF.t.sol                Fuzz: zkNAF circuit boundary tests
│
├── ml-pipeline/            ← Layer III: Offline training & evaluation
│   ├── evaluate_teacher_vs_student.py      Teacher→student distillation metrics
│   ├── cross_validate_v2_model.py          5-fold CV on 625K addresses (Table VI)
│   ├── cross_domain_validation.py          Cross-chain evaluation (§VI-G)
│   ├── orthogonality_proof.py              BSDT component independence proof (§7)
│   ├── comprehensive_bsdt_test.py          36-combination BSDT evaluation
│   ├── mfls_variants_test.py               13 MFLS combination strategies
│   ├── false_alarm_analysis_v3.py          Direction reversal & false alarm analysis
│   ├── compute_address_level_metrics.py    Address-level precision/recall
│   └── compute_etherscan_validation_metrics.py  Production validation (n=23)
│
├── api-integration/        ← Layer II: Compliance logic & orchestration
│   ├── test-complete-system.cjs            Full 17-service end-to-end test
│   ├── test-unified-system.cjs             Unified Docker Compose stack test
│   ├── test-security-controls.cjs          Auth, RBAC, rate limiting
│   ├── test-testnet.cjs                    Sepolia testnet deployment verification
│   ├── test_hybrid_api.py                  ML + rule hybrid scoring endpoint
│   ├── test_integrity_service.py           UI integrity tamper detection
│   ├── test_ml_alone.py                    Isolated ML risk engine tests
│   ├── test_optimized_settings.py          Threshold tuning validation
│   ├── test_recalibrated_settings.py       Score recalibration verification
│   └── automated_testing.py                53-route automated API test suite
│
├── ui/                     ← Layer I: Interface testing
│   ├── browser_ui_test.py                  32 browser interaction tests
│   └── ui_functional_test.py               Flutter + Next.js rendering tests
│
├── external-validation/    ← Cross-domain generalization (§VI-G)
│   ├── validate_etherscan_comprehensive.py Full Etherscan sanity check
│   ├── validate_with_etherscan.py          Production endpoint validation
│   ├── cross_validate_fraud.py             External dataset CV framework
│   └── evaluate_forta_addresses.py         Forta threat intelligence test
│
└── security/               ← Audit & security testing
    ├── run-audit.ps1                       Slither + Echidna audit runner
    └── run-zknaf-tests.ps1                 zkNAF circuit test runner
```

## Running Tests

### Smart Contract Tests (Hardhat)
```bash
npx hardhat test test/AMTTP1.test.mjs          # Core contract suite
npx hardhat test test/GasAnalysis.test.mjs      # Gas benchmarks
```

### Smart Contract Fuzz Tests (Foundry)
```bash
forge test --match-path test/foundry/*.sol      # All fuzz tests
```

### ML Pipeline Evaluation
```bash
python tests/ml-pipeline/cross_validate_v2_model.py    # 5-fold CV
python tests/ml-pipeline/orthogonality_proof.py         # BSDT proof
```

### API Integration Tests
```bash
node tests/api-integration/test-complete-system.cjs     # Full stack
python tests/api-integration/automated_testing.py       # 53-route suite
```

### UI Tests
```bash
python tests/ui/browser_ui_test.py                      # Browser tests
```

## Test Results

Pre-computed results referenced in the paper:
- `data/external_validation/cross_validation_v2_results.json` — Table VI
- `data/external_validation/cross_validation_results.json` — Table VIII
- `reports/publishing/etherscan_validation_metrics.json` — Etherscan sanity check
- `ml/evaluation_results/teacher_vs_student_results.json` — §VI-C
- `papers/bsdt_evidence.json` — BSDT 36-combination results

## Mapping Tests to Paper Sections

| Paper Section | Test Script(s) | Result File |
|---|---|---|
| §VI-A Component Performance | `ml-pipeline/evaluate_teacher_vs_student.py` | `ml/evaluation_results/` |
| §VI-B Five-Fold CV | `ml-pipeline/cross_validate_v2_model.py` | `data/external_validation/cross_validation_v2_results.json` |
| §VI-G External Validation | `ml-pipeline/cross_domain_validation.py`, `external-validation/` | `data/external_validation/` |
| §VI-I Gas Benchmarks | `smart-contracts/hardhat/GasAnalysis.test.mjs` | Table X in paper |
| §VI-J Integration Testing | `api-integration/automated_testing.py` | 53 routes, 32 UI tests |
| BSDT Theory (Paper 2) | `ml-pipeline/comprehensive_bsdt_test.py` | `papers/bsdt_evidence.json` |
