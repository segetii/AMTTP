"""
Crypto Godmode v13 — K Sweep up to 5
====================================

Takes the v12 high-profit / low-DD champion and sweeps normal-sleeve leverage
K from 1 to 5.

Variants tested:
  - be50_btc_sol   : v12 champion, highest return / best Calmar in v12
  - persist6       : lower-DD robust alternative
  - v11_sol_halve  : lowest-DD prior fix
  - base_v9        : reference

The per-asset trade unit returns are built once per variant, then replayed
through the shared circuit-breaker equity engine for each K.
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
K_GRID = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
VARIANT_NAMES = ["be50_btc_sol", "persist6", "v11_sol_halve", "base_v9"]


def replay_unit(unit: pd.Series, k: float) -> dict:
    zero = pd.Series(np.zeros(len(unit)), index=unit.index)
    return simulate_combined(
        unit, zero,
        K_normal=k, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME,
        cb_window_days=CB_WINDOW_DAYS, use_cb=True,
    )


def print_table(rows: list[dict], title: str):
    print(f"\n  {title}")
    print(f"  {'Variant':<18} {'K':>4} {'Final$':>11} {'CAGR':>9} {'Sharpe':>8} {'MaxDD':>8} {'Calmar':>8} {'Halt%':>7} {'Trips':>5}")
    print("  " + "─" * 96)
    for r in rows:
        print(f"  {r['variant']:<18} {r['K']:>4.1f} {r['final']:>11,.2f} {r['cagr']:>+8.2%} "
              f"{r['sharpe']:>+8.3f} {r['maxdd']:>+7.2%} {r['calmar']:>+8.3f} {r['pct_halted']:>6.1%} {r['n_trips']:>5}")


def main():
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v13 — K SWEEP UP TO 5")
    print(BAR)

    print("\n[1] Rebuilding canonical signal and execution inputs ...")
    df, has_sol = build_1h_df(start="2021-01-01", end="2026-05-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask = np.asarray(df.index >= TEST_START)
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v13")
    log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_f, theta,
                                kappa=KAPPA_A, anneal=True, label="v13_anneal")
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs = attach_q_hot(inputs_noq, inputs_q)
    sig_map = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}") for asset, _, _, idx in ASSETS}

    cfgs = {c["name"]: c for c in v12.VARIANTS if c["name"] in VARIANT_NAMES}
    units = {}
    counts = {}
    print("\n[2] Building unit-return books once per variant ...")
    for name in VARIANT_NAMES:
        print(f"  {name} ...")
        # run_variant uses K only in the equity replay; the returned unit book is K-independent.
        res = v12.run_variant(cfgs[name], inputs, sig_map, log_ann)
        units[name] = res["unit"]
        counts[name] = res["counts"]

    print("\n[3] Replaying K grid ...")
    test_ts = pd.Timestamp(TEST_START)
    rows = []
    yearly = {}
    for name in VARIANT_NAMES:
        for k in K_GRID:
            res = replay_unit(units[name], k)
            eq_oos = res["eq"][res["eq"].index >= test_ts]
            m = equity_metrics(eq_oos, f"{name}_K{k}")
            row = dict(
                variant=name, K=k, final=m["final"], return_pct=m["return_pct"], cagr=m["cagr"],
                sharpe=m["sharpe"], maxdd=m["maxdd"], calmar=m["calmar"],
                pct_halted=res["pct_halted"], n_trips=res["n_trips"], avg_y=res["avg_y"],
                counts=counts[name],
            )
            rows.append(row)
            yearly[f"{name}_K{k}"] = period_table(eq_oos, "Y")

    print(f"\n{BAR}")
    print("  K SWEEP RESULTS")
    print(BAR)
    print_table(sorted(rows, key=lambda r: (r["variant"], r["K"])), "All K results")

    best_calmar = max(rows, key=lambda r: r["calmar"])
    under25 = [r for r in rows if r["maxdd"] >= -0.25]
    under30 = [r for r in rows if r["maxdd"] >= -0.30]
    best_under25 = max(under25, key=lambda r: r["final"], default=best_calmar)
    best_under30 = max(under30, key=lambda r: r["final"], default=best_calmar)
    best_final = max(rows, key=lambda r: r["final"])

    print_table(sorted(rows, key=lambda r: r["calmar"], reverse=True)[:12], "Top by Calmar")
    print("\n  Selected:")
    for tag, r in [("best_calmar", best_calmar), ("best_under_25dd", best_under25),
                   ("best_under_30dd", best_under30), ("best_final", best_final)]:
        print(f"    {tag:<16}: {r['variant']} K={r['K']:.1f} final=${r['final']:,.2f} "
              f"CAGR={r['cagr']:+.2%} Sharpe={r['sharpe']:+.3f} MaxDD={r['maxdd']:+.2%} Calmar={r['calmar']:+.3f}")

    print("\n  Yearly for best_under_25dd:")
    key = f"{best_under25['variant']}_K{best_under25['K']}"
    for row in yearly[key]:
        print(f"    {row['period']}: start=${row['start_eq']:,.2f} end=${row['end_eq']:,.2f} "
              f"return={row['return_pct']:+.1%} sharpe={row['sharpe']:+.3f} maxdd={row['maxdd']:+.1%}")

    payload = dict(
        meta=dict(version="godmode_v13_k_sweep", k_grid=K_GRID, variants=VARIANT_NAMES,
                  theta=diag["theta"], elapsed=time.time() - t0),
        rows=rows,
        selected=dict(best_calmar=best_calmar, best_under_25dd=best_under25,
                      best_under_30dd=best_under30, best_final=best_final),
        yearly=yearly,
    )
    out = OUT_DIR_ / "crypto_godmode_v13_k_sweep.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=float)
    print(f"\n  Saved → {out}")
    print(f"  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()