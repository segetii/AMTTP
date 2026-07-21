"""
Crypto BSDT v40 — Phase-Transition Model (G → A with Memory)
=============================================================
Core insight from v39d: G and A are STRUCTURALLY ANTI-CORRELATED at t=0.

    When a_A > 0.70:  mean(a_G) = 0.034  vs full-period mean 0.387
    → G is suppressed by 10× at the moment A fires

This invalidates ALL simultaneous G×A tests (v39c, v39d).  Those tests were
correct in methodology but wrong in framing — they treated channels as
concurrent factors when they are sequential phases.

CORRECT MODEL (phase-transition):
    G = slow structural deformation   → PRECURSOR   (fires early, Δτ(G→C) median=4 bars)
    A = fast kinetic release          → EVENT        (fires at the event, Δτ(A→C) median=0)

The signal is NOT: "is G high NOW when A fires?" (always false)
The signal IS:     "was G high RECENTLY before A fires?" (testable with memory)

FIX: Replace simultaneous condition with temporal lookback:
    G_recent[t] = max(a_G[t-N], …, a_G[t-1])   (rolling max, N bars)

Then A-fire events split into:
    struct_release: (a_A > 0.70) & (G_recent > 0.50)  → GOOD A (built-up stress released)
    rand_cascade:   (a_A > 0.70) & (G_recent ≤ 0.50)  → BAD A  (random volatility shock)

STRATEGIES:
  Phase sweep (N = 4, 8, 12, 20):
    v40_phase_N{N}      : champion + phase_scl (struct boost + rand kill)
  Ablation within N=8:
    v40_structOnly_N8   : only boost struct_release (no rand kill)
    v40_randOnly_N8     : only kill rand_cascade (no struct boost)
    v40_softPhase_N8    : softer coefficients (+0.10 boost, -0.20 kill)
    v40_hardPhase_N8    : harder coefficients (+0.30 boost, -0.60 kill)
  Champion baselines reproduced for direct comparison.

Diagnostic output shows:
  - Fraction of A-fire bars preceded by G spike per window N        ← hypothesis test
  - G_recent distribution at A-fire bars per window
  - Phase activation rates (struct vs rand per N)

Champion baseline: v39b_aG_boost  +2.762
Template:          v39_seq18 (same rolling-lookback-on-fire logic, different channel)
"""
from __future__ import annotations
import os, sys, json, time, warnings
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
from pathlib import Path
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

from collapse_geometry import MasterOperator, Snapshot
from run_crypto_pairs_v38_lambda_norm import compute_lambda_features
from run_crypto_pairs_v37_price_prediction import compute_price_prediction_signals
from run_crypto_pairs_v36_intraday_bsdt import (
    N_AGENTS, N_FEATURES, CALIB_BARS,
    BPD, ANN_1H,
    build_intraday_state_panel, calibrate_intraday_engine,
    compute_intraday_signals,
    _net_ret, _stats,
)
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
    build_1h_df, fetch_and_prepare, fetch_binance_funding,
    add_cross_market_features, add_leverage_features,
    build_daily_positions, upsample_daily_to_1h_pnl,
    compute_1h_strategies, compute_quality, assemble_combined,
)
from run_crypto_pairs_v39_four_channels import (
    CH_C, CH_G, CH_A, CH_T, CH_NAMES,
    FIRE_PERCENTILE,
    calibrate_firing_thresholds,
    print_transmission_lag_analysis,
    print_summary_table, _yoy_table,
)
from run_crypto_pairs_v39b_k1_scaled import (
    PCA_K_B, MU_FLOOR,
    calibrate_channel_means,
    compute_four_channel_signals_v39b,
)

OUT_DIR_ = Path(OUT_DIR)

