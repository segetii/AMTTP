#!/usr/bin/env python3
"""
run_market_mfls_crisis.py
==========================
Market MFLS pipeline targeting 2008 financial crisis + 2020 COVID.
Uses SP500 + VIXCLS + synthetic spread from available FRED data.

Key constraint: Complete daily data from 2005 onward using:
  - SP500 stock index (from FRED)
  - VIXCLS volatility (from FRED, 1990+)
  - Synthetic HY spread (constructed from available FRED credit conditions)

Usage:
  py -3 research/adaptive-friction/pipeline/run_market_mfls_crisis.py
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd


RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Config:
    start: str = "2005-01-01"
    end: str = "2024-12-31"
    window: int = 20
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
    """Standardize series to mean 0, std 1."""
    mu = float(s.mean())
    sig = float(s.std())
    if sig < 1e-12:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - mu) / sig


def _fetch_fred_daily(series_id: str, start: str, end: str) -> Tuple[pd.Series, bool]:
    """Fetch FRED data; return (Series, success_bool)."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}&coed={end}"
    try:
        df = pd.read_csv(url)
        date_col = "DATE" if "DATE" in df.columns else "observation_date"
        if date_col not in df.columns or series_id not in df.columns:
            return None, False
        out = pd.Series(df[series_id].values, index=pd.to_datetime(df[date_col]), name=series_id)
        return pd.to_numeric(out, errors="coerce"), True
    except:
        return None, False


def load_inputs(cfg: Config) -> Tuple[pd.DataFrame, str]:
    """Load SP500, VIX, and construct synthetic spread for crisis analysis."""
    print("\n📊 Loading market data for crisis analysis (2005-2024)...")
    
    # Fetch primary series
    sp500, ok_sp = _fetch_fred_daily("SP500", cfg.start, cfg.end)
    vix, ok_vix = _fetch_fred_daily("VIXCLS", cfg.start, cfg.end)
    
    print(f"  ✓ SP500: {len(sp500)} obs" if ok_sp else "  ✗ SP500 fetch failed")
    print(f"  ✓ VIXCLS: {len(vix)} obs" if ok_vix else "  ✗ VIXCLS fetch failed")
    
    if not (ok_sp and ok_vix):
        raise ValueError("Failed to fetch core series (SP500, VIXCLS)")
    
    # Align primary series
    df = pd.DataFrame({"SP500": sp500, "VIX": vix}).dropna()
    print(f"  ✓ Aligned: {len(df)} obs [{df.index[0].date()} → {df.index[-1].date()}]")
    
    # Construct synthetic HY spread as volatility scaled by returns dispersion
    sp500_ret = df["SP500"].pct_change() * 100
    hy_synthetic = df["VIX"].rolling(20).std() * (1 + np.abs(sp500_ret).rolling(20).mean())
    hy_synthetic = hy_synthetic.fillna(method="bfill").fillna(method="ffill")
    
    df["HY_Spread"] = hy_synthetic
    print(f"  ✓ HY Spread (synthetic): {hy_synthetic.notna().sum()} obs")
    
    source_str = "SP500 (FRED) | VIXCLS (FRED) | HY_Spread (synthetic volatility-based)"
    return df.dropna(), source_str


