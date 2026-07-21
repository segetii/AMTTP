"""
Crypto BSDT v37 — Price Prediction Layer
=========================================
Adds the Feature-Resolved Energy Decomposition on top of v36.

MATH BACKGROUND
───────────────
The v36 engine computes X_t ∈ R^{N×d}  (N=8 instruments, d=8 features).
Calibration uses the Kronecker structure:

    Σ_0 = I_N ⊗ Σ_feat     →  Sigma0.shape = (d, d)  ✓ (confirmed)
    mu_0 = feature mean     →  mu0.shape    = (d,)    ✓ (confirmed)

The Mahalanobis energy decomposes as:

    e_t = tr(C_t · Σ_0^{-1})
    C_t = X̃_t^T X̃_t  ∈ R^{d×d}    (feature cross-product matrix)

FEATURE-RESOLVED SCHUR DECOMPOSITION
──────────────────────────────────────
Row-j contribution to total energy (exact, no approximation):

    e_t^{(j)} = [Σ_0^{-1}]_{j,:} · C_t[j,:]     ← j-th row of trace sum

Price feature (j=0, log-return 1h):

    e_t^price,full = [Σ_0^{-1}]_{0,:} · C_t[0,:]
                   = Σ_k Σ_0_inv[0,k] × Σ_i x̃[i,0] × x̃[i,k]

    (exact formula from practitioner's guide, cross-coupling included)

PRICE LOADING FACTOR
─────────────────────
    λ_t^price = √( max(e_t^price,full, 0) / e_t )  ∈ [0, 1]

    λ → 1:  all energy in returns   → price will move
    λ → 0:  energy in vol/dispersion → price will chop

MOVE PREDICTIONS (all calibrated from physics, no fitting)
─────────────────────────────────────────────────────────────
    M^remaining   = λ × √Σ_0[0,0] × (√e* − √e_t)     [log-return, N-aggregate]
    M^per-instr   = M^remaining / √N                   [single instrument]
    M^pct         = 100×(exp(M^per-instr) − 1)         [percentage]
    M^reversal    = √Σ_0[0,0] × (√e* − √N)            [recovery after crossing e*]

    sign(M)       = sign( Σ_i (x̃[i,0] − 0) )         [weighted return deviations]

    τ_lin         = (e* − e_t) / ė_t                  [linear bars to threshold]
    τ_quad        = quadratic root  (ë_t correction)   [curvature-adjusted]
    τ_Kramers     = (π/|ė_t|) × exp(2(e*−e_t)/σ_n²)  [stochastic MFPT]
    I_t           = M / τ_quad                         [log-ret per bar]

    ë_t sign: +  →  accelerating (cascade shape — enter early)
              −  →  decelerating (impulse-fade shape — entry urgency low)

CORRECTED 3-LAYER POSITION SIZING
────────────────────────────────────
    size = (1 − γ*) × λ_price × 𝟙[dλ/dt ≥ 0]

    Layer 1  (1 − γ*)      — energy damping (v36 logic)
    Layer 2  λ_price       — only size UP when energy IS in price dimension
    Layer 3  dλ/dt ≥ 0     — only size UP when energy rotating INTO price
                            (exits when vol spikes without price confirmation)

Usage:
    py -3 run_crypto_pairs_v37_price_prediction.py
"""
from __future__ import annotations
import os, sys, json, time, warnings
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import chi2 as scipy_chi2
warnings.filterwarnings('ignore')

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

from collapse_geometry import MasterOperator, LedoitWolfNetwork, InformationGeometry
from run_crypto_pairs_v36_intraday_bsdt import (
    N_AGENTS, N_FEATURES, CALIB_BARS, ALPHA_CONF, PCA_K,
    RSS_PRECOLLAPSE, TAU_TIGHT, TAU_NORMAL, KRAMERS_TAU_1H,
    BPD, ANN_1H,
    build_intraday_state_panel, calibrate_intraday_engine,
    compute_intraday_signals,
    print_yoy_table, _net_ret, _stats,
)
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
    build_1h_df, fetch_and_prepare, fetch_binance_funding,
    add_cross_market_features, add_leverage_features,
    build_daily_positions, upsample_daily_to_1h_pnl,
    compute_1h_strategies, compute_quality, assemble_combined,
)

