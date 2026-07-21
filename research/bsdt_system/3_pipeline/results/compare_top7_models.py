"""
compare_top7_models.py — Year-on-Year $1,000 P&L for Top 7 Configurations
===========================================================================
Ranks all 7 champion configs side-by-side, $1,000 starting capital (Jan 2021),
zero-cost model baseline (RT_COST=2bps already in unit returns).

TOP 7 CONFIGS (ranked by OOS Calmar):
  #1  ze7_gate + CB_RESUME=1%          halt=8% resume=1%  ZE7≥0.10
  #2  ze7_gate + CB_RESUME=3%          halt=8% resume=3%  ZE7≥0.10
  #3  layered_daily_no_crash           no ze7 gate         (original champion)
  #4  CB_HALT=7% + ze7_gate            halt=7% resume=0.5% ZE7≥0.10
  #5  eps=0.10 + dir_align             ZE7≥0.10 AND sign(zE7)==direction
  #6  dynamic B_k0.15_W168h            rolling std×0.15, window=168h
  #7  CB_HALT=12% + ze7_gate           halt=12% resume=0.5% ZE7≥0.10
"""
from __future__ import annotations
import time
from collections import deque
from pathlib import Path
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from test_daily_geometry_stop_tp_ohlc   import (
    build_daily_geometry, fetch_futures_ohlcv, get_channel_series,
)
from test_psi_adaptive_y                import BASE
from simulate_master_strategy           import (
    build_positions, simulate_unit_trailing, simulate_combined,
    equity_metrics, period_table,
    RT_COST, FUND_HOURLY, HOURS_PER_DAY,
    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
)
from simulate_v63_quadrant              import (
    _build_quadrant_multiplier,
    CB_WINDOW_DAYS, TRAIL_TRIGGER_MULT, TRAIL_DIST_MULT,
    ZE7_MIN_FORCE, simulate_unit_trailing_ze7gate,
)
from simulate_dynamic_ze7_sweep import build_std_thresh

INIT    = 1_000.0
BAR     = '=' * 120
SEP     = '-' * 120
TEST_TS = pd.Timestamp(TEST_START)
WARMUP_BARS = 24