# ── Thresholds ────────────────────────────────────────────────────────────────
A_FIRE_THRESH    = 0.70    # a_A threshold (same across all v39/v40 variants)
G_MEM_THRESH     = 0.50    # G_recent must exceed this to flag "structural precursor"
G_BOOST_THRESH   = 0.50    # v39b champion: a_G > 0.50 threshold (unchanged)
CHAMPION_BOOST   = 0.50    # v39b champion: size × (1 + 0.50 * (a_G > 0.50))

# Phase sizing coefficients (default / ablation sweep below)
STRUCT_BOOST_DEF = 0.20    # GOOD A: size × (1 + STRUCT_BOOST)
RAND_KILL_DEF    = 0.40    # BAD A:  size × (1 - RAND_KILL)

# Lookback windows (hours)
LOOKBACK_WINDOWS = [4, 8, 12, 20]
BEST_N           = 8       # used for ablation variants


# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE-TRANSITION DIAGNOSTIC
# ═══════════════════════════════════════════════════════════════════════════════

def print_phase_transition_stats(sig_4ch: pd.DataFrame, test_mask) -> dict:
    """
    Print the key diagnostic: for each lookback window N, what fraction of
    A-fire bars were preceded by G > G_MEM_THRESH within the previous N bars?

    If struct_release_rate < 5% for ALL N → phase transition is rare in this
    data and the model hypothesis does not hold here.

    If struct_release_rate > 20% for some N → meaningful signal to capture.
    """
    s    = sig_4ch[test_mask]
    aG   = s['a_G']
    aA   = s['a_A']
    N    = len(s)

    A_fire = (aA > A_FIRE_THRESH)
    n_Afire = int(A_fire.sum())

    print(f"\n  Phase-Transition Diagnostic  (test {N:,} bars)")
    print(f"  A-fire bars (a_A > {A_FIRE_THRESH:.2f}): {n_Afire} ({n_Afire/N*100:.2f}%)")
    print(f"  Global a_G: mean={float(aG.mean()):.3f}  p50={float(aG.median()):.3f}")
    print(f"  a_G when A fires (simultaneous, t=0):")
    if n_Afire > 0:
        aG_at_A = aG[A_fire]
        print(f"    mean={float(aG_at_A.mean()):.4f}  p50={float(aG_at_A.median()):.4f}  "
              f"p75={float(aG_at_A.quantile(0.75)):.4f}  p90={float(aG_at_A.quantile(0.90)):.4f}")
        print(f"    Fraction G > {G_MEM_THRESH:.2f} at A-fire (simultaneous): "
              f"{float((aG_at_A > G_MEM_THRESH).mean())*100:.2f}%  "
              f"(n={(aG_at_A > G_MEM_THRESH).sum()})")

    print(f"\n  G_recent = rolling_max(a_G, N).shift(1)  — N bars before A fires")
    print(f"  {'N':>4}  {'struct_release':>16}  {'rand_cascade':>14}  "
          f"{'G_recent p50':>14}  {'G_recent p90':>14}  {'% of A-fire is struct':>22}")
    print(f"  {'-'*4}  {'-'*16}  {'-'*14}  {'-'*14}  {'-'*14}  {'-'*22}")

    window_stats = {}
    for n_win in LOOKBACK_WINDOWS:
        # Build G_recent: max of a_G over the previous n_win bars (lag-1 = no lookahead)
        G_recent = aG.rolling(n_win, min_periods=1).max().shift(1).fillna(0.0)

        struct_rel = A_fire & (G_recent > G_MEM_THRESH)
        rand_casc  = A_fire & (G_recent <= G_MEM_THRESH)

        n_struct = int(struct_rel.sum())
        n_rand   = int(rand_casc.sum())
        pct_struct = (n_struct / n_Afire * 100) if n_Afire > 0 else 0.0

        G_rec_at_A = G_recent[A_fire] if n_Afire > 0 else pd.Series([], dtype=float)
        p50_G_rec = float(G_rec_at_A.median()) if len(G_rec_at_A) > 0 else 0.0
        p90_G_rec = float(G_rec_at_A.quantile(0.90)) if len(G_rec_at_A) > 0 else 0.0

        print(f"  {n_win:>4}  {n_struct:>6} ({n_struct/N*100:5.2f}%)  "
              f"{n_rand:>5} ({n_rand/N*100:5.2f}%)  "
              f"{p50_G_rec:>14.4f}  {p90_G_rec:>14.4f}  "
              f"{pct_struct:>20.1f}%")

        window_stats[n_win] = dict(
            n_struct=n_struct, n_rand=n_rand, pct_struct=pct_struct,
            p50_G_recent_at_A=p50_G_rec, p90_G_recent_at_A=p90_G_rec,
        )

    # Verdict
    best_n   = max(LOOKBACK_WINDOWS, key=lambda n: window_stats[n]['n_struct'])
    best_pct = window_stats[best_n]['pct_struct']
    print(f"\n  Best window: N={best_n} with {best_pct:.1f}% of A-fires classified as struct_release")
    if best_pct >= 20:
        print(f"  ✓ HYPOTHESIS SUPPORTED: meaningful struct_release signal exists")
    elif best_pct >= 5:
        print(f"  ~ WEAK SIGNAL: struct_release fires but may lack statistical power")
    else:
        print(f"  ✗ HYPOTHESIS WEAK: struct_release rate < 5% — phase transition is rare here")

    return window_stats


