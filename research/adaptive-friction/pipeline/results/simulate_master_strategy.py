"""Master Strategy Simulation — Three-Pillar Risk/Return Architecture.

PILLAR 1 — TRAILING STOP (Protect Profit)
    Once a position is TRAIL_TRIGGER% in profit, the stop-loss chases the
    rolling high (long) / rolling low (short) staying TRAIL_DIST% behind it.
    This locks in profit on winners that reverse before hitting fixed TP.
    Inactive positions still use the original sigma-calibrated stop.

TIMEFRAME DESIGN — 1h primary + 2h confirmation
    The daily filter is removed.  A 2-hour signal (last geometry value of each
    2h bar, shifted 1 bar causal) acts as the fast confirmation timeframe.
    2h agrees with 1h → full size.  2h disagrees → skip.  2h inactive → half.
    This keeps both signals intraday, eliminates overnight lag, and reduces
    the over-filtering that buried entries during trending days.

PILLAR 2 — CIRCUIT BREAKER (Limit Drawdown)
    CB-cash: halt new geometry entries when the portfolio's rolling-90d
    drawdown exceeds 18%.  Resume at 13%.  Proven champion (Calmar 2.58).

PILLAR 3 — REAL CRASH SHORTS (Profit From Collapse)
    Independent of the geometry signal entirely.
    Trigger: ETH 12h return < CRASH_RET_THRESH  AND  24h realized vol > VOL_MULT × baseline
    Trade:   SHORT ETH at next open, SL = +CRASH_SL above entry,
             TP = −CRASH_TP below entry, time-exit after CRASH_MAX_HOURS.
    This catches acute collapses (Luna 2022, FTX 2022, tariff-crash Apr 2025)
    *after* they've started but while there is still continuation downside.

Strategy Grid (OOS 2023→today):
    [A] Baseline K=3     (no trail, no CB, no crash)
    [B] CB-cash          (no trail, no crash)    ← previous champion
    [C] Trail-only       (no CB, no crash)
    [D] CB + Trail       (no crash)
    [E] Crash-short only (no trail, no CB)
    [F] CB + Crash       (no trail)
    [G] CB + Trail + Crash  ← master strategy candidate

Mini-grid on (trail_trigger, trail_dist) × K_crash within strategy G.
"""
from __future__ import annotations
import json, time
from collections import deque
from pathlib import Path
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS
from test_daily_geometry_stop_tp_ohlc   import build_daily_geometry, fetch_futures_ohlcv
from test_psi_adaptive_y                import BASE, simulate_unit_with_psi
from simulate_adaptive_y_drawdown_brake import adaptive_equity, INIT
from test_dynamic_profit_sizing         import _percentile_against

OUT = Path(OUT_DIR) / 'simulation_master_strategy.json'
BAR = '=' * 110
SEP = '-' * 110

RT_COST       = 2.0 / 1e4
FUND_HOURLY   = 0.5 / 1e4 / 24.0
HOURS_PER_DAY = 24

# Normal-mode champion params
DYN_K            = 3.0
DYN_STRENGTH_CAP = 2.5
DYN_VOL_CAP      = 3.0
DYN_TOTAL_CAP    = 2.0
DYN_DD_SOFT      = 0.05
DYN_DD_STOP      = 0.20
DYN_Y_FLOOR      = 0.25

# CB champion params (daily-filter champion: 90d/18%/13%)
CB_HALT        = 0.18
CB_RESUME      = 0.13
CB_WINDOW_DAYS = 90

# Crash-short params
CRASH_RET_THRESH  = -0.06    # ETH 12h return must be worse than -6%
CRASH_VOL_MULT    = 2.5      # 24h realized vol must be > 2.5× training median
CRASH_SL          = 0.04     # stop 4% above entry (short)
CRASH_TP          = 0.10     # TP 10% below entry (short)
CRASH_MAX_HOURS   = 36       # time exit if neither SL nor TP hit

# Grids to sweep
TRAIL_GRID   = [
    dict(trigger_mult=0.0,  dist_mult=0.0),    # no trail (baseline)
    dict(trigger_mult=0.7,  dist_mult=0.35),   # tight trail
    dict(trigger_mult=1.0,  dist_mult=0.50),   # medium trail  ← default
    dict(trigger_mult=1.5,  dist_mult=0.75),   # wide trail
]
K_CRASH_GRID = [0.0, 1.0, 1.5, 2.0]           # 0.0 = crash-short disabled


# ─────────────────────────────────────────────────────────────────────────────
#  METRICS
# ─────────────────────────────────────────────────────────────────────────────

