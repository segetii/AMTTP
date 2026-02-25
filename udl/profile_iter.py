"""Instrumented single-run to find where 48s/iter is spent."""
import numpy as np
from scipy.io import loadmat
from sklearn.preprocessing import StandardScaler
from scipy.spatial import cKDTree
import time, sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from udl.gravity import (radial_pull, pairwise_forces, operator_deviation_pull,
                          compute_system_energy)

d = loadmat("c:/amttp/data/external_validation/odds/shuttle.mat")
X_raw = d["X"].astype(np.float64)
scaler = StandardScaler()
X_work = scaler.fit_transform(X_raw).astype(np.float64)
mu = np.mean(X_work, axis=0)

params = dict(alpha=0.011, gamma=6.06, sigma=2.57, lambda_rep=0.12,
              eta=0.013, k_neighbors=30, beta_dev=0.054)
n = X_work.shape[0]
print(f"Shuttle normalized: n={n}\n")

_tree = None
_tree_refresh = 3

for t in range(6):  # just 6 iterations
    t_iter = time.perf_counter()

    # 1. Radial pull
    t0 = time.perf_counter()
    F = radial_pull(X_work, mu, params["alpha"])
    tr = time.perf_counter() - t0

    # 2. Tree invalidation
    if _tree is not None and t % _tree_refresh == 0:
        _tree = None

    # 3. Pairwise forces
    t0 = time.perf_counter()
    F_pair, _tree = pairwise_forces(
        X_work, params["gamma"], params["sigma"], params["lambda_rep"],
        k_neighbors=params["k_neighbors"], tree=_tree
    )
    tp = time.perf_counter() - t0
    F += F_pair

    # 4. beta_dev
    t0 = time.perf_counter()
    dev = X_work ** 2 - mu ** 2
    F -= params["beta_dev"] * dev
    td = time.perf_counter() - t0

    # 5. Clamp
    t0 = time.perf_counter()
    force_norm = np.linalg.norm(F, axis=1, keepdims=True)
    mask = force_norm > 100.0
    if np.any(mask):
        F = np.where(mask, F * (100.0 / (force_norm + 1e-10)), F)
    tc = time.perf_counter() - t0

    # 6. Euler step
    t0 = time.perf_counter()
    dX = params["eta"] * F
    X_work += dX
    te = time.perf_counter() - t0

    max_disp = float(np.max(np.abs(dX)))
    total = time.perf_counter() - t_iter

    print(f"Iter {t}: total={total:.3f}s  radial={tr:.4f}  pair={tp:.3f}  "
          f"dev={td:.4f}  clamp={tc:.4f}  euler={te:.4f}  maxdisp={max_disp:.6f}")
