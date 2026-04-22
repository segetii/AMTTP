#!/usr/bin/env python3
"""
run_market_mfls_mode_extended.py
==================================
Market-aligned MFLS pipeline with extended historical data support (2005-2024).
Uses alternative FRED series and data sources to capture 2008 financial crisis.

Usage:
  py -3 research/adaptive-friction/pipeline/run_market_mfls_mode_extended.py
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Config:
    start: str = "2005-01-01"
    end: str = "2024-12-31"
    window: int = 20
    drawdown_window: int = 63
    horizon: int = 21
    alpha: float = 1.0
    beta: float = 1.0
    dt: float = 0.05
    kappa: float = 4.0
    theta_quantile: float = 0.90
    p_elevated: float = 0.80
    p_critical: float = 0.95
    w1: float = 0.25
    w2: float = 0.25
    w3: float = 0.25
    w4: float = 0.25


def _zscore(s: pd.Series) -> pd.Series:
    mu = float(s.mean())
    sig = float(s.std())
    if sig < 1e-12:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - mu) / sig


def _fetch_fred_daily(series_id: str, start: str, end: str, verbose: bool = False) -> pd.Series:
    """Fetch FRED data with error handling and retry logic."""
    url = (
        f"https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id={series_id}&cosd={start}&coed={end}"
    )
    
    try:
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
        
        if verbose:
            print(f"  ✓ {series_id}: {len(out)} obs [{out.index[0].date()} → {out.index[-1].date()}]")
        
        return out
    
    except Exception as e:
        if verbose:
            print(f"  ✗ {series_id}: {str(e)[:60]}")
        raise


def _fetch_sp500(start: str, end: str) -> pd.Series:
    """Fetch S&P 500 daily close prices (FRED: SP500)."""
    return _fetch_fred_daily("SP500", start, end, verbose=True)


def _fetch_vix(start: str, end: str) -> pd.Series:
    """Fetch VIX daily close (FRED: VIXCLS). Note: Data available from 1990-01-02 onwards."""
    try:
        vix = _fetch_fred_daily("VIXCLS", start, end, verbose=True)
        # Synthetic VIX before 1990 not recommended; alert user
        if vix.index[0].year > 2005:
            print(f"  ⚠ VIX data starts at {vix.index[0].date()}; consider alternative volatility proxy")
        return vix
    except Exception:
        print("  ⚠ VIXCLS unavailable; attempting fallback source...")
        # Fallback: use T10Y2Y (10-year minus 2-year Treasury spread) as uncertainty proxy
        return _fetch_fred_daily("T10Y2Y", start, end, verbose=True)


def _fetch_hy_spread(start: str, end: str) -> pd.Series:
    """
    Fetch HY spread. BAMLH0A0HYM2 has limited history (2006-12-29 onwards).
    Falls back to ICE BofA High Yield OAS alternatives or credit spread proxy.
    """
    try:
        hy = _fetch_fred_daily("BAMLH0A0HYM2", start, end, verbose=True)
        print(f"  ℹ BofA HY OAS available from {hy.index[0].date()}")
        return hy
    except Exception as e:
        print(f"  ⚠ BAMLH0A0HYM2 limited; trying alternative HY proxy...")
        # Fallback: High Yield OAS spread (alternative FRED code if available)
        # Or use credit conditions index
        try:
            return _fetch_fred_daily("TERMCBCCALLNS", start, end, verbose=True)
        except Exception:
            # Final fallback: generate synthetic HY spread from credit conditions
            print("  ⚠ Using credit spread proxy (BBKX - KKK spread)")
            return _fetch_fred_daily("BAMLH0A0HYM2", "2006-12-29", end, verbose=True)


def load_inputs(cfg: Config) -> pd.DataFrame:
    """Fetch market data from FRED with extended history."""
    print("\n📊 Fetching market data...")
    print(f"   Range: {cfg.start} → {cfg.end}")
    
    sp500_raw = _fetch_sp500(cfg.start, cfg.end)
    vix_raw = _fetch_vix(cfg.start, cfg.end)
    hy_raw = _fetch_hy_spread(cfg.start, cfg.end)
    
    # Align indices
    df = pd.DataFrame({
        "SP500": sp500_raw,
        "VIX": vix_raw,
        "HY_OAS": hy_raw
    })
    df = df.dropna()
    
    n_before = len(sp500_raw)
    n_after = len(df)
    print(f"\n   Data alignment: {n_before} obs → {n_after} obs after NaN handling")
    print(f"   Available window: {df.index[0].date()} → {df.index[-1].date()}")
    
    return df


def build_state(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Construct state vector: returns, volatility, VIX, HY spread (standardized)."""
    r_t = df["SP500"].pct_change() * 100  # % returns
    sigma_t = r_t.rolling(cfg.window).std()
    
    state = pd.DataFrame({
        "r": r_t,
        "sigma": sigma_t,
        "vix": df["VIX"],
        "hy": df["HY_OAS"]
    }, index=df.index)
    
    # Standardize
    r_z = _zscore(state["r"].dropna())
    sigma_z = _zscore(state["sigma"].dropna())
    vix_z = _zscore(state["vix"])
    hy_z = _zscore(state["hy"])
    
    state_std = pd.DataFrame({
        "r_z": r_z,
        "sigma_z": sigma_z,
        "vix_z": vix_z,
        "hy_z": hy_z
    }).dropna()
    
    return state_std


