from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import sys
sys.path.insert(0, str(Path(r"c:\amttp\research\adaptive-friction\pipeline\results")))
import run_crypto_steady_incremental_v1 as base


def score_row(r: dict) -> float:
    # Steady/incremental objective:
    # prioritize month-level consistency and drawdown control, then growth.
    return (
        4.0 * r["pos_month_rate"]
        + 5.0 * r["cagr"]
        + 1.0 * r["calmar"]
        - 1.5 * abs(r["maxdd"])
    )


def run_one(df: pd.DataFrame, tg: float, mg: float, tv: float, tc: float) -> tuple[dict, pd.Series, pd.DataFrame]:
    eq, det = base.simulate(
        df,
        tc_bps=tc,
        target_gross=tg,
        min_gross=mg,
        target_vol_annual=tv,
    )
    met = base.equity_metrics(eq)
    met["target_gross"] = float(tg)
    met["min_gross"] = float(mg)
    met["target_vol_annual"] = float(tv)
    met["tc_bps"] = float(tc)
    met["avg_gross"] = float(det["gross"].mean())
    met["avg_turnover"] = float(det["turnover"].mean())
    met["pos_month_rate"] = float((det["ret"].resample("ME").sum() > 0).mean())
    met["score"] = float(score_row(met))
    return met, eq, det


def main() -> None:
    in_path = Path(r"c:\amttp\data\processed\unified_crypto_1h_20210101_to_20260601.parquet")
    out_dir = Path(r"c:\amttp\research\adaptive-friction\pipeline\results\steady_incremental_v2")
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(in_path).sort_index()
    # Fast calibration window for practical turnaround (recent regime only)
    df = df[df.index >= pd.Timestamp("2023-01-01")]

    # Focused, fast grid: 6 runs.
    target_gross_vals = [0.90, 1.00, 1.10]
    min_gross_vals = [0.45]
    target_vol_vals = [0.10, 0.14]
    tc_vals = [2.0]

    rows = []
    traces = []

    for tg in target_gross_vals:
        for mg in min_gross_vals:
            for tv in target_vol_vals:
                for tc in tc_vals:
                    met, eq, det = run_one(df, tg, mg, tv, tc)
                    rows.append(met)
                    traces.append((met, eq, det))

    sweep = pd.DataFrame(rows).sort_values("score", ascending=False)
    sweep_path = out_dir / "sweep_results.csv"
    sweep.to_csv(sweep_path, index=False)

    best = sweep.iloc[0].to_dict()
    best_path = out_dir / "best_config.json"
    with open(best_path, "w", encoding="utf-8") as f:
        json.dump(best, f, indent=2)

    # Save best run equity/details
    best_match = None
    for met, eq, det in traces:
        if (
            met["target_gross"] == best["target_gross"]
            and met["min_gross"] == best["min_gross"]
            and met["target_vol_annual"] == best["target_vol_annual"]
            and met["tc_bps"] == best["tc_bps"]
        ):
            best_match = (eq, det)
            break

    if best_match is None:
        raise RuntimeError("Best trace not found")

    eq_best, det_best = best_match
    eq_best.to_csv(out_dir / "equity_curve_best.csv", header=True)
    det_best.to_csv(out_dir / "hourly_details_best.csv")

    print("Top candidates:")
    cols = [
        "target_gross", "min_gross", "target_vol_annual", "tc_bps",
        "final", "cagr", "sharpe", "maxdd", "calmar", "pos_month_rate",
        "avg_gross", "avg_turnover", "score",
    ]
    print(sweep[cols].head(10).to_string(index=False))

    print("\nSaved:", sweep_path)
    print("Saved:", best_path)
    print("Saved:", out_dir / "equity_curve_best.csv")
    print("Saved:", out_dir / "hourly_details_best.csv")


if __name__ == "__main__":
    main()
