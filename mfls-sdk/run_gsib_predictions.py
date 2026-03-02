"""
MFLS G-SIB Live Predictions — Fetch current World Bank + ECB data for global banks.
"""
import sys
import json
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from mfls.engine import MFLSEngine


def run_gsib_predictions():
    print("=" * 70)
    print("MFLS G-SIB LIVE PREDICTION — GLOBAL SYSTEMIC RISK")
    print(f"Run date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    engine = MFLSEngine(
        normal_start="2005-01-01",
        normal_end="2006-12-31",
        n_boot=200,
        boot_block_len=4,
        threshold_pctl=75.0,
    )

    print("\n[1/3] Loading G-SIB panel (World Bank + ECB + FDIC)...")
    try:
        panel = engine.load_gsib_panel(
            start="2005-01-01",
            end="2025-12-31",
            force_refresh=True,
            verbose=True,
        )
        print(f"      Panel: T={panel.X_std.shape[0]}, N={panel.X_std.shape[1]}, d={panel.X_std.shape[2]}")
        print(f"      Date range: {panel.dates[0]} to {panel.dates[-1]}")
    except Exception as e:
        print(f"      G-SIB load error: {e}")
        import traceback; traceback.print_exc()
        return

    print("\n[2/3] Running MFLS pipeline...")
    try:
        result = engine.fit_and_score(panel, verbose=True)
    except Exception as e:
        print(f"      Pipeline error: {e}")
        import traceback; traceback.print_exc()
        return

    print("\n[3/3] G-SIB SYSTEMIC RISK ASSESSMENT")
    print("=" * 70)

    latest_date = panel.dates[-1]
    current_signal = result.signal[-1]
    signal_z = (current_signal - np.mean(result.signal)) / max(np.std(result.signal), 1e-6)
    above = current_signal > result.threshold

    recent = result.signal[-4:]
    trend = "RISING" if recent[-1] > recent[0] else "FALLING"

    print(f"\n  G-SIB state ({latest_date}):")
    print(f"  ├── MFLS Signal:     {current_signal:.4f}")
    print(f"  ├── Threshold:       {result.threshold:.4f}")
    print(f"  ├── Z-score:         {signal_z:+.2f}σ")
    print(f"  ├── Above threshold: {'YES' if above else 'NO'}")
    print(f"  ├── Trend (4Q):      {trend}")
    print(f"  ├── AUROC:           {result.auroc:.4f}" if result.auroc else "  ├── AUROC: N/A")
    print(f"  └── Peak CCyB:       {result.peak_ccyb:.0f} bps" if result.peak_ccyb else "  └── Peak CCyB: N/A")

    # Save
    output = {
        "run_date": datetime.datetime.now().isoformat(),
        "panel": f"T={panel.X_std.shape[0]}, N={panel.X_std.shape[1]}, d={panel.X_std.shape[2]}",
        "latest_date": str(latest_date),
        "current_signal": float(current_signal),
        "threshold": float(result.threshold),
        "z_score": float(signal_z),
        "above_threshold": bool(above),
        "auroc": float(result.auroc) if result.auroc else None,
        "auroc_ci": [float(result.auroc_ci[0]), float(result.auroc_ci[1])] if result.auroc_ci else None,
    }
    out_path = Path(__file__).parent / "gsib_prediction_results.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\n  Saved to: {out_path}")
    print("=" * 70)

    return output


if __name__ == "__main__":
    run_gsib_predictions()