# ═══════════════════════════════════════════════════════════════════════════════
#  V40 SIZING — PHASE-TRANSITION
# ═══════════════════════════════════════════════════════════════════════════════

def apply_v40_sizing(base_pnl: pd.Series,
                     sig_v36:  pd.DataFrame,
                     lam_feat: pd.DataFrame,
                     sig_4ch:  pd.DataFrame) -> dict[str, pd.Series]:
    """
    v40: Replace simultaneous G×A condition with temporal G→A sequence.

    G_recent[t] = max(a_G[t-N], …, a_G[t-1])   (rolling max, no lookahead)

    A-fire split:
      struct_release = (a_A > 0.70) & (G_recent > 0.50)  → GOOD A
      rand_cascade   = (a_A > 0.70) & (G_recent ≤ 0.50)  → BAD A

    phase_scl = 1 + STRUCT_BOOST * struct_release - RAND_KILL * rand_cascade

    All signals shifted by 1 bar for no-lookahead compliance.
    """
    idx  = base_pnl.index
    sv36 = sig_v36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lam_feat.reindex(idx, method='ffill').fillna(0.5)
    s4   = sig_4ch.reindex(idx, method='ffill').fillna(0.0)
    base = base_pnl.fillna(0.0)

    # v38 core sizing (lag-1)
    gam_adj  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lam_pct  = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size_sym = np.clip(1.0 - gam_adj, 0.0, 1.0) * (0.75 + 0.5 * lam_pct)

    # Raw channel attributions (unshifted — we apply shift in rolling calc below)
    a_G_raw = s4['a_G']
    a_A_raw = s4['a_A']

    # Point-in-time signals (lag-1) — used for champion G-boost
    a_G = a_G_raw.shift(1).fillna(0.0)
    a_A = a_A_raw.shift(1).fillna(0.0)

    # Champion G-boost flag (lag-1)
    flag_aG_high = (a_G > G_BOOST_THRESH).astype(float)

    # A-fire flag (lag-1)
    A_fire = (a_A > A_FIRE_THRESH).astype(float)

    pnl = {}

    # ── Reference baselines ────────────────────────────────────────────────────
    pnl['v38_sym_W100'] = base * size_sym
    pnl['v39b_aG_boost'] = base * size_sym * (1.0 + CHAMPION_BOOST * flag_aG_high)

    # ── Phase-transition sweep over lookback windows ───────────────────────────
    # G_recent: rolling max of a_G over the N bars BEFORE current bar (no lookahead)
    # Implementation: rolling(N).max() at bar t covers [t-N+1, t],
    # then .shift(1) moves it to [t-N, t-1] from decision bar t's perspective.
    for n_win in LOOKBACK_WINDOWS:
        G_recent = a_G_raw.rolling(n_win, min_periods=1).max().shift(1).fillna(0.0)

        struct_rel = ((a_A_raw.shift(1).fillna(0.0) > A_FIRE_THRESH) &
                      (G_recent > G_MEM_THRESH)).astype(float)
        rand_casc  = ((a_A_raw.shift(1).fillna(0.0) > A_FIRE_THRESH) &
                      (G_recent <= G_MEM_THRESH)).astype(float)

        phase_scl = (1.0
                     + STRUCT_BOOST_DEF * struct_rel
                     - RAND_KILL_DEF    * rand_casc).clip(0.05, 3.0)

        # Champion G-boost × phase scaling
        pnl[f'v40_phase_N{n_win}'] = (base * size_sym
                                       * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                       * phase_scl)

    # ── Ablation suite at N=BEST_N ─────────────────────────────────────────────
    n_abl = BEST_N
    G_rec_abl = a_G_raw.rolling(n_abl, min_periods=1).max().shift(1).fillna(0.0)
    struct_abl = ((a_A_raw.shift(1).fillna(0.0) > A_FIRE_THRESH) &
                  (G_rec_abl > G_MEM_THRESH)).astype(float)
    rand_abl   = ((a_A_raw.shift(1).fillna(0.0) > A_FIRE_THRESH) &
                  (G_rec_abl <= G_MEM_THRESH)).astype(float)

    # Struct-only: boost GOOD A, do not penalise BAD A
    pnl['v40_structOnly_N8'] = (base * size_sym
                                 * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                 * (1.0 + STRUCT_BOOST_DEF * struct_abl))

    # Rand-only: kill BAD A, do not boost GOOD A
    pnl['v40_randOnly_N8'] = (base * size_sym
                               * (1.0 + CHAMPION_BOOST * flag_aG_high)
                               * (1.0 - RAND_KILL_DEF * rand_abl).clip(0.05, 3.0))

    # Soft phase (+0.10 boost, -0.20 kill)
    phase_soft = (1.0 + 0.10 * struct_abl - 0.20 * rand_abl).clip(0.05, 3.0)
    pnl['v40_softPhase_N8'] = (base * size_sym
                                * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                * phase_soft)

    # Hard phase (+0.30 boost, -0.60 kill)
    phase_hard = (1.0 + 0.30 * struct_abl - 0.60 * rand_abl).clip(0.05, 3.0)
    pnl['v40_hardPhase_N8'] = (base * size_sym
                                * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                * phase_hard)

    # Phase scaling without champion G-boost (isolate phase effect alone)
    phase_def = (1.0 + STRUCT_BOOST_DEF * struct_abl - RAND_KILL_DEF * rand_abl).clip(0.05, 3.0)
    pnl['v40_phaseOnly_N8_noGboost'] = base * size_sym * phase_def

    # G_MEM_THRESH sensitivity at N=8 (is 0.50 the right memory threshold?)
    for g_mem_str, g_mem in [('040', 0.40), ('045', 0.45), ('055', 0.55)]:
        struct_m = ((a_A_raw.shift(1).fillna(0.0) > A_FIRE_THRESH) &
                    (G_rec_abl > g_mem)).astype(float)
        rand_m   = ((a_A_raw.shift(1).fillna(0.0) > A_FIRE_THRESH) &
                    (G_rec_abl <= g_mem)).astype(float)
        phase_m  = (1.0 + STRUCT_BOOST_DEF * struct_m - RAND_KILL_DEF * rand_m).clip(0.05, 3.0)
        pnl[f'v40_phase_N8_gmem{g_mem_str}'] = (base * size_sym
                                                  * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                                  * phase_m)

    return pnl


