"""
AMTTP - Teacher vs Student Model Evaluation
============================================
Teacher: VAE/GNN Pipeline (BetaVAE + VGAE + GATv2 + GraphSAGE + XGB + LGBM + LogisticRegressionCV meta)
Student: Stacked Ensemble (XGBoost + LightGBM + LogisticRegression meta-learner)

Dataset: eth_addresses_labeled.parquet (625K addresses)
  - Features: 23 numerical address features from BigQuery
  - Labels: teacher-generated `fraud` column (372 fraud / 624796 clean)

Workflow:
  1. Load dataset + teacher predictions
  2. Train student pipeline via stratified K-fold CV (honest evaluation)
  3. Compare teacher vs student on all metrics
"""
import os
import sys
import json
import time
import warnings
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import RobustScaler
from sklearn.linear_model import LogisticRegressionCV
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    roc_auc_score, average_precision_score, f1_score,
    precision_score, recall_score, classification_report,
    roc_curve, precision_recall_curve, confusion_matrix
)

import xgboost as xgb
import lightgbm as lgb

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger(__name__)

# ============================================================
# Paths
# ============================================================
BASE = Path('c:/amttp')
PROCESSED = BASE / 'processed'
TEACHER_DIR = BASE / 'ml' / 'Automation' / 'amttp_models_20251231_174617'
STUDENT_DIR = BASE / 'ml' / 'Automation' / 'ml_pipeline' / 'models' / 'trained'
RESULTS_DIR = BASE / 'ml' / 'evaluation_results'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

N_FOLDS = 5
RANDOM_STATE = 42


def load_data():
    """Load dataset and split features/target."""
    log.info("Loading eth_addresses_labeled.parquet...")
    df = pd.read_parquet(PROCESSED / 'eth_addresses_labeled.parquet')

    # Numerical feature columns (exclude identifiers, text, target, derived scores)
    exclude = {
        'address', 'patterns', 'risk_level', 'fraud', 'risk_class',
        # These are teacher-derived scores - exclude to avoid data leakage
        'sophisticated_score', 'xgb_raw_score', 'xgb_normalized',
        'pattern_boost', 'soph_normalized', 'hybrid_score', 'pattern_count'
    }
    feature_cols = [c for c in df.columns if c not in exclude and df[c].dtype in ('float64', 'float32', 'int64', 'int32')]
    
    X = df[feature_cols].copy()
    y = df['fraud'].values.astype(int)

    # Handle inf/nan
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0)

    log.info(f"Features: {len(feature_cols)} | Samples: {len(X):,} | Fraud: {y.sum():,} ({100*y.mean():.4f}%)")
    log.info(f"Feature names: {feature_cols}")

    return X, y, df['address'], feature_cols


def load_teacher_predictions(addresses):
    """Load existing teacher model predictions and align to address order."""
    log.info("Loading teacher predictions from inference_results/all_predictions.parquet...")
    preds = pd.read_parquet(PROCESSED / 'inference_results' / 'all_predictions.parquet')

    # Merge on address
    merged = pd.DataFrame({'address': addresses}).merge(
        preds[['address', 'risk_score', 'combined_score', 'prediction']],
        on='address', how='left'
    )

    teacher_score = merged['combined_score'].fillna(merged['risk_score']).fillna(0).values
    teacher_pred = merged['prediction'].fillna(0).astype(int).values

    log.info(f"Teacher predictions loaded: {len(preds):,} records, matched {(teacher_score > 0).sum():,}")
    return teacher_score, teacher_pred


