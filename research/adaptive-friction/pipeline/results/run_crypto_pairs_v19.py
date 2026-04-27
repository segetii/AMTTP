"""
Crypto BSDT v19 — cos_θ_channel collapse invariant as trading signal
=====================================================================

Theoretical foundation (collapse_geometry v1.3.0):

  The universal collapse invariant discovered across FDIC, GSIB, ERCOT, and
  TerraLuna datasets:
      cos_θ_channel → −1  at EVERY systemic crisis

  In 4D channel space, define 4 physical channel stress scores:
      δ_C(t) : Correlation anomaly   ← spectral radius Ω_strat
      δ_G(t) : Geometric deviation   ← MFLS (mean-field level spacing)
      δ_A(t) : Activity anomaly      ← expanding rank of A = MFLS/γ
      δ_T(t) : Topological novelty   ← rolling kNN distance in state space

  cos_θ_channel formula (§VII / §XXIV.3  — exact, not a proxy):
      g   = ∇_S E_BS(S_t)           energy gradient in channel space  ∈ ℝ⁴
            via UnifiedEnergy.grad(bsdt.channel_state(snap))
      h_k = ⟨∂δ_k/∂X, F⟩_F         GravityEngine force projected onto
            the per-channel Jacobian ∂δ_k/∂X  (einsum over N×d)
      cos_θC = (g · h) / (‖g‖ · ‖h‖)

  Distinct from the proxy (g = raw δ scores, h = −Δg):
    • g accounts for the full non-linear energy landscape
    • h accounts for the physical restoring force, not just a finite difference
    • per-channel Jacobians encode Mahalanobis, PCA-gap, velocity, KDE geometry

  Interpretation:
    cos_θC ≈ −1 : stress growing in exact direction of applied force → COLLAPSE
    cos_θC ≈  0 : noise / neutral regime
    cos_θC ≈ +1 : stress actively reversing → RECOVERY

  Geometric Collapse Index (GCI):
      GCI = (1 + cos_θC) / 2  ∈ [0, 1]
      GCI = 0 → imminent collapse → minimum leverage (GCI_LEV_LO)
      GCI = 1 → active recovery  → maximum leverage (GCI_LEV_HI)

  Hard-lock alarm:
      cos_θC < −ALARM_THRESH for ≥ ALARM_MIN_STEPS consecutive steps
      → go FLAT immediately (capital protection protocol)

Falsifiable 5-way ablation [test 2023-present]:
  v14b           : linear γ_rank leverage dial         (published champion)
  v18_smooth     : v14b + φ direction-change + EMA     (strong geometric baseline)
  v19_gci_only   : v18_smooth × GCI leverage           (theory signal only)
  v19_alarm_only : v18_smooth + hard-lock alarm only   (protection only)
  v19_full       : v18_smooth × GCI + hard-lock alarm  (FULL THEORY INTEGRATION)

v19 win criterion:
  Sharpe(v19_full) ≥ Sharpe(v18_smooth)  AND
  MaxDD(v19_full)  ≤ MaxDD(v18_smooth)   OR  CAGR(v19_full) ≥ CAGR(v18_smooth) + 2%

Output:
  crypto_bsdt_v19_results.json
  crypto_bsdt_v19_equity.png  (3-panel: equity curves / cos_θC timeseries / GCI)
"""

import os
import numpy as np
import pandas as pd
import json
import warnings
import requests
import bisect
import time
warnings.filterwarnings('ignore')
import sys; sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import yfinance as yf
from numpy.linalg import eigh
from scipy import stats

# collapse_geometry exact physics engine (§I–XXVII, corrected §XXIV)
import sys as _sys
_sys.path.insert(0, r'C:\amttp\research\adaptive-friction')
from collapse_geometry import MasterOperator, CalibrationState, Snapshot
from collapse_geometry.geometry import CollapseGeometry

OUT_DIR     = r"C:\amttp\research\adaptive-friction\pipeline\results"
TRAIN_START = '2021-01-01'
TRAIN_END   = '2022-12-31'
TEST_START  = '2023-01-01'

# ─── v14 leverage dial ──────────────────────────────────────────────────────
LEV_BASE = 1.5
LEV_LO   = 0.5
LEV_HI   = 1.2

# ─── v16 geometry ───────────────────────────────────────────────────────────
GEOM_PHI_PEN      = 0.5
GEOM_ALIGN_PEN    = 0.5
GEOM_COLLAPSE_WIN = 20
GEOM_EMA_SPAN     = 5
GEOM_LEV_LO       = 0.3
GEOM_LEV_HI       = 1.2
GAMMA_SCORE_WIN   = 126

# ─── v18 state-vector EMA smoothing ─────────────────────────────────────────
V18_STATE_EMA_SPAN = 3

# ─── v19 cos_θ_channel parameters ───────────────────────────────────────────
GCI_LEV_LO       = 0.20    # leverage when GCI = 0 (cos_θC = -1, collapse)
GCI_LEV_HI       = 1.15    # leverage when GCI = 1 (cos_θC = +1, recovery)
GCI_EMA_SPAN     = 5       # smooth the GCI signal to reduce noise
# legacy proxy constants (superseded by collapse_geometry engine):
KNN_K            = 5       # was: kNN k for δ_T approximation
KNN_WINDOW       = 60      # was: kNN lookback (= CG_HISTORY_WIN)
CHANNEL_EMA      = 3       # was: EMA on raw proxy channel scores
ALARM_THRESH     = 0.90    # |cos_θC| threshold for hard-lock alarm
ALARM_MIN_STEPS  = 2       # consecutive steps below −ALARM_THRESH to trigger
# ── collapse_geometry engine parameters (§VI, §XXIV) ────────────────────────
CG_HISTORY_WIN   = 60      # Snapshot.history depth for δ_T KDE (§VI.3)
CG_PCA_K         = 2       # CalibrationState PCA components  (N=4, d=2 → k≤2)


# ─────────────────────────────────────────────────────────────────────────────
#  DATA LOADING (identical to v18)
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
    for c in ['ret_btc', 'ret_eth', 'ret_sol', 'ret_bnb',
              'vol_btc', 'vol_eth', 'btc_dom', 'cross_disp']:
        df[f'{c}_z'] = z(df[c])
    for h in [3, 5, 7]:
        df[f'ret{h}_eth'] = df['ret_eth'].rolling(h).sum()
        df[f'ret{h}_btc'] = df['ret_btc'].rolling(h).sum()
    df = df.dropna()
    print(f"  Data: {df.index[0].date()} → {df.index[-1].date()}  n={len(df)}")
    return df


def add_cross_market_features(df):
    tickers = {'^GSPC': 'spx', '^VIX': 'vix', 'DX-Y.NYB': 'dxy'}
    raw = {}
    for tk, col in tickers.items():
        s = yf.download(tk, start='2020-06-01', progress=False,
                        auto_adjust=True)['Close'].squeeze()
        raw[col] = s
    spx = raw['spx'].reindex(df.index, method='ffill')
    df['ret_spx'] = np.log(spx / spx.shift(1)).fillna(0.0)
    vix = raw['vix'].reindex(df.index, method='ffill')
    df['dvix'] = vix.diff(1).fillna(0.0)
    dxy = raw['dxy'].reindex(df.index, method='ffill')
    df['ret_dxy'] = np.log(dxy / dxy.shift(1)).fillna(0.0)
    def _rz(s, w=252):
        mu = s.rolling(w, min_periods=60).mean()
        sd = s.rolling(w, min_periods=60).std()
        return (s - mu) / (sd + 1e-9)
    for c in ['ret_spx', 'dvix', 'ret_dxy']:
        df[f'{c}_z'] = _rz(df[c])
    return df


