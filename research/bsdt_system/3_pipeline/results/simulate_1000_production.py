"""
simulate_1000_production.py — $1,000 Realistic Production Simulation
======================================================================
Champion strategy: layered_daily_no_crash_ze7
  CB: halt=8%, resume=1%, window=180d
  ZE7 gate: abs(zE7) >= 0.10
  OOS Calmar=+8.149, MaxDD=−16.80% (zero-cost baseline)

Three cost tiers compared side-by-side:
  ─ ZERO COST  : RT_COST=2bps (model baseline, what Calmar numbers assume)
  ─ REALISTIC  : Binance Perps taker + slippage + funding
                 Fee  = 5 bps/side  (10 bps round-trip, Binance taker VIP0)
                 Slip = 2 bps/side  ( 4 bps round-trip, typical $5k–$50k fill)
                 Fund = 1.0 bps/day average drag (long-biased, net positive rate)
                 Total RT cost = 14 bps  vs model 2 bps  → +12 bps drag/trade
  ─ PESSIMISTIC: Wider spreads, worse slippage (small exchange or high vol)
                 Fee  = 7 bps/side  (14 bps round-trip)
                 Slip = 5 bps/side  (10 bps round-trip)
                 Fund = 2.0 bps/day drag
                 Total RT cost = 24 bps

Outputs:
  · Equity curve starting at $1,000
  · Yearly P&L table (absolute $, %, Sharpe, MaxDD)
  · Quarterly P&L table
  · Drawdown table (top 6)
  · Per-trade cost analysis: fee vs slippage vs funding drag
  · Break-even analysis: max RT cost at which strategy is still Calmar>1
"""
from __future__ import annotations
import time
from collections import deque
from pathlib import Path
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS
from test_daily_geometry_stop_tp_ohlc   import (
    build_daily_geometry, fetch_futures_ohlcv, get_channel_series,
)
from test_psi_adaptive_y                import BASE
from simulate_master_strategy           import (
    build_positions, simulate_unit_trailing,
    equity_metrics, period_table, drawdown_periods, print_yearly, print_dd,
    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
    HOURS_PER_DAY,
)
from simulate_v63_quadrant              import (
    _build_quadrant_multiplier,
    CB_HALT, CB_RESUME, CB_WINDOW_DAYS,
    TRAIL_TRIGGER_MULT, TRAIL_DIST_MULT,
    ZE7_MIN_FORCE,
    simulate_unit_trailing_ze7gate,
)

BAR     = '=' * 110
SEP     = '-' * 110
TEST_TS = pd.Timestamp(TEST_START)
INIT    = 1_000.0

# ── Cost tiers ─────────────────────────────────────────────────────────────────
TIERS = {
    'zero_cost': dict(
        fee_bps    = 1.0,    # model assumption (RT_COST=2bps already in unit sim)
        slip_bps   = 1.0,    # already paid in RT_COST
        fund_bps_d = 0.083,  # ~FUND_HOURLY*24*1e4 = 0.05 bps/day
        label      = 'ZERO-COST  (model baseline)',
    ),
    'realistic': dict(
        fee_bps    = 10.0,   # 5 bps × 2 sides (Binance taker VIP0)
        slip_bps   = 4.0,    # 2 bps × 2 sides
        fund_bps_d = 1.0,    # 1 bps/day net drag (long-biased crypto)
        label      = 'REALISTIC  (Binance taker, 2bps slip, 1bps/day fund)',
    ),
    'pessimistic': dict(
        fee_bps    = 14.0,   # 7 bps × 2 sides
        slip_bps   = 10.0,   # 5 bps × 2 sides
        fund_bps_d = 2.0,    # 2 bps/day drag
        label      = 'PESSIMISTIC (7bps fee, 5bps slip, 2bps/day fund)',
    ),
}

# The unit sim already bakes in RT_COST=2bps + FUND_HOURLY. We need to
# SUBTRACT the baked-in cost and ADD the tier cost.
MODEL_RT_BPS  = 2.0           # bps already in unit returns (from simulate_master_strategy)
MODEL_FUND_HOURLY = 0.5 / 1e4 / 24.0   # from simulate_master_strategy


