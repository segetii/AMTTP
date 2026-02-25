"""
Calibration Benchmark: GravityEngine scores -> calibrated probabilities -> classifier
=====================================================================================
Uses 5-fold stratified CV to fit calibration (isotonic / Platt) on held-out folds,
then reports calibrated AUC, AP, Brier score, F1, precision, recall, and FPR-controlled thresholds.
"""
import sys, os, time, warnings
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'c:/amttp')
warnings.filterwarnings('ignore')

import numpy as np
from scipy.io import loadmat
from sklearn.metrics import (roc_auc_score, average_precision_score,
                             f1_score, precision_score, recall_score,
                             brier_score_loss, precision_recall_curve,
                             confusion_matrix)
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from udl.gravity import GravityEngine

OUT = 'c:/amttp/calibration_results.txt'

def log(msg):
    with open(OUT, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')
    print(msg)

# Reset output
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('')


def load_dataset(name):
    d = loadmat(f'c:/amttp/data/external_validation/odds/{name}.mat')
    X = d['X'].astype(np.float64)
    y = d['y'].ravel().astype(int)
    return X, y


def calibrate_scores(scores_train, y_train, scores_test, method='isotonic'):
    """Fit calibration on train scores, apply to test scores."""
    if method == 'isotonic':
        cal = IsotonicRegression(y_min=0, y_max=1, out_of_bounds='clip')
        cal.fit(scores_train, y_train)
        return cal.transform(scores_test)
    elif method == 'platt':
        lr = LogisticRegression(C=1.0, solver='lbfgs', max_iter=1000)
        lr.fit(scores_train.reshape(-1, 1), y_train)
        return lr.predict_proba(scores_test.reshape(-1, 1))[:, 1]
    else:
        raise ValueError(f"Unknown calibration method: {method}")


def optimal_f1_threshold(y_true, probs):
    """Find threshold maximizing F1."""
    prec, rec, thresholds = precision_recall_curve(y_true, probs)
    f1s = 2 * prec * rec / (prec + rec + 1e-10)
    best_idx = np.argmax(f1s)
    if best_idx < len(thresholds):
        return thresholds[best_idx], f1s[best_idx]
    return thresholds[-1], f1s[-1]


def fpr_controlled_threshold(y_true, probs, target_fpr=0.05):
    """Find threshold that yields FPR <= target_fpr."""
    normals = probs[y_true == 0]
    # threshold = quantile of normal scores such that FPR = target_fpr
    thresh = np.percentile(normals, 100 * (1 - target_fpr))
    y_pred = (probs >= thresh).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
    tpr = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = f1_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    return thresh, fpr, tpr, f1, prec, rec


CONFIGS = {
    'mammography': {
        'alpha': 0.00496, 'gamma': 0.0396, 'sigma': 0.265,
        'lambda_rep': 0.620, 'eta': 0.0678, 'iterations': 15,
        'k_neighbors': 27, 'beta_dev': 0.088,
    },
    'pendigits': {
        'alpha': 0.00496, 'gamma': 0.0396, 'sigma': 0.265,
        'lambda_rep': 0.620, 'eta': 0.0678, 'iterations': 30,
        'k_neighbors': 27, 'beta_dev': 0.088,
    },
    'shuttle': {
        'alpha': 0.011, 'gamma': 6.06, 'sigma': 2.57,
        'lambda_rep': 0.12, 'eta': 0.013, 'iterations': 52,
        'k_neighbors': 30, 'beta_dev': 0.054,
    },
}


log("=" * 80)
log("  GRAVITY ENGINE - SCORE CALIBRATION & CLASSIFIER EVALUATION")
log("=" * 80)

for ds_name in ['mammography', 'pendigits', 'shuttle']:
    X, y = load_dataset(ds_name)
    n, d = X.shape
    anom_rate = y.mean()
    n_anom = y.sum()
    log(f"\n{'-'*70}")
    log(f"  {ds_name.upper()}  n={n}  d={d}  anomalies={n_anom} ({anom_rate:.2%})")
    log(f"{'-'*70}")

    # ── Step 1: Run GravityEngine (full data) ──
    cfg = CONFIGS[ds_name]
    eng = GravityEngine(
        alpha=cfg['alpha'], gamma=cfg['gamma'], sigma=cfg['sigma'],
        lambda_rep=cfg['lambda_rep'], eta=cfg['eta'], iterations=cfg['iterations'],
        normalize=True, track_energy=False, convergence_tol=1e-7,
        k_neighbors=cfg['k_neighbors'], beta_dev=cfg['beta_dev'],
    )
    t0 = time.perf_counter()
    eng.fit_transform(X, time_budget=600)
    raw_scores = eng.anomaly_scores()
    t_gravity = time.perf_counter() - t0

    # Also get energy scores
    energy_scores = eng.energy_scores()

    raw_auc = roc_auc_score(y, raw_scores)
    raw_ap = average_precision_score(y, raw_scores)
    energy_auc = roc_auc_score(y, energy_scores)
    energy_ap = average_precision_score(y, energy_scores)

    log(f"\n  RAW SCORES (no calibration):")
    log(f"    Distance:  AUC={raw_auc:.4f}  AP={raw_ap:.4f}  ({t_gravity:.1f}s)")
    log(f"    Energy:    AUC={energy_auc:.4f}  AP={energy_ap:.4f}")

    # ── Step 2: Cross-validated calibration ──
    # Use 5-fold stratified CV to avoid overfitting the calibration
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    for score_name, scores in [('distance', raw_scores), ('energy', energy_scores)]:
        for cal_method in ['isotonic', 'platt']:
            cal_probs = np.zeros(n)

            for train_idx, test_idx in skf.split(X, y):
                s_train, y_train = scores[train_idx], y[train_idx]
                s_test = scores[test_idx]
                cal_probs[test_idx] = calibrate_scores(s_train, y_train, s_test, method=cal_method)

            # Metrics on calibrated probabilities
            cal_auc = roc_auc_score(y, cal_probs)
            cal_ap = average_precision_score(y, cal_probs)
            brier = brier_score_loss(y, cal_probs)

            # Optimal F1 threshold
            thresh_f1, best_f1 = optimal_f1_threshold(y, cal_probs)
            y_pred_f1 = (cal_probs >= thresh_f1).astype(int)
            prec_f1 = precision_score(y, y_pred_f1, zero_division=0)
            rec_f1 = recall_score(y, y_pred_f1, zero_division=0)

            # FPR-controlled thresholds
            results_fpr = {}
            for target_fpr in [0.01, 0.05, 0.10]:
                th, fpr, tpr, f1, prec, rec = fpr_controlled_threshold(y, cal_probs, target_fpr)
                results_fpr[target_fpr] = (th, fpr, tpr, f1, prec, rec)

            log(f"\n  {score_name.upper()} + {cal_method.upper()} calibration (5-fold CV):")
            log(f"    AUC={cal_auc:.4f}  AP={cal_ap:.4f}  Brier={brier:.4f}")
            log(f"    Probability range: [{cal_probs.min():.4f}, {cal_probs.max():.4f}]")
            log(f"    Mean P(anomaly) for normals: {cal_probs[y==0].mean():.4f}")
            log(f"    Mean P(anomaly) for anomalies: {cal_probs[y==1].mean():.4f}")
            log(f"")
            log(f"    CLASSIFIER (optimal F1 threshold = {thresh_f1:.4f}):")
            log(f"      F1={best_f1:.4f}  Precision={prec_f1:.4f}  Recall={rec_f1:.4f}")
            log(f"")
            log(f"    FPR-CONTROLLED THRESHOLDS:")
            log(f"      {'Target FPR':>12s}  {'Actual FPR':>12s}  {'TPR/Recall':>12s}  {'F1':>7s}  {'Precision':>10s}")
            for tfpr in [0.01, 0.05, 0.10]:
                th, fpr, tpr, f1, prec, rec = results_fpr[tfpr]
                log(f"      {tfpr:>12.2%}  {fpr:>12.4f}  {tpr:>12.4f}  {f1:>7.4f}  {prec:>10.4f}")

    # ── Step 3: Ensemble (distance + energy) calibrated ──
    log(f"\n  ENSEMBLE (distance + energy, isotonic, rank-averaged):")
    # Rank-average the two calibrated probability streams
    from scipy.stats import rankdata
    cal_dist = np.zeros(n)
    cal_ener = np.zeros(n)
    for train_idx, test_idx in skf.split(X, y):
        cal_dist[test_idx] = calibrate_scores(raw_scores[train_idx], y[train_idx],
                                               raw_scores[test_idx], 'isotonic')
        cal_ener[test_idx] = calibrate_scores(energy_scores[train_idx], y[train_idx],
                                               energy_scores[test_idx], 'isotonic')
    ensemble_probs = (cal_dist + cal_ener) / 2.0
    ens_auc = roc_auc_score(y, ensemble_probs)
    ens_ap = average_precision_score(y, ensemble_probs)
    ens_brier = brier_score_loss(y, ensemble_probs)
    thresh_ens, f1_ens = optimal_f1_threshold(y, ensemble_probs)
    y_pred_ens = (ensemble_probs >= thresh_ens).astype(int)
    prec_ens = precision_score(y, y_pred_ens, zero_division=0)
    rec_ens = recall_score(y, y_pred_ens, zero_division=0)

    log(f"    AUC={ens_auc:.4f}  AP={ens_ap:.4f}  Brier={ens_brier:.4f}")
    log(f"    F1={f1_ens:.4f}  Precision={prec_ens:.4f}  Recall={rec_ens:.4f}")

    # FPR-controlled for ensemble
    log(f"    FPR-controlled:")
    for target_fpr in [0.01, 0.05, 0.10]:
        th, fpr, tpr, f1, prec, rec = fpr_controlled_threshold(y, ensemble_probs, target_fpr)
        log(f"      FPR<={target_fpr:.0%}: actual_FPR={fpr:.4f}  TPR={tpr:.4f}  F1={f1:.4f}  Prec={prec:.4f}")


log("\n" + "=" * 80)
log("DONE")
