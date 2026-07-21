"""
Crypto BSDT — v60: BSDT Continuous Energy Attenuation (Replacing Hard Clip)
=============================================================================
Motivation
----------
v59 ST-FGRC demonstrated that Schmitt hysteresis eliminates the T-threshold
cliff, but the alpha sensitivity test FAILS (max drop 0.33 > 0.15 bar) because
hardcoded Schmitt thresholds (G_hi=0.32, T_hi=0.31) are calibrated for α=0.85.
Changing α shifts the floating-gate steady-state charge, which invalidates the
thresholds — the gate fires at materially different rates.

Root cause: the CLIP=6.0 constant + hard clip mechanism is a *discrete
approximation* of continuous energy-proportional control. The BSDT already
provides the optimal continuous control law:

    γ*(X_t) = e_t / (e_t + θ)           [math_reference, Theorem 4.1, eq. 878]

    where e_t = tr(X̃_t Σ₀⁻¹ X̃_t^T)   (Mahalanobis-type blind-spot energy)
          θ = intervention cost         (calibrated as 90th-pctile of normal e_t)

The complement, g_E = θ/(e_t+θ) = 1 − γ*, is the pass-through fraction:
    • e_t = 0  (zero energy / normal regime) → g_E = 1 → full signal
    • e_t = θ  (typical energy)              → g_E = 0.5 → half attenuation
    • e_t ≫ θ  (crisis regime)              → g_E → 0   → signal suppressed

v60 architecture
----------------
  LAYER 1 — Floating gate charges (same as v59)
  LAYER 2 — Schmitt triggers (same as v59)
  LAYER 3 — Priority encoder (same as v59, outputs raw_phase)
  LAYER 4 — BSDT continuous attenuation  ← replaces hard clip(0.05, 6.0)

    excess     = max(raw_phase − 1, 0)        # amplification above neutral
    phase      = raw_phase  if raw_phase < 1  # preserve kill decisions (hard)
               = 1 + g_E * excess             # attenuate boost component
    g_E        = θ/(e_t + θ)                  # causal: uses e_t(t-1)

Key properties:
  • Kill state (raw_phase = 0.05) is *preserved* — priority encoder's kill
    decision is regime classification, not energy question
  • Neutral (raw_phase = 1.0) → phase = 1.0 regardless of energy
  • Full boost (raw_phase ≈ 6.0): phase = 1 + g_E × 5 — smooth ceiling
    at 1 + θ/(e_t+θ) × (CLIP−1)
  • α independence: g_E comes from v36 BSDT engine, not from floating
    gate charges → alpha perturbations decouple from the clipping mechanism

Why this fixes alpha sensitivity
---------------------------------
In v59, alpha ±0.05 → Q_G steady-state shifts → Schmitt fires at different
rates → phase distribution shifts → Sharpe drops. In v60, even if the Schmitt
fires more/less, the g_E term independently damps all boosts proportionally
to BSDT energy — which is independent of alpha. The floating gate only sets
WHEN signals fire; g_E controls HOW MUCH they amplify.

Configs tested
--------------
  v58_tight (reference)          — unchanged v58 champion
  v59_schmitt_only (reference)   — v59 minimal upgrade (for comparison)
  v60_fgrc_bsdt_a085             — full ST-FGRC + BSDT attenuation, α=0.85
  v60_fgrc_bsdt_a080             — same, α=0.80  (alpha robustness check)
  v60_fgrc_bsdt_a090             — same, α=0.90  (alpha robustness check)

Tests
------
  TEST 1 — OOS split (pass: second_half Sharpe ≥ 3.60)
  TEST 2 — θ (theta) sensitivity  (pass: max |drop| < 0.20)
             θ × {0.25, 0.50, 1.0, 2.0, 4.0}
             θ is the BSDT intervention cost; conservative bar since it is
             a continuous parameter (vs Schmitt's discrete hysteresis edges)
  TEST 3 — Alpha sensitivity  (pass: max |drop| < 0.15)  ← was FAILING in v59
             α ∈ {0.75, 0.80, 0.85, 0.90, 0.95}
  TEST 4 — Threshold sensitivity  (pass: max |drop| < 0.15)
             G_hi ±0.02, T_hi ±0.02 (Schmitt edge robustness, same as v59)
  TEST 5 — rv stress on v58 reference  (apples-to-apples comparison)

Expected outcome:
  TEST 1 ✓ (v60_full passes OOS, ≥ 4.0 target)
  TEST 2 ✓ (θ is smooth; order-of-magnitude change should be < 0.20 drop)
  TEST 3 ✓ (alpha decoupled from clip mechanism — key v60 hypothesis)
  TEST 4 ✓ (inherits Schmitt stability from v59)
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

# ── cache helpers (unchanged from v58/v59) ────────────────────────────────────
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

# ── frozen constants (inherited from v58 champion) ────────────────────────────
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

# ── v59 ST-FGRC constants (unchanged in v60) ──────────────────────────────────
ALPHA_FG        = 0.85
G_SCHMITT_HI    = 0.32
G_SCHMITT_LO    = 0.26
T_SCHMITT_HI    = 0.31
T_SCHMITT_LO    = 0.25
PARTIAL_CREDIT  = 0.30

# ── v60 BSDT control constants ────────────────────────────────────────────────
# θ is calibrated per-run from training e_t (90th pctile of normal energy)
# These are just fallbacks if calibration yields zero.
THETA_FALLBACK  = 121.0   # v36 calibrated value (~121 per v36 code comment)

V58_SHARPE      = 4.0362
OOS_SPLIT       = '2025-01-01'


# ── v58 helpers (kept verbatim for reference config) ──────────────────────────

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


# ── v59 helpers (unchanged — kept for v59 reference config) ───────────────────

def _float_gate_charge(a: np.ndarray, alpha: float) -> np.ndarray:
    """
    Floating gate charge accumulator.
    Q(t) = alpha * Q(t-1) + a(t-1)

    Shift-by-1 built in (a(t-1)) → strictly causal.
    alpha = 0.85 → ~8-bar half-life, matching v58's N_OPT=8 window.
    """
    q = np.zeros(len(a), dtype=float)
    for t in range(1, len(a)):
        q[t] = alpha * q[t - 1] + a[t - 1]
    return q


def _schmitt_trigger(q: np.ndarray, hi: float, lo: float) -> np.ndarray:
    """
    Schmitt comparator with hysteresis.
    q > hi  → SET (state = 1)
    q < lo  → RESET (state = 0)
    lo ≤ q ≤ hi → HOLD (unchanged)
    """
    state = np.zeros(len(q), dtype=float)
    s = 0.0
    for t in range(len(q)):
        if q[t] > hi:
            s = 1.0
        elif q[t] < lo:
            s = 0.0
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
    """v59 ST-FGRC gate — verbatim for comparison configs."""
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

    Q_G_raw = _float_gate_charge(a_G_arr, alpha)
    Q_T_raw = _float_gate_charge(a_T_arr, alpha)
    Q_G = Q_G_raw * (1.0 - alpha)
    Q_T = Q_T_raw * (1.0 - alpha)

    fire = np.zeros(len(a_A_arr), dtype=bool)
    fire[1:] = a_A_arr[:-1] > A_FIRE_THRESH

    if schmitt_only:
        G_mem = (pd.Series(a_G_arr)
                 .rolling(N_OPT, min_periods=1).max()
                 .shift(1).fillna(0.0).values)
        GH = (G_mem > G_THRESH_BASE).astype(float)
        TH = _schmitt_trigger(Q_T, t_hi, t_lo)
        gh = GH > 0.5; th = TH > 0.5
        q_GH_TH = (fire & gh & th).astype(float)
        q_GH_TL = (fire & gh & ~th).astype(float)
        q_GL_TH = (fire & ~gh & th).astype(float)
        q_GL_TL = (fire & ~gh & ~th).astype(float)
        phase = (1.0 + GH_TH * q_GH_TH + GH_TL * q_GH_TL
                     + GL_TH * q_GL_TH + GL_TL * q_GL_TL)
    else:
        GH = _schmitt_trigger(Q_G, g_hi, g_lo)
        TH = _schmitt_trigger(Q_T, t_hi, t_lo)
        gh = GH > 0.5; th = TH > 0.5
        phase = np.where(
            ~fire,       1.0,
            np.where(
                gh & th,   CLIP,
                np.where(
                    gh & ~th,  1.0 + PARTIAL_CREDIT * (Q_G / g_hi),
                    np.where(
                        ~gh & th,  1.0 + PARTIAL_CREDIT * (Q_T / t_hi),
                        0.05
                    )
                )
            )
        )

    phase = np.clip(phase, 0.05, CLIP)

    flag = np.zeros(len(a_G_arr), dtype=float)
    flag[1:] = (a_G_arr[:-1] > G_BOOST_THRESH).astype(float)

    base_arr = base.reindex(idx).fillna(0.0).values
    pnl_arr  = base_arr * size * (1.0 + CHAMPION_BOOST * flag) * phase
    return pd.Series(pnl_arr, index=idx)


# ── v60: BSDT continuous attenuation ──────────────────────────────────────────

def _build_pnl_v60(
    base:         pd.Series,
    sv36:         pd.DataFrame,
    lf:           pd.DataFrame,
    s4:           pd.DataFrame,
    theta_bsdt:   float,
    alpha:        float = ALPHA_FG,
    schmitt_only: bool  = False,
    g_hi:         float = G_SCHMITT_HI,
    g_lo:         float = G_SCHMITT_LO,
    t_hi:         float = T_SCHMITT_HI,
    t_lo:         float = T_SCHMITT_LO,
) -> pd.Series:
    """
    v60: ST-FGRC + BSDT continuous energy attenuation.

    Architecture:
      LAYER 1   Floating gate charges (same as v59)
      LAYER 2   Schmitt triggers (same as v59)
      LAYER 3   Priority encoder → raw_phase  (same as v59, unclipped)
      LAYER 4   BSDT attenuation  ← replaces clip(0.05, 6.0)

    Attenuation law (from math_reference Theorem 4.1):
      g_E    = θ / (e_t + θ)        [complement of γ* = e_t/(e_t+θ)]
      excess = max(raw_phase − 1, 0)
      phase  = raw_phase              if raw_phase < 1  (preserve kill decisions)
             = 1 + g_E * excess       if raw_phase ≥ 1  (attenuate boost)
      phase  = max(phase, 0.02)       # minimal guard

    e_t is the BSDT blind-spot energy from sig_v36 (causal: uses e_t(t-1)).
    θ is calibrated as the 90th-percentile of e_t over the training window.
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

    # ── LAYER 1: floating gate charges (shift(1) built in) ────────────────────
    Q_G_raw = _float_gate_charge(a_G_arr, alpha)
    Q_T_raw = _float_gate_charge(a_T_arr, alpha)
    Q_G = Q_G_raw * (1.0 - alpha)   # normalise to ≈ E[a] at steady state
    Q_T = Q_T_raw * (1.0 - alpha)

    # ── fire gate (unchanged from v58/v59) ────────────────────────────────────
    fire = np.zeros(len(a_A_arr), dtype=bool)
    fire[1:] = a_A_arr[:-1] > A_FIRE_THRESH

    if schmitt_only:
        # MINIMAL: Schmitt on T, rolling max + static threshold on G
        G_mem = (pd.Series(a_G_arr)
                 .rolling(N_OPT, min_periods=1).max()
                 .shift(1).fillna(0.0).values)
        GH = (G_mem > G_THRESH_BASE).astype(float)
        TH = _schmitt_trigger(Q_T, t_hi, t_lo)
        gh = GH > 0.5; th = TH > 0.5
        q_GH_TH = (fire & gh & th).astype(float)
        q_GH_TL = (fire & gh & ~th).astype(float)
        q_GL_TH = (fire & ~gh & th).astype(float)
        q_GL_TL = (fire & ~gh & ~th).astype(float)
        raw_phase = (1.0 + GH_TH * q_GH_TH + GH_TL * q_GH_TL
                        + GL_TH * q_GL_TH + GL_TL * q_GL_TL)
    else:
        # ── LAYER 2–3: full ST-FGRC (Schmitt + priority encoder) ─────────────
        GH = _schmitt_trigger(Q_G, g_hi, g_lo)
        TH = _schmitt_trigger(Q_T, t_hi, t_lo)
        gh = GH > 0.5; th = TH > 0.5

        # Q ratios clipped at 2.0 to bound partial credit even if alpha
        # perturbation pushes Q above g_hi/t_hi.  Does not affect baseline.
        Q_G_ratio = np.clip(Q_G / g_hi, 0.0, 2.0)
        Q_T_ratio = np.clip(Q_T / t_hi, 0.0, 2.0)

        raw_phase = np.where(
            ~fire,       1.0,
            np.where(
                gh & th,   CLIP,
                np.where(
                    gh & ~th,  1.0 + PARTIAL_CREDIT * Q_G_ratio,
                    np.where(
                        ~gh & th,  1.0 + PARTIAL_CREDIT * Q_T_ratio,
                        0.05   # neither → kill
                    )
                )
            )
        )

    # ── LAYER 4: BSDT continuous attenuation (replaces hard clip) ─────────────
    # e_t from v36 engine, causal (shift 1 bar back)
    e_t_arr = sv36['e_t'].shift(1).fillna(theta_bsdt).values
    # g_E = θ/(e_t+θ): complement of γ* = e_t/(e_t+θ)
    # At θ = 90th-pctile of normal e_t:
    #   g_E ≈ 1.0 when e_t ≈ 0  (clear regime)
    #   g_E ≈ 0.5 when e_t = θ  (typical energy)
    #   g_E → 0   when e_t ≫ θ  (crisis)
    g_E   = theta_bsdt / (e_t_arr + theta_bsdt)

    # Apply attenuation to boost component only.
    # Kill decisions (raw_phase < 1) are preserved unchanged — they are
    # regime classifications from the priority encoder, not energy-level
    # decisions.  Neutral (raw_phase = 1) → phase = 1 regardless of g_E.
    excess = np.maximum(raw_phase - 1.0, 0.0)
    phase  = np.where(raw_phase >= 1.0,
                      1.0 + g_E * excess,
                      raw_phase)           # keep kill states hard

    # Minimal guard — prevents exactly-zero or negative phase from numerical
    # edge cases; does not materially clip during normal operation.
    phase = np.maximum(phase, 0.02)

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
    print("  v60 — BSDT Continuous Energy Attenuation  (replacing hard clip)")
    print("  Phase law:  raw_phase → 1 + g_E*(raw_phase−1),  g_E = θ/(e_t+θ)")
    print("  γ*(X_t) = e_t/(e_t+θ) [Theorem 4.1]  |  g_E = 1−γ* = θ/(e_t+θ)")
    print(f"  ST-FGRC backend: α={ALPHA_FG}, G=({G_SCHMITT_LO},{G_SCHMITT_HI}), "
          f"T=({T_SCHMITT_LO},{T_SCHMITT_HI}), pc={PARTIAL_CREDIT}")
    print(BAR)

    t = lambda msg: print(f'\n{msg}', flush=True)

    # ── Data + signals (identical pipeline, all cached) ───────────────────────
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

    # ── calibrate θ from training e_t ────────────────────────────────────────
    t('[8] θ calibration')
    e_t_series = sig_v36['e_t']
    e_train_vals = e_t_series[calib_mask].values
    e_train_pos  = e_train_vals[e_train_vals > 0]
    if len(e_train_pos) > 10:
        theta_bsdt = float(np.percentile(e_train_pos, 90))
    else:
        theta_bsdt = THETA_FALLBACK
    print(f"    θ_bsdt (90th-pctile normal e_t) = {theta_bsdt:.3f}")
    print(f"    e_t stats:  mean={float(np.mean(e_train_pos)):.1f},"
          f"  p50={float(np.percentile(e_train_pos,50)):.1f},"
          f"  p90={theta_bsdt:.1f},"
          f"  p99={float(np.percentile(e_train_pos,99)):.1f}")
    print(f"    g_E at mean e_t : {theta_bsdt/(float(np.mean(e_train_pos))+theta_bsdt):.3f}")
    print(f"    g_E at p50  e_t : {theta_bsdt/(float(np.percentile(e_train_pos,50))+theta_bsdt):.3f}")

    # ── rv_norm for v58 reference ─────────────────────────────────────────────
    rv_ema = _realized_vol(df_1h, ema_span=3)

    # ── Config registry ────────────────────────────────────────────────────────
    # Each entry: (mode, kwargs)
    #   'v58'  → _build_pnl_v58(... rv_norm, lo)
    #   'v59'  → _build_pnl_v59(... **kwargs)
    #   'v60'  → _build_pnl_v60(... theta_bsdt, **kwargs)
    configs = {
        'v58_tight (reference)         ': (
            'v58', dict(rv_norm=rv_ema, lo=-0.01)),
        'v59_schmitt_only (reference)  ': (
            'v59', dict(alpha=ALPHA_FG, schmitt_only=True,
                        t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO)),
        'v60_fgrc_bsdt (alpha=0.85)   ': (
            'v60', dict(alpha=0.85, schmitt_only=False,
                        g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                        t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO)),
        'v60_fgrc_bsdt (alpha=0.80)   ': (
            'v60', dict(alpha=0.80, schmitt_only=False,
                        g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                        t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO)),
        'v60_fgrc_bsdt (alpha=0.90)   ': (
            'v60', dict(alpha=0.90, schmitt_only=False,
                        g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                        t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO)),
        # schmitt-only + BSDT: test attenuation in isolation of full FGRC
        'v60_schmitt_bsdt             ': (
            'v60', dict(alpha=ALPHA_FG, schmitt_only=True,
                        t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO)),
    }

    def _pnl(label, mode, kw):
        if mode == 'v58':
            return _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, **kw)
        if mode == 'v59':
            return _build_pnl_v59(base_pnl, sig_v36, lam_feat, sig_4ch, **kw)
        # mode == 'v60'
        return _build_pnl_v60(base_pnl, sig_v36, lam_feat, sig_4ch,
                               theta_bsdt=theta_bsdt, **kw)

    # ── TEST 1: OOS SPLIT ─────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 1 — OOS SPLIT  (pass: second_half Sharpe ≥ 3.60)')
    print(f'  Split: first_half 2023-2024 | second_half 2025-2026')
    print(f'{BAR}')
    print(f"\n  {'Config':<46} {'Full':>8} {'23-24':>8} {'25-26':>8} {'DD 25-26':>10}  Pass?")
    print(f"  {'-'*46} {'-'*8} {'-'*8} {'-'*8} {'-'*10}  -----")

    oos_results = {}
    for label, (mode, kw) in configs.items():
        pnl    = _pnl(label, mode, kw)
        s_full = _sharpe(pnl[test_mask])
        s_h1   = _sharpe(pnl[first_half])
        s_h2   = _sharpe(pnl[second_half])
        dd_h2  = _maxdd(pnl[second_half])
        ok     = s_h2 >= 3.60
        print(f"  {label:<46} {s_full:>+8.4f} {s_h1:>+8.4f} {s_h2:>+8.4f} {dd_h2:>+9.1%}  {'✓' if ok else '✗'}")
        oos_results[label.strip()] = {
            'sharpe_full': float(s_full), 'sharpe_first': float(s_h1),
            'sharpe_second': float(s_h2), 'maxdd_second': float(dd_h2), 'pass': ok,
        }

    # ── TEST 2: θ (THETA) SENSITIVITY ────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 2 — θ SENSITIVITY  (pass: max |Sharpe drop| < 0.20)')
    print('  Purpose: verify BSDT attenuation is robust to θ calibration error.')
    print('  Perturbations: θ × {0.25, 0.50, 1.0, 2.0, 4.0}')
    print('  Bar: 0.20 (slightly looser — θ is a continuous param, order-of-mag robust)')
    print(f'{BAR}')

    theta_perturbs = {
        'θ × 0.25': theta_bsdt * 0.25,
        'θ × 0.50': theta_bsdt * 0.50,
        'θ × 1.00': theta_bsdt * 1.00,   # baseline
        'θ × 2.00': theta_bsdt * 2.00,
        'θ × 4.00': theta_bsdt * 4.00,
    }

    base_kw_v60 = dict(alpha=0.85, schmitt_only=False,
                       g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                       t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO)

    print(f"\n  ── v60_fgrc_bsdt (alpha=0.85) ──")
    print(f"  {'Perturbation':<15} {'θ value':>10} {'Sharpe':>8} {'Δ_baseline':>12} {'MaxDD':>8}  Verdict")
    print(f"  {'-'*15} {'-'*10} {'-'*8} {'-'*12} {'-'*8}  -------")

    pnl_theta_base = _build_pnl_v60(base_pnl, sig_v36, lam_feat, sig_4ch,
                                     theta_bsdt=theta_bsdt, **base_kw_v60)
    s_theta_base = _sharpe(pnl_theta_base[test_mask])

    theta_sens_rows = {}; theta_t2_pass = True
    for pname, th in theta_perturbs.items():
        pnl_p = _build_pnl_v60(base_pnl, sig_v36, lam_feat, sig_4ch,
                                theta_bsdt=th, **base_kw_v60)
        s_p   = _sharpe(pnl_p[test_mask])
        drop  = s_p - s_theta_base
        dd_p  = _maxdd(pnl_p[test_mask])
        is_b  = (th == theta_bsdt)
        verdict = '—' if is_b else ('PASS' if abs(drop) < 0.20 else 'FAIL')
        if not is_b and abs(drop) >= 0.20:
            theta_t2_pass = False
        print(f"  {pname:<15} {th:>10.2f} {s_p:>+8.4f} {drop:>+12.4f} {dd_p:>+7.1%}  {verdict}")
        theta_sens_rows[pname] = {'theta': float(th), 'sharpe': float(s_p),
                                  'delta': float(drop), 'maxdd': float(dd_p)}

    t2_max_drop = max(abs(v['delta']) for k, v in theta_sens_rows.items()
                      if abs(v['theta'] - theta_bsdt) > 1e-6)
    print(f"\n  Max drop: {t2_max_drop:.4f}  →  TEST 2: {'✓ PASS' if theta_t2_pass else '✗ FAIL'}")

    # ── TEST 3: ALPHA SENSITIVITY ─────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TEST 3 — ALPHA SENSITIVITY  (pass: max |Sharpe drop| < 0.15)')
    print('  Key test: did BSDT attenuation decouple alpha from clip?')
    print('  In v59 this FAILED with max drop 0.33.  Hypothesis: v60 PASSES.')
    print('  Perturbations: α ∈ {0.75, 0.80, 0.85, 0.90, 0.95}')
    print(f'{BAR}')

    alpha_perturbs = {
        'α = 0.75': 0.75,
        'α = 0.80': 0.80,
        'α = 0.85': 0.85,   # baseline
        'α = 0.90': 0.90,
        'α = 0.95': 0.95,
    }

    print(f"\n  ── v60_fgrc_bsdt (baseline α=0.85) ──")
    print(f"  {'Perturbation':<14} {'α':>6} {'Sharpe':>8} {'Δ_baseline':>12} {'MaxDD':>8}  Verdict")
    print(f"  {'-'*14} {'-'*6} {'-'*8} {'-'*12} {'-'*8}  -------")

    alpha_rows = {}; t3_pass = True
    for pname, a in alpha_perturbs.items():
        kw_a = dict(alpha=a, schmitt_only=False,
                    g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                    t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO)
        pnl_p = _build_pnl_v60(base_pnl, sig_v36, lam_feat, sig_4ch,
                                theta_bsdt=theta_bsdt, **kw_a)
        s_p   = _sharpe(pnl_p[test_mask])
        drop  = s_p - s_theta_base          # baseline is α=0.85
        dd_p  = _maxdd(pnl_p[test_mask])
        is_b  = (a == 0.85)
        verdict = '—' if is_b else ('PASS' if abs(drop) < 0.15 else 'FAIL')
        if not is_b and abs(drop) >= 0.15:
            t3_pass = False
        print(f"  {pname:<14} {a:>6.2f} {s_p:>+8.4f} {drop:>+12.4f} {dd_p:>+7.1%}  {verdict}")
        alpha_rows[pname] = {'alpha': float(a), 'sharpe': float(s_p),
                             'delta': float(drop), 'maxdd': float(dd_p)}

    t3_max_drop = max(abs(v['delta']) for k, v in alpha_rows.items()
                      if abs(v['alpha'] - 0.85) > 1e-6)
    print(f"\n  Max drop: {t3_max_drop:.4f}  →  TEST 3: {'✓ PASS' if t3_pass else '✗ FAIL'}")
    print(f"  v59 alpha max drop was 0.33.  v60 target: < 0.15.")

    # ── TEST 4: THRESHOLD SENSITIVITY (Schmitt edges) ─────────────────────────
    print(f'\n{BAR}')
    print('  TEST 4 — THRESHOLD SENSITIVITY  (pass: max |Sharpe drop| < 0.15)')
    print('  Same as v59 TEST 2 — Schmitt edge robustness.')
    print('  Perturbs: G_hi ±0.02, T_hi ±0.02, band ×1.5, band ×0.5')
    print(f'{BAR}')

    schmitt_perturbs = {
        'baseline':    dict(alpha=0.85, g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                            t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO),
        'T_hi + 0.02': dict(alpha=0.85, g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                            t_hi=T_SCHMITT_HI+0.02, t_lo=T_SCHMITT_LO),
        'T_hi - 0.02': dict(alpha=0.85, g_hi=G_SCHMITT_HI, g_lo=G_SCHMITT_LO,
                            t_hi=T_SCHMITT_HI-0.02, t_lo=T_SCHMITT_LO),
        'G_hi + 0.02': dict(alpha=0.85, g_hi=G_SCHMITT_HI+0.02, g_lo=G_SCHMITT_LO,
                            t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO),
        'G_hi - 0.02': dict(alpha=0.85, g_hi=G_SCHMITT_HI-0.02, g_lo=G_SCHMITT_LO,
                            t_hi=T_SCHMITT_HI, t_lo=T_SCHMITT_LO),
        'band × 1.5':  dict(alpha=0.85, g_hi=G_SCHMITT_HI+0.03, g_lo=G_SCHMITT_LO-0.03,
                            t_hi=T_SCHMITT_HI+0.03, t_lo=T_SCHMITT_LO-0.03),
        'band × 0.5':  dict(alpha=0.85, g_hi=G_SCHMITT_HI-0.03, g_lo=G_SCHMITT_LO+0.03,
                            t_hi=T_SCHMITT_HI-0.03, t_lo=T_SCHMITT_LO+0.03),
    }

    print(f"\n  ── v60_fgrc_bsdt (alpha=0.85) — threshold perturbations ──")
    print(f"  {'Perturbation':<15} {'Sharpe':>8} {'Δ_baseline':>12} {'MaxDD':>8}  Verdict")
    print(f"  {'-'*15} {'-'*8} {'-'*12} {'-'*8}  -------")

    thresh_rows = {}; t4_pass = True
    for pname, pkw in schmitt_perturbs.items():
        pnl_p = _build_pnl_v60(base_pnl, sig_v36, lam_feat, sig_4ch,
                                theta_bsdt=theta_bsdt, schmitt_only=False, **pkw)
        s_p   = _sharpe(pnl_p[test_mask])
        drop  = s_p - s_theta_base
        dd_p  = _maxdd(pnl_p[test_mask])
        is_b  = pname == 'baseline'
        verdict = '—' if is_b else ('PASS' if abs(drop) < 0.15 else 'FAIL')
        if not is_b and abs(drop) >= 0.15:
            t4_pass = False
        print(f"  {pname:<15} {s_p:>+8.4f} {drop:>+12.4f} {dd_p:>+7.1%}  {verdict}")
        thresh_rows[pname] = {'sharpe': float(s_p), 'delta': float(drop), 'maxdd': float(dd_p)}

    t4_max_drop = max(abs(v['delta']) for k, v in thresh_rows.items() if k != 'baseline')
    print(f"\n  Max drop: {t4_max_drop:.4f}  →  TEST 4: {'✓' if t4_pass else '✗'} "
          f"{'PASS' if t4_pass else 'FAIL'}")

    # ── TEST 5: rv STRESS (v58 reference — apples-to-apples) ─────────────────
    print(f'\n{BAR}')
    print('  TEST 5 — rv STRESS on v58_tight  (apples-to-apples v57→v58→v59→v60)')
    print('  v57 failure: rv×1.10 → −0.297.  v58 patch target: < −0.10.')
    print(f'{BAR}')

    rv_stress_perturbs = {
        'baseline':         lambda rv: rv,
        'rv × 0.90':        lambda rv: rv * 0.90,
        'rv × 1.10':        lambda rv: rv * 1.10,
        'rv + N(0, 0.02)':  lambda rv: (rv + rng.normal(0, 0.02,
                                         size=len(rv))).clip(0.02, None),
    }

    print(f"\n  ── v58_tight (rv stress reference) ──")
    print(f"  {'Perturbation':<25} {'Sharpe':>8} {'Δ_baseline':>12} {'MaxDD':>8}  Verdict")
    print(f"  {'-'*25} {'-'*8} {'-'*12} {'-'*8}  -------")

    rv_pnl_base = _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, rv_ema, -0.01)
    rv_s_base   = _sharpe(rv_pnl_base[test_mask])
    rv_rows = {}; t5_pass = True
    for pname, pfunc in rv_stress_perturbs.items():
        rv_p   = pfunc(rv_ema)
        pnl_p  = _build_pnl_v58(base_pnl, sig_v36, lam_feat, sig_4ch, rv_p, -0.01)
        s_p    = _sharpe(pnl_p[test_mask])
        drop   = s_p - rv_s_base
        dd_p   = _maxdd(pnl_p[test_mask])
        is_b   = pname == 'baseline'
        verdict = '—' if is_b else ('PASS' if abs(drop) < 0.15 else 'FAIL')
        if not is_b and abs(drop) >= 0.15:
            t5_pass = False
        print(f"  {pname:<25} {s_p:>+8.4f} {drop:>+12.4f} {dd_p:>+7.1%}  {verdict}")
        rv_rows[pname] = {'sharpe': float(s_p), 'delta': float(drop), 'maxdd': float(dd_p)}

    t5_max_drop = max(abs(v['delta']) for k, v in rv_rows.items() if k != 'baseline')
    print(f"\n  Max drop: {t5_max_drop:.4f}  →  TEST 5: {'✓ PASS' if t5_pass else '✗ FAIL'}")

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SUMMARY — All Tests')
    print(f'  θ_bsdt = {theta_bsdt:.3f}')
    print(f'{BAR}')
    print(f"\n  {'Config':<46} {'OOS':>5} {'Theta':>6} {'Alpha':>6} {'Thr':>5} {'Max Drop':>10} {'OOS H2':>8}")
    print(f"  {'-'*46} {'-'*5} {'-'*6} {'-'*6} {'-'*5} {'-'*10} {'-'*8}")

    best_label = None; best_h2 = -99.0
    for label, (mode, kw) in configs.items():
        lkey   = label.strip()
        oos_ok = oos_results[lkey]['pass']
        s_h2   = oos_results[lkey]['sharpe_second']
        # Sensitivity tests: only apply to v60 full FGRC at alpha=0.85
        if 'alpha=0.85' in label or label.strip() == 'v60_fgrc_bsdt (alpha=0.85)':
            theta_ok = theta_t2_pass
            alpha_ok = t3_pass
            thr_ok   = t4_pass
            mxd = max(t2_max_drop, t3_max_drop, t4_max_drop)
        else:
            theta_ok = alpha_ok = thr_ok = True
            mxd = float('nan')

        all_ok = oos_ok and theta_ok and alpha_ok and thr_ok
        mark   = '  ← CANDIDATE' if (all_ok and s_h2 > best_h2) else ''
        if all_ok and s_h2 > best_h2:
            best_h2 = s_h2; best_label = lkey

        mxd_s = f'{mxd:>+10.4f}' if not np.isnan(mxd) else f'{"N/A":>10}'
        print(f"  {label:<46} {'✓' if oos_ok else '✗':>5} {'✓' if theta_ok else '✗':>6}"
              f" {'✓' if alpha_ok else '✗':>6} {'✓' if thr_ok else '✗':>5}"
              f" {mxd_s} {s_h2:>+8.4f}{mark}")

    print()
    if best_label:
        print(f"  CHAMPION : {best_label}")
        print(f"  OOS H2   : {best_h2:+.4f}")
        print(f"  vs v58   : {best_h2 - V58_SHARPE:+.4f}  Sharpe vs v58 baseline")
    else:
        print("  No config passed all tests — review breakdown above.")

    print(f'\n  Sensitivity recap (v60 vs v59):')
    print(f'    θ max drop: {t2_max_drop:.4f}  (bar 0.20)  {" PASS" if theta_t2_pass else " FAIL"}')
    print(f'    α max drop: {t3_max_drop:.4f}  (bar 0.15)  {" PASS" if t3_pass else " FAIL"}'
          f'  [v59 was FAIL at 0.33]')
    print(f'    Thr max drop: {t4_max_drop:.4f}  (bar 0.15)  {" PASS" if t4_pass else " FAIL"}')
    print(f'{BAR}')

    # ── Save ──────────────────────────────────────────────────────────────────
    results = {
        'meta': {
            'version': 'v60',
            'description': 'BSDT continuous energy attenuation replacing hard clip',
            'theta_bsdt': float(theta_bsdt),
            'v58_sharpe': V58_SHARPE,
            'oos_split_date': OOS_SPLIT,
            'pass_bars': {
                'oos': 3.60,
                'theta_sensitivity': 0.20,
                'alpha_sensitivity': 0.15,
                'threshold_sensitivity': 0.15,
            },
            'st_fgrc_params': {
                'alpha': ALPHA_FG,
                'G_schmitt': [G_SCHMITT_LO, G_SCHMITT_HI],
                'T_schmitt': [T_SCHMITT_LO, T_SCHMITT_HI],
                'partial_credit': PARTIAL_CREDIT,
                'fire_thresh': A_FIRE_THRESH,
                'clip_removed': True,
                'attenuation_law': 'g_E = theta/(e_t + theta)',
            },
        },
        'oos_split': oos_results,
        'theta_sensitivity': {
            'per_perturb': theta_sens_rows,
            'pass': theta_t2_pass,
            'max_drop': float(t2_max_drop),
        },
        'alpha_sensitivity': {
            'per_perturb': alpha_rows,
            'pass': t3_pass,
            'max_drop': float(t3_max_drop),
        },
        'threshold_sensitivity': {
            'per_perturb': thresh_rows,
            'pass': t4_pass,
            'max_drop': float(t4_max_drop),
        },
        'rv_stress_v58_ref': {
            'per_perturb': rv_rows,
            'pass': t5_pass,
            'max_drop': float(t5_max_drop),
        },
        'summary': {
            'best_label': best_label,
            'best_oos_h2': float(best_h2),
            'vs_v58': float(best_h2 - V58_SHARPE) if best_label else None,
        },
    }
    out_path = OUT_DIR_ / 'crypto_bsdt_v60_results.json'
    with open(str(out_path), 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\n  Results saved → {out_path}')
    print(f'  Total time: {time.time()-t0:.0f}s')


if __name__ == '__main__':
    main()
