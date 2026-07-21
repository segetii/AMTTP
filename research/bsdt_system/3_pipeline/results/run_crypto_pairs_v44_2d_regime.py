"""
Crypto BSDT v44 — Continuous 2D (G,T) Regime Surface
=====================================================
Champion: v43_Troll_N8_thr40  +2.940  (N_G=8, G_MEM=0.45, N_T=8, T_MEM=0.40)

Insight from v43: G and T are orthogonal pre-event precursors.
    G = spatial instability  (geometry deviation)
    T = temporal instability (history mismatch)
    Both collapse to ~0 AT A-fire; both are elevated BEFORE it.

The 2-stage causal structure is now confirmed:
    Stage 1 (buildup):  G↑, T↑  →  latent instability
    Stage 2 (release):  A↑, G↓, T↓  →  kinetic event

v43 split instability into 3 discrete classes using a threshold on T_mem.
v44 moves to the full 4-regime framework and tests continuous scoring.

Memory signals (fixed):
    G_mem = rolling_max(a_G, N_G=8).shift(1)   ← champion parameters
    T_mem = rolling_max(a_T, N_T=8).shift(1)   ← v43 winner parameters

4-regime matrix at A-fire:
    q_GH_TH: G_mem > 0.45  AND  T_mem > 0.40  →  full instability (BEST)
    q_GH_TL: G_mem > 0.45  AND  T_mem ≤ 0.40  →  spatial shift only
    q_GL_TH: G_mem ≤ 0.45  AND  T_mem > 0.40  →  temporal anomaly only
    q_GL_TL: G_mem ≤ 0.45  AND  T_mem ≤ 0.40  →  stable (random cascade)

Note: v43 champion treated GL_TH = GL_TL = rand_cascade (uniform -0.40 kill).
Key new test: should GL_TH be neutral (0) or boosted? Is temporal-only instability
a positive signal or just noise?

STRATEGIES (~27 variants):
  Refs: v34_baseline, v40_champion_ref, v43_champion_ref
  Group A: 4-quadrant discrete (vary GH_TH strength)           — 6 variants
  Group B: 4-quadrant discrete (vary GL_TH treatment)          — 5 variants
  Group C: Continuous tanh score (w_G*G + w_T*T mixed)         — 9 variants
  Group D: Interaction term G_mem*T_mem in score               — 4 variants

Continuous scoring (Groups C, D):
    S = w_G * G_mem + w_T * T_mem + λ * G_mem * T_mem
    phase_at_A = 1 + RANGE * tanh(steepness * (S - midpoint))
    phase_elsewhere = 1.0  (only applied at A-fire bars)

The midpoint is set to the discriminating edge:
    midpoint(λ) = w_G*G_THRESH + w_T*T_THRESH + λ*G_THRESH*T_THRESH
    = 0.5*0.45 + 0.5*0.40 + λ*0.45*0.40
    = 0.425 + 0.18*λ
So: at (G_mem=G_THRESH, T_mem=T_THRESH) → S = midpoint → phase = 1.0 (neutral).
Above midpoint → boost; below midpoint → kill.
"""
from __future__ import annotations
import os, sys, json, time, warnings
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
from pathlib import Path
from collections import OrderedDict
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

# ── Champion parameters ────────────────────────────────────────────────────────
N_G             = 8       # G_mem rolling_max window
N_T             = 8       # T_mem rolling_max window
G_THRESH        = 0.45   # G_mem threshold (v40 champion)
T_THRESH        = 0.40   # T_mem threshold (v43 winner)
G_BOOST_THRESH  = 0.50   # v39b G-boost flag
CHAMPION_BOOST  = 0.50   # G-boost coefficient
A_FIRE_THRESH   = 0.70   # a_A threshold

# v43 champion discrete coefficients (4-quadrant baseline):
#   GH_TH = +0.30,  GH_TL = +0.10,  GL_TH = -0.40,  GL_TL = -0.40
V43_CHAMP_COEFFS = (0.30, 0.10, -0.40, -0.40)


