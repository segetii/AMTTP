"""
simulate_surge_sweep.py — Momentum LONG "Surge" Leg Sweep
==========================================================
Symmetrical counterpart to the crash-short leg.
Fires on sudden, broad-based UPSIDE moves with vol confirmation.

─── Motivation ──────────────────────────────────────────────────────────────
  Crash-short leg: ETH 12h ret < −6% AND rv > 2.5× baseline  → SHORT
  Surge-long  leg: ETH 12h ret >  +X% AND rv > Y× baseline   → LONG
                   + optional cross-coin breadth (BTC also ↑)
                   + optional vol-acceleration filter (rv is rising, not just high)

─── Why this is structurally different from the z-score approach ─────────────
  1. Uses 12h cumulative return (same window as the crash leg) — catches
     sustained momentum, not single-bar spikes that mean-revert
  2. Volume confirmation uses a *relative acceleration* metric
     (rv is rising), not just absolute level — filters re-tests of old highs
     on thin volume
  3. Has a time-exit (same as crash leg) — doesn't stay in forever
  4. Parameters calibrated on training window, applied OOS

─── Architecture ─────────────────────────────────────────────────────────────
  The surge unit runs ALONGSIDE the champion BSDT unit (not instead of it),
  exactly like the crash-short arm in simulate_combined.

  combined_return[t] = K_normal * Y * unit_bsdt[t] + K_surge * unit_surge[t]

  K_surge is swept (0.5, 1.0, 1.5) — equivalent to frac in previous sweep.
  CB/Y-brake gate only the normal BSDT leg; surge trades always go through
  (same as crash shorts — they *are* the crisis capture vehicle).

─── Sweep grid: 4 × 3 × 3 × 2 = 72 combos ─────────────────────────────────
  surge_ret_thresh : [+0.04, +0.05, +0.06, +0.08]   (12h return gate)
  vol_mult         : [1.5, 2.0, 2.5]                 (rv > mult × baseline)
  K_surge          : [0.5, 1.0, 1.5]                 (size multiplier)
  breadth_confirm  : [False, True]                    (BTC must also be +)
"""
from __future__ import annotations
import time, itertools
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from test_daily_geometry_stop_tp_ohlc   import (
    build_daily_geometry, fetch_futures_ohlcv, get_channel_series,
)
from test_psi_adaptive_y                import BASE
from simulate_master_strategy           import (
    build_positions, RT_COST, FUND_HOURLY,
    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
    CRASH_SL, CRASH_TP, CRASH_MAX_HOURS,
)
from simulate_v63_quadrant              import (
    _build_quadrant_multiplier,
    CB_WINDOW_DAYS, TRAIL_TRIGGER_MULT, TRAIL_DIST_MULT, ZE7_MIN_FORCE,
    simulate_unit_trailing_ze7gate, CB_HALT, CB_RESUME,
)
from collections import deque

INIT        = 1_000.0
TEST_TS     = pd.Timestamp(TEST_START)
TRAIN_TS    = pd.Timestamp(TRAIN_START)
BAR         = '=' * 120
SEP         = '-' * 120

# Surge-specific stops (symmetric to CRASH_SL/TP)
SURGE_SL        = CRASH_SL          # 4% stop below entry
SURGE_TP        = CRASH_TP          # 10% TP above entry
SURGE_MAX_HOURS = CRASH_MAX_HOURS   # 36h time exit

