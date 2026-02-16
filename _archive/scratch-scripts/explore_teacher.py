"""Explore teacher scores and label derivation for proper evaluation setup."""
import pandas as pd
import numpy as np

df = pd.read_parquet('processed/eth_addresses_labeled.parquet')

print("=== DATASET COLUMNS ===")
for c in df.columns:
    print(f"  {c}: dtype={df[c].dtype}")

print(f"\n=== FRAUD LABEL ===")
print(df['fraud'].value_counts().to_dict())

print(f"\n=== RISK LEVEL vs FRAUD ===")
print(pd.crosstab(df['risk_level'], df['fraud']))

print(f"\n=== RISK CLASS vs FRAUD ===")
print(pd.crosstab(df['risk_class'], df['fraud']))

fraud = df[df['fraud'] == 1]
clean = df[df['fraud'] == 0]

print(f"\n=== TEACHER XGB RAW SCORE ===")
xgb = df['xgb_raw_score']
print(f"  Overall: min={xgb.min():.6f}, max={xgb.max():.6f}, mean={xgb.mean():.6f}")
print(f"  Fraud (n={len(fraud)}): min={fraud['xgb_raw_score'].min():.6f}, max={fraud['xgb_raw_score'].max():.6f}, mean={fraud['xgb_raw_score'].mean():.6f}, median={fraud['xgb_raw_score'].median():.6f}")
print(f"  Clean (n={len(clean)}): min={clean['xgb_raw_score'].min():.6f}, max={clean['xgb_raw_score'].max():.6f}, mean={clean['xgb_raw_score'].mean():.6f}, median={clean['xgb_raw_score'].median():.6f}")

print(f"\n=== XGB NORMALIZED ===")
xn = df['xgb_normalized']
print(f"  Overall: min={xn.min():.6f}, max={xn.max():.6f}")
print(f"  Fraud: min={fraud['xgb_normalized'].min():.6f}, max={fraud['xgb_normalized'].max():.6f}, mean={fraud['xgb_normalized'].mean():.6f}")
print(f"  Clean: min={clean['xgb_normalized'].min():.6f}, max={clean['xgb_normalized'].max():.6f}, mean={clean['xgb_normalized'].mean():.6f}")

print(f"\n=== HYBRID SCORE (Teacher Full Stack) ===")
hs = df['hybrid_score']
print(f"  Overall: min={hs.min():.6f}, max={hs.max():.6f}, mean={hs.mean():.6f}")
print(f"  Fraud: min={fraud['hybrid_score'].min():.6f}, max={fraud['hybrid_score'].max():.6f}, mean={fraud['hybrid_score'].mean():.6f}")
print(f"  Clean: min={clean['hybrid_score'].min():.6f}, max={clean['hybrid_score'].max():.6f}, mean={clean['hybrid_score'].mean():.6f}")

print(f"\n=== PATTERN BOOST & SOPH NORMALIZED ===")
print(f"  pattern_boost: min={df['pattern_boost'].min():.6f}, max={df['pattern_boost'].max():.6f}, mean={df['pattern_boost'].mean():.6f}")
print(f"  soph_normalized: min={df['soph_normalized'].min():.6f}, max={df['soph_normalized'].max():.6f}, mean={df['soph_normalized'].mean():.6f}")

print(f"\n=== HYBRID FORMULA CHECK ===")
recon = 0.4 * df['xgb_normalized'] + 0.3 * df['pattern_boost'] + 0.3 * df['soph_normalized']
diff = (recon - df['hybrid_score']).abs()
print(f"  Reconstructed vs actual diff: max={diff.max():.8f}, mean={diff.mean():.8f}")

# Check how fraud label was derived from risk_level
print(f"\n=== RISK_LEVEL THRESHOLDS ===")
for rl in df['risk_level'].unique():
    subset = df[df['risk_level'] == rl]
    print(f"  {rl}: n={len(subset)}, hybrid_score range=[{subset['hybrid_score'].min():.6f}, {subset['hybrid_score'].max():.6f}], fraud count={subset['fraud'].sum()}")