# ── Inline dir_align unit sim (from simulate_signal_filter_sweep.py) ──────────
def simulate_unit_ze7_diralign(
    op, hi, lo, cl,
    hpos_arr, dpos_arr, dactive_arr,
    layered_size,
    sl, tp, trail_trigger, trail_dist,
    ze7_arr: np.ndarray,
    eps: float = 0.10,
):
    """ze7 gate + directional alignment gate."""
    n   = len(op)
    ret = np.zeros(n, dtype=float)
    pos = 0.0; size = 1.0; entry = 0.0
    stop_px = 0.0; take_px = 0.0
    trail_active = False; trail_ext = 0.0
    trailing_on  = (trail_trigger > 0 or trail_dist > 0)
    counts = dict(entries=0, exits=0, vetoed=0, active_hours=0)

    for i in range(n):
        hpos   = hpos_arr[i]; hactive = (hpos != 0)
        dpos_i = dpos_arr[i]; dact_i  = dactive_arr[i]
        scale  = layered_size[i]

        if hactive:
            if dact_i and hpos == dpos_i:   pass
            elif dact_i and hpos != dpos_i: hactive = False
            else:                           scale *= 0.5
        if hactive and scale <= 1e-12:       hactive = False

        if pos != 0:
            counts['active_hours'] += 1
            exit_ret = None; reason = None
            if pos > 0:
                if hi[i] >= take_px:
                    exit_ret = take_px / entry - 1; reason = 'tp'
                else:
                    if trailing_on:
                        trail_ext = max(trail_ext, hi[i])
                        if trail_ext / entry - 1.0 >= trail_trigger: trail_active = True
                        if trail_active:
                            ns = trail_ext * (1.0 - trail_dist)
                            if ns > stop_px: stop_px = ns
                    if lo[i] <= stop_px:
                        exit_ret = stop_px / entry - 1
                        reason   = 'trail_exit' if trail_active else 'stop'
            else:
                if lo[i] <= take_px:
                    exit_ret = entry / take_px - 1; reason = 'tp'
                else:
                    if trailing_on:
                        trail_ext = min(trail_ext, lo[i])
                        if entry / trail_ext - 1.0 >= trail_trigger: trail_active = True
                        if trail_active:
                            ns = trail_ext * (1.0 + trail_dist)
                            if ns < stop_px: stop_px = ns
                    if hi[i] >= stop_px:
                        exit_ret = entry / stop_px - 1
                        reason   = 'trail_exit' if trail_active else 'stop'

            if exit_ret is None and hactive and hpos == -pos:
                exit_ret = (op[i] / entry - 1) if pos > 0 else (entry / op[i] - 1)
                reason   = 'signal_exit'

            if exit_ret is not None:
                ret[i] += size * (exit_ret - RT_COST)
                counts['exits'] = counts.get('exits', 0) + 1
                pos = 0; size = 1; entry = 0; stop_px = 0; take_px = 0
                trail_active = False; trail_ext = 0.0
            else:
                ret[i] -= size * FUND_HOURLY

        if pos == 0 and hactive:
            ze7 = ze7_arr[i]
            # Rule 1: abs gate
            if eps > 0.0 and abs(ze7) < eps:
                counts['vetoed'] += 1; continue
            # Rule 2: directional alignment (zE7==0 is neutral, allowed)
            if ze7 != 0.0 and int(hpos) * ze7 < 0.0:
                counts['vetoed'] += 1; continue

            pos   = float(hpos); size = float(scale); entry = float(op[i])
            trail_active = False; trail_ext = float(op[i])
            if pos > 0:
                stop_px = entry * (1.0 - sl); take_px = entry * (1.0 + tp)
            else:
                stop_px = entry * (1.0 + sl); take_px = entry * (1.0 - tp)
            counts['entries'] += 1

    if pos != 0:
        gross = (cl[-1] / entry - 1) if pos > 0 else (entry / cl[-1] - 1)
        ret[-1] += size * (gross - RT_COST)
    return ret, counts


def run_config(unit_s: pd.Series, unit_zero: pd.Series,
               cb_halt: float, cb_resume: float) -> pd.Series:
    """Run simulate_combined and return equity series starting from INIT."""
    res = simulate_combined(
        unit_s, unit_zero,
        K_normal=DYN_K, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=cb_halt, cb_resume=cb_resume,
        cb_window_days=CB_WINDOW_DAYS, use_cb=True,
    )
    return res['eq']


def yearly_row(eq: pd.Series) -> list[dict]:
    rows = []
    groups = eq.groupby(pd.Grouper(freq='YE'))
    vals = list(groups)
    for k, (period, s) in enumerate(vals):
        if len(s) < 2: continue
        yr_start = float(s.iloc[0])
        yr_end   = float(s.iloc[-1])
        rows.append(dict(
            year    = period.year,
            start   = yr_start,
            end     = yr_end,
            pnl     = yr_end - yr_start,
            ret_pct = yr_end / yr_start - 1.0,
        ))
    return rows


def oos_summary(eq: pd.Series) -> dict:
    eq_oos  = eq[eq.index >= TEST_TS]
    eq_oos  = eq_oos * (INIT / float(eq_oos.iloc[0]))
    ret_s   = eq_oos.pct_change().dropna()
    dd_s    = (eq_oos - eq_oos.cummax()) / eq_oos.cummax()
    years   = max((eq_oos.index[-1] - eq_oos.index[0]).days / 365.25, 1e-9)
    cagr    = float((eq_oos.iloc[-1] / INIT) ** (1 / years) - 1.0)
    maxdd   = float(dd_s.min())
    calmar  = cagr / abs(maxdd) if maxdd < 0 else 0.0
    sharpe  = float(np.sqrt(24*365.25) * ret_s.mean() / ret_s.std()) if ret_s.std() > 0 else 0.0
    return dict(calmar=calmar, cagr=cagr, maxdd=maxdd, sharpe=sharpe,
                final=float(eq_oos.iloc[-1]), ret=float(eq_oos.iloc[-1] / INIT - 1.0))


