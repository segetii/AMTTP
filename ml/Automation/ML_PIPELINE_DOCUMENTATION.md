# AMTTP ML Pipeline — Complete Documentation

> **Version**: 3.0 — TX-Level Model Production (Path B)  
> **Last Updated**: 2025-07-24  
> **Models Directory**: `ml/Automation/tx_level_models/`  
> **Previous Models**: `ml/Automation/amttp_models_20251231_174617/` (deprecated, address-level)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Teacher Pipeline](#2-teacher-pipeline)
3. [Student Pipeline (v2, deprecated)](#3-student-pipeline-v2-deprecated)
4. [TX-Level Pipeline (v3, production)](#4-tx-level-pipeline-v3-production)
5. [Model Artifacts](#5-model-artifacts)
6. [cuML Meta-Learner Weight Extraction (historical)](#6-cuml-meta-learner-weight-extraction)
7. [Evaluation — Comparison Results](#7-evaluation--comparison-results)
8. [Production Integration](#8-production-integration)
9. [Running the Pipeline End-to-End](#9-running-the-pipeline-end-to-end)
10. [Known Issues & Workarounds](#10-known-issues--workarounds)
11. [Feature Reference](#11-feature-reference)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    TEACHER PIPELINE (v1)                        │
│                                                                 │
│  Kaggle ETH Fraud → XGBoost v1 → Sigmoid Recalibration         │
│       ↓                                                         │
│  hybrid_score = 0.4·xgb_norm + 0.3·pattern + 0.3·soph_norm     │
│       ↓                                                         │
│  fraud = 1 if risk_level ∈ {CRITICAL, HIGH}  (threshold ~48.58) │
│       ↓                                                         │
│  eth_addresses_labeled.parquet  (1.67M rows, 25.1% fraud)       │
└──────────────────────────────┬──────────────────────────────────┘
                               │ Labels
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STUDENT PIPELINE (v2)                        │
│                                                                 │
│  5 tabular features → BetaVAE (64-dim latent) → recon_err      │
│       ↓                        ↓                                │
│  GraphSAGE (128h, 3L)    GATv2 (64h, 4-head)                   │
│       ↓                        ↓                                │
│  XGBoost v2 (1999 est)   LightGBM (2000 est)                   │
│       ↓                        ↓                                │
│  [71 features each: 5 tabular + 64 VAE + recon_err + sage]      │
│       ↓                        ↓                                │
│  ┌──────────────────────────────────┐                           │
│  │   LogisticRegression Meta-Learner │                          │
│  │   7 inputs: [recon, edge, gat,    │                          │
│  │    uncertainty, sage, xgb, lgb]   │                          │
│  │   Optimal threshold: 0.727        │                          │
│  └──────────────────────────────────┘                           │
│                    ↓                                             │
│            fraud_probability [0, 1]                              │
└─────────────────────────────────────────────────────────────────┘
```

### Critical Note: Label Circularity

The fraud labels in `eth_addresses_labeled.parquet` are **derived from** the Teacher
pipeline's `hybrid_score`. This means:

- Teacher Full Stack metrics (F1=1.0) are **circular** — the labels are its own output.
- Student models are learning to **replicate** the Teacher's scoring, not ground truth fraud.
- This is by design (knowledge distillation) but must be understood when interpreting metrics.

---

## 2. Teacher Pipeline

### Source Script
`scripts/sophisticated_fraud_detection_ultra.py`

### Steps

1. **Raw Data**: Kaggle Ethereum fraud dataset with transaction-level features
2. **XGBoost v1**: Trained on original fraud labels
3. **Sigmoid Recalibration**:
   ```python
   p75 = np.percentile(xgb_raw_scores, 75)
   k = 30
   xgb_calibrated = 1 / (1 + np.exp(-k * (xgb_raw - p75)))
   xgb_normalized = xgb_calibrated * 100
   ```
4. **Pattern Boost**: Rule-based signals (high-value, contract complexity, etc.)
5. **Sophistication Score**: Behavioral analysis normalized to 0–100
6. **Hybrid Score Computation**:
   ```python
   hybrid_score = 0.4 * xgb_normalized + 0.3 * pattern_boost + 0.3 * soph_normalized
   ```
7. **Risk Level Assignment** (PR-curve optimized thresholds):
   - CRITICAL: ≥ `threshold_critical`
   - HIGH: ≥ `threshold_high`
   - MEDIUM: ≥ `threshold_medium`
   - LOW: ≥ `threshold_low`
   - MINIMAL: below all thresholds
8. **Label Derivation** (`scripts/create_complete_labeled_dataset.py`):
   ```python
   fraud = risk_level.isin(['CRITICAL', 'HIGH']).astype(int)
   # Threshold: hybrid_score ≥ 48.58 → fraud = 1
   ```

### Output
`eth_addresses_labeled.parquet` — 1,673,244 rows, 25.15% fraud rate

---

## 3. Student Pipeline

### Training Environment
- **Platform**: Google Colab (NVIDIA GPU + cuML/RAPIDS)
- **Training Date**: 2025-12-31T17:46:17
- **Dataset**: 1,673,244 samples, 5 features, 25.15% fraud

### Pipeline Stages

#### Stage 1: Preprocessing (`preprocessors.joblib`)
```python
# 1. Handle NaN/inf
X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

# 2. Log-transform skewed features (skewness > 1.0)
X[:, log_mask] = np.log1p(np.clip(X[:, log_mask], 0, None))

# 3. RobustScaler (outlier-resistant)
X = robust_scaler.transform(X)

# 4. Clip to ±5
X = np.clip(X, -5, 5)
```

#### Stage 2: Unsupervised Feature Extraction
- **BetaVAE**: 5 → 64 latent dimensions (β=4.0) + `recon_err`
- **VGAE**: Variational Graph Auto-Encoder (32 output channels)
- **GATv2**: Graph Attention Network (64 hidden, 4 heads) → `edge_score`, `gat_score`, `uncertainty`
- **GraphSAGE**: Large model (128 hidden, 3 layers) → `sage_score`

#### Stage 3: Boosted Classifiers (71 features each)
- **XGBoost v2**: 1,999 estimators, ROC-AUC = 0.9170
- **LightGBM**: 2,000 estimators, ROC-AUC = 0.9226

Feature vector: `[5 tabular] + [64 VAE latent] + [recon_err] + [graphsage_score]`

#### Stage 4: Meta-Learner
- **Type**: cuML LogisticRegression (C=1.0)
- **Inputs**: 7 features — `[recon_err, edge_score, gat_score, uncertainty, sage_score, xgb_prob, lgb_prob]`
- **Output**: fraud probability [0, 1]
- **Optimal Threshold**: 0.727
- **Meta ROC-AUC**: 0.9229

### Simplified Mode (No Graph Infrastructure)

In production without graph embeddings, the meta-learner receives:
- `recon_err = 0`, `edge_score = 0`, `gat_score = 0`, `uncertainty = 0`, `sage_score = 0`
- `xgb_prob` and `lgb_prob` are the only active inputs

The meta-learner effectively becomes a weighted combination of XGB and LGB:
```
logit = -1.686 * xgb_prob + 8.982 * lgb_prob + intercept_adjustment
```

---

## 4. TX-Level Pipeline (v3, production)

### Why TX-Level?

The Student v2 pipeline (Section 3) had a critical **training/serving skew** problem:
- **Training**: Models were trained on 71 features (5 address aggregates + 64 VAE latents + recon_err + graphsage_score)
- **Serving**: Only 5 address features were available; the other 66 features were hardcoded to zero
- **Result**: 93% of model inputs were zeros in production

### Solution: Path B — train on features available at inference time

```
TransactionRequest (API Input)
    ├── value_eth, gas_price_gwei, gas_used, gas_limit, nonce, transaction_type  (6 raw)
    ├── gas_efficiency, value_log, gas_price_log, is_round_amount,              (7 derived)
    │   value_gas_ratio, is_zero_value, is_high_nonce
    └── sender_total_transactions, sender_total_sent, ...                        (8 sender lookup)
         ↓ (21 features total)
    ┌──────────┐     ┌───────────┐
    │ XGBoost  │     │ LightGBM  │     (each trained on 21 features)
    │ (500 est)│     │ (500 est) │
    └────┬─────┘     └─────┬─────┘
         │                 │
         └──── xgb_prob, lgb_prob ────┐
                                      ▼
                            ┌──────────────────┐
                            │ Meta-Learner     │
                            │ sklearn LogReg   │
                            │ coef=[7.74, 2.22]│
                            │ intercept=-6.25  │
                            └────────┬─────────┘
                                     ▼
                              fraud_probability
```

### Training Script

`ml/Automation/train_tx_level_models.py`

```bash
cd ml/Automation
python train_tx_level_models.py
```

### Training Data

`processed/eth_transactions_full_labeled.parquet`
- **1,673,244** transactions, **69** columns
- **25.15%** fraud rate (420,848 fraud / 1,252,396 normal)
- Created by `scripts/create_gat_transaction_dataset.py` (joins sender/receiver features to raw transactions)

### Features (21 total)

| # | Feature | Source | Description |
|---|---------|--------|-------------|
| 0 | `value_eth` | TransactionRequest | Transaction value in ETH |
| 1 | `gas_price_gwei` | TransactionRequest | Gas price in Gwei |
| 2 | `gas_used` | TransactionRequest | Gas consumed |
| 3 | `gas_limit` | TransactionRequest | Gas limit |
| 4 | `nonce` | TransactionRequest | Sender nonce |
| 5 | `transaction_type` | TransactionRequest | EIP-2718 type (0=legacy, 2=1559) |
| 6 | `gas_efficiency` | Derived | gas_used / gas_limit |
| 7 | `value_log` | Derived | log1p(value_eth) |
| 8 | `gas_price_log` | Derived | log1p(gas_price_gwei) |
| 9 | `is_round_amount` | Derived | (value * 100) % 1 < 0.01 |
| 10 | `value_gas_ratio` | Derived | value_eth / gas_price_gwei |
| 11 | `is_zero_value` | Derived | value_eth == 0 |
| 12 | `is_high_nonce` | Derived | nonce > 1000 |
| 13 | `sender_total_transactions` | Address lookup | Total tx count for sender |
| 14 | `sender_total_sent` | Address lookup | Total ETH sent by sender |
| 15 | `sender_total_received` | Address lookup | Total ETH received by sender |
| 16 | `sender_balance` | Address lookup | Current sender balance |
| 17 | `sender_avg_sent` | Address lookup | Average tx value for sender |
| 18 | `sender_unique_receivers` | Address lookup | Unique receivers count |
| 19 | `sender_in_out_ratio` | Address lookup | In/out transaction ratio |
| 20 | `sender_active_duration_mins` | Address lookup | Active duration in minutes |

### Training/Serving Alignment: **ZERO SKEW**

Every feature used during training is available at inference time:
- 6 features come directly from the API `TransactionRequest`
- 7 features are derived from those via simple arithmetic
- 8 sender features come from an address index/cache lookup (optional, gracefully defaults to 0)

---

## 5. Model Artifacts

### Active: `ml/Automation/tx_level_models/` (v3, production)

| File | Size | Description |
|------|------|-------------|
| `xgboost_tx.ubj` | 5.4 MB | TX-Level XGBoost (500 est, 21 features) |
| `lightgbm_tx.txt` | 6.8 MB | TX-Level LightGBM (500 est, 21 features) |
| `meta_learner.joblib` | 0.8 KB | sklearn LogisticRegression (no cuML/CUDA needed) |
| `metadata.json` | 3 KB | Training metadata + comparison results |
| `feature_config.json` | 1.1 KB | Feature names and groupings |
| `comparison_results.json` | — | Full 6-way comparison results |

### Deprecated: `ml/Automation/amttp_models_20251231_174617/` (v2, address-level)

| File | Size | Description |
|------|------|-------------|
| `xgboost_fraud.ubj` | 8.1 MB | Student XGBoost v2, 1999 estimators, expects 71 features |
| `lightgbm_fraud.txt` | 12.9 MB | Student LightGBM, 2000 estimators, expects 71 features |
| `meta_ensemble.joblib` | 2.2 KB | cuML LogisticRegression — **requires CUDA/RAPIDS** |
| `preprocessors.joblib` | 1.2 KB | RobustScaler + log_transform_mask |
| `beta_vae.pt` | — | BetaVAE PyTorch model (latent_dim=64, β=4.0) |
| `gatv2.pt` | — | GATv2 graph attention model |
| `graphsage_large.pt` | — | GraphSAGE 3-layer model |
| `vgae.pt` | — | Variational Graph Auto-Encoder |
| `scaler_edge.joblib` | — | Edge feature scaler |
| `scaler_recon.joblib` | — | Reconstruction error scaler |
| `metadata.json` | — | Training config, thresholds, performance metrics |
| `feature_config.json` | — | Feature names for tabular (5) and boost (71) |
| `inference.py` | — | Reference inference script (requires cuML) |

### Pre-Existing Production Models: `ml/Automation/ml_pipeline/models/trained/`

| File | Description |
|------|-------------|
| `stacking_lgbm.txt` | Stacking LightGBM ensemble |
| `lgbm.txt` | Standalone LightGBM (ROC-AUC 0.9226) |
| `hybrid_xgb.json` | Teacher XGBoost (original) |
| `catboost.cbm` | CatBoost classifier |
| `stacking_calibrator.joblib` | Isotonic calibrator for stacking model |
| `xgb.json` | Alternative XGBoost |
| `rnn.pt`, `tabt.pt`, `wide_deep.pt` | Deep learning models (not currently used) |

---

## 5. cuML Meta-Learner Weight Extraction

### The Problem

`meta_ensemble.joblib` was trained with **cuML** (NVIDIA RAPIDS). It cannot be loaded
on CPU-only systems because the pickle contains `cuml.linear_model.logistic_regression`
class references.

### The Solution — Binary Weight Extraction

We extracted the raw LogisticRegression weights directly from the serialized bytes
using `pickletools.dis()` to locate the coefficient array and `struct.unpack()` to read
IEEE 754 double-precision floats.

**Script**: `ml/Automation/extract_weights.py`

```python
import struct
data = open('amttp_models_20251231_174617/meta_ensemble.joblib', 'rb').read()

# Coefficients at byte offset 1344, 7 doubles (56 bytes)
offset = 1344
coef = struct.unpack('<7d', data[offset:offset+56])
# coef = (0.7021, 3.3994, 0.4668, -2.5898, 0.8492, -1.6858, 8.9820)

# Intercept at next 8 bytes
intercept = struct.unpack('<d', data[offset+56:offset+64])
# intercept = (-5.5341,)
```

### Extracted Weights

| Index | Feature | Coefficient | Role |
|-------|---------|-------------|------|
| 0 | `recon_err` | 0.7021 | VAE reconstruction error |
| 1 | `edge_score` | 3.3994 | Edge-level graph attention |
| 2 | `gat_score` | 0.4668 | GATv2 node classification |
| 3 | `uncertainty` | -2.5898 | Prediction uncertainty (negative = lower uncertainty → higher fraud) |
| 4 | `sage_score` | 0.8492 | GraphSAGE node embedding |
| 5 | `xgb_prob` | -1.6858 | XGBoost fraud probability |
| 6 | `lgb_prob` | 8.9820 | LightGBM fraud probability (dominant) |
| — | intercept | -5.5341 | Bias term |

### Reconstruction in sklearn

```python
from sklearn.linear_model import LogisticRegression
import numpy as np

meta = LogisticRegression()
meta.classes_ = np.array([0, 1])
meta.coef_ = np.array([[0.7021, 3.3994, 0.4668, -2.5898, 0.8492, -1.6858, 8.9820]])
meta.intercept_ = np.array([-5.5341])
# Now meta.predict_proba() works identically to the cuML version
```

---

## 7. Evaluation — Comparison Results

### Scripts
- TX-Level: `ml/Automation/train_tx_level_models.py` (trains + evaluates in one run)
- Address-Level (deprecated): `ml/Automation/evaluate_teacher_vs_student_v2.py`

### TX-Level Comparison Results (v3, current)

| Model | ROC-AUC | PR-AUC | F1 | Precision | Recall |
|-------|---------|--------|-----|-----------|--------|
| Teacher Stack (⚠ circular) | 0.7301 | 0.6903 | 0.7000 | 1.0000 | 0.5385 |
| Student v2 XGB (addr, padded) | 0.6436 | 0.3618 | 0.4834 | 0.4136 | 0.5814 |
| Student v2 Ensemble (addr, padded) | 0.6322 | 0.3491 | 0.4728 | 0.3959 | 0.5867 |
| **TX-Level XGB** | **0.9878** | **0.9713** | **0.9011** | **0.9210** | **0.8820** |
| **TX-Level LGB** | **0.9876** | **0.9707** | **0.8986** | **0.9253** | **0.8733** |
| **TX-Level Ensemble** | **0.9879** | **0.9715** | **0.9012** | **0.9272** | **0.8765** |

### Key Findings

1. **TX-Level models vastly outperform address-level models on transaction data** —
   ROC-AUC jumps from 0.64 to 0.99, F1 from 0.47 to 0.90.

2. **Address-level models evaluated on transactions fail** — The Student v2 models were
   trained on address aggregates but evaluated on individual transactions, leading to
   poor performance (ROC-AUC 0.63-0.64).

3. **TX-Level Ensemble is the best overall** — ROC-AUC=0.9879, F1=0.9012, with XGB
   coefficient (7.74) dominating the meta-learner.

4. **Zero training/serving skew** — All 21 features used in training are available at
   inference time (6 from API, 7 derived, 8 from address lookup).

5. **Meta-learner only needs 2 inputs** — `[xgb_prob, lgb_prob]`, sklearn LogisticRegression.
   No cuML, no CUDA dependency.

### How to Re-train and Evaluate

```bash
cd c:\amttp\ml\Automation
python train_tx_level_models.py
# Outputs to tx_level_models/: xgboost_tx.ubj, lightgbm_tx.txt, meta_learner.joblib
# Also saves comparison_results.json and metadata.json
```

---

## 8. Production Integration

### Architecture

```
Flutter App / Next.js Frontend
        │
        ▼
Compliance Orchestrator (:8007)
        │
        ├── POST /score         →  Risk Engine (:8000)
        └── POST /score/address →  Risk Engine (:8000)
                │
                ▼
      TX-Level Ensemble (v3)
      (XGB + LGB + sklearn Meta-Learner)
      21 features, zero skew
```

### Production Risk Engine

**Service**: `ml/Automation/risk_engine/integration_service.py`

The risk engine uses the TX-Level model ensemble. See the
`StudentModelEngine` class which:

1. Loads `xgboost_fraud.ubj` and `lightgbm_fraud.txt`
2. Loads `preprocessors.joblib` for feature transformation
3. Reconstructs the meta-learner from extracted sklearn weights (no cuML dependency)
4. Pads 5 tabular features → 71 (zeros for VAE/graph dimensions)
5. Outputs risk_score [0–1000] with the same API contract

### Docker Volume Mount

```yaml
# docker-compose.full.yml
ml-risk-engine:
  volumes:
    - ./ml/Automation/amttp_models_20251231_174617:/app/models
```

### Score Mapping

| Student Probability | Risk Score | Risk Level |
|---------------------|------------|------------|
| < 0.20 | 0–199 | MINIMAL |
| 0.20–0.39 | 200–399 | LOW |
| 0.40–0.59 | 400–599 | MEDIUM |
| 0.60–0.79 | 600–799 | HIGH |
| ≥ 0.80 | 800–1000 | CRITICAL |

---

## 8. Running the Pipeline End-to-End

### Prerequisites

```
Python 3.11+
pip install xgboost lightgbm scikit-learn numpy pandas joblib
```

> **Note**: cuML/RAPIDS is NOT required. The meta-learner weights are reconstructed 
> from extracted binary coefficients using sklearn.

### Step 1: Verify Model Files

```bash
ls ml/Automation/amttp_models_20251231_174617/
# Required: xgboost_fraud.ubj, lightgbm_fraud.txt, preprocessors.joblib,
#           metadata.json, feature_config.json
```

### Step 2: Run Evaluation (Optional)

```bash
cd ml/Automation
python evaluate_teacher_vs_student_v2.py
```

### Step 3: Start Production Service

```bash
cd ml/Automation/risk_engine
python integration_service.py
# Serves on http://localhost:8000
```

### Step 4: Test Scoring

```bash
curl -X POST http://localhost:8000/score -H "Content-Type: application/json" \
  -d '{"from_address":"0xabc...","to_address":"0xdef...","value_eth":1.5,"gas_price_gwei":20,"nonce":42}'
```

### Step 5: Docker Deployment

```bash
docker-compose -f docker-compose.full.yml up ml-risk-engine
```

---

## 9. Known Issues & Workarounds

### Issue 1: cuML Deserialization Failure

**Problem**: `meta_ensemble.joblib` requires CUDA/RAPIDS to deserialize.  
**Workaround**: Weights extracted manually from binary. See Section 5.  
**Permanent Fix**: Re-train meta-learner with sklearn LogisticRegression on next training run.

### Issue 2: Feature Dimension Mismatch

**Problem**: Student XGB/LGB expect 71 features but production only has 5 tabular.  
**Workaround**: Pad zeros for 66 missing features (VAE latent + graph scores).  
**Impact**: Models still perform well because the 5 tabular features carry most signal.
The VAE/graph features would improve performance if graph infrastructure is available.

### Issue 3: Docker Volume Mount (FIXED)

**Problem**: `docker-compose.full.yml` mounted empty `risk_engine/models/` directory.  
**Fix**: Changed mount to `amttp_models_20251231_174617/` (the actual student artifacts).

### Issue 4: Label Circularity

**Problem**: Fraud labels are derived from Teacher hybrid_score, so Teacher Stack metrics
are artificially perfect.  
**Impact**: Student models are distilled from Teacher — they learn the Teacher's scoring
function, not ground-truth fraud. This is acceptable for production but should be noted
in audit reports.

---

## 10. Feature Reference

### 5 Tabular Features (Production Input)

| Index | Feature | Description |
|-------|---------|-------------|
| 0 | `sender_total_transactions` | Total transaction count for sender |
| 1 | `sender_total_sent` | Total ETH sent by sender |
| 2 | `sender_total_received` | Total ETH received by sender |
| 3 | `sender_sophisticated_score` | Behavioral sophistication metric |
| 4 | `sender_hybrid_score` | Teacher pipeline hybrid score |

### 71 Boost Features (Full Pipeline)

- Indices 0–4: Tabular features (above)
- Indices 5–68: VAE latent dimensions (`vae_z0` through `vae_z63`)
- Index 69: `recon_err` (VAE reconstruction error)
- Index 70: `graphsage_score` (GraphSAGE embedding score)

### 7 Meta-Learner Features

| Index | Feature | Source |
|-------|---------|--------|
| 0 | `recon_err` | VAE |
| 1 | `edge_score` | GATv2 edge attention |
| 2 | `gat_score` | GATv2 node classification |
| 3 | `uncertainty` | Model uncertainty estimate |
| 4 | `sage_score` | GraphSAGE |
| 5 | `xgb_prob` | XGBoost v2 prediction |
| 6 | `lgb_prob` | LightGBM prediction |
