"""
Crypto Godmode v8 — Multi-Asset Champion Execution Shell
=========================================================

v7 proved that the old ETH-only shell is too narrow for the current Godmode
edge.  v8 ports the shell to the actual multi-asset system that v55→v60 traded:

  Godmode v1/v_anneal canonical signal over [BTC, ETH, SOL]
    + per-asset BTCUSDT/ETHUSDT/SOLUSDT futures OHLC trade lifecycle
    + per-asset SL / TP / trailing stop
    + shared BSDT ZE7 minimum-force entry gate
    + shared GH/TH quadrant size multiplier
    + shared 8%/1%/180d circuit breaker and adaptive drawdown sizing

Direction rule:
  - Primary variants use the aligned canonical target `w_star_asset`.
    v7 showed discrete execution from raw ODE `w_asset` is too noisy.
  - Diagnostic variants can still run ODE-weight signals.
  - cos(theta) is never used as direction; it is a coherence scalar only.

The old shell simulator is reused asset-by-asset, then unit returns are summed
into one normal sleeve before the shared circuit breaker.
"""
from __future__ import annotations

import os
import sys
import json
import time
import warnings
from pathlib import Path

import requests
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
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import (
    DYN_K,
    DYN_DD_SOFT,
    DYN_DD_STOP,
    DYN_Y_FLOOR,
    simulate_combined,
    equity_metrics,
    period_table,
)
from simulate_v63_quadrant import (
    CB_HALT,
    CB_RESUME,
    CB_WINDOW_DAYS,
    ZE7_MIN_FORCE,
)
from run_crypto_godmode_v7_exec_shell import (
    build_godmode_exec_inputs,
    run_exec_variant,
)


OUT_DIR_ = Path(OUT_DIR)
DATA_DIR = Path(r"C:\amttp\data")
BAR = "=" * 112

ASSETS = [
    ("btc", "BTCUSDT", "w_btc", 0),
    ("eth", "ETHUSDT", "w_eth", 1),
    ("sol", "SOLUSDT", "w_sol", 2),
]