def simulate_combined_with_cost(
    unit_s: pd.Series,
    entries_per_bar: np.ndarray,   # 1 where entry fired, 0 otherwise
    position_active: np.ndarray,   # 1 where position was open (for funding)
    extra_rt_bps: float,           # ADDITIONAL cost vs model (bps, round-trip)
    extra_fund_bps_d: float,       # ADDITIONAL funding drag vs model (bps/day)
) -> dict:
    """
    Replay simulate_combined CB logic but inject extra costs.

    extra_rt_bps    : added as a one-time deduction when entry fires
    extra_fund_bps_d: added as hourly drag while in position
    """
    extra_rt   = extra_rt_bps    / 1e4
    extra_fund = extra_fund_bps_d / 1e4 / HOURS_PER_DAY

    window_bars = CB_WINDOW_DAYS * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq = INIT; peak_alltime = INIT; halted = False
    eq_vals = []; y_vals = []; cb_flags = []

    for i in range(len(unit_s)):
        ur = float(unit_s.iloc[i])

        # extra RT deduction at entry
        if entries_per_bar[i]:
            ur -= extra_rt

        # extra funding drag while in position
        if position_active[i]:
            ur -= extra_fund

        # CB logic
        while mono_dq and mono_dq[0][0] <= i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((i, eq))
        roll_peak = mono_dq[0][1]

        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))
        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))

        if not halted and cb_dd >= CB_HALT:   halted = True
        elif halted and cb_dd <= CB_RESUME:   halted = False

        if halted:
            y = 0.0
        elif dd_aty <= DYN_DD_SOFT:
            y = 1.0
        elif dd_aty >= DYN_DD_STOP:
            y = DYN_Y_FLOOR
        else:
            y = DYN_Y_FLOOR + (1.0 - DYN_Y_FLOOR) * (DYN_DD_STOP - dd_aty) / (DYN_DD_STOP - DYN_DD_SOFT)

        r = DYN_K * y * ur
        r = max(r, -0.95)
        eq = max(eq * (1.0 + r), 1e-6)
        peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq)
        y_vals.append(y)
        cb_flags.append(int(halted))

    eqs  = pd.Series([v * (INIT / eq_vals[0]) * (eq_vals[0] / INIT) for v in eq_vals],
                     index=unit_s.index)
    # Rebuild correctly: just use raw eq_vals scaled to dollars
    eqs  = pd.Series(eq_vals, index=unit_s.index)
    rets = eqs.pct_change().fillna(eqs.iloc[0] / INIT - 1.0)
    dd_s = (eqs - eqs.cummax()) / eqs.cummax()
    years = max((eqs.index[-1] - eqs.index[0]).days / 365.25, 1e-9)
    cagr  = float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0)
    sh    = float(np.sqrt(24 * 365.25) * rets.mean() / rets.std()) if rets.std() > 0 else 0.0
    calmar = cagr / abs(float(dd_s.min())) if dd_s.min() < 0 else 0.0
    return dict(
        eq         = eqs,
        final      = float(eqs.iloc[-1]),
        profit     = float(eqs.iloc[-1] - INIT),
        calmar     = calmar,
        cagr       = cagr,
        maxdd      = float(dd_s.min()),
        sharpe     = sh,
        ret        = float(eqs.iloc[-1] / INIT - 1.0),
        pct_halted = float(np.mean(cb_flags)),
        n_trips    = int(sum(cb_flags[i] > cb_flags[i-1] for i in range(1, len(cb_flags)))),
    )


def print_dollar_yearly(eq: pd.Series, label: str) -> None:
    groups = eq.groupby(pd.Grouper(freq='YE'))
    print(f'  {"Year":<12}  {"Start $":>10}  {"End $":>10}  {"P&L $":>10}  '
          f'{"P&L %":>8}  {"Sharpe":>8}  {"MaxDD":>8}')
    print(f'  {"─"*78}')
    for period, s in groups:
        if len(s) < 2: continue
        yr_start = float(s.iloc[0])
        yr_end   = float(s.iloc[-1])
        yr_ret   = s.pct_change().dropna()
        yr_sh    = float(np.sqrt(24*365.25) * yr_ret.mean() / yr_ret.std()) if yr_ret.std() > 0 else 0.0
        yr_dd    = float(((s - s.cummax()) / s.cummax()).min())
        print(f'  {str(period.year):<12}  {yr_start:>10,.2f}  {yr_end:>10,.2f}  '
              f'{yr_end-yr_start:>+10,.2f}  '
              f'{yr_end/yr_start-1:>+7.1%}  {yr_sh:>+8.3f}  {yr_dd:>+7.2%}')


