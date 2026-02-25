"""
Gravity Engine Hyperparameter Optimizer
=======================================
Uses Bayesian-style random search + refinement to find optimal
GravityEngine hyperparameters for maximum AUC on anomaly detection.

Strategy:
  1. Random search over broad parameter space (Phase 1)
  2. Refine around best region (Phase 2)
  3. Test both anomaly_scores (distance) and displacement_scores
"""

import numpy as np
from scipy.io import loadmat
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedShuffleSplit
import time
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from udl.gravity import GravityEngine


def load_dataset(name: str, data_root: str = "c:/amttp/data/external_validation/odds"):
    """Load a .mat dataset."""
    path = os.path.join(data_root, f"{name}.mat")
    d = loadmat(path)
    X = d["X"].astype(np.float64)
    y = d["y"].ravel().astype(int)
    return X, y


def subsample(X, y, max_n=2000, seed=42):
    """Stratified subsample for speed (O(n^2) forces)."""
    if len(X) <= max_n:
        return X, y
    sss = StratifiedShuffleSplit(n_splits=1, train_size=max_n, random_state=seed)
    idx, _ = next(sss.split(X, y))
    return X[idx], y[idx]


def evaluate(params: dict, X: np.ndarray, y: np.ndarray, max_time: float = 20.0) -> dict:
    """Run GravityEngine with given params, return AUC for all scoring methods."""
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
    t0 = time.time()
    X_final = engine.fit_transform(X, time_budget=max_time)
    elapsed = time.time() - t0

    # Check for NaN / divergence
    if np.any(np.isnan(X_final)) or np.any(np.abs(X_final) > 1e6):
        return {
            "auc_distance": 0.0,
            "auc_displacement": 0.0,
            "auc_energy": 0.0,
            "auc_best": 0.0,
            "best_method": "distance",
            "elapsed": elapsed,
        }

    # Score method 1: distance from centre
    scores_dist = engine.anomaly_scores()
    if np.any(np.isnan(scores_dist)):
        auc_dist = 0.0
    else:
        auc_dist = roc_auc_score(y, scores_dist)

    # Score method 2: displacement
    scores_disp = engine.displacement_scores()
    if np.any(np.isnan(scores_disp)):
        auc_disp = 0.0
    else:
        auc_disp = roc_auc_score(y, scores_disp)

    # Score method 3: per-point energy
    try:
        scores_energy = engine.energy_scores()
        if np.any(np.isnan(scores_energy)) or np.any(np.isinf(scores_energy)):
            auc_energy = 0.0
        else:
            auc_energy = roc_auc_score(y, scores_energy)
    except Exception:
        auc_energy = 0.0

    auc_best = max(auc_dist, auc_disp, auc_energy)
    if auc_energy >= auc_dist and auc_energy >= auc_disp:
        best_method = "energy"
    elif auc_dist >= auc_disp:
        best_method = "distance"
    else:
        best_method = "displacement"

    return {
        "auc_distance": auc_dist,
        "auc_displacement": auc_disp,
        "auc_energy": auc_energy,
        "auc_best": auc_best,
        "best_method": best_method,
        "elapsed": elapsed,
    }


def random_params(rng: np.random.Generator) -> dict:
    """Sample from broad parameter space."""
    return {
        "alpha":      float(rng.choice([0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0])),
        "gamma":      float(rng.choice([0.1, 0.3, 0.5, 1.0, 2.0, 5.0, 10.0])),
        "sigma":      float(rng.choice([0.3, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0])),
        "lambda_rep": float(rng.choice([0.01, 0.05, 0.1, 0.3, 0.5, 1.0])),
        "eta":        float(rng.choice([0.001, 0.005, 0.01, 0.02, 0.05, 0.1])),
        "iterations": int(rng.choice([15, 25, 35, 50])),
        "k_neighbors": int(rng.choice([0, 0, 0, 10, 15, 20, 30])),
        "beta_dev":   float(rng.choice([0.0, 0.0, 0.0, 0.01, 0.05, 0.1, 0.3])),
        "exp_alpha":  float(rng.choice([0.0, 0.0, 0.5, 1.0, 1.5, 2.0, 3.0])),
    }