def train_student_cv(X, y, feature_cols):
    """
    Train the student pipeline with stratified K-fold cross-validation.

    Student Pipeline:
      Base models: XGBoost, LightGBM
      Meta-learner: LogisticRegressionCV (same as teacher)

    Returns OOF predictions (honest evaluation).
    """
    log.info(f"Training student pipeline ({N_FOLDS}-fold CV)...")

    oof_xgb = np.zeros(len(y))
    oof_lgbm = np.zeros(len(y))
    oof_meta = np.zeros(len(y))
    oof_pred = np.zeros(len(y), dtype=int)

    fold_metrics = []
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)

    for fold_idx, (train_idx, val_idx) in enumerate(skf.split(X, y)):
        t0 = time.time()
        log.info(f"--- Fold {fold_idx+1}/{N_FOLDS} ---")

        X_train, X_val = X.values[train_idx], X.values[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        # Preprocessing: RobustScaler
        scaler = RobustScaler()
        X_train_sc = scaler.fit_transform(X_train)
        X_val_sc = scaler.transform(X_val)

        # Handle class imbalance ratio
        n_pos = y_train.sum()
        n_neg = len(y_train) - n_pos
        scale_pos_weight = n_neg / max(n_pos, 1)
        log.info(f"  Train: {len(y_train):,} (pos={n_pos}, neg={n_neg}, ratio=1:{scale_pos_weight:.0f})")

        # ---- Base Model 1: XGBoost ----
        xgb_model = xgb.XGBClassifier(
            n_estimators=500,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=scale_pos_weight,
            eval_metric='aucpr',
            early_stopping_rounds=30,
            random_state=RANDOM_STATE,
            n_jobs=-1,
            tree_method='hist',
            verbosity=0
        )
        xgb_model.fit(
            X_train_sc, y_train,
            eval_set=[(X_val_sc, y_val)],
            verbose=False
        )
        xgb_proba = xgb_model.predict_proba(X_val_sc)[:, 1]
        xgb_train_proba = xgb_model.predict_proba(X_train_sc)[:, 1]

        # ---- Base Model 2: LightGBM ----
        lgbm_model = lgb.LGBMClassifier(
            n_estimators=500,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=scale_pos_weight,
            metric='average_precision',
            random_state=RANDOM_STATE,
            n_jobs=-1,
            verbose=-1
        )
        lgbm_model.fit(
            X_train_sc, y_train,
            eval_set=[(X_val_sc, y_val)],
            callbacks=[lgb.early_stopping(30, verbose=False)]
        )
        lgbm_proba = lgbm_model.predict_proba(X_val_sc)[:, 1]
        lgbm_train_proba = lgbm_model.predict_proba(X_train_sc)[:, 1]

        # ---- Meta-Learner: LogisticRegressionCV (stacking) ----
        meta_train_X = np.column_stack([xgb_train_proba, lgbm_train_proba])
        meta_val_X = np.column_stack([xgb_proba, lgbm_proba])

        meta_model = LogisticRegressionCV(
            Cs=10,
            cv=3,
            scoring='average_precision',
            class_weight='balanced',
            max_iter=1000,
            random_state=RANDOM_STATE
        )
        meta_model.fit(meta_train_X, y_train)
        meta_proba = meta_model.predict_proba(meta_val_X)[:, 1]

        # Store OOF predictions
        oof_xgb[val_idx] = xgb_proba
        oof_lgbm[val_idx] = lgbm_proba
        oof_meta[val_idx] = meta_proba

        # Fold metrics
        fold_auc = roc_auc_score(y_val, meta_proba)
        fold_pr_auc = average_precision_score(y_val, meta_proba)
        elapsed = time.time() - t0
        log.info(f"  Fold {fold_idx+1}: ROC-AUC={fold_auc:.4f}  PR-AUC={fold_pr_auc:.4f}  ({elapsed:.1f}s)")
        fold_metrics.append({'fold': fold_idx+1, 'roc_auc': fold_auc, 'pr_auc': fold_pr_auc, 'time_s': elapsed})

    # Find optimal threshold via F1
    precisions, recalls, thresholds_pr = precision_recall_curve(y, oof_meta)
    f1_scores = 2 * precisions * recalls / (precisions + recalls + 1e-8)
    best_f1_idx = np.argmax(f1_scores)
    optimal_threshold = thresholds_pr[best_f1_idx] if best_f1_idx < len(thresholds_pr) else 0.5
    oof_pred = (oof_meta >= optimal_threshold).astype(int)

    log.info(f"Optimal threshold (max F1): {optimal_threshold:.4f}")
    log.info(f"Fold averages: ROC-AUC={np.mean([m['roc_auc'] for m in fold_metrics]):.4f}, "
             f"PR-AUC={np.mean([m['pr_auc'] for m in fold_metrics]):.4f}")

    return oof_xgb, oof_lgbm, oof_meta, oof_pred, optimal_threshold, fold_metrics


def compute_metrics(y_true, y_score, y_pred, label):
    """Compute full metric suite."""
    metrics = {
        'model': label,
        'roc_auc': roc_auc_score(y_true, y_score),
        'pr_auc': average_precision_score(y_true, y_score),
        'f1': f1_score(y_true, y_pred),
        'precision': precision_score(y_true, y_pred, zero_division=0),
        'recall': recall_score(y_true, y_pred, zero_division=0),
        'true_positives': int(((y_pred == 1) & (y_true == 1)).sum()),
        'false_positives': int(((y_pred == 1) & (y_true == 0)).sum()),
        'false_negatives': int(((y_pred == 0) & (y_true == 1)).sum()),
        'true_negatives': int(((y_pred == 0) & (y_true == 0)).sum()),
        'predicted_positive': int(y_pred.sum()),
        'actual_positive': int(y_true.sum()),
    }
    return metrics


def find_optimal_threshold(y_true, y_score):
    """Find threshold maximizing F1."""
    prec, rec, thresholds = precision_recall_curve(y_true, y_score)
    f1s = 2 * prec * rec / (prec + rec + 1e-8)
    idx = np.argmax(f1s)
    return thresholds[idx] if idx < len(thresholds) else 0.5


def plot_comparison(y, teacher_score, teacher_pred, student_score, student_pred, save_path):
    """Generate comparison plots."""
    fig = plt.figure(figsize=(20, 16))
    fig.suptitle('AMTTP Teacher vs Student Model Comparison', fontsize=16, fontweight='bold', y=0.98)
    gs = GridSpec(3, 3, figure=fig, hspace=0.35, wspace=0.30)

    # --- ROC Curves ---
    ax1 = fig.add_subplot(gs[0, 0])
    for label, score, color in [('Teacher', teacher_score, '#e74c3c'), ('Student (LR Meta)', student_score, '#2ecc71')]:
        fpr, tpr, _ = roc_curve(y, score)
        auc = roc_auc_score(y, score)
        ax1.plot(fpr, tpr, color=color, lw=2, label=f'{label} (AUC={auc:.4f})')
    ax1.plot([0,1],[0,1], 'k--', alpha=0.3)
    ax1.set_xlabel('FPR'); ax1.set_ylabel('TPR'); ax1.set_title('ROC Curve')
    ax1.legend(fontsize=9); ax1.grid(alpha=0.3)

    # --- PR Curves ---
    ax2 = fig.add_subplot(gs[0, 1])
    for label, score, color in [('Teacher', teacher_score, '#e74c3c'), ('Student (LR Meta)', student_score, '#2ecc71')]:
        prec, rec, _ = precision_recall_curve(y, score)
        ap = average_precision_score(y, score)
        ax2.plot(rec, prec, color=color, lw=2, label=f'{label} (AP={ap:.4f})')
    ax2.set_xlabel('Recall'); ax2.set_ylabel('Precision'); ax2.set_title('Precision-Recall Curve')
    ax2.legend(fontsize=9); ax2.grid(alpha=0.3)

    # --- Score Distributions ---
    ax3 = fig.add_subplot(gs[0, 2])
    for label, score, color in [('Teacher', teacher_score, '#e74c3c'), ('Student', student_score, '#2ecc71')]:
        ax3.hist(score[y==0], bins=100, alpha=0.4, color=color, label=f'{label} (clean)', density=True)
        ax3.hist(score[y==1], bins=50, alpha=0.6, color=color, label=f'{label} (fraud)', density=True, histtype='step', lw=2)
    ax3.set_xlabel('Risk Score'); ax3.set_ylabel('Density'); ax3.set_title('Score Distributions')
    ax3.legend(fontsize=7); ax3.grid(alpha=0.3); ax3.set_xlim(-0.05, 1.05)

    # --- Confusion Matrices ---
    for i, (label, pred, color) in enumerate([
        ('Teacher', teacher_pred, '#e74c3c'),
        ('Student (LR Meta)', student_pred, '#2ecc71')
    ]):
        ax = fig.add_subplot(gs[1, i])
        cm = confusion_matrix(y, pred)
        im = ax.imshow(cm, cmap='Blues', aspect='auto')
        for (j, k), val in np.ndenumerate(cm):
            ax.text(k, j, f'{val:,}', ha='center', va='center', fontsize=12,
                    color='white' if val > cm.max()/2 else 'black')
        ax.set_xticks([0,1]); ax.set_yticks([0,1])
        ax.set_xticklabels(['Pred Clean', 'Pred Fraud'])
        ax.set_yticklabels(['True Clean', 'True Fraud'])
        ax.set_title(f'{label} Confusion Matrix')
        plt.colorbar(im, ax=ax)

    # --- Metrics Summary Bar Chart ---
    ax5 = fig.add_subplot(gs[1, 2])
    metrics_names = ['ROC-AUC', 'PR-AUC', 'F1', 'Precision', 'Recall']
    teacher_vals = [
        roc_auc_score(y, teacher_score), average_precision_score(y, teacher_score),
        f1_score(y, teacher_pred), precision_score(y, teacher_pred, zero_division=0),
        recall_score(y, teacher_pred, zero_division=0)
    ]
    student_vals = [
        roc_auc_score(y, student_score), average_precision_score(y, student_score),
        f1_score(y, student_pred), precision_score(y, student_pred, zero_division=0),
        recall_score(y, student_pred, zero_division=0)
    ]
    x_pos = np.arange(len(metrics_names))
    width = 0.35
    ax5.bar(x_pos - width/2, teacher_vals, width, label='Teacher', color='#e74c3c', alpha=0.8)
    ax5.bar(x_pos + width/2, student_vals, width, label='Student', color='#2ecc71', alpha=0.8)
    ax5.set_xticks(x_pos); ax5.set_xticklabels(metrics_names, rotation=25)
    ax5.set_ylabel('Score'); ax5.set_title('Metrics Comparison')
    ax5.legend(); ax5.grid(alpha=0.3, axis='y'); ax5.set_ylim(0, 1.05)

    # --- Threshold Sensitivity ---
    ax6 = fig.add_subplot(gs[2, 0])
    thresholds = np.linspace(0.01, 0.99, 100)
    for label, score, color in [('Teacher', teacher_score, '#e74c3c'), ('Student', student_score, '#2ecc71')]:
        f1s = [f1_score(y, (score >= t).astype(int), zero_division=0) for t in thresholds]
        ax6.plot(thresholds, f1s, color=color, lw=2, label=label)
    ax6.set_xlabel('Threshold'); ax6.set_ylabel('F1 Score'); ax6.set_title('F1 vs Threshold')
    ax6.legend(); ax6.grid(alpha=0.3)

    # --- Agreement Analysis ---
    ax7 = fig.add_subplot(gs[2, 1])
    agree = (teacher_pred == student_pred).astype(int)
    both_pos = ((teacher_pred == 1) & (student_pred == 1)).sum()
    both_neg = ((teacher_pred == 0) & (student_pred == 0)).sum()
    teacher_only = ((teacher_pred == 1) & (student_pred == 0)).sum()
    student_only = ((teacher_pred == 0) & (student_pred == 1)).sum()
    categories = ['Both\nPositive', 'Both\nNegative', 'Teacher\nOnly', 'Student\nOnly']
    values = [both_pos, both_neg, teacher_only, student_only]
    colors = ['#e74c3c', '#2ecc71', '#f39c12', '#3498db']
    ax7.bar(categories, values, color=colors, alpha=0.8)
    ax7.set_title(f'Prediction Agreement ({100*agree.mean():.1f}% agree)')
    ax7.grid(alpha=0.3, axis='y')
    for i, v in enumerate(values):
        ax7.text(i, v + max(values)*0.01, f'{v:,}', ha='center', fontsize=10)

    # --- Score Correlation ---
    ax8 = fig.add_subplot(gs[2, 2])
    # Subsample for scatter (too many points)
    mask_fraud = y == 1
    mask_clean = np.random.RandomState(42).choice(np.where(y == 0)[0], min(5000, (y==0).sum()), replace=False)
    ax8.scatter(teacher_score[mask_clean], student_score[mask_clean], alpha=0.1, s=3, c='#95a5a6', label='Clean (sample)')
    ax8.scatter(teacher_score[mask_fraud], student_score[mask_fraud], alpha=0.8, s=20, c='#e74c3c', label='Fraud', zorder=5)
    ax8.plot([0,1],[0,1], 'k--', alpha=0.3)
    corr = np.corrcoef(teacher_score, student_score)[0,1]
    ax8.set_xlabel('Teacher Score'); ax8.set_ylabel('Student Score')
    ax8.set_title(f'Score Correlation (r={corr:.4f})')
    ax8.legend(fontsize=9); ax8.grid(alpha=0.3)

    plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
    log.info(f"Plots saved to {save_path}")
    plt.close()


def main():
    t_start = time.time()

    # 1. Load data
    X, y, addresses, feature_cols = load_data()

    # 2. Load teacher predictions
    teacher_score, teacher_pred = load_teacher_predictions(addresses)

    # For teacher: also find optimal threshold
    teacher_optimal_thresh = find_optimal_threshold(y, teacher_score)
    teacher_pred_optimal = (teacher_score >= teacher_optimal_thresh).astype(int)
    log.info(f"Teacher optimal threshold: {teacher_optimal_thresh:.4f}")

    # 3. Train student pipeline (CV)
    oof_xgb, oof_lgbm, oof_meta, student_pred, student_threshold, fold_metrics = train_student_cv(X, y, feature_cols)

    # 4. Compute metrics
    log.info("\n" + "="*70)
    log.info("EVALUATION RESULTS")
    log.info("="*70)

    # Teacher metrics (using original predictions)
    teacher_metrics_orig = compute_metrics(y, teacher_score, teacher_pred, 'Teacher (original threshold)')
    teacher_metrics_opt = compute_metrics(y, teacher_score, teacher_pred_optimal, 'Teacher (optimal threshold)')

    # Student metrics (OOF - honest)
    student_metrics = compute_metrics(y, oof_meta, student_pred, 'Student (LR Meta, CV)')

    # Base model OOF metrics
    xgb_thresh = find_optimal_threshold(y, oof_xgb)
    lgbm_thresh = find_optimal_threshold(y, oof_lgbm)
    xgb_metrics = compute_metrics(y, oof_xgb, (oof_xgb >= xgb_thresh).astype(int), 'Student-XGBoost (base)')
    lgbm_metrics = compute_metrics(y, oof_lgbm, (oof_lgbm >= lgbm_thresh).astype(int), 'Student-LightGBM (base)')

    all_metrics = [teacher_metrics_orig, teacher_metrics_opt, xgb_metrics, lgbm_metrics, student_metrics]

    # Print comparison table
    log.info(f"\n{'Model':<40} {'ROC-AUC':>8} {'PR-AUC':>8} {'F1':>8} {'Prec':>8} {'Recall':>8} {'TP':>6} {'FP':>6} {'FN':>6}")
    log.info("-" * 115)
    for m in all_metrics:
        log.info(f"{m['model']:<40} {m['roc_auc']:>8.4f} {m['pr_auc']:>8.4f} {m['f1']:>8.4f} "
                 f"{m['precision']:>8.4f} {m['recall']:>8.4f} {m['true_positives']:>6} {m['false_positives']:>6} {m['false_negatives']:>6}")

    # Knowledge distillation quality
    log.info(f"\n--- Knowledge Distillation Quality ---")
    corr = np.corrcoef(teacher_score, oof_meta)[0,1]
    agreement = ((teacher_pred_optimal > 0) == (student_pred > 0)).mean()
    log.info(f"Score correlation (teacher vs student): {corr:.4f}")
    log.info(f"Prediction agreement: {100*agreement:.2f}%")

    delta_auc = student_metrics['roc_auc'] - teacher_metrics_opt['roc_auc']
    delta_pr = student_metrics['pr_auc'] - teacher_metrics_opt['pr_auc']
    log.info(f"ROC-AUC delta (student - teacher): {delta_auc:+.4f}")
    log.info(f"PR-AUC delta  (student - teacher): {delta_pr:+.4f}")

    if delta_auc >= -0.02 and delta_pr >= -0.02:
        log.info("VERDICT: Student successfully distills teacher knowledge")
    elif delta_auc >= -0.05:
        log.info("VERDICT: Student shows moderate distillation (minor degradation)")
    else:
        log.info("VERDICT: Student underperforms teacher significantly")

    # 5. Save results
    results = {
        'timestamp': pd.Timestamp.now().isoformat(),
        'dataset': {
            'file': 'eth_addresses_labeled.parquet',
            'n_samples': len(y),
            'n_features': len(feature_cols),
            'feature_names': feature_cols,
            'n_fraud': int(y.sum()),
            'fraud_rate': float(y.mean()),
        },
        'teacher': {
            'model_dir': str(TEACHER_DIR),
            'architecture': 'BetaVAE + VGAE + GATv2 + GraphSAGE + XGBoost + LightGBM + LogisticRegressionCV meta',
            'optimal_threshold': float(teacher_optimal_thresh),
            'metrics': teacher_metrics_opt,
        },
        'student': {
            'architecture': 'XGBoost + LightGBM + LogisticRegressionCV meta-learner',
            'n_folds': N_FOLDS,
            'optimal_threshold': float(student_threshold),
            'metrics': student_metrics,
            'base_model_metrics': {
                'xgboost': xgb_metrics,
                'lightgbm': lgbm_metrics,
            },
            'fold_metrics': fold_metrics,
        },
        'comparison': {
            'score_correlation': float(corr),
            'prediction_agreement': float(agreement),
            'roc_auc_delta': float(delta_auc),
            'pr_auc_delta': float(delta_pr),
        },
        'total_time_s': time.time() - t_start,
    }

    results_path = RESULTS_DIR / 'teacher_vs_student_results.json'
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    log.info(f"\nResults saved to {results_path}")

    # Save OOF predictions
    oof_df = pd.DataFrame({
        'address': addresses.values,
        'true_label': y,
        'teacher_score': teacher_score,
        'teacher_pred': teacher_pred_optimal,
        'student_xgb_score': oof_xgb,
        'student_lgbm_score': oof_lgbm,
        'student_meta_score': oof_meta,
        'student_pred': student_pred,
    })
    oof_path = RESULTS_DIR / 'oof_predictions.parquet'
    oof_df.to_parquet(oof_path, index=False)
    log.info(f"OOF predictions saved to {oof_path}")

    # 6. Generate plots
    plot_path = RESULTS_DIR / 'teacher_vs_student_comparison.png'
    plot_comparison(y, teacher_score, teacher_pred_optimal, oof_meta, student_pred, plot_path)

    log.info(f"\nTotal runtime: {time.time() - t_start:.1f}s")
    log.info("DONE.")


if __name__ == '__main__':
    main()
