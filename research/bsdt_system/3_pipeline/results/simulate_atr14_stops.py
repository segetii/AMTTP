"""ATR14 Stop-Loss / Take-Profit Simulation.

Replaces the fixed calibration-sigma stop with Wilder's 14-period ATR:
    SL = entry ± ATR_SL_MULT × ATR14    (default 2× ATR)
    TP = entry ± ATR_TP_MULT × ATR14    (default 3× ATR  →  1.5 : 1 R/R)

ATR14 is computed bar-by-bar from hourly OHLCV and shifted 1 bar so the stop
distance at entry time t uses only data known strictly before bar t.

Comparison matrix (OOS  2023 → today):
  ┌──────────────────────────────┬──────────┬──────────┐
  │  Strategy                    │ K = 3    │ K = 5    │
  ├──────────────────────────────┼──────────┼──────────┤
  │  Sigma stops (v59 baseline)  │  ✓       │  ✓       │
  │  ATR14 stops (this script)   │  ✓       │  ✓       │
  └──────────────────────────────┴──────────┴──────────┘
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS
from test_daily_geometry_stop_tp_ohlc   import build_daily_geometry, fetch_futures_ohlcv
from test_psi_adaptive_y                import BASE, simulate_unit_with_psi
from simulate_adaptive_y_drawdown_brake import adaptive_equity
from test_dynamic_profit_sizing         import _percentile_against

INIT         = 1_000.0
RT_COST      = 2.0  / 1e4
FUND_DAY     = 0.5  / 1e4
RT_HOURLY    = RT_COST
FUND_HOURLY  = FUND_DAY / 24.0

# Champion dynamic sizing config
DYN_K            = 3.0
DYN_STRENGTH_CAP = 2.5
DYN_VOL_CAP      = 3.0
DYN_GAMMA_MODE   = 'convex'
DYN_TOTAL_CAP    = 2.0
DYN_DD_SOFT      = 0.05
DYN_DD_STOP      = 0.20
DYN_Y_FLOOR      = 0.25

# ATR14 parameters  (standard Wilder method)
ATR_PERIOD  = 14
ATR_SL_MULT = 2.0    # SL = 2 × ATR14
ATR_TP_MULT = 3.0    # TP = 3 × ATR14  →  1.5 : 1 reward/risk

OUT = Path(OUT_DIR) / 'simulation_atr14_stops.json'
BAR = '=' * 110
SEP = '-' * 110


# ─────────────────────────────────────────────────────────────────────────────
#  METRICS HELPERS  (identical to v59 file)
# ─────────────────────────────────────────────────────────────────────────────

def equity_metrics(eq: pd.Series, label: str = '') -> dict:
    r     = eq.pct_change().fillna(eq.iloc[0] / INIT - 1.0)
    dd    = (eq - eq.cummax()) / eq.cummax()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    calmar = float((eq.iloc[-1] / INIT) ** (1 / years) - 1) / max(abs(float(dd.min())), 1e-9)
    return dict(
        label      = label,
        init       = float(eq.iloc[0]),
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


def drawdown_periods(eq: pd.Series, top_n: int = 8) -> list[dict]:
    peak = eq.cummax()
    dd   = (eq - peak) / peak
    rows = []
    in_dd = False; start = None; peak_val = None
    for ts, val in dd.items():
        if not in_dd and val < -1e-4:
            in_dd = True; start = ts; peak_val = float(peak[ts])
        elif in_dd and val >= -1e-4:
            trough_i  = dd[start:ts].idxmin()
            trough_dd = float(dd[trough_i])
            rows.append(dict(dd_start=str(start), trough=str(trough_i),
                             dd_end=str(ts), drawdown=trough_dd,
                             peak_eq=peak_val, trough_eq=float(eq[trough_i]),
                             duration_days=int((ts - start).days)))
            in_dd = False
    if in_dd:
        trough_i  = dd[start:].idxmin()
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
#  ATR14 TRADE SIMULATOR
#  Identical logic to simulate_unit_with_psi but sl/tp are per-bar arrays.
# ─────────────────────────────────────────────────────────────────────────────

def simulate_unit_atr14(op, hi, lo, cl,
                         hpos_arr, dpos_arr, dactive_arr,
                         psi_y, sl_arr, tp_arr):
    """Per-bar ATR14 stop/TP simulation.

    sl_arr[i] and tp_arr[i] are fractional return distances from entry price.
    They are only read at the moment of entry (index i), then the resulting
    price levels are held for the life of the position.
    """
    n   = len(op)
    ret = np.zeros(n, dtype=float)
    pos = 0.0; size = 1.0; entry = 0.0; stop_price = 0.0; take_price = 0.0
    counts = dict(entries=0, exits=0, flips=0, longs=0, shorts=0,
                  stop=0, tp=0, signal_exit=0, close_end=0,
                  skipped_daily_filter=0, psi_blocked=0,
                  active_hours=0, avg_psi_y=0.0)
    psi_sizes = []

    for i in range(n):
        hpos    = hpos_arr[i];  hactive = hpos != 0
        dpos_i  = dpos_arr[i];  dact_i  = dactive_arr[i]
        scale   = 1.0

        # daily context filter (identical to simulate_unit_with_psi)
        if hactive:
            if dact_i and hpos == dpos_i:       scale = 1.0
            elif dact_i and hpos != dpos_i:
                hactive = False; hpos = 0;      counts['skipped_daily_filter'] += 1
            else:                               scale = 0.5
        if hactive:
            scale *= psi_y[i]
            if scale <= 1e-12:
                hactive = False; hpos = 0;      counts['psi_blocked'] += 1

        # ── manage open position ──
        if pos != 0:
            counts['active_hours'] += 1
            exit_ret = None; reason = None
            if pos > 0:
                stop_hit = lo[i] <= stop_price
                tp_hit   = hi[i] >= take_price
                if stop_hit:       exit_ret = stop_price / entry - 1; reason = 'stop'
                elif tp_hit:       exit_ret = take_price / entry - 1; reason = 'tp'
            else:
                stop_hit = hi[i] >= stop_price
                tp_hit   = lo[i] <= take_price
                if stop_hit:       exit_ret = entry / stop_price - 1; reason = 'stop'
                elif tp_hit:       exit_ret = entry / take_price - 1; reason = 'tp'
            # signal flip exit
            if exit_ret is None and hactive and hpos == -pos:
                exit_ret = (op[i] / entry - 1) if pos > 0 else (entry / op[i] - 1)
                reason   = 'signal_exit'; counts['flips'] += 1
            if exit_ret is not None:
                ret[i] += size * (exit_ret - RT_COST)
                counts[reason] += 1; counts['exits'] += 1
                pos = 0; size = 1; entry = 0
            else:
                ret[i] += -size * FUND_HOURLY

        # ── open new position ──
        if pos == 0 and hactive:
            sl = float(sl_arr[i]); tp = float(tp_arr[i])
            # guard against degenerate ATR values
            sl = max(sl, 1e-4); tp = max(tp, 1e-4)
            pos   = float(hpos); size = float(scale); entry = op[i]
            psi_sizes.append(float(psi_y[i]))
            if pos > 0:
                stop_price = entry * (1.0 - sl)
                take_price = entry * (1.0 + tp)
                counts['longs'] += 1
            else:
                stop_price = entry * (1.0 + sl)
                take_price = entry * (1.0 - tp)
                counts['shorts'] += 1
            counts['entries'] += 1

    # close at end-of-series
    if pos != 0:
        i     = n - 1
        gross = (cl[i] / entry - 1) if pos > 0 else (entry / cl[i] - 1)
        ret[i] += size * (gross - RT_COST)
        counts['close_end'] += 1; counts['exits'] += 1

    counts['avg_psi_y'] = float(np.mean(psi_sizes)) if psi_sizes else 0.0
    return ret, counts


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL / POSITION BUILDER  (mirrors simulate_enterprise_v59_full.py)
# ─────────────────────────────────────────────────────────────────────────────

def build_signal_and_positions(df_1h, comp_raw, calib_mask, ohlc_all):
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
    ret_daily  = ohlc_all['close'].pct_change().fillna(0.0).groupby(ohlc_all.index.normalize()).sum()
    daily_vol  = float(ret_daily.reindex(calib_days).std())
    daily_cal  = daily_sig.reindex(calib_days).abs().dropna()
    dth        = float(daily_cal.quantile(BASE['q_daily']))
    prev_days  = hours.normalize() - pd.Timedelta(days=1)
    ds_vals    = daily_sig.reindex(prev_days).fillna(0.0).values.astype(float)
    dpos       = np.sign(ds_vals).astype(int)
    dactive    = np.abs(ds_vals) >= dth
    dq         = _percentile_against(np.abs(ds_vals), daily_cal.values)
    confirm    = (dactive & (dpos == hpos) & (hpos != 0)).astype(float)

    # vol / stress
    ret_h       = ohlc_all['close'].pct_change().fillna(0.0)
    rv          = ret_h.rolling(24, min_periods=12).std().shift(1)
    rv_cal      = rv[(rv.index >= pd.Timestamp(TRAIN_START)) &
                     (rv.index <  pd.Timestamp(TEST_START))].dropna()
    rv_h        = rv.reindex(hours).ffill().fillna(rv_cal.median())
    stress_rank = _percentile_against(rv_h.values, rv_cal.values)
    target_vol  = float(rv_cal.median())
    vol_base    = (target_vol / rv_h.clip(lower=1e-8)).values

    # base unit (sigma stops) — used for quality signal build
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
    q_quality = 0.25 + 1.25 / (1.0 + np.exp(-np.clip(roll_mu / roll_sd * np.sqrt(24 * 365.25) * 0.50, -50, 50)))
    strength_raw = hq * (1.0 + dq) * (1.0 + confirm) / 4.0

    # ── ATR14 per bar (causal: shift 1 so entry at bar t uses ATR from bars < t) ──
    tr = pd.concat([
        ohlc['high'] - ohlc['low'],
        (ohlc['high'] - ohlc['close'].shift(1)).abs(),
        (ohlc['low']  - ohlc['close'].shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr14     = tr.ewm(span=ATR_PERIOD, adjust=False).mean().shift(1)
    # Express as fraction of open price at entry bar (causal open is the entry price)
    # Clip to sensible bounds: [0.1%, 20%] per side
    atr14_open = atr14 / ohlc['open']
    sl_atr = (ATR_SL_MULT * atr14_open).clip(lower=0.001, upper=0.20).fillna(
                BASE['sl_mult'] * daily_vol).values
    tp_atr = (ATR_TP_MULT * atr14_open).clip(lower=0.001, upper=0.30).fillna(
                BASE['tp_mult'] * daily_vol).values

    return dict(
        hours        = hours,
        ohlc         = ohlc,
        ohlc_all     = ohlc_all,
        op           = ohlc['open'].values.astype(float),
        hi           = ohlc['high'].values.astype(float),
        lo           = ohlc['low'].values.astype(float),
        cl           = ohlc['close'].values.astype(float),
        hpos         = hpos,
        dpos         = dpos,
        dactive      = dactive,
        daily_vol    = daily_vol,
        unit0        = unit0,
        hth          = hth,
        dth          = dth,
        strength_raw = strength_raw,
        q_quality    = q_quality,
        vol_base     = vol_base,
        stress_rank  = stress_rank,
        calib_days   = calib_days,
        sl_atr       = sl_atr,
        tp_atr       = tp_atr,
        atr14_mean   = float(atr14.dropna().mean()),
        atr14_median = float(atr14.dropna().median()),
        sl_atr_mean  = float(np.nanmean(sl_atr)),
        tp_atr_mean  = float(np.nanmean(tp_atr)),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  STRATEGY RUNNERS
# ─────────────────────────────────────────────────────────────────────────────

def _dynamic_size_mult(p):
    strength_mult = np.clip(0.25 + DYN_STRENGTH_CAP * p['strength_raw'], 0.25, DYN_STRENGTH_CAP)
    vol_mult      = np.clip(p['vol_base'], 0.25, DYN_VOL_CAP)
    delta         = 1.2 - p['stress_rank']
    gamma         = np.clip(np.sign(delta) * delta ** 2, 0.4, 1.3)
    return np.clip(strength_mult * p['q_quality'] * vol_mult * gamma, 0.0, DYN_TOTAL_CAP)


def run_sigma_dynamic(p: dict, K: float) -> dict:
    """Sigma-based stops — v59 baseline (uses simulate_unit_with_psi)."""
    size_mult = _dynamic_size_mult(p)
    unit_arr, counts = simulate_unit_with_psi(
        p['op'], p['hi'], p['lo'], p['cl'],
        p['hpos'], p['dpos'], p['dactive'], size_mult,
        BASE['sl_mult'] * p['daily_vol'],
        BASE['tp_mult'] * p['daily_vol'],
    )
    unit = pd.Series(unit_arr, index=p['hours'])
    y_result = adaptive_equity(unit, K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR)
    eq = y_result['eq']
    test_mask  = unit.index >= pd.Timestamp(TEST_START)
    train_mask = (unit.index >= pd.Timestamp(TRAIN_START)) & (unit.index < pd.Timestamp(TEST_START))
    return dict(
        stop_method = 'sigma',
        K           = K,
        sl_param    = BASE['sl_mult'] * p['daily_vol'],
        tp_param    = BASE['tp_mult'] * p['daily_vol'],
        full        = equity_metrics(eq,            label=f'Sigma K={K} — FULL'),
        train       = equity_metrics(eq[train_mask], label=f'Sigma K={K} — TRAIN'),
        test        = equity_metrics(eq[test_mask],  label=f'Sigma K={K} — TEST (OOS)'),
        yearly      = period_table(eq, 'Y'),
        drawdowns   = drawdown_periods(eq),
        counts      = counts,
        avg_y       = float(y_result['avg_y']),
        min_y       = float(y_result['min_y']),
        pct_cut     = float(y_result['pct_cut']),
    )


def run_atr14_dynamic(p: dict, K: float) -> dict:
    """ATR14 stops — new method (uses simulate_unit_atr14)."""
    size_mult = _dynamic_size_mult(p)
    unit_arr, counts = simulate_unit_atr14(
        p['op'], p['hi'], p['lo'], p['cl'],
        p['hpos'], p['dpos'], p['dactive'], size_mult,
        p['sl_atr'], p['tp_atr'],
    )
    unit = pd.Series(unit_arr, index=p['hours'])
    y_result = adaptive_equity(unit, K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR)
    eq = y_result['eq']
    test_mask  = unit.index >= pd.Timestamp(TEST_START)
    train_mask = (unit.index >= pd.Timestamp(TRAIN_START)) & (unit.index < pd.Timestamp(TEST_START))
    return dict(
        stop_method = 'ATR14',
        K           = K,
        atr_sl_mult = ATR_SL_MULT,
        atr_tp_mult = ATR_TP_MULT,
        rr_ratio    = ATR_TP_MULT / ATR_SL_MULT,
        atr14_mean  = p['atr14_mean'],
        atr14_median= p['atr14_median'],
        sl_atr_mean = float(np.nanmean(p['sl_atr'])),
        tp_atr_mean = float(np.nanmean(p['tp_atr'])),
        full        = equity_metrics(eq,            label=f'ATR14 K={K} — FULL'),
        train       = equity_metrics(eq[train_mask], label=f'ATR14 K={K} — TRAIN'),
        test        = equity_metrics(eq[test_mask],  label=f'ATR14 K={K} — TEST (OOS)'),
        yearly      = period_table(eq, 'Y'),
        drawdowns   = drawdown_periods(eq),
        counts      = counts,
        avg_y       = float(y_result['avg_y']),
        min_y       = float(y_result['min_y']),
        pct_cut     = float(y_result['pct_cut']),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def _print_section(res):
    label = f"{res['stop_method']} stops  K={res['K']}"
    print(f'\n{BAR}')
    print(f'  {label}')
    print(SEP)
    for layer in [res['full'], res['train'], res['test']]:
        print_metrics(layer); print()
    print(f"  avg_Y={res['avg_y']:.3f}  min_Y={res['min_y']:.3f}  pct_time_braked={res['pct_cut']:.1%}")
    c = res['counts']
    print(f"  exits: stop={c['stop']:,}  tp={c['tp']:,}  "
          f"signal_exit={c['signal_exit']:,}  close_end={c['close_end']:,}")
    if res['stop_method'] == 'ATR14':
        print(f"  ATR14: SL={res['atr_sl_mult']}× ATR  TP={res['atr_tp_mult']}× ATR  "
              f"(R:R = 1:{res['rr_ratio']:.1f})")
        print(f"  mean sl_return={res['sl_atr_mean']:.2%}  mean tp_return={res['tp_atr_mean']:.2%}")
    else:
        print(f"  sigma SL={res['sl_param']:.2%}  sigma TP={res['tp_param']:.2%}")
    print(f'\n  Yearly:')
    print_yearly(res['yearly'])
    print(f'\n  Top drawdowns:')
    print_drawdowns(res['drawdowns'])


def main():
    t0 = time.time()
    print(BAR)
    print('  ATR14 STOP/TP SIMULATION  (Wilder 14-period Average True Range)')
    print('  BSDT Geometry (z(E7)+z(dG)+z(E6)+z(dT))/4 — 4-channel — dynamic K=3 and K=5')
    print(f'  Train: {TRAIN_START} → {TEST_START}   OOS: {TEST_START} → today')
    print(f'  ATR params: SL={ATR_SL_MULT}×ATR14  TP={ATR_TP_MULT}×ATR14  '
          f'(1:{ATR_TP_MULT/ATR_SL_MULT:.1f} R:R)  period={ATR_PERIOD}h')
    print(BAR)

    print('\n[1] Building geometry + OHLCV ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ohlc_all = fetch_futures_ohlcv()
    print(f'  geometry bars : {len(df_1h):,}  ({df_1h.index[0]} → {df_1h.index[-1]})')
    print(f'  OHLCV bars    : {len(ohlc_all):,}  ({ohlc_all.index[0]} → {ohlc_all.index[-1]})')

    print('\n[2] Building signal + ATR14 arrays ...')
    p = build_signal_and_positions(df_1h, comp_raw, calib_mask, ohlc_all)
    print(f'  common hours     : {len(p["hours"]):,}')
    print(f'  daily vol (σ)    : {p["daily_vol"]:.2%}    ← sigma-stop distance at sl_mult=1.0')
    print(f'  ATR14 mean       : {p["atr14_mean"]:.4f}   (raw price units)')
    print(f'  ATR14 mean SL %  : {p["sl_atr_mean"]:.2%}  (= {ATR_SL_MULT}×ATR14/open)')
    print(f'  ATR14 mean TP %  : {p["tp_atr_mean"]:.2%}  (= {ATR_TP_MULT}×ATR14/open)')

    # ── run all four strategies ──────────────────────────────────────────────
    print('\n[3] Running sigma baseline K=3 (v59 reference)...')
    sig3 = run_sigma_dynamic(p, K=3.0)

    print('[4] Running ATR14 stops K=3 ...')
    atr3 = run_atr14_dynamic(p, K=3.0)

    print('[5] Running sigma baseline K=5 ...')
    sig5 = run_sigma_dynamic(p, K=5.0)

    print('[6] Running ATR14 stops K=5 ...')
    atr5 = run_atr14_dynamic(p, K=5.0)

    elapsed = time.time() - t0

    # ── full detail sections ─────────────────────────────────────────────────
    _print_section(sig3)
    _print_section(atr3)
    _print_section(sig5)
    _print_section(atr5)

    # ── side-by-side OOS comparison ──────────────────────────────────────────
    print(f'\n{BAR}')
    print('  OOS TEST COMPARISON  (2023 → today)')
    print(f'  ATR14: {ATR_SL_MULT}×SL / {ATR_TP_MULT}×TP   vs   Sigma: '
          f'{BASE["sl_mult"]}×σ SL / {BASE["tp_mult"]}×σ TP')
    print(SEP)
    hdr = f"  {'Strategy':<36} {'Final$':>10} {'Return':>8} {'CAGR':>8} {'Sharpe':>8} {'MaxDD':>8} {'Calmar':>8} {'Stops':>8} {'TPs':>8}"
    print(hdr)
    print(f"  {'-'*36} {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for nm, res in [('Sigma stops  K=3  (v59 baseline)', sig3),
                    ('ATR14 stops  K=3  (this script)',  atr3),
                    ('Sigma stops  K=5',                 sig5),
                    ('ATR14 stops  K=5',                 atr5)]:
        m   = res['test']
        c   = res['counts']
        print(f"  {nm:<36} {m['final']:>10,.2f} {m['return_pct']:>+7.1%} "
              f"{m['cagr']:>+7.2%} {m['sharpe']:>+8.3f} "
              f"{m['maxdd']:>+7.2%} {m['calmar']:>+8.3f} "
              f"{c['stop']:>8,d} {c['tp']:>8,d}")

    print(f'\n  elapsed: {elapsed:.1f}s')
    print(BAR)

    # ── save ─────────────────────────────────────────────────────────────────
    def _ser(d):
        return {k: v for k, v in d.items() if k != 'counts'}

    output = dict(
        generated_at_utc = pd.Timestamp.utcnow().isoformat(),
        atr_params       = dict(period=ATR_PERIOD, sl_mult=ATR_SL_MULT, tp_mult=ATR_TP_MULT),
        sigma_params     = dict(sl_mult=BASE['sl_mult'], tp_mult=BASE['tp_mult']),
        atr14_mean       = p['atr14_mean'],
        atr14_median     = p['atr14_median'],
        sl_atr_mean_pct  = p['sl_atr_mean'],
        tp_atr_mean_pct  = p['tp_atr_mean'],
        sigma_dynamic_k3 = _ser(sig3),
        atr14_dynamic_k3 = _ser(atr3),
        sigma_dynamic_k5 = _ser(sig5),
        atr14_dynamic_k5 = _ser(atr5),
        elapsed_seconds  = elapsed,
    )
    OUT.write_text(json.dumps(output, indent=2, default=float))
    print(f'\n  Saved → {OUT}')


if __name__ == '__main__':
    main()