def equity_metrics(eq: pd.Series, label: str = '') -> dict:
    r     = eq.pct_change().fillna(eq.iloc[0] / INIT - 1.0)
    dd    = (eq - eq.cummax()) / eq.cummax()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    calmar = float((eq.iloc[-1] / INIT) ** (1 / years) - 1) / max(abs(float(dd.min())), 1e-9)
    return dict(
        label=label, final=float(eq.iloc[-1]), profit=float(eq.iloc[-1]-INIT),
        return_pct=float(eq.iloc[-1]/INIT-1.0),
        cagr=float((eq.iloc[-1]/INIT)**(1/years)-1.0),
        sharpe=float(np.sqrt(24*365.25)*r.mean()/r.std()) if r.std()>0 else 0.0,
        maxdd=float(dd.min()), calmar=calmar,
        start=str(eq.index[0]), end=str(eq.index[-1]),
    )


def period_table(eq: pd.Series, freq: str) -> list[dict]:
    rows = []
    for dt, s in eq.groupby(pd.Grouper(freq=freq)):
        if len(s) < 2: continue
        r  = s.pct_change().dropna()
        dd = (s - s.cummax()) / s.cummax()
        rows.append(dict(
            period=str(dt.date()),
            start_eq=round(float(s.iloc[0]),2), end_eq=round(float(s.iloc[-1]),2),
            profit=round(float(s.iloc[-1]-s.iloc[0]),2),
            return_pct=round(float(s.iloc[-1]/s.iloc[0]-1.0),4),
            sharpe=round(float(np.sqrt(24*365.25)*r.mean()/r.std()),3) if r.std()>0 else 0.0,
            maxdd=round(float(dd.min()),4),
        ))
    return rows


def drawdown_periods(eq: pd.Series, top_n: int = 6) -> list[dict]:
    peak  = eq.cummax()
    dd    = (eq - peak) / peak
    rows  = []
    in_dd = False; start = None; peak_val = None
    for ts, val in dd.items():
        if not in_dd and val < -1e-4:
            in_dd = True; start = ts; peak_val = float(peak[ts])
        elif in_dd and val >= -1e-4:
            t = dd[start:ts].idxmin()
            rows.append(dict(dd_start=str(start), trough=str(t), dd_end=str(ts),
                             drawdown=float(dd[t]), peak_eq=peak_val,
                             trough_eq=float(eq[t]),
                             duration_days=int((ts-start).days)))
            in_dd = False
    if in_dd:
        t = dd[start:].idxmin()
        rows.append(dict(dd_start=str(start), trough=str(t), dd_end='ongoing',
                         drawdown=float(dd[t]), peak_eq=peak_val,
                         trough_eq=float(eq[t]),
                         duration_days=int((eq.index[-1]-start).days)))
    rows.sort(key=lambda r: r['drawdown'])
    return rows[:top_n]


def print_metrics(m: dict):
    print(f"  {'label':<28} {m.get('label','')}")
    print(f"  {'period':<28} {m['start'][:10]}  →  {m['end'][:10]}")
    print(f"  {'final equity':<28} ${m['final']:>12,.2f}   (started ${INIT:,.0f})")
    print(f"  {'profit':<28} ${m['profit']:>+12,.2f}   ({m['return_pct']:>+.1%})")
    print(f"  {'CAGR':<28} {m['cagr']:>+.2%}")
    print(f"  {'Sharpe':<28} {m['sharpe']:>+.3f}")
    print(f"  {'MaxDD':<28} {m['maxdd']:>+.2%}")
    print(f"  {'Calmar':<28} {m['calmar']:>+.3f}")


def print_yearly(rows):
    print(f"  {'Year':<8} {'Start':>10} {'End':>10} {'P&L':>10} {'Ret':>8} {'Sharpe':>8} {'MaxDD':>8}")
    for r in rows:
        print(f"  {r['period']:<8} {r['start_eq']:>10,.2f} {r['end_eq']:>10,.2f} "
              f"  {r['profit']:>+9,.2f}  {r['return_pct']:>+7.1%} {r['sharpe']:>+8.3f} {r['maxdd']:>+7.2%}")


def print_dd(rows):
    print(f"  {'Start':<14} {'Trough':<14} {'End':<14} {'DD':>8} {'Days':>6} {'Peak$':>10} {'Trough$':>10}")
    for r in rows:
        end = r['dd_end'][:10] if r['dd_end'] != 'ongoing' else 'ongoing'
        print(f"  {r['dd_start'][:10]:<14} {r['trough'][:10]:<14} {end:<14} "
              f"{r['drawdown']:>+7.2%} {r['duration_days']:>6,d} "
              f"{r['peak_eq']:>10,.2f} {r['trough_eq']:>10,.2f}")


# ─────────────────────────────────────────────────────────────────────────────
#  PILLAR 1 — TRAILING STOP PER-BAR SIMULATOR
#  Mirrors simulate_unit_with_psi exactly, adds trailing stop logic.
# ─────────────────────────────────────────────────────────────────────────────

