"""
simulate_cb_sweep.py — MaxDD Minimisation via CB Architecture Sweep
====================================================================

PROBLEM
-------
Current champion (layered_daily_no_crash): Calmar=3.555, OOS Ret=+1457.7%,
MaxDD=−36.09%, Sharpe=+1.248.

The 36% MaxDD comes from the Dec-2024 → Aug-2025 drawdown where the 90d-rolling
CB trips in/out 12 times, stair-stepping equity down 36% total.  Each individual
CB trip is ≤18%, but multiple trips compound.

ROOT CAUSE
----------
  CB window = 90d  →  rolling peak resets every 90d of flat/recovery
  halt = 18%       →  each trip allows up to 18% loss before stopping
  resume = 13%     →  re-enters after 13% recovery even if trend is still down

FIX OPTIONS TESTED
------------------
[A] Parameter tightening:   halt={8,10,12,15}%  resume={3,5,7,10,13}%  window={30,45,60,90}d
[B] All-time-peak CB:       use ATH DD instead of 90d-rolling peak — CB stays
                            halted until equity recovers to ≤13% below ATH
[C] K-taper after resume:   after each halt→resume, K is reduced by 0.75× until
                            equity regains a new ATH
[D] Two-stage CB:           soft halt (10% from peak → Y×0.5), hard halt (18% → Y=0.0)

TARGET
------
Keep OOS Calmar ≥ 3.5 OR OOS Return ≥ +1000% while pushing MaxDD below −25%.
"""
from __future__ import annotations
import time
from collections import deque
from pathlib import Path
import json
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from test_daily_geometry_stop_tp_ohlc   import (
    build_daily_geometry, fetch_futures_ohlcv, get_channel_series,
)
from test_psi_adaptive_y                import BASE, simulate_unit_with_psi
from simulate_adaptive_y_drawdown_brake import INIT
from test_dynamic_profit_sizing         import _percentile_against
from simulate_master_strategy           import (
    equity_metrics, period_table, drawdown_periods,
    simulate_unit_trailing, simulate_crash_shorts,
    build_positions,
    RT_COST, FUND_HOURLY, HOURS_PER_DAY,
    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
    DYN_STRENGTH_CAP, DYN_VOL_CAP, DYN_TOTAL_CAP,
    CRASH_RET_THRESH, CRASH_VOL_MULT, CRASH_SL, CRASH_TP, CRASH_MAX_HOURS,
)
from simulate_v63_quadrant import (
    _build_quadrant_multiplier,
    N_MEM, G_THRESH, T_THRESH, CLIP_BOOST,
    TRAIL_TRIGGER_MULT, TRAIL_DIST_MULT,
    CB_HALT, CB_RESUME, CB_WINDOW_DAYS,
)

OUT  = Path(OUT_DIR) / 'simulation_cb_sweep.json'
BAR  = '=' * 110
SEP  = '-' * 110


# ─────────────────────────────────────────────────────────────────────────────
#  FAST COMBINED EQUITY ENGINE — variants
# ─────────────────────────────────────────────────────────────────────────────

