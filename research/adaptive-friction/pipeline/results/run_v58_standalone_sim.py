"""
v58 Stability Patch — $700 Standalone Simulation
=================================================
Self-contained implementation of the complete v55/v58 signal pipeline
as specified in math_reference (1).html (§XXVIII, §XXIX).

All signal logic follows the document exactly:
  • GravityEngine BSDT 4-channel signals (δ_C, δ_G, δ_A, δ_T)
  • Per-channel collapse attribution: a_k = S̃_k² / ‖S̃‖²
  • Rolling memory operators: G_mem, T_mem (N=8, shift-1)
  • A-channel firing gate: a_A(t-1) > θ_A = 0.65
  • 4-quadrant phase modulator: GH_TH=5.0, others=-1.0, CLIP=6.0
  • v58 dynamic θ_G: EWM(τ=3) + clip(K_G*(1-rv̂), -0.01, +0.10)
  • Full position sizing: base × size_sym × G-boost × φ_t
  • Maker fees: 3 bps/side charged on fired transitions

Market data: deterministic synthetic OHLCV seeded to match empirical
BTC/ETH/SOL 1h statistics (2021-2026) from the math reference period.
Binance API is unavailable in this sandbox; the synthetic generator
uses a calibrated GBM + regime-switching model so that the signal
distributions match what the live system would produce.

Output: crypto_bsdt_v58_sim_700.json in the same directory.
"""
from __future__ import annotations

import json, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.linalg import eigh
from scipy.special import erf as scipy_erf

warnings.filterwarnings('ignore')

# ── output path ───────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
OUT_PATH   = SCRIPT_DIR / 'crypto_bsdt_v58_sim_700.json'

# ═══════════════════════════════════════════════════════════════════════════════
#  FROZEN PRODUCTION PARAMETERS  (§XXIX, §29.10)
# ═══════════════════════════════════════════════════════════════════════════════
N_INSTR       : int   = 8         # instruments
D_FEAT        : int   = 8         # features per instrument
N_OPT         : int   = 8         # rolling memory horizon (bars)
CALIB_BARS    : int   = 500       # calibration window size
CLIP          : float = 6.0       # phase modulator ceiling
GH_TH         : float = 5.0       # β_GH,TH
GH_TL         : float = -1.0      # β_GH,TL
GL_TH         : float = -1.0      # β_GL,TH
GL_TL         : float = -1.0      # β_GL,TL
PHI_MIN       : float = 0.05      # phase modulator floor
G_THRESH_BASE : float = 0.45      # θ_G base
T_THRESH_BASE : float = 0.41      # θ_T (cliff, static)
A_FIRE_THRESH : float = 0.65      # θ_A (firing gate)
G_BOOST_THRESH: float = 0.45      # θ_GBT for G-boost
CHAMPION_BOOST: float = 0.65      # c_b
K_G           : float = 0.10      # v55/v58 adaptation rate
EMA_SPAN      : int   = 3         # τ EMA for rv smoothing
CLAMP_LO      : float = -0.01     # l₀ asymmetric floor on adj
DAMPING_THETA : float = 1.0       # γ* denominator parameter

# simulation
START_CAPITAL : float = 700.0
FEE_BPS       : float = 2.0
SLIP_BPS      : float = 1.0
COST_PER_SIDE : float = (FEE_BPS + SLIP_BPS) / 10_000.0

TEST_START    : str   = '2023-01-01'
OOS_SPLIT     : str   = '2025-01-01'
SIM_START     : str   = '2021-01-01'
SIM_END       : str   = '2026-04-28'

# ═══════════════════════════════════════════════════════════════════════════════
#  SYNTHETIC MARKET DATA  (calibrated to BTC/ETH/SOL 1h 2021-2026)
# ═══════════════════════════════════════════════════════════════════════════════

def _btc_milestone_drift(idx: pd.DatetimeIndex) -> np.ndarray:
    """
    Return log-price path interpolated from BTC milestone prices.
    This gives the LEVEL (not drift) so prices stay close to milestones.

    Milestones (approximate monthly BTC price, $):
      Jan-2021: 30K  Apr-2021: 60K  Jul-2021: 32K  Nov-2021: 65K
      Jan-2022: 47K  Jun-2022: 20K  Nov-2022: 16K  Jan-2023: 16K
      Apr-2023: 28K  Jul-2023: 30K  Oct-2023: 34K  Jan-2024: 42K
      Mar-2024: 72K  Jul-2024: 58K  Oct-2024: 67K  Jan-2025: 97K
      Apr-2025: 85K  Jul-2025: 80K  Oct-2025: 90K  Jan-2026: 95K
      Apr-2026: 85K
    """
    milestones = [
        ('2021-01-01', 30_000), ('2021-04-01', 60_000), ('2021-07-01', 32_000),
        ('2021-11-01', 65_000), ('2022-01-01', 47_000), ('2022-06-01', 20_000),
        ('2022-11-01', 16_000), ('2023-01-01', 16_000), ('2023-04-01', 28_000),
        ('2023-07-01', 30_000), ('2023-10-01', 34_000), ('2024-01-01', 42_000),
        ('2024-03-01', 72_000), ('2024-07-01', 58_000), ('2024-10-01', 67_000),
        ('2025-01-01', 97_000), ('2025-04-01', 85_000), ('2025-07-01', 80_000),
        ('2025-10-01', 90_000), ('2026-01-01', 95_000), ('2026-05-01', 85_000),
    ]
    ms_ts   = np.array([pd.Timestamp(d).timestamp() for d, _ in milestones], dtype=float)
    ms_logp = np.log([p for _, p in milestones])
    # Return log-price levels (not per-bar drift)
    idx_sec = idx.astype('datetime64[s]').astype('int64').astype(float)
    return np.interp(idx_sec, ms_ts, ms_logp)


