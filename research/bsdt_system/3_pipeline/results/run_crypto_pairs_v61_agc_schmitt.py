"""
Crypto BSDT — v61: AGC-Normalised Floating Gate (Coupling Cap + Auto-Gain Control)
====================================================================================
Problem being solved
--------------------
v59 and v60 both FAIL the alpha-sensitivity test (max drop 0.33–0.37 vs bar 0.15)
because the Schmitt thresholds G_hi=0.32/T_hi=0.31 were hand-calibrated for
α=0.85.  The root cause is that Var[Q_G] ∝ (1−α)/(1+α): changing α shifts the
entire charge distribution, so a fixed threshold fires at materially different
percentiles.

Circuit diagnosis
-----------------
The floating gate output Q_G has an **α-dependent DC level and variance**:

    DC:       E[Q_G] = E[a_G] / (1−α)          → rises with α
    Variance: Var[Q_G] = Var[a_G] / (1−α²)     → rises with α

A fixed threshold is like a voltage comparator with no reference tracking.
The classic solutions from analog design:

  ┌─────────────────────────────────────────────────────────┐
  │  Floating gate → [Coupling Cap] → [AGC Amp] → Schmitt  │
  └─────────────────────────────────────────────────────────┘

  1. Coupling capacitor  — blocks DC level  (removes E[Q_G] dependence on α)
  2. AGC amplifier       — normalises amplitude  (removes Var[Q_G] dependence on α)

In code, both are achieved with a rolling z-score using a FIXED normalisation
window (AGC_SPAN=168 bars = 1 week) that is INDEPENDENT of α:

    Q_G_z(t) = (Q_G(t) − EMA(Q_G, 168)) / EMA_std(Q_G, 168)

    E[Q_G_z] ≈ 0       for all α     (coupling cap removed DC)
    Var[Q_G_z] ≈ 1     for all α     (AGC normalised amplitude)

The Schmitt thresholds are then dimensionless z-score values that represent
fixed percentiles of the distribution regardless of α.

Z-score threshold design
-------------------------
Three variants correspond to different selectivity levels:

  Loose  (G_hi=−1.0, G_lo=−1.5): fires on ~84% of bars — preserves v59 behaviour
  Mid    (G_hi= 0.0, G_lo=−0.5): fires on ~50% of bars — neutral/above-mean regime
  Surge  (G_hi=+1.0, G_lo=+0.5): fires on ~16% of bars — genuine surges only

All three have α-independent firing rates by construction.

Partial credit in z-score space
---------------------------------
v59: phase = 1 + pc × (Q_G / g_hi)   — alpha-dependent (Q_G scale ∝ 1/(1−α))
v61: phase = 1 + pc × clip(Q_G_z, 0, 1)
              — fires only on POSITIVE deviations (Q_G above its recent mean)
              — alpha-independent by construction
              — saturates at full PARTIAL_CREDIT at z ≥ 1σ

Tests
------
  TEST 1 — OOS split (pass: H2 ≥ 3.60)
  TEST 2 — Alpha sensitivity  (pass: max |drop| < 0.15) ← KEY TEST
             α ∈ {0.75, 0.80, 0.85, 0.90, 0.95}
  TEST 3 — Threshold sensitivity (pass: max |drop| < 0.15)
             z-threshold perturbs: +0.25σ, −0.25σ, band ×1.5, band ×0.5
  TEST 4 — rv stress on v58 reference (apples-to-apples)
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

from collapse_geometry import MasterOperator
from run_crypto_pairs_v38_lambda_norm import compute_lambda_features
from run_crypto_pairs_v37_price_prediction import compute_price_prediction_signals
from run_crypto_pairs_v36_intraday_bsdt import (
    CALIB_BARS, BPD,
    build_intraday_state_panel, calibrate_intraday_engine,
    compute_intraday_signals, _stats,
)
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
    build_1h_df, fetch_and_prepare, fetch_binance_funding,
    add_cross_market_features, add_leverage_features,
    build_daily_positions, upsample_daily_to_1h_pnl,
    compute_1h_strategies, compute_quality, assemble_combined,
)
from run_crypto_pairs_v39_four_channels import (
    FIRE_PERCENTILE, calibrate_firing_thresholds,
)
from run_crypto_pairs_v39b_k1_scaled import (
    PCA_K_B, calibrate_channel_means, compute_four_channel_signals_v39b,
)
import run_crypto_pairs_v34_full_combined as _v34mod

OUT_DIR_ = Path(OUT_DIR)

# ── cache helpers (unchanged) ────────────────────────────────────────────────
_CACHE_DIR   = Path(r'C:\amttp\data')
_CACHE_TTL_H = 72

def _make_cached_fetch(orig_fn):
    def _w(symbol, start, end, interval='1h'):
        p = _CACHE_DIR / f'klines_{symbol}_{interval}.pkl'
        if p.exists() and (time.time()-p.stat().st_mtime)/3600 < _CACHE_TTL_H:
            s = pd.read_pickle(str(p)); print(f'  {symbol} [CACHE]'); return s
        s = orig_fn(symbol, start, end, interval)
        if len(s) > 0: s.to_pickle(str(p))
        return s
    return _w

def _cached_fetch_and_prepare():
    p = _CACHE_DIR / 'daily_crypto_pairs.pkl'
    if p.exists() and (time.time()-p.stat().st_mtime)/3600 < _CACHE_TTL_H:
        return pd.read_pickle(str(p))
    df = fetch_and_prepare(); df.to_pickle(str(p)); return df

def _cached_add_cross_market(df):
    p = _CACHE_DIR / 'cross_market_df.pkl'
    if p.exists() and (time.time()-p.stat().st_mtime)/3600 < _CACHE_TTL_H:
        r = pd.read_pickle(str(p))
        if r.shape[0] == df.shape[0] and r.index[-1] == df.index[-1]:
            return r
    r = add_cross_market_features(df); r.to_pickle(str(p)); return r

def _cached_fetch_binance_funding():
    p = _CACHE_DIR / 'binance_funding.pkl'
    if p.exists() and (time.time()-p.stat().st_mtime)/3600 < _CACHE_TTL_H:
        import pickle as _pk
        with open(str(p), 'rb') as f: return _pk.load(f)
    fund = fetch_binance_funding(symbols=['ETHUSDT','BTCUSDT'], start='2020-06-01')
    import pickle as _pk
    with open(str(p), 'wb') as f: _pk.dump(fund, f)
    return fund

# ── frozen constants (from v58 champion) ─────────────────────────────────────
CLIP            = 6.0
GH_TH           = 5.0
GH_TL = GL_TH = GL_TL = -1.0
N_OPT           = 8
T_THRESH_BASE   = 0.41
G_THRESH_BASE   = 0.45
G_BOOST_THRESH  = 0.45
CHAMPION_BOOST  = 0.65
A_FIRE_THRESH   = 0.65
K_G             = 0.10

# ── v59 ST-FGRC constants (for reference configs) ────────────────────────────
ALPHA_FG        = 0.85
G_SCHMITT_HI    = 0.32
G_SCHMITT_LO    = 0.26
T_SCHMITT_HI    = 0.31
T_SCHMITT_LO    = 0.25
PARTIAL_CREDIT  = 0.30

# ── v61 AGC constants ─────────────────────────────────────────────────────────
# Independent of alpha — a WEEK of hourly bars for DC/std tracking.
# Longer window → more stable DC reference; shorter → more adaptive.
# 168 is the natural cycle (1 week ≈ fundamental market periodicity).
AGC_SPAN = 168

# Z-score thresholds — dimensionless percentile references.
# These are the SAME regardless of alpha because the AGC normalises Q_G.
#
#  p(z > -1.0) = 84%   →  LOOSE fires 84% of ticks  (approx v59 firing rate)
#  p(z >  0.0) = 50%   →  MID   fires 50% of ticks
#  p(z > +1.0) = 16%   →  SURGE fires 16% of ticks (genuine above-1σ events)
#
# Hysteresis band ≈ 0.5σ in all cases (same absolute width regardless of threshold)
G_Z_HI_LOOSE =  -1.0;   G_Z_LO_LOOSE = -1.5   # 84% / 93%  (gate mostly ON)
T_Z_HI_LOOSE =  -1.0;   T_Z_LO_LOOSE = -1.5

G_Z_HI_MID   =   0.0;   G_Z_LO_MID   = -0.5   # 50% / 69%  (above/near mean)
T_Z_HI_MID   =   0.0;   T_Z_LO_MID   = -0.5

G_Z_HI_SURGE =  +1.0;   G_Z_LO_SURGE = +0.5   # 16% / 31%  (genuine surges)
T_Z_HI_SURGE =  +1.0;   T_Z_LO_SURGE = +0.5

V58_SHARPE = 4.0362
OOS_SPLIT  = '2025-01-01'


# ── v58 helpers (verbatim for reference) ─────────────────────────────────────

def _realized_vol(df_1h: pd.DataFrame, ema_span: int = 1) -> pd.Series:
    rv      = df_1h['ret_eth'].rolling(168, min_periods=24).std()
    rv_mean = rv.rolling(1000, min_periods=100).mean()
    rv_norm = (rv / rv_mean.replace(0, np.nan)).fillna(1.0)
    if ema_span > 1:
        rv_norm = rv_norm.ewm(span=ema_span, adjust=False).mean()
    return rv_norm.shift(1).fillna(1.0)

def _dynamic_gth(rv_norm: pd.Series, lo: float = -1.0) -> pd.Series:
    adj = K_G * (1.0 - rv_norm)
    if lo > -0.5:
        adj = adj.clip(lo, 0.10)
    return (G_THRESH_BASE * (1.0 + adj)).clip(0.20, 0.70)

def _build_pnl_v58(base, sv36, lf, s4, rv_norm, lo) -> pd.Series:
    idx  = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lf.reindex(idx,   method='ffill').fillna(0.5)
    s4   = s4.reindex(idx,   method='ffill').fillna(0.0)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam, 0.0, 1.0) * (0.75 + 0.5 * lp)
    gth  = _dynamic_gth(rv_norm.reindex(idx, method='ffill').fillna(1.0), lo)
    a_G  = s4['a_G']; a_A = s4['a_A']; a_T = s4['a_T']
    G_mem = a_G.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    T_mem = a_T.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    fired = a_A.shift(1).fillna(0.0) > A_FIRE_THRESH
    q_GH_TH = (fired & (G_mem > gth)  & (T_mem > T_THRESH_BASE)).astype(float)
    q_GH_TL = (fired & (G_mem > gth)  & (T_mem <= T_THRESH_BASE)).astype(float)
    q_GL_TH = (fired & (G_mem <= gth) & (T_mem > T_THRESH_BASE)).astype(float)
    q_GL_TL = (fired & (G_mem <= gth) & (T_mem <= T_THRESH_BASE)).astype(float)
    phase = (1.0 + GH_TH*q_GH_TH + GH_TL*q_GH_TL
                 + GL_TH*q_GL_TH + GL_TL*q_GL_TL).clip(0.05, CLIP)
    flag  = (a_G.shift(1).fillna(0.0) > G_BOOST_THRESH).astype(float)
    return base.fillna(0.0) * size * (1.0 + CHAMPION_BOOST * flag) * phase


# ── v59 reference (verbatim, for comparison) ─────────────────────────────────

def _float_gate_charge(a: np.ndarray, alpha: float) -> np.ndarray:
    """Raw (unnormalized) floating gate.  Q(t) = α·Q(t−1) + a(t−1)."""
    q = np.zeros(len(a), dtype=float)
    for t in range(1, len(a)):
        q[t] = alpha * q[t - 1] + a[t - 1]
    return q

def _schmitt_trigger(q: np.ndarray, hi: float, lo: float) -> np.ndarray:
    """Schmitt comparator: q>hi → SET, q<lo → RESET, else HOLD."""
    state = np.zeros(len(q), dtype=float)
    s = 0.0
    for t in range(len(q)):
        if q[t] > hi:
            s = 1.0
        elif q[t] < lo:
            s = 0.0
        state[t] = s
    return state

def _build_pnl_v59(base, sv36, lf, s4, alpha=ALPHA_FG,
                   schmitt_only=False,
                   g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                   t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO) -> pd.Series:
    """v59 ST-FGRC verbatim — for reference comparison only."""
    idx  = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lf.reindex(idx,   method='ffill').fillna(0.5)
    s4   = s4.reindex(idx,   method='ffill').fillna(0.0)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam.values, 0.0, 1.0) * (0.75 + 0.5 * lp.values)
    a_G  = s4['a_G'].values; a_A = s4['a_A'].values; a_T = s4['a_T'].values
    Q_G  = _float_gate_charge(a_G, alpha) * (1.0 - alpha)
    Q_T  = _float_gate_charge(a_T, alpha) * (1.0 - alpha)
    fire = np.zeros(len(a_A), dtype=bool)
    fire[1:] = a_A[:-1] > A_FIRE_THRESH
    if schmitt_only:
        G_mem = (pd.Series(a_G).rolling(N_OPT, min_periods=1).max()
                 .shift(1).fillna(0.0).values)
        GH = (G_mem > G_THRESH_BASE).astype(float)
        TH = _schmitt_trigger(Q_T, t_hi, t_lo)
        gh = GH > 0.5; th = TH > 0.5
        phase = (1.0 + GH_TH * (fire & gh & th).astype(float)
                     + GH_TL * (fire & gh & ~th).astype(float)
                     + GL_TH * (fire & ~gh & th).astype(float)
                     + GL_TL * (fire & ~gh & ~th).astype(float))
    else:
        GH = _schmitt_trigger(Q_G, g_hi, g_lo)
        TH = _schmitt_trigger(Q_T, t_hi, t_lo)
        gh = GH > 0.5; th = TH > 0.5
        phase = np.where(~fire, 1.0,
                np.where(gh & th, CLIP,
                np.where(gh & ~th, 1.0 + PARTIAL_CREDIT * (Q_G / g_hi),
                np.where(~gh & th, 1.0 + PARTIAL_CREDIT * (Q_T / t_hi),
                         0.05))))
    phase = np.clip(phase, 0.05, CLIP)
    flag = np.zeros(len(a_G), dtype=float)
    flag[1:] = (a_G[:-1] > G_BOOST_THRESH).astype(float)
    return pd.Series(base.reindex(idx).fillna(0.0).values * size
                     * (1.0 + CHAMPION_BOOST * flag) * phase, index=idx)


# ── v61: AGC-normalised floating gate ────────────────────────────────────────

def _float_gate_normalised(a: np.ndarray, alpha: float) -> np.ndarray:
    """
    Floating gate + coupling cap + AGC amplifier.

    Circuit equivalent:
      Signal → [EMA accumulator] → [Coupling Cap: EMA DC-block]
             → [AGC Amp: divide by EMA-std] → Schmitt

    The AGC_SPAN=168 normalisation window is INDEPENDENT of alpha, so:
        E[Q_z] ≈ 0    for all alpha
        Var[Q_z] ≈ 1  for all alpha

    This means any fixed z-score threshold fires at a CONSTANT PERCENTILE
    regardless of what alpha was used in the accumulator.
    """
    q   = _float_gate_charge(a, alpha)         # raw EMA accumulator (causal)
    q_s = pd.Series(q)
    dc  = q_s.ewm(span=AGC_SPAN, adjust=False).mean().values         # DC level
    std = q_s.ewm(span=AGC_SPAN, adjust=False).std().fillna(1.0).values  # amplitude
    return (q - dc) / np.maximum(std, 1e-8)    # z-score: E=0, Var=1 ∀α


def _build_pnl_v61(
    base:  pd.Series,
    sv36:  pd.DataFrame,
    lf:    pd.DataFrame,
    s4:    pd.DataFrame,
    alpha: float = ALPHA_FG,
    g_hi:  float = G_Z_HI_LOOSE,
    g_lo:  float = G_Z_LO_LOOSE,
    t_hi:  float = T_Z_HI_LOOSE,
    t_lo:  float = T_Z_LO_LOOSE,
) -> pd.Series:
    """
    v61: Full ST-FGRC with AGC z-score normalised floating gate.

    Key differences from v59:
      (a) Q_G_z = (Q_G − EMA(Q_G, 168)) / EMA_std(Q_G, 168)
          → Var[Q_G_z] ≈ 1 for any alpha  (alpha independence)
      (b) Schmitt thresholds are z-score values (dimensionless percentiles)
      (c) Partial credit ∝ clip(Q_G_z, 0, 1)
          → positive deviation only; alpha-independent
      (d) CLIP=6.0 retained (separate from v60's BSDT ceiling experiment)
    """
    idx  = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lf.reindex(idx,   method='ffill').fillna(0.5)
    s4   = s4.reindex(idx,   method='ffill').fillna(0.0)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam.values, 0.0, 1.0) * (0.75 + 0.5 * lp.values)

    a_G  = s4['a_G'].values; a_A = s4['a_A'].values; a_T = s4['a_T'].values

    # ── AGC-normalised gate charges ───────────────────────────────────────────
    Q_G_z = _float_gate_normalised(a_G, alpha)    # z-score: E=0, Var≈1, ∀α
    Q_T_z = _float_gate_normalised(a_T, alpha)

    # ── Schmitt triggers (thresholds in z-score units) ────────────────────────
    GH = _schmitt_trigger(Q_G_z, g_hi, g_lo)
    TH = _schmitt_trigger(Q_T_z, t_hi, t_lo)
    gh = GH > 0.5; th = TH > 0.5

    # ── fire gate (unchanged) ─────────────────────────────────────────────────
    fire = np.zeros(len(a_A), dtype=bool)
    fire[1:] = a_A[:-1] > A_FIRE_THRESH

    # ── partial credit — positive z-score deviation, alpha-independent ────────
    # Contribution when ONLY one channel fires.
    # clip(Q_z, 0, 1): only counts ABOVE-mean deviations, saturates at 1σ.
    q_g_credit = np.clip(Q_G_z, 0.0, 1.0)   # ∈ [0, 1]
    q_t_credit = np.clip(Q_T_z, 0.0, 1.0)

    # ── priority encoder ─────────────────────────────────────────────────────
    phase = np.where(
        ~fire,       1.0,
        np.where(
            gh & th,   CLIP,                                    # full boost
            np.where(
                gh & ~th,  1.0 + PARTIAL_CREDIT * q_g_credit,  # partial G
                np.where(
                    ~gh & th,  1.0 + PARTIAL_CREDIT * q_t_credit,  # partial T
                    0.05   # neither — kill
                )
            )
        )
    )

    phase = np.clip(phase, 0.05, CLIP)

    # champion boost (unchanged)
    flag = np.zeros(len(a_G), dtype=float)
    flag[1:] = (a_G[:-1] > G_BOOST_THRESH).astype(float)

    return pd.Series(
        base.reindex(idx).fillna(0.0).values * size
        * (1.0 + CHAMPION_BOOST * flag) * phase,
        index=idx
    )


def _sharpe(p): return float(_stats(p)['sharpe'])
def _maxdd(p):  return float(_stats(p)['max_dd'])


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    t0  = time.time()
    BAR = '=' * 100
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)

    print(BAR)
    print("  v61 — AGC-Normalised Floating Gate  (coupling cap + auto-gain control)")
    print("  Q_G_z = (Q_G − EMA(Q_G, 168)) / EMA_std(Q_G, 168)")
    print("  Schmitt thresholds in z-score units → constant firing rate ∀α")
    print(f"  AGC_SPAN={AGC_SPAN}  α_default={ALPHA_FG}  CLIP={CLIP}")
    print(BAR)

    t = lambda msg: print(f'\n{msg}', flush=True)

    t('[1] 1h data')
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask   = df_1h.index >= TEST_START
    train_1h    = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    first_half  = (df_1h.index >= TEST_START)  & (df_1h.index < OOS_SPLIT)
    second_half = df_1h.index >= OOS_SPLIT

    t(f'[2] Funding  t={time.time()-t0:.0f}s')
    try:
        fund = _cached_fetch_binance_funding()
        fund_eth = fund.get('ETHUSDT'); fund_btc = fund.get('BTCUSDT')
    except Exception as e:
        print(f'    Warning: {e}'); fund_eth = fund_btc = None

    t(f'[3] State panel  t={time.time()-t0:.0f}s')
    X = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X = np.nan_to_num(X)
    train_idx  = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True

    t(f'[4] Engine  t={time.time()-t0:.0f}s')
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(X, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)
    M_k1    = MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)

    t(f'[5] Signals  t={time.time()-t0:.0f}s')
    sig_v36       = compute_intraday_signals(X, df_1h, M, net, ews, stoch, e_star, theta)
    sig_v37, _, _ = compute_price_prediction_signals(X, df_1h, M, sig_v36, e_star, sigma_n)
    lam_feat      = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    t(f'[6] 4-channel  t={time.time()-t0:.0f}s')
    mu_norm  = calibrate_channel_means(X, calib_mask, M_k1)
    fire_thr = calibrate_firing_thresholds(X, calib_mask, M_k1, pct=FIRE_PERCENTILE)
    sig_4ch  = compute_four_channel_signals_v39b(X, df_1h, M_k1, sig_v36, fire_thr, mu_norm)

    t(f'[7] Base portfolio  t={time.time()-t0:.0f}s')
    h_strats = compute_1h_strategies(df_1h, has_sol)
    df_d     = _cached_fetch_and_prepare()
    df_d     = _cached_add_cross_market(df_d)
    fund_d   = _cached_fetch_binance_funding()
    df_d     = add_leverage_features(df_d, fund_d)
    tmask_d  = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
    pos_dict, _, F_daily, gate_daily = build_daily_positions(
        df_d, tmask_d, np.asarray(tmask_d, dtype=bool))
    instr_map = {
        'D1_trend_eth': df_1h['ret_eth'],
        'D2_pairs_eb':  df_1h['spread_ret_eb'],
        'D3_pairs_es':  df_1h['ret_eth'] - df_1h.get('ret_sol', df_1h['ret_eth']),
        'D4_macro_btc': df_1h['ret_btc'],
        'D5_macro_btc': df_1h['ret_btc'],
        'D5_macro_alt': df_1h['ret_eth'],
    }
    d1h = {n: upsample_daily_to_1h_pnl(p, instr_map.get(n, df_1h['ret_eth']), gate_daily)
           for n, p in pos_dict.items()}
    base_pnl = assemble_combined({**d1h, **h_strats},
                                  compute_quality({**d1h, **h_strats}, bpd=BPD))
    print(f"    Base Sharpe (full test): {_sharpe(base_pnl[test_mask]):+.3f}")

    # ── inspect z-score distribution at training time ─────────────────────────
    t('[8] AGC z-score verification')
    a_G_arr = sig_4ch['a_G'].values
    a_T_arr = sig_4ch['a_T'].values
    for a_name, a_arr in [('G', a_G_arr), ('T', a_T_arr)]:
        for al in [0.75, 0.85, 0.95]:
            qz = _float_gate_normalised(a_arr, al)
            qz_test = qz[test_mask]
            print(f"    Q_{a_name}_z  α={al:.2f}:  "
                  f"mean={np.mean(qz_test):+.3f}  "
                  f"std={np.std(qz_test):.3f}  "
                  f"p15={np.percentile(qz_test,15):+.3f}  "
                  f"p85={np.percentile(qz_test,85):+.3f}")
    print("    (mean≈0, std≈1 for all α validates AGC normalisation)")

    rv_ema = _realized_vol(df_1h, ema_span=3)

    # ── Config registry ────────────────────────────────────────────────────────
    configs = {
        'v58_tight (ref)          ': ('v58', dict(rv_norm=rv_ema, lo=-0.01)),
        'v59_schmitt_only (ref)   ': ('v59', dict(alpha=ALPHA_FG, schmitt_only=True,
                                                   t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO)),
        'v61_loose (z=-1.0/-1.5) ': ('v61', dict(alpha=ALPHA_FG,
                                                   g_hi=G_Z_HI_LOOSE, g_lo=G_Z_LO_LOOSE,
                                                   t_hi=T_Z_HI_LOOSE, t_lo=T_Z_LO_LOOSE)),
        'v61_mid   (z= 0.0/-0.5) ': ('v61', dict(alpha=ALPHA_FG,
                                                   g_hi=G_Z_HI_MID, g_lo=G_Z_LO_MID,
                                                   t_hi=T_Z_HI_MID, t_lo=T_Z_LO_MID)),
        'v61_surge (z=+1.0/+0.5) ': ('v61', dict(alpha=ALPHA_FG,
                                                   g_hi=G_Z_HI_SURGE, g_lo=G_Z_LO_SURGE,
                                                   t_hi=T_Z_HI_SURGE, t_lo=T_Z_LO_SURGE)),
    }

    def _pnl(label, mode, kw):
        if mode == 'v58':
            return _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, **kw)
        if mode == 'v59':
            return _build_pnl_v59(base_pnl, sig_v36, lam_feat, sig_4ch, **kw)
        return _build_pnl_v61(base_pnl, sig_v36, lam_feat, sig_4ch, **kw)

    # ── TEST 1: OOS SPLIT ─────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 1 — OOS SPLIT  (pass: second_half Sharpe ≥ 3.60)')
    print(f'  Split: first_half 2023-2024 | second_half 2025-2026')
    print(f'{BAR}')
    print(f"\n  {'Config':<44} {'Full':>8} {'23-24':>8} {'25-26':>8} {'DD 25-26':>10}  Pass?")
    print(f"  {'-'*44} {'-'*8} {'-'*8} {'-'*8} {'-'*10}  -----")

    oos_results = {}
    for label, (mode, kw) in configs.items():
        pnl    = _pnl(label, mode, kw)
        s_full = _sharpe(pnl[test_mask])
        s_h1   = _sharpe(pnl[first_half])
        s_h2   = _sharpe(pnl[second_half])
        dd_h2  = _maxdd(pnl[second_half])
        ok     = s_h2 >= 3.60
        print(f"  {label:<44} {s_full:>+8.4f} {s_h1:>+8.4f} {s_h2:>+8.4f} {dd_h2:>+9.1%}  {'✓' if ok else '✗'}")
        oos_results[label.strip()] = {
            'sharpe_full': float(s_full), 'sharpe_first': float(s_h1),
            'sharpe_second': float(s_h2), 'maxdd_second': float(dd_h2), 'pass': ok,
        }

    # ── TEST 2: ALPHA SENSITIVITY ─────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 2 — ALPHA SENSITIVITY  (pass: max |Sharpe drop| < 0.15)  ← KEY TEST')
    print('  Hypothesis: AGC normalisation E[Q_z]=0, Var[Q_z]=1 ∀α fixes the coupling.')
    print('  v59 failure was 0.33. v60 failure was 0.37.  v61 target: < 0.15.')
    print('  Perturbations: α ∈ {0.75, 0.80, 0.85, 0.90, 0.95}')
    print(f'{BAR}')

    alpha_perturbs = [0.75, 0.80, 0.85, 0.90, 0.95]

    alpha_results  = {}
    alpha_summary  = {}
    v61_labels = [l for l in configs if l.strip().startswith('v61')]

    for label in v61_labels:
        _, base_kw = configs[label]
        print(f"\n  ── {label.strip()} ──")
        print(f"  {'α':>6} {'Sharpe':>8} {'Δ_baseline':>12} {'MaxDD':>8}  Verdict")
        print(f"  {'-'*6} {'-'*8} {'-'*12} {'-'*8}  -------")

        pnl_base = _build_pnl_v61(base_pnl, sig_v36, lam_feat, sig_4ch, **base_kw)
        s_base   = _sharpe(pnl_base[test_mask])
        row = {}; t2_pass = True

        for al in alpha_perturbs:
            kw_a = {**base_kw, 'alpha': al}
            pnl_p = _build_pnl_v61(base_pnl, sig_v36, lam_feat, sig_4ch, **kw_a)
            s_p   = _sharpe(pnl_p[test_mask])
            drop  = s_p - s_base
            dd_p  = _maxdd(pnl_p[test_mask])
            is_b  = (al == ALPHA_FG)
            verdict = '—' if is_b else ('PASS' if abs(drop) < 0.15 else 'FAIL')
            if not is_b and abs(drop) >= 0.15:
                t2_pass = False
            print(f"  {al:>6.2f} {s_p:>+8.4f} {drop:>+12.4f} {dd_p:>+7.1%}  {verdict}")
            row[f'α={al}'] = {'alpha': float(al), 'sharpe': float(s_p),
                              'delta': float(drop), 'maxdd': float(dd_p)}

        max_drop = max(abs(v['delta']) for v in row.values() if v['alpha'] != ALPHA_FG)
        print(f"\n  Max drop: {max_drop:.4f}  →  TEST 2: {'✓ PASS' if t2_pass else '✗ FAIL'}"
              f"  [v59 was ✗ 0.33, v60 was ✗ 0.37]")
        alpha_results[label.strip()]  = row
        alpha_summary[label.strip()] = {'pass': t2_pass, 'max_drop': float(max_drop)}

    # ── TEST 3: THRESHOLD SENSITIVITY ────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 3 — THRESHOLD SENSITIVITY  (pass: max |Sharpe drop| < 0.15)')
    print('  Perturbs z-thresholds by ±0.25σ and changes band width.')
    print(f'{BAR}')

    # perturb the best-OOS-so-far v61 config
    best_v61 = max(
        (l for l in v61_labels if oos_results[l.strip()]['pass']),
        key=lambda l: oos_results[l.strip()]['sharpe_second'],
        default=v61_labels[0]
    )
    _, bkw = configs[best_v61]
    bhi_g = bkw['g_hi']; blo_g = bkw['g_lo']
    bhi_t = bkw['t_hi']; blo_t = bkw['t_lo']
    band_g = bhi_g - blo_g; band_t = bhi_t - blo_t

    thr_perturbs = {
        'baseline':       dict(**bkw),
        'G_hi + 0.25σ':   dict(**{**bkw, 'g_hi': bhi_g+0.25}),
        'G_hi − 0.25σ':   dict(**{**bkw, 'g_hi': bhi_g-0.25}),
        'T_hi + 0.25σ':   dict(**{**bkw, 't_hi': bhi_t+0.25}),
        'T_hi − 0.25σ':   dict(**{**bkw, 't_hi': bhi_t-0.25}),
        'band × 1.5':     dict(**{**bkw, 'g_hi': bhi_g+band_g*0.25, 'g_lo': blo_g-band_g*0.25,
                                         't_hi': bhi_t+band_t*0.25, 't_lo': blo_t-band_t*0.25}),
        'band × 0.5':     dict(**{**bkw, 'g_hi': bhi_g-band_g*0.25, 'g_lo': blo_g+band_g*0.25,
                                         't_hi': bhi_t-band_t*0.25, 't_lo': blo_t+band_t*0.25}),
    }

    print(f"\n  ── {best_v61.strip()} ──  (best OOS v61 config)")
    print(f"  {'Perturbation':<18} {'Sharpe':>8} {'Δ_baseline':>12} {'MaxDD':>8}  Verdict")
    print(f"  {'-'*18} {'-'*8} {'-'*12} {'-'*8}  -------")

    pnl_thr_base = _build_pnl_v61(base_pnl, sig_v36, lam_feat, sig_4ch, **thr_perturbs['baseline'])
    s_thr_base   = _sharpe(pnl_thr_base[test_mask])
    thr_rows = {}; t3_pass = True
    for pname, pkw in thr_perturbs.items():
        pnl_p = _build_pnl_v61(base_pnl, sig_v36, lam_feat, sig_4ch, **pkw)
        s_p   = _sharpe(pnl_p[test_mask])
        drop  = s_p - s_thr_base
        dd_p  = _maxdd(pnl_p[test_mask])
        is_b  = pname == 'baseline'
        verdict = '—' if is_b else ('PASS' if abs(drop) < 0.15 else 'FAIL')
        if not is_b and abs(drop) >= 0.15:
            t3_pass = False
        print(f"  {pname:<18} {s_p:>+8.4f} {drop:>+12.4f} {dd_p:>+7.1%}  {verdict}")
        thr_rows[pname] = {'sharpe': float(s_p), 'delta': float(drop), 'maxdd': float(dd_p)}

    t3_max_drop = max(abs(v['delta']) for k, v in thr_rows.items() if k != 'baseline')
    print(f"\n  Max drop: {t3_max_drop:.4f}  →  TEST 3: {'✓ PASS' if t3_pass else '✗ FAIL'}")

    # ── TEST 4: rv STRESS (v58 reference) ─────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 4 — rv STRESS on v58_tight  (reference, unchanged)')
    print(f'{BAR}')
    rng = np.random.default_rng(42)
    rv_perturbs = {
        'baseline':         lambda rv: rv,
        'rv × 0.90':        lambda rv: rv * 0.90,
        'rv × 1.10':        lambda rv: rv * 1.10,
        'rv + N(0, 0.02)':  lambda rv: (rv + rng.normal(0,0.02,size=len(rv))).clip(0.02, None),
    }
    rv_pnl_base = _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, rv_ema, -0.01)
    rv_s_base   = _sharpe(rv_pnl_base[test_mask])
    print(f"\n  {'Perturbation':<25} {'Sharpe':>8} {'Δ_baseline':>12} {'MaxDD':>8}")
    rv_rows = {}; t4_pass = True
    for pname, pfunc in rv_perturbs.items():
        rv_p  = pfunc(rv_ema)
        pnl_p = _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, rv_p, -0.01)
        s_p   = _sharpe(pnl_p[test_mask])
        drop  = s_p - rv_s_base
        dd_p  = _maxdd(pnl_p[test_mask])
        is_b  = pname == 'baseline'
        verdict = '—' if is_b else ('PASS' if abs(drop) < 0.15 else 'FAIL')
        if not is_b and abs(drop) >= 0.15: t4_pass = False
        print(f"  {pname:<25} {s_p:>+8.4f} {drop:>+12.4f} {dd_p:>+7.1%}  {verdict}")
        rv_rows[pname] = {'sharpe': float(s_p), 'delta': float(drop), 'maxdd': float(dd_p)}
    t4_max_drop = max(abs(v['delta']) for k,v in rv_rows.items() if k != 'baseline')
    print(f"\n  Max drop: {t4_max_drop:.4f}  →  TEST 4: {'✓ PASS' if t4_pass else '✗ FAIL'}")

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SUMMARY')
    print(f'{BAR}')
    print(f"\n  {'Config':<44} {'OOS':>5} {'α-sens':>7} {'Thr':>5} {'Max α-drop':>11} {'OOS H2':>8}")
    print(f"  {'-'*44} {'-'*5} {'-'*7} {'-'*5} {'-'*11} {'-'*8}")

    best_label = None; best_h2 = -99.0
    for label, (mode, kw) in configs.items():
        lkey   = label.strip()
        oos_ok = oos_results[lkey]['pass']
        s_h2   = oos_results[lkey]['sharpe_second']
        a_ok   = alpha_summary.get(lkey, {}).get('pass', True)
        a_mxd  = alpha_summary.get(lkey, {}).get('max_drop', float('nan'))
        thr_ok = t3_pass if lkey == best_v61.strip() else True
        all_ok = oos_ok and a_ok and thr_ok
        mark   = '  ← CANDIDATE' if (all_ok and s_h2 > best_h2) else ''
        if all_ok and s_h2 > best_h2:
            best_h2 = s_h2; best_label = lkey
        a_s = f'{a_mxd:>+11.4f}' if not np.isnan(a_mxd) else f'{"N/A":>11}'
        print(f"  {label:<44} {'✓' if oos_ok else '✗':>5} {'✓' if a_ok else '✗':>7}"
              f" {'✓' if thr_ok else '✗':>5} {a_s} {s_h2:>+8.4f}{mark}")

    print()
    if best_label:
        print(f"  CHAMPION : {best_label}")
        print(f"  OOS H2   : {best_h2:+.4f}")
        print(f"  vs v58   : {best_h2 - V58_SHARPE:+.4f}")
    else:
        print("  No config passed all tests.")

    print(f'\n  Alpha sensitivity progress:')
    for lkey, summary in alpha_summary.items():
        md = summary['max_drop']
        print(f"    {lkey:<40} max_drop={md:.4f}  {'✓ PASS' if summary['pass'] else '✗ FAIL'}")
    print(f'    v59 reference                            max_drop=0.3300  ✗ FAIL')
    print(f'    v60 reference                            max_drop=0.3664  ✗ FAIL')
    print(f'{BAR}')

    # ── Save ──────────────────────────────────────────────────────────────────
    results = {
        'meta': {
            'version': 'v61',
            'description': 'AGC z-score normalised floating gate (coupling cap + AGC)',
            'agc_span': AGC_SPAN,
            'v58_sharpe': V58_SHARPE,
            'oos_split_date': OOS_SPLIT,
            'pass_bars': {'oos': 3.60, 'alpha_sensitivity': 0.15, 'threshold_sensitivity': 0.15},
            'z_thresholds': {
                'loose':  {'g_hi': G_Z_HI_LOOSE, 'g_lo': G_Z_LO_LOOSE,
                           't_hi': T_Z_HI_LOOSE, 't_lo': T_Z_LO_LOOSE},
                'mid':    {'g_hi': G_Z_HI_MID,   'g_lo': G_Z_LO_MID,
                           't_hi': T_Z_HI_MID,   't_lo': T_Z_LO_MID},
                'surge':  {'g_hi': G_Z_HI_SURGE, 'g_lo': G_Z_LO_SURGE,
                           't_hi': T_Z_HI_SURGE, 't_lo': T_Z_LO_SURGE},
            },
        },
        'oos_split': oos_results,
        'alpha_sensitivity': {'per_config': alpha_results, 'summary': alpha_summary},
        'threshold_sensitivity': {
            'config_tested': best_v61.strip(),
            'per_perturb': thr_rows, 'pass': t3_pass, 'max_drop': float(t3_max_drop),
        },
        'rv_stress_v58_ref': {'per_perturb': rv_rows, 'pass': t4_pass,
                              'max_drop': float(t4_max_drop)},
        'summary': {'best_label': best_label, 'best_oos_h2': float(best_h2),
                    'vs_v58': float(best_h2 - V58_SHARPE) if best_label else None},
    }
    out_path = OUT_DIR_ / 'crypto_bsdt_v61_results.json'
    with open(str(out_path), 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\n  Results saved → {out_path}')
    print(f'  Total time: {time.time()-t0:.0f}s')


if __name__ == '__main__':
    main()
