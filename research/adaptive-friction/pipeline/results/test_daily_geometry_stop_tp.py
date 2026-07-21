"""Daily geometry forecast + stop-loss / take-profit test.

Purpose
-------
Use the engine as an early-warning layer at the DAILY level:
  - build daily signal from hourly geometry (E7/B1/E6 composite)
  - predict next-day ETH direction
  - trade next day with intraday stop-loss / take-profit using hourly close path
  - compare thresholds and SL/TP settings under Binance-style low-cost maker model

This answers: can we know the opportunity/risk before the day starts, and set
stop-loss / take-profit instead of blindly reacting hourly?

Assumptions
-----------
- Uses hourly closes only, so SL/TP are approximate close-path stops, not true
  tick/high-low stops.
- Position is opened at the start of the next day and closed at stop/TP or day end.
- K=5 leverage, $1,000 start.
- Low-cost Binance maker: 2 bps round-trip (1.5 fee + 0.5 slippage), 0.5 bps/day funding.
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

from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS, build_intraday_state_panel  # noqa: E402
from run_crypto_pairs_v34_full_combined import build_1h_df, OUT_DIR, TEST_START, TRAIN_START  # noqa: E402
from run_robustness_validation import _make_cached_fetch, _cached_fetch_binance_funding       # noqa: E402
import run_crypto_pairs_v34_full_combined as _v34mod                                         # noqa: E402

CACHE_FG = Path(r'C:\amttp\data\geometric_extractor_engine_arrays_funded_v58_fg.npz')
INIT = 1000.0
K_LEV = 5.0
RT_COST = 2.0 / 1e4          # 2 bps round trip
FUND_DAY = 0.5 / 1e4         # 0.5 bps per active day
Q_GRID = [0.50, 0.60, 0.70, 0.80, 0.90]
SL_MULT = [0.5, 0.75, 1.0, 1.25, 1.5]
TP_MULT = [0.75, 1.0, 1.5, 2.0, 3.0]


def _z(s: pd.Series, calib_mask: np.ndarray) -> pd.Series:
    return (s - s[calib_mask].mean()) / max(s[calib_mask].std(), 1e-12)


def _equity(r: pd.Series, init=INIT):
    r = r.fillna(0.0).clip(lower=-0.95)
    eq = init * (1 + r).cumprod()
    dd = (eq - eq.cummax()) / eq.cummax()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    return dict(final=float(eq.iloc[-1]), profit=float(eq.iloc[-1]-init),
                profit_pct=float(eq.iloc[-1]/init-1), cagr=float((eq.iloc[-1]/init)**(1/years)-1),
                sharpe=float(np.sqrt(365.25)*r.mean()/r.std()) if r.std()>0 else 0.0,
                maxdd=float(dd.min()), eq=eq)


def _period(eq: pd.Series, freq: str):
    out=[]
    for dt, s in eq.groupby(pd.Grouper(freq=freq)):
        if len(s)<2: continue
        out.append(dict(period=str(dt.date()), start=float(s.iloc[0]), end=float(s.iloc[-1]),
                        profit=float(s.iloc[-1]-s.iloc[0]), return_pct=float(s.iloc[-1]/s.iloc[0]-1)))
    return out


def _simulate_daily(sig_daily: pd.Series, ret_hourly: pd.Series, q: float, sl, tp,
                    calib_days: pd.Index, test_days: pd.Index):
    """Trade next day using previous daily signal, approximate intraday close-path SL/TP."""
    abs_cal = sig_daily.reindex(calib_days).abs().dropna()
    th = float(abs_cal.quantile(q)) if len(abs_cal) else np.inf
    day_rets = []
    hit_sl = hit_tp = active_n = long_n = short_n = 0
    for day in test_days:
        prev_day = day - pd.Timedelta(days=1)
        s = sig_daily.get(prev_day, np.nan)
        if not np.isfinite(s) or abs(s) < th:
            day_rets.append((day, 0.0)); continue
        pos = 1.0 if s > 0 else -1.0
        active_n += 1; long_n += int(pos > 0); short_n += int(pos < 0)
        hrs = ret_hourly[ret_hourly.index.normalize() == day]
        if len(hrs) == 0:
            day_rets.append((day, 0.0)); continue
        signed_path = pos * hrs.cumsum()
        exit_ret = float(signed_path.iloc[-1])
        if sl is not None or tp is not None:
            for v in signed_path.values:
                if sl is not None and v <= -sl:
                    exit_ret = -sl; hit_sl += 1; break
                if tp is not None and v >= tp:
                    exit_ret = tp; hit_tp += 1; break
        # cost: round-trip + one-day funding, then leverage applied outside
        net = exit_ret - RT_COST - FUND_DAY
        day_rets.append((day, net))
    out = pd.Series(dict(day_rets)).sort_index()
    stats = dict(threshold=th, active_days=active_n, long_days=long_n, short_days=short_n,
                 hit_sl=hit_sl, hit_tp=hit_tp,
                 active_rate=active_n/max(len(test_days),1), long_rate=long_n/max(active_n,1), short_rate=short_n/max(active_n,1))
    return out, stats


def main():
    BAR='='*100
    print(BAR)
    print('  DAILY GEOMETRY FORECAST + STOP LOSS / TAKE PROFIT')
    print(BAR)
    t0=time.time()

    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)
    df_1h, _ = build_1h_df(start='2021-01-01', end='2026-05-01')
    fund = _cached_fetch_binance_funding()
    X = np.nan_to_num(build_intraday_state_panel(df_1h, fund.get('BTCUSDT'), fund.get('ETHUSDT')))
    idx=df_1h.index; ret=df_1h['ret_eth'].fillna(0.0)
    train_1h=(idx>=TRAIN_START)&(idx<TEST_START)
    train_idx=np.where(train_1h)[0]
    calib_mask=np.zeros(len(df_1h), dtype=bool); calib_mask[train_idx[-CALIB_BARS:]]=True
    test_mask=idx>=TEST_START

    z=np.load(CACHE_FG)
    F_all=z['F_all']; G_all=z['G_all']; valid=z['valid']
    T,N,d=X.shape; F_flat=F_all.reshape(T,-1); G_flat=G_all.reshape(T,-1); Xt_flat=X.reshape(T,-1)
    dX=np.full_like(X,np.nan,dtype=np.float32); dX[:-1]=X[1:]-X[:-1]
    dX_flat=dX.reshape(T,-1); dX_prev=np.roll(dX_flat,1,axis=0); dX_prev[0]=np.nan
    # E7
    a=2/(32+1); Fbar=np.full_like(F_flat,np.nan); Fbar[0]=F_flat[0]
    for t in range(1,T):
        if np.isnan(F_flat[t]).any(): Fbar[t]=Fbar[t-1]
        elif np.isnan(Fbar[t-1]).any(): Fbar[t]=F_flat[t]
        else: Fbar[t]=(1-a)*Fbar[t-1]+a*F_flat[t]
    E7=pd.Series(np.einsum('ti,ti->t',Fbar,dX_prev),index=idx)
    B1=pd.Series(np.einsum('ti,ti->t',G_flat,dX_prev),index=idx)
    Xc=Xt_flat[calib_mask]; mu=Xc.mean(0); Sinv=np.linalg.inv(np.cov(Xc,rowvar=False)+1e-6*np.eye(N*d))
    e6=np.full(T,np.nan)
    for t in range(1,T):
        if valid[t]:
            try: e6[t]=float(-(F_flat[t]@(Sinv@(Xt_flat[t]-mu))))
            except Exception: pass
    E6=pd.Series(e6,index=idx)

    comp_hourly = (_z(E7,calib_mask)+_z(B1,calib_mask)+_z(E6,calib_mask))/3.0
    # Daily signal variants: last signal of day and mean signal of day.
    daily_last = comp_hourly.groupby(comp_hourly.index.normalize()).last()
    daily_mean = comp_hourly.groupby(comp_hourly.index.normalize()).mean()
    daily_absmax = comp_hourly.groupby(comp_hourly.index.normalize()).apply(lambda s: s.loc[s.abs().idxmax()] if len(s.dropna()) else np.nan)
    daily_ret = ret.groupby(ret.index.normalize()).sum()

    days = pd.Index(sorted(daily_ret.index.unique()))
    calib_days = days[(days >= pd.Timestamp(TRAIN_START)) & (days < pd.Timestamp(TEST_START))]
    test_days = days[days >= pd.Timestamp(TEST_START)]
    daily_vol = float(daily_ret.reindex(calib_days).std())
    print(f"\n  calib daily σ = {daily_vol:.2%}; test days={len(test_days)}")

    # Forecast diagnostics for next-day return.
    target_next = daily_ret.shift(-1)
    for name, sig in [('last',daily_last), ('mean',daily_mean), ('absmax',daily_absmax)]:
        ix = sig.reindex(test_days).dropna().index.intersection(target_next.reindex(test_days).dropna().index)
        pear = sig.reindex(ix).corr(target_next.reindex(ix))
        sic = (np.sign(sig.reindex(ix))*np.sign(target_next.reindex(ix)) > 0).mean()
        print(f"  daily {name:<6} forecast: pearson={pear:+.4f} signIC={sic:.1%}")

    results=[]
    signals={'last':daily_last,'mean':daily_mean,'absmax':daily_absmax}
    for sig_name, sig in signals.items():
        # no SL/TP baseline plus SL/TP grid
        combos=[(None,None)] + [(sl*daily_vol,tp*daily_vol) for sl,tp in itertools.product(SL_MULT,TP_MULT)]
        for q in Q_GRID:
            for sl,tp in combos:
                r, info = _simulate_daily(sig, ret, q, sl, tp, calib_days, test_days)
                m = _equity(K_LEV*r)
                results.append(dict(signal=sig_name, q=q,
                                    sl_mult=None if sl is None else sl/daily_vol,
                                    tp_mult=None if tp is None else tp/daily_vol,
                                    sl=None if sl is None else sl, tp=None if tp is None else tp,
                                    final=m['final'], profit=m['profit'], cagr=m['cagr'], sharpe=m['sharpe'], maxdd=m['maxdd'],
                                    **info))
    results=sorted(results,key=lambda x:(x['final'],x['sharpe']),reverse=True)

    print(f"\n{BAR}")
    print('  DAILY STRATEGY RESULTS — K=5, $1,000, low-cost maker')
    print(BAR)
    print(f"  {'Rank':>4} {'Sig':<6} {'q':>4} {'SLσ':>5} {'TPσ':>5} {'Active':>7} {'Long':>6} {'Final$':>10} {'Profit$':>10} {'Sharpe':>8} {'MaxDD':>8} {'SL/TP':>9}")
    for i,r in enumerate(results[:20],1):
        sls='None' if r['sl_mult'] is None else f"{r['sl_mult']:.2f}"
        tps='None' if r['tp_mult'] is None else f"{r['tp_mult']:.2f}"
        print(f"  {i:>4} {r['signal']:<6} {r['q']:>4.2f} {sls:>5} {tps:>5} {r['active_rate']:>6.1%} {r['long_rate']:>5.1%} "
              f"{r['final']:>10,.0f} {r['profit']:>10,.0f} {r['sharpe']:>+8.2f} {r['maxdd']:>+7.1%} {r['hit_sl']:>3}/{r['hit_tp']:<3}")

    best=results[0]
    best_sig=signals[best['signal']]
    r, info = _simulate_daily(best_sig, ret, best['q'], best['sl'], best['tp'], calib_days, test_days)
    m=_equity(K_LEV*r)
    print(f"\n  BEST: signal={best['signal']} q={best['q']:.2f} SL={best['sl_mult']}σ TP={best['tp_mult']}σ final=${best['final']:,.2f}")
    print(f"\n  YEARLY PROFIT — BEST DAILY STRATEGY")
    print(f"  {'Year':<12} {'Start $':>12} {'End $':>12} {'Profit $':>12} {'Return':>9}")
    for row in _period(m['eq'],'Y'):
        print(f"  {row['period']:<12} {row['start']:>12,.2f} {row['end']:>12,.2f} {row['profit']:>12,.2f} {row['return_pct']:>8.1%}")

    out=Path(OUT_DIR)/'daily_geometry_stop_tp_results.json'
    out.write_text(json.dumps({'daily_vol':daily_vol,'best':best,'top20':results[:20], 'all_results':results, 'best_yearly':_period(m['eq'],'Y')},indent=2,default=float))
    print(f"\n  saved -> {out}\n  elapsed={time.time()-t0:.1f}s\n{BAR}")

if __name__=='__main__':
    main()