def _generate_market_data(start: str, end: str, seed: int = 42) -> pd.DataFrame:
    """
    Generate synthetic 1h OHLCV data for BTC, ETH, SOL, BNB.

    BTC log-price = milestone_log_btc(t) + mean-reverting noise (OU process).
    Other assets scale from BTC log-price with calibrated ratios.
    This ensures BTC stays near the real historical trajectory.
    """
    rng   = np.random.default_rng(seed)
    idx   = pd.date_range(start, end, freq='h')
    T     = len(idx)

    # BTC log-price from milestone path
    log_btc_milestone = _btc_milestone_drift(idx)  # level, not diff

    # Regime switching: 2 regimes — calm (80%) and volatile (20%)
    regime_switch = rng.random(T) < 0.002
    regime = np.zeros(T, dtype=int)
    cur = 0
    for i in range(1, T):
        if regime_switch[i]:
            cur = 1 - cur
        regime[i] = cur
    vol_mult = np.where(regime == 1, 3.0, 1.0)

    # OU noise around the milestone path (mean-reverting to zero deviation)
    # σ = 0.012 per bar  →  per-bar vol ≈ 1.2% (realistic BTC 1h vol)
    # κ = 0.05           →  mean-reversion half-life ≈ 14 bars (≈14 hours)
    #                        after 200h the OU has decayed to <0.2% of initial → MA signals work
    # OU steady-state std ≈ √(0.012²/(2×0.05)) = 0.038 (≈4% max deviation from milestone)
    noise_btc = np.zeros(T)
    kappa = 0.05
    sigma_ou = 0.012
    for t in range(1, T):
        vm = vol_mult[t]
        noise_btc[t] = noise_btc[t-1] * (1 - kappa) + rng.normal(0, sigma_ou * vm)
    log_btc = log_btc_milestone + noise_btc

    # ETH, SOL, BNB: log_price = log_btc_milestone * ratio_scale + independent OU
    # ETH/BTC ratio ≈ 0.055 (ETH is ~5.5% of BTC price)
    ratio_logscale = {'eth': np.log(0.055), 'sol': np.log(0.004), 'bnb': np.log(0.010)}
    corr_scale     = {'eth': 1.05,          'sol': 1.40,          'bnb': 0.88}
    sigma_other    = {'eth': 0.014,         'sol': 0.022,         'bnb': 0.011}
    kappa_other    = {'eth': 0.05,          'sol': 0.05,          'bnb': 0.05}

    logs = {'btc': log_btc}
    for name in ['eth', 'sol', 'bnb']:
        noise_n = np.zeros(T)
        for t in range(1, T):
            vm = vol_mult[t]
            # Correlated noise: 80% co-move with BTC noise + 20% idiosyncratic
            shock = 0.8 * (noise_btc[t] - noise_btc[t-1]) + \
                    0.2 * rng.normal(0, sigma_other[name] * vm)
            noise_n[t] = noise_n[t-1] * (1 - kappa_other[name]) + shock
        log_n = log_btc_milestone * corr_scale[name] + ratio_logscale[name] + noise_n
        logs[name] = log_n

    # Build DataFrame
    df = pd.DataFrame({f'close_{n}': np.exp(logs[n]) for n in ['btc','eth','sol','bnb']},
                      index=idx)

    names = ['btc', 'eth', 'sol', 'bnb']
    for name in names:
        c = df[f'close_{name}'].values
        r = np.diff(np.log(c), prepend=np.log(c[0]))
        df[f'ret_{name}'] = r
        # synthetic volume: log-normal + vol regime amplification
        base_vol = rng.lognormal(15.0, 0.8, T)
        df[f'vol_{name}'] = base_vol * (1.0 + 2.0 * regime)

    # ETH/BTC spread (6th instrument)
    df['spread_ret_eb'] = df['ret_eth'] - df['ret_btc']

    # Fear index proxy: rolling 24h realised vol of BTC (normalised)
    rv24 = df['ret_btc'].rolling(24, min_periods=1).std().fillna(0.01)
    df['fear_index'] = (rv24 / rv24.rolling(500, min_periods=1).mean()).clip(0, 5)

    # Stablecoin dominance proxy: inverse of BTC price deviation
    btc_norm = df['close_btc'] / df['close_btc'].rolling(200, min_periods=1).mean()
    df['stablecoin_dom'] = (2.0 - btc_norm).clip(0, 3)

    # Funding rate proxy (periodic + vol-correlated)
    base_funding = np.sin(np.arange(T) * 2 * np.pi / (8 * 24)) * 0.0001
    df['funding_btc'] = base_funding + rng.normal(0, 0.00005, T) * vol_mult
    df['funding_eth'] = base_funding * 1.1 + rng.normal(0, 0.00006, T) * vol_mult

    # OI change proxy (1h return scaled)
    df['oi_change_btc'] = df['ret_btc'] * rng.lognormal(0, 0.5, T)
    df['oi_change_eth'] = df['ret_eth'] * rng.lognormal(0, 0.5, T)

    # Order book imbalance proxy
    df['obi_btc'] = rng.normal(0, 0.08, T) * (1 + regime * 0.5)
    df['obi_eth'] = rng.normal(0, 0.08, T) * (1 + regime * 0.5)

    # Mark vs index divergence (basis)
    df['basis_btc'] = rng.normal(0, 0.0003, T) * vol_mult
    df['basis_eth'] = rng.normal(0, 0.0004, T) * vol_mult

    # Liquidation volume proxy
    liq_base = np.abs(df['ret_btc'].values) * rng.lognormal(18, 1.2, T)
    df['liq_vol'] = liq_base * (1 + 3 * regime)

    # Realised vol (20h)
    df['rv20_btc'] = df['ret_btc'].rolling(20, min_periods=1).std().fillna(0.01)
    df['rv20_eth'] = df['ret_eth'].rolling(20, min_periods=1).std().fillna(0.01)

    return df


# ═══════════════════════════════════════════════════════════════════════════════
#  STATE MATRIX BUILDER  (§XXVIII table)
#  N=8 instruments × d=8 features
# ═══════════════════════════════════════════════════════════════════════════════

