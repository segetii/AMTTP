"""UDL multi-domain transform — connects the Universal Deviation Law
tensor framework to collapse_geometry.

UDLTransform converts each row x ∈ ℝ^d into a multi-domain representation
by applying four spectrum operators and then compressing via PCA:

  StatFeatures (5D)  : entropy, KL div, Hellinger, skewness, kurtosis
  ChaosFeatures (3D) : Lyapunov-like divergence, recurrence, approx-entropy
  SpecFeatures (4D)  : PSD deviation, dominant-freq shift, spectral entropy, centroid
  GeomFeatures (5D)  : Mahalanobis, cosine-disim, L2-dev + 2 PCA projections
  ────────────────────────────────────────────────────────────────────
  Total raw          : 17D → PCA → n_components (default 8)

These signals detect trajectory divergence and distributional shift weeks-to-
quarters before collapse:
  - StatFeatures: distribution drift (KL/Hellinger fire at Q2-2008 for FDIC)
  - ChaosFeatures: recurrence drops (Lyapunov proxy rises) weeks before Uri
  - SpecFeatures:  frequency-domain anomalies in temperature seasonality
  - GeomFeatures:  Mahalanobis pre-saturation

Usage
-----
    from collapse_geometry.udl_transform import UDLTransform
    T = UDLTransform(n_components=8)
    T.fit(X_normal)             # (T0, N, d)
    X_udl = T.transform(panel)  # (T, N, 8)
    M = MasterOperator.calibrate(X_udl, ...)
"""
from __future__ import annotations

import numpy as np
from typing import Optional


# ─────────────────────────── individual domain operators ────────────────────

class _StatFeatures:
    """Statistical/probabilistic spectrum (5 outputs per row)."""

    def __init__(self, eps: float = 1e-10):
        self.eps = eps
        self._ref_dist: Optional[np.ndarray] = None

    def fit(self, X_ref: np.ndarray) -> "_StatFeatures":
        eps = self.eps
        row_sums = np.abs(X_ref).sum(axis=1, keepdims=True) + eps
        P = np.abs(X_ref) / row_sums
        self._ref_dist = P.mean(axis=0)
        self._ref_dist /= self._ref_dist.sum() + eps
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        eps = self.eps
        N = X.shape[0]
        out = np.zeros((N, 5))
        row_sums = np.abs(X).sum(axis=1, keepdims=True) + eps
        P = np.abs(X) / row_sums
        P_s = np.clip(P, eps, 1.0)
        ref = self._ref_dist if self._ref_dist is not None else np.full(X.shape[1], 1.0 / X.shape[1])
        q   = np.clip(ref, eps, 1.0)
        # Shannon entropy
        out[:, 0] = -(P_s * np.log(P_s)).sum(axis=1)
        # KL divergence
        out[:, 1] = (P_s * np.log(P_s / q[None, :])).sum(axis=1)
        # Hellinger
        out[:, 2] = np.sqrt(0.5 * ((np.sqrt(P_s) - np.sqrt(q)[None, :]) ** 2).sum(axis=1))
        # Row skewness
        mu = P.mean(axis=1, keepdims=True)
        sigma = P.std(axis=1, keepdims=True) + eps
        z = (P - mu) / sigma
        out[:, 3] = (z ** 3).mean(axis=1)
        # Row kurtosis (excess)
        out[:, 4] = (z ** 4).mean(axis=1) - 3.0
        return out


class _ChaosFeatures:
    """Chaos / dynamical spectrum (3 outputs per row)."""

    def __init__(self, eps: float = 1e-10):
        self.eps = eps
        self._ref: Optional[np.ndarray] = None

    def fit(self, X_ref: np.ndarray) -> "_ChaosFeatures":
        self._ref = X_ref.mean(axis=0)
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        eps = self.eps
        N, d = X.shape
        out = np.zeros((N, 3))
        ref = self._ref if self._ref is not None else np.zeros(d)
        for i in range(N):
            xi = X[i]
            # 1. Lyapunov-like divergence: mean(log |Δ_k / ref_k|)
            diff = np.abs(xi - ref) + eps
            if d > 1:
                ratios = diff[1:] / (diff[:-1] + eps)
                ratios = np.clip(ratios, eps, 1e6)
                out[i, 0] = float(np.mean(np.log(ratios)))
            # 2. Recurrence rate (fraction of pairs within threshold)
            thresh = np.std(xi) * 0.1 + eps
            n_sub = min(d, 16)
            idx = np.linspace(0, d - 1, n_sub, dtype=int)
            sub = xi[idx]
            dm = np.abs(sub[:, None] - sub[None, :])
            out[i, 1] = float((dm < thresh).sum()) / max(n_sub ** 2, 1)
            # 3. Approximate entropy (simplified two-level template matching)
            out[i, 2] = self._approx_entropy(xi)
        return out

    def _approx_entropy(self, signal: np.ndarray, m: int = 2, r: float = 0.2) -> float:
        n = len(signal)
        cap = 24
        if n > cap:
            idx = np.linspace(0, n - 1, cap, dtype=int)
            signal = signal[idx]
            n = cap
        if n < m + 1:
            return 0.0
        r_val = r * (np.std(signal) + self.eps)

        def _phi(m_ord: int) -> float:
            templates = np.array([signal[j:j + m_ord] for j in range(n - m_ord + 1)])
            tot = len(templates)
            cnt = 0
            for k in range(tot):
                dists = np.abs(templates - templates[k]).max(axis=1)
                cnt += int((dists <= r_val).sum())
            return float(np.log(cnt / max(tot * tot, 1) + self.eps))

        return float(abs(_phi(m) - _phi(m + 1)))


