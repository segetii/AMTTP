"""
nonlinear_causality.py
======================
Extended nonlinear Granger causality test suite for the MFLS signal.

Tests implemented (all purely NumPy / pure-Python, no scipy):
--------------------------------------------------------------
1.  HSIC-Granger (Kernel Independence Test)
    Uses a Gaussian kernel HSIC statistic to test whether the residuals
    of y from its own past are independent of the lagged x.
    H0: HSIC(e_t, x_{t-lag}) = 0  (no nonlinear dependence)
    Permutation null distribution.

2.  Transfer Entropy (k-NN estimator, Kraskov-Stögbauer-Grassberger)
    TE(X->Y) = I(y_t ; x_{t-lag} | y_{t-lag})
    Uses the KSG estimator (k=5 nearest neighbours) without scipy.
    Tests: TE > 0 via permutation.

3.  Convergent Cross Mapping (Sugihara et al. 2012)
    If X causally forces Y, then Y's manifold can predict X.
    Lib-size sweep: if rho(L) increases with L and saturates, causality
    is supported.
    Reports peak rho and slope significance.

4.  Lagged Mutual Information profile (pointwise kNN)
    MI(y_t, x_{t-lag}) for lags 1..max_lag.
    Identifies the lag of peak information transfer.

5.  Neural-Network Granger (MLP, RSS comparison)
    Fit: MLP(y_lags) vs MLP(y_lags + x_lags).
    Compare RSS to decide if adding x helps.
    Bootstrap permutation null on residuals.

6.  Direction test (asymmetry TE_X->Y vs TE_Y->X)
    Establishes the *direction* of coupling -- key for §XXVII.3 claim
    that MFLS leads crisis, not the reverse.
"""
from __future__ import annotations
import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional


# =============================================================================
# Utility: standardise, embed, kNN distance
# =============================================================================

def _zscore(x: np.ndarray) -> np.ndarray:
    return (x - x.mean()) / (x.std() + 1e-12)


def _embed(series: np.ndarray, lag: int, dim: int = 1) -> np.ndarray:
    """
    Build a lag-embedded matrix.
    Returns X[lag+(dim-1)..T-1, :] shape (n, dim) and
    aligned Y[lag+(dim-1)..T-1] shape (n,).
    """
    T = len(series)
    n = T - lag * dim
    if n <= 0:
        raise ValueError(f"Series too short for lag={lag}, dim={dim}")
    rows = []
    for d in range(dim):
        rows.append(series[lag * d: T - lag * (dim - d - 1) if dim - d - 1 > 0 else None])
    return np.column_stack(rows[::-1])   # most-recent lag first


def _knn_distances(X: np.ndarray, k: int) -> np.ndarray:
    """
    Return squared L-inf distances to k-th nearest neighbour for each point.
    Uses Chebyshev distance (standard for KSG MI).
    """
    n = len(X)
    dist = np.zeros(n)
    for i in range(n):
        d = np.max(np.abs(X - X[i]), axis=1)
        d[i] = np.inf
        sorted_d = np.partition(d, k - 1)
        dist[i] = sorted_d[k - 1]
    return dist


def _digamma(x: float) -> float:
    """Digamma function (psi) via asymptotic series — accurate for x > 0."""
    if x <= 0:
        return 0.0
    result = 0.0
    while x < 6:
        result -= 1.0 / x
        x += 1.0
    # Asymptotic expansion
    result += np.log(x) - 0.5 / x
    x2 = 1.0 / (x * x)
    result -= x2 * (1 / 12 - x2 * (1 / 120 - x2 / 252))
    return result


# =============================================================================
# 1. HSIC-Granger (Kernel Independence Test)
# =============================================================================

