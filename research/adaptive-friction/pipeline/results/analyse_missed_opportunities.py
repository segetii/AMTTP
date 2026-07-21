"""
analyse_missed_opportunities.py — Missed Profitable Move Forensics
===================================================================
For the champion strategy (layered_daily_no_crash_ze7), identifies every
bar where an entry was BLOCKED and computes the hypothetical outcome if we
had taken it anyway.  Three blocking categories:

  [A] DIRECTION MISMATCH  — hourly says LONG, daily says SHORT (or vice versa)
                            → completely blocked in simulate_unit_trailing_ze7gate

  [B] CIRCUIT BREAKER     — equity drawdown > 8% from 180d peak  
                            → unit returns are zeroed by simulate_combined
                            (entry physically happens in unit sim but earns 0)

  [C] SIGNAL SUB-THRESHOLD — hourly |comp| is BELOW the calibration threshold
                            → hpos == 0 (signal off), but market moves anyway

For each category the script computes:
  - Count of potential entries
  - Hypothetical win rate (hits TP before SL)
  - Average hypothetical PnL  
  - Total "left-on-the-table" profit if those entries had been taken
  - Year-by-year breakdown
  - Top-10 single best missed trades

Usage:
    py -3 analyse_missed_opportunities.py
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
from test_psi_adaptive_y                import BASE, simulate_unit_with_psi
from simulate_adaptive_y_drawdown_brake import INIT
from test_dynamic_profit_sizing         import _percentile_against
from simulate_master_strategy           import (
    equity_metrics, build_positions,
    simulate_unit_trailing,
    RT_COST, FUND_HOURLY, HOURS_PER_DAY,
    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
)
from simulate_v63_quadrant import (
    _build_quadrant_multiplier,
    CB_HALT, CB_RESUME, CB_WINDOW_DAYS,
    TRAIL_TRIGGER_MULT, TRAIL_DIST_MULT,
    ZE7_MIN_FORCE,
)

BAR = '=' * 110
SEP = '-' * 110
TEST_TS = pd.Timestamp(TEST_START)

MAX_HOLD_BARS = 240   # max forward-scan for hypothetical outcome (10 days)


# ─────────────────────────────────────────────────────────────────────────────
def sim_hypothetical_sl_tp(direction: int, entry_px: float,
                            op, hi, lo, cl,
                            i_entry: int, sl: float, tp: float) -> tuple:
    """Scan forward from bar i_entry+1; return (gross_pct, reason, bars_held)."""
    n = len(op)
    tp_px = entry_px * (1.0 + tp) if direction > 0 else entry_px * (1.0 - tp)
    sl_px = entry_px * (1.0 - sl) if direction > 0 else entry_px * (1.0 + sl)

    for j in range(i_entry + 1, min(i_entry + 1 + MAX_HOLD_BARS, n)):
        if direction > 0:
            if hi[j] >= tp_px:
                return tp, 'tp', j - i_entry
            if lo[j] <= sl_px:
                return -sl, 'stop', j - i_entry
        else:
            if lo[j] <= tp_px:
                return tp, 'tp', j - i_entry
            if hi[j] >= sl_px:
                return -sl, 'stop', j - i_entry

    # time exit at last scanned bar
    j_end = min(i_entry + MAX_HOLD_BARS, n - 1)
    gross = (cl[j_end] / entry_px - 1.0) if direction > 0 else (entry_px / cl[j_end] - 1.0)
    return gross, 'time', j_end - i_entry


def compute_cb_state_per_bar(unit_arr: np.ndarray, hours: pd.DatetimeIndex) -> np.ndarray:
    """Replay simulate_combined CB logic; return per-bar halted flag (0/1)."""
    window_bars = CB_WINDOW_DAYS * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq = INIT; peak_alltime = INIT; halted = False
    flags = np.zeros(len(unit_arr), dtype=np.int8)

    for i in range(len(unit_arr)):
        ur = float(unit_arr[i])
        # sliding window peak
        while mono_dq and mono_dq[0][0] <= i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((i, eq))
        roll_peak = mono_dq[0][1]

        cb_dd = max(0.0, 1.0 - eq / max(roll_peak, 1e-12))
        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        if not halted and cb_dd >= CB_HALT:
            halted = True
        elif halted and cb_dd <= CB_RESUME:
            halted = False

        flags[i] = int(halted)

        y = 0.0 if halted else (
            1.0 if dd_aty <= DYN_DD_SOFT else
            DYN_Y_FLOOR if dd_aty >= DYN_DD_STOP else
            DYN_Y_FLOOR + (1.0 - DYN_Y_FLOOR) * (DYN_DD_STOP - dd_aty) / (DYN_DD_STOP - DYN_DD_SOFT)
        )
        r = DYN_K * y * ur
        r = max(r, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)

    return flags


def collect_blocked_records(p_day, ch, sl, tp, cb_flags: np.ndarray) -> pd.DataFrame:
    """
    Replay bar-by-bar logic identical to simulate_unit_trailing_ze7gate but
    instead of discarding blocked entries, records them with their blocking reason
    and hypothetical outcome.

    Returns DataFrame with one row per blocked entry.
    """
    op   = p_day['op'];   hi   = p_day['hi']
    lo   = p_day['lo'];   cl   = p_day['cl']
    hours = p_day['hours']
    hpos_arr  = p_day['hpos']
    dpos_arr  = p_day['dpos']
    dactive_arr = p_day['dactive']
    layered_size = p_day['size_mult'] * _build_quadrant_multiplier(ch, hours)

    ze7_s = ch['E7'].reindex(hours, method='ffill').fillna(0.0).shift(1).fillna(0.0)
    ze7_arr = ze7_s.values

    # sub-threshold signal: raw comp (shifted, causal)
    from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
    from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS
    from simulate_master_strategy import build_positions as _bp
    # Note: comp_raw came from build_daily_geometry already; we use hpos_arr which
    # encodes the signal direction; sub-threshold bars have hpos==0

    n = len(op)
    pos = 0.0; entry = 0.0
    stop_price = 0.0; take_price = 0.0
    trail_trigger = TRAIL_TRIGGER_MULT * (sl / BASE['sl_mult'] * BASE['sl_mult'])
    # re-derive daily_vol from sl
    daily_vol = sl / BASE['sl_mult']
    trail_trigger = TRAIL_TRIGGER_MULT * daily_vol
    trail_dist    = TRAIL_DIST_MULT    * daily_vol
    trail_active  = False; trail_extreme = 0.0
    trailing_on   = True

    records: list[dict] = []

    for i in range(n):
        hpos    = hpos_arr[i]
        hactive = (hpos != 0)
        dpos_i  = dpos_arr[i]
        dact_i  = dactive_arr[i]
        is_oos  = (hours[i] >= TEST_TS)

        # Determine blocking reason for this bar (if any)
        block_reason = None
        direction    = int(hpos) if hpos != 0 else 0

        if not hactive:
            # [C] sub-threshold: signal is off
            # — we could look at what the raw move was, but there's no directional
            # guess without a signal. Skip.
            pass
        elif hactive:
            # Compute the 'effective' status as in the real simulator
            if dact_i and hpos == dpos_i:
                scale = 1.0    # aligned → would enter (not blocked by filter)
            elif dact_i and hpos != dpos_i:
                block_reason = 'direction_mismatch'  # [A] completely blocked
            else:
                scale = 0.5    # would enter at half size (not blocked)

        # CB override: if market was CB-halted at this bar AND would have entered
        if block_reason is None and hactive:
            # A bar that passes filters but CB zeros it
            if dact_i and hpos == dpos_i:
                if cb_flags[i] == 1:
                    block_reason = 'cb_halted'
            elif not dact_i:   # daily off → half-size → CB still zeros
                if cb_flags[i] == 1:
                    block_reason = 'cb_halted'

        # Manage open position state (track to know if bar is in-position)
        if pos != 0:
            exit_ret = None
            if pos > 0:
                if hi[i] >= take_price:
                    exit_ret = take_price / entry - 1; pos = 0
                elif lo[i] <= stop_price:
                    exit_ret = stop_price / entry - 1; pos = 0
                else:
                    trail_extreme = max(trail_extreme, hi[i])
                    if trail_extreme / entry - 1.0 >= trail_trigger:
                        trail_active = True
                    if trail_active:
                        new_ts = trail_extreme * (1.0 - trail_dist)
                        if new_ts > stop_price: stop_price = new_ts
            else:
                if lo[i] <= take_price:
                    exit_ret = entry / take_price - 1; pos = 0
                elif hi[i] >= stop_price:
                    exit_ret = entry / stop_price - 1; pos = 0
                else:
                    trail_extreme = min(trail_extreme, lo[i])
                    if entry / trail_extreme - 1.0 >= trail_trigger:
                        trail_active = True
                    if trail_active:
                        new_ts = trail_extreme * (1.0 + trail_dist)
                        if new_ts < stop_price: stop_price = new_ts
            if exit_ret is not None:
                pos = 0; entry = 0; stop_price = 0; take_price = 0
                trail_active = False; trail_extreme = 0.0

        # Was in position during this bar?
        in_position = (pos != 0)

        # Record blocked entry for [A] and [B]
        if block_reason is not None and direction != 0:
            entry_px = op[i]
            hyp_pnl, hyp_reason, hyp_bars = sim_hypothetical_sl_tp(
                direction, entry_px, op, hi, lo, cl, i, sl, tp
            )
            records.append(dict(
                bar_idx       = i,
                timestamp     = hours[i],
                is_oos        = int(is_oos),
                year          = hours[i].year,
                block_reason  = block_reason,
                direction     = direction,
                entry_px      = entry_px,
                zE7           = float(ze7_arr[i]),
                abs_zE7       = abs(float(ze7_arr[i])),
                dact          = int(dact_i),
                hpos          = int(hpos),
                dpos          = int(dpos_i),
                cb_halted     = int(cb_flags[i]),
                in_position   = int(in_position),
                hyp_pnl       = hyp_pnl,
                hyp_reason    = hyp_reason,
                hyp_bars_held = hyp_bars,
                hyp_winner    = int(hyp_reason == 'tp'),
            ))

        # Open new position in the real sim (if not blocked by EITHER filter or CB)
        if pos == 0 and hactive and block_reason is None:
            # ze7 gate
            if abs(ze7_arr[i]) >= ZE7_MIN_FORCE:
                pos   = float(hpos); entry = float(op[i])
                trail_active  = False; trail_extreme = float(op[i])
                if pos > 0:
                    stop_price = entry * (1.0 - sl)
                    take_price = entry * (1.0 + tp)
                else:
                    stop_price = entry * (1.0 + sl)
                    take_price = entry * (1.0 - tp)

    df = pd.DataFrame(records)
    return df


def print_summary(df_all: pd.DataFrame, label: str, sl: float, tp: float) -> None:
    print(f'\n{BAR}')
    print(f'  {label}')
    print(BAR)
    if df_all.empty:
        print('  (no records)'); return

    oos = df_all[df_all['is_oos'] == 1].copy()
    for cat, grp in oos.groupby('block_reason', sort=False):
        n     = len(grp)
        wr    = grp['hyp_winner'].mean()
        avg   = grp['hyp_pnl'].mean()
        total = grp['hyp_pnl'].sum()
        print(f'\n  ── {cat.upper()}  (n={n}, OOS only) ──')
        print(f'     Win rate (hits TP):  {wr:.1%}')
        print(f'     Avg hypothetical PnL per trade:  {avg:+.4f}%   '
              f'({avg*100:.2f} bps)')
        print(f'     Total "left on table" (unit sum): {total:+.2f}%')

        print(f'\n     Year  Count  WinRate  AvgPnL   TotalPnL  AvgZE7')
        print(f'     {"─"*64}')
        for yr, yg in grp.groupby('year'):
            yn  = len(yg)
            ywr = yg['hyp_winner'].mean()
            yav = yg['hyp_pnl'].mean()
            yto = yg['hyp_pnl'].sum()
            yze = yg['abs_zE7'].mean()
            print(f'     {yr}  {yn:>5}  {ywr:>7.1%}  {yav:>+7.4f}%  '
                  f'{yto:>+9.2f}%  {yze:>7.3f}')

        print(f'\n     Exit reason breakdown:')
        for reason, rg in grp.groupby('hyp_reason'):
            print(f'       {reason:>10}: {len(rg):>5} ({len(rg)/n:.1%})'
                  f'  avgPnL={rg["hyp_pnl"].mean():+.4f}%')

        print(f'\n     |zE7| distribution at blocked entry:')
        bins = [0, 0.05, 0.10, 0.20, 0.50, 1.0, 9999]
        lbls = ['~0(0–0.05)', 'low(0.05–0.10)', 'med(0.10–0.20)',
                'high(0.20–0.50)', 'v.high(0.5–1.0)', 'extreme(>1.0)']
        for i, (lo_b, hi_b) in enumerate(zip(bins[:-1], bins[1:])):
            sub = grp[(grp['abs_zE7'] >= lo_b) & (grp['abs_zE7'] < hi_b)]
            if len(sub) == 0: continue
            print(f'       {lbls[i]:>22}: {len(sub):>5} ({len(sub)/n:.1%})'
                  f'  winRate={sub["hyp_winner"].mean():.1%}'
                  f'  avgPnL={sub["hyp_pnl"].mean():+.4f}%')

        print(f'\n     TOP 10 BEST SINGLE MISSED TRADES (by hypothetical PnL):')
        top = grp.nlargest(10, 'hyp_pnl')[
            ['timestamp', 'direction', 'hyp_pnl', 'hyp_reason',
             'hyp_bars_held', 'abs_zE7', 'cb_halted', 'dact']
        ]
        for _, row in top.iterrows():
            dir_str = 'L' if row['direction'] > 0 else 'S'
            print(f'       {str(row["timestamp"])[:16]}  {dir_str}  '
                  f'pnl={row["hyp_pnl"]:+.4f}%  {row["hyp_reason"]:>10}  '
                  f'{int(row["hyp_bars_held"]):>4}h  '
                  f'|zE7|={row["abs_zE7"]:.3f}  '
                  f'cb={int(row["cb_halted"])}  dact={int(row["dact"])}')


def main():
    t0 = time.time()
    print(BAR)
    print('  MISSED PROFITABLE MOVES — FORENSIC ANALYSIS')
    print('  Champion: layered_daily_no_crash_ze7  (Calmar=+7.974, MaxDD=−16.80%)')
    print(BAR)

    print('\n[1] Loading data ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ch         = get_channel_series()
    ohlc_all   = fetch_futures_ohlcv()

    print('\n[2] Building positions (champion daily filter) ...')
    p_day = build_positions(df_1h, comp_raw, calib_mask, ohlc_all)
    daily_vol = p_day['daily_vol']
    sl = BASE['sl_mult'] * daily_vol
    tp = BASE['tp_mult'] * daily_vol
    q_mult     = _build_quadrant_multiplier(ch, p_day['hours'])
    layered_size = p_day['size_mult'] * q_mult

    print(f'  daily_vol={daily_vol:.2%}  SL={sl:.2%}  TP={tp:.2%}')
    print(f'  OOS bars: {(p_day["hours"] >= TEST_TS).sum()}')

    print('\n[3] Running unit simulation to derive CB state per bar ...')
    unit_arr, _ = simulate_unit_trailing(
        p_day['op'], p_day['hi'], p_day['lo'], p_day['cl'],
        p_day['hpos'], p_day['dpos'], p_day['dactive'],
        layered_size, sl, tp,
        TRAIL_TRIGGER_MULT * daily_vol, TRAIL_DIST_MULT * daily_vol,
    )
    cb_flags = compute_cb_state_per_bar(unit_arr, p_day['hours'])
    pct_halted = float(cb_flags.mean())
    print(f'  CB halted: {pct_halted:.1%} of all bars')
    print(f'  CB halted (OOS): {float(cb_flags[p_day["hours"] >= TEST_TS].mean()):.1%}')

    print('\n[4] Collecting blocked entry records ...')
    df_blocked = collect_blocked_records(p_day, ch, sl, tp, cb_flags)
    print(f'  Total blocked entries recorded: {len(df_blocked)}')
    print(f'  OOS blocked entries: {df_blocked["is_oos"].sum()}')
    by_cat = df_blocked[df_blocked['is_oos']==1].groupby('block_reason').size()
    for cat, n in by_cat.items():
        print(f'    {cat}: {n}')

    print_summary(df_blocked, 'MISSED OPPORTUNITY ANALYSIS (OOS)', sl, tp)

    # ── [C] LARGE MARKET MOVES WITH NO SIGNAL ─────────────────────────────────
    print(f'\n{BAR}')
    print('  [C] LARGE MARKET MOVES — BSDT SIGNAL WAS OFF (sub-threshold)')
    print(BAR)
    hours  = p_day['hours']
    cl_s   = pd.Series(p_day['cl'].astype(float), index=hours)
    hpos_s = pd.Series(p_day['hpos'].astype(float), index=hours)

    fwd_ret_24h = cl_s.pct_change(24).shift(-24)  # causal look-forward
    fwd_ret_12h = cl_s.pct_change(12).shift(-12)
    fwd_ret_6h  = cl_s.pct_change(6).shift(-6)

    # bars where signal was OFF (hpos==0) AND OOS
    no_signal = (hpos_s == 0) & (hours >= TEST_TS)
    ns_df = pd.DataFrame({
        'fwd_24h': fwd_ret_24h,
        'fwd_12h': fwd_ret_12h,
        'fwd_6h' : fwd_ret_6h,
        'year'   : hours.year,
    })[no_signal].dropna()

    print(f'\n  Bars with no signal (OOS): {len(ns_df):,}')
    print(f'  Distribution of 24h forward return when BSDT was silent:')
    pct_large_up   = (ns_df['fwd_24h'] >  0.05).mean()
    pct_large_down = (ns_df['fwd_24h'] < -0.05).mean()
    pct_flat       = ((ns_df['fwd_24h'].abs()) < 0.01).mean()
    print(f'    >+5% in 24h: {pct_large_up:.1%}  (<-5%: {pct_large_down:.1%}  flat<1%: {pct_flat:.1%})')

    big_up_missed = ns_df[ns_df['fwd_24h'] > 0.05].sort_values('fwd_24h', ascending=False)
    print(f'\n  TOP 15 LARGEST UPWARD MOVES BSDT NEVER SIGNALLED (OOS, signal-off):')
    print(f'  {"Timestamp":>20}  {"Fwd24h":>8}  {"Fwd12h":>8}  {"Fwd6h":>7}  Year')
    print(f'  {"─"*60}')
    for ts, row in big_up_missed.head(15).iterrows():
        print(f'  {str(ts)[:19]:>20}  {row["fwd_24h"]:>+7.2%}  '
              f'{row["fwd_12h"]:>+7.2%}  {row["fwd_6h"]:>+6.2%}  {int(row["year"])}')

    # Year breakdown of missed big up-moves
    print(f'\n  By year (no-signal OOS bars that had >5% gain in 24h):')
    for yr, yg in big_up_missed.groupby('year'):
        print(f'    {yr}: {len(yg):>4} large up-moves missed  '
              f'avg={yg["fwd_24h"].mean():+.2%}  max={yg["fwd_24h"].max():+.2%}')

    big_down_missed = ns_df[ns_df['fwd_24h'] < -0.05].sort_values('fwd_24h')
    print(f'\n  By year (no-signal OOS bars that had >5% DROP in 24h — missed SHORT):')
    for yr, yg in big_down_missed.groupby('year'):
        print(f'    {yr}: {len(yg):>4} large down-moves missed  '
              f'avg={yg["fwd_24h"].mean():+.2%}  worst={yg["fwd_24h"].min():+.2%}')

    # ── CB-halted big moves ────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  [B+] CB-HALTED PERIODS — LARGE MOVES THAT THE PORTFOLIO ZEROED')
    print(BAR)
    cb_s = pd.Series(cb_flags, index=hours)
    sig_on = hpos_s != 0
    cb_and_signal = (cb_s == 1) & sig_on & (hours >= TEST_TS)
    cb_sig_df = pd.DataFrame({
        'direction' : hpos_s,
        'fwd_24h'   : fwd_ret_24h,
        'cb_halted' : cb_s,
        'year'      : hours.year,
    })[cb_and_signal].dropna()

    # Compute hypothetical outcome: direction × fwd_24h (rough proxy)
    cb_sig_df['aligned_ret'] = cb_sig_df['direction'] * cb_sig_df['fwd_24h']

    print(f'\n  Signal-active bars during CB halt (OOS): {len(cb_sig_df):,}')
    pct_would_have_won = (cb_sig_df['aligned_ret'] > 0).mean()
    avg_win  = cb_sig_df[cb_sig_df['aligned_ret'] > 0]['aligned_ret'].mean()
    avg_loss = cb_sig_df[cb_sig_df['aligned_ret'] < 0]['aligned_ret'].mean()
    print(f'  If entered: would-have-won {pct_would_have_won:.1%}  '
          f'avgWin={avg_win:+.3%}  avgLoss={avg_loss:+.3%}')
    print(f'  Total aligned move sum: {cb_sig_df["aligned_ret"].sum():+.2f} '
          f'(avg per bar: {cb_sig_df["aligned_ret"].mean():+.4f})')

    print(f'\n  Year breakdown (signal-active CB-halted bars):')
    print(f'  Year  Count  WouldWin%  AvgAlignedRet  TotalAligned')
    print(f'  {"─"*58}')
    for yr, yg in cb_sig_df.groupby('year'):
        print(f'  {yr}  {len(yg):>5}  {(yg["aligned_ret"]>0).mean():>9.1%}  '
              f'{yg["aligned_ret"].mean():>+13.4%}  {yg["aligned_ret"].sum():>+12.2%}')

    print(f'\n  TOP 10 best signal-active CB-halted moves (24h aligned return):')
    top_cb = cb_sig_df.nlargest(10, 'aligned_ret')
    for ts, row in top_cb.iterrows():
        dir_s = 'L' if row['direction'] > 0 else 'S'
        print(f'    {str(ts)[:16]}  {dir_s}  24h={row["fwd_24h"]:+.3%}  '
              f'aligned={row["aligned_ret"]:+.3%}  {int(row["year"])}')

    # ── Final summary ──────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SUMMARY OF STRUCTURAL MISSES (OOS)')
    print(BAR)
    oos_blocked = df_blocked[df_blocked['is_oos'] == 1]

    dm   = oos_blocked[oos_blocked['block_reason'] == 'direction_mismatch']
    cb_b = oos_blocked[oos_blocked['block_reason'] == 'cb_halted']

    print(f'\n  Direction mismatch blocks: {len(dm):>5}  '
          f'hyp WR={dm["hyp_winner"].mean():.1%}  '
          f'avg PnL={dm["hyp_pnl"].mean():+.4f}%  '
          f'total left-on-table={dm["hyp_pnl"].sum():+.2f}%')
    print(f'  CB-halted signal bars:     {len(cb_b):>5}  '
          f'hyp WR={cb_b["hyp_winner"].mean():.1%}  '
          f'avg PnL={cb_b["hyp_pnl"].mean():+.4f}%  '
          f'total left-on-table={cb_b["hyp_pnl"].sum():+.2f}%')
    print(f'  No-signal large moves:     {len(big_up_missed)+len(big_down_missed):>5}  '
          f'(>5% in 24h while BSDT was silent)')

    print(f'\n  KEY INSIGHT:')
    dm_avg  = dm["hyp_pnl"].mean()   if len(dm)   > 0 else 0.0
    cb_avg  = cb_b["hyp_pnl"].mean() if len(cb_b) > 0 else 0.0
    dm_wr   = dm["hyp_winner"].mean() if len(dm) > 0 else 0.0
    cb_wr   = cb_b["hyp_winner"].mean() if len(cb_b) > 0 else 0.0

    if dm_avg > 0.0:
        print(f'    → Direction-mismatch blocked entries are NET PROFITABLE '
              f'(avg={dm_avg:+.4f}%, WR={dm_wr:.1%})')
        print(f'      These are real missed money — consider relaxing the daily filter '
              f'when |zE7| is strong.')
    else:
        print(f'    → Direction-mismatch blocked entries are NET LOSERS '
              f'(avg={dm_avg:+.4f}%).  Daily filter is protecting you.')

    if cb_avg > 0.0:
        print(f'    → CB-halted signal entries are NET PROFITABLE '
              f'(avg={cb_avg:+.4f}%, WR={cb_wr:.1%})')
        print(f'      Recovery moves occur during CB halts — CB has an opportunity cost.')
    else:
        print(f'    → CB-halted signal entries are NET LOSERS '
              f'(avg={cb_avg:+.4f}%).  CB is correctly protecting you from further loss.')

    print(f'\n  Total elapsed: {time.time()-t0:.1f}s')


if __name__ == '__main__':
    main()
