"""
Crypto Godmode v15 — Fee / Slippage Net Backtest
================================================

Backtests the selected v14 champion under explicit fee + slippage assumptions.

Champion logic:
  - v12 `be50_btc_sol`
  - BTC/ETH/SOL futures OHLC execution
  - abs(ZE7) >= 0.15
  - 1/3 allocation per asset
  - BTC/SOL breakeven stop after 50% TP progress
  - shared 8%/1%/180d circuit breaker
  - K in {6.0, 6.5}

Cost handling:
  `simulate_unit_breakeven` subtracts `RT_COST` once on trade exit.
  Here RT_COST is set to an explicit round-trip bps value per completed trade.

Scenarios:
  - zero_cost:       0 bps round trip
  - current_2bp_rt:  2 bps round trip (legacy research default)
  - maker_4bp_rt:    4 bps round trip
  - realistic_6bp_rt: 6 bps round trip (2bp fee + 1bp slippage per side)
  - taker_10bp_rt:  10 bps round trip
  - stress_20bp_rt: 20 bps round trip
"""
from __future__ import annotations

import os
import sys
import json
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
from run_crypto_godmode_v1 import KAPPA_A, W_TARGET_A1, build_w_star, build_b_aligned, calibrate, run_godmode_sweep
from simulate_master_strategy import DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, simulate_combined, equity_metrics, period_table
from simulate_v63_quadrant import CB_HALT, CB_RESUME, CB_WINDOW_DAYS
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from run_crypto_godmode_v8_multiasset_shell import ASSETS, fetch_futures_ohlcv_symbol, build_asset_inputs
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
import run_crypto_godmode_v12_filter_innovate as v12


OUT_DIR_ = Path(OUT_DIR)
BAR = "=" * 112
K_GRID = [6.0, 6.5]
SCENARIOS = [
    dict(name="zero_cost", rt_bps=0.0),
    dict(name="current_2bp_rt", rt_bps=2.0),
    dict(name="maker_4bp_rt", rt_bps=4.0),
    dict(name="realistic_6bp_rt", rt_bps=6.0),
    dict(name="taker_10bp_rt", rt_bps=10.0),
    dict(name="stress_20bp_rt", rt_bps=20.0),
]


def replay_unit(unit: pd.Series, k: float) -> dict:
    zero = pd.Series(np.zeros(len(unit)), index=unit.index)
    return simulate_combined(
        unit, zero,
        K_normal=k, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME,
        cb_window_days=CB_WINDOW_DAYS, use_cb=True,
    )


def print_table(rows: list[dict]):
    print(f"\n  {'Scenario':<18} {'RT bps':>7} {'K':>4} {'Final$':>13} {'Profit$':>13} "
          f"{'Return':>9} {'CAGR':>9} {'Sharpe':>8} {'MaxDD':>8} {'Calmar':>8} {'Halt%':>7}")
    print("  " + "─" * 112)
    for r in rows:
        print(f"  {r['scenario']:<18} {r['rt_bps']:>7.1f} {r['K']:>4.1f} {r['final']:>13,.2f} "
              f"{r['profit']:>13,.2f} {r['return_pct']:>+8.1%} {r['cagr']:>+8.2%} "
              f"{r['sharpe']:>+8.3f} {r['maxdd']:>+7.2%} {r['calmar']:>+8.3f} {r['pct_halted']:>6.1%}")


def main():
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v15 — FEE / SLIPPAGE NET BACKTEST")
    print(BAR)

    print("\n[1] Rebuilding canonical signal and execution inputs ...")
    df, has_sol = build_1h_df(start="2021-01-01", end="2026-05-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask = np.asarray(df.index >= TEST_START)
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v15")
    log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_f, theta,
                                kappa=KAPPA_A, anneal=True, label="v15_anneal")
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs = attach_q_hot(inputs_noq, inputs_q)
    sig_map = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}") for asset, _, _, idx in ASSETS}
    cfg = next(c for c in v12.VARIANTS if c["name"] == "be50_btc_sol")

    print("\n[2] Running cost scenarios ...")
    test_ts = pd.Timestamp(TEST_START)
    rows = []
    yearly = {}
    counts = {}
    for sc in SCENARIOS:
        rt_cost = float(sc["rt_bps"]) / 10_000.0
        v12.RT_COST = rt_cost
        print(f"  {sc['name']}  RT={sc['rt_bps']:.1f} bps ...")
        unit_res = v12.run_variant(cfg, inputs, sig_map, log_ann)
        counts[sc["name"]] = unit_res["counts"]
        for k in K_GRID:
            eq_res = replay_unit(unit_res["unit"], k)
            eq_oos = eq_res["eq"][eq_res["eq"].index >= test_ts]
            m = equity_metrics(eq_oos, f"{sc['name']}_K{k}")
            row = dict(
                scenario=sc["name"], rt_bps=float(sc["rt_bps"]), K=float(k),
                final=m["final"], profit=m["profit"], return_pct=m["return_pct"],
                cagr=m["cagr"], sharpe=m["sharpe"], maxdd=m["maxdd"], calmar=m["calmar"],
                pct_halted=eq_res["pct_halted"], n_trips=eq_res["n_trips"], avg_y=eq_res["avg_y"],
                entries=unit_res["counts"].get("entries", 0),
                exits=unit_res["counts"].get("tp", 0) + unit_res["counts"].get("stop", 0) +
                      unit_res["counts"].get("trail_exit", 0) + unit_res["counts"].get("breakeven_exit", 0) +
                      unit_res["counts"].get("signal_exit", 0),
            )
            rows.append(row)
            yearly[f"{sc['name']}_K{k}"] = period_table(eq_oos, "Y")

    print(f"\n{BAR}")
    print("  NET BACKTEST RESULTS AFTER FEES / SLIPPAGE")
    print(BAR)
    print_table(rows)

    realistic = [r for r in rows if r["scenario"] == "realistic_6bp_rt"]
    best_realistic = max(realistic, key=lambda r: r["final"])
    best_under30 = max([r for r in rows if r["maxdd"] >= -0.30], key=lambda r: r["final"])
    best_all = max(rows, key=lambda r: r["final"])

    print("\n  Selected:")
    for tag, r in [("best_realistic_6bp", best_realistic), ("best_under_30dd", best_under30), ("best_all", best_all)]:
        print(f"    {tag:<20}: {r['scenario']} K={r['K']:.1f} final=${r['final']:,.2f} "
              f"profit=${r['profit']:,.2f} CAGR={r['cagr']:+.2%} Sharpe={r['sharpe']:+.3f} "
              f"MaxDD={r['maxdd']:+.2%} Calmar={r['calmar']:+.3f}")

    print("\n  Yearly for realistic_6bp best:")
    key = f"{best_realistic['scenario']}_K{best_realistic['K']}"
    for row in yearly[key]:
        print(f"    {row['period']}: start=${row['start_eq']:,.2f} end=${row['end_eq']:,.2f} "
              f"return={row['return_pct']:+.1%} sharpe={row['sharpe']:+.3f} maxdd={row['maxdd']:+.1%}")

    payload = dict(
        meta=dict(version="godmode_v15_cost_backtest", scenarios=SCENARIOS, k_grid=K_GRID,
                  theta=diag["theta"], elapsed=time.time() - t0),
        rows=rows,
        selected=dict(best_realistic_6bp=best_realistic, best_under_30dd=best_under30, best_all=best_all),
        counts=counts,
        yearly=yearly,
    )
    out = OUT_DIR_ / "crypto_godmode_v15_cost_backtest.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=float)
    print(f"\n  Saved → {out}")
    print(f"  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()