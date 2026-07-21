"""Direct $1,000 K=5 comparison: v58_full vs best v59 combo.

Clarifies user question:
  - K=5 is leverage/notional multiplier.
  - k=0.105 is geometry overlay volatility scale.
  - v58 and geometry overlays are signed long/short PnL streams.

Outputs gross / low-cost / realistic-taker simulations, quarterly and yearly.
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


def _equity(r: pd.Series, init=INIT):
    r = r.fillna(0.0).clip(lower=-0.95)
    eq = init * (1.0 + r).cumprod()
    dd = (eq - eq.cummax()) / eq.cummax()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    return dict(eq=eq, final=float(eq.iloc[-1]), profit=float(eq.iloc[-1]-init),
                profit_pct=float(eq.iloc[-1]/init-1), cagr=float((eq.iloc[-1]/init)**(1/years)-1),
                maxdd=float(dd.min()), sharpe=float(np.sqrt(24*365.25)*r.mean()/r.std()) if r.std()>0 else 0.0)


def _period(eq: pd.Series, freq: str):
    out=[]
    for dt, s in eq.groupby(pd.Grouper(freq=freq)):
        if len(s)<2: continue
        out.append(dict(period=str(dt.date()), start=float(s.iloc[0]), end=float(s.iloc[-1]),
                        profit=float(s.iloc[-1]-s.iloc[0]), return_pct=float(s.iloc[-1]/s.iloc[0]-1)))
    return out


def _rt_from_pos(pos: pd.Series):
    p=pos.fillna(0.0).astype(float)
    return p.diff().abs().fillna(p.abs())/2.0


def _simulate(name, pnl, cost, test_mask):
    m=_equity(K_LEV*(pnl[test_mask]-cost[test_mask]))
    print(f"  {name:<28} final=${m['final']:>10,.2f}  profit=${m['profit']:>10,.2f}  "
          f"return={m['profit_pct']:>8.1%}  CAGR={m['cagr']:>8.1%}  Sharpe={m['sharpe']:>+6.2f}  MaxDD={m['maxdd']:>+7.1%}")
    return m


def main():
    BAR='='*100
    print(BAR)
    print('  $1,000 K=5 DIRECT COMPARISON — v58_full vs best v59 combo')
    print(BAR)
    t0=time.time()

    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    fund = _cached_fetch_binance_funding()
    X = np.nan_to_num(build_intraday_state_panel(df_1h, fund.get('BTCUSDT'), fund.get('ETHUSDT')))
    idx=df_1h.index; ret_eth=df_1h['ret_eth'].fillna(0.0)
    train_1h=(idx>=TRAIN_START)&(idx<TEST_START)
    train_idx=np.where(train_1h)[0]
    calib_mask=np.zeros(len(df_1h), dtype=bool); calib_mask[train_idx[-CALIB_BARS:]]=True
    test_mask=idx>=TEST_START

    print(f"\n[1] rebuild v58_full t={time.time()-t0:.0f}s", flush=True)
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(X, calib_mask)
    M_k1 = MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)
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
    pos_dict,_,_,gate_daily=build_daily_positions(df_d, tmask_d, np.asarray(tmask_d, dtype=bool))
    instr_map={
        'D1_trend_eth':df_1h['ret_eth'], 'D2_pairs_eb':df_1h['spread_ret_eb'],
        'D3_pairs_es':df_1h['ret_eth']-df_1h.get('ret_sol',df_1h['ret_eth']),
        'D4_macro_btc':df_1h['ret_btc'], 'D5_macro_btc':df_1h['ret_btc'], 'D5_macro_alt':df_1h['ret_eth']}
    d1h={n:upsample_daily_to_1h_pnl(p, instr_map.get(n,df_1h['ret_eth']), gate_daily) for n,p in pos_dict.items()}
    base_pnl=assemble_combined({**d1h,**h_strats}, compute_quality({**d1h,**h_strats}, bpd=BPD))
    pnl_v58_dyn=_build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch, CORE['clip'], CORE['tth'], CORE['aft'], CORE['cb'], CORE['gbt'], v58_dynamic_gth(df_1h))
    diag=compute_corrected_diagnostics(X, df_1h, M, lyap, start_idx=0, history_len=168, cache_key='v58_default', use_cache=True, verbose=True)
    pnl_v58_full=_apply_overlays(pnl_v58_dyn, cos=(diag['cos_theta']>0).astype(float), rho=(diag['rho_normalised']>0.5).astype(float), M=(diag['M_margin']>0).astype(float)).reindex(idx).fillna(0.0)

    print(f"\n[2] geometry basket t={time.time()-t0:.0f}s", flush=True)
    z=np.load(CACHE_FG); F_all=z['F_all']; G_all=z['G_all']; valid=z['valid']
    T,N,d=X.shape; F_flat=F_all.reshape(T,-1); G_flat=G_all.reshape(T,-1); Xt_flat=X.reshape(T,-1)
    dX=np.full_like(X,np.nan,dtype=np.float32); dX[:-1]=X[1:]-X[:-1]
    dX_flat=dX.reshape(T,-1); dX_prev=np.roll(dX_flat,1,axis=0); dX_prev[0]=np.nan
    # E7
    alpha=2/(32+1); Fbar=np.full_like(F_flat,np.nan); Fbar[0]=F_flat[0]
    for t in range(1,T):
        if np.isnan(F_flat[t]).any(): Fbar[t]=Fbar[t-1]
        elif np.isnan(Fbar[t-1]).any(): Fbar[t]=F_flat[t]
        else: Fbar[t]=(1-alpha)*Fbar[t-1]+alpha*F_flat[t]
    sig_E7=pd.Series(np.einsum('ti,ti->t',Fbar,dX_prev),index=idx)
    sig_B1=pd.Series(np.einsum('ti,ti->t',G_flat,dX_prev),index=idx)
    Xc=Xt_flat[calib_mask]; mu=Xc.mean(0); Sinv=np.linalg.inv(np.cov(Xc,rowvar=False)+1e-6*np.eye(N*d))
    e6=np.full(T,np.nan)
    for t in range(1,T):
        if valid[t]:
            try: e6[t]=float(-(F_flat[t]@(Sinv@(Xt_flat[t]-mu))))
            except Exception: pass
    sig_E6=pd.Series(e6,index=idx)
    pnls={n:np.sign(s).shift(1).fillna(0.0)*ret_eth for n,s in {'E7':sig_E7,'B1':sig_B1,'E6':sig_E6}.items()}
    poses={n:np.sign(s).shift(1).fillna(0.0) for n,s in {'E7':sig_E7,'B1':sig_B1,'E6':sig_E6}.items()}
    k=float(pnl_v58_full[calib_mask].std()/max(pnls['E7'][calib_mask].std(),1e-12))
    geom_pnl=(k*pnls['E7']+k*pnls['B1']+k*pnls['E6'])/3
    pnl_combo=pnl_v58_full+geom_pnl

    # long/short diagnostics for geometry components
    print("\n  Geometry directions (test): +1=long ETH, -1=short ETH")
    for n,p in poses.items():
        pt=p[test_mask]
        print(f"    {n:<3} long={(pt>0).mean():>6.1%}  short={(pt<0).mean():>6.1%}  flat={(pt==0).mean():>6.1%}")

    active_core=(pnl_v58_full.abs()>1e-12).astype(float)
    core_episode=active_core.diff().abs().fillna(active_core)/2
    geom_turn=pd.Series(0.0,index=idx); geom_active=pd.Series(0.0,index=idx)
    for n,pos in poses.items():
        scale=k/3
        geom_turn += scale*_rt_from_pos(pos)
        geom_active += scale*(pos.abs()>0).astype(float)
    active_notional=active_core+geom_active

    def cost(fee_rt, slip_rt, fund_day, include_geom=True):
        rt=(fee_rt+slip_rt)/1e4; fh=(fund_day/24)/1e4
        if include_geom:
            return rt*(core_episode+geom_turn)+fh*active_notional
        return rt*core_episode+fh*active_core

    scenarios={
        'gross_no_cost': (pd.Series(0.0,index=idx), pd.Series(0.0,index=idx)),
        'low_cost_maker': (cost(1.5,0.5,0.5,False), cost(1.5,0.5,0.5,True)),
        'realistic_taker': (cost(5.0,2.0,1.0,False), cost(5.0,2.0,1.0,True)),
    }

    print(f"\n{BAR}")
    print(f"  K=5, $1,000 — v58_full vs combo")
    print(BAR)
    results={}
    for sc,(cost_v58,cost_combo) in scenarios.items():
        print(f"\n  Scenario: {sc}")
        m58=_simulate('v58_full', pnl_v58_full, cost_v58, test_mask)
        mc=_simulate('v58_full + E7/B1/E6', pnl_combo, cost_combo, test_mask)
        results[sc]={'v58_full':{k0:v for k0,v in m58.items() if k0!='eq'}, 'combo':{k0:v for k0,v in mc.items() if k0!='eq'},
                     'combo_quarterly':_period(mc['eq'],'Q'), 'combo_yearly':_period(mc['eq'],'Y'),
                     'v58_quarterly':_period(m58['eq'],'Q'), 'v58_yearly':_period(m58['eq'],'Y')}

    # print detailed K=5 low-cost quarterly/yearly because this matches profitable realistic deployment
    for sc in ['gross_no_cost','low_cost_maker','realistic_taker']:
        print(f"\n{BAR}")
        print(f"  {sc.upper()} — K=5 YEARLY, v58_full vs combo")
        print(BAR)
        print(f"  {'Year':<12} {'v58 profit':>14} {'v58 end':>12} {'combo profit':>14} {'combo end':>12}")
        vy=results[sc]['v58_yearly']; cy=results[sc]['combo_yearly']
        for a,b in zip(vy,cy):
            print(f"  {a['period']:<12} {a['profit']:>14,.2f} {a['end']:>12,.2f} {b['profit']:>14,.2f} {b['end']:>12,.2f}")

    out_path=Path(OUT_DIR)/'v58_vs_v59_k5_1000_comparison.json'
    out_path.write_text(json.dumps({'K':K_LEV,'init':INIT,'overlay_k':k,'results':results},indent=2,default=float))
    print(f"\n  saved -> {out_path}")
    print(f"  elapsed={time.time()-t0:.1f}s")
    print(BAR)

if __name__=='__main__':
    main()