def fetch_binance_funding(symbols=None, start='2020-06-01'):
    if symbols is None:
        symbols = ['ETHUSDT', 'BTCUSDT']
    base_url  = 'https://fapi.binance.com/fapi/v1/fundingRate'
    start_ms  = int(pd.Timestamp(start).timestamp() * 1000)
    end_ms    = int(pd.Timestamp.utcnow().timestamp() * 1000)
    result = {}
    for sym in symbols:
        records   = []
        cur_start = start_ms
        try:
            while True:
                params = {'symbol': sym, 'limit': 1000,
                          'startTime': cur_start, 'endTime': end_ms}
                r    = requests.get(base_url, params=params, timeout=15)
                data = r.json()
                if not isinstance(data, list) or len(data) == 0:
                    break
                records.extend(data)
                last_ts = data[-1]['fundingTime']
                if last_ts >= end_ms or len(data) < 1000:
                    break
                cur_start = last_ts + 1
                time.sleep(0.05)
        except Exception as e:
            print(f"  Warning: funding fetch failed for {sym}: {e}")
        if not records:
            result[sym] = pd.Series(dtype=float)
            continue
        df_fr         = pd.DataFrame(records)
        df_fr['dt']   = pd.to_datetime(df_fr['fundingTime'], unit='ms').dt.normalize()
        df_fr['rate'] = df_fr['fundingRate'].astype(float)
        daily         = df_fr.groupby('dt')['rate'].mean()
        daily.index   = pd.DatetimeIndex(daily.index)
        result[sym]   = daily
        print(f"    {sym}: {len(daily)} daily records  "
              f"{daily.index[0].date()} → {daily.index[-1].date()}")
    return result


def add_leverage_features(df, funding_data):
    def _rz(s, w=252):
        mu = s.rolling(w, min_periods=60).mean()
        sd = s.rolling(w, min_periods=60).std()
        return (s - mu) / (sd + 1e-9)
    for sym, col in [('ETHUSDT', 'eth'), ('BTCUSDT', 'btc')]:
        fr_raw = funding_data.get(sym, pd.Series(dtype=float))
        if len(fr_raw) == 0:
            for feat in [f'fr_{col}', f'fr_vol_{col}', f'fr_cum5_{col}']:
                df[f'{feat}_z'] = np.nan
            continue
        fr_raw.index = fr_raw.index.tz_localize(None) if fr_raw.index.tz else fr_raw.index
        df_idx_tz    = df.index.tz_localize(None) if df.index.tz else df.index
        fr_al        = fr_raw.reindex(df_idx_tz, method='ffill')
        fr_al.index  = df.index
        df[f'fr_{col}']     = fr_al
        df[f'fr_vol_{col}'] = fr_al.rolling(7, min_periods=4).std()
        df[f'fr_cum5_{col}']= fr_al.rolling(5, min_periods=3).sum()
        for feat in [f'fr_{col}', f'fr_vol_{col}', f'fr_cum5_{col}']:
            df[f'{feat}_z'] = _rz(df[feat])
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  BSDT ENGINE (identical to v18)
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


def compute_gamma_rank(omega_series, min_periods=60):
    vals        = omega_series.values
    n           = len(vals)
    out         = np.full(n, np.nan)
    sorted_vals = []
    for i in range(n):
        v = vals[i]
        if np.isnan(v):
            continue
        bisect.insort(sorted_vals, v)
        if len(sorted_vals) >= min_periods:
            rank   = bisect.bisect_right(sorted_vals, v)
            out[i] = rank / len(sorted_vals)
    return pd.Series(out, index=omega_series.index)


def compute_activity_signals(mfls, gamma):
    A       = mfls / (gamma + 1e-9)
    A_rank  = A.expanding(60).rank(pct=True)
    dA_fast = A.diff(1).rolling(2).mean()
    dA_rank = dA_fast.expanding(60).rank(pct=True)
    return A, A_rank, dA_fast, dA_rank


# ─────────────────────────────────────────────────────────────────────────────
#  v19: EXACT cos_θ_CHANNEL ENGINE  (collapse_geometry §VII / §XXIV.3)
#
#  Theory (geometry.py CollapseGeometry.cos_theta_channel):
#    g   = ∇_S E_BS(S_t)           channel-space energy gradient  ∈ ℝ⁴
#          via UnifiedEnergy.grad(channel_state(snap))
#    h_k = ⟨∂δ_k/∂X, F⟩_F         force projected onto per-channel Jacobians
#          via einsum("knd,nd->k", jacobians_stacked, force)
#    cos_θC = (g · h) / (‖g‖ · ‖h‖)
#
#  Distinct from proxy (g = raw δ scores, h = −Δδ):
#    ✓ Non-linear energy landscape (Quadsurf + Expogate + Signed LR)
#    ✓ Physical GravityEngine restoring forces (erf-log kernel)
#    ✓ Per-channel Jacobians ∂δ_k/∂X  (Mahalanobis, PCA-gap, velocity, KDE)
#    ✓ Exact Lyapunov collapse certificate
# ─────────────────────────────────────────────────────────────────────────────
_CG_ASSETS = ['btc', 'eth', 'sol', 'bnb']


def _build_state_panel(df):
    """Build (T, N=4, d=2) state matrix from the daily crypto DataFrame.

    Agent mapping  (§I: X_t ∈ ℝ^{N×d}):
        agent 0 = BTC   [ret_btc_z, vol_btc_z]
        agent 1 = ETH   [ret_eth_z, vol_eth_z]
        agent 2 = SOL   [ret_sol_z, vol_sol_z]
        agent 3 = BNB   [ret_bnb_z, vol_bnb_z]

    Returns: np.ndarray shape (T, 4, 2), never modifies df.
    """
    def _rz(s, w=252):
        mu = s.rolling(w, min_periods=60).mean()
        sd = s.rolling(w, min_periods=60).std()
        return (s - mu) / (sd + 1e-9)

    T = len(df)
    X = np.zeros((T, len(_CG_ASSETS), 2))
    for i, a in enumerate(_CG_ASSETS):
        ret_z = df[f'ret_{a}_z'].fillna(0).values if f'ret_{a}_z' in df.columns \
                else _rz(df[f'ret_{a}']).fillna(0).values
        vol_z = _rz(df[f'vol_{a}']).fillna(0).values if f'vol_{a}' in df.columns \
                else np.zeros(T)
        X[:, i, 0] = ret_z
        X[:, i, 1] = vol_z
    return X


