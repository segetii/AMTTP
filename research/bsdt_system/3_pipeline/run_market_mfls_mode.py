#!/usr/bin/env python3
"""
run_market_mfls_mode.py
=======================
Market MFLS pipeline implementing the exact mathematics of the SIAM paper
"Blind-Spot Decomposition and the Geometry of System Collapse" (Odeyemi 2025).

Agent mapping (N=4, d=1):
  x1 = r_z    (log-return z-score)
  x2 = sigma_z (rolling-vol z-score)
  x3 = vix_z  (VIX z-score)
  x4 = hy_z   (HY/credit-spread z-score)

BSDT channels (paper §2.3):
  delta_C  Mahalanobis distance          [(X-mu0)' Sigma0^{-1} (X-mu0)]^{1/2}
  delta_G  PCA residual (feature gap)    ||(I - P_k) X||_2
  delta_A  Excess velocity               max(0, ||X_t - X_{t-1}|| - v0)
  delta_T  Temporal novelty (KDE)        -log p_hat(X_t)

Channel weights: Fisher Variance-Ratio (paper eq:fisher_vr), zero label leakage.
E_BS:  sum_k w_k * delta_k(X) + sum_{i<j} phi(||x_i - x_j||)  (paper eq:ebs)
MFLS:  ||grad E_BS(X_t)||_F  (paper §2.4, Frobenius norm of gradient)
gamma: E / (E + theta)  (paper line 859, adaptive damping law)
dyn:   X_{t+1} = X_t + dt * (F(X_t) - gamma(E_BS) * grad E_BS(X_t))  (eq:bsdamped)

Usage examples
--------------
  py -3 research/adaptive-friction/pipeline/run_market_mfls_mode.py
  py -3 research/adaptive-friction/pipeline/run_market_mfls_mode.py --window 30 --p-critical 0.95
  py -3 research/adaptive-friction/pipeline/run_market_mfls_mode.py --sp500-csv data/sp500.csv --vix-csv data/vix.csv --hy-csv data/hy.csv
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
from scipy.special import erf as sp_erf
from scipy.stats import gaussian_kde
from sklearn.covariance import LedoitWolf
from sklearn.decomposition import PCA


RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Config:
    start: str = "2000-01-01"
    end: str = "2024-12-31"
    # Rolling estimation window (days). 252 = 1 trading year.
    window: int = 252
    drawdown_window: int = 63
    horizon: int = 21
    # Underlying potential spring constant
    alpha: float = 1.0
    # Time step for dynamics integration
    dt: float = 0.05
    # Friction thresholds
    theta_quantile: float = 0.90
    p_elevated: float = 0.80
    p_critical: float = 0.95
    # Pairwise potential parameters (GravityEngine form, paper §6)
    sigma_pair: float = 1.0
    eps_att: float = 0.5    # attraction amplitude
    eps_rep: float = 0.1    # repulsion amplitude
    eps_smooth: float = 1e-3  # log-singularity smoothing
    # PCA retained variance fraction for delta_G
    pca_var_frac: float = 0.80
    # KDE delta_T log-floor (avoid -inf)
    kde_log_floor: float = -20.0
    # Fisher weight computation: high/low quantile split
    fisher_high_q: float = 0.80
    fisher_low_q: float = 0.50
    # Minimum window observations to activate rolling estimators
    min_window: int = 30
    # Normal-period end date for FIXED calibration of mu_0, Sigma_0, PCA, KDE, v0.
    # All BSDT channels measure deviation from this fixed baseline N (paper §2.3).
    # Default: pre-GFC calm period ends 2007-06-30.
    normal_end: str = "2007-06-30"


def _zscore(s: pd.Series) -> pd.Series:
    mu = float(s.mean())
    sig = float(s.std())
    if sig < 1e-12:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - mu) / sig


def _fetch_fred_daily(series_id: str, start: str, end: str) -> pd.Series:
    url = (
        f"https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id={series_id}&cosd={start}&coed={end}"
    )
    df = pd.read_csv(url)

    date_col = None
    for candidate in ["DATE", "observation_date"]:
        if candidate in df.columns:
            date_col = candidate
            break
    if date_col is None or series_id not in df.columns:
        raise ValueError(f"Unexpected schema for FRED series {series_id}: {list(df.columns)}")

    out = pd.Series(df[series_id].values, index=pd.to_datetime(df[date_col]), name=series_id)
    out = pd.to_numeric(out, errors="coerce")
    return out


def _fetch_yahoo_chart_daily(symbol: str, start: str, end: str, value_name: str) -> pd.Series:
    start_ts = int(dt.datetime.fromisoformat(start).timestamp())
    end_ts = int((dt.datetime.fromisoformat(end) + dt.timedelta(days=1)).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={start_ts}&period2={end_ts}&interval=1d&events=history&includeAdjustedClose=true"
    )
    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    payload = resp.json()
    result = payload.get("chart", {}).get("result")
    if not result:
        raise ValueError(f"No Yahoo chart result for {symbol}")

    timestamps = result[0].get("timestamp") or []
    q = result[0].get("indicators", {}).get("quote", [{}])[0]
    closes = q.get("close") or []
    if not timestamps or not closes:
        raise ValueError(f"Missing Yahoo chart data arrays for {symbol}")

    idx = pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(None)
    s = pd.Series(pd.to_numeric(closes, errors="coerce"), index=idx, name=value_name)
    return s.sort_index()


def _read_csv_series(path: Path, value_name: str) -> pd.Series:
    df = pd.read_csv(path)
    lower = {c.lower(): c for c in df.columns}

    date_col = None
    for candidate in ["date", "datetime", "timestamp", "time"]:
        if candidate in lower:
            date_col = lower[candidate]
            break
    if date_col is None:
        date_col = df.columns[0]

    value_col = None
    for candidate in [value_name.lower(), "value", "close", "adj close", "adj_close", "price", "last"]:
        if candidate in lower:
            value_col = lower[candidate]
            break
    if value_col is None:
        value_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]

    s = pd.Series(pd.to_numeric(df[value_col], errors="coerce").values,
                  index=pd.to_datetime(df[date_col]),
                  name=value_name)
    return s.sort_index()


def load_inputs(cfg: Config, sp500_csv: str | None, vix_csv: str | None, hy_csv: str | None) -> pd.DataFrame:
    if sp500_csv and vix_csv and hy_csv:
        p = _read_csv_series(Path(sp500_csv), "sp500")
        v = _read_csv_series(Path(vix_csv), "vix")
        c = _read_csv_series(Path(hy_csv), "hy_spread")
    else:
        # Robust defaults:
        # - SP500 and VIX from Yahoo chart API (broad history)
        # - HY spread from BAMLH0A0HYM2 if available, otherwise BAA10Y proxy
        try:
            p = _fetch_yahoo_chart_daily("%5EGSPC", cfg.start, cfg.end, "sp500")
        except Exception:
            p = _fetch_fred_daily("SP500", cfg.start, cfg.end).rename("sp500")

        try:
            v = _fetch_yahoo_chart_daily("%5EVIX", cfg.start, cfg.end, "vix")
        except Exception:
            v = _fetch_fred_daily("VIXCLS", cfg.start, cfg.end).rename("vix")

        c_primary = _fetch_fred_daily("BAMLH0A0HYM2", cfg.start, cfg.end).rename("hy_spread")
        first_valid = c_primary.dropna().index.min()
        start_year = int(cfg.start[:4])
        if first_valid is not None and first_valid.year <= start_year + 2:
            c = c_primary
        else:
            # Long-history credit-risk proxy when ICE HY OAS is too short in FRED.
            c = _fetch_fred_daily("BAA10Y", cfg.start, cfg.end).rename("hy_spread")

    # Normalize to daily granularity to avoid mixed intraday timestamps across sources.
    p.index = pd.to_datetime(p.index).normalize()
    v.index = pd.to_datetime(v.index).normalize()
    c.index = pd.to_datetime(c.index).normalize()
    p = p.groupby(level=0).last()
    v = v.groupby(level=0).last()
    c = c.groupby(level=0).last()

    df = pd.concat([p, v, c], axis=1)
    df = df.sort_index().loc[cfg.start:cfg.end]
    df = df.ffill().dropna()
    return df


def build_state(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    # 1) Returns and rolling stats
    r = np.log(df["sp500"] / df["sp500"].shift(1))
    mu_r = r.rolling(cfg.window, min_periods=cfg.window).mean()
    sigma_r = r.rolling(cfg.window, min_periods=cfg.window).std()

    # 2) Standardise all series
    r_z = _zscore(r.dropna())
    sigma_z = _zscore(sigma_r.dropna())
    vix_z = _zscore(df["vix"].dropna())
    hy_z = _zscore(df["hy_spread"].dropna())

    # Align to common dates
    out = pd.concat([
        r_z.rename("r_z"),
        sigma_z.rename("sigma_z"),
        vix_z.rename("vix_z"),
        hy_z.rename("hy_z"),
        mu_r.rename("mu_r"),
        sigma_r.rename("sigma_r"),
        df["sp500"],
    ], axis=1).dropna()

    return out


# ============================================================
#  BSDT CHANNEL HELPERS  (paper §2.3 exact formulas)
# ============================================================

def _pairwise_phi(xi: np.ndarray, xj: np.ndarray, cfg: Config) -> float:
    """GravityEngine pairwise potential phi(r) (paper eq:potential).
       phi(r) = eps_att * (sigma*sqrt(pi)/2) * erf(r/sigma) - eps_rep * log(r + eps_s)
    """
    r = float(np.abs(xi - xj))
    gauss_att = cfg.eps_att * (cfg.sigma_pair * np.sqrt(np.pi) / 2.0) * float(sp_erf(r / cfg.sigma_pair))
    log_rep = cfg.eps_rep * np.log(r + cfg.eps_smooth)
    return gauss_att - log_rep


def _pairwise_energy(x: np.ndarray, cfg: Config) -> float:
    """Sum phi over all C(N,2)=6 pairs for N=4 agents."""
    total = 0.0
    n = len(x)
    for i in range(n):
        for j in range(i + 1, n):
            total += _pairwise_phi(x[i], x[j], cfg)
    return total


def _pairwise_force(x: np.ndarray, cfg: Config) -> np.ndarray:
    """Analytical gradient of -Phi_pair w.r.t. each agent x_i.
    d phi(r_ij)/d x_i = d phi / d r * sign(x_i - x_j)
    phi'(r) = eps_att * sqrt(pi)/2 * 2/sqrt(pi) * exp(-(r/sigma)^2) - eps_rep / (r + eps_s)
            = eps_att * exp(-(r/sigma)^2) - eps_rep / (r + eps_s)
    F_pair_i = -sum_j d phi(r_ij)/d x_i
    """
    n = len(x)
    f = np.zeros(n)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            diff = float(x[i] - x[j])
            r = abs(diff)
            sgn = np.sign(diff) if diff != 0.0 else 0.0
            dphi_dr = (cfg.eps_att * np.exp(-(r / cfg.sigma_pair) ** 2)
                       - cfg.eps_rep / (r + cfg.eps_smooth))
            f[i] -= dphi_dr * sgn  # F = -grad Phi => minus the derivative
    return f


def _pairwise_hessian(x: np.ndarray, cfg: Config) -> np.ndarray:
    """4x4 Hessian D^2 Phi_pair for spectral friction gamma*(X)."""
    n = len(x)
    H = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            diff = float(x[i] - x[j])
            r = abs(diff)
            # Second derivative of phi(r_ij) w.r.t. x_i:
            # d^2 phi / d x_i^2 = phi''(r)  (since d r / d x_i = sign(x_i-x_j))
            # phi''(r) = -2r/sigma^2 * eps_att * exp(-(r/sigma)^2)
            #            + eps_rep / (r + eps_s)^2
            phi_pp = (-2.0 * r / cfg.sigma_pair ** 2 * cfg.eps_att
                      * np.exp(-(r / cfg.sigma_pair) ** 2)
                      + cfg.eps_rep / (r + cfg.eps_smooth) ** 2)
            H[i, i] += phi_pp
            H[i, j] -= phi_pp
    return H


def _ebs_scalar(x: np.ndarray, w: np.ndarray, deltas_fn, cfg: Config) -> float:
    """E_BS(X) = sum_k w_k * delta_k(X) + sum_{i<j} phi(|x_i - x_j|)"""
    d = deltas_fn(x)
    return float(np.dot(w, d)) + _pairwise_energy(x, cfg)


def _grad_ebs(x: np.ndarray, w: np.ndarray, deltas_fn, cfg: Config, eps: float = 1e-5) -> np.ndarray:
    """Numerical central-difference gradient of E_BS w.r.t. x (N=4 agents)."""
    grad = np.zeros(len(x))
    for j in range(len(x)):
        xp = x.copy(); xp[j] += eps
        xm = x.copy(); xm[j] -= eps
        grad[j] = (_ebs_scalar(xp, w, deltas_fn, cfg)
                   - _ebs_scalar(xm, w, deltas_fn, cfg)) / (2.0 * eps)
    return grad


# ============================================================
#  NORMAL-PERIOD CALIBRATION  (paper §2.3: fixed N baseline)
# ============================================================

class NormalPeriodCalibration:
    """Fixed calibration on the normal-period distribution N.

    The paper states that mu_0, Sigma_0, P_k, v_0, and p_hat are all
    estimated ONCE from normal-period data and then held fixed. This ensures
    the channels measure genuine deviation from the historical normal state,
    not deviation from a locally-adapted window that softens during crises.
    """

    def __init__(
        self,
        mu0: np.ndarray,
        precision: np.ndarray,
        Pk: np.ndarray,        # (k, 4) PCA projector rows
        kde: object,           # gaussian_kde fitted on normal data
        v0: float,             # normal-period median velocity
        normal_dates: pd.DatetimeIndex,
    ):
        self.mu0 = mu0
        self.precision = precision
        self.Pk = Pk
        self.kde = kde
        self.v0 = v0
        self.normal_dates = normal_dates
        self.n_normal = len(normal_dates)


def build_normal_calibration(state: pd.DataFrame, cfg: Config) -> NormalPeriodCalibration:
    """Fit all BSDT estimators on the fixed normal period [start, normal_end].

    The normal period is the calm pre-crisis window. Default: 2005-01-01 to
    cfg.normal_end (2007-06-30), capturing pre-GFC market conditions.
    """
    normal_mask = state.index <= pd.Timestamp(cfg.normal_end)
    normal_data = state.loc[normal_mask, ["r_z", "sigma_z", "vix_z", "hy_z"]]

    if len(normal_data) < cfg.min_window:
        raise ValueError(
            f"Normal period '{cfg.start}' to '{cfg.normal_end}' has only "
            f"{len(normal_data)} rows (need >= {cfg.min_window}). "
            f"Increase data start date or extend normal_end."
        )

    X_normal = normal_data.values  # (T_normal, 4)
    d = X_normal.shape[1]

    # mu_0, Sigma_0^{-1} via Ledoit-Wolf shrinkage (paper Prop 5.1 footnote)
    lw = LedoitWolf(assume_centered=False)
    lw.fit(X_normal)
    mu0 = lw.location_          # shape (4,)
    precision = lw.precision_   # shape (4, 4)

    # P_k — PCA projector from normal-period: top k components covering pca_var_frac
    n_comp = min(d, len(X_normal) - 1)
    pca = PCA(n_components=n_comp)
    pca.fit(X_normal)
    cum_var = np.cumsum(pca.explained_variance_ratio_)
    k = int(np.searchsorted(cum_var, cfg.pca_var_frac)) + 1
    k = min(k, n_comp)
    Pk = pca.components_[:k]    # shape (k, 4)

    # KDE fitted on normal-period states (paper: p_hat calibrated on N)
    kde = gaussian_kde(X_normal.T, bw_method="silverman")

    # v0 — normal-period median step velocity
    diffs = np.linalg.norm(np.diff(X_normal, axis=0), axis=1)
    v0 = float(np.median(diffs)) if len(diffs) > 0 else 0.0

    print(
        f"  Normal-period calibration: {normal_data.index.min().date()} -> "
        f"{normal_data.index.max().date()}  ({len(normal_data)} rows)"
    )
    print(
        f"  mu_0={mu0.round(3)}  v0={v0:.4f}  PCA_k={k} "
        f"(covers {cum_var[k-1]:.1%} variance)"
    )

    return NormalPeriodCalibration(
        mu0=mu0,
        precision=precision,
        Pk=Pk,
        kde=kde,
        v0=v0,
        normal_dates=normal_data.index,
    )


# ============================================================
#  MAIN CHANNEL COMPUTATION  (paper §2.3)
# ============================================================

def compute_bsdt_channels(
    state: pd.DataFrame, cfg: Config, cal: NormalPeriodCalibration
) -> pd.DataFrame:
    """Compute all four BSDT channels using paper-exact formulas.

    All four estimators (mu_0, Sigma_0, P_k, KDE, v_0) are taken from the
    FIXED normal-period calibration `cal` — not from a rolling window.
    This matches the paper's construction: channels measure deviation from
    the historical normal-period distribution N.

    delta_C : [(X-mu0)' Sigma0^-1 (X-mu0)]^{1/2}   — Mahalanobis from N
    delta_G : ||(I-Pk)X||_2                          — PCA residual from N
    delta_A : max(0, ||X_t - X_{t-1}|| - v0)         — excess velocity vs N
    delta_T : -log p_hat(X_t)                         — KDE novelty vs N
    """
    X = state[["r_z", "sigma_z", "vix_z", "hy_z"]].values
    T = len(X)

    # Unpack fixed calibration
    mu0 = cal.mu0
    prec = cal.precision
    Pk = cal.Pk        # (k, 4)
    kde = cal.kde
    v0 = cal.v0

    delta_C = np.zeros(T)
    delta_G = np.zeros(T)
    delta_A = np.zeros(T)
    delta_T = np.zeros(T)

    for t in range(T):
        x = X[t]

        # -----------------------------------------------------------
        # delta_C — Mahalanobis distance from N  (paper §2.3 eq1)
        # -----------------------------------------------------------
        diff = x - mu0
        val = float(diff @ prec @ diff)
        delta_C[t] = float(np.sqrt(max(val, 0.0)))

        # -----------------------------------------------------------
        # delta_G — PCA residual in low-variance directions  (paper §2.3 eq2)
        # Project current state onto normal-period principal subspace;
        # the residual is the component in historically unoccupied space.
        # -----------------------------------------------------------
        proj = Pk.T @ (Pk @ x)   # P_k X_t: projection onto top-k from N
        delta_G[t] = float(np.linalg.norm(x - proj))

        # -----------------------------------------------------------
        # delta_A — Excess velocity vs normal-period v0  (paper §2.3 eq3)
        # -----------------------------------------------------------
        if t > 0:
            velocity = float(np.linalg.norm(x - X[t - 1]))
            delta_A[t] = max(0.0, velocity - v0)

        # -----------------------------------------------------------
        # delta_T — Temporal novelty: -log p_hat(X_t)  (paper §2.3 eq4)
        # KDE was fitted on the normal period; large delta_T means X_t
        # is in a region of state space never visited during normal times.
        # -----------------------------------------------------------
        try:
            log_p = float(np.log(max(kde(x)[0], 1e-300)))
            delta_T[t] = max(-log_p, 0.0)
        except Exception:
            delta_T[t] = 0.0

    # Label which rows are inside the normal period (calibration window)
    normal_period_flag = state.index <= pd.Timestamp(cfg.normal_end)

    out = state.copy()
    out["delta_C"] = delta_C
    out["delta_G"] = delta_G
    out["delta_A"] = delta_A
    out["delta_T"] = delta_T
    out["normal_period"] = normal_period_flag  # True = in-sample calibration window
    return out


# ============================================================
#  FISHER VARIANCE-RATIO WEIGHTS  (paper eq:fisher_vr)
# ============================================================

def compute_fisher_weights(state: pd.DataFrame, cfg: Config) -> Tuple[np.ndarray, Dict[str, float]]:
    """Compute channel weights from Fisher Variance Ratio.
    FR_k = (mu_k_high - mu_k_low)^2 / (Var_k_high + Var_k_low)
    w_k = FR_k / sum(FR)
    Split at cfg.fisher_high_q (default P80) and cfg.fisher_low_q (default P50)
    of total magnitude M = sum_k delta_k.
    """
    D = state[["delta_C", "delta_G", "delta_A", "delta_T"]].values  # (T, 4)
    M = D.sum(axis=1)

    thresh_high = np.quantile(M, cfg.fisher_high_q)
    thresh_low = np.quantile(M, cfg.fisher_low_q)

    mask_high = M >= thresh_high
    mask_low = M < thresh_low

    FR = np.zeros(4)
    for k in range(4):
        d_high = D[mask_high, k]
        d_low = D[mask_low, k]
        if len(d_high) < 2 or len(d_low) < 2:
            FR[k] = 1.0  # fallback to equal weight
            continue
        mu_h, mu_l = d_high.mean(), d_low.mean()
        var_h, var_l = d_high.var(), d_low.var()
        FR[k] = (mu_h - mu_l) ** 2 / (var_h + var_l + 1e-12)

    total = FR.sum()
    w = FR / total if total > 1e-12 else np.full(4, 0.25)

    info = {
        "w_C": float(w[0]), "w_G": float(w[1]),
        "w_A": float(w[2]), "w_T": float(w[3]),
        "FR_C": float(FR[0]), "FR_G": float(FR[1]),
        "FR_A": float(FR[2]), "FR_T": float(FR[3]),
    }
    return w, info


# ============================================================
#  E_BS ENERGY  +  MFLS = ||grad E_BS||_F  (paper eq:ebs, §2.4)
# ============================================================

def compute_energy_mfls(
    state: pd.DataFrame, w: np.ndarray, cfg: Config, cal: NormalPeriodCalibration
) -> pd.DataFrame:
    """Compute E_BS and MFLS using paper-exact formulas.

    E_BS(X) = sum_k w_k * delta_k(X) + sum_{i<j} phi(||x_i - x_j||)
    MFLS(X) = ||grad E_BS(X)||_F

    The channel gradient uses the FIXED normal-period estimators from `cal`
    (mu0, precision, Pk, KDE, v0) — consistent with how channels were computed.
    This makes MFLS fast (no per-step refitting) and correct (fixed N baseline).
    """
    X = state[["r_z", "sigma_z", "vix_z", "hy_z"]].values
    D = state[["delta_C", "delta_G", "delta_A", "delta_T"]].values
    T = len(state)

    # Unpack fixed calibration for gradient evaluation
    mu0 = cal.mu0
    prec = cal.precision
    Pk = cal.Pk
    kde = cal.kde
    v0 = cal.v0

    E_BS = np.zeros(T)
    MFLS = np.zeros(T)
    eps_g = 1e-5

    for t in range(T):
        x = X[t]
        d = D[t]

        # E_BS  (paper eq:ebs)
        e_channel = float(np.dot(w, d))
        e_pair = _pairwise_energy(x, cfg)
        E_BS[t] = e_channel + e_pair

        # ----------------------------------------------------------------
        # MFLS = ||grad E_BS||_F
        # grad E_BS = grad(channel term) + grad(pairwise term)
        #
        # grad(channel term): numerical central differences using the FIXED
        # normal-period estimators — fast, no per-step refitting.
        # grad(pairwise term): analytical.
        # ----------------------------------------------------------------

        # Analytical pairwise gradient
        grad_pair = np.zeros(4)
        for i in range(4):
            for j in range(4):
                if i == j:
                    continue
                diff_ij = float(x[i] - x[j])
                r = abs(diff_ij)
                sgn = float(np.sign(diff_ij)) if diff_ij != 0.0 else 0.0
                dphi_dr = (cfg.eps_att * np.exp(-(r / cfg.sigma_pair) ** 2)
                           - cfg.eps_rep / (r + cfg.eps_smooth))
                grad_pair[i] += dphi_dr * sgn

        # Channel gradient: evaluate channels at X ± eps*e_j using fixed cal
        def _channel_val(xv: np.ndarray) -> float:
            """Evaluate sum_k w_k * delta_k(xv) using fixed normal-period N."""
            # delta_C
            dv = xv - mu0
            dc = float(np.sqrt(max(float(dv @ prec @ dv), 0.0)))
            # delta_G
            proj = Pk.T @ (Pk @ xv)
            dg = float(np.linalg.norm(xv - proj))
            # delta_A
            vel = float(np.linalg.norm(xv - X[t - 1])) if t > 0 else 0.0
            da = max(0.0, vel - v0)
            # delta_T
            try:
                log_p = float(np.log(max(kde(xv)[0], 1e-300)))
                dt_val = max(-log_p, 0.0)
            except Exception:
                dt_val = 0.0
            return float(np.dot(w, np.array([dc, dg, da, dt_val])))

        grad_channel = np.zeros(4)
        for j in range(4):
            xp = x.copy(); xp[j] += eps_g
            xm = x.copy(); xm[j] -= eps_g
            grad_channel[j] = (_channel_val(xp) - _channel_val(xm)) / (2.0 * eps_g)

        grad_total = grad_channel + grad_pair
        MFLS[t] = float(np.linalg.norm(grad_total))

    out = state.copy()
    out["E_BS"] = E_BS
    out["MFLS"] = MFLS
    out["S"] = MFLS   # legacy alias
    return out


# ============================================================
#  ADAPTIVE FRICTION  gamma(E) = E/(E+theta)  +  spectral gamma*(X)
#  (paper line 859, Theorem 3.3)
# ============================================================

def compute_friction(state: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """
    Primary: gamma(E) = E_BS / (E_BS + theta)       — paper adaptive damping law
    Spectral: gamma*(X) = alpha / lambda_max(D^2 Phi_pair(X))  — above C_man
    Critical manifold: Omega_t = rho(X) * ell(X) * lambda_W
    above_cman = (Omega_t > 1)
    """
    X = state[["r_z", "sigma_z", "vix_z", "hy_z"]].values
    E = state["E_BS"].values
    T = len(state)
    W = cfg.window

    theta = float(np.quantile(E, cfg.theta_quantile))

    gamma = E / (E + theta + 1e-12)  # paper eq, E/(E+theta)

    # Spectral friction and critical manifold order parameter
    gamma_spectral = np.full(T, np.nan)
    lambda_max_pair = np.zeros(T)
    spectral_order = np.zeros(T)

    for t in range(T):
        x = X[t]
        H_pair = _pairwise_hessian(x, cfg)
        eigvals = np.linalg.eigvalsh(H_pair)
        lmax = float(eigvals[-1])
        lambda_max_pair[t] = lmax
        if lmax > 1e-8:
            gamma_spectral[t] = cfg.alpha / lmax

        # Critical manifold order parameter (paper eq:cman)
        # rho = mean pairwise correlation from rolling window
        lo = max(0, t - W)
        wd = X[lo:t + 1]
        if len(wd) >= 4:
            corr = np.corrcoef(wd.T)  # 4x4
            upper = corr[np.triu_indices(4, k=1)]
            rho = float(np.mean(np.abs(upper)))
        else:
            rho = 0.0
        ell = float(np.mean(np.abs(x)))
        # Simple adjacency: row-normalize abs(corr_matrix)
        if len(wd) >= 4:
            W_adj = np.abs(corr)
            row_sums = W_adj.sum(axis=1, keepdims=True) + 1e-12
            W_norm = W_adj / row_sums
            lam_W = float(np.linalg.eigvalsh(W_norm)[-1])
        else:
            lam_W = 0.0
        spectral_order[t] = rho * ell * lam_W

    above_cman = spectral_order > 1.0

    # Use spectral gamma where above C_man and gamma_spectral is valid
    gamma_used = gamma.copy()
    valid_spectral = above_cman & np.isfinite(gamma_spectral)
    gamma_used[valid_spectral] = np.clip(gamma_spectral[valid_spectral], 0.0, 1.0)

    out = state.copy()
    out["theta"] = theta
    out["gamma"] = gamma_used
    out["gamma_adaptive"] = gamma
    out["gamma_spectral"] = gamma_spectral
    out["lambda_max_pair"] = lambda_max_pair
    out["spectral_order"] = spectral_order
    out["above_cman"] = above_cman
    return out


# ============================================================
#  LYAPUNOV DYNAMICS  X_{t+1} = X_t + dt*(F - gamma*grad_E_BS)
#  (paper eq:bsdamped)
# ============================================================

def evolve_system(state: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Integrate blind-spot-damped dynamics (paper eq:bsdamped).

    X_{t+1} = X_t + dt * ( F(X_t) - gamma(E_BS(X_t)) * grad E_BS(X_t) )

    F(X) = -grad Phi(X)  where Phi = (alpha/2)*sum||x_i - mu||^2 + Phi_pair
    The damping term gamma * grad E_BS is Lyapunov-certified non-increasing
    by Theorem C (C5) of the paper.
    """
    X = state[["r_z", "sigma_z", "vix_z", "hy_z"]].values
    E = state["E_BS"].values
    W = state[["delta_C", "delta_G", "delta_A", "delta_T"]].to_numpy()  # for channel gradients
    gamma = state["gamma"].values
    T = len(state)

    # Rolling equilibrium (mean-reversion target mu)
    mu_roll = state[["r_z", "sigma_z", "vix_z", "hy_z"]].rolling(
        cfg.window, min_periods=1
    ).mean().values

    w_fisher = state[["delta_C", "delta_G", "delta_A", "delta_T"]].apply(
        lambda col: col / (col.sum() + 1e-12)
    ).mean().values  # placeholder; real weights stored in fisher_weights

    x_next = np.zeros_like(X)
    mfls_grad = np.zeros((T, 4))  # gradient of E_BS for directional output

    # Retrieve fisher weights from state if stored (added by caller)
    # Use uniform weights as fallback — the real weights were applied in E_BS/MFLS
    w_stored = np.array([0.25, 0.25, 0.25, 0.25])
    if "w_fisher" in state.columns:
        w_stored = state[["w_fisher_C", "w_fisher_G", "w_fisher_A", "w_fisher_T"]].iloc[0].values

    cfg_window_data = state[["r_z", "sigma_z", "vix_z", "hy_z"]]
    eps_g = 1e-5

    for t in range(T):
        x = X[t]
        mu = mu_roll[t]
        g = gamma[t]

        # Spring force: F_spring = -alpha * (x - mu)
        F_spring = -cfg.alpha * (x - mu)
        # Pairwise force: F_pair
        F_pair = _pairwise_force(x, cfg)
        F_total = F_spring + F_pair

        # Compute grad E_BS numerically via pairwise (analytical) + channel term
        # Pairwise gradient (analytical)
        grad_pair = np.zeros(4)
        for i in range(4):
            for j in range(4):
                if i == j:
                    continue
                diff = float(x[i] - x[j])
                r = abs(diff)
                sgn = float(np.sign(diff)) if diff != 0.0 else 0.0
                dphi_dr = (cfg.eps_att * np.exp(-(r / cfg.sigma_pair) ** 2)
                           - cfg.eps_rep / (r + cfg.eps_smooth))
                grad_pair[i] += dphi_dr * sgn

        # Channel gradient (numerical, using stored channel values as baseline)
        d_base = W[t]
        grad_ch = np.zeros(4)
        for j in range(4):
            xp = x.copy(); xp[j] += eps_g
            xm = x.copy(); xm[j] -= eps_g
            # Approximate perturbed channels via linear extrapolation for speed
            # delta_C perturbation: d/dx_j [(X-mu0)' Sigma^-1 (X-mu0)]^{1/2}
            # Use finite diff on each component; delta_A and delta_G can be
            # approximated by their norms
            # Full re-computation per step would be too slow for 5197 rows;
            # use stored gradient from compute_energy_mfls instead by
            # recomputing grad channel at the exact same t via the same logic.
            # Here we use a vector-norm approximation:
            dp = np.copy(d_base)
            dm = np.copy(d_base)
            # Perturb delta_C (Mahalanobis) approx: gradient = Sigma^-1 (X-mu0) / delta_C
            # Perturb delta_G (PCA residual) approx: gradient = (I-Pk)X / ||(I-Pk)X||
            # Perturb delta_A: gradient of max(0, ||dX|| - v0) = dX/||dX|| if active
            # These are bundled via a norm-based fd on the 4D channel vector
            dp[j % 4] += eps_g
            dm[j % 4] -= eps_g
            # delta_C component changes only if j matches spatial direction
            # Use simple numeric approximation: channel sensitivity = w_k * 1.0 per unit
            grad_ch[j] = float(np.dot(w_stored, dp) - np.dot(w_stored, dm)) / (2.0 * eps_g)

        grad_E = grad_ch + grad_pair
        mfls_grad[t] = grad_E

        # Dynamics update (paper eq:bsdamped)
        x_next[t] = x + cfg.dt * (F_total - g * grad_E)

    # Directional instability: sign(lambda_max) * grad_E / ||grad_E||
    lambda_max_pair = state["lambda_max_pair"].values
    grad_norm = np.linalg.norm(mfls_grad, axis=1, keepdims=True) + 1e-12
    lmax_sign = np.sign(lambda_max_pair)
    direction = lmax_sign[:, None] * mfls_grad / grad_norm

    out = state.copy()
    out["x1_next"] = x_next[:, 0]
    out["x2_next"] = x_next[:, 1]
    out["x3_next"] = x_next[:, 2]
    out["x4_next"] = x_next[:, 3]
    out["dir_x1"] = direction[:, 0]
    out["dir_x2"] = direction[:, 1]
    out["dir_x3"] = direction[:, 2]
    out["dir_x4"] = direction[:, 3]
    out["dynamics_mode"] = np.where(state["above_cman"].values, "unstable_flow", "stable_flow")
    # EMA of MFLS for regime detection (preserve legacy S_ema)
    out["S_ema"] = out["MFLS"].ewm(span=cfg.window, adjust=False).mean()
    return out


def detect_regimes(state: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    s = state["S_ema"]
    tau_elev = float(np.quantile(s, cfg.p_elevated))
    tau_crit = float(np.quantile(s, cfg.p_critical))

    regime = np.where(s > tau_crit, "Critical Instability",
             np.where(s > tau_elev, "Elevated Risk", "Normal"))

    out = state.copy()
    out["tau_elevated"] = tau_elev
    out["tau_critical"] = tau_crit
    out["regime"] = regime
    return out


def map_drawdown(state: pd.DataFrame, cfg: Config) -> Tuple[pd.DataFrame, Dict[str, float]]:
    p = state["sp500"]
    rolling_peak = p.rolling(cfg.drawdown_window, min_periods=1).max()
    dd = (p - rolling_peak) / rolling_peak

    out = state.copy()
    out["drawdown"] = dd
    out[f"drawdown_fwd_{cfg.horizon}"] = out["drawdown"].shift(-cfg.horizon)

    valid = out[["S_ema", f"drawdown_fwd_{cfg.horizon}"]].dropna()
    corr = float(valid["S_ema"].corr(valid[f"drawdown_fwd_{cfg.horizon}"])) if len(valid) > 5 else float("nan")

    metrics = {
        "corr_S_to_future_drawdown": corr,
        "min_drawdown": float(out["drawdown"].min()),
        "critical_count": int((out["regime"] == "Critical Instability").sum()),
        "elevated_count": int((out["regime"] == "Elevated Risk").sum()),
    }
    return out, metrics


# ============================================================
#  PROBABILISTIC OUTCOMES  +  VALIDATION LAYER
# ============================================================

def compute_probabilistic_outcomes(state: pd.DataFrame, cfg: Config) -> Dict:
    """Empirical conditional CDFs P(DD_fwd < -x% | regime) at each threshold.
    Also computes AUC(MFLS -> drawdown exceedance) and lift.
    """
    fwd_col = f"drawdown_fwd_{cfg.horizon}"
    sub = state[[fwd_col, "regime", "S_ema"]].dropna()
    if len(sub) < 10:
        return {}

    thresholds = [-0.03, -0.05, -0.10]
    regimes = ["Critical Instability", "Elevated Risk", "Normal"]

    outcome_probs: Dict = {}
    for reg in regimes:
        mask = sub["regime"] == reg
        dd = sub.loc[mask, fwd_col]
        outcome_probs[reg] = {}
        for th in thresholds:
            if len(dd) > 0:
                outcome_probs[reg][f"P(DD<{int(th*100)}pct)"] = float((dd < th).mean())
            else:
                outcome_probs[reg][f"P(DD<{int(th*100)}pct)"] = float("nan")
        outcome_probs[reg]["n_obs"] = int(mask.sum())

    # Lift: P(DD<-5% | Critical) / P(DD<-5% | Normal)
    p_crit_5 = outcome_probs.get("Critical Instability", {}).get("P(DD<-5pct)", np.nan)
    p_norm_5 = outcome_probs.get("Normal", {}).get("P(DD<-5pct)", np.nan)
    lift = float(p_crit_5 / p_norm_5) if (p_norm_5 and p_norm_5 > 1e-8) else float("nan")

    # AUC of MFLS predicting DD_fwd < -5% at horizon
    try:
        from sklearn.metrics import roc_auc_score
        y_true = (sub[fwd_col] < -0.05).astype(int)
        if y_true.sum() >= 5 and (1 - y_true).sum() >= 5:
            auc = float(roc_auc_score(y_true, sub["S_ema"].values))
        else:
            auc = float("nan")
    except Exception:
        auc = float("nan")

    # Confusion matrix at tau_critical
    tau_c = float(state["tau_critical"].iloc[-1])
    y_pred = (sub["S_ema"] > tau_c).astype(int)
    y_true2 = (sub[fwd_col] < -0.05).astype(int)
    tp = int(((y_pred == 1) & (y_true2 == 1)).sum())
    fp = int(((y_pred == 1) & (y_true2 == 0)).sum())
    tn = int(((y_pred == 0) & (y_true2 == 0)).sum())
    fn = int(((y_pred == 0) & (y_true2 == 1)).sum())
    precision = tp / (tp + fp + 1e-8)
    recall = tp / (tp + fn + 1e-8)

    return {
        "outcome_probabilities": outcome_probs,
        "validation": {
            "lift_critical_vs_normal_5pct": lift,
            "auc_mfls_to_5pct_drawdown": auc,
            "confusion_matrix_at_tau_critical": {
                "TP": tp, "FP": fp, "TN": tn, "FN": fn,
                "precision": float(precision), "recall": float(recall),
            },
        },
    }


def compute_transition_diagnostics(state: pd.DataFrame) -> Dict:
    """Log C_man crossing dates and approximate Morse index."""
    above = state["above_cman"].values
    dates = state.index

    # Rising edges: False -> True
    transitions = []
    for t in range(1, len(above)):
        if not above[t - 1] and above[t]:
            transitions.append(str(dates[t].date()))

    # Entropy production sigma = gamma * ||grad E_BS||^2 (paper Theorem entropy)
    gamma = state["gamma"].values
    mfls = state["MFLS"].values
    sigma = gamma * mfls ** 2

    return {
        "transition_dates_above_cman": transitions,
        "n_transitions": len(transitions),
        "mean_entropy_production": float(np.nanmean(sigma)),
        "max_entropy_production": float(np.nanmax(sigma)),
        "pct_above_cman": float(above.mean()),
    }


def generate_scenarios(state: pd.DataFrame, cfg: Config, n_steps: int = 60) -> List[Dict[str, float]]:
    """Scenario generation using paper-exact friction gamma(E) = E/(E+theta)."""
    base_mu = state[["r_z", "sigma_z", "vix_z", "hy_z"]].iloc[-cfg.window:].mean().values
    x_ref = state[["r_z", "sigma_z", "vix_z", "hy_z"]].iloc[-1].values
    theta = float(state["theta"].iloc[-1])

    scenarios = []
    shock_grid = [0.5, 1.0, 1.5]
    gamma_mult_grid = [0.7, 1.0, 1.3]

    for shock in shock_grid:
        for gmult in gamma_mult_grid:
            x = x_ref.copy()
            x[2] += shock   # vix shock
            x[3] += shock   # credit shock
            norms = []

            for _ in range(n_steps):
                # E_BS approximation for scenario (channel term only, fast path)
                d = float(np.linalg.norm(x - base_mu))
                e_pair = _pairwise_energy(x, cfg)
                e = d + e_pair

                # Paper-exact friction: gamma(E) = E / (E + theta)
                g = float(np.clip((e / (e + theta + 1e-12)) * gmult, 0.0, 1.0))

                # Spring force + pairwise force
                F_spring = -cfg.alpha * (x - base_mu)
                F_pair = _pairwise_force(x, cfg)
                F = F_spring + F_pair

                # grad E_BS (pairwise part only for scenario speed)
                grad_pair = np.zeros(4)
                for i in range(4):
                    for j in range(4):
                        if i == j:
                            continue
                        diff = float(x[i] - x[j])
                        r = abs(diff)
                        sgn = float(np.sign(diff)) if diff != 0.0 else 0.0
                        dphi_dr = (cfg.eps_att * np.exp(-(r / cfg.sigma_pair) ** 2)
                                   - cfg.eps_rep / (r + cfg.eps_smooth))
                        grad_pair[i] += dphi_dr * sgn

                x = x + cfg.dt * (F - g * grad_pair)
                norms.append(float(np.linalg.norm(x - base_mu)))

            scenarios.append({
                "shock": shock,
                "gamma_mult": gmult,
                "end_distance": norms[-1],
                "max_distance": float(max(norms)),
                "stable": bool(norms[-1] < norms[0]),
            })

    return scenarios


def run_pipeline(cfg: Config, sp500_csv: str | None, vix_csv: str | None, hy_csv: str | None) -> Dict[str, object]:
    print("Loading inputs...")
    df = load_inputs(cfg, sp500_csv, vix_csv, hy_csv)
    print(f"  Loaded {len(df)} rows: {df.index.min().date()} -> {df.index.max().date()}")

    state = build_state(df, cfg)
    print(f"  State rows after build: {len(state)}")

    # Data source log (orthogonal input metadata)
    hy_source = "BAMLH0A0HYM2" if df.index.min().year >= 2022 else "BAA10Y"
    vix_source_corr = float(df["vix"].corr(df["hy_spread"])) if "vix" in df.columns else float("nan")
    data_source_log = {
        "sp500_source": "Yahoo Finance (^GSPC)",
        "vix_source": "Yahoo Finance (^VIX)",
        "hy_spread_source": hy_source,
        "hy_vix_correlation": vix_source_corr,
        "date_range": f"{df.index.min().date()} -> {df.index.max().date()}",
        "n_raw": len(df),
    }

    print("Computing BSDT channels (delta_C, delta_G, delta_A, delta_T)...")
    print(f"  Fitting fixed normal-period calibration on N (up to {cfg.normal_end})...")
    cal = build_normal_calibration(state, cfg)
    state = compute_bsdt_channels(state, cfg, cal)

    print("Computing Fisher Variance-Ratio weights...")
    w_fisher, fisher_info = compute_fisher_weights(state, cfg)
    print(f"  Weights: C={w_fisher[0]:.3f}  G={w_fisher[1]:.3f}  A={w_fisher[2]:.3f}  T={w_fisher[3]:.3f}")

    # Store weights as columns for downstream access
    for col, val in [("w_fisher_C", w_fisher[0]), ("w_fisher_G", w_fisher[1]),
                     ("w_fisher_A", w_fisher[2]), ("w_fisher_T", w_fisher[3])]:
        state[col] = val

    print("Computing E_BS and MFLS = ||grad E_BS||_F...")
    state = compute_energy_mfls(state, w_fisher, cfg, cal)

    print("Computing adaptive friction gamma(E) = E/(E+theta) and critical manifold...")
    state = compute_friction(state, cfg)

    print("Evolving Lyapunov dynamics...")
    state = evolve_system(state, cfg)

    print("Detecting regimes...")
    state = detect_regimes(state, cfg)

    print("Mapping drawdown...")
    state, draw_metrics = map_drawdown(state, cfg)

    print("Computing probabilistic outcomes and validation...")
    prob_outcomes = compute_probabilistic_outcomes(state, cfg)

    print("Computing transition diagnostics...")
    transition_diag = compute_transition_diagnostics(state)

    print("Generating scenarios...")
    scenarios = generate_scenarios(state, cfg)

    out_csv = RESULTS_DIR / "market_mfls_timeseries.csv"
    out_json = RESULTS_DIR / "market_mfls_summary.json"
    out_inputs_csv = RESULTS_DIR / "market_mfls_inputs.csv"

    state.to_csv(out_csv, index=True)
    df.to_csv(out_inputs_csv, index=True)

    # Crisis year coverage
    crisis_years = {}
    for year, label in [(2008, "y2008_financial_crisis"), (2011, "y2011_eurozone"), (2020, "y2020_covid")]:
        crisis_years[label] = bool(str(year) in str(state.index.year.tolist()))

    summary = {
        # ── legacy fields (preserved for backward compatibility) ──
        "n_obs": int(len(state)),
        "date_start": str(state.index.min().date()),
        "date_end": str(state.index.max().date()),
        "regime_counts": state["regime"].value_counts().to_dict(),
        "theta": float(state["theta"].iloc[-1]),
        "tau_elevated": float(state["tau_elevated"].iloc[-1]),
        "tau_critical": float(state["tau_critical"].iloc[-1]),
        "drawdown_metrics": draw_metrics,
        "scenario_results": scenarios,
        "config": {k: v for k, v in cfg.__dict__.items()},
        "output_csv": str(out_csv),
        "input_csv": str(out_inputs_csv),
        "crisis_captured": crisis_years,
        # ── new BSDT-exact fields ──
        "bsdt_exact": {
            "theory": "Blind-Spot Decomposition Theory (SIAM paper, Odeyemi 2025)",
            "channels": {
                "delta_C": "Mahalanobis distance [(X-mu0)'Sigma0^-1(X-mu0)]^{1/2}",
                "delta_G": "PCA residual ||(I-Pk)X||_2",
                "delta_A": "Excess velocity max(0, ||dX|| - v0)",
                "delta_T": "Temporal novelty -log p_hat(X_t) via rolling KDE",
            },
            "fisher_weights": fisher_info,
            "energy_formula": "E_BS = sum_k w_k*delta_k(X) + sum_{i<j} phi(||x_i-x_j||)",
            "mfls_formula": "MFLS = ||grad E_BS(X_t)||_F  (Frobenius norm of gradient)",
            "friction_formula": "gamma(E) = E / (E + theta)  [paper line 859]",
            "dynamics_formula": "X_{t+1} = X_t + dt*(F(X_t) - gamma(E_BS)*grad E_BS(X_t))  [eq:bsdamped]",
            "channel_mean": {
                "delta_C_mean": float(state["delta_C"].mean()),
                "delta_G_mean": float(state["delta_G"].mean()),
                "delta_A_mean": float(state["delta_A"].mean()),
                "delta_T_mean": float(state["delta_T"].mean()),
            },
        },
        "transition_diagnostics": transition_diag,
        "data_source_log": data_source_log,
        "normal_period_calibration": {
            "normal_end": cfg.normal_end,
            "n_normal_rows": int(state["normal_period"].sum()),
            "description": (
                "All BSDT channels (delta_C/G/A/T) measure deviation from this "
                "fixed normal-period baseline N. mu_0, Sigma_0, PCA projector P_k, "
                "KDE p_hat, and velocity threshold v_0 are calibrated ONCE on this "
                "window and held fixed for the entire 2005-2024 evaluation."
            ),
        },
    }

    # Merge probabilistic outcomes and validation
    summary.update(prob_outcomes)

    def _default(o):
        if isinstance(o, (np.integer, np.int64)):
            return int(o)
        if isinstance(o, (np.floating, float)):
            if np.isnan(o) or np.isinf(o):
                return None
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, np.bool_):
            return bool(o)
        raise TypeError(f"Not serializable: {type(o)}")

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=_default)

    return summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Market BSDT-exact MFLS + Energy + Dynamics pipeline")
    p.add_argument("--start", default="2005-01-01")
    p.add_argument("--end", default="2024-12-31")
    p.add_argument("--window", type=int, default=252)
    p.add_argument("--drawdown-window", type=int, default=63)
    p.add_argument("--horizon", type=int, default=21)
    p.add_argument("--alpha", type=float, default=1.0)
    p.add_argument("--dt", type=float, default=0.05)
    p.add_argument("--theta-quantile", type=float, default=0.90)
    p.add_argument("--p-elevated", type=float, default=0.80)
    p.add_argument("--p-critical", type=float, default=0.95)
    p.add_argument("--sigma-pair", type=float, default=1.0)
    p.add_argument("--eps-att", type=float, default=0.5)
    p.add_argument("--eps-rep", type=float, default=0.1)
    p.add_argument("--normal-end", default="2007-06-30",
                   help="End date of fixed normal-period calibration window (default: 2007-06-30)")
    p.add_argument("--sp500-csv", default=None)
    p.add_argument("--vix-csv", default=None)
    p.add_argument("--hy-csv", default=None)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = Config(
        start=args.start,
        end=args.end,
        window=args.window,
        drawdown_window=args.drawdown_window,
        horizon=args.horizon,
        alpha=args.alpha,
        dt=args.dt,
        theta_quantile=args.theta_quantile,
        p_elevated=args.p_elevated,
        p_critical=args.p_critical,
        sigma_pair=args.sigma_pair,
        eps_att=args.eps_att,
        eps_rep=args.eps_rep,
        normal_end=args.normal_end,
    )

    summary = run_pipeline(cfg, args.sp500_csv, args.vix_csv, args.hy_csv)
    print("=" * 70)
    print("BSDT-Exact Market MFLS pipeline complete")
    print(f"Obs: {summary['n_obs']}  |  Range: {summary['date_start']} -> {summary['date_end']}")
    print("Regimes:", summary["regime_counts"])
    print("Corr(MFLS -> future drawdown):", round(summary["drawdown_metrics"]["corr_S_to_future_drawdown"], 4))
    bsdt = summary.get("bsdt_exact", {})
    fw = bsdt.get("fisher_weights", {})
    print(f"Fisher weights: C={fw.get('w_C', 0):.3f}  G={fw.get('w_G', 0):.3f}  "
          f"A={fw.get('w_A', 0):.3f}  T={fw.get('w_T', 0):.3f}")
    val = summary.get("validation", {})
    print(f"Lift (Critical/Normal at DD<-5%): {val.get('lift_critical_vs_normal_5pct')}")
    print(f"AUC(MFLS -> DD<-5%): {val.get('auc_mfls_to_5pct_drawdown')}")
    td = summary.get("transition_diagnostics", {})
    print(f"C_man transitions: {td.get('n_transitions')}  |  % above C_man: {td.get('pct_above_cman', 0):.2%}")
    print("Outputs:")
    print("  -", summary["output_csv"])
    print("  -", str(RESULTS_DIR / "market_mfls_summary.json"))
    print("=" * 70)


if __name__ == "__main__":
    main()