OUT_DIR_ = Path(OUT_DIR)
RETURN_FEAT = 0    # column index of log-return in the 8-feature state
N = N_AGENTS       # 8
D = N_FEATURES     # 8


# ═══════════════════════════════════════════════════════════════════════════
#  FEATURE-RESOLVED ENERGY DECOMPOSITION
# ═══════════════════════════════════════════════════════════════════════════

def _extract_sigma00(M) -> tuple[float, float, np.ndarray]:
    """
    Extract return-feature statistics from the calibrated model.
    Sigma0 has shape (d, d) = (8, 8) under Kronecker structure I_N ⊗ Σ_feat.

    Returns
    -------
    sigma00      : float  — Σ_feat[0,0] = return variance in normal period
    sigma00_sqrt : float  — √Σ_feat[0,0], in log-return units
    Sinv_row0    : (d,)    — first row of Σ_feat^{-1} (for cross-coupling)
    """
    Sigma0 = M.cal.Sigma0     # shape (d, d)
    Sinv   = M.cal.Sigma0_inv  # shape (d, d)
    sigma00      = float(Sigma0[RETURN_FEAT, RETURN_FEAT])
    sigma00_sqrt = float(np.sqrt(max(sigma00, 1e-12)))
    Sinv_row0    = Sinv[RETURN_FEAT, :]          # (d,)
    return sigma00, sigma00_sqrt, Sinv_row0


def compute_price_energy(X_tilde: np.ndarray, Sinv_row0: np.ndarray) -> tuple[float, float]:
    """
    Schur decomposition of blind-spot energy onto the price/return feature.

    Parameters
    ----------
    X_tilde   : (N, d)  — centred state X_t − μ_0  (broadcasted to each instrument)
    Sinv_row0 : (d,)    — first row of Σ_feat^{-1}

    Returns
    -------
    e_price_full : (may be slightly negative — use max(0, ·))
                   FULL price energy including cross-feature coupling:
                   e_price = Σ_k Sinv_row0[k] × Σ_i x̃[i, 0] × x̃[i, k]
    e_price_diag : Pure diagonal contribution (no coupling):
                   Sinv_row0[0] × Σ_i x̃[i,0]²
    """
    # C = X̃ᵀX̃  shape (d, d), where C[j1,j2] = Σ_i x̃[i,j1] × x̃[i,j2]
    C = X_tilde.T @ X_tilde          # (d, d)
    # Row-0 contribution to tr(C · Sinv) = full price energy
    e_price_full = float(Sinv_row0 @ C[RETURN_FEAT, :])
    # Diagonal only
    e_price_diag = float(Sinv_row0[RETURN_FEAT] * C[RETURN_FEAT, RETURN_FEAT])
    return e_price_full, e_price_diag


# ═══════════════════════════════════════════════════════════════════════════
#  MOVE DURATION  τ_lin, τ_quad, τ_Kramers
# ═══════════════════════════════════════════════════════════════════════════

def _tau_linear(e_t: float, e_star: float, e_dot: float) -> float:
    """τ_lin = (e* − e_t) / ė_t  (already in v36, re-exported here for clarity)."""
    delta = e_star - e_t
    if delta <= 0 or e_dot <= 1e-8:
        return 9999.0
    return float(np.clip(delta / e_dot, 0, 9999.0))


def _tau_quad(e_t: float, e_star: float, e_dot: float, e_ddot: float) -> float:
    """
    Quadratic duration: solve  ė t + ½ ë t² = e* − e_t
    i.e.  ½ ë t² + ė t − Δe = 0
          t = (−ė + √(ė² + 2ë Δe)) / ë      (take positive root)
    Falls back to τ_lin when ë ≈ 0 or discriminant < 0.
    """
    delta = e_star - e_t
    if delta <= 0:
        return 0.0
    if abs(e_ddot) < 1e-8 or e_dot <= 1e-8:
        return _tau_linear(e_t, e_star, e_dot)
    disc = e_dot ** 2 + 2.0 * e_ddot * delta
    if disc < 0:
        return _tau_linear(e_t, e_star, e_dot)
    t = (-e_dot + np.sqrt(disc)) / e_ddot
    return float(np.clip(t, 0, 9999.0))