def print_model_table(name: str, rank: int, eq: pd.Series, entries: int,
                      extra_note: str = '') -> None:
    # Normalise to $1,000 at first bar
    eq_norm = eq * (INIT / float(eq.iloc[0]))

    # OOS summary
    oos = oos_summary(eq)

    oos_years = max((eq.index[-1] - eq[eq.index >= TEST_TS].index[0]).days / 365.25, 1e-9)

    print(f'\n  ╔{"═"*96}╗')
    print(f'  ║  #{rank}  {name:<90}║')
    print(f'  ║  {extra_note:<94}║')
    print(f'  ║  OOS Calmar={oos["calmar"]:+.3f}  CAGR={oos["cagr"]:+.1%}  MaxDD={oos["maxdd"]:+.2%}  '
          f'Sharpe={oos["sharpe"]:+.3f}  Entries={entries:<6}   ║')
    print(f'  ╠{"═"*20}╦{"═"*14}╦{"═"*14}╦{"═"*14}╦{"═"*14}╦{"═"*14}╣')
    print(f'  ║{"Year":^20}║{"Start $":^14}║{"End $":^14}║{"P&L $":^14}║{"P&L %":^14}║{"Role":^14}║')
    print(f'  ╠{"═"*20}╬{"═"*14}╬{"═"*14}╬{"═"*14}╬{"═"*14}╬{"═"*14}╣')

    rows = yearly_row(eq_norm)
    for r in rows:
        role = '(train)' if r['year'] <= 2022 else '(OOS)'
        sign = '+' if r['pnl'] >= 0 else ''
        print(f'  ║  {r["year"]:<18}║  {r["start"]:>10,.0f}  ║  {r["end"]:>10,.0f}  ║'
              f'  {sign}{r["pnl"]:>10,.0f}  ║  {r["ret_pct"]:>+9.1%}  ║  {role:<12}║')

    print(f'  ╠{"═"*20}╬{"═"*14}╬{"═"*14}╬{"═"*14}╬{"═"*14}╬{"═"*14}╣')
    final = float(eq_norm.iloc[-1])
    total_pnl = final - INIT
    total_ret  = final / INIT - 1.0
    print(f'  ║  {"TOTAL (2021→now)":<18}║  {"$1,000":^12}  ║  {final:>10,.0f}  ║'
          f'  {total_pnl:>+10,.0f}  ║  {total_ret:>+9.1%}  ║  {"":^12}║')
    print(f'  ╚{"═"*20}╩{"═"*14}╩{"═"*14}╩{"═"*14}╩{"═"*14}╩{"═"*14}╝')


