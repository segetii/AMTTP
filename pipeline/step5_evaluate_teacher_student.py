"""
AMTTP Teacher vs Student Model Evaluation (v2)
===============================================

5-Way Model Comparison:
  1. Teacher XGB         – xgb_raw_score (recalibrated with optimal threshold)
  2. Teacher Full Stack  – hybrid_score (XGB + Rules + Graph), NOTE: labels derived from this
  3. Student XGB v2      – XGBoost retrained on teacher-labeled data (71 features)
  4. Student LGB         – LightGBM retrained on teacher-labeled data
  5. Student Ensemble    – LogReg meta-learner over [graph_zeros + XGB_v2 + LGB]

Ground truth: 'fraud' column = risk_level ∈ {CRITICAL, HIGH} (derived from hybrid_score)
Dataset: processed/eth_addresses_labeled.parquet (625,168 addresses, 372 fraud)

NOTE: Because fraud labels are derived FROM the teacher hybrid_score,
      the teacher full stack achieves F1=1.0 by definition (circular).
      The meaningful comparison is Teacher XGB (standalone) vs Student models.
"""

import sys
import os
import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import (
    roc_auc_score, average_precision_score, f1_score,
    precision_score, recall_score, confusion_matrix,
    precision_recall_curve, matthews_corrcoef,
    balanced_accuracy_score, log_loss, roc_curve
)

warnings.filterwarnings('ignore')

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # c:\amttp
PROCESSED_DIR = BASE_DIR / 'processed'
STUDENT_MODEL_DIR = Path(__file__).resolve().parent / 'amttp_models_20251231_174617'
DATASET_PATH = PROCESSED_DIR / 'eth_addresses_labeled.parquet'

# ─── Reconstructed cuML meta-learner weights ────────────────────────────────
# Extracted from meta_ensemble.joblib binary (cuML LogReg, requires CUDA).
# Shape: coef_ (1,7) for [recon, edge, gat, unc, sage, xgb_prob, lgb_prob]
import struct
import joblib
from sklearn.linear_model import LogisticRegression as _SklearnLR

_CUML_COEF = np.array([[
    0.7021293540377205,   # recon_err   (zeroed in simplified mode)
    3.3993734120448260,   # edge_score  (zeroed)
    0.4667988736205826,   # gat_score   (zeroed)
   -2.5898337664377720,   # uncertainty (zeroed)
    0.8491953563291390,   # sage_score  (zeroed)
   -1.6858242340029680,   # xgb_prob    ← active
    8.9820369186922350,   # lgb_prob    ← active
]])
_CUML_INTERCEPT = np.array([-5.5340591160288435])


def build_meta_model():
    """Reconstruct cuML LogReg as sklearn LogReg with extracted weights."""
    m = _SklearnLR(C=1.0, penalty='l2', solver='lbfgs', max_iter=2000)
    m.classes_ = np.array([0, 1])
    m.coef_ = _CUML_COEF
    m.intercept_ = _CUML_INTERCEPT
    m.n_features_in_ = 7
    return m


# ─── Student model loading ──────────────────────────────────────────────────
sys.path.insert(0, str(STUDENT_MODEL_DIR))
from inference import preprocess_features


def load_student_models(model_dir):
    """Load student XGB, LGB, preprocessors, and reconstruct meta-learner."""
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

    return {
        'xgb': xgb_model, 'lgb': lgb_model, 'meta': meta_model,
        'preprocessors': preprocessors, 'metadata': metadata,
        'feature_config': feature_config,
    }


def run_student_inference(df, models):
    """Run student XGB, LGB, and meta-ensemble inference."""
    tabular_features = models['feature_config']['tabular_features']

    feature_df = pd.DataFrame()
    for feat in tabular_features:
        if feat in df.columns:
            feature_df[feat] = df[feat]
        else:
            unmapped = feat.replace('sender_', '')
            if unmapped in df.columns:
                feature_df[feat] = df[unmapped]
            else:
                feature_df[feat] = 0

    raw_features = feature_df.values.astype(np.float32)
    raw_features = np.nan_to_num(raw_features, nan=0.0, posinf=0.0, neginf=0.0)

    features = preprocess_features(raw_features, models['preprocessors'])

    # Pad to 71 features (5 tabular + 64 VAE latents + recon_err + graphsage_score)
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
    meta_prob = models['meta'].predict_proba(meta_features)[:, 1]

    return xgb_prob, lgb_prob, meta_prob