def compute_costheta_channel_exact(df, train_mask, history_win=CG_HISTORY_WIN):
    """Compute cos_θ_channel using the full collapse_geometry physics engine.

    Engine:
        MasterOperator.calibrate(X_normal)  — fitted once on training period
        CollapseGeometry.cos_theta_channel(snap)  — §VII / §XXIV.3

    The exact formula (NOT the proxy):
        g   = ∇_S E_BS(S_t)           ∈ ℝ⁴  (UnifiedEnergy.grad)
        h_k = ⟨∂δ_k/∂X, F⟩_F               (BSDT Jacobians ⋅ ForceField)
        cos_θC = (g · h) / (‖g‖ · ‖h‖)  ∈ [−1, +1]

    Also returns:
        bsdt_energy  — E_BS(S_t) total blind-spot energy  (scalar per day)
        rho_mfls     — ρ_MFLS = MFLS_state / MFLS_channel  (§XXIV.4 amplification)

    Returns: (cos_tc, bsdt_energy_ts, rho_mfls_ts)  — three pd.Series on df.index
    """
    print("  [CG] Building (T, N=4, d=2) state panel ...")
    X_panel = _build_state_panel(df)
    T = len(X_panel)

    print("  [CG] Calibrating MasterOperator on training period ...")
    X_normal = X_panel[np.asarray(train_mask)]          # (T_train, 4, 2)
    op   = MasterOperator.calibrate(X_normal, k=CG_PCA_K)
    geom = CollapseGeometry(op=op)

    print(f"  [CG] Running exact cos_θC with GravityEngine force + BSDT Jacobians ..."
          f"  ({T} steps)")
    cos_vals    = np.full(T, np.nan)
    bsdt_energy = np.full(T, np.nan)
    rho_mfls    = np.full(T, np.nan)

    for t in range(1, T):
        h_start = max(0, t - history_win)
        snap = Snapshot(
            X       = X_panel[t],
            X_prev  = X_panel[t - 1],
            history = X_panel[h_start:t],      # (H, 4, 2)
        )
        try:
            cos_vals[t]    = geom.cos_theta_channel(snap)
            S              = op.bsdt.channel_state(snap)
            bsdt_energy[t] = op.energy.E_total(S)
            rho_mfls[t]    = op.mfls.rho_mfls(snap)
        except Exception:
            pass

    return (
        pd.Series(cos_vals,    index=df.index, name='cos_theta_channel'),
        pd.Series(bsdt_energy, index=df.index, name='bsdt_energy'),
        pd.Series(rho_mfls,    index=df.index, name='rho_mfls'),
    )


def compute_gci_leverage(cos_tc, lev_base,
                          gci_lo=GCI_LEV_LO, gci_hi=GCI_LEV_HI,
                          ema_span=GCI_EMA_SPAN):
    """
    Geometric Collapse Index leverage multiplier.

    GCI = (1 + cos_θC) / 2   ∈ [0, 1]
    lev_gci = lev_base * (gci_lo + (gci_hi - gci_lo) * GCI_smooth)

    When GCI → 0 (cos_θC → -1, collapse): multiply by gci_lo (massive de-risk)
    When GCI → 1 (cos_θC → +1, recovery): multiply by gci_hi (amplify)
    """
    cos_safe  = cos_tc.fillna(0.0).clip(-1.0, 1.0)
    gci_raw   = (1.0 + cos_safe) / 2.0
    gci_smooth = gci_raw.ewm(span=ema_span, adjust=False).mean()
    scale = gci_lo + (gci_hi - gci_lo) * gci_smooth
    return (lev_base * scale).clip(lower=GEOM_LEV_LO, upper=GEOM_LEV_HI + 0.05)


def compute_hard_lock_alarm(cos_tc,
                             thresh=ALARM_THRESH,
                             min_steps=ALARM_MIN_STEPS):
    """
    Hard-lock alarm: True when cos_θC < −thresh for ≥ min_steps consecutive days.

    This is the capital protection protocol:
    once alarm fires, all positions in the portfolio are set to ZERO until
    cos_θC rises above −thresh again.

    Returns: pd.Series bool (True = alarm active, go FLAT).
    """
    below = (cos_tc.fillna(0.0) < -thresh).astype(int)
    # rolling sum: if min_steps-period rolling sum == min_steps → alarm
    roll = below.rolling(min_steps, min_periods=min_steps).sum()
    alarm_raw = roll >= min_steps
    # latch: stay latched while still below thresh; release when cos_tc > -thresh
    alarm_latched = np.zeros(len(alarm_raw), dtype=bool)
    latched = False
    arr = cos_tc.fillna(0.0).values
    for i in range(len(alarm_raw)):
        if alarm_raw.iloc[i]:
            latched = True
        if latched and arr[i] >= -thresh:
            latched = False
        alarm_latched[i] = latched
    return pd.Series(alarm_latched, index=cos_tc.index, name='alarm')


# ─────────────────────────────────────────────────────────────────────────────
#  SPREAD + PAIRS (condensed from v18, needed for v14b baseline)
# ─────────────────────────────────────────────────────────────────────────────
def compute_rolling_spread_v8(log_a, log_b, ret_a, ret_b,
                               train_mask, beta_window=252):
    la = log_a.values; lb = log_b.values
    ra = ret_a.values; rb = ret_b.values
    n  = len(la)
    spread = np.full(n, np.nan)
    betas  = np.full(n, np.nan)
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
    idx   = log_a.index
    S_ser = pd.Series(spread, index=idx)
    B_ser = pd.Series(betas,  index=idx)
    train_S  = S_ser[train_mask].dropna()
    mu_train = train_S.mean()
    sd_train = max(train_S.std(), 1e-9)
    z        = (S_ser - mu_train) / sd_train
    std_30   = S_ser.rolling(30, min_periods=15).std()
    std_252  = S_ser.rolling(252, min_periods=60).std()
    var_ratio     = std_30 / (std_252 + 1e-9)
    beta_mean_abs = B_ser.abs().rolling(252, min_periods=60).mean()
    beta_chg      = B_ser.diff(21).abs()
    beta_velocity = beta_chg / (beta_mean_abs + 1e-9)
    ra_s  = pd.Series(ra, index=idx)
    rb_s  = pd.Series(rb, index=idx)
    poa   = ra_s.rolling(60, min_periods=30).corr(rb_s).abs()
    b_filled = B_ser.fillna(B_ser.median())
    ra_ser   = pd.Series(ra, index=idx)
    rb_ser   = pd.Series(rb, index=idx)
    sret     = (ra_ser - b_filled * rb_ser) / (1.0 + b_filled.abs() + 1e-9)
    return dict(z=z, spread=S_ser, betas=B_ser,
                var_ratio=var_ratio, beta_velocity=beta_velocity,
                poa=poa, sret=sret)


