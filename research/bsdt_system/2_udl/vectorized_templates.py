import numba
import numpy as np

def vectorized_phase_curve(X, ref_mean, ref_std, pca_components=None, pca_mean=None):
    N, m = X.shape
    px = X[:, :-1]
    py = X[:, 1:]
    phase = np.hstack((px, py))
    full = (phase - ref_mean) / ref_std
    if pca_components is not None:
        centered = full - pca_mean
        return centered @ pca_components.T
    return full

@numba.njit(parallel=True)
def fast_mahalanobis(X, mu, cov_inv):
    diff = X - mu
    out = np.empty(X.shape[0], dtype=np.float64)
    for i in numba.prange(X.shape[0]):
        out[i] = np.sqrt(np.maximum(np.dot(np.dot(diff[i], cov_inv), diff[i]), 0.0))
    return out

# Add more vectorized/JIT operator templates as needed
