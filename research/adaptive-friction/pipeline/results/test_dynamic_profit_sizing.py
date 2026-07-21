"""Dynamic profit position sizing for the corrected hourly system.

Implements the previous winning idea in the current hourly engine:

position_size_t = K_base × S_strength × Q_quality × V_vol × L_gamma × Y_drawdown

Where:
  S_strength = hourly/daily move strength score
  Q_quality  = rolling realized strategy quality
  V_vol      = inverse realized-vol target scaling
  L_gamma    = adaptive-friction stress dial (linear or convex proxy)
  Y_drawdown = existing adaptive equity brake

No live/paper orders. Historical simulation only.
"""
from __future__ import annotations
import sys, json, time, itertools
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, TEST_START
from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS
from test_daily_geometry_stop_tp_ohlc import build_daily_geometry, fetch_futures_ohlcv
from test_psi_adaptive_y import simulate_unit_with_psi, BASE
from simulate_adaptive_y_drawdown_brake import adaptive_equity
from simulate_hourly_2h_daily_risk_ohlc_fast import period

OUT = Path(OUT_DIR) / 'dynamic_profit_sizing_results.json'
Y_CFG = dict(dd_soft=0.05, dd_stop=0.20, y_floor=0.25)
K_GRID = [2.0, 3.0, 5.0]
STRENGTH_CAP_GRID = [1.5, 2.0, 2.5, 3.0]
VOL_CAP_GRID = [1.5, 2.0, 3.0]
GAMMA_MODE_GRID = ['linear', 'convex']
TOTAL_CAP_GRID = [2.0, 3.0, 4.0]


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


def _percentile_against(values, cal):
    cal = np.asarray(cal[np.isfinite(cal)], dtype=float)
    vals = np.asarray(values, dtype=float)
    if len(cal) == 0:
        return np.zeros_like(vals)
    return np.searchsorted(np.sort(cal), vals, side='right') / float(len(cal))


def equity_no_y(unit, K):
    r=(K*unit).fillna(0).clip(lower=-0.95)
    eq=1000.0*(1+r).cumprod(); dd=(eq-eq.cummax())/eq.cummax()
    years=max((eq.index[-1]-eq.index[0]).days/365.25,1e-9)
    return dict(final=float(eq.iloc[-1]), profit=float(eq.iloc[-1]-1000.0),
                sharpe=float(np.sqrt(24*365.25)*r.mean()/r.std()) if r.std()>0 else 0.0,
                maxdd=float(dd.min()), cagr=float((eq.iloc[-1]/1000.0)**(1/years)-1), eq=eq)


