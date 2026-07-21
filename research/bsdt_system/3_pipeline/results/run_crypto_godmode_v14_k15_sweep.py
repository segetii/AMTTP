"""
Crypto Godmode v14 — Extended K Sweep to 15
===========================================

Extends the v13 leverage study from K<=5 to K<=15.

Focus variants:
  - be50_btc_sol : v12/v13 high-profit champion
  - persist6     : robust lower-DD alternative

Notes:
  The combined equity engine is nonlinear because the circuit breaker and
  drawdown throttle are path-dependent.  K results can be non-monotonic; this
  script reports best final equity, best Calmar, and best return under DD caps.
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
K_GRID = [round(x, 1) for x in np.arange(1.0, 15.0 + 0.001, 0.5)]
VARIANT_NAMES = ["be50_btc_sol", "persist6"]


def replay_unit(unit: pd.Series, k: float) -> dict:
    zero = pd.Series(np.zeros(len(unit)), index=unit.index)
    return simulate_combined(
        unit, zero,
        K_normal=k, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME,
        cb_window_days=CB_WINDOW_DAYS, use_cb=True,
    )


def print_rows(rows: list[dict], title: str, n: int | None = None):
    data = rows if n is None else rows[:n]
    print(f"\n  {title}")
    print(f"  {'Variant':<16} {'K':>5} {'Final$':>14} {'Return':>9} {'CAGR':>9} {'Sharpe':>8} "
          f"{'MaxDD':>8} {'Calmar':>8} {'Halt%':>7} {'Trips':>5}")
    print("  " + "─" * 108)
    for r in data:
        print(f"  {r['variant']:<16} {r['K']:>5.1f} {r['final']:>14,.2f} {r['return_pct']:>+8.1%} "
              f"{r['cagr']:>+8.2%} {r['sharpe']:>+8.3f} {r['maxdd']:>+7.2%} "
              f"{r['calmar']:>+8.3f} {r['pct_halted']:>6.1%} {r['n_trips']:>5}")


def main():
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v14 — EXTENDED K SWEEP TO 15")
    print(BAR)

    print("\n[1] Rebuilding canonical signal and execution inputs ...")
    df, has_sol = build_1h_df(start="2021-01-01", end="2026-05-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v14")
    test_mask = np.asarray(df.index >= TEST_START)
    log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_f, theta,
                                kappa=KAPPA_A, anneal=True, label="v14_anneal")
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs = attach_q_hot(inputs_noq, inputs_q)
    sig_map = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}") for asset, _, _, idx in ASSETS}

    cfgs = {c["name"]: c for c in v12.VARIANTS if c["name"] in VARIANT_NAMES}
    units = {}
    print("\n[2] Building unit-return books once per variant ...")
    for name in VARIANT_NAMES:
        print(f"  {name} ...")
        res = v12.run_variant(cfgs[name], inputs, sig_map, log_ann)
        units[name] = res["unit"]

    print("\n[3] Replaying K=1..15 ...")
    test_ts = pd.Timestamp(TEST_START)
    rows = []
    yearly = {}
    for name in VARIANT_NAMES:
        for k in K_GRID:
            res = replay_unit(units[name], k)
            eq_oos = res["eq"][res["eq"].index >= test_ts]
            m = equity_metrics(eq_oos, f"{name}_K{k}")
            row = dict(
                variant=name, K=float(k), final=m["final"], return_pct=m["return_pct"],
                cagr=m["cagr"], sharpe=m["sharpe"], maxdd=m["maxdd"], calmar=m["calmar"],
                pct_halted=res["pct_halted"], n_trips=res["n_trips"], avg_y=res["avg_y"],
            )
            rows.append(row)
            yearly[f"{name}_K{k}"] = period_table(eq_oos, "Y")

    print(f"\n{BAR}")
    print("  EXTENDED K RESULTS")
    print(BAR)
    for name in VARIANT_NAMES:
        print_rows([r for r in rows if r["variant"] == name], f"{name} K path")

    best_final = max(rows, key=lambda r: r["final"])
    best_calmar = max(rows, key=lambda r: r["calmar"])
    under25 = [r for r in rows if r["maxdd"] >= -0.25]
    under30 = [r for r in rows if r["maxdd"] >= -0.30]
    under40 = [r for r in rows if r["maxdd"] >= -0.40]
    best_under25 = max(under25, key=lambda r: r["final"], default=best_calmar)
    best_under30 = max(under30, key=lambda r: r["final"], default=best_calmar)
    best_under40 = max(under40, key=lambda r: r["final"], default=best_calmar)
    print_rows(sorted(rows, key=lambda r: r["final"], reverse=True), "Top by final equity", n=15)
    print_rows(sorted(rows, key=lambda r: r["calmar"], reverse=True), "Top by Calmar", n=15)

    print("\n  Selected:")
    for tag, r in [("best_final", best_final), ("best_calmar", best_calmar),
                   ("best_under_25dd", best_under25), ("best_under_30dd", best_under30),
                   ("best_under_40dd", best_under40)]:
        print(f"    {tag:<16}: {r['variant']} K={r['K']:.1f} final=${r['final']:,.2f} "
              f"return={r['return_pct']:+.1%} CAGR={r['cagr']:+.2%} Sharpe={r['sharpe']:+.3f} "
              f"MaxDD={r['maxdd']:+.2%} Calmar={r['calmar']:+.3f}")

    print("\n  Yearly for best_under_25dd:")
    key = f"{best_under25['variant']}_K{best_under25['K']}"
    for row in yearly[key]:
        print(f"    {row['period']}: start=${row['start_eq']:,.2f} end=${row['end_eq']:,.2f} "
              f"return={row['return_pct']:+.1%} sharpe={row['sharpe']:+.3f} maxdd={row['maxdd']:+.1%}")

    payload = dict(
        meta=dict(version="godmode_v14_k15_sweep", k_grid=K_GRID, variants=VARIANT_NAMES,
                  theta=diag["theta"], elapsed=time.time() - t0),
        rows=rows,
        selected=dict(best_final=best_final, best_calmar=best_calmar,
                      best_under_25dd=best_under25, best_under_30dd=best_under30,
                      best_under_40dd=best_under40),
        yearly=yearly,
    )
    out = OUT_DIR_ / "crypto_godmode_v14_k15_sweep.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=float)
    print(f"\n  Saved → {out}")
    print(f"  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()