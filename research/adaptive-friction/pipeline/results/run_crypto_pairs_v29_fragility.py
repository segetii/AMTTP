"""
Crypto BSDT v29 - FRAGILITY TESTING FRAMEWORK
==============================================

Goal: try to BREAK v28_full_no_brk on purpose.

Tests:
  [F1] Noise robustness
       - randomly drop 10% / 20% of active trade days
       - perturb engine signals F by N(0, sigma) noise, sigma in {0.05, 0.10, 0.20}
       - perturb strategy returns by mult noise (1 + N(0, sigma))
       - 50 seeds each, report median / [p5, p95]
       PASS if median Sharpe > 1.8 and p5 > 1.5

  [F2] Signal delay (lookahead test)
       - additional lag of 1, 2, 3 days on engine F + Q
       PASS if Sharpe > 1.8 at lag=1, > 1.5 at lag=2

  [F3] Cross-asset transfer
       - replace trend strategy's underlying return ret_eth -> ret_btc
       - same engine, same allocator, same book structure
       PASS if Sharpe > 1.0 (structural edge)
       FAIL means crypto/ETH-specific artifact

  [F4] Gate dependency reduction (blend gated + always-on)
       - eff_blended = alpha * eff_gated + (1-alpha) * eff_always_on
       - alpha in {1.0, 0.9, 0.8, 0.7, 0.5, 0.0}
       Goal: find blend that trades volatility-of-Sharpe-at-different-alpha

Inputs identical to v28; allocator config locked at production default
  (vol_win=60, sharpe_win=120, sharpe_k=2.0, G_LO=0.50, K_LO=0.30).
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
    simulate_from_pnl,
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
#   STRATEGY BUILDER (factored from v28)
# =====================================================================

def build_strategy_book(df: pd.DataFrame, train_mask, train_mask_arr,
                       trend_underlying: str = 'eth') -> tuple[dict, pd.Series, pd.DataFrame]:
    """Returns (strats_dict, lev_unused, F_engine_panel)."""
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
    trend_ret_col = {'eth': 'ret_eth', 'btc': 'ret_btc', 'sol': 'ret_sol'}[trend_underlying]
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
        'A_directional': get_daily_pnl(pos_A_dir, df[trend_ret_col]),
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

    return strats, lev_v18s, F


# =====================================================================
#   STRESS HELPERS
# =====================================================================

def run_v28(strats, F, test_mask, *, g_lo=0.50, k_lo=0.30,
            sharpe_k=2.0, vol_win=60, sharpe_win=120, lag_extra=0,
            use_activation=True) -> tuple[float, float, int]:
    """Single-shot v28 run with optional extra lag. Returns (sharpe, max_dd, active)."""
    Q = compute_quality_risk_weights(strats, vol_win=vol_win, sharpe_win=sharpe_win,
                                      sharpe_k=sharpe_k, target_vol=0.01,
                                      scale_cap=5.0)
    W = compute_unsigned_weights(F, use_activation=use_activation,
                                  g_lo=g_lo, k_lo=k_lo)
    if lag_extra > 0:
        Q = Q.shift(lag_extra).fillna(0.0)
        W = W.shift(lag_extra).fillna(0.0)
    flat = pd.Series(1.0, index=F.index)
    p = build_v28_pnl(strats, W, Q, flat, F.index)
    s = simulate_from_pnl(p[test_mask].fillna(0.0))
    act = int(p[test_mask].abs().gt(1e-9).sum())
    return s['sharpe'], s['max_dd'], act


def _drop_mask(active_idx: pd.DatetimeIndex, frac: float, rng) -> set:
    n = len(active_idx)
    k = int(round(n * frac))
    if k <= 0:
        return set()
    drop = rng.choice(n, size=k, replace=False)
    return set(active_idx[drop])


# =====================================================================
#   MAIN
# =====================================================================

def main():
    out_dir = Path(OUT_DIR); out_dir.mkdir(parents=True, exist_ok=True)
    print("=" * 96)
    print("  v29 FRAGILITY TESTING FRAMEWORK - try to break v28_full_no_brk")
    print("=" * 96)

    print("\n[1] Loading data + building strategies (ETH trend) ...")
    df = fetch_and_prepare()
    df = add_cross_market_features(df)
    funding = fetch_binance_funding(symbols=['ETHUSDT','BTCUSDT'], start='2020-06-01')
    df = add_leverage_features(df, funding)
    train_mask     = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask      = df.index >= TEST_START
    train_mask_arr = np.asarray(train_mask, dtype=bool)

    strats_eth, _, F = build_strategy_book(df, train_mask, train_mask_arr,
                                             trend_underlying='eth')

    # Production reference
    sh_ref, dd_ref, act_ref = run_v28(strats_eth, F, test_mask)
    print(f"\n  REFERENCE (v28_full_no_brk): Sharpe={sh_ref:+.3f}  "
          f"DD={100*dd_ref:+.2f}%  active={act_ref}d")

    # =================================================================
    #   [F1] NOISE ROBUSTNESS
    # =================================================================
    print("\n" + "=" * 96)
    print("  [F1] NOISE ROBUSTNESS  (50 seeds; median [p5, p95])")
    print("=" * 96)

    N_SEEDS = 50
    Q_base = compute_quality_risk_weights(strats_eth)
    W_base = compute_unsigned_weights(F, use_activation=True, g_lo=0.50, k_lo=0.30)
    flat = pd.Series(1.0, index=F.index)
    pnl_ref = build_v28_pnl(strats_eth, W_base, Q_base, flat, F.index)
    active_idx = pnl_ref[(pnl_ref.abs() > 1e-9) & test_mask].index

    def sharpe_with_drop(frac, seed):
        rng = np.random.default_rng(seed)
        drops = _drop_mask(active_idx, frac, rng)
        p = pnl_ref.copy()
        p.loc[list(drops)] = 0.0
        return simulate_from_pnl(p[test_mask].fillna(0.0))['sharpe']

    print("\n  (a) Random trade dropout (set PnL=0 on chosen days)")
    print(f"    {'frac_drop':>10}  {'p5':>7}  {'med':>7}  {'p95':>7}")
    f1a_results = []
    for frac in (0.10, 0.20, 0.30):
        sh = np.array([sharpe_with_drop(frac, s) for s in range(N_SEEDS)])
        p5, med, p95 = np.percentile(sh, [5, 50, 95])
        f1a_results.append({'frac': frac, 'p5': float(p5), 'median': float(med), 'p95': float(p95)})
        print(f"    {frac:>10.2%}  {p5:+7.3f}  {med:+7.3f}  {p95:+7.3f}")

    print("\n  (b) Engine signal noise: F += N(0, sigma); recompute W")
    print(f"    {'sigma':>8}  {'p5':>7}  {'med':>7}  {'p95':>7}")
    f1b_results = []
    for sigma in (0.05, 0.10, 0.20):
        shs = []
        for s in range(N_SEEDS):
            rng = np.random.default_rng(1000 + s)
            F_n = F.copy()
            for c in F_n.columns:
                F_n[c] = F_n[c] + rng.normal(0.0, sigma * F_n[c].std(), len(F_n))
            sh, _, _ = run_v28(strats_eth, F_n, test_mask)
            shs.append(sh)
        p5, med, p95 = np.percentile(shs, [5, 50, 95])
        f1b_results.append({'sigma': sigma, 'p5': float(p5), 'median': float(med), 'p95': float(p95)})
        print(f"    {sigma:>8.2f}  {p5:+7.3f}  {med:+7.3f}  {p95:+7.3f}")

    print("\n  (c) Strategy return noise: pnl *= (1 + N(0, sigma))")
    print(f"    {'sigma':>8}  {'p5':>7}  {'med':>7}  {'p95':>7}")
    f1c_results = []
    for sigma in (0.05, 0.10, 0.20):
        shs = []
        for s in range(N_SEEDS):
            rng = np.random.default_rng(2000 + s)
            strats_n = {k: v * (1 + rng.normal(0.0, sigma, len(v))) for k, v in strats_eth.items()}
            sh, _, _ = run_v28(strats_n, F, test_mask)
            shs.append(sh)
        p5, med, p95 = np.percentile(shs, [5, 50, 95])
        f1c_results.append({'sigma': sigma, 'p5': float(p5), 'median': float(med), 'p95': float(p95)})
        print(f"    {sigma:>8.2f}  {p5:+7.3f}  {med:+7.3f}  {p95:+7.3f}")

    # =================================================================
    #   [F2] SIGNAL DELAY (lookahead test)
    # =================================================================
    print("\n" + "=" * 96)
    print("  [F2] SIGNAL DELAY  (additional lag on F and Q)")
    print("=" * 96)
    print(f"\n    {'extra_lag':>10}  {'sharpe':>8}  {'maxdd%':>8}  {'active':>7}")
    f2_results = []
    for lag in (0, 1, 2, 3, 5):
        sh, dd, act = run_v28(strats_eth, F, test_mask, lag_extra=lag)
        f2_results.append({'lag': lag, 'sharpe': float(sh), 'max_dd': float(dd), 'active': act})
        print(f"    {lag:>10}  {sh:+8.3f}  {100*dd:+7.2f}%  {act:>6}d")
    print("\n  PASS if Sharpe at lag=1 > 1.8 and lag=2 > 1.5  (no lookahead)")

    # =================================================================
    #   [F3] CROSS-ASSET TRANSFER
    # =================================================================
    print("\n" + "=" * 96)
    print("  [F3] CROSS-ASSET TRANSFER  (swap trend underlying ret_eth -> X)")
    print("=" * 96)
    print(f"\n    {'underlying':<10}  {'sharpe':>8}  {'maxdd%':>8}  {'cagr%':>7}  {'active':>7}")
    f3_results = []
    for under in ('eth', 'btc', 'sol'):
        strats_x, _, F_x = build_strategy_book(df, train_mask, train_mask_arr,
                                                 trend_underlying=under)
        sh, dd, act = run_v28(strats_x, F_x, test_mask)
        # Get cagr too
        Q = compute_quality_risk_weights(strats_x)
        W = compute_unsigned_weights(F_x)
        p = build_v28_pnl(strats_x, W, Q, flat, F_x.index)
        s = simulate_from_pnl(p[test_mask].fillna(0.0))
        f3_results.append({'underlying': under, 'sharpe': float(sh),
                           'max_dd': float(dd), 'cagr': float(s['cagr']), 'active': act})
        print(f"    {under:<10}  {sh:+8.3f}  {100*dd:+7.2f}%  {100*s['cagr']:+6.2f}%  {act:>6}d")
    print("\n  PASS if BTC and SOL Sharpe > 1.0  (structural edge, not ETH artifact)")

    # =================================================================
    #   [F4] GATE DEPENDENCY REDUCTION (blend at PnL level)
    # =================================================================
    print("\n" + "=" * 96)
    print("  [F4] GATE BLEND  (pnl = alpha * gated_pnl + (1-alpha) * always_on_pnl)")
    print("=" * 96)
    print(f"\n    {'alpha':>6}  {'sharpe':>8}  {'maxdd%':>8}  {'cagr%':>7}  {'active':>7}")
    Q_blend = compute_quality_risk_weights(strats_eth)
    W_gated = compute_unsigned_weights(F, use_activation=True, g_lo=0.50, k_lo=0.30)
    W_open  = compute_unsigned_weights(F, use_activation=False)
    pnl_gated = build_v28_pnl(strats_eth, W_gated, Q_blend, flat, F.index)
    pnl_open  = build_v28_pnl(strats_eth, W_open,  Q_blend, flat, F.index)

    f4_results = []
    for alpha in (1.0, 0.9, 0.8, 0.7, 0.5, 0.2, 0.0):
        p = alpha * pnl_gated + (1 - alpha) * pnl_open
        s = simulate_from_pnl(p[test_mask].fillna(0.0))
        act = int(p[test_mask].abs().gt(1e-9).sum())
        f4_results.append({'alpha': alpha, 'sharpe': float(s['sharpe']),
                           'max_dd': float(s['max_dd']), 'cagr': float(s['cagr']),
                           'active': act})
        print(f"    {alpha:>6.2f}  {s['sharpe']:+8.3f}  {100*s['max_dd']:+7.2f}%  "
              f"{100*s['cagr']:+6.2f}%  {act:>6}d")
    print("\n  Insight: trade Sharpe for activity. Robust deployment may want alpha~0.7-0.8.")

    # =================================================================
    #   VERDICT
    # =================================================================
    print("\n" + "=" * 96)
    print("  FRAGILITY VERDICT")
    print("=" * 96)

    f1a_med_20 = next(r['median'] for r in f1a_results if r['frac'] == 0.20)
    f1a_p5_20  = next(r['p5']     for r in f1a_results if r['frac'] == 0.20)
    f1b_med_10 = next(r['median'] for r in f1b_results if r['sigma'] == 0.10)
    f1c_med_10 = next(r['median'] for r in f1c_results if r['sigma'] == 0.10)
    f2_l1      = next(r['sharpe'] for r in f2_results  if r['lag'] == 1)
    f2_l2      = next(r['sharpe'] for r in f2_results  if r['lag'] == 2)
    f3_btc     = next(r['sharpe'] for r in f3_results  if r['underlying'] == 'btc')
    f3_sol     = next(r['sharpe'] for r in f3_results  if r['underlying'] == 'sol')

    def verdict(cond, label):
        return f"  [{'PASS' if cond else 'FAIL'}]  {label}"

    print(f"\n  Reference Sharpe = {sh_ref:+.3f}\n")
    print(verdict(f1a_med_20 > 1.8 and f1a_p5_20 > 1.5,
                  f"F1a 20% trade dropout: median={f1a_med_20:+.3f}, p5={f1a_p5_20:+.3f}  "
                  f"(needs med>1.8, p5>1.5)"))
    print(verdict(f1b_med_10 > 1.8,
                  f"F1b engine noise sigma=0.10: median={f1b_med_10:+.3f}  (needs >1.8)"))
    print(verdict(f1c_med_10 > 1.8,
                  f"F1c return noise sigma=0.10: median={f1c_med_10:+.3f}  (needs >1.8)"))
    print(verdict(f2_l1 > 1.8 and f2_l2 > 1.5,
                  f"F2  lag=1 Sharpe={f2_l1:+.3f}, lag=2 Sharpe={f2_l2:+.3f}  "
                  f"(needs lag1>1.8, lag2>1.5)"))
    print(verdict(f3_btc > 1.0 and f3_sol > 1.0,
                  f"F3  BTC Sharpe={f3_btc:+.3f}, SOL Sharpe={f3_sol:+.3f}  "
                  f"(needs both >1.0)"))

    out = {
        'reference_sharpe':      float(sh_ref),
        'reference_max_dd':      float(dd_ref),
        'reference_active':      int(act_ref),
        'F1a_trade_dropout':     f1a_results,
        'F1b_engine_noise':      f1b_results,
        'F1c_return_noise':      f1c_results,
        'F2_signal_delay':       f2_results,
        'F3_cross_asset':        f3_results,
        'F4_gate_blend':         f4_results,
    }
    jp = Path(OUT_DIR) / 'crypto_bsdt_v29_fragility.json'
    jp.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Saved -> {jp}")
    print("=" * 96)


if __name__ == "__main__":
    main()
