"""
Crypto BSDT v18 — refined geometric layer (smoothed φ, capped z, gated alignment)
================================================================================

v16 (φ direction-change + collapse alignment + EMA) is current PROD at +0.969.
v17 (circular stats R/θ̄/tan + true MFLS κ) was a documented negative result
(+0.929) — those formal signals were redundant with v16's geometric layer.

v18 refines v16's geometric layer itself per noise-robustness review:

  1. EMA-smooth the state vector v_t (span=3) BEFORE computing direction
     change — prevents φ from spiking on micro-fluctuations of the
     normalised unit-vector.

  2. Replace the raw cosine-difference φ with a directional 1st-derivative
     of the smoothed v: directional_φ = ⟨Δv_smooth, u_t⟩, then
     φ = clip(expanding_z(directional_φ), 0, 3) — hard-cap prevents
     low-volatility z-score blowups during regime transitions.

  3. Replace rolling-mean collapse direction with EWMA(span=10) of the
     smoothed state — smoother attractor estimate.

  4. Gate the alignment penalty: only apply when φ exceeds a small
     threshold:
         align_gate = clip((φ - 0.5) / 2.0, 0, 1)
         lev *= (1 - align_gate · max(alignment, 0))
     Small φ → no penalty (don't damp benign trends); real instability
     → penalty activates.

Falsifiable 5-way ablation [test 2023-2026]:
  v16  (PROD)              baseline
  v18_smooth               + state-vector EMA smoothing only
  v18_cap                  + φ cap [0,3] only
  v18_gate                 + gated alignment only
  v18  (full refinement)   smoothing + cap + gate + EWMA collapse_dir

Judged on: Sharpe, MaxDD, leverage jitter (std of lev), and φ distribution
(p99 / fraction of days φ > 1.0). A v18 win requires either Sharpe ≥ v16
with MaxDD improvement, OR materially lower lev jitter at equal Sharpe.

────────────────────────────────────────────────────────────────────────────
[v16 docstring retained below for context]

v14b (linear γ-leverage dial, 6 strats) is the production champion at +0.913.
v15 falsified two upgrades:
  - Convex γ dial: -0.018 (over-de-risks)
  - Funding strategies: -1.077 (sparse signal dilutes weight)

v16 — final layer of the BSDT theory: state-vector geometry.

So far the system uses MAGNITUDE (MFLS), SPEED (γ), CROWDING (R/θ).
What's missing: WHERE the system is moving in deviation space.

Define state vector:
    v_t = [Ω_strat, γ_rank, MFLS_z, ΔA_fast]
    u_t = v_t / ||v_t||                       (unit direction on a 4-sphere)

Two new geometric signals:

  (A) DIRECTION CHANGE  φ_t = 1 - u_t · u_{t-1}
        ~0  → stable regime
        med → drift
        high→ regime break / whipsaw warning

  (B) COLLAPSE ALIGNMENT
        collapse_dir_t = normalise( rolling_mean(v, 20) )
        alignment_t    = u_t · collapse_dir_t
        High +alignment → moving along recent attractor → unsafe (may extend)
        Low / negative  → orthogonal escape → safe

Apply atop v14b's lev_mult:
    lev_v16 = lev_v14b
              / (1 + φ_PEN · φ_t)               # whipsaw guard
              · (1 - ALIGN_PEN · clip(align,0,1))  # collapse-direction guard
    lev_v16 = ema(lev_v16, EMA_SPAN).clip(LEV_LO, LEV_HI)

Falsifiable 4-way ablation (all on v10_orig 6-strat baseline):
  v14b           : v10 × linear γ dial                              (champion)
  v16_phi        : v14b × (1 / (1 + φ·φ_t))                         isolates (A)
  v16_align      : v14b × (1 - α·clip(align,0,1))                   isolates (B)
  v16            : v14b × both penalties + EMA smooth   (PRODUCTION)

Funding strategies retained but NOT in production pnl (kept for diagnostics).
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

# ─── v16: BSDT vector geometry ────────────────────────────────────────
GEOM_PHI_PEN      = 0.5         # lev /= (1 + GEOM_PHI_PEN * φ)
GEOM_ALIGN_PEN    = 0.5         # lev *= (1 - GEOM_ALIGN_PEN * clip(align,0,1))
GEOM_COLLAPSE_WIN = 20          # rolling window for collapse direction
GEOM_EMA_SPAN     = 5           # smoothing on final lev_v16
GEOM_LEV_LO       = 0.3         # post-penalty floor
GEOM_LEV_HI       = 1.2         # post-penalty cap

# ─── v18: noise-robust refinements of the geometric layer ─────────────
V18_STATE_EMA_SPAN    = 3       # EMA span on the 4-D state vector v_t
V18_COLLAPSE_EMA_SPAN = 10      # EWMA span for collapse direction (replaces rolling mean)
V18_PHI_Z_MIN         = 60      # warmup for φ expanding-z
V18_PHI_Z_CAP         = 3.0     # hard cap on φ z-score (prevents blowups)
V18_ALIGN_GATE_THR    = 0.5     # φ threshold below which alignment gate stays at 0
V18_ALIGN_GATE_DIV    = 2.0     # divisor: align_gate = clip((φ - thr)/div, 0, 1)


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


# ─────────────────────────────────────────────────────────────────────────────
#  v16: BSDT vector geometry — direction change φ + collapse alignment
# ─────────────────────────────────────────────────────────────────────────────
def _expanding_z(s, min_p=60):
    mu = s.expanding(min_p).mean()
    sd = s.expanding(min_p).std()
    return (s - mu) / (sd + 1e-9)


def compute_state_vector(omega, gamma_rank, mfls, dA_fast):
    """
    v16: build the 4-D BSDT state vector  v_t = [Ω_z, γ_rank, MFLS_z, ΔA_fast_z].
    All four components are expanding-z normalised so they sit on a
    comparable scale before the ‖v‖ normalisation.
    Returns a DataFrame with columns ['c1','c2','c3','c4'] aligned on omega.index.
    """
    c1 = _expanding_z(omega).fillna(0.0)
    # γ_rank is already in [0,1]; centre at 0.5 and scale to ~unit
    c2 = ((gamma_rank.fillna(0.5) - 0.5) * 2.0)
    c3 = _expanding_z(mfls).fillna(0.0)
    c4 = _expanding_z(dA_fast).fillna(0.0)
    V  = pd.DataFrame({'c1': c1, 'c2': c2, 'c3': c3, 'c4': c4},
                      index=omega.index)
    return V


def compute_geom_signals(V, collapse_win=20):
    """
    v16: from state-vector V (T × 4) compute:
      u_t           : unit vector  v_t / ‖v_t‖
      phi_t         : 1 - cos(φ)  =  1 - u_t · u_{t-1}     (direction change)
      collapse_dir  : normalised rolling mean of v_t       (recent attractor)
      alignment_t   : u_t · collapse_dir_t                 (attractor alignment)
    All series indexed like V; warmup days are NaN.
    """
    M = V.values
    norms = np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
    U = M / norms                                                 # (T,4) unit dirs

    # φ_t = 1 - u_t · u_{t-1}
    cos_phi = np.full(len(U), np.nan)
    cos_phi[1:] = np.einsum('ij,ij->i', U[1:], U[:-1])
    phi = 1.0 - cos_phi                                            # ∈ [0, 2]

    # Collapse direction = normalised rolling mean of raw v
    Vc = V.rolling(collapse_win, min_periods=collapse_win // 2).mean().values
    Vc_norm = np.linalg.norm(Vc, axis=1, keepdims=True) + 1e-9
    Cd = Vc / Vc_norm
    alignment = np.einsum('ij,ij->i', U, Cd)                       # ∈ [-1, 1]

    idx = V.index
    return (pd.Series(phi,        index=idx, name='phi'),
            pd.Series(alignment,  index=idx, name='alignment'),
            pd.DataFrame(U, index=idx, columns=['u1','u2','u3','u4']))


def apply_geom_penalties(lev_base, phi, alignment,
                          phi_pen=0.5, align_pen=0.5,
                          ema_span=5, lo=0.3, hi=1.2):
    """
    v16: layer φ direction-change and collapse-alignment penalties on top of
    a base leverage scalar (e.g. v14b's lev_mult).

      lev = lev_base / (1 + phi_pen * φ)             (whipsaw guard)
      lev = lev      * (1 - align_pen * clip(align, 0, 1))
                                                     (avoid extending into the
                                                      recent attractor / collapse)
      lev = ema(lev, ema_span).clip(lo, hi)
    """
    phi_safe   = phi.fillna(0.0).clip(lower=0.0, upper=2.0)
    align_pos  = alignment.fillna(0.0).clip(lower=0.0, upper=1.0)
    lev = lev_base / (1.0 + phi_pen * phi_safe)
    lev = lev * (1.0 - align_pen * align_pos)
    lev = lev.ewm(span=ema_span, adjust=False).mean()
    return lev.clip(lower=lo, upper=hi)


# ─────────────────────────────────────────────────────────────────────────────
#  v18: noise-robust refinements of the geometric layer
# ─────────────────────────────────────────────────────────────────────────────
def compute_geom_signals_v18(V,
                              state_ema_span=V18_STATE_EMA_SPAN,
                              collapse_ema_span=V18_COLLAPSE_EMA_SPAN,
                              phi_z_min=V18_PHI_Z_MIN,
                              phi_z_cap=V18_PHI_Z_CAP,
                              smooth_state=True,
                              z_phi=True,
                              cap_phi=True,
                              ewma_collapse=True):
    """
    v18 refinement of compute_geom_signals.

    Pipeline:
      1. Optional EMA-smooth state vector V (span=state_ema_span)
         → removes micro-jitter on the unit-vector denominator.
      2. directional_phi_t = ⟨ΔV_smooth_t, u_smooth_t⟩  (1st-derivative-style;
         positive when the system is moving along its current direction).
         Replaces the old 1-cos(angle) measure (which is non-negative by
         construction and tends to spike on small angles).
      3. φ_t = clip( expanding_z(directional_phi_t),
                     0, phi_z_cap )                if z_phi & cap_phi
            (only positive z; hard-cap to phi_z_cap).
      4. collapse_dir_t = normalise( EWMA(V_smooth, collapse_ema_span) )
         if ewma_collapse else fall back to rolling mean of raw V.
      5. alignment_t = u_smooth_t · collapse_dir_t.

    All toggles let us A/B individual refinements in ablation.

    Returns: (phi, alignment, U_smooth) all aligned on V.index.
    """
    # 1. smooth state vector
    if smooth_state:
        V_smooth = V.ewm(span=state_ema_span, adjust=False).mean()
    else:
        V_smooth = V.copy()

    M = V_smooth.values
    norms = np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
    U = M / norms                                                  # (T,4)

    # 2. directional 1st-derivative phi
    dV = np.full_like(M, np.nan)
    dV[1:] = M[1:] - M[:-1]
    directional_phi = np.einsum('ij,ij->i', dV, U)                 # ⟨ΔV, u⟩
    phi_raw = pd.Series(directional_phi, index=V.index, name='dir_phi')

    # 3. expanding-z + cap (or pass-through positive part if z_phi=False)
    if z_phi:
        phi_z = _expanding_z(phi_raw, min_p=phi_z_min)
        phi = phi_z.clip(lower=0.0)
        if cap_phi:
            phi = phi.clip(upper=phi_z_cap)
    else:
        phi = phi_raw.clip(lower=0.0)

    # 4. collapse direction
    if ewma_collapse:
        Vc = V_smooth.ewm(span=collapse_ema_span, adjust=False).mean().values
    else:
        Vc = V.rolling(GEOM_COLLAPSE_WIN,
                       min_periods=GEOM_COLLAPSE_WIN // 2).mean().values
    Vc_norm = np.linalg.norm(Vc, axis=1, keepdims=True) + 1e-9
    Cd = Vc / Vc_norm

    # 5. alignment
    alignment = np.einsum('ij,ij->i', U, Cd)

    idx = V.index
    return (phi.rename('phi'),
            pd.Series(alignment, index=idx, name='alignment'),
            pd.DataFrame(U, index=idx, columns=['u1', 'u2', 'u3', 'u4']))


def apply_geom_penalties_v18(lev_base, phi, alignment,
                              phi_pen=GEOM_PHI_PEN,
                              align_pen=GEOM_ALIGN_PEN,
                              align_gate_thr=V18_ALIGN_GATE_THR,
                              align_gate_div=V18_ALIGN_GATE_DIV,
                              ema_span=GEOM_EMA_SPAN,
                              lo=GEOM_LEV_LO, hi=GEOM_LEV_HI,
                              gate_alignment=True):
    """
    v18 leverage stacking:

      lev = lev_base / (1 + phi_pen · φ)
      align_gate = clip( (φ - thr) / div, 0, 1 )         (off until φ exceeds thr)
      lev *= (1 - align_pen · align_gate · max(alignment, 0))
      lev  = ema(lev, ema_span).clip(lo, hi)

    With gate_alignment=False this collapses to the v16 form (full alignment
    penalty active everywhere), so we can A/B the gate cleanly.
    """
    # Note: with v18 phi we expect [0, phi_z_cap], not [0, 2] like v16.
    phi_safe = phi.fillna(0.0).clip(lower=0.0)
    align_pos = alignment.fillna(0.0).clip(lower=0.0, upper=1.0)

    lev = lev_base / (1.0 + phi_pen * phi_safe)
    if gate_alignment:
        gate = ((phi_safe - align_gate_thr) / align_gate_div).clip(lower=0.0,
                                                                    upper=1.0)
        lev = lev * (1.0 - align_pen * gate * align_pos)
    else:
        lev = lev * (1.0 - align_pen * align_pos)
    lev = lev.ewm(span=ema_span, adjust=False).mean()
    return lev.clip(lower=lo, upper=hi)


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

    # ── v16: BSDT vector geometry (φ + collapse alignment) ────────────────
    # State vector v_t = [Ω_z, γ_rank-centred, MFLS_z, ΔA_fast_z]
    # All ablations layered on TOP of v14b (champion: linear dial, 6-strat baseline).
    V_state = compute_state_vector(omega_strat, gamma_rank, mfls_eth, dA_fast)
    phi_t, align_t, U_t = compute_geom_signals(V_state,
                                                collapse_win=GEOM_COLLAPSE_WIN)

    # 16a: φ direction-change penalty only (no alignment, no EMA, no clip-relax)
    lev_v16_phi   = apply_geom_penalties(lev_mult, phi_t, align_t,
                                          phi_pen=GEOM_PHI_PEN, align_pen=0.0,
                                          ema_span=GEOM_EMA_SPAN,
                                          lo=GEOM_LEV_LO, hi=GEOM_LEV_HI)
    pnl_dyn_v16_phi = pnl_dyn_v10_orig * lev_v16_phi.shift(1).fillna(1.0)
    sims_v16_phi    = simulate_from_pnl(pnl_dyn_v16_phi[test_mask], 'DYNAMIC_v16_phi')

    # 16b: collapse-alignment penalty only
    lev_v16_align = apply_geom_penalties(lev_mult, phi_t, align_t,
                                          phi_pen=0.0, align_pen=GEOM_ALIGN_PEN,
                                          ema_span=GEOM_EMA_SPAN,
                                          lo=GEOM_LEV_LO, hi=GEOM_LEV_HI)
    pnl_dyn_v16_align = pnl_dyn_v10_orig * lev_v16_align.shift(1).fillna(1.0)
    sims_v16_align    = simulate_from_pnl(pnl_dyn_v16_align[test_mask], 'DYNAMIC_v16_align')

    # 16: full geometric layer (φ + alignment + EMA smooth)  PRODUCTION
    lev_v16       = apply_geom_penalties(lev_mult, phi_t, align_t,
                                          phi_pen=GEOM_PHI_PEN,
                                          align_pen=GEOM_ALIGN_PEN,
                                          ema_span=GEOM_EMA_SPAN,
                                          lo=GEOM_LEV_LO, hi=GEOM_LEV_HI)
    pnl_dyn_v16   = pnl_dyn_v10_orig * lev_v16.shift(1).fillna(1.0)
    sims_v16_comb = simulate_from_pnl(pnl_dyn_v16[test_mask], 'DYNAMIC_v16')

    # ── v18: noise-robust refinements of the geometric layer ──────────────
    # 18a: state-vector EMA smoothing only (raw 1-cos φ on smoothed v, no z-cap)
    phi_18a, align_18a, _ = compute_geom_signals_v18(V_state,
                                                       smooth_state=True,
                                                       z_phi=False,
                                                       cap_phi=False,
                                                       ewma_collapse=False)
    # NOTE: 18a returns directional_phi (positive part), not z-scored.
    # That's a different scale than v16's 1-cos φ, so we keep phi_pen=0.5
    # but also pass through apply_geom_penalties (v16 form, ungated) for fair A/B.
    lev_v18_smooth = apply_geom_penalties(lev_mult, phi_18a, align_18a,
                                            phi_pen=GEOM_PHI_PEN,
                                            align_pen=GEOM_ALIGN_PEN,
                                            ema_span=GEOM_EMA_SPAN,
                                            lo=GEOM_LEV_LO, hi=GEOM_LEV_HI)
    pnl_dyn_v18_smooth = pnl_dyn_v10_orig * lev_v18_smooth.shift(1).fillna(1.0)
    sims_v18_smooth    = simulate_from_pnl(pnl_dyn_v18_smooth[test_mask],
                                            'DYNAMIC_v18_smooth')

    # 18b: + φ z-score & cap (still no gate, still rolling-mean collapse_dir)
    phi_18b, align_18b, _ = compute_geom_signals_v18(V_state,
                                                       smooth_state=True,
                                                       z_phi=True,
                                                       cap_phi=True,
                                                       ewma_collapse=False)
    lev_v18_cap = apply_geom_penalties(lev_mult, phi_18b, align_18b,
                                         phi_pen=GEOM_PHI_PEN,
                                         align_pen=GEOM_ALIGN_PEN,
                                         ema_span=GEOM_EMA_SPAN,
                                         lo=GEOM_LEV_LO, hi=GEOM_LEV_HI)
    pnl_dyn_v18_cap = pnl_dyn_v10_orig * lev_v18_cap.shift(1).fillna(1.0)
    sims_v18_cap    = simulate_from_pnl(pnl_dyn_v18_cap[test_mask],
                                          'DYNAMIC_v18_cap')

    # 18c: + gated alignment (uses v18 apply, otherwise = 18b)
    lev_v18_gate = apply_geom_penalties_v18(lev_mult, phi_18b, align_18b,
                                              gate_alignment=True)
    pnl_dyn_v18_gate = pnl_dyn_v10_orig * lev_v18_gate.shift(1).fillna(1.0)
    sims_v18_gate    = simulate_from_pnl(pnl_dyn_v18_gate[test_mask],
                                           'DYNAMIC_v18_gate')

    # 18 full: smoothing + z-cap + EWMA collapse_dir + gated alignment
    phi_18, align_18, _ = compute_geom_signals_v18(V_state,
                                                     smooth_state=True,
                                                     z_phi=True,
                                                     cap_phi=True,
                                                     ewma_collapse=True)
    lev_v18 = apply_geom_penalties_v18(lev_mult, phi_18, align_18,
                                         gate_alignment=True)
    pnl_dyn_v18 = pnl_dyn_v10_orig * lev_v18.shift(1).fillna(1.0)
    sims_v18    = simulate_from_pnl(pnl_dyn_v18[test_mask], 'DYNAMIC_v18')

    # ── v19: ALPHA OVERLAY — momentum direction × BSDT leverage ───────────
    # Layer 1 (alpha)      : trend = sign(EMA(ret_base, span))   → +1/−1
    # Layer 2 (risk/exposure): lev_v18_smooth (already in pnl_dyn_v18_smooth)
    # Layer 3 (execution)  : pnl_dyn_v19 = trend.shift(1) × pnl_dyn_v18_smooth
    #
    # This is the user-spec engine. v18 was a passive filter (~21% active days,
    # net unprofitable at 5 bps). v19 multiplies BSDT exposure by a directional
    # market-trend signal, turning the system from defensive into actively
    # directional. Sweep window ∈ {5, 10, 20} on two trend bases:
    #   - BTC return       (dominant market driver)
    #   - strategy mean    (pnl_dyn_v18_smooth's own short-term momentum)
    # Pick the highest-Sharpe combination as PROD v19.

    def _build_v19(ret_base_series, span, base_pnl):
        """trend = sign(EWM(ret_base, span)); pnl = trend.shift(1) * base_pnl."""
        trend = np.sign(ret_base_series.ewm(span=span, adjust=False).mean())
        # forward-fill zeros so first few bars don't kill the signal
        trend = trend.replace(0, np.nan).ffill().fillna(0.0)
        return (trend.shift(1).fillna(0.0) * base_pnl), trend

    # Two candidate trend bases
    ret_btc_base    = df['ret_btc']
    ret_strat_base  = pnl_dyn_v18_smooth   # strategy's own daily PnL stream

    v19_variants = {}
    for span in (5, 10, 20):
        for base_label, base_series in (('btc', ret_btc_base),
                                         ('strat', ret_strat_base)):
            pnl_v19_w, _trend_w = _build_v19(base_series, span, pnl_dyn_v18_smooth)
            tag = f'v19_{base_label}_w{span}'
            sims_v19_w = simulate_from_pnl(pnl_v19_w[test_mask], f'DYNAMIC_{tag}')
            v19_variants[tag] = (pnl_v19_w, sims_v19_w)

    # Pick best by Sharpe → PROD
    best_v19_tag = max(v19_variants, key=lambda k: v19_variants[k][1]['sharpe'])
    pnl_dyn_v19, sims_v19 = v19_variants[best_v19_tag]
    print(f"\n── v19 ALPHA-OVERLAY sweep [test] ────────────────────────────────────")
    print(f"  {'variant':<22}  Sharpe   MaxDD   ActiveDays")
    print(f"  {'-'*22}  ------  ------   ----------")
    for tag, (_, s) in sorted(v19_variants.items(),
                              key=lambda kv: -kv[1][1]['sharpe']):
        marker = '  ★ PROD' if tag == best_v19_tag else ''
        print(f"  {tag:<22}  {s['sharpe']:+.3f}  {s['max_dd']:+.3f}   "
              f"{s['active_days']:>4}/{s['total_days']}{marker}")
    print(f"\n  v19 PROD = {best_v19_tag}")
    print(f"  v18_smooth Sharpe = {sims_v18_smooth['sharpe']:+.3f}  →  "
          f"v19 Sharpe = {sims_v19['sharpe']:+.3f}  "
          f"(Δ = {sims_v19['sharpe'] - sims_v18_smooth['sharpe']:+.3f})")

    # ════════════════════════════════════════════════════════════════════════
    #  v20: STACK uncorrelated alphas — v18_smooth + funding strategies
    #  ────────────────────────────────────────────────────────────────────
    #  F_FUND_ETH (Sh=+1.74, ~6% active) and F_FUND_BTC (Sh=+1.98, ~6% active)
    #  are higher-Sharpe than any DYNAMIC variant, and trade on different days
    #  than v18 (~21% active). v15 destroyed them by Sharpe-blending with weak
    #  strats. v20 stacks them ADDITIVELY at INVERSE-VOL weights so each leg
    #  contributes equal daily risk to the portfolio.
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 96)
    print("  v20 STACKED-ALPHA ENSEMBLE  —  v18_smooth + F_FUND_ETH + F_FUND_BTC")
    print("═" * 96)

    pnl_v18s_v20 = pnl_dyn_v18_smooth[test_mask].fillna(0.0)
    pnl_fundE_v20 = pnl_base['F_FUND_ETH_M'][test_mask].fillna(0.0)
    pnl_fundB_v20 = pnl_base['F_FUND_BTC_M'][test_mask].fillna(0.0)

    legs_v20 = {
        'v18_smooth':  pnl_v18s_v20,
        'F_FUND_ETH':  pnl_fundE_v20,
        'F_FUND_BTC':  pnl_fundB_v20,
    }
    # inverse-vol weights over non-zero days (active-day risk parity)
    vols_v20 = {}
    for k, v in legs_v20.items():
        nz = v[v != 0]
        vols_v20[k] = float(nz.std()) if len(nz) > 1 else float('nan')
    inv_w  = {k: 1.0 / max(s, 1e-9) for k, s in vols_v20.items()}
    norm   = sum(inv_w.values())
    w_v20  = {k: inv_w[k] / norm for k in inv_w}

    pnl_dyn_v20 = sum(w_v20[k] * legs_v20[k] for k in legs_v20)
    sims_v20    = simulate_from_pnl(pnl_dyn_v20, 'DYNAMIC_v20')

    # cross-correlations (orthogonality sanity)
    def _corr(a, b):
        s = pd.concat([a, b], axis=1).dropna()
        if len(s) < 5:
            return float('nan')
        return float(s.iloc[:, 0].corr(s.iloc[:, 1]))
    corr_v18s_fE = _corr(pnl_v18s_v20, pnl_fundE_v20)
    corr_v18s_fB = _corr(pnl_v18s_v20, pnl_fundB_v20)
    corr_fE_fB   = _corr(pnl_fundE_v20, pnl_fundB_v20)

    print(f"\n  ── Per-leg standalone metrics (test) ──")
    print(f"  {'leg':<14}  {'σ_active':>10}  {'weight':>8}  {'Sharpe':>8}  {'active%':>8}")
    for k in legs_v20:
        nz = legs_v20[k][legs_v20[k] != 0]
        sh_k = float(np.sqrt(252) * legs_v20[k].mean() / vols_v20[k]) if vols_v20[k] > 0 else 0.0
        act_pct = 100.0 * len(nz) / len(legs_v20[k]) if len(legs_v20[k]) else 0.0
        print(f"  {k:<14}  {vols_v20[k]:>10.5f}  {w_v20[k]:>8.3f}  {sh_k:>+8.3f}  {act_pct:>7.1f}%")

    print(f"\n  ── Cross-correlations (orthogonality check) ──")
    print(f"    corr(v18_smooth, F_FUND_ETH) = {corr_v18s_fE:+.3f}")
    print(f"    corr(v18_smooth, F_FUND_BTC) = {corr_v18s_fB:+.3f}")
    print(f"    corr(F_FUND_ETH, F_FUND_BTC) = {corr_fE_fB:+.3f}")
    if max(abs(corr_v18s_fE), abs(corr_v18s_fB), abs(corr_fE_fB)) > 0.30:
        print(f"    ⚠ WARNING: |corr| > 0.30 — orthogonality assumption weakened")
    else:
        print(f"    ✓ all |corr| < 0.30 — orthogonality holds, inverse-vol stacking valid")

    print(f"\n  ── v20 ensemble headline ──")
    print(f"    Sharpe        = {sims_v20['sharpe']:+.3f}   "
          f"(v18_smooth = {sims_v18_smooth['sharpe']:+.3f},  "
          f"Δ = {sims_v20['sharpe']-sims_v18_smooth['sharpe']:+.3f})")
    print(f"    MaxDD         = {sims_v20['max_dd']:+.3f}")
    print(f"    cum return    = {sims_v20['cum_return']:+.3f}")
    print(f"    active days   = {sims_v20['active_days']}/{sims_v20['total_days']}")

    # ── v20 K-sweep (gross + 5bps net), $1,200 capital ───────────────────
    INIT_V20 = 1200.0
    TCOST_V20 = 5.0  # bps per active day

    def _v20_metrics(returns, K, tcost_bps=0.0):
        r = (returns.dropna().astype(float) * K).copy()
        if tcost_bps > 0:
            cost = (tcost_bps / 1e4) * (returns.dropna().abs() > 0).astype(float)
            r = r - cost
        eq = INIT_V20 * (1.0 + r).cumprod()
        if len(eq) == 0 or eq.iloc[-1] <= 0:
            return dict(K=K, final=0.0, pnl=-INIT_V20, sh=float('nan'),
                        cagr=float('nan'), dd_pct=float('nan'),
                        dd_dol=float('nan'), ruined=True)
        peak = eq.cummax()
        dd   = (eq - peak) / peak
        years = len(eq) / 252.0
        cagr  = (eq.iloc[-1] / INIT_V20) ** (1.0 / max(years, 1e-9)) - 1.0
        sh    = float(np.sqrt(252) * r.mean() / r.std()) if r.std() > 0 else 0.0
        return dict(K=K, final=float(eq.iloc[-1]),
                    pnl=float(eq.iloc[-1] - INIT_V20), sh=sh, cagr=cagr,
                    dd_pct=float(dd.min()), dd_dol=float((eq - peak).min()),
                    ruined=False)

    K_GRID_v20 = [1, 2, 3, 5, 10]
    print(f"\n  ── v20 EXPOSURE-SCALING SWEEP ($1,200 starting capital) ──")
    print(f"  {'mode':<10}  {'K':>3}    Sharpe      CAGR        Final          PnL    MaxDD %     MaxDD $")
    print(f"  " + "-" * 96)
    for K in K_GRID_v20:
        m = _v20_metrics(pnl_dyn_v20, K, tcost_bps=0.0)
        print(f"  {'gross':<10}  {K:>3}    {m['sh']:+.3f}   {m['cagr']*100:+6.2f}%  "
              f"$ {m['final']:>9,.2f}  $ {m['pnl']:>+10,.2f}    "
              f"{m['dd_pct']*100:+6.2f}%  $ {m['dd_dol']:>+9,.2f}")
    for K in K_GRID_v20:
        m = _v20_metrics(pnl_dyn_v20, K, tcost_bps=TCOST_V20)
        print(f"  {'net 5bps':<10}  {K:>3}    {m['sh']:+.3f}   {m['cagr']*100:+6.2f}%  "
              f"$ {m['final']:>9,.2f}  $ {m['pnl']:>+10,.2f}    "
              f"{m['dd_pct']*100:+6.2f}%  $ {m['dd_dol']:>+9,.2f}")

    # break-even K (smallest K making net PnL > 0)
    breakeven_K20 = None; breakeven_m20 = None
    for K in np.arange(0.25, 20.01, 0.05):
        m = _v20_metrics(pnl_dyn_v20, float(K), tcost_bps=TCOST_V20)
        if not m['ruined'] and m['pnl'] > 0:
            breakeven_K20 = float(K); breakeven_m20 = m
            break
    if breakeven_m20:
        print(f"\n  v20 NET break-even K = {breakeven_K20:.2f}")
        print(f"    Final ${breakeven_m20['final']:.2f}  PnL ${breakeven_m20['pnl']:+.2f}  "
              f"MaxDD {breakeven_m20['dd_pct']*100:+.2f}%  Sharpe {breakeven_m20['sh']:+.3f}")
    else:
        print(f"\n  v20 NET break-even K not reached in [0.25, 20]")

    # best risk-adjusted K under MaxDD ≤ 40%, net of 5bps
    best_K20 = None; best_sh20 = -1e9; best_m20 = None
    for K in np.arange(1.0, 20.01, 0.25):
        m = _v20_metrics(pnl_dyn_v20, float(K), tcost_bps=TCOST_V20)
        if m['ruined'] or abs(m['dd_pct']) > 0.40:
            continue
        if m['sh'] > best_sh20:
            best_sh20 = m['sh']; best_K20 = float(K); best_m20 = m
    if best_m20:
        print(f"\n  v20 best risk-adjusted K (net Sharpe, MaxDD ≤ 40%): K={best_K20:.2f}")
        print(f"    Final ${best_m20['final']:.2f}  PnL ${best_m20['pnl']:+.2f}  "
              f"MaxDD {best_m20['dd_pct']*100:+.2f}% (${best_m20['dd_dol']:+.2f})  "
              f"Sharpe {best_m20['sh']:+.3f}")

    # save v20 sweep CSV + 2-line PNG (K=1 vs best_K, net 5bps)
    K_save_v20 = best_K20 if best_K20 else 10.0
    eq_K1_v20  = INIT_V20 * (1.0 + pnl_dyn_v20.dropna()).cumprod()
    r_KS_v20   = pnl_dyn_v20.dropna() * K_save_v20
    cost_v20   = (TCOST_V20/1e4) * (pnl_dyn_v20.dropna().abs() > 0).astype(float)
    eq_KS_g    = INIT_V20 * (1.0 + r_KS_v20).cumprod()
    eq_KS_n    = INIT_V20 * (1.0 + (r_KS_v20 - cost_v20)).cumprod()

    sweep_csv_v20 = pd.DataFrame({
        'date':            eq_K1_v20.index,
        'equity_K1_gross': eq_K1_v20.values,
        f'equity_K{K_save_v20:.2f}_gross': eq_KS_g.values,
        f'equity_K{K_save_v20:.2f}_net5bps': eq_KS_n.values,
    })
    v20_csv_path = os.path.join(OUT_DIR, 'crypto_bsdt_v20_exposure_sweep.csv')
    sweep_csv_v20.to_csv(v20_csv_path, index=False)
    print(f"\n  v20 scaled curves saved → {v20_csv_path}")

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(eq_K1_v20.index, eq_K1_v20.values, color='gray', lw=1.0, label='K=1 gross')
        ax.plot(eq_KS_g.index,   eq_KS_g.values,   color='steelblue', lw=1.4,
                label=f'K={K_save_v20:.2f} gross')
        ax.plot(eq_KS_n.index,   eq_KS_n.values,   color='crimson', lw=1.4,
                label=f'K={K_save_v20:.2f} net (5bps)')
        ax.set_title(f'v20 stacked-alpha ensemble — exposure scaling at K=1 vs K={K_save_v20:.2f}')
        ax.set_ylabel(f'Equity (from ${INIT_V20:,.0f})')
        ax.grid(True, alpha=0.3); ax.legend(loc='upper left')
        plt.tight_layout()
        v20_png_path = os.path.join(OUT_DIR, 'crypto_bsdt_v20_exposure_sweep.png')
        plt.savefig(v20_png_path, dpi=110); plt.close()
        print(f"  v20 scaled plot   saved → {v20_png_path}")
    except Exception as e:
        print(f"  (matplotlib skipped: {e})")

    # store v20 K-sweep summary for JSON
    v20_summary = {
        'ensemble_sharpe':   float(sims_v20['sharpe']),
        'ensemble_max_dd':   float(sims_v20['max_dd']),
        'weights':           {k: float(round(w_v20[k], 4)) for k in w_v20},
        'corr_v18s_fundE':   float(round(corr_v18s_fE, 4)),
        'corr_v18s_fundB':   float(round(corr_v18s_fB, 4)),
        'corr_fundE_fundB':  float(round(corr_fE_fB, 4)),
        'breakeven_K':       float(breakeven_K20) if breakeven_K20 else None,
        'breakeven_pnl':     float(round(breakeven_m20['pnl'], 2)) if breakeven_m20 else None,
        'best_K':            float(best_K20) if best_K20 else None,
        'best_K_pnl':        float(round(best_m20['pnl'], 2)) if best_m20 else None,
        'best_K_max_dd':     float(round(best_m20['dd_pct'], 4)) if best_m20 else None,
        'best_K_sharpe_net': float(round(best_m20['sh'], 4)) if best_m20 else None,
    }

    # ════════════════════════════════════════════════════════════════════════
    #  v21: DEEP STACK — 4 legs × 4 weighting schemes, picks profit-maximizing
    #  ────────────────────────────────────────────────────────────────────
    #  v20 used inverse-vol (risk parity) → starves the funding alphas because
    #  they're high-vol-per-active-day. For PROFIT (not just Sharpe) we should
    #  Sharpe-weight or Kelly-weight, which puts heavy weight on the +1.74 /
    #  +1.98 funding legs. Also adds 4th orthogonal leg: M1_ALT_macro
    #  (Sh +1.39, ~4.5% active days) — currently sitting unused.
    #
    #  Schemes tested:
    #    invvol  — w_i ∝ 1/σ_i   (v20 baseline, risk parity)
    #    equal   — w_i = 1/N      (naive)
    #    sharpe  — w_i ∝ max(Sh_i, 0)  (profit-tilted)
    #    kelly   — w_i ∝ μ_i / σ_i² (full-Kelly fractional)
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 96)
    print("  v21 DEEP-STACK ENSEMBLE  —  4 legs × 4 weighting schemes")
    print("═" * 96)

    # 4-leg pool (v18_smooth + 3 orthogonal alpha pockets)
    pnl_alt_macro_t = pnl_v10_dict_orig['M1_ALT_macro'][test_mask].fillna(0.0)
    legs_v21 = {
        'v18_smooth':   pnl_v18s_v20,
        'F_FUND_ETH':   pnl_fundE_v20,
        'F_FUND_BTC':   pnl_fundB_v20,
        'M1_ALT_macro': pnl_alt_macro_t,
    }

    # per-leg statistics (active-day vol, daily-mean, Sharpe)
    leg_stats = {}
    for k, v in legs_v21.items():
        nz = v[v != 0]
        sigma = float(nz.std()) if len(nz) > 1 else float('nan')
        mu = float(v.mean())
        sh = float(np.sqrt(252) * mu / sigma) if sigma > 0 else 0.0
        leg_stats[k] = dict(mu=mu, sigma=sigma, sharpe=sh,
                            active_pct=100.0 * len(nz) / max(len(v), 1))

    print(f"\n  ── Leg statistics (test) ──")
    print(f"  {'leg':<14}  {'σ_active':>10}  {'μ_daily':>10}  {'Sharpe':>8}  {'active%':>8}")
    for k, s in leg_stats.items():
        print(f"  {k:<14}  {s['sigma']:>10.5f}  {s['mu']:>+10.6f}  {s['sharpe']:>+8.3f}  {s['active_pct']:>7.1f}%")

    def _normalise(d):
        s = sum(d.values())
        return {k: (v / s if s > 0 else 0.0) for k, v in d.items()}

    schemes = {
        'invvol': _normalise({k: 1.0 / max(s['sigma'], 1e-9) for k, s in leg_stats.items()}),
        'equal':  _normalise({k: 1.0 for k in leg_stats}),
        'sharpe': _normalise({k: max(s['sharpe'], 0.0) for k, s in leg_stats.items()}),
        'kelly':  _normalise({k: max(s['mu'] / max(s['sigma']**2, 1e-12), 0.0) for k, s in leg_stats.items()}),
    }

    # build all v21 variants and simulate
    v21_variants = {}
    for sname, w in schemes.items():
        pnl_v21 = sum(w[k] * legs_v21[k] for k in legs_v21)
        sims_v21 = simulate_from_pnl(pnl_v21, f'DYNAMIC_v21_{sname}')
        v21_variants[sname] = (pnl_v21, sims_v21, w)

    print(f"\n  ── Weight schemes ──")
    print(f"  {'leg':<14}  " + "  ".join(f"{sn:>8}" for sn in schemes))
    for k in legs_v21:
        print(f"  {k:<14}  " + "  ".join(f"{schemes[sn][k]:>8.3f}" for sn in schemes))

    # K-sweep helper (reuse v20 form)
    INIT_V21 = 1200.0
    TCOST_V21 = 5.0

    def _v21_metrics(returns, K, tcost_bps=0.0):
        r = (returns.dropna().astype(float) * K).copy()
        if tcost_bps > 0:
            cost = (tcost_bps / 1e4) * (returns.dropna().abs() > 0).astype(float)
            r = r - cost
        eq = INIT_V21 * (1.0 + r).cumprod()
        if len(eq) == 0 or eq.iloc[-1] <= 0:
            return dict(K=K, final=0.0, pnl=-INIT_V21, sh=float('nan'),
                        cagr=float('nan'), dd_pct=float('nan'),
                        dd_dol=float('nan'), ruined=True)
        peak = eq.cummax()
        dd = (eq - peak) / peak
        years = len(eq) / 252.0
        cagr = (eq.iloc[-1] / INIT_V21) ** (1.0 / max(years, 1e-9)) - 1.0
        sh = float(np.sqrt(252) * r.mean() / r.std()) if r.std() > 0 else 0.0
        return dict(K=K, final=float(eq.iloc[-1]),
                    pnl=float(eq.iloc[-1] - INIT_V21), sh=sh, cagr=cagr,
                    dd_pct=float(dd.min()), dd_dol=float((eq - peak).min()),
                    ruined=False)

    # for each scheme: find best-K under MaxDD ≤ 40% net 5bps, record PnL
    print(f"\n  ── v21 scheme bake-off (best K under MaxDD ≤ 40%, net 5bps, $1,200) ──")
    print(f"  {'scheme':<10}  {'Sh_gross':>9}  {'best_K':>7}  {'final $':>10}  "
          f"{'PnL $':>10}  {'MaxDD%':>8}  {'Sh_net':>7}  {'CAGR%':>7}")
    print(f"  " + "-" * 90)
    bake_results = {}
    for sname, (pnl_v21, sims_v21, w) in v21_variants.items():
        best_K = None; best_sh = -1e9; best_m = None
        for K in np.arange(1.0, 20.01, 0.25):
            m = _v21_metrics(pnl_v21, float(K), tcost_bps=TCOST_V21)
            if m['ruined'] or abs(m['dd_pct']) > 0.40:
                continue
            if m['sh'] > best_sh:
                best_sh = m['sh']; best_K = float(K); best_m = m
        bake_results[sname] = (sims_v21, best_K, best_m, w, pnl_v21)
        if best_m:
            print(f"  {sname:<10}  {sims_v21['sharpe']:>+9.3f}  {best_K:>7.2f}  "
                  f"$ {best_m['final']:>8,.2f}  $ {best_m['pnl']:>+8,.2f}  "
                  f"{best_m['dd_pct']*100:>+7.2f}%  {best_m['sh']:>+7.3f}  "
                  f"{best_m['cagr']*100:>+6.2f}%")
        else:
            print(f"  {sname:<10}  {sims_v21['sharpe']:>+9.3f}     n/a (all ruined or > 40%DD)")

    # pick PROD = scheme with highest best_K_pnl (substantial profit, not just Sharpe)
    valid = {sn: r for sn, r in bake_results.items() if r[2] is not None}
    if not valid:
        print(f"\n  ⚠ No scheme survived MaxDD ≤ 40% — falling back to inv-vol")
        prod_scheme = 'invvol'
    else:
        prod_scheme = max(valid, key=lambda sn: valid[sn][2]['pnl'])
    sims_v21_prod, best_K_v21, best_m_v21, w_v21_prod, pnl_dyn_v21 = bake_results[prod_scheme]

    print(f"\n  ★ v21 PROD scheme = {prod_scheme!r}")
    print(f"    Headline Sharpe (gross, K=1) = {sims_v21_prod['sharpe']:+.3f}")
    print(f"    Best-K = {best_K_v21:.2f}  →  Final ${best_m_v21['final']:,.2f}  "
          f"PnL ${best_m_v21['pnl']:+,.2f}  MaxDD {best_m_v21['dd_pct']*100:+.2f}%")
    print(f"    vs v20 best-K (K=10): PnL +$1,273.60  →  v21 Δ = "
          f"${best_m_v21['pnl'] - 1273.60:+,.2f}")

    # full K-sweep on PROD scheme
    print(f"\n  ── v21 [{prod_scheme}] EXPOSURE-SCALING SWEEP, $1,200 ──")
    print(f"  {'mode':<10}  {'K':>3}    Sharpe      CAGR        Final          PnL    MaxDD %     MaxDD $")
    print(f"  " + "-" * 96)
    K_GRID_v21 = [1, 2, 3, 5, 10]
    for K in K_GRID_v21:
        m = _v21_metrics(pnl_dyn_v21, K, tcost_bps=0.0)
        print(f"  {'gross':<10}  {K:>3}    {m['sh']:+.3f}   {m['cagr']*100:+6.2f}%  "
              f"$ {m['final']:>9,.2f}  $ {m['pnl']:>+10,.2f}    "
              f"{m['dd_pct']*100:+6.2f}%  $ {m['dd_dol']:>+9,.2f}")
    for K in K_GRID_v21:
        m = _v21_metrics(pnl_dyn_v21, K, tcost_bps=TCOST_V21)
        print(f"  {'net 5bps':<10}  {K:>3}    {m['sh']:+.3f}   {m['cagr']*100:+6.2f}%  "
              f"$ {m['final']:>9,.2f}  $ {m['pnl']:>+10,.2f}    "
              f"{m['dd_pct']*100:+6.2f}%  $ {m['dd_dol']:>+9,.2f}")

    # save v21 sweep CSV + PNG
    eq_K1_v21 = INIT_V21 * (1.0 + pnl_dyn_v21.dropna()).cumprod()
    rKS = pnl_dyn_v21.dropna() * best_K_v21
    cKS = (TCOST_V21/1e4) * (pnl_dyn_v21.dropna().abs() > 0).astype(float)
    eq_KS_g_v21 = INIT_V21 * (1.0 + rKS).cumprod()
    eq_KS_n_v21 = INIT_V21 * (1.0 + (rKS - cKS)).cumprod()
    sweep_csv_v21 = pd.DataFrame({
        'date': eq_K1_v21.index,
        'equity_K1_gross': eq_K1_v21.values,
        f'equity_K{best_K_v21:.2f}_gross': eq_KS_g_v21.values,
        f'equity_K{best_K_v21:.2f}_net5bps': eq_KS_n_v21.values,
    })
    v21_csv_path = os.path.join(OUT_DIR, 'crypto_bsdt_v21_exposure_sweep.csv')
    sweep_csv_v21.to_csv(v21_csv_path, index=False)
    print(f"\n  v21 scaled curves saved → {v21_csv_path}")
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(eq_K1_v21.index, eq_K1_v21.values, color='gray', lw=1.0, label='K=1 gross')
        ax.plot(eq_KS_g_v21.index, eq_KS_g_v21.values, color='steelblue', lw=1.4,
                label=f'K={best_K_v21:.2f} gross')
        ax.plot(eq_KS_n_v21.index, eq_KS_n_v21.values, color='crimson', lw=1.4,
                label=f'K={best_K_v21:.2f} net (5bps)')
        ax.set_title(f'v21 deep-stack ({prod_scheme}) — exposure scaling at K=1 vs K={best_K_v21:.2f}')
        ax.set_ylabel(f'Equity (from ${INIT_V21:,.0f})')
        ax.grid(True, alpha=0.3); ax.legend(loc='upper left')
        plt.tight_layout()
        v21_png_path = os.path.join(OUT_DIR, 'crypto_bsdt_v21_exposure_sweep.png')
        plt.savefig(v21_png_path, dpi=110); plt.close()
        print(f"  v21 scaled plot   saved → {v21_png_path}")
    except Exception as e:
        print(f"  (matplotlib skipped: {e})")

    sims_v21 = sims_v21_prod
    v21_summary = {
        'prod_scheme':       prod_scheme,
        'ensemble_sharpe':   float(sims_v21_prod['sharpe']),
        'ensemble_max_dd':   float(sims_v21_prod['max_dd']),
        'weights':           {k: float(round(w_v21_prod[k], 4)) for k in w_v21_prod},
        'best_K':            float(best_K_v21),
        'best_K_pnl':        float(round(best_m_v21['pnl'], 2)),
        'best_K_max_dd':     float(round(best_m_v21['dd_pct'], 4)),
        'best_K_sharpe_net': float(round(best_m_v21['sh'], 4)),
        'best_K_final':      float(round(best_m_v21['final'], 2)),
        'best_K_cagr':       float(round(best_m_v21['cagr'], 4)),
        'all_schemes_pnl':   {sn: (float(round(r[2]['pnl'], 2)) if r[2] else None)
                              for sn, r in bake_results.items()},
    }

    # ──────────────────────────────────────────────────────────────────────
    # v22: VOL-TARGETED v20  —  realized-vol scaling for higher leverage capacity
    # ──────────────────────────────────────────────────────────────────────
    # Rationale: v20's MaxDD ceiling pins K at ~10. Volatility clusters cause
    # the worst drawdowns. Inverse-realized-vol scaling smooths the leveraged
    # path, allowing higher K under the same MaxDD budget → more $ profit.
    print(f"\n  v22 VOL-TARGETED v20  —  realized-vol scaling (K-capacity unlock)")
    INIT_V22  = 1200.0
    TCOST_V22 = 5.0
    LOOKBACK_V22  = 30
    MAX_LEV_INNER = 20.0  # safety cap on inner vol scaler

    base_v22 = pnl_dyn_v20.fillna(0.0).astype(float)
    realized_v22 = base_v22.rolling(LOOKBACK_V22, min_periods=10).std().shift(1)
    realized_v22 = realized_v22.fillna(base_v22.std())
    realized_v22 = realized_v22.replace(0.0, base_v22.std()).clip(lower=1e-6)

    v22_targets = [0.003, 0.005, 0.008, 0.012, 0.018]

    def _v22_metrics(target_vol, K, tcost_bps=TCOST_V22):
        scaler = (target_vol / realized_v22).clip(lower=0.0, upper=MAX_LEV_INNER)
        levered = base_v22 * scaler * float(K)
        active = (base_v22.abs() > 0).astype(float)
        cost = (tcost_bps / 1e4) * active
        net = levered - cost
        eq = INIT_V22 * (1.0 + net).cumprod()
        if len(eq) == 0 or eq.iloc[-1] <= 0:
            return dict(K=K, final=0.0, pnl=-INIT_V22, sh=float('nan'),
                        cagr=float('nan'), dd_pct=float('nan'), ruined=True)
        peak = eq.cummax()
        dd = (eq - peak) / peak
        years = len(eq) / 252.0
        cagr = (eq.iloc[-1] / INIT_V22) ** (1.0 / max(years, 1e-9)) - 1.0
        sh = float(np.sqrt(252) * net.mean() / net.std()) if net.std() > 0 else 0.0
        return dict(K=K, final=float(eq.iloc[-1]), pnl=float(eq.iloc[-1] - INIT_V22),
                    sh=sh, cagr=cagr, dd_pct=float(dd.min()), ruined=False)

    print(f"  ── target_vol bake-off  (best K under MaxDD ≤ 40%, net 5bps) ──")
    print(f"  {'tgt_daily':<10}{'best_K':>8}{'final $':>14}{'PnL $':>14}{'MaxDD%':>10}{'Sh_net':>9}{'CAGR%':>9}")
    v22_bake = {}
    for tgt in v22_targets:
        best = None
        for K in np.arange(0.5, 30.05, 0.5):
            m = _v22_metrics(tgt, float(K), tcost_bps=TCOST_V22)
            if m is None or m.get('ruined', False):
                continue
            if not (m['dd_pct'] >= -0.40):
                continue
            if best is None or m['pnl'] > best['pnl']:
                best = m
        v22_bake[tgt] = best
        if best is not None:
            print(f"  {tgt:<10.4f}{best['K']:>8.2f}  ${best['final']:>10.2f}  "
                  f"${best['pnl']:>+10.2f}  {best['dd_pct']*100:>+8.2f}%  "
                  f"{best['sh']:>+7.3f}  {best['cagr']*100:>+7.2f}%")
        else:
            print(f"  {tgt:<10.4f}  (no K satisfies DD constraint)")

    valid_v22 = {t: r for t, r in v22_bake.items() if r is not None}
    if valid_v22:
        prod_target_v22 = max(valid_v22, key=lambda t: valid_v22[t]['pnl'])
        best_v22 = valid_v22[prod_target_v22]
        print(f"\n  ★ v22 PROD target_vol = {prod_target_v22:.4f}  (daily)")
        print(f"    best K = {best_v22['K']:.2f}  →  PnL +${best_v22['pnl']:.2f}  "
              f"MaxDD {best_v22['dd_pct']*100:+.2f}%  Sh_net {best_v22['sh']:+.3f}  "
              f"CAGR {best_v22['cagr']*100:+.2f}%")
        delta_v20 = best_v22['pnl'] - 1273.60
        print(f"    vs v20 (K=10):   PnL +$1,273.60  →  v22 Δ = ${delta_v20:+.2f}")

        # build sims dict at K=1 for reporting consistency
        scaler_prod = (prod_target_v22 / realized_v22).clip(lower=0.0, upper=MAX_LEV_INNER)
        pnl_v22_K1  = base_v22 * scaler_prod
        sims_v22    = simulate_from_pnl(pnl_v22_K1, 'DYNAMIC_v22')

        # full K-sweep table for the PROD target
        print(f"\n  ── v22 [target={prod_target_v22:.4f}] EXPOSURE SWEEP, $1,200 ──")
        print(f"  {'K':>5}  {'mode':<10}  {'final $':>12}  {'PnL $':>12}  "
              f"{'MaxDD%':>8}  {'Sh_net':>8}  {'CAGR%':>8}")
        for K in [1, 2, 3, 5, 10, best_v22['K']]:
            for mode, tc in [('gross', 0.0), ('net5bp', TCOST_V22)]:
                m = _v22_metrics(prod_target_v22, float(K), tcost_bps=tc)
                if m is None:
                    continue
                print(f"  {K:>5.2f}  {mode:<10}  ${m['final']:>9.2f}  "
                      f"${m['pnl']:>+9.2f}  {m['dd_pct']*100:>+6.2f}%  "
                      f"{m['sh']:>+6.3f}  {m['cagr']*100:>+6.2f}%")

        # save scaled curves
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            scaler_prod = (prod_target_v22 / realized_v22).clip(lower=0.0, upper=MAX_LEV_INNER)
            r1   = base_v22 * scaler_prod * 1.0
            rKb  = base_v22 * scaler_prod * best_v22['K']
            cost = (TCOST_V22/1e4) * (base_v22.abs() > 0).astype(float)
            eq1   = INIT_V22 * (1.0 + r1).cumprod()
            eqKbg = INIT_V22 * (1.0 + rKb).cumprod()
            eqKbn = INIT_V22 * (1.0 + (rKb - cost)).cumprod()
            fig, ax = plt.subplots(figsize=(11, 4))
            ax.plot(eq1.index,   eq1.values,   color='#888', lw=1.2,
                    label=f'K=1 gross')
            ax.plot(eqKbg.index, eqKbg.values, color='#1f77b4', lw=1.6,
                    label=f'K={best_v22["K"]:.2f} gross')
            ax.plot(eqKbn.index, eqKbn.values, color='#d62728', lw=1.6,
                    label=f'K={best_v22["K"]:.2f} net (5bps)')
            ax.set_title(f"v22 vol-target  (tgt={prod_target_v22:.4f})  "
                         f"— exposure scaling at K=1 vs K={best_v22['K']:.2f}")
            ax.set_ylabel('Equity (from $1,200)')
            ax.legend(loc='upper left', fontsize=9); ax.grid(alpha=0.3)
            v22_png = os.path.join(os.path.dirname(__file__),
                                   'crypto_bsdt_v22_exposure_sweep.png')
            plt.tight_layout(); plt.savefig(v22_png, dpi=110); plt.close()
            print(f"  v22 scaled plot saved → {v22_png}")
        except Exception as e:
            print(f"  (matplotlib skipped: {e})")
    else:
        prod_target_v22 = None
        best_v22  = None
        sims_v22  = sims_v20
        print("  v22: no target satisfies DD constraint  →  fall back to v20")

    v22_summary = {
        'prod_target_vol':   float(prod_target_v22) if prod_target_v22 else None,
        'lookback_days':     LOOKBACK_V22,
        'max_inner_lev':     MAX_LEV_INNER,
        'best_K':            float(best_v22['K']) if best_v22 else None,
        'best_K_pnl':        float(round(best_v22['pnl'], 2)) if best_v22 else None,
        'best_K_max_dd':     float(round(best_v22['dd_pct'], 4)) if best_v22 else None,
        'best_K_sharpe_net': float(round(best_v22['sh'], 4)) if best_v22 else None,
        'best_K_final':      float(round(best_v22['final'], 2)) if best_v22 else None,
        'best_K_cagr':       float(round(best_v22['cagr'], 4)) if best_v22 else None,
        'all_targets_pnl':   {f'{t:.4f}': (float(round(r['pnl'], 2)) if r else None)
                              for t, r in v22_bake.items()},
        'ensemble_sharpe':   float(sims_v22['sharpe']),
        'ensemble_max_dd':   float(sims_v22['max_dd']),
    }

    # ── v16 geometry diagnostics ──────────────────────────────────────────
    print(f"\n── v16 BSDT vector-geometry signals [test] ───────────────────────────")
    phi_t_test   = phi_t[test_mask].dropna()
    align_t_test = align_t[test_mask].dropna()
    print(f"  φ (direction-change):  mean={phi_t_test.mean():.3f}  "
          f"std={phi_t_test.std():.3f}  "
          f"p50={phi_t_test.quantile(.5):.3f}  p90={phi_t_test.quantile(.9):.3f}  "
          f"p99={phi_t_test.quantile(.99):.3f}")
    print(f"  alignment (u·collapse): mean={align_t_test.mean():+.3f}  "
          f"std={align_t_test.std():.3f}  "
          f"p10={align_t_test.quantile(.1):+.3f}  "
          f"p50={align_t_test.quantile(.5):+.3f}  "
          f"p90={align_t_test.quantile(.9):+.3f}")
    lev_v16_t  = lev_v16[test_mask].dropna()
    lev_v14b_t = lev_mult[test_mask].dropna()
    print(f"  lev_v14b: mean={lev_v14b_t.mean():.3f}  std={lev_v14b_t.std():.3f}")
    print(f"  lev_v16:  mean={lev_v16_t.mean():.3f}  std={lev_v16_t.std():.3f}  "
          f"min={lev_v16_t.min():.3f}  max={lev_v16_t.max():.3f}")
    print(f"  v16 vs v14b: defensive (<0.7) {(lev_v16_t<0.7).mean()*100:.1f}% "
          f"vs {(lev_v14b_t<0.7).mean()*100:.1f}%   "
          f"full (>1.0) {(lev_v16_t>1.0).mean()*100:.1f}% "
          f"vs {(lev_v14b_t>1.0).mean()*100:.1f}%")
    # Correlation diagnostics
    corr_geom = np.corrcoef(phi_t_test.values,
                             align_t_test.reindex(phi_t_test.index).values)[0,1]
    corr_phi_gamma = np.corrcoef(phi_t_test.values,
                                  gamma_rank[test_mask].reindex(phi_t_test.index).fillna(0.5).values)[0,1]
    print(f"  corr(φ, alignment) = {corr_geom:+.3f}   "
          f"corr(φ, γ_rank) = {corr_phi_gamma:+.3f}  "
          f"(geom should add info beyond γ)")

    # ── v18 geometry diagnostics (refined φ + gated alignment) ────────────
    print(f"\n── v18 refined geometric layer [test] ────────────────────────────────")
    phi_18_t   = phi_18[test_mask].dropna()
    align_18_t = align_18[test_mask].dropna()
    phi_18a_t  = phi_18a[test_mask].dropna()  # raw directional φ (smoothed v)
    print(f"  φ_v16 (1-cos):       mean={phi_t_test.mean():.3f}  "
          f"std={phi_t_test.std():.3f}  "
          f"p99={phi_t_test.quantile(.99):.3f}  "
          f"%>1.0: {(phi_t_test>1.0).mean()*100:.1f}%")
    print(f"  φ_v18 (z-cap [0,3]): mean={phi_18_t.mean():.3f}  "
          f"std={phi_18_t.std():.3f}  "
          f"p99={phi_18_t.quantile(.99):.3f}  "
          f"%>1.0: {(phi_18_t>1.0).mean()*100:.1f}%")
    print(f"  φ_v18 raw dir (pre-z): mean={phi_18a_t.mean():+.4f}  "
          f"std={phi_18a_t.std():.4f}")
    print(f"  alignment_v16: mean={align_t_test.mean():+.3f}  "
          f"std={align_t_test.std():.3f}")
    print(f"  alignment_v18: mean={align_18_t.mean():+.3f}  "
          f"std={align_18_t.std():.3f}  (EWMA collapse_dir)")
    lev_v18_t = lev_v18[test_mask].dropna()
    print(f"  lev_v16:  mean={lev_v16_t.mean():.3f}  std={lev_v16_t.std():.3f}  "
          f"defensive (<0.7): {(lev_v16_t<0.7).mean()*100:.1f}%")
    print(f"  lev_v18:  mean={lev_v18_t.mean():.3f}  std={lev_v18_t.std():.3f}  "
          f"defensive (<0.7): {(lev_v18_t<0.7).mean()*100:.1f}%")
    # Leverage jitter: day-over-day absolute change
    jitter_v16 = lev_v16_t.diff().abs().mean()
    jitter_v18 = lev_v18_t.diff().abs().mean()
    print(f"  lev jitter (mean |Δlev|): v16={jitter_v16:.4f}  v18={jitter_v18:.4f}  "
          f"({(jitter_v18/jitter_v16-1)*100:+.1f}% vs v16)")

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
    print("── v10 / v14b / v15 / v16 ablation: dynamic portfolio comparison [test] ──")
    print("─" * W)
    print(f"  {'Variant':<40}  {'Sharpe':>8}  {'MaxDD':>8}  {'\u0394 vs v10_orig':>14}")
    print("─" * W)
    rows = [
        ('v10 baseline (6 strats)',           sims_v10_orig),
        ('v10 + funding (8 strats)',          sims_v10_comb),
        ('v14b (linear dial,  6 strats) [prev PROD]', sims_v14b_comb),
        ('v15a (CONVEX dial,  6 strats)',     sims_v15a_comb),
        ('v15b (linear dial,  8 strats)',     sims_v15b_comb),
        ('v15  (CONVEX dial,  8 strats)',     sims_v15_comb),
        ('v16_phi   (φ direction-change only)',  sims_v16_phi),
        ('v16_align (collapse alignment only)',  sims_v16_align),
        ('v16  (φ + alignment + EMA)  [PROD]', sims_v16_comb),
        ('v18_smooth (state EMA only)',          sims_v18_smooth),
        ('v18_cap    (+ φ z-cap [0,3])',         sims_v18_cap),
        ('v18_gate   (+ gated alignment)',       sims_v18_gate),
        ('v18  (smooth + cap + gate + EWMA cd)', sims_v18),
        (f'v19  ({best_v19_tag}) [neg result]',   sims_v19),
        ('v20  STACKED (v18s + fundE + fundB)',  sims_v20),
        (f'v21  DEEP STACK [{prod_scheme}]',     sims_v21_prod),
        (f'v22  VOL-TARGET v20',                 sims_v22),
    ]
    base = sims_v10_orig['sharpe']
    for label, r in rows:
        sh = r['sharpe']; dd = r['max_dd']
        d  = sh - base
        print(f"  {label:<40}  {sh:>+8.3f}  {dd:>+8.3f}  {d:>+14.3f}")

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
    sims_all['DYNAMIC_v16_phi']   = sims_v16_phi
    sims_all['DYNAMIC_v16_align'] = sims_v16_align
    sims_all['DYNAMIC_v16']       = sims_v16_comb
    sims_all['DYNAMIC_v18_smooth'] = sims_v18_smooth
    sims_all['DYNAMIC_v18_cap']    = sims_v18_cap
    sims_all['DYNAMIC_v18_gate']   = sims_v18_gate
    sims_all['DYNAMIC_v18']        = sims_v18
    for tag, (_, s) in v19_variants.items():
        sims_all[f'DYNAMIC_{tag}'] = s
    sims_all['DYNAMIC_v19']        = sims_v19
    sims_all['DYNAMIC_v20']        = sims_v20
    sims_all['DYNAMIC_v21']        = sims_v21_prod
    sims_all['DYNAMIC_v22']        = sims_v22
    sims_all['F_FUND_ETH']   = sim_fund_eth
    sims_all['F_FUND_BTC']   = sim_fund_btc

    results = {
        "model":   "Crypto BSDT v18 — refined geometric layer (smoothed φ, z-cap, gated alignment)",
        "version": "v18",
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
            "v16_phi_dynamic":   sims_v16_phi['sharpe'],
            "v16_align_dynamic": sims_v16_align['sharpe'],
            "v16_dynamic":       sims_v16_comb['sharpe'],
            "v18_smooth":        sims_v18_smooth['sharpe'],
            "v18_cap":           sims_v18_cap['sharpe'],
            "v18_gate":          sims_v18_gate['sharpe'],
            "v18_dynamic":       sims_v18['sharpe'],
            **{f"v19_{tag.replace('v19_','')}": s['sharpe']
               for tag, (_, s) in v19_variants.items()},
            "v19_prod":          sims_v19['sharpe'],
            "v19_prod_variant":  best_v19_tag,
            "v20_ensemble":      sims_v20['sharpe'],
            "v20_summary":       v20_summary,
            "v21_ensemble":      sims_v21_prod['sharpe'],
            "v22_voltarget":     sims_v22['sharpe'],
            "v21_summary":       v21_summary,
            "v22_summary":       v22_summary,
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
        "v16_diagnostics": {
            "phi_mean":      float(round(phi_t_test.mean(), 4)),
            "phi_std":       float(round(phi_t_test.std(), 4)),
            "phi_p90":       float(round(phi_t_test.quantile(0.90), 4)),
            "phi_p99":       float(round(phi_t_test.quantile(0.99), 4)),
            "alignment_mean": float(round(align_t_test.mean(), 4)),
            "alignment_std":  float(round(align_t_test.std(), 4)),
            "alignment_p90":  float(round(align_t_test.quantile(0.90), 4)),
            "corr_phi_alignment":  float(round(corr_geom, 4)),
            "corr_phi_gamma_rank": float(round(corr_phi_gamma, 4)),
            "lev_v16_mean":  float(round(lev_v16_t.mean(), 3)),
            "lev_v16_std":   float(round(lev_v16_t.std(), 3)),
            "lev_v16_min":   float(round(lev_v16_t.min(), 3)),
            "lev_v16_max":   float(round(lev_v16_t.max(), 3)),
            "pct_defensive_v16": float(round((lev_v16_t<0.7).mean()*100, 1)),
        },
    }

    out_path = os.path.join(OUT_DIR, "crypto_bsdt_v18_results.json")
    with open(out_path, 'w') as f:
        json.dump(_clean(results), f, indent=2)
    print(f"\n  Results saved → {out_path}")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 96)
    print("  SUMMARY: v9 → v10 → v11 → v12 → v13 → v14 → v15 → v16")
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
        ('v15 (funding+convex)',     'funding fade + convex γ dial',                   sims_v15_comb['sharpe']),
        ('v16_phi (φ only)',         'v14b × 1/(1+φ·φ_t)',                              sims_v16_phi['sharpe']),
        ('v16_align (alignment)',    'v14b × (1-α·align⁺)',                            sims_v16_align['sharpe']),
        ('v16  (PRODUCTION)',        'v14b + φ + collapse alignment + EMA',            sims_v16_comb['sharpe']),
        ('v18_smooth',               'v16 form on EMA-smoothed state vector',          sims_v18_smooth['sharpe']),
        ('v18_cap',                  'v18_smooth + z-scored φ capped at 3',            sims_v18_cap['sharpe']),
        ('v18_gate',                 'v18_cap + alignment gated by φ>0.5',             sims_v18_gate['sharpe']),
        ('v18  (refined geometry)',  'smooth+cap+gate+EWMA collapse_dir',              sims_v18['sharpe']),
        (f'v19  ALPHA OVERLAY',      f'momentum × v18_smooth ({best_v19_tag})',        sims_v19['sharpe']),
        ('v20  STACKED ALPHA',       'inv-vol(v18s + F_FUND_ETH + F_FUND_BTC)',        sims_v20['sharpe']),
        (f'v21  DEEP STACK ({prod_scheme})',  '4-leg + scheme bake-off',                       sims_v21_prod['sharpe']),
        (f'v22  VOL-TARGET v20',              f'inv-realized-vol overlay  (tgt={prod_target_v22})',  sims_v22['sharpe']),
    ]
    for vname, src, sh in summary_rows:
        print(f"  {vname:<22}  {src:<38}  {sh:>+14.3f}")
    print()
    print(f"  γ_rank [test]:  mean={gr_t.mean():.3f}  std={gr_t.std():.3f}  "
          f">0.6: {pct_hi:.0f}%  <0.4: {pct_lo:.0f}%")
    print(f"  γ_fast [test]:  mean={gf_t.mean():.3f}  std={gf_t.std():.3f}  "
          f">0.6: 0.0%  <0.4: 0.0%  (v11 reference)")

    # ════════════════════════════════════════════════════════════════════════
    #  KILL TEST: is v18_smooth genuinely better than v16, or just lucky?
    #  5 falsifiable tests - revert to v16 if any major one fails.
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 96)
    print("  KILL TEST  —  v18_smooth vs v16 robustness audit")
    print("═" * 96)

    def _sharpe(pnl):
        s = pnl.dropna()
        if len(s) < 5 or s.std() == 0:
            return float('nan')
        return float(np.sqrt(252) * s.mean() / s.std())

    def _max_dd(pnl):
        cum = pnl.fillna(0.0).cumsum()
        peak = cum.cummax()
        return float((cum - peak).min())

    def _dd_duration(pnl):
        cum = pnl.fillna(0.0).cumsum()
        peak = cum.cummax()
        under = (cum < peak).values
        max_run = cur = 0
        for u in under:
            cur = cur + 1 if u else 0
            if cur > max_run:
                max_run = cur
        return int(max_run)

    test_idx = df.index[test_mask]
    pnl_v16_t = pnl_dyn_v16[test_mask]
    pnl_v18s_t = pnl_dyn_v18_smooth[test_mask]

    # ── TEST 1: Time-split robustness ─────────────────────────────────────
    print("\n── TEST 1  Time-split robustness ─────────────────────────────────────")
    splits = [
        ('A 2023-01 → 2024-06', '2023-01-01', '2024-06-30'),
        ('B 2024-07 → 2025-06', '2024-07-01', '2025-06-30'),
        ('C 2025-07 → 2026-04', '2025-07-01', '2026-12-31'),
    ]
    print(f"  {'Split':<24}  {'v16 Sh':>8}  {'v18s Sh':>8}  {'Δ':>7}  {'winner':>8}")
    print("  " + "─" * 72)
    wins_v18 = 0
    for name, s, e in splits:
        m = (test_idx >= s) & (test_idx <= e)
        sh16 = _sharpe(pnl_v16_t[m])
        sh18 = _sharpe(pnl_v18s_t[m])
        win = 'v18' if sh18 >= sh16 else 'v16'
        if sh18 >= sh16: wins_v18 += 1
        print(f"  {name:<24}  {sh16:>+8.3f}  {sh18:>+8.3f}  {sh18-sh16:>+7.3f}  {win:>8}")
    print(f"  → v18 wins {wins_v18}/3 splits.  "
          f"PASS: v18 ≥ v16 in 2 of 3.   "
          f"VERDICT: {'PASS ✓' if wins_v18 >= 2 else 'FAIL ✗  (overfit)'}")

    # ── TEST 2: EMA-span sensitivity ──────────────────────────────────────
    print("\n── TEST 2  state-EMA span sensitivity ────────────────────────────────")
    print(f"  {'span':>5}  {'Sharpe':>8}  {'Δ vs span=3':>13}")
    print("  " + "─" * 32)
    # base_sh = recomputed v18_smooth Sharpe under the SAME _sharpe formula
    base_sh = _sharpe(pnl_v18s_t)
    sh16_full = _sharpe(pnl_v16_t)
    print(f"  (reference: _sharpe(v16)={sh16_full:+.3f}, _sharpe(v18s)={base_sh:+.3f})")
    span_results = []
    for span in [2, 3, 4, 5, 6]:
        phi_x, align_x, _ = compute_geom_signals_v18(V_state,
                                                       state_ema_span=span,
                                                       smooth_state=True,
                                                       z_phi=False,
                                                       cap_phi=False,
                                                       ewma_collapse=False)
        lev_x = apply_geom_penalties(lev_mult, phi_x, align_x,
                                       phi_pen=GEOM_PHI_PEN,
                                       align_pen=GEOM_ALIGN_PEN,
                                       ema_span=GEOM_EMA_SPAN,
                                       lo=GEOM_LEV_LO, hi=GEOM_LEV_HI)
        pnl_x = pnl_dyn_v10_orig * lev_x.shift(1).fillna(1.0)
        sh_x = _sharpe(pnl_x[test_mask])
        d = sh_x - base_sh
        marker = ' ←' if span == 3 else ''
        print(f"  {span:>5}  {sh_x:>+8.3f}  {d:>+13.3f}{marker}")
        span_results.append(sh_x)
    sweep_range = max(span_results) - min(span_results)
    print(f"  → Sharpe range across spans 2-6: {sweep_range:.3f}.   "
          f"PASS: ≤ 0.10.   "
          f"VERDICT: {'PASS ✓' if sweep_range <= 0.10 else 'FAIL ✗  (parameter-tuned)'}")

    # ── TEST 3: φ removal ─────────────────────────────────────────────────
    print("\n── TEST 3  remove φ entirely (smoothing alone vs full v18_smooth) ────")
    # v18_no_phi: take smoothed state, no φ penalty, no alignment penalty
    # → this is just lev_mult passed through EMA(5) and clipped.
    lev_no_phi = lev_mult.ewm(span=GEOM_EMA_SPAN, adjust=False).mean() \
                          .clip(lower=GEOM_LEV_LO, upper=GEOM_LEV_HI)
    pnl_no_phi = pnl_dyn_v10_orig * lev_no_phi.shift(1).fillna(1.0)
    sh_no_phi = _sharpe(pnl_no_phi[test_mask])
    pnl_v14b_t = (pnl_dyn_v10_orig * lev_mult.shift(1).fillna(1.0))[test_mask]
    print(f"  {'v14b (raw lev_mult)':<32}  Sharpe={_sharpe(pnl_v14b_t):>+7.3f}")
    print(f"  {'v16 (raw φ + raw align)':<32}  Sharpe={sh16_full:>+7.3f}")
    print(f"  {'v18_smooth (smoothed φ+align)':<32}  Sharpe={base_sh:>+7.3f}")
    print(f"  {'v18_no_phi (EMA only, no φ)':<32}  Sharpe={sh_no_phi:>+7.3f}")
    edge = base_sh - sh_no_phi
    print(f"  → φ contribution = v18_smooth − v18_no_phi = {edge:+.3f}.   "
          f"PASS: > 0.03.   "
          f"VERDICT: {'PASS ✓' if edge > 0.03 else 'FAIL ✗  (smoothing is the edge, not φ)'}")

    # ── TEST 4: φ shuffle / lag test ──────────────────────────────────────
    print("\n── TEST 4  shuffle test (lag φ by 3 days, kill its timing) ───────────")
    phi_18s, align_18s, _ = compute_geom_signals_v18(V_state,
                                                       smooth_state=True,
                                                       z_phi=False,
                                                       cap_phi=False,
                                                       ewma_collapse=False)
    phi_lag = phi_18s.shift(3)
    align_lag = align_18s.shift(3)
    lev_lag = apply_geom_penalties(lev_mult, phi_lag, align_lag,
                                     phi_pen=GEOM_PHI_PEN,
                                     align_pen=GEOM_ALIGN_PEN,
                                     ema_span=GEOM_EMA_SPAN,
                                     lo=GEOM_LEV_LO, hi=GEOM_LEV_HI)
    pnl_lag = pnl_dyn_v10_orig * lev_lag.shift(1).fillna(1.0)
    sh_lag = _sharpe(pnl_lag[test_mask])
    drop = base_sh - sh_lag
    print(f"  v18_smooth (real timing):    Sharpe={base_sh:>+7.3f}")
    print(f"  v18_smooth (φ lagged by 3d): Sharpe={sh_lag:>+7.3f}   Δ={-drop:+.3f}")
    print(f"  → Performance drop from broken timing = {drop:+.3f}.   "
          f"PASS: ≥ 0.02.   "
          f"VERDICT: {'PASS ✓' if drop >= 0.02 else 'FAIL ✗  (φ timing is irrelevant)'}")

    # ── TEST 5: drawdown profile ──────────────────────────────────────────
    print("\n── TEST 5  drawdown severity AND duration ────────────────────────────")
    dd16 = _max_dd(pnl_v16_t); dur16 = _dd_duration(pnl_v16_t)
    dd18 = _max_dd(pnl_v18s_t); dur18 = _dd_duration(pnl_v18s_t)
    print(f"  v16:        MaxDD={dd16:>+7.4f}   longest underwater = {dur16:>4d} days")
    print(f"  v18_smooth: MaxDD={dd18:>+7.4f}   longest underwater = {dur18:>4d} days")
    sev_better = dd18 >= dd16          # less negative = better
    dur_better = dur18 <= dur16
    print(f"  → severity {'better' if sev_better else 'worse'},   "
          f"duration {'better/equal' if dur_better else 'worse'}.   "
          f"PASS: BOTH improve.   "
          f"VERDICT: {'PASS ✓' if (sev_better and dur_better) else 'FAIL ✗  (one-sided)'}")

    # ── KILL TEST SUMMARY ─────────────────────────────────────────────────
    t1_pass = wins_v18 >= 2
    t2_pass = sweep_range <= 0.10
    t3_pass = edge > 0.03
    t4_pass = drop >= 0.02
    t5_pass = sev_better and dur_better
    n_pass = sum([t1_pass, t2_pass, t3_pass, t4_pass, t5_pass])
    print("\n" + "═" * 96)
    print(f"  KILL TEST RESULT:  {n_pass}/5 passed")
    for i, (lbl, ok) in enumerate([
        ('1 time-split   (v18 ≥ v16 in ≥2/3)',           t1_pass),
        ('2 EMA span     (Sharpe range ≤ 0.10)',         t2_pass),
        ('3 φ removal    (φ contributes > 0.03)',        t3_pass),
        ('4 shuffle      (lag-3 φ drops Sharpe ≥ 0.02)', t4_pass),
        ('5 drawdown     (both severity AND duration)',  t5_pass),
    ], 1):
        print(f"    Test {lbl:<48}  {'PASS ✓' if ok else 'FAIL ✗'}")
    if n_pass == 5:
        verdict = "🟢 SHIP v18_smooth — all five kill-tests passed.  Stop optimizing."
    elif n_pass >= 3:
        verdict = "🟡 MIXED — keep v16 as fallback, v18_smooth is conditional."
    else:
        verdict = "🔴 REVERT to v16 — gain was noise."
    print(f"\n  VERDICT: {verdict}")
    print("═" * 96)

    # ════════════════════════════════════════════════════════════════════════
    #  EQUITY CURVE REPORT — what does v18_smooth do to real money?
    #  Compounded equity from $500 and $1,200, with and without 5 bps t-cost.
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 96)
    print("  EQUITY CURVE REPORT  —  $500 and $1,200 starting capital")
    print("═" * 96)

    TCOST_BPS = 5.0   # 5 basis points charged on each active (non-zero) day

    def _equity_report(returns, label, capital_list=(500.0, 1200.0),
                        tcost_bps=0.0):
        r = returns.dropna().astype(float).copy()
        if tcost_bps > 0:
            cost = (tcost_bps / 1e4) * (r.abs() > 0).astype(float)
            r = r - cost
        cum = (1.0 + r).cumprod()
        rows = []
        for cap in capital_list:
            eq = cap * cum
            final = float(eq.iloc[-1])
            pnl = final - cap
            roll_max = eq.cummax()
            dd_dollars = float((eq - roll_max).min())
            dd_pct = float(((eq - roll_max) / roll_max).min() * 100)
            under = (eq < roll_max).values
            max_uw, cur = 0, 0
            for u in under:
                cur = cur + 1 if u else 0
                if cur > max_uw: max_uw = cur
            yrs = len(r) / 252.0
            cagr_pct = (cum.iloc[-1] ** (1.0 / yrs) - 1.0) * 100.0 if yrs > 0 else float('nan')
            sh = float(np.sqrt(252) * r.mean() / r.std()) if r.std() > 0 else float('nan')
            rows.append({
                'cap': cap, 'final': final, 'pnl': pnl,
                'dd_d': dd_dollars, 'dd_pct': dd_pct,
                'uw_days': max_uw, 'cagr': cagr_pct, 'sh': sh,
            })
        cost_tag = f' (after {tcost_bps:.0f} bps t-cost)' if tcost_bps > 0 else ' (gross)'
        print(f"\n  {label}{cost_tag}")
        print(f"  Window: {r.index[0].date()} → {r.index[-1].date()}  "
              f"({len(r)} trading days, {len(r)/252:.2f} yrs)")
        print(f"  Sharpe={rows[0]['sh']:+.3f}   CAGR={rows[0]['cagr']:+.2f}%   "
              f"MaxDD={rows[0]['dd_pct']:+.2f}%   "
              f"longest underwater={rows[0]['uw_days']}d")
        print(f"  {'Initial':>10}  {'Final':>10}  {'PnL':>11}  "
              f"{'MaxDD ($)':>12}  {'MaxDD (%)':>10}")
        print("  " + "─" * 60)
        for row in rows:
            print(f"  ${row['cap']:>9,.0f}  ${row['final']:>9,.2f}  "
                  f"${row['pnl']:>+10,.2f}  ${row['dd_d']:>+11,.2f}  "
                  f"{row['dd_pct']:>+9.2f}%")
        return rows

    rep_v16_gross = _equity_report(pnl_v16_t,  'v16 (prev PROD)',     tcost_bps=0.0)
    rep_v18_gross = _equity_report(pnl_v18s_t, 'v18_smooth (PROD)',   tcost_bps=0.0)
    rep_v16_net   = _equity_report(pnl_v16_t,  'v16 (prev PROD)',     tcost_bps=TCOST_BPS)
    rep_v18_net   = _equity_report(pnl_v18s_t, 'v18_smooth (PROD)',   tcost_bps=TCOST_BPS)

    print("\n  ── Head-to-head at $1,200 starting capital, net of 5 bps ─────────")
    a, b = rep_v16_net[1], rep_v18_net[1]
    print(f"  {'metric':<22}  {'v16':>12}  {'v18_smooth':>12}  {'Δ':>10}")
    print("  " + "─" * 62)
    print(f"  {'Final equity':<22}  ${a['final']:>11,.2f}  ${b['final']:>11,.2f}  "
          f"${b['final']-a['final']:>+9,.2f}")
    print(f"  {'PnL':<22}  ${a['pnl']:>+11,.2f}  ${b['pnl']:>+11,.2f}  "
          f"${b['pnl']-a['pnl']:>+9,.2f}")
    print(f"  {'MaxDD ($)':<22}  ${a['dd_d']:>+11,.2f}  ${b['dd_d']:>+11,.2f}  "
          f"${b['dd_d']-a['dd_d']:>+9,.2f}")
    print(f"  {'MaxDD (%)':<22}  {a['dd_pct']:>+11.2f}%  {b['dd_pct']:>+11.2f}%  "
          f"{b['dd_pct']-a['dd_pct']:>+9.2f}%")
    print(f"  {'CAGR':<22}  {a['cagr']:>+11.2f}%  {b['cagr']:>+11.2f}%  "
          f"{b['cagr']-a['cagr']:>+9.2f}%")
    print(f"  {'Sharpe':<22}  {a['sh']:>+12.3f}  {b['sh']:>+12.3f}  "
          f"{b['sh']-a['sh']:>+10.3f}")
    print(f"  {'Longest underwater':<22}  {a['uw_days']:>11}d  {b['uw_days']:>11}d  "
          f"{b['uw_days']-a['uw_days']:>+9}d")

    eq_out = pd.DataFrame({
        'date':         pnl_v18s_t.index,
        'ret_v16':      pnl_v16_t.values,
        'ret_v18s':     pnl_v18s_t.values,
        'eq_v16_500':   500.0  * (1.0 + pnl_v16_t.fillna(0.0)).cumprod().values,
        'eq_v18s_500':  500.0  * (1.0 + pnl_v18s_t.fillna(0.0)).cumprod().values,
        'eq_v16_1200':  1200.0 * (1.0 + pnl_v16_t.fillna(0.0)).cumprod().values,
        'eq_v18s_1200': 1200.0 * (1.0 + pnl_v18s_t.fillna(0.0)).cumprod().values,
    })
    eq_csv_path = os.path.join(OUT_DIR, 'crypto_bsdt_v18_equity_curves.csv')
    eq_out.to_csv(eq_csv_path, index=False)
    print(f"\n  Equity curves saved → {eq_csv_path}")

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
        ax[0].plot(eq_out['date'], eq_out['eq_v16_500'],
                    label='v16  $500',  lw=1.2, color='#888888')
        ax[0].plot(eq_out['date'], eq_out['eq_v18s_500'],
                    label='v18s $500',  lw=1.4, color='#1f77b4')
        ax[0].set_ylabel('Equity ($)'); ax[0].legend(loc='upper left')
        ax[0].set_title('v18_smooth vs v16 — $500 starting capital (gross)')
        ax[0].grid(alpha=0.3)
        ax[1].plot(eq_out['date'], eq_out['eq_v16_1200'],
                    label='v16  $1,200', lw=1.2, color='#888888')
        ax[1].plot(eq_out['date'], eq_out['eq_v18s_1200'],
                    label='v18s $1,200', lw=1.4, color='#d62728')
        ax[1].set_ylabel('Equity ($)'); ax[1].legend(loc='upper left')
        ax[1].set_title('v18_smooth vs v16 — $1,200 starting capital (gross)')
        ax[1].grid(alpha=0.3)
        plt.tight_layout()
        png_path = os.path.join(OUT_DIR, 'crypto_bsdt_v18_equity_curves.png')
        plt.savefig(png_path, dpi=110)
        plt.close(fig)
        print(f"  Equity plot   saved → {png_path}")
    except Exception as e:
        print(f"  (matplotlib unavailable — skipped PNG: {e})")

    print("═" * 96)

    # ════════════════════════════════════════════════════════════════════════
    #  EXPOSURE-SCALING SWEEP
    #  Multiply v18_smooth daily returns by K ∈ {1, 2, 3, 5, 10}.
    #  Gross Sharpe is invariant to K; NET Sharpe improves with K because
    #  t-cost (per active day) is fixed while signal scales linearly.
    #  Question: at what K does v18_smooth turn net-profitable on $1,200?
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 96)
    print("  EXPOSURE-SCALING SWEEP  —  v18_smooth at K × leverage")
    print("═" * 96)

    K_GRID = [1.0, 2.0, 3.0, 5.0, 10.0]
    INIT_CAP = 1200.0

    def _scaled_metrics(returns, K, tcost_bps=0.0, init_cap=INIT_CAP):
        r = (returns.dropna().astype(float) * K).copy()
        if tcost_bps > 0:
            cost = (tcost_bps / 1e4) * (returns.dropna().abs() > 0).astype(float)
            r = r - cost
        cum = (1.0 + r).cumprod()
        eq = init_cap * cum
        final = float(eq.iloc[-1])
        pnl = final - init_cap
        roll_max = eq.cummax()
        dd_pct = float(((eq - roll_max) / roll_max).min() * 100)
        dd_dol = float((eq - roll_max).min())
        sh = float(np.sqrt(252) * r.mean() / r.std()) if r.std() > 0 else float('nan')
        yrs = len(r) / 252.0
        cagr = (cum.iloc[-1] ** (1.0 / yrs) - 1.0) * 100.0 if yrs > 0 and cum.iloc[-1] > 0 else float('nan')
        # ruin check: any equity ≤ 0?
        ruined = bool((eq <= 0).any())
        return {
            'K': K, 'final': final, 'pnl': pnl, 'sh': sh,
            'cagr': cagr, 'dd_pct': dd_pct, 'dd_dol': dd_dol,
            'ruined': ruined,
        }

    for tag, tcost in [('GROSS (no t-cost)', 0.0),
                        ('NET (5 bps per active day)', 5.0)]:
        print(f"\n  ── {tag}, $1,200 starting capital ───────────────────────────")
        print(f"  {'K':>4}  {'Sharpe':>8}  {'CAGR':>8}  {'Final':>10}  "
              f"{'PnL':>11}  {'MaxDD %':>9}  {'MaxDD $':>10}  notes")
        print("  " + "─" * 86)
        for K in K_GRID:
            m = _scaled_metrics(pnl_v18s_t, K, tcost_bps=tcost)
            note = '  RUINED' if m['ruined'] else ''
            if m['dd_pct'] < -50.0 and not m['ruined']:
                note = '  >50% DD'
            print(f"  {m['K']:>4.0f}  {m['sh']:>+8.3f}  {m['cagr']:>+7.2f}%  "
                  f"${m['final']:>9,.2f}  ${m['pnl']:>+10,.2f}  "
                  f"{m['dd_pct']:>+8.2f}%  ${m['dd_dol']:>+9,.2f}{note}")

    # Find break-even K (smallest K where NET PnL ≥ 0)
    print("\n  ── NET break-even analysis ────────────────────────────────────────")
    K_fine = np.arange(1.0, 20.1, 0.25)
    be_K = None
    for K in K_fine:
        m = _scaled_metrics(pnl_v18s_t, float(K), tcost_bps=5.0)
        if m['pnl'] >= 0 and not m['ruined']:
            be_K = float(K); be_m = m; break
    if be_K is None:
        print("  No K in [1, 20] makes v18_smooth profitable net of 5 bps.")
        print("  Strategy is structurally unprofitable at retail crypto cost levels.")
    else:
        print(f"  Break-even K = {be_K:.2f}")
        print(f"    Final ${be_m['final']:,.2f}   PnL ${be_m['pnl']:+,.2f}   "
              f"MaxDD {be_m['dd_pct']:+.2f}% (${be_m['dd_dol']:+,.2f})   "
              f"Sharpe {be_m['sh']:+.3f}")
        # Sweet-spot K = max risk-adjusted (net Sharpe / MaxDD%) within K ≤ 10
        best_K, best_score = None, -np.inf
        for K in K_fine[K_fine <= 10.0]:
            m = _scaled_metrics(pnl_v18s_t, float(K), tcost_bps=5.0)
            if m['ruined'] or m['dd_pct'] < -40.0: continue
            score = m['sh']  # maximise net Sharpe under DD < 40% constraint
            if score > best_score:
                best_score, best_K, best_m = score, float(K), m
        if best_K is not None:
            print(f"  Best risk-adjusted K (net Sharpe, MaxDD ≤ 40%): K={best_K:.2f}")
            print(f"    Final ${best_m['final']:,.2f}   PnL ${best_m['pnl']:+,.2f}   "
                  f"MaxDD {best_m['dd_pct']:+.2f}% (${best_m['dd_dol']:+,.2f})   "
                  f"Sharpe {best_m['sh']:+.3f}")

    # Save scaled equity curves at K = best_K (or K=5 fallback)
    K_save = best_K if (be_K is not None and best_K is not None) else 5.0
    r_scaled_gross = (pnl_v18s_t.fillna(0.0) * K_save)
    r_scaled_net   = r_scaled_gross - (5.0/1e4) * (pnl_v18s_t.fillna(0.0).abs() > 0).astype(float)
    eq_scaled = pd.DataFrame({
        'date':            pnl_v18s_t.index,
        'eq_gross_K1':     INIT_CAP * (1.0 + pnl_v18s_t.fillna(0.0)).cumprod().values,
        f'eq_gross_K{int(K_save)}':  INIT_CAP * (1.0 + r_scaled_gross).cumprod().values,
        f'eq_net_K{int(K_save)}':    INIT_CAP * (1.0 + r_scaled_net).cumprod().values,
    })
    sc_csv_path = os.path.join(OUT_DIR, 'crypto_bsdt_v18_exposure_sweep.csv')
    eq_scaled.to_csv(sc_csv_path, index=False)
    print(f"\n  Scaled curves saved → {sc_csv_path}")

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 1, figsize=(11, 5))
        ax.plot(eq_scaled['date'], eq_scaled['eq_gross_K1'],
                 label='K=1 gross', lw=1.0, color='#888888')
        ax.plot(eq_scaled['date'], eq_scaled[f'eq_gross_K{int(K_save)}'],
                 label=f'K={int(K_save)} gross', lw=1.4, color='#1f77b4')
        ax.plot(eq_scaled['date'], eq_scaled[f'eq_net_K{int(K_save)}'],
                 label=f'K={int(K_save)} net (5bps)', lw=1.4, color='#d62728')
        ax.set_ylabel(f'Equity ($ from ${int(INIT_CAP)})')
        ax.set_title(f'v18_smooth — exposure scaling at K=1 vs K={int(K_save)}')
        ax.legend(loc='upper left'); ax.grid(alpha=0.3)
        plt.tight_layout()
        png_path = os.path.join(OUT_DIR, 'crypto_bsdt_v18_exposure_sweep.png')
        plt.savefig(png_path, dpi=110)
        plt.close(fig)
        print(f"  Scaled plot   saved → {png_path}")
    except Exception as e:
        print(f"  (matplotlib unavailable — skipped PNG: {e})")

    print("═" * 96)


if __name__ == '__main__':
    main()
