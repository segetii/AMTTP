"""
simulate_cb_resume_sweep.py — CB_HALT × CB_RESUME 2-D Sweep
=============================================================
The missed-opportunity analysis showed 86% of OOS time is CB-halted.
The 2024 bull recovery generated +382% aligned return while halted.
Top CB-missed trades in 2025: SHORT +19.4%, +16.7%, +14.6% during crashes.

The unit simulation (trade-level) is CB-INDEPENDENT — CB params only affect
simulate_combined(). So we run simulate_unit_trailing_ze7gate ONCE and then
sweep (CB_HALT × CB_RESUME) cheaply through simulate_combined.

GRID:
  CB_HALT   : [0.06, 0.07, 0.08, 0.09, 0.10, 0.12]
  CB_RESUME : [0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07]
  CB_WINDOW : 180 days (fixed — champion value)
  Constraint: CB_RESUME < CB_HALT
  ZE7 gate  : 0.10 (champion gate — fixed)

BASELINE: CB_HALT=0.08, CB_RESUME=0.03  →  OOS Calmar=+7.974, MaxDD=−16.80%

Metrics reported for each combo (OOS only):
  Calmar, Return, MaxDD, Sharpe, %Halted, CB trips
"""
from __future__ import annotations
import time
from pathlib import Path
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START
from test_daily_geometry_stop_tp_ohlc   import (
    build_daily_geometry, fetch_futures_ohlcv, get_channel_series,
)
from test_psi_adaptive_y                import BASE
from simulate_master_strategy           import (
    equity_metrics, build_positions,
    simulate_unit_trailing,
    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
    simulate_combined,
)
from simulate_v63_quadrant              import (
    _build_quadrant_multiplier,
    CB_WINDOW_DAYS,
    TRAIL_TRIGGER_MULT, TRAIL_DIST_MULT,
    ZE7_MIN_FORCE,
    simulate_unit_trailing_ze7gate,
)

BAR     = '=' * 110
SEP     = '-' * 110
TEST_TS = pd.Timestamp(TEST_START)

# ── Sweep grid ─────────────────────────────────────────────────────────────────
CB_HALTS   = [0.06, 0.07, 0.08, 0.09, 0.10, 0.12]
CB_RESUMES = [0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07]
# champion baseline
BASELINE_HALT   = 0.08
BASELINE_RESUME = 0.03