# Find optimal XGB threshold
from sklearn.metrics import precision_recall_curve, f1_score, roc_auc_score
y_true = df['fraud'].values
xgb_scores = df['xgb_raw_score'].values

print(f"\n=== TEACHER XGB RECALIBRATION ===")
print(f"  ROC-AUC: {roc_auc_score(y_true, xgb_scores):.6f}")

precisions, recalls, thresholds = precision_recall_curve(y_true, xgb_scores)
f1s = 2 * precisions * recalls / (precisions + recalls + 1e-10)
best_idx = np.argmax(f1s)
best_thresh = thresholds[best_idx] if best_idx < len(thresholds) else 0.5
best_f1 = f1s[best_idx]
print(f"  Optimal F1 threshold: {best_thresh:.6f}")
print(f"  Optimal F1 score: {best_f1:.6f}")

# At optimal threshold
preds_opt = (xgb_scores >= best_thresh).astype(int)
tp = ((preds_opt == 1) & (y_true == 1)).sum()
fp = ((preds_opt == 1) & (y_true == 0)).sum()
fn = ((preds_opt == 0) & (y_true == 1)).sum()
tn = ((preds_opt == 0) & (y_true == 0)).sum()
print(f"  At optimal threshold: TP={tp}, FP={fp}, FN={fn}, TN={tn}")
print(f"  Precision={tp/(tp+fp+1e-10):.4f}, Recall={tp/(tp+fn+1e-10):.4f}")

# Also check xgb_normalized
print(f"\n=== TEACHER XGB NORMALIZED RECALIBRATION ===")
xn_scores = df['xgb_normalized'].values
print(f"  ROC-AUC: {roc_auc_score(y_true, xn_scores):.6f}")
precisions2, recalls2, thresholds2 = precision_recall_curve(y_true, xn_scores)
f1s2 = 2 * precisions2 * recalls2 / (precisions2 + recalls2 + 1e-10)
best_idx2 = np.argmax(f1s2)
best_thresh2 = thresholds2[best_idx2] if best_idx2 < len(thresholds2) else 0.5
print(f"  Optimal F1 threshold: {best_thresh2:.6f}")
print(f"  Optimal F1 score: {f1s2[best_idx2]:.6f}")

# Also calibrate hybrid_score
print(f"\n=== TEACHER HYBRID SCORE RECALIBRATION ===")
hs_scores = df['hybrid_score'].values
print(f"  ROC-AUC: {roc_auc_score(y_true, hs_scores):.6f}")
precisions3, recalls3, thresholds3 = precision_recall_curve(y_true, hs_scores)
f1s3 = 2 * precisions3 * recalls3 / (precisions3 + recalls3 + 1e-10)
best_idx3 = np.argmax(f1s3)
best_thresh3 = thresholds3[best_idx3] if best_idx3 < len(thresholds3) else 0.5
print(f"  Optimal F1 threshold: {best_thresh3:.6f}")
print(f"  Optimal F1 score: {f1s3[best_idx3]:.6f}")
preds_hs = (hs_scores >= best_thresh3).astype(int)
tp3 = ((preds_hs == 1) & (y_true == 1)).sum()
fp3 = ((preds_hs == 1) & (y_true == 0)).sum()
fn3 = ((preds_hs == 0) & (y_true == 1)).sum()
print(f"  At optimal threshold: TP={tp3}, FP={fp3}, FN={fn3}")

# Check percentiles of xgb_raw_score for fraud vs clean
print(f"\n=== XGB RAW SCORE PERCENTILES ===")
for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
    print(f"  p{p}: fraud={np.percentile(fraud['xgb_raw_score'], p):.6f}, clean={np.percentile(clean['xgb_raw_score'], p):.6f}")
