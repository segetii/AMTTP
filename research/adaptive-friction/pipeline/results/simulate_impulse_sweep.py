"""
simulate_impulse_sweep.py — Impulse / Breakout Momentum Layer Sweep
=====================================================================
Fills the BSDT "no-signal blind spot": sudden large moves where the
physics engine is silent because the geometry didn't pre-build.

Forensic evidence (analyse_missed_opportunities.py):
  - 2,669 bars had large price moves (>5%) with BSDT completely silent
  - May 2025: ETH +24.69% in a single day — zero BSDT signal

Root cause: BSDT channels are geometric-state predictors. "Bolt from the
blue" moves have no detectable precursor in state-space — they're regime
shocks, not geometry-building events.

─── Architecture ────────────────────────────────────────────────────────────
  Champion unit_B (ze7≥0.10 gate)
    + IMPULSE_FRAC × Impulse momentum unit
    → blended_unit → simulate_combined (same CB params as champion #1)

  blended_unit[t] = unit_bsdt[t] + FRAC * unit_impulse[t]

  The CB + adaptive-Y brake operate on the blended equity, so impulse
  trading is automatically halted during champion drawdown periods.

─── Impulse signal (causal: all inputs shifted 1 bar, enter at next open) ───
  z_1h[t]  = (log_ret_1h[t-1] − μ_train) / σ_train    per-bar z-shock
  z_4h[t]  = cumulative 4h z-score ending at bar t-1   short-term trend
  z_vol[t] = log-volume z-score at bar t-1              volume confirmation

─── Variants swept (5 signal modes) ─────────────────────────────────────────
  A: abs(z_1h) > thresh                           [basic shock]
  B: A + sign(z_1h) == sign(z_4h)                [+ 4h direction confirm]
  C: A + abs(z_1h.shift(1)) > 1.5                [+ persistence (2-bar)]
  D: A + z_vol > VOL_THRESH                       [+ above-avg volume]
  E: B + D                                        [4h confirm + volume]

─── Better-than-basic improvements vs. user's idea ─────────────────────────
  1. Train-calibrated z-scores (not fixed σ) — adapts to regime
  2. Log-volume z-score for confirmation — filters thin-market noise
  3. Rolling volatility regime check — adaptive threshold option
  4. Blended with CB / Y-brake — impulse auto-pauses during drawdowns
  5. Full sweep (60 combos) — data-driven threshold selection

─── Sweep grid: 4 × 3 × 5 = 60 combos ──────────────────────────────────────
  thresh : [2.0, 2.5, 3.0, 3.5]  z-score threshold
  frac   : [0.3, 0.5, 0.7]       impulse position size fraction
  variant: [A, B, C, D, E]       signal mode

Baseline: Champion #1 (ze7≥0.10 + CB halt=8% resume=1%) → OOS Calmar +3.236
"""
from __future__ import annotations
import time
from pathlib import Path
import itertools, textwrap
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from test_daily_geometry_stop_tp_ohlc   import (
    build_daily_geometry, fetch_futures_ohlcv, get_channel_series,
)
from test_psi_adaptive_y                import BASE
from simulate_master_strategy           import (
    build_positions, simulate_combined,
    RT_COST, FUND_HOURLY, DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
)
from simulate_v63_quadrant              import (
    _build_quadrant_multiplier,
    CB_WINDOW_DAYS, TRAIL_TRIGGER_MULT, TRAIL_DIST_MULT, ZE7_MIN_FORCE,
    simulate_unit_trailing_ze7gate,
    CB_HALT, CB_RESUME,
)

INIT        = 1_000.0
TEST_TS     = pd.Timestamp(TEST_START)
TRAIN_TS    = pd.Timestamp(TRAIN_START)
BAR         = '=' * 120
SEP         = '-' * 120

