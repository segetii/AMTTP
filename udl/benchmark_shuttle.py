"""Quick shuttle benchmark: GravityEngine vs IsolationForest + kNN only."""
import sys, os, time, warnings
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'c:/amttp')
warnings.filterwarnings('ignore')

import numpy as np
from scipy.io import loadmat
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import NearestNeighbors, LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from udl.gravity import GravityEngine

X, y = loadmat('c:/amttp/data/external_validation/odds/shuttle.mat', simplify_cells=True).values().__iter__().__next__(), None
d = loadmat('c:/amttp/data/external_validation/odds/shuttle.mat')
X = d['X'].astype(np.float64)
y = d['y'].ravel().astype(int)
n, dim = X.shape
print(f"SHUTTLE  n={n}  d={dim}  anomaly_rate={y.mean():.4f}")

# IsolationForest
t0 = time.perf_counter()
iso = IsolationForest(n_estimators=200, contamination='auto', random_state=42, n_jobs=-1)
iso.fit(X)
scores_if = -iso.decision_function(X)
t_if = time.perf_counter() - t0
auc_if = roc_auc_score(y, scores_if)
ap_if = average_precision_score(y, scores_if)
print(f"  IsolationForest(200)   AUC={auc_if:.4f}  AP={ap_if:.4f}  {t_if:.1f}s")

# kNN
scaler = StandardScaler()
X_s = scaler.fit_transform(X)
t0 = time.perf_counter()
nn = NearestNeighbors(n_neighbors=21, algorithm='brute')
nn.fit(X_s)
dists, _ = nn.kneighbors(X_s)
scores_knn = dists[:, -1]
t_knn = time.perf_counter() - t0
auc_knn = roc_auc_score(y, scores_knn)
ap_knn = average_precision_score(y, scores_knn)
print(f"  kNN (k=20)             AUC={auc_knn:.4f}  AP={ap_knn:.4f}  {t_knn:.1f}s")

# LOF
t0 = time.perf_counter()
lof = LocalOutlierFactor(n_neighbors=20, contamination='auto', novelty=False)
lof.fit_predict(X)
scores_lof = -lof.negative_outlier_factor_
t_lof = time.perf_counter() - t0
auc_lof = roc_auc_score(y, scores_lof)
ap_lof = average_precision_score(y, scores_lof)
print(f"  LOF (k=20)             AUC={auc_lof:.4f}  AP={ap_lof:.4f}  {t_lof:.1f}s")

# GravityEngine
cfg = {
    'alpha': 0.011, 'gamma': 6.06, 'sigma': 2.57,
    'lambda_rep': 0.12, 'eta': 0.013, 'iterations': 52,
    'k_neighbors': 30, 'beta_dev': 0.054,
}
eng = GravityEngine(
    alpha=cfg['alpha'], gamma=cfg['gamma'], sigma=cfg['sigma'],
    lambda_rep=cfg['lambda_rep'], eta=cfg['eta'], iterations=cfg['iterations'],
    normalize=True, track_energy=False, convergence_tol=1e-7,
    k_neighbors=cfg['k_neighbors'], beta_dev=cfg['beta_dev'],
)
t0 = time.perf_counter()
eng.fit_transform(X, time_budget=600)
scores_g = eng.anomaly_scores()
t_g = time.perf_counter() - t0
auc_g = roc_auc_score(y, scores_g)
ap_g = average_precision_score(y, scores_g)
print(f"  GravityEngine          AUC={auc_g:.4f}  AP={ap_g:.4f}  {t_g:.1f}s")

print(f"\nRANKING by AUC:")
ranked = sorted([
    ('IsolationForest', auc_if),
    ('kNN', auc_knn),
    ('LOF', auc_lof),
    ('GravityEngine', auc_g),
], key=lambda x: -x[1])
for i, (nm, a) in enumerate(ranked, 1):
    marker = " <<<" if nm == 'GravityEngine' else ""
    print(f"  {i}. {nm:<20s} AUC={a:.4f}{marker}")
