"""Corrected expert simulation: still trade hourly.

The daily layer does NOT replace hourly trading. It only tunes risk:
  - whether daily context confirms or conflicts with hourly direction
  - stop-loss and take-profit scale via daily volatility
  - optional leverage reduction on non-confirmed hours

The 2h/hourly geometry signal still decides entries every hour.

Execution model:
  - one open position at a time
  - signal is shifted one hour: use signal[t-1], enter at open[t]
  - true OHLC stop/take-profit inside each hourly candle
  - if opposite hourly signal arrives, exit at candle open and optionally flip
  - low-cost maker model approximated as 2 bps round-trip per completed trade
    plus 0.5 bps/day funding while position is active
  - no live/paper orders
"""
from __future__ import annotations
import json, time, itertools
from pathlib import Path
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS
from test_daily_geometry_stop_tp_ohlc import build_daily_geometry, fetch_futures_ohlcv

INIT = 1000.0
RT_COST = 2.0 / 1e4
FUND_HOUR = (0.5 / 24.0) / 1e4
OUT = Path(OUT_DIR) / 'hourly_2h_daily_risk_ohlc_results.json'

QH_GRID = [0.50, 0.60, 0.70, 0.80, 0.90]
QD_GRID = [0.70, 0.80, 0.90]
SL_GRID = [0.35, 0.50, 0.75, 1.00]
TP_GRID = [1.00, 1.50, 2.00, 3.00]
K_GRID = [2.0, 3.0, 5.0]
MODES = ['hourly_only', 'daily_filter', 'daily_size']


def _equity(hourly_ret):
    r = pd.Series(hourly_ret).fillna(0.0).clip(lower=-0.95)
    eq = INIT * (1.0 + r).cumprod()
    dd = (eq - eq.cummax()) / eq.cummax()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    return dict(final=float(eq.iloc[-1]), profit=float(eq.iloc[-1]-INIT), profit_pct=float(eq.iloc[-1]/INIT-1),
                cagr=float((eq.iloc[-1]/INIT)**(1/years)-1),
                sharpe=float(np.sqrt(24*365.25)*r.mean()/r.std()) if r.std()>0 else 0.0,
                maxdd=float(dd.min()), eq=eq)


def _period(eq, freq):
    out=[]
    for dt, s in eq.groupby(pd.Grouper(freq=freq)):
        if len(s)<2: continue
        out.append(dict(period=str(dt.date()), start=float(s.iloc[0]), end=float(s.iloc[-1]),
                        profit=float(s.iloc[-1]-s.iloc[0]), return_pct=float(s.iloc[-1]/s.iloc[0]-1)))
    return out


def _daily_context(daily_sig, daily_th, ts):
    prev_day = ts.normalize() - pd.Timedelta(days=1)
    ds = daily_sig.get(prev_day, np.nan)
    if not np.isfinite(ds):
        return 0, False
    return (1 if ds > 0 else -1), abs(ds) >= daily_th


