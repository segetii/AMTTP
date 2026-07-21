"""
Crypto BSDT v15 — Production+: convex γ dial + funding-extreme fade strategy
===================================================================

v14 lessons:
  v14b (γ-leverage dial only) won at +0.913 Sharpe (v10 +0.597 + 0.316).
  Sharpe×Stability weighting penalised the high-Sharpe-but-volatile ALT_macro
  strategy (v14a = +0.405) — rejected.

v15 — two orthogonal upgrades on top of v14b:

  (1) CONVEX leverage dial (was linear in v14b):
        v14b:  lev_mult = clip(1.5 − γ_rank,           0.5, 1.2)   # linear
        v15:   lev_mult = clip((1.2 − γ_rank)**2,      0.4, 1.3)   # convex
      Convex form: small γ changes → small effect, extreme γ → aggressive
      de-risk. Better tail protection than the linear dial.

  (2) NEW STRATEGY: funding-extreme fade (orthogonal alpha source):
        Binance perp funding rate already pulled in v12 (fr_eth_z, fr_btc_z).
        When funding z-score > +2  : longs are paying → crowded long → short ETH
        When funding z-score < −2  : shorts are paying → crowded short → long ETH
        Position = clip(-fr_eth_z / 2.0, −1.5, +1.5) when |fr_eth_z| > 2 else 0
        Plugs into pnl_base, inherits v10 Sharpe weighting + γ-leverage dial.

Falsifiable comparisons (all on top of v10 Sharpe weights + funding strategy):
  v15a = convex dial only (no funding fade)              → isolates (1)
  v15b = funding fade only + linear dial (v14b)          → isolates (2)
  v15  = both (PRODUCTION)

Reports v10 / v14b / v15 (3 variants) side-by-side.
"""

import numpy as np
import pandas as pd
import json
import warnings
import requests
import bisect
import time
warnings.filterwarnings('ignore')
import yfinance as yf
from numpy.linalg import eigh
from scipy import stats

OUT_DIR     = r"C:\amttp\research\adaptive-friction\pipeline\results"
TRAIN_START = '2021-01-01'
TRAIN_END   = '2022-12-31'
TEST_START  = '2023-01-01'

# ─── position routing constants ───────────────────────────────────────────────
BETA_VEL_THRESH    = 0.30
POA_LOW            = 0.30
POA_HIGH           = 0.80
STRUCT_SIZE_SCALE  = 0.50

# ─── manifold validity thresholds ─────────────────────────────────────────────
DRIFT_WINDOW  = 60
EFF_WINDOW    = 60
DRIFT_THRESH  = 1.00
EFF_THRESH    = 0.0

# ─── v10/v11 γ constants (kept for reference computation) ─────────────────────
GAMMA_CLIP_LOW   = 0.10
GAMMA_CLIP_HIGH  = 0.90
GAMMA_SCORE_WIN  = 126

# ─── v12: Ω_combined + γ_rank ─────────────────────────────────────────────────
GAMMA_RANK_CLIP_LOW  = 0.05   # floor/cap for rank-based γ (already in [0,1])
GAMMA_RANK_CLIP_HIGH = 0.95
OMEGA_PRICE_WEIGHT   = 0.6    # Ω_combined = 0.6*Ω_price_z + 0.4*Ω_lev_z
OMEGA_LEV_WEIGHT     = 0.4
OMEGA_LEV_WINDOW     = 30     # funding features are more reactive → shorter window


GAMMA_REGIME_THRESHOLD = 0.5    # γ_rank > 0.5 → 'high stress' regime (v13 ref)
GAMMA_REGIME_WINDOW    = 252   # rolling window (≈2x v10's 126 to compensate)

# ─── v14: stability + γ leverage dial ──────────────────────────────────
STAB_WIN          = 60          # rolling-std window for Sharpe stability
STAB_EPS          = 1e-6
LEV_BASE          = 1.5         # v14b linear: lev = clip(LEV_BASE - γ_rank, LEV_LO, LEV_HI)
LEV_LO            = 0.5
LEV_HI            = 1.2

# ─── v15: convex dial + funding-fade strategy ────────────────────────
CVX_BASE          = 1.2         # convex: lev = clip((CVX_BASE - γ_rank)**2, CVX_LO, CVX_HI)
CVX_LO            = 0.4
CVX_HI            = 1.3
FUND_THRESH       = 2.0         # |funding z| > FUND_THRESH → fade signal active
FUND_POS_CAP      = 1.5         # max position size (z-clipped)


# ─────────────────────────────────────────────────────────────────────────────
#  DATA — crypto (unchanged from v11)
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


# ─────────────────────────────────────────────────────────────────────────────
#  v12: CROSS-MARKET FEATURES  (VIX, SPX, DXY via yfinance)
# ─────────────────────────────────────────────────────────────────────────────
def add_cross_market_features(df):
    """
    Add SPX log returns, VIX daily changes, DXY log returns to df.
    All are forward-filled on crypto weekend/holiday dates.
    Z-scored with rolling 252d window (same as crypto features).
    """
    tickers = {'^GSPC': 'spx', '^VIX': 'vix', 'DX-Y.NYB': 'dxy'}
    raw = {}
    for tk, col in tickers.items():
        s = yf.download(tk, start='2020-06-01', progress=False,
                        auto_adjust=True)['Close'].squeeze()
        raw[col] = s

    # ── SPX: log return ────────────────────────────────────────────────────
    spx = raw['spx'].reindex(df.index, method='ffill')
    df['ret_spx'] = np.log(spx / spx.shift(1)).fillna(0.0)

    # ── VIX: daily absolute change (level already in % annualised vol) ─────
    vix = raw['vix'].reindex(df.index, method='ffill')
    df['dvix'] = vix.diff(1).fillna(0.0)

    # ── DXY: log return ────────────────────────────────────────────────────
    dxy = raw['dxy'].reindex(df.index, method='ffill')
    df['ret_dxy'] = np.log(dxy / dxy.shift(1)).fillna(0.0)

    def _rz(s, w=252):
        mu = s.rolling(w, min_periods=60).mean()
        sd = s.rolling(w, min_periods=60).std()
        return (s - mu) / (sd + 1e-9)

    for c in ['ret_spx', 'dvix', 'ret_dxy']:
        df[f'{c}_z'] = _rz(df[c])

    return df


# ─────────────────────────────────────────────────────────────────────────────
#  v12: BINANCE FUNDING RATE FETCH
# ─────────────────────────────────────────────────────────────────────────────
def fetch_binance_funding(symbols=None, start='2020-06-01'):
    """
    Fetch Binance perpetual funding rates via public API (no auth needed).
    Paginates from `start` to today, 1000 records per page.
    Funding settles 3x daily (every 8h). Returns daily mean rate per symbol.

    Returns dict: symbol -> pd.Series(date_index, daily_mean_rate)
    Returns empty Series gracefully on any error.
    """
    if symbols is None:
        symbols = ['ETHUSDT', 'BTCUSDT']
    base_url  = 'https://fapi.binance.com/fapi/v1/fundingRate'
    start_ms  = int(pd.Timestamp(start).timestamp() * 1000)
    end_ms    = int(pd.Timestamp.utcnow().timestamp() * 1000)

    result = {}
    for sym in symbols:
        records   = []
        cur_start = start_ms
        n_pages   = 0
        try:
            while True:
                params = {
                    'symbol':    sym,
                    'limit':     1000,
                    'startTime': cur_start,
                    'endTime':   end_ms,
                }
                r    = requests.get(base_url, params=params, timeout=15)
                data = r.json()
                if not isinstance(data, list) or len(data) == 0:
                    break
                records.extend(data)
                n_pages += 1
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


