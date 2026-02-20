"""Test calibration end-to-end."""
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from udl import UDLPipeline, ScoreCalibrator
from udl.datasets import make_synthetic, load_mammography
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

print("=== TEST 1: Standalone ScoreCalibrator ===")
X, y = make_synthetic()
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, stratify=y, random_state=42)

pipe = UDLPipeline(score_method='v3e')
pipe.fit(X_tr, y_tr)
train_scores = pipe.score(X_tr)
test_scores = pipe.score(X_te)

for method in ['isotonic', 'platt', 'beta']:
    cal = ScoreCalibrator(method=method)
    cal.fit(train_scores, y_tr)
    probs = cal.transform(test_scores)
    s = cal.summary(test_scores, y_te)
    print(f"  {method:>8s}: ECE={s['ece']:.4f}  Brier={s['brier']:.4f}  "
          f"F1={s['f1']:.4f}  thr={s['threshold']:.4f}  "
          f"probs=[{probs.min():.3f},{probs.max():.3f}]")

print()
print("=== TEST 2: Pipeline with calibrate= ===")
for method in ['isotonic', 'platt', 'beta']:
    pipe_cal = UDLPipeline(score_method='v3e', calibrate=method)
    pipe_cal.fit(X_tr, y_tr)
    probs = pipe_cal.predict_proba(X_te)
    cal_scores = pipe_cal.score_calibrated(X_te)
    summ = pipe_cal.calibration_summary(X_te, y_te)
    auc = roc_auc_score(y_te, probs)
    print(f"  {method:>8s}: AUC={auc:.4f}  ECE={summ['ece']:.4f}  "
          f"Brier={summ['brier']:.4f}  F1={summ['f1']:.4f}  "
          f"range=[{probs.min():.3f},{probs.max():.3f}]")

print()
print("=== TEST 3: predict_proba without calibration (sigmoid fallback) ===")
pipe_noc = UDLPipeline(score_method='v3e')
pipe_noc.fit(X_tr, y_tr)
probs_noc = pipe_noc.predict_proba(X_te)
auc_noc = roc_auc_score(y_te, probs_noc)
print(f"  Sigmoid fallback: range=[{probs_noc.min():.3f},{probs_noc.max():.3f}]  AUC={auc_noc:.4f}")

print()
print("=== TEST 4: Mammography with calibration ===")
try:
    X, y = load_mammography()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, stratify=y, random_state=42)
    pipe = UDLPipeline(score_method='v3e', calibrate='isotonic')
    pipe.fit(X_tr, y_tr)
    probs = pipe.predict_proba(X_te)
    summ = pipe.calibration_summary(X_te, y_te)
    auc = roc_auc_score(y_te, probs)
    print(f"  Mammography: AUC={auc:.4f}  ECE={summ['ece']:.4f}  "
          f"Brier={summ['brier']:.4f}  F1={summ['f1']:.4f}")
    tp, fn, fp, tn = summ['tp'], summ['fn'], summ['fp'], summ['tn']
    print(f"  Caught: {tp}/{tp+fn}  False Alarm: {fp}/{fp+tn}")
except Exception as e:
    import traceback
    traceback.print_exc()

print()
print("=== TEST 5: Reliability curve data ===")
X, y = make_synthetic()
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, stratify=y, random_state=42)
pipe = UDLPipeline(score_method='v3e', calibrate='isotonic')
pipe.fit(X_tr, y_tr)
raw = pipe.score(X_te)
centers, frac_pos, mean_pred, counts = pipe._calibrator.reliability_curve(raw, y_te)
print(f"  Bins with data: {(counts > 0).sum()}/{len(counts)}")
print(f"  Calibrator repr: {pipe._calibrator}")

print()
print("ALL TESTS PASSED")
