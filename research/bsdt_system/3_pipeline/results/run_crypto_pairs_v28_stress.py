"""
Crypto BSDT v28 — Walk-Forward + Parameter Stress Test
=======================================================

Purpose: validate v28_full_no_brk Sharpe +2.34 is real signal, not overfit.

Tests:
  [A] Year-by-year breakdown (2023, 2024, 2025, 2026 YTD)
  [B] Trade-level concentration (top-10 days, top-decile share)
  [C] Parameter stress grid:
        sharpe_k    in {1.2, 1.5, 2.0, 2.5, 3.0}
        vol_win     in {40, 60, 80}
        sharpe_win  in {90, 120, 180}
        gate (G_LO,K_LO) in {(.35,.20),(.50,.30),(.65,.50)}
  [D] v22_core vs v28_core direct comparison (isolate diversification)
  [E] Relaxed-gate sweet spot search (target 150-200 active days, Sh > 1.8)

Reuses ALL building blocks from v28; no new signals.
"""
from __future__ import annotations
import os, sys, json, itertools
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
from run_crypto_pairs_v27 import compute_unsigned_weights
from run_crypto_pairs_v28 import (
    compute_quality_risk_weights, build_v28_pnl, V28_KEYS, V28_WCOLS,
)


# =====================================================================
#   HELPERS
# =====================================================================

def yearly_stats(pnl: pd.Series) -> pd.DataFrame:
    """Per-calendar-year Sharpe/CAGR/MaxDD/active."""
    rows = []
    for y, sub in pnl.groupby(pnl.index.year):
        sub = sub.fillna(0.0)
        if len(sub) < 30:
            continue
        s = simulate_from_pnl(sub)
        act = int(sub.abs().gt(1e-9).sum())
        rows.append({
            'year': int(y),
            'days': len(sub),
            'active': act,
            'sharpe': s['sharpe'],
            'cagr': s['cagr'],
            'max_dd': s['max_dd'],
            'cum_ret': s['cum_return'],
        })
    return pd.DataFrame(rows)


