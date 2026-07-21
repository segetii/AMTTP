"""2-hour forecast, hourly execution test.

Hypothesis: model the next 2h cumulative move, but update/trade every hour.
This should be better than naive 1h sign because it uses early-warning horizon
while still allowing hourly risk control.

Tests:
  - geometry composite sign baseline
  - ridge model trained on calibration only to predict next 2h ETH return
  - confidence thresholds by calibration prediction quantile
  - standalone geometry overlay and v58_full + overlay
  - K=5 $1,000 capital with low-cost maker and taker costs

No lookahead: features at t, target = ret[t+1]+ret[t+2].
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

from collapse_geometry import MasterOperator                            # noqa: E402
from run_crypto_pairs_v36_intraday_bsdt import (                        # noqa: E402
    CALIB_BARS, BPD,
    build_intraday_state_panel, calibrate_intraday_engine, _stats,
    compute_intraday_signals,
)
from run_crypto_pairs_v37_price_prediction import compute_price_prediction_signals  # noqa: E402
from run_crypto_pairs_v38_lambda_norm import compute_lambda_features              # noqa: E402
from run_crypto_pairs_v34_full_combined import (                        # noqa: E402
    build_1h_df, OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
    compute_1h_strategies, compute_quality, assemble_combined,
    upsample_daily_to_1h_pnl, build_daily_positions,
    add_leverage_features,
)
from run_crypto_pairs_v39_four_channels import FIRE_PERCENTILE, calibrate_firing_thresholds  # noqa: E402
from run_crypto_pairs_v39b_k1_scaled import compute_four_channel_signals_v39b, calibrate_channel_means, PCA_K_B  # noqa: E402
from run_robustness_validation import (                                  # noqa: E402
    _build_pnl, _apply_overlays, CORE,
    _make_cached_fetch, _cached_fetch_binance_funding,
    _cached_fetch_and_prepare, _cached_add_cross_market,
)
from corrected_diagnostics import compute_corrected_diagnostics, v58_dynamic_gth  # noqa: E402
import run_crypto_pairs_v34_full_combined as _v34mod                    # noqa: E402

CACHE_FG = Path(r'C:\amttp\data\geometric_extractor_engine_arrays_funded_v58_fg.npz')
INIT = 1000.0
K_LEV = 5.0
H = 2
THRESH_Q = [0.00, 0.50, 0.60, 0.70, 0.80, 0.90]


def _z(s: pd.Series, calib_mask: np.ndarray) -> pd.Series:
    return (s - s[calib_mask].mean()) / max(s[calib_mask].std(), 1e-12)


def _equity(r: pd.Series, init=INIT):
    r = r.fillna(0.0).clip(lower=-0.95)
    eq = init * (1 + r).cumprod()
    dd = (eq - eq.cummax()) / eq.cummax()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    return dict(final=float(eq.iloc[-1]), profit=float(eq.iloc[-1]-init),
                profit_pct=float(eq.iloc[-1]/init-1), cagr=float((eq.iloc[-1]/init)**(1/years)-1),
                sharpe=float(np.sqrt(24*365.25)*r.mean()/r.std()) if r.std()>0 else 0.0,
                maxdd=float(dd.min()), eq=eq)


def _period(eq: pd.Series, freq: str):
    out=[]
    for dt, s in eq.groupby(pd.Grouper(freq=freq)):
        if len(s)<2: continue
        out.append(dict(period=str(dt.date()), start=float(s.iloc[0]), end=float(s.iloc[-1]),
                        profit=float(s.iloc[-1]-s.iloc[0]), return_pct=float(s.iloc[-1]/s.iloc[0]-1)))
    return out


def _turnover(pos: pd.Series):
    p = pos.fillna(0.0).astype(float)
    return p.diff().abs().fillna(p.abs()) / 2.0


def _ridge_fit_predict(Xdf: pd.DataFrame, y: pd.Series, calib_mask: np.ndarray, lam_scale=1e-2):
    ix = Xdf.index
    X = Xdf.fillna(0.0).values.astype(float)
    yy = y.reindex(ix).values.astype(float)
    train = calib_mask & np.isfinite(yy) & np.isfinite(X).all(axis=1)
    Xtr = X[train]; ytr = yy[train]
    # add intercept
    Xtr1 = np.c_[np.ones(len(Xtr)), Xtr]
    X1 = np.c_[np.ones(len(X)), X]
    lam = lam_scale * np.trace(Xtr1.T @ Xtr1) / max(Xtr1.shape[1], 1)
    A = Xtr1.T @ Xtr1 + lam * np.eye(Xtr1.shape[1])
    A[0,0] -= lam  # do not penalize intercept
    w = np.linalg.solve(A, Xtr1.T @ ytr)
    pred = pd.Series(X1 @ w, index=ix)
    return pred, w


def main():
    BAR='='*100
    print(BAR)
    print('  2H MODEL / HOURLY TRADING TEST')
    print(BAR)
    t0=time.time()

    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    fund = _cached_fetch_binance_funding()
    X = np.nan_to_num(build_intraday_state_panel(df_1h, fund.get('BTCUSDT'), fund.get('ETHUSDT')))
    idx=df_1h.index; ret=df_1h['ret_eth'].fillna(0.0)
    train_1h=(idx>=TRAIN_START)&(idx<TEST_START)
    train_idx=np.where(train_1h)[0]
    calib_mask=np.zeros(len(df_1h), dtype=bool); calib_mask[train_idx[-CALIB_BARS:]]=True
    test_mask=idx>=TEST_START

    # v58_full core
    print(f"\n[1] rebuild v58_full t={time.time()-t0:.0f}s", flush=True)
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(X, calib_mask)
    M_k1=MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)
    sig_v36=compute_intraday_signals(X, df_1h, M, net, ews, stoch, e_star, theta)
    sig_v37,_,_=compute_price_prediction_signals(X, df_1h, M, sig_v36, e_star, getattr(stoch,'sigma_n',1.0))
    lam_feat=compute_lambda_features(sig_v37, roll_windows=(100,200,500))
    mu_norm=calibrate_channel_means(X, calib_mask, M_k1)
    fire_thr=calibrate_firing_thresholds(X, calib_mask, M_k1, pct=FIRE_PERCENTILE)
    sig_4ch=compute_four_channel_signals_v39b(X, df_1h, M_k1, sig_v36, fire_thr, mu_norm)
    h_strats=compute_1h_strategies(df_1h, has_sol)
    df_d=_cached_fetch_and_prepare(); df_d=_cached_add_cross_market(df_d)
    fund_d=_cached_fetch_binance_funding(); df_d=add_leverage_features(df_d, fund_d)
    tmask_d=(df_d.index>=TRAIN_START)&(df_d.index<=TRAIN_END)
    pos_dict,_,_,gate_daily=build_daily_positions(df_d, tmask_d, np.asarray(tmask_d,dtype=bool))
    instr_map={'D1_trend_eth':df_1h['ret_eth'],'D2_pairs_eb':df_1h['spread_ret_eb'],
               'D3_pairs_es':df_1h['ret_eth']-df_1h.get('ret_sol',df_1h['ret_eth']),
               'D4_macro_btc':df_1h['ret_btc'],'D5_macro_btc':df_1h['ret_btc'],'D5_macro_alt':df_1h['ret_eth']}
    d1h={n:upsample_daily_to_1h_pnl(p,instr_map.get(n,df_1h['ret_eth']),gate_daily) for n,p in pos_dict.items()}
    base_pnl=assemble_combined({**d1h,**h_strats}, compute_quality({**d1h,**h_strats}, bpd=BPD))
    pnl_v58_dyn=_build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch, CORE['clip'], CORE['tth'], CORE['aft'], CORE['cb'], CORE['gbt'], v58_dynamic_gth(df_1h))
    diag=compute_corrected_diagnostics(X, df_1h, M, lyap, start_idx=0, history_len=168, cache_key='v58_default', use_cache=True, verbose=True)
    pnl_v58_full=_apply_overlays(pnl_v58_dyn, cos=(diag['cos_theta']>0).astype(float), rho=(diag['rho_normalised']>0.5).astype(float), M=(diag['M_margin']>0).astype(float)).reindex(idx).fillna(0.0)

    # geometry features
    print(f"\n[2] geometry features t={time.time()-t0:.0f}s", flush=True)
    z=np.load(CACHE_FG); F_all=z['F_all']; G_all=z['G_all']; valid=z['valid']
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
    # E8 as optional feature
    Fpath=np.full_like(F_flat,np.nan); cs=np.cumsum(np.nan_to_num(F_flat),axis=0)
    for t in range(32,T): Fpath[t]=(cs[t]-cs[t-32])/32
    E8=pd.Series(np.einsum('ti,ti->t',Fpath,dX_prev),index=idx)

    features=pd.DataFrame({
        'E7':_z(E7,calib_mask), 'B1':_z(B1,calib_mask), 'E6':_z(E6,calib_mask), 'E8':_z(E8,calib_mask),
    }, index=idx)
    features['E7_abs']=features['E7'].abs(); features['B1_abs']=features['B1'].abs(); features['E6_abs']=features['E6'].abs()
    features['combo_mean']=features[['E7','B1','E6']].mean(axis=1)
    features['combo_abs']=features['combo_mean'].abs()
    features['v58_active']=(pnl_v58_full.abs()>1e-12).astype(float)

    target2 = ret.shift(-1) + ret.shift(-2)
    pred2, w = _ridge_fit_predict(features, target2, calib_mask)
    raw_combo = features['combo_mean']

    print("\n  Forecast diagnostics on test:")
    for name, pred in [('raw_combo',raw_combo), ('ridge2h',pred2)]:
        ix=pred[test_mask].dropna().index.intersection(target2[test_mask].dropna().index)
        print(f"    {name:<10} pearson={pred.reindex(ix).corr(target2.reindex(ix)):+.4f}  "
              f"signIC={((np.sign(pred.reindex(ix))*np.sign(target2.reindex(ix))>0).mean()):.1%}")

    # v58 core execution cost: active episodes, same convention as K=5 comparison.
    active_core = (pnl_v58_full.abs() > 1e-12).astype(float)
    core_turn = active_core.diff().abs().fillna(active_core) / 2.0
    low_core_cost = (2.0/1e4)*core_turn + ((0.5/24)/1e4)*active_core
    taker_core_cost = (7.0/1e4)*core_turn + ((1.0/24)/1e4)*active_core

    # cost helper for hourly position overlay
    def eval_signal(sig_name, pred, base_name, base_pnl):
        rows=[]
        abs_cal=pred[calib_mask].abs().dropna()
        for q in THRESH_Q:
            th=float(abs_cal.quantile(q)) if q>0 else 0.0
            pos=np.sign(pred).where(pred.abs()>=th,0.0).shift(1).fillna(0.0)
            pnl=pos*ret
            # vol match overlay to base calib
            k=float(base_pnl[calib_mask].std()/max(pnl[calib_mask].std(),1e-12))
            overlay=k*pnl
            total=base_pnl+overlay
            turn=_turnover(pos)*(k)  # overlay notional turnover
            active=(pos.abs()>0).astype(float)*k
            low_cost=(2.0/1e4)*turn + ((0.5/24)/1e4)*active
            taker_cost=(7.0/1e4)*turn + ((1.0/24)/1e4)*active
            # full-system cost: v58 core cost + overlay cost
            low_total_cost = low_core_cost + low_cost
            taker_total_cost = taker_core_cost + taker_cost
            low=_equity(K_LEV*(total[test_mask] - low_total_cost[test_mask]))
            taker=_equity(K_LEV*(total[test_mask] - taker_total_cost[test_mask]))
            gross=_equity(K_LEV*total[test_mask])
            rows.append(dict(signal=sig_name, base=base_name, q=q, threshold=th, active=float((pos[test_mask]!=0).mean()),
                             k=k, gross_final=gross['final'], low_final=low['final'], taker_final=taker['final'],
                             gross_sharpe=gross['sharpe'], low_sharpe=low['sharpe'], taker_sharpe=taker['sharpe'],
                             low_maxdd=low['maxdd'], taker_maxdd=taker['maxdd']))
        return rows

    all_rows=[]
    for sig_name,pred in [('raw_combo',raw_combo),('ridge2h',pred2)]:
        all_rows += eval_signal(sig_name,pred,'v58_full',pnl_v58_full)

    all_rows=sorted(all_rows,key=lambda r:r['low_final'],reverse=True)
    print(f"\n{'='*100}\n  2H MODEL / HOURLY EXECUTION — K=5, overlay over v58_full\n{'='*100}")
    print(f"  {'Rank':>4} {'Signal':<10} {'q':>4} {'Active':>7} {'k':>7} {'Gross$':>10} {'LowCost$':>10} {'Taker$':>10} {'LowSh':>8} {'LowDD':>8}")
    for i,r in enumerate(all_rows[:20],1):
        print(f"  {i:>4} {r['signal']:<10} {r['q']:>4.2f} {r['active']:>6.1%} {r['k']:>7.4f} "
              f"{r['gross_final']:>10,.0f} {r['low_final']:>10,.0f} {r['taker_final']:>10,.0f} {r['low_sharpe']:>+8.2f} {r['low_maxdd']:>+7.1%}")

    best=all_rows[0]
    # detailed periods for best low-cost
    best_pred=pred2 if best['signal']=='ridge2h' else raw_combo
    pos=np.sign(best_pred).where(best_pred.abs()>=best['threshold'],0.0).shift(1).fillna(0.0)
    pnl=pos*ret; overlay=best['k']*pnl; total=pnl_v58_full+overlay
    turn=_turnover(pos)*best['k']; active=(pos.abs()>0).astype(float)*best['k']
    low_cost=(2.0/1e4)*turn + ((0.5/24)/1e4)*active
    m=_equity(K_LEV*(total[test_mask]-(low_core_cost+low_cost)[test_mask]))
    print(f"\n  BEST LOW-COST: {best['signal']} q={best['q']:.2f} active={best['active']:.1%} final=${best['low_final']:,.2f}")
    print(f"\n  YEARLY PROFIT — BEST 2H MODEL HOURLY, K=5 LOW-COST")
    print(f"  {'Year':<12} {'Start $':>12} {'End $':>12} {'Profit $':>12} {'Return':>9}")
    for row in _period(m['eq'],'Y'):
        print(f"  {row['period']:<12} {row['start']:>12,.2f} {row['end']:>12,.2f} {row['profit']:>12,.2f} {row['return_pct']:>8.1%}")

    out=Path(OUT_DIR)/'two_hour_model_trade_hourly_results.json'
    out.write_text(json.dumps({'rows':all_rows,'best':best,'yearly':_period(m['eq'],'Y')},indent=2,default=float))
    print(f"\n  saved -> {out}\n  elapsed={time.time()-t0:.1f}s")

if __name__=='__main__':
    main()
