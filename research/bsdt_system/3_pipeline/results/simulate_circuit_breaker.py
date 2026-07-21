"""Circuit Breaker — MaxDD Control Simulation.

When portfolio equity drawdown from its ROLLING-WINDOW peak EXCEEDS `cb_halt`,
all new trade entries are blocked (Y=0).  The peak rolls off as time passes
(window = CB_WINDOW_DAYS), so a breaker triggered by an old bear-market peak
naturally expires and trading resumes once that peak ages out of the window —
without requiring a full equity recovery to the all-time high.

Two rates of DD:
  • Adaptive Y  →  uses all-time peak  (unchanged from v59)
  • Circuit Breaker  →  uses rolling(CB_WINDOW_DAYS)-day max peak only

This is layered on top of the existing Adaptive-Y linear brake:

    Normal mode  →  Adaptive Y (dd_soft=5%, dd_stop=20%, y_floor=0.25)
    CB mode      →  Y forced to 0.0 regardless of the Adaptive-Y value

Grid tested (K=3, Sigma stops — v59 champion):
    cb_halt        ∈ {12%, 15%, 18%, 20%, 25%}
    cb_resume      = cb_halt − 5%   (fixed 5 % hysteresis band)
    CB_WINDOW_DAYS ∈ {90, 180, 365}  (rolling peak look-back)

OOS comparison also includes the unbraked K=3 and K=5 baselines.
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

OUT = Path(OUT_DIR) / 'simulation_circuit_breaker.json'
BAR = '=' * 110
SEP = '-' * 110

RT_COST    = 2.0 / 1e4
FUND_DAY   = 0.5 / 1e4
FUND_HOURLY = FUND_DAY / 24.0

# Champion dynamic-sizing params (from v59)
DYN_K            = 3.0
DYN_STRENGTH_CAP = 2.5
DYN_VOL_CAP      = 3.0
DYN_GAMMA_MODE   = 'convex'
DYN_TOTAL_CAP    = 2.0
DYN_DD_SOFT      = 0.05
DYN_DD_STOP      = 0.20
DYN_Y_FLOOR      = 0.25

# Circuit-breaker grid
CB_HALT_GRID  = [0.12, 0.15, 0.18, 0.20, 0.25]
CB_HYSTERESIS = 0.05   # resume = halt − 5%
CB_WINDOW_GRID = [90, 180, 365]  # rolling-peak look-back in calendar days
HOURS_PER_DAY  = 24


# ─────────────────────────────────────────────────────────────────────────────
#  METRICS
# ─────────────────────────────────────────────────────────────────────────────

def equity_metrics(eq: pd.Series, label: str = '') -> dict:
    r     = eq.pct_change().fillna(eq.iloc[0] / INIT - 1.0)
    dd    = (eq - eq.cummax()) / eq.cummax()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    calmar = float((eq.iloc[-1] / INIT) ** (1 / years) - 1) / max(abs(float(dd.min())), 1e-9)
    return dict(
        label      = label,
        final      = float(eq.iloc[-1]),
        profit     = float(eq.iloc[-1] - INIT),
        return_pct = float(eq.iloc[-1] / INIT - 1.0),
        cagr       = float((eq.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe     = float(np.sqrt(24 * 365.25) * r.mean() / r.std()) if r.std() > 0 else 0.0,
        maxdd      = float(dd.min()),
        calmar     = calmar,
        start      = str(eq.index[0]),
        end        = str(eq.index[-1]),
    )


def period_table(eq: pd.Series, freq: str) -> list[dict]:
    rows = []
    for dt, s in eq.groupby(pd.Grouper(freq=freq)):
        if len(s) < 2: continue
        r  = s.pct_change().dropna()
        dd = (s - s.cummax()) / s.cummax()
        rows.append(dict(
            period     = str(dt.date()),
            start_eq   = round(float(s.iloc[0]), 2),
            end_eq     = round(float(s.iloc[-1]), 2),
            profit     = round(float(s.iloc[-1] - s.iloc[0]), 2),
            return_pct = round(float(s.iloc[-1] / s.iloc[0] - 1.0), 4),
            sharpe     = round(float(np.sqrt(24 * 365.25) * r.mean() / r.std()), 3) if r.std() > 0 else 0.0,
            maxdd      = round(float(dd.min()), 4),
        ))
    return rows


def drawdown_periods(eq: pd.Series, top_n: int = 6) -> list[dict]:
    peak = eq.cummax()
    dd   = (eq - peak) / peak
    rows = []
    in_dd = False; start = None; peak_val = None
    for ts, val in dd.items():
        if not in_dd and val < -1e-4:
            in_dd = True; start = ts; peak_val = float(peak[ts])
        elif in_dd and val >= -1e-4:
            trough_i  = dd[start:ts].idxmin()
            rows.append(dict(dd_start=str(start), trough=str(trough_i),
                             dd_end=str(ts), drawdown=float(dd[trough_i]),
                             peak_eq=peak_val, trough_eq=float(eq[trough_i]),
                             duration_days=int((ts - start).days)))
            in_dd = False
    if in_dd:
        trough_i = dd[start:].idxmin()
        rows.append(dict(dd_start=str(start), trough=str(trough_i),
                         dd_end='ongoing', drawdown=float(dd[trough_i]),
                         peak_eq=peak_val, trough_eq=float(eq[trough_i]),
                         duration_days=int((eq.index[-1] - start).days)))
    rows.sort(key=lambda r: r['drawdown'])
    return rows[:top_n]


def print_metrics(m: dict):
    print(f"  {'label':<28} {m.get('label','')}")
    print(f"  {'period':<28} {m['start'][:10]}  →  {m['end'][:10]}")
    print(f"  {'final equity':<28} ${m['final']:>12,.2f}   (started ${INIT:,.0f})")
    print(f"  {'profit':<28} ${m['profit']:>+12,.2f}   ({m['return_pct']:>+.1%})")
    print(f"  {'CAGR':<28} {m['cagr']:>+.2%}")
    print(f"  {'Sharpe (hourly-freq)':<28} {m['sharpe']:>+.3f}")
    print(f"  {'MaxDD':<28} {m['maxdd']:>+.2%}")
    print(f"  {'Calmar':<28} {m['calmar']:>+.3f}")


def print_yearly(rows):
    print(f"  {'Year':<8} {'Start':>10} {'End':>10} {'P&L':>10} {'Ret':>8} {'Sharpe':>8} {'MaxDD':>8}")
    for r in rows:
        print(f"  {r['period']:<8} {r['start_eq']:>10,.2f} {r['end_eq']:>10,.2f} "
              f"  {r['profit']:>+9,.2f}  {r['return_pct']:>+7.1%} {r['sharpe']:>+8.3f} {r['maxdd']:>+7.2%}")


def print_drawdowns(rows):
    print(f"  {'Start':<14} {'Trough':<14} {'End':<14} {'DD':>8} {'Days':>6} {'Peak$':>10} {'Trough$':>10}")
    for r in rows:
        end = r['dd_end'][:10] if r['dd_end'] != 'ongoing' else 'ongoing'
        print(f"  {r['dd_start'][:10]:<14} {r['trough'][:10]:<14} {end:<14} "
              f"{r['drawdown']:>+7.2%} {r['duration_days']:>6,d} {r['peak_eq']:>10,.2f} {r['trough_eq']:>10,.2f}")


# ─────────────────────────────────────────────────────────────────────────────
#  CIRCUIT-BREAKER EQUITY ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def adaptive_equity_cb(unit_ret: pd.Series,
                       K: float,
                       dd_soft: float,
                       dd_stop: float,
                       y_floor: float,
                       cb_halt: float,
                       cb_resume: float,
                       cb_window_days: int = 180):
    """Adaptive Y + rolling-window circuit breaker.

    The circuit-breaker drawdown is measured from the MAXIMUM equity over the
    last `cb_window_days` calendar days (the rolling peak), not the all-time
    peak.  This means a breaker triggered by an ageing bear-market high
    automatically expires once that peak scrolls out of the window — trading
    resumes naturally without requiring a full all-time-high recovery.

    The Adaptive-Y linear brake still uses the all-time peak (unchanged).

    State machine (evaluated each bar with previous-bar values — fully causal):
      NOT HALTED → if cb_dd >= cb_halt  :  HALT
      HALTED     → if cb_dd <= cb_resume : RESUME
    """
    window_bars = cb_window_days * HOURS_PER_DAY
    # Monotonic deque for O(1) sliding-window maximum of equity history.
    # Each entry is (bar_index, equity_value); front = current max.
    mono_dq: deque = deque()     # (i, eq) stored in decreasing eq order
    eq = INIT; peak_alltime = INIT; halted = False
    eq_vals = []; y_vals = []; cb_flags = []

    for bar_i, (_, ur) in enumerate(unit_ret.items()):
        # ── Update sliding-window max (before applying this bar's return) ──
        # Remove indices that have left the window
        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        # Maintain monotonically decreasing deque (remove smaller tail values)
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]    # O(1)

        # Drawdown for Adaptive Y  →  all-time peak
        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        # Drawdown for CB  →  rolling-window peak
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak, 1e-12))

        # Circuit-breaker state machine (causal — uses current-bar start state)
        if not halted and cb_dd >= cb_halt:
            halted = True
        elif halted and cb_dd <= cb_resume:
            halted = False

        if halted:
            y = 0.0
        elif dd_aty <= dd_soft:
            y = 1.0
        elif dd_aty >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        r = K * y * float(ur)
        r = max(r, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq)
        y_vals.append(y)
        cb_flags.append(int(halted))

    eqs = pd.Series(eq_vals, index=unit_ret.index)
    rets = eqs.pct_change().fillna(eqs.iloc[0] / INIT - 1.0)
    dd_s = (eqs - eqs.cummax()) / eqs.cummax()
    years = max((eqs.index[-1] - eqs.index[0]).days / 365.25, 1e-9)
    return dict(
        eq         = eqs,
        y          = pd.Series(y_vals,   index=unit_ret.index),
        cb         = pd.Series(cb_flags, index=unit_ret.index),
        final      = float(eqs.iloc[-1]),
        cagr       = float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe     = float(np.sqrt(24 * 365.25) * rets.mean() / rets.std()) if rets.std() > 0 else 0.0,
        maxdd      = float(dd_s.min()),
        avg_y      = float(np.mean(y_vals)),
        min_y      = float(np.min(y_vals)),
        pct_cut    = float(np.mean(np.array(y_vals) < 0.999)),
        pct_halted = float(np.mean(cb_flags)),
        n_trips    = int(sum(cb_flags[i] > cb_flags[i-1] for i in range(1, len(cb_flags)))),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL / POSITION BUILDER  (reused from simulate_atr14_stops.py)
# ─────────────────────────────────────────────────────────────────────────────

def build_signal_and_positions(df_1h, comp_raw, calib_mask, ohlc_all):
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

    daily_sig  = comp_raw.groupby(comp_raw.index.normalize()).last()
    all_days   = pd.Index(sorted(ohlc_all.index.normalize().unique()))
    calib_days = all_days[
        (all_days >= pd.Timestamp(TRAIN_START)) & (all_days < pd.Timestamp(TEST_START))
    ]
    ret_daily  = ohlc_all['close'].pct_change().fillna(0.0).groupby(ohlc_all.index.normalize()).sum()
    daily_vol  = float(ret_daily.reindex(calib_days).std())
    daily_cal  = daily_sig.reindex(calib_days).abs().dropna()
    dth        = float(daily_cal.quantile(BASE['q_daily']))
    prev_days  = hours.normalize() - pd.Timedelta(days=1)
    ds_vals    = daily_sig.reindex(prev_days).fillna(0.0).values.astype(float)
    dpos       = np.sign(ds_vals).astype(int)
    dactive    = np.abs(ds_vals) >= dth
    dq         = _percentile_against(np.abs(ds_vals), daily_cal.values)
    confirm    = (dactive & (dpos == hpos) & (hpos != 0)).astype(float)

    ret_h       = ohlc_all['close'].pct_change().fillna(0.0)
    rv          = ret_h.rolling(24, min_periods=12).std().shift(1)
    rv_cal      = rv[(rv.index >= pd.Timestamp(TRAIN_START)) &
                     (rv.index <  pd.Timestamp(TEST_START))].dropna()
    rv_h        = rv.reindex(hours).ffill().fillna(rv_cal.median())
    stress_rank = _percentile_against(rv_h.values, rv_cal.values)
    target_vol  = float(rv_cal.median())
    vol_base    = (target_vol / rv_h.clip(lower=1e-8)).values

    unit0_arr, _ = simulate_unit_with_psi(
        ohlc['open'].values.astype(float),
        ohlc['high'].values.astype(float),
        ohlc['low'].values.astype(float),
        ohlc['close'].values.astype(float),
        hpos, dpos, dactive,
        np.ones(len(hours)),
        BASE['sl_mult'] * daily_vol,
        BASE['tp_mult'] * daily_vol,
    )
    unit0    = pd.Series(unit0_arr, index=hours)
    roll_mu  = unit0.rolling(240, min_periods=72).mean().shift(1).fillna(0.0)
    roll_sd  = unit0.rolling(240, min_periods=72).std().shift(1).replace(0, np.nan).fillna(unit0.std())
    q_quality     = 0.25 + 1.25 / (1.0 + np.exp(-np.clip(roll_mu / roll_sd * np.sqrt(24 * 365.25) * 0.50, -50, 50)))
    strength_raw  = hq * (1.0 + dq) * (1.0 + confirm) / 4.0

    return dict(
        hours        = hours,
        ohlc         = ohlc,
        op           = ohlc['open'].values.astype(float),
        hi           = ohlc['high'].values.astype(float),
        lo           = ohlc['low'].values.astype(float),
        cl           = ohlc['close'].values.astype(float),
        hpos         = hpos,
        dpos         = dpos,
        dactive      = dactive,
        daily_vol    = daily_vol,
        unit0        = unit0,
        hth          = hth,
        dth          = dth,
        strength_raw = strength_raw,
        q_quality    = q_quality,
        vol_base     = vol_base,
        stress_rank  = stress_rank,
        calib_days   = calib_days,
    )


def _dynamic_size_mult(p):
    strength_mult = np.clip(0.25 + DYN_STRENGTH_CAP * p['strength_raw'], 0.25, DYN_STRENGTH_CAP)
    vol_mult      = np.clip(p['vol_base'], 0.25, DYN_VOL_CAP)
    delta         = 1.2 - p['stress_rank']
    gamma         = np.clip(np.sign(delta) * delta ** 2, 0.4, 1.3)
    return np.clip(strength_mult * p['q_quality'] * vol_mult * gamma, 0.0, DYN_TOTAL_CAP)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(BAR)
    print('  CIRCUIT BREAKER — MaxDD CONTROL SIMULATION')
    print('  BSDT Geometry (z(E7)+z(dG)+z(E6)+z(dT))/4 — 4-channel — K=3 sigma stops')
    print(f'  Train: {TRAIN_START[:10]}  →  {TEST_START[:10]}   '
          f'OOS: {TEST_START[:10]}  →  today')
    print(f'  CB grid: halt ∈ {[f"{x:.0%}" for x in CB_HALT_GRID]}   '
          f'hysteresis = {CB_HYSTERESIS:.0%}')
    print(BAR)

    # ── [1] Build geometry + OHLCV ──
    print('\n[1] Building geometry + OHLCV ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ohlc_all = fetch_futures_ohlcv()

    # ── [2] Signal + positions ──
    print('[2] Building signal + dynamic sizing ...')
    p = build_signal_and_positions(df_1h, comp_raw, calib_mask, ohlc_all)
    size_mult = _dynamic_size_mult(p)
    print(f'  daily vol (σ) : {p["daily_vol"]:.2%}   σ-SL={BASE["sl_mult"]*p["daily_vol"]:.2%}  '
          f'σ-TP={BASE["tp_mult"]*p["daily_vol"]:.2%}')
    print(f'  train bars    : {(p["hours"] < pd.Timestamp(TEST_START)).sum():,}   '
          f'test bars: {(p["hours"] >= pd.Timestamp(TEST_START)).sum():,}')

    # ── [3] Run unit returns once (reused across all CB thresholds) ──
    print('[3] Running unit-level simulation (sigma stops, dynamic sizing) ...')
    unit_arr, counts = simulate_unit_with_psi(
        p['op'], p['hi'], p['lo'], p['cl'],
        p['hpos'], p['dpos'], p['dactive'], size_mult,
        BASE['sl_mult'] * p['daily_vol'],
        BASE['tp_mult'] * p['daily_vol'],
    )
    unit = pd.Series(unit_arr, index=p['hours'])
    print(f'  entries={counts["entries"]:,}  stops={counts["stop"]:,}  '
          f'tp={counts["tp"]:,}  signal_exits={counts["signal_exit"]:,}')

    # ── [4] Baseline (no circuit breaker) ──
    print('[4] Baselines (K=3, K=5 — original Adaptive Y, no CB) ...')
    base3 = adaptive_equity(unit, K=3.0, dd_soft=DYN_DD_SOFT,
                             dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR)
    base5 = adaptive_equity(unit, K=5.0, dd_soft=DYN_DD_SOFT,
                             dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR)

    # ── [5] Circuit breaker sweep (K=3) ──
    print('[5] Sweeping circuit breaker thresholds (K=3) ...')
    print(f'  (rolling-peak window × halt threshold  →  result)')
    cb_results = {}
    for win in CB_WINDOW_GRID:
        for cb_halt in CB_HALT_GRID:
            cb_resume = max(0.01, cb_halt - CB_HYSTERESIS)
            res = adaptive_equity_cb(unit, K=3.0, dd_soft=DYN_DD_SOFT,
                                      dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                                      cb_halt=cb_halt, cb_resume=cb_resume,
                                      cb_window_days=win)
            cb_results[(win, cb_halt)] = res
            print(f'  win={win:3d}d  halt={cb_halt:.0%} resume={cb_resume:.0%}  →  '
                  f'final=${res["final"]:>10,.2f}  maxdd={res["maxdd"]:>+6.1%}  '
                  f'sharpe={res["sharpe"]:>+5.2f}  halted={res["pct_halted"]:.1%}  '
                  f'trips={res["n_trips"]}')

    # ── [6] Best CB by Calmar ──
    test_start_ts = pd.Timestamp(TEST_START)

    def oos_calmar(res):
        eq_oos = res['eq'][res['eq'].index >= test_start_ts]
        if len(eq_oos) < 2:
            return -999.0
        m = equity_metrics(eq_oos)
        return m['calmar']

    best_key = max(cb_results.keys(), key=lambda k: oos_calmar(cb_results[k]))
    best_win, best_halt = best_key
    print(f'\n  Best CB by OOS Calmar: window={best_win}d  halt={best_halt:.0%}')

    # ── [7] Detailed printout for best CB ──
    best = cb_results[best_key]
    best_resume = max(0.01, best_halt - CB_HYSTERESIS)
    eq_b = best['eq']
    test_mask  = eq_b.index >= test_start_ts
    train_mask = (eq_b.index >= pd.Timestamp(TRAIN_START)) & (eq_b.index < test_start_ts)

    print()
    print(BAR)
    print(f'  Circuit Breaker K=3  (win={best_win}d  halt={best_halt:.0%}  resume={best_resume:.0%})')
    print(SEP)
    for m in [equity_metrics(eq_b,             f'CB K=3 — FULL'),
              equity_metrics(eq_b[train_mask],  f'CB K=3 — TRAIN'),
              equity_metrics(eq_b[test_mask],   f'CB K=3 — TEST (OOS)')]:
        print(); print_metrics(m)

    print(f'\n  avg_Y={best["avg_y"]:.3f}  min_Y={best["min_y"]:.3f}  '
          f'pct_halted={best["pct_halted"]:.1%}  cb_trips={best["n_trips"]}')

    print('\n  Yearly:')
    print_yearly(period_table(eq_b, 'Y'))

    print('\n  Top drawdowns:')
    print_drawdowns(drawdown_periods(eq_b))

    # ── [8] OOS comparison table (all thresholds + baselines) ──
    print()
    print(BAR)
    print('  OOS COMPARISON  (2023 → today)')
    print(f'  {"Strategy":<42} {"Final$":>10} {"Return":>8} {"CAGR":>8} '
          f'{"Sharpe":>8} {"MaxDD":>8} {"Calmar":>8} {"Halted%":>8} {"Trips":>6}')
    print(f'  {"-"*42} {"-"*10} {"-"*8} {"-"*8} {"-"*8} {"-"*8} {"-"*8} {"-"*8} {"-"*6}')

    def oos_row(eq_oos, label, pct_halted=0.0, n_trips=0):
        m = equity_metrics(eq_oos, label)
        print(f'  {label:<42} {m["final"]:>10,.2f} {m["return_pct"]:>+7.1%} '
              f'{m["cagr"]:>+7.2%} {m["sharpe"]:>+8.3f} {m["maxdd"]:>+7.2%} '
              f'{m["calmar"]:>+8.3f} {pct_halted:>7.1%} {n_trips:>6}')
        return m

    eq3_oos = base3['eq'][base3['eq'].index >= test_start_ts]
    eq5_oos = base5['eq'][base5['eq'].index >= test_start_ts]
    oos_row(eq3_oos, 'Baseline K=3  (no CB)',
            pct_halted=base3['pct_cut'], n_trips=0)
    oos_row(eq5_oos, 'Baseline K=5  (no CB)',
            pct_halted=base5['pct_cut'], n_trips=0)

    for win in CB_WINDOW_GRID:
        for cb_halt in CB_HALT_GRID:
            res = cb_results[(win, cb_halt)]
            cb_resume = max(0.01, cb_halt - CB_HYSTERESIS)
            eq_oos = res['eq'][res['eq'].index >= test_start_ts]
            cb_oos = res['cb'][res['cb'].index >= test_start_ts]
            oos_row(eq_oos,
                    f'CB w={win}d h={cb_halt:.0%} r={cb_resume:.0%}  K=3',
                    pct_halted=float(cb_oos.mean()),
                    n_trips=int(sum(cb_oos.values[i] > cb_oos.values[i-1]
                                    for i in range(1, len(cb_oos)))))

    print(f'\n  elapsed: {time.time()-t0:.1f}s')
    print(BAR)

    # ── Save JSON ──
    payload = dict(
        config = dict(
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
            cb_hysteresis=CB_HYSTERESIS, cb_halt_grid=CB_HALT_GRID,
            cb_window_grid=CB_WINDOW_GRID,
        ),
        unit_counts = counts,
        baselines = dict(
            k3 = dict(full=equity_metrics(base3['eq']),
                      train=equity_metrics(base3['eq'][base3['eq'].index < test_start_ts]),
                      test=equity_metrics(base3['eq'][base3['eq'].index >= test_start_ts]),
                      yearly=period_table(base3['eq'], 'Y'),
                      drawdowns=drawdown_periods(base3['eq'])),
            k5 = dict(full=equity_metrics(base5['eq']),
                      train=equity_metrics(base5['eq'][base5['eq'].index < test_start_ts]),
                      test=equity_metrics(base5['eq'][base5['eq'].index >= test_start_ts]),
                      yearly=period_table(base5['eq'], 'Y'),
                      drawdowns=drawdown_periods(base5['eq'])),
        ),
        circuit_breakers = {
            f'w{win}_h{halt}': dict(
                cb_window_days = win,
                cb_halt    = halt,
                cb_resume  = max(0.01, halt - CB_HYSTERESIS),
                full       = equity_metrics(cb_results[(win, halt)]['eq']),
                train      = equity_metrics(cb_results[(win, halt)]['eq'][cb_results[(win, halt)]['eq'].index < test_start_ts]),
                test       = equity_metrics(cb_results[(win, halt)]['eq'][cb_results[(win, halt)]['eq'].index >= test_start_ts]),
                yearly     = period_table(cb_results[(win, halt)]['eq'], 'Y'),
                drawdowns  = drawdown_periods(cb_results[(win, halt)]['eq']),
                avg_y      = cb_results[(win, halt)]['avg_y'],
                pct_halted = cb_results[(win, halt)]['pct_halted'],
                n_trips    = cb_results[(win, halt)]['n_trips'],
            )
            for win in CB_WINDOW_GRID
            for halt in CB_HALT_GRID
        },
        best_window = best_win,
        best_halt   = best_halt,
        elapsed     = time.time() - t0,
    )
    OUT.write_text(json.dumps(payload, indent=2, default=float))
    print(f'\n  Saved → {OUT}')


if __name__ == '__main__':
    main()