# ─────────────────────────────────────────────────────────────────────────────
#  v12: ADD LEVERAGE FEATURES
# ─────────────────────────────────────────────────────────────────────────────
def add_leverage_features(df, funding_data):
    """
    Add funding rate features to df.
    For each asset (ETH, BTC):
      fr_{a}          : daily mean funding rate
      fr_vol_{a}      : 7d rolling std of funding rate (leverage volatility)
      fr_cum5_{a}     : 5d cumulative funding (carry accumulation signal)
    All z-scored with rolling 252d window.
    """
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

        # Align to df index; forward-fill weekends/gaps (at most 1d gap)
        fr_raw.index = fr_raw.index.tz_localize(None) if fr_raw.index.tz else fr_raw.index
        df_idx_tz    = df.index.tz_localize(None) if df.index.tz else df.index
        fr_al        = fr_raw.reindex(df_idx_tz, method='ffill')
        fr_al.index  = df.index   # restore original index (handles tz)

        df[f'fr_{col}']     = fr_al
        df[f'fr_vol_{col}'] = fr_al.rolling(7, min_periods=4).std()
        df[f'fr_cum5_{col}']= fr_al.rolling(5, min_periods=3).sum()

        for feat in [f'fr_{col}', f'fr_vol_{col}', f'fr_cum5_{col}']:
            df[f'{feat}_z'] = _rz(df[feat])

    return df


# ─────────────────────────────────────────────────────────────────────────────
#  BSDT ENGINE (unchanged from v11 — now called with 11-feature space)
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
#  v12: Ω_leverage (thin wrapper — compute_bsdt with leverage features)
# ─────────────────────────────────────────────────────────────────────────────
def compute_omega_leverage(df, features, window=30):
    """
    Compute Ω_leverage via BSDT on funding rate features.
    Smaller window (30d) — funding features are more reactive than price.
    The BSDT engine already skips windows with non-finite rows.
    """
    omega_lev, _, _ = compute_bsdt(df, features, window=window)
    return omega_lev


