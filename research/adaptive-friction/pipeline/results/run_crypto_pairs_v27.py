"""
Crypto BSDT v27 - Unsigned Allocator with State-Space Direction
================================================================

Fix for v26 failure mode:
  v26 used `sign(cos_theta)` as a directional view. cos_theta lives in
  engine-internal space (alignment between two engine gradients) and has
  mean -0.71 in the test panel -> it force-shorted three strategies into
  a 3-year bull market.

v27 design:
  1. DIRECTION comes from each strategy's own signed PnL series. No
     external sign multiplication. Strategies are responsible for their
     own long/short calls.
  2. ENGINE SCALARS used purely as NON-NEGATIVE GATES:
       align = |cos_theta|        (confidence: how coherent are the
                                   engine's two gradient fields)
       geom_n, prec_n             (sigmoid of rolling z, structural stress
                                   and early warning)
       kp = kramers_p             (escape probability)
  3. ACTIVATION GATE recovers v22's selectivity edge: only trade when
     engine state is "interesting".

Weight functions (all >= 0):
  mag_trend    = align    * (1 - geom_n) * (1 - prec_n)   # calm + coherent
  mag_breakout = align    * kp           * (1 - geom_n)   # escape + coherent
  mag_macro    = align    * geom_n       * (1 - kp)       # stress + coherent + trapped
  mag_mr       = (1-align) * prec_n                       # chop + warning
  mag_pairs    = (1-align) * (1 - kp)                     # chop + trapped (mkt-neutral)

  W = stack(mag) / sum(mag)              # L1 normalize (positive)
  W = W.ewm(span=3).mean()               # smooth
  activation = (geom_n > G_LO) & (kp > K_LO)
  W = W * activation                     # selective participation

  pnl_t = lev[t-1] * sum_s W[t-1, s] * pnl_s[t]
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
from run_crypto_pairs_v24 import compute_mahal_risk, hard_gate, GATE_SIGMA, GATE_DAMP
from run_crypto_pairs_v26 import (
    compute_donchian_breakout, compute_mean_reversion,
    _sigmoid, _rolling_z,
)


# =====================================================================
#   PHASE 1 - UNSIGNED CONTINUOUS WEIGHTS  (the fix)
# =====================================================================

# Activation thresholds - controls participation
G_LO = 0.50      # geom_n > G_LO required (median or above)
K_LO = 0.30      # kp     > K_LO required (some escape probability)


def compute_unsigned_weights(F: pd.DataFrame, win: int = 252,
                              smooth_span: int = 3,
                              g_lo: float = G_LO, k_lo: float = K_LO,
                              use_activation: bool = True) -> pd.DataFrame:
    """All-positive weights from engine state.

    Direction lives in each strategy's own PnL series; this function only
    decides HOW MUCH to allocate to each, not which side.

    Returns DataFrame[T, 5] with cols [w_trend, w_pairs, w_breakout, w_mr,
    w_macro], all non-negative, EWM(span) smoothed, optionally gated.
    """
    geom = F['geom_score'].fillna(0.0)
    prec = F['precursor_score'].fillna(0.0)
    cos  = F['cos_theta'].fillna(0.0).clip(-1.0, 1.0)
    kp   = F['kramers_p'].fillna(0.0).clip(0.0, 1.0)

    geom_n = _sigmoid(_rolling_z(geom, win=win, lag=1))
    prec_n = _sigmoid(_rolling_z(prec, win=win, lag=1))
    align  = cos.abs()                          # in [0,1]: coherence

    one_minus_align = 1.0 - align
    one_minus_geom  = 1.0 - geom_n
    one_minus_prec  = 1.0 - prec_n
    one_minus_kp    = 1.0 - kp

    mag_trend    = align           * one_minus_geom * one_minus_prec
    mag_breakout = align           * kp             * one_minus_geom
    mag_macro    = align           * geom_n         * one_minus_kp
    mag_mr       = one_minus_align * prec_n
    mag_pairs    = one_minus_align * one_minus_kp

    W = pd.DataFrame({
        'w_trend':    mag_trend,
        'w_pairs':    mag_pairs,
        'w_breakout': mag_breakout,
        'w_mr':       mag_mr,
        'w_macro':    mag_macro,
    }, index=F.index)

    denom = W.sum(axis=1).replace(0.0, np.nan)
    W = W.div(denom, axis=0).fillna(0.0)

    if smooth_span and smooth_span > 1:
        W = W.ewm(span=smooth_span, adjust=False).mean()
        denom2 = W.sum(axis=1).replace(0.0, np.nan)
        W = W.div(denom2, axis=0).fillna(0.0)

    if use_activation:
        activation = ((geom_n > g_lo) & (kp > k_lo)).astype(float)
        W = W.mul(activation, axis=0)

    return W


# =====================================================================
#   PHASE 2 - PORTFOLIO ASSEMBLY
# =====================================================================

def build_v27_pnl(strats: dict, W: pd.DataFrame, lev: pd.Series,
                  index: pd.Index) -> pd.Series:
    """pnl_t = lev[t-1] * sum_s W[t-1, s] * pnl_s[t]
    Strategies provide their own signed PnL; W is non-negative sizing.
    """
    cols = ['w_trend', 'w_pairs', 'w_breakout', 'w_mr', 'w_macro']
    keys = ['trend',   'pairs',   'breakout',   'mr',   'macro']
    W_lag   = W.shift(1).fillna(0.0)
    lev_lag = lev.shift(1).fillna(1.0)
    pnl = pd.Series(0.0, index=index)
    for c, k in zip(cols, keys):
        pnl = pnl + W_lag[c] * strats[k]
    return pnl * lev_lag


# =====================================================================
#   MAIN
# =====================================================================

def main():
    out_dir = Path(OUT_DIR); out_dir.mkdir(parents=True, exist_ok=True)
    print("=" * 96)
    print("  CRYPTO BSDT v27 - Unsigned Allocator (direction = strategy PnL)")
    print("  Engine scalars used as non-negative gates only; no sign(cos_theta)")
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

    print("\n[2] Building shared signals (omega, mfls, gamma, phase) ...")
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

    print("\n[3] Building strategies ...")
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
    pnl_mr       = compute_mean_reversion(df, win=10, z_in=2.0, z_out=0.5)

    strats = {
        'trend':    pnl_v18s,
        'pairs':    pnl_pairs,
        'breakout': pnl_breakout,
        'mr':       pnl_mr,
        'macro':    pnl_macro,
    }

    print("\n  Per-strategy STANDALONE Sharpe (test):")
    print(f"    {'strategy':<12}  {'Sharpe':>8}  {'CAGR%':>7}  {'MaxDD%':>8}  {'Active':>7}")
    for k, p in strats.items():
        s = simulate_from_pnl(p[test_mask].fillna(0.0))
        act = int(p[test_mask].abs().gt(1e-9).sum())
        print(f"    {k:<12}  {s['sharpe']:+8.4f}  {100*s['cagr']:+6.2f}%  "
              f"{100*s['max_dd']:+7.2f}%  {act:6d}d")

    print("\n[4] Running physics engine for state signals ...")
    X_panel = _build_state_panel(df)
    M, net, geom_e, lyap, info, ews, e_star, sigma_n = calibrate_frozen_engine(
        X_panel, train_mask_arr)
    patch_precursor_scale(ews, M, X_panel[train_mask_arr])
    F = emit_global_signals(df, X_panel, M, net, geom_e, lyap, ews, sigma_n)

    print("\n[5] Building unsigned weight variants ...")

    W_no_act      = compute_unsigned_weights(F, use_activation=False)
    W_full        = compute_unsigned_weights(F, use_activation=True,
                                              g_lo=G_LO, k_lo=K_LO)
    W_tight       = compute_unsigned_weights(F, use_activation=True,
                                              g_lo=0.65, k_lo=0.50)
    W_loose       = compute_unsigned_weights(F, use_activation=True,
                                              g_lo=0.35, k_lo=0.20)

    lev_kramers = (LEV_LO + (LEV_HI - LEV_LO) * F['kramers_p'].fillna(0.5)).clip(LEV_LO, LEV_HI)

    print(f"\n  Activation rates [test]:")
    for name, W in [('no_act', W_no_act), ('full(.50/.30)', W_full),
                    ('tight(.65/.50)', W_tight), ('loose(.35/.20)', W_loose)]:
        active = int((W[test_mask].sum(axis=1) > 1e-6).sum())
        print(f"    {name:<16}  active days: {active:4d} / {int(test_mask.sum())}")

    print(f"\n  Weight stats [test, W_full]:")
    print(f"    {'strategy':<12}  {'mean(w)':>10}  {'std(w)':>10}  {'%active':>8}")
    for c in W_full.columns:
        ws = W_full[c][test_mask]
        pct_active = 100 * (ws.values > 1e-3).sum() / len(ws)
        print(f"    {c:<12}  {ws.mean():10.4f}  {ws.std():10.4f}  {pct_active:7.1f}%")

    print("\n[6] Reproducing v22 reference ...")
    sim_v22, pnl_v22, _ = run_repr_pipeline(
        X_panel, train_mask_arr, df, test_mask, pnl_v18s)

    variants = {}
    variants['v22_baseline']      = pnl_v22
    variants['v27_no_act']        = build_v27_pnl(strats, W_no_act, lev_kramers, df.index)
    variants['v27_no_act_flat']   = build_v27_pnl(strats, W_no_act, pd.Series(1.0, index=df.index), df.index)
    variants['v27_full']          = build_v27_pnl(strats, W_full, lev_kramers, df.index)
    variants['v27_full_flat']     = build_v27_pnl(strats, W_full, pd.Series(1.0, index=df.index), df.index)
    variants['v27_tight']         = build_v27_pnl(strats, W_tight, lev_kramers, df.index)
    variants['v27_loose']         = build_v27_pnl(strats, W_loose, lev_kramers, df.index)

    risk_z = pd.Series(compute_mahal_risk(X_panel, train_mask_arr).values, index=df.index)
    ps_gate = pd.Series(hard_gate(risk_z.values, GATE_SIGMA, GATE_DAMP), index=df.index)
    variants['v27_full_mgate']    = variants['v27_full'] * ps_gate
    variants['v27_tight_mgate']   = variants['v27_tight'] * ps_gate

    strats_no_brk = dict(strats); strats_no_brk['breakout'] = pd.Series(0.0, index=df.index)
    variants['v27_full_no_brk']   = build_v27_pnl(strats_no_brk, W_full, lev_kramers, df.index)

    strats_no_mr = dict(strats); strats_no_mr['mr'] = pd.Series(0.0, index=df.index)
    variants['v27_full_no_mr']    = build_v27_pnl(strats_no_mr, W_full, lev_kramers, df.index)

    print("\n" + "=" * 96)
    print("  v27 ABLATION TABLE  (test period, K=1 gross)")
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

    print(f"\n[7] Per-strategy contribution analysis [v27_full]:")
    W_lag   = W_full.shift(1).fillna(0.0)
    lev_lag = lev_kramers.shift(1).fillna(1.0)
    print(f"    {'strategy':<12}  {'contrib Sh':>11}  {'mean*1e4':>9}  {'%abs PnL':>9}")
    pnl_v27_full = variants['v27_full']
    total_abs = pnl_v27_full[test_mask].abs().sum()
    for c, k in zip(W_full.columns, ['trend','pairs','breakout','mr','macro']):
        contrib = W_lag[c] * strats[k] * lev_lag
        ct = contrib[test_mask].fillna(0.0)
        sh = simulate_from_pnl(ct)['sharpe']
        share = 100 * ct.abs().sum() / max(total_abs, 1e-12)
        print(f"    {k:<12}  {sh:+11.4f}  {1e4*ct.mean():+9.3f}  {share:8.1f}%")

    best_pnl = variants[best_key]
    print(f"\n[8] K-sweep on [{best_key}]:")
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
        'protocol': 'v27 unsigned-allocator (direction from strategy PnL)',
        'design': 'Engine scalars used as non-negative gates only',
        'strategies': list(strats.keys()),
        'activation_thresholds': {'G_LO': G_LO, 'K_LO': K_LO},
        'variants': {k: {kk: (float(vv) if isinstance(vv, (int,float,np.floating)) else vv)
                         for kk, vv in s.items()}
                     for k, s in all_sims.items()},
        'best_variant': best_key,
        'best_sharpe':  float(best_sharpe),
        'v22_reference_sharpe': float(sim_v22['sharpe']),
        'v22_reference_max_dd': float(sim_v22['max_dd']),
    }
    jp = Path(OUT_DIR) / 'crypto_bsdt_v27_results.json'
    jp.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Saved -> {jp}")
    print("=" * 96)


if __name__ == "__main__":
    main()