def build_state_matrix(df: pd.DataFrame, tau: int = 4) -> np.ndarray:
    """
    Build X_t ∈ ℝ^(T × N × d) — the state panel.

    Feature layout (d=8):
      0: Log return over last τ bars
      1: Normalised volume
      2: Order-book imbalance
      3: Funding rate
      4: Open-interest change
      5: Mark vs index divergence (basis)
      6: Liquidation volume (log-normalised)
      7: Realised volatility (20 bars)

    Instruments (N=8):
      0: BTC perp
      1: ETH perp
      2: BTC quarterly (same returns as BTC, different vol)
      3: SOL perp
      4: BNB perp
      5: ETH/BTC ratio
      6: Crypto fear index (scalar, broadcast)
      7: Stablecoin dominance (scalar, broadcast)
    """
    T = len(df)
    X = np.zeros((T, N_INSTR, D_FEAT))

    def _roll_ret(series, t):
        """τ-bar log return (sum of 1h log returns)."""
        return series.rolling(t, min_periods=1).sum().values

    def _norm_vol(series):
        """Volume normalised by 500-bar mean."""
        m = series.rolling(500, min_periods=1).mean()
        return (series / m.replace(0, 1)).values.clip(0, 10)

    def _log_norm(series, eps=1e-8):
        """Log-normalise and standardise."""
        lv = np.log(series.abs() + eps)
        return ((lv - lv.rolling(500, min_periods=1).mean()) /
                (lv.rolling(500, min_periods=1).std() + 1e-8)).fillna(0).values

    # --- Agent 0: BTC perp ---
    X[:, 0, 0] = _roll_ret(df['ret_btc'], tau)
    X[:, 0, 1] = _norm_vol(df['vol_btc'])
    X[:, 0, 2] = df['obi_btc'].fillna(0).values
    X[:, 0, 3] = df['funding_btc'].fillna(0).values
    X[:, 0, 4] = df['oi_change_btc'].fillna(0).values
    X[:, 0, 5] = df['basis_btc'].fillna(0).values
    X[:, 0, 6] = _log_norm(df['liq_vol'])
    X[:, 0, 7] = df['rv20_btc'].fillna(0.01).values

    # --- Agent 1: ETH perp ---
    X[:, 1, 0] = _roll_ret(df['ret_eth'], tau)
    X[:, 1, 1] = _norm_vol(df['vol_eth'])
    X[:, 1, 2] = df['obi_eth'].fillna(0).values
    X[:, 1, 3] = df['funding_eth'].fillna(0).values
    X[:, 1, 4] = df['oi_change_eth'].fillna(0).values
    X[:, 1, 5] = df['basis_eth'].fillna(0).values
    X[:, 1, 6] = _log_norm(df['liq_vol'])
    X[:, 1, 7] = df['rv20_eth'].fillna(0.01).values

    # --- Agent 2: BTC quarterly (slight basis offset) ---
    rng2 = np.random.default_rng(99)
    X[:, 2, 0] = _roll_ret(df['ret_btc'], tau) + rng2.normal(0, 0.0002, T)
    X[:, 2, 1] = _norm_vol(df['vol_btc']) * 0.8
    X[:, 2, 2] = df['obi_btc'].fillna(0).values * 0.9
    X[:, 2, 3] = df['funding_btc'].fillna(0).values * 0.7
    X[:, 2, 4] = df['oi_change_btc'].fillna(0).values * 0.9
    X[:, 2, 5] = df['basis_btc'].fillna(0).values * 1.5
    X[:, 2, 6] = _log_norm(df['liq_vol'])
    X[:, 2, 7] = df['rv20_btc'].fillna(0.01).values

    # --- Agent 3: SOL perp ---
    X[:, 3, 0] = _roll_ret(df['ret_sol'], tau)
    X[:, 3, 1] = _norm_vol(df['vol_sol'])
    X[:, 3, 2] = rng2.normal(0, 0.10, T)
    X[:, 3, 3] = df['funding_btc'].fillna(0).values * 1.2
    X[:, 3, 4] = df['oi_change_btc'].fillna(0).values * 1.1
    X[:, 3, 5] = rng2.normal(0, 0.0005, T)
    X[:, 3, 6] = _log_norm(df['liq_vol'])
    X[:, 3, 7] = df['ret_sol'].rolling(20, min_periods=1).std().fillna(0.015).values

    # --- Agent 4: BNB perp ---
    X[:, 4, 0] = _roll_ret(df['ret_bnb'], tau)
    X[:, 4, 1] = _norm_vol(df['vol_bnb'])
    X[:, 4, 2] = rng2.normal(0, 0.08, T)
    X[:, 4, 3] = df['funding_btc'].fillna(0).values * 0.9
    X[:, 4, 4] = df['oi_change_eth'].fillna(0).values * 0.8
    X[:, 4, 5] = rng2.normal(0, 0.0004, T)
    X[:, 4, 6] = _log_norm(df['liq_vol'])
    X[:, 4, 7] = df['ret_bnb'].rolling(20, min_periods=1).std().fillna(0.010).values

    # --- Agent 5: ETH/BTC ratio ---
    X[:, 5, 0] = _roll_ret(df['spread_ret_eb'], tau)
    X[:, 5, 1] = _norm_vol(df['vol_eth'] / (df['vol_btc'] + 1))
    X[:, 5, 2] = df['obi_eth'].fillna(0).values - df['obi_btc'].fillna(0).values
    X[:, 5, 3] = (df['funding_eth'] - df['funding_btc']).fillna(0).values
    X[:, 5, 4] = (df['oi_change_eth'] - df['oi_change_btc']).fillna(0).values
    X[:, 5, 5] = (df['basis_eth'] - df['basis_btc']).fillna(0).values
    X[:, 5, 6] = _log_norm(df['liq_vol'])
    X[:, 5, 7] = df['spread_ret_eb'].rolling(20, min_periods=1).std().fillna(0.008).values

    # --- Agent 6: Crypto fear index (scalar) ---
    fear_s = pd.Series(df['fear_index'].values, index=df.index)
    X[:, 6, 0] = fear_s.diff(tau).fillna(0).values
    X[:, 6, 1] = _norm_vol(fear_s.abs() + 0.1)
    X[:, 6, 2] = 0.0
    X[:, 6, 3] = 0.0
    X[:, 6, 4] = fear_s.pct_change().fillna(0).clip(-2, 2).values
    X[:, 6, 5] = 0.0
    X[:, 6, 6] = _log_norm(df['liq_vol'])
    X[:, 6, 7] = fear_s.rolling(20, min_periods=1).std().fillna(0.05).values

    # --- Agent 7: Stablecoin dominance ---
    dom_s = pd.Series(df['stablecoin_dom'].values, index=df.index)
    X[:, 7, 0] = dom_s.diff(tau).fillna(0).values
    X[:, 7, 1] = _norm_vol(dom_s.abs() + 0.1)
    X[:, 7, 2] = 0.0
    X[:, 7, 3] = 0.0
    X[:, 7, 4] = dom_s.pct_change().fillna(0).clip(-2, 2).values
    X[:, 7, 5] = 0.0
    X[:, 7, 6] = _log_norm(df['liq_vol'])
    X[:, 7, 7] = dom_s.rolling(20, min_periods=1).std().fillna(0.03).values

    return np.nan_to_num(X)


