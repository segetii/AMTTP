"""
Crypto BSDT v41 — Decay Memory + Continuous Phase Score + GT Multi-Phase
=========================================================================
Extends v40_phase_N8_gmem045 champion (+2.883) with four targeted improvements.

FEATURE 1 — Exponential decay on G memory  (highest expected impact)
  Problem: rolling_max(N) treats G from 1 bar ago == G from 8 bars ago.
  Fix A — EMA:
    G_mem = EMA(a_G, span=τ).shift(1)      → exponentially weighted average
  Fix B — Decayed max (user formula):
    G_mem = max_{i=1..N}( a_G[t-i] * exp(-(i-1)/τ) )
            freshest bar (t-1) has full weight 1.0; older bars decay by exp

  Sweep: τ ∈ {4, 6, 8, 12, 16}
  Also: EMA(8) threshold sensitivity {0.38, 0.40, 0.42, 0.43, 0.45}
        (EMA averages → smaller values than rolling_max → possibly needs lower threshold)

FEATURE 2 — Continuous sigmoid phase score  (removes discontinuity)
  Hard threshold → G_mem > 0.45 is binary (size jumps at crossing)
  Fix: phase_score = sigmoid(k * (G_mem − 0.45)) ∈ [0, 1]
       phase_scl = 1 + A_fire × (STRUCT_BOOST × ps − RAND_KILL × (1 − ps))
         = 1 + A_fire × (0.60 × ps − 0.40)
  At ps=1.0 (strong G):  scl = 1.20   (same as hard boost, capped)
  At ps=0.5 (at thresh): scl = 0.90   (slightly conservative at uncertainty)
  At ps=0.0 (no G):      scl = 0.60   (same as hard kill)
  Sweep k ∈ {3, 5, 8, 12}  (steepness: gradual → semi-hard)

FEATURE 3 — G → T → A three-level phase
  T is the intermediate phase (Δτ(T→C) median=0 but fire rate = 9.1%, similar to A)
  Three levels conditioned on A-fire:
    strong_struct: G_mem > 0.45 AND T_mem > T_THRESH  → GOOD A (both precursors)
    mod_struct:    G_mem > 0.45 AND T_mem ≤ T_THRESH  → OK A  (G precursor only)
    rand_cascade:  G_mem ≤ 0.45                        → BAD A (no structural context)

FEATURE 4 — ψ/alignment inside phase (diagnostic)
  cos_psi_4ch ≈ 1.000 always in this dataset (std=0.001) → confirmed useless globally
  Test: align_CA column (C↔A jacobian alignment) within struct_release bars
  Expected result: null (align ≈ 0 mean always), included as diagnostic confirmation

Champion baseline: v40_phase_N8_gmem045  +2.883 Sharpe  -13.9% MaxDD  318% CAGR
Previous champion: v39b_aG_boost         +2.762 Sharpe  -14.1% MaxDD  289% CAGR
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

# ── Constants ─────────────────────────────────────────────────────────────────
A_FIRE_THRESH    = 0.70    # a_A threshold (fixed across all versions)
G_CHAMPION_THRESH = 0.45   # v40 champion G_MEM_THRESH
G_BOOST_THRESH   = 0.50    # v39b champion: a_G > 0.50 (point-in-time)
CHAMPION_BOOST   = 0.50    # v39b: size × (1 + 0.50 * (a_G > 0.50))

STRUCT_BOOST_DEF = 0.20    # GOOD A: +20%
RAND_KILL_DEF    = 0.40    # BAD A:  -40%
STRONG_BOOST_GT  = 0.30    # GT strong: G + T both elevated
MOD_BOOST_GT     = 0.10    # GT moderate: G elevated, T not

# Sweep axes
EMA_TAUS          = [4, 6, 8, 12, 16]
EMA8_THRESHOLDS   = [0.38, 0.40, 0.42, 0.43, 0.45]   # sensitivity for EMA tau=8
SIGMOID_K_VALUES  = [3, 5, 8, 12]
DECMAX_CONFIGS    = [(8, 4), (8, 8), (20, 8)]          # (N, tau) pairs

T_MEM_THRESH = 0.38     # GT: T EMA(8) threshold (above mean 0.355)


# ═══════════════════════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def sigmoid(x: np.ndarray | pd.Series) -> np.ndarray | pd.Series:
    """Numerically stable sigmoid."""
    x_clip = np.clip(x, -20.0, 20.0)
    return 1.0 / (1.0 + np.exp(-x_clip))


def rolling_decayed_max(series: pd.Series, N: int, tau: float) -> pd.Series:
    """
    Decayed max (user formula, no lookahead):
      G_mem[t] = max_{i=1..N}( a_G[t-i] * exp(-(i-1)/tau) )
               = max of (a_G[t-1]*1, a_G[t-2]*exp(-1/tau), ..., a_G[t-N]*exp(-(N-1)/tau))

    Freshest observation (t-1) carries full weight 1.0.
    Older observations decay exponentially with timescale tau.
    Bars 0..N-1 are left at 0.0 (insufficient history).
    """
    arr  = series.values.astype(float)
    T    = len(arr)
    # decay[0] = 1.0 (bar t-1), decay[1] = exp(-1/tau) (bar t-2), ...
    decay = np.exp(-np.arange(N) / tau)
    out  = np.zeros(T)
    for t in range(N, T):
        window = arr[t - N : t][::-1]   # [arr[t-1], arr[t-2], ..., arr[t-N]]
        out[t] = float(np.max(window * decay))
    return pd.Series(out, index=series.index)


# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE-DECAY DIAGNOSTIC
# ═══════════════════════════════════════════════════════════════════════════════

def print_phase_decay_diagnostic(sig_4ch: pd.DataFrame, test_mask) -> None:
    """
    Compare rolling_max vs EMA vs decayed_max memory mechanisms.
    Print struct_release rates and G_mem distribution at A-fire bars for each.
    """
    s    = sig_4ch[test_mask]
    aG   = s['a_G']
    aA   = s['a_A']
    N    = len(s)

    A_fire  = (aA > A_FIRE_THRESH)
    n_Afire = int(A_fire.sum())

    print(f"\n  Phase-Decay Diagnostic  (test {N:,} bars,  A-fire: {n_Afire} = {n_Afire/N*100:.2f}%)")
    print(f"  threshold = {G_CHAMPION_THRESH:.2f}  (v40 champion G_MEM_THRESH)")
    print(f"\n  {'Memory mechanism':<30}  {'struct%':>8}  {'rand%':>7}  "
          f"{'mem_p50@A':>11}  {'mem_p90@A':>11}  {'% of A-fires struct':>20}")
    print(f"  {'-'*30}  {'-'*8}  {'-'*7}  {'-'*11}  {'-'*11}  {'-'*20}")

    # v40 champion reference (rolling_max N=8, threshold 0.45)
    G_rmax8 = aG.rolling(8, min_periods=1).max().shift(1).fillna(0.0)
    _print_mem_row("v40_rollmax(N=8)", G_rmax8, A_fire, G_CHAMPION_THRESH, N, n_Afire)

    # EMA sweep
    for tau in EMA_TAUS:
        G_ema = aG.ewm(span=tau, adjust=False).mean().shift(1).fillna(0.0)
        _print_mem_row(f"EMA(tau={tau})", G_ema, A_fire, G_CHAMPION_THRESH, N, n_Afire)

    # Decayed max configs
    for N_dm, tau_dm in DECMAX_CONFIGS:
        G_dm = rolling_decayed_max(aG, N=N_dm, tau=float(tau_dm))
        _print_mem_row(f"decmax(N={N_dm},τ={tau_dm})", G_dm, A_fire, G_CHAMPION_THRESH, N, n_Afire)

    # EMA(8) threshold sensitivity
    print(f"\n  EMA(tau=8) threshold sensitivity:")
    G_ema8 = aG.ewm(span=8, adjust=False).mean().shift(1).fillna(0.0)
    for thr in EMA8_THRESHOLDS:
        _print_mem_row(f"  EMA8 thr={thr:.2f}", G_ema8, A_fire, thr, N, n_Afire)

    # Sigmoid phase score stats at A-fire with EMA(8)
    G_ema8_nolag = aG.ewm(span=8, adjust=False).mean().shift(1).fillna(0.0)
    print(f"\n  Sigmoid phase_score = sigmoid(k × (EMA8 − 0.45)) at A-fire bars:")
    print(f"  {'k':>5}  {'ps_mean@A':>11}  {'ps_p25@A':>10}  {'ps_p50@A':>10}  {'ps_p75@A':>10}")
    for k in SIGMOID_K_VALUES:
        ps = sigmoid(k * (G_ema8_nolag[A_fire] - 0.45))
        print(f"  {k:>5}  {float(ps.mean()):>11.3f}  {float(ps.quantile(0.25)):>10.3f}  "
              f"{float(ps.median()):>10.3f}  {float(ps.quantile(0.75)):>10.3f}")

    # GT: T_mem distribution at A-fire
    aT = s['a_T']
    T_ema8 = aT.ewm(span=8, adjust=False).mean().shift(1).fillna(0.0)
    T_at_A = T_ema8[A_fire]
    G_at_A = G_ema8_nolag[A_fire]
    print(f"\n  GT diagnostic at A-fire bars:")
    print(f"  G_mem(EMA8) p50={float(G_at_A.median()):.3f}  p75={float(G_at_A.quantile(0.75)):.3f}")
    print(f"  T_mem(EMA8) p50={float(T_at_A.median()):.3f}  p75={float(T_at_A.quantile(0.75)):.3f}")
    G_high = (G_at_A > G_CHAMPION_THRESH)
    T_high = (T_at_A > T_MEM_THRESH)
    n_strong = int((G_high & T_high).sum())
    n_mod    = int((G_high & ~T_high).sum())
    n_rand   = int((~G_high).sum())
    print(f"  strong_struct (G>{G_CHAMPION_THRESH} & T>{T_MEM_THRESH}): "
          f"{n_strong} ({n_strong/n_Afire*100:.1f}% of A-fires)")
    print(f"  mod_struct    (G>{G_CHAMPION_THRESH} & T≤{T_MEM_THRESH}): "
          f"{n_mod} ({n_mod/n_Afire*100:.1f}% of A-fires)")
    print(f"  rand_cascade  (G≤{G_CHAMPION_THRESH}):                    "
          f"{n_rand} ({n_rand/n_Afire*100:.1f}% of A-fires)")

    # ψ diagnostic
    if 'align_CA' in s.columns:
        alCA = s['align_CA'].shift(1).fillna(0.0)
        print(f"\n  Feature 4 (ψ/alignment) diagnostic:")
        print(f"  align_CA global: mean={float(alCA.mean()):.4f}  std={float(alCA.std()):.4f}  "
              f"abs_mean={float(alCA.abs().mean()):.4f}")
        alCA_at_A = alCA[A_fire]
        print(f"  align_CA at A-fire: mean={float(alCA_at_A.mean()):.4f}  "
              f"std={float(alCA_at_A.std()):.4f}")
        if float(alCA.abs().mean()) < 0.01:
            print(f"  → CONFIRMED NULL: channel jacobians are geometrically orthogonal.")
            print(f"     Feature 4 (ψ inside phase) will not improve performance.")


def _print_mem_row(label, G_mem, A_fire, threshold, N, n_Afire):
    struct = A_fire & (G_mem > threshold)
    rand   = A_fire & (G_mem <= threshold)
    n_st = int(struct.sum()); n_rd = int(rand.sum())
    mem_at_A = G_mem[A_fire]
    p50 = float(mem_at_A.median()) if len(mem_at_A) > 0 else 0.0
    p90 = float(mem_at_A.quantile(0.90)) if len(mem_at_A) > 0 else 0.0
    pct_st = n_st / n_Afire * 100 if n_Afire > 0 else 0.0
    print(f"  {label:<30}  {n_st/N*100:>7.2f}%  {n_rd/N*100:>6.2f}%  "
          f"{p50:>11.4f}  {p90:>11.4f}  {pct_st:>19.1f}%")


# ═══════════════════════════════════════════════════════════════════════════════
#  V41 SIZING
# ═══════════════════════════════════════════════════════════════════════════════

def apply_v41_sizing(base_pnl: pd.Series,
                     sig_v36:  pd.DataFrame,
                     lam_feat: pd.DataFrame,
                     sig_4ch:  pd.DataFrame) -> dict[str, pd.Series]:
    """
    v41: Decay memory + continuous sigmoid + GT multi-phase.
    All signals lag-1 compliant (no lookahead).
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

    # Raw unshifted channels (shift applied inside each variant)
    a_G_raw  = s4['a_G']
    a_A_raw  = s4['a_A']
    a_T_raw  = s4['a_T']

    # Champion G-boost flag (lag-1, point-in-time)
    a_G_1 = a_G_raw.shift(1).fillna(0.0)
    a_A_1 = a_A_raw.shift(1).fillna(0.0)
    flag_aG    = (a_G_1 > G_BOOST_THRESH).astype(float)
    A_fire_1   = a_A_1 > A_FIRE_THRESH

    pnl = {}

    # ── Reference baselines ───────────────────────────────────────────────────
    pnl['v39b_aG_boost']   = base * size_sym * (1.0 + CHAMPION_BOOST * flag_aG)

    # v40 champion (rolling_max N=8, threshold 0.45) for direct comparison
    G_rmax8 = a_G_raw.rolling(8, min_periods=1).max().shift(1).fillna(0.0)
    sr_ch = (A_fire_1 & (G_rmax8 > G_CHAMPION_THRESH)).astype(float)
    rc_ch = (A_fire_1 & (G_rmax8 <= G_CHAMPION_THRESH)).astype(float)
    pscl_ch = (1.0 + STRUCT_BOOST_DEF * sr_ch - RAND_KILL_DEF * rc_ch).clip(0.05, 3.0)
    pnl['v40_champion_ref']= base * size_sym * (1.0 + CHAMPION_BOOST * flag_aG) * pscl_ch

    # ── FEATURE 1A: EMA decay sweep ───────────────────────────────────────────
    for tau in EMA_TAUS:
        G_ema = a_G_raw.ewm(span=tau, adjust=False).mean().shift(1).fillna(0.0)
        sr    = (A_fire_1 & (G_ema > G_CHAMPION_THRESH)).astype(float)
        rc    = (A_fire_1 & (G_ema <= G_CHAMPION_THRESH)).astype(float)
        pscl  = (1.0 + STRUCT_BOOST_DEF * sr - RAND_KILL_DEF * rc).clip(0.05, 3.0)
        pnl[f'v41_ema_tau{tau}'] = (base * size_sym
                                     * (1.0 + CHAMPION_BOOST * flag_aG) * pscl)

    # ── FEATURE 1A extra: EMA(8) threshold sensitivity ───────────────────────
    G_ema8 = a_G_raw.ewm(span=8, adjust=False).mean().shift(1).fillna(0.0)
    for thr_str, thr in [('038', 0.38), ('040', 0.40), ('042', 0.42), ('043', 0.43)]:
        # 0.45 already covered by v41_ema_tau8
        sr  = (A_fire_1 & (G_ema8 > thr)).astype(float)
        rc  = (A_fire_1 & (G_ema8 <= thr)).astype(float)
        pscl = (1.0 + STRUCT_BOOST_DEF * sr - RAND_KILL_DEF * rc).clip(0.05, 3.0)
        pnl[f'v41_ema8_thr{thr_str}'] = (base * size_sym
                                          * (1.0 + CHAMPION_BOOST * flag_aG) * pscl)

    # ── FEATURE 1B: Decayed max sweep ────────────────────────────────────────
    for N_dm, tau_dm in DECMAX_CONFIGS:
        G_dm = rolling_decayed_max(a_G_raw, N=N_dm, tau=float(tau_dm))
        sr   = (A_fire_1 & (G_dm > G_CHAMPION_THRESH)).astype(float)
        rc   = (A_fire_1 & (G_dm <= G_CHAMPION_THRESH)).astype(float)
        pscl = (1.0 + STRUCT_BOOST_DEF * sr - RAND_KILL_DEF * rc).clip(0.05, 3.0)
        pnl[f'v41_decmax_N{N_dm}_tau{tau_dm}'] = (base * size_sym
                                                    * (1.0 + CHAMPION_BOOST * flag_aG)
                                                    * pscl)

    # ── FEATURE 2: Continuous sigmoid phase score ────────────────────────────
    # Base: EMA(8) for G memory; sweep steepness k
    for k in SIGMOID_K_VALUES:
        ps    = sigmoid(k * (G_ema8 - G_CHAMPION_THRESH))   # ∈ [0, 1]
        # phase_scl = 1 + A_fire × (0.60 × ps − 0.40)
        #   → ps=1.0: 1.20  (same as hard struct)
        #   → ps=0.5: 0.90  (neutral/uncertain)
        #   → ps=0.0: 0.60  (same as hard rand)
        pscl_sig = (1.0
                    + A_fire_1.astype(float)
                    * ((STRUCT_BOOST_DEF + RAND_KILL_DEF) * ps - RAND_KILL_DEF)
                    ).clip(0.05, 3.0)
        pnl[f'v41_sig_k{k}_ema8'] = (base * size_sym
                                       * (1.0 + CHAMPION_BOOST * flag_aG) * pscl_sig)

    # Best sigmoid on decayed_max(N=8, tau=4) — peak-sensitive decay
    G_dm84 = rolling_decayed_max(a_G_raw, N=8, tau=4.0)
    for k in [5, 8]:
        ps    = sigmoid(k * (G_dm84 - G_CHAMPION_THRESH))
        pscl_sig = (1.0
                    + A_fire_1.astype(float)
                    * ((STRUCT_BOOST_DEF + RAND_KILL_DEF) * ps - RAND_KILL_DEF)
                    ).clip(0.05, 3.0)
        pnl[f'v41_sig_k{k}_decmax84'] = (base * size_sym
                                           * (1.0 + CHAMPION_BOOST * flag_aG)
                                           * pscl_sig)

    # ── FEATURE 3: GT multi-phase (3 levels) ─────────────────────────────────
    # T_mem uses same EMA(8) as G_mem for consistency
    T_ema8 = a_T_raw.ewm(span=8, adjust=False).mean().shift(1).fillna(0.0)

    strong_struct = (A_fire_1 & (G_ema8 > G_CHAMPION_THRESH) & (T_ema8 > T_MEM_THRESH)).astype(float)
    mod_struct    = (A_fire_1 & (G_ema8 > G_CHAMPION_THRESH) & (T_ema8 <= T_MEM_THRESH)).astype(float)
    rand_cascade  = (A_fire_1 & (G_ema8 <= G_CHAMPION_THRESH)).astype(float)

    pscl_gt = (1.0
               + STRONG_BOOST_GT * strong_struct
               + MOD_BOOST_GT    * mod_struct
               - RAND_KILL_DEF   * rand_cascade).clip(0.05, 3.0)
    pnl['v41_GT_ema8'] = (base * size_sym
                           * (1.0 + CHAMPION_BOOST * flag_aG) * pscl_gt)

    # GT with decayed_max memory
    G_dm88 = rolling_decayed_max(a_G_raw, N=8, tau=8.0)
    T_dm88 = rolling_decayed_max(a_T_raw, N=8, tau=8.0)

    ss_dm  = (A_fire_1 & (G_dm88 > G_CHAMPION_THRESH) & (T_dm88 > T_MEM_THRESH)).astype(float)
    ms_dm  = (A_fire_1 & (G_dm88 > G_CHAMPION_THRESH) & (T_dm88 <= T_MEM_THRESH)).astype(float)
    rc_dm  = (A_fire_1 & (G_dm88 <= G_CHAMPION_THRESH)).astype(float)

    pscl_gt_dm = (1.0
                  + STRONG_BOOST_GT * ss_dm
                  + MOD_BOOST_GT    * ms_dm
                  - RAND_KILL_DEF   * rc_dm).clip(0.05, 3.0)
    pnl['v41_GT_decmax88'] = (base * size_sym
                               * (1.0 + CHAMPION_BOOST * flag_aG) * pscl_gt_dm)

    # GT with sigmoid (strong/rand split using phase scores for G and T)
    ps_G = sigmoid(8 * (G_ema8 - G_CHAMPION_THRESH))
    ps_T = sigmoid(8 * (T_ema8 - T_MEM_THRESH))
    # Combined phase score: geometric mean → 1 only if both are high
    ps_GT = ps_G * ps_T
    # Use GT score when A fires; fallback to G-only score otherwise
    ps_combined = A_fire_1.astype(float) * ps_GT + (1 - A_fire_1.astype(float)) * 0.5
    pscl_GT_sig = (1.0
                   + A_fire_1.astype(float)
                   * ((STRONG_BOOST_GT + RAND_KILL_DEF) * ps_GT - RAND_KILL_DEF)
                   ).clip(0.05, 3.0)
    pnl['v41_GT_sigmoid_k8'] = (base * size_sym
                                  * (1.0 + CHAMPION_BOOST * flag_aG) * pscl_GT_sig)

    # ── FEATURE 4 (diagnostic): ψ alignment inside phase ─────────────────────
    # cos_psi_4ch ≈ 1.0 always → expected null result
    # align_CA measures C↔A jacobian alignment: expected ≈ 0 always
    if 'align_CA' in s4.columns:
        alCA = s4['align_CA'].shift(1).fillna(0.0)
        # Use alignment as additional discriminator within struct_release
        struct_aligned    = (A_fire_1 & (G_ema8 > G_CHAMPION_THRESH) & (alCA > 0.05)).astype(float)
        struct_misaligned = (A_fire_1 & (G_ema8 > G_CHAMPION_THRESH) & (alCA <= 0.05)).astype(float)
        rc_psi = (A_fire_1 & (G_ema8 <= G_CHAMPION_THRESH)).astype(float)
        pscl_psi = (1.0
                    + (STRUCT_BOOST_DEF + 0.10) * struct_aligned
                    + STRUCT_BOOST_DEF            * struct_misaligned
                    - RAND_KILL_DEF               * rc_psi).clip(0.05, 3.0)
        pnl['v41_psi_phase_diag'] = (base * size_sym
                                      * (1.0 + CHAMPION_BOOST * flag_aG) * pscl_psi)

    # ── Combined best candidates ──────────────────────────────────────────────
    # Best overall guess: decayed_max(N=8, tau=4) + sigmoid k=8 + GT multi-phase
    G_dm84_c = rolling_decayed_max(a_G_raw, N=8, tau=4.0)
    T_dm84_c = rolling_decayed_max(a_T_raw, N=8, tau=4.0)
    ps_G_c = sigmoid(8 * (G_dm84_c - G_CHAMPION_THRESH))
    ps_T_c = sigmoid(8 * (T_dm84_c - T_MEM_THRESH))
    ps_GT_c = ps_G_c * ps_T_c  # both precursors must be elevated
    pscl_comb = (1.0
                 + A_fire_1.astype(float)
                 * ((STRONG_BOOST_GT + RAND_KILL_DEF) * ps_GT_c - RAND_KILL_DEF)
                 ).clip(0.05, 3.0)
    pnl['v41_combined_decmax84_sig8_GT'] = (base * size_sym
                                             * (1.0 + CHAMPION_BOOST * flag_aG) * pscl_comb)

    # Softer version of combined — less aggressive kill
    pscl_soft = (1.0
                 + A_fire_1.astype(float)
                 * ((STRONG_BOOST_GT + 0.25) * ps_GT_c - 0.25)
                 ).clip(0.05, 3.0)
    pnl['v41_combined_decmax84_sig8_GT_soft'] = (base * size_sym
                                                   * (1.0 + CHAMPION_BOOST * flag_aG)
                                                   * pscl_soft)

    return pnl