def main():
    t0 = time.time()
    print(BAR)
    print('  CB_HALT × CB_RESUME SWEEP  (fixed: ZE7=0.10, window=180d)')
    print(f'  Baseline: halt={BASELINE_HALT:.0%}  resume={BASELINE_RESUME:.0%}'
          f'  →  OOS Calmar=+7.974, MaxDD=−16.80%')
    print(BAR)

    # ── [1] Load data once ─────────────────────────────────────────────────────
    print('\n  Loading data ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ch       = get_channel_series()
    ohlc_all = fetch_futures_ohlcv()

    print('  Building positions ...')
    p_day = build_positions(df_1h, comp_raw, calib_mask, ohlc_all)
    daily_vol     = p_day['daily_vol']
    sl            = BASE['sl_mult'] * daily_vol
    tp            = BASE['tp_mult'] * daily_vol
    trail_trigger = TRAIL_TRIGGER_MULT * daily_vol
    trail_dist    = TRAIL_DIST_MULT    * daily_vol
    hours         = p_day['hours']
    q_mult        = _build_quadrant_multiplier(ch, hours)
    layered_size  = p_day['size_mult'] * q_mult

    # ── [2] Run unit sim once ──────────────────────────────────────────────────
    print('  Running unit simulation (once) ...')
    ze7_s = ch['E7'].reindex(hours, method='ffill').fillna(0.0).shift(1).fillna(0.0)
    ze7_arr = ze7_s.values

    unit_arr, cnt = simulate_unit_trailing_ze7gate(
        p_day['op'], p_day['hi'], p_day['lo'], p_day['cl'],
        p_day['hpos'], p_day['dpos'], p_day['dactive'],
        layered_size, sl, tp, trail_trigger, trail_dist,
        ze7_arr=ze7_arr, ze7_min=ZE7_MIN_FORCE,
    )
    unit_s = pd.Series(unit_arr, index=hours)
    unit_zero = pd.Series(np.zeros(len(hours)), index=hours)
    print(f'  Entries={cnt["entries"]}  vetoed_force={cnt["vetoed_force"]} ({cnt["vetoed_force"]/(cnt["entries"]+cnt["vetoed_force"]):.1%})')

    # ── [3] Sweep CB params ────────────────────────────────────────────────────
    combos = [
        (h, r) for h in CB_HALTS for r in CB_RESUMES if r < h
    ]
    print(f'\n  Sweeping {len(combos)} combos ...')

    rows = []
    for halt, resume in combos:
        res = simulate_combined(
            unit_s, unit_zero,
            K_normal=DYN_K, K_crash=0.0,
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
            cb_halt=halt, cb_resume=resume,
            cb_window_days=CB_WINDOW_DAYS, use_cb=True,
        )
        eq = res['eq']
        m  = equity_metrics(eq[eq.index >= TEST_TS], label='oos')
        rows.append(dict(
            halt       = halt,
            resume     = resume,
            spread     = halt - resume,
            calmar     = m['calmar'],
            ret        = m['return_pct'],
            maxdd      = m['maxdd'],
            sharpe     = m['sharpe'],
            pct_halted = res['pct_halted'],
            n_trips    = res['n_trips'],
            label      = f'h{halt:.0%}_r{resume:.1%}'.replace('.0%','%'),
        ))

    df = pd.DataFrame(rows)
    df_sorted = df.sort_values('calmar', ascending=False)

    # ── [4] Full sorted table ──────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  FULL RESULTS — sorted by OOS Calmar')
    print(BAR)
    print(f'  {"Label":<18}  {"Calmar":>8}  {"Return":>10}  {"MaxDD":>8}  '
          f'{"Sharpe":>8}  {"Halted%":>9}  {"Trips":>6}  {"Spread":>7}')
    print(f'  {"─"*90}')
    baseline_row = None
    for _, row in df_sorted.iterrows():
        is_base = (abs(row['halt'] - BASELINE_HALT) < 0.001 and
                   abs(row['resume'] - BASELINE_RESUME) < 0.001)
        marker = ' ★ BASELINE' if is_base else ''
        if is_base:
            baseline_row = row
        print(f'  {row["label"]:<18}  {row["calmar"]:>+8.3f}  '
              f'{row["ret"]:>+9.1%}  {row["maxdd"]:>+7.2%}  '
              f'{row["sharpe"]:>+8.3f}  {row["pct_halted"]:>8.1%}  '
              f'{int(row["n_trips"]):>6}  {row["spread"]:>6.1%}  {marker}')

    # ── [5] Pivot: Calmar by halt × resume ────────────────────────────────────
    print(f'\n{BAR}')
    print('  PIVOT — OOS Calmar  (rows=CB_HALT, cols=CB_RESUME)')
    print(BAR)
    pivot = df.pivot(index='halt', columns='resume', values='calmar')
    col_lbls = [f'{c:.1%}' for c in pivot.columns]
    row_lbls = [f'{r:.0%}' for r in pivot.index]
    header = f'  {"halt":>6}  ' + '  '.join(f'{c:>8}' for c in col_lbls)
    print(header)
    print(f'  {"─"*len(header)}')
    for halt, row_s in pivot.iterrows():
        vals = []
        for resume, v in row_s.items():
            if resume >= halt:
                vals.append('      --')
            else:
                mark = '★' if (abs(halt - BASELINE_HALT) < 0.001 and
                                abs(resume - BASELINE_RESUME) < 0.001) else ' '
                vals.append(f'{v:>+7.3f}{mark}')
        print(f'  {halt:.0%}     ' + '  '.join(vals))

    # ── [6] Pivot: MaxDD ──────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  PIVOT — OOS MaxDD  (rows=CB_HALT, cols=CB_RESUME)')
    print(BAR)
    pivot_dd = df.pivot(index='halt', columns='resume', values='maxdd')
    print(header)
    print(f'  {"─"*len(header)}')
    for halt, row_s in pivot_dd.iterrows():
        vals = []
        for resume, v in row_s.items():
            if resume >= halt:
                vals.append('      --')
            else:
                mark = '★' if (abs(halt - BASELINE_HALT) < 0.001 and
                                abs(resume - BASELINE_RESUME) < 0.001) else ' '
                vals.append(f'{v:>+7.2%}{mark}')
        print(f'  {halt:.0%}     ' + '  '.join(vals))

    # ── [7] Pivot: %Halted ─────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  PIVOT — % OOS time halted  (rows=CB_HALT, cols=CB_RESUME)')
    print(BAR)
    pivot_h = df.pivot(index='halt', columns='resume', values='pct_halted')
    print(header)
    print(f'  {"─"*len(header)}')
    for halt, row_s in pivot_h.iterrows():
        vals = []
        for resume, v in row_s.items():
            if resume >= halt:
                vals.append('      --')
            else:
                mark = '★' if (abs(halt - BASELINE_HALT) < 0.001 and
                                abs(resume - BASELINE_RESUME) < 0.001) else ' '
                vals.append(f'{v:>+7.1%}{mark}')
        print(f'  {halt:.0%}     ' + '  '.join(vals))

    # ── [8] Top-5 winners vs baseline ─────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TOP 5 COMBOS vs BASELINE')
    print(BAR)
    if baseline_row is not None:
        print(f'  Baseline  halt={BASELINE_HALT:.0%}  resume={BASELINE_RESUME:.0%}'
              f'  Calmar={baseline_row["calmar"]:+.3f}  '
              f'MaxDD={baseline_row["maxdd"]:+.2%}  '
              f'Sharpe={baseline_row["sharpe"]:+.3f}  '
              f'Halted={baseline_row["pct_halted"]:.1%}')
    print()
    for i, (_, row) in enumerate(df_sorted.head(5).iterrows()):
        delta_c = row['calmar'] - (baseline_row['calmar'] if baseline_row is not None else 0)
        delta_d = row['maxdd']  - (baseline_row['maxdd']  if baseline_row is not None else 0)
        print(f'  #{i+1}  {row["label"]:<16}  '
              f'Calmar={row["calmar"]:+.3f} ({delta_c:+.3f})  '
              f'MaxDD={row["maxdd"]:+.2%} ({delta_d:+.2%})  '
              f'Sharpe={row["sharpe"]:+.3f}  '
              f'Return={row["ret"]:+.1%}  '
              f'Halted={row["pct_halted"]:.1%}  '
              f'spread={row["halt"]-row["resume"]:.1%}')

    # ── [9] Yearly breakdown for top combo ────────────────────────────────────
    top_row = df_sorted.iloc[0]
    print(f'\n{BAR}')
    print(f'  YEARLY BREAKDOWN — top combo: halt={top_row["halt"]:.0%}  '
          f'resume={top_row["resume"]:.1%}')
    print(BAR)
    from simulate_master_strategy import period_table, print_yearly, drawdown_periods, print_dd
    res_top = simulate_combined(
        unit_s, unit_zero,
        K_normal=DYN_K, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=float(top_row['halt']), cb_resume=float(top_row['resume']),
        cb_window_days=CB_WINDOW_DAYS, use_cb=True,
    )
    eq_top = res_top['eq']
    print_yearly(period_table(eq_top, 'Y'))
    print('  Drawdowns:')
    print_dd(drawdown_periods(eq_top))

    # Also show baseline yearly if top is different
    if not (abs(top_row['halt'] - BASELINE_HALT) < 0.001 and
            abs(top_row['resume'] - BASELINE_RESUME) < 0.001):
        print(f'\n  YEARLY BREAKDOWN — baseline: halt={BASELINE_HALT:.0%}  '
              f'resume={BASELINE_RESUME:.0%}')
        res_base = simulate_combined(
            unit_s, unit_zero,
            K_normal=DYN_K, K_crash=0.0,
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
            cb_halt=BASELINE_HALT, cb_resume=BASELINE_RESUME,
            cb_window_days=CB_WINDOW_DAYS, use_cb=True,
        )
        eq_base = res_base['eq']
        print_yearly(period_table(eq_base, 'Y'))
        print('  Drawdowns:')
        print_dd(drawdown_periods(eq_base))

    print(f'\n  Total elapsed: {time.time()-t0:.1f}s')


if __name__ == '__main__':
    main()
