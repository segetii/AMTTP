"""
Crypto Godmode v12 — Innovative Signal Filtering for High Profit / Low DD
=========================================================================

Goal: keep v9/v11 profit but reduce drawdown by filtering bad interpretations
of the canonical signal, not changing the canonical engine.

New ideas tested:

  1. Persistence filter
     Require w_star sign to persist N hours before entry.  This targets false
     break / noisy turn entries without requiring signed ZE7 alignment.

  2. Breakeven stop after partial success
     If a trade reaches 50–75% of TP, move stop to breakeven plus small buffer.
     This targets "right but reverted" trades without globally tightening the
     trailing stop from the start.

  3. Canonical stress gate
     Optional gate on gamma / cos quality.  Prior tests showed alarm-gating was
     bad for continuous weights, but here we test it only at new trade entry.

  4. v11 SOL high-vol long halving
     Keep the one confirmed improvement: halve, not kill, C0-like SOL long risk.

Baseline reference:
  v9 champion = abs(ZE7)>=0.15, allocation=1/3, Q=1.00, CB on.
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
from simulate_master_strategy import (
    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
    RT_COST, FUND_HOURLY, simulate_combined, equity_metrics, period_table,
)
from simulate_v63_quadrant import CB_HALT, CB_RESUME, CB_WINDOW_DAYS
from run_crypto_godmode_v8_multiasset_shell import ASSETS, fetch_futures_ohlcv_symbol, build_asset_inputs
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot


OUT_DIR_ = Path(OUT_DIR)
BAR = "=" * 118

BASE_ZE7 = 0.150
BASE_ALLOC = 1.0 / 3.0


VARIANTS = [
    dict(name="base_v9", persist=0, be_assets=set(), be_frac=None, be_buf=0.0, sol_halve=False, gamma_max=None, cos_min=None),
    dict(name="v11_sol_halve", persist=0, be_assets=set(), be_frac=None, be_buf=0.0, sol_halve=True, gamma_max=None, cos_min=None),
    dict(name="persist6", persist=6, be_assets=set(), be_frac=None, be_buf=0.0, sol_halve=False, gamma_max=None, cos_min=None),
    dict(name="persist12", persist=12, be_assets=set(), be_frac=None, be_buf=0.0, sol_halve=False, gamma_max=None, cos_min=None),
    dict(name="be50_btc_sol", persist=0, be_assets={"btc", "sol"}, be_frac=0.50, be_buf=0.0005, sol_halve=False, gamma_max=None, cos_min=None),
    dict(name="be75_btc_sol", persist=0, be_assets={"btc", "sol"}, be_frac=0.75, be_buf=0.0005, sol_halve=False, gamma_max=None, cos_min=None),
    dict(name="be50_all", persist=0, be_assets={"btc", "eth", "sol"}, be_frac=0.50, be_buf=0.0005, sol_halve=False, gamma_max=None, cos_min=None),
    dict(name="persist6_be75", persist=6, be_assets={"btc", "sol"}, be_frac=0.75, be_buf=0.0005, sol_halve=False, gamma_max=None, cos_min=None),
    dict(name="halve_be75", persist=0, be_assets={"btc", "sol"}, be_frac=0.75, be_buf=0.0005, sol_halve=True, gamma_max=None, cos_min=None),
    dict(name="halve_persist6", persist=6, be_assets=set(), be_frac=None, be_buf=0.0, sol_halve=True, gamma_max=None, cos_min=None),
    dict(name="canon_gamma085", persist=0, be_assets=set(), be_frac=None, be_buf=0.0, sol_halve=False, gamma_max=0.85, cos_min=None),
    dict(name="canon_cos030", persist=0, be_assets=set(), be_frac=None, be_buf=0.0, sol_halve=False, gamma_max=None, cos_min=0.30),
    dict(name="combo_safe", persist=6, be_assets={"btc", "sol"}, be_frac=0.75, be_buf=0.0005, sol_halve=True, gamma_max=0.90, cos_min=None),
]


def _asset_annvol(p: dict) -> np.ndarray:
    cl = pd.Series(np.asarray(p["cl"], dtype=float), index=p["hours"])
    return (np.log(cl / cl.shift(1)).rolling(24).std().fillna(0.0) * np.sqrt(24 * 365.25)).values


def _signal_persistence(sig: pd.Series, hours: pd.DatetimeIndex, n: int) -> np.ndarray:
    if n <= 1:
        return np.ones(len(hours), dtype=bool)
    s = sig.reindex(hours, method="ffill").shift(1).fillna(0.0)
    sign = np.sign(s)
    ok = np.zeros(len(sign), dtype=bool)
    arr = sign.values
    for i in range(len(arr)):
        if arr[i] == 0 or i < n - 1:
            continue
        window = arr[i - n + 1:i + 1]
        ok[i] = np.all(window == arr[i])
    return ok


def prepare_input(p0: dict, asset: str, cfg: dict, sig: pd.Series, log_ann: pd.DataFrame) -> tuple[dict, dict]:
    p = dict(p0)
    hours = p["hours"]
    hpos = np.asarray(p["hpos"], dtype=int).copy()
    psi = np.asarray(p["psi_y"], dtype=float).copy() * BASE_ALLOC
    ze7 = np.asarray(p["ze7"], dtype=float)
    diag = dict(persist_blocked=0, sol_halved=0, gamma_blocked=0, cos_blocked=0)

    # Persistence: avoid entries where canonical target just flipped/noised.
    if cfg["persist"]:
        ok = _signal_persistence(sig, hours, int(cfg["persist"]))
        mask = (hpos != 0) & (~ok)
        diag["persist_blocked"] = int(mask.sum())
        hpos[mask] = 0

    # Canonical stress gates, entry-only.
    if cfg["gamma_max"] is not None:
        gamma = log_ann["gamma"].reindex(hours, method="ffill").shift(1).fillna(1.0).values
        mask = (hpos != 0) & (gamma > float(cfg["gamma_max"]))
        diag["gamma_blocked"] = int(mask.sum())
        hpos[mask] = 0
    if cfg["cos_min"] is not None:
        cos_quality = (-log_ann["cos_theta"].reindex(hours, method="ffill").shift(1).fillna(0.0)).clip(0.0, 1.0).values
        mask = (hpos != 0) & (cos_quality < float(cfg["cos_min"]))
        diag["cos_blocked"] = int(mask.sum())
        hpos[mask] = 0

    # Keep v11 proven improvement: halve C0-like SOL high-vol long risk.
    if asset == "sol" and cfg["sol_halve"]:
        annvol = _asset_annvol(p)
        mask = (hpos > 0) & (annvol >= 1.0) & ((hpos.astype(float) * ze7) <= 0.20)
        diag["sol_halved"] = int(mask.sum())
        psi[mask] *= 0.50

    p["hpos"] = hpos
    p["psi_y"] = psi
    return p, diag


def simulate_unit_breakeven(op, hi, lo, cl, hpos_arr, dpos_arr, dactive_arr, psi_y,
                            sl: float, tp: float, trail_trigger: float, trail_dist: float,
                            ze7_arr: np.ndarray, ze7_min: float,
                            be_trigger: float | None, be_buffer: float = 0.0):
    n = len(op)
    ret = np.zeros(n, dtype=float)
    pos = 0.0; size = 1.0; entry = 0.0
    stop_px = 0.0; take_px = 0.0; trail_ext = 0.0; trail_active = False; be_active = False
    counts = dict(entries=0, exits=0, longs=0, shorts=0, stop=0, tp=0, trail_exit=0,
                  signal_exit=0, close_end=0, vetoed_force=0, skipped_daily_filter=0,
                  active_hours=0, breakeven_exit=0, be_armed=0)

    for i in range(n):
        hpos = int(hpos_arr[i]); hactive = hpos != 0
        dpos = int(dpos_arr[i]); dact = bool(dactive_arr[i])
        scale = float(psi_y[i])
        if hactive:
            if dact and hpos == dpos:
                pass
            elif dact and hpos != dpos:
                hactive = False; hpos = 0; counts["skipped_daily_filter"] += 1
            else:
                scale *= 0.5
        if hactive and scale <= 1e-12:
            hactive = False; hpos = 0

        if pos != 0:
            counts["active_hours"] += 1
            exit_ret = None; reason = None
            if pos > 0:
                if hi[i] >= take_px:
                    exit_ret = take_px / entry - 1.0; reason = "tp"
                else:
                    trail_ext = max(trail_ext, hi[i])
                    if be_trigger is not None and (trail_ext / entry - 1.0) >= be_trigger:
                        new_stop = entry * (1.0 + be_buffer)
                        if new_stop > stop_px:
                            stop_px = new_stop
                            if not be_active:
                                counts["be_armed"] += 1
                            be_active = True
                    if trail_ext / entry - 1.0 >= trail_trigger:
                        trail_active = True
                    if trail_active:
                        stop_px = max(stop_px, trail_ext * (1.0 - trail_dist))
                    if lo[i] <= stop_px:
                        exit_ret = stop_px / entry - 1.0
                        reason = "trail_exit" if trail_active else ("breakeven_exit" if be_active else "stop")
            else:
                if lo[i] <= take_px:
                    exit_ret = entry / take_px - 1.0; reason = "tp"
                else:
                    trail_ext = min(trail_ext, lo[i])
                    if be_trigger is not None and (entry / trail_ext - 1.0) >= be_trigger:
                        new_stop = entry * (1.0 - be_buffer)
                        if new_stop < stop_px:
                            stop_px = new_stop
                            if not be_active:
                                counts["be_armed"] += 1
                            be_active = True
                    if entry / trail_ext - 1.0 >= trail_trigger:
                        trail_active = True
                    if trail_active:
                        stop_px = min(stop_px, trail_ext * (1.0 + trail_dist))
                    if hi[i] >= stop_px:
                        exit_ret = entry / stop_px - 1.0
                        reason = "trail_exit" if trail_active else ("breakeven_exit" if be_active else "stop")

            if exit_ret is None and hactive and hpos == -pos:
                exit_ret = (op[i] / entry - 1.0) if pos > 0 else (entry / op[i] - 1.0)
                reason = "signal_exit"
            if exit_ret is not None:
                ret[i] += size * (float(exit_ret) - RT_COST)
                counts[reason] += 1; counts["exits"] += 1
                pos = 0.0; size = 1.0; entry = 0.0; stop_px = 0.0; take_px = 0.0
                trail_ext = 0.0; trail_active = False; be_active = False
            else:
                ret[i] -= size * FUND_HOURLY

        if pos == 0 and hactive:
            if abs(float(ze7_arr[i])) < ze7_min:
                counts["vetoed_force"] += 1
                continue
            pos = float(hpos); size = float(scale); entry = float(op[i]); trail_ext = entry; be_active = False
            if pos > 0:
                stop_px = entry * (1.0 - sl); take_px = entry * (1.0 + tp); counts["longs"] += 1
            else:
                stop_px = entry * (1.0 + sl); take_px = entry * (1.0 - tp); counts["shorts"] += 1
            counts["entries"] += 1

    if pos != 0:
        gross = (cl[-1] / entry - 1.0) if pos > 0 else (entry / cl[-1] - 1.0)
        ret[-1] += size * (gross - RT_COST)
        counts["close_end"] += 1; counts["exits"] += 1
    return ret, counts


def run_variant(cfg: dict, inputs: dict[str, dict], sig_map: dict[str, pd.Series], log_ann: pd.DataFrame) -> dict:
    unit_sum: pd.Series | None = None
    per_asset = {}; diag_total = dict(persist_blocked=0, sol_halved=0, gamma_blocked=0, cos_blocked=0)
    for asset, p0 in inputs.items():
        p, diag = prepare_input(p0, asset, cfg, sig_map[asset], log_ann)
        for k, v in diag.items():
            diag_total[k] += v
        sl = BASE["sl_mult"] * p["daily_vol"]
        tp = BASE["tp_mult"] * p["daily_vol"]
        trail_trigger = 1.50 * p["daily_vol"]
        trail_dist = 0.75 * p["daily_vol"]
        be_trigger = None
        if asset in cfg["be_assets"] and cfg["be_frac"] is not None:
            be_trigger = float(cfg["be_frac"]) * tp
        unit_arr, counts = simulate_unit_breakeven(
            p["op"], p["hi"], p["lo"], p["cl"], p["hpos"], p["dpos"], p["dactive"], p["psi_y"],
            sl, tp, trail_trigger, trail_dist, p["ze7"], BASE_ZE7,
            be_trigger=be_trigger, be_buffer=float(cfg["be_buf"]),
        )
        unit = pd.Series(unit_arr, index=p["hours"])
        unit_sum = unit if unit_sum is None else unit_sum.add(unit, fill_value=0.0)
        per_asset[asset] = dict(counts=counts, diag=diag, unit_stats_test=_stats(unit.loc[unit.index >= pd.Timestamp(TEST_START)]))
    assert unit_sum is not None
    unit_sum = unit_sum.sort_index().fillna(0.0)
    zero = pd.Series(np.zeros(len(unit_sum)), index=unit_sum.index)
    combined = simulate_combined(unit_sum, zero, K_normal=DYN_K, K_crash=0.0,
                                 dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                                 cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window_days=CB_WINDOW_DAYS, use_cb=True)
    counts_total = {k: int(sum(v["counts"].get(k, 0) for v in per_asset.values()))
                    for k in ["entries", "vetoed_force", "tp", "stop", "trail_exit", "signal_exit", "breakeven_exit", "be_armed"]}
    combined.update(dict(label=cfg["name"], cfg=cfg, unit=unit_sum, per_asset=per_asset,
                         counts=counts_total, diagnostics=diag_total))
    return combined


def print_table(rows: list[dict]):
    print(f"\n  {'Variant':<20} {'Final$':>11} {'CAGR':>9} {'Sharpe':>8} {'MaxDD':>8} {'Calmar':>8} "
          f"{'Ent':>6} {'BEexit':>6} {'Persist':>7} {'SolHalf':>7} {'Gblk':>6} {'Halt%':>7}")
    print("  " + "─" * 118)
    for r in sorted(rows, key=lambda x: (x["calmar"], x["final"]), reverse=True):
        print(f"  {r['name']:<20} {r['final']:>11,.2f} {r['cagr']:>+8.2%} {r['sharpe']:>+8.3f} "
              f"{r['maxdd']:>+7.2%} {r['calmar']:>+8.3f} {r['entries']:>6} {r['breakeven_exit']:>6} "
              f"{r['persist_blocked']:>7} {r['sol_halved']:>7} {r['gamma_blocked']:>6} {r['pct_halted']:>6.1%}")


def _json_safe(obj):
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def main():
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v12 — INNOVATIVE FILTERS FOR HIGH PROFIT / LOW DD")
    print(BAR)
    print("\n[1] Loading data and canonical signal ...")
    df, has_sol = build_1h_df(start="2021-01-01", end="2026-05-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask = np.asarray(df.index >= TEST_START)
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v12")
    log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_f, theta,
                                kappa=KAPPA_A, anneal=True, label="v12_anneal")
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs = attach_q_hot(inputs_noq, inputs_q)
    sig_map = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}") for asset, _, _, idx in ASSETS}

    print("\n[2] Running v12 filter variants ...")
    test_ts = pd.Timestamp(TEST_START)
    results = {}; rows = []
    for cfg in VARIANTS:
        print(f"  {cfg['name']} ...")
        res = run_variant(cfg, inputs, sig_map, log_ann)
        results[cfg["name"]] = res
        m = equity_metrics(res["eq"][res["eq"].index >= test_ts], cfg["name"])
        rows.append(dict(name=cfg["name"], final=m["final"], cagr=m["cagr"], sharpe=m["sharpe"],
                         maxdd=m["maxdd"], calmar=m["calmar"], pct_halted=res["pct_halted"],
                         **res["counts"], **res["diagnostics"]))

    print(f"\n{BAR}")
    print("  v12 FILTER RESULTS")
    print(BAR)
    print_table(rows)
    best_calmar = max(rows, key=lambda r: r["calmar"])
    best_25 = max([r for r in rows if r["maxdd"] >= -0.25], key=lambda r: r["final"], default=best_calmar)
    best_final = max(rows, key=lambda r: r["final"])
    print("\n  Selected:")
    for tag, row in [("best_calmar", best_calmar), ("best_under_25dd", best_25), ("best_final", best_final)]:
        print(f"    {tag:<16}: {row['name']} final=${row['final']:,.2f} CAGR={row['cagr']:+.2%} "
              f"Sharpe={row['sharpe']:+.3f} MaxDD={row['maxdd']:+.2%} Calmar={row['calmar']:+.3f}")

    best_res = results[best_calmar["name"]]
    print("\n  Best-Calmar yearly OOS table:")
    eq_oos = best_res["eq"][best_res["eq"].index >= test_ts]
    for row in period_table(eq_oos, "Y"):
        print(f"    {row['period']}: start=${row['start_eq']:,.2f} end=${row['end_eq']:,.2f} "
              f"return={row['return_pct']:+.1%} sharpe={row['sharpe']:+.3f} maxdd={row['maxdd']:+.1%}")

    print("\n  Continuous v_anneal reference:")
    st = _stats(log_ann["pnl"].iloc[test_mask])
    print(f"    Sharpe={st['sharpe']:+.3f} MaxDD={st['max_dd']:+.2%} CAGR={st['cagr']:+.2%} $100→${st['final']:.2f}")
    print_yoy_table("v12_underlying_v_anneal", log_ann["pnl"].iloc[test_mask], [1, 2, 3, 5])

    payload = dict(
        meta=dict(version="godmode_v12_filter_innovate", base_ze7=BASE_ZE7, base_alloc=BASE_ALLOC,
                  theta=diag["theta"], elapsed=time.time() - t0),
        rows=rows,
        selected=dict(best_calmar=best_calmar, best_under_25dd=best_25, best_final=best_final),
        results={name: dict(full=equity_metrics(res["eq"], name),
                            test=equity_metrics(res["eq"][res["eq"].index >= test_ts], name),
                    counts=res["counts"], diagnostics=res["diagnostics"], cfg=_json_safe(res["cfg"]),
                            per_asset=res["per_asset"])
                 for name, res in results.items()},
        continuous_reference=_stats(log_ann["pnl"].iloc[test_mask]),
    )
    out = OUT_DIR_ / "crypto_godmode_v12_filter_innovate.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=float)
    print(f"\n  Saved → {out}")
    print(f"  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()