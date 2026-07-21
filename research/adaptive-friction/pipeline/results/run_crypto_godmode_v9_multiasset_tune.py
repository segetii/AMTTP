"""
Crypto Godmode v9 — Multi-Asset ZE7 / Quadrant / Allocation Tuner
=================================================================

v8 restored the old multi-asset execution structure and found a strong stable
candidate (`star_eq_CB`).  v9 tunes the parts that were inherited unchanged from
the ETH-era engine:

  - ZE7 minimum-force threshold
  - GH/TH quadrant size multiplier
  - multi-asset allocation scale

Important implementation detail:
  Per-asset trade returns are linear in position size, so v9 simulates each
  (ZE7, quadrant multiplier) unit-return book once at full per-asset sizing and
  then scales the summed book for allocation sweeps before applying the shared
  circuit breaker.  This keeps the sweep fast enough while preserving the
  nonlinear CB/equity path at the combined-book level.
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
from run_crypto_canonical_v4 import _stats, print_yoy_table
from run_crypto_godmode_v1 import (
    KAPPA_A,
    W_TARGET_A1,
    build_w_star,
    build_b_aligned,
    calibrate,
    run_godmode_sweep,
)
from simulate_master_strategy import (
    DYN_K,
    DYN_DD_SOFT,
    DYN_DD_STOP,
    DYN_Y_FLOOR,
    simulate_combined,
    equity_metrics,
    period_table,
)
from simulate_v63_quadrant import CB_HALT, CB_RESUME, CB_WINDOW_DAYS
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from run_crypto_godmode_v7_exec_shell import build_godmode_exec_inputs, run_exec_variant
from run_crypto_godmode_v8_multiasset_shell import ASSETS, fetch_futures_ohlcv_symbol, build_asset_inputs


OUT_DIR_ = Path(OUT_DIR)
BAR = "=" * 116

ZE7_GRID = [0.00, 0.025, 0.05, 0.075, 0.10, 0.15]
QBOOST_GRID = [0.75, 1.00, 1.05, 1.10, 1.25]
ALLOC_GRID = [1.0 / 3.0, 0.40, 0.50, 2.0 / 3.0, 1.00]


def _copy_with_qboost(p: dict, qboost: float) -> dict:
    """Apply a custom GH/TH multiplier to a no-quadrant input dict."""
    q_hot = np.asarray(p.get("q_hot", np.zeros(len(p["psi_y"]), dtype=bool)), dtype=bool)
    out = dict(p)
    out["psi_y"] = np.asarray(p["psi_y"], dtype=float) * np.where(q_hot, qboost, 1.0)
    out["qboost"] = qboost
    out["q_hot_pct"] = float(q_hot.mean())
    return out


def attach_q_hot(inputs_noq: dict[str, dict], inputs_q: dict[str, dict]) -> dict[str, dict]:
    """Mark GH/TH-hot bars using the old helper but keep base no-Q sizing."""
    out: dict[str, dict] = {}
    for asset, p in inputs_noq.items():
        q = inputs_q[asset]
        x = dict(p)
        x["q_hot"] = np.asarray(q["q_mult"], dtype=float) > 1.0
        out[asset] = x
    return out


def simulate_unit_book(inputs_noq_hot: dict[str, dict], ze7_min: float, qboost: float) -> dict:
    """Simulate per-asset unit returns once for a given ZE7 and Q multiplier."""
    per_asset: dict[str, dict] = {}
    unit_sum: pd.Series | None = None

    for asset, p0 in inputs_noq_hot.items():
        p = _copy_with_qboost(p0, qboost)
        res = run_exec_variant(f"unit_{asset}_z{ze7_min}_q{qboost}", p, ze7_min=ze7_min, use_cb=False)
        unit = res["unit"]
        unit_sum = unit if unit_sum is None else unit_sum.add(unit, fill_value=0.0)
        per_asset[asset] = {
            "counts": res["counts"],
            "q_hot_pct": p["q_hot_pct"],
            "avg_psi": float(np.mean(p["psi_y"])),
            "unit_stats_test": _stats(unit.loc[unit.index >= pd.Timestamp(TEST_START)]),
        }

    assert unit_sum is not None
    counts = {
        "entries": int(sum(v["counts"].get("entries", 0) for v in per_asset.values())),
        "vetoed_force": int(sum(v["counts"].get("vetoed_force", 0) for v in per_asset.values())),
        "tp": int(sum(v["counts"].get("tp", 0) for v in per_asset.values())),
        "stop": int(sum(v["counts"].get("stop", 0) for v in per_asset.values())),
        "trail_exit": int(sum(v["counts"].get("trail_exit", 0) for v in per_asset.values())),
        "signal_exit": int(sum(v["counts"].get("signal_exit", 0) for v in per_asset.values())),
    }
    return dict(unit=unit_sum.sort_index().fillna(0.0), per_asset=per_asset, counts=counts)


def run_cb_scaled(unit_sum: pd.Series, alloc: float) -> dict:
    unit = unit_sum * alloc
    zero = pd.Series(np.zeros(len(unit)), index=unit.index)
    return simulate_combined(
        unit, zero,
        K_normal=DYN_K, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME,
        cb_window_days=CB_WINDOW_DAYS, use_cb=True,
    )


def print_top(rows: list[dict], key: str, title: str, n: int = 12):
    print(f"\n  {title}")
    print(f"  {'variant':<26} {'Final$':>11} {'CAGR':>9} {'Sharpe':>8} {'MaxDD':>8} "
          f"{'Calmar':>8} {'ZE7':>6} {'Q':>5} {'Alloc':>7} {'Entries':>8} {'Veto':>7} {'Halt%':>7}")
    print(f"  {'─'*116}")
    for r in sorted(rows, key=lambda x: x[key], reverse=True)[:n]:
        print(f"  {r['name']:<26} {r['final']:>11,.2f} {r['cagr']:>+8.2%} {r['sharpe']:>+8.3f} "
              f"{r['maxdd']:>+7.2%} {r['calmar']:>+8.3f} {r['ze7']:>6.3f} {r['qboost']:>5.2f} "
              f"{r['alloc']:>7.3f} {r['entries']:>8} {r['vetoed_force']:>7} {r['pct_halted']:>6.1%}")


def main():
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v9 — MULTI-ASSET ZE7 / QUADRANT / ALLOCATION TUNER")
    print(BAR)

    print("\n[1] Loading data and channels ...")
    df, has_sol = build_1h_df(start="2021-01-01", end="2026-05-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask = np.asarray(df.index >= TEST_START)
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()
    print(f"  spot bars={len(df):,} train={train_mask.sum():,} test={test_mask.sum():,} SOL={has_sol}")

    print("\n[2] Building Godmode v_anneal signal once ...")
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v9")
    log_ann = run_godmode_sweep(
        df, train_mask, test_mask,
        w_star, b_aligned, Sigma_f, theta,
        kappa=KAPPA_A, anneal=True, label="v9_anneal",
    )

    print("\n[3] Building base w_star per-asset inputs ...")
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs_hot = attach_q_hot(inputs_noq, inputs_q)
    for asset, p in inputs_hot.items():
        print(f"  {asset.upper():<3}: active={p['active_pct']:.1%} daily_active={p['daily_active_pct']:.1%} "
              f"q_hot={np.mean(p['q_hot']):.1%} avg_psi={p['avg_psi']:.3f}")

    print("\n[4] Sweeping ZE7 × Q multiplier × allocation ...")
    test_ts = pd.Timestamp(TEST_START)
    rows: list[dict] = []
    detail: dict[str, dict] = {}
    total_books = len(ZE7_GRID) * len(QBOOST_GRID)
    book_i = 0
    for ze7 in ZE7_GRID:
        for qb in QBOOST_GRID:
            book_i += 1
            print(f"  book {book_i:>2}/{total_books}: ZE7={ze7:.3f} Q={qb:.2f}")
            book = simulate_unit_book(inputs_hot, ze7_min=ze7, qboost=qb)
            for alloc in ALLOC_GRID:
                res = run_cb_scaled(book["unit"], alloc)
                eq_oos = res["eq"][res["eq"].index >= test_ts]
                m = equity_metrics(eq_oos)
                name = f"z{ze7:.3f}_q{qb:.2f}_a{alloc:.3f}"
                row = dict(
                    name=name, ze7=ze7, qboost=qb, alloc=alloc,
                    final=m["final"], return_pct=m["return_pct"], cagr=m["cagr"],
                    sharpe=m["sharpe"], maxdd=m["maxdd"], calmar=m["calmar"],
                    pct_halted=res["pct_halted"], n_trips=res["n_trips"], avg_y=res["avg_y"],
                    **book["counts"],
                )
                rows.append(row)
                detail[name] = {
                    "row": row,
                    "full": equity_metrics(res["eq"], name),
                    "test": m,
                    "yearly_test": period_table(eq_oos, "Y"),
                    "per_asset": book["per_asset"],
                }

    print(f"\n{BAR}")
    print("  GODMODE v9 TUNING RESULTS")
    print(BAR)
    print_top(rows, "calmar", "Top by Calmar")
    print_top(rows, "final", "Top by Final Equity")
    print_top([r for r in rows if r["maxdd"] >= -0.25], "final", "Top with MaxDD no worse than -25%")

    best_calmar = max(rows, key=lambda r: r["calmar"])
    best_return_25 = max([r for r in rows if r["maxdd"] >= -0.25], key=lambda r: r["final"], default=best_calmar)
    best_final = max(rows, key=lambda r: r["final"])

    print("\n  Selected champions:")
    for tag, row in [("best_calmar", best_calmar), ("best_under_25dd", best_return_25), ("best_final", best_final)]:
        print(f"    {tag:<16}: {row['name']} final=${row['final']:,.2f} CAGR={row['cagr']:+.2%} "
              f"Sharpe={row['sharpe']:+.3f} MaxDD={row['maxdd']:+.2%} Calmar={row['calmar']:+.3f}")

    print("\n  Underlying continuous v_anneal reference:")
    st = _stats(log_ann["pnl"].iloc[test_mask])
    print(f"    Sharpe={st['sharpe']:+.3f} MaxDD={st['max_dd']:+.2%} CAGR={st['cagr']:+.2%} $100→${st['final']:.2f}")
    print_yoy_table("v9_underlying_v_anneal", log_ann["pnl"].iloc[test_mask], [1, 2, 3, 5])

    payload = {
        "meta": {
            "version": "godmode_v9_multiasset_tune",
            "ze7_grid": ZE7_GRID,
            "qboost_grid": QBOOST_GRID,
            "alloc_grid": ALLOC_GRID,
            "W_TARGET_A1": W_TARGET_A1,
            "KAPPA_A": KAPPA_A,
            "theta": diag["theta"],
            "cb_halt": CB_HALT,
            "cb_resume": CB_RESUME,
            "cb_window_days": CB_WINDOW_DAYS,
            "DYN_K": DYN_K,
        },
        "continuous_reference": _stats(log_ann["pnl"].iloc[test_mask]),
        "rows": rows,
        "champions": {
            "best_calmar": best_calmar,
            "best_under_25dd": best_return_25,
            "best_final": best_final,
        },
        "detail": detail,
        "elapsed": time.time() - t0,
    }
    out = OUT_DIR_ / "crypto_godmode_v9_multiasset_tune.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=float)
    print(f"\n  Saved → {out}")
    print(f"  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()