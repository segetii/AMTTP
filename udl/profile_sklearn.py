"""Profile: sklearn brute-force (BLAS) vs cKDTree on fresh & clustered."""
import numpy as np
from scipy.io import loadmat
from scipy.spatial import cKDTree
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
import time

d = loadmat("c:/amttp/data/external_validation/odds/shuttle.mat")
X = StandardScaler().fit_transform(d["X"].astype(np.float64))
n, dim = X.shape
k = 30
print(f"n={n}, d={dim}, k={k}\n")

# --- Fresh data ---
print("=== FRESH (normalized, no clustering) ===")

t0 = time.perf_counter()
tree = cKDTree(X); tree.query(X, k=k+1)
print(f"cKDTree:         {time.perf_counter()-t0:.3f}s")

t0 = time.perf_counter()
nn = NearestNeighbors(n_neighbors=k+1, algorithm='auto').fit(X)
nn.kneighbors(X)
print(f"sklearn auto:    {time.perf_counter()-t0:.3f}s")

t0 = time.perf_counter()
nn = NearestNeighbors(n_neighbors=k+1, algorithm='brute').fit(X)
nn.kneighbors(X)
print(f"sklearn brute:   {time.perf_counter()-t0:.3f}s")

t0 = time.perf_counter()
nn = NearestNeighbors(n_neighbors=k+1, algorithm='ball_tree').fit(X)
nn.kneighbors(X)
print(f"sklearn ball:    {time.perf_counter()-t0:.3f}s")

t0 = time.perf_counter()
nn = NearestNeighbors(n_neighbors=k+1, algorithm='kd_tree').fit(X)
nn.kneighbors(X)
print(f"sklearn kd_tree: {time.perf_counter()-t0:.3f}s")

# --- Clustered data (simulating late-stage dynamics) ---
print("\n=== CLUSTERED (10× compression + noise) ===")
X_c = X * 0.1 + np.random.randn(n, dim) * 0.01

t0 = time.perf_counter()
tree = cKDTree(X_c); tree.query(X_c, k=k+1)
print(f"cKDTree:         {time.perf_counter()-t0:.3f}s")

t0 = time.perf_counter()
nn = NearestNeighbors(n_neighbors=k+1, algorithm='auto').fit(X_c)
nn.kneighbors(X_c)
print(f"sklearn auto:    {time.perf_counter()-t0:.3f}s")

t0 = time.perf_counter()
nn = NearestNeighbors(n_neighbors=k+1, algorithm='brute').fit(X_c)
nn.kneighbors(X_c)
print(f"sklearn brute:   {time.perf_counter()-t0:.3f}s")

t0 = time.perf_counter()
nn = NearestNeighbors(n_neighbors=k+1, algorithm='ball_tree').fit(X_c)
nn.kneighbors(X_c)
print(f"sklearn ball:    {time.perf_counter()-t0:.3f}s")
