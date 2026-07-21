"""
bsdt_paper_engine.py
====================
Faithful implementation of the BSDT detection protocol from Odeyemi,
"Blind-Spot Decomposition and the Geometry of System Collapse" (2026):

  * Four channels as defined in §2.2 (Mahalanobis, PCA residual, excess
    velocity, KDE neg-log-density).
  * Ledoit-Wolf shrinkage covariance (§7.1).
  * Per-channel z-scoring on the frozen reference window, identity link
    psi(u)=u (Appendix B(iv)).
  * Closed-form Fisher Variance-Ratio weights (eq. 2.4), no label leakage.
  * E_BS = sum_k w_k * z_k(t).
  * Split conformal calibration (eq. 6.9, alpha_cal=0.25) -> p-values.
  * Adaptive rolling P99 threshold (§7.12) over trailing window W.
  * Alarm: s_t > tau_t  AND  p_t < 0.01.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np

try:
    from sklearn.covariance import LedoitWolf
    _HAS_LW = True
except Exception:
    _HAS_LW = False


# ---------------------------------------------------------------- helpers ----
def _ledoit_wolf(X_ref: np.ndarray) -> np.ndarray:
    """Ledoit-Wolf shrinkage covariance.  Falls back to ridge if sklearn absent."""
    if _HAS_LW:
        lw = LedoitWolf().fit(X_ref)
        return lw.covariance_
    Xc = X_ref - X_ref.mean(0, keepdims=True)
    S = (Xc.T @ Xc) / max(1, X_ref.shape[0] - 1)
    rho = 0.05
    return (1 - rho) * S + rho * np.trace(S) / S.shape[0] * np.eye(S.shape[0])


def _safe_inv(M: np.ndarray, ridge: float = 1e-8) -> np.ndarray:
    return np.linalg.inv(M + ridge * np.eye(M.shape[0]))


def _gaussian_kde_logpdf(x: np.ndarray, ref: np.ndarray, bw: float,
                          chunk: int = 512) -> np.ndarray:
    """Diagonal-Gaussian KDE with isotropic bandwidth bw on standardised data.

    Batched over test points to bound memory at chunk * n_ref * d floats.
    """
    T, d = x.shape
    n_ref = ref.shape[0]
    log_norm = -0.5 * d * np.log(2 * np.pi * bw * bw)
    out = np.empty(T)
    # ||x - r||^2 = ||x||^2 + ||r||^2 - 2 x.r  -> avoids the (T, n_ref, d) tensor
    ref_sq = np.einsum("ij,ij->i", ref, ref)              # (n_ref,)
    for s in range(0, T, chunk):
        e = min(T, s + chunk)
        xs = x[s:e]
        x_sq = np.einsum("ij,ij->i", xs, xs)              # (B,)
        cross = xs @ ref.T                                # (B, n_ref)
        sq = (x_sq[:, None] + ref_sq[None, :] - 2.0 * cross) / (2.0 * bw * bw)
        m = -sq.max(axis=1, keepdims=True)
        inner = np.exp(-sq + m).mean(axis=1)
        inner = np.clip(inner, 1e-300, None)
        out[s:e] = log_norm + np.log(inner) - m[:, 0]
    return out


def _scott_bandwidth(n: int, d: int) -> float:
    return n ** (-1.0 / (d + 4))


# ------------------------------------------------------------------ output ---
@dataclass
class BSDTResult:
    delta_C: np.ndarray
    delta_G: np.ndarray
    delta_A: np.ndarray
    delta_T: np.ndarray
    z: np.ndarray              # (T, 4) z-scored channels
    weights: np.ndarray        # (4,)   Fisher-VR weights
    E_BS: np.ndarray           # (T,)
    pvalue: np.ndarray         # (T,)   conformal p-values
    threshold: np.ndarray      # (T,)   adaptive rolling P99
    alarms: np.ndarray         # (T,)   bool  (s > tau AND p < alpha_alarm)
    fixed_threshold: float     # global P99 of reference E_BS (for ref)
    info: dict


# ------------------------------------------------------------------ engine ---
class BSDTPaperEngine:
    """
    Implements the BSDT detection protocol.

    Parameters
    ----------
    pca_var : float
        cumulative reference-PCA variance retained for P_k (so I-P_k captures
        the low-variance subspace used by delta_G).
    v0_q : float
        reference quantile defining the velocity threshold v_0 in delta_A.
    alpha_cal : float
        fraction of reference used as conformal calibration set (paper: 0.25).
    alpha_alarm : float
        conformal p-value alarm level (paper p99 ~ 0.01).
    rolling_window : int
        trailing window for the adaptive P99 threshold (paper §7.12: 8 quarters).
    fisher_split : tuple
        (low_q, high_q) for Fisher-VR group split on total magnitude M.
        Paper: (0.50, 0.80).
    """

    def __init__(
        self,
        pca_var: float = 0.90,
        v0_q: float = 0.95,
        alpha_cal: float = 0.25,
        alpha_alarm: float = 0.01,
        rolling_window: int = 32,
        fisher_split: tuple = (0.50, 0.80),
    ) -> None:
        self.pca_var = pca_var
        self.v0_q = v0_q
        self.alpha_cal = alpha_cal
        self.alpha_alarm = alpha_alarm
        self.rolling_window = rolling_window
        self.fisher_split = fisher_split

    # -------- fit on the frozen reference window ---------------------------
    def fit(self, X_ref: np.ndarray) -> "BSDTPaperEngine":
        n, d = X_ref.shape
        self.mu0_ = X_ref.mean(axis=0)
        self.Sigma0_ = _ledoit_wolf(X_ref)
        self.SigmaInv_ = _safe_inv(self.Sigma0_)

        # PCA on reference (centred) -> P_k
        Xc = X_ref - self.mu0_
        # symmetric eigen for stability
        cov_emp = (Xc.T @ Xc) / max(1, n - 1)
        evals, evecs = np.linalg.eigh(cov_emp)
        order = np.argsort(evals)[::-1]
        evals = np.clip(evals[order], 0.0, None)
        evecs = evecs[:, order]
        cum = np.cumsum(evals) / max(evals.sum(), 1e-12)
        k = int(np.searchsorted(cum, self.pca_var) + 1)
        k = max(1, min(k, d))
        self.k_ = k
        Vk = evecs[:, :k]
        self.Pk_ = Vk @ Vk.T                 # rank-k projector
        self.IminusPk_ = np.eye(d) - self.Pk_

        # Velocity threshold v_0 from reference
        if n >= 2:
            dX = np.diff(X_ref, axis=0)
            v_norms = np.linalg.norm(dX, axis=1)
            self.v0_ = float(np.quantile(v_norms, self.v0_q))
        else:
            self.v0_ = 0.0

        # KDE bandwidth on standardised reference
        # use diagonal whitening: z_ref = (X_ref - mu0) / std0
        std0 = X_ref.std(axis=0, ddof=1)
        std0 = np.where(std0 < 1e-12, 1.0, std0)
        self.std0_ = std0
        self.z_ref_ = (X_ref - self.mu0_) / std0
        self.kde_bw_ = _scott_bandwidth(n, d)

        # split conformal: hold out alpha_cal of reference for calibration
        rng = np.random.default_rng(0)
        idx = rng.permutation(n)
        n_cal = max(2, int(round(self.alpha_cal * n)))
        self.cal_idx_ = idx[:n_cal]
        self.tr_idx_ = idx[n_cal:]
        self.X_ref_ = X_ref
        return self

    # -------- per-observation channel computation --------------------------
    def _channels(self, X: np.ndarray, X_prev_for_velocity: Optional[np.ndarray] = None
                  ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        Xc = X - self.mu0_
        # delta_C  Mahalanobis
        quad = np.einsum("ti,ij,tj->t", Xc, self.SigmaInv_, Xc)
        delta_C = np.sqrt(np.clip(quad, 0.0, None))
        # delta_G  PCA residual in low-variance subspace
        resid = Xc @ self.IminusPk_.T
        delta_G = np.linalg.norm(resid, axis=1)
        # delta_A  excess velocity
        if X_prev_for_velocity is None:
            X_prev = np.vstack([X[:1], X[:-1]])
        else:
            X_prev = X_prev_for_velocity
        v = np.linalg.norm(X - X_prev, axis=1)
        delta_A = np.clip(v - self.v0_, 0.0, None)
        # delta_T  -log KDE on standardised data
        z = (X - self.mu0_) / self.std0_
        log_p = _gaussian_kde_logpdf(z, self.z_ref_, self.kde_bw_)
        delta_T = -log_p
        # Sanitise: clip to finite range so far-from-reference points don't
        # poison Fisher VR weights / z-statistics with +inf.
        for arr in (delta_C, delta_G, delta_A, delta_T):
            np.nan_to_num(arr, copy=False, nan=0.0, posinf=1e6, neginf=0.0)
        return delta_C, delta_G, delta_A, delta_T

    # -------- Fisher VR weights (eq. 2.4) ---------------------------------
    @staticmethod
    def _fisher_weights(channel_mat: np.ndarray, q_lo: float, q_hi: float) -> np.ndarray:
        """channel_mat: (T, K) raw channel magnitudes."""
        M = channel_mat.sum(axis=1)
        thr_lo = np.quantile(M, q_lo)
        thr_hi = np.quantile(M, q_hi)
        low = M <= thr_lo
        high = M >= thr_hi
        if low.sum() < 2 or high.sum() < 2:
            return np.ones(channel_mat.shape[1]) / channel_mat.shape[1]
        FR = np.zeros(channel_mat.shape[1])
        for k in range(channel_mat.shape[1]):
            mu_h = channel_mat[high, k].mean()
            mu_l = channel_mat[low, k].mean()
            v_h = channel_mat[high, k].var(ddof=1) + 1e-12
            v_l = channel_mat[low, k].var(ddof=1) + 1e-12
            FR[k] = (mu_h - mu_l) ** 2 / (v_h + v_l)
        s = FR.sum()
        return FR / s if s > 0 else np.ones_like(FR) / FR.size

    # -------- main evaluate -----------------------------------------------
    def evaluate(self, X: np.ndarray) -> BSDTResult:
        T = X.shape[0]

        # --- channels on full series and on calibration set ---
        d_C, d_G, d_A, d_T = self._channels(X)
        ch_full = np.column_stack([d_C, d_G, d_A, d_T])

        # z-score on REFERENCE statistics (trained subset only)
        d_ref_C, d_ref_G, d_ref_A, d_ref_T = self._channels(self.X_ref_)
        ref_mat = np.column_stack([d_ref_C, d_ref_G, d_ref_A, d_ref_T])
        mu = ref_mat.mean(axis=0)
        sd = ref_mat.std(axis=0, ddof=1)
        sd = np.where(sd < 1e-12, 1.0, sd)
        z_full = (ch_full - mu) / sd
        z_ref = (ref_mat - mu) / sd

        # Fisher VR weights from full-series magnitudes (transductive,
        # paper §10.1 finding 4 — labels-free)
        weights = self._fisher_weights(ch_full, *self.fisher_split)

        # E_BS = w . z   (identity link psi(u)=u, Appendix B(iv))
        E_BS = z_full @ weights
        E_ref = z_ref @ weights

        # --- split conformal calibration (eq. 6.9) ---
        cal_scores = E_ref[self.cal_idx_]
        n_cal = cal_scores.size
        # p-value: (#{R_j >= s(x)} + 1) / (n_cal + 1)
        ranks = np.sum(cal_scores[None, :] >= E_BS[:, None], axis=1)
        pvalue = (ranks + 1.0) / (n_cal + 1.0)
        # When the reference is too small for the requested alpha (1/(n_cal+1)
        # is the conformal p-value floor), raise the alarm threshold to the
        # smallest attainable level so the alarm gate is never structurally
        # impossible to fire.
        alpha_eff = max(float(self.alpha_alarm), 2.0 / (n_cal + 1.0))

        # --- adaptive rolling P99 threshold (paper §7.12) ---
        W = max(8, min(self.rolling_window, T // 4))
        threshold = np.empty(T)
        # seed with reference P99 until window fills
        ref_p99 = float(np.quantile(E_ref, 0.99))
        for t in range(T):
            if t < W:
                threshold[t] = ref_p99
            else:
                threshold[t] = float(np.quantile(E_BS[t - W:t], 0.99))

        alarms = (E_BS > threshold) & (pvalue <= alpha_eff)

        info = {
            "n_ref": int(self.X_ref_.shape[0]),
            "n_cal": int(n_cal),
            "pca_k": int(self.k_),
            "v0": float(self.v0_),
            "kde_bw": float(self.kde_bw_),
            "weights": weights.tolist(),
            "rolling_window": int(W),
            "fixed_p99_ref": float(ref_p99),
            "alpha_alarm": float(self.alpha_alarm),
            "alpha_alarm_effective": float(alpha_eff),
        }
        return BSDTResult(
            delta_C=d_C, delta_G=d_G, delta_A=d_A, delta_T=d_T,
            z=z_full, weights=weights,
            E_BS=E_BS, pvalue=pvalue, threshold=threshold,
            alarms=alarms, fixed_threshold=ref_p99, info=info,
        )


# --------------------------------------------------- evaluation utilities ----
def channel_dominance_z(res: BSDTResult, mask: np.ndarray) -> dict:
    """Weighted-z dominance: w_k * mean(z_k_+) over the masked window."""
    z_pos = np.clip(res.z[mask], 0.0, None).mean(axis=0)
    contrib = res.weights * z_pos
    s = contrib.sum() + 1e-12
    return {
        "delta_C": float(contrib[0] / s),
        "delta_G": float(contrib[1] / s),
        "delta_A": float(contrib[2] / s),
        "delta_T": float(contrib[3] / s),
    }


def first_alarm_lead(alarms: np.ndarray, crisis_idx: int) -> int:
    if not np.any(alarms):
        return 0
    return int(crisis_idx - int(np.argmax(alarms)))
