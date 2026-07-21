"""
simulate_v63_quadrant.py — GH,TH Quadrant-Gated Master Strategy
================================================================

WHY GH,TH IS THE ONLY PROFITABLE QUADRANT
------------------------------------------
The 4 BSDT channels measure four orthogonal kinds of abnormality:

    δ_G (dG)  — STRUCTURAL NOVELTY   — something new is happening
    δ_T (dT)  — TEMPORAL RARITY      — this hasn't happened in a long time
    δ_A (E7)  — VELOCITY / IMPULSE   — the market is moving fast right now
    δ_C (E6)  — SYSTEMIC DISTORTION  — everything is shifting together

The channels fire in order: δ_T → δ_G → δ_A → δ_C → price.

GH,TH (G-high AND T-high) means: "a regime shift is underway that the
system has never experienced before."  This is the ONLY quadrant where:
  1. The move has structural depth (δ_G — not ordinary volatility)
  2. The move is historically rare (δ_T — crowd hasn't priced it in)
  3. There is still runway (price hasn't yet reacted fully)

All other quadrants represent inferior conditions:
  GH,TL → novel structure but within-regime normal frequency → crowded
  GL,TH → rare event but no new structural pressure → likely noise spike
  GL,TL → ordinary market noise → entry timing is random

QUADRANT GATE (v63 translation to 4-channel z-scores)
------------------------------------------------------
From v63 floating-gate logic, translated to our signed channel projections:

    G_active[t] = (rolling max of z(dG) over N bars) > G_THRESH
    T_active[t] = (rolling max of z(dT) over N bars) > T_THRESH
    fired[t]    = |z(E7)| > A_THRESH                            (velocity burst)

    GH_TH[t]  = fired[t] AND G_active[t] AND T_active[t]  → enter at CLIP× size
    otherwise                                               → no new entries

This replaces the 2h confirmation filter from simulate_master_strategy.py.
Keep all other pillars: CB (90d/18%/13%) + trailing stop (1.5σ/0.75σ).

STRATEGY COMPARISON
-------------------
  [A] Master (2h filter, current)              ← baseline from simulate_master_strategy
  [B] Quadrant-gate (GH,TH only)              ← this script, strict kill
  [C] Quadrant-gate + size boost              ← GH,TH gets CLIP× size, others half
  [D] Daily filter (original champion)        ← revert control (best daily config)

Expected result:
  GH,TH filter should improve precision (fewer bad trades) at cost of recall
  (fewer total entries). Net effect on Calmar depends on which entries are cut.
"""
from __future__ import annotations
import json, time
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
    equity_metrics, period_table, drawdown_periods,
    print_metrics, print_yearly, print_dd,
    simulate_unit_trailing, simulate_crash_shorts, simulate_combined,
    build_positions,
    RT_COST, FUND_HOURLY, HOURS_PER_DAY,
    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
    DYN_STRENGTH_CAP, DYN_VOL_CAP, DYN_TOTAL_CAP,
    CRASH_RET_THRESH, CRASH_VOL_MULT, CRASH_SL, CRASH_TP, CRASH_MAX_HOURS,
)

OUT  = Path(OUT_DIR) / 'simulation_v63_quadrant.json'
BAR  = '=' * 110
SEP  = '-' * 110

# ─── Champion CB params (daily-signal tuning, reverting 2h mis-tune) ──────────
CB_HALT        = 0.08   # sweep winner: halt at 8% from 180d rolling peak
CB_RESUME      = 0.01   # sweep winner: resume at 1% — strictly dominates 3% (+0.175 Calmar, same MaxDD)
CB_WINDOW_DAYS = 180    # longer window keeps peak reference high through bear phases

# ─── Quadrant gate thresholds ─────────────────────────────────────────────────
N_MEM      = 8       # rolling window (bars) for G_active / T_active memory
                     # same as v63 N_OPT=8 (one hourly "cooling off" period)
G_THRESH   = 0.45    # z(dG) must have peaked > this in the last N_MEM bars
                     # calibrated to ~55th pctile of absolute values
T_THRESH   = 0.30    # z(dT) threshold — lower because δ_T fires earliest
                     # calibrated to ~45th pctile
A_THRESH   = 0.35    # |z(E7)| activity threshold — velocity above noise floor

CLIP_BOOST = 1.25    # size multiplier for GH,TH entries (boost when all aligned)
HALF_SIZE  = 0.50    # size for entries where only ONE of G/T is active
KILL_SIZE  = 0.0     # size when neither is active (pure kill)

# ─── Trailing stop (daily-champion config) ────────────────────────────────────
TRAIL_TRIGGER_MULT = 1.5   # σ units
TRAIL_DIST_MULT    = 0.75  # σ units

