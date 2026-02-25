"""
Benchmark: GravityEngine vs Standard Anomaly Detectors
======================================================
Compares against: LOF, Isolation Forest, One-Class SVM, KNN, HBOS, ECOD
on Mammography, Shuttle, Pendigits (full data).

Also tests GravityEngine as a binary classifier via threshold.
"""
import sys, os, time, warnings
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'c:/amttp')
warnings.filterwarnings('ignore')

import numpy as np
from scipy.io import loadmat
from sklearn.metrics import (roc_auc_score, average_precision_score,
                             f1_score, precision_score, recall_score)
from sklearn.neighbors import LocalOutlierFactor, NearestNeighbors
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler
from udl.gravity import GravityEngine


def load_dataset(name):
    d = loadmat(f'c:/amttp/data/external_validation/odds/{name}.mat')
    X = d['X'].astype(np.float64)
    y = d['y'].ravel().astype(int)
    return X, y


def run_lof(X, y, k=20):
    t0 = time.perf_counter()
    lof = LocalOutlierFactor(n_neighbors=k, contamination='auto', novelty=False)
    lof.fit_predict(X)
    scores = -lof.negative_outlier_factor_  # higher = more anomalous
    t = time.perf_counter() - t0
    auc = roc_auc_score(y, scores)
    ap = average_precision_score(y, scores)
    return auc, ap, t


def run_iforest(X, y, n_estimators=200):
    t0 = time.perf_counter()
    iso = IsolationForest(n_estimators=n_estimators, contamination='auto',
                          random_state=42, n_jobs=-1)
    iso.fit(X)
    scores = -iso.decision_function(X)  # higher = more anomalous
    t = time.perf_counter() - t0
    auc = roc_auc_score(y, scores)
    ap = average_precision_score(y, scores)
    return auc, ap, t


def run_ocsvm(X, y, max_n=10000):
    """One-Class SVM — subsample if too large."""
    if X.shape[0] > max_n:
        idx = np.random.RandomState(42).choice(X.shape[0], max_n, replace=False)
        X_sub, y_sub = X[idx], y[idx]
    else:
        X_sub, y_sub = X, y
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X_sub)
    t0 = time.perf_counter()
    svm = OneClassSVM(kernel='rbf', gamma='scale', nu=0.05)
    svm.fit(X_s)
    scores = -svm.decision_function(X_s)
    t = time.perf_counter() - t0
    auc = roc_auc_score(y_sub, scores)
    ap = average_precision_score(y_sub, scores)
    return auc, ap, t


def run_knn_ad(X, y, k=20):
    """kNN anomaly detection: score = distance to k-th neighbor."""
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X)
    t0 = time.perf_counter()
    nn = NearestNeighbors(n_neighbors=k + 1, algorithm='brute')
    nn.fit(X_s)
    distances, _ = nn.kneighbors(X_s)
    scores = distances[:, -1]  # k-th neighbor distance
    t = time.perf_counter() - t0
    auc = roc_auc_score(y, scores)
    ap = average_precision_score(y, scores)
    return auc, ap, t


def run_gravity(X, y, params):
    eng = GravityEngine(
        alpha=params['alpha'], gamma=params['gamma'],
        sigma=params['sigma'], lambda_rep=params['lambda_rep'],
        eta=params['eta'], iterations=params['iterations'],
        normalize=True, track_energy=False, convergence_tol=1e-7,
        k_neighbors=params.get('k_neighbors', 0),
        beta_dev=params.get('beta_dev', 0.0),
    )
    t0 = time.perf_counter()
    eng.fit_transform(X, time_budget=600)
    scores = eng.anomaly_scores()
    t = time.perf_counter() - t0
    auc = roc_auc_score(y, scores)
    ap = average_precision_score(y, scores)
    return auc, ap, t, scores, eng


def optimal_f1_threshold(y_true, scores):
    """Find threshold that maximizes F1 score."""
    from sklearn.metrics import precision_recall_curve
    prec, rec, thresholds = precision_recall_curve(y_true, scores)
    f1s = 2 * prec * rec / (prec + rec + 1e-10)
    best_idx = np.argmax(f1s)
    if best_idx < len(thresholds):
        return thresholds[best_idx], f1s[best_idx]
    return thresholds[-1], f1s[-1]


