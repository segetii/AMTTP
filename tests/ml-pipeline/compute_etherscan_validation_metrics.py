import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "processed" / "etherscan_full_validation.csv"
OUT_DIR = ROOT / "reports" / "publishing"
OUT_JSON = OUT_DIR / "etherscan_validation_metrics.json"
OUT_MD = OUT_DIR / "etherscan_validation_metrics.md"


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


def _fmt(x: float) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "NA"
    return f"{x:.4f}"


def _compute_score_metrics(y_true: np.ndarray, y_score: np.ndarray) -> ScoreMetrics:
    y_true = y_true.astype(int)
    n = int(y_true.shape[0])
    positives = int(y_true.sum())
    positive_rate = positives / n if n else float("nan")

    roc_auc = float(roc_auc_score(y_true, y_score)) if n and len(np.unique(y_true)) > 1 else float("nan")
    pr_auc = float(average_precision_score(y_true, y_score)) if n and len(np.unique(y_true)) > 1 else float("nan")

    return ScoreMetrics(n=n, positives=positives, positive_rate=float(positive_rate), roc_auc=roc_auc, pr_auc=pr_auc)


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

    df = pd.read_csv(DATA_PATH)
    # Independent labels from the file: type in {FRAUD, LEGITIMATE}
    y = (df["type"].astype(str).str.upper() == "FRAUD").to_numpy(dtype=int)

    score = pd.to_numeric(df["score"], errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(score)
    y = y[mask]
    score = score[mask]

    # Scores appear to be in [0,100] for most rows, with some small constants (e.g. 0.7)
    # Scaling to [0,1] is monotone and does not change AUC.
    score_01 = score / 100.0

    metrics = {
        "dataset": {
            "path": str(DATA_PATH.relative_to(ROOT)),
            "n_rows": int(df.shape[0]),
            "n_scored": int(mask.sum()),
        },
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "score_metrics": asdict(_compute_score_metrics(y, score_01)),
        "threshold_metrics": {},
        "confusion": {},
        "notes": [
            "This is a small, manually-curated external label set derived from the CSV in processed/.",
            "Treat results as a sanity check, not a statistically powered benchmark.",
        ],
    }

    # Discrete: our_prediction == FRAUD
    pred_flag = (df.loc[mask, "our_prediction"].astype(str).str.upper() == "FRAUD").to_numpy(dtype=int)
    tm = _compute_threshold_metrics(y, pred_flag, "our_prediction == 'FRAUD'")
    metrics["threshold_metrics"]["our_prediction_is_fraud"] = asdict(tm)

    # Discrete: risk_level in {HIGH,CRITICAL}
    risk_level = df.loc[mask, "risk_level"].astype(str).str.upper().to_numpy()
    pred_risk = np.isin(risk_level, ["HIGH", "CRITICAL"]).astype(int)
    tm2 = _compute_threshold_metrics(y, pred_risk, "risk_level in {HIGH,CRITICAL}")
    metrics["threshold_metrics"]["risk_level_is_high_or_critical"] = asdict(tm2)

    cm = confusion_matrix(y, pred_risk, labels=[0, 1])
    metrics["confusion"]["risk_level_is_high_or_critical"] = {
        "labels": {"0": "LEGITIMATE", "1": "FRAUD"},
        "matrix": cm.tolist(),
        "layout": "[[tn, fp], [fn, tp]]",
    }

    OUT_JSON.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    md = []
    md.append("# Etherscan External Validation Metrics (Computed)")
    md.append("")
    md.append(f"Computed at (UTC): {metrics['computed_at']}")
    md.append("")
    md.append("## Dataset")
    md.append("")
    md.append(f"- Source: `{metrics['dataset']['path']}`")
    md.append(f"- Rows: {metrics['dataset']['n_rows']}")
    md.append(f"- Rows with numeric score: {metrics['dataset']['n_scored']}")
    md.append("")
    md.append("## Continuous-Score Metrics")
    md.append("")
    md.append(f"- positives (FRAUD): {metrics['score_metrics']['positives']} / {metrics['score_metrics']['n']} (rate={_fmt(metrics['score_metrics']['positive_rate'])})")
    md.append(f"- ROC-AUC (score): {_fmt(metrics['score_metrics']['roc_auc'])}")
    md.append(f"- PR-AUC  (score): {_fmt(metrics['score_metrics']['pr_auc'])}")
    md.append("")
    md.append("## Discrete Predicate Metrics")
    md.append("")
    for name, tm_ in metrics["threshold_metrics"].items():
        md.append(f"### {name}")
        md.append("")
        md.append(f"- predicate: {tm_['positive_predicate']}")
        md.append(f"- precision: {_fmt(tm_['precision'])}")
        md.append(f"- recall: {_fmt(tm_['recall'])}")
        md.append(f"- f1: {_fmt(tm_['f1'])}")
        md.append("")

    md.append("## Confusion Matrix")
    md.append("")
    cm_info = metrics["confusion"]["risk_level_is_high_or_critical"]
    md.append("For predicate: risk_level in {HIGH,CRITICAL}")
    md.append("")
    md.append(f"- layout: {cm_info['layout']}")
    md.append(f"- matrix: {cm_info['matrix']}")
    md.append("")
    md.append("## Notes")
    md.append("")
    for note in metrics["notes"]:
        md.append(f"- {note}")
    md.append("")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    print(f"Wrote: {OUT_JSON}")
    print(f"Wrote: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
