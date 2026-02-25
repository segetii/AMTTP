"""Test convergence after energy fix + line-search."""
import sys, os, warnings, numpy as np
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'c:/amttp')
warnings.filterwarnings('ignore')
from scipy.io import loadmat
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
from udl.gravity import GravityEngine

d = loadmat('c:/amttp/data/external_validation/odds/mammography.mat')
X, y = d['X'].astype(np.float64), d['y'].ravel().astype(int)
cfg = dict(alpha=0.00496, gamma=0.0396, sigma=0.265, lambda_rep=0.620,
           eta=0.0678, iterations=15, k_neighbors=27, beta_dev=0.088)

print('============================================')
print('  CONVERGENCE TEST (FIXED ENERGY + LINE-SEARCH)')
print('============================================')
print()

eng = GravityEngine(
    alpha=cfg['alpha'], gamma=cfg['gamma'], sigma=cfg['sigma'],
    lambda_rep=cfg['lambda_rep'], eta=cfg['eta'], iterations=cfg['iterations'],
    normalize=True, track_energy=True, convergence_tol=1e-7,
    k_neighbors=cfg['k_neighbors'], beta_dev=cfg['beta_dev'],
)
eng.fit_transform(X, time_budget=600)
scores = eng.anomaly_scores()
auc = roc_auc_score(y, scores)

print(f'  AUC = {auc:.6f}')
print(f'  Energy history: {len(eng.energy_history_)} steps')

if eng.energy_history_:
    E = np.array([e['total'] for e in eng.energy_history_])
    dE = np.diff(E)
    n_dec = np.sum(dE < 0)
    n_inc = np.sum(dE > 0)
    print(f'  E[0] = {E[0]:.4f}  E[-1] = {E[-1]:.4f}')
    print(f'  Steps where energy DECREASED: {n_dec}')
    print(f'  Steps where energy INCREASED: {n_inc}')
    if n_inc == 0:
        print('  RESULT: ENERGY IS MONOTONICALLY DECREASING')
    else:
        print(f'  RESULT: Not fully monotone (max increase: {np.max(dE):.6f})')
    print()
    for i, e in enumerate(eng.energy_history_):
        step = e.get('step', i)
        tag = ''
        if i > 0:
            de = e['total'] - eng.energy_history_[i-1]['total']
            tag = f'  dE={de:+.4f}' + (' UP!' if de > 0 else ' down')
        dev_val = e.get('deviation', 0)
        print(f'  step {step:2d}: E={e["total"]:12.4f}  '
              f'rad={e["radial"]:10.4f}  attr={e["attraction"]:12.4f}  '
              f'rep={e["repulsion"]:12.4f}  dev={dev_val:10.4f}{tag}')

print()
print('=== Fixed-point uniqueness (3 noisy inits) ===')
for seed in [42, 123, 999]:
    np.random.seed(seed)
    noise = np.random.randn(*X.shape) * 0.01 * X.std(axis=0)
    X_n = X + noise
    eng2 = GravityEngine(**cfg, normalize=True, track_energy=False, convergence_tol=1e-7)
    eng2.fit_transform(X_n, time_budget=120)
    s = eng2.anomaly_scores()
    rho, _ = spearmanr(scores, s)
    auc_n = roc_auc_score(y, s)
    print(f'  seed={seed}: AUC={auc_n:.6f}  rho_vs_base={rho:.6f}')

print()
print('DONE')
