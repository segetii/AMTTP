"""
AMTTP Teacher vs Student Model Evaluation (Corrected)
======================================================

Compares the Teacher (recalibrated XGB v1 + Rules + Graph -> hybrid_score)
against the Student (stacked ensemble with LogisticRegression meta-learner).

Teacher pipeline (171-feature XGBoost v1, from Kaggle ETH Fraud):
  XGBoost raw score -> sigmoid calibration -> xgb_normalized (0-100)
  + Pattern boost (SMURFING, STRUCTURING, PEELING, etc.)
  + Sophisticated score (behavioral analysis, normalized 0-100)
  -> hybrid_score = 0.4*xgb_normalized + 0.3*pattern_boost + 0.3*soph_normalized
  -> risk_level via PR-curve optimized thresholds
  -> fraud = 1 iff risk_level in {CRITICAL, HIGH}

Student pipeline (5-feature ensemble, trained on teacher labels):
  5 tabular features -> preprocessor -> pad to 71 features
  -> XGBoost v2 + LightGBM -> [zeros]*5 + [xgb_prob, lgb_prob]
  -> LogisticRegression meta-learner -> final fraud probability

Ground truth: 'fraud' column (derived from teacher's hybrid_score -> risk_level).
Since fraud labels ARE the teacher's output, teacher full pipeline has perfect
classification by construction. The meaningful comparisons are:
  - Teacher XGB component (xgb_raw_score) vs Student XGB component
  - Teacher XGB component vs Student full pipeline (meta-learner)
  - Discrimination power: how well each model's scores separate fraud from clean
"""

import sys
import os
import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings('ignore')

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # c:\amttp
PROCESSED_DIR = BASE_DIR / 'processed'
STUDENT_MODEL_DIR = Path(__file__).resolve().parent / 'amttp_models_20251231_174617'
DATASET_PATH = PROCESSED_DIR / 'eth_addresses_labeled.parquet'

# --- Reconstruct cuML meta-learner from binary-extracted weights ---
# meta_ensemble.joblib was pickled with cuml.linear_model.LogisticRegression
# (requires CUDA/RAPIDS). Weights extracted from raw binary at offset 1344.
import struct
import joblib

from sklearn.linear_model import LogisticRegression as _SklearnLR

_CUML_COEF = np.array([
    [ 0.7021293540377205,   #  recon_err (zeroed in simplified mode)
      3.3993734120448260,   #  edge_score (zeroed)
      0.4667988736205826,   #  gat_score (zeroed)
     -2.5898337664377720,   #  uncertainty (zeroed)
      0.8491953563291390,   #  sage_score (zeroed)
     -1.6858242340029680,   #  xgb_prob  <- active
      8.9820369186922350]   #  lgb_prob  <- active
])  # shape (1, 7)

_CUML_INTERCEPT = np.array([-5.5340591160288435])  # shape (1,)


def build_meta_model():
    """Reconstruct the cuML LogisticRegression as sklearn with extracted weights."""
    meta = _SklearnLR(C=1.0, penalty='l2', solver='lbfgs', max_iter=2000, fit_intercept=True)
    meta.classes_ = np.array([0, 1])
    meta.coef_ = _CUML_COEF
    meta.intercept_ = _CUML_INTERCEPT
    meta.n_features_in_ = 7
    return meta


# --- Student model modules ---
sys.path.insert(0, str(STUDENT_MODEL_DIR))
from inference import preprocess_features


