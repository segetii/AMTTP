"""
Crypto BSDT v10 — γ-Aware Dynamic Allocation
===============================================

v9 lesson:
  Drift-only validity gate raised VALID% to 48–61% and restored sample
  sizes to n=47–98. ETH/SOL Sharpe +1.357. Allocation is still static:
  all strategies contribute equally regardless of system state (γ level).

v10 — Strategy-Specific γ Modulation:
  position_i(t) = base_position_i(t) × f_i(γ_clipped(t))

  f(γ) by strategy type:
    Directional (A_dir)   : f(γ) = 1 − γ   — reduce when system near saturation
    Mean-reversion (pairs): f(γ) = γ      — amplify when stress peaks (reversion set-up)
    Macro (ALT/BTC)       : f(γ) = 1       — Ω/A driven, insensitive to γ

  Intuition:
    γ = 1/(1 + ĀΩ_20d) — high when system near saturation (Ω high repeatedly)
    High γ → late-stage crash risk for directional
    High γ → pairs far from anchor → better reversion set-up

  γ clipped to [0.10, 0.90] — prevents full position elimination.

v10 — Cross-Sectional Dynamic Weighting (combined portfolio):
  Weights ∝ rolling 126d Sharpe per γ-adjusted strategy (causal).
  Negative-Sharpe strategies get zero weight.
  Combined PnL = Σ_i w_i(t−1) × pos_i(t−1) × ret_i(t)

Full 5-layer architecture unchanged from v9; γ is Layer 6:
  Layer 1: Ω — timing gate
  Layer 2: A — intensity gate
  Layer 3: UDL MDN — geometry (EQUIL / DEGEN / STRUCT)
  Layer 4: Drift gate only  |̄z_60d| < 1.0  (anchored z)
  Layer 5: POA-scaled sizing
  Layer 6 [NEW]: γ-modulation × cross-sectional Sharpe weights
"""

import numpy as np
import pandas as pd
import json
import warnings
warnings.filterwarnings('ignore')
import yfinance as yf
from numpy.linalg import eigh
from scipy import stats

OUT_DIR     = r"C:\amttp\research\adaptive-friction\pipeline\results"
TRAIN_START = '2021-01-01'
TRAIN_END   = '2022-12-31'
TEST_START  = '2023-01-01'

# ─── constants ───────────────────────────────────────────────────────────────
BETA_VEL_THRESH    = 0.30   # β changed >30% of level in 21d → STRUCTURAL
POA_LOW            = 0.30
POA_HIGH           = 0.80
STRUCT_SIZE_SCALE  = 0.50

# ─── manifold validity thresholds ────────────────────────────────────────────
DRIFT_WINDOW  = 60    # days over which to measure z-score drift
EFF_WINDOW    = 60    # days over which to measure reversion effectiveness
DRIFT_THRESH  = 1.00  # |z̄_60d| above this → manifold shifted (1σ for anchored z)
EFF_THRESH    = 0.0   # rev_eff_60d below this → reversion not paying

# ─── γ-aware allocation (v10) ─────────────────────────────────────────────────────
GAMMA_CLIP_LOW   = 0.10   # floor — never fully zero-out directional
GAMMA_CLIP_HIGH  = 0.90   # cap   — never fully saturate reversion
GAMMA_SCORE_WIN  = 126    # ~6-month rolling Sharpe window for cross-sectional scoring


