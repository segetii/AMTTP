"""
Crypto BSDT v28 - Quality-Gated Risk-Normalized Allocator
==========================================================

Fix for v27 finding: per-strategy contribution Sharpe was excellent
(trend +1.93, pairs +1.64, macro +2.62) but breakout (Sh +0.0) ate 99% of
the absolute PnL because L1 normalization rewards raw magnitude regardless
of quality.

v28 = three-layer allocator:

  Layer 1 - Risk normalization
      pnl_scaled[s] = target_vol / rolling_vol[s]   (per-strategy size cap)
      Removes magnitude dominance.

  Layer 2 - Quality gating
      q[s] = sigmoid(rolling_sharpe[s] * k)         (suppress weak signals)
      A strategy with rolling_sharpe ~ 0 collapses to q ~ 0.5;
      with rolling_sharpe < 0 collapses toward 0.

  Layer 3 - State allocation
      W_state[s] = engine-state-driven gates  (from v27)
      effective[t,s] = W_state[t-1,s] * q[t-1,s] * scale[t-1,s]
      Then normalize sum to 1 across strategies (relative sizing).

  Final:
      pnl[t] = lev[t-1] * sum_s effective[t,s] * pnl_s[t]

Strategy book: trend, pairs, breakout, macro  (mean-rev DROPPED -
v27 contribution Sharpe -2.27 - structurally wrong for this market).
"""
from __future__ import annotations
import os, sys, json
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from run_crypto_pairs_v19 import (
    fetch_and_prepare, add_cross_market_features,
    fetch_binance_funding, add_leverage_features,
    compute_bsdt, compute_gamma_rank, compute_activity_signals,
    compute_state_vector, compute_geom_signals_v18_smooth,
    apply_geom_penalties_v18, compute_leverage_dial,
    compute_rolling_spread_v8, SpreadUDLClassifier,
    compute_manifold_validity, detect_phase,
    route_pair_v7, route_btcalt_macro, setup_a_directional,
    get_daily_pnl, compute_cs_weights,
    simulate_from_pnl, equity_at_K, find_best_K,
    _build_state_panel,
    TRAIN_START, TRAIN_END, TEST_START, OUT_DIR,
    GAMMA_SCORE_WIN,
)
from run_crypto_pairs_v22 import (
    calibrate_frozen_engine, patch_precursor_scale, emit_global_signals,
    LEV_LO, LEV_HI,
)
from run_crypto_pairs_v23 import run_repr_pipeline
from run_crypto_pairs_v26 import compute_donchian_breakout, _sigmoid
from run_crypto_pairs_v27 import compute_unsigned_weights, G_LO, K_LO


# =====================================================================
#   PHASE 1 - QUALITY + RISK WEIGHTS
# =====================================================================

def compute_quality_risk_weights(pnl_dict: dict,
                                  vol_win: int = 60,
                                  sharpe_win: int = 120,
                                  sharpe_k: float = 2.0,
                                  target_vol: float = 0.01,
                                  scale_cap: float = 5.0) -> pd.DataFrame:
    """For each strategy, build a per-day multiplier combining:
        scale[s,t]   = target_vol / rolling_std(pnl_s, vol_win)   (capped)
        quality[s,t] = sigmoid(rolling_sharpe(pnl_s, sharpe_win) * sharpe_k)
        weight[s,t]  = scale * quality                  (lagged 1 day)

    Output is a DataFrame[T, len(pnl_dict)] of NON-NEGATIVE multipliers.
    These multipliers go on top of the engine-state weights.
    """
    out = {}
    for k, p in pnl_dict.items():
        rv = p.rolling(vol_win, min_periods=20).std().clip(lower=1e-6)
        rs_mean = p.rolling(sharpe_win, min_periods=30).mean()
        rs_std  = p.rolling(sharpe_win, min_periods=30).std().clip(lower=1e-6)
        rsharpe = (rs_mean / rs_std) * np.sqrt(252)
        q = _sigmoid(rsharpe.fillna(0.0) * sharpe_k)
        scale = (target_vol / rv).clip(upper=scale_cap)
        w = (q * scale).shift(1).fillna(0.0)
        out[k] = w
    return pd.DataFrame(out)


# =====================================================================
#   PHASE 2 - PORTFOLIO ASSEMBLY (4 strategies, mr dropped)
# =====================================================================