# ─── Minimum force condition (NEW CHAMPION gate) ─────────────────────────────
# Require |z(E7)| >= this value at entry time.
# Removes geometrically-undecided entries (no directional commitment).
# Proven effect: +7.974 Calmar, −16.80% MaxDD vs +7.086 / −27.13% baseline.
# Only 148 / 2892 entries blocked (5.1% — surgical, not aggressive).
ZE7_MIN_FORCE = 0.10


def _build_quadrant_gate(ch: dict, hours: pd.DatetimeIndex) -> np.ndarray:
    """Compute per-bar quadrant gate scale (STRICT: kills non-GH,TH entries).

    Returns float array shape (len(hours),):
        CLIP_BOOST  — GH,TH (fired + G-hot + T-hot)
        HALF_SIZE   — one of G/T hot, fired
        HALF_SIZE   — neither hot, fired (minimal entry allowed)
        KILL_SIZE   — not fired (no velocity event)

    All arrays are aligned to `hours` via forward-fill.
    """
    zE7 = ch['E7'].reindex(hours, method='ffill').fillna(0.0).shift(1).fillna(0.0)
    zdG = ch['dG'].reindex(hours, method='ffill').fillna(0.0).shift(1).fillna(0.0)
    zdT = ch['dT'].reindex(hours, method='ffill').fillna(0.0).shift(1).fillna(0.0)

    G_mem = zdG.rolling(N_MEM, min_periods=1).max()
    T_mem = zdT.rolling(N_MEM, min_periods=1).max()

    fired    = (zE7.abs().values > A_THRESH)
    G_active = (G_mem.values > G_THRESH)
    T_active = (T_mem.values > T_THRESH)

    gate = np.where(
        ~fired,        KILL_SIZE,
        np.where(
            G_active & T_active, CLIP_BOOST,
            np.where(
                G_active | T_active, HALF_SIZE,
                HALF_SIZE * 0.5,
            )
        )
    )
    return gate.astype(float)


def _build_quadrant_multiplier(ch: dict, hours: pd.DatetimeIndex) -> np.ndarray:
    """Compute per-bar SIZE MULTIPLIER for layered mode (never kills entries).

    Layers on top of the daily filter — the daily filter remains the gating
    authority; the quadrant only MODIFIES SIZE:
        CLIP_BOOST   — GH,TH active → boost size
        1.0          — otherwise    → pass through unchanged

    Rolling memory means G_active/T_active stay hot for N_MEM bars after
    the channel first exceeded the threshold.
    """
    zdG = ch['dG'].reindex(hours, method='ffill').fillna(0.0).shift(1).fillna(0.0)
    zdT = ch['dT'].reindex(hours, method='ffill').fillna(0.0).shift(1).fillna(0.0)

    G_mem = zdG.rolling(N_MEM, min_periods=1).max()
    T_mem = zdT.rolling(N_MEM, min_periods=1).max()

    G_active = (G_mem.values > G_THRESH)
    T_active = (T_mem.values > T_THRESH)

    return np.where(G_active & T_active, CLIP_BOOST, 1.0).astype(float)


