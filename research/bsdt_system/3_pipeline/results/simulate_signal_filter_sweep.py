"""
simulate_signal_filter_sweep.py
================================
Tests three signal-quality entry gates on the champion strategy
(layered_daily_no_crash, CB=8%/3%/180d).

USER FRAMEWORK — root cause is trading WITHOUT momentum:
  "If those conditions are NOT present → the correct action is NO TRADE"

RULE 1 (momentum magnitude):
    abs(zE7) >= eps                           [eps ∈ {0, 0.02, 0.05, 0.10}]

RULE 2 (directional alignment):
    direction * zE7 >= 0                      [True/False]
    (momentum must agree with direction; zero momentum is allowed)

RULE 3 (structural support):
    zdG >= zdg_thresh                         [None, -0.10, -0.05, 0.0]

All three are ENTRY gates — never touch open positions.
Applied in order: R1 → R2 → R3.

Grid: 4 × 2 × 4 = 32 combinations (incl. baseline at R1=0, R2=off, R3=None)
"""
from __future__ import annotations
import time
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

BAR = '=' * 110
SEP = '-' * 110
TEST_TS = pd.Timestamp(TEST_START)


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL-FILTERED SIMULATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def simulate_signal_filtered(
    op, hi, lo, cl,
    hpos_arr, dpos_arr, dactive_arr,
    layered_size,
    sl: float, tp: float,
    trail_trigger: float, trail_dist: float,
    # ── signal gate params ────────────────────────────────────────────
    zE7_arr:    np.ndarray,   # per-bar zE7 (velocity), shift(1) applied upstream
    zdG_arr:    np.ndarray,   # per-bar zdG (structural novelty), shift(1) applied
    eps:        float = 0.0,  # Rule 1: require abs(zE7) >= eps (0 = inactive)
    dir_align:  bool  = False, # Rule 2: require direction * zE7 >= 0
    zdg_thresh: float = None,  # Rule 3: require zdG >= zdg_thresh (None = inactive)
) -> tuple:
    """
    Drop-in replacement for simulate_combined entry path with 3 signal gates.

    Gates apply ONLY at new-entry time. Never affect open positions.
    Veto counts tracked per rule.
    """
    n   = len(op)
    ret = np.zeros(n, dtype=float)
    pos = 0.0; size = 1.0; entry = 0.0
    stop_px = 0.0; take_px = 0.0
    trail_active = False; trail_ext = 0.0
    trailing_on  = (trail_trigger > 0 or trail_dist > 0)

    counts = dict(
        entries=0, exits=0, longs=0, shorts=0,
        stop=0, tp=0, signal_exit=0, trail_exit=0,
        close_end=0, flips=0,
        skipped_daily_filter=0, psi_blocked=0, active_hours=0,
        vetoed_r1=0, vetoed_r2=0, vetoed_r3=0,
    )
    psi_sizes = []

    for i in range(n):
        hpos   = hpos_arr[i]; hactive = hpos != 0
        dpos_i = dpos_arr[i]; dact_i  = dactive_arr[i]
        scale  = layered_size[i]

        # ── daily context filter (mirrors champion exactly) ───────────────
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

        # ── manage open position ──────────────────────────────────────────
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
                pos = 0; size = 1; entry = 0
                stop_px = 0; take_px = 0
                trail_active = False; trail_ext = 0.0
            else:
                ret[i] -= size * FUND_HOURLY

        # ── new entry candidate ───────────────────────────────────────────
        if pos == 0 and hactive:
            intended_dir = int(hpos)
            ze7 = zE7_arr[i]
            zdg = zdG_arr[i]

            # ── RULE 1: momentum magnitude gate ──────────────────────────
            if eps > 0.0 and abs(ze7) < eps:
                counts['vetoed_r1'] += 1
                continue

            # ── RULE 2: directional alignment (momentum must agree) ───────
            # zE7 == 0 is allowed (no momentum is neutral, not opposing)
            # Only block when zE7 actively opposes direction
            if dir_align and ze7 != 0.0 and intended_dir * ze7 < 0.0:
                counts['vetoed_r2'] += 1
                continue

            # ── RULE 3: structural support ────────────────────────────────
            if zdg_thresh is not None and zdg < zdg_thresh:
                counts['vetoed_r3'] += 1
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
    print('  SIGNAL-QUALITY FILTER SWEEP')
    print('  Base champion: layered_daily_no_crash  Calmar=+7.086  MaxDD=−27.13%')
    print('  Hypothesis: NO FORCE → NO TRADE  (zE7 + zdG gating)')
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

    hours    = p['hours']
    unit_zero = pd.Series(np.zeros(len(hours)), index=hours)
    test_ts   = TEST_TS

    print(f'  daily_vol={p["daily_vol"]:.3%}  sl={sl:.3%}  tp={tp:.3%}')
    print(f'  CB: halt={CB_HALT:.0%}  resume={CB_RESUME:.0%}  window={CB_WINDOW_DAYS}d')

    # ── [2] Precompute signal arrays (shift(1) for causal application) ─────────
    print('\n[2] Precomputing signal arrays ...')
    zE7_s = ch['E7'].reindex(hours, method='ffill').fillna(0.0).shift(1).fillna(0.0)
    zdG_s = ch['dG'].reindex(hours, method='ffill').fillna(0.0).shift(1).fillna(0.0)
    zE7_arr = zE7_s.values
    zdG_arr = zdG_s.values

    # ── Diagnostic: check distribution across entry bars only ─────────────────
    entry_mask = p['hpos'] != 0
    ze7_at_entries = zE7_arr[entry_mask]
    zdg_at_entries = zdG_arr[entry_mask]
    print(f'  zE7 at entry bars: mean={ze7_at_entries.mean():+.4f}  '
          f'std={ze7_at_entries.std():.4f}  '
          f'pct_zero={np.mean(ze7_at_entries == 0):.1%}  '
          f'pct_pos={np.mean(ze7_at_entries > 0):.1%}  '
          f'pct_neg={np.mean(ze7_at_entries < 0):.1%}')
    print(f'  zdG at entry bars: mean={zdg_at_entries.mean():+.4f}  '
          f'std={zdg_at_entries.std():.4f}  '
          f'pct_pos={np.mean(zdg_at_entries > 0):.1%}  '
          f'pct_neg={np.mean(zdg_at_entries < 0):.1%}')

    # Direction breakdown of zE7 at entries
    hpos = p['hpos']
    long_mask  = (hpos ==  1) & entry_mask
    short_mask = (hpos == -1) & entry_mask
    ze7_long  = zE7_arr[long_mask]
    ze7_short = zE7_arr[short_mask]
    print(f'\n  LONG  entries ({long_mask.sum()}): '
          f'zE7<0 (opposing) = {np.mean(ze7_long < 0):.1%}  '
          f'zE7=0 = {np.mean(ze7_long == 0):.1%}  '
          f'zE7>0 (aligned) = {np.mean(ze7_long > 0):.1%}')
    print(f'  SHORT entries ({short_mask.sum()}): '
          f'zE7>0 (opposing) = {np.mean(ze7_short > 0):.1%}  '
          f'zE7=0 = {np.mean(ze7_short == 0):.1%}  '
          f'zE7<0 (aligned) = {np.mean(ze7_short < 0):.1%}')

    # Percentile of block counts by threshold
    print(f'\n  Rule 1 veto count by eps threshold:')
    for eps_test in [0.01, 0.02, 0.05, 0.10, 0.15, 0.20]:
        blocked = np.mean(abs(ze7_at_entries) < eps_test)
        print(f'    eps={eps_test:.2f}: {blocked:.1%} of entries would be blocked')

    print(f'\n  Rule 2 veto count (direction misalignment):')
    opp_long  = np.mean(ze7_long < 0)
    opp_short = np.mean(ze7_short > 0)
    total_misalign = (np.sum(ze7_long < 0) + np.sum(ze7_short > 0)) / (long_mask.sum() + short_mask.sum())
    print(f'    LONG opposing (zE7<0):  {opp_long:.1%} of long entries')
    print(f'    SHORT opposing (zE7>0): {opp_short:.1%} of short entries')
    print(f'    Total misaligned:       {total_misalign:.1%} of all entries')

    print(f'\n  Rule 3 veto count by zdG threshold:')
    for zdg_test in [-0.10, -0.05, 0.0, 0.05]:
        blocked = np.mean(zdg_at_entries < zdg_test)
        print(f'    zdG<{zdg_test:+.2f}: {blocked:.1%} of entries would be blocked')

    # ── [3] Sweep ──────────────────────────────────────────────────────────────
    eps_list       = [0.0, 0.02, 0.05, 0.10]
    dir_align_list = [False, True]
    zdg_thresh_list = [None, -0.10, -0.05, 0.0]

    total_combos = len(eps_list) * len(dir_align_list) * len(zdg_thresh_list)
    print(f'\n[3] Sweeping {total_combos} signal-filter combinations ...')

    results = []
    for eps in eps_list:
        for da in dir_align_list:
            for zdgt in zdg_thresh_list:
                unit_arr, cnts = simulate_signal_filtered(
                    p['op'], p['hi'], p['lo'], p['cl'],
                    p['hpos'], p['dpos'], p['dactive'],
                    layered_size, sl, tp, trail_trigger, trail_dist,
                    zE7_arr=zE7_arr, zdG_arr=zdG_arr,
                    eps=eps, dir_align=da, zdg_thresh=zdgt,
                )
                unit_s = pd.Series(unit_arr, index=hours)
                res = simulate_combined(
                    unit_s, unit_zero,
                    K_normal=DYN_K, K_crash=0.0,
                    dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                    cb_halt=CB_HALT, cb_resume=CB_RESUME,
                    cb_window_days=CB_WINDOW_DAYS, use_cb=True,
                )
                eq    = res['eq']
                m_oos = equity_metrics(eq[eq.index >= test_ts], label='oos')

                results.append(dict(
                    eps=eps, dir_align=da, zdg_thresh=zdgt,
                    calmar   = m_oos['calmar'],
                    ret_pct  = m_oos['return_pct'],
                    cagr     = m_oos['cagr'],
                    sharpe   = m_oos['sharpe'],
                    maxdd    = m_oos['maxdd'],
                    entries  = cnts['entries'],
                    stops    = cnts.get('stop', 0),
                    stop_rt  = cnts.get('stop', 0) / max(cnts['entries'], 1),
                    v_r1     = cnts.get('vetoed_r1', 0),
                    v_r2     = cnts.get('vetoed_r2', 0),
                    v_r3     = cnts.get('vetoed_r3', 0),
                ))

    df_res = pd.DataFrame(results).sort_values('calmar', ascending=False)

    def _zdg_label(v):
        return f'zdG≥{v:+.2f}' if v is not None else 'zdG=off'

    # ── [4] Full results table ─────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  FULL RESULTS — sorted by OOS Calmar')
    print(f'  Reference: Calmar=+7.086  MaxDD=−27.13%  Sharpe=+0.935  Entries=2892')
    print(BAR)
    hdr = (f"  {'eps':>5} {'R2':>5} {'R3':>10}  "
           f"{'Calmar':>9} {'Return':>9} {'CAGR':>8} {'Sharpe':>8} "
           f"{'MaxDD':>8} {'Entries':>8} {'StopRt':>7} "
           f"{'vR1':>6} {'vR2':>6} {'vR3':>6}")
    print(hdr); print(SEP)
    for _, r in df_res.iterrows():
        marker = ''
        if r['maxdd'] > -0.20:   marker += ' ★★★'
        elif r['maxdd'] > -0.22: marker += ' ★★'
        elif r['maxdd'] > -0.25: marker += ' ★'
        zdg_lbl = _zdg_label(r['zdg_thresh'])
        print(f"  {r['eps']:>5.2f} {'ON' if r['dir_align'] else 'off':>5} {zdg_lbl:>10}  "
              f"{r['calmar']:>+9.3f} {r['ret_pct']:>+8.1%} {r['cagr']:>+7.1%} "
              f"{r['sharpe']:>+8.3f} {r['maxdd']:>+7.2%} "
              f"{int(r['entries']):>8} {r['stop_rt']:>6.1%} "
              f"{int(r['v_r1']):>6} {int(r['v_r2']):>6} {int(r['v_r3']):>6}{marker}")

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
        zdg_lbl = _zdg_label(best['zdg_thresh'])
        print(f'  DD < {cap:.0%}:  {best["calmar"]:>+12.3f}  {best["ret_pct"]:>+8.1%}  '
              f'{best["cagr"]:>+7.1%}  {best["sharpe"]:>+8.3f}  '
              f'eps={best["eps"]:.2f} dir_align={"ON" if best["dir_align"] else "off"} '
              f'{zdg_lbl}')

    # ── [6] Decomposition: which rule contributes ──────────────────────────────
    print(f'\n{BAR}')
    print('  RULE IMPACT DECOMPOSITION')
    print(BAR)

    # Rule 1 only (R2=off, R3=None, eps varies)
    r1_only = df_res[~df_res['dir_align'] & df_res['zdg_thresh'].isna()].sort_values('calmar', ascending=False)
    print(f'\n  ─ RULE 1 ONLY (momentum magnitude gate):')
    print(f"  {'eps':>5}  {'Calmar':>9} {'Return':>9} {'MaxDD':>8} {'Sharpe':>8} "
          f"{'Entries':>8} {'vR1':>6}")
    for _, r in r1_only.iterrows():
        print(f"  {r['eps']:>5.2f}  {r['calmar']:>+9.3f} {r['ret_pct']:>+8.1%} "
              f"{r['maxdd']:>+7.2%} {r['sharpe']:>+8.3f} "
              f"{int(r['entries']):>8} {int(r['v_r1']):>6}")

    # Rule 2 only (R1=0, R3=None, dir_align varies)
    r2_only = df_res[(df_res['eps'] == 0) & df_res['zdg_thresh'].isna()].sort_values('calmar', ascending=False)
    print(f'\n  ─ RULE 2 ONLY (directional alignment gate):')
    print(f"  {'R2':>5}  {'Calmar':>9} {'Return':>9} {'MaxDD':>8} {'Sharpe':>8} "
          f"{'Entries':>8} {'vR2':>6}")
    for _, r in r2_only.iterrows():
        print(f"  {'ON' if r['dir_align'] else 'off':>5}  {r['calmar']:>+9.3f} "
              f"{r['ret_pct']:>+8.1%} {r['maxdd']:>+7.2%} {r['sharpe']:>+8.3f} "
              f"{int(r['entries']):>8} {int(r['v_r2']):>6}")

    # Rule 3 only (R1=0, R2=off, zdg varies)
    r3_only = df_res[(df_res['eps'] == 0) & ~df_res['dir_align']].sort_values('calmar', ascending=False)
    print(f'\n  ─ RULE 3 ONLY (structural support gate):')
    print(f"  {'R3':>10}  {'Calmar':>9} {'Return':>9} {'MaxDD':>8} {'Sharpe':>8} "
          f"{'Entries':>8} {'vR3':>6}")
    for _, r in r3_only.iterrows():
        zdg_lbl = _zdg_label(r['zdg_thresh'])
        print(f"  {zdg_lbl:>10}  {r['calmar']:>+9.3f} {r['ret_pct']:>+8.1%} "
              f"{r['maxdd']:>+7.2%} {r['sharpe']:>+8.3f} "
              f"{int(r['entries']):>8} {int(r['v_r3']):>6}")

    # Combined (all 3 active)
    all3 = df_res[(df_res['eps'] > 0) & df_res['dir_align'] & df_res['zdg_thresh'].notna()].sort_values('calmar', ascending=False)
    print(f'\n  ─ ALL 3 RULES COMBINED — top configs:')
    print(f"  {'eps':>5} {'R2':>5} {'R3':>10}  {'Calmar':>9} {'Return':>9} "
          f"{'MaxDD':>8} {'Sharpe':>8} {'Entries':>8}")
    for _, r in all3.head(8).iterrows():
        zdg_lbl = _zdg_label(r['zdg_thresh'])
        print(f"  {r['eps']:>5.2f} ON {zdg_lbl:>10}  {r['calmar']:>+9.3f} "
              f"{r['ret_pct']:>+8.1%} {r['maxdd']:>+7.2%} {r['sharpe']:>+8.3f} "
              f"{int(r['entries']):>8}")

    # ── [7] Tradeoff summary ──────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TRADEOFF SUMMARY')
    print(BAR)
    print(f'\n  {"Config":<55} {"Calmar":>9} {"Return":>9} {"MaxDD":>8} '
          f'{"Sharpe":>8} {"Entries":>8}')
    print(SEP)

    base_row = df_res[(df_res['eps'] == 0.0) & (~df_res['dir_align']) & df_res['zdg_thresh'].isna()].iloc[0]
    print(f'  {"Baseline (no filter)":<55} {base_row["calmar"]:>+9.3f} '
          f'{base_row["ret_pct"]:>+8.1%} {base_row["maxdd"]:>+7.2%} '
          f'{base_row["sharpe"]:>+8.3f} {int(base_row["entries"]):>8}')

    best = df_res.iloc[0]
    zdg_lbl = _zdg_label(best['zdg_thresh'])
    print(f'  {"Best Calmar overall":<55} {best["calmar"]:>+9.3f} '
          f'{best["ret_pct"]:>+8.1%} {best["maxdd"]:>+7.2%} '
          f'{best["sharpe"]:>+8.3f} {int(best["entries"]):>8}')
    print(f'    → eps={best["eps"]:.2f} dir_align={"ON" if best["dir_align"] else "off"} {zdg_lbl}')

    best_sharpe = df_res.sort_values('sharpe', ascending=False).iloc[0]
    zdg_lbl_s  = _zdg_label(best_sharpe['zdg_thresh'])
    print(f'  {"Best Sharpe overall":<55} {best_sharpe["calmar"]:>+9.3f} '
          f'{best_sharpe["ret_pct"]:>+8.1%} {best_sharpe["maxdd"]:>+7.2%} '
          f'{best_sharpe["sharpe"]:>+8.3f} {int(best_sharpe["entries"]):>8}')
    print(f'    → eps={best_sharpe["eps"]:.2f} dir_align={"ON" if best_sharpe["dir_align"] else "off"} {zdg_lbl_s}')

    safe = df_res[df_res['maxdd'] > -0.20]
    if len(safe) > 0:
        bs = safe.sort_values('calmar', ascending=False).iloc[0]
        zdg_lbl_b = _zdg_label(bs['zdg_thresh'])
        print(f'  {"Best Calmar (MaxDD<20%)":<55} {bs["calmar"]:>+9.3f} '
              f'{bs["ret_pct"]:>+8.1%} {bs["maxdd"]:>+7.2%} '
              f'{bs["sharpe"]:>+8.3f} {int(bs["entries"]):>8}')
        print(f'    → eps={bs["eps"]:.2f} dir_align={"ON" if bs["dir_align"] else "off"} {zdg_lbl_b}')
    else:
        print(f'  Best Calmar (MaxDD<20%): no config qualifies')

    # Minimum filter set: find lowest total veto count that still improves MaxDD
    improved_dd = df_res[df_res['maxdd'] > base_row['maxdd'] + 0.01]  # >1% improvement
    if len(improved_dd) > 0:
        improved_dd = improved_dd.copy()
        improved_dd['total_veto'] = improved_dd['v_r1'] + improved_dd['v_r2'] + improved_dd['v_r3']
        min_veto = improved_dd.sort_values('total_veto').iloc[0]
        zdg_lbl_m = _zdg_label(min_veto['zdg_thresh'])
        print(f'\n  MINIMUM FILTER SET (least entries blocked, still improves MaxDD):')
        print(f'    eps={min_veto["eps"]:.2f}  dir_align={"ON" if min_veto["dir_align"] else "off"}  {zdg_lbl_m}')
        print(f'    Total vetoed: {int(min_veto["total_veto"])}  '
              f'Calmar={min_veto["calmar"]:+.3f}  MaxDD={min_veto["maxdd"]:+.2%}  '
              f'Sharpe={min_veto["sharpe"]:+.3f}')

    elapsed = time.time() - t0
    print(f'\n  Total time: {elapsed:.1f}s   Combinations: {total_combos}')
    print(BAR)


if __name__ == '__main__':
    main()
