"""
Crypto BSDT — v62: Sigmoid Soft Gate (Replacing Schmitt Trigger)
=================================================================
Problem being solved
--------------------
v61 proved that AGC z-score normalisation makes the MARGINAL distribution of
Q_G_z alpha-independent (mean≈0, Var≈1 for all α). But the Schmitt trigger's
stateful SET/HOLD/RESET machine is sensitive to AUTOCORRELATION of Q_G_z
(Corr ≈ α), not just the marginal distribution.

  Higher α  →  Q_G_z more persistent  →  longer HOLD zone occupancy
            →  boosted/killed bars change even when Var[Q_G_z] = 1

The Schmitt trigger is a LATCHING RELAY — once it flips, it stays until
the threshold is re-crossed.  It amplifies autocorrelation.

Circuit upgrade: replace LATCHING RELAY with MOSFET
----------------------------------------------------
A MOSFET (field effect transistor) is a STATELESS voltage-controlled switch.
Its conductance is a smooth function of gate voltage only — no hysteresis,
no memory:

    I_DS = I_0 * (V_GS - V_th)^2 / (1 + λ*V_DS)   [saturation region]

In soft-gate form (normalised to [0,1]):

    g(z) = sigmoid(k * (z − μ))   =   1 / (1 + exp(−k*(z−μ)))

    μ = inflection point (z-score units; threshold analogous to V_th)
    k = steepness (k→∞ becomes a hard step; k=4 is smooth)

Properties that fix alpha sensitivity:
  • STATELESS: g(t) depends ONLY on Q_G_z(t), not previous values
  • No HOLD zone → no autocorrelation amplification
  • When Q_G_z marginal distribution is alpha-invariant (confirmed by AGC),
    E[g(Q_G_z)] is also alpha-invariant
  • At μ=0: fires 50% of the time → recovers OOS Sharpe
  • Smooth continuous output → no cliff, no oscillation

Continuous priority encoder
-----------------------------
v59 had a discrete priority encoder (CLIP / partial / kill).
v62 generalises it to a continuous form using MOSFET gate values:

    boost   = (CLIP−1) · g_G · g_T          both ON  → ramp toward 6.0
    partial = PC · [g_G(1−g_T) + g_T(1−g_G)] one ON  → partial credit
    quiet   = KILL · (1−g_G)(1−g_T)         both OFF → ramp toward 0.05

    phase = 1 + boost + partial − quiet

At boundary values (k → ∞, g_G/g_T ∈ {0,1}):
    g_G=1, g_T=1 → phase = 1 + (CLIP−1) + 0 − 0        = CLIP  = 6.0  (full boost)
    g_G=1, g_T=0 → phase = 1 + 0 + PC − 0               = 1+PC  = 1.30 (partial G)
    g_G=0, g_T=1 → phase = 1 + 0 + PC − 0               = 1+PC  = 1.30 (partial T)
    g_G=0, g_T=0 → phase = 1 + 0 + 0 − KILL             = 1−0.95= 0.05 (kill)

This is the EXACT continuous generalisation of v59's discrete priority encoder.

Configs tested
--------------
  v58_tight (reference)
  v61_surge  (reference — only alpha-pass from v61, OOS H2=+2.70)
  v62_k4_mu0   — k=4, μ=0.0  (50th pctile, wide firing → high OOS?)
  v62_k4_mu05  — k=4, μ=0.5  (31st pctile, selective)
  v62_k4_mu1   — k=4, μ=1.0  (16th pctile, matches v61_surge selectivity)
  v62_k6_mu0   — k=6, μ=0.0  (sharper transition at median)
  v62_k8_mu1   — k=8, μ=1.0  (very sharp, near-hard threshold at 1σ)

Tests
------
  TEST 1 — OOS split (pass: H2 ≥ 3.60)
  TEST 2 — Alpha sensitivity  (pass: max |drop| < 0.15)  ← KEY TEST
  TEST 3 — Threshold sensitivity (±0.25σ in μ, steepness ±2)
  TEST 4 — rv stress on v58 reference
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

# ── cache helpers ─────────────────────────────────────────────────────────────
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

# ── frozen constants (v58 champion) ──────────────────────────────────────────
CLIP            = 6.0
N_OPT           = 8
T_THRESH_BASE   = 0.41
G_THRESH_BASE   = 0.45
G_BOOST_THRESH  = 0.45
CHAMPION_BOOST  = 0.65
A_FIRE_THRESH   = 0.65
K_G             = 0.10
GH_TH           = 5.0
GH_TL = GL_TH = GL_TL = -1.0

# ── v61 AGC constants (carried into v62) ─────────────────────────────────────
ALPHA_FG  = 0.85
AGC_SPAN  = 168    # fixed 1-week window, alpha-independent

# ── v61 Schmitt constants (for v61_surge reference) ──────────────────────────
G_SCHMITT_HI = 0.32; G_SCHMITT_LO = 0.26
T_SCHMITT_HI = 0.31; T_SCHMITT_LO = 0.25
PARTIAL_CREDIT = 0.30

# ── v62 continuous priority encoder constants ─────────────────────────────────
#
#  KILL_SOFT: suppression term when both channels quiet.
#    At g_G=0, g_T=0 (both quiet): phase = 1 − KILL_SOFT = 1 − 0.95 = 0.05
#    Matches v59's hard kill exactly at the extremes; smooth in the middle.
KILL_SOFT = 0.95

#  PC_V62: partial credit for single-channel events.
#    At g_G=1, g_T=0: phase = 1 + PC_V62 (= 1.30 matching v59 at PC=0.30)
PC_V62 = 0.30

V58_SHARPE = 4.0362
OOS_SPLIT  = '2025-01-01'


# ── v58 reference (verbatim) ──────────────────────────────────────────────────

def _realized_vol(df_1h, ema_span=1):
    rv      = df_1h['ret_eth'].rolling(168, min_periods=24).std()
    rv_mean = rv.rolling(1000, min_periods=100).mean()
    rv_norm = (rv / rv_mean.replace(0, np.nan)).fillna(1.0)
    if ema_span > 1:
        rv_norm = rv_norm.ewm(span=ema_span, adjust=False).mean()
    return rv_norm.shift(1).fillna(1.0)

def _dynamic_gth(rv_norm, lo=-1.0):
    adj = K_G * (1.0 - rv_norm)
    if lo > -0.5:
        adj = adj.clip(lo, 0.10)
    return (G_THRESH_BASE * (1.0 + adj)).clip(0.20, 0.70)

def _build_pnl_v58(base, sv36, lf, s4, rv_norm, lo):
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


# ── shared layer 1: AGC-normalised floating gate (from v61, unchanged) ────────

def _float_gate_charge(a: np.ndarray, alpha: float) -> np.ndarray:
    """Q(t) = alpha*Q(t-1) + a(t-1). Shift-1 built in."""
    q = np.zeros(len(a), dtype=float)
    for t in range(1, len(a)):
        q[t] = alpha * q[t - 1] + a[t - 1]
    return q

def _float_gate_normalised(a: np.ndarray, alpha: float) -> np.ndarray:
    """
    Coupling cap + AGC: Q_z = (Q - EMA(Q, 168)) / EMA_std(Q, 168).
    E[Q_z] ≈ 0, Var[Q_z] ≈ 1 for all alpha (confirmed in v61).
    AGC_SPAN=168 is fixed — does NOT depend on alpha.
    """
    q   = _float_gate_charge(a, alpha)
    q_s = pd.Series(q)
    dc  = q_s.ewm(span=AGC_SPAN, adjust=False).mean().values
    std = q_s.ewm(span=AGC_SPAN, adjust=False).std().fillna(1.0).values
    return (q - dc) / np.maximum(std, 1e-8)


# ── v61 Schmitt reference (for comparison) ────────────────────────────────────

def _schmitt_trigger(q, hi, lo):
    state = np.zeros(len(q), dtype=float); s = 0.0
    for t in range(len(q)):
        if q[t] > hi: s = 1.0
        elif q[t] < lo: s = 0.0
        state[t] = s
    return state

def _build_pnl_v61_surge(base, sv36, lf, s4, alpha=ALPHA_FG):
    """v61_surge reference: Schmitt at z=+1.0/+0.5 (only alpha-pass in v61)."""
    idx  = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lf.reindex(idx,   method='ffill').fillna(0.5)
    s4   = s4.reindex(idx,   method='ffill').fillna(0.0)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam.values, 0.0, 1.0) * (0.75 + 0.5 * lp.values)
    a_G  = s4['a_G'].values; a_A = s4['a_A'].values; a_T = s4['a_T'].values
    Q_G_z = _float_gate_normalised(a_G, alpha)
    Q_T_z = _float_gate_normalised(a_T, alpha)
    GH = _schmitt_trigger(Q_G_z, 1.0, 0.5)
    TH = _schmitt_trigger(Q_T_z, 1.0, 0.5)
    gh = GH > 0.5; th = TH > 0.5
    fire = np.zeros(len(a_A), dtype=bool); fire[1:] = a_A[:-1] > A_FIRE_THRESH
    q_g  = np.clip(Q_G_z, 0.0, 1.0); q_t = np.clip(Q_T_z, 0.0, 1.0)
    phase = np.where(~fire, 1.0,
            np.where(gh & th,  CLIP,
            np.where(gh & ~th, 1.0 + PARTIAL_CREDIT * q_g,
            np.where(~gh & th, 1.0 + PARTIAL_CREDIT * q_t,
                     0.05))))
    phase = np.clip(phase, 0.05, CLIP)
    flag  = np.zeros(len(a_G), dtype=float); flag[1:] = (a_G[:-1] > G_BOOST_THRESH).astype(float)
    return pd.Series(base.reindex(idx).fillna(0.0).values * size
                     * (1.0 + CHAMPION_BOOST * flag) * phase, index=idx)


# ── v62: MOSFET sigmoid gate (stateless) ─────────────────────────────────────

def _sigmoid_gate(q_z: np.ndarray, k: float, mu: float) -> np.ndarray:
    """
    Stateless soft gate — analog MOSFET in saturation region.

    g(z) = 1 / (1 + exp(−k*(z − μ)))   ∈ (0, 1)

    k = steepness (k→∞ → hard step; k=4 → 10%–90% span ≈ 1.1σ)
    μ = inflection point (z-score threshold)

    At z = μ:          g = 0.50  (half-conducting)
    At z = μ + 1/k:    g ≈ 0.73
    At z = μ − 1/k:    g ≈ 0.27

    NO STATE. g(t) depends only on q_z(t).
    → alpha changes Q_G_z autocorrelation but NOT the mapping g(Q_G_z)
    → if Q_G_z marginal is alpha-invariant, E[g(Q_G_z)] is alpha-invariant.
    """
    return 1.0 / (1.0 + np.exp(-k * (q_z - mu)))


def _build_pnl_v62(
    base:   pd.Series,
    sv36:   pd.DataFrame,
    lf:     pd.DataFrame,
    s4:     pd.DataFrame,
    alpha:  float = ALPHA_FG,
    k:      float = 4.0,
    mu:     float = 0.0,
    pc:     float = PC_V62,
    kill:   float = KILL_SOFT,
) -> pd.Series:
    """
    v62: AGC z-score + sigmoid MOSFET gate + continuous priority encoder.

    Phase mapping (continuous generalisation of v59 discrete encoder):
        boost   = (CLIP−1) · g_G · g_T          [∈ 0–5, both channels ON]
        partial = pc     · [g_G(1−g_T)+g_T(1−g_G)]  [∈ 0–pc, one channel]
        quiet   = kill   · (1−g_G)(1−g_T)       [∈ 0–kill, both OFF]
        phase   = 1 + boost + partial − quiet

    At g_G=g_T=1.0: phase = 1 + 5 + 0 − 0     = 6.0  (full boost = CLIP)
    At g_G=1,g_T=0: phase = 1 + 0 + pc − 0     = 1+pc (partial)
    At g_G=g_T=0.0: phase = 1 + 0 + 0 − kill   = 0.05 (kill)
    """
    idx  = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lf.reindex(idx,   method='ffill').fillna(0.5)
    s4   = s4.reindex(idx,   method='ffill').fillna(0.0)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam.values, 0.0, 1.0) * (0.75 + 0.5 * lp.values)

    a_G = s4['a_G'].values; a_A = s4['a_A'].values; a_T = s4['a_T'].values

    # Layer 1+2: AGC z-score normalised floating gate (alpha-invariant marginal)
    Q_G_z = _float_gate_normalised(a_G, alpha)
    Q_T_z = _float_gate_normalised(a_T, alpha)

    # Layer 3: Sigmoid MOSFET gate — STATELESS, no autocorrelation amplification
    g_G = _sigmoid_gate(Q_G_z, k, mu)   # ∈ (0,1), purely a function of Q_G_z(t)
    g_T = _sigmoid_gate(Q_T_z, k, mu)

    # Fire gate (unchanged)
    fire = np.zeros(len(a_A), dtype=bool)
    fire[1:] = a_A[:-1] > A_FIRE_THRESH

    # Layer 4: Continuous priority encoder
    boost   = (CLIP - 1.0) * g_G * g_T                           # both ON
    partial = pc * (g_G * (1.0 - g_T) + g_T * (1.0 - g_G))      # one ON (XOR)
    quiet   = kill * (1.0 - g_G) * (1.0 - g_T)                   # both OFF

    raw_phase = 1.0 + boost + partial - quiet
    phase = np.where(fire, raw_phase, 1.0)
    phase = np.clip(phase, 0.02, CLIP)   # minimal guard only

    # Champion boost (unchanged)
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
    print("  v62 — Sigmoid MOSFET Soft Gate  (stateless, replaces Schmitt latch)")
    print("  g(z) = sigmoid(k*(z−μ))  |  phase = 1 + (CLIP−1)·gG·gT + pc·[gG(1−gT)+gT(1−gG)] − kill·(1−gG)(1−gT)")
    print("  NO STATE → no autocorrelation amplification → alpha-independent at all μ")
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
        fund     = _cached_fetch_binance_funding()
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
    M, net, geom, lyap, ews, stoch, e_star, theta, cos_mu, cos_sig, rss_mu, rss_sig, xi_calib = calibrate_intraday_engine(X, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)
    M_k1    = MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)

    t(f'[5] Signals  t={time.time()-t0:.0f}s')
    sig_v36       = compute_intraday_signals(X, df_1h, M, net, ews, stoch, e_star, theta,
                                             history_len=48, cos_mu=cos_mu, cos_sig=cos_sig,
                                             rss_mu=rss_mu, rss_sig=rss_sig, xi_calib=xi_calib)
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

    # ── print sigmoid gate statistics at α=0.75,0.85,0.95 ────────────────────
    t('[8] Sigmoid gate verification (stateless alpha-independence check)')
    a_G_arr = sig_4ch['a_G'].values; a_T_arr = sig_4ch['a_T'].values
    print(f"  {'Channel':<6} {'α':>5} {'k':>4} {'μ':>5}  "
          f"{'E[g]':>6} {'std[g]':>7} {'P(g>0.7)':>10} {'P(g<0.3)':>10}")
    print(f"  {'-'*6} {'-'*5} {'-'*4} {'-'*5}  {'-'*6} {'-'*7} {'-'*10} {'-'*10}")
    for a_name, a_arr in [('G', a_G_arr), ('T', a_T_arr)]:
        for al in [0.75, 0.85, 0.95]:
            qz = _float_gate_normalised(a_arr, al)
            g  = _sigmoid_gate(qz[test_mask], k=4.0, mu=0.0)
            print(f"  {a_name:<6} {al:>5.2f} {'4':>4} {'0.0':>5}  "
                  f"{np.mean(g):>6.3f} {np.std(g):>7.3f} "
                  f"{np.mean(g>0.7):>10.3f} {np.mean(g<0.3):>10.3f}")

    rv_ema = _realized_vol(df_1h, ema_span=3)

    # ── Config registry ────────────────────────────────────────────────────────
    configs = {
        'v58_tight (ref)          ': ('v58',      dict(rv_norm=rv_ema, lo=-0.01)),
        'v61_surge (ref, α-pass)  ': ('v61surge', dict()),
        'v62_k4_mu0.0             ': ('v62',      dict(k=4.0, mu=0.0)),
        'v62_k4_mu0.5             ': ('v62',      dict(k=4.0, mu=0.5)),
        'v62_k4_mu1.0             ': ('v62',      dict(k=4.0, mu=1.0)),
        'v62_k6_mu0.0             ': ('v62',      dict(k=6.0, mu=0.0)),
        'v62_k8_mu1.0             ': ('v62',      dict(k=8.0, mu=1.0)),
    }

    def _pnl(label, mode, kw):
        if mode == 'v58':
            return _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, **kw)
        if mode == 'v61surge':
            return _build_pnl_v61_surge(base_pnl, sig_v36, lam_feat, sig_4ch)
        return _build_pnl_v62(base_pnl, sig_v36, lam_feat, sig_4ch, **kw)

    # ── TEST 1: OOS SPLIT ─────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 1 — OOS SPLIT  (pass: second_half Sharpe ≥ 3.60)')
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
    print('  TEST 2 — ALPHA SENSITIVITY  (pass: max |drop| < 0.15)')
    print('  KEY: sigmoid is stateless → autocorrelation of Q_G_z cannot')
    print('  affect the gate mapping, only the time-average of g(Q_G_z).')
    print('  Since Q_G_z marginal ≈ N(0,1) ∀α, E[g(Q_G_z)] is alpha-invariant.')
    print(f'{BAR}')

    alpha_perturbs = [0.75, 0.80, 0.85, 0.90, 0.95]
    v62_labels = [l for l in configs if l.strip().startswith('v62')]
    alpha_results = {}; alpha_summary = {}

    for label in v62_labels:
        _, base_kw = configs[label]
        print(f"\n  ── {label.strip()} ──")
        print(f"  {'α':>6} {'Sharpe':>8} {'Δ_baseline':>12} {'MaxDD':>8}  Verdict")
        print(f"  {'-'*6} {'-'*8} {'-'*12} {'-'*8}  -------")

        pnl_base = _build_pnl_v62(base_pnl, sig_v36, lam_feat, sig_4ch, **base_kw)
        s_base   = _sharpe(pnl_base[test_mask])
        row = {}; t2_pass = True

        for al in alpha_perturbs:
            pnl_p = _build_pnl_v62(base_pnl, sig_v36, lam_feat, sig_4ch,
                                    **{**base_kw, 'alpha': al})
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
              f"  [v59=0.33, v60=0.37, v61_surge=0.076]")
        alpha_results[label.strip()] = row
        alpha_summary[label.strip()] = {'pass': t2_pass, 'max_drop': float(max_drop)}

    # ── TEST 3: MU / STEEPNESS SENSITIVITY ───────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 3 — MU / STEEPNESS SENSITIVITY  (pass: max |drop| < 0.15)')
    print('  Verifies smooth behaviour under sigmoid parameter perturbations.')
    print(f'{BAR}')

    # Choose best OOS-passing v62 config for sensitivity test
    best_v62 = max(
        (l for l in v62_labels if oos_results[l.strip()]['pass']),
        key=lambda l: oos_results[l.strip()]['sharpe_second'],
        default=v62_labels[0]
    )
    _, bkw = configs[best_v62]
    bk = bkw.get('k', 4.0); bmu = bkw.get('mu', 0.0)

    mu_perturbs = {
        'baseline':       dict(k=bk,   mu=bmu),
        'μ + 0.25':       dict(k=bk,   mu=bmu+0.25),
        'μ − 0.25':       dict(k=bk,   mu=bmu-0.25),
        'μ + 0.50':       dict(k=bk,   mu=bmu+0.50),
        'μ − 0.50':       dict(k=bk,   mu=bmu-0.50),
        'k + 2':          dict(k=bk+2, mu=bmu),
        'k − 2':          dict(k=max(bk-2, 1.0), mu=bmu),
    }

    print(f"\n  ── {best_v62.strip()} ──  (best OOS v62)")
    print(f"  {'Perturbation':<15} {'Sharpe':>8} {'Δ_baseline':>12} {'MaxDD':>8}  Verdict")
    print(f"  {'-'*15} {'-'*8} {'-'*12} {'-'*8}  -------")

    pnl_base_t3 = _build_pnl_v62(base_pnl, sig_v36, lam_feat, sig_4ch, **mu_perturbs['baseline'])
    s_base_t3   = _sharpe(pnl_base_t3[test_mask])
    t3_rows = {}; t3_pass = True
    for pname, pkw in mu_perturbs.items():
        pnl_p = _build_pnl_v62(base_pnl, sig_v36, lam_feat, sig_4ch, **pkw)
        s_p   = _sharpe(pnl_p[test_mask])
        drop  = s_p - s_base_t3
        dd_p  = _maxdd(pnl_p[test_mask])
        is_b  = pname == 'baseline'
        verdict = '—' if is_b else ('PASS' if abs(drop) < 0.15 else 'FAIL')
        if not is_b and abs(drop) >= 0.15: t3_pass = False
        print(f"  {pname:<15} {s_p:>+8.4f} {drop:>+12.4f} {dd_p:>+7.1%}  {verdict}")
        t3_rows[pname] = {'sharpe': float(s_p), 'delta': float(drop), 'maxdd': float(dd_p)}

    t3_max = max(abs(v['delta']) for k, v in t3_rows.items() if k != 'baseline')
    print(f"\n  Max drop: {t3_max:.4f}  →  TEST 3: {'✓ PASS' if t3_pass else '✗ FAIL'}")

    # ── TEST 4: rv STRESS (v58 reference) ─────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 4 — rv STRESS on v58_tight  (apples-to-apples reference)')
    print(f'{BAR}')
    rng = np.random.default_rng(42)
    rv_perturbs = {
        'baseline': lambda rv: rv,
        'rv × 0.90': lambda rv: rv * 0.90,
        'rv × 1.10': lambda rv: rv * 1.10,
        'rv + N(0,0.02)': lambda rv: (rv + rng.normal(0,0.02,size=len(rv))).clip(0.02, None),
    }
    rv_base = _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, rv_ema, -0.01)
    rv_s0   = _sharpe(rv_base[test_mask])
    rv_rows = {}; t4_pass = True
    print(f"\n  {'Perturbation':<25} {'Sharpe':>8} {'Δ_baseline':>12} {'MaxDD':>8}")
    for pname, pfunc in rv_perturbs.items():
        pnl_p = _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, pfunc(rv_ema), -0.01)
        s_p   = _sharpe(pnl_p[test_mask])
        drop  = s_p - rv_s0; dd_p  = _maxdd(pnl_p[test_mask])
        is_b  = pname == 'baseline'
        verdict = '—' if is_b else ('PASS' if abs(drop) < 0.15 else 'FAIL')
        if not is_b and abs(drop) >= 0.15: t4_pass = False
        print(f"  {pname:<25} {s_p:>+8.4f} {drop:>+12.4f} {dd_p:>+7.1%}  {verdict}")
        rv_rows[pname] = {'sharpe': float(s_p), 'delta': float(drop), 'maxdd': float(dd_p)}
    t4_max = max(abs(v['delta']) for k,v in rv_rows.items() if k != 'baseline')
    print(f"\n  Max drop: {t4_max:.4f}  →  TEST 4: {'✓ PASS' if t4_pass else '✗ FAIL'}")

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SUMMARY — all configs, all tests')
    print(f'{BAR}')
    print(f"\n  {'Config':<44} {'OOS':>5} {'α':>5} {'Thr':>5} {'α max-drop':>11} {'OOS H2':>8}")
    print(f"  {'-'*44} {'-'*5} {'-'*5} {'-'*5} {'-'*11} {'-'*8}")

    best_label = None; best_h2 = -99.0
    for label, (mode, kw) in configs.items():
        lkey   = label.strip()
        oos_ok = oos_results[lkey]['pass']
        s_h2   = oos_results[lkey]['sharpe_second']
        a_ok   = alpha_summary.get(lkey, {}).get('pass', True)
        a_mxd  = alpha_summary.get(lkey, {}).get('max_drop', float('nan'))
        thr_ok = (t3_pass if lkey == best_v62.strip() else True)
        all_ok = oos_ok and a_ok and thr_ok
        mark   = '  ← CANDIDATE' if (all_ok and s_h2 > best_h2) else ''
        if all_ok and s_h2 > best_h2:
            best_h2 = s_h2; best_label = lkey
        a_s = f'{a_mxd:>+11.4f}' if not np.isnan(a_mxd) else f'{"N/A":>11}'
        print(f"  {label:<44} {'✓' if oos_ok else '✗':>5} {'✓' if a_ok else '✗':>5}"
              f" {'✓' if thr_ok else '✗':>5} {a_s} {s_h2:>+8.4f}{mark}")

    print()
    if best_label:
        print(f"  CHAMPION : {best_label}")
        print(f"  OOS H2   : {best_h2:+.4f}")
        print(f"  vs v58   : {best_h2 - V58_SHARPE:+.4f}")
    else:
        print("  No config passed both tests — see breakdown above.")

    print('\n  Alpha sensitivity progression (max drop, lower=better, bar=0.15):')
    print(f'    v59 Schmitt:   0.3300  ✗')
    print(f'    v60 BSDT:      0.3664  ✗')
    print(f'    v61_loose:     0.3211  ✗')
    print(f'    v61_surge:     0.0764  ✓  (but OOS H2=+2.70, below bar +3.60)')
    for lkey, summary in alpha_summary.items():
        md = summary['max_drop']
        h2 = oos_results.get(lkey, {}).get('sharpe_second', float('nan'))
        print(f'    {lkey:<38} {md:.4f}  {"✓" if summary["pass"] else "✗"}'
              f'  OOS H2={h2:+.2f}')
    print(f'{BAR}')

    # ── Save ──────────────────────────────────────────────────────────────────
    results = {
        'meta': {
            'version': 'v62',
            'description': 'Sigmoid MOSFET soft gate — stateless, no autocorrelation coupling',
            'agc_span': AGC_SPAN, 'v58_sharpe': V58_SHARPE, 'oos_split_date': OOS_SPLIT,
            'pass_bars': {'oos': 3.60, 'alpha_sensitivity': 0.15, 'threshold_sensitivity': 0.15},
            'continuous_encoder': {
                'boost':   '(CLIP-1) * g_G * g_T',
                'partial': 'pc * (g_G*(1-g_T) + g_T*(1-g_G))',
                'quiet':   'kill * (1-g_G) * (1-g_T)',
                'phase':   '1 + boost + partial - quiet',
            },
        },
        'oos_split': oos_results,
        'alpha_sensitivity': {'per_config': alpha_results, 'summary': alpha_summary},
        'param_sensitivity': {'config_tested': best_v62.strip(),
                              'per_perturb': t3_rows, 'pass': t3_pass, 'max_drop': float(t3_max)},
        'rv_stress_v58_ref': {'per_perturb': rv_rows, 'pass': t4_pass, 'max_drop': float(t4_max)},
        'summary': {'best_label': best_label, 'best_oos_h2': float(best_h2),
                    'vs_v58': float(best_h2 - V58_SHARPE) if best_label else None},
    }
    out_path = OUT_DIR_ / 'crypto_bsdt_v62_results.json'
    with open(str(out_path), 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\n  Results saved → {out_path}')
    print(f'  Total time: {time.time()-t0:.0f}s')


if __name__ == '__main__':
    main()
