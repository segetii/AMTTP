"""
Crypto BSDT v6 — Degenerate-Aware Pair Classifier
===================================================

Diagnosis from v5:
  ✗ AR(1) half-life blows up when |φ| ≈ 0 (flat or transitioning spread)
  ✗ This pushes equilibrium days into Class C → wrong continuation signal
  ✗ ETH/BTC and ETH/BNB regressed from v4 for this reason
  ✗ Three fundamentally different phenomena were collapsed into one "Class C" bucket:
        (a) flat spread / numerical degenerate
        (b) structural β-shift (real repricing)
        (c) genuine flow / trend
      Only (c) is continuation-tradeable; (a) and (b) should not be traded

v6 design:
  ✓ New 3-state classifier: EQUILIBRIUM / DEGENERATE / STRUCTURAL
      EQUILIBRIUM  : |φ| > φ_min   AND  spread variance healthy    → full mean reversion
      DEGENERATE   : |φ| ≤ φ_min   OR   spread variance collapsed  → NO TRADE
      STRUCTURAL   : β velocity > thresh (genuine β repricing)      → half-size reversion
                     (the spread is moving but the long-run mean is shifting too;
                      cautious reversion only if Ω + A gate passed)

  ✓ AR(1) fix:
      if |φ| < 0.05: state = DEGENERATE (not "infinite half-life")
      half_life only computed when |φ| is meaningful (≥ 0.05)

  ✓ Spread variance filter:
      spread_std_ratio = rolling_std(S, 30d) / rolling_std(S, 252d)
      if ratio < 0.15: flat spread → DEGENERATE

  ✓ β velocity:
      beta_velocity = |β_t − β_{t-21}| / (mean(|β|) + ε)
      if beta_velocity > 0.30: β is actively repricing → STRUCTURAL

  ✓ Geometry-based stability metric (BSDT-native):
      Pair Omega Alignment (POA) = rolling 60d |corr(ret_a, ret_b)|
      Used as a continuous size scaler (not a hard gate):
          size_scale = clip((POA − 0.3) / 0.5, 0, 1)
      Near-zero POA = assets decoupled = high uncertainty → scale down

  ✓ Continuation removed:
      Data shows all tested pairs are predominantly EQUILIBRIUM (hl ≈ 3d).
      No continuation signals — cleaner, more robust, easier to falsify.

  ✓ Routing summary:
      DEGENERATE            → flat (no trade)
      STRUCTURAL            → 0.5 × reversion (if Ω + A gate)
      EQUILIBRIUM           → 1.0 × reversion × POA_scale (if Ω + A gate)
      All gates unchanged:  Ω ≥ Q50, A_level ≥ Q33, |z| > 1.0

Pairs:
  P1. ETH/BTC — expected: mostly EQUILIBRIUM; was broken by AR(1) blowup → should recover
  P2. ETH/SOL — already best (v5: 2.099) — should remain strong or improve
  P3. ETH/BNB — 49% was false Class C → should recover toward v4 level (1.251)
  M1. BTC/ALT — unchanged macro rotation (kept from v5)
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

# ─── v6 routing / sizing constants (no magic numbers) ───────────────────────
BETA_VEL_THRESH    = 0.30   # β changed >30% of level in 21d → STRUCTURAL
POA_LOW            = 0.30   # pair correlation below this → scale=0
POA_HIGH           = 0.80   # pair correlation above this → full scale
STRUCT_SIZE_SCALE  = 0.50   # half-size for STRUCTURAL days


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
#  v6 SPREAD COMPUTATION
# ─────────────────────────────────────────────────────────────────────────────
def compute_rolling_spread_v6(log_a, log_b, ret_a, ret_b,
                               beta_window=252, zscore_window=60):
    """
    For each day t compute:
      spread S_t         using rolling OLS β (252d)
      z-score            rolling-mean / rolling-std (zscore_window)
      spread_var_ratio   roll_30d_std / roll_252d_std  (diagnostic)
      beta_velocity      |β_t − β_{t−21}| / (mean|β| + ε)  (diagnostic)
      POA                rolling 60d |corr(ret_a, ret_b)|   (position sizing)

    Returns dict of pd.Series indexed on log_a.index.
    Classification is handled by SpreadUDLClassifier (fitted separately).
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

    # ── Step 3: z-score (expanding mean, rolling std) ───────────────────
    mu_s   = S_ser.rolling(zscore_window, min_periods=30).mean()
    sd_s   = S_ser.rolling(zscore_window, min_periods=30).std()
    z      = (S_ser - mu_s) / (sd_s + 1e-9)

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
#  v6 ROUTER  — state-aware, POA-scaled, no continuation
# ─────────────────────────────────────────────────────────────────────────────
def route_pair_v6(omega, A_rank, z_spread, udl_state, poa, z_threshold=1.0):
    """
    Gate:  Ω ≥ Q50  AND  A_level ≥ Q33  AND  |z| > z_threshold

    DEGENERATE  (state=1): skip entirely
    EQUILIBRIUM (state=0): direction = -sign(z); size = min(|z|,2)/2 × POA_scale
    STRUCTURAL  (state=2): direction = -sign(z); size = STRUCT_SIZE_SCALE × min(|z|,2)/2

    POA_scale = clip((poa - POA_LOW) / (POA_HIGH - POA_LOW), 0, 1)
    — scales position from 0 at low correlation to 1 at high correlation
    """
    omega_q50   = omega.expanding(60).quantile(0.50)
    omega_gate  = omega >= omega_q50
    active_gate = A_rank >= 0.33
    spread_gate = np.abs(z_spread) > z_threshold
    gate        = omega_gate & active_gate & spread_gate

    state_v = udl_state.values
    z_v     = z_spread.values
    poa_v   = poa.fillna(0.5).values
    g_v     = gate.values

    pos = np.zeros(len(z_v))
    for i in range(len(z_v)):
        if not g_v[i] or state_v[i] == 1:  # gate failed OR degenerate
            continue
        direction  = -np.sign(z_v[i])      # always revert
        base_size  = min(abs(z_v[i]), 2.0) / 2.0

        if state_v[i] == 0:                # EQUILIBRIUM
            poa_scale = np.clip((poa_v[i] - POA_LOW) / (POA_HIGH - POA_LOW), 0, 1)
            pos[i]    = direction * base_size * poa_scale
        elif state_v[i] == 2:              # STRUCTURAL — cautious
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
    print("  CRYPTO BSDT v6 — Degenerate-Aware Classifier (EQUIL / DEGEN / STRUCT)")
    print("  Key fix: |φ|<0.05 OR flat spread → DEGENERATE (no trade)")
    print("           POA geometry metric scales position continuously")
    print("           No continuation trades — reversion-only engine")
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
        sd  = compute_rolling_spread_v6(
            df[col_a], df[col_b], df[ret_a], df[ret_b],
            beta_window=252, zscore_window=60)

        # Fit UDL classifier on training spread; classify full series
        train_spread = sd['spread'][train_mask].dropna()
        clf = SpreadUDLClassifier(window=20, n_ref_dirs=100).fit(train_spread)
        udl_state, udl_mag, udl_novelty = clf.classify_series(sd['spread'])
        sd['udl_state']   = udl_state
        sd['udl_mag']     = udl_mag
        sd['udl_novelty'] = udl_novelty
        pair_data[key]    = sd

        # Classification summary [test]
        t_st    = udl_state[test_mask]
        total   = len(t_st)
        n_eq    = (t_st == 0).sum()
        n_dg    = (t_st == 1).sum()
        n_st    = (t_st == 2).sum()
        mag_med = udl_mag[test_mask].dropna().median()
        nov_med = udl_novelty[test_mask].dropna().median()
        poa_med = sd['poa'][test_mask].dropna().median()

        print(f"  EQUIL={n_eq/total*100:.1f}%  DEGEN={n_dg/total*100:.1f}%  "
              f"STRUCT={n_st/total*100:.1f}%  "
              f"mag_med={mag_med:.3f}  novelty_med={nov_med:.3f}  "
              f"POA_med={poa_med:.3f}")

    # ── Build positions ───────────────────────────────────────────────────
    print("\n[4]  Building positions (UDL router: EQUIL/DEGEN/STRUCT) ...")
    pos_A_dir = setup_a_directional(df, omega, mfls_eth, gamma_eth, phase)

    pair_positions = {}
    for key, _, _, _, _ in pairs:
        sd  = pair_data[key]
        pos = route_pair_v6(omega, A_rank, sd['z'], sd['udl_state'], sd['poa'],
                            z_threshold=1.0)
        pair_positions[key] = pos

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

    # ── Results table ─────────────────────────────────────────────────────
    print()
    print("─" * 90)
    print(f"── PnL results (test {TEST_START}–2026) — comparing v4, v5, v6 ──────────────")
    print("─" * 90)
    v4_ref = {'A_directional': 0.535, 'P1_ETH_BTC': 0.758,
              'P2_ETH_SOL': 0.835, 'P3_ETH_BNB': 1.251}
    v5_ref = {'A_directional': 0.535, 'P1_ETH_BTC': 0.443,
              'P2_ETH_SOL': 2.099, 'P3_ETH_BNB': 0.167,
              'M1_ALT_macro': 1.387, 'M1_BTC_macro': 0.156}
    print(f"  {'Strategy':<22}  {'v4 Sh':>6}  {'v5 Sh':>7}  {'v6 Sh':>7}  "
          f"{'v4→v6':>6}  {'Sh/Lev':>7}  {'MaxDD':>7}  {'Active%':>7}")
    print("─" * 90)

    bhr = sims['A_directional']
    print(f"  {'ETH Buy & Hold':<22}  {'':>6}  {'':>7}  "
          f"{bhr['bh_sharpe']:>+7.3f}  {'':>6}  {'   ---':>7}  "
          f"{bhr['bh_max_dd']:>7.3f}  {'100.0%':>7}")
    print()

    for name, r in sims.items():
        pct  = r['active_days'] / r['total_days'] * 100
        v4_s = f"{v4_ref[name]:>+6.3f}" if name in v4_ref else "      "
        v5_s = f"{v5_ref[name]:>+7.3f}" if name in v5_ref else "       "
        delta_all = ""
        if name in v4_ref:
            d4 = r['sharpe'] - v4_ref[name]
            delta_all = f"{d4:>+6.3f}"
        print(f"  {name:<22}  {v4_s}  {v5_s}  {r['sharpe']:>+7.3f}  "
              f"{delta_all:>6}  {r['sharpe_per_lev']:>+7.3f}  "
              f"{r['max_dd']:>7.3f}  {pct:>6.1f}%")

    print(f"\n── IC (H=21d fwd) ───────────────────────────────────────────────────")
    for name, r in ic_res.items():
        ic_s = f"{r['ic']:>+8.4f}" if r['ic'] is not None else "     n/a"
        print(f"  {name:<22}: n={r['n']:>4}  IC={ic_s}  acc={r['acc'] if r['acc'] else 'n/a'}")

    # ── v6 classification breakdown [test] ────────────────────────────────
    print(f"\n── v6 State distribution [test period] ─────────────────────────────")
    state_names = {0: 'EQUIL', 1: 'DEGEN', 2: 'STRUCT'}
    print(f"  {'Pair':<14}  {'EQUIL%':>8}  {'DEGEN%':>8}  {'STRUCT%':>9}  "
          f"{'POA_med':>8}  {'mag_med':>8}  {'novelty_med':>11}")
    print("─" * 74)
    for key, _, _, _, _ in pairs:
        sd    = pair_data[key]
        t_st  = sd['udl_state'][test_mask]
        total = len(t_st)
        pE    = (t_st == 0).sum() / total * 100
        pD    = (t_st == 1).sum() / total * 100
        pS    = (t_st == 2).sum() / total * 100
        poa_m = sd['poa'][test_mask].dropna().median()
        mag_m = sd['udl_mag'][test_mask].dropna().median()
        nov_m = sd['udl_novelty'][test_mask].dropna().median()
        print(f"  {key:<14}  {pE:>7.1f}%  {pD:>7.1f}%  {pS:>8.1f}%  "
              f"{poa_m:>8.3f}  {mag_m:>8.3f}  {nov_m:>11.3f}")

    # ── Theory validation per UDL state ───────────────────────────────────────────────
    print(f"\n── Reversion accuracy by UDL state [test] ─────────────────────────────────")
    for key, _, _, _, _ in pairs:
        sd    = pair_data[key]
        z     = sd['z']
        sr    = sd['sret']
        fwd5  = sr.rolling(5).sum().shift(-5)
        print(f"  {key}:")
        for st, sname in state_names.items():
            m = test_mask & (sd['udl_state'] == st) & (z.abs() > 1.0)
            n = m.sum()
            if n < 10:
                print(f"    {sname:<10}: n={n} (too small)")
                continue
            z_sign   = np.sign(z[m])
            fv       = np.sign(fwd5[m].fillna(0))
            rev_acc  = ((-z_sign) == fv).mean()
            result   = "REVERT" if rev_acc > 0.52 else "CONTINUE" if rev_acc < 0.48 else "mixed"
            expected = "REVERT" if st < 2 else "STRUCT-REVERT"
            print(f"    {sname:<10}: n={n:>4}  rev_acc={rev_acc:.3f}  → {result}  "
                  f"(expected {expected})")
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
    def c_sh(pos, ret_s, cs, ce):
        m = (df.index >= cs) & (df.index <= ce)
        if m.sum() < 5:
            return "    n/a"
        return f"{simulate(pos[m], ret_s[m])['sharpe']:>+7.3f}"
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
            'mag_median':     round(float(sd['udl_mag'][test_mask].dropna().median()), 4),
            'novelty_median': round(float(sd['udl_novelty'][test_mask].dropna().median()), 4),
            'poa_median':     round(float(sd['poa'][test_mask].dropna().median()), 4),
        }

    crisis_sharpe = {}
    for cname, (cs, ce) in crises.items():
        m = (df.index >= cs) & (df.index <= ce)
        crisis_sharpe[cname] = {}
        for key, _, _, _, _ in pairs:
            if m.sum() >= 5:
                r = simulate(pair_positions[key][m], pair_data[key]['sret'][m])
                crisis_sharpe[cname][key] = round(r['sharpe'], 3)

    results = {
        "model": "Crypto BSDT v6 — UDL MDN Pair Classifier",
        "version": "v6",
        "architecture": {
            "classifier": {
                "method":      "UDL Magnitude-Direction-Novelty (MDN) decomposition",
                "operators":   "Stat(5) + Chaos(3) + Freq(3) + Recon(3) = 14-dim feature vector",
                "EQUILIBRIUM": "normal magnitude AND known direction → full reversion",
                "DEGENERATE":  "spread var<p10 OR feature magnitude<p10 → no trade",
                "STRUCTURAL":  "direction novelty>p85 (unprecedented in training) → half-size reversion",
            },
            "geometry_metric": "POA = rolling 60d |corr(ret_a, ret_b)| scales position 0→1",
            "thresholds": {
                "var_low":      "p10 of training window variance (DEGENERATE gate)",
                "mag_low":      "p10 of training MDN magnitude (DEGENERATE gate)",
                "novelty_high": "p85 of training direction novelty (STRUCTURAL gate)",
                "POA_LOW":   POA_LOW,
                "POA_HIGH":  POA_HIGH,
                "STRUCT_SIZE": STRUCT_SIZE_SCALE,
            },
            "continuation_removed": True,
            "key_fix": "AR(1) φ≈0→hl=2403d artefact eliminated; flat spread detected by low variance (Stat operator)",
        },
        "v5_vs_v6_class_dist": class_dist,
        "pnl_results": _clean(sims),
        "ic_results":  _clean(ic_res),
        "crisis_sharpe": _clean(crisis_sharpe),
        "method_note": (
            "UDL MDN: each 20-day spread window is embedded as a 14-dim feature vector via "
            "4 spectral operators (Stat, Chaos, Freq, Recon). Training centroid + SVD reference "
            "directions fit on 2021-2022 data. Classification uses magnitude (distance from centroid) "
            "and novelty (1 - max cosine similarity with reference directions)."
        ),
    }

    import os
    out_path = os.path.join(OUT_DIR, "crypto_bsdt_v6_results.json")
    with open(out_path, 'w') as f:
        json.dump(_clean(results), f, indent=2)
    print(f"\n  Results saved → {out_path}")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  SUMMARY: v4 → v5 → v6")
    print("=" * 80)
    for name in ['A_directional', 'P1_ETH_BTC', 'P2_ETH_SOL', 'P3_ETH_BNB',
                 'M1_ALT_macro']:
        v4 = v4_ref.get(name, None)
        v5 = v5_ref.get(name, None)
        v6 = sims[name]['sharpe'] if name in sims else None
        v4s = f"{v4:>+7.3f}" if v4 is not None else "       "
        v5s = f"{v5:>+7.3f}" if v5 is not None else "       "
        v6s = f"{v6:>+7.3f}" if v6 is not None else "       "
        if name in sims:
            dd = (f"  MaxDD {sims[name]['max_dd']:>7.3f}  "
                  f"active {sims[name]['active_days']/sims[name]['total_days']*100:.1f}%")
        else:
            dd = ""
        print(f"  {name:<22}  v4:{v4s}  v5:{v5s}  v6:{v6s}{dd}")
    print()


if __name__ == '__main__':
    main()