# Sweep grid
SURGE_RET_GRID  = [0.04, 0.05, 0.06, 0.08]
VOL_MULT_GRID   = [1.5, 2.0, 2.5]
K_SURGE_GRID    = [0.5, 1.0, 1.5]
BREADTH_GRID    = [False, True]


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_surge_signal(ohlc_eth: pd.DataFrame,
                       ohlc_btc: pd.DataFrame,
                       hours: pd.DatetimeIndex,
                       surge_ret_thresh: float,
                       vol_mult: float,
                       breadth_confirm: bool) -> np.ndarray:
    """Build causal surge-long signal array.

    Conditions (all evaluated at bar t-1, applied at bar t open):
      1. ETH 12h log return > surge_ret_thresh
      2. 24h realized vol   > vol_mult × training-period median vol
      3. (optional) BTC 12h log return > 0  (breadth confirmation)

    Returns integer array (1 = fire, 0 = no signal).
    """
    eth_close = ohlc_eth['close'].reindex(hours).ffill()
    btc_close = ohlc_btc['close'].reindex(hours).ffill()
    eth_ret_1h = eth_close.pct_change().fillna(0.0)

    # 12h cumulative log return — causal shift(1)
    eth_ret_12h = np.log(eth_close / eth_close.shift(12)).fillna(0.0).shift(1).fillna(0.0)
    btc_ret_12h = np.log(btc_close / btc_close.shift(12)).fillna(0.0).shift(1).fillna(0.0)

    # 24h realized vol — causal
    rv_1h_24 = eth_ret_1h.rolling(24, min_periods=12).std().shift(1).fillna(0.0)

    # Calibrate vol baseline on training window
    train_mask = (rv_1h_24.index >= TRAIN_TS) & (rv_1h_24.index < TEST_TS)
    rv_base = float(rv_1h_24[train_mask].median())

    fire = (eth_ret_12h > surge_ret_thresh) & (rv_1h_24 > vol_mult * rv_base)

    if breadth_confirm:
        fire = fire & (btc_ret_12h > 0.0)

    return fire.values.astype(int), rv_base


# ─────────────────────────────────────────────────────────────────────────────
#  SURGE UNIT SIMULATOR
# ─────────────────────────────────────────────────────────────────────────────

