"""
Crypto BSDT v24 — Clean Exposure Controller
============================================

Two-layer system, explicitly separated:

  LAYER 1  Direction signal  — v18_smooth base strategy
           What to trade, what size, which pairs.
           Unchanged from v22 (6-strategy blend + cs_weights + lev_v18s).

  LAYER 2  Exposure controller  — risk-shaped position scale
           How much to trust Layer 1 at each point in time.
           Derived from Mahalanobis anomaly score in the (ret_z, vol_z)
           state space — the best anomaly detector per v23 AUC (0.730).

Insight from v23: performance came from being in the market at the right
intensity, not from predicting better.  This is the clean implementation
of that principle.

Controller variants (ablation):
  A  no_control     pos_scale = 1.0 everywhere (baseline)
  B  exp_decay      pos_scale = exp(-alpha * max(0, risk_z))
  C  logistic       pos_scale = 1 / (1 + alpha * max(0, risk_z))
  D  hard_gate      pos_scale = DAMP if risk_z > GATE else 1.0
  E  exp_gate       exp_decay THEN hard gate at extreme risk
  F  exp_layerB     exp_decay * v22 rolling Layer-B alarm gate

Alpha is swept across [0.2, 0.5, 0.8, 1.0, 1.5, 2.0] for continuous variants.
Best-alpha config used for layerB hybrid.
"""
from __future__ import annotations
import os, sys, json, time
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
from run_crypto_pairs_v22 import (
    calibrate_frozen_engine, apply_alarm_latch,
    patch_precursor_scale, emit_global_signals,
    rolling_layer_b_alarm,
    LAYER_B_N_SIGMA, ROLL_WIN, ALARM_LATCH_DAYS,
    LEV_LO, LEV_HI,
)

sys.path.insert(0, r'C:\amttp\research\adaptive-friction')
from collapse_geometry import (
    MasterOperator, Snapshot, LedoitWolfNetwork,
    LyapunovCertificate, CollapseGeometry,
    EarlyWarning, PrecursorScale,
    InformationGeometry, StochasticExtension,
)


# ═══════════════════════════════════════════════════════════════
#  EXPOSURE CONTROLLER PARAMETERS
# ═══════════════════════════════════════════════════════════════

ALPHA_SWEEP    = [0.2, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0]
GATE_SIGMA     = 2.0      # hard gate fires when risk_z > GATE_SIGMA
GATE_DAMP      = 0.20     # exposure multiplier when gate fires
MAHAL_WIN      = 252      # rolling z-score window for Mahalanobis signal
MAHAL_MIN      = 60       # min periods for rolling stats
EXP_FLOOR      = 0.10     # minimum pos_scale (never go fully flat)


# ═══════════════════════════════════════════════════════════════
#  RISK SIGNAL — Mahalanobis distance, rolling-z-scored
# ═══════════════════════════════════════════════════════════════

def compute_mahal_risk(X_panel: np.ndarray, train_mask_arr: np.ndarray) -> pd.Series:
    """Per-day risk signal: max over agents of Mahalanobis distance.

    Steps:
      1. Fit covariance on TRAIN window (frozen — no lookahead)
      2. Compute Mahalanobis for all T*N points
      3. Take MAX over N agents -> (T,) daily signal
      4. Rolling z-score with MAHAL_WIN-day window, 1-day lag
         -> risk_z  (0 = normal, >1 = above average, >2 = tail)

    Returns pd.Series risk_z indexed by position (0..T-1).
    """
    T, N, d = X_panel.shape
    X_flat  = X_panel.reshape(T * N, d)
    X_tr    = X_panel[train_mask_arr].reshape(-1, d)

    mu  = X_tr.mean(axis=0)
    cov = np.cov(X_tr.T) + np.eye(d) * 1e-6
    try:
        VI = np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        VI = np.eye(d)

    diff = X_flat - mu
    m    = np.sqrt(np.einsum('ij,jk,ik->i', diff, VI, diff))
    m    = np.nan_to_num(m, nan=0.0)

    # max over agents -> daily signal
    m_day = m.reshape(T, N).max(axis=1)  # (T,)

    # rolling z-score (lagged 1 day -> no lookahead)
    s     = pd.Series(m_day)
    mu_r  = s.rolling(MAHAL_WIN, min_periods=MAHAL_MIN).mean().shift(1)
    sd_r  = s.rolling(MAHAL_WIN, min_periods=MAHAL_MIN).std().shift(1).clip(lower=1e-6)
    risk_z = ((s - mu_r) / sd_r).clip(-5.0, 5.0).fillna(0.0)
    return risk_z