def recalibrate_teacher_xgb(y_true, xgb_scores):
    """
    Recalibrate Teacher XGB: find optimal threshold via Youden's J and F1.
    Also apply sigmoid calibration matching the teacher's own pipeline.
    """
    results = {}

    # 1. Raw ROC-AUC
    results['roc_auc'] = roc_auc_score(y_true, xgb_scores)

    # 2. PR-AUC
    results['pr_auc'] = average_precision_score(y_true, xgb_scores)

    # 3. F1-optimal threshold on raw scores
    prec, rec, thresh = precision_recall_curve(y_true, xgb_scores)
    f1s = 2 * prec * rec / (prec + rec + 1e-10)
    best_f1_idx = np.argmax(f1s)
    results['f1_optimal_threshold'] = float(thresh[best_f1_idx]) if best_f1_idx < len(thresh) else 0.5
    results['f1_optimal'] = float(f1s[best_f1_idx])

    # 4. Youden's J optimal threshold (maximizes sensitivity + specificity - 1)
    fpr, tpr, roc_thresh = roc_curve(y_true, xgb_scores)
    j_scores = tpr - fpr
    best_j_idx = np.argmax(j_scores)
    results['youden_threshold'] = float(roc_thresh[best_j_idx])
    results['youden_j'] = float(j_scores[best_j_idx])
    results['youden_tpr'] = float(tpr[best_j_idx])
    results['youden_fpr'] = float(fpr[best_j_idx])

    # 5. Apply sigmoid calibration (matching teacher pipeline)
    # Teacher used: sigmoid with k=30 centered at p75
    p75 = np.percentile(xgb_scores, 75)
    k = 30
    calibrated = 1.0 / (1.0 + np.exp(-k * (xgb_scores - p75)))
    results['calibrated_scores'] = calibrated
    results['calibrated_roc_auc'] = roc_auc_score(y_true, calibrated)
    results['calibrated_pr_auc'] = average_precision_score(y_true, calibrated)

    # F1-optimal on calibrated
    prec_c, rec_c, thresh_c = precision_recall_curve(y_true, calibrated)
    f1s_c = 2 * prec_c * rec_c / (prec_c + rec_c + 1e-10)
    best_c_idx = np.argmax(f1s_c)
    results['calibrated_f1_threshold'] = float(thresh_c[best_c_idx]) if best_c_idx < len(thresh_c) else 0.5
    results['calibrated_f1_optimal'] = float(f1s_c[best_c_idx])

    return results


def compute_metrics(y_true, y_prob, threshold, model_name):
    """Compute full classification metrics at a given threshold."""
    y_pred = (y_prob >= threshold).astype(int)
    m = {}

    m['threshold'] = threshold
    try:
        m['roc_auc'] = roc_auc_score(y_true, y_prob)
    except:
        m['roc_auc'] = float('nan')
    try:
        m['pr_auc'] = average_precision_score(y_true, y_prob)
    except:
        m['pr_auc'] = float('nan')
    try:
        m['log_loss'] = log_loss(y_true, np.clip(y_prob, 1e-15, 1-1e-15))
    except:
        m['log_loss'] = float('nan')

    m['f1'] = f1_score(y_true, y_pred, zero_division=0)
    m['precision'] = precision_score(y_true, y_pred, zero_division=0)
    m['recall'] = recall_score(y_true, y_pred, zero_division=0)
    m['mcc'] = matthews_corrcoef(y_true, y_pred)
    m['balanced_accuracy'] = balanced_accuracy_score(y_true, y_pred)

    cm = confusion_matrix(y_true, y_pred)
    if cm.shape == (2, 2):
        tn, fp, fn, tp = cm.ravel()
    else:
        tn = fp = fn = tp = 0
    m['tp'], m['fp'], m['fn'], m['tn'] = int(tp), int(fp), int(fn), int(tn)
    m['fpr'] = fp / (fp + tn) if (fp + tn) > 0 else 0
    m['fnr'] = fn / (fn + tp) if (fn + tp) > 0 else 0

    # Optimal F1 threshold
    try:
        prec, rec, thr = precision_recall_curve(y_true, y_prob)
        f1s = 2 * prec * rec / (prec + rec + 1e-10)
        best = np.argmax(f1s)
        m['optimal_f1_threshold'] = float(thr[best]) if best < len(thr) else threshold
        m['optimal_f1'] = float(f1s[best])
    except:
        m['optimal_f1_threshold'] = threshold
        m['optimal_f1'] = m['f1']

    return m


