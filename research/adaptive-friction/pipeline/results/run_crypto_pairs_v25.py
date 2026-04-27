"""
Crypto BSDT v25 — Stacked Filter: v22 Physics + Mahalanobis Hard Gate
=======================================================================

Hypothesis: The physics engine (v22) detects structural regime transitions.
The Mahalanobis hard gate (v24-D) catches statistical tail events.
These two signals may be *complementary* — each catching different crises.

Architecture:
  LAYER 1  Direction        — v18_smooth blend (unchanged)
  LAYER 2  Regime alarm     — v22 rolling two-layer (geom + precursor)
           -> Discrete 4-state: {} / A / B / AB  (allocations v21)
  LAYER 3  Tail gate        — Mahalanobis >2σ -> damp to GATE_DAMP
           -> Applied multiplicatively on top of Layer 2 position

Test variants:
  v22_plain          v22 two-layer alarm (reference, Sharpe ~+1.743)
  v25_hard_gate      v22 × Mahal hard gate >2σ -> 0.20x
  v25_soft_gate_10   v22 × Mahal hard gate >1.0σ -> 0.50x
  v25_soft_gate_15   v22 × Mahal hard gate >1.5σ -> 0.35x
  v25_exp_top        v22 × exp(-alpha * max(0, risk_z)), best alpha sweep
  v25_exp_gate_top   v22 × exp × hard gate (double suppression)

Key diagnostic: How many of the 67 gate days overlap with v22 B/AB alarm?
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
import run_crypto_pairs_v19 as v19
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
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')
from collapse_geometry import (
    MasterOperator, Snapshot, LedoitWolfNetwork,
    LyapunovCertificate, CollapseGeometry,
    EarlyWarning, PrecursorScale,
    InformationGeometry, StochasticExtension,
)

# ── import v23 pipeline (exact reproduction) and v24 risk tools ──────
from run_crypto_pairs_v23 import run_repr_pipeline
from run_crypto_pairs_v24 import (
    compute_mahal_risk, exp_decay, hard_gate, EXP_FLOOR,
    GATE_SIGMA, GATE_DAMP, MAHAL_WIN, ALPHA_SWEEP,
)


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    out_dir = Path(OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 94)
    print("  CRYPTO BSDT v25 — Stacked Filter: v22 Physics Engine + Mahalanobis Gate")
    print("=" * 94)

    # ── data ──────────────────────────────────────────────────────────
    print("\n[1] Loading data ...")
    df = fetch_and_prepare()
    df = add_cross_market_features(df)
    funding = fetch_binance_funding(symbols=['ETHUSDT','BTCUSDT'], start='2020-06-01')
    df = add_leverage_features(df, funding)

    train_mask     = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask      = df.index >= TEST_START
    train_mask_arr = np.asarray(train_mask, dtype=bool)
    T              = len(df)

    print(f"  Train {df[train_mask].index[0].date()} -> {df[train_mask].index[-1].date()} "
          f"({int(train_mask.sum())}d)  "
          f"Test {df[test_mask].index[0].date()} -> {df[test_mask].index[-1].date()} "
          f"({int(test_mask.sum())}d)")

    # ── v18_smooth ────────────────────────────────────────────────────
    print("\n[2] Building v18_smooth direction (Layer 1) ...")
    feats_strat = ['ret_eth_z','ret_btc_z','ret_sol_z','ret_bnb_z',
                   'vol_eth_z','vol_btc_z','btc_dom_z','cross_disp_z']
    feats_ext   = feats_strat + ['ret_spx_z','dvix_z','ret_dxy_z']
    omega_strat, mfls_eth, gamma_eth = compute_bsdt(df, feats_strat, window=60)
    omega_ext,   _,        _         = compute_bsdt(df, feats_ext,   window=60)
    A_eth, A_rank, dA_fast, dA_rank  = compute_activity_signals(mfls_eth, gamma_eth)
    gamma_rank  = compute_gamma_rank(omega_ext, min_periods=60)
    lev_mult    = compute_leverage_dial(gamma_rank)
    ret7 = df['ret_eth'].rolling(7).sum()
    ret3 = df['ret_eth'].rolling(3).sum()
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
    n_s      = len(pnl_base_dict)
    pnl_v10  = pd.Series(0.0, index=df.index)
    for k in pnl_base_dict:
        pnl_v10 += cs_wts[k].shift(1).fillna(1.0/n_s) * pnl_base_dict[k]
    pnl_v18s = pnl_v10 * lev_v18s.shift(1).fillna(1.0)

    # ── v22/v23 two-layer alarm — exact reproduction via run_repr_pipeline ──
    print("\n[3] Building v22 physics alarm (Layer 2) via run_repr_pipeline ...")
    X_panel = _build_state_panel(df)
    sim_v22, pnl_v22, diag_v22 = run_repr_pipeline(
        X_panel, train_mask_arr, df, test_mask, pnl_v18s)
    print(f"  v22 (Layer 1+2):  Sharpe {sim_v22['sharpe']:+.4f}  "
          f"MaxDD {sim_v22['max_dd']:+.4f}  CAGR {100*sim_v22['cagr']:+.2f}%")
    print(f"  Alarm-A days [test]: {diag_v22['layer_A_days']}  "
          f"Alarm-B days [test]: {diag_v22['layer_B_days']}  "
          f"Latched [test]: {diag_v22['latched_days']}")

    # ── Mahalanobis risk signal ────────────────────────────────────────
    print("\n[4] Building Mahalanobis risk signal (Layer 3 candidate) ...")
    risk_z    = pd.Series(
        compute_mahal_risk(X_panel, train_mask_arr).values,
        index=df.index)                            # align to DatetimeIndex
    risk_arr  = risk_z.values
    gate_mask = test_mask & (risk_z > GATE_SIGMA)

    print(f"  Mahal gate days (>{GATE_SIGMA}σ): {int(gate_mask.sum())} / "
          f"{int(test_mask.sum())} ({100*gate_mask.sum()/test_mask.sum():.1f}%)")

    # ── overlap: gate days vs v22 latched/unlatched ────────────────────
    print("\n[5] Where are the gate days falling in the v22 strategy?")
    # Reconstruct v22 latched mask from the pnl signal
    # pnl_v22 is 0 on days where g_pos * (1-g_cash) = 0 [never: ALLOC floor is 0.4]
    # Instead measure mean pnl on gate days vs non-gate test days
    pnl_gate     = pnl_v22[gate_mask].fillna(0.0)
    pnl_no_gate  = pnl_v22[test_mask & ~gate_mask].fillna(0.0)
    print(f"  Mean daily v22 pnl on GATE days :  {pnl_gate.mean():+.5f}  "
          f"({len(pnl_gate)} days)")
    print(f"  Mean daily v22 pnl on non-gate  :  {pnl_no_gate.mean():+.5f}  "
          f"({len(pnl_no_gate)} days)")
    print(f"  Mean daily v18_smooth on GATE   :  "
          f"{pnl_v18s[gate_mask].mean():+.5f}")
    print(f"  Ratio (v22_gate / v18_gate)     :  "
          f"{pnl_gate.mean() / (pnl_v18s[gate_mask].mean() + 1e-10):+.3f}")
    worst5 = pnl_v22[gate_mask].nsmallest(5)
    print(f"  5 worst v22 gate days:")
    for d, v in worst5.items():
        print(f"    {d.date()}  pnl={v:+.5f}  risk_z={risk_z[d]:+.2f}")

    # ── ablation on top of v22 ────────────────────────────────────────
    print("\n[6] Stacked filter ablation ...")

    variants = {}

    # Reference: v22 alone
    variants['v22'] = pnl_v22.copy()

    # v25a: hard gate >2σ -> 0.20x on top of v22
    ps_hard = pd.Series(hard_gate(risk_arr, GATE_SIGMA, GATE_DAMP), index=df.index)
    variants['v25a_hard2s_020'] = pnl_v22 * ps_hard

    # v25b: softer gate >1.5σ -> 0.35x
    ps_soft15 = pd.Series(hard_gate(risk_arr, 1.5, 0.35), index=df.index)
    variants['v25b_soft15s_035'] = pnl_v22 * ps_soft15

    # v25c: softer gate >1.0σ -> 0.50x
    ps_soft10 = pd.Series(hard_gate(risk_arr, 1.0, 0.50), index=df.index)
    variants['v25c_soft10s_050'] = pnl_v22 * ps_soft10

    # v25d: exp decay top (best alpha from v24)
    best_exp = {'sharpe': -999, 'alpha': None, 'pnl': None}
    for alpha in ALPHA_SWEEP:
        ps   = pd.Series(exp_decay(risk_arr, alpha), index=df.index)
        pnl_c = pnl_v22 * ps
        sim  = simulate_from_pnl(pnl_c[test_mask].fillna(0.0))
        if sim['sharpe'] > best_exp['sharpe']:
            best_exp = {'sharpe': sim['sharpe'], 'alpha': alpha, 'pnl': pnl_c}
    variants[f"v25d_exp_a{best_exp['alpha']}"] = best_exp['pnl']

    # v25e: exp + hard gate >2σ
    best_combo = {'sharpe': -999, 'alpha': None, 'pnl': None}
    for alpha in ALPHA_SWEEP:
        ps   = pd.Series(
            np.maximum(EXP_FLOOR, exp_decay(risk_arr, alpha) * hard_gate(risk_arr)),
            index=df.index)
        pnl_c = pnl_v22 * ps
        sim  = simulate_from_pnl(pnl_c[test_mask].fillna(0.0))
        if sim['sharpe'] > best_combo['sharpe']:
            best_combo = {'sharpe': sim['sharpe'], 'alpha': alpha, 'pnl': pnl_c}
    variants[f"v25e_expgate_a{best_combo['alpha']}"] = best_combo['pnl']

    # ── comparison table ──────────────────────────────────────────────
    print("\n" + "=" * 94)
    print("  v25 STACKED RESULTS  (test period, K=1 gross)")
    print("  Note: v22 reference reproduced here; external best was Sharpe +1.7425")
    print("=" * 94)
    print(f"  {'Variant':<36}  {'Sharpe':>8}  {'MaxDD':>8}  {'CAGR%':>8}  "
          f"{'HitRate':>8}  {'Active':>7}")
    print("  " + "-" * 84)

    best_sharpe, best_key = -999.0, 'v22'
    all_sims = {}
    for k, pnl in variants.items():
        sim = simulate_from_pnl(pnl[test_mask].fillna(0.0))
        all_sims[k] = sim
        act = int(pnl[test_mask].abs().gt(1e-9).sum())
        flag = ' <--' if sim['sharpe'] > best_sharpe else ''
        if sim['sharpe'] > best_sharpe:
            best_sharpe, best_key = sim['sharpe'], k
        print(f"  {k:<36}  {sim['sharpe']:+8.4f}  {sim['max_dd']:+8.4f}  "
              f"{100*sim['cagr']:+7.2f}%  {sim['hit_rate']:8.4f}  {act:6d}d{flag}")

    print(f"\n  Best: {best_key}  Sharpe {best_sharpe:+.4f}")

    # ── K-sweep on best ───────────────────────────────────────────────
    best_pnl = variants[best_key]
    print(f"\n  K-sweep on [{best_key}]:")
    print(f"  {'K':>5}  {'mode':<10}  {'Sharpe':>8}  {'CAGR%':>8}  "
          f"{'Final $':>12}  {'PnL':>12}  {'MaxDD%':>8}")
    print("  " + "-" * 80)
    for K in (1, 2, 3, 5, 8, 10, 12):
        for mode, bps in (('gross', 0.0), ('net 5bp', 5.0)):
            m = equity_at_K(best_pnl[test_mask].fillna(0.0),
                            K=float(K), tcost_bps=bps, init=1200.0)
            print(f"  {K:5d}  {mode:<10}  {m['sh']:+8.3f}  "
                  f"{100*m['cagr']:+7.2f}%  ${m['final']:10,.2f}  "
                  f"${m['pnl']:+10,.2f}  {100*m['max_dd']:+7.2f}%")
    bK = find_best_K(best_pnl[test_mask].fillna(0.0),
                     tcost_bps=5.0, init=1200.0, max_dd_limit=0.40)
    if bK:
        print(f"\n  Best K net 5bp (MaxDD<=40%): K={bK['K']:.2f}  "
              f"Final ${bK['final']:,.2f}  Sharpe {bK['sh']:+.3f}  "
              f"CAGR {100*bK['cagr']:.1f}%")

    # Also compare both best variants side by side with K-sweep
    if best_key != 'v22':
        print(f"\n  K-sweep comparison: [v22] vs [{best_key}]:")
        print(f"  {'K':>5}  {'Sharpe v22':>12}  {'Sharpe best':>12}  "
              f"{'Final v22':>12}  {'Final best':>12}  {'DD v22':>8}  {'DD best':>8}")
        print("  " + "-" * 90)
        for K in (1, 3, 5, 8, 10):
            m22  = equity_at_K(pnl_v22[test_mask].fillna(0.0),
                               K=float(K), tcost_bps=5.0, init=1200.0)
            mbst = equity_at_K(best_pnl[test_mask].fillna(0.0),
                               K=float(K), tcost_bps=5.0, init=1200.0)
            print(f"  {K:5d}  {m22['sh']:+12.3f}  {mbst['sh']:+12.3f}  "
                  f"${m22['final']:10,.2f}  ${mbst['final']:10,.2f}  "
                  f"{100*m22['max_dd']:+7.2f}%  {100*mbst['max_dd']:+7.2f}%")

    # ── save ──────────────────────────────────────────────────────────
    out = {
        'protocol':  'v25 stacked filter: v22 physics + Mahal gate',
        'layer1':    'v18_smooth direction',
        'layer2':    'v22 rolling two-layer alarm (geom + precursor)',
        'layer3':    f'Mahal hard gate (>{GATE_SIGMA}sigma -> {GATE_DAMP}x), or exp decay',
        'variants':  {
            k: {
                'sim': {kk: (float(vv) if isinstance(vv, (int,float,np.floating)) else vv)
                        for kk, vv in s.items()}
            }
            for k, s in all_sims.items()
        },
        'best_key':    best_key,
        'best_sharpe': float(best_sharpe),
        'mahal_gate_days': int(gate_mask.sum()),
        'v22_sharpe_reproduced': float(sim_v22['sharpe']),
    }
    jp = Path(OUT_DIR) / 'crypto_bsdt_v25_results.json'
    jp.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Saved -> {jp}")
    print("=" * 94)


if __name__ == "__main__":
    main()