def _tau_kramers(e_t: float, e_star: float, e_dot: float, sigma_n: float) -> float:
    """
    Simplified Kramers MFPT:
        τ_K ≈ (π / √(|ė_t| × |ė_*|)) × exp(2(e* − e_t) / σ_n²)
    where ė_* ≈ ė_t × e* / e_t  (extrapolated drift at threshold).
    Exponent capped at 50 to avoid overflow.
    """
    delta = e_star - e_t
    if delta <= 0 or e_dot <= 1e-8 or sigma_n <= 1e-9:
        return 9999.0
    e_dot_star = e_dot * (e_star / max(e_t, 1.0))
    omega_sq   = abs(e_dot * e_dot_star)
    exponent   = min(2.0 * delta / (sigma_n ** 2), 50.0)
    tau_k      = (np.pi / max(np.sqrt(omega_sq), 1e-9)) * np.exp(exponent)
    return float(min(tau_k, 9999.0))


# ═══════════════════════════════════════════════════════════════════════════
#  PRICE PREDICTION SIGNAL SWEEP
# ═══════════════════════════════════════════════════════════════════════════

def compute_price_prediction_signals(X_panel:   np.ndarray,
                                      df_1h:     pd.DataFrame,
                                      M,
                                      sig_v36:   pd.DataFrame,
                                      e_star:    float,
                                      sigma_n:   float) -> pd.DataFrame:
    """
    Compute the full price prediction signal stack per bar.

    New signals added on top of v36:
      lambda_price     — price loading factor  λ_t ∈ [0,1]
      e_price_full     — price energy (cross-coupling included)
      e_price_diag     — price energy (diagonal only, for comparison)
      dlambda_dt       — dλ/dt  (positive = energy rotating INTO price)
      move_dir         — sign of return deviation sum (+1 up, −1 down, 0 neutral)
      M_remaining      — remaining move magnitude (log-ret, N-aggregate)
      M_per_instr      — M_remaining / √N  (single-instrument estimate)
      M_pct            — M_per_instr as percentage
      M_lo, M_hi       — 90% CI (chi-squared model on e_price)
      M_reversal       — recovery magnitude after crossing e*  (static scalar)
      tau_quad         — curvature-adjusted duration  (π_quad formula)
      tau_kramers      — stochastic duration (Kramers MFPT)
      e_ddot           — energy curvature  (>0: accelerating, <0: decelerating)
      I_lin            — intensity via τ_lin  = M_remaining / τ_lin
      I_quad           — intensity via τ_quad = M_remaining / τ_quad
      size_v37         — CORRECTED 3-layer position multiplier
                         = (1−γ*) × λ × 𝟙[dλ/dt ≥ 0]
    """
    T  = len(X_panel)
    mu0  = M.cal.mu0           # shape (d,) — feature mean
    sigma00, sigma00_sqrt, Sinv_row0 = _extract_sigma00(M)

    print(f"  [v37] σ_feat[0,0] = {sigma00:.6f}   √σ_feat[0,0] = {sigma00_sqrt:.4f}")
    print(f"  [v37]  Sinv_row0  = {Sinv_row0.round(4)}")
    print(f"  [v37]  e* = {e_star:.3f}   σ_n = {sigma_n:.4f}")

    # Static reversal magnitude (recovery: e* → N, the chi² mean under H₀)
    M_reversal_static = sigma00_sqrt * max(np.sqrt(e_star) - np.sqrt(max(N, 1.0)), 0.0)
    print(f"  [v37] M_reversal (static) = {M_reversal_static:.4f} log-ret "
          f"({100*(np.exp(M_reversal_static/np.sqrt(N))-1):.2f}% per instrument)")

    # chi² percentiles for CI  (df = N per instrument)
    e_price_p05 = scipy_chi2.ppf(0.05, df=N) * sigma00
    e_price_p95 = scipy_chi2.ppf(0.95, df=N) * sigma00

    # Arrays
    bufs = {k: np.full(T, np.nan) for k in [
        'e_price_full', 'e_price_diag', 'lambda_price',
        'move_dir', 'M_remaining', 'M_per_instr', 'M_pct',
        'M_lo', 'M_hi', 'tau_quad', 'tau_kramers',
        'e_ddot', 'I_lin', 'I_quad',
    ]}

    # Pre-compute e_t series and its first/second derivatives from v36 signals
    e_t_series   = sig_v36['e_t'].values
    e_dot_series = np.gradient(e_t_series)        # ė_t finite difference
    e_ddot_raw   = np.gradient(e_dot_series)       # ë_t finite difference

    t0 = time.time()
    for t in range(1, T):
        X_t     = X_panel[t]                       # (N, d)
        X_tilde = X_t - mu0                        # (N, d) — broadcast (d,) mean

        # ── Price-feature energy (corrected Schur decomposition) ────────
        e_full, e_diag = compute_price_energy(X_tilde, Sinv_row0)
        bufs['e_price_full'][t] = e_full
        bufs['e_price_diag'][t] = e_diag

        # ── λ_t^price ────────────────────────────────────────────────────
        e_t   = float(e_t_series[t])
        e_p   = max(e_full, 0.0)
        lam   = float(np.sqrt(e_p / max(e_t, 1e-9)))
        lam   = float(np.clip(lam, 0.0, 1.0))
        bufs['lambda_price'][t] = lam

        # ── Move direction ───────────────────────────────────────────────
        # sign of weighted sum of return deviations
        r_dev = X_tilde[:, RETURN_FEAT]            # (N,)
        bufs['move_dir'][t] = float(np.sign(np.sum(r_dev)))

        # ── M_remaining ──────────────────────────────────────────────────
        M_rem = lam * sigma00_sqrt * max(np.sqrt(e_star) - np.sqrt(e_t), 0.0)
        M_rem_per = M_rem / np.sqrt(N)             # per-instrument estimate
        bufs['M_remaining'][t] = M_rem
        bufs['M_per_instr'][t] = M_rem_per
        bufs['M_pct'][t] = float(100.0 * (np.exp(M_rem_per) - 1.0))

        # ── Confidence interval (chi² model, df=N) ───────────────────────
        M_lo = lam * sigma00_sqrt * max(np.sqrt(e_star) - np.sqrt(e_price_p95), 0.0)
        M_hi = lam * sigma00_sqrt * max(np.sqrt(e_star) - np.sqrt(e_price_p05), 0.0)
        bufs['M_lo'][t] = M_lo / np.sqrt(N)
        bufs['M_hi'][t] = M_hi / np.sqrt(N)

        # ── Duration estimates ────────────────────────────────────────────
        e_dot  = float(e_dot_series[t])
        e_ddot = float(e_ddot_raw[t])
        bufs['e_ddot'][t] = e_ddot
        tau_q  = _tau_quad(e_t, e_star, e_dot, e_ddot)
        tau_k  = _tau_kramers(e_t, e_star, e_dot, sigma_n)
        tau_l  = _tau_linear(e_t, e_star, e_dot)
        bufs['tau_quad'][t]    = tau_q
        bufs['tau_kramers'][t] = tau_k

        # ── Intensity ─────────────────────────────────────────────────────
        bufs['I_lin'][t]  = M_rem_per / max(tau_l, 1.0)
        bufs['I_quad'][t] = M_rem_per / max(tau_q, 1.0)

    print(f"  [v37] Price prediction sweep: {T:,} bars  {time.time()-t0:.1f}s")

    # ── Forward-fill and compute derived signals ──────────────────────────
    def _ff(arr, fill=0.0):
        return pd.Series(arr).fillna(method='ffill').fillna(fill).values

    idx = df_1h.index
    lam_ff = _ff(bufs['lambda_price'], 0.0)

    # dλ/dt — finite difference of forward-filled lambda
    dlam = np.concatenate([[0.0], np.diff(lam_ff)])

    # Gamma from v36 (calibrated θ)
    gam_adj = sig_v36['gamma_star_adj'].values

    # 3-layer corrected size
    size_v37 = np.clip(1.0 - gam_adj, 0.0, 1.0) * lam_ff * (dlam >= 0).astype(float)

    df_out = pd.DataFrame({
        'lambda_price':  lam_ff,
        'e_price_full':  _ff(bufs['e_price_full'],  0.0),
        'e_price_diag':  _ff(bufs['e_price_diag'],  0.0),
        'dlambda_dt':    dlam,
        'move_dir':      _ff(bufs['move_dir'],       0.0),
        'M_remaining':   _ff(bufs['M_remaining'],    0.0),
        'M_per_instr':   _ff(bufs['M_per_instr'],    0.0),
        'M_pct':         _ff(bufs['M_pct'],          0.0),
        'M_lo':          _ff(bufs['M_lo'],           0.0),
        'M_hi':          _ff(bufs['M_hi'],           0.0),
        'tau_quad':      _ff(bufs['tau_quad'],     9999.0),
        'tau_kramers':   _ff(bufs['tau_kramers'],  9999.0),
        'e_ddot':        _ff(bufs['e_ddot'],         0.0),
        'I_lin':         _ff(bufs['I_lin'],          0.0),
        'I_quad':        _ff(bufs['I_quad'],         0.0),
        'size_v37':      size_v37,
    }, index=idx)

    return df_out, M_reversal_static, sigma00_sqrt