# ─────────────────────────────────────────────────────────────────────────────
#  DATA
# ─────────────────────────────────────────────────────────────────────────────
def fetch_and_prepare():
    print("  Fetching BTC, ETH, SOL, BNB ...")
    raw = {}
    for tk in ['BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD']:
        raw[tk] = yf.download(tk, start='2020-06-01', progress=False,
                              auto_adjust=True)['Close'].squeeze()
    df = pd.DataFrame({
        'btc': raw['BTC-USD'], 'eth': raw['ETH-USD'],
        'sol': raw['SOL-USD'], 'bnb': raw['BNB-USD'],
    }).dropna()
    for a in ['btc', 'eth', 'sol', 'bnb']:
        df[f'ret_{a}'] = np.log(df[a] / df[a].shift(1))
        df[f'log_{a}'] = np.log(df[a])
    df['alt_basket']     = np.exp((df['log_eth'] + df['log_sol'] + df['log_bnb']) / 3)
    df['log_alt_basket'] = np.log(df['alt_basket'])
    df['ret_alt_basket'] = np.log(df['alt_basket'] / df['alt_basket'].shift(1))
    df['alt_ret_eq']  = (df['ret_eth'] + df['ret_sol'] + df['ret_bnb']) / 3
    df['btc_dom']     = df['ret_btc'] - df['alt_ret_eq']
    df['cross_disp']  = df[['ret_btc', 'ret_eth', 'ret_sol', 'ret_bnb']].std(axis=1)
    for a in ['btc', 'eth', 'sol', 'bnb']:
        df[f'vol_{a}'] = df[f'ret_{a}'].rolling(20).std() * np.sqrt(252)
    def z(s, w=252):
        mu = s.rolling(w, min_periods=60).mean()
        sd = s.rolling(w, min_periods=60).std()
        return (s - mu) / (sd + 1e-9)
    for c in ['ret_btc','ret_eth','ret_sol','ret_bnb',
              'vol_btc','vol_eth','btc_dom','cross_disp']:
        df[f'{c}_z'] = z(df[c])
    for h in [3, 5, 7]:
        df[f'ret{h}_eth'] = df['ret_eth'].rolling(h).sum()
        df[f'ret{h}_btc'] = df['ret_btc'].rolling(h).sum()
    df = df.dropna()
    print(f"  Data: {df.index[0].date()} → {df.index[-1].date()}  n={len(df)}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  BSDT ENGINE (unchanged from v5)
# ─────────────────────────────────────────────────────────────────────────────
def compute_bsdt(df, features, window=60):
    X = df[features].values
    T = len(X)
    omega = np.full(T, np.nan)
    mfls  = np.full(T, np.nan)
    gamma = np.full(T, np.nan)
    for t in range(window, T):
        wd = X[t - window:t + 1]
        wd = wd[np.all(np.isfinite(wd), axis=1)]
        if len(wd) < window // 2:
            continue
        corr = np.corrcoef(wd.T)
        if not np.all(np.isfinite(corr)):
            corr = np.where(np.isfinite(corr), corr, 0.0)
            np.fill_diagonal(corr, 1.0)
        W = np.abs(corr)
        W = W / (W.sum(axis=1, keepdims=True) + 1e-12)
        eigvals, _ = eigh(W)
        lam_max  = eigvals[-1]
        omega[t] = 0.9 * lam_max
        mfls[t]  = np.linalg.norm(X[t] - wd.mean(axis=0)) * lam_max
        oh       = omega[max(0, t-20):t+1]
        gamma[t] = 1.0 / (1.0 + oh[np.isfinite(oh)].mean())
    idx = df.index
    return (pd.Series(omega, index=idx),
            pd.Series(mfls,  index=idx),
            pd.Series(gamma, index=idx))


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE (unchanged from v5)
# ─────────────────────────────────────────────────────────────────────────────
def detect_phase(omega, ret7, ret3, btc_dom_z):
    q50   = omega.expanding(60).quantile(0.50)
    q75   = omega.expanding(60).quantile(0.75)
    elev  = omega >= q50
    high  = omega >= q75
    crash = elev & ((ret7 < -0.10) | (btc_dom_z > 1.5)) & (ret3 < 0)
    recov = high & (ret3 > 0.03) & ~crash
    raw   = np.ones(len(omega), dtype=int)
    raw[~elev.values]   = 0
    raw[crash.values]   = 2
    raw[recov.values]   = 3
    return pd.Series(raw, index=omega.index)


# ─────────────────────────────────────────────────────────────────────────────
#  ACTIVITY (unchanged from v5 — keep fast ΔA)
# ─────────────────────────────────────────────────────────────────────────────
def compute_activity_signals(mfls, gamma):
    A       = mfls / (gamma + 1e-9)
    A_rank  = A.expanding(60).rank(pct=True)
    dA_fast = A.diff(1).rolling(2).mean()
    dA_rank = dA_fast.expanding(60).rank(pct=True)
    return A, A_rank, dA_fast, dA_rank


# ─────────────────────────────────────────────────────────────────────────────
#  v8 SPREAD COMPUTATION — training-anchored z-score
# ─────────────────────────────────────────────────────────────────────────────
def compute_rolling_spread_v8(log_a, log_b, ret_a, ret_b,
                               train_mask,
                               beta_window=252):
    """
    Computes spread using rolling OLS β (252d).
    Z-score uses TRAINING-PERIOD μ and σ — fixed after train end.

    This is the key v8 fix: rolling z-score adapts to spread drift and
    masks regime changes. Anchoring to training μ/σ makes z_t a genuine
    out-of-sample deviation from the learned equilibrium manifold.

    If a pair reprices permanently (e.g. ETH/BNB 2023+), z_t trends
    away from zero → drift gate fires → pair auto-disabled.
    If a pair is healthy (e.g. ETH/SOL), z_t stays near zero despite
    any short-term moves, and the validity filter stays open.

    Parameters
    ----------
    train_mask : boolean pd.Series aligned to log_a.index
    beta_window : rolling OLS window (252d)

    Returns dict of pd.Series indexed on log_a.index.
    """
    la = log_a.values
    lb = log_b.values
    ra = ret_a.values
    rb = ret_b.values
    n  = len(la)

    spread     = np.full(n, np.nan)
    betas      = np.full(n, np.nan)

    # ── Step 1: rolling OLS β and spread ─────────────────────────────────
    for t in range(beta_window, n):
        wla = la[t - beta_window:t]
        wlb = lb[t - beta_window:t]
        X   = np.column_stack([np.ones(beta_window), wlb])
        try:
            coefs       = np.linalg.lstsq(X, wla, rcond=None)[0]
            alpha, beta = coefs[0], coefs[1]
            spread[t]   = la[t] - alpha - beta * lb[t]
            betas[t]    = beta
        except Exception:
            pass

    idx    = log_a.index
    S_ser  = pd.Series(spread, index=idx)
    B_ser  = pd.Series(betas, index=idx)

    # ── Step 3: TRAINING-ANCHORED z-score ──────────────────────────────────
    # μ and σ fixed from training period — makes z genuinely out-of-sample
    train_S  = S_ser[train_mask].dropna()
    mu_train = train_S.mean()
    sd_train = max(train_S.std(), 1e-9)
    z        = (S_ser - mu_train) / sd_train

    # ── Step 4: spread variance ratio (flat-spread detector) ─────────────
    std_30  = S_ser.rolling(30, min_periods=15).std()
    std_252 = S_ser.rolling(252, min_periods=60).std()
    var_ratio = std_30 / (std_252 + 1e-9)

    # ── Step 5: β velocity (structural-break detector) ───────────────────
    beta_mean_abs = B_ser.abs().rolling(252, min_periods=60).mean()
    beta_chg      = B_ser.diff(21).abs()
    beta_velocity = beta_chg / (beta_mean_abs + 1e-9)

    # ── Step 6: Pair Omega Alignment — geometry-based stability ──────────
    # POA = rolling |corr(ret_a, ret_b)| over 60d
    # We compute manually to avoid a 2-step rolling issue
    ra_s  = pd.Series(ra, index=idx)
    rb_s  = pd.Series(rb, index=idx)
    poa   = ra_s.rolling(60, min_periods=30).corr(rb_s).abs()

    # ── Step 7: spread return (for PnL simulation) ───────────────────────
    b_filled = B_ser.fillna(B_ser.median())
    ra_ser   = pd.Series(ra, index=idx)
    rb_ser   = pd.Series(rb, index=idx)
    sret     = (ra_ser - b_filled * rb_ser) / (1.0 + b_filled.abs() + 1e-9)

    return dict(
        z=z, spread=S_ser, betas=B_ser,
        var_ratio=var_ratio, beta_velocity=beta_velocity,
        poa=poa, sret=sret
    )


# ─────────────────────────────────────────────────────────────────────────────
#  v6 CLASSIFIER — UDL Magnitude-Direction-Novelty (MDN) decomposition
# ─────────────────────────────────────────────────────────────────────────────
class SpreadUDLClassifier:
    """
    Fit on training spread windows, then classify each day via MDN decomposition.

    Each day t → window spread[t-W+1:t+1] ∈ ℝ^W → 14-dim feature vector
    via 4 spectral operators:

      Stat  [0:5]  : variance, 8-bin entropy, Hellinger-from-N(0,1), skewness, kurtosis
      Chaos [5:8]  : lag-1 autocorr, ac1²+ac2², Lyapunov proxy (diffs.std/std)
      Freq  [8:11] : spectral entropy, dominant energy ratio, spectral centroid
      Recon [11:14]: |linear slope|, residual variance, mean abs curvature

    MDN decomposition (fitted on training windows):
      centroid_    : mean feature vector → normal operating point
      ref_dirs_    : top-K SVD directions of deviation space
      thresholds_  : var_low (p10), mag_low (p10), novelty_high (p85)

    States:
      0 = EQUILIBRIUM  : normal magnitude + known direction → revert in full
      1 = DEGENERATE   : spread is flat/trivial (low variance OR low magnitude)
      2 = STRUCTURAL   : deviation is in a direction never seen in training
    """

    LAW_SLICES = [(0, 5), (5, 8), (8, 11), (11, 14)]
    N_FEAT     = 14

    def __init__(self, window: int = 20, n_ref_dirs: int = 100):
        self.window     = window
        self.n_ref_dirs = n_ref_dirs
        self.centroid_  = None
        self.ref_dirs_  = None
        self.thresholds_: dict = {}

    @staticmethod
    def _extract(x: np.ndarray) -> np.ndarray:
        """14-dim feature vector from raw window x ∈ ℝ^W."""
        from scipy.special import erf
        eps = 1e-10
        w   = len(x)
        f   = np.zeros(14)

        # ── Stat [0:5] ────────────────────────────────────────────────────
        var_ = x.var()
        f[0] = var_

        hist, _ = np.histogram(x, bins=8)
        p_h = hist / (hist.sum() + eps)
        p_h = np.clip(p_h, eps, 1.0)
        f[1] = -np.sum(p_h * np.log(p_h))

        mu_x   = x.mean(); std_x = x.std() + eps
        x_std  = (x - mu_x) / std_x
        h2, edges = np.histogram(x_std, bins=8)
        p_emp  = np.clip(h2 / (h2.sum() + eps), eps, 1.0)
        p_ref  = np.diff(0.5 * (1.0 + erf(edges / np.sqrt(2))))
        p_ref  = np.clip(p_ref / (p_ref.sum() + eps), eps, 1.0)
        f[2]   = np.sqrt(0.5 * np.sum((np.sqrt(p_emp) - np.sqrt(p_ref)) ** 2))

        if std_x > eps:
            z3    = (x - x.mean()) / std_x
            f[3]  = np.mean(z3 ** 3)
            f[4]  = np.mean(z3 ** 4) - 3.0

        # ── Chaos [5:8] ──────────────────────────────────────────────────
        if w >= 3:
            mu     = x.mean()
            denom  = (x - mu) @ (x - mu) + eps
            f[5]   = ((x[:-1] - mu) @ (x[1:] - mu)) / denom   # ac1
            ac2    = ((x[:-2] - mu) @ (x[2:] - mu)) / denom if w >= 4 else 0.0
            f[6]   = f[5] ** 2 + ac2 ** 2                       # ac energy
            dx     = np.diff(x)
            f[7]   = dx.std() / (x.std() + eps)                 # Lyapunov proxy

        # ── Freq [8:11] ──────────────────────────────────────────────────
        xf       = x - x.mean()
        psd      = np.abs(np.fft.rfft(xf)[1:]) ** 2
        psd_sum  = psd.sum() + eps
        pn       = np.clip(psd / psd_sum, eps, 1.0)
        f[8]     = -np.sum(pn * np.log(pn))                     # spectral entropy
        f[9]     = psd.max() / psd_sum                          # dominant power ratio
        freqs    = np.arange(1, len(psd) + 1, dtype=float)
        f[10]    = (freqs * pn).sum()                            # spectral centroid

        # ── Recon [11:14] ────────────────────────────────────────────────
        t_       = np.linspace(0.0, 1.0, w)
        tc       = t_ - t_.mean(); xc = x - x.mean()
        slope    = (tc @ xc) / (tc @ tc + eps)
        f[11]    = abs(slope)
        resid    = xc - slope * tc
        f[12]    = resid.var()
        if w >= 3:
            f[13] = np.abs(np.diff(x, n=2)).mean()              # mean curvature

        return f

    def fit(self, spread_series: pd.Series) -> 'SpreadUDLClassifier':
        """Fit on training spread; derive centroid, reference directions, thresholds."""
        w    = self.window
        vals = spread_series.dropna().values
        if len(vals) < w + 20:
            raise ValueError(f"Training series too short: {len(vals)}")

        n_wins = len(vals) - w + 1
        F      = np.array([self._extract(vals[i:i + w]) for i in range(n_wins)])
        var_w  = np.array([vals[i:i + w].var() for i in range(n_wins)])

        self.centroid_ = F.mean(axis=0)
        dev    = F - self.centroid_
        norms  = np.linalg.norm(dev, axis=1, keepdims=True)
        norms  = np.where(norms < 1e-10, 1.0, norms)
        unit_d = dev / norms

        k                = min(self.n_ref_dirs, len(unit_d))
        _, _, Vt         = np.linalg.svd(unit_d, full_matrices=False)
        self.ref_dirs_   = Vt[:k]           # (k, N_FEAT)

        mag_all  = np.linalg.norm(dev, axis=1)
        cos_all  = unit_d @ self.ref_dirs_.T
        nov_all  = 1.0 - cos_all.max(axis=1)

        self.thresholds_ = {
            'var_low':      float(np.percentile(var_w,   10)),
            'mag_low':      float(np.percentile(mag_all, 10)),
            'novelty_high': float(np.percentile(nov_all, 85)),
        }
        return self

    def _classify_one(self, win: np.ndarray):
        f    = self._extract(win)
        dev  = f - self.centroid_
        mag  = float(np.linalg.norm(dev))
        var_ = float(win.var())

        if mag < 1e-10:
            return 1, mag, 1.0

        unit_dev = dev / mag
        novelty  = float(1.0 - (self.ref_dirs_ @ unit_dev).max())

        if var_ <= self.thresholds_['var_low'] or mag <= self.thresholds_['mag_low']:
            return 1, mag, novelty      # DEGENERATE — flat or trivially small
        if novelty >= self.thresholds_['novelty_high']:
            return 2, mag, novelty      # STRUCTURAL — direction unprecedented
        return 0, mag, novelty          # EQUILIBRIUM

    def classify_series(self, spread_series: pd.Series):
        """
        Returns (state_s, mag_s, novelty_s) as pd.Series on spread_series.index.
        Days before window-1 default to DEGENERATE (state=1).
        """
        w    = self.window
        vals = spread_series.values
        n    = len(vals)
        state   = np.ones(n, dtype=int)   # default DEGENERATE
        mag     = np.full(n, np.nan)
        novelty = np.full(n, np.nan)

        for t in range(w - 1, n):
            win = vals[t - w + 1: t + 1]
            if not np.all(np.isfinite(win)):
                continue
            st, mg, nv  = self._classify_one(win)
            state[t]    = st
            mag[t]      = mg
            novelty[t]  = nv

        idx = spread_series.index
        return (
            pd.Series(state,   index=idx, name='udl_state'),
            pd.Series(mag,     index=idx, name='udl_mag'),
            pd.Series(novelty, index=idx, name='udl_novelty'),
        )


# ─────────────────────────────────────────────────────────────────────────────
#  v7 MANIFOLD VALIDITY (Layer 4)
# ─────────────────────────────────────────────────────────────────────────────
def compute_manifold_validity(z_spread, sret):
    """
    v9: Drift-only validity gate (rev_eff gate removed).

    Test — Drift gate:
        drift = |rolling_mean(z, DRIFT_WINDOW)|
        If > DRIFT_THRESH: equilibrium level has shifted → invalid

    Rev_eff computed and returned for diagnostics only — NOT used in valid.

    Returns
    -------
    valid     : pd.Series int   (1 = drift test passes, 0 = fails)
    z_drift   : pd.Series float  absolute rolling mean of z
    rev_eff   : pd.Series float  rolling reversion PnL (diagnostic only)
    """
    drift    = z_spread.rolling(DRIFT_WINDOW, min_periods=30).mean().abs()
    drift_ok = drift < DRIFT_THRESH

    rev_sig   = -np.sign(z_spread.shift(1))
    daily_pnl = rev_sig * sret
    rev_eff   = daily_pnl.rolling(EFF_WINDOW, min_periods=30).mean()
    # NOTE: rev_eff NOT included in valid — see module docstring for rationale

    valid = drift_ok.astype(int)
    return (
        pd.Series(valid.values,    index=z_spread.index, name='manifold_valid'),
        pd.Series(drift.values,    index=z_spread.index, name='z_drift'),
        pd.Series(rev_eff.values,  index=z_spread.index, name='rev_eff'),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  v6 BASELINE ROUTER (no validity filter — for ablation comparison)
# ─────────────────────────────────────────────────────────────────────────────
def route_pair_v6_baseline(omega, A_rank, z_spread, udl_state, poa, z_threshold=1.0):
    """Same as v6 route_pair: UDL gating, no manifold validity check."""
    omega_q50   = omega.expanding(60).quantile(0.50)
    gate        = (omega >= omega_q50) & (A_rank >= 0.33) & (z_spread.abs() > z_threshold)
    state_v = udl_state.values; z_v = z_spread.values
    poa_v   = poa.fillna(0.5).values; g_v = gate.values
    pos = np.zeros(len(z_v))
    for i in range(len(z_v)):
        if not g_v[i] or state_v[i] == 1:
            continue
        direction = -np.sign(z_v[i])
        base_size = min(abs(z_v[i]), 2.0) / 2.0
        if state_v[i] == 0:
            poa_scale = np.clip((poa_v[i] - POA_LOW) / (POA_HIGH - POA_LOW), 0, 1)
            pos[i]    = direction * base_size * poa_scale
        elif state_v[i] == 2:
            pos[i]    = direction * base_size * STRUCT_SIZE_SCALE
    return pd.Series(pos, index=omega.index).clip(-1, 1)



def route_pair_v7(omega, A_rank, z_spread, udl_state, poa,
                  manifold_valid, z_threshold=1.0):
    """
    5 gates (all must pass):
      1. Ω ≥ Q50        (system active)
      2. A_rank ≥ 0.33  (move strong enough)
      3. |z| > 1.0      (spread extreme enough)
      4. udl_state ≠ 1  (not degenerate window)
      5. manifold_valid (drift gate only — anchored z)

    Sizing:
      EQUILIBRIUM  → direction × min(|z|,2)/2 × POA_scale
      STRUCTURAL   → direction × min(|z|,2)/2 × STRUCT_SIZE_SCALE
    """
    omega_q50   = omega.expanding(60).quantile(0.50)
    omega_gate  = omega >= omega_q50
    active_gate = A_rank >= 0.33
    spread_gate = z_spread.abs() > z_threshold
    mval_gate   = manifold_valid.astype(bool)
    gate        = omega_gate & active_gate & spread_gate & mval_gate

    state_v = udl_state.values
    z_v     = z_spread.values
    poa_v   = poa.fillna(0.5).values
    g_v     = gate.values

    pos = np.zeros(len(z_v))
    for i in range(len(z_v)):
        if not g_v[i] or state_v[i] == 1:
            continue
        direction = -np.sign(z_v[i])
        base_size = min(abs(z_v[i]), 2.0) / 2.0

        if state_v[i] == 0:
            poa_scale = np.clip((poa_v[i] - POA_LOW) / (POA_HIGH - POA_LOW), 0, 1)
            pos[i]    = direction * base_size * poa_scale
        elif state_v[i] == 2:
            pos[i]    = direction * base_size * STRUCT_SIZE_SCALE

    return pd.Series(pos, index=omega.index).clip(-1, 1)


# ─────────────────────────────────────────────────────────────────────────────
#  BTC/ALT MACRO ROTATION (unchanged from v5)
# ─────────────────────────────────────────────────────────────────────────────
def route_btcalt_macro(df, omega, A_rank, dA_rank):
    omega_q50  = omega.expanding(60).quantile(0.50)
    omega_gate = omega >= omega_q50
    active     = A_rank >= 0.33

    dom_z  = df['btc_dom_z']
    disp_z = df['cross_disp_z']

    btc_flight   = omega_gate & active & (dom_z > 1.0)
    alt_season   = omega_gate & active & (dom_z < -1.0) & (disp_z > 1.0)
    da_active    = dA_rank >= 0.50
    btc_flight_w = omega_gate & active & da_active & (dom_z > 0.5)
    alt_season_w = omega_gate & active & da_active & (dom_z < -0.5) & (disp_z > 0.5)

    pos_btc = pd.Series(0.0, index=df.index)
    pos_alt = pd.Series(0.0, index=df.index)

    pos_btc[btc_flight]   = np.minimum(dom_z[btc_flight], 2.0) / 2.0
    pos_btc[btc_flight_w & ~btc_flight] = 0.5 * np.minimum(
        dom_z[btc_flight_w & ~btc_flight], 1.0)
    pos_alt[alt_season]   = 1.0
    pos_alt[alt_season_w & ~alt_season] = 0.5

    return pos_btc.clip(0, 1), pos_alt.clip(0, 1)



# ─────────────────────────────────────────────────────────────────────────────
#  γ-AWARE ALLOCATION FUNCTIONS (v10)
# ─────────────────────────────────────────────────────────────────────────────
def apply_gamma_mod(pos, gamma_series, mode='macro'):
    """
    Modulate position by strategy-specific adaptive friction term.

    mode='directional' : pos x (1 - gamma_clipped)
        Directional strategies profit in early/mid regimes.
        Reduce as gamma rises (system near saturation = late-stage crash risk).
    mode='reversion'   : pos x gamma_clipped
        Reversion strategies profit after stress peaks.
        Amplify when gamma high (large displacement from anchor = better set-up).
    mode='macro'       : pos unchanged
        Macro rotation driven by Omega and A; less sensitive to gamma level.

    Clipping (GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH) prevents full zero-out at extremes.
    """
    gc = gamma_series.reindex(pos.index).clip(GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH)
    if mode == 'directional':
        return (pos * (1.0 - gc)).clip(-1, 1)
    elif mode == 'reversion':
        return (pos * gc).clip(-1, 1)
    else:
        return pos.clip(-1, 1)


def get_daily_pnl(pos, ret):
    """Causal daily PnL: position(t-1) x ret(t). No lookahead."""
    return pos.shift(1).fillna(0) * ret.reindex(pos.index).fillna(0)


def compute_cs_weights(pnl_dict, window=126):
    """
    Rolling cross-sectional Sharpe weights for dynamic portfolio allocation.

    Backward-looking rolling Sharpe per strategy, normalized to portfolio weights.
    Negative-Sharpe strategies get zero weight (no short-selling of strategies).
    Equal-weight fallback when all Sharpes are non-positive.

    Parameters
    ----------
    pnl_dict : dict label -> pd.Series daily PnL (full history, causal)
    window   : rolling window in days

    Returns
    -------
    dict label -> pd.Series weights (sum to 1 cross-sectionally each day)
    """
    sharpes = {}
    for label, pnl in pnl_dict.items():
        mu = pnl.rolling(window, min_periods=window // 2).mean()
        sd = pnl.rolling(window, min_periods=window // 2).std()
        sharpes[label] = mu / (sd + 1e-12) * np.sqrt(252)
    df_sh = pd.DataFrame(sharpes).clip(lower=0.0)
    total = df_sh.sum(axis=1)
    n     = len(pnl_dict)
    weights = {}
    for label in pnl_dict:
        w = df_sh[label] / total.replace(0, float('nan'))
        weights[label] = w.fillna(1.0 / n)
    return weights


def simulate_from_pnl(pnl_series, label=""):
    """
    Compute simulation stats directly from daily PnL stream.
    Used for the dynamic combined portfolio (multiple return streams).
    """
    import numpy as _np
    pnl      = pnl_series.fillna(0).values
    cum      = _np.cumprod(1.0 + pnl)
    active   = pnl[pnl != 0]
    sharpe   = float(active.mean() / (_np.std(active) + 1e-12) * _np.sqrt(252)) if len(active) > 0 else 0.0
    roll_max = _np.maximum.accumulate(cum)
    max_dd   = float((cum / roll_max - 1).min())
    hit_rate = float((active > 0).mean()) if len(active) > 0 else float('nan')
    return dict(
        label=label,
        sharpe=round(sharpe, 3),
        max_dd=round(max_dd, 3),
        cum_return=round(float(cum[-1] - 1), 3),
        active_days=int((pnl != 0).sum()),
        total_days=int(len(pnl)),
        hit_rate=round(hit_rate, 3) if hit_rate == hit_rate else None,
    )

# ─────────────────────────────────────────────────────────────────────────────
#  v2 DIRECTIONAL (unchanged reference)
# ─────────────────────────────────────────────────────────────────────────────
def setup_a_directional(df, omega, mfls, gamma, phase):
    A    = mfls / (gamma + 1e-9)
    w1   = omega.expanding(60).rank(pct=True)
    w2   = A.expanding(60).rank(pct=True)
    w1_g = w1.where(w1 >= 0.50, 0.0)
    w2_g = w2.where(w2 >= 0.33, 0.0)
    mom5 = np.sign(df['ret5_eth'])
    ph   = phase.values
    d    = np.zeros(len(df))
    d[ph == 2] = mom5.values[ph == 2]
    d[ph == 3] = 1.0
    d  = pd.Series(d, index=df.index)
    return (d * w1_g * w2_g).clip(-1, 1)


# ─────────────────────────────────────────────────────────────────────────────
#  PnL / IC (unchanged)
# ─────────────────────────────────────────────────────────────────────────────
def simulate(pos, ret, label=""):
    r   = ret.fillna(0).values
    p   = pos.shift(1).fillna(0).values
    pnl = p * r
    cum = np.cumprod(1 + pnl)
    bh  = np.cumprod(1 + r)
    active   = pnl[p != 0]
    sharpe   = (active.mean() / (np.std(active) + 1e-12)) * np.sqrt(252) if len(active) > 0 else 0.0
    roll_max = np.maximum.accumulate(cum)
    max_dd   = (cum / roll_max - 1).min()
    leverage = np.abs(p).mean()
    hit_rate = (active > 0).mean() if len(active) > 0 else np.nan
    q10      = np.quantile(r, 0.10)
    t_mask   = (r <= q10) & (p != 0)
    tail_acc = (np.sign(p[t_mask]) == np.sign(r[t_mask])).mean() if t_mask.sum() > 0 else np.nan
    tail_pnl = (p[t_mask] * r[t_mask]).mean() if t_mask.sum() > 0 else np.nan
    bh_sh    = (r.mean() / (r.std() + 1e-12)) * np.sqrt(252)
    bh_dd    = (bh / np.maximum.accumulate(bh) - 1).min()
    return dict(
        label=label,
        sharpe=round(float(sharpe), 3),
        sharpe_per_lev=round(float(sharpe / (leverage + 1e-9)), 3),
        max_dd=round(float(max_dd), 3),
        cum_return=round(float(cum[-1] - 1), 3),
        active_days=int((p != 0).sum()),
        total_days=len(p),
        hit_rate=round(float(hit_rate), 3) if not np.isnan(hit_rate) else None,
        tail_acc=round(float(tail_acc), 3) if not np.isnan(tail_acc) else None,
        tail_pnl=round(float(tail_pnl), 5) if not np.isnan(tail_pnl) else None,
        leverage=round(float(leverage), 4),
        bh_sharpe=round(float(bh_sh), 3),
        bh_max_dd=round(float(bh_dd), 3),
        bh_cum=round(float(bh[-1] - 1), 3),
    )


def ic_metric(pos, fwd, label=""):
    nz = (pos != 0) & fwd.notna()
    n  = nz.sum()
    if n < 20:
        return dict(label=label, n=int(n), ic=None, acc=None)
    ic_v, _ = stats.spearmanr(pos[nz].values, fwd[nz].values)
    acc = (np.sign(pos[nz].values) == np.sign(fwd[nz].values)).mean()
    return dict(label=label, n=int(n), ic=round(float(ic_v), 4), acc=round(float(acc), 3))


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 80)
    print("  CRYPTO BSDT v10 — γ-Aware Dynamic Allocation")
    print("  Anchored z + Layer 6: γ-modulation × cross-sectional Sharpe weights")
    print("  Layer 4: Drift gate only  |z̄_60d| < 1.0  (rev_eff removed)")
    print("=" * 80)

    df = fetch_and_prepare()
    train_mask = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask  = df.index >= TEST_START
    print(f"  Train: {df[train_mask].index[0].date()} → {df[train_mask].index[-1].date()}")
    print(f"  Test:  {df[test_mask].index[0].date()} → {df[test_mask].index[-1].date()}"
          f"  n={test_mask.sum()}")

    # ── BSDT ─────────────────────────────────────────────────────────────
    feats = ['ret_eth_z','ret_btc_z','ret_sol_z','ret_bnb_z',
             'vol_eth_z','vol_btc_z','btc_dom_z','cross_disp_z']
    print("\n[1]  Computing BSDT metrics ...")
    omega, mfls_eth, gamma_eth = compute_bsdt(df, feats, window=60)

    # ── Activity ──────────────────────────────────────────────────────────
    print("\n[2]  Computing A_level and ΔA_fast ...")
    A_eth, A_rank, dA_fast, dA_rank = compute_activity_signals(mfls_eth, gamma_eth)

    # ── Phase ─────────────────────────────────────────────────────────────
    ret7  = df['ret_eth'].rolling(7).sum()
    ret3  = df['ret_eth'].rolling(3).sum()
    phase = detect_phase(omega, ret7, ret3, df['btc_dom_z'])

    # ── Rolling spread + UDL MDN classification ──────────────────────────
    print("\n[3]  Rolling spread + UDL MDN classification ...")
    pairs = [
        ('P1_ETH_BTC', 'log_eth', 'log_btc', 'ret_eth', 'ret_btc'),
        ('P2_ETH_SOL', 'log_eth', 'log_sol', 'ret_eth', 'ret_sol'),
        ('P3_ETH_BNB', 'log_eth', 'log_bnb', 'ret_eth', 'ret_bnb'),
    ]
    pair_data = {}
    for key, col_a, col_b, ret_a, ret_b in pairs:
        print(f"  {key}: computing spread ...", end='', flush=True)
        sd  = compute_rolling_spread_v8(
            df[col_a], df[col_b], df[ret_a], df[ret_b],
            train_mask=train_mask, beta_window=252)

        # Fit UDL classifier on training spread; classify full series
        train_spread = sd['spread'][train_mask].dropna()
        clf = SpreadUDLClassifier(window=20, n_ref_dirs=100).fit(train_spread)
        udl_state, udl_mag, udl_novelty = clf.classify_series(sd['spread'])
        sd['udl_state']   = udl_state
        sd['udl_mag']     = udl_mag
        sd['udl_novelty'] = udl_novelty

        # Layer 4: manifold validity
        mval, z_drift, rev_eff = compute_manifold_validity(sd['z'], sd['sret'])
        sd['manifold_valid'] = mval
        sd['z_drift']        = z_drift
        sd['rev_eff']        = rev_eff
        pair_data[key]       = sd

        # Classification summary [test]
        t_st    = udl_state[test_mask]
        t_mval  = mval[test_mask]
        total   = len(t_st)
        n_eq    = (t_st == 0).sum()
        n_dg    = (t_st == 1).sum()
        n_st    = (t_st == 2).sum()
        n_valid = t_mval.sum()
        mag_med = udl_mag[test_mask].dropna().median()
        nov_med = udl_novelty[test_mask].dropna().median()
        drft_m  = z_drift[test_mask].dropna().median()
        reff_m  = rev_eff[test_mask].dropna().median()

        print(f"  EQUIL={n_eq/total*100:.1f}%  DEGEN={n_dg/total*100:.1f}%  "
              f"STRUCT={n_st/total*100:.1f}%  "
              f"VALID={n_valid/total*100:.1f}%  "
              f"drift_med={drft_m:.3f}  rev_eff_med={reff_m:.5f}")

    # ── Build positions ───────────────────────────────────────────────────
    print("\n[4]  Building positions (v7: UDL + manifold validity) ...")
    pos_A_dir = setup_a_directional(df, omega, mfls_eth, gamma_eth, phase)

    pair_positions    = {}
    pair_positions_v6 = {}   # v6 baseline (no validity filter) for comparison
    for key, _, _, _, _ in pairs:
        sd = pair_data[key]
        pair_positions[key] = route_pair_v7(
            omega, A_rank, sd['z'], sd['udl_state'], sd['poa'],
            sd['manifold_valid'], z_threshold=1.0)
        # v6 baseline (same UDL, no validity filter)
        pair_positions_v6[key] = route_pair_v6_baseline(
            omega, A_rank, sd['z'], sd['udl_state'], sd['poa'],
            z_threshold=1.0)

    pos_btc_macro, pos_alt_macro = route_btcalt_macro(df, omega, A_rank, dA_rank)

    # ── Simulate [test] ───────────────────────────────────────────────────
    print(f"\n[5]  Simulating (test {TEST_START}→2026) ...")
    ret_eth = df.loc[test_mask, 'ret_eth']
    ret_btc = df.loc[test_mask, 'ret_btc']
    fwd21   = df['ret_eth'].rolling(21).sum().shift(-21)

    sims = {}
    sims['A_directional'] = simulate(pos_A_dir[test_mask], ret_eth, 'A_directional')
    for key, _, _, _, _ in pairs:
        sims[key] = simulate(pair_positions[key][test_mask],
                             pair_data[key]['sret'][test_mask], key)
    sims['M1_BTC_macro'] = simulate(pos_btc_macro[test_mask], ret_btc, 'M1_BTC_macro')
    sims['M1_ALT_macro'] = simulate(pos_alt_macro[test_mask], ret_eth, 'M1_ALT_macro')

    pos_combined = (pos_A_dir + pair_positions['P1_ETH_BTC'] +
                    pair_positions['P2_ETH_SOL'] + pos_btc_macro) / 4.0
    sims['COMBINED_4way'] = simulate(pos_combined[test_mask], ret_eth, 'COMBINED_4way')

    ic_res = {}
    ic_res['A_directional'] = ic_metric(pos_A_dir[test_mask], fwd21[test_mask], 'A_dir')
    for key, _, _, _, _ in pairs:
        ic_res[key] = ic_metric(pair_positions[key][test_mask], fwd21[test_mask], key)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  [6]  v10: γ-AWARE POSITIONS + CROSS-SECTIONAL DYNAMIC WEIGHTS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print(f"\n[6]  Building γ-aware positions (v10) ...")
    gc_test = gamma_eth.clip(GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH)[test_mask]
    g_mean  = gc_test.mean()
    print(f"  γ [test]: mean={g_mean:.3f}  std={gc_test.std():.3f}  "
          f"p25={gc_test.quantile(0.25):.3f}  p75={gc_test.quantile(0.75):.3f}")
    print(f"  directional factor (1-γ): mean={(1-g_mean):.3f}")
    print(f"  reversion   factor (γ):   mean={g_mean:.3f}")
    pct_hi = (gc_test > 0.6).mean() * 100
    pct_lo = (gc_test < 0.4).mean() * 100
    print(f"  γ>0.6 (reversion-favourable): {pct_hi:.1f}%  "
          f"γ<0.4 (directional-favourable): {pct_lo:.1f}%")

    pos_v10 = {
        'A_directional': apply_gamma_mod(pos_A_dir,                    gamma_eth, 'directional'),
        'P1_ETH_BTC':    apply_gamma_mod(pair_positions['P1_ETH_BTC'], gamma_eth, 'reversion'),
        'P2_ETH_SOL':    apply_gamma_mod(pair_positions['P2_ETH_SOL'], gamma_eth, 'reversion'),
        'P3_ETH_BNB':    apply_gamma_mod(pair_positions['P3_ETH_BNB'], gamma_eth, 'reversion'),
        'M1_ALT_macro':  apply_gamma_mod(pos_alt_macro,                gamma_eth, 'macro'),
        'M1_BTC_macro':  apply_gamma_mod(pos_btc_macro,                gamma_eth, 'macro'),
    }
    strat_rets = {
        'A_directional': df['ret_eth'],
        'P1_ETH_BTC':    pair_data['P1_ETH_BTC']['sret'],
        'P2_ETH_SOL':    pair_data['P2_ETH_SOL']['sret'],
        'P3_ETH_BNB':    pair_data['P3_ETH_BNB']['sret'],
        'M1_ALT_macro':  df['ret_eth'],
        'M1_BTC_macro':  df['ret_btc'],
    }

    # -- Daily PnL streams (full history) for cross-sectional Sharpe scoring --
    pnl_full = {k: get_daily_pnl(pos_v10[k], strat_rets[k]) for k in pos_v10}

    # -- Rolling cross-sectional Sharpe weights (causal) ----------------------
    cs_wts = compute_cs_weights(pnl_full, window=GAMMA_SCORE_WIN)

    # -- Dynamic combined portfolio PnL: sum_i w_i(t-1) * pnl_i(t) -----------
    pnl_dyn = pd.Series(0.0, index=df.index)
    n_strats = len(pos_v10)
    for k in pos_v10:
        pnl_dyn += cs_wts[k].shift(1).fillna(1.0 / n_strats) * pnl_full[k]

    print(f"\n[7]  Simulating v10 (test {TEST_START}→2026) ...")
    sims_v10 = {}
    for k in ['A_directional', 'P1_ETH_BTC', 'P2_ETH_SOL', 'P3_ETH_BNB',
              'M1_ALT_macro', 'M1_BTC_macro']:
        sims_v10[k] = simulate(pos_v10[k][test_mask], strat_rets[k][test_mask], k)
    sims_v10['DYNAMIC_COMBINED'] = simulate_from_pnl(pnl_dyn[test_mask], 'DYNAMIC_COMBINED')

    # -- v9 vs v10 comparison table -------------------------------------------
    print()
    print("─" * 88)
    print(f"── v9 vs v10: γ-aware allocation [test {TEST_START}→2026] ────────────────────────────")
    print("─" * 88)
    gamma_modes = {
        'A_directional': '(1-γ)',  'P1_ETH_BTC': 'γ', 'P2_ETH_SOL': 'γ',
        'P3_ETH_BNB':   'γ',       'M1_ALT_macro': '1', 'M1_BTC_macro': '1',
        'DYNAMIC_COMBINED': 'w×γ',
    }
    print(f"  {'Strategy':<22}  {'v9 Sh':>7}  {'v10 Sh':>7}  {'Δ':>7}  "
          f"{'γ-mode':>7}  {'MaxDD':>7}  {'Active%':>7}")
    print("─" * 88)
    for name in ['A_directional', 'P1_ETH_BTC', 'P2_ETH_SOL', 'P3_ETH_BNB',
                 'M1_ALT_macro', 'M1_BTC_macro', 'DYNAMIC_COMBINED']:
        v9s  = sims.get(name, {}).get('sharpe', None)
        v10r = sims_v10.get(name, {})
        v10s = v10r.get('sharpe', None)
        dd   = v10r.get('max_dd', None)
        tot  = v10r.get('total_days', 1)
        act  = v10r.get('active_days', 0)
        pct  = act / tot * 100 if tot > 0 else 0.0
        dlt  = f"{v10s - v9s:>+7.3f}" if (v9s is not None and v10s is not None) else "       "
        v9ss  = f"{v9s:>+7.3f}"  if v9s  is not None else "       "
        v10ss = f"{v10s:>+7.3f}" if v10s is not None else "       "
        dds   = f"{dd:>7.3f}"    if dd   is not None else "       "
        gm    = gamma_modes.get(name, '?')
        print(f"  {name:<22}  {v9ss}  {v10ss}  {dlt}  {gm:>7}  {dds}  {pct:>6.1f}%")

    # -- Mean cross-sectional weights [test] ----------------------------------
    print()
    print("── Mean cross-sectional weights [test period] ──────────────────────")
    for k in pos_v10:
        w_mean = cs_wts[k][test_mask].mean()
        print(f"  {k:<22}: {w_mean:.3f}")
    print()


    # ── Results table ─────────────────────────────────────────────────────
    print()
    print("─" * 95)
    print(f"── PnL results (test {TEST_START}–2026) — v4 / v6 / v7 / v8 / v9 ─────────────────────")
    print("─" * 95)
    v4_ref = {'A_directional': 0.535, 'P1_ETH_BTC': 0.758,
              'P2_ETH_SOL': 0.835, 'P3_ETH_BNB': 1.251}
    v5_ref = {'A_directional': 0.535, 'P1_ETH_BTC': 0.443,
              'P2_ETH_SOL': 2.099, 'P3_ETH_BNB': 0.167,
              'M1_ALT_macro': 1.387, 'M1_BTC_macro': 0.156}
    v6_ref = {'A_directional': 0.535, 'P1_ETH_BTC': 0.641,
              'P2_ETH_SOL': 0.927, 'P3_ETH_BNB': -1.248,
              'M1_ALT_macro': 1.387, 'M1_BTC_macro': 0.156}
    v7_ref = {'A_directional': 0.535, 'P1_ETH_BTC': -3.130,
              'P2_ETH_SOL': 2.237, 'P3_ETH_BNB': -9.641,
              'M1_ALT_macro': 1.387, 'M1_BTC_macro': 0.156}
    print(f"  {'Strategy':<22}  {'v4 Sh':>6}  {'v6 Sh':>7}  {'v7 Sh':>7}  "
          f"{'v6→v7':>6}  {'Sh/Lev':>7}  {'MaxDD':>7}  {'Active%':>7}")
    print("─" * 95)

    bhr = sims['A_directional']
    print(f"  {'ETH Buy & Hold':<22}  {'':>6}  {'':>7}  "
          f"{bhr['bh_sharpe']:>+7.3f}  {'':>6}  {'   ---':>7}  "
          f"{bhr['bh_max_dd']:>7.3f}  {'100.0%':>7}")
    print()

    for name, r in sims.items():
        pct  = r['active_days'] / r['total_days'] * 100
        v4_s = f"{v4_ref[name]:>+6.3f}" if name in v4_ref else "      "
        v6_s = f"{v6_ref[name]:>+7.3f}" if name in v6_ref else "       "
        delta_v6 = ""
        if name in v6_ref:
            delta_v6 = f"{r['sharpe'] - v6_ref[name]:>+6.3f}"
        print(f"  {name:<22}  {v4_s}  {v6_s}  {r['sharpe']:>+7.3f}  "
              f"{delta_v6:>6}  {r['sharpe_per_lev']:>+7.3f}  "
              f"{r['max_dd']:>7.3f}  {pct:>6.1f}%")

    print(f"\n── IC (H=21d fwd) ───────────────────────────────────────────────────")
    for name, r in ic_res.items():
        ic_s = f"{r['ic']:>+8.4f}" if r['ic'] is not None else "     n/a"
        print(f"  {name:<22}: n={r['n']:>4}  IC={ic_s}  acc={r['acc'] if r['acc'] else 'n/a'}")

    # ── State + validity distribution [test] ─────────────────────────────
    print(f"\n── UDL state + manifold validity [test period] ─────────────────────")
    state_names = {0: 'EQUIL', 1: 'DEGEN', 2: 'STRUCT'}
    print(f"  {'Pair':<14}  {'EQUIL%':>8}  {'DEGEN%':>8}  {'STRUCT%':>9}  "
          f"{'VALID%':>7}  {'drift_med':>10}  {'rev_eff_med':>12}")
    print("─" * 78)
    for key, _, _, _, _ in pairs:
        sd    = pair_data[key]
        t_st  = sd['udl_state'][test_mask]
        t_mv  = sd['manifold_valid'][test_mask]
        total = len(t_st)
        pE    = (t_st == 0).sum() / total * 100
        pD    = (t_st == 1).sum() / total * 100
        pS    = (t_st == 2).sum() / total * 100
        pV    = t_mv.sum() / total * 100
        drft_m = sd['z_drift'][test_mask].dropna().median()
        reff_m = sd['rev_eff'][test_mask].dropna().median()
        print(f"  {key:<14}  {pE:>7.1f}%  {pD:>7.1f}%  {pS:>8.1f}%  "
              f"{pV:>6.1f}%  {drft_m:>10.4f}  {reff_m:>12.6f}")

    # ── Ablation: v6 (no validity) vs v7 (with validity) ─────────────────
    print(f"\n── Ablation: v6 router vs v7 router [test period] ───────────────────")
    print(f"  {'Pair':<14}  {'v6 Sharpe':>10}  {'v7 Sharpe':>10}  "
          f"{'Δ':>6}  {'v6 Active%':>11}  {'v7 Active%':>11}")
    print("─" * 70)
    for key, _, _, _, _ in pairs:
        sret_k = pair_data[key]['sret']
        r6 = simulate(pair_positions_v6[key][test_mask], sret_k[test_mask])
        r7 = simulate(pair_positions[key][test_mask],    sret_k[test_mask])
        pct6 = r6['active_days'] / r6['total_days'] * 100
        pct7 = r7['active_days'] / r7['total_days'] * 100
        print(f"  {key:<14}  {r6['sharpe']:>+10.3f}  {r7['sharpe']:>+10.3f}  "
              f"{r7['sharpe'] - r6['sharpe']:>+6.3f}  {pct6:>10.1f}%  {pct7:>10.1f}%")

    # ── Theory validation per UDL state ──────────────────────────────────
    print(f"\n── Reversion accuracy by UDL state [test, validity-gated days only] ─")
    for key, _, _, _, _ in pairs:
        sd    = pair_data[key]
        z     = sd['z']
        sr    = sd['sret']
        fwd5  = sr.rolling(5).sum().shift(-5)
        mval  = sd['manifold_valid']
        print(f"  {key}:")
        for st, sname in state_names.items():
            m = test_mask & (sd['udl_state'] == st) & (z.abs() > 1.0) & mval.astype(bool)
            n = m.sum()
            if n < 10:
                print(f"    {sname:<10}: n={n} (too small)")
                continue
            rev_acc = ((-np.sign(z[m])) == np.sign(fwd5[m].fillna(0))).mean()
            result  = "REVERT" if rev_acc > 0.52 else "CONTINUE" if rev_acc < 0.48 else "mixed"
            print(f"    {sname:<10}: n={n:>4}  rev_acc={rev_acc:.3f}  → {result}")
        print()

    # ── POA scale effect ──────────────────────────────────────────────────
    print("── POA (Pair Omega Alignment) analysis [test] ──────────────────────")
    print("  POA = rolling 60d |corr(ret_a, ret_b)| — geometry stability proxy")
    for key, _, _, _, _ in pairs:
        sd   = pair_data[key]
        poa  = sd['poa'][test_mask]
        sr   = sd['sret'][test_mask]
        fwd5 = sr.rolling(5).sum().shift(-5)
        z    = sd['z'][test_mask]
        print(f"  {key}:")
        for lo, hi, lab in [(0.0, 0.4, 'Low  (<0.4)'),
                            (0.4, 0.7, 'Med  (0.4-0.7)'),
                            (0.7, 1.0, 'High (>0.7)')]:
            m   = (poa >= lo) & (poa < hi) & (z.abs() > 1.0)
            n   = m.sum()
            if n < 5:
                continue
            rev = ((-np.sign(z[m])) == np.sign(fwd5[m].fillna(0))).mean()
            print(f"    {lab}: n={n:>4}  rev_acc={rev:.3f}")
        print()

    # ── Crisis breakdown ──────────────────────────────────────────────────
    crises = {
        '2022_winter':   ('2022-01-01', '2022-12-31'),
        '2023_recovery': ('2023-01-01', '2023-12-31'),
        '2024_bull':     ('2024-01-01', '2024-12-31'),
        '2025_bear':     ('2025-01-01', '2025-12-31'),
    }
    print("── Crisis Sharpe (v6) ───────────────────────────────────────────────")
    print(f"  {'Period':<18}  {'A_dir':>7}  {'P1_ETH/BTC':>11}  "
          f"{'P2_ETH/SOL':>11}  {'P3_ETH/BNB':>11}  {'ALT_macro':>10}")
    print("─" * 72)
    def c_sh(pos, ret_s, cs, ce, min_active=5):
        m = (df.index >= cs) & (df.index <= ce)
        if m.sum() < 5:
            return "    n/a"
        r = simulate(pos[m], ret_s[m])
        if r['active_days'] < min_active:
            return "  <5act"
        return f"{r['sharpe']:>+7.3f}"
    for cname, (cs, ce) in crises.items():
        va  = c_sh(pos_A_dir, df['ret_eth'], cs, ce)
        p1  = c_sh(pair_positions['P1_ETH_BTC'],
                   pair_data['P1_ETH_BTC']['sret'], cs, ce)
        p2  = c_sh(pair_positions['P2_ETH_SOL'],
                   pair_data['P2_ETH_SOL']['sret'], cs, ce)
        p3  = c_sh(pair_positions['P3_ETH_BNB'],
                   pair_data['P3_ETH_BNB']['sret'], cs, ce)
        am  = c_sh(pos_alt_macro, df['ret_eth'], cs, ce)
        print(f"  {cname:<18}  {va}  {p1:>11}  {p2:>11}  {p3:>11}  {am:>10}")

    # ─────────────────────────────────────────────────────────────────────
    #  SAVE RESULTS
    # ─────────────────────────────────────────────────────────────────────
    def _clean(obj):
        if isinstance(obj, dict):  return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):  return [_clean(v) for v in obj]
        if isinstance(obj, float) and np.isnan(obj): return None
        if isinstance(obj, (np.integer, np.floating)): return obj.item()
        return obj

    class_dist = {}
    for key, _, _, _, _ in pairs:
        sd   = pair_data[key]
        t_st = sd['udl_state'][test_mask]
        class_dist[key] = {
            'equil_pct':      round(float((t_st == 0).mean() * 100), 1),
            'degen_pct':      round(float((t_st == 1).mean() * 100), 1),
            'struct_pct':     round(float((t_st == 2).mean() * 100), 1),
            'valid_pct':      round(float(sd['manifold_valid'][test_mask].mean() * 100), 1),
            'mag_median':     round(float(sd['udl_mag'][test_mask].dropna().median()), 4),
            'novelty_median': round(float(sd['udl_novelty'][test_mask].dropna().median()), 4),
            'z_drift_median': round(float(sd['z_drift'][test_mask].dropna().median()), 4),
            'rev_eff_median': round(float(sd['rev_eff'][test_mask].dropna().median()), 6),
            'poa_median':     round(float(sd['poa'][test_mask].dropna().median()), 4),
        }

    # ablation sharpes for JSON
    ablation = {}
    for key, _, _, _, _ in pairs:
        sret_k = pair_data[key]['sret']
        r6 = simulate(pair_positions_v6[key][test_mask], sret_k[test_mask])
        r7 = simulate(pair_positions[key][test_mask],    sret_k[test_mask])
        ablation[key] = {'v6_sharpe': round(r6['sharpe'], 3),
                         'v7_sharpe': round(r7['sharpe'], 3),
                         'delta':     round(r7['sharpe'] - r6['sharpe'], 3)}

    crisis_sharpe = {}
    for cname, (cs, ce) in crises.items():
        m = (df.index >= cs) & (df.index <= ce)
        crisis_sharpe[cname] = {}
        for key, _, _, _, _ in pairs:
            if m.sum() >= 5:
                r = simulate(pair_positions[key][m], pair_data[key]['sret'][m])
                crisis_sharpe[cname][key] = round(r['sharpe'], 3)

    results = {
        "model": "Crypto BSDT v10 — γ-Aware Dynamic Allocation",
        "version": "v8",
        "architecture": {
            "layer_1": "Ω (BSDT spectral order) — timing gate ≥ Q50",
            "layer_2": "A = MFLS/γ — intensity gate ≥ Q33",
            "layer_3_udl_mdn": {
                "method":      "UDL Magnitude-Direction-Novelty decomposition",
                "operators":   "Stat(5) + Chaos(3) + Freq(3) + Recon(3) = 14-dim feature vector",
                "EQUILIBRIUM": "normal magnitude AND known direction → revert",
                "DEGENERATE":  "spread var<p10 OR magnitude<p10 → skip",
                "STRUCTURAL":  "novelty>p85 → half-size revert",
            },
            "layer_4_validity": {
                "drift_test":       f"|rolling_mean(z, {DRIFT_WINDOW}d)| < {DRIFT_THRESH} (1σ threshold; anchored z makes this meaningful)",
                "effectiveness_test": f"rolling_mean(sign(-z_prev)*sret, {EFF_WINDOW}d) > {EFF_THRESH}",
                "action_if_invalid": "skip (pair auto-disabled)",
            },
            "layer_5_sizing": "min(|z|,2)/2 × POA_scale (EQUIL) or × 0.5 (STRUCT)",
        },
        "class_dist_and_validity": class_dist,
        "ablation_v6_vs_v7": ablation,
        "pnl_results":   _clean(sims),
        "ic_results":    _clean(ic_res),
        "crisis_sharpe": _clean(crisis_sharpe),
        "v10_gamma_results": _clean(sims_v10),
        "v10_gamma_stats": {
            "gamma_clip_low":  GAMMA_CLIP_LOW,
            "gamma_clip_high": GAMMA_CLIP_HIGH,
            "gamma_score_win": GAMMA_SCORE_WIN,
            "gamma_mean_test": float(round(gamma_eth.clip(GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH)[test_mask].mean(), 4)),
            "pct_hi_gamma_test": float(round((gamma_eth.clip(GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH)[test_mask] > 0.6).mean() * 100, 1)),
        },
        "version_history": {
            "v4":  {"P1_ETH_BTC": 0.758, "P2_ETH_SOL": 0.835, "P3_ETH_BNB": 1.251},
            "v6":  {"P1_ETH_BTC": 0.641, "P2_ETH_SOL": 0.927, "P3_ETH_BNB": -1.248,
                    "M1_ALT_macro": 1.387},
            "v7":  {"P1_ETH_BTC": -3.130, "P2_ETH_SOL": 2.237, "P3_ETH_BNB": -9.641,
                    "M1_ALT_macro": 1.387},
            "v8":  {"P1_ETH_BTC": -5.664, "P2_ETH_SOL": 0.546, "P3_ETH_BNB": -16.946,
                    "M1_ALT_macro": 1.387},
            "v9":  {"P1_ETH_BTC": -1.248, "P2_ETH_SOL": 1.357, "P3_ETH_BNB": -0.463,
                    "M1_ALT_macro": 1.387},
        },
    }

    import os
    out_path = os.path.join(OUT_DIR, "crypto_bsdt_v10_results.json")
    with open(out_path, 'w') as f:
        json.dump(_clean(results), f, indent=2)
    print(f"\n  Results saved → {out_path}")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  SUMMARY: v4 → v6 → v7 → v8 → v9 → v10 (γ-aware dynamic allocation)")
    print("=" * 80)
    v9_ref = {'A_directional': 0.535, 'P1_ETH_BTC': -1.248,
              'P2_ETH_SOL': 1.357, 'P3_ETH_BNB': -0.463,
              'M1_ALT_macro': 1.387, 'M1_BTC_macro': 0.156}
    for name in ['A_directional', 'P1_ETH_BTC', 'P2_ETH_SOL', 'P3_ETH_BNB',
                 'M1_ALT_macro', 'DYNAMIC_COMBINED']:
        v4  = v4_ref.get(name, None)
        v9  = v9_ref.get(name, None)
        v10 = sims_v10[name]['sharpe'] if name in sims_v10 else None
        v4s  = f"{v4:>+7.3f}"  if v4  is not None else "       "
        v9s  = f"{v9:>+7.3f}"  if v9  is not None else "       "
        v10s = f"{v10:>+7.3f}" if v10 is not None else "       "
        if name in sims_v10:
            r  = sims_v10[name]
            dd = (f"  MaxDD {r['max_dd']:>7.3f}  "
                  f"active {r['active_days']/r['total_days']*100:.1f}%")
        elif name in sims:
            r  = sims[name]
            dd = (f"  MaxDD {r['max_dd']:>7.3f}  "
                  f"active {r['active_days']/r['total_days']*100:.1f}%")
        else:
            dd = ""
        print(f"  {name:<22}  v4:{v4s}  v9:{v9s}  v10:{v10s}{dd}")
    print()


if __name__ == '__main__':
    main()
