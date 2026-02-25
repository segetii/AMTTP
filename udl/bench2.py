"""Minimal benchmark - all output goes to bench2_results.txt"""
import sys, os, time, traceback
sys.path.insert(0, 'c:/amttp')

OUT = 'c:/amttp/bench2_results.txt'

def log(msg):
    with open(OUT, 'a') as f:
        f.write(msg + '\n')
    print(msg)  # also print for terminal visibility

# Clear file
with open(OUT, 'w') as f:
    f.write('')

try:
    import numpy as np
    from scipy.io import loadmat
    from sklearn.metrics import roc_auc_score
    from udl.gravity import GravityEngine

    datasets = [
        ('mammography', {
            'alpha': 0.00496, 'gamma': 0.0396, 'sigma': 0.265,
            'lambda_rep': 0.620, 'eta': 0.0678, 'iterations': 15,
            'k_neighbors': 27, 'beta_dev': 0.088, 'exp_alpha': 0.0,
        }),
        ('shuttle', {
            'alpha': 0.011, 'gamma': 6.06, 'sigma': 2.57,
            'lambda_rep': 0.12, 'eta': 0.013, 'iterations': 52,
            'k_neighbors': 30, 'beta_dev': 0.054, 'exp_alpha': 0.0,
        }),
        ('pendigits', {
            'alpha': 0.00496, 'gamma': 0.0396, 'sigma': 0.265,
            'lambda_rep': 0.620, 'eta': 0.0678, 'iterations': 30,
            'k_neighbors': 27, 'beta_dev': 0.088, 'exp_alpha': 0.0,
        }),
    ]

    prev_total = {'mammography': 18.0, 'shuttle': 352.7, 'pendigits': 34.1}
    prev_auc = {'mammography': 0.8972, 'shuttle': 0.9830, 'pendigits': 0.9187}

    log("GRAVITY ENGINE BENCHMARK")
    log("=" * 70)

    for name, params in datasets:
        try:
            d = loadmat(f'c:/amttp/data/external_validation/odds/{name}.mat')
            X = d['X'].astype(np.float64)
            y = d['y'].ravel().astype(int)
            n = X.shape[0]

            eng = GravityEngine(
                alpha=params['alpha'], gamma=params['gamma'],
                sigma=params['sigma'], lambda_rep=params['lambda_rep'],
                eta=params['eta'], iterations=params['iterations'],
                normalize=True, track_energy=False, convergence_tol=1e-7,
                k_neighbors=params.get('k_neighbors', 0),
                beta_dev=params.get('beta_dev', 0.0),
                exp_alpha=params.get('exp_alpha', 0.0),
            )

            t0 = time.perf_counter()
            eng.fit_transform(X, time_budget=600)
            t_sim = time.perf_counter() - t0
            iters = eng.converged_at_ if eng.converged_at_ else params['iterations']

            auc_d = roc_auc_score(y, eng.anomaly_scores())

            t1 = time.perf_counter()
            se = eng.energy_scores()
            t_en = time.perf_counter() - t1
            if np.any(np.isnan(se)) or np.any(np.isinf(se)):
                auc_e = 0.0
            else:
                auc_e = roc_auc_score(y, se)

            total = t_sim + t_en
            old_t = prev_total.get(name, 0)
            spd = old_t / total if total > 0 else 0
            old_auc = prev_auc.get(name, 0)
            auc_diff = auc_d - old_auc

            log(f"{name}: n={n} iters={iters} sim={t_sim:.1f}s energy={t_en:.1f}s total={total:.1f}s")
            log(f"  AUC_dist={auc_d:.4f} AUC_energy={auc_e:.4f}")
            log(f"  vs_old: {old_t:.1f}s -> {total:.1f}s ({spd:.2f}x) AUC_diff={auc_diff:+.4f}")
            log("")
        except Exception as e:
            log(f"{name}: FAILED - {e}")
            log(traceback.format_exc())

    log("DONE")

except Exception as e:
    log(f"FATAL: {e}")
    log(traceback.format_exc())