def prepare():
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ohlc_all = fetch_futures_ohlcv()
    common_start=comp_raw.dropna().index.min(); common_end=comp_raw.dropna().index.max()
    ohlc=ohlc_all[(ohlc_all.index>=common_start)&(ohlc_all.index<=common_end)&(ohlc_all.index>=pd.Timestamp(TEST_START))].copy()
    hours=ohlc.index
    op=ohlc['open'].values.astype(float); hi=ohlc['high'].values.astype(float); lo=ohlc['low'].values.astype(float); cl=ohlc['close'].values.astype(float)

    hourly_cal=comp_raw[calib_mask].abs().dropna()
    sig_shifted=comp_raw.shift(1).reindex(hours).fillna(0.0).values.astype(float)
    hth=float(hourly_cal.quantile(BASE['q_hourly']))
    hpos=np.where(np.abs(sig_shifted)>=hth, np.sign(sig_shifted).astype(int), 0)
    hq=_percentile_against(np.abs(sig_shifted), hourly_cal.values)

    daily_sig=comp_raw.groupby(comp_raw.index.normalize()).last()
    all_days=pd.Index(sorted(ohlc_all.index.normalize().unique()))
    calib_days=all_days[(all_days>=pd.Timestamp(TRAIN_START))&(all_days<pd.Timestamp(TEST_START))]
    ret_daily=ohlc_all['close'].pct_change().fillna(0.0).groupby(ohlc_all.index.normalize()).sum()
    daily_vol=float(ret_daily.reindex(calib_days).std())
    daily_cal=daily_sig.reindex(calib_days).abs().dropna()
    dth=float(daily_cal.quantile(BASE['q_daily']))
    prev_days=hours.normalize()-pd.Timedelta(days=1)
    ds_vals=daily_sig.reindex(prev_days).fillna(0.0).values.astype(float)
    dpos=np.sign(ds_vals).astype(int); dactive=np.abs(ds_vals)>=dth
    dq=_percentile_against(np.abs(ds_vals), daily_cal.values)
    confirm=(dactive & (dpos==hpos) & (hpos!=0)).astype(float)

    # Base unit stream for causal quality estimation.
    unit0_arr, counts0 = simulate_unit_with_psi(op,hi,lo,cl,hpos,dpos,dactive,np.ones(len(hours)),BASE['sl_mult']*daily_vol,BASE['tp_mult']*daily_vol)
    unit0=pd.Series(unit0_arr,index=hours)

    roll_mu=unit0.rolling(240,min_periods=72).mean().shift(1).fillna(0.0)
    roll_sd=unit0.rolling(240,min_periods=72).std().shift(1).replace(0,np.nan).fillna(unit0.std())
    roll_sh=roll_mu/roll_sd*np.sqrt(24*365.25)
    q_quality=0.25 + 1.25*_sigmoid(roll_sh.values*0.50)

    # Volatility stress / gamma proxy from realized ETH vol percentile.
    ret_h=ohlc_all['close'].pct_change().fillna(0.0)
    rv=ret_h.rolling(24,min_periods=12).std().shift(1)
    rv_cal=rv[(rv.index>=pd.Timestamp(TRAIN_START))&(rv.index<pd.Timestamp(TEST_START))].dropna()
    rv_h=rv.reindex(hours).ffill().fillna(rv_cal.median())
    stress_rank=_percentile_against(rv_h.values, rv_cal.values)
    target_vol=float(rv_cal.median())
    vol_base=(target_vol/rv_h.clip(lower=1e-8)).values

    strength_raw = hq * (1.0 + dq) * (1.0 + confirm) / 4.0
    return dict(hours=hours, op=op, hi=hi, lo=lo, cl=cl, hpos=hpos, dpos=dpos, dactive=dactive,
                daily_vol=daily_vol, unit0=unit0, counts0=counts0, strength_raw=strength_raw,
                q_quality=q_quality, vol_base=vol_base, stress_rank=stress_rank)


