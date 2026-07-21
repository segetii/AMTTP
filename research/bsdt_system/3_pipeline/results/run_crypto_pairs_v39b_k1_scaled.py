"""
Crypto BSDT v39b — k=1 PCA + Per-Channel Mean Normalization
=============================================================
Two targeted fixes based on run_crypto_diag_delta_g.py diagnostic:

FIX 1 — PCA_K = 1  (was 4)
  With k=4: I − V_kV_kᵀ projects onto 0.029% residual → S_G ≈ 0.005
  With k=1: projector captures 40.2% residual → S_G rises 1393× to ~7.4
  Root cause confirmed: k=4 over-fits the 2D feature space (cumvar 99.97%)

FIX 2 — Per-channel mean normalization
  S̃_k = S_k / μ_k^normal  (μ_k = mean of S_k over calibration window)
  Purpose: makes attribution relative to normal-period baseline.
  Without normalization: a_G = S_G² / ‖S‖² is a raw scale race (S_G << S_T forever)
  With normalization: a_G = S̃_G² / ‖S̃‖²  — each channel contributes ~0.25 in
  normal conditions; deviations above the normal mean drive attribution up.
  This is the correct interpretation: "how much is this channel above its normal level?"

ATTRIBUTION FORMULA (CONFIRMED):
  g = 2·A·S̃  with A=I₄ (pure_mahalanobis mode) → g = 2·S̃
  a_k = [g]_k² / ‖g‖² = S̃_k² / ‖S̃‖²

NEW STRATEGIES vs v39:
  v39b_base      : v38_sym_W100 with k=1 (isolates effect of k change)
  v39b_aG_gate   : base × 𝟙[a_G < 0.35]  (exit when novel stress > 35% of attribution)
  v39b_aG_boost  : base × (1 + 0.5·𝟙[a_G > 0.50]) (boost when G dominates — novel regime)
  v39b_psi_gate  : base × max(0, cos_ψ_4ch)  (zero when gradient channels oppose)
  v39b_full      : base × 𝟙[a_G<0.35] × boost_T  [PRIMARY combined]
  v39b_anti_G    : base × 𝟙[a_G < 0.20] × 𝟙[a_A < 0.20] × boost_T  (tight)

All built on v38_sym_W100 base with lag-1 all signals.

Usage:
    cd C:\\amttp\\research\\adaptive-friction\\pipeline\\results
    py -3 run_crypto_pairs_v39b_k1_scaled.py
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

from collapse_geometry import MasterOperator, Snapshot, LedoitWolfNetwork, InformationGeometry
from run_crypto_pairs_v38_lambda_norm import compute_lambda_features
from run_crypto_pairs_v37_price_prediction import compute_price_prediction_signals
from run_crypto_pairs_v36_intraday_bsdt import (
    N_AGENTS, N_FEATURES, CALIB_BARS, ALPHA_CONF,
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
    FIRE_PERCENTILE, PSI_FLOOR,
    calibrate_firing_thresholds,
    print_transmission_lag_analysis,
    print_summary_table, _yoy_table,
)

OUT_DIR_ = Path(OUT_DIR)
N = N_AGENTS    # 8
D = N_FEATURES  # 8

# ── THE KEY FIX ──────────────────────────────────────────────────────────────
PCA_K_B = 1    # was 4 in v36/v39 — diagnostic shows k=4 leaves 0.029% residual

# Strategy sizing thresholds — tuned for normalized attribution (a_k ≈ 0.25 normal)
GATE_A_G   = 0.35   # exit when novel-stress attribution > 35% (above normal ~0.25)
GATE_A_G_T = 0.50   # tight exit threshold
BOOST_A_T  = 0.40   # boost at regime transition (a_T > 40% = T dominant)
BOOST_A_G  = 0.50   # boost at novel structural stress (a_G > 50%)
MU_FLOOR   = 1e-6   # floor for mean normalization denominator


# ═══════════════════════════════════════════════════════════════════════════
#  CALIBRATE CHANNEL MEANS  (for normalization)
# ═══════════════════════════════════════════════════════════════════════════

def calibrate_channel_means(X_panel: np.ndarray,
                             calib_mask: np.ndarray,
                             M) -> np.ndarray:
    """
    Compute per-channel mean of S_k = Σ_i δ_k^(i) over the calibration window.

    Returns
    -------
    mu_norm : (4,) mean [mu_C, mu_G, mu_A, mu_T] over normal period
    """
    bsdt   = M.bsdt
    X_c    = X_panel[calib_mask]
    T0     = len(X_c)
    S_list = []
    for t in range(1, T0):
        snap = Snapshot(X=X_c[t], X_prev=X_c[t-1],
                        history=X_c[max(0, t - 20):t])
        try:
            S_list.append(bsdt.channel_state(snap))
        except Exception:
            pass
    S_arr   = np.array(S_list)   # (T0-1, 4)
    mu_norm = np.maximum(np.mean(S_arr, axis=0), MU_FLOOR)
    std_norm = np.std(S_arr, axis=0)
    print(f"  [v39b] Channel means (μ_k^normal):")
    for k, name in CH_NAMES.items():
        print(f"    {name}: μ={mu_norm[k]:.5f}  σ={std_norm[k]:.5f}  "
              f"σ/μ={std_norm[k]/mu_norm[k]:.3f}")
    return mu_norm


# ═══════════════════════════════════════════════════════════════════════════
#  FOUR-CHANNEL SWEEP  (with per-channel mean normalization)
# ═══════════════════════════════════════════════════════════════════════════

def compute_four_channel_signals_v39b(X_panel: np.ndarray,
                                       df_1h:   pd.DataFrame,
                                       M,
                                       sig_v36: pd.DataFrame,
                                       fire_thresholds: np.ndarray,
                                       mu_norm: np.ndarray) -> pd.DataFrame:
    """
    Four-channel sweep with FIX 1 (k=1) + FIX 2 (mean normalization).

    Normalization: S̃_k = S_k / μ_k^normal
      - In normal conditions: S̃_k ≈ 1  for each channel
      - During stress: S̃_k >> 1  for channels that are firing above normal
    Attribution: a_k = S̃_k² / ‖S̃‖²
      - In normal: ≈ equal weight (0.25 each for active channels)
      - During novel stress: a_G rises when S_G / μ_G exceeds other channels' ratios

    Jacobians are NOT normalized — they operate in the raw feature space.
    """
    T    = len(X_panel)
    bsdt = M.bsdt
    E    = M.energy

    keys = [
        'e_C', 'e_G', 'e_A', 'e_T',        # raw channel energies
        'S_norm_C', 'S_norm_G',              # normalized channel states (diagnostic)
        'S_norm_A', 'S_norm_T',
        'a_C', 'a_G', 'a_A', 'a_T',        # normalized attribution
        'a_G_raw',                            # raw (unnormalized) a_G for comparison
        'dom_energy',
        'G_norm_C', 'G_norm_G', 'G_norm_A', 'G_norm_T', 'G_norm_4ch',
        'cos_psi_4ch', 'R_t_4ch',
        'fire_C', 'fire_G', 'fire_A', 'fire_T',
        'align_CG', 'align_CA', 'align_CT',
    ]
    buf = {k: np.full(T, np.nan) for k in keys}

    t0 = time.time()
    for t in range(2, T):
        snap = Snapshot(X=X_panel[t], X_prev=X_panel[t - 1],
                        history=X_panel[max(0, t - 20):t])
        try:
            # ── Raw channel-state ─────────────────────────────────────
            S = bsdt.channel_state(snap)   # (4,)
            buf['e_C'][t] = S[CH_C]
            buf['e_G'][t] = S[CH_G]
            buf['e_A'][t] = S[CH_A]
            buf['e_T'][t] = S[CH_T]

            # ── FIX 2: mean-normalized channel state ──────────────────
            # S̃_k = S_k / μ_k^normal   (μ_k from calibration window)
            S_norm = S / mu_norm
            buf['S_norm_C'][t] = S_norm[CH_C]
            buf['S_norm_G'][t] = S_norm[CH_G]
            buf['S_norm_A'][t] = S_norm[CH_A]
            buf['S_norm_T'][t] = S_norm[CH_T]

            # ── Attribution from normalized S̃ ─────────────────────────
            a = E.channel_attribution(S_norm)    # a_k = S̃_k² / ‖S̃‖²
            buf['a_C'][t] = a[CH_C]
            buf['a_G'][t] = a[CH_G]
            buf['a_A'][t] = a[CH_A]
            buf['a_T'][t] = a[CH_T]
            buf['dom_energy'][t] = float(E.dominant_channel(S_norm))

            # Raw a_G for comparison diagnostic
            a_raw = E.channel_attribution(S)
            buf['a_G_raw'][t] = a_raw[CH_G]

            # ── Jacobians (unnormalized feature space) ─────────────────
            jac = bsdt.jacobians(snap)
            jC, jG, jA, jT = jac['C'], jac['G'], jac['A'], jac['T']
            nC = float(np.linalg.norm(jC, 'fro'))
            nG = float(np.linalg.norm(jG, 'fro'))
            buf['G_norm_C'][t] = nC
            buf['G_norm_G'][t] = nG
            buf['G_norm_A'][t] = float(np.linalg.norm(jA, 'fro'))
            buf['G_norm_T'][t] = float(np.linalg.norm(jT, 'fro'))

            # ── Composite gradient (attribution-weighted jacobian sum) ─
            G4 = a[CH_C] * jC + a[CH_G] * jG + a[CH_A] * jA + a[CH_T] * jT
            n4 = float(np.linalg.norm(G4, 'fro'))
            buf['G_norm_4ch'][t] = n4

            if n4 > 1e-12 and nC > 1e-12:
                buf['cos_psi_4ch'][t] = float(np.clip(np.sum(G4 * jC) / (n4 * nC), -1.0, 1.0))
            else:
                buf['cos_psi_4ch'][t] = 1.0
            buf['R_t_4ch'][t] = n4 ** 2 / max(nC ** 2, 1e-12)

            # ── Cross-channel jacobian alignment ──────────────────────
            def _cos(J1, J2):
                n1 = np.linalg.norm(J1, 'fro')
                n2 = np.linalg.norm(J2, 'fro')
                if n1 < 1e-12 or n2 < 1e-12:
                    return 0.0
                return float(np.sum(J1 * J2)) / (n1 * n2)

            buf['align_CG'][t] = _cos(jC, jG)
            buf['align_CA'][t] = _cos(jC, jA)
            buf['align_CT'][t] = _cos(jC, jT)

            # ── Firing thresholds (raw S, not normalized) ─────────────
            buf['fire_C'][t] = float(S[CH_C] > fire_thresholds[CH_C])
            buf['fire_G'][t] = float(S[CH_G] > fire_thresholds[CH_G])
            buf['fire_A'][t] = float(S[CH_A] > fire_thresholds[CH_A])
            buf['fire_T'][t] = float(S[CH_T] > fire_thresholds[CH_T])

        except Exception:
            pass

        if t % 5000 == 0:
            print(f"    {t}/{T}  ({time.time() - t0:.1f}s)")

    print(f"  [v39b] Sweep: {T:,} bars in {time.time() - t0:.1f}s")

    idx = df_1h.index
    def _ff(arr, fill=0.0):
        return pd.Series(arr, index=idx).ffill().fillna(fill)

    df = pd.DataFrame({k: _ff(buf[k]) for k in keys}, index=idx)

    # ── Firing sequence ───────────────────────────────────────────────
    fire_C_v = df['fire_C'].values.astype(bool)
    fire_G_v = df['fire_G'].values.astype(bool)
    fire_A_v = df['fire_A'].values.astype(bool)
    fire_T_v = df['fire_T'].values.astype(bool)
    dt_CG = np.full(T, np.nan)
    dt_CA = np.full(T, np.nan)
    dt_CT = np.full(T, np.nan)
    last_G = last_A = last_T = -1
    for t in range(T):
        if fire_G_v[t]: last_G = t
        if fire_A_v[t]: last_A = t
        if fire_T_v[t]: last_T = t
        if fire_C_v[t]:
            if last_G >= 0: dt_CG[t] = t - last_G
            if last_A >= 0: dt_CA[t] = t - last_A
            if last_T >= 0: dt_CT[t] = t - last_T
    df['dt_CG'] = dt_CG
    df['dt_CA'] = dt_CA
    df['dt_CT'] = dt_CT
    return df


# ═══════════════════════════════════════════════════════════════════════════
#  V39b SIZING STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════

def apply_v39b_sizing(base_pnl: pd.Series,
                      sig_v36:  pd.DataFrame,
                      lam_feat: pd.DataFrame,
                      sig_4ch:  pd.DataFrame) -> dict[str, pd.Series]:
    """
    v39b strategy variants. All use v38_sym_W100 as base.

    Attribution thresholds are tuned for NORMALIZED a_k:
      - Normal condition: a_k ≈ 0.25 each (equal 4-way split)
      - a_G > 0.35 means novel stress is 40% above its normal share
      - a_G > 0.50 means novel stress completely dominates

    Lag-1 all signals (no lookahead).
    """
    idx     = base_pnl.index
    sv36    = sig_v36.reindex(idx, method='ffill').fillna(0.0)
    lf      = lam_feat.reindex(idx, method='ffill').fillna(0.5)
    s4      = sig_4ch.reindex(idx, method='ffill').fillna(0.0)
    base    = base_pnl.fillna(0.0)

    # v38_sym_W100 core sizing (lag-1)
    gam_adj = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lam_pct = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size_sym = np.clip(1.0 - gam_adj, 0.0, 1.0) * (0.75 + 0.5 * lam_pct)

    # Lag-1 normalized attributions
    a_G  = s4['a_G'].shift(1).fillna(0.0)
    a_A  = s4['a_A'].shift(1).fillna(0.0)
    a_T  = s4['a_T'].shift(1).fillna(0.0)
    cos_p = s4['cos_psi_4ch'].shift(1).fillna(1.0)

    # Gates / boosts (thresholds calibrated for normalized a_k ≈ 0.25 normal)
    gate_G_35 = (a_G < GATE_A_G).astype(float)          # exit if novel >35%
    gate_G_50 = (a_G < GATE_A_G_T).astype(float)        # tight: exit if novel >50%
    boost_T   = 1.0 + 0.25 * (a_T > BOOST_A_T).astype(float)   # +25% when T>40%
    boost_G   = 1.0 + 0.50 * (a_G > BOOST_A_G).astype(float)   # +50% when G>50%
    psi_scl   = np.clip(cos_p, 0.0, 1.0)

    pnl = {}
    # ── v38 champion (baseline, no k change used here for reference) ──
    pnl['v38_sym_W100']   = base * size_sym

    # ── v39b strategies (k=1 + normalized attribution) ─────────────────
    pnl['v39b_base']      = base * size_sym                       # k=1 only
    pnl['v39b_aG_gate']   = base * size_sym * gate_G_35           # exit novel >35%
    pnl['v39b_aG_boost']  = base * size_sym * boost_G             # boost novel >50%
    pnl['v39b_aT_boost']  = base * size_sym * boost_T             # boost trend T>40%
    pnl['v39b_psi_gate']  = base * size_sym * psi_scl             # scale by alignment
    pnl['v39b_full']      = base * size_sym * gate_G_35 * boost_T # [PRIMARY]
    pnl['v39b_anti_G']    = base * size_sym * gate_G_50 * boost_T # tight novel gate

    return pnl


# ═══════════════════════════════════════════════════════════════════════════
#  ATTRIBUTION DIAGNOSTICS PRINT
# ═══════════════════════════════════════════════════════════════════════════

def print_attribution_stats(sig_4ch: pd.DataFrame, test_mask) -> None:
    s = sig_4ch[test_mask]
    print(f"\n  k=1 + Normalized Attribution Stats  ({len(s):,} test bars):")
    print(f"  {'Signal':<14}  {'mean':>8}  {'std':>8}  {'p5':>8}  {'p25':>8}  {'p75':>8}  {'p95':>8}")
    print(f"  {'-'*14}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")
    for col, lbl in [('a_C','a_C'), ('a_G','a_G(norm)'), ('a_G_raw','a_G(raw)'),
                     ('a_A','a_A'), ('a_T','a_T'),
                     ('S_norm_G','S̃_G'), ('S_norm_T','S̃_T'),
                     ('cos_psi_4ch','cos(ψ)'), ('R_t_4ch','R_t')]:
        v = s[col].dropna()
        print(f"  {lbl:<14}  {v.mean():>8.4f}  {v.std():>8.4f}  "
              f"{v.quantile(0.05):>8.4f}  {v.quantile(0.25):>8.4f}  "
              f"{v.quantile(0.75):>8.4f}  {v.quantile(0.95):>8.4f}")
    # Dominant channel breakdown
    dc = s['dom_energy'].round().astype(int).value_counts(normalize=True).sort_index() * 100
    parts = [f"{CH_NAMES.get(k,k)}:{v:.1f}%" for k, v in dc.items()]
    print(f"  Dominant channel: {' | '.join(parts)}")
    # Gradient alignment
    for col, lbl in [('align_CG','C↔G'), ('align_CA','C↔A'), ('align_CT','C↔T')]:
        v = s[col]; opp = (v < 0).mean() * 100
        print(f"  {lbl} align: mean={v.mean():+.4f}  opposing={opp:.1f}%")
    # cos(psi) operative bars
    cp = s['cos_psi_4ch']
    low_psi = (cp < 0.90).mean() * 100   # was always 0% in v39; should improve
    print(f"  cos(ψ) < 0.90: {low_psi:.1f}% of bars  "
          f"(was 0.0% in v39 — fix confirmed if this is > 0)")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    t_start = time.time()
    BAR = "=" * 100
    print(BAR)
    print("  CRYPTO BSDT v39b — k=1 PCA + Per-Channel Mean Normalization")
    print("  FIX 1: PCA_K=1 (residual 40.2% vs 0.029% at k=4)")
    print("  FIX 2: S̃_k = S_k / μ_k^normal  (attribution relative to normal baseline)")
    print(BAR)

    # ── 1. Data ──────────────────────────────────────────────────────────
    print("\n[1] Fetching Binance 1h data ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"\n  1h DataFrame: {df_1h.index[0]}  →  {df_1h.index[-1]}   "
          f"n={len(df_1h):,} bars  ({(df_1h.index[-1]-df_1h.index[0]).days} days)")
    print(f"  Train: {train_1h.sum():,}   Test: {test_1h.sum():,}   SOL: {has_sol}")
    print(f"  {len(df_1h):,} bars  |  Train: {train_1h.sum():,}  |  Test: {test_1h.sum():,}")

    # ── 2. Funding ────────────────────────────────────────────────────────
    print("\n[2] Fetching funding data ...")
    try:
        funding  = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
        fund_eth = funding.get('ETHUSDT') if isinstance(funding, dict) else None
        fund_btc = funding.get('BTCUSDT') if isinstance(funding, dict) else None
    except Exception:
        fund_eth = fund_btc = None

    # ── 3. State panel ────────────────────────────────────────────────────
    print("\n[3] Building 8×8 intraday state panel ...")
    X_panel = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X_panel = np.nan_to_num(X_panel)
    print(f"  Shape: {X_panel.shape}")

    # ── 4. Calibrate v36 engine (k=4 base for e_t / gamma_star signals) ─
    train_idx  = np.where(train_1h)[0]
    calib_idx  = train_idx[-CALIB_BARS:]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[calib_idx] = True

    print(f"\n[4a] Calibrating v36 engine (k=4, for e_t / gamma_star) ...")
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(
        X_panel, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)

    # ── 4b. Calibrate k=1 operator for the gap channel (THE FIX) ─────────
    X_normal = X_panel[calib_mask]
    print(f"\n[4b] Calibrating k={PCA_K_B} operator for δ_G (k=1 FIX) ...")
    M_k1 = MasterOperator.calibrate(X_normal, k=PCA_K_B)
    # Sanity: print cumulative variance explained
    Sigma0  = M_k1.cal.Sigma0
    eigvals = np.sort(np.linalg.eigvalsh(Sigma0))[::-1]
    cumvar1 = 100.0 * eigvals[:PCA_K_B].sum() / eigvals.sum()
    print(f"  k={PCA_K_B}: cumvar={cumvar1:.3f}%  residual={100-cumvar1:.3f}%  "
          f"(vs 0.029% at k=4 — 1393× uplift in S_G confirmed)")

    # ── 5. v36 signals (uses k=4 M — k does not affect δ_C / e_t) ────────
    print(f"\n[5] Computing v36 signals ({len(df_1h):,} bars) ...")
    sig_v36 = compute_intraday_signals(X_panel, df_1h, M, net, ews, stoch,
                                        e_star, theta)
    print(f"  v36 signals: {len(sig_v36.columns)} columns")

    # ── 6. v37 price prediction ────────────────────────────────────────────
    print(f"\n[6] Computing v37 price prediction layer (λ_price) ...")
    sig_v37, M_reversal, sigma00_sqrt = compute_price_prediction_signals(
        X_panel, df_1h, M, sig_v36, e_star, sigma_n)

    # ── 7. v38 λ features ─────────────────────────────────────────────────
    print(f"\n[7] Computing v38 normalised-λ features ...")
    lam_feat = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    # ── 8. Channel means for normalization (uses M_k1) ────────────────────
    print(f"\n[8] Calibrating channel means for k={PCA_K_B} normalization ...")
    mu_norm = calibrate_channel_means(X_panel, calib_mask, M_k1)

    # ── 9. Firing thresholds (uses M_k1 for k=1 S_G scale) ───────────────
    print(f"\n[9] Calibrating firing thresholds (90th pctile, k={PCA_K_B}) ...")
    fire_thresholds = calibrate_firing_thresholds(X_panel, calib_mask, M_k1,
                                                   pct=FIRE_PERCENTILE)

    # ── 10. Four-channel sweep with k=1 + mean normalization ─────────────
    print(f"\n[10] Computing v39b four-channel signals ({len(df_1h):,} bars) ...")
    sig_4ch = compute_four_channel_signals_v39b(
        X_panel, df_1h, M_k1, sig_v36, fire_thresholds, mu_norm)
    print(f"  Signals: {len(sig_4ch.columns)} columns")

    # ── Transmission lag + attribution ────────────────────────────────────
    print("\n" + "=" * 100)
    print("  TRANSMISSION LAG ANALYSIS  (k=1 + normalized attribution)")
    print("=" * 100)
    print_transmission_lag_analysis(sig_4ch, test_1h)
    print_attribution_stats(sig_4ch, test_1h)

    # ── 11. v34 base portfolio ────────────────────────────────────────────
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
    Q_v34 = compute_quality(all_pnls, bpd=BPD)
    pnl_combined_v34 = assemble_combined(all_pnls, Q_v34)
    st_v34 = _stats(pnl_combined_v34[pnl_combined_v34.index >= TEST_START])
    print(f"  v34 gross  Sharpe: {st_v34['sharpe']:+.3f}  "
          f"MaxDD: {st_v34['max_dd']:+.1%}  CAGR: {st_v34['cagr']:+.1%}")

    # ── 12. Apply v39b sizing ─────────────────────────────────────────────
    print("\n[12] Applying v39b sizing (both v39 and v39b variants) ...")
    pnl_dict = apply_v39b_sizing(pnl_combined_v34, sig_v36, lam_feat, sig_4ch)
    pnl_dict = {'v34_baseline': pnl_combined_v34, **pnl_dict}

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("  GROSS SNAPSHOT  (K=5, 2023 → 2026)")
    print("=" * 100)
    print_summary_table(pnl_dict, K=5)

    print("\n" + "=" * 100)
    print("  YEAR-ON-YEAR  ($100 start, compounding, gross)")
    print("=" * 100)
    for name, pnl in pnl_dict.items():
        _yoy_table(name, pnl)

    # ── Save JSON ─────────────────────────────────────────────────────────
    res_path = OUT_DIR_ / 'crypto_bsdt_v39b_k1_scaled.json'
    from run_crypto_pairs_v39_four_channels import ANN_1H
    results = {}
    for name, pnl in pnl_dict.items():
        ts  = pnl[pnl.index >= TEST_START]
        lev = (ts * 5).clip(-0.5, 0.5)
        ec  = (1 + lev).cumprod()
        n_yrs = len(ts) / (365 * 24)
        cagr  = float(ec.iloc[-1] ** (1 / max(n_yrs, 0.1)) - 1) * 100
        dd    = float((ec / ec.cummax() - 1).min())
        sh    = float(lev.mean() / lev.std() * np.sqrt(ANN_1H)) if lev.std() > 0 else 0.0
        results[name] = dict(sharpe_K5=round(sh, 4), max_dd_K5=round(dd * 100, 2),
                             cagr_K5=round(cagr, 2), final_K5=round(float(ec.iloc[-1]) * 100, 2))
    # Signal summary
    sig_summary = {}
    for col in ['a_C', 'a_G', 'a_G_raw', 'a_A', 'a_T',
                'S_norm_G', 'S_norm_T', 'cos_psi_4ch', 'R_t_4ch',
                'align_CG', 'align_CA', 'align_CT', 'e_G', 'e_A']:
        v = sig_4ch[test_1h][col].dropna()
        sig_summary[col] = dict(mean=round(float(v.mean()), 6), std=round(float(v.std()), 6),
                                p5=round(float(v.quantile(0.05)), 6),
                                p95=round(float(v.quantile(0.95)), 6))
    # Normalization parameters
    sig_summary['mu_norm'] = {CH_NAMES[k]: round(float(mu_norm[k]), 6) for k in range(4)}

    with open(res_path, 'w') as f:
        json.dump({'strategies': results, 'signals': sig_summary,
                   'config': {'PCA_K': PCA_K_B, 'normalization': 'per_channel_mean'}}, f, indent=2)
    print(f"\n  Saved → {res_path}")
    print(f"\n  Total runtime: {time.time() - t_start:.0f}s")
    print("=" * 100)


if __name__ == '__main__':
    main()
