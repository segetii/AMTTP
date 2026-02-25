"""Profile: brute-force cdist+argpartition kNN vs cKDTree on clustered data."""
import numpy as np
from scipy.io import loadmat
from scipy.spatial.distance import cdist
from scipy.spatial import cKDTree
from sklearn.preprocessing import StandardScaler
import time

d = loadmat("c:/amttp/data/external_validation/odds/shuttle.mat")
X_raw = d["X"].astype(np.float64)
X = StandardScaler().fit_transform(X_raw)
n, dim = X.shape
k = 30
print(f"Shuttle normalized: n={n}, d={dim}, k={k}")

# --- Test 1: Brute-force chunked kNN ---
chunk_size = 2000
t0 = time.perf_counter()
all_idx = np.empty((n, k), dtype=int)
for start in range(0, n, chunk_size):
    end = min(start + chunk_size, n)
    D = cdist(X[start:end], X)
    for i in range(end - start):
        D[i, start + i] = np.inf
    all_idx[start:end] = np.argpartition(D, k, axis=1)[:, :k]
t1 = time.perf_counter()
print(f"Brute-force kNN (chunk={chunk_size}):  {t1-t0:.3f}s")

# --- Test 2: cKDTree (fresh) ---
t0 = time.perf_counter()
tree = cKDTree(X)
_, idx_tree = tree.query(X, k=k+1)
t1 = time.perf_counter()
print(f"cKDTree build+query (fresh):    {t1-t0:.3f}s")

# --- Test 3: Simulate clustered data (after gravity dynamics) ---
# Pull 80% of points toward center to simulate clustering
X_clustered = X.copy()
X_clustered *= 0.1  # compress all points toward origin
noise = np.random.randn(n, dim) * 0.01
X_clustered += noise

t0 = time.perf_counter()
all_idx2 = np.empty((n, k), dtype=int)
for start in range(0, n, chunk_size):
    end = min(start + chunk_size, n)
    D = cdist(X_clustered[start:end], X_clustered)
    for i in range(end - start):
        D[i, start + i] = np.inf
    all_idx2[start:end] = np.argpartition(D, k, axis=1)[:, :k]
t1 = time.perf_counter()
print(f"Brute-force kNN (clustered):    {t1-t0:.3f}s")

t0 = time.perf_counter()
tree2 = cKDTree(X_clustered)
_, idx_tree2 = tree2.query(X_clustered, k=k+1)
t1 = time.perf_counter()
print(f"cKDTree (clustered, fresh):     {t1-t0:.3f}s")

# --- Test 4: Different chunk sizes ---
for cs in [500, 1000, 2000, 5000]:
    t0 = time.perf_counter()
    for start in range(0, n, cs):
        end = min(start + cs, n)
        D = cdist(X[start:end], X)
        for i in range(end - start):
            D[i, start + i] = np.inf
        np.argpartition(D, k, axis=1)[:, :k]
    t1 = time.perf_counter()
    print(f"Brute-force chunk={cs:>5d}:       {t1-t0:.3f}s")
