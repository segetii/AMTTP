"""Quick profile: time each operation in one kNN force iteration on shuttle."""
import numpy as np
from scipy.io import loadmat
from scipy.spatial import cKDTree
from sklearn.neighbors import NearestNeighbors
import time

d = loadmat("c:/amttp/data/external_validation/odds/shuttle.mat")
X = d["X"].astype(np.float64)
n = X.shape[0]
k = 30
print(f"Shuttle: n={n}, d={X.shape[1]}, k={k}")

# --- Build tree: cKDTree vs sklearn ---
t0 = time.perf_counter(); tree = cKDTree(X); t1 = time.perf_counter()
print(f"cKDTree build:   {t1-t0:.4f}s")

t0 = time.perf_counter(); nn = NearestNeighbors(n_neighbors=k+1, algorithm='auto'); nn.fit(X); t1 = time.perf_counter()
print(f"sklearn NN fit:  {t1-t0:.4f}s")

# --- Query: cKDTree vs sklearn ---
t0 = time.perf_counter(); dist_c, idx_c = tree.query(X, k=k+1); t1 = time.perf_counter()
print(f"cKDTree query:   {t1-t0:.4f}s")

t0 = time.perf_counter(); dist_s, idx_s = nn.kneighbors(X); t1 = time.perf_counter()
print(f"sklearn query:   {t1-t0:.4f}s")

# --- Vectorized force computation ---
nbr_idx = idx_c[:, 1:]  # skip self
gamma, sigma, lam, eps = 6.06, 2.57, 0.12, 1e-5

t0 = time.perf_counter()
X_nbrs = X[nbr_idx]                              # (n, k, d)
diff = X[:, None, :] - X_nbrs                    # (n, k, d)
dist = np.linalg.norm(diff, axis=2, keepdims=True) + eps
attraction = np.exp(-(dist**2) / (sigma**2))
repulsion = lam / dist
magnitude = -gamma * (attraction - repulsion)
unit = diff / dist
forces = np.sum(magnitude * unit, axis=1)
t1 = time.perf_counter()
print(f"Vectorized force: {t1-t0:.4f}s")
print(f"Force array: shape={forces.shape}, mem={forces.nbytes/1e6:.1f}MB")

# --- Test stale tree query (simulate cached tree on shifted data) ---
X_shifted = X + np.random.randn(*X.shape) * 0.01
t0 = time.perf_counter(); dist_stale, idx_stale = tree.query(X_shifted, k=k+1); t1 = time.perf_counter()
print(f"Stale tree query: {t1-t0:.4f}s")

print(f"\nExpected iter time: build+query+force ≈ {0:.0f}s (using cache)")
