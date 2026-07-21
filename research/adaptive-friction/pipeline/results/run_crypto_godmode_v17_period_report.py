"""
Crypto Godmode v17 — Period Report
===================================

Builds comprehensive quarterly and year-on-year tables for the selected
champion backtest:

  strategy: be50_btc_sol
  K values: 6.0 and 6.5
  costs: realistic 6 bps round-trip

Outputs:
  - crypto_godmode_v17_period_report.json
  - crypto_godmode_v17_period_report.md
  - crypto_godmode_v17_equity_curves.csv
  - crypto_godmode_v17_quarterly.csv
  - crypto_godmode_v17_yearly.csv
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
warnings.filterwarnings("ignore")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, r"C:\amttp\research\adaptive-friction")

from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import KAPPA_A, W_TARGET_A1, build_b_aligned, build_w_star, calibrate, run_godmode_sweep
from run_crypto_godmode_v8_multiasset_shell import ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from simulate_master_strategy import DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, equity_metrics, simulate_combined
from simulate_v63_quadrant import CB_HALT, CB_RESUME, CB_WINDOW_DAYS
from test_daily_geometry_stop_tp_ohlc import get_channel_series
import run_crypto_godmode_v12_filter_innovate as v12


OUT_DIR_ = Path(OUT_DIR)
K_LIST = [6.0, 6.5]
REALISTIC_RT_BPS = 6.0
BAR = "=" * 112


def replay_unit(unit: pd.Series, k: float) -> dict:
    zero = pd.Series(np.zeros(len(unit)), index=unit.index)
    return simulate_combined(
        unit, zero,
        K_normal=k, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME,
        cb_window_days=CB_WINDOW_DAYS, use_cb=True,
    )


def _period_metrics(eq: pd.Series, period: str, k: float) -> list[dict]:
    rows = []
    grouped = eq.groupby(eq.index.to_period(period))
    for p, s in grouped:
        if s.empty:
            continue
        start_eq = float(s.iloc[0])
        end_eq = float(s.iloc[-1])
        profit = end_eq - start_eq
        ret = end_eq / start_eq - 1.0 if start_eq else np.nan
        dd = float((s / s.cummax() - 1.0).min())
        r = s.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        sharpe = float(r.mean() / (r.std() + 1e-12) * np.sqrt(365 * 24)) if len(r) > 3 else 0.0
        rows.append({
            "K": k,
            "period": str(p),
            "start": str(s.index[0]),
            "end": str(s.index[-1]),
            "start_eq": start_eq,
            "end_eq": end_eq,
            "profit": profit,
            "return_pct": 100.0 * ret,
            "maxdd_pct": 100.0 * dd,
            "sharpe": sharpe,
            "bars": int(len(s)),
        })
    return rows


def _fmt_money(x: float) -> str:
    return f"${x:,.2f}"


def _fmt_pct(x: float) -> str:
    return f"{x:+,.2f}%"


def _fmt_float(x: float) -> str:
    return f"{x:+.3f}"


def _markdown_table(df: pd.DataFrame, cols: list[str]) -> str:
    lines = []
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "|".join(["---"] * len(cols)) + "|")
    for _, r in df.iterrows():
        vals = []
        for c in cols:
            v = r[c]
            if c in {"start_eq", "end_eq", "profit", "final", "profit_total"}:
                vals.append(_fmt_money(float(v)))
            elif c in {"return_pct", "maxdd_pct", "cagr_pct", "total_return_pct"}:
                vals.append(_fmt_pct(float(v)))
            elif c in {"sharpe", "calmar"}:
                vals.append(_fmt_float(float(v)))
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def main():
    t0 = time.time()
    print(BAR)
    print("  CRYPTO GODMODE v17 — QUARTERLY + YEAR-ON-YEAR REPORT")
    print(BAR)

    print("\n[1] Rebuilding champion equity curves ...")
    df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask = np.asarray(df.index >= TEST_START)
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()

    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v17")
    log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_f, theta,
                                kappa=KAPPA_A, anneal=True, label="v17_anneal")

    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs = attach_q_hot(inputs_noq, inputs_q)
    sig_map = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}") for asset, _, _, idx in ASSETS}
    cfg = next(c for c in v12.VARIANTS if c["name"] == "be50_btc_sol")
    v12.RT_COST = REALISTIC_RT_BPS / 10_000.0
    unit_res = v12.run_variant(cfg, inputs, sig_map, log_ann)

    print("\n[2] Replaying K values and building period tables ...")
    test_ts = pd.Timestamp(TEST_START)
    curves = pd.DataFrame()
    summary_rows = []
    quarterly_rows = []
    yearly_rows = []

    for k in K_LIST:
        res = replay_unit(unit_res["unit"], k)
        eq = res["eq"][res["eq"].index >= test_ts].copy()
        curves[f"K{k:.1f}"] = eq
        m = equity_metrics(eq, f"K{k:.1f}")
        start = pd.Timestamp(m["start"])
        end = pd.Timestamp(m["end"])
        days = (end - start).total_seconds() / 86400.0
        years = days / 365.25
        summary_rows.append({
            "K": k,
            "start": str(start),
            "end": str(end),
            "days": days,
            "years": years,
            "final": float(m["final"]),
            "profit_total": float(m["profit"]),
            "total_return_pct": 100.0 * float(m["return_pct"]),
            "cagr_pct": 100.0 * float(m["cagr"]),
            "sharpe": float(m["sharpe"]),
            "maxdd_pct": 100.0 * float(m["maxdd"]),
            "calmar": float(m["calmar"]),
        })
        quarterly_rows.extend(_period_metrics(eq, "Q", k))
        yearly_rows.extend(_period_metrics(eq, "Y", k))
        print(f"  K={k:.1f}: years={years:.2f}, final=${m['final']:,.2f}, maxdd={m['maxdd']:+.2%}")

    summary = pd.DataFrame(summary_rows)
    quarterly = pd.DataFrame(quarterly_rows)
    yearly = pd.DataFrame(yearly_rows)

    curves.index.name = "timestamp"
    curves.to_csv(OUT_DIR_ / "crypto_godmode_v17_equity_curves.csv")
    quarterly.to_csv(OUT_DIR_ / "crypto_godmode_v17_quarterly.csv", index=False)
    yearly.to_csv(OUT_DIR_ / "crypto_godmode_v17_yearly.csv", index=False)

    payload = {
        "meta": {
            "version": "godmode_v17_period_report",
            "strategy": "be50_btc_sol",
            "rt_bps": REALISTIC_RT_BPS,
            "k_list": K_LIST,
            "theta": diag["theta"],
            "elapsed": time.time() - t0,
        },
        "summary": summary.to_dict(orient="records"),
        "quarterly": quarterly.to_dict(orient="records"),
        "yearly": yearly.to_dict(orient="records"),
        "counts": unit_res.get("counts", {}),
    }
    json_path = OUT_DIR_ / "crypto_godmode_v17_period_report.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=float)

    md_path = OUT_DIR_ / "crypto_godmode_v17_period_report.md"
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("# Crypto Godmode v17 Period Report\n\n")
        fh.write("Strategy: `be50_btc_sol`  \n")
        fh.write("Cost model: realistic 6 bps round-trip  \n")
        fh.write("OOS window: 2023-01-01 to 2026-04-29 20:00  \n")
        fh.write("Duration: 3.33 calendar years, spanning 2023, 2024, 2025, and partial 2026.  \n")
        fh.write("Active return years: 2023-2025; 2026 is partial and flat in this replay.\n\n")
        fh.write("## Overall Summary\n\n")
        fh.write(_markdown_table(summary, ["K", "start", "end", "years", "final", "profit_total", "total_return_pct", "cagr_pct", "sharpe", "maxdd_pct", "calmar"]))
        fh.write("\n\n## Year-on-Year Results\n\n")
        fh.write(_markdown_table(yearly, ["K", "period", "start_eq", "end_eq", "profit", "return_pct", "maxdd_pct", "sharpe"]))
        fh.write("\n\n## Quarterly Results\n\n")
        fh.write(_markdown_table(quarterly, ["K", "period", "start_eq", "end_eq", "profit", "return_pct", "maxdd_pct", "sharpe"]))
        fh.write("\n")

    print("\n[3] Saved report files:")
    for p in [json_path, md_path, OUT_DIR_ / "crypto_godmode_v17_equity_curves.csv",
              OUT_DIR_ / "crypto_godmode_v17_quarterly.csv", OUT_DIR_ / "crypto_godmode_v17_yearly.csv"]:
        print(f"  saved: {p}")
    print(f"\n  elapsed={time.time() - t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()