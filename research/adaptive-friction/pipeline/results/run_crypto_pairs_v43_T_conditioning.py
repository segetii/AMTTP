"""
Crypto BSDT v43 — T-Channel Conditioning on Phase Transitions
=============================================================
Champion: v40_phase_N8_gmem045  +2.883  (N=8, G_MEM=0.45, STRUCT=+0.20, KILL=-0.40)

Hypothesis: Among struct_release events (A-fire after G-precursor), those
accompanied by HIGH temporal novelty (T-channel) are stronger phase transitions.

Physical basis:
  T = temporal novelty: how far the current state is outside the normal-mode
      temporal manifold of calibration states.
  High T at A-fire → the system is in genuinely novel territory → stronger signal
  Low T at A-fire  → a familiar kind of structural event → weaker, possibly noise

3-class phase decomposition:
  super_struct = struct_release & (T_sig > T_thresh)   → STRONG (boost harder)
  weak_struct  = struct_release & (T_sig ≤ T_thresh)   → WEAK   (boost softer)
  rand_cascade = (a_A > 0.70) & (G_recent ≤ 0.45)     → BAD A  (kill, unchanged)

T signal variants:
  direct:         a_T.shift(1)                     → point-in-time lag-1
  rollmax(N_T):   rolling_max(a_T, N_T).shift(1)   → rolling peak of T

DIAGNOSTIC (printed before strategies):
  a_T distribution at struct_release vs rand_cascade vs all bars
  T-struct correlation check (does high T correlate with G_recent at A-fire?)

STRATEGIES (~31 variants):
  Refs: v34_baseline, v39b_aG_boost, v40_champion_ref
  Direct thresh sweep:
    'soft'  (SUPER=0.25, WEAK=0.15)  × {0.35, 0.38, 0.40, 0.42, 0.45, 0.48}  → 6
    'mid'   (SUPER=0.30, WEAK=0.10)  × 6 thresholds                            → 6
    'hard'  (SUPER=0.40, WEAK=0.00)  × 6 thresholds                            → 6
  RollMax T signal (N_T=4, N_T=8), mid coeffs:
    thresholds {0.40, 0.45, 0.48} × 2 windows                                  → 6
  T conditions rand_cascade too (4-class, mid coeffs):
    thresholds {0.40, 0.45}                                                     → 2
  T on rand_cascade only (struct unchanged at +0.20):
    thresholds {0.40, 0.45}                                                     → 2

T-channel stats from v40 test period:
  a_T: mean=0.355, p25=0.313, p50≈0.355, p75=0.450, p95=0.510
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

# ── Champion parameters (v40_phase_N8_gmem045) ────────────────────────────────
N_BEST          = 8       # rolling_max window for G memory
G_MEM_THRESH    = 0.45   # G_recent threshold for structural precursor
G_BOOST_THRESH  = 0.50   # v39b champion G-boost flag
CHAMPION_BOOST  = 0.50   # G-boost coefficient
A_FIRE_THRESH   = 0.70   # a_A threshold for velocity event
STRUCT_BOOST    = 0.20   # v40 champion struct boost
RAND_KILL       = 0.40   # v40 champion rand kill

# ── T-conditioning sweep parameters ───────────────────────────────────────────
# a_T: mean=0.355, p25=0.313, p50≈0.355, p75=0.450, p95=0.510
T_THRESHOLDS  = [0.35, 0.38, 0.40, 0.42, 0.45, 0.48]
T_THRESH_STRS = ['35', '38', '40', '42', '45', '48']

# (super_boost, weak_boost) — super > STRUCT_BOOST(0.20) > weak
COEFF_PAIRS = {
    'soft': (0.25, 0.15),   # gentle split around 0.20
    'mid':  (0.30, 0.10),   # moderate split
    'hard': (0.40, 0.00),   # maximum: no boost for weak_struct
}

# RollMax T signal windows and thresholds
T_ROLL_WINDOWS  = [4, 8]
T_ROLL_THRS     = [('40', 0.40), ('45', 0.45), ('48', 0.48)]

# T-rand split thresholds
T_RAND_THRS     = [('40', 0.40), ('45', 0.45)]


# ═══════════════════════════════════════════════════════════════════════════════
#  T-CHANNEL DIAGNOSTIC AT PHASE EVENTS
# ═══════════════════════════════════════════════════════════════════════════════

def print_T_conditioning_diagnostic(sig_4ch: pd.DataFrame, test_mask) -> None:
    """
    Key question: Does a_T discriminate between struct_release bars with
    different outcomes? And is T independent of G (or just proxying it)?

    Prints:
      1. a_T distribution: all bars vs struct_release vs rand_cascade
      2. T-G correlation at A-fire events
      3. struct%@T>thresh for various thresholds (how many struct_release have high T)
    """
    s    = sig_4ch[test_mask]
    aG   = s['a_G']
    aA   = s['a_A']
    aT   = s['a_T']
    N    = len(s)

    A_fire      = (aA > A_FIRE_THRESH)
    G_recent    = aG.rolling(N_BEST, min_periods=1).max().shift(1).fillna(0.0)

    struct_rel  = A_fire & (G_recent > G_MEM_THRESH)
    rand_casc   = A_fire & (G_recent <= G_MEM_THRESH)

    n_struct    = int(struct_rel.sum())
    n_rand      = int(rand_casc.sum())
    n_Afire     = int(A_fire.sum())

    BAR = "=" * 100
    print(f"\n{BAR}")
    print("  T-CHANNEL CONDITIONING DIAGNOSTIC")
    print(BAR)
    print(f"  Test period: {N:,} bars  |  A-fire: {n_Afire}  |  "
          f"struct_release: {n_struct}  |  rand_cascade: {n_rand}")
    print()

    # 1. a_T distributions
    def _dist(v: pd.Series, label: str) -> None:
        if len(v) == 0:
            print(f"  {label:<30s}  [empty]")
            return
        print(f"  {label:<30s}  mean={v.mean():.4f}  p25={v.quantile(0.25):.4f}  "
              f"p50={v.median():.4f}  p75={v.quantile(0.75):.4f}  "
              f"p90={v.quantile(0.90):.4f}  p95={v.quantile(0.95):.4f}")

    print("  a_T distributions (lag-1, same-bar simultaneous):")
    _dist(aT,                              "All bars (global)")
    _dist(aT[A_fire],                      "At A-fire (any)")
    _dist(aT[struct_rel],                  "At struct_release")
    _dist(aT[rand_casc],                   "At rand_cascade")
    if n_struct > 0:
        # T at struct_release vs rand_cascade — are they different?
        t_struct_mean = float(aT[struct_rel].mean())
        t_rand_mean   = float(aT[rand_casc].mean() if n_rand > 0 else 0.0)
        delta = t_struct_mean - t_rand_mean
        print(f"\n  ΔT (struct_release − rand_cascade) = {delta:+.4f}")
        if abs(delta) >= 0.02:
            print(f"  → T discriminates phase type  (|ΔT| = {abs(delta):.3f} ≥ 0.02)")
        else:
            print(f"  → T does NOT discriminate phase type  (|ΔT| = {abs(delta):.3f} < 0.02)")

    # 2. T-G correlation at A-fire events
    print()
    if n_Afire > 5:
        corr_TG_Afire = float(aT[A_fire].corr(G_recent[A_fire]))
        print(f"  Correlation(a_T, G_recent) at A-fire bars: {corr_TG_Afire:+.4f}")
        if abs(corr_TG_Afire) < 0.15:
            print(f"  → T and G are INDEPENDENT at A-fire  (|corr| < 0.15) — T adds new info")
        else:
            print(f"  → T and G are CORRELATED at A-fire  (|corr| = {abs(corr_TG_Afire):.3f}) — T may proxy G")

    # 3. struct% split at T thresholds (direct lag-1 T)
    aT_lag1 = aT.shift(1).fillna(0.0)
    G_rec2  = aG.rolling(N_BEST, min_periods=1).max().shift(1).fillna(0.0)
    A_fire2 = (aA.shift(1).fillna(0.0) > A_FIRE_THRESH)
    sr2     = A_fire2 & (G_rec2 > G_MEM_THRESH)
    n_sr2   = int(sr2.sum())

    print(f"\n  struct_release split at T thresholds (lag-1 T_sig, n_struct={n_sr2}):")
    print(f"  {'T_thresh':>10}  {'super_struct%':>15}  {'#super':>8}  {'#weak':>7}  "
          f"{'T_super_p50':>13}  {'T_weak_p50':>12}")
    print(f"  {'-'*10}  {'-'*15}  {'-'*8}  {'-'*7}  {'-'*13}  {'-'*12}")
    for t_thr in T_THRESHOLDS:
        super_s = sr2 & (aT_lag1 > t_thr)
        weak_s  = sr2 & (aT_lag1 <= t_thr)
        n_sup   = int(super_s.sum())
        n_wk    = int(weak_s.sum())
        pct_sup = (n_sup / n_sr2 * 100) if n_sr2 > 0 else 0.0
        p50_sup = float(aT_lag1[super_s].median()) if n_sup > 0 else float('nan')
        p50_wk  = float(aT_lag1[weak_s].median())  if n_wk  > 0 else float('nan')
        print(f"  {t_thr:>10.2f}  {pct_sup:>14.1f}%  {n_sup:>8d}  {n_wk:>7d}  "
              f"  {p50_sup:>11.4f}    {p50_wk:>10.4f}")

    print()


# ═══════════════════════════════════════════════════════════════════════════════
#  V43 SIZING — T-CHANNEL CONDITIONING
# ═══════════════════════════════════════════════════════════════════════════════

def apply_v43_sizing(base_pnl: pd.Series,
                     sig_v36:  pd.DataFrame,
                     lam_feat: pd.DataFrame,
                     sig_4ch:  pd.DataFrame) -> dict[str, pd.Series]:
    """
    v43: Extend v40 champion with T-channel conditioning.

    Champion (v40_phase_N8_gmem045):
      G_recent = rolling_max(a_G, 8).shift(1)
      struct_release = A-fire & G_recent > 0.45
      rand_cascade   = A-fire & G_recent ≤ 0.45
      size = base × size_sym × (1 + 0.50*G_high) × (1 + 0.20*struct − 0.40*rand)

    v43 addition — split struct_release by T-novelty:
      super_struct = struct_release & T_sig > T_thresh
      weak_struct  = struct_release & T_sig ≤ T_thresh
      size = base × size_sym × (1 + 0.50*G_high)
             × (1 + SUPER*super + WEAK*weak − KILL*rand)
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

    a_G_raw = s4['a_G']
    a_A_raw = s4['a_A']
    a_T_raw = s4['a_T']

    # Lag-1 signals
    a_G = a_G_raw.shift(1).fillna(0.0)
    a_T = a_T_raw.shift(1).fillna(0.0)     # direct lag-1 T signal

    # Champion G-boost flag (lag-1)
    flag_aG_high = (a_G > G_BOOST_THRESH).astype(float)

    # G_recent: rolling_max(a_G, N_BEST).shift(1)  — champion memory window
    G_recent = a_G_raw.rolling(N_BEST, min_periods=1).max().shift(1).fillna(0.0)

    # A-fire (lag-1)
    A_fire_lag1 = (a_A_raw.shift(1).fillna(0.0) > A_FIRE_THRESH)

    # Base phase flags (v40 champion split)
    struct_rel_base = (A_fire_lag1 & (G_recent > G_MEM_THRESH))
    rand_casc_base  = (A_fire_lag1 & (G_recent <= G_MEM_THRESH))

    pnl = {}

    # ── References ────────────────────────────────────────────────────────────
    pnl['v39b_aG_boost'] = base * size_sym * (1.0 + CHAMPION_BOOST * flag_aG_high)

    phase_champ = (1.0
                   + STRUCT_BOOST * struct_rel_base.astype(float)
                   - RAND_KILL    * rand_casc_base.astype(float)).clip(0.05, 3.0)
    pnl['v40_champion_ref'] = (base * size_sym
                                * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                * phase_champ)

    # ── Direct a_T conditioning ───────────────────────────────────────────────
    # T_sig = a_T.shift(1)  (direct lag-1 T novelty score)
    for t_str, t_thr in zip(T_THRESH_STRS, T_THRESHOLDS):
        super_s = (struct_rel_base & (a_T > t_thr)).astype(float)
        weak_s  = (struct_rel_base & (a_T <= t_thr)).astype(float)
        rand_f  = rand_casc_base.astype(float)

        for cname, (sb, wb) in COEFF_PAIRS.items():
            phase_t = (1.0
                       + sb * super_s
                       + wb * weak_s
                       - RAND_KILL * rand_f).clip(0.05, 3.0)
            pnl[f'v43_T2c_{cname}_thr{t_str}'] = (base * size_sym
                                                    * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                                    * phase_t)

    # ── RollMax T signal ──────────────────────────────────────────────────────
    # T_sig = rolling_max(a_T, N_T).shift(1)  — memory of T spikes
    for n_t in T_ROLL_WINDOWS:
        T_sig_roll = a_T_raw.rolling(n_t, min_periods=1).max().shift(1).fillna(0.0)
        for t_str, t_thr in T_ROLL_THRS:
            super_s = (struct_rel_base & (T_sig_roll > t_thr)).astype(float)
            weak_s  = (struct_rel_base & (T_sig_roll <= t_thr)).astype(float)
            rand_f  = rand_casc_base.astype(float)
            # Use mid coefficients for rollmax variants
            phase_t = (1.0
                       + 0.30 * super_s
                       + 0.10 * weak_s
                       - RAND_KILL * rand_f).clip(0.05, 3.0)
            pnl[f'v43_Troll_N{n_t}_thr{t_str}'] = (base * size_sym
                                                     * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                                     * phase_t)

    # ── T conditioning rand_cascade (4-class) ─────────────────────────────────
    # Split rand_cascade by T:
    #   high_T_rand: novel random cascade → kill less  (-0.20)
    #   low_T_rand:  boring random cascade → kill more (-0.60)
    # Also split struct_release by T (mid coefficients).
    for t_str, t_thr in T_RAND_THRS:
        super_s     = (struct_rel_base & (a_T > t_thr)).astype(float)
        weak_s      = (struct_rel_base & (a_T <= t_thr)).astype(float)
        hiT_rand    = (rand_casc_base & (a_T > t_thr)).astype(float)
        loT_rand    = (rand_casc_base & (a_T <= t_thr)).astype(float)

        phase_4cls = (1.0
                      + 0.30 * super_s
                      + 0.10 * weak_s
                      - 0.20 * hiT_rand
                      - 0.60 * loT_rand).clip(0.05, 3.0)
        pnl[f'v43_4cls_thr{t_str}'] = (base * size_sym
                                        * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                        * phase_4cls)

    # ── T conditions rand_cascade only (struct unchanged at +0.20) ───────────
    for t_str, t_thr in T_RAND_THRS:
        hiT_rand = (rand_casc_base & (a_T > t_thr)).astype(float)
        loT_rand = (rand_casc_base & (a_T <= t_thr)).astype(float)
        struct_f = struct_rel_base.astype(float)

        phase_ro = (1.0
                    + STRUCT_BOOST * struct_f
                    - 0.20 * hiT_rand
                    - 0.60 * loT_rand).clip(0.05, 3.0)
        pnl[f'v43_TrandOnly_thr{t_str}'] = (base * size_sym
                                              * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                              * phase_ro)

    return pnl


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    t_start = time.time()
    BAR = "=" * 100
    print(BAR)
    print("  CRYPTO BSDT v43 — T-Channel Conditioning on Phase Transitions")
    print("  Champion: v40_phase_N8_gmem045  +2.883")
    print("  Hypothesis: High T novelty at struct_release → stronger phase transition")
    print("  3-class: super_struct (T high) / weak_struct (T low) / rand_cascade")
    print(BAR)

    # ── 1. Data ─────────────────────────────────────────────────────────────────
    print("\n[1] Fetching 1h data ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"  1h DataFrame: {df_1h.index[0]}  →  {df_1h.index[-1]}   "
          f"n={len(df_1h):,} bars  ({(df_1h.index[-1]-df_1h.index[0]).days} days)")
    print(f"  Train: {train_1h.sum():,}   Test: {test_1h.sum():,}   SOL: {has_sol}")
    print(f"  {len(df_1h):,} bars  |  Train: {train_1h.sum():,}  |  Test: {test_1h.sum():,}")

    # ── 2. Funding ───────────────────────────────────────────────────────────────
    print("\n[2] Fetching funding ...")
    try:
        funding  = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
        fund_eth = funding.get('ETHUSDT') if isinstance(funding, dict) else None
        fund_btc = funding.get('BTCUSDT') if isinstance(funding, dict) else None
    except Exception:
        fund_eth = fund_btc = None

    # ── 3. State panel ───────────────────────────────────────────────────────────
    print("\n[3] Building state panel ...")
    X_panel = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X_panel = np.nan_to_num(X_panel)

    # ── 4a. v36 engine ───────────────────────────────────────────────────────────
    train_idx  = np.where(train_1h)[0]
    calib_idx  = train_idx[-CALIB_BARS:]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[calib_idx] = True

    print("\n[4a] Calibrating v36 engine ...")
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(
        X_panel, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)

    # ── 4b. k=1 operator ─────────────────────────────────────────────────────────
    X_normal = X_panel[calib_mask]
    print(f"\n[4b] Calibrating k={PCA_K_B} operator ...")
    M_k1 = MasterOperator.calibrate(X_normal, k=PCA_K_B)

    # ── 5. v36 signals ───────────────────────────────────────────────────────────
    print(f"\n[5] v36 signals ...")
    sig_v36 = compute_intraday_signals(X_panel, df_1h, M, net, ews, stoch,
                                        e_star, theta)

    # ── 6. v37 price prediction ──────────────────────────────────────────────────
    print("\n[6] v37 price prediction ...")
    sig_v37, M_reversal, sigma00_sqrt = compute_price_prediction_signals(
        X_panel, df_1h, M, sig_v36, e_star, sigma_n)

    # ── 7. v38 lambda features ───────────────────────────────────────────────────
    print("\n[7] v38 lambda features ...")
    lam_feat = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    # ── 8. Channel means ─────────────────────────────────────────────────────────
    print(f"\n[8] Channel means ...")
    mu_norm = calibrate_channel_means(X_panel, calib_mask, M_k1)

    # ── 9. Firing thresholds ─────────────────────────────────────────────────────
    print(f"\n[9] Firing thresholds ...")
    fire_thresholds = calibrate_firing_thresholds(X_panel, calib_mask, M_k1,
                                                   pct=FIRE_PERCENTILE)

    # ── 10. Four-channel signals ─────────────────────────────────────────────────
    print(f"\n[10] Four-channel signals ...")
    sig_4ch = compute_four_channel_signals_v39b(
        X_panel, df_1h, M_k1, sig_v36, fire_thresholds, mu_norm)

    # ── T diagnostic ─────────────────────────────────────────────────────────────
    print_T_conditioning_diagnostic(sig_4ch, test_1h)

    # ── 11. v34 base portfolio ───────────────────────────────────────────────────
    print("\n[11] v34 base portfolio ...")
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

    # ── 12. Apply v43 sizing ──────────────────────────────────────────────────────
    print("\n[12] Applying v43 T-conditioning sizing ...")
    pnl_dict = apply_v43_sizing(pnl_combined_v34, sig_v36, lam_feat, sig_4ch)
    pnl_dict = {'v34_baseline': pnl_combined_v34, **pnl_dict}

    # ── Summary ───────────────────────────────────────────────────────────────────
    print("\n" + BAR)
    print("  GROSS SNAPSHOT  (K=5, 2023 → 2026)")
    print(BAR)
    print_summary_table(pnl_dict, K=5)

    print("\n" + BAR)
    print("  YEAR-ON-YEAR  ($100 start, compounding, gross)")
    print(BAR)
    for name, pnl in pnl_dict.items():
        _yoy_table(name, pnl)

    # ── Save JSON ─────────────────────────────────────────────────────────────────
    res_path = OUT_DIR_ / 'crypto_bsdt_v43_T_conditioning.json'
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

    # Signal and T-conditioning summary
    sig_s = sig_4ch[test_1h]
    sig_summary = {}
    for col in ['a_G', 'a_A', 'a_T', 'a_C']:
        v = sig_s[col].dropna()
        sig_summary[col] = dict(mean=round(float(v.mean()), 6),
                                std=round(float(v.std()), 6),
                                p25=round(float(v.quantile(0.25)), 6),
                                p75=round(float(v.quantile(0.75)), 6),
                                p95=round(float(v.quantile(0.95)), 6))

    # T-conditioning activation summary
    aG_s   = sig_s['a_G']
    aA_s   = sig_s['a_A']
    aT_s   = sig_s['a_T']
    G_rec  = aG_s.rolling(N_BEST, min_periods=1).max().shift(1).fillna(0.0)
    A_f    = (aA_s.shift(1).fillna(0.0) > A_FIRE_THRESH)
    sr     = A_f & (G_rec > G_MEM_THRESH)
    rc     = A_f & (G_rec <= G_MEM_THRESH)
    aT_l1  = aT_s.shift(1).fillna(0.0)

    t_cond_summary = {
        'struct_release_bars':  int(sr.sum()),
        'rand_cascade_bars':    int(rc.sum()),
        'aT_at_struct_release': {
            'mean': round(float(aT_l1[sr].mean()) if sr.any() else 0.0, 4),
            'p50':  round(float(aT_l1[sr].median()) if sr.any() else 0.0, 4),
            'p75':  round(float(aT_l1[sr].quantile(0.75)) if sr.any() else 0.0, 4),
        },
        'aT_at_rand_cascade': {
            'mean': round(float(aT_l1[rc].mean()) if rc.any() else 0.0, 4),
            'p50':  round(float(aT_l1[rc].median()) if rc.any() else 0.0, 4),
            'p75':  round(float(aT_l1[rc].quantile(0.75)) if rc.any() else 0.0, 4),
        },
        'delta_T_struct_minus_rand': round(
            float(aT_l1[sr].mean() - aT_l1[rc].mean()) if (sr.any() and rc.any()) else 0.0, 4),
        'corr_T_Grecent_at_Afire': round(
            float(aT_l1[A_f].corr(G_rec[A_f])) if A_f.any() else 0.0, 4),
        'super_struct_split': {
            str(t): {'n_super': int((sr & (aT_l1 > t)).sum()),
                     'n_weak':  int((sr & (aT_l1 <= t)).sum())}
            for t in T_THRESHOLDS
        },
    }

    with open(res_path, 'w') as f:
        json.dump({
            'strategies':    results,
            'signals':       sig_summary,
            'T_conditioning': t_cond_summary,
            'config': {
                'PCA_K':          PCA_K_B,
                'N_BEST':         N_BEST,
                'G_MEM_THRESH':   G_MEM_THRESH,
                'G_BOOST_THRESH': G_BOOST_THRESH,
                'CHAMPION_BOOST': CHAMPION_BOOST,
                'A_FIRE_THRESH':  A_FIRE_THRESH,
                'STRUCT_BOOST':   STRUCT_BOOST,
                'RAND_KILL':      RAND_KILL,
                'T_THRESHOLDS':   T_THRESHOLDS,
                'COEFF_PAIRS':    {k: list(v) for k, v in COEFF_PAIRS.items()},
            },
        }, f, indent=2)
    print(f"\n  Saved → {res_path}")
    print(f"\n  Total runtime: {time.time() - t_start:.0f}s")
    print(BAR)


if __name__ == '__main__':
    main()