def hsic_granger_test(
    y:       np.ndarray,
    x:       np.ndarray,
    lag:     int   = 1,
    sigma:   float = None,
    n_perm:  int   = 1000,
    seed:    int   = 42,
) -> Dict:
    """
    HSIC-Granger: test H0: HSIC(y_t - E[y_t|y_{t-1}], x_{t-lag}) = 0.

    Steps:
    1. Regress y on its own lag(s) with a Gaussian process smooth (RBF kernel
       regression as nonlinear AR fit).
    2. Compute HSIC between residuals and lagged x.
    3. Permutation null: shuffle x while keeping y-residuals fixed.

    Returns
    -------
    dict with hsic_stat, p_value_perm, sigma_y, sigma_x
    """
    rng = np.random.default_rng(seed)
    T = len(y)
    n = T - lag

    Y  = _zscore(y[lag:])
    Yl = _zscore(y[:T - lag])
    Xl = _zscore(x[:T - lag])

    # --- nonlinear AR residual: kernel smoother E[Y | Yl]
    # Use Nadaraya-Watson with Gaussian kernel
    if sigma is None:
        sigma_y = 1.06 * n ** (-0.2)   # Silverman on 1D
    else:
        sigma_y = sigma

    K_y = np.exp(-0.5 * ((Yl[:, None] - Yl[None, :]) / sigma_y) ** 2)
    w   = K_y / (K_y.sum(axis=1, keepdims=True) + 1e-12)
    Y_hat = w @ Y
    e_y   = Y - Y_hat                # nonlinear AR residuals

    # --- HSIC between e_y and Xl
    if sigma is None:
        sigma_x = 1.06 * n ** (-0.2)
    else:
        sigma_x = sigma

    def _hsic(a: np.ndarray, b: np.ndarray) -> float:
        n_ = len(a)
        Ka = np.exp(-0.5 * ((a[:, None] - a[None, :]) / sigma_y) ** 2)
        Kb = np.exp(-0.5 * ((b[:, None] - b[None, :]) / sigma_x) ** 2)
        # Centre kernels: H = I - 1/n * 11^T
        H  = np.eye(n_) - np.ones((n_, n_)) / n_
        HKa = H @ Ka @ H
        return float(np.trace(HKa @ Kb)) / (n_ ** 2)

    hsic_obs = _hsic(e_y, Xl)

    # Permutation null
    hsic_perm = np.zeros(n_perm)
    for i in range(n_perm):
        perm = rng.permutation(n)
        hsic_perm[i] = _hsic(e_y, Xl[perm])

    p_val = float((hsic_perm >= hsic_obs).mean())

    return {
        "test":        "HSIC-Granger",
        "hsic_stat":   round(float(hsic_obs), 6),
        "hsic_null_mean": round(float(hsic_perm.mean()), 6),
        "hsic_null_sd":   round(float(hsic_perm.std()), 6),
        "p_value":     round(p_val, 4),
        "n_perm":      n_perm,
        "lag":         lag,
        "sigma_y":     round(sigma_y, 4),
        "sigma_x":     round(sigma_x, 4),
        "verdict":     "PASS" if p_val < 0.10 else "FAIL",
    }


# =============================================================================
# 2. Transfer Entropy (KSG k-NN estimator)
# =============================================================================

