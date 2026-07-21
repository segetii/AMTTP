"""Fast full sweep: hourly trading with 2h geometry entries and daily risk tuning.

This is the corrected interpretation:
- Trading lifecycle is hourly.
- The 2h/hourly geometry signal decides entry/flip timing.
- The daily layer only confirms/filters/sizes risk and supplies SL/TP scale.
- True Binance futures OHLC high/low is used for stop-loss/take-profit.
- No paper/live orders.
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


def equity_from_unit(unit_ret: pd.Series, K: float):
    r = (K * unit_ret).fillna(0.0).clip(lower=-0.95)
    eq = INIT * (1.0 + r).cumprod()
    dd = (eq - eq.cummax()) / eq.cummax()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    return dict(final=float(eq.iloc[-1]), profit=float(eq.iloc[-1]-INIT), profit_pct=float(eq.iloc[-1]/INIT-1),
                cagr=float((eq.iloc[-1]/INIT)**(1/years)-1),
                sharpe=float(np.sqrt(24*365.25)*r.mean()/r.std()) if r.std()>0 else 0.0,
                maxdd=float(dd.min()), eq=eq)


def period(eq, freq):
    out=[]
    for dt, s in eq.groupby(pd.Grouper(freq=freq)):
        if len(s)<2: continue
        out.append(dict(period=str(dt.date()), start=float(s.iloc[0]), end=float(s.iloc[-1]),
                        profit=float(s.iloc[-1]-s.iloc[0]), return_pct=float(s.iloc[-1]/s.iloc[0]-1)))
    return out


def simulate_unit(op, hi, lo, cl, hpos_arr, dpos_arr, dactive_arr, sl, tp, mode):
    n=len(op)
    ret=np.zeros(n, dtype=np.float64)
    pos=0.0; size=1.0; entry=0.0; stop_price=0.0; take_price=0.0
    counts=dict(entries=0, exits=0, flips=0, longs=0, shorts=0, stop=0, tp=0, signal_exit=0, close_end=0,
                skipped_daily_filter=0, active_hours=0)
    for i in range(n):
        hpos = hpos_arr[i]
        hactive = hpos != 0
        dpos = dpos_arr[i]
        dactive = dactive_arr[i]
        scale = 1.0
        if mode == 'daily_filter':
            if dactive and hactive and hpos != dpos:
                hactive = False; hpos = 0; counts['skipped_daily_filter'] += 1
        elif mode == 'daily_size':
            if hactive:
                if dactive and hpos == dpos:
                    scale = 1.0
                elif dactive and hpos != dpos:
                    hactive = False; hpos = 0; counts['skipped_daily_filter'] += 1
                else:
                    scale = 0.5
        if pos != 0:
            counts['active_hours'] += 1
            exit_ret=None; reason=None
            if pos > 0:
                stop_hit = lo[i] <= stop_price
                tp_hit = hi[i] >= take_price
                if stop_hit and tp_hit:
                    exit_ret = stop_price / entry - 1.0; reason='stop'
                elif stop_hit:
                    exit_ret = stop_price / entry - 1.0; reason='stop'
                elif tp_hit:
                    exit_ret = take_price / entry - 1.0; reason='tp'
            else:
                stop_hit = hi[i] >= stop_price
                tp_hit = lo[i] <= take_price
                if stop_hit and tp_hit:
                    exit_ret = entry / stop_price - 1.0; reason='stop'
                elif stop_hit:
                    exit_ret = entry / stop_price - 1.0; reason='stop'
                elif tp_hit:
                    exit_ret = entry / take_price - 1.0; reason='tp'
            if exit_ret is None and hactive and hpos == -pos:
                exit_ret = (op[i]/entry - 1.0) if pos > 0 else (entry/op[i] - 1.0)
                reason='signal_exit'; counts['flips'] += 1
            if exit_ret is not None:
                ret[i] += size * (exit_ret - RT_COST)
                counts[reason] += 1; counts['exits'] += 1
                pos=0.0; size=1.0; entry=0.0
            else:
                ret[i] += -size * FUND_HOUR
        if pos == 0 and hactive:
            pos=float(hpos); size=float(scale); entry=op[i]
            if pos > 0:
                stop_price = entry * (1.0 - sl); take_price = entry * (1.0 + tp); counts['longs'] += 1
            else:
                stop_price = entry * (1.0 + sl); take_price = entry * (1.0 - tp); counts['shorts'] += 1
            counts['entries'] += 1
    if pos != 0:
        i=n-1
        gross = (cl[i]/entry - 1.0) if pos > 0 else (entry/cl[i] - 1.0)
        ret[i] += size * (gross - RT_COST)
        counts['close_end'] += 1; counts['exits'] += 1
    return ret, counts


def main():
    BAR='='*100
    print(BAR)
    print('  FAST FULL SWEEP — HOURLY TRADING + 2H ENTRY + DAILY RISK + TRUE OHLC STOPS')
    print(BAR)
    t0=time.time()
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

    daily_sig=comp_raw.groupby(comp_raw.index.normalize()).last()
    days=pd.Index(sorted(ohlc.index.normalize().unique()))
    all_days=pd.Index(sorted(fetch_futures_ohlcv().index.normalize().unique()))
    calib_days=all_days[(all_days>=pd.Timestamp(TRAIN_START))&(all_days<pd.Timestamp(TEST_START))]
    ret_daily=fetch_futures_ohlcv()['close'].pct_change().fillna(0.0).groupby(fetch_futures_ohlcv().index.normalize()).sum()
    daily_vol=float(ret_daily.reindex(calib_days).std())
    daily_cal=daily_sig.reindex(calib_days).abs().dropna()

    prev_days=hours.normalize()-pd.Timedelta(days=1)
    ds_vals=daily_sig.reindex(prev_days).fillna(0.0).values.astype(float)
    dsign_all=np.sign(ds_vals).astype(int)

    hpos_by_q={}
    for qh in QH_GRID:
        th=float(hourly_cal.quantile(qh))
        hpos_by_q[qh]=np.where(np.abs(sig_shifted)>=th, np.sign(sig_shifted).astype(int), 0)
    dctx_by_q={}
    for qd in QD_GRID:
        th=float(daily_cal.quantile(qd))
        dctx_by_q[qd]=(dsign_all, np.abs(ds_vals)>=th)

    print(f'  bars={len(hours)} daily σ={daily_vol:.2%}; configs={len(MODES)*len(QD_GRID)*len(QH_GRID)*len(SL_GRID)*len(TP_GRID)} × K={len(K_GRID)}')
    results=[]
    configs=list(itertools.product(MODES, QD_GRID, QH_GRID, SL_GRID, TP_GRID))
    for n,(mode,qd,qh,slm,tpm) in enumerate(configs,1):
        if n % 100 == 0: print(f'    {n}/{len(configs)} t={time.time()-t0:.0f}s', flush=True)
        dpos,dactive=dctx_by_q[qd]
        unit_arr, counts=simulate_unit(op,hi,lo,cl,hpos_by_q[qh],dpos,dactive,slm*daily_vol,tpm*daily_vol,mode)
        unit=pd.Series(unit_arr,index=hours)
        for K in K_GRID:
            m=equity_from_unit(unit,K)
            results.append(dict(mode=mode,q_daily=qd,q_hourly=qh,sl_mult=slm,tp_mult=tpm,leverage=K,
                                final=m['final'],profit=m['profit'],profit_pct=m['profit_pct'],cagr=m['cagr'],
                                sharpe=m['sharpe'],maxdd=m['maxdd'],**counts))
    top=sorted(results,key=lambda r:(r['final'],r['sharpe']),reverse=True)
    safe=[r for r in results if r['leverage']==2.0 and r['maxdd']>=-0.35 and r['sharpe']>=1.0 and r['entries']>=100]
    safe=sorted(safe,key=lambda r:(r['final'],r['sharpe']),reverse=True)
    selected=safe[0] if safe else top[0]
    dpos,dactive=dctx_by_q[selected['q_daily']]
    unit_arr,counts=simulate_unit(op,hi,lo,cl,hpos_by_q[selected['q_hourly']],dpos,dactive,selected['sl_mult']*daily_vol,selected['tp_mult']*daily_vol,selected['mode'])
    unit=pd.Series(unit_arr,index=hours)
    m=equity_from_unit(unit,selected['leverage'])
    yearly=period(m['eq'],'Y'); quarterly=period(m['eq'],'Q')

    print(f"\n{BAR}\n  TOP BY FINAL\n{BAR}")
    print(f"  {'Rank':>4} {'Mode':<12} {'K':>3} {'qd':>4} {'qh':>4} {'SL':>4} {'TP':>4} {'Ent':>5} {'Final$':>10} {'Sharpe':>8} {'MaxDD':>8}")
    for i,r in enumerate(top[:20],1):
        print(f"  {i:>4} {r['mode']:<12} {r['leverage']:>3.0f} {r['q_daily']:>4.2f} {r['q_hourly']:>4.2f} {r['sl_mult']:>4.2f} {r['tp_mult']:>4.2f} {r['entries']:>5} {r['final']:>10,.0f} {r['sharpe']:>+8.2f} {r['maxdd']:>+7.1%}")
    print(f"\n{BAR}\n  TOP SAFE K=2\n{BAR}")
    for i,r in enumerate(safe[:20],1):
        print(f"  {i:>4} {r['mode']:<12} qd={r['q_daily']:.2f} qh={r['q_hourly']:.2f} SL={r['sl_mult']:.2f} TP={r['tp_mult']:.2f} entries={r['entries']:>4} final=${r['final']:>9,.0f} sharpe={r['sharpe']:+.2f} dd={r['maxdd']:+.1%}")
    print(f"\n  SELECTED HOURLY: {selected['mode']} K={selected['leverage']} qd={selected['q_daily']} qh={selected['q_hourly']} SL={selected['sl_mult']}σ TP={selected['tp_mult']}σ")
    print(f"  final=${m['final']:,.2f} profit=${m['profit']:,.2f} sharpe={m['sharpe']:+.2f} maxDD={m['maxdd']:.1%} entries={counts['entries']}")
    print('  yearly:')
    for y in yearly:
        print(f"    {y['period']}: start=${y['start']:,.2f} end=${y['end']:,.2f} profit=${y['profit']:,.2f} ret={y['return_pct']:.1%}")
    OUT.write_text(json.dumps({'top_by_final':top[:50], 'top_safe_k2':safe[:50], 'selected':selected, 'selected_counts':counts,
                               'selected_yearly':yearly, 'selected_quarterly':quarterly, 'daily_vol':daily_vol,
                               'elapsed_seconds':time.time()-t0},indent=2,default=float))
    print(f"\n  saved -> {OUT}\n  elapsed={time.time()-t0:.1f}s\n{BAR}")

if __name__=='__main__':
    main()
