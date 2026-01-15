# AMTTP Complete File Mapping

## Every File in the Project with Purpose and Details

**Version:** 1.0  
**Last Updated:** January 2, 2026

---

# Table of Contents

1. [Project Structure Overview](#1-project-structure-overview)
2. [Data Collection Files](#2-data-collection-files)
3. [Feature Engineering Files](#3-feature-engineering-files)
4. [Labeling Pipeline Files](#4-labeling-pipeline-files)
5. [Model Training Files](#5-model-training-files)
6. [Evaluation Files](#6-evaluation-files)
7. [Deployment Files](#7-deployment-files)
8. [Model Artifacts](#8-model-artifacts)
9. [Data Files](#9-data-files)
10. [Report Files](#10-report-files)
11. [Configuration Files](#11-configuration-files)
12. [Documentation Files](#12-documentation-files)
13. [File Dependencies](#13-file-dependencies)
14. [Quick Reference](#14-quick-reference)

---

# 1. Project Structure Overview

```
C:\amttp\
│
├── automation/                    # Scheduled data fetching scripts
│   ├── bigquery_fetcher.py       # Downloads ETH transactions from BigQuery
│   ├── eth_data_fetcher.py       # Alternative data fetcher
│   ├── memgraph_ingest.py        # Loads data into Memgraph
│   ├── automation_cli.py         # CLI for automation tasks
│   └── requirements.txt          # Python dependencies
│
├── scripts/                       # Core pipeline scripts
│   ├── feature_engineering.py    # Creates 127 features
│   ├── add_receiver_features.py  # Adds 15 new receiver features
│   ├── train_ensemble.py         # Trains all 7 models
│   ├── evaluate_model.py         # Calculates metrics
│   ├── predict.py                # Runs inference
│   ├── investigate_8percent.py   # Analyzes missed fraud
│   ├── load_memgraph_fraud.py    # Loads to graph database
│   ├── node2vec_memgraph.py      # Generates graph embeddings
│   ├── ensemble_visualizations.py # Creates charts
│   └── create_investor_report.py # Generates HTML report
│
├── processed/                     # Processed datasets
│   ├── eth_transactions_full_labeled.parquet
│   ├── eth_transactions_with_receiver_features.parquet
│   └── node2vec_embeddings.npz
│
├── reports/                       # Generated visualizations
│   ├── AMTTP_Investor_Report.html
│   ├── 1_ensemble_architecture.png
│   ├── 2_feature_importance_ensemble.png
│   └── fraud_8percent_investigation.png
│
├── docs/                          # Documentation
│   ├── COMPLETE_SYSTEM_DOCUMENTATION.md
│   ├── COMPLETE_FILE_MAPPING.md
│   └── MODEL_DOCUMENTATION.md
│
├── contracts/                     # Solidity smart contracts
│   ├── AMTTPCore.sol
│   ├── AMTTPRouter.sol
│   └── AMTTPDisputeResolver.sol
│
└── config/                        # Configuration files
    └── feature_config.json
```

---

# 2. Data Collection Files

## 2.1 automation/bigquery_fetcher.py

**Purpose:** Downloads Ethereum transactions from Google BigQuery

**Key Functions:**
```python
def fetch_transactions(start_date, end_date):
    """
    Fetches ETH transactions from BigQuery public dataset
    
    Input: Date range (e.g., '2025-12-01' to '2025-12-20')
    Output: DataFrame with raw transactions
    """
    
def aggregate_address_features(transactions_df):
    """
    Aggregates transaction-level data to address-level features
    
    Input: Raw transactions DataFrame
    Output: Address features DataFrame with:
        - total_transactions
        - sent_count, received_count
        - total_sent, total_received
        - unique_counterparties
        - etc.
    """
```

**Input:** BigQuery credentials, date range  
**Output:** `processed/bigquery_transactions.parquet`

**Features Generated:**
- `tx_hash`, `block_number`, `block_timestamp`
- `from_address`, `to_address`
- `value_eth`, `gas_price_gwei`, `gas_used`

---

## 2.2 automation/eth_data_fetcher.py

**Purpose:** Alternative data fetcher using Etherscan API

**Key Functions:**
```python
def fetch_address_transactions(address, api_key):
    """Fetches all transactions for a specific address"""
    
def fetch_known_fraud_addresses():
    """Fetches list of known fraud/phishing addresses from Etherscan"""
```

**Input:** Etherscan API key  
**Output:** Transaction data, fraud labels

---

## 2.3 automation/memgraph_ingest.py

**Purpose:** Loads transaction data into Memgraph graph database

**Key Functions:**
```python
def create_address_nodes(addresses):
    """Creates Address nodes in Memgraph"""
    
def create_transaction_edges(transactions):
    """Creates SENT_TO relationships between addresses"""
    
def run_pagerank():
    """Runs PageRank algorithm on the graph"""
```

**Input:** Processed transaction data  
**Output:** Populated Memgraph database

---

# 3. Feature Engineering Files

## 3.1 scripts/feature_engineering.py

**Purpose:** Main feature engineering script - creates 127 features

**Key Functions:**
```python
def compute_basic_aggregations(df):
    """
    Creates basic count/sum features
    
    Output Features:
        - sender_total_transactions
        - sender_sent_count
        - sender_received_count
        - sender_total_sent
        - sender_total_received
        - sender_balance
        - receiver_* (same for receiver)
    """

def compute_temporal_features(df):
    """
    Creates time-based features
    
    Output Features:
        - sender_active_duration_mins
        - receiver_active_duration_mins
        - hour_of_day
        - day_of_week
        - is_weekend
    """

def compute_behavioral_ratios(df):
    """
    Creates normalized ratio features
    
    Output Features:
        - sender_in_out_ratio = received / (sent + 1)
        - sender_avg_sent = total_sent / (sent_count + 1)
        - sender_avg_received = total_received / (received_count + 1)
        - counterparty_diversity = unique / total
    """

def detect_sophistication_patterns(df):
    """
    Detects 6 money laundering patterns
    
    Patterns Detected:
        - SMURFING: Many small transactions
        - LAYERING: Multiple hops
        - ROUND_TRIP: Circular transfers
        - FAN_OUT: 1-to-many distribution
        - FAN_IN: Many-to-1 collection
        - RAPID_MOVEMENT: Quick fund movement
    
    Output Features:
        - sender_pattern_count
        - sender_sophisticated_score
        - sender_pattern_* (individual pattern flags)
    """

def compute_xgb_scores(df, model_path):
    """
    Applies pre-trained XGBoost model
    
    Output Features:
        - sender_xgb_raw_score
        - sender_xgb_normalized
        - receiver_xgb_raw_score
        - receiver_xgb_normalized
    """

def compute_hybrid_score(df):
    """
    Combines multiple scoring methods
    
    Formula:
        hybrid_score = 0.4 * xgb_normalized + 
                       0.3 * sophisticated_normalized + 
                       0.3 * graph_risk_normalized
    
    Output Features:
        - sender_hybrid_score
        - receiver_hybrid_score
        - max_hybrid_score
    """
```

**Input:** Raw transaction data  
**Output:** `processed/eth_transactions_full_labeled.parquet`

---

## 3.2 scripts/add_receiver_features.py

**Purpose:** Adds 15 new receiver-side features to catch the 8% missed fraud

**Key Functions:**
```python
def add_receiver_activity_features(df):
    """
    Adds receiver activity features
    
    Output Features:
        - receiver_total_transactions
        - receiver_unique_counterparties
        - receiver_sent_count
        - receiver_received_count
    """

def add_derived_ratios(df):
    """
    Creates ratio features between sender and receiver
    
    Output Features:
        - sender_receiver_tx_ratio = sender_txs / receiver_txs
        - receiver_is_hub = 1 if counterparties > 100
        - account_age_ratio = sender_duration / receiver_duration
        - counterparty_ratio = sender_counterparties / receiver_counterparties
    """

def add_receiver_fraud_flag(df, fraud_addresses):
    """
    Flags transactions to known fraud receivers
    
    Output Features:
        - receiver_is_fraud
    """
```

**Input:** `processed/eth_transactions_full_labeled.parquet`  
**Output:** `processed/eth_transactions_with_receiver_features.parquet`

**New Features Added (15):**
1. `receiver_total_transactions`
2. `receiver_unique_counterparties`
3. `receiver_sent_count`
4. `receiver_received_count`
5. `receiver_is_fraud`
6. `sender_active_duration_mins`
7. `receiver_active_duration_mins`
8. `sender_receiver_tx_ratio`
9. `receiver_is_hub`
10. `account_age_ratio`
11. `counterparty_ratio`
12. `value_eth`
13. `gas_price_gwei`
14. `sender_pattern_count`
15. `sender_in_out_ratio`

---

# 4. Labeling Pipeline Files

## 4.1 scripts/label_transactions.py

**Purpose:** Creates pseudo-labels for training data

**Key Functions:**
```python
def apply_xgb_labels(df, threshold=0.7):
    """
    Labels based on XGB model predictions
    
    Rule: fraud = 1 if xgb_score > threshold
    """

def apply_sophistication_labels(df):
    """
    Labels based on pattern detection
    
    Rule: fraud = 1 if sophisticated_score > 0 AND pattern_count >= 2
    """

def apply_known_fraud_labels(df, fraud_list):
    """
    Labels based on known fraud addresses
    
    Rule: fraud = 1 if address in fraud_list
    """

def combine_labels(df):
    """
    Combines all labeling methods
    
    Final Rule:
        fraud = 1 if (xgb_fraud OR sophisticated_fraud OR known_fraud)
        fraud = 0 otherwise
    """
```

**Input:** Feature-engineered data  
**Output:** Labeled dataset with `fraud` column

---

# 5. Model Training Files

## 5.1 scripts/train_ensemble.py

**Purpose:** Main training script for the full ensemble

**Key Functions:**
```python
def train_vae(X_train):
    """
    Trains BetaVAE for latent feature extraction
    
    Architecture:
        - Encoder: input → 256 → 128 → 64 (latent)
        - Decoder: 64 → 128 → 256 → output
        - Beta: 4.0
    
    Output: 64 latent dimensions + reconstruction error
    """

def train_graph_models(graph, node_features):
    """
    Trains graph neural networks
    
    Models:
        - VGAE (32 dimensions)
        - GATv2 (64 dimensions, 4 heads)
        - GraphSAGE (128 dimensions, 3 layers)
    
    Output: graphsage_score for each node
    """

def train_xgboost(X_train, y_train):
    """
    Trains XGBoost with Optuna hyperparameter tuning
    
    Features: 71 (5 tabular + 64 VAE + 1 graph + recon_err)
    Output: Trained XGBClassifier
    """

def train_lightgbm(X_train, y_train):
    """
    Trains LightGBM with Optuna hyperparameter tuning
    
    Features: 71 (same as XGBoost)
    Output: Trained LGBMClassifier
    """

def train_meta_learner(predictions, y_train):
    """
    Trains meta-learner to combine predictions
    
    Input: Stacked predictions from all models
    Output: LogisticRegression meta-learner
    """

def find_optimal_threshold(y_true, y_pred):
    """
    Finds threshold that maximizes F1-score
    
    Output: optimal_threshold (e.g., 0.7270)
    """
```

**Input:** Labeled training data  
**Output:** All trained models in `models/` directory

---

## 5.2 scripts/train_vae.py

**Purpose:** Dedicated VAE training script

**Key Classes:**
```python
class BetaVAE(nn.Module):
    def __init__(self, input_dim, latent_dim=64, beta=4.0):
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 128),
            nn.ReLU()
        )
        self.fc_mu = nn.Linear(128, latent_dim)
        self.fc_var = nn.Linear(128, latent_dim)
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 256),
            nn.ReLU(),
            nn.Linear(256, input_dim)
        )
    
    def reparameterize(self, mu, log_var):
        std = torch.exp(0.5 * log_var)
        eps = torch.randn_like(std)
        return mu + eps * std
    
    def forward(self, x):
        h = self.encoder(x)
        mu, log_var = self.fc_mu(h), self.fc_var(h)
        z = self.reparameterize(mu, log_var)
        recon = self.decoder(z)
        return recon, mu, log_var, z
```

**Output:** `models/vae_model.pt`

---

# 6. Evaluation Files

## 6.1 scripts/evaluate_model.py

**Purpose:** Calculates and reports model performance metrics

**Key Functions:**
```python
def calculate_metrics(y_true, y_pred, y_proba):
    """
    Calculates all evaluation metrics
    
    Metrics:
        - ROC-AUC
        - PR-AUC
        - Precision, Recall, F1
        - Confusion Matrix
    """

def plot_roc_curve(y_true, y_proba):
    """Generates ROC curve visualization"""

def plot_precision_recall_curve(y_true, y_proba):
    """Generates PR curve visualization"""

def generate_classification_report(y_true, y_pred):
    """Generates detailed classification report"""
```

**Input:** True labels, predictions  
**Output:** Metrics report, visualizations

---

## 6.2 scripts/investigate_8percent.py

**Purpose:** Analyzes why 8% of fraud cases slip through

**Key Functions:**
```python
def identify_hard_fraud(df, predictions):
    """
    Finds fraud cases that the model misses
    
    Definition: hard_fraud = (fraud == 1) AND (predicted == 0)
    """

def compare_features(easy_fraud, hard_fraud, legitimate):
    """
    Compares feature distributions between groups
    
    Output: Feature comparison table
    """

def identify_root_causes():
    """
    Determines why fraud is missed
    
    Findings:
        1. New/one-time attackers (35%)
        2. Normal network structure (25%)
        3. Appearing simple (25%)
        4. Normal value ranges (15%)
    """

def recommend_solutions():
    """
    Recommends features to catch missed fraud
    
    Recommendations:
        - Add receiver features
        - Add temporal features
        - Lower threshold for high-value transactions
    """
```

**Input:** Labeled data, model predictions  
**Output:** Investigation report, visualizations

---

## 6.3 scripts/individual_model_analysis.py

**Purpose:** Checks if any individual model can catch the 8%

**Output:** Analysis showing no individual model can catch hard fraud alone

---

# 7. Deployment Files

## 7.1 scripts/predict.py

**Purpose:** Runs inference on new transactions

**Key Functions:**
```python
def load_models():
    """Loads all trained model artifacts"""

def preprocess_transaction(tx):
    """Engineers features for a single transaction"""

def predict_single(tx, models):
    """
    Predicts fraud probability for one transaction
    
    Returns: score [0, 1], risk_level (CRITICAL/HIGH/MEDIUM/LOW)
    """

def predict_batch(transactions, models):
    """Batch prediction for multiple transactions"""
```

**Input:** New transaction data  
**Output:** Fraud predictions with risk levels

---

## 7.2 scripts/load_memgraph_fraud.py

**Purpose:** Loads fraud data into Memgraph graph database

**Key Functions:**
```python
def connect_memgraph():
    """Establishes connection to Memgraph"""

def create_address_nodes(addresses, labels):
    """
    Creates Address nodes with properties:
        - address (string)
        - is_fraud (boolean)
        - risk_score (float)
    """

def create_transaction_edges(transactions):
    """
    Creates SENT_TO relationships with properties:
        - tx_hash
        - value_eth
        - timestamp
    """
```

**Input:** Labeled transaction data  
**Output:** Populated Memgraph database

---

## 7.3 scripts/node2vec_memgraph.py

**Purpose:** Generates Node2Vec graph embeddings from Memgraph

**Key Functions:**
```python
def run_node2vec(dimensions=64, walk_length=80, num_walks=10):
    """
    Runs Node2Vec algorithm on transaction graph
    
    Output: Embeddings for each address
    """

def cluster_embeddings(embeddings, n_clusters=10):
    """
    Clusters addresses using DBSCAN
    
    Output: Cluster assignments
    """
```

**Input:** Memgraph database  
**Output:** `processed/node2vec_embeddings.npz`

---

# 8. Model Artifacts

## Location: `C:\Users\Administrator\Downloads\amttp_models_20251231_174617\`

| File | Size | Description |
|------|------|-------------|
| `xgboost_fraud.ubj` | 8.5 MB | Trained XGBoost model |
| `lightgbm_fraud.txt` | 13.5 MB | Trained LightGBM model |
| `beta_vae.pt` | 2.1 MB | BetaVAE encoder/decoder |
| `vgae.pt` | 0.8 MB | Variational Graph Autoencoder |
| `gatv2.pt` | 1.2 MB | Graph Attention Network |
| `graphsage_large.pt` | 3.4 MB | GraphSAGE model |
| `meta_ensemble.joblib` | 0.1 MB | Meta-learner |
| `preprocessors.joblib` | 0.5 MB | Scalers and encoders |
| `metadata.json` | 2 KB | Model configuration |
| `feature_config.json` | 3 KB | Feature definitions |
| `inference.py` | 5 KB | Inference code |

## feature_config.json Contents:
```json
{
  "tabular_features": [
    "sender_total_transactions",
    "sender_total_sent",
    "sender_total_received",
    "sender_sophisticated_score",
    "sender_hybrid_score"
  ],
  "boost_features": [
    "sender_total_transactions",
    "sender_total_sent",
    "sender_total_received",
    "sender_sophisticated_score",
    "sender_hybrid_score",
    "vae_z0", "vae_z1", ... "vae_z63",
    "recon_err",
    "graphsage_score"
  ],
  "label_column": "fraud"
}
```

---

# 9. Data Files

## Location: `C:\amttp\processed\`

| File | Size | Records | Description |
|------|------|---------|-------------|
| `eth_transactions_full_labeled.parquet` | 450 MB | 1,673,244 | Main dataset with 69 columns |
| `eth_transactions_with_receiver_features.parquet` | 520 MB | 1,673,244 | Enhanced with 15 new features |
| `node2vec_embeddings.npz` | 45 MB | 58,352 | Graph embeddings |

## Column List (69 columns):
```
tx_hash, block_number, block_timestamp, from_address, to_address,
value_eth, gas_price_gwei, gas_used, gas_limit, transaction_type, nonce,
sender_sent_count, sender_received_count, sender_total_transactions,
sender_total_sent, sender_total_received, sender_balance,
sender_avg_sent, sender_avg_received, sender_max_sent, sender_max_received,
sender_unique_receivers, sender_unique_senders, sender_unique_counterparties,
sender_in_out_ratio, sender_active_duration_mins, sender_sophisticated_score,
sender_pattern_count, sender_xgb_raw_score, sender_xgb_normalized,
sender_pattern_boost, sender_soph_normalized, sender_hybrid_score,
sender_risk_level, sender_fraud, sender_risk_class,
receiver_* (same features for receiver),
fraud, risk_class, max_hybrid_score, from_idx, to_idx
```

---

# 10. Report Files

## Location: `C:\amttp\reports\`

| File | Description |
|------|-------------|
| `AMTTP_Investor_Report.html` | Interactive HTML report for investors |
| `1_ensemble_architecture.png` | Model architecture diagram |
| `2_feature_importance_ensemble.png` | Feature importance chart |
| `3_model_comparison.png` | Model performance comparison |
| `4_investor_dashboard_ensemble.png` | Key metrics dashboard |
| `5_explainability_ensemble.png` | How ensemble makes decisions |
| `fraud_8percent_investigation.png` | Analysis of missed fraud |
| `individual_models_analysis.png` | Individual model capabilities |
| `missed_fraud_investigation.png` | Deep dive into missed cases |

---

# 11. Configuration Files

## 11.1 feature_config.json

**Location:** Model artifacts folder  
**Purpose:** Defines which features are used by each model component

## 11.2 automation/config.yaml

**Purpose:** Configuration for data fetching automation
```yaml
bigquery:
  project_id: "your-project"
  dataset: "crypto_ethereum"
  
etherscan:
  api_key: "YOUR_API_KEY"
  
memgraph:
  host: "localhost"
  port: 7687
```

---

# 12. Documentation Files

## Location: `C:\amttp\docs\`

| File | Description |
|------|-------------|
| `COMPLETE_SYSTEM_DOCUMENTATION.md` | Master technical reference |
| `COMPLETE_FILE_MAPPING.md` | This file - maps all project files |
| `MODEL_DOCUMENTATION.md` | Model-specific documentation |
| `AUDIT_PACKAGE.md` | Audit and compliance guide |
| `SECURITY_REQUIREMENTS.md` | Security specifications |
| `VERIFICATION_GUIDE.md` | Testing and verification guide |

---

# 13. File Dependencies

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FILE DEPENDENCY GRAPH                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  DATA COLLECTION                                                             │
│  automation/bigquery_fetcher.py                                              │
│         │                                                                    │
│         ▼                                                                    │
│  FEATURE ENGINEERING                                                         │
│  scripts/feature_engineering.py                                              │
│         │                                                                    │
│         ├──────────────────────────────────┐                                 │
│         ▼                                  ▼                                 │
│  scripts/sophistication_detector.py   scripts/graph_features.py             │
│         │                                  │                                 │
│         └──────────────┬───────────────────┘                                 │
│                        ▼                                                     │
│  LABELING                                                                    │
│  scripts/label_transactions.py                                               │
│         │                                                                    │
│         ▼                                                                    │
│  OUTPUT: processed/eth_transactions_full_labeled.parquet                     │
│         │                                                                    │
│         ▼                                                                    │
│  MODEL TRAINING                                                              │
│  scripts/train_ensemble.py                                                   │
│         │                                                                    │
│         ├───────────┬───────────┬───────────┐                               │
│         ▼           ▼           ▼           ▼                               │
│  train_vae.py  train_graph.py  xgboost   lightgbm                           │
│         │           │           │           │                               │
│         └───────────┴───────────┴───────────┘                               │
│                        │                                                     │
│                        ▼                                                     │
│  META-LEARNER TRAINING                                                       │
│         │                                                                    │
│         ▼                                                                    │
│  OUTPUT: models/*.pkl, models/*.pt                                           │
│         │                                                                    │
│         ▼                                                                    │
│  EVALUATION                                                                  │
│  scripts/evaluate_model.py                                                   │
│  scripts/investigate_8percent.py                                             │
│         │                                                                    │
│         ▼                                                                    │
│  ENHANCEMENT                                                                 │
│  scripts/add_receiver_features.py                                            │
│         │                                                                    │
│         ▼                                                                    │
│  OUTPUT: processed/eth_transactions_with_receiver_features.parquet           │
│         │                                                                    │
│         ▼                                                                    │
│  DEPLOYMENT                                                                  │
│  scripts/predict.py                                                          │
│  scripts/load_memgraph_fraud.py                                              │
│         │                                                                    │
│         ▼                                                                    │
│  REPORTING                                                                   │
│  scripts/create_investor_report.py                                           │
│  scripts/ensemble_visualizations.py                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# 14. Quick Reference

## Run Full Pipeline

```bash
# Step 1: Fetch data
python automation/bigquery_fetcher.py --start 2025-12-01 --end 2025-12-20

# Step 2: Engineer features
python scripts/feature_engineering.py --input raw_data.parquet

# Step 3: Train models
python scripts/train_ensemble.py --data processed/eth_transactions_full_labeled.parquet

# Step 4: Evaluate
python scripts/evaluate_model.py --model models/meta_ensemble.joblib

# Step 5: Add receiver features (optional - for catching 8%)
python scripts/add_receiver_features.py

# Step 6: Deploy to Memgraph
python scripts/load_memgraph_fraud.py

# Step 7: Generate reports
python scripts/create_investor_report.py
```

## Key Model Metrics

| Model | ROC-AUC | File |
|-------|---------|------|
| XGBoost | 0.9170 | `xgboost_fraud.ubj` |
| LightGBM | 0.9226 | `lightgbm_fraud.txt` |
| Meta-Ensemble | 0.9229 | `meta_ensemble.joblib` |

## Key Data Files

| Purpose | File |
|---------|------|
| Main dataset | `processed/eth_transactions_full_labeled.parquet` |
| Enhanced dataset | `processed/eth_transactions_with_receiver_features.parquet` |
| Graph embeddings | `processed/node2vec_embeddings.npz` |

---

*Document generated: January 2, 2026*