class _SpecFeatures:
    """Spectral / frequency-domain spectrum (4 outputs per row)."""

    def __init__(self, eps: float = 1e-10):
        self.eps = eps
        self._ref_psd: Optional[np.ndarray] = None
        self._ref_centroid: float = 0.0

    def fit(self, X_ref: np.ndarray) -> "_SpecFeatures":
        eps = self.eps
        N, d = X_ref.shape
        n_freq = d // 2 + 1
        psds = np.zeros((N, n_freq))
        for i in range(N):
            fft_vals = np.fft.rfft(X_ref[i])
            psds[i] = np.abs(fft_vals) ** 2
        ref_psd = psds.mean(axis=0)
        ref_psd /= ref_psd.sum() + eps
        self._ref_psd = ref_psd
        freqs = np.arange(n_freq, dtype=float)
        self._ref_centroid = float((freqs * ref_psd).sum())
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        eps = self.eps
        N, d = X.shape
        n_freq = d // 2 + 1
        freqs = np.arange(n_freq, dtype=float)
        ref = self._ref_psd if self._ref_psd is not None else np.ones(n_freq) / n_freq
        psd_all = np.abs(np.fft.rfft(X, axis=1)) ** 2
        psd_sum = psd_all.sum(axis=1, keepdims=True) + eps
        psd_norm = psd_all / psd_sum
        out = np.zeros((N, 4))
        # 1. PSD L2 deviation
        out[:, 0] = np.sqrt(((psd_norm - ref[None, :]) ** 2).sum(axis=1))
        # 2. Dominant frequency shift
        dom_obs = np.argmax(psd_norm, axis=1).astype(float)
        dom_ref = float(np.argmax(ref))
        out[:, 1] = np.abs(dom_obs - dom_ref) / max(n_freq, 1)
        # 3. Spectral entropy
        ps = psd_norm + eps
        out[:, 2] = -(ps * np.log(ps)).sum(axis=1)
        # 4. Spectral centroid shift
        centroids = (freqs[None, :] * psd_norm).sum(axis=1)
        out[:, 3] = np.abs(centroids - self._ref_centroid)
        return out


class _GeomFeatures:
    """Geometric / manifold spectrum (5 outputs per row)."""

    def __init__(self, n_pca: int = 2, eps: float = 1e-10):
        self.n_pca = n_pca
        self.eps = eps
        self._mu: Optional[np.ndarray] = None
        self._Sigma_inv: Optional[np.ndarray] = None
        self._pca_dirs: Optional[np.ndarray] = None

    def fit(self, X_ref: np.ndarray) -> "_GeomFeatures":
        mu = X_ref.mean(axis=0)
        self._mu = mu
        Xc = X_ref - mu
        Sigma = (Xc.T @ Xc) / max(len(X_ref) - 1, 1)
        # regularise
        Sigma += np.eye(X_ref.shape[1]) * self.eps
        try:
            self._Sigma_inv = np.linalg.inv(Sigma)
        except np.linalg.LinAlgError:
            self._Sigma_inv = np.eye(X_ref.shape[1])
        # PCA directions (top n_pca eigenvectors)
        try:
            vals, vecs = np.linalg.eigh(Sigma)
            self._pca_dirs = vecs[:, -self.n_pca:]  # (d, n_pca)
        except np.linalg.LinAlgError:
            d = X_ref.shape[1]
            self._pca_dirs = np.eye(d)[:, :self.n_pca]
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        eps = self.eps
        mu = self._mu if self._mu is not None else np.zeros(X.shape[1])
        Xc = X - mu[None, :]
        out = np.zeros((len(X), 5))
        # 1. Mahalanobis distance
        if self._Sigma_inv is not None:
            mah2 = np.einsum("ni,ij,nj->n", Xc, self._Sigma_inv, Xc)
            out[:, 0] = np.sqrt(np.clip(mah2, 0, None))
        # 2. Cosine dissimilarity from reference mean
        nmu = float(np.linalg.norm(mu)) + eps
        nX  = np.linalg.norm(Xc, axis=1) + eps
        cos_sim = np.clip((Xc * mu[None, :]).sum(axis=1) / (nX * nmu), -1.0, 1.0)
        out[:, 1] = 1.0 - cos_sim
        # 3. L2 deviation from mean
        out[:, 2] = np.linalg.norm(Xc, axis=1)
        # 4-5. Projection onto top 2 PCA directions
        if self._pca_dirs is not None:
            proj = Xc @ self._pca_dirs                # (N, n_pca)
            out[:, 3] = proj[:, 0]
            if self.n_pca >= 2:
                out[:, 4] = proj[:, 1]
        return out


