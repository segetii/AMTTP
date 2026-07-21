"""Anti-Collapse Short Mode — Trade AGAINST the Geometry During CB Trips.

Normal mode (CB not fired):
    hpos = geometry signal → LONG/SHORT as usual, Adaptive Y sizing, K=3

CB-halted mode (rolling-90d drawdown >= cb_halt):
    Instead of sitting in cash (Y=0), FLIP the geometry signal and trade the
    REVERSE direction at K_short leverage.

Intuition: when the geometry signal loses ≥18% over 90 days, the signal has
inverted — the same force that was the tailwind is now a headwind.  The
cleanest trade is to turn it around and profit from the collapse phase rather
than waiting it out.

The reverse signal uses no Adaptive Y brake — when the CB fires the system is
already in trouble, and the short leg is the escape valve, not the risk source.
We do apply a separate Y_short brake keyed to the SHORT leg's own equity.

Strategies compared on OOS (2023 → today):
    [A] CB-cash K=3  (90d/18% — champion from simulate_circuit_breaker.py)
    [B] CB-short K_short=1  (flip signal, size 1×)
    [C] CB-short K_short=2  (flip signal, size 2×)
    [D] CB-short K_short=3  (flip signal, size 3×)
    [E] Baseline K=3  (no CB, reference)
    [F] Baseline K=5  (no CB, reference)
"""
from __future__ import annotations
import json, time
from collections import deque
from pathlib import Path
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS
from test_daily_geometry_stop_tp_ohlc   import build_daily_geometry, fetch_futures_ohlcv
from test_psi_adaptive_y                import BASE, simulate_unit_with_psi
from simulate_adaptive_y_drawdown_brake import adaptive_equity, INIT
from test_dynamic_profit_sizing         import _percentile_against

OUT = Path(OUT_DIR) / 'simulation_cb_short.json'
BAR = '=' * 110
SEP = '-' * 110

RT_COST     = 2.0 / 1e4
FUND_DAY    = 0.5 / 1e4
FUND_HOURLY = FUND_DAY / 24.0
HOURS_PER_DAY = 24

# Champion CB params (from simulate_circuit_breaker.py sweep)
CB_HALT       = 0.18
CB_RESUME     = 0.13
CB_WINDOW_DAYS = 90

# Normal-mode dynamic sizing
DYN_K            = 3.0
DYN_STRENGTH_CAP = 2.5
DYN_VOL_CAP      = 3.0
DYN_TOTAL_CAP    = 2.0
DYN_DD_SOFT      = 0.05
DYN_DD_STOP      = 0.20
DYN_Y_FLOOR      = 0.25

# Short-mode K grid
K_SHORT_GRID = [0.5, 1.0, 1.5, 2.0, 3.0]


# ─────────────────────────────────────────────────────────────────────────────
#  METRICS
# ─────────────────────────────────────────────────────────────────────────────

