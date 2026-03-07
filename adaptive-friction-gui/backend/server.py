"""
Adaptive Friction Control — API Server
=======================================
FastAPI backend serving pipeline results and real-time parameter control.
"""
from __future__ import annotations
import sys, json, time
import numpy as np
import pandas as pd
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

# Add pipeline to path (both original and upgraded)
BASE = Path(__file__).resolve().parent.parent.parent
PIPELINE_DIR = BASE / "research" / "adaptive-friction" / "pipeline"
UPGRADED_DIR = BASE / "research" / "adaptive-friction" / "upgraded"
PIPELINE_DIR_V2 = BASE / "adaptive-friction-stability-upgraded" / "pipeline"
sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(UPGRADED_DIR))
sys.path.insert(0, str(PIPELINE_DIR_V2))

from gravity_engine import (
    BSDTOperator, analyse_trajectory, simulate_and_align,
    total_energy, total_force, radial_energy, pairwise_energy,
    ALPHA, GAMMA, SIGMA, LAMBDA_REP
)
try:
    from state_matrix import build_state_matrix_fdic, standardise_panel, get_normal_period
except ImportError:
    from state_matrix import build_state_matrix as build_state_matrix_fdic, standardise_panel, get_normal_period

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="Adaptive Friction Control", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Cached state ─────────────────────────────────────────────────────────────
_cache: dict = {}
RESULTS_DIR = PIPELINE_DIR / "results"


def _load_results() -> dict:
    """Load pre-computed pipeline results."""
    stats_path = RESULTS_DIR / "pipeline_stats.json"
    if not stats_path.exists():
        # Try v2
        stats_path = RESULTS_DIR / "pipeline_stats_v2.json"
    if not stats_path.exists():
        raise FileNotFoundError("No pipeline results found. Run the pipeline first.")
    with open(stats_path) as f:
        return json.load(f)


def _load_cached_pipeline():
    """Load or compute full pipeline trajectory data."""
    if "stats" in _cache:
        return _cache

    # Try loading from numpy cache first
    cache_npz = RESULTS_DIR / "trajectory_cache.npz"
    if cache_npz.exists():
        data = np.load(cache_npz, allow_pickle=True)
        _cache["energy"] = data["energy"]
        _cache["mfls"] = data["mfls"]
        _cache["lambda_max"] = data["lambda_max"]
        _cache["gamma_star"] = data["gamma_star"]
        _cache["above_cman"] = data["above_cman"]
        _cache["cos_theta"] = data["cos_theta"]
        _cache["force_norm"] = data["force_norm"]
        _cache["dates"] = [str(d) for d in data["dates"]]
        _cache["stats"] = True
        # NOTE: npz cache does not contain X_std / bsdt / mu_eq which the
        # /api/simulate endpoint needs.  Fall through to rebuild them so
        # simulation works even after a server restart.

    # Run or re-run the minimal pipeline (also fills X_std, bsdt, mu_eq)
    have_trajectory = "stats" in _cache      # True when npz was loaded above
    if not have_trajectory:
        print("[server] Running minimal pipeline to generate trajectory...")
    else:
        print("[server] Rebuilding X_std / bsdt for simulation support...")

    try:
        from fred_loader import fetch_all, apply_transforms, standardise
        raw_fred = fetch_all(use_cache=True, verbose=False)
    except Exception:
        # Synthetic fallback
        from run_pipeline import _synthetic_fred_fallback
        raw_fred = _synthetic_fred_fallback()

    slope_col = "slope_10y2y" if "slope_10y2y" in raw_fred.columns else raw_fred.columns[0]
    fred_slope = raw_fred[slope_col].copy()

    # Try FDIC
    try:
        from fdic_loader import fetch_fdic_specgrp
        fdic_df = fetch_fdic_specgrp(start="1990-01-01", end="2024-12-31",
                                     use_cache=True, verbose=False)
        X_all, dates, sector_names = build_state_matrix_fdic(fdic_df, fred_slope)
    except Exception:
        from run_pipeline import main as _  # just to get the fallback logic
        xf = apply_transforms(raw_fred)
        std_df, _, _ = standardise(xf)
        # Minimal synthetic
        rng = np.random.default_rng(42)
        T = len(std_df)
        N, d = 7, 6
        X_all = rng.standard_normal((T, N, d))
        dates = std_df.index
        sector_names = [f"Sector {i+1}" for i in range(N)]

    X_normal, dates_normal = get_normal_period(X_all, dates)
    X_std, _, _ = standardise_panel(X_all, X_ref=X_normal)
    X_norm_std, _, _ = standardise_panel(X_normal, X_ref=X_normal)
    mu_eq = X_norm_std.reshape(-1, X_std.shape[-1]).mean(axis=0)

    bsdt = BSDTOperator().fit(X_norm_std)

    if not have_trajectory:
        stats = analyse_trajectory(X_std, mu_eq, bsdt, alpha=ALPHA, n_power_iter=10)

        # Cache to disk
        cache_npz = RESULTS_DIR / "trajectory_cache.npz"
        np.savez(cache_npz,
                 energy=stats["energy"], mfls=stats["mfls"],
                 lambda_max=stats["lambda_max"], gamma_star=stats["gamma_star"],
                 above_cman=stats["above_cman"], cos_theta=stats["cos_theta"],
                 force_norm=stats["force_norm"],
                 dates=np.array([str(d.date()) for d in dates]))

        _cache["energy"] = stats["energy"]
        _cache["mfls"] = stats["mfls"]
        _cache["lambda_max"] = stats["lambda_max"]
        _cache["gamma_star"] = stats["gamma_star"]
        _cache["above_cman"] = stats["above_cman"]
        _cache["cos_theta"] = stats["cos_theta"]
        _cache["force_norm"] = stats["force_norm"]
        _cache["dates"] = [str(d.date()) for d in dates]

    _cache["sector_names"] = sector_names
    _cache["mu_eq"] = mu_eq
    _cache["X_std"] = X_std
    _cache["bsdt"] = bsdt
    _cache["stats"] = True
    return _cache