# ── Sweep hyperparameters ─────────────────────────────────────────────────────
THRESH_GRID  = [2.0, 2.5, 3.0, 3.5]  # z-shock threshold
FRAC_GRID    = [0.3, 0.5, 0.7]        # impulse size fraction of normal unit
VARIANT_LIST = ['A', 'B', 'C', 'D', 'E']
VOL_Z_THRESH = 1.0                    # volume z-score threshold for variants D and E


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_impulse_signals(ohlc_all: pd.DataFrame,
                          hours: pd.DatetimeIndex) -> dict[str, np.ndarray]:
    """Build all per-bar impulse signal arrays (causal). Returns dict with
    arrays for z_1h, z_4h, z_vol, and z_1h_lag2 all pre-shifted by 1 bar."""
    # Align to strategy hours
    close = ohlc_all['close'].reindex(hours).ffill()
    vol   = ohlc_all['volume'].reindex(hours).ffill().clip(lower=1.0)

    # 1h log return
    lret_1h = np.log(close / close.shift(1)).fillna(0.0)

    # 4h cumulative log return (rolling sum of 4 bars)
    lret_4h = lret_1h.rolling(4, min_periods=4).sum().fillna(0.0)

    # Log volume (more normal-ish than raw volume)
    lvol = np.log(vol)

    # Train-period masks (full training window, not just CALIB_BARS slice)
    train_mask = (pd.Series(hours).values >= np.datetime64(TRAIN_START)) & \
                 (pd.Series(hours).values <  np.datetime64(TEST_START))

    # Z-score calibration from training period
    def _z(s: pd.Series, mask: np.ndarray) -> pd.Series:
        mu  = float(s[mask].mean())
        sig = float(s[mask].std())
        return (s - mu) / max(sig, 1e-9)

    z_1h  = _z(lret_1h, train_mask)   # 1h return z-score
    z_4h  = _z(lret_4h, train_mask)   # 4h return z-score
    z_vol = _z(lvol,    train_mask)    # log-volume z-score

    # Causal shift: at bar t we use info from bar t-1 (or t-2)
    return {
        'z_1h':  z_1h.shift(1).fillna(0.0).values,   # previous 1h z-shock
        'z_4h':  z_4h.shift(1).fillna(0.0).values,   # previous 4h trend
        'z_vol': z_vol.shift(1).fillna(0.0).values,   # previous volume level
        'z_1h_lag2': z_1h.shift(2).fillna(0.0).values # 2-bar-ago shock
    }


def make_fire_dir(sigs: dict[str, np.ndarray],
                  thresh: float,
                  variant: str) -> tuple[np.ndarray, np.ndarray]:
    """Return (fire: bool array, direction: int array) for given variant."""
    z1  = sigs['z_1h']
    z4  = sigs['z_4h']
    zv  = sigs['z_vol']
    z1l = sigs['z_1h_lag2']
    n   = len(z1)

    fire = np.abs(z1) > thresh                      # base: 1h shock

    if variant == 'A':                              # basic
        pass
    elif variant == 'B':                            # + 4h direction agree
        fire &= (np.sign(z1) == np.sign(z4)) & (z4 != 0.0)
    elif variant == 'C':                            # + persistence (lag-2 also elevated)
        fire &= np.abs(z1l) > 1.5
    elif variant == 'D':                            # + above-average volume
        fire &= zv > VOL_Z_THRESH
    elif variant == 'E':                            # 4h confirm + volume
        fire &= (np.sign(z1) == np.sign(z4)) & (z4 != 0.0) & (zv > VOL_Z_THRESH)
    else:
        raise ValueError(f'Unknown variant {variant}')

    direction = np.where(fire, np.sign(z1).astype(int), 0)
    return fire, direction


# ─────────────────────────────────────────────────────────────────────────────
#  IMPULSE UNIT SIMULATOR
# ─────────────────────────────────────────────────────────────────────────────

def simulate_impulse_unit(
    op: np.ndarray, hi: np.ndarray, lo: np.ndarray, cl: np.ndarray,
    fire_arr: np.ndarray, dir_arr: np.ndarray,
    sl: float, tp: float,
    trail_trigger: float, trail_dist: float,
    size_frac: float = 0.5,
) -> tuple[np.ndarray, dict]:
    """Standalone impulse momentum unit.

    Enters at next-bar open when impulse fires.
    Uses identical trailing-stop mechanics as the BSDT unit.
    No daily filter — impulse fires in any market condition.
    Size is fixed at size_frac (no quadrant boost, no psi scaling).
    """
    n = len(op)
    ret = np.zeros(n, dtype=float)
    pos = 0.0; entry = 0.0; size = size_frac
    stop_px = 0.0; take_px = 0.0
    trail_active = False; trail_ext = 0.0
    trailing_on = (trail_trigger > 0 or trail_dist > 0)
    counts = dict(entries=0, exits=0, active_hours=0, longs=0, shorts=0)

    for i in range(n):
        # ── manage open position ─────────────────────────────────────────────
        if pos != 0:
            counts['active_hours'] += 1
            exit_ret = None

            if pos > 0:   # long
                if hi[i] >= take_px:
                    exit_ret = take_px / entry - 1
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
            else:         # short
                if lo[i] <= take_px:
                    exit_ret = entry / take_px - 1
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

            if exit_ret is not None:
                ret[i] += size * (exit_ret - RT_COST)
                counts['exits'] += 1
                pos = 0; entry = 0; stop_px = 0; take_px = 0
                trail_active = False; trail_ext = 0.0
            else:
                ret[i] -= size * FUND_HOURLY

        # ── open new impulse position ────────────────────────────────────────
        if pos == 0 and fire_arr[i]:
            pos   = float(dir_arr[i])
            entry = float(op[i])
            trail_active = False; trail_ext = float(op[i])
            if pos > 0:
                stop_px = entry * (1.0 - sl)
                take_px = entry * (1.0 + tp)
                counts['longs'] += 1
            else:
                stop_px = entry * (1.0 + sl)
                take_px = entry * (1.0 - tp)
                counts['shorts'] += 1
            counts['entries'] += 1

    # Close any open position at last bar
    if pos != 0:
        gross = (cl[-1] / entry - 1) if pos > 0 else (entry / cl[-1] - 1)
        ret[-1] += size * (gross - RT_COST)

    return ret, counts


