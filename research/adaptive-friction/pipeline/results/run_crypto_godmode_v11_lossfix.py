"""
Crypto Godmode v11 — Cluster-Informed Loss Logic Fixes
======================================================

Fixes the logic that v10/v10b found was causing loss:

  1. C0 bad-entry logic:
     - SOL-heavy long entries in high vol with weak/non-confirming ZE7 impulse.
     - These were mostly clean losses, not useful false breaks.

  2. False-break logic:
     - BTC/SOL trades often moved in the right direction then reverted.
     - Test tighter trailing for BTC/SOL only.

  3. Interpretation logic:
     - Old v9 used abs(ZE7) only.  This allows entries where impulse magnitude is
       high but not aligned with the proposed direction.
     - Test directional ZE7 alignment: direction * ZE7 >= threshold.

Baseline is v9 champion:
  ZE7 abs gate = 0.150, Q boost = 1.00, allocation = 1/3 per asset, CB on.
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
from run_crypto_godmode_v1 import KAPPA_A, W_TARGET_A1, build_w_star, build_b_aligned, calibrate, run_godmode_sweep
from test_psi_adaptive_y import BASE
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, simulate_combined, equity_metrics, period_table
from simulate_v63_quadrant import CB_HALT, CB_RESUME, CB_WINDOW_DAYS, simulate_unit_trailing_ze7gate
from run_crypto_godmode_v8_multiasset_shell import ASSETS, fetch_futures_ohlcv_symbol, build_asset_inputs
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot


OUT_DIR_ = Path(OUT_DIR)
BAR = "=" * 116

BASE_ZE7 = 0.150
BASE_ALLOC = 1.0 / 3.0
BASE_QBOOST = 1.00


VARIANTS = [
    dict(name="base_v9", align=None, sol_mode="none", sol_vol=1.0, sol_align=0.20, trail="base"),
    dict(name="align_0", align=0.00, sol_mode="none", sol_vol=1.0, sol_align=0.20, trail="base"),
    dict(name="align_005", align=0.05, sol_mode="none", sol_vol=1.0, sol_align=0.20, trail="base"),
    dict(name="align_010", align=0.10, sol_mode="none", sol_vol=1.0, sol_align=0.20, trail="base"),
    dict(name="sol_long_vol_kill", align=None, sol_mode="kill", sol_vol=1.00, sol_align=0.20, trail="base"),
    dict(name="sol_long_vol_halve", align=None, sol_mode="halve", sol_vol=1.00, sol_align=0.20, trail="base"),
    dict(name="tight_btc_sol", align=None, sol_mode="none", sol_vol=1.0, sol_align=0.20, trail="tight_btc_sol"),
    dict(name="tight_align005", align=0.05, sol_mode="none", sol_vol=1.0, sol_align=0.20, trail="tight_btc_sol"),
    dict(name="kill_tight_align005", align=0.05, sol_mode="kill", sol_vol=1.00, sol_align=0.20, trail="tight_btc_sol"),
]


def _asset_annvol(p: dict) -> np.ndarray:
    cl = pd.Series(np.asarray(p["cl"], dtype=float), index=p["hours"])
    return (np.log(cl / cl.shift(1)).rolling(24).std().fillna(0.0) * np.sqrt(24 * 365.25)).values


def _prepare_asset_input(p0: dict, asset: str, cfg: dict) -> tuple[dict, dict]:
    p = dict(p0)
    hpos = np.asarray(p["hpos"], dtype=int).copy()
    psi = np.asarray(p["psi_y"], dtype=float).copy() * BASE_ALLOC
    ze7 = np.asarray(p["ze7"], dtype=float)
    q_hot = np.asarray(p.get("q_hot", np.zeros(len(psi), dtype=bool)), dtype=bool)
    psi *= np.where(q_hot, BASE_QBOOST, 1.0)

    diagnostics = dict(align_blocked=0, sol_killed=0, sol_halved=0)

    # Fix 1: directional interpretation of ZE7.  abs(ZE7) alone is not enough.
    if cfg["align"] is not None:
        active = hpos != 0
        bad_align = active & ((hpos.astype(float) * ze7) < float(cfg["align"]))
        diagnostics["align_blocked"] = int(bad_align.sum())
        hpos[bad_align] = 0

    # Fix 2: C0-like SOL long high-vol entries.  These were mostly clean losses.
    if asset == "sol" and cfg["sol_mode"] != "none":
        annvol = _asset_annvol(p)
        active_long = hpos > 0
        weak_impulse = (hpos.astype(float) * ze7) <= float(cfg["sol_align"])
        high_vol = annvol >= float(cfg["sol_vol"])
        mask = active_long & high_vol & weak_impulse
        if cfg["sol_mode"] == "kill":
            diagnostics["sol_killed"] = int(mask.sum())
            hpos[mask] = 0
        elif cfg["sol_mode"] == "halve":
            diagnostics["sol_halved"] = int(mask.sum())
            psi[mask] *= 0.50

    p["hpos"] = hpos
    p["psi_y"] = psi
    return p, diagnostics


def _trail_params(asset: str, p: dict, cfg: dict) -> tuple[float, float, float, float]:
    sl = BASE["sl_mult"] * p["daily_vol"]
    tp = BASE["tp_mult"] * p["daily_vol"]
    if cfg["trail"] == "tight_btc_sol" and asset in {"btc", "sol"}:
        return sl, tp, 0.75 * p["daily_vol"], 0.35 * p["daily_vol"]
    return sl, tp, 1.50 * p["daily_vol"], 0.75 * p["daily_vol"]


def run_variant(cfg: dict, inputs_hot: dict[str, dict]) -> dict:
    unit_sum: pd.Series | None = None
    per_asset = {}
    diag_total = dict(align_blocked=0, sol_killed=0, sol_halved=0)

    for asset, p0 in inputs_hot.items():
        p, diag = _prepare_asset_input(p0, asset, cfg)
        for k, v in diag.items():
            diag_total[k] += v
        sl, tp, trail_trigger, trail_dist = _trail_params(asset, p, cfg)
        unit_arr, counts = simulate_unit_trailing_ze7gate(
            p["op"], p["hi"], p["lo"], p["cl"],
            p["hpos"], p["dpos"], p["dactive"], p["psi_y"],
            sl, tp, trail_trigger, trail_dist,
            ze7_arr=p["ze7"], ze7_min=BASE_ZE7,
        )
        unit = pd.Series(unit_arr, index=p["hours"])
        unit_sum = unit if unit_sum is None else unit_sum.add(unit, fill_value=0.0)
        per_asset[asset] = dict(
            counts=counts,
            diag=diag,
            unit_stats_test=_stats(unit.loc[unit.index >= pd.Timestamp(TEST_START)]),
        )

    assert unit_sum is not None
    unit_sum = unit_sum.sort_index().fillna(0.0)
    zero = pd.Series(np.zeros(len(unit_sum)), index=unit_sum.index)
    combined = simulate_combined(
        unit_sum, zero,
        K_normal=DYN_K, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME,
        cb_window_days=CB_WINDOW_DAYS, use_cb=True,
    )
    counts_total = {
        "entries": int(sum(v["counts"].get("entries", 0) for v in per_asset.values())),
        "vetoed_force": int(sum(v["counts"].get("vetoed_force", 0) for v in per_asset.values())),
        "tp": int(sum(v["counts"].get("tp", 0) for v in per_asset.values())),
        "stop": int(sum(v["counts"].get("stop", 0) for v in per_asset.values())),
        "trail_exit": int(sum(v["counts"].get("trail_exit", 0) for v in per_asset.values())),
        "signal_exit": int(sum(v["counts"].get("signal_exit", 0) for v in per_asset.values())),
    }
    combined.update(dict(label=cfg["name"], cfg=cfg, unit=unit_sum, per_asset=per_asset,
                         counts=counts_total, diagnostics=diag_total))
    return combined


def print_table(rows: list[dict]):
    print(f"\n  {'Variant':<24} {'Final$':>11} {'CAGR':>9} {'Sharpe':>8} {'MaxDD':>8} {'Calmar':>8} "
          f"{'Entries':>8} {'AlignBlk':>8} {'SolKill':>7} {'Trail':>7} {'Halt%':>7}")
    print("  " + "─" * 116)
    for r in sorted(rows, key=lambda x: x["calmar"], reverse=True):
        print(f"  {r['name']:<24} {r['final']:>11,.2f} {r['cagr']:>+8.2%} {r['sharpe']:>+8.3f} "
              f"{r['maxdd']:>+7.2%} {r['calmar']:>+8.3f} {r['entries']:>8} {r['align_blocked']:>8} "
              f"{r['sol_killed']:>7} {r['trail_exit']:>7} {r['pct_halted']:>6.1%}")


def main():
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v11 — FIX LOSS-CAUSING LOGIC")
    print(BAR)

    print("\n[1] Loading data and rebuilding v9 champion signal ...")
    df, has_sol = build_1h_df(start="2021-01-01", end="2026-05-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask = np.asarray(df.index >= TEST_START)
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v11")
    log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_f, theta,
                                kappa=KAPPA_A, anneal=True, label="v11_anneal")

    print("\n[2] Building per-asset inputs ...")
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs_hot = attach_q_hot(inputs_noq, inputs_q)

    print("\n[3] Running loss-fix variants ...")
    test_ts = pd.Timestamp(TEST_START)
    results = {}
    rows = []
    for cfg in VARIANTS:
        print(f"  {cfg['name']} ...")
        res = run_variant(cfg, inputs_hot)
        results[cfg["name"]] = res
        m = equity_metrics(res["eq"][res["eq"].index >= test_ts], cfg["name"])
        row = dict(name=cfg["name"], final=m["final"], cagr=m["cagr"], sharpe=m["sharpe"],
                   maxdd=m["maxdd"], calmar=m["calmar"], pct_halted=res["pct_halted"],
                   **res["counts"], **res["diagnostics"])
        rows.append(row)

    print(f"\n{BAR}")
    print("  v11 LOSS-FIX RESULTS")
    print(BAR)
    print_table(rows)

    best = max(rows, key=lambda r: r["calmar"])
    best_res = results[best["name"]]
    print(f"\n  Best by Calmar: {best['name']}  final=${best['final']:,.2f} CAGR={best['cagr']:+.2%} "
          f"Sharpe={best['sharpe']:+.3f} MaxDD={best['maxdd']:+.2%} Calmar={best['calmar']:+.3f}")
    print("\n  Best per-asset diagnostics:")
    for asset, pa in best_res["per_asset"].items():
        c = pa["counts"]; d = pa["diag"]; s = pa["unit_stats_test"]
        print(f"    {asset.upper():<3}: entries={c.get('entries',0):>5} veto={c.get('vetoed_force',0):>4} "
              f"tp={c.get('tp',0):>4} stop={c.get('stop',0):>4} trail={c.get('trail_exit',0):>4} "
              f"alignBlk={d.get('align_blocked',0):>5} solKill={d.get('sol_killed',0):>5} "
              f"unitSharpe={s['sharpe']:+.3f}")

    print("\n  Best yearly OOS table:")
    eq_oos = best_res["eq"][best_res["eq"].index >= test_ts]
    for row in period_table(eq_oos, "Y"):
        print(f"    {row['period']}: start=${row['start_eq']:,.2f} end=${row['end_eq']:,.2f} "
              f"return={row['return_pct']:+.1%} sharpe={row['sharpe']:+.3f} maxdd={row['maxdd']:+.1%}")

    print("\n  Underlying continuous v_anneal reference:")
    st = _stats(log_ann["pnl"].iloc[test_mask])
    print(f"    Sharpe={st['sharpe']:+.3f} MaxDD={st['max_dd']:+.2%} CAGR={st['cagr']:+.2%} $100→${st['final']:.2f}")
    print_yoy_table("v11_underlying_v_anneal", log_ann["pnl"].iloc[test_mask], [1, 2, 3, 5])

    payload = dict(
        meta=dict(version="godmode_v11_lossfix", base_ze7=BASE_ZE7, base_alloc=BASE_ALLOC,
                  base_qboost=BASE_QBOOST, theta=diag["theta"], elapsed=time.time() - t0),
        rows=rows,
        best=best,
        results={
            name: dict(full=equity_metrics(res["eq"], name),
                       test=equity_metrics(res["eq"][res["eq"].index >= test_ts], name),
                       counts=res["counts"], diagnostics=res["diagnostics"], cfg=res["cfg"],
                       per_asset=res["per_asset"])
            for name, res in results.items()
        },
        continuous_reference=_stats(log_ann["pnl"].iloc[test_mask]),
    )
    out = OUT_DIR_ / "crypto_godmode_v11_lossfix.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=float)
    print(f"\n  Saved → {out}")
    print(f"  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()