def simulate_unit_trailing(op, hi, lo, cl,
                            hpos_arr, dpos_arr, dactive_arr,
                            psi_y,
                            sl: float, tp: float,
                            trail_trigger: float, trail_dist: float):
    """Geometry strategy with trailing stop.

    sl, tp          : initial stop/TP distances as fractions of entry price.
    trail_trigger   : un-realised gain fraction at which trailing activates.
                      Set = 0 to trail from the very start (aggressive).
                      Set = sl to trail only once we have covered the initial risk.
    trail_dist      : how far behind the rolling extreme the trail sits.
                      E.g. trail_dist=0.025 → stop = rolling_high × (1−0.025) for longs.

    If trail_trigger == 0 and trail_dist == 0: identical to simulate_unit_with_psi.
    """
    n    = len(op)
    ret  = np.zeros(n, dtype=float)
    pos  = 0.0; size = 1.0; entry = 0.0
    stop_price = 0.0; take_price = 0.0
    trail_active   = False
    trail_extreme  = 0.0        # rolling high (long) or rolling low (short)
    trailing_on    = (trail_trigger > 0 or trail_dist > 0)

    counts = dict(entries=0, exits=0, flips=0, longs=0, shorts=0,
                  stop=0, tp=0, signal_exit=0, close_end=0,
                  trail_exit=0,
                  skipped_daily_filter=0, psi_blocked=0,
                  active_hours=0)
    psi_sizes = []

    for i in range(n):
        hpos   = hpos_arr[i]; hactive = hpos != 0
        dpos_i = dpos_arr[i]; dact_i  = dactive_arr[i]
        scale  = 1.0

        # ── daily context filter (daily agree → full, daily disagrees → skip, inactive → half) ──
        if hactive:
            if   dact_i and hpos == dpos_i:    scale = 1.0
            elif dact_i and hpos != dpos_i:
                hactive = False; hpos = 0;     counts['skipped_daily_filter'] += 1
            else:                              scale = 0.5
        if hactive:
            scale *= psi_y[i]
            if scale <= 1e-12:
                hactive = False; hpos = 0;     counts['psi_blocked'] += 1

        # ── manage open position ──
        if pos != 0:
            counts['active_hours'] += 1
            exit_ret = None; reason = None

            if pos > 0:
                # 1. Check TP first (price spiked high enough)
                if hi[i] >= take_price:
                    exit_ret = take_price / entry - 1; reason = 'tp'
                else:
                    # 2. Update trailing extreme → possibly raise stop
                    if trailing_on:
                        trail_extreme = max(trail_extreme, hi[i])
                        unreal = trail_extreme / entry - 1.0
                        if unreal >= trail_trigger:
                            trail_active = True
                        if trail_active:
                            new_ts = trail_extreme * (1.0 - trail_dist)
                            if new_ts > stop_price:
                                stop_price = new_ts   # only move up, never down
                    # 3. Check stop (original or trailed)
                    if lo[i] <= stop_price:
                        # Use stop_price as exit; if trail moved stop above entry → profit
                        exit_price = min(op[i], stop_price) if op[i] < stop_price else stop_price
                        # Note: gap opens below stop → exit at open (worse than stop)
                        exit_price = min(stop_price, max(lo[i], stop_price))
                        # Simplified: fill at stop_price (limit assumption)
                        exit_ret = stop_price / entry - 1
                        reason   = 'trail_exit' if trail_active else 'stop'
            else:  # short
                # 1. Check TP first (price fell far enough)
                if lo[i] <= take_price:
                    exit_ret = entry / take_price - 1; reason = 'tp'
                else:
                    # 2. Update trailing extreme → possibly lower stop
                    if trailing_on:
                        trail_extreme = min(trail_extreme, lo[i])
                        unreal = entry / trail_extreme - 1.0
                        if unreal >= trail_trigger:
                            trail_active = True
                        if trail_active:
                            new_ts = trail_extreme * (1.0 + trail_dist)
                            if new_ts < stop_price:
                                stop_price = new_ts   # only move down
                    # 3. Check stop
                    if hi[i] >= stop_price:
                        exit_ret = entry / stop_price - 1
                        reason   = 'trail_exit' if trail_active else 'stop'

            # 4. Signal flip exit (no other exit triggered this bar)
            if exit_ret is None and hactive and hpos == -pos:
                exit_ret = (op[i] / entry - 1) if pos > 0 else (entry / op[i] - 1)
                reason   = 'signal_exit'; counts['flips'] += 1

            if exit_ret is not None:
                ret[i] += size * (exit_ret - RT_COST)
                counts[reason] += 1; counts['exits'] += 1
                pos    = 0; size = 1; entry = 0
                stop_price = 0; take_price = 0
                trail_active = False; trail_extreme = 0.0
            else:
                ret[i] -= size * FUND_HOURLY

        # ── open new position ──
        if pos == 0 and hactive:
            pos   = float(hpos); size = float(scale); entry = float(op[i])
            psi_sizes.append(float(psi_y[i]))
            trail_active  = False
            trail_extreme = float(op[i])  # rolling extreme starts at entry
            if pos > 0:  # long
                stop_price = entry * (1.0 - sl)
                take_price = entry * (1.0 + tp)
                counts['longs'] += 1
            else:         # short
                stop_price = entry * (1.0 + sl)
                take_price = entry * (1.0 - tp)
                counts['shorts'] += 1
            counts['entries'] += 1

    # close at end-of-series
    if pos != 0:
        i = n - 1
        gross = (cl[i] / entry - 1) if pos > 0 else (entry / cl[i] - 1)
        ret[i] += size * (gross - RT_COST)
        counts['close_end'] += 1; counts['exits'] += 1

    counts['avg_psi_y'] = float(np.mean(psi_sizes)) if psi_sizes else 0.0
    return ret, counts


