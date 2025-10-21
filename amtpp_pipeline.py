"""
AMTTP Fraud Ensemble Pipeline (Memory-Safe, Multi-Dataset, GPU Preprocessing)
-----------------------------------------------------------------------------
Best-approach baseline:
- Sequential GPU preprocessing per dataset (cuDF/cuML if available, else pandas fallback)
- Class-balanced capped sampling per dataset
- Unified training with dataset_id as a feature
- Ensemble: TabNet + LightGBM (+ optional GraphSAGE, Transformer)
- Logistic Regression blender
- Crypto signature (keccak256 + ECDSA) for representative output row

Run in Colab with GPU and RAPIDS installed (CUDA12.x):
%pip install -q cudf-cu12 dask-cudf-cu12 cuml-cu12 cupy-cuda12x --extra-index-url=https://pypi.nvidia.com
%pip install -q lightgbm==4.5.0 scikit-learn==1.5.2 pytorch-tabnet==4.1.0 eth-keys eth-utils
# (PyG optional; the script will skip GraphSAGE / Transformer if install fails)

Local (CPU-only) fallback automatically triggers if cuDF import fails.

Memory Constrained / Colab Tips:
- Set AMTTP_LIGHT_MODE=1 to skip GraphSAGE, Transformer, SHAP and shrink epochs/estimators.
- Set AMTTP_STREAMING=1 for chunked ingestion (CPU path) to avoid loading huge CSVs fully.
- Adjust AMTTP_MAX_MEMORY_FRACTION (default 0.55) to control unified table memory budget.
- GLOBAL_ROW_CAP limits total merged rows; lower it if OOM persists.
- TABNET batch sizes: AMTTP_TABNET_BATCH / AMTTP_TABNET_VBATCH env vars.
"""
from __future__ import annotations
import os, gc, json, random, warnings, math, joblib
from typing import List, Dict, Optional, Tuple
warnings.filterwarnings("ignore")

# ------------------ Core Imports ------------------
import numpy as np
import pandas as pd

# ------------------ Try GPU Stack ------------------
GPU_AVAILABLE = False
try:  # RAPIDS
    import cudf  # type: ignore
    import cupy as cp  # type: ignore
    from cuml.preprocessing import StandardScaler as cuStandardScaler  # type: ignore
    GPU_AVAILABLE = True
except Exception:
    cudf = None  # type: ignore
    cp = None  # type: ignore
    cuStandardScaler = None  # type: ignore

# ------------------ Torch / ML ------------------
import torch
import torch.nn as nn
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score
import lightgbm as lgb
from pytorch_tabnet.tab_model import TabNetClassifier

# ------------------ Crypto ------------------
from eth_utils import keccak, to_hex
from eth_keys import keys

# ---------- Optional PyG (GraphSAGE) ----------
try:
    from torch_geometric.nn import SAGEConv, global_mean_pool  # type: ignore
    from torch_geometric.data import Data  # type: ignore
    PYG_AVAILABLE = True
except Exception:
    PYG_AVAILABLE = False

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
SEED = 42
random.seed(SEED); np.random.seed(SEED)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(SEED)

# =========================
# Config (override via env)
# =========================
DATA_DIR = os.environ.get("AMTTP_DATA_DIR", "/content/drive/MyDrive/dataehancedfraud")
OUT_DIR  = os.environ.get("AMTTP_OUT_DIR", "/content/drive/MyDrive/AMTTP_Models_GPU")

DATASETS = [
    {"name":"creditcard",        "path": f"{DATA_DIR}/transaction_dataset.csv",                          "enabled": True},
    {"name":"paysim",            "path": f"{DATA_DIR}/PS_20174392719_1491204439457_log.csv",             "enabled": True},
    {"name":"ethereum",          "path": f"{DATA_DIR}/Cryptocurrency_Scam_Dataset_for_DQN_Models.csv",   "enabled": True},
    {"name":"ieee_transactions", "path": f"{DATA_DIR}/train_transaction.csv",                            "enabled": True},
]

TARGET_COL = "isFraud"
MAX_ROWS_PER_DATASET   = int(os.environ.get("AMTTP_MAX_ROWS", 300_000))
MAJORITY_MULTIPLIER    = int(os.environ.get("AMTTP_MAJORITY_MULT", 3))
SEQ_WINDOW             = int(os.environ.get("AMTTP_SEQ_WINDOW", 20))
TABNET_EPOCHS          = int(os.environ.get("AMTTP_TABNET_EPOCHS", 20))
LGBM_ESTIMATORS        = int(os.environ.get("AMTTP_LGBM_ESTIMATORS", 1000))
STREAMING_ENABLED      = bool(int(os.environ.get("AMTTP_STREAMING", 0)))
STREAM_CHUNK_SIZE      = int(os.environ.get("AMTTP_STREAM_CHUNK", 200_000))
MAX_GRAPH_EDGES        = int(os.environ.get("AMTTP_MAX_GRAPH_EDGES", 300_000))
FALSE_POSITIVE_COST    = float(os.environ.get("AMTTP_COST_FP", 1.0))
FALSE_NEGATIVE_COST    = float(os.environ.get("AMTTP_COST_FN", 5.0))
MAX_SHAP_SAMPLES       = int(os.environ.get("AMTTP_SHAP_SAMPLES", 5000))
LIGHT_MODE             = bool(int(os.environ.get("AMTTP_LIGHT_MODE", 0)))
MEMORY_FRACTION_BUDGET = float(os.environ.get("AMTTP_MAX_MEMORY_FRACTION", 0.55))
GLOBAL_ROW_CAP         = int(os.environ.get("AMTTP_GLOBAL_ROW_CAP", 1_200_000))
TABNET_BATCH_SIZE      = int(os.environ.get("AMTTP_TABNET_BATCH", 4096))
TABNET_VBATCH_SIZE     = int(os.environ.get("AMTTP_TABNET_VBATCH", 1024))

