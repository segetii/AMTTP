# AMTTP Fraud Detection — Data Labeling Pipeline

## Quick Start

```bash
# Default: run pattern detection + build labeled dataset (Steps 1+2)
python pipeline/run_pipeline.py

# Full pipeline from scratch
python pipeline/run_pipeline.py --steps 0,1,2

# List all steps
python pipeline/run_pipeline.py --list

# Dry run (show what would execute)
python pipeline/run_pipeline.py --steps 0,1,2,3,4,5 --dry-run
```

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AMTTP DATA LABELING PIPELINE                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐                                                    │
│  │  STEP 0     │  Data Acquisition                                  │
│  │  (optional) │  Etherscan API / BigQuery                          │
│  └──────┬──────┘                                                    │
│         │                                                           │
│         ▼                                                           │
│  ┌──────────────────────────────────┐                               │
│  │  eth_merged_dataset.parquet      │  1.67M txs · 625K addresses   │
│  └──────┬───────────────────────────┘                               │
│         │                                                           │
│         ▼                                                           │
│  ┌─────────────┐  7 patterns (Polars ultra)                         │
│  │  STEP 1     │  SMURFING · LAYERING · FAN_OUT · FAN_IN            │
│  │  Pattern +  │  PEELING · STRUCTURING · VELOCITY                  │
│  │  XGB Score  │  + XGB cross-validation (sigmoid-calibrated)       │
│  └──────┬──────┘  + PR-curve threshold optimization                 │
│         │                                                           │
│         ├──► sophisticated_fraud_patterns.csv     (14K addrs)       │
│         ├──► sophisticated_xgb_combined.csv       (hybrid scores)   │
│         └──► xgb_high_risk_addresses.csv          (600+ addrs)      │
│         │                                                           │
│         ▼                                                           │
│  ┌─────────────┐  Merge ultra output + full XGB + graph props       │
│  │  STEP 2     │  → Hybrid score (40% XGB + 30% rules + 30% graph) │
│  │  Build      │  → Multi-signal bonus (1.2× two, 1.5× three)      │
│  │  Labeled    │  → Cross-check: XGB vs Rules vs Graph              │
│  │  Dataset    │  → PR-curve → risk_level → fraud label             │
│  └──────┬──────┘                                                    │
│         │                                                           │
│         └──► eth_addresses_labeled_v2.parquet  ★ FINAL OUTPUT       │
│             625K addrs · 80 cols · fraud/risk_level                 │
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │  STEP 3     │  │  STEP 4     │  │  STEP 5     │                 │
│  │  30d Relabel│  │  GAT/GNN    │  │  Validation  │                │
│  │  (drift)    │  │  Dataset    │  │  & Eval      │                │
│  └─────────────┘  └─────────────┘  └─────────────┘                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Step-by-Step Reference

### Step 0 — Data Acquisition *(optional)*

| | |
|---|---|
| **Script** | `step0_fetch_etherscan.py` / `step0_fetch_bigquery.py` |
| **Source** | Original: `automation/eth_data_fetcher.py` / `automation/bigquery_fetcher.py` |
| **Input** | `ETHERSCAN_API_KEY` env var; or GCP credentials |
| **Output** | `eth_merged_dataset.parquet` (1,673,244 txs) |
| **Notes** | Skipped automatically if parquet already exists |

### Step 1 — Pattern Detection + XGB Cross-Validation

| | |
|---|---|
| **Script** | `step1_pattern_detection.py` |
| **Source** | `scripts/sophisticated_fraud_detection_ultra.py` |
| **Input** | `eth_merged_dataset.parquet`; XGB model (`ml/Automation/ml_pipeline/models/trained/xgb.json`); feature schema |
| **Output** | `processed/sophisticated_fraud_patterns.csv` (14K flagged addrs); `processed/sophisticated_xgb_combined.csv`; `processed/xgb_high_risk_addresses.csv` |
| **Runtime** | ~67 seconds |

**Pattern detectors:**

| Pattern | What It Detects | Retention Strategy |
|---|---|---|
| SMURFING | Many small txs below threshold to multiple receivers | Above-median score (≥ p50 of qualifiers) |
| LAYERING | Pass-through addresses (recv ≈ sent) | Above-median, capped at 5000 |
| FAN_OUT | One sender → many unique receivers | Above-median score |
| FAN_IN | Many unique senders → one receiver | Above-median score |
| PEELING | Decreasing tx values (peeling chain) | Above-median, capped at 5000 |
| STRUCTURING | Round-amount transactions (1, 5, 10, 100 ETH) | Above-median score |
| VELOCITY | Burst activity (max hourly txs ≫ average) | Above-median score |

**Adaptive filtering** (replaces old `.head(1000)` hard cap):
- Keeps all addresses scoring above the **median** of qualifying addresses per pattern
- Safety cap at 5000 per pattern to prevent combinatorial explosion
- Result: ~14K unique flagged addresses (vs 5K with hard cap, vs 96K uncapped)