def equity_metrics(eq: pd.Series, label: str = '') -> dict:
    r     = eq.pct_change().fillna(eq.iloc[0] / INIT - 1.0)
    dd    = (eq - eq.cummax()) / eq.cummax()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    calmar = float((eq.iloc[-1] / INIT) ** (1 / years) - 1) / max(abs(float(dd.min())), 1e-9)
    return dict(
        label      = label,
        final      = float(eq.iloc[-1]),
        profit     = float(eq.iloc[-1] - INIT),
        return_pct = float(eq.iloc[-1] / INIT - 1.0),
        cagr       = float((eq.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe     = float(np.sqrt(24 * 365.25) * r.mean() / r.std()) if r.std() > 0 else 0.0,
        maxdd      = float(dd.min()),
        calmar     = calmar,
        start      = str(eq.index[0]),
        end        = str(eq.index[-1]),
    )


def period_table(eq: pd.Series, freq: str) -> list[dict]:
    rows = []
    for dt, s in eq.groupby(pd.Grouper(freq=freq)):
        if len(s) < 2: continue
        r  = s.pct_change().dropna()
        dd = (s - s.cummax()) / s.cummax()
        rows.append(dict(
            period     = str(dt.date()),
            start_eq   = round(float(s.iloc[0]), 2),
            end_eq     = round(float(s.iloc[-1]), 2),
            profit     = round(float(s.iloc[-1] - s.iloc[0]), 2),
            return_pct = round(float(s.iloc[-1] / s.iloc[0] - 1.0), 4),
            sharpe     = round(float(np.sqrt(24 * 365.25) * r.mean() / r.std()), 3) if r.std() > 0 else 0.0,
            maxdd      = round(float(dd.min()), 4),
        ))
    return rows


def drawdown_periods(eq: pd.Series, top_n: int = 6) -> list[dict]:
    peak = eq.cummax()
    dd   = (eq - peak) / peak
    rows = []
    in_dd = False; start = None; peak_val = None
    for ts, val in dd.items():
        if not in_dd and val < -1e-4:
            in_dd = True; start = ts; peak_val = float(peak[ts])
        elif in_dd and val >= -1e-4:
            trough_i = dd[start:ts].idxmin()
            rows.append(dict(dd_start=str(start), trough=str(trough_i),
                             dd_end=str(ts), drawdown=float(dd[trough_i]),
                             peak_eq=peak_val, trough_eq=float(eq[trough_i]),
                             duration_days=int((ts - start).days)))
            in_dd = False
    if in_dd:
        trough_i = dd[start:].idxmin()
        rows.append(dict(dd_start=str(start), trough=str(trough_i),
                         dd_end='ongoing', drawdown=float(dd[trough_i]),
                         peak_eq=peak_val, trough_eq=float(eq[trough_i]),
                         duration_days=int((eq.index[-1] - start).days)))
    rows.sort(key=lambda r: r['drawdown'])
    return rows[:top_n]


def print_metrics(m: dict):
    print(f"  {'label':<28} {m.get('label','')}")
    print(f"  {'period':<28} {m['start'][:10]}  →  {m['end'][:10]}")
    print(f"  {'final equity':<28} ${m['final']:>12,.2f}   (started ${INIT:,.0f})")
    print(f"  {'profit':<28} ${m['profit']:>+12,.2f}   ({m['return_pct']:>+.1%})")
    print(f"  {'CAGR':<28} {m['cagr']:>+.2%}")
    print(f"  {'Sharpe (hourly-freq)':<28} {m['sharpe']:>+.3f}")
    print(f"  {'MaxDD':<28} {m['maxdd']:>+.2%}")
    print(f"  {'Calmar':<28} {m['calmar']:>+.3f}")


def print_yearly(rows):
    print(f"  {'Year':<8} {'Start':>10} {'End':>10} {'P&L':>10} {'Ret':>8} {'Sharpe':>8} {'MaxDD':>8}")
    for r in rows:
        print(f"  {r['period']:<8} {r['start_eq']:>10,.2f} {r['end_eq']:>10,.2f} "
              f"  {r['profit']:>+9,.2f}  {r['return_pct']:>+7.1%} {r['sharpe']:>+8.3f} {r['maxdd']:>+7.2%}")


def print_drawdowns(rows):
    print(f"  {'Start':<14} {'Trough':<14} {'End':<14} {'DD':>8} {'Days':>6} {'Peak$':>10} {'Trough$':>10}")
    for r in rows:
        end = r['dd_end'][:10] if r['dd_end'] != 'ongoing' else 'ongoing'
        print(f"  {r['dd_start'][:10]:<14} {r['trough'][:10]:<14} {end:<14} "
              f"{r['drawdown']:>+7.2%} {r['duration_days']:>6,d} {r['peak_eq']:>10,.2f} {r['trough_eq']:>10,.2f}")


# ─────────────────────────────────────────────────────────────────────────────
#  DUAL-MODE SIMULATOR
#  Normal:  trade geometry signal, Adaptive Y, K_long
#  Halted:  trade FLIPPED geometry signal (anti-collapse), flat Y, K_short
# ─────────────────────────────────────────────────────────────────────────────

def simulate_dual_mode(unit_normal: pd.Series,
                       unit_short: pd.Series,
                       K_long: float,
                       K_short: float,
                       dd_soft: float,
                       dd_stop: float,
                       y_floor: float,
                       cb_halt: float,
                       cb_resume: float,
                       cb_window_days: int):
    """Combine two pre-computed unit-return series with CB-based mode switching.

    unit_normal : hourly unit returns from the forward geometry signal (long mode)
    unit_short  : hourly unit returns from the INVERTED geometry signal (short mode)

    Both series were already simulated at size=1.0 per bar using simulate_unit_with_psi.
    Scaling (K_long / K_short) and Adaptive Y are applied here.

    The CB state machine uses the COMBINED equity curve's rolling drawdown.
    """
    assert len(unit_normal) == len(unit_short), 'length mismatch'
    window_bars = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq = INIT; peak_alltime = INIT; halted = False
    eq_vals = []; y_vals = []; mode_vals = []; cb_flags = []

    for bar_i, ts in enumerate(unit_normal.index):
        ur_normal = float(unit_normal.iloc[bar_i])
        ur_short  = float(unit_short.iloc[bar_i])

        # ── sliding-window rolling peak (for CB) ──
        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        # Drawdown for Adaptive Y  →  all-time peak
        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        # Drawdown for CB  →  rolling-window peak
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak, 1e-12))

        # CB state machine
        if not halted and cb_dd >= cb_halt:
            halted = True
        elif halted and cb_dd <= cb_resume:
            halted = False

        if halted:
            # Anti-collapse SHORT mode — apply K_short directly, no Y brake
            # (the leg's own returns are the hedge; we don't further brake it)
            y = K_short  # full K_short exposure, no Y multiplier
            r = float(ur_short) * y
            mode_vals.append('short')
        else:
            # Normal LONG mode — Adaptive Y brake
            if dd_aty <= dd_soft:
                y_aty = 1.0
            elif dd_aty >= dd_stop:
                y_aty = y_floor
            else:
                y_aty = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)
            y = y_aty
            r = K_long * y * float(ur_normal)
            mode_vals.append('long')

        r = max(r, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq)
        y_vals.append(y)
        cb_flags.append(int(halted))

    eqs  = pd.Series(eq_vals,  index=unit_normal.index)
    rets = eqs.pct_change().fillna(eqs.iloc[0] / INIT - 1.0)
    dd_s = (eqs - eqs.cummax()) / eqs.cummax()
    years = max((eqs.index[-1] - eqs.index[0]).days / 365.25, 1e-9)
    modes = pd.Series(mode_vals, index=unit_normal.index)
    return dict(
        eq         = eqs,
        modes      = modes,
        final      = float(eqs.iloc[-1]),
        cagr       = float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe     = float(np.sqrt(24 * 365.25) * rets.mean() / rets.std()) if rets.std() > 0 else 0.0,
        maxdd      = float(dd_s.min()),
        pct_halted = float(np.mean(cb_flags)),
        pct_short  = float((modes == 'short').mean()),
        n_trips    = int(sum(cb_flags[i] > cb_flags[i-1] for i in range(1, len(cb_flags)))),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL / POSITION BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_positions(df_1h, comp_raw, calib_mask, ohlc_all):
    common_start = comp_raw.dropna().index.min()
    common_end   = comp_raw.dropna().index.max()
    ohlc = ohlc_all[
        (ohlc_all.index >= common_start) &
        (ohlc_all.index <= common_end)
    ].copy()
    hours = ohlc.index

    idx       = df_1h.index
    train_1h  = (idx >= TRAIN_START) & (idx < TEST_START)
    train_idx = np.where(train_1h)[0]
    cm        = np.zeros(len(df_1h), dtype=bool)
    cm[train_idx[-CALIB_BARS:]] = True

    hourly_cal  = comp_raw[cm].abs().dropna()
    sig_shifted = comp_raw.shift(1).reindex(hours).fillna(0.0).values.astype(float)
    hth  = float(hourly_cal.quantile(BASE['q_hourly']))
    hpos = np.where(np.abs(sig_shifted) >= hth, np.sign(sig_shifted).astype(int), 0)
    hq   = _percentile_against(np.abs(sig_shifted), hourly_cal.values)

    daily_sig  = comp_raw.groupby(comp_raw.index.normalize()).last()
    all_days   = pd.Index(sorted(ohlc_all.index.normalize().unique()))
    calib_days = all_days[
        (all_days >= pd.Timestamp(TRAIN_START)) & (all_days < pd.Timestamp(TEST_START))
    ]
    ret_daily = ohlc_all['close'].pct_change().fillna(0.0).groupby(ohlc_all.index.normalize()).sum()
    daily_vol = float(ret_daily.reindex(calib_days).std())
    daily_cal = daily_sig.reindex(calib_days).abs().dropna()
    dth       = float(daily_cal.quantile(BASE['q_daily']))
    prev_days = hours.normalize() - pd.Timedelta(days=1)
    ds_vals   = daily_sig.reindex(prev_days).fillna(0.0).values.astype(float)
    dpos      = np.sign(ds_vals).astype(int)
    dactive   = np.abs(ds_vals) >= dth
    dq        = _percentile_against(np.abs(ds_vals), daily_cal.values)
    confirm   = (dactive & (dpos == hpos) & (hpos != 0)).astype(float)

    ret_h     = ohlc_all['close'].pct_change().fillna(0.0)
    rv        = ret_h.rolling(24, min_periods=12).std().shift(1)
    rv_cal    = rv[(rv.index >= pd.Timestamp(TRAIN_START)) &
                   (rv.index <  pd.Timestamp(TEST_START))].dropna()
    rv_h      = rv.reindex(hours).ffill().fillna(rv_cal.median())
    stress_rank  = _percentile_against(rv_h.values, rv_cal.values)
    target_vol   = float(rv_cal.median())
    vol_base     = (target_vol / rv_h.clip(lower=1e-8)).values

    unit0_arr, _ = simulate_unit_with_psi(
        ohlc['open'].values.astype(float),
        ohlc['high'].values.astype(float),
        ohlc['low'].values.astype(float),
        ohlc['close'].values.astype(float),
        hpos, dpos, dactive,
        np.ones(len(hours)),
        BASE['sl_mult'] * daily_vol,
        BASE['tp_mult'] * daily_vol,
    )
    unit0    = pd.Series(unit0_arr, index=hours)
    roll_mu  = unit0.rolling(240, min_periods=72).mean().shift(1).fillna(0.0)
    roll_sd  = unit0.rolling(240, min_periods=72).std().shift(1).replace(0, np.nan).fillna(unit0.std())
    q_quality    = 0.25 + 1.25 / (1.0 + np.exp(-np.clip(roll_mu / roll_sd * np.sqrt(24 * 365.25) * 0.50, -50, 50)))
    strength_raw = hq * (1.0 + dq) * (1.0 + confirm) / 4.0

    # Dynamic size multiplier
    strength_mult = np.clip(0.25 + DYN_STRENGTH_CAP * strength_raw, 0.25, DYN_STRENGTH_CAP)
    vol_mult      = np.clip(vol_base, 0.25, DYN_VOL_CAP)
    delta         = 1.2 - stress_rank
    gamma         = np.clip(np.sign(delta) * delta ** 2, 0.4, 1.3)
    size_mult     = np.clip(strength_mult * q_quality * vol_mult * gamma, 0.0, DYN_TOTAL_CAP)

    op = ohlc['open'].values.astype(float)
    hi = ohlc['high'].values.astype(float)
    lo = ohlc['low'].values.astype(float)
    cl = ohlc['close'].values.astype(float)

    return dict(
        hours      = hours,
        op = op, hi = hi, lo = lo, cl = cl,
        hpos       = hpos,
        dpos       = dpos,
        dactive    = dactive,
        daily_vol  = daily_vol,
        size_mult  = size_mult,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(BAR)
    print('  ANTI-COLLAPSE SHORT MODE SIMULATION')
    print('  Normal: geometry signal → LONG/SHORT, Adaptive Y, K=3')
    print('  Halted (CB fires): FLIP geometry signal → inverse trade, K_short')
    print(f'  CB: roll_window={CB_WINDOW_DAYS}d  halt={CB_HALT:.0%}  resume={CB_RESUME:.0%}')
    print(f'  K_short grid: {K_SHORT_GRID}')
    print(BAR)

    # ── Build geometry ──
    print('\n[1] Building geometry + OHLCV ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ohlc_all = fetch_futures_ohlcv()

    print('[2] Building signal + positions ...')
    p = build_positions(df_1h, comp_raw, calib_mask, ohlc_all)
    print(f'  daily vol (σ) : {p["daily_vol"]:.2%}   '
          f'σ-SL={BASE["sl_mult"]*p["daily_vol"]:.2%}  '
          f'σ-TP={BASE["tp_mult"]*p["daily_vol"]:.2%}')

    sl = BASE['sl_mult'] * p['daily_vol']
    tp = BASE['tp_mult'] * p['daily_vol']

    # ── Unit returns: forward signal (normal mode) ──
    print('[3] Running FORWARD unit simulation (normal-mode returns) ...')
    unit_fwd_arr, cnt_fwd = simulate_unit_with_psi(
        p['op'], p['hi'], p['lo'], p['cl'],
        p['hpos'], p['dpos'], p['dactive'],
        p['size_mult'], sl, tp,
    )
    unit_fwd = pd.Series(unit_fwd_arr, index=p['hours'])
    print(f'  entries={cnt_fwd["entries"]:,}  stops={cnt_fwd["stop"]:,}  '
          f'tp={cnt_fwd["tp"]:,}  signal_exits={cnt_fwd["signal_exit"]:,}')

    # ── Unit returns: INVERTED signal (anti-collapse / short mode) ──
    # Flip hpos so that wherever the normal signal says LONG, we go SHORT,
    # and wherever it says SHORT, we go LONG.  Position sizing uses the same
    # size_mult (momentum quality of the signal itself), but K_short is the
    # external lever swept below.
    print('[4] Running INVERTED unit simulation (short-mode returns) ...')
    hpos_inv = -p['hpos']          # flip all positions
    dpos_inv = -p['dpos']          # flip daily filter direction too
    unit_inv_arr, cnt_inv = simulate_unit_with_psi(
        p['op'], p['hi'], p['lo'], p['cl'],
        hpos_inv, dpos_inv, p['dactive'],
        p['size_mult'], sl, tp,
    )
    unit_inv = pd.Series(unit_inv_arr, index=p['hours'])
    print(f'  entries={cnt_inv["entries"]:,}  stops={cnt_inv["stop"]:,}  '
          f'tp={cnt_inv["tp"]:,}  signal_exits={cnt_inv["signal_exit"]:,}')

    # ── Quick sanity: standalone equity of each leg ──
    eq_fwd_base = adaptive_equity(unit_fwd, K=3.0,
                                   dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP,
                                   y_floor=DYN_Y_FLOOR)
    eq_inv_base = adaptive_equity(unit_inv, K=1.0,
                                   dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP,
                                   y_floor=DYN_Y_FLOOR)
    test_ts = pd.Timestamp(TEST_START)
    print(f'\n  FORWARD leg standalone (K=3, AdaptY): '
          f'FULL final=${eq_fwd_base["final"]:,.0f}  maxdd={eq_fwd_base["maxdd"]:+.1%}')
    inv_oos = eq_inv_base['eq'][eq_inv_base['eq'].index >= test_ts]
    print(f'  INVERTED leg standalone (K=1): '
          f'OOS final=${float(inv_oos.iloc[-1]):,.0f}  '
          f'maxdd={float((inv_oos - inv_oos.cummax()).div(inv_oos.cummax()).min()):+.1%}')

    # ── CB-cash baseline (from champion result) ──
    print('\n[5] CB-cash baseline (halt=18%, resume=13%, window=90d, K=3) ...')
    from simulate_circuit_breaker import adaptive_equity_cb
    cb_cash = adaptive_equity_cb(unit_fwd, K=3.0,
                                  dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP,
                                  y_floor=DYN_Y_FLOOR,
                                  cb_halt=CB_HALT, cb_resume=CB_RESUME,
                                  cb_window_days=CB_WINDOW_DAYS)

    # ── Sweep K_short with dual-mode simulator ──
    print('[6] Sweeping K_short with dual-mode (normal + anti-collapse short) ...')
    dm_results = {}
    for K_short in K_SHORT_GRID:
        res = simulate_dual_mode(
            unit_fwd, unit_inv,
            K_long=3.0, K_short=K_short,
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
            cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window_days=CB_WINDOW_DAYS,
        )
        dm_results[K_short] = res
        eq_oos = res['eq'][res['eq'].index >= test_ts]
        m_oos  = equity_metrics(eq_oos)
        print(f'  K_short={K_short}  OOS: final=${m_oos["final"]:>10,.2f}  '
              f'ret={m_oos["return_pct"]:>+7.1%}  sharpe={m_oos["sharpe"]:>+5.2f}  '
              f'maxdd={m_oos["maxdd"]:>+6.1%}  calmar={m_oos["calmar"]:>+6.3f}  '
              f'short%={res["pct_short"]:.1%}  trips={res["n_trips"]}')

    # ── Best by OOS Calmar ──
    best_K = max(K_SHORT_GRID,
                 key=lambda k: equity_metrics(
                     dm_results[k]['eq'][dm_results[k]['eq'].index >= test_ts])['calmar'])
    print(f'\n  Best K_short by OOS Calmar: {best_K}')

    # ── Detailed output for best dual-mode ──
    best = dm_results[best_K]
    eq_b = best['eq']
    test_mask  = eq_b.index >= test_ts
    train_mask = (eq_b.index >= pd.Timestamp(TRAIN_START)) & (eq_b.index < test_ts)

    print()
    print(BAR)
    print(f'  DUAL-MODE  K_long=3  K_short={best_K}')
    print(f'  CB: window={CB_WINDOW_DAYS}d  halt={CB_HALT:.0%}  resume={CB_RESUME:.0%}')
    print(SEP)
    for m in [equity_metrics(eq_b,             f'DualMode K_s={best_K} — FULL'),
              equity_metrics(eq_b[train_mask],  f'DualMode K_s={best_K} — TRAIN'),
              equity_metrics(eq_b[test_mask],   f'DualMode K_s={best_K} — TEST (OOS)')]:
        print(); print_metrics(m)

    print(f'\n  pct_short={best["pct_short"]:.1%}  '
          f'pct_long={(1 - best["pct_short"]):.1%}  '
          f'cb_trips={best["n_trips"]}')

    print('\n  Yearly:')
    print_yearly(period_table(eq_b, 'Y'))

    print('\n  Top drawdowns:')
    print_drawdowns(drawdown_periods(eq_b))

    # ── OOS comparison table ──
    print()
    print(BAR)
    print('  OOS COMPARISON  (2023 → today)')
    print(f'  {"Strategy":<46} {"Final$":>10} {"Return":>8} {"CAGR":>8} '
          f'{"Sharpe":>8} {"MaxDD":>8} {"Calmar":>8} {"Short%":>7} {"Trips":>6}')
    print(f'  {"-"*46} {"-"*10} {"-"*8} {"-"*8} {"-"*8} {"-"*8} {"-"*8} {"-"*7} {"-"*6}')

    def oos_row(eq_oos, label, pct_short=0.0, n_trips=0):
        m = equity_metrics(eq_oos, label)
        print(f'  {label:<46} {m["final"]:>10,.2f} {m["return_pct"]:>+7.1%} '
              f'{m["cagr"]:>+7.2%} {m["sharpe"]:>+8.3f} {m["maxdd"]:>+7.2%} '
              f'{m["calmar"]:>+8.3f} {pct_short:>6.1%} {n_trips:>6}')
        return m

    eq3_oos = adaptive_equity(unit_fwd, K=3.0, dd_soft=DYN_DD_SOFT,
                               dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR)
    eq5_oos = adaptive_equity(unit_fwd, K=5.0, dd_soft=DYN_DD_SOFT,
                               dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR)
    oos_row(eq3_oos['eq'][eq3_oos['eq'].index >= test_ts], 'Baseline K=3  (no CB)')
    oos_row(eq5_oos['eq'][eq5_oos['eq'].index >= test_ts], 'Baseline K=5  (no CB)')

    # CB-cash champion
    cb_eq_oos = cb_cash['eq'][cb_cash['eq'].index >= test_ts]
    cb_oos_mode = cb_cash['cb'][cb_cash['cb'].index >= test_ts]
    oos_row(cb_eq_oos, f'CB-cash  halt={CB_HALT:.0%}  K=3',
            pct_short=float(cb_oos_mode.mean()), n_trips=int(sum(
                cb_oos_mode.values[i] > cb_oos_mode.values[i-1]
                for i in range(1, len(cb_oos_mode)))))

    for K_short in K_SHORT_GRID:
        res    = dm_results[K_short]
        eq_oos = res['eq'][res['eq'].index >= test_ts]
        m_oos  = res['modes'][res['modes'].index >= test_ts]
        oos_row(eq_oos,
                f'CB-short K_long=3  K_short={K_short}',
                pct_short=float((m_oos == 'short').mean()),
                n_trips=res['n_trips'])

    print(f'\n  elapsed: {time.time()-t0:.1f}s')
    print(BAR)

    # ── Save ──
    payload = dict(
        config = dict(
            cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window_days=CB_WINDOW_DAYS,
            K_long=DYN_K, K_short_grid=K_SHORT_GRID,
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        ),
        unit_fwd_counts = cnt_fwd,
        unit_inv_counts = cnt_inv,
        results = {
            str(K_short): dict(
                K_short    = K_short,
                full       = equity_metrics(dm_results[K_short]['eq']),
                train      = equity_metrics(dm_results[K_short]['eq'][
                                 dm_results[K_short]['eq'].index < test_ts]),
                test       = equity_metrics(dm_results[K_short]['eq'][
                                 dm_results[K_short]['eq'].index >= test_ts]),
                yearly     = period_table(dm_results[K_short]['eq'], 'Y'),
                drawdowns  = drawdown_periods(dm_results[K_short]['eq']),
                pct_short  = dm_results[K_short]['pct_short'],
                n_trips    = dm_results[K_short]['n_trips'],
            )
            for K_short in K_SHORT_GRID
        },
        best_K_short = best_K,
        elapsed      = time.time() - t0,
    )
    OUT.write_text(json.dumps(payload, indent=2, default=float))
    print(f'\n  Saved → {OUT}')


if __name__ == '__main__':
    main()