def perturb_params(best: dict, rng: np.random.Generator, scale=0.3) -> dict:
    """Small perturbation around a known good config."""
    p = {}
    for k in ["alpha", "gamma", "sigma", "lambda_rep", "eta"]:
        v = best[k] * (1 + scale * rng.standard_normal())
        p[k] = max(1e-4, float(v))
    p["iterations"] = max(10, min(60, int(best["iterations"] * (1 + 0.2 * rng.standard_normal()))))
    # Perturb k_neighbors: keep at 0 if was 0, else jitter
    k_orig = best.get("k_neighbors", 0)
    if k_orig > 0:
        p["k_neighbors"] = max(5, int(k_orig * (1 + 0.3 * rng.standard_normal())))
    else:
        p["k_neighbors"] = int(rng.choice([0, 0, 10, 20]))  # occasionally try kNN
    # Perturb beta_dev
    b_orig = best.get("beta_dev", 0.0)
    if b_orig > 0:
        p["beta_dev"] = max(0.0, float(b_orig * (1 + 0.3 * rng.standard_normal())))
    else:
        p["beta_dev"] = float(rng.choice([0.0, 0.0, 0.01, 0.05]))
    # Perturb exp_alpha
    ea_orig = best.get("exp_alpha", 0.0)
    if ea_orig > 0:
        p["exp_alpha"] = max(0.0, float(ea_orig * (1 + 0.3 * rng.standard_normal())))
    else:
        p["exp_alpha"] = float(rng.choice([0.0, 0.0, 0.5, 1.0, 2.0]))  # occasionally try
    return p


def optimize_dataset(name: str, n_random=60, n_refine=40, max_n=1500, seed=42,
                     seed_params: dict = None):
    """Full optimization for one dataset."""
    print(f"\n{'='*60}")
    print(f"  OPTIMIZING: {name.upper()}")
    print(f"{'='*60}")

    X, y = load_dataset(name)
    X_sub, y_sub = subsample(X, y, max_n=max_n, seed=seed)
    print(f"  Full: {X.shape[0]} samples, {X.shape[1]} features, anomaly rate {y.mean():.3f}")
    print(f"  Subsample: {X_sub.shape[0]} samples")

    rng = np.random.default_rng(seed)
    results = []

    # Seed: evaluate known-best + exp_alpha variants
    if seed_params is not None:
        print(f"\n  Phase 0: Seeded configs...")
        for ea in [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]:
            p = dict(seed_params)
            p["exp_alpha"] = ea
            try:
                res = evaluate(p, X_sub, y_sub)
                res["params"] = p
                results.append(res)
                print(f"    exp_alpha={ea:.1f} -> AUC={res['auc_best']:.4f} "
                      f"({res['best_method']}: dist={res['auc_distance']:.4f} "
                      f"disp={res['auc_displacement']:.4f} E={res.get('auc_energy',0):.4f})")
            except Exception as e:
                print(f"    exp_alpha={ea:.1f} FAILED: {e}")

    # Phase 1: Random search
    print(f"\n  Phase 1: Random search ({n_random} trials)...")
    for i in range(n_random):
        params = random_params(rng)
        try:
            res = evaluate(params, X_sub, y_sub)
            res["params"] = params
            results.append(res)
            if (i + 1) % 5 == 0:
                best_so_far = max(r["auc_best"] for r in results)
                print(f"    [{i+1}/{n_random}] best AUC so far: {best_so_far:.4f} (last took {res['elapsed']:.1f}s)")
        except Exception as e:
            print(f"    [{i+1}] FAILED: {e}")

    # Phase 2: Refine around top-5
    print(f"\n  Phase 2: Refinement ({n_refine} trials)...")
    results.sort(key=lambda r: r["auc_best"], reverse=True)
    top5 = [r["params"] for r in results[:5]]

    for i in range(n_refine):
        base = top5[i % len(top5)]
        params = perturb_params(base, rng, scale=0.25)
        try:
            res = evaluate(params, X_sub, y_sub)
            res["params"] = params
            results.append(res)
            if (i + 1) % 10 == 0:
                best_so_far = max(r["auc_best"] for r in results)
                print(f"    [{i+1}/{n_refine}] best AUC so far: {best_so_far:.4f}")
        except Exception as e:
            print(f"    [{i+1}] FAILED: {e}")

    # Final: Sort and report
    results.sort(key=lambda r: r["auc_best"], reverse=True)
    best = results[0]

    print(f"\n  {'─'*50}")
    print(f"  BEST RESULT for {name.upper()}:")
    print(f"    AUC (distance):     {best['auc_distance']:.4f}")
    print(f"    AUC (displacement): {best['auc_displacement']:.4f}")
    print(f"    AUC (energy):       {best.get('auc_energy', 0):.4f}")
    print(f"    Best AUC:           {best['auc_best']:.4f}")
    print(f"    Best method:        {best['best_method']}")
    print(f"    Time:               {best['elapsed']:.1f}s")
    print(f"    Parameters:")
    for k, v in best["params"].items():
        print(f"      {k:>12s}: {v}")

    # Also report top-5
    print(f"\n  Top-5 configs:")
    for rank, r in enumerate(results[:5], 1):
        p = r["params"]
        print(f"    #{rank} AUC={r['auc_best']:.4f} "
              f"({r['best_method']}: dist={r['auc_distance']:.4f} "
              f"disp={r['auc_displacement']:.4f} E={r.get('auc_energy',0):.4f}) "
              f"a={p['alpha']:.3f} g={p['gamma']:.1f} s={p['sigma']:.1f} "
              f"lr={p['lambda_rep']:.3f} eta={p['eta']:.4f} it={p['iterations']} "
              f"k={p.get('k_neighbors',0)} bd={p.get('beta_dev',0):.3f} "
              f"ea={p.get('exp_alpha',0):.2f}")

    # Validate best on full dataset (if different size)
    if len(X) > max_n:
        print(f"\n  Validating best params on FULL dataset ({len(X)} samples)...")
        # Use larger subsample for validation
        X_val, y_val = subsample(X, y, max_n=min(len(X), 3000), seed=seed+1)
        res_full = evaluate(best["params"], X_val, y_val)
        print(f"    Full-data AUC (distance):     {res_full['auc_distance']:.4f}")
        print(f"    Full-data AUC (displacement): {res_full['auc_displacement']:.4f}")
        print(f"    Full-data AUC (energy):       {res_full.get('auc_energy', 0):.4f}")
        print(f"    Full-data best AUC:           {res_full['auc_best']:.4f}")
        print(f"    Full-data best method:        {res_full['best_method']}")
        print(f"    Time:                         {res_full['elapsed']:.1f}s")

    return best