**XGB calibration:**
- Sigmoid calibration: `k=30` centered at `p75` → scale to 0-100
- Raw scores 0.009%–1.1% → calibrated 49.5–57.8
- PR-curve threshold optimization using pseudo-labels (`pattern_count ≥ 3`)

### Step 2 — Build Final Labeled Dataset

| | |
|---|---|
| **Script** | `step2_build_labeled_dataset.py` |
| **Source** | `scripts/build_labeled_v2_final.py` |
| **Input** | `eth_merged_dataset.parquet`; `processed/sophisticated_xgb_combined.csv`; XGB model + TeacherAM model |
| **Output** | **`processed/eth_addresses_labeled_v2.parquet`** (625,168 rows × 80 cols) |
| **Runtime** | ~164 seconds |

**What this step does:**

1. **Aggregate** all 625K addresses from 1.67M transactions (sent/recv counts, values, gas, unique counterparties, active duration)
2. **Merge** ultra-script pattern scores for the 14K flagged addresses
3. **Run XGB** on ALL 625K addresses using both models:
   - ml_pipeline XGB (171 features, primary) — meaningful scores
   - TeacherAM XGB (67 features, secondary) — comparison column
4. **Compute graph properties** for ALL 625K:
   - Degree centrality, betweenness proxy
   - Mixer / sanctioned / exchange interaction counts
   - Graph risk score (weighted composite)
5. **Hybrid score**: `40% XGB + 30% pattern_boost + 30% soph_normalized`
   - Multi-signal bonus: `1.2×` for 2 signals, `1.5×` for 3 signals
6. **Cross-check** XGB vs Rules vs Graph (agreement matrix, overlap rates, Spearman correlations)
7. **Threshold** via PR-curve → `risk_level` → `fraud` label

**Output schema (key columns):**

| Column | Description |
|---|---|
| `address` | Ethereum address (lowercase) |
| `sent_count`, `received_count`, `total_transactions` | Transaction counts |
| `total_sent`, `total_received`, `balance` | ETH values |
| `avg_sent`, `avg_received`, `avg_value` | Averages |
| `sophisticated_score` | Ultra-script pattern score (0 if clean) |
| `patterns` | Comma-separated pattern names |
| `pattern_count` | Number of patterns detected |
| `xgb_raw_score` | ml_pipeline XGB raw output |
| `xgb_normalized` | Sigmoid-calibrated XGB (0-100) |
| `teacher_raw_score` | TeacherAM XGB raw output |
| `pattern_boost` | Sum of pattern boost weights |
| `soph_normalized` | Normalized sophisticated score (0-100) |
| `graph_risk_score` | Composite graph risk (0-100) |
| `degree_centrality`, `betweenness_proxy` | Graph topology metrics |
| `mixer_interaction`, `sanctioned_interaction` | Known-entity interaction counts |
| `hybrid_score` | Final weighted composite (0-100) |
| `signal_count` | Number of active signals (0-3) |
| `risk_level` | CRITICAL / HIGH / MEDIUM / LOW / MINIMAL |
| `fraud` | Binary label (1 = CRITICAL or HIGH) |
| `risk_class` | Numeric (0=MINIMAL → 4=CRITICAL) |

### Step 3 — 30-Day Relabel *(drift update)*

| | |
|---|---|
| **Script** | `step3_relabel_30d.py` |
| **Source** | `automation/relabel_eth_30d_from_etherscan.py` |
| **Input** | `ETHERSCAN_API_KEY`; TeacherAM model |
| **Output** | `processed/eth_30d_teacher_labeled.parquet` |
| **Notes** | For production drift monitoring — fetches fresh data and relabels |

### Step 4 — GAT/GNN Dataset

| | |
|---|---|
| **Script** | `step4_create_gat_dataset.py` |
| **Source** | `scripts/create_gat_transaction_dataset.py` |
| **Input** | `eth_merged_dataset.parquet`; `processed/eth_addresses_labeled.parquet` |
| **Output** | `processed/eth_transactions_full_labeled.parquet`; PyG graph pickle |
| **Notes** | Transaction-level with sender+receiver features + edge_index for PyTorch Geometric |

### Step 5 — Validation & Evaluation

| | |
|---|---|
| **Script** | `step5_validate_metrics.py` / `step5_evaluate_teacher_student.py` |
| **Source** | `scripts/compute_etherscan_validation_metrics.py` / `ml/Automation/evaluate_teacher_vs_student_v2.py` |
| **Input** | Labeled dataset; validation sets; model artifacts |
| **Output** | `reports/publishing/etherscan_validation_metrics.json`; comparison tables |

---

## Folder Structure

