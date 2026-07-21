from __future__ import annotations

import itertools
import json
from pathlib import Path

import pandas as pd

import sys
sys.path.insert(0, str(Path(r"c:\amttp\research\adaptive-friction\pipeline\results")))
import run_crypto_steady_incremental_v1 as m


def main() -> None:
    in_path = Path(r"c:\amttp\data\processed\unified_crypto_1h_20210101_to_20260601.parquet")
    out_dir = Path(r"c:\amttp\research\adaptive-friction\pipeline\results\steady_incremental_v1")
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(in_path).sort_index()

    grid = list(itertools.product(
        [0.90, 1.10],         # target_gross
        [0.45, 0.60],         # min_gross
        [0.10, 0.14],         # target_vol_annual
        [2.0, 4.0],           # tc_bps
    ))

    rows = []
    for tg, mg, tv, tc in grid:
        eq, det = m.simulate(
            df,
            tc_bps=tc,
            target_gross=tg,
            min_gross=mg,
            target_vol_annual=tv,
        )
        met = m.equity_metrics(eq)
        met["avg_gross"] = float(det["gross"].mean())
        met["avg_turnover"] = float(det["turnover"].mean())
        met["pos_month_rate"] = float((det["ret"].resample("ME").sum() > 0).mean())
        met["target_gross"] = float(tg)
        met["min_gross"] = float(mg)
        met["target_vol_annual"] = float(tv)
        met["tc_bps"] = float(tc)

        # Score favors steady month-level consistency + positive compounding,
        # while penalizing deep drawdowns.
        met["score"] = (
            3.0 * met["pos_month_rate"]
            + 6.0 * met["cagr"]
            + 1.0 * met["calmar"]
            - 1.2 * abs(met["maxdd"])
        )
        rows.append(met)

    out = pd.DataFrame(rows).sort_values("score", ascending=False)
    out_csv = out_dir / "focused_sweep.csv"
    out.to_csv(out_csv, index=False)

    best = out.iloc[0].to_dict()
    best_json = out_dir / "best_steady_config.json"
    with open(best_json, "w", encoding="utf-8") as f:
        json.dump(best, f, indent=2)

    show_cols = [
        "target_gross", "min_gross", "target_vol_annual", "tc_bps",
        "final", "cagr", "sharpe", "maxdd", "calmar", "pos_month_rate",
        "avg_gross", "avg_turnover", "score",
    ]
    print(out[show_cols].head(10).to_string(index=False))
    print(f"\nSaved: {out_csv}")
    print(f"Saved: {best_json}")


if __name__ == "__main__":
    main()
