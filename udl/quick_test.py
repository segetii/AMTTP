"""Quick sanity: mammography only, ~15s."""
import sys, time
sys.path.insert(0, 'c:/amttp')
import numpy as np
from scipy.io import loadmat
from sklearn.metrics import roc_auc_score
from udl.gravity import GravityEngine

d = loadmat('c:/amttp/data/external_validation/odds/mammography.mat')
X, y = d['X'].astype(np.float64), d['y'].ravel().astype(int)

eng = GravityEngine(alpha=0.00496, gamma=0.0396, sigma=0.265,
    lambda_rep=0.620, eta=0.0678, iterations=15, normalize=True,
    track_energy=False, convergence_tol=1e-7, k_neighbors=27, beta_dev=0.088)

t0 = time.perf_counter()
eng.fit_transform(X)
t_sim = time.perf_counter() - t0

auc = roc_auc_score(y, eng.anomaly_scores())

t1 = time.perf_counter()
se = eng.energy_scores()
t_en = time.perf_counter() - t1
auc_e = roc_auc_score(y, se)

with open('c:/amttp/quick_result.txt', 'w') as f:
    f.write(f"sim={t_sim:.1f}s auc_d={auc:.4f} energy={t_en:.1f}s auc_e={auc_e:.4f} total={t_sim+t_en:.1f}s\n")
print(f"sim={t_sim:.1f}s auc_d={auc:.4f} energy={t_en:.1f}s auc_e={auc_e:.4f} total={t_sim+t_en:.1f}s")
