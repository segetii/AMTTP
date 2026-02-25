"""
Quick focused test: Raw+Functional concatenation and individual best configs.
"""
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
from udl.functional import FunctionalExtractor

OUT = 'c:/amttp/functional_focused.txt'

def log(msg):
    with open(OUT, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')
    print(msg)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('')


def load_dataset(name):
    d = loadmat(f'c:/amttp/data/external_validation/odds/{name}.mat')
    return d['X'].astype(np.float64), d['y'].ravel().astype(int)


GRAVITY_CONFIGS = {
    'mammography': dict(alpha=0.00496, gamma=0.0396, sigma=0.265,
                        lambda_rep=0.620, eta=0.0678, iterations=15,
                        k_neighbors=27, beta_dev=0.088),
    'pendigits': dict(alpha=0.00496, gamma=0.0396, sigma=0.265,
                      lambda_rep=0.620, eta=0.0678, iterations=30,
                      k_neighbors=27, beta_dev=0.088),
}


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
    eng.fit_transform(X, time_budget=300)
    dist = eng.anomaly_scores()
    energy = eng.energy_scores()
    t = time.perf_counter() - t0
    auc_d = roc_auc_score(y, dist)
    auc_e = roc_auc_score(y, energy)
    ens = (rankdata(dist) + rankdata(energy)) / 2
    auc_ens = roc_auc_score(y, ens)
    ap = average_precision_score(y, dist)
    return auc_d, auc_e, auc_ens, ap, t, dist, energy


log("=" * 70)
log("  FUNCTIONAL+RAW CONCATENATION TEST")
log("=" * 70)

for ds_name in ['mammography', 'pendigits']:
    X, y = load_dataset(ds_name)
    n, d = X.shape
    log(f"\n{'-'*60}")
    log(f"  {ds_name.upper()}  n={n}  d={d}")
    log(f"{'-'*60}")

    cfg = GRAVITY_CONFIGS[ds_name]

    # ── Baseline: Raw ──
    auc_d, auc_e, auc_ens, ap, t, dist_raw, energy_raw = run_gravity(X, y, cfg)
    log(f"  RAW (d={d}):         AUC(d)={auc_d:.4f}  AUC(e)={auc_e:.4f}  AUC(ens)={auc_ens:.4f}  AP={ap:.4f}  {t:.1f}s")
    raw_best = max(auc_d, auc_ens)

    # ── Test 1: Best functional only (variance ordering, poly=3, dct=5) ──
    fe = FunctionalExtractor(ordering='variance', poly_degree=3, n_dct=5,
                              include_stats=True, include_wavelets=True, standardize=True)
    Theta, names = fe.fit_transform(X)
    func_cfg = cfg.copy()
    func_cfg['k_neighbors'] = min(20, n // 10)
    func_cfg['iterations'] = 20
    auc_d, auc_e, auc_ens, ap, t, dist_func, energy_func = run_gravity(Theta, y, func_cfg)
    log(f"  FUNC variance (d={Theta.shape[1]}):  AUC(d)={auc_d:.4f}  AUC(e)={auc_e:.4f}  AUC(ens)={auc_ens:.4f}  AP={ap:.4f}  {t:.1f}s")

    # ── Test 2: Raw + Functional concatenation ──
    from sklearn.preprocessing import StandardScaler
    scaler_x = StandardScaler()
    scaler_t = StandardScaler()
    X_std = scaler_x.fit_transform(X)
    T_std = scaler_t.fit_transform(Theta)
    X_concat = np.hstack([X_std, T_std])
    concat_cfg = cfg.copy()
    concat_cfg['k_neighbors'] = min(20, n // 10)
    concat_cfg['iterations'] = 20
    auc_d, auc_e, auc_ens, ap, t, dist_concat, energy_concat = run_gravity(X_concat, y, concat_cfg)
    marker = " ***" if max(auc_d, auc_ens) > raw_best else ""
    log(f"  RAW+FUNC concat (d={X_concat.shape[1]}): AUC(d)={auc_d:.4f}  AUC(e)={auc_e:.4f}  AUC(ens)={auc_ens:.4f}  AP={ap:.4f}  {t:.1f}s{marker}")

    # ── Test 3: Score-level fusion (raw scores + functional scores) ──
    # Rank-average the raw engine scores with functional engine scores
    ens_cross = (rankdata(dist_raw) + rankdata(dist_func)) / 2
    auc_fusion = roc_auc_score(y, ens_cross)
    ap_fusion = average_precision_score(y, ens_cross)
    marker2 = " ***" if auc_fusion > raw_best else ""
    log(f"  SCORE FUSION (raw+func ranks):  AUC={auc_fusion:.4f}  AP={ap_fusion:.4f}{marker2}")

    # ── Test 4: Triple fusion (raw dist + func dist + raw energy) ──
    ens_triple = (rankdata(dist_raw) + rankdata(dist_func) + rankdata(energy_raw)) / 3
    auc_triple = roc_auc_score(y, ens_triple)
    ap_triple = average_precision_score(y, ens_triple)
    marker3 = " ***" if auc_triple > raw_best else ""
    log(f"  TRIPLE FUSION (raw_d+func_d+raw_e): AUC={auc_triple:.4f}  AP={ap_triple:.4f}{marker3}")

    # ── Test 5: Selective features (just polynomial + gradient — pure structural) ──
    fe_min = FunctionalExtractor(ordering='variance', poly_degree=3, n_dct=0,
                                  include_stats=False, include_wavelets=False, standardize=True)
    # DCT=0 won't work, use a minimal extraction
    fe_min2 = FunctionalExtractor(ordering='sorted', poly_degree=3, n_dct=3,
                                   include_stats=True, include_wavelets=False, standardize=True)
    Theta_min, names_min = fe_min2.fit_transform(X)
    min_cfg = cfg.copy()
    min_cfg['k_neighbors'] = min(15, n // 10)
    min_cfg['iterations'] = 20
    auc_d, auc_e, auc_ens, ap, t, _, _ = run_gravity(Theta_min, y, min_cfg)
    log(f"  MINIMAL func (d={Theta_min.shape[1]}):  AUC(d)={auc_d:.4f}  AUC(e)={auc_e:.4f}  AUC(ens)={auc_ens:.4f}  AP={ap:.4f}  {t:.1f}s")

log(f"\n{'='*70}")
log("DONE")
log("*** = beats raw GravityEngine baseline")