# ─────────────────────────────────────────────────────────────────────────────
#  METRICS
# ─────────────────────────────────────────────────────────────────────────────

def oos_calmar(eq: pd.Series) -> float:
    eq_oos = eq[eq.index >= TEST_TS]
    if len(eq_oos) < 100: return 0.0
    eq_oos = eq_oos * (INIT / float(eq_oos.iloc[0]))
    dd     = (eq_oos - eq_oos.cummax()) / eq_oos.cummax()
    years  = max((eq_oos.index[-1] - eq_oos.index[0]).days / 365.25, 1e-9)
    cagr   = float((eq_oos.iloc[-1] / INIT) ** (1 / years) - 1.0)
    maxdd  = float(dd.min())
    return cagr / abs(maxdd) if maxdd < 0 else 0.0


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
                         start=float(s.iloc[0]),
                         end  =float(s.iloc[-1]),
                         ret  =float(s.iloc[-1] / s.iloc[0] - 1.0)))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(BAR)
    print('  IMPULSE / BREAKOUT MOMENTUM LAYER SWEEP')
    print('  Fills the BSDT "no-signal" blind spot via z-scored price shocks')
    print('  Baseline: Champion #1 (ze7≥0.10 + CB halt=8% resume=1%)  OOS Calmar +3.236')
    print(BAR)

    # ── [1] Load data ─────────────────────────────────────────────────────────
    print('\n  Loading data ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ch       = get_channel_series()
    ohlc_all = fetch_futures_ohlcv()

    p_day = build_positions(df_1h, comp_raw, calib_mask, ohlc_all)
    hours = p_day['hours']

    daily_vol     = p_day['daily_vol']
    sl            = BASE['sl_mult']       * daily_vol
    tp            = BASE['tp_mult']       * daily_vol
    trail_trigger = TRAIL_TRIGGER_MULT    * daily_vol
    trail_dist    = TRAIL_DIST_MULT       * daily_vol

    q_mult       = _build_quadrant_multiplier(ch, hours)
    layered_size = p_day['size_mult'] * q_mult
    unit_zero    = pd.Series(np.zeros(len(hours)), index=hours)

    ze7_s   = ch['E7'].reindex(hours, method='ffill').fillna(0.0).shift(1).fillna(0.0)
    ze7_arr = ze7_s.values

    print(f'  daily_vol={daily_vol:.2%}  SL={sl:.2%}  TP={tp:.2%}')
    print(f'  trail_trigger={trail_trigger:.2%}  trail_dist={trail_dist:.2%}')

    # ── [2] Champion unit B (ze7 gate, fixed) ─────────────────────────────────
    print('\n  Building champion unit B (ze7≥0.10 gate) ...')
    unit_B_arr, cnt_B = simulate_unit_trailing_ze7gate(
        p_day['op'], p_day['hi'], p_day['lo'], p_day['cl'],
        p_day['hpos'], p_day['dpos'], p_day['dactive'],
        layered_size, sl, tp, trail_trigger, trail_dist,
        ze7_arr=ze7_arr, ze7_min=ZE7_MIN_FORCE,
    )
    unit_B = pd.Series(unit_B_arr, index=hours)

    # ── Champion baseline equity ───────────────────────────────────────────────
    champ_res = simulate_combined(
        unit_B, unit_zero,
        K_normal=DYN_K, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME,
        cb_window_days=CB_WINDOW_DAYS, use_cb=True,
    )
    champ_stats = oos_stats(champ_res['eq'])
    print(f'  Champion baseline → OOS Calmar={champ_stats["calmar"]:+.3f}  '
          f'CAGR={champ_stats["cagr"]:+.1%}  MaxDD={champ_stats["maxdd"]:+.2%}  '
          f'Sharpe={champ_stats["sharpe"]:+.3f}  entries={cnt_B["entries"]}')

    # ── [3] Build impulse signals once ────────────────────────────────────────
    print('\n  Computing impulse signals ...')
    sigs = build_impulse_signals(ohlc_all, hours)

    # Show signal stats
    for thresh in THRESH_GRID:
        n_A = int((np.abs(sigs['z_1h']) > thresh).sum())
        n_B = int((np.abs(sigs['z_1h']) > thresh).sum())
        print(f'    thresh={thresh:.1f}σ : {n_A} bars fire variant-A '
              f'({n_A / len(hours):.2%}  of all bars)')

    # ── [4] Sweep ─────────────────────────────────────────────────────────────
    print(f'\n  Running {len(THRESH_GRID) * len(FRAC_GRID) * len(VARIANT_LIST)} combos ...')
    results = []
    op, hi, lo, cl = p_day['op'], p_day['hi'], p_day['lo'], p_day['cl']

    for thresh, frac, variant in itertools.product(THRESH_GRID, FRAC_GRID, VARIANT_LIST):
        fire_arr, dir_arr = make_fire_dir(sigs, thresh, variant)
        n_impulse_fires = int(fire_arr.sum())

        # Impulse unit simulation
        imp_arr, imp_cnt = simulate_impulse_unit(
            op, hi, lo, cl,
            fire_arr, dir_arr,
            sl, tp, trail_trigger, trail_dist,
            size_frac=frac,
        )
        unit_imp = pd.Series(imp_arr, index=hours)

        # Blend: champion BSDT + impulse
        blended_unit = unit_B + unit_imp  # frac already encoded in size_frac

        # Apply combined CB + Y-brake
        res = simulate_combined(
            blended_unit, unit_zero,
            K_normal=DYN_K, K_crash=0.0,
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
            cb_halt=CB_HALT, cb_resume=CB_RESUME,
            cb_window_days=CB_WINDOW_DAYS, use_cb=True,
        )
        stats = oos_stats(res['eq'])
        delta_calmar = stats['calmar'] - champ_stats['calmar']

        results.append(dict(
            thresh=thresh, frac=frac, variant=variant,
            calmar=stats['calmar'], delta_calmar=delta_calmar,
            cagr=stats['cagr'], maxdd=stats['maxdd'], sharpe=stats['sharpe'],
            final=stats['final'],
            n_fires=n_impulse_fires,
            imp_entries=imp_cnt['entries'],
            eq=res['eq'],
        ))

    # ── [5] Sort and display ──────────────────────────────────────────────────
    results.sort(key=lambda r: -r['calmar'])

    print(f'\n{BAR}')
    print('  SWEEP RESULTS  (sorted by OOS Calmar, top 15 shown)')
    print(BAR)
    print(f'  {"Variant":<8} {"Thresh":>7} {"Frac":>6} '
          f'{"Calmar":>9} {"ΔCalmar":>9} {"MaxDD":>8} {"Sharpe":>8} '
          f'{"CAGR":>8} {"Final$":>9} {"ImpFires":>10} {"ImpEntries":>12}')
    print(f'  {SEP[:110]}')

    for r in results[:15]:
        marker = '  ★' if r['delta_calmar'] > 0 else '   '
        print(f'{marker} {r["variant"]:<8} {r["thresh"]:>6.1f}σ {r["frac"]:>5.1f}× '
              f'{r["calmar"]:>+9.3f} {r["delta_calmar"]:>+9.3f} {r["maxdd"]:>+7.2%} '
              f'{r["sharpe"]:>+7.3f} {r["cagr"]:>+7.1%} '
              f'{r["final"]:>9,.0f} {r["n_fires"]:>10} {r["imp_entries"]:>12}')

    # Show baseline in context
    print(f'\n  Baseline champion: Calmar={champ_stats["calmar"]:+.3f}  '
          f'MaxDD={champ_stats["maxdd"]:+.2%}  Sharpe={champ_stats["sharpe"]:+.3f}  '
          f'Final=${champ_stats["final"]:,.0f}')

    # ── [6] Variant summary (best per variant) ────────────────────────────────
    print(f'\n{BAR}')
    print('  BEST RESULT PER VARIANT (best Calmar within each signal mode)')
    print(BAR)
    print(f'  {"Variant":<8} {"Name":^42} {"Thresh":>7} {"Frac":>6} '
          f'{"Calmar":>9} {"ΔCalmar":>9} {"MaxDD":>8} {"Sharpe":>8}')
    print(f'  {SEP[:110]}')

    variant_names = {
        'A': 'Basic shock (z_1h > thresh)',
        'B': 'Shock + 4h direction confirm',
        'C': 'Shock + 2-bar persistence',
        'D': 'Shock + above-avg volume',
        'E': 'Shock + 4h confirm + volume',
    }
    for v in VARIANT_LIST:
        group = [r for r in results if r['variant'] == v]
        if not group: continue
        best = group[0]  # already sorted by calmar
        marker = '★' if best['delta_calmar'] > 0 else ' '
        print(f'  {marker} {best["variant"]:<6} {variant_names[best["variant"]]:<42} '
              f'{best["thresh"]:>6.1f}σ  {best["frac"]:>5.1f}×  '
              f'{best["calmar"]:>+9.3f}  {best["delta_calmar"]:>+9.3f}  '
              f'{best["maxdd"]:>+7.2%}  {best["sharpe"]:>+7.3f}')

    # ── [7] Year-by-year: best vs. champion ───────────────────────────────────
    best_overall = results[0]
    print(f'\n{BAR}')
    print(f'  YEAR-BY-YEAR: Best result [variant-{best_overall["variant"]} '
          f'thresh={best_overall["thresh"]:.1f}σ frac={best_overall["frac"]:.1f}×] '
          f'vs. Champion')
    print(BAR)

    champ_rows = yearly_table(champ_res['eq'])
    best_rows  = yearly_table(best_overall['eq'])
    yr_champ = {r['year']: r for r in champ_rows}
    yr_best  = {r['year']: r for r in best_rows}
    all_years = sorted(set(yr_champ) | set(yr_best))

    print(f'  {"Year":<8}  '
          f'{"Champion End$":>14} {"Champ Ret":>10}  '
          f'{"+ Impulse End$":>14} {"Impls Ret":>10}  '
          f'{"Δ $":>10}')
    print(f'  {SEP[:90]}')
    for yr in all_years:
        role = '(train)' if yr <= 2022 else '(OOS)  '
        ch = yr_champ.get(yr)
        bst = yr_best.get(yr)
        ch_end  = ch['end']  if ch  else float('nan')
        bst_end = bst['end'] if bst else float('nan')
        ch_ret  = f'{ch["ret"]:+.1%}'  if ch  else '—'
        bst_ret = f'{bst["ret"]:+.1%}' if bst else '—'
        delta   = bst_end - ch_end if (ch and bst) else float('nan')
        delta_s = f'{delta:>+,.0f}' if not np.isnan(delta) else '—'
        print(f'  {yr} {role}  '
              f'{ch_end:>14,.0f} {ch_ret:>10}  '
              f'{bst_end:>14,.0f} {bst_ret:>10}  '
              f'{delta_s:>10}')

    # ── [8] Bottom full table ──────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  FULL SWEEP TABLE  (all 60 combos, sorted by OOS Calmar)')
    print(BAR)
    print(f'  {"V":<3} {"Thresh":>6} {"Frac":>5} '
          f'{"Calmar":>9} {"ΔCalmar":>9} {"MaxDD":>8} '
          f'{"Sharpe":>8} {"CAGR":>8} {"Final $":>9}')
    print(f'  {SEP[:80]}')
    for r in results:
        mark = '★' if r['delta_calmar'] > 0 else ' '
        print(f'  {mark} {r["variant"]:<2} {r["thresh"]:>5.1f}σ {r["frac"]:>4.1f}× '
              f'{r["calmar"]:>+9.3f} {r["delta_calmar"]:>+9.3f} {r["maxdd"]:>+7.2%} '
              f'{r["sharpe"]:>+7.3f} {r["cagr"]:>+7.1%} {r["final"]:>9,.0f}')

    print(f'\n  Total elapsed: {time.time()-t0:.1f}s')
    print(BAR)


if __name__ == '__main__':
    main()
