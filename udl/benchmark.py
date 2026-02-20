"""
UDL Benchmark — Validate Universal Deviation Law pipeline
on synthetic + real-world datasets.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score

from udl import UDLPipeline, load_dataset, list_datasets

np.random.seed(42)

def benchmark_dataset(name, X, y, verbose=True):
    """Run UDL pipeline on a single dataset and return metrics."""
    # Train/test split (80/20 stratified)
    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=42
    )

    # Fit pipeline
    pipe = UDLPipeline(
        centroid_method="auto",
        projection_method="fisher",
        exp_alpha=1.0,
        score_weights=(0.7, 0.3),
    )
    pipe.fit(X_train, y_train)

    # Score + predict
    scores = pipe.score(X_test)
    labels = pipe.predict(X_test)

    # Metrics
    auc = roc_auc_score(y_test, scores)
    f1 = f1_score(y_test, labels, zero_division=0)
    prec = precision_score(y_test, labels, zero_division=0)
    rec = recall_score(y_test, labels, zero_division=0)

    # Diagnostics
    diag = pipe.get_diagnostics()

    if verbose:
        print(f"\n{'='*60}")
        print(f"  Dataset: {name}")
        print(f"  Samples: {len(X)} (train={len(X_train)}, test={len(X_test)})")
        print(f"  Features: {X.shape[1]}")
        print(f"  Anomaly rate: {y.mean():.1%}")
        print(f"  Representation dim: {diag['total_representation_dim']}")
        print(f"  Law dims: {dict(zip(diag['law_names'], diag['law_dims']))}")
        print(f"  Centroid: {diag['centroid_method']}")
        print(f"  ──────────────────────────")
        print(f"  AUC-ROC:   {auc:.4f}")
        print(f"  F1 Score:  {f1:.4f}")
        print(f"  Precision: {prec:.4f}")
        print(f"  Recall:    {rec:.4f}")
        print(f"{'='*60}")

    return {"name": name, "auc": auc, "f1": f1, "precision": prec,
            "recall": rec, "n_samples": len(X), "n_features": X.shape[1]}


def main():
    print("=" * 60)
    print("  UNIVERSAL DEVIATION LAW — Benchmark Validation")
    print("  Pipeline: Raw → Stack → Centroid → Tensor → Projection")
    print("=" * 60)

    results = []

    # Synthetic datasets
    for ds_name in ["synthetic", "mimic"]:
        X, y = load_dataset(ds_name)
        r = benchmark_dataset(ds_name, X, y)
        results.append(r)

    # Summary
    print("\n\n" + "=" * 60)
    print("  SUMMARY — Cross-Domain Results")
    print("=" * 60)
    print(f"  {'Dataset':<20} {'AUC':>8} {'F1':>8} {'Prec':>8} {'Rec':>8}")
    print(f"  {'─'*20} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
    for r in results:
        print(f"  {r['name']:<20} {r['auc']:>8.4f} {r['f1']:>8.4f} "
              f"{r['precision']:>8.4f} {r['recall']:>8.4f}")

    avg_auc = np.mean([r["auc"] for r in results])
    print(f"\n  Average AUC: {avg_auc:.4f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