# ─────────────────────────────────────────────────────────────────────────────
#  PILLAR 3 — CRASH SHORT SIMULATOR
#  Independent of geometry signal.  Returns unit returns at size=1.0.
# ─────────────────────────────────────────────────────────────────────────────

def simulate_crash_shorts(op, hi, lo, cl, crash_signal,
                           crash_sl: float, crash_tp: float,
                           crash_max_hours: int) -> tuple:
    """Enter short when crash_signal[i]=1 and not already in a position.

    crash_signal must be causal (already shifted 1 bar relative to the
    condition that produced it).

    Returns (unit_returns_array, counts).
    unit_returns includes RT cost but not K scaling (applied externally).
    """
    n     = len(op)
    ret   = np.zeros(n, dtype=float)
    pos   = 0; entry = 0.0; stop_price = 0.0; take_price = 0.0
    held  = 0
    counts = dict(entries=0, exits=0, stop=0, tp=0, time_exit=0)

    for i in range(n):
        if pos != 0:
            held += 1
            exit_ret = None; reason = None
            # Short: stop = hi >= stop (above entry), tp = lo <= take (below entry)
            if hi[i] >= stop_price:
                exit_ret = entry / stop_price - 1; reason = 'stop'
            elif lo[i] <= take_price:
                exit_ret = entry / take_price - 1; reason = 'tp'
            elif held >= crash_max_hours:
                # Time exit at close (neutral, let the market settle)
                exit_ret = entry / cl[i] - 1; reason = 'time_exit'

            if exit_ret is not None:
                ret[i] += exit_ret - RT_COST
                pos = 0; held = 0
                counts[reason] += 1; counts['exits'] += 1
            else:
                ret[i] -= FUND_HOURLY  # funding cost while holding short

        if pos == 0 and crash_signal[i]:
            entry      = float(op[i])
            stop_price = entry * (1.0 + crash_sl)   # above entry
            take_price = entry * (1.0 - crash_tp)   # below entry
            pos = -1; held = 0
            counts['entries'] += 1

    return ret, counts


# ─────────────────────────────────────────────────────────────────────────────
#  COMBINED 3-STATE EQUITY ENGINE
#  Normal trades + crash overlay run simultaneously.
#  CB only gates the normal trades; crash shorts are always active.
# ─────────────────────────────────────────────────────────────────────────────