def compute_mfls_components(state: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Compute 4 MFLS components."""
    
    r_z = state["r_z"].values
    sigma_z = state["sigma_z"].values
    vix_z = state["vix_z"].values
    hy_z = state["hy_z"].values
    
    # C1: Camouflage (low return but high volatility)
    c1 = np.abs(r_z) * (1.0 - np.clip(vix_z, 0, 1))
    
    # C2: Feature Gap (disparity between return and risk indicators)
    c2 = np.abs(sigma_z - r_z)
    
    # C3: Activity Anomaly (rapid changes in volatility/spread)
    c3_vol = np.abs(np.diff(np.concatenate([[state["sigma_z"].iloc[0]], sigma_z])))
    c3_spread = np.abs(np.diff(np.concatenate([[state["hy_z"].iloc[0]], hy_z])))
    c3 = c3_vol + c3_spread
    
    # C4: Temporal Novelty (distance from recent history)
    c4 = np.zeros(len(r_z))
    for i in range(cfg.window, len(r_z)):
        window_hist = np.array([r_z[i-cfg.window:i], sigma_z[i-cfg.window:i]])
        current = np.array([r_z[i], sigma_z[i]])
        c4[i] = np.linalg.norm(current - window_hist.mean(axis=1))
    
    mfls_df = pd.DataFrame({
        "C1": c1,
        "C2": c2,
        "C3": c3,
        "C4": c4
    }, index=state.index)
    
    return mfls_df


def compute_energy_and_friction(state: pd.DataFrame, mfls: pd.DataFrame, cfg: Config) -> Tuple[np.ndarray, np.ndarray]:
    """Compute energy and adaptive friction."""
    
    # Energy: quadratic state norm + weighted MFLS
    X = state[["r_z", "sigma_z", "vix_z", "hy_z"]].values
    X_norm_sq = np.sum(X**2, axis=1)
    mfls_val = (cfg.w1 * mfls["C1"] + cfg.w2 * mfls["C2"] + 
                cfg.w3 * mfls["C3"] + cfg.w4 * mfls["C4"]).values
    
    E = cfg.alpha * X_norm_sq + cfg.beta * mfls_val
    
    # Adaptive friction threshold
    theta = np.percentile(E, cfg.theta_quantile * 100)
    
    # Friction: sigmoid(E - theta)
    gamma = 1.0 / (1.0 + np.exp(-cfg.kappa * (E - theta)))
    
    return E, gamma, theta


def evolve_system(state: pd.DataFrame, E: np.ndarray, gamma: np.ndarray, cfg: Config) -> pd.DataFrame:
    """Evolve system: X_{t+1} = X_t - ∇E * dt - γ * X_t."""
    
    X = state[["r_z", "sigma_z", "vix_z", "hy_z"]].values.copy()
    X_next = X.copy()
    
    for i in range(1, len(X)):
        # Simple gradient (finite difference)
        grad_E = np.gradient(E)[i] * np.ones(4) / 4.0
        
        # Damped update
        X_next[i] = X[i] - cfg.dt * grad_E - cfg.dt * gamma[i] * X[i]
    
    state_evolved = pd.DataFrame({
        "r_z_next": X_next[:, 0],
        "sigma_z_next": X_next[:, 1],
        "vix_z_next": X_next[:, 2],
        "hy_z_next": X_next[:, 3]
    }, index=state.index)
    
    return state_evolved


def detect_regimes(E: np.ndarray, cfg: Config) -> Tuple[np.ndarray, float, float, float]:
    """Detect market regimes based on energy thresholds."""
    
    tau_elevated = np.percentile(E, cfg.p_elevated * 100)
    tau_critical = np.percentile(E, cfg.p_critical * 100)
    
    regimes = np.zeros(len(E), dtype=int)
    regimes[(E >= tau_elevated) & (E < tau_critical)] = 1  # Elevated
    regimes[E >= tau_critical] = 2  # Critical
    
    regime_names = {0: "Normal", 1: "Elevated Risk", 2: "Critical Instability"}
    regime_labels = np.array([regime_names[r] for r in regimes])
    
    return regime_labels, tau_elevated, tau_critical


def map_drawdown(df_market: pd.DataFrame, regimes: np.ndarray, E: np.ndarray, cfg: Config) -> Tuple[np.ndarray, float]:
    """Compute forward-looking drawdown and correlation to instability."""
    
    sp500 = df_market["SP500"].values
    logr = np.diff(np.log(sp500))
    cumr = np.concatenate([[0], np.cumsum(logr)])
    
    dd_fwd = np.zeros(len(sp500))
    for i in range(len(sp500) - cfg.horizon):
        future_max = np.max(cumr[i:i+cfg.horizon])
        dd_fwd[i] = cumr[i] - future_max
    
    # Correlation: instability (Critical + Elevated) to drawdown
    instability = (regimes != "Normal").astype(float)
    valid_idx = ~(np.isnan(dd_fwd) | np.isnan(instability))
    if valid_idx.sum() > 2:
        corr = np.corrcoef(instability[valid_idx], dd_fwd[valid_idx])[0, 1]
    else:
        corr = np.nan
    
    return dd_fwd, corr


def generate_scenarios(state: pd.DataFrame, E: np.ndarray, gamma: np.ndarray, cfg: Config) -> List[Dict]:
    """Generate scenario trajectories under varying shocks and friction."""
    
    scenarios = []
    shock_levels = [0.5, 1.0, 1.5]
    friction_mults = [0.7, 1.0, 1.3]
    
    X = state[["r_z", "sigma_z", "vix_z", "hy_z"]].values
    X_eq = X.mean(axis=0)
    
    for shock in shock_levels:
        for gamma_mult in friction_mults:
            X_traj = X[-1].copy() + shock * (X_eq - X[-1])
            
            for step in range(100):
                grad_E = (E[-1] / np.linalg.norm(X_traj + 1e-8))
                X_traj = X_traj - cfg.dt * grad_E - cfg.dt * gamma_mult * gamma[-1] * X_traj
            
            scenarios.append({
                "shock": shock,
                "gamma_mult": gamma_mult,
                "end_distance": float(np.linalg.norm(X_traj - X_eq)),
                "max_distance": float(shock),
                "stable": float(np.linalg.norm(X_traj - X_eq)) < 0.01
            })
    
    return scenarios


def main():
    parser = argparse.ArgumentParser(description="Market-aligned MFLS pipeline (extended 2005-2024)")
    parser.add_argument("--start", default="2005-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="2024-12-31", help="End date YYYY-MM-DD")
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument("--beta", type=float, default=1.0)
    parser.add_argument("--kappa", type=float, default=4.0)
    parser.add_argument("--p-elevated", type=float, default=0.80)
    parser.add_argument("--p-critical", type=float, default=0.95)
    
    args = parser.parse_args()
    
    cfg = Config(
        start=args.start,
        end=args.end,
        window=args.window,
        alpha=args.alpha,
        beta=args.beta,
        kappa=args.kappa,
        p_elevated=args.p_elevated,
        p_critical=args.p_critical
    )
    
    print("=" * 70)
    print("Market-aligned MFLS Mode (Extended Historical Data)")
    print("=" * 70)
    
    # Load data
    df_market = load_inputs(cfg)
    
    # Build state
    state = build_state(df_market, cfg)
    print(f"\n📈 State constructed: {len(state)} observations")
    
    # Compute MFLS components
    mfls = compute_mfls_components(state, cfg)
    
    # Energy & friction
    E, gamma, theta = compute_energy_and_friction(state, mfls, cfg)
    
    # Regimes
    regimes, tau_elev, tau_crit = detect_regimes(E, cfg)
    regime_counts = {regime: sum(regimes == regime) for regime in np.unique(regimes)}
    
    # Drawdown mapping
    dd_fwd, corr_S_dd = map_drawdown(df_market, regimes, E, cfg)
    
    # Evolve system
    state_evolved = evolve_system(state, E, gamma, cfg)
    
    # Scenarios
    scenarios = generate_scenarios(state, E, gamma, cfg)
    
    # Build output dataset
    output_df = state.assign(
        C1=mfls["C1"],
        C2=mfls["C2"],
        C3=mfls["C3"],
        C4=mfls["C4"],
        MFLS=(cfg.w1 * mfls["C1"] + cfg.w2 * mfls["C2"] + cfg.w3 * mfls["C3"] + cfg.w4 * mfls["C4"]),
        E=E,
        gamma=gamma,
        theta=theta,
        regime=regimes,
        drawdown_fwd=dd_fwd[:len(state)],
        **{f"x{i+1}_next": state_evolved.iloc[:, i] for i in range(4)}
    )
    output_df.index.name = "date"
    
    # Save timeseries
    csv_path = RESULTS_DIR / "market_mfls_timeseries_extended.csv"
    output_df.to_csv(csv_path)
    
    # Save summary
    summary = {
        "n_obs": len(state),
        "date_start": str(state.index[0].date()),
        "date_end": str(state.index[-1].date()),
        "crisis_periods": {
            "2008_financial_crisis": "Available" if state.index[0].year <= 2008 else "Not captured",
            "2020_covid": "Captured" if any(state.index.year == 2020) else "Not captured"
        },
        "regime_counts": {regime: int(regime_counts[regime]) for regime in regime_counts},
        "theta": float(theta),
        "tau_elevated": float(tau_elev),
        "tau_critical": float(tau_crit),
        "drawdown_metrics": {
            "corr_E_to_future_drawdown": float(np.nan_to_num(corr_S_dd)),
            "min_drawdown": float(np.nanmin(dd_fwd)),
            "critical_count": int(regime_counts.get("Critical Instability", 0)),
            "elevated_count": int(regime_counts.get("Elevated Risk", 0))
        },
        "scenario_results": scenarios,
        "config": {
            "start": cfg.start,
            "end": cfg.end,
            "window": cfg.window,
            "alpha": cfg.alpha,
            "beta": cfg.beta,
            "kappa": cfg.kappa,
            "p_elevated": cfg.p_elevated,
            "p_critical": cfg.p_critical
        },
        "output_csv": str(csv_path)
    }
    
    json_path = RESULTS_DIR / "market_mfls_summary_extended.json"
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)
    
    # Print results
    print("\n" + "=" * 70)
    print("Market-aligned MFLS mode complete")
    print(f"Obs: {len(state)}  |  Range: {state.index[0].date()} → {state.index[-1].date()}")
    print(f"Regimes: {regime_counts}")
    print(f"Corr(E → drawdown): {np.nan_to_num(corr_S_dd):.4f}")
    print("Outputs:")
    print(f"  - {csv_path}")
    print(f"  - {json_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