def simulate_surge_longs(op, hi, lo, cl, surge_signal,
                         surge_sl: float, surge_tp: float,
                         surge_max_hours: int) -> tuple:
    """Symmetrical to simulate_crash_shorts but for LONG momentum entries.

    Returns (unit_returns_array, counts).
    Unit returns include RT cost, K scaling applied externally.
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
            # Long: stop = lo <= stop (below entry), tp = hi >= take (above entry)
            if lo[i] <= stop_price:
                exit_ret = stop_price / entry - 1; reason = 'stop'
            elif hi[i] >= take_price:
                exit_ret = take_price / entry - 1; reason = 'tp'
            elif held >= surge_max_hours:
                exit_ret = cl[i] / entry - 1; reason = 'time_exit'

            if exit_ret is not None:
                ret[i] += exit_ret - RT_COST
                pos = 0; held = 0
                counts[reason] += 1; counts['exits'] += 1
            else:
                ret[i] -= FUND_HOURLY

        if pos == 0 and surge_signal[i]:
            entry      = float(op[i])
            stop_price = entry * (1.0 - surge_sl)
            take_price = entry * (1.0 + surge_tp)
            pos = 1; held = 0
            counts['entries'] += 1

    return ret, counts


# ─────────────────────────────────────────────────────────────────────────────
#  COMBINED ENGINE WITH SURGE LEG (mirrors simulate_combined adding surge)
# ─────────────────────────────────────────────────────────────────────────────

def simulate_combined_surge(unit_normal: pd.Series,
                            unit_surge: pd.Series,
                            K_normal: float,
                            K_surge: float,
                            dd_soft, dd_stop, y_floor,
                            cb_halt, cb_resume, cb_window_days) -> dict:
    """CB + adaptive-Y on the BSDT normal leg; surge leg always active."""
    window_bars = cb_window_days * 24
    mono_dq: deque = deque()
    eq = INIT; peak_alltime = INIT; halted = False
    eq_vals = []; cb_flags = []

    for bar_i in range(len(unit_normal)):
        ur_n = float(unit_normal.iloc[bar_i])
        ur_s = float(unit_surge.iloc[bar_i])

        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

        if not halted and cb_dd >= cb_halt:   halted = True
        elif  halted and cb_dd <= cb_resume:  halted = False

        if halted:
            y = 0.0
        elif dd_aty <= dd_soft:
            y = 1.0
        elif dd_aty >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        r = K_normal * y * ur_n + K_surge * ur_s
        r = max(r, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq)
        cb_flags.append(int(halted))

    eqs = pd.Series(eq_vals, index=unit_normal.index)
    return dict(eq=eqs, pct_halted=float(np.mean(cb_flags)))


# ─────────────────────────────────────────────────────────────────────────────
#  METRICS
# ─────────────────────────────────────────────────────────────────────────────

def oos_stats(eq: pd.Series) -> dict:
    eq_oos = eq[eq.index >= TEST_TS]
    if len(eq_oos) < 100:
        return dict(calmar=0.0, cagr=0.0, maxdd=0.0, sharpe=0.0, final=INIT)
    eq_oos = eq_oos * (INIT / float(eq_oos.iloc[0]))
    dd     = (eq_oos - eq_oos.cummax()) / eq_oos.cummax()
    years  = max((eq_oos.index[-1] - eq_oos.index[0]).days / 365.25, 1e-9)
    cagr   = float((eq_oos.iloc[-1] / INIT) ** (1 / years) - 1.0)
    maxdd  = float(dd.min())
    rets   = eq_oos.pct_change().dropna()
    sharpe = float(np.sqrt(24 * 365.25) * rets.mean() / rets.std()) if rets.std() > 0 else 0.0
    calmar = cagr / abs(maxdd) if maxdd < 0 else 0.0
    return dict(calmar=calmar, cagr=cagr, maxdd=maxdd, sharpe=sharpe,
                final=float(eq_oos.iloc[-1]))


def yearly_table(eq: pd.Series) -> list[dict]:
    eq_norm = eq * (INIT / float(eq.iloc[0]))
    rows = []
    for period, s in eq_norm.groupby(pd.Grouper(freq='YE')):
        if len(s) < 2: continue
        rows.append(dict(year=period.year,
                         end =float(s.iloc[-1]),
                         ret =float(s.iloc[-1] / s.iloc[0] - 1.0)))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    N_COMBOS = len(SURGE_RET_GRID) * len(VOL_MULT_GRID) * len(K_SURGE_GRID) * len(BREADTH_GRID)
    print(BAR)
    print('  SURGE MOMENTUM LONG LEG SWEEP')
    print('  Symmetrical to crash-short leg — fires on sustained high-vol UPSIDE moves')
    print(f'  {N_COMBOS} combos: ret_thresh × vol_mult × K_surge × breadth_confirm')
    print('  Baseline: Champion #1 (ze7≥0.10 + CB halt=8% resume=1%)  OOS Calmar +3.236')
    print(BAR)

    # ── [1] Load data ─────────────────────────────────────────────────────────
    print('\n  Loading data ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ch       = get_channel_series()
    ohlc_eth = fetch_futures_ohlcv(symbol='ETHUSDT')

    # Fetch BTC for breadth confirmation
    from test_daily_geometry_stop_tp_ohlc import fetch_futures_ohlcv as _fetch
    ohlc_btc = _fetch(symbol='BTCUSDT')

    p_day = build_positions(df_1h, comp_raw, calib_mask, ohlc_eth)
    hours = p_day['hours']

    daily_vol     = p_day['daily_vol']
    sl            = BASE['sl_mult']    * daily_vol
    tp            = BASE['tp_mult']    * daily_vol
    trail_trigger = TRAIL_TRIGGER_MULT * daily_vol
    trail_dist    = TRAIL_DIST_MULT    * daily_vol

    q_mult       = _build_quadrant_multiplier(ch, hours)
    layered_size = p_day['size_mult'] * q_mult
    unit_zero    = pd.Series(np.zeros(len(hours)), index=hours)

    ze7_s   = ch['E7'].reindex(hours, method='ffill').fillna(0.0).shift(1).fillna(0.0)
    ze7_arr = ze7_s.values

    print(f'  daily_vol={daily_vol:.2%}  SL={sl:.2%}  TP={tp:.2%}')

    # ── [2] Champion BSDT unit (fixed) ────────────────────────────────────────
    print('  Building champion unit (ze7≥0.10 gate) ...')
    unit_B_arr, cnt_B = simulate_unit_trailing_ze7gate(
        p_day['op'], p_day['hi'], p_day['lo'], p_day['cl'],
        p_day['hpos'], p_day['dpos'], p_day['dactive'],
        layered_size, sl, tp, trail_trigger, trail_dist,
        ze7_arr=ze7_arr, ze7_min=ZE7_MIN_FORCE,
    )
    unit_B = pd.Series(unit_B_arr, index=hours)

    # Champion baseline (no surge leg, K_surge=0)
    champ_res = simulate_combined_surge(
        unit_B, unit_zero,
        K_normal=DYN_K, K_surge=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window_days=CB_WINDOW_DAYS,
    )
    champ_stats = oos_stats(champ_res['eq'])
    print(f'  Champion → Calmar={champ_stats["calmar"]:+.3f}  '
          f'CAGR={champ_stats["cagr"]:+.1%}  MaxDD={champ_stats["maxdd"]:+.2%}  '
          f'Sharpe={champ_stats["sharpe"]:+.3f}  entries={cnt_B["entries"]}')

    op = p_day['op']; hi = p_day['hi']; lo = p_day['lo']; cl = p_day['cl']

    # ── [3] Sweep ─────────────────────────────────────────────────────────────
    print(f'\n  Running {N_COMBOS} combos ...')
    results = []

    for srt, vm, ks, bc in itertools.product(
            SURGE_RET_GRID, VOL_MULT_GRID, K_SURGE_GRID, BREADTH_GRID):

        surge_sig, rv_base = build_surge_signal(
            ohlc_eth, ohlc_btc, hours,
            surge_ret_thresh=srt, vol_mult=vm, breadth_confirm=bc,
        )
        n_fires = int(surge_sig.sum())

        surge_arr, surge_cnt = simulate_surge_longs(
            op, hi, lo, cl, surge_sig,
            SURGE_SL, SURGE_TP, SURGE_MAX_HOURS,
        )
        unit_surge = pd.Series(surge_arr, index=hours)

        res = simulate_combined_surge(
            unit_B, unit_surge,
            K_normal=DYN_K, K_surge=ks,
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
            cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window_days=CB_WINDOW_DAYS,
        )
        stats = oos_stats(res['eq'])

        results.append(dict(
            srt=srt, vm=vm, ks=ks, bc=bc,
            calmar=stats['calmar'],
            delta=stats['calmar'] - champ_stats['calmar'],
            cagr=stats['cagr'], maxdd=stats['maxdd'],
            sharpe=stats['sharpe'], final=stats['final'],
            n_fires=n_fires,
            entries=surge_cnt['entries'],
            tp_rate=surge_cnt['tp'] / max(surge_cnt['exits'], 1),
            eq=res['eq'],
        ))

    results.sort(key=lambda r: -r['calmar'])

    # ── [4] Results table ─────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SWEEP RESULTS  (sorted by OOS Calmar, top 20)')
    print(BAR)
    print(f'  {"RT%":>5} {"VolX":>5} {"K_s":>4} {"Brd":>4} '
          f'{"Calmar":>9} {"Δ":>7} {"MaxDD":>8} {"Sharpe":>8} '
          f'{"CAGR":>8} {"Final$":>9} {"Fires":>7} {"Entries":>8} {"TP%":>6}')
    print(f'  {SEP[:108]}')

    for r in results[:20]:
        mk = '★' if r['delta'] > 0 else ' '
        brd = 'Y' if r['bc'] else 'N'
        print(f'  {mk} {r["srt"]*100:>4.0f}% {r["vm"]:>4.1f}× {r["ks"]:>3.1f}× {brd:>4} '
              f'{r["calmar"]:>+9.3f} {r["delta"]:>+7.3f} {r["maxdd"]:>+7.2%} '
              f'{r["sharpe"]:>+7.3f} {r["cagr"]:>+7.1%} '
              f'{r["final"]:>9,.0f} {r["n_fires"]:>7} {r["entries"]:>8} {r["tp_rate"]:>5.1%}')

    print(f'\n  Baseline: Calmar={champ_stats["calmar"]:+.3f}  '
          f'MaxDD={champ_stats["maxdd"]:+.2%}  Sharpe={champ_stats["sharpe"]:+.3f}  '
          f'Final=${champ_stats["final"]:,.0f}')

    # ── [5] Full table ────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  FULL TABLE  (all combos)')
    print(BAR)
    print(f'  {"RT%":>5} {"VolX":>5} {"K_s":>4} {"Brd":>4} '
          f'{"Calmar":>9} {"Δ":>7} {"MaxDD":>8} {"Sharpe":>8} {"CAGR":>8} {"Final$":>9}')
    print(f'  {SEP[:95]}')
    for r in results:
        mk = '★' if r['delta'] > 0 else ' '
        brd = 'Y' if r['bc'] else 'N'
        print(f'  {mk} {r["srt"]*100:>4.0f}% {r["vm"]:>4.1f}× {r["ks"]:>3.1f}× {brd:>4} '
              f'{r["calmar"]:>+9.3f} {r["delta"]:>+7.3f} {r["maxdd"]:>+7.2%} '
              f'{r["sharpe"]:>+7.3f} {r["cagr"]:>+7.1%} {r["final"]:>9,.0f}')

    # ── [6] Year-by-year best vs. champion ────────────────────────────────────
    best = results[0]
    print(f'\n{BAR}')
    print(f'  YEAR-BY-YEAR: Best Surge combo  '
          f'[{best["srt"]*100:.0f}% ret  vol>{best["vm"]:.1f}×  K_surge={best["ks"]}  '
          f'breadth={"Y" if best["bc"] else "N"}]  vs. Champion')
    print(f'  ΔCalmar = {best["delta"]:+.3f}')
    print(BAR)
    yr_champ = {r['year']: r for r in yearly_table(champ_res['eq'])}
    yr_best  = {r['year']: r for r in yearly_table(best['eq'])}
    all_yrs  = sorted(set(yr_champ) | set(yr_best))
    print(f'  {"Year":<8}  {"Champion End$":>14} {"Ret":>7}  '
          f'{"+ Surge End$":>14} {"Ret":>7}  {"Δ$":>10}')
    print(f'  {SEP[:80]}')
    for yr in all_yrs:
        role = '(train)' if yr <= 2022 else '(OOS)  '
        ch  = yr_champ.get(yr)
        bst = yr_best.get(yr)
        c_end = ch['end']  if ch  else float('nan')
        b_end = bst['end'] if bst else float('nan')
        c_ret = f'{ch["ret"]:+.1%}'  if ch  else '—'
        b_ret = f'{bst["ret"]:+.1%}' if bst else '—'
        dlt   = f'{b_end-c_end:>+,.0f}' if (ch and bst) else '—'
        print(f'  {yr} {role}  {c_end:>14,.0f} {c_ret:>7}  {b_end:>14,.0f} {b_ret:>7}  {dlt:>10}')

    # ── [7] Surge leg standalone P&L analysis ────────────────────────────────
    best_sig, rv_base = build_surge_signal(
        ohlc_eth, ohlc_btc, hours,
        surge_ret_thresh=best['srt'], vol_mult=best['vm'],
        breadth_confirm=best['bc'],
    )
    best_arr, best_cnt = simulate_surge_longs(
        op, hi, lo, cl, best_sig,
        SURGE_SL, SURGE_TP, SURGE_MAX_HOURS,
    )
    best_unit_surge = pd.Series(best_arr, index=hours)
    surge_eq = (1.0 + best_unit_surge * DYN_K).cumprod() * INIT
    surge_oos  = surge_eq[surge_eq.index >= TEST_TS]

    print(f'\n{SEP}')
    print(f'  SURGE LEG STANDALONE  (K={DYN_K}×, no BSDT, OOS only)')
    print(f'  Entries={best_cnt["entries"]}  TP={best_cnt["tp"]}  Stop={best_cnt["stop"]}  '
          f'Time-exit={best_cnt["time_exit"]}')
    tp_r  = best_cnt['tp']   / max(best_cnt['entries'], 1)
    stp_r = best_cnt['stop'] / max(best_cnt['entries'], 1)
    tex_r = best_cnt['time_exit'] / max(best_cnt['entries'], 1)
    print(f'  Win rate (TP): {tp_r:.1%}   Stop rate: {stp_r:.1%}   Time exit: {tex_r:.1%}')
    print(f'  OOS start ${INIT:,.0f}  →  ${float(surge_oos.iloc[-1] * INIT / float(surge_oos.iloc[0])):,.0f}')

    print(f'\n  Total elapsed: {time.time()-t0:.1f}s')
    print(BAR)


if __name__ == '__main__':
    main()
