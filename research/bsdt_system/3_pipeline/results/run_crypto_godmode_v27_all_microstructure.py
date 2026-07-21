"""
run_crypto_godmode_v27_all_microstructure.py
============================================

OBJECTIVE
---------
Use the best current algorithm (v25 tbr0p47 / be50_btc_sol) and include the
extra cached microstructure features that were downloaded but mostly unused:

  Raw features:
    taker_buy_ratio, funding_rate, oi_usd, lsr, top_lsr, taker_ls

  Derived features:
    tbr_z, funding_z, oi_pct_1h, oi_pct_24h, oi_z,
    lsr_z, top_lsr_z, taker_ls_z

All microstructure values are shifted by one hour before use to avoid lookahead.

This is a 2023-2026 OOS simulation, matching the strong v17/v25 regime.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

import run_crypto_godmode_v12_filter_innovate as v12
from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import KAPPA_A, W_TARGET_A1, build_b_aligned, build_w_star, calibrate, run_godmode_sweep
from run_crypto_godmode_v8_multiasset_shell import ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from test_psi_adaptive_y import BASE
from simulate_master_strategy import (
    DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, FUND_HOURLY,
    simulate_combined, equity_metrics, period_table,
)
from run_crypto_microstructure_data import load_microstructure


BAR = "=" * 96
OUT_DIR_ = Path(OUT_DIR) / "v27_all_microstructure"

CHAMPION_CFG = dict(
    name="be50_btc_sol",
    persist=0,
    be_assets={"btc", "sol"},
    be_frac=0.50,
    be_buf=0.0005,
    sol_halve=False,
    gamma_max=None,
    cos_min=None,
)

K_NORMAL = 6.0
REALISTIC_RT_BPS = 6.0
RT_COST = REALISTIC_RT_BPS / 10_000.0

CB_HALT = 0.08
CB_RESUME = 0.01
CB_WINDOW_DAYS = 180


# Best v25 filter is tbr0p47.  v27 keeps that as the base and adds new data.
FILTER_VARIANTS = [
    dict(name="v25_tbr0p47", tbr_long_min=0.47, tbr_short_max=0.53),

    # Avoid longs when funding/crowding is too hot.
    dict(name="funding_hot_guard", tbr_long_min=0.47, tbr_short_max=0.53,
         funding_z_long_max=1.50),

    # Avoid longs when open interest is collapsing / deleveraging.
    dict(name="oi_delev_guard", tbr_long_min=0.47, tbr_short_max=0.53,
         oi_pct24h_long_min=-0.030, oi_z_long_min=-2.00),

    # Avoid longs when account crowding is long-heavy and funding confirms it.
    dict(name="crowded_long_guard", tbr_long_min=0.47, tbr_short_max=0.53,
         lsr_z_long_max=1.25, top_lsr_z_long_max=1.25, funding_z_long_max=1.25),

    # Taker-flow confirmation: longs need non-negative taker skew; shorts need
    # non-positive taker skew.  Uses z-scored taker volume ratio + TBR z-score.
    dict(name="taker_flow_confirm", tbr_long_min=0.47, tbr_short_max=0.53,
         tbr_z_long_min=-0.50, taker_ls_z_long_min=-0.50,
         tbr_z_short_max=0.50, taker_ls_z_short_max=0.50),

    # Combined conservative filter using all unused features.
    dict(name="all_feature_guard", tbr_long_min=0.47, tbr_short_max=0.53,
         funding_z_long_max=1.50,
         oi_pct24h_long_min=-0.030, oi_z_long_min=-2.00,
         lsr_z_long_max=1.50, top_lsr_z_long_max=1.50,
         tbr_z_long_min=-0.75, taker_ls_z_long_min=-0.75,
         tbr_z_short_max=0.75, taker_ls_z_short_max=0.75),
]


_MS_CACHE: dict[str, pd.DataFrame] = {}


def _get_ms(symbol: str) -> pd.DataFrame:
    if symbol not in _MS_CACHE:
        _MS_CACHE[symbol] = load_microstructure(symbol, start="2022-01-01", end="2026-06-01")
    return _MS_CACHE[symbol]


def _is_bad(v: float | None) -> bool:
    return v is None or np.isnan(v)


def simulate_unit_v27(
    op, hi, lo, cl,
    hpos_arr, dpos_arr, dactive_arr, psi_y,
    sl: float, tp: float, trail_trigger: float, trail_dist: float,
    ze7_arr: np.ndarray, ze7_min: float,
    be_trigger: float | None, be_buffer: float,
    features: dict[str, np.ndarray],
    fcfg: dict,
):
    n = len(op)
    ret = np.zeros(n, dtype=float)
    long_arr = np.zeros(n, dtype=float)
    short_arr = np.zeros(n, dtype=float)

    pos = 0.0; size = 1.0; entry = 0.0
    stop_px = 0.0; take_px = 0.0; trail_ext = 0.0
    trail_active = False; be_active = False

    counts = dict(entries=0, exits=0, longs=0, shorts=0,
                  stop=0, tp=0, trail_exit=0, signal_exit=0, close_end=0,
                  vetoed_ze7=0, skipped_daily_filter=0, active_hours=0,
                  breakeven_exit=0, be_armed=0,
                  vetoed_tbr_long=0, vetoed_tbr_short=0,
                  vetoed_funding_long=0, vetoed_oi_long=0,
                  vetoed_lsr_long=0, vetoed_taker_long=0, vetoed_taker_short=0)

    def feat(name: str, i: int, default: float = np.nan) -> float:
        arr = features.get(name)
        if arr is None:
            return default
        return float(arr[i])

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

        bar_dir = int(pos)

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
                bar_pnl = size * (float(exit_ret) - RT_COST)
                ret[i] += bar_pnl
                if bar_dir > 0: long_arr[i] += bar_pnl
                else: short_arr[i] += bar_pnl
                counts[reason] += 1; counts["exits"] += 1
                pos = 0.0; size = 1.0; entry = 0.0
                stop_px = 0.0; take_px = 0.0; trail_ext = 0.0
                trail_active = False; be_active = False
            else:
                funding = size * FUND_HOURLY
                ret[i] -= funding
                if bar_dir > 0: long_arr[i] -= funding
                else: short_arr[i] -= funding

        if pos == 0 and hactive:
            if abs(float(ze7_arr[i])) < ze7_min:
                counts["vetoed_ze7"] += 1
                continue

            # Base v25 TBR filter.
            tbr = feat("taker_buy_ratio", i, 0.5)
            if hpos > 0 and fcfg.get("tbr_long_min") is not None and not _is_bad(tbr) and tbr < fcfg["tbr_long_min"]:
                counts["vetoed_tbr_long"] += 1; continue
            if hpos < 0 and fcfg.get("tbr_short_max") is not None and not _is_bad(tbr) and tbr > fcfg["tbr_short_max"]:
                counts["vetoed_tbr_short"] += 1; continue

            if hpos > 0:
                funding_z = feat("funding_z", i)
                if fcfg.get("funding_z_long_max") is not None and not _is_bad(funding_z) and funding_z > fcfg["funding_z_long_max"]:
                    counts["vetoed_funding_long"] += 1; continue

                oi24 = feat("oi_pct_24h", i)
                oi_z = feat("oi_z", i)
                if fcfg.get("oi_pct24h_long_min") is not None and not _is_bad(oi24) and oi24 < fcfg["oi_pct24h_long_min"]:
                    counts["vetoed_oi_long"] += 1; continue
                if fcfg.get("oi_z_long_min") is not None and not _is_bad(oi_z) and oi_z < fcfg["oi_z_long_min"]:
                    counts["vetoed_oi_long"] += 1; continue

                lsr_z = feat("lsr_z", i)
                top_lsr_z = feat("top_lsr_z", i)
                if fcfg.get("lsr_z_long_max") is not None and not _is_bad(lsr_z) and lsr_z > fcfg["lsr_z_long_max"]:
                    counts["vetoed_lsr_long"] += 1; continue
                if fcfg.get("top_lsr_z_long_max") is not None and not _is_bad(top_lsr_z) and top_lsr_z > fcfg["top_lsr_z_long_max"]:
                    counts["vetoed_lsr_long"] += 1; continue

                tbr_z = feat("tbr_z", i)
                taker_ls_z = feat("taker_ls_z", i)
                if fcfg.get("tbr_z_long_min") is not None and not _is_bad(tbr_z) and tbr_z < fcfg["tbr_z_long_min"]:
                    counts["vetoed_taker_long"] += 1; continue
                if fcfg.get("taker_ls_z_long_min") is not None and not _is_bad(taker_ls_z) and taker_ls_z < fcfg["taker_ls_z_long_min"]:
                    counts["vetoed_taker_long"] += 1; continue

            if hpos < 0:
                tbr_z = feat("tbr_z", i)
                taker_ls_z = feat("taker_ls_z", i)
                if fcfg.get("tbr_z_short_max") is not None and not _is_bad(tbr_z) and tbr_z > fcfg["tbr_z_short_max"]:
                    counts["vetoed_taker_short"] += 1; continue
                if fcfg.get("taker_ls_z_short_max") is not None and not _is_bad(taker_ls_z) and taker_ls_z > fcfg["taker_ls_z_short_max"]:
                    counts["vetoed_taker_short"] += 1; continue

            pos = float(hpos); size = float(scale); entry = float(op[i])
            trail_ext = entry; be_active = False
            if pos > 0:
                stop_px = entry * (1.0 - sl); take_px = entry * (1.0 + tp); counts["longs"] += 1
            else:
                stop_px = entry * (1.0 + sl); take_px = entry * (1.0 - tp); counts["shorts"] += 1
            counts["entries"] += 1

    if pos != 0:
        gross = (cl[-1] / entry - 1.0) if pos > 0 else (entry / cl[-1] - 1.0)
        bar_pnl = size * (gross - RT_COST)
        ret[-1] += bar_pnl
        if pos > 0: long_arr[-1] += bar_pnl
        else: short_arr[-1] += bar_pnl
        counts["close_end"] += 1; counts["exits"] += 1

    return ret, long_arr, short_arr, counts


def run_variant_v27(cfg: dict, fcfg: dict, inputs: dict, sig_map: dict[str, pd.Series], log_ann: pd.DataFrame) -> dict:
    unit_sum = None
    per_asset = {}
    asset_to_sym = {"btc": "BTCUSDT", "sol": "SOLUSDT", "eth": "ETHUSDT"}

    for asset, p0 in inputs.items():
        p, diag = v12.prepare_input(p0, asset, cfg, sig_map[asset], log_ann)
        sl = BASE["sl_mult"] * p["daily_vol"]
        tp = BASE["tp_mult"] * p["daily_vol"]
        trail_trigger = 1.50 * p["daily_vol"]
        trail_dist = 0.75 * p["daily_vol"]
        be_trigger = float(cfg["be_frac"]) * tp if asset in cfg["be_assets"] and cfg["be_frac"] is not None else None
        hours_idx = p["hours"]

        ms = _get_ms(asset_to_sym.get(asset, asset.upper() + "USDT"))

        def _align_shift(col: str, default: float = np.nan) -> np.ndarray:
            if col not in ms.columns:
                return np.full(len(hours_idx), default, dtype=float)
            s = ms[col]
            if s.index.tz is not None:
                s = s.tz_convert("UTC").tz_localize(None)
            return s.shift(1).reindex(hours_idx, method="ffill").fillna(default).values.astype(float)

        feature_cols = [
            "taker_buy_ratio", "funding_rate", "tbr_z", "funding_z",
            "oi_pct_1h", "oi_pct_24h", "oi_z", "lsr_z", "top_lsr_z", "taker_ls_z",
            "oi_usd", "lsr", "top_lsr", "taker_ls",
        ]
        features = {c: _align_shift(c, 0.5 if c == "taker_buy_ratio" else np.nan) for c in feature_cols}

        arr, _, _, counts = simulate_unit_v27(
            p["op"], p["hi"], p["lo"], p["cl"],
            p["hpos"], p["dpos"], p["dactive"], p["psi_y"],
            sl, tp, trail_trigger, trail_dist, p["ze7"], v12.BASE_ZE7,
            be_trigger=be_trigger, be_buffer=float(cfg["be_buf"]),
            features=features, fcfg=fcfg,
        )
        unit = pd.Series(arr, index=hours_idx)
        unit_sum = unit if unit_sum is None else unit_sum.add(unit, fill_value=0.0)
        per_asset[asset] = dict(counts=counts, diag=diag)

    return dict(unit=unit_sum.sort_index().fillna(0.0), per_asset=per_asset)


def simulate_combined_v27(unit: pd.Series) -> dict:
    return simulate_combined(
        unit_normal=unit,
        unit_crash=pd.Series(0.0, index=unit.index),
        K_normal=K_NORMAL,
        K_crash=0.0,
        dd_soft=DYN_DD_SOFT,
        dd_stop=DYN_DD_STOP,
        y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT,
        cb_resume=CB_RESUME,
        cb_window_days=CB_WINDOW_DAYS,
        use_cb=True,
    )


def _yoy_table(eq: pd.Series) -> list[dict]:
    rows = []
    for row in period_table(eq, "Y"):
        row["period"] = row["period"][:4]
        rows.append(row)
    return rows


def main() -> None:
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v27 — BEST ALGORITHM + ALL CACHED MICROSTRUCTURE")
    print(BAR)
    print("  Base algorithm: v25 tbr0p47 / be50_btc_sol")
    print("  Extra features: funding_z, oi_pct_24h, oi_z, lsr_z, top_lsr_z, taker_ls_z, tbr_z")
    print(f"  OOS={TEST_START}→2026-06-01  K={K_NORMAL}  RT={REALISTIC_RT_BPS} bps")

    print("\n[1] Building canonical engine ...")
    df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask = np.asarray(df.index >= TEST_START)
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, _ = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v27")
    log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_f, theta,
                                kappa=KAPPA_A, anneal=True, label="v27_anneal")
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs = attach_q_hot(inputs_noq, inputs_q)
    sig_map = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}") for asset, _, _, idx in ASSETS}
    test_ts = pd.Timestamp(TEST_START)
    print(f"  Engine built: {df.index[0]} → {df.index[-1]}  train={train_mask.sum():,}h test={test_mask.sum():,}h")

    print("\n[2] Preloading cached microstructure ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = _get_ms(sym)
        print(f"  {sym}: shape={ms.shape} cols={list(ms.columns)}")

    print(f"\n[3] Running {len(FILTER_VARIANTS)} variants ...")
    results = []
    for fcfg in FILTER_VARIANTS:
        res = run_variant_v27(CHAMPION_CFG, fcfg, inputs, sig_map, log_ann)
        sim = simulate_combined_v27(res["unit"])
        eq_oos = sim["eq"][sim["eq"].index >= test_ts]
        m = equity_metrics(eq_oos, fcfg["name"])
        yoy = {r["period"]: r["return_pct"] for r in _yoy_table(eq_oos)}
        counts_total = {}
        for pa in res["per_asset"].values():
            for k, v in pa["counts"].items():
                counts_total[k] = counts_total.get(k, 0) + int(v)
        veto_keys = [k for k in counts_total if k.startswith("vetoed_") and k != "vetoed_ze7"]
        total_vetoes = sum(counts_total[k] for k in veto_keys)
        entries = counts_total.get("entries", 0)
        veto_pct = total_vetoes / max(entries + total_vetoes, 1)
        row = dict(
            name=fcfg["name"], final=m["final"], cagr=m["cagr"], calmar=m["calmar"],
            sharpe=m["sharpe"], maxdd=m["maxdd"], pct_halted=sim["pct_halted"],
            veto_pct=veto_pct, entries=entries,
            r2023=yoy.get("2023", np.nan), r2024=yoy.get("2024", np.nan),
            r2025=yoy.get("2025", np.nan), r2026=yoy.get("2026", np.nan),
            counts=counts_total, config=fcfg,
        )
        results.append(row)
        print(f"  {fcfg['name']:<22} final=${m['final']:>10,.0f} CAGR={m['cagr']:+7.2%} "
              f"Calmar={m['calmar']:+6.3f} MaxDD={m['maxdd']:+.2%} veto={veto_pct:.1%}")

    best = max(results, key=lambda x: x["calmar"])
    best_final = max(results, key=lambda x: x["final"])
    print("\n" + BAR)
    print("  v27 RESULTS")
    print(BAR)
    for r in sorted(results, key=lambda x: -x["calmar"]):
        print(f"  {r['name']:<22} ${r['final']:>10,.0f}  CAGR={r['cagr']:+7.2%}  "
              f"Calmar={r['calmar']:+6.3f}  Sharpe={r['sharpe']:+.3f}  MaxDD={r['maxdd']:+.2%}  "
              f"2023={r['r2023']:+.1%} 2024={r['r2024']:+.1%} 2025={r['r2025']:+.1%} 2026={r['r2026']:+.1%}")
    print(f"\n  Best Calmar: {best['name']}  Calmar={best['calmar']:+.3f} final=${best['final']:,.0f}")
    print(f"  Best final : {best_final['name']}  final=${best_final['final']:,.0f} Calmar={best_final['calmar']:+.3f}")

    out = OUT_DIR_ / "crypto_godmode_v27_all_microstructure.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dict(
            meta=dict(version="v27_all_microstructure", base="v25_tbr0p47", oos_start=TEST_START,
                      K_normal=K_NORMAL, rt_bps=REALISTIC_RT_BPS, elapsed=time.time() - t0),
            results=results,
            best_calmar=best,
            best_final=best_final,
        ), f, indent=2, default=float)
    print(f"\n  Saved → {out}")
    print(f"  Elapsed: {time.time() - t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()