def simulate_unit_quadrant(op, hi, lo, cl,
                            hpos_arr, gate_arr, psi_y,
                            sl: float, tp: float,
                            trail_trigger: float, trail_dist: float,
                            use_trail: bool = True):
    """Single-pass per-bar simulator with quadrant gate replacing 2h filter.

    gate_arr[i]:  CLIP_BOOST → full+boost entry
                  HALF_SIZE  → half-size entry
                  KILL_SIZE  → no new entry (existing positions not affected)
    """
    n   = len(op)
    ret = np.zeros(n, dtype=float)
    pos = 0.0; size = 1.0; entry = 0.0
    stop_price = 0.0; take_price = 0.0
    trail_active  = False
    trail_extreme = 0.0
    trailing_on   = use_trail and (trail_trigger > 0 or trail_dist > 0)

    counts = dict(entries=0, exits=0, flips=0, longs=0, shorts=0,
                  stop=0, tp=0, signal_exit=0, close_end=0,
                  trail_exit=0, killed=0, gh_th=0, partial=0,
                  active_hours=0)
    psi_sizes = []

    for i in range(n):
        hpos   = hpos_arr[i]
        hactive = (hpos != 0)
        g      = gate_arr[i]

        if hactive:
            if g <= 1e-9:
                hactive = False; counts['killed'] += 1
            else:
                scale = g * psi_y[i]
                if scale <= 1e-9:
                    hactive = False; counts['killed'] += 1

        # ── manage open position ──────────────────────────────────────────
        if pos != 0:
            counts['active_hours'] += 1
            exit_ret = None; reason = None
            if pos > 0:
                if hi[i] >= take_price:
                    exit_ret = take_price / entry - 1; reason = 'tp'
                else:
                    if trailing_on:
                        trail_extreme = max(trail_extreme, hi[i])
                        unreal = trail_extreme / entry - 1.0
                        if unreal >= trail_trigger:
                            trail_active = True
                        if trail_active:
                            new_ts = trail_extreme * (1.0 - trail_dist)
                            if new_ts > stop_price:
                                stop_price = new_ts
                    if lo[i] <= stop_price:
                        exit_ret = stop_price / entry - 1
                        reason   = 'trail_exit' if trail_active else 'stop'
            else:
                if lo[i] <= take_price:
                    exit_ret = entry / take_price - 1; reason = 'tp'
                else:
                    if trailing_on:
                        trail_extreme = min(trail_extreme, lo[i])
                        unreal = entry / trail_extreme - 1.0
                        if unreal >= trail_trigger:
                            trail_active = True
                        if trail_active:
                            new_ts = trail_extreme * (1.0 + trail_dist)
                            if new_ts < stop_price:
                                stop_price = new_ts
                    if hi[i] >= stop_price:
                        exit_ret = entry / stop_price - 1
                        reason   = 'trail_exit' if trail_active else 'stop'

            if exit_ret is None and hactive and hpos == -pos:
                exit_ret = (op[i] / entry - 1) if pos > 0 else (entry / op[i] - 1)
                reason   = 'signal_exit'; counts['flips'] += 1

            if exit_ret is not None:
                ret[i] += size * (exit_ret - RT_COST)
                counts[reason] += 1; counts['exits'] += 1
                pos = 0; size = 1; entry = 0
                stop_price = 0; take_price = 0
                trail_active = False; trail_extreme = 0.0
            else:
                ret[i] -= size * FUND_HOURLY

        # ── open new position ─────────────────────────────────────────────
        if pos == 0 and hactive:
            effective_scale = g * psi_y[i]
            pos   = float(hpos); size = float(effective_scale); entry = float(op[i])
            psi_sizes.append(float(psi_y[i]))
            trail_active  = False
            trail_extreme = float(op[i])
            if pos > 0:
                stop_price = entry * (1.0 - sl)
                take_price = entry * (1.0 + tp)
                counts['longs'] += 1
            else:
                stop_price = entry * (1.0 + sl)
                take_price = entry * (1.0 - tp)
                counts['shorts'] += 1
            counts['entries'] += 1
            if g >= CLIP_BOOST - 0.01:          counts['gh_th']   += 1
            elif g >= HALF_SIZE - 0.01:         counts['partial'] += 1

    if pos != 0:
        i = n - 1
        gross = (cl[i] / entry - 1) if pos > 0 else (entry / cl[i] - 1)
        ret[i] += size * (gross - RT_COST)
        counts['close_end'] += 1; counts['exits'] += 1

    counts['avg_psi_y'] = float(np.mean(psi_sizes)) if psi_sizes else 0.0
    return ret, counts


