"""
Functional Feature Extraction + GravityEngine — Benchmark
===========================================================
Pipeline:  Raw x → FunctionalExtractor → θ → GravityEngine → anomaly scores

Compares:
  1. GravityEngine on RAW features (baseline)
  2. GravityEngine on FUNCTIONAL coefficients (sorted ordering)
  3. GravityEngine on FUNCTIONAL coefficients (variance ordering)
  4. GravityEngine on FUNCTIONAL coefficients (raw ordering)
  5. IsolationForest on FUNCTIONAL coefficients (for reference)
  6. Standalone baselines: LOF, IF, kNN on raw (from prior benchmark)

Tests all 3 datasets: mammography, pendigits, shuttle.
"""
import sys, os, time, warnings
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'c:/amttp')
warnings.filterwarnings('ignore')

import numpy as np
from scipy.io import loadmat
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from udl.gravity import GravityEngine
from udl.functional import FunctionalExtractor

OUT = 'c:/amttp/functional_benchmark.txt'

def log(msg):
    with open(OUT, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')
    print(msg)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('')


def load_dataset(name):
    d = loadmat(f'c:/amttp/data/external_validation/odds/{name}.mat')
    X = d['X'].astype(np.float64)
    y = d['y'].ravel().astype(int)
    return X, y


# Known best configs for raw GravityEngine
GRAVITY_CONFIGS = {
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

# For functional space, start with mammography config as base (works well across datasets)
FUNC_GRAVITY_CONFIG = {
    'alpha': 0.00496, 'gamma': 0.0396, 'sigma': 0.265,
    'lambda_rep': 0.620, 'eta': 0.0678, 'iterations': 20,
    'k_neighbors': 20, 'beta_dev': 0.088,
}


def run_gravity(X, y, params, label='GravityEngine'):
    eng = GravityEngine(
        alpha=params['alpha'], gamma=params['gamma'],
        sigma=params['sigma'], lambda_rep=params['lambda_rep'],
        eta=params['eta'], iterations=params['iterations'],
        normalize=True, track_energy=False, convergence_tol=1e-7,
        k_neighbors=params.get('k_neighbors', 0),
        beta_dev=params.get('beta_dev', 0.0),
    )
    t0 = time.perf_counter()
    eng.fit_transform(X, time_budget=300)
    dist_scores = eng.anomaly_scores()
    energy_scores = eng.energy_scores()
    t = time.perf_counter() - t0

    auc_d = roc_auc_score(y, dist_scores)
    auc_e = roc_auc_score(y, energy_scores)
    ap_d = average_precision_score(y, dist_scores)

    # Rank ensemble
    from scipy.stats import rankdata
    r_d = rankdata(dist_scores)
    r_e = rankdata(energy_scores)
    ensemble = (r_d + r_e) / 2
    auc_ens = roc_auc_score(y, ensemble)

    return auc_d, auc_e, auc_ens, ap_d, t


def run_iforest(X, y):
    iso = IsolationForest(n_estimators=200, contamination='auto', random_state=42, n_jobs=-1)
    t0 = time.perf_counter()
    iso.fit(X)
    scores = -iso.decision_function(X)
    t = time.perf_counter() - t0
    return roc_auc_score(y, scores), average_precision_score(y, scores), t


def run_lof(X, y, k=20):
    t0 = time.perf_counter()
    lof = LocalOutlierFactor(n_neighbors=k, contamination='auto', novelty=False)
    lof.fit_predict(X)
    scores = -lof.negative_outlier_factor_
    t = time.perf_counter() - t0
    return roc_auc_score(y, scores), average_precision_score(y, scores), t


log("=" * 80)
log("  FUNCTIONAL FEATURE EXTRACTION + GRAVITY ENGINE BENCHMARK")
log("=" * 80)
log("")
log("Pipeline: Raw x -> FunctionalExtractor -> theta -> GravityEngine -> scores")
log("Extraction: polynomial coeffs + DCT spectrum + stats + wavelets + gradients")
log("")

for ds_name in ['mammography', 'pendigits', 'shuttle']:
    X, y = load_dataset(ds_name)
    n, d = X.shape
    anom_rate = y.mean()

    log(f"\n{'='*70}")
    log(f"  {ds_name.upper()}  n={n}  d={d}  anomaly_rate={anom_rate:.4f}")
    log(f"{'='*70}")

    # ── 1. Raw GravityEngine (baseline) ──
    log(f"\n  [1] GravityEngine on RAW features (d={d})")
    try:
        auc_d, auc_e, auc_ens, ap_d, t = run_gravity(X, y, GRAVITY_CONFIGS[ds_name])
        log(f"      AUC(dist)={auc_d:.4f}  AUC(energy)={auc_e:.4f}  AUC(ens)={auc_ens:.4f}  AP={ap_d:.4f}  {t:.1f}s")
        raw_best = max(auc_d, auc_ens)
    except Exception as e:
        log(f"      FAILED: {e}")
        raw_best = 0

    # ── 2. Functional extraction + GravityEngine (multiple orderings) ──
    for ordering in ['sorted', 'variance', 'raw']:
        for n_dct in [5, 8]:
            for poly_deg in [3, 5]:
                fe = FunctionalExtractor(
                    ordering=ordering, poly_degree=poly_deg, n_dct=n_dct,
                    include_stats=True, include_wavelets=True, standardize=True,
                )
                Theta, feat_names = fe.fit_transform(X)
                k = Theta.shape[1]

                # Adjust k_neighbors if needed
                func_cfg = FUNC_GRAVITY_CONFIG.copy()
                func_cfg['k_neighbors'] = min(func_cfg['k_neighbors'], n // 10)
                if ds_name == 'shuttle':
                    func_cfg['iterations'] = 15  # faster for shuttle

                try:
                    auc_d, auc_e, auc_ens, ap_d, t = run_gravity(Theta, y, func_cfg)
                    best = max(auc_d, auc_ens)
                    marker = " ***" if best > raw_best else ""
                    log(f"  [F] {ordering:>8s} poly={poly_deg} dct={n_dct} -> d={k:>2d}  "
                        f"AUC(d)={auc_d:.4f} AUC(e)={auc_e:.4f} AUC(ens)={auc_ens:.4f} AP={ap_d:.4f} {t:.1f}s{marker}")
                except Exception as e:
                    log(f"  [F] {ordering:>8s} poly={poly_deg} dct={n_dct} -> d={k:>2d}  FAILED: {e}")

    # ── 3. Functional + IsolationForest (reference) ──
    fe_best = FunctionalExtractor(ordering='sorted', poly_degree=3, n_dct=5,
                                   include_stats=True, include_wavelets=True, standardize=True)
    Theta_best, _ = fe_best.fit_transform(X)
    try:
        auc_if, ap_if, t_if = run_iforest(Theta_best, y)
        log(f"  [IF] IsolationForest on sorted functional (d={Theta_best.shape[1]})  AUC={auc_if:.4f}  AP={ap_if:.4f}  {t_if:.1f}s")
    except Exception as e:
        log(f"  [IF] FAILED: {e}")

    # ── 4. LOF on functional ──
    try:
        auc_lof, ap_lof, t_lof = run_lof(Theta_best, y)
        log(f"  [LOF] LOF on sorted functional (d={Theta_best.shape[1]})  AUC={auc_lof:.4f}  AP={ap_lof:.4f}  {t_lof:.1f}s")
    except Exception as e:
        log(f"  [LOF] FAILED: {e}")

    # ── 5. Show what features were extracted ──
    fe_show = FunctionalExtractor(ordering='sorted', poly_degree=3, n_dct=5)
    Theta_show, names_show = fe_show.fit_transform(X[:5])
    log(f"\n  Extracted {len(names_show)} features: {names_show}")


log("\n" + "=" * 80)
log("DONE")
log("")
log("*** = functional representation BEATS raw feature GravityEngine")
