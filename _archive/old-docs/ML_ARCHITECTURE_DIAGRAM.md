# AMTTP Machine Learning Model Architecture

## 🧠 **Complete ML Architecture Overview**

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         AMTTP SOTA ENSEMBLE ARCHITECTURE                        │
└─────────────────────────────────────────────────────────────────────────────────┘

                                    INPUT LAYER
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            Raw Transaction Data                                 │
├─────────────────┬─────────────────┬─────────────────┬─────────────────────────┤
│   Transaction   │   Address       │   Temporal      │      Compliance         │
│   Features      │   Graph         │   Sequences     │      Features           │
│                 │                 │                 │                         │
│ • amount_eth    │ • sender        │ • tx_history    │ • sanctions_flag        │
│ • gas_price     │ • receiver      │ • time_series   │ • kyc_tier             │
│ • token_addr    │ • relationships │ • patterns      │ • country_risk         │
│ • velocity_*    │ • neighbors     │ • frequencies   │ • wallet_age           │
└─────────────────┴─────────────────┴─────────────────┴─────────────────────────┘
          │                  │                  │                  │
          ▼                  ▼                  ▼                  ▼

                              FEATURE ENGINEERING LAYER
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          Advanced Feature Engineering                           │
├─────────────────┬─────────────────┬─────────────────┬─────────────────────────┤
│  Tabular Eng.  │   Graph Eng.    │ Sequence Eng.   │   Composite Eng.        │
│                 │                 │                 │                         │
│ • amount_log    │ • node_features │ • embeddings    │ • risk_interactions     │
│ • amount_zscore │ • edge_weights  │ • sequences     │ • cross_features        │
│ • percentiles   │ • graph_metrics │ • tokenization  │ • statistical_aggs      │
│ • interactions  │ • centrality    │ • attention     │ • domain_knowledge      │
└─────────────────┴─────────────────┴─────────────────┴─────────────────────────┘
          │                  │                  │                  │
          ▼                  ▼                  ▼                  ▼

                                 MODEL LAYER (ENSEMBLE)
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            4-Model Ensemble Architecture                        │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   MODEL 1:      │  │   MODEL 2:      │  │   MODEL 3:      │  │   MODEL 4:      │
│    TABNET       │  │  GRAPHSAGE      │  │ TRANSFORMER     │  │   LIGHTGBM      │
│                 │  │                 │  │                 │  │                 │
│ ┌─────────────┐ │  │ ┌─────────────┐ │  │ ┌─────────────┐ │  │ ┌─────────────┐ │
│ │ Attention   │ │  │ │ Graph Conv  │ │  │ │ Multi-Head  │ │  │ │ Gradient    │ │
│ │ Mechanism   │ │  │ │ Layers      │ │  │ │ Attention   │ │  │ │ Boosting    │ │
│ │             │ │  │ │             │ │  │ │             │ │  │ │             │ │
│ │ n_d: 64     │ │  │ │ Hidden:128  │ │  │ │ Embed:128   │ │  │ │ Trees:1000  │ │
│ │ n_a: 64     │ │  │ │ Layers: 3   │ │  │ │ Heads: 8    │ │  │ │ Leaves: 31  │ │
│ │ n_steps: 5  │ │  │ │ Dropout:0.2 │ │  │ │ Layers: 4   │ │  │ │ LR: 0.05    │ │
│ │             │ │  │ │             │ │  │ │             │ │  │ │             │ │
│ │ ┌─────────┐ │ │  │ │ ┌─────────┐ │ │  │ │ ┌─────────┐ │ │  │ │ ┌─────────┐ │ │
│ │ │Decision │ │ │  │ │ │Global   │ │ │  │ │ │Sequence │ │ │  │ │ │Feature  │ │ │
│ │ │Layers   │ │ │  │ │ │Pooling  │ │ │  │ │ │Pooling  │ │ │  │ │ │Selection│ │ │
│ │ └─────────┘ │ │  │ │ └─────────┘ │ │  │ │ └─────────┘ │ │  │ │ └─────────┘ │ │
│ │             │ │  │ │             │ │  │ │             │ │  │ │             │ │
│ │ OUTPUT:     │ │  │ │ OUTPUT:     │ │  │ │ OUTPUT:     │ │  │ │ OUTPUT:     │ │
│ │ 92% Acc     │ │  │ │ 89% Acc     │ │  │ │ 91% Acc     │ │  │ │ 93% Acc     │ │
│ │ Tabular     │ │  │ │ Graph       │ │  │ │ Behavioral  │ │  │ │ Baseline    │ │
│ │ Expert      │ │  │ │ Analysis    │ │  │ │ Patterns    │ │  │ │ Fast        │ │
│ └─────────────┘ │  │ └─────────────┘ │  │ └─────────────┘ │  │ └─────────────┘ │
└─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘
          │                    │                    │                    │
          ▼                    ▼                    ▼                    ▼
      Score: 0.87           Score: 0.91          Score: 0.84         Score: 0.89

                                       │
                                       ▼
                              ENSEMBLE BLENDING LAYER
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Meta-Learning Blender                                 │
│                                                                                 │
│    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                      │
│    │   Input:    │    │ Blender     │    │   Output:   │                      │
│    │             │    │ Algorithm   │    │             │                      │
│    │ TabNet:0.87 │───▶│             │───▶│ Final Risk  │                      │
│    │ Graph: 0.91 │    │ Logistic    │    │ Score: 0.88 │                      │
│    │ Trans: 0.84 │    │ Regression  │    │             │                      │
│    │ LightGBM:0.89│   │     OR      │    │ Confidence: │                      │
│    │             │    │ Random      │    │ 0.94        │                      │
│    │ + Meta      │    │ Forest      │    │             │                      │
│    │ Features    │    │             │    │ Risk Level: │                      │
│    │             │    │ Weight      │    │ HIGH (3)    │                      │
│    └─────────────┘    │ Learning    │    └─────────────┘                      │
│                       └─────────────┘                                         │
│                                                                                │
│ Performance Target: 95%+ Accuracy, 0.975+ AUC                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                              CRYPTOGRAPHIC LAYER
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          ECDSA Signature & Verification                         │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                      Signature Generation                               │   │
│  │                                                                         │   │
│  │  hash = keccak256(risk_score, timestamp, transaction_id)              │   │
│  │  signature = sign(hash, oracle_private_key)                           │   │
│  │  oracle_address = recover_address(signature)                          │   │
│  │                                                                         │   │
│  │  On-chain Verification:                                                │   │
│  │  require(oracle_address == authorized_oracle)                         │   │
│  │                                                                         │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                                 OUTPUT LAYER
┌─────────────────────────────────────────────────────────────────────────────────┐
│                             Final Risk Assessment                               │
│                                                                                 │
│  {                                                                              │
│    "risk_score": 0.88,              // Probability (0-1)                      │
│    "risk_level": 3,                 // Level (1=Low, 2=Med, 3=High)           │
│    "confidence": 0.94,              // Model confidence                        │
│    "individual_scores": {           // Individual model outputs                │
│      "tabnet": 0.87,                                                           │
│      "graphsage": 0.91,                                                        │
│      "transformer": 0.84,                                                      │
│      "lightgbm": 0.89                                                          │
│    },                                                                          │
│    "explanations": [                // Human-readable reasons                  │
│      "High transaction amount",                                                │
│      "Unusual velocity pattern",                                               │
│      "New account risk"                                                        │
│    ],                                                                          │
│    "shap_values": {...},            // Explainable AI                         │
│    "signature": "0x...",            // ECDSA signature                        │
│    "latency_ms": 234                // Processing time                         │
│  }                                                                             │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## 🔧 **Detailed Model Architectures**