def main():
    t0=time.time()
    print('='*100)
    print('  DYNAMIC PROFIT POSITION SIZING')
    print('='*100)
    p=prepare()
    print(f"  base entries={p['counts0']['entries']} daily_vol={p['daily_vol']:.2%}")
    rows=[]
    configs=list(itertools.product(K_GRID, STRENGTH_CAP_GRID, VOL_CAP_GRID, GAMMA_MODE_GRID, TOTAL_CAP_GRID))
    for K,scap,vcap,gmode,tcap in configs:
        strength_mult=np.clip(0.25 + scap*p['strength_raw'], 0.25, scap)
        vol_mult=np.clip(p['vol_base'], 0.25, vcap)
        if gmode=='linear':
            gamma=np.clip(1.5-p['stress_rank'], 0.5, 1.2)
        else:
            delta=1.2-p['stress_rank']
            gamma=np.clip(np.sign(delta)*delta*delta, 0.4, 1.3)
        size_mult=np.clip(strength_mult*p['q_quality']*vol_mult*gamma, 0.0, tcap)
        unit_arr, counts=simulate_unit_with_psi(p['op'],p['hi'],p['lo'],p['cl'],p['hpos'],p['dpos'],p['dactive'],size_mult,BASE['sl_mult']*p['daily_vol'],BASE['tp_mult']*p['daily_vol'])
        unit=pd.Series(unit_arr,index=p['hours'])
        raw=equity_no_y(unit,K)
        y=adaptive_equity(unit,K,Y_CFG['dd_soft'],Y_CFG['dd_stop'],Y_CFG['y_floor'])
        rows.append(dict(K=K,strength_cap=scap,vol_cap=vcap,gamma_mode=gmode,total_cap=tcap,
                         avg_size=float(np.mean(size_mult[p['hpos']!=0])),p95_size=float(np.quantile(size_mult[p['hpos']!=0],0.95)),
                         raw_final=raw['final'],raw_sharpe=raw['sharpe'],raw_maxdd=raw['maxdd'],
                         y_final=y['final'],y_profit=y['profit'],y_sharpe=y['sharpe'],y_maxdd=y['maxdd'],y_avg=y['avg_y'],
                         **counts))
    top=sorted(rows,key=lambda r:(r['y_final'],r['y_sharpe']),reverse=True)
    safe=[r for r in rows if r['y_maxdd']>=-0.40 and r['y_sharpe']>=1.0]
    safe=sorted(safe,key=lambda r:(r['y_final'],r['y_sharpe']),reverse=True)
    selected=safe[0] if safe else top[0]

    # recompute selected for yearly
    K=selected['K']; scap=selected['strength_cap']; vcap=selected['vol_cap']; gmode=selected['gamma_mode']; tcap=selected['total_cap']
    strength_mult=np.clip(0.25 + scap*p['strength_raw'],0.25,scap)
    vol_mult=np.clip(p['vol_base'],0.25,vcap)
    gamma=np.clip(1.5-p['stress_rank'],0.5,1.2) if gmode=='linear' else np.clip(np.sign(1.2-p['stress_rank'])*(1.2-p['stress_rank'])**2,0.4,1.3)
    size_mult=np.clip(strength_mult*p['q_quality']*vol_mult*gamma,0.0,tcap)
    unit_arr,counts=simulate_unit_with_psi(p['op'],p['hi'],p['lo'],p['cl'],p['hpos'],p['dpos'],p['dactive'],size_mult,BASE['sl_mult']*p['daily_vol'],BASE['tp_mult']*p['daily_vol'])
    unit=pd.Series(unit_arr,index=p['hours'])
    y=adaptive_equity(unit,K,Y_CFG['dd_soft'],Y_CFG['dd_stop'],Y_CFG['y_floor'])
    yearly=period(y['eq'],'Y')

    print(f"\n  TOP SAFE DYNAMIC SIZING (Y maxDD >= -40%)")
    print(f"  {'Rank':>4} {'K':>3} {'S':>4} {'V':>4} {'G':<6} {'Cap':>4} {'AvgSz':>6} {'Final$':>10} {'Sharpe':>8} {'MaxDD':>8}")
    for i,r in enumerate(safe[:20],1):
        print(f"  {i:>4} {r['K']:>3.0f} {r['strength_cap']:>4.1f} {r['vol_cap']:>4.1f} {r['gamma_mode']:<6} {r['total_cap']:>4.1f} {r['avg_size']:>6.2f} {r['y_final']:>10,.0f} {r['y_sharpe']:>+8.2f} {r['y_maxdd']:>+7.1%}")
    print(f"\n  SELECTED: K={K} strength_cap={scap} vol_cap={vcap} gamma={gmode} total_cap={tcap}")
    print(f"  final=${y['final']:,.2f} profit=${y['profit']:,.2f} sharpe={y['sharpe']:+.2f} maxDD={y['maxdd']:.1%} avgY={y['avg_y']:.2f}")
    print('  yearly:')
    for row in yearly:
        print(f"    {row['period']}: start=${row['start']:,.2f} end=${row['end']:,.2f} profit=${row['profit']:,.2f} ret={row['return_pct']:.1%}")
    OUT.write_text(json.dumps({'formula':'K × strength × rolling_quality × vol_target × gamma_dial × adaptive_Y',
                               'base_config':BASE,'adaptive_y':Y_CFG,'top_safe':safe[:30],'top_by_final':top[:30],
                               'selected':selected,'selected_counts':counts,'selected_yearly':yearly,
                               'elapsed_seconds':time.time()-t0},indent=2,default=float))
    print(f"\n  saved -> {OUT}\n  elapsed={time.time()-t0:.1f}s")

if __name__=='__main__':
    main()