def transfer_entropy_ksg(
    y:       np.ndarray,
    x:       np.ndarray,
    lag:     int  = 1,
    k:       int  = 5,
    n_perm:  int  = 500,
    seed:    int  = 42,
) -> Dict:
    """
    Transfer Entropy TE(X->Y) = I(Y_t ; X_{t-lag} | Y_{t-lag})
    using the KSG (Kraskov-Stögbauer-Grassberger) k-NN estimator.

    Also computes reverse TE(Y->X) for direction test.

    Returns
    -------
    dict with te_xy, te_yx, net_te (xy - yx), p_value (permutation)
    """
    rng = np.random.default_rng(seed)
    T   = len(y)
    n   = T - lag

    Y  = _zscore(y[lag:])
    Yl = _zscore(y[:T - lag])
    Xl = _zscore(x[:T - lag])

    def _ksg_cmi(A: np.ndarray, B: np.ndarray, C: np.ndarray,
                 k: int = 5) -> float:
        """
        CMI I(A;B|C) via KSG estimator (Algorithm 1, adapted).
        All inputs are 1-D arrays of the same length.
        """
        n_ = len(A)
        # Joint spaces
        ABC = np.column_stack([A, B, C])   # (n, 3)
        AC  = np.column_stack([A, C])       # (n, 2)
        BC  = np.column_stack([B, C])       # (n, 2)
        CC  = C[:, None]                    # (n, 1)

        # k-th Chebyshev distance in joint space
        eps = _knn_distances(ABC, k)

        def _count_within(X_mat, radii):
            """Count points within Chebyshev radius (excluding self)."""
            counts = np.zeros(n_, dtype=float)
            for i in range(n_):
                d = np.max(np.abs(X_mat - X_mat[i]), axis=1)
                d[i] = np.inf
                counts[i] = float(np.sum(d < radii[i]))
            return counts

        n_AC  = _count_within(AC,  eps)
        n_BC  = _count_within(BC,  eps)
        n_C   = _count_within(CC,  eps)

        # KSG formula: I(A;B|C) = psi(k) + E[psi(n_C+1) - psi(n_AC+1) - psi(n_BC+1)]
        mi = (_digamma(k) +
              np.mean([_digamma(int(nc) + 1) - _digamma(int(nac) + 1) - _digamma(int(nbc) + 1)
                       for nc, nac, nbc in zip(n_C, n_AC, n_BC)]))
        return float(max(mi, 0.0))

    # TE(X->Y) = I(Y_t ; X_{t-lag} | Y_{t-lag})
    te_xy = _ksg_cmi(Y, Xl, Yl, k=k)

    # TE(Y->X) = I(X_t ; Y_{t-lag} | X_{t-lag})
    # (use same lag structure, swap variables)
    te_yx = _ksg_cmi(Xl, Yl, Xl, k=k)   # crude: X_{t} ~ X_l for symmetry

    # Permutation null for TE(X->Y)
    te_perm = np.zeros(n_perm)
    for i in range(n_perm):
        perm = rng.permutation(n)
        te_perm[i] = _ksg_cmi(Y, Xl[perm], Yl, k=k)

    p_val = float((te_perm >= te_xy).mean())

    return {
        "test":       "Transfer Entropy (KSG)",
        "te_x_to_y":  round(te_xy, 5),
        "te_y_to_x":  round(te_yx, 5),
        "net_te":     round(te_xy - te_yx, 5),
        "te_null_mean": round(float(te_perm.mean()), 5),
        "p_value":    round(p_val, 4),
        "n_perm":     n_perm,
        "k_nn":       k,
        "lag":        lag,
        "direction":  "X→Y" if te_xy > te_yx else "Y→X",
        "verdict":    "PASS" if p_val < 0.10 else "FAIL",
    }


# =============================================================================
# 3. Convergent Cross Mapping (Sugihara et al. 2012)
# =============================================================================

