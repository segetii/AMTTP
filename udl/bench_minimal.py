"""Minimal benchmark - writes results to file to avoid terminal issues."""
import sys, os, time, json
sys.path.insert(0, 'c:/amttp')

import numpy as np
from scipy.io import loadmat
from sklearn.metrics import roc_auc_score
from udl.gravity import GravityEngine

results = {}

# --- MAMMOGRAPHY ---
d = loadmat('c:/amttp/data/external_validation/odds/mammography.mat')
X, y = d['X'].astype(np.float64), d['y'].ravel().astype(int)
eng = GravityEngine(alpha=0.00496, gamma=0.0396, sigma=0.265,
    lambda_rep=0.620, eta=0.0678, iterations=15, normalize=True,
    track_energy=False, convergence_tol=1e-7, k_neighbors=27,
    beta_dev=0.088, exp_alpha=0.0)
t0 = time.perf_counter()
eng.fit_transform(X, time_budget=600)
t_sim = time.perf_counter() - t0
auc_d = roc_auc_score(y, eng.anomaly_scores())
t1 = time.perf_counter()
se = eng.energy_scores()
t_en = time.perf_counter() - t1
auc_e = roc_auc_score(y, se)
iters = eng.converged_at_ if eng.converged_at_ else 15
results['mammography'] = {
    'sim': round(t_sim, 2), 'iters': iters,
    'energy_t': round(t_en, 2), 'total': round(t_sim + t_en, 2),
    'auc_dist': round(auc_d, 4), 'auc_energy': round(auc_e, 4)
}

# --- SHUTTLE ---
d = loadmat('c:/amttp/data/external_validation/odds/shuttle.mat')
X, y = d['X'].astype(np.float64), d['y'].ravel().astype(int)
eng = GravityEngine(alpha=0.011, gamma=6.06, sigma=2.57,
    lambda_rep=0.12, eta=0.013, iterations=52, normalize=True,
    track_energy=False, convergence_tol=1e-7, k_neighbors=30,
    beta_dev=0.054, exp_alpha=0.0)
t0 = time.perf_counter()
eng.fit_transform(X, time_budget=600)
t_sim = time.perf_counter() - t0
auc_d = roc_auc_score(y, eng.anomaly_scores())
t1 = time.perf_counter()
se = eng.energy_scores()
t_en = time.perf_counter() - t1
auc_e = roc_auc_score(y, se)
iters = eng.converged_at_ if eng.converged_at_ else 52
results['shuttle'] = {
    'sim': round(t_sim, 2), 'iters': iters,
    'energy_t': round(t_en, 2), 'total': round(t_sim + t_en, 2),
    'auc_dist': round(auc_d, 4), 'auc_energy': round(auc_e, 4)
}

# --- PENDIGITS ---
d = loadmat('c:/amttp/data/external_validation/odds/pendigits.mat')
X, y = d['X'].astype(np.float64), d['y'].ravel().astype(int)
eng = GravityEngine(alpha=0.00496, gamma=0.0396, sigma=0.265,
    lambda_rep=0.620, eta=0.0678, iterations=30, normalize=True,
    track_energy=False, convergence_tol=1e-7, k_neighbors=27,
    beta_dev=0.088, exp_alpha=0.0)
t0 = time.perf_counter()
eng.fit_transform(X, time_budget=600)
t_sim = time.perf_counter() - t0
auc_d = roc_auc_score(y, eng.anomaly_scores())
t1 = time.perf_counter()
se = eng.energy_scores()
t_en = time.perf_counter() - t1
auc_e = roc_auc_score(y, se)
iters = eng.converged_at_ if eng.converged_at_ else 30
results['pendigits'] = {
    'sim': round(t_sim, 2), 'iters': iters,
    'energy_t': round(t_en, 2), 'total': round(t_sim + t_en, 2),
    'auc_dist': round(auc_d, 4), 'auc_energy': round(auc_e, 4)
}

# Write results
with open('c:/amttp/bench_results.json', 'w') as f:
    json.dump(results, f, indent=2)

# Also write text summary
with open('c:/amttp/bench_results.txt', 'w') as f:
    prev = {
        'mammography': {'sim': 6.7, 'energy_t': 11.3, 'total': 18.0, 'auc_dist': 0.8972},
        'shuttle':     {'sim': 308.4, 'energy_t': 44.3, 'total': 352.7, 'auc_dist': 0.9830},
        'pendigits':   {'sim': 23.3, 'energy_t': 10.8, 'total': 34.1, 'auc_dist': 0.9187},
    }
    f.write("GRAVITY ENGINE BENCHMARK RESULTS\n")
    f.write("=" * 70 + "\n")
    f.write(f"{'Dataset':<15s} {'Iters':>5s} {'Sim(s)':>8s} {'Enrg(s)':>8s} {'Total(s)':>9s} {'AUC-d':>7s} {'AUC-e':>7s} {'Old(s)':>8s} {'Speedup':>8s}\n")
    f.write("-" * 70 + "\n")
    for name, r in results.items():
        old = prev.get(name, {}).get('total', 0)
        spd = old / r['total'] if r['total'] > 0 else 0
        f.write(f"{name:<15s} {r['iters']:>5d} {r['sim']:>8.1f} {r['energy_t']:>8.1f} {r['total']:>9.1f} {r['auc_dist']:>7.4f} {r['auc_energy']:>7.4f} {old:>8.1f} {spd:>7.2f}x\n")
    f.write("-" * 70 + "\n")
    f.write("DONE\n")