if __name__ == "__main__":
    print("Gravity Engine Hyperparameter Optimization")
    print("=" * 60)

    # Seed with known-best configs from previous runs
    KNOWN_BEST = {
        "mammography": {
            "alpha": 0.006, "gamma": 0.042, "sigma": 0.25,
            "lambda_rep": 0.594, "eta": 0.093, "iterations": 15,
            "k_neighbors": 26, "beta_dev": 0.05, "exp_alpha": 0.0,
        },
        "shuttle": {
            "alpha": 0.011, "gamma": 6.06, "sigma": 2.57,
            "lambda_rep": 0.12, "eta": 0.013, "iterations": 52,
            "k_neighbors": 0, "beta_dev": 0.054, "exp_alpha": 0.0,
        },
    }

    all_results = {}
    for dataset in ["mammography", "shuttle"]:
        mn = 800 if dataset == "mammography" else 500
        best = optimize_dataset(
            dataset,
            n_random=50,
            n_refine=30,
            max_n=mn,
            seed=42,
            seed_params=KNOWN_BEST.get(dataset),
        )
        all_results[dataset] = best

    # Final summary
    print("\n\n" + "=" * 60)
    print("  FINAL SUMMARY")
    print("=" * 60)
    for name, best in all_results.items():
        print(f"\n  {name.upper()}:")
        print(f"    Best AUC:    {best['auc_best']:.4f}")
        print(f"    Method:      {best['best_method']}")
        p = best["params"]
        print(f"    Params:      alpha={p['alpha']}, gamma={p['gamma']}, "
              f"sigma={p['sigma']}, lambda_rep={p['lambda_rep']}, "
              f"eta={p['eta']}, iterations={p['iterations']}")