def predict_fraud_cpu(raw_features, models, threshold=None):
    """Student inference (CPU-only). Pads 5 -> 71 features, zeros for VAE/graph."""
    if threshold is None:
        threshold = models['metadata']['optimal_threshold']

    features = preprocess_features(raw_features, models['preprocessors'])

    n_samples = features.shape[0]
    full_features = np.zeros((n_samples, 71), dtype=np.float32)
    full_features[:, :5] = features

    xgb_prob = models['xgb'].predict_proba(full_features)[:, 1]
    lgb_prob = models['lgb'].predict(full_features)

    zeros = np.zeros(n_samples)
    meta_features = np.column_stack([
        zeros, zeros, zeros, zeros, zeros,  # recon, edge, gat, unc, sage
        xgb_prob, lgb_prob
    ])

    fraud_prob = models['meta'].predict_proba(meta_features)[:, 1]
    risk_levels = np.where(fraud_prob >= 0.85, 'CRITICAL',
                  np.where(fraud_prob >= 0.65, 'HIGH',
                  np.where(fraud_prob >= 0.45, 'MEDIUM',
                  np.where(fraud_prob >= 0.25, 'LOW', 'MINIMAL'))))

    return {
        'fraud_prob': fraud_prob,
        'risk_levels': risk_levels,
        'is_fraud': fraud_prob >= threshold,
        'threshold': threshold,
        'xgb_prob': xgb_prob,
        'lgb_prob': lgb_prob,
    }


def load_student_models(model_dir):
    """Load student models, reconstructing meta-learner from extracted weights."""
    import xgboost as xgb
    import lightgbm as lgb

    with open(f'{model_dir}/metadata.json') as f:
        metadata = json.load(f)
    with open(f'{model_dir}/feature_config.json') as f:
        feature_config = json.load(f)

    preprocessors = joblib.load(f'{model_dir}/preprocessors.joblib')
    xgb_model = xgb.XGBClassifier()
    xgb_model.load_model(f'{model_dir}/xgboost_fraud.ubj')
    lgb_model = lgb.Booster(model_file=f'{model_dir}/lightgbm_fraud.txt')
    meta_model = build_meta_model()

    print(f"  Meta-model: LogisticRegression (reconstructed from cuML binary weights)")
    print(f"  Active weights: xgb_prob={meta_model.coef_[0, 5]:.4f}, lgb_prob={meta_model.coef_[0, 6]:.4f}, intercept={meta_model.intercept_[0]:.4f}")

    return {
        'xgb': xgb_model, 'lgb': lgb_model, 'meta': meta_model,
        'preprocessors': preprocessors, 'metadata': metadata,
        'feature_config': feature_config,
    }


def compute_metrics(y_true, y_prob, y_pred, model_name):
    """Compute comprehensive classification metrics."""
    from sklearn.metrics import (
        roc_auc_score, average_precision_score, f1_score,
        precision_score, recall_score, confusion_matrix,
        precision_recall_curve, matthews_corrcoef,
        balanced_accuracy_score, log_loss
    )

    metrics = {}
    try:
        metrics['roc_auc'] = roc_auc_score(y_true, y_prob)
    except Exception:
        metrics['roc_auc'] = float('nan')
    try:
        metrics['pr_auc'] = average_precision_score(y_true, y_prob)
    except Exception:
        metrics['pr_auc'] = float('nan')
    try:
        metrics['log_loss'] = log_loss(y_true, np.clip(y_prob, 1e-15, 1-1e-15))
    except Exception:
        metrics['log_loss'] = float('nan')

    metrics['f1'] = f1_score(y_true, y_pred, zero_division=0)
    metrics['precision'] = precision_score(y_true, y_pred, zero_division=0)
    metrics['recall'] = recall_score(y_true, y_pred, zero_division=0)
    metrics['mcc'] = matthews_corrcoef(y_true, y_pred)
    metrics['balanced_accuracy'] = balanced_accuracy_score(y_true, y_pred)

    cm = confusion_matrix(y_true, y_pred)
    metrics['confusion_matrix'] = cm
    tn, fp, fn, tp = cm.ravel() if cm.shape == (2, 2) else (0, 0, 0, 0)
    metrics['tp'] = int(tp)
    metrics['tn'] = int(tn)
    metrics['fp'] = int(fp)
    metrics['fn'] = int(fn)
    metrics['fpr'] = fp / (fp + tn) if (fp + tn) > 0 else 0
    metrics['fnr'] = fn / (fn + tp) if (fn + tp) > 0 else 0

    try:
        precisions, recalls, thresholds_pr = precision_recall_curve(y_true, y_prob)
        f1_scores = 2 * precisions * recalls / (precisions + recalls + 1e-10)
        best_idx = np.argmax(f1_scores)
        metrics['optimal_f1_threshold'] = float(thresholds_pr[best_idx]) if best_idx < len(thresholds_pr) else 0.5
        metrics['optimal_f1'] = float(f1_scores[best_idx])
    except Exception:
        metrics['optimal_f1_threshold'] = 0.5
        metrics['optimal_f1'] = metrics['f1']

    return metrics


