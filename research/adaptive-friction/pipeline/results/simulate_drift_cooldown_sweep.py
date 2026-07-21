"""
simulate_drift_cooldown_sweep.py
================================
Tests two corrective filters on the champion strategy (layered_daily_no_crash,
CB=8%/3%/180d) to reduce MaxDD without hurting Sharpe:

  FILTER 1 — Short-term drift veto (directional sanity check)
      if direction == LONG  and eth_ret_Nh < -drift_thresh  → skip
      if direction == SHORT and eth_ret_Nh > +drift_thresh  → skip
      Rationale: prevents entering AFTER a local reversal has already occurred.
      Uses N=12h or N=24h lookback.

  FILTER 2 — Anti-cluster memory (per-direction stop cooldown)
      if last M same-direction trades stopped within cooldown_hours → block that dir
      Rationale: treats directional staleness state, not just symptoms.
      With optional confirmation tightening (require |ret_Nh| > min_confirmation).

Neither filter touches zE7 (proved destructive in diagnose_wrong_trades.py).

Grid:
  drift_lookback ∈ {12, 24}
  drift_thresh   ∈ {0.000, 0.003, 0.005, 0.008, 0.012, 0.018}
  cooldown_hours ∈ {0, 24, 48, 72, 96}
  n_stop_thresh  = 2  (fixed — 2 consecutive same-dir stops triggers cooldown)

  Total: 2×6×5 = 60 combinations
"""
from __future__ import annotations
import time
from collections import deque
import numpy as np
import pandas as pd
from pathlib import Path

from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START
from test_daily_geometry_stop_tp_ohlc   import (
    build_daily_geometry, fetch_futures_ohlcv, get_channel_series,
)
from test_psi_adaptive_y                import BASE
from simulate_adaptive_y_drawdown_brake import INIT
from simulate_master_strategy           import (
    build_positions, simulate_combined, equity_metrics,
    RT_COST, FUND_HOURLY, HOURS_PER_DAY,
    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
)
from simulate_v63_quadrant              import (
    _build_quadrant_multiplier,
    CB_HALT, CB_RESUME, CB_WINDOW_DAYS,
    TRAIL_TRIGGER_MULT, TRAIL_DIST_MULT,
)

BAR     = '=' * 110
SEP     = '-' * 110
TEST_TS = pd.Timestamp(TEST_START)