# ── 4-quadrant specs: (c_GH_TH, c_GH_TL, c_GL_TH, c_GL_TL) ──────────────────
# phase = 1 + c_GH_TH*q_GH_TH + c_GH_TL*q_GH_TL + c_GL_TH*q_GL_TH + c_GL_TL*q_GL_TL
QUAD_SPECS: dict[str, tuple[float, float, float, float]] = {
    # ── Group A: vary GH_TH magnitude (GL_TH=-0.40 = v43 uniform rand kill) ──
    'q4_ghth035': (0.35, 0.10, -0.40, -0.40),  # +0.05 vs v43 champion
    'q4_ghth040': (0.40, 0.10, -0.40, -0.40),
    'q4_ghth045': (0.45, 0.10, -0.40, -0.40),
    'q4_ghth050': (0.50, 0.10, -0.40, -0.40),
    'q4_ghth035_ghtl005': (0.35, 0.05, -0.40, -0.40),  # tighter GHTL to fund GHTH
    'q4_ghth040_ghtl005': (0.40, 0.05, -0.40, -0.40),
    # ── Group B: vary GL_TH treatment (should temporal-only anomaly be neutral?) ──
    # v43 champion: GL_TH = -0.40 (treated as rand cascade)
    # New: allow GL_TH to be neutral (0) or positive
    'q4_glth_0_b030':    (0.30, 0.10, 0.00, -0.40),   # v43 GHTH=0.30, neutral GLTH
    'q4_glth_0_b035':    (0.35, 0.10, 0.00, -0.40),
    'q4_glth_0_b040':    (0.40, 0.10, 0.00, -0.40),
    'q4_glth_pos_b030':  (0.30, 0.10, 0.10, -0.40),   # small temporal boost
    'q4_glth_pos_b035':  (0.35, 0.10, 0.10, -0.40),
}


# ── Continuous score specs: (w_G, w_T, steepness, range) ──────────────────────
# midpoint is auto-computed: w_G*G_THRESH + w_T*T_THRESH  (no interaction)
# phase_at_A = 1 + range * tanh(steepness * (S - midpoint))
# S = w_G * G_mem + w_T * T_mem
CONT_SPECS: dict[str, tuple[float, float, float, float]] = {
    # ── Group C: linear sum score ──
    # Equal weights (0.5/0.5), vary steepness
    'cnt_eq_s10_r38':   (0.5, 0.5, 10, 0.38),
    'cnt_eq_s15_r38':   (0.5, 0.5, 15, 0.38),
    'cnt_eq_s20_r38':   (0.5, 0.5, 20, 0.38),
    'cnt_eq_s10_r40':   (0.5, 0.5, 10, 0.40),   # range=0.40 matches champion kill
    # G-dominant (0.7/0.3)
    'cnt_Gd_s10_r38':   (0.7, 0.3, 10, 0.38),
    'cnt_Gd_s15_r38':   (0.7, 0.3, 15, 0.38),
    # T-dominant (0.3/0.7)
    'cnt_Td_s10_r38':   (0.3, 0.7, 10, 0.38),
    # G-only (reference: purely geometric instability)
    'cnt_Go_s10_r38':   (1.0, 0.0, 10, 0.38),
    # T-only (reference: purely temporal instability)
    'cnt_To_s10_r38':   (0.0, 1.0, 10, 0.38),
}


# ── Product interaction specs: (lambda, w_G, w_T, steepness, range) ──────────
# S = w_G * G_mem + w_T * T_mem + lambda * G_mem * T_mem
# midpoint = w_G*G_THRESH + w_T*T_THRESH + lambda*G_THRESH*T_THRESH
PROD_SPECS: dict[str, tuple[float, float, float, float, float]] = {
    'prd_lam0': (0.0, 0.5, 0.5, 10, 0.38),   # no interaction (sanity = cnt_eq_s10_r38)
    'prd_lam1': (1.0, 0.5, 0.5, 10, 0.38),   # mild interaction
    'prd_lam2': (2.0, 0.5, 0.5, 10, 0.38),   # moderate interaction
    'prd_lam4': (4.0, 0.5, 0.5, 10, 0.38),   # strong interaction
}


# ═══════════════════════════════════════════════════════════════════════════════
#  DIAGNOSTIC
# ═══════════════════════════════════════════════════════════════════════════════