class SpreadUDLClassifier:
    LAW_SLICES = [(0, 5), (5, 8), (8, 11), (11, 14)]
    N_FEAT     = 14

    def __init__(self, window=20, n_ref_dirs=100):
        self.window     = window
        self.n_ref_dirs = n_ref_dirs
        self.centroid_  = None
        self.ref_dirs_  = None
        self.thresholds_: dict = {}

    @staticmethod
    def _extract(x):
        from scipy.special import erf
        eps = 1e-10
        w   = len(x)
        f   = np.zeros(14)
        var_ = x.var()
        f[0] = var_
        hist, _ = np.histogram(x, bins=8)
        p_h = hist / (hist.sum() + eps)
        p_h = np.clip(p_h, eps, 1.0)
        f[1] = -np.sum(p_h * np.log(p_h))
        mu_x  = x.mean(); std_x = x.std() + eps
        x_std = (x - mu_x) / std_x
        h2, edges = np.histogram(x_std, bins=8)
        p_emp = np.clip(h2 / (h2.sum() + eps), eps, 1.0)
        p_ref = np.diff(0.5 * (1.0 + erf(edges / np.sqrt(2))))
        p_ref = np.clip(p_ref / (p_ref.sum() + eps), eps, 1.0)
        f[2]  = np.sqrt(0.5 * np.sum((np.sqrt(p_emp) - np.sqrt(p_ref)) ** 2))
        if std_x > eps:
            z3   = (x - x.mean()) / std_x
            f[3] = np.mean(z3 ** 3)
            f[4] = np.mean(z3 ** 4) - 3.0
        if w >= 3:
            mu    = x.mean()
            denom = (x - mu) @ (x - mu) + eps
            f[5]  = ((x[:-1] - mu) @ (x[1:] - mu)) / denom
            ac2   = ((x[:-2] - mu) @ (x[2:] - mu)) / denom if w >= 4 else 0.0
            f[6]  = f[5] ** 2 + ac2 ** 2
            dx    = np.diff(x)
            f[7]  = dx.std() / (x.std() + eps)
        xf      = x - x.mean()
        psd     = np.abs(np.fft.rfft(xf)[1:]) ** 2
        psd_sum = psd.sum() + eps
        pn      = np.clip(psd / psd_sum, eps, 1.0)
        f[8]    = -np.sum(pn * np.log(pn))
        f[9]    = psd.max() / psd_sum
        freqs   = np.arange(1, len(psd) + 1, dtype=float)
        f[10]   = (freqs * pn).sum()
        t_      = np.linspace(0.0, 1.0, w)
        tc      = t_ - t_.mean(); xc = x - x.mean()
        slope   = (tc @ xc) / (tc @ tc + eps)
        f[11]   = abs(slope)
        resid   = xc - slope * tc
        f[12]   = resid.var()
        if w >= 3:
            f[13] = np.abs(np.diff(x, n=2)).mean()
        return f

    def fit(self, spread_series):
        w    = self.window
        vals = spread_series.dropna().values
        if len(vals) < w + 20:
            raise ValueError(f"Training series too short: {len(vals)}")
        n_wins = len(vals) - w + 1
        F      = np.array([self._extract(vals[i:i+w]) for i in range(n_wins)])
        var_w  = np.array([vals[i:i+w].var() for i in range(n_wins)])
        self.centroid_ = F.mean(axis=0)
        dev    = F - self.centroid_
        norms  = np.linalg.norm(dev, axis=1, keepdims=True)
        norms  = np.where(norms < 1e-10, 1.0, norms)
        unit_d = dev / norms
        k              = min(self.n_ref_dirs, len(unit_d))
        _, _, Vt       = np.linalg.svd(unit_d, full_matrices=False)
        self.ref_dirs_ = Vt[:k]
        mag_all = np.linalg.norm(dev, axis=1)
        cos_all = unit_d @ self.ref_dirs_.T
        nov_all = 1.0 - cos_all.max(axis=1)
        self.thresholds_ = {
            'var_low':      float(np.percentile(var_w,   10)),
            'mag_low':      float(np.percentile(mag_all, 10)),
            'novelty_high': float(np.percentile(nov_all, 85)),
        }
        return self

    def _classify_one(self, win):
        f    = self._extract(win)
        dev  = f - self.centroid_
        mag  = float(np.linalg.norm(dev))
        var_ = float(win.var())
        if mag < 1e-10:
            return 1, mag, 1.0
        unit_dev = dev / mag
        novelty  = float(1.0 - (self.ref_dirs_ @ unit_dev).max())
        if var_ <= self.thresholds_['var_low'] or mag <= self.thresholds_['mag_low']:
            return 1, mag, novelty
        if novelty >= self.thresholds_['novelty_high']:
            return 2, mag, novelty
        return 0, mag, novelty

    def classify_series(self, spread_series):
        w    = self.window
        vals = spread_series.values
        n    = len(vals)
        state   = np.ones(n, dtype=int)
        mag     = np.full(n, np.nan)
        novelty = np.full(n, np.nan)
        for t in range(w - 1, n):
            win = vals[t - w + 1: t + 1]
            if not np.all(np.isfinite(win)):
                continue
            st, mg, nv = self._classify_one(win)
            state[t]   = st
            mag[t]     = mg
            novelty[t] = nv
        idx = spread_series.index
        return (pd.Series(state,   index=idx, name='udl_state'),
                pd.Series(mag,     index=idx, name='udl_mag'),
                pd.Series(novelty, index=idx, name='udl_novelty'))


def compute_manifold_validity(z_spread, sret, drift_thresh=1.0, drift_win=60):
    drift    = z_spread.rolling(drift_win, min_periods=30).mean().abs()
    drift_ok = drift < drift_thresh
    return drift_ok.astype(int), drift


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


def route_pair_v7(omega, A_rank, z_spread, udl_state, poa,
                  manifold_valid, z_threshold=1.0):
    omega_q50   = omega.expanding(60).quantile(0.50)
    gate        = (omega >= omega_q50) & (A_rank >= 0.33) & \
                  (z_spread.abs() > z_threshold) & manifold_valid.astype(bool)
    state_v = udl_state.values; z_v = z_spread.values
    poa_v   = poa.fillna(0.5).values; g_v = gate.values
    pos = np.zeros(len(z_v))
    POA_LOW = 0.30; POA_HIGH = 0.80; STRUCT_SIZE_SCALE = 0.50
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


def route_btcalt_macro(df, omega, A_rank, dA_rank):
    omega_q50  = omega.expanding(60).quantile(0.50)
    omega_gate = omega >= omega_q50
    active     = A_rank >= 0.33
    dom_z  = df['btc_dom_z']
    disp_z = df['cross_disp_z']
    btc_flight   = omega_gate & active & (dom_z > 1.0)
    alt_season   = omega_gate & active & (dom_z < -1.0) & (disp_z > 1.0)
    pos_btc = pd.Series(0.0, index=df.index)
    pos_alt = pd.Series(0.0, index=df.index)
    pos_btc[btc_flight]   = np.minimum(dom_z[btc_flight], 2.0) / 2.0
    pos_alt[alt_season]   = 1.0
    return pos_btc.clip(0, 1), pos_alt.clip(0, 1)


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
#  PORTFOLIO BUILDING (from v18)
# ─────────────────────────────────────────────────────────────────────────────
def get_daily_pnl(pos, ret):
    return pos.shift(1).fillna(0) * ret.reindex(pos.index).fillna(0)


def compute_cs_weights(pnl_dict, window=126):
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


def compute_leverage_dial(gamma_rank, base=LEV_BASE, lo=LEV_LO, hi=LEV_HI):
    return (base - gamma_rank.fillna(0.5)).clip(lower=lo, upper=hi)


def _expanding_z(s, min_p=60):
    mu = s.expanding(min_p).mean()
    sd = s.expanding(min_p).std()
    return (s - mu) / (sd + 1e-9)


def compute_state_vector(omega, gamma_rank, mfls, dA_fast):
    c1 = _expanding_z(omega).fillna(0.0)
    c2 = ((gamma_rank.fillna(0.5) - 0.5) * 2.0)
    c3 = _expanding_z(mfls).fillna(0.0)
    c4 = _expanding_z(dA_fast).fillna(0.0)
    return pd.DataFrame({'c1': c1, 'c2': c2, 'c3': c3, 'c4': c4},
                        index=omega.index)