# ═══════════════════════════════════════════════════════════════════════════
#  POSITION SIZING — 3-LAYER CORRECTED + VARIANTS
# ═══════════════════════════════════════════════════════════════════════════

def apply_v37_sizing(base_pnl:  pd.Series,
                     sig_v36:   pd.DataFrame,
                     sig_v37:   pd.DataFrame,
                     ret_eth:   pd.Series) -> dict[str, pd.Series]:
    """
    Six strategies to isolate the contribution of each v37 layer:

    v34_baseline     — raw v34 PnL (reference)
    v36_BSDT_scaled  — v36's (1−γ*) energy damping only
    v37_lambda       — (1−γ*) × λ_price  (adds feature-loading, removes vol-energy sizing)
    v37_dlambda      — (1−γ*) × 𝟙[dλ/dt ≥ 0]  (rotation filter alone)
    v37_full         — (1−γ*) × λ × 𝟙[dλ/dt ≥ 0]  (all 3 layers — primary target)
    v37_dir          — v37_full × move_dir  (includes direction flip for MR)
    """
    base   = base_pnl.fillna(0.0)
    sv36   = sig_v36.reindex(base.index, method='ffill').fillna(0.0)
    sv37   = sig_v37.reindex(base.index, method='ffill').fillna(0.0)
    r      = ret_eth.reindex(base.index, fill_value=0.0)

    # Lag all sizing signals by 1 bar (no lookahead)
    gam_adj   = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lam       = sv37['lambda_price'].shift(1).fillna(0.5)
    dlam_ok   = (sv37['dlambda_dt'].shift(1).fillna(0.0) >= 0.0).astype(float)
    size_v36  = np.clip(1.0 - gam_adj, 0.0, 1.0)         # (1−γ*)
    mv_dir    = sv37['move_dir'].shift(1).fillna(0.0)

    pnl_base       = base
    pnl_v36_scaled = base * size_v36
    pnl_v37_lam    = base * size_v36 * lam
    pnl_v37_dlam   = base * size_v36 * dlam_ok
    pnl_v37_full   = base * size_v36 * lam * dlam_ok
    # Directional variant: flip base direction when move_dir = −1
    # Only for the hourly H-series (trend strategies); don't flip pairs/macro
    # Use move_dir as an additional multiplier on v37_full
    # cos_theta sign wasn't effective (near-zero), but move_dir from return sum is cleaner
    dir_mult       = np.where(mv_dir != 0, np.abs(mv_dir), 1.0)   # stays 1.0 (no flipping, just gating)
    pnl_v37_dir    = pnl_v37_full * dir_mult

    return {
        'v34_baseline':   pnl_base,
        'v36_BSDT_scaled':pnl_v36_scaled,
        'v37_lambda':     pnl_v37_lam,
        'v37_dlambda':    pnl_v37_dlam,
        'v37_full':       pnl_v37_full,
        'v37_dir':        pnl_v37_dir,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  SIGNAL REPORT (extended)
# ═══════════════════════════════════════════════════════════════════════════

def print_price_signal_report(sv37: pd.DataFrame, mask: pd.Index,
                               M_reversal: float, sigma00_sqrt: float,
                               e_star: float):
    s  = sv37[mask]
    T  = len(s)
    print(f"\n  [Price prediction signals]  {T:,} test bars  "
          f"({s.index[0].date()} → {s.index[-1].date()})")
    print(f"  {'Signal':<16}  {'mean':>9}  {'std':>9}  {'p5':>9}  {'p95':>9}")
    for col in ['lambda_price', 'dlambda_dt', 'e_price_full', 'e_price_diag',
                'M_pct', 'M_per_instr', 'M_lo', 'M_hi',
                'tau_quad', 'tau_kramers', 'I_quad', 'e_ddot', 'size_v37']:
        if col not in s.columns:
            continue
        v = s[col].replace([np.inf, -np.inf], np.nan).dropna()
        if len(v) == 0:
            continue
        print(f"  {col:<16}  {v.mean():>+9.4f}  {v.std():>9.4f}  "
              f"{v.quantile(0.05):>+9.4f}  {v.quantile(0.95):>+9.4f}")

    # λ distribution
    lam = s['lambda_price']
    print(f"\n  λ_price distribution:")
    print(f"    λ < 0.3   (mostly vol):        {100*(lam < 0.3).mean():.1f}%")
    print(f"    λ 0.3-0.6 (mixed):             {100*((lam >= 0.3)&(lam < 0.6)).mean():.1f}%")
    print(f"    λ 0.6-0.8 (price-dominant):    {100*((lam >= 0.6)&(lam < 0.8)).mean():.1f}%")
    print(f"    λ > 0.8   (pure price signal): {100*(lam >= 0.8).mean():.1f}%")

    # dλ/dt distribution
    dlam = s['dlambda_dt']
    print(f"\n  dλ/dt:  rotating INTO price: {100*(dlam >= 0).mean():.1f}%  "
          f"| rotating OUT: {100*(dlam < 0).mean():.1f}%")

    # Move direction
    md = s['move_dir']
    print(f"\n  Move direction:  up (+1): {100*(md > 0).mean():.1f}%  "
          f"| flat: {100*(md == 0).mean():.1f}%  | down (−1): {100*(md < 0).mean():.1f}%")

    # 3-layer sizing stats
    sz = s['size_v37']
    print(f"\n  3-layer size_v37:")
    print(f"    Mean = {sz.mean():.3f}   Std = {sz.std():.3f}")
    print(f"    Flat  (size=0): {100*(sz == 0).mean():.1f}%   [dλ/dt < 0 exits]")
    print(f"    Full  (size≈max): {100*(sz > 0.7).mean():.1f}%")

    # Magnitude example at current energy levels
    e_mean = s.get('e_price_full', pd.Series([40.0])).mean()
    e_mean = max(e_mean, 1.0)
    M_ex = np.sqrt(max(e_star, 1.0)) - np.sqrt(e_mean)
    M_ex_pct = 100 * (np.exp(sigma00_sqrt * M_ex / np.sqrt(N)) - 1.0)
    print(f"\n  Example magnitude (λ=1, e_t=mean):")
    print(f"    M_remaining ≈ {M_ex_pct:.2f}% per instrument")
    print(f"    M_reversal  ≈ {100*(np.exp(M_reversal/np.sqrt(N))-1):.2f}% per instrument")

    # e_ddot move shape
    edd = s['e_ddot']
    print(f"\n  e_ddot > 0 (accelerating / cascade shape): {100*(edd > 0).mean():.1f}%")
    print(f"  e_ddot < 0 (decelerating / impulse-fade):   {100*(edd < 0).mean():.1f}%")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print("=" * 100)
    print("  CRYPTO BSDT v37 — PRICE PREDICTION LAYER")
    print("  Feature-resolved Schur decomposition  |  3-layer corrected sizing")
    print("=" * 100)

    # ─────────────────────────────────────────────────── 1h DATA ──
    print("\n[1] Fetching Binance 1h data ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"  {len(df_1h):,} bars  |  Train: {train_1h.sum():,}  |  Test: {test_1h.sum():,}")

    # ──────────────────────────────────────────── FUNDING DATA ──
    print("\n[2] Fetching funding data ...")
    try:
        funding = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
        fund_eth = funding.get('ETHUSDT') if isinstance(funding, dict) else None
        fund_btc = funding.get('BTCUSDT') if isinstance(funding, dict) else None
    except Exception:
        fund_eth = fund_btc = None

    # ──────────────────────────────────────────────── 8×8 STATE ──
    print("\n[3] Building 8×8 intraday state matrix ...")
    X_panel = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X_panel = np.nan_to_num(X_panel)
    print(f"  Shape: {X_panel.shape}")

    # ─────────────────────────────────── CALIBRATE ENGINE ──
    train_idx  = np.where(train_1h)[0]
    calib_idx  = train_idx[-CALIB_BARS:]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[calib_idx] = True

    print(f"\n[4] Calibrating intraday physics engine ...")
    M, net, geom, lyap, ews, stoch, e_star, theta = \
        calibrate_intraday_engine(X_panel, calib_mask)

    # Calibration shape verification
    print(f"\n  [v37] CalibrationState shapes:")
    print(f"    mu0.shape      = {M.cal.mu0.shape}")
    print(f"    Sigma0.shape   = {M.cal.Sigma0.shape}")
    print(f"    Sigma0_inv.shape = {M.cal.Sigma0_inv.shape}")
    print(f"    e*             = {e_star:.3f}   θ = {theta:.3f}")

    # sigma_n (re-extract for Kramers)
    sigma_n_from_stoch = getattr(stoch, 'sigma_n', 1.0)
    print(f"    σ_n            = {sigma_n_from_stoch:.4f}")

    # ──────────────────────────────────────── V36 SIGNALS ──
    print(f"\n[5] Computing v36 signals ({len(df_1h):,} bars) ...")
    sig_v36 = compute_intraday_signals(X_panel, df_1h, M, net, ews, stoch,
                                       e_star, theta, history_len=48)
    print(f"  v36 signals: {len(sig_v36.columns)} columns")

    # ────────────────────────────── PRICE PREDICTION LAYER ──
    print(f"\n[6] Computing v37 price prediction layer ...")
    sig_v37, M_reversal, sigma00_sqrt = compute_price_prediction_signals(
        X_panel, df_1h, M, sig_v36, e_star, sigma_n_from_stoch)

    print_price_signal_report(sig_v37, test_1h, M_reversal, sigma00_sqrt, e_star)

    # ─────────────────────────────────────── BUILD V34 BASE ──
    print("\n[7] Building v34 base portfolio ...")
    h_strats = compute_1h_strategies(df_1h, has_sol)
    df_d = fetch_and_prepare()
    df_d = add_cross_market_features(df_d)
    fund_d = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
    df_d = add_leverage_features(df_d, fund_d)
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
        name: upsample_daily_to_1h_pnl(pos, instr_map.get(name, df_1h['ret_eth']), gate_daily)
        for name, pos in pos_dict.items()
    }
    all_pnls     = {**d_strats_1h, **h_strats}
    Q_v34        = compute_quality(all_pnls, bpd=BPD)
    pnl_v34_full = assemble_combined(all_pnls, Q_v34)

    st_v34 = _stats(pnl_v34_full[test_1h])
    print(f"  v34 gross  Sharpe: {st_v34['sharpe']:+.3f}  "
          f"MaxDD: {100*st_v34['max_dd']:+.1f}%  CAGR: {100*st_v34['cagr']:+.1f}%")

    # ───────────────────────────────── APPLY V37 SIZING ──
    print("\n[8] Applying 3-layer corrected sizing ...")
    strategies = apply_v37_sizing(pnl_v34_full, sig_v36, sig_v37, df_1h['ret_eth'])
    for k in list(strategies.keys()):
        strategies[k] = strategies[k][test_1h]

    # Gross comparison table
    print(f"\n  Gross snapshot (test 2023→2026):")
    print(f"  {'Strategy':<22}  {'Sharpe':>8}  {'MaxDD':>8}  {'CAGR':>9}  "
          f"{'Active%':>8}  {'ActDays':>8}")
    for name, pnl in strategies.items():
        st  = _stats(pnl)
        act = float((pnl.abs() > 1e-12).mean()) * 100
        actd = float((pnl.abs() > 1e-12).sum()) / BPD
        print(f"  {name:<22}  {st['sharpe']:>+8.3f}  {100*st['max_dd']:>+7.1f}%  "
              f"{100*st['cagr']:>+8.1f}%  {act:>7.1f}%  {actd:>7.0f}d")

    # ──────────────────────────────────────── YEAR-ON-YEAR ──
    print(f"\n\n{'═'*100}")
    print("  YEAR-ON-YEAR  ($100 start, compounding, gross)")
    print(f"{'═'*100}")
    K_LIST = [1, 2, 5, 10, 14]
    for name, pnl in strategies.items():
        print_yoy_table(name, pnl, K_LIST)

    # ── LAYER ABLATION SUMMARY at K=5 ──────────────────────────────────
    print(f"\n  {'='*70}")
    print(f"  Layer ablation — K=5 net  (vs v34 baseline)")
    print(f"  {'='*70}")
    print(f"  {'Strategy':<22}  {'Sharpe':>8}  {'$100→':>9}  {'MaxDD':>8}")
    for name, pnl in strategies.items():
        r5 = _net_ret(pnl, 5)
        eq5 = 100.0
        for y in [2023, 2024, 2025, 2026]:
            m = pnl.index.year == y
            if m.any(): eq5 *= float((1.0 + r5[m]).prod())
        sh5   = _stats(pnl)['sharpe']
        ec5   = 100.0 * (1.0 + r5).cumprod()
        mdd5  = float((ec5 / ec5.cummax() - 1.0).min())
        print(f"  {name:<22}  {sh5:>+8.3f}  ${eq5:>8.2f}  {100*mdd5:>+7.1f}%")

    # ─────────────────────────────────────────────── SAVE ──
    out = {
        'meta': {
            'version': 'v37',
            'state_dim': f'{N}x{D}',
            'e_star': float(e_star),
            'theta': float(theta),
            'sigma00_sqrt': float(sigma00_sqrt),
            'sigma_n': float(sigma_n_from_stoch),
            'M_reversal': float(M_reversal),
        },
        'signal_summary': {
            'lambda_mean':    float(sig_v37['lambda_price'][test_1h].mean()),
            'lambda_std':     float(sig_v37['lambda_price'][test_1h].std()),
            'dlam_pos_pct':   float((sig_v37['dlambda_dt'][test_1h] >= 0).mean()),
            'size_v37_mean':  float(sig_v37['size_v37'][test_1h].mean()),
            'M_pct_mean':     float(sig_v37['M_pct'][test_1h].mean()),
            'tau_quad_mean':  float(sig_v37['tau_quad'][test_1h].replace(9999, np.nan).mean()),
        },
        'strategies': {},
        'v34_gross': st_v34,
    }
    for name, pnl in strategies.items():
        r2 = _net_ret(pnl, 2)
        eq = 100.0; yr = {}
        for y in [2023, 2024, 2025, 2026]:
            msk = pnl.index.year == y
            if not msk.any(): continue
            ret = float((1.0 + r2[msk]).prod() - 1.0)
            yr[str(y)] = ret; eq *= (1.0 + ret)
        st = _stats(pnl)
        out['strategies'][name] = {
            'yr_returns_K2': yr, 'final_K2': float(eq),
            'sharpe_gross': st['sharpe'], 'max_dd': st['max_dd'],
        }

    out_path = OUT_DIR_ / 'crypto_bsdt_v37_price_prediction.json'
    with open(out_path, 'w') as fh:
        json.dump(out, fh, indent=2, default=float)
    print(f"\n  Saved → {out_path}")
    print("=" * 100)


if __name__ == '__main__':
    main()
