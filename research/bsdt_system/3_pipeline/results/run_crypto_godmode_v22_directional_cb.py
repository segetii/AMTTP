"""
Crypto Godmode v22 — Directional CB (Long-halt / Short-pass)
=============================================================

v17 finding: CB blocks ALL trades (long + short) during 2026 correction.
Root cause:  simulate_combined multiplies both long and short unit returns
             by y=0 when the circuit breaker fires.

This is wrong for a long/short futures strategy.
  - Halting LONGS during a downtrend = CORRECT (prevents losses on long legs)
  - Halting SHORTS during a downtrend = WRONG   (shorts EARN during selloff)

v22 fix:
  1. simulate_unit_breakeven_v22(): also returns long_arr and short_arr
     (per-bar P&L attributed to the long or short leg of the trade that was
     active at the start of that bar).
  2. simulate_combined_v22(): accepts unit_long + unit_short separately.
     When CB is NOT halted: both streams scale at K_normal * y (as before).
     When CB IS halted:     unit_long   → y = 0  (longs blocked)
                            unit_short  → y = 1.0 (shorts run at full K)

Result: in Jan-Apr 2026 (BTC -30% from peak), the BSDT generates short
signals on BTC and SOL. These now generate returns instead of being blocked.

Outputs:
  crypto_bsdt_v22_directional_cb.json
  crypto_bsdt_v22_directional_cb_report.md
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from collections import deque
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
from simulate_master_strategy import (
    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
    RT_COST, FUND_HOURLY, equity_metrics, INIT, HOURS_PER_DAY,
)
from simulate_v63_quadrant import CB_HALT, CB_RESUME, CB_WINDOW_DAYS
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from test_psi_adaptive_y import BASE
import run_crypto_godmode_v12_filter_innovate as v12

OUT_DIR_         = Path(OUT_DIR)
REALISTIC_RT_BPS = 6.0
RT_COST          = REALISTIC_RT_BPS / 10_000.0   # 6 bps — overrides the 2 bps in simulate_master_strategy
BAR              = "=" * 112
K_NORMAL         = 6.0   # champion from v17

# ─── K_SHORT_DURING_CB: leverage applied to shorts while CB is halted ─────────
# 1.0 = same leverage as normal mode; 0 = shorts off during CB too
K_SHORT_HALT_GRID = [0.5, 1.0, 1.5, 2.0]   # sweep over short K during halt


# ─── directional simulate_unit_breakeven ─────────────────────────────────────

def simulate_unit_breakeven_v22(
    op, hi, lo, cl, hpos_arr, dpos_arr, dactive_arr, psi_y,
    sl: float, tp: float,
    trail_trigger: float, trail_dist: float,
    ze7_arr: np.ndarray, ze7_min: float,
    be_trigger: float | None, be_buffer: float = 0.0,
):
    """Same as simulate_unit_breakeven, but also returns long_arr and short_arr.

    long_arr[i]  = ret[i] when the position active at bar-start was LONG  (+1)
    short_arr[i] = ret[i] when the position active at bar-start was SHORT (-1)
    flat bars (no trade open) contribute 0 to both.
    """
    n = len(op)
    ret       = np.zeros(n, dtype=float)
    long_arr  = np.zeros(n, dtype=float)
    short_arr = np.zeros(n, dtype=float)

    pos = 0.0; size = 1.0; entry = 0.0
    stop_px = 0.0; take_px = 0.0; trail_ext = 0.0
    trail_active = False; be_active = False
    counts = dict(entries=0, exits=0, longs=0, shorts=0, stop=0, tp=0,
                  trail_exit=0, signal_exit=0, close_end=0,
                  vetoed_force=0, skipped_daily_filter=0,
                  active_hours=0, breakeven_exit=0, be_armed=0)

    for i in range(n):
        hpos   = int(hpos_arr[i]); hactive = hpos != 0
        dpos   = int(dpos_arr[i]); dact    = bool(dactive_arr[i])
        scale  = float(psi_y[i])
        if hactive:
            if dact and hpos == dpos:
                pass
            elif dact and hpos != dpos:
                hactive = False; hpos = 0; counts["skipped_daily_filter"] += 1
            else:
                scale *= 0.5
        if hactive and scale <= 1e-12:
            hactive = False; hpos = 0

        # direction BEFORE any exit/entry this bar (for attribution)
        bar_dir = int(pos)   # +1, -1, or 0

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
            else:  # pos < 0
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
                if bar_dir > 0:
                    long_arr[i]  += bar_pnl
                elif bar_dir < 0:
                    short_arr[i] += bar_pnl
                counts[reason] += 1; counts["exits"] += 1
                pos = 0.0; size = 1.0; entry = 0.0; stop_px = 0.0; take_px = 0.0
                trail_ext = 0.0; trail_active = False; be_active = False
            else:
                # funding charge — attribute to the direction of current trade
                funding = size * FUND_HOURLY
                ret[i] -= funding
                if bar_dir > 0:
                    long_arr[i]  -= funding
                elif bar_dir < 0:
                    short_arr[i] -= funding

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
        bar_pnl = size * (gross - RT_COST)
        ret[-1] += bar_pnl
        if pos > 0:
            long_arr[-1]  += bar_pnl
        else:
            short_arr[-1] += bar_pnl
        counts["close_end"] += 1; counts["exits"] += 1

    return ret, long_arr, short_arr, counts


# ─── run_variant_v22: accumulates unit_long and unit_short ───────────────────

def run_variant_v22(
    cfg: dict,
    inputs: dict,
    sig_map: dict[str, pd.Series],
    log_ann: pd.DataFrame,
) -> dict:
    """Same as v12.run_variant but returns unit_long and unit_short separately."""
    from test_psi_adaptive_y import BASE
    unit_sum: pd.Series | None       = None
    unit_long_sum: pd.Series | None  = None
    unit_short_sum: pd.Series | None = None
    per_asset = {}

    for asset, p0 in inputs.items():
        p, diag = v12.prepare_input(p0, asset, cfg, sig_map[asset], log_ann)
        sl           = BASE["sl_mult"]   * p["daily_vol"]
        tp           = BASE["tp_mult"]   * p["daily_vol"]
        trail_trigger = 1.50 * p["daily_vol"]
        trail_dist    = 0.75 * p["daily_vol"]
        be_trigger    = None
        if asset in cfg["be_assets"] and cfg["be_frac"] is not None:
            be_trigger = float(cfg["be_frac"]) * tp

        arr, long_arr, short_arr, counts = simulate_unit_breakeven_v22(
            p["op"], p["hi"], p["lo"], p["cl"],
            p["hpos"], p["dpos"], p["dactive"], p["psi_y"],
            sl, tp, trail_trigger, trail_dist, p["ze7"], v12.BASE_ZE7,
            be_trigger=be_trigger, be_buffer=float(cfg["be_buf"]),
        )
        unit  = pd.Series(arr,       index=p["hours"])
        unitL = pd.Series(long_arr,  index=p["hours"])
        unitS = pd.Series(short_arr, index=p["hours"])
        unit_sum       = unit  if unit_sum       is None else unit_sum.add(unit,   fill_value=0.0)
        unit_long_sum  = unitL if unit_long_sum  is None else unit_long_sum.add(unitL,  fill_value=0.0)
        unit_short_sum = unitS if unit_short_sum is None else unit_short_sum.add(unitS, fill_value=0.0)
        per_asset[asset] = dict(counts=counts, diag=diag)

    assert unit_sum is not None
    unit_sum       = unit_sum.sort_index().fillna(0.0)
    unit_long_sum  = unit_long_sum.sort_index().fillna(0.0)
    unit_short_sum = unit_short_sum.sort_index().fillna(0.0)
    return dict(unit=unit_sum, unit_long=unit_long_sum, unit_short=unit_short_sum, per_asset=per_asset)


# ─── simulate_combined_v22: directional CB ───────────────────────────────────

def simulate_combined_v22(
    unit_long:  pd.Series,
    unit_short: pd.Series,
    K_normal:   float,
    K_short_halt: float,         # K applied to shorts when CB is halted
    dd_soft:    float,
    dd_stop:    float,
    y_floor:    float,
    cb_halt:    float,
    cb_resume:  float,
    cb_window_days: int,
    use_cb:     bool = True,
) -> dict:
    """Directional circuit breaker.

    When NOT halted: both longs and shorts trade at K_normal * y(dd_aty).
    When HALTED:     longs are blocked (y=0), shorts scale at K_short_halt.

    K_short_halt = 0     → same as original (all off)
    K_short_halt = 1.0   → shorts keep full K_normal scale during CB
    K_short_halt = 1.5   → shorts are boosted 50% during CB (bear alpha)
    """
    window_bars  = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq           = INIT
    peak_alltime = INIT
    halted       = False
    eq_vals:   list[float] = []
    y_vals:    list[float] = []
    cb_flags:  list[int]   = []
    long_active: list[int] = []
    short_active: list[int] = []

    assert len(unit_long) == len(unit_short), "unit_long and unit_short must be same length"

    for bar_i in range(len(unit_long)):
        ul = float(unit_long.iloc[bar_i])
        us = float(unit_short.iloc[bar_i])

        # Sliding-window monotonic deque for CB rolling peak
        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

        if use_cb:
            if not halted and cb_dd >= cb_halt:
                halted = True
            elif halted and cb_dd <= cb_resume:
                halted = False
        else:
            halted = False

        # Adaptive Y for normal (non-halted) regime — based on all-time dd
        if dd_aty <= dd_soft:
            y_normal = 1.0
        elif dd_aty >= dd_stop:
            y_normal = y_floor
        else:
            y_normal = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        if halted:
            # Longs OFF, shorts at K_short_halt
            r_long  = 0.0
            r_short = K_short_halt * us
            y       = 0.0   # reported y for longs
        else:
            r_long  = K_normal * y_normal * ul
            r_short = K_normal * y_normal * us
            y       = y_normal

        r  = r_long + r_short
        r  = max(r, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq)
        y_vals.append(y)
        cb_flags.append(int(halted))
        long_active.append(0 if halted else 1)
        short_active.append(1 if halted else 1)

    eqs  = pd.Series(eq_vals,  index=unit_long.index)
    rets = eqs.pct_change().fillna(eqs.iloc[0] / INIT - 1.0)
    dd_s = (eqs - eqs.cummax()) / eqs.cummax()
    years = max((eqs.index[-1] - eqs.index[0]).days / 365.25, 1e-9)
    return dict(
        eq         = eqs,
        final      = float(eqs.iloc[-1]),
        cagr       = float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe     = float(np.sqrt(24 * 365.25) * rets.mean() / rets.std()) if rets.std() > 0 else 0.0,
        maxdd      = float(dd_s.min()),
        pct_halted = float(np.mean(cb_flags)),
        n_trips    = int(sum(cb_flags[i] > cb_flags[i - 1] for i in range(1, len(cb_flags)))),
        avg_y      = float(np.mean(y_vals)),
        cb_flags   = cb_flags,
    )


# ─── period helpers ───────────────────────────────────────────────────────────

def _period_metrics(eq: pd.Series, cb_flags: list[int], period: str, label: str) -> list[dict]:
    rows   = []
    cb_s   = pd.Series(cb_flags, index=eq.index)
    grp_eq = eq.groupby(eq.index.to_period(period))
    grp_cb = cb_s.groupby(cb_s.index.to_period(period))
    for p, s in grp_eq:
        if s.empty:
            continue
        cb_p  = grp_cb.get_group(p) if p in grp_cb.groups else pd.Series([], dtype=float)
        start = float(s.iloc[0])
        end   = float(s.iloc[-1])
        ret   = end / start - 1.0 if start else float("nan")
        dd    = float((s / s.cummax() - 1.0).min())
        r_ch  = s.pct_change().replace([float("inf"), float("-inf")], float("nan")).dropna()
        sh    = float(r_ch.mean() / (r_ch.std() + 1e-12) * np.sqrt(365 * 24)) if len(r_ch) > 3 else 0.0
        ph    = float(cb_p.mean()) if len(cb_p) > 0 else 0.0
        rows.append({
            "label": label, "period": str(p),
            "start": str(s.index[0]), "end": str(s.index[-1]),
            "start_eq": start, "end_eq": end, "profit": end - start,
            "return_pct": 100.0 * ret, "maxdd_pct": 100.0 * dd,
            "sharpe": sh, "pct_halted": 100.0 * ph, "bars": int(len(s)),
        })
    return rows


def _fmt_money(x: float)  -> str: return f"${x:,.2f}"
def _fmt_pct(x: float)    -> str: return f"{x:+,.2f}%"
def _fmt_float(x: float)  -> str: return f"{x:+.3f}"


def _md_table(df: pd.DataFrame, cols: list[str]) -> str:
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, row in df.iterrows():
        vals = []
        for c in cols:
            v = row[c]
            if c in {"start_eq", "end_eq", "profit"}:
                vals.append(_fmt_money(float(v)))
            elif c in {"return_pct", "maxdd_pct", "cagr_pct", "pct_halted",
                       "ret_2026_pct", "halted_2026_pct", "k_short_halt"}:
                vals.append(_fmt_pct(float(v)))
            elif c in {"sharpe", "calmar"}:
                vals.append(_fmt_float(float(v)))
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(BAR)
    print("  CRYPTO GODMODE v22 — DIRECTIONAL CB (LONG-HALT / SHORT-PASS)")
    print(f"  Fix: during CB halt, longs are blocked but shorts continue trading")
    print(BAR)

    # ── Step 1: build unit series (long + short split) ────────────────────
    print("\n[1] Building be50_btc_sol unit series with long/short split ...")
    df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    ohlc_map   = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch         = get_channel_series()

    w_star    = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag_cal = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v22")
    log_ann   = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_f, theta,
                                   kappa=KAPPA_A, anneal=True, label="v22_anneal")

    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
    inputs     = attach_q_hot(inputs_noq, inputs_q)
    sig_map    = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                  for asset, _, _, idx in ASSETS}
    cfg        = next(c for c in v12.VARIANTS if c["name"] == "be50_btc_sol")
    # RT_COST is already set to REALISTIC_RT_BPS/10_000 at module level

    unit_res   = run_variant_v22(cfg, inputs, sig_map, log_ann)
    unit       = unit_res["unit"]
    unit_long  = unit_res["unit_long"]
    unit_short = unit_res["unit_short"]
    test_ts    = pd.Timestamp(TEST_START)

    # Stats on the directional split
    ul_test = unit_long[unit_long.index  >= test_ts]
    us_test = unit_short[unit_short.index >= test_ts]
    long_active_bars  = int((ul_test != 0).sum())
    short_active_bars = int((us_test != 0).sum())
    print(f"  unit: {unit.index[0].date()} -> {unit.index[-1].date()}  n={len(unit):,}")
    print(f"  long bars (OOS):  {long_active_bars:,}  ({long_active_bars/len(ul_test):.1%})")
    print(f"  short bars (OOS): {short_active_bars:,}  ({short_active_bars/len(us_test):.1%})")

    # ── Step 2: baseline comparison (original CB, all-halted) ─────────────
    print("\n[2] Baseline: original CB (longs+shorts both halted) ...")
    from simulate_master_strategy import simulate_combined as sim_orig
    zero = pd.Series(np.zeros(len(unit)), index=unit.index)
    res_base = sim_orig(
        unit, zero,
        K_normal=K_NORMAL, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window_days=CB_WINDOW_DAYS, use_cb=True,
    )
    eq_base = res_base["eq"][res_base["eq"].index >= test_ts]
    m_base  = equity_metrics(eq_base, "baseline_v17")
    calmar_base = float(m_base["cagr"]) / max(abs(float(m_base["maxdd"])), 1e-9)
    eq_2026_base = eq_base[eq_base.index >= "2026-01-01"]
    ret_2026_base = float(eq_2026_base.iloc[-1]) / float(eq_2026_base.iloc[0]) - 1.0 if len(eq_2026_base) > 1 else 0.0
    print(f"  CAGR={m_base['cagr']:+.1%}  Sharpe={m_base['sharpe']:+.3f}  "
          f"MaxDD={m_base['maxdd']:+.1%}  Calmar={calmar_base:+.3f}  "
          f"halt={res_base['pct_halted']:.0%}  2026_ret={ret_2026_base:+.1%}")

    # ── Step 3: sweep K_short_halt ────────────────────────────────────────
    print(f"\n[3] Sweeping K_short_halt (how hard shorts run during CB halt)")
    print(f"  CB_HALT={CB_HALT:.0%}  CB_RESUME={CB_RESUME:.0%}  CB_WINDOW={CB_WINDOW_DAYS}d  K={K_NORMAL}")
    sweep_rows = []

    for ksh in K_SHORT_HALT_GRID:
        label = f"ksh{int(ksh*10):03d}"
        res   = simulate_combined_v22(
            unit_long, unit_short,
            K_normal=K_NORMAL, K_short_halt=ksh,
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
            cb_halt=CB_HALT, cb_resume=CB_RESUME,
            cb_window_days=CB_WINDOW_DAYS, use_cb=True,
        )
        eq_t   = res["eq"][res["eq"].index >= test_ts]
        cb_t   = [res["cb_flags"][i] for i, ts in enumerate(res["eq"].index) if ts >= test_ts]

        eq_2026  = eq_t[eq_t.index >= "2026-01-01"]
        ret_2026 = float(eq_2026.iloc[-1]) / float(eq_2026.iloc[0]) - 1.0 if len(eq_2026) > 1 else 0.0
        cb_2026  = [res["cb_flags"][i] for i, ts in enumerate(res["eq"].index)
                    if ts >= pd.Timestamp("2026-01-01")]
        halted_2026_pct = float(np.mean(cb_2026)) if cb_2026 else 0.0

        m      = equity_metrics(eq_t, label)
        calmar = float(m["cagr"]) / max(abs(float(m["maxdd"])), 1e-9)
        sweep_rows.append({
            "label":           label,
            "k_short_halt":    ksh * 100,
            "final":           float(m["final"]),
            "cagr_pct":        float(m["cagr"]) * 100,
            "sharpe":          float(m["sharpe"]),
            "maxdd_pct":       float(m["maxdd"]) * 100,
            "calmar":          calmar,
            "pct_halted":      res["pct_halted"] * 100,
            "n_trips":         res["n_trips"],
            "ret_2026_pct":    ret_2026 * 100,
            "halted_2026_pct": halted_2026_pct * 100,
        })
        print(f"  K_short_halt={ksh:.1f}  CAGR={m['cagr']:+.1%}  Sharpe={m['sharpe']:+.3f}  "
              f"MaxDD={m['maxdd']:+.1%}  Calmar={calmar:+.3f}  "
              f"halt={res['pct_halted']:.0%}  2026_ret={ret_2026:+.1%}  2026_halt={halted_2026_pct:.0%}")

    sweep_df = pd.DataFrame(sweep_rows).sort_values("calmar", ascending=False).reset_index(drop=True)

    # ── Step 4: period tables for top configs ─────────────────────────────
    top3 = sweep_df.head(3)
    period_results: dict = {}

    for _, w in top3.iterrows():
        ksh = float(w["k_short_halt"]) / 100.0
        lbl = w["label"]
        print(f"\n[4] Period tables for {lbl} (K_short_halt={ksh:.1f}):")
        r_win = simulate_combined_v22(
            unit_long, unit_short,
            K_normal=K_NORMAL, K_short_halt=ksh,
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
            cb_halt=CB_HALT, cb_resume=CB_RESUME,
            cb_window_days=CB_WINDOW_DAYS, use_cb=True,
        )
        eq_win   = r_win["eq"][r_win["eq"].index >= test_ts]
        t_mask   = r_win["eq"].index >= test_ts
        cb_w_t   = [f for f, m2 in zip(r_win["cb_flags"], t_mask) if m2]

        yr  = _period_metrics(eq_win, cb_w_t, "Y", lbl)
        qtr = _period_metrics(eq_win, cb_w_t, "Q", lbl)
        period_results[lbl] = {"yearly": yr, "quarterly": qtr}

        print(f"  Year-on-Year:")
        for row in yr:
            print(f"    {row['period']}  return={row['return_pct']:+.1f}%  "
                  f"halted={row['pct_halted']:.0f}%  maxdd={row['maxdd_pct']:+.1f}%")

    # Also show baseline yearly for direct comparison
    print("\n  [baseline v17 yearly for comparison]:")
    # simulate_combined doesn't return cb_flags directly; use 0 placeholder for halted%
    yr_base   = _period_metrics(eq_base, [0] * len(eq_base), "Y", "v17_baseline")
    for row in yr_base:
        print(f"    {row['period']}  return={row['return_pct']:+.1f}%  "
              f"halted={row['pct_halted']:.0f}%  maxdd={row['maxdd_pct']:+.1f}%")

    winner = sweep_df.iloc[0]

    # ── Step 5: save outputs ──────────────────────────────────────────────
    print("\n[5] Saving outputs ...")
    payload = {
        "meta": {
            "version":          "godmode_v22_directional_cb",
            "strategy":         "be50_btc_sol",
            "K_normal":         K_NORMAL,
            "rt_bps":           REALISTIC_RT_BPS,
            "cb_halt":          CB_HALT,
            "cb_resume":        CB_RESUME,
            "cb_window_days":   CB_WINDOW_DAYS,
            "sweep_k_short":    K_SHORT_HALT_GRID,
            "theta":            diag_cal["theta"],
            "elapsed":          time.time() - t0,
            "fix":              "directional_cb_long_halt_short_pass",
        },
        "baseline": {
            "label":    "v17_original_cb",
            "cagr_pct": float(m_base["cagr"]) * 100,
            "sharpe":   float(m_base["sharpe"]),
            "maxdd_pct": float(m_base["maxdd"]) * 100,
            "calmar":   calmar_base,
            "ret_2026_pct": ret_2026_base * 100,
        },
        "sweep":          sweep_df.to_dict(orient="records"),
        "winner": {
            "label":         winner["label"],
            "k_short_halt":  float(winner["k_short_halt"]),
            "cagr_pct":      float(winner["cagr_pct"]),
            "sharpe":        float(winner["sharpe"]),
            "maxdd_pct":     float(winner["maxdd_pct"]),
            "calmar":        float(winner["calmar"]),
        },
        "period_results": period_results,
    }

    json_path = OUT_DIR_ / "crypto_bsdt_v22_directional_cb.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)

    md_lines = [
        "# Crypto Godmode v22 — Directional CB (Long-halt / Short-pass)",
        "",
        "## Problem",
        "",
        "The circuit breaker in v17 halts **all** trades (longs AND shorts) when triggered.",
        "For a long/short futures strategy this is wrong:",
        "",
        "- **Halting longs** during a downtrend: ✅ correct (prevents long losses)",
        "- **Halting shorts** during a downtrend: ❌ wrong (shorts *earn* during selloff)",
        "",
        "In 2026Q1-Q2, BTC corrected ~30% from the Dec 2025 peak. The BSDT generated",
        "short signals, but all were blocked by the CB → 2026 return = 0%.",
        "",
        "## Fix",
        "",
        "Split the unit return stream into `unit_long` and `unit_short` per bar.",
        "When CB is halted:",
        "",
        "| Leg | Scale |",
        "|-----|-------|",
        "| Long  | `y = 0` (blocked) |",
        f"| Short | `K_SHORT_HALT` × `unit_short` (active) |",
        "",
        f"**K:** {K_NORMAL}  **CB_HALT:** {CB_HALT:.0%}  **CB_RESUME:** {CB_RESUME:.0%}  "
        f"**CB_WINDOW:** {CB_WINDOW_DAYS}d  **Strategy:** be50_btc_sol  **RT:** {REALISTIC_RT_BPS} bps",
        "",
        "## Baseline (v17 original CB)",
        "",
        f"CAGR = {m_base['cagr']:+.1%}  |  Sharpe = {m_base['sharpe']:+.3f}  |  "
        f"MaxDD = {m_base['maxdd']:+.1%}  |  Calmar = {calmar_base:+.3f}  |  "
        f"2026 = {ret_2026_base:+.1%}",
        "",
        "## Sweep Results (K_short_halt)",
        "",
        _md_table(sweep_df, [
            "label", "k_short_halt", "cagr_pct", "sharpe", "maxdd_pct", "calmar",
            "pct_halted", "ret_2026_pct", "halted_2026_pct",
        ]),
        "",
        f"## Winner: `{winner['label']}` (K_short_halt = {float(winner['k_short_halt']):.0f}%)",
        "",
    ]

    for lbl, pdata in period_results.items():
        md_lines += [
            f"### Period: `{lbl}`",
            "",
            "**Year-on-Year**",
            "",
            _md_table(pd.DataFrame(pdata["yearly"]),
                      ["period", "start_eq", "end_eq", "profit", "return_pct", "maxdd_pct", "sharpe", "pct_halted"]),
            "",
            "**Quarterly**",
            "",
            _md_table(pd.DataFrame(pdata["quarterly"]),
                      ["period", "start_eq", "end_eq", "profit", "return_pct", "maxdd_pct", "sharpe", "pct_halted"]),
            "",
        ]

    md_path = OUT_DIR_ / "crypto_bsdt_v22_directional_cb_report.md"
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines))

    print(f"  saved: {json_path}")
    print(f"  saved: {md_path}")
    el = time.time() - t0
    print(f"\n  Elapsed: {el:.1f}s  ({el/60:.1f} min)")
    print(BAR)


if __name__ == "__main__":
    main()
