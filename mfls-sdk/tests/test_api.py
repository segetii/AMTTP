"""Unit tests for the FastAPI REST API (no network calls)."""
import numpy as np
import pytest

from mfls.api.models import SignalResponse, SignalPoint, AuditResponse, HerdingResponse


class TestPydanticModels:
    """Verify response models can be constructed and serialised."""

    def test_signal_response(self):
        resp = SignalResponse(
            panel_type="gsib",
            n_institutions=7,
            n_quarters=40,
            auroc=0.81,
            auroc_ci=[0.60, 0.95],
            hit_rate=0.87,
            false_alarm_rate=0.52,
            gfc_lead_quarters=6,
            current_mfls=0.65,
            current_ccyb_bps=150.0,
            current_alert=True,
            signal=[SignalPoint(date="2008-01-01", mfls_score=0.6, ccyb_bps=120.0, above_threshold=True)],
        )
        d = resp.model_dump()
        assert d["auroc"] == 0.81
        assert len(d["signal"]) == 1

    def test_audit_response(self):
        resp = AuditResponse(
            date="2008-01-01",
            n_institutions=1,
            institutions=[
                {
                    "name": "JPMorgan",
                    "total_score": 2.3,
                    "dominant_channel": "delta_C",
                    "delta_C": 1.5,
                    "delta_G": 0.4,
                    "delta_A": 0.2,
                    "delta_T": 0.2,
                }
            ],
        )
        assert resp.institutions[0]["name"] == "JPMorgan"

    def test_herding_response(self):
        resp = HerdingResponse(
            current_herding_score=0.45,
            beta_delta_T=-0.12,
            signed_lr_weights={"delta_C": 0.3, "delta_G": 0.2, "delta_A": 0.1, "delta_T": -0.4},
            signal=[{"date": "2008-01-01", "herding_score": 0.45}],
        )
        assert resp.beta_delta_T == -0.12


class TestAPIImport:
    """Verify the FastAPI app can be imported without errors."""

    def test_import_app(self):
        from mfls.api.app import app
        assert app is not None
        # Check routes exist
        routes = [r.path for r in app.routes]
        assert "/health" in routes
        assert "/api/v1/signal/gsib" in routes
        assert "/api/v1/signal/fdic" in routes
        assert "/api/v1/audit/bsdt" in routes
        assert "/api/v1/herding" in routes
        assert "/api/v1/causality" in routes
        assert "/api/v1/signal/custom" in routes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