# ── Models ───────────────────────────────────────────────────────────────────
class SimulationParams(BaseModel):
    alpha: float = 0.10
    gamma: float = 1.00
    sigma: float = 1.00
    lambda_rep: float = 0.10
    n_steps: int = 100
    eta: float = 0.02
    crisis_date: str = "2008-09-30"


class CCyBParams(BaseModel):
    kappa: float = 0.5
    ccyb_max_bps: float = 250.0


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/api/summary")
def get_summary():
    """Return pipeline summary statistics."""
    try:
        results = _load_results()
        return results
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/trajectory")
def get_trajectory():
    """Return full time series trajectory data for charts."""
    try:
        data = _load_cached_pipeline()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "dates": data["dates"],
        "energy": data["energy"].tolist(),
        "mfls": data["mfls"].tolist(),
        "lambda_max": data["lambda_max"].tolist(),
        "gamma_star": data["gamma_star"].tolist(),
        "above_cman": data["above_cman"].tolist(),
        "cos_theta": data["cos_theta"].tolist(),
        "force_norm": data["force_norm"].tolist(),
    }


@app.get("/api/crisis-windows")
def get_crisis_windows():
    """Return crisis window definitions and timing."""
    return {
        "windows": {
            "GFC 2008": {"start": "2007-01-01", "end": "2009-06-30", "peak": "2008-09-15"},
            "COVID 2020": {"start": "2019-10-01", "end": "2021-03-31", "peak": "2020-03-31"},
            "Rate Shock 2022": {"start": "2022-01-01", "end": "2023-06-30", "peak": "2022-10-31"},
        }
    }


@app.post("/api/simulate")
def run_simulation(params: SimulationParams):
    """Run a GravityEngine simulation from a crisis onset with custom parameters."""
    try:
        data = _load_cached_pipeline()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if "X_std" not in data or "bsdt" not in data:
        raise HTTPException(status_code=400, detail="Full pipeline data not cached. Restart server.")

    X_std = data["X_std"]
    dates = data["dates"]
    bsdt = data["bsdt"]
    mu_eq = data["mu_eq"]

    # Find nearest date
    target = pd.Timestamp(params.crisis_date)
    date_idx = int(np.argmin([abs((pd.Timestamp(d) - target).days) for d in dates]))

    X0 = X_std[date_idx].copy()

    # Run simulation
    X = X0.copy()
    trajectory = {"steps": [], "energy": [], "mfls": [], "cos_theta": [], "force_norm": []}

    for step in range(params.n_steps):
        mu_t = X.mean(axis=0)
        F = total_force(X, mu_t, alpha=params.alpha)
        G_bs = bsdt.gradient(X)

        e = total_energy(X, mu_eq, alpha=params.alpha)
        m = float(np.linalg.norm(G_bs))
        fn = float(np.linalg.norm(F))

        dot_per = np.sum(G_bs * F, axis=1)
        norm_g = np.linalg.norm(G_bs, axis=1)
        norm_f = np.linalg.norm(F, axis=1)
        cos_per = dot_per / (norm_g * norm_f + 1e-12)
        ct = float(np.mean(cos_per))

        trajectory["steps"].append(step)
        trajectory["energy"].append(e)
        trajectory["mfls"].append(m)
        trajectory["cos_theta"].append(ct)
        trajectory["force_norm"].append(fn)

        X = X + params.eta * F
        if np.linalg.norm(params.eta * F) < 1e-6:
            break

    return {
        "start_date": dates[date_idx],
        "n_steps": len(trajectory["steps"]),
        "params": params.dict(),
        "trajectory": trajectory,
    }


@app.post("/api/ccyb")
def compute_ccyb(params: CCyBParams):
    """Compute CCyB recommendations with custom parameters."""
    try:
        data = _load_cached_pipeline()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    gamma_star = data["gamma_star"]
    # Use MFLS as proxy for sigma_leverage
    sigma_lev = data["mfls"] / (np.max(data["mfls"]) + 1e-12)

    raw = gamma_star * sigma_lev / (params.kappa + 1e-9)
    p99 = np.quantile(raw[raw > 0], 0.99) if (raw > 0).any() else 1.0
    ccyb_bps = np.clip(raw / (p99 + 1e-9) * 200.0, 0.0, params.ccyb_max_bps)

    return {
        "dates": data["dates"],
        "ccyb_bps": ccyb_bps.tolist(),
        "gamma_star": gamma_star.tolist(),
        "sigma_leverage": sigma_lev.tolist(),
        "params": params.dict(),
        "summary": {
            "mean_ccyb_bps": float(np.mean(ccyb_bps)),
            "max_ccyb_bps": float(np.max(ccyb_bps)),
            "quarters_above_100bps": int((ccyb_bps > 100).sum()),
            "quarters_above_200bps": int((ccyb_bps > 200).sum()),
        }
    }


@app.get("/api/phase-diagram")
def get_phase_diagram():
    """Return data for the spectral phase transition diagram."""
    try:
        data = _load_cached_pipeline()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "dates": data["dates"],
        "lambda_max": data["lambda_max"].tolist(),
        "gamma_star": data["gamma_star"].tolist(),
        "above_cman": data["above_cman"].tolist(),
        "alpha": ALPHA,
        "phase_threshold": ALPHA,
    }


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": time.time()}


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

@app.get("/")
def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8050)