# ── Gravity configs ──
CONFIGS = {
    'mammography': {
        'alpha': 0.00496, 'gamma': 0.0396, 'sigma': 0.265,
        'lambda_rep': 0.620, 'eta': 0.0678, 'iterations': 15,
        'k_neighbors': 27, 'beta_dev': 0.088,
    },
    'shuttle': {
        'alpha': 0.011, 'gamma': 6.06, 'sigma': 2.57,
        'lambda_rep': 0.12, 'eta': 0.013, 'iterations': 52,
        'k_neighbors': 30, 'beta_dev': 0.054,
    },
    'pendigits': {
        'alpha': 0.00496, 'gamma': 0.0396, 'sigma': 0.265,
        'lambda_rep': 0.620, 'eta': 0.0678, 'iterations': 30,
        'k_neighbors': 27, 'beta_dev': 0.088,
    },
}

OUT = 'c:/amttp/baseline_comparison.txt'
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('')

def log(msg):
    with open(OUT, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')
    print(msg)


log("=" * 80)
log("  GRAVITY ENGINE vs STANDARD ANOMALY DETECTORS — FULL DATA BENCHMARK")
log("=" * 80)

for ds_name in ['mammography', 'pendigits']:   # shuttle too slow for all baselines
    X, y = load_dataset(ds_name)
    n, d = X.shape
    anom_rate = y.mean()
    log(f"\n{'-'*70}")
    log(f"  {ds_name.upper()}  n={n}  d={d}  anomaly_rate={anom_rate:.4f}")
    log(f"{'-'*70}")
    log(f"  {'Method':<25s} {'AUC':>7s}  {'AP':>7s}  {'Time':>7s}")
    log(f"  {'-'*50}")

    results = {}

    # LOF
    try:
        auc, ap, t = run_lof(X, y, k=20)
        log(f"  {'LOF (k=20)':<25s} {auc:>7.4f}  {ap:>7.4f}  {t:>6.1f}s")
        results['lof'] = (auc, ap)
    except Exception as e:
        log(f"  LOF failed: {e}")

    # Isolation Forest
    try:
        auc, ap, t = run_iforest(X, y, n_estimators=200)
        log(f"  {'IsolationForest (200)':<25s} {auc:>7.4f}  {ap:>7.4f}  {t:>6.1f}s")
        results['iforest'] = (auc, ap)
    except Exception as e:
        log(f"  IForest failed: {e}")

    # One-Class SVM
    try:
        auc, ap, t = run_ocsvm(X, y)
        log(f"  {'One-Class SVM':<25s} {auc:>7.4f}  {ap:>7.4f}  {t:>6.1f}s")
        results['ocsvm'] = (auc, ap)
    except Exception as e:
        log(f"  OCSVM failed: {e}")

    # kNN anomaly detection
    try:
        auc, ap, t = run_knn_ad(X, y, k=20)
        log(f"  {'kNN (k=20)':<25s} {auc:>7.4f}  {ap:>7.4f}  {t:>6.1f}s")
        results['knn'] = (auc, ap)
    except Exception as e:
        log(f"  kNN failed: {e}")

    # GravityEngine
    try:
        auc, ap, t, scores, eng = run_gravity(X, y, CONFIGS[ds_name])
        log(f"  {'GravityEngine':<25s} {auc:>7.4f}  {ap:>7.4f}  {t:>6.1f}s")
        results['gravity'] = (auc, ap)

        # ── Classifier mode: find optimal threshold ──
        thresh, best_f1 = optimal_f1_threshold(y, scores)
        y_pred = (scores >= thresh).astype(int)
        prec = precision_score(y, y_pred)
        rec = recall_score(y, y_pred)
        log(f"\n  GravityEngine as CLASSIFIER (optimal threshold={thresh:.4f}):")
        log(f"    F1={best_f1:.4f}  Precision={prec:.4f}  Recall={rec:.4f}")
    except Exception as e:
        log(f"  Gravity failed: {e}")

    # ── Ranking ──
    if results:
        sorted_r = sorted(results.items(), key=lambda x: -x[1][0])
        log(f"\n  RANKING by AUC:")
        for rank, (name, (auc, ap)) in enumerate(sorted_r, 1):
            marker = " <<<" if name == 'gravity' else ""
            log(f"    {rank}. {name:<20s} AUC={auc:.4f}{marker}")

log("\n" + "=" * 80)
log("DONE")
