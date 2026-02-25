"""Quick focused pendigits test — best coordinate configs only."""
import sys, os, time, warnings
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'c:/amttp')
warnings.filterwarnings('ignore')

import numpy as np
from scipy.io import loadmat
from scipy.stats import rankdata
from sklearn.metrics import roc_auc_score, average_precision_score
from udl.gravity import GravityEngine
from udl.coordinates import CoefficientCoordinates

def load_dataset(name):
    d = loadmat(f'c:/amttp/data/external_validation/odds/{name}.mat')
    return d['X'].astype(np.float64), d['y'].ravel().astype(int)

cfg = dict(alpha=0.00496, gamma=0.0396, sigma=0.265,
           lambda_rep=0.620, eta=0.0678, iterations=30,
           k_neighbors=27, beta_dev=0.088)

X, y = load_dataset('pendigits')
n, d = X.shape
print(f"PENDIGITS  n={n}  d={d}")

def run_g(data, iters=20, k=20):
    c = cfg.copy()
    c['iterations'] = iters
    c['k_neighbors'] = min(k, data.shape[0]//10)
    eng = GravityEngine(alpha=c['alpha'], gamma=c['gamma'], sigma=c['sigma'],
                        lambda_rep=c['lambda_rep'], eta=c['eta'], iterations=c['iterations'],
                        normalize=True, track_energy=False, convergence_tol=1e-7,
                        k_neighbors=c['k_neighbors'], beta_dev=c['beta_dev'])
    t0 = time.perf_counter()
    eng.fit_transform(data, time_budget=300)
    dist = eng.anomaly_scores()
    energy = eng.energy_scores()
    t = time.perf_counter() - t0
    auc_d = roc_auc_score(y, dist)
    auc_e = roc_auc_score(y, energy)
    ens = (rankdata(dist) + rankdata(energy)) / 2
    auc_ens = roc_auc_score(y, ens)
    return auc_d, auc_e, auc_ens, t, dist, energy

# Raw baseline
auc_d, auc_e, auc_ens, t, dist_raw, energy_raw = run_g(X, iters=30, k=27)
raw_best = max(auc_d, auc_ens)
print(f"  RAW (d={d}):  AUC_d={auc_d:.4f} AUC_e={auc_e:.4f} AUC_ens={auc_ens:.4f}  {t:.0f}s  best={raw_best:.4f}")

# Best configs from mammography: variance p=1 s=3, sorted p=3 s=2, multi sor+var p=3 s=2
tests = [
    ('variance', [1], [3]),
    ('sorted',   [3], [2]),
    ('raw',      [2], [2]),
    ('variance', [2], [2]),
]
for view, pds, nss in tests:
    for pd in pds:
        for ns in nss:
            cc = CoefficientCoordinates(views=[view], poly_degree=pd, n_spectral=ns)
            Theta, names = cc.fit_transform(X)
            auc_d, auc_e, auc_ens, t, dist_c, energy_c = run_g(Theta)
            best = max(auc_d, auc_ens)
            m = " ***" if best > raw_best else ""
            print(f"  {view:>9s} p={pd} s={ns} d={Theta.shape[1]:>2d}: "
                  f"AUC_d={auc_d:.4f} AUC_e={auc_e:.4f} AUC_ens={auc_ens:.4f}  {t:.0f}s{m}")

            # Score fusion
            fuse = (rankdata(dist_raw) + rankdata(dist_c)) / 2
            auc_f = roc_auc_score(y, fuse)
            m2 = " ***" if auc_f > raw_best else ""
            print(f"            fusion raw+coord: AUC={auc_f:.4f}{m2}")

# Multi-view: sorted+variance p=3 s=2
cc = CoefficientCoordinates(views=['sorted','variance'], poly_degree=3, n_spectral=2)
Theta, names = cc.fit_transform(X)
auc_d, auc_e, auc_ens, t, dist_c, energy_c = run_g(Theta)
best = max(auc_d, auc_ens)
m = " ***" if best > raw_best else ""
print(f"  sor+var p=3 s=2 d={Theta.shape[1]:>2d}: "
      f"AUC_d={auc_d:.4f} AUC_e={auc_e:.4f} AUC_ens={auc_ens:.4f}  {t:.0f}s{m}")
fuse = (rankdata(dist_raw) + rankdata(dist_c)) / 2
auc_f = roc_auc_score(y, fuse)
m2 = " ***" if auc_f > raw_best else ""
print(f"            fusion raw+coord: AUC={auc_f:.4f}{m2}")

# Triple fusion
fuse3 = (rankdata(dist_raw) + rankdata(dist_c) + rankdata(energy_raw)) / 3
auc_t = roc_auc_score(y, fuse3)
m3 = " ***" if auc_t > raw_best else ""
print(f"            triple fusion:    AUC={auc_t:.4f}{m3}")
