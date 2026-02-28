"""
FastAPI REST API for MFLS signals.

Endpoints:
  GET  /health                  — Health check
  GET  /api/v1/signal/gsib      — G-SIB MFLS signal
  GET  /api/v1/signal/fdic      — FDIC bank-level signal (top 30)
  GET  /api/v1/audit/bsdt       — Per-institution blind-spot audit
  GET  /api/v1/herding          — Herding / convergence monitor
  GET  /api/v1/causality        — Granger causality results
  POST /api/v1/signal/custom    — Score a custom panel
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from mfls import __version__
from mfls.engine import MFLSEngine
from mfls.api.models import (
    HealthResponse,
    SignalResponse,
    SignalPoint,
    AuditResponse,
    HerdingResponse,
    CausalityResponse,
    CustomPanelRequest,
)

logger = logging.getLogger("mfls.api")

app = FastAPI(
    title="MFLS API",
    description="Multi-Factor Lyapunov Systemic-risk engine — real-time blind-spot detection and macro-prudential calibration.",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# State: lazily initialised engines
# ---------------------------------------------------------------------------

_engines: dict = {}


def _get_engine(panel_type: str = "gsib", force_refresh: bool = False) -> MFLSEngine:
    """Get or create a cached engine for the given panel type."""
    key = panel_type
    if key not in _engines or force_refresh:
        engine = MFLSEngine()
        if panel_type == "gsib":
            panel = engine.load_gsib_panel(verbose=True)
        elif panel_type == "fdic":
            from mfls.data.fdic import FEATURE_NAMES
            # Top 30 US banks by asset size
            TOP_30_CERTS = {
                "JPMorgan Chase": 628, "Bank of America": 3510,
                "Citigroup": 7213, "Wells Fargo": 3511,
                "Goldman Sachs": 33124, "Morgan Stanley": 32992,
                "US Bancorp": 6548, "PNC": 3005,
                "Truist": 9846, "Capital One": 4297,
                "TD Bank": 57890, "Charles Schwab": 57450,
                "BNY Mellon": 542, "State Street": 14,
                "HSBC NA": 413208, "Citizens": 27389,
                "Fifth Third": 6672, "KeyBank": 3931,
                "Ally Financial": 57803, "M&T Bank": 501105,
                "Huntington": 12311, "Regions": 233031,
                "Discover": 5649, "Synchrony": 476810,
                "Comerica": 60143, "Zions": 2270,
                "Webster": 18022, "Popular": 27559,
                "East West": 19990, "Valley National": 14776,
            }
            panel = engine.load_fdic_panel(TOP_30_CERTS, verbose=True)
        else:
            raise ValueError(f"Unknown panel type: {panel_type}")

        engine.fit_and_score(panel, verbose=True)
        _engines[key] = engine

    return _engines[key]


def _build_signal_response(engine: MFLSEngine, panel_type: str) -> SignalResponse:
    """Build a SignalResponse from a fitted engine."""
    result = engine.fit_and_score(verbose=False)
    panel = engine._panel

    signal_points = []
    for i in range(len(result.dates)):
        signal_points.append(SignalPoint(
            date=str(result.dates[i].date()),
            mfls_score=round(float(result.signal[i]), 6),
            ccyb_bps=round(float(result.ccyb_bps[i]), 1) if result.ccyb_bps is not None else 0.0,
            above_threshold=bool(result.signal[i] > result.threshold) if result.threshold else False,
        ))

    return SignalResponse(
        panel_type=panel_type,
        n_institutions=panel.X_std.shape[1],
        n_quarters=panel.X_std.shape[0],
        auroc=result.auroc,
        auroc_ci=list(result.auroc_ci) if result.auroc_ci else None,
        gfc_lead_quarters=result.gfc_lead_quarters,
        hit_rate=result.hit_rate,
        false_alarm_rate=result.false_alarm_rate,
        threshold=result.threshold,
        spectral_radius=result.spectral_radius,
        current_mfls=round(float(result.signal[-1]), 6),
        current_ccyb_bps=round(float(result.ccyb_bps[-1]), 1) if result.ccyb_bps is not None else 0.0,
        current_alert=bool(result.signal[-1] > result.threshold) if result.threshold else False,
        signal=signal_points,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", version=__version__)


@app.get("/api/v1/signal/gsib", response_model=SignalResponse)
def signal_gsib(refresh: bool = Query(False, description="Force data refresh")):
    """G-SIB real-data systemic risk signal."""
    try:
        engine = _get_engine("gsib", force_refresh=refresh)
        return _build_signal_response(engine, "gsib")
    except Exception as e:
        logger.exception("Error computing G-SIB signal")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/signal/fdic", response_model=SignalResponse)
def signal_fdic(refresh: bool = Query(False, description="Force data refresh")):
    """FDIC bank-level systemic risk signal (top 30 US banks)."""
    try:
        engine = _get_engine("fdic", force_refresh=refresh)
        return _build_signal_response(engine, "fdic")
    except Exception as e:
        logger.exception("Error computing FDIC signal")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/audit/bsdt")
def audit_bsdt(
    panel_type: str = Query("gsib", description="gsib or fdic"),
    t: int = Query(-1, description="Time index (-1 = latest)"),
):
    """Per-institution blind-spot audit (4 BSDT channels)."""
    try:
        engine = _get_engine(panel_type)
        audit = engine.bsdt_audit(t=t)
        panel = engine._panel
        date_str = str(panel.dates[t if t >= 0 else len(panel.dates) + t].date())

        institutions = []
        for i in range(len(audit.institution_names)):
            institutions.append({
                "name": audit.institution_names[i],
                "delta_C": round(float(audit.delta_C[i]), 6),
                "delta_G": round(float(audit.delta_G[i]), 6),
                "delta_A": round(float(audit.delta_A[i]), 6),
                "delta_T": round(float(audit.delta_T[i]), 6),
                "total_score": round(float(audit.total_score[i]), 6),
                "dominant_channel": audit.dominant_channel[i],
            })

        return AuditResponse(
            date=date_str,
            n_institutions=len(audit.institution_names),
            institutions=institutions,
        )
    except Exception as e:
        logger.exception("Error computing BSDT audit")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/herding", response_model=HerdingResponse)
def herding(panel_type: str = Query("gsib")):
    """Herding / convergent behaviour monitor."""
    try:
        engine = _get_engine(panel_type)
        herd = engine.herding_score()
        panel = engine._panel

        signal_list = []
        for i in range(len(herd.dates)):
            signal_list.append({
                "date": str(herd.dates[i].date()),
                "temporal_novelty": round(float(herd.temporal_novelty[i]), 6),
                "herding_score": round(float(herd.herding_score[i]), 6),
            })

        return HerdingResponse(
            current_herding_score=round(float(herd.herding_score[-1]), 6),
            beta_delta_T=round(float(herd.beta_delta_T), 4) if herd.beta_delta_T else None,
            signed_lr_weights=herd.signed_lr_weights,
            signal=signal_list,
        )
    except Exception as e:
        logger.exception("Error computing herding score")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/causality", response_model=CausalityResponse)
def causality(panel_type: str = Query("gsib")):
    """Granger causality test results."""
    try:
        engine = _get_engine(panel_type)
        result = engine.fit_and_score(verbose=False)
        if result.causality_results is None:
            raise HTTPException(status_code=404, detail="Causality tests not available")

        summary = result.causality_results.get("summary", {})
        return CausalityResponse(
            linear_granger_best_p=summary.get("linear_granger_best_p", 1.0),
            threshold_granger_best_p=summary.get("threshold_granger_best_p", 1.0),
            quantile_causality_best_p=summary.get("quantile_causality_best_p", 1.0),
            detail=result.causality_results,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error computing causality")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/signal/custom", response_model=SignalResponse)
def signal_custom(req: CustomPanelRequest):
    """Score a custom panel (bring your own data)."""
    try:
        X = np.array(req.X)
        dates = pd.DatetimeIndex(req.dates)
        engine = MFLSEngine()
        panel = engine.load_custom_panel(
            X, dates, req.names, req.feature_names,
            req.normal_start, req.normal_end,
        )
        engine.fit_and_score(panel, verbose=False)
        return _build_signal_response(engine, "custom")
    except Exception as e:
        logger.exception("Error scoring custom panel")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """Start the MFLS API server."""
    import uvicorn
    uvicorn.run("mfls.api.app:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
