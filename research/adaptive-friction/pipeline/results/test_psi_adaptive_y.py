"""Test ψ as a geometric validity multiplier with adaptive Y drawdown brake.

Compares current corrected hourly system:
  1) no ψ
  2) hard ψ gate: ψ < π/4
  3) soft ψ multiplier: max(cosψ, 0)
  4) thresholded soft: 0 if cosψ < .30 else cosψ

Then applies adaptive Y drawdown brake to each return stream.
No live/paper orders.
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS, build_intraday_state_panel, calibrate_intraday_engine, compute_intraday_signals
from run_robustness_validation import _cached_fetch_binance_funding
from test_daily_geometry_stop_tp_ohlc import build_daily_geometry, fetch_futures_ohlcv
from simulate_adaptive_y_drawdown_brake import adaptive_equity
from simulate_hourly_2h_daily_risk_ohlc_fast import period

OUT = Path(OUT_DIR) / 'psi_adaptive_y_results.json'
BASE = dict(mode='daily_size', q_daily=0.70, q_hourly=0.50, sl_mult=1.00, tp_mult=1.50)
Y_CFG = dict(leverage=2.0, dd_soft=0.05, dd_stop=0.20, y_floor=0.25)
RT_COST = 2.0 / 1e4
FUND_HOUR = (0.5 / 24.0) / 1e4
INIT = 1000.0


def compute_psi(df_1h, calib_mask):
    fund = _cached_fetch_binance_funding()
    X = np.nan_to_num(build_intraday_state_panel(df_1h, fund.get('BTCUSDT'), fund.get('ETHUSDT')))
    if len(X) != len(df_1h):
        n = min(len(X), len(df_1h)); X = X[:n]; df_1h = df_1h.iloc[:n]; calib_mask = calib_mask[:n]
    print('  [psi] calibrating v36 engine...', flush=True)
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(X, calib_mask)
    print('  [psi] computing v36 ψ signals...', flush=True)
    sig = compute_intraday_signals(X, df_1h, M, net, ews, stoch, e_star, theta)
    return sig['psi_t'].reindex(df_1h.index).ffill().fillna(np.pi/2)


def equity_no_y(unit, K):
    r=(K*unit).fillna(0).clip(lower=-0.95)
    eq=INIT*(1+r).cumprod(); dd=(eq-eq.cummax())/eq.cummax()
    years=max((eq.index[-1]-eq.index[0]).days/365.25,1e-9)
    return dict(final=float(eq.iloc[-1]), sharpe=float(np.sqrt(24*365.25)*r.mean()/r.std()) if r.std()>0 else 0.0,
                maxdd=float(dd.min()), cagr=float((eq.iloc[-1]/INIT)**(1/years)-1), eq=eq)


def simulate_unit_with_psi(op,hi,lo,cl,hpos_arr,dpos_arr,dactive_arr,psi_y,sl,tp):
    n=len(op); ret=np.zeros(n,dtype=float)
    pos=0.0; size=1.0; entry=0.0; stop_price=0.0; take_price=0.0
    counts=dict(entries=0, exits=0, flips=0, longs=0, shorts=0, stop=0, tp=0, signal_exit=0, close_end=0, skipped_daily_filter=0, psi_blocked=0, active_hours=0, avg_psi_y=0.0)
    psi_sizes=[]
    for i in range(n):
        hpos=hpos_arr[i]; hactive=hpos!=0
        dpos=dpos_arr[i]; dactive=dactive_arr[i]
        scale=1.0
        # daily_size base: confirms full, no daily = half, conflict = no entry
        if hactive:
            if dactive and hpos == dpos: scale=1.0
            elif dactive and hpos != dpos:
                hactive=False; hpos=0; counts['skipped_daily_filter']+=1
            else: scale=0.5
        if hactive:
            scale *= psi_y[i]
            if scale <= 1e-12:
                hactive=False; hpos=0; counts['psi_blocked']+=1
        if pos != 0:
            counts['active_hours']+=1
            exit_ret=None; reason=None
            if pos>0:
                stop_hit=lo[i]<=stop_price; tp_hit=hi[i]>=take_price
                if stop_hit and tp_hit: exit_ret=stop_price/entry-1; reason='stop'
                elif stop_hit: exit_ret=stop_price/entry-1; reason='stop'
                elif tp_hit: exit_ret=take_price/entry-1; reason='tp'
            else:
                stop_hit=hi[i]>=stop_price; tp_hit=lo[i]<=take_price
                if stop_hit and tp_hit: exit_ret=entry/stop_price-1; reason='stop'
                elif stop_hit: exit_ret=entry/stop_price-1; reason='stop'
                elif tp_hit: exit_ret=entry/take_price-1; reason='tp'
            if exit_ret is None and hactive and hpos == -pos:
                exit_ret=(op[i]/entry-1) if pos>0 else (entry/op[i]-1); reason='signal_exit'; counts['flips']+=1
            if exit_ret is not None:
                ret[i]+=size*(exit_ret-RT_COST); counts[reason]+=1; counts['exits']+=1
                pos=0; size=1; entry=0
            else:
                ret[i]+=-size*FUND_HOUR
        if pos == 0 and hactive:
            pos=float(hpos); size=float(scale); entry=op[i]; psi_sizes.append(float(psi_y[i]))
            if pos>0:
                stop_price=entry*(1-sl); take_price=entry*(1+tp); counts['longs']+=1
            else:
                stop_price=entry*(1+sl); take_price=entry*(1-tp); counts['shorts']+=1
            counts['entries']+=1
    if pos!=0:
        i=n-1; gross=(cl[i]/entry-1) if pos>0 else (entry/cl[i]-1)
        ret[i]+=size*(gross-RT_COST); counts['close_end']+=1; counts['exits']+=1
    counts['avg_psi_y']=float(np.mean(psi_sizes)) if psi_sizes else 0.0
    return ret, counts


def main():
    t0=time.time(); print('='*100); print('  ψ + ADAPTIVE Y TEST'); print('='*100)
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    psi = compute_psi(df_1h, calib_mask)
    ohlc = fetch_futures_ohlcv()
    common_start=comp_raw.dropna().index.min(); common_end=comp_raw.dropna().index.max()
    ohlc=ohlc[(ohlc.index>=common_start)&(ohlc.index<=common_end)&(ohlc.index>=pd.Timestamp(TEST_START))].copy()
    hours=ohlc.index
    op=ohlc['open'].values.astype(float); hi=ohlc['high'].values.astype(float); lo=ohlc['low'].values.astype(float); cl=ohlc['close'].values.astype(float)

    hourly_cal=comp_raw[calib_mask].abs().dropna(); hth=float(hourly_cal.quantile(BASE['q_hourly']))
    sig_shifted=comp_raw.shift(1).reindex(hours).fillna(0.0).values.astype(float)
    hpos=np.where(np.abs(sig_shifted)>=hth, np.sign(sig_shifted).astype(int), 0)
    daily_sig=comp_raw.groupby(comp_raw.index.normalize()).last()
    all_ohlc=fetch_futures_ohlcv(); all_days=pd.Index(sorted(all_ohlc.index.normalize().unique()))
    calib_days=all_days[(all_days>=pd.Timestamp(TRAIN_START))&(all_days<pd.Timestamp(TEST_START))]
    ret_daily=all_ohlc['close'].pct_change().fillna(0.0).groupby(all_ohlc.index.normalize()).sum()
    daily_vol=float(ret_daily.reindex(calib_days).std())
    dth=float(daily_sig.reindex(calib_days).abs().dropna().quantile(BASE['q_daily']))
    prev_days=hours.normalize()-pd.Timedelta(days=1)
    ds_vals=daily_sig.reindex(prev_days).fillna(0.0).values.astype(float)
    dpos=np.sign(ds_vals).astype(int); dactive=np.abs(ds_vals)>=dth
    psi_shift=psi.shift(1).reindex(hours).ffill().fillna(np.pi/2)
    cospsi=np.cos(psi_shift.values.astype(float))
    variants={
        'no_psi': np.ones(len(hours)),
        'hard_pi4': (psi_shift.values < np.pi/4).astype(float),
        'soft_cos': np.clip(cospsi,0,1),
        'soft_floor_030': np.where(cospsi < 0.30, 0.0, np.clip(cospsi,0,1)),
        'soft_sqrt_cos': np.sqrt(np.clip(cospsi,0,1)),
    }
    rows=[]
    for name,py in variants.items():
        unit_arr, counts=simulate_unit_with_psi(op,hi,lo,cl,hpos,dpos,dactive,py,BASE['sl_mult']*daily_vol,BASE['tp_mult']*daily_vol)
        unit=pd.Series(unit_arr,index=hours)
        raw=equity_no_y(unit,Y_CFG['leverage'])
        y=adaptive_equity(unit,Y_CFG['leverage'],Y_CFG['dd_soft'],Y_CFG['dd_stop'],Y_CFG['y_floor'])
        rows.append(dict(variant=name, raw_final=raw['final'], raw_sharpe=raw['sharpe'], raw_maxdd=raw['maxdd'],
                         y_final=y['final'], y_profit=y['profit'], y_sharpe=y['sharpe'], y_maxdd=y['maxdd'],
                         y_avg=y['avg_y'], y_pct_cut=y['pct_cut'], **counts))
    rows=sorted(rows,key=lambda r:(r['y_final'],r['y_sharpe']),reverse=True)
    selected=rows[0]
    # yearly for selected
    unit_arr, counts=simulate_unit_with_psi(op,hi,lo,cl,hpos,dpos,dactive,variants[selected['variant']],BASE['sl_mult']*daily_vol,BASE['tp_mult']*daily_vol)
    y=adaptive_equity(pd.Series(unit_arr,index=hours),Y_CFG['leverage'],Y_CFG['dd_soft'],Y_CFG['dd_stop'],Y_CFG['y_floor'])
    yearly=period(y['eq'],'Y')
    print(f"\n  {'Variant':<16} {'Entries':>7} {'AvgPsi':>7} {'Raw$':>10} {'RawDD':>8} {'Y$':>10} {'YSh':>7} {'YDD':>8} {'AvgY':>6}")
    for r in rows:
        print(f"  {r['variant']:<16} {r['entries']:>7} {r['avg_psi_y']:>7.2f} {r['raw_final']:>10,.0f} {r['raw_maxdd']:>+7.1%} {r['y_final']:>10,.0f} {r['y_sharpe']:>+7.2f} {r['y_maxdd']:>+7.1%} {r['y_avg']:>6.2f}")
    print(f"\n  SELECTED: {selected['variant']} + adaptive Y")
    print(f"  final=${y['final']:,.2f} profit=${y['profit']:,.2f} sharpe={y['sharpe']:+.2f} maxDD={y['maxdd']:.1%}")
    OUT.write_text(json.dumps({'base_config':BASE,'adaptive_y':Y_CFG,'rows':rows,'selected':selected,'selected_yearly':yearly,'elapsed_seconds':time.time()-t0},indent=2,default=float))
    print(f"  saved -> {OUT}\n  elapsed={time.time()-t0:.1f}s")

if __name__=='__main__':
    main()