try:
    import shap  # type: ignore
    SHAP_AVAILABLE = True
except Exception:
    SHAP_AVAILABLE = False

try:
    import psutil  # type: ignore
    PSUTIL_AVAILABLE = True
except Exception:
    PSUTIL_AVAILABLE = False

# =====================================================
# Utility / Memory Helpers
# =====================================================

def cleanup_memory():
    gc.collect()
    if GPU_AVAILABLE and cp is not None:
        try:
            cp.get_default_memory_pool().free_all_blocks()
            cp.get_default_pinned_memory_pool().free_all_blocks()
        except Exception:
            pass

def safe_parquet_save(df: pd.DataFrame, path: str):
    """Save DataFrame to parquet; fallback to CSV if engine missing."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        df.to_parquet(path, index=False, compression="snappy")
        return path
    except Exception as e:
        alt = path.replace(".parquet", ".csv.gz")
        df.to_csv(alt, index=False, compression="gzip")
        return alt

# =========================
# Added: GPU Processor Wrapper + Artifact Persist Helpers
# =========================

class GPUMemoryEfficientDataProcessor:
    """
    Wraps the existing function-style GPU preprocessing for parity
    with the design narrative. Keeps lightweight metadata for audit.
    """
    def __init__(self):
        self.processed = []
        self.scalers = {}
        self.datasets = []

    def process(self, cfg_list):
        paths = []
        for cfg in cfg_list:
            if not cfg.get("enabled", True):
                continue
            p = ""
            if GPU_AVAILABLE and not STREAMING_ENABLED:
                p = process_one_dataset_gpu(cfg["path"], cfg["name"])
            else:
                p = process_one_dataset_cpu(cfg["path"], cfg["name"]) if not STREAMING_ENABLED else preprocess_dataset_streaming_cpu(cfg["path"], cfg["name"], STREAM_CHUNK_SIZE)
            if p:
                self.datasets.append(cfg["name"])
                paths.append(p)
        self.processed = paths
        return paths

def persist_threshold_and_manifest(
    out_dir: str,
    blend_threshold: dict,
    feature_names: list,
    cost_fp: float,
    cost_fn: float,
    models_present: list,
    extra: dict | None = None
):
    os.makedirs(out_dir, exist_ok=True)
    thr_path = os.path.join(out_dir, "cost_threshold.json")
    with open(thr_path, "w", encoding="utf-8") as f:
        json.dump(blend_threshold, f, indent=2)

    manifest = {
        "version": "amttp-ensemble-v1",
        "features": feature_names,
        "threshold": blend_threshold.get("threshold"),
        "cost_params": {"fp": cost_fp, "fn": cost_fn},
        "models": models_present,
        "gpu_enabled": GPU_AVAILABLE,
        "light_mode": LIGHT_MODE,
        "timestamp": pd.Timestamp.utcnow().isoformat(),
    }
    if extra:
        manifest.update(extra)
    manifest_path = os.path.join(out_dir, "model_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"🗂  Manifest saved: {manifest_path}")
    return {"threshold_json": thr_path, "manifest_json": manifest_path}

# =====================================================
# Label Inference / Standardization
# =====================================================

def infer_label_column_df(df: pd.DataFrame, target_col: str, dataset_name: str) -> pd.DataFrame:
    if target_col in df.columns:
        return df
    mapping = {
        'creditcard':['FLAG','Class','class'],
        'paysim':['isFraud','is_fraud','fraud'],
        'ethereum':['Is_Scam','is_scam','label','isFraud'],
        'ieee_transactions':['isFraud','is_fraud'],
    }
    candidates = mapping.get(dataset_name, [])
    generic = ['isfraud','fraud','flag','label','class','target','y']
    lower = {c.lower(): c for c in df.columns}
    for c in candidates + generic:
        if c.lower() in lower:
            return df.rename(columns={lower[c.lower()]: target_col})
    return df

# =====================================================
# GPU Path (cuDF) Preprocessing
# =====================================================

def infer_label_column_gdf(gdf, target_col: str, dataset_name: str):  # type: ignore
    if target_col in gdf.columns:
        return gdf
    mapping = {
        'creditcard':['FLAG','Class','class'],
        'paysim':['isFraud','is_fraud','fraud'],
        'ethereum':['Is_Scam','is_scam','label','isFraud'],
        'ieee_transactions':['isFraud','is_fraud'],
    }
    candidates = mapping.get(dataset_name, [])
    generic = ['isfraud','fraud','flag','label','class','target','y']
    lower = {c.lower(): c for c in gdf.columns}
    for c in candidates + generic:
        if c.lower() in lower:
            return gdf.rename(columns={lower[c.lower()]: target_col})
    return gdf

def binaryize_target_gdf(gdf, target_col: str):  # type: ignore
    import cudf  # local import for mypy
    if not cudf.api.types.is_numeric_dtype(gdf[target_col]):
        codes = gdf[target_col].astype('category').cat.codes
        gdf[target_col] = (codes == codes.max()).astype('int8')
    else:
        u = gdf[target_col].dropna().unique().to_cupy()
        if len(u) == 2:
            mx = int(u.max())
            gdf[target_col] = (gdf[target_col] == mx).astype('int8')
        else:
            gdf[target_col] = (gdf[target_col] > 0).astype('int8')
    return gdf

def process_one_dataset_gpu(csv_path: str, dataset_name: str) -> str:
    if not GPU_AVAILABLE:
        return ""
    print(f"\n🔄 GPU preprocessing: {dataset_name}")
    if not os.path.exists(csv_path):
        print(f"  ❌ Missing file: {csv_path}")
        return ""
    gdf = cudf.read_csv(csv_path)  # type: ignore
    gdf = infer_label_column_gdf(gdf, TARGET_COL, dataset_name)
    if TARGET_COL not in gdf.columns:
        print(f"  ❌ No label for {dataset_name}, skipping.")
        return ""
    # Drop rows with >50% missing
    gdf = gdf.dropna(thresh=int(len(gdf.columns) * 0.5))
    num_cols = [c for c in gdf.columns if c != TARGET_COL and str(gdf[c].dtype) not in ('object','str')]  # crude numeric
    cat_cols = [c for c in gdf.columns if c not in num_cols and c != TARGET_COL]
    # Fill
    if num_cols:
        med = gdf[num_cols].quantile(0.5)
        gdf[num_cols] = gdf[num_cols].fillna(med)
    for c in cat_cols:
        vals = gdf[c].dropna()
        fill_val = vals.value_counts().index[0] if len(vals) else "unknown"
        gdf[c] = gdf[c].fillna(fill_val)
    # Cardinality cap
    for c in cat_cols:
        top = gdf[c].value_counts().head(50).index
        gdf[c] = gdf[c].where(gdf[c].isin(top), 'other')
    # Label encode categoricals (basic)
    for c in cat_cols:
        uniq = gdf[c].astype('str').unique().to_pandas().tolist()
        mapping = {v:i for i,v in enumerate(uniq, start=1)}
        mp = pd.DataFrame(list(mapping.items()), columns=[c, f"{c}__id"])
        from cudf import DataFrame as cuDF   # type: ignore
        mp_g = cuDF.from_pandas(mp)
        gdf[c] = gdf[c].astype('str')
        gdf = gdf.merge(mp_g, on=c, how='left')
        gdf = gdf.drop(columns=[c]).rename(columns={f"{c}__id": c}).fillna({c:0})
        gdf[c] = gdf[c].astype('int32')
    # Scale numerics
    if num_cols and cuStandardScaler is not None:
        scaler = cuStandardScaler()
        gdf[num_cols] = scaler.fit_transform(gdf[num_cols])
    # Binary target
    gdf = binaryize_target_gdf(gdf, TARGET_COL)
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = f"{OUT_DIR}/{dataset_name}_processed.parquet"
    gdf.to_parquet(out_path, compression="snappy")  # cuDF writer
    print(f"  💾 Saved: {out_path}  (rows={len(gdf):,}, cols={len(gdf.columns)})")
    cleanup_memory()
    return out_path

# =====================================================
# CPU (pandas) fallback preprocessing
# =====================================================

def binaryize_target_cpu(df: pd.DataFrame, target_col: str):
    if not pd.api.types.is_numeric_dtype(df[target_col]):
        codes = df[target_col].astype('category').cat.codes
        df[target_col] = (codes == codes.max()).astype('int8')
    else:
        u = df[target_col].dropna().unique()
        if len(u) == 2:
            mx = max(u)
            df[target_col] = (df[target_col] == mx).astype('int8')
        else:
            df[target_col] = (df[target_col] > 0).astype('int8')
    return df

def process_one_dataset_cpu(csv_path: str, dataset_name: str) -> str:
    print(f"\n🔄 CPU preprocessing: {dataset_name}")
    if not os.path.exists(csv_path):
        print(f"  ❌ Missing file: {csv_path}")
        return ""
    df = pd.read_csv(csv_path)
    df = infer_label_column_df(df, TARGET_COL, dataset_name)
    if TARGET_COL not in df.columns:
        print(f"  ❌ No label for {dataset_name}, skipping.")
        return ""
    thresh = int(len(df.columns) * 0.5)
    df = df.dropna(thresh=thresh)
    num_cols = [c for c in df.columns if c != TARGET_COL and pd.api.types.is_numeric_dtype(df[c])]
    cat_cols = [c for c in df.columns if c not in num_cols and c != TARGET_COL]
    if num_cols:
        med = df[num_cols].median()
        df[num_cols] = df[num_cols].fillna(med)
    for c in cat_cols:
        mode_val = df[c].mode()
        fill_val = mode_val.iloc[0] if len(mode_val) else "unknown"
        df[c] = df[c].fillna(fill_val)
    for c in cat_cols:
        vc = df[c].value_counts()
        top = vc.head(50).index
        df[c] = df[c].where(df[c].isin(top), 'other')
    # label encode categoricals (simple mapping)
    for c in cat_cols:
        uniq = df[c].astype(str).unique().tolist()
        mapping = {v:i+1 for i,v in enumerate(uniq)}
        df[c] = df[c].astype(str).map(mapping).fillna(0).astype('int32')
    # scale numerics
    if num_cols:
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        df[num_cols] = scaler.fit_transform(df[num_cols])
    df = binaryize_target_cpu(df, TARGET_COL)
    out_path = f"{OUT_DIR}/{dataset_name}_processed.parquet"
    saved = safe_parquet_save(df, out_path)
    print(f"  💾 Saved: {saved} (rows={len(df):,}, cols={len(df.columns)})")
    cleanup_memory()
    return saved

# =====================================================
# Streaming (Incremental) CPU Ingestion (Memory Bounded)
# =====================================================

def preprocess_dataset_streaming_cpu(csv_path: str, dataset_name: str, chunk_size: int = STREAM_CHUNK_SIZE) -> str:
    """Incrementally ingest large CSV with per-chunk preprocessing & balancing.
    Simplifications:
      - Maintains categorical mapping dictionaries across chunks.
      - Performs numeric scaling AFTER concatenation (single pass) to avoid storing large state mid-stream.
      - Applies class balancing cumulatively: stops when cap reached.
    """
    print(f"\n🚰 Streaming CPU preprocessing: {dataset_name} (chunk_size={chunk_size})")
    if not os.path.exists(csv_path):
        print(f"  ❌ Missing file: {csv_path}")
        return ""
    cat_maps: Dict[str, Dict[str, int]] = {}
    collected: List[pd.DataFrame] = []
    total_fraud = 0
    total_legit = 0
    # Pass 1: iterate chunks
    for chunk in pd.read_csv(csv_path, chunksize=chunk_size):
        chunk = infer_label_column_df(chunk, TARGET_COL, dataset_name)
        if TARGET_COL not in chunk.columns:
            continue
        thresh = int(len(chunk.columns) * 0.5)
        chunk = chunk.dropna(thresh=thresh)
        if chunk.empty:
            continue
        num_cols = [c for c in chunk.columns if c != TARGET_COL and pd.api.types.is_numeric_dtype(chunk[c])]
        cat_cols = [c for c in chunk.columns if c not in num_cols and c != TARGET_COL]
        # fill missing
        if num_cols:
            med = chunk[num_cols].median()
            chunk[num_cols] = chunk[num_cols].fillna(med)
        for c in cat_cols:
            mode_val = chunk[c].mode()
            fill_val = mode_val.iloc[0] if len(mode_val) else "unknown"
            chunk[c] = chunk[c].fillna(fill_val)
        # cardinality cap per chunk
        for c in cat_cols:
            vc = chunk[c].value_counts()
            top = vc.head(50).index
            chunk[c] = chunk[c].where(chunk[c].isin(top), 'other')
        # encode categoricals with persistent mapping
        for c in cat_cols:
            if c not in cat_maps:
                cat_maps[c] = {}
            mapping = cat_maps[c]
            # assign ids
            vals = chunk[c].astype(str)
            new_vals = [v for v in vals.unique() if v not in mapping]
            if new_vals:
                start_id = len(mapping) + 1
                for i,v in enumerate(new_vals):
                    mapping[v] = start_id + i
            chunk[c] = vals.map(mapping).fillna(0).astype('int32')
        # binary target
        if not pd.api.types.is_integer_dtype(chunk[TARGET_COL]):
            chunk = binaryize_target_cpu(chunk, TARGET_COL)
        # per-chunk balance sampling logically: we want to approximate global policy
        fraud = chunk[chunk[TARGET_COL] == 1]
        legit = chunk[chunk[TARGET_COL] == 0]
        # compute remaining allowance
        max_total = MAX_ROWS_PER_DATASET
        max_fraud_allowed = max_total // (MAJORITY_MULTIPLIER + 1)
        max_legit_allowed = MAJORITY_MULTIPLIER * max_fraud_allowed
        remaining_fraud = max(0, max_fraud_allowed - total_fraud)
        remaining_legit = max(0, max_legit_allowed - total_legit)
        if remaining_fraud <= 0 and remaining_legit <= 0:
            break
        take_fraud = min(len(fraud), remaining_fraud if remaining_fraud > 0 else len(fraud))
        take_legit = min(len(legit), remaining_legit if remaining_legit > 0 else len(legit))
        part = pd.concat([
            fraud.sample(n=take_fraud, random_state=SEED) if take_fraud < len(fraud) else fraud,
            legit.sample(n=take_legit, random_state=SEED) if take_legit < len(legit) else legit
        ], ignore_index=True)
        total_fraud += (part[TARGET_COL] == 1).sum()
        total_legit += (part[TARGET_COL] == 0).sum()
        collected.append(part)
        if (total_fraud + total_legit) >= MAX_ROWS_PER_DATASET:
            break
    if not collected:
        print("  ⚠️ No data collected in streaming mode.")
        return ""
    final_df = pd.concat(collected, ignore_index=True)
    # scale numerics now
    num_cols_final = [c for c in final_df.columns if c != TARGET_COL and pd.api.types.is_float_dtype(final_df[c])]
    if num_cols_final:
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        final_df[num_cols_final] = scaler.fit_transform(final_df[num_cols_final])
    out_path = f"{OUT_DIR}/{dataset_name}_processed.parquet"
    saved = safe_parquet_save(final_df, out_path)
    print(f"  💾 Streaming saved: {saved} (rows={len(final_df):,})")
    cleanup_memory()
    return saved

# =====================================================
# Sampling & Merge (Memory Safe)
# =====================================================

def balanced_cap_sample(df: pd.DataFrame, target_col: str) -> pd.DataFrame:
    fraud = df[df[target_col] == 1]
    legit = df[df[target_col] == 0]
    if len(fraud) == 0 or len(legit) == 0:
        return df.sample(n=min(len(df), MAX_ROWS_PER_DATASET), random_state=SEED)
    keep_legit = min(len(legit), MAJORITY_MULTIPLIER * len(fraud))
    df_bal = pd.concat([fraud, legit.sample(n=keep_legit, random_state=SEED)], ignore_index=True)
    if len(df_bal) > MAX_ROWS_PER_DATASET:
        df_bal = df_bal.sample(n=MAX_ROWS_PER_DATASET, random_state=SEED)
    return df_bal

def load_all_processed_as_merged(parquets: List[str]) -> pd.DataFrame:
    def _mem_bytes(d: pd.DataFrame) -> int:
        return int(d.memory_usage(deep=True).sum())
    if PSUTIL_AVAILABLE:
        total_ram = psutil.virtual_memory().total
        budget = int(total_ram * MEMORY_FRACTION_BUDGET)
    else:
        budget = int(12 * (1024**3) * MEMORY_FRACTION_BUDGET)
    frames: List[pd.DataFrame] = []
    dataset_ids: List[int] = []
    cur_id = 1
    total_rows = 0
    for p in parquets:
        if not (p and os.path.exists(p)):
            continue
        f = pd.read_parquet(p)
        f_bal = balanced_cap_sample(f, TARGET_COL)
        if total_rows + len(f_bal) > GLOBAL_ROW_CAP:
            remain = GLOBAL_ROW_CAP - total_rows
            if remain <= 0:
                break
            f_bal = f_bal.sample(n=remain, random_state=SEED)
        frames.append(f_bal)
        dataset_ids.extend([cur_id]*len(f_bal))
        total_rows += len(f_bal)
        cur_id += 1
        merged_mem = sum(_mem_bytes(fr) for fr in frames)
        if merged_mem > budget:
            shrink = budget / merged_mem
            if shrink < 0.95:
                new_frames: List[pd.DataFrame] = []
                new_ids: List[int] = []
                for did, fr in enumerate(frames, start=1):
                    target = max(1000, int(len(fr) * shrink))
                    fr_s = fr.sample(n=target, random_state=SEED) if target < len(fr) else fr
                    new_frames.append(fr_s)
                    new_ids.extend([did]*len(fr_s))
                frames = new_frames
                dataset_ids = new_ids
                gc.collect()
    if not frames:
        raise RuntimeError("No processed dataset files found.")
    df = pd.concat(frames, ignore_index=True)
    df['dataset_id'] = np.array(dataset_ids[:len(df)], dtype=np.int32)
    final_mem = _mem_bytes(df)
    if final_mem > budget:
        frac = budget / final_mem
        keep_n = max(10_000, int(len(df) * frac))
        df = df.sample(n=keep_n, random_state=SEED).reset_index(drop=True)
        print(f"⚖️ Memory guard: downsampled unified table to {len(df):,} rows (budget≈{budget/1e9:.2f}GB)")
    return df

# =====================================================
# Feature Splits
# =====================================================

def split_cols(df: pd.DataFrame, target_col: str):
    cat_cols = [c for c in df.columns if c != target_col and str(df[c].dtype) in ("int32","int64")]
    cat_cols = [c for c in cat_cols if c != target_col and df[c].nunique() <= 100000]
    num_cols = [c for c in df.columns if c not in cat_cols and c != target_col]
    if "dataset_id" in df.columns and "dataset_id" not in cat_cols:
        cat_cols.append("dataset_id")
    return cat_cols, num_cols

# =====================================================
# Optional Graph Construction (Proxy)
# =====================================================

def detect_entity_columns(df: pd.DataFrame) -> List[str]:
    candidates = []
    patterns = ["account","acct","card","customer","merchant","ip","device","user","address","sender","receiver","from","to","addr","wallet","hash"]
    for c in df.columns:
        lc = c.lower()
        if any(p in lc for p in patterns):
            # reasonable cardinality filter
            nunq = df[c].nunique()
            if 2 <= nunq <= min(len(df)//2 + 1, 1_000_000):
                candidates.append(c)
    return candidates[:5]

def build_real_graph(df: pd.DataFrame, numeric_cols: List[str], max_edges: int = MAX_GRAPH_EDGES):
    if not PYG_AVAILABLE:
        return None
    entity_cols = detect_entity_columns(df)
    if not entity_cols and not numeric_cols:
        return None
    # Node features: select up to 32 numerics (pad if needed)
    feats = numeric_cols[:min(32, len(numeric_cols))]
    if not feats:
        # fabricate minimal feature if none
        df['_dummy_feat'] = 0.0
        feats = ['_dummy_feat']
    x = torch.tensor(df[feats].fillna(0).values, dtype=torch.float32)
    N = len(df)
    edges_list: List[Tuple[int,int]] = []
    # For each entity column, connect rows sharing same entity in a star (first occurrence hub)
    for col in entity_cols:
        groups = df.groupby(col).indices
        for _, idxs in groups.items():
            if len(idxs) < 2:
                continue
            center = idxs[0]
            for j in idxs[1:]:
                edges_list.append((center, j))
                if len(edges_list) >= max_edges:
                    break
            if len(edges_list) >= max_edges:
                break
        if len(edges_list) >= max_edges:
            break
    # Fallback: ensure at least a chain if still sparse
    if len(edges_list) < min(10, N-1):
        for i in range(N-1):
            edges_list.append((i, i+1))
            if len(edges_list) >= max_edges:
                break
    if not edges_list:
        return None
    edges = np.array(edges_list, dtype=np.int64).T  # shape (2,E)
    edge_index = torch.tensor(edges, dtype=torch.long)
    y = torch.tensor(df[TARGET_COL].values, dtype=torch.long)
    return Data(x=x, edge_index=edge_index, y=y)

class GraphSAGEModel(nn.Module):
    def __init__(self, in_dim, hidden=128):
        super().__init__()
        self.conv1 = SAGEConv(in_dim, hidden)
        self.conv2 = SAGEConv(hidden, hidden)
        self.lin1  = nn.Linear(hidden, 64)
        self.out   = nn.Linear(64, 1)
        self.relu, self.drop, self.sig = nn.ReLU(), nn.Dropout(0.2), nn.Sigmoid()
    def forward(self, x, edge_index, batch=None):
        x = self.relu(self.conv1(x, edge_index))
        x = self.relu(self.conv2(x, edge_index))
        x = global_mean_pool(x, batch) if batch is not None else x.mean(dim=0, keepdim=True).repeat(x.size(0),1)
        x = self.drop(self.relu(self.lin1(x)))
        return self.sig(self.out(x))

# =====================================================
# Tiny Transformer (Sequence Proxy)
# =====================================================
class TinyTransformer(nn.Module):
    def __init__(self, feat_dim=16, d_model=128, nhead=8, num_layers=2):
        super().__init__()
        self.proj = nn.Linear(feat_dim, d_model)
        enc_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, dim_feedforward=512, dropout=0.1, batch_first=True)
        self.enc = nn.TransformerEncoder(enc_layer, num_layers=num_layers)
        self.cls = nn.Linear(d_model, 1)
        self.sig = nn.Sigmoid()
    def forward(self, x):
        h = self.proj(x)
        h = self.enc(h)
        h = h.mean(1)
        return self.sig(self.cls(h))

def build_sequences(df: pd.DataFrame, num_cols, T=20, max_batches=1024):
    if len(num_cols) == 0:
        return None, None
    sel = num_cols[:min(16, len(num_cols))]
    N = len(df)
    if N < T:
        return None, None
    step = T
    max_windows = min((N - T + 1)//step, max_batches)
    if max_windows <= 0:
        return None, None
    seqs = []
    labs = []
    for i in range(0, max_windows * step, step):
        window = df[sel].iloc[i:i+T].values.astype(np.float32)
        seqs.append(window)
        labs.append(df[TARGET_COL].iloc[i:i+T].max())
    X = torch.tensor(np.stack(seqs), dtype=torch.float32)
    y = torch.tensor(np.array(labs, dtype=np.float32))
    return X, y

# =====================================================
# Main Training / Blending
# =====================================================

def train_tabnet(train_df: pd.DataFrame, val_df: pd.DataFrame, cat_cols, num_cols):
    features = cat_cols + num_cols
    X_train = train_df[features].values
    X_val   = val_df[features].values
    y_train = train_df[TARGET_COL].values
    y_val   = val_df[TARGET_COL].values
    tabnet = TabNetClassifier(
        n_d=64, n_a=64, n_steps=5, gamma=1.5,
        optimizer_fn=torch.optim.Adam, optimizer_params=dict(lr=2e-3),
        mask_type="entmax"
    )
    effective_epochs = TABNET_EPOCHS if not LIGHT_MODE else min(TABNET_EPOCHS, 12)
    tabnet.fit(X_train=X_train, y_train=y_train,
               eval_set=[(X_val, y_val)], eval_metric=['auc'],
               max_epochs=effective_epochs, patience=5, batch_size=TABNET_BATCH_SIZE, virtual_batch_size=TABNET_VBATCH_SIZE,
               num_workers=0, drop_last=False)
    val_pred = tabnet.predict_proba(X_val)[:,1]
    return tabnet, val_pred

def train_lightgbm(train_df: pd.DataFrame, val_df: pd.DataFrame, cat_cols, num_cols):
    features = cat_cols + num_cols
    n_estimators = LGBM_ESTIMATORS if not LIGHT_MODE else min(LGBM_ESTIMATORS, 400)
    lgbm = lgb.LGBMClassifier(
        n_estimators=n_estimators, learning_rate=0.05, num_leaves=31,
        subsample=0.8, colsample_bytree=0.8, random_state=SEED
    )
    lgbm.fit(train_df[features], train_df[TARGET_COL],
             eval_set=[(val_df[features], val_df[TARGET_COL])], eval_metric="auc", verbose=False)
    val_pred = lgbm.predict_proba(val_df[features])[:,1]
    return lgbm, val_pred

def run_graphsage(val_df: pd.DataFrame, num_cols):
    if LIGHT_MODE:
        print("ℹ️ LIGHT_MODE=1: skipping GraphSAGE.")
        return None
    if not PYG_AVAILABLE:
        print("ℹ️ PyG not available; skipping GraphSAGE.")
        return None
    gdata = build_real_graph(val_df, num_cols)
    if gdata is None:
        print("⚠️ Graph construction failed or insufficient data.")
        return None
    model = GraphSAGEModel(in_dim=gdata.x.shape[1]).to(DEVICE)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    bce = nn.BCELoss()
    for _ in range(6):
        model.train(); opt.zero_grad()
        out = model(gdata.x.to(DEVICE), gdata.edge_index.to(DEVICE)).view(-1)
        loss = bce(out, gdata.y.float().to(DEVICE)); loss.backward(); opt.step()
    model.eval()
    with torch.no_grad():
        preds = model(gdata.x.to(DEVICE), gdata.edge_index.to(DEVICE)).view(-1).cpu().numpy()
    return preds

def run_transformer(val_df: pd.DataFrame, num_cols):
    if LIGHT_MODE:
        print("ℹ️ LIGHT_MODE=1: skipping Transformer.")
        return None
    X_seq, y_seq = build_sequences(val_df, num_cols, T=SEQ_WINDOW, max_batches=256)
    if X_seq is None:
        print("ℹ️ No sequence view; skipping Transformer.")
        return None
    model = TinyTransformer(feat_dim=X_seq.shape[-1]).to(DEVICE)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    bce = nn.BCELoss()
    for _ in range(6):
        model.train(); opt.zero_grad()
        out = model(X_seq.to(DEVICE)).view(-1)
        loss = bce(out, y_seq.to(DEVICE)); loss.backward(); opt.step()
    model.eval()
    with torch.no_grad():
        pv = model(X_seq.to(DEVICE)).view(-1).cpu().numpy()
    return pv

# =====================================================
# Feature Importance / SHAP / Thresholding / Persistence
# =====================================================

def compute_feature_importances(tabnet: TabNetClassifier, lgbm: lgb.LGBMClassifier, feature_names: List[str]):
    results = {}
    # TabNet feature importances
    try:
        t_imp = tabnet.feature_importances_ if hasattr(tabnet, 'feature_importances_') else None
        if t_imp is not None:
            results['tabnet'] = {fn: float(w) for fn, w in zip(feature_names, t_imp)}
            with open(os.path.join(OUT_DIR, 'feature_importances_tabnet.json'), 'w', encoding='utf-8') as f:
                json.dump(results['tabnet'], f, indent=2)
    except Exception as e:
        print(f"⚠️ TabNet importance extraction failed: {e}")
    # LightGBM
    try:
        booster = lgbm.booster_
        gain = booster.feature_importance(importance_type='gain')
        split = booster.feature_importance(importance_type='split')
        lgb_imp = {fn: {"gain": float(g), "split": int(s)} for fn, g, s in zip(feature_names, gain, split)}
        results['lightgbm'] = lgb_imp
        with open(os.path.join(OUT_DIR, 'feature_importances_lightgbm.json'), 'w', encoding='utf-8') as f:
            json.dump(lgb_imp, f, indent=2)
    except Exception as e:
        print(f"⚠️ LightGBM importance extraction failed: {e}")
    return results

def compute_shap_values_lgbm(lgbm: lgb.LGBMClassifier, val_df: pd.DataFrame, feature_names: List[str]):
    if not SHAP_AVAILABLE:
        print("ℹ️ SHAP not installed; skipping.")
        return None
    if LIGHT_MODE:
        print("ℹ️ LIGHT_MODE=1: skipping SHAP computation.")
        return None
    try:
        sample = val_df[feature_names]
        if len(sample) > MAX_SHAP_SAMPLES:
            sample = sample.sample(n=MAX_SHAP_SAMPLES, random_state=SEED)
        explainer = shap.TreeExplainer(lgbm)
        shap_vals = explainer.shap_values(sample)
        # binary classification returns list
        if isinstance(shap_vals, list) and len(shap_vals) == 2:
            shap_vals = shap_vals[1]
        mean_abs = np.abs(shap_vals).mean(axis=0)
        shap_imp = {fn: float(v) for fn, v in zip(feature_names, mean_abs)}
        with open(os.path.join(OUT_DIR, 'shap_lightgbm_importance.json'), 'w', encoding='utf-8') as f:
            json.dump(shap_imp, f, indent=2)
        np.savez_compressed(os.path.join(OUT_DIR, 'shap_lightgbm_values.npz'), values=shap_vals, features=feature_names, index=sample.index.values)
        print(f"🧷 SHAP (LightGBM) computed on {len(sample)} samples.")
        return shap_imp
    except Exception as e:
        print(f"⚠️ SHAP computation failed: {e}")
        return None

def compute_cost_based_threshold(y_true: np.ndarray, y_prob: np.ndarray, cost_fp: float, cost_fn: float):
    # Use percentile-based candidate thresholds for numerical stability
    qs = np.unique(np.quantile(y_prob, np.linspace(0,1,101)))
    best = {"threshold": 0.5, "cost": float('inf'), "fp":0, "fn":0, "tp":0, "tn":0}
    P = (y_true == 1).sum(); N = (y_true == 0).sum()
    for t in qs:
        pred = (y_prob >= t).astype(int)
        tp = int(((pred == 1) & (y_true == 1)).sum())
        fp = int(((pred == 1) & (y_true == 0)).sum())
        fn = int(((pred == 0) & (y_true == 1)).sum())
        tn = int(((pred == 0) & (y_true == 0)).sum())
        cost = fp * cost_fp + fn * cost_fn
        if cost < best['cost']:
            best = {"threshold": float(t), "cost": float(cost), "fp":fp, "fn":fn, "tp":tp, "tn":tn,
                    "tpr": float(tp/(P+1e-9)), "fpr": float(fp/(N+1e-9))}
    return best

def persist_models(tabnet: TabNetClassifier, lgbm: lgb.LGBMClassifier, blender: LogisticRegression):
    try:
        tabnet.save_model(os.path.join(OUT_DIR, 'tabnet_model'))
    except Exception as e:
        print(f"⚠️ Failed saving TabNet: {e}")
    try:
        lgbm.booster_.save_model(os.path.join(OUT_DIR, 'lightgbm_model.txt'))
    except Exception as e:
        print(f"⚠️ Failed saving LightGBM: {e}")
    try:
        joblib.dump(blender, os.path.join(OUT_DIR, 'blender_logreg.joblib'))
    except Exception as e:
        print(f"⚠️ Failed saving blender: {e}")
    print("💾 Models persisted to disk.")

# =====================================================
# Orchestration
# =====================================================

def preprocess_all() -> List[str]:
    paths: List[str] = []
    for cfg in DATASETS:
        if not cfg.get("enabled", True):
            continue
        if GPU_AVAILABLE and not STREAMING_ENABLED:
            p = process_one_dataset_gpu(cfg["path"], cfg["name"])
        else:
            # if streaming enabled (or GPU unavailable) use streaming CPU ingestion
            if STREAMING_ENABLED:
                p = preprocess_dataset_streaming_cpu(cfg["path"], cfg["name"], STREAM_CHUNK_SIZE)
            else:
                p = process_one_dataset_cpu(cfg["path"], cfg["name"])
        if p:
            paths.append(p)
    return paths

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"GPU stack available: {GPU_AVAILABLE}")
    print(f"LIGHT_MODE={LIGHT_MODE} | STREAMING_ENABLED={STREAMING_ENABLED} | MEMORY_FRACTION_BUDGET={MEMORY_FRACTION_BUDGET} | GLOBAL_ROW_CAP={GLOBAL_ROW_CAP}")
    if LIGHT_MODE:
        print("ℹ️ Light mode active: GraphSAGE, Transformer, SHAP skipped; reduced epochs/estimators.")

    # Use new processor wrapper (audit visibility)
    gpu_proc = GPUMemoryEfficientDataProcessor()
    parquet_paths = gpu_proc.process(DATASETS)

    if not parquet_paths:
        raise RuntimeError("No datasets processed; check paths.")

    df = load_all_processed_as_merged(parquet_paths)
    print(f"\n📊 Unified training table: {df.shape}, fraud_rate={df[TARGET_COL].mean():.4f}")

    train_df, val_df = train_test_split(df, test_size=0.2, random_state=SEED, stratify=df[TARGET_COL])
    cat_cols, num_cols = split_cols(df, TARGET_COL)
    print(f"🔤 Categorical: {len(cat_cols)} | 🔢 Numeric: {len(num_cols)}")

    tabnet, tab_val = train_tabnet(train_df, val_df, cat_cols, num_cols)
    print("🟣 TabNet AUC:", roc_auc_score(val_df[TARGET_COL], tab_val))
    lgbm, lgb_val = train_lightgbm(train_df, val_df, cat_cols, num_cols)
    print("🟡 LightGBM AUC:", roc_auc_score(val_df[TARGET_COL], lgb_val))

    graph_val = run_graphsage(val_df, num_cols)
    if graph_val is not None:
        print("🟢 GraphSAGE AUC (proxy):", roc_auc_score(val_df[TARGET_COL][:len(graph_val)], graph_val[:len(val_df)]))
    seq_val = run_transformer(val_df, num_cols)
    if seq_val is not None:
        seq_val = np.resize(seq_val, len(val_df))

    scores = [tab_val, lgb_val]
    names  = ["tabnet", "lightgbm"]
    if graph_val is not None and len(graph_val) == len(val_df):
        scores.append(graph_val); names.append("graphsage")
    if seq_val is not None:
        scores.append(seq_val); names.append("transformer")

    S_val = np.vstack(scores).T
    blender = LogisticRegression(max_iter=1000).fit(S_val, val_df[TARGET_COL])
    blend_val = blender.predict_proba(S_val)[:,1]
    print("🔮 Blender AUC:", roc_auc_score(val_df[TARGET_COL], blend_val), "| PR-AUC:", average_precision_score(val_df[TARGET_COL], blend_val))
    print("🧪 Blender inputs:", names)

    best_thresh = compute_cost_based_threshold(val_df[TARGET_COL].values, blend_val, FALSE_POSITIVE_COST, FALSE_NEGATIVE_COST)
    print(f"💲 Cost-based threshold: {best_thresh['threshold']:.4f} | cost={best_thresh['cost']:.2f} | TPR={best_thresh['tpr']:.3f} | FPR={best_thresh['fpr']:.3f}")

    feature_names = cat_cols + num_cols
    compute_feature_importances(tabnet, lgbm, feature_names)
    compute_shap_values_lgbm(lgbm, val_df, feature_names)
    persist_models(tabnet, lgbm, blender)

    # Persist threshold + manifest
    persist_threshold_and_manifest(
        OUT_DIR,
        best_thresh,
        feature_names,
        FALSE_POSITIVE_COST,
        FALSE_NEGATIVE_COST,
        names,
        extra={"datasets": gpu_proc.datasets}
    )

    # Sample cryptographic signature
    i = 0
    indiv = {n: float(scores[j][i]) for j,n in enumerate(names)}
    risk_score = float(blend_val[i])
    confidence = float(np.std(list(indiv.values()))) if indiv else 0.0
    payload = {
        "transaction_id": str(val_df.index[i]),
        "risk_score": risk_score,
        "risk_level": 1 if risk_score < 0.33 else 2 if risk_score < 0.66 else 3,
        "confidence": confidence,
        "individual_scores": indiv,
        "explanations": []
    }
    demo_priv = "0x" + "a"*64  # Placeholder only; DO NOT use in production
    msg = f"{payload['risk_score']}|{payload['transaction_id']}|{payload['risk_level']}"
    h = keccak(text=msg)
    pk = keys.PrivateKey(bytes.fromhex(demo_priv.replace("0x","")))
    sig = pk.sign_msg_hash(h)
    signer = pk.public_key.to_checksum_address()
    final_output = {**payload, "hash": to_hex(h), "signature": to_hex(sig.to_bytes()), "signer": signer,
                    "cost_threshold": best_thresh}
    sig_path = os.path.join(OUT_DIR, "sample_signed_payload.json")
    with open(sig_path, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2)
    print("\n🔐 Signed payload saved:", sig_path)
    print(json.dumps(final_output, indent=2))

if __name__ == "__main__":
    main()
