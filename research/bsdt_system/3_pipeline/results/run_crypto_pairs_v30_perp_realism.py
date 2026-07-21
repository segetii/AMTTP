"""
Crypto BSDT v30 - LONG/SHORT SPLIT, FUNDING COSTS, $100 EQUITY SIMULATION
==========================================================================

Three deliverables:

  [F5] LONG/SHORT decomposition (portfolio level)
       Split portfolio PnL by ETH direction on the underlying day:
         - up_pnl   = sum of pnl on days where ret_eth > 0
         - down_pnl = sum of pnl on days where ret_eth < 0
         - flat_pnl = sum on days where ret_eth ~ 0
       Reveals whether edge depends on long bias, short bias, or both.

  [F6] FUNDING COST (perp realism)
       Daily funding = sum over s of |eff[t-1, s]| * |fr[s, t]| * 3
       (3 funding periods * 8h = 24h, worst-case = always paying side).
       Deducted from gross PnL at K=1; scaled with K for leverage runs.

  [SIM] $100 STARTING EQUITY at K = {1, 2, best_K} for the production
        v28_full_no_brk system, on test period (2023-01-01 -> 2026-04-25).
        Includes 5bp round-trip fee + worst-case funding.

Production reference (peak Sharpe mode):
  vol_win=60, sharpe_win=120, sharpe_k=2.0, G_LO=0.50, K_LO=0.30,
  alpha=1.0 (fully gated)
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
    simulate_from_pnl, equity_at_K,
    _build_state_panel,
    TRAIN_START, TRAIN_END, TEST_START, OUT_DIR,
    GAMMA_SCORE_WIN,
)
from run_crypto_pairs_v22 import (
    calibrate_frozen_engine, patch_precursor_scale, emit_global_signals,
)
from run_crypto_pairs_v27 import compute_unsigned_weights
from run_crypto_pairs_v28 import (
    compute_quality_risk_weights, build_v28_pnl, V28_KEYS, V28_WCOLS,
)


# =====================================================================
#   STRATEGY BUILDER (returns full panel including funding map)
# =====================================================================

def build_book(df, train_mask, train_mask_arr):
    feats_strat = ['ret_eth_z','ret_btc_z','ret_sol_z','ret_bnb_z',
                   'vol_eth_z','vol_btc_z','btc_dom_z','cross_disp_z']
    feats_ext   = feats_strat + ['ret_spx_z','dvix_z','ret_dxy_z']
    omega_strat, mfls_eth, gamma_eth = compute_bsdt(df, feats_strat, window=60)
    omega_ext,   _,        _         = compute_bsdt(df, feats_ext,   window=60)
    _, A_rank, dA_fast, dA_rank      = compute_activity_signals(mfls_eth, gamma_eth)
    gamma_rank  = compute_gamma_rank(omega_ext, min_periods=60)
    ret7  = df['ret_eth'].rolling(7).sum()
    ret3  = df['ret_eth'].rolling(3).sum()
    phase = detect_phase(omega_strat, ret7, ret3, df['btc_dom_z'])

    pos_A_dir = setup_a_directional(df, omega_strat, mfls_eth, gamma_eth, phase)
    pos_btc_macro, pos_alt_macro = route_btcalt_macro(df, omega_strat, A_rank, dA_rank)

    pairs_def = [
        ('P1_ETH_BTC','log_eth','log_btc','ret_eth','ret_btc'),
        ('P2_ETH_SOL','log_eth','log_sol','ret_eth','ret_sol'),
        ('P3_ETH_BNB','log_eth','log_bnb','ret_eth','ret_bnb'),
    ]
    pair_pnls = []
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
        pos = route_pair_v7(omega_strat, A_rank, sd['z'], sd['udl_state'],
                            sd['poa'], sd['manifold_valid'])
        pair_pnls.append(get_daily_pnl(pos, sd['sret']))

    pnl_base = {
        'A_directional': get_daily_pnl(pos_A_dir, df['ret_eth']),
        'P1':            pair_pnls[0],
        'P2':            pair_pnls[1],
        'P3':            pair_pnls[2],
        'M_alt':         get_daily_pnl(pos_alt_macro, df['ret_eth']),
        'M_btc':         get_daily_pnl(pos_btc_macro, df['ret_btc']),
    }
    V_state  = compute_state_vector(omega_strat, gamma_rank, mfls_eth, dA_fast)
    phi_18s, align_18s = compute_geom_signals_v18_smooth(V_state)
    lev_mult = compute_leverage_dial(gamma_rank)
    lev_v18s = apply_geom_penalties_v18(lev_mult, phi_18s, align_18s)
    cs_wts   = compute_cs_weights(pnl_base, window=GAMMA_SCORE_WIN)
    pnl_v10  = pd.Series(0.0, index=df.index)
    for k in pnl_base:
        pnl_v10 += cs_wts[k].shift(1).fillna(1.0/len(pnl_base)) * pnl_base[k]
    pnl_v18s = pnl_v10 * lev_v18s.shift(1).fillna(1.0)
    pnl_pairs = (pair_pnls[0] + pair_pnls[1] + pair_pnls[2]) / 3.0
    pnl_macro = (pnl_base['M_btc'] + pnl_base['M_alt']) / 2.0

    strats = {
        'trend':    pnl_v18s,
        'pairs':    pnl_pairs,
        'breakout': pd.Series(0.0, index=df.index),
        'macro':    pnl_macro,
    }

    X_panel = _build_state_panel(df)
    M, net, geom_e, lyap, info, ews, e_star, sigma_n = calibrate_frozen_engine(
        X_panel, train_mask_arr)
    patch_precursor_scale(ews, M, X_panel[train_mask_arr])
    F = emit_global_signals(df, X_panel, M, net, geom_e, lyap, ews, sigma_n)

    return strats, F, pos_A_dir, lev_v18s


# =====================================================================
#   F6 — FUNDING COST
# =====================================================================

def compute_funding_costs(df, eff: pd.DataFrame, pos_trend: pd.Series) -> dict:
    """
    Three funding scenarios per unit notional per day:

      WORST: always paying side, charge |fr|*3 on every notional unit
        upper bound; assumes adversarial scheduling

      NEUTRAL (most realistic for this book):
        - pairs leg = 0 (market-neutral: long perp_A + short perp_B,
          fundings approximately cancel since both are positive in bull)
        - trend/macro = |fr|*3 *only on net directional notional* (not abs)
          but we don't know macro position sign, so assume 50% offset:
          charge |fr|*3 * 0.5 on trend+macro notional
        - "effective payment fraction" per scenario applied

      DIRECTIONAL: use actual pos_trend sign to compute REAL signed funding
        on the trend leg; pairs=0; macro estimated as half-paying.
        Funding can be NEGATIVE (received).

    Returns dict of pd.Series, each = per-day cost per unit gross K=1 PnL.
    """
    fr_eth = df['fr_eth'].fillna(0.0)
    fr_btc = df['fr_btc'].fillna(0.0)
    fr_avg = (fr_eth + fr_btc) / 2.0  # both perps similar in magnitude

    # WORST: full notional, sign-blind, both legs of pairs charged
    notional = eff.abs().sum(axis=1).shift(1).fillna(0.0)
    worst = notional * fr_avg.abs() * 3.0

    # NEUTRAL: pairs=0, trend+macro = 50% of notional × |fr| × 3
    n_directional = (eff['trend'].abs() + eff['macro'].abs()).shift(1).fillna(0.0)
    neutral = n_directional * fr_avg.abs() * 3.0 * 0.5

    # DIRECTIONAL: trend leg uses actual pos sign; macro half-paying
    # When long with positive funding → pays; when short with positive → receives
    pt = pos_trend.shift(1).fillna(0.0)
    sign_trend = np.sign(pt)
    # ETH funding is near-perfect proxy for trend's funding (trend is on ETH)
    trend_fund = eff['trend'].shift(1).fillna(0.0) * sign_trend * fr_eth * 3.0
    macro_fund = eff['macro'].abs().shift(1).fillna(0.0) * fr_avg.abs() * 3.0 * 0.5
    # signed: trend can be net negative (i.e., receive funding)
    directional = trend_fund + macro_fund

    return {'worst': worst, 'neutral': neutral, 'directional': directional}


# =====================================================================
#   $100 EQUITY SIMULATION (with fees + funding)
# =====================================================================

def equity_curve(pnl_gross, funding_per_unit, K, *, init=100.0,
                 tcost_bps=5.0):
    """
    Net daily return = K * pnl_gross  -  K * funding_per_unit  -  fee
    fee triggers when |pnl| > 0 (entry/exit cost lump-sum)
    """
    p = pnl_gross.fillna(0.0).astype(float) * K
    fund = funding_per_unit.fillna(0.0).astype(float) * K
    fee = (tcost_bps / 1e4) * (pnl_gross.fillna(0.0).abs() > 0).astype(float)
    r_net = p - fund - fee
    eq = init * (1.0 + r_net).cumprod()
    peak = eq.cummax()
    dd = (eq - peak) / peak
    yrs = len(eq) / 252.0
    cagr = (eq.iloc[-1] / init) ** (1.0 / max(yrs, 1e-9)) - 1.0
    sh = float(np.sqrt(252) * r_net.mean() / r_net.std()) if r_net.std() > 0 else 0.0
    return {
        'K': K, 'init': init, 'final': float(eq.iloc[-1]),
        'pnl_dollar': float(eq.iloc[-1] - init),
        'sharpe_net': sh,
        'cagr': float(cagr),
        'max_dd': float(dd.min()),
        'max_dd_dol': float((eq - peak).min()),
        'gross_fund_drag_bps': float(fund.sum() * 1e4),
        'gross_fee_drag_bps':  float(fee.sum() * 1e4),
        'eq_curve': eq,
    }


def find_best_K_net(pnl_gross, funding_per_unit, *, init=100.0,
                    tcost_bps=5.0, max_dd_limit=0.40,
                    K_grid=np.arange(0.5, 25.05, 0.25)):
    best = None
    for K in K_grid:
        m = equity_curve(pnl_gross, funding_per_unit, float(K),
                         init=init, tcost_bps=tcost_bps)
        if m['max_dd'] < -max_dd_limit:
            continue
        if best is None or m['sharpe_net'] > best['sharpe_net']:
            best = m
    return best


# =====================================================================
#   MAIN
# =====================================================================

def main():
    out_dir = Path(OUT_DIR); out_dir.mkdir(parents=True, exist_ok=True)
    print("=" * 96)
    print("  v30 - LONG/SHORT SPLIT, FUNDING COST, $100 EQUITY SIMULATION")
    print("=" * 96)

    print("\n[1] Loading + building production v28_full_no_brk ...")
    df = fetch_and_prepare()
    df = add_cross_market_features(df)
    funding = fetch_binance_funding(symbols=['ETHUSDT','BTCUSDT'], start='2020-06-01')
    df = add_leverage_features(df, funding)
    train_mask     = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask      = df.index >= TEST_START
    train_mask_arr = np.asarray(train_mask, dtype=bool)

    strats, F, pos_trend, lev_v18s = build_book(df, train_mask, train_mask_arr)
    Q = compute_quality_risk_weights(strats)
    W = compute_unsigned_weights(F, use_activation=True, g_lo=0.50, k_lo=0.30)
    flat = pd.Series(1.0, index=F.index)

    # Build effective weights and PnL
    W_lag = W.shift(1).fillna(0.0)
    eff = pd.DataFrame(0.0, index=F.index, columns=V28_KEYS)
    for c, k in zip(V28_WCOLS, V28_KEYS):
        eff[k] = W_lag[c] * Q[k]
    s = eff.sum(axis=1).replace(0.0, np.nan)
    eff = eff.div(s, axis=0).fillna(0.0)
    pnl_gross = pd.Series(0.0, index=F.index)
    for k in V28_KEYS:
        pnl_gross += eff[k] * strats[k]
    # Note: production v28 uses lev=flat (Kramers off), per peak-Sharpe config
    sim = simulate_from_pnl(pnl_gross[test_mask].fillna(0.0))
    print(f"\n  Gross production PnL: Sharpe={sim['sharpe']:+.3f}  "
          f"DD={100*sim['max_dd']:+.2f}%  active={sim['active_days']}d")

    # =================================================================
    #   [F5] LONG vs SHORT DECOMPOSITION (vs ETH direction)
    # =================================================================
    print("\n" + "=" * 96)
    print("  [F5] LONG/SHORT DECOMPOSITION (PnL by ETH direction)")
    print("=" * 96)
    ret_eth = df['ret_eth']
    p_test  = pnl_gross[test_mask]
    r_test  = ret_eth[test_mask]

    # Three buckets by underlying ETH move that day
    mask_up   = r_test > 0.001
    mask_down = r_test < -0.001
    mask_flat = ~(mask_up | mask_down)
    pnl_up    = p_test[mask_up].sum()
    pnl_down  = p_test[mask_down].sum()
    pnl_flat  = p_test[mask_flat].sum()
    n_up, n_dn, n_fl = int(mask_up.sum()), int(mask_down.sum()), int(mask_flat.sum())
    total = pnl_up + pnl_down + pnl_flat

    print(f"\n  Total test PnL (gross, K=1): {100*total:+.2f}%")
    print(f"\n  {'bucket':<22}  {'days':>5}  {'pnl%':>8}  {'share':>7}  {'avg_per_day_bps':>15}")
    for label, msk, p_sum, n in [
        ('ETH up days   (>0.1%)', mask_up,   pnl_up,   n_up),
        ('ETH flat days',         mask_flat, pnl_flat, n_fl),
        ('ETH down days (<-0.1%)', mask_down, pnl_down, n_dn),
    ]:
        avg_bps = 1e4 * (p_sum / max(n, 1))
        share   = 100 * p_sum / total if total != 0 else 0.0
        print(f"  {label:<22}  {n:>5}  {100*p_sum:+8.2f}%  {share:+6.1f}%  {avg_bps:+13.2f}")

    # Same split restricted to ACTIVE days only (excluding zero-PnL days)
    active = p_test.abs() > 1e-9
    print("\n  Active-only (engine flagged a trade):")
    print(f"  {'bucket':<22}  {'days':>5}  {'pnl%':>8}  {'avg_per_day_bps':>15}")
    for label, msk in [
        ('ETH up   & active',   mask_up & active),
        ('ETH flat & active',   mask_flat & active),
        ('ETH down & active',   mask_down & active),
    ]:
        n = int(msk.sum())
        p_sum = p_test[msk].sum()
        avg = 1e4 * p_sum / max(n, 1)
        print(f"  {label:<22}  {n:>5}  {100*p_sum:+8.2f}%  {avg:+13.2f}")

    # Trend-strategy specific position recovery (this one is single-asset ETH)
    # pos_trend is the directional setup A position vector (clean signed)
    pos_t = pos_trend.shift(1).fillna(0.0)
    long_days  = (pos_t > 0) & test_mask
    short_days = (pos_t < 0) & test_mask
    flat_days  = (pos_t == 0) & test_mask
    pnl_trend = strats['trend']
    print("\n  Trend strategy (setup_A) - explicit position breakdown:")
    print(f"  {'side':<10}  {'days':>5}  {'pnl%':>8}  {'sharpe':>8}")
    for label, msk in [('LONG', long_days), ('SHORT', short_days), ('FLAT', flat_days)]:
        sub = pnl_trend[msk]
        n = int(msk.sum())
        p_sum = sub.sum()
        sd = sub.std() if len(sub) > 1 else 0.0
        sh = float(np.sqrt(252) * sub.mean() / sd) if sd > 0 else 0.0
        print(f"  {label:<10}  {n:>5}  {100*p_sum:+8.2f}%  {sh:+8.3f}")

    # =================================================================
    #   [F6] FUNDING COST (3 scenarios)
    # =================================================================
    print("\n" + "=" * 96)
    print("  [F6] FUNDING COST  (3 scenarios)")
    print("=" * 96)
    fund_scenarios = compute_funding_costs(df, eff, pos_trend)

    print(f"\n  Total drag over test (K=1, bps):")
    for name, fs in fund_scenarios.items():
        bps = 1e4 * fs[test_mask].sum()
        avg = 1e4 * fs[test_mask & (eff.abs().sum(axis=1).shift(1) > 0)].mean()
        print(f"    {name:<13}  total={bps:+8.0f} bps   avg/active_day={avg:+6.2f} bps")

    # =================================================================
    #   [SIM] $100 EQUITY — three funding regimes
    # =================================================================
    print("\n" + "=" * 96)
    print("  [SIM] $100 STARTING EQUITY  (test 2023-01-01 -> 2026-04-25)")
    print("=" * 96)

    rows = []
    for fund_name, fs in fund_scenarios.items():
        print(f"\n  --- Funding scenario: {fund_name.upper()} ---")
        print(f"  {'config':<30}  {'final$':>10}  {'pnl$':>9}  {'cagr%':>7}  "
              f"{'sharpe':>8}  {'maxdd%':>8}")
        for K, label in [(1.0, 'K=1  (no leverage)'),
                          (2.0, 'K=2  (2x perp)'),
                          (5.0, 'K=5  (5x perp)'),
                          (10.0, 'K=10 (10x perp)')]:
            m = equity_curve(pnl_gross[test_mask], fs[test_mask], K=K,
                              init=100.0, tcost_bps=5.0)
            rows.append({'fund': fund_name, 'K': K, **{k: m[k] for k in
                ('final', 'pnl_dollar', 'cagr', 'sharpe_net', 'max_dd')}})
            print(f"  {label:<30}  ${m['final']:>9.2f}  ${m['pnl_dollar']:+8.2f}  "
                  f"{100*m['cagr']:+6.2f}%  {m['sharpe_net']:+8.3f}  "
                  f"{100*m['max_dd']:+7.2f}%")
        bestK = find_best_K_net(pnl_gross[test_mask], fs[test_mask],
                                  init=100.0, tcost_bps=5.0, max_dd_limit=0.20)
        if bestK is not None:
            rows.append({'fund': fund_name, 'K': bestK['K'], 'best_dd20': True,
                         **{k: bestK[k] for k in
                            ('final','pnl_dollar','cagr','sharpe_net','max_dd')}})
            print(f"  K={bestK['K']:.2f} (best, DD<20%)         "
                  f" ${bestK['final']:>9.2f}  ${bestK['pnl_dollar']:+8.2f}  "
                  f"{100*bestK['cagr']:+6.2f}%  {bestK['sharpe_net']:+8.3f}  "
                  f"{100*bestK['max_dd']:+7.2f}%")

    # Yearly curve under DIRECTIONAL (most realistic) at K=2
    print("\n" + "=" * 96)
    print("  YEARLY P&L on $100 - DIRECTIONAL funding, K=2 (2x perp, 5bp fees)")
    print("=" * 96)
    s_real = equity_curve(pnl_gross[test_mask],
                           fund_scenarios['directional'][test_mask], K=2.0,
                           init=100.0, tcost_bps=5.0)
    eq = s_real['eq_curve']
    print(f"\n  Final: ${s_real['final']:.2f}  ({100*(s_real['final']/100-1):+.2f}%)  "
          f"Sharpe={s_real['sharpe_net']:+.3f}  MaxDD={100*s_real['max_dd']:+.2f}%")
    print(f"\n  {'year':>5}  {'start$':>9}  {'end$':>9}  {'pnl$':>9}  {'pnl%':>7}")
    for y, sub in eq.groupby(eq.index.year):
        if len(sub) < 5:
            continue
        start = sub.iloc[0]
        end = sub.iloc[-1]
        print(f"  {int(y):>5}  ${start:>8.2f}  ${end:>8.2f}  "
              f"${end-start:+8.2f}  {100*(end/start-1):+6.2f}%")

    # =================================================================
    #   SAVE
    # =================================================================
    out = {
        'config': {
            'mode': 'perp futures (long + short)',
            'venue_assumed': 'Binance USDT-perp / Hyperliquid / dYdX',
            'fees_bps_round_trip': 5.0,
            'funding_models': {
                'worst':       'always paying side, both legs charged',
                'neutral':     'pairs=0, trend+macro 50% offset',
                'directional': 'trend uses real position sign, pairs=0',
            },
            'init_capital_usd': 100.0,
        },
        'F5_long_short_split': {
            'eth_up_days_pnl_pct':     float(100 * pnl_up),
            'eth_down_days_pnl_pct':   float(100 * pnl_down),
            'eth_flat_days_pnl_pct':   float(100 * pnl_flat),
            'n_up_days':   n_up,
            'n_down_days': n_dn,
            'n_flat_days': n_fl,
        },
        'F6_funding_total_bps': {
            name: float(1e4 * fs[test_mask].sum())
            for name, fs in fund_scenarios.items()
        },
        'sim_100usd': rows,
        'directional_K2_final_usd':  float(s_real['final']),
        'directional_K2_sharpe_net': float(s_real['sharpe_net']),
        'directional_K2_max_dd':     float(s_real['max_dd']),
    }
    jp = Path(OUT_DIR) / 'crypto_bsdt_v30_long_short_funding_100usd.json'
    jp.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Saved -> {jp}")
    print("=" * 96)


if __name__ == "__main__":
    main()