def simulate_combined(unit_normal: pd.Series,
                      unit_crash:  pd.Series,
                      K_normal:    float,
                      K_crash:     float,
                      dd_soft:     float,
                      dd_stop:     float,
                      y_floor:     float,
                      cb_halt:     float,
                      cb_resume:   float,
                      cb_window_days: int,
                      use_cb:      bool = True) -> dict:
    """Combine normal geometry trades + independent crash shorts.

    unit_normal : per-bar returns already scaled by size_mult (K not yet applied)
    unit_crash  : per-bar returns from crash shorts at size=1 (K_crash not applied)

    Returns the combined equity Series plus diagnostics.
    """
    window_bars  = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq = INIT; peak_alltime = INIT; halted = False
    eq_vals = []; y_vals = []; cb_flags = []

    for bar_i in range(len(unit_normal)):
        ur_n = float(unit_normal.iloc[bar_i])
        ur_c = float(unit_crash.iloc[bar_i])

        # Sliding-window max for CB
        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

        if use_cb:
            if not halted and cb_dd >= cb_halt:   halted = True
            elif  halted and cb_dd <= cb_resume:  halted = False
        else:
            halted = False

        # Adaptive Y for normal leg
        if halted:
            y = 0.0
        elif dd_aty <= dd_soft:
            y = 1.0
        elif dd_aty >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        r = K_normal * y * ur_n + K_crash * ur_c
        r = max(r, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq)
        y_vals.append(y)
        cb_flags.append(int(halted))

    eqs  = pd.Series(eq_vals, index=unit_normal.index)
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
        n_trips    = int(sum(cb_flags[i] > cb_flags[i-1] for i in range(1, len(cb_flags)))),
        avg_y      = float(np.mean(y_vals)),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL / POSITION BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_positions(df_1h, comp_raw, calib_mask, ohlc_all):
    common_start = comp_raw.dropna().index.min()
    common_end   = comp_raw.dropna().index.max()
    ohlc = ohlc_all[
        (ohlc_all.index >= common_start) &
        (ohlc_all.index <= common_end)
    ].copy()
    hours = ohlc.index

    idx       = df_1h.index
    train_1h  = (idx >= TRAIN_START) & (idx < TEST_START)
    train_idx = np.where(train_1h)[0]
    cm        = np.zeros(len(df_1h), dtype=bool)
    cm[train_idx[-CALIB_BARS:]] = True

    hourly_cal  = comp_raw[cm].abs().dropna()
    sig_shifted = comp_raw.shift(1).reindex(hours).fillna(0.0).values.astype(float)
    hth  = float(hourly_cal.quantile(BASE['q_hourly']))
    hpos = np.where(np.abs(sig_shifted) >= hth, np.sign(sig_shifted).astype(int), 0)
    hq   = _percentile_against(np.abs(sig_shifted), hourly_cal.values)

    # ── daily signal (champion confirmation timeframe) ──
    daily_sig   = comp_raw.groupby(comp_raw.index.normalize()).last()
    train_daily = (daily_sig.index >= pd.Timestamp(TRAIN_START)) & \
                  (daily_sig.index <  pd.Timestamp(TEST_START))
    cal_daily   = daily_sig[train_daily].abs().dropna()
    tth         = float(cal_daily.quantile(BASE['q_daily']))
    d_vals      = daily_sig.shift(1).reindex(hours, method='ffill').fillna(0.0).values.astype(float)
    tpos        = np.sign(d_vals).astype(int)
    tactive     = np.abs(d_vals) >= tth
    tq          = _percentile_against(np.abs(d_vals), cal_daily.values)
    confirm     = (tactive & (tpos == hpos) & (hpos != 0)).astype(float)

    # ── daily vol — kept only for sigma-stop sizing, not a trading signal ──
    all_days   = pd.Index(sorted(ohlc_all.index.normalize().unique()))
    calib_days = all_days[
        (all_days >= pd.Timestamp(TRAIN_START)) & (all_days < pd.Timestamp(TEST_START))
    ]
    ret_daily = ohlc_all['close'].pct_change().fillna(0.0).groupby(ohlc_all.index.normalize()).sum()
    daily_vol = float(ret_daily.reindex(calib_days).std())

    ret_h    = ohlc_all['close'].pct_change().fillna(0.0)
    rv       = ret_h.rolling(24, min_periods=12).std().shift(1)
    rv_cal   = rv[(rv.index >= pd.Timestamp(TRAIN_START)) &
                  (rv.index <  pd.Timestamp(TEST_START))].dropna()
    rv_h     = rv.reindex(hours).ffill().fillna(rv_cal.median())
    stress_rank = _percentile_against(rv_h.values, rv_cal.values)
    vol_base    = (float(rv_cal.median()) / rv_h.clip(lower=1e-8)).values

    unit0_arr, _ = simulate_unit_with_psi(
        ohlc['open'].values.astype(float),
        ohlc['high'].values.astype(float),
        ohlc['low'].values.astype(float),
        ohlc['close'].values.astype(float),
        hpos, tpos, tactive, np.ones(len(hours)),
        BASE['sl_mult'] * daily_vol,
        BASE['tp_mult'] * daily_vol,
    )
    unit0   = pd.Series(unit0_arr, index=hours)
    roll_mu = unit0.rolling(240, min_periods=72).mean().shift(1).fillna(0.0)
    roll_sd = unit0.rolling(240, min_periods=72).std().shift(1).replace(0, np.nan).fillna(unit0.std())
    q_quality    = 0.25 + 1.25 / (1.0 + np.exp(-np.clip(
                       roll_mu / roll_sd * np.sqrt(24*365.25) * 0.50, -50, 50)))
    strength_raw = hq * (1.0 + tq) * (1.0 + confirm) / 4.0

    sm_mult = np.clip(0.25 + DYN_STRENGTH_CAP * strength_raw, 0.25, DYN_STRENGTH_CAP)
    vm_mult = np.clip(vol_base, 0.25, DYN_VOL_CAP)
    delta   = 1.2 - stress_rank
    gamma   = np.clip(np.sign(delta) * delta**2, 0.4, 1.3)
    size_mult = np.clip(sm_mult * q_quality * vm_mult * gamma, 0.0, DYN_TOTAL_CAP)

    # ── Crash signal (causal) ──
    eth_ret_1h  = ohlc['close'].pct_change().fillna(0.0)
    eth_ret_12h = ohlc['close'].pct_change(12).shift(1).fillna(0.0)  # causal
    rv_1h_24    = eth_ret_1h.rolling(24, min_periods=12).std().shift(1).fillna(0.0)  # causal
    rv_train    = rv_1h_24[(rv_1h_24.index >= pd.Timestamp(TRAIN_START)) &
                            (rv_1h_24.index <  pd.Timestamp(TEST_START))]
    rv_base     = float(rv_train.median())
    crash_raw   = (eth_ret_12h < CRASH_RET_THRESH) & \
                  (rv_1h_24    > CRASH_VOL_MULT * rv_base)
    crash_signal = crash_raw.values.astype(int)

    n_crash = int(crash_signal.sum())
    print(f'  crash signal fires    : {n_crash} bars  '
          f'({n_crash/HOURS_PER_DAY:.1f} potential crash-short entry bars)')
    print(f'  rv_baseline (train)   : {rv_base:.4f}  ({rv_base*100:.2f}% / hr)')
    print(f'  crash threshold vol   : {CRASH_VOL_MULT * rv_base:.4f}  '
          f'({CRASH_VOL_MULT}× baseline)')

    op = ohlc['open'].values.astype(float)
    hi = ohlc['high'].values.astype(float)
    lo = ohlc['low'].values.astype(float)
    cl = ohlc['close'].values.astype(float)

    return dict(
        hours=hours, op=op, hi=hi, lo=lo, cl=cl,
        hpos=hpos, dpos=tpos, dactive=tactive,
        daily_vol=daily_vol, size_mult=size_mult,
        crash_signal=crash_signal,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(BAR)
    print('  MASTER STRATEGY SIMULATION  (1h primary + 2h confirmation)')
    print('  Three pillars: Trailing Stop + Circuit Breaker + Crash Short')
    print(BAR)

    print('\n[1] Building geometry + OHLCV ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ohlc_all = fetch_futures_ohlcv()

    print('[2] Building signal, sizing, and crash signal ...')
    p = build_positions(df_1h, comp_raw, calib_mask, ohlc_all)
    sl = BASE['sl_mult'] * p['daily_vol']
    tp = BASE['tp_mult'] * p['daily_vol']
    print(f'  daily vol (σ) : {p["daily_vol"]:.2%}   σ-SL={sl:.2%}  σ-TP={tp:.2%}')

    test_ts    = pd.Timestamp(TEST_START)
    train_mask = lambda eq: (eq.index >= pd.Timestamp(TRAIN_START)) & (eq.index < test_ts)
    test_mask  = lambda eq: (eq.index >= test_ts)

    # ── [3] Pre-compute crash short unit returns (independent of trail/CB) ──
    print('[3] Pre-computing crash-short unit returns ...')
    crash_arr, crash_cnt = simulate_crash_shorts(
        p['op'], p['hi'], p['lo'], p['cl'],
        p['crash_signal'], CRASH_SL, CRASH_TP, CRASH_MAX_HOURS,
    )
    unit_crash = pd.Series(crash_arr, index=p['hours'])
    print(f'  crash entries={crash_cnt["entries"]}  '
          f'stop={crash_cnt["stop"]}  tp={crash_cnt["tp"]}  '
          f'time_exit={crash_cnt["time_exit"]}')
    # Standalone crash-only equity check:
    eq_crash_sa = (1.0 + unit_crash * 2.0).cumprod() * INIT  # K=2 sanity check
    print(f'  crash-short standalone (K=2): '
          f'final=${float(eq_crash_sa.iloc[-1]):,.0f}  '
          f'OOS ${float(eq_crash_sa[eq_crash_sa.index >= test_ts].iloc[-1]):,.0f}')
    unit_zero = pd.Series(np.zeros(len(p['hours'])), index=p['hours'])  # no crash

    # ── [4] Sweep trail × K_crash ──
    print('[4] Sweeping trail × K_crash combinations ...')
    results = {}
    for tg in TRAIL_GRID:
        tm = tg['trigger_mult']; dm = tg['dist_mult']
        trail_trigger = tm * p['daily_vol']
        trail_dist    = dm * p['daily_vol']
        trail_label   = f'trig={tm}σ dist={dm}σ'

        # Run the normal unit returns with this trail config
        unit_arr, cnt = simulate_unit_trailing(
            p['op'], p['hi'], p['lo'], p['cl'],
            p['hpos'], p['dpos'], p['dactive'],
            p['size_mult'], sl, tp, trail_trigger, trail_dist,
        )
        unit_normal = pd.Series(unit_arr, index=p['hours'])

        for K_crash in K_CRASH_GRID:
            uc = unit_crash if K_crash > 0 else unit_zero
            res = simulate_combined(
                unit_normal, uc,
                K_normal=DYN_K, K_crash=K_crash,
                dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                cb_halt=CB_HALT, cb_resume=CB_RESUME,
                cb_window_days=CB_WINDOW_DAYS, use_cb=True,
            )
            key = (tm, dm, K_crash)
            results[key] = dict(**res, trail_label=trail_label,
                                K_crash=K_crash, trail_trigger=tm, trail_dist=dm,
                                unit_normal=unit_normal, trail_counts=cnt)

        print(f'  trail [{trail_label}]  done  '
              f'(entries={cnt["entries"]:,}  '
              f'trail_exits={cnt["trail_exit"]}  '
              f'tp={cnt["tp"]}  signal={cnt["signal_exit"]})')

    # ── [5] Find best by OOS Calmar ──
    def oos_calmar(key):
        eq_oos = results[key]['eq'][results[key]['eq'].index >= test_ts]
        return equity_metrics(eq_oos)['calmar']
    best_key = max(results.keys(), key=oos_calmar)

    # ── [6] Print strategy reference cases ──
    # A: baseline K=3 (no trail, no CB, no crash) — reuse no-trail, no-CB variant
    print('\n[5] Computing reference strategies ...')
    # no-trail baseline
    unit_base_arr, _ = simulate_unit_with_psi(
        p['op'], p['hi'], p['lo'], p['cl'],
        p['hpos'], p['dpos'], p['dactive'],
        p['size_mult'], sl, tp,
    )
    unit_base = pd.Series(unit_base_arr, index=p['hours'])
    eq_A = adaptive_equity(unit_base, K=3.0, dd_soft=DYN_DD_SOFT,
                            dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR)['eq']
    eq_B = simulate_combined(unit_base, unit_zero, K_normal=3.0, K_crash=0.0,
                              dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP,
                              y_floor=DYN_Y_FLOOR,
                              cb_halt=CB_HALT, cb_resume=CB_RESUME,
                              cb_window_days=CB_WINDOW_DAYS, use_cb=True)['eq']   # CB-cash
    eq_C = simulate_combined(results[(1.0, 0.50, 0.0)]['unit_normal'], unit_zero,
                              K_normal=3.0, K_crash=0.0,
                              dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP,
                              y_floor=DYN_Y_FLOOR,
                              cb_halt=CB_HALT, cb_resume=CB_RESUME,
                              cb_window_days=CB_WINDOW_DAYS, use_cb=False)['eq']  # Trail only
    eq_D = simulate_combined(results[(1.0, 0.50, 0.0)]['unit_normal'], unit_zero,
                              K_normal=3.0, K_crash=0.0,
                              dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP,
                              y_floor=DYN_Y_FLOOR,
                              cb_halt=CB_HALT, cb_resume=CB_RESUME,
                              cb_window_days=CB_WINDOW_DAYS, use_cb=True)['eq']   # CB + Trail
    eq_E = simulate_combined(unit_base, unit_crash,
                              K_normal=3.0, K_crash=1.5,
                              dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP,
                              y_floor=DYN_Y_FLOOR,
                              cb_halt=CB_HALT, cb_resume=CB_RESUME,
                              cb_window_days=CB_WINDOW_DAYS, use_cb=False)['eq']  # Crash only
    eq_F = simulate_combined(unit_base, unit_crash,
                              K_normal=3.0, K_crash=1.5,
                              dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP,
                              y_floor=DYN_Y_FLOOR,
                              cb_halt=CB_HALT, cb_resume=CB_RESUME,
                              cb_window_days=CB_WINDOW_DAYS, use_cb=True)['eq']   # CB + Crash

    eq_best = results[best_key]['eq']
    best_tm, best_dm, best_Kc = best_key

    # ── [7] Detail print for best ──
    print()
    print(BAR)
    print(f'  MASTER STRATEGY — BEST COMBINATION')
    print(f'  Trail: trigger={best_tm}σ={best_tm*p["daily_vol"]:.2%}  '
          f'dist={best_dm}σ={best_dm*p["daily_vol"]:.2%}')
    print(f'  CB: window={CB_WINDOW_DAYS}d  halt={CB_HALT:.0%}  resume={CB_RESUME:.0%}')
    print(f'  Crash: SL={CRASH_SL:.0%}  TP={CRASH_TP:.0%}  '
          f'max={CRASH_MAX_HOURS}h  K_crash={best_Kc}')
    print(SEP)

    for m in [equity_metrics(eq_best,                   'Master — FULL'),
              equity_metrics(eq_best[train_mask(eq_best)],'Master — TRAIN'),
              equity_metrics(eq_best[test_mask(eq_best)], 'Master — TEST (OOS)')]:
        print(); print_metrics(m)

    r_best = results[best_key]
    cnt_b  = r_best['trail_counts']
    print(f'\n  exits: stop={cnt_b["stop"]}  trail_exit={cnt_b["trail_exit"]}  '
          f'tp={cnt_b["tp"]}  signal={cnt_b["signal_exit"]}')
    print(f'  crash: entries={crash_cnt["entries"]}  '
          f'stop={crash_cnt["stop"]}  tp={crash_cnt["tp"]}  '
          f'time={crash_cnt["time_exit"]}')
    print(f'  pct_halted={r_best["pct_halted"]:.1%}  '
          f'cb_trips={r_best["n_trips"]}  avg_Y={r_best["avg_y"]:.3f}')

    print('\n  Yearly:')
    print_yearly(period_table(eq_best, 'Y'))

    print('\n  Top drawdowns:')
    print_dd(drawdown_periods(eq_best))

    # ── [8] OOS comparison table ──
    print()
    print(BAR)
    print('  OOS COMPARISON TABLE  (2023 → today)')
    header = f'  {"Strategy":<52} {"Final$":>10} {"Return":>8} {"CAGR":>8} {"Sharpe":>8} {"MaxDD":>8} {"Calmar":>8}'
    print(header); print(f'  {"-"*52} {"-"*10} {"-"*8} {"-"*8} {"-"*8} {"-"*8} {"-"*8}')

    def pr(eq_oos, label):
        m = equity_metrics(eq_oos, label)
        print(f'  {label:<52} {m["final"]:>10,.2f} {m["return_pct"]:>+7.1%} '
              f'{m["cagr"]:>+7.2%} {m["sharpe"]:>+8.3f} '
              f'{m["maxdd"]:>+7.2%} {m["calmar"]:>+8.3f}')
        return m

    pr(eq_A[test_mask(eq_A)],  '[A] Baseline K=3  (no trail, no CB, no crash)')
    pr(eq_B[test_mask(eq_B)],  '[B] CB-cash  K=3  (previous champion)')
    pr(eq_C[test_mask(eq_C)],  '[C] Trailing stop only  (1σ/0.5σ, no CB)')
    pr(eq_D[test_mask(eq_D)],  '[D] CB + Trailing stop  (1σ/0.5σ)')
    pr(eq_E[test_mask(eq_E)],  '[E] Crash short only  K_crash=1.5')
    pr(eq_F[test_mask(eq_F)],  '[F] CB + Crash short  K_crash=1.5')

    print()
    print(f'  {"--- TRAIL × K_CRASH GRID (CB always on) ---":<52}')
    for tg in TRAIL_GRID:
        tm, dm = tg['trigger_mult'], tg['dist_mult']
        for Kc in K_CRASH_GRID:
            key   = (tm, dm, Kc)
            eq_oo = results[key]['eq'][results[key]['eq'].index >= test_ts]
            star  = ' ◄ BEST' if key == best_key else ''
            pr(eq_oo,
               f'  trail={tm}σ/{dm}σ  K_crash={Kc}{star}')

    print(f'\n  elapsed: {time.time()-t0:.1f}s')
    print(BAR)

    # ── Save JSON ──
    best_eq = results[best_key]['eq']
    payload = dict(
        config=dict(
            cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window_days=CB_WINDOW_DAYS,
            crash_ret_thresh=CRASH_RET_THRESH, crash_vol_mult=CRASH_VOL_MULT,
            crash_sl=CRASH_SL, crash_tp=CRASH_TP, crash_max_hours=CRASH_MAX_HOURS,
            K_normal=DYN_K,
        ),
        crash_counts=crash_cnt,
        best=dict(
            trail_trigger_mult=best_tm, trail_dist_mult=best_dm, K_crash=best_Kc,
            full=equity_metrics(best_eq),
            train=equity_metrics(best_eq[train_mask(best_eq)]),
            test=equity_metrics(best_eq[test_mask(best_eq)]),
            yearly=period_table(best_eq, 'Y'),
            drawdowns=drawdown_periods(best_eq),
        ),
        grid={
            f't{tm}_d{dm}_kc{Kc}': dict(
                test=equity_metrics(results[(tm, dm, Kc)]['eq'][
                         results[(tm, dm, Kc)]['eq'].index >= test_ts]),
            )
            for tg in TRAIL_GRID
            for tm, dm in [(tg['trigger_mult'], tg['dist_mult'])]
            for Kc in K_CRASH_GRID
        },
        elapsed=time.time() - t0,
    )
    OUT.write_text(json.dumps(payload, indent=2, default=float))
    print(f'\n  Saved → {OUT}')


if __name__ == '__main__':
    main()
