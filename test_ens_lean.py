"""Lean ensemble test - mammography only, key combos."""
import sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, r'c:\amttp')
import numpy as np
from udl.pipeline import UDLPipeline
from udl.datasets import load_mammography
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, f1_score, roc_auc_score

X, y = load_mammography()
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)
n_normal = int((y_te == 0).sum())
n_anomaly = int((y_te == 1).sum())

configs = [
    ("QDA-Mag BASELINE (cost=1)",    dict(projection_method='qda-magnified', cost_ratio=1.0)),
    ("QDA-Mag BASELINE (cost=10)",   dict(projection_method='qda-magnified', cost_ratio=10.0)),
    ("quadratic + stack (cost=1)",   dict(projection_method='qda-magnified', mfls_method='quadratic', ensemble='stack', cost_ratio=1.0)),
    ("quadratic + stack (cost=10)",  dict(projection_method='qda-magnified', mfls_method='quadratic', ensemble='stack', cost_ratio=10.0)),
    ("quadratic + max_f1 (cost=1)",  dict(projection_method='qda-magnified', mfls_method='quadratic', ensemble='max_f1', cost_ratio=1.0)),
    ("quadratic + max_f1 (cost=10)", dict(projection_method='qda-magnified', mfls_method='quadratic', ensemble='max_f1', cost_ratio=10.0)),
    ("logistic + stack (cost=1)",    dict(projection_method='qda-magnified', mfls_method='logistic', ensemble='stack', cost_ratio=1.0)),
    ("logistic + stack (cost=10)",   dict(projection_method='qda-magnified', mfls_method='logistic', ensemble='stack', cost_ratio=10.0)),
    ("quad_smooth + stack (cost=1)", dict(projection_method='qda-magnified', mfls_method='quadratic_smooth', ensemble='stack', cost_ratio=1.0)),
    ("quad_smooth + stack (cost=10)",dict(projection_method='qda-magnified', mfls_method='quadratic_smooth', ensemble='stack', cost_ratio=10.0)),
]

print("MAMMOGRAPHY ENSEMBLE RESULTS")
print(f"Test: {len(y_te)} samples, {n_anomaly} anomalies ({n_anomaly/len(y_te)*100:.1f}%)")
print(f"{'Config':<38s} {'FN':>3} {'FP':>4} {'FNR':>7} {'FPR':>7} {'Prec':>6} {'F1':>7} {'Acc':>6}")
print("-" * 90)

for label, kw in configs:
    try:
        p = UDLPipeline(**kw)
        if p.magnifier_ is not None:
            p.magnifier_.verbose = False
        p.fit(X_tr, y_tr)
        preds = p.predict(X_te)
        probs = p.predict_proba(X_te)
        tn, fp, fn, tp = confusion_matrix(y_te, preds).ravel()
        f1 = f1_score(y_te, preds)
        prec = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
        fnr = fn / n_anomaly * 100
        fpr = fp / n_normal * 100
        acc = (tp + tn) / len(y_te) * 100
        print(f"{label:<38s} {fn:>3d} {fp:>4d} {fnr:>6.1f}% {fpr:>6.2f}% {prec:>5.1f}% {f1:>7.4f} {acc:>5.1f}%", flush=True)
    except Exception as e:
        print(f"{label:<38s} ERROR: {e}", flush=True)

print("\nDONE")