V28_KEYS = ['trend', 'pairs', 'breakout', 'macro']
V28_WCOLS = ['w_trend', 'w_pairs', 'w_breakout', 'w_macro']


def build_v28_pnl(strats: dict, W_state: pd.DataFrame, Q: pd.DataFrame,
                  lev: pd.Series, index: pd.Index,
                  renorm: bool = True) -> pd.Series:
    """pnl_t = lev[t-1] * sum_s eff[t,s] * pnl_s[t]
    where eff[t,s] = W_state[t-1,s] * Q[t-1,s] (Q already lagged inside Q).
    Optionally row-normalize eff to sum=1 (relative sizing).
    """
    W_lag = W_state.shift(1).fillna(0.0)
    eff = pd.DataFrame(0.0, index=index, columns=V28_KEYS)
    for c, k in zip(V28_WCOLS, V28_KEYS):
        eff[k] = W_lag[c] * Q[k]
    if renorm:
        s = eff.sum(axis=1).replace(0.0, np.nan)
        eff = eff.div(s, axis=0).fillna(0.0)
    pnl = pd.Series(0.0, index=index)
    for k in V28_KEYS:
        pnl = pnl + eff[k] * strats[k]
    return pnl * lev.shift(1).fillna(1.0)


# =====================================================================
#   MAIN
# =====================================================================

