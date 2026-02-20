"""
False Positive / False Negative Analysis for QDA-Magnified
"""
import sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, r'c:\amttp')
import numpy as np
from udl.pipeline import UDLPipeline
from udl.datasets import load_mammography, load_shuttle
from sklearn.model_selection import train_test_split
from sklearn.metrics import (roc_auc_score, confusion_matrix, f1_score)

def make_synthetic(n_normal=1000, n_anomaly=50, n_features=10, seed=42):
    rng = np.random.RandomState(seed)
    X_n = rng.randn(n_normal, n_features)
    X_a = rng.randn(n_anomaly, n_features) + 4.0
    return np.vstack([X_n, X_a]), np.concatenate([np.zeros(n_normal), np.ones(n_anomaly)])

def make_mimic(n_normal=1000, n_anomaly=50, n_features=10, seed=42):
    rng = np.random.RandomState(seed)
    X_n = rng.randn(n_normal, n_features)
    X_a = rng.randn(n_anomaly, n_features)
    X_a[:, 5:] += 4.0
    return np.vstack([X_n, X_a]), np.concatenate([np.zeros(n_normal), np.ones(n_anomaly)])

all_ds = [
    ('synthetic', make_synthetic),
    ('mimic', make_mimic),
    ('mammography', load_mammography),
    ('shuttle', load_shuttle),
]

SEP = "-" * 60

print("=" * 80)
print("  FALSE POSITIVE / FALSE NEGATIVE ANALYSIS  -  QDA-MAGNIFIED")
print("=" * 80)

for ds_name, loader in all_ds:
    X, y = loader()
    if ds_name == 'shuttle' and len(X) > 15000:
        rng = np.random.RandomState(42)
        idx = rng.choice(len(X), 10000, replace=False)
        X, y = X[idx], y[idx]

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )

    p = UDLPipeline(projection_method='qda-magnified')
    # Suppress magnifier verbose output
    if p.magnifier_ is not None:
        p.magnifier_.verbose = False
    p.fit(X_tr, y_tr)
    preds = p.predict(X_te)

    R_te = p.transform(X_te)
    R_mag = p.magnifier_.magnify(R_te)
    _, scores = p.projector.classify(R_mag, return_scores=True)
    auc = roc_auc_score(y_te, scores)

    tn, fp, fn, tp = confusion_matrix(y_te, preds).ravel()
    total = len(y_te)
    n_normal = int((y_te == 0).sum())
    n_anomaly = int((y_te == 1).sum())

    fpr = fp / n_normal * 100 if n_normal > 0 else 0
    fnr = fn / n_anomaly * 100 if n_anomaly > 0 else 0
    tpr = tp / n_anomaly * 100 if n_anomaly > 0 else 0
    tnr = tn / n_normal * 100 if n_normal > 0 else 0
    prec = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
    acc = (tp + tn) / total * 100
    right = tp + tn
    wrong = fp + fn

    print(f"\n  DATASET: {ds_name.upper()}")
    print(f"  Test set: {total} samples ({n_normal} normal, {n_anomaly} anomalies)")
    print(f"  AUC-ROC: {auc:.4f}")
    print()
    print(f"  Confusion Matrix:")
    print(f"                    Predicted Normal  Predicted Anomaly")
    print(f"  Actual Normal:    {tn:>8d} (TN)      {fp:>8d} (FP)")
    print(f"  Actual Anomaly:   {fn:>8d} (FN)      {tp:>8d} (TP)")
    print()
    print(f"  RIGHT CALLS: {right}/{total} ({acc:.1f}%)")
    print(f"  WRONG CALLS: {wrong}/{total} ({100-acc:.1f}%)")
    print(f"    - False Positives (normal called anomaly): {fp}/{n_normal} ({fpr:.2f}%)")
    print(f"    - False Negatives (anomaly called normal): {fn}/{n_anomaly} ({fnr:.2f}%)")
    print()
    print(f"  True Positive Rate  (anomalies caught):     {tp}/{n_anomaly} ({tpr:.1f}%)")
    print(f"  True Negative Rate  (normals correct):      {tn}/{n_normal} ({tnr:.1f}%)")
    print(f"  Precision (of flagged, how many are real):   {prec:.1f}%")
    print(f"  F1 Score:                                   {f1_score(y_te, preds):.4f}")
    print(f"  {SEP}")

print()
print("=" * 80)
