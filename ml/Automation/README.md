# ML Automation Pipelines

This workspace contains two distinct training pipelines that should be treated differently:

1) Baseline (Tabular, merged dataset)
- Purpose: Strong tabular baseline on the merged BTC+ETH feature table
- File: `ml/Automation/pipeline/train_baseline_unified.py`
- Features: leak-safe temporal split, global PCA (variance-targeted), XGBoost/LogReg/CatBoost, stacking meta-learner, explainability (SHAP/coefficients)
- Outputs: `ml/Automation/models/cloud/` (per-model artifacts, meta.json, explain/)

2) Memgraph (Graph + Temporal)
- Purpose: Train a graph-temporal fraud detector over time-evolving transaction edges
- Folder: `ml/Automation/graph_temporal/`
	- `train_tgn.py` — GPU-first trainer (TGN fallback), leak-safe time split, AMP, class imbalance
	- `anomaly.py` — simple node embeddings + IsolationForest anomaly scoring
	- `dataset.py` — Polars/Pandas IO, node indexing, temporal split
	- `export_memgraph_edges.py` — export edges from Memgraph to CSV (src,dst,timestamp,label)
- Outputs: `ml/Automation/models/graph_temporal/` (model.pt, meta.json, anomaly artifacts)

## Run: Baseline (Windows PowerShell)
```powershell
python ml/Automation/pipeline/train_baseline_unified.py `
	--merged "C:\path\to\merged_clean.csv" `
	--gpu `
	--models "xgb,cat,lr" `
	--time-split-fracs "0.7,0.15,0.15" `
	--pca-variance 0.99 `
	--pca-max-components 256 `
	--explain-samples 800 `
	--out-dir "ml/Automation/models/cloud"
```

## Run: Baseline on Google Colab (RAPIDS/cuML)

On Colab, the trainer prefers GPU and will try to use RAPIDS when available:
- cuDF is used to read the merged dataset when installed (GPU-accelerated IO)
- cuML UMAP/PCA are used for dimensionality reduction on Linux with GPU

Quick start:
```bash
# Optional but recommended: pre-install RAPIDS
pip install --extra-index-url https://pypi.nvidia.com cudf-cu12 cuml-cu12

# Core dependencies (if missing)
pip install xgboost catboost polars shap matplotlib

# Place your merged dataset under one of these auto-detected paths or pass --merged explicitly
# /content/merged_clean.parquet | /content/merged_clean.csv | /content/merged_dataset.parquet | /content/merged_dataset.csv

python ml/Automation/pipeline/train_baseline_unified.py \
  --gpu \
  --merged "/content/merged_clean.parquet" \
  --models "xgb,cat,lr" \
  --umap-components 16 \
  --pca-components 64
```

Notes:
- You should see "Using GPU acceleration (xgboost gpu_hist)." in logs and "device": "gpu" in the meta JSON.
- UMAP runs only if RAPIDS (cuML) is installed and embedding feature groups are present; otherwise it falls back to PCA or is skipped.
- Global PCA uses cuML when available to hit the configured variance target (default 0.99). Disable with `--no-global-pca` if needed.

## Export edges from Memgraph
Set environment variables (defaults shown) and run the exporter.
```powershell
$env:MG_URI="bolt://localhost:7687"
$env:MG_USER="neo4j"
$env:MG_PASSWORD="memgraph"
$env:MG_QUERY="MATCH (a)-[e:TRANSFER]->(b) RETURN a.address AS src, b.address AS dst, coalesce(e.timestamp, e.ts, e.time) AS timestamp, coalesce(e.label,0) AS label"
python ml/Automation/graph_temporal/export_memgraph_edges.py `
	--out "c:\amttp\data\edges.csv" `
	--limit 2000000
```

## Run: Graph-Temporal (Windows PowerShell)
```powershell
python ml/Automation/graph_temporal/train_tgn.py `
	--edges "c:\amttp\data\edges.csv" `
	--out-dir "ml/Automation/models/graph_temporal" `
	--time-split-frac 0.8 `
	--batch-size 32768 `
	--epochs 30 `
	--lr 3e-4
```

Notes:
- Baseline and Memgraph pipelines are separate by design: different data, models, and outputs.
- GPU training is preferred; on Windows, some graph packages may fall back gracefully.