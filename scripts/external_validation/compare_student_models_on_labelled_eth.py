"""Compare previous vs new AMTTP student artifacts on an external labeled ETH dataset.

Designed for the dataset you downloaded as:
  C:/Users/Administrator/Downloads/labelled_eth.parquet

This script:
- Maps the external dataset into the AMTTP 93-feature schema (best-effort)
- Loads a student artifacts directory (preprocessors + XGB + LGB)
- Runs XGB/LGB probabilities and computes metrics vs label_unified
- Optionally compares two artifacts directories (prev vs new)

Notes
- We intentionally ignore any columns starting with 'h_' or 'teacher_' as model inputs
  to avoid leakage; teacher_* columns are evaluated only as baselines.
- Meta-learner evaluation is not included because the external dataset does not
  provide VAE/GNN-derived meta features.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Metrics:
    n: int
    positives: int
    positive_rate: float
    roc_auc: float
    pr_auc: float
    threshold: float
    precision: float
    recall: float
    f1: float
    tn: int
    fp: int
    fn: int
    tp: int


def _best_f1_threshold(y: np.ndarray, p: np.ndarray) -> float:
    """Find the threshold that maximizes F1 on this dataset.

    This is for reporting only (it is label-dependent).
    """

    from sklearn.metrics import precision_recall_curve

    y = y.astype(int)
    p = np.asarray(p, dtype=float)

    if len(np.unique(y)) < 2:
        return 0.5

    precision, recall, thresholds = precision_recall_curve(y, p)
    if thresholds.size == 0:
        return 0.5

    # thresholds has length = len(precision) - 1
    precision = precision[:-1]
    recall = recall[:-1]
    denom = precision + recall
    f1 = np.zeros_like(denom, dtype=float)
    np.divide(2 * precision * recall, denom, out=f1, where=denom > 0)
    best_idx = int(np.nanargmax(f1))
    return float(thresholds[best_idx])


def _metrics_suite(y: np.ndarray, p: np.ndarray, artifact_threshold: float) -> dict:
    thr_art = float(artifact_threshold)
    thr_half = 0.5
    thr_best = _best_f1_threshold(y, p)
    return {
        "roc_auc": _safe_auc(y, p),
        "pr_auc": _safe_ap(y, p),
        "thresholds": {
            "artifact": thr_art,
            "half": thr_half,
            "best_f1": thr_best,
        },
        "at_artifact": asdict(compute_metrics(y, p, threshold=thr_art)),
        "at_half": asdict(compute_metrics(y, p, threshold=thr_half)),
        "at_best_f1": asdict(compute_metrics(y, p, threshold=thr_best)),
        "score_mean": float(np.mean(p)),
        "score_min": float(np.min(p)),
        "score_max": float(np.max(p)),
    }


def _select_orientation(y: np.ndarray, p: np.ndarray) -> tuple[np.ndarray, str, dict, dict]:
    """Select p vs (1-p) orientation by higher ROC-AUC.

    Returns (p_selected, orientation, suite_as_is, suite_flipped).
    """

    p = np.asarray(p, dtype=float)
    p_flip = 1.0 - p
    auc_as_is = _safe_auc(y, p)
    auc_flip = _safe_auc(y, p_flip)

    # If AUC is NaN (single-class), don't flip.
    if np.isnan(auc_as_is) or np.isnan(auc_flip):
        return p, "as_is", {}, {}
    if auc_flip > auc_as_is:
        return p_flip, "flipped_1_minus_p", {}, {}
    return p, "as_is", {}, {}


def _safe_auc(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score

    if len(np.unique(y)) < 2:
        return float("nan")
    return float(roc_auc_score(y, p))


def _safe_ap(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import average_precision_score

    if len(np.unique(y)) < 2:
        return float("nan")
    return float(average_precision_score(y, p))


def compute_metrics(y: np.ndarray, p: np.ndarray, threshold: float) -> Metrics:
    from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

    y = y.astype(int)
    p = np.asarray(p, dtype=float)
    pred = (p >= float(threshold)).astype(int)

    cm = confusion_matrix(y, pred, labels=[0, 1])
    tn, fp, fn, tp = [int(x) for x in cm.ravel()]

    precision, recall, f1, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)

    return Metrics(
        n=int(y.shape[0]),
        positives=int(y.sum()),
        positive_rate=float(y.mean()) if y.size else float("nan"),
        roc_auc=_safe_auc(y, p),
        pr_auc=_safe_ap(y, p),
        threshold=float(threshold),
        precision=float(precision),
        recall=float(recall),
        f1=float(f1),
        tn=tn,
        fp=fp,
        fn=fn,
        tp=tp,
    )


def _build_features_93(
    df: pd.DataFrame,
    features_93: list[str],
) -> tuple[np.ndarray, dict[str, dict[str, object]]]:
    """Best-effort mapping from the external dataset columns to AMTTP 93 features."""

    # External dataset is address-level (XBlock-like). Map its columns to sender_/receiver_ features.
    # Column names in parquet are snake_case.
    mapping: dict[str, str] = {
        # Counts
        "sent_tnx": "sender_sent_count",
        "received_tnx": "receiver_received_count",
        "total_transactions_(including_tnx_to_create_contract": "sender_total_transactions",
        "unique_sent_to_addresses": "sender_unique_receivers",
        "unique_received_from_addresses": "receiver_unique_senders",
        # Values
        "total_ether_sent": "sender_total_sent",
        "total_ether_received": "receiver_total_received",
        "total_ether_balance": "sender_balance",
        "avg_val_sent": "sender_avg_sent",
        "avg_val_received": "receiver_avg_received",
        "max_val_sent": "sender_max_sent",
        "min_val_sent": "sender_min_sent",
        "max_value_received": "receiver_max_received",
        "min_value_received": "receiver_min_received",
        # Time
        "time_diff_between_first_and_last_(mins)": "sender_active_duration_mins",
        "avg_min_between_sent_tnx": "sender_active_duration_mins",
        "avg_min_between_received_tnx": "receiver_active_duration_mins",
        # Connectivity-ish proxies
        "neighbors": "sender_neighbors",
        "count": "sender_count",
        "income": "sender_income",
    }

    # Build empty frame with exactly expected columns
    out = pd.DataFrame({f: np.zeros(len(df), dtype=np.float32) for f in features_93})

    # Audit: where did each feature come from (and what were other candidates)?
    feature_source: dict[str, str] = {f: "" for f in features_93}
    feature_candidates: dict[str, list[str]] = {f: [] for f in features_93}

    lower_cols = {c.lower(): c for c in df.columns}

    def get_numeric(col_name: str) -> np.ndarray | None:
        src = lower_cols.get(col_name)
        if not src:
            return None
        s = pd.to_numeric(df[src], errors="coerce").fillna(0.0)
        return s.to_numpy(dtype=np.float32)

    # 1) Direct matches: if parquet already has a column with the same name.
    for feat in features_93:
        vals = get_numeric(feat.lower())
        if vals is None:
            continue
        out[feat] = vals
        src = f"direct:{lower_cols[feat.lower()]}"
        feature_source[feat] = src
        feature_candidates[feat].append(src)

    # 2) Known mapping from external names -> AMTTP names.
    for src_lower, dst in mapping.items():
        if dst not in out.columns:
            continue
        vals = get_numeric(src_lower)
        if vals is None:
            continue
        candidate = f"mapped:{lower_cols[src_lower]}"
        feature_candidates[dst].append(candidate)
        if not feature_source.get(dst):
            out[dst] = vals
            feature_source[dst] = candidate

    # Derived fields when we can
    if "sender_total_transactions" in out.columns:
        # If missing, approximate total txns from sent+received
        approx_total = out.get("sender_sent_count", 0) + out.get("receiver_received_count", 0)
        current = out["sender_total_transactions"].to_numpy(dtype=np.float32)
        mask_zero = current == 0
        if isinstance(approx_total, (pd.Series, np.ndarray)):
            approx_arr = np.asarray(approx_total, dtype=np.float32)
            fill_mask = mask_zero & (approx_arr != 0)
            if np.any(fill_mask):
                out.loc[fill_mask, "sender_total_transactions"] = approx_arr[fill_mask]
                existing = feature_source.get("sender_total_transactions", "")
                if existing:
                    if "derived_fill_zeros" not in existing:
                        feature_source["sender_total_transactions"] = f"{existing}+derived_fill_zeros"
                else:
                    feature_source["sender_total_transactions"] = "derived:sent+received_fill_zeros"
                feature_candidates["sender_total_transactions"].append(
                    "derived:sent+received_fill_zeros"
                )

    if "sender_total_sent" in out.columns and "sender_total_transactions" in out.columns:
        denom = np.maximum(out["sender_total_transactions"].to_numpy(dtype=np.float32), 1.0)
        if "value_eth" in out.columns and not feature_source.get("value_eth"):
            out["value_eth"] = (out["sender_total_sent"].to_numpy(dtype=np.float32) / denom).astype(
                np.float32
            )
            feature_source["value_eth"] = "derived:sender_total_sent/sender_total_transactions"
            feature_candidates["value_eth"].append(
                "derived:sender_total_sent/sender_total_transactions"
            )

    if "receiver_total_received" in out.columns and "receiver_received_count" in out.columns:
        denom = np.maximum(out["receiver_received_count"].to_numpy(dtype=np.float32), 1.0)
        out["receiver_avg_received"] = np.where(
            out["receiver_avg_received"].to_numpy(dtype=np.float32) == 0,
            out["receiver_total_received"].to_numpy(dtype=np.float32) / denom,
            out["receiver_avg_received"].to_numpy(dtype=np.float32),
        ).astype(np.float32)
        if "receiver_avg_received" in out.columns and not feature_source.get("receiver_avg_received"):
            feature_source["receiver_avg_received"] = "derived:receiver_total_received/receiver_received_count"
        if "receiver_avg_received" in out.columns:
            feature_candidates["receiver_avg_received"].append(
                "derived:receiver_total_received/receiver_received_count"
            )

    # Mirror sender_balance into receiver_balance if present
    if "sender_balance" in out.columns and "receiver_balance" in out.columns:
        out["receiver_balance"] = np.where(
            out["receiver_balance"].to_numpy(dtype=np.float32) == 0,
            out["sender_balance"].to_numpy(dtype=np.float32),
            out["receiver_balance"].to_numpy(dtype=np.float32),
        ).astype(np.float32)
        if "receiver_balance" in out.columns and not feature_source.get("receiver_balance"):
            feature_source["receiver_balance"] = "derived:mirror_sender_balance"
        if "receiver_balance" in out.columns:
            feature_candidates["receiver_balance"].append("derived:mirror_sender_balance")

    X = out[features_93].to_numpy(dtype=np.float32)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    audit: dict[str, dict[str, object]] = {
        "source": feature_source,
        "candidates": feature_candidates,
    }
    return X, audit


def load_bundle(artifacts_dir: Path) -> dict:
    import joblib
    import xgboost as xgb
    import lightgbm as lgb

    def load_lgb_with_lf_newlines(model_path: Path) -> lgb.Booster:
        """LightGBM 4.x can fail parsing text models with CRLF on Windows.

        Normalize CRLF->LF into a cached file, then load.
        """

        cache_dir = Path(r"C:\\amttp\\cache\\lightgbm_normalized")
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = cache_dir / f"{artifacts_dir.name}__{model_path.name}.lf"

        if not cached.exists() or cached.stat().st_size != model_path.stat().st_size:
            data = model_path.read_bytes().replace(b"\r\n", b"\n")
            cached.write_bytes(data)

        return lgb.Booster(model_file=str(cached))

    preprocessors = joblib.load(str(artifacts_dir / "preprocessors.joblib"))

    xgb_model = xgb.XGBClassifier()
    xgb_model.load_model(str(artifacts_dir / "xgboost_fraud.ubj"))

    lgb_model = load_lgb_with_lf_newlines(artifacts_dir / "lightgbm_fraud.txt")

    feature_config = json.loads((artifacts_dir / "feature_config.json").read_text(encoding="utf-8"))
    metadata = json.loads((artifacts_dir / "metadata.json").read_text(encoding="utf-8"))

    return {
        "dir": str(artifacts_dir),
        "preprocessors": preprocessors,
        "xgb": xgb_model,
        "lgb": lgb_model,
        "feature_config": feature_config,
        "metadata": metadata,
    }


def preprocess_X(X_raw: np.ndarray, preprocessors: dict) -> np.ndarray:
    # Mirror the shipped inference.py behavior.
    X = np.asarray(X_raw, dtype=np.float32)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    log_mask = preprocessors.get("log_transform_mask")
    if log_mask is not None:
        log_mask = np.asarray(log_mask, dtype=bool)
        X[:, log_mask] = np.log1p(np.clip(X[:, log_mask], 0, None))

    scaler = preprocessors.get("robust_scaler")
    if scaler is None:
        raise ValueError("preprocessors.joblib missing 'robust_scaler'")

    X = scaler.transform(X)

    clip_range = preprocessors.get("clip_range", 5)
    if isinstance(clip_range, (int, float, np.integer, np.floating)):
        lo, hi = -float(clip_range), float(clip_range)
    else:
        lo, hi = float(clip_range[0]), float(clip_range[1])
    return np.clip(X, lo, hi)


def score_bundle(df: pd.DataFrame, y: np.ndarray, bundle: dict) -> dict:
    raw_features = bundle["feature_config"].get("raw_features")
    if not raw_features:
        return {
            "bundle_dir": bundle["dir"],
            "error": "feature_config.json missing raw_features (expected 93-feature transfer schema)",
        }

    boost_features = bundle["feature_config"].get("boost_features")
    if not boost_features:
        return {
            "bundle_dir": bundle["dir"],
            "error": "feature_config.json missing boost_features (expected 160 features for XGB/LGB)",
        }

    X_raw, feature_audit = _build_features_93(df, raw_features)
    X_scaled = preprocess_X(X_raw, bundle["preprocessors"])
    feature_source = feature_audit.get("source", {}) if isinstance(feature_audit, dict) else {}

    # Diagnostics: how much of the 93-feature schema is actually populated.
    nonzero_by_feature = (X_raw != 0).mean(axis=0)
    n_features_total = int(len(raw_features))
    n_features_any_nonzero = int(np.sum(nonzero_by_feature > 0))
    all_zero_features = [
        raw_features[i] for i in range(len(raw_features)) if float(nonzero_by_feature[i]) == 0.0
    ]
    nonzero_per_row = (X_raw != 0).sum(axis=1).astype(int)

    source_counts: dict[str, int] = {"": 0, "direct": 0, "mapped": 0, "derived": 0}
    for feat in raw_features:
        src = str(feature_source.get(feat, "")) if isinstance(feature_source, dict) else ""
        if not src:
            source_counts[""] += 1
        elif src.startswith("direct:"):
            source_counts["direct"] += 1
        elif src.startswith("mapped:"):
            source_counts["mapped"] += 1
        elif src.startswith("derived:"):
            source_counts["derived"] += 1

    # Build the 160-dim boost feature vector: [scaled 93 raw] + [zeros for VAE-derived features].
    X_boost = np.zeros((X_scaled.shape[0], len(boost_features)), dtype=np.float32)

    # Most bundles put raw_features first and in the same order; still fill by name for safety.
    boost_idx = {name: i for i, name in enumerate(boost_features)}
    for raw_i, raw_name in enumerate(raw_features):
        j = boost_idx.get(raw_name)
        if j is None:
            continue
        X_boost[:, j] = X_scaled[:, raw_i]

    xgb_prob = bundle["xgb"].predict_proba(X_boost)[:, 1]
    lgb_prob = bundle["lgb"].predict(X_boost)

    thr_artifact = float(bundle["metadata"].get("optimal_threshold", 0.5))

    xgb_selected, xgb_orientation, _, _ = _select_orientation(y, xgb_prob)
    lgb_selected, lgb_orientation, _, _ = _select_orientation(y, lgb_prob)

    return {
        "bundle_dir": bundle["dir"],
        "artifact_threshold": thr_artifact,
        "feature_population": {
            "raw_features_total": n_features_total,
            "raw_features_any_nonzero": n_features_any_nonzero,
            "raw_features_all_zero": int(n_features_total - n_features_any_nonzero),
            "raw_all_zero_feature_names_first20": all_zero_features[:20],
            "raw_feature_source_counts": source_counts,
            "raw_feature_source": feature_source,
            "raw_feature_source_candidates": feature_audit.get("candidates", {})
            if isinstance(feature_audit, dict)
            else {},
            "raw_feature_nonzero_rate": {raw_features[i]: float(nonzero_by_feature[i]) for i in range(len(raw_features))},
            "raw_nonzero_per_row": {
                "min": int(np.min(nonzero_per_row)) if nonzero_per_row.size else 0,
                "p50": float(np.percentile(nonzero_per_row, 50)) if nonzero_per_row.size else 0.0,
                "p90": float(np.percentile(nonzero_per_row, 90)) if nonzero_per_row.size else 0.0,
                "max": int(np.max(nonzero_per_row)) if nonzero_per_row.size else 0,
                "mean": float(np.mean(nonzero_per_row)) if nonzero_per_row.size else 0.0,
            },
        },
        "xgb": {
            "orientation_selected": xgb_orientation,
            "as_is": _metrics_suite(y, xgb_prob, artifact_threshold=thr_artifact),
            "flipped_1_minus_p": _metrics_suite(y, 1.0 - xgb_prob, artifact_threshold=thr_artifact),
            "selected": _metrics_suite(y, xgb_selected, artifact_threshold=thr_artifact),
        },
        "lgb": {
            "orientation_selected": lgb_orientation,
            "as_is": _metrics_suite(y, lgb_prob, artifact_threshold=thr_artifact),
            "flipped_1_minus_p": _metrics_suite(y, 1.0 - lgb_prob, artifact_threshold=thr_artifact),
            "selected": _metrics_suite(y, lgb_selected, artifact_threshold=thr_artifact),
        },
        "feature_mode": "simplified_transfer_raw93_plus_zeros",
        "n_raw_features": int(len(raw_features)),
        "n_boost_features": int(len(boost_features)),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--parquet",
        type=str,
        default=r"C:\Users\Administrator\Downloads\labelled_eth.parquet",
        help="External dataset parquet path (must include label_unified).",
    )
    p.add_argument(
        "--artifacts-a",
        type=str,
        default="",
        help="Optional: second artifacts directory to compare (must expose raw_features in feature_config.json).",
    )
    p.add_argument(
        "--artifacts-b",
        type=str,
        default=r"C:\Users\Administrator\Downloads\complete_amttp_student_artifacts\amttp_models_20260213_213346",
        help="Student artifacts directory (new V2 bundle by default).",
    )
    p.add_argument(
        "--out-json",
        type=str,
        default=r"C:\amttp\reports\external_validation\labelled_eth_student_compare.json",
        help="Where to write comparison JSON.",
    )
    args = p.parse_args()

    parquet = Path(args.parquet)
    if not parquet.exists():
        raise FileNotFoundError(f"Missing parquet: {parquet}")

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(parquet)
    if "label_unified" not in df.columns:
        raise ValueError("External parquet must include 'label_unified' as ground truth")

    y = pd.to_numeric(df["label_unified"], errors="coerce").fillna(0).astype(int).to_numpy()

    # Dataset diagnostics
    used_columns = {
        "label": ["label_unified"],
        "teacher": [c for c in df.columns if c.lower().startswith("teacher_")],
        "leakage_like": [c for c in df.columns if c.lower().startswith("h_")],
    }

    # Teacher baselines (not used as inputs)
    teacher = {}
    if "teacher_score" in df.columns:
        teacher_score = pd.to_numeric(df["teacher_score"], errors="coerce").fillna(0).to_numpy(dtype=float)
        thr = 0.5
        if "teacher_threshold" in df.columns:
            t = pd.to_numeric(df["teacher_threshold"], errors="coerce").dropna().unique()
            if t.size == 1:
                thr = float(t[0])
        teacher["teacher_score"] = _metrics_suite(y, teacher_score, artifact_threshold=thr)
    if "flag" in df.columns:
        # often identical to label_unified
        pass

    bundle_b = load_bundle(Path(args.artifacts_b))

    res_a = None
    if args.artifacts_a:
        bundle_a = load_bundle(Path(args.artifacts_a))
        res_a = score_bundle(df, y, bundle_a)

    res_b = score_bundle(df, y, bundle_b)

    result = {
        "dataset": {
            "path": str(parquet),
            "n": int(len(y)),
            "positives": int(y.sum()),
            "positive_rate": float(y.mean()),
            "columns": {
                "total": int(df.shape[1]),
                "teacher_prefix": used_columns["teacher"],
                "h_prefix": used_columns["leakage_like"],
            },
        },
        "teacher_baselines": teacher,
        "student_b": res_b,
        "notes": [
            "Mapping to 93 features is best-effort; many AMTTP-specific features are missing and set to 0.",
            "Meta-learner is not evaluated because external dataset lacks VAE/GNN-derived meta features.",
            "For XGB/LGB, we report both score orientations (p and 1-p) and select the one with higher ROC-AUC on this labeled dataset. This auto-selection is evaluation-only and should not be used in production inference.",
        ],
    }

    if res_a is not None:
        result["student_a"] = res_a

    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    def fmt_suite(s: dict) -> str:
        m = s["at_artifact"]
        mb = s["at_best_f1"]
        return (
            f"AUC={s['roc_auc']:.4f} AP={s['pr_auc']:.4f} "
            f"F1@artifact={m['f1']:.4f} F1@best={mb['f1']:.4f}"
        )

    print("=" * 88)
    print(f"Dataset: {parquet}  n={len(y):,}  pos={int(y.sum()):,} ({y.mean():.2%})")
    print("=" * 88)
    if teacher:
        for k, m in teacher.items():
            print(f"Teacher baseline ({k}): {fmt_suite(m)}")
    if res_a is not None:
        print("\nStudent A:")
        print(f"  dir: {res_a['bundle_dir']}")
        if "error" in res_a:
            print(f"  error: {res_a['error']}")
        else:
            print(
                f"  XGB ({res_a['xgb']['orientation_selected']}): {fmt_suite(res_a['xgb']['selected'])}"
            )
            print(
                f"  LGB ({res_a['lgb']['orientation_selected']}): {fmt_suite(res_a['lgb']['selected'])}"
            )

    print("\nStudent B:")
    if "error" in res_b:
        print(f"  error: {res_b['error']}")
    else:
        print(f"  dir: {res_b['bundle_dir']}")
        print(
            f"  XGB ({res_b['xgb']['orientation_selected']}): {fmt_suite(res_b['xgb']['selected'])}"
        )
        print(
            f"  LGB ({res_b['lgb']['orientation_selected']}): {fmt_suite(res_b['lgb']['selected'])}"
        )

    print("\nWrote:", out_json)
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
