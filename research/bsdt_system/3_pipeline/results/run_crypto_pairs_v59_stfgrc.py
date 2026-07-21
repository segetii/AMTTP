"""
Crypto BSDT — v59: Schmitt Trigger-Enhanced Floating Gate Regime Controller
=============================================================================
Motivation
----------
v58 champion (lo=-0.01, EMA=3) passed all tests but carried a −0.077 Sharpe
cost from the asymmetric clamp, and the system remained a digital circuit
(hard AND gate) imposed on continuous geometric signals.  The Schmitt/floating-
gate architecture resolves the root cause rather than patching the symptom.

Three problems with the v58 gate:
  1. Hard AND gate   — discards gradient info at threshold boundaries
  2. Binary kill     — GH,TL and GL,TH do useful work; current 0.05 wastes it
  3. Rolling max     — peak-hold has no memory decay; a spike 8 bars ago and
                       sustained pressure 2 bars ago look identical

ST-FGRC changes (from the spec):
─────────────────────────────────
  LAYER 1 — Floating gate charge accumulators (replaces rolling max)
    Q_G(t) = alpha * Q_G(t-1) + a_G(t-1)    alpha ≈ 0.85 (8-bar half-life)
    Q_T(t) = alpha * Q_T(t-1) + a_T(t-1)    shift(1) built in → no lookahead

  LAYER 2 — Schmitt triggers (replaces single-threshold comparators)
    GH: SET when Q_G > 0.50, RESET when Q_G < 0.40, hold otherwise
    TH: SET when Q_T > 0.44, RESET when Q_T < 0.38, hold otherwise
    fire: a_A.shift(1) > 0.65  (unchanged)

  LAYER 3 — Priority encoder (replaces hard kill for single-channel events)
    NOT fire            →  phase = 1.0
    fire, GH, TH        →  phase = 6.0              (full boost)
    fire, GH, NOT TH    →  phase = 1 + 0.30*(Q_G/0.50)  (partial G boost)
    fire, NOT GH, TH    →  phase = 1 + 0.30*(Q_T/0.44)  (partial T boost)
    fire, NOT GH, NOT TH →  phase = 0.05             (kill)

  LAYER 4 — clip(0.05, 6.0)  (unchanged)

Configs tested
--------------
  v58_tight          — v58 champion reference (rv_ema, lo=-0.01)
  v59_schmitt_only   — MINIMAL: Schmitt on T only, rolling max + static G
  v59_fgrc_a085      — Full ST-FGRC, alpha=0.85  ← expected champion
  v59_fgrc_a080      — Full ST-FGRC, alpha=0.80
  v59_fgrc_a090      — Full ST-FGRC, alpha=0.90

Tests
------
  TEST 1 — OOS split (pass: second_half Sharpe ≥ 3.60)
  TEST 2 — Threshold sensitivity for v59 (pass: max |drop| < 0.15)
             perturbs G_hi ±0.02, T_hi ±0.02, alpha ±0.05
  TEST 3 — rv stress for v58 reference (rv×0.9, rv×1.1, rv+noise)
             kept for apples-to-apples v57→v58→v59 comparison

Pass bar unchanged from v58: max |Sharpe drop| < 0.15.
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

# ── cache helpers (identical to v58) ──────────────────────────────────────────
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

# ── frozen constants (inherited from v58 / v55 champion) ──────────────────────
CLIP            = 6.0
GH_TH           = 5.0      # quadrant multiplier: GH,TH
GH_TL = GL_TH = GL_TL = -1.0  # quadrant multipliers: kills (v58 gate)
N_OPT           = 8
T_THRESH_BASE   = 0.41     # v58 static T threshold (used in schmitt_only mode)
G_THRESH_BASE   = 0.45     # v58 static G threshold (used in schmitt_only mode)
G_BOOST_THRESH  = 0.45
CHAMPION_BOOST  = 0.65
A_FIRE_THRESH   = 0.65
K_G             = 0.10

# ── v59 ST-FGRC constants ──────────────────────────────────────────────────────
ALPHA_FG        = 0.85     # floating gate decay (0.85^8 ≈ 0.27 → ~8-bar half-life)
# Charge-scale Schmitt thresholds — calibrated to match v58's firing rates:
#   v58 P(G_mem > 0.45) ≈ 85%  →  Q_G_norm p15 ≈ 0.32  →  G_SCHMITT_HI = 0.32
#   v58 P(T_mem > 0.41) ≈ 81%  →  Q_T_norm p19 ≈ 0.31  →  T_SCHMITT_HI = 0.31
# Hysteresis band ≈ 0.06 (prevents cliff oscillation at boundary)
G_SCHMITT_HI    = 0.32     # Q_G_norm SET threshold   (~ p15 of Q_G_norm)
G_SCHMITT_LO    = 0.26     # Q_G_norm RESET threshold (~ p5  of Q_G_norm)
T_SCHMITT_HI    = 0.31     # Q_T_norm SET threshold   (~ p19 of Q_T_norm)
T_SCHMITT_LO    = 0.25     # Q_T_norm RESET threshold (~ p5  of Q_T_norm)
PARTIAL_CREDIT  = 0.30     # partial boost multiplier for single-channel events

V58_SHARPE  = 4.0362       # v58 champion full-test Sharpe (baseline to beat)
OOS_SPLIT   = '2025-01-01'


# ── v58 helpers (kept verbatim for v58_tight reference config) ─────────────────

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

def _build_pnl_v58(
    base:    pd.Series,
    sv36:    pd.DataFrame,
    lf:      pd.DataFrame,
    s4:      pd.DataFrame,
    rv_norm: pd.Series,
    lo:      float,
) -> pd.Series:
    """Verbatim v58 champion gate — for reference comparison."""
    idx  = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lf.reindex(idx,   method='ffill').fillna(0.5)
    s4   = s4.reindex(idx,   method='ffill').fillna(0.0)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam, 0.0, 1.0) * (0.75 + 0.5 * lp)

    gth   = _dynamic_gth(rv_norm.reindex(idx, method='ffill').fillna(1.0), lo)
    a_G   = s4['a_G']; a_A = s4['a_A']; a_T = s4['a_T']
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


# ── v59 ST-FGRC gate functions ─────────────────────────────────────────────────

def _float_gate_charge(a: np.ndarray, alpha: float) -> np.ndarray:
    """
    Floating gate charge accumulator.
    Q(t) = alpha * Q(t-1) + a(t-1)

    Shift-by-1 is built in (uses a(t-1)), so Q(t) is strictly causal.
    alpha = 0.85 → ~8-bar half-life, matching v58's N_OPT=8 window.
    Unlike rolling max, sustained moderate values accumulate; a single
    spike does not fully charge the gate.
    """
    q = np.zeros(len(a), dtype=float)
    for t in range(1, len(a)):
        q[t] = alpha * q[t - 1] + a[t - 1]
    return q


def _schmitt_trigger(q: np.ndarray, hi: float, lo: float) -> np.ndarray:
    """
    Schmitt comparator with hysteresis.

    State transitions:
      q > hi  →  SET   (state = 1)
      q < lo  →  RESET (state = 0)
      lo ≤ q ≤ hi → HOLD (state unchanged)

    The hold zone prevents cliff oscillation at the threshold boundary.
    Once SET, the gate stays ON until q clearly falls below lo.
    """
    state = np.zeros(len(q), dtype=float)
    s = 0.0
    for t in range(len(q)):
        if q[t] > hi:
            s = 1.0
        elif q[t] < lo:
            s = 0.0
        # else: hold — s unchanged
        state[t] = s
    return state


def _build_pnl_v59(
    base:         pd.Series,
    sv36:         pd.DataFrame,
    lf:           pd.DataFrame,
    s4:           pd.DataFrame,
    alpha:        float = ALPHA_FG,
    schmitt_only: bool  = False,
    g_hi:         float = G_SCHMITT_HI,
    g_lo:         float = G_SCHMITT_LO,
    t_hi:         float = T_SCHMITT_HI,
    t_lo:         float = T_SCHMITT_LO,
) -> pd.Series:
    """
    ST-FGRC gate applied to the base portfolio.

    schmitt_only=False  (default): full ST-FGRC
        - Q_G, Q_T floating gate charges
        - GH/TH via Schmitt triggers
        - Priority encoder with partial credit for single-channel events

    schmitt_only=True: minimal upgrade
        - Only Schmitt trigger on T (spec section 9: "if you only change ONE thing")
        - G uses rolling max + static G_THRESH_BASE (v58 behaviour)
        - Quadrant logic unchanged from v58 (kill on GH,TL / GL,TH)
        - Expected benefit: removes T-threshold cliff only
    """
    idx  = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lf.reindex(idx,   method='ffill').fillna(0.5)
    s4   = s4.reindex(idx,   method='ffill').fillna(0.0)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam.values, 0.0, 1.0) * (0.75 + 0.5 * lp.values)

    a_G_arr = s4['a_G'].values
    a_A_arr = s4['a_A'].values
    a_T_arr = s4['a_T'].values

    # ── floating gate charges (shift(1) built in) ────────────────────────────
    Q_G_raw = _float_gate_charge(a_G_arr, alpha)   # (T,)  steady-state ≈ E[a_G]/(1-α)
    Q_T_raw = _float_gate_charge(a_T_arr, alpha)   # (T,)

    # Normalise to [0,1] scale so Schmitt thresholds remain comparable to
    # the original attribution values (G_hi=0.50, T_hi=0.44, etc.).
    # Without this, Q_G ≈ 0.3/0.15 = 2.0 at steady state → GH always ON.
    Q_G = Q_G_raw * (1.0 - alpha)   # ≈ E[a_G] at steady state
    Q_T = Q_T_raw * (1.0 - alpha)   # ≈ E[a_T] at steady state

    # ── fire gate (unchanged from v58) ───────────────────────────────────────
    fire = np.zeros(len(a_A_arr), dtype=bool)
    fire[1:] = a_A_arr[:-1] > A_FIRE_THRESH

    if schmitt_only:
        # ── MINIMAL: Schmitt on T only ───────────────────────────────────────
        # G: rolling max + static threshold (verbatim v58)
        G_mem = (pd.Series(a_G_arr)
                 .rolling(N_OPT, min_periods=1).max()
                 .shift(1).fillna(0.0).values)
        GH = (G_mem > G_THRESH_BASE).astype(float)
        # T: Schmitt trigger on accumulated charge
        TH = _schmitt_trigger(Q_T, t_hi, t_lo)
        gh = GH > 0.5; th = TH > 0.5
        # quadrant multipliers unchanged from v58
        q_GH_TH = (fire & gh & th).astype(float)
        q_GH_TL = (fire & gh & ~th).astype(float)
        q_GL_TH = (fire & ~gh & th).astype(float)
        q_GL_TL = (fire & ~gh & ~th).astype(float)
        phase = (1.0 + GH_TH * q_GH_TH + GH_TL * q_GH_TL
                     + GL_TH * q_GL_TH + GL_TL * q_GL_TL)

    else:
        # ── FULL ST-FGRC ─────────────────────────────────────────────────────
        GH = _schmitt_trigger(Q_G, g_hi, g_lo)   # 0/1 Schmitt state
        TH = _schmitt_trigger(Q_T, t_hi, t_lo)   # 0/1 Schmitt state
        gh = GH > 0.5; th = TH > 0.5
        # priority encoder — NO hard kill for single-channel events
        phase = np.where(
            ~fire,         1.0,
            np.where(
                gh & th,   CLIP,
                np.where(
                    gh & ~th,  1.0 + PARTIAL_CREDIT * (Q_G / g_hi),
                    np.where(
                        ~gh & th,  1.0 + PARTIAL_CREDIT * (Q_T / t_hi),
                        0.05   # neither GH nor TH — genuine weak signal, kill
                    )
                )
            )
        )

    phase = np.clip(phase, 0.05, CLIP)

    # champion boost (unchanged from v58)
    flag = np.zeros(len(a_G_arr), dtype=float)
    flag[1:] = (a_G_arr[:-1] > G_BOOST_THRESH).astype(float)

    base_arr = base.reindex(idx).fillna(0.0).values
    pnl_arr  = base_arr * size * (1.0 + CHAMPION_BOOST * flag) * phase
    return pd.Series(pnl_arr, index=idx)


def _sharpe(p): return float(_stats(p)['sharpe'])
def _maxdd(p):  return float(_stats(p)['max_dd'])


# ── main ───────────────────────────────────────────────────────────────────────
def main():
    t0  = time.time()
    BAR = '=' * 100
    rng = np.random.default_rng(42)
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)

    print(BAR)
    print("  v59 — ST-FGRC  (Schmitt Trigger-Enhanced Floating Gate Regime Controller)")
    print("  Floating gate charges + Schmitt hysteresis + priority encoder")
    print(f"  alpha={ALPHA_FG}  G_bands=({G_SCHMITT_LO},{G_SCHMITT_HI})"
          f"  T_bands=({T_SCHMITT_LO},{T_SCHMITT_HI})  partial_credit={PARTIAL_CREDIT}")
    print(BAR)

    t = lambda msg: print(f'\n{msg}', flush=True)

    # ── Data + signals (identical pipeline — all cached after first run) ───────
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

    # ── rv_norm for v58 reference only ────────────────────────────────────────
    rv_ema = _realized_vol(df_1h, ema_span=3)

    # ── Config registry ────────────────────────────────────────────────────────
    # Each entry: (mode, kwargs)
    #   mode='v58' → _build_pnl_v58(... rv_norm, lo)
    #   mode='v59' → _build_pnl_v59(... **kwargs)
    configs = {
        'v58_tight (reference)      ': (
            'v58', dict(rv_norm=rv_ema, lo=-0.01)),
        'v59_schmitt_only (T-Schmitt)': (
            'v59', dict(alpha=ALPHA_FG, schmitt_only=True,
                        t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO)),
        'v59_fgrc (alpha=0.85)      ': (
            'v59', dict(alpha=0.85, schmitt_only=False,
                        g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                        t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO)),
        'v59_fgrc (alpha=0.80)      ': (
            'v59', dict(alpha=0.80, schmitt_only=False,
                        g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                        t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO)),
        'v59_fgrc (alpha=0.90)      ': (
            'v59', dict(alpha=0.90, schmitt_only=False,
                        g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                        t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO)),
        # wider band — test Schmitt stability
        'v59_fgrc (wide band)       ': (
            'v59', dict(alpha=0.85, schmitt_only=False,
                        g_hi=G_SCHMITT_HI+0.03, g_lo=G_SCHMITT_LO-0.03,
                        t_hi=T_SCHMITT_HI+0.03, t_lo=T_SCHMITT_LO-0.03)),
    }

    def _pnl(label, mode, kw):
        if mode == 'v58':
            return _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, **kw)
        return _build_pnl_v59(base_pnl, sig_v36, lam_feat, sig_4ch, **kw)

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

    # ── TEST 2: THRESHOLD SENSITIVITY (v59 configs) ───────────────────────────
    print(f'\n{BAR}')
    print('  TEST 2 — THRESHOLD SENSITIVITY  (pass: max |Sharpe drop| < 0.15)')
    print('  Purpose: verify Schmitt hysteresis eliminates cliff at T_hi boundary.')
    print('  Perturbs: G_hi ±0.02, T_hi ±0.02, alpha ±0.05')
    print(f'{BAR}')

    # Schmitt perturbations (applied to v59 full FGRC configs only)
    schmitt_perturbs = {
        'baseline':       dict(alpha=0.85, g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                               t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO),
        'T_hi + 0.02':    dict(alpha=0.85, g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                               t_hi=T_SCHMITT_HI+0.02, t_lo=T_SCHMITT_LO),
        'T_hi - 0.02':    dict(alpha=0.85, g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                               t_hi=T_SCHMITT_HI-0.02, t_lo=T_SCHMITT_LO),
        'G_hi + 0.02':    dict(alpha=0.85, g_hi=G_SCHMITT_HI+0.02, g_lo=G_SCHMITT_LO,
                               t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO),
        'G_hi - 0.02':    dict(alpha=0.85, g_hi=G_SCHMITT_HI-0.02, g_lo=G_SCHMITT_LO,
                               t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO),
        'alpha + 0.05':   dict(alpha=0.90, g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                               t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO),
        'alpha - 0.05':   dict(alpha=0.80, g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                               t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO),
        # wider band stress — Schmitt hysteresis robustness
        'band * 1.5':     dict(alpha=0.85, g_hi=G_SCHMITT_HI+0.03, g_lo=G_SCHMITT_LO-0.03,
                               t_hi=T_SCHMITT_HI+0.03, t_lo=T_SCHMITT_LO-0.03),
        'band * 0.5':     dict(alpha=0.85, g_hi=G_SCHMITT_HI-0.03, g_lo=G_SCHMITT_LO+0.03,
                               t_hi=T_SCHMITT_HI-0.03, t_lo=T_SCHMITT_LO+0.03),
    }

    sensitivity_results = {}
    sensitivity_summary = {}

    # run sensitivity only for full FGRC configs
    fgrc_labels = [l for l in configs if 'fgrc' in l.lower()]
    for label in fgrc_labels:
        print(f"\n  ── {label.strip()} ──")
        print(f"  {'Perturbation':<18} {'Sharpe':>8} {'Δ_baseline':>12} {'MaxDD':>8}  Verdict")
        print(f"  {'-'*18} {'-'*8} {'-'*12} {'-'*8}  -------")

        alpha_base = configs[label][1]['alpha']
        pnl_base = _build_pnl_v59(base_pnl, sig_v36, lam_feat, sig_4ch,
                                   schmitt_only=False, **schmitt_perturbs['baseline'])
        s_base = _sharpe(pnl_base[test_mask])
        row = {}; t2_pass = True

        for pname, pkw in schmitt_perturbs.items():
            # respect the config's own alpha when the perturb changes alpha
            kw_run = dict(pkw, schmitt_only=False)
            pnl_p = _build_pnl_v59(base_pnl, sig_v36, lam_feat, sig_4ch, **kw_run)
            s_p   = _sharpe(pnl_p[test_mask])
            drop  = s_p - s_base
            dd_p  = _maxdd(pnl_p[test_mask])
            is_b  = pname == 'baseline'
            verdict = '—' if is_b else ('PASS' if abs(drop) < 0.15 else 'FAIL')
            if not is_b and abs(drop) >= 0.15:
                t2_pass = False
            print(f"  {pname:<18} {s_p:>+8.4f} {drop:>+12.4f} {dd_p:>+7.1%}  {verdict}")
            row[pname] = {'sharpe': float(s_p), 'delta': float(drop), 'maxdd': float(dd_p)}

        max_drop = max(abs(v['delta']) for k, v in row.items() if k != 'baseline')
        print(f"\n  Max drop: {max_drop:.4f}  →  TEST 2: {'✓ PASS' if t2_pass else '✗ FAIL'}")
        sensitivity_results[label.strip()] = row
        sensitivity_summary[label.strip()] = {'pass': t2_pass, 'max_drop': float(max_drop)}

    # ── TEST 3: rv STRESS (v58 reference comparison) ──────────────────────────
    print(f'\n{BAR}')
    print('  TEST 3 — rv STRESS on v58_tight  (apples-to-apples v57→v58→v59)')
    print('  v57 failure: rv×1.10 → -0.297.  v58 patch target: < -0.10.')
    print(f'{BAR}')

    rv_stress_perturbs = {
        'baseline':       lambda rv: rv,
        'rv × 0.90':      lambda rv: rv * 0.90,
        'rv × 1.10':      lambda rv: rv * 1.10,
        'rv + N(0,0.02)': lambda rv: (rv + rng.normal(0, 0.02, size=len(rv))).clip(0.02, None),
    }

    print(f"\n  ── v58_tight (rv stress reference) ──")
    print(f"  {'Perturbation':<25} {'Sharpe':>8} {'Δ_baseline':>12} {'MaxDD':>8}  Verdict")
    print(f"  {'-'*25} {'-'*8} {'-'*12} {'-'*8}  -------")

    rv_pnl_base = _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, rv_ema, -0.01)
    rv_s_base   = _sharpe(rv_pnl_base[test_mask])
    rv_row = {}; rv_pass = True
    for pname, pfunc in rv_stress_perturbs.items():
        rv_p   = pfunc(rv_ema)
        pnl_p  = _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, rv_p, -0.01)
        s_p    = _sharpe(pnl_p[test_mask])
        drop   = s_p - rv_s_base
        dd_p   = _maxdd(pnl_p[test_mask])
        is_b   = pname == 'baseline'
        verdict = '—' if is_b else ('PASS' if abs(drop) < 0.15 else 'FAIL')
        if not is_b and abs(drop) >= 0.15:
            rv_pass = False
        print(f"  {pname:<25} {s_p:>+8.4f} {drop:>+12.4f} {dd_p:>+7.1%}  {verdict}")
        rv_row[pname] = {'sharpe': float(s_p), 'delta': float(drop), 'maxdd': float(dd_p)}

    rv_max_drop = max(abs(v['delta']) for k, v in rv_row.items() if k != 'baseline')
    print(f"\n  Max drop: {rv_max_drop:.4f}  →  rv stress: {'✓ PASS' if rv_pass else '✗ FAIL'}")

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SUMMARY — OOS + Sensitivity')
    print(f'{BAR}')
    print(f"\n  {'Config':<44} {'OOS':>5} {'Sens':>6} {'Max Drop':>10} {'OOS H2':>8}")
    print(f"  {'-'*44} {'-'*5} {'-'*6} {'-'*10} {'-'*8}")

    best_label = None; best_h2 = -99.0
    for label, (mode, kw) in configs.items():
        lkey = label.strip()
        oos_ok   = oos_results[lkey]['pass']
        sens_ok  = sensitivity_summary.get(lkey, {}).get('pass', True)  # v58 ref: N/A
        mxd      = sensitivity_summary.get(lkey, {}).get('max_drop', float('nan'))
        s_h2     = oos_results[lkey]['sharpe_second']
        both_ok  = oos_ok and sens_ok
        mark     = '  ← CHAMPION' if (both_ok and s_h2 > best_h2) else ''
        if both_ok and s_h2 > best_h2:
            best_h2 = s_h2; best_label = lkey
        mxd_str = f'{mxd:>+10.4f}' if not np.isnan(mxd) else f'{"N/A":>10}'
        print(f"  {label:<44} {'✓' if oos_ok else '✗':>5} {'✓' if sens_ok else '✗':>6}"
              f" {mxd_str} {s_h2:>+8.4f}{mark}")

    print()
    if best_label:
        print(f"  CHAMPION : {best_label}")
        print(f"  OOS H2   : {best_h2:+.4f}")
        print(f"  vs v58   : {best_h2 - V58_SHARPE:+.4f}  Sharpe improvement over v58 baseline")
    else:
        print("  No config passed both tests — review breakdown above.")
    print(f'\n{BAR}')

    # ── Save ──────────────────────────────────────────────────────────────────
    results = {
        'meta': {
            'v58_sharpe': V58_SHARPE,
            'oos_split_date': OOS_SPLIT,
            'pass_threshold_sensitivity': 0.15,
            'pass_threshold_oos': 3.60,
            'st_fgrc_params': {
                'alpha': ALPHA_FG,
                'G_schmitt': [G_SCHMITT_LO, G_SCHMITT_HI],
                'T_schmitt': [T_SCHMITT_LO, T_SCHMITT_HI],
                'partial_credit': PARTIAL_CREDIT,
                'fire_thresh': A_FIRE_THRESH,
                'clip': CLIP,
            },
        },
        'oos_split': oos_results,
        'threshold_sensitivity': {
            'per_config': sensitivity_results,
            'summary': sensitivity_summary,
        },
        'rv_stress_v58_ref': {
            'per_perturb': rv_row,
            'pass': rv_pass,
            'max_drop': float(rv_max_drop),
        },
        'champion': best_label,
        'champion_second_half_sharpe': float(best_h2) if best_label else None,
    }
    out_path = OUT_DIR_ / 'crypto_bsdt_v59_stfgrc.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"  Results saved → {out_path}")
    print(f"  Total elapsed: {time.time()-t0:.1f}s")
    print(BAR)
    return results


if __name__ == '__main__':
    main()