def print_metrics(metrics, model_name):
    print(f"\n  --- {model_name} ---")
    print(f"  ROC-AUC:           {metrics['roc_auc']:.4f}")
    print(f"  PR-AUC:            {metrics['pr_auc']:.4f}")
    print(f"  Log Loss:          {metrics['log_loss']:.4f}")
    print(f"  F1 Score:          {metrics['f1']:.4f}")
    print(f"  Precision:         {metrics['precision']:.4f}")
    print(f"  Recall:            {metrics['recall']:.4f}")
    print(f"  MCC:               {metrics['mcc']:.4f}")
    print(f"  Balanced Accuracy: {metrics['balanced_accuracy']:.4f}")
    print(f"  FPR:               {metrics['fpr']:.6f}")
    print(f"  FNR:               {metrics['fnr']:.4f}")
    print(f"  Confusion Matrix:  TN={metrics['tn']:>7d}  FP={metrics['fp']:>7d}")
    print(f"                     FN={metrics['fn']:>7d}  TP={metrics['tp']:>7d}")
    print(f"  Optimal F1 @:      threshold={metrics['optimal_f1_threshold']:.4f} -> F1={metrics['optimal_f1']:.4f}")


def main():
    print("=" * 80)
    print(" AMTTP Teacher vs Student Model Evaluation (Corrected)")
    print(" Knowledge Distillation Performance Comparison")
    print("=" * 80)

    # --- 1. Load dataset with teacher scoring columns ---
    print("\n[1] LOADING DATASET")
    print("-" * 80)

    df = pd.read_parquet(DATASET_PATH)
    print(f"  Shape: {df.shape}")
    fraud_dist = df['fraud'].value_counts().to_dict()
    print(f"  Fraud distribution: {fraud_dist}")
    print(f"  Fraud rate: {fraud_dist.get(1, 0) / len(df) * 100:.4f}%")

    y_true = df['fraud'].values.astype(int)

    # --- 2. Extract teacher scores (from the labeled dataset itself) ---
    print("\n[2] TEACHER SCORES (from recalibrated pipeline)")
    print("-" * 80)
    print("  Teacher = XGBoost v1 (171 features) + Pattern Rules + Graph/Soph scores")
    print("  Formula: hybrid_score = 0.4*xgb_normalized + 0.3*pattern_boost + 0.3*soph_normalized")
    print("  Labels:  fraud=1 iff risk_level in {CRITICAL, HIGH}")

    # Teacher composite score (the full teacher pipeline output)
    teacher_hybrid = df['hybrid_score'].values / 100.0  # normalize 0-100 -> 0-1
    # Teacher XGB component alone
    teacher_xgb_raw = df['xgb_raw_score'].values  # already 0-1 range (raw XGB probability)
    teacher_xgb_norm = df['xgb_normalized'].values / 100.0  # sigmoid-calibrated, 0-100 -> 0-1
    # Teacher rule/graph components
    teacher_pattern = df['pattern_boost'].values / 100.0
    teacher_soph = df['soph_normalized'].values / 100.0

    fraud_mask = y_true == 1
    clean_mask = y_true == 0

    # Since fraud labels ARE derived from hybrid_score -> risk_level, teacher has
    # perfect separation by construction.
    fraud_min_hybrid = df.loc[df['fraud']==1, 'hybrid_score'].min()
    clean_max_hybrid = df.loc[df['fraud']==0, 'hybrid_score'].max()
    print(f"\n  Teacher hybrid_score:")
    print(f"    Fraud min: {fraud_min_hybrid:.4f},  Clean max: {clean_max_hybrid:.4f}")
    print(f"    Gap: {fraud_min_hybrid - clean_max_hybrid:.4f} (perfect separation)")

    print(f"\n  Teacher XGB raw_score (component):")
    print(f"    Fraud: mean={teacher_xgb_raw[fraud_mask].mean():.6f}, min={teacher_xgb_raw[fraud_mask].min():.6f}, max={teacher_xgb_raw[fraud_mask].max():.6f}")
    print(f"    Clean: mean={teacher_xgb_raw[clean_mask].mean():.6f}, min={teacher_xgb_raw[clean_mask].min():.6f}, max={teacher_xgb_raw[clean_mask].max():.6f}")

    # --- 3. Load and run student model ---
    print("\n[3] STUDENT MODEL (stacked ensemble)")
    print("-" * 80)
    models = load_student_models(str(STUDENT_MODEL_DIR))
    print(f"  Version: {models['metadata']['version']}")
    print(f"  Training ROC-AUC: {models['metadata']['performance']['meta_roc_auc']:.4f}")
    print(f"  Optimal threshold: {models['metadata']['optimal_threshold']:.4f}")

    # Build feature matrix
    tabular_features = models['feature_config']['tabular_features']
    feature_mapping = {
        'sender_total_transactions': 'total_transactions',
        'sender_total_sent': 'total_sent',
        'sender_total_received': 'total_received',
        'sender_sophisticated_score': 'sophisticated_score',
        'sender_hybrid_score': 'hybrid_score',
    }
    feature_df = pd.DataFrame()
    for feat in tabular_features:
        src = feature_mapping.get(feat, feat)
        if src in df.columns:
            feature_df[feat] = df[src]
        else:
            print(f"  WARNING: Feature '{feat}' not found, filling with 0")
            feature_df[feat] = 0

    raw_features = np.nan_to_num(feature_df.values.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)

    print(f"\n  Running inference on {len(raw_features)} samples...")
    student = predict_fraud_cpu(raw_features, models)

    print(f"  Student meta prob: mean={student['fraud_prob'].mean():.4f}, max={student['fraud_prob'].max():.4f}")
    print(f"  Student XGB prob:  mean={student['xgb_prob'].mean():.4f}, max={student['xgb_prob'].max():.4f}")
    print(f"  Student LGB prob:  mean={student['lgb_prob'].mean():.4f}, max={student['lgb_prob'].max():.4f}")
    print(f"  Student predictions (threshold={student['threshold']:.4f}): fraud={student['is_fraud'].sum()}, clean={(~student['is_fraud']).sum()}")

    # --- 4. Compute metrics ---
    print("\n[4] METRICS")
    print("-" * 80)

    from sklearn.metrics import roc_auc_score, precision_recall_curve

    # A) Teacher XGB component (xgb_raw_score)
    teacher_xgb_auc = roc_auc_score(y_true, teacher_xgb_raw)
    prec_t, rec_t, thresh_t = precision_recall_curve(y_true, teacher_xgb_raw)
    f1_t = 2 * prec_t * rec_t / (prec_t + rec_t + 1e-10)
    best_idx_t = np.argmax(f1_t)
    teacher_xgb_optimal_thresh = thresh_t[best_idx_t] if best_idx_t < len(thresh_t) else 0.5
    teacher_xgb_pred_optimal = (teacher_xgb_raw >= teacher_xgb_optimal_thresh).astype(int)
    teacher_xgb_metrics = compute_metrics(y_true, teacher_xgb_raw, teacher_xgb_pred_optimal, "Teacher XGB")
    print_metrics(teacher_xgb_metrics, f"Teacher XGB Component (v1, 171-feat, threshold={teacher_xgb_optimal_thresh:.6f})")

    # B) Teacher full pipeline (hybrid_score) — perfect by construction
    effective_threshold = (fraud_min_hybrid + clean_max_hybrid) / 2 / 100.0
    teacher_hybrid_pred = (teacher_hybrid >= effective_threshold).astype(int)
    teacher_hybrid_metrics = compute_metrics(y_true, teacher_hybrid, teacher_hybrid_pred, "Teacher Hybrid")
    print_metrics(teacher_hybrid_metrics, f"Teacher Full Pipeline (XGB+Rules+Graph, threshold={effective_threshold:.4f})")

    # C) Student meta-learner (full pipeline)
    student_meta_pred = student['is_fraud'].astype(int)
    student_meta_metrics = compute_metrics(y_true, student['fraud_prob'], student_meta_pred, "Student Meta")
    print_metrics(student_meta_metrics, f"Student Meta-Learner (LogReg, threshold={student['threshold']:.4f})")

    # D) Student XGB component
    student_xgb_pred = (student['xgb_prob'] >= 0.5).astype(int)
    student_xgb_metrics = compute_metrics(y_true, student['xgb_prob'], student_xgb_pred, "Student XGB")
    print_metrics(student_xgb_metrics, "Student XGBoost v2 (5-feat, threshold=0.5)")

    # E) Student LGB component
    student_lgb_pred = (student['lgb_prob'] >= 0.5).astype(int)
    student_lgb_metrics = compute_metrics(y_true, student['lgb_prob'], student_lgb_pred, "Student LGB")
    print_metrics(student_lgb_metrics, "Student LightGBM (5-feat, threshold=0.5)")

    # --- 5. Head-to-head comparison ---
    print("\n[5] COMPARISON TABLE")
    print("-" * 80)

    all_models = {
        'Tch XGB(v1)': teacher_xgb_metrics,
        'Tch Full':    teacher_hybrid_metrics,
        'Stu Meta':    student_meta_metrics,
        'Stu XGB(v2)': student_xgb_metrics,
        'Stu LGB':     student_lgb_metrics,
    }

    compare_metrics = ['roc_auc', 'pr_auc', 'f1', 'precision', 'recall', 'mcc', 'fpr', 'fnr']
    lower_better = {'log_loss', 'fpr', 'fnr'}

    names = list(all_models.keys())
    hdr = f"  {'Metric':<18}"
    for n in names:
        hdr += f" {n:>12}"
    hdr += f" {'Winner':>14}"
    print(hdr)
    print("  " + "-" * (18 + 13*len(names) + 15))

    for m in compare_metrics:
        row = f"  {m:<18}"
        vals = {}
        for n, metrics in all_models.items():
            v = metrics.get(m, float('nan'))
            vals[n] = v
            row += f" {v:>12.4f}"

        valid = {k: v for k, v in vals.items() if not np.isnan(v)}
        if valid:
            winner = min(valid, key=valid.get) if m in lower_better else max(valid, key=valid.get)
        else:
            winner = 'N/A'
        row += f" {winner:>14}"
        print(row)

    # --- 6. Key comparisons ---
    print("\n[6] KEY COMPARISONS")
    print("-" * 80)

    print("\n  A) Teacher XGB (v1, 171 features) vs Student XGB (v2, 5 features):")
    delta_auc = student_xgb_metrics['roc_auc'] - teacher_xgb_metrics['roc_auc']
    delta_f1 = student_xgb_metrics['optimal_f1'] - teacher_xgb_metrics['optimal_f1']
    print(f"     ROC-AUC: Teacher={teacher_xgb_metrics['roc_auc']:.4f} vs Student={student_xgb_metrics['roc_auc']:.4f} (delta={delta_auc:+.4f})")
    print(f"     Optimal F1: Teacher={teacher_xgb_metrics['optimal_f1']:.4f} vs Student={student_xgb_metrics['optimal_f1']:.4f} (delta={delta_f1:+.4f})")
    print(f"     PR-AUC: Teacher={teacher_xgb_metrics['pr_auc']:.4f} vs Student={student_xgb_metrics['pr_auc']:.4f}")
    if delta_auc > 0:
        print(f"     --> Student XGB outperforms Teacher XGB by {delta_auc:.4f} ROC-AUC")
    else:
        print(f"     --> Teacher XGB outperforms Student XGB by {abs(delta_auc):.4f} ROC-AUC")

    print("\n  B) Teacher XGB (v1) vs Student Full Pipeline (meta-learner):")
    delta_auc2 = student_meta_metrics['roc_auc'] - teacher_xgb_metrics['roc_auc']
    delta_f12 = student_meta_metrics['optimal_f1'] - teacher_xgb_metrics['optimal_f1']
    print(f"     ROC-AUC: Teacher XGB={teacher_xgb_metrics['roc_auc']:.4f} vs Student Meta={student_meta_metrics['roc_auc']:.4f} (delta={delta_auc2:+.4f})")
    print(f"     Optimal F1: Teacher XGB={teacher_xgb_metrics['optimal_f1']:.4f} vs Student Meta={student_meta_metrics['optimal_f1']:.4f} (delta={delta_f12:+.4f})")
    print(f"     PR-AUC: Teacher XGB={teacher_xgb_metrics['pr_auc']:.4f} vs Student Meta={student_meta_metrics['pr_auc']:.4f}")

    print("\n  C) Teacher Full (XGB+Rules+Graph) vs Student Full (meta-learner):")
    print(f"     NOTE: Teacher Full has perfect metrics because the labels are derived FROM its scores.")
    print(f"     This comparison is asymmetric -- teacher is evaluated on its own labels.")
    delta_auc3 = student_meta_metrics['roc_auc'] - teacher_hybrid_metrics['roc_auc']
    print(f"     ROC-AUC: Teacher Full={teacher_hybrid_metrics['roc_auc']:.4f} vs Student Meta={student_meta_metrics['roc_auc']:.4f} (delta={delta_auc3:+.4f})")
    print(f"     F1: Teacher Full={teacher_hybrid_metrics['f1']:.4f} vs Student Meta={student_meta_metrics['f1']:.4f}")

    # --- 7. Score distribution by class ---
    print("\n[7] SCORE DISTRIBUTION BY CLASS")
    print("-" * 80)

    print(f"\n  {'Score':<25} {'Fraud mean':>12} {'Fraud std':>12} {'Clean mean':>12} {'Clean std':>12} {'Cohen d':>10}")
    print("  " + "-" * 85)

    distributions = [
        ('Teacher xgb_raw', teacher_xgb_raw),
        ('Teacher xgb_norm/100', teacher_xgb_norm),
        ('Teacher hybrid/100', teacher_hybrid),
        ('Student meta_prob', student['fraud_prob']),
        ('Student xgb_prob', student['xgb_prob']),
        ('Student lgb_prob', student['lgb_prob']),
    ]

    for name, scores in distributions:
        fm = scores[fraud_mask].mean()
        fs = scores[fraud_mask].std()
        cm = scores[clean_mask].mean()
        cs = scores[clean_mask].std()
        pooled_std = np.sqrt((fs**2 + cs**2) / 2) if (fs > 0 and cs > 0) else 1e-10
        cohen_d = (fm - cm) / pooled_std
        print(f"  {name:<25} {fm:>12.6f} {fs:>12.6f} {cm:>12.6f} {cs:>12.6f} {cohen_d:>10.2f}")

    # --- 8. Agreement analysis ---
    print("\n[8] AGREEMENT ANALYSIS")
    print("-" * 80)

    student_pred = student['is_fraud'].astype(int)
    agree = (y_true == student_pred).sum()
    print(f"  Teacher labels vs Student predictions: {agree}/{len(y_true)} ({agree/len(y_true)*100:.2f}%)")
    print(f"  Teacher=Fraud, Student=Clean (missed by student): {((y_true==1) & (student_pred==0)).sum()}")
    print(f"  Teacher=Clean, Student=Fraud (student false alarm): {((y_true==0) & (student_pred==1)).sum()}")
    print(f"  Both=Fraud:  {((y_true==1) & (student_pred==1)).sum()}")
    print(f"  Both=Clean:  {((y_true==0) & (student_pred==0)).sum()}")

    # --- 9. Save results ---
    results_path = BASE_DIR / 'ml' / 'Automation' / 'evaluation_results.json'
    def sanitize(metrics):
        return {k: float(v) if isinstance(v, (int, float, np.floating, np.integer)) else None
                for k, v in metrics.items() if k != 'confusion_matrix'}

    results = {
        'evaluation_date': pd.Timestamp.now().isoformat(),
        'dataset': {
            'path': str(DATASET_PATH),
            'n_samples': int(len(df)),
            'n_fraud': int(y_true.sum()),
            'fraud_rate': float(y_true.mean()),
        },
        'teacher_xgb': {
            'model': 'ml/Automation/ml_pipeline/models/trained/xgb.json',
            'description': 'Original XGBoost v1, 171 features (Kaggle ETH Fraud trained)',
            'scores_column': 'xgb_raw_score',
            'optimal_threshold': float(teacher_xgb_optimal_thresh),
            'metrics': sanitize(teacher_xgb_metrics),
            'confusion_matrix': teacher_xgb_metrics['confusion_matrix'].tolist(),
        },
        'teacher_full': {
            'formula': '0.4*xgb_normalized + 0.3*pattern_boost + 0.3*soph_normalized',
            'description': 'Full teacher pipeline: XGBoost v1 + Pattern Rules + Graph/Soph scores',
            'scores_column': 'hybrid_score',
            'note': 'Labels are derived from this score -- perfect by construction',
            'metrics': sanitize(teacher_hybrid_metrics),
        },
        'student_meta': {
            'model': 'ml/Automation/amttp_models_20251231_174617/meta_ensemble.joblib',
            'description': 'LogReg meta-learner over [XGB v2 + LGB] (simplified: graph/VAE zeroed)',
            'threshold': float(student['threshold']),
            'coef': _CUML_COEF.tolist(),
            'intercept': _CUML_INTERCEPT.tolist(),
            'metrics': sanitize(student_meta_metrics),
            'confusion_matrix': student_meta_metrics['confusion_matrix'].tolist(),
        },
        'student_xgb': {
            'model': 'ml/Automation/amttp_models_20251231_174617/xgboost_fraud.ubj',
            'description': 'Student XGBoost v2, 5 tabular features (knowledge-distilled)',
            'metrics': sanitize(student_xgb_metrics),
            'confusion_matrix': student_xgb_metrics['confusion_matrix'].tolist(),
        },
        'student_lgb': {
            'model': 'ml/Automation/amttp_models_20251231_174617/lightgbm_fraud.txt',
            'description': 'Student LightGBM, 5 tabular features (knowledge-distilled)',
            'metrics': sanitize(student_lgb_metrics),
            'confusion_matrix': student_lgb_metrics['confusion_matrix'].tolist(),
        },
        'notes': [
            'Ground truth = fraud column, derived from teacher hybrid_score -> risk_level in {CRITICAL, HIGH}',
            'Teacher Full has perfect metrics by construction (labels derive from its scores)',
            'Fair comparison: Teacher XGB component vs Student XGB/Meta/LGB',
            'Student runs in simplified mode: graph/VAE features zeroed out',
            'Teacher XGB: 171 features from Kaggle ETH dataset',
            'Student models: 5 tabular features (total_transactions, total_sent, total_received, sophisticated_score, hybrid_score)',
        ]
    }

    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved to: {results_path}")

    print("\n" + "=" * 80)
    print(" EVALUATION COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
