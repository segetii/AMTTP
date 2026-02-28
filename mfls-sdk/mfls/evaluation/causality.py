"""
Granger causality test suite.

Four tests:
  1. Linear Granger (VAR F-test)
  2. Threshold Granger (regime-dependent, bootstrap)
  3. Quantile causality (quantile regression, block bootstrap)
  4. Exceedance regression (tail-risk P(Y > threshold | X))
"""

from __future__ import annotations

import warnings
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Internal: OLS and F-distribution
# ---------------------------------------------------------------------------

def _ols(X: np.ndarray, y: np.ndarray):
    """OLS regression. Returns (beta, residuals, r_squared)."""
    XtX = X.T @ X
    try:
        beta = np.linalg.solve(XtX + 1e-10 * np.eye(XtX.shape[0]), X.T @ y)
    except np.linalg.LinAlgError:
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ beta
    return beta, resid, float(np.sum(resid ** 2))


def _lgamma(x):
    """Log-gamma via Lanczos approximation."""
    if x <= 0:
        return 0.0
    g = 7
    c = [
        0.99999999999980993, 676.5203681218851, -1259.1392167224028,
        771.32342877765313, -176.61502916214059, 12.507343278686905,
        -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7,
    ]
    x -= 1
    s = c[0]
    for i in range(1, g + 2):
        s += c[i] / (x + i)
    t = x + g + 0.5
    return 0.5 * np.log(2 * np.pi) + (x + 0.5) * np.log(t) - t + np.log(s)


def _lbeta(a, b):
    return _lgamma(a) + _lgamma(b) - _lgamma(a + b)


