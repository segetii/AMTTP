"""
Gravity Engine — Hyperparameter Optimiser
==========================================
Uses scipy.optimize.differential_evolution to find the best
alpha, gamma, sigma, lambda_rep, eta, iterations for each dataset.
"""
import numpy as np, warnings, sys, time
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')

from scipy.optimize import differential_evolution
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from udl.datasets import load_mammography, load_shuttle
from udl.gravity import GravityEngine

# ---- Load data ----
X_m, y_m = load_mammography()
X_s, y_s = load_shuttle()
_, X_m_te, _, y_m_te = train_test_split(X_m, y_m, test_size=0.3, stratify=y_m, random_state=42)
_, X_s_te, _, y_s_te = train_test_split(X_s, y_s, test_size=0.3, stratify=y_s, random_state=42)

# Fixed subsamples for reproducibility
np.random.seed(42)
idx_m = np.random.choice(len(X_m_te), 1000, replace=False)
idx_s = np.random.choice(len(X_s_te), 1000, replace=False)
X_m_sub, y_m_sub = X_m_te[idx_m], y_m_te[idx_m]
X_s_sub, y_s_sub = X_s_te[idx_s], y_s_te[idx_s]

call_count = [0]
best_so_far = [0.0]

def objective(params, X, y):
    alpha, gamma, sigma, lambda_rep, eta, iters = params
    iters = int(round(iters))
    call_count[0] += 1
    try:
        engine = GravityEngine(
            alpha=alpha, gamma=gamma, sigma=sigma,
            lambda_rep=lambda_rep, eta=eta,
            iterations=iters, track_energy=False,
            convergence_tol=0,
        )
        X_final = engine.fit_transform(X)
        s_dist = engine.anomaly_scores()
        s_disp = engine.displacement_scores()
        auc_dist = roc_auc_score(y, s_dist)
        auc_disp = roc_auc_score(y, s_disp)
        best = max(auc_dist, auc_disp)
        marker = ""
        if best > best_so_far[0]:
            best_so_far[0] = best
            marker = " ***NEW BEST***"
        if call_count[0] % 10 == 0 or marker:
            print(
                f"  [{call_count[0]:3d}] a={alpha:.3f} g={gamma:.3f} "
                f"s={sigma:.3f} lr={lambda_rep:.3f} e={eta:.4f} "
                f"T={iters:3d}  AUC={best:.4f}{marker}",
                flush=True,
            )
        return -best  # minimise negative AUC
    except Exception:
        return 0.0  # penalty

bounds = [
    (0.001, 2.0),    # alpha
    (0.01, 5.0),     # gamma
    (0.1, 10.0),     # sigma
    (0.001, 2.0),    # lambda_rep
    (0.001, 0.1),    # eta
    (10, 100),       # iterations
]

results = {}

for name, X_sub, y_sub in [("MAMMOGRAPHY", X_m_sub, y_m_sub),
                            ("SHUTTLE", X_s_sub, y_s_sub)]:
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  Optimising {name} (n={len(X_sub)}, d={X_sub.shape[1]})")
    print(sep)
    call_count[0] = 0
    best_so_far[0] = 0.0
    t0 = time.time()

    result = differential_evolution(
        objective, bounds, args=(X_sub, y_sub),
        maxiter=15, popsize=10, seed=42, tol=0.001,
        mutation=(0.5, 1.5), recombination=0.8,
        workers=1, polish=False,
    )
    elapsed = time.time() - t0
    alpha, gamma, sigma, lambda_rep, eta, iters = result.x
    iters = int(round(iters))

    print(f"\n  BEST AUC: {-result.fun:.4f}  ({call_count[0]} evals, {elapsed:.0f}s)")
    print(f"  alpha      = {alpha:.4f}")
    print(f"  gamma      = {gamma:.4f}")
    print(f"  sigma      = {sigma:.4f}")
    print(f"  lambda_rep = {lambda_rep:.4f}")
    print(f"  eta        = {eta:.5f}")
    print(f"  iterations = {iters}")

    # Re-run best to get details
    engine = GravityEngine(
        alpha=alpha, gamma=gamma, sigma=sigma,
        lambda_rep=lambda_rep, eta=eta,
        iterations=iters, track_energy=True,
    )
    X_f = engine.fit_transform(X_sub)
    s1 = engine.anomaly_scores()
    s2 = engine.displacement_scores()
    auc1 = roc_auc_score(y_sub, s1)
    auc2 = roc_auc_score(y_sub, s2)
    print(f"  Distance AUC:      {auc1:.4f}")
    print(f"  Displacement AUC:  {auc2:.4f}")
    engine.print_summary()

    results[name] = {
        "alpha": alpha, "gamma": gamma, "sigma": sigma,
        "lambda_rep": lambda_rep, "eta": eta, "iterations": iters,
        "auc_dist": auc1, "auc_disp": auc2,
    }

# ---- Summary ----
print("\n" + "=" * 60)
print("  OPTIMISATION SUMMARY")
print("=" * 60)
for name, r in results.items():
    best_auc = max(r["auc_dist"], r["auc_disp"])
    score_type = "distance" if r["auc_dist"] >= r["auc_disp"] else "displacement"
    print(f"\n  {name}:")
    print(f"    Best AUC = {best_auc:.4f} ({score_type})")
    print(f"    alpha={r['alpha']:.4f}  gamma={r['gamma']:.4f}  sigma={r['sigma']:.4f}")
    print(f"    lambda_rep={r['lambda_rep']:.4f}  eta={r['eta']:.5f}  T={r['iterations']}")

print("\nDONE")
