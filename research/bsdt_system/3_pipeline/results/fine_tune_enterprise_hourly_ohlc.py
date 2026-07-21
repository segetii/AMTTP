"""Fine-tune hourly geometry execution with true OHLC stops.

Goal: recover more of the strong hourly/2h performance while keeping enterprise
risk controls:
  - true Binance futures OHLC stop/TP simulation
  - maker low-cost execution
  - optional daily risk confirmation
  - hourly confidence threshold sweep
  - stop/take-profit sweep

This places no orders.
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
FUND_DAY = 0.5 / 1e4
OUT = Path(OUT_DIR) / 'fine_tuned_enterprise_hourly_ohlc_results.json'

MODES = ['hourly_only', 'daily_soft', 'daily_confirm']
Q_DAILY_GRID = [0.60, 0.70, 0.80, 0.90]
Q_HOURLY_GRID = [0.50, 0.60, 0.70, 0.80, 0.90]
SL_GRID = [0.35, 0.50, 0.75, 1.00, 1.25]
TP_GRID = [0.50, 0.75, 1.00, 1.50, 2.00, 3.00]
K_GRID = [2.0, 3.0, 5.0]


def _equity(r, init=INIT):
    r = pd.Series(r).fillna(0.0).clip(lower=-0.95)
    eq = init * (1.0 + r).cumprod()
    dd = (eq - eq.cummax()) / eq.cummax()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    return dict(final=float(eq.iloc[-1]), profit=float(eq.iloc[-1]-init), profit_pct=float(eq.iloc[-1]/init-1),
                cagr=float((eq.iloc[-1]/init)**(1/years)-1),
                sharpe=float(np.sqrt(365.25)*r.mean()/r.std()) if r.std()>0 else 0.0,
                maxdd=float(dd.min()), eq=eq)


def _period(eq, freq):
    out=[]
    for dt, s in eq.groupby(pd.Grouper(freq=freq)):
        if len(s)<2: continue
        out.append(dict(period=str(dt.date()), start=float(s.iloc[0]), end=float(s.iloc[-1]),
                        profit=float(s.iloc[-1]-s.iloc[0]), return_pct=float(s.iloc[-1]/s.iloc[0]-1)))
    return out


def _path_exit(day_ohlc, entry_i, pos, sl, tp):
    path = day_ohlc.iloc[entry_i:]
    if len(path) == 0:
        return 0.0, 'none'
    entry = float(path['open'].iloc[0])
    for _, row in path.iterrows():
        if pos > 0:
            adverse = float(row['low']/entry - 1.0)
            favourable = float(row['high']/entry - 1.0)
        else:
            adverse = float(entry/row['high'] - 1.0)
            favourable = float(entry/row['low'] - 1.0)
        stop_hit = adverse <= -sl
        tp_hit = favourable >= tp
        if stop_hit and tp_hit: return -sl, 'both_stop_first'
        if stop_hit: return -sl, 'stop'
        if tp_hit: return tp, 'tp'
    close = float(path['close'].iloc[-1])
    return ((close/entry - 1.0) if pos > 0 else (entry/close - 1.0)), 'close'


def simulate_config(day_data, comp_hourly, daily_sig, test_days, q_daily, q_hourly, sl, tp, mode):
    th_daily = None if q_daily is None else float(daily_sig['calib_abs'].quantile(q_daily))
    th_hourly = float(comp_hourly['calib_abs'].quantile(q_hourly))
    rows=[]
    counts={'trades':0,'long':0,'short':0,'stop':0,'tp':0,'both_stop_first':0,'close':0,'none':0,'skip_daily':0,'skip_hourly':0}
    for day in test_days:
        prev_day = day - pd.Timedelta(days=1)
        ds = daily_sig['sig'].get(prev_day, np.nan)
        daily_active = np.isfinite(ds) and (th_daily is not None) and abs(ds) >= th_daily
        daily_pos = 1.0 if np.isfinite(ds) and ds > 0 else (-1.0 if np.isfinite(ds) else 0.0)
        if mode == 'daily_confirm' and not daily_active:
            rows.append((day,0.0)); counts['skip_daily']+=1; continue
        day_ohlc = day_data.get(day)
        if day_ohlc is None:
            day_ohlc = []
        if len(day_ohlc)==0:
            rows.append((day,0.0)); counts['skip_hourly']+=1; continue
        entry_i=None; pos=None
        for i, ts in enumerate(day_ohlc.index):
            hs = comp_hourly['sig_shifted'].get(ts, np.nan)
            if not np.isfinite(hs) or abs(hs) < th_hourly:
                continue
            hpos = 1.0 if hs > 0 else -1.0
            if mode == 'daily_confirm':
                if hpos != daily_pos: continue
            elif mode == 'daily_soft':
                # if daily gate is active, require agreement; if inactive, allow hourly.
                if daily_active and hpos != daily_pos: continue
            # hourly_only ignores daily completely.
            entry_i=i; pos=hpos; break
        if entry_i is None:
            rows.append((day,0.0)); counts['skip_hourly']+=1; continue
        gross, reason = _path_exit(day_ohlc, entry_i, pos, sl, tp)
        net = gross - RT_COST - FUND_DAY
        rows.append((day, net))
        counts['trades']+=1; counts['long' if pos>0 else 'short']+=1; counts[reason]+=1
    return pd.Series(dict(rows)).sort_index(), counts


def main():
    BAR='='*100
    print(BAR)
    print('  FINE-TUNE HOURLY EXECUTION — TRUE OHLC STOPS')
    print(BAR)
    t0=time.time()
    df_1h, comp_raw, _ = build_daily_geometry()
    ohlc = fetch_futures_ohlcv()
    common_start = comp_raw.dropna().index.min(); common_end = comp_raw.dropna().index.max()
    ohlc = ohlc[(ohlc.index >= common_start) & (ohlc.index <= common_end)].copy()
    day_data = {day: day_df for day, day_df in ohlc.groupby(ohlc.index.normalize())}
    idx = df_1h.index
    train_1h=(idx>=TRAIN_START)&(idx<TEST_START)
    train_idx=np.where(train_1h)[0]
    calib_mask=np.zeros(len(df_1h), dtype=bool); calib_mask[train_idx[-CALIB_BARS:]]=True
    comp_hourly = {'sig': comp_raw, 'sig_shifted': comp_raw.shift(1), 'calib_abs': comp_raw[calib_mask].abs().dropna()}
    daily_last = comp_raw.groupby(comp_raw.index.normalize()).last()
    ret_daily = ohlc['close'].pct_change().fillna(0.0).groupby(ohlc.index.normalize()).sum()
    days = pd.Index(sorted(ret_daily.index.unique()))
    calib_days = days[(days>=pd.Timestamp(TRAIN_START)) & (days<pd.Timestamp(TEST_START))]
    test_days = days[days>=pd.Timestamp(TEST_START)]
    daily_vol=float(ret_daily.reindex(calib_days).std())
    daily_sig={'sig': daily_last, 'calib_abs': daily_last.reindex(calib_days).abs().dropna()}
    print(f'  daily σ={daily_vol:.2%}; test days={len(test_days)}')

    raw_rows=[]
    configs=[]
    for mode in MODES:
        qds = [None] if mode == 'hourly_only' else Q_DAILY_GRID
        for qd, qh, slm, tpm in itertools.product(qds, Q_HOURLY_GRID, SL_GRID, TP_GRID):
            configs.append((mode, qd, qh, slm, tpm))
    print(f'  sweeping {len(configs)} configs × {len(K_GRID)} leverage levels')
    for n,(mode,qd,qh,slm,tpm) in enumerate(configs,1):
        if n % 100 == 0: print(f'    config {n}/{len(configs)} t={time.time()-t0:.0f}s', flush=True)
        r_unit, counts = simulate_config(day_data, comp_hourly, daily_sig, test_days, qd, qh, slm*daily_vol, tpm*daily_vol, mode)
        for K in K_GRID:
            m=_equity(K*r_unit)
            raw_rows.append(dict(mode=mode, q_daily=qd, q_hourly=qh, sl_mult=slm, tp_mult=tpm, leverage=K,
                                 final=m['final'], profit=m['profit'], profit_pct=m['profit_pct'], cagr=m['cagr'],
                                 sharpe=m['sharpe'], maxdd=m['maxdd'], **counts))
    rows=sorted(raw_rows, key=lambda r:(r['final'], r['sharpe']), reverse=True)
    safe=[r for r in raw_rows if r['leverage']==2.0 and r['maxdd']>=-0.35 and r['sharpe']>=1.0 and r['trades']>=100]
    safe=sorted(safe, key=lambda r:(r['final'], r['sharpe']), reverse=True)

    print(f"\n{BAR}\n  TOP BY FINAL EQUITY\n{BAR}")
    print(f"  {'Rank':>4} {'Mode':<13} {'K':>3} {'qd':>4} {'qh':>4} {'SL':>4} {'TP':>4} {'Trades':>6} {'Final$':>10} {'Sharpe':>8} {'MaxDD':>8}")
    for i,r in enumerate(rows[:20],1):
        qd='--' if r['q_daily'] is None else f"{r['q_daily']:.2f}"
        print(f"  {i:>4} {r['mode']:<13} {r['leverage']:>3.0f} {qd:>4} {r['q_hourly']:>4.2f} {r['sl_mult']:>4.2f} {r['tp_mult']:>4.2f} {r['trades']:>6} {r['final']:>10,.0f} {r['sharpe']:>+8.2f} {r['maxdd']:>+7.1%}")

    print(f"\n{BAR}\n  TOP SAFE K=2 (MaxDD ≥ -35%, Sharpe ≥ 1, trades ≥ 100)\n{BAR}")
    for i,r in enumerate(safe[:20],1):
        qd='--' if r['q_daily'] is None else f"{r['q_daily']:.2f}"
        print(f"  {i:>4} {r['mode']:<13} {qd:>4} {r['q_hourly']:>4.2f} SL={r['sl_mult']:.2f} TP={r['tp_mult']:.2f} trades={r['trades']:>4} final=${r['final']:>9,.0f} sharpe={r['sharpe']:+.2f} dd={r['maxdd']:+.1%}")

    best = safe[0] if safe else rows[0]
    r_unit, counts = simulate_config(day_data, comp_hourly, daily_sig, test_days, best['q_daily'], best['q_hourly'], best['sl_mult']*daily_vol, best['tp_mult']*daily_vol, best['mode'])
    m=_equity(best['leverage']*r_unit)
    yearly=_period(m['eq'],'Y'); quarterly=_period(m['eq'],'Q')
    print(f"\n  SELECTED: {best['mode']} K={best['leverage']} qd={best['q_daily']} qh={best['q_hourly']} SL={best['sl_mult']}σ TP={best['tp_mult']}σ")
    print(f"  final=${m['final']:,.2f} profit=${m['profit']:,.2f} Sharpe={m['sharpe']:+.2f} MaxDD={m['maxdd']:.1%} trades={counts['trades']}")
    print('  yearly:')
    for y in yearly:
        print(f"    {y['period']}: start=${y['start']:,.2f} end=${y['end']:,.2f} profit=${y['profit']:,.2f} ret={y['return_pct']:.1%}")

    OUT.write_text(json.dumps({'top_by_final': rows[:50], 'top_safe_k2': safe[:50], 'selected': best, 'selected_counts': counts,
                               'selected_yearly': yearly, 'selected_quarterly': quarterly,
                               'daily_vol': daily_vol, 'elapsed_seconds': time.time()-t0}, indent=2, default=float))
    print(f"\n  saved -> {OUT}\n  elapsed={time.time()-t0:.1f}s\n{BAR}")

if __name__ == '__main__':
    main()