# ═══════════════════════════════════════════════════════════════════════════════
#  PRINT SIZING ACTIVATION RATES
# ═══════════════════════════════════════════════════════════════════════════════

def print_v41_activation_rates(sig_4ch: pd.DataFrame, test_mask) -> None:
    """Print key activation rates for the main v41 variants."""
    s   = sig_4ch[test_mask]
    aG  = s['a_G']
    aA  = s['a_A']
    N   = len(s)
    A_f = aA > A_FIRE_THRESH
    n_A = int(A_f.sum())

    G_ema8 = aG.ewm(span=8, adjust=False).mean().shift(1).fillna(0.0)
    G_dm84 = rolling_decayed_max(aG, N=8, tau=4.0)

    print(f"\n  Activation rates summary (test {N:,} bars, {n_A} A-fires):")
    print(f"  EMA(8)  > 0.45 at A-fire: {int((A_f & (G_ema8 > 0.45)).sum()):>4} struct  "
          f"({int((A_f & (G_ema8 > 0.45)).sum())/n_A*100:.1f}% of A-fires)")
    print(f"  EMA(8)  > 0.42 at A-fire: {int((A_f & (G_ema8 > 0.42)).sum()):>4} struct  "
          f"({int((A_f & (G_ema8 > 0.42)).sum())/n_A*100:.1f}% of A-fires)")
    print(f"  decmax(N=8,τ=4) > 0.45 at A-fire: {int((A_f & (G_dm84 > 0.45)).sum()):>4} struct  "
          f"({int((A_f & (G_dm84 > 0.45)).sum())/n_A*100:.1f}% of A-fires)")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    t_start = time.time()
    BAR = "=" * 100
    print(BAR)
    print("  CRYPTO BSDT v41 — Decay Memory + Sigmoid Phase + GT Multi-Phase")
    print("  Feature 1: EMA decay / decayed_max  (fresh stress > stale stress)")
    print("  Feature 2: Sigmoid phase_score      (continuous, removes discontinuity)")
    print("  Feature 3: G → T → A 3-level phase  (both precursors = strong release)")
    print("  Feature 4: ψ inside phase (diagnostic — expected null)")
    print("  v40 champion: v40_phase_N8_gmem045  +2.883  MaxDD -13.9%  CAGR 318%")
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

    # ── 4b. k=1 operator ──────────────────────────────────────────────────────
    X_normal = X_panel[calib_mask]
    print(f"\n[4b] Calibrating k={PCA_K_B} operator ...")
    M_k1 = MasterOperator.calibrate(X_normal, k=PCA_K_B)

    # ── 5-7. Signal chain ─────────────────────────────────────────────────────
    print(f"\n[5] Computing v36 signals ...")
    sig_v36 = compute_intraday_signals(X_panel, df_1h, M, net, ews, stoch,
                                        e_star, theta)
    print("\n[6] Computing v37 price prediction ...")
    sig_v37, M_reversal, sigma00_sqrt = compute_price_prediction_signals(
        X_panel, df_1h, M, sig_v36, e_star, sigma_n)
    print("\n[7] Computing v38 lambda features ...")
    lam_feat = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    # ── 8-9. Calibration ──────────────────────────────────────────────────────
    print(f"\n[8] Calibrating channel means (k={PCA_K_B}) ...")
    mu_norm = calibrate_channel_means(X_panel, calib_mask, M_k1)
    print(f"\n[9] Calibrating firing thresholds ...")
    fire_thresholds = calibrate_firing_thresholds(X_panel, calib_mask, M_k1,
                                                   pct=FIRE_PERCENTILE)

    # ── 10. Four-channel signals ───────────────────────────────────────────────
    print(f"\n[10] Computing four-channel signals ...")
    sig_4ch = compute_four_channel_signals_v39b(
        X_panel, df_1h, M_k1, sig_v36, fire_thresholds, mu_norm)
    print(f"  Signals: {len(sig_4ch.columns)} columns")

    # ── Phase-decay diagnostics ────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("  PHASE-DECAY DIAGNOSTICS")
    print("=" * 100)
    print_transmission_lag_analysis(sig_4ch, test_1h)
    print_phase_decay_diagnostic(sig_4ch, test_1h)
    print_v41_activation_rates(sig_4ch, test_1h)

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

    # ── 12. Sizing ─────────────────────────────────────────────────────────────
    print("\n[12] Applying v41 sizing ...")
    pnl_dict = apply_v41_sizing(pnl_combined_v34, sig_v36, lam_feat, sig_4ch)
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
    res_path = OUT_DIR_ / 'crypto_bsdt_v41_decay_phase.json'
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

    with open(res_path, 'w') as f:
        json.dump({
            'strategies': results,
            'signals':    sig_summary,
            'config': {
                'PCA_K':          PCA_K_B,
                'A_FIRE_THRESH':  A_FIRE_THRESH,
                'G_CHAMPION_THRESH': G_CHAMPION_THRESH,
                'CHAMPION_BOOST': CHAMPION_BOOST,
                'STRUCT_BOOST':   STRUCT_BOOST_DEF,
                'RAND_KILL':      RAND_KILL_DEF,
                'STRONG_BOOST_GT': STRONG_BOOST_GT,
                'MOD_BOOST_GT':   MOD_BOOST_GT,
                'T_MEM_THRESH':   T_MEM_THRESH,
                'EMA_TAUS':       EMA_TAUS,
                'DECMAX_CONFIGS': DECMAX_CONFIGS,
                'SIGMOID_K_VALUES': SIGMOID_K_VALUES,
            },
        }, f, indent=2)
    print(f"\n  Saved → {res_path}")
    print(f"\n  Total runtime: {time.time() - t_start:.0f}s")
    print("=" * 100)


if __name__ == '__main__':
    main()