# ───────────────────────────────── UDLTransform ─────────────────────────────

class UDLTransform:
    """Multi-domain tensor transform for collapse_geometry.

    Applies four spectrum operators (stat 5D, chaos 3D, spec 4D, geom 5D)
    to flatten a panel (T, N, d) → (T*N, 17D), then PCA-compresses to
    n_components.  Input (T0, N, d) from CalibrationState can be passed
    through UDLTransform.fit/transform before MasterOperator.calibrate().

    Parameters
    ----------
    n_components : int
        Number of PCA components after multi-domain expansion (default 8).
    standardize : bool
        Z-score each input feature before applying operators (default True).
    eps : float
        Numerical stability floor across all operators.
    """

    def __init__(self, n_components: int = 8, standardize: bool = True,
                 eps: float = 1e-10):
        self.n_components = n_components
        self.standardize = standardize
        self.eps = eps
        self._input_mu: Optional[np.ndarray] = None
        self._input_sigma: Optional[np.ndarray] = None
        self._stat = _StatFeatures(eps=eps)
        self._chaos = _ChaosFeatures(eps=eps)
        self._spec = _SpecFeatures(eps=eps)
        self._geom = _GeomFeatures(n_pca=2, eps=eps)
        self._pca_mean: Optional[np.ndarray] = None
        self._pca_vecs: Optional[np.ndarray] = None   # (17, n_components)
        self._fitted: bool = False

    # ── internal helpers ─────────────────────────────────────────

    def _raw_dim(self) -> int:
        return 5 + 3 + 4 + 5  # = 17

    def _standardize(self, X_flat: np.ndarray) -> np.ndarray:
        if self.standardize and self._input_mu is not None:
            return (X_flat - self._input_mu) / self._input_sigma
        return X_flat

    def _multi_domain(self, X_flat: np.ndarray) -> np.ndarray:
        """Apply all four operators and concatenate → (N, 17)."""
        blocks = [
            self._stat.transform(X_flat),    # (N, 5)
            self._chaos.transform(X_flat),   # (N, 3)
            self._spec.transform(X_flat),    # (N, 4)
            self._geom.transform(X_flat),    # (N, 5)
        ]
        return np.hstack(blocks)             # (N, 17)

    # ── public API ───────────────────────────────────────────────

    def fit(self, X_normal: np.ndarray) -> "UDLTransform":
        """Calibrate all operators and PCA on the normal-period panel.

        Parameters
        ----------
        X_normal : (T0, N, d) normal-period panel (already z-scored or raw)
        """
        T0, N, d = X_normal.shape
        X_flat = X_normal.reshape(T0 * N, d)

        if self.standardize:
            self._input_mu    = X_flat.mean(axis=0)
            self._input_sigma = X_flat.std(axis=0) + self.eps
        X_std = self._standardize(X_flat)

        # Fit each operator
        self._stat.fit(X_std)
        self._chaos.fit(X_std)
        self._spec.fit(X_std)
        self._geom.fit(X_std)

        # Build multi-domain representation and fit PCA
        R = self._multi_domain(X_std)                # (T0*N, 17)
        R = np.nan_to_num(R, nan=0.0, posinf=0.0, neginf=0.0)

        self._pca_mean = R.mean(axis=0)
        Rc = R - self._pca_mean
        d_in = R.shape[1]
        k = min(self.n_components, d_in, Rc.shape[0] - 1)
        try:
            _, _, Vt = np.linalg.svd(Rc, full_matrices=False)
            self._pca_vecs = Vt[:k].T            # (d_in, k)
        except np.linalg.LinAlgError:
            self._pca_vecs = np.eye(d_in)[:, :k]

        self._fitted = True
        return self

    def transform(self, X_panel: np.ndarray) -> np.ndarray:
        """Transform a panel → multi-domain PCA representation.

        Parameters
        ----------
        X_panel : (T, N, d) — same feature layout as X_normal passed to fit()

        Returns
        -------
        (T, N, n_components)  — ready for CalibrationState.fit()
        """
        if not self._fitted:
            raise RuntimeError("Call fit() first")
        T, N, d = X_panel.shape
        X_flat = X_panel.reshape(T * N, d)
        X_std  = self._standardize(X_flat)
        R      = self._multi_domain(X_std)           # (T*N, 17)
        R      = np.nan_to_num(R, nan=0.0, posinf=0.0, neginf=0.0)
        Rc     = R - self._pca_mean
        X_out  = Rc @ self._pca_vecs                 # (T*N, n_components)
        return X_out.reshape(T, N, self.n_components)

    def fit_transform(self, X_normal: np.ndarray) -> np.ndarray:
        """Fit on X_normal and return its own transformed version."""
        self.fit(X_normal)
        return self.transform(X_normal)

    def __repr__(self) -> str:
        return (f"UDLTransform(n_components={self.n_components}, "
                f"fitted={self._fitted})")