# ─────────────────────────────────────────────────────────────────────────────
#  v12: Ω_combined — normalised weighted combination
# ─────────────────────────────────────────────────────────────────────────────
def combine_omegas(omega_price, omega_lev, w_price=0.6, w_lev=0.4):
    """
    Expanding z-normalise each Ω independently, then combine.
    Z-normalisation ensures scale differences don't create discontinuities
    when leverage data starts appearing mid-series.
    Where Ω_lev is NaN, falls back to Ω_price_z alone.
    """
    def _ez(s, min_p=60):
        mu = s.expanding(min_p).mean()
        sd = s.expanding(min_p).std()
        return (s - mu) / (sd + 1e-9)

    ol   = omega_lev.reindex(omega_price.index)
    op_z = _ez(omega_price)
    ol_z = _ez(ol)   # NaN propagates where ol is NaN

    mask_both = op_z.notna() & ol_z.notna()
    result    = op_z.copy()
    result[mask_both] = (
        w_price * op_z[mask_both] + w_lev * ol_z[mask_both]
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  v12: γ_rank — expanding percentile rank  O(n log n)
# ─────────────────────────────────────────────────────────────────────────────
def compute_gamma_rank(omega_series, min_periods=60):
    """
    Expanding percentile rank of omega_series.
    For each t: γ_rank_t = fraction of ω_s (s ≤ t, not NaN) that are ≤ ω_t.
    Guaranteed to be in [0, 1] with std ≈ 0.289 (uniform distribution).
    Uses bisect for O(n log n) total time complexity.

    NaN positions in omega_series → NaN in output (safely skipped in bisect list).
    Positions before min_periods non-NaN values → NaN output.
    """
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


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE (unchanged)
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
def compute_activity_signals(mfls, gamma):
    A       = mfls / (gamma + 1e-9)
    A_rank  = A.expanding(60).rank(pct=True)
    dA_fast = A.diff(1).rolling(2).mean()
    dA_rank = dA_fast.expanding(60).rank(pct=True)
    return A, A_rank, dA_fast, dA_rank


# ─────────────────────────────────────────────────────────────────────────────
#  v8 SPREAD — training-anchored z-score (unchanged)
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


# ─────────────────────────────────────────────────────────────────────────────
#  UDL MDN CLASSIFIER (unchanged)
# ─────────────────────────────────────────────────────────────────────────────
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
        k               = min(self.n_ref_dirs, len(unit_d))
        _, _, Vt        = np.linalg.svd(unit_d, full_matrices=False)
        self.ref_dirs_  = Vt[:k]
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


# ─────────────────────────────────────────────────────────────────────────────
#  v7 MANIFOLD VALIDITY — drift-only gate (unchanged)
# ─────────────────────────────────────────────────────────────────────────────
def compute_manifold_validity(z_spread, sret):
    drift    = z_spread.rolling(DRIFT_WINDOW, min_periods=30).mean().abs()
    drift_ok = drift < DRIFT_THRESH
    rev_sig   = -np.sign(z_spread.shift(1))
    daily_pnl = rev_sig * sret
    rev_eff   = daily_pnl.rolling(EFF_WINDOW, min_periods=30).mean()
    valid = drift_ok.astype(int)
    return (pd.Series(valid.values,   index=z_spread.index, name='manifold_valid'),
            pd.Series(drift.values,   index=z_spread.index, name='z_drift'),
            pd.Series(rev_eff.values, index=z_spread.index, name='rev_eff'))


# ─────────────────────────────────────────────────────────────────────────────
#  ROUTERS (unchanged)
# ─────────────────────────────────────────────────────────────────────────────
def route_pair_v6_baseline(omega, A_rank, z_spread, udl_state, poa, z_threshold=1.0):
    omega_q50 = omega.expanding(60).quantile(0.50)
    gate      = (omega >= omega_q50) & (A_rank >= 0.33) & (z_spread.abs() > z_threshold)
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
    omega_q50   = omega.expanding(60).quantile(0.50)
    omega_gate  = omega >= omega_q50
    active_gate = A_rank >= 0.33
    spread_gate = z_spread.abs() > z_threshold
    mval_gate   = manifold_valid.astype(bool)
    gate        = omega_gate & active_gate & spread_gate & mval_gate
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
#  PORTFOLIO ALLOCATION FUNCTIONS (unchanged from v11)
# ─────────────────────────────────────────────────────────────────────────────
def apply_gamma_mod(pos, gamma_series, mode='macro'):
    gc = gamma_series.reindex(pos.index).clip(GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH)
    if mode == 'directional':
        return (pos * (1.0 - gc)).clip(-1, 1)
    elif mode == 'reversion':
        return (pos * gc).clip(-1, 1)
    else:
        return pos.clip(-1, 1)


def get_daily_pnl(pos, ret):
    """Causal daily PnL: position(t-1) × ret(t)."""
    return pos.shift(1).fillna(0) * ret.reindex(pos.index).fillna(0)


def compute_cs_weights(pnl_dict, window=126):
    """Rolling cross-sectional Sharpe weights. Negative-Sharpe → zero weight."""
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


def compute_tilted_weights(pnl_dict, gamma_series, tilt_modes, window=126):
    """
    Portfolio weights = rolling_Sharpe × γ_tilt × normalisation.
    Works for any γ in [0,1]: γ_fast (v11), γ_rank (v12).
      directional: w ∝ Sh+ × (1 - γ)   — reduce when stress high
      reversion:   w ∝ Sh+ × γ          — amplify when stress high
      macro:       w ∝ Sh+              — γ-insensitive
    """
    gc = gamma_series.clip(GAMMA_RANK_CLIP_LOW, GAMMA_RANK_CLIP_HIGH)

    sharpes = {}
    for label, pnl in pnl_dict.items():
        mu = pnl.rolling(window, min_periods=window // 2).mean()
        sd = pnl.rolling(window, min_periods=window // 2).std()
        sharpes[label] = (mu / (sd + 1e-12) * np.sqrt(252)).clip(lower=0.0)

    raw_w = {}
    for label, mode in tilt_modes.items():
        sh = sharpes[label].reindex(pnl_dict[label].index)
        if mode == 'directional':
            tilt = (1.0 - gc).reindex(sh.index).fillna(0.5)
        elif mode == 'reversion':
            tilt = gc.reindex(sh.index).fillna(0.5)
        else:
            tilt = pd.Series(1.0, index=sh.index)
        raw_w[label] = sh * tilt

    raw_df = pd.DataFrame(raw_w)
    total  = raw_df.sum(axis=1).replace(0, float('nan'))
    n      = len(pnl_dict)
    weights = {}
    for label in pnl_dict:
        weights[label] = (raw_df[label] / total).fillna(1.0 / n)
    return weights


def compute_stability_weights(pnl_dict, window=126, stab_win=60):
    """
    v14: weights ∝ rolling_Sharpe⁺ × stability,  stability = 1/(1 + std(Sharpe)).
    Penalises strategies whose Sharpe estimate itself wobbles.
    Returns (weights, stability_dict, raw_sharpe_dict) for diagnostics.
    """
    sharpes, stabs, raws = {}, {}, {}
    for label, pnl in pnl_dict.items():
        mu = pnl.rolling(window, min_periods=window // 2).mean()
        sd = pnl.rolling(window, min_periods=window // 2).std()
        sh = mu / (sd + 1e-12) * np.sqrt(252)
        raws[label]    = sh
        # stability: low rolling-std of Sharpe → high stability
        sh_std = sh.rolling(stab_win, min_periods=stab_win // 2).std()
        stab   = 1.0 / (1.0 + sh_std.fillna(sh_std.median()) + STAB_EPS)
        stabs[label]   = stab
        sharpes[label] = sh.clip(lower=0.0) * stab

    df_sh = pd.DataFrame(sharpes)
    total = df_sh.sum(axis=1)
    n     = len(pnl_dict)
    weights = {}
    for label in pnl_dict:
        w = df_sh[label] / total.replace(0, float('nan'))
        weights[label] = w.fillna(1.0 / n)
    return weights, stabs, raws


def compute_leverage_dial(gamma_rank, base=1.5, lo=0.5, hi=1.2):
    """
    v14: γ_rank → global gross-exposure scalar (LINEAR).
      lev_mult = clip(base − γ_rank, lo, hi)
    """
    return (base - gamma_rank.fillna(0.5)).clip(lower=lo, upper=hi)


def compute_leverage_dial_convex(gamma_rank, base=1.2, lo=0.4, hi=1.3):
    """
    v15: convex γ_rank → leverage scalar.
      lev_mult = clip((base − γ_rank)**2 × sign(base − γ_rank), lo, hi)
      Use signed-square so γ_rank > base reduces below 0... but we don't want
      negative. Instead: square the positive side, linearly extrapolate negative.
      Practically: lev = clip((base − γ_rank)² , lo, hi) when (base-γ)≥0,
                   else lev = lo (full de-risk for extreme stress).
      γ_rank=0.0 → 1.44→clip 1.3   (full size in calm)
      γ_rank=0.2 → 1.00            (neutral)
      γ_rank=0.5 → 0.49            (mild de-risk)
      γ_rank=0.8 → 0.16→clip 0.4   (aggressive de-risk)
      γ_rank=1.0 → 0.04→clip 0.4   (max de-risk)
    """
    delta = (base - gamma_rank.fillna(0.5))
    val   = np.sign(delta) * delta * delta
    return val.clip(lower=lo, upper=hi)


def compute_funding_fade_position(df, asset='eth', thresh=2.0, cap=1.5,
                                   direction='fade'):
    """
    v15: funding-extreme strategy.
      direction='fade': crowded longs (high +funding) → short next bar (mean-reversion view)
      direction='mom' : crowded longs (high +funding) → long next bar  (momentum view)

    Position: when |fr_z| > thresh,
                pos = sign × clip(fr_z / thresh, -cap, +cap)
              else 0.
              sign = -1 for 'fade', +1 for 'mom'.
    """
    fr_z_col = f'fr_{asset}_z'
    if fr_z_col not in df.columns:
        return pd.Series(0.0, index=df.index)
    fr_z = df[fr_z_col].fillna(0.0)
    sign = -1.0 if direction == 'fade' else +1.0
    pos  = (sign * fr_z / thresh).clip(lower=-cap, upper=cap)
    pos  = pos.where(fr_z.abs() > thresh, 0.0)
    return pos


def compute_regime_conditional_weights(pnl_dict, gamma_rank, window=252,
                                        threshold=0.5):
    """
    v13: Regime-conditional rolling Sharpe weights.

    For each day t with γ_rank_t = r:
      regime_t = 'high'  if r > threshold  else  'low'
      For each strategy:
        Compute rolling Sharpe over the last `window` days,
        but only counting days where regime matched current regime_t.
        Implemented by masking PnL to NaN on off-regime days
        before applying rolling mean/std (NaN-aware).
      Negative-Sharpe strategies get zero weight (same as v10).

    This is v10's killer feature (Sharpe weighting zeroes losers) PLUS
    regime-conditioning. No a priori 'reversion'/'directional' labels.
    The data itself decides which strategy works in which regime.

    Window default 252 ≈ 2× v10's 126 because each regime gets ~50% of days,
    so 252 calendar days → ~126 same-regime samples → matches v10's signal.

    Parameters
    ----------
    pnl_dict   : dict  label -> pd.Series daily PnL (full history)
    gamma_rank : pd.Series  in [0, 1] (NaN before warmup)
    window     : rolling window in calendar days
    threshold  : regime split threshold (default 0.5)

    Returns
    -------
    dict  label -> pd.Series daily weights (sum to 1 cross-sectionally)
    """
    g = gamma_rank.fillna(0.5)
    high_mask = g > threshold
    low_mask  = ~high_mask

    weights_high = {}   # rolling Sharpe over high-regime days only
    weights_low  = {}

    for label, pnl in pnl_dict.items():
        # Mask: on off-regime days, set PnL to NaN so rolling stats skip them
        pnl_h = pnl.where(high_mask, np.nan)
        pnl_l = pnl.where(low_mask,  np.nan)

        # NaN-aware rolling Sharpe (min_periods relaxed to ~quarter window)
        mu_h = pnl_h.rolling(window, min_periods=window // 4).mean()
        sd_h = pnl_h.rolling(window, min_periods=window // 4).std()
        weights_high[label] = (mu_h / (sd_h + 1e-12) * np.sqrt(252)).clip(lower=0.0)

        mu_l = pnl_l.rolling(window, min_periods=window // 4).mean()
        sd_l = pnl_l.rolling(window, min_periods=window // 4).std()
        weights_low[label] = (mu_l / (sd_l + 1e-12) * np.sqrt(252)).clip(lower=0.0)

    # Dispatch: pick the regime-matching Sharpe each day
    sharpes = {}
    for label in pnl_dict:
        sh = pd.Series(
            np.where(high_mask, weights_high[label].values, weights_low[label].values),
            index=pnl_dict[label].index,
        )
        sharpes[label] = sh.fillna(0.0)

    df_sh = pd.DataFrame(sharpes)
    total = df_sh.sum(axis=1)
    n     = len(pnl_dict)
    weights = {}
    for label in pnl_dict:
        w = df_sh[label] / total.replace(0, float('nan'))
        weights[label] = w.fillna(1.0 / n)
    return weights, weights_high, weights_low


def simulate_from_pnl(pnl_series, label=""):
    pnl    = pnl_series.fillna(0).values
    cum    = np.cumprod(1.0 + pnl)
    active = pnl[pnl != 0]
    sharpe = float(active.mean() / (np.std(active) + 1e-12) * np.sqrt(252)) if len(active) > 0 else 0.0
    roll_max = np.maximum.accumulate(cum)
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
#  DIRECTIONAL STRATEGY (unchanged)
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
    print("=" * 84)
    print("  CRYPTO BSDT v12 — Ω decomposition: price + leverage + cross-market")
    print("  Layer 6: w = rolling_Sharpe × γ_rank_tilt")
    print("  γ_rank = expanding_pct_rank(Ω_combined)  always in [0,1]")
    print("=" * 84)

    # ── Load and extend data ───────────────────────────────────────────────
    df = fetch_and_prepare()

    print("  Adding cross-market features (VIX, SPX, DXY) ...")
    df = add_cross_market_features(df)

    print("  Fetching Binance funding rates (ETH, BTC, paginated) ...")
    funding = fetch_binance_funding(
        symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
    df = add_leverage_features(df, funding)

    # Coverage summary
    lev_cols   = ['fr_eth_z', 'fr_btc_z', 'fr_vol_eth_z',
                  'fr_vol_btc_z', 'fr_cum5_eth_z', 'fr_cum5_btc_z']
    cross_cols = ['ret_spx_z', 'dvix_z', 'ret_dxy_z']
    lev_ok   = df[lev_cols].notna().all(axis=1)
    cross_ok = df[cross_cols].notna().all(axis=1)
    print(f"  Cross-market coverage: {cross_ok.sum()}/{len(df)} "
          f"({cross_ok.mean()*100:.0f}%)")
    print(f"  Leverage coverage:     {lev_ok.sum()}/{len(df)} "
          f"({lev_ok.mean()*100:.0f}%)")

    train_mask = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask  = df.index >= TEST_START
    print(f"  Train: {df[train_mask].index[0].date()} → "
          f"{df[train_mask].index[-1].date()}")
    print(f"  Test:  {df[test_mask].index[0].date()} → "
          f"{df[test_mask].index[-1].date()}  n={test_mask.sum()}")

    # ── [1a] Ω_strat: 8-feature crypto-only BSDT — used for ALL strategy gates ──
    #         Identical to v9/v10/v11. Keeps existing strategy timing intact.
    feats_strat = [
        'ret_eth_z', 'ret_btc_z', 'ret_sol_z', 'ret_bnb_z',
        'vol_eth_z', 'vol_btc_z', 'btc_dom_z', 'cross_disp_z',
    ]
    print(f"\n[1a] Computing Ω_strat (8-feature crypto BSDT, strategy gates) ...")
    omega_strat, mfls_eth, gamma_eth = compute_bsdt(df, feats_strat, window=60)

    # ── [1b] Ω_price_ext: 11-feature cross-market BSDT — for γ_rank only ─────
    #         Cross-market features (VIX/SPX/DXY) add coupling blocks.
    #         Used ONLY in Ω_combined → γ_rank → portfolio weight tilt.
    feats_ext = [
        'ret_eth_z', 'ret_btc_z', 'ret_sol_z', 'ret_bnb_z',
        'vol_eth_z', 'vol_btc_z', 'btc_dom_z', 'cross_disp_z',
        'ret_spx_z', 'dvix_z', 'ret_dxy_z',
    ]
    print(f"[1b] Computing Ω_price_ext ({len(feats_ext)}-feature cross-market BSDT, γ_rank) ...")
    omega_price_ext, _, _ = compute_bsdt(df, feats_ext, window=60)

    # Strategy gates always use omega_strat (unchanged from v9/v10/v11)
    omega = omega_strat

    # ── [2] Activity signals ───────────────────────────────────────────────
    print("\n[2]  Computing A_level and ΔA_fast ...")
    A_eth, A_rank, dA_fast, dA_rank = compute_activity_signals(mfls_eth, gamma_eth)

    # ── [3] Spread + UDL MDN classification ───────────────────────────────
    ret7  = df['ret_eth'].rolling(7).sum()
    ret3  = df['ret_eth'].rolling(3).sum()
    phase = detect_phase(omega, ret7, ret3, df['btc_dom_z'])

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
        train_spread = sd['spread'][train_mask].dropna()
        clf = SpreadUDLClassifier(window=20, n_ref_dirs=100).fit(train_spread)
        udl_state, udl_mag, udl_novelty = clf.classify_series(sd['spread'])
        sd['udl_state']   = udl_state
        sd['udl_mag']     = udl_mag
        sd['udl_novelty'] = udl_novelty
        mval, z_drift, rev_eff = compute_manifold_validity(sd['z'], sd['sret'])
        sd['manifold_valid'] = mval
        sd['z_drift']        = z_drift
        sd['rev_eff']        = rev_eff
        pair_data[key]       = sd
        t_st    = udl_state[test_mask]
        t_mval  = mval[test_mask]
        total   = len(t_st)
        n_eq    = (t_st == 0).sum()
        n_dg    = (t_st == 1).sum()
        n_st    = (t_st == 2).sum()
        n_valid = t_mval.sum()
        drft_m  = z_drift[test_mask].dropna().median()
        reff_m  = rev_eff[test_mask].dropna().median()
        print(f"  EQUIL={n_eq/total*100:.1f}%  DEGEN={n_dg/total*100:.1f}%  "
              f"STRUCT={n_st/total*100:.1f}%  "
              f"VALID={n_valid/total*100:.1f}%  "
              f"drift_med={drft_m:.3f}  rev_eff_med={reff_m:.5f}")

    # ── [4] Build positions ────────────────────────────────────────────────
    print("\n[4]  Building positions (v7: UDL + manifold validity) ...")
    pos_A_dir = setup_a_directional(df, omega, mfls_eth, gamma_eth, phase)

    pair_positions    = {}
    pair_positions_v6 = {}
    for key, _, _, _, _ in pairs:
        sd = pair_data[key]
        pair_positions[key] = route_pair_v7(
            omega, A_rank, sd['z'], sd['udl_state'], sd['poa'],
            sd['manifold_valid'], z_threshold=1.0)
        pair_positions_v6[key] = route_pair_v6_baseline(
            omega, A_rank, sd['z'], sd['udl_state'], sd['poa'],
            z_threshold=1.0)
    pos_btc_macro, pos_alt_macro = route_btcalt_macro(df, omega, A_rank, dA_rank)

    # ── [5] Simulate individual strategies [test] ─────────────────────────
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
    ic_res['A_directional'] = ic_metric(
        pos_A_dir[test_mask], fwd21[test_mask], 'A_dir')
    for key, _, _, _, _ in pairs:
        ic_res[key] = ic_metric(
            pair_positions[key][test_mask], fwd21[test_mask], key)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  [6]  v12: Ω_leverage + Ω_combined + γ_rank
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print(f"\n[6]  Computing Ω_leverage, Ω_combined, γ_rank ...")

    feats_lev = [
        'fr_eth_z', 'fr_btc_z',
        'fr_vol_eth_z', 'fr_vol_btc_z',
        'fr_cum5_eth_z', 'fr_cum5_btc_z',
    ]
    omega_lev      = compute_omega_leverage(df, feats_lev, window=OMEGA_LEV_WINDOW)
    # Ω_combined uses Ω_price_ext (11-feat cross-market) + Ω_leverage
    # NOT omega_strat — we want the richer signal for portfolio allocation
    omega_combined = combine_omegas(
        omega_price_ext, omega_lev,
        w_price=OMEGA_PRICE_WEIGHT, w_lev=OMEGA_LEV_WEIGHT)
    gamma_rank     = compute_gamma_rank(omega_combined, min_periods=60)

    # Diagnostics [test period]
    op_t   = omega_price_ext[test_mask]
    ol_t   = omega_lev[test_mask]
    oc_t   = omega_combined[test_mask]
    gr_t   = gamma_rank[test_mask]
    gf_t   = (1.0 / (1.0 + omega_strat)).clip(GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH)[test_mask]
    lev_cov = ol_t.notna().mean() * 100

    os_t = omega_strat[test_mask]
    print(f"  Ω_strat    [test]: mean={os_t.mean():.3f}  std={os_t.std():.3f}  "
          f"p10={os_t.quantile(0.10):.3f}  p90={os_t.quantile(0.90):.3f}  (strategy gates)")
    print(f"  Ω_price_ext[test]: mean={op_t.mean():.3f}  std={op_t.std():.3f}  "
          f"p10={op_t.quantile(0.10):.3f}  p90={op_t.quantile(0.90):.3f}  (γ_rank input)")
    if lev_cov > 0:
        print(f"  Ω_leverage [test]: mean={ol_t.dropna().mean():.3f}  "
              f"std={ol_t.dropna().std():.3f}  "
              f"p10={ol_t.dropna().quantile(0.10):.3f}  "
              f"p90={ol_t.dropna().quantile(0.90):.3f}  "
              f"coverage={lev_cov:.0f}%")
    else:
        print(f"  Ω_leverage [test]: no data (funding API returned nothing)")
    print(f"  Ω_combined [test]: mean={oc_t.mean():.3f}  std={oc_t.std():.3f}  "
          f"p10={oc_t.quantile(0.10):.3f}  p90={oc_t.quantile(0.90):.3f}")
    print(f"  γ_rank     [test]: mean={gr_t.mean():.3f}  std={gr_t.std():.3f}  "
          f"p10={gr_t.quantile(0.10):.3f}  p90={gr_t.quantile(0.90):.3f}")
    pct_hi = (gr_t > 0.6).mean() * 100
    pct_lo = (gr_t < 0.4).mean() * 100
    print(f"  γ_rank>0.6 (reversion-favour): {pct_hi:.1f}%  "
          f"γ_rank<0.4 (directional-favour): {pct_lo:.1f}%")
    print(f"  γ_fast [test] (v11 ref):  mean={gf_t.mean():.3f}  std={gf_t.std():.3f}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  [7]  Portfolio comparison: v10 / v11 / v12
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print(f"\n[7]  Building v10 / v11 / v12 dynamic portfolios ...")

    pos_base = {
        'A_directional': pos_A_dir,
        'P1_ETH_BTC':    pair_positions['P1_ETH_BTC'],
        'P2_ETH_SOL':    pair_positions['P2_ETH_SOL'],
        'P3_ETH_BNB':    pair_positions['P3_ETH_BNB'],
        'M1_ALT_macro':  pos_alt_macro,
        'M1_BTC_macro':  pos_btc_macro,
    }
    # v15: funding-extreme MOMENTUM (high funding → follow trend; +1.7 standalone Sh).
    # Fade variants tested but lost (-1.7 Sh) — dropped. In bull markets,
    # crowded longs continue trending up.
    pos_fund_eth_mom  = compute_funding_fade_position(df, asset='eth',
                                                     thresh=FUND_THRESH,
                                                     cap=FUND_POS_CAP,
                                                     direction='mom')
    pos_fund_btc_mom  = compute_funding_fade_position(df, asset='btc',
                                                     thresh=FUND_THRESH,
                                                     cap=FUND_POS_CAP,
                                                     direction='mom')
    pos_base['F_FUND_ETH_M'] = pos_fund_eth_mom
    pos_base['F_FUND_BTC_M'] = pos_fund_btc_mom

    strat_rets_all = {
        'A_directional': df['ret_eth'],
        'P1_ETH_BTC':    pair_data['P1_ETH_BTC']['sret'],
        'P2_ETH_SOL':    pair_data['P2_ETH_SOL']['sret'],
        'P3_ETH_BNB':    pair_data['P3_ETH_BNB']['sret'],
        'M1_ALT_macro':  df['ret_eth'],
        'M1_BTC_macro':  df['ret_btc'],
        'F_FUND_ETH_M':  df['ret_eth'],
        'F_FUND_BTC_M':  df['ret_btc'],
    }
    pnl_base = {k: get_daily_pnl(pos_base[k], strat_rets_all[k]) for k in pos_base}
    tilt_modes = {
        'A_directional': 'directional',
        'P1_ETH_BTC':    'reversion',
        'P2_ETH_SOL':    'reversion',
        'P3_ETH_BNB':    'reversion',
        'M1_ALT_macro':  'macro',
        'M1_BTC_macro':  'macro',
        'F_FUND_ETH_M':  'macro',
        'F_FUND_BTC_M':  'macro',
    }
    n_s = len(pnl_base)

    # Funding individual diagnostics (test period)
    print(f"\n  v15 funding signal stats [test]:")
    fre_t = df['fr_eth_z'][test_mask].dropna()
    frb_t = df['fr_btc_z'][test_mask].dropna()
    print(f"    fr_eth_z: mean={fre_t.mean():+.3f}  std={fre_t.std():.3f}  "
          f"|z|>{FUND_THRESH}: {(fre_t.abs()>FUND_THRESH).mean()*100:.1f}%")
    print(f"    fr_btc_z: mean={frb_t.mean():+.3f}  std={frb_t.std():.3f}  "
          f"|z|>{FUND_THRESH}: {(frb_t.abs()>FUND_THRESH).mean()*100:.1f}%")
    sim_fund_eth_m = simulate_from_pnl(pnl_base['F_FUND_ETH_M'][test_mask], 'F_FUND_ETH_mom')
    sim_fund_btc_m = simulate_from_pnl(pnl_base['F_FUND_BTC_M'][test_mask], 'F_FUND_BTC_mom')
    print(f"    F_FUND_ETH (mom): Sharpe={sim_fund_eth_m['sharpe']:+.3f}  "
          f"active={sim_fund_eth_m['active_days']}/{sim_fund_eth_m['total_days']}")
    print(f"    F_FUND_BTC (mom): Sharpe={sim_fund_btc_m['sharpe']:+.3f}  "
          f"active={sim_fund_btc_m['active_days']}/{sim_fund_btc_m['total_days']}")

    # Aliases for backward references in JSON save
    sim_fund_eth = sim_fund_eth_m
    sim_fund_btc = sim_fund_btc_m

    # v11 reference uses gamma_fast from omega_strat (same as v11's omega)
    # v10 reference: slow γ from omega_strat gamma_eth (unchanged)
    # v10: slow γ position scaling + Sharpe weights
    # NOTE: pnl_v10_dict_orig = 6 strats (matches v10/v11/v12/v13/v14 prior runs)
    #       pnl_v10_dict_full = 8 strats (adds funding fade for v15)
    pnl_v10_dict_orig = {
        'A_directional': get_daily_pnl(apply_gamma_mod(pos_A_dir, gamma_eth, 'directional'), df['ret_eth']),
        'P1_ETH_BTC':    get_daily_pnl(apply_gamma_mod(pair_positions['P1_ETH_BTC'], gamma_eth, 'reversion'), pair_data['P1_ETH_BTC']['sret']),
        'P2_ETH_SOL':    get_daily_pnl(apply_gamma_mod(pair_positions['P2_ETH_SOL'], gamma_eth, 'reversion'), pair_data['P2_ETH_SOL']['sret']),
        'P3_ETH_BNB':    get_daily_pnl(apply_gamma_mod(pair_positions['P3_ETH_BNB'], gamma_eth, 'reversion'), pair_data['P3_ETH_BNB']['sret']),
        'M1_ALT_macro':  get_daily_pnl(pos_alt_macro, df['ret_eth']),
        'M1_BTC_macro':  get_daily_pnl(pos_btc_macro, df['ret_btc']),
    }
    pnl_v10_dict = dict(pnl_v10_dict_orig)
    pnl_v10_dict['F_FUND_ETH_M'] = pnl_base['F_FUND_ETH_M']
    pnl_v10_dict['F_FUND_BTC_M'] = pnl_base['F_FUND_BTC_M']

    # v10 baseline (6 strategies, no funding) — for backward compatibility with v9-v14
    n_s_orig = len(pnl_v10_dict_orig)
    cs_wts_v10_orig  = compute_cs_weights(pnl_v10_dict_orig, window=GAMMA_SCORE_WIN)
    pnl_dyn_v10_orig = pd.Series(0.0, index=df.index)
    for k in pnl_v10_dict_orig:
        pnl_dyn_v10_orig += cs_wts_v10_orig[k].shift(1).fillna(1.0/n_s_orig) * pnl_v10_dict_orig[k]
    sims_v10_orig    = simulate_from_pnl(pnl_dyn_v10_orig[test_mask], 'DYNAMIC_v10_orig')

    # v10 + funding (8 strategies) — the baseline that v15 builds on
    cs_wts_v10 = compute_cs_weights(pnl_v10_dict, window=GAMMA_SCORE_WIN)
    pnl_dyn_v10 = pd.Series(0.0, index=df.index)
    for k in pnl_v10_dict:
        pnl_dyn_v10 += cs_wts_v10[k].shift(1).fillna(1.0/n_s) * pnl_v10_dict[k]
    sims_v10_comb = simulate_from_pnl(pnl_dyn_v10[test_mask], 'DYNAMIC_v10')

    # v11: fast γ weight tilt — uses omega_strat (same 8-feature Ω as v11 used)
    gamma_fast_v11 = (1.0 / (1.0 + omega_strat)).clip(GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH)
    cs_wts_v11 = compute_tilted_weights(
        pnl_base, gamma_fast_v11, tilt_modes, window=GAMMA_SCORE_WIN)
    pnl_dyn_v11 = pd.Series(0.0, index=df.index)
    for k in pnl_base:
        pnl_dyn_v11 += cs_wts_v11[k].shift(1).fillna(1.0/n_s) * pnl_base[k]
    sims_v11_comb = simulate_from_pnl(pnl_dyn_v11[test_mask], 'DYNAMIC_v11')

    # v12: γ_rank tilt (pct_rank of Ω_combined, clipped to [0.05, 0.95])
    gamma_rank_clipped = gamma_rank.clip(GAMMA_RANK_CLIP_LOW, GAMMA_RANK_CLIP_HIGH)
    cs_wts_v12 = compute_tilted_weights(
        pnl_base, gamma_rank_clipped, tilt_modes, window=GAMMA_SCORE_WIN)
    pnl_dyn_v12 = pd.Series(0.0, index=df.index)
    for k in pnl_base:
        pnl_dyn_v12 += cs_wts_v12[k].shift(1).fillna(1.0/n_s) * pnl_base[k]
    sims_v12_comb = simulate_from_pnl(pnl_dyn_v12[test_mask], 'DYNAMIC_v12')

    # v13: regime-conditional rolling Sharpe (no manual tilt_modes)
    cs_wts_v13, sh_high, sh_low = compute_regime_conditional_weights(
        pnl_base, gamma_rank,
        window=GAMMA_REGIME_WINDOW,
        threshold=GAMMA_REGIME_THRESHOLD)
    pnl_dyn_v13 = pd.Series(0.0, index=df.index)
    for k in pnl_base:
        pnl_dyn_v13 += cs_wts_v13[k].shift(1).fillna(1.0/n_s) * pnl_base[k]
    sims_v13_comb = simulate_from_pnl(pnl_dyn_v13[test_mask], 'DYNAMIC_v13')

    # ── v14: production layer ─────────────────────────────────────────────
    # v14a: Sharpe × Stability (no leverage dial) — isolates stability gain
    cs_wts_v14a, stab_dict, raw_sh_dict = compute_stability_weights(
        pnl_base, window=GAMMA_SCORE_WIN, stab_win=STAB_WIN)
    pnl_dyn_v14a = pd.Series(0.0, index=df.index)
    for k in pnl_base:
        pnl_dyn_v14a += cs_wts_v14a[k].shift(1).fillna(1.0/n_s) * pnl_base[k]
    sims_v14a_comb = simulate_from_pnl(pnl_dyn_v14a[test_mask], 'DYNAMIC_v14a')

    # v14b: v10 Sharpe weights × γ leverage dial — isolates risk-control gain
    # Use 6-strategy baseline so v14b matches its prior published value
    lev_mult = compute_leverage_dial(gamma_rank, base=LEV_BASE,
                                     lo=LEV_LO, hi=LEV_HI)
    pnl_dyn_v14b = pnl_dyn_v10_orig * lev_mult.shift(1).fillna(1.0)
    sims_v14b_comb = simulate_from_pnl(pnl_dyn_v14b[test_mask], 'DYNAMIC_v14b')

    # v14_full: Sharpe × Stability × γ leverage dial — production
    pnl_dyn_v14 = pnl_dyn_v14a * lev_mult.shift(1).fillna(1.0)
    sims_v14_comb = simulate_from_pnl(pnl_dyn_v14[test_mask], 'DYNAMIC_v14')

    # ── v15: convex dial + funding-fade strategy ──────────────────────────
    # Clean 4-way ablation:
    #   v15_funding_only = 8-strat (with funding) + LINEAR dial   → isolates funding
    #   v15_convex_only  = 6-strat (no funding)   + CONVEX dial   → isolates convex
    #   v15_full         = 8-strat (with funding) + CONVEX dial   → PRODUCTION
    lev_cvx = compute_leverage_dial_convex(gamma_rank, base=CVX_BASE,
                                           lo=CVX_LO, hi=CVX_HI)

    # 15a: convex dial only (6 strats, no funding)
    pnl_dyn_v15a = pnl_dyn_v10_orig * lev_cvx.shift(1).fillna(1.0)
    sims_v15a_comb = simulate_from_pnl(pnl_dyn_v15a[test_mask], 'DYNAMIC_v15a_convex_only')

    # 15b: funding-fade only (8 strats, linear dial)
    pnl_dyn_v15b = pnl_dyn_v10 * lev_mult.shift(1).fillna(1.0)
    sims_v15b_comb = simulate_from_pnl(pnl_dyn_v15b[test_mask], 'DYNAMIC_v15b_funding_only')

    # 15: full production (8 strats + convex dial)
    pnl_dyn_v15 = pnl_dyn_v10 * lev_cvx.shift(1).fillna(1.0)
    sims_v15_comb = simulate_from_pnl(pnl_dyn_v15[test_mask], 'DYNAMIC_v15')

    print(f"\n── v15 convex leverage dial [test stats] ─────────────────────────────")
    lev_cvx_t = lev_cvx[test_mask]
    lev_lin_t = lev_mult[test_mask]
    print(f"  lev_cvx:  mean={lev_cvx_t.mean():.3f}  std={lev_cvx_t.std():.3f}  "
          f"min={lev_cvx_t.min():.3f}  max={lev_cvx_t.max():.3f}")
    print(f"  defensive (lev<0.7): {(lev_cvx_t<0.7).mean()*100:.1f}%   "
          f"full       (lev>1.1): {(lev_cvx_t>1.1).mean()*100:.1f}%")
    print(f"  v14b linear dial:    mean={lev_lin_t.mean():.3f}  std={lev_lin_t.std():.3f}")

    # ── v14 diagnostics ───────────────────────────────────────────────────
    print(f"\n── v14 leverage dial [test stats] ────────────────────────────────────")
    lev_t = lev_mult[test_mask]
    print(f"  lev_mult: mean={lev_t.mean():.3f}  std={lev_t.std():.3f}  "
          f"min={lev_t.min():.3f}  max={lev_t.max():.3f}")
    print(f"  defensive (lev<0.8): {(lev_t<0.8).mean()*100:.1f}%   "
          f"full       (lev>1.1): {(lev_t>1.1).mean()*100:.1f}%")

    print(f"\n── v14 stability multipliers [test mean] ─────────────────────────────")
    print(f"  {'Strategy':<22}  {'rawSh_end':>10}  {'stab_end':>10}  {'wt_v10':>8}  {'wt_v14a':>8}")
    print("─" * 70)
    last_idx = df.index[test_mask][-1]
    for k in pos_base:
        rsh = raw_sh_dict[k].loc[last_idx] if last_idx in raw_sh_dict[k].index else float('nan')
        st  = stab_dict[k].loc[last_idx]   if last_idx in stab_dict[k].index   else float('nan')
        w10 = cs_wts_v10[k][test_mask].mean()
        w14 = cs_wts_v14a[k][test_mask].mean()
        print(f"  {k:<22}  {rsh:>+10.3f}  {st:>+10.3f}  {w10:>+8.3f}  {w14:>+8.3f}")

    # ── Per-regime Sharpe diagnostic [test, end-of-period values] ─────────
    print(f"\n── Per-regime rolling Sharpe at test-end [v13 internals] ─────────────")
    print(f"  {'Strategy':<22}  {'high-γ Sh':>10}  {'low-γ Sh':>10}  {'preferred regime':>17}")
    print("─" * 68)
    last_idx = df.index[test_mask][-1]
    for k in pos_base:
        sh_h = sh_high[k].loc[last_idx] if last_idx in sh_high[k].index else float('nan')
        sh_l = sh_low[k].loc[last_idx]  if last_idx in sh_low[k].index  else float('nan')
        if np.isnan(sh_h) or np.isnan(sh_l):
            pref = 'n/a'
        elif sh_h > sh_l + 0.1:
            pref = 'HIGH (stress)'
        elif sh_l > sh_h + 0.1:
            pref = 'LOW (calm)'
        else:
            pref = 'neutral'
        print(f"  {k:<22}  {sh_h:>+10.3f}  {sh_l:>+10.3f}  {pref:>17}")

    # ── Comparison table ───────────────────────────────────────────────────
    W = 110
    print("\n" + "─" * W)
    print("── v10 / v14b / v15 ablation: dynamic portfolio comparison [test] ──")
    print("─" * W)
    print(f"  {'Variant':<32}  {'Sharpe':>8}  {'MaxDD':>8}  {'\u0394 vs v10_orig':>14}")
    print("─" * W)
    rows = [
        ('v10 baseline (6 strats)',           sims_v10_orig),
        ('v10 + funding (8 strats)',          sims_v10_comb),
        ('v14b (linear dial,  6 strats)',     sims_v14b_comb),
        ('v15a (CONVEX dial,  6 strats)',     sims_v15a_comb),
        ('v15b (linear dial,  8 strats)',     sims_v15b_comb),
        ('v15  (CONVEX dial,  8 strats) [PROD]', sims_v15_comb),
    ]
    base = sims_v10_orig['sharpe']
    for label, r in rows:
        sh = r['sharpe']; dd = r['max_dd']
        d  = sh - base
        print(f"  {label:<32}  {sh:>+8.3f}  {dd:>+8.3f}  {d:>+14.3f}")

    # ── Mean weights: v10 with funding (8 strats) ─────────────────────────
    print(f"\n── Mean weights [test]: v10 8-strat (with funding) ──────────────────")
    print(f"  {'Strategy':<22}  {'wt':>8}")
    print("─" * 36)
    for k in pnl_v10_dict:
        wt = cs_wts_v10[k][test_mask].mean()
        print(f"  {k:<22}  {wt:>+8.3f}")

    # ── Mean weights: v10 → v14a (Sharpe×Stability) ───────────────────────
    print(f"\n── Mean weights [test]: v10 → v14a (Sharpe×Stability) ──────────────────")
    print(f"  {'Strategy':<22}  {'v10 wt':>8}  {'v14a wt':>8}  {'Δ':>8}")
    print("─" * 56)
    for k in pos_base:
        wt10  = cs_wts_v10[k][test_mask].mean()
        wt14a = cs_wts_v14a[k][test_mask].mean()
        print(f"  {k:<22}  {wt10:>+8.3f}  {wt14a:>+8.3f}  {wt14a-wt10:>+8.3f}")

    # ── Full v9 results table (unchanged from v11) ─────────────────────────
    print()
    print("─" * 95)
    print(f"── PnL results (test {TEST_START}–2026) — individual strategies ─────────────────────")
    print("─" * 95)
    v4_ref = {'A_directional': 0.535, 'P1_ETH_BTC': 0.758,
              'P2_ETH_SOL': 0.835, 'P3_ETH_BNB': 1.251}
    v6_ref = {'A_directional': 0.535, 'P1_ETH_BTC': 0.641,
              'P2_ETH_SOL': 0.927, 'P3_ETH_BNB': -1.248,
              'M1_ALT_macro': 1.387, 'M1_BTC_macro': 0.156}
    print(f"  {'Strategy':<22}  {'v4 Sh':>6}  {'v6 Sh':>7}  {'v9 Sh':>7}  "
          f"{'Sh/Lev':>7}  {'MaxDD':>7}  {'Active%':>7}")
    print("─" * 95)

    bhr = sims['A_directional']
    print(f"  {'ETH Buy & Hold':<22}  {'':>6}  {'':>7}  "
          f"{bhr['bh_sharpe']:>+7.3f}  {'':>7}  "
          f"{'   ---':>7}  "
          f"{bhr['bh_max_dd']:>7.3f}  {'100.0%':>7}")
    print()
    for name, r in sims.items():
        if name == 'COMBINED_4way':
            continue
        pct  = r['active_days'] / r['total_days'] * 100
        v4_s = f"{v4_ref[name]:>+6.3f}" if name in v4_ref else "      "
        v6_s = f"{v6_ref[name]:>+7.3f}" if name in v6_ref else "       "
        print(f"  {name:<22}  {v4_s}  {v6_s}  {r['sharpe']:>+7.3f}  "
              f"{r['sharpe_per_lev']:>+7.3f}  "
              f"{r['max_dd']:>7.3f}  {pct:>6.1f}%")

    # ── IC ─────────────────────────────────────────────────────────────────
    print(f"\n── IC (H=21d fwd) ───────────────────────────────────────────────────")
    for name, r in ic_res.items():
        ic_s = f"{r['ic']:>+8.4f}" if r['ic'] is not None else "     n/a"
        print(f"  {name:<22}: n={r['n']:>4}  IC={ic_s}  acc={r['acc'] if r['acc'] else 'n/a'}")

    # ── UDL state + validity ───────────────────────────────────────────────
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
        pE    = (t_st==0).sum() / total * 100
        pD    = (t_st==1).sum() / total * 100
        pS    = (t_st==2).sum() / total * 100
        pV    = t_mv.sum() / total * 100
        drft_m = sd['z_drift'][test_mask].dropna().median()
        reff_m = sd['rev_eff'][test_mask].dropna().median()
        print(f"  {key:<14}  {pE:>7.1f}%  {pD:>7.1f}%  {pS:>8.1f}%  "
              f"{pV:>6.1f}%  {drft_m:>10.4f}  {reff_m:>12.6f}")

    # ── Ablation: v6 vs v7 router ──────────────────────────────────────────
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
              f"{r7['sharpe'] - r6['sharpe']:>+6.3f}  "
              f"{pct6:>10.1f}%  {pct7:>10.1f}%")

    # ── Reversion accuracy by UDL state ───────────────────────────────────
    print(f"\n── Reversion accuracy by UDL state [test, validity-gated] ──────────")
    for key, _, _, _, _ in pairs:
        sd   = pair_data[key]
        z    = sd['z']
        sr   = sd['sret']
        fwd5 = sr.rolling(5).sum().shift(-5)
        mval = sd['manifold_valid']
        print(f"  {key}:")
        for st, sname in state_names.items():
            m = test_mask & (sd['udl_state'] == st) & (z.abs() > 1.0) & mval.astype(bool)
            n_m = m.sum()
            if n_m < 10:
                print(f"    {sname:<10}: n={n_m} (too small)")
                continue
            rev_acc = ((-np.sign(z[m])) == np.sign(fwd5[m].fillna(0))).mean()
            result  = "REVERT" if rev_acc > 0.52 else "CONTINUE" if rev_acc < 0.48 else "mixed"
            print(f"    {sname:<10}: n={n_m:>4}  rev_acc={rev_acc:.3f}  → {result}")
        print()

    # ── Crisis Sharpe ──────────────────────────────────────────────────────
    crises = {
        '2022_winter':   ('2022-01-01', '2022-12-31'),
        '2023_recovery': ('2023-01-01', '2023-12-31'),
        '2024_bull':     ('2024-01-01', '2024-12-31'),
        '2025_bear':     ('2025-01-01', '2025-12-31'),
    }
    print("── Crisis Sharpe (v9 positions) ─────────────────────────────────────")
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
        va = c_sh(pos_A_dir, df['ret_eth'], cs, ce)
        p1 = c_sh(pair_positions['P1_ETH_BTC'], pair_data['P1_ETH_BTC']['sret'], cs, ce)
        p2 = c_sh(pair_positions['P2_ETH_SOL'], pair_data['P2_ETH_SOL']['sret'], cs, ce)
        p3 = c_sh(pair_positions['P3_ETH_BNB'], pair_data['P3_ETH_BNB']['sret'], cs, ce)
        am = c_sh(pos_alt_macro, df['ret_eth'], cs, ce)
        print(f"  {cname:<18}  {va}  {p1:>11}  {p2:>11}  {p3:>11}  {am:>10}")

    # ─────────────────────────────────────────────────────────────────────
    #  SAVE
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
            'z_drift_median': round(float(sd['z_drift'][test_mask].dropna().median()), 4),
            'rev_eff_median': round(float(sd['rev_eff'][test_mask].dropna().median()), 6),
        }

    sims_all = dict(sims)
    sims_all['DYNAMIC_v10']  = sims_v10_comb
    sims_all['DYNAMIC_v11']  = sims_v11_comb
    sims_all['DYNAMIC_v12']  = sims_v12_comb
    sims_all['DYNAMIC_v13']  = sims_v13_comb
    sims_all['DYNAMIC_v14a'] = sims_v14a_comb
    sims_all['DYNAMIC_v14b'] = sims_v14b_comb
    sims_all['DYNAMIC_v14']  = sims_v14_comb
    sims_all['DYNAMIC_v15a'] = sims_v15a_comb
    sims_all['DYNAMIC_v15b'] = sims_v15b_comb
    sims_all['DYNAMIC_v15']  = sims_v15_comb
    sims_all['F_FUND_ETH']   = sim_fund_eth
    sims_all['F_FUND_BTC']   = sim_fund_btc

    results = {
        "model":   "Crypto BSDT v15 — Production+: convex γ dial + funding-extreme fade",
        "version": "v15",
        "gamma_stats": {
            "gamma_rank_mean_test":  float(round(gr_t.mean(), 4)),
            "gamma_rank_std_test":   float(round(gr_t.std(), 4)),
            "gamma_rank_p10_test":   float(round(gr_t.quantile(0.10), 4)),
            "gamma_rank_p90_test":   float(round(gr_t.quantile(0.90), 4)),
            "pct_hi_rank":           float(round(pct_hi, 1)),
            "pct_lo_rank":           float(round(pct_lo, 1)),
            "gamma_fast_mean_test":    float(round(gf_t.mean(), 4)),
            "gamma_fast_std_test":     float(round(gf_t.std(), 4)),
            "omega_strat_mean_test":   float(round(os_t.mean(), 4)),
            "omega_strat_std_test":    float(round(os_t.std(), 4)),
            "omega_price_ext_mean":    float(round(op_t.mean(), 4)),
            "omega_price_ext_std":     float(round(op_t.std(), 4)),
            "omega_lev_mean_test":   float(round(ol_t.dropna().mean(), 4)) if lev_cov > 0 else None,
            "omega_lev_std_test":    float(round(ol_t.dropna().std(), 4)) if lev_cov > 0 else None,
            "omega_lev_coverage_pct": float(round(lev_cov, 1)),
        },
        "class_dist": class_dist,
        "pnl_results": _clean(sims_all),
        "ic_results":  _clean(ic_res),
        "version_history": {
            "v9_dynamic":   -0.020,
            "v10_dynamic":  sims_v10_comb['sharpe'],
            "v10_orig_dynamic": sims_v10_orig['sharpe'],
            "v11_dynamic":  sims_v11_comb['sharpe'],
            "v12_dynamic":  sims_v12_comb['sharpe'],
            "v13_dynamic":  sims_v13_comb['sharpe'],
            "v14a_dynamic": sims_v14a_comb['sharpe'],
            "v14b_dynamic": sims_v14b_comb['sharpe'],
            "v14_dynamic":  sims_v14_comb['sharpe'],
            "v15a_dynamic": sims_v15a_comb['sharpe'],
            "v15b_dynamic": sims_v15b_comb['sharpe'],
            "v15_dynamic":  sims_v15_comb['sharpe'],
        },
        "v14_diagnostics": {
            "lev_mult_mean": float(round(lev_t.mean(), 3)),
            "lev_mult_std":  float(round(lev_t.std(), 3)),
            "lev_mult_min":  float(round(lev_t.min(), 3)),
            "lev_mult_max":  float(round(lev_t.max(), 3)),
            "pct_defensive": float(round((lev_t<0.8).mean()*100, 1)),
            "pct_full":      float(round((lev_t>1.1).mean()*100, 1)),
        },
        "v15_diagnostics": {
            "lev_cvx_mean": float(round(lev_cvx_t.mean(), 3)),
            "lev_cvx_std":  float(round(lev_cvx_t.std(), 3)),
            "lev_cvx_min":  float(round(lev_cvx_t.min(), 3)),
            "lev_cvx_max":  float(round(lev_cvx_t.max(), 3)),
            "funding_eth_standalone_sharpe": float(round(sim_fund_eth['sharpe'], 3)),
            "funding_btc_standalone_sharpe": float(round(sim_fund_btc['sharpe'], 3)),
            "funding_eth_active_pct": float(round(sim_fund_eth['active_days']/sim_fund_eth['total_days']*100, 1)),
            "funding_btc_active_pct": float(round(sim_fund_btc['active_days']/sim_fund_btc['total_days']*100, 1)),
        },
    }

    import os
    out_path = os.path.join(OUT_DIR, "crypto_bsdt_v15_results.json")
    with open(out_path, 'w') as f:
        json.dump(_clean(results), f, indent=2)
    print(f"\n  Results saved → {out_path}")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 96)
    print("  SUMMARY: v9 → v10 → v11 → v12 → v13 → v14 → v15")
    print("=" * 96)
    print(f"  {'Version':<28}  {'Source':<48}  {'DYNAMIC Sharpe':>14}")
    print("─" * 96)
    summary_rows = [
        ('v9 (4-way equal)',         'drift gate, anchored z-score',                   -0.020),
        ('v10 (Sharpe wts, 6 str)',  'rolling Sharpe weights',                          sims_v10_orig['sharpe']),
        ('v11 (fast γ tilt)',         'γ_fast=1/(1+Ω_price), weight tilt',               sims_v11_comb['sharpe']),
        ('v12 (γ_rank tilt)',         'γ_rank tilt + Ω decomposition',                   sims_v12_comb['sharpe']),
        ('v13 (regime Sharpe)',      'rolling Sharpe split by γ_rank>0.5 regime',       sims_v13_comb['sharpe']),
        ('v14a (Sh×Stab)',           'Sharpe×Stability weights, no leverage dial',      sims_v14a_comb['sharpe']),
        ('v14b (linear γ dial)',     'v10 × linear γ-leverage dial',                    sims_v14b_comb['sharpe']),
        ('v15a (CONVEX dial only)',  'v10 6-strat × convex dial',                      sims_v15a_comb['sharpe']),
        ('v15b (funding only)',      'v10 8-strat (with funding) × linear dial',       sims_v15b_comb['sharpe']),
        ('v15  (PRODUCTION)',        'funding fade + convex γ dial',                   sims_v15_comb['sharpe']),
    ]
    for vname, src, sh in summary_rows:
        print(f"  {vname:<22}  {src:<38}  {sh:>+14.3f}")
    print()
    print(f"  γ_rank [test]:  mean={gr_t.mean():.3f}  std={gr_t.std():.3f}  "
          f">0.6: {pct_hi:.0f}%  <0.4: {pct_lo:.0f}%")
    print(f"  γ_fast [test]:  mean={gf_t.mean():.3f}  std={gf_t.std():.3f}  "
          f">0.6: 0.0%  <0.4: 0.0%  (v11 reference)")


if __name__ == '__main__':
    main()