def print_2d_regime_diagnostic(sig_4ch: pd.DataFrame, test_mask) -> None:
    """
    Print the 4-regime joint distribution.
    Key question: how many bars fall in each quadrant at A-fire?
    And what does the continuous score S look like in each quadrant?
    """
    s    = sig_4ch[test_mask]
    aG   = s['a_G']
    aA   = s['a_A']
    aT   = s['a_T']
    N    = len(s)

    G_mem = aG.rolling(N_G, min_periods=1).max().shift(1).fillna(0.0)
    T_mem = aT.rolling(N_T, min_periods=1).max().shift(1).fillna(0.0)
    A_fire = (aA.shift(1).fillna(0.0) > A_FIRE_THRESH)

    q_GH_TH = A_fire & (G_mem > G_THRESH) & (T_mem > T_THRESH)
    q_GH_TL = A_fire & (G_mem > G_THRESH) & (T_mem <= T_THRESH)
    q_GL_TH = A_fire & (G_mem <= G_THRESH) & (T_mem > T_THRESH)
    q_GL_TL = A_fire & (G_mem <= G_THRESH) & (T_mem <= T_THRESH)

    n_A     = int(A_fire.sum())
    n_GHTH  = int(q_GH_TH.sum())
    n_GHTL  = int(q_GH_TL.sum())
    n_GLTH  = int(q_GL_TH.sum())
    n_GLTL  = int(q_GL_TL.sum())

    BAR = "=" * 100
    print(f"\n{BAR}")
    print("  2D REGIME DIAGNOSTIC")
    print(BAR)
    print(f"  Test period: {N:,} bars  |  A-fire: {n_A} ({n_A/N*100:.2f}%)")
    print(f"  G_THRESH={G_THRESH:.2f}  T_THRESH={T_THRESH:.2f}  N_G={N_G}  N_T={N_T}")
    print()
    print(f"  {'Quadrant':<30s}  {'n':>6}  {'%A':>6}  "
          f"{'G_mem p50':>10}  {'T_mem p50':>10}  {'S_eq p50':>10}")
    print(f"  {'-'*30}  {'-'*6}  {'-'*6}  {'-'*10}  {'-'*10}  {'-'*10}")

    S_eq = 0.5 * G_mem + 0.5 * T_mem

    for label, mask in [
        ('GH_TH  (G↑,T↑) full instability', q_GH_TH),
        ('GH_TL  (G↑,T↓) spatial shift',    q_GH_TL),
        ('GL_TH  (G↓,T↑) temporal anomaly', q_GL_TH),
        ('GL_TL  (G↓,T↓) stable/random',    q_GL_TL),
    ]:
        n   = int(mask.sum())
        pct = (n / n_A * 100) if n_A > 0 else 0.0
        gm  = float(G_mem[mask].median()) if n > 0 else float('nan')
        tm  = float(T_mem[mask].median()) if n > 0 else float('nan')
        sm  = float(S_eq[mask].median())  if n > 0 else float('nan')
        print(f"  {label:<30s}  {n:>6d}  {pct:>5.1f}%  "
              f"  {gm:>8.4f}    {tm:>8.4f}    {sm:>8.4f}")

    # G_mem and T_mem distributions in struct_release
    struct = A_fire & (G_mem > G_THRESH)
    rand   = A_fire & (G_mem <= G_THRESH)
    n_str  = int(struct.sum())
    n_rnd  = int(rand.sum())

    print()
    print(f"  G_mem distribution at struct_release ({n_str} bars):")
    if n_str > 0:
        gm_s = G_mem[struct]
        print(f"    mean={gm_s.mean():.4f}  p25={gm_s.quantile(0.25):.4f}  "
              f"p50={gm_s.median():.4f}  p75={gm_s.quantile(0.75):.4f}  "
              f"p90={gm_s.quantile(0.90):.4f}")
    print(f"  T_mem distribution at struct_release ({n_str} bars):")
    if n_str > 0:
        tm_s = T_mem[struct]
        print(f"    mean={tm_s.mean():.4f}  p25={tm_s.quantile(0.25):.4f}  "
              f"p50={tm_s.median():.4f}  p75={tm_s.quantile(0.75):.4f}  "
              f"p90={tm_s.quantile(0.90):.4f}")
        frac_t_high = float((tm_s > T_THRESH).mean()) * 100
        print(f"    T_mem > {T_THRESH:.2f}: {frac_t_high:.1f}%  "
              f"→ super_struct: {n_GHTH}  weak_struct: {n_GHTL}")

    # Continuous score S distribution – equal weights
    print()
    print(f"  Continuous score S=0.5*G+0.5*T at A-fire quadrants:")
    mid_eq = 0.5 * G_THRESH + 0.5 * T_THRESH
    for label, mask in [
        ('GH_TH', q_GH_TH), ('GH_TL', q_GH_TL),
        ('GL_TH', q_GL_TH), ('GL_TL', q_GL_TL),
    ]:
        if mask.sum() > 0:
            sv = S_eq[mask]
            frac_above = float((sv > mid_eq).mean()) * 100
            print(f"    {label}: p25={sv.quantile(0.25):.4f}  p50={sv.median():.4f}  "
                  f"p75={sv.quantile(0.75):.4f}  frac>midpt({mid_eq:.3f}): {frac_above:.0f}%")
    print()