# ═══════════════════════════════════════════════════════════════════════════════
#  PRINT PHASE ACTIVATION RATES (post-run, for the sizing pnl dict)
# ═══════════════════════════════════════════════════════════════════════════════

def print_phase_activation_rates(sig_4ch: pd.DataFrame, test_mask) -> None:
    """Print per-window struct/rand firing rates for the test period."""
    s   = sig_4ch[test_mask]
    aG  = s['a_G']
    aA  = s['a_A']
    N   = len(s)

    A_fire  = (aA > A_FIRE_THRESH)
    n_Afire = int(A_fire.sum())

    print(f"\n  Phase Activation Rates  (test {N:,} bars, {n_Afire} A-fire bars)")
    print(f"  {'N':>4}  {'struct_release':>14}  {'rand_cascade':>13}  "
          f"{'struct_scl':>12}  {'rand_scl':>10}")
    print(f"  {'-'*4}  {'-'*14}  {'-'*13}  {'-'*12}  {'-'*10}")

    for n_win in LOOKBACK_WINDOWS:
        G_recent   = aG.rolling(n_win, min_periods=1).max().shift(1).fillna(0.0)
        struct_rel = A_fire & (G_recent > G_MEM_THRESH)
        rand_casc  = A_fire & (G_recent <= G_MEM_THRESH)

        n_struct = int(struct_rel.sum())
        n_rand   = int(rand_casc.sum())

        struct_mean = float((1.0 + STRUCT_BOOST_DEF * struct_rel.astype(float)).mean())
        rand_mean   = float((1.0 - RAND_KILL_DEF   * rand_casc.astype(float)).mean())

        print(f"  {n_win:>4}  {n_struct:>5} ({n_struct/N*100:5.2f}%)  "
              f"{n_rand:>4} ({n_rand/N*100:5.2f}%)  "
              f"{struct_mean:>12.4f}  {rand_mean:>10.4f}")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    t_start = time.time()
    BAR = "=" * 100
    print(BAR)
    print("  CRYPTO BSDT v40 — Phase-Transition Model  (G → A with Memory)")
    print("  Insight: G and A are sequential phases, not concurrent factors.")
    print("  Fix:     G_recent = rolling_max(a_G, N).shift(1)  — temporal G memory")
    print("  Split:   struct_release = A-fire after G buildup  (GOOD)")
    print("           rand_cascade   = A-fire with no G prior  (BAD)")
    print("  Champion reference: v39b_aG_boost  +2.762")
    print(BAR)

    # ── 1. Data ────────────────────────────────────────────────────────────────
    print("\n[1] Fetching Binance 1h data ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"  {len(df_1h):,} bars  |  Train: {train_1h.sum():,}  |  Test: {test_1h.sum():,}")

    # ── 2. Funding ─────────────────────────────────────────────────────────────
    print("\n[2] Fetching funding data ...")
    try:
        funding  = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
        fund_eth = funding.get('ETHUSDT') if isinstance(funding, dict) else None
        fund_btc = funding.get('BTCUSDT') if isinstance(funding, dict) else None
    except Exception:
        fund_eth = fund_btc = None

    # ── 3. State panel ─────────────────────────────────────────────────────────
    print("\n[3] Building 8×8 intraday state panel ...")
    X_panel = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X_panel = np.nan_to_num(X_panel)
    print(f"  Shape: {X_panel.shape}")

    # ── 4a. v36 engine ─────────────────────────────────────────────────────────
    train_idx  = np.where(train_1h)[0]
    calib_idx  = train_idx[-CALIB_BARS:]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[calib_idx] = True

    print("\n[4a] Calibrating v36 engine (k=4) ...")
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(
        X_panel, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)

    # ── 4b. k=1 operator for gap channel ──────────────────────────────────────
    X_normal = X_panel[calib_mask]
    print(f"\n[4b] Calibrating k={PCA_K_B} operator for delta_G ...")
    M_k1 = MasterOperator.calibrate(X_normal, k=PCA_K_B)

    # ── 5. v36 signals ─────────────────────────────────────────────────────────
    print(f"\n[5] Computing v36 signals ...")
    sig_v36 = compute_intraday_signals(X_panel, df_1h, M, net, ews, stoch,
                                        e_star, theta)

    # ── 6. v37 price prediction ────────────────────────────────────────────────
    print("\n[6] Computing v37 price prediction layer ...")
    sig_v37, M_reversal, sigma00_sqrt = compute_price_prediction_signals(
        X_panel, df_1h, M, sig_v36, e_star, sigma_n)

    # ── 7. v38 lambda features ─────────────────────────────────────────────────
    print("\n[7] Computing v38 normalised-lambda features ...")
    lam_feat = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    # ── 8. Channel means + firing thresholds ──────────────────────────────────
    print(f"\n[8] Calibrating channel means (k={PCA_K_B}) ...")
    mu_norm = calibrate_channel_means(X_panel, calib_mask, M_k1)

    print(f"\n[9] Calibrating firing thresholds (k={PCA_K_B}) ...")
    fire_thresholds = calibrate_firing_thresholds(X_panel, calib_mask, M_k1,
                                                   pct=FIRE_PERCENTILE)

    # ── 10. Four-channel signals ───────────────────────────────────────────────
    print(f"\n[10] Computing four-channel signals ...")
    sig_4ch = compute_four_channel_signals_v39b(
        X_panel, df_1h, M_k1, sig_v36, fire_thresholds, mu_norm)
    print(f"  Signals: {len(sig_4ch.columns)} columns")

    # ── Phase-transition diagnostics ──────────────────────────────────────────
    print("\n" + "=" * 100)
    print("  PHASE-TRANSITION DIAGNOSTICS")
    print("=" * 100)
    print_transmission_lag_analysis(sig_4ch, test_1h)
    window_stats = print_phase_transition_stats(sig_4ch, test_1h)
    print_phase_activation_rates(sig_4ch, test_1h)

    # ── 11. v34 base portfolio ─────────────────────────────────────────────────
    print("\n[11] Building v34 base portfolio ...")
    h_strats = compute_1h_strategies(df_1h, has_sol)
    df_d   = fetch_and_prepare()
    df_d   = add_cross_market_features(df_d)
    fund_d = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
    df_d   = add_leverage_features(df_d, fund_d)
    train_mask_d   = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
    train_mask_arr = np.asarray(train_mask_d, dtype=bool)
    pos_dict, _, F_daily, gate_daily = build_daily_positions(
        df_d, train_mask_d, train_mask_arr)
    instr_map = {
        'D1_trend_eth': df_1h['ret_eth'],
        'D2_pairs_eb':  df_1h['spread_ret_eb'],
        'D3_pairs_es':  df_1h['ret_eth'] - df_1h.get('ret_sol', df_1h['ret_eth']),
        'D4_macro_btc': df_1h['ret_btc'],
        'D5_macro_alt': df_1h['ret_eth'],
    }
    d_strats_1h = {
        name: upsample_daily_to_1h_pnl(pos, instr_map.get(name, df_1h['ret_eth']),
                                         gate_daily)
        for name, pos in pos_dict.items()
    }
    all_pnls = {**d_strats_1h, **h_strats}
    Q_v34    = compute_quality(all_pnls, bpd=BPD)
    pnl_combined_v34 = assemble_combined(all_pnls, Q_v34)
    st_v34 = _stats(pnl_combined_v34[pnl_combined_v34.index >= TEST_START])
    print(f"  v34 gross  Sharpe: {st_v34['sharpe']:+.3f}  "
          f"MaxDD: {st_v34['max_dd']:+.1%}  CAGR: {st_v34['cagr']:+.1%}")

    # ── 12. Apply v40 sizing ───────────────────────────────────────────────────
    print("\n[12] Applying v40 phase-transition sizing ...")
    pnl_dict = apply_v40_sizing(pnl_combined_v34, sig_v36, lam_feat, sig_4ch)
    pnl_dict = {'v34_baseline': pnl_combined_v34, **pnl_dict}

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("  GROSS SNAPSHOT  (K=5, 2023 → 2026)")
    print("=" * 100)
    print_summary_table(pnl_dict, K=5)

    print("\n" + "=" * 100)
    print("  YEAR-ON-YEAR  ($100 start, compounding, gross)")
    print("=" * 100)
    for name, pnl in pnl_dict.items():
        _yoy_table(name, pnl)

    # ── Save JSON ──────────────────────────────────────────────────────────────
    res_path = OUT_DIR_ / 'crypto_bsdt_v40_phase_transition.json'
    results  = {}
    for name, pnl in pnl_dict.items():
        ts    = pnl[pnl.index >= TEST_START]
        lev   = (ts * 5).clip(-0.5, 0.5)
        ec    = (1 + lev).cumprod()
        n_yrs = len(ts) / (365 * 24)
        cagr  = float(ec.iloc[-1] ** (1 / max(n_yrs, 0.1)) - 1) * 100
        dd    = float((ec / ec.cummax() - 1).min())
        sh    = float(lev.mean() / lev.std() * np.sqrt(ANN_1H)) if lev.std() > 0 else 0.0
        results[name] = dict(sharpe_K5=round(sh, 4),
                             max_dd_K5=round(dd * 100, 2),
                             cagr_K5=round(cagr, 2),
                             final_K5=round(float(ec.iloc[-1]) * 100, 2))

    # Signal summary
    sig_s = sig_4ch[test_1h]
    sig_summary = {}
    for col in ['a_G', 'a_A', 'a_T', 'a_C']:
        v = sig_s[col].dropna()
        sig_summary[col] = dict(mean=round(float(v.mean()), 6),
                                std=round(float(v.std()), 6),
                                p25=round(float(v.quantile(0.25)), 6),
                                p75=round(float(v.quantile(0.75)), 6),
                                p95=round(float(v.quantile(0.95)), 6))

    # Phase window statistics
    phase_summary = {}
    for n_win in LOOKBACK_WINDOWS:
        aG_t = sig_s['a_G']
        aA_t = sig_s['a_A']
        G_rec = aG_t.rolling(n_win, min_periods=1).max().shift(1).fillna(0.0)
        A_f   = (aA_t > A_FIRE_THRESH)
        sr    = A_f & (G_rec > G_MEM_THRESH)
        rc    = A_f & (G_rec <= G_MEM_THRESH)
        phase_summary[f'N{n_win}'] = dict(
            struct_release_bars=int(sr.sum()),
            rand_cascade_bars=int(rc.sum()),
            struct_pct_of_A_fires=round(float(sr.sum()) / max(int(A_f.sum()), 1) * 100, 2),
            G_recent_p50_at_A=round(float(G_rec[A_f].median()) if A_f.any() else 0.0, 4),
            G_recent_p90_at_A=round(float(G_rec[A_f].quantile(0.9)) if A_f.any() else 0.0, 4),
        )

    with open(res_path, 'w') as f:
        json.dump({
            'strategies':    results,
            'signals':       sig_summary,
            'phase_windows': phase_summary,
            'config': {
                'PCA_K':           PCA_K_B,
                'A_FIRE_THRESH':   A_FIRE_THRESH,
                'G_MEM_THRESH':    G_MEM_THRESH,
                'G_BOOST_THRESH':  G_BOOST_THRESH,
                'CHAMPION_BOOST':  CHAMPION_BOOST,
                'STRUCT_BOOST':    STRUCT_BOOST_DEF,
                'RAND_KILL':       RAND_KILL_DEF,
                'LOOKBACK_WINDOWS': LOOKBACK_WINDOWS,
                'BEST_N':          BEST_N,
            },
        }, f, indent=2)
    print(f"\n  Saved → {res_path}")
    print(f"\n  Total runtime: {time.time() - t_start:.0f}s")
    print("=" * 100)


if __name__ == '__main__':
    main()