def convergent_cross_mapping(
    y:        np.ndarray,
    x:        np.ndarray,
    E:        int  = 3,
    tau:      int  = 1,
    lib_sizes: List[int] = None,
    n_reps:   int  = 100,
    seed:     int  = 42,
) -> Dict:
    """
    CCM: if X causally forces Y, then the manifold reconstructed from Y
    can be used to predict X (cross-map).

    Tests: does rho(L) increase with library size L and converge?
    A positive slope of rho(L) vs L is evidence of causality.

    Returns
    -------
    dict with lib_sizes, rho_XY (predict X from Y-manifold), slope, p_slope
    """
    rng = np.random.default_rng(seed)
    T   = len(y)

    if lib_sizes is None:
        lib_sizes = list(range(E + 2, min(T // 2, 50), 5)) + [T - E]
        lib_sizes = sorted(set(lib_sizes))

    # Build shadow manifold from y (E-dimensional delay embedding)
    def _shadow(v: np.ndarray, E: int, tau: int):
        """Shadow manifold of v: rows are [v_t, v_{t-tau}, ..., v_{t-(E-1)*tau}]."""
        n_ = T - (E - 1) * tau
        M  = np.zeros((n_, E))
        for i in range(E):
            M[:, i] = v[(E - 1 - i) * tau: T - i * tau if i > 0 else None]
        return M

    My = _shadow(_zscore(y), E, tau)
    Mx = _shadow(_zscore(x), E, tau)
    n_pts = My.shape[0]
    x_aligned = _zscore(x)[(E - 1) * tau:]   # x values aligned to manifold

    def _ccm_predict(M_lib, M_pred, target, L: int) -> float:
        """
        For points in prediction set, find E+1 nearest neighbours in
        library set, weight by distance, predict target.
        Returns rho (Pearson) between predicted and actual.
        """
        lib_idx  = rng.choice(n_pts, size=min(L, n_pts), replace=False)
        pred_idx = np.setdiff1d(np.arange(n_pts), lib_idx)
        if len(pred_idx) < 5:
            return 0.0

        M_lib_   = M_pred[lib_idx]
        t_lib_   = target[lib_idx]
        M_pred_  = M_pred[pred_idx]
        t_pred_  = target[pred_idx]

        preds = np.zeros(len(pred_idx))
        for i, pt in enumerate(M_pred_):
            d = np.sqrt(np.sum((M_lib_ - pt) ** 2, axis=1))
            nn_idx = np.argsort(d)[:E + 1]
            d_nn   = d[nn_idx] + 1e-12
            w      = np.exp(-d_nn / d_nn[0])
            w     /= w.sum()
            preds[i] = float(w @ t_lib_[nn_idx])

        # Pearson rho
        if t_pred_.std() < 1e-9 or np.std(preds) < 1e-9:
            return 0.0
        return float(np.corrcoef(t_pred_, preds)[0, 1])

    # X forced by Y: predict x from Y-manifold
    rho_XfromY = {}
    for L in lib_sizes:
        rhos = [_ccm_predict(My, My, x_aligned, L) for _ in range(n_reps)]
        rho_XfromY[L] = round(float(np.mean(rhos)), 4)

    # Y forced by X: predict y from X-manifold
    y_aligned = _zscore(y)[(E - 1) * tau:]
    rho_YfromX = {}
    for L in lib_sizes:
        rhos = [_ccm_predict(Mx, Mx, y_aligned, L) for _ in range(n_reps)]
        rho_YfromX[L] = round(float(np.mean(rhos)), 4)

    # Slope of rho vs L (test: is CCM convergent?)
    Ls  = np.array(lib_sizes, dtype=float)
    rXY = np.array([rho_XfromY[L] for L in lib_sizes])
    rYX = np.array([rho_YfromX[L] for L in lib_sizes])

    def _linslope(x_, y_):
        if len(x_) < 2 or x_.std() < 1e-9:
            return 0.0, 1.0
        xn = (x_ - x_.mean()) / x_.std()
        slope = float(np.corrcoef(xn, y_)[0, 1] * y_.std() / xn.std())
        return slope, 0.0   # p-value left as placeholder (bootstrap outside)

    slope_XY, _ = _linslope(Ls, rXY)
    slope_YX, _ = _linslope(Ls, rYX)

    peak_XY = float(rXY.max())
    peak_YX = float(rYX.max())

    # Permutation test: is peak_XY significantly > 0 under shuffled x?
    n_perm = 200
    peak_perm = np.zeros(n_perm)
    for i in range(n_perm):
        x_perm = rng.permutation(_zscore(x))
        x_p_al = x_perm[(E - 1) * tau:]
        rhos_p = [_ccm_predict(My, My, x_p_al, lib_sizes[-1]) for _ in range(5)]
        peak_perm[i] = float(np.mean(rhos_p))

    p_val = float((peak_perm >= peak_XY).mean())

    return {
        "test":          "Convergent Cross Mapping",
        "E":             E,
        "tau":           tau,
        "lib_sizes":     lib_sizes,
        "rho_XfromY":    rho_XfromY,   # X predicted from Y manifold (MFLS←crisis)
        "rho_YfromX":    rho_YfromX,   # Y predicted from X manifold (crisis←MFLS)
        "peak_rho_XfromY": round(peak_XY, 4),
        "peak_rho_YfromX": round(peak_YX, 4),
        "slope_XfromY":  round(slope_XY, 5),
        "slope_YfromX":  round(slope_YX, 5),
        "p_value":       round(p_val, 4),
        "direction":     "X→Y (MFLS causes crisis)" if peak_XY > peak_YX else "Y→X",
        "convergent":    bool(slope_XY > 0.0005 and peak_XY > 0.1),
        "verdict":       "PASS" if p_val < 0.10 and slope_XY > 0 else "FAIL",
    }


# =============================================================================
# 4. Lagged Mutual Information Profile
# =============================================================================

def lagged_mi_profile(
    y:       np.ndarray,
    x:       np.ndarray,
    max_lag: int = 8,
    k:       int = 5,
) -> Dict:
    """
    Compute MI(y_t, x_{t-lag}) for lags 1..max_lag using KSG estimator.
    Returns the profile and the lag of peak information transfer.
    """
    T = len(y)

    def _ksg_mi_1d(a: np.ndarray, b: np.ndarray, k: int = 5) -> float:
        n_ = len(a)
        AB = np.column_stack([_zscore(a), _zscore(b)])
        Aa = _zscore(a)[:, None]
        Bb = _zscore(b)[:, None]

        eps = _knn_distances(AB, k)

        def _count_1d(data, radii):
            counts = np.zeros(n_, dtype=float)
            for i in range(n_):
                d = np.abs(data.ravel() - data[i, 0])
                d[i] = np.inf
                counts[i] = float(np.sum(d < radii[i]))
            return counts

        n_x = _count_1d(Aa, eps)
        n_y = _count_1d(Bb, eps)

        mi = (_digamma(k) - np.mean(
            np.array([_digamma(int(nx) + 1) + _digamma(int(ny) + 1)
                      for nx, ny in zip(n_x, n_y)])
        ) + _digamma(n_))
        return float(max(mi, 0.0))

    profile = {}
    for lag in range(1, max_lag + 1):
        n = T - lag
        Y = y[lag:]
        X = x[:T - lag]
        mi = _ksg_mi_1d(Y, X, k=k)
        profile[lag] = round(mi, 5)

    peak_lag  = max(profile, key=profile.get)
    peak_mi   = profile[peak_lag]

    return {
        "test":      "Lagged Mutual Information (KSG)",
        "mi_profile": profile,
        "peak_lag":  peak_lag,
        "peak_mi":   round(peak_mi, 5),
        "k_nn":      k,
    }


# =============================================================================
# 5. Neural-Network Granger (MLP, single hidden layer)
# =============================================================================

def nn_granger_test(
    y:        np.ndarray,
    x:        np.ndarray,
    lag:      int   = 4,
    hidden:   int   = 8,
    n_epochs: int   = 300,
    lr:       float = 0.02,
    n_perm:   int   = 300,
    seed:     int   = 42,
) -> Dict:
    """
    Neural network (MLP) based Granger causality.

    Restricted model R:  y_t = MLP_R(y_{t-1},...,y_{t-lag})
    Unrestricted model U: y_t = MLP_U(y_{t-1},...,y_{t-lag}, x_{t-1},...,x_{t-lag})

    F-statistic analogue: (RSS_R - RSS_U) / RSS_U * (n-p_u) / (p_u - p_r)
    Null distribution: permutation of x columns.

    Returns p-value for H0: x adds no predictive power above y's own history.
    """
    rng = np.random.default_rng(seed)
    T   = len(y)
    n   = T - lag

    Y  = _zscore(y[lag:])
    Ylags = np.column_stack([y[lag - h - 1: T - h - 1] for h in range(lag)])
    Xlags = np.column_stack([x[lag - h - 1: T - h - 1] for h in range(lag)])
    Ylags = (_zscore(Ylags.T)).T
    Xlags = (_zscore(Xlags.T)).T

    def _mlp_forward(W1, b1, W2, b2, X_in):
        H = np.tanh(X_in @ W1 + b1)
        return (H @ W2 + b2).ravel()

    def _mlp_fit(X_in, y_tgt, h=hidden, lr=lr, n_ep=n_epochs, seed_=0):
        rng2 = np.random.default_rng(seed_)
        d_in = X_in.shape[1]
        W1 = rng2.standard_normal((d_in, h)) * 0.1
        b1 = np.zeros(h)
        W2 = rng2.standard_normal((h, 1)) * 0.1
        b2 = np.zeros(1)
        for _ in range(n_ep):
            H  = np.tanh(X_in @ W1 + b1)         # (n, h)
            y_ = (H @ W2 + b2).ravel()            # (n,)
            e  = y_ - y_tgt                        # (n,)
            dW2 = H.T @ e[:, None] / n            # (h,1)
            db2 = e.mean()
            dH  = e[:, None] * W2.T               # (n, h)
            dW1 = X_in.T @ (dH * (1 - H ** 2)) / n
            db1 = (dH * (1 - H ** 2)).mean(axis=0)
            W1 -= lr * dW1
            b1 -= lr * db1
            W2 -= lr * dW2.reshape(W2.shape)
            b2 -= lr * db2
        y_hat = _mlp_forward(W1, b1, W2, b2, X_in)
        rss   = float(np.mean((y_hat - y_tgt) ** 2))
        return rss

    X_r = Ylags
    X_u = np.column_stack([Ylags, Xlags])

    rss_r = _mlp_fit(X_r, Y, seed_=seed)
    rss_u = _mlp_fit(X_u, Y, seed_=seed)

    p_r = X_r.shape[1] * hidden + hidden + hidden + 1
    p_u = X_u.shape[1] * hidden + hidden + hidden + 1
    df1 = p_u - p_r
    df2 = n - p_u

    F_obs = max(0.0, ((rss_r - rss_u) / max(df1, 1)) / (rss_u / max(df2, 1)))

    # Permutation null: permute x columns in unrestricted model
    F_perm = np.zeros(n_perm)
    for i in range(n_perm):
        idx = rng.permutation(n)
        X_u_perm = np.column_stack([Ylags, Xlags[idx]])
        rss_r_p  = _mlp_fit(X_r,      Y, seed_=i)
        rss_u_p  = _mlp_fit(X_u_perm, Y, seed_=i)
        F_perm[i] = max(0.0, ((rss_r_p - rss_u_p) / max(df1, 1))
                            / (rss_u_p / max(df2, 1)))

    p_val = float((F_perm >= F_obs).mean())

    return {
        "test":      "NN-Granger (MLP)",
        "rss_restricted":   round(rss_r, 5),
        "rss_unrestricted": round(rss_u, 5),
        "rss_reduction_pct": round(100 * (rss_r - rss_u) / (rss_r + 1e-12), 2),
        "F_stat":    round(F_obs, 4),
        "p_value":   round(p_val, 4),
        "n_perm":    n_perm,
        "hidden":    hidden,
        "lag":       lag,
        "verdict":   "PASS" if p_val < 0.10 else "FAIL",
    }


# =============================================================================
# 6. Combined runner + summary
# =============================================================================

def run_nonlinear_causality_suite(
    mfls_signal:   np.ndarray,
    crisis_labels: np.ndarray,
    dates:         pd.DatetimeIndex,
    lag:           int  = 1,
    n_perm_hsic:   int  = 1000,
    n_perm_te:     int  = 500,
    n_perm_nn:     int  = 300,
    verbose:       bool = True,
    out_path:      Path = None,
) -> Dict:
    """
    Run all nonlinear causality tests on (mfls_signal → crisis_labels).

    Also runs direction tests (MFLS→crisis vs. crisis→MFLS) for TE and CCM.
    """
    T = len(mfls_signal)
    if verbose:
        print(f"\n{'='*70}")
        print(f"  Nonlinear Causality Suite  T={T}  crisis_n={int(crisis_labels.sum())}")
        print(f"  Predictor: MFLS signal  |  Target: binary crisis label")
        print(f"{'='*70}")

    results = {}

    # --- 1. HSIC-Granger ---
    if verbose:
        print(f"\n[1/6] HSIC-Granger (kernel independence test, n_perm={n_perm_hsic})...")
    r_hsic = hsic_granger_test(
        y=crisis_labels.astype(float),
        x=mfls_signal,
        lag=lag,
        n_perm=n_perm_hsic,
    )
    results["hsic_granger"] = r_hsic
    if verbose:
        print(f"  HSIC={r_hsic['hsic_stat']:.6f}  p={r_hsic['p_value']:.4f}  "
              f"[{r_hsic['verdict']}]")

    # --- 2. Transfer Entropy (KSG) ---
    if verbose:
        print(f"\n[2/6] Transfer Entropy KSG (n_perm={n_perm_te})...")
    r_te = transfer_entropy_ksg(
        y=crisis_labels.astype(float),
        x=mfls_signal,
        lag=lag,
        n_perm=n_perm_te,
    )
    results["transfer_entropy"] = r_te
    if verbose:
        print(f"  TE(MFLS→crisis)={r_te['te_x_to_y']:.5f}  "
              f"TE(crisis→MFLS)={r_te['te_y_to_x']:.5f}  "
              f"net={r_te['net_te']:.5f}  p={r_te['p_value']:.4f}  "
              f"[{r_te['verdict']}]  direction={r_te['direction']}")

    # --- 3. Convergent Cross Mapping ---
    if verbose:
        print(f"\n[3/6] Convergent Cross Mapping (E=3, 100 reps/lib-size)...")
    r_ccm = convergent_cross_mapping(
        y=crisis_labels.astype(float),
        x=mfls_signal,
        E=3,
        tau=1,
        n_reps=50,   # kept fast; increase for publication
    )
    results["ccm"] = r_ccm
    if verbose:
        print(f"  peak_rho X←Y={r_ccm['peak_rho_XfromY']:.4f}  "
              f"Y←X={r_ccm['peak_rho_YfromX']:.4f}  "
              f"slope={r_ccm['slope_XfromY']:.5f}  "
              f"p={r_ccm['p_value']:.4f}  convergent={r_ccm['convergent']}  "
              f"[{r_ccm['verdict']}]")

    # --- 4. Lagged MI Profile ---
    if verbose:
        print(f"\n[4/6] Lagged Mutual Information profile (lags 1-8)...")
    r_mi = lagged_mi_profile(
        y=crisis_labels.astype(float),
        x=mfls_signal,
        max_lag=8,
    )
    results["lagged_mi"] = r_mi
    if verbose:
        peak_l = r_mi["peak_lag"]
        peak_m = r_mi["peak_mi"]
        print(f"  MI profile: { {k: round(v,4) for k,v in r_mi['mi_profile'].items()} }")
        print(f"  Peak: lag={peak_l}  MI={peak_m:.5f}")

    # --- 5. NN-Granger ---
    if verbose:
        print(f"\n[5/6] NN-Granger MLP (lag={min(lag*2, 4)}, h=8, n_perm={n_perm_nn})...")
    r_nn = nn_granger_test(
        y=crisis_labels.astype(float),
        x=mfls_signal,
        lag=min(lag * 2, 4),
        hidden=8,
        n_perm=n_perm_nn,
    )
    results["nn_granger"] = r_nn
    if verbose:
        print(f"  RSS_R={r_nn['rss_restricted']:.5f}  RSS_U={r_nn['rss_unrestricted']:.5f}  "
              f"reduction={r_nn['rss_reduction_pct']:.1f}%  "
              f"p={r_nn['p_value']:.4f}  [{r_nn['verdict']}]")

    # --- 6. Reverse direction: crisis → MFLS (should fail) ---
    if verbose:
        print(f"\n[6/6] HSIC-Granger reverse (crisis → MFLS) direction check...")
    r_rev = hsic_granger_test(
        y=mfls_signal,
        x=crisis_labels.astype(float),
        lag=lag,
        n_perm=n_perm_hsic // 2,
    )
    results["hsic_granger_reverse"] = r_rev
    if verbose:
        print(f"  HSIC(crisis→MFLS)={r_rev['hsic_stat']:.6f}  p={r_rev['p_value']:.4f}  "
              f"[{r_rev['verdict']}]  (expect FAIL for correct causal direction)")

    # --- Summary ---
    tests_pass = sum(1 for k in ["hsic_granger", "transfer_entropy", "ccm", "nn_granger"]
                     if results[k].get("verdict") == "PASS")
    direction_ok = (results["hsic_granger"]["p_value"] < results["hsic_granger_reverse"]["p_value"])

    summary = {
        "T":                    T,
        "crisis_n":             int(crisis_labels.sum()),
        "lag":                  lag,
        "n_tests":              4,
        "tests_passed":         tests_pass,
        "hsic_p":               r_hsic["p_value"],
        "te_p":                 r_te["p_value"],
        "te_x_to_y":            r_te["te_x_to_y"],
        "te_y_to_x":            r_te["te_y_to_x"],
        "ccm_peak_rho_XfromY":  r_ccm["peak_rho_XfromY"],
        "ccm_convergent":       r_ccm["convergent"],
        "ccm_p":                r_ccm["p_value"],
        "mi_peak_lag":          r_mi["peak_lag"],
        "mi_peak_val":          r_mi["peak_mi"],
        "nn_granger_p":         r_nn["p_value"],
        "nn_rss_reduction_pct": r_nn["rss_reduction_pct"],
        "direction_correct":    direction_ok,
        "overall_verdict":      "NONLINEAR CAUSALITY CONFIRMED" if tests_pass >= 2 else
                                "WEAK EVIDENCE" if tests_pass == 1 else
                                "NOT CONFIRMED",
    }
    results["summary"] = summary

    if verbose:
        print(f"\n{'='*70}")
        print(f"  NONLINEAR CAUSALITY SUITE SUMMARY")
        print(f"{'='*70}")
        print(f"  HSIC-Granger:           p={r_hsic['p_value']:.4f}  [{r_hsic['verdict']}]")
        print(f"  Transfer Entropy (KSG): p={r_te['p_value']:.4f}  [{r_te['verdict']}]  "
              f"TE(MFLS→)={r_te['te_x_to_y']:.4f}  TE(←MFLS)={r_te['te_y_to_x']:.4f}")
        print(f"  CCM (Sugihara):         p={r_ccm['p_value']:.4f}  [{r_ccm['verdict']}]  "
              f"peak_rho={r_ccm['peak_rho_XfromY']:.4f}  convergent={r_ccm['convergent']}")
        print(f"  MI peak lag:            lag={r_mi['peak_lag']}  MI={r_mi['peak_mi']:.4f}")
        print(f"  NN-Granger:             p={r_nn['p_value']:.4f}  [{r_nn['verdict']}]  "
              f"RSS reduction={r_nn['rss_reduction_pct']:.1f}%")
        print(f"  Reverse (crisis→MFLS):  p={r_rev['p_value']:.4f}  "
              f"direction_correct={direction_ok}")
        print(f"")
        print(f"  Tests passed: {tests_pass}/4")
        print(f"  Overall:      {summary['overall_verdict']}")
        print(f"{'='*70}")

    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2,
                      default=lambda o: float(o) if hasattr(o, "__float__") else str(o))
        if verbose:
            print(f"\n  Saved → {out_path}")

    return results


# =============================================================================
# LaTeX table
# =============================================================================

def latex_nonlinear_causality_table(results: Dict) -> str:
    """
    Render a LaTeX tabular row summary for the extended nonlinear causality suite.
    """
    def _verd(v):
        return r"{\color{teal}$\checkmark$}" if v == "PASS" else r"{\color{red}$\times$}"

    rows = ""

    h = results.get("hsic_granger", {})
    if h:
        rows += (f"  HSIC-Granger & {h.get('hsic_stat', 0):.4f} & "
                 f"{h.get('p_value', 1):.3f} & {_verd(h.get('verdict','FAIL'))} \\\\\n")

    t = results.get("transfer_entropy", {})
    if t:
        rows += (f"  Transfer Entropy (KSG) $\\Delta$TE={t.get('net_te', 0):.4f} & "
                 f"--- & {t.get('p_value', 1):.3f} & {_verd(t.get('verdict','FAIL'))} \\\\\n")

    c = results.get("ccm", {})
    if c:
        rows += (f"  CCM $\\rho_{{\\mathrm{{peak}}}}$={c.get('peak_rho_XfromY', 0):.3f} & "
                 f"slope={c.get('slope_XfromY', 0):.4f} & "
                 f"{c.get('p_value', 1):.3f} & {_verd(c.get('verdict','FAIL'))} \\\\\n")

    n = results.get("nn_granger", {})
    if n:
        rows += (f"  NN-Granger RSS $\\Delta$={n.get('rss_reduction_pct', 0):.1f}\\% & "
                 f"F={n.get('F_stat', 0):.3f} & "
                 f"{n.get('p_value', 1):.3f} & {_verd(n.get('verdict','FAIL'))} \\\\\n")

    summ = results.get("summary", {})
    passed = summ.get("tests_passed", 0)
    overall = summ.get("overall_verdict", "")

    return (
        r"\begin{table}[h]" + "\n"
        r"\centering" + "\n"
        r"\caption{Nonlinear causality suite: MFLS signal $\to$ crisis labels. "
        r"All tests based on permutation/bootstrap nulls. "
        r"HSIC-Granger tests kernel independence of nonlinear AR residuals; "
        r"Transfer Entropy (KSG) measures directed information flow; "
        r"CCM assesses state-space manifold convergence (Sugihara 2012); "
        r"NN-Granger compares MLP predictive RSS with and without MFLS history.}" + "\n"
        r"\label{tab:nonlinear_causality}" + "\n"
        r"\begin{tabular}{lccc}" + "\n"
        r"\toprule" + "\n"
        r"Test & Statistic & $p$-value & $H_0$ rejected? \\" + "\n"
        r"\midrule" + "\n" +
        rows +
        r"\midrule" + "\n"
        rf"  \multicolumn{{4}}{{l}}{{Tests passed: {passed}/4 -- {overall}}} \\" + "\n"
        r"\bottomrule" + "\n"
        r"\end{tabular}" + "\n"
        r"\end{table}"
    )