# ═══════════════════════════════════════════════════════════════════════════════
#  V44 SIZING
# ═══════════════════════════════════════════════════════════════════════════════

def apply_v44_sizing(base_pnl: pd.Series,
                     sig_v36:  pd.DataFrame,
                     lam_feat: pd.DataFrame,
                     sig_4ch:  pd.DataFrame) -> dict[str, pd.Series]:
    """
    v44: Full 4-regime (G,T) matrix and continuous 2D scoring surface.

    Memory signals:
        G_mem[t] = max(a_G[t-N_G], ..., a_G[t-1])  rolling_max, no lookahead
        T_mem[t] = max(a_T[t-N_T], ..., a_T[t-1])  rolling_max, no lookahead

    At A-fire[t]:
      discrete: assign to 4 quadrant based on (G_mem, T_mem) vs (G_THRESH, T_THRESH)
      continuous: score S = w_G*G_mem + w_T*T_mem [+ λ*G_mem*T_mem]
                  phase = 1 + RANGE * tanh(steepness * (S - midpoint))
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

    # Champion G-boost (lag-1)
    a_G = a_G_raw.shift(1).fillna(0.0)
    flag_aG_high = (a_G > G_BOOST_THRESH).astype(float)

    # Memory signals (lag-1 via rolling then shift)
    G_mem = a_G_raw.rolling(N_G, min_periods=1).max().shift(1).fillna(0.0)
    T_mem = a_T_raw.rolling(N_T, min_periods=1).max().shift(1).fillna(0.0)

    # A-fire flag (lag-1)
    A_fire_lag1 = (a_A_raw.shift(1).fillna(0.0) > A_FIRE_THRESH)

    # 4-quadrant masks (A-fire only)
    q_GH_TH = (A_fire_lag1 & (G_mem > G_THRESH) & (T_mem > T_THRESH)).astype(float)
    q_GH_TL = (A_fire_lag1 & (G_mem > G_THRESH) & (T_mem <= T_THRESH)).astype(float)
    q_GL_TH = (A_fire_lag1 & (G_mem <= G_THRESH) & (T_mem > T_THRESH)).astype(float)
    q_GL_TL = (A_fire_lag1 & (G_mem <= G_THRESH) & (T_mem <= T_THRESH)).astype(float)

    pnl: dict[str, pd.Series] = {}

    # ── References ────────────────────────────────────────────────────────────
    pnl['v40_champion_ref'] = (base * size_sym
                                * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                * (1.0
                                   + 0.20 * (q_GH_TH + q_GH_TL)  # struct_release
                                   - 0.40 * (q_GL_TH + q_GL_TL)  # rand_cascade
                                   ).clip(0.05, 3.0))

    # v43 champion: (GH_TH=0.30, GH_TL=0.10, GL_TH=-0.40, GL_TL=-0.40)
    a_v43, b_v43, c_v43, d_v43 = V43_CHAMP_COEFFS
    pnl['v43_champion_ref'] = (base * size_sym
                                * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                * (1.0
                                   + a_v43 * q_GH_TH
                                   + b_v43 * q_GH_TL
                                   + c_v43 * q_GL_TH
                                   + d_v43 * q_GL_TL
                                   ).clip(0.05, 3.0))

    # ── 4-quadrant discrete strategies ────────────────────────────────────────
    for name, (a, b, c, d) in QUAD_SPECS.items():
        phase = (1.0
                 + a * q_GH_TH
                 + b * q_GH_TL
                 + c * q_GL_TH
                 + d * q_GL_TL).clip(0.05, 3.0)
        pnl[f'v44_{name}'] = (base * size_sym
                               * (1.0 + CHAMPION_BOOST * flag_aG_high)
                               * phase)

    # ── Continuous tanh strategies ─────────────────────────────────────────────
    # Only applied at A-fire bars; non-A-fire bars get phase = 1.0
    A_fire_float = A_fire_lag1.astype(float)

    for name, (w_g, w_t, steep, rng) in CONT_SPECS.items():
        S      = w_g * G_mem + w_t * T_mem
        midpt  = w_g * G_THRESH + w_t * T_THRESH
        # phase at A-fire
        phase_A = 1.0 + rng * np.tanh(steep * (S - midpt))
        # apply only at A-fire, neutral elsewhere
        phase_all = (phase_A * A_fire_float + 1.0 * (1.0 - A_fire_float)).clip(0.05, 3.0)
        pnl[f'v44_{name}'] = (base * size_sym
                               * (1.0 + CHAMPION_BOOST * flag_aG_high)
                               * phase_all)

    # ── Product interaction strategies ─────────────────────────────────────────
    for name, (lam, w_g, w_t, steep, rng) in PROD_SPECS.items():
        S      = w_g * G_mem + w_t * T_mem + lam * G_mem * T_mem
        midpt  = w_g * G_THRESH + w_t * T_THRESH + lam * G_THRESH * T_THRESH
        phase_A   = 1.0 + rng * np.tanh(steep * (S - midpt))
        phase_all = (phase_A * A_fire_float + 1.0 * (1.0 - A_fire_float)).clip(0.05, 3.0)
        pnl[f'v44_{name}'] = (base * size_sym
                               * (1.0 + CHAMPION_BOOST * flag_aG_high)
                               * phase_all)

    return pnl


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    t_start = time.time()
    BAR = "=" * 100
    print(BAR)
    print("  CRYPTO BSDT v44 — Continuous 2D (G,T) Regime Surface")
    print("  Champion: v43_Troll_N8_thr40  +2.940")
    print("  Causal structure: G↑,T↑ (Stage 1 buildup) → A↑,G↓,T↓ (Stage 2 release)")
    print("  Framework: joint (G_mem, T_mem) state → continuous instability score → sizing")
    print(f"  G_THRESH={G_THRESH}  T_THRESH={T_THRESH}  N_G={N_G}  N_T={N_T}")
    print(BAR)

    # ── 1. Data ─────────────────────────────────────────────────────────────
    print("\n[1] Fetching 1h data ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"  1h DataFrame: {df_1h.index[0]}  →  {df_1h.index[-1]}   "
          f"n={len(df_1h):,} bars  ({(df_1h.index[-1]-df_1h.index[0]).days} days)")
    print(f"  Train: {train_1h.sum():,}   Test: {test_1h.sum():,}   SOL: {has_sol}")
    print(f"  {len(df_1h):,} bars  |  Train: {train_1h.sum():,}  |  Test: {test_1h.sum():,}")

    # ── 2. Funding ───────────────────────────────────────────────────────────
    print("\n[2] Fetching funding ...")
    try:
        funding  = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
        fund_eth = funding.get('ETHUSDT') if isinstance(funding, dict) else None
        fund_btc = funding.get('BTCUSDT') if isinstance(funding, dict) else None
    except Exception:
        fund_eth = fund_btc = None

    # ── 3. State panel ───────────────────────────────────────────────────────
    print("\n[3] Building state panel ...")
    X_panel = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X_panel = np.nan_to_num(X_panel)

    # ── 4a. v36 engine ───────────────────────────────────────────────────────
    train_idx  = np.where(train_1h)[0]
    calib_idx  = train_idx[-CALIB_BARS:]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[calib_idx] = True

    print("\n[4a] Calibrating v36 engine ...")
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(
        X_panel, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)

    # ── 4b. k=1 operator ─────────────────────────────────────────────────────
    X_normal = X_panel[calib_mask]
    print(f"\n[4b] Calibrating k={PCA_K_B} operator ...")
    M_k1 = MasterOperator.calibrate(X_normal, k=PCA_K_B)

    # ── 5. v36 signals ───────────────────────────────────────────────────────
    print(f"\n[5] v36 signals ...")
    sig_v36 = compute_intraday_signals(X_panel, df_1h, M, net, ews, stoch,
                                        e_star, theta)

    # ── 6. v37 price prediction ──────────────────────────────────────────────
    print("\n[6] v37 price prediction ...")
    sig_v37, M_reversal, sigma00_sqrt = compute_price_prediction_signals(
        X_panel, df_1h, M, sig_v36, e_star, sigma_n)

    # ── 7. v38 lambda features ───────────────────────────────────────────────
    print("\n[7] v38 lambda features ...")
    lam_feat = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    # ── 8. Channel means ─────────────────────────────────────────────────────
    print(f"\n[8] Channel means ...")
    mu_norm = calibrate_channel_means(X_panel, calib_mask, M_k1)

    # ── 9. Firing thresholds ─────────────────────────────────────────────────
    print(f"\n[9] Firing thresholds ...")
    fire_thresholds = calibrate_firing_thresholds(X_panel, calib_mask, M_k1,
                                                   pct=FIRE_PERCENTILE)

    # ── 10. Four-channel signals ─────────────────────────────────────────────
    print(f"\n[10] Four-channel signals ...")
    sig_4ch = compute_four_channel_signals_v39b(
        X_panel, df_1h, M_k1, sig_v36, fire_thresholds, mu_norm)

    # ── 2D regime diagnostic ─────────────────────────────────────────────────
    print_2d_regime_diagnostic(sig_4ch, test_1h)

    # ── 11. v34 base portfolio ───────────────────────────────────────────────
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

    # ── 12. Apply v44 sizing ─────────────────────────────────────────────────
    print("\n[12] Applying v44 2D regime sizing ...")
    pnl_dict = apply_v44_sizing(pnl_combined_v34, sig_v36, lam_feat, sig_4ch)
    pnl_dict = {'v34_baseline': pnl_combined_v34, **pnl_dict}

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + BAR)
    print("  GROSS SNAPSHOT  (K=5, 2023 → 2026)")
    print(BAR)
    print_summary_table(pnl_dict, K=5)

    print("\n" + BAR)
    print("  YEAR-ON-YEAR  ($100 start, compounding, gross)")
    print(BAR)
    for name, pnl in pnl_dict.items():
        _yoy_table(name, pnl)

    # ── Save JSON ─────────────────────────────────────────────────────────────
    res_path = OUT_DIR_ / 'crypto_bsdt_v44_2d_regime.json'
    results: dict = {}
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
    sig_summary: dict = {}
    for col in ['a_G', 'a_A', 'a_T', 'a_C']:
        v = sig_s[col].dropna()
        sig_summary[col] = dict(mean=round(float(v.mean()), 6),
                                std=round(float(v.std()), 6),
                                p25=round(float(v.quantile(0.25)), 6),
                                p75=round(float(v.quantile(0.75)), 6),
                                p95=round(float(v.quantile(0.95)), 6))

    # 4-quadrant activation summary
    aG_s = sig_s['a_G']
    aA_s = sig_s['a_A']
    aT_s = sig_s['a_T']
    Gm   = aG_s.rolling(N_G, min_periods=1).max().shift(1).fillna(0.0)
    Tm   = aT_s.rolling(N_T, min_periods=1).max().shift(1).fillna(0.0)
    Af   = (aA_s.shift(1).fillna(0.0) > A_FIRE_THRESH)
    quad_summary = {
        'GH_TH': int((Af & (Gm > G_THRESH) & (Tm > T_THRESH)).sum()),
        'GH_TL': int((Af & (Gm > G_THRESH) & (Tm <= T_THRESH)).sum()),
        'GL_TH': int((Af & (Gm <= G_THRESH) & (Tm > T_THRESH)).sum()),
        'GL_TL': int((Af & (Gm <= G_THRESH) & (Tm <= T_THRESH)).sum()),
        'G_THRESH': G_THRESH,
        'T_THRESH': T_THRESH,
        'N_G': N_G,
        'N_T': N_T,
    }

    with open(res_path, 'w') as f:
        json.dump({
            'strategies':  results,
            'signals':     sig_summary,
            'quadrants':   quad_summary,
            'config': {
                'PCA_K':          PCA_K_B,
                'N_G':            N_G,
                'N_T':            N_T,
                'G_THRESH':       G_THRESH,
                'T_THRESH':       T_THRESH,
                'G_BOOST_THRESH': G_BOOST_THRESH,
                'CHAMPION_BOOST': CHAMPION_BOOST,
                'A_FIRE_THRESH':  A_FIRE_THRESH,
                'V43_CHAMP_COEFFS': list(V43_CHAMP_COEFFS),
                'QUAD_SPECS': {k: list(v) for k, v in QUAD_SPECS.items()},
                'CONT_SPECS': {k: list(v) for k, v in CONT_SPECS.items()},
                'PROD_SPECS': {k: list(v) for k, v in PROD_SPECS.items()},
            },
        }, f, indent=2)
    print(f"\n  Saved → {res_path}")
    print(f"\n  Total runtime: {time.time() - t_start:.0f}s")
    print(BAR)


if __name__ == '__main__':
    main()
