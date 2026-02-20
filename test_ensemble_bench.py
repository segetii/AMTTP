"""
MFLS + QDA Ensemble Test
=========================
Compares standalone QDA-Magnified vs stacked with MFLS Quadratic.
Tests all 3 ensemble modes: stack, product, max_f1.
Tests key MFLS methods: quadratic, quadratic_smooth, logistic.
"""
import sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, r'c:\amttp')
import numpy as np
from udl.pipeline import UDLPipeline
from udl.datasets import load_mammography, load_shuttle
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, f1_score, roc_auc_score

def run_config(label, X_tr, X_te, y_tr, y_te, **kwargs):
    p = UDLPipeline(**kwargs)
    if p.magnifier_ is not None:
        p.magnifier_.verbose = False
    p.fit(X_tr, y_tr)
    preds = p.predict(X_te)
    probs = p.predict_proba(X_te)

    tn, fp, fn, tp = confusion_matrix(y_te, preds).ravel()
    n_normal = int((y_te == 0).sum())
    n_anomaly = int((y_te == 1).sum())
    f1 = f1_score(y_te, preds)
    auc = roc_auc_score(y_te, probs)
    prec = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
    fnr = fn / n_anomaly * 100 if n_anomaly else 0
    fpr = fp / n_normal * 100 if n_normal else 0
    acc = (tp + tn) / len(y_te) * 100

    thr_info = ""
    if hasattr(p, '_ensemble_threshold') and p._ensemble_threshold != 0.5:
        thr_info = f" thr={p._ensemble_threshold:.4f}"
    elif hasattr(p, 'projector') and hasattr(p.projector, 'threshold_'):
        thr_info = f" thr={p.projector.threshold_:.4f}"

    print(f"  {label:<44s} FN={fn:>2d} FP={fp:>3d} FNR={fnr:>6.2f}% FPR={fpr:>6.2f}% Prec={prec:>5.1f}% F1={f1:.4f} Acc={acc:.1f}%{thr_info}")
    return {"f1": f1, "fnr": fnr, "fpr": fpr, "prec": prec, "acc": acc, "auc": auc,
            "tp": tp, "tn": tn, "fp": fp, "fn": fn}


print("=" * 120)
print("  MFLS + QDA-MAGNIFIED ENSEMBLE STACKING TEST")
print("=" * 120)

# Only test mammography first (the hard dataset)
X, y = load_mammography()
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)
n_anomaly = int((y_te == 1).sum())

print(f"\n  MAMMOGRAPHY ({len(X_te)} test, {n_anomaly} anomalies, {n_anomaly/len(y_te)*100:.1f}% rate)")
print(f"  {'='*116}")

# Baselines
print("\n  --- BASELINES (no ensemble) ---")
run_config("QDA-Mag alone (cost=1)", X_tr, X_te, y_tr, y_te,
           projection_method='qda-magnified', cost_ratio=1.0)
run_config("QDA-Mag alone (cost=10)", X_tr, X_te, y_tr, y_te,
           projection_method='qda-magnified', cost_ratio=10.0)

# Ensemble combos
print("\n  --- MFLS QUADRATIC + QDA-MAG ENSEMBLE ---")
for ens in ['stack', 'product', 'max_f1']:
    run_config(f"quadratic + {ens} (cost=1)", X_tr, X_te, y_tr, y_te,
               projection_method='qda-magnified', mfls_method='quadratic',
               ensemble=ens, cost_ratio=1.0)

print("\n  --- MFLS QUADRATIC_SMOOTH + QDA-MAG ENSEMBLE ---")
for ens in ['stack', 'product', 'max_f1']:
    run_config(f"quadratic_smooth + {ens} (cost=1)", X_tr, X_te, y_tr, y_te,
               projection_method='qda-magnified', mfls_method='quadratic_smooth',
               ensemble=ens, cost_ratio=1.0)

print("\n  --- MFLS LOGISTIC + QDA-MAG ENSEMBLE ---")
for ens in ['stack', 'product', 'max_f1']:
    run_config(f"logistic + {ens} (cost=1)", X_tr, X_te, y_tr, y_te,
               projection_method='qda-magnified', mfls_method='logistic',
               ensemble=ens, cost_ratio=1.0)

print("\n  --- BEST COMBOS WITH COST-SENSITIVE ---")
for mfls in ['quadratic', 'quadratic_smooth', 'logistic']:
    for ens in ['stack', 'max_f1']:
        for cost in [10.0]:
            run_config(f"{mfls} + {ens} (cost={cost:.0f})", X_tr, X_te, y_tr, y_te,
                       projection_method='qda-magnified', mfls_method=mfls,
                       ensemble=ens, cost_ratio=cost)

print(f"\n{'='*120}")
print("  DONE")