```
pipeline/
├── run_pipeline.py                    # Master orchestrator
├── README.md                          # This file
├── __init__.py
├── config/
│   ├── calibrated_thresholds.json     # Model threshold config
│   └── settings.py                    # Inference/hybrid weights
├── step0_fetch_etherscan.py           # Data acquisition (Etherscan)
├── step0_fetch_bigquery.py            # Data acquisition (BigQuery)
├── step1_pattern_detection.py         # 7-pattern ultra detection + XGB
├── step2_build_labeled_dataset.py     # Final 625K labeled parquet
├── step3_relabel_30d.py               # 30-day drift relabeling
├── step3_relabel_teacher.py           # Generic TeacherAM relabeling
├── step4_create_gat_dataset.py        # GAT/GNN dataset builder
├── step5_validate_metrics.py          # External validation metrics
└── step5_evaluate_teacher_student.py  # Teacher vs student comparison
```

## Dependencies

```
polars>=1.0          # Step 1 (Rust-based fast pattern detection)
xgboost>=2.0         # Steps 1, 2 (XGB scoring)
pandas>=2.0          # Step 2 (aggregation, graph properties)
numpy>=1.24          # All steps
scipy>=1.10          # Step 2 (Spearman correlations)
pyarrow>=14.0        # All steps (parquet I/O)
```

## Models Used

| Model | Path | Features | Role |
|---|---|---|---|
| ml_pipeline XGB | `ml/Automation/ml_pipeline/models/trained/xgb.json` | 171 | Primary scorer — produces meaningful 0.009%-1.1% raw scores |
| TeacherAM XGB | `ml/Automation/TeacherAM/models/xgb.json` | 67 | Secondary comparison — near-zero on this data, retained for reference |
| Feature schema (ml) | `ml/Automation/ml_pipeline/models/feature_schema.json` | — | Feature name mapping for ml_pipeline |
| Feature schema (teacher) | `ml/Automation/TeacherAM/metadata/feature_schema.json` | — | Feature name mapping for TeacherAM |

## Key Design Decisions

### Adaptive Pattern Filtering (vs `.head(1000)`)
Each pattern detector keeps all qualifying addresses **above the median score** (p50) rather than an arbitrary top-1000 cutoff. This ensures:
- Score-aware retention (no silent boundary drops)
- Scales with data size (more data → proportional retention)
- Safety cap at 5000 prevents explosion for high-prevalence patterns (LAYERING, PEELING)

### 3-Signal Hybrid Score
```
hybrid_score = 0.40 × XGB_normalized
             + 0.30 × pattern_boost
             + 0.30 × soph_normalized
             × multi_signal_bonus
```
Where `multi_signal_bonus` = 1.2× if 2 signals active, 1.5× if all 3.

### Cross-Check Verification
Step 2 produces a full agreement matrix showing how XGB, rules, and graph signals overlap:
- **Complementary signals**: XGB↔Rules ρ=+0.09 (weak), XGB↔Graph ρ=+0.50 (moderate), Rules↔Graph ρ=+0.17 (weak)
- This confirms the three signals capture different fraud dimensions — exactly what a multi-signal system requires

### Sigmoid Calibration
Raw XGB scores are tiny (0.009%-1.1%) because only 18/171 features have data. Sigmoid calibration (`k=30`, centered at p75) maps these to a 49-58 range on 0-100.

---

## Typical Output (Step 2)

```
Addresses:     625,168
Transactions:  1,673,244
Columns:       80

CRITICAL:        272  (0.04%)
HIGH:            341  (0.05%)
MEDIUM:        2,012  (0.32%)
LOW:         253,014  (40.47%)
MINIMAL:     369,529  (59.11%)

fraud=1:         613  (0.10%)

3-signal overlap (XGB∩Rule∩Graph): 695 addresses
```

## Original Script Locations (canonical sources)

These are the authoritative versions that the pipeline copies are derived from:

| Pipeline Script | Original Location |
|---|---|
| `step0_fetch_etherscan.py` | `automation/eth_data_fetcher.py` |
| `step0_fetch_bigquery.py` | `automation/bigquery_fetcher.py` |
| `step1_pattern_detection.py` | `scripts/sophisticated_fraud_detection_ultra.py` |
| `step2_build_labeled_dataset.py` | `scripts/build_labeled_v2_final.py` |
| `step3_relabel_30d.py` | `automation/relabel_eth_30d_from_etherscan.py` |
| `step3_relabel_teacher.py` | `ml/Automation/relabel_eth_with_teacher.py` |
| `step4_create_gat_dataset.py` | `scripts/create_gat_transaction_dataset.py` |
| `step5_validate_metrics.py` | `scripts/compute_etherscan_validation_metrics.py` |
| `step5_evaluate_teacher_student.py` | `ml/Automation/evaluate_teacher_vs_student_v2.py` |
