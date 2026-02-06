import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    precision_recall_fscore_support,
    roc_auc_score,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "processed" / "eth_addresses_labeled.csv"
OUT_DIR = ROOT / "reports" / "publishing"
OUT_JSON = OUT_DIR / "address_level_metrics.json"
OUT_MD = OUT_DIR / "address_level_metrics.md"


@dataclass(frozen=True)
class ScoreMetrics:
    n: int
    positives: int
    positive_rate: float
    roc_auc: float
    pr_auc: float


@dataclass(frozen=True)
class ThresholdMetrics:
    positive_predicate: str
    precision: float
    recall: float
    f1: float


def _safe_float(x: float) -> float:
    if x is None:
        return float("nan")
    try:
        return float(x)
    except Exception:
        return float("nan")


def _compute_score_metrics(y_true: np.ndarray, y_score: np.ndarray) -> ScoreMetrics:
    y_true = y_true.astype(int)

    n = int(y_true.shape[0])
    positives = int(y_true.sum())
    positive_rate = positives / n if n else float("nan")

    roc_auc = float(roc_auc_score(y_true, y_score)) if n and len(np.unique(y_true)) > 1 else float("nan")
    pr_auc = float(average_precision_score(y_true, y_score)) if n and len(np.unique(y_true)) > 1 else float("nan")

    return ScoreMetrics(
        n=n,
        positives=positives,
        positive_rate=float(positive_rate),
        roc_auc=roc_auc,
        pr_auc=pr_auc,
    )


def _compute_threshold_metrics(y_true: np.ndarray, y_pred: np.ndarray, positive_predicate: str) -> ThresholdMetrics:
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true.astype(int), y_pred.astype(int), average="binary", zero_division=0
    )
    return ThresholdMetrics(
        positive_predicate=positive_predicate,
        precision=float(precision),
        recall=float(recall),
        f1=float(f1),
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing dataset: {DATA_PATH}")

    usecols = [
        "fraud",
        "hybrid_score",
        "xgb_normalized",
        "soph_normalized",
        "risk_level",
    ]

    df = pd.read_csv(
        DATA_PATH,
        usecols=usecols,
        dtype={
            "fraud": "int8",
            "hybrid_score": "float32",
            "xgb_normalized": "float32",
            "soph_normalized": "float32",
            "risk_level": "string",
        },
        low_memory=False,
    )

    # Clean
    df = df.dropna(subset=["fraud", "hybrid_score", "xgb_normalized", "soph_normalized", "risk_level"])

    y = df["fraud"].to_numpy(dtype=int)

    # Scores
    hybrid = df["hybrid_score"].to_numpy(dtype=float)
    xgb = df["xgb_normalized"].to_numpy(dtype=float)
    soph = df["soph_normalized"].to_numpy(dtype=float)

    # Normalize any [0,100] scores to [0,1] for AUC stability (monotone scaling; AUC unchanged)
    hybrid_01 = hybrid / 100.0
    xgb_01 = xgb / 100.0
    soph_01 = soph / 100.0

    metrics = {
        "dataset": {
            "path": str(DATA_PATH.relative_to(ROOT)),
            "columns_used": usecols,
        },
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "score_metrics": {
            "hybrid_score": asdict(_compute_score_metrics(y, hybrid_01)),
            "xgb_normalized": asdict(_compute_score_metrics(y, xgb_01)),
            "soph_normalized": asdict(_compute_score_metrics(y, soph_01)),
        },
        "threshold_metrics": {},
        "label_provenance_checks": {},
        "notes": [
            "All metrics are computed from processed/eth_addresses_labeled.csv present in the repo.",
            "ROC-AUC and PR-AUC use continuous scores; threshold metrics use a discrete predicate.",
        ],
    }

    # Discrete predicate consistent with create_complete_labeled_dataset: CRITICAL/HIGH => positive
    risk_level = df["risk_level"].astype(str).to_numpy()
    y_pred_risk = np.isin(risk_level, ["CRITICAL", "HIGH"]).astype(int)

    # Check whether the label is derived from the predicate (proxy-label circularity)
    agreement = float((y_pred_risk == y).mean()) if y.shape[0] else float("nan")
    metrics["label_provenance_checks"]["agreement_fraud_equals_risk_level_predicate"] = {
        "predicate": "risk_level in {CRITICAL,HIGH}",
        "agreement": agreement,
    }

    if agreement == 1.0:
        metrics["notes"].insert(
            0,
            "IMPORTANT: In this dataset, the fraud label exactly matches the predicate risk_level in {CRITICAL,HIGH}. Metrics here reflect proxy-label consistency, not independent generalization performance.",
        )

    metrics["threshold_metrics"]["risk_level_is_critical_or_high"] = asdict(
        _compute_threshold_metrics(y, y_pred_risk, "risk_level in {CRITICAL,HIGH}")
    )

    # Also show MEDIUM+ predicate (often used operationally)
    y_pred_med = np.isin(risk_level, ["CRITICAL", "HIGH", "MEDIUM"]).astype(int)
    metrics["threshold_metrics"]["risk_level_is_medium_or_higher"] = asdict(
        _compute_threshold_metrics(y, y_pred_med, "risk_level in {CRITICAL,HIGH,MEDIUM}")
    )

    OUT_JSON.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    def fmt(x: float) -> str:
        if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
            return "NA"
        return f"{x:.4f}"

    md_lines = []
    md_lines.append("# Address-Level Evaluation Metrics (Computed)")
    md_lines.append("")
    md_lines.append(f"Computed at (UTC): {metrics['computed_at']}")
    md_lines.append("")

    if metrics["label_provenance_checks"]["agreement_fraud_equals_risk_level_predicate"]["agreement"] == 1.0:
        md_lines.append("**IMPORTANT:** The `fraud` label in this dataset exactly matches `risk_level in {CRITICAL,HIGH}`.")
        md_lines.append("This report is therefore a *proxy-label consistency* check and should not be interpreted as independent model generalization performance.")
        md_lines.append("")

    md_lines.append("## Dataset")
    md_lines.append("")
    md_lines.append(f"- Source: `{metrics['dataset']['path']}`")
    md_lines.append(f"- Columns used: {', '.join(usecols)}")
    md_lines.append("")
    md_lines.append("## Continuous-Score Metrics")
    md_lines.append("")
    md_lines.append("Scores are monotone-scaled to [0,1] before AUC computation; this does not change AUC values.")
    md_lines.append("")

    for name, sm in metrics["score_metrics"].items():
        md_lines.append(f"### {name}")
        md_lines.append("")
        md_lines.append(f"- n: {sm['n']}")
        md_lines.append(f"- positives: {sm['positives']}")
        md_lines.append(f"- positive_rate: {fmt(sm['positive_rate'])}")
        md_lines.append(f"- ROC-AUC: {fmt(sm['roc_auc'])}")
        md_lines.append(f"- PR-AUC: {fmt(sm['pr_auc'])}")
        md_lines.append("")

    md_lines.append("## Discrete Predicate Metrics")
    md_lines.append("")
    for name, tm in metrics["threshold_metrics"].items():
        md_lines.append(f"### {name}")
        md_lines.append("")
        md_lines.append(f"- predicate: {tm['positive_predicate']}")
        md_lines.append(f"- precision: {fmt(tm['precision'])}")
        md_lines.append(f"- recall: {fmt(tm['recall'])}")
        md_lines.append(f"- f1: {fmt(tm['f1'])}")
        md_lines.append("")

    OUT_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"Wrote: {OUT_JSON}")
    print(f"Wrote: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