# ─────────────────────────────────────────────────────────────────────────────
#  FILTERED SIMULATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def simulate_filtered(
    op, hi, lo, cl,
    hpos_arr, dpos_arr, dactive_arr,
    layered_size,
    sl: float, tp: float,
    trail_trigger: float, trail_dist: float,
    # ── drift veto params ──────────────────────────────────────────
    drift_ret:     np.ndarray,   # precomputed N-bar % return array (ETH close)
    drift_thresh:  float,        # |ret| threshold to veto entry (0 = inactive)
    # ── anti-cluster params ────────────────────────────────────────
    cooldown_bars: int,          # hours to block same direction after M stops (0 = inactive)
    n_stop_thresh: int = 2,      # M consecutive same-dir stops triggers cooldown
) -> tuple:
    """
    Drop-in replacement for simulate_unit_trailing with two causal entry filters.

    Both filters are applied ONLY at new-entry time (never touch open positions).
    Both filters add to counts['vetoed_drift'] and counts['vetoed_cluster'].
    """
    n   = len(op)
    ret = np.zeros(n, dtype=float)
    pos = 0.0; size = 1.0; entry = 0.0
    stop_px = 0.0; take_px = 0.0
    trail_active = False; trail_ext = 0.0
    trailing_on  = (trail_trigger > 0 or trail_dist > 0)

    # Anti-cluster memory: ring of (bar_index, direction, was_stop)
    # We track per-direction stop history as a deque of bar indices
    dir_stop_history: dict[int, deque] = {1: deque(), -1: deque()}

    counts = dict(
        entries=0, exits=0, longs=0, shorts=0,
        stop=0, tp=0, signal_exit=0, trail_exit=0,
        close_end=0, flips=0,
        skipped_daily_filter=0, psi_blocked=0, active_hours=0,
        vetoed_drift=0, vetoed_cluster=0,
    )
    psi_sizes = []

    for i in range(n):
        hpos   = hpos_arr[i]; hactive = hpos != 0
        dpos_i = dpos_arr[i]; dact_i  = dactive_arr[i]
        scale  = layered_size[i]

        # ── daily context filter (mirrors simulate_unit_trailing exactly) ──
        if hactive:
            if dact_i and hpos == dpos_i:
                pass
            elif dact_i and hpos != dpos_i:
                hactive = False; hpos = 0
                counts['skipped_daily_filter'] += 1
            else:
                scale *= 0.5
        if hactive and scale <= 1e-12:
            hactive = False; hpos = 0
            counts['psi_blocked'] += 1

        # ── manage open position ──────────────────────────────────────────────
        if pos != 0:
            counts['active_hours'] += 1
            exit_ret = None; reason = None

            if pos > 0:
                if hi[i] >= take_px:
                    exit_ret = take_px / entry - 1; reason = 'tp'
                else:
                    if trailing_on:
                        trail_ext = max(trail_ext, hi[i])
                        if trail_ext / entry - 1.0 >= trail_trigger:
                            trail_active = True
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
                        if entry / trail_ext - 1.0 >= trail_trigger:
                            trail_active = True
                        if trail_active:
                            ns = trail_ext * (1.0 + trail_dist)
                            if ns < stop_px: stop_px = ns
                    if hi[i] >= stop_px:
                        exit_ret = entry / stop_px - 1
                        reason   = 'trail_exit' if trail_active else 'stop'

            if exit_ret is None and hactive and hpos == -pos:
                exit_ret = (op[i] / entry - 1) if pos > 0 else (entry / op[i] - 1)
                reason   = 'signal_exit'; counts['flips'] += 1

            if exit_ret is not None:
                ret[i]  += size * (exit_ret - RT_COST)
                counts[reason] = counts.get(reason, 0) + 1
                counts['exits'] += 1

                # ── record in anti-cluster memory ────────────────────────
                closed_dir = int(pos)
                was_stop   = int(reason == 'stop')
                if cooldown_bars > 0 and was_stop:
                    dir_stop_history[closed_dir].append(i)

                pos = 0; size = 1; entry = 0
                stop_px = 0; take_px = 0
                trail_active = False; trail_ext = 0.0
            else:
                ret[i] -= size * FUND_HOURLY

        # ── new entry candidate ───────────────────────────────────────────────
        if pos == 0 and hactive:
            intended_dir = int(hpos)

            # ── FILTER 1: drift veto ──────────────────────────────────────
            if drift_thresh > 0.0:
                dr = drift_ret[i] if not np.isnan(drift_ret[i]) else 0.0
                if intended_dir == +1 and dr < -drift_thresh:
                    counts['vetoed_drift'] += 1
                    continue
                if intended_dir == -1 and dr > +drift_thresh:
                    counts['vetoed_drift'] += 1
                    continue

            # ── FILTER 2: anti-cluster cooldown ──────────────────────────
            if cooldown_bars > 0:
                hist = dir_stop_history[intended_dir]
                # Drop stale entries outside cooldown window
                while hist and i - hist[0] >= cooldown_bars:
                    hist.popleft()
                if len(hist) >= n_stop_thresh:
                    counts['vetoed_cluster'] += 1
                    continue

            # ── open position ─────────────────────────────────────────────
            pos   = float(hpos); size = float(scale); entry = float(op[i])
            psi_sizes.append(float(layered_size[i]))
            trail_active = False; trail_ext = float(op[i])
            if pos > 0:
                stop_px = entry * (1.0 - sl); take_px = entry * (1.0 + tp)
                counts['longs'] += 1
            else:
                stop_px = entry * (1.0 + sl); take_px = entry * (1.0 - tp)
                counts['shorts'] += 1
            counts['entries'] += 1

    # close at end of series
    if pos != 0:
        gross   = (cl[-1] / entry - 1) if pos > 0 else (entry / cl[-1] - 1)
        ret[-1]+= size * (gross - RT_COST)
        counts['close_end'] += 1; counts['exits'] += 1

    counts['avg_psi_y'] = float(np.mean(psi_sizes)) if psi_sizes else 0.0
    return ret, counts


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(BAR)
    print('  DRIFT-VETO + ANTI-CLUSTER SWEEP')
    print('  Base champion: layered_daily_no_crash  Calmar=+7.086  MaxDD=−27.13%')
    print('  Rational: directional staleness fix — no zE7 filtering')
    print(BAR)

    # ── [1] Build geometry + positions (ONCE) ─────────────────────────────────
    print('\n[1] Building geometry + positions ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ch       = get_channel_series()
    ohlc_all = fetch_futures_ohlcv()
    p        = build_positions(df_1h, comp_raw, calib_mask, ohlc_all)
    q_mult   = _build_quadrant_multiplier(ch, p['hours'])
    layered_size = p['size_mult'] * q_mult

    sl            = BASE['sl_mult']     * p['daily_vol']
    tp            = BASE['tp_mult']     * p['daily_vol']
    trail_trigger = TRAIL_TRIGGER_MULT  * p['daily_vol']
    trail_dist    = TRAIL_DIST_MULT     * p['daily_vol']

    hours   = p['hours']
    unit_zero = pd.Series(np.zeros(len(hours)), index=hours)
    test_ts   = TEST_TS

    print(f'  daily_vol={p["daily_vol"]:.3%}  sl={sl:.3%}  tp={tp:.3%}')
    print(f'  CB: halt={CB_HALT:.0%}  resume={CB_RESUME:.0%}  window={CB_WINDOW_DAYS}d')

    # ── [2] Precompute ETH drift arrays ───────────────────────────────────────
    print('\n[2] Precomputing ETH drift arrays ...')
    cl_eth   = pd.Series(p['cl'].astype(float), index=hours)
    ret_12h  = cl_eth.pct_change(12).fillna(0.0).values
    ret_24h  = cl_eth.pct_change(24).fillna(0.0).values
    print(f'  ret_12h: mean={ret_12h.mean():+.5f}  std={ret_12h.std():.5f}')
    print(f'  ret_24h: mean={ret_24h.mean():+.5f}  std={ret_24h.std():.5f}')

    # ── [3] Sweep ──────────────────────────────────────────────────────────────
    drift_lookbacks = {12: ret_12h, 24: ret_24h}
    drift_thresholds = [0.000, 0.003, 0.005, 0.008, 0.012, 0.018]
    cooldown_hours_list = [0, 24, 48, 72, 96]
    N_STOP_THRESH  = 2

    total_combos = len(drift_lookbacks) * len(drift_thresholds) * len(cooldown_hours_list)
    print(f'\n[3] Sweeping {total_combos} filter combinations ...')

    results = []
    for lb_h, drift_arr in drift_lookbacks.items():
        for dt in drift_thresholds:
            for cd_h in cooldown_hours_list:
                cd_bars = cd_h * 1      # 1h bars, so cd_h bars directly

                unit_arr, cnts = simulate_filtered(
                    p['op'], p['hi'], p['lo'], p['cl'],
                    p['hpos'], p['dpos'], p['dactive'],
                    layered_size, sl, tp, trail_trigger, trail_dist,
                    drift_ret=drift_arr, drift_thresh=dt,
                    cooldown_bars=cd_bars, n_stop_thresh=N_STOP_THRESH,
                )
                unit_s = pd.Series(unit_arr, index=hours)
                res = simulate_combined(
                    unit_s, unit_zero,
                    K_normal=DYN_K, K_crash=0.0,
                    dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                    cb_halt=CB_HALT, cb_resume=CB_RESUME,
                    cb_window_days=CB_WINDOW_DAYS, use_cb=True,
                )
                eq     = res['eq']
                m_oos  = equity_metrics(eq[eq.index >= test_ts], label='oos')
                m_full = equity_metrics(eq,                       label='full')

                results.append(dict(
                    lb=lb_h, dt=dt, cd=cd_h,
                    calmar   = m_oos['calmar'],
                    ret_pct  = m_oos['return_pct'],
                    cagr     = m_oos['cagr'],
                    sharpe   = m_oos['sharpe'],
                    maxdd    = m_oos['maxdd'],
                    entries  = cnts['entries'],
                    stops    = cnts.get('stop', 0),
                    stop_rt  = cnts.get('stop', 0) / max(cnts['entries'], 1),
                    v_drift  = cnts.get('vetoed_drift', 0),
                    v_clust  = cnts.get('vetoed_cluster', 0),
                    halted   = res['pct_halted'],
                    cb_trips = res['n_trips'],
                ))

    df_res = pd.DataFrame(results).sort_values('calmar', ascending=False)

    # ── [4] Full table ─────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  FULL RESULTS — sorted by OOS Calmar')
    print(f'  Reference champion (no filter):  Calmar=+7.086  MaxDD=−27.13%  Sharpe=+0.935')
    print(BAR)
    hdr = (f"  {'LB':>3} {'DT':>7} {'CD':>5}  "
           f"{'Calmar':>9} {'Return':>9} {'CAGR':>8} {'Sharpe':>8} "
           f"{'MaxDD':>8} {'Entries':>8} {'Stops':>6} {'StopRt':>7} "
           f"{'vDrift':>7} {'vClust':>7}")
    print(hdr); print(SEP)
    for _, r in df_res.iterrows():
        marker = ''
        if r['maxdd'] > -0.20:         marker += ' ★★★'
        elif r['maxdd'] > -0.22:       marker += ' ★★'
        elif r['maxdd'] > -0.25:       marker += ' ★'
        print(f"  {int(r['lb']):>3}h {r['dt']:>6.3f} cd{int(r['cd']):>3}h  "
              f"{r['calmar']:>+9.3f} {r['ret_pct']:>+8.1%} {r['cagr']:>+7.1%} "
              f"{r['sharpe']:>+8.3f} {r['maxdd']:>+7.2%} "
              f"{int(r['entries']):>8} {int(r['stops']):>6} {r['stop_rt']:>6.1%} "
              f"{int(r['v_drift']):>7} {int(r['v_clust']):>7}{marker}")

    # ── [5] Efficient frontier ─────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  EFFICIENT FRONTIER — best Calmar at each MaxDD cap')
    print(BAR)
    print(f'  {"MaxDD cap":>10}  {"Best Calmar":>12}  {"Return":>9}  {"CAGR":>8}  '
          f'{"Sharpe":>8}  {"Config"}')
    print(SEP)
    for cap in [0.15, 0.18, 0.20, 0.22, 0.25, 0.27]:
        subset = df_res[df_res['maxdd'] > -cap]
        if len(subset) == 0:
            print(f'  DD < {cap:.0%}:  no config qualifies')
            continue
        best = subset.iloc[0]
        print(f'  DD < {cap:.0%}:  {best["calmar"]:>+12.3f}  {best["ret_pct"]:>+8.1%}  '
              f'{best["cagr"]:>+7.1%}  {best["sharpe"]:>+8.3f}  '
              f'lb={int(best["lb"])}h drift={best["dt"]:.3f} cd={int(best["cd"])}h')

    # ── [6] Decomposed impact analysis ────────────────────────────────────────
    print(f'\n{BAR}')
    print('  FILTER DECOMPOSITION — drift-only vs cooldown-only vs combined')
    print(BAR)

    # Drift only (cooldown=0)
    drift_only = df_res[df_res['cd'] == 0].sort_values('calmar', ascending=False)
    print(f'\n  ─ DRIFT VETO ONLY (no cooldown) — top 8:')
    print(f"  {'LB':>3} {'DT':>7}  {'Calmar':>9} {'Return':>9} {'MaxDD':>8} "
          f"{'Sharpe':>8} {'Stops':>6} {'vDrift':>7}")
    for _, r in drift_only.head(8).iterrows():
        print(f"  {int(r['lb']):>3}h {r['dt']:>6.3f}  "
              f"{r['calmar']:>+9.3f} {r['ret_pct']:>+8.1%} {r['maxdd']:>+7.2%} "
              f"{r['sharpe']:>+8.3f} {int(r['stops']):>6} {int(r['v_drift']):>7}")

    # Cooldown only (drift_thresh=0)
    cd_only = df_res[df_res['dt'] == 0.0].sort_values('calmar', ascending=False)
    print(f'\n  ─ COOLDOWN ONLY (no drift veto) — top 8:')
    print(f"  {'CD':>5}  {'Calmar':>9} {'Return':>9} {'MaxDD':>8} "
          f"{'Sharpe':>8} {'Stops':>6} {'vClust':>7}")
    for _, r in cd_only.head(8).iterrows():
        print(f"  cd{int(r['cd']):>3}h  "
              f"{r['calmar']:>+9.3f} {r['ret_pct']:>+8.1%} {r['maxdd']:>+7.2%} "
              f"{r['sharpe']:>+8.3f} {int(r['stops']):>6} {int(r['v_clust']):>7}")

    # Combined (both active)
    both = df_res[(df_res['dt'] > 0) & (df_res['cd'] > 0)].sort_values('calmar', ascending=False)
    print(f'\n  ─ COMBINED (drift veto + cooldown) — top 8:')
    print(f"  {'LB':>3} {'DT':>7} {'CD':>5}  {'Calmar':>9} {'Return':>9} "
          f"{'MaxDD':>8} {'Sharpe':>8} {'vDrift':>7} {'vClust':>7}")
    for _, r in both.head(8).iterrows():
        print(f"  {int(r['lb']):>3}h {r['dt']:>6.3f} cd{int(r['cd']):>3}h  "
              f"{r['calmar']:>+9.3f} {r['ret_pct']:>+8.1%} {r['maxdd']:>+7.2%} "
              f"{r['sharpe']:>+8.3f} {int(r['v_drift']):>7} {int(r['v_clust']):>7}")

    # ── [7] Tradeoff summary ──────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TRADEOFF SUMMARY — Calmar vs MaxDD Pareto frontier')
    print(BAR)
    # For each < MaxDD threshold, compare: no filter vs best filtered
    print(f'\n  {"Config":<48} {"Calmar":>9} {"Return":>9} {"MaxDD":>8} '
          f'{"Sharpe":>8} {"Entries":>8}')
    print(SEP)

    # Baseline (lb=12, dt=0, cd=0)
    base_row = df_res[(df_res['dt'] == 0.0) & (df_res['cd'] == 0)].iloc[0]
    print(f'  {"Baseline (no filter)":<48} {base_row["calmar"]:>+9.3f} '
          f'{base_row["ret_pct"]:>+8.1%} {base_row["maxdd"]:>+7.2%} '
          f'{base_row["sharpe"]:>+8.3f} {int(base_row["entries"]):>8}')

    # Best by Calmar overall
    best_overall = df_res.iloc[0]
    print(f'  {"Best Calmar overall":<48} {best_overall["calmar"]:>+9.3f} '
          f'{best_overall["ret_pct"]:>+8.1%} {best_overall["maxdd"]:>+7.2%} '
          f'{best_overall["sharpe"]:>+8.3f} {int(best_overall["entries"]):>8}')
    print(f'    → lb={int(best_overall["lb"])}h drift={best_overall["dt"]:.3f} '
          f'cd={int(best_overall["cd"])}h')

    # Best Sharpe
    best_sharpe = df_res.sort_values('sharpe', ascending=False).iloc[0]
    print(f'  {"Best Sharpe overall":<48} {best_sharpe["calmar"]:>+9.3f} '
          f'{best_sharpe["ret_pct"]:>+8.1%} {best_sharpe["maxdd"]:>+7.2%} '
          f'{best_sharpe["sharpe"]:>+8.3f} {int(best_sharpe["entries"]):>8}')
    print(f'    → lb={int(best_sharpe["lb"])}h drift={best_sharpe["dt"]:.3f} '
          f'cd={int(best_sharpe["cd"])}h')

    # Best MaxDD < 20% with Calmar > 3
    safe = df_res[(df_res['maxdd'] > -0.20) & (df_res['calmar'] > 3.0)]
    if len(safe) > 0:
        bs = safe.sort_values('calmar', ascending=False).iloc[0]
        print(f'  {"Best Calmar (MaxDD<20%)":<48} {bs["calmar"]:>+9.3f} '
              f'{bs["ret_pct"]:>+8.1%} {bs["maxdd"]:>+7.2%} '
              f'{bs["sharpe"]:>+8.3f} {int(bs["entries"]):>8}')
        print(f'    → lb={int(bs["lb"])}h drift={bs["dt"]:.3f} cd={int(bs["cd"])}h')
    else:
        print(f'  Best Calmar (MaxDD<20%): no config qualifies')

    # Best Calmar with Sharpe > 1.0
    hi_sharpe = df_res[df_res['sharpe'] > 1.0]
    if len(hi_sharpe) > 0:
        bhs = hi_sharpe.sort_values('calmar', ascending=False).iloc[0]
        print(f'  {"Best Calmar (Sharpe>1.0)":<48} {bhs["calmar"]:>+9.3f} '
              f'{bhs["ret_pct"]:>+8.1%} {bhs["maxdd"]:>+7.2%} '
              f'{bhs["sharpe"]:>+8.3f} {int(bhs["entries"]):>8}')
        print(f'    → lb={int(bhs["lb"])}h drift={bhs["dt"]:.3f} cd={int(bhs["cd"])}h')

    elapsed = time.time() - t0
    print(f'\n  Total time: {elapsed:.1f}s   Combinations: {total_combos}')
    print(BAR)


if __name__ == '__main__':
    main()
