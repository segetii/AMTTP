"""
Full-Data Evaluation of Optimized Gravity Engine
=================================================
Runs the best hyperparameters on FULL datasets (no subsampling).
Reports AUC for all three scoring methods.
"""

import numpy as np
from scipy.io import loadmat
from sklearn.metrics import roc_auc_score, average_precision_score
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from udl.gravity import GravityEngine


def load_dataset(name: str, data_root: str = "c:/amttp/data/external_validation/odds"):
    path = os.path.join(data_root, f"{name}.mat")
    d = loadmat(path)
    X = d["X"].astype(np.float64)
    y = d["y"].ravel().astype(int)
    return X, y


def evaluate_full(name: str, params: dict, time_budget: float = 600.0):
    """Run GravityEngine on FULL dataset with given params."""
    X, y = load_dataset(name)
    n, d = X.shape
    anom_rate = y.mean()
    print(f"\n{'='*65}")
    print(f"  {name.upper()} — FULL DATA EVALUATION")
    print(f"{'='*65}")
    print(f"  Samples: {n}  |  Features: {d}  |  Anomaly rate: {anom_rate:.4f}")
    print(f"  Parameters:")
    for k, v in params.items():
        print(f"    {k:>14s}: {v}")

    engine = GravityEngine(
        alpha=params["alpha"],
        gamma=params["gamma"],
        sigma=params["sigma"],
        lambda_rep=params["lambda_rep"],
        eta=params["eta"],
        iterations=params["iterations"],
        normalize=True,
        track_energy=False,
        convergence_tol=1e-7,
        k_neighbors=params.get("k_neighbors", 0),
        beta_dev=params.get("beta_dev", 0.0),
        exp_alpha=params.get("exp_alpha", 0.0),
    )

    print(f"\n  Running gravity simulation on {n} points...")
    t0 = time.time()
    X_final = engine.fit_transform(X, time_budget=time_budget)
    elapsed = time.time() - t0
    print(f"  Simulation complete in {elapsed:.1f}s")

    if engine.converged_at_ is not None:
        print(f"  Converged/stopped at iteration {engine.converged_at_}")
    else:
        print(f"  Ran full {params['iterations']} iterations")

    # Check validity
    if np.any(np.isnan(X_final)):
        print("  !! WARNING: NaN in final positions !!")
        return

    # Score — distance
    scores_dist = engine.anomaly_scores()
    auc_dist = roc_auc_score(y, scores_dist)
    ap_dist = average_precision_score(y, scores_dist)

    # Score — displacement
    scores_disp = engine.displacement_scores()
    auc_disp = roc_auc_score(y, scores_disp)
    ap_disp = average_precision_score(y, scores_disp)

    # Score — energy
    print(f"  Computing per-point energy scores...")
    t1 = time.time()
    scores_energy = engine.energy_scores()
    t_energy = time.time() - t1
    if np.any(np.isnan(scores_energy)) or np.any(np.isinf(scores_energy)):
        auc_energy = 0.0
        ap_energy = 0.0
        print(f"  !! Energy scores contain NaN/Inf, skipping !!")
    else:
        auc_energy = roc_auc_score(y, scores_energy)
        ap_energy = average_precision_score(y, scores_energy)
    print(f"  Energy scoring took {t_energy:.1f}s")

    # Ensemble: rank-average of distance + energy
    from scipy.stats import rankdata
    ranks_dist = rankdata(scores_dist)
    ranks_disp = rankdata(scores_disp)
    ranks_energy = rankdata(scores_energy) if auc_energy > 0 else np.zeros_like(scores_dist)
    ensemble_2 = ranks_dist + ranks_energy
    ensemble_3 = ranks_dist + ranks_disp + ranks_energy
    auc_ens2 = roc_auc_score(y, ensemble_2) if auc_energy > 0 else 0.0
    auc_ens3 = roc_auc_score(y, ensemble_3) if auc_energy > 0 else 0.0
    ap_ens2 = average_precision_score(y, ensemble_2) if auc_energy > 0 else 0.0

    print(f"\n  {'─'*55}")
    print(f"  RESULTS on {name.upper()} (n={n}, FULL DATA)")
    print(f"  {'─'*55}")
    print(f"  {'Scoring Method':<25s} {'AUC':>8s}  {'AP':>8s}")
    print(f"  {'─'*43}")
    print(f"  {'Distance':<25s} {auc_dist:>8.4f}  {ap_dist:>8.4f}")
    print(f"  {'Displacement':<25s} {auc_disp:>8.4f}  {ap_disp:>8.4f}")
    print(f"  {'Energy':<25s} {auc_energy:>8.4f}  {ap_energy:>8.4f}")
    print(f"  {'Ensemble (dist+energy)':<25s} {auc_ens2:>8.4f}  {ap_ens2:>8.4f}")
    print(f"  {'Ensemble (all 3)':<25s} {auc_ens3:>8.4f}")
    print(f"  {'─'*43}")
    best_auc = max(auc_dist, auc_disp, auc_energy, auc_ens2, auc_ens3)
    print(f"  {'>>> BEST AUC':<25s} {best_auc:>8.4f}")
    print(f"  Total time: {elapsed + t_energy:.1f}s")

    return {
        "auc_distance": auc_dist, "auc_displacement": auc_disp,
        "auc_energy": auc_energy, "auc_ensemble2": auc_ens2,
        "auc_ensemble3": auc_ens3, "best_auc": best_auc,
        "ap_distance": ap_dist, "ap_displacement": ap_disp,
        "elapsed": elapsed,
    }