def simulate(ohlc, sig_shifted, daily_sig, qh_th, qd_th, sl, tp, mode, leverage):
    hours = ohlc.index[ohlc.index >= pd.Timestamp(TEST_START)]
    pnl = pd.Series(0.0, index=hours)
    pos = 0
    size = 1.0
    entry = None
    stop_price = None
    tp_price = None
    counts = dict(entries=0, exits=0, flips=0, longs=0, shorts=0, stop=0, tp=0, signal_exit=0, close_end=0,
                  skipped_daily_filter=0, active_hours=0)
    for ts in hours:
        row = ohlc.loc[ts]
        hsig = sig_shifted.get(ts, np.nan)
        hactive = np.isfinite(hsig) and abs(hsig) >= qh_th
        hpos = 1 if np.isfinite(hsig) and hsig > 0 else (-1 if np.isfinite(hsig) else 0)
        dpos, dactive = _daily_context(daily_sig, qd_th, ts)
        scale = 1.0
        if mode == 'daily_filter':
            if dactive and hactive and hpos != dpos:
                hactive = False
                counts['skipped_daily_filter'] += 1
        elif mode == 'daily_size':
            # daily confirms -> full size; daily conflicts -> no entry; no daily signal -> half size.
            if hactive:
                if dactive and hpos == dpos:
                    scale = 1.0
                elif dactive and hpos != dpos:
                    hactive = False
                    counts['skipped_daily_filter'] += 1
                else:
                    scale = 0.5
        # manage open position first using true OHLC path
        if pos != 0:
            counts['active_hours'] += 1
            exit_ret = None; reason = None
            if pos > 0:
                stop_hit = float(row['low']) <= stop_price
                tp_hit = float(row['high']) >= tp_price
                if stop_hit and tp_hit:
                    exit_ret = stop_price / entry - 1.0; reason = 'stop'
                elif stop_hit:
                    exit_ret = stop_price / entry - 1.0; reason = 'stop'
                elif tp_hit:
                    exit_ret = tp_price / entry - 1.0; reason = 'tp'
            else:
                stop_hit = float(row['high']) >= stop_price
                tp_hit = float(row['low']) <= tp_price
                if stop_hit and tp_hit:
                    exit_ret = entry / stop_price - 1.0; reason = 'stop'
                elif stop_hit:
                    exit_ret = entry / stop_price - 1.0; reason = 'stop'
                elif tp_hit:
                    exit_ret = entry / tp_price - 1.0; reason = 'tp'
            # signal flip exits at open if no stop/TP already counted in candle.
            if exit_ret is None and hactive and hpos == -pos:
                op = float(row['open'])
                exit_ret = (op / entry - 1.0) if pos > 0 else (entry / op - 1.0)
                reason = 'signal_exit'
                counts['flips'] += 1
            if exit_ret is not None:
                pnl.loc[ts] += leverage * size * (exit_ret - RT_COST)
                counts[reason] += 1; counts['exits'] += 1
                pos = 0; size = 1.0; entry = stop_price = tp_price = None
            else:
                pnl.loc[ts] += -leverage * size * FUND_HOUR
        # enter if flat and hourly signal active
        if pos == 0 and hactive:
            pos = hpos
            size = scale
            entry = float(row['open'])
            if pos > 0:
                stop_price = entry * (1.0 - sl)
                tp_price = entry * (1.0 + tp)
                counts['longs'] += 1
            else:
                stop_price = entry * (1.0 + sl)
                tp_price = entry * (1.0 - tp)
                counts['shorts'] += 1
            counts['entries'] += 1
    # close remaining at last close
    if pos != 0 and entry is not None:
        ts = hours[-1]
        close = float(ohlc.loc[ts, 'close'])
        gross = (close/entry - 1.0) if pos > 0 else (entry/close - 1.0)
        pnl.loc[ts] += leverage * size * (gross - RT_COST)
        counts['close_end'] += 1; counts['exits'] += 1
    return pnl, counts


