"""Relabel ETH data using a TeacherAM model artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _load_feature_schema(schema_path: Path) -> list[str]:
    with schema_path.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    features = schema.get("feature_names", [])
    if not features:
        raise ValueError(f"No feature_names found in {schema_path}")
    return features


def _select_teacher_model(model_comp_path: Path) -> tuple[str, float]:
    df = pd.read_csv(model_comp_path)
    if "Val AP" not in df.columns or "Model" not in df.columns:
        raise ValueError("model_comparison.csv missing required columns")

    best = df.sort_values("Val AP", ascending=False).iloc[0]
    model_name = str(best["Model"]).strip().lower()
    threshold = float(best.get("Optimal Threshold", 0.5))

    # Stacking requires base-model probabilities, not raw features.
    if model_name == "stacking":
        model_name = "xgb"
    return model_name, threshold


def _load_model(model_name: str, models_dir: Path):
    if model_name == "xgb":
        import xgboost as xgb

        model_path = models_dir / "xgb.json"
        booster = xgb.Booster()
        booster.load_model(str(model_path))
        return ("xgb", booster)
    if model_name == "lgbm":
        import lightgbm as lgb

        model_path = models_dir / "lgbm.txt"
        booster = lgb.Booster(model_file=str(model_path))
        return ("lgbm", booster)
    raise ValueError(f"Unsupported model: {model_name}")


def _predict(model_name: str, model, X: pd.DataFrame) -> np.ndarray:
    if model_name == "xgb":
        import xgboost as xgb

        dmatrix = xgb.DMatrix(X.values, feature_names=list(X.columns))
        return model.predict(dmatrix)
    if model_name == "lgbm":
        return model.predict(X.values)
    raise ValueError(f"Unsupported model: {model_name}")


def relabel_dataset(
    input_path: Path,
    output_path: Path,
    schema_path: Path,
    models_dir: Path,
    model_comp_path: Path,
) -> None:
    features = _load_feature_schema(schema_path)
    model_name, threshold = _select_teacher_model(model_comp_path)
    model_name, model = _load_model(model_name, models_dir)

    try:
        df = pd.read_parquet(input_path, engine="pyarrow")
    except Exception:
        df = pd.read_parquet(input_path)

    missing = [f for f in features if f not in df.columns]
    if missing:
        print(f"[WARN] Missing {len(missing)} features; filling with 0. Example: {missing[:5]}")

    # Backfill harmonized h_* features if they are missing.
    if any(col.startswith("h_") for col in missing):
        total_in = df.get("total_ether_received", 0)
        total_out = df.get("total_ether_sent", 0)
        total_to_contracts = df.get("total_ether_sent_contracts", 0)
        tx_in = df.get("received_tnx", 0)
        tx_out = df.get("sent_tnx", 0)
        tx_total = df.get("total_transactions_(including_tnx_to_create_contract", 0)
        counter_in = df.get("unique_received_from_addresses", 0)
        counter_out = df.get("unique_sent_to_addresses", 0)
        temporal_span = df.get("time_diff_between_first_and_last_(mins)", 0)
        created = df.get("number_of_created_contracts", 0)
        erc20_tx = df.get("total_erc20_tnxs", 0)
        looped = df.get("looped", 0)

        df["h_value_in"] = total_in
        df["h_value_out"] = total_out
        df["h_net_flow"] = total_in - total_out
        df["h_value_to_contracts"] = total_to_contracts

        df["h_tx_in_count"] = tx_in
        df["h_tx_out_count"] = tx_out
        df["h_tx_count"] = tx_total

        df["h_counterparties"] = counter_in + counter_out
        df["h_cp_per_tx"] = df["h_counterparties"] / np.maximum(tx_total, 1)
        df["h_self_dealing"] = (looped > 0).astype(float)

        df["h_value_per_cp"] = (total_in + total_out) / np.maximum(df["h_counterparties"], 1)
        df["h_value_per_tx"] = (total_in + total_out) / np.maximum(tx_total, 1)
        df["h_complexity"] = np.log1p(created + erc20_tx + tx_total)
        df["h_temporal_span"] = temporal_span
        df["h_tx_frequency"] = tx_total / np.maximum(temporal_span, 1)

    aligned = pd.DataFrame(0.0, index=df.index, columns=features)
    for col in features:
        if col in df.columns:
            aligned[col] = df[col]
    aligned = aligned.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    scores = _predict(model_name, model, aligned)
    labels = (scores >= threshold).astype(np.int32)
    risk_levels = np.where(labels == 1, "HIGH", "LOW")

    df = df.copy()
    df["teacher_model"] = model_name
    df["teacher_score"] = scores
    df["teacher_threshold"] = float(threshold)
    df["teacher_fraud"] = labels
    df["teacher_risk_level"] = risk_levels

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Relabel ETH dataset with TeacherAM")
    parser.add_argument(
        "--input",
        default=r"C:\Users\Administrator\Desktop\datasetAMTTP\ethereum_clean.parquet",
    )
    parser.add_argument(
        "--output",
        default=r"C:\amttp\automation\labelled_eth.parquet",
    )
    parser.add_argument(
        "--schema",
        default=r"C:\amttp\ml\Automation\TeacherAM\metadata\feature_schema.json",
    )
    parser.add_argument(
        "--models-dir",
        default=r"C:\amttp\ml\Automation\TeacherAM\models",
    )
    parser.add_argument(
        "--model-comp",
        default=r"C:\amttp\ml\Automation\TeacherAM\metadata\model_comparison.csv",
    )
    args = parser.parse_args()

    relabel_dataset(
        input_path=Path(args.input),
        output_path=Path(args.output),
        schema_path=Path(args.schema),
        models_dir=Path(args.models_dir),
        model_comp_path=Path(args.model_comp),
    )


if __name__ == "__main__":
    main()