if __name__ == "__main__":
    print("=" * 65)
    print("  GRAVITY ENGINE — FULL DATA EVALUATION")
    print("=" * 65)

    # ── Best configs from optimization ──
    CONFIGS = {
        "mammography": {
            "alpha": 0.00496, "gamma": 0.0396, "sigma": 0.265,
            "lambda_rep": 0.620, "eta": 0.0678, "iterations": 15,
            "k_neighbors": 27, "beta_dev": 0.088, "exp_alpha": 0.0,
        },
        "shuttle": {
            "alpha": 0.011, "gamma": 6.06, "sigma": 2.57,
            "lambda_rep": 0.12, "eta": 0.013, "iterations": 52,
            "k_neighbors": 0, "beta_dev": 0.054, "exp_alpha": 0.0,
        },
        # Shuttle with kNN for faster full-data run
        "shuttle_knn": {
            "alpha": 0.011, "gamma": 6.06, "sigma": 2.57,
            "lambda_rep": 0.12, "eta": 0.013, "iterations": 52,
            "k_neighbors": 30, "beta_dev": 0.054, "exp_alpha": 0.0,
        },
    }

    all_results = {}

    # ── Mammography (11,183 pts, k=27 → kNN path, fast) ──
    all_results["mammography"] = evaluate_full("mammography", CONFIGS["mammography"])

    # ── Shuttle (49,097 pts) ──
    # k=0 (all-to-all) is O(n²)=2.4B pairs → too slow for 49K
    # Run with kNN variant instead
    print("\n\n  [Shuttle: using kNN=30 for tractable full-data run]")
    all_results["shuttle"] = evaluate_full("shuttle", CONFIGS["shuttle_knn"],
                                            time_budget=300.0)

    # ── Also try additional datasets if available ──
    for extra in ["pendigits", "smtp"]:
        fpath = f"c:/amttp/data/external_validation/odds/{extra}.mat"
        if os.path.exists(fpath):
            cfg = dict(CONFIGS["mammography"])
            cfg["iterations"] = 30
            try:
                all_results[extra] = evaluate_full(extra, cfg)
            except Exception as e:
                print(f"  !! {extra} failed: {e}")

    # ── Final table ──
    print("\n\n" + "=" * 65)
    print("  SUMMARY — ALL DATASETS, FULL DATA")
    print("=" * 65)
    print(f"  {'Dataset':<15s} {'n':>7s} {'AUC-dist':>9s} {'AUC-disp':>9s} "
          f"{'AUC-E':>7s} {'AUC-ens':>8s} {'BEST':>7s}")
    print(f"  {'─'*62}")
    for name, res in all_results.items():
        if res is None:
            continue
        dname = name.replace("_knn", "")
        try:
            X, y = load_dataset(dname)
        except Exception:
            continue
        print(f"  {dname:<15s} {len(X):>7d} {res['auc_distance']:>9.4f} "
              f"{res['auc_displacement']:>9.4f} {res['auc_energy']:>7.4f} "
              f"{res['auc_ensemble2']:>8.4f} {res['best_auc']:>7.4f}")