def main():
    BAR='='*100
    print(BAR)
    print('  CORRECTED HOURLY TRADING: 2H ENTRY + DAILY RISK + TRUE OHLC STOPS')
    print(BAR)
    t0=time.time()
    df_1h, comp_raw, _ = build_daily_geometry()
    ohlc = fetch_futures_ohlcv()
    common_start = comp_raw.dropna().index.min(); common_end = comp_raw.dropna().index.max()
    ohlc = ohlc[(ohlc.index >= common_start) & (ohlc.index <= common_end)].copy()
    idx = df_1h.index
    train_1h = (idx >= TRAIN_START) & (idx < TEST_START)
    train_idx = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool); calib_mask[train_idx[-CALIB_BARS:]] = True
    sig_shifted = comp_raw.shift(1)
    hourly_abs_cal = comp_raw[calib_mask].abs().dropna()
    daily_sig = comp_raw.groupby(comp_raw.index.normalize()).last()
    days = pd.Index(sorted(ohlc.index.normalize().unique()))
    calib_days = days[(days >= pd.Timestamp(TRAIN_START)) & (days < pd.Timestamp(TEST_START))]
    ret_daily = ohlc['close'].pct_change().fillna(0.0).groupby(ohlc.index.normalize()).sum()
    daily_vol = float(ret_daily.reindex(calib_days).std())
    daily_abs_cal = daily_sig.reindex(calib_days).abs().dropna()
    print(f'  daily σ={daily_vol:.2%}; hourly bars={len(ohlc[ohlc.index>=pd.Timestamp(TEST_START)])}')

    results=[]
    configs=list(itertools.product(MODES, QD_GRID, QH_GRID, SL_GRID, TP_GRID, K_GRID))
    print(f'  sweeping {len(configs)} configs')
    for i,(mode,qd,qh,slm,tpm,K) in enumerate(configs,1):
        if i % 250 == 0: print(f'    {i}/{len(configs)} t={time.time()-t0:.0f}s', flush=True)
        qh_th = float(hourly_abs_cal.quantile(qh))
        qd_th = float(daily_abs_cal.quantile(qd))
        pnl, counts = simulate(ohlc, sig_shifted, daily_sig, qh_th, qd_th, slm*daily_vol, tpm*daily_vol, mode, K)
        m=_equity(pnl)
        results.append(dict(mode=mode, q_daily=qd, q_hourly=qh, sl_mult=slm, tp_mult=tpm, leverage=K,
                            final=m['final'], profit=m['profit'], profit_pct=m['profit_pct'], cagr=m['cagr'],
                            sharpe=m['sharpe'], maxdd=m['maxdd'], **counts))
    top=sorted(results, key=lambda r:(r['final'], r['sharpe']), reverse=True)
    safe=[r for r in results if r['leverage']==2.0 and r['maxdd']>=-0.35 and r['sharpe']>=1.0 and r['entries']>=100]
    safe=sorted(safe, key=lambda r:(r['final'], r['sharpe']), reverse=True)

    print(f"\n{BAR}\n  TOP BY FINAL\n{BAR}")
    print(f"  {'Rank':>4} {'Mode':<12} {'K':>3} {'qd':>4} {'qh':>4} {'SL':>4} {'TP':>4} {'Ent':>5} {'Final$':>10} {'Sharpe':>8} {'MaxDD':>8}")
    for j,r in enumerate(top[:20],1):
        print(f"  {j:>4} {r['mode']:<12} {r['leverage']:>3.0f} {r['q_daily']:>4.2f} {r['q_hourly']:>4.2f} {r['sl_mult']:>4.2f} {r['tp_mult']:>4.2f} {r['entries']:>5} {r['final']:>10,.0f} {r['sharpe']:>+8.2f} {r['maxdd']:>+7.1%}")

    print(f"\n{BAR}\n  TOP SAFE K=2\n{BAR}")
    for j,r in enumerate(safe[:20],1):
        print(f"  {j:>4} {r['mode']:<12} qd={r['q_daily']:.2f} qh={r['q_hourly']:.2f} SL={r['sl_mult']:.2f} TP={r['tp_mult']:.2f} entries={r['entries']:>4} final=${r['final']:>9,.0f} sharpe={r['sharpe']:+.2f} dd={r['maxdd']:+.1%}")

    selected = safe[0] if safe else top[0]
    qh_th=float(hourly_abs_cal.quantile(selected['q_hourly'])); qd_th=float(daily_abs_cal.quantile(selected['q_daily']))
    pnl, counts = simulate(ohlc, sig_shifted, daily_sig, qh_th, qd_th, selected['sl_mult']*daily_vol, selected['tp_mult']*daily_vol, selected['mode'], selected['leverage'])
    m=_equity(pnl); yearly=_period(m['eq'], 'Y'); quarterly=_period(m['eq'], 'Q')
    print(f"\n  SELECTED HOURLY: {selected['mode']} K={selected['leverage']} qd={selected['q_daily']} qh={selected['q_hourly']} SL={selected['sl_mult']}σ TP={selected['tp_mult']}σ")
    print(f"  final=${m['final']:,.2f} profit=${m['profit']:,.2f} sharpe={m['sharpe']:+.2f} maxDD={m['maxdd']:.1%} entries={counts['entries']}")
    print('  yearly:')
    for y in yearly:
        print(f"    {y['period']}: start=${y['start']:,.2f} end=${y['end']:,.2f} profit=${y['profit']:,.2f} ret={y['return_pct']:.1%}")

    OUT.write_text(json.dumps({'top_by_final': top[:50], 'top_safe_k2': safe[:50], 'selected': selected,
                               'selected_counts': counts, 'selected_yearly': yearly, 'selected_quarterly': quarterly,
                               'daily_vol': daily_vol, 'elapsed_seconds': time.time()-t0}, indent=2, default=float))
    print(f"\n  saved -> {OUT}\n  elapsed={time.time()-t0:.1f}s\n{BAR}")

if __name__ == '__main__':
    main()