### **1. TabNet Model (Deep Tabular Learning)**
```
Input: [amount, velocity, age, risk_factors, ...]  (20+ features)
│
├─ Embedding Layer (Categorical features)
├─ Feature Transformer
│  ├─ Attention Mask Generation
│  ├─ Feature Selection (n_d=64)
│  └─ Decision Steps (n_steps=5)
│
├─ Attention Mechanism
│  ├─ Attentive Transformer (n_a=64)
│  ├─ Sparse Feature Selection
│  └─ Feature Reusability (gamma=1.5)
│
├─ Decision Network
│  ├─ ReLU Activation
│  ├─ Normalization
│  └─ Aggregation
│
└─ Output: Risk Probability (0-1)

Target Performance: 92%+ Accuracy
Training: Google Colab Pro (2-3 hours)
```

### **2. GraphSAGE Model (Graph Neural Network)**
```
Input: Address Graph [nodes, edges, features]
│
├─ Node Feature Initialization (64 features)
│  ├─ Address age, transaction count
│  ├─ Velocity metrics, amounts
│  └─ Risk indicators
│
├─ GraphSAGE Layers (3 layers)
│  ├─ Layer 1: 64 → 128 (neighbor aggregation)
│  ├─ Layer 2: 128 → 128 (feature propagation)
│  └─ Layer 3: 128 → 128 (final representation)
│
├─ Graph-Level Pooling
│  ├─ Global Mean Pooling
│  └─ Attention Pooling (optional)
│
├─ Classification Head
│  ├─ Linear: 128 → 64
│  ├─ ReLU + Dropout(0.2)
│  └─ Linear: 64 → 1
│
└─ Output: Graph Risk Score (0-1)

Target Performance: 89%+ Accuracy
Specialization: Money laundering, address clustering
```