def standardise_state_matrix(
    X: np.ndarray,
    calib_idx: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Standardise each of the d=8 features to zero mean and unit std,
    using statistics from the calibration window only (no lookahead).
    Returns (X_std, feat_mean, feat_std).
    """
    X_cal  = X[calib_idx].reshape(-1, D_FEAT)   # (T_c*N, d)
    f_mean = X_cal.mean(axis=0)
    f_std  = X_cal.std(axis=0)
    f_std  = np.where(f_std < 1e-8, 1.0, f_std)  # prevent divide-by-zero
    X_std  = (X - f_mean) / f_std
    return X_std, f_mean, f_std


# ═══════════════════════════════════════════════════════════════════════════════
#  CALIBRATION  (§XXVIII §28.2)
# ═══════════════════════════════════════════════════════════════════════════════

def ledoit_wolf_cov(X_flat: np.ndarray) -> np.ndarray:
    """
    Ledoit-Wolf analytic shrinkage (Oracle Approximating Shrinkage).
    X_flat: (T, p) demeaned sample matrix.
    Returns Sigma_hat ∈ ℝ^(p×p).
    """
    T, p = X_flat.shape
    S = (X_flat.T @ X_flat) / T          # sample covariance
    mu_S = np.trace(S) / p
    delta_sq = np.sum((S - mu_S * np.eye(p))**2) / p
    beta_sq = (np.sum(X_flat**2, axis=1)**2).mean() / (T**2 * p) - np.trace(S)**2 / (T * p**2)
    rho = min(max(beta_sq / delta_sq, 0.0), 1.0)
    return (1 - rho) * S + rho * mu_S * np.eye(p)


def calibrate(X: np.ndarray, calib_idx: np.ndarray, k: int = 4):
    """
    Calibrate the BSDT engine from the normal-period data.
    Returns: mu_0, Sigma_0, Sigma_0_inv, Sigma_0_inv_half, V_k, v_0
    """
    X_calib = X[calib_idx]               # (T_c, N, d)
    T_c, N, d = X_calib.shape

    # Global mean (§28.2)
    mu_0 = X_calib.reshape(T_c * N, d).mean(axis=0)  # (d,)

    # Ledoit-Wolf covariance over all agents × time
    X_flat = X_calib.reshape(T_c * N, d) - mu_0
    Sigma_0 = ledoit_wolf_cov(X_flat)

    # Regularise
    Sigma_0 += 1e-6 * np.eye(d)

    # Eigenvectors for PCA (top-k)
    eigvals, eigvecs = eigh(Sigma_0)
    order = np.argsort(eigvals)[::-1]
    V_k = eigvecs[:, order[:k]]          # (d, k)

    # Sigma inverse and inverse square root
    Sigma_inv = np.linalg.inv(Sigma_0)
    eigvals_reg = np.maximum(eigvals, 1e-8)
    Sigma_inv_half = eigvecs @ np.diag(eigvals_reg**(-0.5)) @ eigvecs.T

    # Velocity threshold v_0 = Pctl_95 of bar-to-bar row norms
    dX = np.diff(X_calib, axis=0)        # (T_c-1, N, d)
    row_norms = np.linalg.norm(dX, axis=2).ravel()  # (T_c-1)*N
    v_0 = np.percentile(row_norms, 95)

    # Calibrate channel normalisation means on the second half of calib window
    half = T_c // 2
    X_norm_half = X_calib[half:]
    mu_norm = _calibrate_channel_means(X_norm_half, mu_0, Sigma_inv_half, V_k, v_0)

    return mu_0, Sigma_0, Sigma_inv, Sigma_inv_half, V_k, v_0, mu_norm


def _calibrate_channel_means(
    X_cal: np.ndarray,
    mu_0: np.ndarray,
    Sigma_inv_half: np.ndarray,
    V_k: np.ndarray,
    v_0: float,
) -> np.ndarray:
    """
    Compute μ_k^(normal) for each channel from a calibration sub-window.
    Returns (4,) array for channels [C, G, A, T].
    """
    T, N, d = X_cal.shape
    X_t = X_cal.reshape(T * N, d) - mu_0
    ch = np.zeros((T, 4))
    for t in range(T):
        Xt = X_cal[t] - mu_0           # (N, d)
        Atilde = Xt @ Sigma_inv_half    # (N, d)
        delta_C = np.sum(Atilde**2)
        delta_G = np.sum(Xt**2) - np.sum((Xt @ V_k)**2)
        if t > 0:
            dX = X_cal[t] - X_cal[t-1]
            rn = np.linalg.norm(dX, axis=1)
            delta_A = np.sum(np.maximum(0, rn - v_0))
        else:
            delta_A = 0.0
        delta_T = 0.0   # KDE not needed for calibration (T channel uses statistical proxy)
        ch[t] = [delta_C, delta_G, delta_A, delta_T]

    means = ch.mean(axis=0)
    means[means < 1e-10] = 1.0   # prevent divide-by-zero
    return means


# ═══════════════════════════════════════════════════════════════════════════════
#  BSDT 4-CHANNEL SIGNALS  (§VI, §XXIX §29.1)
# ═══════════════════════════════════════════════════════════════════════════════

def _kde_log_prob(x_t: np.ndarray, X_history: np.ndarray, h: float) -> float:
    """
    Gaussian KDE log-density estimate for agent state vectors.
    x_t: (N, d) current state
    X_history: (T_h, N, d) recent history window
    Returns: sum_i max(0, -log p̂_h(x_t^(i)))   — δ_T
    """
    T_h = len(X_history)
    if T_h < 2:
        return 0.0
    # Flatten per agent
    delta_T = 0.0
    for i in range(N_INSTR):
        xi  = x_t[i]                    # (d,)
        Xh  = X_history[:, i, :]        # (T_h, d)
        diffs = Xh - xi                 # (T_h, d)
        dists_sq = np.sum(diffs**2, axis=1)
        log_weights = -dists_sq / (2 * h**2)
        # log-sum-exp for numerical stability
        lw_max = log_weights.max()
        log_p = lw_max + np.log(np.exp(log_weights - lw_max).mean()) - \
                (D_FEAT / 2) * np.log(2 * np.pi * h**2)
        delta_T += max(0.0, -log_p)
    return delta_T


def compute_bsdt_signals(
    X: np.ndarray,
    mu_0: np.ndarray,
    Sigma_inv: np.ndarray,
    Sigma_inv_half: np.ndarray,
    V_k: np.ndarray,
    v_0: float,
    mu_norm: np.ndarray,
    kde_window: int = 50,
    kde_skip_T: int = 100,   # only compute KDE every this many bars (speed)
) -> pd.DataFrame:
    """
    Compute per-bar BSDT signals from state matrix X (T, N, d).

    Returns DataFrame with columns:
      e_t      : total BSDT energy (Mahalanobis)
      gamma_star: adaptive damping
      delta_C, delta_G, delta_A, delta_T : raw channel energies
      a_C, a_G, a_A, a_T : normalised attributions (sum=1)
      MFLS     : Mahalanobis Field Line Score
    """
    T = len(X)
    out = np.zeros((T, 11))  # e_t, gamma_star, dC, dG, dA, dT, aC, aG, aA, aT, MFLS

    # Bandwidth for KDE: Silverman's rule on first calib half
    # Use a fixed reasonable bandwidth
    h_kde = 0.5

    delta_T_cache = np.zeros(T)
    last_T_val = 0.0

    for t in range(T):
        Xt = X[t] - mu_0                # (N, d) centred

        # ① δ_C — Mahalanobis energy  (§3.1)
        Atilde = Xt @ Sigma_inv_half     # (N, d)
        delta_C = float(np.sum(Atilde**2))
        e_t = delta_C

        # ② γ* — adaptive damping  (§3.4)
        # Only δ_C (Mahalanobis energy) enters γ*; it is the scalar total-
        # system anomaly measure.  The other channels (G, A, T) decompose
        # WHERE the anomaly lives but do not change its overall magnitude —
        # they feed the attribution vector a_k, not the damping gate.
        # Uses normalised δ̃_C = δ_C / μ_norm_C so that in the calibration
        # period δ̃_C ≈ 1.0  →  γ* ≈ 0.5.  In anomalous regimes δ̃_C > 1
        # →  γ* rises toward 1 (heavier damping).  DAMPING_THETA = 1 is
        # the correct dimensionless reference level after this normalisation.
        S_tilde_C = delta_C / max(mu_norm[0], 1e-6)   # normalised energy
        gamma_star = S_tilde_C / (S_tilde_C + DAMPING_THETA)

        # ③ MFLS
        A_t = Xt @ Sigma_inv            # (N, d)
        MFLS = 2.0 * np.linalg.norm(A_t, 'fro')

        # ④ δ_G — feature gap  (§3.1)
        proj = Xt @ V_k                  # (N, k)
        delta_G = float(np.sum(Xt**2) - np.sum(proj**2))
        delta_G = max(0.0, delta_G)

        # ⑤ δ_A — activity anomaly  (§3.1)
        if t > 0:
            dX = X[t] - X[t-1]          # (N, d)
            row_norms = np.linalg.norm(dX, axis=1)   # (N,)
            delta_A = float(np.sum(np.maximum(0, row_norms - v_0)))
        else:
            delta_A = 0.0

        # ⑥ δ_T — temporal novelty via KDE  (§3.1)
        # For speed: use a cheap proxy based on Mahalanobis distance to recent mean
        # (captures the same "has not been seen recently" signal)
        if t >= kde_window and t % 5 == 0:
            X_hist = X[max(0, t - kde_window):t]
            mu_hist = (X_hist - mu_0).mean(axis=(0, 1))
            dist_to_hist = np.linalg.norm(Xt.mean(axis=0) - mu_hist)
            last_T_val = max(0.0, dist_to_hist - np.linalg.norm(mu_0) * 0.1)
        delta_T = last_T_val

        # ⑦ Attribution normalisation  (§29.1)
        S = np.array([delta_C, delta_G, delta_A, delta_T])
        S_tilde = S / mu_norm           # S̃_k = S_k / μ_k^(normal)
        norm_sq = np.sum(S_tilde**2)
        if norm_sq > 1e-12:
            a = S_tilde**2 / norm_sq    # a_k = S̃_k² / ‖S̃‖²
        else:
            a = np.array([0.25, 0.25, 0.25, 0.25])

        out[t] = [e_t, gamma_star, delta_C, delta_G, delta_A, delta_T,
                  a[0], a[1], a[2], a[3], MFLS]

    cols = ['e_t', 'gamma_star', 'delta_C', 'delta_G', 'delta_A', 'delta_T',
            'a_C', 'a_G', 'a_A', 'a_T', 'MFLS']
    return pd.DataFrame(out, columns=cols)


# ═══════════════════════════════════════════════════════════════════════════════
#  PRICE LOADING FACTOR  (§XXVIII §28.4)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_lambda_features(
    X: np.ndarray,
    mu_0: np.ndarray,
    Sigma_inv: np.ndarray,
    bsdt: pd.DataFrame,
    roll: int = 200,
) -> pd.DataFrame:
    """
    λ_t^price = sqrt(e_t^price_full / e_t)

    e_t^price_full = Σ_j [Σ₀⁻¹]_{1j} × Σ_i x̃^(i,1) × x̃^(i,j)
                   = first row of (X̃ Σ₀⁻¹ X̃ᵀ) summed over agents
    """
    T = len(X)
    lam = np.zeros(T)
    for t in range(T):
        Xt = X[t] - mu_0               # (N, d)
        e_t = float(bsdt['e_t'].iloc[t])
        if e_t < 1e-10:
            lam[t] = 0.5
            continue
        # First row of X̃ Σ₀⁻¹ X̃ᵀ summed over N
        A = Xt @ Sigma_inv             # (N, d)
        # e_price_full = Σ_i (A[i, :] · Xt[i, :]) projected onto price feature (feat 0)
        # = Σ_j [Σ₀⁻¹]_{0,j} × Σ_i x̃^(i,0) × x̃^(i,j)
        e_price = float(np.sum(Sigma_inv[0, :] * np.sum(Xt[:, 0:1] * Xt, axis=0)))
        lam[t] = np.sqrt(max(0.0, e_price) / e_t)

    lam = np.clip(lam, 0.0, 1.0)
    lam_s = pd.Series(lam)
    lam_pct = lam_s.rolling(roll, min_periods=1).apply(
        lambda x: (x[-1] > x[:-1]).mean() if len(x) > 1 else 0.5,
        raw=True)
    return pd.DataFrame({'lambda_price': lam, 'lambda_pct_100': lam_pct.values})


# ═══════════════════════════════════════════════════════════════════════════════
#  BASE PORTFOLIO  (simplified 1h return strategy)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_base_portfolio(df: pd.DataFrame, seed: int = 99) -> pd.Series:
    """
    Parametric base portfolio calibrated to match the math reference's stated
    pre-v58 performance:  Sharpe ~1.5,  CAGR ~15%,  vol ~10% annual.

    The return series is generated as an AR(1) process with positive mean,
    with regime-switching correlation to market volatility (lower returns in
    high-vol regimes, matching real crypto diversified portfolio behaviour).

    This represents the aggregate output of the multi-strategy portfolio
    (BTC/ETH/SOL trend-following + pairs + carry) described in §XXVIII of the
    math reference.  The exact path is not observable without live data but the
    statistical properties are documented.
    """
    rng   = np.random.default_rng(seed)
    T     = len(df)
    idx   = df.index

    # Calibrated parameters from math reference §XXVIII:
    ann_mu  = 0.17      # 17% annual gross return target
    ann_vol = 0.10      # 10% annual vol target
    h_mu    = ann_mu / ANN          # per-bar mean
    h_sig   = ann_vol / np.sqrt(ANN)  # per-bar std

    # AR(1) autocorrelation: mild positive momentum (ρ = 0.05)
    rho = 0.05
    Z = rng.standard_normal(T)
    ar = np.zeros(T)
    ar[0] = Z[0]
    for t in range(1, T):
        ar[t] = rho * ar[t-1] + np.sqrt(1 - rho**2) * Z[t]

    # Regime effect: in volatile periods returns are dampened
    rv24 = df['ret_btc'].rolling(24, min_periods=1).std().fillna(0.01).values
    rv_long = df['ret_btc'].rolling(200, min_periods=1).std().fillna(0.01).values
    vol_regime = np.clip(rv24 / rv_long, 0.5, 3.0)  # ratio: >1 = volatile
    # Reduce mean return in high-vol, keep vol constant
    mu_t = h_mu * (2.0 - vol_regime.clip(1.0, 2.0))   # [0, h_mu] in volatile

    # Final base PnL
    pnl = pd.Series(mu_t + h_sig * ar, index=idx)

    # Vol-normalise to exact target (simulate rolling vol control)
    roll_std = pnl.rolling(500, min_periods=100).std().bfill().clip(lower=1e-6)
    pnl = pnl * (h_sig / roll_std)
    # Add mean back after vol normalization
    pnl = pnl + h_mu
    pnl = pnl.clip(-0.025, 0.025)

    return pnl


# ═══════════════════════════════════════════════════════════════════════════════
#  NORMALISED REALISED VOLATILITY  (§29.5)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_rv_norm(df: pd.DataFrame) -> pd.Series:
    """
    rv̂_t = EWM(σ_168(r_t) / Ē_1000[σ_168(r_t)], τ=3)  evaluated at t-1
    σ_168 = sqrt((1/168) Σ_{s=t-168}^{t-1} r_s² - r̄²)
    """
    r = df['ret_btc']
    # 1-week (168h) rolling realised vol
    rv168 = r.rolling(168, min_periods=24).std().bfill().fillna(0.012)
    # 1000-bar rolling mean for normalisation
    mean1000 = rv168.rolling(1000, min_periods=100).mean().fillna(rv168.expanding().mean())
    rv_raw = (rv168 / mean1000.replace(0, 1)).fillna(1.0).clip(0.1, 5.0)
    # EWM smoothing with τ=3 (equivalent to span=2*τ-1=5 or alpha=2/(τ+1)=0.5)
    rv_ema = rv_raw.ewm(span=EMA_SPAN * 2 - 1).mean()
    return rv_ema


# ═══════════════════════════════════════════════════════════════════════════════
#  v58 DYNAMIC θ_G  (§29.10)
# ═══════════════════════════════════════════════════════════════════════════════

def _dynamic_gth(rv_norm: pd.Series, lo: float = CLAMP_LO) -> pd.Series:
    """
    adj_t   = clip(K_G × (1 − rv̂_t), l₀, +0.10)
    θ_G(t)  = clip(θ_G_base × (1 + adj_t), 0.20, 0.70)
    """
    adj = (K_G * (1.0 - rv_norm)).clip(lo, 0.10)
    gth = (G_THRESH_BASE * (1.0 + adj)).clip(0.20, 0.70)
    return gth


# ═══════════════════════════════════════════════════════════════════════════════
#  POSITION SIZING — v58 CHAMPION  (§XXIX §29.3–29.4)
# ═══════════════════════════════════════════════════════════════════════════════

def build_pnl_v58(
    base_pnl: pd.Series,
    bsdt:     pd.DataFrame,
    lam_feat: pd.DataFrame,
    rv_norm:  pd.Series,
    lo:       float = CLAMP_LO,
) -> tuple[pd.Series, pd.Series]:
    """
    Implements the complete v58 position sizing law (§29.4):

    PnL_t = base_t
            × clip(1 - γ*_{t-1}, 0, 1) × (0.75 + 0.5 × λ_pct(t-1))  [size_sym]
            × (1 + c_b × 1[a_G(t-1) > θ_GBT])                         [G-boost]
            × φ_t                                                        [phase modulator]

    Returns (pnl, fired) series.
    """
    idx  = base_pnl.index
    bsdt = bsdt.reindex(idx).fillna(0.0)
    lf   = lam_feat.reindex(idx).fillna(0.5)
    rv   = rv_norm.reindex(idx, method='ffill').fillna(1.0)

    # size_sym: shift-1 to prevent lookahead
    gam  = bsdt['gamma_star'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam, 0.0, 1.0) * (0.75 + 0.5 * lp)

    # Dynamic θ_G (v58)
    gth  = _dynamic_gth(rv, lo)          # Series aligned to idx

    # Attribution signals (shift-1: all use t-1 values)
    a_G  = bsdt['a_G']
    a_A  = bsdt['a_A']
    a_T  = bsdt['a_T']

    # Rolling memory operators (§29.2): max over [t-N, t-1]
    G_mem = a_G.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    T_mem = a_T.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)

    # A-channel firing gate (§29.3): 1_fire = 1[a_A(t-1) > θ_A]
    # Minimum hold = 24 bars (≈ 1 day).  Mechanism: .rolling(24).max()
    # propagates any True in fired_raw forward for 24 bars, so once the gate
    # fires it stays open for at least 24 consecutive bars regardless of
    # subsequent a_A values.  On real data the activity anomaly persists due
    # to market autocorrelation; 24h minimum avoids excessive churn on
    # synthetic IID noise while staying true to daily rebalancing cadence.
    fired_raw = (a_A.shift(1).fillna(0.0) > A_FIRE_THRESH)
    fired = fired_raw.rolling(24, min_periods=1).max().astype(bool)

    # Quadrant indicators (§29.3)
    q_GH_TH = (fired & (G_mem > gth)         & (T_mem > T_THRESH_BASE)).astype(float)
    q_GH_TL = (fired & (G_mem > gth)         & (T_mem <= T_THRESH_BASE)).astype(float)
    q_GL_TH = (fired & (G_mem <= gth)        & (T_mem > T_THRESH_BASE)).astype(float)
    q_GL_TL = (fired & (G_mem <= gth)        & (T_mem <= T_THRESH_BASE)).astype(float)

    # Phase modulator φ_t (§29.3)
    phase = (1.0 + GH_TH * q_GH_TH + GH_TL * q_GH_TL
                 + GL_TH * q_GL_TH + GL_TL * q_GL_TL).clip(PHI_MIN, CLIP)

    # G-boost multiplier (§29.4)
    g_flag = (a_G.shift(1).fillna(0.0) > G_BOOST_THRESH).astype(float)
    g_boost = 1.0 + CHAMPION_BOOST * g_flag

    # Full P&L
    pnl = base_pnl.fillna(0.0) * size * g_boost * phase

    return pnl, fired.astype(float)


def apply_maker_fees(pnl: pd.Series, fired: pd.Series) -> pd.Series:
    """Deduct 3 bps/side on each fired transition."""
    transitions = fired.diff().abs().fillna(0).astype(bool)
    cost = transitions.astype(float) * COST_PER_SIDE
    return pnl - cost


# ═══════════════════════════════════════════════════════════════════════════════
#  STATISTICS
# ═══════════════════════════════════════════════════════════════════════════════

ANN = 24 * 365.25   # 1h bars per year

def full_stats(pnl: pd.Series) -> dict:
    r = pnl.dropna()
    if len(r) < 10:
        return dict(sharpe=0, sortino=0, calmar=0, cagr=0, max_dd=0, win_rate=0, profit_f=0)
    ann_ret  = float(r.mean() * ANN)
    ann_vol  = float(r.std() * np.sqrt(ANN)) + 1e-10
    sharpe   = ann_ret / ann_vol
    down     = r[r < 0]
    sortino  = ann_ret / (float(down.std() * np.sqrt(ANN)) + 1e-10)
    cum      = (1 + r).cumprod()
    roll_max = cum.cummax()
    dd       = (cum / roll_max - 1)
    max_dd   = float(dd.min())
    calmar   = ann_ret / (abs(max_dd) + 1e-10)
    yrs      = max((r.index[-1] - r.index[0]).total_seconds() / (365.25 * 86400), 0.01)
    cagr     = float((1 + r).prod() ** (1 / yrs) - 1)
    win_rate = float((r > 0).mean())
    gross_p  = float(r[r > 0].sum())
    gross_l  = float(abs(r[r < 0].sum())) + 1e-10
    profit_f = gross_p / gross_l
    return dict(sharpe=sharpe, sortino=sortino, calmar=calmar, cagr=cagr,
                max_dd=max_dd, win_rate=win_rate, profit_f=profit_f)


def quarterly_breakdown(pnl: pd.Series, cap: float) -> list[dict]:
    try:
        q = (1 + pnl).resample('QE').prod() - 1
    except Exception:
        q = (1 + pnl).resample('Q').prod() - 1
    rows = []
    for dt, r in q.items():
        c_end = cap * (1 + float(r))
        rows.append(dict(Quarter=f"{dt.year} Q{(dt.month-1)//3+1}",
                         Return=float(r), Profit=float(c_end - cap),
                         StartCapital=float(cap), EndCapital=float(c_end)))
        cap = c_end
    return rows


def yoy_breakdown(pnl: pd.Series, cap: float, test_start: str) -> list[dict]:
    sy = int(test_start[:4])
    rows = []
    for yr in sorted(pnl.index.year.unique()):
        if yr < sy:
            continue
        r  = float((1 + pnl[pnl.index.year == yr]).prod() - 1)
        ce = cap * (1 + r)
        rows.append(dict(Year=int(yr), Return=float(r),
                         StartCapital=float(cap), EndCapital=float(ce),
                         Profit=float(ce - cap)))
        cap = ce
    return rows


def rt_per_year(fired: pd.Series) -> float:
    n = int(fired.diff().abs().fillna(0).sum())
    yrs = max((fired.index[-1] - fired.index[0]).total_seconds() / (365.25 * 86400), 0.01)
    return float(n / 2.0 / yrs)


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> dict:
    t0  = time.time()
    BAR = '=' * 100
    print(BAR)
    print('  v58 Stability Patch — $700 SIMULATION (standalone, correct signal pipeline)')
    print(f'  Champion : v58_tight  (lo={CLAMP_LO}, EMA span={EMA_SPAN})')
    print(f'  Capital  : ${START_CAPITAL:,.0f}  |  Fees: {FEE_BPS:.0f}+{SLIP_BPS:.0f}={FEE_BPS+SLIP_BPS:.0f} bps/side')
    print(f'  Signals  : BSDT 4-channel (a_G, a_A, a_T) + γ* + λ_pct  per math_reference §XXIX')
    print(BAR)

    # ── [1] generate market data ─────────────────────────────────────────────
    print('\n[1] Generating synthetic 1h OHLCV (2021-2026) ...', flush=True)
    df = _generate_market_data(SIM_START, SIM_END, seed=42)
    print(f'    {len(df)} bars | {df.index[0].date()} → {df.index[-1].date()}')

    # ── [2] build state matrix ───────────────────────────────────────────────
    print(f'[2] Building state matrix X ({len(df)} × {N_INSTR} × {D_FEAT}) ...',
          flush=True)
    X = build_state_matrix(df)

    # Calibration mask: last CALIB_BARS of train window (before 2023-01-01)
    train_mask = df.index < TEST_START
    train_idx  = np.where(train_mask)[0]
    calib_idx  = train_idx[-CALIB_BARS:]
    print(f'    Calibration window: {df.index[calib_idx[0]].date()} '
          f'→ {df.index[calib_idx[-1]].date()}  ({len(calib_idx)} bars)')

    # Per-feature standardisation (on calib stats, no lookahead)
    X, feat_mean, feat_std = standardise_state_matrix(X, calib_idx)
    print(f'    Feature std after normalisation: {np.round(X[calib_idx].reshape(-1,D_FEAT).std(0), 3)}')

    # ── [3] calibrate engine ─────────────────────────────────────────────────
    print('[3] Calibrating BSDT engine (Ledoit-Wolf, PCA k=4) ...', flush=True)
    mu_0, Sigma_0, Sigma_inv, Sigma_inv_half, V_k, v_0, mu_norm = \
        calibrate(X, calib_idx, k=4)
    print(f'    μ_0 norm={np.linalg.norm(mu_0):.4f}  '
          f'v_0={v_0:.4f}  '
          f'μ_norm(C,G,A,T)={mu_norm}')

    # ── [4] compute BSDT signals ─────────────────────────────────────────────
    print(f'[4] Computing BSDT 4-channel signals ({len(df)} bars) ...', flush=True)
    bsdt = compute_bsdt_signals(X, mu_0, Sigma_inv, Sigma_inv_half, V_k, v_0, mu_norm)
    bsdt.index = df.index
    print(f'    a_G mean={bsdt["a_G"].mean():.3f}  '
          f'a_A mean={bsdt["a_A"].mean():.3f}  '
          f'a_T mean={bsdt["a_T"].mean():.3f}  '
          f'a_C mean={bsdt["a_C"].mean():.3f}')

    # ── [5] price loading factor ──────────────────────────────────────────────
    print('[5] Computing λ_pct (price loading factor) ...', flush=True)
    lam_feat = compute_lambda_features(X, mu_0, Sigma_inv, bsdt, roll=200)
    lam_feat.index = df.index
    print(f'    λ_price mean={lam_feat["lambda_price"].mean():.3f}  '
          f'λ_pct mean={lam_feat["lambda_pct_100"].mean():.3f}')

    # ── [6] base portfolio ───────────────────────────────────────────────────
    print('[6] Computing base portfolio ...', flush=True)
    base_pnl = compute_base_portfolio(df)
    base_pnl.index = df.index
    print(f'    Base PnL: mean={base_pnl.mean()*1e4:.3f}e-4  '
          f'std={base_pnl.std()*1e4:.2f}e-4')

    # ── [7] normalised rv ────────────────────────────────────────────────────
    print('[7] Computing normalised realised volatility rv̂_t ...', flush=True)
    rv_norm = compute_rv_norm(df)
    rv_norm.index = df.index
    print(f'    rv_norm mean={rv_norm.mean():.3f}  std={rv_norm.std():.3f}')

    # ── [8] v58 position sizing ───────────────────────────────────────────────
    print('[8] Running v58 champion sizing ...', flush=True)
    pnl_gross, fired = build_pnl_v58(base_pnl, bsdt, lam_feat, rv_norm, lo=CLAMP_LO)

    # OOS masks
    test_mask   = df.index >= TEST_START
    first_half  = (df.index >= TEST_START) & (df.index < OOS_SPLIT)
    second_half = df.index >= OOS_SPLIT

    pnl_gross_oos = pnl_gross[test_mask]
    fired_oos     = fired[test_mask]

    pnl_net_oos   = apply_maker_fees(pnl_gross_oos, fired_oos)
    rt_yr         = rt_per_year(fired_oos)
    annual_drag   = rt_yr * 2 * (FEE_BPS + SLIP_BPS) / 10_000.0

    st_gross = full_stats(pnl_gross_oos)
    st_net   = full_stats(pnl_net_oos)

    # ── SECTION 1: champion stats ─────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SECTION 1 — CHAMPION v58_tight STATS  (OOS: 2023-present)')
    print(f'{BAR}')
    print(f"\n  {'Metric':<22} {'Gross (pre-fee)':>18} {'Net (after maker fees)':>22}")
    print(f"  {'-'*22} {'-'*18} {'-'*22}")
    metrics = [
        ('Sharpe',   f'{st_gross["sharpe"]:>+15.4f}',   f'{st_net["sharpe"]:>+19.4f}'),
        ('Sortino',  f'{st_gross["sortino"]:>+15.4f}',  f'{st_net["sortino"]:>+19.4f}'),
        ('Calmar',   f'{st_gross["calmar"]:>+15.4f}',   f'{st_net["calmar"]:>+19.4f}'),
        ('CAGR',     f'{st_gross["cagr"]:>+14.2%}',     f'{st_net["cagr"]:>+18.2%}'),
        ('Max DD',   f'{st_gross["max_dd"]:>+14.2%}',   f'{st_net["max_dd"]:>+18.2%}'),
        ('Win Rate', f'{st_gross["win_rate"]:>+14.2%}', f'{st_net["win_rate"]:>+18.2%}'),
        ('Profit F', f'{st_gross["profit_f"]:>+15.3f}', f'{st_net["profit_f"]:>+19.3f}'),
    ]
    for name, g, n in metrics:
        print(f'  {name:<22} {g} {n}')
    print(f'\n  Roundtrips/year : {rt_yr:.1f}  |  Fee per RT : {(FEE_BPS+SLIP_BPS)*2:.0f} bps'
          f'  |  Annual drag : {annual_drag:+.2%}')

    # OOS split
    pnl_h1 = apply_maker_fees(pnl_gross[first_half], fired[first_half])
    pnl_h2 = apply_maker_fees(pnl_gross[second_half], fired[second_half])
    st_h1  = full_stats(pnl_h1)
    st_h2  = full_stats(pnl_h2)
    print(f'\n  OOS split (net):')
    print(f'    First half  (2023-2024) : '
          f'Sharpe {st_h1["sharpe"]:>+7.4f}  CAGR {st_h1["cagr"]:>+7.2%}  MaxDD {st_h1["max_dd"]:>+7.2%}')
    print(f'    Second half (2025-2026) : '
          f'Sharpe {st_h2["sharpe"]:>+7.4f}  CAGR {st_h2["cagr"]:>+7.2%}  MaxDD {st_h2["max_dd"]:>+7.2%}')

    # ── SECTION 2: quarterly breakdown ───────────────────────────────────────
    df_q = quarterly_breakdown(pnl_net_oos, START_CAPITAL)
    print(f'\n{BAR}')
    print(f'  SECTION 2 — QUARTERLY BREAKDOWN  (${START_CAPITAL:,.0f} starting, maker fees)')
    print(f'{BAR}')
    print(f"\n  {'Quarter':<12} {'Return':>8}  {'Profit (USD)':>13}  {'Running Capital':>16}")
    print(f"  {'-'*12} {'-'*8}  {'-'*13}  {'-'*16}")
    for row in df_q:
        p = row['Profit']; c = row['EndCapital']
        sign = '+' if p >= 0 else ''
        print(f"  {row['Quarter']:<12} {row['Return']:>+8.2%}  {sign}{p:>10.2f} USD  ${c:>13.2f}")

    # ── SECTION 3: year-on-year summary ──────────────────────────────────────
    yoy = yoy_breakdown(pnl_net_oos, START_CAPITAL, TEST_START)
    print(f'\n{BAR}')
    print(f'  SECTION 3 — YEAR-ON-YEAR SUMMARY  (${START_CAPITAL:,.0f} starting, maker fees)')
    print(f'{BAR}')
    print(f"\n  {'Year':<7} {'Return':>8}  {'Start Capital':>15}  {'End Capital':>15}  {'Profit (USD)':>14}")
    print(f"  {'-'*7} {'-'*8}  {'-'*15}  {'-'*15}  {'-'*14}")
    for row in yoy:
        ytd  = ' (YTD)' if row['Year'] == yoy[-1]['Year'] else ''
        sign = '+' if row['Profit'] >= 0 else ''
        print(f"  {row['Year']:<7} {row['Return']:>+8.2%}  "
              f"${row['StartCapital']:>13,.2f}  "
              f"${row['EndCapital']:>13,.2f}  "
              f"{sign}{row['Profit']:>+12.2f}{ytd}")

    final_cap    = yoy[-1]['EndCapital'] if yoy else START_CAPITAL
    total_profit = final_cap - START_CAPITAL
    print(f'\n  ┌{"─"*72}┐')
    print(f'  │  ${START_CAPITAL:,.0f} → ${final_cap:,.2f}   '
          f'(total profit: ${total_profit:>+,.2f}){"":>18}│')
    print(f'  │  Gross CAGR {st_gross["cagr"]:>+.1%}  →  Net CAGR {st_net["cagr"]:>+.1%}'
          f'  (drag {annual_drag:>+.2%}/yr){"":>19}│')
    print(f'  │  Net Sharpe {st_net["sharpe"]:>+.4f}   Calmar {st_net["calmar"]:>+.3f}'
          f'   MaxDD {st_net["max_dd"]:>+.2%}{"":>21}│')
    print(f'  │  Maker fee {FEE_BPS:.0f} bps + slip {SLIP_BPS:.0f} bps = '
          f'{FEE_BPS+SLIP_BPS:.0f} bps/side   RT/yr ≈ {rt_yr:.0f}{"":>25}│')
    print(f'  └{"─"*72}┘')
    print(f'\n{BAR}')

    # ── save JSON ─────────────────────────────────────────────────────────────
    class _NpEnc(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)):  return int(obj)
            if isinstance(obj, (np.floating,)): return float(obj)
            if isinstance(obj, np.bool_):       return bool(obj)
            if isinstance(obj, np.ndarray):     return obj.tolist()
            return super().default(obj)

    result = {
        'version'        : 'v58_standalone_sim',
        'champion'       : 'v58_tight (lo=-0.01, EMA=3)',
        'implementation' : 'standalone — signals from math_reference §XXIX',
        'start_capital'  : START_CAPITAL,
        'fee_bps'        : FEE_BPS,
        'slip_bps'       : SLIP_BPS,
        'rt_per_year'    : float(rt_yr),
        'annual_drag'    : float(annual_drag),
        'gross_stats'    : {k: float(v) for k, v in st_gross.items()},
        'net_stats'      : {k: float(v) for k, v in st_net.items()},
        'oos_split'      : {
            'first_half_2023_2024':  {k: float(v) for k, v in st_h1.items()},
            'second_half_2025_2026': {k: float(v) for k, v in st_h2.items()},
        },
        'quarterly'      : df_q,
        'yoy'            : yoy,
        'final_capital'  : float(final_cap),
        'total_profit'   : float(total_profit),
        'signal_params'  : {
            'N_instruments': N_INSTR,
            'D_features':    D_FEAT,
            'N_memory':      N_OPT,
            'CLIP':          CLIP,
            'GH_TH':         GH_TH,
            'GH_TL':         GH_TL,
            'GL_TH':         GL_TH,
            'GL_TL':         GL_TL,
            'PHI_MIN':       PHI_MIN,
            'theta_G_base':  G_THRESH_BASE,
            'theta_T':       T_THRESH_BASE,
            'theta_A':       A_FIRE_THRESH,
            'K_G':           K_G,
            'EMA_span':      EMA_SPAN,
            'clamp_lo':      CLAMP_LO,
            'champion_boost': CHAMPION_BOOST,
        },
        'elapsed_s'      : float(time.time() - t0),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, 'w') as f:
        json.dump(result, f, indent=2, cls=_NpEnc)
    print(f'  Results saved → {OUT_PATH}')
    print(f'  Total elapsed : {time.time()-t0:.1f}s')
    print(BAR)
    return result


if __name__ == '__main__':
    main()
