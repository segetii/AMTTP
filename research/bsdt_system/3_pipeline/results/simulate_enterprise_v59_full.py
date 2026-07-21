"""Enterprise-grade full backtest simulation — v58/v59 geometry + dynamic sizing + adaptive Y.

Evaluation Layers
-----------------
1.  BASE UNIT (K=1, no sizing multiplier)
    Raw hourly signal quality in pure unit-return space.

2.  FIXED LEVERAGE (K=2 expert / K=3 research)
    Classic constant-leverage equity curve.

3.  DYNAMIC SIZING + ADAPTIVE Y  (champion config)
    L_t = K × S_strength × Q_quality × V_vol × Γ_gamma × Y_drawdown
    Best safe config from test_dynamic_profit_sizing.py sweep:
      K=3, strength_cap=2.5, vol_cap=3.0, gamma=convex, total_cap=2.0
    Adaptive Y: dd_soft=5%, dd_stop=20%, y_floor=25%

Reports
-------
- Full period + train + test sub-period metrics for every layer
- Yearly and quarterly equity table
- Trade count breakdown (long/short/stop/tp/close)
- Top-10 drawdown periods
- Running Sharpe by year
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS
from test_daily_geometry_stop_tp_ohlc import build_daily_geometry, fetch_futures_ohlcv
from test_psi_adaptive_y import BASE, simulate_unit_with_psi
from simulate_adaptive_y_drawdown_brake import adaptive_equity
from test_dynamic_profit_sizing import _percentile_against

INIT          = 1_000.0
RT_COST       = 2.0 / 1e4      # 2 bps round-trip (maker)
FUND_DAY      = 0.5 / 1e4      # 0.5 bps daily funding
RT_HOURLY     = RT_COST        # one trip per hourly trade is conservative
FUND_HOURLY   = FUND_DAY / 24.0

# Champion dynamic sizing config (from grid sweep)
DYN_K             = 3.0
DYN_STRENGTH_CAP  = 2.5
DYN_VOL_CAP       = 3.0
DYN_GAMMA_MODE    = 'convex'
DYN_TOTAL_CAP     = 2.0
DYN_DD_SOFT       = 0.05
DYN_DD_STOP       = 0.20
DYN_Y_FLOOR       = 0.25

OUT = Path(OUT_DIR) / 'simulation_enterprise_v59_full.json'

BAR  = '=' * 110
SEP  = '-' * 110


# ─────────────────────────────────────────────────────────────────────────────
#  METRICS HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def equity_metrics(eq: pd.Series, label: str = '') -> dict:
    r = eq.pct_change().fillna(eq.iloc[0] / INIT - 1.0)
    dd = (eq - eq.cummax()) / eq.cummax()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    calmar = float((eq.iloc[-1] / INIT) ** (1 / years) - 1) / max(abs(float(dd.min())), 1e-9)
    return dict(
        label        = label,
        init         = float(eq.iloc[0]),
        final        = float(eq.iloc[-1]),
        profit       = float(eq.iloc[-1] - INIT),
        return_pct   = float(eq.iloc[-1] / INIT - 1.0),
        cagr         = float((eq.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe       = float(np.sqrt(24 * 365.25) * r.mean() / r.std()) if r.std() > 0 else 0.0,
        maxdd        = float(dd.min()),
        calmar       = calmar,
        start        = str(eq.index[0]),
        end          = str(eq.index[-1]),
    )


def period_table(eq: pd.Series, freq: str) -> list[dict]:
    rows = []
    for dt, s in eq.groupby(pd.Grouper(freq=freq)):
        if len(s) < 2:
            continue
        r  = s.pct_change().dropna()
        dd = (s - s.cummax()) / s.cummax()
        rows.append(dict(
            period      = str(dt.date()),
            start_eq    = round(float(s.iloc[0]),  2),
            end_eq      = round(float(s.iloc[-1]), 2),
            profit      = round(float(s.iloc[-1] - s.iloc[0]), 2),
            return_pct  = round(float(s.iloc[-1] / s.iloc[0] - 1.0), 4),
            sharpe      = round(float(np.sqrt(24 * 365.25) * r.mean() / r.std()), 3) if r.std() > 0 else 0.0,
            maxdd       = round(float(dd.min()), 4),
        ))
    return rows


def drawdown_periods(eq: pd.Series, top_n: int = 10) -> list[dict]:
    """Identify the N worst drawdown troughs and their recovery times."""
    peak = eq.cummax()
    dd   = (eq - peak) / peak
    rows = []
    in_dd = False; start = None; peak_val = None
    for ts, val in dd.items():
        if not in_dd and val < -1e-4:
            in_dd    = True
            start    = ts
            peak_val = float(peak[ts])
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
        trough_dd = float(dd[trough_i])
        rows.append(dict(dd_start=str(start), trough=str(trough_i),
                         dd_end='ongoing', drawdown=trough_dd,
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


def print_yearly(rows: list[dict]):
    print(f"  {'Year':<8} {'Start':>10} {'End':>10} {'P&L':>10} {'Ret':>8} {'Sharpe':>8} {'MaxDD':>8}")
    for r in rows:
        print(f"  {r['period']:<8} {r['start_eq']:>10,.2f} {r['end_eq']:>10,.2f} "
              f"  {r['profit']:>+9,.2f}  {r['return_pct']:>+7.1%} {r['sharpe']:>+8.3f} {r['maxdd']:>+7.2%}")


def print_drawdowns(rows: list[dict]):
    print(f"  {'Start':<14} {'Trough':<14} {'End':<14} {'DD':>8} {'Days':>6} {'Peak$':>10} {'Trough$':>10}")
    for r in rows:
        end = r['dd_end'][:10] if r['dd_end'] != 'ongoing' else 'ongoing'
        print(f"  {r['dd_start'][:10]:<14} {r['trough'][:10]:<14} {end:<14} "
              f"{r['drawdown']:>+7.2%} {r['duration_days']:>6,d} {r['peak_eq']:>10,.2f} {r['trough_eq']:>10,.2f}")


# ─────────────────────────────────────────────────────────────────────────────
#  CORE SIMULATION
# ─────────────────────────────────────────────────────────────────────────────

def build_signal_and_positions(df_1h, comp_raw, calib_mask, ohlc_all):
    """Return aligned hourly arrays ready for simulate_unit_with_psi."""
    # Filter to common window where both geometry and OHLC exist.
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

    hourly_cal = comp_raw[cm].abs().dropna()
    # Use comp.shift(1) — matches backtest (no intra-bar look-ahead).
    sig_shifted = comp_raw.shift(1).reindex(hours).fillna(0.0).values.astype(float)
    hth = float(hourly_cal.quantile(BASE['q_hourly']))
    hpos = np.where(np.abs(sig_shifted) >= hth,
                    np.sign(sig_shifted).astype(int), 0)
    hq   = _percentile_against(np.abs(sig_shifted), hourly_cal.values)

    daily_sig  = comp_raw.groupby(comp_raw.index.normalize()).last()
    all_days   = pd.Index(sorted(ohlc_all.index.normalize().unique()))
    calib_days = all_days[
        (all_days >= pd.Timestamp(TRAIN_START)) & (all_days <  pd.Timestamp(TEST_START))
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

    # Volatility stress / gamma proxy
    ret_h    = ohlc_all['close'].pct_change().fillna(0.0)
    rv       = ret_h.rolling(24, min_periods=12).std().shift(1)
    rv_cal   = rv[(rv.index >= pd.Timestamp(TRAIN_START)) &
                  (rv.index <  pd.Timestamp(TEST_START))].dropna()
    rv_h     = rv.reindex(hours).ffill().fillna(rv_cal.median())
    stress_rank  = _percentile_against(rv_h.values, rv_cal.values)
    target_vol   = float(rv_cal.median())
    vol_base     = (target_vol / rv_h.clip(lower=1e-8)).values

    # Quality (rolling Sharpe of the base unit, forward-free)
    unit0_arr, _  = simulate_unit_with_psi(
        ohlc['open'].values.astype(float),
        ohlc['high'].values.astype(float),
        ohlc['low'].values.astype(float),
        ohlc['close'].values.astype(float),
        hpos, dpos, dactive,
        np.ones(len(hours)),
        BASE['sl_mult'] * daily_vol,
        BASE['tp_mult'] * daily_vol,
    )
    unit0  = pd.Series(unit0_arr, index=hours)
    roll_mu = unit0.rolling(240, min_periods=72).mean().shift(1).fillna(0.0)
    roll_sd = unit0.rolling(240, min_periods=72).std().shift(1).replace(0, np.nan).fillna(unit0.std())
    q_quality = 0.25 + 1.25 / (1.0 + np.exp(-np.clip(roll_mu / roll_sd * np.sqrt(24 * 365.25) * 0.50, -50, 50)))
    strength_raw = hq * (1.0 + dq) * (1.0 + confirm) / 4.0

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
    )


def run_fixed_leverage(p: dict, K: float) -> dict:
    """Constant K on the base unit stream."""
    unit = p['unit0']
    r    = (K * unit).fillna(0.0).clip(lower=-0.95)
    eq   = pd.Series(INIT * (1 + r).cumprod(), index=unit.index)
    test_mask  = unit.index >= pd.Timestamp(TEST_START)
    train_mask = (unit.index >= pd.Timestamp(TRAIN_START)) & (unit.index < pd.Timestamp(TEST_START))
    return dict(
        K           = K,
        full        = equity_metrics(eq,                   label=f'Fixed K={K} — FULL'),
        train       = equity_metrics(eq[train_mask],       label=f'Fixed K={K} — TRAIN'),
        test        = equity_metrics(eq[test_mask],        label=f'Fixed K={K} — TEST (OOS)'),
        yearly      = period_table(eq, 'Y'),
        quarterly   = period_table(eq, 'Q'),
        drawdowns   = drawdown_periods(eq),
        counts      = None,          # no trade breakdown for fixed mode
    )


def run_dynamic(p: dict, K: float = DYN_K) -> dict:
    """Champion dynamic sizing: K × strength × quality × vol × gamma × Y."""
    strength_mult = np.clip(0.25 + DYN_STRENGTH_CAP * p['strength_raw'], 0.25, DYN_STRENGTH_CAP)
    vol_mult      = np.clip(p['vol_base'], 0.25, DYN_VOL_CAP)
    delta         = 1.2 - p['stress_rank']
    gamma         = np.clip(np.sign(delta) * delta ** 2, 0.4, 1.3)   # convex mode
    size_mult     = np.clip(strength_mult * p['q_quality'] * vol_mult * gamma, 0.0, DYN_TOTAL_CAP)

    unit_arr, counts = simulate_unit_with_psi(
        p['op'], p['hi'], p['lo'], p['cl'],
        p['hpos'], p['dpos'], p['dactive'], size_mult,
        BASE['sl_mult'] * p['daily_vol'],
        BASE['tp_mult'] * p['daily_vol'],
    )
    unit = pd.Series(unit_arr, index=p['hours'])

    # Adaptive Y
    y_result = adaptive_equity(unit, K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR)
    eq       = y_result['eq']

    test_mask  = unit.index >= pd.Timestamp(TEST_START)
    train_mask = (unit.index >= pd.Timestamp(TRAIN_START)) & (unit.index < pd.Timestamp(TEST_START))

    return dict(
        K              = K,
        full           = equity_metrics(eq,             label=f'Dynamic K={K} — FULL'),
        train          = equity_metrics(eq[train_mask],  label=f'Dynamic K={K} — TRAIN'),
        test           = equity_metrics(eq[test_mask],   label=f'Dynamic K={K} — TEST (OOS)'),
        yearly         = period_table(eq, 'Y'),
        quarterly      = period_table(eq, 'Q'),
        drawdowns      = drawdown_periods(eq),
        unit_yearly    = period_table(unit.cumsum().apply(lambda x: INIT * (1 + x)), 'Y'),
        counts         = counts,
        avg_y          = float(y_result['avg_y']),
        min_y          = float(y_result['min_y']),
        pct_cut        = float(y_result['pct_cut']),
        config         = dict(K=K, strength_cap=DYN_STRENGTH_CAP, vol_cap=DYN_VOL_CAP,
                              gamma_mode=DYN_GAMMA_MODE, total_cap=DYN_TOTAL_CAP,
                              dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                              q_hourly=BASE['q_hourly'], q_daily=BASE['q_daily'],
                              sl_mult=BASE['sl_mult'], tp_mult=BASE['tp_mult']),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(BAR)
    print('  ENTERPRISE v59 FULL SIMULATION')
    print('  BSDT Geometry (z(E7)+z(dG)+z(E6)+z(dT))/4 — 4-channel — SOL ffill extension')
    print(f'  Train: {TRAIN_START} → {TEST_START}   OOS test: {TEST_START} → today')
    print(BAR)

    # ── 1. Build geometry ────────────────────────────────────────────────────
    print('\n[1] Building geometry signal ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ohlc_all = fetch_futures_ohlcv()
    print(f'  geometry bars: {len(df_1h):,}  ({df_1h.index[0]} → {df_1h.index[-1]})')
    print(f'  OHLCV bars   : {len(ohlc_all):,}  ({ohlc_all.index[0]} → {ohlc_all.index[-1]})')

    # ── 2. Build signal / position arrays ───────────────────────────────────
    print('\n[2] Building signal and position arrays ...')
    p = build_signal_and_positions(df_1h, comp_raw, calib_mask, ohlc_all)
    n_active   = int((p['hpos'] != 0).sum())
    n_test_h   = int((p['hours'] >= pd.Timestamp(TEST_START)).sum())
    print(f'  common hours         : {len(p["hours"]):,}')
    print(f'  active (hpos != 0)   : {n_active:,}  ({n_active/len(p["hours"]):.1%} of bars)')
    print(f'  OOS test hours       : {n_test_h:,}')
    print(f'  hourly threshold     : {p["hth"]:.4f}  (q={BASE["q_hourly"]:.2f})')
    print(f'  daily threshold      : {p["dth"]:.4f}  (q={BASE["q_daily"]:.2f})')
    print(f'  daily vol (calib σ)  : {p["daily_vol"]:.2%}')

    # ── 3. Fixed leverage curves ─────────────────────────────────────────────
    print('\n[3] Fixed leverage simulations ...')
    res_k1  = run_fixed_leverage(p, K=1.0)
    res_k2  = run_fixed_leverage(p, K=2.0)
    res_k3  = run_fixed_leverage(p, K=3.0)
    res_k5  = run_fixed_leverage(p, K=5.0)

    # ── 4. Dynamic sizing + adaptive Y ──────────────────────────────────────
    print('[4] Dynamic sizing + adaptive Y simulation ...')
    res_dyn  = run_dynamic(p, K=3.0)
    res_dyn5 = run_dynamic(p, K=5.0)

    elapsed = time.time() - t0

    # ── PRINT RESULTS ────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  RESULTS — BASE UNIT (K=1)')
    print(SEP)
    for layer in [res_k1['full'], res_k1['train'], res_k1['test']]:
        print_metrics(layer); print()

    print(BAR)
    print('  RESULTS — FIXED K=2  (expert conservative)')
    print(SEP)
    for layer in [res_k2['full'], res_k2['train'], res_k2['test']]:
        print_metrics(layer); print()
    print('  Yearly:')
    print_yearly(res_k2['yearly'])

    print(f'\n{BAR}')
    print('  RESULTS — FIXED K=3  (research)')
    print(SEP)
    for layer in [res_k3['full'], res_k3['train'], res_k3['test']]:
        print_metrics(layer); print()
    print('  Yearly:')
    print_yearly(res_k3['yearly'])

    print(f'\n{BAR}')
    print('  RESULTS — FIXED K=5  (high leverage / blowup risk)')
    print(SEP)
    for layer in [res_k5['full'], res_k5['train'], res_k5['test']]:
        print_metrics(layer); print()
    print('  Yearly:')
    print_yearly(res_k5['yearly'])

    print(f'\n{BAR}')
    print(f'  RESULTS — DYNAMIC SIZING + ADAPTIVE Y  (champion K={DYN_K})')
    print(f'  Config: strength_cap={DYN_STRENGTH_CAP} vol_cap={DYN_VOL_CAP} gamma={DYN_GAMMA_MODE} '
          f'total_cap={DYN_TOTAL_CAP}  dd_soft={DYN_DD_SOFT:.0%} dd_stop={DYN_DD_STOP:.0%} y_floor={DYN_Y_FLOOR:.0%}')
    print(SEP)
    for layer in [res_dyn['full'], res_dyn['train'], res_dyn['test']]:
        print_metrics(layer); print()
    print(f'  avg_Y={res_dyn["avg_y"]:.3f}  min_Y={res_dyn["min_y"]:.3f}  '
          f'pct_time_braked={res_dyn["pct_cut"]:.1%}')
    print(f'\n  Trade counts (full period):')
    c = res_dyn['counts']
    print(f'    entries={c["entries"]:,}  exits={c["exits"]:,}  flips={c["flips"]:,}')
    print(f'    longs={c["longs"]:,}  shorts={c["shorts"]:,}')
    print(f'    exit reasons → stop={c["stop"]:,}  tp={c["tp"]:,}  '
          f'signal_exit={c["signal_exit"]:,}  close_end={c["close_end"]:,}')
    print(f'    skipped_daily_filter={c["skipped_daily_filter"]:,}  active_hours={c["active_hours"]:,}')
    print(f'\n  Yearly equity (dynamic K=3):')
    print_yearly(res_dyn['yearly'])
    print(f'\n  Quarterly equity (dynamic K=3):')
    print_yearly(res_dyn['quarterly'])
    print(f'\n  Top drawdown periods (dynamic K=3):')
    print_drawdowns(res_dyn['drawdowns'])

    print(f'\n{BAR}')
    print(f'  RESULTS — DYNAMIC SIZING + ADAPTIVE Y  (K=5.0  — high-leverage)')
    print(f'  Same sizing formula; adaptive Y absorbs tail risk.  Compare MaxDD carefully.')
    print(SEP)
    for layer in [res_dyn5['full'], res_dyn5['train'], res_dyn5['test']]:
        print_metrics(layer); print()
    print(f'  avg_Y={res_dyn5["avg_y"]:.3f}  min_Y={res_dyn5["min_y"]:.3f}  '
          f'pct_time_braked={res_dyn5["pct_cut"]:.1%}')
    print(f'\n  Yearly equity (dynamic K=5):')
    print_yearly(res_dyn5['yearly'])
    print(f'\n  Top drawdown periods (dynamic K=5):')
    print_drawdowns(res_dyn5['drawdowns'])

    # ── SIDE-BY-SIDE OOS COMPARISON ──────────────────────────────────────────
    print(f'\n{BAR}')
    print('  OOS TEST SUMMARY  (all strategies, post-2023)')
    print(SEP)
    print(f"  {'Strategy':<34} {'Final$':>10} {'Profit':>10} {'Ret':>8} {'CAGR':>8} "
          f"{'Sharpe':>8} {'MaxDD':>8} {'Calmar':>8}")
    for nm, res in [('Base unit (K=1)',         res_k1),
                    ('Fixed K=2',               res_k2),
                    ('Fixed K=3',               res_k3),
                    ('Fixed K=5',               res_k5),
                    ('Dynamic+AdaptY  K=3',     res_dyn),
                    ('Dynamic+AdaptY  K=5',     res_dyn5)]:
        m = res['test']
        print(f"  {nm:<34} {m['final']:>10,.2f} {m['profit']:>+10,.2f} {m['return_pct']:>+7.1%} "
              f"{m['cagr']:>+7.2%} {m['sharpe']:>+8.3f} {m['maxdd']:>+7.2%} {m['calmar']:>+8.3f}")

    print(f'\n  elapsed: {elapsed:.1f}s')
    print(BAR)

    # ── SAVE JSON ─────────────────────────────────────────────────────────────
    output = dict(
        generated_at_utc = pd.Timestamp.utcnow().isoformat(),
        geometry_window  = dict(start=str(df_1h.index[0]), end=str(df_1h.index[-1]), bars=len(df_1h)),
        ohlcv_window     = dict(start=str(ohlc_all.index[0]), end=str(ohlc_all.index[-1]), bars=len(ohlc_all)),
        signal_window    = dict(start=str(p['hours'][0]), end=str(p['hours'][-1]), bars=len(p['hours'])),
        active_bars      = n_active,
        fixed_k1         = {k: v for k, v in res_k1.items()   if k != 'counts'},
        fixed_k2         = {k: v for k, v in res_k2.items()   if k != 'counts'},
        fixed_k3         = {k: v for k, v in res_k3.items()   if k != 'counts'},
        fixed_k5         = {k: v for k, v in res_k5.items()   if k != 'counts'},
        dynamic_k3       = {k: v for k, v in res_dyn.items()  if k not in ('unit_yearly',)},
        dynamic_k5       = {k: v for k, v in res_dyn5.items() if k not in ('unit_yearly',)},
        elapsed_seconds  = elapsed,
    )
    OUT.write_text(json.dumps(output, indent=2, default=float))
    print(f'\n  Saved → {OUT}')


if __name__ == '__main__':
    main()
