# Hope Machine (4) — Complete Pipeline Documentation

> **Notebook**: `Hope_machine (4).ipynb`  
> **Date**: February 2026  
> **Scope**: End-to-end Teacher model: data pipeline → training → evaluation → deployment  
> **Target Hardware**: Colab T4 / A100 GPU  
> **Dataset**: ~2.6M Ethereum transactions, 113:1 class imbalance (fraud detection)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Data Pipeline](#data-pipeline)
3. [Model Training Pipeline](#model-training-pipeline)
4. [Evaluation Pipeline](#evaluation-pipeline)
5. [Label Generation — How Fraud Labels Are Created](#label-generation--how-fraud-labels-are-created)
6. [Teacher Inference Architecture](#teacher-inference-architecture)
7. [Knowledge Distillation — Teacher → Student](#knowledge-distillation--teacher--student)
8. [Production Inference (Three Serving Paths)](#production-inference-three-serving-paths)
9. [Deployment Pipeline](#deployment-pipeline)
10. [Readiness Checklist — When Models Are Correct](#readiness-checklist--when-models-are-correct)
11. [Session 1 — Probability Threshold Fixes](#session-1--probability-threshold-fixes)
12. [Session 2 — Speed Optimizations (xformers)](#session-2--speed-optimizations-xformers)
13. [Session 3 — AMP/FP16 Stability Hardening](#session-3--ampfp16-stability-hardening)
14. [Cell-by-Cell Change Map](#cell-by-cell-change-map)
15. [Technical Details](#technical-details)
16. [Known Risks & Mitigations](#known-risks--mitigations)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                   AMTTP FRAUD DETECTION SYSTEM                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  TEACHER (Hope_machine notebook — Colab GPU)                    │
│  ┌───────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ VAE+xfmrs │  │   SAINT   │  │Wide&Deep │  │  RNN (GRU)   │ │
│  │ (AE feat) │  │ (xfmrs)   │  │          │  │              │ │
│  └─────┬─────┘  └─────┬─────┘  └────┬─────┘  └──────┬───────┘ │
│        │              │              │               │          │
│  ┌─────┴──────┐  ┌────┴─────┐  ┌────┴─────┐                   │
│  │  XGBoost   │  │ LightGBM │  │ CatBoost │                   │
│  └─────┬──────┘  └────┬─────┘  └────┬─────┘                   │
│        └───────────────┼─────────────┘                          │
│                  ┌─────┴─────┐                                  │
│                  │  LGB      │                                  │
│                  │  Stacking │                                  │
│                  └─────┬─────┘                                  │
│                        │                                        │
│              ┌─────────┴──────────┐                             │
│              │  Calibration +     │                             │
│              │  Threshold Optim   │                             │
│              └─────────┬──────────┘                             │
│                        │                                        │
│                  ARTIFACTS/                                      │
│                  ├── models/ (*.pt, *.json, *.txt, *.cbm)      │
│                  ├── metadata/ (preds, metrics, curves)         │
│                  ├── cache/ (ae_features.npz)                   │
│                  └── feature_schema.json                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  STUDENT (TX-Level — production, CPU-friendly)                  │
│  ┌──────────┐  ┌──────────┐  ┌────────────────┐               │
│  │ XGBoost  │  │ LightGBM │→│ Meta-Learner   │               │
│  │ (21 feat)│  │ (21 feat)│  │ (LogisticReg)  │               │
│  └──────────┘  └──────────┘  └───────┬────────┘               │
│                                       │                         │
│                              risk_engine/                       │
│                              integration_service.py             │
│                              (FastAPI, Docker, port 8002)       │
└─────────────────────────────────────────────────────────────────┘
```

The system uses a **Teacher → Student** distillation pipeline:
1. **Teacher** (this notebook) trains 7 models + stacking ensemble on 171 address-level features using GPU
2. **Student** trains on 21 transaction-level features (available at inference time) using Teacher labels
3. **Production API** serves the Student model via FastAPI + Docker

---

## Data Pipeline

### Cell 1 — Environment Setup
- Installs RAPIDS (cudf, cuml), xformers, xgboost, lightgbm, catboost, optuna, lion-pytorch
- Verifies GPU availability (T4 or A100 required)
- Sets `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` to reduce fragmentation

### Cell 2 — Configuration
- All hyperparameters in a single `cfg = SimpleNamespace(...)` object
- Key data settings: `data_path="merged_clean_imputed_v2.parquet"`, `label_col="label_unified"`
- Artifact directories auto-created under `cfg.artifact_root` (default: `artifacts/`)

### Cell 3 — Imports + GPU Setup
- RAPIDS stack: cudf, cuml, cupy for GPU-accelerated data processing
- xformers: `xops.memory_efficient_attention` (NOT flash attention)
- TF32 enabled for matmul/cudnn, `cudnn.benchmark = True`
- Utility functions: `focal_loss_with_logits` (FP32-safe), `safe_roc_auc`, `safe_average_precision`
- Imbalance utilities: `WeightedRandomSampler`, `compute_imbalance_stats`, `get_scale_pos_weight`
- Threshold optimization: `optimize_threshold()` — finds optimal threshold for F1/F2/precision@recall
- Confidence analysis: `analyze_prediction_confidence()` — flags uncertain predictions

### Cell 3A — Artifact + VRAM Helpers
- `artifact_path()` — resolves paths inside `cfg.artifact_root`
- `save_torch_model()` / `try_load_torch_model()` — persist/load PyTorch models
- `log_metrics()` — persist JSON metrics to `cfg.metrics_dir`
- `fit_probability_calibrator()` — Platt scaling (LogisticRegression) for calibrated probabilities
- `recall_at_target()` — find threshold achieving target recall
- `vram_session()` — context manager for GPU memory guarding

### Cell 4 — Data Loading & Feature Engineering

**Data source**: `merged_clean_imputed_v2.parquet` (~2.6M rows)  
Downloaded from Google Drive if not present locally.

**Leakage columns removed**: `label`, `unnamed:_0`, `index`, `address`, `tx_hash`, `flag`, `erc20_uniq_sent_addr.1`

**Feature engineering** (GPU-accelerated via cudf/cupy):
1. **Periodic time features**: `time_periodic_sin`, `time_periodic_cos`, `time_anomaly` — von Mises-inspired encoding of transaction times
2. **Rolling aggregations**: `txn_count_Xd`, `amt_sum_Xd` for windows [1, 3, 7] days (grouped by address)
3. **Ratio/log features**: `sent_received_ratio`, `log_avg_val_sent`
4. **Frequency encoding**: `erc20_most_rec_token_type_freq`, `erc20_most_sent_token_type_freq`
5. **Chain one-hot encoding** (if multi-chain data present)

### Cell 5 — Data Split

Two split strategies (controlled by `cfg.use_time_based_split`):

| Strategy | Train | Val | Test |
|---|---|---|---|
| **Stratified** (default) | 80% | 10% | 10% |
| **Time-based** | year < cutoff | 50% of remainder | 50% of remainder |

Post-split leakage columns are dropped again (safety net).

**Expected split statistics** (~2.6M samples):
- Train: ~2.1M samples (~18,400 positives, ~0.88% fraud rate)
- Val: ~262K samples (~2,300 positives)
- Test: ~262K samples (~2,300 positives)
- Imbalance ratio: ~113:1

---

## Model Training Pipeline

### Cell 10 — VAE Autoencoder (Feature Extraction)

**Purpose**: Learn a compressed latent representation + reconstruction error as extra features for downstream models. NOT a classifier itself.

**Architecture**: `VAEWithAttention`
- Encoder: Linear → GELU → xformers attention → Linear layers → μ, logvar
- Decoder: Linear → GELU → Linear layers → reconstruction
- Latent dim: 32 (tunable via Optuna)
- xformers `memory_efficient_attention` for the self-attention layer

**Training**:
- Trains on normal transactions only (`cfg.ae_normals_only=True`) — learns normal patterns
- Denoising: masks random features + adds Gaussian noise
- Loss: Huber reconstruction + β·KL divergence + L1 latent sparsity
- AMP with FP16-safe KL (computed in FP32, logvar clamped to [-20, 10])
- Conservative GradScaler (init_scale=1024) + NaN recovery (auto-disable AMP after 15 NaN batches)

**Output**: `X_train_enh`, `X_val_enh`, `X_test_enh` — original features concatenated with:
- 32-dim latent vector (z)
- 1-dim reconstruction error
- Total: `original_features + 33` columns

**Caching**: Features cached to `ae_features.npz`; model to `ae.pt`

### Cell 11 — Hybrid AE+XGB

Quick XGBoost trained on VAE-enhanced features. Produces `hybrid_val_preds` for optional stacking.

### Cell 12 — SAINT Transformer

**Architecture**: `SAINTModel` with `XFormersEncoderLayer`
- FeatureTokenizer → stacked XFormersEncoderLayers → mean pooling → classification head
- xformers attention with `.contiguous()` Q/K/V
- Gradient checkpointing to save VRAM
- Optuna tunes hidden dim, layers, heads, dropout, LR

**Training**:
- WeightedRandomSampler for balanced batches (50/50 pos/neg per batch)
- Focal loss (α=0.25, γ=2.0) — FP32-safe
- OneCycleLR scheduler
- AMP re-enabled with conservative GradScaler + NaN auto-disable (20 batch limit)
- Chunked inference (chunk_size=1024)
- Platt calibration post-training

**Output**: `tabt_val_preds`, `tabt_train_preds`, `tabt_test_preds` → saved to `tabt_preds.npz`

### Cell 13 — Wide & Deep NN

**Architecture**: Wide (linear) + Deep (MLP with residual connections) → single logit
- Optuna tunes layers, sizes, dropout, LR
- WeightedRandomSampler + focal loss + AMP
- Platt calibration

**Output**: `wide_deep_val_preds`, etc. → `wide_deep_preds.npz`

### Cell 14 — RNN (GRU/LSTM)

**Architecture**: GRU or LSTM → linear classification head
- Features reshaped into pseudo-sequences (`cfg.rnn_sequence_steps`)
- Optuna tunes hidden_dim, num_layers, rnn_type, dropout
- WeightedRandomSampler + focal loss + AMP

**Output**: `rnn_val_preds`, etc. → `rnn_preds.npz`

### Cell 15 — Tree Models (XGBoost, LightGBM, CatBoost)

All three train on **raw features** (NOT VAE-enhanced) using GPU-native cudf input.

| Model | Tuning | Special |
|---|---|---|
| **XGBoost** | Bayesian Optimization (50 iters) | `device='cuda'`, `tree_method='hist'` |
| **LightGBM** | Bayesian Optimization (38 iters) | `device='gpu'`, column name sanitization |
| **CatBoost** | Default params | `task_type='GPU'`, `gpu_ram_part=0.9` |

All use dynamic `scale_pos_weight` computed from actual class distribution.

**Output**: `xgb_val_preds`, `lgb_val_preds`, `cat_val_preds` → `tree_preds/`

### Cell 16 — LGB Stacking Meta-Learner

**Architecture**: LightGBM trained on stacked predictions from all base models.

**Input**: Predicted probabilities from up to 7 models:
```
[tabt_prob, wide_deep_prob, rnn_prob, hybrid_prob, xgb_prob, lgbm_prob, catboost_prob]
```

**Training**: GPU-accelerated LightGBM with `scale_pos_weight` + early stopping.

**Calibration**: Platt scaling applied to final stacking predictions.

**Output**: `stacking_val_preds`, `stacking_test_preds` → `stacking_preds.npz`  
**Model**: `stacking_lgbm.txt`

---

## Evaluation Pipeline

### Cell 17 — Comprehensive Final Evaluation

1. **Threshold Optimization**
   - Finds optimal threshold for F1, F2, precision@90%recall
   - Default metric: `cfg.threshold_metric = 'f1'`
   - Search over 200 evenly-spaced thresholds [0.01, 0.99]

2. **Confusion Matrix** (at optimal threshold)
   - Reports TP, FP, FN, TN on test set
   - Highlights Type II errors (missed fraud) separately

3. **Classification Report** (sklearn `classification_report`)

4. **Key Metrics Summary**
   | Metric | Validation | Test |
   |---|---|---|
   | Average Precision (AP) | ✓ | ✓ |
   | ROC AUC | ✓ | ✓ |
   | F1 Score | — | ✓ |
   | Precision | — | ✓ |
   | Recall | — | ✓ |

5. **PR & ROC Curves** — saved to `evaluation_curves.png`

6. **Confidence Analysis**
   - Confident Negative (prob < 0.3)
   - Confident Positive (prob > 0.7)
   - Uncertain (0.3–0.7) — flagged for manual review

7. **Saved artifacts**:
   - `final_evaluation.json` — threshold, all metrics, confusion matrix, data distribution
   - `final_predictions.npz` — val/test predictions + labels + threshold

### Cell 18 — Feature Importance Analysis

- XGBoost built-in importance (gain)
- LightGBM built-in importance (gain)
- SHAP TreeExplainer values (sample of 1000)
- Aggregated cross-method importance ranking
- Plots: `shap_importance.png`, `feature_importance.png`
- CSV: `feature_importance.csv`

### Cell 19 — Model Comparison & Summary

- Side-by-side comparison of all 7 models:
  ```
  Model         Val AP   Test AP   Test F1   Recall   Precision
  STACKING      ...      ...       ...       ...      ...
  XGB           ...      ...       ...       ...      ...
  ...
  ```
- Identifies best model
- Checks for overfitting (Val-Test AP gap > 0.05)
- Lists models with >80% recall (suitable for fraud detection)
- Generates `model_comparison.csv` and `model_comparison.png`
- **Auto-generates** `feature_schema.json` at `ml/Automation/ml_pipeline/models/`

### Cell 20–22 — Artifact Download & Cleanup
- Zips `artifacts/` directory for Colab download
- Terminates Colab runtime

---

## Label Generation — How Fraud Labels Are Created

The system does **not** have ground-truth fraud labels. Instead, it builds labels through a multi-step scoring pipeline, culminating in a `fraud` column that the Teacher and Student models train on.

### Step 1: Compute `hybrid_score` per Address

**File**: `scripts/sophisticated_fraud_detection_ultra.py` (lines 664–668)

$$\text{hybrid\_score} = 0.4 \times \text{xgb\_normalized} + 0.3 \times \text{pattern\_boost} + 0.3 \times \text{soph\_normalized}$$

| Component | Range | How Computed |
|---|---|---|
| `xgb_normalized` | [0, 100] | XGBoost raw score → sigmoid calibration `1/(1+exp(-30*(raw - p75)))` → scaled 0–100 |
| `pattern_boost` | [0, 100] | Rule-based bonus per behavioral pattern: SMURFING=25, STRUCTURING=20, PEELING=20, LAYERING=15, FAN_OUT=15, FAN_IN=15, VELOCITY=15; capped at 100 |
| `soph_normalized` | [0, 100] | `(sophisticated_score / max_sophisticated_score) × 100` |

**Multi-signal bonus** (applied after weighted sum):
- 2 signals active → `hybrid_score *= 1.2`
- 3+ signals active → `hybrid_score *= 1.5`
- Final value clipped to `[0, 100]`

### Step 2: Assign `risk_level` from `hybrid_score`

**Primary path** — PR-curve optimized thresholds (`sophisticated_fraud_detection_ultra.py`, lines 672–693):

```python
optimized_thresholds = optimize_thresholds_pr_curve(
    combined_pd['hybrid_score'].values,
    combined_pd['pattern_count'].values,  # pseudo ground truth: pattern_count >= 3
)
```

This finds the best F1 threshold using `pattern_count >= 3` as proxy ground truth, then derives:

| Risk Level | Threshold | Empirical Value |
|---|---|---|
| CRITICAL | `best_threshold + 15` | ~63.58 |
| HIGH | `best_threshold` | ~48.58 |
| MEDIUM | `best_threshold - 15` | ~33.58 |
| LOW | 20 | 20 |
| MINIMAL | < 20 | < 20 |

**Fallback path** — Fixed thresholds (`scripts/hybrid_scoring_model.py`, lines 109–110):

| Risk Level | Threshold |
|---|---|
| CRITICAL | ≥ 80 |
| HIGH | ≥ 60 |
| MEDIUM | ≥ 40 |
| LOW | ≥ 20 |
| MINIMAL | < 20 |

### Step 3: Create Binary `fraud` Column

**File**: `scripts/create_complete_labeled_dataset.py` (line 186)

```python
addr_pd['fraud'] = addr_pd['risk_level'].isin(['CRITICAL', 'HIGH']).astype(int)
```

This means: **`fraud = 1` when `hybrid_score >= ~48.58`** (the PR-curve optimized HIGH threshold).

Addresses **not** present in the scored dataset get `risk_level = 'MINIMAL'` → `fraud = 0`.

### Step 4: Propagate to Transactions

The output `eth_addresses_labeled.parquet` contains address-level labels. The transaction-level `eth_transactions_full_labeled.parquet` is built by joining these address labels back onto transactions via the sender address:

- If the sender address has `fraud = 1`, all its transactions inherit `fraud = 1`
- If the sender address has `fraud = 0`, all its transactions inherit `fraud = 0`

### Label Statistics (from Teacher metadata)

| Metric | Value |
|---|---|
| Total samples | 1,673,244 |
| Fraud rate | 25.15% |
| Tabular features | 5 (address-level) |
| Teacher ROC AUC | 0.9229 |
| Optimal threshold | 0.7270 |

### ⚠ Important: Labels Are Self-Supervised

These labels are **NOT** ground truth — they are generated by the XGBoost + pattern + sophistication scoring pipeline. The Teacher model trains on these labels, and the Student then distills from the Teacher. This is a **self-supervised** pipeline. Implications:

1. **Circularity warning**: The 5-way comparison in `train_tx_level_models.py` includes Teacher Stack evaluation on the same labels it generated — this metric is circular and inflated
2. **No external validation**: True model quality requires external labeled data (e.g., flagged addresses from exchanges, law enforcement)
3. **Threshold sensitivity**: The fraud rate (25.15%) is determined entirely by the `hybrid_score` threshold; changing it changes everything downstream

---

## Teacher Inference Architecture

The Teacher inference pipeline converts raw features into fraud predictions through a multi-stage ensemble.

### Model File: `ml/Automation/amttp_models_20251231_174617/inference.py`

```
                  ┌─── 5 Tabular Features ───┐
                  │                           │
                  ▼                           ▼
            ┌──────────┐               ┌──────────┐
            │ XGBoost  │               │ LightGBM │
            │(1999 rnd)│               │(2000 rnd)│
            └────┬─────┘               └────┬─────┘
                 │ xgb_prob                  │ lgb_prob
                 ▼                           ▼
           ┌─────────────────────────────────────┐
           │     Meta-Feature Vector (7-dim)     │
           │ [recon, edge, gat, unc, sage,       │
           │  xgb_prob, lgb_prob]                │
           └──────────────┬──────────────────────┘
                          │
                          ▼
                  ┌──────────────┐
                  │ Meta Ensemble│
                  │ (LogReg C=1) │
                  └──────┬───────┘
                         │ fraud_prob
                         ▼
                  ┌──────────────┐
                  │ Risk Levels  │
                  └──────────────┘
```

### `load_models(model_dir)` — Loading

Loads from `amttp_models_20251231_174617/`:

| Artifact | File | Purpose |
|---|---|---|
| XGBoost | `xgboost_fraud.ubj` | Binary classifier on 71 features |
| LightGBM | `lightgbm_fraud.txt` | Binary classifier on 71 features |
| Meta-ensemble | `meta_ensemble.joblib` | LogisticRegression on 7 meta-features |
| Preprocessors | `preprocessors.joblib` | NaN fill, log transform, RobustScaler |
| Metadata | `metadata.json` | Thresholds, performance, feature config |
| Feature config | `feature_config.json` | 71 feature names + label column |

### `preprocess_features(features, preprocessors)` — Preprocessing

```
raw features → NaN fill (median) → log1p transform → RobustScaler → clip ±5σ
```

### `predict_fraud(raw_features, models, threshold)` — Prediction

1. **Preprocess** the 5 tabular features
2. **XGB** `predict_proba` → `xgb_prob`
3. **LGB** `predict` → `lgb_prob`
4. **Build 7-dim meta-feature vector**:
   ```python
   meta_features = [[0.0, 0.0, 0.0, 0.0, 0.0, xgb_prob, lgb_prob]]
   #                 recon edge  gat  unc  sage  ← zeroed (graph/unsupervised not available)
   ```
5. **Meta-ensemble** `predict_proba` → `fraud_prob`
6. **Apply threshold** (default `0.7270`) → binary prediction

### ⚠ Simplified Inference Warning

The standalone `inference.py` **zeros out** the first 5 meta-features (recon_err, edge_score, gat_score, uncertainty, graphsage_score) because these require the full graph/VAE pipeline which is only available during Teacher training. This means standalone Teacher inference uses only XGB + LGB probabilities through the meta-learner.

### Risk Level Thresholds (Teacher)

| Level | Threshold | Action |
|---|---|---|
| CRITICAL | ≥ 0.85 | Block immediately |
| HIGH | ≥ 0.65 | Escrow |
| MEDIUM | ≥ 0.45 | Flag for review |
| LOW | ≥ 0.25 | Monitor |
| MINIMAL | < 0.25 | Approve |

### 71-Feature Breakdown (Teacher)

| Group | Count | Features |
|---|---|---|
| Tabular | 5 | sender_total_transactions, sender_total_sent, sender_total_received, sender_sophisticated_score, sender_hybrid_score |
| VAE Latents | 64 | vae_z0, vae_z1, ..., vae_z63 |
| Reconstruction | 1 | recon_err |
| Graph | 1 | graphsage_score |
| **Total** | **71** | |

---

## Knowledge Distillation — Teacher → Student

The production Student model is trained via **knowledge distillation** — it learns to replicate the Teacher's labels using only features available at transaction time.

### Why Distillation?

| Concern | Teacher | Student |
|---|---|---|
| **Input** | 71 features (address-level + VAE + graph) | 21 features (TX-level + sender aggregates) |
| **Hardware** | GPU required (VAE, GNN, SAINT) | CPU-only (XGB + LGB) |
| **Latency** | Minutes per batch (graph construction) | <10ms per transaction |
| **Training data** | Address-level (1.67M addresses) | Transaction-level (1.34M transactions) |
| **Serving skew** | All 71 features must be computed | Zero skew — same features at train & serve |

### Training Pipeline: `ml/Automation/train_tx_level_models.py`

**Input**: `processed/eth_transactions_full_labeled.parquet`

**Label**: `fraud` column — inherited from Teacher's `hybrid_score` thresholds (see Label Generation above)

**Feature Engineering** (21 features, 3 groups):

| Group | # | Features |
|---|---|---|
| TX Raw | 6 | `value_eth`, `gas_price_gwei`, `gas_used`, `gas_limit`, `nonce`, `transaction_type` |
| Derived | 7 | `gas_efficiency` (gas_used/gas_limit), `value_log` (log1p), `gas_price_log` (log1p), `is_round_amount`, `value_gas_ratio`, `is_zero_value`, `is_high_nonce` (>1000) |
| Sender | 8 | `sender_total_transactions`, `sender_total_sent`, `sender_total_received`, `sender_balance`, `sender_avg_sent`, `sender_unique_receivers`, `sender_in_out_ratio`, `sender_active_duration_mins` |

**Models trained** (in sequence):

| Step | Model | Config | Output |
|---|---|---|---|
| 4 | XGBoost | 500 estimators, max_depth=8, dynamic scale_pos_weight | `xgboost_tx.ubj` |
| 5 | LightGBM | 500 rounds, num_leaves=127, max_depth=8 | `lightgbm_tx.txt` |
| 6 | Meta-Learner | `sklearn.LogisticRegression([xgb_prob, lgb_prob])` | `meta_learner.joblib` |

**5-Way Comparison** (Step 7):

| Model | Type | Features | Note |
|---|---|---|---|
| Teacher Stack | Address-level | 71 (hybrid_score) | ⚠ Circular — evaluated on its own labels |
| Student v2 XGB | Address-level | 71 (padded with zeros) | Legacy student |
| TX-Level XGB | Transaction-level | 21 | New student |
| TX-Level LGB | Transaction-level | 21 | New student |
| TX-Level Ensemble | Transaction-level | 2 (xgb_prob, lgb_prob) | Meta-learner, deployed to production |

**Saved artifacts** (in `tx_level_models/`):

```
tx_level_models/
├── xgboost_tx.ubj         # XGBoost on 21 features
├── lightgbm_tx.txt        # LightGBM on 21 features
├── meta_learner.joblib     # sklearn LogReg on [xgb_prob, lgb_prob]
├── metadata.json           # optimal_threshold, performance metrics
├── feature_config.json     # 21 feature names
└── comparison_results.json # 5-way model comparison
```

---

## Production Inference (Three Serving Paths)

The system provides three inference APIs, each optimized for a different use case.

### Path A: TX-Level Ensemble (Primary — `risk_engine/integration_service.py`)

**Port**: 8002 | **Model**: TX-Level XGB + LGB + Meta-Learner | **Features**: 21

This is the **production-deployed** inference path with zero training/serving skew.

```
TransactionRequest (18 fields)
        │
        ▼
  _extract_features()        ← 21 features in exact training order
        │
        ├── TX Raw [0-5]:     value_eth, gas_price_gwei, gas_used, gas_limit, nonce, transaction_type
        ├── Derived [6-12]:   gas_efficiency, value_log, gas_price_log, is_round_amount,
        │                     value_gas_ratio, is_zero_value, is_high_nonce
        └── Sender [13-20]:   sender_total_transactions...sender_active_duration_mins
        │
        ▼
  _predict_ensemble()
        │
        ├── XGBoost predict_proba → xgb_prob
        ├── LightGBM predict     → lgb_prob
        └── Meta-Learner([xgb_prob, lgb_prob]) → fraud_prob
        │
        ▼
  score_transaction()
        │
        ├── ML score = fraud_prob × 1000
        ├── Heuristic score (value, address pattern, contract, nonce, gas)
        ├── Combine: 70% ML + 30% heuristic (normal case)
        │   └── Override: if ≥4 red flags + low ML → heuristic takes over
        └── Risk level from combined score
        │
        ▼
  RiskResponse
        ├── risk_score: 0–1000
        ├── risk_level: minimal | low | medium | high | critical
        ├── confidence: 0.9879 (from TX-Level Ensemble ROC-AUC)
        ├── factors: {ml_prediction, model_used, red_flags, ...}
        └── → AlertStore (SIEM dashboard integration)
```

**Risk Level Mapping** (integration_service.py):

| Risk Score | Level | Action |
|---|---|---|
| 0–199 | minimal | APPROVE |
| 200–399 | low | MONITOR |
| 400–599 | medium | FLAG |
| 600–799 | high | ESCROW |
| 800–1000 | critical | BLOCK |

**Model Fallback Chain**:
1. **TX-Level models** (`xgboost_tx.ubj` + `lightgbm_tx.txt` + `meta_learner.joblib`) — preferred
2. **Legacy Student v2** (`xgboost_fraud.ubj` + `lightgbm_fraud.txt`) — 71 features, padded
3. **Heuristic-only** — if no models found, uses rule-based scoring (confidence = 0.55)

**API Endpoints**:

| Endpoint | Method | Purpose |
|---|---|---|
| `/score` | POST | Score single transaction |
| `/batch` | POST | Score multiple transactions |
| `/health` | GET | Health check + model status |
| `/model/info` | GET | Model details + performance |
| `/alerts` | GET | Dashboard alerts (SIEM) |
| `/dashboard/stats` | GET | Aggregate statistics |
| `/dashboard/timeline` | GET | Time-series data for charts |
| `/alerts/{id}/action` | POST | RESOLVE, FALSE_POSITIVE, INVESTIGATING, BLOCK |

### Path B: Address-Level CPU Predictor (`ml_pipeline/inference/cpu_api.py`)

**Port**: 8000 | **Model**: XGBoost (single) | **Features**: address-level (from schema)

This serves the **Teacher-style** address-level predictions on CPU.

```
PredictRequest {transaction_id, features: Dict[str, float]}
        │
        ▼
  CPUPredictor
        │
        ├── _load_feature_schema()   ← feature_schema.json (from Cell 19)
        ├── _load_thresholds()       ← thresholds.json (calibrated from training)
        ├── _load_reference_distribution() ← reference_scores_xgb.npy (validation scores)
        │   └── Pre-computes percentile cutoffs: BLOCK=p99, ESCROW=p95, REVIEW=p85, MONITOR=p70
        └── _load_model()            ← xgb.json (XGBoost Booster)
        │
        ▼
  predict_with_action()
        │
        ├── predict_proba(features)  → raw probability
        ├── _score_to_percentile()   → rank within reference distribution
        └── Action from percentile cutoffs (NOT absolute thresholds)
        │
        ▼
  PredictResponse
        ├── risk_score: float (raw probability)
        ├── percentile: float (rank in reference distribution)
        ├── prediction: 0 | 1 (binary, using calibrated threshold)
        └── action: BLOCK | ESCROW | REVIEW | MONITOR | APPROVE
```

**Key Design**: Uses **percentile-based** risk tiers (top-N% of reference distribution) rather than absolute probability cutoffs, because raw model probabilities are poorly calibrated across different data distributions.

### Path C: Hybrid Multi-Signal API (`ml_pipeline/inference/hybrid_api.py`)

**Port**: configurable | **Signals**: ML + Graph (Memgraph) + Behavioral Patterns

This is the most sophisticated inference path, combining three independent signals.

```
AddressScoreRequest {address}
        │
        ├──── Signal 1: ML Score ──────────────────────────┐
        │     CPU Predictor → ml_score                     │
        │     ml_signal = (ml_score >= 0.55)              │
        │                                                   │
        ├──── Signal 2: Graph Score ───────────────────────┤
        │     Memgraph query → direct/2-hop/3-hop links    │
        │     to sanctioned/mixer addresses                │
        │     graph_signal = (graph_score > 0)             │
        │                                                   │
        ├──── Signal 3: Behavioral Patterns ───────────────┤
        │     sophisticated_fraud_patterns.csv lookup       │
        │     SMURFING, LAYERING, PEELING, STRUCTURING...  │
        │     pattern_signal = (patterns found)            │
        │                                                   │
        └──── Combine ─────────────────────────────────────┘
              │
              ▼
        hybrid_score = 0.30 × ml_norm + 0.35 × graph_norm + 0.35 × pattern_norm
              │
              ├── Multi-signal boost: 2 signals → ×1.2, 3 signals → ×1.5
              └── Require 2+ signals to ESCROW/FLAG (reduces false positives)
              │
              ▼
        AddressScoreResponse
              ├── hybrid_score, risk_level (CRITICAL/HIGH/MEDIUM/LOW)
              ├── action: ESCROW | FLAG | REVIEW | MONITOR | APPROVE
              ├── Per-signal breakdown (ml_score, graph_score, patterns)
              └── signal_count (for 2-signal requirement audit)
```

**Multi-Signal Requirement**: By default (`require_multi_signal: True`), ESCROW/FLAG actions require at least 2 independent signals confirming fraud. This dramatically reduces false positive rate at the cost of some missed detections.

### Serving Path Comparison

| Feature | Path A (TX-Level) | Path B (CPU Address) | Path C (Hybrid) |
|---|---|---|---|
| **Level** | Transaction | Address | Address |
| **ML Model** | XGB + LGB + Meta | XGBoost (single) | XGBoost (single) |
| **Features** | 21 (TX raw + derived + sender) | ~171 (address-level) | ~171 + graph + patterns |
| **Graph signals** | No | No | Yes (Memgraph) |
| **Behavioral patterns** | No | No | Yes |
| **Risk assignment** | Absolute score (0-1000) | Percentile-based | Hybrid score (0-100) |
| **Multi-signal** | Heuristic red flags | N/A | ML + Graph + Pattern |
| **Latency** | <10ms | <50ms | <500ms (graph queries) |
| **Dependencies** | XGB, LGB, joblib | XGB | XGB, Memgraph, pattern CSV |
| **Docker** | `risk-engine` | `cpu-api` | `graph-api` |
| **Production use** | ✅ Primary | Fallback / batch | Investigation / SIEM |

### Step 1: Download Artifacts from Colab

After training completes, download `all_artifacts.zip` containing:
```
artifacts/
├── models/
│   ├── ae.pt                    # VAE autoencoder
│   ├── tabt.pt                  # SAINT transformer
│   ├── wide_deep.pt             # Wide & Deep NN
│   ├── rnn.pt                   # GRU/LSTM
│   ├── xgb.json                 # XGBoost
│   ├── lgbm.txt                 # LightGBM
│   ├── catboost.cbm             # CatBoost
│   ├── stacking_lgbm.txt        # Stacking meta-learner
│   ├── hybrid_xgb.json          # Hybrid AE+XGB
│   ├── tabt_calibrator.joblib   # Platt calibrators
│   ├── wide_deep_calibrator.joblib
│   ├── rnn_calibrator.joblib
│   └── stacking_calibrator.joblib
├── metadata/
│   ├── final_evaluation.json    # thresholds + metrics
│   ├── final_predictions.npz    # raw predictions
│   ├── model_comparison.csv     # all models side-by-side
│   ├── feature_importance.csv   # ranked features
│   ├── stacking_preds.npz       # stacking predictions
│   └── *.png                    # evaluation plots
└── cache/
    └── ae_features.npz          # VAE-enhanced features cache
```

### Step 2: Place Models in Serving Directories

```powershell
# Address-level models (for cpu_api.py)
Copy-Item artifacts/models/* ml/Automation/ml_pipeline/models/trained/

# Student training uses Teacher labels — run train_tx_level_models.py
# to produce TX-level models for the production API
```

### Step 3: Train Student (TX-Level Models)

```bash
cd ml/Automation
python train_tx_level_models.py
```

This produces TX-level models in `tx_level_models/`:
- `xgboost_tx.ubj` — XGBoost on 21 TX features
- `lightgbm_tx.txt` — LightGBM on 21 TX features
- `meta_learner.joblib` — LogisticRegression meta-ensemble
- `metadata.json` — optimal threshold, feature config, performance metrics

The 21 TX-level features are (3 groups):
```
TX Raw (6):     value_eth, gas_price_gwei, gas_used, gas_limit, nonce, transaction_type
Derived (7):    gas_efficiency, value_log, gas_price_log, is_round_amount,
                value_gas_ratio, is_zero_value, is_high_nonce
Sender (8):     sender_total_transactions, sender_total_sent, sender_total_received,
                sender_balance, sender_avg_sent, sender_unique_receivers,
                sender_in_out_ratio, sender_active_duration_mins
```

### Step 4: Deploy via Docker

```bash
# Development (single service)
docker compose up risk-engine

# Full stack (risk engine + graph API + memgraph)
docker compose -f docker-compose.full.yml up ml-risk-engine graph-api memgraph
```

**Service endpoints**:

| Service | Port | Endpoint | Description |
|---|---|---|---|
| `risk-engine` | 8002 | `POST /score` | Score a single transaction |
| `risk-engine` | 8002 | `POST /score/batch` | Score multiple transactions |
| `risk-engine` | 8002 | `GET /health` | Health check + model info |
| `risk-engine` | 8002 | `GET /alerts` | Dashboard alerts |
| `graph-api` | 8001 | `POST /predict` | Multi-signal (ML + graph) |
| `cpu-api` | 8000 | `POST /predict` | Address-level CPU inference |

### Step 5: Verify Production Predictions

```bash
# Smoke test
cd ml/Automation/risk_engine
python test_student_model.py

# Manual curl
curl -X POST http://localhost:8002/score \
  -H "Content-Type: application/json" \
  -d '{"tx_hash":"0x...", "from_address":"0x...", "to_address":"0x...", "value":1.5, "gas":21000, "gas_price":20000000000, "gas_used":21000, "nonce":5, "input":"0x"}'
```

**Response structure**:
```json
{
  "tx_hash": "0x...",
  "risk_score": 0.73,
  "risk_level": "HIGH",
  "fraud_probability": 0.68,
  "action": "REVIEW",
  "confidence": 0.85,
  "model_version": "tx_level_v1"
}
```

**Risk levels**: `CRITICAL` (>0.9) → `HIGH` (>0.7) → `MEDIUM` (>0.4) → `LOW` (>0.2) → `MINIMAL`  
**Actions**: `BLOCK`, `ESCROW`, `REVIEW`, `MONITOR`, `APPROVE`

---

## Readiness Checklist — When Models Are Correct

### Training Quality Gates

Run these checks after Cell 19 completes. **All must pass** before proceeding to deployment.

| # | Check | Threshold | Where to Look |
|---|---|---|---|
| 1 | **Stacking Test AP** | ≥ 0.40 | Cell 19 model comparison table |
| 2 | **Stacking Test AUC** | ≥ 0.90 | Cell 19 model comparison table |
| 3 | **Test Recall** (at optimal threshold) | ≥ 0.80 | Cell 17 classification report |
| 4 | **Val-Test AP gap** (overfitting check) | < 0.05 | Cell 19 overfitting warnings |
| 5 | **No NaN losses in training** | 0 NaN or ≤5 skipped | Training output logs (AE, SAINT) |
| 6 | **Feature schema generated** | File exists + >100 features | `feature_schema.json` |
| 7 | **All 7 model artifacts saved** | All files present in artifacts/models/ | Cell 19 artifact listing |
| 8 | **Calibrators produce [0,1] probabilities** | No probs >1 or <0 | Cell 17 score distribution plot |

### Evaluation Artifacts to Review

Before deployment, manually verify these outputs:

1. **`final_evaluation.json`** — Check `optimal_threshold` is reasonable (typically 0.01–0.30 for imbalanced data, NOT 0.5)
2. **`evaluation_curves.png`** — PR curve should be well above the random baseline; ROC curve should hug top-left
3. **`model_comparison.csv`** — Stacking should be top or within 0.01 AP of the best single model
4. **`feature_importance.csv`** — Top features should be domain-meaningful (e.g., `total_ether_sent`, `sent_received_ratio`), NOT leakage

### Student Model Quality Gates

After running `train_tx_level_models.py`:

| # | Check | Threshold | Where to Look |
|---|---|---|---|
| 1 | **TX-Level ROC AUC** | ≥ 0.95 | `tx_level_models/metadata.json` |
| 2 | **TX-Level PR AUC** | ≥ 0.85 | `tx_level_models/metadata.json` |
| 3 | **Teacher-Student agreement** | ≥ 90% | `evaluate_teacher_vs_student.py` output |
| 4 | **Score correlation** | ≥ 0.85 | `evaluate_teacher_vs_student.py` output |

### Production Deployment Checklist

| # | Step | Command | Expected |
|---|---|---|---|
| 1 | Copy Teacher artifacts | `Copy-Item artifacts/models/* ml/.../trained/` | All files present |
| 2 | Train Student | `python train_tx_level_models.py` | `tx_level_models/` populated |
| 3 | Run evaluation | `python evaluate_teacher_vs_student.py` | Agreement ≥90% |
| 4 | Start Docker | `docker compose up risk-engine` | Health check passes |
| 5 | Smoke test | `python test_student_model.py` | Returns valid risk scores |
| 6 | Load test | Send 1000 requests | p99 latency < 200ms |
| 7 | Update thresholds | Edit `calibrated_thresholds.json` if needed | Matches `final_evaluation.json` |

### Monitoring in Production

- **Model drift**: `ml/Automation/model_drift_monitor.py` — monitors input feature distributions
- **Alerts dashboard**: `GET /alerts` endpoint shows flagged transactions
- **Recalibration**: `ml/Automation/ml_pipeline/recalibrate_ml.py` — periodic recalibration on new data

---

## Session 1 — Probability Threshold Fixes

**Problem**: All models in the AMTTP pipeline (Teacher notebook, Student, cpu_predictor.py, proofs notebook) used hardcoded probability thresholds (e.g. `> 0.5`) that were inappropriate for the extreme 113:1 class imbalance. This caused near-zero recall on fraud cases.

**Fix Applied**: Replaced all hardcoded thresholds with **percentile-based dynamic thresholds** computed from the validation set. The threshold is tuned to achieve a target recall (default 90%).

**Files Changed**:
- `Hope_machine (4).ipynb` — Teacher notebook
- Student model pipeline
- `cpu_predictor.py`
- Proofs notebook

---

## Session 2 — Speed Optimizations (xformers)

**Goal**: Optimize the notebook for maximum training speed using `xformers` memory-efficient attention. Flash Attention was explicitly excluded (difficult to install).

### 2.1 Configuration (Cell 2)

| Parameter | Before | After | Reason |
|---|---|---|---|
| `batch_size` | 128 | **256** | Larger batches = better GPU utilization |
| `dataloader_workers` | 0 | **2** | Async data prefetching from CPU |
| `use_pin_memory` | *(missing)* | **True** | Faster CPU→GPU transfers with workers>0 |
| `use_xformers` | *(missing)* | **True** | Enable xformers memory_efficient_attention |

### 2.2 VAE Attention — xformers (Cell 10)

**Before**: `nn.MultiheadAttention` (standard PyTorch, no xformers)  
**After**: Manual Q/K/V projections → `xops.memory_efficient_attention()`

```python
# Before
self.attention = nn.MultiheadAttention(hidden, num_heads, dropout=dropout, batch_first=True)
attn_output, _ = self.attention(h.unsqueeze(1), h.unsqueeze(1), h.unsqueeze(1))

# After
q = self.q_proj(h).view(B, 1, self.num_heads, self.head_dim).contiguous()
k = self.k_proj(h).view(B, 1, self.num_heads, self.head_dim).contiguous()
v = self.v_proj(h).view(B, 1, self.num_heads, self.head_dim).contiguous()
attn_output = xops.memory_efficient_attention(q, k, v, p=drop_p)
```

Key detail: `.contiguous()` is required on Q/K/V tensors — xformers requires contiguous memory layout.

### 2.3 SAINT Transformer — XFormersEncoderLayer (Cell 12)

**Before**: `nn.TransformerEncoderLayer` (standard PyTorch)  
**After**: Custom `XFormersEncoderLayer` class using `xops.memory_efficient_attention()`

```python
class XFormersEncoderLayer(nn.Module):
    """Pre-norm transformer layer with xformers attention."""
    def forward(self, x):
        B, S, D = x.shape
        h = self.norm1(x)
        q = self.q_proj(h).view(B, S, self.nhead, self.head_dim).contiguous()
        k = self.k_proj(h).view(B, S, self.nhead, self.head_dim).contiguous()
        v = self.v_proj(h).view(B, S, self.nhead, self.head_dim).contiguous()
        attn_out = xops.memory_efficient_attention(q, k, v, p=drop_p)
        ...
```

SAINTModel now stacks `XFormersEncoderLayer` instances with gradient checkpointing.

### 2.4 SAINT AMP Re-Enabled (Cell 12)

**Before**: AMP was **disabled** for SAINT ("for stability" — commented out)  
**After**: AMP re-enabled with xformers (xformers stabilizes mixed precision by handling attention internally)

### 2.5 DataLoader Optimizations (Cells 12, 13, 14)

All DataLoaders updated with speed parameters:

```python
DataLoader(
    dataset,
    batch_size=effective_batch,
    sampler=weighted_sampler,
    pin_memory=cfg.use_pin_memory,          # NEW: True
    num_workers=cfg.dataloader_workers,      # NEW: 2
    persistent_workers=cfg.dataloader_workers > 0,  # NEW: True (reuse workers)
)
```

Applied to: SAINT, Wide&Deep, RNN training DataLoaders.

### 2.6 Inference Mode (Cells 10, 12, 13, 14)

**Before**: `torch.no_grad()` everywhere  
**After**: `torch.inference_mode()` — faster than no_grad (disables autograd entirely)

Applied to: AE validation, AE encoding, SAINT chunked inference, Wide&Deep eval, RNN eval.

### 2.7 Increased Chunk Sizes

| Location | Before | After |
|---|---|---|
| SAINT chunked_inference | 512 | **1024** |
| AE chunked_ae_encode | 256 | **512** |
| SAINT effective batch | 64 | **128** |

---

## Session 3 — AMP/FP16 Stability Hardening

**Motivation**: User concern that AMP was previously disabled because training was unstable — NaN losses, "expected Half got Float" errors, memory crashes. All AMP safety guards below were added to prevent these issues while keeping FP16 speed.

### 3.1 VAE logvar Clamping (Cell 10)

**Problem**: `logvar.exp()` in the reparameterization trick can overflow FP16 (max ≈ 65504). `exp(12) ≈ 162755` → overflow → NaN → training crash.

**Fix**: Clamp logvar before exp() in `reparameterize()`:

```python
def reparameterize(self, mu, logvar):
    # FP16 max ≈ 65504, exp(11) ≈ 59874 → safe; exp(12) overflows
    logvar = torch.clamp(logvar, min=-20.0, max=10.0)
    std = torch.exp(0.5 * logvar)
    ...
```

### 3.2 FP32 KL Divergence Computation (Cell 10)

**Problem**: KL divergence `= -0.5 * mean(1 + logvar - mu² - exp(logvar))` contains `exp(logvar)` which overflows in FP16.

**Fix**: Exit autocast before KL computation, force FP32:

```python
# Forward pass in FP16 (fast)
with torch.autocast(device_type='cuda', dtype=torch.float16, enabled=_ae_use_amp):
    rec, _, mu, logvar = ae(noisy)
    recon_loss = F.huber_loss(rec, batch, delta=1.0)

# KL in FP32 (safe — outside autocast)
mu_f32 = mu.float()
logvar_f32 = torch.clamp(logvar.float(), min=-20.0, max=10.0)
kl_loss = -0.5 * torch.mean(1 + logvar_f32 - mu_f32.pow(2) - logvar_f32.exp())
```

This pattern is also applied in the AE validation loop.

### 3.3 Focal Loss FP32 Safety (Cell 3)

**Problem**: `focal_loss_with_logits` can underflow in FP16 when computing `(1-pt)^gamma` with gamma=2.0.

**Fix**: Force FP32 at the top of the function:

```python
def focal_loss_with_logits(logits, targets, alpha=0.25, gamma=2.0, pos_weight=None):
    # AMP SAFETY: always compute focal loss in FP32
    logits = logits.float()
    targets = targets.float()
    ...
```

### 3.4 Conservative GradScaler Parameters (Cells 10, 12)

**Problem**: Default GradScaler starts with `init_scale=65536` and doubles every 2000 steps. With KL loss, this can spike the loss scale to overflow levels before the scaler backs off.

**Fix**: Conservative scaler for both AE and SAINT:

```python
ae_scaler = torch.amp.GradScaler('cuda', enabled=_ae_use_amp,
    init_scale=2**10,         # 1024 (not 65536) — start low
    growth_interval=2000,     # double less often
    backoff_factor=0.25       # quarter on overflow (recover fast)
)
```

| Parameter | Default | Ours | Why |
|---|---|---|---|
| `init_scale` | 65536 | **1024** | Prevent early overflow with KL loss |
| `growth_interval` | 2000 | **2000** | Same (already conservative) |
| `backoff_factor` | 0.5 | **0.25** | Recover faster after overflow |

### 3.5 NaN Batch Skip + Auto-Disable AMP (Cells 10, 12)

**Problem**: Even with safety guards, rare edge cases can produce NaN loss (e.g., adversarial batch composition, sudden scale spike). Without recovery, this crashes training.

**Fix**: NaN recovery loop with auto-disable fallback:

```python
if not torch.isfinite(loss):
    _ae_nan_count += 1
    print(f"⚠️ AE NaN loss ... (skip {_ae_nan_count}/{_ae_nan_limit})")
    opt.zero_grad(set_to_none=True)
    ae_scaler.update()  # keep scaler in sync
    if _ae_nan_count >= _ae_nan_limit and _ae_use_amp:
        print("⚠️ Too many NaN → disabling AMP for rest of AE training")
        _ae_use_amp = False
        ae_scaler = torch.amp.GradScaler('cuda', enabled=False)
    del rec, mu, logvar, mu_f32, logvar_f32
    continue
```

- **AE**: limit = 15 NaN batches before auto-disabling AMP
- **SAINT**: limit = 20 NaN batches before auto-disabling AMP

This ensures the training always completes — worst case it falls back to FP32 (slower but stable).

### 3.6 xformers .contiguous() Guard (Cells 10, 12)

**Problem**: xformers `memory_efficient_attention` requires contiguous tensors. Non-contiguous views from `.view()` can cause silent wrong results or CUDA errors.

**Fix**: Added `.contiguous()` to all Q/K/V projections:

```python
q = self.q_proj(h).view(B, 1, self.num_heads, self.head_dim).contiguous()
k = self.k_proj(h).view(B, 1, self.num_heads, self.head_dim).contiguous()
v = self.v_proj(h).view(B, 1, self.num_heads, self.head_dim).contiguous()
```

Applied to both VAEWithAttention.encode() and XFormersEncoderLayer.forward().

---

## Cell-by-Cell Change Map

| Cell # | Lines | Component | Changes |
|---|---|---|---|
| 2 | 34–240 | **Configuration** | `batch_size` 128→256, `dataloader_workers` 0→2, added `use_pin_memory=True`, added `use_xformers=True` |
| 3 | 243–761 | **Imports + Utilities** | `focal_loss_with_logits`: added `logits.float()` + `targets.float()` at top for FP32 safety |
| 10 | 1085–1604 | **VAE + AE Training** | xformers attention (Q/K/V + `memory_efficient_attention`), logvar clamping (`-20, +10`), FP32 KL loss, conservative GradScaler, NaN skip recovery (15 limit), auto-disable AMP fallback, `inference_mode()` in validation, `.contiguous()` on Q/K/V |
| 12 | 1651–2170 | **SAINT Transformer** | New `XFormersEncoderLayer` class (replaces `nn.TransformerEncoderLayer`), AMP re-enabled, conservative GradScaler (init_scale=1024), NaN skip recovery (20 limit), auto-disable AMP, `pin_memory`+`num_workers`+`persistent_workers` on DataLoader, `inference_mode()`, chunk_size 512→1024 |
| 13 | 2173–2550 | **Wide & Deep NN** | `pin_memory`+`num_workers`+`persistent_workers` on DataLoader, `inference_mode()` for eval |
| 14 | 2553–2928 | **RNN (GRU/LSTM)** | `pin_memory`+`num_workers`+`persistent_workers` on DataLoader, `inference_mode()` for eval |
| 15 | 2931–3196 | **Tree Models** | No changes (already GPU-native via RAPIDS/XGBoost/LightGBM/CatBoost) |
| 16–19 | 3199–4002 | **Stacking + Eval** | No changes |

---

## Technical Details

### xformers vs Flash Attention

We use **xformers `memory_efficient_attention()`**, NOT Flash Attention:
- `xformers` is a pip-installable library by Meta
- Flash Attention requires custom CUDA compilation (problematic on Colab)
- xformers automatically picks the best kernel (cutlass, etc.) based on GPU
- Tensor shape: `(B, S, H, D)` where B=batch, S=seq_len, H=heads, D=head_dim
- Dropout is handled natively via `p=` parameter

### AMP Architecture (Split Precision)

The AMP strategy is **split precision**: forward pass in FP16 for speed, loss computation in FP32 for stability.

```
Forward Pass (FP16):    x → VAE → rec, mu, logvar       ← autocast
Recon Loss (FP16):      huber_loss(rec, batch)            ← still in autocast
KL Loss (FP32):         -0.5 * mean(1 + logvar - mu² - exp(logvar))  ← OUTSIDE autocast
Total Loss (FP32):      recon.float() + beta*KL + L1      ← explicit .float()
Backward (scaled):      scaler.scale(loss).backward()
Gradient Clip:          scaler.unscale_() → clip_grad_norm_
Optimizer Step:         scaler.step(opt) → scaler.update()
```

### GradScaler Lifecycle

```
Normal batch:   scale(loss).backward() → unscale_() → step() → update()
NaN batch:      zero_grad() → update() → continue (skip backward entirely)
Auto-disable:   After N NaN batches, replace scaler with GradScaler(enabled=False)
```

---

## Known Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| FP16 overflow in KL loss | **Eliminated** | logvar clamped to [-20, 10], KL computed in FP32 |
| "Expected Half got Float" error | **Eliminated** | Explicit `.float()` on KL operands; focal_loss forces FP32 |
| NaN loss crash | **Mitigated** | NaN skip + auto-disable AMP (15/20 batch limit) |
| OOM with batch_size=256 | **Low** (T4 has 15GB) | VRAM guards check free memory before each epoch |
| xformers non-contiguous tensor | **Eliminated** | `.contiguous()` on all Q/K/V before xformers call |
| GradScaler scale explosion | **Mitigated** | init_scale=1024, growth_interval=2000, backoff=0.25 |
| Focal loss underflow in FP16 | **Eliminated** | Forces FP32 at function entry |

---

## Performance Impact (Expected)

| Optimization | Expected Speedup | Memory Impact |
|---|---|---|
| xformers attention (VAE) | ~1.3–1.5x on attention | Slightly less VRAM |
| xformers attention (SAINT) | ~1.5–2x on attention | Slightly less VRAM |
| AMP re-enabled (SAINT) | ~1.5–2x on training | ~40% less VRAM |
| AMP enabled (AE) | ~1.3–1.5x on training | ~30% less VRAM |
| batch_size 128→256 | ~1.2–1.4x throughput | More VRAM per batch |
| DataLoader workers=2 | ~1.1–1.2x (data-bound) | Minimal |
| pin_memory + persistent_workers | ~1.05x | Minimal |
| inference_mode() | ~1.05–1.1x on eval | Slightly less |
| Larger chunk sizes | ~1.1x on inference | More VRAM per chunk |

**Overall expected speedup**: **2–3x** end-to-end training time compared to the original (no xformers, no AMP, batch_size=128, workers=0).
