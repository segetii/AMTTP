"""Evaluate AMTTP V2 student artifacts on the XBlock external ETH dataset.

This script is designed for the dataset you downloaded locally (e.g. Kaggle/XBlock)
with ~9.8K Ethereum addresses and label columns like `label_unified` / `flag`.

It compares:
- Previous model score shipped inside the dataset (columns: teacher_score/teacher_threshold)
- V2 student XGBoost / LightGBM scores from a V2 artifacts bundle

Important:
- The external dataset schema does NOT match V2 training features 1:1.
  We do a best-effort mapping for a subset of the 93 raw features and fill the rest with 0.
  Interpret results as a domain-transfer / blind-spot check, not a definitive benchmark.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import polars as pl


@dataclass(frozen=True)
class EvalResult:
    name: str
    n: int
    positives: int
    positive_rate: float
    roc_auc: float | None
    pr_auc: float | None
    threshold_used: float | None
    f1_at_threshold: float | None
    precision_at_threshold: float | None
    recall_at_threshold: float | None
    best_f1: float | None
    best_f1_threshold: float | None
    confusion_at_threshold: dict | None


def _safe_auc(y_true: np.ndarray, y_score: np.ndarray) -> tuple[float | None, float | None]:
    from sklearn.metrics import average_precision_score, roc_auc_score

    if len(np.unique(y_true)) < 2:
        return (None, None)
    return (float(roc_auc_score(y_true, y_score)), float(average_precision_score(y_true, y_score)))


def _threshold_metrics(y_true: np.ndarray, y_score: np.ndarray, threshold: float) -> tuple[float, float, float, dict]:
    from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

    y_pred = (y_score >= threshold).astype(int)
    f1 = float(f1_score(y_true, y_pred, zero_division=0))
    precision = float(precision_score(y_true, y_pred, zero_division=0))
    recall = float(recall_score(y_true, y_pred, zero_division=0))
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = (int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1]))
    return f1, precision, recall, {"tn": tn, "fp": fp, "fn": fn, "tp": tp}


def _best_f1(y_true: np.ndarray, y_score: np.ndarray) -> tuple[float | None, float | None]:
    from sklearn.metrics import precision_recall_curve

    if len(np.unique(y_true)) < 2:
        return (None, None)
    precision, recall, thresholds = precision_recall_curve(y_true, y_score)
    f1s = (2 * precision * recall) / (precision + recall + 1e-12)
    best_idx = int(np.nanargmax(f1s))
    best_f1 = float(f1s[best_idx])
    if best_idx >= len(thresholds):
        return (best_f1, 1.0)
    return (best_f1, float(thresholds[best_idx]))


def _extract_zip_if_needed(zip_path: Path, extract_dir: Path) -> Path:
    if extract_dir.exists():
        return extract_dir

    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)
    return extract_dir


def _resolve_model_dir(artifact_root: Path) -> Path:
    # The provided ZIP contains a folder like `amttp_models_YYYYMMDD_HHMMSS/`.
    candidates = [p for p in artifact_root.rglob("metadata.json") if p.parent.name.startswith("amttp_models_")]
    if not candidates:
        raise FileNotFoundError(f"Could not find amttp_models_* in: {artifact_root}")
    # Pick the most recent by folder name (lexicographic timestamp)
    candidates.sort(key=lambda p: p.parent.name, reverse=True)
    return candidates[0].parent


def _load_v2_models(model_dir: Path):
    import joblib
    import lightgbm as lgb
    import xgboost as xgb

    with (model_dir / "metadata.json").open("r", encoding="utf-8") as f:
        metadata = json.load(f)
    with (model_dir / "feature_config.json").open("r", encoding="utf-8") as f:
        feature_config = json.load(f)

    preprocessors = joblib.load(str(model_dir / "preprocessors.joblib"))

    xgb_model = xgb.XGBClassifier()
    xgb_model.load_model(str(model_dir / "xgboost_fraud.ubj"))

    lgb_model = lgb.Booster(model_file=str(model_dir / "lightgbm_fraud.txt"))

    return metadata, feature_config, preprocessors, xgb_model, lgb_model


def _preprocess_raw(X_raw: np.ndarray, preprocessors: dict) -> np.ndarray:
    X = X_raw.astype(np.float32, copy=True)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    log_mask = preprocessors.get("log_transform_mask")
    if log_mask is not None:
        # mask is bool array length 93
        X[:, log_mask] = np.log1p(np.clip(X[:, log_mask], 0, None))

    scaler = preprocessors.get("robust_scaler") or preprocessors.get("scaler")
    if scaler is not None:
        X = scaler.transform(X)

    clip_range = preprocessors.get("clip_range", (-5.0, 5.0))
    low, high = float(clip_range[0]), float(clip_range[1])
    return np.clip(X, low, high)


def _build_v2_raw_matrix_xblock(df: pl.DataFrame, raw_features: list[str]) -> tuple[np.ndarray, dict]:
    """Best-effort mapping from XBlock/Kaggle address-level columns to V2 raw features."""

    # Normalize column name lookup
    cols = {c.lower(): c for c in df.columns}

    def col(name: str) -> str | None:
        return cols.get(name.lower())

    # External dataset columns (observed in labelled_eth.parquet)
    mapping_base = {
        "sent_tnx": "sent_tnx",
        "received_tnx": "received_tnx",
        "total_transactions": "total_transactions_(including_tnx_to_create_contract",
        "total_sent": "total_ether_sent",
        "total_received": "total_ether_received",
        "balance": "total_ether_balance",
        "avg_sent": "avg_val_sent",
        "avg_received": "avg_val_received",
        "max_sent": "max_val_sent",
        "min_sent": "min_val_sent",
        "max_received": "max_value_received",
        "min_received": "min_value_received",
        "unique_receivers": "unique_sent_to_addresses",
        "unique_senders": "unique_received_from_addresses",
        "active_duration_mins": "time_diff_between_first_and_last_(mins)",
        "neighbors": "neighbors",
        "count": "count",
        "income": "income",
    }

    # Convert only columns that exist
    resolved = {}
    for k, v in mapping_base.items():
        src = col(v)
        if src is not None:
            resolved[k] = src

    n = df.height
    X = np.zeros((n, len(raw_features)), dtype=np.float32)

    # Pull external values once
    ext_cache: dict[str, np.ndarray] = {}
    for base_key, src in resolved.items():
        ext_cache[base_key] = df[src].to_numpy()

    filled_from_external = 0

    for j, feat in enumerate(raw_features):
        feat_l = feat.lower()

        # tx-level placeholders
        if feat_l in {
            "value_eth",
            "gas_price_gwei",
            "gas_used",
            "gas_limit",
            "transaction_type",
            "nonce",
            "transaction_index",
        }:
            # Approximate value_eth from avg_sent if available, else 0
            if feat_l == "value_eth" and "avg_sent" in ext_cache:
                X[:, j] = np.asarray(ext_cache["avg_sent"], dtype=np.float32)
                filled_from_external += 1
            else:
                X[:, j] = 0.0
            continue

        # mixer/sanctions/exchange flags unavailable → 0
        if feat_l.endswith("_is_mixer") or feat_l.endswith("_is_sanctioned") or feat_l.endswith("_is_exchange"):
            continue
        if "mixer" in feat_l or "sanction" in feat_l or "exchange" in feat_l:
            continue

        # Graph structural metrics are not available in XBlock → 0
        if any(x in feat_l for x in ["in_degree", "out_degree", "degree", "centrality", "betweenness_proxy"]):
            continue

        # Directional address aggregates: map to the same address-level values.
        # This is a simplifying assumption: we set sender_* and receiver_* from the same external aggregates.
        if feat_l.startswith("sender_") or feat_l.startswith("receiver_"):
            suffix = feat_l.split("_", 1)[1]

            # sent/received counts
            if suffix in {"sent_count"} and "sent_tnx" in ext_cache:
                X[:, j] = np.asarray(ext_cache["sent_tnx"], dtype=np.float32)
                filled_from_external += 1
                continue
            if suffix in {"received_count"} and "received_tnx" in ext_cache:
                X[:, j] = np.asarray(ext_cache["received_tnx"], dtype=np.float32)
                filled_from_external += 1
                continue
            if suffix in {"total_transactions"} and "total_transactions" in ext_cache:
                X[:, j] = np.asarray(ext_cache["total_transactions"], dtype=np.float32)
                filled_from_external += 1
                continue

            # value aggregates
            if suffix in {"total_sent"} and "total_sent" in ext_cache:
                X[:, j] = np.asarray(ext_cache["total_sent"], dtype=np.float32)
                filled_from_external += 1
                continue
            if suffix in {"total_received"} and "total_received" in ext_cache:
                X[:, j] = np.asarray(ext_cache["total_received"], dtype=np.float32)
                filled_from_external += 1
                continue
            if suffix in {"balance"} and "balance" in ext_cache:
                X[:, j] = np.asarray(ext_cache["balance"], dtype=np.float32)
                filled_from_external += 1
                continue

            if suffix in {"avg_sent"} and "avg_sent" in ext_cache:
                X[:, j] = np.asarray(ext_cache["avg_sent"], dtype=np.float32)
                filled_from_external += 1
                continue
            if suffix in {"avg_received"} and "avg_received" in ext_cache:
                X[:, j] = np.asarray(ext_cache["avg_received"], dtype=np.float32)
                filled_from_external += 1
                continue

            if suffix in {"max_sent"} and "max_sent" in ext_cache:
                X[:, j] = np.asarray(ext_cache["max_sent"], dtype=np.float32)
                filled_from_external += 1
                continue
            if suffix in {"min_sent"} and "min_sent" in ext_cache:
                X[:, j] = np.asarray(ext_cache["min_sent"], dtype=np.float32)
                filled_from_external += 1
                continue
            if suffix in {"max_received"} and "max_received" in ext_cache:
                X[:, j] = np.asarray(ext_cache["max_received"], dtype=np.float32)
                filled_from_external += 1
                continue
            if suffix in {"min_received"} and "min_received" in ext_cache:
                X[:, j] = np.asarray(ext_cache["min_received"], dtype=np.float32)
                filled_from_external += 1
                continue

            # uniqueness + activity
            if suffix in {"unique_receivers"} and "unique_receivers" in ext_cache:
                X[:, j] = np.asarray(ext_cache["unique_receivers"], dtype=np.float32)
                filled_from_external += 1
                continue
            if suffix in {"unique_senders"} and "unique_senders" in ext_cache:
                X[:, j] = np.asarray(ext_cache["unique_senders"], dtype=np.float32)
                filled_from_external += 1
                continue
            if suffix in {"active_duration_mins"} and "active_duration_mins" in ext_cache:
                X[:, j] = np.asarray(ext_cache["active_duration_mins"], dtype=np.float32)
                filled_from_external += 1
                continue

            # misc
            if suffix in {"neighbors"} and "neighbors" in ext_cache:
                X[:, j] = np.asarray(ext_cache["neighbors"], dtype=np.float32)
                filled_from_external += 1
                continue
            if suffix in {"count"} and "count" in ext_cache:
                X[:, j] = np.asarray(ext_cache["count"], dtype=np.float32)
                filled_from_external += 1
                continue
            if suffix in {"income"} and "income" in ext_cache:
                X[:, j] = np.asarray(ext_cache["income"], dtype=np.float32)
                filled_from_external += 1
                continue

            # ratios not present → 0
            if suffix in {"in_out_ratio", "avg_value", "unique_counterparties"}:
                continue

        # Everything else defaults to 0.

    coverage = {
        "n_raw_features": int(len(raw_features)),
        "filled_from_external": int(filled_from_external),
        "resolved_external_cols": sorted(list({v for v in resolved.values()})),
    }
    return X, coverage


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--artifacts-zip",
        type=Path,
        default=Path(r"C:\Users\Administrator\Downloads\complete_amttp_student_artifacts.zip"),
        help="Path to complete_amttp_student_artifacts.zip",
    )
    ap.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path(r"C:\Users\Administrator\Downloads\complete_amttp_student_artifacts"),
        help="Where to extract ZIP (or existing extracted dir)",
    )
    ap.add_argument(
        "--xblock-parquet",
        type=Path,
        default=Path(r"C:\Users\Administrator\Downloads\labelled_eth.parquet"),
        help="External dataset parquet (XBlock/Kaggle style)",
    )
    ap.add_argument(
        "--out-json",
        type=Path,
        default=Path(r"C:\amttp\reports\publishing\xblock_external_v2_eval.json"),
        help="Where to write JSON results",
    )
    args = ap.parse_args()

    if not args.xblock_parquet.exists():
        raise FileNotFoundError(f"External parquet not found: {args.xblock_parquet}")

    # Extract & resolve model dir
    if args.artifacts_zip.exists():
        artifact_root = _extract_zip_if_needed(args.artifacts_zip, args.artifacts_dir)
    else:
        artifact_root = args.artifacts_dir

    model_dir = _resolve_model_dir(artifact_root)

    # Load models
    metadata, feature_config, preprocessors, xgb_model, lgb_model = _load_v2_models(model_dir)
    raw_features = feature_config["raw_features"]

    # Load external data
    df = pl.read_parquet(str(args.xblock_parquet))

    label_col = "label_unified" if "label_unified" in df.columns else ("flag" if "flag" in df.columns else None)
    if label_col is None:
        raise ValueError(f"No label column found. Expected label_unified or flag. Found: {df.columns}")

    y_true = df[label_col].to_numpy().astype(int)

    # Build feature matrix
    X_raw, coverage = _build_v2_raw_matrix_xblock(df, raw_features)
    X = _preprocess_raw(X_raw, preprocessors)

    # Predict
    xgb_prob = xgb_model.predict_proba(X)[:, 1]
    lgb_prob = lgb_model.predict(X)

    # Teacher baseline if present in dataset
    teacher_score = None
    teacher_threshold = None
    if "teacher_score" in df.columns:
        teacher_score = df["teacher_score"].to_numpy().astype(np.float32)
    if "teacher_threshold" in df.columns:
        # could be scalar or per-row
        tt = df["teacher_threshold"].to_numpy()
        if tt.size:
            teacher_threshold = float(np.nanmedian(tt.astype(np.float64)))

    results: list[EvalResult] = []

    def add_result(name: str, y_score: np.ndarray, threshold: float | None):
        roc, pr = _safe_auc(y_true, y_score)
        best_f1, best_thr = _best_f1(y_true, y_score)

        f1_t = prec_t = rec_t = None
        cm_t = None
        if threshold is not None:
            f1_t, prec_t, rec_t, cm_t = _threshold_metrics(y_true, y_score, float(threshold))

        results.append(
            EvalResult(
                name=name,
                n=int(y_true.shape[0]),
                positives=int(y_true.sum()),
                positive_rate=float(y_true.mean()),
                roc_auc=roc,
                pr_auc=pr,
                threshold_used=float(threshold) if threshold is not None else None,
                f1_at_threshold=f1_t,
                precision_at_threshold=prec_t,
                recall_at_threshold=rec_t,
                best_f1=best_f1,
                best_f1_threshold=best_thr,
                confusion_at_threshold=cm_t,
            )
        )

    add_result("V2 XGBoost", xgb_prob, metadata.get("optimal_threshold"))
    add_result("V2 LightGBM", lgb_prob, metadata.get("optimal_threshold"))

    if teacher_score is not None:
        add_result("Teacher score (from dataset)", teacher_score, teacher_threshold)

    out = {
        "external_dataset": {
            "path": str(args.xblock_parquet),
            "n": int(df.height),
            "label_col": label_col,
        },
        "v2_artifacts": {
            "model_dir": str(model_dir),
            "version": metadata.get("version"),
            "optimal_threshold": metadata.get("optimal_threshold"),
        },
        "feature_mapping": coverage,
        "results": [asdict(r) for r in results],
        "notes": [
            "This evaluation uses best-effort feature mapping from XBlock/Kaggle schema into V2 93 raw features; many features are filled with 0.",
            "Interpret as a blind-spot / domain-transfer check, not a definitive generalization benchmark.",
            "If you want a strict evaluation, we need an external dataset that provides the same 93 features (or a pipeline to compute them from raw transactions).",
        ],
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(out, indent=2), encoding="utf-8")

    # Print quick summary
    print("=" * 80)
    print("External XBlock evaluation")
    print("=" * 80)
    print(f"Dataset: {args.xblock_parquet} (n={df.height}, pos={int(y_true.sum())}, rate={y_true.mean():.2%})")
    print(f"V2: {metadata.get('version')} | optimal_threshold={metadata.get('optimal_threshold')}")
    print(f"Feature mapping: filled_from_external={coverage['filled_from_external']}/{coverage['n_raw_features']}")

    for r in results:
        print("\n---", r.name, "---")
        print(f"ROC-AUC: {r.roc_auc}")
        print(f"PR-AUC:  {r.pr_auc}")
        if r.threshold_used is not None:
            print(f"F1@thr({r.threshold_used:.4f}): {r.f1_at_threshold} | P={r.precision_at_threshold} | R={r.recall_at_threshold}")
            if r.confusion_at_threshold:
                print(f"Confusion: {r.confusion_at_threshold}")
        print(f"Best F1: {r.best_f1} @ thr={r.best_f1_threshold}")

    print("\nWrote:", args.out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