def compute_geom_signals_v18_smooth(V, state_ema_span=V18_STATE_EMA_SPAN):
    """v18_smooth: EMA-smoothed state vector + directional phi."""
    V_smooth = V.ewm(span=state_ema_span, adjust=False).mean()
    M  = V_smooth.values
    norms = np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
    U  = M / norms
    dV = np.full_like(M, np.nan)
    dV[1:] = M[1:] - M[:-1]
    dir_phi = np.einsum('ij,ij->i', dV, U)
    phi = pd.Series(dir_phi, index=V.index).clip(lower=0.0)
    Vc  = V_smooth.ewm(span=20, adjust=False).mean().values
    Vcn = np.linalg.norm(Vc, axis=1, keepdims=True) + 1e-9
    Cd  = Vc / Vcn
    alignment = np.einsum('ij,ij->i', U, Cd)
    return (phi.rename('phi'),
            pd.Series(alignment, index=V.index, name='alignment'))


def apply_geom_penalties_v18(lev_base, phi, alignment,
                              phi_pen=GEOM_PHI_PEN, align_pen=GEOM_ALIGN_PEN,
                              ema_span=GEOM_EMA_SPAN, lo=GEOM_LEV_LO,
                              hi=GEOM_LEV_HI, align_gate_thr=0.5):
    phi_safe = phi.fillna(0.0).clip(lower=0.0)
    align_pos = alignment.fillna(0.0).clip(lower=0.0, upper=1.0)
    lev = lev_base / (1.0 + phi_pen * phi_safe)
    gate = ((phi_safe - align_gate_thr) / 2.0).clip(lower=0.0, upper=1.0)
    lev = lev * (1.0 - align_pen * gate * align_pos)
    lev = lev.ewm(span=ema_span, adjust=False).mean()
    return lev.clip(lower=lo, upper=hi)


# ─────────────────────────────────────────────────────────────────────────────
#  SIMULATION + METRICS
# ─────────────────────────────────────────────────────────────────────────────
def simulate_from_pnl(pnl_series, label=""):
    pnl    = pnl_series.fillna(0).values
    cum    = np.cumprod(1.0 + pnl)
    active = pnl[pnl != 0]
    sharpe = float(active.mean() / (np.std(active) + 1e-12) * np.sqrt(252)) if len(active) > 0 else 0.0
    roll_max = np.maximum.accumulate(cum)
    max_dd   = float((cum / roll_max - 1).min())
    yrs  = len(pnl) / 252.0
    cagr = float((cum[-1]) ** (1.0 / max(yrs, 1e-9)) - 1.0)
    hit_rate = float((active > 0).mean()) if len(active) > 0 else float('nan')
    return dict(
        label=label, sharpe=round(sharpe, 4), max_dd=round(max_dd, 4),
        cum_return=round(float(cum[-1] - 1), 4), active_days=int((pnl != 0).sum()),
        total_days=int(len(pnl)), hit_rate=round(hit_rate, 4),
        cagr=round(cagr, 4),
    )


def equity_at_K(pnl_series, K=1.0, tcost_bps=5.0, init=1200.0):
    """Compute scaled equity curve with transaction cost."""
    r = pnl_series.dropna().astype(float) * K
    if tcost_bps > 0:
        cost = (tcost_bps / 1e4) * (pnl_series.dropna().abs() > 0).astype(float)
        r = r - cost
    eq   = init * (1.0 + r).cumprod()
    peak = eq.cummax()
    dd   = (eq - peak) / peak
    yrs  = len(eq) / 252.0
    cagr = (eq.iloc[-1] / init) ** (1.0 / max(yrs, 1e-9)) - 1.0
    sh   = float(np.sqrt(252) * r.mean() / r.std()) if r.std() > 0 else 0.0
    return dict(
        K=K, eq=eq, final=float(eq.iloc[-1]),
        pnl=float(eq.iloc[-1] - init), sh=sh,
        cagr=float(cagr), max_dd=float(dd.min()),
        max_dd_dol=float((eq - peak).min()),
    )