def fetch_futures_ohlcv_symbol(symbol: str,
                               start: str = "2021-01-01",
                               end: str = "2026-06-01",
                               interval: str = "1h") -> pd.DataFrame:
    """Fetch Binance USDT-perp OHLCV with a symbol-specific cache.

    The legacy helper caches only ETHUSDT globally.  Multi-asset mode needs a
    separate cache per symbol to avoid accidentally reusing ETH candles for BTC
    or SOL.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache = DATA_DIR / f"binance_futures_{symbol}_{interval}_ohlcv.pkl"
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    now_floor = pd.Timestamp.utcnow().tz_localize(None).floor(interval)
    expected_latest = min(end_ts, now_floor) - pd.Timedelta(hours=2)

    if cache.exists():
        df = pd.read_pickle(cache)
        if df.index.min() <= start_ts and df.index.max() >= expected_latest:
            print(f"  {symbol} futures OHLCV [CACHE]")
            return df[(df.index >= start_ts) & (df.index < end_ts)].copy()
        print(f"  {symbol} futures OHLCV [STALE max={df.index.max()} expected>={expected_latest}]")

    print(f"  {symbol} futures OHLCV [FETCH]")
    url = "https://fapi.binance.com/fapi/v1/klines"
    iv_ms = {"1h": 3_600_000, "4h": 14_400_000}.get(interval, 3_600_000)
    s_ms = int(start_ts.timestamp() * 1000)
    e_ms = int(end_ts.timestamp() * 1000)
    recs: list = []
    cur = s_ms
    fails = 0
    while cur < e_ms:
        try:
            r = requests.get(
                url,
                params={"symbol": symbol, "interval": interval,
                        "startTime": cur, "endTime": e_ms, "limit": 1500},
                timeout=30,
            )
            data = r.json()
            if not isinstance(data, list) or not data:
                break
            recs.extend(data)
            cur = int(data[-1][0]) + iv_ms
            if len(data) < 1500:
                break
            time.sleep(0.03)
            fails = 0
        except Exception as exc:
            fails += 1
            if fails >= 4:
                raise RuntimeError(f"{symbol} OHLCV fetch failed: {exc}")
            time.sleep(1.5)

    if not recs:
        raise RuntimeError(f"No OHLCV records fetched for {symbol}")

    ts = pd.to_datetime([int(r[0]) for r in recs], unit="ms").tz_localize(None)
    df = pd.DataFrame({
        "open": [float(r[1]) for r in recs],
        "high": [float(r[2]) for r in recs],
        "low": [float(r[3]) for r in recs],
        "close": [float(r[4]) for r in recs],
        "volume": [float(r[5]) for r in recs],
    }, index=ts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df.to_pickle(cache)
    return df[(df.index >= start_ts) & (df.index < end_ts)].copy()


def build_asset_inputs(df: pd.DataFrame,
                       log_ann: pd.DataFrame,
                       w_star: np.ndarray,
                       ch: dict,
                       ohlc_map: dict[str, pd.DataFrame],
                       signal_kind: str,
                       use_quadrant: bool) -> dict[str, dict]:
    """Build execution arrays for all assets."""
    out: dict[str, dict] = {}
    for asset, symbol, w_col, idx in ASSETS:
        sig = None
        src = f"ode_{w_col}"
        if signal_kind == "wstar":
            sig = pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
            src = f"wstar_{asset}"
        p = build_godmode_exec_inputs(
            df, ohlc_map[symbol], log_ann, ch,
            use_quadrant=use_quadrant,
            signal_series=sig,
            source_label=src,
        )
        p["asset"] = asset
        p["symbol"] = symbol
        p["signal_kind"] = signal_kind
        out[asset] = p
    return out


def run_multi_asset_variant(label: str,
                            asset_inputs: dict[str, dict],
                            allocation_scale: float,
                            ze7_min: float,
                            use_cb: bool) -> dict:
    """Run per-asset shell simulations and combine unit returns."""
    per_asset: dict[str, dict] = {}
    unit_sum: pd.Series | None = None

    for asset, p0 in asset_inputs.items():
        p = dict(p0)
        p["psi_y"] = np.asarray(p["psi_y"], dtype=float) * allocation_scale
        res = run_exec_variant(f"{label}_{asset}", p, ze7_min=ze7_min, use_cb=False)
        unit = res["unit"]
        unit_sum = unit if unit_sum is None else unit_sum.add(unit, fill_value=0.0)
        per_asset[asset] = {
            "counts": res["counts"],
            "unit_stats": _stats(unit.loc[unit.index >= pd.Timestamp(TEST_START)]),
            "active_pct": p["active_pct"],
            "avg_psi": float(np.mean(p["psi_y"])),
            "daily_vol": p["daily_vol"],
        }

    assert unit_sum is not None
    unit_sum = unit_sum.sort_index().fillna(0.0)
    zero = pd.Series(np.zeros(len(unit_sum)), index=unit_sum.index)
    combined = simulate_combined(
        unit_sum, zero,
        K_normal=DYN_K, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME,
        cb_window_days=CB_WINDOW_DAYS, use_cb=use_cb,
    )
    combined.update(dict(
        label=label,
        unit=unit_sum,
        per_asset=per_asset,
        allocation_scale=allocation_scale,
        ze7_min=ze7_min,
        use_cb=use_cb,
        counts={
            "entries": int(sum(v["counts"].get("entries", 0) for v in per_asset.values())),
            "vetoed_force": int(sum(v["counts"].get("vetoed_force", 0) for v in per_asset.values())),
            "tp": int(sum(v["counts"].get("tp", 0) for v in per_asset.values())),
            "stop": int(sum(v["counts"].get("stop", 0) for v in per_asset.values())),
            "trail_exit": int(sum(v["counts"].get("trail_exit", 0) for v in per_asset.values())),
            "signal_exit": int(sum(v["counts"].get("signal_exit", 0) for v in per_asset.values())),
        },
    ))
    return combined


def print_results_table(results: dict[str, dict], test_ts: pd.Timestamp):
    print(f"\n  {'Multi-asset variant':<28} {'Final$':>11} {'Return':>9} {'CAGR':>9} "
          f"{'Sharpe':>8} {'MaxDD':>8} {'Calmar':>8} {'Entries':>8} {'Veto':>7} {'Halt%':>7}")
    print(f"  {'─'*112}")
    for name, res in results.items():
        eq_oos = res["eq"][res["eq"].index >= test_ts]
        m = equity_metrics(eq_oos, name)
        c = res["counts"]
        print(f"  {name:<28} {m['final']:>11,.2f} {m['return_pct']:>+8.1%} "
              f"{m['cagr']:>+8.2%} {m['sharpe']:>+8.3f} {m['maxdd']:>+7.2%} "
              f"{m['calmar']:>+8.3f} {c['entries']:>8} {c['vetoed_force']:>7} "
              f"{res.get('pct_halted', 0.0):>6.1%}")


def main():
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v8 — MULTI-ASSET OLD-WINNER EXECUTION SHELL")
    print("  Assets: BTCUSDT + ETHUSDT + SOLUSDT | Signal: Godmode v_anneal")
    print(BAR)

    print("\n[1] Loading spot panel, per-asset futures OHLCV, and BSDT channels ...")
    df, has_sol = build_1h_df(start="2021-01-01", end="2026-05-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask = np.asarray(df.index >= TEST_START)
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()
    print(f"  spot bars={len(df):,} train={train_mask.sum():,} test={test_mask.sum():,} SOL={has_sol}")
    for asset, symbol, _, _ in ASSETS:
        x = ohlc_map[symbol]
        print(f"  {asset.upper():<3} {symbol}: {len(x):,} bars [{x.index.min()} → {x.index.max()}]")

    print("\n[2] Building Godmode v_anneal canonical signal ...")
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v8")
    log_ann = run_godmode_sweep(
        df, train_mask, test_mask,
        w_star, b_aligned, Sigma_f, theta,
        kappa=KAPPA_A, anneal=True, label="v8_anneal",
    )

    print("\n[3] Building per-asset execution inputs ...")
    inputs_star_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs_star_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_ode_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="ode", use_quadrant=True)

    for asset, p in inputs_star_q.items():
        print(f"  {asset.upper():<3} w_star: active={p['active_pct']:.1%} daily_active={p['daily_active_pct']:.1%} "
              f"daily_vol={p['daily_vol']:.2%} avg_psi={p['avg_psi']:.3f}")

    print("\n[4] Running multi-asset shell variants ...")
    # allocation_scale is applied per asset before the shared K=3 normal sleeve.
    # 1/3 approximates equal-capital slots; 1/2 tests controlled concentration;
    # 1.0 is diagnostic full-notional-per-asset mode.
    results = {
        "star_eq_CB": run_multi_asset_variant("star_eq_CB", inputs_star_noq, allocation_scale=1/3, ze7_min=0.0, use_cb=True),
        "star_eq_ZE7_CB": run_multi_asset_variant("star_eq_ZE7_CB", inputs_star_noq, allocation_scale=1/3, ze7_min=ZE7_MIN_FORCE, use_cb=True),
        "star_eq_Q_ZE7_CB": run_multi_asset_variant("star_eq_Q_ZE7_CB", inputs_star_q, allocation_scale=1/3, ze7_min=ZE7_MIN_FORCE, use_cb=True),
        "star_half_Q_ZE7_CB": run_multi_asset_variant("star_half_Q_ZE7_CB", inputs_star_q, allocation_scale=0.5, ze7_min=ZE7_MIN_FORCE, use_cb=True),
        "star_full_Q_ZE7_CB": run_multi_asset_variant("star_full_Q_ZE7_CB", inputs_star_q, allocation_scale=1.0, ze7_min=ZE7_MIN_FORCE, use_cb=True),
        "ode_eq_Q_ZE7_CB": run_multi_asset_variant("ode_eq_Q_ZE7_CB", inputs_ode_q, allocation_scale=1/3, ze7_min=ZE7_MIN_FORCE, use_cb=True),
    }

    test_ts = pd.Timestamp(TEST_START)
    print(f"\n{BAR}")
    print("  GODMODE v8 MULTI-ASSET HYBRID RESULTS  (OOS 2023→2026, $1,000, K=3 normal sleeve)")
    print(BAR)
    print_results_table(results, test_ts)

    print(f"\n  {'Reference continuous Godmode v_anneal, 1× gross':<54}")
    st = _stats(log_ann["pnl"].iloc[test_mask])
    print(f"  Sharpe={st['sharpe']:+.3f}  MaxDD={st['max_dd']:+.2%}  "
          f"CAGR={st['cagr']:+.2%}  $100→${st['final']:.2f}")

    best_name = max(results.keys(), key=lambda k: equity_metrics(results[k]["eq"][results[k]["eq"].index >= test_ts])["calmar"])
    best = results[best_name]
    print(f"\n  Best by OOS Calmar: {best_name}")
    print(f"  Aggregate counts: {best['counts']}")
    print("\n  Per-asset counts for best:")
    for asset, pa in best["per_asset"].items():
        c = pa["counts"]
        us = pa["unit_stats"]
        print(f"    {asset.upper():<3}: entries={c.get('entries',0):>5} veto={c.get('vetoed_force',0):>4} "
              f"tp={c.get('tp',0):>4} stop={c.get('stop',0):>4} trail={c.get('trail_exit',0):>3} "
              f"unit_sharpe={us['sharpe']:+.3f} unit_dd={us['max_dd']:+.2%}")

    best_eq_oos = best["eq"][best["eq"].index >= test_ts]
    print("\n  Best yearly OOS table:")
    for row in period_table(best_eq_oos, "Y"):
        print(f"    {row['period']}: start=${row['start_eq']:,.2f} end=${row['end_eq']:,.2f} "
              f"return={row['return_pct']:+.1%} sharpe={row['sharpe']:+.3f} maxdd={row['maxdd']:+.1%}")

    print_yoy_table("v8_underlying_v_anneal", log_ann["pnl"].iloc[test_mask], [1, 2, 3, 5])

    payload = {
        "meta": {
            "version": "godmode_v8_multiasset_shell",
            "assets": [a for a, _, _, _ in ASSETS],
            "symbols": [s for _, s, _, _ in ASSETS],
            "W_TARGET_A1": W_TARGET_A1,
            "KAPPA_A": KAPPA_A,
            "theta": diag["theta"],
            "ze7_min_force": ZE7_MIN_FORCE,
            "cb_halt": CB_HALT,
            "cb_resume": CB_RESUME,
            "cb_window_days": CB_WINDOW_DAYS,
            "DYN_K": DYN_K,
        },
        "continuous_reference": _stats(log_ann["pnl"].iloc[test_mask]),
        "execution_results": {
            name: {
                "full": equity_metrics(res["eq"], name),
                "test": equity_metrics(res["eq"][res["eq"].index >= test_ts], name),
                "counts": res["counts"],
                "allocation_scale": res["allocation_scale"],
                "pct_halted": res["pct_halted"],
                "n_trips": res["n_trips"],
                "avg_y": res["avg_y"],
                "per_asset": res["per_asset"],
            }
            for name, res in results.items()
        },
        "best_by_oos_calmar": best_name,
        "elapsed": time.time() - t0,
    }
    out = OUT_DIR_ / "crypto_godmode_v8_multiasset_shell.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=float)
    print(f"\n  Saved → {out}")
    print(f"  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()