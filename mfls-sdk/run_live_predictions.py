"""
MFLS Live Predictions — Fetch current FDIC data and generate fresh economic forecast.

This script:
1. Loads the top-30 U.S. bank panel via FDIC API (latest available data)
2. Runs the full MFLS pipeline (BSDT calibration, scoring, evaluation)
3. Generates a BSDT audit for the latest quarter
4. Computes CCyB recommendations
5. Computes herding scores
6. Outputs a comprehensive systemic risk assessment
"""

import sys
import json
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure mfls is importable
sys.path.insert(0, str(Path(__file__).parent))

from mfls.engine import MFLSEngine, CRISIS_WINDOWS
from mfls.data.fdic import build_bank_panel
from mfls.core.network import lw_correlation_network
from mfls.signals.pipeline import standardise_panel


def run_live_predictions():
    """Run full MFLS pipeline on latest FDIC data."""
    
    print("=" * 70)
    print("MFLS LIVE PREDICTION — SYSTEMIC RISK ASSESSMENT")
    print(f"Run date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    
    # --- 1. Load FDIC panel (latest available data) ---
    print("\n[1/6] Loading FDIC bank panel (top-30 U.S. banks)...")
    print("      Source: FDIC SDI REST API (https://banks.data.fdic.gov)")
    
    engine = MFLSEngine(
        normal_start="1994-01-01",
        normal_end="2003-12-31",
        n_boot=500,
        boot_block_len=8,
        threshold_pctl=75.0,
    )
    
    # Use a curated list of top U.S. banks by total assets
    certs = {
        "JPMorgan Chase": 628,
        "Bank of America": 3510,
        "Citibank": 7213,
        "Wells Fargo": 3511,
        "Goldman Sachs": 33124,
        "Morgan Stanley": 32992,
        "U.S. Bancorp": 6548,
        "PNC Financial": 6384,
        "Truist": 9846,
        "Capital One": 4297,
        "TD Bank": 17529,
        "Bank of NY Mellon": 542,
        "State Street": 14,
        "Charles Schwab": 57450,
        "Citizens Financial": 15680,
        "Fifth Third": 6672,
        "M&T Bank": 501,
        "KeyBank": 17534,
        "Huntington": 6560,
        "Regions Financial": 12368,
        "Ally Financial": 57803,
        "Synchrony": 57852,
        "Discover": 5649,
        "Comerica": 60143,
        "Zions Bancorp": 2270,
        "East West Bancorp": 32469,
        "New York Community": 22494,
        "Western Alliance": 58732,
    }
    
    try:
        panel = engine.load_fdic_panel(
            certs=certs,
            start="19900101",
            end="20251231",   # Request up to latest
            force_refresh=True,  # Force fresh fetch
            verbose=True,
        )
        print(f"      Panel loaded: T={panel.X_std.shape[0]}, N={panel.X_std.shape[1]}, d={panel.X_std.shape[2]}")
        print(f"      Date range:   {panel.dates[0]} to {panel.dates[-1]}")
        latest_date = panel.dates[-1]
        print(f"      Latest data:  {latest_date}")
    except Exception as e:
        print(f"      ERROR loading FDIC panel: {e}")
        print("      Falling back to cached data...")
        panel = engine.load_fdic_panel(certs=certs, force_refresh=False, verbose=True)
        latest_date = panel.dates[-1]
    
    # --- 2. Run full pipeline ---
    print("\n[2/6] Running MFLS pipeline (fit + score + evaluate)...")
    
    try:
        result = engine.fit_and_score(panel, verbose=True)
    except Exception as e:
        print(f"      ERROR in pipeline: {e}")
        import traceback; traceback.print_exc()
        return
    
    # --- 3. BSDT Audit (latest quarter) ---
    print("\n[3/6] BSDT Audit — latest quarter...")
    try:
        audit = engine.bsdt_audit(panel, t=-1)
        print(f"      Latest quarter audit ({latest_date}):")
        print(f"      Top 5 institutions by BSDT score:")
        # Sort by total score
        if hasattr(audit, 'scores') and audit.scores is not None:
            sorted_idx = np.argsort(-audit.scores)
            for rank, idx in enumerate(sorted_idx[:5], 1):
                name = panel.names[idx] if idx < len(panel.names) else f"Institution {idx}"
                score = audit.scores[idx]
                dominant = audit.dominant_channel[idx] if hasattr(audit, 'dominant_channel') else "N/A"
                print(f"        {rank}. {name}: score={score:.4f}, dominant={dominant}")
    except Exception as e:
        print(f"      Audit error: {e}")
    
    # --- 4. CCyB Recommendations ---
    print("\n[4/6] CCyB (Countercyclical Capital Buffer) recommendations...")
    try:
        ccyb = engine.ccyb(panel)
        latest_ccyb = ccyb[-1] if len(ccyb) > 0 else 0
        peak_ccyb = float(ccyb.max())
        print(f"      Current CCyB recommendation: {latest_ccyb:.0f} bps")
        print(f"      Peak historical CCyB:        {peak_ccyb:.0f} bps")
        
        # Recent trajectory
        recent = ccyb[-8:]  # Last 2 years
        recent_dates = panel.dates[-8:]
        print(f"      Recent CCyB trajectory (last 8 quarters):")
        for d, c in zip(recent_dates, recent):
            print(f"        {d.strftime('%Y-Q') + str(d.quarter)}: {c:.0f} bps")
    except Exception as e:
        print(f"      CCyB error: {e}")
    
    # --- 5. Herding Score ---
    print("\n[5/6] Herding score (convergent behaviour detection)...")
    try:
        herding = engine.herding_score(panel)
        latest_herding = herding.herding_score[-1] if len(herding.herding_score) > 0 else 0
        print(f"      Current herding score: {latest_herding:.4f} (0=diverse, 1=herding)")
        if herding.beta_delta_T is not None:
            print(f"      Signed-LR β_δT:        {herding.beta_delta_T:.4f}")
            if herding.beta_delta_T < 0:
                print(f"      → HERDING SIGNAL: negative β_δT indicates convergent behaviour")
        
        # Recent trajectory
        recent_h = herding.herding_score[-8:]
        print(f"      Recent herding trajectory:")
        for d, h in zip(panel.dates[-8:], recent_h):
            severity = "HIGH" if h > 0.7 else "MODERATE" if h > 0.4 else "LOW"
            print(f"        {d.strftime('%Y-Q') + str(d.quarter)}: {h:.4f} ({severity})")
    except Exception as e:
        print(f"      Herding error: {e}")
    
    # --- 6. Comprehensive Forecast ---
    print("\n[6/6] SYSTEMIC RISK FORECAST")
    print("=" * 70)
    
    # Current signal level
    current_signal = result.signal[-1]
    signal_mean = np.mean(result.signal)
    signal_std = np.std(result.signal)
    signal_z = (current_signal - signal_mean) / signal_std if signal_std > 0 else 0
    
    # Above/below threshold
    above_threshold = current_signal > result.threshold
    
    # Trend (last 4 quarters)
    recent_signal = result.signal[-4:]
    trend = "RISING" if recent_signal[-1] > recent_signal[0] else "FALLING"
    trend_pct = ((recent_signal[-1] - recent_signal[0]) / max(abs(recent_signal[0]), 1e-6)) * 100
    
    # Supercriticality
    from mfls.core.network import lw_correlation_network
    net = lw_correlation_network(panel.X_std)
    spectral_radius = net.spectral_radius
    
    # Normal period spectral radius for comparison
    X_normal = panel.X_std[panel.normal_mask]
    net_normal = lw_correlation_network(X_normal)
    sr_ratio = spectral_radius / net_normal.spectral_radius if net_normal.spectral_radius > 0 else 1
    
    print(f"\n  CURRENT STATE ({latest_date.strftime('%Y-Q') + str(latest_date.quarter)}):")
    print(f"  ├── MFLS Signal:        {current_signal:.4f}")
    print(f"  ├── Alarm Threshold:    {result.threshold:.4f}")
    print(f"  ├── Signal Z-score:     {signal_z:+.2f}σ")
    print(f"  ├── Above threshold:    {'YES ⚠' if above_threshold else 'NO ✓'}")
    print(f"  ├── 4Q Trend:           {trend} ({trend_pct:+.1f}%)")
    print(f"  ├── Spectral Radius:    {spectral_radius:.3f}")
    print(f"  ├── SR Ratio (vs norm): {sr_ratio:.2f}x")
    print(f"  ├── CCyB:               {latest_ccyb:.0f} bps")
    try:
        print(f"  └── Herding:            {latest_herding:.4f}")
    except:
        pass
    
    # Risk assessment
    print(f"\n  RISK ASSESSMENT:")
    if above_threshold and signal_z > 2:
        risk_level = "CRITICAL"
        print(f"  ⚠ CRITICAL: Signal above threshold at {signal_z:.1f}σ")
        print(f"    → Historical precedent: GFC-like conditions")
        print(f"    → Recommended action: Activate macro-prudential buffers")
    elif above_threshold:
        risk_level = "ELEVATED"
        print(f"  ⚠ ELEVATED: Signal above threshold at {signal_z:.1f}σ")
        print(f"    → Monitoring recommended; prepare contingency buffers")
    elif signal_z > 1:
        risk_level = "MODERATE"
        print(f"  ◇ MODERATE: Signal below threshold but elevated ({signal_z:.1f}σ)")
        print(f"    → Watchlist status; increased monitoring frequency")
    else:
        risk_level = "LOW"
        print(f"  ✓ LOW: Signal within normal range ({signal_z:.1f}σ)")
        print(f"    → Standard monitoring sufficient")
    
    # Forward-looking
    print(f"\n  FORWARD OUTLOOK:")
    if trend == "RISING" and above_threshold:
        print(f"  → Signal RISING while above threshold — highest concern")
        print(f"  → Based on MFLS 6Q lead-time record, monitor for structural stress")
    elif trend == "RISING":
        print(f"  → Signal RISING — approaching threshold from below")
        print(f"  → If trend continues, alarm may fire within 2-4 quarters")
    elif trend == "FALLING" and above_threshold:
        print(f"  → Signal FALLING from elevated level — potential resolution")
        print(f"  → Maintain buffers until signal drops below threshold for 2 consecutive Q")
    else:
        print(f"  → Signal FALLING from normal level — favourable dynamics")
    
    # Pipeline metrics summary
    print(f"\n  FULL PIPELINE METRICS:")
    print(f"  ├── AUROC:              {result.auroc:.4f}" if result.auroc else "  ├── AUROC: N/A")
    if result.auroc_ci:
        print(f"  ├── 95% Bootstrap CI:   [{result.auroc_ci[0]:.4f}, {result.auroc_ci[1]:.4f}]")
    print(f"  ├── GFC Lead:           {result.gfc_lead_quarters}Q" if result.gfc_lead_quarters else "  ├── GFC Lead: N/A")
    print(f"  ├── Hit Rate:           {result.hit_rate:.1%}" if result.hit_rate is not None else "  ├── Hit Rate: N/A")
    print(f"  ├── False Alarm Rate:   {result.false_alarm_rate:.1%}" if result.false_alarm_rate is not None else "  ├── False Alarm Rate: N/A")
    print(f"  └── Peak CCyB:          {result.peak_ccyb:.0f} bps" if result.peak_ccyb else "  └── Peak CCyB: N/A")
    
    # Save results
    output = {
        "run_date": datetime.datetime.now().isoformat(),
        "latest_data_quarter": str(latest_date),
        "panel_dimensions": {
            "T": int(panel.X_std.shape[0]),
            "N": int(panel.X_std.shape[1]),
            "d": int(panel.X_std.shape[2]),
        },
        "current_state": {
            "mfls_signal": float(current_signal),
            "alarm_threshold": float(result.threshold),
            "signal_z_score": float(signal_z),
            "above_threshold": bool(above_threshold),
            "trend_4q": trend,
            "trend_pct": float(trend_pct),
            "spectral_radius": float(spectral_radius),
            "sr_ratio_vs_normal": float(sr_ratio),
            "ccyb_bps": float(latest_ccyb),
            "risk_level": risk_level,
        },
        "pipeline_metrics": {
            "auroc": float(result.auroc) if result.auroc else None,
            "auroc_ci": [float(result.auroc_ci[0]), float(result.auroc_ci[1])] if result.auroc_ci else None,
            "gfc_lead_quarters": result.gfc_lead_quarters,
            "hit_rate": float(result.hit_rate) if result.hit_rate is not None else None,
            "false_alarm_rate": float(result.false_alarm_rate) if result.false_alarm_rate is not None else None,
            "peak_ccyb_bps": float(result.peak_ccyb) if result.peak_ccyb else None,
        },
        "signal_history_last_8q": [
            {"date": str(d), "signal": float(s)}
            for d, s in zip(panel.dates[-8:], result.signal[-8:])
        ],
    }
    
    output_path = Path(__file__).parent / "live_prediction_results.json"
    output_path.write_text(json.dumps(output, indent=2))
    print(f"\n  Results saved to: {output_path}")
    print("=" * 70)
    
    return output


if __name__ == "__main__":
    run_live_predictions()
