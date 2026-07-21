"""Multi-hour forecast / holding test for geometry basket.

Question: does the engine see ahead a few hours before the move?

Tests E7/B1/E6 geometry basket as a signed ETH-perp forecast at horizons:
  H = 1,2,3,4,6,8,12,24 hours

For each H:
  signal at t = sign(mean(zscore(E7), zscore(B1), zscore(E6)))
  target     = cumulative ETH return t+1..t+H
  trade      = non-overlapping H-hour holds (rebalance every H hours)
  costs      = Binance-like low-cost maker and taker models

This separates true multi-hour predictive power from hourly churn.
"""
from __future__ import annotations
import sys, json, time
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS, build_intraday_state_panel, _stats  # noqa: E402
from run_crypto_pairs_v34_full_combined import build_1h_df, OUT_DIR, TEST_START, TRAIN_START  # noqa: E402
from run_robustness_validation import _make_cached_fetch, _cached_fetch_binance_funding       # noqa: E402
import run_crypto_pairs_v34_full_combined as _v34mod                                         # noqa: E402

CACHE_FG = Path(r'C:\amttp\data\geometric_extractor_engine_arrays_funded_v58_fg.npz')
INIT = 1000.0
K_LEV = 5.0
HORIZONS = [1, 2, 3, 4, 6, 8, 12, 24]


def _z(s: pd.Series, calib_mask: np.ndarray) -> pd.Series:
    mu = s[calib_mask].mean()
    sd = s[calib_mask].std()
    return (s - mu) / max(sd, 1e-12)


def _equity(r: pd.Series, init=INIT):
    r = r.fillna(0.0).clip(lower=-0.95)
    eq = init * (1.0 + r).cumprod()
    dd = (eq - eq.cummax()) / eq.cummax()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    return dict(final=float(eq.iloc[-1]), profit=float(eq.iloc[-1] - init),
                profit_pct=float(eq.iloc[-1]/init - 1.0), cagr=float((eq.iloc[-1]/init)**(1/years)-1),
                sharpe=float(np.sqrt(24*365.25)*r.mean()/r.std()) if r.std()>0 else 0.0,
                maxdd=float(dd.min()), eq=eq)


def _period(eq: pd.Series, freq: str):
    out=[]
    for dt, s in eq.groupby(pd.Grouper(freq=freq)):
        if len(s)<2: continue
        out.append(dict(period=str(dt.date()), start=float(s.iloc[0]), end=float(s.iloc[-1]),
                        profit=float(s.iloc[-1]-s.iloc[0]), return_pct=float(s.iloc[-1]/s.iloc[0]-1)))
    return out


def _build_nonoverlap_pnl(pos_signal: pd.Series, ret: pd.Series, H: int) -> tuple[pd.Series, pd.Series]:
    """Position at t is used over next H bars. Rebalance only every H bars."""
    idx = ret.index
    pos = pd.Series(0.0, index=idx)
    vals = pos_signal.reindex(idx).fillna(0.0).values
    for start in range(0, len(idx), H):
        # signal known at start, position active from start+1 to start+H inclusive
        p = vals[start]
        lo = start + 1
        hi = min(start + H + 1, len(idx))
        if lo < hi:
            pos.iloc[lo:hi] = p
    pnl = pos * ret.fillna(0.0)
    return pnl, pos


def _turnover(pos: pd.Series) -> pd.Series:
    return pos.diff().abs().fillna(pos.abs()) / 2.0