def simulate_unit_trailing_ze7gate(
    op, hi, lo, cl,
    hpos_arr, dpos_arr, dactive_arr,
    psi_y,
    sl: float, tp: float,
    trail_trigger: float, trail_dist: float,
    ze7_arr: np.ndarray,
    ze7_min = ZE7_MIN_FORCE,   # scalar float OR np.ndarray of per-bar thresholds
):
    """Identical to simulate_unit_trailing but adds a minimum-force gate at entry.

    Gate: abs(ze7_arr[i]) >= threshold_i  where threshold_i is:
        - ze7_min (scalar float, default 0.10)  — fixed threshold
        - ze7_min[i] (array)                    — dynamic per-bar threshold

    Applied ONLY at new-entry time — never touches open positions.
    Fixed 0.10:  5.1% of entries blocked; MaxDD −27.13% → −16.80%.
    """
    from simulate_master_strategy import RT_COST, FUND_HOURLY

    n    = len(op)
    ret  = np.zeros(n, dtype=float)
    pos  = 0.0; size = 1.0; entry = 0.0
    stop_price = 0.0; take_price = 0.0
    trail_active  = False
    trail_extreme = 0.0
    trailing_on   = (trail_trigger > 0 or trail_dist > 0)

    counts = dict(entries=0, exits=0, flips=0, longs=0, shorts=0,
                  stop=0, tp=0, signal_exit=0, close_end=0,
                  trail_exit=0,
                  skipped_daily_filter=0, psi_blocked=0,
                  active_hours=0, vetoed_force=0)
    psi_sizes = []

    for i in range(n):
        hpos   = hpos_arr[i]; hactive = hpos != 0
        dpos_i = dpos_arr[i]; dact_i  = dactive_arr[i]
        scale  = 1.0

        if hactive:
            if   dact_i and hpos == dpos_i:  scale = 1.0
            elif dact_i and hpos != dpos_i:
                hactive = False; hpos = 0;   counts['skipped_daily_filter'] += 1
            else:                            scale = 0.5
        if hactive:
            scale *= psi_y[i]
            if scale <= 1e-12:
                hactive = False; hpos = 0;   counts['psi_blocked'] += 1

        if pos != 0:
            counts['active_hours'] += 1
            exit_ret = None; reason = None

            if pos > 0:
                if hi[i] >= take_price:
                    exit_ret = take_price / entry - 1; reason = 'tp'
                else:
                    if trailing_on:
                        trail_extreme = max(trail_extreme, hi[i])
                        if trail_extreme / entry - 1.0 >= trail_trigger:
                            trail_active = True
                        if trail_active:
                            new_ts = trail_extreme * (1.0 - trail_dist)
                            if new_ts > stop_price: stop_price = new_ts
                    if lo[i] <= stop_price:
                        exit_ret = stop_price / entry - 1
                        reason   = 'trail_exit' if trail_active else 'stop'
            else:
                if lo[i] <= take_price:
                    exit_ret = entry / take_price - 1; reason = 'tp'
                else:
                    if trailing_on:
                        trail_extreme = min(trail_extreme, lo[i])
                        if entry / trail_extreme - 1.0 >= trail_trigger:
                            trail_active = True
                        if trail_active:
                            new_ts = trail_extreme * (1.0 + trail_dist)
                            if new_ts < stop_price: stop_price = new_ts
                    if hi[i] >= stop_price:
                        exit_ret = entry / stop_price - 1
                        reason   = 'trail_exit' if trail_active else 'stop'

            if exit_ret is None and hactive and hpos == -pos:
                exit_ret = (op[i] / entry - 1) if pos > 0 else (entry / op[i] - 1)
                reason   = 'signal_exit'; counts['flips'] += 1

            if exit_ret is not None:
                ret[i] += size * (exit_ret - RT_COST)
                counts[reason] += 1; counts['exits'] += 1
                pos = 0; size = 1; entry = 0
                stop_price = 0; take_price = 0
                trail_active = False; trail_extreme = 0.0
            else:
                ret[i] -= size * FUND_HOURLY

        if pos == 0 and hactive:
            # ── Minimum force gate (scalar or per-bar array) ────────────────────
            thresh_i = float(ze7_min[i]) if hasattr(ze7_min, '__len__') else float(ze7_min)
            if thresh_i > 0.0 and abs(ze7_arr[i]) < thresh_i:
                counts['vetoed_force'] += 1
                continue

            pos   = float(hpos); size = float(scale); entry = float(op[i])
            psi_sizes.append(float(psi_y[i]))
            trail_active  = False
            trail_extreme = float(op[i])
            if pos > 0:
                stop_price = entry * (1.0 - sl)
                take_price = entry * (1.0 + tp)
                counts['longs'] += 1
            else:
                stop_price = entry * (1.0 + sl)
                take_price = entry * (1.0 - tp)
                counts['shorts'] += 1
            counts['entries'] += 1

    if pos != 0:
        gross   = (cl[-1] / entry - 1) if pos > 0 else (entry / cl[-1] - 1)
        ret[-1]+= size * (gross - RT_COST)
        counts['close_end'] += 1; counts['exits'] += 1

    counts['avg_psi_y'] = float(np.mean(psi_sizes)) if psi_sizes else 0.0
    return ret, counts