def concentration_stats(pnl: pd.Series) -> dict:
    p = pnl[pnl.abs() > 1e-9].fillna(0.0)
    if len(p) == 0:
        return {'n': 0, 'top10_share': 0.0, 'top_decile_share': 0.0,
                'top10_neg_share': 0.0}
    abs_pnl = p.abs().sort_values(ascending=False)
    total = abs_pnl.sum()
    top10 = abs_pnl.head(10).sum() / max(total, 1e-12)
    decile = max(1, len(p) // 10)
    top_decile = abs_pnl.head(decile).sum() / max(total, 1e-12)
    # Top 10 worst loss share
    worst = p.sort_values().head(10)
    top10_neg = worst.sum() / max(p[p < 0].sum(), -1e-12)
    return {'n': len(p), 'top10_share': float(top10),
            'top_decile_share': float(top_decile),
            'top10_neg_share': float(top10_neg)}


# =====================================================================
#   MAIN
# =====================================================================

def main():
    out_dir = Path(OUT_DIR); out_dir.mkdir(parents=True, exist_ok=True)
    print("=" * 96)
    print("  v28 STRESS TEST — Walk-Forward + Parameter Robustness")
    print("=" * 96)

    print("\n[1] Loading data + building strategies (one-time) ...")
    df = fetch_and_prepare()
    df = add_cross_market_features(df)
    funding = fetch_binance_funding(symbols=['ETHUSDT','BTCUSDT'], start='2020-06-01')
    df = add_leverage_features(df, funding)

    train_mask     = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask      = df.index >= TEST_START
    train_mask_arr = np.asarray(train_mask, dtype=bool)

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

    # PRODUCTION strategy book — breakout permanently dropped
    strats_no_brk = {
        'trend':    pnl_v18s,
        'pairs':    pnl_pairs,
        'breakout': pd.Series(0.0, index=df.index),  # zeroed
        'macro':    pnl_macro,
    }

    print("\n[2] Engine signal sweep ...")
    X_panel = _build_state_panel(df)
    M, net, geom_e, lyap, info, ews, e_star, sigma_n = calibrate_frozen_engine(
        X_panel, train_mask_arr)
    patch_precursor_scale(ews, M, X_panel[train_mask_arr])
    F = emit_global_signals(df, X_panel, M, net, geom_e, lyap, ews, sigma_n)

    flat_lev = pd.Series(1.0, index=df.index)

    # =================================================================
    #   [A] v22 reference + production v28 baseline
    # =================================================================
    print("\n[3] v22 reference reproduction ...")
    sim_v22, pnl_v22, _ = run_repr_pipeline(
        X_panel, train_mask_arr, df, test_mask, pnl_v18s)

    Q_prod = compute_quality_risk_weights(strats_no_brk, vol_win=60, sharpe_win=120,
                                            sharpe_k=2.0, target_vol=0.01,
                                            scale_cap=5.0)
    W_prod = compute_unsigned_weights(F, use_activation=True, g_lo=0.50, k_lo=0.30)
    pnl_v28 = build_v28_pnl(strats_no_brk, W_prod, Q_prod, flat_lev, df.index)

    print("\n" + "=" * 96)
    print("  [TEST A] YEAR-BY-YEAR BREAKDOWN")
    print("=" * 96)
    for name, p in [('v22_baseline', pnl_v22), ('v28_full_no_brk', pnl_v28)]:
        ys = yearly_stats(p[test_mask])
        print(f"\n  {name}:")
        print(f"    {'year':>5}  {'days':>5}  {'active':>7}  {'sharpe':>8}  "
              f"{'cagr%':>7}  {'maxdd%':>8}  {'cumret%':>8}")
        for _, r in ys.iterrows():
            print(f"    {r['year']:>5}  {r['days']:>5}  {r['active']:>7}  "
                  f"{r['sharpe']:+8.3f}  {100*r['cagr']:+6.2f}%  "
                  f"{100*r['max_dd']:+7.2f}%  {100*r['cum_ret']:+7.2f}%")

    # =================================================================
    #   [B] Concentration analysis
    # =================================================================
    print("\n" + "=" * 96)
    print("  [TEST B] PnL CONCENTRATION ANALYSIS")
    print("=" * 96)
    print(f"\n  {'variant':<22}  {'n_act':>6}  {'top10/total%':>13}  "
          f"{'top10pct/total%':>17}  {'top10_loss/loss%':>18}")
    for name, p in [('v22_baseline', pnl_v22), ('v28_full_no_brk', pnl_v28)]:
        c = concentration_stats(p[test_mask])
        print(f"  {name:<22}  {c['n']:>6}  {100*c['top10_share']:>12.1f}%  "
              f"{100*c['top_decile_share']:>16.1f}%  "
              f"{100*c['top10_neg_share']:>17.1f}%")
    print("\n  Healthy: top10/total < 30%, top10pct < 60%, top10_loss < 50%")

    # =================================================================
    #   [C] Parameter stress grid
    # =================================================================
    print("\n" + "=" * 96)
    print("  [TEST C] PARAMETER STRESS GRID")
    print("=" * 96)
    print("\n  Varying sharpe_k (gate sharpness) holding vol_win=60, sharpe_win=120, gate=(.50,.30):")
    print(f"    {'sharpe_k':>10}  {'sharpe':>8}  {'maxdd%':>8}  {'cagr%':>7}  {'active':>7}")
    sk_results = []
    for sk in (1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0):
        Q = compute_quality_risk_weights(strats_no_brk, vol_win=60, sharpe_win=120,
                                          sharpe_k=sk, target_vol=0.01, scale_cap=5.0)
        p = build_v28_pnl(strats_no_brk, W_prod, Q, flat_lev, df.index)
        s = simulate_from_pnl(p[test_mask].fillna(0.0))
        act = int(p[test_mask].abs().gt(1e-9).sum())
        sk_results.append({'sharpe_k': sk, 'sharpe': s['sharpe'],
                           'max_dd': s['max_dd'], 'cagr': s['cagr'], 'active': act})
        print(f"    {sk:>10.2f}  {s['sharpe']:+8.3f}  {100*s['max_dd']:+7.2f}%  "
              f"{100*s['cagr']:+6.2f}%  {act:>6}d")

    print("\n  Varying vol_win:")
    print(f"    {'vol_win':>10}  {'sharpe':>8}  {'maxdd%':>8}  {'active':>7}")
    for vw in (30, 40, 60, 80, 120):
        Q = compute_quality_risk_weights(strats_no_brk, vol_win=vw, sharpe_win=120,
                                          sharpe_k=2.0, target_vol=0.01, scale_cap=5.0)
        p = build_v28_pnl(strats_no_brk, W_prod, Q, flat_lev, df.index)
        s = simulate_from_pnl(p[test_mask].fillna(0.0))
        act = int(p[test_mask].abs().gt(1e-9).sum())
        print(f"    {vw:>10}  {s['sharpe']:+8.3f}  {100*s['max_dd']:+7.2f}%  {act:>6}d")

    print("\n  Varying sharpe_win:")
    print(f"    {'sharpe_win':>11}  {'sharpe':>8}  {'maxdd%':>8}  {'active':>7}")
    for sw in (60, 90, 120, 180, 252):
        Q = compute_quality_risk_weights(strats_no_brk, vol_win=60, sharpe_win=sw,
                                          sharpe_k=2.0, target_vol=0.01, scale_cap=5.0)
        p = build_v28_pnl(strats_no_brk, W_prod, Q, flat_lev, df.index)
        s = simulate_from_pnl(p[test_mask].fillna(0.0))
        act = int(p[test_mask].abs().gt(1e-9).sum())
        print(f"    {sw:>11}  {s['sharpe']:+8.3f}  {100*s['max_dd']:+7.2f}%  {act:>6}d")

    print("\n  Varying engine gate (G_LO, K_LO):")
    print(f"    {'(G,K)':<14}  {'sharpe':>8}  {'maxdd%':>8}  {'cagr%':>7}  {'active':>7}")
    Q_default = compute_quality_risk_weights(strats_no_brk, vol_win=60, sharpe_win=120,
                                               sharpe_k=2.0, target_vol=0.01, scale_cap=5.0)
    for g, k in [(0.20,0.10), (0.35,0.20), (0.50,0.30), (0.50,0.50),
                 (0.65,0.30), (0.65,0.50), (0.80,0.50)]:
        W = compute_unsigned_weights(F, use_activation=True, g_lo=g, k_lo=k)
        p = build_v28_pnl(strats_no_brk, W, Q_default, flat_lev, df.index)
        s = simulate_from_pnl(p[test_mask].fillna(0.0))
        act = int(p[test_mask].abs().gt(1e-9).sum())
        print(f"    ({g:.2f},{k:.2f})    {s['sharpe']:+8.3f}  {100*s['max_dd']:+7.2f}%  "
              f"{100*s['cagr']:+6.2f}%  {act:>6}d")

    # =================================================================
    #   [D] v22_core vs v28_core (isolate diversification)
    # =================================================================
    print("\n" + "=" * 96)
    print("  [TEST D] v22_core vs v28_core — DIVERSIFICATION vs FILTERING")
    print("=" * 96)
    # v22 already = v18_smooth + engine gate from run_repr_pipeline
    # v28_trend_only = use only trend strategy under same gate+Q
    strats_trend_only = {
        'trend':    pnl_v18s,
        'pairs':    pd.Series(0.0, index=df.index),
        'breakout': pd.Series(0.0, index=df.index),
        'macro':    pd.Series(0.0, index=df.index),
    }
    Q_trend_only = compute_quality_risk_weights(strats_trend_only, vol_win=60,
                                                  sharpe_win=120, sharpe_k=2.0,
                                                  target_vol=0.01, scale_cap=5.0)
    pnl_v28_trendonly = build_v28_pnl(strats_trend_only, W_prod, Q_trend_only,
                                        flat_lev, df.index)
    pnl_v28_3strat    = pnl_v28  # already trend+pairs+macro

    print(f"\n  {'variant':<28}  {'sharpe':>8}  {'maxdd%':>8}  {'cagr%':>7}  {'active':>7}")
    for name, p in [
        ('v22_core (v18s + v22 gate)',    pnl_v22),
        ('v28_trend_only (trend + Q+W)',  pnl_v28_trendonly),
        ('v28_full_no_brk (3-strat)',     pnl_v28_3strat),
    ]:
        s = simulate_from_pnl(p[test_mask].fillna(0.0))
        act = int(p[test_mask].abs().gt(1e-9).sum())
        print(f"  {name:<28}  {s['sharpe']:+8.3f}  {100*s['max_dd']:+7.2f}%  "
              f"{100*s['cagr']:+6.2f}%  {act:>6}d")
    print("\n  Reads: trend_only Sharpe vs 3-strat Sharpe = diversification value.")

    # =================================================================
    #   [E] Relaxed-gate sweet-spot search (target 150-200 active days)
    # =================================================================
    print("\n" + "=" * 96)
    print("  [TEST E] RELAXED-GATE SWEET-SPOT (target 150-200 active days, Sh > 1.8)")
    print("=" * 96)
    print(f"\n  {'(sk, G, K)':<16}  {'sharpe':>8}  {'maxdd%':>8}  {'cagr%':>7}  "
          f"{'active':>7}  {'calmar':>7}")
    candidates = []
    for sk, (g, k) in itertools.product(
            (1.2, 1.5, 1.8, 2.0),
            [(0.35, 0.20), (0.40, 0.20), (0.45, 0.25), (0.50, 0.30), (0.50, 0.20)]):
        Q = compute_quality_risk_weights(strats_no_brk, vol_win=60, sharpe_win=120,
                                          sharpe_k=sk, target_vol=0.01, scale_cap=5.0)
        W = compute_unsigned_weights(F, use_activation=True, g_lo=g, k_lo=k)
        p = build_v28_pnl(strats_no_brk, W, Q, flat_lev, df.index)
        s = simulate_from_pnl(p[test_mask].fillna(0.0))
        act = int(p[test_mask].abs().gt(1e-9).sum())
        cal = s['cagr']/abs(s['max_dd']) if s['max_dd'] != 0 else float('nan')
        rec = {'sk': sk, 'g': g, 'k': k, 'sharpe': s['sharpe'],
               'max_dd': s['max_dd'], 'cagr': s['cagr'], 'active': act,
               'calmar': cal}
        candidates.append(rec)
        flag = ''
        if 150 <= act <= 200 and s['sharpe'] > 1.8:
            flag = ' <-- TARGET'
        print(f"  ({sk:.1f},{g:.2f},{k:.2f}) {s['sharpe']:+8.3f}  "
              f"{100*s['max_dd']:+7.2f}%  {100*s['cagr']:+6.2f}%  "
              f"{act:>6}d  {cal:+7.3f}{flag}")

    # =================================================================
    #   SAVE + VERDICT
    # =================================================================
    print("\n" + "=" * 96)
    print("  VERDICT")
    print("=" * 96)
    sk_sharpes = [r['sharpe'] for r in sk_results]
    sk_range_2_3 = [r['sharpe'] for r in sk_results if 1.5 <= r['sharpe_k'] <= 2.5]
    sk_min, sk_max = min(sk_range_2_3), max(sk_range_2_3)

    sim_v28 = simulate_from_pnl(pnl_v28[test_mask].fillna(0.0))
    sim_trend = simulate_from_pnl(pnl_v28_trendonly[test_mask].fillna(0.0))
    div_value = sim_v28['sharpe'] - sim_trend['sharpe']
    conc_v28 = concentration_stats(pnl_v28[test_mask])

    print(f"\n  Production (sk=2.0): Sharpe {sim_v28['sharpe']:+.3f}, "
          f"MaxDD {100*sim_v28['max_dd']:+.2f}%, active {int(pnl_v28[test_mask].abs().gt(1e-9).sum())}d")
    print(f"  Param stability (sharpe_k in [1.5, 2.5]): "
          f"Sharpe range [{sk_min:+.3f}, {sk_max:+.3f}]   "
          f"spread = {sk_max-sk_min:+.3f}")
    print(f"  Diversification value: trend_only {sim_trend['sharpe']:+.3f}  ->  "
          f"3-strat {sim_v28['sharpe']:+.3f}   delta = {div_value:+.3f}")
    print(f"  Concentration: top-10 days = {100*conc_v28['top10_share']:.1f}% of |PnL|; "
          f"top-decile = {100*conc_v28['top_decile_share']:.1f}%")
    print(f"  Year coverage: see [TEST A] - all years should show Sharpe > 0")

    out = {
        'production_sharpe':         float(sim_v28['sharpe']),
        'production_max_dd':         float(sim_v28['max_dd']),
        'param_stability_range':     [float(sk_min), float(sk_max)],
        'param_stability_spread':    float(sk_max - sk_min),
        'diversification_delta':     float(div_value),
        'trend_only_sharpe':         float(sim_trend['sharpe']),
        'concentration_top10':       float(conc_v28['top10_share']),
        'concentration_top_decile':  float(conc_v28['top_decile_share']),
        'sharpe_k_sweep':            sk_results,
        'gate_sweet_spot_candidates': candidates,
        'yearly_v22':                yearly_stats(pnl_v22[test_mask]).to_dict(orient='records'),
        'yearly_v28':                yearly_stats(pnl_v28[test_mask]).to_dict(orient='records'),
    }
    jp = Path(OUT_DIR) / 'crypto_bsdt_v28_stress_test.json'
    jp.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Saved -> {jp}")
    print("=" * 96)


if __name__ == "__main__":
    main()
