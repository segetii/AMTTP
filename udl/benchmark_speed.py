"""
Speed Benchmark — cKDTree + Tree Caching vs Previous Implementation
====================================================================
Runs GravityEngine on real datasets and reports timing breakdowns.
"""

import numpy as np
from scipy.io import loadmat
from sklearn.metrics import roc_auc_score
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from udl.gravity import GravityEngine


def load_dataset(name: str, data_root: str = "c:/amttp/data/external_validation/odds"):
    d = loadmat(os.path.join(data_root, f"{name}.mat"))
    X = d["X"].astype(np.float64)
    y = d["y"].ravel().astype(int)
    return X, y


def benchmark(name: str, params: dict, label: str = ""):
    X, y = load_dataset(name)
    n, d = X.shape
    print(f"\n{'─'*60}")
    print(f"  {name.upper()} — {label}")
    print(f"  n={n}, d={d}, anomaly_rate={y.mean():.4f}")
    print(f"{'─'*60}")

    engine = GravityEngine(
        alpha=params["alpha"], gamma=params["gamma"],
        sigma=params["sigma"], lambda_rep=params["lambda_rep"],
        eta=params["eta"], iterations=params["iterations"],
        normalize=True, track_energy=False, convergence_tol=1e-7,
        k_neighbors=params.get("k_neighbors", 0),
        beta_dev=params.get("beta_dev", 0.0),
        exp_alpha=params.get("exp_alpha", 0.0),
    )

    # --- Simulation ---
    t0 = time.perf_counter()
    X_final = engine.fit_transform(X, time_budget=600.0)
    t_sim = time.perf_counter() - t0
    stopped = engine.converged_at_ if engine.converged_at_ else params["iterations"]
    print(f"  Simulation: {t_sim:.2f}s  ({stopped} iters, {t_sim/stopped:.3f}s/iter)")

    if np.any(np.isnan(X_final)):
        print("  !! NaN in output — aborting")
        return

    # --- Distance scoring (instant) ---
    t0 = time.perf_counter()
    s_dist = engine.anomaly_scores()
    t_dist = time.perf_counter() - t0
    auc_dist = roc_auc_score(y, s_dist)
    print(f"  Distance scoring:  {t_dist:.3f}s  AUC={auc_dist:.4f}")

    # --- Energy scoring ---
    t0 = time.perf_counter()
    s_en = engine.energy_scores()
    t_en = time.perf_counter() - t0
    if np.any(np.isnan(s_en)) or np.any(np.isinf(s_en)):
        print(f"  Energy scoring:    {t_en:.3f}s  AUC=NaN/Inf")
    else:
        auc_en = roc_auc_score(y, s_en)
        print(f"  Energy scoring:    {t_en:.3f}s  AUC={auc_en:.4f}")

    total = t_sim + t_en
    print(f"  TOTAL time:        {total:.2f}s")
    return {"sim": t_sim, "energy": t_en, "total": total, "auc_dist": auc_dist}


if __name__ == "__main__":
    print("=" * 60)
    print("  GRAVITY ENGINE — SPEED BENCHMARK")
    print("  (cKDTree + tree caching + chunked vectorized)")
    print("=" * 60)

    CONFIGS = {
        "mammography": {
            "alpha": 0.00496, "gamma": 0.0396, "sigma": 0.265,
            "lambda_rep": 0.620, "eta": 0.0678, "iterations": 15,
            "k_neighbors": 27, "beta_dev": 0.088, "exp_alpha": 0.0,
        },
        "shuttle_knn": {
            "alpha": 0.011, "gamma": 6.06, "sigma": 2.57,
            "lambda_rep": 0.12, "eta": 0.013, "iterations": 52,
            "k_neighbors": 30, "beta_dev": 0.054, "exp_alpha": 0.0,
        },
        "pendigits": {
            "alpha": 0.00496, "gamma": 0.0396, "sigma": 0.265,
            "lambda_rep": 0.620, "eta": 0.0678, "iterations": 30,
            "k_neighbors": 27, "beta_dev": 0.088, "exp_alpha": 0.0,
        },
    }

    results = {}
    for name, cfg in CONFIGS.items():
        ds = name.replace("_knn", "")
        try:
            results[name] = benchmark(ds, cfg, label=name)
        except Exception as e:
            print(f"  !! {name} failed: {e}")

    # Previous timings for comparison
    print("\n\n" + "=" * 60)
    print("  COMPARISON WITH PREVIOUS TIMINGS")
    print("=" * 60)
    prev = {
        "mammography":  {"sim": 6.7,  "energy": 11.3, "total": 18.0},
        "shuttle_knn":  {"sim": 308.4, "energy": 44.3, "total": 352.7},
        "pendigits":    {"sim": 23.3, "energy": 10.8, "total": 34.1},
    }
    print(f"  {'Dataset':<18s} {'Old (s)':>8s} {'New (s)':>8s} {'Speedup':>8s} {'AUC chg':>8s}")
    print(f"  {'─'*52}")
    for name in CONFIGS:
        old = prev.get(name, {})
        new = results.get(name, {})
        if old and new:
            old_t = old["total"]
            new_t = new["total"]
            speedup = old_t / new_t if new_t > 0 else 0
            print(f"  {name:<18s} {old_t:>8.1f} {new_t:>8.1f} {speedup:>7.2f}x")