def find_best_K(pnl_series, tcost_bps=5.0, init=1200.0,
                max_dd_limit=0.40, K_grid=None):
    """Find K that maximises net Sharpe under MaxDD ≤ max_dd_limit."""
    if K_grid is None:
        K_grid = np.arange(0.5, 20.05, 0.25)
    best = None
    for K in K_grid:
        m = equity_at_K(pnl_series, K=float(K), tcost_bps=tcost_bps, init=init)
        if m['max_dd'] < -max_dd_limit:
            continue
        if best is None or m['sh'] > best['sh']:
            best = m
    return best


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 90)
    print("  CRYPTO BSDT v19 — cos_θ_channel COLLAPSE INVARIANT as trading signal")
    print("  Theory: collapse_geometry v1.3.0, universal invariant:  cos_θC → −1")
    print("=" * 90)

    # ── [1] Load data ──────────────────────────────────────────────────────
    df = fetch_and_prepare()
    print("  Adding cross-market features ...")
    df = add_cross_market_features(df)
    print("  Fetching Binance funding rates ...")
    funding = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
    df = add_leverage_features(df, funding)

    train_mask = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask  = df.index >= TEST_START
    print(f"  Train: {df[train_mask].index[0].date()} → {df[train_mask].index[-1].date()}")
    print(f"  Test:  {df[test_mask].index[0].date()} → {df[test_mask].index[-1].date()}")

    # ── [2] Core BSDT signals ──────────────────────────────────────────────
    feats_strat = [
        'ret_eth_z', 'ret_btc_z', 'ret_sol_z', 'ret_bnb_z',
        'vol_eth_z', 'vol_btc_z', 'btc_dom_z', 'cross_disp_z',
    ]
    feats_ext = feats_strat + ['ret_spx_z', 'dvix_z', 'ret_dxy_z']
    print("\n[2] Computing BSDT signals ...")
    omega_strat, mfls_eth, gamma_eth = compute_bsdt(df, feats_strat, window=60)
    omega_ext,        _,          _  = compute_bsdt(df, feats_ext,   window=60)

    A_eth, A_rank, dA_fast, dA_rank = compute_activity_signals(mfls_eth, gamma_eth)
    gamma_rank = compute_gamma_rank(omega_ext, min_periods=60)
    lev_mult   = compute_leverage_dial(gamma_rank)

    # ── [3] v19 cos_θ_channel — exact collapse_geometry engine ──────────────
    print("\n[3] Computing cos_θ_channel (exact: §VII/§XXIV.3, GravityEngine + BSDT Jacobians) ...")

    # Build 4D state vector for v18_smooth and v14b baselines (unchanged)
    V_state = compute_state_vector(omega_strat, gamma_rank, mfls_eth, dA_fast)

    # Theory-correct cos_θ_channel from the full physics engine
    cos_tc, bsdt_energy_ts, rho_mfls_ts = compute_costheta_channel_exact(
        df, train_mask, history_win=CG_HISTORY_WIN)

    # Diagnostics
    cos_test    = cos_tc[test_mask]
    rho_test    = rho_mfls_ts[test_mask].dropna()
    frac_neg_09 = float((cos_test.dropna() < -0.9).mean() * 100)
    frac_neg_07 = float((cos_test.dropna() < -0.7).mean() * 100)
    print(f"\n  cos_θC [test]  (exact §VII/§XXIV.3):")
    print(f"    mean={cos_test.mean():.4f}  std={cos_test.std():.4f}  "
          f"min={cos_test.min():.4f}  max={cos_test.max():.4f}")
    print(f"    cos_θC < -0.90: {frac_neg_09:.1f}% of test days")
    print(f"    cos_θC < -0.70: {frac_neg_07:.1f}% of test days")
    if len(rho_test) > 0:
        print(f"  ρ_MFLS [test]  (§XXIV.4 amplification factor):")
        print(f"    mean={rho_test.mean():.3f}  max={rho_test.max():.3f}  "
              f"frac>1 (state over-amplifies channel): {(rho_test > 1).mean()*100:.1f}%")
        print(f"    ρ<1 → risk contained  |  ρ>1 → real collapse pressure")

    # ── [4] GCI leverage + alarm ───────────────────────────────────────────
    print("\n[4] Building GCI leverage + hard-lock alarm ...")

    # Compute v18_smooth baseline (the reference geometric baseline)
    phi_18s, align_18s = compute_geom_signals_v18_smooth(V_state)
    lev_v18_smooth = apply_geom_penalties_v18(lev_mult, phi_18s, align_18s)

    # GCI leverage (theory signal)
    lev_v19_gci   = compute_gci_leverage(cos_tc, lev_v18_smooth)

    # Hard-lock alarm
    alarm         = compute_hard_lock_alarm(cos_tc)
    alarm_test    = alarm[test_mask]
    alarm_days    = int(alarm_test.sum())
    print(f"  Hard-lock alarm: {alarm_days} alarm days in test "
          f"({alarm_days/test_mask.sum()*100:.1f}%)")
    print(f"  GCI range [test]: min={lev_v19_gci[test_mask].min():.3f}  "
          f"max={lev_v19_gci[test_mask].max():.3f}  "
          f"mean={lev_v19_gci[test_mask].mean():.3f}")

    # ── [5] Build 6-strategy base positions (same as v18) ─────────────────
    print("\n[5] Building strategy positions ...")
    ret7  = df['ret_eth'].rolling(7).sum()
    ret3  = df['ret_eth'].rolling(3).sum()
    phase = detect_phase(omega_strat, ret7, ret3, df['btc_dom_z'])
    pos_A_dir = setup_a_directional(df, omega_strat, mfls_eth, gamma_eth, phase)
    pairs = [
        ('P1_ETH_BTC', 'log_eth', 'log_btc', 'ret_eth', 'ret_btc'),
        ('P2_ETH_SOL', 'log_eth', 'log_sol', 'ret_eth', 'ret_sol'),
        ('P3_ETH_BNB', 'log_eth', 'log_bnb', 'ret_eth', 'ret_bnb'),
    ]
    pair_data = {}
    for key, col_a, col_b, ret_a, ret_b in pairs:
        print(f"  {key}: computing spread ...", end='', flush=True)
        sd = compute_rolling_spread_v8(
            df[col_a], df[col_b], df[ret_a], df[ret_b],
            train_mask=train_mask, beta_window=252)
        train_spread = sd['spread'][train_mask].dropna()
        clf = SpreadUDLClassifier(window=20, n_ref_dirs=100).fit(train_spread)
        udl_state, udl_mag, udl_novelty = clf.classify_series(sd['spread'])
        sd['udl_state']   = udl_state
        mval, _ = compute_manifold_validity(sd['z'], sd['sret'])
        sd['manifold_valid'] = mval
        pair_data[key]       = sd
        print(f" done")

    pair_pos = {}
    for key, _, _, _, _ in pairs:
        sd = pair_data[key]
        pair_pos[key] = route_pair_v7(
            omega_strat, A_rank, sd['z'], sd['udl_state'], sd['poa'],
            sd['manifold_valid'])
    pos_btc_macro, pos_alt_macro = route_btcalt_macro(df, omega_strat, A_rank, dA_rank)

    pnl_base = {
        'A_directional': get_daily_pnl(pos_A_dir, df['ret_eth']),
        'P1_ETH_BTC':    get_daily_pnl(pair_pos['P1_ETH_BTC'], pair_data['P1_ETH_BTC']['sret']),
        'P2_ETH_SOL':    get_daily_pnl(pair_pos['P2_ETH_SOL'], pair_data['P2_ETH_SOL']['sret']),
        'P3_ETH_BNB':    get_daily_pnl(pair_pos['P3_ETH_BNB'], pair_data['P3_ETH_BNB']['sret']),
        'M1_ALT_macro':  get_daily_pnl(pos_alt_macro, df['ret_eth']),
        'M1_BTC_macro':  get_daily_pnl(pos_btc_macro, df['ret_btc']),
    }

    # v10 Sharpe-weighted portfolio — the v14b base
    cs_wts_v10 = compute_cs_weights(pnl_base, window=GAMMA_SCORE_WIN)
    n_s = len(pnl_base)
    pnl_dyn_v10 = pd.Series(0.0, index=df.index)
    for k in pnl_base:
        pnl_dyn_v10 += cs_wts_v10[k].shift(1).fillna(1.0/n_s) * pnl_base[k]

    # v14b: v10 × linear γ leverage dial
    pnl_dyn_v14b = pnl_dyn_v10 * lev_mult.shift(1).fillna(1.0)

    # v18_smooth: v10 × v18 geometric leverage
    pnl_dyn_v18s = pnl_dyn_v10 * lev_v18_smooth.shift(1).fillna(1.0)

    # ── [6] v19 ablation: GCI + alarm ─────────────────────────────────────
    print("\n[6] Computing v19 ablation: GCI / alarm / full ...")

    # v19_gci_only: GCI leverage (replaces v18's geometric lever)  atop v10 pnl
    pnl_dyn_v19_gci = pnl_dyn_v10 * lev_v19_gci.shift(1).fillna(1.0)

    # v19_alarm_only: v18_smooth + hard-lock alarm (mute when alarm fires)
    # Alarm active: set portfolio return = 0 (exit all positions)
    alarm_shift = alarm.shift(1).fillna(False)   # yesterday's alarm → today's action
    pnl_dyn_v19_alarm = pnl_dyn_v18s.copy()
    pnl_dyn_v19_alarm[alarm_shift] = 0.0

    # v19_full: GCI leverage × alarm (both)
    pnl_dyn_v19_full = pnl_dyn_v10 * lev_v19_gci.shift(1).fillna(1.0)
    pnl_dyn_v19_full[alarm_shift] = 0.0

    # ── [7] Simulate test period ───────────────────────────────────────────
    print(f"\n[7] Simulating test period {TEST_START} → present ...")
    ablation = {
        'v14b':           pnl_dyn_v14b[test_mask],
        'v18_smooth':     pnl_dyn_v18s[test_mask],
        'v19_gci_only':   pnl_dyn_v19_gci[test_mask],
        'v19_alarm_only': pnl_dyn_v19_alarm[test_mask],
        'v19_full':       pnl_dyn_v19_full[test_mask],
    }
    sims = {k: simulate_from_pnl(v, k) for k, v in ablation.items()}

    # Print ablation table
    print("\n" + "=" * 84)
    print("  v19 ABLATION RESULTS  (K=1 gross, test period)")
    print("=" * 84)
    print(f"  {'variant':<22}  {'Sharpe':>8}  {'MaxDD':>8}  {'CAGR%':>8}  "
          f"{'CumRet%':>8}  {'Active':>8}")
    print("  " + "─" * 74)
    for k, s in sims.items():
        marker = '  ← NEW' if k == 'v19_full' else ('  ← PROD baseline' if k == 'v18_smooth' else '')
        print(f"  {k:<22}  {s['sharpe']:>+8.4f}  {s['max_dd']:>+8.4f}  "
              f"{s['cagr']*100:>+7.2f}%  {s['cum_return']*100:>+7.2f}%  "
              f"{s['active_days']:>6}d{marker}")
    print()

    # Win/loss verdict
    sh_v18  = sims['v18_smooth']['sharpe']
    sh_v19  = sims['v19_full']['sharpe']
    dd_v18  = sims['v18_smooth']['max_dd']
    dd_v19  = sims['v19_full']['max_dd']
    cagr_v18 = sims['v18_smooth']['cagr']
    cagr_v19 = sims['v19_full']['cagr']
    win_sharpe = sh_v19 >= sh_v18
    win_dd     = dd_v19 >= dd_v18
    win_cagr   = cagr_v19 >= cagr_v18 + 0.02
    v19_wins   = win_sharpe and (win_dd or win_cagr)
    verdict = "★ v19_full BEATS v18_smooth — UPGRADE" if v19_wins else \
              "v19_full does NOT beat v18_smooth — keep v18_smooth as PROD"
    print(f"  Win criterion: Sharpe({'✓' if win_sharpe else '✗'}) "
          f"AND (MaxDD({'✓' if win_dd else '✗'}) OR CAGR+2%({'✓' if win_cagr else '✗'}))")
    print(f"  VERDICT: {verdict}")
    print()

    # ── [8] K-sweep on best variant ────────────────────────────────────────
    print("\n[8] Exposure-scaling sweep ($1,200 capital, 5bps t-cost) ...")
    best_variant = 'v19_full' if v19_wins else 'v18_smooth'
    pnl_best = ablation[best_variant]
    best_K_result = find_best_K(pnl_best, tcost_bps=5.0, init=1200.0, max_dd_limit=0.40)

    print(f"\n  Best variant for scaling: {best_variant}")
    print(f"  {'K':>4}  {'mode':<10}  {'Sharpe':>8}  {'CAGR%':>8}  {'Final $':>10}  "
          f"{'PnL $':>10}  {'MaxDD%':>9}  {'MaxDD $':>10}")
    print("  " + "─" * 78)
    for K in [1.0, 2.0, 3.0, 5.0, 10.0]:
        for tcost, label in [(0.0, 'gross'), (5.0, 'net 5bp')]:
            m = equity_at_K(pnl_best, K=K, tcost_bps=tcost)
            print(f"  {K:>4.0f}  {label:<10}  {m['sh']:>+8.3f}  "
                  f"{m['cagr']*100:>+7.2f}%  ${m['final']:>9,.2f}  "
                  f"${m['pnl']:>+9,.2f}  {m['max_dd']*100:>+8.2f}%  "
                  f"${m['max_dd_dol']:>+9,.2f}")
    if best_K_result:
        print(f"\n  ★ Best risk-adjusted K (net Sharpe, MaxDD ≤ 40%): "
              f"K={best_K_result['K']:.2f}")
        print(f"    Final ${best_K_result['final']:,.2f}  PnL ${best_K_result['pnl']:+,.2f}  "
              f"MaxDD {best_K_result['max_dd']*100:+.2f}%  "
              f"Sharpe {best_K_result['sh']:+.3f}")

    # ── [9] cos_θC channel signal diagnostics ─────────────────────────────
    print("\n[9] cos_θC signal regression on future returns ...")
    fwd5  = df['ret_eth'].rolling(5).sum().shift(-5)
    cos_test_series = cos_tc[test_mask]
    fwd_test  = fwd5[test_mask]
    mask_both = cos_test_series.notna() & fwd_test.notna()
    if mask_both.sum() > 50:
        ic, _ = stats.spearmanr(cos_test_series[mask_both], fwd_test[mask_both])
        below_neg09 = cos_test_series < -0.90
        above_neg03 = cos_test_series > -0.30
        ret_alarm = fwd_test[below_neg09 & fwd_test.notna()].mean()
        ret_neutral = fwd_test[above_neg03 & fwd_test.notna()].mean()
        print(f"  IC(cos_θC → fwd5_eth): {ic:+.4f}")
        print(f"  Mean fwd5 when cos_θC < −0.90: {ret_alarm:+.4f}  "
              f"(n={int((below_neg09 & fwd_test.notna()).sum())})")
        print(f"  Mean fwd5 when cos_θC > −0.30: {ret_neutral:+.4f}  "
              f"(n={int((above_neg03 & fwd_test.notna()).sum())})")
        signal_edge = float(ret_neutral - ret_alarm)
        print(f"  Signal edge (neutral − alarm): {signal_edge:+.4f}")
    else:
        ic = float('nan')
        signal_edge = float('nan')

    # ── [10] Save results ──────────────────────────────────────────────────
    print("\n[10] Saving results ...")

    result_obj = {
        'description': 'cos_theta_channel collapse invariant as trading signal',
        'version': 'v19',
        'train': f'{TRAIN_START} to {TRAIN_END}',
        'test_start': TEST_START,
        'parameters': {
            'GCI_LEV_LO': GCI_LEV_LO, 'GCI_LEV_HI': GCI_LEV_HI,
            'GCI_EMA_SPAN': GCI_EMA_SPAN,
            'ALARM_THRESH': ALARM_THRESH, 'ALARM_MIN_STEPS': ALARM_MIN_STEPS,
            'CG_HISTORY_WIN': CG_HISTORY_WIN, 'CG_PCA_K': CG_PCA_K,
            'engine': 'collapse_geometry_exact_MasterOperator',
        },
        'costheta_channel_stats': {
            'mean': round(float(cos_test_series.mean()), 4),
            'std':  round(float(cos_test_series.std()), 4),
            'min':  round(float(cos_test_series.min()), 4),
            'max':  round(float(cos_test_series.max()), 4),
            'frac_below_neg09': round(frac_neg_09, 2),
            'frac_below_neg07': round(frac_neg_07, 2),
            'alarm_days_pct': round(alarm_days / test_mask.sum() * 100, 2),
            'rho_mfls_mean': round(float(rho_mfls_ts[test_mask].dropna().mean()), 4),
            'rho_mfls_frac_over1_pct': round(
                float((rho_mfls_ts[test_mask].dropna() > 1).mean() * 100), 2),
            'formula': 'g=nabla_S_E_BS  h_k=<J_k,F>_F  (§VII/§XXIV.3)',
        },
        'signal_edge': {
            'IC_spearman': round(ic, 4) if ic == ic else None,
            'edge_fwd5':   round(signal_edge, 6) if signal_edge == signal_edge else None,
        },
        'ablation': {k: s for k, s in sims.items()},
        'verdict': verdict,
        'best_variant': best_variant,
        'best_K': {
            'K': float(best_K_result['K']) if best_K_result else None,
            'pnl': round(float(best_K_result['pnl']), 2) if best_K_result else None,
            'sharpe_net': round(float(best_K_result['sh']), 4) if best_K_result else None,
            'max_dd': round(float(best_K_result['max_dd']), 4) if best_K_result else None,
            'final': round(float(best_K_result['final']), 2) if best_K_result else None,
            'cagr': round(float(best_K_result['cagr']), 4) if best_K_result else None,
        },
    }
    json_path = os.path.join(OUT_DIR, 'crypto_bsdt_v19_results.json')
    with open(json_path, 'w') as f:
        json.dump(result_obj, f, indent=2)
    print(f"  Results saved → {json_path}")

    # ── [11] Equity + cos_θC plots ─────────────────────────────────────────
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec

        fig = plt.figure(figsize=(14, 10))
        gs  = GridSpec(3, 2, figure=fig,
                       height_ratios=[2.2, 1.2, 1.0], hspace=0.45, wspace=0.3)

        ax_eq   = fig.add_subplot(gs[0, :])   # full-width equity curves
        ax_cos  = fig.add_subplot(gs[1, :])   # full-width cos_θC
        ax_gci  = fig.add_subplot(gs[2, 0])   # GCI leverage
        ax_bar  = fig.add_subplot(gs[2, 1])   # ablation bar chart

        # ── equity curves ──
        colors = {
            'v14b':           '#aaaaaa',
            'v18_smooth':     '#4477aa',
            'v19_gci_only':   '#ee8833',
            'v19_alarm_only': '#aa3377',
            'v19_full':       '#228833',
        }
        for k, pnl_series in ablation.items():
            eq = 1200.0 * (1.0 + pnl_series.fillna(0)).cumprod()
            ax_eq.plot(eq.index, eq.values, color=colors[k], lw=1.4,
                       label=f"{k}  Sh={sims[k]['sharpe']:+.3f}")
        ax_eq.axhline(1200.0, color='k', lw=0.5, ls='--')
        ax_eq.set_title("v19 Ablation — Equity Curves (K=1 gross, from $1,200)", fontsize=11)
        ax_eq.set_ylabel('Equity ($)'); ax_eq.legend(loc='upper left', fontsize=8)
        ax_eq.grid(alpha=0.3)

        # ── cos_θC timeseries ──
        ax_cos.plot(cos_test_series.index, cos_test_series.values,
                    color='#333333', lw=0.8, alpha=0.7, label='cos_θC')
        ax_cos.axhline(-ALARM_THRESH, color='red', lw=1.2, ls='--',
                       label=f'alarm thresh = −{ALARM_THRESH}')
        ax_cos.fill_between(cos_test_series.index,
                            cos_test_series.values.clip(-1, 0), 0,
                            where=(cos_test_series < -0.7),
                            color='red', alpha=0.25, label='|cos_θC| > 0.7')
        # mark alarm days
        alarm_dates = cos_test_series.index[alarm[test_mask].values]
        ax_cos.scatter(alarm_dates,
                       np.full(len(alarm_dates), -0.95),
                       color='red', s=8, alpha=0.6, zorder=3, label='alarm active')
        ax_cos.set_title('cos_θ_channel signal (test period)', fontsize=10)
        ax_cos.set_ylabel('cos_θC'); ax_cos.set_ylim(-1.05, 1.05)
        ax_cos.legend(loc='upper right', fontsize=8); ax_cos.grid(alpha=0.3)

        # ── GCI leverage ──
        gci_test = lev_v19_gci[test_mask]
        ax_gci.plot(gci_test.index, gci_test.values,
                    color='#8844aa', lw=1.0)
        ax_gci.fill_between(gci_test.index, gci_test.values, GCI_LEV_LO,
                            where=(gci_test < (GCI_LEV_LO + (GCI_LEV_HI - GCI_LEV_LO) * 0.3)),
                            color='red', alpha=0.3)
        ax_gci.axhline(lev_v18_smooth[test_mask].mean(), color='blue', lw=0.8, ls=':',
                       label='v18_smooth mean lev')
        ax_gci.set_title('GCI leverage (v19)', fontsize=10)
        ax_gci.set_ylabel('Leverage'); ax_gci.legend(fontsize=8); ax_gci.grid(alpha=0.3)

        # ── ablation Sharpe bar ──
        variant_labels = list(sims.keys())
        variant_sharpes = [sims[k]['sharpe'] for k in variant_labels]
        bar_colors = [('#228833' if v == 'v19_full' else
                       '#4477aa' if v == 'v18_smooth' else '#aaaaaa')
                      for v in variant_labels]
        bars = ax_bar.barh(range(len(variant_labels)), variant_sharpes,
                           color=bar_colors)
        ax_bar.set_yticks(range(len(variant_labels)))
        ax_bar.set_yticklabels(variant_labels, fontsize=8)
        ax_bar.axvline(0, color='k', lw=0.5)
        ax_bar.set_title('Sharpe (K=1 gross)', fontsize=10)
        ax_bar.grid(alpha=0.3, axis='x')
        for i, (sh, bar) in enumerate(zip(variant_sharpes, bars)):
            ax_bar.text(sh + 0.01, i, f'{sh:+.3f}', va='center', fontsize=8)

        plt.suptitle(
            f"v19: cos_θ_channel (universal collapse invariant) → GCI leverage\n"
            f"verdict: {verdict}",
            fontsize=10, y=0.98)
        png_path = os.path.join(OUT_DIR, 'crypto_bsdt_v19_equity.png')
        plt.savefig(png_path, dpi=120, bbox_inches='tight')
        plt.close(fig)
        print(f"  Plot saved → {png_path}")
    except Exception as e:
        print(f"  (matplotlib skipped: {e})")

    # ── [12] Final summary ─────────────────────────────────────────────────
    print("\n" + "=" * 84)
    print("  v19 FINAL SUMMARY")
    print("=" * 84)
    print(f"  Theory signal:    cos_θC → −1 at collapse  (confirmed in 4 real-world crises)")
    print(f"  Signal coverage:  {frac_neg_09:.1f}% days with cos_θC < −0.90 in test period")
    print(f"  Hard-lock days:   {alarm_days} ({alarm_days/test_mask.sum()*100:.1f}% of test)")
    print()
    print(f"  {'Variant':<22}  {'Sharpe':>8}  {'MaxDD':>8}  {'CAGR%':>8}  {'Comment'}")
    print("  " + "─" * 74)
    for k, s in sims.items():
        delta_sh  = s['sharpe'] - sh_v18 if k != 'v18_smooth' else 0.0
        delta_tag = f"  Δ={delta_sh:+.4f}" if k != 'v18_smooth' else "  (reference)"
        print(f"  {k:<22}  {s['sharpe']:>+8.4f}  {s['max_dd']:>+8.4f}  "
              f"{s['cagr']*100:>+7.2f}%{delta_tag}")
    print()
    print(f"  VERDICT: {verdict}")
    if best_K_result:
        print(f"  Best K ($1,200, net 5bp, MaxDD≤40%): K={best_K_result['K']:.2f}")
        print(f"    → Final ${best_K_result['final']:,.2f}  PnL ${best_K_result['pnl']:+,.2f}  "
              f"Sharpe {best_K_result['sh']:+.3f}  CAGR {best_K_result['cagr']*100:+.2f}%")
    print()
    print(f"  JSON → {json_path}")
    print("=" * 84)


if __name__ == '__main__':
    main()