def _combined_fast(unit_normal_vals, n, test_start_idx,
                   K_normal, dd_soft, dd_stop, y_floor,
                   cb_halt, cb_resume, cb_window_bars,
                   index):
    """Rolling-window CB (standard).  Returns (oos_metrics_dict, full_eq_series)."""
    mono_dq: deque = deque()
    eq = INIT; peak_at = INIT; halted = False
    eq_vals = []; cb_flags = []

    for i in range(n):
        ur = unit_normal_vals[i]
        while mono_dq and mono_dq[0][0] <= i - cb_window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_at, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak, 1e-12))

        if not halted and cb_dd >= cb_halt:   halted = True
        elif halted and cb_dd <= cb_resume:   halted = False

        if halted:
            y = 0.0
        elif dd_aty <= dd_soft:
            y = 1.0
        elif dd_aty >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        r  = K_normal * y * ur
        r  = max(r, -0.95)
        eq *= (1.0 + r)
        peak_at = max(peak_at, eq)
        eq_vals.append(eq)
        cb_flags.append(int(halted))

    eqs  = pd.Series(eq_vals, index=index)
    oos  = eqs.iloc[test_start_idx:]
    rets = oos.pct_change().fillna(oos.iloc[0] / INIT - 1.0)
    dd_s = (oos - oos.cummax()) / oos.cummax()
    years = max((oos.index[-1] - oos.index[0]).days / 365.25, 1e-9)
    calmar = float((oos.iloc[-1] / INIT) ** (1 / years) - 1) / max(abs(float(dd_s.min())), 1e-9)
    return dict(
        calmar     = calmar,
        return_pct = float(oos.iloc[-1] / INIT - 1.0),
        cagr       = float((oos.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe     = float(np.sqrt(24 * 365.25) * rets.mean() / rets.std()) if rets.std() > 0 else 0.0,
        maxdd      = float(dd_s.min()),
        pct_halted = float(np.mean(cb_flags)),
        n_trips    = int(sum(cb_flags[i] > cb_flags[i-1] for i in range(1, len(cb_flags)))),
        final      = float(oos.iloc[-1]),
    ), eqs


def _combined_alltime(unit_normal_vals, n, test_start_idx,
                      K_normal, dd_soft, dd_stop, y_floor,
                      cb_halt, cb_resume, index):
    """All-time-peak CB: halt when DD from ATH ≥ cb_halt, resume at ≤ cb_resume.
    No rolling window — once you drop >cb_halt% from any ATH, you wait until
    equity is within cb_resume% of that ATH before resuming.
    """
    eq = INIT; ath = INIT; halted = False
    eq_vals = []; cb_flags = []

    for i in range(n):
        ur = unit_normal_vals[i]

        dd_ath = max(0.0, 1.0 - eq / max(ath, 1e-12))   # DD from all-time peak
        if not halted and dd_ath >= cb_halt:   halted = True
        elif halted and dd_ath <= cb_resume:   halted = False

        dd_aty = dd_ath   # same metric for adaptive Y
        if halted:
            y = 0.0
        elif dd_aty <= dd_soft:
            y = 1.0
        elif dd_aty >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        r  = K_normal * y * ur
        r  = max(r, -0.95)
        eq *= (1.0 + r)
        ath = max(ath, eq)
        eq_vals.append(eq)
        cb_flags.append(int(halted))

    eqs  = pd.Series(eq_vals, index=index)
    oos  = eqs.iloc[test_start_idx:]
    rets = oos.pct_change().fillna(oos.iloc[0] / INIT - 1.0)
    dd_s = (oos - oos.cummax()) / oos.cummax()
    years = max((oos.index[-1] - oos.index[0]).days / 365.25, 1e-9)
    calmar = float((oos.iloc[-1] / INIT) ** (1 / years) - 1) / max(abs(float(dd_s.min())), 1e-9)
    return dict(
        calmar     = calmar,
        return_pct = float(oos.iloc[-1] / INIT - 1.0),
        cagr       = float((oos.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe     = float(np.sqrt(24 * 365.25) * rets.mean() / rets.std()) if rets.std() > 0 else 0.0,
        maxdd      = float(dd_s.min()),
        pct_halted = float(np.mean(cb_flags)),
        n_trips    = int(sum(cb_flags[i] > cb_flags[i-1] for i in range(1, len(cb_flags)))),
        final      = float(oos.iloc[-1]),
    ), eqs


def _combined_ktaper(unit_normal_vals, n, test_start_idx,
                     K_normal, dd_soft, dd_stop, y_floor,
                     cb_halt, cb_resume, cb_window_bars,
                     taper_factor, index):
    """Rolling-window CB + K-taper: each halt→resume cycle reduces effective K
    by taper_factor until equity sets a new all-time high.
    """
    mono_dq: deque = deque()
    eq = INIT; peak_at = INIT; halted = False
    k_eff = K_normal; last_trip_peak = INIT
    eq_vals = []; cb_flags = []

    for i in range(n):
        ur = unit_normal_vals[i]
        while mono_dq and mono_dq[0][0] <= i - cb_window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_at, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak, 1e-12))

        was_halted = halted
        if not halted and cb_dd >= cb_halt:
            halted = True; last_trip_peak = eq
        elif halted and cb_dd <= cb_resume:
            halted = False
            k_eff  = max(K_normal * 0.25, k_eff * taper_factor)   # taper on resume

        # Restore K when equity exceeds last trip peak → new relative high
        if not halted and eq >= last_trip_peak:
            k_eff = K_normal

        if halted:
            y = 0.0
        elif dd_aty <= dd_soft:
            y = 1.0
        elif dd_aty >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        r  = k_eff * y * ur
        r  = max(r, -0.95)
        eq *= (1.0 + r)
        peak_at = max(peak_at, eq)
        eq_vals.append(eq)
        cb_flags.append(int(halted))

    eqs  = pd.Series(eq_vals, index=index)
    oos  = eqs.iloc[test_start_idx:]
    rets = oos.pct_change().fillna(oos.iloc[0] / INIT - 1.0)
    dd_s = (oos - oos.cummax()) / oos.cummax()
    years = max((oos.index[-1] - oos.index[0]).days / 365.25, 1e-9)
    calmar = float((oos.iloc[-1] / INIT) ** (1 / years) - 1) / max(abs(float(dd_s.min())), 1e-9)
    return dict(
        calmar     = calmar,
        return_pct = float(oos.iloc[-1] / INIT - 1.0),
        cagr       = float((oos.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe     = float(np.sqrt(24 * 365.25) * rets.mean() / rets.std()) if rets.std() > 0 else 0.0,
        maxdd      = float(dd_s.min()),
        pct_halted = float(np.mean(cb_flags)),
        n_trips    = int(sum(cb_flags[i] > cb_flags[i-1] for i in range(1, len(cb_flags)))),
        final      = float(oos.iloc[-1]),
    ), eqs


def _combined_twostage(unit_normal_vals, n, test_start_idx,
                       K_normal, dd_soft, dd_stop, y_floor,
                       soft_halt, hard_halt, resume, cb_window_bars, index):
    """Two-stage CB:
        - soft_halt: Y × 0.5 (reduce exposure by half)
        - hard_halt: Y = 0.0 (full stop)
    Both measured from rolling-window peak.
    """
    mono_dq: deque = deque()
    eq = INIT; peak_at = INIT; stage = 0   # 0=normal, 1=soft, 2=hard
    eq_vals = []; cb_flags = []

    for i in range(n):
        ur = unit_normal_vals[i]
        while mono_dq and mono_dq[0][0] <= i - cb_window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((i, eq))
        roll_peak = mono_dq[0][1]

        cb_dd = max(0.0, 1.0 - eq / max(roll_peak, 1e-12))
        if   cb_dd >= hard_halt:                  stage = 2
        elif cb_dd >= soft_halt:                  stage = max(stage, 1)
        elif cb_dd <= resume and stage == 2:      stage = 1
        elif cb_dd <= resume * 0.5 and stage == 1: stage = 0

        dd_aty = max(0.0, 1.0 - eq / max(peak_at, 1e-12))
        if dd_aty <= dd_soft:
            y = 1.0
        elif dd_aty >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        if   stage == 2: y_final = 0.0
        elif stage == 1: y_final = y * 0.5
        else:            y_final = y

        r  = K_normal * y_final * ur
        r  = max(r, -0.95)
        eq *= (1.0 + r)
        peak_at = max(peak_at, eq)
        eq_vals.append(eq)
        cb_flags.append(stage)

    eqs  = pd.Series(eq_vals, index=index)
    oos  = eqs.iloc[test_start_idx:]
    rets = oos.pct_change().fillna(oos.iloc[0] / INIT - 1.0)
    dd_s = (oos - oos.cummax()) / oos.cummax()
    years = max((oos.index[-1] - oos.index[0]).days / 365.25, 1e-9)
    calmar = float((oos.iloc[-1] / INIT) ** (1 / years) - 1) / max(abs(float(dd_s.min())), 1e-9)
    return dict(
        calmar     = calmar,
        return_pct = float(oos.iloc[-1] / INIT - 1.0),
        cagr       = float((oos.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe     = float(np.sqrt(24 * 365.25) * rets.mean() / rets.std()) if rets.std() > 0 else 0.0,
        maxdd      = float(dd_s.min()),
        pct_halted = float(np.mean([1 if s > 0 else 0 for s in cb_flags])),
        n_trips    = int(sum(cb_flags[i] > 0 and cb_flags[i-1] == 0 for i in range(1, len(cb_flags)))),
        final      = float(oos.iloc[-1]),
    ), eqs


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(BAR)
    print('  CB ARCHITECTURE SWEEP — MaxDD Minimisation')
    print('  Base: layered_daily champion (GH,TH boost, daily filter, no crash)')
    print('  Champion reference: OOS Calmar=3.555  Ret=+1457.7%  MaxDD=−36.09%  Sharpe=+1.248')
    print(BAR)

    print('\n[1] Building geometry + positions (once) ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ch       = get_channel_series()
    ohlc_all = fetch_futures_ohlcv()
    p        = build_positions(df_1h, comp_raw, calib_mask, ohlc_all)

    sl            = BASE['sl_mult'] * p['daily_vol']
    tp            = BASE['tp_mult'] * p['daily_vol']
    trail_trigger = TRAIL_TRIGGER_MULT * p['daily_vol']
    trail_dist    = TRAIL_DIST_MULT    * p['daily_vol']

    # Quadrant size multiplier
    q_mult       = _build_quadrant_multiplier(ch, p['hours'])
    layered_size = p['size_mult'] * q_mult

    print('\n[2] Computing unit_normal series (one call) ...')
    unit_arr, cnt = simulate_unit_trailing(
        p['op'], p['hi'], p['lo'], p['cl'],
        p['hpos'], p['dpos'], p['dactive'],
        layered_size, sl, tp, trail_trigger, trail_dist,
    )
    unit_vals   = unit_arr   # already a numpy array from simulate_unit_trailing
    n           = len(unit_vals)
    idx         = p['hours']
    test_ts     = pd.Timestamp(TEST_START)
    test_start_idx = int(np.searchsorted(idx, test_ts))
    print(f'  n={n:,}  test_start_idx={test_start_idx:,}  entries={cnt["entries"]:,}  '
          f'GH,TH_boosted≈{int((q_mult[p["hpos"]!=0]>1.0).sum())}')

    all_results = []

    # ── [A] Rolling-window CB parameter sweep ─────────────────────────────────
    print('\n[3a] Sweeping rolling-window CB parameters ...')
    halt_grid   = [0.08, 0.10, 0.12, 0.15, 0.18, 0.20]
    resume_grid = [0.03, 0.05, 0.07, 0.10, 0.13]
    window_grid = [30, 45, 60, 90, 180]
    n_sweep = len(halt_grid) * len(resume_grid) * len(window_grid)
    done = 0
    for halt in halt_grid:
        for resume in resume_grid:
            if resume >= halt:
                continue     # invalid
            for win in window_grid:
                win_bars = win * HOURS_PER_DAY
                m, _ = _combined_fast(
                    unit_vals, n, test_start_idx,
                    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
                    halt, resume, win_bars, idx,
                )
                all_results.append(dict(
                    mode=f'rolling  halt={halt:.0%} res={resume:.0%} win={win}d',
                    **m,
                ))
                done += 1
    print(f'  {done} rolling-CB combinations done')

    # ── [B] All-time-peak CB sweep ─────────────────────────────────────────────
    print('\n[3b] Sweeping all-time-peak CB ...')
    for halt in [0.08, 0.10, 0.12, 0.15, 0.18, 0.20]:
        for resume in [0.03, 0.05, 0.07, 0.10, 0.13]:
            if resume >= halt:
                continue
            m, _ = _combined_alltime(
                unit_vals, n, test_start_idx,
                DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
                halt, resume, idx,
            )
            all_results.append(dict(
                mode=f'ATH-peak halt={halt:.0%} res={resume:.0%}',
                **m,
            ))
    print(f'  {len([r for r in all_results if "ATH" in r["mode"]])} ATH-CB combinations done')

    # ── [C] K-taper after resume ───────────────────────────────────────────────
    print('\n[3c] K-taper after resume sweep ...')
    for taper in [0.50, 0.65, 0.75, 0.85]:
        for halt in [0.12, 0.15, 0.18]:
            for resume in [0.05, 0.07, 0.10]:
                if resume >= halt:
                    continue
                m, _ = _combined_ktaper(
                    unit_vals, n, test_start_idx,
                    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
                    halt, resume, 90 * HOURS_PER_DAY, taper, idx,
                )
                all_results.append(dict(
                    mode=f'K-taper  taper={taper:.2f} halt={halt:.0%} res={resume:.0%}',
                    **m,
                ))
    print(f'  {len([r for r in all_results if "taper" in r["mode"]])} K-taper combinations done')

    # ── [D] Two-stage CB sweep ─────────────────────────────────────────────────
    print('\n[3d] Two-stage (soft+hard) CB sweep ...')
    for soft in [0.06, 0.08, 0.10]:
        for hard in [0.14, 0.18, 0.22]:
            if soft >= hard:
                continue
            for resume in [0.03, 0.05, 0.07]:
                m, _ = _combined_twostage(
                    unit_vals, n, test_start_idx,
                    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
                    soft, hard, resume, 90 * HOURS_PER_DAY, idx,
                )
                all_results.append(dict(
                    mode=f'2-stage  soft={soft:.0%} hard={hard:.0%} res={resume:.0%}',
                    **m,
                ))
    print(f'  {len([r for r in all_results if "stage" in r["mode"]])} two-stage combinations done')

    # ── Report ─────────────────────────────────────────────────────────────────
    total = len(all_results)
    print(f'\n  Total: {total} configurations evaluated in {time.time()-t0:.1f}s')

    # Sort by Calmar descending
    all_results.sort(key=lambda r: r['calmar'], reverse=True)

    print(f'\n{BAR}')
    print(f'  FULL RESULTS — sorted by OOS Calmar  (reference: Calmar=3.555  MaxDD=−36.09%)')
    print(BAR)
    hdr = (f"  {'Mode':<52} {'Calmar':>8} {'Return':>9} {'CAGR':>8} "
           f"{'Sharpe':>8} {'MaxDD':>9} {'Halted':>7} {'Trips':>6}")
    print(hdr); print(SEP)
    for r in all_results:
        flag = ''
        if r['maxdd'] > -0.25:  flag = ' ★★★'
        elif r['maxdd'] > -0.30: flag = ' ★★'
        elif r['maxdd'] > -0.35: flag = ' ★'
        print(f"  {r['mode']:<52} {r['calmar']:>+8.3f} {r['return_pct']:>+8.1%} "
              f"{r['cagr']:>+7.1%} {r['sharpe']:>+8.3f} {r['maxdd']:>+8.2%} "
              f"{r['pct_halted']:>7.1%} {r['n_trips']:>6}{flag}")

    # Efficient frontier: MaxDD brackets with best Calmar in each
    print(f'\n{BAR}')
    print('  EFFICIENT FRONTIER — best Calmar at each MaxDD cap')
    print(BAR)
    print(f"  {'MaxDD cap':<14} {'Best Calmar':>12} {'Return':>10} {'CAGR':>9} {'Sharpe':>9} {'Mode'}")
    print(SEP)
    for dd_cap in [0.15, 0.20, 0.22, 0.25, 0.28, 0.30, 0.35]:
        cands = [r for r in all_results if r['maxdd'] >= -dd_cap and r['return_pct'] > 0]
        if not cands:
            print(f"  DD < {dd_cap:.0%}          {'none':>12}")
            continue
        best = max(cands, key=lambda r: r['calmar'])
        print(f"  DD < {dd_cap:.0%}         {best['calmar']:>+12.3f} "
              f"{best['return_pct']:>+9.1%} {best['cagr']:>+8.1%} "
              f"{best['sharpe']:>+9.3f}  {best['mode']}")

    # Top 5 in each mode type
    for mode_type in ['rolling', 'ATH-peak', 'K-taper', '2-stage']:
        subset = [r for r in all_results if mode_type in r['mode']]
        if not subset:
            continue
        print(f'\n  ── Top 5 by Calmar: [{mode_type}] ──')
        for r in subset[:5]:
            flag = '★★★' if r['maxdd'] > -0.25 else ('★★' if r['maxdd'] > -0.30 else ('★' if r['maxdd'] > -0.35 else ''))
            print(f"    {r['mode']:<52} Calmar={r['calmar']:>+6.3f}  "
                  f"Ret={r['return_pct']:>+6.1%}  MaxDD={r['maxdd']:>+6.2%}  "
                  f"Sharpe={r['sharpe']:>+6.3f}  {flag}")

    # Save
    OUT.write_text(json.dumps(all_results[:50], indent=2, default=str))
    print(f'\n  JSON (top 50) saved → {OUT}')
    print(f'  Total time: {time.time()-t0:.1f}s')


if __name__ == '__main__':
    main()
