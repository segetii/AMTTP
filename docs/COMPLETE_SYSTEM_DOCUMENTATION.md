# AMTTP Complete System Documentation

## Ethereum Fraud Detection Pipeline - Full Technical Reference

**Version:** 1.0  
**Last Updated:** January 2, 2026  
**Author:** AMTTP Development Team

---

# Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Data Sources](#3-data-sources)
4. [Feature Engineering](#4-feature-engineering)
5. [Labeling Methodology](#5-labeling-methodology)
6. [Model Architecture](#6-model-architecture)
7. [Training Pipeline](#7-training-pipeline)
8. [Evaluation Results](#8-evaluation-results)
9. [The 8% Problem](#9-the-8-problem)
10. [Production Deployment](#10-production-deployment)
11. [Troubleshooting](#11-troubleshooting)
12. [Quick Reference](#12-quick-reference)

---

# 1. Executive Summary

## Project Overview

AMTTP (Anti-Money Laundering Transaction Tracking Protocol) is an ensemble machine learning system for detecting fraudulent Ethereum transactions.

## Key Achievements

| Metric | Value |
|--------|-------|
| **ROC-AUC** | 0.9229 (92.29%) |
| **PR-AUC** | 0.8609 (86.09%) |
| **Transactions Analyzed** | 1,673,244 |
| **Fraud Detection Rate** | 92% |
| **False Positive Rate** | ~12% |

## Business Value

- **Real-time fraud detection** on Ethereum transactions
- **Regulatory compliance** with FCA/AML requirements
- **Cost savings** from prevented fraud
- **Explainable AI** for audit trails

---

# 2. System Architecture

## High-Level Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AMTTP FRAUD DETECTION PIPELINE                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌────────────┐ │
│  │  KAGGLE      │    │  BIGQUERY    │    │  ETHERSCAN   │    │  OFAC      │ │
│  │  LABELED     │    │  20-DAY ETH  │    │  LABELS      │    │  SANCTIONS │ │
│  │  DATASET     │    │  TRANSACTIONS│    │              │    │  LIST      │ │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘    └─────┬──────┘ │
│         │                   │                   │                   │        │
│         ▼                   ▼                   ▼                   ▼        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    FEATURE ENGINEERING (127 features)                 │   │
│  │  • Raw Transaction Features (8)                                       │   │
│  │  • Aggregated Features (12)                                           │   │
│  │  • Temporal Features (8)                                              │   │
│  │  • Behavioral Ratios (10)                                             │   │
│  │  • Sophistication Patterns (15)                                       │   │
│  │  • Graph Features (12)                                                │   │
│  │  • Deep Learning Features (67)                                        │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         MODEL ENSEMBLE                                │   │
│  │                                                                       │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐                     │   │
│  │  │ BetaVAE │ │  VGAE   │ │  GATv2  │ │GraphSAGE│                     │   │
│  │  │(64 dim) │ │(32 dim) │ │(64 dim) │ │(128 dim)│                     │   │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘                     │   │
│  │       │           │           │           │                           │   │
│  │       └───────────┴───────────┴───────────┘                           │   │
│  │                         │                                             │   │
│  │                         ▼                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────┐     │   │
│  │  │              XGBoost + LightGBM (86 features)               │     │   │
│  │  │              ROC-AUC: 0.917    ROC-AUC: 0.923               │     │   │
│  │  └─────────────────────────────────────────────────────────────┘     │   │
│  │                         │                                             │   │
│  │                         ▼                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────┐     │   │
│  │  │              META-LEARNER (Logistic Regression)             │     │   │
│  │  │                    Final ROC-AUC: 0.9229                    │     │   │
│  │  └─────────────────────────────────────────────────────────────┘     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    RISK CLASSIFICATION                                │   │
│  │  • CRITICAL (>0.90): Immediate block                                  │   │
│  │  • HIGH (>0.75): Manual review required                               │   │
│  │  • MEDIUM (>0.50): Enhanced monitoring                                │   │
│  │  • LOW (<0.30): Normal processing                                     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# 3. Data Sources

## 3.1 Kaggle Labeled Dataset

**Source:** Ethereum Fraud Detection Dataset  
**Records:** ~10,000 labeled addresses  
**Labels:** Binary (fraud/legitimate)

**Used For:**
- Training initial XGBoost model (XGBv1)
- Generating pseudo-labels for BigQuery data

## 3.2 BigQuery Ethereum Data

**Source:** Google BigQuery `bigquery-public-data.crypto_ethereum`  
**Date Range:** December 1-20, 2025 (20 days)  
**Records:** 1,673,244 transactions

**SQL Query Used:**
```sql
SELECT
    t.hash as tx_hash,
    t.block_number,
    t.block_timestamp,
    t.from_address,
    t.to_address,
    t.value / 1e18 as value_eth,
    t.gas_price / 1e9 as gas_price_gwei,
    t.gas as gas_limit,
    t.receipt_gas_used as gas_used,
    t.transaction_type,
    t.nonce,
    t.transaction_index
FROM `bigquery-public-data.crypto_ethereum.transactions` t
WHERE DATE(t.block_timestamp) BETWEEN '2025-12-01' AND '2025-12-20'
    AND t.value > 0
    AND t.to_address IS NOT NULL
```

## 3.3 Etherscan Labels

**Source:** Etherscan API  
**Data:** Known fraud/phishing/scam addresses  
**Used For:** Ground truth validation

## 3.4 OFAC Sanctions List

**Source:** US Treasury OFAC  
**Data:** Sanctioned cryptocurrency addresses  
**Used For:** Regulatory compliance checks

---

# 4. Feature Engineering

## 4.1 Feature Categories

| Category | Count | Description |
|----------|-------|-------------|
| Raw Transaction | 8 | Direct from blockchain |
| Basic Aggregations | 12 | Counts, sums, averages |
| Temporal Features | 8 | Time-based patterns |
| Behavioral Ratios | 10 | Normalized behaviors |
| Sophistication Patterns | 15 | Fraud pattern detection |
| Graph Features | 12 | Network analysis |
| Deep Learning | 67 | VAE + GraphSAGE |
| **Total** | **127** | |

## 4.2 Key Features with Formulas

### XGB Score
```python
# Source: XGBoost model trained on Kaggle labeled data
# Input: 21 address-level features
# Output: Probability [0, 1]

xgb_score = xgb_model.predict_proba(X)[:, 1]
```

### Sophisticated Score
```python
# Source: Rule-based pattern detection
# Output: Score [0, 600] based on 6 patterns

sophisticated_score = (
    SMURFING * 100 +      # Many small transactions
    LAYERING * 100 +      # Multiple hops
    ROUND_TRIP * 100 +    # Circular transfers
    FAN_OUT * 100 +       # 1-to-many distribution
    FAN_IN * 100 +        # Many-to-1 collection
    RAPID_MOVEMENT * 100  # Quick fund movement
)
```

### Pattern Detection Formulas

| Pattern | Formula |
|---------|---------|
| **SMURFING** | `(tx_count > 10) AND (avg_value < 1000) AND (time_span < 24h)` |
| **LAYERING** | `(hop_count >= 3) AND (intermediaries >= 2)` |
| **ROUND_TRIP** | `(A→B→A pattern) AND (time < 48h)` |
| **FAN_OUT** | `(unique_receivers > 10) AND (similar_amounts)` |
| **FAN_IN** | `(unique_senders > 10) AND (single_receiver)` |
| **RAPID_MOVEMENT** | `(receive_to_send_time < 10 minutes)` |

### Hybrid Score
```python
# Combination of multiple scoring methods
hybrid_score = (
    0.4 * xgb_normalized +           # [0, 100]
    0.3 * sophisticated_normalized + # [0, 100]
    0.3 * graph_risk_normalized      # [0, 100]
)
# Output: [0, 100]
```

### Behavioral Ratios
```python
# In/Out Ratio
in_out_ratio = received_count / (sent_count + 1)

# Average Transaction Size
avg_sent = total_sent / (sent_count + 1)
avg_received = total_received / (received_count + 1)

# Counterparty Diversity
counterparty_ratio = unique_counterparties / total_transactions
```

### Graph Features
```python
# PageRank (importance in network)
pagerank = nx.pagerank(G)[address]

# Degree Centrality (connectivity)
degree_centrality = G.degree(address) / (len(G.nodes) - 1)

# Betweenness Centrality (bridge nodes)
betweenness = nx.betweenness_centrality(G)[address]

# Clustering Coefficient (local density)
clustering = nx.clustering(G, address)
```

### NEW Receiver Features (to catch 8%)
```python
# Sender-to-Receiver Transaction Ratio
sender_receiver_tx_ratio = sender_total_transactions / receiver_total_transactions

# Receiver is Hub (money mule detection)
receiver_is_hub = 1 if receiver_unique_counterparties > 100 else 0

# Account Age Ratio
account_age_ratio = sender_active_duration_mins / receiver_active_duration_mins

# Counterparty Ratio
counterparty_ratio = sender_unique_counterparties / receiver_unique_counterparties

# Receiver is Fraud (lookup)
receiver_is_fraud = 1 if to_address in fraud_addresses else 0
```

---

# 5. Labeling Methodology

## 5.1 Pseudo-Labeling Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PSEUDO-LABELING PIPELINE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  STEP 1: INITIAL XGB MODEL (Kaggle Data)                                     │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Kaggle Labeled Data → Train XGBoost → xgb_score [0, 1]                │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  STEP 2: APPLY TO BIGQUERY DATA                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  BigQuery Transactions → Feature Engineering → XGB Scoring              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  STEP 3: SOPHISTICATION SCORING                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Each Address → Detect 6 Patterns → sophisticated_score [0, 600]       │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  STEP 4: GRAPH RISK SCORING                                                  │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Transaction Graph → PageRank/Centrality → graph_risk [0, 100]         │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  STEP 5: HYBRID COMBINATION                                                  │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  hybrid_score = 0.4*XGB + 0.3*SOPHISTICATED + 0.3*GRAPH                │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  STEP 6: PSEUDO-LABEL ASSIGNMENT                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  fraud = 1 if:                                                          │ │
│  │    (hybrid_score > 70) OR                                               │ │
│  │    (sophisticated_score > 0 AND pattern_count >= 2) OR                  │ │
│  │    (address in known_fraud_list)                                        │ │
│  │  else:                                                                  │ │
│  │    fraud = 0                                                            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 5.2 Labeling Statistics

| Label | Count | Percentage |
|-------|-------|------------|
| Fraud (1) | 420,848 | 25.15% |
| Legitimate (0) | 1,252,396 | 74.85% |
| **Total** | **1,673,244** | **100%** |

---

# 6. Model Architecture

## 6.1 Ensemble Components

### BetaVAE (Variational Autoencoder)
```python
class BetaVAE:
    latent_dim = 64
    beta = 4.0
    encoder = [input → 256 → 128 → 64]
    decoder = [64 → 128 → 256 → output]
    
    # Loss function
    loss = reconstruction_loss + beta * KL_divergence
    
    # Output: 64 latent dimensions + reconstruction_error
```

### VGAE (Variational Graph Autoencoder)
```python
class VGAE:
    out_channels = 32
    # Learns graph structure reconstruction
```

### GATv2 (Graph Attention Network v2)
```python
class GATv2:
    hidden = 64
    heads = 4
    # Attention-based node embeddings
```

### GraphSAGE
```python
class GraphSAGE_Large:
    hidden = 128
    num_layers = 3
    # Neighborhood aggregation embeddings
```

### XGBoost
```python
XGBClassifier(
    n_estimators=1999,
    max_depth=6,
    learning_rate=0.1,
    subsample=0.8,
    colsample_bytree=0.8
)
# ROC-AUC: 0.9170
```

### LightGBM
```python
LGBMClassifier(
    n_estimators=2000,
    max_depth=6,
    learning_rate=0.1,
    num_leaves=31
)
# ROC-AUC: 0.9226 (BEST individual model)
```

### Meta-Learner
```python
LogisticRegression(C=1.0)
# Combines all model predictions
# Final ROC-AUC: 0.9229
```

## 6.2 Feature Flow

```
Input Features (5 tabular):
├── sender_total_transactions
├── sender_total_sent
├── sender_total_received
├── sender_sophisticated_score
└── sender_hybrid_score

+ VAE Features (65):
├── vae_z0 through vae_z63 (64 latent dimensions)
└── recon_err (reconstruction error)

+ Graph Features (1):
└── graphsage_score

= Total: 71 features → XGBoost/LightGBM → Meta-Learner
```

---

# 7. Training Pipeline

## 7.1 Data Split
```python
train_size = 0.7  # 70% training
val_size = 0.15   # 15% validation
test_size = 0.15  # 15% test
```

## 7.2 Training Process

```
Step 1: Train BetaVAE
    - Input: 5 tabular features
    - Output: 64 latent dimensions + recon_err
    - Time: ~30 minutes (GPU)

Step 2: Train Graph Models
    - Build transaction graph
    - Train VGAE, GATv2, GraphSAGE
    - Output: graphsage_score
    - Time: ~1 hour (GPU)

Step 3: Train Boosting Models
    - Combine all 71 features
    - Train XGBoost with Optuna tuning
    - Train LightGBM with Optuna tuning
    - Time: ~30 minutes (CPU)

Step 4: Train Meta-Learner
    - Stack predictions from all models
    - Train Logistic Regression
    - Find optimal threshold
    - Time: ~5 minutes
```

## 7.3 Hyperparameter Tuning

Used **Optuna** for automated hyperparameter search:
- 100 trials per model
- 5-fold cross-validation
- Optimizing for ROC-AUC

---

# 8. Evaluation Results

## 8.1 Model Performance Comparison

| Model | ROC-AUC | PR-AUC |
|-------|---------|--------|
| BetaVAE | 0.6891 | 0.5234 |
| VGAE | 0.7123 | 0.5567 |
| GATv2 | 0.6506 | 0.4891 |
| GraphSAGE | 0.8579 | 0.7234 |
| XGBoost | 0.9170 | 0.8456 |
| **LightGBM** | **0.9226** | **0.8589** |
| **Meta-Ensemble** | **0.9229** | **0.8609** |

## 8.2 Optimal Threshold

```python
optimal_threshold = 0.7270  # Maximizes F1-score

At this threshold:
- Recall: 92% (catches 92% of fraud)
- Precision: 88% (88% of flags are true fraud)
- F1-Score: 0.90
```

## 8.3 Confusion Matrix (Estimated)

```
                    Predicted
                 FRAUD    LEGITIMATE
Actual FRAUD    387,180     33,668  (8% missed)
Actual LEGIT     52,000  1,200,396
```

---

# 9. The 8% Problem

## 9.1 Why 8% of Fraud Slips Through

The ensemble misses approximately **33,668 fraud cases** (8%) because:

### Root Causes

| Cause | % of Missed | Description |
|-------|-------------|-------------|
| New/One-time Attackers | 35% | Only 4 transactions (vs 3,727 for caught fraud) |
| Normal Network Structure | 25% | Only 2 counterparties (similar to legitimate) |
| Appearing "Simple" | 25% | Zero sophistication score |
| Normal Value Ranges | 15% | Transaction values within normal range |

### Key Insight

**Hard fraud ≈ New legitimate user** - They are statistically indistinguishable from the sender's perspective.

## 9.2 The Solution: Receiver Features

The model was only using **sender features**. Adding **receiver features** can catch the 8%:

| Feature | Hard Fraud | Legitimate | Difference |
|---------|------------|------------|------------|
| `receiver_unique_counterparties` | 2,577 | 8 | **32,112%** |
| `receiver_total_transactions` | 6,910 | 69 | **9,915%** |
| `receiver_is_fraud` | 0.247 | 0.003 | **8,133%** |

### New Features Added

```python
# 15 new features to catch the 8%
new_features = [
    'receiver_total_transactions',
    'receiver_unique_counterparties',
    'receiver_sent_count',
    'receiver_received_count',
    'receiver_is_fraud',
    'sender_active_duration_mins',
    'receiver_active_duration_mins',
    'sender_receiver_tx_ratio',
    'receiver_is_hub',
    'account_age_ratio',
    'counterparty_ratio',
    'value_eth',
    'gas_price_gwei',
    'sender_pattern_count',
    'sender_in_out_ratio'
]
```

## 9.3 Expected Improvement

| Metric | Current | Expected with Receiver Features |
|--------|---------|--------------------------------|
| Overall Recall | 92% | **96-98%** |
| Hard Fraud Catch Rate | 0% | **60-80%** |
| False Positive Rate | ~12% | Similar |

---

# 10. Production Deployment

## 10.1 Inference Pipeline

```python
def predict_fraud(transaction):
    # Step 1: Feature engineering
    features = engineer_features(transaction)
    
    # Step 2: Get VAE latent representation
    vae_features = vae_model.encode(features)
    
    # Step 3: Get graph score
    graph_score = graphsage_model.predict(transaction)
    
    # Step 4: Combine all features
    all_features = np.concatenate([features, vae_features, graph_score])
    
    # Step 5: Get XGB and LGB predictions
    xgb_pred = xgb_model.predict_proba(all_features)[:, 1]
    lgb_pred = lgb_model.predict_proba(all_features)[:, 1]
    
    # Step 6: Meta-learner final prediction
    final_score = meta_learner.predict_proba([xgb_pred, lgb_pred])[:, 1]
    
    # Step 7: Classify risk level
    if final_score > 0.90:
        return "CRITICAL"
    elif final_score > 0.75:
        return "HIGH"
    elif final_score > 0.50:
        return "MEDIUM"
    else:
        return "LOW"
```

## 10.2 Latency Requirements

| Operation | Target | Actual |
|-----------|--------|--------|
| Feature Engineering | <100ms | ~50ms |
| Model Inference | <50ms | ~30ms |
| Total | <200ms | ~100ms |

---

# 11. Troubleshooting

## Common Issues

### 1. "No module named 'cuml'"
```bash
# Solution: Use CPU versions
pip install xgboost lightgbm scikit-learn
```

### 2. Memory Error on Large Dataset
```python
# Solution: Process in chunks
for chunk in pd.read_parquet(file, chunksize=100000):
    process(chunk)
```

### 3. GPU Out of Memory
```python
# Solution: Reduce batch size
batch_size = 256  # Instead of 1024
```

---

# 12. Quick Reference

## Key Commands

```bash
# Feature engineering
python scripts/feature_engineering.py --input data.parquet

# Train models
python scripts/train_ensemble.py --data processed/training_data.parquet

# Run inference
python scripts/predict.py --input new_transactions.parquet

# Load to Memgraph
python scripts/load_memgraph_fraud.py

# Generate report
python scripts/create_investor_report.py
```

## Key Files

| File | Purpose |
|------|---------|
| `processed/eth_transactions_full_labeled.parquet` | Main dataset |
| `processed/eth_transactions_with_receiver_features.parquet` | Enhanced dataset |
| `models/xgb_model.pkl` | Trained XGBoost |
| `models/lgb_model.pkl` | Trained LightGBM |
| `models/vae_model.pt` | Trained VAE |
| `models/meta_learner.pkl` | Final ensemble |

## Key Metrics

| Metric | Value |
|--------|-------|
| ROC-AUC | 0.9229 |
| PR-AUC | 0.8609 |
| Optimal Threshold | 0.7270 |
| Recall | 92% |
| Precision | 88% |
| Miss Rate | 8% |

---

# Appendix

## A. OFAC Sanctioned Addresses (Sample)

```
0x8589427373D6D84E98730D7795D8f6f8731FDA16 (Tornado Cash)
0x722122dF12D4e14e13Ac3b6895a86e84145b6967 (Tornado Cash)
0xd90e2f925DA726b50C4Ed8D0Fb90Ad053324F31b (Tornado Cash)
```

## B. Glossary

| Term | Definition |
|------|------------|
| **ROC-AUC** | Area Under Receiver Operating Characteristic Curve |
| **PR-AUC** | Area Under Precision-Recall Curve |
| **VAE** | Variational Autoencoder |
| **GNN** | Graph Neural Network |
| **Pseudo-labeling** | Using model predictions as training labels |
| **Meta-learner** | Model that combines other model predictions |

---

*Document generated: January 2, 2026*