### **3. Behavioral Transformer (Sequence Analysis)**
```
Input: Transaction Sequence [tx1, tx2, tx3, ...]
│
├─ Tokenization & Embedding
│  ├─ Transaction → Token (vocab_size=1000)
│  ├─ Embedding Layer (128-dim)
│  └─ Positional Encoding (200 max sequence)
│
├─ Multi-Head Attention (8 heads)
│  ├─ Query/Key/Value Projection
│  ├─ Scaled Dot-Product Attention
│  └─ Multi-Head Concatenation
│
├─ Transformer Encoder (4 layers)
│  ├─ Self-Attention Mechanism
│  ├─ Feed-Forward Network (512-dim)
│  ├─ Residual Connections
│  └─ Layer Normalization
│
├─ Sequence Pooling
│  ├─ Average Pooling (temporal aggregation)
│  └─ Attention Pooling (weighted)
│
├─ Classification Head
│  ├─ Linear: 128 → 64
│  ├─ ReLU Activation
│  └─ Linear: 64 → 1
│
└─ Output: Behavioral Risk Score (0-1)

Target Performance: 91%+ Accuracy  
Specialization: Temporal patterns, behavioral anomalies
```

### **4. LightGBM Model (Gradient Boosting)**
```
Input: Engineered Tabular Features
│
├─ Feature Engineering
│  ├─ Statistical aggregations
│  ├─ Interaction features
│  └─ Domain-specific features
│
├─ Gradient Boosting Trees
│  ├─ num_leaves: 31
│  ├─ learning_rate: 0.05
│  ├─ n_estimators: 1000
│  └─ Early stopping
│
├─ Feature Selection
│  ├─ Feature importance ranking
│  ├─ SHAP value calculation
│  └─ Recursive elimination
│
└─ Output: Tree-based Risk Score (0-1)

Target Performance: 93%+ Accuracy
Specialization: Fast inference, feature importance
```

## 🎯 **Ensemble Integration Strategy**

### **Meta-Learning Approach**
```python
# Individual model outputs become features for meta-model
ensemble_features = [
    tabnet_score,      # 0.87
    graphsage_score,   # 0.91  
    transformer_score, # 0.84
    lightgbm_score,    # 0.89
    # Plus original key features
    amount_percentile, # 0.95
    velocity_ratio,    # 2.3
    account_age_risk,  # 0.6
    country_risk,      # 0.3
    sanctions_flag     # 0 or 1
]

# Meta-model (Logistic Regression or Random Forest)
final_score = blender_model.predict_proba(ensemble_features)[1]
confidence = calculate_confidence(ensemble_features, final_score)
```

### **Weight Learning**
```python
# Adaptive weights based on model performance
weights = {
    'tabnet': 0.30,      # Strong on general patterns
    'graphsage': 0.25,   # Expert on address analysis  
    'transformer': 0.20, # Behavioral specialist
    'lightgbm': 0.25     # Fast and reliable baseline
}

# Weighted ensemble (fallback if meta-model unavailable)
weighted_score = sum(score * weight for score, weight in zip(scores, weights))
```

## 📊 **Performance Characteristics**

| Component | Latency | Accuracy | Specialization |
|-----------|---------|----------|----------------|
| **TabNet** | 15ms | 92%+ | Tabular feature expertise |
| **GraphSAGE** | 45ms | 89%+ | Address relationship analysis |
| **Transformer** | 32ms | 91%+ | Behavioral pattern detection |  
| **LightGBM** | 8ms | 93%+ | Fast baseline + explanations |
| **Ensemble** | **<250ms** | **95%+** | **Combined intelligence** |

## 🔄 **Training & Deployment Flow**

```
1. Data Collection (100K+ transactions)
2. Feature Engineering (20+ engineered features)  
3. Individual Model Training (Google Colab Pro)
4. Model Validation & Testing
5. Ensemble Training (Meta-learning)
6. Model Packaging & Versioning
7. Hot-Swap Deployment
8. Performance Monitoring
9. Continuous Retraining
```

This architecture represents **state-of-the-art fraud detection** combining multiple AI paradigms for maximum accuracy and robustness! 🚀