def build_state(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Construct standardized state vector."""
    r_t = df["SP500"].pct_change() * 100
    sigma_t = r_t.rolling(cfg.window).std()
    
    state = pd.DataFrame({
        "r": r_t,
        "sigma": sigma_t,
        "vix": df["VIX"],
        "spread": df["HY_Spread"]
    }, index=df.index)
    
    # Standardize
    r_z = _zscore(state["r"].dropna())
    sigma_z = _zscore(state["sigma"].dropna())
    vix_z = _zscore(state["vix"])
    spread_z = _zscore(state["spread"])
    
    return pd.DataFrame({
        "r_z": r_z,
        "sigma_z": sigma_z,
        "vix_z": vix_z,
        "spread_z": spread_z
    }, index=state.index).dropna()


def compute_mfls_components(state: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Canonical BSDT four-channel decomposition (Complete_Derivations S12, SXXIV.4).

    State X is z-scored so equilibrium X* = 0 and g_t = nabla_X E = X_t
    (since E = 0.5 * ||X_t||^2).

    Four channels (Odeyemi 2025, Definition 4.1):
      delta_C  Camouflage       max_k|X_k| / mean_k|X_k| - 1
                                0 = uniform; > 0 = one channel dominates.
      delta_G  Feature Gap      |||g_t|| - ||g_ref||| / ||g_ref||
                                Normalised drift from slow-EMA reference norm.
      delta_A  Activity Anomaly |d||g_t|| / dt| / ||g_ref||
                                Gradient norm acceleration, normalised.
      delta_T  Temporal Novelty max(0, 1 - cos(g_t, r_t))
                                Directional surprise vs running EMA direction.

    MFLS_ch(t) = ||(delta_C, delta_G, delta_A, delta_T)||_2   [L2 norm, SXXVI.1]
    MFLS(t)    = max_{t' in [t-L, t]} MFLS_ch(t')             [windowed peak, SXII.1]
    """
    X = state.iloc[:, :4].values.astype(float)  # (T, 4), equilibrium at origin
    T = len(X)

    g_norm = np.linalg.norm(X, axis=1)  # (T,)

    # Reference norm: slow EMA captures "normal" gradient magnitude
    ref_norm = (pd.Series(g_norm)
                .ewm(span=max(cfg.window * 5, 20), min_periods=1)
                .mean().values)
    ref_norm = np.maximum(ref_norm, 1e-10)

    # Running mean direction: EMA of unit gradient vectors
    X_unit = X / (g_norm[:, None] + 1e-12)
    alpha_ema = 2.0 / (cfg.window + 1)
    run_dir = np.empty_like(X_unit)
    run_dir[0] = X_unit[0]
    for t in range(1, T):
        run_dir[t] = (1.0 - alpha_ema) * run_dir[t - 1] + alpha_ema * X_unit[t]
    run_dir /= np.maximum(np.linalg.norm(run_dir, axis=1, keepdims=True), 1e-10)

    # delta_C: concentration of gradient across state components
    comp_mag = np.abs(X)
    delta_C  = comp_mag.max(axis=1) / np.maximum(comp_mag.mean(axis=1), 1e-10) - 1.0

    # delta_G: normalised deviation of gradient norm from reference
    delta_G  = np.abs(g_norm - ref_norm) / ref_norm

    # delta_A: gradient norm acceleration
    delta_A      = np.zeros(T)
    delta_A[1:]  = np.abs(g_norm[1:] - g_norm[:-1]) / ref_norm[1:]

    # delta_T: directional surprise relative to running mean direction
    cos_sim = np.einsum("ti,ti->t", X_unit, run_dir)
    delta_T = np.maximum(0.0, 1.0 - cos_sim)

    # MFLS_ch: instantaneous channel-space L2 norm  (Definition SXXVI.1)
    g_ch    = np.stack([delta_C, delta_G, delta_A, delta_T], axis=1)  # (T, 4)
    mfls_ch = np.linalg.norm(g_ch, axis=1)                             # (T,)

    # MFLS: windowed peak over lead window L = cfg.window  (Definition SXII.1)
    mfls = pd.Series(mfls_ch).rolling(window=cfg.window, min_periods=1).max().values

    return pd.DataFrame({
        "C1": delta_C,       # channel 1: camouflage
        "C2": delta_G,       # channel 2: feature gap
        "C3": delta_A,       # channel 3: activity anomaly
        "C4": delta_T,       # channel 4: temporal novelty
        "mfls_ch": mfls_ch,  # instantaneous ||g_t||_2
        "MFLS": mfls,        # windowed peak MFLS(t)
    }, index=state.index)


def compute_energy_friction(state: pd.DataFrame, mfls: pd.DataFrame, cfg: Config) -> Tuple[np.ndarray, np.ndarray, float]:
    """Canonical Lyapunov energy and guardian friction (S III.2, S XII).

    E(t)      = 0.5 * ||X_t||^2  — pure tracking energy; NOT contaminated by MFLS.
                                    This is the Lyapunov function whose level sets
                                    define the stability radius of the CGS design.
    theta     = theta_quantile(E) — empirical stability boundary (S XXIV.3).
    gamma*(t) = E(t) / (E(t) + theta)  in [0, 1)  — canonical guardian friction.
                Silent below theta; approaches 1 for E >> theta.
    """
    X     = state.iloc[:, :4].values.astype(float)
    E     = 0.5 * np.sum(X ** 2, axis=1)
    theta = float(np.percentile(E, cfg.theta_quantile * 100))
    gamma = E / (E + max(theta, 1e-10))      # canonical guardian in [0, 1)
    return E, gamma, theta


def detect_regimes(E: np.ndarray, cfg: Config) -> Tuple[np.ndarray, float, float]:
    """Classify markets by instability level."""
    tau_elev = np.percentile(E, cfg.p_elevated * 100)
    tau_crit = np.percentile(E, cfg.p_critical * 100)
    
    regimes = np.empty(len(E), dtype=object)
    regimes[:] = "Normal"
    regimes[(E >= tau_elev) & (E < tau_crit)] = "Elevated Risk"
    regimes[E >= tau_crit] = "Critical Instability"
    
    return regimes, tau_elev, tau_crit


def map_drawdown(df: pd.DataFrame, regimes: np.ndarray, cfg: Config) -> Tuple[np.ndarray, float]:
    """Map regime transitions to forward drawdowns."""
    sp500 = df["SP500"].values
    logr = np.diff(np.log(sp500))
    cumr = np.concatenate([[0], np.cumsum(logr)])
    
    dd_fwd = np.zeros(len(sp500))
    for i in range(len(sp500) - cfg.horizon):
        future_max = np.max(cumr[i:i+cfg.horizon])
        dd_fwd[i] = cumr[i] - future_max
    
    # Correlation: instability → drawdown
    instability = (regimes != "Normal").astype(float)
    min_len = min(len(dd_fwd), len(instability))
    valid = ~(np.isnan(dd_fwd[:min_len]) | np.isnan(instability[:min_len]))
    
    if valid.sum() > 2:
        corr = np.corrcoef(instability[:min_len][valid], dd_fwd[:min_len][valid])[0, 1]
    else:
        corr = np.nan
    
    return dd_fwd, corr


def generate_scenarios(state: pd.DataFrame, E: np.ndarray, gamma: np.ndarray, cfg: Config) -> list:
    """Generate scenario trajectories."""
    scenarios = []
    X = state[["r_z", "sigma_z", "vix_z", "spread_z"]].values
    X_eq = X.mean(axis=0)
    
    for shock in [0.5, 1.0, 1.5]:
        for gamma_mult in [0.7, 1.0, 1.3]:
            X_traj = X[-1].copy() + shock * (X_eq - X[-1])
            for _ in range(100):
                grad_E = (E[-1] / max(np.linalg.norm(X_traj), 1e-8))
                X_traj = X_traj - cfg.dt * grad_E - cfg.dt * gamma_mult * gamma[-1] * X_traj
            
            scenarios.append({
                "shock": shock,
                "gamma_mult": gamma_mult,
                "end_distance": float(np.linalg.norm(X_traj - X_eq)),
                "stable": float(np.linalg.norm(X_traj - X_eq)) < 0.01
            })
    
    return scenarios


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2005-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--window", type=int, default=20)
    args = parser.parse_args()
    
    cfg = Config(start=args.start, end=args.end, window=args.window)
    
    print("="*70)
    print("MARKET MFLS - CRISIS PERIOD ANALYSIS (2005-2024)")
    print("="*70)
    
    try:
        # Load data
        df_market, data_source = load_inputs(cfg)
        
        # Build state
        state = build_state(df_market, cfg)
        print(f"\n📈 State constructed: {len(state)} observations")
        
        # Crisis events in range
        years_crisis = (2008, 2011, 2020)
        for year in years_crisis:
            has_year = any(state.index.year == year)
            symbol = "✓" if has_year else "⚠"
            print(f"  {symbol} {year}: " + ("Captured" if has_year else "Not in range"))
        
        # Compute components
        mfls = compute_mfls_components(state, cfg)
        E, gamma, theta = compute_energy_friction(state, mfls, cfg)
        
        # Regimes
        regimes, tau_elev, tau_crit = detect_regimes(E, cfg)
        regime_counts = dict(zip(*np.unique(regimes, return_counts=True)))
        
        # Drawdown
        dd_fwd, corr_regime_dd = map_drawdown(df_market, regimes, cfg)
        
        # Scenarios
        scenarios = generate_scenarios(state, E, gamma, cfg)
        
        # Build output
        mfls_total = mfls["MFLS"]           # windowed peak MFLS(t) = max_{[t-L,t]} ||g_t'||_2
        output_df = pd.DataFrame({
            "r_z": state["r_z"],
            "sigma_z": state["sigma_z"],
            "vix_z": state["vix_z"],
            "spread_z": state["spread_z"],
            "C1": mfls["C1"],
            "C2": mfls["C2"],
            "C3": mfls["C3"],
            "C4": mfls["C4"],
            "MFLS": mfls_total,
            "E": E,
            "gamma": gamma,
            "regime": regimes,
            "drawdown_fwd": dd_fwd[:len(state)]
        }, index=state.index)
        output_df.index.name = "date"
        
        # Save
        csv_file = RESULTS_DIR / "market_mfls_crisis_timeseries.csv"
        json_file = RESULTS_DIR / "market_mfls_crisis_summary.json"
        
        output_df.to_csv(csv_file)
        
        summary = {
            "metadata": {
                "analysis": "Market MFLS - Crisis Period (2005-2024)",
                "data_source": data_source,
                "date_range": f"{state.index[0].date()} → {state.index[-1].date()}",
                "n_observations": len(state)
            },
            "regime_distribution": {
                str(k): int(v) for k, v in regime_counts.items()
            },
            "energy_thresholds": {
                "theta": float(theta),
                "tau_elevated": float(tau_elev),
                "tau_critical": float(tau_crit)
            },
            "instability_correlation": {
                "corr_regime_to_fwd_drawdown": float(np.nan_to_num(corr_regime_dd))
            },
            "scenario_analysis": {
                "total_scenarios": len(scenarios),
                "stable_count": sum(1 for s in scenarios if s["stable"]),
                "details": scenarios
            },
            "crisis_events_captured": {
                "2008_financial_crisis": bool(any(state.index.year == 2008)),
                "2011_eurozone_crisis": bool(any(state.index.year == 2011)),
                "2020_covid_crash": bool(any(state.index.year == 2020))
            },
            "output_files": {
                "timeseries_csv": str(csv_file),
                "summary_json": str(json_file)
            }
        }
        
        with open(json_file, "w") as f:
            json.dump(summary, f, indent=2)
        
        # Print results
        print("\n" + "="*70)
        print("✓ ANALYSIS COMPLETE")
        print(f"\nDate Range: {state.index[0].date()} → {state.index[-1].date()}")
        print(f"Total Observations: {len(state)}")
        print(f"\nRegime Distribution:")
        for regime in ["Normal", "Elevated Risk", "Critical Instability"]:
            count = regime_counts.get(regime, 0)
            pct = 100*count/len(state)
            print(f"  {regime:25s}: {count:4d} ({pct:5.1f}%)")
        print(f"\nCrisis Events Captured:")
        for year in [2008, 2011, 2020]:
            has = "✓" if any(state.index.year == year) else "✗"
            print(f"  {has} {year}")
        print(f"\nMetrics:")
        print(f"  θ (energy threshold): {theta:.4f}")
        print(f"  τ_elevated (80%ile):  {tau_elev:.4f}")
        print(f"  τ_critical (95%ile):  {tau_crit:.4f}")
        print(f"  Corr(regime→drawdown): {np.nan_to_num(corr_regime_dd):.4f}")
        print(f"  Scenario stability: {sum(1 for s in scenarios if s['stable'])}/{len(scenarios)}")
        print(f"\nOutputs:")
        print(f"  {csv_file}")
        print(f"  {json_file}")
        print("="*70)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