def print_dollar_quarterly(eq: pd.Series) -> None:
    groups = eq.groupby(pd.Grouper(freq='QE'))
    print(f'  {"Quarter":<12}  {"Start $":>10}  {"End $":>10}  {"P&L $":>10}  {"P&L %":>8}')
    print(f'  {"─"*58}')
    for period, s in groups:
        if len(s) < 2: continue
        qs = float(s.iloc[0]); qe = float(s.iloc[-1])
        yr_q = f'{period.year}-Q{period.quarter}'
        print(f'  {yr_q:<12}  {qs:>10,.2f}  {qe:>10,.2f}  {qe-qs:>+10,.2f}  {qe/qs-1:>+7.1%}')


def main():
    t0 = time.time()
    print(BAR)
    print('  $1,000 PRODUCTION SIMULATION — layered_daily_no_crash_ze7')
    print(f'  CB: halt={CB_HALT:.0%}  resume={CB_RESUME:.0%}  window={CB_WINDOW_DAYS}d')
    print(f'  ZE7 gate: abs(zE7)≥{ZE7_MIN_FORCE}')
    print(BAR)

    # ── [1] Load and build ─────────────────────────────────────────────────────
    print('\n[1] Loading data ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ch       = get_channel_series()
    ohlc_all = fetch_futures_ohlcv()

    print('[2] Building positions ...')
    p_day = build_positions(df_1h, comp_raw, calib_mask, ohlc_all)
    daily_vol     = p_day['daily_vol']
    sl            = BASE['sl_mult'] * daily_vol
    tp            = BASE['tp_mult'] * daily_vol
    trail_trigger = TRAIL_TRIGGER_MULT * daily_vol
    trail_dist    = TRAIL_DIST_MULT    * daily_vol
    hours         = p_day['hours']
    q_mult        = _build_quadrant_multiplier(ch, hours)
    layered_size  = p_day['size_mult'] * q_mult

    print('[3] Running unit simulation (once) ...')
    ze7_s   = ch['E7'].reindex(hours, method='ffill').fillna(0.0).shift(1).fillna(0.0)
    ze7_arr = ze7_s.values

    unit_arr, cnt = simulate_unit_trailing_ze7gate(
        p_day['op'], p_day['hi'], p_day['lo'], p_day['cl'],
        p_day['hpos'], p_day['dpos'], p_day['dactive'],
        layered_size, sl, tp, trail_trigger, trail_dist,
        ze7_arr=ze7_arr, ze7_min=ZE7_MIN_FORCE,
    )
    unit_s    = pd.Series(unit_arr, index=hours)
    unit_zero = pd.Series(np.zeros(len(hours)), index=hours)

    n_entries = cnt['entries']
    n_vetoed  = cnt['vetoed_force']
    avg_hold  = cnt['active_hours'] / max(n_entries, 1)
    print(f'  Entries={n_entries}  vetoed={n_vetoed} ({n_vetoed/(n_entries+n_vetoed):.1%})')
    print(f'  Avg hold: {avg_hold:.1f}h  ({avg_hold/24:.1f} days)')
    print(f'  SL={sl:.2%}  TP={tp:.2%}  trail_trig={trail_trigger:.2%}  trail_dist={trail_dist:.2%}')

    # ── [4] Build entry and active arrays for cost injection ──────────────────
    # Replay the sim to track per-bar entry flags and active-position flags
    # We piggyback on the unit_arr: entry bars have large one-time RT deduction baked in.
    # Simpler: re-track entry bars directly from position changes.
    # Use a lightweight replay: pos changes from 0 → nonzero = entry.
    print('[4] Tracking per-bar entry and active flags ...')
    pos_arr = np.zeros(len(hours), dtype=np.int8)
    entries_per_bar  = np.zeros(len(hours), dtype=np.int8)
    position_active  = np.zeros(len(hours), dtype=np.int8)

    pos = 0.0; entry = 0.0
    stop_price = 0.0; take_price = 0.0
    trail_active = False; trail_extreme = 0.0
    op = p_day['op']; hi = p_day['hi']
    lo = p_day['lo']; cl = p_day['cl']
    hpos_arr   = p_day['hpos']
    dpos_arr   = p_day['dpos']
    dactive_arr= p_day['dactive']

    for i in range(len(hours)):
        hpos   = hpos_arr[i]; hactive = (hpos != 0)
        dpos_i = dpos_arr[i]; dact_i  = dactive_arr[i]

        if hactive:
            if dact_i and hpos == dpos_i:   scale = 1.0
            elif dact_i and hpos != dpos_i: hactive = False
            else:                           scale = 0.5

        if pos != 0:
            position_active[i] = 1
            if pos > 0:
                if hi[i] >= take_price or lo[i] <= stop_price:
                    pos = 0; entry = 0; stop_price = 0; take_price = 0
                    trail_active = False; trail_extreme = 0.0
                else:
                    trail_extreme = max(trail_extreme, hi[i])
                    if trail_extreme / entry - 1.0 >= trail_trigger:
                        trail_active = True
                    if trail_active:
                        new_ts = trail_extreme * (1.0 - trail_dist)
                        if new_ts > stop_price: stop_price = new_ts
            else:
                if lo[i] <= take_price or hi[i] >= stop_price:
                    pos = 0; entry = 0; stop_price = 0; take_price = 0
                    trail_active = False; trail_extreme = 0.0
                else:
                    trail_extreme = min(trail_extreme, lo[i])
                    if entry / trail_extreme - 1.0 >= trail_trigger:
                        trail_active = True
                    if trail_active:
                        new_ts = trail_extreme * (1.0 + trail_dist)
                        if new_ts < stop_price: stop_price = new_ts

        if pos == 0 and hactive:
            if abs(ze7_arr[i]) >= ZE7_MIN_FORCE:
                pos = float(hpos); entry = float(op[i])
                trail_active = False; trail_extreme = float(op[i])
                if pos > 0:
                    stop_price = entry * (1.0 - sl)
                    take_price = entry * (1.0 + tp)
                else:
                    stop_price = entry * (1.0 + sl)
                    take_price = entry * (1.0 - tp)
                entries_per_bar[i] = 1

    total_active_hours = int(position_active.sum())
    total_entries_tracked = int(entries_per_bar.sum())
    print(f'  Cross-check: tracked entries={total_entries_tracked} (expected {n_entries})')
    print(f'  Total active hours: {total_active_hours}  '
          f'({total_active_hours/24:.0f} days in position over full history)')

    # ── [5] Run all cost tiers ─────────────────────────────────────────────────
    print(f'\n[5] Simulating cost tiers ...')

    # MODEL_RT_BPS already paid in unit_arr: 2bps RT + ~0.05bps/day fund
    # Extra cost = tier_total - model_assumption
    results = {}
    for key, tier in TIERS.items():
        extra_rt   = tier['fee_bps'] + tier['slip_bps'] - MODEL_RT_BPS
        extra_fund = tier['fund_bps_d'] - (MODEL_FUND_HOURLY * 1e4 * 24)
        extra_rt   = max(extra_rt, 0.0)
        extra_fund = max(extra_fund, 0.0)
        r = simulate_combined_with_cost(
            unit_s, entries_per_bar, position_active, extra_rt, extra_fund
        )
        results[key] = (tier, r)

    # ── [6] Print summary table ────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SUMMARY — OOS (2023-01 → 2026-04)  [Starting capital: $1,000]')
    print(BAR)

    oos_results = {}
    for key, (tier, res) in results.items():
        eq_oos = res['eq'][res['eq'].index >= TEST_TS]
        eq_oos = eq_oos * (INIT / float(eq_oos.iloc[0]))  # normalise OOS to $1000 start
        oos_ret = eq_oos.pct_change().dropna()
        oos_dd  = (eq_oos - eq_oos.cummax()) / eq_oos.cummax()
        oos_years= max((eq_oos.index[-1] - eq_oos.index[0]).days / 365.25, 1e-9)
        oos_cagr = float((eq_oos.iloc[-1] / INIT) ** (1 / oos_years) - 1.0)
        oos_maxdd= float(oos_dd.min())
        oos_calmar = oos_cagr / abs(oos_maxdd) if oos_maxdd < 0 else 0.0
        oos_sh   = float(np.sqrt(24*365.25) * oos_ret.mean() / oos_ret.std()) if oos_ret.std() > 0 else 0.0
        oos_profit = float(eq_oos.iloc[-1] - INIT)
        oos_results[key] = dict(
            eq=eq_oos, calmar=oos_calmar, cagr=oos_cagr, maxdd=oos_maxdd,
            sharpe=oos_sh, profit=oos_profit, final=float(eq_oos.iloc[-1]),
        )
        total_rt_bps = tier['fee_bps'] + tier['slip_bps']
        print(f'\n  ── {tier["label"]}')
        print(f'     RT cost: {total_rt_bps:.0f} bps/trade  '
              f'Fund: {tier["fund_bps_d"]:.1f} bps/day')
        print(f'     OOS Calmar={oos_calmar:+.3f}  CAGR={oos_cagr:+.1%}  '
              f'MaxDD={oos_maxdd:+.2%}  Sharpe={oos_sh:+.3f}')
        print(f'     $1,000 → ${eq_oos.iloc[-1]:,.2f}  (P&L: ${oos_profit:+,.2f}  '
              f'= {eq_oos.iloc[-1]/INIT-1:+.1%})')

    # ── [7] Detailed yearly tables ─────────────────────────────────────────────
    for key, (tier, res) in results.items():
        eq_full = res['eq']
        eq_oos  = oos_results[key]['eq']
        print(f'\n{BAR}')
        print(f'  {tier["label"]}')
        print(BAR)
        print(f'\n  FULL HISTORY (train + OOS):')
        # rescale full to $1000 at start
        eq_full_norm = eq_full * (INIT / float(eq_full.iloc[0]))
        print_dollar_yearly(eq_full_norm, key)

        print(f'\n  OOS QUARTERLY ($1,000 at OOS start):')
        print_dollar_quarterly(eq_oos)

        # Drawdowns (OOS)
        dd_s = (eq_oos - eq_oos.cummax()) / eq_oos.cummax()
        dds  = []
        in_dd = False; start_dd = None; peak_dd = 0.0; trough_t = None
        peak_v = float(eq_oos.iloc[0])
        for t, v in eq_oos.items():
            v = float(v)
            if v >= peak_v:
                if in_dd:
                    dds.append(dict(start=start_dd, trough=trough_t, end=t,
                                    dd=peak_dd, peak_v=peak_v))
                    in_dd = False; peak_dd = 0.0
                peak_v = v
            else:
                dd_here = v / peak_v - 1.0
                if not in_dd:
                    in_dd = True; start_dd = t; peak_dd = dd_here; trough_t = t
                elif dd_here < peak_dd:
                    peak_dd = dd_here; trough_t = t
        if in_dd:
            dds.append(dict(start=start_dd, trough=trough_t, end=None,
                            dd=peak_dd, peak_v=peak_v))
        dds.sort(key=lambda x: x['dd'])
        print(f'\n  TOP DRAWDOWNS (OOS):')
        print(f'  {"Start":>12}  {"Trough":>12}  {"End":>12}  {"DD":>8}  {"Days":>6}  Peak$  Trough$')
        print(f'  {"─"*78}')
        for d in dds[:6]:
            end_str = str(d['end'])[:10] if d['end'] else 'ongoing'
            days = (d['trough'] - d['start']).days if d['trough'] else 0
            trough_v = d['peak_v'] * (1 + d['dd'])
            print(f'  {str(d["start"])[:10]:>12}  {str(d["trough"])[:10]:>12}  '
                  f'{end_str:>12}  {d["dd"]:>+7.2%}  {days:>6}  '
                  f'${d["peak_v"]:>8,.0f}  ${trough_v:>8,.0f}')

    # ── [8] Cost sensitivity / break-even ─────────────────────────────────────
    print(f'\n{BAR}')
    print('  COST SENSITIVITY — OOS Calmar vs total RT cost (bps)')
    print('  (fund drag fixed at 1 bps/day, sweeping RT cost 0→40 bps)')
    print(BAR)
    print(f'  {"RT bps":>8}  {"Calmar":>8}  {"MaxDD":>8}  {"CAGR":>8}  {"$Final":>10}')
    print(f'  {"─"*50}')
    for rt_bps in [0, 5, 10, 14, 20, 24, 30, 40]:
        extra_rt   = max(rt_bps - MODEL_RT_BPS, 0.0)
        extra_fund = max(1.0 - MODEL_FUND_HOURLY * 1e4 * 24, 0.0)
        r = simulate_combined_with_cost(
            unit_s, entries_per_bar, position_active, extra_rt, extra_fund
        )
        eq_s = r['eq'][r['eq'].index >= TEST_TS]
        eq_s = eq_s * (INIT / float(eq_s.iloc[0]))
        yr_oos = max((eq_s.index[-1] - eq_s.index[0]).days / 365.25, 1e-9)
        cg = float((eq_s.iloc[-1] / INIT) ** (1 / yr_oos) - 1.0)
        dd = float(((eq_s - eq_s.cummax()) / eq_s.cummax()).min())
        cal = cg / abs(dd) if dd < 0 else 0.0
        mark = '  ← BREAK-EVEN' if abs(cal - 1.0) < 0.15 else ''
        mark = '  ← REALISTIC' if rt_bps == 14 else mark
        mark = '  ← PESSIMISTIC' if rt_bps == 24 else mark
        print(f'  {rt_bps:>8}  {cal:>+8.3f}  {dd:>+7.2%}  {cg:>+7.1%}  '
              f'${eq_s.iloc[-1]:>9,.0f}  {mark}')

    # ── [9] Key statistics ─────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TRADE STATISTICS')
    print(BAR)
    trade_freq = n_entries / max((hours[-1] - hours[hours >= TEST_TS][0]).days / 365.25, 1e-9)
    oos_entries = entries_per_bar[np.searchsorted(hours, TEST_TS):].sum()
    oos_active  = position_active[np.searchsorted(hours, TEST_TS):].sum()
    oos_years   = max((hours[-1] - hours[hours >= TEST_TS][0]).days / 365.25, 1e-9)
    print(f'  OOS entries:      {oos_entries}  ({oos_entries/oos_years:.0f}/year, {oos_entries/oos_years/12:.1f}/month)')
    print(f'  Avg hold:         {oos_active/max(oos_entries,1):.1f}h ({oos_active/max(oos_entries,1)/24:.1f} days)')
    print(f'  Time in market:   {oos_active/(oos_years*365.25*24):.1%} of OOS hours')
    print(f'  SL:               {sl:.2%}  TP: {tp:.2%}  trail_trigger: {trail_trigger:.2%}')
    print(f'  CB: halt={CB_HALT:.0%}  resume={CB_RESUME:.0%}  window={CB_WINDOW_DAYS}d')
    print(f'  ZE7 min force:    {ZE7_MIN_FORCE:.2f} (vetoed {n_vetoed} entries, {n_vetoed/(n_entries+n_vetoed):.1%})')

    # Realistic cost breakdown for oos_entries trades
    rt_bps_real = 14.0
    fund_total_bps = 1.0 * (oos_active / HOURS_PER_DAY)  # total bps funding drag
    fee_total      = rt_bps_real * oos_entries / 1e4 * INIT   # dollar estimate (rough, unit sizing)
    print(f'\n  Cost breakdown (REALISTIC, rough $ estimate on $1k starting):')
    print(f'    Round-trip fee+slip:  {rt_bps_real:.0f} bps × {oos_entries} entries')
    print(f'    Total funding drag:   1 bps/day × {oos_active/HOURS_PER_DAY:.0f} active days')

    print(f'\n  Total elapsed: {time.time()-t0:.1f}s')


if __name__ == '__main__':
    main()
