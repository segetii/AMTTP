"""
Test: Coefficient Coordinate System — compact structural axes.
================================================================
Compare:
  A) Raw GravityEngine (baseline)
  B) Single-view coordinates (sorted / variance / magnitude)
  C) Multi-view coordinates (sorted+variance, sorted+variance+magnitude)
  D) Score fusion: raw scores + coordinate scores
  E) Various compactness levels (poly_degree=1,2,3; spectral=0,2,3)
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
from udl.coordinates import CoefficientCoordinates

OUT = 'c:/amttp/coordinates_results.txt'

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


def run_gravity(X, y, params, iters_override=None):
    cfg = params.copy()
    if iters_override:
        cfg['iterations'] = iters_override
    cfg['k_neighbors'] = min(cfg['k_neighbors'], X.shape[0] // 10)
    eng = GravityEngine(
        alpha=cfg['alpha'], gamma=cfg['gamma'],
        sigma=cfg['sigma'], lambda_rep=cfg['lambda_rep'],
        eta=cfg['eta'], iterations=cfg['iterations'],
        normalize=True, track_energy=False, convergence_tol=1e-7,
        k_neighbors=cfg['k_neighbors'], beta_dev=cfg['beta_dev'],
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


log("=" * 75)
log("  COEFFICIENT COORDINATE SYSTEM — BENCHMARK")
log("=" * 75)
log("  Each row x -> theta = (level, gradient, curvature, residual, freq...)")
log("  Axes have structural meaning. Anomaly = deviation in structure.")
log("")

for ds_name in ['mammography', 'pendigits']:
    X, y = load_dataset(ds_name)
    n, d = X.shape
    cfg = GRAVITY_CONFIGS[ds_name]

    log(f"\n{'='*65}")
    log(f"  {ds_name.upper()}  n={n}  d={d}  anomaly_rate={y.mean():.4f}")
    log(f"{'='*65}")

    # ── A) Baseline: Raw features ──
    auc_d, auc_e, auc_ens, ap, t, dist_raw, energy_raw = run_gravity(X, y, cfg)
    raw_best = max(auc_d, auc_ens)
    log(f"\n  [A] RAW features (d={d})")
    log(f"      AUC_d={auc_d:.4f}  AUC_e={auc_e:.4f}  AUC_ens={auc_ens:.4f}  AP={ap:.4f}  {t:.1f}s")
    log(f"      --> Best AUC = {raw_best:.4f}")

    # ── B) Single-view coordinates ──
    log(f"\n  [B] Single-view coordinates:")
    best_single_view = None
    best_single_auc = 0
    best_single_dist = None

    for view in ['sorted', 'variance', 'magnitude']:
        for poly_deg, n_spec in [(2, 2), (3, 2), (2, 0), (1, 3)]:
            cc = CoefficientCoordinates(
                views=[view], poly_degree=poly_deg, n_spectral=n_spec,
                include_residual=True, include_gradient_stats=True,
            )
            Theta, names = cc.fit_transform(X)
            k = Theta.shape[1]
            try:
                auc_d, auc_e, auc_ens, ap, t, dist_c, energy_c = run_gravity(
                    Theta, y, cfg, iters_override=20)
                best = max(auc_d, auc_ens)
                marker = " ***" if best > raw_best else ""
                log(f"      {view:>9s} p={poly_deg} s={n_spec} -> d={k:>2d}  "
                    f"AUC_d={auc_d:.4f} AUC_e={auc_e:.4f} AUC_ens={auc_ens:.4f} {t:.0f}s{marker}")
                if best > best_single_auc:
                    best_single_auc = best
                    best_single_view = (view, poly_deg, n_spec)
                    best_single_dist = dist_c
            except Exception as e:
                log(f"      {view:>9s} p={poly_deg} s={n_spec} -> d={k:>2d}  FAILED: {e}")

    # ── C) Multi-view coordinates ──
    log(f"\n  [C] Multi-view coordinates:")
    multi_configs = [
        (['sorted', 'variance'], 2, 2),
        (['sorted', 'variance', 'magnitude'], 2, 2),
        (['sorted', 'variance'], 2, 0),
        (['sorted', 'variance'], 3, 2),
        (['sorted', 'variance', 'magnitude'], 1, 2),
    ]
    best_multi_dist = None
    best_multi_auc = 0

    for views, poly_deg, n_spec in multi_configs:
        cc = CoefficientCoordinates(
            views=views, poly_degree=poly_deg, n_spectral=n_spec,
            include_residual=True, include_gradient_stats=True,
        )
        Theta, names = cc.fit_transform(X)
        k = Theta.shape[1]
        view_str = '+'.join(v[:3] for v in views)
        try:
            auc_d, auc_e, auc_ens, ap, t, dist_c, energy_c = run_gravity(
                Theta, y, cfg, iters_override=20)
            best = max(auc_d, auc_ens)
            marker = " ***" if best > raw_best else ""
            log(f"      {view_str:>11s} p={poly_deg} s={n_spec} -> d={k:>2d}  "
                f"AUC_d={auc_d:.4f} AUC_e={auc_e:.4f} AUC_ens={auc_ens:.4f} {t:.0f}s{marker}")
            if best > best_multi_auc:
                best_multi_auc = best
                best_multi_dist = dist_c
        except Exception as e:
            log(f"      {view_str:>11s} p={poly_deg} s={n_spec} -> d={k:>2d}  FAILED: {e}")

    # ── D) Score-level fusion ──
    log(f"\n  [D] Score-level fusion (rank-average):")
    fusions = []

    if best_single_dist is not None:
        ens = (rankdata(dist_raw) + rankdata(best_single_dist)) / 2
        auc_f = roc_auc_score(y, ens)
        ap_f = average_precision_score(y, ens)
        marker = " ***" if auc_f > raw_best else ""
        log(f"      raw + best_single_coord:  AUC={auc_f:.4f}  AP={ap_f:.4f}{marker}")
        fusions.append(('raw+single', auc_f))

    if best_multi_dist is not None:
        ens = (rankdata(dist_raw) + rankdata(best_multi_dist)) / 2
        auc_f = roc_auc_score(y, ens)
        ap_f = average_precision_score(y, ens)
        marker = " ***" if auc_f > raw_best else ""
        log(f"      raw + best_multi_coord:   AUC={auc_f:.4f}  AP={ap_f:.4f}{marker}")
        fusions.append(('raw+multi', auc_f))

    if best_single_dist is not None:
        ens = (rankdata(dist_raw) + rankdata(best_single_dist) + rankdata(energy_raw)) / 3
        auc_f = roc_auc_score(y, ens)
        ap_f = average_precision_score(y, ens)
        marker = " ***" if auc_f > raw_best else ""
        log(f"      raw_d + single + raw_e:   AUC={auc_f:.4f}  AP={ap_f:.4f}{marker}")
        fusions.append(('triple', auc_f))

    # ── E) Show coordinate names for best config ──
    cc_show = CoefficientCoordinates(views=['sorted', 'variance'], poly_degree=2, n_spectral=2)
    _, show_names = cc_show.fit_transform(X[:3])
    log(f"\n  Coordinate axes (sorted+variance, poly=2, spec=2):")
    log(f"      {show_names}")
    log(f"      Total: {len(show_names)} axes  (from {d} raw features)")

    # ── Summary ──
    log(f"\n  SUMMARY:")
    log(f"      Raw baseline:         AUC = {raw_best:.4f}")
    if best_single_dist is not None:
        log(f"      Best single-view:     AUC = {best_single_auc:.4f}  ({best_single_view})")
    log(f"      Best multi-view:      AUC = {best_multi_auc:.4f}")
    if fusions:
        best_fusion = max(fusions, key=lambda x: x[1])
        log(f"      Best fusion:          AUC = {best_fusion[1]:.4f}  ({best_fusion[0]})")


log(f"\n{'='*75}")
log("DONE")
log("*** = beats raw GravityEngine baseline")