def main():
    BAR='='*100
    print(BAR)
    print('  GEOMETRY HORIZON TEST — can it see a few hours ahead?')
    print(BAR)
    t0=time.time()

    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)
    df_1h, _ = build_1h_df(start='2021-01-01', end='2026-05-01')
    fund = _cached_fetch_binance_funding()
    X = np.nan_to_num(build_intraday_state_panel(df_1h, fund.get('BTCUSDT'), fund.get('ETHUSDT')))
    idx = df_1h.index
    ret = df_1h['ret_eth'].fillna(0.0)
    train_1h=(idx>=TRAIN_START)&(idx<TEST_START)
    train_idx=np.where(train_1h)[0]
    calib_mask=np.zeros(len(df_1h), dtype=bool); calib_mask[train_idx[-CALIB_BARS:]]=True
    test_mask=idx>=TEST_START

    z=np.load(CACHE_FG)
    F_all=z['F_all']; G_all=z['G_all']; valid=z['valid']
    T,N,d=X.shape
    F_flat=F_all.reshape(T,-1); G_flat=G_all.reshape(T,-1); Xt_flat=X.reshape(T,-1)
    dX=np.full_like(X,np.nan,dtype=np.float32); dX[:-1]=X[1:]-X[:-1]
    dX_flat=dX.reshape(T,-1); dX_prev=np.roll(dX_flat,1,axis=0); dX_prev[0]=np.nan

    # E7
    alpha=2/(32+1); Fbar=np.full_like(F_flat,np.nan); Fbar[0]=F_flat[0]
    for t in range(1,T):
        if np.isnan(F_flat[t]).any(): Fbar[t]=Fbar[t-1]
        elif np.isnan(Fbar[t-1]).any(): Fbar[t]=F_flat[t]
        else: Fbar[t]=(1-alpha)*Fbar[t-1]+alpha*F_flat[t]
    sig_E7=pd.Series(np.einsum('ti,ti->t',Fbar,dX_prev), index=idx)
    sig_B1=pd.Series(np.einsum('ti,ti->t',G_flat,dX_prev), index=idx)
    Xc=Xt_flat[calib_mask]; mu=Xc.mean(0)
    Sinv=np.linalg.inv(np.cov(Xc,rowvar=False)+1e-6*np.eye(N*d))
    e6=np.full(T,np.nan)
    for t in range(1,T):
        if valid[t]:
            try: e6[t]=float(-(F_flat[t]@(Sinv@(Xt_flat[t]-mu))))
            except Exception: pass
    sig_E6=pd.Series(e6,index=idx)

    score = (_z(sig_E7, calib_mask) + _z(sig_B1, calib_mask) + _z(sig_E6, calib_mask)) / 3.0
    pos_sig = np.sign(score).fillna(0.0)

    print(f"\n  Composite direction rates on test: long={(pos_sig[test_mask]>0).mean():.1%}, short={(pos_sig[test_mask]<0).mean():.1%}")
    rows=[]
    for H in HORIZONS:
        # Forecast IC vs H-hour future return
        future = sum(ret.shift(-i) for i in range(1, H+1))
        ix = score[test_mask].dropna().index.intersection(future[test_mask].dropna().index)
        pear = float(score.reindex(ix).corr(future.reindex(ix)))
        sign_ic = float((np.sign(score.reindex(ix))*np.sign(future.reindex(ix)) > 0).mean())

        gross_pnl, pos = _build_nonoverlap_pnl(pos_sig, ret, H)
        gross = gross_pnl[test_mask]
        turns = _turnover(pos)[test_mask]
        active = (pos.abs() > 0).astype(float)[test_mask]

        # cost per hour return unit
        low_cost = (2.0/1e4)*turns + ((0.5/24)/1e4)*active     # 1.5+0.5 bp RT + funding
        taker_cost = (7.0/1e4)*turns + ((1.0/24)/1e4)*active   # 5+2 bp RT + funding

        m_g = _equity(K_LEV*gross)
        m_l = _equity(K_LEV*(gross-low_cost))
        m_t = _equity(K_LEV*(gross-taker_cost))
        rows.append(dict(H=H, pearson=pear, sign_ic=sign_ic,
                         gross_final=m_g['final'], low_final=m_l['final'], taker_final=m_t['final'],
                         gross_sharpe=m_g['sharpe'], low_sharpe=m_l['sharpe'], taker_sharpe=m_t['sharpe'],
                         low_maxdd=m_l['maxdd'], taker_maxdd=m_t['maxdd'],
                         trades=int((turns>0).sum())))

    print(f"\n{BAR}")
    print('  HORIZON RESULTS — K=5, $1,000, non-overlap holding')
    print(BAR)
    print(f"  {'H(h)':>4} {'Pearson':>9} {'SignIC':>8} {'Trades':>7} {'Gross$':>10} {'LowCost$':>10} {'Taker$':>10} {'LowSh':>8} {'LowDD':>8}")
    for r in rows:
        print(f"  {r['H']:>4} {r['pearson']:>+9.4f} {r['sign_ic']:>7.1%} {r['trades']:>7} "
              f"{r['gross_final']:>10,.0f} {r['low_final']:>10,.0f} {r['taker_final']:>10,.0f} "
              f"{r['low_sharpe']:>+8.2f} {r['low_maxdd']:>+7.1%}")

    best_low = max(rows, key=lambda x: x['low_final'])
    print(f"\n  Best low-cost horizon: H={best_low['H']}h final=${best_low['low_final']:,.2f} "
          f"SignIC={best_low['sign_ic']:.1%} trades={best_low['trades']}")

    # Detailed periods for best H under low-cost
    H=best_low['H']
    gross_pnl, pos = _build_nonoverlap_pnl(pos_sig, ret, H)
    turns=_turnover(pos)[test_mask]; active=(pos.abs()>0).astype(float)[test_mask]
    low_cost=(2.0/1e4)*turns + ((0.5/24)/1e4)*active
    m=_equity(K_LEV*(gross_pnl[test_mask]-low_cost))
    print(f"\n{BAR}\n  BEST H={H}h LOW-COST MAKER — YEARLY PROFIT\n{BAR}")
    print(f"  {'Year':<12} {'Start $':>12} {'End $':>12} {'Profit $':>12} {'Return':>9}")
    for row in _period(m['eq'],'Y'):
        print(f"  {row['period']:<12} {row['start']:>12,.2f} {row['end']:>12,.2f} {row['profit']:>12,.2f} {row['return_pct']:>8.1%}")

    out_path=Path(OUT_DIR)/'geometry_horizon_forecast_results.json'
    out_path.write_text(json.dumps({'rows':rows,'best_low':best_low,'best_yearly':_period(m['eq'],'Y')},indent=2,default=float))
    print(f"\n  saved -> {out_path}\n  elapsed={time.time()-t0:.1f}s\n{BAR}")

if __name__=='__main__':
    main()