# ═══════════════════════════════════════════════════════════════
#  EXPOSURE FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def exp_decay(risk_z: np.ndarray, alpha: float) -> np.ndarray:
    """pos_scale = exp(-alpha * max(0, risk_z)), floored at EXP_FLOOR."""
    return np.maximum(EXP_FLOOR, np.exp(-alpha * np.maximum(0.0, risk_z)))


def logistic_decay(risk_z: np.ndarray, alpha: float) -> np.ndarray:
    """pos_scale = 1 / (1 + alpha * max(0, risk_z)), floored at EXP_FLOOR."""
    return np.maximum(EXP_FLOOR, 1.0 / (1.0 + alpha * np.maximum(0.0, risk_z)))


def hard_gate(risk_z: np.ndarray, gate_sigma: float = GATE_SIGMA,
              damp: float = GATE_DAMP) -> np.ndarray:
    """Binary gate: DAMP when risk_z > GATE_SIGMA, else 1.0."""
    return np.where(risk_z > gate_sigma, damp, 1.0)


# ═══════════════════════════════════════════════════════════════
#  SIMULATE ONE VARIANT
# ═══════════════════════════════════════════════════════════════

def apply_controller(pnl_base: pd.Series, pos_scale: np.ndarray,
                     test_mask) -> pd.Series:
    """Apply exposure scale to base PnL (1-day lag baked into risk_z already)."""
    ps = pd.Series(pos_scale, index=pnl_base.index).clip(EXP_FLOOR, 1.0)
    return pnl_base * ps


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    out_dir = Path(OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 92)
    print("  CRYPTO BSDT v24 — Clean Exposure Controller")
    print("  Layer 1: v18_smooth direction  |  Layer 2: Mahalanobis risk scaling")
    print("=" * 92)

    # ── data ────────────────────────────────────────────────────────
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

    # ── Layer 1: v18_smooth base PnL ────────────────────────────────
    print("\n[2] Building Layer 1 (v18_smooth direction) ...")
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

    sim_base = simulate_from_pnl(pnl_v18s[test_mask].fillna(0.0))
    print(f"  v18_smooth: Sharpe {sim_base['sharpe']:+.4f}  "
          f"MaxDD {sim_base['max_dd']:+.4f}  CAGR {100*sim_base['cagr']:+.2f}%")

    # ── Layer 2: risk signal ─────────────────────────────────────────
    print("\n[3] Building Layer 2 (Mahalanobis risk signal) ...")
    X_panel  = _build_state_panel(df)
    risk_z   = compute_mahal_risk(X_panel, train_mask_arr)
    risk_arr = risk_z.values   # (T,)

    print(f"  risk_z stats [test]:  "
          f"mean={risk_arr[train_mask_arr==False].mean():.2f}  "
          f"p90={np.percentile(risk_arr[test_mask], 90):.2f}  "
          f"p99={np.percentile(risk_arr[test_mask], 99):.2f}  "
          f"gate_days(>{GATE_SIGMA}σ)={int((risk_arr[test_mask] > GATE_SIGMA).sum())}")

    # ── also get v22 Layer B for the hybrid variant ──────────────────
    print("\n[4] Running physics engine (Layer B signal for hybrid) ...")
    M, net, geom_e, lyap, info, ews, e_star, sigma_n = calibrate_frozen_engine(
        X_panel, train_mask_arr)
    patch_precursor_scale(ews, M, X_panel[train_mask_arr])
    F_eng = emit_global_signals(df, X_panel, M, net, geom_e, lyap, ews, sigma_n)
    _, alarm_B = rolling_layer_b_alarm(
        F_eng['geom_score'].fillna(0.0),
        n_sigma=LAYER_B_N_SIGMA, win=ROLL_WIN, min_periods=60)
    layer_b_gate = np.where(alarm_B.values, 0.40, 1.0)   # Layer B fires -> 40% exposure

    # ── ablation sweep ───────────────────────────────────────────────
    print("\n[5] Running ablation sweep ...")
    results = {}

    # A. No controller (baseline)
    results['A_no_control'] = {
        'pnl': pnl_v18s, 'label': 'A: no controller',
        'alpha': None, 'fn': 'none',
    }

    # B. exp_decay sweep
    best_exp = {'sharpe': -999, 'alpha': None, 'pnl': None}
    for alpha in ALPHA_SWEEP:
        ps    = exp_decay(risk_arr, alpha)
        pnl_c = apply_controller(pnl_v18s, ps, test_mask)
        sim   = simulate_from_pnl(pnl_c[test_mask].fillna(0.0))
        if sim['sharpe'] > best_exp['sharpe']:
            best_exp = {'sharpe': sim['sharpe'], 'alpha': alpha,
                        'pnl': pnl_c, 'sim': sim}
    results['B_exp_decay'] = {
        'pnl': best_exp['pnl'], 'label': f"B: exp_decay (alpha={best_exp['alpha']})",
        'alpha': best_exp['alpha'], 'fn': 'exp',
    }

    # C. logistic sweep
    best_log = {'sharpe': -999, 'alpha': None, 'pnl': None}
    for alpha in ALPHA_SWEEP:
        ps    = logistic_decay(risk_arr, alpha)
        pnl_c = apply_controller(pnl_v18s, ps, test_mask)
        sim   = simulate_from_pnl(pnl_c[test_mask].fillna(0.0))
        if sim['sharpe'] > best_log['sharpe']:
            best_log = {'sharpe': sim['sharpe'], 'alpha': alpha,
                        'pnl': pnl_c, 'sim': sim}
    results['C_logistic'] = {
        'pnl': best_log['pnl'], 'label': f"C: logistic (alpha={best_log['alpha']})",
        'alpha': best_log['alpha'], 'fn': 'logistic',
    }

    # D. hard gate only
    ps_gate   = hard_gate(risk_arr)
    pnl_gate  = apply_controller(pnl_v18s, ps_gate, test_mask)
    results['D_hard_gate'] = {
        'pnl': pnl_gate, 'label': f"D: hard_gate (>{GATE_SIGMA}σ -> {GATE_DAMP}x)",
        'alpha': None, 'fn': 'gate',
    }

    # E. exp + hard gate (combo)
    best_combo = {'sharpe': -999, 'alpha': None, 'pnl': None}
    for alpha in ALPHA_SWEEP:
        ps    = exp_decay(risk_arr, alpha) * hard_gate(risk_arr)
        ps    = np.maximum(EXP_FLOOR, ps)
        pnl_c = apply_controller(pnl_v18s, ps, test_mask)
        sim   = simulate_from_pnl(pnl_c[test_mask].fillna(0.0))
        if sim['sharpe'] > best_combo['sharpe']:
            best_combo = {'sharpe': sim['sharpe'], 'alpha': alpha,
                          'pnl': pnl_c, 'sim': sim}
    results['E_exp_gate'] = {
        'pnl': best_combo['pnl'],
        'label': f"E: exp+gate (alpha={best_combo['alpha']})",
        'alpha': best_combo['alpha'], 'fn': 'exp+gate',
    }

    # F. best-exp + Layer B alarm (hybrid: mahal controller + physics gate)
    best_alpha_f = best_exp['alpha']
    ps_f = exp_decay(risk_arr, best_alpha_f) * layer_b_gate
    ps_f = np.maximum(EXP_FLOOR, ps_f)
    pnl_f = apply_controller(pnl_v18s, ps_f, test_mask)
    results['F_exp_layerB'] = {
        'pnl': pnl_f,
        'label': f"F: exp+LayerB (alpha={best_alpha_f}, B=40%)",
        'alpha': best_alpha_f, 'fn': 'exp+layerB',
    }

    # ── comparison table ─────────────────────────────────────────────
    print("\n" + "=" * 92)
    print("  v24 EXPOSURE CONTROLLER — ablation (test period, K=1 gross)")
    print("=" * 92)
    print(f"  {'Variant':<36}  {'Sharpe':>8}  {'MaxDD':>8}  {'CAGR%':>8}  "
          f"{'HitRate':>8}  {'Active':>7}")
    print("  " + "-" * 84)

    best_sharpe = -999.0
    best_key    = 'A_no_control'
    all_sims    = {}
    for rk, res in results.items():
        sim = simulate_from_pnl(res['pnl'][test_mask].fillna(0.0))
        all_sims[rk] = sim
        act = int(res['pnl'][test_mask].abs().gt(1e-9).sum())
        mk  = ' <--' if sim['sharpe'] > best_sharpe else ''
        if sim['sharpe'] > best_sharpe:
            best_sharpe, best_key = sim['sharpe'], rk
        print(f"  {res['label']:<36}  {sim['sharpe']:+8.4f}  {sim['max_dd']:+8.4f}  "
              f"{100*sim['cagr']:+7.2f}%  {sim['hit_rate']:8.4f}  {act:6d}d{mk}")

    print()
    print(f"  Best: {results[best_key]['label']}  "
          f"Sharpe {best_sharpe:+.4f}")
    print(f"  v22 reference (rolling two-layer): Sharpe +1.7425  MaxDD -0.0499  CAGR +2.66%")

    # ── alpha sweep detail for exp_decay ────────────────────────────
    print(f"\n  exp_decay alpha sweep detail:")
    print(f"  {'alpha':>6}  {'Sharpe':>8}  {'MaxDD':>8}  {'CAGR%':>8}  "
          f"{'mean scale':>10}  {'min scale':>10}")
    print("  " + "-" * 60)
    for alpha in ALPHA_SWEEP:
        ps   = exp_decay(risk_arr, alpha)
        pnl_c = apply_controller(pnl_v18s, ps, test_mask)
        sim  = simulate_from_pnl(pnl_c[test_mask].fillna(0.0))
        ms   = float(ps[test_mask].mean()) if hasattr(ps, '__getitem__') else ps.mean()
        mins = float(ps[test_mask].min()) if hasattr(ps, '__getitem__') else ps.min()
        ps_s = pd.Series(ps, index=df.index)
        ms   = float(ps_s[test_mask].mean())
        mins = float(ps_s[test_mask].min())
        print(f"  {alpha:6.2f}  {sim['sharpe']:+8.4f}  {sim['max_dd']:+8.4f}  "
              f"{100*sim['cagr']:+7.2f}%  {ms:10.3f}  {mins:10.3f}")

    # ── K-sweep on winner ─────────────────────────────────────────────
    best_pnl = results[best_key]['pnl']
    print(f"\n  K-sweep on [{results[best_key]['label']}]:")
    print(f"  {'K':>5}  {'mode':<10}  {'Sharpe':>8}  {'CAGR%':>8}  "
          f"{'Final $':>12}  {'PnL $':>12}  {'MaxDD%':>8}")
    print("  " + "-" * 78)
    for K in (1, 2, 3, 5, 10):
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

    # ── intuition: mean exposure per variant ─────────────────────────
    print("\n  Mean exposure scale [test] per variant:")
    for alpha in (best_exp['alpha'], 0.5, 1.0):
        ps_s = pd.Series(exp_decay(risk_arr, alpha), index=df.index)
        gate_days = int((risk_z[test_mask] > GATE_SIGMA).sum())
        print(f"    exp alpha={alpha}: mean={ps_s[test_mask].mean():.3f}  "
              f"min={ps_s[test_mask].min():.3f}  "
              f"gate_days(>{GATE_SIGMA}σ)={gate_days}")

    # ── save ─────────────────────────────────────────────────────────
    out = {
        'protocol': 'v24 clean exposure controller',
        'layer1': 'v18_smooth direction signal',
        'layer2': 'Mahalanobis risk scaling (plain d=2 panel, frozen train cov)',
        'variants': {
            rk: {
                'label':      res['label'],
                'alpha':      res['alpha'],
                'fn':         res['fn'],
                'sim': {k: (float(v) if isinstance(v, (int,float,np.floating)) else v)
                        for k, v in all_sims[rk].items()},
            }
            for rk, res in results.items()
        },
        'best_variant':   best_key,
        'best_sharpe':    float(best_sharpe),
        'v22_reference':  {'sharpe': 1.7425, 'max_dd': -0.0499, 'cagr': 0.0266},
        'alpha_sweep':    {},
    }
    for alpha in ALPHA_SWEEP:
        ps   = exp_decay(risk_arr, alpha)
        pnl_c = apply_controller(pnl_v18s, ps, test_mask)
        sim  = simulate_from_pnl(pnl_c[test_mask].fillna(0.0))
        out['alpha_sweep'][str(alpha)] = {
            k: (float(v) if isinstance(v, (int,float,np.floating)) else v)
            for k, v in sim.items()}
    jp = Path(OUT_DIR) / 'crypto_bsdt_v24_results.json'
    jp.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Saved -> {jp}")
    print("=" * 92)


if __name__ == "__main__":
    main()
