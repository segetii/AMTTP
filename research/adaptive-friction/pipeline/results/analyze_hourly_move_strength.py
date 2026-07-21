"""Analyze move strength quantities for hourly trading.

Answers: do we know how strong each move is, and which quantities help?

Uses the best raw corrected hourly config from the full sweep:
  daily_size, q_daily=0.70, q_hourly=0.50, SL=1.0σ, TP=1.5σ.
No orders are placed.
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS
from test_daily_geometry_stop_tp_ohlc import build_daily_geometry, fetch_futures_ohlcv

OUT = Path(OUT_DIR) / 'hourly_move_strength_diagnostics.json'
QH = 0.50
QD = 0.70
SL_SIGMA = 1.00
TP_SIGMA = 1.50
RT_COST = 2.0 / 1e4
FUND_HOUR = (0.5 / 24.0) / 1e4


def _quantile(x, cal):
    cal = np.asarray(cal[np.isfinite(cal)], dtype=float)
    if len(cal) == 0 or not np.isfinite(x):
        return np.nan
    return float((cal <= abs(x)).mean())


def _bin_table(df, col):
    out=[]
    edges=[0.0,0.5,0.7,0.8,0.9,0.95,1.01]
    labels=['0-50','50-70','70-80','80-90','90-95','95-100']
    for lo,hi,lab in zip(edges[:-1],edges[1:],labels):
        s=df[(df[col]>=lo)&(df[col]<hi)]
        if len(s)==0: continue
        out.append(dict(bin=lab, n=int(len(s)), win_rate=float((s['net_return']>0).mean()),
                        avg_net=float(s['net_return'].mean()), median_net=float(s['net_return'].median()),
                        avg_mfe=float(s['mfe'].mean()), avg_mae=float(s['mae'].mean()),
                        stop_rate=float((s['exit_reason']=='stop').mean()), tp_rate=float((s['exit_reason']=='tp').mean())))
    return out


def main():
    t0=time.time()
    print('='*100)
    print('  HOURLY MOVE STRENGTH DIAGNOSTICS')
    print('='*100)
    df_1h, comp_raw, _ = build_daily_geometry()
    ohlc = fetch_futures_ohlcv()
    common_start=comp_raw.dropna().index.min(); common_end=comp_raw.dropna().index.max()
    ohlc=ohlc[(ohlc.index>=common_start)&(ohlc.index<=common_end)&(ohlc.index>=pd.Timestamp(TEST_START))].copy()
    idx=df_1h.index
    train_1h=(idx>=TRAIN_START)&(idx<TEST_START)
    train_idx=np.where(train_1h)[0]
    calib_mask=np.zeros(len(df_1h), dtype=bool); calib_mask[train_idx[-CALIB_BARS:]]=True
    hourly_cal=comp_raw[calib_mask].abs().dropna().values
    sig_shifted=comp_raw.shift(1)
    qh_th=float(pd.Series(hourly_cal).quantile(QH))

    daily_sig=comp_raw.groupby(comp_raw.index.normalize()).last()
    all_ohlc=fetch_futures_ohlcv()
    all_days=pd.Index(sorted(all_ohlc.index.normalize().unique()))
    calib_days=all_days[(all_days>=pd.Timestamp(TRAIN_START))&(all_days<pd.Timestamp(TEST_START))]
    ret_daily=all_ohlc['close'].pct_change().fillna(0.0).groupby(all_ohlc.index.normalize()).sum()
    daily_vol=float(ret_daily.reindex(calib_days).std())
    daily_cal=daily_sig.reindex(calib_days).abs().dropna().values
    qd_th=float(pd.Series(daily_cal).quantile(QD))
    sl=SL_SIGMA*daily_vol; tp=TP_SIGMA*daily_vol

    trades=[]
    pos=0; size=1.0; entry=0.0; entry_ts=None; entry_hsig=np.nan; entry_dsig=np.nan; stop_price=0.0; take_price=0.0
    mfe=0.0; mae=0.0; active_hours=0
    for ts,row in ohlc.iterrows():
        hs=float(sig_shifted.get(ts, np.nan)) if np.isfinite(sig_shifted.get(ts, np.nan)) else np.nan
        hactive=np.isfinite(hs) and abs(hs)>=qh_th
        hpos=1 if np.isfinite(hs) and hs>0 else (-1 if np.isfinite(hs) else 0)
        prev_day=ts.normalize()-pd.Timedelta(days=1)
        ds=float(daily_sig.get(prev_day, np.nan)) if np.isfinite(daily_sig.get(prev_day, np.nan)) else np.nan
        dactive=np.isfinite(ds) and abs(ds)>=qd_th
        dpos=1 if np.isfinite(ds) and ds>0 else (-1 if np.isfinite(ds) else 0)
        scale=1.0 if (dactive and hpos==dpos) else (0.5 if hactive and not dactive else 0.0)
        if hactive and dactive and hpos != dpos:
            hactive=False
        if pos != 0:
            active_hours += 1
            if pos > 0:
                cur_mfe=float(row['high']/entry-1.0); cur_mae=float(row['low']/entry-1.0)
                stop_hit=float(row['low'])<=stop_price; tp_hit=float(row['high'])>=take_price
            else:
                cur_mfe=float(entry/row['low']-1.0); cur_mae=float(entry/row['high']-1.0)
                stop_hit=float(row['high'])>=stop_price; tp_hit=float(row['low'])<=take_price
            mfe=max(mfe, cur_mfe); mae=min(mae, cur_mae)
            exit_ret=None; reason=None
            if stop_hit and tp_hit:
                exit_ret=-sl; reason='stop'
            elif stop_hit:
                exit_ret=-sl; reason='stop'
            elif tp_hit:
                exit_ret=tp; reason='tp'
            elif hactive and hpos == -pos:
                op=float(row['open'])
                exit_ret=(op/entry-1.0) if pos>0 else (entry/op-1.0); reason='signal_exit'
            if exit_ret is not None:
                net=size*(exit_ret-RT_COST-active_hours*FUND_HOUR)
                trades.append(dict(entry_time=str(entry_ts), exit_time=str(ts), side='LONG' if pos>0 else 'SHORT',
                                   size=size, active_hours=active_hours, entry_hourly_signal=entry_hsig,
                                   entry_daily_signal=entry_dsig, hourly_abs=abs(entry_hsig), daily_abs=abs(entry_dsig) if np.isfinite(entry_dsig) else np.nan,
                                   hourly_q=_quantile(entry_hsig,hourly_cal), daily_q=_quantile(entry_dsig,daily_cal),
                                   daily_confirm=bool(np.isfinite(entry_dsig) and abs(entry_dsig)>=qd_th and np.sign(entry_dsig)==pos),
                                   gross_return=exit_ret, net_return=net, mfe=mfe, mae=mae, exit_reason=reason))
                pos=0; size=1.0; entry=0.0; entry_ts=None; active_hours=0; mfe=0.0; mae=0.0
        if pos == 0 and hactive:
            pos=hpos; size=scale if scale>0 else 1.0; entry=float(row['open']); entry_ts=ts; entry_hsig=hs; entry_dsig=ds
            if pos>0:
                stop_price=entry*(1-sl); take_price=entry*(1+tp)
            else:
                stop_price=entry*(1+sl); take_price=entry*(1-tp)
    df=pd.DataFrame(trades)
    if len(df)==0:
        raise RuntimeError('No trades produced')
    df['strength_score']=df['hourly_q']*(1.0+df['daily_q'].fillna(0.0))*(1.0+df['daily_confirm'].astype(float))
    corr_cols=['hourly_abs','daily_abs','hourly_q','daily_q','strength_score','active_hours','mfe','mae']
    corr={c:float(df[c].corr(df['net_return'])) for c in corr_cols if c in df and df[c].notna().sum()>3}
    summary=dict(n_trades=int(len(df)), win_rate=float((df['net_return']>0).mean()), avg_net=float(df['net_return'].mean()),
                 median_net=float(df['net_return'].median()), avg_mfe=float(df['mfe'].mean()), avg_mae=float(df['mae'].mean()),
                 stop_rate=float((df['exit_reason']=='stop').mean()), tp_rate=float((df['exit_reason']=='tp').mean()),
                 signal_exit_rate=float((df['exit_reason']=='signal_exit').mean()))
    result=dict(config=dict(q_hourly=QH,q_daily=QD,sl_sigma=SL_SIGMA,tp_sigma=TP_SIGMA,daily_vol=daily_vol,sl=sl,tp=tp),
                summary=summary, correlations=corr, by_hourly_q=_bin_table(df,'hourly_q'), by_daily_q=_bin_table(df,'daily_q'),
                by_strength_score=_bin_table(df.assign(strength_score_q=df['strength_score'].rank(pct=True)),'strength_score_q'),
                top_winners=df.sort_values('net_return',ascending=False).head(20).to_dict(orient='records'),
                top_losers=df.sort_values('net_return').head(20).to_dict(orient='records'),
                elapsed_seconds=time.time()-t0)
    OUT.write_text(json.dumps(result,indent=2,default=float))
    print(f"  trades={summary['n_trades']} win={summary['win_rate']:.1%} avg_net={summary['avg_net']:.3%} stop={summary['stop_rate']:.1%} tp={summary['tp_rate']:.1%} signal_exit={summary['signal_exit_rate']:.1%}")
    print('\n  Correlation with net return:')
    for k,v in corr.items(): print(f'    {k:<16} {v:+.4f}')
    print('\n  By hourly signal quantile:')
    for r in result['by_hourly_q']:
        print(f"    q {r['bin']:<6} n={r['n']:>4} win={r['win_rate']:.1%} avg={r['avg_net']:+.3%} mfe={r['avg_mfe']:.2%} mae={r['avg_mae']:.2%}")
    print('\n  By combined strength score quantile:')
    for r in result['by_strength_score']:
        print(f"    q {r['bin']:<6} n={r['n']:>4} win={r['win_rate']:.1%} avg={r['avg_net']:+.3%} mfe={r['avg_mfe']:.2%} mae={r['avg_mae']:.2%}")
    print(f"\n  saved -> {OUT}\n  elapsed={time.time()-t0:.1f}s")

if __name__=='__main__':
    main()