def main():
    t0 = time.time()
    print(BAR)
    print('  TOP 7 MODELS — $1,000 Year-on-Year P&L (zero-cost model baseline)')
    print('  Starting capital: $1,000 — January 2021')
    print('  OOS period: January 2023 → April 2026')
    print(BAR)

    # ── [1] Load data once ─────────────────────────────────────────────────────
    print('\n  Loading data ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ch       = get_channel_series()
    ohlc_all = fetch_futures_ohlcv()

    p_day = build_positions(df_1h, comp_raw, calib_mask, ohlc_all)
    daily_vol     = p_day['daily_vol']
    sl            = BASE['sl_mult'] * daily_vol
    tp            = BASE['tp_mult'] * daily_vol
    trail_trigger = TRAIL_TRIGGER_MULT * daily_vol
    trail_dist    = TRAIL_DIST_MULT    * daily_vol
    hours         = p_day['hours']
    q_mult        = _build_quadrant_multiplier(ch, hours)
    layered_size  = p_day['size_mult'] * q_mult
    unit_zero     = pd.Series(np.zeros(len(hours)), index=hours)

    ze7_s   = ch['E7'].reindex(hours, method='ffill').fillna(0.0).shift(1).fillna(0.0)
    ze7_arr = ze7_s.values

    print(f'  daily_vol={daily_vol:.2%}  SL={sl:.2%}  TP={tp:.2%}')

    # ── [2] Unit sims ─────────────────────────────────────────────────────────
    print('  Running unit simulations ...')

    # Unit A: no ze7 gate (config #3)
    unit_A_arr, cnt_A = simulate_unit_trailing(
        p_day['op'], p_day['hi'], p_day['lo'], p_day['cl'],
        p_day['hpos'], p_day['dpos'], p_day['dactive'],
        layered_size, sl, tp, trail_trigger, trail_dist,
    )
    unit_A = pd.Series(unit_A_arr, index=hours)

    # Unit B: ze7 gate 0.10 (configs #1, #2, #4, #7)
    unit_B_arr, cnt_B = simulate_unit_trailing_ze7gate(
        p_day['op'], p_day['hi'], p_day['lo'], p_day['cl'],
        p_day['hpos'], p_day['dpos'], p_day['dactive'],
        layered_size, sl, tp, trail_trigger, trail_dist,
        ze7_arr=ze7_arr, ze7_min=ZE7_MIN_FORCE,
    )
    unit_B = pd.Series(unit_B_arr, index=hours)

    # Unit C: ze7 gate + dir_align (config #5)
    unit_C_arr, cnt_C = simulate_unit_ze7_diralign(
        p_day['op'], p_day['hi'], p_day['lo'], p_day['cl'],
        p_day['hpos'], p_day['dpos'], p_day['dactive'],
        layered_size, sl, tp, trail_trigger, trail_dist,
        ze7_arr=ze7_arr, eps=ZE7_MIN_FORCE,
    )
    unit_C = pd.Series(unit_C_arr, index=hours)

    # Unit D: dynamic B_k=0.15, W=168h (config #6)
    dyn_thresh = build_std_thresh(ze7_s, window=168, k=0.15, fallback=ZE7_MIN_FORCE)
    unit_D_arr, cnt_D = simulate_unit_trailing_ze7gate(
        p_day['op'], p_day['hi'], p_day['lo'], p_day['cl'],
        p_day['hpos'], p_day['dpos'], p_day['dactive'],
        layered_size, sl, tp, trail_trigger, trail_dist,
        ze7_arr=ze7_arr, ze7_min=dyn_thresh,
    )
    unit_D = pd.Series(unit_D_arr, index=hours)

    print(f'  Unit sims done:')
    print(f'    A (no gate):    entries={cnt_A["entries"]}')
    print(f'    B (ze7≥0.10):   entries={cnt_B["entries"]}  vetoed={cnt_B["vetoed_force"]}')
    print(f'    C (ze7+align):  entries={cnt_C["entries"]}  vetoed={cnt_C["vetoed"]}')
    print(f'    D (dyn k0.15):  entries={cnt_D["entries"]}  vetoed={cnt_D["vetoed_force"]}')

    # ── [3] Apply CB params and build equity curves ───────────────────────────
    print('  Applying CB params ...')

    configs = [
        dict(rank=1, name='ze7≥0.10 gate  +  CB halt=8% resume=1%',
             unit=unit_B, halt=0.08, resume=0.01,
             entries=cnt_B['entries'],
             note='CURRENT CHAMPION  (CB_RESUME tightened from sweep)'),
        dict(rank=2, name='ze7≥0.10 gate  +  CB halt=8% resume=3%',
             unit=unit_B, halt=0.08, resume=0.03,
             entries=cnt_B['entries'],
             note='Previous champion before CB_RESUME sweep'),
        dict(rank=3, name='layered_daily_no_crash  (original, no ze7 gate)',
             unit=unit_A, halt=0.08, resume=0.01,
             entries=cnt_A['entries'],
             note='First champion — no signal gate applied'),
        dict(rank=4, name='ze7≥0.10  +  CB halt=7% resume=0.5%',
             unit=unit_B, halt=0.07, resume=0.005,
             entries=cnt_B['entries'],
             note='Tighter halt — more CB trips, lower Calmar'),
        dict(rank=5, name='ze7≥0.10 + dir_align  +  CB halt=8% resume=1%',
             unit=unit_C, halt=0.08, resume=0.01,
             entries=cnt_C['entries'],
             note='Direction alignment gate — highest Sharpe (≈+1.06)'),
        dict(rank=6, name='dynamic ze7 B_k0.15_W168h  +  CB halt=8% resume=1%',
             unit=unit_D, halt=0.08, resume=0.01,
             entries=cnt_D['entries'],
             note='Rolling std×0.15 adaptive threshold — best dynamic method'),
        dict(rank=7, name='ze7≥0.10  +  CB halt=12% resume=0.5%',
             unit=unit_B, halt=0.12, resume=0.005,
             entries=cnt_B['entries'],
             note='Wider halt window — more exposure but deeper MaxDD'),
    ]

    equities = []
    for cfg in configs:
        eq = run_config(cfg['unit'], unit_zero, cfg['halt'], cfg['resume'])
        equities.append(eq)

    # ── [4] Print all tables ───────────────────────────────────────────────────
    for cfg, eq in zip(configs, equities):
        print_model_table(cfg['name'], cfg['rank'], eq,
                          cfg['entries'], cfg['note'])

    # ── [5] Summary comparison ─────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SIDE-BY-SIDE SUMMARY  ($1,000 starting capital — Full history 2021→2026)')
    print(BAR)
    print(f'  {"#":<3}  {"Config":<44}  {"Final $":>10}  {"Total %":>9}  '
          f'{"OOS Calmar":>10}  {"OOS MaxDD":>10}  {"OOS Sharpe":>10}')
    print(f'  {"─"*110}')

    for cfg, eq in zip(configs, equities):
        eq_norm = eq * (INIT / float(eq.iloc[0]))
        final   = float(eq_norm.iloc[-1])
        total   = final / INIT - 1.0
        oos     = oos_summary(eq)
        short_name = cfg['name'][:44]
        print(f'  {cfg["rank"]:<3}  {short_name:<44}  '
              f'{final:>10,.0f}  {total:>+8.1%}  '
              f'{oos["calmar"]:>+10.3f}  {oos["maxdd"]:>+9.2%}  {oos["sharpe"]:>+10.3f}')

    # ── [6] Year-by-year side-by-side grid ────────────────────────────────────
    print(f'\n{BAR}')
    print('  YEAR-BY-YEAR END VALUE  ($1,000 start, each config independently)')
    print(BAR)
    year_data = {}
    all_years = set()
    for cfg, eq in zip(configs, equities):
        eq_norm = eq * (INIT / float(eq.iloc[0]))
        rows = yearly_row(eq_norm)
        year_data[cfg['rank']] = {r['year']: r for r in rows}
        all_years.update(r['year'] for r in rows)

    years_sorted = sorted(all_years)
    header = f'  {"Year":<8}' + ''.join(f'  {"#"+str(c["rank"]):>12}' for c in configs)
    print(header)
    print(f'  {"─"*100}')
    for yr in years_sorted:
        role = '(train)' if yr <= 2022 else '(OOS)  '
        row = f'  {yr} {role}'
        for cfg in configs:
            rd = year_data[cfg['rank']].get(yr)
            if rd:
                row += f'  {rd["end"]:>12,.0f}'
            else:
                row += f'  {"—":>12}'
        print(row)

    print(f'\n  Starting capital: $1,000 each row begins from their prior year end')
    print(f'  Total elapsed: {time.time()-t0:.1f}s')


if __name__ == '__main__':
    main()