def build_positions_quadrant(df_1h, comp_raw, calib_mask, ch, ohlc_all):
    """Signal / sizing builder using the quadrant gate (replaces 2h filter)."""
    common_start = comp_raw.dropna().index.min()
    common_end   = comp_raw.dropna().index.max()
    ohlc  = ohlc_all[(ohlc_all.index >= common_start) &
                      (ohlc_all.index <= common_end)].copy()
    hours = ohlc.index

    idx      = df_1h.index
    train_1h = (idx >= TRAIN_START) & (idx < TEST_START)
    train_idx = np.where(train_1h)[0]
    cm = np.zeros(len(df_1h), dtype=bool); cm[train_idx[-CALIB_BARS:]] = True

    hourly_cal  = comp_raw[cm].abs().dropna()
    sig_shifted = comp_raw.shift(1).reindex(hours).fillna(0.0).values.astype(float)
    hth  = float(hourly_cal.quantile(BASE['q_hourly']))
    hpos = np.where(np.abs(sig_shifted) >= hth, np.sign(sig_shifted).astype(int), 0)
    hq   = _percentile_against(np.abs(sig_shifted), hourly_cal.values)

    # ── Quadrant gate ──────────────────────────────────────────────────────────
    gate_arr = _build_quadrant_gate(ch, hours)
    pct_gh_th = float((gate_arr >= CLIP_BOOST - 0.01).mean())
    pct_fire  = float((hpos != 0).mean())
    pct_combined = float(((hpos != 0) & (gate_arr > KILL_SIZE + 0.01)).mean())
    print(f'  hourly signal active  : {pct_fire:.1%} of bars')
    print(f'  GH,TH gate hot        : {pct_gh_th:.1%} of bars')
    print(f'  entry-eligible (both) : {pct_combined:.1%} of bars')

    # ── Daily vol for sigma-stops ──────────────────────────────────────────────
    all_days   = pd.Index(sorted(ohlc_all.index.normalize().unique()))
    calib_days = all_days[
        (all_days >= pd.Timestamp(TRAIN_START)) & (all_days < pd.Timestamp(TEST_START))
    ]
    ret_daily = (ohlc_all['close'].pct_change().fillna(0.0)
                 .groupby(ohlc_all.index.normalize()).sum())
    daily_vol = float(ret_daily.reindex(calib_days).std())

    # ── Sizing components ──────────────────────────────────────────────────────
    ret_h    = ohlc_all['close'].pct_change().fillna(0.0)
    rv       = ret_h.rolling(24, min_periods=12).std().shift(1)
    rv_cal   = rv[(rv.index >= pd.Timestamp(TRAIN_START)) &
                  (rv.index <  pd.Timestamp(TEST_START))].dropna()
    rv_h     = rv.reindex(hours).ffill().fillna(rv_cal.median())
    stress_rank = _percentile_against(rv_h.values, rv_cal.values)
    vol_base    = (float(rv_cal.median()) / rv_h.clip(lower=1e-8)).values

    unit0_arr, _ = simulate_unit_with_psi(
        ohlc['open'].values.astype(float),
        ohlc['high'].values.astype(float),
        ohlc['low'].values.astype(float),
        ohlc['close'].values.astype(float),
        hpos, np.zeros(len(hours), dtype=int),
        np.zeros(len(hours), dtype=bool), np.ones(len(hours)),
        BASE['sl_mult'] * daily_vol, BASE['tp_mult'] * daily_vol,
    )
    unit0    = pd.Series(unit0_arr, index=hours)
    roll_mu  = unit0.rolling(240, min_periods=72).mean().shift(1).fillna(0.0)
    roll_sd  = unit0.rolling(240, min_periods=72).std().shift(1).replace(0, np.nan).fillna(unit0.std())
    q_quality = 0.25 + 1.25 / (1.0 + np.exp(-np.clip(
                    roll_mu / roll_sd * np.sqrt(24 * 365.25) * 0.50, -50, 50)))

    # dq: use the quadrant gate value as the "daily quality" component
    # Higher gate → higher strength signal
    sm_mult = np.clip(0.25 + DYN_STRENGTH_CAP * hq, 0.25, DYN_STRENGTH_CAP)
    vm_mult = np.clip(vol_base, 0.25, DYN_VOL_CAP)
    delta   = 1.2 - stress_rank
    gamma   = np.clip(np.sign(delta) * delta ** 2, 0.4, 1.3)
    size_mult = np.clip(sm_mult * q_quality * vm_mult * gamma, 0.0, DYN_TOTAL_CAP)

    # ── Crash signal ───────────────────────────────────────────────────────────
    eth_ret_12h = ohlc['close'].pct_change(12).shift(1).fillna(0.0)
    rv_1h_24    = ret_h.rolling(24, min_periods=12).std().shift(1).fillna(0.0)
    rv_train    = rv_1h_24[(rv_1h_24.index >= pd.Timestamp(TRAIN_START)) &
                            (rv_1h_24.index <  pd.Timestamp(TEST_START))]
    rv_base     = float(rv_train.median())
    crash_signal = ((eth_ret_12h < CRASH_RET_THRESH) &
                    (rv_1h_24    > CRASH_VOL_MULT * rv_base)).values.astype(int)

    op = ohlc['open'].values.astype(float)
    hi = ohlc['high'].values.astype(float)
    lo = ohlc['low'].values.astype(float)
    cl = ohlc['close'].values.astype(float)

    return dict(
        hours=hours, op=op, hi=hi, lo=lo, cl=cl,
        hpos=hpos, gate_arr=gate_arr,
        daily_vol=daily_vol, size_mult=size_mult,
        crash_signal=crash_signal, rv_base=rv_base,
    )


