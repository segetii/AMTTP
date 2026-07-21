"""
Crypto Godmode v7 — Canonical Signal + Champion Execution Shell
================================================================

This is the direct hybrid requested after the old-engine archaeology:

  Godmode v1/v_anneal canonical signal
    + old winner OHLC trade lifecycle
    + ZE7 minimum-force entry gate
    + GH/TH quadrant size boost
    + trailing stop / SL / TP
    + 8%/1%/180d circuit breaker
    + adaptive drawdown sizing

The goal is NOT to alter the canonical ODE again.  The experiment keeps the
proven v1 aligned geometry and puts the missing old survival/execution stack
around it.

Execution choice:
  - Single-instrument ETHUSDT perp shell, matching the old paper-correct lesson:
    a single directional signal should execute as one directional instrument.
  - Direction comes from the lagged Godmode ETH weight, not from cos(theta).
  - cos(theta) remains a non-negative confidence/coherence scalar only.
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
from test_psi_adaptive_y import BASE
from test_daily_geometry_stop_tp_ohlc import fetch_futures_ohlcv, get_channel_series
from simulate_master_strategy import (
    INIT,
    DYN_K,
    DYN_DD_SOFT,
    DYN_DD_STOP,
    DYN_Y_FLOOR,
    DYN_TOTAL_CAP,
    simulate_combined,
    equity_metrics,
    period_table,
)
from simulate_v63_quadrant import (
    _build_quadrant_multiplier,
    simulate_unit_trailing_ze7gate,
    CB_HALT,
    CB_RESUME,
    CB_WINDOW_DAYS,
    TRAIL_TRIGGER_MULT,
    TRAIL_DIST_MULT,
    ZE7_MIN_FORCE,
)


OUT_DIR_ = Path(OUT_DIR)
BAR = "=" * 108
SEP = "-" * 108


def _percentile_against(x: np.ndarray, cal: np.ndarray) -> np.ndarray:
    """Empirical percentile rank of x against calibration sample."""
    cal = np.sort(np.asarray(cal, dtype=float))
    if len(cal) == 0:
        return np.zeros_like(x, dtype=float)
    return np.searchsorted(cal, x, side="right") / len(cal)


def _daily_vol_from_ohlc(ohlc: pd.DataFrame) -> float:
    train_days = pd.Index(sorted(ohlc.index.normalize().unique()))
    train_days = train_days[(train_days >= pd.Timestamp(TRAIN_START)) &
                            (train_days < pd.Timestamp(TEST_START))]
    ret_daily = ohlc["close"].pct_change().fillna(0.0).groupby(ohlc.index.normalize()).sum()
    return float(ret_daily.reindex(train_days).std())


def build_godmode_exec_inputs(df: pd.DataFrame,
                              ohlc_all: pd.DataFrame,
                              log_ann: pd.DataFrame,
                              ch: dict,
                              use_quadrant: bool = True,
                              signal_series: pd.Series | None = None,
                              source_label: str = "w_eth") -> dict:
    """Convert Godmode v_anneal weights into old-shell execution arrays.

    Causality:
      - hpos uses lagged `w_eth`; current bar opens using previous canonical state.
      - dpos uses previous day's final Godmode ETH signal, forward-filled.
      - ZE7 and quadrant channels are shifted by their own helper/shift logic.
    """
    common_start = max(df.index.min(), ohlc_all.index.min(), log_ann.index.min())
    common_end = min(df.index.max(), ohlc_all.index.max(), log_ann.index.max())
    ohlc = ohlc_all[(ohlc_all.index >= common_start) & (ohlc_all.index <= common_end)].copy()
    hours = ohlc.index

    raw_signal = log_ann["w_eth"] if signal_series is None else signal_series
    w_eth = raw_signal.reindex(hours, method="ffill").shift(1).fillna(0.0)
    conv = log_ann["conviction"].reindex(hours, method="ffill").shift(1).fillna(0.0)
    cos_theta = log_ann["cos_theta"].reindex(hours, method="ffill").shift(1).fillna(0.0)

    train_h = (hours >= pd.Timestamp(TRAIN_START)) & (hours < pd.Timestamp(TEST_START))
    cal_abs = w_eth.loc[train_h].abs().replace(0.0, np.nan).dropna()
    hth = float(cal_abs.quantile(BASE["q_hourly"])) if len(cal_abs) else 0.0
    hpos = np.where(w_eth.abs().values >= hth, np.sign(w_eth.values).astype(int), 0)

    # Daily confirmation from the same Godmode ETH signal.
    daily_sig = w_eth.groupby(w_eth.index.normalize()).last()
    train_daily = (daily_sig.index >= pd.Timestamp(TRAIN_START)) & (daily_sig.index < pd.Timestamp(TEST_START))
    cal_daily = daily_sig.loc[train_daily].abs().replace(0.0, np.nan).dropna()
    dth = float(cal_daily.quantile(BASE["q_daily"])) if len(cal_daily) else hth
    d_vals = daily_sig.shift(1).reindex(hours, method="ffill").fillna(0.0)
    dpos = np.sign(d_vals.values).astype(int)
    dactive = (d_vals.abs().values >= dth)

    # Volatility/risk sizing shell from the old strategy family.
    ret_h = ohlc_all["close"].pct_change().fillna(0.0)
    rv = ret_h.rolling(24, min_periods=12).std().shift(1)
    rv_cal = rv[(rv.index >= pd.Timestamp(TRAIN_START)) & (rv.index < pd.Timestamp(TEST_START))].dropna()
    rv_h = rv.reindex(hours).ffill().fillna(float(rv_cal.median()) if len(rv_cal) else 1e-3)
    rv_med = float(rv_cal.median()) if len(rv_cal) else float(rv_h.median())
    vol_base = (rv_med / rv_h.clip(lower=1e-8)).values
    vol_mult = np.clip(vol_base, 0.25, 3.0)

    cal_strength = cal_abs.values if len(cal_abs) else np.array([1.0])
    strength_rank = _percentile_against(w_eth.abs().values, cal_strength)
    # Direction is from w_eth; cos(theta) is only coherence confidence.
    coherence = np.clip(-cos_theta.values, 0.20, 1.00)
    psi_base = np.clip(0.25 + 1.75 * strength_rank, 0.25, 2.0)
    psi_y = psi_base * np.clip(conv.values, 0.20, 1.00) * coherence * vol_mult

    q_mult = _build_quadrant_multiplier(ch, hours) if use_quadrant else np.ones(len(hours))
    psi_y = np.clip(psi_y * q_mult, 0.0, DYN_TOTAL_CAP)

    ze7 = ch["E7"].reindex(hours, method="ffill").shift(1).fillna(0.0).values.astype(float)
    daily_vol = _daily_vol_from_ohlc(ohlc_all)

    return dict(
        hours=hours,
        op=ohlc["open"].values.astype(float),
        hi=ohlc["high"].values.astype(float),
        lo=ohlc["low"].values.astype(float),
        cl=ohlc["close"].values.astype(float),
        hpos=hpos,
        dpos=dpos,
        dactive=dactive,
        psi_y=psi_y,
        ze7=ze7,
        q_mult=q_mult,
        daily_vol=daily_vol,
        hth=hth,
        dth=dth,
        active_pct=float((hpos != 0).mean()),
        daily_active_pct=float(dactive.mean()),
        q_boost_pct=float((q_mult > 1.0).mean()),
        avg_psi=float(np.mean(psi_y)),
        source_label=source_label,
    )


def run_exec_variant(label: str,
                     p: dict,
                     ze7_min: float,
                     use_cb: bool) -> dict:
    """Run one old-shell variant around the Godmode signal."""
    sl = BASE["sl_mult"] * p["daily_vol"]
    tp = BASE["tp_mult"] * p["daily_vol"]
    trail_trigger = TRAIL_TRIGGER_MULT * p["daily_vol"]
    trail_dist = TRAIL_DIST_MULT * p["daily_vol"]

    unit_arr, counts = simulate_unit_trailing_ze7gate(
        p["op"], p["hi"], p["lo"], p["cl"],
        p["hpos"], p["dpos"], p["dactive"], p["psi_y"],
        sl, tp, trail_trigger, trail_dist,
        ze7_arr=p["ze7"], ze7_min=ze7_min,
    )
    unit = pd.Series(unit_arr, index=p["hours"])
    zero = pd.Series(np.zeros(len(unit)), index=unit.index)

    res = simulate_combined(
        unit, zero,
        K_normal=DYN_K, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME,
        cb_window_days=CB_WINDOW_DAYS, use_cb=use_cb,
    )
    res.update(dict(label=label, unit=unit, counts=counts, ze7_min=ze7_min, use_cb=use_cb))
    return res


def _print_exec_table(results: dict, test_ts: pd.Timestamp):
    print(f"\n  {'Hybrid execution result':<34} {'Final$':>11} {'Return':>9} {'CAGR':>9} "
          f"{'Sharpe':>8} {'MaxDD':>8} {'Calmar':>8} {'Trades':>8} {'Veto':>7} {'Halt%':>7}")
    print(f"  {'─'*108}")
    for name, res in results.items():
        eq_oos = res["eq"][res["eq"].index >= test_ts]
        m = equity_metrics(eq_oos, name)
        c = res["counts"]
        print(f"  {name:<34} {m['final']:>11,.2f} {m['return_pct']:>+8.1%} "
              f"{m['cagr']:>+8.2%} {m['sharpe']:>+8.3f} {m['maxdd']:>+7.2%} "
              f"{m['calmar']:>+8.3f} {c.get('entries', 0):>8} {c.get('vetoed_force', 0):>7} "
              f"{res.get('pct_halted', 0.0):>6.1%}")


def main():
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v7 — v_anneal canonical signal inside old champion execution shell")
    print("  Shell: ETHUSDT OHLC SL/TP/trail + ZE7 gate + GH/TH boost + 8/1/180d CB")
    print(BAR)

    print("\n[1] Loading 1h spot panel + ETHUSDT futures OHLC + BSDT channels ...")
    df, has_sol = build_1h_df(start="2021-01-01", end="2026-05-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask = np.asarray(df.index >= TEST_START)
    ohlc_all = fetch_futures_ohlcv()
    ch = get_channel_series()
    print(f"  bars={len(df):,} train={train_mask.sum():,} test={test_mask.sum():,} SOL={has_sol}")
    print(f"  futures bars={len(ohlc_all):,} channels={list(ch.keys())}")

    print("\n[2] Building Godmode v_anneal canonical signal ...")
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v7")
    log_ann = run_godmode_sweep(
        df, train_mask, test_mask,
        w_star, b_aligned, Sigma_f, theta,
        kappa=KAPPA_A, anneal=True, label="v7_anneal",
    )

    print("\n[3] Translating canonical ETH weight into execution arrays ...")
    wstar_eth = pd.Series(w_star[:, 1], index=df.index, name="wstar_eth")
    p_q = build_godmode_exec_inputs(df, ohlc_all, log_ann, ch, use_quadrant=True,
                                    source_label="ode_w_eth")
    p_noq = build_godmode_exec_inputs(df, ohlc_all, log_ann, ch, use_quadrant=False,
                                      source_label="ode_w_eth")
    p_star_q = build_godmode_exec_inputs(df, ohlc_all, log_ann, ch, use_quadrant=True,
                                         signal_series=wstar_eth, source_label="wstar_eth")
    p_star_noq = build_godmode_exec_inputs(df, ohlc_all, log_ann, ch, use_quadrant=False,
                                           signal_series=wstar_eth, source_label="wstar_eth")
    print(f"  ODE-w:   hth={p_q['hth']:.4f} dth={p_q['dth']:.4f} active={p_q['active_pct']:.1%} "
          f"daily_active={p_q['daily_active_pct']:.1%} avg_psi={p_q['avg_psi']:.3f}")
    print(f"  w_star:  hth={p_star_q['hth']:.4f} dth={p_star_q['dth']:.4f} active={p_star_q['active_pct']:.1%} "
          f"daily_active={p_star_q['daily_active_pct']:.1%} avg_psi={p_star_q['avg_psi']:.3f}")
    print(f"  daily_vol={p_q['daily_vol']:.2%}  GH/TH boost={p_q['q_boost_pct']:.1%}")

    print("\n[4] Running execution-shell variants ...")
    results = {
        "exec_plain_noCB": run_exec_variant("exec_plain_noCB", p_noq, ze7_min=0.0, use_cb=False),
        "exec_CB": run_exec_variant("exec_CB", p_noq, ze7_min=0.0, use_cb=True),
        "exec_ZE7_CB": run_exec_variant("exec_ZE7_CB", p_noq, ze7_min=ZE7_MIN_FORCE, use_cb=True),
        "exec_Q_ZE7_CB": run_exec_variant("exec_Q_ZE7_CB", p_q, ze7_min=ZE7_MIN_FORCE, use_cb=True),
        "star_CB": run_exec_variant("star_CB", p_star_noq, ze7_min=0.0, use_cb=True),
        "star_ZE7_CB": run_exec_variant("star_ZE7_CB", p_star_noq, ze7_min=ZE7_MIN_FORCE, use_cb=True),
        "star_Q_ZE7_CB": run_exec_variant("star_Q_ZE7_CB", p_star_q, ze7_min=ZE7_MIN_FORCE, use_cb=True),
    }

    test_ts = pd.Timestamp(TEST_START)
    print(f"\n{BAR}")
    print("  GODMODE v7 HYBRID RESULTS  (OOS 2023→2026, $1,000, K=3 normal sleeve)")
    print(BAR)
    _print_exec_table(results, test_ts)

    # Reference: raw v_anneal close-to-close, shown separately because it is a
    # multi-asset continuous-weight PnL, not the same ETH trade shell.
    print(f"\n  {'Reference continuous Godmode v_anneal, 1× gross':<54}")
    st = _stats(log_ann["pnl"].iloc[test_mask])
    print(f"  Sharpe={st['sharpe']:+.3f}  MaxDD={st['max_dd']:+.2%}  "
          f"CAGR={st['cagr']:+.2%}  $100→${st['final']:.2f}")

    best_name = max(results.keys(), key=lambda k: equity_metrics(results[k]["eq"][results[k]["eq"].index >= test_ts])["calmar"])
    best = results[best_name]
    best_eq_oos = best["eq"][best["eq"].index >= test_ts]
    print(f"\n  Best by OOS Calmar: {best_name}")
    print(f"  Counts: {best['counts']}")
    print("\n  Best yearly OOS table:")
    for row in period_table(best_eq_oos, "Y"):
        print(f"    {row['period']}: start=${row['start_eq']:,.2f} end=${row['end_eq']:,.2f} "
              f"return={row['return_pct']:+.1%} sharpe={row['sharpe']:+.3f} maxdd={row['maxdd']:+.1%}")

    # Keep old-style YoY table for the underlying continuous signal.
    print_yoy_table("v7_underlying_v_anneal", log_ann["pnl"].iloc[test_mask], [1, 2, 3, 5])

    payload = {
        "meta": {
            "version": "godmode_v7_exec_shell",
            "description": "Godmode v1/v_anneal signal wrapped in old champion execution shell",
            "W_TARGET_A1": W_TARGET_A1,
            "KAPPA_A": KAPPA_A,
            "theta": diag["theta"],
            "ze7_min_force": ZE7_MIN_FORCE,
            "cb_halt": CB_HALT,
            "cb_resume": CB_RESUME,
            "cb_window_days": CB_WINDOW_DAYS,
            "trail_trigger_mult": TRAIL_TRIGGER_MULT,
            "trail_dist_mult": TRAIL_DIST_MULT,
            "DYN_K": DYN_K,
        },
        "signal": {
            "hth": p_q["hth"],
            "dth": p_q["dth"],
            "daily_vol": p_q["daily_vol"],
            "active_pct": p_q["active_pct"],
            "daily_active_pct": p_q["daily_active_pct"],
            "q_boost_pct": p_q["q_boost_pct"],
            "avg_psi": p_q["avg_psi"],
        },
        "continuous_reference": _stats(log_ann["pnl"].iloc[test_mask]),
        "execution_results": {
            name: {
                "full": equity_metrics(res["eq"], name),
                "test": equity_metrics(res["eq"][res["eq"].index >= test_ts], name),
                "counts": res["counts"],
                "pct_halted": res["pct_halted"],
                "n_trips": res["n_trips"],
                "avg_y": res["avg_y"],
            }
            for name, res in results.items()
        },
        "best_by_oos_calmar": best_name,
        "elapsed": time.time() - t0,
    }
    out = OUT_DIR_ / "crypto_godmode_v7_exec_shell.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=float)
    print(f"\n  Saved → {out}")
    print(f"  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()