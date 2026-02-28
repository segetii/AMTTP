"""
Pydantic models for API request/response schemas.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
#  Response models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str


class SignalPoint(BaseModel):
    date: str
    mfls_score: float
    ccyb_bps: float
    above_threshold: bool


class SignalResponse(BaseModel):
    panel_type: str
    n_institutions: int
    n_quarters: int
    auroc: Optional[float] = None
    auroc_ci: Optional[List[float]] = None
    gfc_lead_quarters: Optional[int] = None
    hit_rate: Optional[float] = None
    false_alarm_rate: Optional[float] = None
    threshold: Optional[float] = None
    spectral_radius: Optional[float] = None
    current_mfls: float
    current_ccyb_bps: float
    current_alert: bool
    signal: List[SignalPoint]


class ChannelScore(BaseModel):
    delta_C: float
    delta_G: float
    delta_A: float
    delta_T: float
    total: float
    dominant_channel: str


class AuditResponse(BaseModel):
    date: str
    n_institutions: int
    institutions: List[Dict[str, object]]


class HerdingResponse(BaseModel):
    current_herding_score: float
    beta_delta_T: Optional[float] = None
    signed_lr_weights: Optional[Dict[str, float]] = None
    signal: List[Dict[str, object]]


class CausalityResponse(BaseModel):
    linear_granger_best_p: float
    threshold_granger_best_p: float
    quantile_causality_best_p: float
    detail: Dict


# ---------------------------------------------------------------------------
#  Request models
# ---------------------------------------------------------------------------

class CustomPanelRequest(BaseModel):
    """Upload a custom panel for scoring."""
    X: List[List[List[float]]] = Field(..., description="State matrix (T, N, d)")
    dates: List[str] = Field(..., description="ISO date strings (length T)")
    names: List[str] = Field(..., description="Institution names (length N)")
    feature_names: List[str] = Field(..., description="Feature names (length d)")
    normal_start: Optional[str] = None
    normal_end: Optional[str] = None