def _ibeta(x, a, b, n_iter=200):
    """Regularised incomplete beta via continued fraction."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = np.exp(a * np.log(x) + b * np.log(1 - x) - _lbeta(a, b)) / a
    # Lentz's method
    f = 1.0
    c = 1.0
    d = 1.0 - (a + b) * x / (a + 1)
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    f = d
    for m in range(1, n_iter + 1):
        # even step
        num = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m))
        d = 1.0 + num * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + num / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        f *= c * d
        # odd step
        num = -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1.0 + num * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + num / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = c * d
        f *= delta
        if abs(delta - 1.0) < 1e-10:
            break
    return front * f


def _f_pvalue(F: float, df1: int, df2: int) -> float:
    """P-value for F-statistic using incomplete beta."""
    if F <= 0 or df1 <= 0 or df2 <= 0:
        return 1.0
    x = df2 / (df2 + df1 * F)
    return _ibeta(x, df2 / 2.0, df1 / 2.0)


# ---------------------------------------------------------------------------
# 1. Linear Granger
# ---------------------------------------------------------------------------

def linear_granger_test(
    y: np.ndarray,
    x: np.ndarray,
    max_lag: int = 4,
) -> Dict:
    """
    Standard Granger causality (F-test): does x Granger-cause y?

    Parameters
    ----------
    y : ndarray (T,) — dependent variable (e.g. SRISK proxy)
    x : ndarray (T,) — predictor (MFLS signal)
    max_lag : int

    Returns
    -------
    dict keyed lag1..lag{max_lag} → {F_stat, p_value, df1, df2}
    """
    T = len(y)
    results = {}
    for h in range(1, max_lag + 1):
        if T <= 2 * h + 2:
            continue
        Y = y[h:]
        n = len(Y)

        # Restricted: only lags of y
        Xr = np.column_stack([y[h - j:T - j] for j in range(1, h + 1)])
        Xr = np.column_stack([np.ones(n), Xr])
        _, _, rss_r = _ols(Xr, Y)

        # Unrestricted: lags of y + lags of x
        Xu = np.column_stack([Xr, *[x[h - j:T - j] for j in range(1, h + 1)]])
        _, _, rss_u = _ols(Xu, Y)

        df1 = h
        df2 = n - Xu.shape[1]
        if df2 <= 0 or rss_u <= 0:
            continue
        F = ((rss_r - rss_u) / df1) / (rss_u / df2)
        p = _f_pvalue(float(F), df1, df2)
        results[f"lag{h}"] = {"F_stat": float(F), "p_value": p, "df1": df1, "df2": df2}

    return results


# ---------------------------------------------------------------------------
# 2. Threshold Granger
# ---------------------------------------------------------------------------

def threshold_granger_test(
    y: np.ndarray,
    x: np.ndarray,
    quantiles: List[float] = [0.60, 0.70, 0.75, 0.80, 0.85, 0.90],
    lag: int = 1,
    n_boot: int = 2000,
    seed: int = 42,
) -> Dict:
    """
    Threshold Granger: x predicts y only in the upper-tail regime.

    Tests H0: beta_threshold = 0 (x has no predictive power above quantile).

    Returns
    -------
    dict keyed by quantile → {beta, t_stat, p_value_boot}
    """
    T = len(y)
    rng = np.random.default_rng(seed)
    results = {}
    best_p = 1.0
    best_q = None

    for q in quantiles:
        threshold = float(np.quantile(x, q))
        Y = y[lag:]
        y_lag = y[:-lag] if lag > 0 else y
        x_lag = x[:-lag] if lag > 0 else x
        n = len(Y)

        above = x_lag > threshold
        regime_n = int(above.sum())
        if regime_n < 5:
            continue

        # Regression: Y = a + b*y_lag + c*(x_lag * I(above)) + eps
        interaction = x_lag * above
        Xmat = np.column_stack([np.ones(n), y_lag[:n], interaction[:n]])
        beta, resid, rss = _ols(Xmat, Y)
        se = np.sqrt(rss / max(n - 3, 1)) / max(np.sqrt(np.sum(interaction[:n] ** 2)), 1e-10)
        t_stat = float(beta[2] / max(se, 1e-10))

        # Bootstrap p-value
        t_boot = np.zeros(n_boot)
        for b in range(n_boot):
            idx = rng.integers(0, n, size=n)
            Y_b = Y[idx]
            Xmat_b = Xmat[idx]
            beta_b, resid_b, rss_b = _ols(Xmat_b, Y_b)
            se_b = np.sqrt(rss_b / max(n - 3, 1)) / max(np.sqrt(np.sum(Xmat_b[:, 2] ** 2)), 1e-10)
            t_boot[b] = beta_b[2] / max(se_b, 1e-10)

        p_boot = float(np.mean(np.abs(t_boot) >= abs(t_stat)))

        results[f"q{int(q*100)}"] = {
            "quantile": q,
            "threshold": threshold,
            "beta_threshold": float(beta[2]),
            "t_stat": t_stat,
            "p_value_boot": p_boot,
            "regime_n": regime_n,
            "regime_frac": regime_n / n,
        }

        if p_boot < best_p:
            best_p = p_boot
            best_q = f"q{int(q*100)}"

    results["best"] = best_q
    results["min_p"] = best_p
    return results


# ---------------------------------------------------------------------------
# 3. Quantile causality
# ---------------------------------------------------------------------------

def quantile_causality_test(
    y: np.ndarray,
    x: np.ndarray,
    taus: List[float] = [0.75, 0.85, 0.90],
    lag: int = 1,
    n_boot: int = 1000,
    seed: int = 42,
) -> Dict:
    """
    Quantile causality: tests if x helps predict the tau-quantile of y.

    Returns
    -------
    dict keyed by tau → {J_stat, p_value}
    """
    T = len(y)
    rng = np.random.default_rng(seed)
    results = {}
    best_p = 1.0
    best_tau = None

    for tau in taus:
        Y = y[lag:]
        x_lag = x[:-lag] if lag > 0 else x
        y_lag = y[:-lag] if lag > 0 else y
        n = len(Y)

        # Quantile regression via iteratively reweighted least squares
        Xmat = np.column_stack([np.ones(n), y_lag[:n], x_lag[:n]])
        beta = np.zeros(Xmat.shape[1])
        for _ in range(50):
            resid = Y - Xmat @ beta
            w = np.where(resid >= 0, tau, 1 - tau) / (np.abs(resid) + 1e-6)
            Xw = Xmat * np.sqrt(w[:, None])
            Yw = Y * np.sqrt(w)
            try:
                beta = np.linalg.solve(Xw.T @ Xw + 1e-8 * np.eye(3), Xw.T @ Yw)
            except np.linalg.LinAlgError:
                break

        # Test statistic: Wald test on beta_x
        resid = Y - Xmat @ beta
        J_stat = float(beta[2] ** 2 / max(np.var(resid), 1e-10) * n)

        # Bootstrap
        J_boot = np.zeros(n_boot)
        for b in range(n_boot):
            idx = rng.integers(0, n, size=n)
            Y_b = Y[idx]
            Xmat_b = Xmat[idx]
            beta_b = np.zeros(3)
            for _ in range(30):
                r = Y_b - Xmat_b @ beta_b
                w = np.where(r >= 0, tau, 1 - tau) / (np.abs(r) + 1e-6)
                Xw = Xmat_b * np.sqrt(w[:, None])
                Yw = Y_b * np.sqrt(w)
                try:
                    beta_b = np.linalg.solve(Xw.T @ Xw + 1e-8 * np.eye(3), Xw.T @ Yw)
                except np.linalg.LinAlgError:
                    break
            r_b = Y_b - Xmat_b @ beta_b
            J_boot[b] = beta_b[2] ** 2 / max(np.var(r_b), 1e-10) * n

        p = float(np.mean(J_boot >= J_stat))

        key = f"tau{int(tau*100)}"
        results[key] = {"tau": tau, "J_stat": J_stat, "p_value": p}
        if p < best_p:
            best_p = p
            best_tau = key

    results["best"] = best_tau
    results["min_p"] = best_p
    return results


# ---------------------------------------------------------------------------
# 4. Exceedance regression
# ---------------------------------------------------------------------------

def exceedance_regression_test(
    y: np.ndarray,
    x: np.ndarray,
    thresholds: Optional[List[float]] = None,
    lag: int = 1,
) -> Dict:
    """
    Exceedance regression: P(y > threshold | x) via logistic-style test.

    Returns
    -------
    dict keyed by percentile → {lr_stat, p_value}
    """
    T = len(y)
    if thresholds is None:
        thresholds = [float(np.percentile(y, p)) for p in [75, 85, 90]]

    results = {}
    for i, thr in enumerate(thresholds):
        pct = [75, 85, 90][i] if i < 3 else int(100 * np.mean(y <= thr))
        Y = (y[lag:] > thr).astype(float)
        x_lag = x[:-lag] if lag > 0 else x
        n = len(Y)
        if Y.sum() < 3 or (n - Y.sum()) < 3:
            continue

        # Restricted (intercept only)
        p0 = Y.mean()
        ll0 = float(np.sum(Y * np.log(p0 + 1e-10) + (1 - Y) * np.log(1 - p0 + 1e-10)))

        # Unrestricted (intercept + x_lag)
        Xmat = np.column_stack([np.ones(n), x_lag[:n]])
        beta = np.zeros(2)
        for _ in range(100):
            z = Xmat @ beta
            p = 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))
            grad = Xmat.T @ (p - Y) / n
            beta -= 0.5 * grad
        z1 = Xmat @ beta
        p1 = 1.0 / (1.0 + np.exp(-np.clip(z1, -500, 500)))
        ll1 = float(np.sum(Y * np.log(p1 + 1e-10) + (1 - Y) * np.log(1 - p1 + 1e-10)))

        lr_stat = 2 * (ll1 - ll0)
        # Chi-squared p-value approximation (df=1)
        p_val = float(np.exp(-lr_stat / 2)) if lr_stat > 0 else 1.0

        results[f"tau{pct}pct"] = {
            "threshold": thr,
            "pct_above": float(Y.mean()),
            "lr_stat": lr_stat,
            "p_value_chi2": p_val,
            "beta_x": float(beta[1]),
        }

    return results


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

def run_all_causality_tests(
    mfls_signal: np.ndarray,
    crisis_labels: np.ndarray,
    dates: pd.DatetimeIndex,
    lags: List[int] = [1, 2, 4],
    n_boot: int = 2000,
    verbose: bool = True,
) -> Dict:
    """
    Run full causality test suite.

    Parameters
    ----------
    mfls_signal : (T,) — MFLS detection signal
    crisis_labels : (T,) — binary crisis labels
    dates : DatetimeIndex
    lags : list of lag orders
    n_boot : int
    verbose : bool

    Returns
    -------
    dict with keys: linear_granger, threshold_granger, quantile_causality,
                    exceedance_reg, summary
    """
    if verbose:
        print("Running causality tests...")

    # Use crisis labels as the dependent variable
    y = crisis_labels.astype(float)
    x = mfls_signal

    results = {}

    # Linear Granger
    lg = linear_granger_test(y, x, max_lag=max(lags))
    results["linear_granger"] = lg
    best_lg_p = min((v["p_value"] for v in lg.values() if isinstance(v, dict)), default=1.0)

    # Threshold Granger
    tg = threshold_granger_test(y, x, lag=1, n_boot=n_boot)
    results["threshold_granger"] = tg

    # Quantile causality
    qc = quantile_causality_test(y, x, lag=1, n_boot=min(n_boot, 1000))
    results["quantile_causality"] = qc

    # Exceedance regression
    er = exceedance_regression_test(y, x, lag=1)
    results["exceedance_reg"] = er

    results["summary"] = {
        "linear_granger_best_p": best_lg_p,
        "threshold_granger_best_p": tg.get("min_p", 1.0),
        "quantile_causality_best_p": qc.get("min_p", 1.0),
    }

    if verbose:
        print(f"  Linear Granger best p:    {best_lg_p:.4f}")
        print(f"  Threshold Granger best p: {tg.get('min_p', 1.0):.4f}")
        print(f"  Quantile causality best p: {qc.get('min_p', 1.0):.4f}")

    return results
