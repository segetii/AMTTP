"""FP/FN for shuttle only"""
import sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, r'c:\amttp')
import numpy as np
from udl.pipeline import UDLPipeline
from udl.datasets import load_shuttle
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, confusion_matrix, f1_score

X, y = load_shuttle()
rng = np.random.RandomState(42)
idx = rng.choice(len(X), 10000, replace=False)
X, y = X[idx], y[idx]

X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)

p = UDLPipeline(projection_method='qda-magnified')
if p.magnifier_ is not None:
    p.magnifier_.verbose = False
print("Fitting...", flush=True)
p.fit(X_tr, y_tr)
print("Predicting...", flush=True)
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

print(f"\n  DATASET: SHUTTLE")
print(f"  Test set: {total} samples ({n_normal} normal, {n_anomaly} anomalies)")
print(f"  AUC-ROC: {auc:.4f}")
print(f"\n  Confusion Matrix:")
print(f"                    Predicted Normal  Predicted Anomaly")
print(f"  Actual Normal:    {tn:>8d} (TN)      {fp:>8d} (FP)")
print(f"  Actual Anomaly:   {fn:>8d} (FN)      {tp:>8d} (TP)")
print(f"\n  RIGHT CALLS: {right}/{total} ({acc:.1f}%)")
print(f"  WRONG CALLS: {wrong}/{total} ({100-acc:.1f}%)")
print(f"    - False Positives (normal called anomaly): {fp}/{n_normal} ({fpr:.2f}%)")
print(f"    - False Negatives (anomaly called normal): {fn}/{n_anomaly} ({fnr:.2f}%)")
print(f"\n  True Positive Rate  (anomalies caught):     {tp}/{n_anomaly} ({tpr:.1f}%)")
print(f"  True Negative Rate  (normals correct):      {tn}/{n_normal} ({tnr:.1f}%)")
print(f"  Precision (of flagged, how many are real):   {prec:.1f}%")
print(f"  F1 Score:                                   {f1_score(y_te, preds):.4f}")
