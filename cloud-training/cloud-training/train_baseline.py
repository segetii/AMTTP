import argparse
import json
import os
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder
import joblib

DEFAULT_MODEL_DIR = Path(os.getenv("MODEL_DIR", "/app/models/cloud"))
DEFAULT_MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = DEFAULT_MODEL_DIR / "baseline_model.joblib"
META_PATH = DEFAULT_MODEL_DIR / "baseline_model_meta.json"


def load_data(path: Optional[str]) -> pd.DataFrame:
    if path and Path(path).exists():
        ext = Path(path).suffix.lower()
        if ext in (".csv", ".txt"):
            return pd.read_csv(path)
        elif ext in (".parquet", ".pq"):
            return pd.read_parquet(path)
        else:
            raise ValueError(f"Unsupported data extension: {ext}")
    # Generate a small synthetic binary classification dataset as a fallback
    rng = np.random.RandomState(42)
    n = 5000
    X = pd.DataFrame(
        {
            "amount": np.exp(rng.normal(5, 1, n)),
            "hour": rng.randint(0, 24, n),
            "day_of_week": rng.randint(0, 7, n),
            "country_risk": rng.beta(2, 5, n),
            "velocity_1h": rng.poisson(1.2, n),
            "velocity_24h": rng.poisson(4.5, n),
            "account_age_days": rng.randint(0, 365, n),
            "merchant_category": rng.choice(["online", "pos", "card_present"], n, p=[0.45, 0.4, 0.15]),
        }
    )
    # Fraud label with some signal
    y = (
        (np.log1p(X["amount"]) > 4.5).astype(int)
        + (X["hour"].isin([0, 1, 2, 3, 23])).astype(int)
        + (X["merchant_category"] == "online").astype(int)
        + (X["country_risk"] > 0.6).astype(int)
        + (X["account_age_days"] < 14).astype(int)
    )
    y = (y >= 2).astype(int)
    X["label"] = y
    return X


def train_and_save(df: pd.DataFrame, label_col: str = "label") -> dict:
    assert label_col in df.columns, f"Label column '{label_col}' not found"
    y = df[label_col].astype(int).values
    X = df.drop(columns=[label_col])

    # Split columns by type
    numeric_features = X.select_dtypes(include=[np.number]).columns.tolist()
    categorical_features = X.select_dtypes(exclude=[np.number]).columns.tolist()

    numeric_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    categorical_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, numeric_features),
            ("cat", categorical_transformer, categorical_features),
        ]
    )

    model = LogisticRegression(max_iter=1000, n_jobs=None)

    clf = Pipeline(steps=[("preprocessor", preprocessor), ("clf", model)])

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    clf.fit(X_train, y_train)

    y_prob = clf.predict_proba(X_val)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    metrics = {
        "auc": float(roc_auc_score(y_val, y_prob)),
        "f1": float(f1_score(y_val, y_pred)),
        "accuracy": float(accuracy_score(y_val, y_pred)),
        "n_train": int(len(X_train)),
        "n_val": int(len(X_val)),
    }

    # Persist
    joblib.dump(clf, MODEL_PATH)
    meta = {
        "label_col": label_col,
        "numeric_features": numeric_features,
        "categorical_features": categorical_features,
        "metrics": metrics,
    }
    META_PATH.write_text(json.dumps(meta, indent=2))

    return metrics


def main():
    parser = argparse.ArgumentParser(description="Train baseline sklearn model")
    parser.add_argument("--data", dest="data_path", default=os.getenv("TRAIN_DATA_PATH"), help="Path to CSV/Parquet with label column 'label'. If omitted, synthetic data is used.")
    args = parser.parse_args()

    df = load_data(args.data_path)
    metrics = train_and_save(df)
    print(json.dumps({"model_path": str(MODEL_PATH), **metrics}, indent=2))


if __name__ == "__main__":
    main()