def print_metrics(m, name):
    print(f"\n  {'─'*3} {name} {'─'*3}")
    print(f"  Threshold used:     {m['threshold']:.6f}")
    print(f"  ROC-AUC:            {m['roc_auc']:.6f}")
    print(f"  PR-AUC:             {m['pr_auc']:.6f}")
    print(f"  Log Loss:           {m['log_loss']:.6f}")
    print(f"  F1 Score:           {m['f1']:.6f}")
    print(f"  Precision:          {m['precision']:.6f}")
    print(f"  Recall:             {m['recall']:.6f}")
    print(f"  MCC:                {m['mcc']:.6f}")
    print(f"  Balanced Accuracy:  {m['balanced_accuracy']:.6f}")
    print(f"  FPR:                {m['fpr']:.6f}")
    print(f"  FNR:                {m['fnr']:.6f}")
    print(f"  Confusion: TP={m['tp']:>6d}  FP={m['fp']:>6d}  FN={m['fn']:>6d}  TN={m['tn']:>6d}")
    print(f"  Optimal F1:         {m['optimal_f1']:.6f} @ threshold={m['optimal_f1_threshold']:.6f}")


def main():
    print("╔" + "═"*78 + "╗")
    print("║" + " AMTTP 5-Way Model Comparison ".center(78) + "║")
    print("║" + " Teacher XGB │ Teacher Stack │ Student XGB │ Student LGB │ Student Ensemble ".center(78) + "║")
    print("╚" + "═"*78 + "╝")

    # ─── Load dataset ─────────────────────────────────────────────────────
    print("\n" + "="*80)
    print("1. LOADING DATASET")
    print("="*80)

    df = pd.read_parquet(DATASET_PATH)
    y_true = df['fraud'].values.astype(int)
    n_fraud = y_true.sum()
    n_total = len(y_true)
    print(f"  Samples: {n_total:,}  |  Fraud: {n_fraud} ({n_fraud/n_total*100:.4f}%)")
    print(f"  Label derivation: fraud=1 iff risk_level ∈ {{CRITICAL, HIGH}}")
    print(f"  Label source:     hybrid_score thresholds (teacher full stack)")

    # ─── Teacher XGB Recalibration ────────────────────────────────────────
    print("\n" + "="*80)
    print("2. TEACHER XGB RECALIBRATION")
    print("="*80)

    xgb_raw = df['xgb_raw_score'].values
    cal = recalibrate_teacher_xgb(y_true, xgb_raw)

    print(f"  Raw XGB score range: [{xgb_raw.min():.6f}, {xgb_raw.max():.6f}]")
    print(f"  Raw ROC-AUC: {cal['roc_auc']:.6f}")
    print(f"  Raw PR-AUC:  {cal['pr_auc']:.6f}")
    print(f"  F1-optimal threshold (raw): {cal['f1_optimal_threshold']:.6f}  →  F1={cal['f1_optimal']:.6f}")
    print(f"  Youden J threshold:         {cal['youden_threshold']:.6f}  →  J={cal['youden_j']:.4f} (TPR={cal['youden_tpr']:.4f}, FPR={cal['youden_fpr']:.4f})")
    print(f"")
    print(f"  Sigmoid-calibrated (k=30, centering=p75):")
    print(f"    ROC-AUC: {cal['calibrated_roc_auc']:.6f}")
    print(f"    PR-AUC:  {cal['calibrated_pr_auc']:.6f}")
    print(f"    F1-optimal threshold: {cal['calibrated_f1_threshold']:.6f}  →  F1={cal['calibrated_f1_optimal']:.6f}")

    # Use both raw (F1-optimal) and calibrated for Teacher XGB
    teacher_xgb_raw_thresh = cal['f1_optimal_threshold']
    teacher_xgb_cal = cal['calibrated_scores']
    teacher_xgb_cal_thresh = cal['calibrated_f1_threshold']

    # ─── Teacher Full Stack (hybrid_score) ────────────────────────────────
    print("\n" + "="*80)
    print("3. TEACHER FULL STACK (hybrid_score = 0.4*XGB + 0.3*Rules + 0.3*Graph)")
    print("="*80)

    hybrid = df['hybrid_score'].values
    print(f"  hybrid_score range: [{hybrid.min():.2f}, {hybrid.max():.2f}]")
    print(f"  Fraud range:  [{hybrid[y_true==1].min():.2f}, {hybrid[y_true==1].max():.2f}]")
    print(f"  Clean range:  [{hybrid[y_true==0].min():.2f}, {hybrid[y_true==0].max():.2f}]")
    print(f"  ⚠  Labels derived FROM hybrid_score → comparison is CIRCULAR (F1=1.0)")

    # Normalize hybrid to [0,1] for fair metric comparison
    hybrid_norm = hybrid / 100.0  # hybrid is on 0-100 scale
    hybrid_thresh = 0.4858  # ~48.58/100, where HIGH starts

    # ─── Load & Run Student Models ────────────────────────────────────────
    print("\n" + "="*80)
    print("4. LOADING STUDENT MODELS")
    print("="*80)

    models = load_student_models(str(STUDENT_MODEL_DIR))
    meta_data = models['metadata']
    print(f"  Version: {meta_data['version']}")
    print(f"  Training ROC-AUC: {meta_data['performance']['meta_roc_auc']:.4f}")
    print(f"  Optimal threshold: {meta_data['optimal_threshold']:.4f}")
    print(f"  Meta-learner weights:")
    print(f"    xgb_prob coef:  {_CUML_COEF[0, 5]:.4f}")
    print(f"    lgb_prob coef:  {_CUML_COEF[0, 6]:.4f}")
    print(f"    intercept:      {_CUML_INTERCEPT[0]:.4f}")

    print("\n" + "="*80)
    print("5. RUNNING STUDENT INFERENCE (625K addresses)")
    print("="*80)

    s_xgb_prob, s_lgb_prob, s_meta_prob = run_student_inference(df, models)

    student_threshold = meta_data['optimal_threshold']  # 0.727

    print(f"  Student XGB prob:  mean={s_xgb_prob.mean():.6f}, max={s_xgb_prob.max():.6f}")
    print(f"  Student LGB prob:  mean={s_lgb_prob.mean():.6f}, max={s_lgb_prob.max():.6f}")
    print(f"  Student Meta prob: mean={s_meta_prob.mean():.6f}, max={s_meta_prob.max():.6f}")

    # ─── Compute metrics for all 5 models ────────────────────────────────
    print("\n" + "="*80)
    print("6. COMPUTING METRICS (all 5 models)")
    print("="*80)

    # Model 1: Teacher XGB (recalibrated, raw scores, F1-optimal threshold)
    m_teacher_xgb_raw = compute_metrics(y_true, xgb_raw, teacher_xgb_raw_thresh, "Teacher XGB (raw)")
    print_metrics(m_teacher_xgb_raw, "MODEL 1: Teacher XGB (raw, F1-optimal threshold)")

    # Model 1b: Teacher XGB (sigmoid-calibrated, F1-optimal threshold)
    m_teacher_xgb_cal = compute_metrics(y_true, teacher_xgb_cal, teacher_xgb_cal_thresh, "Teacher XGB (calibrated)")
    print_metrics(m_teacher_xgb_cal, "MODEL 1b: Teacher XGB (sigmoid-calibrated)")

    # Model 2: Teacher Full Stack (hybrid_score, normalized)
    m_teacher_stack = compute_metrics(y_true, hybrid_norm, hybrid_thresh, "Teacher Full Stack")
    print_metrics(m_teacher_stack, "MODEL 2: Teacher Full Stack (XGB+Rules+Graph) ⚠ CIRCULAR")

    # Model 3: Student XGB v2 (at 0.5 threshold + optimal)
    m_student_xgb = compute_metrics(y_true, s_xgb_prob, 0.5, "Student XGB v2")
    print_metrics(m_student_xgb, "MODEL 3: Student XGB v2 (threshold=0.5)")

    # Model 4: Student LGB (at 0.5 threshold + optimal)
    m_student_lgb = compute_metrics(y_true, s_lgb_prob, 0.5, "Student LGB")
    print_metrics(m_student_lgb, "MODEL 4: Student LightGBM (threshold=0.5)")

    # Model 5: Student Ensemble (meta-learner, at trained threshold)
    m_student_ens = compute_metrics(y_true, s_meta_prob, student_threshold, "Student Ensemble")
    print_metrics(m_student_ens, f"MODEL 5: Student Ensemble (threshold={student_threshold})")

    # ─── 5-Way Comparison Table ──────────────────────────────────────────
    print("\n" + "="*80)
    print("7. COMPARISON TABLE")
    print("="*80)

    all_models = {
        'Teacher XGB': m_teacher_xgb_cal,
        'Teacher Stack⚠': m_teacher_stack,
        'Student XGB': m_student_xgb,
        'Student LGB': m_student_lgb,
        'Student Ens': m_student_ens,
    }

    compare_metrics = ['roc_auc', 'pr_auc', 'f1', 'precision', 'recall', 'mcc', 'balanced_accuracy', 'fpr', 'fnr']
    lower_better = {'fpr', 'fnr', 'log_loss'}

    header = f"  {'Metric':<20}"
    for name in all_models:
        header += f" {name:>14}"
    header += f" {'Winner':>14}"
    print(header)
    print("  " + "─"*(20 + 15*len(all_models) + 15))

    for metric in compare_metrics:
        row = f"  {metric:<20}"
        vals = {}
        for name, m in all_models.items():
            v = m.get(metric, float('nan'))
            vals[name] = v
            row += f" {v:>14.6f}"

        valid = {k: v for k, v in vals.items() if not np.isnan(v) and 'Stack' not in k}  # exclude circular
        if valid:
            if metric in lower_better:
                winner = min(valid, key=valid.get)
            else:
                winner = max(valid, key=valid.get)
        else:
            winner = 'N/A'
        row += f" {winner:>14}"
        print(row)

    # ─── Score Distribution Analysis ─────────────────────────────────────
    print("\n" + "="*80)
    print("8. SCORE DISTRIBUTION (Fraud vs Clean)")
    print("="*80)

    fraud_mask = y_true == 1
    clean_mask = y_true == 0

    for name, scores in [("Teacher XGB (calibrated)", teacher_xgb_cal),
                          ("Teacher hybrid (norm)", hybrid_norm),
                          ("Student XGB", s_xgb_prob),
                          ("Student LGB", s_lgb_prob),
                          ("Student Ensemble", s_meta_prob)]:
        print(f"\n  {name}:")
        print(f"    Fraud (n={fraud_mask.sum()}): mean={scores[fraud_mask].mean():.6f}, "
              f"median={np.median(scores[fraud_mask]):.6f}, std={scores[fraud_mask].std():.6f}")
        print(f"    Clean (n={clean_mask.sum()}): mean={scores[clean_mask].mean():.6f}, "
              f"median={np.median(scores[clean_mask]):.6f}, std={scores[clean_mask].std():.6f}")
        sep = scores[fraud_mask].mean() - scores[clean_mask].mean()
        print(f"    Separation (mean fraud - mean clean): {sep:.6f}")

    # ─── Knowledge Distillation Analysis ─────────────────────────────────
    print("\n" + "="*80)
    print("9. KNOWLEDGE DISTILLATION ANALYSIS")
    print("="*80)

    print(f"\n  Teacher XGB alone (ROC-AUC={m_teacher_xgb_cal['roc_auc']:.4f}, F1={m_teacher_xgb_cal['optimal_f1']:.4f}):")
    print(f"    Great ranking but poor classification — scores too compressed")
    print(f"    Even at F1-optimal threshold: Precision={m_teacher_xgb_cal['precision']:.4f}, Recall={m_teacher_xgb_cal['recall']:.4f}")
    print(f"    The XGB separates fraud from clean but with huge overlap zone")

    print(f"\n  Teacher Full Stack (ROC-AUC={m_teacher_stack['roc_auc']:.4f}, F1={m_teacher_stack['f1']:.4f}):")
    print(f"    ⚠  Perfect because labels were derived from hybrid_score thresholds")
    print(f"    The rules + graph features create clean separation the XGB alone lacks")

    print(f"\n  Student Ensemble (ROC-AUC={m_student_ens['roc_auc']:.4f}, F1={m_student_ens['optimal_f1']:.4f}):")
    delta_roc = m_student_ens['roc_auc'] - m_teacher_xgb_cal['roc_auc']
    delta_f1 = m_student_ens['optimal_f1'] - m_teacher_xgb_cal['optimal_f1']
    print(f"    vs Teacher XGB: ROC-AUC {delta_roc:+.4f}, F1 {delta_f1:+.4f}")
    if delta_roc > 0 and delta_f1 > 0:
        print(f"    ✅ Student has SUCCESSFULLY distilled teacher stack knowledge")
        print(f"       The ensemble learned the rules+graph patterns from teacher labels")
    else:
        print(f"    Student has NOT fully captured teacher stack patterns")

    print(f"\n  Student XGB v2 vs Teacher XGB v1:")
    delta = m_student_xgb['roc_auc'] - m_teacher_xgb_cal['roc_auc']
    print(f"    ROC-AUC: Teacher={m_teacher_xgb_cal['roc_auc']:.4f} → Student={m_student_xgb['roc_auc']:.4f} ({delta:+.4f})")
    print(f"    F1-opt:  Teacher={m_teacher_xgb_cal['optimal_f1']:.4f} → Student={m_student_xgb['optimal_f1']:.4f}")

    # ─── Save Results ─────────────────────────────────────────────────────
    results_path = BASE_DIR / 'ml' / 'Automation' / 'evaluation_results_v2.json'
    results = {
        'evaluation_date': pd.Timestamp.now().isoformat(),
        'dataset': {
            'path': str(DATASET_PATH),
            'n_samples': n_total,
            'n_fraud': int(n_fraud),
            'fraud_rate': float(n_fraud / n_total),
            'label_source': 'hybrid_score thresholds (CRITICAL/HIGH risk_level)',
        },
        'models': {}
    }
    for name, m in all_models.items():
        results['models'][name] = {
            k: (float(v) if isinstance(v, (int, float, np.floating, np.integer)) else None)
            for k, v in m.items()
        }
    results['recalibration'] = {
        'teacher_xgb_raw_roc_auc': cal['roc_auc'],
        'teacher_xgb_raw_pr_auc': cal['pr_auc'],
        'teacher_xgb_f1_threshold_raw': cal['f1_optimal_threshold'],
        'teacher_xgb_f1_optimal_raw': cal['f1_optimal'],
        'teacher_xgb_youden_threshold': cal['youden_threshold'],
        'teacher_xgb_youden_j': cal['youden_j'],
        'teacher_xgb_calibrated_roc_auc': cal['calibrated_roc_auc'],
        'teacher_xgb_calibrated_pr_auc': cal['calibrated_pr_auc'],
        'teacher_xgb_calibrated_f1_threshold': cal['calibrated_f1_threshold'],
        'teacher_xgb_calibrated_f1_optimal': cal['calibrated_f1_optimal'],
        'sigmoid_params': {'k': 30, 'center': 'p75'},
    }
    results['meta_learner_weights'] = {
        'coef': _CUML_COEF.tolist(),
        'intercept': _CUML_INTERCEPT.tolist(),
        'feature_names': ['recon_err', 'edge_score', 'gat_score', 'uncertainty', 'sage_score', 'xgb_prob', 'lgb_prob'],
    }
    results['notes'] = [
        'Teacher Full Stack achieves F1=1.0 because fraud labels ARE derived from hybrid_score thresholds (CIRCULAR)',
        'The meaningful comparison is Teacher XGB (standalone) vs Student models',
        'Student runs in SIMPLIFIED mode: graph/VAE features zeroed, only XGB+LGB flow through meta-learner',
        'Teacher XGB v1 trained on 171 Kaggle features; Student XGB v2 trained on 71 features (5 tabular + 64 VAE + 2 graph)',
        'Teacher XGB has high ROC-AUC (ranking) but poor F1 (classification) due to compressed score range',
    ]

    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved to: {results_path}")

    print("\n" + "╔" + "═"*78 + "╗")
    print("║" + " EVALUATION COMPLETE ".center(78) + "║")
    print("╚" + "═"*78 + "╝")


if __name__ == '__main__':
    main()