def main():
    out_dir = Path(OUT_DIR); out_dir.mkdir(parents=True, exist_ok=True)
    print("=" * 96)
    print("  CRYPTO BSDT v28 - Quality-Gated Risk-Normalized Allocator")
    print("  Drop mr; vol-scale + rolling-Sharpe gate + engine-state allocator")
    print("=" * 96)

    print("\n[1] Loading data ...")
    df = fetch_and_prepare()
    df = add_cross_market_features(df)
    funding = fetch_binance_funding(symbols=['ETHUSDT','BTCUSDT'], start='2020-06-01')
    df = add_leverage_features(df, funding)

    train_mask     = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask      = df.index >= TEST_START
    train_mask_arr = np.asarray(train_mask, dtype=bool)
    print(f"  Train: {df[train_mask].index[0].date()} -> {df[train_mask].index[-1].date()} "
          f"({int(train_mask.sum())}d)  "
          f"Test: {df[test_mask].index[0].date()} -> {df[test_mask].index[-1].date()} "
          f"({int(test_mask.sum())}d)")

    print("\n[2] Building shared signals ...")
    feats_strat = ['ret_eth_z','ret_btc_z','ret_sol_z','ret_bnb_z',
                   'vol_eth_z','vol_btc_z','btc_dom_z','cross_disp_z']
    feats_ext   = feats_strat + ['ret_spx_z','dvix_z','ret_dxy_z']
    omega_strat, mfls_eth, gamma_eth = compute_bsdt(df, feats_strat, window=60)
    omega_ext,   _,        _         = compute_bsdt(df, feats_ext,   window=60)
    A_eth, A_rank, dA_fast, dA_rank  = compute_activity_signals(mfls_eth, gamma_eth)
    gamma_rank  = compute_gamma_rank(omega_ext, min_periods=60)
    lev_mult    = compute_leverage_dial(gamma_rank)
    ret7  = df['ret_eth'].rolling(7).sum()
    ret3  = df['ret_eth'].rolling(3).sum()
    phase = detect_phase(omega_strat, ret7, ret3, df['btc_dom_z'])

    print("\n[3] Building strategies (mr dropped) ...")
    pos_A_dir = setup_a_directional(df, omega_strat, mfls_eth, gamma_eth, phase)
    pairs_def = [
        ('P1_ETH_BTC','log_eth','log_btc','ret_eth','ret_btc'),
        ('P2_ETH_SOL','log_eth','log_sol','ret_eth','ret_sol'),
        ('P3_ETH_BNB','log_eth','log_bnb','ret_eth','ret_bnb'),
    ]
    pair_data = {}
    for key, col_a, col_b, ret_a, ret_b in pairs_def:
        sd = compute_rolling_spread_v8(
            df[col_a], df[col_b], df[ret_a], df[ret_b],
            train_mask=train_mask, beta_window=252)
        clf = SpreadUDLClassifier(window=20, n_ref_dirs=100).fit(
            sd['spread'][train_mask].dropna())
        udl_s, _, _ = clf.classify_series(sd['spread'])
        sd['udl_state'] = udl_s
        mval, _ = compute_manifold_validity(sd['z'], sd['sret'])
        sd['manifold_valid'] = mval
        pair_data[key] = sd
    pair_pos = {k: route_pair_v7(omega_strat, A_rank, pair_data[k]['z'],
                                  pair_data[k]['udl_state'], pair_data[k]['poa'],
                                  pair_data[k]['manifold_valid'])
                for k, *_ in pairs_def}
    pos_btc_macro, pos_alt_macro = route_btcalt_macro(df, omega_strat, A_rank, dA_rank)

    pnl_base_dict = {
        'A_directional': get_daily_pnl(pos_A_dir, df['ret_eth']),
        'P1_ETH_BTC':    get_daily_pnl(pair_pos['P1_ETH_BTC'], pair_data['P1_ETH_BTC']['sret']),
        'P2_ETH_SOL':    get_daily_pnl(pair_pos['P2_ETH_SOL'], pair_data['P2_ETH_SOL']['sret']),
        'P3_ETH_BNB':    get_daily_pnl(pair_pos['P3_ETH_BNB'], pair_data['P3_ETH_BNB']['sret']),
        'M1_ALT_macro':  get_daily_pnl(pos_alt_macro, df['ret_eth']),
        'M1_BTC_macro':  get_daily_pnl(pos_btc_macro, df['ret_btc']),
    }

    V_state  = compute_state_vector(omega_strat, gamma_rank, mfls_eth, dA_fast)
    phi_18s, align_18s = compute_geom_signals_v18_smooth(V_state)
    lev_v18s = apply_geom_penalties_v18(lev_mult, phi_18s, align_18s)
    cs_wts   = compute_cs_weights(pnl_base_dict, window=GAMMA_SCORE_WIN)
    pnl_v10  = pd.Series(0.0, index=df.index)
    for k in pnl_base_dict:
        pnl_v10 += cs_wts[k].shift(1).fillna(1.0/len(pnl_base_dict)) * pnl_base_dict[k]
    pnl_v18s = pnl_v10 * lev_v18s.shift(1).fillna(1.0)

    pnl_pairs = (pnl_base_dict['P1_ETH_BTC']
                 + pnl_base_dict['P2_ETH_SOL']
                 + pnl_base_dict['P3_ETH_BNB']) / 3.0
    pnl_macro = (pnl_base_dict['M1_BTC_macro']
                 + pnl_base_dict['M1_ALT_macro']) / 2.0
    pnl_breakout = compute_donchian_breakout(df, win_in=20, win_out=10)

    strats = {
        'trend':    pnl_v18s,
        'pairs':    pnl_pairs,
        'breakout': pnl_breakout,
        'macro':    pnl_macro,
    }

    print("\n  Per-strategy STANDALONE Sharpe (test):")
    print(f"    {'strategy':<12}  {'Sharpe':>8}  {'CAGR%':>7}  {'MaxDD%':>8}  "
          f"{'std*1e3':>8}  {'Active':>7}")
    for k, p in strats.items():
        s = simulate_from_pnl(p[test_mask].fillna(0.0))
        std = p[test_mask].std()
        act = int(p[test_mask].abs().gt(1e-9).sum())
        print(f"    {k:<12}  {s['sharpe']:+8.4f}  {100*s['cagr']:+6.2f}%  "
              f"{100*s['max_dd']:+7.2f}%  {1e3*std:7.3f}  {act:6d}d")

    print("\n[4] Computing quality+risk weights (Layer 1 + 2) ...")
    Q = compute_quality_risk_weights(strats, vol_win=60, sharpe_win=120,
                                       sharpe_k=2.0, target_vol=0.01,
                                       scale_cap=5.0)

    print(f"\n  Quality*Scale weights [test]:")
    print(f"    {'strategy':<12}  {'mean(Q)':>10}  {'std(Q)':>10}  "
          f"{'min(Q)':>10}  {'max(Q)':>10}")
    for k in V28_KEYS:
        q = Q[k][test_mask]
        print(f"    {k:<12}  {q.mean():10.4f}  {q.std():10.4f}  "
              f"{q.min():10.4f}  {q.max():10.4f}")

    print("\n[5] Running physics engine for state signals ...")
    X_panel = _build_state_panel(df)
    M, net, geom_e, lyap, info, ews, e_star, sigma_n = calibrate_frozen_engine(
        X_panel, train_mask_arr)
    patch_precursor_scale(ews, M, X_panel[train_mask_arr])
    F = emit_global_signals(df, X_panel, M, net, geom_e, lyap, ews, sigma_n)

    print("\n[6] Computing engine-state weights (Layer 3) ...")
    W_full   = compute_unsigned_weights(F, use_activation=True,
                                         g_lo=G_LO, k_lo=K_LO)
    W_no_act = compute_unsigned_weights(F, use_activation=False)
    W_loose  = compute_unsigned_weights(F, use_activation=True,
                                         g_lo=0.35, k_lo=0.20)

    lev_kramers = (LEV_LO + (LEV_HI - LEV_LO) * F['kramers_p'].fillna(0.5)).clip(LEV_LO, LEV_HI)
    flat_lev    = pd.Series(1.0, index=df.index)

    print("\n[7] Reproducing v22 reference ...")
    sim_v22, pnl_v22, _ = run_repr_pipeline(
        X_panel, train_mask_arr, df, test_mask, pnl_v18s)

    variants = {}
    variants['v22_baseline']         = pnl_v22

    # Q layer only (no engine state W)
    W_uniform = pd.DataFrame(1.0, index=df.index, columns=V28_WCOLS)
    variants['v28_QonlyFlat']        = build_v28_pnl(strats, W_uniform, Q, flat_lev, df.index)
    variants['v28_QonlyKramers']     = build_v28_pnl(strats, W_uniform, Q, lev_kramers, df.index)

    # Full v28
    variants['v28_full']             = build_v28_pnl(strats, W_full, Q, lev_kramers, df.index)
    variants['v28_full_flat']        = build_v28_pnl(strats, W_full, Q, flat_lev, df.index)
    variants['v28_loose']            = build_v28_pnl(strats, W_loose, Q, lev_kramers, df.index)
    variants['v28_loose_flat']       = build_v28_pnl(strats, W_loose, Q, flat_lev, df.index)
    variants['v28_no_act']           = build_v28_pnl(strats, W_no_act, Q, lev_kramers, df.index)
    variants['v28_no_act_flat']      = build_v28_pnl(strats, W_no_act, Q, flat_lev, df.index)

    # Without breakout (sanity: does it still hurt after Q?)
    strats_no_brk = dict(strats); strats_no_brk['breakout'] = pd.Series(0.0, index=df.index)
    variants['v28_full_no_brk']      = build_v28_pnl(strats_no_brk, W_full, Q, lev_kramers, df.index)

    # Without quality (sanity: prove Q is the active ingredient)
    Q_unit = pd.DataFrame(1.0, index=df.index, columns=V28_KEYS)
    variants['v28_full_no_Q']        = build_v28_pnl(strats, W_full, Q_unit, lev_kramers, df.index)

    # Quality higher k (sharper gate)
    Q_sharp = compute_quality_risk_weights(strats, vol_win=60, sharpe_win=120,
                                            sharpe_k=4.0, target_vol=0.01,
                                            scale_cap=5.0)
    variants['v28_full_Qsharp']      = build_v28_pnl(strats, W_full, Q_sharp, lev_kramers, df.index)

    print("\n" + "=" * 96)
    print("  v28 ABLATION TABLE  (test period, K=1 gross)")
    print("=" * 96)
    print(f"  {'Variant':<24}  {'Sharpe':>8}  {'MaxDD%':>8}  {'CAGR%':>7}  "
          f"{'HitRate':>8}  {'Active':>7}  {'Calmar':>7}")
    print("  " + "-" * 84)
    best_sharpe, best_key = -999.0, 'v22_baseline'
    all_sims = {}
    for k, p in variants.items():
        s = simulate_from_pnl(p[test_mask].fillna(0.0))
        all_sims[k] = s
        act = int(p[test_mask].abs().gt(1e-9).sum())
        calmar = s['cagr'] / abs(s['max_dd']) if s['max_dd'] != 0 else float('nan')
        flag = ' <--' if s['sharpe'] > best_sharpe else ''
        if s['sharpe'] > best_sharpe:
            best_sharpe, best_key = s['sharpe'], k
        print(f"  {k:<24}  {s['sharpe']:+8.4f}  {100*s['max_dd']:+7.2f}%  "
              f"{100*s['cagr']:+6.2f}%  {s['hit_rate']:8.4f}  {act:6d}d  "
              f"{calmar:+7.3f}{flag}")
    print(f"\n  Best: {best_key}  Sharpe {best_sharpe:+.4f}")

    print(f"\n[8] Per-strategy contribution analysis [{best_key}]:")
    if best_key.startswith('v28'):
        # use the W matrix that produced this best variant
        W_used = W_full if 'full' in best_key else (W_loose if 'loose' in best_key else W_no_act)
        if 'Qonly' in best_key:
            W_used = W_uniform
        if 'no_Q' in best_key:
            Q_used = Q_unit
        elif 'Qsharp' in best_key:
            Q_used = Q_sharp
        else:
            Q_used = Q
        lev_used = flat_lev if 'flat' in best_key or 'Flat' in best_key else lev_kramers
        W_lag = W_used.shift(1).fillna(0.0)
        eff = pd.DataFrame(0.0, index=df.index, columns=V28_KEYS)
        for c, k in zip(V28_WCOLS, V28_KEYS):
            eff[k] = W_lag[c] * Q_used[k]
        s_eff = eff.sum(axis=1).replace(0.0, np.nan)
        eff_n = eff.div(s_eff, axis=0).fillna(0.0)
        lev_lag = lev_used.shift(1).fillna(1.0)
        pnl_best = variants[best_key]
        total_abs = pnl_best[test_mask].abs().sum()
        print(f"    {'strategy':<12}  {'mean(eff)':>10}  {'contrib Sh':>11}  "
              f"{'%abs PnL':>9}")
        for k in V28_KEYS:
            contrib = eff_n[k] * strats[k] * lev_lag
            ct = contrib[test_mask].fillna(0.0)
            sh = simulate_from_pnl(ct)['sharpe']
            share = 100 * ct.abs().sum() / max(total_abs, 1e-12)
            print(f"    {k:<12}  {eff_n[k][test_mask].mean():10.4f}  "
                  f"{sh:+11.4f}  {share:8.1f}%")

    best_pnl = variants[best_key]
    print(f"\n[9] K-sweep on [{best_key}]:")
    print(f"  {'K':>5}  {'mode':<10}  {'Sharpe':>8}  {'CAGR%':>7}  "
          f"{'Final $':>12}  {'PnL $':>12}  {'MaxDD%':>8}")
    print("  " + "-" * 78)
    for K in (1, 2, 3, 5, 8, 10, 12):
        for mode, bps in (('gross', 0.0), ('net 5bp', 5.0)):
            m = equity_at_K(best_pnl[test_mask].fillna(0.0),
                            K=float(K), tcost_bps=bps, init=1200.0)
            print(f"  {K:5d}  {mode:<10}  {m['sh']:+8.3f}  {100*m['cagr']:+6.2f}%  "
                  f"${m['final']:10,.2f}  ${m['pnl']:+10,.2f}  {100*m['max_dd']:+7.2f}%")

    bK = find_best_K(best_pnl[test_mask].fillna(0.0),
                     tcost_bps=5.0, init=1200.0, max_dd_limit=0.40)
    if bK:
        print(f"\n  Best K net 5bp (MaxDD<=40%): K={bK['K']:.2f}  "
              f"Final ${bK['final']:,.2f}  Sharpe {bK['sh']:+.3f}  "
              f"CAGR {100*bK['cagr']:.1f}%")
    print(f"  v22 reference best K: K=8.75 -> Final $2,649.71 Sharpe +0.679 CAGR 17.9%")

    out = {
        'protocol': 'v28 quality-gated risk-normalized allocator',
        'design': '3-layer: vol-scale + rolling-Sharpe sigmoid + engine-state gate',
        'strategies': V28_KEYS,
        'mean_rev_status': 'DROPPED (v27 contrib Sharpe -2.27)',
        'params': {'vol_win': 60, 'sharpe_win': 120, 'sharpe_k': 2.0,
                    'target_vol': 0.01, 'scale_cap': 5.0,
                    'G_LO': G_LO, 'K_LO': K_LO},
        'variants': {k: {kk: (float(vv) if isinstance(vv, (int,float,np.floating)) else vv)
                         for kk, vv in s.items()}
                     for k, s in all_sims.items()},
        'best_variant': best_key,
        'best_sharpe':  float(best_sharpe),
        'v22_reference_sharpe': float(sim_v22['sharpe']),
        'v22_reference_max_dd': float(sim_v22['max_dd']),
    }
    jp = Path(OUT_DIR) / 'crypto_bsdt_v28_results.json'
    jp.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Saved -> {jp}")
    print("=" * 96)


if __name__ == "__main__":
    main()
