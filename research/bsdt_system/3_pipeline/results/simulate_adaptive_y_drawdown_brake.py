"""Adaptive Y drawdown brake for corrected hourly strategy.

Y_t is the risk multiplier applied to the hourly strategy BEFORE the next trade:
    effective_return_t = K * Y_t * unit_return_t

Y_t uses only past equity state:
  - no brake while drawdown <= dd_soft
  - linearly reduce exposure between dd_soft and dd_stop
  - zero exposure once drawdown >= dd_stop
  - optional recovery: exposure comes back as equity recovers toward peak

This tests whether adaptive Y can make the high-performing hourly strategy
enterprise-safer without changing the alpha signal.
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

from simulate_hourly_2h_daily_risk_ohlc_fast import (
    INIT, OUT_DIR, TRAIN_START, TEST_START, QH_GRID, QD_GRID,
    build_daily_geometry, fetch_futures_ohlcv, CALIB_BARS,
    simulate_unit, period,
)

OUT = Path(OUT_DIR) / 'adaptive_y_drawdown_brake_results.json'

# Start from best raw corrected hourly config from full sweep.
BASE = dict(mode='daily_size', q_daily=0.70, q_hourly=0.50, sl_mult=1.00, tp_mult=1.50)
K_GRID = [2.0, 3.0, 5.0]
DD_SOFT_GRID = [0.05, 0.10, 0.15, 0.20]
DD_STOP_GRID = [0.20, 0.30, 0.40, 0.50]
Y_FLOOR_GRID = [0.0, 0.10, 0.25]


def adaptive_equity(unit_ret: pd.Series, K: float, dd_soft: float, dd_stop: float, y_floor: float):
    eq_vals=[]; y_vals=[]; dd_vals=[]
    eq=INIT; peak=INIT
    for _, ur in unit_ret.items():
        dd = max(0.0, 1.0 - eq/max(peak, 1e-12))
        if dd <= dd_soft:
            y = 1.0
        elif dd >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0-y_floor)*(dd_stop-dd)/(dd_stop-dd_soft)
        r = K * y * float(ur)
        r = max(r, -0.95)
        eq *= (1.0 + r)
        peak = max(peak, eq)
        eq_vals.append(eq); y_vals.append(y); dd_vals.append(dd)
    eqs = pd.Series(eq_vals, index=unit_ret.index)
    rets = eqs.pct_change().fillna(eqs.iloc[0]/INIT-1.0)
    dd_series = (eqs - eqs.cummax()) / eqs.cummax()
    years=max((eqs.index[-1]-eqs.index[0]).days/365.25, 1e-9)
    return dict(final=float(eqs.iloc[-1]), profit=float(eqs.iloc[-1]-INIT), profit_pct=float(eqs.iloc[-1]/INIT-1),
                cagr=float((eqs.iloc[-1]/INIT)**(1/years)-1),
                sharpe=float(np.sqrt(24*365.25)*rets.mean()/rets.std()) if rets.std()>0 else 0.0,
                maxdd=float(dd_series.min()), avg_y=float(np.mean(y_vals)), min_y=float(np.min(y_vals)),
                pct_cut=float(np.mean(np.array(y_vals)<0.999)), eq=eqs, y=pd.Series(y_vals,index=unit_ret.index))


def prep_unit_returns():
    df_1h, comp_raw, _ = build_daily_geometry()
    ohlc = fetch_futures_ohlcv()
    common_start=comp_raw.dropna().index.min(); common_end=comp_raw.dropna().index.max()
    ohlc=ohlc[(ohlc.index>=common_start)&(ohlc.index<=common_end)&(ohlc.index>=pd.Timestamp(TEST_START))].copy()
    hours=ohlc.index
    op=ohlc['open'].values.astype(float); hi=ohlc['high'].values.astype(float); lo=ohlc['low'].values.astype(float); cl=ohlc['close'].values.astype(float)
    idx=df_1h.index
    train_1h=(idx>=TRAIN_START)&(idx<TEST_START)
    train_idx=np.where(train_1h)[0]
    calib_mask=np.zeros(len(df_1h), dtype=bool); calib_mask[train_idx[-CALIB_BARS:]]=True
    hourly_cal=comp_raw[calib_mask].abs().dropna()
    sig_shifted=comp_raw.shift(1).reindex(hours).fillna(0.0).values.astype(float)
    hth=float(hourly_cal.quantile(BASE['q_hourly']))
    hpos=np.where(np.abs(sig_shifted)>=hth, np.sign(sig_shifted).astype(int), 0)

    daily_sig=comp_raw.groupby(comp_raw.index.normalize()).last()
    all_ohlc=fetch_futures_ohlcv()
    all_days=pd.Index(sorted(all_ohlc.index.normalize().unique()))
    calib_days=all_days[(all_days>=pd.Timestamp(TRAIN_START))&(all_days<pd.Timestamp(TEST_START))]
    ret_daily=all_ohlc['close'].pct_change().fillna(0.0).groupby(all_ohlc.index.normalize()).sum()
    daily_vol=float(ret_daily.reindex(calib_days).std())
    daily_cal=daily_sig.reindex(calib_days).abs().dropna()
    dth=float(daily_cal.quantile(BASE['q_daily']))
    prev_days=hours.normalize()-pd.Timedelta(days=1)
    ds_vals=daily_sig.reindex(prev_days).fillna(0.0).values.astype(float)
    dpos=np.sign(ds_vals).astype(int)
    dactive=np.abs(ds_vals)>=dth
    unit_arr, counts = simulate_unit(op,hi,lo,cl,hpos,dpos,dactive,BASE['sl_mult']*daily_vol,BASE['tp_mult']*daily_vol,BASE['mode'])
    return pd.Series(unit_arr,index=hours), counts, daily_vol


def main():
    t0=time.time()
    print('='*100)
    print('  ADAPTIVE Y DRAWDOWN BRAKE')
    print('='*100)
    unit, counts, daily_vol = prep_unit_returns()
    rows=[]
    for K in K_GRID:
        for ds in DD_SOFT_GRID:
            for dst in DD_STOP_GRID:
                if dst <= ds: continue
                for yf in Y_FLOOR_GRID:
                    m=adaptive_equity(unit,K,ds,dst,yf)
                    rows.append(dict(leverage=K, dd_soft=ds, dd_stop=dst, y_floor=yf,
                                     final=m['final'], profit=m['profit'], profit_pct=m['profit_pct'], cagr=m['cagr'],
                                     sharpe=m['sharpe'], maxdd=m['maxdd'], avg_y=m['avg_y'], min_y=m['min_y'], pct_cut=m['pct_cut']))
    top=sorted(rows,key=lambda r:(r['final'],r['sharpe']),reverse=True)
    safe=[r for r in rows if r['maxdd']>=-0.35 and r['sharpe']>=1.0]
    safe=sorted(safe,key=lambda r:(r['final'],r['sharpe']),reverse=True)
    selected=safe[0] if safe else top[0]
    m=adaptive_equity(unit,selected['leverage'],selected['dd_soft'],selected['dd_stop'],selected['y_floor'])
    yearly=period(m['eq'],'Y')
    print(f"  base counts: entries={counts['entries']} flips={counts['flips']} stop={counts['stop']} tp={counts['tp']}")
    print(f"\n  TOP SAFE ADAPTIVE Y")
    print(f"  {'Rank':>4} {'K':>3} {'soft':>5} {'stop':>5} {'floor':>5} {'Final$':>10} {'Sharpe':>8} {'MaxDD':>8} {'AvgY':>6} {'Cut%':>6}")
    for i,r in enumerate(safe[:20],1):
        print(f"  {i:>4} {r['leverage']:>3.0f} {r['dd_soft']:>5.0%} {r['dd_stop']:>5.0%} {r['y_floor']:>5.0%} {r['final']:>10,.0f} {r['sharpe']:>+8.2f} {r['maxdd']:>+7.1%} {r['avg_y']:>6.2f} {r['pct_cut']:>5.1%}")
    print(f"\n  SELECTED Y: K={selected['leverage']} dd_soft={selected['dd_soft']:.0%} dd_stop={selected['dd_stop']:.0%} floor={selected['y_floor']:.0%}")
    print(f"  final=${m['final']:,.2f} profit=${m['profit']:,.2f} sharpe={m['sharpe']:+.2f} maxDD={m['maxdd']:.1%} avgY={m['avg_y']:.2f}")
    print('  yearly:')
    for y in yearly:
        print(f"    {y['period']}: start=${y['start']:,.2f} end=${y['end']:,.2f} profit=${y['profit']:,.2f} ret={y['return_pct']:.1%}")
    OUT.write_text(json.dumps({'base_config':BASE,'base_counts':counts,'daily_vol':daily_vol,
                               'top_safe':safe[:30],'top_by_final':top[:30],'selected':selected,
                               'selected_yearly':yearly,'elapsed_seconds':time.time()-t0},indent=2,default=float))
    print(f"\n  saved -> {OUT}\n  elapsed={time.time()-t0:.1f}s")

if __name__=='__main__':
    main()