def main():
    t0 = time.time()
    print(BAR)
    print('  v63 QUADRANT-GATED MASTER STRATEGY')
    print('  Gate: GH,TH only — δ_G AND δ_T must both be elevated')
    print('  Pillars: Quadrant Gate + Trailing Stop + Circuit Breaker')
    print(BAR)

    print('\n[1] Building geometry + channel series + OHLCV ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ch      = get_channel_series()          # {E7, dG, E6, dT}
    ohlc_all = fetch_futures_ohlcv()

    print(f'\n  Channel z-score stats (full series):')
    for name, s in ch.items():
        v = s.dropna()
        print(f'    {name}: mean={float(v.mean()):+.3f}  std={float(v.std()):.3f}  '
              f'p75={float(v.abs().quantile(0.75)):.3f}  p90={float(v.abs().quantile(0.90)):.3f}')

    print('\n[2] Building signal, sizing, quadrant gate, crash signal ...')
    p = build_positions_quadrant(df_1h, comp_raw, calib_mask, ch, ohlc_all)
    sl = BASE['sl_mult'] * p['daily_vol']
    tp = BASE['tp_mult'] * p['daily_vol']
    trail_trigger = TRAIL_TRIGGER_MULT * p['daily_vol']
    trail_dist    = TRAIL_DIST_MULT    * p['daily_vol']
    print(f'  daily_vol={p["daily_vol"]:.2%}  SL={sl:.2%}  TP={tp:.2%}')
    print(f'  trail_trigger={trail_trigger:.2%}  trail_dist={trail_dist:.2%}')

    test_ts = pd.Timestamp(TEST_START)

    print('\n[3] Crash-short unit returns ...')
    crash_arr, crash_cnt = simulate_crash_shorts(
        p['op'], p['hi'], p['lo'], p['cl'],
        p['crash_signal'], CRASH_SL, CRASH_TP, CRASH_MAX_HOURS,
    )
    unit_crash = pd.Series(crash_arr, index=p['hours'])
    unit_zero  = pd.Series(np.zeros(len(p['hours'])), index=p['hours'])
    print(f'  crash: entries={crash_cnt["entries"]}  '
          f'stop={crash_cnt["stop"]}  tp={crash_cnt["tp"]}  '
          f'time_exit={crash_cnt["time_exit"]}')

    print('\n[4] Quadrant-gated simulation sweep ...')
    configs = [
        dict(label='strict_kill',   gate=p['gate_arr'],
             note='GH,TH=boost; else kill — strict quadrant filter'),
        dict(label='no_gate_daily', gate=np.ones(len(p['hours'])),
             note='No gate (baseline 1h-only, no daily/2h filter)'),
    ]

    results = {}
    for cfg in configs:
        gate_now = cfg['gate']
        lbl      = cfg['label']
        print(f'\n  [{lbl}]  {cfg["note"]}')

        unit_arr, cnt = simulate_unit_quadrant(
            p['op'], p['hi'], p['lo'], p['cl'],
            p['hpos'], gate_now, p['size_mult'],
            sl, tp, trail_trigger, trail_dist, use_trail=True,
        )
        unit_normal = pd.Series(unit_arr, index=p['hours'])

        for label_ext, K_crash, uc in [
            ('no_crash',   0.0, unit_zero),
            ('with_crash', 1.5, unit_crash),
        ]:
            full_lbl = f'{lbl}_{label_ext}'
            res = simulate_combined(
                unit_normal, uc,
                K_normal=DYN_K, K_crash=K_crash,
                dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                cb_halt=CB_HALT, cb_resume=CB_RESUME,
                cb_window_days=CB_WINDOW_DAYS, use_cb=True,
            )
            eq = res['eq']
            m_full  = equity_metrics(eq,                             label=full_lbl)
            m_train = equity_metrics(eq[eq.index <  test_ts],        label='train')
            m_oos   = equity_metrics(eq[eq.index >= test_ts],        label='OOS')
            print(f'    {full_lbl}')
            print(f'      OOS  Calmar={m_oos["calmar"]:+.3f}  '
                  f'Ret={m_oos["return_pct"]:+.1%}  '
                  f'MaxDD={m_oos["maxdd"]:+.2%}  '
                  f'Sharpe={m_oos["sharpe"]:+.3f}')
            print(f'      FULL Calmar={m_full["calmar"]:+.3f}  '
                  f'Ret={m_full["return_pct"]:+.1%}  '
                  f'MaxDD={m_full["maxdd"]:+.2%}')
            print(f'      CB: {res["pct_halted"]:.1%} halted  '
                  f'{res["n_trips"]} trips  '
                  f'entries={cnt["entries"]}  '
                  f'gh_th={cnt.get("gh_th",0)}  '
                  f'killed={cnt.get("killed",0)}')

            results[full_lbl] = dict(
                full=m_full, train=m_train, oos=m_oos,
                yearly=period_table(eq, 'Y'),
                drawdowns=drawdown_periods(eq),
                counts=cnt,
                cb_halted_pct=res['pct_halted'],
                n_cb_trips=res['n_trips'],
                gate_params=dict(
                    N_MEM=N_MEM, G_THRESH=G_THRESH, T_THRESH=T_THRESH,
                    A_THRESH=A_THRESH, CLIP_BOOST=CLIP_BOOST,
                ),
            )

    # ── [layered_daily] Daily filter champion + quadrant size boost on top ────
    print(f'\n  [layered_daily]  Daily filter (champion) + GH,TH size-boost layer')
    p_day = build_positions(df_1h, comp_raw, calib_mask, ohlc_all)
    q_mult = _build_quadrant_multiplier(ch, p_day['hours'])
    pct_boost = float((q_mult > 1.0).mean())
    print(f'  GH,TH boost active : {pct_boost:.1%} of bars  (×{CLIP_BOOST} when active)')

    layered_size = p_day['size_mult'] * q_mult
    lbl = 'layered_daily'
    unit_arr_l, cnt_l = simulate_unit_trailing(
        p_day['op'], p_day['hi'], p_day['lo'], p_day['cl'],
        p_day['hpos'], p_day['dpos'], p_day['dactive'],
        layered_size,
        sl, tp, trail_trigger, trail_dist,
    )
    unit_normal_l = pd.Series(unit_arr_l, index=p_day['hours'])

    crash_l_arr, crash_l_cnt = simulate_crash_shorts(
        p_day['op'], p_day['hi'], p_day['lo'], p_day['cl'],
        p_day['crash_signal'], CRASH_SL, CRASH_TP, CRASH_MAX_HOURS,
    )
    unit_crash_l = pd.Series(crash_l_arr, index=p_day['hours'])
    unit_zero_l  = pd.Series(np.zeros(len(p_day['hours'])), index=p_day['hours'])

    for label_ext, K_crash, uc_l in [
        ('no_crash',   0.0, unit_zero_l),
        ('with_crash', 1.5, unit_crash_l),
    ]:
        full_lbl = f'{lbl}_{label_ext}'
        res = simulate_combined(
            unit_normal_l, uc_l,
            K_normal=DYN_K, K_crash=K_crash,
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
            cb_halt=CB_HALT, cb_resume=CB_RESUME,
            cb_window_days=CB_WINDOW_DAYS, use_cb=True,
        )
        eq = res['eq']
        m_full  = equity_metrics(eq,                             label=full_lbl)
        m_train = equity_metrics(eq[eq.index <  test_ts],        label='train')
        m_oos   = equity_metrics(eq[eq.index >= test_ts],        label='OOS')
        print(f'    {full_lbl}')
        print(f'      OOS  Calmar={m_oos["calmar"]:+.3f}  '
              f'Ret={m_oos["return_pct"]:+.1%}  '
              f'MaxDD={m_oos["maxdd"]:+.2%}  '
              f'Sharpe={m_oos["sharpe"]:+.3f}')
        print(f'      FULL Calmar={m_full["calmar"]:+.3f}  '
              f'Ret={m_full["return_pct"]:+.1%}  '
              f'MaxDD={m_full["maxdd"]:+.2%}')
        print(f'      CB: {res["pct_halted"]:.1%} halted  {res["n_trips"]} trips  '
              f'entries={cnt_l["entries"]}  '
              f'boosted={int((q_mult[p_day["hpos"] != 0] > 1.0).sum())} GH,TH entries')
        results[full_lbl] = dict(
            full=m_full, train=m_train, oos=m_oos,
            yearly=period_table(eq, 'Y'),
            drawdowns=drawdown_periods(eq),
            counts=cnt_l,
            cb_halted_pct=res['pct_halted'],
            n_cb_trips=res['n_trips'],
            gate_params=dict(
                N_MEM=N_MEM, G_THRESH=G_THRESH, T_THRESH=T_THRESH,
                CLIP_BOOST=CLIP_BOOST, mode='layered_multiplier',
            ),
        )

    # ── [layered_daily_no_crash_ze7] Champion + |zE7| >= 0.10 force gate ─────────
    print(f'\n  [layered_daily_no_crash_ze7]  Champion + minimum-force gate |zE7|≥{ZE7_MIN_FORCE}')
    ze7_s = ch['E7'].reindex(p_day['hours'], method='ffill').fillna(0.0).shift(1).fillna(0.0)
    ze7_arr_gate = ze7_s.values

    lbl_ze7 = 'layered_daily_no_crash_ze7'
    unit_arr_ze7, cnt_ze7 = simulate_unit_trailing_ze7gate(
        p_day['op'], p_day['hi'], p_day['lo'], p_day['cl'],
        p_day['hpos'], p_day['dpos'], p_day['dactive'],
        layered_size,
        sl, tp, trail_trigger, trail_dist,
        ze7_arr=ze7_arr_gate, ze7_min=ZE7_MIN_FORCE,
    )
    unit_normal_ze7 = pd.Series(unit_arr_ze7, index=p_day['hours'])
    res_ze7 = simulate_combined(
        unit_normal_ze7, unit_zero_l,
        K_normal=DYN_K, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME,
        cb_window_days=CB_WINDOW_DAYS, use_cb=True,
    )
    eq_ze7    = res_ze7['eq']
    m_full_ze7  = equity_metrics(eq_ze7,                              label=lbl_ze7)
    m_train_ze7 = equity_metrics(eq_ze7[eq_ze7.index <  test_ts],    label='train')
    m_oos_ze7   = equity_metrics(eq_ze7[eq_ze7.index >= test_ts],    label='OOS')
    pct_vetoed  = cnt_ze7['vetoed_force'] / max(cnt_ze7['entries'] + cnt_ze7['vetoed_force'], 1)
    print(f'    {lbl_ze7}')
    print(f'      OOS  Calmar={m_oos_ze7["calmar"]:+.3f}  '
          f'Ret={m_oos_ze7["return_pct"]:+.1%}  '
          f'MaxDD={m_oos_ze7["maxdd"]:+.2%}  '
          f'Sharpe={m_oos_ze7["sharpe"]:+.3f}')
    print(f'      FULL Calmar={m_full_ze7["calmar"]:+.3f}  '
          f'Ret={m_full_ze7["return_pct"]:+.1%}  '
          f'MaxDD={m_full_ze7["maxdd"]:+.2%}')
    print(f'      CB: {res_ze7["pct_halted"]:.1%} halted  {res_ze7["n_trips"]} trips  '
          f'entries={cnt_ze7["entries"]}  vetoed_force={cnt_ze7["vetoed_force"]} ({pct_vetoed:.1%})')
    print(f'      Yearly:')
    yearly_ze7 = period_table(eq_ze7, 'Y')
    print_yearly(yearly_ze7)
    print(f'      Drawdowns:')
    print_dd(drawdown_periods(eq_ze7))
    results[lbl_ze7] = dict(
        full=m_full_ze7, train=m_train_ze7, oos=m_oos_ze7,
        yearly=yearly_ze7,
        drawdowns=drawdown_periods(eq_ze7),
        counts=cnt_ze7,
        cb_halted_pct=res_ze7['pct_halted'],
        n_cb_trips=res_ze7['n_trips'],
        gate_params=dict(
            ze7_min=ZE7_MIN_FORCE,
            CB_HALT=CB_HALT, CB_RESUME=CB_RESUME, CB_WINDOW_DAYS=CB_WINDOW_DAYS,
            mode='layered_multiplier_ze7gate',
        ),
    )

    # ── Summary table ──────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SUMMARY  (OOS)')
    print(BAR)
    hdr = (f"  {'Config':<42} {'Calmar':>8} {'Ret':>9} {'MaxDD':>9} "
           f"{'Sharpe':>8} {'Entries':>8} {'GH_TH%':>8}")
    print(hdr); print(SEP)
    for k, v in results.items():
        m   = v['oos']
        ent = v['counts'].get('entries', 0)
        gh  = v['counts'].get('gh_th', 0)
        pct = f'{gh/max(ent,1):.0%}' if ent > 0 and gh > 0 else ('layered' if 'layered' in k else 'n/a')
        print(f"  {k:<42} {m['calmar']:>+8.3f} {m['return_pct']:>+8.1%} "
              f"{m['maxdd']:>+8.2%} {m['sharpe']:>+8.3f} {ent:>8,d} {pct:>8}")

    OUT.write_text(json.dumps(results, indent=2, default=str))
    print(f'\n  JSON saved → {OUT}')
    print(f'  Total time: {time.time() - t0:.1f}s')


if __name__ == '__main__':
    main()
